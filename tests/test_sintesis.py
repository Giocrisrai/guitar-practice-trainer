import threading
import time

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
    # tempo=300 es el maximo permitido (ver TEMPO_MAXIMO_PPM): 5 pulsos por
    # segundo. Con 0.9 s de espera caen pulsos en t=0, 0.2, 0.4, 0.6 y 0.8, es
    # decir 5, el mismo numero esperado que con el tempo=600/sleep=0.45 original
    # (proporcion 2x/2x), por lo que el rango de la asercion no cambia.
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=300, salida=salida)  # 5 pulsos por segundo
    assert metronomo.iniciar() is True
    import time

    time.sleep(0.9)
    metronomo.detener()
    assert 3 <= metronomo.pulsos_emitidos <= 6


def test_detener_el_metronomo_deja_de_emitir():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=300, salida=salida)
    metronomo.iniciar()
    import time

    time.sleep(0.4)
    metronomo.detener()
    emitidos = metronomo.pulsos_emitidos
    time.sleep(0.4)
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


def test_el_metronomo_rechaza_tempos_por_encima_del_limite():
    """Por encima de ~2000 ppm el intervalo (60/tempo) es menor que los 30 ms que
    dura el propio click: la escritura bloqueante se comeria el intervalo y los
    clicks saldrian pegados. Se limita a un tope razonable (300 ppm, mas de lo
    que cualquier ejercicio de guitarra necesita)."""
    with pytest.raises(ValueError):
        Metronomo(tempo=301, salida=SalidaAudio())


class StreamSalidaBloqueante:
    """Doble de OutputStream cuya write() se queda bloqueada hasta liberarla.

    Simula un dispositivo lento (o simplemente el tiempo que tarda CoreAudio en
    aceptar un bloque) para poder reproducir a voluntad el escenario del hilo
    huerfano: reproducir() bloqueada mas alla del timeout del join() de
    Metronomo.detener().
    """

    def __init__(self, **kwargs):
        self.escrito = []
        self.cerrado = False
        self._liberar = threading.Event()

    def start(self):
        pass

    def write(self, muestras):
        self._liberar.wait()
        self.escrito.append(np.asarray(muestras).copy())

    def stop(self):
        pass

    def close(self):
        self.cerrado = True

    def liberar(self):
        """Desbloquea cualquier write() en curso o futura."""
        self._liberar.set()


def test_el_hilo_huerfano_no_emite_tras_un_join_vencido():
    """Si write() sigue bloqueada mas alla del timeout del join, detener()
    devuelve el control con el hilo todavia vivo. Cuando por fin se libera, ese
    hilo huerfano no debe contar otro pulso ni intentar otro click: el contador
    de generacion (ver Metronomo.detener() y Metronomo._trabajar()) tiene que
    detenerlo."""
    stream = StreamSalidaBloqueante()
    salida = SalidaAudio(abrir_stream=lambda **kw: stream)
    salida.abrir()
    metronomo = Metronomo(tempo=300, salida=salida)
    assert metronomo.iniciar() is True

    # Deja que el hilo entre en su primer reproducir(), que se queda bloqueado
    # dentro de write() porque el evento de liberacion todavia no se disparo.
    time.sleep(0.05)

    # write() sigue bloqueada: el join(timeout=1.0) de detener() vence sin que
    # el hilo real haya terminado.
    metronomo.detener()
    emitidos_justo_tras_detener = metronomo.pulsos_emitidos

    # Ahora se libera la escritura bloqueada: el hilo huerfano puede continuar.
    stream.liberar()
    time.sleep(0.3)

    assert metronomo.pulsos_emitidos == emitidos_justo_tras_detener


def test_cerrar_y_reproducir_concurrentes_no_revientan():
    """cerrar() pone self._stream en None ANTES de detener/cerrar la copia
    local, para que un reproducir() concurrente nunca toque un stream a medio
    cerrar. Un reproducir() posterior al cierre debe devolver False."""
    stream = StreamSalidaFalso()
    salida = SalidaAudio(abrir_stream=lambda **kw: stream)
    salida.abrir()
    errores = []

    def escribir_sin_parar():
        try:
            for _ in range(500):
                salida.reproducir(tono(440.0, 0.005))
        except Exception as error:  # no deberia lanzar nunca
            errores.append(error)

    hilo = threading.Thread(target=escribir_sin_parar)
    hilo.start()
    time.sleep(0.002)
    salida.cerrar()
    hilo.join(timeout=2.0)

    assert not hilo.is_alive()
    assert errores == []
    assert salida.reproducir(tono(440.0, 0.005)) is False
