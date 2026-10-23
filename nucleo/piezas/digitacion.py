"""Donde se toca cada nota: el camino de coste minimo sobre el mastil.

Una nota vive en hasta seis sitios de una guitarra. Elegir el sitio de cada una es
elegir UN camino entre capas: una capa por nota, y el coste de cada arista es lo que
cuesta mover la mano de una a otra.

Un nodo no es solo una posicion: es **una posicion y el traste donde esta la mano**,
que aqui se llama el *ancla*. Sin el ancla no hay forma de distinguir las dos cosas
que la mano puede hacer, y son distintas:

- **Mover la mano** por el mastil. Es legitimo, es lo caro, y permite cualquier salto:
  un Fa2, que solo vive en el primer traste de la sexta, seguido de un Si4, que no
  baja del septimo de la primera, lo toca cualquiera desplazando la mano.
- **Estirar los dedos** dentro de una misma posicion de la mano. Eso si tiene un
  limite humano, y pasado el limite no es caro: es imposible.

Con el ancla en el estado el limite se expresa donde le corresponde: una nota pisada
en el traste f obliga a que el ancla cumpla `ancla <= f <= ancla + estiramiento_maximo`,
y los estados que no lo cumplen no existen. Una cuerda al aire no obliga a nada: suena
sola, asi que no dice donde esta la mano. Y como la mano siempre puede moverse,
**entre dos notas cualesquiera hay siempre al menos una arista**: el grafo nunca se
queda sin camino y ningun coste es infinito.

Se resuelve por programacion dinamica, que aqui da el MINIMO EXACTO y no una
aproximacion: con k <= 6 posiciones por nota y T = trastes + 1 anclas, el coste es
O(n·k²·T²), que para mil notas son milisegundos. Es la diferencia con la heuristica de
`desde_ejercicio.py`, que mira una nota hacia atras y ninguna hacia delante y esta
documentada como provisional.

Sobre la acotacion de las anclas: se usan **todos** los trastes del perfil, de 0 a
`perfil.trastes`, y no solo los que alguna nota obliga. Son 23 valores en una guitarra,
la rejilla es uniforme (lo que mantiene la aritmetica del movimiento trivial) y evita
tener que demostrar que un subconjunto de anclas basta para contener el optimo. Si
alguna vez estorba, el conjunto se puede recortar a los extremos de los intervalos
`[f - estiramiento_maximo, f]` de las notas de la pieza, que es donde un optimo siempre
puede colocarse; el algoritmo no cambia.

Los pesos viven en `CosteDigitacion` y son DATOS: si una digitacion sale incomoda se
cambia un numero, no el algoritmo. **No estan medidos tocando**, igual que los demas
umbrales del proyecto: estan razonados (mover la mano por el mastil cuesta mucho mas
que cruzar una cuerda con los dedos, y una cuerda al aire no cuesta nada) y habra que
corregirlos con la guitarra en las manos.
"""

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
    estiramiento_maximo: trastes que los dedos abarcan sin mover la mano. Una nota
        pisada mas alla de eso no es cara, es imposible, y su estado no existe.

    Los tres pesos se suponen no negativos; con pesos negativos "minimo" dejaria de
    significar "mas comodo".
    """

    por_traste: float = 1.0
    por_cuerda: float = 0.3
    al_aire: float = 0.0
    estiramiento_maximo: int = 5


def _anclas(perfil: PerfilAfinacion) -> np.ndarray:
    """Los trastes donde la mano puede estar: todos los del perfil."""
    return np.arange(perfil.trastes + 1, dtype=np.float64)


def _estados_validos(
    posiciones: list[Posicion], anclas: np.ndarray, coste: CosteDigitacion
) -> np.ndarray:
    """Matriz (len(posiciones) × len(anclas)) de que estados existen.

    Una nota pisada en el traste f solo existe con la mano en un ancla que la alcance
    sin estirar los dedos mas de lo humano:

        ancla <= f <= ancla + estiramiento_maximo

    Una cuerda al aire existe con la mano en cualquier parte: no hay dedo que estirar.
    """
    trastes = np.array([p.traste for p in posiciones], dtype=np.float64)[:, None]
    al_aire = trastes == 0.0
    alcanzable = (anclas[None, :] <= trastes) & (
        trastes <= anclas[None, :] + coste.estiramiento_maximo
    )
    return al_aire | alcanzable


def _coste_de_salida(
    posiciones: list[Posicion], anclas: np.ndarray, coste: CosteDigitacion
) -> np.ndarray:
    """Lo que cuesta empezar la pieza en cada estado de la primera nota.

    La mano empieza en la cejuela, asi que llevarla al ancla a cuesta `por_traste·a`.
    No hay cuerda anterior, asi que no se cruza ninguna; y una cuerda al aire cuesta
    `al_aire`, es decir nada.
    """
    extra = np.array(
        [coste.al_aire if p.traste == 0 else 0.0 for p in posiciones],
        dtype=np.float64,
    )[:, None]
    return coste.por_traste * anclas[None, :] + extra


def _coste_entre_posiciones(
    previas: list[Posicion], actuales: list[Posicion], coste: CosteDigitacion
) -> np.ndarray:
    """Matriz (len(previas) × len(actuales)) de lo que cuesta la nota, sin la mano.

    Es la parte del coste que no depende del ancla: cruzar de cuerda cuesta
    `por_cuerda`, y llegar a una cuerda al aire cuesta `al_aire` y nada mas, porque la
    cuerda suena sola. El movimiento de la mano se suma aparte, en `_camino_minimo`,
    porque solo depende de las anclas.
    """
    cuerda_previa = np.array([p.cuerda for p in previas])[:, None]
    cuerda_actual = np.array([p.cuerda for p in actuales])[None, :]
    traste_actual = np.array([p.traste for p in actuales])[None, :]

    cruza = cuerda_actual != cuerda_previa
    costes = np.where(cruza, float(coste.por_cuerda), 0.0)
    return np.where(traste_actual == 0, float(coste.al_aire), costes)


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


def _camino_minimo(
    capas: list[list[Posicion]], perfil: PerfilAfinacion, coste: CosteDigitacion
) -> tuple[float, list[int]]:
    """El coste minimo y el indice de la posicion elegida en cada capa.

    La unica implementacion de la programacion dinamica, y la usan tanto `digitar`
    como `coste_total`: si se separasen, la desigualdad que vigila el algoritmo
    compararia dos cosas distintas y no significaria nada.

    El estado es el par (posicion, ancla), aplanado a un solo indice `p · T + a` para
    que la transicion entre dos capas sea una sola matriz de numpy. El coste de esa
    transicion se separa en dos sumandos independientes —el movimiento del ancla, que
    no depende de las posiciones, y el coste de la nota, que no depende de las anclas—
    asi que la matriz grande se arma por broadcasting de las dos pequenas.
    """
    anclas = _anclas(perfil)
    total_anclas = len(anclas)
    movimiento = coste.por_traste * np.abs(anclas[:, None] - anclas[None, :])

    salida = _coste_de_salida(capas[0], anclas, coste)
    validos = _estados_validos(capas[0], anclas, coste)
    acumulado = np.where(validos, salida, np.inf).reshape(-1)
    predecesores: list[np.ndarray] = []

    for previas, actuales in zip(capas[:-1], capas[1:], strict=True):
        nota = _coste_entre_posiciones(previas, actuales, coste)
        transicion = (
            nota[:, None, :, None] + movimiento[None, :, None, :]
        ).reshape(len(previas) * total_anclas, len(actuales) * total_anclas)

        candidatos = acumulado[:, None] + transicion
        validos = _estados_validos(actuales, anclas, coste).reshape(-1)
        candidatos = np.where(validos[None, :], candidatos, np.inf)

        elegidos = candidatos.argmin(axis=0)
        acumulado = candidatos[elegidos, np.arange(candidatos.shape[1])]
        predecesores.append(elegidos)

    estado = int(acumulado.argmin())
    minimo = float(acumulado[estado])
    estados = [estado]
    for elegidos in reversed(predecesores):
        estados.append(int(elegidos[estados[-1]]))
    estados.reverse()
    return minimo, [estado // total_anclas for estado in estados]


def digitar(
    midis: list[int],
    perfil: PerfilAfinacion,
    coste: CosteDigitacion = CosteDigitacion(),
) -> tuple[Posicion, ...]:
    """La digitacion de coste minimo de una secuencia de notas.

    Recorre las capas acumulando, para cada estado (posicion, ancla), el coste minimo
    con que se puede llegar a el y de donde se llego; al final reconstruye el camino
    hacia atras desde el mejor estado de la ultima capa.

    El minimo es exacto, no una aproximacion: el coste es aditivo a lo largo del
    camino y no negativo, asi que el optimo de un prefijo forma parte del optimo
    global, que es justo lo que la programacion dinamica necesita.

    Lanza `ValueError` nombrando la nota si alguna no existe en el mastil del perfil.
    """
    capas = _capas(midis, perfil)
    if not capas:
        return ()
    _, elegidas = _camino_minimo(capas, perfil, coste)
    return tuple(capa[indice] for capa, indice in zip(capas, elegidas, strict=True))


def coste_total(
    posiciones: tuple[Posicion, ...],
    perfil: PerfilAfinacion,
    coste: CosteDigitacion = CosteDigitacion(),
) -> float:
    """Lo que cuesta una digitacion ya elegida, con la misma aritmetica que `digitar`.

    Las posiciones vienen dadas, pero las anclas no: una misma secuencia de posiciones
    se puede tocar con la mano en varios sitios, y lo que cuesta es tocarla de la
    mejor manera posible. Asi que esto es `_camino_minimo` sobre las mismas capas con
    una sola posicion cada una: la misma funcion de coste, el mismo codigo, y la
    minimizacion reducida a las anclas. Necesita el perfil precisamente para eso,
    porque las anclas son trastes del instrumento.

    Es la vara de medir de la prueba de la desigualdad: `digitar` minimiza sobre las
    posiciones **y** las anclas, asi que su coste medido aqui es menor o igual que el
    de cualquier otra eleccion de posiciones. Comparar con otra funcion de coste no
    demostraria nada, y por eso las dos pasan por `_camino_minimo`.
    """
    if not posiciones:
        return 0.0
    minimo, _ = _camino_minimo([[p] for p in posiciones], perfil, coste)
    return minimo
