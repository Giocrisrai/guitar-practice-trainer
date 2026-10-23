import math

import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.musica import Posicion
from nucleo.piezas.digitacion import CosteDigitacion, coste_total, digitar

GUITARRA = PERFILES["guitarra_estandar"]


def test_una_nota_sola_toma_la_posicion_mas_comoda():
    """Sin nada alrededor, gana la cuerda al aire: cuesta cero."""
    posiciones = digitar([40], GUITARRA)
    assert posiciones == (Posicion(cuerda=6, traste=0),)


def test_una_escala_en_una_posicion_no_salta_por_el_mastil():
    midis = [48, 50, 52, 53, 55, 57, 59, 60]
    trastes = [p.traste for p in digitar(midis, GUITARRA) if p.traste > 0]
    assert max(trastes) - min(trastes) <= 4


def test_el_minimo_nunca_es_peor_que_la_heuristica_de_cercania():
    """La propiedad que de verdad vigila: comparamos contra lo que ya existe.

    `digitar` devuelve un minimo, asi que su coste tiene que ser menor o igual que el
    de cualquier otra eleccion sobre las MISMAS posiciones y con la MISMA funcion de
    coste. Si alguna vez falla, el algoritmo esta mal.

    El ancla de la heuristica no hay que derivarla a mano: `coste_total` la deduce
    igual para las dos digitaciones, quedandose con la mejor colocacion de la mano
    para la secuencia de posiciones que le dan.
    """
    from nucleo.musica import posiciones_en_mastil
    from nucleo.piezas.desde_ejercicio import elegir_posicion

    coste = CosteDigitacion()
    generador = np.random.default_rng(7)
    for _ in range(50):
        midis = [int(m) for m in generador.integers(40, 76, size=20)]
        optimo = digitar(midis, GUITARRA, coste)

        cercanas = []
        anterior = None
        for midi in midis:
            elegida = elegir_posicion(posiciones_en_mastil(midi, GUITARRA), anterior)
            cercanas.append(elegida)
            anterior = elegida.traste

        propio = coste_total(optimo, GUITARRA, coste)
        heuristico = coste_total(tuple(cercanas), GUITARRA, coste)
        assert math.isfinite(propio) and math.isfinite(heuristico)
        assert propio <= heuristico + 1e-9


def test_ninguna_posicion_cae_fuera_del_mastil():
    generador = np.random.default_rng(11)
    midis = [int(m) for m in generador.integers(40, 76, size=40)]
    for p in digitar(midis, GUITARRA):
        assert 1 <= p.cuerda <= len(GUITARRA.cuerdas)
        assert 0 <= p.traste <= GUITARRA.trastes


def test_ningun_salto_supera_el_estiramiento_permitido():
    """Salvo cuando la musica obliga: un salto grande entre notas lejanas es legitimo.

    Lo que el coste prohibe es estirar los DEDOS mas de lo humano dentro de una misma
    posicion de la mano, no mover la mano entera.
    """
    coste = CosteDigitacion(estiramiento_maximo=4)
    midis = [40, 41, 42, 43]
    trastes = [p.traste for p in digitar(midis, GUITARRA, coste) if p.traste > 0]
    assert max(trastes) - min(trastes) <= 4


def test_un_salto_grande_se_toca_moviendo_la_mano():
    """El caso que destapo que el modelo viejo llamaba imposible a un desplazamiento.

    Fa2 (midi 41) solo vive en el primer traste de la sexta; Si4 (midi 71) no baja del
    septimo de la primera. Entre los dos hay seis trastes, mas de los que abarcan los
    dedos, y aun asi ese salto lo toca cualquiera moviendo la mano. Lo que el coste
    prohibe es estirar los dedos, no desplazar la mano, asi que la arista existe y el
    coste es finito.
    """
    midis = [41, 71]
    assert digitar(midis, GUITARRA) == (
        Posicion(cuerda=6, traste=1),
        Posicion(cuerda=1, traste=7),
    )
    assert math.isfinite(coste_total(digitar(midis, GUITARRA), GUITARRA))


def test_una_nota_que_no_existe_en_el_mastil_se_rechaza():
    with pytest.raises(ValueError, match="C-1|midi 0"):
        digitar([0], GUITARRA)


def test_una_pieza_vacia_da_una_digitacion_vacia():
    assert digitar([], GUITARRA) == ()


def test_los_pesos_son_datos_y_cambiarlos_cambia_la_eleccion():
    """Si encarecer el cambio de cuerda no cambia nada, los pesos no se estan usando."""
    midis = [52, 57]
    barato = digitar(midis, GUITARRA, CosteDigitacion(por_cuerda=0.0))
    caro = digitar(midis, GUITARRA, CosteDigitacion(por_cuerda=50.0))
    assert barato != caro


def test_mil_notas_se_digitan_en_un_pestaneo():
    """O(n*k^2) con k<=6: una cancion larga no puede tardar."""
    import time

    generador = np.random.default_rng(3)
    midis = [int(m) for m in generador.integers(40, 76, size=1000)]
    inicio = time.monotonic()
    digitar(midis, GUITARRA)
    assert time.monotonic() - inicio < 1.0
