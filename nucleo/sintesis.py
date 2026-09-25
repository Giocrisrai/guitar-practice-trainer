"""Generacion de sonido: tonos de referencia y click de metronomo.

La etapa 1 solo escuchaba; esta es la primera vez que el software emite. El
sonido sale por los altavoces del Mac y el cable Rocksmith solo capta la
guitarra, asi que el metronomo NO contamina la deteccion: con un microfono habria
que resolver la realimentacion, aqui el problema no existe.
"""

import threading
import time
from typing import Callable

import numpy as np

from nucleo.musica import midi_a_frecuencia

FRECUENCIA_MUESTREO_SALIDA = 48000

# Frecuencias del click. El acentuado marca el primer tiempo del compas.
FRECUENCIA_CLICK = 1000.0
FRECUENCIA_CLICK_ACENTUADO = 1500.0
DURACION_CLICK_S = 0.03


def _envolvente(n: int, frecuencia_muestreo: int, ataque_s: float, caida_s: float) -> np.ndarray:
    """Rampa de entrada y salida para evitar el chasquido de los extremos.

    Una senoide que empieza de golpe salta de cero a su amplitud en una sola
    muestra, y eso se oye como un clic sucio. Cinco milisegundos de subida no se
    perciben como tales pero eliminan el artefacto.
    """
    envolvente = np.ones(n, dtype=np.float64)
    muestras_ataque = min(int(ataque_s * frecuencia_muestreo), n // 2)
    muestras_caida = min(int(caida_s * frecuencia_muestreo), n // 2)
    if muestras_ataque > 0:
        envolvente[:muestras_ataque] = np.linspace(0.0, 1.0, muestras_ataque)
    if muestras_caida > 0:
        envolvente[-muestras_caida:] = np.linspace(1.0, 0.0, muestras_caida)
    return envolvente


def tono(
    frecuencia: float,
    duracion_s: float,
    frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA,
    armonicos: tuple[float, ...] = (1.0, 0.4, 0.2),
    ataque_s: float = 0.005,
    caida_s: float = 0.08,
) -> np.ndarray:
    """Tono con armonicos y envolvente suave.

        x(t) = sum_k  a_k · sin(2π · k · f · t)   por la envolvente

    Los armonicos evitan que suene a pitido de test: una senoide pura es
    desagradable y cuesta identificar su altura.
    """
    n = int(duracion_s * frecuencia_muestreo)
    t = np.arange(n) / frecuencia_muestreo
    onda = np.zeros(n, dtype=np.float64)
    for indice, peso in enumerate(armonicos, start=1):
        onda += peso * np.sin(2 * np.pi * frecuencia * indice * t)
    if np.max(np.abs(onda)) > 0:
        onda /= np.max(np.abs(onda))
    onda *= _envolvente(n, frecuencia_muestreo, ataque_s, caida_s)
    return onda.astype(np.float32)


def tono_de_midi(
    midi: int,
    duracion_s: float = 0.6,
    referencia_a4: float = 440.0,
    **argumentos,
) -> np.ndarray:
    """Tono de una nota MIDI, usando la misma conversion que el resto del nucleo."""
    return tono(midi_a_frecuencia(midi, referencia_a4), duracion_s, **argumentos)


def click(
    frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA, acentuado: bool = False
) -> np.ndarray:
    """Click corto de metronomo. El acentuado, mas agudo, marca el primer tiempo."""
    frecuencia = FRECUENCIA_CLICK_ACENTUADO if acentuado else FRECUENCIA_CLICK
    return tono(
        frecuencia,
        DURACION_CLICK_S,
        frecuencia_muestreo=frecuencia_muestreo,
        armonicos=(1.0,),
        ataque_s=0.001,
        caida_s=0.02,
    )


def _abrir_stream_real(**argumentos):
    """Abre un OutputStream de sounddevice. Aislado para poder sustituirlo."""
    import sounddevice

    return sounddevice.OutputStream(**argumentos)


class SalidaAudio:
    """Salida de audio por los altavoces del sistema.

    Quedarse sin salida degrada la experiencia, no la impide: abrir() devuelve
    False y guarda el error en vez de lanzar, para que el ejercicio pueda seguir
    sin metronomo.
    """

    def __init__(
        self,
        frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA,
        abrir_stream: Callable | None = None,
    ) -> None:
        self.frecuencia_muestreo = frecuencia_muestreo
        self._abrir_stream = abrir_stream or _abrir_stream_real
        self._stream = None
        self._ultimo_error: str | None = None

    @property
    def activa(self) -> bool:
        return self._stream is not None

    @property
    def ultimo_error(self) -> str | None:
        return self._ultimo_error

    def abrir(self) -> bool:
        """Abre el stream de salida. Devuelve False y guarda el error si no se pudo."""
        if self._stream is not None:
            return True
        try:
            self._stream = self._abrir_stream(
                samplerate=self.frecuencia_muestreo, channels=1, dtype="float32"
            )
            self._stream.start()
            self._ultimo_error = None
            return True
        except Exception as error:
            self._stream = None
            self._ultimo_error = str(error)
            return False

    def reproducir(self, muestras: np.ndarray) -> bool:
        """Envia muestras a los altavoces. Devuelve False si no hay salida abierta."""
        if self._stream is None:
            return False
        try:
            self._stream.write(muestras)
            return True
        except Exception as error:
            self._ultimo_error = str(error)
            return False

    def cerrar(self) -> None:
        """Cierra el stream. Seguro de llamar varias veces.

        Toma la referencia en una variable local y pone `self._stream = None`
        ANTES de detener y cerrar esa copia local, no despues. Si el orden fuera
        al reves (detener, cerrar y solo entonces poner None, como antes), un
        `reproducir()` que entrara justo mientras el stream se esta deteniendo o
        cerrando lo veria todavia no nulo e intentaria escribir sobre un stream a
        medio cerrar. Con el orden invertido, cualquier `reproducir()` concurrente
        ve None de inmediato en cuanto `cerrar()` empieza y devuelve False sin
        tocar el objeto.
        """
        stream, self._stream = self._stream, None
        if stream is None:
            return
        stream.stop()
        stream.close()


TEMPO_MAXIMO_PPM = 300

# Cada cuanto vuelve a mirar un hilo que esta esperando algo (una peticion de
# tono, o que se levante la pausa). Corto para que la respuesta se note
# inmediata, largo para no gastar CPU en girar.
INTERVALO_SONDEO_S = 0.01


class ReproductorTonos:
    """Hace sonar notas sueltas sin bloquear a quien las pide.

    Lo necesita el tono de referencia de los ejercicios de intervalo: la spec
    §4.5 y §4.1 piden que el software haga sonar la nota de referencia antes de
    pedir la nota objetivo, y sin eso el ejercicio de intervalos es uno de
    lectura con la respuesta escrita en pantalla.

    Existe como clase con hilo propio porque quien pide el tono es el hilo de
    analisis (es ahi donde se ve que la nota del ejercicio cambio) y
    `SalidaAudio.reproducir()` es BLOQUEANTE: escribir seis decimas de audio
    tarda seis decimas de segundo. El hilo de analisis no puede pararse ese
    tiempo, porque la deteccion de ataques trabaja sobre la evolucion de la
    energia y perder cuadros la ciega. `pedir()` deja la peticion en un buzon y
    vuelve en el acto.

    El buzon tiene UNA sola plaza a proposito: si llega una peticion nueva antes
    de que suene la anterior, la sustituye. Encolarlas haria sonar la referencia
    de una nota que el alumno ya dejo atras.

    Contra el hilo huerfano usa el mismo contador de generacion que `Metronomo`,
    comprobado antes y despues de la escritura bloqueante (ver `_trabajar`).
    """

    def __init__(
        self,
        salida: SalidaAudio | None = None,
        duracion_s: float = 0.6,
    ) -> None:
        self._salida = salida or SalidaAudio()
        self.duracion_s = duracion_s
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._aviso = threading.Event()
        self._candado = threading.Lock()
        self._pendiente: tuple[int, float] | None = None
        self._generacion = 0
        # Las ondas se generan una vez por (nota, referencia): un ejercicio de
        # intervalos repite las mismas pocas referencias muchas veces.
        self._ondas: dict[tuple[int, float], np.ndarray] = {}
        self._sonados = 0

    @property
    def activo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    @property
    def tonos_sonados(self) -> int:
        """Cuantos tonos se han escrito de verdad en la salida."""
        return self._sonados

    def iniciar(self) -> bool:
        """Arranca el hilo. Devuelve False si no hay salida de audio abierta."""
        if self.activo:
            return True
        if not self._salida.activa:
            return False
        self._parar.clear()
        self._aviso.clear()
        with self._candado:
            self._pendiente = None
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return True

    def pedir(self, midi: int, referencia_a4: float = 440.0) -> bool:
        """Pide que suene esa nota. NO bloquea. False si no hay hilo vivo.

        Se puede llamar desde el hilo de analisis sin miedo: lo unico que hace es
        dejar la peticion en el buzon y levantar el aviso.
        """
        if not self.activo:
            return False
        with self._candado:
            self._pendiente = (int(midi), float(referencia_a4))
        self._aviso.set()
        return True

    def _onda(self, midi: int, referencia_a4: float) -> np.ndarray:
        clave = (midi, referencia_a4)
        if clave not in self._ondas:
            self._ondas[clave] = tono_de_midi(
                midi,
                self.duracion_s,
                referencia_a4,
                frecuencia_muestreo=self._salida.frecuencia_muestreo,
            )
        return self._ondas[clave]

    def _trabajar(self) -> None:
        """Hilo del reproductor: espera peticiones y las hace sonar.

        Lee su generacion al arrancar y la comprueba, junto con la peticion de
        parada, JUSTO ANTES y JUSTO DESPUES de la escritura bloqueante. El motivo
        es el mismo que en `Metronomo._trabajar`: `reproducir()` puede seguir
        dentro de `stream.write()` cuando `detener()` ya se rindio en su
        `join(timeout=1.0)` y devolvio el control, y ese hilo huerfano no debe
        escribir sobre una salida que la sesion ya pudo haber cerrado, ni contar
        como sonado un tono que nadie llego a oir.
        """
        generacion = self._generacion
        while not self._parar.is_set() and self._generacion == generacion:
            if not self._aviso.wait(INTERVALO_SONDEO_S):
                continue
            self._aviso.clear()
            with self._candado:
                peticion, self._pendiente = self._pendiente, None
            if peticion is None:
                continue
            if self._parar.is_set() or self._generacion != generacion:
                return
            self._salida.reproducir(self._onda(*peticion))
            if self._parar.is_set() or self._generacion != generacion:
                return
            self._sonados += 1

    def detener(self) -> None:
        """Para el hilo y olvida lo pendiente. Seguro de llamar varias veces.

        Incrementa la generacion ANTES de tocar cualquier otra cosa, por lo mismo
        que `Metronomo.detener()`.
        """
        self._generacion += 1
        self._parar.set()
        self._aviso.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
        with self._candado:
            self._pendiente = None


class Metronomo:
    """Emite un click por pulso en un hilo aparte."""

    def __init__(self, tempo: int, compas: int = 4, salida: SalidaAudio | None = None) -> None:
        if tempo < 1:
            raise ValueError("El tempo debe ser al menos 1 pulso por minuto")
        if tempo > TEMPO_MAXIMO_PPM:
            # Por encima de esto el intervalo entre pulsos (60/tempo) baja de los
            # 30 ms que dura el propio click: la escritura bloqueante se come el
            # intervalo y los clicks salen pegados. 300 ppm es mas de lo que
            # cualquier ejercicio de guitarra necesita.
            raise ValueError(
                f"El tempo no puede superar {TEMPO_MAXIMO_PPM} pulsos por minuto"
            )
        self.tempo = tempo
        self.compas = compas
        self._salida = salida or SalidaAudio()
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._pausado = threading.Event()
        self._pulsos = 0
        # Contador de generacion: detener() lo incrementa antes de tocar
        # cualquier otra cosa. Protege contra el hilo huerfano que sobrevive a un
        # join(timeout=...) vencido (ver detener() y _trabajar()).
        self._generacion = 0
        self._click_normal = click(self._salida.frecuencia_muestreo)
        self._click_acentuado = click(self._salida.frecuencia_muestreo, acentuado=True)

    @property
    def sonando(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    @property
    def pulsos_emitidos(self) -> int:
        return self._pulsos

    @property
    def pausado(self) -> bool:
        return self._pausado.is_set()

    def pausar(self) -> None:
        """Deja de emitir clicks sin matar el hilo. Seguro de llamar varias veces.

        La spec §5 pide que al perder la senal el ejercicio se PAUSE, y un
        metronomo que sigue marcando el compas mientras el cable esta
        desenchufado es justo lo contrario. Se hace con una bandera y no con
        `detener()` porque quien lo pide es el hilo de analisis, y `detener()`
        hace `join(timeout=1.0)`: bloquear ahi hasta un segundo cegaria la
        deteccion de ataques. Levantar una bandera no bloquea nada.
        """
        self._pausado.set()

    def reanudar(self) -> None:
        """Vuelve a emitir. Seguro de llamar varias veces."""
        self._pausado.clear()

    def iniciar(self) -> bool:
        """Arranca el metronomo. Devuelve False si no hay salida de audio."""
        if self.sonando:
            return True
        if not self._salida.activa:
            return False
        self._parar.clear()
        self._pausado.clear()
        self._pulsos = 0
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return True

    def _trabajar(self) -> None:
        """Hilo del metronomo: un click cada 60/tempo segundos.

        Lee su generacion al arrancar. En cada vuelta comprueba, antes de llamar
        a reproducir(), que esa generacion sigue siendo la vigente y que no se
        pidio parar; si cualquiera cambio, sale sin emitir. Vuelve a comprobar
        las dos cosas justo despues de que reproducir() retorne, antes de contar
        el pulso: reproducir() puede quedarse bloqueada dentro de
        SalidaAudio.reproducir() (que a su vez espera a stream.write()) mas
        tiempo del que detener() esta dispuesto a esperar en su join(timeout=1.0).
        Si eso pasa, detener() ya devolvio el control con este hilo todavia vivo
        (huerfano); cuando por fin se desbloquea, esta segunda comprobacion evita
        que cuente ese click como emitido o que de otra vuelta llamando de nuevo a
        reproducir() sobre una salida que la sesion ya pudo haber cerrado.

        Mientras `pausar()` este puesto no emite nada y no cuenta pulsos. Al
        reanudar realinea `siguiente` con el reloj: si lo arrastrara, volveria
        con tantos clicks pegados como pulsos hubieran cabido en la pausa.
        """
        intervalo = 60.0 / self.tempo
        generacion = self._generacion
        siguiente = time.monotonic()
        while not self._parar.is_set() and self._generacion == generacion:
            if self._pausado.is_set():
                if self._parar.wait(INTERVALO_SONDEO_S):
                    return
                siguiente = time.monotonic()
                continue
            acentuado = self._pulsos % self.compas == 0
            self._salida.reproducir(self._click_acentuado if acentuado else self._click_normal)
            if self._parar.is_set() or self._generacion != generacion:
                return
            self._pulsos += 1
            siguiente += intervalo
            espera = max(0.0, siguiente - time.monotonic())
            if self._parar.wait(espera):
                return

    def detener(self) -> None:
        """Para el metronomo. Seguro de llamar varias veces.

        Incrementa la generacion ANTES de tocar cualquier otra cosa (incluido
        `_parar.set()`). Ese contador es lo que protege contra el hilo huerfano
        que sobrevive a un `join(timeout=1.0)` vencido: si `reproducir()` seguia
        bloqueada dentro de `stream.write()` cuando el join expiro, este metodo
        ya devolvio el control como si el metronomo estuviera parado, pero el
        hilo real sigue vivo. Al desbloquearse, `_trabajar()` compara su
        generacion capturada al arrancar con `self._generacion` (ver ahi) y, como
        ya no coincide, se retira sin emitir un click mas ni volver a tocar la
        salida, aunque para entonces `SalidaAudio.cerrar()` ya se haya llamado.
        """
        self._generacion += 1
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
