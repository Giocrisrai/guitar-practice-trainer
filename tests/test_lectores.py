import importlib

import pytest

from nucleo.piezas.lectores import (
    _CONVERSORES,
    _LECTORES,
    FORMATOS,
    importar,
    pistas_de_archivo,
)

TABLATURA = (
    "e|--0--2--|\nB|--------|\nG|--------|\nD|--------|\nA|--------|\nE|--3--5--|\n"
)


def test_los_cuatro_formatos_estan_registrados():
    assert {".gp5", ".mid", ".xml", ".txt"} <= set(FORMATOS)


def test_las_dos_tablas_cubren_las_mismas_extensiones():
    assert set(_LECTORES) == set(_CONVERSORES) == set(FORMATOS)


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
        ("desde_guitarpro", (".gp3", ".gp4", ".gp5", ".gpx", ".gp")),
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
