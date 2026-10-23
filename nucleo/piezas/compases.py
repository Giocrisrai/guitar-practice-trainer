"""Pulsos a compases, y al reves. El unico sitio del proyecto que hace esta cuenta.

Lo necesitan cuatro cosas a la vez -la rejilla de la interfaz, el rango del
bucle, el acento del metronomo y el informe por compases-, y una cuenta repetida
en cuatro sitios es una cuenta que se arregla en tres.

LIMITE DECLARADO: `Pieza` guarda UN SOLO compas, el del principio, porque los
lectores de la etapa 3b se quedaron con el primero y avisan con
`Pieza.compas_variable`. Con un 3/4 en medio de un 4/4, las barras caen mal desde
el cambio hasta el final. Este modulo NO lo arregla -haria falta guardar los
cambios en el modelo, que es tocar los cuatro lectores-: quien dibuje encima
tiene que mostrar ese aviso. Fingir precision aqui seria peor que no tener
rejilla.
"""

import math

from nucleo.piezas.modelo import Pieza


def pulsos_por_compas(pieza: Pieza) -> float:
    """Cuantos pulsos ocupa un compas de esta pieza.

    El pulso lo define el DENOMINADOR del compas, no un 4 fijo: `Pieza.tempo`
    esta en pulsos por minuto, y en 7/8 el pulso es la corchea, asi que el compas
    son 7 corcheas = 3,5 negras. Devolver 7 aqui pondria las barras al doble de
    distancia de donde van.
    """
    numerador, denominador = pieza.compas
    return numerador * 4.0 / denominador


def total_de_compases(pieza: Pieza) -> int:
    """Cuantos compases ocupa la pieza, contando desde 1.

    El ultimo compas incompleto CUENTA: nueve pulsos en 4/4 son tres compases, y
    el tercero es un compas de verdad con una negra y tres silencios. Casi
    cualquier cancion de verdad acaba asi.
    """
    if len(pieza) == 0:
        return 0
    return max(1, math.ceil(pieza.duracion_pulsos / pulsos_por_compas(pieza)))


def compas_en(pieza: Pieza, pulsos: float) -> int:
    """En que compas cae ese pulso. El primero es el 1, como cuentan los musicos.

    En una pieza sin notas devuelve 1: no hay compas donde caer, y 1 es el unico
    numero que no miente sobre el sitio del cabezal.
    """
    if pulsos <= 0:
        return 1
    return int(pulsos // pulsos_por_compas(pieza)) + 1


def pulsos_del_compas(pieza: Pieza, numero: int) -> tuple[float, float]:
    """[inicio, fin) en pulsos del compas `numero`.

    Medio abierto a proposito: el pulso 4 en 4/4 es el primero del compas 2, no el
    ultimo del 1, y asi dos compases consecutivos no se solapan en una nota.
    """
    total = total_de_compases(pieza)
    if numero < 1 or numero > total:
        raise ValueError(
            f"La pieza '{pieza.nombre}' no tiene compas {numero}: "
            f"va del 1 al {total}"
        )
    ancho = pulsos_por_compas(pieza)
    return ((numero - 1) * ancho, numero * ancho)


def compases_de_la_seccion(pieza: Pieza, indice: int) -> tuple[int, int]:
    """Primer y ultimo compas de la seccion `indice`, para armar el bucle con ella.

    Se pide por INDICE y no por nombre: `Seccion` solo guarda `nombre` e
    `inicio_pulsos`, y los nombres se repiten -una cancion con dos estribillos
    trae dos secciones llamadas "Estribillo"-, asi que pedirla por nombre
    obligaria a elegir una de las dos en silencio.

    Y como `Seccion` NO guarda donde acaba, el ultimo compas de una seccion es el
    anterior al comienzo de la siguiente, o el ultimo de la pieza si es la ultima.
    """
    if indice < 0 or indice >= len(pieza.secciones):
        raise ValueError(
            f"La pieza '{pieza.nombre}' no tiene seccion {indice}: "
            f"tiene {len(pieza.secciones)}"
        )
    primero = compas_en(pieza, pieza.secciones[indice].inicio_pulsos)
    if indice + 1 < len(pieza.secciones):
        siguiente = pieza.secciones[indice + 1].inicio_pulsos
        ultimo = max(primero, compas_en(pieza, siguiente) - 1)
    else:
        ultimo = max(primero, total_de_compases(pieza))
    return (primero, ultimo)
