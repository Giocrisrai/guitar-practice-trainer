"""Piezas escritas EN CODIGO para que el gemelo tenga algo que tocar.

Ningun archivo con derechos de autor entra al repositorio, asi que las piezas de
prueba se construyen aqui, nota a nota. No son musica: son casos. Cada una existe
para que una prueba pueda nombrar lo que comprueba -el acorde, la nota repetida,
el tramo vacio- sin tener que montar la pieza dentro de la prueba y sin que dos
pruebas monten dos versiones distintas de lo mismo.

La digitacion (cuerda y traste de cada nota) no se escribe a mano: se pide a
`nucleo.piezas.digitacion.digitar`, que es el mismo codigo de produccion que
digita una cancion importada. Escribirla a mano seria inventar un dato que el
proyecto ya sabe calcular, y ademas mal: a mano salen saltos de mastil que ningun
guitarrista haria.
"""

from nucleo.afinaciones import PERFILES
from nucleo.piezas.digitacion import digitar
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion

PERFIL = "guitarra_estandar"

# Una escala de sol mayor subiendo, en la zona donde el detector de tono trabaja
# mas comodo (G3 a G4): lo bastante aguda para que la ventana de analisis coja
# varios periodos y lo bastante grave para quedarse en las tres primeras cuerdas.
ESCALA = (55, 57, 59, 60, 62, 64, 65, 67)

# La melodia del escaparate: cuatro frases de doce pulsos, una por seccion. No
# hay dos notas consecutivas iguales a proposito, porque el veredicto excluye las
# repetidas y una demostracion con exclusiones se lee peor.
FRASES = (
    ("Intro", (55, 57, 59, 60, 62, 60, 59, 57, 55, 57, 59, 55)),
    ("Tema", (60, 62, 64, 65, 67, 65, 64, 62, 60, 64, 67, 64)),
    ("Puente", (57, 59, 60, 62, 64, 62, 60, 59, 57, 60, 62, 59)),
    ("Final", (55, 59, 62, 64, 67, 64, 62, 59, 55, 60, 59, 55)),
)


def _notas(
    midis: tuple[int, ...],
    inicios: tuple[float, ...],
    duraciones: tuple[float, ...] | None = None,
) -> tuple[NotaEnPieza, ...]:
    """Monta las notas digitando la secuencia con el codigo de produccion."""
    posiciones = digitar(list(midis), PERFILES[PERFIL])
    if duraciones is None:
        duraciones = (1.0,) * len(midis)
    return tuple(
        NotaEnPieza(
            midi=midi,
            cuerda=posicion.cuerda,
            traste=posicion.traste,
            inicio_pulsos=inicio,
            duracion_pulsos=duracion,
        )
        for midi, posicion, inicio, duracion in zip(
            midis, posiciones, inicios, duraciones, strict=True
        )
    )


def escala_de_ocho_notas(tempo: int = 100) -> Pieza:
    """Ocho notas, una por pulso, dos compases de 4/4.

    Es la pieza por defecto de la etapa: dos compases exactos para poder pedir
    «solo el segundo», y una nota por pulso para que el instante de cada nota se
    pueda calcular de cabeza en una prueba.
    """
    return Pieza(
        nombre="Escala de ocho notas",
        perfil=PERFIL,
        tempo=tempo,
        compas=(4, 4),
        notas=_notas(ESCALA, tuple(float(indice) for indice in range(8))),
    )


def pieza_con_acorde(tempo: int = 100) -> Pieza:
    """Un compas de 4/4 con DOS notas en el segundo pulso.

    El modelo admite acordes porque los archivos de verdad los traen; el gemelo
    no sabe tocarlos y los reduce a la nota mas grave. Esta pieza es la que
    comprueba esa reduccion.
    """
    midis = (55, 60, 64, 62)
    inicios = (0.0, 1.0, 1.0, 2.0)
    return Pieza(
        nombre="Pieza con un acorde",
        perfil=PERFIL,
        tempo=tempo,
        compas=(4, 4),
        notas=_notas(midis, inicios),
    )


def pieza_con_nota_repetida(tempo: int = 100) -> Pieza:
    """Un compas de 4/4 cuyas dos primeras notas son la misma altura.

    `DetectorPulsaciones` declara que no distingue dos pulsaciones seguidas de la
    misma nota sin un hueco de tres cuadros sin nota creible, asi que el veredicto
    las excluye. Esta pieza es la que deja comprobar esa exclusion.
    """
    midis = (59, 59, 62, 64)
    inicios = (0.0, 1.0, 2.0, 3.0)
    return Pieza(
        nombre="Pieza con una nota repetida",
        perfil=PERFIL,
        tempo=tempo,
        compas=(4, 4),
        notas=_notas(midis, inicios),
    )


def pieza_vacia(tempo: int = 100) -> Pieza:
    """Una pieza sin ninguna nota.

    No es un caso absurdo: un compas vacio de una cancion de verdad llega aqui
    igual, y la cadena entera tiene que tragarlo sin lanzar. Lo que el gemelo
    devuelve es audio en silencio, no un audio de longitud cero.
    """
    return Pieza(
        nombre="Pieza vacia",
        perfil=PERFIL,
        tempo=tempo,
        compas=(4, 4),
        notas=(),
    )


def pieza_de_demostracion(tempo: int = 92) -> Pieza:
    """La pieza del escaparate: unos 31 s, cuatro secciones con nombre.

    Cuarenta y ocho notas, una por pulso, en doce compases de 4/4 repartidos en
    cuatro secciones de tres compases. Lleva secciones porque la demostracion
    practica POR SECCIONES, y una pieza sin marcadores no deja probar eso.
    """
    midis: list[int] = []
    secciones: list[Seccion] = []
    for indice, (nombre, frase) in enumerate(FRASES):
        secciones.append(Seccion(nombre=nombre, inicio_pulsos=float(indice * 12)))
        midis.extend(frase)
    return Pieza(
        nombre="Demostracion del gemelo",
        perfil=PERFIL,
        tempo=tempo,
        compas=(4, 4),
        notas=_notas(
            tuple(midis), tuple(float(indice) for indice in range(len(midis)))
        ),
        secciones=tuple(secciones),
    )
