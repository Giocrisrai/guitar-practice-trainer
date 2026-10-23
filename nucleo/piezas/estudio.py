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
    """

    numero: int
    notas_escritas: int
    notas_medibles: int
    acertadas: int
    a_tiempo: int
    pronto: int
    tarde: int
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
            "desfase_medio_s": (
                None if self.desfase_medio_s is None else round(self.desfase_medio_s, 3)
            ),
            "tiene_acordes": self.tiene_acordes,
        }


@dataclass(frozen=True)
class InformeDePasada:
    """El informe del tramo que se esta estudiando, compas a compas."""

    compases: tuple[CompasDelInforme, ...]
    ritmo_aproximado: bool
    compas_variable: bool
    factor_tempo: float

    def a_dict(self) -> dict:
        return {
            "compases": [c.a_dict() for c in self.compases],
            "ritmo_aproximado": self.ritmo_aproximado,
            "compas_variable": self.compas_variable,
            "factor_tempo": self.factor_tempo,
        }


def proporcion_limpia(informe: InformeDePasada) -> float | None:
    """Que fraccion de las notas medibles se acerto Y a tiempo, 0 a 1.

    Los compases con acordes quedan FUERA, y es la decision que hace que la regla
    del tempo sirva: contandolos, cualquier cancion de Guitar Pro bajaria el tempo
    para siempre. Devuelve None cuando no hay ni una nota medible sin acordes -una
    pieza entera de acordes-, y quien lea esto tiene que distinguir None de 0,0:
    uno es "no se puede medir" y el otro es "lo fallaste todo".
    """
    medibles = sum(c.notas_medibles for c in informe.compases if not c.tiene_acordes)
    if medibles == 0:
        return None
    buenas = sum(
        min(c.acertadas, c.a_tiempo) for c in informe.compases if not c.tiene_acordes
    )
    return buenas / medibles


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
        )

    def colocar_en(self, instante_pasada_s: float) -> EstadoEstudio:
        """Pone el cabezal en ese instante de la pasada. No consume audio.

        Es la puerta ABSOLUTA del reloj. La relativa es `avanzar`, y la
        diferencia importa: con una sola puerta absoluta, el llamador sigue
        contando tiempo durante la pausa y al reanudar el cabezal saltaria el
        tamano de la pausa.

        Mueve el reloj y NADA MAS: no descobra las notas del tramo abandonado
        (`olvidar_tramo`), y si se retrocede eso le toca a quien llama.
        """
        self._seguidor.avanzar_a(instante_pasada_s)
        return self.estado

    def avanzar(self, delta_s: float) -> EstadoEstudio:
        """Ha pasado `delta_s` de tiempo. Puerta RELATIVA del reloj.

        Por ahora solo suma; la pausa y la cuenta atras entran despues, que es
        donde existen.
        """
        # Un delta negativo se acota a 0 en vez de lanzar: el llamador es el
        # servidor con un reloj monotono, asi que un negativo es un hueco raro
        # y no una orden de retroceder (para eso esta `colocar_en`).
        self._seguidor.avanzar_a(self._seguidor.estado.instante_s + max(0.0, delta_s))
        return self.estado

    def procesar(
        self, resultado: ResultadoAnalisis, instante_analisis: float
    ) -> EstadoEstudio:
        """Consume un cuadro de analisis."""
        self._seguidor.procesar(resultado, instante_analisis)
        return self.estado

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
        return {"acertadas": 0, "a_tiempo": 0, "pronto": 0, "tarde": 0,
                "suma_desfase": 0.0, "con_desfase": 0}

    def _contar(self, tocadas, reparto: dict[int, list[int]]) -> dict[int, dict]:
        """Reparte por compas una lista de `NotaTocada`."""
        de_cada_indice = {
            indice: numero for numero, indices in reparto.items() for indice in indices
        }
        cuenta: dict[int, dict] = {}
        for tocada in tocadas:
            numero = de_cada_indice.get(tocada.indice)
            if numero is None:
                continue
            fila = cuenta.setdefault(numero, self._contadores())
            if tocada.acertada:
                fila["acertadas"] += 1
            if tocada.clasificacion is not None:
                fila[tocada.clasificacion] += 1
            if tocada.desfase_s is not None:
                fila["suma_desfase"] += tocada.desfase_s
                fila["con_desfase"] += 1
        return cuenta

    def _armar_informe(
        self, reparto: dict[int, list[int]], cuenta: dict[int, dict], acumulado: dict[int, dict]
    ) -> InformeDePasada:
        """Monta un informe sumando dos cuentas por compas. Sin efectos."""
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
        )

    @property
    def informe(self) -> InformeDePasada:
        """El informe de la PASADA al dia: lo acumulado mas lo que el seguidor lleva.

        Acumula todas las repeticiones del bucle: es lo que la interfaz muestra
        como "esta pasada". Lo de UNA repeticion lo devuelve `cerrar_repeticion`.
        """
        reparto = self._indices_por_compas()
        en_vuelo = self._contar(self._seguidor.estado.tocadas, reparto)
        return self._armar_informe(reparto, en_vuelo, self._acumulado)

    def cerrar_repeticion(self) -> InformeDePasada:
        """Vuelca lo que el seguidor lleva anotado al acumulador y lo deja limpio.

        **Devuelve el informe de SOLO esa repeticion**, sin lo acumulado, y eso es
        lo que la Tarea 7 anota en el historial: estudiando un bucle, la pregunta
        "ya te sale?" es sobre la vuelta que acaba de pasar, no sobre la suma de
        las ocho anteriores. El informe acumulado sigue disponible en `informe`.

        Se llama al dar la vuelta el bucle y antes de reconstruir el seguidor por
        un cambio de tempo: en los dos casos las `NotaTocada` del seguidor estan a
        punto de desaparecer, y sin este volcado el informe perderia la
        repeticion entera.

        Vaciar el seguidor despues es lo que impide contar dos veces: el informe
        suma lo acumulado MAS lo que el seguidor tenga.
        """
        reparto = self._indices_por_compas()
        cuenta = self._contar(self._seguidor.estado.tocadas, reparto)
        solo_esta_vuelta = self._armar_informe(reparto, cuenta, {})
        for numero, fila in cuenta.items():
            destino = self._acumulado.setdefault(numero, self._contadores())
            for clave, valor in fila.items():
                destino[clave] += valor
        self._seguidor.olvidar_tramo(0.0, self._seguidor.duracion_s + 1.0)
        return solo_esta_vuelta
