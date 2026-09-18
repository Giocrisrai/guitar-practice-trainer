"""Perfiles de afinación como dato.

Un perfil describe un instrumento afinado: sus cuerdas, sus frecuencias al aire y
cuántos trastes tiene. Tratarlo como dato y no como código es lo que permite que un
bajo sea simplemente otra entrada del diccionario en lugar de una rama especial.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Cuerda:
    """Una cuerda al aire.

    numero: numeración convencional del instrumento, 1 es la más aguda.
    nota: nombre científico, por ejemplo "E2".
    frecuencia: frecuencia fundamental al aire, en Hz.
    """

    numero: int
    nota: str
    frecuencia: float


@dataclass(frozen=True)
class PerfilAfinacion:
    """Un instrumento afinado. Las cuerdas van de la más grave a la más aguda."""

    nombre: str
    cuerdas: tuple[Cuerda, ...]
    trastes: int

    @property
    def frecuencia_minima(self) -> float:
        """Frecuencia más baja que el análisis debe poder reconocer, en Hz."""
        return min(cuerda.frecuencia for cuerda in self.cuerdas)

    def tamano_ventana(self, frecuencia_muestreo: int = 48000) -> int:
        """Muestras por ventana de análisis, potencia de 2.

        El detector de tono necesita varios periodos completos de la frecuencia más
        grave. Se piden 4 periodos (el doble del mínimo teórico de 2) y se redondea
        hacia arriba a la siguiente potencia de 2:

            ventana = 2^ceil(log2(4 · fs / f_min))

        Para una guitarra estándar (f_min = 82,41 Hz a 48 kHz) da 4096 muestras
        (85 ms); para un bajo de 5 cuerdas (30,87 Hz) da 8192 (171 ms).
        """
        muestras_necesarias = 4.0 * frecuencia_muestreo / self.frecuencia_minima
        exponente = math.ceil(math.log2(muestras_necesarias))
        return 2**exponente


PERFILES: dict[str, PerfilAfinacion] = {
    "guitarra_estandar": PerfilAfinacion(
        nombre="Guitarra estándar",
        cuerdas=(
            Cuerda(6, "E2", 82.41),
            Cuerda(5, "A2", 110.00),
            Cuerda(4, "D3", 146.83),
            Cuerda(3, "G3", 196.00),
            Cuerda(2, "B3", 246.94),
            Cuerda(1, "E4", 329.63),
        ),
        trastes=22,
    ),
    "guitarra_drop_d": PerfilAfinacion(
        nombre="Guitarra Drop D",
        cuerdas=(
            Cuerda(6, "D2", 73.42),
            Cuerda(5, "A2", 110.00),
            Cuerda(4, "D3", 146.83),
            Cuerda(3, "G3", 196.00),
            Cuerda(2, "B3", 246.94),
            Cuerda(1, "E4", 329.63),
        ),
        trastes=22,
    ),
    "bajo_4": PerfilAfinacion(
        nombre="Bajo 4 cuerdas",
        cuerdas=(
            Cuerda(4, "E1", 41.20),
            Cuerda(3, "A1", 55.00),
            Cuerda(2, "D2", 73.42),
            Cuerda(1, "G2", 98.00),
        ),
        trastes=24,
    ),
    "bajo_5": PerfilAfinacion(
        nombre="Bajo 5 cuerdas",
        cuerdas=(
            Cuerda(5, "B0", 30.87),
            Cuerda(4, "E1", 41.20),
            Cuerda(3, "A1", 55.00),
            Cuerda(2, "D2", 73.42),
            Cuerda(1, "G2", 98.00),
        ),
        trastes=24,
    ),
}
