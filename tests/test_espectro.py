"""Pruebas de la capa pura de espectro."""

import numpy as np
import pytest

from nucleo.analisis.espectro import (
    ANCHO_BANDA_CENTS,
    ARMONICOS_POR_DEFECTO,
    espectro_de_magnitud,
    saliencia_de_nota,
)
from nucleo.musica import midi_a_frecuencia

FS = 48000


def senoide(frecuencia: float, muestras: int, fs: int = FS) -> np.ndarray:
    t = np.arange(muestras) / fs
    return np.sin(2.0 * np.pi * frecuencia * t)


def cuerda(frecuencia: float, muestras: int, armonicos: int = 8, fs: int = FS) -> np.ndarray:
    """Cuerda pulsada tosca: armonicos con decaimiento y fase aleatoria."""
    generador = np.random.default_rng(abs(int(frecuencia)))
    t = np.arange(muestras) / fs
    onda = np.zeros_like(t)
    for h in range(1, armonicos + 1):
        onda += (
            (1.0 / h**1.2)
            * np.exp(-t / (1.5 / h))
            * np.sin(2.0 * np.pi * frecuencia * h * t + generador.uniform(0.0, 2.0 * np.pi))
        )
    return onda


class TestEspectroDeMagnitud:
    def test_una_senoide_tiene_su_maximo_en_su_frecuencia(self):
        frecuencias, magnitud = espectro_de_magnitud(senoide(440.0, 8192), FS)
        pico = frecuencias[int(np.argmax(magnitud))]
        assert abs(pico - 440.0) < 10.0

    def test_el_silencio_no_tiene_magnitud(self):
        _, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        assert float(np.max(magnitud)) == 0.0

    def test_las_frecuencias_llegan_a_nyquist(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        assert frecuencias.size == magnitud.size
        assert frecuencias[0] == 0.0
        assert abs(frecuencias[-1] - FS / 2) < 1.0

    def test_una_ventana_vacia_no_rompe(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(0), FS)
        assert frecuencias.size == 0
        assert magnitud.size == 0


class TestSalienciaDeNota:
    def test_la_nota_que_suena_sale_mas_saliente_que_el_semitono_vecino(self):
        midi = 48  # C3
        frecuencias, magnitud = espectro_de_magnitud(cuerda(midi_a_frecuencia(midi), 8192), FS)
        suya = saliencia_de_nota(frecuencias, magnitud, midi)
        vecina = saliencia_de_nota(frecuencias, magnitud, midi + 1)
        assert suya > 2.0 * vecina

    def test_el_silencio_da_saliencia_cero(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        assert saliencia_de_nota(frecuencias, magnitud, 48) == 0.0

    def test_mas_armonicos_no_puede_bajar_la_saliencia(self):
        """Es una suma de terminos no negativos: anadir sumandos no resta."""
        frecuencias, magnitud = espectro_de_magnitud(cuerda(midi_a_frecuencia(48), 8192), FS)
        pocos = saliencia_de_nota(frecuencias, magnitud, 48, armonicos=2)
        muchos = saliencia_de_nota(frecuencias, magnitud, 48, armonicos=6)
        assert muchos >= pocos

    def test_una_nota_sobre_nyquist_no_rompe_ni_inventa(self):
        """Sus armonicos caen fuera del espectro: no hay donde medir."""
        frecuencias, magnitud = espectro_de_magnitud(cuerda(midi_a_frecuencia(48), 8192), FS)
        assert saliencia_de_nota(frecuencias, magnitud, 140) == 0.0

    def test_la_banda_tolera_una_cuerda_algo_desafinada(self):
        """Un tercio de semitono de margen: 20 cents no debe perder la nota."""
        midi = 48
        desafinada = midi_a_frecuencia(midi) * 2.0 ** (20.0 / 1200.0)
        frecuencias, magnitud = espectro_de_magnitud(cuerda(desafinada, 8192), FS)
        suya = saliencia_de_nota(frecuencias, magnitud, midi)
        vecina = saliencia_de_nota(frecuencias, magnitud, midi + 1)
        assert suya > vecina

    def test_un_ancho_de_banda_absurdo_se_rechaza(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        with pytest.raises(ValueError):
            saliencia_de_nota(frecuencias, magnitud, 48, ancho_cents=0.0)

    def test_pedir_cero_armonicos_se_rechaza(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        with pytest.raises(ValueError):
            saliencia_de_nota(frecuencias, magnitud, 48, armonicos=0)

    def test_las_constantes_son_las_de_la_spec(self):
        assert ARMONICOS_POR_DEFECTO == 6
        assert ANCHO_BANDA_CENTS == 35.0
