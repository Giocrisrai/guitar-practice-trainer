import numpy as np
import pytest

from nucleo.analisis.energia import (
    NIVEL_SILENCIO_DBFS,
    UMBRAL_RUIDO_POR_DEFECTO_DBFS,
    hay_senal,
    nivel_dbfs,
)


def senoide(amplitud: float, frecuencia: float = 440.0, muestras: int = 4096) -> np.ndarray:
    t = np.arange(muestras) / 48000.0
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def test_silencio_absoluto_no_devuelve_infinito():
    assert nivel_dbfs(np.zeros(4096, dtype=np.float32)) == NIVEL_SILENCIO_DBFS


def test_senoide_de_amplitud_uno_da_menos_tres_dbfs():
    """El RMS de una senoide de amplitud 1 es 1/sqrt(2), o sea -3,01 dBFS."""
    assert nivel_dbfs(senoide(1.0)) == pytest.approx(-3.01, abs=0.05)


def test_mitad_de_amplitud_baja_seis_decibelios():
    assert nivel_dbfs(senoide(0.5)) == pytest.approx(-9.03, abs=0.05)


def test_el_umbral_por_defecto_es_menos_sesenta():
    """Valor derivado de medir el equipo real: ruido -74,4 dBFS, señal -45 dBFS."""
    assert UMBRAL_RUIDO_POR_DEFECTO_DBFS == -60.0


def test_senal_por_encima_del_umbral_pasa_la_compuerta():
    # -45 dBFS aproximado, el nivel medio medido tocando
    assert hay_senal(senoide(0.008)) is True


def test_piso_de_ruido_medido_no_pasa_la_compuerta():
    # -74 dBFS aproximado, el piso de ruido medido del cable
    generador = np.random.default_rng(1)
    ruido = (generador.normal(0.0, 0.0002, 4096)).astype(np.float32)
    assert hay_senal(ruido) is False


def test_el_umbral_es_ajustable():
    tenue = senoide(0.0005)  # unos -69 dBFS
    assert hay_senal(tenue, umbral_dbfs=-60.0) is False
    assert hay_senal(tenue, umbral_dbfs=-80.0) is True
