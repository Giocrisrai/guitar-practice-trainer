import numpy as np
import pytest

from nucleo.captura import (
    NOMBRE_ROCKSMITH,
    BufferCircular,
    CapturaAudio,
    DispositivoAudio,
    buscar_rocksmith,
)


def test_el_buffer_devuelve_none_hasta_tener_suficiente():
    buffer = BufferCircular(capacidad=100)
    buffer.escribir(np.arange(10, dtype=np.float32))
    assert buffer.leer_ultimas(20) is None


def test_el_buffer_devuelve_las_ultimas_muestras_en_orden():
    buffer = BufferCircular(capacidad=100)
    buffer.escribir(np.arange(50, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(5), np.arange(45, 50))


def test_el_buffer_sobrescribe_lo_mas_antiguo_al_dar_la_vuelta():
    """Perder muestras viejas es el comportamiento correcto: solo importa el presente."""
    buffer = BufferCircular(capacidad=10)
    buffer.escribir(np.arange(15, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(10), np.arange(5, 15))


def test_el_buffer_maneja_una_escritura_mayor_que_su_capacidad():
    buffer = BufferCircular(capacidad=8)
    buffer.escribir(np.arange(20, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(8), np.arange(12, 20))


def test_el_buffer_es_continuo_tras_varias_vueltas():
    buffer = BufferCircular(capacidad=16)
    for inicio in range(0, 100, 5):
        buffer.escribir(np.arange(inicio, inicio + 5, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(4), np.arange(96, 100))


def test_no_se_puede_pedir_mas_que_la_capacidad():
    buffer = BufferCircular(capacidad=10)
    buffer.escribir(np.arange(10, dtype=np.float32))
    assert buffer.leer_ultimas(11) is None


def test_reconoce_el_rocksmith_entre_otros_dispositivos():
    dispositivos = [
        DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0),
        DispositivoAudio(1, "ZoomAudioDevice", 2, 48000.0),
        DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0),
    ]
    encontrado = buscar_rocksmith(dispositivos)
    assert encontrado is not None
    assert encontrado.indice == 3


def test_sin_rocksmith_devuelve_none():
    dispositivos = [DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)]
    assert buscar_rocksmith(dispositivos) is None


class StreamFalso:
    """Doble de sounddevice.InputStream para probar el hilo sin hardware."""

    def __init__(self, callback, **kwargs):
        self.callback = callback
        self.latency = 0.012
        self.cerrado = False

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        self.cerrado = True

    def entregar(self, bloque: np.ndarray):
        """Simula que CoreAudio entrega un bloque."""
        self.callback(bloque.reshape(-1, 1), len(bloque), None, None)


def test_la_captura_acumula_los_bloques_entregados():
    creados = []

    def abrir(callback, **kwargs):
        stream = StreamFalso(callback, **kwargs)
        creados.append(stream)
        return stream

    captura = CapturaAudio(indice_dispositivo=3, capacidad_buffer=4096, abrir_stream=abrir)
    captura.iniciar()
    for _ in range(4):
        creados[0].entregar(np.full(512, 0.25, dtype=np.float32))

    ventana = captura.leer_ventana(2048)
    assert ventana is not None
    assert ventana.shape == (2048,)
    assert ventana.dtype == np.float32
    assert np.allclose(ventana, 0.25)
    captura.detener()
    assert creados[0].cerrado is True


def test_la_ganancia_multiplica_la_senal():
    """El cable entrega nivel bajo: la ganancia digital es parte del diseño."""
    creados = []

    def abrir(callback, **kwargs):
        stream = StreamFalso(callback, **kwargs)
        creados.append(stream)
        return stream

    captura = CapturaAudio(
        indice_dispositivo=3, capacidad_buffer=4096, ganancia=4.0, abrir_stream=abrir
    )
    captura.iniciar()
    creados[0].entregar(np.full(1024, 0.1, dtype=np.float32))
    assert np.allclose(captura.leer_ventana(1024), 0.4)
    captura.detener()


def test_la_latencia_se_reporta_en_milisegundos():
    captura = CapturaAudio(
        indice_dispositivo=3, abrir_stream=lambda callback, **kw: StreamFalso(callback)
    )
    captura.iniciar()
    assert captura.latencia_ms == pytest.approx(12.0, abs=0.1)
    captura.detener()


def test_un_fallo_al_abrir_se_guarda_en_lugar_de_reventar():
    def abrir_que_falla(callback, **kwargs):
        raise OSError("Device unavailable")

    captura = CapturaAudio(indice_dispositivo=99, abrir_stream=abrir_que_falla)
    captura.iniciar()
    assert captura.activa is False
    assert "Device unavailable" in captura.ultimo_error
