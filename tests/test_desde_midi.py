import mido
import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.musica import Posicion, posiciones_en_mastil
from nucleo.piezas.digitacion import coste_total, digitar

from nucleo.piezas.desde_midi import pieza_desde_midi, pistas_de_midi

TICKS = 480


def midi_de(notas, tempo_bpm=120, marcadores=(), nombre_pista="Guitarra"):
    """Fabrica un .mid con las notas dadas como (midi, inicio_ticks, duracion_ticks)."""
    archivo = mido.MidiFile(ticks_per_beat=TICKS)
    pista = mido.MidiTrack()
    archivo.tracks.append(pista)
    pista.append(mido.MetaMessage("track_name", name=nombre_pista, time=0))
    pista.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    for titulo, tick in marcadores:
        pista.append(mido.MetaMessage("marker", text=titulo, time=tick))
    # Los tiempos de un archivo MIDI son delta: se pasa a absolutos, se ordena (los
    # fines antes que los inicios en el mismo tick) y se vuelve a delta. Asi dos notas
    # simultaneas -un acorde- no producen un delta negativo.
    eventos = []
    for midi, inicio, duracion in notas:
        eventos.append((inicio, 1, mido.Message("note_on", note=midi)))
        eventos.append((inicio + duracion, 0, mido.Message("note_off", note=midi)))
    reloj = 0
    for tick, _, mensaje in sorted(eventos, key=lambda e: (e[0], e[1])):
        pista.append(mensaje.copy(time=tick - reloj))
        reloj = tick
    return archivo


def test_las_notas_y_el_ritmo_salen_exactos(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS), (45, TICKS, TICKS * 2)]).save(str(ruta))
    pieza = pieza_desde_midi(ruta, 1)
    assert [n.midi for n in pieza.notas] == [40, 45]
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 1.0]
    assert [n.duracion_pulsos for n in pieza.notas] == [1.0, 2.0]


def test_la_digitacion_la_pone_el_algoritmo(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS)]).save(str(ruta))
    nota = pieza_desde_midi(ruta, 1).notas[0]
    assert nota.cuerda == 6 and nota.traste == 0


def test_el_tempo_sale_del_archivo(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS)], tempo_bpm=90).save(str(ruta))
    assert pieza_desde_midi(ruta, 1).tempo == 90


def test_un_cambio_de_tempo_se_marca(tmp_path):
    """Review Focus 3."""
    ruta = tmp_path / "x.mid"
    archivo = midi_de([(40, 0, TICKS), (45, TICKS, TICKS)], tempo_bpm=90)
    archivo.tracks[0].append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(140), time=0))
    archivo.save(str(ruta))
    pieza = pieza_desde_midi(ruta, 1)
    assert pieza.tempo == 90
    assert pieza.tempo_variable is True


def test_los_marcadores_se_importan_como_secciones(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS)], marcadores=[("Intro", 0)]).save(str(ruta))
    assert [s.nombre for s in pieza_desde_midi(ruta, 1).secciones] == ["Intro"]


def test_una_nota_que_no_cabe_en_el_mastil_se_rechaza_nombrandola(tmp_path):
    """Un MIDI de piano trae notas que una guitarra no tiene."""
    ruta = tmp_path / "x.mid"
    midi_de([(20, 0, TICKS)]).save(str(ruta))
    with pytest.raises(ValueError) as error:
        pieza_desde_midi(ruta, 1)
    assert "G#0" in str(error.value) or "20" in str(error.value)


def test_una_pista_sin_notas_no_se_puede_usar(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([]).save(str(ruta))
    assert pistas_de_midi(ruta)[0].motivo_no_usable is not None


def test_dos_notas_a_la_vez_entran_las_dos(tmp_path):
    """Un acorde: el modelo lo admite, el carril no lo sigue. Lo avisa la pantalla."""
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS), (47, 0, TICKS)]).save(str(ruta))
    pieza = pieza_desde_midi(ruta, 1)
    assert len(pieza.notas) == 2
    assert pieza.notas[0].inicio_pulsos == pieza.notas[1].inicio_pulsos


def test_un_note_on_con_velocidad_cero_cierra_la_nota(tmp_path):
    """La trampa clasica: si se ignora, la nota no se cierra y dura hasta el final."""
    ruta = tmp_path / "x.mid"
    archivo = mido.MidiFile(ticks_per_beat=TICKS)
    pista = mido.MidiTrack()
    archivo.tracks.append(pista)
    pista.append(mido.Message("note_on", note=40, velocity=64, time=0))
    pista.append(mido.Message("note_on", note=40, velocity=0, time=TICKS))
    pista.append(mido.Message("note_on", note=45, velocity=64, time=0))
    pista.append(mido.Message("note_on", note=45, velocity=0, time=TICKS * 3))
    archivo.save(str(ruta))
    pieza = pieza_desde_midi(ruta, 1)
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 1.0]
    assert [n.duracion_pulsos for n in pieza.notas] == [1.0, 3.0]


def test_un_cambio_de_compas_se_marca_y_se_toma_el_primero(tmp_path):
    ruta = tmp_path / "x.mid"
    archivo = midi_de([(40, 0, TICKS)])
    archivo.tracks[0].insert(1, mido.MetaMessage("time_signature", numerator=3, denominator=4))
    archivo.tracks[0].append(mido.MetaMessage("time_signature", numerator=6, denominator=8))
    archivo.save(str(ruta))
    pieza = pieza_desde_midi(ruta, 1)
    assert pieza.compas == (3, 4)
    assert pieza.compas_variable is True


def test_sin_cambios_las_banderas_quedan_bajas_y_el_compas_es_4_4(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS)]).save(str(ruta))
    pieza = pieza_desde_midi(ruta, 1)
    assert pieza.compas == (4, 4)
    assert not pieza.tempo_variable and not pieza.compas_variable


def test_el_tempo_puede_vivir_en_otra_pista(tmp_path):
    ruta = tmp_path / "x.mid"
    archivo = mido.MidiFile(type=1, ticks_per_beat=TICKS)
    conductor = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(100))])
    archivo.tracks.append(conductor)
    archivo.tracks.append(midi_de([(40, 0, TICKS)]).tracks[0])
    archivo.save(str(ruta))
    assert pieza_desde_midi(ruta, 2).tempo == 100
    assert not pistas_de_midi(ruta)[0].usable


def test_la_percusion_no_se_importa(tmp_path):
    ruta = tmp_path / "x.mid"
    archivo = mido.MidiFile(ticks_per_beat=TICKS)
    archivo.tracks.append(mido.MidiTrack([
        mido.Message("note_on", channel=9, note=36, time=0),
        mido.Message("note_off", channel=9, note=36, time=TICKS),
    ]))
    archivo.save(str(ruta))
    assert pistas_de_midi(ruta)[0].instrumento == "Percusion"
    with pytest.raises(ValueError, match="percusion"):
        pieza_desde_midi(ruta, 1)


def test_un_archivo_que_no_es_midi_da_un_mensaje_legible(tmp_path):
    ruta = tmp_path / "x.mid"
    ruta.write_bytes(b"esto no es un midi")
    with pytest.raises(ValueError, match="MIDI"):
        pistas_de_midi(ruta)


def test_la_nota_que_no_cabe_no_deja_traceback_encadenado(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(20, 0, TICKS)]).save(str(ruta))
    with pytest.raises(ValueError) as error:
        pieza_desde_midi(ruta, 1)
    assert error.value.__suppress_context__
    assert "Guitarra" in str(error.value)


def _melodia_larga(cantidad, semilla=7):
    """Una melodia pseudoaleatoria dentro del registro de la guitarra, una nota por pulso."""
    midis = np.random.default_rng(semilla).integers(40, 77, size=cantidad)
    return [(int(m), i * TICKS, TICKS) for i, m in enumerate(midis)]


def test_la_digitacion_es_un_minimo_sobre_la_pieza_entera(tmp_path):
    """Protege lo que da valor a la etapa: `digitar` recibe todos los midis de golpe.

    Digitar nota a nota (`[digitar([m], p)[0] for m in midis]`) deja la mano sin
    memoria y sale bastante mas caro; esta prueba muere si alguien lo simplifica asi.
    """
    ruta = tmp_path / "x.mid"
    melodia = _melodia_larga(60)
    midi_de(melodia).save(str(ruta))
    perfil = PERFILES["guitarra_estandar"]
    midis = [m for m, _, _ in melodia]

    pieza = pieza_desde_midi(ruta, 1)
    del_lector = tuple(Posicion(n.cuerda, n.traste) for n in pieza.notas)
    de_golpe = coste_total(digitar(midis, perfil), perfil)
    nota_a_nota = coste_total(tuple(digitar([m], perfil)[0] for m in midis), perfil)

    assert coste_total(del_lector, perfil) == pytest.approx(de_golpe)
    # La prueba solo tiene sentido si la alternativa de verdad es peor.
    assert nota_a_nota > de_golpe * 1.2


def test_una_pieza_larga_acumula_bien_los_delta(tmp_path):
    ruta = tmp_path / "x.mid"
    melodia = _melodia_larga(400)
    midi_de(melodia).save(str(ruta))
    pieza = pieza_desde_midi(ruta, 1)
    assert len(pieza.notas) == 400
    assert [n.inicio_pulsos for n in pieza.notas] == [float(i) for i in range(400)]
    assert all(n.duracion_pulsos == 1.0 for n in pieza.notas)
    assert pieza.notas[-1].fin_pulsos == 400.0


def test_cada_pista_usa_su_propio_reloj(tmp_path):
    """Con notas en varias pistas, los delta de una no se acumulan en la otra."""
    ruta = tmp_path / "x.mid"
    archivo = mido.MidiFile(type=1, ticks_per_beat=TICKS)
    archivo.tracks.append(midi_de(_melodia_larga(50, 1), nombre_pista="A").tracks[0])
    desfasada = [(m, 10 * TICKS + i * TICKS * 2, TICKS * 2) for i, (m, _, _) in enumerate(_melodia_larga(30, 2))]
    archivo.tracks.append(midi_de(desfasada, nombre_pista="B").tracks[0])
    archivo.save(str(ruta))

    primera = pieza_desde_midi(ruta, 1)
    segunda = pieza_desde_midi(ruta, 2)
    assert [n.inicio_pulsos for n in primera.notas] == [float(i) for i in range(50)]
    assert [n.inicio_pulsos for n in segunda.notas] == [10.0 + 2 * i for i in range(30)]
    assert all(n.duracion_pulsos == 2.0 for n in segunda.notas)


def test_un_acorde_no_pone_dos_notas_en_la_misma_cuerda(tmp_path):
    """Un acorde tocable: sin la correccion, digitar lo trata como secuencia."""
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS), (45, 0, TICKS), (52, 0, TICKS)]).save(str(ruta))
    notas = pieza_desde_midi(ruta, 1).notas
    perfil = PERFILES["guitarra_estandar"]
    assert len({n.cuerda for n in notas}) == 3
    assert sorted(n.midi for n in notas) == [40, 45, 52]
    for n in notas:  # cada posicion produce de verdad esa nota
        assert Posicion(n.cuerda, n.traste) in posiciones_en_mastil(n.midi, perfil)


def test_un_acorde_que_ninguna_mano_toca_se_rechaza(tmp_path):
    """40, 45 y 49 a la vez: el 40 solo vive en la 6a y el 45 y el 49 en la 5a y la 6a.

    Digitado como secuencia salia 6/0, 5/0 y 5/4: dos notas en la misma cuerda.
    """
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS), (45, 0, TICKS), (49, 0, TICKS)]).save(str(ruta))
    with pytest.raises(ValueError, match="acorde"):
        pieza_desde_midi(ruta, 1)


def test_un_acorde_imposible_se_rechaza_nombrandolo(tmp_path):
    """Siete notas no caben en seis cuerdas."""
    ruta = tmp_path / "x.mid"
    midi_de([(m, 0, TICKS) for m in (40, 45, 50, 55, 59, 64, 67)]).save(str(ruta))
    with pytest.raises(ValueError, match="acorde"):
        pieza_desde_midi(ruta, 1)
