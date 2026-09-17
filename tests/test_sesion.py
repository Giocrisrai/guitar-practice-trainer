import threading
import time

import numpy as np

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.configuracion import Configuracion
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
MICROFONO = DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)
OTRO_DISPOSITIVO = DispositivoAudio(7, "Otra entrada de audio", 1, 48000.0)
FS = 48000


class CapturaFalsa:
    """Doble de CapturaAudio que devuelve siempre la misma ventana."""

    def __init__(self, frecuencia: float = 82.41, amplitud: float = 0.3, **kwargs):
        self.frecuencia = frecuencia
        self.amplitud = amplitud
        self.iniciada = False
        self.detenida = False
        self.ganancia = kwargs.get("ganancia", 1.0)
        self.ultimo_error = None
        self.latencia_ms = 12.0

    def iniciar(self) -> bool:
        self.iniciada = True
        return True

    def detener(self) -> None:
        self.detenida = True

    def leer_ventana(self, n: int):
        t = np.arange(n) / FS
        return (self.amplitud * np.sin(2 * np.pi * self.frecuencia * t)).astype(np.float32)


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
        Configuracion(dispositivo=3),
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
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(frecuencia=30.87, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    sesion.aplicar(Configuracion(dispositivo=3, perfil="bajo_5"))
    resultado = esperar_resultado(sesion)
    assert resultado.nota == "B0"
    sesion.detener()


def test_la_calibracion_devuelve_un_umbral_sobre_el_ruido():
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(amplitud=0.0002, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    umbral = sesion.calibrar(segundos=0.2)
    assert -75.0 < umbral < -45.0
    sesion.detener()


def test_dispositivo_elegido_que_desaparecio_no_cae_de_vuelta_al_rocksmith():
    """Si el índice elegido ya no está en la lista, hay que decirlo, no sustituirlo."""
    sesion = Sesion(
        Configuracion(dispositivo=99),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, CABLE],
    )
    diagnostico = sesion.iniciar()
    assert diagnostico.estado == "sin_dispositivo"
    assert sesion.activa is False


def test_detener_dos_veces_no_falla():
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    sesion.detener()
    sesion.detener()


def test_calibrar_no_revienta_si_detener_corre_en_paralelo():
    """detener() puede poner self._captura a None a mitad de la calibración."""
    sesion = Sesion(
        Configuracion(dispositivo=3),
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
        Configuracion(dispositivo=3),
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
        Configuracion(dispositivo=3),
        crear_captura=crear,
        listar=lambda: [CABLE, OTRO_DISPOSITIVO],
    )
    sesion.iniciar()

    diagnostico = sesion.aplicar(Configuracion(dispositivo=7))

    assert diagnostico.estado != "ok"
    assert sesion.configuracion.dispositivo == 7
    sesion.detener()
