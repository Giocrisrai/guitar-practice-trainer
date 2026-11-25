"""Deteccion de acordes por verificacion.

No transcribe: comprueba. Dada una lista de notas esperadas -que el ejercicio
genero, o que la pieza trae escritas- mide cuanta prueba hay de que cada una esta
sonando y responde con las que faltan. La spec de la etapa 2b razona por que eso
basta y por que la transcripcion polifonica libre no hace falta aqui.

Es el unico objeto con estado de la deteccion de acordes, y lo es por una razon
concreta: necesita una ventana de 8192 muestras (171 ms) para separar semitonos
graves -a E2 dos semitonos vecinos distan 4,9 Hz, y 4096 muestras dan 11,7 Hz por
bin- mientras que quien lo alimenta entrega bloques de unas 1008. De ahi el bufer
circular.
"""

from dataclasses import dataclass, field

import numpy as np

from nucleo.afinaciones import PerfilAfinacion
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS, nivel_dbfs
from nucleo.analisis.espectro import (
    ANCHO_BANDA_CENTS,
    ARMONICOS_POR_DEFECTO,
    espectro_de_magnitud,
    saliencia_de_nota,
)
from nucleo.musica import frecuencia_a_midi

# Muestras por ventana de deteccion de acordes.
#
# **NO es `PerfilAfinacion.tamano_ventana`**, y la diferencia es deliberada. El
# afinador usa 4096 porque le basta y porque menos latencia hace mejor aguja. Un
# acorde necesita separar semitonos en la zona grave, donde 4096 muestras no
# llegan: a 48 kHz dan 11,7 Hz por bin, y entre E2 (82,41) y F2 (87,31) hay 4,9.
# Con 8192 el bin baja a 5,9 Hz y las notas del acorde se distinguen.
#
# El coste es latencia: 171 ms. Es aceptable justo porque un acorde se sostiene.
# Para una escala rapida no lo seria, y por eso las dos ventanas no se unifican.
VENTANA_ACORDES = 8192

# Presencia relativa minima para dar una nota por sonada.
#
# Medido con acordes sinteticos por `tests/test_acordes.py`, con ESTE codigo y no
# con el prototipo de la spec:
#
#     Do completo          sonando min 0,71   mudas max 0,00
#     Sol completo         sonando min 0,58   mudas max 0,00
#     Do sin la 1.a        sonando min 0,71   mudas max 0,27
#     Do sin la 2.a        sonando min 0,72   mudas max 0,32
#     suena Sol, pide Do   sonando min 0,89   mudas max 0,46
#     suena Do, pide Sol   sonando min 0,71   mudas max 0,41
#
# Las cuatro primeras filas son el caso que importa -el acorde que se intenta
# tocar- y ahi el hueco va de 0,32 a 0,58. 0,45 cae en medio.
#
# **La quinta fila es un falso positivo y esta medido a proposito.** Con el Sol
# sonando y el Do pedido, el C3 que nadie toca llega a 0,46 porque su tercer y
# sexto armonico (392 Hz y 785 Hz) caen justo sobre el Sol que si suena. Subir el
# umbral para taparlo estrecharia el margen del caso que importa, asi que se deja
# y se asume la consecuencia: cuando tocas un acorde EQUIVOCADO, el veredicto
# sigue siendo correcto -faltan las otras tres notas- pero la lista de ausencias
# puede quedarse corta en una nota. Decir "ese no es el acorde" no depende de esa
# nota; decir exactamente cuales faltan, en ese caso, si.
#
# **Esta por calibrar con la guitarra del usuario.** El hueco real puede ser mas
# estrecho que el sintetico: una pastilla electrica reparte los armonicos de otra
# manera que ocho senoides con decaimiento.
#
# Para medirlo hay herramienta, no hay que estimarlo:
#
#     uv run python -m herramientas.calibrar_presencia
#
# Graba cada acorde dos veces -completo y con una cuerda apagada- y da el hueco
# real. Si sale negativo, ningun valor de esta constante sirve y lo que hay que
# revisar es `saliencia_de_nota` (nucleo/analisis/espectro.py); la herramienta lo
# dice en vez de proponer un numero. Cuando se mida, los numeros nuevos van aqui,
# al lado de la tabla sintetica de arriba, sin borrarla: la sintetica es la que
# las pruebas vigilan.
#
# **SEGUNDA MEDIDA, DEL GEMELO RASGUEANDO, y es mas dura que la de arriba.** La
# tabla sintetica suma senoides con decaimiento, todas a la misma fuerza y en el
# mismo instante. El gemelo toca las cuerdas con `cuerda_pulsada`, cada una con su
# fuerza y barridas 8 ms, que es bastante mas parecido a una mano. Medido en el
# cuadro en que el carril consulta la presencia -0,25 s despues del rasgueo, ver
# `tests/test_gemelo_rasgueo.py`-:
#
#     Do mayor (5 cuerdas)   48:0,56  52:0,70  55:0,88  60:1,00  64:0,73
#     Sol mayor (6 cuerdas)  43:0,87  47:0,40  50:0,55  55:0,94  59:0,47  67:0,70
#
# El Do entra completo con holgura. **En el Sol, las dos terceras -B2 y B3- caen al
# borde del umbral y la grave se queda fuera**, asi que un Sol bien tocado se lee
# como «te falta la quinta cuerda» durante medio segundo. La causa se ve en los
# numeros y no es el umbral: el Sol esta DOBLADO en tres octavas (43, 55, 67), la
# saliencia se normaliza contra la nota mas fuerte de todo el mastil y las terceras
# pierden esa carrera. Medio segundo mas tarde las dos pasan de 0,45, o sea que el
# problema es CUANDO se mira, no si suena.
#
# No se toca esta constante por esto, a proposito: moverla desde audio sintetico es
# exactamente lo que el parrafo de arriba dice que no se haga, y el arreglo que los
# numeros sugieren es otro -mirar unos cuantos cuadros en vez de uno solo, como ya
# hace `nucleo.ejercicios.cambios`- y necesita medidas de guitarra de verdad para
# decidirse.
UMBRAL_PRESENCIA = 0.45

# Fraccion de la ventana que tiene que estar llena antes de juzgar nada.
#
# Alimentado por bloques, el bufer arranca en ceros. Sin esta guarda los primeros
# cuadros se juzgarian sobre una ventana mayoritariamente vacia, cuyo espectro no
# es el del acorde sino el del escalon entre los ceros y la senal. Un veredicto
# asi no es dudoso: es inventado, y la etapa 2a ya fijo la regla de que una
# lectura dudosa se calla en vez de mostrarse atenuada.
FRACCION_MINIMA_LLENA = 0.9


@dataclass(frozen=True)
class ResultadoAcorde:
    """Lo que el detector publica por cada ventana.

    estado es "silencio", "incompleto" o "completo". En silencio, presencias esta
    vacio y faltan tambien: el detector no rellena con el ultimo valor conocido,
    igual que el analisis monofonico.

    No hay estado "equivocado". Un acorde equivocado es uno al que le faltan casi
    todas las notas, y `faltan` ya lo dice sin inventar una categoria mas.
    Decidir si eso se le cuenta al usuario como "te falta la primera" o como "ese
    no es el acorde" es presentacion, y la presentacion no vive en el nucleo.
    """

    estado: str
    nivel_db: float
    presencias: dict[int, float] = field(default_factory=dict)
    faltan: tuple[int, ...] = ()

    def a_dict(self) -> dict:
        """Forma exacta del mensaje que viaja por WebSocket.

        Las claves de `presencias` van como texto porque JSON no admite claves
        numericas; quien lo lea tendra que volver a convertirlas.
        """
        return {
            "estado": self.estado,
            "nivel_db": round(self.nivel_db, 1),
            "presencias": {str(k): round(v, 3) for k, v in self.presencias.items()},
            "faltan": list(self.faltan),
        }


class DetectorAcordes:
    """Comprueba si las notas esperadas de un acorde estan sonando."""

    def __init__(
        self,
        perfil: PerfilAfinacion,
        frecuencia_muestreo: int = 48000,
        ventana: int = VENTANA_ACORDES,
        umbral_ruido_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS,
        umbral_presencia: float = UMBRAL_PRESENCIA,
        armonicos: int = ARMONICOS_POR_DEFECTO,
        ancho_cents: float = ANCHO_BANDA_CENTS,
        referencia_a4: float = 440.0,
    ) -> None:
        if ventana < 2:
            raise ValueError("La ventana de acordes tiene que tener al menos 2 muestras")
        self.perfil = perfil
        self.frecuencia_muestreo = frecuencia_muestreo
        self.ventana = ventana
        self.umbral_ruido_dbfs = umbral_ruido_dbfs
        self.umbral_presencia = umbral_presencia
        self.armonicos = armonicos
        self.ancho_cents = ancho_cents
        self.referencia_a4 = referencia_a4

        # El rango sobre el que se normaliza: todo lo que el mastil alcanza, con un
        # semitono de margen por abajo. Normalizar contra las notas ESPERADAS haria
        # que un acorde completamente equivocado saliera completo, porque la mas
        # fuerte de las esperadas valdria 1 por construccion.
        grave = round(frecuencia_a_midi(perfil.frecuencia_minima, referencia_a4)) - 1
        aguda = max(
            round(frecuencia_a_midi(cuerda.frecuencia, referencia_a4))
            for cuerda in perfil.cuerdas
        )
        self._rango = tuple(range(grave, aguda + perfil.trastes + 1))

        self._bufer = np.zeros(ventana, dtype=np.float64)
        self._llenas = 0

    def reiniciar(self) -> None:
        """Vacia el bufer. Se llama al parar o al cambiar de pieza."""
        self._bufer[:] = 0.0
        self._llenas = 0

    def _acumular(self, muestras: np.ndarray) -> None:
        """Mete el bloque por el final del bufer circular."""
        bloque = np.asarray(muestras, dtype=np.float64).ravel()
        if bloque.size == 0:
            return
        if bloque.size >= self.ventana:
            self._bufer[:] = bloque[-self.ventana :]
            self._llenas = self.ventana
            return
        self._bufer[:] = np.concatenate((self._bufer[bloque.size :], bloque))
        self._llenas = min(self.ventana, self._llenas + bloque.size)

    def _saliencia(self, frecuencias: np.ndarray, magnitud: np.ndarray, midi: int) -> float:
        return saliencia_de_nota(
            frecuencias,
            magnitud,
            midi,
            armonicos=self.armonicos,
            ancho_cents=self.ancho_cents,
            referencia_a4=self.referencia_a4,
        )

    def _silencio(self, nivel: float) -> ResultadoAcorde:
        return ResultadoAcorde(estado="silencio", nivel_db=nivel)

    def procesar(
        self, muestras: np.ndarray, midis_esperados: tuple[int, ...]
    ) -> ResultadoAcorde:
        """Acumula el bloque y juzga el acorde esperado sobre la ventana completa.

        Tres puertas devuelven silencio en vez de inventar, en este orden: la
        ventana a medio llenar, la lista de esperadas vacia y la compuerta de
        ruido. La segunda importa mas de lo que parece: una lista vacia se
        cumpliria por vacuidad y daria "completo" sin que suene nada.
        """
        self._acumular(muestras)
        medible = self._bufer[-self._llenas :] if self._llenas else self._bufer
        nivel = nivel_dbfs(medible)

        if self._llenas < FRACCION_MINIMA_LLENA * self.ventana:
            return self._silencio(nivel)
        if not midis_esperados:
            return self._silencio(nivel)
        if nivel <= self.umbral_ruido_dbfs:
            return self._silencio(nivel)

        frecuencias, magnitud = espectro_de_magnitud(self._bufer, self.frecuencia_muestreo)
        tope = max(
            (self._saliencia(frecuencias, magnitud, midi) for midi in self._rango),
            default=0.0,
        )

        if tope <= 0.0:
            # Energia sin ninguna saliencia en todo el mastil: ruido o continua.
            # Dividir aqui daria nan, y un nan nunca supera un umbral, asi que el
            # veredicto saldria "incompleto" por accidente aritmetico en vez de
            # por una medida. Se dice explicitamente: presencia cero.
            presencias = {midi: 0.0 for midi in midis_esperados}
        else:
            presencias = {
                midi: self._saliencia(frecuencias, magnitud, midi) / tope
                for midi in midis_esperados
            }

        faltan = tuple(
            sorted(midi for midi, valor in presencias.items() if valor < self.umbral_presencia)
        )
        return ResultadoAcorde(
            estado="completo" if not faltan else "incompleto",
            nivel_db=nivel,
            presencias=presencias,
            faltan=faltan,
        )
