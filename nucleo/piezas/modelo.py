"""Una pieza: notas con sitio en el mastil y sitio en el tiempo.

A diferencia de `Ejercicio`, que da TODAS las posiciones donde vive cada nota y
deja que el alumno elija, aqui cada nota trae UNA: el carril tiene que dibujarla
en algun sitio. Y a diferencia de el, el tiempo es absoluto.

El tiempo se guarda en PULSOS y no en segundos para que bajar el tempo y
practicar lento sea cambiar un numero, y no reescribir la pieza entera.

Este modulo no importa nada de `nucleo.ejercicios`: una pieza leida de un archivo
de Guitar Pro no tiene nada que ver con un ejercicio generado. El unico puente
entre ambos vive en `desde_ejercicio.py`.
"""

from dataclasses import dataclass

from nucleo.afinaciones import PERFILES
from nucleo.musica import nombre_de_midi


def pulsos_a_segundos(pulsos: float, tempo: int) -> float:
    """Pulsos a segundos: segundos = pulsos * 60 / tempo."""
    if tempo <= 0:
        raise ValueError(f"El tempo {tempo} no sirve: tiene que ser mayor que cero")
    return pulsos * 60.0 / tempo


def segundos_a_pulsos(segundos: float, tempo: int) -> float:
    """La inversa de `pulsos_a_segundos`."""
    if tempo <= 0:
        raise ValueError(f"El tempo {tempo} no sirve: tiene que ser mayor que cero")
    return segundos * tempo / 60.0


@dataclass(frozen=True)
class NotaEnPieza:
    """Una nota con cuerda, traste, instante y duracion."""

    midi: int
    cuerda: int
    traste: int
    inicio_pulsos: float
    duracion_pulsos: float

    @property
    def fin_pulsos(self) -> float:
        return self.inicio_pulsos + self.duracion_pulsos

    def a_dict(self) -> dict:
        return {
            "midi": self.midi,
            "nombre": nombre_de_midi(self.midi),
            "cuerda": self.cuerda,
            "traste": self.traste,
            "inicio_pulsos": self.inicio_pulsos,
            "duracion_pulsos": self.duracion_pulsos,
        }


@dataclass(frozen=True)
class Seccion:
    """Un trozo con nombre: "Intro", "Estribillo", "Solo".

    Viene de los marcadores del archivo -Guitar Pro los llama marcadores, MusicXML
    marcas de ensayo, MIDI marcadores de texto-, y si se tiran al importar no hay
    forma de reconstruirlas despues.

    **SE USAN, y desde la etapa 3c.** El camino entero es: `compases_de_la_seccion`
    (`nucleo/piezas/compases.py`) convierte el indice de una seccion en el
    `(primer_compas, ultimo_compas)` con que se arma un tramo;
    `SesionCarril._secciones_en_compases` (`servidor/piezas.py`) hace esa
    conversion para todas y las publica ya hechas, y el selector «Seccion» de
    `interfaz/src/ControlesEstudio.tsx` las ofrece en una lista y pone el tramo de
    la pasada en la que se elija. La conversion vive en el nucleo y viaja hecha a
    proposito: la interfaz no repite la formula.

    Se piden por INDICE y no por nombre porque los nombres se repiten -una cancion
    con dos estribillos trae dos secciones llamadas "Estribillo"-; la razon larga
    esta en `compases_de_la_seccion`.
    """

    nombre: str
    inicio_pulsos: float

    def a_dict(self) -> dict:
        return {"nombre": self.nombre, "inicio_pulsos": self.inicio_pulsos}


@dataclass(frozen=True)
class Pieza:
    """Notas ordenadas en el tiempo, con la afinacion con que se escribieron.

    Dos notas pueden compartir `inicio_pulsos`: eso es un acorde, y el modelo lo
    admite a proposito. La razon es que esta clase tambien es el destino de la
    etapa 3b, que va a leer musica de verdad desde archivos Guitar Pro y
    MusicXML, y esos formatos traen acordes; rechazarlos aqui obligaria al
    importador a destrozar el archivo antes de que la nota entrara al modelo.

    Lo que esta etapa NO puede hacer es tocarlos: el carril de la etapa 3a sigue
    el sonido con un detector de tono monofonico, que no distingue dos cuerdas
    sonando a la vez. Esa restriccion vive un nivel mas arriba, en el seguidor
    (Task 4), que debe declarar que no sabe seguir un acorde en vez de fallar en
    silencio. El modelo se limita a representarlos.
    """

    nombre: str
    perfil: str
    tempo: int
    compas: tuple[int, int]
    notas: tuple[NotaEnPieza, ...]
    # Los tres llevan valor por defecto: los ejercicios de la etapa 3a construyen
    # Pieza sin ellos.
    secciones: tuple[Seccion, ...] = ()
    # El ritmo se infirio de una tablatura de texto y no es de fiar.
    ritmo_aproximado: bool = False
    # La cancion cambiaba de tempo y se tomo el primero.
    tempo_variable: bool = False
    # La cancion cambiaba de compas y se tomo el del primero. Importa porque quien
    # dibuja la partitura trocea la pieza con UN compas constante
    # (`interfaz/src/vistaEscrita.ts`): con un 3/4 en medio, las barras caen en el
    # sitio equivocado desde ahi hasta el final y nada avisa.
    compas_variable: bool = False
    # La cancion traia casillas de primera y segunda vez y el expansor de
    # repeticiones no las entiende: se toca un trozo de mas. Detectarlo y
    # arreglarlo son dos cosas distintas, y esta es la primera, que es la que
    # cumple el estandar de la rama: si se detecta, se avisa. Arreglarlo es
    # rehacer el expansor de `desde_guitarpro.py` y NO es la etapa 3c (se
    # considero y se descarto: es un defecto de lectura, no de practica).
    casillas_de_repeticion: bool = False

    def __post_init__(self) -> None:
        if self.perfil not in PERFILES:
            disponibles = ", ".join(sorted(PERFILES))
            raise ValueError(f"El perfil '{self.perfil}' no existe. Opciones: {disponibles}")
        pulsos_a_segundos(1.0, self.tempo)  # valida el tempo con el mismo mensaje
        anterior = None
        for nota in self.notas:
            if nota.duracion_pulsos <= 0:
                raise ValueError(
                    f"La nota {nombre_de_midi(nota.midi)} tiene duracion "
                    f"{nota.duracion_pulsos}: tiene que ser mayor que cero"
                )
            if anterior is not None and nota.inicio_pulsos < anterior:
                raise ValueError(
                    "Las notas tienen que venir en orden de inicio_pulsos: "
                    f"{nota.inicio_pulsos} llega despues de {anterior}"
                )
            anterior = nota.inicio_pulsos
        previa = None
        for seccion in self.secciones:
            if seccion.inicio_pulsos < 0:
                raise ValueError(
                    f"La seccion '{seccion.nombre}' empieza en {seccion.inicio_pulsos}: "
                    "no puede ser negativo"
                )
            if previa is not None and seccion.inicio_pulsos < previa:
                raise ValueError(
                    "Las secciones tienen que venir en orden de inicio_pulsos: "
                    f"{seccion.inicio_pulsos} llega despues de {previa}"
                )
            previa = seccion.inicio_pulsos

    def __len__(self) -> int:
        return len(self.notas)

    @property
    def duracion_pulsos(self) -> float:
        """Hasta donde llega la pieza, no cuanto suena.

        Es el final de la ultima nota, no la suma de las duraciones: las notas
        pueden dejar huecos entre si.
        """
        return max((nota.fin_pulsos for nota in self.notas), default=0.0)

    @property
    def duracion_s(self) -> float:
        return pulsos_a_segundos(self.duracion_pulsos, self.tempo)

    def seccion_en(self, pulsos: float) -> Seccion | None:
        """La seccion que esta sonando en ese instante, o None si no hay secciones.

        La ultima cuyo inicio no ha pasado todavia. Una pieza sin secciones devuelve
        None en todas partes, que es lo que ocurre con los ejercicios generados.
        """
        actual = None
        for seccion in self.secciones:
            if seccion.inicio_pulsos > pulsos:
                break
            actual = seccion
        return actual

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "perfil": self.perfil,
            "tempo": self.tempo,
            "compas": list(self.compas),
            "duracion_pulsos": self.duracion_pulsos,
            "notas": [nota.a_dict() for nota in self.notas],
            "secciones": [seccion.a_dict() for seccion in self.secciones],
            "ritmo_aproximado": self.ritmo_aproximado,
            "tempo_variable": self.tempo_variable,
            "compas_variable": self.compas_variable,
            "casillas_de_repeticion": self.casillas_de_repeticion,
        }
