"""Que nota se toco y cuando: la deteccion de pulsaciones, sin saber de ejercicios.

Consume el mismo flujo de ResultadoAnalisis que alimenta al afinador. Como
ResultadoAnalisis es un dato, toda esta logica se prueba escribiendo la secuencia
exacta que produciria alguien tocando, sin audio y sin hardware.

Una pulsacion (una lectura que cuenta como intento de tocar algo) puede
dispararse por dos caminos independientes, resueltos a lo sumo uno por cuadro:

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

from dataclasses import dataclass

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.ataques import ESPERA_ESTABILIZACION_S, DetectorAtaques

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
# del detector, sino de quien lo alimenta (el pipeline de audio); quien
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
class Pulsacion:
    """Una nota que el alumno toco, con cuando empezo y como de afinada iba.

    `instante` es el onset que se anota en el informe: el instante del ataque de
    energia siempre que hubo uno, o el comienzo de la racha estable cuando no lo
    hubo (ver `DetectorPulsaciones._onset_camino_b`). Puede ser None en el caso
    raro en que el camino A resuelve con el ataque ya gastado por un descarte
    previo; `IntentoNota.instante` admite None por lo mismo, y `regularidad_ms`
    ignora esos instantes.
    """

    nota: str
    cents: float | None
    instante: float | None


class DetectorPulsaciones:
    """Que nota se toco y cuando, sin saber nada de ejercicios ni de piezas.

    Es la mitad de abajo del evaluador de ejercicios, extraida para que el carril
    la use sin duplicarla. La mitad de arriba -comparar con lo que tocaba,
    contar intentos, ayudar- se queda en quien la use, porque no es la misma en
    los dos modos: en un ejercicio la nota espera a que la aciertes y en una
    pieza la musica sigue.

    Los dos caminos de disparo (el ataque de energia y el cambio estable de
    nota) y el filtro que comparten estan explicados en el docstring del modulo.

    Limitacion conocida: dos pulsaciones seguidas de la MISMA nota no se
    distinguen si entre ellas no hay un hueco de `cuadros_para_olvidar_nota`
    cuadros (unos 63 ms al intervalo de analisis habitual) SEGUIDOS sin ninguna
    nota creible. El nivel no interviene: el filtro compara NOMBRES DE NOTA, no
    niveles, asi que por muy marcada que sea la caida de volumen entre las dos
    pulsaciones el camino A queda filtrado igual, y el camino B no ve ninguna
    altura nueva. Ojo con el detalle: no basta con que deje de darse ESA nota,
    porque cualquier otra lectura creible reinicia el contador del hueco; con una
    nota de guitarra que sigue sonando, eso puede no llegar nunca. Quien use el
    detector decide como salir de ese atasco (el evaluador de ejercicios lo hace
    con su disparador de ayuda por tiempo).

    No lleva candado propio: no lo necesita, porque quien lo usa desde varios
    hilos ya lo protege (ver `EvaluadorEjercicio._candado`).
    """

    def __init__(
        self,
        detector_ataques: DetectorAtaques | None = None,
        confianza_minima: float = CONFIANZA_MINIMA,
        espera_estabilizacion_s: float = ESPERA_ESTABILIZACION_S,
        cuadros_para_nota_estable: int = CUADROS_PARA_NOTA_ESTABLE,
        cuadros_para_olvidar_nota: int = CUADROS_PARA_OLVIDAR_NOTA,
    ) -> None:
        self._detector = detector_ataques or DetectorAtaques()
        self.confianza_minima = confianza_minima
        self.espera_estabilizacion_s = espera_estabilizacion_s
        self.cuadros_para_nota_estable = cuadros_para_nota_estable
        self.cuadros_para_olvidar_nota = cuadros_para_olvidar_nota
        self.reiniciar()

    def reiniciar(self) -> None:
        """Olvida todo lo oido. Se llama al empezar un ejercicio o una pieza."""
        self._detector.reiniciar()
        # Camino A: cuando toca leer la nota del ataque, y el instante del ataque
        # que origino esa lectura diferida.
        self._lectura_pendiente: float | None = None
        self._instante_ataque: float | None = None
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
        self._senal_de_nota_nueva = False

    @property
    def senal_de_nota_nueva(self) -> bool:
        """Si el ultimo cuadro traia senal que podria ser una pulsacion nueva.

        Es decir: nota creible que NO es `_ultima_nota_resuelta`. Un cuadro
        creible cuya nota es la ultima ya resuelta es la cola de esa pulsacion,
        que se conto y sigue sonando: no es que el alumno este intentando nada.
        Esa distincion la necesita quien decide si el alumno esta tocando de
        verdad (ver la regla de la ayuda por tiempo en `EvaluadorEjercicio`):
        tomar cualquier cuadro creible por senal nueva hacia que la cola
        rearmara la bandera justo despues de cada nota resuelta, y entonces una
        pausa para pensar -o el cable desenchufado- regalaba la ayuda sin haber
        tocado nada.
        """
        return self._senal_de_nota_nueva

    def procesar(self, resultado: ResultadoAnalisis, instante: float) -> Pulsacion | None:
        """Devuelve la pulsacion detectada en este cuadro, o None.

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
        """
        self._senal_de_nota_nueva = False

        if self._es_creible(resultado):
            self._cuadros_sin_nota_creible = 0
            # `senal_de_nota_nueva` solo se arma con senal que PODRIA ser una
            # pulsacion nueva: un cuadro creible cuya nota es
            # `_ultima_nota_resuelta` es la cola de la anterior (ver la
            # propiedad). Se calcula ANTES de resolver, contra la nota resuelta
            # con la que empezo el cuadro.
            if resultado.nota != self._ultima_nota_resuelta:
                self._senal_de_nota_nueva = True
        else:
            self._cuadros_sin_nota_creible += 1
            if self._cuadros_sin_nota_creible >= self.cuadros_para_olvidar_nota:
                self._ultima_nota_resuelta = None

        ataque = self._detector.procesar(resultado.nivel_db, instante)
        if ataque is not None:
            self._lectura_pendiente = ataque.instante + self.espera_estabilizacion_s
            self._instante_ataque = ataque.instante

        pulsacion: Pulsacion | None = None

        if self._lectura_pendiente is not None and instante >= self._lectura_pendiente:
            self._lectura_pendiente = None
            pulsacion = self._sellar(resultado, self._instante_ataque)
            if pulsacion is not None:
                # Este ataque ya se leyo: el camino B empieza a contar de nuevo
                # para no repetir el mismo evento con la nota que sigue sonando.
                self._nota_candidata = None
                self._contador_candidata = 0
                self._instante_inicio_candidata = None

        if pulsacion is None:
            nota_estable = self._actualizar_candidata(resultado, instante)
            if nota_estable is not None:
                pulsacion = self._sellar(resultado, self._onset_camino_b(instante))
                if pulsacion is not None:
                    # Esta nota ya se resolvio por el camino B: si habia una
                    # lectura pendiente del camino A para el mismo sonido, se
                    # cancela para no contarla otra vez cuando le toque su turno.
                    self._lectura_pendiente = None

        return pulsacion

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
        filtro es responsabilidad de `_sellar`, el mismo para los dos caminos.
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

    def _sellar(
        self, resultado: ResultadoAnalisis, instante_evento: float | None
    ) -> Pulsacion | None:
        """Convierte en pulsacion la nota que suena al disparar un evento, o la descarta.

        `instante_evento` es el onset que se anota (el ataque de energia, o lo
        que devuelva `_onset_camino_b`).

        Devuelve None si el evento se descarta: sin nota creible (un golpe en la
        caja o una cuerda apagada no es un intento), o porque la nota leida es la
        misma que la ultima ya resuelta, en cuyo caso no hubo forma de distinguir
        esta lectura de la que la origino.
        """
        # Sin nota creible no hubo intento.
        if not self._es_creible(resultado):
            return None

        # Misma nota que la ultima ya resuelta: sin un cuadro sin nota creible
        # de por medio, no hay forma de saber si es una pulsacion nueva o el
        # mismo sonido que ya se conto (un segundo pico de energia sobre la
        # nota aceptada, o el resto de la racha que el camino B ya resolvio).
        if resultado.nota == self._ultima_nota_resuelta:
            # Este ataque pertenece a una pulsacion que ya se conto (un hinchado,
            # un vibrato o un roce sobre la nota aceptada). Si se quedara puesto,
            # `_onset_camino_b` lo firmaria como onset de la pulsacion SIGUIENTE
            # y falsearia `regularidad_ms` hasta en VENTANA_ATAQUE_COMO_ONSET_S.
            # Ojo: esto NO vale para el descarte por falta de nota creible de
            # arriba, donde el ataque es real y su lectura solo llego antes de
            # tiempo.
            self._instante_ataque = None
            return None

        self._ultima_nota_resuelta = resultado.nota
        # El ataque que origino este evento ya se gasto: dejarlo puesto haria
        # que `_onset_camino_b` lo firmara como onset de la pulsacion siguiente.
        self._instante_ataque = None

        return Pulsacion(
            nota=resultado.nota,
            cents=resultado.cents,
            instante=instante_evento,
        )
