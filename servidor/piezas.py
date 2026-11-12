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

import logging
import threading
import time
from dataclasses import replace
from typing import Callable

from nucleo.acompanamiento import PiezaRenderizada, renderizar
from nucleo.acompanante import Acompanante, BloqueadoAhora
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
from nucleo.piezas.voces_de_fondo import FondoDisponible, NotaDeFondo, VozDeFondo
from nucleo.sintesis import Metronomo, SalidaAudio
from servidor.configuracion import Configuracion

_registro = logging.getLogger(__name__)

# El perfil que se da por activo cuando la sesion de audio no dice cual es (ver
# `SesionCarril._perfil_activo`). Es el mismo que trae la configuracion recien
# hecha, para no tener dos respuestas distintas a la misma pregunta.
PERFIL_POR_DEFECTO = Configuracion().perfil

# El umbral de ruido que se da por bueno cuando la sesion de audio no lleva
# configuracion (un doble de prueba, u otro flujo de audio). Mismo motivo y misma
# fuente que `PERFIL_POR_DEFECTO`: la configuracion no es parte de la frontera de
# tres miembros que esta clase le exige a su sesion de audio.
UMBRAL_DE_RUIDO_POR_DEFECTO_DBFS = Configuracion().umbral_ruido_dbfs

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


def se_esperan_notas(
    estado: EstadoEstudio | None, sin_senal: bool, hubo_senal_en_la_pasada: bool
) -> bool:
    """**LA REGLA DEL AVISO DEL CABLE, DECIDIDA UNA VEZ Y EN UN SOLO SITIO.**

    Contesta una sola pregunta: *si el silencio de ahora mismo puede ser una
    averia del montaje*. De ella cuelgan las DOS mitades del mismo aviso -el
    `sin_senal` de `/api/diagnostico` y la linea naranja del carril en la
    pantalla-, y por eso vive aqui y viaja PUBLICADA en el estado
    (`esperando_notas`): estaba escrita dos veces, en dos idiomas, las dos no eran
    la misma, y un comentario del JSX afirmaba que si. Cada mitad tenia su mutante
    y cada mutante moria en su propio idioma, lo que daba la sensacion de estar
    cubierto.

    Los cuatro casos:

    - **Sin pasada en marcha, SI se esperan notas.** El usuario puede estar en el
      afinador peleandose con el jack, y ahi callarse esconderia el unico aviso
      que le explicaria por que no ve nada.
    - **Con la pieza o el tramo terminados, no.** El silencio es el final: el
      usuario acabo y dejo de tocar. Es el defecto que se arreglo primero -«sube
      el volumen de la guitarra» en cuanto la pasada acababa-.
    - **Con el carril congelado por falta de señal DESPUES de haber recibido señal
      en esta pasada, no.** Es el defecto que el revisor midio en `--bucle 2-2
      --repeticiones 2`: un tramo en bucle no publica `completado` ni
      `tramo_terminado` NUNCA -el bucle no se acaba, es su proposito-, asi que la
      regla anterior no mordia y la pantalla acusaba al cable de que el usuario
      descansara la mano entre repeticiones, que es como se practica un compas.
      Si el cable entrego señal hace un momento, «sube el volumen de la guitarra»
      es falso, y un aviso falso justo cuando mas se ve es un aviso que el usuario
      deja de leer.
    - **En cualquier otro caso, si**, y ahi esta el caso legitimo entero: la pasada
      corriendo y el cable sin entregar una sola muestra -volumen a cero, jack
      flojo- sigue avisando, en marcha o en pausa.

    **LA PAUSA DEL USUARIO NO CALLA NADA**, y callarla era el otro defecto: quien
    pausa porque no le marca nada es exactamente quien necesita leer que no llega
    señal. Es el mismo argumento del afinador, y la linea naranja del carril ya
    salia en pausa, asi que las dos mitades decian lo contrario a la vez.

    Se distingue por ESTADO y no por un temporizador: «lleva un rato callado» es
    verdad en todos los casos, asi que el tiempo no los separa.
    """
    if estado is None:
        return True
    if estado.tramo_terminado or estado.carril.completado:
        return False
    return not (sin_senal and hubo_senal_en_la_pasada)


# El volumen del fondo recien cargado, entre 0 y 1. Por debajo de lo que toca el
# usuario a proposito: el fondo acompaña, y si tapa a la guitarra el alumno deja
# de oirse los fallos, que es para lo que esta practicando.
VOLUMEN_DEL_FONDO_POR_OMISION = 0.6

# Cuanto se baja el fondo cuando lo que suena es la parte del PROPIO usuario,
# porque el archivo no traia ninguna otra voz. Es la mitad, y la mitad porque lo
# que se oye entonces no es un acompañamiento sino una guia: a volumen de
# acompañamiento, el alumno no distingue su guitarra de la grabacion y cree que
# toca limpio lo que esta tocando la maquina.
GANANCIA_DE_TU_PARTE = 0.5


def acompanamiento_posible(hay_fondo: bool, entrada_es_el_cable: bool) -> bool:
    """Si encender la pieza de fondo tiene sentido ahora mismo. UN SOLO SITIO.

    Dos condiciones, y las dos son necesarias:

    - **Hay fondo cargado** (`SesionCarril.cargar_acompanamiento`). Sin archivo
      no hay nada que sonar y el interruptor no haria nada.
    - **La entrada es el cable** (`Sesion.entrada_es_el_cable`, que es donde esa
      regla se decide y el unico sitio que llama a `buscar_rocksmith`). Con un
      microfono abierto el fondo vuelve a entrar por el, el detector ve la suma
      del fondo y del alumno, y el informe de la pasada deja de medir al alumno.

    **No es una compuerta: es un recordatorio publicado.** Encender el
    acompañamiento con el microfono lo hace sonar igual -manda el usuario, que
    puede tener auriculares puestos y saber perfectamente lo que hace- y el
    estado sigue diciendo `acompanamiento_posible: False`, de modo que el aviso
    no se va. Convertirlo en compuerta seria discutirle al usuario el uso de sus
    propios altavoces; callar el aviso seria dejarle creer que su informe mide lo
    que toca.

    Vive aqui y viaja PUBLICADA (`EstadoEstudio.acompanamiento_posible`) por lo
    mismo que `se_esperan_notas`: la pantalla, el endpoint y lo que venga despues
    leen el campo en vez de rehacer la cuenta, porque la misma regla escrita dos
    veces nunca es la misma regla.
    """
    return hay_fondo and entrada_es_el_cable


def acompanamiento_debe_sonar(
    encendido: bool, lo_encendio_el_usuario: bool, entrada_es_el_cable: bool
) -> bool:
    """**EL PESTILLO DE M6, y se mira en CADA instantanea, no una sola vez.**

    Quien encendio el fondo decide si la entrada puede volver a apagarlo, y esa
    es toda la regla:

    - **Lo encendio `cargar_acompanamiento`** -automaticamente, porque en ese
      momento habia cable-. Esa decision no la tomo nadie: la tomo el programa
      porque se daban las condiciones, asi que **sigue a las condiciones**. Si
      la entrada deja de ser el cable, el fondo se calla.
    - **Lo encendio el usuario a mano** (`acompanamiento(encendido=True)`). Su
      decision manda y persiste aunque la entrada sea un microfono: es su
      equipo, puede tener auriculares puestos y ya vio el aviso -que sigue
      publicado mientras suene, porque `acompanamiento_posible` no se mueve-.

    **Por que no basta con mirarlo al cargar**, que es lo que se hacia y lo que
    un revisor reprodujo: el usuario carga con el cable y el fondo suena; luego
    **elige el microfono del portatil en el selector**, la sesion de audio
    reabre la captura, `entrada_es_el_cable` pasa a False... y el fondo seguia
    sonando encima de una entrada que lo recoge. El detector cobra ese sonido
    como notas del usuario y el informe se llena de aciertos que no toco nadie,
    sin que se note. Era el anti-objetivo de la etapa ocurriendo en vivo a
    mitad de pasada, y el pestillo de una sola lectura solo tapaba el arranque.

    Al ser una compuerta VIVA y no un estado que se escriba, tambien desaparece
    la ventana estrecha del arranque: si la entrada cambia entre el `cargar` y
    la primera instantanea, el fondo no llega a empezar.
    """
    return encendido and (lo_encendio_el_usuario or entrada_es_el_cable)


def cabezal_del_fondo(estado: EstadoEstudio | None) -> float | None:
    """El instante EN PULSOS que el fondo debe estar sonando, o None si nada.

    Es el contrato de `Acompanante.iniciar(cabezal)` visto desde el carril, y el
    unico sitio donde se decide que es «ahora no suena nada»:

    - **Sin pasada**, nada que sonar.
    - **Durante la cuenta atras**, tampoco: la cuenta esta para que el alumno
      entre a tiempo, y un fondo tocando el compas 1 mientras el click cuenta
      cuatro le haria entrar encima de la nota, no antes de ella. El cabezal del
      carril ya esta en el pulso de salida durante toda la cuenta, asi que no
      basta con leerlo: hay que mirar la cuenta.
    - **Con el tramo o la pieza terminados**, tampoco. Los dos motivos, igual que
      en `se_esperan_notas`: una pieza cuyas notas acaban antes de su barra de
      compas termina por `carril.completado` y el reloj sigue andando hasta el
      final del tramo.
    - **En cualquier otro caso**, el instante en pulsos, tal cual lo publica el
      nucleo. En pulsos y no en segundos porque el factor de tempo ya esta
      aplicado en los dos lados -el render se hace con el factor- y los pulsos
      son lo unico que significa lo mismo en la pieza y en la pasada.

    La pausa NO sale aqui: el que pausa es `_ajustar_acompanamiento`, con
    `Acompanante.pausar()`, igual que el click. Devolver None en pausa
    desvaneceria el fondo a silencio tras cuatro bloques y lo volveria a meter
    con una rampa al reanudar, que es mas trabajo para el mismo resultado peor.
    """
    if estado is None:
        return None
    if estado.cuenta_atras_restante_s > 0.0:
        return None
    if estado.tramo_terminado or estado.carril.completado:
        return None
    return estado.instante_pulsos


def voz_de_tu_parte(pieza: Pieza) -> VozDeFondo:
    """La pieza del carril convertida en voz de fondo, para cuando no hay otra.

    Un archivo de una sola pista -una tablatura de texto, un MIDI de un solo
    instrumento- no tiene ninguna voz que el usuario no toque, asi que
    `FondoDisponible.voces` viene vacio. Sonar su propia parte a media ganancia
    sigue sirviendo -es la guia con la que se aprende una melodia nueva- siempre
    que se DIGA, que es para lo que existe `acompanamiento_es_tu_parte`.

    Se tira la digitacion y se queda la altura: es exactamente lo que
    `nucleo.piezas.voces_de_fondo` hace con las pistas del archivo, porque para
    sonar no hay que digitar nada.
    """
    return VozDeFondo(
        nombre=pieza.nombre,
        instrumento="Tu parte",
        notas=tuple(
            NotaDeFondo(
                midi=float(nota.midi),
                inicio_pulsos=nota.inicio_pulsos,
                duracion_pulsos=nota.duracion_pulsos,
            )
            for nota in pieza.notas
        ),
    )


def _volumen_valido(volumen: float) -> float:
    """El volumen del fondo, comprobado. `ValueError` sale como 400.

    Se rechaza en vez de recortarse porque quien lo manda es un deslizador de la
    pantalla: un valor fuera de rango es un defecto de quien llama, y recortarlo
    en silencio lo deja vivo.
    """
    volumen = float(volumen)
    if not 0.0 <= volumen <= 1.0:
        raise ValueError(
            f"El volumen del acompanamiento va de 0 a 1, y pediste {volumen}"
        )
    return volumen


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
        salida_fondo: SalidaAudio | None = None,
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
        # **La salida del acompañamiento es PROPIA, no la del click**, y no es
        # una comodidad: `_parar_click` llama a `self._salida.cerrar()` SIN
        # condiciones, y con `con_click` apagado eso ocurre en cada instantanea,
        # treinta veces por segundo. Hoy es inocuo porque el stream ya esta en
        # None; compartiendo la salida seria cerrarle el stream al
        # acompañamiento treinta veces por segundo, o sea un fondo que no suena.
        # Dos streams sobre el mismo dispositivo es justo lo que PortAudio sabe
        # hacer, y el precio -un `abrir()` mas- se paga una vez por pasada.
        self._salida_fondo = salida_fondo or SalidaAudio()
        self._acompanante: Acompanante | None = None
        # El archivo de fondo cargado por su puerta (`cargar_acompanamiento`), o
        # None si nadie llamo. Mientras sea None el carril corre exactamente como
        # antes de esta etapa.
        self._fondo: FondoDisponible | None = None
        # El interruptor y el volumen VIVOS, que no viven en `PlanDePasada` a
        # proposito: todo cambio de plan hace `cerrar_repeticion(cuenta_como_
        # vuelta=False)`, asi que un deslizador de volumen arrastrado serian
        # decenas de cierres de repeticion y encender el fondo a mitad de pasada
        # cortaria la vuelta por la mitad. Ni el volumen ni el interruptor
        # cambian la PASADA; cambian lo que sale por los altavoces.
        self._fondo_encendido = False
        # Y QUIEN lo encendio, que es lo que decide si la entrada puede volver a
        # apagarlo: ver `acompanamiento_debe_sonar`. El encendido automatico de
        # `cargar_acompanamiento` sigue a la entrada; la mano del usuario manda.
        self._fondo_encendido_a_mano = False
        self._volumen_del_fondo = VOLUMEN_DEL_FONDO_POR_OMISION
        # Sube con cada fondo nuevo, y forma parte de la clave del render. Es un
        # contador y no el `FondoDisponible` mismo porque la clave se compara en
        # cada instantanea: comparar dos fondos es recorrer todas sus notas
        # treinta veces por segundo.
        self._generacion_del_fondo = 0
        # (generacion del fondo, factor de tempo) de lo ultimo que se mando
        # renderizar. Es lo que decide si hay que volver a sintetizar: solo
        # cuando cambia el archivo o el factor, nunca por mirar el estado.
        self._clave_del_render: tuple[int, float] | None = None
        self._renderizada: PiezaRenderizada | None = None
        # El hilo que esta sintetizando ahora mismo, si lo hay. Nadie lo espera
        # en produccion -el render entrega solo, y mientras no entrega el fondo
        # escribe silencio-: se guarda para que las pruebas puedan esperarlo con
        # un `join` en vez de dormir, que es como esta rama ha arreglado ya dos
        # pruebas intermitentes.
        self._hilo_del_render: threading.Thread | None = None
        # El pulso que el fondo debe estar sonando, puesto por quien mueve el
        # reloj y leido por la clausura del cabezal SIN esperar el candado. Ver
        # `_cabezal_del_carril`, que es lo que de verdad decide si el fondo suena
        # o se calla.
        self._cabezal_pulsos: float | None = None
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
        # Si el cable ha entregado señal en ALGUN momento de esta pasada. Lo pone
        # el mismo sitio que `_pausado` y se borra al arrancar y al parar, porque
        # es un hecho DE LA PASADA: lo que dice es si acusar al cable del silencio
        # de ahora mismo sigue siendo creible. Ver `se_esperan_notas`.
        self._hubo_senal = False

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
                # **El fondo se suelta con la pieza**, y de ahi el orden que
                # tiene que seguir quien quiera las dos cosas: primero
                # `iniciar(pieza, plan)` -que detiene lo anterior- y despues
                # `cargar_acompanamiento(fondo)`. Un fondo que sobreviviera al
                # `detener()` sonaria encima de la pieza SIGUIENTE, que es otra
                # cancion y casi nunca el mismo tempo.
                self._parar_acompanamiento()
                self._olvidar_el_fondo()
                self._cabezal_pulsos = None
                self._estudio = None
                # Con el conductor se va todo lo que llevaba: el reloj, las
                # marcas del final y la sugerencia del tempo. El historial no,
                # que vive en `_historiales` por nombre de pieza.
                self._conductor = None
                self._pieza = None
                self._instante = 0.0
                self._pausado = False
                # Se borra SOLO aqui, y `iniciar` detiene antes de arrancar: la
                # copia en `iniciar` era un mutante equivalente -quitarla no
                # mataba ninguna prueba- y este modulo ya aprendio que reponer lo
                # mismo en dos sitios son dos lineas que hay que acordarse de
                # repetir.
                self._hubo_senal = False

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

    @property
    def esperando_notas(self) -> bool:
        """Si el silencio de ahora mismo puede ser una averia del cable.

        **LA REGLA NO ESTA AQUI: esta en `se_esperan_notas`**, de donde la leen
        las dos mitades del aviso -esta propiedad, que es lo que mira
        `/api/diagnostico`, y el campo `esperando_notas` del estado publicado, que
        es lo que mira la linea naranja del carril-. Que estuviera escrita dos
        veces, en dos idiomas y distinta en cada uno es el defecto que esto cierra.

        NO mira el reloj ni mueve nada: lee el estado que el estudio ya tiene, sin
        pasar por `estado()`, que MIRA antes de publicar. Esto lo llama el hilo
        HTTP cada pocos segundos y mover el reloj de la pasada desde el endpoint
        del diagnostico seria darle de comer tiempo por una puerta que no es la
        suya.
        """
        with self._candado:
            estudio = self._estudio
            return se_esperan_notas(
                None if estudio is None else estudio.estado,
                self._pausado,
                self._hubo_senal,
            )

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

    def _cuadro_con_senal(self, resultado) -> bool:
        """Si este cuadro de audio trae señal de verdad, no silencio.

        Es el hecho que `_hubo_senal` acumula, y la pregunta se le hace AL CUADRO
        porque es la unica forma de saber que el cable entrego algo: el
        `senal_ausente` de la sesion es «cinco segundos seguidos por debajo del
        umbral», asi que es falso durante los cinco primeros segundos de cualquier
        pasada, tambien de una en la que nunca llegue nada.

        El umbral es el de la configuracion de la sesion de audio -el mismo con el
        que ella decide la falta de señal, para no tener dos respuestas a la misma
        pregunta- y el de fabrica cuando esa sesion no lleva configuracion, igual
        que en `_perfil_activo`.
        """
        configuracion = getattr(self._sesion_audio, "configuracion", None)
        umbral = (
            UMBRAL_DE_RUIDO_POR_DEFECTO_DBFS
            if configuracion is None
            else configuracion.umbral_ruido_dbfs
        )
        return resultado.nivel_db is not None and resultado.nivel_db > umbral

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
        falta de señal y `_instante`, que es un espejo del reloj del conductor.

        **Ese espejo NO es lo que publica el WebSocket**, y decirlo aqui era falso
        desde que el reloj de esta clase paso a ser una copia del del estudio: lo
        que se publica sale del `EstadoEstudio` que devuelve el conductor (ver
        `_instantanea`, que recibe el estado como parametro y no lee este campo).
        `_instante` no lo lee hoy ningun codigo de produccion; su unico lector
        vivo es `tests/test_sesion_carril.py`, que lo usa para mirar el reloj desde
        fuera. La razon de que se quede -y lo que habria que hacer el dia que
        estorbe- esta en el docstring de la clase.
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
            # **DEL CUADRO Y NO DE `ausente`**: `senal_ausente` solo se enciende
            # tras cinco segundos por debajo del umbral, asi que al arrancar la
            # pasada es falso sin que haya llegado una sola muestra y el hecho se
            # daria por cierto antes de ser cierto. Lo que cuenta es un cuadro con
            # nivel por encima del umbral de ruido: eso es el cable entregando.
            if self._cuadro_con_senal(resultado):
                self._hubo_senal = True
            self._instante = conductor.instante
        estado = conductor.observar(resultado, instante_analisis)
        # El cabezal del fondo se refresca tambien aqui, y no solo en la
        # instantanea: el audio llega cada 21 ms y la instantanea cada 33, asi
        # que sin esto el fondo iria a tirones de un tercio de bloque. No se
        # pregunta mas a menudo porque no serviria: el reloj de la pasada SOLO
        # se mueve en estos dos sitios, asi que entre dos avisos el cabezal vale
        # exactamente lo mismo se pregunte cuando se pregunte. Eso es lo que
        # permite que la clausura lea un float en vez de entrar en el nucleo.
        with self._candado:
            # Y solo si el conductor sigue siendo el de esta pasada: un cuadro
            # en vuelo puede aterrizar despues de `detener()`, y dejaria un
            # cabezal vivo apuntando a una pieza que ya no esta.
            if self._conductor is conductor:
                self._cabezal_pulsos = cabezal_del_fondo(estado)

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
        self._cabezal_pulsos = cabezal_del_fondo(estado)
        if estado is None:
            return {
                **replace(_ESTUDIO_APAGADO, **self._campos_del_fondo()).a_dict(),
                "pausado": False,
                # Sin pasada SI se esperan notas: el afinador. Ver
                # `se_esperan_notas`, que es quien lo decide tambien aqui.
                "esperando_notas": se_esperan_notas(None, False, False),
                "click_sonando": False,
                "factor_sugerido": None,
                "arranque": ARRANQUE_NINGUNO,
            }
        # El click se ajusta en CADA instantanea y no solo en la vuelta: aqui se
        # atiende el tempo nuevo, la pausa y el fin del tramo. La vuelta la avisa
        # ademas el conductor (`al_cambiar_repeticion`), y que se solapen no
        # cuesta nada: con la misma clave este metodo no reabre nada.
        self._ajustar_click(estado)
        # Y el acompañamiento en la misma instantanea y por lo mismo: aqui se
        # atiende el factor de tempo nuevo, la pausa y el fin del tramo. No
        # rearranca por repeticion, al contrario que el click: el acompañante no
        # lleva reloj propio, asi que no acumula deriva que haya que borrar
        # dando la vuelta. Es la ventaja de leer el cabezal en cada bloque.
        self._ajustar_acompanamiento(estado)
        return {
            **replace(estado, **self._campos_del_fondo()).a_dict(),
            "pausado": self._pausado,
            # La MISMA llamada que contesta a `/api/diagnostico` por la propiedad
            # `esperando_notas`: las dos mitades del aviso del cable no pueden
            # discrepar porque leen el mismo dato. Ver `se_esperan_notas`.
            "esperando_notas": se_esperan_notas(
                estado, self._pausado, self._hubo_senal
            ),
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

    # -- el acompañamiento: la pieza de fondo mientras el usuario toca --------

    def cargar_acompanamiento(
        self,
        fondo: FondoDisponible | None,
        volumen: float = VOLUMEN_DEL_FONDO_POR_OMISION,
    ) -> None:
        """**La puerta PROPIA del acompañamiento**, y lo enciende al cargarlo.

        No pasa por `iniciar(pieza, plan)`, y eso es una decision y no un
        descuido: `iniciar` es la puerta unica del carril y su firma no cambia.
        Si el fondo entrara por ella, el carril tendria que saber de que archivo
        salio su pieza -hoy no lo sabe y no le hace falta-, y todo el que ya
        llama a `iniciar` (el gemelo, los generadores de ejercicios, las piezas
        de prueba) tendria que aprender un parametro que no usa.

        **El orden es `iniciar` y DESPUES esto**: `iniciar` detiene lo anterior,
        y `detener` suelta el fondo con la pieza (ver `detener`).

        `fondo=None` lo apaga y lo olvida, que es lo que hace falta cuando el
        usuario deselecciona el archivo de fondo.

        **Cargar enciende, pero es un encendido AUTOMATICO: solo suena mientras
        la entrada sea el cable** (decision M6 de la spec). Cargarlo es haberlo
        pedido, si, y con el cable esto deja el caso normal en un solo paso.
        Pero con cualquier otra entrada -el microfono del portatil- el sonido
        del fondo ENTRA por ella, el detector de ataques lo cobra como notas del
        usuario y el informe se llena de aciertos y fallos que no toco nadie. Y
        lo peor no es que este mal: es que **no se nota**, porque los numeros
        salen. Que eso ocurra porque alguien eligio un archivo -sin haber
        decidido nada- es el anti-objetivo de la etapa entera pasando solo.

        **La condicion NO se evalua aqui y se guarda**, se mira en cada
        instantanea (`acompanamiento_debe_sonar`), porque la entrada cambia a
        mitad de pasada: el usuario que elige el microfono en el selector tiene
        que quedarse sin fondo en el acto, no al empezar la pieza siguiente.
        Lo que esta llamada deja dicho es solo que el encendido es automatico y
        no de la mano del usuario.

        Con otra entrada, entonces, se carga y se queda CALLADO. El usuario
        puede encenderlo a mano con `acompanamiento(encendido=True)` -es su
        equipo, y con auriculares no hay realimentacion ninguna-; esa decision
        si persiste, y mientras suene el estado seguira diciendo
        `acompanamiento_posible: False` para que el recordatorio no se vaya. El
        precio de equivocarse esta medido y es pequeño: quien tenga una interfaz
        que no se llame «Rocksmith» le da al interruptor una vez.

        Encendido no es sonando: hace falta ademas salida de audio, pasada en
        marcha y buffer renderizado, y nada de eso lo decide esta llamada.

        Un volumen fuera de [0, 1] es `ValueError`, que sale como 400 igual que
        un plan imposible.
        """
        volumen = _volumen_valido(volumen)
        with self._candado:
            if fondo is None:
                self._parar_acompanamiento()
                self._olvidar_el_fondo()
                return
            # El fondo nuevo invalida el buffer de el anterior, y el contador de
            # generacion es lo que hace que la instantanea siguiente mande
            # renderizar sin tener que comparar dos archivos nota a nota.
            self._fondo = fondo
            # **La generacion es lo UNICO que invalida el render**, y por eso
            # aqui no se toca `_clave_del_render`: con dos senales para la misma
            # decision -subir el contador y ademas borrar la clave- la segunda
            # tapa a la primera, y un dia que la primera se rompa no se entera
            # nadie. El buffer si se tira, que es otra cosa: la clave dice
            # «hay que volver a sintetizar» y `_renderizada` es «lo que suena
            # mientras tanto», que no puede ser la pista anterior.
            self._generacion_del_fondo += 1
            self._renderizada = None
            self._volumen_del_fondo = volumen
            # Encendido AUTOMATICO: suena mientras la entrada sea el cable, y
            # el pestillo se mira en cada instantanea, no aqui. Ver
            # `acompanamiento_debe_sonar`, que es donde vive la regla M6.
            self._fondo_encendido = True
            self._fondo_encendido_a_mano = False
            # **Y se para el que estuviera sonando.** No es simetria: el
            # acompañante vivo lleva CARGADA la pieza anterior y seguiria
            # tocandola tan contento durante todo el render de la nueva, asi
            # que elegir otra pista de fondo sonaria a la anterior unos
            # segundos. Parar aqui lo deja en silencio y la instantanea
            # siguiente lo vuelve a levantar con el buffer que toque -o sin
            # ninguno todavia, que es silencio-. Cuesta un cierre y una
            # apertura del dispositivo por cambio de archivo, que es algo que
            # el usuario hace a mano y de uvas a peras.
            self._parar_acompanamiento()

    def acompanamiento(
        self, encendido: bool | None = None, volumen: float | None = None
    ) -> dict:
        """El interruptor y el volumen, VIVOS. Devuelve el estado publicado.

        **Ninguno de los dos va en `PlanDePasada`**, y el motivo es medible:
        todo cambio de plan pasa por `SesionDeEstudio.cambiar_plan`, que hace
        `cerrar_repeticion(cuenta_como_vuelta=False)` para volcar lo tocado antes
        de tirar el seguidor. Un deslizador de volumen arrastrado de 0,2 a 0,8
        son decenas de cierres de repeticion -y decenas de reconstrucciones del
        seguidor si ademas tocara el factor-, y encender el fondo a mitad de
        pasada le partiria la vuelta al alumno. Ni el volumen ni el interruptor
        cambian la pasada: cambian lo que sale por los altavoces.

        Los dos son explicitos y no interruptores de los de «dale la vuelta a lo
        que haya», por lo mismo que `pausa(activa)`: dos clics desde dos
        pestañas no pueden dejar el fondo en el estado contrario al que las dos
        pidieron.

        El volumen NO vuelve a renderizar: el render se hace a ganancia 1 y el
        volumen entra por `Acompanante.ganancia()`, que lo aplica suavizado en el
        bloque siguiente. Renderizar una pieza de tres minutos por cada paso del
        deslizador seria mover un deslizador con segundos de retardo.
        """
        with self._candado:
            if encendido is not None:
                self._fondo_encendido = bool(encendido)
                # La mano del usuario: a partir de aqui la entrada ya no apaga
                # el fondo por su cuenta (ver `acompanamiento_debe_sonar`). Se
                # apunta tambien al apagar, y a False, porque apagar deja el
                # fondo sin ninguna decision viva que defender: el encendido
                # siguiente volvera a decir de quien es.
                self._fondo_encendido_a_mano = bool(encendido)
            if volumen is not None:
                self._volumen_del_fondo = _volumen_valido(volumen)
                if self._acompanante is not None:
                    self._acompanante.ganancia(self._ganancia_del_fondo())
        return self.estado()

    def _campos_del_fondo(self) -> dict:
        """Los campos del acompañamiento que viajan en el estado.

        Un solo sitio los decide, y los dos caminos de `_instantanea` -con pieza
        y sin ella- llaman AQUI en vez de escribirlos cada uno. Es la misma
        leccion de `se_esperan_notas`, aplicada dentro de un solo archivo:
        bastan dos copias en el mismo idioma para que empiecen a discrepar.
        """
        fondo = self._fondo
        return {
            # Lo que SUENA, no lo que se pidio: sin salida de audio el
            # interruptor esta puesto y esto es False, para que la pantalla
            # escriba «sin fondo» en vez de un interruptor que no hace nada.
            # Mismo criterio que `click_sonando`.
            "acompanamiento_sonando": (
                self._acompanante is not None and self._acompanante.sonando
            ),
            "acompanamiento_posible": acompanamiento_posible(
                fondo is not None, self._entrada_es_el_cable()
            ),
            "acompanamiento_es_tu_parte": fondo is not None and not fondo.voces,
            # Las voces AJENAS que suenan, y las pistas que se quedaron fuera
            # con su motivo. Salen del `FondoDisponible` tal cual lo dejo
            # `cargar_acompanamiento`, sin recontar nada: quien decide que pista
            # entra es `voces_de_fondo._se_pierde_algo` y aqui solo se publica.
            # Sin fondo, cero y nada: no es que el archivo no tenga voces, es
            # que no hay archivo.
            "acompanamiento_voces": len(fondo.voces) if fondo is not None else 0,
            "acompanamiento_excluidas": fondo.excluidas if fondo is not None else (),
        }

    def _entrada_es_el_cable(self) -> bool:
        """Lo que diga la sesion de audio, que es quien decide esa regla.

        Aqui NO se busca el cable: `Sesion.entrada_es_el_cable` es el unico sitio
        que llama a `buscar_rocksmith` para contestarlo, y esto solo lo lee para
        publicarlo. Una sesion de audio que no lleve la propiedad -un doble de
        prueba, un flujo de audio futuro- no es el cable: afirmarlo callaria el
        recordatorio sin saber nada, y el recordatorio existe precisamente para
        los casos en que la entrada no es la que se cree.
        """
        return bool(getattr(self._sesion_audio, "entrada_es_el_cable", False))

    def _ganancia_del_fondo(self) -> float:
        """El volumen pedido, a la mitad cuando lo que suena es tu propia parte.

        Se aplica como ganancia del acompañante y NO como ganancia del render,
        que va siempre a 1: asi mover el deslizador no vuelve a sintetizar nada.
        """
        if self._fondo is not None and not self._fondo.voces:
            return self._volumen_del_fondo * GANANCIA_DE_TU_PARTE
        return self._volumen_del_fondo

    def _cabezal_del_carril(self) -> float | None:
        """El cabezal que lee el acompañante, SIN ESPERAR NUNCA el candado.

        **Esta clausura la llama el hilo de audio una vez por bloque -cada 21
        ms-, y si se bloquea, se oye.** Por eso intenta el candado con
        `blocking=False` y lanza `BloqueadoAhora` cuando lo encuentra ocupado:
        el acompañante trata esa excepcion repitiendo el ultimo instante
        conocido durante `REPETICIONES_MAXIMAS` bloques seguidos (~85 ms) y
        desvaneciendose despues, que es una degradacion suave y acotada.

        Esperar el candado no seria una degradacion suave, seria un abrazo
        mortal: `_parar_acompanamiento` corre CON el candado tomado y hace
        `Acompanante.detener()`, que es un `join(timeout=1.0)` sobre este mismo
        hilo. Con `blocking=True` el hilo de audio estaria esperando el candado
        que el que lo quiere parar tiene en la mano: el join venceria al segundo,
        `detener()` devolveria el control como si el fondo estuviera parado y
        quedaria un hilo huerfano escribiendo sobre una salida que la linea
        siguiente cierra. Cambiar `blocking=False` por un `with self._candado:`
        es exactamente ese defecto, y es el primer mutante de esta tarea.

        Lo que se lee es un `float | None` y nada mas: ni se entra en el nucleo
        -cuyo candado tambien podria estar ocupado- ni se construye ningun
        estado. Cuesta nanosegundos, y es tan actual como preguntarle al estudio
        **porque se mantiene una invariante que conviene escribir entera, ya que
        no la obliga nada**:

        > **TODO metodo que mueva el estudio tiene que acabar llamando a
        > `estado()`.**

        La foto la escriben `_instantanea` y `_observar` (y `detener`, que la
        pone a `None`, que es silencio y siempre es seguro). Pero el estado del
        nucleo del que sale lo mueven CINCO sitios: esos dos y, ademas,
        `_aplicar_plan`, `saltar` y `pausa`. Los tres ultimos no refrescan la
        foto ellos mismos; quedan cubiertos solo porque cada uno termina en
        `self.estado()`. El nucleo no lleva reloj propio, asi que entre dos
        avisos el cabezal vale exactamente lo mismo y la foto es exacta.

        **Lo que rompe esto es un metodo nuevo que mute el estudio y devuelva
        otra cosa**: la foto se quedaria vieja y el fondo sonaria desplazado
        respecto al carril, sin que nada lo dijera. Si haces uno -un endpoint
        de la Task 6, por ejemplo-, acaba en `estado()` o refresca la foto a
        mano con `cabezal_del_fondo`.
        """
        if not self._candado.acquire(blocking=False):
            raise BloqueadoAhora()
        try:
            return self._cabezal_pulsos
        finally:
            self._candado.release()

    def _ajustar_acompanamiento(self, estado: EstadoEstudio) -> None:
        """Arranca, para o pausa el fondo segun el estado. BAJO candado.

        Calcada de `_ajustar_click`, incluidas las dos cosas que la etapa 3c
        aprendio: se llama desde la instantanea y NO desde `_observar` -el hilo
        de analisis no puede pagar un `join`-, y **sin salida de audio la pasada
        sigue en pie**, porque quedarse sin fondo degrada la experiencia y no la
        impide.

        Tres diferencias con el click, todas por la misma razon -el acompañante
        no lleva reloj propio-:

        1. **No rearranca en cada repeticion.** El metronomo lo hace para borrar
           la deriva de su reloj y para que la cuenta atras se oiga desde su
           primer pulso; aqui no hay reloj que derive y la cuenta atras la
           resuelve `cabezal_del_fondo` devolviendo None.
        2. **Un tempo nuevo no rearranca nada**: vuelve a renderizar, y el buffer
           nuevo entra en caliente con `Acompanante.cargar()`.
        3. **El render va en un hilo aparte** y hasta que el buffer este, el
           fondo escribe silencio. Sintetizar tres minutos de musica dentro de la
           instantanea dejaria el WebSocket mudo varios segundos.
        """
        estudio = self._estudio
        pieza = self._pieza
        if (
            estudio is None
            or pieza is None
            or self._fondo is None
            # El pestillo de M6, mirado AQUI y por tanto en cada instantanea:
            # el usuario que cambia de entrada a mitad de pasada se queda sin
            # fondo en el acto, y el que lo encendio a mano no.
            or not acompanamiento_debe_sonar(
                self._fondo_encendido,
                self._fondo_encendido_a_mano,
                self._entrada_es_el_cable(),
            )
        ):
            self._parar_acompanamiento()
            return
        # Igual que el click, y el `and not estado.en_bucle` igual de defensivo:
        # acabada la pasada sin bucle, el fondo seguiria solo mientras el usuario
        # mira el informe.
        if estado.tramo_terminado and not estado.en_bucle:
            self._parar_acompanamiento()
            return
        self._pedir_el_render(pieza, estudio)
        if self._acompanante is None and not self._arrancar_acompanante():
            return
        # Las dos pausas, las mismas que el click: la del usuario y la de la
        # falta de señal. Con `pausar()` y no con `detener()`, para no pagar el
        # `join` en cada pulsacion del boton -y para no perder el buffer, que
        # volver a cargar es gratis pero volver a renderizar no-.
        if self._pausado or estado.en_pausa:
            self._acompanante.pausar()
        else:
            self._acompanante.reanudar()

    def _arrancar_acompanante(self) -> bool:
        """Abre la salida propia y echa a andar el hilo. False si no se pudo.

        No deja la salida abierta cuando el hilo no arranca, por lo mismo que el
        click: seria retener el dispositivo sin usarlo.
        """
        if not self._salida_fondo.abrir():
            return False
        acompanante = Acompanante(salida=self._salida_fondo)
        if self._renderizada is not None:
            acompanante.cargar(self._renderizada)
        acompanante.ganancia(self._ganancia_del_fondo())
        if not acompanante.iniciar(self._cabezal_del_carril):
            self._salida_fondo.cerrar()
            return False
        self._acompanante = acompanante
        return True

    def _pedir_el_render(self, pieza: Pieza, estudio: SesionDeEstudio) -> None:
        """Manda sintetizar el fondo, SOLO si cambio el archivo o el factor.

        La clave es `(generacion del fondo, factor de tempo)`, y es lo unico que
        separa un render por pasada de un render en cada instantanea: esto lo
        llama la instantanea treinta veces por segundo, y sintetizar tres minutos
        de musica treinta veces por segundo no es que vaya lento, es que no
        termina nunca.

        El tempo sale de la PIEZA y el factor del PLAN, que es la unica
        combinacion que mueve el fondo al compas del carril: el tempo de
        `FondoDisponible` es informativo y puede no ser el mismo (ver el
        docstring de `nucleo.acompanamiento`).
        """
        fondo = self._fondo
        if fondo is None:
            return
        clave = (self._generacion_del_fondo, estudio.plan.factor_tempo)
        if clave == self._clave_del_render:
            return
        self._clave_del_render = clave
        # Sin voces en el archivo suena la parte del propio usuario, a media
        # ganancia y DICIENDOLO (`acompanamiento_es_tu_parte`).
        voces = fondo.voces or (voz_de_tu_parte(pieza),)
        hilo = threading.Thread(
            target=self._renderizar,
            args=(clave, voces, pieza.tempo, estudio.plan.factor_tempo),
            daemon=True,
        )
        self._hilo_del_render = hilo
        hilo.start()

    def _renderizar(
        self,
        clave: tuple[int, float],
        voces: tuple[VozDeFondo, ...],
        tempo: int,
        factor_tempo: float,
    ) -> None:
        """Sintetiza fuera del hilo de la instantanea y entrega si sigue valiendo.

        La sintesis corre SIN candado -es lo lento, y retenerlo aqui dejaria la
        clausura del cabezal fallando durante todo el render, o sea el fondo
        desvanecido justo al empezar-. Solo la entrega lo toma, y comprueba antes
        que la clave siga siendo la vigente: un render que se queda por el camino
        -el usuario movio el tempo dos veces seguidas- no puede pisar al que
        venia detras.

        Una pieza que no cabe (`MUESTRAS_MAXIMAS`) o un tempo imposible dejan la
        pasada sin fondo y en pie, y lo dicen en el registro UNA vez: es el mismo
        trato que el tempo que el metronomo rechaza.
        """
        try:
            renderizada = renderizar(
                voces,
                tempo=tempo,
                factor_tempo=factor_tempo,
                frecuencia_muestreo=self._salida_fondo.frecuencia_muestreo,
            )
        except ValueError as error:
            _registro.error("La pieza de fondo no se pudo renderizar: %s", error)
            return
        with self._candado:
            if clave != self._clave_del_render:
                return
            self._renderizada = renderizada
            if self._acompanante is not None:
                self._acompanante.cargar(renderizada)

    def _parar_acompanamiento(self) -> None:
        """Para el fondo y cierra SU salida. Seguro de llamar sin fondo.

        **El buffer renderizado NO se tira**, al contrario que el metronomo con
        su clave: apagar y encender el interruptor es gratis y volver a
        sintetizar tres minutos de musica no. Lo que invalida el buffer es
        cambiar de archivo o de factor, y eso lo llevan `cargar_acompanamiento` y
        la clave del render.

        Cierra `self._salida_fondo`, que es SUYA: por eso puede hacerlo sin
        condiciones treinta veces por segundo -con el fondo apagado el stream ya
        esta en None y no hay nada que cerrar- sin tocarle el stream al click.
        """
        if self._acompanante is not None:
            self._acompanante.detener()
        self._acompanante = None
        self._salida_fondo.cerrar()

    def _olvidar_el_fondo(self) -> None:
        """Suelta el archivo de fondo y todo lo que se derivaba de el.

        **La clave del render NO se toca aqui**, y la ausencia es a proposito:
        invalidar el render es UNA sola cosa, la generacion del fondo (ver
        `cargar_acompanamiento`). Esta linea estuvo y se quito: era inofensiva
        -sin `_fondo`, `_pedir_el_render` sale por la puerta de arriba y la
        carga siguiente sube la generacion igual-, pero PARECIA una segunda
        senal de invalidacion justo al lado de la que se quito por serlo, y una
        linea que hay que demostrar inocente cada vez que se lee cuesta mas de
        lo que vale.
        """
        self._fondo = None
        self._fondo_encendido = False
        self._fondo_encendido_a_mano = False
        self._renderizada = None

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

        **Mueve el estudio, asi que quien lo llame tiene que acabar en
        `estado()`**: de eso depende que la foto del cabezal del fondo
        (`_cabezal_pulsos`) no se quede vieja. Hoy lo cumplen los dos que hay,
        `cambiar_plan` y `parchar_plan`. Ver `_cabezal_del_carril`.
        """
        self._instante = self._conductor.cambiar_plan(plan).carril.instante_s

    def saltar(self, numero: int) -> dict:
        """Coloca el cabezal al principio de un compas DEL TRAMO.

        Un compas fuera del tramo lo rechaza el nucleo con `ValueError`, y sale
        como 400 igual que los demas: saltar fuera del tramo es cambiar el plan.

        Mueve el estudio y por eso **acaba en `estado()`**, que es lo que
        refresca la foto del cabezal del fondo: un salto que devolviera otra
        cosa dejaria el fondo sonando donde el cabezal ya no esta. Ver
        `_cabezal_del_carril`, que escribe la invariante entera.
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

        Mueve el estudio y **acaba en `estado()`**, por lo mismo que `saltar`.
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
