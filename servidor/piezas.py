"""La sesion del carril: lleva el reloj de la pieza y le da de comer al seguidor.

Reparto de trabajo con el nucleo, que es lo que explica todo lo demas:

- `SeguidorPieza` (nucleo) sabe que nota toca ahora y a que nota de la pieza
  pertenece cada pulsacion. Su reloj lo mueven los cuadros de audio.
- Esta clase (servidor) es la dueña del RELOJ y de la PAUSA. El reloj se inyecta
  para que las pruebas lo muevan a mano, y la pausa -por falta de señal- es cosa
  del servidor: el seguidor no sabe nada de cables.

Es la hermana de `SesionPractica` (`servidor/ejercicios.py`) y copia su forma: se
suscribe al flujo de analisis como observadora en vez de muestrearlo, protege con
un candado la instantanea que lee el hilo HTTP, y no hace nada lento dentro del
observador.
"""

import threading
import time
from typing import Callable

from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.piezas.modelo import Pieza
from nucleo.piezas.seguimiento import EstadoCarril, SeguidorPieza
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
ESPERA_SIN_CUADROS_S = VENTANA_ATAQUE_COMO_ONSET_S

# El perfil que se da por activo cuando la sesion de audio no dice cual es (ver
# `SesionCarril._perfil_activo`). Es el mismo que trae la configuracion recien
# hecha, para no tener dos respuestas distintas a la misma pregunta.
PERFIL_POR_DEFECTO = Configuracion().perfil

# Lo que publica un carril sin pieza: las mismas claves que con pieza, para que el
# WebSocket y la interfaz no tengan que distinguir dos formas de estado.
_CARRIL_APAGADO = EstadoCarril(
    instante_s=0.0, indice_actual=0, total=0, completado=False, tocadas=()
)


class SesionCarril:
    """Propietaria de la pieza en curso, de su seguidor y del reloj que la mueve.

    Dos relojes, como en el seguidor, y aqui tampoco se pueden mezclar:

    - El de la PIEZA, en segundos desde su comienzo, es lo que publica
      `estado()["instante_s"]`. Lo lleva esta clase sumando el tiempo
      transcurrido entre dos miradas, y NO suma los tramos sin señal.
    - El del ANALISIS, que acompaña a cada cuadro de audio, se le pasa al
      seguidor tal cual (`procesar`), porque sus esperas estan medidas en el.

    En produccion los dos son `time.monotonic()`; el reloj se inyecta para que las
    pruebas lo muevan a mano, y debe ser monotonico.

    Candado: `SeguidorPieza` no lleva candado para sus dueños (el suyo protege su
    interior, pero quien lo comparta entre hilos tiene que ordenar los accesos).
    Aqui lo muta el hilo de analisis (`_observar`) y lo lee el hilo HTTP/WS a 30 Hz
    (`estado()`), asi que el candado de la pausa y el del reloj son de esta clase,
    y la instantanea se construye ENTERA debajo de el: en la etapa 2a se colo un
    fallo por leer dos campos sin candado y devolver un estado a medias.

    Frontera con la sesion de audio: solo tres miembros, `senal_ausente`,
    `registrar_observador` y `quitar_observador`. Nada mas. Es una frontera
    estrecha a proposito: asi una prueba puede darle un doble de tres lineas en
    vez de obligar a `Sesion` a llevar un interruptor que solo sirva para los
    tests.
    """

    def __init__(
        self,
        sesion_audio,
        reloj: Callable[[], float] = time.monotonic,
        perfil_activo: Callable[[], str] | None = None,
    ) -> None:
        self._sesion_audio = sesion_audio
        self._reloj = reloj
        self._perfil_activo_inyectado = perfil_activo
        self._pieza: Pieza | None = None
        self._seguidor: SeguidorPieza | None = None
        self._candado = threading.Lock()
        # Reloj de la pieza y contabilidad de la pausa. Todo bajo `_candado`.
        self._instante = 0.0
        self._ultima_mirada = reloj()
        self._pausado = False
        # Cuando llego el ultimo cuadro AL SEGUIDOR, en el reloj de esta clase.
        # None es "ninguno todavia". Ver `ESPERA_SIN_CUADROS_S`.
        self._ultimo_cuadro: float | None = None

    @property
    def activa(self) -> bool:
        return self._seguidor is not None

    @property
    def pieza(self) -> Pieza | None:
        return self._pieza

    def iniciar(self, pieza: Pieza) -> dict:
        """Arranca una pieza. Devuelve la pieza ENTERA mas el estado inicial.

        La pieza se devuelve aqui y una sola vez: `estado()` no la repite, porque
        lo llama el WebSocket 30 veces por segundo y mandar cientos de notas que
        no cambian seria tirar el canal.

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
        self.detener()
        ahora = self._reloj()
        with self._candado:
            self._pieza = pieza
            self._seguidor = SeguidorPieza(pieza)
            self._instante = 0.0
            self._ultima_mirada = ahora
            self._ultimo_cuadro = None
            self._pausado = False
        # El observador se registra AL FINAL, con el seguidor ya en su sitio: si se
        # registrara antes, el primer cuadro podria entrar con `_seguidor` a None y
        # el audio de ese instante se perderia sin que nada lo dijera.
        self._sesion_audio.registrar_observador(self._observar)
        return {"pieza": pieza.a_dict(), **self.estado()}

    def detener(self) -> None:
        """Para el carril y suelta la pieza. Seguro de llamar varias veces.

        El observador se quita PRIMERO, igual que en `SesionPractica`: asi ningun
        cuadro posterior puede alimentar al seguidor que las lineas siguientes
        estan soltando.
        """
        self._sesion_audio.quitar_observador(self._observar)
        with self._candado:
            self._seguidor = None
            self._pieza = None
            self._instante = 0.0
            self._ultima_mirada = self._reloj()
            self._ultimo_cuadro = None
            self._pausado = False

    def estado(self) -> dict:
        """Instantanea para la interfaz: el `EstadoCarril` mas `pausado`.

        Mueve el reloj aqui, ademas de en `_observar`, y por la misma razon que
        `SesionPractica.estado()` ajusta ahi el metronomo: los dos sitios cubren
        mitades distintas del problema. `_observar` solo corre cuando llega audio,
        y el caso que hay que atender es precisamente que deje de llegar: al
        desaparecer el dispositivo, la sesion de audio publica un unico resultado
        de silencio y entra en el ciclo de reintento sin publicar nada mas, asi que
        el observador no vuelve a correr NUNCA. Este metodo, en cambio, lo llama el
        WebSocket a 30 Hz, y es la mitad que sigue viva.

        `pausado` lo añade el servidor y no el nucleo: el seguidor no sabe nada de
        cables, y la interfaz necesita poder decir "sin señal" en vez de fingir
        que la pieza va sola.
        """
        ahora = self._reloj()
        # Fuera del candado: en la sesion de verdad es una propiedad que mira su
        # historial de niveles, y no hay motivo para hacerla esperar a nadie.
        ausente = bool(self._sesion_audio.senal_ausente)
        with self._candado:
            self._mirar(ahora, ausente)
            return self._instantanea(ahora)

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
        """Alimenta al seguidor con un cuadro de analisis.

        Corre DENTRO del hilo de analisis, asi que aqui no se hace nada lento: se
        mueve el reloj bajo candado, se suelta, y `procesar` -que es el trabajo de
        verdad- corre fuera, con el candado del propio seguidor.

        Mientras el carril esta pausado el cuadro NO llega al seguidor. No es un
        detalle: con el cable enchufado y callado los cuadros de silencio siguen
        llegando, y `procesar` mueve el reloj del seguidor con cada uno, asi que
        alimentarlo durante la pausa dejaria el carril corriendo igual que si no
        hubiera pausa.
        """
        ahora = self._reloj()
        ausente = bool(self._sesion_audio.senal_ausente)
        with self._candado:
            self._mirar(ahora, ausente)
            seguidor = self._seguidor
            if seguidor is None or self._pausado:
                return
            self._ultimo_cuadro = ahora
        seguidor.procesar(resultado, instante_analisis)

    def _mirar(self, ahora: float, ausente: bool) -> None:
        """Mueve el reloj de la pieza y ajusta la pausa. Se llama BAJO candado.

        El reloj se lleva sumando lo transcurrido entre dos miradas, y el tramo
        cuenta solo si en esta mirada HAY señal. Dicho de otro modo: el tiempo sin
        señal no entra en la pieza, que es lo que pide la spec §5 (un carril que
        corre con el cable desenchufado te hace fallar notas que nunca sonaron).

        Atribuir el tramo a la lectura NUEVA y no a la vieja es deliberado: la
        señal se va y vuelve entre dos miradas, y nadie sabe en que punto exacto.
        Con miradas cada 33 ms como maximo (el WebSocket, y mas a menudo cuando
        entra audio), el error es de una mirada, y se equivoca del lado bueno: al
        perder la señal no se cuenta tiempo que el alumno no oyo, y al volver no
        se pierde tiempo que ya estaba sonando.

        Al pausar se le congela tambien el reloj al seguidor (`avanzar_a`), que es
        lo que hace segura la pausa: `avanzar_a` invalida las pulsaciones en vuelo
        -las tocadas en el tramo que se acaba de abandonar- y deja la
        correspondencia entre relojes sin fijar, de modo que el primer cuadro tras
        la vuelta la fija de nuevo y la pieza sigue donde estaba.
        """
        seguidor = self._seguidor
        if seguidor is None:
            self._ultima_mirada = ahora
            return
        transcurrido = ahora - self._ultima_mirada
        self._ultima_mirada = ahora
        if not ausente:
            self._pausado = False
            self._instante += transcurrido
        elif not self._pausado:
            self._pausado = True
            seguidor.avanzar_a(self._instante)

    def _instantanea(self, ahora: float) -> dict:
        """El estado publicable, construido entero bajo candado.

        Cuando hace rato que no llega un cuadro, el reloj del seguidor no avanza
        solo y hay que moverselo (`avanzar_a`); cuando esta llegando audio, el
        seguidor ya lo lleva y no se le toca, porque `avanzar_a` le costaria las
        pulsaciones en vuelo (ver `ESPERA_SIN_CUADROS_S`). En los dos casos el
        estado sale de UNA sola llamada al seguidor, asi que `instante_s`,
        `indice_actual` y `tocadas` siempre hablan del mismo instante.
        """
        seguidor = self._seguidor
        if seguidor is None:
            return {**_CARRIL_APAGADO.a_dict(), "pausado": False}
        sin_cuadros = (
            self._ultimo_cuadro is None or ahora - self._ultimo_cuadro >= ESPERA_SIN_CUADROS_S
        )
        estado = seguidor.avanzar_a(self._instante) if sin_cuadros else seguidor.estado
        return {**estado.a_dict(), "pausado": self._pausado}
