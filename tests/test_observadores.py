import logging
import time

import numpy as np

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.configuracion import Configuracion
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000


class CapturaFalsa:
    def __init__(self, **kwargs):
        self.ultimo_error = None
        self.latencia_ms = 12.0
        self.total_capturado = 0

    def iniciar(self) -> bool:
        return True

    def detener(self) -> None:
        pass

    def leer_ventana(self, n: int):
        self.total_capturado += n
        t = np.arange(n) / FS
        return (0.3 * np.sin(2 * np.pi * 82.41 * t)).astype(np.float32)


def sesion_falsa() -> Sesion:
    return Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )


def test_un_observador_recibe_los_resultados():
    recibidos = []
    sesion = sesion_falsa()
    sesion.registrar_observador(lambda resultado, instante: recibidos.append(resultado))
    sesion.iniciar()
    time.sleep(0.3)
    sesion.detener()
    assert len(recibidos) > 3


def test_el_observador_recibe_tambien_el_instante():
    instantes = []
    sesion = sesion_falsa()
    sesion.registrar_observador(lambda resultado, instante: instantes.append(instante))
    sesion.iniciar()
    time.sleep(0.3)
    sesion.detener()
    assert instantes == sorted(instantes)


def test_quitar_el_observador_deja_de_entregarle():
    recibidos = []

    def observador(resultado, instante):
        recibidos.append(resultado)

    sesion = sesion_falsa()
    sesion.registrar_observador(observador)
    sesion.iniciar()
    time.sleep(0.2)
    sesion.quitar_observador(observador)
    cuantos = len(recibidos)
    time.sleep(0.2)
    sesion.detener()
    assert len(recibidos) == cuantos


def test_un_observador_que_revienta_no_mata_el_hilo_ni_a_los_demas():
    """Un observador roto no puede tumbar el analisis del afinador."""
    buenos = []

    def roto(resultado, instante):
        raise RuntimeError("observador defectuoso")

    sesion = sesion_falsa()
    sesion.registrar_observador(roto)
    sesion.registrar_observador(lambda resultado, instante: buenos.append(resultado))
    sesion.iniciar()
    time.sleep(0.3)
    assert sesion.activa is True
    assert len(buenos) > 3
    sesion.detener()


def test_sin_observadores_la_sesion_funciona_igual():
    sesion = sesion_falsa()
    sesion.iniciar()
    time.sleep(0.2)
    assert sesion.ultimo_resultado() is not None
    sesion.detener()


def test_el_fallo_de_un_observador_se_registra(caplog):
    """`except Exception: continue` se tragaba el fallo: un error dentro del
    evaluador de ejercicios se veia como "el ejercicio no avanza" sin ninguna
    pista de por que. Ahora se registra, una sola vez por observador y tipo.
    """

    def observador_roto(resultado, instante):
        raise RuntimeError("el evaluador se atraganto")

    sesion = sesion_falsa()
    sesion.registrar_observador(observador_roto)
    with caplog.at_level(logging.ERROR, logger="servidor.sesion"):
        sesion.iniciar()
        time.sleep(0.3)
        sesion.detener()

    registrado = caplog.text
    assert "observador_roto" in registrado
    assert "RuntimeError" in registrado
    assert "el evaluador se atraganto" in registrado
    # Una sola linea, aunque el analisis publique a unos 47 Hz.
    assert registrado.count("el evaluador se atraganto") == 1


def test_un_observador_cuyo_error_cambia_de_texto_solo_se_registra_una_vez(caplog):
    """Se recuerda por observador y tipo de error, no por mensaje: un error que
    lleva un contador en el texto llenaria la terminal a 47 lineas por segundo y
    haria crecer sin cota el conjunto de fallos ya anunciados.
    """
    cuenta = {"n": 0}

    def observador_parlanchin(resultado, instante):
        cuenta["n"] += 1
        raise RuntimeError(f"fallo numero {cuenta['n']}")

    sesion = sesion_falsa()
    sesion.registrar_observador(observador_parlanchin)
    with caplog.at_level(logging.ERROR, logger="servidor.sesion"):
        sesion.iniciar()
        time.sleep(0.3)
        sesion.detener()

    assert cuenta["n"] > 1, "el observador tiene que haber fallado varias veces"
    assert caplog.text.count("observador_parlanchin") == 1


def test_suscribirse_y_desuscribirse_mientras_el_analisis_corre_no_revienta():
    """La lista se muta desde el hilo HTTP y se recorre desde el de analisis."""
    import threading

    sesion = sesion_falsa()
    sesion.iniciar()
    parar = threading.Event()
    fallos = []

    def observador(resultado, instante):
        pass

    def alternar():
        while not parar.is_set():
            try:
                sesion.registrar_observador(observador)
                sesion.quitar_observador(observador)
            except Exception as error:  # pragma: no cover
                fallos.append(error)
                return

    hilo = threading.Thread(target=alternar, daemon=True)
    hilo.start()
    time.sleep(0.4)
    parar.set()
    hilo.join(timeout=2.0)
    sesion.detener()

    assert fallos == []
