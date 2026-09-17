"""Captura de audio desde el dispositivo elegido.

Única parte del proyecto sensible al tiempo real. Regla que no se negocia: el
callback de audio nunca se bloquea. Sin cálculo, sin red, sin asignar memoria, sin
locks que puedan esperar. Copia el bloque al buffer y retorna.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np

NOMBRE_ROCKSMITH = "Rocksmith USB Guitar Adapter"


@dataclass(frozen=True)
class DispositivoAudio:
    """Una entrada de audio del sistema."""

    indice: int
    nombre: str
    canales_entrada: int
    frecuencia_muestreo: float


class BufferCircular:
    """Almacén de muestras de tamaño fijo que sobrescribe lo más antiguo.

    La memoria se reserva una sola vez al construirlo: asignar memoria dentro del
    callback de audio es justo lo que hay que evitar. Cuando se llena, lo viejo se
    pierde, que es el comportamiento correcto para un afinador donde solo importa el
    presente.
    """

    def __init__(self, capacidad: int) -> None:
        if capacidad < 1:
            raise ValueError("La capacidad debe ser positiva")
        self._capacidad = capacidad
        self._datos = np.zeros(capacidad, dtype=np.float32)
        self._posicion = 0
        self._total = 0

    @property
    def total_escrito(self) -> int:
        """Muestras escritas desde el inicio, incluidas las ya sobrescritas."""
        return self._total

    def escribir(self, bloque: np.ndarray) -> None:
        """Copia un bloque al buffer. Llamado desde el callback de audio."""
        n = bloque.size
        if n >= self._capacidad:
            self._datos[:] = bloque[-self._capacidad :]
            self._posicion = 0
        else:
            fin = self._posicion + n
            if fin <= self._capacidad:
                self._datos[self._posicion : fin] = bloque
            else:
                corte = self._capacidad - self._posicion
                self._datos[self._posicion :] = bloque[:corte]
                self._datos[: n - corte] = bloque[corte:]
            self._posicion = fin % self._capacidad
        self._total += n

    def leer_ultimas(self, n: int) -> np.ndarray | None:
        """Copia de las n muestras más recientes, o None si aún no hay tantas."""
        if n > self._capacidad or self._total < n:
            return None
        inicio = (self._posicion - n) % self._capacidad
        if inicio + n <= self._capacidad:
            return self._datos[inicio : inicio + n].copy()
        corte = self._capacidad - inicio
        return np.concatenate((self._datos[inicio:], self._datos[: n - corte]))


def listar_dispositivos_entrada() -> list[DispositivoAudio]:
    """Entradas de audio disponibles en el sistema.

    Devuelve lista vacía si macOS no ha concedido permiso de micrófono: el sistema
    no da error, simplemente no enseña nada. Distinguir ese caso es trabajo del
    diagnóstico.
    """
    import sounddevice

    dispositivos = []
    for indice, info in enumerate(sounddevice.query_devices()):
        if info["max_input_channels"] > 0:
            dispositivos.append(
                DispositivoAudio(
                    indice=indice,
                    nombre=info["name"],
                    canales_entrada=info["max_input_channels"],
                    frecuencia_muestreo=info["default_samplerate"],
                )
            )
    return dispositivos


def buscar_rocksmith(
    dispositivos: list[DispositivoAudio] | None = None,
) -> DispositivoAudio | None:
    """Busca el cable Rocksmith por nombre. None si no está conectado."""
    if dispositivos is None:
        dispositivos = listar_dispositivos_entrada()
    for dispositivo in dispositivos:
        if NOMBRE_ROCKSMITH.lower() in dispositivo.nombre.lower():
            return dispositivo
    return None


def _abrir_stream_real(callback: Callable, **argumentos):
    """Abre un InputStream de sounddevice. Aislado aquí para poder sustituirlo."""
    import sounddevice

    return sounddevice.InputStream(callback=callback, **argumentos)


class CapturaAudio:
    """Hilo de audio que vuelca el dispositivo elegido en un buffer circular.

    abrir_stream permite inyectar un doble en las pruebas y así ejercitar toda la
    clase sin hardware.
    """

    def __init__(
        self,
        indice_dispositivo: int,
        frecuencia_muestreo: int = 48000,
        tamano_bloque: int = 512,
        capacidad_buffer: int = 48000,
        ganancia: float = 1.0,
        abrir_stream: Callable | None = None,
    ) -> None:
        self.indice_dispositivo = indice_dispositivo
        self.frecuencia_muestreo = frecuencia_muestreo
        self.tamano_bloque = tamano_bloque
        self.ganancia = ganancia
        self._buffer = BufferCircular(capacidad_buffer)
        self._abrir_stream = abrir_stream or _abrir_stream_real
        self._stream = None
        self._ultimo_error: str | None = None
        self._desbordes = 0

    @property
    def activa(self) -> bool:
        """Verdadero si el stream está abierto."""
        return self._stream is not None

    @property
    def ultimo_error(self) -> str | None:
        """Texto del último fallo, o None si no ha habido ninguno."""
        return self._ultimo_error

    @property
    def desbordes(self) -> int:
        """Veces que CoreAudio reportó pérdida de muestras."""
        return self._desbordes

    @property
    def latencia_ms(self) -> float:
        """Latencia de entrada reportada por el dispositivo, en milisegundos."""
        if self._stream is None:
            return 0.0
        return float(self._stream.latency) * 1000.0

    @property
    def total_capturado(self) -> int:
        """Muestras capturadas desde el inicio."""
        return self._buffer.total_escrito

    def _callback(self, datos, cuadros, tiempo, estado) -> None:
        """Callback de audio. NO BLOQUEAR: copiar y salir, nada más."""
        if estado:
            self._desbordes += 1
        self._buffer.escribir(datos[:, 0] * self.ganancia)

    def iniciar(self) -> bool:
        """Abre el stream. Devuelve False y guarda el error si no se pudo."""
        if self._stream is not None:
            return True
        try:
            self._stream = self._abrir_stream(
                self._callback,
                device=self.indice_dispositivo,
                channels=1,
                samplerate=self.frecuencia_muestreo,
                blocksize=self.tamano_bloque,
                dtype="float32",
            )
            self._stream.start()
            self._ultimo_error = None
            return True
        except Exception as error:
            self._stream = None
            self._ultimo_error = str(error)
            return False

    def detener(self) -> None:
        """Cierra el stream y libera el dispositivo."""
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

    def leer_ventana(self, n: int) -> np.ndarray | None:
        """Últimas n muestras capturadas, o None si todavía no hay suficientes."""
        return self._buffer.leer_ultimas(n)
