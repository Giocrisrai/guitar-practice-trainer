"""Perfiles de afinación como dato.

Un perfil describe un instrumento afinado: sus cuerdas, sus frecuencias al aire y
cuántos trastes tiene. Tratarlo como dato y no como código es lo que permite que un
bajo sea simplemente otra entrada del diccionario en lugar de una rama especial.
"""

import math
from dataclasses import dataclass

import numpy as np


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


PERFILES_DE_FABRICA: dict[str, PerfilAfinacion] = {
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

# El registro vivo de afinaciones: arranca con las de fabrica y los lectores de
# archivos dan de alta en el las que traiga una cancion (ver `registrar_perfil`).
# Se separan porque `clave_de_perfil` solo debe reconocer las de fabrica: importar
# una cancion en Drop C no convierte el Drop C en una afinacion conocida.
PERFILES: dict[str, PerfilAfinacion] = dict(PERFILES_DE_FABRICA)


def perfil_desde_midis(
    nombre: str, midis: list[int] | tuple[int, ...], trastes: int = 22
) -> PerfilAfinacion:
    """Construye un perfil a medida desde las notas MIDI de las cuerdas al aire.

    `midis` va de la cuerda más grave a la más aguda, como en `PERFILES`: la primera
    es la de número más alto (en una guitarra de 6, la sexta). El nombre de cada nota
    sale de `nombre_de_midi` y su frecuencia de `midi_a_frecuencia`:

        f = f_A4 · 2^((midi - 69) / 12)
    """
    if len(midis) == 0:
        raise ValueError("un perfil necesita al menos una cuerda")
    # Importación diferida: musica.py importa este módulo al cargarse.
    from nucleo.musica import midi_a_frecuencia, nombre_de_midi

    total = len(midis)
    cuerdas = tuple(
        Cuerda(total - indice, nombre_de_midi(midi), midi_a_frecuencia(midi))
        for indice, midi in enumerate(midis)
    )
    return PerfilAfinacion(nombre=nombre, cuerdas=cuerdas, trastes=trastes)


def registrar_perfil(perfil: PerfilAfinacion) -> str:
    """Da de alta `perfil` en `PERFILES` y devuelve su clave.

    Existe porque `Pieza.perfil` es una CLAVE de `PERFILES` y no un `PerfilAfinacion`:
    una cancion en Drop C no se podria importar si su afinacion no tuviera nombre en
    el diccionario. La clave se deriva de las cuerdas y de los trastes, asi que
    importar el mismo archivo dos veces no llena el diccionario de copias:

        a_medida_c2-g2-c3-f3-a3-d4_24t

    Quien importa debe preguntar primero por `clave_de_perfil`: una cancion en
    afinacion estandar no tiene que inventarse un perfil.
    """
    cuerdas = "-".join(cuerda.nota.replace("#", "s").lower() for cuerda in perfil.cuerdas)
    clave = f"a_medida_{cuerdas}_{perfil.trastes}t"
    PERFILES.setdefault(clave, perfil)
    return clave


def clave_de_perfil(
    perfil: PerfilAfinacion, tolerancia_cents: float = 1.0
) -> str | None:
    """Clave de un perfil DE FABRICA cuyo juego de cuerdas coincide, o None.

    Compara por frecuencia, no por igualdad de flotantes: dos cuerdas coinciden si

        |1200 · log2(f / f_conocida)| <= tolerancia_cents

    Recorre `PERFILES_DE_FABRICA` y no `PERFILES` a proposito: las afinaciones que
    dan de alta los lectores no son afinaciones conocidas, y si se compararan, la
    segunda vez que se importara la misma cancion rara se reconoceria a si misma.
    """
    frecuencias = np.array([cuerda.frecuencia for cuerda in perfil.cuerdas])
    for clave, conocido in PERFILES_DE_FABRICA.items():
        if len(conocido.cuerdas) != len(frecuencias):
            continue
        conocidas = np.array([cuerda.frecuencia for cuerda in conocido.cuerdas])
        if np.all(
            np.abs(1200.0 * np.log2(frecuencias / conocidas)) <= tolerancia_cents
        ):
            return clave
    return None
