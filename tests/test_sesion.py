import time

import numpy as np

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.configuracion import Configuracion
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
MICROFONO = DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)
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


def test_detener_dos_veces_no_falla():
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    sesion.detener()
    sesion.detener()
