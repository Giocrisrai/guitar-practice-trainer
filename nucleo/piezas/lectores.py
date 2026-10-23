"""Lo que los lectores de archivos comparten.

Cada formato -Guitar Pro, MusicXML, MIDI, tablatura de texto- tiene su propio
modulo y ninguno importa a los otros. Lo unico comun es como se DESCRIBE una pista
antes de convertirla: el usuario tiene que poder elegir cual importa, y para eso le
hace falta ver todas, incluidas las que no se pueden usar y por que.
"""

from collections.abc import Callable
from importlib import import_module
from dataclasses import dataclass
from pathlib import Path

from nucleo.afinaciones import PERFILES
from nucleo.musica import midi_de_nombre
from nucleo.piezas.modelo import Pieza

# Las dieciseis familias del General MIDI, de ocho programas cada una. Sirven para
# que el usuario reconozca la pista por su sonido y no por el numero 25.
FAMILIAS_GM = (
    "Piano",
    "Percusion cromatica",
    "Organo",
    "Guitarra",
    "Bajo",
    "Cuerdas",
    "Conjunto",
    "Metales",
    "Cañas",
    "Flautas",
    "Sintetizador solista",
    "Sintetizador de acompañamiento",
    "Sintetizador de efectos",
    "Etnico",
    "Percusivo",
    "Efectos de sonido",
)


@dataclass(frozen=True)
class PistaDisponible:
    """Una pista de un archivo, descrita sin convertirla.

    Listar tiene que ser barato: aqui no hay notas con sitio en el mastil ni en el
    tiempo, solo lo justo para que el usuario reconozca la pista que busca.

    numero: el que ve el usuario, empezando en 1.
    nombre: como la llamo quien escribio el archivo ("Guitarra ritmica").
    instrumento: la familia del sonido que trae ("Guitarra", "Bajo", "Percusion").
    cuerdas_midi: las cuerdas al aire EN EL ORDEN DEL ARCHIVO, sin reordenar, para
        que lo que se muestre sea lo que el archivo dice.
    notas: cuantas notas con altura trae, para distinguir una pista de verdad de
        una vacia o de una de letra.
    motivo_no_usable: None si se puede importar; si no, la frase que explica por
        que no, escrita para el usuario y no para un programador.
    """

    numero: int
    nombre: str
    instrumento: str
    cuerdas_midi: tuple[int, ...]
    notas: int
    motivo_no_usable: str | None = None

    @property
    def usable(self) -> bool:
        return self.motivo_no_usable is None

    def a_dict(self) -> dict:
        return {
            "numero": self.numero,
            "nombre": self.nombre,
            "instrumento": self.instrumento,
            "cuerdas_midi": list(self.cuerdas_midi),
            "notas": self.notas,
            "usable": self.usable,
            "motivo_no_usable": self.motivo_no_usable,
        }


# ---------------------------------------------------------------------------
# El registro: extension -> lector. No sabe nada de los formatos, solo a quien
# llamar. Las extensiones van en minusculas; `_extension` baja la del archivo.
# ---------------------------------------------------------------------------

_GUITAR_PRO = "Guitar Pro"
_MIDI = "MIDI"
_MUSICXML = "MusicXML"
_ASCII = "Tablatura de texto"

FORMATOS: dict[str, str] = {
    ".gp3": _GUITAR_PRO,
    ".gp4": _GUITAR_PRO,
    ".gp5": _GUITAR_PRO,
    ".gpx": _GUITAR_PRO,
    ".gp": _GUITAR_PRO,
    ".mid": _MIDI,
    ".midi": _MIDI,
    ".xml": _MUSICXML,
    ".musicxml": _MUSICXML,
    ".mxl": _MUSICXML,
    ".txt": _ASCII,
    ".tab": _ASCII,
}


def _diferido(modulo: str, nombre: str) -> Callable:
    """Una funcion de un lector, buscada al llamarla y no al importar.

    Los lectores importan `PistaDisponible` de este archivo; importarlos aqui arriba
    cerraria un circulo. Buscarlos en cada llamada lo evita, y de paso deja que una
    prueba cambie la funcion del lector y vea que el registro la sigue.
    """

    def llamar(*args, **kwargs):
        return getattr(import_module(f"nucleo.piezas.{modulo}"), nombre)(
            *args, **kwargs
        )

    return llamar


def _leer_texto(ruta: Path) -> str:
    """El contenido de un archivo de texto; UTF-8 y, si no, Windows-1252.

    Las tablaturas de los foros llegan en cualquiera de las dos. Latin-1 no puede
    fallar, asi que nunca se rechaza un archivo por su codificacion.
    """
    datos = ruta.read_bytes()
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


def _pistas_de_ascii(ruta: Path | str) -> tuple[PistaDisponible, ...]:
    """El ASCII no tiene pistas: una sola, la tablatura, descrita al leerla.

    Leerla ya es validarla, asi que un .txt que no es una tablatura se rechaza aqui
    y no al importar.
    """
    pieza = _diferido("desde_ascii", "pieza_desde_ascii")(_leer_texto(Path(ruta)))
    cuerdas = PERFILES[pieza.perfil].cuerdas
    return (
        PistaDisponible(
            numero=1,
            nombre=pieza.nombre,
            instrumento="Bajo" if len(cuerdas) == 4 else "Guitarra",
            cuerdas_midi=tuple(midi_de_nombre(cuerda.nota) for cuerda in cuerdas),
            notas=len(pieza.notas),
        ),
    )


def _pieza_de_ascii(
    ruta: Path | str, numero_pista: int, perfil_clave: str | None
) -> Pieza:
    # La costura: el lector de ASCII recibe TEXTO (tambien puede llegar pegado en un
    # cuadro), asi que quien tiene una ruta lo lee aqui y le pasa el contenido.
    if numero_pista != 1:
        raise ValueError(
            f"Una tablatura de texto tiene una sola pista, la 1, no la {numero_pista}."
        )
    ruta = Path(ruta)
    return _diferido("desde_ascii", "pieza_desde_ascii")(
        _leer_texto(ruta), perfil_clave=perfil_clave, nombre=ruta.stem
    )


def _pieza_de_guitarpro(
    ruta: Path | str, numero_pista: int, perfil_clave: str | None
) -> Pieza:
    # Guitar Pro trae su afinacion en el archivo y esa manda: `perfil_clave` no se usa.
    return _diferido("desde_guitarpro", "pieza_desde_guitarpro")(ruta, numero_pista)


def _con_perfil(
    lector: Callable[..., Pieza],
) -> Callable[[Path | str, int, str | None], Pieza]:
    """Adapta un lector que solo admite `perfil_clave` como texto: None es el suyo."""

    def convertir(
        ruta: Path | str, numero_pista: int, perfil_clave: str | None
    ) -> Pieza:
        if perfil_clave is None:
            return lector(ruta, numero_pista)
        return lector(ruta, numero_pista, perfil_clave=perfil_clave)

    return convertir


# Dos tablas con las mismas claves: listar las pistas y convertir una.
_LECTORES: dict[str, Callable[[Path | str], tuple[PistaDisponible, ...]]] = {
    **dict.fromkeys(
        (".gp3", ".gp4", ".gp5", ".gpx", ".gp"),
        _diferido("desde_guitarpro", "pistas_de"),
    ),
    **dict.fromkeys((".mid", ".midi"), _diferido("desde_midi", "pistas_de_midi")),
    **dict.fromkeys(
        (".xml", ".musicxml", ".mxl"), _diferido("desde_musicxml", "pistas_de_musicxml")
    ),
    **dict.fromkeys((".txt", ".tab"), _pistas_de_ascii),
}

_CONVERSORES: dict[str, Callable[[Path | str, int, str | None], Pieza]] = {
    **dict.fromkeys((".gp3", ".gp4", ".gp5", ".gpx", ".gp"), _pieza_de_guitarpro),
    **dict.fromkeys(
        (".mid", ".midi"), _con_perfil(_diferido("desde_midi", "pieza_desde_midi"))
    ),
    **dict.fromkeys(
        (".xml", ".musicxml", ".mxl"),
        _con_perfil(_diferido("desde_musicxml", "pieza_desde_musicxml")),
    ),
    **dict.fromkeys((".txt", ".tab"), _pieza_de_ascii),
}


def _extension(ruta: Path | str, tabla: dict) -> str:
    extension = Path(ruta).suffix.lower()
    if extension not in tabla:
        validas = ", ".join(sorted(FORMATOS))
        raise ValueError(
            f"No sé leer archivos '{extension or 'sin extension'}'. Los que valen: {validas}"
        )
    return extension


def pistas_de_archivo(ruta: Path | str) -> tuple[PistaDisponible, ...]:
    """Las pistas del archivo, despachando por extension (sin distinguir mayusculas).

    Una tablatura de texto devuelve una sola pista, la numero 1.
    """
    return _LECTORES[_extension(ruta, _LECTORES)](ruta)


def importar(
    ruta: Path | str, numero_pista: int, perfil_clave: str | None = None
) -> Pieza:
    """La pista `numero_pista` (empezando en 1) del archivo, como `Pieza`.

    `perfil_clave` solo cuenta donde el archivo no trae afinacion (MIDI, MusicXML sin
    tablatura, texto); en Guitar Pro manda la del archivo.
    """
    return _CONVERSORES[_extension(ruta, _CONVERSORES)](
        ruta, numero_pista, perfil_clave
    )
