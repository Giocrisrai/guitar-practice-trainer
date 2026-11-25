"""Pruebas de la calibración de `UMBRAL_PRESENCIA`.

Se prueba lo que no necesita cable: la medición sobre una grabación ya hecha y la
aritmética de la recomendación. Lo interactivo —buscar el cable, pedir Enter,
grabar— no se prueba aquí, igual que en el resto de `herramientas/`: lo único que
podría comprobarse es que se llamó a un doble.

El acorde sintético se sintetiza igual que en `tests/test_acordes.py`, y la copia
es a propósito: si esa síntesis cambia allí para probar otra cosa, esta prueba
debe seguir midiendo lo que mide hoy.
"""

import numpy as np
import pytest

from herramientas.calibrar_presencia import (
    PERCENTIL_MUDA,
    PERCENTIL_SONANDO,
    presencias_de,
    recomendar,
    resumir,
)
from nucleo.analisis.acordes import VENTANA_ACORDES
from nucleo.musica import midi_a_frecuencia

FS = 48000
DO_MAYOR = (48, 52, 55, 60, 64)


def cuerda(frecuencia: float, muestras: int, semilla: int) -> np.ndarray:
    generador = np.random.default_rng(semilla)
    t = np.arange(muestras) / FS
    onda = np.zeros_like(t)
    for h in range(1, 9):
        onda += (
            (1.0 / h**1.2)
            * np.exp(-t / (1.5 / h))
            * np.sin(2.0 * np.pi * frecuencia * h * t + generador.uniform(0.0, 2.0 * np.pi))
        )
    return onda


def rasgueo(midis, muestras: int) -> np.ndarray:
    mezcla = np.zeros(muestras)
    for indice, midi in enumerate(midis):
        mezcla += cuerda(midi_a_frecuencia(midi), muestras, semilla=indice)
    pico = float(np.max(np.abs(mezcla)))
    return mezcla / pico if pico > 0.0 else mezcla


# Tres ventanas: la primera se va en llenar el búfer y las otras dan cuadros
# juzgados. Menos que esto no deja ninguno.
MUESTRAS = VENTANA_ACORDES * 3


class TestLaMedicion:
    def test_cada_cuerda_que_suena_trae_sus_cuadros(self):
        recogidas = presencias_de(rasgueo(DO_MAYOR, MUESTRAS), DO_MAYOR)
        assert set(recogidas) == set(DO_MAYOR)
        # Todas con la misma cantidad de cuadros: el detector publica las cinco
        # presencias o ninguna, nunca unas sí y otras no.
        cantidades = {len(valores) for valores in recogidas.values()}
        assert len(cantidades) == 1
        assert cantidades.pop() > 0

    def test_la_cuerda_muda_mide_menos_que_las_que_suenan(self):
        """El hueco que la herramienta existe para medir, sobre señal sintética."""
        suena = DO_MAYOR[:-1]
        muda = DO_MAYOR[-1]
        recogidas = presencias_de(rasgueo(suena, MUESTRAS), DO_MAYOR)
        peor_sonando = min(min(recogidas[midi]) for midi in suena)
        mejor_muda = max(recogidas[muda])
        assert mejor_muda < peor_sonando

    def test_el_silencio_no_trae_ningun_cuadro(self):
        """Bajo la compuerta de ruido el detector se calla, y aquí eso es una lista
        vacía: medir sobre el silencio daría un umbral sacado de la nada."""
        recogidas = presencias_de(np.zeros(MUESTRAS), DO_MAYOR)
        assert all(valores == [] for valores in recogidas.values())

    def test_sin_notas_esperadas_no_hay_nada_que_medir(self):
        assert presencias_de(rasgueo(DO_MAYOR, MUESTRAS), ()) == {}

    def test_el_umbral_de_ruido_decide_cuantos_cuadros_entran(self):
        """Subirlo por encima de la señal deja la medición sin cuadros, que es lo
        que la herramienta detecta para decirle al usuario que suba el volumen."""
        muestras = rasgueo(DO_MAYOR, MUESTRAS)
        recogidas = presencias_de(muestras, DO_MAYOR, umbral_ruido_dbfs=0.0)
        assert all(valores == [] for valores in recogidas.values())


class TestElResumen:
    def test_un_percentil_bajo_trae_el_minimo_como_extremo(self):
        percentil, extremo = resumir([0.2, 0.5, 0.9], PERCENTIL_SONANDO)
        assert extremo == pytest.approx(0.2)
        assert percentil == pytest.approx(np.percentile([0.2, 0.5, 0.9], PERCENTIL_SONANDO))

    def test_un_percentil_alto_trae_el_maximo(self):
        _, extremo = resumir([0.2, 0.5, 0.9], PERCENTIL_MUDA)
        assert extremo == pytest.approx(0.9)

    def test_una_lista_vacia_no_finge_un_numero(self):
        """`nan` y no 0,0: cero diría "medí y salió cero", y aquí no se midió."""
        percentil, extremo = resumir([], PERCENTIL_SONANDO)
        assert np.isnan(percentil)
        assert np.isnan(extremo)


class TestLaRecomendacion:
    def test_cae_en_medio_del_hueco(self):
        umbral, margen = recomendar([0.8] * 10, [0.2] * 10)
        assert umbral == pytest.approx(0.5)
        assert margen == pytest.approx(0.6)

    def test_el_margen_sale_negativo_cuando_no_hay_hueco(self):
        """Lo que la herramienta trata como "esto no se arregla con un número":
        las mudas miden más que las que suenan."""
        _, margen = recomendar([0.3] * 10, [0.7] * 10)
        assert margen < 0.0

    def test_un_cuadro_malo_no_arrastra_la_recomendacion(self):
        """La razón de usar percentiles. Un único cuadro de presencia casi nula
        —el instante del ataque— bajaría el umbral hasta donde no sirve si se
        usara el mínimo absoluto."""
        sonando = [0.01] + [0.8] * 99
        umbral, margen = recomendar(sonando, [0.2] * 10)
        assert umbral > 0.4
        assert margen > 0.0
