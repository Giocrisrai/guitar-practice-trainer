"""La maquina de estados que corrige lo que tocas.

Consume el mismo flujo de ResultadoAnalisis que alimenta al afinador. Como
ResultadoAnalisis es un dato, toda esta logica se prueba escribiendo la secuencia
exacta que produciria alguien tocando, sin audio y sin hardware.

Este modulo es solo la mitad de arriba del evaluador: comparar con la nota que
tocaba, contar intentos, ayudar e informar. La mitad de abajo -que nota se toco
y cuando- vive en `nucleo.ejercicios.pulsaciones`, y ahi estan explicados los
dos caminos de disparo (el ataque de energia y el cambio estable de nota), el
filtro que comparten contra la ultima nota resuelta y por que existe cada guarda.
Se extrajo para que el carril de piezas la use sin duplicarla.
"""

import threading
from dataclasses import dataclass

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.ataques import ESPERA_ESTABILIZACION_S, DetectorAtaques
from nucleo.ejercicios.modelo import Ejercicio, IntentoNota, NotaEsperada, ResultadoEjercicio
from nucleo.ejercicios.pulsaciones import (
    CONFIANZA_MINIMA,
    CUADROS_PARA_NOTA_ESTABLE,
    CUADROS_PARA_OLVIDAR_NOTA,
    VENTANA_ATAQUE_COMO_ONSET_S,
    DetectorPulsaciones,
    Pulsacion,
)
from nucleo.musica import nombre_de_midi

# Se reexportan para quien evaluaba contra el evaluador antes de la extraccion:
# siguen siendo los parametros con los que trabaja esta clase, aunque ahora los
# aplique `DetectorPulsaciones`.
__all__ = [
    "CONFIANZA_MINIMA",
    "CUADROS_PARA_NOTA_ESTABLE",
    "CUADROS_PARA_OLVIDAR_NOTA",
    "INTENTOS_PARA_AYUDA",
    "SEGUNDOS_PARA_AYUDA",
    "VENTANA_ATAQUE_COMO_ONSET_S",
    "EstadoEvaluacion",
    "EvaluadorEjercicio",
]

# Fallos seguidos en la misma nota antes de resaltar donde esta en el mastil.
INTENTOS_PARA_AYUDA = 5

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
# sonando, no cuenta (ver `DetectorPulsaciones.senal_de_nota_nueva`).
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
       nada. Un roce o un armonico accidental no deben puntuar en contra. Esa
       guarda vive en `DetectorPulsaciones`: un cuadro sin nota creible no
       produce pulsacion, y sin pulsacion aqui no se cuenta nada.
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

    Que nota se toco y cuando lo decide `DetectorPulsaciones`, por dos caminos
    independientes -el ataque de energia y el cambio estable de nota- y con un
    filtro que impide contar dos veces la misma pulsacion. Todo eso, y por que
    cada guarda esta ahi, esta documentado en `nucleo.ejercicios.pulsaciones`.
    Este evaluador solo ve el resultado: una `Pulsacion` o nada.

    Limitacion conocida, heredada de ese filtro: dos pulsaciones seguidas de la
    MISMA nota no se distinguen si entre ellas no hay un hueco de
    `cuadros_para_olvidar_nota` cuadros (unos 63 ms al intervalo de analisis
    habitual) SEGUIDOS sin ninguna nota creible (ver `DetectorPulsaciones`).

    Lo que evita que el alumno se quede atascado en ese caso es el disparador
    temporal de la regla 3: pasados `segundos_para_ayuda` desde que se detecto
    senal que pudiera ser un intento de la nota actual -no la cola de la que ya
    se resolvio-, la ayuda aparece aunque no se haya podido contar ni un solo
    intento. Ese reloj lo reinicia el acierto, no el fallo. Y los
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
        self._pulsaciones = DetectorPulsaciones(
            detector_ataques=detector_ataques,
            confianza_minima=confianza_minima,
            espera_estabilizacion_s=espera_estabilizacion_s,
            cuadros_para_nota_estable=cuadros_para_nota_estable,
            cuadros_para_olvidar_nota=cuadros_para_olvidar_nota,
        )
        self.intentos_para_ayuda = intentos_para_ayuda
        self.segundos_para_ayuda = segundos_para_ayuda
        # El evaluador se muta desde el hilo de analisis (procesar) y se lee
        # desde el hilo HTTP/WS (estado, resultado, a 30 Hz). Es reentrante
        # porque procesar() construye la instantanea con `self.estado` sin
        # soltarlo. Sin candado, una instantanea podia salir incoherente: el
        # indice leido antes de avanzar y la nota_actual leida despues, o
        # completado=False con nota_actual=None. Este candado protege tambien al
        # detector de pulsaciones, que no lleva uno propio.
        self._candado = threading.RLock()
        self.reiniciar()

    @property
    def confianza_minima(self) -> float:
        return self._pulsaciones.confianza_minima

    @property
    def espera_estabilizacion_s(self) -> float:
        return self._pulsaciones.espera_estabilizacion_s

    @property
    def cuadros_para_nota_estable(self) -> int:
        return self._pulsaciones.cuadros_para_nota_estable

    @property
    def cuadros_para_olvidar_nota(self) -> int:
        return self._pulsaciones.cuadros_para_olvidar_nota

    def reiniciar(self) -> None:
        """Vuelve al principio del ejercicio y olvida lo hecho."""
        with self._candado:
            self._pulsaciones.reiniciar()
            self._indice = 0
            self._intentos = 0
            self._ayuda_mostrada = False
            self._ultimo_fallo: str | None = None
            self._hechas: list[IntentoNota] = []
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

        Le pasa el cuadro al detector de pulsaciones y, si de ahi sale una
        pulsacion, le aplica las reglas sobre la nota esperada. Ademas mantiene
        el reloj del disparador temporal de la ayuda (regla 3).

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

        pulsacion = self._pulsaciones.procesar(resultado, instante)

        # La bandera del disparador temporal solo se arma con senal que PODRIA
        # ser un intento de la nota que se esta pidiendo ahora, y eso es
        # exactamente `senal_de_nota_nueva`: la cola de la nota anterior, que se
        # resolvio y sigue sonando, no cuenta. Armarla con cualquier cuadro
        # creible hacia que, de la nota 2 en adelante, la bandera quedara
        # siempre verdadera (la cola la rearmaba justo despues de que el acierto
        # la limpiara), y entonces una pausa para pensar -o el cable
        # desenchufado- regalaba la respuesta resaltada en el mastil sin haber
        # tocado nada. Se lee del cuadro que el detector acaba de consumir, no de
        # la pulsacion: el detector la calcula antes de resolver nada.
        if self._pulsaciones.senal_de_nota_nueva:
            self._hubo_senal_creible_nota_actual = True

        # El reloj del disparador temporal no arranca mientras no haya habido
        # senal que pueda ser un intento de ESTA nota: hasta entonces se arrastra
        # al presente. Sin esto, los segundos que el alumno pasa leyendo el
        # ejercicio -o con el cable desenchufado- se descuentan de la ventana, y
        # la ayuda salta en el primer cuadro creible que llegue despues, con lo
        # que una pausa para pensar seguiria regalando la respuesta resaltada.
        if not self._hubo_senal_creible_nota_actual:
            self._instante_nota_actual = instante

        if pulsacion is not None:
            self._aplicar(pulsacion, instante)

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

    def _aplicar(self, pulsacion: Pulsacion, instante: float) -> None:
        """Decide que hacer con una pulsacion que el detector dio por buena.

        `pulsacion.instante` es el onset que se anota en el informe (el ataque de
        energia, o el comienzo de la racha estable). `instante` es el del cuadro
        que se esta procesando, y es OTRA cosa: llega despues del onset, y es el
        que sella el comienzo de la ventana temporal de la nota siguiente.
        Sellarla con el onset (como se hacia antes) hacia empezar la cuenta de
        `segundos_para_ayuda` de la nota nueva antes de que la anterior se
        hubiera resuelto.
        """
        esperada = self._nota_actual
        if esperada is None:
            return

        self._intentos += 1

        if pulsacion.nota == nombre_de_midi(esperada.midi):
            # Regla 2: la afinacion se guarda, no bloquea.
            self._hechas.append(
                IntentoNota(
                    indice=self._indice,
                    midi=esperada.midi,
                    intentos=self._intentos,
                    cents=pulsacion.cents,
                    instante=pulsacion.instante,
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
            return

        self._ultimo_fallo = pulsacion.nota
        # Regla 3: se ayuda, no se salta.
        if self._intentos >= self.intentos_para_ayuda:
            self._ayuda_mostrada = True

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
