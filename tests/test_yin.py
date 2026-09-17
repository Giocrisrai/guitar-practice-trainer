# tests/test_yin.py
import numpy as np
import pytest

from nucleo.analisis.registro import ResultadoTono, nombres_disponibles, obtener, registrar
from nucleo.analisis.yin import detectar_yin

FS = 48000
F_MIN = 70.0
F_MAX = 1400.0


def senoide(frecuencia: float, muestras: int = 4096, amplitud: float = 0.3) -> np.ndarray:
    t = np.arange(muestras) / FS
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def cuerda_pulsada(fundamental: float, muestras: int = 4096) -> np.ndarray:
    """Imita una cuerda real: fundamental más armónicos decrecientes."""
    t = np.arange(muestras) / FS
    señal = np.zeros(muestras)
    for armonico, peso in enumerate([1.0, 0.6, 0.4, 0.25, 0.15], start=1):
        señal += peso * np.sin(2 * np.pi * fundamental * armonico * t)
    return (0.3 * señal / np.max(np.abs(señal))).astype(np.float32)


def cents_de_error(medida: float, real: float) -> float:
    return abs(1200.0 * np.log2(medida / real))


@pytest.mark.parametrize(
    "frecuencia", [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
)
def test_detecta_cada_cuerda_al_aire_con_menos_de_un_cent_de_error(frecuencia):
    resultado = detectar_yin(senoide(frecuencia), FS, F_MIN, F_MAX)
    assert cents_de_error(resultado.frecuencia, frecuencia) < 1.0


def test_detecta_la_fundamental_y_no_el_segundo_armonico():
    """El error clásico de un detector de tono: oír 164 Hz donde hay un E2 de 82."""
    resultado = detectar_yin(cuerda_pulsada(82.41), FS, F_MIN, F_MAX)
    assert cents_de_error(resultado.frecuencia, 82.41) < 5.0


def test_una_nota_limpia_tiene_confianza_alta():
    resultado = detectar_yin(senoide(196.0), FS, F_MIN, F_MAX)
    assert resultado.confianza > 0.9


def test_el_ruido_blanco_tiene_confianza_baja():
    """No basta con devolver algo: hay que poder saber que no vale nada."""
    generador = np.random.default_rng(7)
    ruido = generador.normal(0.0, 0.3, 4096).astype(np.float32)
    resultado = detectar_yin(ruido, FS, F_MIN, F_MAX)
    assert resultado.confianza < 0.5


def test_no_devuelve_frecuencias_fuera_del_rango_pedido():
    resultado = detectar_yin(senoide(300.0), FS, 200.0, 400.0)
    assert 200.0 <= resultado.frecuencia <= 400.0


def test_detecta_un_si0_de_bajo_con_la_ventana_larga():
    """30,87 Hz necesita 8192 muestras; con 4096 no hay periodos suficientes."""
    resultado = detectar_yin(senoide(30.87, muestras=8192), FS, 28.0, 400.0)
    assert cents_de_error(resultado.frecuencia, 30.87) < 2.0


def test_desviacion_de_veinte_cents_se_detecta_como_tal():
    real = 110.0 * 2 ** (20.0 / 1200.0)
    resultado = detectar_yin(senoide(real), FS, F_MIN, F_MAX)
    assert cents_de_error(resultado.frecuencia, real) < 1.0


def test_el_detector_yin_esta_registrado():
    assert "yin" in nombres_disponibles()
    assert obtener("yin") is detectar_yin


def test_se_puede_registrar_otro_detector():
    """La etapa 2 enchufará aquí un detector de acordes sin tocar el núcleo."""

    def detector_falso(muestras, frecuencia_muestreo, frecuencia_minima, frecuencia_maxima):
        return ResultadoTono(frecuencia=440.0, confianza=1.0)

    registrar("falso", detector_falso)
    assert obtener("falso") is detector_falso
    assert "falso" in nombres_disponibles()


def test_pedir_un_detector_inexistente_es_un_error_claro():
    with pytest.raises(KeyError, match="inexistente"):
        obtener("inexistente")
