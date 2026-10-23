"""Leer una pieza de un archivo MusicXML.

MusicXML trae el ritmo y los compases SIEMPRE, y A VECES la tablatura: la cuerda y el
traste en `<technical><string>` y `<fret>`. Cuando vienen se respetan, porque quien
escribio esa tablatura sabia mas que nuestro algoritmo; cuando no, las pone `digitar`.

Puntos que importan:

1. `offset` y `quarterLength` de music21 ya vienen en negras, que son nuestros pulsos:
   no hay conversion.
2. Una ligadura (`tie` de tipo `stop` o `continue`) no es un ataque nuevo: funde con
   la nota anterior y la alarga.
3. Las repeticiones se expanden con `obra.expandRepeats()`.
4. music21 es lento de importar: se importa DENTRO de las funciones, para que arrancar
   el servidor no pague ese precio cuando nadie va a leer un MusicXML.
"""

from pathlib import Path

from nucleo.afinaciones import PERFILES
from nucleo.musica import Posicion, posiciones_en_mastil
from nucleo.piezas.digitacion import digitar
from nucleo.piezas.lectores import PistaDisponible
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion

TEMPO_POR_DEFECTO = 120
COMPAS_POR_DEFECTO = (4, 4)


def _abrir(ruta: Path | str):
    """La partitura, o un `ValueError` con una frase que el usuario pueda leer."""
    from music21 import converter

    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError(f"El archivo '{ruta}' no existe.")
    try:
        return converter.parse(str(ruta), forceSource=True)
    except Exception as error:
        raise ValueError(
            f"No se pudo leer '{ruta.name}' como un archivo MusicXML: {error}"
        ) from None


def _partes(obra) -> list:
    """Las partes de la obra (una obra que ya es una sola parte cuenta como una)."""
    from music21 import stream

    if isinstance(obra, stream.Score):
        return list(obra.parts)
    return [obra]


def _atomos(parte) -> list:
    """Las notas sueltas de la parte, con los acordes deshechos en sus notas."""
    from music21 import chord, note

    sueltas = []
    for elemento in parte.flatten().notes:
        if isinstance(elemento, chord.Chord):
            for componente in elemento.notes:
                # El tiempo es del acorde; la ligadura y la tablatura, de cada nota.
                sueltas.append((componente, elemento.offset, elemento.quarterLength))
        elif isinstance(elemento, note.Note):
            sueltas.append((elemento, elemento.offset, elemento.quarterLength))
    return sueltas


def pistas_de_musicxml(ruta: Path | str) -> tuple[PistaDisponible, ...]:
    """Las partes del archivo, descritas sin convertir ninguna."""
    obra = _abrir(ruta)
    pistas = []
    for numero, parte in enumerate(_partes(obra), start=1):
        notas = len(_atomos(parte))
        instrumento = parte.getInstrument(returnDefault=False)
        pistas.append(
            PistaDisponible(
                numero=numero,
                nombre=(parte.partName or "").strip() or f"Parte {numero}",
                instrumento=(
                    (instrumento.instrumentName or "").strip()
                    if instrumento is not None
                    else ""
                )
                or "Desconocido",
                cuerdas_midi=(),
                notas=notas,
                motivo_no_usable=None if notas else "La parte no tiene ninguna nota.",
            )
        )
    return tuple(pistas)


def _tablatura(nota) -> tuple[int, int] | None:
    """(cuerda, traste) si la nota trae las DOS indicaciones; una sola no dice nada."""
    from music21 import articulations

    cuerda = traste = None
    for articulacion in nota.articulations:
        if isinstance(articulacion, articulations.StringIndication):
            cuerda = articulacion.number
        elif isinstance(articulacion, articulations.FretIndication):
            traste = articulacion.number
    if cuerda is None or traste is None:
        return None
    return int(cuerda), int(traste)


def _crudas(parte) -> list[dict]:
    """Los ataques de la parte como dicts por inicio, con las ligaduras fundidas."""
    crudas: list[dict] = []
    abiertas: dict[int, dict] = {}  # midi -> ataque que una ligadura puede alargar
    ordenadas = sorted(_atomos(parte), key=lambda t: (t[1], t[0].pitch.midi))
    for nota, inicio, duracion in ordenadas:
        midi = nota.pitch.midi
        tipo = nota.tie.type if nota.tie is not None else None
        if tipo in ("stop", "continue") and midi in abiertas:
            abiertas[midi]["duracion"] = float(inicio + duracion) - abiertas[midi]["inicio"]
            if tipo == "stop":
                del abiertas[midi]
            continue
        if duracion <= 0:
            continue  # notas de adorno sin duracion: no son tocables
        ataque = {
            "midi": midi,
            "inicio": float(inicio),
            "duracion": float(duracion),
            "tablatura": _tablatura(nota),
        }
        crudas.append(ataque)
        if tipo in ("start", "continue"):
            abiertas[midi] = ataque
    return crudas


def _posiciones(crudas: list[dict], perfil) -> list[Posicion]:
    """La del archivo cuando es coherente con el perfil; si no, la de `digitar`.

    Las notas sin tablatura se digitan TODAS de golpe (el minimo es sobre la pieza
    entera). Una tablatura que no da esa altura en el perfil elegido -otra afinacion,
    una cejilla- tampoco se respeta: se digita como si no la trajera.
    """
    elegidas: list[Posicion | None] = []
    for ataque in crudas:
        propia = ataque["tablatura"]
        posicion = Posicion(*propia) if propia else None
        if posicion not in posiciones_en_mastil(ataque["midi"], perfil):
            posicion = None
        elegidas.append(posicion)
    faltan = [i for i, p in enumerate(elegidas) if p is None]
    if faltan:
        digitadas = digitar([crudas[i]["midi"] for i in faltan], perfil)
        for i, posicion in zip(faltan, digitadas, strict=True):
            elegidas[i] = posicion
    return elegidas  # type: ignore[return-value]


def pieza_desde_musicxml(
    ruta: Path | str, numero_pista: int, perfil_clave: str = "guitarra_estandar"
) -> Pieza:
    """La parte `numero_pista` (empezando en 1) del MusicXML, para `perfil_clave`."""
    from music21 import expressions, meter, tempo as tempos_m21

    ruta = Path(ruta)
    if perfil_clave not in PERFILES:
        disponibles = ", ".join(sorted(PERFILES))
        raise ValueError(f"El perfil '{perfil_clave}' no existe. Opciones: {disponibles}")
    obra = _abrir(ruta)
    pistas = pistas_de_musicxml(ruta)
    if not 1 <= numero_pista <= len(pistas):
        disponibles = ", ".join(f"{p.numero} ({p.nombre})" for p in pistas)
        raise ValueError(
            f"La parte {numero_pista} no existe en '{ruta.name}'. "
            f"Las que hay son: {disponibles or 'ninguna'}."
        )
    descripcion = pistas[numero_pista - 1]
    if not descripcion.usable:
        raise ValueError(
            f"La parte {numero_pista} ('{descripcion.nombre}') no se puede importar: "
            f"{descripcion.motivo_no_usable}"
        )

    try:
        obra = obra.expandRepeats()
    except Exception as error:
        raise ValueError(
            f"Las repeticiones de '{ruta.name}' no se pueden expandir: {error}"
        ) from None
    parte = _partes(obra)[numero_pista - 1]

    crudas = _crudas(parte)
    perfil = PERFILES[perfil_clave]
    try:
        posiciones = _posiciones(crudas, perfil)
    except ValueError as error:
        raise ValueError(
            f"La parte {numero_pista} ('{descripcion.nombre}') no cabe en "
            f"{perfil.nombre}: {error}. Prueba con otra parte o con otra afinacion."
        ) from None
    notas = tuple(
        NotaEnPieza(
            midi=c["midi"],
            cuerda=p.cuerda,
            traste=p.traste,
            inicio_pulsos=c["inicio"],
            duracion_pulsos=c["duracion"],
        )
        for c, p in zip(crudas, posiciones, strict=True)
    )

    plano = parte.flatten()
    bpms = [
        round(m.getQuarterBPM())
        for m in plano.getElementsByClass(tempos_m21.MetronomeMark)
        if m.getQuarterBPM()
    ]
    tempo = bpms[0] if bpms else TEMPO_POR_DEFECTO
    compases = [
        (c.numerator, c.denominator)
        for c in plano.getElementsByClass(meter.TimeSignature)
    ]
    compas = compases[0] if compases else COMPAS_POR_DEFECTO
    secciones = tuple(
        Seccion(str(m.content).strip(), float(m.offset))
        for m in sorted(
            plano.getElementsByClass(expressions.RehearsalMark), key=lambda m: m.offset
        )
        if str(m.content).strip()
    )
    return Pieza(
        nombre=ruta.stem,
        perfil=perfil_clave,
        tempo=tempo,
        compas=compas,
        notas=notas,
        secciones=secciones,
        tempo_variable=any(b != tempo for b in bpms),
        compas_variable=any(c != compas for c in compases),
    )
