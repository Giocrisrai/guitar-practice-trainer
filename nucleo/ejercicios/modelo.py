"""Vocabulario comun de los ejercicios.

Las cuatro familias de ejercicios producen esta misma estructura. Esa es la razon
de que el evaluador y la pantalla se escriban una sola vez: si cada familia
trajera su propio formato, harian falta cuatro evaluadores.
"""

from dataclasses import dataclass

import numpy as np

from nucleo.musica import Posicion, nombre_de_midi

# A partir de cuantos intentos se considera que una nota costo trabajo.
INTENTOS_NOTA_DIFICIL = 3

# Minimo de notas acertadas para que la regularidad signifique algo: con dos
# ataques solo hay un intervalo y su desviacion tipica es siempre cero.
MINIMO_NOTAS_REGULARIDAD = 3


@dataclass(frozen=True)
class NotaEsperada:
    """Una nota que el ejercicio pide tocar.

    posiciones es una tupla y no una sola posicion a proposito: un Mi puede
    tocarse en varios sitios del mastil, y el ejercicio no debe exigir uno
    concreto salvo que el generador lo restrinja.

    pulsos es la duracion en pulsos de metronomo; el modo por turnos no la usa,
    pero el modo en tiempo real la necesitara y guardarla ahora no cuesta nada.

    referencia_midi es la nota que el software hace sonar antes de pedir esta, y
    es None en los ejercicios donde no suena nada. La necesita el entrenamiento
    de oido: "esto es un Do, tocame la tercera mayor".
    """

    midi: int
    posiciones: tuple[Posicion, ...]
    pulsos: float = 1.0
    referencia_midi: int | None = None

    @property
    def nombre(self) -> str:
        """Nombre en notacion cientifica, por ejemplo "E2"."""
        return nombre_de_midi(self.midi)

    def a_dict(self) -> dict:
        return {
            "midi": self.midi,
            "nombre": self.nombre,
            "posiciones": [{"cuerda": p.cuerda, "traste": p.traste} for p in self.posiciones],
            "pulsos": self.pulsos,
            "referencia_midi": self.referencia_midi,
        }


@dataclass(frozen=True)
class Ejercicio:
    """Un ejercicio generado: que tocar, en que orden y a que tempo."""

    clave: str
    nombre: str
    descripcion: str
    notas: tuple[NotaEsperada, ...]
    tempo: int
    perfil: str

    def __len__(self) -> int:
        return len(self.notas)

    def a_dict(self) -> dict:
        return {
            "clave": self.clave,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "notas": [n.a_dict() for n in self.notas],
            "tempo": self.tempo,
            "perfil": self.perfil,
        }


@dataclass(frozen=True)
class IntentoNota:
    """Lo ocurrido con una nota del ejercicio.

    cents es None cuando la nota NO se acerto. No es cero: cero significa que se
    acerto perfectamente afinada, y confundir ambos falsearia el informe.
    """

    indice: int
    midi: int
    intentos: int
    cents: float | None
    instante: float | None
    ayuda_mostrada: bool = False

    @property
    def nombre(self) -> str:
        return nombre_de_midi(self.midi)

    @property
    def acertada(self) -> bool:
        return self.cents is not None

    @property
    def a_la_primera(self) -> bool:
        """Acertada al primer intento y SIN la ayuda del mastil puesta.

        La ayuda tiene un disparador temporal, no solo el de los cinco fallos,
        asi que puede estar visible con `intentos == 1`. Acertar leyendo la
        respuesta resaltada en el mastil no es acertar a la primera, y contarlo
        como tal falsearia `aciertos_a_la_primera`, que es la cifra con la que el
        alumno mide su progreso.
        """
        return self.acertada and self.intentos == 1 and not self.ayuda_mostrada

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "midi": self.midi,
            "nombre": self.nombre,
            "intentos": self.intentos,
            "cents": None if self.cents is None else round(self.cents, 1),
            "instante": self.instante,
            "ayuda_mostrada": self.ayuda_mostrada,
        }


@dataclass(frozen=True)
class ResultadoEjercicio:
    """El informe que se muestra al terminar."""

    ejercicio: str
    notas: tuple[IntentoNota, ...]
    completado: bool

    @property
    def _acertadas(self) -> tuple[IntentoNota, ...]:
        return tuple(n for n in self.notas if n.acertada)

    @property
    def aciertos_a_la_primera(self) -> int:
        """Cuantas notas salieron al primer intento."""
        return sum(1 for n in self.notas if n.a_la_primera)

    @property
    def desviacion_mediana_cents(self) -> float | None:
        """Mediana de la desviacion de las notas acertadas, o None si no hay ninguna.

        Se usa la mediana y no la media por el mismo motivo que en el suavizado del
        afinador: un golpe desafinado aislado no debe definir la sesion entera.
        """
        acertadas = self._acertadas
        if not acertadas:
            return None
        return float(np.median([n.cents for n in acertadas]))

    @property
    def notas_dificiles(self) -> tuple[IntentoNota, ...]:
        """Notas que costaron tres intentos o mas: donde conviene insistir."""
        return tuple(n for n in self.notas if n.intentos >= INTENTOS_NOTA_DIFICIL)

    @property
    def regularidad_ms(self) -> float | None:
        """Desviacion tipica de los intervalos entre onsets, en milisegundos.

            regularidad = sqrt( (1/n) · Σ (Δt_i − mean(Δt))² ) · 1000
            con Δt_i = t[i+1] − t[i],  n = len(Δt)

        Mide constancia, no velocidad: tocar lento y parejo da un numero bajo, que
        es justo lo que interesa al practicar. Devuelve None con menos de tres
        notas acertadas, porque con dos solo hay un intervalo y su desviacion
        tipica es siempre cero, lo que fingiria una regularidad perfecta.

        Es la desviacion tipica POBLACIONAL: `np.std` usa `ddof=0`, es decir
        divide por n y no por n−1. Con 2 o 3 intervalos la diferencia frente a
        `ddof=1` no es un detalle (el factor sqrt(n/(n−1)) vale 1.41 con n=2 y
        1.22 con n=3), asi que la cifra del informe no es comparable con la
        desviacion cuasi-insesgada que da, por ejemplo, una hoja de calculo con
        DESVEST. Se elige `ddof=0` porque aqui los intervalos tocados NO son una
        muestra de una poblacion mayor: son todos los intervalos de este
        ejercicio, y lo que se describe es exactamente esa ejecucion.

        Todos los `instante` que entran aqui son el MISMO tipo de onset,
        independientemente del camino por el que el evaluador resolviera cada
        nota: el instante del ataque de energia siempre que hubo uno (ver
        `_onset_camino_b` en `evaluacion.py`). Mezclar el ataque con el primer
        cuadro de tono creible, que en una guitarra real llega decenas de
        milisegundos despues, metia en esta cifra un sesgo del orden de lo que
        pretende medir.
        """
        instantes = [n.instante for n in self._acertadas if n.instante is not None]
        if len(instantes) < MINIMO_NOTAS_REGULARIDAD:
            return None
        intervalos = np.diff(np.array(instantes, dtype=np.float64))
        return float(np.std(intervalos) * 1000.0)

    def a_dict(self) -> dict:
        mediana = self.desviacion_mediana_cents
        regularidad = self.regularidad_ms
        return {
            "ejercicio": self.ejercicio,
            "completado": self.completado,
            "notas": [n.a_dict() for n in self.notas],
            "aciertos_a_la_primera": self.aciertos_a_la_primera,
            "desviacion_mediana_cents": None if mediana is None else round(mediana, 1),
            "regularidad_ms": None if regularidad is None else round(regularidad, 1),
            "notas_dificiles": [n.a_dict() for n in self.notas_dificiles],
        }
