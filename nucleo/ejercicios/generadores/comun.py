"""Lo que comparten los generadores de ejercicios.

Escalas y arpegios se generan igual: mismo mastil, misma interseccion, misma
secuenciacion. Lo unico que cambia es el patron. Extraerlo aqui evita dos
archivos casi identicos que habria que corregir en pareja para siempre.

Aqui vive tambien el muestreo de las dos familias que eligen al azar (lectura e
intervalos), por la misma razon: las dos tienen que respetar la misma regla de
no producir dos notas iguales seguidas.
"""

from collections.abc import Sequence

import numpy as np

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


def elegir_sin_repetir_adyacentes(
    generador: np.random.Generator, candidatas: Sequence[int], cuantas: int
) -> list[int]:
    """Muestrea `cuantas` candidatas con reemplazo pero sin dos iguales seguidas.

    Muestreo por rechazo: se pide un valor al azar y, si coincide con el
    anterior, se descarta y se vuelve a pedir. La semilla se respeta igual que
    antes (el mismo `Generator` produce el mismo ejercicio), aunque la secuencia
    ya no es la que daba `choice(..., replace=True)`: los rechazos consumen
    numeros del generador.

    Por que no basta con que sea mas variado: dos notas iguales seguidas
    producen un ejercicio que el evaluador **no puede terminar**. Al repicar la
    misma nota el tono sigue siendo creible, asi que nunca se acumulan los
    `cuadros_para_olvidar_nota` cuadros sin nota creible que liberan
    `_ultima_nota_resuelta`, y ninguno de los dos caminos de disparo vuelve a
    contar esa nota (ver la limitacion documentada en `EvaluadorEjercicio`).

    Con una sola candidata la repeticion es inevitable: en ese caso se deja
    pasar el duplicado en vez de girar para siempre en el rechazo. Es el unico
    resultado de esta funcion que contiene valores iguales adyacentes, y ocurre
    solo cuando el mastil ofrece exactamente una nota alcanzable.
    """
    opciones = [int(valor) for valor in candidatas]
    if not opciones:
        raise ValueError("No hay ninguna candidata que muestrear")
    if len(opciones) == 1:
        return opciones * cuantas

    elegidas: list[int] = []
    anterior: int | None = None
    for _ in range(cuantas):
        valor = anterior
        while valor == anterior:
            valor = int(generador.choice(opciones))
        elegidas.append(valor)
        anterior = valor
    return elegidas


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
