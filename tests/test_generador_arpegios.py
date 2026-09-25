import pytest

from nucleo.ejercicios.generadores.arpegios import generar_arpegio
from nucleo.ejercicios.teoria import ACORDES, clases_del_patron

DO3 = 48


def test_el_arpegio_mayor_solo_usa_fundamental_tercera_y_quinta():
    ejercicio = generar_arpegio(raiz_midi=DO3, tipo="mayor", traste_minimo=0, traste_maximo=5)
    clases = clases_del_patron(DO3, ACORDES["mayor"])
    assert all(n.midi % 12 in clases for n in ejercicio.notas)
    assert {n.midi % 12 for n in ejercicio.notas} <= {0, 4, 7}


def test_el_arpegio_menor_baja_la_tercera():
    menor = generar_arpegio(raiz_midi=DO3, tipo="menor", traste_minimo=0, traste_maximo=5)
    assert 3 in {n.midi % 12 for n in menor.notas}
    assert 4 not in {n.midi % 12 for n in menor.notas}


def test_la_septima_anade_una_nota_mas_al_repertorio():
    triada = generar_arpegio(tipo="mayor", direccion="ascendente", traste_maximo=7)
    septima = generar_arpegio(tipo="septima", direccion="ascendente", traste_maximo=7)
    assert len({n.midi % 12 for n in septima.notas}) > len({n.midi % 12 for n in triada.notas})


def test_el_arpegio_tiene_menos_notas_que_la_escala_en_el_mismo_rango():
    from nucleo.ejercicios.generadores.escalas import generar_escala

    escala = generar_escala(direccion="ascendente", traste_maximo=5)
    arpegio = generar_arpegio(direccion="ascendente", traste_maximo=5)
    assert len(arpegio.notas) < len(escala.notas)


def test_ambas_direcciones_no_repite_la_cumbre():
    ascendente = generar_arpegio(direccion="ascendente", traste_maximo=5)
    ambas = generar_arpegio(direccion="ambas", traste_maximo=5)
    assert len(ambas.notas) == 2 * len(ascendente.notas) - 1


def test_un_acorde_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="acorde"):
        generar_arpegio(tipo="disminuido_septima_alterado")


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_arpegio(perfil_clave="ukelele")


def test_un_rango_sin_notas_del_acorde_se_rechaza_al_generar():
    with pytest.raises(ValueError, match="ninguna nota"):
        generar_arpegio(traste_minimo=30, traste_maximo=30)


def test_cada_nota_trae_sus_posiciones():
    ejercicio = generar_arpegio(traste_maximo=5)
    assert all(len(n.posiciones) >= 1 for n in ejercicio.notas)


def test_el_nombre_menciona_el_acorde():
    ejercicio = generar_arpegio(raiz_midi=DO3, tipo="menor_septima", traste_maximo=7)
    assert "menor" in ejercicio.nombre.lower()
