"""Registro de los módulos de la aplicación.

Un módulo es una pantalla con su propósito. El afinador es el primero; las etapas
siguientes añadirán ejercicios, canciones, grabación y efectos. Que la interfaz los
descubra aquí en vez de tenerlos escritos a mano es lo que permite añadir uno nuevo
sin tocar el armazón.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Modulo:
    """Una pantalla de la aplicación.

    disponible en False permite anunciar un módulo futuro sin que se pueda abrir.
    """

    clave: str
    nombre: str
    descripcion: str
    icono: str
    disponible: bool = True

    def a_dict(self) -> dict:
        return asdict(self)


_MODULOS: dict[str, Modulo] = {}


def registrar_modulo(modulo: Modulo) -> None:
    """Añade un módulo al registro, sustituyendo el anterior con esa clave."""
    _MODULOS[modulo.clave] = modulo


def obtener_modulo(clave: str) -> Modulo:
    """Devuelve un módulo por clave. Lanza KeyError si no existe."""
    if clave not in _MODULOS:
        disponibles = ", ".join(sorted(_MODULOS)) or "ninguno"
        raise KeyError(f"No existe el módulo '{clave}'. Disponibles: {disponibles}")
    return _MODULOS[clave]


def listar_modulos() -> list[Modulo]:
    """Módulos registrados, ordenados por clave."""
    return [_MODULOS[clave] for clave in sorted(_MODULOS)]


registrar_modulo(
    Modulo(
        clave="afinador",
        nombre="Afinador",
        descripcion="Afina tu instrumento y mira qué notas tocas en el mástil",
        icono="🎸",
    )
)

registrar_modulo(
    Modulo(
        clave="ejercicios",
        nombre="Ejercicios",
        descripcion="Escalas, arpegios, intervalos y lectura del mástil, con corrección",
        icono="🎯",
    )
)

registrar_modulo(
    Modulo(
        clave="carril",
        nombre="Carril",
        descripcion="Las notas vienen hacia ti: toca cuando llegan",
        icono="🛣️",
    )
)
