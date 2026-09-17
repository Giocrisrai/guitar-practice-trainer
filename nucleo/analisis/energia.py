"""Nivel de señal y compuerta de ruido.

Primera puerta del análisis: por debajo del umbral no se calcula nada más. Sin esta
compuerta el detector de tono perseguiría el piso de ruido del cable y la aguja del
afinador no pararía de bailar.
"""

import numpy as np

# El logaritmo de cero es menos infinito; se recorta aquí para que el silencio
# absoluto siga siendo un número con el que se pueda operar y comparar.
NIVEL_SILENCIO_DBFS = -120.0

# Derivado de medir el equipo real: con la guitarra sonando el nivel medio fue
# -45 dBFS y el piso de ruido -74,4 dBFS. El umbral queda centrado en ese hueco.
UMBRAL_RUIDO_POR_DEFECTO_DBFS = -60.0


def nivel_dbfs(muestras: np.ndarray) -> float:
    """Nivel RMS de la ventana en decibelios relativos a escala completa.

        nivel = 20 · log10( sqrt( media(x²) ) )

    Escala completa (amplitud 1,0) equivale a 0 dBFS; todo lo demás es negativo.
    Una senoide de amplitud 1 da -3,01 dBFS porque su RMS es 1/sqrt(2).
    """
    if muestras.size == 0:
        return NIVEL_SILENCIO_DBFS
    rms = float(np.sqrt(np.mean(np.square(muestras, dtype=np.float64))))
    if rms <= 0.0:
        return NIVEL_SILENCIO_DBFS
    return max(20.0 * np.log10(rms), NIVEL_SILENCIO_DBFS)


def hay_senal(
    muestras: np.ndarray, umbral_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS
) -> bool:
    """Verdadero si la ventana supera el umbral y merece ser analizada."""
    return bool(nivel_dbfs(muestras) > umbral_dbfs)
