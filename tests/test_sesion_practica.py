import time

import numpy as np
import pytest

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.gemelo.salida import SalidaCapturada
from nucleo.musica import midi_a_frecuencia
from servidor.configuracion import Configuracion
from servidor.ejercicios import GENERADORES, SesionPractica
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000


def frecuencia_dominante(muestras: np.ndarray, fs: int = FS) -> float:
    """Frecuencia del pico del espectro, para comprobar que el tono suena donde debe."""
    espectro = np.abs(np.fft.rfft(np.asarray(muestras, dtype=np.float64)))
    return float(np.fft.rfftfreq(np.size(muestras), 1 / fs)[np.argmax(espectro)])


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


def practica(perfil: str = "guitarra_estandar") -> SesionPractica:
    sesion = Sesion(
        Configuracion(dispositivo=3, perfil=perfil),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    return SesionPractica(sesion, salida=SalidaCapturada().salida)


def test_las_cinco_familias_estan_registradas():
    # "cambios" la anade la etapa 2b, y es la unica que produce acordes.
    assert set(GENERADORES) == {"escala", "arpegio", "intervalo", "lectura", "cambios"}


def test_generar_devuelve_un_ejercicio_de_la_familia_pedida():
    sesion = practica()
    ejercicio = sesion.generar("escala", raiz_midi=48, tipo="mayor")
    assert len(ejercicio) > 0
    assert "escala" in ejercicio.clave
    sesion.detener()


def test_el_ejercicio_hereda_el_perfil_activo_del_afinador():
    """Con el bajo enchufado, las notas pedidas tienen que estar en su mastil.

    El bajo de 4 cuerdas llega hasta E1 (MIDI 28) y no pasa de G3 (MIDI 55) en
    el traste 24; la guitarra estandar empieza en E2 (MIDI 40). Si el generador
    ignorase el perfil, pediria notas que el instrumento no tiene.
    """
    sesion = practica(perfil="bajo_4")
    ejercicio = sesion.generar("lectura")
    assert ejercicio.perfil == "bajo_4"
    assert all(28 <= nota.midi <= 55 for nota in ejercicio.notas)
    sesion.detener()


def test_quien_pide_un_perfil_concreto_manda_sobre_el_activo():
    sesion = practica(perfil="bajo_4")
    ejercicio = sesion.generar("lectura", perfil_clave="guitarra_estandar")
    assert ejercicio.perfil == "guitarra_estandar"
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

    sesion = SesionPractica(sesion_audio, salida=SalidaCapturada(fallar_al_abrir=True).salida)
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


def test_el_ejercicio_de_intervalos_hace_sonar_la_nota_de_referencia():
    """Spec §4.5 y §4.1: el software suena la referencia antes de pedir la nota
    objetivo. Sin eso el ejercicio de intervalos es uno de lectura con la
    respuesta escrita en pantalla, y el entrenamiento de oido no existe.
    """
    captura = SalidaCapturada()

    sesion_audio = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion_audio.iniciar()
    sesion = SesionPractica(
        sesion_audio, salida=captura.salida
    )
    ejercicio = sesion.generar("intervalo", repeticiones=3, semilla=1)
    assert ejercicio.notas[0].referencia_midi is not None

    sesion.iniciar(ejercicio, con_metronomo=False)
    for _ in range(100):
        if captura.bloques:
            break
        time.sleep(0.01)
    sesion.detener()

    assert len(captura.bloques) == 1
    esperada = midi_a_frecuencia(ejercicio.notas[0].referencia_midi)
    assert frecuencia_dominante(captura.muestras) == pytest.approx(esperada, rel=0.03)


def test_la_referencia_suena_una_sola_vez_por_nota():
    """Se pide al entrar en la nota, no en cada cuadro de analisis."""
    captura = SalidaCapturada()

    sesion_audio = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion_audio.iniciar()
    sesion = SesionPractica(
        sesion_audio, salida=captura.salida
    )
    ejercicio = sesion.generar("intervalo", repeticiones=3, semilla=2)
    sesion.iniciar(ejercicio, con_metronomo=False)
    time.sleep(0.5)  # unos 24 cuadros de analisis
    sesion.detener()

    assert len(captura.bloques) == 1


def test_el_ejercicio_de_lectura_no_hace_sonar_nada():
    """En lectura `referencia_midi` es None: no se abre la salida ni suena nada."""
    captura = SalidaCapturada()

    sesion_audio = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion_audio.iniciar()
    sesion = SesionPractica(
        sesion_audio, salida=captura.salida
    )
    ejercicio = sesion.generar("lectura", repeticiones=3, semilla=1)
    sesion.iniciar(ejercicio, con_metronomo=False)
    time.sleep(0.3)
    sesion.detener()

    assert captura.bloques == ()


def test_sin_salida_de_audio_el_ejercicio_de_intervalos_sigue_sin_tono():
    """Degrada suave, igual que el metronomo: la spec dice que quedarse sin
    altavoces no impide practicar.
    """
    sesion_audio = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion_audio.iniciar()
    sesion = SesionPractica(sesion_audio, salida=SalidaCapturada(fallar_al_abrir=True).salida)
    ejercicio = sesion.generar("intervalo", repeticiones=2, semilla=1)
    sesion.iniciar(ejercicio, con_metronomo=False)
    assert sesion.activa is True
    time.sleep(0.2)
    assert sesion.estado()["evaluacion"]["total"] == 2
    sesion.detener()


def test_al_perder_la_senal_el_metronomo_se_pausa_y_al_volver_se_reanuda():
    """Spec §5: al perder la senal el ejercicio se pausa. La otra mitad de la
    pausa (el temporizador de la ayuda) vive en el evaluador.
    """
    sesion_audio = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion_audio.segundos_sin_senal = 0.05
    sesion_audio.iniciar()
    sesion = SesionPractica(sesion_audio, salida=SalidaCapturada().salida)
    ejercicio = sesion.generar("escala", traste_maximo=4)
    estado = sesion.iniciar(ejercicio)
    assert estado["metronomo"] is True

    # La captura falsa entrega una senoide a -10 dBFS: hay senal, nada se pausa.
    time.sleep(0.2)
    assert sesion.estado()["metronomo_pausado"] is False

    # Se desenchufa el cable: el hilo de analisis publica silencio.
    sesion_audio._listar = lambda: []
    for _ in range(200):
        if sesion.estado()["metronomo_pausado"]:
            break
        time.sleep(0.02)
    assert sesion.estado()["metronomo_pausado"] is True

    # Y al volver a aparecer, se reanuda solo.
    sesion_audio._listar = lambda: [CABLE]
    for _ in range(300):
        if not sesion.estado()["metronomo_pausado"]:
            break
        time.sleep(0.02)
    assert sesion.estado()["metronomo_pausado"] is False
    sesion.detener()
