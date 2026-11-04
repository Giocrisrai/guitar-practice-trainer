"""Estudiar una pieza: el plan de la pasada, el bucle y el informe.

Este objeto ENVUELVE al `SeguidorPieza` en vez de modificarlo, y la razon esta
escrita en la spec: el seguidor tiene dos relojes y una adjudicacion de
pulsaciones que costo mucho dejar correcta, y meterle un tercer reloj seria tocar
justo lo que no conviene tocar. Aqui vive todo lo que la etapa 3c anade; alli solo
llegaron `factor_tempo` y `olvidar_tramo`.

EL RELOJ DE LA PASADA ES EL DEL SEGUIDOR, ya estirado por el factor: con
`factor_tempo=0.5` una pieza de 10 s escritos dura 20 s de pasada. Lo que no
depende del tempo es `instante_pulsos`, y es lo que usan los compases.

NO ABRE AUDIO. El click lo pone el servidor, igual que con los ejercicios: aqui
solo se publica `repeticion`, y el servidor rearranca el metronomo cuando ese
numero cambia. Un contador es un dato; un `Metronomo` seria una dependencia del
nucleo con el dispositivo de sonido, y esta clase tiene que poder probarse entera
en silencio.
"""

import threading
from dataclasses import dataclass, replace

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import (
    VENTANA_ATAQUE_COMO_ONSET_S,
    DetectorPulsaciones,
)
from nucleo.piezas.compases import (
    compas_en,
    pulsos_del_compas,
    pulsos_por_compas,
    total_de_compases,
)
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos, segundos_a_pulsos
from nucleo.piezas.seguimiento import EstadoCarril, NotaTocada, SeguidorPieza

# Mas abajo del 40 % el carril ya no se parece a musica; por encima del 100 % se
# estaria practicando mas rapido que el original, que es otra cosa y no se
# construye aqui. El paso es el del deslizador de la interfaz.
FACTOR_MINIMO = 0.40
FACTOR_MAXIMO = 1.00
PASO_DEL_FACTOR = 0.05


@dataclass(frozen=True)
class PlanDePasada:
    """Como se toca esta vez. No cambia la pieza: cambia la pasada.

    Los valores por defecto son el comportamiento de la etapa 3a -pieza entera,
    tempo escrito, sin bucle, sin click-, asi que las piezas que vienen de los
    generadores de ejercicios no cambian en nada.

    `ultimo_compas` a None es "hasta el final": no se puede poner el numero aqui
    porque el plan se construye sin ver la pieza. Lo resuelve `validar_plan`.
    """

    primer_compas: int = 1
    ultimo_compas: int | None = None
    factor_tempo: float = 1.0
    en_bucle: bool = False
    compases_de_cuenta_atras: int = 1
    con_click: bool = False
    tempo_automatico: bool = False

    def __post_init__(self) -> None:
        if not FACTOR_MINIMO <= self.factor_tempo <= FACTOR_MAXIMO:
            raise ValueError(
                f"El tempo tiene que estar entre el {FACTOR_MINIMO:.0%} y el "
                f"{FACTOR_MAXIMO:.0%} del escrito, y pediste "
                f"{self.factor_tempo:.0%}"
            )
        if self.primer_compas < 1:
            raise ValueError(
                f"El primer compas es el 1, y pediste {self.primer_compas}"
            )
        # El 0 significa "pieza sin compases" y SOLO lo produce `validar_plan`:
        # un llamador que pide 0 en una pieza con compases es rechazado alli.
        if (
            self.ultimo_compas is not None
            and self.ultimo_compas != 0
            and self.ultimo_compas < self.primer_compas
        ):
            raise ValueError(
                f"El ultimo compas ({self.ultimo_compas}) no puede ir antes del "
                f"primero ({self.primer_compas})"
            )
        if self.compases_de_cuenta_atras < 0:
            raise ValueError(
                "Los compases de cuenta atras no pueden ser negativos, y pediste "
                f"{self.compases_de_cuenta_atras}"
            )

    def a_dict(self) -> dict:
        return {
            "primer_compas": self.primer_compas,
            "ultimo_compas": self.ultimo_compas,
            "factor_tempo": self.factor_tempo,
            "en_bucle": self.en_bucle,
            "compases_de_cuenta_atras": self.compases_de_cuenta_atras,
            "con_click": self.con_click,
            "tempo_automatico": self.tempo_automatico,
        }


def validar_plan(pieza: Pieza, plan: PlanDePasada) -> PlanDePasada:
    """Comprueba el plan CONTRA la pieza y devuelve `ultimo_compas` resuelto.

    Tras esta funcion `ultimo_compas` es SIEMPRE un entero. Si la pieza no tiene
    compases vale 0; ese 0 solo es legitimo en la pieza vacia, y en una pieza
    con compases pedirlo es un error.

    `PlanDePasada` valida lo que puede sin ver la pieza (el factor, el orden de
    los compases); lo que solo se sabe con la pieza delante -si el compas 20
    existe- se valida aqui. El mensaje nombra el compas pedido y el ultimo que
    hay, que es lo unico que le permite al usuario arreglarlo.
    """
    total = total_de_compases(pieza)
    if total == 0:
        return replace(plan, ultimo_compas=0)
    if plan.primer_compas > total:
        raise ValueError(
            f"La pieza '{pieza.nombre}' tiene {total} compases y pediste empezar "
            f"en el {plan.primer_compas}"
        )
    if plan.ultimo_compas == 0:
        raise ValueError(
            f"La pieza '{pieza.nombre}' tiene {total} compases y pediste acabar "
            "en el 0: el 0 solo vale para una pieza sin compases"
        )
    ultimo = total if plan.ultimo_compas is None else plan.ultimo_compas
    if ultimo > total:
        raise ValueError(
            f"La pieza '{pieza.nombre}' tiene {total} compases y pediste acabar "
            f"en el {ultimo}"
        )
    return replace(plan, ultimo_compas=ultimo)


@dataclass(frozen=True)
class CompasDelInforme:
    """Lo que paso en un compas de una pasada.

    `notas_medibles` son menos que `notas_escritas` cuando hay acordes: las notas
    de un acorde comparten instante, el detector de tono es MONOFONICO y lee una
    sola altura, asi que de un acorde de cuatro notas solo una se puede medir. Las
    otras tres no se cuentan como falladas porque no son un fallo del alumno, son
    un limite del programa.

    `desfase_medio_s` lleva SIGNO, y es el dato que de verdad diagnostica:
    "el 19 lo tocas entero 40 ms tarde" es accionable, "fallas el 19" no. Negativo
    es adelantarse, con la misma convencion que `NotaTocada.desfase_s`. Vale None
    cuando no se midio ni un desfase en ese compas.

    `limpias` cuenta las notas que fueron acertadas Y a tiempo A LA VEZ, nota a
    nota. No se deduce de `acertadas` y `a_tiempo`: son dos contadores
    independientes y un compas con una nota acertada-pero-tarde y otra
    a-tiempo-pero-de-otra-altura tiene uno y uno y cero limpias.
    """

    numero: int
    notas_escritas: int
    notas_medibles: int
    acertadas: int
    a_tiempo: int
    pronto: int
    tarde: int
    limpias: int
    desfase_medio_s: float | None
    tiene_acordes: bool

    def a_dict(self) -> dict:
        return {
            "numero": self.numero,
            "notas_escritas": self.notas_escritas,
            "notas_medibles": self.notas_medibles,
            "acertadas": self.acertadas,
            "a_tiempo": self.a_tiempo,
            "pronto": self.pronto,
            "tarde": self.tarde,
            "limpias": self.limpias,
            "desfase_medio_s": (
                None if self.desfase_medio_s is None else round(self.desfase_medio_s, 3)
            ),
            "tiene_acordes": self.tiene_acordes,
        }


@dataclass(frozen=True)
class InformeDePasada:
    """El informe del tramo que se esta estudiando, compas a compas.

    `repeticiones` dice cuantas vueltas del tramo hay sumadas en los contadores:
    1 en el informe de una sola vuelta, y mas en el acumulado de un bucle. Sin
    ese dato nadie puede convertir los contadores en una proporcion.
    """

    compases: tuple[CompasDelInforme, ...]
    ritmo_aproximado: bool
    compas_variable: bool
    factor_tempo: float
    repeticiones: int = 1

    def a_dict(self) -> dict:
        return {
            "compases": [c.a_dict() for c in self.compases],
            "ritmo_aproximado": self.ritmo_aproximado,
            "compas_variable": self.compas_variable,
            "factor_tempo": self.factor_tempo,
            "repeticiones": self.repeticiones,
        }


def proporcion_limpia(informe: InformeDePasada) -> float | None:
    """Que fraccion de las notas medibles se acerto Y a tiempo, 0 a 1.

    Las notas limpias se cuentan por nota y se dividen por lo medible de TODAS
    las vueltas que el informe lleva dentro (`medibles * repeticiones`): el
    numerador acumula vueltas y el denominador, sin esto, no.

    Los compases con acordes quedan FUERA, y es la decision que hace que la regla
    del tempo sirva: contandolos, cualquier cancion de Guitar Pro bajaria el tempo
    para siempre. Devuelve None cuando no hay ni una nota medible sin acordes -una
    pieza entera de acordes-, y quien lea esto tiene que distinguir None de 0,0:
    uno es "no se puede medir" y el otro es "lo fallaste todo".
    """
    medibles = sum(c.notas_medibles for c in informe.compases if not c.tiene_acordes)
    if medibles == 0:
        return None
    buenas = sum(c.limpias for c in informe.compases if not c.tiene_acordes)
    return buenas / (medibles * max(1, informe.repeticiones))


@dataclass(frozen=True)
class EstadoEstudio:
    """Lo que la interfaz necesita: el estado del carril mas el de la pasada.

    `a_dict` publica los campos del carril AL MISMO NIVEL y no anidados: la
    interfaz de la etapa 3a ya lee `instante_s`, `indice_actual`, `total`,
    `completado` y `tocadas` del paquete del WebSocket, y anidarlos obligaria a
    tocar `useCarril.ts` sin ningun motivo.
    """

    carril: EstadoCarril
    instante_pulsos: float
    compas_en_curso: int
    total_de_compases: int
    primer_compas: int
    ultimo_compas: int
    repeticion: int
    cuenta_atras_restante_s: float
    factor_tempo: float
    tempo_efectivo: float
    en_bucle: bool
    con_click: bool
    tempo_automatico: bool
    en_pausa: bool
    compas_variable: bool
    ritmo_aproximado: bool
    tramo_terminado: bool

    def a_dict(self) -> dict:
        return {
            **self.carril.a_dict(),
            "instante_pulsos": round(self.instante_pulsos, 3),
            "compas_en_curso": self.compas_en_curso,
            "total_de_compases": self.total_de_compases,
            "primer_compas": self.primer_compas,
            "ultimo_compas": self.ultimo_compas,
            "repeticion": self.repeticion,
            "cuenta_atras_restante_s": round(self.cuenta_atras_restante_s, 3),
            "factor_tempo": self.factor_tempo,
            "tempo_efectivo": round(self.tempo_efectivo, 2),
            "en_bucle": self.en_bucle,
            "con_click": self.con_click,
            "tempo_automatico": self.tempo_automatico,
            "en_pausa": self.en_pausa,
            "compas_variable": self.compas_variable,
            "ritmo_aproximado": self.ritmo_aproximado,
            "tramo_terminado": self.tramo_terminado,
            # `completado` del carril es "se acabo la PIEZA"; para quien practica
            # un tramo, lo que se acabo es el tramo. Se publica con el mismo
            # nombre porque es lo que la interfaz de la etapa 3a ya lee.
            "completado": self.tramo_terminado or self.carril.completado,
        }


class SesionDeEstudio:
    """Un seguidor, un plan, y el informe de lo que va pasando.

    CANDADO PROPIO, y hace falta: el servidor la muta desde DOS hilos. El hilo de
    analisis entra por `procesar` -y a proposito fuera del candado de
    `SesionCarril`, que no quiere nada lento dentro-, mientras el hilo HTTP puede
    estar en `cambiar_plan`, `saltar_al_compas` o `cerrar_repeticion` sobre el
    mismo objeto. El candado del `SeguidorPieza` no cubre nada de eso: esta etapa
    anadio media docena de campos mutables AQUI (`_cuenta_atras_restante_s`,
    `_tramo_terminado`, `_acumulado`, `_vueltas_cerradas`, `_repeticion`,
    `_ultimo_analisis`, y el propio `_seguidor`, que `cambiar_plan` REEMPLAZA).
    Sin candado, un `cambiar_plan` colado entre el `procesar` del seguidor y el
    `_al_dia` de la misma llamada adjudicaba la pulsacion del cuadro a un seguidor
    que se estaba tirando, y el `destino[clave] += valor` de `cerrar_repeticion`
    no es atomico.

    Es REENTRANTE porque varios de estos metodos se llaman entre si:
    `cambiar_plan` y `saltar_al_compas` acaban en `colocar_en`, `arrancar` tambien,
    `reiniciar_pasada` llama a `arrancar`, y `_dar_la_vuelta` -desde `avanzar` o
    `procesar`- llama a `cerrar_repeticion`.

    ORDEN DE LOS CANDADOS, comprobado: el del seguidor se toma SIEMPRE DENTRO de
    este (es este objeto quien llama al seguidor, nunca al reves) y el seguidor no
    llama hacia arriba -no conoce a esta clase-, asi que no hay inversion posible.
    El de `SesionCarril` queda SIEMPRE FUERA de este -el servidor llama al nucleo
    y no al reves-, asi que la cadena es carril -> estudio -> seguidor y nunca se
    recorre en otro sentido.
    """

    def __init__(
        self,
        pieza: Pieza,
        plan: PlanDePasada = PlanDePasada(),
        detector: DetectorPulsaciones | None = None,
    ) -> None:
        # Ver el docstring de la clase: reentrante, y el del seguidor va dentro.
        self._candado = threading.RLock()
        self.pieza = pieza
        self._plan = validar_plan(pieza, plan)
        self._detector = detector
        self._repeticion = 1
        self._en_pausa = False
        self._cuenta_atras_restante_s = 0.0
        # Contadores por compas de ESTA pasada, con lo de las repeticiones ya
        # cerradas. Lo que todavia esta en el seguidor se suma al leer el informe
        # y se vuelca aqui en `cerrar_repeticion`: asi nada se cuenta dos veces y
        # el informe esta siempre al dia.
        self._acumulado: dict[int, dict] = {}
        self._vueltas_cerradas = 0
        # El reparto de notas por compas solo depende de la pieza, que no cambia:
        # se calcula una vez y no en cada lectura del informe (la interfaz lo
        # pide muchas veces por segundo).
        self._reparto = self._indices_por_compas()
        self._compas_de_cada_nota = {
            indice: numero
            for numero, indices in self._reparto.items()
            for indice in indices
        }
        self._tramo_terminado = False
        # El instante del reloj del ANALISIS en que el tramo se dio por acabado
        # con audio entrando, o None si acabo sin audio (o no ha acabado). Lo usa
        # `_ataques_en_vuelo` para aplazar la recolocacion del reloj.
        self._analisis_al_acabar: float | None = None
        # El informe de la ultima vuelta del bucle que se cerro, o None si
        # todavia no se cerro ninguna. Lo lee el servidor para el historial.
        self._ultima_vuelta: InformeDePasada | None = None
        # Y las `NotaTocada` de esa misma vuelta, que el informe NO lleva: solo
        # lleva conteos por compas. Sin esto, lo adjudicado en el mismo cuadro
        # que da la vuelta no es observable por ninguna API publica (ver
        # `_dar_la_vuelta` y la propiedad `tocadas_de_la_ultima_vuelta`).
        self._tocadas_de_la_vuelta: tuple[NotaTocada, ...] = ()
        # El ultimo instante del reloj del ANALISIS que vimos, solo para sacar
        # el delta de la cuenta atras cuando el tiempo viene en cuadros.
        self._ultimo_analisis: float | None = None
        self._seguidor = self._nuevo_seguidor()
        self._seguidor.avanzar_a(self._inicio_s())

    # -- construccion y conversiones -------------------------------------

    def _nuevo_seguidor(self) -> SeguidorPieza:
        return SeguidorPieza(
            self.pieza, self._detector, factor_tempo=self._plan.factor_tempo
        )

    def _segundos(self, pulsos: float) -> float:
        """Pulsos de la pieza a segundos DE LA PASADA."""
        return pulsos_a_segundos(pulsos, self.pieza.tempo) / self._plan.factor_tempo

    # Decimales de pulso a los que se redondea el viaje de vuelta (ver `_pulsos`).
    # Nueve esta MUY por debajo de lo que cualquier figura musical distingue -la
    # semifusa de un 4/4 es 0,0625 pulsos-, asi que redondear ahi no puede mover
    # nada que se vea, y en cambio borra la clase entera de defecto que trae el
    # binario.
    DECIMALES_DE_PULSO = 9

    def _pulsos(self, segundos_de_pasada: float) -> float:
        """Segundos DE LA PASADA a pulsos de la pieza. Redondeado a proposito.

        El redondeo esta AQUI, en el viaje de vuelta, porque aqui esta la causa:
        `_segundos` divide por el factor y esto vuelve a multiplicar por el, y ese
        ida y vuelta no es exacto en binario. Con `factor_tempo=0.95`, el inicio
        del compas 2 -4 pulsos- sale de `_segundos` como 4,2105... y vuelve como
        3,9999999999999996, que es un pulso MENOS de cuatro: `compas_en` lo lee
        como compas 1 y el numero de compas de la pantalla se equivoca justo al
        cruzar la barra, que es cuando el alumno mas lo mira.

        Y NO esta en `compas_en` ni en ningun otro consumidor, aunque alli tambien
        se taparia: `compas_en` recibe pulsos de muchos sitios -los lectores, el
        informe, la rejilla- y la mayoria no vienen de este ida y vuelta, asi que
        redondear alli seria disimular este defecto en un sitio que no lo causa y
        dejarlo vivo para el siguiente consumidor que llegue. Arreglada la
        conversion, todos los que la usan quedan arreglados a la vez.
        """
        return round(
            segundos_a_pulsos(
                segundos_de_pasada * self._plan.factor_tempo, self.pieza.tempo
            ),
            self.DECIMALES_DE_PULSO,
        )

    def _inicio_s(self) -> float:
        """Donde empieza el tramo del plan, en segundos de la pasada."""
        if total_de_compases(self.pieza) == 0:
            return 0.0
        desde, _ = pulsos_del_compas(self.pieza, self._plan.primer_compas)
        return self._segundos(desde)

    def _fin_s(self) -> float:
        """Donde acaba el tramo del plan, en segundos de la pasada."""
        if total_de_compases(self.pieza) == 0:
            return 0.0
        _, hasta = pulsos_del_compas(self.pieza, self._plan.ultimo_compas)
        return self._segundos(hasta)

    # -- lo que ve el de fuera -------------------------------------------

    @property
    def plan(self) -> PlanDePasada:
        return self._plan

    @property
    def estado(self) -> EstadoEstudio:
        carril = self._seguidor.estado
        pulsos = self._pulsos(carril.instante_s)
        # El compas se acota al ultimo del tramo, y no es cosmetica: los pulsos
        # del compas son un intervalo MEDIO ABIERTO, asi que el reloj parado en
        # el final del compas 3 cae ya en el 4. Sin acotar, al terminar un tramo
        # la pantalla decia "compas 4" de un bucle que va del 2 al 3.
        compas = compas_en(self.pieza, pulsos)
        if self._plan.ultimo_compas is not None:
            # El suelo en 1: en la pieza vacia el ultimo compas es 0 y el cabezal
            # sigue estando en el compas 1, el unico que no miente.
            compas = max(1, min(compas, self._plan.ultimo_compas))
        return EstadoEstudio(
            carril=carril,
            instante_pulsos=pulsos,
            compas_en_curso=compas,
            total_de_compases=total_de_compases(self.pieza),
            primer_compas=self._plan.primer_compas,
            ultimo_compas=self._plan.ultimo_compas,
            repeticion=self._repeticion,
            cuenta_atras_restante_s=self._cuenta_atras_restante_s,
            factor_tempo=self._plan.factor_tempo,
            tempo_efectivo=self.pieza.tempo * self._plan.factor_tempo,
            en_bucle=self._plan.en_bucle,
            con_click=self._plan.con_click,
            tempo_automatico=self._plan.tempo_automatico,
            en_pausa=self._en_pausa,
            compas_variable=self.pieza.compas_variable,
            ritmo_aproximado=self.pieza.ritmo_aproximado,
            tramo_terminado=self._tramo_terminado,
        )

    @property
    def ultima_vuelta(self) -> InformeDePasada | None:
        """El informe de la ultima vuelta del bucle cerrada, o None si no hubo."""
        return self._ultima_vuelta

    @property
    def tocadas_de_la_ultima_vuelta(self) -> tuple[NotaTocada, ...]:
        """Las `NotaTocada` de la ultima vuelta cerrada. Vacia si no hubo ninguna.

        Es la hermana de `ultima_vuelta` y existe por un defecto medido: lo que se
        adjudica en el MISMO cuadro que da la vuelta no aparece en ningun
        `estado.carril.tocadas` de ninguna llamada. `procesar` llama al seguidor y,
        en la misma llamada, acaba en `_dar_la_vuelta` -> `cerrar_repeticion`, cuyo
        ultimo acto es `olvidar_tramo`, y devuelve el estado DESPUES de eso. El
        informe de la vuelta no lo salva: solo lleva conteos por compas, no las
        notas. Sin esta propiedad, quien quiera saber QUE nota se adjudico en ese
        cuadro -el gemelo digital recogiendo el registro, o la interfaz- no tiene
        por donde preguntarlo.
        """
        return self._tocadas_de_la_vuelta

    def _segundos_de_cuenta_atras(self) -> float:
        if self._plan.compases_de_cuenta_atras == 0:
            return 0.0
        return self._segundos(
            pulsos_por_compas(self.pieza) * self._plan.compases_de_cuenta_atras
        )

    def _delta_del_analisis(self, instante_analisis: float) -> float:
        """Cuanto tiempo paso entre dos cuadros, nunca negativo y SIN HUECOS.

        Solo lo necesita la cuenta atras: el reloj de la pieza lo mueve
        `procesar` del seguidor por su correspondencia, no esta resta.

        **UN HUECO DE AUDIO NO ES TIEMPO TRANSCURRIDO Y AQUI VALE CERO.** Es la
        misma regla que `ConductorDeEstudio` escribe para el reloj de la pasada
        -«un hueco largo no entra en la pieza por ningun camino»- y el mismo
        criterio con que ese conductor decide que un cuadro llega tras un apagon
        (`_hueco_de_audio`, que mide `VENTANA_ATAQUE_COMO_ONSET_S` contra el reloj
        del analisis). Se vuelve a aplicar aqui porque el conductor no lo puede
        aplicar por nosotros: `congelar_en` -lo que llama al detectar el hueco- NO
        reinicia `_ultimo_analisis`, asi que el cuadro siguiente llega con el hueco
        entero en la resta.

        Era un defecto medido en los dos caminos que la usan, y el segundo lo
        trajo la rama que le entrega al reloj lo que sobra del cuadro que agota la
        cuenta:

        * la cuenta atras se la comia un apagon de golpe -30 s de hueco se tragan
          cualquier cuenta-, cuando `congelar_en` existe precisamente para que
          perder la señal en plena cuenta NO sea motivo para tirarla;
        * y lo que sobraba de ese hueco se le daba al reloj: medido con un hueco de
          30 s dentro de la cuenta, **el cabezal se iba al final del tramo y el
          bucle daba una VUELTA FANTASMA** que nadie toco (repeticion 2 con el
          alumno con el cable desenchufado).

        El techo es el del propio detector y no un numero nuevo: por encima de
        `VENTANA_ATAQUE_COMO_ONSET_S` sin un cuadro no queda nada en vuelo que
        pueda resolverse, que es la definicion de hueco que ya usan el conductor
        (`ESPERA_SIN_CUADROS_S`) y `_ataques_en_vuelo`. Y el hueco vale CERO y no
        el techo, porque el tiempo sin señal no entra en la pieza por ninguna
        puerta: quien desenchufa el cable a media cuenta y lo vuelve a enchufar se
        encuentra la cuenta DONDE LA DEJO, no reiniciada y no gastada.

        Es el mismo razonamiento que `_exceso_de_la_vuelta` escribe dos metodos mas
        abajo -«un exceso mayor que el tramo no es una vuelta sino un salto de
        reloj»- aplicado a la otra punta.
        """
        anterior = self._ultimo_analisis
        self._ultimo_analisis = instante_analisis
        if anterior is None:
            return 0.0
        delta = max(0.0, instante_analisis - anterior)
        return 0.0 if delta >= VENTANA_ATAQUE_COMO_ONSET_S else delta

    def _exceso_de_la_vuelta(self, inicio: float, fin: float) -> float:
        """Con cuanto se paso el reloj del final del tramo, acotado al tramo.

        EL EXCESO NO SE TIRA, y tirarlo era el defecto central del bucle. El
        reloj no cruza el final del tramo en el final exacto: lo cruza en el
        primer cuadro de analisis POSTERIOR, con hasta 21 ms de exceso (y con lo
        que mida la mirada, en el camino sin audio). Dando la vuelta a `inicio`
        pelado, el audio de la vuelta siguiente empieza donde tocaba pero el
        reloj empieza re-anclado, y la diferencia SE ACUMULA vuelta a vuelta.
        Medido con el gemelo antes del arreglo, cuatro vueltas de un interprete
        PERFECTO: desfase medio +36,1, +2,6, -36,0 ms -unos 36 ms por vuelta-, y
        con ocho vueltas la quinta ya salia con 2 notas limpias de 8 y la sexta
        con 0.

        El exceso se ACOTA a la longitud del tramo, y no es cosmetica: un exceso
        mayor que el tramo entero no es una vuelta sino un salto de reloj -una
        mirada tras un apagon, un `avanzar` con un delta enorme-, y arrastrarlo
        dejaria el cabezal mas alla del final del tramo recien abierto. Acotado,
        el reloj siempre queda DENTRO del tramo.
        """
        return min(max(0.0, self._seguidor.estado.instante_s - fin), max(0.0, fin - inicio))

    def _dar_la_vuelta(self, con_audio: bool = False) -> None:
        """Los cuatro pasos del bucle, en este orden y no en otro.

        El informe de la vuelta que acaba se guarda en `_ultima_vuelta`, porque
        quien lo necesita -el historial- se entera de la vuelta mirando
        `repeticion` DESPUES de que esto haya pasado, y entonces ya no podria
        pedirlo. Y con el las `NotaTocada` de esa vuelta, por el mismo motivo y
        por uno mas: lo adjudicado en el MISMO cuadro que da la vuelta no aparece
        en ningun `estado.carril.tocadas` de ninguna llamada -`procesar` devuelve
        el estado DESPUES de que `cerrar_repeticion` haya vaciado el seguidor-,
        asi que sin esta linea esas notas no son observables por ninguna API
        publica. El informe solo lleva conteos por compas.

        **El exceso con que el reloj cruzo el final se CONSERVA, y con audio el
        salto lleva ademas su correspondencia escrita.** Son las dos mitades de lo
        mismo -que la vuelta no le robe tiempo al reloj- y hacen falta las dos:

        * El exceso (`_exceso_de_la_vuelta`): el reloj no cruza el final en el
          final exacto, y tirar la diferencia arrastraba ~15 ms por vuelta.
        * La correspondencia: con audio, el reloj de la pieza lo mueve SOLO la
          correspondencia entre los dos relojes del seguidor, y un salto ordinario
          la deja sin fijar hasta el cuadro siguiente, con lo que el reloj se
          queda quieto un cuadro entero (21 ms por vuelta a la cadencia de
          produccion). Pasandole al seguidor el instante del analisis en que el
          reloj vale `inicio + exceso`, la correspondencia queda escrita y **no
          hay nada que estimar**.

        La version anterior de esto SI estimaba: le sumaba al exceso «la cadencia
        recien medida». Era un defecto medido y lo delato una revision: si el
        cuadro que cruza el final llega tarde -un hueco de audio-, ese retraso
        entra en el exceso, que es correcto, **y otra vez** en la cadencia, que es
        lo que se sumaba. Con un hueco de 300 ms en la frontera, la vuelta nueva
        arrancaba en 0,359 s en vez de 0,059, y con un tramo corto el tope se lo
        comia entero y la vuelta se saltaba. Escribir la correspondencia en vez de
        estimarla no arregla el doble conteo: lo hace imposible, y de paso deja el
        reloj exacto a cualquier cadencia (comprobado a 7,5 / 21 / 40 / 100 ms por
        cuadro, con desvio 0,000).

        SIN AUDIO no hay correspondencia ni frontera que pasar, y no hace falta:
        `avanzar` suma el tramo transcurrido sobre el reloj que haya, asi que la
        vuelta no congela nada.
        """
        inicio, fin = self._inicio_s(), self._fin_s()
        exceso_del_cruce = self._exceso_de_la_vuelta(inicio, fin)
        cuenta = self._segundos_de_cuenta_atras()
        # **CON CUENTA ATRAS, EL EXCESO SE LE DEBITA A LA CUENTA Y NO AL RELOJ**, y
        # es la primera mitad del arrastre que el bucle CON cuenta tenia (la
        # segunda esta en `procesar`). El exceso es tiempo que ya paso desde que el
        # reloj cruzo el final del tramo, y con una cuenta atras abierta ese tiempo
        # lo gasta la CUENTA: la cuenta empieza en la frontera, no en el cuadro que
        # se entero. Dandoselo al reloj -que es lo que se hacia- la cuenta duraba
        # `exceso` de mas y el reloj no se lo quedaba, porque mientras la cuenta
        # corre esta clavado en el inicio: se perdia en cada vuelta.
        #
        # Si el exceso es MAYOR que la cuenta, lo que sobra sigue yendo al reloj:
        # un exceso enorme es un salto de reloj y no una vuelta, y tragarselo
        # entero en una cuenta de dos compases seria inventarse una cuenta corta.
        #
        # Sin cuenta atras (`cuenta == 0`) esto no hace nada y el exceso va al
        # reloj, que es lo que la T7 dejo medido.
        gastado_en_la_cuenta = min(exceso_del_cruce, cuenta)
        cuenta -= gastado_en_la_cuenta
        exceso = exceso_del_cruce - gastado_en_la_cuenta
        frontera = None
        ahora = None
        if con_audio and self._ultimo_analisis is not None:
            # LA FRONTERA ES UN INSTANTE DEL RELOJ DEL ANALISIS, no un cuadro: es
            # el instante en que el reloj de la pieza paso por el final del tramo,
            # que no es este cuadro sino `exceso` segundos antes (el reloj avanza
            # con el analisis y por eso la resta vale). Lo que atacaste antes de
            # ese instante es de la vuelta que cierra y lo que atacaste despues es
            # de la que abre, y el seguidor necesita el numero para decidirlo.
            #
            # Y la correspondencia va con ella, por el mismo motivo por el que la
            # resta vale: el reloj de la pieza marca `inicio + exceso` AHORA.
            #
            # La frontera se resta con el exceso DEL CRUCE y no con el que le queda
            # al reloj: la frontera es el instante en que el reloj paso por el final
            # del tramo, y eso no cambia porque parte de ese tiempo se le debite a
            # la cuenta atras. Restar el debitado la pondria en este cuadro y le
            # regalaria a la vuelta nueva lo que se ataco antes de ella.
            ahora = self._ultimo_analisis
            frontera = ahora - exceso_del_cruce
        self._tocadas_de_la_vuelta = tuple(self._seguidor.estado.tocadas)
        self._ultima_vuelta = self.cerrar_repeticion()
        self._seguidor.olvidar_tramo(inicio, fin)
        self._seguidor.avanzar_a(
            inicio + exceso,
            frontera_del_salto_s=frontera,
            instante_analisis_s=ahora,
        )
        self._repeticion += 1
        self._cuenta_atras_restante_s = cuenta

    def _cobrar_la_cola(self) -> None:
        """Vuelca al informe de la vuelta que CERRO lo que se ataco antes de ella.

        El detector firma un onset hasta `VENTANA_ATAQUE_COMO_ONSET_S` (250 ms)
        despues de que ocurriera, asi que la ultima nota de una vuelta se resuelve
        con la vuelta siguiente ya abierta. **Una nota pertenece a la vuelta en que
        se ATACO**, no a la vuelta en que el detector la resolvio: una nota atacada
        50 ms antes del final cuenta en la vuelta que cierra, y lo contrario le
        regalaria a la vuelta nueva una nota que nadie toco en ella.

        Quien las retiene es el seguidor -son suyas, y es el unico que tiene el
        reloj en que se atacaron- y aqui solo se cobran: suman al acumulado de la
        pasada, se anaden a las `NotaTocada` de la vuelta y el informe de esa
        vuelta se vuelve a armar con ellas dentro. Rearmarlo y no parchearlo es lo
        que mantiene `InformeDePasada` inmutable.

        Se llama en CADA cuadro con audio y no solo tras la vuelta: la cola puede
        tardar varios cuadros en llenarse, y preguntar siempre cuesta una tupla
        vacia.

        **UNA NOTA DE LA VUELTA NO SE COBRA DOS VECES, y eso se decide aqui.** La
        cola lleva su propio registro de lo cobrado -la nota de la frontera es de
        la vuelta que cierra, asi que la vuelta que abre tiene que poder cobrar su
        propia copia de esa misma nota-, pero ese registro arranca vacio en cada
        vuelta y no sabe lo que la vuelta que cerro ya habia cobrado: cuando
        `cerrar_repeticion` se llevo sus `NotaTocada`, el seguidor dejo de tenerlo.
        El unico que lo sabe es este metodo, porque es quien guarda
        `_tocadas_de_la_vuelta`.

        Sin esta guarda, dos ataques cerca de la frontera -machacando un compas no
        es nada exotico- cobraban la misma nota dos veces: medido, la nota 3 salia
        en `estado.tocadas` «a tiempo» con +0,000 y OTRA VEZ en la cola «tarde»
        con +0,900, y como `_contar` no deduplica y esto suma encima del informe
        ya cerrado, **el compas salia con mas acertadas que notas escritas**.
        Exactamente lo que la regla 1 de `_adjudicar` promete que no pasa, y con
        el tempo automatico colgando de esos contadores.

        Lo repetido se DESCARTA, no se re-adjudica a la siguiente nota libre: es
        lo mismo que hace `_adjudicar` cuando una pulsacion no alcanza a ninguna
        nota reclamable -no se anota y no cuenta como fallo- y es la unica salida
        honesta desde aqui, porque re-adjudicar exigiria volver a correr la
        adjudicacion entera con el reloj retirado, que es del seguidor y no de
        este metodo.
        """
        cola = self._seguidor.recoger_la_cola()
        if not cola:
            return
        ya_cobrados = {tocada.indice for tocada in self._tocadas_de_la_vuelta}
        nuevas = tuple(t for t in cola if t.indice not in ya_cobrados)
        if not nuevas:
            return
        for numero, fila in self._contar(nuevas).items():
            destino = self._acumulado.setdefault(numero, self._contadores())
            for clave, valor in fila.items():
                destino[clave] += valor
        self._tocadas_de_la_vuelta += nuevas
        self._ultima_vuelta = self._armar_informe(
            self._contar(self._tocadas_de_la_vuelta), {}, 1
        )

    def _ataques_en_vuelo(self) -> bool:
        """Si todavia puede quedar un ataque del final del tramo por resolver.

        Solo esta abierta mientras los avisos llegan CON AUDIO (ver `_al_dia`, que
        es quien pone y quita la marca): `_ultimo_analisis` solo lo mueve
        `procesar`, asi que en cuanto el audio se para la resta se congela y
        preguntarselo daria «si» para siempre. De ahi que el primer aviso sin
        cuadros cierre la ventana, que es lo que la acota.
        """
        marca = self._analisis_al_acabar
        if marca is None or self._ultimo_analisis is None:
            return False
        return self._ultimo_analisis - marca < VENTANA_ATAQUE_COMO_ONSET_S

    def _al_dia(self, avanzando: bool, con_audio: bool = False) -> None:
        """Lo que hay que mirar tras mover el reloj: la cuenta atras y el final.

        La llaman los dos caminos -con audio y sin audio-, porque el bucle tiene
        que dar la vuelta igual cuando el cable esta desenchufado. `con_audio` lo
        pone solo `procesar`, y decide cuando se puede clavar el reloj en el final
        del tramo (ver abajo).

        El bucle solo da la vuelta si el reloj CRUZO el final AVANZANDO
        (`avanzando=True`: `avanzar` y `procesar`). Si el llamador lo COLOCO mas
        alla (`colocar_en`), no hay vuelta ni repeticion: colocar el cabezal es
        una orden sobre donde esta, y convertirla en una vuelta del bucle es
        inventarse una repeticion que el alumno no toco.
        """
        # Una pieza sin compases no tiene tramo que acabar ni que repetir.
        if total_de_compases(self.pieza) == 0:
            return
        if self._cuenta_atras_restante_s > 0:
            return
        if self._seguidor.estado.instante_s < self._fin_s():
            return
        if self._plan.en_bucle:
            if avanzando:
                self._dar_la_vuelta(con_audio=con_audio)
        else:
            # Clavar el reloj en el final del tramo se APLAZA mientras pueda
            # quedar un ataque en vuelo, y esa es la correccion de un defecto
            # medido: aqui se llamaba a `avanzar_a(self._fin_s())` en CADA cuadro
            # -109 recolocaciones en 300 cuadros-, y cada `avanzar_a` invalida la
            # correspondencia entre los dos relojes del seguidor. `_adjudicar`
            # descarta los onsets anteriores al primer cuadro posterior al salto,
            # asi que se perdia hasta `VENTANA_ATAQUE_COMO_ONSET_S` (250 ms) de
            # notas: una nota atacada a 3,95 s de un tramo que acaba en 4,0 salia
            # con `acertadas=0` y `limpias=0`. Y envenenaba lo que cuelga: el
            # ultimo compas de cada pasada salia siempre sin limpias, de modo que
            # `peores_compases` lo nominaba siempre y el tempo automatico no subia
            # nunca por culpa de una nota que si se toco.
            #
            # Es el invariante de `ESPERA_SIN_CUADROS_S` del servidor burlado por
            # DENTRO del nucleo, donde esa constante no llega.
            #
            # Recolocar una sola vez, en la transicion, no basta: el detector firma
            # un onset hasta 250 ms despues de que ocurriera, asi que el ataque del
            # final del tramo se resuelve DESPUES de la transicion y la unica
            # recolocacion ya lo habria descartado (medido). De ahi que no se
            # recoloque ninguna vez hasta que la ventana del detector se cierra:
            # entonces no queda nada por resolver y clavar el reloj vuelve a ser
            # gratis. El precio es que el cabezal se pasa del final del tramo esos
            # 250 ms como mucho, y lo paga quien ya tiene «terminado» en pantalla.
            #
            # Sin audio no hay ventana que esperar y se clava en el acto, que es lo
            # que mantiene el reloj quieto en el final mirada tras mirada.
            #
            # Y NO se arregla acotando el `instante_s` que publica `estado`: toda
            # la etapa esta construida sobre que el servidor ADOPTA el reloj del
            # nucleo, y publicar un instante distinto del que tiene el seguidor
            # romperia esa regla por detras.
            if not self._tramo_terminado:
                self._tramo_terminado = True
                self._analisis_al_acabar = self._ultimo_analisis
            if not con_audio:
                # Un aviso SIN cuadros cierra la ventana, y no solo en la
                # transicion: esta linea es el tope del aplazamiento y sin ella el
                # reloj se escapaba sin limite. `_ultimo_analisis` solo lo mueve
                # `procesar`, asi que si el tramo acaba CON audio y el audio se
                # para en seguida -el alumno termina la pasada y deja de tocar, o
                # desenchufa- la resta de `_ataques_en_vuelo` se congela por
                # debajo de la ventana y decia «si» para siempre: `avanzar`
                # empujaba el cabezal `TECHO_TRAMO_S` por mirada y, con el tramo
                # acabando en 8,0 s, a los 10 s de miradas iba por 17,8 y a los 40
                # s por 47,8. Y aqui no hay nada que aplazar, porque sin cuadros no
                # puede haber ninguna pulsacion en vuelo: es el mismo argumento de
                # `ESPERA_SIN_CUADROS_S`.
                self._analisis_al_acabar = None
            if self._ataques_en_vuelo():
                return
            self._seguidor.avanzar_a(self._fin_s())

    def congelar_en(self, instante_pasada_s: float) -> EstadoEstudio:
        """Coloca el cabezal SIN tocar la cuenta atras. La usa el SERVIDOR.

        Es la hermana de `colocar_en` para el unico caso en que colocar el cabezal
        NO es una orden del usuario: el servidor congelando su espejo del reloj
        tras un hueco de audio o al pausar por falta de senal. Esos dos sitios
        llamaban a `colocar_en`, y `colocar_en` es la puerta que CANCELA la cuenta
        atras: la cuenta que `arrancar()` acababa de abrir moria con el primer
        cuadro de audio -unos 21 ms despues de pulsar «empezar»-, porque
        `_ultimo_cuadro` empieza a None y el primer `_observar` ya pasaba por ahi.
        Lo mismo con cualquier hueco de audio dentro de una cuenta de vuelta.

        Congelar no es desobedecer la cuenta: el servidor esta diciendo «el reloj
        se queda donde esta», que es exactamente lo que la cuenta atras quiere.

        Mueve el reloj y NADA MAS, igual que `colocar_en`: no descobra las notas
        del tramo abandonado.
        """
        with self._candado:
            self._seguidor.avanzar_a(instante_pasada_s)
            self._al_dia(avanzando=False)
            return self.estado

    def colocar_en(self, instante_pasada_s: float) -> EstadoEstudio:
        """Puerta ABSOLUTA: pon el cabezal aqui. CANCELA la cuenta atras.

        Cancelarla es deliberado: colocar el cabezal es una orden sobre donde
        esta ahora, y hacerla esperar a una cuenta atras que ya no viene al caso
        seria desobedecerla a medias. Quien quiere que el tiempo pase respetando
        la pausa y la cuenta usa `avanzar`, y quien solo quiere CONGELAR el reloj
        sin opinar sobre la cuenta usa `congelar_en` (el servidor, tras un hueco
        de audio o al pausar por falta de senal).

        Mueve el reloj y NADA MAS: no descobra las notas del tramo abandonado
        (`olvidar_tramo`), y si se retrocede eso le toca a quien llama.
        """
        with self._candado:
            self._cuenta_atras_restante_s = 0.0
            self._seguidor.avanzar_a(instante_pasada_s)
            self._al_dia(avanzando=False)
            return self.estado

    def avanzar(self, delta_s: float) -> EstadoEstudio:
        """Puerta RELATIVA: ha pasado `delta_s`. Respeta la pausa y la cuenta atras.

        Es la que usa el servidor, con su tramo ya acotado por `TECHO_TRAMO_S`.
        En pausa no pasa nada de nada: el tiempo que no se cuenta no se suma, y
        por eso reanudar no mueve el cabezal ni un milimetro.

        Un delta negativo se acota a 0 en vez de lanzar: el llamador es el
        servidor con un reloj monotono, asi que un negativo es un hueco raro y no
        una orden de retroceder (para eso esta `colocar_en`).
        """
        with self._candado:
            paso = max(0.0, delta_s)
            if self._en_pausa:
                return self.estado
            if self._cuenta_atras_restante_s > 0:
                self._cuenta_atras_restante_s = max(
                    0.0, self._cuenta_atras_restante_s - paso
                )
                # Colocar el reloj del seguidor en el inicio en cada mirada es lo
                # que lo congela, y ademas descarta las pulsaciones en vuelo:
                # durante la cuenta atras no se puede cobrar nada. La abren
                # `_dar_la_vuelta` y `arrancar`, que dejan el reloj en el inicio;
                # esto lo mantiene ahi y descarta lo que llegue en vuelo.
                self._seguidor.avanzar_a(self._inicio_s())
                return self.estado
            self._seguidor.avanzar_a(self._seguidor.estado.instante_s + paso)
            self._al_dia(avanzando=True)
            return self.estado

    def procesar(
        self, resultado: ResultadoAnalisis, instante_analisis: float
    ) -> EstadoEstudio:
        """Camino CON audio: el cuadro mueve el reloj por su correspondencia.

        Aqui NO se llama `avanzar_a` cuando la pasada corre: invalidaria la
        correspondencia entre el reloj de la pieza y el del analisis, y
        `_adjudicar` descarta los onsets anteriores al primer cuadro posterior a
        un salto, asi que ningun ataque se anotaria nunca.
        """
        with self._candado:
            delta = self._delta_del_analisis(instante_analisis)
            if self._en_pausa:
                self._seguidor.avanzar_a(self._seguidor.estado.instante_s)
                return self.estado
            if delta < self._cuenta_atras_restante_s:
                # La cuenta se come el cuadro ENTERO y sigue viva. Igual que en
                # `avanzar`: reloj quieto en el inicio, nada se cobra.
                self._cuenta_atras_restante_s -= delta
                self._seguidor.avanzar_a(self._inicio_s())
                return self.estado
            if self._cuenta_atras_restante_s > 0:
                # **LA CUENTA SE ACABA DENTRO DE ESTE CUADRO, Y LO QUE SOBRA DEL
                # CUADRO YA ES TIEMPO DEL TRAMO: se le entrega al reloj AQUI.** Es
                # la segunda mitad del arrastre que el bucle CON cuenta atras tenia
                # (la primera esta en `_dar_la_vuelta`), y era un cuadro de analisis
                # entero por vuelta -21 ms a la cadencia de produccion-: el cuadro
                # que agotaba la cuenta volvia con el reloj clavado en el inicio y
                # la correspondencia sin fijar, asi que el reloj no empezaba a
                # correr hasta el cuadro SIGUIENTE y se perdia lo que `sobra` mide.
                # Es el mismo cuadro congelado que la T7 le quito a la vuelta del
                # bucle, aqui por el camino de la cuenta.
                #
                # **Y NO HACE FALTA NI UNA PUERTA NUEVA NI TOCAR NINGUN CONTRATO**,
                # que es lo que hace a esta la version barata: el `avanzar_a` es
                # ORDINARIO -sin frontera ni correspondencia- y la correspondencia
                # la escribe el `procesar` de abajo, en este mismo cuadro, desde el
                # reloj que acabamos de dejar (`SeguidorPieza.procesar`: «si
                # `_origen_analisis` es None, se fija con el instante de este
                # cuadro»). El salto ordinario sigue DESCARTANDO lo que estuviera en
                # vuelo y sigue poniendo `_analisis_desde` en este cuadro, que es
                # literalmente «durante la cuenta atras no se cobra nada»: lo
                # atacado antes de que la cuenta se agotara no se anota ni va a la
                # cola.
                sobra = delta - self._cuenta_atras_restante_s
                self._cuenta_atras_restante_s = 0.0
                self._seguidor.avanzar_a(self._inicio_s() + sobra)
            self._seguidor.procesar(resultado, instante_analisis)
            # Cobrar ANTES de `_al_dia`, porque lo que el seguidor acaba de
            # retener es de la vuelta que cerro la vez ANTERIOR: si este mismo
            # cuadro diera OTRA vuelta, `_ultima_vuelta` ya seria la nueva y la
            # cola iria al informe equivocado.
            #
            # Y el orden es gratis, no estructural: para que importe, un mismo
            # cuadro tiene que resolver una nota retenida Y cruzar el final de la
            # vuelta siguiente, o sea que la vuelta entera tiene que durar menos
            # que lo que el detector tarda en firmar un ataque
            # (`VENTANA_ATAQUE_COMO_ONSET_S`, 250 ms). Eso pide un compas de 0,24 s
            # -un 4/4 a 1000 ppm, o un 1/4 a 250- y por eso NO hay prueba que lo
            # cubra: se escribe el orden correcto porque cuesta lo mismo, y se
            # escribe aqui que no esta medido para que nadie lo lea como una carga
            # que lo esta.
            self._cobrar_la_cola()
            self._al_dia(avanzando=True, con_audio=True)
            return self.estado

    def cambiar_plan(self, plan: PlanDePasada) -> EstadoEstudio:
        """Cambia tempo, bucle, click o rango SIN reiniciar la pasada.

        Un factor nuevo obliga a reconstruir el seguidor, porque sus instantes se
        calculan una vez y no cambian nunca. Antes de tirarlo se vuelca lo
        tocado al informe, SIN contarlo como vuelta del bucle: mover el
        deslizador del tempo no es dar una vuelta, y contarlo inflaria el
        denominador de `proporcion_limpia`.

        El cabezal se queda en el MISMO PULSO, no en el mismo segundo: cambiar de
        tempo no mueve a nadie de sitio dentro de la musica.
        """
        with self._candado:
            nuevo = validar_plan(self.pieza, plan)
            pulsos = self._pulsos(self._seguidor.estado.instante_s)
            self.cerrar_repeticion(cuenta_como_vuelta=False)
            cambia_el_factor = nuevo.factor_tempo != self._plan.factor_tempo
            self._plan = nuevo
            if cambia_el_factor:
                self._seguidor = self._nuevo_seguidor()
            self._tramo_terminado = False
            self._analisis_al_acabar = None
            self._cuenta_atras_restante_s = 0.0
            dentro = (
                nuevo.primer_compas <= compas_en(self.pieza, pulsos) <= nuevo.ultimo_compas
            )
            destino = self._segundos(pulsos) if dentro else self._inicio_s()
            return self.colocar_en(destino)

    def saltar_al_compas(self, numero: int) -> EstadoEstudio:
        """Coloca el cabezal al principio del compas `numero` del TRAMO.

        Un compas fuera del tramo se rechaza: el tramo es lo que el usuario
        eligio, y saltar fuera de el es cambiar el plan (`cambiar_plan`), no saltar.

        No borra el informe: lo que ya tocaste sigue contando, pero no como una
        vuelta nueva. Descobra las notas del compas de destino hasta el final del
        tramo, porque si saltas atras a algo que ya tocaste, volver a tocarlo
        tiene que contar. Cancela la cuenta atras, porque la cuenta atras es para
        empezar donde ya estabas.

        El olvido efectivo ya lo hace `cerrar_repeticion` sobre la pieza entera;
        la llamada propia a `olvidar_tramo` esta por CONTRATO (descobrir el tramo
        de destino, y antes de colocar el reloj) y la fijan pruebas con espia. No
        la borres por redundante ni la des por necesaria sin leer esto.
        """
        with self._candado:
            # La guarda del tramo va ANTES de `pulsos_del_compas`: puesta despues,
            # un compas que la pieza no tiene salia con el mensaje de
            # `compases.py` ("la pieza no tiene compas 40") y no con el de este
            # metodo, que es el que nombra los dos extremos del tramo y el que
            # dice que hay que cambiar el plan. Fuera del tramo es fuera del
            # tramo, exista el compas o no.
            if not self._plan.primer_compas <= numero <= self._plan.ultimo_compas:
                raise ValueError(
                    f"El compas {numero} esta fuera del tramo que se estudia, que va "
                    f"del {self._plan.primer_compas} al {self._plan.ultimo_compas}: "
                    "cambia el plan antes de saltar"
                )
            desde, _ = pulsos_del_compas(self.pieza, numero)
            destino = self._segundos(desde)
            self.cerrar_repeticion(cuenta_como_vuelta=False)
            self._tramo_terminado = False
            self._analisis_al_acabar = None
            # Primero se olvida y despues se coloca: colocar acaba en `avanzar_a`,
            # que es quien descarta las pulsaciones en vuelo del tramo abandonado.
            self._seguidor.olvidar_tramo(destino, self._fin_s())
            return self.colocar_en(destino)

    def reiniciar_pasada(self) -> EstadoEstudio:
        """Vuelve al principio del tramo y olvida el informe. Empieza otra pasada."""
        with self._candado:
            self._acumulado = {}
            self._vueltas_cerradas = 0
            # La ultima vuelta es de la pasada que se acaba: dejarla alli metaria
            # una repeticion fantasma en el historial de la pasada nueva.
            self._ultima_vuelta = None
            self._tocadas_de_la_vuelta = ()
            self._repeticion = 1
            self._tramo_terminado = False
            self._analisis_al_acabar = None
            self._seguidor = self._nuevo_seguidor()
            return self.arrancar()

    def arrancar(self) -> EstadoEstudio:
        """Empieza a tocar: coloca el cabezal al principio del tramo y abre la cuenta atras.

        Es la entrada al tramo por primera vez (o de nuevo, en `reiniciar_pasada`):
        la spec pide el compas de aviso ANTES de arrancar y en cada repeticion, y
        la repeticion ya la abre `_dar_la_vuelta`. La duracion es la misma
        (`_segundos_de_cuenta_atras`), cero si el plan dice 0 compases.

        Construir la sesion NO llama a esto: quien solo coloca el reloj y espera
        que la pieza avance (casi todas las pruebas del nucleo) sigue sin cuenta.

        El orden importa: `colocar_en` cancela la cuenta atras, asi que se coloca
        primero y se abre despues. Abrirla antes la dejaria cancelada.
        """
        with self._candado:
            self._ultimo_analisis = None
            self.colocar_en(self._inicio_s())
            self._cuenta_atras_restante_s = self._segundos_de_cuenta_atras()
            return self.estado

    def pausar(self) -> None:
        """Pausa a voluntad del usuario. No es lo mismo que perder la senal.

        **BAJO CANDADO, y no por simetria.** El interruptor es una sola
        asignacion y por tanto atomica, asi que lo que el candado compra no es la
        asignacion: es que la pausa no pueda caer EN MEDIO de un cuadro. Esto lo
        llama el hilo HTTP y `procesar` corre en el del analisis, que lee
        `_en_pausa` al entrar y mueve el reloj despues; sin candado, una pausa que
        se colara entre esas dos cosas volvia con el cabezal todavia por mover y
        el cuadro lo movia DESPUES, o sea que el reloj avanzaba despues de que
        `pausar()` hubiera vuelto. Con el candado, `pausar()` espera a que el
        cuadro en vuelo termine y a partir de que vuelve el reloj esta quieto, que
        es lo que la interfaz promete al pintar el boton.

        El candado es reentrante (ver el docstring de la clase), asi que llamar a
        esto desde dentro de otro metodo que ya lo tenga tomado no se bloquea.
        """
        with self._candado:
            self._en_pausa = True

    def reanudar(self) -> None:
        """Quita la pausa del usuario. BAJO CANDADO, por lo mismo que `pausar`.

        Reanudar no mueve el cabezal ni un milimetro -el tiempo que no se conto no
        se suma, ver `avanzar`-, asi que lo que el candado ordena aqui es la otra
        mitad: que el primer cuadro que vuelva a contar sea entero y no uno que ya
        estaba a medio camino de descartarse por la pausa.
        """
        with self._candado:
            self._en_pausa = False

    # -- el informe --------------------------------------------------------

    def _compases_del_tramo(self) -> tuple[int, ...]:
        # Tras `validar_plan`, `ultimo_compas` es siempre un entero y vale 0 solo
        # en la pieza sin compases, que no tiene nada que informar.
        if total_de_compases(self.pieza) == 0:
            return ()
        return tuple(range(self._plan.primer_compas, self._plan.ultimo_compas + 1))

    def _indices_por_compas(self) -> dict[int, list[int]]:
        """Que notas de la pieza caen en cada compas, por indice."""
        reparto: dict[int, list[int]] = {}
        for indice, nota in enumerate(self.pieza.notas):
            reparto.setdefault(compas_en(self.pieza, nota.inicio_pulsos), []).append(indice)
        return reparto

    @staticmethod
    def _contadores() -> dict:
        return {"acertadas": 0, "a_tiempo": 0, "pronto": 0, "tarde": 0, "limpias": 0,
                "suma_desfase": 0.0, "con_desfase": 0}

    def _contar(self, tocadas) -> dict[int, dict]:
        """Reparte por compas una lista de `NotaTocada`."""
        de_cada_indice = self._compas_de_cada_nota
        cuenta: dict[int, dict] = {}
        for tocada in tocadas:
            numero = de_cada_indice.get(tocada.indice)
            if numero is None:
                continue
            fila = cuenta.setdefault(numero, self._contadores())
            if tocada.acertada:
                fila["acertadas"] += 1
            # Con guarda: una clasificacion nueva en el seguidor no debe romper
            # la ruta que publica el estado varias veces por segundo.
            if tocada.clasificacion in ("a_tiempo", "pronto", "tarde"):
                fila[tocada.clasificacion] += 1
            if tocada.acertada and tocada.clasificacion == "a_tiempo":
                fila["limpias"] += 1
            if tocada.desfase_s is not None:
                fila["suma_desfase"] += tocada.desfase_s
                fila["con_desfase"] += 1
        return cuenta

    def _armar_informe(
        self, cuenta: dict[int, dict], acumulado: dict[int, dict], repeticiones: int
    ) -> InformeDePasada:
        """Monta un informe sumando dos cuentas por compas. Sin efectos."""
        reparto = self._reparto
        filas = []
        for numero in self._compases_del_tramo():
            indices = reparto.get(numero, [])
            escritas = len(indices)
            medibles = len({self.pieza.notas[i].inicio_pulsos for i in indices})
            suma = acumulado.get(numero, self._contadores())
            ahora = cuenta.get(numero, self._contadores())
            con_desfase = suma["con_desfase"] + ahora["con_desfase"]
            total_desfase = suma["suma_desfase"] + ahora["suma_desfase"]
            filas.append(
                CompasDelInforme(
                    numero=numero,
                    notas_escritas=escritas,
                    notas_medibles=medibles,
                    acertadas=suma["acertadas"] + ahora["acertadas"],
                    a_tiempo=suma["a_tiempo"] + ahora["a_tiempo"],
                    pronto=suma["pronto"] + ahora["pronto"],
                    tarde=suma["tarde"] + ahora["tarde"],
                    limpias=suma["limpias"] + ahora["limpias"],
                    desfase_medio_s=(
                        None if con_desfase == 0 else total_desfase / con_desfase
                    ),
                    tiene_acordes=medibles < escritas,
                )
            )
        return InformeDePasada(
            compases=tuple(filas),
            ritmo_aproximado=self.pieza.ritmo_aproximado,
            compas_variable=self.pieza.compas_variable,
            factor_tempo=self._plan.factor_tempo,
            repeticiones=repeticiones,
        )

    @property
    def informe(self) -> InformeDePasada:
        """El informe de la PASADA al dia: lo acumulado mas lo que el seguidor lleva.

        Acumula todas las repeticiones del bucle: es lo que la interfaz muestra
        como "esta pasada". Lo de UNA repeticion lo devuelve `cerrar_repeticion`.
        """
        en_vuelo = self._contar(self._seguidor.estado.tocadas)
        return self._armar_informe(
            en_vuelo, self._acumulado, self._vueltas_cerradas + 1
        )

    def cerrar_repeticion(self, cuenta_como_vuelta: bool = True) -> InformeDePasada:
        """Vuelca lo que el seguidor lleva anotado al acumulador y lo deja limpio.

        **Devuelve el informe de SOLO esa repeticion**, sin lo acumulado, y eso es
        lo que la Tarea 7 anota en el historial: estudiando un bucle, la pregunta
        "ya te sale?" es sobre la vuelta que acaba de pasar, no sobre la suma de
        las ocho anteriores. El informe acumulado sigue disponible en `informe`.

        Se llama al dar la vuelta el bucle y antes de reconstruir el seguidor por
        un cambio de tempo o un salto: en todos los casos las `NotaTocada` del
        seguidor estan a punto de desaparecer, y sin este volcado el informe
        perderia lo tocado.

        `cuenta_como_vuelta=False` vuelca igual pero no suma una vuelta: es lo que
        usan `cambiar_plan` y `saltar_al_compas`, que no son una vuelta del
        bucle. Contarlas inflaria `repeticiones` y hundiria `proporcion_limpia`
        cada vez que el usuario moviera el deslizador del tempo.

        Y lo usa un tercero, que es el que delato el defecto: `ConductorDeEstudio`
        al cerrar un tramo **sin bucle**. Esa pasada tiene UNA vuelta, la que el
        `+1` de `informe` ya cuenta; sumarle otra dejaba `repeticiones=2` con el
        seguidor ya vacio, o sea el denominador doblado y el numerador quieto:
        ocho notas limpias de ocho salian 0,5.

        Vaciar el seguidor despues es lo que impide contar dos veces: el informe
        suma lo acumulado MAS lo que el seguidor tenga.

        `olvidar_tramo` hace ademas otra cosa que conviene tener presente: deja
        la pieza entera RECOBRABLE (pone `_cobradas` a False). Y el `avanzar_a`
        que el contrato de `olvidar_tramo` pide a continuacion le toca a quien
        repite el tramo, no a este metodo.
        """
        with self._candado:
            cuenta = self._contar(self._seguidor.estado.tocadas)
            solo_esta_vuelta = self._armar_informe(cuenta, {}, 1)
            if cuenta_como_vuelta:
                self._vueltas_cerradas += 1
            for numero, fila in cuenta.items():
                destino = self._acumulado.setdefault(numero, self._contadores())
                for clave, valor in fila.items():
                    # `+=` sobre un dict compartido no es atomico: sin el candado
                    # de la clase, dos hilos podian leer el mismo valor y escribir
                    # el mismo resultado, perdiendo una de las dos sumas.
                    destino[clave] += valor
            self._seguidor.olvidar_tramo(0.0, self._seguidor.duracion_s + 1.0)
            return solo_esta_vuelta


# La frontera para subir y la para bajar, separadas a proposito: con una sola,
# una pasada al 89 % bajaria el tempo que la del 90 % acababa de subir, y el
# tempo oscilaria sin que el alumno mejorara ni empeorara.
UMBRAL_PARA_SUBIR = 0.90
UMBRAL_PARA_BAJAR = 0.70
PASADAS_BUENAS_PARA_SUBIR = 2


class HistorialDeEstudio:
    """Las pasadas de esta sesion. En memoria: al apagar el servidor se olvida.

    Es la decision del usuario, y el precio esta medido: no hay formato de
    archivo que versionar, ni escritura atomica, ni una sola prueba que toque el
    disco. El dia que se quiera recordar entre dias, esta clase es el unico sitio
    que cambia.
    """

    def __init__(self) -> None:
        self._pasadas: list[InformeDePasada] = []
        # Proporciones desde la ultima vez que se decidio mover el tempo. Se
        # vacia al decidir, y por eso `factor_sugerido` no sube dos veces con la
        # misma racha.
        self._racha: list[float] = []

    def anotar(self, informe: InformeDePasada) -> None:
        self._pasadas.append(informe)
        proporcion = proporcion_limpia(informe)
        if proporcion is not None:
            self._racha.append(proporcion)

    @property
    def pasadas(self) -> int:
        return len(self._pasadas)

    def peores_compases(self, cuantos: int = 3) -> tuple[tuple[int, int, int], ...]:
        """(compas, pasadas falladas, pasadas contadas), el peor primero.

        Un compas esta "fallado" en una pasada si no todas sus notas medibles
        salieron limpias (acertadas Y a tiempo): un compas bien tocado pero tarde
        tambien merece machacarse. Los compases con acordes NO entran: ahi solo
        se puede medir una nota de cada acorde, asi que saldrian fallados siempre
        y el boton de machacar mandaria al usuario justo a los compases que nunca
        podra pasar.

        **LAS NOTAS MEDIBLES SE MULTIPLICAN POR LAS REPETICIONES DEL INFORME**, y
        por lo mismo que en `proporcion_limpia`: `limpias` acumula TODAS las
        vueltas que el informe lleva dentro y `notas_medibles` es lo que hay
        escrito en el compas, que no se repite. Sin multiplicar, un informe de
        cuatro vueltas con un compas de cuatro notas daba el compas por bueno con
        **cuatro limpias de las dieciseis** que se tocaron -tres vueltas enteras
        falladas-, y el boton de machacar no lo nominaba nunca. Era el defecto 4
        del §8.
        """
        fallos: dict[int, list[int]] = {}
        for informe in self._pasadas:
            vueltas = max(1, informe.repeticiones)
            for compas in informe.compases:
                if compas.tiene_acordes:
                    continue
                marca = fallos.setdefault(compas.numero, [0, 0])
                marca[1] += 1
                if compas.limpias < compas.notas_medibles * vueltas:
                    marca[0] += 1
        ordenados = sorted(
            ((numero, fallo, contadas) for numero, (fallo, contadas) in fallos.items()),
            key=lambda fila: (-fila[1], -fila[1] / fila[2], fila[0]),
        )
        return tuple(fila for fila in ordenados[:cuantos] if fila[1] > 0)

    def factor_sugerido(self, factor_actual: float) -> float:
        """Que factor deberia tener la proxima pasada. CONSUME la racha al decidir.

        Dos pasadas seguidas por encima de `UMBRAL_PARA_SUBIR` suben un paso; una
        sola por debajo de `UMBRAL_PARA_BAJAR` baja un paso, sin esperar a la
        segunda, porque quien falla mucho no necesita confirmacion. Las pasadas
        sin proporcion medible -una pieza entera de acordes- no cuentan para
        ninguna de las dos cosas.
        """
        if not self._racha:
            return factor_actual
        if self._racha[-1] < UMBRAL_PARA_BAJAR:
            self._racha = []
            return max(FACTOR_MINIMO, round(factor_actual - PASO_DEL_FACTOR, 2))
        ultimas = self._racha[-PASADAS_BUENAS_PARA_SUBIR:]
        if (
            len(ultimas) == PASADAS_BUENAS_PARA_SUBIR
            and all(p >= UMBRAL_PARA_SUBIR for p in ultimas)
        ):
            self._racha = []
            return min(FACTOR_MAXIMO, round(factor_actual + PASO_DEL_FACTOR, 2))
        return factor_actual

    def a_dict(self) -> dict:
        return {
            "pasadas": self.pasadas,
            "peores_compases": [
                {"compas": c, "falladas": f, "contadas": t}
                for c, f, t in self.peores_compases()
            ],
        }
