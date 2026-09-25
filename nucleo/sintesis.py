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
        """Cierra el stream. Seguro de llamar varias veces."""
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None


class Metronomo:
    """Emite un click por pulso en un hilo aparte."""

    def __init__(self, tempo: int, compas: int = 4, salida: SalidaAudio | None = None) -> None:
        if tempo < 1:
            raise ValueError("El tempo debe ser al menos 1 pulso por minuto")
        self.tempo = tempo
        self.compas = compas
        self._salida = salida or SalidaAudio()
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._pulsos = 0
        self._click_normal = click(self._salida.frecuencia_muestreo)
        self._click_acentuado = click(self._salida.frecuencia_muestreo, acentuado=True)

    @property
    def sonando(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    @property
    def pulsos_emitidos(self) -> int:
        return self._pulsos

    def iniciar(self) -> bool:
        """Arranca el metronomo. Devuelve False si no hay salida de audio."""
        if self.sonando:
            return True
        if not self._salida.activa:
            return False
        self._parar.clear()
        self._pulsos = 0
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return True

    def _trabajar(self) -> None:
        """Hilo del metronomo: un click cada 60/tempo segundos."""
        intervalo = 60.0 / self.tempo
        siguiente = time.monotonic()
        while not self._parar.is_set():
            acentuado = self._pulsos % self.compas == 0
            self._salida.reproducir(self._click_acentuado if acentuado else self._click_normal)
            self._pulsos += 1
            siguiente += intervalo
            espera = max(0.0, siguiente - time.monotonic())
            if self._parar.wait(espera):
                return

    def detener(self) -> None:
        """Para el metronomo. Seguro de llamar varias veces."""
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
