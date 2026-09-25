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
llega tarde a leer el mismo sonido. Ese registro se libera cuando se acumulan
`cuadros_para_olvidar_nota` cuadros SEGUIDOS sin nota creible (silencio o
confianza insuficiente): un hueco real es la frontera entre pulsaciones y le
devuelve a ambos caminos la capacidad de volver a contar la misma nota. No
basta un solo cuadro dudoso: el detector de tono flaquea a mitad de una nota
sostenida sin que la pulsacion haya terminado, y limpiar al primer bache
resolveria dos veces la misma pulsacion (ver CUADROS_PARA_OLVIDAR_NOTA).
"""

import threading
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

# Cuadros seguidos sin nota creible antes de olvidar la ultima nota resuelta.
# Uno solo no basta: el detector de tono flaquea a mitad de una nota sostenida y
# el pipeline emite "silencio" con el nivel intacto, asi que limpiar al primer
# bache haria que una misma pulsacion se resolviera dos veces. Se usa el mismo
# criterio de estabilidad que el camino B: tres cuadros, unos 63 ms al intervalo
# de analisis habitual.
CUADROS_PARA_OLVIDAR_NOTA = 3

# Segundos que la nota actual puede estar sin resolverse antes de mostrar la
# ayuda, aunque no se haya contado ningun intento (ni cinco, ni uno solo). El
# conteo de intentos depende de que alguno de los dos caminos logre RESOLVER
# una pulsacion, y hay escenarios en los que ninguno lo consigue pese a que el
# alumno esta tocando de verdad: repulsar la misma nota equivocada a nivel
# constante, sin ningun hueco real de por medio, o un detector de tono que
# oscila con periodo corto (creible, dudoso, creible, dudoso...) sin llegar
# nunca a los cuadros seguidos que exige ningun camino. La condicion no es
# "hubo al menos un fallo", sino "hubo alguna nota creible mientras esta nota
# era la actual": eso basta para distinguir a un alumno que esta tocando
# -aunque el software no logre resolver sus pulsaciones- de uno que todavia
# esta leyendo el ejercicio sin tocar la guitarra.
#
# La cuenta arranca en ese primer cuadro con senal creible, no cuando la nota
# paso a ser la actual: el tiempo que el alumno pasa leyendo el ejercicio, o con
# el cable desenchufado, no es tiempo atascado. Y la senal tiene que poder ser un
# intento de ESTA nota: la cola de la nota anterior, que se resolvio y sigue
# sonando, no cuenta (ver procesar()).
SEGUNDOS_PARA_AYUDA = 12.0

# Cuanto puede haber pasado desde un ataque de energia para que el camino B lo
# tome como el onset de la pulsacion que esta resolviendo (ver
# _onset_camino_b). El detector de tono tarda decenas de milisegundos en dar una
# lectura creible tras el ataque de la pua, y el camino B necesita ademas
# `cuadros_para_nota_estable` cuadros seguidos: 0.25 s cubre ese retraso con
# holgura. Y sigue estando muy por debajo del hueco entre notas a cualquier
# tempo de practica (los generadores producen de 60 a 95 ppm, es decir de 1.0 a
# 0.63 s por nota), asi que un ataque mas viejo que esto pertenece a otra
# pulsacion y no debe firmar este onset.
VENTANA_ATAQUE_COMO_ONSET_S = 0.25


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
       resolver cada pulsacion, y eso puede fallar (ver limitacion mas abajo,
       y el caso del detector que oscila), hay un segundo disparador puramente
       temporal: si pasan `segundos_para_ayuda` desde el primer cuadro con
       señal creible que podria ser un intento de la nota actual, la ayuda
       aparece igual, se haya llegado a contar un fallo o no. Exigir señal
       creible (en vez de un fallo) evita que la ayuda salte sola mientras el
       alumno todavia esta leyendo el ejercicio sin tocar la guitarra, sin
       depender de que el software haya logrado resolver ninguna pulsacion. Y
       que la cuenta arranque en esa señal, y no cuando la nota paso a ser la
       actual, es lo que evita que una pausa para pensar -o un cable
       desenchufado- regale la respuesta resaltada en el mastil.

    Un evento de nota (una lectura que cuenta como intento) puede llegar por dos
    caminos independientes, resueltos a lo sumo uno por cuadro: el ataque de
    energia (DetectorAtaques, con su lectura diferida) o el cambio estable de
    nota (ver CUADROS_PARA_NOTA_ESTABLE en el modulo). Cuando uno de los dos
    resuelve una lectura creible, la nota leida pasa a ser
    `_ultima_nota_resuelta`, y ni el camino A ni el camino B vuelven a
    dispararse con ella hasta que se acumulan `cuadros_para_olvidar_nota`
    cuadros SEGUIDOS sin nota creible (ver CUADROS_PARA_OLVIDAR_NOTA en el
    modulo). Un solo cuadro dudoso a mitad de una nota sostenida no basta: el
    detector de tono puede flaquear sin que la pulsacion haya terminado, y
    limpiar el registro ahi mismo resolveria la misma pulsacion dos veces.

    Limitacion conocida: dos pulsaciones seguidas de la MISMA nota no se
    distinguen si entre ellas no hay un hueco de `cuadros_para_olvidar_nota`
    cuadros (unos 63 ms al intervalo de analisis habitual) en los que el tono
    deje de ser creible. El nivel no interviene: el filtro compara NOMBRES DE
    NOTA, no niveles, asi que por muy marcada que sea la caida de volumen entre
    las dos pulsaciones el camino A queda filtrado igual, y el camino B no ve
    ninguna altura nueva. Lo unico que libera el filtro es que el detector de
    tono deje de dar esa nota como creible durante esos cuadros seguidos; con
    una nota de guitarra que sigue sonando, eso puede no llegar nunca.

    Lo que evita que el alumno se quede atascado en ese caso es el disparador
    temporal de la regla 3: pasados `segundos_para_ayuda` con senal creible, la
    ayuda aparece aunque no se haya podido contar ni un solo intento. Y los
    generadores de lectura e intervalos ya no producen notas repetidas
    adyacentes (ver `elegir_sin_repetir_adyacentes`), asi que este escenario
    solo aparece con un ejercicio escrito a mano que las contenga.
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
        cuadros_para_olvidar_nota: int = CUADROS_PARA_OLVIDAR_NOTA,
    ) -> None:
        self.ejercicio = ejercicio
        self._detector = detector_ataques or DetectorAtaques()
        self.confianza_minima = confianza_minima
        self.espera_estabilizacion_s = espera_estabilizacion_s
        self.intentos_para_ayuda = intentos_para_ayuda
        self.cuadros_para_nota_estable = cuadros_para_nota_estable
        self.segundos_para_ayuda = segundos_para_ayuda
        self.cuadros_para_olvidar_nota = cuadros_para_olvidar_nota
        # El evaluador se muta desde el hilo de analisis (procesar) y se lee
        # desde el hilo HTTP/WS (estado, resultado, a 30 Hz). Es reentrante
        # porque procesar() construye la instantanea con `self.estado` sin
        # soltarlo. Sin candado, una instantanea podia salir incoherente: el
        # indice leido antes de avanzar y la nota_actual leida despues, o
        # completado=False con nota_actual=None.
        self._candado = threading.RLock()
        self.reiniciar()

    def reiniciar(self) -> None:
        """Vuelve al principio del ejercicio y olvida lo hecho."""
        with self._candado:
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
            # Ultima nota resuelta por cualquiera de los dos caminos; se libera
            # cuando se acumulan cuadros_para_olvidar_nota cuadros SEGUIDOS sin
            # nota creible (ver _cuadros_sin_nota_creible mas abajo).
            self._ultima_nota_resuelta: str | None = None
            self._cuadros_sin_nota_creible = 0
            # Regla 3, disparador por tiempo: desde cuando corre el reloj de la
            # nota actual (el primer cuadro con senal que podria ser un intento
            # de ella) y si ha habido alguna senal asi.
            self._instante_nota_actual: float | None = None
            self._hubo_senal_creible_nota_actual = False

    @property
    def _nota_actual(self) -> NotaEsperada | None:
        if self._indice >= len(self.ejercicio):
            return None
        return self.ejercicio.notas[self._indice]

    @property
    def estado(self) -> EstadoEvaluacion:
        """Instantanea COHERENTE para la pantalla.

        Se construye entera bajo `_candado`. Sin el, la instantanea mezclaba dos
        momentos distintos: el hilo HTTP/WS la pide a 30 Hz mientras el hilo de
        analisis avanza el indice, asi que podia salir `indice=n` con la
        `nota_actual` de n+1 (se leen en dos accesos separados), o
        `completado=False` con `nota_actual=None`.
        """
        with self._candado:
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

        Ademas, cuando se acumulan `cuadros_para_olvidar_nota` cuadros SEGUIDOS
        sin nota creible (silencio o confianza insuficiente) se libera
        `_ultima_nota_resuelta`: un hueco real es la frontera entre
        pulsaciones, y sin esa liberacion una nota equivocada repetida
        bloquearia ambos caminos para siempre (ver la limitacion documentada
        en la clase). Un solo cuadro dudoso no cuenta como hueco: el contador
        se reinicia en cuanto vuelve un cuadro con nota creible, para no
        resolver dos veces la misma pulsacion solo porque el detector de tono
        flaqueo un instante a mitad de la nota.

        Todo el cuerpo corre bajo `_candado`: este metodo vive en el hilo de
        analisis y es el unico que muta el evaluador, pero el hilo HTTP/WS lee
        `estado` y `resultado()` a la vez, y esas lecturas tienen que ver un
        cuadro entero, no medio.
        """
        with self._candado:
            return self._procesar_bajo_candado(resultado, instante)

    def _procesar_bajo_candado(
        self, resultado: ResultadoAnalisis, instante: float
    ) -> EstadoEvaluacion:
        """Cuerpo de `procesar`. Quien llame ya tiene `_candado`."""
        if self._indice >= len(self.ejercicio):
            return self.estado

        if self._instante_nota_actual is None:
            self._instante_nota_actual = instante

        if self._es_creible(resultado):
            self._cuadros_sin_nota_creible = 0
            # La bandera del disparador temporal solo se arma con senal que
            # PODRIA ser un intento de la nota que se esta pidiendo ahora. Un
            # cuadro creible cuya nota es `_ultima_nota_resuelta` es la cola de
            # la nota anterior, que se resolvio y sigue sonando: no es que el
            # alumno este intentando nada. Armarla con cualquier cuadro creible
            # hacia que, de la nota 2 en adelante, la bandera quedara siempre
            # verdadera (la cola la rearmaba justo despues de que `_resolver` la
            # limpiara), y entonces una pausa para pensar -o el cable
            # desenchufado- regalaba la respuesta resaltada en el mastil sin
            # haber tocado nada.
            if resultado.nota != self._ultima_nota_resuelta:
                self._hubo_senal_creible_nota_actual = True
        else:
            self._cuadros_sin_nota_creible += 1
            if self._cuadros_sin_nota_creible >= self.cuadros_para_olvidar_nota:
                self._ultima_nota_resuelta = None

        # El reloj del disparador temporal no arranca mientras no haya habido
        # senal que pueda ser un intento de ESTA nota: hasta entonces se arrastra
        # al presente. Sin esto, los segundos que el alumno pasa leyendo el
        # ejercicio -o con el cable desenchufado- se descuentan de la ventana, y
        # la ayuda salta en el primer cuadro creible que llegue despues, con lo
        # que una pausa para pensar seguiria regalando la respuesta resaltada.
        if not self._hubo_senal_creible_nota_actual:
            self._instante_nota_actual = instante

        ataque = self._detector.procesar(resultado.nivel_db, instante)
        if ataque is not None:
            self._lectura_pendiente = ataque.instante + self.espera_estabilizacion_s
            self._instante_ataque = ataque.instante

        resuelto_este_cuadro = False

        if self._lectura_pendiente is not None and instante >= self._lectura_pendiente:
            self._lectura_pendiente = None
            if self._resolver(resultado, self._instante_ataque, instante):
                resuelto_este_cuadro = True
                # Este ataque ya se leyo: el camino B empieza a contar de nuevo
                # para no repetir el mismo evento con la nota que sigue sonando.
                self._nota_candidata = None
                self._contador_candidata = 0
                self._instante_inicio_candidata = None

        if not resuelto_este_cuadro:
            nota_estable = self._actualizar_candidata(resultado, instante)
            if nota_estable is not None:
                if self._resolver(resultado, self._onset_camino_b(instante), instante):
                    # Esta nota ya se resolvio por el camino B: si habia una
                    # lectura pendiente del camino A para el mismo sonido, se
                    # cancela para no contarla otra vez cuando le toque su turno.
                    self._lectura_pendiente = None

        # Regla 3, respaldo por tiempo: si nada de lo anterior logro resolver
        # ninguna pulsacion, el tiempo atascado en la misma nota tambien
        # dispara la ayuda, con tal de que se haya detectado alguna nota
        # creible en ese tramo (no hace falta que ningun camino la haya
        # llegado a resolver: ver SEGUNDOS_PARA_AYUDA).
        if (
            not self._ayuda_mostrada
            and self._hubo_senal_creible_nota_actual
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

    def _onset_camino_b(self, instante: float) -> float | None:
        """Instante que se anota como comienzo de la nota cuando resuelve el camino B.

        Los dos caminos deben anotar la MISMA definicion de onset, porque
        `regularidad_ms` mide la desviacion tipica de los huecos entre onsets
        consecutivos. El camino A anota el instante del ataque de energia; el
        comienzo de la racha estable del camino B llega, en una guitarra real,
        decenas de milisegundos DESPUES de ese ataque (el transitorio de la pua
        no tiene altura definida, asi que el detector de tono tarda en dar una
        lectura creible). Un ejercicio que resolviera unas notas por A y otras
        por B mezclaria las dos definiciones y arrastraria a `regularidad_ms` un
        sesgo del orden de lo que se quiere medir.

        Se unifica asi: si hay un ataque de energia lo bastante reciente
        (`VENTANA_ATAQUE_COMO_ONSET_S`), es el ataque de esta misma pulsacion y
        ese es el instante que se anota; solo cuando no hay ninguno -nivel
        constante, ningun salto que el detector viera- se recurre al comienzo de
        la racha, que es lo unico disponible.
        """
        if (
            self._instante_ataque is not None
            and instante - self._instante_ataque <= VENTANA_ATAQUE_COMO_ONSET_S
        ):
            return self._instante_ataque
        return self._instante_inicio_candidata

    def _resolver(
        self,
        resultado: ResultadoAnalisis,
        instante_evento: float | None,
        instante: float,
    ) -> bool:
        """Decide que hacer con la nota que suena al disparar un evento.

        `instante_evento` es el onset que se anota en el informe (el ataque de
        energia, o lo que devuelva `_onset_camino_b`). `instante` es el del
        cuadro que se esta procesando, y es OTRA cosa: llega despues del onset,
        y es el que sella el comienzo de la ventana temporal de la nota
        siguiente. Sellarla con el onset (como se hacia antes) hacia empezar la
        cuenta de `segundos_para_ayuda` de la nota nueva antes de que la
        anterior se hubiera resuelto.

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
        # El ataque que origino este evento ya se gasto: dejarlo puesto haria
        # que `_onset_camino_b` lo firmara como onset de la pulsacion siguiente.
        self._instante_ataque = None

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
            # La ventana temporal de la nota NUEVA empieza en el cuadro en que
            # esta se resolvio, no en el onset del ataque de la nota anterior:
            # con el onset, los milisegundos (o segundos) que el alumno tardo en
            # completar la nota anterior ya venian descontados de la ventana de
            # la siguiente.
            self._instante_nota_actual = instante
            self._hubo_senal_creible_nota_actual = False
            return True

        self._ultimo_fallo = resultado.nota
        # Regla 3: se ayuda, no se salta.
        if self._intentos >= self.intentos_para_ayuda:
            self._ayuda_mostrada = True
        return True

    def resultado(self) -> ResultadoEjercicio:
        """Informe de lo hecho hasta ahora.

        Bajo `_candado` por lo mismo que `estado`: `_hechas` crece en el hilo de
        analisis mientras el hilo HTTP/WS copia la tupla.
        """
        with self._candado:
            return ResultadoEjercicio(
                ejercicio=self.ejercicio.clave,
                notas=tuple(self._hechas),
                completado=self._indice >= len(self.ejercicio),
            )
