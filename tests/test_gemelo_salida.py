"""El capturador de salida: que lo que suena se pueda probar sin altavoces.

Lo escrito se compara SIEMPRE contra arrays construidos aqui en la prueba, nunca
contra lo que el capturador diga de si mismo.
"""

import numpy as np
import pytest

from nucleo.gemelo.salida import SalidaCapturada, StreamCapturado
from nucleo.sintesis import SalidaAudio


def _bloque(n: int, inicio: float) -> np.ndarray:
    """Un bloque distinguible: valores consecutivos desde `inicio`."""
    return (inicio + np.arange(n)).astype(np.float32)


def test_lo_escrito_se_guarda_en_orden_y_entero():
    a, b, c = _bloque(5, 1.0), _bloque(3, 100.0), _bloque(8, 1000.0)
    captura = SalidaCapturada()
    assert captura.abrir()
    for bloque in (a, b, c):
        assert captura.salida.reproducir(bloque) is True

    esperado = np.concatenate([a, b, c])
    np.testing.assert_array_equal(captura.muestras, esperado)
    assert captura.muestras.dtype == np.float32
    assert captura.bloques == (5, 3, 8)


def test_sin_escrituras_no_hay_muestras_ni_bloques():
    captura = SalidaCapturada()
    assert captura.muestras.shape == (0,)
    # El vacio es float32 como todo lo demas: si no, al concatenarlo con bloques
    # float32 promocionaria el resultado entero a float64.
    assert captura.muestras.dtype == np.float32
    assert captura.bloques == ()


def test_lo_guardado_es_una_copia_del_buffer_reutilizado():
    """sounddevice reutiliza el buffer: quien lo guarda tiene que copiar."""
    captura = SalidaCapturada()
    captura.abrir()
    buffer = _bloque(4, 1.0)
    captura.salida.reproducir(buffer)
    buffer[:] = -7.0
    np.testing.assert_array_equal(captura.muestras, _bloque(4, 1.0))


def test_un_bloque_de_dos_dimensiones_cuenta_sus_cuadros():
    captura = SalidaCapturada()
    captura.abrir()
    captura.salida.reproducir(_bloque(6, 1.0).reshape(6, 1))
    captura.salida.reproducir(_bloque(2, 50.0))
    assert captura.bloques == (6, 2)
    np.testing.assert_array_equal(
        captura.muestras, np.concatenate([_bloque(6, 1.0), _bloque(2, 50.0)])
    )


def test_la_salida_capturada_se_comporta_como_la_de_verdad():
    captura = SalidaCapturada()
    antes = _bloque(4, 1.0)
    despues = _bloque(4, 500.0)

    assert captura.abrir() is True
    assert captura.abrir() is True  # idempotente: la clausura no se agota
    assert captura.salida.activa
    assert captura.salida.reproducir(antes) is True

    captura.salida.cerrar()
    captura.salida.cerrar()  # dos veces no lanza
    assert not captura.salida.activa

    # Tras cerrar: False y SIN tocar lo guardado.
    assert captura.salida.reproducir(despues) is False
    np.testing.assert_array_equal(captura.muestras, antes)
    assert captura.bloques == (4,)


def test_se_puede_reabrir_tras_cerrar_y_la_clausura_no_se_agota():
    """Es el defecto que la etapa anterior pago: nada se vacia ni se agota."""
    captura = SalidaCapturada()
    uno, dos = _bloque(3, 1.0), _bloque(3, 10.0)
    for _ in range(3):
        assert captura.abrir() is True
        captura.salida.cerrar()
    assert captura.abrir() is True
    captura.salida.reproducir(uno)
    captura.salida.cerrar()
    assert captura.abrir() is True
    captura.salida.reproducir(dos)
    # Un solo stream capturado a lo largo de todas las aperturas.
    np.testing.assert_array_equal(captura.muestras, np.concatenate([uno, dos]))
    assert captura.bloques == (3, 3)


def test_el_stream_se_arranca_y_se_cierra_de_verdad():
    captura = SalidaCapturada()
    assert (captura.arranques, captura.cierres) == (0, 0)
    captura.abrir()
    captura.abrir()
    assert captura.arranques == 1
    captura.salida.cerrar()
    captura.salida.cerrar()
    assert captura.cierres == 1


def test_el_stream_recibe_lo_que_la_salida_pide():
    captura = SalidaCapturada(frecuencia_muestreo=22050)
    captura.abrir()
    assert captura.argumentos == {
        "samplerate": 22050,
        "channels": 1,
        "dtype": "float32",
    }
    assert captura.salida.frecuencia_muestreo == 22050


def test_es_una_salida_audio_de_verdad():
    assert isinstance(SalidaCapturada().salida, SalidaAudio)


def test_un_stream_que_falla_al_escribir_no_mata_a_quien_escribe():
    captura = SalidaCapturada(fallar_en=2)
    captura.abrir()
    a, b, c = _bloque(2, 1.0), _bloque(2, 10.0), _bloque(2, 100.0)
    assert captura.salida.reproducir(a) is True
    assert captura.salida.reproducir(b) is True
    assert captura.salida.ultimo_error is None
    assert captura.salida.reproducir(c) is False  # la tercera falla, sin lanzar
    assert captura.salida.ultimo_error
    # La escritura fallida no queda como si hubiera sonado.
    np.testing.assert_array_equal(captura.muestras, np.concatenate([a, b]))
    assert captura.bloques == (2, 2)


def test_tras_el_fallo_las_escrituras_siguientes_vuelven_a_sonar():
    """`fallar_en` falla UNA escritura: el resto del stream sigue sano."""
    captura = SalidaCapturada(fallar_en=1)
    captura.abrir()
    a, b, c, d = (_bloque(2, k) for k in (1.0, 10.0, 100.0, 1000.0))
    assert captura.salida.reproducir(a) is True
    assert captura.salida.reproducir(b) is False
    assert captura.salida.reproducir(c) is True
    assert captura.salida.reproducir(d) is True
    np.testing.assert_array_equal(captura.muestras, np.concatenate([a, c, d]))
    assert captura.bloques == (2, 2, 2)


def test_el_error_de_escritura_viaja_con_su_mensaje():
    captura = SalidaCapturada(fallar_en=0)
    captura.abrir()
    captura.salida.reproducir(_bloque(1, 1.0))
    assert "escritura" in captura.salida.ultimo_error


def test_sin_dispositivo_abrir_devuelve_false_y_deja_el_error():
    captura = SalidaCapturada(fallar_al_abrir=True)
    assert captura.abrir() is False
    assert not captura.salida.activa
    assert captura.salida.ultimo_error
    assert captura.salida.reproducir(_bloque(2, 1.0)) is False
    assert captura.bloques == ()


def test_sin_dispositivo_sigue_sin_dispositivo_al_reintentar():
    """El caso real: se arranca sin cable, el programa reintenta y sigue sin cable."""
    captura = SalidaCapturada(fallar_al_abrir=True)
    for _ in range(3):
        assert captura.abrir() is False
        assert not captura.salida.activa
        assert captura.salida.ultimo_error
    assert captura.arranques == 0
    assert captura.bloques == ()


def test_el_stream_capturado_se_puede_usar_solo():
    stream = StreamCapturado()
    stream.start()
    stream.write(_bloque(3, 1.0))
    stream.stop()
    stream.close()
    np.testing.assert_array_equal(stream.muestras, _bloque(3, 1.0))
    assert stream.bloques == (3,)


def test_el_stream_con_fallo_lanza_en_la_escritura_indicada():
    stream = StreamCapturado(fallar_en=1)
    stream.write(_bloque(1, 1.0))
    with pytest.raises(OSError):
        stream.write(_bloque(1, 2.0))
