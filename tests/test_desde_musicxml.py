import pytest
from music21 import articulations, note, stream, tempo

from nucleo.piezas.desde_musicxml import pieza_desde_musicxml, pistas_de_musicxml


def partitura(midis_y_duraciones, con_tablatura=False, bpm=100):
    parte = stream.Part()
    parte.partName = "Guitarra"
    parte.append(tempo.MetronomeMark(number=bpm))
    for midi, duracion in midis_y_duraciones:
        n = note.Note(midi)
        n.quarterLength = duracion
        if con_tablatura:
            indicacion = articulations.StringIndication()
            indicacion.number = 6
            traste = articulations.FretIndication()
            traste.number = midi - 40
            n.articulations.extend([indicacion, traste])
        parte.append(n)
    obra = stream.Score()
    obra.append(parte)
    return obra


def escribir(obra, tmp_path, nombre="x.xml"):
    ruta = tmp_path / nombre
    obra.write("musicxml", fp=str(ruta))
    return ruta


def test_el_ritmo_y_las_alturas_salen_del_archivo(tmp_path):
    ruta = escribir(partitura([(40, 1.0), (45, 2.0)]), tmp_path)
    pieza = pieza_desde_musicxml(ruta, 1)
    assert [n.midi for n in pieza.notas] == [40, 45]
    assert [n.duracion_pulsos for n in pieza.notas] == [1.0, 2.0]


def test_si_el_archivo_trae_tablatura_se_respeta(tmp_path):
    """El que la escribio sabia mas que nuestro algoritmo."""
    ruta = escribir(partitura([(45, 1.0)], con_tablatura=True), tmp_path)
    nota = pieza_desde_musicxml(ruta, 1).notas[0]
    assert nota.cuerda == 6 and nota.traste == 5


def test_sin_tablatura_la_pone_el_algoritmo(tmp_path):
    # Con una nota sola, 5/0 y 6/5 empatan; con contexto (45, 47, 48) gana la 5a.
    ruta = escribir(partitura([(45, 1.0), (47, 1.0), (48, 1.0)]), tmp_path)
    nota = pieza_desde_musicxml(ruta, 1).notas[0]
    assert nota.cuerda == 5 and nota.traste == 0


def test_el_tempo_sale_del_archivo(tmp_path):
    ruta = escribir(partitura([(40, 1.0)], bpm=76), tmp_path)
    assert pieza_desde_musicxml(ruta, 1).tempo == 76


def test_un_cambio_de_tempo_se_marca(tmp_path):
    """Review Focus 3."""
    obra = partitura([(40, 1.0), (45, 1.0)], bpm=76)
    obra.parts[0].insert(1.0, tempo.MetronomeMark(number=120))
    ruta = escribir(obra, tmp_path)
    pieza = pieza_desde_musicxml(ruta, 1)
    assert pieza.tempo == 76
    assert pieza.tempo_variable is True


def test_una_nota_ligada_alarga_la_anterior(tmp_path):
    """Review Focus 1, otra vez: una ligadura no es un ataque nuevo."""
    from music21 import tie

    obra = partitura([(40, 1.0), (40, 1.0)])
    obra.parts[0].notes[0].tie = tie.Tie("start")
    obra.parts[0].notes[1].tie = tie.Tie("stop")
    ruta = escribir(obra, tmp_path)
    pieza = pieza_desde_musicxml(ruta, 1)
    assert len(pieza.notas) == 1
    assert pieza.notas[0].duracion_pulsos == pytest.approx(2.0)


def test_las_marcas_de_ensayo_se_importan_como_secciones(tmp_path):
    from music21 import expressions

    obra = partitura([(40, 1.0), (45, 1.0)])
    obra.parts[0].insert(1.0, expressions.RehearsalMark("B"))
    ruta = escribir(obra, tmp_path)
    assert [s.nombre for s in pieza_desde_musicxml(ruta, 1).secciones] == ["B"]


def test_un_archivo_ilegible_se_rechaza_con_mensaje(tmp_path):
    ruta = tmp_path / "roto.xml"
    ruta.write_text("<esto no es musicxml>")
    with pytest.raises(ValueError):
        pistas_de_musicxml(ruta)


def test_una_parte_sin_notas_no_se_puede_usar(tmp_path):
    ruta = escribir(partitura([]), tmp_path)
    assert pistas_de_musicxml(ruta)[0].motivo_no_usable is not None


def test_las_repeticiones_se_expanden(tmp_path):
    from music21 import bar

    obra = partitura([(40, 4.0), (45, 4.0)])
    parte = obra.parts[0].makeMeasures()
    medidas = list(parte.getElementsByClass("Measure"))
    medidas[0].leftBarline = bar.Repeat(direction="start")
    medidas[-1].rightBarline = bar.Repeat(direction="end")
    nueva = type(obra)()
    nueva.append(parte)
    ruta = escribir(nueva, tmp_path)
    pieza = pieza_desde_musicxml(ruta, 1)
    assert [n.midi for n in pieza.notas] == [40, 45, 40, 45]


def test_una_sola_indicacion_no_basta(tmp_path):
    obra = partitura([(45, 1.0), (47, 1.0), (48, 1.0)])
    indicacion = articulations.StringIndication()
    indicacion.number = 6
    obra.parts[0].notes[0].articulations.append(indicacion)
    ruta = escribir(obra, tmp_path)
    nota = pieza_desde_musicxml(ruta, 1).notas[0]
    assert nota.cuerda == 5 and nota.traste == 0


def test_la_tablatura_del_archivo_gana_al_algoritmo(tmp_path):
    """Un 52 en 6/12: el algoritmo nunca lo elegiria (preferiria 4/2 o 5/7)."""
    obra = partitura([(52, 1.0)], con_tablatura=True)
    ruta = escribir(obra, tmp_path)
    nota = pieza_desde_musicxml(ruta, 1).notas[0]
    assert (nota.cuerda, nota.traste) == (6, 12)


def test_una_tablatura_incoherente_con_el_perfil_se_recalcula(tmp_path):
    """6/5 en el archivo, pero en Drop D la 6a da 38 + 5 = 43, no 45."""
    from nucleo.afinaciones import perfil_desde_midis, registrar_perfil

    clave = registrar_perfil(perfil_desde_midis("Drop D", [38, 45, 50, 55, 59, 64]))
    obra = partitura([(45, 1.0), (47, 1.0), (48, 1.0)])
    indicacion = articulations.StringIndication()
    indicacion.number = 6
    traste = articulations.FretIndication()
    traste.number = 5
    obra.parts[0].notes[0].articulations.extend([indicacion, traste])
    ruta = escribir(obra, tmp_path)
    nota = pieza_desde_musicxml(ruta, 1, clave).notas[0]
    assert nota.midi == 45
    assert (nota.cuerda, nota.traste) in {(6, 7), (5, 0)}  # nunca el 6/5 del archivo


def test_una_ligadura_continue_tambien_funde(tmp_path):
    from music21 import tie

    obra = partitura([(40, 1.0), (40, 1.0), (40, 1.0)])
    notas = obra.parts[0].notes
    notas[0].tie = tie.Tie("start")
    notas[1].tie = tie.Tie("continue")
    notas[2].tie = tie.Tie("stop")
    pieza = pieza_desde_musicxml(escribir(obra, tmp_path), 1)
    assert len(pieza.notas) == 1
    assert pieza.notas[0].duracion_pulsos == pytest.approx(3.0)


def test_un_traste_solo_no_basta(tmp_path):
    obra = partitura([(45, 1.0), (47, 1.0), (48, 1.0)])
    traste = articulations.FretIndication()
    traste.number = 5
    obra.parts[0].notes[0].articulations.append(traste)
    nota = pieza_desde_musicxml(escribir(obra, tmp_path), 1).notas[0]
    assert (nota.cuerda, nota.traste) == (5, 0)


def test_una_repeticion_mal_formada_es_un_value_error(tmp_path):
    from music21 import bar

    obra = partitura([(40, 4.0), (45, 4.0)])
    parte = obra.parts[0].makeMeasures()
    medidas = list(parte.getElementsByClass("Measure"))
    medidas[0].leftBarline = bar.Repeat(direction="start")
    medidas[1].leftBarline = bar.Repeat(direction="start")  # dos inicios seguidos
    nueva = stream.Score()
    nueva.append(parte)
    ruta = escribir(nueva, tmp_path)
    with pytest.raises(ValueError, match="repeticiones"):
        pieza_desde_musicxml(ruta, 1)


def test_un_acorde_va_con_la_grave_primero_como_en_los_demas_lectores(tmp_path):
    """El mismo invariante que vigila `tests/test_desde_ascii.py`, aqui.

    `EstadoCarril.indice_actual` señala la ULTIMA nota del acorde
    (`seguimiento._indice_en_curso`), asi que el orden decide que nota resalta el
    carril y cual lleva el aro en la vista escrita: tiene que ser la aguda. El
    invariante es entre los CUATRO lectores y hasta ahora solo lo vigilaba el de
    ASCII, asi que invertir el desempate aqui -el `(t[1], t[0].pitch.midi)` de
    `_crudas`- no rompia ninguna prueba.
    """
    from music21 import chord

    parte = stream.Part()
    parte.partName = "Guitarra"
    parte.append(tempo.MetronomeMark(number=80))
    # El acorde se escribe de la mas aguda a la mas grave: el orden tiene que salir
    # del lector y no del archivo.
    acorde = chord.Chord([64, 59, 55, 52])
    acorde.quarterLength = 2.0
    parte.append(acorde)
    obra = stream.Score()
    obra.append(parte)

    notas = pieza_desde_musicxml(escribir(obra, tmp_path, "acorde.xml"), 1).notas
    assert [n.midi for n in notas] == [52, 55, 59, 64]
