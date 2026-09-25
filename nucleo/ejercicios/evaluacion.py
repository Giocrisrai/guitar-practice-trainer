"""La maquina de estados que corrige lo que tocas.

Consume el mismo flujo de ResultadoAnalisis que alimenta al afinador. Como
ResultadoAnalisis es un dato, toda esta logica se prueba escribiendo la secuencia
exacta que produciria alguien tocando, sin audio y sin hardware.

Un evento de nota (una lectura que cuenta como intento) puede dispararse por dos
caminos independientes, resueltos a lo sumo uno por cuadro:

Camino A - ataque de energia. `DetectorAtaques` marca un ataque por el salto de
nivel; se anota una lectura pendiente para `instante + espera_estabilizacion_s`
y se resuelve en la primera llamada posterior a ese momento. Es el camino que
describe la Task 7 original.

Camino B - cambio estable de nota. Se cuenta cuantos cuadros seguidos trae la
misma nota con confianza suficiente. Al llegar a `cuadros_para_nota_estable`
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

Ambos caminos comparten el mismo filtro: una lectura que coincide con la
ultima nota ya resuelta (`_ultima_nota_resuelta`) no vuelve a contarse. Eso
evita que un segundo pico de energia sobre una nota que ya sonaba (un hinchado
de volumen, un vibrato) se lea contra la nota siguiente, y evita que una racha
estable ya resuelta por el camino B se cuente otra vez cuando el camino A
llega tarde a leer el mismo sonido. Ese registro se limpia en cuanto un cuadro
deja de traer una nota creible (silencio o confianza insuficiente): el
silencio es la frontera natural entre pulsaciones y le devuelve a ambos
caminos la capacidad de volver a contar la misma nota.
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
# estabilizacion del camino A (60 ms), y esa cercania es intencional, no
# casual: si el camino B tardara mucho mas que el camino A en confirmar,
# dejaria de aportar nada sobre una pulsacion normal. La equivalencia en
# milisegundos esta ACOPLADA al intervalo entre cuadros de analisis (aqui 21
# ms, el de las pruebas): con un intervalo mayor, los mismos cuadros
# representan mas tiempo, y con uno menor, menos. Nada en este modulo verifica
# ese acoplamiento porque el intervalo de analisis no es una constante propia
# del evaluador, sino de quien lo alimenta (el pipeline de audio); quien
# cambie la tasa de analisis debe revisar si `cuadros_para_nota_estable` sigue
# teniendo sentido.
CUADROS_PARA_NOTA_ESTABLE = 3

# Segundos que la nota actual puede estar sin acertarse antes de mostrar la ayuda,
# aunque no se hayan contado cinco intentos. El conteo de intentos depende de
# detectar cada pulsacion, y hay situaciones -repulsar la misma nota equivocada a
# nivel constante, sin ningun silencio real de por medio- en que ninguna de las
# dos vias lo consigue. El alumno atascado merece ayuda igual.
SEGUNDOS_PARA_AYUDA = 12.0


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
       se salta el ejercicio: se ayuda. Como el conteo de fallos depende de
       detectar cada pulsacion, y eso puede fallar (ver limitacion mas abajo),
       hay un segundo disparador puramente temporal: si pasan
       `segundos_para_ayuda` desde que la nota actual paso a serlo y hubo al
       menos un fallo, la ayuda aparece igual. Exigir un fallo evita que la
       ayuda salte sola mientras el alumno todavia esta leyendo el ejercicio
       sin haber tocado nada.

    Un evento de nota (una lectura que cuenta como intento) puede llegar por dos
    caminos independientes, resueltos a lo sumo uno por cuadro: el ataque de
    energia (DetectorAtaques, con su lectura diferida) o el cambio estable de
    nota (ver CUADROS_PARA_NOTA_ESTABLE en el modulo). Cuando uno de los dos
    resuelve una lectura creible, la nota leida pasa a ser
    `_ultima_nota_resuelta`, y ni el camino A ni el camino B vuelven a
    dispararse con ella hasta que un cuadro sin nota creible (silencio o
    confianza insuficiente) la libere.

    Limitacion conocida: dos pulsaciones seguidas de la MISMA nota, sin
    ninguna caida de nivel real entre ellas, no se distinguen. Ni la altura
    cambia (el camino B no ve nada nuevo) ni hay, por definicion, un silencio
    que libere `_ultima_nota_resuelta` para que un segundo ataque de energia
    vuelva a contar (el camino A tambien queda filtrado). Mientras el nivel
    baje lo suficiente entre pulsaciones -el caso normal al tocar con
    articulacion- el camino A las distingue igual que antes. El caso sin
    solucion es el de picar la misma nota una y otra vez sin que el nivel
    llegue a caer: ahi solo el disparador temporal de la regla 3 garantiza que
    el alumno no se quede atascado sin ayuda. Los generadores de lectura e
    intervalos pueden producir el escenario de nota repetida; que el nivel no
    caiga entre pulsaciones depende de como toque el alumno, no del generador.
    """

    def __init__(
        self,
        ejercicio: Ejercicio,
        detector_ataques: DetectorAtaques | None = None,
        confianza_minima: float = CONFIANZA_MINIMA,
        espera_estabilizacion_s: float = ESPERA_ESTABILIZACION_S,
        intentos_para_ayuda: int = INTENTOS_PARA_AYUDA,
        cuadros_para_nota_estable: int = CUADROS_PARA_NOTA_ESTABLE,
        segundos_para_ayuda: float = SEGUNDOS_PARA_AYUDA,
    ) -> None:
        self.ejercicio = ejercicio
        self._detector = detector_ataques or DetectorAtaques()
        self.confianza_minima = confianza_minima
        self.espera_estabilizacion_s = espera_estabilizacion_s
        self.intentos_para_ayuda = intentos_para_ayuda
        self.cuadros_para_nota_estable = cuadros_para_nota_estable
        self.segundos_para_ayuda = segundos_para_ayuda
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
        # Camino B: nota candidata, cuantos cuadros seguidos lleva y cuando
        # empezo esa racha (para registrar el instante correcto del evento).
        self._nota_candidata: str | None = None
        self._contador_candidata = 0
        self._instante_inicio_candidata: float | None = None
        # Ultima nota resuelta por cualquiera de los dos caminos; se limpia en
        # cuanto un cuadro deja de traer una nota creible.
        self._ultima_nota_resuelta: str | None = None
        # Regla 3, disparador por tiempo: cuando paso a ser actual la nota que
        # se esta pidiendo ahora mismo.
        self._instante_nota_actual: float | None = None

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

        Camino B. Se sigue cuantos cuadros lleva la misma nota creible. Si el
        camino A resuelve en este cuadro, la cuenta del camino B se reinicia
        (ese ataque ya se leyo). Si es el camino B el que resuelve, se cancela
        cualquier lectura pendiente del camino A para esa misma nota
        sostenida, evitando contar el mismo evento dos veces.

        Ademas, un cuadro sin nota creible (silencio o confianza insuficiente)
        libera `_ultima_nota_resuelta`: el silencio es la frontera natural
        entre pulsaciones, y sin esa liberacion una nota equivocada repetida
        bloquearia ambos caminos para siempre (ver la limitacion documentada
        en la clase).
        """
        if self._indice >= len(self.ejercicio):
            return self.estado

        if self._instante_nota_actual is None:
            self._instante_nota_actual = instante

        if not self._es_creible(resultado):
            self._ultima_nota_resuelta = None

        ataque = self._detector.procesar(resultado.nivel_db, instante)
        if ataque is not None:
            self._lectura_pendiente = ataque.instante + self.espera_estabilizacion_s
            self._instante_ataque = ataque.instante

        resuelto_este_cuadro = False

        if self._lectura_pendiente is not None and instante >= self._lectura_pendiente:
            self._lectura_pendiente = None
            if self._resolver(resultado, self._instante_ataque):
                resuelto_este_cuadro = True
                # Este ataque ya se leyo: el camino B empieza a contar de nuevo
                # para no repetir el mismo evento con la nota que sigue sonando.
                self._nota_candidata = None
                self._contador_candidata = 0
                self._instante_inicio_candidata = None

        if not resuelto_este_cuadro:
            nota_estable = self._actualizar_candidata(resultado, instante)
            if nota_estable is not None:
                instante_evento = self._instante_inicio_candidata
                if self._resolver(resultado, instante_evento):
                    # Esta nota ya se resolvio por el camino B: si habia una
                    # lectura pendiente del camino A para el mismo sonido, se
                    # cancela para no contarla otra vez cuando le toque su turno.
                    self._lectura_pendiente = None

        # Regla 3, respaldo por tiempo: si nada de lo anterior logro
        # confirmar suficientes intentos, el tiempo atascado en la misma nota
        # tambien dispara la ayuda, con tal de que haya habido al menos un
        # fallo real.
        if (
            not self._ayuda_mostrada
            and self._intentos >= 1
            and self._instante_nota_actual is not None
            and instante - self._instante_nota_actual >= self.segundos_para_ayuda
        ):
            self._ayuda_mostrada = True

        return self.estado

    def _es_creible(self, resultado: ResultadoAnalisis) -> bool:
        """Si esta lectura trae una nota que se puede tomar en serio."""
        return (
            resultado.estado == "nota"
            and resultado.nota is not None
            and resultado.confianza >= self.confianza_minima
        )

    def _actualizar_candidata(
        self, resultado: ResultadoAnalisis, instante: float
    ) -> str | None:
        """Sigue la pista de cuantos cuadros seguidos suena la misma nota creible.

        Devuelve el nombre de la nota en cuanto lleva `cuadros_para_nota_estable`
        cuadros seguidos, o None si no hay racha suficiente (sin nota creible,
        o racha mas corta). No compara aqui contra la ultima nota resuelta: ese
        filtro es responsabilidad de `_resolver`, el mismo para los dos caminos.
        """
        if not self._es_creible(resultado):
            self._nota_candidata = None
            self._contador_candidata = 0
            self._instante_inicio_candidata = None
            return None

        if resultado.nota == self._nota_candidata:
            self._contador_candidata += 1
        else:
            self._nota_candidata = resultado.nota
            self._contador_candidata = 1
            self._instante_inicio_candidata = instante

        if self._contador_candidata >= self.cuadros_para_nota_estable:
            return self._nota_candidata
        return None

    def _resolver(self, resultado: ResultadoAnalisis, instante_evento: float | None) -> bool:
        """Decide que hacer con la nota que suena al disparar un evento.

        Devuelve True si el evento se conto de verdad (acierto o fallo), y
        False si se descarto: sin nota esperada, sin nota creible (regla 1), o
        porque la nota leida es la misma que la ultima ya resuelta, en cuyo
        caso no hubo forma de distinguir esta lectura de la que la origino.
        """
        esperada = self._nota_actual
        if esperada is None:
            return False

        # Regla 1: sin nota creible no hubo intento.
        if not self._es_creible(resultado):
            return False

        # Misma nota que la ultima ya resuelta: sin un cuadro sin nota creible
        # de por medio, no hay forma de saber si es una pulsacion nueva o el
        # mismo sonido que ya se conto (un segundo pico de energia sobre la
        # nota aceptada, o el resto de la racha que el camino B ya resolvio).
        if resultado.nota == self._ultima_nota_resuelta:
            return False

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
            self._instante_nota_actual = instante_evento
            return True

        self._ultimo_fallo = resultado.nota
        # Regla 3: se ayuda, no se salta.
        if self._intentos >= self.intentos_para_ayuda:
            self._ayuda_mostrada = True
        return True

    def resultado(self) -> ResultadoEjercicio:
        """Informe de lo hecho hasta ahora."""
        return ResultadoEjercicio(
            ejercicio=self.ejercicio.clave,
            notas=tuple(self._hechas),
            completado=self._indice >= len(self.ejercicio),
        )
