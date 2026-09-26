"""Generador de arpegios: las notas de un acorde tocadas por separado.

Es monofonico —una nota cada vez— asi que funciona con el detector de tono de la
etapa 1. Ensena a ver los acordes en el mastil antes de rasguearlos.
"""

from nucleo.ejercicios.generadores.comun import (
    DIRECCIONES,
    notas_del_patron_en_mastil,
    secuenciar,
    validar_parametros,
)
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import ACORDES
from nucleo.musica import nombre_de_clase, nombre_de_midi

__all__ = ["DIRECCIONES", "generar_arpegio"]

NOMBRES_ACORDES: dict[str, str] = {
    "mayor": "mayor",
    "menor": "menor",
    "septima": "con septima",
    "menor_septima": "menor con septima",
}


def generar_arpegio(
    perfil_clave: str = "guitarra_estandar",
    raiz_midi: int = 48,
    tipo: str = "mayor",
    traste_minimo: int = 0,
    traste_maximo: int = 4,
    tempo: int = 80,
    direccion: str = "ambas",
) -> Ejercicio:
    """Genera un arpegio dentro de un rango de trastes.

    Lanza ValueError si la configuracion es imposible, igual que el generador de
    escalas: la spec exige detectarlo al generar, no mientras se toca.
    """
    perfil = validar_parametros(perfil_clave, direccion, tempo)
    if tipo not in ACORDES:
        disponibles = ", ".join(sorted(ACORDES))
        raise ValueError(f"El acorde '{tipo}' no existe. Opciones: {disponibles}")

    midis, alcanzables = notas_del_patron_en_mastil(
        perfil, raiz_midi, ACORDES[tipo], traste_minimo, traste_maximo
    )
    if not midis:
        raise ValueError(
            f"No cae ninguna nota del acorde {NOMBRES_ACORDES[tipo]} de "
            f"{nombre_de_midi(raiz_midi)} entre los trastes {traste_minimo} y "
            f"{traste_maximo} del perfil {perfil.nombre}."
        )

    secuencia = secuenciar(midis, direccion)
    notas = tuple(
        NotaEsperada(midi=midi, posiciones=alcanzables[midi], pulsos=1.0) for midi in secuencia
    )

    nombre_raiz = nombre_de_clase(raiz_midi)
    return Ejercicio(
        clave=f"arpegio_{tipo}_{nombre_raiz.lower()}_{traste_minimo}_{traste_maximo}",
        nombre=f"Arpegio {NOMBRES_ACORDES[tipo]} de {nombre_raiz}",
        descripcion=(
            f"{len(notas)} notas entre los trastes {traste_minimo} y {traste_maximo}, "
            f"{direccion}, a {tempo} pulsos por minuto."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
