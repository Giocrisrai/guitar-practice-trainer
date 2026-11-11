"""Deteccion de ataques: cuando empieza una nota nueva.

El afinador solo necesita saber QUE nota suena ahora. Un ejercicio necesita saber
CUANDO empieza una nota nueva. Si tocas un Do y lo sostienes dos segundos, el
analizador emite unos sesenta resultados diciendo "Do", y eso es UNA nota. Si
tocas Do, Do, Do repetidos, son TRES, y el analizador dice exactamente lo mismo.
La diferencia no esta en la frecuencia: esta en la energia.
"""

from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from nucleo.analisis.energia import NIVEL_SILENCIO_DBFS, UMBRAL_RUIDO_POR_DEFECTO_DBFS

# Cuanto debe subir el nivel sobre la referencia reciente para contar como ataque.
# Provisional: se calibra con grabaciones reales de la guitarra del usuario.
SALTO_ATAQUE_DB = 6.0

# Tiempo muerto tras un ataque. El transitorio de la pua hace que el nivel suba,
# baje y vuelva a subir en pocos milisegundos; sin esto una sola pulsacion
# marcaria dos o tres ataques y el ejercicio avanzaria solo.
REFRACTARIO_S = 0.050

# Lo MINIMO que espera el detector de pulsaciones tras un ataque antes de poder
# leer la nota. Justo en el ataque la senal es caotica y la frecuencia poco
# fiable.
#
# ES UN SUELO, NO LA ESPERA. Desde la Task 6c, el camino A de
# `DetectorPulsaciones` no lee en el primer cuadro posterior a esta espera: lee
# en el primero posterior EN QUE la nota ya lleva racha estable, y abandona si el
# ataque envejece mas de `VENTANA_ATAQUE_COMO_ONSET_S`. La razon es que estos
# 60 ms no alcanzan a cubrir lo que tarda el pipeline en PUBLICAR la altura nueva
# (85,3 ms de ventana mas 42 ms de suavizador con guitarra estandar), asi que
# leer justo aqui sellaba el ataque con la altura de la nota anterior. Subir este
# numero no era la salida: dependeria del perfil de afinacion, porque la ventana
# lo hace. Esta medido y razonado en el docstring de
# `nucleo/ejercicios/pulsaciones.py`.
ESPERA_ESTABILIZACION_S = 0.060

# Cuantos niveles recientes componen la referencia. El valor esta ACOPLADO al
# refractario y al intervalo de analisis: la mediana de n muestras no refleja el
# nivel nuevo hasta pasadas ceil(n/2)-1 vueltas, y hasta entonces lo unico que
# impide un disparo repetido es el refractario. La condicion es
#
#     (ceil(n/2) - 1) · intervalo_de_analisis < refractario_s
#
# Con n=5, intervalo 21 ms y refractario 50 ms: 2·21 = 42 < 50, correcto y con
# 8 ms de margen. Con n=6 el margen desaparece y una nota sostenida marca un
# ataque falso. Cambiar cualquiera de los tres obliga a revisar los otros dos.
MUESTRAS_REFERENCIA = 5


@dataclass(frozen=True)
class Ataque:
    """El instante en que empieza una nota nueva, y con que nivel."""

    instante: float
    nivel_db: float


class DetectorAtaques:
    """Marca ataques a partir de la subida de energia.

    Mantiene un historial corto de niveles recientes y toma su mediana como
    referencia. Hay ataque cuando el nivel supera esa referencia por mas del
    salto configurado y ha pasado el periodo refractario desde el anterior.

    Se usa mediana y no media por lo mismo que en el suavizado del afinador: un
    valor atipico no debe mover la referencia.

    `muestras_referencia` esta acoplado a `refractario_s` y al intervalo de
    analisis: la mediana solo refleja un nivel nuevo pasadas ceil(n/2)-1 vueltas,
    y ese hueco debe caber dentro del refractario. Ver la constante
    `MUESTRAS_REFERENCIA` para la formula y por que 5 es el maximo a 21 ms.
    """

    def __init__(
        self,
        salto_db: float = SALTO_ATAQUE_DB,
        refractario_s: float = REFRACTARIO_S,
        muestras_referencia: int = MUESTRAS_REFERENCIA,
        nivel_minimo_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS,
    ) -> None:
        self.salto_db = salto_db
        self.refractario_s = refractario_s
        self.nivel_minimo_dbfs = nivel_minimo_dbfs
        self._historial: deque[float] = deque(maxlen=muestras_referencia)
        self._instante_ultimo: float | None = None

    def reiniciar(self) -> None:
        """Olvida el historial y el ultimo ataque. Se llama al empezar un ejercicio."""
        self._historial.clear()
        self._instante_ultimo = None

    def _referencia(self) -> float:
        """Nivel contra el que se compara. Sin historial, el silencio absoluto.

        Tomar el silencio como referencia inicial es lo que hace que la primera
        nota de un ejercicio se detecte, en vez de perderse por no tener con que
        compararse.
        """
        if not self._historial:
            return NIVEL_SILENCIO_DBFS
        return float(np.median(self._historial))

    def procesar(self, nivel_db: float, instante: float) -> Ataque | None:
        """Consume un nivel y devuelve el ataque si lo hay, o None."""
        referencia = self._referencia()
        self._historial.append(nivel_db)

        # Un ataque exige senal real: sin este suelo, el primer cuadro de ruido
        # marcaria ataque al compararse con los -120 dBFS del silencio absoluto.
        if nivel_db <= self.nivel_minimo_dbfs:
            return None
        if nivel_db - referencia < self.salto_db:
            return None
        if (
            self._instante_ultimo is not None
            and instante - self._instante_ultimo < self.refractario_s
        ):
            return None

        self._instante_ultimo = instante
        return Ataque(instante=instante, nivel_db=nivel_db)


_DETECTORES: dict[str, Callable[[], DetectorAtaques]] = {}


def registrar_detector(nombre: str, fabrica: Callable[[], DetectorAtaques]) -> None:
    """Anade un detector al registro, sustituyendo el anterior con ese nombre."""
    _DETECTORES[nombre] = fabrica


def obtener_detector(nombre: str) -> Callable[[], DetectorAtaques]:
    """Devuelve la fabrica de un detector por nombre. Lanza KeyError si no existe."""
    if nombre not in _DETECTORES:
        disponibles = ", ".join(sorted(_DETECTORES)) or "ninguno"
        raise KeyError(f"No existe el detector de ataques '{nombre}'. Disponibles: {disponibles}")
    return _DETECTORES[nombre]


def nombres_disponibles() -> list[str]:
    """Nombres de los detectores registrados, ordenados."""
    return sorted(_DETECTORES)


registrar_detector("energia", DetectorAtaques)
