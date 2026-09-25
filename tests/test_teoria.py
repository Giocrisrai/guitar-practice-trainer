import pytest

from nucleo.afinaciones import PERFILES
from nucleo.ejercicios.teoria import (
    ACORDES,
    ESCALAS,
    INTERVALOS,
    clases_del_patron,
    nombre_de_intervalo,
    notas_alcanzables,
    notas_del_patron,
)
from nucleo.musica import Posicion

GUITARRA = PERFILES["guitarra_estandar"]
DO3 = 48  # Do de la tercera octava


def test_la_escala_mayor_tiene_siete_grados():
    assert ESCALAS["mayor"] == (0, 2, 4, 5, 7, 9, 11)


def test_las_pentatonicas_tienen_cinco():
    assert len(ESCALAS["pentatonica_mayor"]) == 5
    assert len(ESCALAS["pentatonica_menor"]) == 5


def test_el_acorde_mayor_es_fundamental_tercera_quinta():
    assert ACORDES["mayor"] == (0, 4, 7)


def test_el_acorde_menor_baja_la_tercera():
    assert ACORDES["menor"] == (0, 3, 7)


def test_transportar_es_sumar_modulo_doce():
    """Sol mayor es Do mayor desplazada siete semitonos."""
    do_mayor = clases_del_patron(DO3, ESCALAS["mayor"])
    sol_mayor = clases_del_patron(DO3 + 7, ESCALAS["mayor"])
    assert do_mayor == frozenset({0, 2, 4, 5, 7, 9, 11})
    assert sol_mayor == frozenset({(c + 7) % 12 for c in do_mayor})


def test_la_octava_de_la_raiz_no_cambia_las_clases():
    """Do3 y Do4 generan exactamente el mismo conjunto de clases."""
    assert clases_del_patron(DO3, ESCALAS["mayor"]) == clases_del_patron(DO3 + 12, ESCALAS["mayor"])


def test_las_notas_del_patron_salen_ordenadas_y_dentro_del_rango():
    notas = notas_del_patron(DO3, ESCALAS["mayor"], midi_minimo=DO3, midi_maximo=DO3 + 12)
    assert notas == (48, 50, 52, 53, 55, 57, 59, 60)
    assert list(notas) == sorted(notas)


def test_un_rango_vacio_no_da_notas():
    assert notas_del_patron(DO3, ESCALAS["mayor"], midi_minimo=60, midi_maximo=48) == ()


def test_el_mastil_alcanza_las_seis_cuerdas_al_aire():
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=0)
    assert sorted(alcanzables) == [40, 45, 50, 55, 59, 64]


def test_una_nota_ambigua_aparece_con_todas_sus_posiciones():
    """El La de 110 Hz es la 5a al aire y la 6a en el traste 5."""
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=5)
    assert Posicion(cuerda=5, traste=0) in alcanzables[45]
    assert Posicion(cuerda=6, traste=5) in alcanzables[45]


def test_las_posiciones_van_de_la_cuerda_mas_grave_a_la_mas_aguda():
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=5)
    cuerdas = [p.cuerda for p in alcanzables[45]]
    assert cuerdas == sorted(cuerdas, reverse=True)


def test_el_rango_de_trastes_se_respeta():
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=5, traste_maximo=8)
    for posiciones in alcanzables.values():
        for posicion in posiciones:
            assert 5 <= posicion.traste <= 8


def test_el_bajo_alcanza_sus_cuatro_cuerdas():
    alcanzables = notas_alcanzables(PERFILES["bajo_4"], traste_minimo=0, traste_maximo=0)
    assert sorted(alcanzables) == [28, 33, 38, 43]


def test_la_escala_en_una_posicion_es_la_interseccion_con_el_mastil():
    """Generar un ejercicio es intersecar el patron con lo que el mastil alcanza."""
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=4)
    clases = clases_del_patron(DO3, ESCALAS["mayor"])
    en_posicion = sorted(m for m in alcanzables if m % 12 in clases)
    assert 40 in en_posicion  # E2 pertenece a Do mayor
    assert 41 in en_posicion  # F2 tambien pertenece a Do mayor
    assert 42 not in en_posicion  # F#2 no pertenece a Do mayor


@pytest.mark.parametrize(
    "nombre, semitonos",
    [("unisono", 0), ("segunda_mayor", 2), ("tercera_mayor", 4), ("quinta_justa", 7), ("octava", 12)],
)
def test_los_intervalos_tienen_los_semitonos_correctos(nombre, semitonos):
    assert INTERVALOS[nombre] == semitonos


def test_el_intervalo_se_nombra_en_castellano():
    assert nombre_de_intervalo(7) == "quinta justa"
    assert nombre_de_intervalo(4) == "tercera mayor"


def test_un_intervalo_mayor_que_una_octava_se_reduce():
    """Una decima mayor suena como una tercera mayor una octava mas arriba."""
    assert nombre_de_intervalo(16) == nombre_de_intervalo(4)
