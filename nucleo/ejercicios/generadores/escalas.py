"""Generador de ejercicios de escala en una posicion del mastil.

Marca el patron de los cuatro generadores: una funcion pura que recibe
parametros y devuelve un Ejercicio. Sin estado, sin audio, sin catalogos
escritos a mano.
"""

from nucleo.afinaciones import PERFILES
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import ESCALAS, clases_del_patron, notas_alcanzables
from nucleo.musica import nombre_de_midi

DIRECCIONES: tuple[str, ...] = ("ascendente", "descendente", "ambas")

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
    if perfil_clave not in PERFILES:
        disponibles = ", ".join(sorted(PERFILES))
        raise ValueError(f"El perfil '{perfil_clave}' no existe. Opciones: {disponibles}")
    if tipo not in ESCALAS:
        disponibles = ", ".join(sorted(ESCALAS))
        raise ValueError(f"La escala '{tipo}' no existe. Opciones: {disponibles}")
    if direccion not in DIRECCIONES:
        disponibles = ", ".join(DIRECCIONES)
        raise ValueError(f"La direccion '{direccion}' no existe. Opciones: {disponibles}")

    perfil = PERFILES[perfil_clave]
    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    clases = clases_del_patron(raiz_midi, ESCALAS[tipo])
    midis = sorted(midi for midi in alcanzables if midi % 12 in clases)

    if not midis:
        raise ValueError(
            f"No cae ninguna nota de la escala {NOMBRES_TIPOS[tipo]} de "
            f"{nombre_de_midi(raiz_midi)} entre los trastes {traste_minimo} y "
            f"{traste_maximo} del perfil {perfil.nombre}."
        )

    if direccion == "ascendente":
        secuencia = midis
    elif direccion == "descendente":
        secuencia = midis[::-1]
    else:
        # Subir y bajar sin repetir la cumbre: do re mi fa sol fa mi re do.
        secuencia = midis + midis[-2::-1]

    notas = tuple(
        NotaEsperada(midi=midi, posiciones=alcanzables[midi], pulsos=1.0) for midi in secuencia
    )

    nombre_raiz = nombre_de_midi(raiz_midi)[:-1]  # sin el numero de octava
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
