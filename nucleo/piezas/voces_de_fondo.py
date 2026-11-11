"""Las notas de las pistas que el usuario NO esta tocando, para que suenen de fondo.

Tocar una cancion a solas es tocar un trozo de cancion: falta el bajo, falta la
bateria, falta la voz. Lo que hace falta para que suene el resto es poco y muy
concreto -alturas e instantes- y es justo lo que `Pieza` no sabe guardar.

**Por que este modulo existe y no se reusa `importar`.** `Pieza` exige CUERDA Y
TRASTE por nota, asi que los lectores de MIDI y de MusicXML digitan cada nota en el
mastil del usuario y lanzan `ValueError` cuando no cabe
(`desde_midi.pieza_desde_midi`, `desde_musicxml.pieza_desde_musicxml`). Eso esta
bien para la pista que se toca -no se puede seguir una tablatura que no existe- y es
imposible para las demas: un piano, una voz o unas cuerdas no caben en seis cuerdas
y casi nunca lo haran. Pero para SONAR no hay que digitar nada.

De ahi la regla de este modulo, que es su razon de ser: **no construye `Pieza`, no
llama a `digitacion.py` y no mira afinaciones**. Por eso no puede rechazar una pista
por no caber en el mastil: nunca pregunta si cabe. Lo que si usa, formato por
formato, es el MISMO parser que su lector hermano, para que las notas de fondo y las
de la pista que se toca salgan del mismo sitio y no se desincronicen.

Lo que si se excluye es lo que no tiene nada que sonar: la percusion -sin alturas- y
las pistas vacias. Y se excluye DICIENDO POR QUE, con la frase que ya escribe el
lector del formato (`desde_guitarpro._motivo_no_usable`,
`desde_midi._motivo_no_usable`, la descripcion de `desde_musicxml`), porque el
usuario tiene que ver que su bateria esta ahi y por que no se le ofrece, igual que
en el listado de pistas.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nucleo.piezas.lectores import _extension

# Una tablatura de texto no lleva tempo escrito en ninguna parte: lo pone quien la
# lee (`desde_ascii.pieza_desde_ascii`, cuyo parametro `tempo` vale 90 por omision).
# Este es el mismo numero, y esta aqui para no dejar el campo sin valor; quien tenga
# la `Pieza` del usuario debe preferir el tempo de ella, que es el que el usuario
# eligio.
TEMPO_DE_LA_TABLATURA = 90


@dataclass(frozen=True)
class NotaDeFondo:
    """Una nota que solo tiene que sonar: altura e instante, sin sitio en el mastil.

    `midi` es `float` y no `int` a proposito: aqui no hay traste que redondear, asi
    que una altura que no sea un semitono exacto -una cuerda desafinada a proposito,
    un bend escrito como microtono- cabe sin tener que mentir. Los parsers de hoy
    dan enteros.
    """

    midi: float
    inicio_pulsos: float
    duracion_pulsos: float

    @property
    def fin_pulsos(self) -> float:
        return self.inicio_pulsos + self.duracion_pulsos


@dataclass(frozen=True)
class VozDeFondo:
    """Una pista del archivo lista para sonar, con su nombre y su instrumento.

    El nombre y el instrumento no los necesita el sintetizador: los necesita el
    usuario, para subir el bajo y bajar la guitarra de acompañamiento.
    """

    nombre: str
    instrumento: str
    notas: tuple[NotaDeFondo, ...]


@dataclass(frozen=True)
class FondoDisponible:
    """Todo lo que puede sonar detras del usuario en un archivo.

    voces: una por pista que puede sonar, en el orden del archivo y SIN la pista que
        el usuario toca.
    tempo: el del archivo, en negras por minuto. Es el mismo que trae la `Pieza` de
        la pista importada, porque sale del mismo sitio.
    excluidas: (nombre, motivo) de las pistas que NO pueden sonar, con la frase
        escrita para el usuario. La pista que el usuario toca no esta aqui: no esta
        rechazada, simplemente la toca el.
    """

    voces: tuple[VozDeFondo, ...]
    tempo: int
    excluidas: tuple[tuple[str, str], ...]


def _voces_de_guitarpro(ruta: Path | str, pista_excluida: int) -> FondoDisponible:
    """El fondo de un archivo de Guitar Pro.

    Las notas las da `desde_guitarpro._convertir`, la misma funcion que usa el
    lector: trae ya resueltas las tres trampas del formato -el tick absoluto del
    primer compas, el orden de las cuerdas y las ligaduras, que alargan una nota en
    vez de atacar otra- y expande las repeticiones con `_orden_de_compases`. Si el
    fondo las leyera por su cuenta, sonaria desplazado respecto a la pista que el
    usuario esta tocando, que es el unico error que no se puede permitir aqui.

    Lo que NO se usa es `_describir`: da de alta en `PERFILES` la afinacion de cada
    pista (ver `desde_guitarpro._clave_de_pista`), y eso es trabajo del aviso de
    afinacion, que habla de la pista que se toca. Registrar la "afinacion" de un
    piano porque suena de fondo seria ofrecerle al usuario afinarse a el.
    """
    from nucleo.piezas.desde_guitarpro import (
        _abrir,
        _contar_notas,
        _convertir,
        _instrumento,
        _motivo_no_usable,
        _orden_de_compases,
    )

    cancion = _abrir(ruta)
    # Solo gp5 normaliza el cierre de repeticion al leerlo; lo explica
    # `desde_guitarpro._veces_que_se_toca`.
    normalizado = cancion.versionTuple[0] >= 5
    voces: list[VozDeFondo] = []
    excluidas: list[tuple[str, str]] = []
    for numero, pista in enumerate(cancion.tracks, start=1):
        if numero == pista_excluida:
            continue
        nombre = pista.name.strip() or f"Pista {numero}"
        motivo = _motivo_no_usable(pista, _contar_notas(pista))
        if motivo is not None:
            excluidas.append((nombre, motivo))
            continue
        notas, _ = _convertir(
            pista, _orden_de_compases(pista.measures, normalizado)
        )
        voces.append(
            VozDeFondo(
                nombre=nombre,
                instrumento=_instrumento(pista),
                notas=tuple(
                    NotaDeFondo(
                        midi=nota.midi,
                        inicio_pulsos=nota.inicio_pulsos,
                        duracion_pulsos=nota.duracion_pulsos,
                    )
                    for nota in notas
                ),
            )
        )
    return FondoDisponible(tuple(voces), cancion.tempo, tuple(excluidas))


def _voces_de_midi(ruta: Path | str, pista_excluida: int) -> FondoDisponible:
    """El fondo de un archivo MIDI.

    Es el caso que mas se nota: un MIDI trae la cancion entera repartida en pistas y
    `importar` solo puede traer las que caben en una guitarra. Las notas las da
    `desde_midi._notas_de`, que resuelve los delta y el `note_on` con velocidad cero,
    y el tempo sale de todas las pistas (`_metas`) porque suele vivir en la pista 0
    aunque la musica este en otra.
    """
    import mido

    from nucleo.piezas.desde_midi import (
        CANAL_PERCUSION,
        TEMPO_POR_DEFECTO,
        _abrir,
        _canales,
        _contar_notas,
        _instrumento,
        _metas,
        _motivo_no_usable,
        _notas_de,
    )

    ruta = Path(ruta)
    archivo = _abrir(ruta)
    ticks_por_pulso = archivo.ticks_per_beat
    if ticks_por_pulso <= 0:
        # El mismo rechazo que `pieza_desde_midi`: sin pulsos no hay nada que medir
        # en pulsos, y no es un problema de afinacion sino del reloj del archivo.
        raise ValueError(
            f"'{ruta.name}' mide el tiempo en SMPTE y no en pulsos: no se puede "
            "importar."
        )
    voces: list[VozDeFondo] = []
    excluidas: list[tuple[str, str]] = []
    for numero, pista in enumerate(archivo.tracks, start=1):
        if numero == pista_excluida:
            continue
        nombre = (pista.name or "").strip() or f"Pista {numero}"
        motivo = _motivo_no_usable(pista, _contar_notas(pista))
        if motivo is not None:
            excluidas.append((nombre, motivo))
            continue
        # Una pista de percusion ya se ha ido por el motivo de arriba; esta
        # comprobacion no sobra, deja dicho que `_notas_de` no distingue canales y
        # que la bateria no debe colarse por aqui si el motivo cambiara.
        assert CANAL_PERCUSION not in _canales(pista)
        voces.append(
            VozDeFondo(
                nombre=nombre,
                instrumento=_instrumento(pista),
                notas=tuple(
                    NotaDeFondo(
                        midi=midi, inicio_pulsos=inicio, duracion_pulsos=duracion
                    )
                    for midi, inicio, duracion in _notas_de(pista, ticks_por_pulso)
                ),
            )
        )
    tempos = [mensaje.tempo for _, mensaje in _metas(archivo, "set_tempo")]
    tempo = round(mido.tempo2bpm(tempos[0])) if tempos else TEMPO_POR_DEFECTO
    return FondoDisponible(tuple(voces), tempo, tuple(excluidas))


def _voces_de_musicxml(ruta: Path | str, pista_excluida: int) -> FondoDisponible:
    """El fondo de un archivo MusicXML.

    Las partes se describen sobre la obra SIN expandir y las notas se leen de la
    expandida, en ese orden y por separado, igual que `pieza_desde_musicxml`: la
    descripcion es lo que el usuario ve y la expansion es lo que suena.

    El tempo se busca en la obra entera y no en una parte: aqui no hay una parte
    elegida, y la indicacion metronomica suele estar escrita en la primera. Con una
    cancion de un solo tempo -el caso normal- es el mismo numero que trae la pieza.
    """
    from music21 import tempo as tempos_m21

    from nucleo.piezas.desde_musicxml import (
        TEMPO_POR_DEFECTO,
        _abrir,
        _crudas,
        _describir,
        _partes,
    )

    ruta = Path(ruta)
    obra = _abrir(ruta)
    descripciones = _describir(obra)
    try:
        expandida = obra.expandRepeats()
    except Exception as error:
        raise ValueError(
            f"Las repeticiones de '{ruta.name}' no se pueden expandir: {error}"
        ) from None
    partes = _partes(expandida)
    voces: list[VozDeFondo] = []
    excluidas: list[tuple[str, str]] = []
    for descripcion, parte in zip(descripciones, partes, strict=True):
        if descripcion.numero == pista_excluida:
            continue
        if descripcion.motivo_no_usable is not None:
            excluidas.append((descripcion.nombre, descripcion.motivo_no_usable))
            continue
        voces.append(
            VozDeFondo(
                nombre=descripcion.nombre,
                instrumento=descripcion.instrumento,
                notas=tuple(
                    NotaDeFondo(
                        midi=cruda["midi"],
                        inicio_pulsos=cruda["inicio"],
                        duracion_pulsos=cruda["duracion"],
                    )
                    for cruda in _crudas(parte)
                ),
            )
        )
    plano = expandida.flatten()
    bpms = [
        round(marca.getQuarterBPM())
        for marca in plano.getElementsByClass(tempos_m21.MetronomeMark)
        if marca.getQuarterBPM()
    ]
    tempo = bpms[0] if bpms else TEMPO_POR_DEFECTO
    return FondoDisponible(tuple(voces), tempo, tuple(excluidas))


def _voces_de_ascii(ruta: Path | str, pista_excluida: int) -> FondoDisponible:
    """Una tablatura de texto no tiene fondo: es UNA pista, la del usuario.

    Vacio y no una excepcion: el programa ofrece el fondo para cualquier archivo, y
    «esta cancion no trae nada que suene detras» es una respuesta, no un fallo. El
    archivo no se abre -no hay nada que buscar en el- asi que `pista_excluida` da
    igual.
    """
    return FondoDisponible((), TEMPO_DE_LA_TABLATURA, ())


# El despacho por extension, con las MISMAS claves que `lectores._LECTORES` y
# `lectores._CONVERSORES`: una extension que se puede listar e importar tambien se
# puede oir de fondo. El import de cada parser va DENTRO de su funcion, por lo mismo
# que `lectores._diferido` existe: abrir un .gp5 no debe pagar el arranque de
# music21, que es lento. Aqui no hace falta el ayudante porque las funciones son de
# este modulo y no de los lectores; lo diferido es el parser, no la funcion.
_VOCES: dict[str, Callable[[Path | str, int], FondoDisponible]] = {
    **dict.fromkeys((".gp3", ".gp4", ".gp5"), _voces_de_guitarpro),
    **dict.fromkeys((".mid", ".midi"), _voces_de_midi),
    **dict.fromkeys((".xml", ".musicxml", ".mxl"), _voces_de_musicxml),
    **dict.fromkeys((".txt", ".tab"), _voces_de_ascii),
}


def voces_de(ruta: Path | str, pista_excluida: int) -> FondoDisponible:
    """Lo que puede sonar de fondo en `ruta` mientras el usuario toca `pista_excluida`.

    `pista_excluida` es el numero de pista que ve el usuario, empezando en 1: el
    mismo que recibe `lectores.importar`. Un numero que no corresponde a ninguna
    pista no es un error -nadie reserva nada y suena el archivo entero-, porque este
    modulo no decide que pista toca el usuario: solo aparta la que le digan.

    No lanza `ValueError` por una pista que no quepa en ninguna afinacion, que es el
    punto entero del modulo. Si lo lanza cuando el archivo no se puede abrir, cuando
    la extension no se sabe leer (la misma frase que `lectores`) o cuando el MIDI
    mide el tiempo en SMPTE: ahi no hay notas que sacar.
    """
    return _VOCES[_extension(ruta, _VOCES)](ruta, pista_excluida)
