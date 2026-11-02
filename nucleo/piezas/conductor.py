"""El conductor del estudio: quien mueve el reloj de la pasada y cierra las vueltas.

Esta clase es la POLITICA del estudio, y vivia en `SesionCarril`
(`servidor/piezas.py`) hasta la etapa 3d. Lo que decide: cuanto tiempo entra en la
pieza por cada aviso, cuando se le congela el reloj al estudio, cuando se puede
mover a mano sin costarle pulsaciones al seguidor, que se anota en el historial al
cerrarse una vuelta y cuando se mueve el tempo automatico.

POR QUE ESTA AQUI Y NO EN EL SERVIDOR. El gemelo digital (`nucleo/gemelo/`) mete
audio por la ruta real del cable para poder verificar la cadena entera sin
guitarra, y `nucleo/` no importa de `servidor/`. Con la politica dentro de
`SesionCarril`, el gemelo tendria que reimplementarla para poder conducirla, y
entonces estaria verificando una copia paralela en vez del codigo de verdad: se
daria la razon a si mismo. Extraerla es lo que hace que el gemelo conduzca ESTE
codigo, el mismo que conduce el servidor.

NO ABRE AUDIO, igual que `SesionDeEstudio` y por lo mismo. El click se queda en el
servidor: aqui solo se avisa de que la repeticion cambio
(`al_cambiar_repeticion`), que es un dato, y quien conduzca decide si eso
significa rearrancar un click o no significa nada. El gemelo no quiere ninguno.

NO TIENE RELOJ. Todo el tiempo entra por parametro -`ahora` en `mirar`,
`instante_analisis` en `observar`-, porque el dueño del reloj de pared es quien
conduce: en produccion es `time.monotonic()` desde el servidor, en las pruebas un
reloj falso, y en el gemelo el reloj de la pasada sintetica. Debe ser monotonico.

NO SABE NADA DE CABLES. La falta de señal entra como el `senal_ausente` de
`mirar`, que es un hecho que le cuentan; que eso se publique como una pausa, se
dibuje en una pantalla o devuelva un 400 es cosa de quien conduce.

Dos relojes, como en el estudio y en el seguidor, y aqui tampoco se mezclan: el de
la PASADA (segundos desde el comienzo de la pieza, ya estirado por el factor de
tempo) y el del ANALISIS, que acompaña a cada cuadro de audio. Y dos puertas para
el primero, que usar la que no toca es un fallo: `avanzar(delta)` es relativa
-respeta la pausa del usuario y la cuenta atras, y puede dar la vuelta al bucle- y
`congelar_en(instante)` es absoluta y no toca la cuenta. Aqui se avanza cuando el
tiempo pasa y se congela cuando hay que recolocar el cabezal donde esta clase
dice.

`self._instante` NO es la cuenta de esta clase: es el ESPEJO del reloj del
estudio, que es la verdad (ver `mover_el_reloj`).

Candado: `SeguidorPieza` no lleva candado para sus dueños y `SesionDeEstudio`
lleva el suyo (reentrante) solo para su interior, asi que el de esta clase protege
SU estado -el espejo del reloj, las marcas del detector de final, la mirada y el
ultimo cuadro-. Lo muta el hilo de analisis (`observar`) y lo lee el hilo HTTP/WS
a 30 Hz (`mirar`), que es exactamente el reparto que tenia en el servidor.
"""

import threading
from dataclasses import replace
from typing import Callable

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.piezas.estudio import (
    EstadoEstudio,
    HistorialDeEstudio,
    InformeDePasada,
    PlanDePasada,
    SesionDeEstudio,
)

# Cuanto puede llevar el seguidor sin recibir un cuadro de audio para que sea
# seguro moverle el reloj a mano desde una mirada.
#
# Por que hace falta el limite: `SeguidorPieza.avanzar_a` descarta las pulsaciones
# EN VUELO (las que el detector resuelva con un onset anterior al salto), asi que
# llamarlo 30 veces por segundo mientras entra audio se comeria todas las notas:
# el detector tarda decenas de milisegundos en resolver una, y cada llamada las
# invalidaria antes de que llegara.
#
# Por que 0.25 s: es la ventana del propio detector para firmar un onset
# (`VENTANA_ATAQUE_COMO_ONSET_S`). Pasado ese tiempo sin un solo cuadro no hay
# nada en vuelo que pueda resolverse -resolver requiere cuadros-, asi que mover el
# reloj a mano no le quita nada a nadie. Y el caso que lo necesita es justo ese:
# sin audio (dispositivo desaparecido, o un arranque antes del primer cuadro) el
# reloj del seguidor no avanza solo, y el carril tiene que seguir sabiendo donde
# esta el cabezal.
#
# Con la sesion de estudio por medio el limite rige igual y por lo mismo: sus dos
# puertas al reloj -`colocar_en` y `avanzar`- acaban las dos en `avanzar_a` del
# seguidor, asi que las dos cuestan las pulsaciones en vuelo. De ahi que esta
# clase solo mueva el reloj del estudio cuando `_sin_cuadros` es verdad; mientras
# entra audio lo mueve `procesar`, que es el unico camino que no las pierde.
ESPERA_SIN_CUADROS_S = VENTANA_ATAQUE_COMO_ONSET_S

# Lo mas que puede entrar en la pieza por cada aviso: el invariante del reloj.
#
# La regla es de una linea y no admite casos: **un hueco largo no entra en la pieza
# por ningun camino**, venga el aviso de un cuadro de audio o de una consulta de
# estado, y llegue quien llegue primero tras el hueco. El cabezal avanza como mucho
# TECHO_TRAMO_S por aviso.
#
# El problema que resuelve: `mover_el_reloj` atribuye a la lectura nueva todo el
# tramo transcurrido desde la mirada anterior, y hay situaciones reales en las que
# nadie mira durante mucho tiempo -WebSocket desconectado o navegador en segundo
# plano, y dispositivo ausente, que es justo cuando nadie publica cuadros-. Sin
# techo, el primer aviso tras el hueco metia el hueco entero en el cabezal: con
# 30 s medidos, el cabezal saltaba a 30 s y el alumno fallaba de golpe todas las
# notas de esos 30 s sin haber oido ninguna.
#
# Por que rige SIEMPRE y no solo en algunos avisos: se intento acotar solo los
# tramos "sin testigo" y el salto volvio por tres caminos distintos en tres rondas
# de revision (el cuadro de la vuelta tras un apagon; el primer cuadro de una pieza
# iniciada sin dispositivo; la consulta de estado que gana la carrera a ese primer
# cuadro). Cada excepcion era un camino nuevo. Un hueco largo no es creible por
# ningun camino, asi que no hay excepcion que abrir.
#
# Por que no estorba: en produccion el latido son los cuadros, unos 47 por segundo
# (`INTERVALO_ANALISIS`), y el WebSocket pregunta a 30 Hz (33 ms). Mientras el
# alumno toca, el cabezal avanza con ellos y el techo no muerde ni con un pico de
# latencia por medio, porque 0,1 s es el triple de la cadencia del WebSocket y unas
# cinco veces la del analisis. Y si los avisos se espacian de verdad, el cabezal se
# queda CORTO, que es el error que queremos: un cabezal adelantado hace fallar notas
# que nunca sonaron; uno atrasado, no.
#
# Lo que esto NO es: una forma de llevar el reloj de la pieza con avisos lentos. Si
# alguien consultara el estado cada medio segundo sin audio, el cabezal avanzaria
# 0,1 s por consulta e iria cada vez mas atrasado. Es deliberado: sin audio no hay
# pieza que seguir, y el sitio donde eso se nota -la pausa por falta de señal- ya
# congela el reloj a proposito.
TECHO_TRAMO_S = 0.100


class ConductorDeEstudio:
    """Conduce una `SesionDeEstudio`: le mueve el reloj y le cierra las vueltas.

    Se le dan dos avisos y nada mas, y con ellos basta para una pasada entera:

    - `mirar(ahora, senal_ausente)`: ha pasado tiempo de pared. Mueve el reloj de
      la pasada si toca, y cierra en el historial lo que haya terminado.
    - `observar(resultado, instante_analisis)`: ha llegado un cuadro de audio.

    El reparto entre los dos no es una comodidad: `observar` solo corre cuando
    llega audio, y el caso que hay que atender es precisamente que deje de llegar
    -al desaparecer el dispositivo, la sesion de audio publica un unico resultado
    de silencio y entra en el ciclo de reintento sin publicar nada mas-, asi que
    hace falta la otra mitad, la que sigue viva sin audio.

    `historial` es opcional y se crea vacio si no se da, pero quien quiera que el
    historial sobreviva a empezar otra pasada de la misma cancion tiene que
    guardarlo fuera y pasarlo: esta clase no lo hace por nadie (el servidor lleva
    uno por NOMBRE de pieza).

    `techo_tramo_s` y `espera_sin_cuadros_s` se inyectan para poder conducir el
    reloj con otra cadencia -el gemelo no va a 47 cuadros por segundo- sin tocar
    las constantes, que son las de produccion y siguen siendo el valor por
    defecto.
    """

    def __init__(
        self,
        estudio: SesionDeEstudio,
        historial: HistorialDeEstudio | None = None,
        al_cambiar_repeticion: Callable[[EstadoEstudio], None] | None = None,
        techo_tramo_s: float = TECHO_TRAMO_S,
        espera_sin_cuadros_s: float = ESPERA_SIN_CUADROS_S,
    ) -> None:
        self._estudio = estudio
        self._historial = historial if historial is not None else HistorialDeEstudio()
        self._al_cambiar_repeticion = al_cambiar_repeticion
        self._techo_tramo_s = techo_tramo_s
        self._espera_sin_cuadros_s = espera_sin_cuadros_s
        self._candado = threading.RLock()
        # El espejo del reloj del estudio. Arranca donde el estudio diga y NO en
        # cero: con un plan que empieza en el compas 5 el cabezal arranca donde
        # ese compas caiga en segundos de la pasada, y eso lo sabe el estudio.
        self._instante = estudio.estado.carril.instante_s
        # Cuando se mira por ultima vez, en el reloj de quien conduce. None es
        # "todavia nadie": la primera mirada no cuenta tramo, porque no hay
        # mirada anterior desde la que contarlo. Quien conduzca puede fijarla al
        # arrancar (`fijar_la_mirada`), que es lo que hace el servidor para que el
        # tramo de la primera mirada se cuente desde que empezo la pasada.
        self._ultima_mirada: float | None = None
        # Cuando llego el ultimo cuadro AL SEGUIDOR, en el mismo reloj. None es
        # "ninguno todavia". Ver `ESPERA_SIN_CUADROS_S`.
        #
        # Con el reloj congelado NO se actualiza, porque los cuadros no llegan al
        # seguidor: se queda viejo a proposito, y asi la primera mirada tras
        # reanudar todavia cae en la rama "sin cuadros" y le recoloca el reloj al
        # seguidor antes de que vuelva a comer audio. Es lo que hace falta.
        self._ultimo_cuadro: float | None = None
        # Si el reloj esta congelado por falta de señal. Es la mitad de la pausa
        # que SI es del nucleo -el reloj quieto-; que ademas se publique, se
        # dibuje o se cuente como un estado del servidor no es cosa de aqui.
        self._congelado = False
        # Las dos marcas del detector de final (ver `cerrar_lo_que_termino`): lo
        # ultimo que se anoto en el historial, para no anotarlo dos veces. La
        # repeticion empieza en 1 porque es la primera vuelta, no la vuelta cero.
        self._termino_anunciado = False
        self._repeticion_anunciada = 1
        # Los informes que este conductor ha cerrado y anotado, en orden. Es lo
        # mismo que fue al historial, pero sin agregar: el historial responde
        # "vas mejor que ayer?" y esto responde "que paso en cada vuelta?", que es
        # lo que una verificacion -o el gemelo- necesita poder afirmar.
        self._vueltas_cerradas: tuple[InformeDePasada, ...] = ()
        # El factor que el historial sugiere para la pasada SIGUIENTE, o None si
        # no hay nada que sugerir. Solo se llena con el tempo automatico y SIN
        # bucle, que es el caso en que el plan no se puede tocar sin reiniciar la
        # pasada acabada (ver `cerrar_lo_que_termino`). Lo aplica quien conduce al
        # empezar la pasada siguiente.
        self._factor_sugerido: float | None = None

    @property
    def estudio(self) -> SesionDeEstudio:
        return self._estudio

    @property
    def historial(self) -> HistorialDeEstudio:
        return self._historial

    @property
    def vueltas_cerradas(self) -> tuple[InformeDePasada, ...]:
        """Los informes de las vueltas que este conductor cerro, en orden.

        No es el contador de repeticiones del estudio (`estado.repeticion`) ni el
        acumulado del informe: son las vueltas ANOTADAS, una por cada cierre.
        """
        return self._vueltas_cerradas

    @property
    def factor_sugerido(self) -> float | None:
        return self._factor_sugerido

    @property
    def instante(self) -> float:
        """El espejo del reloj de la pasada, en segundos y ya estirado por el tempo.

        Lo publica para que quien conduzca no tenga que llevar su propia cuenta:
        el reloj del estudio es la verdad y esto es lo que esta clase sabe de el.
        """
        return self._instante

    @property
    def congelado(self) -> bool:
        """Si el reloj esta parado porque no hay señal que oir."""
        return self._congelado

    def fijar_la_mirada(self, ahora: float) -> None:
        """Deja la mirada puesta en `ahora` sin mover nada.

        Es para el arranque: el tramo de la primera mirada se cuenta desde aqui,
        asi que quien empieza una pasada fija la mirada en ese instante y no deja
        que la primera cuente el tiempo que el proceso llevaba encendido.
        """
        with self._candado:
            self._ultima_mirada = ahora

    def mirar(self, ahora: float, senal_ausente: bool) -> EstadoEstudio:
        """El aviso completo del reloj de pared: mueve, cierra y avisa.

        Devuelve el estado LEIDO TRAS MOVER EL RELOJ y antes de cerrar, que es el
        que hay que publicar: si el cierre cambia el plan -el tempo automatico con
        bucle-, el estado posterior describe ya el plan nuevo, y quien mira pidio
        una foto de este instante, no del siguiente.

        Son los dos pasos en el orden en que tienen que ir, y se exponen tambien
        por separado (`mover_el_reloj`, `cerrar_lo_que_termino`) porque el camino
        del audio solo necesita el primero: cerrar una vuelta puede acabar en un
        callback de quien conduce, y el hilo del analisis no es sitio para eso.
        """
        with self._candado:
            self.mover_el_reloj(ahora, senal_ausente)
            estado = self._estudio.estado
            self.cerrar_lo_que_termino(estado)
            return estado

    def observar(
        self, resultado: ResultadoAnalisis, instante_analisis: float
    ) -> EstadoEstudio:
        """Alimenta al estudio con un cuadro de analisis.

        Corre DENTRO del hilo de analisis de quien conduce, asi que aqui no se
        hace nada lento. Tampoco se cierra ninguna vuelta: eso es de `mirar`.

        El reloj de pared que usa es el de la ULTIMA MIRADA, y no uno propio
        porque esta clase no tiene reloj: quien conduce mira y en seguida observa
        con el mismo instante (es lo que hace el servidor en su observador), asi
        que la mirada es ese instante. Sin ninguna mirada todavia se usa el reloj
        del analisis, que en produccion es el mismo `time.monotonic()`.

        Con el reloj congelado por falta de señal el cuadro NO llega al estudio.
        No es un detalle: con el cable enchufado y callado los cuadros de silencio
        siguen llegando, y `procesar` mueve el reloj con cada uno, asi que
        alimentarlo durante la pausa dejaria el carril corriendo igual que si no
        hubiera pausa.

        Y si este cuadro llega despues de un hueco largo -el audio se paro y ha
        vuelto- se le recoloca el reloj al estudio ANTES de darle de comer, con
        `congelar_en` y no con la puerta relativa: es una colocacion en el sitio
        que esta clase ya decidio, no un tiempo que haya pasado, y tratarla como
        un avance le haria dar la vuelta al bucle por un hueco de audio.

        Y con `congelar_en` y no con `colocar_en`, que es la otra puerta absoluta:
        `colocar_en` CANCELA la cuenta atras, y `_ultimo_cuadro` empieza a None,
        asi que el PRIMER cuadro tras arrancar entraba por aqui y mataba la cuenta
        que `arrancar()` acababa de abrir, unos 21 ms despues de pulsar «empezar».
        Lo mismo con cualquier hueco de audio dentro de una cuenta de vuelta.
        Cancelar la cuenta es el contrato de `colocar_en` para las ordenes del
        USUARIO (saltar, cambiar de plan); congelar el reloj no es una de ellas.

        Sin recolocar, `procesar` calcula el instante de la pieza restandole al
        reloj del analisis un origen fijado antes del hueco, y el hueco entero
        entra en el cabezal: con 30 s de apagon, el cabezal saltaba a 30 s aunque
        el reloj de esta clase se hubiera quedado donde debia. Recolocar es seguro
        justo ahi, por lo mismo que en `mover_el_reloj`: sin cuadros no hay
        pulsacion en vuelo que pueda resolverse.
        """
        with self._candado:
            if self._congelado:
                return self._estudio.estado
            mirada = self._ultima_mirada
            ahora = instante_analisis if mirada is None else mirada
            if self._sin_cuadros(ahora):
                self._estudio.congelar_en(self._instante)
            self._ultimo_cuadro = ahora
            # El espejo del reloj NO se actualiza con el cuadro, y es a proposito:
            # lo adopta la mirada (`mover_el_reloj`), que es quien lo lee. Si se
            # actualizara aqui, una señal que se fuera justo despues congelaria el
            # cabezal donde lo dejo el ultimo cuadro en vez de donde lo dejo la
            # ultima mirada, y la pausa por falta de señal dejaria de ser el punto
            # fijo que las pruebas del carril fijan.
            return self._estudio.procesar(resultado, instante_analisis)

    def mover_el_reloj(self, ahora: float, senal_ausente: bool) -> None:
        """Mueve el reloj de la pasada y congela si falta la señal.

        Es la PRIMERA MITAD de `mirar`, y esta suelta porque el camino del audio
        necesita solo esta: quien reciba los cuadros en un hilo de analisis mueve
        el reloj aqui y deja los cierres -y el callback que cuelga de ellos- para
        la mirada siguiente, que corre donde se pueda gastar tiempo.

        El tramo transcurrido entre dos miradas se le PASA a la sesion de estudio,
        y cuenta solo si en esta mirada HAY señal. Dicho de otro modo: el tiempo
        sin señal no entra en la pieza, que es lo que pide la spec §5 (un carril
        que corre con el cable desenchufado te hace fallar notas que nunca
        sonaron).

        Atribuir el tramo a la lectura NUEVA y no a la vieja es deliberado: la
        señal se va y vuelve entre dos miradas, y nadie sabe en que punto exacto.
        Con miradas cada 33 ms como maximo (el WebSocket, y mas a menudo cuando
        entra audio), el error es de una mirada, y se equivoca del lado bueno: al
        perder la señal no se cuenta tiempo que el alumno no oyo, y al volver no
        se pierde tiempo que ya estaba sonando.

        Pero "una mirada" solo es poco tiempo mientras alguien mire, y el caso en
        que nadie mira es real: con el WebSocket desconectado y el dispositivo
        desaparecido no hay ni cuadros ni consultas de estado, y el tramo hasta la
        vuelta puede ser de minutos. De ahi que el tramo se cuente con techo
        (`TECHO_TRAMO_S`), y con techo SIEMPRE, sin mirar de donde viene el aviso:
        cada excepcion a esa regla ha sido un camino nuevo por el que el hueco
        volvia a entrar.

        Al congelar se le congela tambien el reloj al estudio (`congelar_en`, que
        acaba en el `avanzar_a` del seguidor y NO cancela la cuenta atras: perder
        la senal en plena cuenta no es motivo para tirarla), que es lo que hace
        segura la pausa:
        `avanzar_a` invalida las pulsaciones en vuelo -las tocadas en el tramo que
        se acaba de abandonar- y deja la correspondencia entre relojes sin fijar,
        de modo que el primer cuadro tras la vuelta la fija de nuevo y la pieza
        sigue donde estaba.
        """
        with self._candado:
            estudio = self._estudio
            # La primera mirada no tiene desde donde contar: sin esto, el tramo
            # saldria de la distancia entre cero y un reloj monotonico que lleva
            # horas encendido, y el techo lo convertiria en un empujon de 0,1 s
            # que nadie pidio. Quien conduce la fija antes con `fijar_la_mirada`.
            mirada = self._ultima_mirada
            transcurrido = 0.0 if mirada is None else ahora - mirada
            self._ultima_mirada = ahora
            if not senal_ausente:
                self._congelado = False
                # El tramo se le pasa a la sesion de estudio, que decide que
                # hacer con el: en pausa del usuario no suma nada, durante la
                # cuenta atras descuenta la cuenta, y al final del bucle da la
                # vuelta. Solo cuando NO llegan cuadros, porque con audio el reloj
                # lo mueve `procesar` (ver ESPERA_SIN_CUADROS_S: colocarlo con
                # audio entrando cuesta las pulsaciones en vuelo).
                if self._sin_cuadros(ahora):
                    estudio.avanzar(min(transcurrido, self._techo_tramo_s))
            elif not self._congelado:
                self._congelado = True
                estudio.congelar_en(self._instante)
            # El reloj de la sesion de estudio es la verdad, y esta clase lo
            # adopta en vez de llevar su propia cuenta: ella congela durante la
            # cuenta atras y da la vuelta al bucle. Sin esta linea el cabezal
            # saltaba hacia delante al acabar cada cuenta atras.
            self._instante = estudio.estado.carril.instante_s

    def _sin_cuadros(self, ahora: float) -> bool:
        """Si el seguidor lleva tanto sin recibir audio que se le puede mover el
        reloj a mano sin costarle una pulsacion. Ver `ESPERA_SIN_CUADROS_S`."""
        return (
            self._ultimo_cuadro is None
            or ahora - self._ultimo_cuadro >= self._espera_sin_cuadros_s
        )

    def cerrar_lo_que_termino(self, estado: EstadoEstudio) -> None:
        """Anota en el historial lo que acabo de cerrarse, y mueve el tempo si toca.

        Se llama BAJO candado y con el estado recien leido, porque es ahi donde se
        ve la transicion. Lo que mira son dos, y hacen falta las dos:

        - Cambio de `repeticion`: estudiando un bucle, la pregunta "ya te sale?"
          es sobre la vuelta que acaba de pasar, asi que cada vuelta es una
          pasada del historial.
        - `tramo_terminado` de False a True: sin bucle, la pasada acaba una vez.

        `cerrar_repeticion` devuelve el informe de SOLO esa vuelta, que es lo que
        se anota: anotar el acumulado contaria las vueltas anteriores otra vez.

        Y el tempo automatico se aplica SOLO con bucle. Sin bucle no se toca el
        plan: se publica la sugerencia en `factor_sugerido` y quien conduce la
        aplicara al empezar la pasada siguiente. La razon es que `cambiar_plan`
        recoloca el cabezal cuando el pulso cae fuera del tramo y limpia
        `tramo_terminado` -es su contrato, no un defecto-, asi que llamarlo con la
        pasada ya acabada arrancaba solo un bucle que nadie pidio: la pantalla
        decia "terminado" 33 ms, el cabezal se iba al principio y esa pasada
        fantasma no se anotaba nunca. Con bucle no hay nada de eso: la vuelta
        siguiente empieza ya y el cabezal lo esta recolocando el propio bucle.

        El aviso de la repeticion nueva (`al_cambiar_repeticion`) sale AL FINAL,
        con el plan ya movido si habia que moverlo: quien escuche quiere saber
        contra que tempo se vuelve a empezar, y en el servidor ese oyente es el
        click.
        """
        with self._candado:
            estudio = self._estudio
            termino = estado.tramo_terminado and not self._termino_anunciado
            dio_la_vuelta = estado.repeticion != self._repeticion_anunciada
            if not termino and not dio_la_vuelta:
                return
            self._termino_anunciado = estado.tramo_terminado
            self._repeticion_anunciada = estado.repeticion
            # Al dar la vuelta, `_dar_la_vuelta` ya cerro la repeticion por dentro
            # y su informe se perdio: lo que se anota aqui es lo que el estudio
            # tenga cerrado. Por eso `SesionDeEstudio._dar_la_vuelta` guarda el
            # informe de la vuelta en `self._ultima_vuelta`, y aqui se lee.
            informe = (
                estudio.ultima_vuelta if dio_la_vuelta else estudio.cerrar_repeticion()
            )
            if informe is None:
                return
            self._historial.anotar(informe)
            self._vueltas_cerradas += (informe,)
            if estudio.plan.tempo_automatico:
                self._mover_el_tempo(estudio)
            if dio_la_vuelta:
                self._avisar_de_la_repeticion(estado)

    def _mover_el_tempo(self, estudio: SesionDeEstudio) -> None:
        """Pregunta al historial por el factor de la pasada siguiente y lo aplica.

        El cuerpo de la rama del tempo automatico de `cerrar_lo_que_termino`, y
        corre bajo su mismo candado.
        """
        # `factor_sugerido` CONSUME la racha al decidir, asi que se le pregunta
        # una sola vez por pasada anotada, aqui.
        sugerido = self._historial.factor_sugerido(estudio.plan.factor_tempo)
        if sugerido == estudio.plan.factor_tempo:
            return
        if estudio.plan.en_bucle:
            # El reloj del plan nuevo se adopta en el acto: `cambiar_plan`
            # recoloca el cabezal en el mismo pulso, y entre esto y la mirada
            # siguiente puede colarse una pausa que lo colocaria en el viejo.
            self._instante = estudio.cambiar_plan(
                replace(estudio.plan, factor_tempo=sugerido)
            ).carril.instante_s
        else:
            self._factor_sugerido = sugerido

    def _avisar_de_la_repeticion(self, estado: EstadoEstudio) -> None:
        """Le cuenta a quien conduce que la repeticion cambio. Bajo candado.

        Va bajo candado a proposito, y no por descuido: en el servidor el oyente
        es el click, que se ajusta siempre bajo el mismo candado que el reloj, y
        soltarlo aqui dejaria que el estado se moviera entre el aviso y lo que el
        oyente haga con el. El precio es que un oyente lento retiene el candado,
        que es el mismo trato que ya tenia en `SesionCarril`.
        """
        if self._al_cambiar_repeticion is not None:
            self._al_cambiar_repeticion(estado)

    def cambiar_plan(self, plan: PlanDePasada) -> EstadoEstudio:
        """Cambia el plan de la pasada SIN reiniciar lo tocado, y adopta su reloj.

        Es una orden de quien conduce -el usuario moviendo el deslizador- y no un
        tramo de tiempo, asi que no pasa por el reloj de las miradas.
        """
        with self._candado:
            # El reloj que devuelve el nucleo se adopta AQUI, y no se deja para la
            # mirada siguiente: si la señal ya se habia ido y nadie ha mirado
            # desde entonces, la primera mirada entra por la rama de la pausa y
            # coloca el cabezal en `self._instante`, que seria el de antes de esta
            # orden. Asi se perdia justo la primera accion del usuario tras un
            # apagon, que es el caso que la etapa 3a documenta como real.
            estado = self._estudio.cambiar_plan(plan)
            self._instante = estado.carril.instante_s
            # Un plan nuevo puesto a mano deja sin sentido la sugerencia anterior:
            # el historial la hizo sobre el plan que ya no esta.
            self._factor_sugerido = None
            return estado

    def saltar_al_compas(self, numero: int) -> EstadoEstudio:
        """Coloca el cabezal al principio de un compas DEL TRAMO y adopta su reloj."""
        with self._candado:
            # El reloj que devuelve el nucleo se adopta aqui, por lo mismo que en
            # `cambiar_plan`: sin esto, un salto pedido con la señal ya perdida y
            # sin ninguna mirada por medio se quedaba en el sitio viejo.
            estado = self._estudio.saltar_al_compas(numero)
            self._instante = estado.carril.instante_s
            # Y la sugerencia se va con el salto, igual que `tramo_terminado` se
            # va dentro del nucleo: saltar es empezar a tocar otra vez, y la
            # sugerencia era sobre la pasada que acabo. Si se quedara puesta, el
            # usuario que la ignora y toca otra pasada que no mueve el factor
            # seguiria viendo ofrecido un cambio que el historial ya no dice:
            # `cerrar_lo_que_termino` solo la escribe, nunca la borra, asi que
            # borrarla es de quien empieza la pasada nueva.
            self._factor_sugerido = None
            return estado
