"""Teoría musical: conversión entre frecuencia, nota y posición en el mástil.

Aritmética pura. Este módulo no conoce el audio ni el hardware; recibe números y
devuelve números. Toda la afinación temperada se apoya en dos identidades:

    midi(f) = 69 + 12 · log2(f / f_ref)        con f_ref = A4
    cents   = 1200 · log2(f / f_ideal)

donde f_ideal es la frecuencia exacta de la nota más cercana.
"""

import math
from dataclasses import dataclass

from nucleo.afinaciones import PerfilAfinacion

NOMBRES_NOTAS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

MIDI_LA4 = 69


@dataclass(frozen=True)
class NotaDetectada:
    """Nota reconocida a partir de una frecuencia.

    nombre: notación científica, por ejemplo "E2".
    midi: número MIDI de la nota más cercana.
    frecuencia_ideal: frecuencia exacta de esa nota, en Hz.
    cents: desviación respecto a la nota ideal. Negativo = grave, positivo = agudo.
    """

    nombre: str
    midi: int
    frecuencia_ideal: float
    cents: float


@dataclass(frozen=True)
class Posicion:
    """Un punto del mástil: número de cuerda y traste. Traste 0 es al aire."""

    cuerda: int
    traste: int


def frecuencia_a_midi(frecuencia: float, referencia_a4: float = 440.0) -> float:
    """Número MIDI (con decimales) de una frecuencia.

        midi(f) = 69 + 12 · log2(f / f_ref)
    """
    if frecuencia <= 0.0:
        raise ValueError("La frecuencia debe ser positiva")
    return MIDI_LA4 + 12.0 * math.log2(frecuencia / referencia_a4)


def midi_a_frecuencia(midi: float, referencia_a4: float = 440.0) -> float:
    """Frecuencia en Hz de un número MIDI.

        f(midi) = f_ref · 2^((midi - 69) / 12)
    """
    return referencia_a4 * 2.0 ** ((midi - MIDI_LA4) / 12.0)


def nombre_de_midi(midi: int) -> str:
    """Nombre en notación científica, por ejemplo 40 -> "E2"."""
    octava = midi // 12 - 1
    return f"{NOMBRES_NOTAS[midi % 12]}{octava}"


def frecuencia_a_nota(frecuencia: float, referencia_a4: float = 440.0) -> NotaDetectada:
    """Nota más cercana a una frecuencia, con su desviación en cents."""
    midi_exacto = frecuencia_a_midi(frecuencia, referencia_a4)
    midi_cercano = round(midi_exacto)
    frecuencia_ideal = midi_a_frecuencia(midi_cercano, referencia_a4)
    cents = 1200.0 * math.log2(frecuencia / frecuencia_ideal)
    return NotaDetectada(
        nombre=nombre_de_midi(midi_cercano),
        midi=midi_cercano,
        frecuencia_ideal=frecuencia_ideal,
        cents=cents,
    )


def posiciones_en_mastil(midi: int, perfil: PerfilAfinacion) -> list[Posicion]:
    """Todas las posiciones del mástil que producen esa nota.

    Devuelve una lista y no una sola posición a propósito: un La de 110 Hz es tanto
    la 5ª cuerda al aire como la 6ª en el traste 5, y desde la frecuencia no hay
    forma de distinguirlas. Elegir una sería fingir una certeza inexistente.

    El resultado va ordenado por número de cuerda descendente (de la más grave a la
    más aguda), que es el orden en que se dibuja el mástil.
    """
    posiciones = []
    for cuerda in perfil.cuerdas:
        midi_al_aire = round(frecuencia_a_midi(cuerda.frecuencia))
        traste = midi - midi_al_aire
        if 0 <= traste <= perfil.trastes:
            posiciones.append(Posicion(cuerda=cuerda.numero, traste=traste))
    return sorted(posiciones, key=lambda p: -p.cuerda)


def esta_afinada(cents: float, tolerancia: float = 5.0) -> bool:
    """Verdadero si la desviación cae dentro de la tolerancia, en cents."""
    return abs(cents) < tolerancia
