"""Lo que los lectores de archivos comparten.

Cada formato -Guitar Pro, MusicXML, MIDI, tablatura de texto- tiene su propio
modulo y ninguno importa a los otros. Lo unico comun es como se DESCRIBE una pista
antes de convertirla: el usuario tiene que poder elegir cual importa, y para eso le
hace falta ver todas, incluidas las que no se pueden usar y por que.
"""

from dataclasses import dataclass

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
