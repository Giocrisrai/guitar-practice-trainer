"""Lo que comparten todos los generadores que recorren un patron por el mastil.

Escalas y arpegios se generan igual: mismo mastil, misma interseccion, misma
secuenciacion. Lo unico que cambia es el patron. Extraerlo aqui evita dos
archivos casi identicos que habria que corregir en pareja para siempre.
"""

from nucleo.afinaciones import PERFILES, PerfilAfinacion
from nucleo.ejercicios.teoria import clases_del_patron, notas_alcanzables
from nucleo.musica import Posicion

DIRECCIONES: tuple[str, ...] = ("ascendente", "descendente", "ambas")


def validar_parametros(perfil_clave: str, direccion: str) -> PerfilAfinacion:
    """Comprueba perfil y direccion, y devuelve el perfil resuelto."""
    if perfil_clave not in PERFILES:
        disponibles = ", ".join(sorted(PERFILES))
        raise ValueError(f"El perfil '{perfil_clave}' no existe. Opciones: {disponibles}")
    if direccion not in DIRECCIONES:
        disponibles = ", ".join(DIRECCIONES)
        raise ValueError(f"La direccion '{direccion}' no existe. Opciones: {disponibles}")
    return PERFILES[perfil_clave]


def notas_del_patron_en_mastil(
    perfil: PerfilAfinacion,
    raiz_midi: int,
    patron: tuple[int, ...],
    traste_minimo: int,
    traste_maximo: int,
) -> tuple[list[int], dict[int, tuple[Posicion, ...]]]:
    """Notas del patron que caen en el rango de trastes, y donde tocarlas.

    Devuelve la lista de numeros MIDI ordenada de grave a aguda y el diccionario
    completo de posiciones alcanzables, que el generador necesita para rellenar
    cada NotaEsperada.
    """
    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    clases = clases_del_patron(raiz_midi, patron)
    midis = sorted(midi for midi in alcanzables if midi % 12 in clases)
    return midis, alcanzables


def secuenciar(midis: list[int], direccion: str) -> list[int]:
    """Ordena las notas segun la direccion pedida.

    "ambas" sube y baja sin repetir la nota mas aguda: do re mi fa sol fa mi re
    do. Repetir la cumbre suena mal y descuadra la cuenta de notas.
    """
    if direccion == "ascendente":
        return list(midis)
    if direccion == "descendente":
        return list(midis[::-1])
    return list(midis) + list(midis[-2::-1])
