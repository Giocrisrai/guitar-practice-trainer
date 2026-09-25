import pytest

from nucleo.ejercicios.generadores.intervalos import generar_intervalo
from nucleo.ejercicios.teoria import INTERVALOS


def test_cada_nota_lleva_su_referencia_que_sonara_antes():
    ejercicio = generar_intervalo(semilla=1)
    assert all(n.referencia_midi is not None for n in ejercicio.notas)


def test_la_distancia_es_exactamente_el_intervalo_pedido():
    ejercicio = generar_intervalo(intervalo="quinta_justa", semilla=2)
    for nota in ejercicio.notas:
        assert nota.midi - nota.referencia_midi == INTERVALOS["quinta_justa"]


def test_se_generan_tantas_repeticiones_como_se_piden():
    assert len(generar_intervalo(repeticiones=5, semilla=3).notas) == 5


def test_la_misma_semilla_da_el_mismo_ejercicio():
    uno = generar_intervalo(semilla=7)
    otro = generar_intervalo(semilla=7)
    assert [n.midi for n in uno.notas] == [n.midi for n in otro.notas]
    assert [n.referencia_midi for n in uno.notas] == [n.referencia_midi for n in otro.notas]


def test_semillas_distintas_dan_ejercicios_distintos():
    uno = generar_intervalo(semilla=7, repeticiones=12)
    otro = generar_intervalo(semilla=8, repeticiones=12)
    assert [n.midi for n in uno.notas] != [n.midi for n in otro.notas]


def test_la_nota_objetivo_siempre_es_alcanzable_en_el_mastil():
    """No basta con que exista en teoria: hay que poder tocarla en el rango."""
    ejercicio = generar_intervalo(intervalo="octava", traste_minimo=0, traste_maximo=5, semilla=4)
    for nota in ejercicio.notas:
        assert len(nota.posiciones) >= 1
        assert all(0 <= p.traste <= 5 for p in nota.posiciones)


def test_el_nombre_menciona_el_intervalo_en_castellano():
    ejercicio = generar_intervalo(intervalo="tercera_mayor", semilla=5)
    assert "tercera mayor" in ejercicio.nombre.lower()


def test_un_intervalo_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="intervalo"):
        generar_intervalo(intervalo="cuarta_aumentada_disminuida")


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_intervalo(perfil_clave="ukelele")


def test_un_rango_sin_pares_validos_se_rechaza_al_generar():
    """Con un solo traste disponible no cabe ninguna octava."""
    with pytest.raises(ValueError, match="ningun"):
        generar_intervalo(intervalo="octava", traste_minimo=0, traste_maximo=0)


def test_cero_repeticiones_se_rechaza():
    with pytest.raises(ValueError, match="repeticiones"):
        generar_intervalo(repeticiones=0)


def test_nunca_hay_dos_notas_iguales_seguidas():
    """Referencias iguales adyacentes darian objetivos iguales adyacentes, y ese
    ejercicio el evaluador no lo puede terminar.
    """
    for semilla in range(200):
        ejercicio = generar_intervalo(repeticiones=12, semilla=semilla)
        midis = [n.midi for n in ejercicio.notas]
        referencias = [n.referencia_midi for n in ejercicio.notas]
        assert all(a != b for a, b in zip(midis, midis[1:])), f"semilla {semilla}"
        assert all(a != b for a, b in zip(referencias, referencias[1:])), f"semilla {semilla}"


def test_con_un_solo_par_valido_se_deja_pasar_el_duplicado():
    """Con una sola referencia posible la repeticion es inevitable: el generador
    devuelve el ejercicio en vez de girar para siempre en el rechazo.
    """
    ejercicio = generar_intervalo(
        intervalo="tercera_mayor", traste_minimo=2, traste_maximo=2, repeticiones=3, semilla=1
    )
    assert len({n.referencia_midi for n in ejercicio.notas}) == 1
    assert len(ejercicio.notas) == 3
