import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones

PASO = 0.021


def suena(nota="E2", nivel=-25.0, confianza=0.9, cents=0.0) -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=confianza, nivel_db=nivel,
        nota=nota, cents=cents, posiciones=(),
    )


def silencio() -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
        nota=None, cents=None, posiciones=(),
    )


def correr(detector, cuadros, instante=0.0):
    """Pasa una lista de resultados y devuelve las pulsaciones que salieron."""
    salidas = []
    for resultado in cuadros:
        pulsacion = detector.procesar(resultado, instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO
    return salidas


def test_una_pulsacion_limpia_da_una_sola_salida():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena()] * 12)
    assert len(salidas) == 1
    assert salidas[0].nota == "E2"


def test_la_cola_de_la_nota_no_produce_una_segunda():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(nivel=n) for n in range(-25, -5)])
    assert len(salidas) == 1


def test_un_ataque_sin_nota_creible_no_produce_nada():
    """Regla 1: un golpe en la caja o una cuerda apagada no es un intento."""
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(confianza=0.2)] * 12)
    assert salidas == []


def test_tras_un_hueco_la_misma_nota_vuelve_a_contar():
    detector = DetectorPulsaciones()
    cuadros = [silencio()] * 6 + [suena()] * 10 + [silencio()] * 6 + [suena()] * 10
    assert len(correr(detector, cuadros)) == 2


def test_la_pulsacion_trae_los_cents_de_lo_que_sono():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(cents=-14.0)] * 12)
    assert salidas[0].cents == pytest.approx(-14.0)


def test_el_instante_es_el_del_ataque_no_el_de_la_lectura():
    """El ataque de energia marca cuando empezo la nota; la lectura del tono llega
    despues. Anotar la lectura convertiria el retraso del detector en desfase del
    alumno."""
    detector = DetectorPulsaciones()
    instante = 0.0
    for _ in range(6):
        detector.procesar(silencio(), instante)
        instante += PASO
    inicio = instante
    salidas = []
    for _ in range(12):
        pulsacion = detector.procesar(suena(), instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO
    assert salidas[0].instante == pytest.approx(inicio, abs=PASO)


def test_senal_de_nota_nueva_distingue_la_cola_de_un_intento():
    """Lo que la regla de la ayuda por tiempo necesita: senal creible que NO sea
    la nota que se acaba de resolver."""
    detector = DetectorPulsaciones()
    correr(detector, [silencio()] * 6 + [suena()] * 12)
    detector.procesar(suena(), 1.0)          # cola de la misma nota
    assert detector.senal_de_nota_nueva is False
    detector.procesar(suena(nota="A2"), 1.1)  # otra nota: eso si es un intento
    assert detector.senal_de_nota_nueva is True
