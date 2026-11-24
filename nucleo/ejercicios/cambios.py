"""Evaluador de cambios de acorde.

Consume `ResultadoAcorde` -un dato- igual que el evaluador monofonico consume
`ResultadoAnalisis`, y por el mismo motivo: asi toda la logica pedagogica se
prueba sin audio y sin hardware, escribiendo la secuencia exacta de alguien que
tarda dos segundos en el cambio o que deja muda la primera cuerda.

No reutiliza `EvaluadorEjercicio`, y la razon es que casi nada de aquel se aplica:
no hay `DetectorPulsaciones` -un rasgueo no es una pulsacion de altura estable-,
no hay cents, y la unidad de acierto es un acorde sostenido, no un ataque. Lo que
SI se copia deliberadamente, porque funciona y esta medido en la etapa 2a, son
tres reglas:

1. La exigencia no bloquea. Alla era la afinacion; aqui, que la presencia de cada
   nota no tiene que ser perfecta: basta que supere el umbral del detector.
2. Tras varios intentos se AYUDA, no se salta. Mismo numero y mismo respaldo
   temporal, porque el conteo de intentos puede no llegar nunca.
3. Un cuadro dudoso no cuenta como fallo. El silencio no es un error.
"""

import threading
from dataclasses import dataclass

import numpy as np

from nucleo.analisis.acordes import ResultadoAcorde
from nucleo.ejercicios.evaluacion import INTENTOS_PARA_AYUDA, SEGUNDOS_PARA_AYUDA
from nucleo.ejercicios.modelo import AcordeEsperado, Ejercicio

# Cuantos cuadros seguidos tiene que estar el acorde completo para darlo por bueno.
#
# Cuatro, unos 84 ms a la cadencia de analisis habitual (21 ms). Un cuadro suelto
# no basta: durante el rasgueo las cuerdas entran una tras otra, y hay un instante
# a mitad de camino en que el acorde esta "completo" por accidente -las que faltan
# todavia no han entrado y las que sobran ya han decaido-. Exigir una racha
# convierte ese accidente en lo que es: un instante, no un acorde.
#
# Y la misma racha se exige por el lado del fallo, para que un rasgueo torcido
# cuente UN intento y no cuatro.
CUADROS_PARA_ACORDE_ESTABLE = 4

# Cuanto se le perdona al alumno despues de dar un acorde por bueno.
#
# Un segundo. No es generosidad pedagogica: es que durante ese rato lo que suena
# NO es lo que el alumno esta tocando. Las cuerdas de un acorde abierto siguen
# vibrando mas de un segundo, y el detector ya esta juzgando contra el acorde
# siguiente, asi que publica "incompleto" sin que nadie haya intentado nada.
# Contar eso como intento fallido acusaba a las cuerdas del acorde que acababa de
# salir BIEN.
#
# El silencio corta la gracia de inmediato: si el alumno apaga las cuerdas y
# rasguea mal, eso si es un intento suyo y se cuenta. Y pasado el segundo, los
# cuadros incompletos vuelven a contar aunque la cuerda siga sonando: a partir de
# ahi es responsabilidad de la mano.
#
# El coste de equivocarse por este lado es un intento fallido que no se cuenta -el
# del alumno que rasguea torcido dentro del primer segundo sin apagar nada-. El de
# equivocarse por el otro era contar un fallo por cada cambio de acorde, siempre.
GRACIA_TRAS_ACERTAR_S = 1.0


@dataclass(frozen=True)
class IntentoAcorde:
    """Lo ocurrido con un acorde del ejercicio.

    cambio_s es None en el PRIMER acorde del ejercicio, y eso no es un dato que
    falte: antes del primero no hay nada de lo que cambiar. Tambien es None en un
    acorde que no se llego a tocar. `logrado` distingue los dos casos.
    """

    indice: int
    nombre: str
    intentos: int
    logrado: bool
    cambio_s: float | None
    faltaron: tuple[int, ...] = ()
    ayuda_mostrada: bool = False

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "nombre": self.nombre,
            "intentos": self.intentos,
            "logrado": self.logrado,
            "cambio_s": None if self.cambio_s is None else round(self.cambio_s, 2),
            "faltaron": list(self.faltaron),
            "ayuda_mostrada": self.ayuda_mostrada,
        }


@dataclass(frozen=True)
class EstadoCambios:
    """Lo que la pantalla necesita saber en cada instante."""

    indice: int
    total: int
    intentos: int
    ayuda_visible: bool
    completado: bool
    acorde_actual: AcordeEsperado | None
    faltan: tuple[int, ...] = ()
    ultimo_cambio_s: float | None = None

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "total": self.total,
            "intentos": self.intentos,
            "ayuda_visible": self.ayuda_visible,
            "completado": self.completado,
            "acorde_actual": None if self.acorde_actual is None else self.acorde_actual.a_dict(),
            "faltan": list(self.faltan),
            "ultimo_cambio_s": (
                None if self.ultimo_cambio_s is None else round(self.ultimo_cambio_s, 2)
            ),
        }


@dataclass(frozen=True)
class InformeCambios:
    """El informe que se muestra al terminar."""

    ejercicio: str
    acordes: tuple[IntentoAcorde, ...]
    completado: bool

    @property
    def tiempo_medio_de_cambio_s(self) -> float | None:
        """La cifra de cabecera: cuanto tardas de media en cambiar de acorde.

        Es la MEDIANA y no la media, por el mismo motivo que la desviacion del
        informe monofonico: un cambio en el que te quedaste pensando diez
        segundos no debe definir la sesion entera.

        None cuando no hay ningun cambio medido, que no es lo mismo que cero: no
        haber logrado ningun cambio no es cambiar instantaneamente.
        """
        cambios = [a.cambio_s for a in self.acordes if a.cambio_s is not None]
        if not cambios:
            return None
        return float(np.median(cambios))

    @property
    def cambio_mas_lento_s(self) -> float | None:
        """El peor cambio, que es donde conviene insistir."""
        cambios = [a.cambio_s for a in self.acordes if a.cambio_s is not None]
        return max(cambios) if cambios else None

    @property
    def cuerdas_problematicas(self) -> tuple[int, ...]:
        """Notas que faltaron mas veces, de mas a menos.

        Son numeros MIDI y no numeros de cuerda a proposito: la misma nota puede
        estar en cuerdas distintas segun el acorde, y lo que se repite es la nota
        que el dedo no llega a pisar.
        """
        cuenta: dict[int, int] = {}
        for intento in self.acordes:
            for midi in intento.faltaron:
                cuenta[midi] = cuenta.get(midi, 0) + 1
        return tuple(sorted(cuenta, key=lambda midi: (-cuenta[midi], midi)))

    @property
    def logrados(self) -> int:
        return sum(1 for a in self.acordes if a.logrado)

    @property
    def a_la_primera(self) -> int:
        """Acordes que salieron al primer intento y sin la ayuda puesta."""
        return sum(
            1 for a in self.acordes if a.logrado and a.intentos <= 1 and not a.ayuda_mostrada
        )

    def a_dict(self) -> dict:
        medio = self.tiempo_medio_de_cambio_s
        lento = self.cambio_mas_lento_s
        return {
            "ejercicio": self.ejercicio,
            "completado": self.completado,
            "acordes": [a.a_dict() for a in self.acordes],
            "logrados": self.logrados,
            "a_la_primera": self.a_la_primera,
            "tiempo_medio_de_cambio_s": None if medio is None else round(medio, 2),
            "cambio_mas_lento_s": None if lento is None else round(lento, 2),
            "cuerdas_problematicas": list(self.cuerdas_problematicas),
        }


class EvaluadorCambios:
    """Corrige un ejercicio de cambios acorde a acorde."""

    def __init__(
        self,
        ejercicio: Ejercicio,
        intentos_para_ayuda: int = INTENTOS_PARA_AYUDA,
        segundos_para_ayuda: float = SEGUNDOS_PARA_AYUDA,
        cuadros_para_acorde_estable: int = CUADROS_PARA_ACORDE_ESTABLE,
        gracia_tras_acertar_s: float = GRACIA_TRAS_ACERTAR_S,
    ) -> None:
        if not ejercicio.acordes:
            raise ValueError(
                f"El ejercicio '{ejercicio.clave}' no trae acordes: este evaluador "
                "solo corrige ejercicios de acordes"
            )
        if cuadros_para_acorde_estable < 1:
            raise ValueError("Hace falta al menos 1 cuadro para dar un acorde por estable")
        self.ejercicio = ejercicio
        self.intentos_para_ayuda = intentos_para_ayuda
        self.segundos_para_ayuda = segundos_para_ayuda
        self.cuadros_para_acorde_estable = cuadros_para_acorde_estable
        self.gracia_tras_acertar_s = gracia_tras_acertar_s
        # Mismo motivo que en EvaluadorEjercicio: se muta desde el hilo de
        # analisis y se lee desde el hilo HTTP/WS a 30 Hz. Reentrante porque
        # `_procesar_bajo_candado` construye la instantanea con `self.estado`.
        self._candado = threading.RLock()
        self.reiniciar()

    def reiniciar(self) -> None:
        """Vuelve al principio del ejercicio y olvida lo hecho."""
        with self._candado:
            self._indice = 0
            self._intentos = 0
            self._ayuda_mostrada = False
            self._faltan: tuple[int, ...] = ()
            self._hechos: list[IntentoAcorde] = []
            self._racha_completo = 0
            self._racha_incompleto = 0
            self._faltaron_este: list[int] = []
            # Cuando se dio por bueno el acorde anterior, para medir el cambio.
            self._instante_anterior: float | None = None
            self._ultimo_cambio_s: float | None = None
            # Hay que SOLTAR entre un acorde y el siguiente. Sin esto, sostener
            # un Do valdria por los dos Do de un ejercicio que pida Do, Do: la
            # racha de completo nunca se rompe y el segundo se regala sin que el
            # alumno mueva un dedo.
            self._hay_que_soltar = False
            # Cuantos cuadros seguidos llevamos viendo que el acorde anterior se
            # suelta. Ver la rama de `_hay_que_soltar` en `_procesar_bajo_candado`.
            self._racha_soltando = 0
            # Hasta cuando no se cuentan fallos, por la cola del acorde anterior.
            # None es "no hay gracia en curso". Ver `GRACIA_TRAS_ACERTAR_S`.
            self._fin_de_la_gracia: float | None = None
            # Respaldo temporal de la ayuda: desde cuando corre el reloj de este
            # acorde, y si ha habido alguna senal que pudiera ser un intento.
            self._instante_acorde_actual: float | None = None
            self._hubo_senal = False

    @property
    def _acorde_actual(self) -> AcordeEsperado | None:
        if self._indice >= len(self.ejercicio):
            return None
        return self.ejercicio.acordes[self._indice]

    @property
    def midis_esperados(self) -> tuple[int, ...]:
        """Lo que hay que pasarle al detector de acordes en este instante.

        Vacio cuando el ejercicio ha terminado, que es justo lo que el detector
        trata como "no hay acorde que juzgar".
        """
        actual = self._acorde_actual
        return () if actual is None else actual.midis

    @property
    def estado(self) -> EstadoCambios:
        """Instantanea coherente para la pantalla, construida bajo candado."""
        with self._candado:
            return EstadoCambios(
                indice=self._indice,
                total=len(self.ejercicio),
                intentos=self._intentos,
                ayuda_visible=self._ayuda_mostrada,
                completado=self._indice >= len(self.ejercicio),
                acorde_actual=self._acorde_actual,
                faltan=self._faltan,
                ultimo_cambio_s=self._ultimo_cambio_s,
            )

    def procesar(self, resultado: ResultadoAcorde, instante: float) -> EstadoCambios:
        """Consume un cuadro del detector y devuelve el estado resultante."""
        with self._candado:
            return self._procesar_bajo_candado(resultado, instante)

    def _procesar_bajo_candado(
        self, resultado: ResultadoAcorde, instante: float
    ) -> EstadoCambios:
        if self._indice >= len(self.ejercicio):
            return self.estado

        if self._instante_acorde_actual is None:
            self._instante_acorde_actual = instante

        if resultado.estado == "silencio":
            # Regla 3: el silencio no es un error. Rompe las dos rachas y es
            # ademas lo que cuenta como soltar entre dos acordes iguales.
            self._racha_completo = 0
            self._racha_incompleto = 0
            self._racha_soltando = 0
            self._hay_que_soltar = False
            # Y olvida lo que faltaba. `faltan` viaja al diagrama, que pinta las
            # cuerdas que no suenan: dejarlo puesto hacia que una guitarra
            # callada -el alumno para a recolocar la mano- siguiera marcando "no
            # suena" indefinidamente. Es la misma regla que cumple el detector,
            # que en silencio no rellena con el ultimo valor conocido. Lo que
            # falto no se pierde: queda en `_faltaron_este`, que es lo que el
            # informe cuenta.
            self._faltan = ()
            # Y corta la gracia: apagar las cuerdas prueba que lo que suene
            # despues ya es del alumno, no del acorde anterior.
            self._fin_de_la_gracia = None
        elif resultado.estado == "completo":
            self._racha_incompleto = 0
            if self._hay_que_soltar:
                # Sigue sonando el acorde anterior: no se acumula racha nueva.
                self._racha_completo = 0
            else:
                self._racha_completo += 1
                self._hubo_senal = True
                if self._racha_completo >= self.cuadros_para_acorde_estable:
                    self._acertar(instante)
        else:
            self._racha_completo = 0
            # SOLTAR se prueba con una racha, no con un cuadro.
            #
            # Soltar es lo que permite cobrar el acorde siguiente aunque sea el
            # mismo (ver `_hay_que_soltar` en `reiniciar`), y hasta ahora un
            # unico cuadro incompleto lo daba por hecho. Con eso basta el bache
            # del decaimiento normal -una cuerda baja del umbral un instante y
            # vuelve- para que un solo rasgueo sostenido cobre los dos Do de un
            # ejercicio "Do, Do" sin mover un dedo. Una racha no se da por
            # accidente.
            if self._hay_que_soltar:
                self._racha_soltando += 1
                if self._racha_soltando >= self.cuadros_para_acorde_estable:
                    self._hay_que_soltar = False
                    self._racha_soltando = 0
            # `_racha_incompleto` NO se toca aqui. Los cuadros que prueban que se
            # solto son casi siempre los de la cola, y esos ya no cuentan como
            # intento porque caen dentro de la gracia. Reiniciarla ademas dejaba
            # sin contar el fallo del alumno que sigue sonando pasado el segundo:
            # la racha se rompia justo antes de llegar a cuatro.

            if self._en_la_gracia(instante):
                # La cola del acorde ANTERIOR, no un intento de este.
                #
                # Las cuerdas del acorde que se acaba de dar por bueno siguen
                # vibrando mientras la mano se mueve, y el detector ya juzga
                # contra el acorde SIGUIENTE: devuelve "incompleto" sin que nadie
                # haya intentado nada. Cobrarlo como fallo hacia dos danos a la
                # vez: `a_la_primera` no contaba casi ningun acorde que no fuera
                # el primero, y `cuerdas_problematicas` -lo que la pantalla
                # presenta como "las que mas veces no sonaron"- acusaba a las
                # cuerdas del acorde que el alumno acababa de tocar BIEN.
                #
                # Por que esto es por TIEMPO y lo de soltar por RACHA, siendo los
                # dos "la cola del anterior": son dos preguntas distintas. Soltar
                # pregunta si el acorde dejo de estar completo, y eso se ve en
                # cuatro cuadros. La gracia pregunta cuanto dura la cola, y eso no
                # se ve en el dato: una cuerda al aire suena mas de un segundo.
                # Ver `GRACIA_TRAS_ACERTAR_S`.
                pass
            else:
                self._racha_incompleto += 1
                self._hubo_senal = True
                self._faltan = resultado.faltan
                if self._racha_incompleto == self.cuadros_para_acorde_estable:
                    self._fallar(resultado.faltan)

        # El reloj del respaldo temporal no arranca mientras no haya habido
        # senal que pueda ser un intento de ESTE acorde: hasta entonces se
        # arrastra al presente, igual que en el evaluador monofonico. Asi los
        # segundos que el alumno pasa leyendo el diagrama -o con el cable
        # desenchufado- no se descuentan de la ventana.
        if not self._hubo_senal:
            self._instante_acorde_actual = instante

        if (
            not self._ayuda_mostrada
            and self._hubo_senal
            and self._instante_acorde_actual is not None
            and instante - self._instante_acorde_actual >= self.segundos_para_ayuda
        ):
            self._ayuda_mostrada = True

        return self.estado

    def _en_la_gracia(self, instante: float) -> bool:
        """Si lo que suena todavia puede ser la cola del acorde anterior."""
        return self._fin_de_la_gracia is not None and instante < self._fin_de_la_gracia

    def _acertar(self, instante: float) -> None:
        """El acorde sono completo y sostenido: se cobra y se pasa al siguiente."""
        actual = self._acorde_actual
        if actual is None:
            return

        cambio = (
            None if self._instante_anterior is None else instante - self._instante_anterior
        )
        self._hechos.append(
            IntentoAcorde(
                indice=self._indice,
                nombre=actual.nombre,
                intentos=self._intentos + 1,
                logrado=True,
                cambio_s=cambio,
                faltaron=tuple(sorted(set(self._faltaron_este))),
                ayuda_mostrada=self._ayuda_mostrada,
            )
        )
        self._ultimo_cambio_s = cambio
        self._instante_anterior = instante
        self._indice += 1
        self._intentos = 0
        self._ayuda_mostrada = False
        self._faltan = ()
        self._faltaron_este = []
        self._racha_completo = 0
        self._racha_incompleto = 0
        self._racha_soltando = 0
        # Hay que soltar antes de poder acertar el siguiente, aunque sea el mismo
        # acorde: ver `_hay_que_soltar` en `reiniciar`.
        self._hay_que_soltar = True
        self._fin_de_la_gracia = instante + self.gracia_tras_acertar_s
        self._instante_acorde_actual = instante
        self._hubo_senal = False

    def _fallar(self, faltan: tuple[int, ...]) -> None:
        """Una racha de cuadros incompletos cuenta un intento y guarda que falto."""
        self._intentos += 1
        self._faltaron_este.extend(faltan)
        # Regla 2: se ayuda, no se salta.
        if self._intentos >= self.intentos_para_ayuda:
            self._ayuda_mostrada = True

    def resultado(self) -> InformeCambios:
        """Informe de lo hecho hasta ahora."""
        with self._candado:
            return InformeCambios(
                ejercicio=self.ejercicio.clave,
                acordes=tuple(self._hechos),
                completado=self._indice >= len(self.ejercicio),
            )
