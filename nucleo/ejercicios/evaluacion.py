"""La maquina de estados que corrige lo que tocas.

Consume el mismo flujo de ResultadoAnalisis que alimenta al afinador. Como
ResultadoAnalisis es un dato, toda esta logica se prueba escribiendo la secuencia
exacta que produciria alguien tocando, sin audio y sin hardware.

Dos caminos disparan un evento de nota (a lo sumo uno por cuadro procesado):

Camino A - ataque de energia. `DetectorAtaques` marca un ataque por el salto de
nivel; se anota una lectura pendiente para `instante + espera_estabilizacion_s`
y se resuelve en la primera llamada posterior a ese momento. Es el camino que
describe la Task 7 original.

Camino B - cambio estable de nota. Se cuenta cuantos cuadros seguidos trae la
misma nota con confianza suficiente. Al llegar a CUADROS_PARA_NOTA_ESTABLE
cuadros, y si esa nota es distinta de la ultima ya resuelta, se dispara el
evento sin esperar ningun salto de energia.

Se necesito el camino B porque, con el decaimiento real de una guitarra
(unos 8.7 dB/s), a tempo normal la nota anterior todavia suena casi al mismo
nivel cuando se pulsa la siguiente: el salto no llega a los 6 dB que exige el
detector de energia y el ejercicio no avanza nunca. Medido con negras:

    60 BPM (1.000 s entre notas) -> 8 de 8 ataques detectados
    90 BPM (0.667 s)             -> 1 de 8
    120 BPM (0.500 s)            -> 1 de 8

El camino B no depende de la energia, asi que detecta el cambio de nota aunque
el nivel apenas se mueva. Exigir estabilidad (varios cuadros seguidos, no uno
solo) es lo que evita que el caos del transitorio de la pua dispare con un
armonico falso.
"""

from dataclasses import dataclass

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.ataques import ESPERA_ESTABILIZACION_S, DetectorAtaques
from nucleo.ejercicios.modelo import Ejercicio, IntentoNota, NotaEsperada, ResultadoEjercicio
from nucleo.musica import nombre_de_midi

# Fallos seguidos en la misma nota antes de resaltar donde esta en el mastil.
INTENTOS_PARA_AYUDA = 5

# Confianza minima del detector de tono para que una lectura cuente como intento.
CONFIANZA_MINIMA = 0.75

# Cuadros seguidos con la misma nota creible para que el camino B la de por
# estable. A 21 ms por cuadro son unos 63 ms: el mismo orden que la espera de
# estabilizacion del camino A (60 ms). Un solo cuadro no basta: el transitorio
# de la pua puede sonar como un armonico distinto durante uno o dos cuadros.
CUADROS_PARA_NOTA_ESTABLE = 3


@dataclass(frozen=True)
class EstadoEvaluacion:
    """Lo que la pantalla necesita saber en cada instante."""

    indice: int
    total: int
    intentos: int
    ayuda_visible: bool
    completado: bool
    nota_actual: NotaEsperada | None
    ultimo_fallo: str | None = None

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "total": self.total,
            "intentos": self.intentos,
            "ayuda_visible": self.ayuda_visible,
            "completado": self.completado,
            "nota_actual": None if self.nota_actual is None else self.nota_actual.a_dict(),
            "ultimo_fallo": self.ultimo_fallo,
        }


class EvaluadorEjercicio:
    """Corrige un ejercicio nota a nota.

    Tres reglas gobiernan su comportamiento:

    1. Un ataque sin nota creible no cuenta como fallo, sino como que no tocaste
       nada. Un roce o un armonico accidental no deben puntuar en contra.
    2. La afinacion no bloquea: una nota correcta se acepta aunque este a 20
       cents, y la desviacion se guarda para el informe.
    3. Tras INTENTOS_PARA_AYUDA fallos en la misma nota se resalta donde esta. No
       se salta el ejercicio: se ayuda.

    Un evento de nota (una lectura que cuenta como intento) puede llegar por dos
    caminos independientes, resueltos a lo sumo uno por cuadro: el ataque de
    energia (DetectorAtaques, con su lectura diferida) o el cambio estable de
    nota (ver CUADROS_PARA_NOTA_ESTABLE en el modulo). Cuando uno de los dos
    resuelve, la nota leida pasa a ser `_ultima_nota_resuelta`, y mientras la
    misma nota siga sonando el camino B no vuelve a dispararse con ella.

    Limitacion conocida: si el ejercicio pide dos veces seguidas la MISMA nota,
    el camino B no distingue la segunda de la primera (no hay cambio de
    altura), y la deteccion queda enteramente en manos del camino A. A tempo
    rapido, con la guitarra decayendo despacio, el camino A puede perder ese
    segundo ataque igual que perdia todos antes de este cambio. Los
    generadores de lectura e intervalos pueden producir esa situacion (una
    escala con nota repetida, un intervalo que vuelve a la tonica ya tocada).
    No se soluciona aqui: se documenta.
    """

    def __init__(
        self,
        ejercicio: Ejercicio,
        detector_ataques: DetectorAtaques | None = None,
        confianza_minima: float = CONFIANZA_MINIMA,
        espera_estabilizacion_s: float = ESPERA_ESTABILIZACION_S,
        intentos_para_ayuda: int = INTENTOS_PARA_AYUDA,
    ) -> None:
        self.ejercicio = ejercicio
        self._detector = detector_ataques or DetectorAtaques()
        self.confianza_minima = confianza_minima
        self.espera_estabilizacion_s = espera_estabilizacion_s
        self.intentos_para_ayuda = intentos_para_ayuda
        self.reiniciar()

    def reiniciar(self) -> None:
        """Vuelve al principio del ejercicio y olvida lo hecho."""
        self._detector.reiniciar()
        self._indice = 0
        self._intentos = 0
        self._ayuda_mostrada = False
        self._ultimo_fallo: str | None = None
        self._lectura_pendiente: float | None = None
        self._instante_ataque: float | None = None
        self._hechas: list[IntentoNota] = []
        # Camino B: nota candidata y cuantos cuadros seguidos lleva, y la
        # ultima nota que se resolvio por cualquiera de los dos caminos.
        self._ultima_nota_resuelta: str | None = None
        self._nota_candidata: str | None = None
        self._contador_candidata = 0

    @property
    def _nota_actual(self) -> NotaEsperada | None:
        if self._indice >= len(self.ejercicio):
            return None
        return self.ejercicio.notas[self._indice]

    @property
    def estado(self) -> EstadoEvaluacion:
        """Instantanea para la pantalla."""
        return EstadoEvaluacion(
            indice=self._indice,
            total=len(self.ejercicio),
            intentos=self._intentos,
            ayuda_visible=self._ayuda_mostrada,
            completado=self._indice >= len(self.ejercicio),
            nota_actual=self._nota_actual,
            ultimo_fallo=self._ultimo_fallo,
        )

    def procesar(self, resultado: ResultadoAnalisis, instante: float) -> EstadoEvaluacion:
        """Consume un resultado del analisis y devuelve el estado resultante.

        Evalua los dos caminos de disparo y resuelve a lo sumo uno por cuadro:

        Camino A. La lectura de un ataque es diferida: no se lee en su propio
        instante, sino pasada la espera de estabilizacion. Justo en el ataque
        la senal es caotica y leer ahi daria notas falsas.

        Camino B. Se sigue cuantos cuadros lleva la misma nota creible. Si
        el camino A resuelve en este cuadro, la cuenta del camino B se
        reinicia (ese ataque ya se leyo). Si es el camino B el que resuelve,
        se cancela cualquier lectura pendiente del camino A para esa misma
        nota sostenida, evitando contar el mismo evento dos veces.
        """
        if self._indice >= len(self.ejercicio):
            return self.estado

        ataque = self._detector.procesar(resultado.nivel_db, instante)
        if ataque is not None:
            self._lectura_pendiente = ataque.instante + self.espera_estabilizacion_s
            self._instante_ataque = ataque.instante

        resuelto_este_cuadro = False

        if self._lectura_pendiente is not None and instante >= self._lectura_pendiente:
            self._lectura_pendiente = None
            self._resolver(resultado, self._instante_ataque)
            resuelto_este_cuadro = True
            # Este ataque ya se leyo: el camino B empieza a contar de nuevo
            # para no repetir el mismo evento con la nota que sigue sonando.
            self._nota_candidata = None
            self._contador_candidata = 0

        if not resuelto_este_cuadro:
            nota_estable = self._actualizar_candidata(resultado)
            if nota_estable is not None:
                self._resolver(resultado, instante)
                # Esta nota ya se resolvio por el camino B: si habia una
                # lectura pendiente del camino A para el mismo sonido, se
                # cancela para no contarla otra vez cuando le toque su turno.
                self._lectura_pendiente = None

        return self.estado

    def _actualizar_candidata(self, resultado: ResultadoAnalisis) -> str | None:
        """Sigue la pista de cuantos cuadros seguidos suena la misma nota creible.

        Devuelve el nombre de la nota cuando lleva CUADROS_PARA_NOTA_ESTABLE
        cuadros seguidos y es distinta de la ultima nota resuelta; None en
        cualquier otro caso (sin nota creible, racha corta, o misma nota que ya
        se resolvio).
        """
        if (
            resultado.estado != "nota"
            or resultado.nota is None
            or resultado.confianza < self.confianza_minima
        ):
            self._nota_candidata = None
            self._contador_candidata = 0
            return None

        if resultado.nota == self._nota_candidata:
            self._contador_candidata += 1
        else:
            self._nota_candidata = resultado.nota
            self._contador_candidata = 1

        if (
            self._contador_candidata >= CUADROS_PARA_NOTA_ESTABLE
            and self._nota_candidata != self._ultima_nota_resuelta
        ):
            return self._nota_candidata
        return None

    def _resolver(self, resultado: ResultadoAnalisis, instante_evento: float | None) -> None:
        """Decide que hacer con la nota que suena al disparar un evento."""
        esperada = self._nota_actual
        if esperada is None:
            return

        # Regla 1: sin nota creible no hubo intento.
        if resultado.estado != "nota" or resultado.nota is None:
            return
        if resultado.confianza < self.confianza_minima:
            return

        self._intentos += 1
        self._ultima_nota_resuelta = resultado.nota

        if resultado.nota == nombre_de_midi(esperada.midi):
            # Regla 2: la afinacion se guarda, no bloquea.
            self._hechas.append(
                IntentoNota(
                    indice=self._indice,
                    midi=esperada.midi,
                    intentos=self._intentos,
                    cents=resultado.cents,
                    instante=instante_evento,
                    ayuda_mostrada=self._ayuda_mostrada,
                )
            )
            self._indice += 1
            self._intentos = 0
            self._ayuda_mostrada = False
            self._ultimo_fallo = None
            return

        self._ultimo_fallo = resultado.nota
        # Regla 3: se ayuda, no se salta.
        if self._intentos >= self.intentos_para_ayuda:
            self._ayuda_mostrada = True

    def resultado(self) -> ResultadoEjercicio:
        """Informe de lo hecho hasta ahora."""
        return ResultadoEjercicio(
            ejercicio=self.ejercicio.clave,
            notas=tuple(self._hechas),
            completado=self._indice >= len(self.ejercicio),
        )
