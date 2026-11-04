"""Encadena compuerta de ruido, detector de tono, suavizado y traducción musical.

Es el único objeto con estado del análisis: el suavizador necesita recordar las
últimas detecciones. Todo lo que hay debajo son funciones puras.
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from nucleo.afinaciones import PerfilAfinacion
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS, nivel_dbfs
from nucleo.analisis.registro import obtener
from nucleo.musica import (
    Posicion,
    esta_afinada,
    frecuencia_a_midi,
    frecuencia_a_nota,
    posiciones_en_mastil,
)


# Cada cuánto se analiza una ventana, en segundos. Es la CADENCIA DE PRODUCCIÓN, y
# vive aquí -y no en quien alimenta el análisis- porque hay dos alimentadores: el
# hilo de trabajo del servidor (`servidor/sesion.py`, que la importa con el nombre
# `INTERVALO_ANALISIS`) y la cadena directa del gemelo digital
# (`nucleo/gemelo/cadena.py`), que mete audio por la ruta real en tiempo virtual.
# Con una copia en cada sitio, el gemelo verificaría una cadencia que producción no
# usa, y lo haría en silencio.
#
# Por qué 21 ms: 512/48000 ≈ 10,67 ms es lo que tarda en llegar un bloque, y 21 ms
# son unos 1008, es decir dos bloques. No hace falta analizar a la cadencia exacta
# de los bloques, porque la emisión posterior hacia la interfaz va a 30 Hz (unos
# 33 ms) y analizar más a menudo que eso no añadiría información visible, solo
# gastaría CPU.
#
# **NO se cambia sin revisar el detector de pulsaciones.** Las constantes de
# `nucleo/ejercicios/pulsaciones.py` están acopladas a este número y lo dice por
# escrito: `CUADROS_PARA_NOTA_ESTABLE = 3` son 63 ms a 21 ms por cuadro y 32 ms a
# 10,67 ms. Los mismos cuadros representan más tiempo con un intervalo mayor y
# menos con uno menor, así que quien mueva esto tiene que volver a mirar allí.
INTERVALO_DE_ANALISIS_S = 0.021

# Cuantas frecuencias entran en la mediana movil del suavizado.
#
# **ESTA ACOPLADO A `CUADROS_PARA_NOTA_ESTABLE` DEL DETECTOR DE PULSACIONES**, y
# la desigualdad que tiene que seguir siendo cierta es
#
#     CUADROS_PARA_NOTA_ESTABLE > TAMANO_SUAVIZADO // 2
#
# De donde sale: una mediana de n no gira hasta que `n // 2 + 1` de sus entradas
# son nuevas, asi que tras un cambio de altura publica la altura VIEJA durante
# `n // 2` cuadros. Con n=5 son 2 cuadros. El camino A del detector
# (`nucleo/ejercicios/pulsaciones.py`) solo sella cuando la nota lleva
# `cuadros_para_nota_estable` cuadros creibles seguidos, asi que si la racha
# vieja alcanzara esa cifra el detector volveria a sellar el ataque de una nota
# con la altura de la anterior: es el defecto que la Task 6c arreglo, y perder
# esta desigualdad lo devuelve entero.
#
# Se cuenta en CUADROS por los dos lados, asi que la desigualdad no depende de la
# frecuencia de muestreo ni del tempo. Lo que SI depende del perfil es el otro
# sumando de la racha vieja -los cuadros cuya ventana cruza la frontera entre dos
# notas-, y con el perfil de bajo ese sumando ya se come el margen: ver la
# medicion en el docstring de `nucleo/ejercicios/pulsaciones.py`. La desigualdad
# esta afirmada en
# `tests/test_pulsaciones.py::test_la_racha_estable_supera_al_suavizador`.
TAMANO_SUAVIZADO = 5


class Suavizador:
    """Mediana móvil sobre las últimas frecuencias detectadas.

    Se usa mediana y no media a propósito. Los fallos de un detector de tono no son
    ruido alrededor del valor correcto: son saltos aislados y grandes, casi siempre
    a la octava. La media los reparte y contamina el resultado; la mediana los
    descarta sin más.

    Devuelve None hasta tener el historial completo, para no publicar una lectura
    apoyada en menos muestras de las previstas.
    """

    def __init__(self, tamano: int = TAMANO_SUAVIZADO) -> None:
        if tamano < 1:
            raise ValueError("El tamaño del suavizado debe ser al menos 1")
        self._tamano = tamano
        self._historial: deque[float] = deque(maxlen=tamano)

    def agregar(self, frecuencia: float) -> float | None:
        """Añade una detección y devuelve la mediana, o None si falta historial."""
        self._historial.append(frecuencia)
        if len(self._historial) < self._tamano:
            return None
        return float(np.median(self._historial))

    def reiniciar(self) -> None:
        """Vacía el historial. Se llama al entrar en silencio."""
        self._historial.clear()


@dataclass(frozen=True)
class ResultadoAnalisis:
    """Lo que el análisis publica por cada ventana procesada.

    estado es "nota" o "silencio". En silencio, nota y cents son None y posiciones
    está vacía: el análisis no rellena con el último valor conocido.
    """

    estado: str
    frecuencia: float
    confianza: float
    nivel_db: float
    nota: str | None = None
    cents: float | None = None
    posiciones: list[Posicion] = field(default_factory=list)
    cuerda_objetivo: int | None = None
    afinada: bool = False

    def a_dict(self) -> dict:
        """Forma exacta del mensaje que viaja por WebSocket."""
        return {
            "estado": self.estado,
            "frecuencia": round(self.frecuencia, 2),
            "nota": self.nota,
            "cents": None if self.cents is None else round(self.cents, 1),
            "confianza": round(self.confianza, 3),
            "nivel_db": round(self.nivel_db, 1),
            "posiciones": [
                {"cuerda": p.cuerda, "traste": p.traste} for p in self.posiciones
            ],
            "cuerda_objetivo": self.cuerda_objetivo,
            "afinada": self.afinada,
        }


class Analizador:
    """Convierte ventanas de audio en resultados musicales."""

    def __init__(
        self,
        perfil: PerfilAfinacion,
        frecuencia_muestreo: int = 48000,
        umbral_ruido_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS,
        referencia_a4: float = 440.0,
        confianza_minima: float = 0.75,
        nombre_detector: str = "yin",
        tamano_suavizado: int = TAMANO_SUAVIZADO,
    ) -> None:
        self.perfil = perfil
        self.frecuencia_muestreo = frecuencia_muestreo
        self.umbral_ruido_dbfs = umbral_ruido_dbfs
        self.referencia_a4 = referencia_a4
        self.confianza_minima = confianza_minima
        self._detector = obtener(nombre_detector)
        self._suavizador = Suavizador(tamano_suavizado)

        # El rango de búsqueda sale del perfil: un margen bajo la cuerda más grave
        # para poder ver que está desafinada por abajo, y hasta el último traste de
        # la más aguda con margen por arriba.
        self._frecuencia_minima = perfil.frecuencia_minima * 0.85
        aguda = max(cuerda.frecuencia for cuerda in perfil.cuerdas)
        self._frecuencia_maxima = aguda * 2 ** (perfil.trastes / 12.0) * 1.15

    @property
    def tamano_ventana(self) -> int:
        """Muestras por ventana, derivadas del perfil."""
        return self.perfil.tamano_ventana(self.frecuencia_muestreo)

    def _silencio(
        self, nivel: float, confianza: float = 0.0, reiniciar: bool = True
    ) -> ResultadoAnalisis:
        """Resultado de silencio.

        `reiniciar` distingue los dos motivos por los que se calla. Vaciar el
        historial solo tiene sentido cuando de verdad se dejó de tocar: si un
        cuadro dudoso en mitad de una nota sostenida reiniciase el suavizador, se
        tirarían ~107 ms de historial y la aguja parpadearía justo mientras el
        usuario afina, que es la función principal de la etapa.
        """
        if reiniciar:
            self._suavizador.reiniciar()
        return ResultadoAnalisis(
            estado="silencio", frecuencia=0.0, confianza=confianza, nivel_db=nivel
        )

    def _cuerda_mas_cercana(self, midi: int) -> int:
        """Cuerda al aire del perfil más próxima en semitonos a la nota detectada."""
        return min(
            self.perfil.cuerdas,
            key=lambda c: abs(midi - round(frecuencia_a_midi(c.frecuencia, self.referencia_a4))),
        ).numero

    def procesar(self, muestras: np.ndarray) -> ResultadoAnalisis:
        """Analiza una ventana y devuelve el resultado.

        Dos puertas sucesivas devuelven silencio en vez de inventar: la energía y la
        confianza del detector. Una lectura dudosa no se muestra atenuada, no se
        muestra; enseñar al usuario a desconfiar de la pantalla es peor que callar.
        """
        nivel = nivel_dbfs(muestras)
        if nivel <= self.umbral_ruido_dbfs:
            return self._silencio(nivel)

        tono = self._detector(
            muestras,
            self.frecuencia_muestreo,
            self._frecuencia_minima,
            self._frecuencia_maxima,
        )
        if tono.confianza < self.confianza_minima or tono.frecuencia <= 0.0:
            # Hay energía suficiente: el usuario sigue tocando y este cuadro
            # simplemente no se pudo leer. Se calla, pero se conserva el
            # historial del suavizado (ver _silencio).
            return self._silencio(nivel, tono.confianza, reiniciar=False)

        suavizada = self._suavizador.agregar(tono.frecuencia)
        if suavizada is None:
            return ResultadoAnalisis(
                estado="silencio",
                frecuencia=0.0,
                confianza=tono.confianza,
                nivel_db=nivel,
            )

        nota = frecuencia_a_nota(suavizada, self.referencia_a4)
        return ResultadoAnalisis(
            estado="nota",
            frecuencia=suavizada,
            confianza=tono.confianza,
            nivel_db=nivel,
            nota=nota.nombre,
            cents=nota.cents,
            posiciones=posiciones_en_mastil(nota.midi, self.perfil),
            cuerda_objetivo=self._cuerda_mas_cercana(nota.midi),
            afinada=esta_afinada(nota.cents),
        )
