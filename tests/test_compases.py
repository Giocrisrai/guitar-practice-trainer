"""Pulsos a compases: el unico sitio del proyecto que hace esta cuenta."""

import pytest

from nucleo.piezas.compases import (
    compas_en,
    compases_de_la_seccion,
    pulsos_del_compas,
    pulsos_por_compas,
    total_de_compases,
)
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion


def pieza_de(inicios, compas=(4, 4), secciones=()):
    """Una pieza con una nota de un pulso en cada inicio dado."""
    notas = tuple(
        NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i in inicios
    )
    return Pieza(
        nombre="p",
        perfil="guitarra_estandar",
        tempo=60,
        compas=compas,
        notas=notas,
        secciones=secciones,
    )


def test_en_cuatro_por_cuatro_el_compas_tiene_cuatro_pulsos():
    assert pulsos_por_compas(pieza_de([0])) == 4.0


def test_en_siete_por_ocho_el_pulso_es_la_corchea():
    # El tempo esta en pulsos por minuto y el pulso lo define el denominador:
    # en 7/8 el compas son siete corcheas, no siete negras.
    assert pulsos_por_compas(pieza_de([0], compas=(7, 8))) == 3.5


def test_en_seis_por_ocho_el_compas_son_tres_negras():
    assert pulsos_por_compas(pieza_de([0], compas=(6, 8))) == 3.0


def test_los_pulsos_del_compas_en_seis_por_ocho():
    pieza = pieza_de([0.0, 3.0, 6.0], compas=(6, 8))
    assert pulsos_del_compas(pieza, 1) == (0.0, 3.0)
    assert pulsos_del_compas(pieza, 2) == (3.0, 6.0)


def test_los_pulsos_del_compas_en_siete_por_ocho_caen_en_medias_negras():
    # 7/8 son 3,5 negras, asi que las barras no caen en pulsos enteros: el segundo
    # compas va del 3,5 al 7,0. Es el caso que delataba el acento del metronomo,
    # que contaba 7 clicks por compas en vez de 3,5 pulsos.
    pieza = pieza_de([0.0, 3.5, 7.0], compas=(7, 8))
    assert pulsos_del_compas(pieza, 1) == (0.0, 3.5)
    assert pulsos_del_compas(pieza, 2) == (3.5, 7.0)
    assert compas_en(pieza, 3.5) == 2
    assert compas_en(pieza, 3.49) == 1


def test_el_total_de_compases_en_seis_por_ocho_y_en_siete_por_ocho():
    # La pieza dura lo que el ultimo inicio mas su duracion (un pulso), y el
    # ultimo compas incompleto cuenta. 6/8: 7 pulsos / 3 = 3 compases.
    assert total_de_compases(pieza_de([0.0, 3.0, 6.0], compas=(6, 8))) == 3
    # 7/8: 8 pulsos / 3,5 = 2,28... -> 3 compases.
    assert total_de_compases(pieza_de([0.0, 3.5, 7.0], compas=(7, 8))) == 3


def test_el_primer_compas_es_el_uno():
    pieza = pieza_de([0.0, 3.9])
    assert compas_en(pieza, 0.0) == 1
    assert compas_en(pieza, 3.9) == 1


def test_el_pulso_cuatro_ya_es_el_segundo_compas():
    assert compas_en(pieza_de([0.0, 4.0]), 4.0) == 2


def test_una_pieza_sin_notas_no_tiene_compases_y_el_cabezal_esta_en_el_uno():
    vacia = pieza_de([])
    assert total_de_compases(vacia) == 0
    assert compas_en(vacia, 0.0) == 1


def test_el_ultimo_compas_incompleto_cuenta_como_compas():
    # Nueve pulsos de musica en 4/4 son tres compases: el tercero tiene una
    # negra y tres silencios, y sigue siendo el compas 3. Es el caso de casi
    # cualquier cancion de verdad.
    pieza = pieza_de([0.0, 4.0, 8.0])
    assert total_de_compases(pieza) == 3
    assert compas_en(pieza, 8.5) == 3


def test_los_pulsos_del_compas_son_un_intervalo_medio_abierto():
    assert pulsos_del_compas(pieza_de([0.0, 4.0]), 2) == (4.0, 8.0)


def test_un_compas_que_no_existe_se_rechaza_con_su_numero():
    pieza = pieza_de([0.0])
    with pytest.raises(ValueError, match="compas 7"):
        pulsos_del_compas(pieza, 7)
    with pytest.raises(ValueError, match="compas 0"):
        pulsos_del_compas(pieza, 0)


def test_una_seccion_acaba_donde_empieza_la_siguiente():
    pieza = pieza_de(
        [0.0, 4.0, 8.0, 12.0],
        secciones=(Seccion(nombre="Intro", inicio_pulsos=0.0),
                   Seccion(nombre="Estribillo", inicio_pulsos=8.0)),
    )
    assert compases_de_la_seccion(pieza, 0) == (1, 2)


def test_la_ultima_seccion_acaba_al_final_de_la_pieza():
    pieza = pieza_de(
        [0.0, 4.0, 8.0, 12.0],
        secciones=(Seccion(nombre="Intro", inicio_pulsos=0.0),
                   Seccion(nombre="Estribillo", inicio_pulsos=8.0)),
    )
    assert compases_de_la_seccion(pieza, 1) == (3, 4)


def test_dos_secciones_con_el_mismo_nombre_se_distinguen_por_indice():
    # Por esto la seccion se pide por INDICE y no por nombre: una cancion con
    # dos estribillos trae dos secciones llamadas igual, y elegir una de las dos
    # en silencio es la clase de empate que costo un Critical en la etapa 3b.
    pieza = pieza_de(
        [0.0, 4.0, 8.0, 12.0],
        secciones=(Seccion(nombre="Estribillo", inicio_pulsos=0.0),
                   Seccion(nombre="Estribillo", inicio_pulsos=8.0)),
    )
    assert compases_de_la_seccion(pieza, 0) == (1, 2)
    assert compases_de_la_seccion(pieza, 1) == (3, 4)


def test_una_seccion_que_no_existe_se_rechaza():
    with pytest.raises(ValueError, match="seccion 2"):
        compases_de_la_seccion(pieza_de([0.0]), 2)
