"""Generador de ejercicios de escala en una posicion del mastil.

Marca el patron de los cuatro generadores: una funcion pura que recibe
parametros y devuelve un Ejercicio. Sin estado, sin audio, sin catalogos
escritos a mano.
"""

from nucleo.ejercicios.generadores.comun import (
    DIRECCIONES,
    notas_del_patron_en_mastil,
    secuenciar,
    validar_parametros,
)
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import ESCALAS
from nucleo.musica import nombre_de_clase, nombre_de_midi

__all__ = ["DIRECCIONES", "generar_escala"]

NOMBRES_TIPOS: dict[str, str] = {
    "mayor": "mayor",
    "menor_natural": "menor natural",
    "pentatonica_mayor": "pentatonica mayor",
    "pentatonica_menor": "pentatonica menor",
    "blues": "de blues",
}


def generar_escala(
    perfil_clave: str = "guitarra_estandar",
    raiz_midi: int = 48,
    tipo: str = "mayor",
    traste_minimo: int = 0,
    traste_maximo: int = 4,
    tempo: int = 80,
    direccion: str = "ambas",
) -> Ejercicio:
    """Genera una escala dentro de un rango de trastes.

    El algoritmo son tres pasos: pedir al mastil que notas alcanza en el rango,
    pedir a la teoria que clases pertenecen a la escala, y quedarse con la
    interseccion ordenada de grave a aguda.

    Lanza ValueError si la configuracion es imposible. Detectarlo aqui y no
    mientras se toca es lo que pide la spec: descubrirlo tocando seria tarde.
    """
    perfil = validar_parametros(perfil_clave, direccion, tempo)
    if tipo not in ESCALAS:
        disponibles = ", ".join(sorted(ESCALAS))
        raise ValueError(f"La escala '{tipo}' no existe. Opciones: {disponibles}")

    midis, alcanzables = notas_del_patron_en_mastil(
        perfil, raiz_midi, ESCALAS[tipo], traste_minimo, traste_maximo
    )

    if not midis:
        raise ValueError(
            f"No cae ninguna nota de la escala {NOMBRES_TIPOS[tipo]} de "
            f"{nombre_de_midi(raiz_midi)} entre los trastes {traste_minimo} y "
            f"{traste_maximo} del perfil {perfil.nombre}."
        )

    secuencia = secuenciar(midis, direccion)
    notas = tuple(
        NotaEsperada(midi=midi, posiciones=alcanzables[midi], pulsos=1.0) for midi in secuencia
    )

    nombre_raiz = nombre_de_clase(raiz_midi)
    return Ejercicio(
        clave=f"escala_{tipo}_{nombre_raiz.lower()}_{traste_minimo}_{traste_maximo}",
        nombre=f"Escala {NOMBRES_TIPOS[tipo]} de {nombre_raiz}",
        descripcion=(
            f"{len(notas)} notas entre los trastes {traste_minimo} y {traste_maximo}, "
            f"{direccion}, a {tempo} pulsos por minuto."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
