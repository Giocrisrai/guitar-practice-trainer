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

import logging
import threading
from typing import Callable

import numpy as np

from nucleo.acompanamiento import PiezaRenderizada
from nucleo.sintesis import INTERVALO_SONDEO_S, SalidaAudio

_registro = logging.getLogger(__name__)

# Cuantas muestras lleva cada escritura por omision. A 48 kHz son 21,3 ms: lo
# bastante corto para que un salto del cabezal se oiga enseguida y lo bastante
# largo para que el hilo no se pase el dia entrando y saliendo de PortAudio.
BLOQUE_POR_OMISION = 1024

# Cuantos bloques seguidos se puede repetir el ultimo cabezal conocido antes de
# degradar a silencio. Ver `BloqueadoAhora`: cuatro bloques del tamaño por
# omision son 85 ms, lo justo para cubrir un candado que se suelta enseguida y
# demasiado poco para que la repeticion se oiga como un bucle.
REPETICIONES_MAXIMAS = 4


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
    conocido es, para UN bloque, 21 ms que suenan dos veces y no se perciben.

    **Pero la repeticion tiene techo, porque N seguidas no son N veces lo
    mismo.** Si el candado se queda ocupado un segundo, con el bloque por
    omision salen ~47 copias consecutivas del mismo fragmento de 21 ms: eso no
    se oye como musica repetida, se oye como un bucle cerrado, un zumbido
    periodico a ~47 Hz. Y el hilo no se frena por si solo: va tan rapido como la
    tarjeta acepte. Asi que tras `REPETICIONES_MAXIMAS` bloqueos CONSECUTIVOS el
    acompañante deja de repetir y se calla, que es lo menos malo de los tres:
    mejor un hueco que un zumbido que no estaba en la pieza.

    **Callarse es irse, no cortarse.** El modulo entero gasta `_con_ganancia` en
    no meter un escalon entre dos muestras seguidas; saltar a cero de golpe seria
    exactamente ese escalon, y otro igual al volver. Asi que el bloque que pasa
    el techo baja a cero A LO LARGO del bloque con la misma rampa, y cuando el
    cabezal vuelve a contestar, la pieza entra con la rampa simetrica desde el
    silencio. Los bloqueos se cuentan SEGUIDOS: un solo cabezal bueno reinicia
    la cuenta, porque el candado de la sesion se ocupa a rachas y no sin parar.
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
        # La ganancia que de verdad salio en la ultima muestra ESCRITA, y de
        # donde arranca la rampa siguiente. Va bajo el mismo candado que la
        # pedida, y no porque «solo la toque el hilo»: en la ventana del hilo
        # huerfano -el que sobrevive al `join(timeout=1.0)` vencido- puede haber
        # dos hilos pasando por el commit, y el candado es lo que garantiza que
        # la pareja (pedida, aplicada) que el bloque siguiente fotografia sea
        # coherente en vez de media de cada uno.
        self._ganancia_aplicada = 1.0
        self._cabezal: Callable[[], float | None] | None = None
        self._ultimo_instante: float | None = None
        # Bloqueos CONSECUTIVOS del cabezal, para el techo de repeticiones (ver
        # `BloqueadoAhora`). No es un reloj: no avanza solo, no influye en DONDE
        # suena la pieza y un solo cabezal bueno lo pone a cero. Lo unico que
        # decide es si el bloque repite el ultimo instante o escribe silencio.
        self._repeticiones_seguidas = 0
        # Tipos de error del cabezal ya anunciados, para no escribir una linea
        # por bloque. Mismo criterio que `servidor/sesion.py` con los
        # observadores que fallan: a 47 bloques por segundo, un fallo
        # persistente llenaria la terminal.
        self._fallos_cabezal_anunciados: set[str] = set()
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
        """Cuantas veces el cabezal NO dio un instante nuevo.

        Suma los dos modos de fallo, porque la degradacion es la misma: la
        `BloqueadoAhora` esperada (el candado de la sesion estaba ocupado) y
        cualquier otra excepcion de la clausura ajena. Lo que los distingue es el
        registro: la segunda deja una linea de error y la primera no, porque la
        primera es normal y la segunda es un defecto.

        No cuenta lo que haga un hilo huerfano despues de que `detener()` haya
        devuelto el control: ese incremento aterrizaria sobre el contador ya
        reiniciado de la pasada siguiente.
        """
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

        Reinicia lo que es de la pasada -el cabezal, sus contadores, la cuenta de
        repeticiones seguidas- y limpia LAS DOS banderas: sin `_pausado.clear()`,
        un `pausar(); detener(); iniciar()` arrancaria un hilo que dice `sonando`
        True y no alimenta la tarjeta jamas.

        Lo que NO reinicia es `_ganancia_aplicada`, y es a proposito: es una
        propiedad de lo ultimo que salio por el altavoz, no de la pasada.
        Volverla a 1,0 soltaria, con la ganancia en 0,2, un bloque de 21 ms
        rampando desde 1,0 -hasta cinco veces el volumen pedido- en cada
        arranque: el usuario le da a Empezar y recibe un golpe de volumen.
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
        self._repeticiones_seguidas = 0
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

        **Todo lo que el bloque deja escrito en el objeto se APUNTA al final**,
        detras de la segunda comprobacion de generacion: las muestras contadas,
        la ganancia que de verdad salio, el ultimo cabezal bueno y la cuenta de
        repeticiones. Es la otra mitad del contrato del huerfano: el hilo que
        sobrevive al `join(timeout=1.0)` vencido no escribe un bloque mas, y
        tampoco deja huella en los contadores de la pasada siguiente.
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
                desde = self._ganancia_aplicada
            instante, fallo = self._preguntar(cabezal)
            # Pasado el techo de repeticiones la pieza se va a cero, y se va
            # DESVANECIDA: el objetivo de ganancia de este bloque pasa a ser 0,0
            # y la rampa que ya existe hace el resto. Al volver el cabezal, el
            # objetivo vuelve a ser el pedido y la misma rampa la trae de vuelta
            # desde el silencio. No hace falta estado nuevo -ni progreso de
            # desvanecido ni nada que arrastrar entre bloques-: la pareja
            # (`_ganancia_aplicada`, objetivo) ya lo dice todo.
            objetivo = 0.0 if fallo and self._techo_pasado() else pedida
            bloque = self._con_ganancia(self._rodaja(renderizada, instante), desde, objetivo)
            if self._parar.is_set() or self._generacion != generacion:
                return
            aceptado = self._salida.reproducir(bloque)
            if self._parar.is_set() or self._generacion != generacion:
                return
            self._apuntar(instante, fallo, aceptado, bloque.size, objetivo)

    def _preguntar(
        self, cabezal: Callable[[], float | None] | None
    ) -> tuple[float | None, bool]:
        """El instante que suena ahora, preguntandolo CADA bloque.

        Devuelve el instante y si el cabezal FALLO, para que el que apunta el
        resultado del bloque -`_apuntar`, ya pasada la comprobacion de
        generacion- sepa que contar. Aqui no se toca ni un contador: esta
        funcion la ejecuta tambien el hilo huerfano, que todavia no sabe que lo
        es.

        Dos modos de fallo, misma degradacion: reutilizar el ultimo instante
        conocido mientras quede techo (ver `BloqueadoAhora`).

        1. `BloqueadoAhora`: lo esperado, el candado de la sesion ocupado. No se
           registra, porque es normal y pasaria 47 veces por segundo.
        2. Cualquier otra excepcion: un defecto de la clausura ajena, que la
           escribe la Task 5. **No puede matar el hilo**, por lo mismo que una
           escritura fallida no lo mata: quedarse sin fondo degrada la
           experiencia, y el hilo es daemon, asi que nadie se enteraria hasta que
           el usuario notara que la pieza dejo de sonar. Se registra una vez por
           tipo de error.

        Antes del primer cabezal bueno no hay nada que repetir y se devuelve
        `None`, que es silencio.
        """
        if cabezal is None:
            return None, False
        try:
            return cabezal(), False
        except BloqueadoAhora:
            return self._instante_repetido(), True
        except Exception as error:  # el cabezal es codigo ajeno: no nos tumba
            self._anunciar_fallo_cabezal(error)
            return self._instante_repetido(), True

    def _techo_pasado(self) -> bool:
        """Si los bloqueos SEGUIDOS ya llegaron al techo. Compuerta, no reloj.

        Se mira la cuenta ya apuntada, sin tocarla, y un solo cabezal bueno la
        pone a cero (ver `_apuntar`). Esa palabra, «seguidos», es lo que hace
        seguro el techo: el candado de la sesion se ocupa a rachas, y un techo
        que contara bloqueos TOTALES dejaria el fondo mudo para siempre despues
        de cuatro bloqueos sueltos repartidos por la pieza.
        """
        return self._repeticiones_seguidas >= REPETICIONES_MAXIMAS

    def _instante_repetido(self) -> float | None:
        """El ultimo cabezal conocido, o `None` cuando ya ni eso.

        El techo es lo que convierte un bucle cerrado audible en un hueco: ver
        `BloqueadoAhora`. El bloque que lo PASA todavia repite el audio, porque
        es el que se desvanece (`_trabajar` le pone la ganancia objetivo a 0,0);
        de ahi en adelante no hay ya nada que desvanecer y se escribe silencio
        directamente, que ademas se calcula mas barato.
        """
        if self._repeticiones_seguidas > REPETICIONES_MAXIMAS:
            return None
        return self._ultimo_instante

    def _anunciar_fallo_cabezal(self, error: Exception) -> None:
        """Registra el fallo de la clausura la primera vez que se ve ese tipo.

        Se recuerda por tipo de error y no por mensaje, igual que
        `servidor/sesion.py` con los observadores: un error cuyo texto cambia en
        cada bloque escribiria ~47 lineas por segundo y haria crecer el conjunto
        sin cota. El mensaje del primero si se imprime, que es el que sirve para
        diagnosticar.
        """
        clave = type(error).__name__
        if clave in self._fallos_cabezal_anunciados:
            return
        self._fallos_cabezal_anunciados.add(clave)
        _registro.error(
            "El cabezal de la pieza de fondo fallo: %s: %s. Se repite el ultimo "
            "instante conocido y, pasadas %d veces seguidas, se escribe silencio.",
            clave,
            error,
            REPETICIONES_MAXIMAS,
            exc_info=True,
        )

    def _apuntar(
        self,
        instante: float | None,
        fallo: bool,
        aceptado: bool,
        muestras: int,
        objetivo: float,
    ) -> None:
        """Deja apuntado lo que ese bloque dejo hecho. Solo para el hilo vigente.

        Se llama DESPUES de la segunda comprobacion de generacion, y en eso esta
        todo el asunto: nada de lo que un hilo huerfano calcule llega hasta aqui.

        Un cabezal bueno **reinicia** la cuenta de bloqueos seguidos, y ese
        reinicio es lo unico que hace seguro el techo: ver `_techo_pasado`. Un
        `None` del cabezal es un cabezal bueno -quiere decir «ahora no suena
        nada»-, asi que borra el ultimo instante: si lo dejara en pie, un bloqueo
        posterior resucitaria audio de antes de que la pasada terminara.

        `_ganancia_aplicada` toma el objetivo de ESTE bloque (que durante el
        desvanecido es 0,0, no lo que el usuario pidio) y solo si la salida
        ACEPTO el bloque. Darla por avanzada en un bloque que nadie oyo
        -rechazado por la tarjeta- dejaria la rampa consumida y el cambio de
        ganancia entraria como escalon en el siguiente, que es justo el
        chasquido que la rampa existe para evitar.
        """
        if fallo:
            self._repetidos += 1
            self._repeticiones_seguidas += 1
        else:
            self._repeticiones_seguidas = 0
            self._ultimo_instante = instante
        if aceptado:
            with self._candado:
                self._ganancia_aplicada = objetivo
            self._escritas += muestras

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

    def _con_ganancia(self, bloque: np.ndarray, desde: float, pedida: float) -> np.ndarray:
        """Aplica la ganancia, y un CAMBIO de ganancia como rampa dentro del bloque.

        Multiplicar de golpe mete un salto del tamaño entero del cambio entre dos
        muestras consecutivas, y un escalon asi es un chasquido audible: bajar el
        fondo con un deslizador sonaria a interruptor. La rampa reparte el cambio
        por las 1024 muestras del bloque (21 ms), que no se percibe como tal, y
        ocupa el bloque ENTERO: una rampa que se agotara en el primer octavo
        seria ocho veces mas abrupta por el mismo cambio.

        No guarda nada: el que apunta que la ganancia avanzo es `_apuntar`, y
        solo si la salida acepto el bloque. `desde` sale de la foto tomada bajo
        candado, asi que la rampa de un bloque siempre arranca donde acabo la
        anterior QUE SE OYO. Y `pedida` es el objetivo de ESTE bloque, que casi
        siempre es la ganancia que el usuario pidio y durante el desvanecido del
        techo de repeticiones es 0,0: la misma rampa sirve para las dos cosas, y
        por eso apagarse y volver no necesitan ni una linea de estado propia.

        **Trabaja EN SITIO, y eso depende de un modulo ajeno:**
        `PiezaRenderizada.rodaja` (`nucleo/acompanamiento.py`) construye un
        `np.zeros` nuevo en cada llamada y copia dentro, nunca devuelve una vista
        del buffer de la pieza. Si algun dia devolviera una vista, este `*=`
        multiplicaria el buffer CARGADO muestra a muestra, bloque tras bloque y
        de forma acumulativa: la pieza se iria apagando -o reventando- sola, con
        la copia compartida por todas las pasadas y sin nada en este modulo que
        lo delatara. Es la razon, no solo la conclusion: si esa invariante de
        `rodaja` cambia, lo primero que hay que hacer aqui es copiar.
        """
        if desde == pedida:
            if pedida != 1.0:
                bloque *= np.float32(pedida)
            return bloque
        rampa = np.linspace(desde, pedida, bloque.size, dtype=np.float32)
        bloque *= rampa
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
