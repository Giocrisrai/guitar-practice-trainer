"""La sesion del carril: el cable, el click y el canal, sobre la politica del nucleo.

Reparto de trabajo con el nucleo, que es lo que explica todo lo demas:

- `SesionDeEstudio` (nucleo) envuelve al `SeguidorPieza`: sabe que nota toca
  ahora, a que nota de la pieza pertenece cada pulsacion, en que compas va el
  cabezal, cuando el bucle da la vuelta y que lleva anotado la pasada. Su reloj
  lo mueven los cuadros de audio, o el delta que le pasan.
- `ConductorDeEstudio` (nucleo, etapa 3d) lleva la POLITICA de la pasada: cuanto
  tiempo entra en la pieza por cada aviso, cuando se le congela el reloj al
  estudio, cuando se puede mover a mano sin costarle pulsaciones al seguidor, que
  se anota en el historial al cerrarse una vuelta y cuando sube el tempo. Vivia
  aqui hasta la etapa 3d, y se fue para que el gemelo digital pueda conducir ESTE
  codigo -el mismo que conduce el servidor- sin FastAPI por medio: `nucleo/` no
  importa de `servidor/`, asi que con la politica aqui el gemelo tendria que
  reimplementarla y acabaria dandose la razon a si mismo.
- Esta clase (servidor) es la dueña del RELOJ DE PARED, de la PAUSA POR FALTA DE
  SEÑAL como estado publicable, del CLICK y del canal. El reloj se inyecta para
  que las pruebas lo muevan a mano, y la pausa es cosa del servidor: el nucleo no
  sabe nada de cables.

Al conductor se le dan dos avisos y nada mas: `mirar(ahora, ausente)` cuando pasa
tiempo de pared y `observar(cuadro, instante)` cuando llega audio. El estado que
devuelve es lo que se publica.

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

from nucleo.piezas.compases import compases_de_la_seccion, pulsos_por_compas
# Las dos constantes del reloj y la politica que las usa viven en el nucleo desde
# la etapa 3d. Se importan -y con eso quedan reexportadas- para no romper a nadie
# que las lea donde estaban: `tests/test_sesion_carril.py` las pide de este
# modulo, y un cambio de domicilio no es motivo para tocar una prueba que vigila
# el comportamiento.
from nucleo.piezas.conductor import (  # noqa: F401  (reexportadas a proposito)
    ESPERA_SIN_CUADROS_S,
    TECHO_TRAMO_S,
    ConductorDeEstudio,
)
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
      LEE el reloj de pared y le dice al conductor que hora es; el conductor mide
      el tramo entre dos miradas, lo acota y se lo pasa a la sesion de estudio,
      que es quien decide que hacer con el: en pausa del usuario no suma nada,
      durante la cuenta atras la descuenta, y al final del tramo da la vuelta al
      bucle. Los tramos sin señal no se le pasan.
    - El del ANALISIS, que acompaña a cada cuadro de audio, llega al estudio tal
      cual (`procesar`), porque sus esperas estan medidas en el.

    `self._instante` NO es la cuenta de esta clase y hoy ya no es de nadie: es un
    espejo del reloj del conductor que se adopta tras cada aviso y que ningun
    codigo de produccion lee. Lo que se publica sale del `EstadoEstudio` que
    devuelve el conductor, no de aqui. Se queda porque su unico lector vivo es
    `tests/test_sesion_carril.py`, que lo usa para afirmar que la pausa por falta
    de señal deja el cabezal quieto, y porque es barato: una asignacion por aviso
    a cambio de que esa prueba pueda mirar el reloj desde fuera. Si algun dia
    estorba, lo que hay que hacer es cambiar esa prueba por una que lea el estado
    publicado, no borrar el campo por detras.

    En produccion los dos son `time.monotonic()`; el reloj se inyecta para que las
    pruebas lo muevan a mano, y debe ser monotonico.

    Candado: `SeguidorPieza` no lleva candado para sus dueños (el suyo protege su
    interior, pero quien lo comparta entre hilos tiene que ordenar los accesos).
    Aqui lo muta el hilo de analisis (`_observar`) y lo lee el hilo HTTP/WS a 30 Hz
    (`estado()`), asi que el candado de la pausa y el del espejo del reloj son de
    esta clase, y la instantanea se construye ENTERA debajo de el: en la etapa 2a
    se colo un fallo por leer dos campos sin candado y devolver un estado a
    medias. El conductor lleva ademas el suyo, reentrante, para su propio estado.

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
        # Quien lleva la POLITICA de la pasada, y vive en el nucleo desde la
        # etapa 3d: el reloj de la pieza, la vuelta del bucle, lo que se anota en
        # el historial y el tempo automatico. Esta clase le da de comer (los
        # cuadros, el reloj de pared y la falta de señal) y publica lo que
        # decide; lo que NO se fue es el click, el espejo del estado y todo lo
        # que toca FastAPI o el WebSocket.
        #
        # Sin pieza no hay conductor: se crea en `iniciar` y lo suelta `detener`,
        # igual que el estudio, porque conduce una pasada concreta.
        self._conductor: ConductorDeEstudio | None = None
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
        # Reentrante, y no por comodidad: el oyente que el conductor avisa al dar
        # la vuelta el bucle (`_ajustar_click_bajo_candado`) toma este candado el
        # mismo, y en el camino del WebSocket ese aviso llega con el ya tomado por
        # este hilo -`estado()` lo tiene cuando llama al conductor-. Con un `Lock`
        # pelado eso es un abrazo mortal consigo mismo.
        self._candado = threading.RLock()
        # Candado de arranque y parada, aparte del otro. Sin el, dos `iniciar()`
        # a la vez desde el hilo HTTP pueden registrar el observador dos veces y
        # `quitar_observador` solo quita uno, asi que quedaria un observador
        # huerfano alimentando al seguidor de una pieza ya muerta. Es RLock porque
        # `iniciar` llama a `detener` con el ya tomado.
        self._candado_arranque = threading.RLock()
        # El ESPEJO del reloj de la pieza y la pausa por falta de señal, las dos
        # bajo `_candado`. El reloj de verdad lo lleva el conductor -y antes de
        # el, la sesion de estudio-; esto se adopta tras cada aviso y no lo lee
        # nadie en produccion (ver el docstring de la clase).
        #
        # La pausa se queda aqui porque es un concepto del SERVIDOR: el nucleo no
        # sabe nada de cables y el conductor solo sabe que tiene el reloj
        # congelado. `pausado` es lo que la interfaz dibuja como "sin señal".
        self._instante = 0.0
        self._pausado = False

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
                # El conductor nace con la pasada, asi que las marcas del
                # detector de final y la sugerencia del tempo nacen limpias con
                # el: antes se reponian a mano aqui y en `detener`, y eran tres
                # lineas que habia que acordarse de repetir en los dos sitios.
                #
                # El click se engancha por aqui y no por dentro: el conductor
                # avisa de que la repeticion cambio -un dato- y esta clase decide
                # que eso significa rearrancar el metronomo. `_ajustar_click` se
                # sigue llamando ademas en cada instantanea, que es lo que cubre
                # lo demas (el tempo nuevo, la pausa, el fin del tramo) y lo que
                # hace que llamarlo dos veces en la vuelta no cueste nada: con la
                # misma clave no reabre nada.
                #
                # Y se engancha la version QUE TOMA EL CANDADO, porque el aviso
                # puede llegar de un hilo que no sea el del WebSocket: quien
                # conduzca el conductor directamente -el gemelo digital- avisa sin
                # ningun candado de este servidor por encima.
                self._conductor = ConductorDeEstudio(
                    self._estudio,
                    historial=self._historial,
                    al_cambiar_repeticion=self._ajustar_click_bajo_candado,
                )
                self._arranque += 1
                # NO cero: con un plan que empieza en el compas 5 el cabezal
                # arranca donde diga el estudio, que es quien sabe donde cae ese
                # compas en segundos de la pasada.
                self._instante = self._conductor.instante
                # El tramo de la primera mirada se cuenta desde que empieza la
                # pasada, y no desde un reloj monotonico que lleva horas andando.
                self._conductor.fijar_la_mirada(ahora)
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
                # Con el conductor se va todo lo que llevaba: el reloj, las
                # marcas del final y la sugerencia del tempo. El historial no,
                # que vive en `_historiales` por nombre de pieza.
                self._conductor = None
                self._pieza = None
                self._instante = 0.0
                self._pausado = False

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
            return self._instantanea(self._mirar(ahora, ausente))

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
        """Alimenta al conductor con un cuadro de analisis.

        Corre DENTRO del hilo de analisis, asi que aqui no se hace nada lento: se
        mueve el reloj bajo candado -el espejo del estado es de esta clase y lo
        lee el hilo HTTP-, se suelta, y el cuadro se le da al conductor fuera.

        Fuera de ESTE candado, no sin ninguno: el conductor lleva el suyo propio
        (reentrante) y lo toma todo lo que le entra, igual que `SesionDeEstudio`
        toma el suyo en `procesar`, `cambiar_plan`, `saltar_al_compas` y
        `cerrar_repeticion` desde el hilo HTTP. Lo que ESTE candado protege es lo
        de aqui: el espejo del reloj y la pausa por falta de señal, que los lee el
        hilo HTTP/WS a 30 Hz.

        Antes aqui se decia que `procesar` corria "con el candado del propio
        seguidor", y eso seguia siendo cierto DEL SEGUIDOR pero dejo de ser
        suficiente: la etapa 3c le anadio a la sesion de estudio media docena de
        campos mutables (la cuenta atras, el tramo terminado, el acumulado, las
        vueltas cerradas y el propio seguidor, que `cambiar_plan` reemplaza) que
        ese candado no protege. La 3d anade los del conductor -el espejo de su
        reloj, las marcas del final, la mirada y el ultimo cuadro-, y por eso el
        conductor tiene candado y no se conforma con el del estudio.

        Lo que decide con el cuadro -si hay que congelarle el reloj al estudio
        tras un hueco de audio, si el cuadro llega durante la pausa- es politica y
        esta en `ConductorDeEstudio.observar`, con los comentarios que explican
        cada linea. Aqui solo queda lo que es del servidor: el reloj de pared, la
        falta de señal y el espejo que publica el WebSocket.
        """
        ahora = self._reloj()
        ausente = self._sin_senal()
        with self._candado:
            conductor = self._conductor
            if conductor is None:
                return
            # Solo la primera mitad de la mirada: mover el reloj. Cerrar las
            # vueltas se queda para `estado()`, porque el cierre acaba avisando al
            # click y `Metronomo.detener()` hace `join(timeout=1.0)`: bloquear
            # hasta un segundo aqui cegaria la deteccion de ataques.
            conductor.mover_el_reloj(ahora, ausente)
            self._pausado = ausente
            self._instante = conductor.instante
        conductor.observar(resultado, instante_analisis)

    def _mirar(self, ahora: float, ausente: bool) -> EstadoEstudio | None:
        """Le pasa al conductor el tiempo y la señal, y adopta lo que decida.

        Devuelve el estado que hay que publicar -el leido tras mover el reloj- o
        None sin pieza. Lo que hace con el tramo transcurrido, con el techo y con
        la vuelta del bucle esta en `ConductorDeEstudio`, que es donde esos
        comentarios viven desde la etapa 3d.

        Lo que queda aqui son las dos cosas que no son del nucleo: `_pausado`, que
        es la falta de señal como estado publicable -el nucleo no sabe nada de
        cables, y esto si lo lee la instantanea-, y `_instante`, que es un espejo
        del reloj del conductor que hoy solo lee una prueba (ver el docstring de
        la clase). El reloj de verdad es el del conductor; esto lo copia.
        """
        conductor = self._conductor
        if conductor is None:
            return None
        estado = conductor.mirar(ahora, ausente)
        self._pausado = ausente
        self._instante = conductor.instante
        return estado

    def _instantanea(self, estado: EstadoEstudio | None) -> dict:
        """El estado publicable, construido entero bajo candado. NO mueve el reloj.

        Mover el reloj es cosa del conductor, que corre justo antes en `_mirar` y
        es el unico que sabe cuanto tiempo ha pasado; aqui se publica el estado
        que de ahi sale. Este metodo SI colocaba antes el reloj del seguidor, y
        dejo de hacerlo cuando el reloj de esta clase paso a ser el espejo del
        estudio: colocarlo aqui seria recolocar el cabezal en el sitio donde el
        estudio ya lo tiene, cancelandole la cuenta atras treinta veces por
        segundo.

        El estado llega como parametro y NO se vuelve a leer, que es lo que lo
        mantiene siendo una sola lectura: `_mirar` lo leyo tras mover el reloj y
        antes de que el conductor cerrara lo que hubiera terminado, asi que es la
        foto de ESTE instante y no la del siguiente (cerrar una vuelta con el
        tempo automatico puesto puede cambiar el plan).

        El estado sale de UNA sola lectura, asi que `instante_s`, `indice_actual`,
        `compas_en_curso` y `tocadas` siempre hablan del mismo instante.

        Las dos pausas viajan juntas y separadas: `en_pausa` -la del usuario- la
        trae el estudio dentro de `a_dict()`, y `pausado` -la falta de señal- la
        añade esta clase. El nucleo no sabe nada de cables, y la interfaz necesita
        poder decir "sin señal" en vez de fingir que la pieza va sola.

        `factor_sugerido` lo trae el conductor, que es quien lleva el historial y
        quien decide cuando hay algo que sugerir. Viaja en el estado porque lo
        aplica la interfaz al empezar la pasada siguiente. Vale None cuando no hay
        nada que sugerir, que es casi siempre.
        """
        if estado is None:
            return {
                **_ESTUDIO_APAGADO.a_dict(),
                "pausado": False,
                "click_sonando": False,
                "factor_sugerido": None,
                "arranque": ARRANQUE_NINGUNO,
            }
        # El click se ajusta en CADA instantanea y no solo en la vuelta: aqui se
        # atiende el tempo nuevo, la pausa y el fin del tramo. La vuelta la avisa
        # ademas el conductor (`al_cambiar_repeticion`), y que se solapen no
        # cuesta nada: con la misma clave este metodo no reabre nada.
        self._ajustar_click(estado)
        return {
            **estado.a_dict(),
            "pausado": self._pausado,
            # Lo que SUENA y no lo que se pidio: sin salida de audio, o con un
            # tempo que el metronomo rechaza, el plan dice con_click y esto dice
            # False, para que la interfaz escriba "sin click" en vez de mostrar un
            # interruptor encendido que no hace nada.
            "click_sonando": self._metronomo is not None and self._metronomo.sonando,
            "factor_sugerido": self._conductor.factor_sugerido,
            "arranque": self._arranque,
        }

    def _ajustar_click_bajo_candado(self, estado: EstadoEstudio) -> None:
        """El oyente que el conductor avisa al dar la vuelta el bucle.

        Existe para no depender de quien llame. El conductor avisa SIN su candado
        -tiene que ser asi: si avisara con el tomado y este metodo tomara el de
        aqui, los dos candados se tomarian en ordenes distintos segun el hilo y se
        plantaria el servidor-, asi que la exclusion de `_ajustar_click` la toma
        este metodo y no se hereda de nadie. `_metronomo`, `_clave_del_click` y
        `_pausado` son de esta clase y se tocan aqui dentro.

        Por el camino del WebSocket el candado ya esta tomado por este mismo hilo
        (`estado()` lo tiene cuando llama al conductor) y por eso es reentrante.
        Por el camino de quien conduzca el conductor a mano -el gemelo digital, en
        otro hilo y sin ningun candado de servidor- se toma aqui, que es el unico
        sitio donde se puede saber que hace falta.
        """
        with self._candado:
            self._ajustar_click(estado)

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
                metronomo = Metronomo(tempo, self._periodo_del_acento(pieza), self._salida)
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

    @staticmethod
    def _periodo_del_acento(pieza: Pieza) -> int:
        """Cada cuantos clicks acentua el metronomo en esta pieza.

        El `Metronomo` emite un click cada `60/tempo` segundos -o sea, un click
        por PULSO- y acentua cada `compas` clicks. Asi que el periodo del acento
        se mide en PULSOS DEL MODELO, que es la negra: `pulsos_por_compas` lo
        convierte con `num*4/den`.

        La spec §5 decia literalmente `compas = pieza.compas[0]`, y la
        implementacion la copio. Acierta en 4/4 y en 3/4, donde el numerador y los
        pulsos coinciden, y falla en todo lo demas: en 6/8 el compas son 3 negras
        y acentuaba cada 6, y en 7/8 son 3,5 y acentuaba cada 7, de modo que el
        acento caia cada dos compases y nunca sobre la misma nota. Dentro de la
        propia etapa las dos cuentas se contradecian, porque
        `SesionDeEstudio._segundos_de_cuenta_atras` si usa `pulsos_por_compas`.

        Se redondea porque el metronomo cuenta clicks enteros: en 7/8 el acento va
        cada 4 pulsos (3,5 redondeado), que es lo mas cerca que se puede estar del
        compas con un click por negra. Suelo en 1 para que una pieza con un compas
        raro no le pida al metronomo un periodo de 0.
        """
        return max(1, round(pulsos_por_compas(pieza)))

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
            self._aplicar_plan(replace(estudio.plan, **cambios))
        return self.estado()

    def cambiar_plan(self, plan: PlanDePasada) -> dict:
        """Cambia el plan SIN reiniciar la pasada: lo tocado sigue contando."""
        with self._candado:
            self._estudio_o_falla()
            self._aplicar_plan(plan)
        return self.estado()

    def _aplicar_plan(self, plan: PlanDePasada) -> None:
        """El cuerpo de `cambiar_plan`; quien lo llama ya tiene el candado.

        El plan nuevo se lo pide al conductor y no al estudio directamente:
        adoptar el reloj que devuelve el nucleo y borrar la sugerencia del
        historial son dos decisiones de la politica, y viven con ella.
        """
        self._instante = self._conductor.cambiar_plan(plan).carril.instante_s

    def saltar(self, numero: int) -> dict:
        """Coloca el cabezal al principio de un compas DEL TRAMO.

        Un compas fuera del tramo lo rechaza el nucleo con `ValueError`, y sale
        como 400 igual que los demas: saltar fuera del tramo es cambiar el plan.
        """
        with self._candado:
            self._estudio_o_falla()
            # El salto va por el conductor por lo mismo que el plan: adoptar el
            # reloj que devuelve el nucleo y borrar la sugerencia del historial
            # son de la politica, y los dos comentarios que lo explican se fueron
            # con ella a `ConductorDeEstudio.saltar_al_compas`.
            self._instante = self._conductor.saltar_al_compas(numero).carril.instante_s
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
