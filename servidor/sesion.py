"""Une captura y análisis, y los mantiene corriendo en segundo plano.

El hilo de trabajo es el **dueño del ciclo de vida del dispositivo**: no solo
analiza, también abre la captura cuando falta y la cierra cuando el dispositivo
desaparece. Esta es la pieza que hace posible la reconexión automática que pide
la spec §5: desconectar el cable es algo que pasa a menudo y obligar a reiniciar
el programa sería un castigo desproporcionado.
"""

import logging
import threading
import time
from dataclasses import replace
from typing import Callable

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import nivel_dbfs
from nucleo.analisis.pipeline import (
    INTERVALO_DE_ANALISIS_S as INTERVALO_ANALISIS,
)
from nucleo.analisis.pipeline import Analizador, ResultadoAnalisis
from nucleo.captura import CapturaAudio, buscar_rocksmith, listar_dispositivos_entrada
from servidor.configuracion import Configuracion, calibrar_umbral
from servidor.diagnostico import Diagnostico, diagnosticar

_registro = logging.getLogger(__name__)

# Cada cuánto analiza el hilo de trabajo. La constante vive en el núcleo
# (`nucleo.analisis.pipeline.INTERVALO_DE_ANALISIS_S`) y aquí se reexporta con su
# nombre de siempre, porque el otro alimentador del análisis es la cadena directa
# del gemelo digital y dos copias de la cadencia que gobierna la calibración del
# detector se separan tarde o temprano. Es el mismo reparto que `TECHO_TRAMO_S`,
# que vive en `nucleo/piezas/conductor.py` y `servidor/piezas.py` reexporta.

# Espera entre intentos de abrir el dispositivo. Dos segundos es suficiente para
# que enchufar el cable se note casi al instante y lo bastante largo para no
# martillear a CoreAudio ni llenar la terminal de mensajes.
ESPERA_REINTENTO_APERTURA = 2.0

# Cada cuánto se comprueba que el dispositivo abierto sigue en la lista del
# sistema. Enumerar dispositivos es caro comparado con analizar una ventana, así
# que no se hace en cada vuelta.
INTERVALO_REVISION_DISPOSITIVO = 1.0

# Tiempo sin muestras nuevas tras el cual se publica silencio. El buffer circular
# no caduca solo: si el cable se desconecta en caliente, el callback deja de
# escribir pero las últimas muestras siguen ahí, y reprocesarlas congelaría la
# última nota en pantalla para siempre. Medio segundo es de sobra: a 48 kHz con
# bloques de 512 muestras llega uno cada 10,67 ms.
TIEMPO_SIN_MUESTRAS_SILENCIO = 0.5

# La spec §5 exige que la falta de señal se anuncie solo tras más de 5 s seguidos
# por debajo del umbral. Con el sondeo de la interfaz cada 3 s, avisar al instante
# haría parpadear el aviso entre nota y nota, y un aviso que cría lobo se deja de
# leer.
SEGUNDOS_SIN_SENAL = 5.0


class Sesion:
    """Propietaria única de la captura y el analizador.

    Guarda solo el último resultado, no una cola: un consumidor lento debe ver el
    presente, no desenterrar el pasado.
    """

    def __init__(
        self,
        configuracion: Configuracion,
        crear_captura: Callable | None = None,
        listar: Callable | None = None,
        reloj: Callable[[], float] | None = None,
    ) -> None:
        self.configuracion = configuracion
        self._crear_captura = crear_captura or (lambda **kw: CapturaAudio(**kw))
        self._listar = listar or listar_dispositivos_entrada
        # El reloj monotono del hilo de analisis, inyectable. Es la tercera
        # costura de esta clase, por la misma razon que las otras dos: la
        # aritmetica del plazo acumulado (`_esperar_el_cuadro`) no es afirmable
        # contra el reloj de verdad, y parchear `time.monotonic` en el modulo lo
        # parchea para TODOS los hilos que esten corriendo -se intento, y dejo la
        # suite intermitente-.
        self._reloj = reloj or time.monotonic
        self._captura = None
        self._analizador: Analizador | None = None
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._ultimo: ResultadoAnalisis | None = None
        self._candado = threading.Lock()
        # Funciones suscritas a cada resultado publicado (no muestreado): las
        # necesita quien no puede permitirse perder cuadros, como el evaluador
        # de ejercicios. Ver registrar_observador().
        self._observadores: list[Callable] = []
        # La lista se muta desde el hilo HTTP (iniciar o detener un ejercicio) y
        # se recorre desde el hilo de análisis. Candado propio y no `_candado`:
        # ese protege `_ultimo`, y compartirlo obligaría a retenerlo mientras
        # corre el código de un observador ajeno.
        self._candado_observadores = threading.Lock()
        # Fallos de observador ya anunciados (observador + tipo de error), para
        # no repetir la misma línea en cada cuadro: el análisis publica a 47 Hz.
        self._fallos_observador_anunciados: set[str] = set()
        # Protege el ciclo de vida de la captura: el hilo de trabajo la abre y la
        # cierra, pero `aplicar()` y `detener()` también la tocan desde el hilo
        # del servidor.
        self._candado_dispositivo = threading.RLock()
        self._ultimo_error_apertura: str | None = None
        self._error_anunciado: str | None = None
        # Si la captura ABIERTA es el cable Rocksmith. Ver `entrada_es_el_cable`:
        # se decide al abrir, que es el unico momento en que se sabe, y se lee
        # muchas veces por segundo sin volver a enumerar nada.
        self._entrada_es_el_cable = False
        # Muestras vistas en la vuelta anterior y cuándo se vieron, para detectar
        # que dejaron de llegar (ver TIEMPO_SIN_MUESTRAS_SILENCIO).
        self._total_visto = -1
        self._instante_muestras = 0.0
        # Desde cuándo el nivel está bajo el umbral, o None si no lo está.
        self._instante_bajo_umbral: float | None = None
        # Latencia medida entre la llegada del bloque y la publicación del
        # resultado, que es la que pide la spec §6. None hasta la primera medida.
        self._latencia_medida_ms: float | None = None
        # Se incrementa en detener() y en aplicar() cada vez que se reconstruye el
        # analizador o se reabre el stream. _trabajar la lee al empezar cada vuelta
        # y solo publica si no cambió: así un resultado calculado con la
        # configuración anterior, o por un hilo huérfano que ya debía haber
        # terminado, nunca llega a publicarse.
        self._generacion = 0
        # Ajustables en las pruebas para no esperar segundos de reloj.
        self.espera_reintento = ESPERA_REINTENTO_APERTURA
        self.intervalo_revision = INTERVALO_REVISION_DISPOSITIVO
        self.tiempo_sin_muestras = TIEMPO_SIN_MUESTRAS_SILENCIO
        self.segundos_sin_senal = SEGUNDOS_SIN_SENAL

    @property
    def activa(self) -> bool:
        """Verdadero si se está capturando de verdad: captura abierta **y** hilo vivo.

        Las dos condiciones son necesarias desde que el hilo es el dueño del
        ciclo de vida del dispositivo. Una captura abierta sin un hilo que la lea
        es una sesión muerta que aparenta estar viva: el stream sigue escribiendo
        en el buffer circular, nadie lo analiza, el último resultado se queda
        congelado y `diagnostico()` diría "ok" sobre una pantalla que ya no se
        actualiza. Es la misma mentira que la reconexión automática vino a
        eliminar, solo que por otra causa.
        """
        return self._captura is not None and self._hilo is not None and self._hilo.is_alive()

    @property
    def entrada_es_el_cable(self) -> bool:
        """**LA REGLA «LA ENTRADA ES EL CABLE», DECIDIDA UNA SOLA VEZ.**

        Contesta si lo que se esta capturando AHORA MISMO es el cable Rocksmith,
        y no un microfono. De ella cuelga el acompañamiento: la pieza de fondo
        sale por los altavoces, y con un microfono abierto vuelve a entrar por el
        y se mezcla con lo que el alumno toca. El detector de tono ve entonces la
        suma de las dos cosas, el carril le adjudica al alumno notas que no ha
        tocado y el informe de la pasada deja de ser suyo. Con el cable no pasa:
        la guitarra entra por el jack y lo que suena por los altavoces no vuelve.
        El resultado no es un fondo peor, es una medicion falsa, y por eso la
        pantalla lo recuerda.

        **Es la UNICA fuente de esa regla**, igual que `se_esperan_notas` lo es
        de la del aviso del cable, y por el mismo motivo: escrita dos veces -una
        aqui y otra en el carril, o una en Python y otra en TypeScript- son dos
        reglas que no son la misma, y cada una tendria su mutante muriendo en su
        idioma. El carril la LEE y la publica (`acompanamiento_posible`); nadie
        mas llama a `buscar_rocksmith` para contestarla.

        Se responde con lo que se abrio y no con lo que se pretendia abrir: la
        preferencia es `_indice_objetivo` -lo que el usuario eligio, y el cable
        si no eligio nada-, asi que un usuario que elige a mano el microfono del
        portatil teniendo el cable enchufado recibe False, que es la verdad.
        Falso tambien sin captura abierta: sin entrada no hay entrada que sea el
        cable.
        """
        return self._entrada_es_el_cable

    @property
    def latencia_ms(self) -> float:
        """Latencia medida entre la llegada del bloque y la publicación.

        La spec §6 pide la latencia real de la cadena, no la que el dispositivo
        promete. Mientras no haya una medida todavía se devuelve la del
        dispositivo, que al menos es del orden correcto.
        """
        if self._latencia_medida_ms is not None:
            return self._latencia_medida_ms
        return self.latencia_dispositivo_ms

    @property
    def latencia_dispositivo_ms(self) -> float:
        """Latencia de entrada que reporta CoreAudio. Informativa, no la mostrada."""
        return self._captura.latencia_ms if self._captura else 0.0

    # ------------------------------------------------------------------
    # Diagnóstico
    # ------------------------------------------------------------------

    def _anotar_nivel(self, nivel_db: float | None) -> None:
        """Recuerda desde cuándo el nivel está por debajo del umbral.

        Llamado desde el hilo de trabajo en cada resultado publicado y desde
        `diagnostico()` cuando le pasan un nivel. Un solo nivel por encima del
        umbral reinicia la cuenta: el usuario tocó, luego hay señal.
        """
        if nivel_db is None:
            return
        if nivel_db > self.configuracion.umbral_ruido_dbfs:
            self._instante_bajo_umbral = None
        elif self._instante_bajo_umbral is None:
            self._instante_bajo_umbral = time.monotonic()

    def _falta_senal_confirmada(self) -> bool:
        """Verdadero si el nivel lleva más de 5 s seguidos bajo el umbral."""
        if self._instante_bajo_umbral is None:
            return False
        return time.monotonic() - self._instante_bajo_umbral > self.segundos_sin_senal

    @property
    def senal_ausente(self) -> bool:
        """Lo mismo que el diagnóstico llama `sin_senal`, pero barato de consultar.

        `diagnostico()` enumera los dispositivos del sistema, que es caro
        comparado con analizar una ventana; quien necesite saber si hay señal en
        cada cuadro (la sesión de práctica, para pausar el ejercicio como pide la
        spec §5) tiene que poder preguntarlo sin pagar esa enumeración.
        """
        return self._falta_senal_confirmada()

    def leer_ventana_cruda(self, muestras: int) -> np.ndarray | None:
        """Las últimas `muestras` muestras capturadas, sin analizar.

        Existe por la detección de acordes (etapa 2b), que necesita una ventana
        más larga que el análisis monofónico —8192 muestras frente a 4096, para
        separar semitonos graves— y por tanto no puede servirse de lo que los
        observadores reciben, que es un `ResultadoAnalisis` ya calculado sobre la
        ventana del perfil.

        Devuelve None si no hay captura abierta o si el buffer todavía no tiene
        tantas muestras. Es deliberado que no rellene con ceros: una ventana a
        medio llenar no se puede juzgar, y quien la pida tiene que poder
        distinguir "no hay bastante" de "hay silencio".
        """
        captura = self._captura
        if captura is None:
            return None
        return captura.leer_ventana(muestras)

    def diagnostico(
        self, nivel_db: float | None = None, esperando_notas: bool = True
    ) -> Diagnostico:
        """Estado actual del montaje.

        Nunca devuelve "ok" si la sesión no está capturando: decir que todo está
        bien con la captura cerrada es justo la mentira que dejaba al usuario
        mirando una pantalla muerta con un mensaje tranquilizador.

        `esperando_notas` viaja tal cual hasta `diagnosticar`, que es donde la
        regla vive y está explicada: esta sesión no sabe si hay una pieza en marcha
        -eso es del carril- y no es quien para decidirlo.
        """
        self._anotar_nivel(nivel_db)
        # Solo se acusa de falta de señal cuando lleva más de 5 s seguidos por
        # debajo (spec §5). Antes de eso, el nivel bajo es simplemente una pausa
        # entre notas y no se pasa al diagnóstico.
        nivel_efectivo = nivel_db
        if nivel_db is not None and not self._falta_senal_confirmada():
            if nivel_db <= self.configuracion.umbral_ruido_dbfs:
                nivel_efectivo = None

        dispositivos = self._listar()
        rocksmith = buscar_rocksmith(dispositivos)
        cable = rocksmith
        sustituido = False
        if self.configuracion.dispositivo is not None:
            elegido = self._elegido(dispositivos)
            if elegido is None and rocksmith is None:
                # Ni lo elegido ni el cable: no hay nada que abrir.
                return Diagnostico(
                    estado="sin_dispositivo",
                    mensaje=(
                        f"El dispositivo elegido ({self.configuracion.dispositivo}) "
                        "ya no está disponible."
                    ),
                    accion=(
                        "Reconéctalo si es un dispositivo USB, o elige otro "
                        "dispositivo en el selector. Se reintenta abrirlo solo."
                    ),
                    dispositivos=dispositivos,
                )
            # Si lo elegido no está pero el cable sí, se sigue adelante con el
            # cable. NO se devuelve aquí un "ok" propio: eso diría que todo va
            # bien sin haber comprobado que la captura está viva, que es el fallo
            # que la etapa 1 tuvo que corregir. El camino normal de abajo mira
            # `self.activa` antes de decir nada.
            cable = elegido if elegido is not None else rocksmith
            sustituido = elegido is None

        base = diagnosticar(
            dispositivos,
            cable,
            nivel_efectivo,
            self.configuracion.umbral_ruido_dbfs,
            rocksmith,
            esperando_notas,
        )
        if sustituido:
            # Usar otro dispositivo que el elegido no se hace en silencio.
            base = replace(
                base,
                mensaje=(
                    f"El dispositivo elegido ({self.configuracion.dispositivo}) no está; "
                    f"se usa {cable.nombre}. {base.mensaje}"
                ),
            )
        if base.estado in ("sin_permiso", "sin_dispositivo"):
            return base
        if not self.activa:
            detalle = (
                f" Último error del sistema: {self._ultimo_error_apertura}."
                if self._ultimo_error_apertura
                else ""
            )
            return Diagnostico(
                estado="sin_dispositivo",
                mensaje=(
                    f"{cable.nombre} está en la lista pero todavía no se ha podido "
                    "abrir para capturar."
                ),
                accion=(
                    "Se reintenta abrirlo automáticamente cada pocos segundos. "
                    "Si no se recupera, prueba a reconectar el cable o a elegir "
                    f"otro dispositivo.{detalle}"
                ),
                dispositivos=dispositivos,
            )
        return base

    # ------------------------------------------------------------------
    # Ciclo de vida del dispositivo
    # ------------------------------------------------------------------

    def _construir_analizador(self, configuracion: Configuracion) -> Analizador:
        """Construye el analizador de una configuración. Puede lanzar si es inválida."""
        return Analizador(
            PERFILES[configuracion.perfil],
            umbral_ruido_dbfs=configuracion.umbral_ruido_dbfs,
            referencia_a4=configuracion.referencia_a4,
            confianza_minima=configuracion.confianza_minima,
            nombre_detector=configuracion.detector,
        )

    def _elegido(self, dispositivos: list):
        """El dispositivo que el usuario eligió a mano, si sigue estando.

        Se busca por NOMBRE. macOS reasigna los índices cada vez que se enchufa o
        desenchufa algo, de modo que el índice guardado ayer puede ser hoy el
        micrófono del portátil, o no existir: eso último es lo que dejaba el
        afinador diciendo "reconéctalo" con el cable enchufado delante.
        """
        nombre = self.configuracion.dispositivo
        if nombre is None:
            return None
        return next((d for d in dispositivos if d.nombre == nombre), None)

    def _indice_objetivo(self, dispositivos: list) -> int | None:
        """Índice que hay que abrir, o None si no hay ninguno utilizable.

        Por orden: lo que el usuario eligió a mano mientras siga estando, y si no
        está -o no eligió nada- el Rocksmith buscado por nombre. Nunca la entrada
        por defecto del sistema: en este equipo sería el micrófono del portátil.

        Caer al cable cuando lo elegido desaparece es deliberado: el caso normal
        es que el usuario no haya elegido nada, y el caso raro -desenchufar la
        interfaz elegida- no debe dejarle sin afinador teniendo el cable ahí. El
        diagnóstico lo dice, no lo sustituye en silencio.
        """
        elegido = self._elegido(dispositivos)
        if elegido is not None:
            return elegido.indice
        cable = buscar_rocksmith(dispositivos)
        return None if cable is None else cable.indice

    def _abrir_captura(self) -> bool:
        """Intenta abrir la captura. Devuelve True si quedó abierta.

        No lanza: no poder abrir el dispositivo es un estado normal (el cable
        todavía no está enchufado), no un error del programa.
        """
        with self._candado_dispositivo:
            if self._captura is not None:
                return True
            dispositivos = self._listar()
            indice = self._indice_objetivo(dispositivos)
            if indice is None:
                self._ultimo_error_apertura = None
                return False
            captura = self._crear_captura(
                indice_dispositivo=indice, ganancia=self.configuracion.ganancia
            )
            if not captura.iniciar():
                self._ultimo_error_apertura = captura.ultimo_error
                self._anunciar_error_una_vez()
                return False
            self._ultimo_error_apertura = None
            self._error_anunciado = None
            self._captura = captura
            # Se decide AQUI y no al preguntarlo: aqui esta la lista que se acaba
            # de enumerar y el indice que de verdad se abrio, y enumerar
            # dispositivos es caro comparado con analizar una ventana (ver
            # INTERVALO_REVISION_DISPOSITIVO). Quien pregunta lo hace muchas veces
            # por segundo desde el carril.
            cable = buscar_rocksmith(dispositivos)
            self._entrada_es_el_cable = cable is not None and cable.indice == indice
            self._total_visto = -1
            self._instante_muestras = time.monotonic()
            return True

    def _anunciar_error_una_vez(self) -> None:
        """Imprime el último error del dispositivo solo cuando cambia.

        Con un reintento cada dos segundos, imprimirlo siempre llenaría la
        terminal de la misma línea repetida y escondería lo que sí importa. Lo
        usan tanto el fallo al abrir como el fallo a mitad de captura.
        """
        if self._ultimo_error_apertura != self._error_anunciado:
            self._error_anunciado = self._ultimo_error_apertura
            print(f"Aviso del dispositivo de audio: {self._ultimo_error_apertura}")

    def _cerrar_captura(self) -> None:
        """Cierra la captura si está abierta. Seguro de llamar varias veces."""
        with self._candado_dispositivo:
            if self._captura is None:
                return
            self._generacion += 1
            captura, self._captura = self._captura, None
            captura.detener()
            self._latencia_medida_ms = None
            # Sin captura abierta no hay entrada, asi que tampoco es el cable:
            # dejarlo puesto diria «puedes poner el fondo» con el jack fuera.
            self._entrada_es_el_cable = False

    def _dispositivo_sigue_presente(self) -> bool:
        """Verdadero si el dispositivo que se está usando sigue en la lista."""
        return self._indice_objetivo(self._listar()) is not None

    def iniciar(self) -> Diagnostico:
        """Arranca el hilo de trabajo y devuelve el diagnóstico.

        El hilo arranca **siempre**, haya o no dispositivo: es él quien abre la
        captura y quien la reabre si el cable aparece más tarde. Si el
        diagnóstico no es "ok", la sesión todavía no está capturando y el
        diagnóstico explica qué falta; el hilo seguirá intentándolo.
        """
        if self._hilo is not None and self._hilo.is_alive():
            return self.diagnostico()

        self._analizador = self._construir_analizador(self.configuracion)
        self._abrir_captura()
        self._parar.clear()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return self.diagnostico()

    def _publicar(self, resultado: ResultadoAnalisis, generacion: int) -> None:
        """Guarda el resultado si sigue siendo el de la generación vigente.

        Los observadores se avisan solo cuando el resultado se publica de
        verdad (la generación no cambió y no se pidió parar), nunca cuando se
        descarta por obsoleto. Se invocan fuera del candado, para no retener
        el lock de `_ultimo` mientras corre código ajeno, y cada uno en su
        propio try/except: un observador roto no puede tumbar el análisis del
        afinador ni impedir que se avise a los demás (esto vive dentro del
        try/except general de `_trabajar`, que ya cubre esta llamada).

        Ese fallo se **registra**, no se traga. Antes se hacía
        `except Exception: continue` y un error dentro del evaluador de
        ejercicios se veía como "el ejercicio no avanza", sin ninguna pista de
        por qué: el síntoma más caro de diagnosticar que puede tener este
        programa. Se anuncia una sola vez por mensaje distinto, porque a 47
        cuadros por segundo repetirlo llenaría la terminal y escondería lo demás.
        """
        publicado = False
        with self._candado:
            if generacion == self._generacion and not self._parar.is_set():
                self._ultimo = resultado
                publicado = True
        if publicado:
            instante = time.monotonic()
            with self._candado_observadores:
                observadores = list(self._observadores)
            for observador in observadores:
                try:
                    observador(resultado, instante)
                except Exception as error:
                    self._anunciar_fallo_observador(observador, error)
        self._anotar_nivel(resultado.nivel_db)

    def _anunciar_fallo_observador(self, observador: Callable, error: Exception) -> None:
        """Anuncia el fallo de un observador la primera vez que se ve.

        Se recuerda por observador y tipo de error, no por mensaje completo: un
        error cuyo texto cambia en cada cuadro (porque lleva un indice o un
        valor) llenaria la terminal a 47 lineas por segundo y haria crecer el
        conjunto sin cota. El mensaje concreto del primero si se imprime, que es
        el que sirve para diagnosticar.
        """
        nombre = getattr(observador, "__qualname__", repr(observador))
        clave = f"{nombre}:{type(error).__name__}"
        if clave in self._fallos_observador_anunciados:
            return
        self._fallos_observador_anunciados.add(clave)
        _registro.error("Fallo en el observador %s: %s: %s", nombre, type(error).__name__, error)

    def _esperar_el_cuadro(self, plazo: float) -> float:
        """Espera hasta `plazo` y devuelve el plazo del cuadro siguiente.

        **ESPERAR UN INTERVALO NO ES CORRER A UN INTERVALO, Y ESTABA MEDIDO.** El
        hilo pedía `plazo = self._esperar_el_cuadro(plazo)` en cada vuelta, y en un
        MacBook M1 `Event.wait(0,021)` tarda unos 27 ms: macOS agrupa los
        temporizadores y nunca despierta antes de lo pedido, así que cada vuelta
        pagaba su retraso Y el de todas las anteriores. Analizar la ventana cuesta
        0,15 ms, de modo que el trabajo no era la causa.

        Medido sobre el gemelo PERFECTO rasgueando los ocho acordes abiertos, el
        desfase que el carril le firma (ventana de acierto: 80 ms):

            cadena directa, 21 ms exactos   +20 +73 +63 +74 +64 +75 +65 +76 ms
            sesión, esperando fijo (26,3 ms) +44 +88 +83 +88 +79 +70 +82 +57 ms
            sesión, con plazo (21,0 ms)      +20 +33 +22 +76 +24 +75 +25 +77 ms

        Cuatro de ocho «tarde» antes, cero después, con el MISMO audio y el MISMO
        seguidor: ese sesgo entero era la cadencia del hilo. La mediana baja de
        +80,5 a +29 ms y la cadencia efectiva de 26,25 a 21,05.

        **LO QUE EL ARREGLO NO ARREGLA, Y HAY QUE LEERLO ANTES DE CELEBRARLO.**
        Repetida cuatro veces, la pasada da 0, 2, 2 y 0 acordes «tarde»: el sesgo
        se fue, el borde no. Un rasgueo gasta hasta 76 ms de los 80 en latencia
        honesta del detector -`DetectorAtaques` necesita un salto de 6 dB sobre el
        nivel de referencia, y ese salto tarda más cuando el acorde anterior sigue
        sonando-, así que la ventana no tiene sitio para un acorde ni con el reloj
        perfecto: los 11 ms de tembleque que queda del tiempo real bastan para
        pasarse. Eso YA NO es un defecto de este módulo, es la pregunta de diseño
        de si 80 ms es la ventana correcta para un gesto que cuesta 76, y está
        pendiente de decidir. Lo que este arreglo compra es que la pregunta se
        pueda hacer sin un error de reloj encima.

        Lo que hace: el plazo no se recalcula desde «ahora» sino que se ACUMULA, de
        forma que una vuelta lenta la recupera la siguiente en vez de arrastrarla.
        Es el mismo patrón que `nucleo.sintesis` usa para el metrónomo, con su
        misma guarda: si el plazo siguiente ya quedó más de un intervalo atrás, se
        realinea con el reloj. Sin esa guarda, un parón -el equipo dormido, una
        captura que se reabre- soltaría de golpe todas las vueltas atrasadas en
        ráfaga, que es peor que haberlas perdido.

        Devuelve el plazo siguiente para que la vuelta lo arrastre; `detener()`
        sigue cortando la espera, porque la espera sigue siendo la del evento.
        """
        self._parar.wait(max(0.0, plazo - self._reloj()))
        plazo += INTERVALO_ANALISIS
        ahora = self._reloj()
        if plazo < ahora - INTERVALO_ANALISIS:
            plazo = ahora + INTERVALO_ANALISIS
        return plazo

    def _trabajar(self) -> None:
        """Hilo de trabajo: abre, vigila y analiza.

        En cada vuelta, por orden:

        1. Si no hay captura abierta, intenta abrirla y espera antes de
           reintentar. Así el cable enchufado después de arrancar se recoge solo.
        2. Si la hay, comprueba de vez en cuando que el dispositivo sigue en la
           lista del sistema; si desapareció, cierra y vuelve al punto 1.
        3. Compara `total_capturado` con la vuelta anterior. Si no creció durante
           más de medio segundo, publica silencio y **deja de reprocesar** hasta
           que lleguen muestras nuevas: el buffer circular no caduca, así que
           reanalizar la misma ventana vieja congelaría la última nota en
           pantalla indefinidamente tras desconectar el cable en caliente.

        Todo el cuerpo va dentro de un try/except: una excepción a mitad de
        vuelta mataría el hilo en silencio y dejaría la sesión publicando el
        pasado con el stream todavía abierto. Se registra, se cierra la captura y
        se vuelve al punto 1, que es de donde la sesión sabe salir sola.

        La generación se lee al empezar la vuelta y se vuelve a comprobar justo
        antes de publicar. Entre ambas lecturas puede haber pasado un buen rato
        (analizar una ventana no es instantáneo), y en ese hueco `detener()` o
        `aplicar()` pueden haber cambiado la generación: si eso ocurrió, el
        resultado se calculó con una captura o un analizador que ya no son los
        vigentes y se descarta en vez de publicarse. Esto cubre tanto al hilo
        huérfano que sigue vivo tras un `join(timeout=...)` vencido como al hilo
        que estaba a mitad de una vuelta cuando `aplicar()` cambió el perfil.
        """
        proximo_intento = 0.0
        proxima_revision = time.monotonic() + self.intervalo_revision
        silencio_publicado = False
        # El plazo del cuadro siguiente, acumulado. Ver `_esperar_el_cuadro`.
        plazo = time.monotonic() + INTERVALO_ANALISIS

        while not self._parar.is_set():
            try:
                generacion = self._generacion
                ahora = time.monotonic()
                captura, analizador = self._captura, self._analizador

                if captura is None or analizador is None:
                    if ahora >= proximo_intento:
                        proximo_intento = ahora + self.espera_reintento
                        self._abrir_captura()
                    plazo = self._esperar_el_cuadro(plazo)
                    continue

                if ahora >= proxima_revision:
                    proxima_revision = ahora + self.intervalo_revision
                    if not self._dispositivo_sigue_presente():
                        self._cerrar_captura()
                        proximo_intento = ahora + self.espera_reintento
                        # Tras cerrar, la generación ya cambió: se publica con la
                        # nueva para que el silencio sí llegue a la pantalla.
                        self._publicar(self._resultado_silencio(), self._generacion)
                        plazo = self._esperar_el_cuadro(plazo)
                        continue

                total = captura.total_capturado
                if total > self._total_visto:
                    self._total_visto = total
                    self._instante_muestras = ahora
                    silencio_publicado = False
                    muestras = captura.leer_ventana(analizador.tamano_ventana)
                    if muestras is not None:
                        resultado = analizador.procesar(muestras)
                        self._medir_latencia(captura)
                        self._publicar(resultado, generacion)
                elif not silencio_publicado and (
                    ahora - self._instante_muestras > self.tiempo_sin_muestras
                ):
                    silencio_publicado = True
                    self._publicar(self._resultado_silencio(), generacion)

                plazo = self._esperar_el_cuadro(plazo)
            except Exception as error:
                # Una excepción a mitad de vuelta (un fallo de PortAudio, por
                # ejemplo) mataría el hilo en silencio, y con el hilo muerto la
                # sesión deja de publicar mientras el stream sigue abierto: otra
                # vez "ok" sobre una pantalla congelada. Se registra una sola
                # vez, se cierra la captura y la vuelta siguiente entra en el
                # camino de reintento, que es de donde se sale solo.
                self._ultimo_error_apertura = f"fallo durante la captura: {error}"
                self._anunciar_error_una_vez()
                self._cerrar_captura()
                proximo_intento = time.monotonic() + self.espera_reintento
                plazo = self._esperar_el_cuadro(plazo)

    def _resultado_silencio(self) -> ResultadoAnalisis:
        """Silencio por falta de muestras nuevas, no por falta de energía."""
        return ResultadoAnalisis(
            estado="silencio", frecuencia=0.0, confianza=0.0, nivel_db=-120.0
        )

    def _medir_latencia(self, captura) -> None:
        """Latencia entre la llegada del último bloque y la publicación, en ms.

            latencia = (t_publicación − t_último_bloque) · 1000

        Es la medida que pide la spec §6: el retardo real de la cadena
        callback → buffer → análisis → publicación, no el que promete el
        dispositivo.
        """
        instante = getattr(captura, "instante_ultimo_bloque", None)
        if instante is None:
            return
        self._latencia_medida_ms = max(0.0, (time.monotonic() - instante) * 1000.0)

    def ultimo_resultado(self) -> ResultadoAnalisis | None:
        """Resultado más reciente, o None si aún no hay ninguno."""
        with self._candado:
            return self._ultimo

    def registrar_observador(self, observador: Callable) -> None:
        """Suscribe una función que recibirá (resultado, instante) de cada análisis.

        El afinador lee el último resultado y le basta; el evaluador de
        ejercicios necesita TODOS los resultados, porque la detección de
        ataques trabaja sobre la evolución de la energía y muestrear perdería
        cuadros.

        El observador se invoca DENTRO del hilo de análisis, así que debe ser
        rápido: nada de red, nada de disco, nada que bloquee.
        """
        with self._candado_observadores:
            if observador not in self._observadores:
                self._observadores.append(observador)

    def quitar_observador(self, observador: Callable) -> None:
        """Desuscribe un observador. No falla si no estaba."""
        with self._candado_observadores:
            if observador in self._observadores:
                self._observadores.remove(observador)

    def aplicar(self, configuracion: Configuracion) -> Diagnostico:
        """Cambia la configuración en caliente y devuelve el diagnóstico resultante.

        El analizador se construye **antes** de adoptar la configuración: si la
        construcción falla (un detector inexistente, por ejemplo), la sesión
        queda exactamente como estaba en vez de inservible para el resto de su
        vida con una configuración a medio aplicar.

        Si cambia el dispositivo o la ganancia hay que reabrir el stream; para el
        resto basta con reconstruir el analizador, que es instantáneo. La
        configuración nueva se adopta pase lo que pase, incluida una reapertura
        que falle: el usuario pidió ese dispositivo, y revertirle la elección en
        silencio sería otra mentira. Devolver el diagnóstico es la única forma de
        que quien llama se entere de que la reapertura falló y con qué error del
        sistema.
        """
        configuracion.validar()
        try:
            analizador = self._construir_analizador(configuracion)
        except KeyError as error:
            # El registro de detectores o de perfiles no la reconoce. Nada se ha
            # tocado todavía, así que la sesión sigue operativa.
            raise ValueError(str(error)) from error

        reabrir = (
            configuracion.dispositivo != self.configuracion.dispositivo
            or configuracion.ganancia != self.configuracion.ganancia
        )
        self.configuracion = configuracion
        self._instante_bajo_umbral = None

        if self._hilo is None:
            # Sesión aún sin arrancar: solo se guarda la configuración.
            return self.diagnostico()

        if reabrir:
            self._cerrar_captura()
        self._generacion += 1
        self._analizador = analizador
        with self._candado:
            self._ultimo = None
        if reabrir:
            # Reabrir aquí y no dejarlo al hilo permite devolver un diagnóstico
            # verdadero a quien acaba de cambiar el dispositivo.
            self._abrir_captura()
        return self.diagnostico()

    def calibrar(self, segundos: float = 2.0) -> float:
        """Mide el piso de ruido durante unos segundos y devuelve el umbral sugerido.

        El usuario debe estar en silencio mientras dura. No modifica la
        configuración: devolver el valor y dejar que el usuario lo acepte es
        preferible a cambiarle los ajustes por sorpresa.

        La captura se referencia una sola vez, al principio, igual que `ventana`,
        y en cada vuelta se comprueba que sigue siendo la vigente. Este bucle
        puede tardar segundos; si mientras tanto otro hilo llama a `detener()` (o
        `aplicar()` reabre con una captura distinta), `self._captura` cambia por
        debajo. Sin esta comprobación, la vuelta siguiente llamaría
        `leer_ventana()` sobre `None` (o sobre una captura ya cerrada) y
        reventaría con `AttributeError` a mitad de la calibración.
        """
        if not self.activa or self._analizador is None:
            return self.configuracion.umbral_ruido_dbfs
        captura = self._captura
        ventana = self._analizador.tamano_ventana
        niveles = []
        final = time.monotonic() + segundos
        while time.monotonic() < final:
            if captura is not self._captura:
                break
            muestras = captura.leer_ventana(ventana)
            if muestras is not None:
                niveles.append(nivel_dbfs(muestras))
            time.sleep(0.05)
        return calibrar_umbral(niveles)

    def detener(self) -> None:
        """Para el hilo y cierra el dispositivo. Seguro de llamar varias veces.

        La generación se incrementa antes de tocar nada más. Si `join(timeout=...)`
        vence con el hilo aún vivo, ese hilo huérfano sigue corriendo: al terminar
        su vuelta verá que la generación ya no coincide con la que leyó al
        empezarla y descartará su resultado, en vez de publicarlo después de que
        esta llamada ya haya dejado la sesión como parada.
        """
        self._generacion += 1
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
        self._cerrar_captura()
        self._analizador = None
        self._instante_bajo_umbral = None
        self._latencia_medida_ms = None
        with self._candado:
            self._ultimo = None
