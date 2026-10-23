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

from dataclasses import dataclass, replace

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones
from nucleo.piezas.compases import (
    compas_en,
    pulsos_del_compas,
    pulsos_por_compas,
    total_de_compases,
)
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos, segundos_a_pulsos
from nucleo.piezas.seguimiento import EstadoCarril, SeguidorPieza

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
    """Un seguidor, un plan, y el informe de lo que va pasando."""

    def __init__(
        self,
        pieza: Pieza,
        plan: PlanDePasada = PlanDePasada(),
        detector: DetectorPulsaciones | None = None,
    ) -> None:
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
        # El informe de la ultima vuelta del bucle que se cerro, o None si
        # todavia no se cerro ninguna. Lo lee el servidor para el historial.
        self._ultima_vuelta: InformeDePasada | None = None
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

    def _pulsos(self, segundos_de_pasada: float) -> float:
        return segundos_a_pulsos(
            segundos_de_pasada * self._plan.factor_tempo, self.pieza.tempo
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
            en_pausa=self._en_pausa,
            compas_variable=self.pieza.compas_variable,
            ritmo_aproximado=self.pieza.ritmo_aproximado,
            tramo_terminado=self._tramo_terminado,
        )

    @property
    def ultima_vuelta(self) -> InformeDePasada | None:
        """El informe de la ultima vuelta del bucle cerrada, o None si no hubo."""
        return self._ultima_vuelta

    def _segundos_de_cuenta_atras(self) -> float:
        if self._plan.compases_de_cuenta_atras == 0:
            return 0.0
        return self._segundos(
            pulsos_por_compas(self.pieza) * self._plan.compases_de_cuenta_atras
        )

    def _delta_del_analisis(self, instante_analisis: float) -> float:
        """Cuanto tiempo paso entre dos cuadros, nunca negativo.

        Solo lo necesita la cuenta atras: el reloj de la pieza lo mueve
        `procesar` del seguidor por su correspondencia, no esta resta.
        """
        anterior = self._ultimo_analisis
        self._ultimo_analisis = instante_analisis
        if anterior is None:
            return 0.0
        return max(0.0, instante_analisis - anterior)

    def _dar_la_vuelta(self) -> None:
        """Los cuatro pasos del bucle, en este orden y no en otro.

        El informe de la vuelta que acaba se guarda en `_ultima_vuelta`, porque
        quien lo necesita -el historial- se entera de la vuelta mirando
        `repeticion` DESPUES de que esto haya pasado, y entonces ya no podria
        pedirlo.
        """
        self._ultima_vuelta = self.cerrar_repeticion()
        inicio, fin = self._inicio_s(), self._fin_s()
        self._seguidor.olvidar_tramo(inicio, fin)
        self._seguidor.avanzar_a(inicio)
        self._repeticion += 1
        self._cuenta_atras_restante_s = self._segundos_de_cuenta_atras()

    def _al_dia(self, avanzando: bool) -> None:
        """Lo que hay que mirar tras mover el reloj: la cuenta atras y el final.

        La llaman los dos caminos -con audio y sin audio-, porque el bucle tiene
        que dar la vuelta igual cuando el cable esta desenchufado.

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
                self._dar_la_vuelta()
        else:
            self._tramo_terminado = True
            self._seguidor.avanzar_a(self._fin_s())

    def colocar_en(self, instante_pasada_s: float) -> EstadoEstudio:
        """Puerta ABSOLUTA: pon el cabezal aqui. CANCELA la cuenta atras.

        Cancelarla es deliberado: colocar el cabezal es una orden sobre donde
        esta ahora, y hacerla esperar a una cuenta atras que ya no viene al caso
        seria desobedecerla a medias. Quien quiere que el tiempo pase respetando
        la pausa y la cuenta usa `avanzar`.

        Mueve el reloj y NADA MAS: no descobra las notas del tramo abandonado
        (`olvidar_tramo`), y si se retrocede eso le toca a quien llama.
        """
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
        paso = max(0.0, delta_s)
        if self._en_pausa:
            return self.estado
        if self._cuenta_atras_restante_s > 0:
            self._cuenta_atras_restante_s = max(0.0, self._cuenta_atras_restante_s - paso)
            # Colocar el reloj del seguidor en el inicio en cada mirada es lo que
            # lo congela, y ademas descarta las pulsaciones en vuelo: durante la
            # cuenta atras no se puede cobrar nada. HOY es defensa: `_dar_la_vuelta`
            # ya dejo el reloj en el inicio y nadie mas abre la cuenta atras. Se
            # queda para que el reloj siga quieto si alguien la abre por otro lado.
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
        delta = self._delta_del_analisis(instante_analisis)
        if self._en_pausa:
            self._seguidor.avanzar_a(self._seguidor.estado.instante_s)
            return self.estado
        if self._cuenta_atras_restante_s > 0:
            self._cuenta_atras_restante_s = max(0.0, self._cuenta_atras_restante_s - delta)
            # Defensa, igual que en `avanzar`: hoy el reloj ya esta en el inicio.
            self._seguidor.avanzar_a(self._inicio_s())
            return self.estado
        self._seguidor.procesar(resultado, instante_analisis)
        self._al_dia(avanzando=True)
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
        nuevo = validar_plan(self.pieza, plan)
        pulsos = self._pulsos(self._seguidor.estado.instante_s)
        self.cerrar_repeticion(cuenta_como_vuelta=False)
        cambia_el_factor = nuevo.factor_tempo != self._plan.factor_tempo
        self._plan = nuevo
        if cambia_el_factor:
            self._seguidor = self._nuevo_seguidor()
        self._tramo_terminado = False
        self._cuenta_atras_restante_s = 0.0
        dentro = nuevo.primer_compas <= compas_en(self.pieza, pulsos) <= nuevo.ultimo_compas
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
        desde, _ = pulsos_del_compas(self.pieza, numero)
        if not self._plan.primer_compas <= numero <= self._plan.ultimo_compas:
            raise ValueError(
                f"El compas {numero} esta fuera del tramo que se estudia, que va "
                f"del {self._plan.primer_compas} al {self._plan.ultimo_compas}: "
                "cambia el plan antes de saltar"
            )
        destino = self._segundos(desde)
        self.cerrar_repeticion(cuenta_como_vuelta=False)
        self._tramo_terminado = False
        # Primero se olvida y despues se coloca: colocar acaba en `avanzar_a`, que
        # es quien descarta las pulsaciones en vuelo del tramo abandonado.
        self._seguidor.olvidar_tramo(destino, self._fin_s())
        return self.colocar_en(destino)

    def reiniciar_pasada(self) -> EstadoEstudio:
        """Vuelve al principio del tramo y olvida el informe. Empieza otra pasada."""
        self._acumulado = {}
        self._vueltas_cerradas = 0
        # La ultima vuelta es de la pasada que se acaba: dejarla alli metaria una
        # repeticion fantasma en el historial de la pasada nueva.
        self._ultima_vuelta = None
        self._repeticion = 1
        self._tramo_terminado = False
        self._cuenta_atras_restante_s = 0.0
        self._seguidor = self._nuevo_seguidor()
        self._ultimo_analisis = None
        return self.colocar_en(self._inicio_s())

    def pausar(self) -> None:
        """Pausa a voluntad del usuario. No es lo mismo que perder la senal."""
        self._en_pausa = True

    def reanudar(self) -> None:
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

        Vaciar el seguidor despues es lo que impide contar dos veces: el informe
        suma lo acumulado MAS lo que el seguidor tenga.

        `olvidar_tramo` hace ademas otra cosa que conviene tener presente: deja
        la pieza entera RECOBRABLE (pone `_cobradas` a False). Y el `avanzar_a`
        que el contrato de `olvidar_tramo` pide a continuacion le toca a quien
        repite el tramo, no a este metodo.
        """
        cuenta = self._contar(self._seguidor.estado.tocadas)
        solo_esta_vuelta = self._armar_informe(cuenta, {}, 1)
        if cuenta_como_vuelta:
            self._vueltas_cerradas += 1
        for numero, fila in cuenta.items():
            destino = self._acumulado.setdefault(numero, self._contadores())
            for clave, valor in fila.items():
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
        tambien merece machacarse. Los compases con acordes NO entran: ahi solo se puede medir una
        nota de cada acorde, asi que saldrian fallados siempre y el boton de
        machacar mandaria al usuario justo a los compases que nunca podra pasar.
        """
        fallos: dict[int, list[int]] = {}
        for informe in self._pasadas:
            for compas in informe.compases:
                if compas.tiene_acordes or compas.notas_medibles == 0:
                    continue
                marca = fallos.setdefault(compas.numero, [0, 0])
                marca[1] += 1
                if compas.limpias < compas.notas_medibles:
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
