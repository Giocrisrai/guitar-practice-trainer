import pytest

from nucleo.afinaciones import PERFILES
from nucleo.ejercicios.generadores.lectura import generar_lectura


def test_se_generan_tantas_notas_como_repeticiones():
    assert len(generar_lectura(repeticiones=6, semilla=1).notas) == 6


def test_ninguna_nota_lleva_referencia_sonora():
    """En lectura no suena nada: se nombra la nota y tu la buscas."""
    ejercicio = generar_lectura(semilla=2)
    assert all(n.referencia_midi is None for n in ejercicio.notas)


def test_restringir_la_cuerda_restringe_tambien_las_posiciones():
    """Si pide el Fa# en la quinta cuerda, aceptarlo en otra vacia el ejercicio."""
    ejercicio = generar_lectura(cuerda=5, semilla=3)
    for nota in ejercicio.notas:
        assert all(p.cuerda == 5 for p in nota.posiciones)


def test_sin_restringir_cuerda_se_usan_todas():
    ejercicio = generar_lectura(repeticiones=20, semilla=4)
    cuerdas = {p.cuerda for n in ejercicio.notas for p in n.posiciones}
    assert len(cuerdas) > 1


def test_la_misma_semilla_da_el_mismo_ejercicio():
    uno = generar_lectura(semilla=9)
    otro = generar_lectura(semilla=9)
    assert [n.midi for n in uno.notas] == [n.midi for n in otro.notas]


def test_todas_las_notas_caen_en_el_rango_de_trastes():
    ejercicio = generar_lectura(traste_minimo=3, traste_maximo=7, semilla=5)
    for nota in ejercicio.notas:
        assert all(3 <= p.traste <= 7 for p in nota.posiciones)


def test_el_nombre_menciona_la_cuerda_cuando_se_restringe():
    ejercicio = generar_lectura(cuerda=5, semilla=6)
    assert "5" in ejercicio.nombre


def test_una_cuerda_que_el_perfil_no_tiene_se_rechaza():
    with pytest.raises(ValueError, match="cuerda"):
        generar_lectura(perfil_clave="bajo_4", cuerda=6)


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_lectura(perfil_clave="ukelele")


def test_cero_repeticiones_se_rechaza():
    with pytest.raises(ValueError, match="repeticiones"):
        generar_lectura(repeticiones=0)


def test_el_bajo_tambien_sirve_para_leer():
    ejercicio = generar_lectura(perfil_clave="bajo_4", semilla=7)
    assert ejercicio.perfil == "bajo_4"
    cuerdas_validas = {c.numero for c in PERFILES["bajo_4"].cuerdas}
    for nota in ejercicio.notas:
        assert all(p.cuerda in cuerdas_validas for p in nota.posiciones)


def test_nunca_hay_dos_notas_iguales_seguidas():
    """Una nota repetida adyacente hace el ejercicio imposible de terminar: al
    repicarla el tono sigue siendo creible, asi que el evaluador nunca libera
    `_ultima_nota_resuelta` y esa nota no se puede resolver nunca.
    """
    for semilla in range(200):
        midis = [n.midi for n in generar_lectura(repeticiones=12, semilla=semilla).notas]
        assert all(a != b for a, b in zip(midis, midis[1:])), f"semilla {semilla}"


def test_con_una_sola_nota_alcanzable_se_deja_pasar_el_duplicado():
    """Preferible a colgarse: con un solo traste de una sola cuerda no hay otra
    nota que elegir, y el generador debe devolver el ejercicio igualmente.
    """
    ejercicio = generar_lectura(cuerda=6, traste_minimo=5, traste_maximo=5, repeticiones=4, semilla=1)
    midis = [n.midi for n in ejercicio.notas]
    assert len(set(midis)) == 1
    assert len(midis) == 4
