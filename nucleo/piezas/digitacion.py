"""Donde se toca cada nota: el camino de coste minimo sobre el mastil.

Una nota vive en hasta seis sitios de una guitarra. Elegir el sitio de cada una es
elegir UN camino entre capas: una capa por nota, un nodo por posicion alcanzable, y
el coste de cada arista es lo que cuesta mover la mano de una a otra.

Se resuelve por programacion dinamica, que aqui da el MINIMO EXACTO y no una
aproximacion: con k <= 6 posiciones por nota, el coste es O(n·k²). Es la diferencia
con la heuristica de `desde_ejercicio.py`, que mira una nota hacia atras y ninguna
hacia delante y esta documentada como provisional.

Los pesos viven en `CosteDigitacion` y son DATOS: si una digitacion sale incomoda se
cambia un numero, no el algoritmo. **No estan medidos tocando**, igual que los demas
umbrales del proyecto: estan razonados (mover la mano por el mastil cuesta mucho mas
que cruzar una cuerda con los dedos, y una cuerda al aire no cuesta nada) y habra que
corregirlos con la guitarra en las manos.

El estiramiento maximo PROHIBE, no encarece: si entre dos notas seguidas hay mas
trastes de los que los dedos abarcan, esa arista no existe. Modelarla como un coste
alto seria peor que no modelarla, porque el algoritmo la elegiria en cuanto le
conviniera y escupiria una digitacion que nadie puede tocar.

Y como el grafo puede quedarse sin ninguna arista posible (un Sol#2, que solo vive en
el cuarto traste de la sexta, seguido de un Re5, que no baja del traste diez: la
musica obliga), la programacion dinamica minimiza el par **(estiramientos imposibles,
coste)** en orden lexicografico. Mientras exista una digitacion tocable, ninguna con
un estiramiento imposible puede ganarle, por barata que sea: eso es exactamente "la
arista no existe". Y cuando no existe ninguna tocable, en vez de reventar se devuelve
la que menos veces pide lo imposible, y `coste_total` la delata con `inf`.
"""

import math
from dataclasses import dataclass

import numpy as np

from nucleo.afinaciones import PerfilAfinacion
from nucleo.musica import Posicion, nombre_de_midi, posiciones_en_mastil


@dataclass(frozen=True)
class CosteDigitacion:
    """Lo que cuesta cada cosa que la mano puede hacer.

    por_traste: mover la mano un traste a lo largo del mastil. Es el movimiento caro.
    por_cuerda: cambiar de cuerda sin mover la mano. Barato: lo hacen los dedos.
    al_aire: llegar a una cuerda al aire no cuesta nada, venga la mano de donde venga.
    estiramiento_maximo: mas trastes que esto entre dos notas seguidas sin mover la
        mano no es caro, es imposible, asi que esa arista no existe.

    Los tres pesos se suponen no negativos; con pesos negativos "minimo" dejaria de
    significar "mas comodo" y el orden lexicografico perderia sentido.
    """

    por_traste: float = 1.0
    por_cuerda: float = 0.3
    al_aire: float = 0.0
    estiramiento_maximo: int = 5


def _coste_de_salida(posiciones: list[Posicion], coste: CosteDigitacion) -> np.ndarray:
    """Lo que cuesta empezar la pieza en cada posicion de la primera nota.

    La mano empieza en la cejuela, asi que llegar al traste f cuesta `por_traste·f` y
    una cuerda al aire cuesta `al_aire`, es decir nada. Nada prohibe nada aqui: no hay
    nota anterior de la que estirarse.
    """
    trastes = np.array([p.traste for p in posiciones], dtype=np.float64)
    return np.where(trastes == 0.0, coste.al_aire, coste.por_traste * trastes)


def _costes_entre_capas(
    previas: list[Posicion], actuales: list[Posicion], coste: CosteDigitacion
) -> tuple[np.ndarray, np.ndarray]:
    """Matrices (len(previas) × len(actuales)) de coste y de imposibilidad.

    Es la unica funcion que sabe lo que cuesta pasar de una posicion a otra, y la usan
    tanto `digitar` como `coste_total`: si se separasen, la desigualdad que vigila el
    algoritmo compararia dos cosas distintas y no significaria nada.

        coste(a → b) = por_traste·|traste_b − traste_a| + por_cuerda·|cuerda_b − cuerda_a|

    con dos excepciones, ambas sobre las cuerdas al aire:

    - Llegar al aire cuesta `al_aire` y nada mas: la mano no tiene que ir a ningun
      sitio, la cuerda suena sola.
    - El estiramiento solo se mide entre dos notas pisadas. Una cuerda al aire no dice
      donde esta la mano, asi que no puede estirarla ni prohibir nada.
    """
    traste_previo = np.array([p.traste for p in previas], dtype=np.float64)[:, None]
    cuerda_previa = np.array([p.cuerda for p in previas], dtype=np.float64)[:, None]
    traste_actual = np.array([p.traste for p in actuales], dtype=np.float64)[None, :]
    cuerda_actual = np.array([p.cuerda for p in actuales], dtype=np.float64)[None, :]

    salto = np.abs(traste_actual - traste_previo)
    cruce = np.abs(cuerda_actual - cuerda_previa)
    costes = coste.por_traste * salto + coste.por_cuerda * cruce

    llega_al_aire = traste_actual == 0.0
    costes = np.where(llega_al_aire, float(coste.al_aire), costes)

    entre_pisadas = ~llega_al_aire & (traste_previo != 0.0)
    imposibles = entre_pisadas & (salto > coste.estiramiento_maximo)
    return costes, imposibles


def _capas(midis: list[int], perfil: PerfilAfinacion) -> list[list[Posicion]]:
    """Las posiciones alcanzables de cada nota, en orden.

    Una capa vacia significa que la nota no existe en este instrumento, y eso es un
    error del que llama, no algo que se pueda digitar de alguna manera.
    """
    capas = []
    for midi in midis:
        posiciones = list(posiciones_en_mastil(midi, perfil))
        if not posiciones:
            raise ValueError(
                f"La nota {nombre_de_midi(midi)} (midi {midi}) no se puede tocar en "
                f"{perfil.nombre}: no hay ninguna posicion en el mastil"
            )
        capas.append(posiciones)
    return capas


def digitar(
    midis: list[int],
    perfil: PerfilAfinacion,
    coste: CosteDigitacion = CosteDigitacion(),
) -> tuple[Posicion, ...]:
    """La digitacion de coste minimo de una secuencia de notas.

    Recorre las capas acumulando, para cada posicion, el mejor par (estiramientos
    imposibles, coste) con que se puede llegar a ella y de donde se llego. Al final
    reconstruye el camino hacia atras desde la mejor posicion de la ultima capa.

    El minimo es exacto, no una aproximacion: ambas componentes del par son aditivas y
    el orden lexicografico es monotono al sumarles cantidades no negativas, que es
    justo lo que la programacion dinamica necesita para que el optimo de un prefijo
    forme parte del optimo global.

    Lanza `ValueError` nombrando la nota si alguna no existe en el mastil del perfil.
    """
    capas = _capas(midis, perfil)
    if not capas:
        return ()

    acumulado_imposibles = np.zeros(len(capas[0]), dtype=np.int64)
    acumulado_coste = _coste_de_salida(capas[0], coste)
    predecesores: list[np.ndarray] = []

    for previas, actuales in zip(capas[:-1], capas[1:], strict=True):
        costes, imposibles = _costes_entre_capas(previas, actuales, coste)
        candidatos_imposibles = acumulado_imposibles[:, None] + imposibles
        candidatos_coste = acumulado_coste[:, None] + costes

        # Lexicografico sin numeros magicos: primero el minimo de imposibles por
        # columna, y el coste solo decide entre los caminos que lo alcanzan.
        minimo_imposibles = candidatos_imposibles.min(axis=0)
        coste_filtrado = np.where(
            candidatos_imposibles == minimo_imposibles, candidatos_coste, np.inf
        )
        elegidos = coste_filtrado.argmin(axis=0)

        acumulado_imposibles = minimo_imposibles
        acumulado_coste = coste_filtrado[elegidos, np.arange(len(actuales))]
        predecesores.append(elegidos)

    final = int(
        np.where(
            acumulado_imposibles == acumulado_imposibles.min(), acumulado_coste, np.inf
        ).argmin()
    )
    camino = [final]
    for elegidos in reversed(predecesores):
        camino.append(int(elegidos[camino[-1]]))
    camino.reverse()
    return tuple(capa[indice] for capa, indice in zip(capas, camino, strict=True))


def coste_total(posiciones: tuple[Posicion, ...], coste: CosteDigitacion) -> float:
    """Lo que cuesta una digitacion ya elegida, con la misma aritmetica que `digitar`.

    Devuelve `inf` si alguna pareja de notas seguidas pide un estiramiento imposible,
    porque esa arista no existe y un camino que la usa no tiene coste finito.

    Es la vara de medir de la prueba de la desigualdad: `digitar` devuelve un minimo,
    asi que su coste medido aqui tiene que ser menor o igual que el de cualquier otra
    eleccion sobre las mismas posiciones. Comparar con otra funcion de coste no
    demostraria nada, asi que las dos llaman a `_costes_entre_capas`.
    """
    if not posiciones:
        return 0.0

    total = float(_coste_de_salida([posiciones[0]], coste)[0])
    for previa, actual in zip(posiciones[:-1], posiciones[1:], strict=True):
        costes, imposibles = _costes_entre_capas([previa], [actual], coste)
        if bool(imposibles[0, 0]):
            return math.inf
        total += float(costes[0, 0])
    return total
