"""Pruebas de las voces de fondo: las notas de las pistas que el usuario NO toca.

Lo que se vigila aqui no es la digitacion -no hay- sino lo contrario: que sacar las
alturas y los instantes de las demas pistas NO pase por el mastil, y por eso
funcione justo donde `importar` tiene que rendirse (un piano no cabe en seis
cuerdas). Las muestras se fabrican con los mismos constructores que las pruebas de
cada lector, para no tener dos versiones del mismo archivo de ejemplo.
"""

import copy

import guitarpro
import mido
import pytest
from music21 import note, stream, tempo as tempos_m21

from nucleo.piezas.desde_guitarpro import _contar_notas, _motivo_no_usable
from nucleo.piezas.lectores import importar
from nucleo.piezas.voces_de_fondo import NotaDeFondo, voces_de
from tests.test_desde_ascii import ESTANDAR
from tests.test_desde_guitarpro import con_notas, escribir
from tests.test_desde_midi import TICKS, midi_de
from tests.test_desde_musicxml import escribir as escribir_musicxml, partitura


# ---------------------------------------------------------------------------
# Constructores. Cada uno monta un archivo de DOS pistas a partir del
# constructor de una del lector correspondiente: la 1 es la del usuario y la 2
# la que tiene que sonar de fondo.
# ---------------------------------------------------------------------------


def _gp5_de_dos_pistas(tmp_path, percusion=False, tempo=90, nombre="Bajo de fondo"):
    """Un .gp5 con la pista del usuario y una segunda distinguible.

    La segunda es la primera con los trastes subidos dos semitonos, para que sus
    alturas no se puedan confundir con las de la pista 1 si el despacho de pistas
    se equivoca.
    """
    cancion = con_notas([(0, 6, 3), (1, 6, 5)])
    cancion.tempo = tempo
    cancion.tracks[0].name = "La mia"
    segunda = copy.deepcopy(cancion.tracks[0])
    segunda.name = nombre
    segunda.number = 2
    segunda.isPercussionTrack = percusion
    for compas in segunda.measures:
        for voz in compas.voices:
            for beat in voz.beats:
                for nota in beat.notes:
                    nota.value += 2
    cancion.tracks.append(segunda)
    return escribir(cancion, tmp_path, "dos_pistas.gp5")


def _midi_con_un_piano(tmp_path):
    """Un .mid cuya pista 2 es un piano: alturas que no caben en una guitarra."""
    ruta = tmp_path / "con_piano.mid"
    archivo = midi_de([(45, 0, TICKS)], nombre_pista="La mia")
    archivo.tracks.append(
        midi_de(
            [(20, 0, TICKS), (100, TICKS, TICKS * 2)], nombre_pista="Piano"
        ).tracks[0]
    )
    archivo.save(str(ruta))
    return ruta


def _musicxml_de_dos_partes(tmp_path):
    """Un MusicXML cuya parte 2 es un piano, con las mismas alturas imposibles."""
    obra = partitura([(45, 1.0), (47, 1.0)])
    segunda = stream.Part()
    segunda.partName = "Piano"
    segunda.append(tempos_m21.MetronomeMark(number=100))
    for midi, duracion in ((20, 1.0), (100, 2.0)):
        nota = note.Note(midi)
        nota.quarterLength = duracion
        segunda.append(nota)
    obra.insert(0, segunda)
    return escribir_musicxml(obra, tmp_path, "dos_partes.xml")


def _tablatura(tmp_path):
    ruta = tmp_path / "tablatura.txt"
    ruta.write_text(ESTANDAR, encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Las pruebas
# ---------------------------------------------------------------------------


def test_las_demas_pistas_suenan_y_la_tuya_no(tmp_path):
    """Lo minimo: de dos pistas, suena la que el usuario no esta tocando."""
    ruta = _gp5_de_dos_pistas(tmp_path)

    fondo = voces_de(ruta, 1)

    assert len(fondo.voces) == 1
    voz = fondo.voces[0]
    assert voz.nombre == "Bajo de fondo"
    # Las alturas y los instantes se comparan contra los que `importar` saca de ESA
    # pista: dos caminos distintos sobre el mismo archivo tienen que coincidir, y
    # asi la prueba falla tambien si se cuela la pista equivocada.
    pieza = importar(ruta, 2)
    assert [n.midi for n in voz.notas] == [n.midi for n in pieza.notas]
    assert [n.inicio_pulsos for n in voz.notas] == [
        n.inicio_pulsos for n in pieza.notas
    ]
    assert [n.duracion_pulsos for n in voz.notas] == [
        n.duracion_pulsos for n in pieza.notas
    ]
    assert all(isinstance(n, NotaDeFondo) for n in voz.notas)


def test_la_pista_del_usuario_no_entra_ni_como_excluida(tmp_path):
    """La pista reservada no es una pista «rechazada»: no se la nombra.

    `excluidas` es la lista de las que NO PUEDEN sonar y por que. La del usuario si
    podria, simplemente la toca el; ponerla ahi haria que la pantalla dijera que su
    propia pista no sirve.
    """
    ruta = _gp5_de_dos_pistas(tmp_path, nombre="La otra")

    for excluida in (1, 2):
        fondo = voces_de(ruta, excluida)
        assert len(fondo.voces) == 1
        assert fondo.excluidas == ()
    assert voces_de(ruta, 1).voces[0].nombre == "La otra"
    assert voces_de(ruta, 2).voces[0].nombre == "La mia"


def test_una_pista_de_percusion_se_excluye_y_se_dice_por_que(tmp_path):
    """La bateria no tiene notas con altura: no suena, y se explica.

    El motivo se afirma contra `desde_guitarpro._motivo_no_usable`, que es quien lo
    escribe para el usuario, y no contra una copia del texto: si la frase cambia,
    esta prueba sigue valiendo y el que se entere sera quien la lea.
    """
    ruta = _gp5_de_dos_pistas(tmp_path, percusion=True, nombre="Bateria")

    fondo = voces_de(ruta, 1)

    assert fondo.voces == ()
    pista = guitarpro.parse(str(ruta)).tracks[1]
    esperado = _motivo_no_usable(pista, _contar_notas(pista))
    assert esperado is not None
    assert fondo.excluidas == (("Bateria", esperado),)


def test_una_pista_que_no_cabe_en_la_afinacion_SI_suena(tmp_path):
    """El caso por el que este modulo existe.

    Un piano no cabe en seis cuerdas y `importar` tiene que rechazarlo -no hay
    traste donde dibujar un La0-. Para SONAR no hace falta ningun traste, asi que
    la misma pista entra como voz de fondo con sus alturas intactas.
    """
    ruta = _midi_con_un_piano(tmp_path)

    with pytest.raises(ValueError):
        importar(ruta, 2)

    fondo = voces_de(ruta, 1)
    assert len(fondo.voces) == 1
    voz = fondo.voces[0]
    assert voz.nombre == "Piano"
    # Las alturas son las que se escribieron en el archivo, no las que caben en una
    # guitarra: 20 esta muy por debajo de la sexta cuerda y 100 muy por encima del
    # ultimo traste.
    assert [n.midi for n in voz.notas] == [20, 100]
    assert [n.inicio_pulsos for n in voz.notas] == [0.0, 1.0]
    assert [n.duracion_pulsos for n in voz.notas] == [1.0, 2.0]
    assert fondo.excluidas == ()


def test_el_tempo_sale_del_archivo_y_no_se_inventa(tmp_path):
    """El tempo del fondo es el de la cancion: el mismo que trae la pieza."""
    ruta = _gp5_de_dos_pistas(tmp_path, tempo=137)

    assert voces_de(ruta, 1).tempo == importar(ruta, 1).tempo


def test_sin_mas_pistas_no_hay_voces_pero_tampoco_error(tmp_path):
    """Una cancion de una sola pista no tiene fondo, y eso no es un fallo."""
    ruta = escribir(con_notas([(0, 6, 3)]), tmp_path, "una.gp5")

    fondo = voces_de(ruta, 1)

    assert fondo.voces == ()
    assert fondo.excluidas == ()
    assert fondo.tempo == importar(ruta, 1).tempo


def test_los_cuatro_formatos_dan_voces(tmp_path):
    """Guitar Pro, MIDI y MusicXML traen voces; la tablatura de texto, ninguna."""
    for ruta, nombre in (
        (_gp5_de_dos_pistas(tmp_path, nombre="Segunda"), "Segunda"),
        (_midi_con_un_piano(tmp_path), "Piano"),
        (_musicxml_de_dos_partes(tmp_path), "Piano"),
    ):
        fondo = voces_de(ruta, 1)
        assert [voz.nombre for voz in fondo.voces] == [nombre], ruta.name
        assert fondo.voces[0].notas, ruta.name
        assert fondo.tempo > 0, ruta.name

    # Una tablatura de texto es UNA pista, la del usuario: no hay nada de fondo. Y
    # no es un error, porque el programa ofrece el fondo para cualquier archivo.
    fondo = voces_de(_tablatura(tmp_path), 1)
    assert fondo.voces == ()
    assert fondo.excluidas == ()


def test_una_pista_sin_notas_se_excluye_con_su_motivo(tmp_path):
    """Una pista vacia no tiene nada que sonar, y tampoco es un error."""
    ruta = _gp5_de_dos_pistas(tmp_path, nombre="Vacia")
    cancion = guitarpro.parse(str(ruta))
    for compas in cancion.tracks[1].measures:
        for voz in compas.voices:
            voz.beats.clear()
    vacia = tmp_path / "con_vacia.gp5"
    guitarpro.write(cancion, str(vacia))

    fondo = voces_de(vacia, 1)

    assert fondo.voces == ()
    pista = guitarpro.parse(str(vacia)).tracks[1]
    assert fondo.excluidas == (
        ("Vacia", _motivo_no_usable(pista, _contar_notas(pista))),
    )
