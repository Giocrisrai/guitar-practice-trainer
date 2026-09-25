"""Generador de ejercicios de intervalo y entrenamiento de oido.

A diferencia de escalas y arpegios, no recorre un patron: elige pares de notas
al azar. El software hace sonar la referencia y tu tocas la nota que esta al
intervalo pedido.
"""

import numpy as np

from nucleo.ejercicios.generadores.comun import (
    elegir_sin_repetir_adyacentes,
    validar_parametros,
)
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import INTERVALOS, nombre_de_intervalo, notas_alcanzables


def generar_intervalo(
    perfil_clave: str = "guitarra_estandar",
    intervalo: str = "tercera_mayor",
    traste_minimo: int = 0,
    traste_maximo: int = 7,
    tempo: int = 70,
    repeticiones: int = 8,
    semilla: int | None = None,
) -> Ejercicio:
    """Genera pares (referencia que suena, nota que debes tocar).

    La aleatoriedad es reproducible con `semilla`: sin eso las pruebas no podrian
    afirmar nada y no podrias repetir un ejercicio que te salio bien. Con
    semilla=None el ejercicio cambia cada vez, que es lo que se quiere al
    practicar.

    Las referencias se eligen SOLO entre las que tienen objetivo alcanzable en el
    mastil. Elegir primero y comprobar despues fallaria cerca del extremo agudo.

    El muestreo es con reemplazo pero nunca repite la misma referencia dos veces
    seguidas. Como el objetivo es `referencia + salto`, referencias iguales
    adyacentes darian notas objetivo iguales adyacentes, y ese ejercicio no se
    puede terminar: el evaluador no distingue la segunda pulsacion de la primera
    (ver `elegir_sin_repetir_adyacentes`).
    """
    perfil = validar_parametros(perfil_clave, "ascendente")
    if intervalo not in INTERVALOS:
        disponibles = ", ".join(sorted(INTERVALOS))
        raise ValueError(f"El intervalo '{intervalo}' no existe. Opciones: {disponibles}")
    if repeticiones < 1:
        raise ValueError("Las repeticiones deben ser al menos 1")

    salto = INTERVALOS[intervalo]
    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    referencias = sorted(midi for midi in alcanzables if midi + salto in alcanzables)
    if not referencias:
        raise ValueError(
            f"No hay ningun par a distancia de {nombre_de_intervalo(salto)} entre los "
            f"trastes {traste_minimo} y {traste_maximo} del perfil {perfil.nombre}."
        )

    generador = np.random.default_rng(semilla)
    elegidas = elegir_sin_repetir_adyacentes(generador, referencias, repeticiones)
    notas = tuple(
        NotaEsperada(
            midi=referencia + salto,
            posiciones=alcanzables[referencia + salto],
            pulsos=1.0,
            referencia_midi=referencia,
        )
        for referencia in elegidas
    )

    return Ejercicio(
        clave=f"intervalo_{intervalo}_{traste_minimo}_{traste_maximo}",
        nombre=f"Intervalo: {nombre_de_intervalo(salto)}",
        descripcion=(
            f"{repeticiones} repeticiones. Suena una nota y tocas la que esta una "
            f"{nombre_de_intervalo(salto)} por encima, entre los trastes "
            f"{traste_minimo} y {traste_maximo}."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
