"""El acompañante: el hilo que hace sonar la pieza de fondo siguiendo el carril.

La Task 2 (`nucleo.acompanamiento`) dejo el render determinista y la Task 3
(`nucleo.gemelo.salida`) el capturador que permite probar lo que suena sin
altavoces. Esto es lo que las une: un hilo que, bloque a bloque, pregunta por
donde va la pasada, corta la rodaja que corresponde y la escribe en la tarjeta.

**El acompañante NO lleva reloj propio** (decision M2 de la spec, y no es
negociable). En cada bloque pregunta el cabezal, calcula la rodaja y la escribe.
No acumula posicion, no cuenta bloques para saber donde va, no interpola. El
motivo: cualquier reloj propio DERIVA del carril, y el carril ya sabe de bucles,
cuenta atras, saltos de compas, pausa por falta de señal y factor de tempo. Un
segundo reloj seria un segundo sitio donde el bucle puede equivocarse, y la
etapa anterior gasto una etapa entera demostrando que dos copias de la misma
regla nunca son la misma regla. **Si el cabezal salta, el audio salta: eso es lo
correcto.**

**La forma del hilo se copia de `Metronomo` y no se inventa**: contador de
generacion incrementado antes que nada en `detener()`, bandera de pausa con
`Event`, `join(timeout=1.0)` y la comprobacion de generacion DESPUES de que
`reproducir()` retorne. Ese codigo esta probado contra el hilo huerfano que
sobrevive a un `join` vencido -un defecto real que la etapa 3c pago- y el
docstring de `Metronomo.detener` explica por que. Lo unico que no se copia es el
reloj: `Metronomo` lleva el suyo porque el es la fuente del pulso; aqui la
fuente es el carril.

**El cabezal es una funcion, no un objeto de sesion.** El acompañante no sabe
que existe una `SesionDeEstudio` y no puede tocarla: recibe una clausura que
devuelve el instante de la pieza en pulsos, o `None` si ahora mismo no hay nada
que suene. Asi el acompañante no puede derivar del carril ni por accidente,
porque no tiene con que.
"""

import threading
from typing import Callable

import numpy as np

from nucleo.acompanamiento import PiezaRenderizada
from nucleo.sintesis import INTERVALO_SONDEO_S, SalidaAudio

# Cuantas muestras lleva cada escritura por omision. A 48 kHz son 21,3 ms: lo
# bastante corto para que un salto del cabezal se oiga enseguida y lo bastante
# largo para que el hilo no se pase el dia entrando y saliendo de PortAudio.
BLOQUE_POR_OMISION = 1024


class BloqueadoAhora(Exception):
    """El cabezal no se pudo leer sin esperar.

    La lanza la clausura que el llamante pasa a `iniciar`, y el acompañante la
    trata reutilizando el ultimo cabezal conocido. Vive aqui porque el que la
    trata es este modulo, y quien la lanza (`servidor/piezas.py`, Task 5) la
    importa.

    El caso real: la clausura hace `acquire(blocking=False)` sobre el candado de
    la sesion y falla porque el hilo de analisis esta dentro. Esperar el candado
    dejaria la tarjeta sin alimentar durante un bloque entero, y escribir ceros
    seria un agujero audible en medio de la pieza. Repetir el ultimo instante
    conocido es, como mucho, un bloque de 21 ms que suena dos veces.
    """


class Acompanante:
    """Hace sonar una `PiezaRenderizada` en un hilo, al compas del cabezal ajeno.

    Uso: `cargar(renderizada)`, `iniciar(cabezal)`, y el hilo se encarga.
    `cargar()` y `ganancia()` se pueden llamar en caliente desde cualquier hilo
    y se aplican en el bloque SIGUIENTE, nunca a medias dentro del que esta en
    vuelo. `pausar()`/`reanudar()` dejan de alimentar la tarjeta sin cerrar el
    stream, y `detener()` mata el hilo.

    Sin dispositivo de audio `iniciar()` devuelve False y no lanza: es el mismo
    contrato que `Metronomo`, porque quedarse sin fondo degrada la experiencia y
    no la impide.
    """

    def __init__(
        self,
        salida: SalidaAudio | None = None,
        bloque: int = BLOQUE_POR_OMISION,
    ) -> None:
        bloque = int(bloque)
        if bloque < 1:
            # Falla aqui y no dentro del hilo, donde la excepcion moriria sin
            # que nadie la vea y el fondo simplemente no sonaria.
            raise ValueError(f"El bloque {bloque} no sirve: tiene que ser al menos 1 muestra")
        self.bloque = bloque
        self._salida = salida or SalidaAudio()
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._pausado = threading.Event()
        # Candado PROPIO del acompañante, no el de la sesion: protege lo que se
        # puede cambiar en caliente (la pieza y la ganancia pedida) para que el
        # hilo tome una foto coherente al empezar cada bloque.
        self._candado = threading.Lock()
        self._renderizada: PiezaRenderizada | None = None
        self._ganancia_pedida = 1.0
        # La ganancia que de verdad salio en la ultima muestra escrita. Solo la
        # toca el hilo, asi que no necesita candado.
        self._ganancia_aplicada = 1.0
        self._cabezal: Callable[[], float | None] | None = None
        self._ultimo_instante: float | None = None
        # Contador de generacion: `detener()` lo incrementa antes de tocar
        # cualquier otra cosa. Protege contra el hilo huerfano que sobrevive a un
        # `join(timeout=...)` vencido (ver `detener()` y `_trabajar()`).
        self._generacion = 0
        self._escritas = 0
        self._repetidos = 0

    @property
    def sonando(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    @property
    def pausado(self) -> bool:
        return self._pausado.is_set()

    @property
    def muestras_escritas(self) -> int:
        """Muestras que la salida ACEPTO, no las que se intentaron.

        Una escritura que la tarjeta rechaza (`reproducir()` devuelve False) no
        se cuenta: si contara los intentos, un dispositivo que falla la mitad de
        las escrituras mentiria el doble.
        """
        return self._escritas

    @property
    def cabezales_repetidos(self) -> int:
        """Cuantas veces el cabezal lanzo `BloqueadoAhora` y se repitio el ultimo."""
        return self._repetidos

    def cargar(self, renderizada: PiezaRenderizada) -> None:
        """Pone la pieza que va a sonar. Se aplica en el bloque siguiente.

        Bajo el candado propio, y sustituyendo la referencia entera: el hilo lee
        la pieza UNA vez al empezar cada bloque y despues trabaja con su copia
        local. Asi un cambio que cae en mitad de un bloque no lo deja medio
        viejo y medio nuevo, que es un chasquido donde antes habia musica.
        """
        with self._candado:
            self._renderizada = renderizada

    def ganancia(self, valor: float) -> None:
        """Pide un volumen nuevo. Entra suavizado en el bloque siguiente."""
        with self._candado:
            self._ganancia_pedida = float(valor)

    def iniciar(self, cabezal: Callable[[], float | None]) -> bool:
        """Arranca el hilo con ese cabezal. False si no hay salida de audio.

        `cabezal()` devuelve el instante de la pieza en pulsos, o `None` si ahora
        mismo no hay nada que suene (cuenta atras, pasada terminada, sin pasada).
        Puede lanzar `BloqueadoAhora` si no se puede leer sin esperar.
        """
        if self.sonando:
            return True
        if not self._salida.activa:
            return False
        self._parar.clear()
        self._pausado.clear()
        self._cabezal = cabezal
        self._ultimo_instante = None
        self._escritas = 0
        self._repetidos = 0
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return True

    def pausar(self) -> None:
        """Deja de alimentar la tarjeta sin matar el hilo. Idempotente.

        Con una bandera y no con `detener()` por lo mismo que en `Metronomo`:
        quien lo pide es el hilo de analisis, y `detener()` hace
        `join(timeout=1.0)`; bloquear ahi hasta un segundo cegaria la deteccion
        de ataques. Levantar una bandera no bloquea nada.
        """
        self._pausado.set()

    def reanudar(self) -> None:
        """Vuelve a sonar. Idempotente.

        No hay nada que realinear al volver -al contrario que en `Metronomo`,
        que recoloca su `siguiente`-: el bloque siguiente sale del cabezal, que
        ya sabe donde esta la pasada. Es la ventaja de no llevar reloj.
        """
        self._pausado.clear()

    def _trabajar(self) -> None:
        """El hilo: un bloque cada vez, y cada bloque sale del cabezal.

        Lee su generacion al arrancar y la comprueba, junto con la peticion de
        parada, JUSTO ANTES y JUSTO DESPUES de la escritura bloqueante. El motivo
        es el de `Metronomo._trabajar`: `reproducir()` puede seguir dentro de
        `stream.write()` cuando `detener()` ya se rindio en su
        `join(timeout=1.0)` y devolvio el control. Ese hilo huerfano no debe
        escribir sobre una salida que la sesion ya pudo cerrar, ni contar como
        escrito un bloque que nadie llego a oir.

        El orden de dentro del bucle no es casual: primero la FOTO de lo que se
        puede cambiar en caliente, despues la pregunta al cabezal. La clausura
        del cabezal es ajena y puede hacer cualquier cosa -incluso llamar a
        `cargar()`-, y con la foto tomada antes, ese cambio entra limpio en el
        bloque siguiente en vez de partir este por la mitad.

        Lo que NO hay aqui es un contador de posicion. Si el cabezal contesta dos
        veces el mismo pulso, se escribe dos veces el mismo audio; si salta, el
        audio salta. No hay ningun estado del que el audio pueda derivar.
        """
        generacion = self._generacion
        cabezal = self._cabezal
        while not self._parar.is_set() and self._generacion == generacion:
            if self._pausado.is_set():
                if self._parar.wait(INTERVALO_SONDEO_S):
                    return
                continue
            with self._candado:
                renderizada = self._renderizada
                pedida = self._ganancia_pedida
            instante = self._preguntar(cabezal)
            bloque = self._con_ganancia(self._rodaja(renderizada, instante), pedida)
            if self._parar.is_set() or self._generacion != generacion:
                return
            aceptado = self._salida.reproducir(bloque)
            if self._parar.is_set() or self._generacion != generacion:
                return
            if aceptado:
                self._escritas += bloque.size

    def _preguntar(self, cabezal: Callable[[], float | None] | None) -> float | None:
        """El instante que suena ahora, preguntandolo CADA bloque.

        Si el cabezal no se puede leer sin esperar, se reutiliza el ultimo
        conocido: ver `BloqueadoAhora`. Antes del primer cabezal bueno no hay
        nada que repetir y se devuelve `None`, que es silencio.
        """
        if cabezal is None:
            return None
        try:
            instante = cabezal()
        except BloqueadoAhora:
            self._repetidos += 1
            return self._ultimo_instante
        self._ultimo_instante = instante
        return instante

    def _rodaja(
        self, renderizada: PiezaRenderizada | None, instante: float | None
    ) -> np.ndarray:
        """Las muestras del bloque: la rodaja de la pieza, o silencio.

        `None` escribe silencio y NO para el hilo. Es la cuenta atras, la pasada
        terminada y el «todavia no hay pasada»; parar y arrancar el stream en
        cada una de esas seria un chasquido en cada vuelta del bucle.

        Siempre devuelve `self.bloque` muestras, tambien en los bordes: de eso se
        encarga `PiezaRenderizada.rodaja`, que da silencio en vez de lanzar antes
        del comienzo y despues del final. Un bloque corto es un chasquido.
        """
        if renderizada is None or instante is None:
            return np.zeros(self.bloque, dtype=np.float32)
        return renderizada.rodaja(float(instante), self.bloque)

    def _con_ganancia(self, bloque: np.ndarray, pedida: float) -> np.ndarray:
        """Aplica la ganancia, y un CAMBIO de ganancia como rampa dentro del bloque.

        Multiplicar de golpe mete un salto del tamaño entero del cambio entre dos
        muestras consecutivas, y un escalon asi es un chasquido audible: bajar el
        fondo con un deslizador sonaria a interruptor. La rampa reparte el cambio
        por las 1024 muestras del bloque (21 ms), que no se percibe como tal.

        Trabaja en sitio porque `bloque` siempre es un array recien hecho -lo
        acaba de devolver `rodaja` o `np.zeros`- y nadie mas lo tiene.
        """
        desde = self._ganancia_aplicada
        if desde == pedida:
            if pedida != 1.0:
                bloque *= np.float32(pedida)
            return bloque
        rampa = np.linspace(desde, pedida, bloque.size, dtype=np.float32)
        bloque *= rampa
        self._ganancia_aplicada = pedida
        return bloque

    def detener(self) -> None:
        """Para el hilo. Seguro de llamar varias veces, y sin haber arrancado.

        Incrementa la generacion ANTES de tocar cualquier otra cosa (incluido
        `_parar.set()`), igual que `Metronomo.detener()`. Ese contador es lo que
        protege contra el hilo huerfano que sobrevive a un `join(timeout=1.0)`
        vencido: si `reproducir()` seguia bloqueada dentro de `stream.write()`
        cuando el join expiro, este metodo ya devolvio el control como si el
        fondo estuviera parado, pero el hilo real sigue vivo. Al desbloquearse,
        `_trabajar()` compara su generacion capturada al arrancar con
        `self._generacion` y, como ya no coincide, se retira sin escribir un
        bloque mas, sin contarlo y sin volver a tocar la salida, aunque para
        entonces `SalidaAudio.cerrar()` ya se haya llamado.

        No cierra la salida: la salida es de quien la presto (la sesion), que
        tambien la comparte con el metronomo y los tonos de referencia.
        """
        self._generacion += 1
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
