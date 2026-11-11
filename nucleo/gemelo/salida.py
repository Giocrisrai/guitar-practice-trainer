"""El capturador de salida: el hermano simetrico del cable falso.

`nucleo.gemelo.dispositivo` simula la ENTRADA (lo que el guitarrista toca); este
modulo simula la SALIDA (lo que la pieza de fondo, el metronomo y los tonos de
referencia hacen sonar). Sin el, nada de lo que suena se puede probar ni
demostrar en una maquina sin altavoces.

`SalidaCapturada` construye una `SalidaAudio` DE VERDAD con un stream sustituido,
asi que ejerce su codigo real (candado de escritura, `abrir`/`cerrar`
idempotentes, `ultimo_error`) y no una imitacion. El stream se construye una vez y
la clausura que se lo entrega a `SalidaAudio` lo devuelve SIEMPRE, las veces que
haga falta: igual que el `listar` del cable falso, no se vacia ni se agota (una
clausura que fabricara un stream nuevo en cada llamada perderia lo escrito en
cuanto la salida se reabriera).

Lo guardado se compara en las pruebas contra arrays construidos por la propia
prueba, nunca contra lo que el capturador diga de si mismo.
"""

import threading

import numpy as np

from nucleo.sintesis import FRECUENCIA_MUESTREO_SALIDA, SalidaAudio


class StreamCapturado:
    """Lo que `SalidaAudio` cree que es un stream de salida.

    Imita de `sounddevice.OutputStream` lo que `SalidaAudio` usa: `start`,
    `write`, `stop` y `close`. Copia cada escritura, porque `sounddevice`
    reutiliza sus buffers y quien guarda sin copiar acaba con basura.

    `fallar_en=n` hace que la escritura de indice `n` (empezando en 0) lance
    `OSError`; solo esa, y no queda guardada.
    """

    def __init__(self, fallar_en: int | None = None, **argumentos) -> None:
        self.argumentos = dict(argumentos)
        self._fallar_en = fallar_en
        self._bloques: list[np.ndarray] = []
        self._intentos = 0
        self._candado = threading.Lock()
        self.arranques = 0
        self.paradas = 0
        self.cierres = 0

    @property
    def muestras(self) -> np.ndarray:
        """Todo lo escrito, concatenado y en orden (vacio si no se escribio nada)."""
        with self._candado:
            if not self._bloques:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._bloques)

    @property
    def bloques(self) -> tuple[int, ...]:
        """El numero de cuadros de cada escritura, en orden."""
        with self._candado:
            return tuple(len(bloque) for bloque in self._bloques)

    def start(self) -> None:
        self.arranques += 1

    def write(self, muestras: np.ndarray) -> None:
        with self._candado:
            indice = self._intentos
            self._intentos += 1
            if self._fallar_en is not None and indice == self._fallar_en:
                raise OSError(f"fallo simulado en la escritura {indice}")
            datos = np.array(muestras, dtype=np.float32, copy=True)
            # Mono: un bloque (n, 1) y uno (n,) son lo mismo.
            self._bloques.append(datos.reshape(datos.shape[0], -1)[:, 0])

    def stop(self) -> None:
        self.paradas += 1

    def close(self) -> None:
        self.cierres += 1


class SalidaCapturada:
    """`SalidaAudio` con el stream sustituido, y lo escrito a mano.

    `salida` es la que se le pasa al codigo bajo prueba. `fallar_en` hace fallar
    una escritura (ver `StreamCapturado`); `fallar_al_abrir` simula una maquina
    sin dispositivo: `abrir()` devuelve False y deja el error.
    """

    def __init__(
        self,
        frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA,
        fallar_en: int | None = None,
        fallar_al_abrir: bool = False,
    ) -> None:
        self._stream = StreamCapturado(fallar_en=fallar_en)

        def abrir_stream(**argumentos) -> StreamCapturado:
            if fallar_al_abrir:
                raise OSError("sin dispositivo de audio (simulado)")
            self._stream.argumentos = dict(argumentos)
            return self._stream

        self.salida = SalidaAudio(
            frecuencia_muestreo=frecuencia_muestreo, abrir_stream=abrir_stream
        )

    @property
    def muestras(self) -> np.ndarray:
        """Todo lo escrito, concatenado."""
        return self._stream.muestras

    @property
    def bloques(self) -> tuple[int, ...]:
        """El tamano de cada escritura."""
        return self._stream.bloques

    @property
    def argumentos(self) -> dict:
        """Lo que `SalidaAudio` le pidio al abrir el stream."""
        return self._stream.argumentos

    @property
    def arranques(self) -> int:
        return self._stream.arranques

    @property
    def paradas(self) -> int:
        return self._stream.paradas

    @property
    def cierres(self) -> int:
        return self._stream.cierres

    def abrir(self) -> bool:
        return self.salida.abrir()
