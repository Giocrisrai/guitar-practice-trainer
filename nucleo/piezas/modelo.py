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

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "perfil": self.perfil,
            "tempo": self.tempo,
            "compas": list(self.compas),
            "duracion_pulsos": self.duracion_pulsos,
            "notas": [nota.a_dict() for nota in self.notas],
        }
