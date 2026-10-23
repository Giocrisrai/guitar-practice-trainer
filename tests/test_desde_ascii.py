import pytest

from nucleo.afinaciones import PERFILES
from nucleo.piezas.desde_ascii import pieza_desde_ascii

ESTANDAR = """\
e|---------------|
B|---------------|
G|---------------|
D|---------------|
A|---------------|
E|--0---2---3----|
"""


def test_las_seis_lineas_dan_cuerda_y_traste():
    pieza = pieza_desde_ascii(ESTANDAR)
    assert [(n.cuerda, n.traste) for n in pieza.notas] == [(6, 0), (6, 2), (6, 3)]


def test_la_sexta_cuerda_es_la_linea_de_abajo():
    """La convencion de la tablatura, al reves de como se leen las listas."""
    texto = "e|--3--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-----|\n"
    assert pieza_desde_ascii(texto).notas[0].cuerda == 1


def test_la_pieza_sale_marcada_como_de_ritmo_aproximado():
    """Fingir que una tablatura de foro trae ritmo seria mentir."""
    assert pieza_desde_ascii(ESTANDAR).ritmo_aproximado is True


def test_un_traste_de_dos_digitos_se_lee_entero():
    texto = "e|-----|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-12--|\n"
    assert pieza_desde_ascii(texto).notas[0].traste == 12


def test_lineas_de_distinta_longitud_se_rechazan_nombrando_la_linea():
    """Review Focus 5: es el sintoma de una tablatura copiada a medias."""
    texto = "e|--3--|\nB|--3-|\nG|--3--|\nD|--3--|\nA|--3--|\nE|--3--|\n"
    with pytest.raises(ValueError, match="linea 2 "):
        pieza_desde_ascii(texto)


def test_un_texto_que_no_es_una_tablatura_se_rechaza():
    with pytest.raises(ValueError):
        pieza_desde_ascii("Esto es la letra de la cancion, no una tablatura")


def test_dos_numeros_en_la_misma_columna_son_un_acorde():
    texto = "e|-----|\nB|-----|\nG|--0--|\nD|--2--|\nA|--2--|\nE|--0--|\n"
    pieza = pieza_desde_ascii(texto)
    assert len(pieza.notas) == 4
    assert len({n.inicio_pulsos for n in pieza.notas}) == 1


def test_el_tempo_se_recibe_porque_el_texto_no_lo_trae():
    assert pieza_desde_ascii(ESTANDAR, tempo=120).tempo == 120


# --- Pruebas que las once anteriores no podian hacer fallar ---------------------


def _tab(linea_de_abajo: str, ancho: int | None = None) -> str:
    """Seis lineas vacias salvo la de abajo."""
    ancho = ancho or len(linea_de_abajo)
    vacia = "-" * ancho
    return "\n".join(
        [f"e|{vacia}|", f"B|{vacia}|", f"G|{vacia}|", f"D|{vacia}|", f"A|{vacia}|"]
        + [f"E|{linea_de_abajo}|"]
    )


def test_las_duraciones_siguen_la_distancia_y_la_mas_corta_es_una_negra():
    """Distancias 2 y 6 columnas: 1 y 3 pulsos. Mata una duracion constante, una
    unidad fija (una columna = un pulso) y una unidad que no sea la distancia minima."""
    pieza = pieza_desde_ascii(_tab("0-2-----3--"))
    assert [n.inicio_pulsos for n in pieza.notas] == pytest.approx([0, 1, 4])
    assert [n.duracion_pulsos for n in pieza.notas] == pytest.approx([1, 3, 1])


def test_la_barra_de_compas_no_estira_la_distancia():
    """La barra es una columna en todas las lineas y no es tiempo. Mata no quitarla:
    con ella la distancia entre el 2 y el 3 seria 3 columnas y no 2."""
    texto = (
        "e|-----|-----|\nB|-----|-----|\nG|-----|-----|\n"
        "D|-----|-----|\nA|-----|-----|\nE|0-2--|3----|\n"
    )
    pieza = pieza_desde_ascii(texto)
    assert [n.inicio_pulsos for n in pieza.notas] == pytest.approx([0, 1, 2.5])


def test_la_linea_de_abajo_tiene_el_midi_mas_grave():
    """Mata invertir el orden de las lineas: se mira el MIDI, no solo el numero."""
    arriba = "e|--3--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-----|\n"
    abajo = "e|-----|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|--3--|\n"
    assert pieza_desde_ascii(arriba).notas[0].midi == 64 + 3
    assert pieza_desde_ascii(abajo).notas[0].midi == 40 + 3


def test_cuatro_lineas_son_el_bajo_de_fabrica():
    """Mata el default de 6 cuerdas: el perfil tiene que ser bajo_4 y los MIDI de bajo."""
    texto = "G|--5--|\nD|-----|\nA|-----|\nE|--0--|\n"
    pieza = pieza_desde_ascii(texto)
    assert pieza.perfil == "bajo_4"
    assert [(n.cuerda, n.midi) for n in pieza.notas] == [(4, 28), (1, 43 + 5)]


def test_las_letras_de_las_cuerdas_construyen_el_perfil():
    """Una Drop D no es la estandar: mata ignorar las letras."""
    texto = "e|--0--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nD|--0--|\n"
    pieza = pieza_desde_ascii(texto)
    assert pieza.perfil == "guitarra_drop_d"
    assert max(pieza.notas, key=lambda n: n.cuerda).midi == 38


def test_una_afinacion_rara_se_da_de_alta_y_conserva_su_octava():
    """Todas medio tono abajo: no es de fabrica, se registra y los MIDI bajan uno.
    Mata usar siempre la estandar y mata una octava mal deducida."""
    texto = (
        "Eb|--0--|\nBb|-----|\nGb|-----|\nDb|-----|\nAb|-----|\nEb|--0--|\n"
    )
    pieza = pieza_desde_ascii(texto)
    assert pieza.perfil not in ("guitarra_estandar", "guitarra_drop_d")
    assert pieza.perfil in PERFILES
    assert sorted(n.midi for n in pieza.notas) == [39, 63]


def test_sin_letras_se_supone_la_afinacion_estandar():
    texto = "|--3--|\n|-----|\n|-----|\n|-----|\n|-----|\n|--0--|\n"
    pieza = pieza_desde_ascii(texto)
    assert pieza.perfil == "guitarra_estandar"
    assert sorted(n.midi for n in pieza.notas) == [40, 67]


def test_siete_lineas_son_una_guitarra_de_siete_y_la_grave_es_un_si():
    texto = "\n".join("x|--0--|" for _ in range(7)) + "\n"
    pieza = pieza_desde_ascii(texto)
    assert len(PERFILES[pieza.perfil].cuerdas) == 7
    assert min(n.midi for n in pieza.notas) == 35


def test_perfil_clave_manda_y_debe_tener_las_cuerdas_de_las_lineas():
    drop_d = "e|--0--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|--0--|\n"
    pieza = pieza_desde_ascii(drop_d, perfil_clave="guitarra_drop_d")
    assert pieza.perfil == "guitarra_drop_d"
    with pytest.raises(ValueError, match="cuerdas"):
        pieza_desde_ascii(drop_d, perfil_clave="bajo_4")


def test_se_nombra_la_linea_malformada_aunque_sea_la_primera():
    """Mata culpar siempre a la linea que no es la primera."""
    texto = "e|--3-|\nB|--3--|\nG|--3--|\nD|--3--|\nA|--3--|\nE|--3--|\n"
    with pytest.raises(ValueError, match="linea 1 "):
        pieza_desde_ascii(texto)


def test_el_numero_de_linea_es_el_del_texto_no_el_del_bloque():
    texto = "Intro\n\n" + "e|--3--|\nB|--3-|\nG|--3--|\nD|--3--|\nA|--3--|\nE|--3--|\n"
    with pytest.raises(ValueError, match="linea 4 "):
        pieza_desde_ascii(texto)


def test_dos_sistemas_se_leen_uno_a_continuacion_del_otro():
    """Mata leer solo el primer bloque, y mata reiniciar el reloj en el segundo."""
    uno = _tab("0-2-")
    dos = _tab("3-5-")
    pieza = pieza_desde_ascii(uno + "\n\n" + dos)
    assert [n.traste for n in pieza.notas] == [0, 2, 3, 5]
    assert [n.inicio_pulsos for n in pieza.notas] == pytest.approx([0, 1, 2, 3])


def test_un_acorde_dura_hasta_el_siguiente_ataque_y_va_con_la_grave_primero_y_el_resto_en_orden():
    texto = (
        "e|--0----|\nB|-------|\nG|--0--5-|\nD|-------|\nA|-------|\nE|-------|\n"
    )
    pieza = pieza_desde_ascii(texto)
    assert [(n.cuerda, n.inicio_pulsos, n.duracion_pulsos) for n in pieza.notas] == [
        (3, 0, 1),
        (1, 0, 1),
        (3, 1, 1),
    ]


def test_una_tablatura_sin_numeros_se_rechaza():
    with pytest.raises(ValueError, match="ninguna nota"):
        pieza_desde_ascii(_tab("-----"))


def test_un_numero_de_lineas_no_soportado_se_rechaza():
    with pytest.raises(ValueError, match="3 lineas"):
        pieza_desde_ascii("e|--0--|\nB|--0--|\nG|--0--|\n")


def test_las_letras_en_minuscula_son_la_estandar_y_la_b_es_un_si():
    """e|b|g|d|a|e es como se escribe en los foros: la 'b' sola es SI, no si bemol.
    Mata leer la 'b' como bemol (la segunda cuerda saldria un semitono baja)."""
    texto = "\n".join(f"{c}|--0--|" for c in "ebgdae") + "\n"
    pieza = pieza_desde_ascii(texto)
    assert pieza.perfil == "guitarra_estandar"
    assert [n.midi for n in pieza.notas] == [40, 45, 50, 55, 59, 64]


def test_un_acorde_va_con_la_grave_primero_como_en_los_demas_lectores():
    """El seguimiento senala la ultima nota de un acorde: tiene que ser la aguda.
    Mata ordenar de arriba abajo."""
    texto = "\n".join(f"{c}|--0--|" for c in "eBGDAE") + "\n"
    pieza = pieza_desde_ascii(texto)
    assert [n.cuerda for n in pieza.notas] == [6, 5, 4, 3, 2, 1]
    assert [n.midi for n in pieza.notas] == sorted(n.midi for n in pieza.notas)


def test_una_linea_de_guiones_entre_sistemas_es_un_separador():
    """Mata tomarla por una cuerda vacia: daria 7 lineas y un mensaje enganoso."""
    texto = _tab("0-2-") + "\n-----------\n" + _tab("3-5-")
    assert [n.traste for n in pieza_desde_ascii(texto).notas] == [0, 2, 3, 5]
