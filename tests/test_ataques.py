# tests/test_ataques.py
import pytest

from nucleo.ejercicios import ataques as _modulo_ataques
from nucleo.ejercicios.ataques import (
    REFRACTARIO_S,
    SALTO_ATAQUE_DB,
    Ataque,
    DetectorAtaques,
    nombres_disponibles,
    obtener_detector,
    registrar_detector,
)

PASO = 0.021  # el intervalo de analisis de la sesion, en segundos


@pytest.fixture(autouse=True)
def _restaurar_registro_global():
    """Evita que un detector de prueba (p. ej. "falso") contamine el resto de la sesión."""
    original = dict(_modulo_ataques._DETECTORES)
    yield
    _modulo_ataques._DETECTORES.clear()
    _modulo_ataques._DETECTORES.update(original)


def alimentar(detector: DetectorAtaques, niveles: list[float], paso: float = PASO) -> list[Ataque]:
    """Pasa una secuencia de niveles al detector y devuelve los ataques marcados."""
    ataques = []
    for indice, nivel in enumerate(niveles):
        ataque = detector.procesar(nivel, indice * paso)
        if ataque is not None:
            ataques.append(ataque)
    return ataques


def test_los_valores_por_defecto_son_los_de_la_spec():
    assert SALTO_ATAQUE_DB == 6.0
    assert REFRACTARIO_S == 0.050


def test_el_silencio_no_produce_ataques():
    """Sin suelo, el primer cuadro de ruido ya marcaria ataque contra los -120 dBFS."""
    assert alimentar(DetectorAtaques(), [-95.0] * 20) == []


def test_una_nota_sostenida_es_un_solo_ataque():
    """Sesenta resultados diciendo Do son UNA nota, no sesenta."""
    niveles = [-95.0] * 5 + [-30.0] * 40
    assert len(alimentar(DetectorAtaques(), niveles)) == 1


def test_dos_pulsaciones_separadas_son_dos_ataques():
    niveles = [-95.0] * 5 + [-30.0] * 20 + [-95.0] * 10 + [-30.0] * 20
    assert len(alimentar(DetectorAtaques(), niveles)) == 2


def test_una_nota_repetida_sin_silencio_intermedio_tambien_son_dos():
    """El decaimiento natural basta para que la siguiente pulsacion destaque."""
    niveles = [-95.0] * 5 + [-30.0, -34.0, -40.0, -46.0, -52.0] + [-30.0] * 10
    assert len(alimentar(DetectorAtaques(), niveles)) == 2


def test_el_decaimiento_lento_no_marca_ataques():
    """Una nota que se apaga no empieza otra vez."""
    niveles = [-95.0] * 5 + [-30.0 - i * 1.5 for i in range(30)]
    assert len(alimentar(DetectorAtaques(), niveles)) == 1


def test_el_refractario_impide_el_doble_disparo_del_transitorio():
    """Sin tiempo muerto, una sola pulsacion marcaria dos o tres ataques."""
    # Sube, baja y vuelve a subir en menos de 50 ms (tres pasos de 21 ms son 63,
    # asi que se usan pasos de 10 ms para quedar dentro del refractario).
    niveles = [-95.0] * 5 + [-30.0, -45.0, -28.0]
    assert len(alimentar(DetectorAtaques(), niveles, paso=0.010)) == 1


def test_pasado_el_refractario_si_se_admite_un_ataque_nuevo():
    niveles = [-95.0] * 5 + [-30.0, -45.0]
    assert len(alimentar(DetectorAtaques(), niveles, paso=0.060)) == 2


def test_la_primera_nota_se_detecta_sin_historial_previo():
    """Sin historial la referencia es el silencio absoluto, no un hueco."""
    assert len(alimentar(DetectorAtaques(), [-30.0] * 10)) == 1


def test_el_ataque_lleva_su_instante_y_su_nivel():
    ataques = alimentar(DetectorAtaques(), [-95.0] * 5 + [-30.0] * 5)
    assert ataques[0].instante == pytest.approx(5 * PASO)
    assert ataques[0].nivel_db == pytest.approx(-30.0)


def test_un_salto_menor_que_el_umbral_no_cuenta():
    """El primer ataque es el inicio de la senal; la subida de 4 dB no anade otro."""
    niveles = [-40.0] * 10 + [-36.0] * 10  # solo 4 dB de subida
    assert len(alimentar(DetectorAtaques(), niveles)) == 1


def test_el_salto_es_configurable():
    """Con el umbral en 3 dB, esa misma subida de 4 dB si cuenta."""
    niveles = [-40.0] * 10 + [-36.0] * 10
    assert len(alimentar(DetectorAtaques(salto_db=3.0), niveles)) == 2


def test_reiniciar_olvida_el_historial():
    detector = DetectorAtaques()
    alimentar(detector, [-30.0] * 10)
    detector.reiniciar()
    assert len(alimentar(detector, [-30.0] * 10)) == 1


def test_el_detector_de_energia_esta_registrado():
    assert "energia" in nombres_disponibles()
    assert isinstance(obtener_detector("energia")(), DetectorAtaques)


def test_se_puede_registrar_otro_detector():
    """Para enchufar uno espectral sin tocar el evaluador."""
    registrar_detector("falso", lambda: DetectorAtaques(salto_db=99.0))
    assert "falso" in nombres_disponibles()


def test_pedir_un_detector_inexistente_es_un_error_claro():
    with pytest.raises(KeyError, match="inexistente"):
        obtener_detector("inexistente")
