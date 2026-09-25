"""Generador de ejercicios de lectura de notas en el mastil.

Se nombra una nota y tienes que encontrarla. No suena nada: ataca directamente el
conocimiento del diapason, que es lo que mas cuesta al principio.
"""

import numpy as np

from nucleo.ejercicios.generadores.comun import validar_parametros
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import notas_alcanzables


def generar_lectura(
    perfil_clave: str = "guitarra_estandar",
    cuerda: int | None = None,
    traste_minimo: int = 0,
    traste_maximo: int = 12,
    tempo: int = 60,
    repeticiones: int = 10,
    semilla: int | None = None,
) -> Ejercicio:
    """Genera notas sueltas para buscar en el mastil.

    Si se restringe la cuerda, cada nota lleva SOLO la posicion de esa cuerda:
    pedir "el Fa# en la quinta" y aceptarlo en cualquier otra vaciaria el
    ejercicio de sentido.
    """
    perfil = validar_parametros(perfil_clave, "ascendente")
    if repeticiones < 1:
        raise ValueError("Las repeticiones deben ser al menos 1")

    numeros_validos = {c.numero for c in perfil.cuerdas}
    if cuerda is not None and cuerda not in numeros_validos:
        disponibles = ", ".join(str(n) for n in sorted(numeros_validos))
        raise ValueError(
            f"El perfil {perfil.nombre} no tiene la cuerda {cuerda}. Cuerdas: {disponibles}"
        )

    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    if cuerda is not None:
        alcanzables = {
            midi: tuple(p for p in posiciones if p.cuerda == cuerda)
            for midi, posiciones in alcanzables.items()
        }
        alcanzables = {midi: p for midi, p in alcanzables.items() if p}

    candidatas = sorted(alcanzables)
    if not candidatas:
        raise ValueError(
            f"No hay ninguna nota entre los trastes {traste_minimo} y {traste_maximo} "
            f"del perfil {perfil.nombre} con esa restriccion de cuerda."
        )

    generador = np.random.default_rng(semilla)
    elegidas = generador.choice(candidatas, size=repeticiones, replace=True)
    notas = tuple(
        NotaEsperada(midi=int(midi), posiciones=alcanzables[int(midi)], pulsos=1.0)
        for midi in elegidas
    )

    donde = f"en la cuerda {cuerda}" if cuerda is not None else "en cualquier cuerda"
    return Ejercicio(
        clave=f"lectura_{cuerda or 'todas'}_{traste_minimo}_{traste_maximo}",
        nombre=f"Lectura del mastil {donde}",
        descripcion=(
            f"{repeticiones} notas para encontrar {donde}, entre los trastes "
            f"{traste_minimo} y {traste_maximo}."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
