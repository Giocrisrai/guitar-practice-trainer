"""La sesion del carril: lleva el reloj de la pieza y le da de comer al estudio.

Reparto de trabajo con el nucleo, que es lo que explica todo lo demas:

- `SesionDeEstudio` (nucleo) envuelve al `SeguidorPieza`: sabe que nota toca
  ahora, a que nota de la pieza pertenece cada pulsacion, en que compas va el
  cabezal, cuando el bucle da la vuelta y que lleva anotado la pasada. Su reloj
  lo mueven los cuadros de audio, o el delta que le pasa esta clase.
- Esta clase (servidor) es la dueña del RELOJ DE PARED y de la PAUSA POR FALTA DE
  SEÑAL. El reloj se inyecta para que las pruebas lo muevan a mano, y la pausa
  -por falta de señal- es cosa del servidor: el nucleo no sabe nada de cables.

Dos puertas para el reloj del estudio, y usar la que no toca es un fallo:
`avanzar(delta)` es relativa (respeta la pausa del usuario y la cuenta atras, y
puede dar la vuelta al bucle) y `colocar_en(instante)` es absoluta (cancela la
cuenta atras y nunca da la vuelta). Aqui se avanza cuando el tiempo pasa y se
coloca cuando hay que recolocar el cabezal donde esta clase dice.

Dos pausas, y tampoco se mezclan: `pausado` es "no llega senal del cable" y la
decide esta clase mirando el audio; `en_pausa` la decide el usuario y la lleva la
sesion de estudio. El estado publica las dos, porque la interfaz dice cosas
distintas.

Es la hermana de `SesionPractica` (`servidor/ejercicios.py`) y copia su forma: se
suscribe al flujo de analisis como observadora en vez de muestrearlo, protege con
un candado la instantanea que lee el hilo HTTP, y no hace nada lento dentro del
observador.
"""

import threading
import time
from dataclasses import replace
from typing import Callable

from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.piezas.compases import compases_de_la_seccion
from nucleo.piezas.estudio import (
    EstadoEstudio,
    HistorialDeEstudio,
    PlanDePasada,
    SesionDeEstudio,
)
from nucleo.piezas.modelo import Pieza
from nucleo.piezas.seguimiento import EstadoCarril
from nucleo.sintesis import Metronomo, SalidaAudio
from servidor.configuracion import Configuracion

# Cuanto puede llevar el seguidor sin recibir un cuadro de audio para que sea
# seguro moverle el reloj a mano desde `estado()`.
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
# El problema que resuelve: `_mirar` atribuye a la lectura nueva todo el tramo
# transcurrido desde la mirada anterior, y hay situaciones reales en las que nadie
# mira durante mucho tiempo -WebSocket desconectado o navegador en segundo plano, y
# dispositivo ausente, que es justo cuando nadie publica cuadros-. Sin techo, el
# primer aviso tras el hueco metia el hueco entero en el cabezal: con 30 s medidos,
# el cabezal saltaba a 30 s y el alumno fallaba de golpe todas las notas de esos
# 30 s sin haber oido ninguna.
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

# El perfil que se da por activo cuando la sesion de audio no dice cual es (ver
# `SesionCarril._perfil_activo`). Es el mismo que trae la configuracion recien
# hecha, para no tener dos respuestas distintas a la misma pregunta.
PERFIL_POR_DEFECTO = Configuracion().perfil

# Lo que publica un carril sin pieza: las mismas claves que con pieza, para que el
# WebSocket y la interfaz no tengan que distinguir dos formas de estado.
#
# La etapa 3c añade los campos de la pasada (compas, repeticion, tempo...), asi
# que el estado apagado los lleva tambien: si se quedara con los cinco de la
# etapa 3a, la interfaz tendria otra vez dos formas de estado que distinguir, que
# es justo lo que este objeto existe para evitar. Los valores son los de "no hay
# nada que practicar": compas 1 -el unico que no miente sobre un cabezal que no
# esta en ninguna parte-, ultimo compas 0 porque no hay tramo, y el plan por
# defecto en lo demas.
_CARRIL_APAGADO = EstadoCarril(
    instante_s=0.0, indice_actual=0, total=0, completado=False, tocadas=()
)
_ESTUDIO_APAGADO = EstadoEstudio(
    carril=_CARRIL_APAGADO,
    instante_pulsos=0.0,
    compas_en_curso=1,
    total_de_compases=0,
    primer_compas=1,
    ultimo_compas=0,
    repeticion=1,
    cuenta_atras_restante_s=0.0,
    factor_tempo=1.0,
    tempo_efectivo=0.0,
    en_bucle=False,
    con_click=False,
    tempo_automatico=False,
    en_pausa=False,
    compas_variable=False,
    ritmo_aproximado=False,
    tramo_terminado=False,
)

# El `arranque` que publica un carril sin pieza. Los arranques de verdad empiezan
# en 1, asi que el cero no es el de ninguna pieza y nadie puede confundirlo con
# una: es justo lo que se quiere, porque este estado no describe ninguna.
ARRANQUE_NINGUNO = 0


class SesionCarril:
    """Propietaria de la pieza en curso, de su estudio y del reloj que lo mueve.

    Dos relojes, como en el seguidor, y aqui tampoco se pueden mezclar:

    - El de la PASADA, en segundos desde el comienzo de la pieza y ya estirado por
      el factor de tempo, es lo que publica `estado()["instante_s"]`. Esta clase
      mide el tiempo transcurrido entre dos miradas y se lo PASA a la sesion de
      estudio, que es quien decide que hacer con el: en pausa del usuario no suma
      nada, durante la cuenta atras la descuenta, y al final del tramo da la
      vuelta al bucle. Los tramos sin señal no se le pasan.
    - El del ANALISIS, que acompaña a cada cuadro de audio, se le pasa al estudio
      tal cual (`procesar`), porque sus esperas estan medidas en el.

    `self._instante` NO es la cuenta de esta clase: es el ESPEJO del reloj del
    estudio, que es la verdad (ver `_mirar`).

    En produccion los dos son `time.monotonic()`; el reloj se inyecta para que las
    pruebas lo muevan a mano, y debe ser monotonico.

    Candado: `SeguidorPieza` no lleva candado para sus dueños (el suyo protege su
    interior, pero quien lo comparta entre hilos tiene que ordenar los accesos).
    Aqui lo muta el hilo de analisis (`_observar`) y lo lee el hilo HTTP/WS a 30 Hz
    (`estado()`), asi que el candado de la pausa y el del reloj son de esta clase,
    y la instantanea se construye ENTERA debajo de el: en la etapa 2a se colo un
    fallo por leer dos campos sin candado y devolver un estado a medias.

    Frontera con la sesion de audio: `senal_ausente`, `registrar_observador` y
    `quitar_observador`, mas `activa` (opcional: un doble que no la tenga se da
    por activo). Es una frontera estrecha a proposito: asi una prueba puede darle
    un doble de pocas lineas en vez de obligar a `Sesion` a llevar un interruptor
    que solo sirva para los tests.
    """

    def __init__(
        self,
        sesion_audio,
        reloj: Callable[[], float] = time.monotonic,
        perfil_activo: Callable[[], str] | None = None,
        salida: SalidaAudio | None = None,
    ) -> None:
        self._sesion_audio = sesion_audio
        # La salida de audio del click, inyectable como en `SesionPractica`. Crear
        # una `SalidaAudio` no abre ningun dispositivo: eso lo hace `abrir()`, y
        # solo cuando un plan pide click.
        self._salida = salida or SalidaAudio()
        self._metronomo: Metronomo | None = None
        # (tempo, repeticion) del ultimo intento de arrancar el click, haya salido
        # bien o no. Es lo que decide si hay que rearrancar, y que un intento
        # fallido tambien se anote evita reabrir el dispositivo 30 veces por
        # segundo con el cable de los altavoces desenchufado.
        self._clave_del_click: tuple[int, int] | None = None
        self._reloj = reloj
        self._perfil_activo_inyectado = perfil_activo
        self._pieza: Pieza | None = None
        self._estudio: SesionDeEstudio | None = None
        # Un historial por NOMBRE de pieza, porque el historial tiene que
        # sobrevivir a empezar otra pasada de la misma cancion: es justo para eso.
        # Se vacia al apagar el servidor, que es la decision del usuario.
        #
        # La clave es el nombre y no la pieza entera: dos canciones distintas que
        # se llamen igual comparten historial. Es un empate declarado, y el precio
        # de equivocarse es un "fallas el 19" de otra cancion, no un dato perdido.
        self._historiales: dict[str, HistorialDeEstudio] = {}
        # El historial de la pieza en marcha. Sin pieza no es el de nadie: lo
        # reemplaza `iniciar` con el que corresponde al nombre, y nadie lo lee
        # antes (los dos sitios que lo tocan pasan primero por el estudio, que
        # sin pieza no existe).
        self._historial = HistorialDeEstudio()
        # Las dos marcas del detector de final (ver `_cerrar_lo_que_termino`): lo
        # ultimo que se anoto en el historial, para no anotarlo dos veces. La
        # repeticion empieza en 1 porque es la primera vuelta, no la vuelta cero.
        self._termino_anunciado = False
        self._repeticion_anunciada = 1
        # El factor que el historial sugiere para la pasada SIGUIENTE, o None si
        # no hay nada que sugerir. Solo se llena con el tempo automatico y SIN
        # bucle, que es el caso en que el plan no se puede tocar sin reiniciar la
        # pasada acabada (ver `_cerrar_lo_que_termino`). Lo aplica la interfaz al
        # empezar la pasada siguiente, y por eso viaja en el estado.
        self._factor_sugerido: float | None = None
        # Que arranque publica el estado: sube en cada `iniciar` y nunca se
        # reutiliza. Es lo que le permite al navegador saber de QUE pieza habla un
        # paquete, en vez de adivinarlo.
        #
        # Hace falta porque el WebSocket y la respuesta de `iniciar` son dos
        # canales distintos y se cruzan: un paquete emitido antes del arranque
        # puede llegar despues de la respuesta, y uno emitido despues puede llegar
        # antes. Sin etiqueta, el navegador acababa comparando totales para
        # adivinar, y dos piezas del mismo tamaño -tocar dos veces la misma
        # escala- se confundian: salia el resumen de la anterior sobre la nueva.
        self._arranque = ARRANQUE_NINGUNO
        self._candado = threading.Lock()
        # Candado de arranque y parada, aparte del otro. Sin el, dos `iniciar()`
        # a la vez desde el hilo HTTP pueden registrar el observador dos veces y
        # `quitar_observador` solo quita uno, asi que quedaria un observador
        # huerfano alimentando al seguidor de una pieza ya muerta. Es RLock porque
        # `iniciar` llama a `detener` con el ya tomado.
        self._candado_arranque = threading.RLock()
        # Reloj de la pieza y contabilidad de la pausa. Todo bajo `_candado`.
        self._instante = 0.0
        self._ultima_mirada = reloj()
        self._pausado = False
        # Cuando llego el ultimo cuadro AL SEGUIDOR, en el reloj de esta clase.
        # None es "ninguno todavia". Ver `ESPERA_SIN_CUADROS_S`.
        #
        # Durante la pausa NO se actualiza, porque los cuadros no llegan al
        # seguidor: se queda viejo a proposito, y asi la primera mirada tras
        # reanudar todavia cae en la rama "sin cuadros" y le recoloca el reloj al
        # seguidor antes de que vuelva a comer audio. Es lo que hace falta.
        self._ultimo_cuadro: float | None = None

    @property
    def activa(self) -> bool:
        return self._estudio is not None

    @property
    def pieza(self) -> Pieza | None:
        return self._pieza

    def iniciar(self, pieza: Pieza, plan: PlanDePasada | None = None) -> dict:
        """Arranca una pieza con su plan. Devuelve la pieza ENTERA y el estado.

        La pieza se devuelve aqui y una sola vez: `estado()` no la repite, porque
        lo llama el WebSocket 30 veces por segundo y mandar cientos de notas que
        no cambian seria tirar el canal. Quien recargue el navegador a mitad de
        cancion la vuelve a pedir por `pieza_en_marcha`, que es la deuda que la
        etapa 3a dejo abierta.

        Sin plan se usa `PlanDePasada()`, que es exactamente el comportamiento de
        la etapa 3a: la pieza entera, a tempo escrito, sin bucle y sin click.

        Un plan imposible -un factor fuera de rango, un compas que la pieza no
        tiene- sale como `ValueError` desde el nucleo, y `iniciar_pieza` lo
        traduce a 400 igual que el de la afinacion.

        La respuesta lleva tambien el `arranque` de esta pieza -viene dentro de
        `estado()`-, que es la etiqueta con la que el navegador reconoce despues
        sus paquetes y descarta los de la pieza anterior (ver `self._arranque`).

        Se rechaza una pieza escrita en otra afinacion que la activa (spec §5):
        dibujar trastes que tu instrumento no tiene es peor que no dibujar nada.
        El mensaje nombra las dos afinaciones, que es lo unico que le permite al
        usuario arreglarlo.
        """
        perfil_activo = self._perfil_activo()
        if pieza.perfil != perfil_activo:
            raise ValueError(
                f"La pieza '{pieza.nombre}' esta escrita en la afinacion "
                f"'{pieza.perfil}' y la tuya activa es '{perfil_activo}': "
                "cambia de afinacion o elige otra pieza"
            )
        with self._candado_arranque:
            self.detener()
            ahora = self._reloj()
            with self._candado:
                self._pieza = pieza
                self._estudio = SesionDeEstudio(pieza, plan or PlanDePasada())
                # Empezar a tocar abre la cuenta atras (la spec la pide antes de
                # la primera entrada, no solo al dar la vuelta el bucle).
                self._estudio.arrancar()
                self._historial = self._historiales.setdefault(
                    pieza.nombre, HistorialDeEstudio()
                )
                self._termino_anunciado = False
                self._repeticion_anunciada = 1
                self._factor_sugerido = None
                self._arranque += 1
                # NO cero: con un plan que empieza en el compas 5 el cabezal
                # arranca donde diga el estudio, que es quien sabe donde cae ese
                # compas en segundos de la pasada.
                self._instante = self._estudio.estado.carril.instante_s
                self._ultima_mirada = ahora
                self._ultimo_cuadro = None
                self._pausado = False
            # (`detener()` de arriba ya paro el click de la pieza anterior.)
            # El observador se registra AL FINAL, con el estudio ya en su sitio:
            # si se registrara antes, el primer cuadro podria entrar con
            # `_estudio` a None y el audio de ese instante se perderia sin que
            # nada lo dijera.
            self._sesion_audio.registrar_observador(self._observar)
        return {
            "pieza": pieza.a_dict(),
            "secciones_en_compases": self._secciones_en_compases(pieza),
            **self.estado(),
        }

    def detener(self) -> None:
        """Para el carril y suelta la pieza. Seguro de llamar varias veces.

        El observador se quita PRIMERO, igual que en `SesionPractica`: asi ningun
        cuadro posterior puede alimentar al estudio que las lineas siguientes
        estan soltando.

        El historial NO se suelta: vive en `_historiales`, por nombre de pieza, y
        tiene que sobrevivir a detener y volver a empezar la misma cancion.

        Va bajo `_candado_arranque` (reentrante, porque `iniciar` lo llama con el
        ya tomado) para que no pueda cruzarse con un `iniciar()` y dejar
        registrado un observador sin pieza, o al contrario.
        """
        with self._candado_arranque:
            self._sesion_audio.quitar_observador(self._observar)
            with self._candado:
                self._parar_click()
                self._estudio = None
                self._pieza = None
                self._instante = 0.0
                self._ultima_mirada = self._reloj()
                self._ultimo_cuadro = None
                self._pausado = False
                self._termino_anunciado = False
                self._repeticion_anunciada = 1
                self._factor_sugerido = None

    def estado(self) -> dict:
        """Instantanea para la interfaz: el `EstadoEstudio` mas `pausado`.

        Mueve el reloj aqui, ademas de en `_observar`, y por la misma razon que
        `SesionPractica.estado()` ajusta ahi el metronomo: los dos sitios cubren
        mitades distintas del problema. `_observar` solo corre cuando llega audio,
        y el caso que hay que atender es precisamente que deje de llegar: al
        desaparecer el dispositivo, la sesion de audio publica un unico resultado
        de silencio y entra en el ciclo de reintento sin publicar nada mas, asi que
        el observador no vuelve a correr NUNCA. Este metodo, en cambio, lo llama el
        WebSocket a 30 Hz, y es la mitad que sigue viva.

        `pausado` lo añade el servidor y no el nucleo: el nucleo no sabe nada de
        cables, y la interfaz necesita poder decir "sin señal" en vez de fingir
        que la pieza va sola. `en_pausa` -la del usuario- viene del estudio y es
        otra cosa: las dos se publican, y la interfaz dice cosas distintas.
        """
        ahora = self._reloj()
        # Fuera del candado: en la sesion de verdad es una propiedad que mira su
        # historial de niveles, y no hay motivo para hacerla esperar a nadie.
        ausente = self._sin_senal()
        # Este candado se retiene mientras `_instantanea` espera el del seguidor,
        # que puede estar en manos de un `procesar` en curso. Es a proposito: la
        # instantanea tiene que salir entera de una sola lectura. La espera es de
        # un cuadro de analisis como maximo (`procesar` no hace E/S ni espera a
        # nadie), asi que a 30 Hz no se nota; si algun dia el seguidor hiciera algo
        # lento ahi dentro, esto habria que revisarlo.
        with self._candado:
            self._mirar(ahora, ausente)
            return self._instantanea()

    def _sin_senal(self) -> bool:
        """Si el carril debe tratarse como sin señal: no hay audio que oir.

        Son dos casos distintos y hacen falta los dos. `senal_ausente` es el nivel
        por debajo del umbral de ruido durante mas de 5 s (incluido quien deja de
        tocar). Pero mientras la captura NO esta abierta -el cable sin enchufar al
        arrancar, o el permiso de microfono sin conceder- el bucle de la sesion
        reintenta sin publicar nada, ni siquiera un silencio, asi que
        `senal_ausente` nunca llega a ser verdadero y el carril corria con la
        pieza entera fallandose sin que el alumno oyera nada. La captura cerrada
        cuenta como ausente de inmediato.
        """
        activa = getattr(self._sesion_audio, "activa", True)
        return bool(self._sesion_audio.senal_ausente) or not activa

    def _perfil_activo(self) -> str:
        """La afinacion con la que el usuario esta tocando ahora mismo.

        Por defecto se le pregunta a la sesion de audio, que es quien la tiene
        (`Sesion.configuracion.perfil`), pero la configuracion NO es parte de la
        frontera de tres miembros que esta clase le exige: una sesion que no la
        lleve -un doble de prueba, o un futuro flujo de audio distinto- no tiene
        que inventarse una. Quien quiera decidirlo de otra manera inyecta
        `perfil_activo`.
        """
        if self._perfil_activo_inyectado is not None:
            return self._perfil_activo_inyectado()
        configuracion = getattr(self._sesion_audio, "configuracion", None)
        return PERFIL_POR_DEFECTO if configuracion is None else configuracion.perfil

    def _observar(self, resultado, instante_analisis: float) -> None:
        """Alimenta al estudio con un cuadro de analisis.

        Corre DENTRO del hilo de analisis, asi que aqui no se hace nada lento: se
        mueve el reloj bajo candado, se suelta, y `procesar` -que es el trabajo de
        verdad- corre fuera, con el candado del propio seguidor.

        Mientras el carril esta pausado por falta de señal el cuadro NO llega al
        estudio. No es un detalle: con el cable enchufado y callado los cuadros de
        silencio siguen llegando, y `procesar` mueve el reloj con cada uno, asi
        que alimentarlo durante la pausa dejaria el carril corriendo igual que si
        no hubiera pausa.

        Y si este cuadro llega despues de un hueco largo -el audio se paro y ha
        vuelto- se le recoloca el reloj al estudio ANTES de darle de comer, con la
        puerta ABSOLUTA (`colocar_en`) y no con la relativa: es una colocacion en
        el sitio que esta clase ya decidio, no un tiempo que haya pasado, y
        tratarla como un avance le haria dar la vuelta al bucle por un hueco de
        audio. Sin recolocar, `procesar` calcula el instante de la pieza
        restandole al reloj del analisis un origen fijado antes del hueco, y el
        hueco entero entra en el cabezal: con 30 s de apagon, el cabezal saltaba a
        30 s aunque el reloj de esta clase se hubiera quedado donde debia.
        Recolocar es seguro justo ahi, por lo mismo que en `_mirar`: sin cuadros no
        hay pulsacion en vuelo que pueda resolverse.
        """
        ahora = self._reloj()
        ausente = self._sin_senal()
        with self._candado:
            self._mirar(ahora, ausente)
            estudio = self._estudio
            if estudio is None or self._pausado:
                return
            if self._sin_cuadros(ahora):
                estudio.colocar_en(self._instante)
            self._ultimo_cuadro = ahora
        estudio.procesar(resultado, instante_analisis)

    def _mirar(self, ahora: float, ausente: bool) -> None:
        """Mueve el reloj de la pasada y ajusta la pausa. Se llama BAJO candado.

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

        Al pausar se le congela tambien el reloj al estudio (`colocar_en`, que
        acaba en el `avanzar_a` del seguidor), que es lo que hace segura la pausa:
        `avanzar_a` invalida las pulsaciones en vuelo -las tocadas en el tramo que
        se acaba de abandonar- y deja la correspondencia entre relojes sin fijar,
        de modo que el primer cuadro tras la vuelta la fija de nuevo y la pieza
        sigue donde estaba.
        """
        estudio = self._estudio
        if estudio is None:
            self._ultima_mirada = ahora
            return
        transcurrido = ahora - self._ultima_mirada
        self._ultima_mirada = ahora
        if not ausente:
            self._pausado = False
            # El tramo se le pasa a la sesion de estudio, que decide que hacer con
            # el: en pausa del usuario no suma nada, durante la cuenta atras
            # descuenta la cuenta, y al final del bucle da la vuelta. Solo cuando
            # NO llegan cuadros, porque con audio el reloj lo mueve `procesar`
            # (ver ESPERA_SIN_CUADROS_S: colocarlo con audio entrando cuesta las
            # pulsaciones en vuelo).
            if self._sin_cuadros(ahora):
                estudio.avanzar(min(transcurrido, TECHO_TRAMO_S))
        elif not self._pausado:
            self._pausado = True
            estudio.colocar_en(self._instante)
        # El reloj de la sesion de estudio es la verdad, y esta clase lo adopta en
        # vez de llevar su propia cuenta: ella congela durante la cuenta atras y
        # da la vuelta al bucle. Sin esta linea el cabezal saltaba hacia delante
        # al acabar cada cuenta atras.
        self._instante = estudio.estado.carril.instante_s

    def _sin_cuadros(self, ahora: float) -> bool:
        """Si el seguidor lleva tanto sin recibir audio que se le puede mover el
        reloj a mano sin costarle una pulsacion. Ver `ESPERA_SIN_CUADROS_S`."""
        return (
            self._ultimo_cuadro is None or ahora - self._ultimo_cuadro >= ESPERA_SIN_CUADROS_S
        )

    def _instantanea(self) -> dict:
        """El estado publicable, construido entero bajo candado. NO mueve el reloj.

        Mover el reloj es cosa de `_mirar`, que corre justo antes y es el unico
        sitio que sabe cuanto tiempo ha pasado; aqui se lee lo que el estudio
        diga. Este metodo SI colocaba antes el reloj del seguidor, y dejo de
        hacerlo cuando el reloj de esta clase paso a ser el espejo del estudio:
        colocarlo aqui seria recolocar el cabezal en el sitio donde el estudio ya
        lo tiene, cancelandole la cuenta atras treinta veces por segundo.

        El estado sale de UNA sola lectura, asi que `instante_s`, `indice_actual`,
        `compas_en_curso` y `tocadas` siempre hablan del mismo instante.

        Las dos pausas viajan juntas y separadas: `en_pausa` -la del usuario- la
        trae el estudio dentro de `a_dict()`, y `pausado` -la falta de señal- la
        añade esta clase. El nucleo no sabe nada de cables, y la interfaz necesita
        poder decir "sin señal" en vez de fingir que la pieza va sola.

        `factor_sugerido` lo añade tambien esta clase, y por una razon parecida: el
        nucleo no lleva historial, y la sugerencia sale de el. Vale None cuando no
        hay nada que sugerir, que es casi siempre.
        """
        estudio = self._estudio
        if estudio is None:
            return {
                **_ESTUDIO_APAGADO.a_dict(),
                "pausado": False,
                "click_sonando": False,
                "factor_sugerido": None,
                "arranque": ARRANQUE_NINGUNO,
            }
        estado = estudio.estado
        self._cerrar_lo_que_termino(estado)
        self._ajustar_click(estado)
        return {
            **estado.a_dict(),
            "pausado": self._pausado,
            # Lo que SUENA y no lo que se pidio: sin salida de audio, o con un
            # tempo que el metronomo rechaza, el plan dice con_click y esto dice
            # False, para que la interfaz escriba "sin click" en vez de mostrar un
            # interruptor encendido que no hace nada.
            "click_sonando": self._metronomo is not None and self._metronomo.sonando,
            "factor_sugerido": self._factor_sugerido,
            "arranque": self._arranque,
        }

    def _cerrar_lo_que_termino(self, estado: EstadoEstudio) -> None:
        """Anota en el historial lo que acabo de cerrarse, y mueve el tempo si toca.

        Se llama BAJO candado, desde la instantanea, porque es ahi donde se ve el
        estado nuevo. Lo que mira son dos transiciones, y hacen falta las dos:

        - Cambio de `repeticion`: estudiando un bucle, la pregunta "ya te sale?"
          es sobre la vuelta que acaba de pasar, asi que cada vuelta es una
          pasada del historial.
        - `tramo_terminado` de False a True: sin bucle, la pasada acaba una vez.

        `cerrar_repeticion` devuelve el informe de SOLO esa vuelta, que es lo que
        se anota: anotar el acumulado contaria las vueltas anteriores otra vez.

        Y el tempo automatico se aplica SOLO con bucle. Sin bucle no se toca el
        plan: se publica la sugerencia en `factor_sugerido` y la interfaz la
        aplicara al empezar la pasada siguiente. La razon es que `cambiar_plan`
        recoloca el cabezal cuando el pulso cae fuera del tramo y limpia
        `tramo_terminado` -es su contrato, no un defecto-, asi que llamarlo con la
        pasada ya acabada arrancaba solo un bucle que nadie pidio: la pantalla
        decia "terminado" 33 ms, el cabezal se iba al principio y esa pasada
        fantasma no se anotaba nunca. Con bucle no hay nada de eso: la vuelta
        siguiente empieza ya y el cabezal lo esta recolocando el propio bucle.
        """
        estudio = self._estudio
        if estudio is None:
            return
        termino = estado.tramo_terminado and not self._termino_anunciado
        dio_la_vuelta = estado.repeticion != self._repeticion_anunciada
        if not termino and not dio_la_vuelta:
            return
        self._termino_anunciado = estado.tramo_terminado
        self._repeticion_anunciada = estado.repeticion
        # Al dar la vuelta, `_dar_la_vuelta` ya cerro la repeticion por dentro y
        # su informe se perdio: lo que se anota aqui es lo que el estudio tenga
        # cerrado. Por eso `SesionDeEstudio._dar_la_vuelta` guarda el informe de
        # la vuelta en `self._ultima_vuelta`, y aqui se lee.
        informe = estudio.ultima_vuelta if dio_la_vuelta else estudio.cerrar_repeticion()
        if informe is None:
            return
        self._historial.anotar(informe)
        if not estudio.plan.tempo_automatico:
            return
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

    def _ajustar_click(self, estado: EstadoEstudio) -> None:
        """Arranca, para o rearranca el click segun el plan y la señal. BAJO candado.

        Se llama desde la instantanea y NO desde `_observar`: `_observar` corre en
        el hilo de analisis, y `Metronomo.detener()` hace `join(timeout=1.0)`.
        Bloquear ahi hasta un segundo cegaria la deteccion de ataques, que es lo
        que explica el docstring de `Metronomo.pausar`. La instantanea la llama el
        hilo HTTP/WS a 30 Hz, donde esto puede costar tiempo sin romper nada.

        Rearranca en cada repeticion (`estado.repeticion`) por dos razones: la
        cuenta atras tiene que oirse desde su primer pulso, y el hilo del
        metronomo lleva su propio reloj con esperas de 60/tempo, asi que cada
        rearranque borra la deriva acumulada respecto al carril. Tambien rearranca
        si cambia el tempo (otro factor, a mano o automatico).

        Se pausa mientras falta la señal o el usuario tiene la pausa puesta, y se
        para del todo al acabar el tramo sin bucle. La pausa por señal es la de
        `SesionPractica._ajustar_metronomo`: un click marcando el compas con el
        cable desenchufado es lo contrario de lo que pide la spec.

        Coste de parar, medido: `_parar_click` corre bajo `_candado` y suma el
        `join` de `Metronomo.detener()` (menos de 1 ms, el hilo espera en un
        Event) y `SalidaAudio.cerrar()`, que toma el candado de escritura y espera
        al `stream.write()` en vuelo: con audio real es un click de unos 30 ms.
        Son decenas de ms, solo en transiciones (arrancar, vuelta, tempo, fin de
        tramo, detener) y acotados por la duracion del click, no por el timeout
        de un segundo. Pero `_observar` toma este mismo candado, asi que un hilo
        HTTP parado ahi dentro ciega la deteccion de ataques lo mismo que ajustar
        el click desde el observador, solo un salto mas alla. Si algun dia eso
        importa, la salida es quedarse el metronomo viejo en una variable local,
        soltar el candado y pararlo (y cerrar la salida) fuera de el.

        Un tempo que el metronomo no acepta -por encima de TEMPO_MAXIMO_PPM o
        menor que 1- deja la pasada sin click y en pie: tumbarla por el metronomo
        seria cambiar un lujo por lo esencial.
        """
        estudio = self._estudio
        pieza = self._pieza
        if estudio is None or pieza is None or not estudio.plan.con_click:
            self._parar_click()
            return
        # `and not estado.en_bucle` es DEFENSIVO: el nucleo solo pone
        # `tramo_terminado` en la rama sin bucle (con bucle da la vuelta), asi que
        # con bucle la condicion es inalcanzable hoy. Se queda para que un cambio
        # futuro del nucleo no pare el click de un bucle que sigue girando.
        if estado.tramo_terminado and not estado.en_bucle:
            # La pasada se acabo y no hay nada que marcar: el click seguiria solo
            # como ruido mientras el usuario mira el informe. Aqui si se detiene
            # del todo, porque no hace falta hasta la pasada siguiente, que al
            # empezar (`iniciar` o `saltar`) lo arranca de nuevo.
            self._parar_click()
            return
        tempo = round(pieza.tempo * estudio.plan.factor_tempo)
        clave = (tempo, estado.repeticion)
        if clave != self._clave_del_click:
            self._parar_click(cerrar_salida=False)
            self._clave_del_click = clave
            try:
                metronomo = Metronomo(tempo, pieza.compas[0], self._salida)
            except ValueError:
                # Se acaba de parar el click anterior sin cerrar la salida (para
                # no reabrirla cada vuelta): sin metronomo nuevo no se queda
                # abierta, que seria retener los altavoces sin usarlos.
                self._salida.cerrar()
                return
            # Abrir es idempotente. Si no se puede, el estado dice que no suena.
            if not self._salida.abrir() or not metronomo.iniciar():
                self._salida.cerrar()
                return
            self._metronomo = metronomo
        if self._metronomo is not None:
            # Se pausa si falta la señal (decide el servidor) o si el usuario
            # tiene el carril en pausa (`en_pausa`, la decide el): en los dos
            # casos la musica no avanza y un click marcando el compas sobra. Con
            # `pausar()` y no con `detener()`, para no pagar el `join` en cada
            # pulsacion del boton de pausa.
            if self._pausado or estado.en_pausa:
                self._metronomo.pausar()
            else:
                self._metronomo.reanudar()

    def _parar_click(self, cerrar_salida: bool = True) -> None:
        """Para el click y olvida el intento. Seguro de llamar sin click.

        La salida se cierra salvo al rearrancar en la vuelta siguiente, donde
        cerrarla y reabrirla cada compas seria gastar el dispositivo en balde.
        """
        if self._metronomo is not None:
            self._metronomo.detener()
        self._metronomo = None
        self._clave_del_click = None
        if cerrar_salida:
            self._salida.cerrar()

    def _estudio_o_falla(self) -> SesionDeEstudio:
        """La sesion de estudio en marcha, o el `ValueError` que sale como 400.

        Los cinco endpoints de la etapa 3c se piden sobre una pieza que suena, y
        pedirlos sin ninguna no es una rotura del servidor: es un pedido que llega
        tarde -el navegador que tiene la pantalla abierta y la pieza ya detenida-,
        asi que la respuesta es un 400 que lo dice. La excepcion unica evita que
        los cinco se inventen cada uno su mensaje.
        """
        estudio = self._estudio
        if estudio is None:
            raise ValueError("No hay ninguna pieza en marcha que practicar")
        return estudio

    def parchar_plan(self, cambios: dict) -> dict:
        """Aplica `cambios` ENCIMA del plan vigente, y lo que no diga se queda.

        Leer el plan, fusionarlo y cambiarlo ocurre bajo UNA sola toma del
        candado: con dos tomas, dos parches simultaneos (dos pestañas) leian el
        mismo plan viejo y el segundo revertia en silencio el cambio del primero.
        `cambios` ya viene convertido a sus tipos; `PlanDePasada` y
        `validar_plan` lanzan `ValueError` si el resultado es imposible.
        """
        with self._candado:
            estudio = self._estudio_o_falla()
            self._aplicar_plan(estudio, replace(estudio.plan, **cambios))
        return self.estado()

    def cambiar_plan(self, plan: PlanDePasada) -> dict:
        """Cambia el plan SIN reiniciar la pasada: lo tocado sigue contando."""
        with self._candado:
            self._aplicar_plan(self._estudio_o_falla(), plan)
        return self.estado()

    def _aplicar_plan(self, estudio: SesionDeEstudio, plan: PlanDePasada) -> None:
        """El cuerpo de `cambiar_plan`; quien lo llama ya tiene el candado."""
        # El reloj que devuelve el nucleo se adopta AQUI, y no se deja para la
        # mirada siguiente: si la señal ya se habia ido y nadie ha mirado
        # desde entonces, la primera mirada entra por la rama de la pausa y
        # coloca el cabezal en `self._instante`, que seria el de antes de esta
        # orden. Asi se perdia justo la primera accion del usuario tras un
        # apagon, que es el caso que la etapa 3a documenta como real.
        self._instante = estudio.cambiar_plan(plan).carril.instante_s
        # Un plan nuevo puesto a mano deja sin sentido la sugerencia anterior:
        # el historial la hizo sobre el plan que ya no esta.
        self._factor_sugerido = None

    def saltar(self, numero: int) -> dict:
        """Coloca el cabezal al principio de un compas DEL TRAMO.

        Un compas fuera del tramo lo rechaza el nucleo con `ValueError`, y sale
        como 400 igual que los demas: saltar fuera del tramo es cambiar el plan.
        """
        with self._candado:
            # El reloj que devuelve el nucleo se adopta aqui, por lo mismo que en
            # `cambiar_plan`: sin esto, un salto pedido con la señal ya perdida y
            # sin ninguna mirada por medio se quedaba en el sitio viejo.
            self._instante = self._estudio_o_falla().saltar_al_compas(
                numero
            ).carril.instante_s
            # Y la sugerencia se va con el salto, igual que `tramo_terminado` se
            # va dentro del nucleo: saltar es empezar a tocar otra vez, y la
            # sugerencia era sobre la pasada que acabo. Si se quedara puesta, el
            # usuario que la ignora y toca otra pasada que no mueve el factor
            # seguiria viendo ofrecido un cambio que el historial ya no dice:
            # `_cerrar_lo_que_termino` solo la escribe, nunca la borra, asi que
            # borrarla es de quien empieza la pasada nueva.
            self._factor_sugerido = None
        return self.estado()

    def pausa(self, activa: bool) -> dict:
        """Pausa a voluntad del usuario. Explicita y no un interruptor: dos clics
        seguidos desde dos pestañas no pueden dejar el carril en el estado
        contrario al que las dos pidieron.

        No es la pausa por falta de señal (`self._pausado`), que la decide esta
        clase mirando el audio: ni se mezclan ni se sobreescriben.
        """
        with self._candado:
            estudio = self._estudio_o_falla()
            estudio.pausar() if activa else estudio.reanudar()
        return self.estado()

    def informe(self) -> dict:
        """Lo tocado en esta pasada, y el historial de la pieza.

        Los dos juntos porque la pantalla los pide juntos: el informe dice como va
        esta vuelta y el historial, si vas mejor que ayer.
        """
        with self._candado:
            estudio = self._estudio_o_falla()
            return {
                "informe": estudio.informe.a_dict(),
                "historial": self._historial.a_dict(),
            }

    def _secciones_en_compases(self, pieza: Pieza) -> list[dict]:
        """Las secciones de la pieza, ya convertidas en rangos de compases.

        La conversion es del NUCLEO (`compases_de_la_seccion`) y viaja hecha: la
        interfaz no repite la formula. Es la misma regla que la etapa 2a aplico
        cuatro veces con el umbral de los cents, y aqui ademas el dia que el
        compas variable se arregle habria que arreglarlo en dos idiomas.
        """
        return [
            {
                "nombre": seccion.nombre,
                "primer_compas": compases_de_la_seccion(pieza, indice)[0],
                "ultimo_compas": compases_de_la_seccion(pieza, indice)[1],
            }
            for indice, seccion in enumerate(pieza.secciones)
        ]

    def pieza_en_marcha(self) -> dict:
        """La pieza que suena ahora, para quien recargo el navegador.

        `pieza` vale None sin nada en marcha, y NO es un error: el navegador que
        arranca de cero pregunta y se encuentra con que no hay nada, que es una
        respuesta.
        """
        pieza = self._pieza
        return {
            "pieza": None if pieza is None else pieza.a_dict(),
            "secciones_en_compases": (
                [] if pieza is None else self._secciones_en_compases(pieza)
            ),
            **self.estado(),
        }
