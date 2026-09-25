import time

import numpy as np
import pytest

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.sintesis import SalidaAudio
from servidor.configuracion import Configuracion
from servidor.ejercicios import GENERADORES, SesionPractica
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


class StreamSalidaFalso:
    def __init__(self, **kwargs):
        self.cerrado = False

    def start(self):
        pass

    def write(self, muestras):
        pass

    def stop(self):
        pass

    def close(self):
        self.cerrado = True


def practica() -> SesionPractica:
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    return SesionPractica(sesion, salida=SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso()))


def test_las_cuatro_familias_estan_registradas():
    assert set(GENERADORES) == {"escala", "arpegio", "intervalo", "lectura"}


def test_generar_devuelve_un_ejercicio_de_la_familia_pedida():
    sesion = practica()
    ejercicio = sesion.generar("escala", raiz_midi=48, tipo="mayor")
    assert len(ejercicio) > 0
    assert "escala" in ejercicio.clave
    sesion.detener()


def test_una_familia_inexistente_se_rechaza():
    sesion = practica()
    with pytest.raises(ValueError, match="familia"):
        sesion.generar("solfeo")
    sesion.detener()


def test_un_parametro_invalido_se_propaga_con_su_mensaje():
    sesion = practica()
    with pytest.raises(ValueError, match="escala"):
        sesion.generar("escala", tipo="inventada")
    sesion.detener()


def test_iniciar_suscribe_el_evaluador_al_flujo_de_audio():
    sesion = practica()
    ejercicio = sesion.generar("escala", traste_maximo=4)
    sesion.iniciar(ejercicio, con_metronomo=False)
    assert sesion.activa is True
    time.sleep(0.3)
    assert sesion.estado()["evaluacion"]["total"] == len(ejercicio)
    sesion.detener()


def test_detener_desuscribe_y_para_el_metronomo():
    sesion = practica()
    ejercicio = sesion.generar("escala", traste_maximo=4)
    sesion.iniciar(ejercicio)
    sesion.detener()
    assert sesion.activa is False
    assert sesion.ejercicio is None


def test_el_estado_sin_ejercicio_lo_dice_sin_reventar():
    sesion = practica()
    estado = sesion.estado()
    assert estado["ejercicio"] is None
    assert estado["evaluacion"] is None
    sesion.detener()


def test_el_estado_trae_ejercicio_evaluacion_e_informe():
    sesion = practica()
    ejercicio = sesion.generar("lectura", repeticiones=3, semilla=1)
    sesion.iniciar(ejercicio, con_metronomo=False)
    estado = sesion.estado()
    assert set(estado) >= {"ejercicio", "evaluacion", "informe", "metronomo"}
    sesion.detener()


def test_sin_salida_de_audio_el_ejercicio_arranca_igual_sin_metronomo():
    """La spec es explicita: quedarse sin altavoces degrada, no aborta."""
    sesion_audio = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion_audio.iniciar()

    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    sesion = SesionPractica(sesion_audio, salida=SalidaAudio(abrir_stream=abrir_que_falla))
    ejercicio = sesion.generar("lectura", repeticiones=2, semilla=1)
    estado = sesion.iniciar(ejercicio, con_metronomo=True)
    assert sesion.activa is True
    assert estado["metronomo"] is False
    sesion.detener()


def test_iniciar_dos_veces_reemplaza_el_ejercicio_anterior():
    sesion = practica()
    primero = sesion.generar("lectura", repeticiones=2, semilla=1)
    segundo = sesion.generar("lectura", repeticiones=5, semilla=2)
    sesion.iniciar(primero, con_metronomo=False)
    sesion.iniciar(segundo, con_metronomo=False)
    assert sesion.estado()["evaluacion"]["total"] == 5
    sesion.detener()


def test_detener_dos_veces_no_falla():
    sesion = practica()
    sesion.detener()
    sesion.detener()
