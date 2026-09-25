import numpy as np
import pytest

from nucleo.sintesis import (
    FRECUENCIA_MUESTREO_SALIDA,
    Metronomo,
    SalidaAudio,
    click,
    tono,
    tono_de_midi,
)

FS = FRECUENCIA_MUESTREO_SALIDA


def frecuencia_dominante(muestras: np.ndarray, fs: int = FS) -> float:
    """Frecuencia del pico del espectro, para comprobar que el tono suena donde debe."""
    espectro = np.abs(np.fft.rfft(muestras.astype(np.float64)))
    return float(np.fft.rfftfreq(muestras.size, 1 / fs)[np.argmax(espectro)])


def test_el_tono_dura_lo_que_se_le_pide():
    assert tono(440.0, 0.5).size == int(0.5 * FS)


def test_el_tono_suena_en_la_frecuencia_pedida():
    assert frecuencia_dominante(tono(440.0, 1.0)) == pytest.approx(440.0, abs=2.0)


def test_el_tono_no_satura():
    assert np.max(np.abs(tono(440.0, 0.5))) <= 1.0


def test_el_tono_es_float32():
    assert tono(440.0, 0.1).dtype == np.float32


def test_la_envolvente_evita_el_chasquido_de_los_extremos():
    """Una senoide que empieza de golpe salta de cero a su amplitud en una muestra."""
    muestras = tono(440.0, 0.5)
    assert abs(muestras[0]) < 0.01
    assert abs(muestras[-1]) < 0.01


def test_el_tono_tiene_armonicos_y_no_es_una_senoide_pura():
    """Para que no suene a pitido de test."""
    muestras = tono(220.0, 1.0, armonicos=(1.0, 0.5))
    espectro = np.abs(np.fft.rfft(muestras.astype(np.float64)))
    frecuencias = np.fft.rfftfreq(muestras.size, 1 / FS)
    energia_segundo = espectro[np.argmin(np.abs(frecuencias - 440.0))]
    assert energia_segundo > espectro.max() * 0.1


def test_el_tono_de_una_nota_midi_suena_donde_debe():
    """El La4 de MIDI 69 son 440 Hz."""
    assert frecuencia_dominante(tono_de_midi(69, duracion_s=1.0)) == pytest.approx(440.0, abs=2.0)


def test_el_click_es_corto():
    assert click().size < int(0.1 * FS)


def test_el_click_acentuado_suena_mas_agudo():
    normal = frecuencia_dominante(click(), FS)
    acentuado = frecuencia_dominante(click(acentuado=True), FS)
    assert acentuado > normal


class StreamSalidaFalso:
    """Doble de sounddevice.OutputStream para probar sin hardware."""

    def __init__(self, **kwargs):
        self.escrito = []
        self.cerrado = False

    def start(self):
        pass

    def write(self, muestras):
        self.escrito.append(np.asarray(muestras).copy())

    def stop(self):
        pass

    def close(self):
        self.cerrado = True


def test_la_salida_reproduce_lo_que_se_le_da():
    creados = []

    def abrir(**kwargs):
        stream = StreamSalidaFalso(**kwargs)
        creados.append(stream)
        return stream

    salida = SalidaAudio(abrir_stream=abrir)
    assert salida.abrir() is True
    assert salida.reproducir(tono(440.0, 0.1)) is True
    assert len(creados[0].escrito) == 1
    salida.cerrar()
    assert creados[0].cerrado is True


def test_un_fallo_al_abrir_la_salida_se_guarda_en_lugar_de_reventar():
    """Quedarse sin metronomo degrada el ejercicio; no lo aborta."""

    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    salida = SalidaAudio(abrir_stream=abrir_que_falla)
    assert salida.abrir() is False
    assert salida.activa is False
    assert "No output device" in salida.ultimo_error


def test_reproducir_sin_salida_abierta_devuelve_false_sin_reventar():
    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    salida = SalidaAudio(abrir_stream=abrir_que_falla)
    salida.abrir()
    assert salida.reproducir(tono(440.0, 0.1)) is False


def test_cerrar_dos_veces_no_falla():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    salida.cerrar()
    salida.cerrar()


def test_el_metronomo_emite_pulsos_al_tempo_pedido():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=600, salida=salida)  # 10 pulsos por segundo
    assert metronomo.iniciar() is True
    import time

    time.sleep(0.45)
    metronomo.detener()
    assert 3 <= metronomo.pulsos_emitidos <= 6


def test_detener_el_metronomo_deja_de_emitir():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=600, salida=salida)
    metronomo.iniciar()
    import time

    time.sleep(0.2)
    metronomo.detener()
    emitidos = metronomo.pulsos_emitidos
    time.sleep(0.2)
    assert metronomo.pulsos_emitidos == emitidos
    assert metronomo.sonando is False


def test_detener_dos_veces_no_falla():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=120, salida=salida)
    metronomo.iniciar()
    metronomo.detener()
    metronomo.detener()


def test_el_metronomo_sin_salida_no_arranca_pero_no_revienta():
    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    salida = SalidaAudio(abrir_stream=abrir_que_falla)
    salida.abrir()
    metronomo = Metronomo(tempo=120, salida=salida)
    assert metronomo.iniciar() is False
    assert metronomo.sonando is False
