"""Pruebas de las voces de fondo: las notas de las pistas que el usuario NO toca.

Lo que se vigila aqui no es la digitacion -no hay- sino lo contrario: que sacar las
alturas y los instantes de las demas pistas NO pase por el mastil, y por eso
funcione justo donde `importar` tiene que rendirse (un piano no cabe en seis
cuerdas). Las muestras se fabrican con los mismos constructores que las pruebas de
cada lector, para no tener dos versiones del mismo archivo de ejemplo.

El modulo tiene CUATRO caminos, uno por formato, y cada uno abre el archivo con un
parser distinto: lo que vale para Guitar Pro no dice nada de MIDI. Asi que las
exclusiones, los tempos, las alturas y los instrumentos se prueban formato por
formato, y no una vez «en general».
"""

import copy
import inspect

import guitarpro
import mido
import pytest
from music21 import instrument, note, stream, tempo as tempos_m21

from nucleo.piezas.desde_ascii import pieza_desde_ascii
from nucleo.piezas.desde_guitarpro import _contar_notas, _instrumento, _motivo_no_usable
from nucleo.piezas.desde_midi import pistas_de_midi
from nucleo.piezas.desde_musicxml import pistas_de_musicxml
from nucleo.piezas.lectores import FORMATOS, importar
from nucleo.piezas.voces_de_fondo import _VOCES, NotaDeFondo, voces_de
from tests.test_desde_ascii import ESTANDAR
from tests.test_desde_guitarpro import con_notas, con_repeticion, escribir
from tests.test_desde_midi import TICKS, midi_de
from tests.test_desde_musicxml import escribir as escribir_musicxml, partitura


# ---------------------------------------------------------------------------
# Constructores. Cada uno monta un archivo de VARIAS pistas a partir del
# constructor de una del lector correspondiente: la del usuario y las que
# tienen que sonar de fondo.
# ---------------------------------------------------------------------------


def _segunda_pista(cancion, nombre, percusion=False, subir=2):
    """Clona la pista 1 de una cancion de Guitar Pro como pista 2, distinguible.

    Los trastes de la copia suben `subir` semitonos para que sus alturas no se
    puedan confundir con las de la pista 1 si el despacho de pistas se equivoca.
    """
    segunda = copy.deepcopy(cancion.tracks[0])
    segunda.name = nombre
    segunda.number = 2
    segunda.isPercussionTrack = percusion
    for compas in segunda.measures:
        for voz in compas.voices:
            for beat in voz.beats:
                for nota in beat.notes:
                    nota.value += subir
    cancion.tracks.append(segunda)
    return cancion


def _gp5_de_dos_pistas(tmp_path, percusion=False, tempo=90, nombre="Bajo de fondo"):
    """Un .gp5 con la pista del usuario y una segunda distinguible."""
    cancion = con_notas([(0, 6, 3), (1, 6, 5)])
    cancion.tempo = tempo
    cancion.tracks[0].name = "La mia"
    return escribir(
        _segunda_pista(cancion, nombre, percusion=percusion), tmp_path, "dos_pistas.gp5"
    )


def _gp5_con_repeticion(tmp_path):
    """Un .gp5 de dos pistas con los dos compases entre barras de repeticion."""
    cancion = con_repeticion()
    cancion.tracks[0].name = "La mia"
    return escribir(
        _segunda_pista(cancion, "Con repeticion"), tmp_path, "repeticion.gp5"
    )


def _midi_con_un_piano(tmp_path):
    """Un .mid cuya pista 2 es un piano: alturas que no caben en una guitarra."""
    ruta = tmp_path / "con_piano.mid"
    archivo = midi_de([(45, 0, TICKS)], nombre_pista="La mia")
    archivo.tracks[0].insert(1, mido.Message("program_change", program=25))
    piano = midi_de(
        [(20, 0, TICKS), (100, TICKS, TICKS * 2)], nombre_pista="Piano"
    ).tracks[0]
    piano.insert(1, mido.Message("program_change", program=0))
    archivo.tracks.append(piano)
    archivo.save(str(ruta))
    return ruta


def _midi_con_bateria(tmp_path):
    """Un .mid cuya pista 2 toca en el canal 10, el de percusion."""
    ruta = tmp_path / "con_bateria.mid"
    archivo = midi_de([(45, 0, TICKS)], nombre_pista="La mia")
    archivo.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage("track_name", name="Bateria", time=0),
                mido.Message("note_on", channel=9, note=36, time=0),
                mido.Message("note_off", channel=9, note=36, time=TICKS),
            ]
        )
    )
    archivo.save(str(ruta))
    return ruta


def _midi_de_formato_1(tmp_path):
    """Un .mid de formato 1: la pista 1 solo lleva el tempo, sin una sola nota.

    Es como guarda un MIDI cualquier secuenciador, y por eso importa: esa pista no
    es una perdida para el usuario, es la convencion del formato. El tempo de la
    pista de tempo (76) es distinto del que `midi_de` pone en las demas (120), asi
    que el archivo sirve ademas para ver CUAL de los dos gana.
    """
    ruta = tmp_path / "formato_1.mid"
    archivo = mido.MidiFile(ticks_per_beat=TICKS)
    archivo.tracks.append(
        mido.MidiTrack(
            [
                mido.MetaMessage("track_name", name="Tempo", time=0),
                mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(76), time=0),
            ]
        )
    )
    archivo.tracks.append(midi_de([(45, 0, TICKS)], nombre_pista="La mia").tracks[0])
    archivo.tracks.append(midi_de([(20, 0, TICKS)], nombre_pista="Piano").tracks[0])
    archivo.save(str(ruta))
    return ruta


def _parte(nombre, midis_y_duraciones, bpm, instrumento):
    parte = stream.Part()
    parte.partName = nombre
    parte.insert(0, instrumento)
    parte.append(tempos_m21.MetronomeMark(number=bpm))
    for midi, duracion in midis_y_duraciones:
        nota = note.Note(midi)
        nota.quarterLength = duracion
        parte.append(nota)
    return parte


def _musicxml_de_dos_partes(tmp_path):
    """Un MusicXML cuya parte 2 es un piano, con alturas que no caben en el mastil."""
    obra = partitura([(45, 1.0), (47, 1.0)], bpm=76)
    obra.parts[0].insert(0, instrument.AcousticGuitar())
    obra.insert(
        0,
        _parte("Piano", ((20, 1.0), (100, 2.0)), 76, instrument.Piano()),
    )
    return escribir_musicxml(obra, tmp_path, "dos_partes.xml")


def _musicxml_de_dos_tempos(tmp_path):
    """Dos partes tocables que declaran tempos DISTINTOS: 76 la primera, 140 la otra."""
    obra = partitura([(52, 1.0), (53, 1.0)], bpm=76)
    obra.insert(
        0, _parte("Segunda", ((45, 1.0), (47, 1.0)), 140, instrument.AcousticGuitar())
    )
    return escribir_musicxml(obra, tmp_path, "dos_tempos.xml")


def _musicxml_con_una_parte_sin_notas(tmp_path):
    """Una obra cuya parte 2 no trae ni una nota: solo un silencio."""
    obra = partitura([(45, 1.0), (47, 1.0)], bpm=76)
    letra = stream.Part()
    letra.partName = "Letra"
    letra.append(tempos_m21.MetronomeMark(number=76))
    letra.append(note.Rest(quarterLength=4.0))
    obra.insert(0, letra)
    return escribir_musicxml(obra, tmp_path, "con_vacia.xml")


def _tablatura(tmp_path):
    ruta = tmp_path / "tablatura.txt"
    ruta.write_text(ESTANDAR, encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# Lo minimo: suena lo que el usuario no toca
# ---------------------------------------------------------------------------


def test_las_demas_pistas_suenan_y_la_tuya_no(tmp_path):
    """De dos pistas, suena la que el usuario no esta tocando."""
    ruta = _gp5_de_dos_pistas(tmp_path)

    fondo = voces_de(ruta, 1)

    assert len(fondo.voces) == 1
    voz = fondo.voces[0]
    assert voz.nombre == "Bajo de fondo"
    # El instrumento es el que dice el canal de ESA pista, no uno cualquiera: es lo
    # que el usuario va a leer para subir el bajo y bajar la guitarra.
    esperado = _instrumento(guitarpro.parse(str(ruta)).tracks[1])
    assert voz.instrumento == esperado != "Desconocido"
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


def test_las_repeticiones_se_expanden_como_en_la_pista_del_usuario(tmp_path):
    """El fondo tiene que durar lo que dura la cancion, no la mitad.

    Una barra de repeticion no es un adorno: si el fondo no la expande, suena una
    vez lo que el usuario toca dos veces y se desincroniza a la mitad. El oraculo es
    `importar` sobre LA MISMA pista, que expande con la convencion correcta para
    gp5 (la del byte del cierre, que no significa lo mismo en gp3/gp4).
    """
    ruta = _gp5_con_repeticion(tmp_path)

    voz = voces_de(ruta, 1).voces[0]

    pieza = importar(ruta, 2)
    # Dos compases tocados dos veces: cuatro notas donde el archivo escribe dos.
    assert len(voz.notas) == 4
    assert [n.inicio_pulsos for n in voz.notas] == [
        n.inicio_pulsos for n in pieza.notas
    ]
    assert [n.midi for n in voz.notas] == [n.midi for n in pieza.notas]


# ---------------------------------------------------------------------------
# Lo que no puede sonar, y lo que no hay que anunciar
# ---------------------------------------------------------------------------


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


def test_en_midi_la_percusion_tambien_se_excluye_y_se_dice_por_que(tmp_path):
    """El mismo caso en MIDI, que es otro parser y otra forma de reconocerla.

    Aqui la bateria no se declara: se deduce del canal 10. Si la guarda faltara, sus
    notas -el 36 es el bombo- sonarian como alturas de un piano.
    """
    ruta = _midi_con_bateria(tmp_path)

    fondo = voces_de(ruta, 1)

    assert fondo.voces == ()
    # El motivo lo decide `desde_midi`, que es quien sabe lo del canal 10; esta
    # prueba no sabe que frase es.
    esperado = pistas_de_midi(ruta)[1].motivo_no_usable
    assert esperado is not None
    assert fondo.excluidas == (("Bateria", esperado),)


def test_una_pista_vacia_no_se_anuncia_como_perdida(tmp_path):
    """`excluidas` dice QUE SE PERDIO, y de una pista sin notas no se pierde nada.

    No poder sonar y quitarle algo al usuario no es lo mismo: la bateria si se echa
    de menos, una pista vacia no. Anunciarla seria decirle que le falta un trozo del
    fondo cuando no le falta ninguno.
    """
    ruta = _gp5_de_dos_pistas(tmp_path, nombre="Vacia")
    cancion = guitarpro.parse(str(ruta))
    for compas in cancion.tracks[1].measures:
        for voz in compas.voices:
            voz.beats.clear()
    vacia = tmp_path / "con_vacia.gp5"
    guitarpro.write(cancion, str(vacia))

    fondo = voces_de(vacia, 1)

    # Que la pista NO SE PUEDE usar lo dice el lector, no esta prueba: asi se ve que
    # la rama que se ejercita es la de la exclusion y no la de una pista normal.
    pista = guitarpro.parse(str(vacia)).tracks[1]
    assert _motivo_no_usable(pista, _contar_notas(pista)) is not None
    assert fondo.voces == ()
    assert fondo.excluidas == ()


def test_la_pista_de_tempo_de_un_midi_no_se_anuncia_como_perdida(tmp_path):
    """El caso real de la regla: un MIDI de formato 1 empieza por una pista sin notas.

    La pista de tempo es la convencion del formato, no un trozo de la cancion. Si
    apareciera en `excluidas`, el usuario leeria «La pista no tiene ninguna nota» de
    algo que nunca iba a sonar.
    """
    ruta = _midi_de_formato_1(tmp_path)

    fondo = voces_de(ruta, 2)

    assert pistas_de_midi(ruta)[0].motivo_no_usable is not None
    assert [voz.nombre for voz in fondo.voces] == ["Piano"]
    assert fondo.excluidas == ()


def test_en_musicxml_una_parte_sin_notas_no_suena_ni_se_anuncia(tmp_path):
    """La misma regla en el tercer parser: una parte de solo silencios se calla.

    No suena -no tiene nada que sonar- y no se anuncia, por lo mismo que la pista de
    tempo de un MIDI. Que la parte no es usable lo dice `desde_musicxml`.
    """
    ruta = _musicxml_con_una_parte_sin_notas(tmp_path)

    fondo = voces_de(ruta, 1)

    assert pistas_de_musicxml(ruta)[1].motivo_no_usable is not None
    assert fondo.voces == ()
    assert fondo.excluidas == ()


# ---------------------------------------------------------------------------
# El caso por el que el modulo existe
# ---------------------------------------------------------------------------


def test_una_pista_que_no_cabe_en_la_afinacion_SI_suena(tmp_path):
    """Un piano no cabe en seis cuerdas y `importar` tiene que rechazarlo -no hay
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
    assert voz.instrumento == pistas_de_midi(ruta)[1].instrumento != "Desconocido"
    # Las alturas son las que se escribieron en el archivo, no las que caben en una
    # guitarra: 20 esta muy por debajo de la sexta cuerda y 100 muy por encima del
    # ultimo traste.
    assert [n.midi for n in voz.notas] == [20, 100]
    assert [n.inicio_pulsos for n in voz.notas] == [0.0, 1.0]
    assert [n.duracion_pulsos for n in voz.notas] == [1.0, 2.0]
    assert fondo.excluidas == ()


def test_en_musicxml_las_alturas_y_los_instantes_salen_del_archivo(tmp_path):
    """El mismo piano imposible, leido por el parser de MusicXML.

    Las cifras van escritas porque aqui no hay segundo camino: `importar` rechaza la
    parte, asi que el oraculo es el dato con el que se fabrico el archivo.
    """
    ruta = _musicxml_de_dos_partes(tmp_path)

    with pytest.raises(ValueError):
        importar(ruta, 2)

    voz = voces_de(ruta, 1).voces[0]
    assert voz.nombre == "Piano"
    assert voz.instrumento == pistas_de_musicxml(ruta)[1].instrumento != "Desconocido"
    assert [n.midi for n in voz.notas] == [20, 100]
    assert [n.inicio_pulsos for n in voz.notas] == [0.0, 1.0]
    assert [n.duracion_pulsos for n in voz.notas] == [1.0, 2.0]


# ---------------------------------------------------------------------------
# El tempo, formato por formato
# ---------------------------------------------------------------------------


def test_el_tempo_sale_del_archivo_y_no_se_inventa(tmp_path):
    """Guitar Pro: el tempo del fondo es el mismo que trae la pieza."""
    ruta = _gp5_de_dos_pistas(tmp_path, tempo=137)

    assert voces_de(ruta, 1).tempo == importar(ruta, 1).tempo


def test_el_tempo_de_un_midi_es_el_primero_del_archivo(tmp_path):
    """MIDI: el tempo es el PRIMERO, el mismo que toma la pieza.

    El archivo trae dos tempos distintos -76 en la pista de tempo y 120 en las
    demas-, y que sean distintos no lo afirma esta prueba: lo afirma la pieza, con
    su bandera de tempo variable. Sin eso, tomar el ultimo en vez del primero
    pasaria desapercibido.
    """
    ruta = _midi_de_formato_1(tmp_path)

    pieza = importar(ruta, 2)
    assert pieza.tempo_variable is True
    assert voces_de(ruta, 2).tempo == pieza.tempo


def test_el_tempo_de_un_musicxml_es_el_de_la_primera_parte(tmp_path):
    """MusicXML: con dos partes que declaran tempos distintos, gana la primera.

    Las dos referencias son `importar`: la de la parte 1 es el tempo esperado y la
    de la parte 2 esta solo para demostrar que el archivo tiene DOS tempos y que la
    comparacion distingue cual sale.
    """
    ruta = _musicxml_de_dos_tempos(tmp_path)

    de_la_primera = importar(ruta, 1).tempo
    de_la_segunda = importar(ruta, 2).tempo
    assert de_la_primera != de_la_segunda
    assert voces_de(ruta, 1).tempo == de_la_primera


def test_el_fondo_de_una_tablatura_usa_el_tempo_por_omision_del_lector_de_ascii(
    tmp_path,
):
    """Una tablatura de texto no lleva tempo escrito: hay que ponerle uno.

    El que se pone es EL MISMO que pone el lector de ASCII cuando nadie le dice
    otro, y la prueba lo saca de la firma de ese lector en vez de repetir el numero:
    si alla cambia, aqui se entera.
    """
    por_omision = inspect.signature(pieza_desde_ascii).parameters["tempo"].default

    assert voces_de(_tablatura(tmp_path), 1).tempo == por_omision


# ---------------------------------------------------------------------------
# Los cuatro formatos y el despacho
# ---------------------------------------------------------------------------


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

    # Una tablatura de texto es UNA pista, la del usuario: no hay nada de fondo. Y
    # no es un error, porque el programa ofrece el fondo para cualquier archivo.
    fondo = voces_de(_tablatura(tmp_path), 1)
    assert fondo.voces == ()
    assert fondo.excluidas == ()


def test_sin_mas_pistas_no_hay_voces_pero_tampoco_error(tmp_path):
    """Una cancion de una sola pista no tiene fondo, y eso no es un fallo."""
    ruta = escribir(con_notas([(0, 6, 3)]), tmp_path, "una.gp5")

    fondo = voces_de(ruta, 1)

    assert fondo.voces == ()
    assert fondo.excluidas == ()
    assert fondo.tempo == importar(ruta, 1).tempo


def test_toda_extension_que_se_importa_se_puede_oir_de_fondo():
    """El despacho del fondo cubre exactamente los formatos que se pueden leer.

    Una extension que se puede listar e importar y NO se puede oir seria un
    `KeyError` en la cara del usuario a mitad de la pantalla de practica. La lista
    la manda `lectores.FORMATOS`, que es la de los formatos que funcionan.
    """
    assert set(_VOCES) == set(FORMATOS)
