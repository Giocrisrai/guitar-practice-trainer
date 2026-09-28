"""El unico puente entre un ejercicio y una pieza.

Vive aparte del modelo a proposito: en la etapa 3b tendra al lado un
`desde_guitarpro.py` y un `desde_musicxml.py`, y `modelo.py` no tiene por que
enterarse de ninguno de los tres.
"""

from nucleo.ejercicios.modelo import Ejercicio
from nucleo.musica import Posicion, nombre_de_midi
from nucleo.piezas.modelo import NotaEnPieza, Pieza


def elegir_posicion(
    posiciones: tuple[Posicion, ...], traste_anterior: int | None
) -> Posicion:
    """Donde tocar una nota que vive en varios sitios del mastil.

    HEURISTICA LOCAL, y hay que decirlo: se queda con la posicion cuyo traste
    esta mas cerca del de la nota anterior, sin mirar lo que viene despues. Sobre
    una escala en una posicion acierta siempre, porque todas las notas caben en
    cuatro trastes. Sobre una pieza de verdad producira saltos absurdos: la
    eleccion correcta es la que minimiza el movimiento de la mano a lo largo de
    TODA la pieza, que es un camino de coste minimo y es trabajo de la etapa 3b.

    A igualdad de distancia gana la cuerda mas grave: en esa zona del mastil la
    nota suena mas llena y es donde la mano suele estar.
    """
    if not posiciones:
        raise ValueError("No hay ninguna posicion que elegir")
    if traste_anterior is None:
        return min(posiciones, key=lambda p: (p.traste, -p.cuerda))
    return min(posiciones, key=lambda p: (abs(p.traste - traste_anterior), -p.cuerda))


def pieza_desde_ejercicio(ejercicio: Ejercicio) -> Pieza:
    """Traduce un ejercicio a una pieza, acumulando los pulsos y fijando posicion."""
    notas: list[NotaEnPieza] = []
    inicio = 0.0
    traste_anterior: int | None = None
    for esperada in ejercicio.notas:
        if not esperada.posiciones:
            raise ValueError(
                f"La nota {nombre_de_midi(esperada.midi)} no tiene ninguna posicion "
                "alcanzable: el generador no deberia haberla producido"
            )
        posicion = elegir_posicion(esperada.posiciones, traste_anterior)
        notas.append(
            NotaEnPieza(
                midi=esperada.midi,
                cuerda=posicion.cuerda,
                traste=posicion.traste,
                inicio_pulsos=inicio,
                duracion_pulsos=esperada.pulsos,
            )
        )
        inicio += esperada.pulsos
        traste_anterior = posicion.traste
    return Pieza(
        nombre=ejercicio.nombre,
        perfil=ejercicio.perfil,
        tempo=ejercicio.tempo,
        compas=(4, 4),
        notas=tuple(notas),
    )
