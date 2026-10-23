import importlib

import pytest

from nucleo.piezas.lectores import (
    _CONVERSORES,
    _LECTORES,
    FORMATOS,
    NO_LEIBLES,
    importar,
    mensaje_extension_no_valida,
    pistas_de_archivo,
)

TABLATURA = (
    "e|--0--2--|\nB|--------|\nG|--------|\nD|--------|\nA|--------|\nE|--3--5--|\n"
)


def test_los_cuatro_formatos_estan_registrados():
    assert {".gp5", ".mid", ".xml", ".txt"} <= set(FORMATOS)


def test_las_dos_tablas_cubren_las_mismas_extensiones():
    assert set(_LECTORES) == set(_CONVERSORES) == set(FORMATOS)


def test_lo_que_no_se_puede_leer_no_esta_en_formatos():
    """La regla de `FORMATOS`: si una extension esta en la tabla, se puede abrir.

    `.gpx` y `.gp` estuvieron dentro y no se podian leer, asi que el archivo entraba
    en la biblioteca y reventaba despues, al pedir las pistas. Las dos tablas tienen
    que ser disjuntas o volvemos a eso.
    """
    assert set(FORMATOS) & set(NO_LEIBLES) == set()


@pytest.mark.parametrize("extension", [".gpx", ".gp", ".GPX"])
def test_el_rechazo_de_un_guitar_pro_moderno_dice_que_hacer(tmp_path, extension):
    """No basta con «no reconozco esto»: el usuario tiene un archivo de Guitar Pro.

    Lo que necesita saber es que ESE formato no se lee y que exportando a gp5 sigue
    adelante, no la lista de extensiones a secas.
    """
    mensaje = mensaje_extension_no_valida(extension)
    assert "Guitar Pro" in mensaje
    assert ".gp5" in mensaje

    ruta = tmp_path / f"cancion{extension}"
    ruta.write_bytes(b"BCFZ no soy un gp5")
    with pytest.raises(ValueError, match=r"\.gp5"):
        pistas_de_archivo(ruta)
    with pytest.raises(ValueError, match=r"\.gp5"):
        importar(ruta, 1)


def test_el_rechazo_de_un_formato_que_no_es_de_guitar_pro_no_habla_de_guitar_pro(
    monkeypatch,
):
    """La frase sale de la TABLA, no esta escrita en la funcion.

    Decia «la librería con la que leemos Guitar Pro no sabe abrirlos» y mandaba a
    exportar desde Guitar Pro para CUALQUIER entrada de `NO_LEIBLES`. Hoy las dos
    son de Guitar Pro y es verdad; una tercera habria dado una frase falsa y una
    salida imposible. Se prueba con una tercera inventada, que es el unico modo de
    distinguir «la frase viene del dato» de «el dato coincide con la frase».
    """
    monkeypatch.setitem(
        NO_LEIBLES, ".ptb", ("Power Tab", "Vuelve a escribir la tablatura a mano.")
    )
    mensaje = mensaje_extension_no_valida(".ptb")
    assert "Power Tab" in mensaje
    assert "Vuelve a escribir la tablatura a mano." in mensaje
    assert "Guitar Pro" not in mensaje
    assert "TuxGuitar" not in mensaje
    # Y los formatos que valen siguen estando: es lo accionable del mensaje.
    assert ".gp5" in mensaje


def test_una_extension_desconocida_se_rechaza_diciendo_cuales_valen(tmp_path):
    ruta = tmp_path / "cancion.pdf"
    ruta.write_text("x")
    with pytest.raises(ValueError) as error:
        pistas_de_archivo(ruta)
    assert ".gp5" in str(error.value)
    with pytest.raises(ValueError, match=r"\.gp5"):
        importar(ruta, 1)


def test_el_registro_despacha_al_lector_correcto(tmp_path, monkeypatch):
    """No comprueba el contenido: comprueba que llama a quien debe, con la ruta."""
    llamados = []
    monkeypatch.setitem(
        _LECTORES, ".mid", lambda ruta: llamados.append(("midi", ruta)) or ()
    )
    monkeypatch.setitem(
        _LECTORES, ".xml", lambda ruta: llamados.append(("xml", ruta)) or ()
    )
    ruta = tmp_path / "x.mid"
    ruta.write_bytes(b"")
    assert pistas_de_archivo(ruta) == ()
    assert llamados == [("midi", ruta)]


def test_importar_despacha_con_numero_y_perfil(tmp_path, monkeypatch):
    llamados = []
    monkeypatch.setitem(
        _CONVERSORES, ".xml", lambda *args: llamados.append(args) or "pieza"
    )
    ruta = tmp_path / "x.xml"
    assert importar(ruta, 3, "bajo_estandar") == "pieza"
    assert llamados == [(ruta, 3, "bajo_estandar")]


def test_la_extension_no_distingue_mayusculas(tmp_path, monkeypatch):
    llamados = []
    monkeypatch.setitem(_LECTORES, ".gp5", lambda ruta: llamados.append(ruta) or ())
    ruta = tmp_path / "CANCION.GP5"
    ruta.write_bytes(b"no importa")
    pistas_de_archivo(ruta)
    assert llamados == [ruta]


_LECTORES_REALES = {
    "desde_guitarpro": "pistas_de",
    "desde_midi": "pistas_de_midi",
    "desde_musicxml": "pistas_de_musicxml",
}


@pytest.mark.parametrize(
    ("modulo", "extensiones"),
    [
        ("desde_guitarpro", (".gp3", ".gp4", ".gp5")),
        ("desde_midi", (".mid", ".midi")),
        ("desde_musicxml", (".xml", ".musicxml", ".mxl")),
    ],
)
def test_cada_extension_llega_al_lector_de_su_formato(
    tmp_path, monkeypatch, modulo, extensiones
):
    """Lo que el despacho simulado no ve: que la tabla real no cruce formatos."""
    llamados = []
    for nombre, funcion in _LECTORES_REALES.items():
        lector = importlib.import_module(f"nucleo.piezas.{nombre}")
        monkeypatch.setattr(
            lector, funcion, lambda ruta, marca=nombre: llamados.append(marca) or ()
        )
    for extension in extensiones:
        pistas_de_archivo(tmp_path / f"x{extension}")
    assert llamados == [modulo] * len(extensiones)


_CONVERSORES_REALES = {
    "desde_guitarpro": "pieza_desde_guitarpro",
    "desde_midi": "pieza_desde_midi",
    "desde_musicxml": "pieza_desde_musicxml",
}


@pytest.mark.parametrize(
    ("modulo", "extension", "con_perfil"),
    [
        ("desde_guitarpro", ".gp5", False),
        ("desde_midi", ".MID", True),
        ("desde_musicxml", ".xml", True),
    ],
)
def test_importar_llega_al_conversor_de_su_formato(
    tmp_path, monkeypatch, modulo, extension, con_perfil
):
    llamados = []
    for nombre, funcion in _CONVERSORES_REALES.items():
        lector = importlib.import_module(f"nucleo.piezas.{nombre}")
        monkeypatch.setattr(
            lector,
            funcion,
            lambda *args, marca=nombre, **kw: llamados.append((marca, args, kw))
            or "pieza",
        )
    ruta = tmp_path / f"x{extension}"
    assert importar(ruta, 2) == "pieza"
    assert importar(ruta, 2, "bajo_estandar") == "pieza"
    sin = (modulo, (ruta, 2), {})
    con = (modulo, (ruta, 2), {"perfil_clave": "bajo_estandar"} if con_perfil else {})
    assert llamados == [sin, con]


def test_la_tablatura_se_lee_del_archivo_y_se_pasa_como_texto(tmp_path):
    """La costura: el lector de ASCII recibe el contenido, no la ruta."""
    ruta = tmp_path / "Riff.TXT"
    ruta.write_text(TABLATURA, encoding="utf-8")
    pieza = importar(ruta, 1)
    assert [(n.cuerda, n.traste) for n in pieza.notas] == [
        (6, 3),
        (1, 0),
        (6, 5),
        (1, 2),
    ] or len(pieza.notas) == 4
    assert pieza.ritmo_aproximado
    assert pieza.nombre == "Riff"


def test_la_tablatura_en_windows_1252_tambien_se_lee(tmp_path):
    ruta = tmp_path / "ñ.tab"
    ruta.write_bytes(("Canción\n" + TABLATURA).encode("cp1252"))
    assert len(importar(ruta, 1).notas) == 4


def test_una_tablatura_tiene_una_sola_pista(tmp_path):
    ruta = tmp_path / "riff.txt"
    ruta.write_text(TABLATURA)
    (pista,) = pistas_de_archivo(ruta)
    assert (pista.numero, pista.notas, pista.instrumento, pista.usable) == (
        1,
        4,
        "Guitarra",
        True,
    )
    assert pista.cuerdas_midi == (40, 45, 50, 55, 59, 64)
    with pytest.raises(ValueError, match="una sola pista"):
        importar(ruta, 2)


def test_un_txt_que_no_es_tablatura_se_rechaza_al_listar(tmp_path):
    ruta = tmp_path / "notas.txt"
    ruta.write_text("la lista de la compra")
    with pytest.raises(ValueError, match="tablatura"):
        pistas_de_archivo(ruta)


# ---------------------------------------------------------------------------
# El invariante de `FORMATOS`: lo que esta en la tabla se abre de verdad
# ---------------------------------------------------------------------------


def _escribir_muestra(ruta):
    """Un archivo de verdad del formato que pide la extension de `ruta`.

    Fabricado con las librerias del proyecto, como el resto de las pruebas: ningun
    archivo con derechos de autor entra al repositorio.
    """
    import guitarpro
    import mido
    from music21 import note, stream, tempo

    formato = FORMATOS[ruta.suffix.lower()]
    if formato == "Guitar Pro":
        song = guitarpro.Song()
        song.tempo = 90
        pista = song.tracks[0]
        pista.name = "Guitarra"
        pista.strings = [
            guitarpro.GuitarString(number=i + 1, value=v)
            for i, v in enumerate((64, 59, 55, 50, 45, 40))
        ]
        compas = pista.measures[0]
        voz = compas.voices[0]
        beat = guitarpro.Beat(
            voice=voz,
            start=compas.header.start,
            duration=guitarpro.Duration(value=4),
            status=guitarpro.BeatStatus.normal,
        )
        beat.notes = [
            guitarpro.Note(beat=beat, value=3, string=6, type=guitarpro.NoteType.normal)
        ]
        voz.beats.append(beat)
        guitarpro.write(song, str(ruta))
        return
    if formato == "MIDI":
        archivo = mido.MidiFile(ticks_per_beat=480)
        pista = mido.MidiTrack()
        archivo.tracks.append(pista)
        pista.append(mido.Message("note_on", note=52, velocity=64, time=0))
        pista.append(mido.Message("note_off", note=52, velocity=0, time=480))
        archivo.save(str(ruta))
        return
    if formato == "Tablatura de texto":
        ruta.write_text(TABLATURA)
        return
    # MusicXML. `.mxl` es el mismo documento COMPRIMIDO, con su `META-INF`: es la
    # extension con mas papeletas de estar en la tabla sin funcionar, asi que se
    # fabrica el contenedor de verdad en vez de darla por buena.
    parte = stream.Part()
    parte.partName = "Guitarra"
    parte.append(tempo.MetronomeMark(number=80))
    for midi in (45, 47, 48):
        n = note.Note(midi)
        n.quarterLength = 1.0
        parte.append(n)
    obra = stream.Score()
    obra.append(parte)
    if ruta.suffix.lower() != ".mxl":
        obra.write("musicxml", fp=str(ruta))
        return
    import zipfile

    suelto = ruta.with_suffix(".xml")
    obra.write("musicxml", fp=str(suelto))
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as comprimido:
        comprimido.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0" encoding="UTF-8"?><container><rootfiles>'
            '<rootfile full-path="partitura.xml"/></rootfiles></container>',
        )
        comprimido.writestr("partitura.xml", suelto.read_text())
    suelto.unlink()


@pytest.mark.parametrize("extension", sorted(FORMATOS))
def test_toda_extension_de_formatos_abre_un_archivo_de_verdad(tmp_path, extension):
    """El invariante que `.gpx` y `.gp` rompian: estar en la tabla es funcionar.

    Las dos pasaban `_extension` -estaban en `FORMATOS` y en las dos tablas de
    despacho- y morian dentro del lector. Un despacho simulado no lo ve: hay que
    abrir un archivo de cada formato. Si manana alguien anade una extension a la
    tabla sin lector que la abra, esta prueba lo dice aqui y no en la biblioteca del
    usuario.
    """
    ruta = tmp_path / f"muestra{extension}"
    _escribir_muestra(ruta)

    pistas = pistas_de_archivo(ruta)
    assert pistas, f"'{extension}' no describe ninguna pista"
    pieza = importar(ruta, 1)
    assert pieza.notas, f"'{extension}' se abre pero no trae ninguna nota"
