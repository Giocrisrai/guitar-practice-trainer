import pytest

from nucleo.piezas.modelo import (
    NotaEnPieza,
    Pieza,
    pulsos_a_segundos,
    segundos_a_pulsos,
)


def nota(midi=40, cuerda=6, traste=0, inicio=0.0, duracion=1.0) -> NotaEnPieza:
    return NotaEnPieza(
        midi=midi, cuerda=cuerda, traste=traste,
        inicio_pulsos=inicio, duracion_pulsos=duracion,
    )


def pieza(notas, tempo=60) -> Pieza:
    return Pieza(
        nombre="prueba", perfil="guitarra_estandar", tempo=tempo,
        compas=(4, 4), notas=tuple(notas),
    )


def test_a_60_ppm_un_pulso_es_un_segundo():
    assert pulsos_a_segundos(1.0, 60) == pytest.approx(1.0)
    assert pulsos_a_segundos(4.0, 120) == pytest.approx(2.0)


def test_la_conversion_es_reversible():
    assert segundos_a_pulsos(pulsos_a_segundos(3.5, 90), 90) == pytest.approx(3.5)


def test_un_tempo_imposible_se_rechaza():
    """Un tempo de cero o negativo no convierte nada: dividir por el explotaria
    mucho mas lejos y con un traceback en vez de un mensaje."""
    with pytest.raises(ValueError, match="tempo"):
        pulsos_a_segundos(1.0, 0)


def test_la_duracion_es_la_del_final_de_la_ultima_nota():
    """No la suma de las duraciones: las notas pueden solaparse o dejar huecos."""
    p = pieza([nota(inicio=0.0, duracion=1.0), nota(inicio=3.0, duracion=2.0)])
    assert p.duracion_pulsos == pytest.approx(5.0)
    assert p.duracion_s == pytest.approx(5.0)  # 60 ppm


def test_las_notas_tienen_que_venir_ordenadas():
    """El carril recorre la pieza hacia delante; desordenada lo rompe en silencio."""
    with pytest.raises(ValueError, match="orden"):
        pieza([nota(inicio=2.0), nota(inicio=1.0)])


def test_una_duracion_no_positiva_se_rechaza():
    with pytest.raises(ValueError, match="duracion"):
        pieza([nota(duracion=0.0)])
    with pytest.raises(ValueError, match="duracion"):
        pieza([nota(duracion=-1.0)])


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        Pieza(nombre="x", perfil="ukelele", tempo=60, compas=(4, 4), notas=())


def test_a_dict_publica_todo_lo_que_la_interfaz_necesita():
    p = pieza([nota(midi=45, cuerda=5, traste=0, inicio=0.0, duracion=2.0)])
    d = p.a_dict()
    assert d["tempo"] == 60
    assert d["compas"] == [4, 4]
    assert d["duracion_pulsos"] == pytest.approx(2.0)
    assert d["notas"][0] == {
        "midi": 45, "nombre": "A2", "cuerda": 5, "traste": 0,
        "inicio_pulsos": 0.0, "duracion_pulsos": 2.0,
    }


def test_una_pieza_vacia_dura_cero_y_no_revienta():
    assert pieza([]).duracion_pulsos == 0.0


def test_dos_notas_con_el_mismo_inicio_son_un_acorde_admitido_a_proposito():
    """El modelo no rechaza acordes: los representa y deja que el seguidor
    (que si es monofonico) decida que hacer con ellos."""
    p = pieza([
        nota(midi=40, cuerda=6, inicio=0.0, duracion=1.0),
        nota(midi=45, cuerda=5, inicio=0.0, duracion=3.0),
    ])
    assert p.duracion_pulsos == pytest.approx(3.0)
