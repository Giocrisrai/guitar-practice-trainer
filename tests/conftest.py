"""Lo que toda la suite necesita antes de cada prueba."""

import pytest

from nucleo.afinaciones import PERFILES, PERFILES_DE_FABRICA


@pytest.fixture(autouse=True)
def perfiles_limpios():
    """Deja `PERFILES` como salio de fabrica despues de cada prueba.

    `PERFILES` es estado global y `registrar_perfil` escribe en el: importar una
    cancion en una afinacion rara la deja dada de alta. Sin esto, una prueba que
    importa un archivo cambia lo que ven las demas y la suite pasa o falla segun
    el orden en que se ejecuten los archivos.
    """
    yield
    PERFILES.clear()
    PERFILES.update(PERFILES_DE_FABRICA)
