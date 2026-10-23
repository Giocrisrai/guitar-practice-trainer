"""Leer una pieza de un archivo MIDI.

MIDI da las alturas y el ritmo EXACTOS, pero no dice donde se toca nada: no hay
cuerda ni traste. Toda la digitacion la pone `digitar`, y se le pasan todas las
notas de golpe para que el resultado sea un minimo sobre la pieza entera y no una
eleccion nota a nota.

Trampas del formato:

1. Los tiempos de mido son DELTA (ticks desde el mensaje anterior de la pista): hay
   que acumularlos para tener el instante absoluto.
2. Un `note_on` con `velocity=0` es un `note_off`. Es la forma habitual de cerrar una
   nota; si se ignora, las notas no se cierran nunca y las duraciones salen absurdas.
3. El tempo y el compas suelen vivir en la pista 0 aunque la musica este en otra, asi
   que se leen de todas las pistas.
"""

from collections import defaultdict, deque
from pathlib import Path

import mido
import numpy as np
from scipy.optimize import linear_sum_assignment

from nucleo.afinaciones import PERFILES, PerfilAfinacion
from nucleo.piezas.digitacion import digitar
from nucleo.piezas.lectores import FAMILIAS_GM, PistaDisponible
from nucleo.musica import Posicion, nombre_de_midi, posiciones_en_mastil
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion

# El canal de percusion de General MIDI, contado desde 0.
CANAL_PERCUSION = 9
TEMPO_POR_DEFECTO = 120
COMPAS_POR_DEFECTO = (4, 4)


def _abrir(ruta: Path | str) -> mido.MidiFile:
    """El archivo, o un `ValueError` con una frase que el usuario pueda leer."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError(f"El archivo '{ruta}' no existe.")
    try:
        return mido.MidiFile(str(ruta))
    except Exception as error:
        raise ValueError(
            f"No se pudo leer '{ruta.name}' como un archivo MIDI: {error}"
        ) from None


def _absolutos(pista: mido.MidiTrack):
    """Los mensajes de la pista con su instante absoluto en ticks (acumula los delta)."""
    reloj = 0
    for mensaje in pista:
        reloj += mensaje.time
        yield reloj, mensaje


def _es_inicio(mensaje: mido.Message) -> bool:
    return mensaje.type == "note_on" and mensaje.velocity > 0


def _es_fin(mensaje: mido.Message) -> bool:
    return mensaje.type == "note_off" or (
        mensaje.type == "note_on" and mensaje.velocity == 0
    )


def _notas_de(pista: mido.MidiTrack, ticks_por_pulso: int) -> list[tuple[int, float, float]]:
    """Las notas de la pista como (midi, inicio, duracion) en pulsos, por inicio.

    Cada (canal, nota) lleva una cola de inicios abiertos: un fin cierra el MAS
    ANTIGUO, que es lo que hace cualquier reproductor cuando una nota se repite
    sin soltarse. Lo que quede abierto al final se cierra con la pista.
    """
    abiertas: dict[tuple[int, int], deque[int]] = defaultdict(deque)
    cerradas: list[tuple[int, int, int]] = []
    final = 0
    for tick, mensaje in _absolutos(pista):
        final = tick
        if mensaje.type not in ("note_on", "note_off"):
            continue
        clave = (mensaje.channel, mensaje.note)
        if _es_inicio(mensaje):
            abiertas[clave].append(tick)
        elif _es_fin(mensaje) and abiertas[clave]:
            cerradas.append((mensaje.note, abiertas[clave].popleft(), tick))
    for (_, nota), inicios in abiertas.items():
        cerradas.extend((nota, inicio, final) for inicio in inicios)
    # Una nota que abre y cierra en el mismo tick no dura nada: no es tocable.
    notas = [
        (midi, inicio / ticks_por_pulso, (fin - inicio) / ticks_por_pulso)
        for midi, inicio, fin in cerradas
        if fin > inicio
    ]
    return sorted(notas, key=lambda nota: (nota[1], nota[0]))


def _canales(pista: mido.MidiTrack) -> set[int]:
    return {m.channel for m in pista if m.type in ("note_on", "note_off")}


def _instrumento(pista: mido.MidiTrack) -> str:
    """La familia General MIDI del primer programa que la pista elige."""
    if CANAL_PERCUSION in _canales(pista):
        return "Percusion"
    for mensaje in pista:
        if mensaje.type == "program_change":
            return FAMILIAS_GM[mensaje.program // 8]
    return "Desconocido"


def _contar_notas(pista: mido.MidiTrack) -> int:
    return sum(1 for mensaje in pista if _es_inicio(mensaje))


def _motivo_no_usable(pista: mido.MidiTrack, notas: int) -> str | None:
    if CANAL_PERCUSION in _canales(pista):
        return (
            "Es una pista de percusion: no tiene alturas que digitar en un mastil."
        )
    if notas == 0:
        return "La pista no tiene ninguna nota."
    return None


def pistas_de_midi(ruta: Path | str) -> tuple[PistaDisponible, ...]:
    """Las pistas del archivo, descritas sin convertir ninguna.

    MIDI no trae afinacion, asi que `cuerdas_midi` va vacio. Se listan todas, tambien
    la pista de tempo (sin notas) y la de bateria, con el motivo por el que no sirven.
    """
    archivo = _abrir(ruta)
    pistas = []
    for numero, pista in enumerate(archivo.tracks, start=1):
        notas = _contar_notas(pista)
        pistas.append(
            PistaDisponible(
                numero=numero,
                nombre=(pista.name or "").strip() or f"Pista {numero}",
                instrumento=_instrumento(pista),
                cuerdas_midi=(),
                notas=notas,
                motivo_no_usable=_motivo_no_usable(pista, notas),
            )
        )
    return tuple(pistas)


def _metas(archivo: mido.MidiFile, tipo: str) -> list[tuple[int, mido.MetaMessage]]:
    """Los meta-mensajes de ese tipo de TODAS las pistas, por instante."""
    encontrados = [
        (tick, mensaje)
        for pista in archivo.tracks
        for tick, mensaje in _absolutos(pista)
        if mensaje.type == tipo
    ]
    return sorted(encontrados, key=lambda par: par[0])


# Coste de una asignacion imposible (una cuerda que no da esa nota).
_IMPOSIBLE = 1e6


def _separar_cuerdas_de_acordes(
    crudas: list[tuple[int, float, float]],
    posiciones: tuple[Posicion, ...],
    perfil: PerfilAfinacion,
) -> tuple[Posicion, ...]:
    """Corrige las notas que suenan a la vez para que no compartan cuerda.

    `digitar` trata la lista como una secuencia: dos notas con el mismo instante son
    para el dos pasos seguidos, y nada le impide ponerlas en la misma cuerda, que
    es fisicamente imposible. Aqui, para cada grupo con el mismo inicio, se reparten
    las cuerdas con una asignacion de coste minimo (scipy), donde cada nota cuesta
    la distancia en trastes a lo que `digitar` habia elegido para ella: se cambia lo
    minimo.

    Limitacion: el reparto es local al acorde. No vuelve a optimizar la pieza
    entera, asi que con acordes el resultado ya no es el minimo global.

    Lanza `ValueError` si el acorde no se puede tocar (mas notas que cuerdas, o
    notas que no admiten cuerdas distintas).
    """
    corregidas = list(posiciones)
    i = 0
    while i < len(crudas):
        j = i
        while j < len(crudas) and crudas[j][1] == crudas[i][1]:
            j += 1
        grupo = range(i, j)
        if len(grupo) > 1 and len({posiciones[k].cuerda for k in grupo}) < len(grupo):
            cuerdas = sorted({c.cuerda for k in grupo
                              for c in posiciones_en_mastil(crudas[k][0], perfil)})
            coste = np.full((len(grupo), len(cuerdas)), _IMPOSIBLE)
            for fila, k in enumerate(grupo):
                for opcion in posiciones_en_mastil(crudas[k][0], perfil):
                    coste[fila, cuerdas.index(opcion.cuerda)] = abs(
                        opcion.traste - posiciones[k].traste
                    )
            filas, columnas = linear_sum_assignment(coste)
            if len(filas) < len(grupo) or coste[filas, columnas].max() >= _IMPOSIBLE:
                notas = ", ".join(nombre_de_midi(crudas[k][0]) for k in grupo)
                raise ValueError(
                    f"El acorde {notas} (en el pulso {crudas[i][1]:g}) no se puede "
                    f"tocar en {perfil.nombre}: no hay una cuerda distinta para cada nota."
                )
            for fila, columna in zip(filas, columnas, strict=True):
                nota = crudas[grupo[fila]][0]
                traste = next(o.traste for o in posiciones_en_mastil(nota, perfil)
                              if o.cuerda == cuerdas[columna])
                corregidas[grupo[fila]] = Posicion(cuerdas[columna], traste)
        i = j
    return tuple(corregidas)


def pieza_desde_midi(
    ruta: Path | str, numero_pista: int, perfil_clave: str = "guitarra_estandar"
) -> Pieza:
    """La pista `numero_pista` (empezando en 1) del MIDI, digitada para `perfil_clave`.

    El perfil no viene en el archivo: es la afinacion que tenga el usuario. Si una
    nota no cabe en su mastil -lo normal con un MIDI de piano- se lanza un
    `ValueError` que la nombra.
    """
    ruta = Path(ruta)
    if perfil_clave not in PERFILES:
        disponibles = ", ".join(sorted(PERFILES))
        raise ValueError(f"El perfil '{perfil_clave}' no existe. Opciones: {disponibles}")
    archivo = _abrir(ruta)
    pistas = pistas_de_midi(ruta)
    if not 1 <= numero_pista <= len(pistas):
        disponibles = ", ".join(f"{p.numero} ({p.nombre})" for p in pistas)
        raise ValueError(
            f"La pista {numero_pista} no existe en '{ruta.name}'. "
            f"Las que hay son: {disponibles or 'ninguna'}."
        )
    descripcion = pistas[numero_pista - 1]
    if CANAL_PERCUSION in _canales(archivo.tracks[numero_pista - 1]):
        raise ValueError(
            f"La pista {numero_pista} ('{descripcion.nombre}') no se puede importar: "
            f"{descripcion.motivo_no_usable}"
        )

    ticks_por_pulso = archivo.ticks_per_beat
    if ticks_por_pulso <= 0:
        raise ValueError(
            f"'{ruta.name}' mide el tiempo en SMPTE y no en pulsos: no se puede importar."
        )
    crudas = _notas_de(archivo.tracks[numero_pista - 1], ticks_por_pulso)

    perfil = PERFILES[perfil_clave]
    try:
        # Todos los midis de golpe: el minimo es sobre la pieza entera.
        posiciones = digitar([midi for midi, _, _ in crudas], perfil)
    except ValueError as error:
        raise ValueError(
            f"La pista {numero_pista} ('{descripcion.nombre}') no cabe en "
            f"{perfil.nombre}: {error}. Si el archivo es de piano u otro instrumento "
            "mas grave o mas agudo, prueba con otra pista o con otra afinacion."
        ) from None
    posiciones = _separar_cuerdas_de_acordes(crudas, posiciones, perfil)
    notas = tuple(
        NotaEnPieza(
            midi=midi,
            cuerda=posicion.cuerda,
            traste=posicion.traste,
            inicio_pulsos=inicio,
            duracion_pulsos=duracion,
        )
        for (midi, inicio, duracion), posicion in zip(crudas, posiciones, strict=True)
    )

    # Tempo y compas: se toma el primero y se avisa si cambian (como Guitar Pro).
    tempos = [mensaje.tempo for _, mensaje in _metas(archivo, "set_tempo")]
    tempo = round(mido.tempo2bpm(tempos[0])) if tempos else TEMPO_POR_DEFECTO
    compases = [
        (mensaje.numerator, mensaje.denominator)
        for _, mensaje in _metas(archivo, "time_signature")
    ]
    compas = compases[0] if compases else COMPAS_POR_DEFECTO
    secciones = tuple(
        Seccion(mensaje.text.strip(), tick / ticks_por_pulso)
        for tick, mensaje in _metas(archivo, "marker")
        if mensaje.text.strip()
    )
    return Pieza(
        nombre=ruta.stem,
        perfil=perfil_clave,
        tempo=tempo,
        compas=compas,
        notas=notas,
        secciones=secciones,
        tempo_variable=any(t != tempos[0] for t in tempos),
        compas_variable=any(c != compas for c in compases),
    )
