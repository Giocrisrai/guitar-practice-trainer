"""Teoria musical como patrones sobre Z12.

Una escala no es una lista de notas: es un subconjunto de Z12, el conjunto de las
doce clases de altura modulo la octava. La escala mayor es {0,2,4,5,7,9,11}
medida en semitonos desde su raiz, y transportarla a otra tonalidad es sumar
modulo 12.

Esa abstraccion es lo que hace trivial el resto: generar "Sol mayor en la quinta
posicion" son dos operaciones de conjuntos, transportar el patron e intersecar
con lo que el mastil alcanza. Sin ella, cada escala en cada tonalidad en cada
posicion seria una tabla escrita a mano.
"""

from nucleo.afinaciones import PerfilAfinacion
from nucleo.musica import Posicion, frecuencia_a_midi

# Patrones de escala en semitonos desde la raiz. Anadir la dorica es anadir una
# linea: (0, 2, 3, 5, 7, 9, 10).
ESCALAS: dict[str, tuple[int, ...]] = {
    "mayor": (0, 2, 4, 5, 7, 9, 11),
    "menor_natural": (0, 2, 3, 5, 7, 8, 10),
    "pentatonica_mayor": (0, 2, 4, 7, 9),
    "pentatonica_menor": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
}

# Acordes como patrones de intervalos desde la fundamental.
ACORDES: dict[str, tuple[int, ...]] = {
    "mayor": (0, 4, 7),
    "menor": (0, 3, 7),
    "septima": (0, 4, 7, 10),
    "menor_septima": (0, 3, 7, 10),
}

INTERVALOS: dict[str, int] = {
    "unisono": 0,
    "segunda_menor": 1,
    "segunda_mayor": 2,
    "tercera_menor": 3,
    "tercera_mayor": 4,
    "cuarta_justa": 5,
    "tritono": 6,
    "quinta_justa": 7,
    "sexta_menor": 8,
    "sexta_mayor": 9,
    "septima_menor": 10,
    "septima_mayor": 11,
    "octava": 12,
}

NOMBRES_INTERVALOS: dict[int, str] = {
    0: "unisono",
    1: "segunda menor",
    2: "segunda mayor",
    3: "tercera menor",
    4: "tercera mayor",
    5: "cuarta justa",
    6: "tritono",
    7: "quinta justa",
    8: "sexta menor",
    9: "sexta mayor",
    10: "septima menor",
    11: "septima mayor",
    12: "octava",
}


def clases_del_patron(raiz_midi: int, patron: tuple[int, ...]) -> frozenset[int]:
    """Clases de altura del patron transportado a una raiz.

        clases = { (raiz + p) mod 12 : p en patron }

    La octava de la raiz es irrelevante: Do3 y Do4 producen el mismo conjunto,
    porque una clase de altura ignora en que octava suena la nota.
    """
    return frozenset((raiz_midi + paso) % 12 for paso in patron)


def notas_del_patron(
    raiz_midi: int, patron: tuple[int, ...], midi_minimo: int, midi_maximo: int
) -> tuple[int, ...]:
    """Notas concretas del patron dentro de un rango, ordenadas de grave a aguda.

    A diferencia de clases_del_patron, aqui si importa la octava: se devuelven
    numeros MIDI, no clases.
    """
    clases = clases_del_patron(raiz_midi, patron)
    return tuple(midi for midi in range(midi_minimo, midi_maximo + 1) if midi % 12 in clases)


def notas_alcanzables(
    perfil: PerfilAfinacion, traste_minimo: int, traste_maximo: int
) -> dict[int, tuple[Posicion, ...]]:
    """Notas que el mastil alcanza en un rango de trastes, con donde tocarlas.

    Devuelve un diccionario de numero MIDI a las posiciones que lo producen. Un
    mismo MIDI aparece varias veces —la ambiguedad del mastil que ya conocemos
    del afinador— y por eso el valor es una tupla, no una posicion suelta.

    Las posiciones van de la cuerda mas grave a la mas aguda, el mismo orden en
    que se dibuja el mastil.
    """
    limite_superior = min(traste_maximo, perfil.trastes)
    alcanzables: dict[int, list[Posicion]] = {}
    for cuerda in perfil.cuerdas:
        midi_al_aire = round(frecuencia_a_midi(cuerda.frecuencia))
        for traste in range(max(0, traste_minimo), limite_superior + 1):
            midi = midi_al_aire + traste
            alcanzables.setdefault(midi, []).append(Posicion(cuerda=cuerda.numero, traste=traste))
    return {
        midi: tuple(sorted(posiciones, key=lambda p: -p.cuerda))
        for midi, posiciones in alcanzables.items()
    }


def nombre_de_intervalo(semitonos: int) -> str:
    """Nombre en castellano de un intervalo, reducido a una octava.

    Una decima mayor (16 semitonos) se nombra como su tercera mayor equivalente:
    el nombre describe la relacion, no la distancia absoluta.
    """
    if semitonos == 12:
        return NOMBRES_INTERVALOS[12]
    return NOMBRES_INTERVALOS[semitonos % 12]
