"""Generador de cambios de acorde: la quinta familia de ejercicios.

Las digitaciones son una tabla escrita a mano y NO se derivan del patron de
intervalos de `teoria.ACORDES`. Un Do mayor abierto es x32010 porque asi se toca;
derivarlo como "la interseccion optima del conjunto {0,4,7} con el mastil"
produciria digitaciones correctas en teoria que nadie usa y que ninguna mano
alcanza. El arpegio si se deriva -ahi se toca nota a nota y vale cualquier
posicion-; el acorde, no.
"""

from nucleo.afinaciones import PerfilAfinacion
from nucleo.ejercicios.generadores.comun import validar_parametros
from nucleo.ejercicios.modelo import AcordeEsperado, Ejercicio
from nucleo.musica import Posicion, frecuencia_a_midi

__all__ = ["DIGITACIONES", "PULSOS_POR_ACORDE", "acorde_de_clave", "generar_cambios"]

# Clave -> (nombre en castellano, trastes de la 6.a cuerda a la 1.a).
#
# None NO es lo mismo que 0: None es una cuerda que no se toca y 0 es una cuerda
# al aire, que suena. Confundirlos haria que el detector buscase una nota que
# nadie esta tocando y la contase como muda, es decir que el programa riniera al
# alumno por hacerlo bien.
#
# Son los ocho acordes abiertos con los que se empieza. Anadir uno es anadir una
# linea; lo que no cabe aqui son las formas con cejilla, que piden otra cosa de
# la mano y quedan fuera de la etapa.
DIGITACIONES: dict[str, tuple[str, tuple[int | None, ...]]] = {
    "do": ("Do mayor", (None, 3, 2, 0, 1, 0)),
    "sol": ("Sol mayor", (3, 2, 0, 0, 0, 3)),
    "re": ("Re mayor", (None, None, 0, 2, 3, 2)),
    "la": ("La mayor", (None, 0, 2, 2, 2, 0)),
    "mi": ("Mi mayor", (0, 2, 2, 1, 0, 0)),
    "la_menor": ("La menor", (None, 0, 2, 2, 1, 0)),
    "mi_menor": ("Mi menor", (0, 2, 2, 0, 0, 0)),
    "re_menor": ("Re menor", (None, None, 0, 2, 3, 1)),
}

# Pulsos que dura cada acorde: un compas de 4/4.
PULSOS_POR_ACORDE = 4.0


def acorde_de_clave(clave: str, perfil: PerfilAfinacion) -> AcordeEsperado:
    """Traduce una digitacion de la tabla a notas concretas de este perfil.

    Lanza ValueError si el perfil no alcanza la digitacion -un bajo de cuatro
    cuerdas no toca un Do de cinco-, y lo hace AQUI, al generar, no mientras se
    toca. Es la misma regla que los cuatro generadores de la etapa 2a: una
    configuracion imposible se rechaza explicando el problema.
    """
    if clave not in DIGITACIONES:
        disponibles = ", ".join(sorted(DIGITACIONES))
        raise ValueError(f"El acorde '{clave}' no esta en la tabla. Opciones: {disponibles}")

    nombre, trastes = DIGITACIONES[clave]
    por_numero = {cuerda.numero: cuerda for cuerda in perfil.cuerdas}

    posiciones: list[Posicion] = []
    midis: list[int] = []
    # La tabla va de la 6.a a la 1.a, asi que el numero de cuerda BAJA al avanzar.
    for indice, traste in enumerate(trastes):
        numero = len(trastes) - indice
        if traste is None:
            continue
        if numero not in por_numero:
            raise ValueError(
                f"El acorde {nombre} necesita la cuerda {numero} y el perfil "
                f"{perfil.nombre} no la tiene."
            )
        if traste > perfil.trastes:
            raise ValueError(
                f"El acorde {nombre} pide el traste {traste} y el perfil "
                f"{perfil.nombre} solo tiene {perfil.trastes}."
            )
        posiciones.append(Posicion(cuerda=numero, traste=traste))
        midis.append(round(frecuencia_a_midi(por_numero[numero].frecuencia)) + traste)

    # De grave a aguda, el mismo orden en que se escribe un acorde y en que los
    # lectores de piezas ordenan las notas simultaneas.
    orden = sorted(range(len(midis)), key=lambda i: midis[i])
    return AcordeEsperado(
        nombre=nombre,
        posiciones=tuple(posiciones[i] for i in orden),
        midis=tuple(midis[i] for i in orden),
        pulsos=PULSOS_POR_ACORDE,
    )


def generar_cambios(
    perfil_clave: str = "guitarra_estandar",
    claves: tuple[str, ...] = ("do", "sol", "re"),
    repeticiones: int = 4,
    tempo: int = 60,
) -> Ejercicio:
    """Alterna los acordes pedidos tantas veces como se diga.

    Alterna y no agrupa: Do, Sol, Re, Do, Sol, Re. Lo que se practica es el
    CAMBIO, asi que cuatro Do seguidos no son el ejercicio.

    La direccion que se le pasa a `validar_parametros` es "ascendente" y no
    significa nada aqui: en un ejercicio de acordes no hay direccion que elegir.
    Se pasa una valida porque esa funcion valida las tres cosas de golpe -perfil,
    direccion y tempo- y el tempo si importa.
    """
    perfil = validar_parametros(perfil_clave, "ascendente", tempo)
    if len(set(claves)) < 2:
        raise ValueError("Un ejercicio de cambios necesita al menos dos acordes distintos")
    if repeticiones < 1:
        raise ValueError("Hacen falta al menos 1 repeticion")

    acordes = tuple(acorde_de_clave(clave, perfil) for clave in claves) * repeticiones
    nombres = ", ".join(DIGITACIONES[clave][0] for clave in claves)
    return Ejercicio(
        clave=f"cambios_{'_'.join(claves)}",
        nombre=f"Cambios: {nombres}",
        descripcion=(
            f"{len(acordes)} acordes alternando {nombres}, a {tempo} pulsos por "
            f"minuto. Se mide si el acorde suena completo y cuanto tardas en cambiar."
        ),
        notas=(),
        acordes=acordes,
        tempo=tempo,
        perfil=perfil_clave,
    )
