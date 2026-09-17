"""Registro de detectores de tono intercambiables.

Existe para que la etapa 2 pueda enchufar un detector de acordes junto al
monofónico sin tocar el resto del núcleo. Es deliberadamente mínimo: un diccionario
y tres funciones. Sin prioridades, sin configuración, sin descubrimiento automático.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class ResultadoTono:
    """Salida de un detector.

    frecuencia: fundamental estimada en Hz, 0.0 si no se detectó nada.
    confianza: entre 0 y 1. Importa tanto como la frecuencia: sin ella no se puede
        distinguir una nota real de ruido de dedos o de un armónico.
    """

    frecuencia: float
    confianza: float


class Detector(Protocol):
    """Contrato que cumple todo detector de tono."""

    def __call__(
        self,
        muestras: np.ndarray,
        frecuencia_muestreo: int,
        frecuencia_minima: float,
        frecuencia_maxima: float,
    ) -> ResultadoTono: ...


_DETECTORES: dict[str, Detector] = {}


def registrar(nombre: str, detector: Detector) -> None:
    """Añade un detector al registro, sustituyendo el anterior con ese nombre."""
    _DETECTORES[nombre] = detector


def obtener(nombre: str) -> Detector:
    """Devuelve un detector por nombre. Lanza KeyError si no existe."""
    if nombre not in _DETECTORES:
        disponibles = ", ".join(sorted(_DETECTORES)) or "ninguno"
        raise KeyError(f"No existe el detector '{nombre}'. Disponibles: {disponibles}")
    return _DETECTORES[nombre]


def nombres_disponibles() -> list[str]:
    """Nombres de los detectores registrados, ordenados."""
    return sorted(_DETECTORES)
