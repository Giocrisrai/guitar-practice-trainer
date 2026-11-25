import threading
import time

import numpy as np
import pytest

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.configuracion import Configuracion
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
MICROFONO = DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)
OTRO_DISPOSITIVO = DispositivoAudio(7, "Otra entrada de audio", 1, 48000.0)
FS = 48000


class CapturaFalsa:
    """Doble de CapturaAudio que devuelve siempre la misma ventana.

    Imita también el contador de muestras y la marca de tiempo del último bloque,
    que es lo que la sesión usa para saber si el dispositivo sigue entregando
    audio y para medir la latencia real.
    """

    def __init__(self, frecuencia: float = 82.41, amplitud: float = 0.3, **kwargs):
        self.frecuencia = frecuencia
        self.amplitud = amplitud
        self.iniciada = False
        self.detenida = False
        self.ganancia = kwargs.get("ganancia", 1.0)
        self.ultimo_error = None
        self.latencia_ms = 12.0
        self.indice_dispositivo = kwargs.get("indice_dispositivo")
        self._total = 0
        self.instante_ultimo_bloque = time.monotonic()

    @property
    def total_capturado(self) -> int:
        """Cada consulta simula que siguen llegando bloques del dispositivo."""
        self._total += 512
        self.instante_ultimo_bloque = time.monotonic()
        return self._total

    def iniciar(self) -> bool:
        self.iniciada = True
        return True

    def detener(self) -> None:
        self.detenida = True

    def leer_ventana(self, n: int):
        t = np.arange(n) / FS
        return (self.amplitud * np.sin(2 * np.pi * self.frecuencia * t)).astype(np.float32)


class CapturaQueSeCongela(CapturaFalsa):
    """Doble que deja de entregar bloques en cuanto se le llama `congelar()`.

    Reproduce la desconexión en caliente del cable: el callback deja de escribir
    pero el buffer circular conserva las últimas muestras, que es lo que hacía
    que el afinador congelase la última nota para siempre.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.congelada = False

    def congelar(self) -> None:
        self.congelada = True

    @property
    def total_capturado(self) -> int:
        if self.congelada:
            return self._total
        return CapturaFalsa.total_capturado.fget(self)


class CapturaQueSeRompe(CapturaFalsa):
    """Doble que revienta al leer mientras esté averiada.

    Es lo que haría un fallo de PortAudio a mitad de vuelta. Mientras dura la
    avería tampoco se deja abrir, igual que un dispositivo que el sistema ya ha
    soltado, para que el estado de la sesión durante el fallo sea inequívoco.
    """

    def __init__(self, averia: dict, **kwargs):
        super().__init__(**kwargs)
        self.averia = averia

    def iniciar(self) -> bool:
        if self.averia["rota"]:
            self.ultimo_error = "el dispositivo no responde"
            return False
        return super().iniciar()

    def leer_ventana(self, n: int):
        if self.averia["rota"]:
            raise RuntimeError("PortAudio devolvió un error a mitad de lectura")
        return super().leer_ventana(n)


class CapturaLenta(CapturaFalsa):
    """Doble cuya lectura tarda más que el timeout de join() en detener()."""

    def __init__(self, retraso: float = 1.2, **kwargs):
        super().__init__(**kwargs)
        self.retraso = retraso

    def leer_ventana(self, n: int):
        time.sleep(self.retraso)
        return super().leer_ventana(n)


class CapturaQueFalla(CapturaFalsa):
    """Doble que simula un dispositivo que no se puede abrir."""

    def iniciar(self) -> bool:
        self.ultimo_error = "dispositivo ocupado"
        return False


def esperar_resultado(sesion, intentos: int = 100):
    for _ in range(intentos):
        resultado = sesion.ultimo_resultado()
        if resultado is not None and resultado.estado == "nota":
            return resultado
        time.sleep(0.02)
    return sesion.ultimo_resultado()


def test_la_sesion_analiza_en_segundo_plano():
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, CABLE],
    )
    assert sesion.iniciar().estado == "ok"
    resultado = esperar_resultado(sesion)
    assert resultado is not None
    assert resultado.nota == "E2"
    sesion.detener()
    assert sesion.activa is False


def test_sin_dispositivos_la_sesion_no_arranca_y_explica_por_que():
    sesion = Sesion(
        Configuracion(),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [],
    )
    diagnostico = sesion.iniciar()
    assert diagnostico.estado == "sin_permiso"
    assert sesion.activa is False
    sesion.detener()  # el hilo de reintento arranca siempre: no dejarlo vivo


def test_sin_dispositivo_elegido_se_usa_el_rocksmith():
    """Nunca la entrada por defecto: sería el micrófono del MacBook."""
    creadas = []

    def crear(**kw):
        captura = CapturaFalsa(**kw)
        creadas.append(kw)
        return captura

    sesion = Sesion(Configuracion(), crear_captura=crear, listar=lambda: [MICROFONO, CABLE])
    sesion.iniciar()
    assert creadas[0]["indice_dispositivo"] == 3
    sesion.detener()


def test_cambiar_de_perfil_reinicia_el_analisis():
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(frecuencia=30.87, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    sesion.aplicar(Configuracion(dispositivo=NOMBRE_ROCKSMITH, perfil="bajo_5"))
    resultado = esperar_resultado(sesion)
    assert resultado.nota == "B0"
    sesion.detener()


def test_la_calibracion_devuelve_un_umbral_sobre_el_ruido():
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(amplitud=0.0002, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    umbral = sesion.calibrar(segundos=0.2)
    assert -75.0 < umbral < -45.0
    sesion.detener()


def test_si_lo_elegido_desaparece_se_usa_el_cable_y_se_dice():
    """Antes esto se quedaba en "sin_dispositivo" con el cable enchufado delante.

    Quedarse parado era defendible mientras el dispositivo se guardaba por
    indice, porque un indice que cambia no dice nada; ahora que se guarda por
    nombre, que lo elegido no este significa que de verdad no esta, y dejar al
    usuario sin afinador teniendo el cable ahi no ayuda a nadie. Se usa el cable,
    pero el diagnostico lo dice: sustituir en silencio seria peor.
    """
    sesion = Sesion(
        Configuracion(dispositivo="Una interfaz que ya no esta"),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, CABLE],
    )
    diagnostico = sesion.iniciar()
    assert diagnostico.estado == "ok"
    assert sesion.activa is True
    assert "no está" in diagnostico.mensaje
    assert NOMBRE_ROCKSMITH in diagnostico.mensaje
    sesion.detener()


def test_sin_cable_ni_dispositivo_elegido_se_dice_que_no_hay_nada():
    sesion = Sesion(
        Configuracion(dispositivo="Una interfaz que ya no esta"),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO],
    )
    diagnostico = sesion.iniciar()
    assert diagnostico.estado == "sin_dispositivo"
    assert sesion.activa is False
    sesion.detener()


def test_detener_dos_veces_no_falla():
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    sesion.detener()
    sesion.detener()


def test_calibrar_no_revienta_si_detener_corre_en_paralelo():
    """detener() puede poner self._captura a None a mitad de la calibración."""
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(amplitud=0.0002, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()

    resultado: dict = {}

    def calibrar_en_hilo():
        try:
            resultado["umbral"] = sesion.calibrar(segundos=1.0)
        except Exception as error:  # queremos capturar cualquier fallo, no solo AttributeError
            resultado["error"] = error

    hilo = threading.Thread(target=calibrar_en_hilo)
    hilo.start()
    time.sleep(0.15)
    sesion.detener()
    hilo.join(timeout=2.0)

    assert "error" not in resultado, f"calibrar() lanzó: {resultado.get('error')!r}"
    assert "umbral" in resultado


def test_hilo_huerfano_no_publica_tras_detener():
    """Un hilo que sigue vivo tras el timeout de join() no debe publicar nada.

    detener() espera como mucho un segundo (join(timeout=1.0)). Si la lectura
    tarda más, el hilo queda huérfano corriendo en segundo plano; cuando por fin
    termina su vuelta, la generación ya no coincide con la que leyó al empezarla
    y su resultado debe descartarse en vez de publicarse.
    """
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaLenta(retraso=1.2, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    time.sleep(0.1)  # asegurar que el hilo ya entró en leer_ventana()
    sesion.detener()
    assert sesion.ultimo_resultado() is None
    time.sleep(0.6)  # tiempo de sobra para que el hilo huérfano termine su vuelta
    assert sesion.ultimo_resultado() is None


def test_aplicar_devuelve_diagnostico_y_no_revierte_si_la_reapertura_falla():
    """El usuario pidió ese dispositivo; si falla, se le informa pero no se revierte."""

    def crear(**kw):
        if kw["indice_dispositivo"] == 3:
            return CapturaFalsa(**kw)
        return CapturaQueFalla(**kw)

    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=crear,
        listar=lambda: [CABLE, OTRO_DISPOSITIVO],
    )
    sesion.iniciar()

    diagnostico = sesion.aplicar(Configuracion(dispositivo="Otra entrada de audio"))

    assert diagnostico.estado != "ok"
    assert sesion.configuracion.dispositivo == "Otra entrada de audio"
    sesion.detener()


def esperar(condicion, intentos: int = 200, pausa: float = 0.02) -> bool:
    """Espera activa a que se cumpla una condición. Devuelve si se cumplió."""
    for _ in range(intentos):
        if condicion():
            return True
        time.sleep(pausa)
    return condicion()


def test_la_sesion_se_recupera_sola_cuando_el_dispositivo_aparece_despues():
    """Arrancar sin cable y enchufarlo después debe bastar (spec §5).

    El hilo de trabajo es el dueño del ciclo de vida del dispositivo: si al
    arrancar no hay nada que abrir, reintenta hasta que lo haya. Obligar a
    reiniciar el programa sería un castigo desproporcionado.
    """
    dispositivos = [MICROFONO]
    capturas = []

    def crear(**kw):
        captura = CapturaFalsa(**kw)
        capturas.append(captura)
        return captura

    sesion = Sesion(Configuracion(), crear_captura=crear, listar=lambda: list(dispositivos))
    sesion.espera_reintento = 0.05

    assert sesion.iniciar().estado != "ok"
    assert sesion.activa is False

    dispositivos.append(CABLE)  # el usuario enchufa el cable

    assert esperar(lambda: sesion.activa), "la sesión no reabrió el dispositivo sola"
    assert capturas[-1].indice_dispositivo == CABLE.indice
    assert sesion.diagnostico().estado == "ok"
    assert esperar(lambda: sesion.ultimo_resultado() is not None)
    sesion.detener()


def test_el_diagnostico_no_dice_ok_mientras_no_se_captura():
    """Con el dispositivo en la lista pero sin poder abrirlo, "ok" sería mentira."""
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaQueFalla(**kw),
        listar=lambda: [CABLE],
    )
    sesion.espera_reintento = 0.05

    diagnostico = sesion.iniciar()
    assert sesion.activa is False
    assert diagnostico.estado != "ok"
    assert diagnostico.estado == "sin_dispositivo"
    assert "dispositivo ocupado" in diagnostico.accion

    time.sleep(0.15)  # el hilo reintenta y sigue fallando: tampoco ahora es "ok"
    assert sesion.diagnostico().estado != "ok"
    sesion.detener()


def test_sin_muestras_nuevas_el_resultado_pasa_a_silencio():
    """Al desconectar el cable en caliente no se congela la última nota.

    El buffer circular no caduca: sin esta comprobación el analizador reprocesa
    la misma ventana vieja y la aguja se queda clavada en E2 para siempre.
    """
    captura = None

    def crear(**kw):
        nonlocal captura
        captura = CapturaQueSeCongela(**kw)
        return captura

    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH), crear_captura=crear, listar=lambda: [CABLE]
    )
    sesion.tiempo_sin_muestras = 0.2

    sesion.iniciar()
    resultado = esperar_resultado(sesion)
    assert resultado is not None and resultado.estado == "nota"

    captura.congelar()

    assert esperar(
        lambda: sesion.ultimo_resultado().estado == "silencio"
    ), "el resultado se quedó congelado en la última nota"
    sesion.detener()


def test_la_falta_de_senal_solo_se_avisa_tras_varios_segundos():
    """spec §5: sin_senal exige más de 5 s seguidos bajo el umbral.

    Avisar al instante haría parpadear "sube el volumen" entre nota y nota, y un
    aviso que cría lobo se deja de leer. Aquí se acorta la espera para no
    encadenar cinco segundos de reloj en la prueba.
    """
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(amplitud=0.0002, **kw),
        listar=lambda: [CABLE],
    )
    sesion.segundos_sin_senal = 0.3
    sesion.iniciar()

    assert sesion.diagnostico(-80.0).estado != "sin_senal"
    time.sleep(0.4)
    assert sesion.diagnostico(-80.0).estado == "sin_senal"

    # Una sola lectura con señal reinicia la cuenta: el usuario volvió a tocar.
    assert sesion.diagnostico(-30.0).estado != "sin_senal"
    assert sesion.diagnostico(-80.0).estado != "sin_senal"
    sesion.detener()


def test_la_latencia_publicada_es_la_medida_no_la_del_dispositivo():
    """spec §6: se mide el tiempo entre la llegada del bloque y la emisión."""
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    assert esperar(lambda: sesion.ultimo_resultado() is not None)

    assert sesion.latencia_ms > 0.0
    assert sesion.latencia_ms < 200.0
    # 12 ms es lo que reporta el dispositivo falso: lo que se muestra es la medida.
    assert sesion.latencia_dispositivo_ms == 12.0
    assert sesion.latencia_ms != sesion.latencia_dispositivo_ms
    sesion.detener()


def test_una_configuracion_invalida_no_deja_la_sesion_inservible():
    """aplicar() construye el analizador antes de adoptar la configuración."""
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()

    try:
        sesion.aplicar(Configuracion(dispositivo=NOMBRE_ROCKSMITH, detector="inexistente"))
        raise AssertionError("se esperaba ValueError")
    except ValueError:
        pass

    assert sesion.configuracion.detector == "yin"
    assert sesion.aplicar(Configuracion(dispositivo=NOMBRE_ROCKSMITH, perfil="bajo_4")).estado == "ok"
    assert esperar(lambda: sesion.ultimo_resultado() is not None)
    sesion.detener()


def test_un_fallo_al_leer_no_mata_el_hilo_y_la_sesion_se_recupera():
    """Una excepción a mitad de vuelta no puede matar el hilo en silencio.

    Con el hilo muerto y el stream todavía abierto, la sesión dejaría de
    publicar mientras el diagnóstico seguiría diciendo "ok": la misma mentira
    que la reconexión automática vino a eliminar, solo que por otra causa.
    """
    averia = {"rota": False}
    sesion = Sesion(
        Configuracion(dispositivo=NOMBRE_ROCKSMITH),
        crear_captura=lambda **kw: CapturaQueSeRompe(averia, **kw),
        listar=lambda: [CABLE],
    )
    sesion.espera_reintento = 0.05

    assert sesion.iniciar().estado == "ok"
    assert esperar_resultado(sesion).estado == "nota"

    averia["rota"] = True

    assert esperar(lambda: not sesion.activa), "la captura rota no se cerró"
    assert sesion._hilo.is_alive(), "el hilo murió con la excepción"
    assert sesion.diagnostico().estado != "ok"

    averia["rota"] = False

    assert esperar(lambda: sesion.activa), "la sesión no se recuperó sola"
    assert sesion.diagnostico().estado == "ok"
    assert esperar(
        lambda: sesion.ultimo_resultado() is not None
        and sesion.ultimo_resultado().estado == "nota"
    )
    sesion.detener()


# ---------------------------------------------------------------------------
# Resolucion del dispositivo por nombre (macOS renumera al reconectar el USB)
# ---------------------------------------------------------------------------

CABLE_OTRO_INDICE = DispositivoAudio(1, NOMBRE_ROCKSMITH, 1, 48000.0)


def test_el_cable_se_recoge_aunque_macos_le_cambie_el_indice():
    """El caso real que rompio al usuario: config guardada con el indice 0 y el
    cable reconectado en el 1. Guardar un numero que el sistema reasigna al
    enchufar convierte "reconecta el cable" en un callejon sin salida.
    """
    sesion = Sesion(
        Configuracion(dispositivo="Rocksmith USB Guitar Adapter"),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, CABLE_OTRO_INDICE],
    )
    assert sesion._indice_objetivo([MICROFONO, CABLE_OTRO_INDICE]) == 1


def test_sin_eleccion_gana_el_cable_aunque_haya_otras_entradas():
    sesion = Sesion(
        Configuracion(dispositivo=None),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, OTRO_DISPOSITIVO, CABLE_OTRO_INDICE],
    )
    assert sesion._indice_objetivo([MICROFONO, OTRO_DISPOSITIVO, CABLE_OTRO_INDICE]) == 1


def test_lo_elegido_a_mano_se_respeta_mientras_exista():
    sesion = Sesion(
        Configuracion(dispositivo="MacBook Pro Microphone"),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, CABLE_OTRO_INDICE],
    )
    assert sesion._indice_objetivo([MICROFONO, CABLE_OTRO_INDICE]) == MICROFONO.indice


def test_si_lo_elegido_desaparece_se_cae_al_cable():
    """Desenchufar la interfaz elegida no debe dejar al usuario sin afinador
    cuando el cable esta ahi mismo.
    """
    sesion = Sesion(
        Configuracion(dispositivo="Una interfaz que ya no esta"),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, CABLE_OTRO_INDICE],
    )
    assert sesion._indice_objetivo([MICROFONO, CABLE_OTRO_INDICE]) == 1


def test_un_indice_viejo_guardado_se_migra_a_nombre():
    """Los config_local.json que ya existen traen un numero. Al cargarlos el
    numero se descarta -no significa nada entre reconexiones- y se queda en
    automatico, que es lo que el usuario querria.
    """
    from servidor.configuracion import Configuracion as C

    assert C.desde_dict({"dispositivo": 0}).dispositivo is None
    assert C.desde_dict({"dispositivo": "Rocksmith USB Guitar Adapter"}).dispositivo == (
        "Rocksmith USB Guitar Adapter"
    )


# -- la cadencia del hilo de analisis -----------------------------------------
#
# El hilo pedia `wait(INTERVALO_ANALISIS)` en cada vuelta y corria a 26-30 ms,
# porque `Event.wait` nunca despierta antes de lo pedido y cada vuelta pagaba su
# retraso y el de todas las anteriores. El arreglo -plazo acumulado- esta medido
# en `Sesion._esperar_el_cuadro`; estas pruebas vigilan su aritmetica con un
# reloj falso, porque el reloj de verdad no es afirmable.


class EsperaApuntada:
    """Doble de `_parar` que apunta lo que se le pidio esperar y no espera."""

    def __init__(self):
        self.esperas = []

    def wait(self, plazo):
        self.esperas.append(plazo)
        return False

    def is_set(self):
        return False


def _sesion_con_reloj(instantes):
    """Una sesion cuyo reloj inyectado devuelve `instantes` en orden.

    Por la costura y no con `monkeypatch`: parchear `servidor.sesion.time.monotonic`
    parchea el modulo `time` COMPARTIDO, asi que afecta a los hilos que otras
    pruebas dejaron vivos. Se intento primero y dejo la suite intermitente -un
    `IndexError: pop from empty list` en un hilo ajeno-.
    """
    restantes = list(instantes)
    sesion = Sesion(
        Configuracion(),
        crear_captura=lambda **_: None,
        listar=lambda: [],
        reloj=lambda: restantes.pop(0),
    )
    espera = EsperaApuntada()
    sesion._parar = espera
    return sesion, espera


def test_una_vuelta_puntual_espera_lo_que_le_queda_del_intervalo():
    """La vuelta costo 5 ms, asi que espera los 16 que faltan de los 21."""
    # El reloj se lee dos veces: al descontar la espera y al comprobar la deriva.
    sesion, espera = _sesion_con_reloj([100.005, 100.021])
    siguiente = sesion._esperar_el_cuadro(100.021)
    assert espera.esperas == [pytest.approx(0.016)]
    assert siguiente == pytest.approx(100.042)


def test_una_vuelta_lenta_la_recupera_la_siguiente_en_vez_de_arrastrarla():
    """ESTO es el arreglo: el plazo se acumula, no se recalcula desde ahora.

    La vuelta se paso 8 ms del plazo (llego a 100.029 con plazo en 100.021). No
    espera nada, y el plazo siguiente sigue siendo el que tocaba -100.042-, no
    «ahora mas 21», que seria 100.050. Esos 8 ms los recupera la vuelta siguiente,
    que es justo lo que el `wait` fijo no hacia: con el fijo cada retraso se
    sumaba al de todos los anteriores y la cadencia derivaba a 26-30 ms.
    """
    sesion, espera = _sesion_con_reloj([100.029, 100.029])
    siguiente = sesion._esperar_el_cuadro(100.021)
    assert espera.esperas == [0.0]
    assert siguiente == pytest.approx(100.042)


def test_un_paron_mas_largo_que_un_intervalo_realinea_en_vez_de_soltar_la_rafaga():
    """Sin esta guarda, un paron soltaria de golpe todas las vueltas atrasadas.

    El equipo se durmio medio segundo: el plazo siguiente (100.042) quedo mucho
    mas de un intervalo por detras del reloj (100.500). Se realinea con el reloj
    en vez de dejar que las vueltas corran sin esperar hasta ponerse al dia, que
    es peor que haberlas perdido -y es el mismo criterio que `nucleo.sintesis`
    aplica al metronomo-.
    """
    sesion, espera = _sesion_con_reloj([100.500, 100.500])
    siguiente = sesion._esperar_el_cuadro(100.021)
    assert espera.esperas == [0.0]
    assert siguiente == pytest.approx(100.521)
