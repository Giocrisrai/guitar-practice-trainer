"""Leer una pieza de un archivo de Guitar Pro.

Es el formato bueno: el unico que trae cuerda, traste, ritmo, compases, secciones y
afinacion ya hechos. Por eso este lector NO usa `digitacion.py`: elegir la posicion
de cada nota seria tirar el dato que el archivo ya da. Si una cancion dice que el
Sol se toca en el traste 3 de la sexta y no al aire en la tercera, es que se toca
ahi.

Las tres trampas del modelo de PyGuitarPro, verificadas ejecutandolo:

1. `Beat.start` es un tick ABSOLUTO y el primer compas empieza en 960, no en 0:
   hay que restar el inicio de su compas o la pieza entera sale corrida un pulso.
2. `Track.strings` va de la cuerda MAS AGUDA a la mas grave -la numero 1 primero;
   lo documenta `gp5.readTrack`: "the strings are stored from the highest to the
   lowest"-, mientras que `PerfilAfinacion.cuerdas` va al contrario. Hay que darle
   la vuelta, y si no se hace la tablatura sale del reves sin que nada falle.
3. Un `NoteType.tie` no es un ataque nuevo: es la nota anterior que sigue sonando.
   Si entrara como nota, el carril pediria tocar algo que no se toca y lo contaria
   como fallo.
"""

from dataclasses import dataclass
from pathlib import Path

import guitarpro

from nucleo.afinaciones import (
    PERFILES,
    PerfilAfinacion,
    clave_de_perfil,
    perfil_desde_midis,
    registrar_perfil,
)
from nucleo.piezas.lectores import FAMILIAS_GM, PistaDisponible
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion

TICKS_NEGRA = guitarpro.Duration.quarterTime

TRASTES_POR_DEFECTO = 22

# Cota de seguridad al expandir repeticiones: un archivo con las barras mal puestas
# no debe colgar el programa.
MAXIMO_COMPASES_TOCADOS = 10_000


@dataclass
class _NotaEnObra:
    """Una nota a medio construir, porque una ligadura puede alargarla despues."""

    midi: int
    cuerda: int
    traste: int
    inicio_pulsos: float
    fin_pulsos: float


def _abrir(ruta: Path | str) -> guitarpro.Song:
    """La cancion, o un `ValueError` con una frase que el usuario pueda leer.

    Cualquier fallo de la libreria se traduce aqui: quien lee el mensaje quiere
    saber que archivo no sirve, no en que linea de PyGuitarPro se rompio. Por eso
    `from None`, que corta el traceback encadenado.
    """
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ValueError(f"El archivo '{ruta}' no existe.")
    try:
        return guitarpro.parse(str(ruta))
    except Exception as error:
        raise ValueError(
            f"No se pudo leer '{ruta.name}' como un archivo de Guitar Pro "
            f"(gp3, gp4 o gp5): {error}"
        ) from None


def _instrumento(pista: guitarpro.Track) -> str:
    """La familia General MIDI del sonido de la pista."""
    if pista.isPercussionTrack:
        return "Percusion"
    programa = pista.channel.instrument
    if not 0 <= programa < 128:
        return "Desconocido"
    return FAMILIAS_GM[programa // 8]


def _contar_notas(pista: guitarpro.Track) -> int:
    """Cuantas notas con altura trae la pista.

    No convierte nada -listar tiene que ser barato- y no mira `Note.string`, que en
    una pista de percusion no significa nada.
    """
    return sum(
        1
        for compas in pista.measures
        for voz in compas.voices
        for beat in voz.beats
        for nota in beat.notes
        if nota.type is guitarpro.NoteType.normal
    )


def _motivo_no_usable(pista: guitarpro.Track, notas: int) -> str | None:
    """Por que no se puede importar esta pista, o None si se puede."""
    if pista.isPercussionTrack:
        return (
            "Es una pista de percusion: no tiene cuerdas ni trastes, asi que no hay "
            "tablatura que seguir."
        )
    if not pista.strings:
        return "La pista no declara ninguna cuerda, asi que no se sabe como esta afinada."
    if notas == 0:
        return "La pista no tiene ninguna nota."
    return None


def pistas_de(ruta: Path | str) -> tuple[PistaDisponible, ...]:
    """Las pistas del archivo, descritas sin convertir ninguna.

    Se listan TODAS, tambien las que no se pueden usar: el usuario tiene que ver que
    la pista de bateria esta ahi y por que no se le ofrece, en vez de preguntarse
    donde fue.
    """
    return _describir(_abrir(ruta))


def _describir(cancion: guitarpro.Song) -> tuple[PistaDisponible, ...]:
    """El listado de `pistas_de`, a partir de una cancion ya abierta.

    Da de alta la afinacion de cada pista que declare cuerdas (`_clave_de_pista`, y
    ahi esta el porque). Describir una pista no convierte ni una nota, pero su
    afinacion sí queda disponible, que es lo que el aviso de «aféinate a esto»
    necesita para poder ofrecer el botón.

    Y la clave con la que se dio de alta VIAJA en la descripcion
    (`PistaDisponible.perfil_clave`). No es un extra: es la unica forma de que quien
    muestra el aviso proponga exactamente la clave que va a traer la pieza. Mientras
    el servidor la volvia a deducir comparando las notas de `cuerdas_midi` contra el
    registro, dos perfiles de la misma afinacion y distinto numero de trastes -una
    cancion con `fretCount` 22 y otra con 24- se tapaban: el aviso proponia el
    primero que encajaba y el carril rechazaba la pieza despues de afinarse.
    """
    pistas = []
    for numero, pista in enumerate(cancion.tracks, start=1):
        notas = _contar_notas(pista)
        pistas.append(
            PistaDisponible(
                numero=numero,
                nombre=pista.name.strip() or f"Pista {numero}",
                instrumento=_instrumento(pista),
                cuerdas_midi=tuple(cuerda.value for cuerda in pista.strings),
                notas=notas,
                motivo_no_usable=_motivo_no_usable(pista, notas),
                perfil_clave=_clave_de_pista(pista),
            )
        )
    return tuple(pistas)


def _veces_que_se_toca(cabecera, normalizado: bool) -> int:
    """Cuantas veces se toca el trozo que cierra en este compas; 1 si no cierra.

    El byte del disco es el NUMERO DE VECES que se toca, con minimo 2: es el "x2"
    que muestra Guitar Pro. PyGuitarPro no lo deja igual en los tres formatos, y
    esto se puede comprobar sin tener un archivo real (lo hace
    `test_el_byte_del_disco_de_un_cierre_cuenta_las_veces_que_se_toca`):

    - gp5 lo normaliza a PASADAS DE MAS: resta 1 al leer (`gp5.py:328`) y suma 1
      al escribir (`gp5.py:1059`), asi que un "x2" llega a memoria como 1.
    - gp3 y gp4 no lo tocan (`gp3.py:225`): un "x2" llega a memoria como 2.

    Que en gp5 la memoria cuente pasadas de mas lo confirma la propia libreria:
    `RepeatGroup` solo considera que hay cierre si `repeatClose > 0`
    (`models.py:119`), asi que si la memoria contara veces, un "x1" -que no es una
    repeticion- seria indistinguible de no tener cierre.

    Sin cierre, `repeatClose` vale -1 y aqui se devuelve 1: se toca una vez.
    """
    veces = cabecera.repeatClose + 1 if normalizado else cabecera.repeatClose
    return max(veces, 1)


def _orden_de_compases(compases: list, normalizado: bool) -> tuple[int, ...]:
    """Los indices de los compases EN EL ORDEN EN QUE SE TOCAN.

    Una barra de repeticion no es un adorno: si no se expande, la pieza dura la
    mitad de lo que suena. `isRepeatOpen` abre y el cierre dice cuantas veces se
    toca el trozo en total, asi que se vuelve a el `veces - 1` veces.
    """
    orden: list[int] = []
    abierto = 0
    vueltas: dict[int, int] = {}
    indice = 0
    while indice < len(compases) and len(orden) < MAXIMO_COMPASES_TOCADOS:
        cabecera = compases[indice].header
        if cabecera.isRepeatOpen:
            abierto = indice
        orden.append(indice)
        veces = _veces_que_se_toca(cabecera, normalizado)
        if veces > 1 and vueltas.get(indice, 0) < veces - 1:
            vueltas[indice] = vueltas.get(indice, 0) + 1
            indice = abierto
            continue
        indice += 1
    return tuple(orden)


def _midis_al_aire(pista: guitarpro.Track) -> dict[int, int]:
    """Numero de cuerda -> MIDI de esa cuerda al aire."""
    return {cuerda.number: cuerda.value for cuerda in pista.strings}


def _cuerdas_de_grave_a_aguda(pista: guitarpro.Track) -> tuple[int, ...]:
    """Los MIDI al aire en el orden que espera `perfil_desde_midis`.

    Se ordena por numero de cuerda DESCENDENTE y no por altura: `perfil_desde_midis`
    numera las cuerdas por su posicion (la primera recibe el numero mas alto), y esa
    numeracion tiene que coincidir con la de `Note.string` del archivo o la nota se
    dibujaria en otra linea de la tablatura.
    """
    por_numero = sorted(pista.strings, key=lambda cuerda: -cuerda.number)
    return tuple(cuerda.value for cuerda in por_numero)


def _tempo_variable(cancion: guitarpro.Song) -> bool:
    """Si el archivo cambia de tempo en algun momento.

    `Pieza` tiene UN tempo. Rechazar la cancion seria peor que importarla avisando:
    se toma el primero y se marca, y el carril ya decidira que hace con el aviso.
    """
    for pista in cancion.tracks:
        for compas in pista.measures:
            for voz in compas.voices:
                for beat in voz.beats:
                    cambio = beat.effect.mixTableChange
                    if cambio is not None and cambio.tempo is not None:
                        if cambio.tempo.value != cancion.tempo:
                            return True
    return False


def _convertir(
    pista: guitarpro.Track, orden: tuple[int, ...]
) -> tuple[tuple[NotaEnPieza, ...], tuple[Seccion, ...]]:
    """Las notas y las secciones de la pista, en pulsos desde el principio."""
    al_aire = _midis_al_aire(pista)
    en_obra: list[_NotaEnObra] = []
    # (voz, cuerda, traste) -> la ultima nota que sigue abierta a una ligadura.
    ultima: dict[tuple[int, int, int], _NotaEnObra] = {}
    secciones: list[Seccion] = []
    desplazamiento = 0.0

    for indice in orden:
        compas = pista.measures[indice]
        marcador = compas.header.marker
        if marcador is not None and marcador.title.strip():
            secciones.append(Seccion(marcador.title.strip(), desplazamiento))
        for numero_voz, voz in enumerate(compas.voices):
            for beat in voz.beats:
                inicio = desplazamiento + (beat.start - compas.start) / TICKS_NEGRA
                duracion = beat.duration.time / TICKS_NEGRA
                for nota in beat.notes:
                    if nota.type is guitarpro.NoteType.tie:
                        # No es un ataque: alarga la nota de la misma cuerda y
                        # traste que ya estaba sonando. Si no hay ninguna -el
                        # archivo empieza por una ligadura- no hay nada que
                        # alargar y se ignora.
                        abierta = ultima.get((numero_voz, nota.string, nota.value))
                        if abierta is not None:
                            abierta.fin_pulsos = max(
                                abierta.fin_pulsos, inicio + duracion
                            )
                        continue
                    if nota.type is not guitarpro.NoteType.normal:
                        # `rest` es que NO HAY nota, y `dead` una nota apagada, que
                        # no tiene altura que seguir. Ninguna de las dos entra.
                        continue
                    if nota.string not in al_aire:
                        continue
                    nueva = _NotaEnObra(
                        midi=al_aire[nota.string] + nota.value,
                        cuerda=nota.string,
                        traste=nota.value,
                        inicio_pulsos=inicio,
                        fin_pulsos=inicio + duracion,
                    )
                    en_obra.append(nueva)
                    ultima[(numero_voz, nota.string, nota.value)] = nueva
        desplazamiento += compas.length / TICKS_NEGRA

    # `Pieza` exige las notas en orden de inicio; la cuerda desempata para que un
    # acorde salga siempre igual, de la mas grave a la mas aguda. No es cosmetica:
    # `indice_actual` señala la ultima nota del acorde
    # (`seguimiento._indice_en_curso`), asi que el orden decide cual resalta el
    # carril y cual lleva el aro en la vista escrita, y es un invariante entre los
    # cuatro lectores (`test_un_acorde_va_con_la_grave_primero_como_en_los_demas_lectores`,
    # en los cuatro archivos de pruebas). El archivo las guarda al contrario -de la
    # mas aguda a la mas grave, que es como se escribe la mascara de cuerdas-, asi
    # que leerlas en su orden da justo el equivocado.
    en_obra.sort(key=lambda nota: (nota.inicio_pulsos, -nota.cuerda))
    notas = tuple(
        NotaEnPieza(
            midi=nota.midi,
            cuerda=nota.cuerda,
            traste=nota.traste,
            inicio_pulsos=nota.inicio_pulsos,
            duracion_pulsos=nota.fin_pulsos - nota.inicio_pulsos,
        )
        for nota in en_obra
    )
    return notas, tuple(secciones)


def _compas(cabecera) -> tuple[int, int]:
    """El compas de una cabecera: (4, 4), (3, 4), (6, 8)."""
    return (
        cabecera.timeSignature.numerator,
        cabecera.timeSignature.denominator.value,
    )


def _trastes_declarados(pista: guitarpro.Track) -> int:
    """Los trastes que dice la pista, o los de una guitarra si no dice nada util."""
    if pista.fretCount and pista.fretCount > 0:
        return int(pista.fretCount)
    return TRASTES_POR_DEFECTO


def _traste_maximo(pista: guitarpro.Track) -> int:
    """El traste mas alto que pisa la pista, sin convertir nada.

    Se cuenta sobre las notas `normal`, el mismo filtro que `_contar_notas` y que
    `_convertir`: una ligadura alarga una nota que ya existe y una nota muerta no
    entra, asi que ninguna de las dos puede aportar un traste que las normales no
    tengan.

    Lo usan los DOS caminos -listar y leer- y a proposito: el traste maximo entra en
    la clave del perfil a medida (`_clave_de_la_afinacion`), asi que si cada camino
    lo calculase a su manera, listar una cancion podria dar de alta
    `a_medida_..._22t` e importarla `a_medida_..._24t`, y el aviso de afinacion
    compararia la tuya con una clave que la pieza no va a traer. Una sola cuenta,
    una sola clave.
    """
    return max(
        (
            nota.value
            for compas in pista.measures
            for voz in compas.voices
            for beat in voz.beats
            for nota in beat.notes
            if nota.type is guitarpro.NoteType.normal
        ),
        default=0,
    )


def _clave_de_pista(pista: guitarpro.Track) -> str | None:
    """La clave de `PERFILES` de la afinacion de la pista, **dandola de alta**.

    None si la pista no declara cuerdas -percusion, o una pista sin cuerdas-: ahi no
    hay afinacion de la que hablar.

    Esta funcion es la union de los dos caminos, y la razon es un fallo medido: el
    alta del perfil colgaba solo de `pieza_desde_guitarpro`, asi que al LISTAR las
    pistas de una cancion en una afinacion rara el perfil todavia no existia,
    `servidor/canciones.afinacion_de` devolvia `clave: None` y la pantalla decia «no
    tengo ningun perfil al que afinarte». Es decir: el aviso de afinacion fallaba en
    el unico caso en el que hacia falta -con una afinacion de fabrica ya funcionaba-
    y empezaba a funcionar a la segunda vez que abrias la cancion, que es como no
    funcionar.

    Listar las pistas de una cancion es un acto de intencion igual que importarla:
    el usuario la ha abierto. Asi que el alta se hace en los dos sitios, y como es
    `registrar_perfil` quien la hace -con una clave derivada de las cuerdas y un
    `setdefault`-, hacerla dos veces no deja dos entradas.
    """
    if pista.isPercussionTrack or not pista.strings:
        return None
    traste_maximo = _traste_maximo(pista)
    # El nombre que se le da al perfil es provisional: `registrar_perfil` guarda uno
    # derivado de las cuerdas, porque la clave la comparten todas las canciones con
    # la misma afinacion y el nombre no puede depender de cual se importo primero.
    perfil = perfil_desde_midis(
        f"Afinación de '{pista.name.strip() or 'la pista'}'",
        _cuerdas_de_grave_a_aguda(pista),
        trastes=max(_trastes_declarados(pista), traste_maximo),
    )
    return _clave_de_la_afinacion(perfil, traste_maximo)


def _clave_de_la_afinacion(perfil: PerfilAfinacion, traste_maximo: int) -> str:
    """La clave de `PERFILES` con la que guardar esta afinacion.

    Decision sobre `Track.fretCount`: `clave_de_perfil` compara solo frecuencias y
    descarta los trastes, asi que una guitarra que declara 24 trastes en afinacion
    estandar se reconoce como "guitarra_estandar", que tiene 22. Se acepta esa
    perdida -el perfil conocido es el que entiende el resto del programa, y aqui no
    digitamos nada: el traste lo da el archivo- salvo cuando la pista toca por
    encima del mastil del perfil conocido. Entonces el perfil conocido seria
    mentira, y se da de alta uno a medida con los trastes que declara la pista.
    """
    conocida = clave_de_perfil(perfil)
    if conocida is not None and PERFILES[conocida].trastes >= traste_maximo:
        return conocida
    return registrar_perfil(perfil)


def pieza_desde_guitarpro(ruta: Path | str, numero_pista: int) -> Pieza:
    """La pista `numero_pista` (empezando en 1) del archivo, como `Pieza`."""
    ruta = Path(ruta)
    cancion = _abrir(ruta)
    pistas = _describir(cancion)
    if not 1 <= numero_pista <= len(cancion.tracks):
        disponibles = ", ".join(
            f"{pista.numero} ({pista.nombre})" for pista in pistas
        )
        raise ValueError(
            f"La pista {numero_pista} no existe en '{ruta.name}'. "
            f"Las que hay son: {disponibles or 'ninguna'}."
        )
    descripcion = pistas[numero_pista - 1]
    pista = cancion.tracks[numero_pista - 1]
    # Una pista sin notas se importa: es una pieza vacia, no un error. Lo que no se
    # puede es importar percusion ni una pista sin cuerdas, porque entonces
    # `Note.string` no quiere decir nada.
    if pista.isPercussionTrack or not pista.strings:
        raise ValueError(
            f"La pista {numero_pista} ('{descripcion.nombre}') no se puede importar: "
            f"{descripcion.motivo_no_usable}"
        )

    # Solo gp5 normaliza el cierre de repeticion al leerlo; ver `_veces_que_se_toca`.
    normalizado = cancion.versionTuple[0] >= 5
    notas, secciones = _convertir(
        pista, _orden_de_compases(pista.measures, normalizado)
    )
    # La afinacion es la que ya trae la DESCRIPCION, es decir la que publico el
    # listado: no se vuelve a calcular aqui. Antes se llamaba otra vez a
    # `_clave_de_pista` -la misma funcion, asi que daba lo mismo-, pero una sola
    # llamada deja dicho en el codigo lo que el aviso necesita: la clave del listado
    # y la de la pieza son el MISMO valor, no dos cuentas que coinciden. Aqui no
    # puede ser None: las dos pistas que no declaran cuerdas ya se han rechazado
    # arriba, y son las unicas para las que `_clave_de_pista` no da clave.
    clave = descripcion.perfil_clave
    assert clave is not None
    compas = _compas(cancion.measureHeaders[0])
    return Pieza(
        nombre=cancion.title.strip() or ruta.stem,
        perfil=clave,
        tempo=cancion.tempo,
        compas=compas,
        notas=notas,
        secciones=secciones,
        tempo_variable=_tempo_variable(cancion),
        compas_variable=any(
            _compas(cabecera) != compas for cabecera in cancion.measureHeaders
        ),
    )
