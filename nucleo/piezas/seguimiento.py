"""Seguir una pieza: manda el reloj, no los aciertos.

La diferencia con `EvaluadorEjercicio` no es de detalle, es de genero. Un
ejercicio es por turnos: la nota espera a que la aciertes y no avanza hasta
entonces. Una pieza es musica: el reloj corre, la nota pasa, y si no llegaste no
se repite. De ahi sale todo lo que hace este modulo:

- El indice de la nota en curso lo decide el reloj (`avanzar_a`), no el acierto.
- Una pulsacion no hace avanzar nada: solo se anota contra la nota a la que
  corresponde, con su desfase.
- Fallar no bloquea ni descalifica: `acertada` y `clasificacion` informan, igual
  que la afinacion en los ejercicios.

Que nota sono y cuando lo decide `DetectorPulsaciones`, compartido con el
evaluador de ejercicios. Aqui solo se decide a que nota de la pieza le toca cada
pulsacion y como de tarde llego.
"""

import threading
from dataclasses import dataclass, replace

import numpy as np

from collections.abc import Callable

from nucleo.analisis.acordes import DetectorAcordes
from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones, Pulsacion
from nucleo.musica import esta_afinada, midi_de_nombre, nombre_de_midi
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos

# Cuanto puede desviarse una pulsacion del instante escrito y seguir contando
# como "a tiempo".
#
# De donde sale: por debajo de unos 30 ms dos ataques no se perciben como
# separados, asi que una ventana mas estrecha marcaria como error algo que el
# oido no distingue; por encima de unos 100 ms el desfase ya se oye como error, y
# llamarlo "a tiempo" seria mentir. Dentro de ese margen hay que descontar la
# latencia del cable, medida en 13,8 ms, que el alumno no toca mal sino que el
# programa oye tarde. 80 ms cae en ese hueco con sitio para la latencia.
#
# NO esta calibrado tocando: es un valor razonado sobre umbrales de percepcion y
# una latencia medida, no el resultado de sentarse con la guitarra a ver cuando
# un alumno siente que ha llegado tarde. Esa calibracion esta pendiente y es la
# unica que puede justificar mover este numero.
VENTANA_A_TIEMPO_S = 0.080

# Piso de la ventana de reclamo: lo mas lejos que se puede haber tocado una nota
# y seguir siendo un intento de ELLA, por corta que sea la figura.
#
# De donde sale: la ventana de reclamo se deriva de la duracion escrita (ver
# `SeguidorPieza._ventanas_reclamo_s`), y eso solo funciona mientras la figura sea
# larga. Con semicorcheas a 200 ppm la nota dura 75 ms y la ventana se quedaba en
# 155 ms: mas estrecha que el error de un principiante, asi que una nota tocada
# 200 ms tarde -que el brief quiere que cuente como "tarde"- no se adjudicaba a
# nadie y desaparecia del informe. Medio segundo esta muy por encima del retraso
# real de un principiante (los desfases que se ven tocando lento son de decenas de
# milisegundos, no de cientos) y muy por debajo del absurdo que la ventana existe
# para cortar (una pulsacion suelta 30 s despues del final). La ventana es el mayor
# de los dos: el piso manda en figuras cortas y la duracion manda en las largas.
#
# TAMPOCO esta calibrado tocando, igual que VENTANA_A_TIEMPO_S: es un orden de
# magnitud razonado, no el resultado de medirle el retraso a nadie con la guitarra
# en la mano. Esa calibracion sigue pendiente.
VENTANA_RECLAMO_MINIMA_S = 0.500

# Lo mas lejos que puede estar una coincidencia de ALTURA para que todavia sea la
# nota que el alumno estaba intentando, y no otra nota de la pieza que se llama
# igual. Simetrica: vale lo mismo llegando tarde que pronto.
#
# De donde sale: la preferencia por altura existe porque en un pasaje denso el
# tiempo no distingue cual se quiso tocar y el nombre de la nota si (ver
# `SeguidorPieza`). Pero sin tope, esa preferencia alcanzaba notas a 750 ms -mas
# de una negra entera a 80 ppm- y le adjudicaba la pulsacion a una nota que el
# alumno no habia tocado todavia, o que se habia saltado hacia atras. Asi que la
# altura necesita su propia vecindad, mas estrecha que la ventana de reclamo: la
# del error humano, no la de la figura.
#
# Por que 0,25 s: cae entre las dos medidas que hay que respetar a la vez. Por
# arriba, el caso que motivo la preferencia -una semicorchea a 200 ppm tocada 200
# ms tarde o pronto- tiene que seguir yendo por altura, asi que el tope no puede
# bajar de 0,205 s. Por abajo, una nota de la misma altura a 400 ms ya no es un
# intento de ella: es otra nota de la pieza, y adjudicarsela deja la que de
# verdad se fallo sin marca. Entre 0,205 y 0,4, el cuarto de segundo es el numero
# redondo.
#
# NO esta calibrado tocando, igual que VENTANA_A_TIEMPO_S y
# VENTANA_RECLAMO_MINIMA_S: es un orden de magnitud razonado entre dos medidas
# hechas con el codigo, no el resultado de medirle el error a nadie con la
# guitarra en la mano. Esa calibracion sigue pendiente.
VENTANA_ALTURA_S = 0.250


@dataclass(frozen=True)
class NotaTocada:
    """Una pulsacion ya adjudicada a una nota de la pieza.

    `indice` es la nota de la PIEZA a la que se adjudico; `midi` es lo que
    SONO, que es otra cosa en cuanto el alumno se equivoca (y es justo lo que la
    interfaz necesita para decirle que toco en su lugar). La nota escrita se
    recupera con `indice`, y `acertada` ya compara las dos.

    `desfase_s` es negativo si se toco antes de tiempo. Vale None -y con el
    `clasificacion`- cuando la pulsacion llego sin instante (ver
    `Pulsacion.instante`): no se sabe cuando empezo, y fabricar un desfase con el
    instante del cuadro mediria el retraso del detector, no el del alumno.

    `afinada` es el veredicto de la DESVIACION, con la misma regla que el resto
    del programa (`nucleo.musica.esta_afinada`). Se publica calculado aqui porque
    es un veredicto, y los veredictos los decide el nucleo: la interfaz se copiaba
    el umbral de 5 cents para elegir el color, que es la clase de duplicacion que
    en la etapa 2a hubo que quitar cuatro veces. Vale None cuando `cents` es None
    -no se supo la desviacion-, que no es ni afinada ni desafinada.
    """

    indice: int
    midi: int
    cents: float | None
    desfase_s: float | None
    clasificacion: str | None
    acertada: bool
    afinada: bool | None
    # True cuando la nota se cobro por PRESENCIA y no por ataque propio: es una
    # cuerda de un acorde que sonaba cuando se rasgueo el grupo, verificada con el
    # detector de acordes sobre la ventana cruda. Lleva `cents`, `desfase_s`,
    # `clasificacion` y `afinada` a None por fuerza y no por descuido (ver la spec
    # de la 2b, §4.4.1): copiarle el desfase a la nota hermana que SI tuvo ataque
    # publicaria la colocacion del rasgueo como si fuera la de cada cuerda, y
    # cualquier promedio de tiempo saldria con una muestra repetida tantas veces
    # como cuerdas tenga el acorde. Quien haga estadistica de tiempo filtra por
    # este campo.
    por_presencia: bool = False

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "midi": self.midi,
            "nombre": nombre_de_midi(self.midi),
            "cents": None if self.cents is None else round(self.cents, 1),
            "desfase_s": None if self.desfase_s is None else round(self.desfase_s, 3),
            "clasificacion": self.clasificacion,
            "acertada": self.acertada,
            "afinada": self.afinada,
            "por_presencia": self.por_presencia,
        }


@dataclass(frozen=True)
class EstadoCarril:
    """Lo que el carril necesita pintar en cada instante.

    `instante_s` es el reloj de la PIEZA, en segundos desde su comienzo: es la
    posicion del cabezal en el carril, no un instante del reloj del sistema.

    `indice_actual` es la ultima nota que ya empezo segun ese reloj. Antes de la
    primera señala a la primera y pasado el final se queda en la ultima: quien
    quiera saber si la pieza termino mira `completado`, no el indice. Si en ese
    instante hay un ACORDE -varias notas con el mismo inicio- señala a la ultima
    de ellas, que es una eleccion arbitraria entre iguales, porque el seguidor no
    senala a UNA nota y un acorde son varias (ver `SeguidorPieza`). Esta frontera
    es la que lee la interfaz, asi que la arbitrariedad se dice aqui y no solo
    alla.

    `tocadas` solo trae las pulsaciones que se pudieron adjudicar. Una nota que
    nadie toco no aparece: el carril la pinta sin marca, y contar "cuantas
    faltan" es `total` menos lo que hay aqui.
    """

    instante_s: float
    indice_actual: int
    total: int
    completado: bool
    tocadas: tuple[NotaTocada, ...]

    def a_dict(self) -> dict:
        return {
            "instante_s": round(self.instante_s, 3),
            "indice_actual": self.indice_actual,
            "total": self.total,
            "completado": self.completado,
            "tocadas": [tocada.a_dict() for tocada in self.tocadas],
        }


class SeguidorPieza:
    """Sigue una pieza con el reloj por delante y las pulsaciones por detras.

    Dos relojes, y no hay que confundirlos:

    - El reloj de la PIEZA, en segundos desde su comienzo, es el que dice que
      nota toca ahora. Se mueve con `avanzar_a`, que no consume audio: es lo que
      el servidor llama cuando no llega señal y lo que permite probar todo esto
      sin una sola espera real.
    - El reloj del ANALISIS es el que acompaña a cada cuadro de audio en
      `procesar`. Es `time.monotonic()`, con los dias de encendido de la maquina
      dentro. El seguidor guarda la correspondencia entre los dos, fijada en el
      primer cuadro tras colocar el reloj de la pieza, y traduce. Restar sin
      traducir haria que el desfase midiera la antiguedad del proceso en vez del
      error del alumno.

    Como se adjudica una pulsacion: de entre las notas sin cobrar que caen dentro
    de su ventana de reclamo, gana una cuya ALTURA coincida con lo que sono (la
    mas cercana de ellas si hay varias), y solo si ninguna coincide se cae a la
    mas cercana EN EL TIEMPO. La altura es informacion gratis y en un pasaje denso
    -notas a 75 ms unas de otras- es la unica que puede decir cual se quiso tocar:
    por cercania sola, una nota tocada 200 ms tarde se adjudicaba a la vecina y
    salia "a_tiempo" y equivocada. Los fallos de altura siguen yendo por cercania,
    que es donde tienen sentido.

    La altura DESEMPATA ENTRE VECINAS, con su propia ventana y simetrica
    (`VENTANA_ALTURA_S`, un cuarto de segundo AL TEMPO ESCRITO): una nota de la misma altura mas
    lejos que eso no es la que el alumno estaba intentando, es otra nota de la
    pieza que se llama igual, y adjudicarsela deja sin marca la que de verdad
    fallo. Es un tope de DISTANCIA, no de direccion: adelantarse es tan normal
    como retrasarse, y acotar solo un lado devolvia el fantasma por el otro (ver
    `_adjudicar`).

    En ningun caso se adjudica a la nota en curso por estar en curso. Tocar antes
    de tiempo es lo normal -es lo que hace un musico que va con el pulso-,
    y adjudicar esa pulsacion a la nota anterior convertiria un adelanto de 50 ms
    en un fallo y ademas dejaria la nota buena sin cobrar. Cada nota se cobra una
    sola vez, acertada o no: una segunda pulsacion busca otra nota. Y todo esto tiene
    un limite: cada nota solo se puede reclamar desde su ventana de reclamo, que
    es ASIMETRICA -llegando tarde, su duracion escrita mas la ventana de "a
    tiempo", con un piso de `VENTANA_RECLAMO_MINIMA_S` AL TEMPO ESCRITO (`_ventanas_reclamo_s`);
    llegando pronto, solo ese piso (`_ventana_reclamo_pronto_s`)-, y una pulsacion
    que no alcanza a ninguna no se anota ni cuenta como fallo. Sin ese limite,
    una nota que el alumno nunca toco acababa en el informe como tocada -y
    acertada- con un desfase absurdo.

    LOS ACORDES SE COBRAN EN DOS MITADES, y solo si se le dio un detector de
    acordes al construirlo (`detector_acordes` + `proveedor_de_muestras`). `Pieza`
    admite dos notas con el mismo `inicio_pulsos` a proposito -los archivos de
    Guitar Pro de la etapa 3b los traen-, y debajo de este seguidor sigue habiendo
    un detector de tono MONOFONICO, que de un rasgueo lee UNA altura. Esa mitad no
    cambia: el ataque se adjudica como siempre, con su desfase, su clasificacion y
    sus cents. Lo que se anade es la otra mitad: en cuanto una nota de un grupo se
    cobra por ataque, las DEMAS notas de ese mismo grupo se verifican por
    PRESENCIA contra la ventana cruda (`nucleo.analisis.acordes`), y las que suenan
    se cobran con `por_presencia=True` y sin cents ni desfase (el por que, en la
    spec de la 2b §4.4.1 y en `NotaTocada`).

    El ataque es la PUERTA, y es deliberado: sin el, los armonicos de un acorde
    vecino cobrarian un acorde que nadie rasgueo. El detector monofonico autoriza
    y el de acordes solo reparte.

    SIN detector de acordes el comportamiento es el de antes: de un acorde se cobra
    una sola nota y las demas quedan sin cobrar. Es el caso de todas las pruebas
    que construyen el seguidor a secas, y de cualquier pieza seguida sin audio
    crudo a mano.

    TEMPO AJUSTABLE (`factor_tempo`, 1.0 es el tempo escrito, 0.5 la mitad). Las
    tres ventanas y TODOS los instantes -los de las notas, los que toma
    `avanzar_a`, los de `estado`- estan en segundos DE LA PASADA, es decir ya
    estirados por el factor. Las constantes del modulo (`VENTANA_A_TIEMPO_S`,
    `VENTANA_RECLAMO_MINIMA_S`, `VENTANA_ALTURA_S`) son la referencia AL TEMPO
    ESCRITO: los numeros de arriba (80 ms, medio segundo, un cuarto de segundo)
    son ciertos solo con factor 1.0; al 50 % se duplican. Lo que se lee de la
    instancia son los atributos estirados, no las constantes.

    - `factor_tempo`: el factor, de solo lectura; se fija al construir.
    - `duracion_s`: duracion de la pieza en segundos de la pasada.
    - `olvidar_tramo(desde_s, hasta_s)`: deja sin cobrar las notas de ese tramo
      y borra sus anotaciones, para poder repetir un bucle.
    - `avanzar_a(instante_s, frontera_del_salto_s=None, instante_analisis_s=None)`:
      con los dos ultimos, el salto es CONTINUO -la vuelta de un bucle-, trae su
      correspondencia escrita y las pulsaciones en vuelo no se tiran: las de antes
      de la frontera se adjudican con el reloj en que se atacaron y se retienen en
      la COLA.
    - `recoger_la_cola()`: entrega esas notas retenidas y las olvida. No salen en
      `estado.tocadas`, que es el tramo que corre.

    Candado: este seguidor lleva el suyo (`_candado`) y protege tambien al
    `DetectorPulsaciones`, que no lleva ninguno. `procesar` y `avanzar_a` corren
    en el hilo de analisis y `estado` se lee desde el hilo HTTP/WS (la Task 5 lo
    publica a 30 Hz): sin candado, una instantanea podia mezclar el reloj de
    antes de avanzar con las notas de despues. Toda mutacion del detector pasa
    por aqui; quien añada otro consumidor tiene que traer su propio candado.
    """

    def __init__(
        self,
        pieza: Pieza,
        detector: DetectorPulsaciones | None = None,
        ventana_a_tiempo_s: float = VENTANA_A_TIEMPO_S,
        ventana_reclamo_minima_s: float = VENTANA_RECLAMO_MINIMA_S,
        ventana_altura_s: float = VENTANA_ALTURA_S,
        factor_tempo: float = 1.0,
        detector_acordes: DetectorAcordes | None = None,
        proveedor_de_muestras: Callable[[int], np.ndarray | None] | None = None,
    ) -> None:
        # `not > 0` y no `<= 0`: con NaN la segunda comparacion da False y lo dejaria pasar.
        if not factor_tempo > 0:
            raise ValueError(
                f"El factor de tempo es {factor_tempo}: tiene que ser mayor que cero"
            )
        self.pieza = pieza
        self._detector = detector or DetectorPulsaciones()
        self._factor_tempo = float(factor_tempo)
        # Las tres ventanas se ESTIRAN con el factor, y es una decision de la
        # etapa 3c, no un efecto secundario: practicando al 50 % lo que se juzga
        # es la colocacion dentro del compas, con la misma indulgencia a
        # cualquier velocidad, y al subir el tempo la ventana se cierra sola. Las
        # constantes siguen siendo la referencia AL TEMPO ESCRITO.
        self.ventana_a_tiempo_s = ventana_a_tiempo_s / self._factor_tempo
        self.ventana_reclamo_minima_s = ventana_reclamo_minima_s / self._factor_tempo
        self.ventana_altura_s = ventana_altura_s / self._factor_tempo

        def segundos(pulsos: float) -> float:
            """Pulsos a segundos DE LA PASADA: el factor estira el reloj entero.

            El factor divide el resultado y NO multiplica el tempo: `tempo` es un
            entero validado por `pulsos_a_segundos`, y 0,7 x 100 no es un tempo.
            """
            return pulsos_a_segundos(pulsos, pieza.tempo) / self._factor_tempo

        # Los instantes escritos, ya en segundos: se consultan en cada cuadro
        # (buscar la nota en curso y la mas cercana) y no cambian nunca.
        self._inicios_s = np.array(
            [segundos(nota.inicio_pulsos) for nota in pieza.notas],
            dtype=float,
        )
        # Hasta donde puede estirarse una pulsacion para reclamar cada nota
        # LLEGANDO TARDE. El lado "pronto" no se deriva de la duracion: ver
        # `_ventana_reclamo_pronto_s` justo debajo.
        #
        # Se deriva de la PIEZA y no es un numero clavado: la duracion escrita de
        # la nota mas la ventana de "a tiempo". Al bajar el tempo para practicar
        # lento la nota dura mas y la ventana se ensancha sola, que es lo que hace
        # falta (a 40 ppm nadie llega con la precision de 120).
        #
        # Pero derivarla solo de la duracion se rompe por abajo: con figuras cortas
        # a tempo rapido la ventana se vuelve mas estrecha que el error humano que
        # se quiere tolerar, asi que hay un piso, `VENTANA_RECLAMO_MINIMA_S`, y la
        # ventana es el MAYOR de los dos.
        #
        # Sin este limite, una pulsacion suelta se adjudicaba a la nota huerfana
        # mas cercana por lejos que estuviera: una nota que el alumno NUNCA toco
        # entraba en el informe como tocada y acertada con un desfase de 30 s, y
        # todo lo que se publique encima -porcentaje de acertadas, desfase medio,
        # regularidad- quedaba envenenado.
        self._ventanas_reclamo_s = np.maximum(
            np.array(
                [
                    segundos(nota.duracion_pulsos) + self.ventana_a_tiempo_s
                    for nota in pieza.notas
                ],
                dtype=float,
            ),
            self.ventana_reclamo_minima_s,
        )
        # Lo mas PRONTO que se puede reclamar una nota. No se deriva de la
        # duracion escrita, y por eso no es un vector sino un solo numero.
        #
        # El argumento de la duracion es un argumento sobre llegar TARDE: la nota
        # todavia suena, asi que una pulsacion que cae dentro sigue siendo un
        # intento de ella. Aplicado tambien hacia atras autorizaba reclamarla
        # igual de pronto, y eso no se sostiene: una redonda a 40 ppm se podia
        # reclamar 6,08 s ANTES de su instante, asi que una nota equivocada
        # tocada en el sitio de otra se adjudicaba a la redonda del futuro -con
        # `acertada=True` y 1,5 s de "pronto"- en vez de a la nota que estaba
        # debajo del dedo. Hoy lo tapaban los cuatro generadores, que producen
        # `pulsos=1.0`; la etapa 3b, que es para lo que existe `nucleo/piezas/`,
        # trae figuras largas de verdad.
        #
        # Tocar antes de tiempo es lo normal, asi que el lado pronto no puede ser
        # cero: lo acota la ventana de "a tiempo" con el mismo piso que el otro
        # lado, es decir lo que se tolera de error humano, no lo que dure la
        # figura.
        self._ventana_reclamo_pronto_s = max(self.ventana_a_tiempo_s, self.ventana_reclamo_minima_s)
        # Las alturas escritas, para adjudicar por nombre y no solo por cercania.
        self._midis = np.array([nota.midi for nota in pieza.notas], dtype=int)
        # Los GRUPOS: las notas que comparten `inicio_pulsos` son un acorde. Se
        # calculan una vez porque no cambian, y se guardan como el conjunto de
        # indices de cada grupo indexado por nota, para que cobrar el resto de un
        # acorde sea una busqueda y no un barrido.
        #
        # Se agrupa por el instante ESCRITO en pulsos y no por los segundos ya
        # estirados: el factor de tempo multiplica a todos por igual, asi que
        # agrupar por segundos daria el mismo resultado con un float mas de error.
        grupos: dict[float, list[int]] = {}
        for indice, nota in enumerate(pieza.notas):
            grupos.setdefault(nota.inicio_pulsos, []).append(indice)
        # Solo los grupos de mas de una nota son acordes. Una nota suelta no tiene
        # "resto del acorde" que cobrar, y dejarla fuera del diccionario es lo que
        # hace que el camino monofonico no pague nada por esto.
        self._grupo_de: dict[int, tuple[int, ...]] = {
            indice: tuple(miembros)
            for miembros in grupos.values()
            if len(miembros) > 1
            for indice in miembros
        }
        self._detector_acordes = detector_acordes
        self._proveedor_de_muestras = proveedor_de_muestras
        self._duracion_s = pieza.duracion_s / self._factor_tempo
        self._candado = threading.RLock()
        self.reiniciar()

    def reiniciar(self) -> None:
        """Vuelve al comienzo de la pieza y olvida lo tocado."""
        with self._candado:
            self._detector.reiniciar()
            if self._detector_acordes is not None:
                # El bufer del detector de acordes guarda 171 ms de audio del tramo
                # que se abandona. Sin vaciarlo, el primer acorde del tramo nuevo se
                # juzgaria en parte con lo que sonaba antes del salto.
                self._detector_acordes.reiniciar()
            self._instante_pieza = 0.0
            # Instante del reloj del analisis que corresponde a `_instante_pieza`.
            # None es "todavia sin fijar": lo fija el proximo cuadro.
            self._origen_analisis: float | None = None
            # Instante del reloj del analisis desde el que la correspondencia
            # actual es valida: el primer cuadro tras colocar el reloj a mano.
            # Un onset anterior se midio con otra correspondencia (ver `procesar`).
            self._analisis_desde: float | None = None
            # La correspondencia RETIRADA por el ultimo salto continuo, y el
            # instante del reloj del analisis en que ese salto fue continuo. Las
            # dos a None es "no hay salto continuo vigente", que es el caso de
            # todos los saltos menos la vuelta del bucle (ver `avanzar_a`).
            self._origen_retirado: float | None = None
            self._frontera_del_salto: float | None = None
            self._tocadas: list[NotaTocada] = []
            # La COLA: las pulsaciones que se atacaron antes de la frontera del
            # ultimo salto continuo y que el detector firmo despues. No son del
            # tramo que corre, asi que no salen en `estado.tocadas`: se las lleva
            # `recoger_la_cola`.
            self._tocadas_de_la_cola: list[NotaTocada] = []
            self._cobradas = np.zeros(len(self._inicios_s), dtype=bool)
            # Lo que la cola ya cobro, aparte de `_cobradas` y a proposito: la
            # nota de la frontera es de la vuelta que CERRO, asi que la vuelta que
            # abre tiene que poder cobrar su propia copia de esa misma nota. Lo
            # que este array impide es que dos pulsaciones DE LA COLA se lleven la
            # misma nota; lo que la vuelta que cierra ya tenia cobrado no se puede
            # saber desde aqui (ver `avanzar_a`).
            self._cobradas_de_la_cola = np.zeros(len(self._inicios_s), dtype=bool)

    @property
    def factor_tempo(self) -> float:
        """Factor de tempo (1.0 = el escrito); se fija al construir y no cambia."""
        return self._factor_tempo

    def olvidar_tramo(self, desde_s: float, hasta_s: float) -> None:
        """Deja sin cobrar las notas de [desde_s, hasta_s) y borra sus anotaciones.

        Es lo que permite REPETIR: al volver al principio del bucle, las notas de
        ese tramo tienen que poder cobrarse otra vez o la segunda pasada saldria
        entera en blanco.

        Los instantes son del reloj de la PASADA, los mismos que `avanzar_a`.

        No toca el reloj ni el detector: quien repite llama ademas a `avanzar_a`,
        que es lo que invalida la correspondencia con el reloj del analisis y
        descarta las pulsaciones en vuelo del tramo que se abandona. Las dos
        cosas van juntas y en ese orden.
        """
        with self._candado:
            dentro = (self._inicios_s >= desde_s) & (self._inicios_s < hasta_s)
            self._cobradas[dentro] = False
            indices = set(np.flatnonzero(dentro).tolist())
            self._tocadas = [t for t in self._tocadas if t.indice not in indices]

    @property
    def duracion_s(self) -> float:
        """Duracion de la pieza en segundos DE LA PASADA, con el factor ya aplicado."""
        return self._duracion_s

    @property
    def estado(self) -> EstadoCarril:
        """Instantanea COHERENTE del carril, construida entera bajo candado."""
        with self._candado:
            return EstadoCarril(
                instante_s=self._instante_pieza,
                indice_actual=self._indice_en_curso(self._instante_pieza),
                total=len(self.pieza),
                completado=self._instante_pieza >= self._duracion_s,
                tocadas=tuple(self._tocadas),
            )

    def recoger_la_cola(self) -> tuple[NotaTocada, ...]:
        """Las notas que se atacaron ANTES del ultimo salto continuo, y las olvida.

        Es la otra mitad de `avanzar_a(..., frontera_del_salto_s=...)`: lo que se
        retuvo del tramo que se abandono, para que quien dio el salto lo cuente en
        el informe del tramo al que pertenece. Se entrega UNA vez; la segunda
        llamada devuelve la tupla vacia.

        NO sale en `estado.tocadas` y es deliberado: el carril pinta el tramo que
        corre, y una nota de la vuelta anterior pintada sobre la vuelta nueva
        seria una marca en una nota que todavia no se ha tocado.
        """
        with self._candado:
            cola = tuple(self._tocadas_de_la_cola)
            self._tocadas_de_la_cola = []
            return cola

    def avanzar_a(
        self,
        instante_s: float,
        frontera_del_salto_s: float | None = None,
        instante_analisis_s: float | None = None,
    ) -> EstadoCarril:
        """Mueve el reloj de la pieza a `instante_s`. No consume audio.

        Es la unica forma de mover el reloj sin señal, y por eso es tambien la que
        deja probar el carril sin esperas: las pruebas lo colocan a mano.

        Mover el reloj a mano invalida la correspondencia con el del analisis (el
        cabezal ya no esta donde el ultimo cuadro decia), asi que se vuelve a
        fijar en el proximo cuadro.

        Y invalida algo mas: las pulsaciones EN VUELO. El detector resuelve un
        onset hasta 250 ms despues de que ocurriera, con su instante en el reloj
        del analisis; si el reloj de la pieza salta entremedias, traducir ese
        onset con la correspondencia nueva lo coloca donde no paso nada. Con un
        salto a 3,0 s, una pulsacion tocada en el segundo 1,0 se adjudicaba a la
        nota 3 y "a tiempo". Por eso `_adjudicar` descarta los onsets anteriores
        al primer cuadro posterior a este salto: lo que se toco antes de la pausa
        pertenece al tramo que se acaba de abandonar.

        **`frontera_del_salto_s` es la excepcion, y es UNA sola: el salto
        CONTINUO.** Quien lo pasa esta declarando que el reloj de la pieza vuelve
        atras pero no se ha ido a ninguna parte -la vuelta de un bucle: el audio
        sigue sonando sin un corte y ese instante del reloj del ANALISIS es el
        punto exacto en que el reloj de la pieza paso del final del tramo a su
        principio-. Y entonces el argumento de arriba no se aplica, porque se sabe
        DONDE paso cada cosa:

        * Un onset POSTERIOR a la frontera se ataco ya en el tramo nuevo: se
          adjudica con la correspondencia nueva, que es la que lo coloca bien, en
          vez de descartarse. Sin esto se perdia la primera nota de cada vuelta
          cuando su ataque caia en el mismo cuadro que la vuelta: medido con el
          gemelo, una nota cada tres vueltas con un interprete PERFECTO.
        * Un onset ANTERIOR se ataco en el tramo que se abandona, asi que se
          adjudica con la correspondencia RETIRADA -el reloj en que se ataco- y va
          a la COLA (`recoger_la_cola`), no a `estado.tocadas`. **Una nota
          pertenece a la vuelta en que se ATACO, no a la vuelta en que el detector
          la resolvio**, y el detector firma hasta
          `VENTANA_ATAQUE_COMO_ONSET_S` despues.

        **Y UN SALTO CONTINUO TRAE SU PROPIA CORRESPONDENCIA**
        (`instante_analisis_s`, el instante del reloj del ANALISIS en que el reloj
        de la pieza vale `instante_s`, o sea «ahora»). Es obligatorio con
        `frontera_del_salto_s` y no se acepta sin ella: las dos o ninguna.

        Esto es lo contrario de lo que hace un salto ordinario, y la razon es
        medida. Un salto ordinario DEJA LA CORRESPONDENCIA SIN FIJAR y la fija el
        cuadro siguiente, con el reloj donde el salto lo dejo, asi que entre los
        dos cuadros el reloj de la pieza se queda QUIETO: en un bucle, eso es un
        cuadro de analisis perdido en cada vuelta -21 ms a la cadencia de
        produccion- y el arrastre que la Task 7 vino a quitar. Un salto continuo
        no puede permitirselo, porque el audio no se para para que el reloj
        espere: el reloj de la pieza es CONTINUO en la frontera y la
        correspondencia se puede escribir exacta aqui mismo
        (`instante_analisis_s - instante_s`), sin estimar nada.

        Por eso `_analisis_desde` se fija en la FRONTERA y no en el cuadro
        siguiente: lo que separa las dos vueltas es el instante en que el reloj
        paso por el final del tramo, no el cuadro en que se entero nadie.

        Sin `frontera_del_salto_s` -el valor por omision y lo que hacen todos los
        demas llamadores: colocar, congelar, saltar de compas, la pausa, la cuenta
        atras, el hueco de audio- el comportamiento es exactamente el de antes:
        todo lo que estaba en vuelo se descarta y la correspondencia se vuelve a
        fijar en el cuadro siguiente.

        La frontera NO sobrevive al salto siguiente: un salto ordinario la borra,
        y con ella la cola que nadie recogio, porque ese tramo ya se abandono de
        verdad.

        Lanza `ValueError` si se da una de las dos cosas del salto continuo sin la
        otra: una frontera sin correspondencia dejaria el cuadro congelado que
        esto existe para no perder, y una correspondencia sin frontera adjudicaria
        con el reloj nuevo lo que se ataco con el viejo.
        """
        if (frontera_del_salto_s is None) != (instante_analisis_s is None):
            raise ValueError(
                "un salto continuo necesita la frontera Y la correspondencia: "
                f"frontera={frontera_del_salto_s}, analisis={instante_analisis_s}"
            )
        with self._candado:
            self._instante_pieza = float(instante_s)
            # La cola arranca sin nada cobrado en CUALQUIER salto, y aqui NO se
            # hereda lo que el tramo que se abandona llevaba cobrado, aunque
            # parezca lo natural. **No se puede desde aqui**: quien repite llama a
            # `olvidar_tramo` antes del salto -es su contrato, para que la vuelta
            # nueva pueda volver a cobrar- asi que cuando el salto llega
            # `_cobradas` ya esta a cero y heredarlo seria heredar ceros. Se probo
            # y se midio: la linea que lo heredaba no la ejecutaba ningun camino y
            # su mutante no mataba ni una prueba.
            #
            # Que una nota ya cobrada por la vuelta que cierra no se vuelva a
            # cobrar por la cola lo decide, por eso, quien cerro la vuelta:
            # `SesionDeEstudio._cobrar_la_cola`, que es el unico que sigue
            # teniendo esa lista. Lo que este array si decide es que dos
            # pulsaciones DE LA COLA no se adjudiquen a la misma nota.
            self._cobradas_de_la_cola[:] = False
            if frontera_del_salto_s is None:
                self._origen_retirado = None
                self._frontera_del_salto = None
                self._tocadas_de_la_cola = []
                self._origen_analisis = None
                self._analisis_desde = None
            else:
                self._origen_retirado = self._origen_analisis
                self._frontera_del_salto = float(frontera_del_salto_s)
                # La correspondencia, escrita y no estimada: el reloj de la pieza
                # vale `instante_s` en `instante_analisis_s`, y de ahi en adelante
                # corre con el analisis sin haberse parado un solo cuadro.
                self._origen_analisis = float(instante_analisis_s) - self._instante_pieza
                self._analisis_desde = float(frontera_del_salto_s)
            return self.estado

    def procesar(self, resultado: ResultadoAnalisis, instante_analisis: float) -> EstadoCarril:
        """Consume un cuadro de analisis y devuelve el estado del carril.

        `instante_analisis` es del reloj del ANALISIS, no de la pieza. El cuadro
        mueve el reloj de la pieza a traves de la correspondencia entre ambos, y
        al detector se le pasa tal cual: sus esperas (la de estabilizacion, la
        racha estable) estan medidas en su propio reloj.
        """
        with self._candado:
            if self._origen_analisis is None:
                self._origen_analisis = instante_analisis - self._instante_pieza
                self._analisis_desde = instante_analisis
            self._instante_pieza = instante_analisis - self._origen_analisis
            pulsacion = self._detector.procesar(resultado, instante_analisis)
            if pulsacion is not None:
                cobrada = self._adjudicar(pulsacion)
                if cobrada is not None:
                    self._cobrar_el_resto_del_acorde(cobrada)
            return self.estado

    def _indice_en_curso(self, instante_s: float) -> int:
        """Indice de la nota que el reloj señala: la ultima que ya empezo.

        Antes de la primera nota señala a la primera (es la que hay que
        prepararse a tocar), y pasado el final se queda en la ultima; quien
        quiera saber si la pieza termino mira `completado`.

        Con un acorde -varias notas en el mismo instante- devuelve la ultima de
        ellas, que es una eleccion arbitraria entre iguales: el indice es UNA nota
        y un acorde son varias. Cobrarlas si se sabe (ver la clase); senalar a
        todas a la vez con un solo entero, no.
        """
        if len(self._inicios_s) == 0:
            return 0
        indice = int(np.searchsorted(self._inicios_s, instante_s, side="right")) - 1
        return max(0, indice)

    def _adjudicar(self, pulsacion: Pulsacion) -> int | None:
        """Anota una pulsacion contra la nota sin cobrar mas cercana en el tiempo.

        Devuelve el indice de la nota que cobro, o None si la descarto. Lo
        devuelve para que `procesar` sepa sobre QUE grupo preguntar por el resto
        del acorde: el ataque es la puerta de la mitad por presencia (ver la
        clase), y sin este valor habria que adivinar cual fue mirando `_tocadas`.
        Las pulsaciones de la COLA devuelven None a proposito: son de un tramo ya
        abandonado, y la ventana cruda de ahora no dice nada de lo que sonaba
        entonces.

        Cuando `pulsacion.instante` es None no se sabe cuando empezo la nota (ver
        `Pulsacion.instante`): se adjudica con el reloj de la pieza en este cuadro,
        que es lo unico que hay, pero no se publica desfase ni clasificacion,
        porque ese instante llega despues del ataque y el numero que saldria seria
        el retraso del detector disfrazado de retraso del alumno.

        Una pulsacion se DESCARTA, sin anotar nada y sin contar como fallo, en
        tres casos:

        1. Ninguna nota sin cobrar cae dentro de su ventana de reclamo
           (`_ventanas_reclamo_s` hacia atras, `_ventana_reclamo_pronto_s` hacia
           delante). Una pulsacion parasita -o una nota tocada
           muchisimo despues del final- no puede adjudicarse a una nota que el
           alumno nunca toco: eso la meteria en el informe como tocada, y encima
           acertada si coincidia la altura.
        2. La pieza entera esta ya cobrada.
        3. El onset es anterior al primer cuadro de la correspondencia actual, es
           decir, se toco antes del ultimo `avanzar_a` (ver su docstring). **Con
           una excepcion: el salto CONTINUO**, donde un onset anterior no se
           descarta sino que se adjudica con el reloj en que se ataco y va a la
           cola (ver `avanzar_a` y `recoger_la_cola`).

        Descartar no es gratis, y se paga en el detector: el ya ha sellado esa nota
        como la ultima resuelta y ha gastado el instante del ataque antes de que
        aqui se decida nada.
        """
        if not self._cobradas.size:
            return None

        # Si esta pulsacion es de la COLA -atacada antes de la frontera del ultimo
        # salto continuo- se adjudica contra otro reloj y contra otro juego de
        # notas cobradas, asi que se decide antes de buscar nada.
        de_la_cola = False
        if pulsacion.instante is None:
            instante_onset: float | None = None
            instante_para_buscar = self._instante_pieza
        else:
            # `procesar` fija la correspondencia antes de llamar aqui, siempre. Si
            # faltara, el desfase saldria del tamaño de time.monotonic() y una
            # rama defensiva lo taparia en vez de delatarlo.
            assert self._origen_analisis is not None, "sin correspondencia entre relojes"
            origen = self._origen_analisis
            if self._analisis_desde is not None and pulsacion.instante < self._analisis_desde:
                if self._frontera_del_salto is None or self._origen_retirado is None:
                    return None
                if pulsacion.instante < self._frontera_del_salto:
                    de_la_cola = True
                    origen = self._origen_retirado
            instante_onset = pulsacion.instante - origen
            instante_para_buscar = instante_onset

        cobradas = self._cobradas_de_la_cola if de_la_cola else self._cobradas
        if cobradas.all():
            return None

        midi_tocado = midi_de_nombre(pulsacion.nota)
        # La ventana de reclamo es ASIMETRICA: hacia atras la manda la duracion
        # escrita (la nota todavia suena), hacia delante solo la tolerancia al
        # error humano (ver `_ventana_reclamo_pronto_s`).
        desfases = instante_para_buscar - self._inicios_s
        distancias = np.abs(desfases)
        limites = np.where(
            desfases >= 0, self._ventanas_reclamo_s, self._ventana_reclamo_pronto_s
        )
        reclamables = (~cobradas) & (distancias <= limites)
        if not reclamables.any():
            return None
        # La altura primero, la cercania despues. Cuando las notas van a 75 ms unas
        # de otras el tiempo no puede decir cual se quiso tocar, y el nombre de la
        # nota si: adjudicar solo por cercania mandaba una nota tocada 200 ms tarde
        # a la vecina de al lado, que salia "a_tiempo" y equivocada -un fantasma-
        # en vez de reconocer la nota real tocada tarde. Entre varias notas de la
        # misma altura gana la mas cercana. Si ninguna coincide, se cae a la mas
        # cercana en el tiempo: ahi es donde se anotan los fallos de altura, que
        # siguen saliendo con `acertada=False`.
        #
        # Pero la altura DESEMPATA ENTRE VECINAS, y por eso tiene su propia
        # ventana, `VENTANA_ALTURA_S`, mas estrecha que la de reclamo y SIMETRICA:
        # una coincidencia de altura mas lejos que eso no es la nota que el alumno
        # estaba intentando, es otra nota de la pieza que se llama igual.
        #
        # Lo que separa los dos casos es la DISTANCIA, no la direccion. Sin este
        # tope, las dos decisiones de rondas anteriores -la ventana de reclamo
        # derivada de la figura y la preferencia por altura- se juntaban y se
        # invertia el veredicto de dos notas en los dos sentidos, con la escala de
        # C mayor a 80 ppm (negras de 0,75 s):
        #
        # - Un dedo un traste bajo sobre la nota 5 (F3, sonando E3) se adjudicaba
        #   a la nota 6 (E3, 750 ms POR DELANTE) y salia acertada; la nota 5 se
        #   quedaba sin marca y el acierto siguiente salia fallado.
        # - El espejo: saltarse la nota 0 y poner el dedo un traste bajo en la 1
        #   (D3, sonando C3) se adjudicaba a la nota 0 (C3, 755 ms POR DETRAS) y
        #   salia acertada una nota que el alumno NUNCA toco.
        #
        # Una guarda por direccion solo tapa el primero, y encima rompe al alumno
        # que se adelanta: a 200 ppm, una nota tocada 200 ms PRONTO se iria a la
        # vecina, que es el fantasma que la preferencia por altura vino a matar.
        # Adelantarse es lo normal (ver la clase), asi que el tope es igual por
        # los dos lados.
        coincidentes = reclamables & (self._midis == midi_tocado) & (
            distancias <= self.ventana_altura_s
        )
        candidatas = coincidentes if coincidentes.any() else reclamables
        indice = int(np.argmin(np.where(candidatas, distancias, np.inf)))
        nota = self.pieza.notas[indice]
        cobradas[indice] = True

        if instante_onset is None:
            desfase: float | None = None
            clasificacion: str | None = None
        else:
            desfase = float(instante_onset - self._inicios_s[indice])
            clasificacion = self._clasificar(desfase)

        destino = self._tocadas_de_la_cola if de_la_cola else self._tocadas
        destino.append(
            NotaTocada(
                indice=indice,
                midi=midi_tocado,
                cents=pulsacion.cents,
                desfase_s=desfase,
                clasificacion=clasificacion,
                acertada=midi_tocado == nota.midi,
                afinada=None if pulsacion.cents is None else esta_afinada(pulsacion.cents),
            )
        )
        return None if de_la_cola else indice

    def _cobrar_el_resto_del_acorde(self, indice_del_ataque: int) -> None:
        """Cobra por PRESENCIA las demas notas del grupo de `indice_del_ataque`.

        El ataque ya se adjudico (es `indice_del_ataque`). Lo que queda es el
        resto de las cuerdas del mismo rasgueo, que no tienen ataque propio que
        detectar porque el rasgueo fue uno: se verifican contra la ventana cruda
        con el detector de acordes y se cobran las que suenan.

        No hace nada, y sin coste, cuando:

        - no se le dio detector de acordes o proveedor de muestras al construir el
          seguidor (el caso por defecto: el camino monofonico de siempre);
        - la nota del ataque no esta en ningun grupo de mas de una nota, es decir
          no es un acorde;
        - el proveedor no tiene todavia una ventana entera que dar (arranque de la
          captura, o una pasada movida a mano sin audio).

        **Al detector se le pasan los MIDI del grupo ENTERO, incluido el que ya se
        cobro por ataque.** No es un descuido: el detector normaliza contra la nota
        mas saliente de todo el mastil (ver `nucleo.analisis.acordes`), asi que lo
        que se le pregunta no depende de la lista que se le pase; pero la nota del
        ataque es casi siempre la mas fuerte del acorde, y dejarla fuera de la
        pregunta no cambiaria nada del veredicto mientras oculta en la lectura que
        el acorde que se verifica es el escrito completo.

        Lo que SI depende de la lista es `faltan`, y de ahi sale la decision: se
        cobra toda nota del grupo que este sin cobrar y NO este en `faltan`. Una
        que falta se queda sin cobrar, igual que hoy se queda una nota suelta que
        nadie toco: el carril la pinta sin marca. Marcar un fallo explicito por
        cuerda es la pantalla de ejercicios, no el carril.

        **Nunca cobra por la cola.** Una pulsacion de la cola devuelve None en
        `_adjudicar` y no llega aqui: la ventana cruda es de AHORA y no dice nada
        de lo que sonaba antes del salto.
        """
        detector = self._detector_acordes
        proveedor = self._proveedor_de_muestras
        if detector is None or proveedor is None:
            return
        grupo = self._grupo_de.get(indice_del_ataque)
        if grupo is None:
            return
        muestras = proveedor(detector.ventana)
        if muestras is None:
            return
        midis = [int(self.pieza.notas[i].midi) for i in grupo]
        resultado = detector.procesar(muestras, midis)
        if resultado.estado == "silencio":
            # Ni ventana llena ni señal por encima del ruido: el detector no vio
            # nada que juzgar. Que el ataque se haya cobrado no autoriza a dar por
            # presentes unas cuerdas que no se midieron.
            return
        faltan = set(resultado.faltan)
        self._corregir_el_ataque(indice_del_ataque, faltan)
        for indice in grupo:
            if self._cobradas[indice]:
                continue
            nota = self.pieza.notas[indice]
            if nota.midi in faltan:
                continue
            self._cobradas[indice] = True
            self._tocadas.append(
                NotaTocada(
                    indice=indice,
                    midi=nota.midi,
                    cents=None,
                    desfase_s=None,
                    clasificacion=None,
                    # `acertada=True` porque la pregunta que se contesto es
                    # precisamente «¿suena la nota ESCRITA?»: el detector verifica,
                    # no transcribe, asi que una nota presente es la escrita por
                    # construccion. Un dedo en el traste equivocado no sale aqui
                    # como una nota distinta: sale como la escrita ausente, y la
                    # escrita se queda sin cobrar.
                    acertada=True,
                    afinada=None,
                    por_presencia=True,
                )
            )

    def _corregir_el_ataque(self, indice: int, faltan: set[int]) -> None:
        """Revisa el veredicto de la nota del ataque con lo que dice la presencia.

        Un rasgueo no es una altura. El detector monofonico lee UNA, y en un
        acorde puede no ser ninguna de las escritas: un parcial fuerte, o la
        diferencia entre dos cuerdas. Cuando eso pasa, `_adjudicar` no encuentra
        ningun MIDI coincidente, cae en la nota mas cercana en el tiempo -y en un
        acorde todas empatan, asi que sale la mas grave- y la cobra con
        `acertada=False`. Luego esta nota ya estaba cobrada y la presencia no
        podia revisarla, asi que el informe lo leia como «3 de 4»: un error del
        alumno donde solo hubo una lectura de altura mala.

        Asi que si la presencia dice que la nota escrita SI suena, el veredicto se
        corrige. No es una amnistia: necesita la confirmacion, y si el detector la
        pone en `faltan` el fallo se queda tal cual.

        Que se conserva y que no:

        - `desfase_s` y `clasificacion` se QUEDAN. El ataque existio y su instante
          es real; lo que no valia era la altura. Ademas es la unica medida de
          tiempo que este rasgueo va a dar, y tirarla dejaria el compas sin ritmo
          medible.
        - `cents` y `afinada` se PONEN A None. Median la desviacion del parcial
          que se leyo, no la de esta cuerda, y publicar eso como la afinacion de
          la nota escrita seria mentir. `NotaTocada` ya admite esa combinacion
          -instante sin cents- y dice que `None` es "no se supo".
        - `por_presencia` se queda en False, porque hubo ataque: esta nota SI
          aporta una medida de tiempo, y es lo que ese campo separa.
        - `midi` pasa a ser el ESCRITO. Publicar el parcial que se leyo junto a
          `acertada=True` seria contradictorio -la fila diria "sono un C5" y a la
          vez "acertaste el C3"-, y la nota que la presencia verifico es la
          escrita por construccion: el detector comprueba, no transcribe.
        """
        for posicion in range(len(self._tocadas) - 1, -1, -1):
            tocada = self._tocadas[posicion]
            if tocada.indice != indice:
                continue
            if tocada.acertada:
                return
            escrita = int(self.pieza.notas[indice].midi)
            if escrita in faltan:
                return
            self._tocadas[posicion] = replace(
                tocada, midi=escrita, cents=None, acertada=True, afinada=None
            )
            return

    def _clasificar(self, desfase_s: float) -> str:
        """"a_tiempo", "pronto" (negativo) o "tarde" segun la ventana."""
        if abs(desfase_s) <= self.ventana_a_tiempo_s:
            return "a_tiempo"
        return "pronto" if desfase_s < 0 else "tarde"
