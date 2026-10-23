"""Lector de tablatura ASCII, la de los foros: el lector FLOJO.

Hay que decirlo sin adornos: la tablatura de texto NO TRAE RITMO. Las seis lineas
dan cuerda y traste y nada mas. Todo lo que este modulo cuenta sobre el tiempo es
una inferencia a partir del espacio en blanco, y por eso la pieza sale con
`ritmo_aproximado=True` y la pantalla lo dice.

Que se lee y que no:

- Cuerda y traste: de fiar, siempre que la tablatura este bien copiada. La linea
  de ABAJO es la cuerda de numero mas alto (la sexta), que es la convencion de
  cualquier tablatura; las lineas deben medir lo mismo y, si no, se rechaza el
  texto nombrando la linea, porque es el sintoma de una tablatura copiada a medias.
- Instrumento: lo decide el numero de lineas -4 bajo, 6 guitarra, 7 guitarra de
  siete-. Otros numeros se rechazan en vez de adivinar. Si la primera columna trae
  las letras de las cuerdas se construye el perfil con ellas (una Drop D se lee
  como Drop D); si no, o si alguna letra no es una nota, se supone la afinacion
  estandar del instrumento.
- Tecnicas (h, p, b, /, \\, ~, x, parentesis): se IGNORAN. "5h7" son dos ataques, 5
  y 7, y una nota muerta "x" desaparece. No hay legatos ni bends.
- Varios sistemas (bloques de lineas separados por texto o por lineas en blanco) se
  leen uno a continuacion de otro.

El ritmo, la parte que falla:

    La distancia en columnas entre un ataque y el siguiente es su duracion, y la
    unidad se elige de modo que la distancia MAS CORTA de toda la tablatura sea una
    negra (1 pulso). Es la convencion implicita de quien las escribe, y es una
    HEURISTICA, no un dato.

Funciona en tablaturas bien alineadas con un espaciado proporcional al tiempo.
Falla, y no avisa, en las que no: una columna de desajuste que acorte la distancia
MINIMA encoge la unidad y alarga todas las demas duraciones (si no la acorta, solo
falsea esa nota); entre sistemas la distancia incluye los guiones finales del primero
y los iniciales del segundo, asi que dos notas contiguas en sistemas distintos salen
mas separadas de lo que estan; un espaciado uniforme
-todas las notas a la misma distancia aunque unas sean corcheas y otras negras-
da todas las notas iguales; un acorde cuyos numeros no estan en la misma columna
se lee como notas sucesivas. La ultima nota dura una negra, porque no hay otra
despues contra la que medir. El compas se supone 4/4 y el tempo lo da quien llama,
porque el texto no lo trae.

Los numeros de una misma columna son un acorde: el modelo de `Pieza` los admite, y
sus notas van con la GRAVE PRIMERO, como en los demas lectores (el seguimiento senala
la ultima nota de un acorde, y debe ser la aguda).
"""

import re

import numpy as np

from nucleo.afinaciones import (
    PERFILES,
    clave_de_perfil,
    perfil_desde_midis,
    registrar_perfil,
)
from nucleo.musica import NOMBRES_NOTAS, midi_de_nombre
from nucleo.piezas.modelo import NotaEnPieza, Pieza

# Cuerdas al aire de la afinacion estandar de cada instrumento, de la mas grave a la
# mas aguda. Las claves son el numero de lineas de la tablatura.
AFINACION_ESTANDAR = {
    4: (28, 33, 38, 43),  # bajo: E1 A1 D2 G2
    6: (40, 45, 50, 55, 59, 64),  # guitarra: E2 A2 D3 G3 B3 E4
    7: (35, 40, 45, 50, 55, 59, 64),  # guitarra de siete: B1 E2 A2 D3 G3 B3 E4
}
NOMBRE_DEL_INSTRUMENTO = {4: "bajo", 6: "guitarra", 7: "guitarra de siete cuerdas"}
TRASTES_DEL_INSTRUMENTO = {4: 24, 6: 22, 7: 24}

_LINEA = re.compile(r"^\s*([A-Za-z#]{0,2})\s*\|?(.*?)\s*$")
_NUMERO = re.compile(r"\d+")
_ES_NOTA = re.compile(r"^[A-Ga-g][#b]?$")


def _parece_de_tablatura(cuerpo: str) -> bool:
    """Casi todo guiones, barras y digitos, y con guiones de verdad."""
    if not cuerpo or cuerpo.count("-") < 2:
        return False
    utiles = sum(1 for c in cuerpo if c in "-|" or c.isdigit())
    return utiles / len(cuerpo) >= 0.7


def _bloques(texto: str) -> list[list[tuple[int, str, str]]]:
    """Los grupos de lineas de tablatura consecutivas: (numero de linea, etiqueta, cuerpo)."""
    bloques: list[list[tuple[int, str, str]]] = []
    actual: list[tuple[int, str, str]] = []
    for numero, linea in enumerate(texto.splitlines(), start=1):
        coincide = _LINEA.match(linea)
        # Una linea de solo guiones, sin letra, sin barra y sin numeros, es un
        # separador entre sistemas y no una cuerda vacia.
        con_marca = coincide and (
            coincide.group(1) or "|" in linea or any(c.isdigit() for c in linea)
        )
        if con_marca and _parece_de_tablatura(coincide.group(2)):
            actual.append((numero, coincide.group(1), coincide.group(2)))
        elif actual:
            bloques.append(actual)
            actual = []
    if actual:
        bloques.append(actual)
    return bloques


def _comprobar_longitudes(bloque: list[tuple[int, str, str]]) -> None:
    """Todas las lineas del bloque miden lo mismo, o se nombra la primera que no."""
    longitudes = [len(cuerpo) for _, _, cuerpo in bloque]
    # La longitud de referencia es la mas frecuente; a igualdad, la de la primera linea.
    referencia = max(dict.fromkeys(longitudes), key=longitudes.count)
    for (numero, _, cuerpo) in bloque:
        if len(cuerpo) != referencia:
            raise ValueError(
                f"La linea {numero} de la tablatura mide {len(cuerpo)} columnas y las "
                f"demas del bloque {referencia}: parece copiada a medias, y con las "
                "lineas desalineadas el ritmo saldria inventado"
            )


def _ataques_del_bloque(bloque: list[tuple[int, str, str]]) -> tuple[list, int]:
    """Los ataques (columna, linea, traste) del bloque y su ancho sin barras de compas.

    Una columna que es '|' en TODAS las lineas es una barra de compas: no es tiempo
    y se quita, para que no estire la distancia entre la ultima nota de un compas y
    la primera del siguiente.
    """
    matriz = np.array([list(cuerpo) for _, _, cuerpo in bloque])
    barras = (matriz == "|").all(axis=0)
    columna_efectiva = np.cumsum(~barras) - 1
    ataques = []
    for indice, (numero, _, cuerpo) in enumerate(bloque):
        for coincidencia in _NUMERO.finditer(cuerpo):
            if len(coincidencia.group()) > 2:
                raise ValueError(
                    f"La linea {numero} tiene '{coincidencia.group()}': un traste de "
                    "tres digitos no existe"
                )
            ataques.append(
                (int(columna_efectiva[coincidencia.start()]), indice, int(coincidencia.group()))
            )
    return ataques, int((~barras).sum())


def _nota_mas_cercana(clase: int, referencia: int) -> int:
    """El MIDI de esa clase de nota (0-11) que cae mas cerca de `referencia`."""
    candidatos = [12 * octava + clase for octava in range(-1, 10)]
    return min(candidatos, key=lambda midi: (abs(midi - referencia), midi))


def _midis_de_las_etiquetas(etiquetas: list[str], lineas: int) -> tuple[int, ...] | None:
    """Los MIDI al aire que dicen las letras de la primera columna, o None si no sirven.

    La tablatura trae letras sin octava, asi que la octava se deduce: la cuerda mas
    grave (la linea de abajo) es la nota de esa letra mas cercana a la de la
    afinacion estandar, y cada cuerda mas aguda es la primera nota de su letra POR
    ENCIMA de la anterior. Dos cuerdas con la misma letra quedan a una octava.
    """
    if not all(_ES_NOTA.match(e) for e in etiquetas):
        return None
    clases = [_clase(e) for e in etiquetas]
    # `etiquetas` va de arriba abajo; la afinacion, de la mas grave a la mas aguda.
    clases.reverse()
    midis = [_nota_mas_cercana(clases[0], AFINACION_ESTANDAR[lineas][0])]
    for clase in clases[1:]:
        siguiente = midis[-1] + 1
        while siguiente % 12 != clase:
            siguiente += 1
        midis.append(siguiente)
    return tuple(midis)


def _clase(etiqueta: str) -> int:
    """'E' -> 4, 'Bb' -> 10, 'f#' -> 6."""
    clase = NOMBRES_NOTAS.index(etiqueta[0].upper())
    # Solo con dos caracteres: la 'b' sola es la nota si, la convencion de los foros
    # para la segunda cuerda ("e|b|g|d|a|e"), y no un bemol de nada.
    if len(etiqueta) == 2 and etiqueta[1] == "#":
        clase += 1
    elif len(etiqueta) == 2 and etiqueta[1] == "b":
        clase -= 1
    return clase % 12


def _clave_del_perfil(midis: tuple[int, ...], lineas: int, traste_maximo: int, titulo: str) -> str:
    """La clave de `PERFILES`: la de fabrica si la afinacion la conoce y el mastil llega."""
    perfil = perfil_desde_midis(
        titulo, midis, trastes=max(TRASTES_DEL_INSTRUMENTO[lineas], traste_maximo)
    )
    conocida = clave_de_perfil(perfil)
    if conocida is not None and PERFILES[conocida].trastes >= traste_maximo:
        return conocida
    return registrar_perfil(perfil)


def pieza_desde_ascii(
    texto: str,
    tempo: int = 90,
    perfil_clave: str | None = None,
    nombre: str = "Tablatura ASCII",
) -> Pieza:
    """Una `Pieza` desde una tablatura de texto, con el RITMO APROXIMADO.

    La duracion de cada ataque es la distancia en columnas hasta el siguiente, con la
    unidad elegida para que la distancia mas corta sea 1 pulso (ver el docstring del
    modulo). Es una heuristica: falla en las tablaturas mal alineadas, que son
    muchas, y la pieza lo declara con `ritmo_aproximado=True`.

    `perfil_clave`: si se da, manda sobre las letras de la tablatura y debe tener
    tantas cuerdas como lineas; si no, el instrumento sale del numero de lineas y la
    afinacion de las letras (o la estandar).

    Lanza ValueError si el texto no trae ninguna tablatura, si sus lineas no miden
    lo mismo (nombrando la linea), si el numero de lineas no es 4, 6 o 7, si los
    bloques no tienen todos el mismo numero de lineas, o si no hay ninguna nota.
    """
    bloques = _bloques(texto)
    if not bloques:
        raise ValueError(
            "No encuentro ninguna tablatura en el texto: espero lineas como "
            "'e|--0--2--|', casi todo guiones y numeros"
        )
    lineas = len(bloques[0])
    for bloque in bloques:
        _comprobar_longitudes(bloque)
        if len(bloque) != lineas:
            raise ValueError(
                f"La tablatura mezcla bloques de {lineas} y de {len(bloque)} lineas "
                f"(el segundo empieza en la linea {bloque[0][0]})"
            )
    if lineas not in AFINACION_ESTANDAR and perfil_clave is None:
        raise ValueError(
            f"Una tablatura de {lineas} lineas: solo sé leer 4 (bajo), 6 (guitarra) "
            "o 7 (guitarra de siete cuerdas)"
        )

    ataques = []
    desplazamiento = 0
    for bloque in bloques:
        del_bloque, ancho = _ataques_del_bloque(bloque)
        ataques += [(desplazamiento + col, linea, traste) for col, linea, traste in del_bloque]
        desplazamiento += ancho
    if not ataques:
        raise ValueError("La tablatura no trae ninguna nota: todas las lineas estan vacias")
    traste_maximo = max(traste for _, _, traste in ataques)

    if perfil_clave is not None:
        if perfil_clave not in PERFILES:
            disponibles = ", ".join(sorted(PERFILES))
            raise ValueError(f"El perfil '{perfil_clave}' no existe. Opciones: {disponibles}")
        perfil = PERFILES[perfil_clave]
        if len(perfil.cuerdas) != lineas:
            raise ValueError(
                f"El perfil '{perfil_clave}' tiene {len(perfil.cuerdas)} cuerdas y la "
                f"tablatura {lineas} lineas"
            )
        if traste_maximo > perfil.trastes:
            raise ValueError(
                f"La tablatura toca el traste {traste_maximo} y '{perfil_clave}' "
                f"solo tiene {perfil.trastes}"
            )
        midis = tuple(midi_de_nombre(cuerda.nota) for cuerda in perfil.cuerdas)
        clave = perfil_clave
    else:
        etiquetas = [etiqueta for _, etiqueta, _ in bloques[0]]
        midis = _midis_de_las_etiquetas(etiquetas, lineas) or AFINACION_ESTANDAR[lineas]
        clave = _clave_del_perfil(
            midis, lineas, traste_maximo, f"Tablatura de {NOMBRE_DEL_INSTRUMENTO[lineas]}"
        )

    # La linea de arriba (indice 0) es la cuerda 1; los MIDI van de grave a aguda, asi
    # que la linea de indice i es la cuerda midis[lineas - 1 - i].
    columnas = np.unique([columna for columna, _, _ in ataques])
    distancias = np.diff(columnas)
    unidad = float(distancias.min()) if len(distancias) else 1.0
    inicios = (columnas - columnas[0]) / unidad
    duraciones = np.append(distancias / unidad, 1.0)
    por_columna = {int(c): (float(i), float(d)) for c, i, d in zip(columnas, inicios, duraciones)}

    notas = tuple(
        NotaEnPieza(
            midi=midis[lineas - 1 - linea] + traste,
            cuerda=linea + 1,
            traste=traste,
            inicio_pulsos=por_columna[columna][0],
            duracion_pulsos=por_columna[columna][1],
        )
        for columna, linea, traste in sorted(ataques, key=lambda ataque: (ataque[0], -ataque[1]))
    )
    return Pieza(
        nombre=nombre,
        perfil=clave,
        tempo=tempo,
        compas=(4, 4),
        notas=notas,
        ritmo_aproximado=True,
    )
