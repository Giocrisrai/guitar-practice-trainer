import threading
import time

import numpy as np
import pytest

from nucleo.sintesis import (
    FRECUENCIA_MUESTREO_SALIDA,
    Metronomo,
    ReproductorTonos,
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


def test_cerrar_espera_a_que_termine_la_escritura_en_curso():
    """`close()` sobre un stream que otro hilo esta escribiendo es un choque real.

    Un tono de referencia dura hasta 0,6 s dentro de `write()`. Poner
    `_stream = None` antes de cerrar evita que entren escrituras NUEVAS, pero no
    saca de `write()` a la que ya esta dentro: hace falta que `cerrar()` tome el
    mismo candado que serializa las escrituras.
    """
    stream = StreamSalidaBloqueante()
    salida = SalidaAudio(abrir_stream=lambda **kw: stream)
    salida.abrir()

    escribiendo = threading.Event()
    terminada = threading.Event()

    def escribir():
        escribiendo.set()
        salida.reproducir(tono(440.0, 0.1))
        terminada.set()

    hilo = threading.Thread(target=escribir, daemon=True)
    hilo.start()
    assert escribiendo.wait(1.0)
    time.sleep(0.05)  # el hilo ya esta dentro de write(), bloqueado

    cerrado = threading.Event()

    def cerrar():
        salida.cerrar()
        cerrado.set()

    hilo_cierre = threading.Thread(target=cerrar, daemon=True)
    hilo_cierre.start()
    # Mientras la escritura sigue dentro de write(), el cierre no puede haber
    # llamado a close(): esta esperando el candado.
    time.sleep(0.05)
    assert stream.cerrado is False, "close() corrio mientras write() seguia dentro"
    assert cerrado.is_set() is False

    stream.liberar()
    assert terminada.wait(1.0)
    assert cerrado.wait(1.0)
    assert stream.cerrado is True
    hilo.join(timeout=1.0)
    hilo_cierre.join(timeout=1.0)


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


def test_pausar_el_metronomo_deja_de_emitir_sin_matar_el_hilo():
    """La spec §5 pide pausar el ejercicio al perder la senal. Se pausa con una
    bandera y no con detener() porque quien lo pide es el hilo de analisis, y
    detener() hace join(timeout=1.0): bloquear ahi cegaria la deteccion.
    """
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=300, salida=salida)
    metronomo.iniciar()
    time.sleep(0.3)
    metronomo.pausar()
    assert metronomo.pausado is True
    time.sleep(0.05)
    emitidos = metronomo.pulsos_emitidos

    time.sleep(0.4)
    assert metronomo.pulsos_emitidos == emitidos
    assert metronomo.sonando is True  # el hilo sigue vivo

    metronomo.reanudar()
    assert metronomo.pausado is False
    time.sleep(0.4)
    assert metronomo.pulsos_emitidos > emitidos
    metronomo.detener()


def test_al_reanudar_no_salen_los_clicks_de_la_pausa_pegados():
    """Si el reloj del metronomo arrastrara los pulsos de la pausa, al reanudar
    soltaria de golpe tantos clicks como hubieran cabido en ella.
    """
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    # Tempo rapido a proposito: la pausa tiene que durar VARIOS intervalos para
    # que el hilo despierte dentro de ella y ejecute de verdad la rama de pausa.
    # Con tempo 60 el hilo seguia dormido en su espera de ~1 s y la prueba
    # pasaba sin ejercitar la realineacion que dice comprobar.
    metronomo = Metronomo(tempo=240, salida=salida)  # un pulso cada 0,25 s
    metronomo.iniciar()
    time.sleep(0.05)
    metronomo.pausar()
    emitidos = metronomo.pulsos_emitidos
    time.sleep(1.0)  # caben cuatro pulsos: si los arrastrara, saldrian de golpe
    metronomo.reanudar()
    time.sleep(0.05)  # menos de un intervalo: solo cabe el pulso de la reanudacion
    nuevos = metronomo.pulsos_emitidos - emitidos
    assert nuevos <= 1, f"{nuevos} pulsos de golpe al reanudar: el reloj arrastra la pausa"
    metronomo.detener()


def test_el_reproductor_hace_sonar_la_nota_pedida():
    creados = []

    def abrir(**kwargs):
        stream = StreamSalidaFalso(**kwargs)
        creados.append(stream)
        return stream

    salida = SalidaAudio(abrir_stream=abrir)
    salida.abrir()
    reproductor = ReproductorTonos(salida=salida, duracion_s=0.2)
    assert reproductor.iniciar() is True
    assert reproductor.pedir(60) is True  # C4
    for _ in range(100):
        if reproductor.tonos_sonados >= 1:
            break
        time.sleep(0.01)
    reproductor.detener()

    assert reproductor.tonos_sonados == 1
    assert len(creados[0].escrito) == 1
    assert frecuencia_dominante(creados[0].escrito[0]) == pytest.approx(261.63, abs=3.0)


def test_pedir_un_tono_no_bloquea_a_quien_lo_pide():
    """Se pide desde el hilo de analisis, que no puede pararse los 0.6 s que
    tarda la escritura bloqueante de la salida sin perder cuadros.
    """

    class StreamLento(StreamSalidaFalso):
        def write(self, muestras):
            time.sleep(0.4)
            super().write(muestras)

    salida = SalidaAudio(abrir_stream=lambda **kw: StreamLento())
    salida.abrir()
    reproductor = ReproductorTonos(salida=salida, duracion_s=0.1)
    reproductor.iniciar()
    comienzo = time.monotonic()
    reproductor.pedir(60)
    assert time.monotonic() - comienzo < 0.1
    reproductor.detener()


def test_una_peticion_nueva_sustituye_a_la_que_no_ha_sonado():
    """Buzon de una sola plaza: encolar haria sonar la referencia de una nota que
    el alumno ya dejo atras.
    """
    creados = []

    class StreamLento(StreamSalidaFalso):
        def write(self, muestras):
            time.sleep(0.15)
            super().write(muestras)

    def abrir(**kwargs):
        stream = StreamLento(**kwargs)
        creados.append(stream)
        return stream

    salida = SalidaAudio(abrir_stream=abrir)
    salida.abrir()
    reproductor = ReproductorTonos(salida=salida, duracion_s=0.2)
    reproductor.iniciar()
    reproductor.pedir(60)
    time.sleep(0.05)  # el hilo esta dentro de write()
    reproductor.pedir(62)
    reproductor.pedir(64)  # sustituye a la de 62, que no llego a sonar
    for _ in range(100):
        if reproductor.tonos_sonados >= 2:
            break
        time.sleep(0.01)
    reproductor.detener()

    assert reproductor.tonos_sonados == 2
    assert frecuencia_dominante(creados[0].escrito[1]) == pytest.approx(329.63, abs=6.0)


def test_el_reproductor_sin_salida_no_arranca_pero_no_revienta():
    reproductor = ReproductorTonos(salida=SalidaAudio(abrir_stream=lambda **kw: 1 / 0))
    assert reproductor.iniciar() is False
    assert reproductor.pedir(60) is False
    reproductor.detener()


def test_el_reproductor_huerfano_no_escribe_tras_un_join_vencido():
    """Mismo patron que el metronomo: la generacion se comprueba antes y despues
    de la escritura bloqueante, que puede durar mas que el join(timeout=1.0).
    """
    dentro = threading.Event()
    seguir = threading.Event()
    escrituras = []

    class StreamAtascado(StreamSalidaFalso):
        def write(self, muestras):
            escrituras.append(1)
            dentro.set()
            seguir.wait(5.0)

    salida = SalidaAudio(abrir_stream=lambda **kw: StreamAtascado())
    salida.abrir()
    reproductor = ReproductorTonos(salida=salida, duracion_s=0.05)
    reproductor.iniciar()
    reproductor.pedir(60)
    assert dentro.wait(2.0) is True

    comienzo = time.monotonic()
    reproductor.detener()  # el join vence con el hilo dentro de write()
    assert time.monotonic() - comienzo >= 1.0
    seguir.set()
    time.sleep(0.2)

    # Ni conto ese tono ni dio otra vuelta escribiendo sobre la salida cerrada.
    assert reproductor.tonos_sonados == 0
    assert len(escrituras) == 1


def test_dos_emisores_no_escriben_a_la_vez_en_la_misma_salida():
    """Un ejercicio de intervalos tiene dos emisores sobre la misma salida en
    hilos distintos: el metronomo y el tono de referencia. OutputStream.write()
    no promete ser seguro entre hilos, asi que reproducir() las serializa.
    """
    solapes = []
    dentro = threading.Lock()
    escribiendo = [False]

    class StreamQueVigila(StreamSalidaFalso):
        def write(self, muestras):
            with dentro:
                if escribiendo[0]:
                    solapes.append(1)
                escribiendo[0] = True
            time.sleep(0.01)
            with dentro:
                escribiendo[0] = False

    salida = SalidaAudio(abrir_stream=lambda **kw: StreamQueVigila())
    salida.abrir()
    onda = tono(440.0, 0.05)

    def emitir():
        for _ in range(20):
            salida.reproducir(onda)

    hilos = [threading.Thread(target=emitir) for _ in range(4)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=10.0)
    salida.cerrar()

    assert solapes == []
