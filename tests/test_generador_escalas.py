import pytest

from nucleo.afinaciones import PERFILES
from nucleo.ejercicios.generadores.escalas import generar_escala
from nucleo.ejercicios.teoria import ESCALAS, clases_del_patron, notas_alcanzables

DO3 = 48


def test_la_escala_sale_ordenada_de_grave_a_aguda():
    ejercicio = generar_escala(raiz_midi=DO3, tipo="mayor", direccion="ascendente")
    midis = [n.midi for n in ejercicio.notas]
    assert midis == sorted(midis)


def test_todas_las_notas_pertenecen_a_la_escala():
    ejercicio = generar_escala(raiz_midi=DO3, tipo="mayor", traste_minimo=0, traste_maximo=4)
    clases = clases_del_patron(DO3, ESCALAS["mayor"])
    assert all(n.midi % 12 in clases for n in ejercicio.notas)


def test_ninguna_nota_cae_fuera_del_rango_de_trastes():
    ejercicio = generar_escala(traste_minimo=5, traste_maximo=8)
    for nota in ejercicio.notas:
        assert all(5 <= p.traste <= 8 for p in nota.posiciones)


def test_ambas_direcciones_sube_y_baja_sin_repetir_la_cumbre():
    """do re mi fa sol fa mi re do, no ...sol sol..."""
    ascendente = generar_escala(raiz_midi=DO3, direccion="ascendente")
    ambas = generar_escala(raiz_midi=DO3, direccion="ambas")
    assert len(ambas.notas) == 2 * len(ascendente.notas) - 1
    midis = [n.midi for n in ambas.notas]
    assert midis == sorted(midis[: len(ascendente.notas)]) + sorted(
        midis[len(ascendente.notas) :], reverse=True
    )


def test_descendente_es_la_ascendente_al_reves():
    ascendente = generar_escala(raiz_midi=DO3, direccion="ascendente")
    descendente = generar_escala(raiz_midi=DO3, direccion="descendente")
    assert [n.midi for n in descendente.notas] == [n.midi for n in ascendente.notas][::-1]


def test_cada_nota_trae_sus_posiciones_en_el_mastil():
    """Cada nota debe tener exactamente las posiciones que devuelve notas_alcanzables."""
    ejercicio = generar_escala()
    perfil = PERFILES["guitarra_estandar"]
    alcanzables = notas_alcanzables(perfil, traste_minimo=0, traste_maximo=4)

    # Verificar que cada nota tiene exactamente las posiciones esperadas
    for nota in ejercicio.notas:
        assert nota.posiciones == alcanzables[nota.midi]

    # Verificar que al menos una nota tiene más de una posición
    # (con guitarra estándar entre trastes 0 y 4, el Si3 se toca en dos lugares)
    assert any(len(n.posiciones) > 1 for n in ejercicio.notas)


def test_la_pentatonica_tiene_menos_notas_que_la_mayor():
    mayor = generar_escala(tipo="mayor", direccion="ascendente")
    pentatonica = generar_escala(tipo="pentatonica_mayor", direccion="ascendente")
    assert len(pentatonica.notas) < len(mayor.notas)


def test_el_ejercicio_se_describe_de_forma_legible():
    ejercicio = generar_escala(raiz_midi=DO3, tipo="mayor")
    assert "Do" in ejercicio.nombre or "C" in ejercicio.nombre
    assert ejercicio.descripcion


def test_el_tempo_y_el_perfil_viajan_en_el_ejercicio():
    ejercicio = generar_escala(tempo=95, perfil_clave="bajo_4")
    assert ejercicio.tempo == 95
    assert ejercicio.perfil == "bajo_4"


def test_un_tipo_de_escala_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="escala"):
        generar_escala(tipo="inventada")


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_escala(perfil_clave="ukelele")


def test_una_direccion_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="direccion"):
        generar_escala(direccion="en_zigzag")


def test_un_rango_sin_notas_de_la_escala_se_rechaza_al_generar():
    """La spec exige detectar esto al generar, no al tocar."""
    with pytest.raises(ValueError, match="ninguna nota"):
        generar_escala(traste_minimo=30, traste_maximo=30)


def test_el_bajo_genera_su_propia_escala():
    ejercicio = generar_escala(perfil_clave="bajo_5", raiz_midi=31, traste_minimo=0, traste_maximo=5)
    assert len(ejercicio.notas) > 0
    assert ejercicio.perfil == "bajo_5"
