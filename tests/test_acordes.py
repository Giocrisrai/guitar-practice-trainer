"""Pruebas del detector de acordes por verificacion."""

import numpy as np
import pytest

from nucleo.afinaciones import PERFILES_DE_FABRICA
from nucleo.analisis.acordes import (
    UMBRAL_PRESENCIA,
    VENTANA_ACORDES,
    DetectorAcordes,
    ResultadoAcorde,
)
from nucleo.musica import midi_a_frecuencia

FS = 48000
GUITARRA = PERFILES_DE_FABRICA["guitarra_estandar"]

# Do mayor abierto (x32010) y Sol mayor abierto (320003), en MIDI.
DO_MAYOR = (48, 52, 55, 60, 64)
SOL_MAYOR = (43, 47, 50, 55, 59, 67)


def cuerda(frecuencia: float, muestras: int, semilla: int, fs: int = FS) -> np.ndarray:
    generador = np.random.default_rng(semilla)
    t = np.arange(muestras) / fs
    onda = np.zeros_like(t)
    for h in range(1, 9):
        onda += (
            (1.0 / h**1.2)
            * np.exp(-t / (1.5 / h))
            * np.sin(2.0 * np.pi * frecuencia * h * t + generador.uniform(0.0, 2.0 * np.pi))
        )
    return onda


def rasgueo(midis, muestras: int = VENTANA_ACORDES) -> np.ndarray:
    """Las notas de un acorde sonando a la vez, normalizadas a amplitud 1."""
    mezcla = np.zeros(muestras)
    for indice, midi in enumerate(midis):
        mezcla += cuerda(midi_a_frecuencia(midi), muestras, semilla=indice)
    pico = float(np.max(np.abs(mezcla)))
    return mezcla / pico if pico > 0.0 else mezcla


def detectar(midis_sonando, midis_esperados) -> ResultadoAcorde:
    detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
    return detector.procesar(rasgueo(midis_sonando), midis_esperados)


class TestVeredicto:
    def test_el_acorde_completo_sale_completo(self):
        resultado = detectar(DO_MAYOR, DO_MAYOR)
        assert resultado.estado == "completo"
        assert resultado.faltan == ()

    def test_sol_completo_tambien(self):
        resultado = detectar(SOL_MAYOR, SOL_MAYOR)
        assert resultado.estado == "completo"
        assert resultado.faltan == ()

    def test_una_cuerda_muda_sale_nombrada(self):
        """Do sin la primera: falta E4 (midi 64) y solo esa."""
        resultado = detectar(DO_MAYOR[:-1], DO_MAYOR)
        assert resultado.estado == "incompleto"
        assert resultado.faltan == (64,)

    def test_la_cuerda_muda_del_medio_tambien(self):
        """Do sin la segunda: falta C4 (midi 60)."""
        suena = tuple(m for m in DO_MAYOR if m != 60)
        resultado = detectar(suena, DO_MAYOR)
        assert resultado.estado == "incompleto"
        assert resultado.faltan == (60,)

    def test_el_acorde_equivocado_falla_por_varias_notas(self):
        """Suena Sol, se pide Do: no es una cuerda muda, es otro acorde."""
        resultado = detectar(SOL_MAYOR, DO_MAYOR)
        assert resultado.estado == "incompleto"
        assert len(resultado.faltan) >= 3

    def test_el_acorde_equivocado_no_necesita_todas_las_ausencias_para_verse(self):
        """Limitacion medida y asumida, documentada en UMBRAL_PRESENCIA.

        Con el Sol sonando y el Do pedido, el C3 que nadie toca llega a 0,46 -sus
        armonicos tercero y sexto caen sobre el Sol- y se cuela como presente. El
        veredicto no depende de el: las otras tres ausencias ya lo dicen. Esta
        prueba fija eso para que si algun dia deja de ser cierto se sepa.
        """
        resultado = detectar(SOL_MAYOR, DO_MAYOR)
        assert resultado.estado == "incompleto"
        assert 48 not in resultado.faltan
        assert resultado.presencias[48] > UMBRAL_PRESENCIA

    def test_las_ausencias_van_de_grave_a_aguda(self):
        resultado = detectar(SOL_MAYOR, DO_MAYOR)
        assert list(resultado.faltan) == sorted(resultado.faltan)

    def test_la_presencia_de_una_nota_muda_es_menor_que_la_de_una_que_suena(self):
        resultado = detectar(DO_MAYOR[:-1], DO_MAYOR)
        assert resultado.presencias[64] < resultado.presencias[48]


class TestPuertas:
    def test_el_silencio_es_silencio_y_no_dice_que_falte_nada(self):
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        resultado = detector.procesar(np.zeros(VENTANA_ACORDES), DO_MAYOR)
        assert resultado.estado == "silencio"
        assert resultado.presencias == {}
        assert resultado.faltan == ()

    def test_sin_notas_esperadas_no_hay_acorde_completo(self):
        """Una tupla vacia no se cumple por vacuidad: no hay acorde que juzgar."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        resultado = detector.procesar(rasgueo(DO_MAYOR), ())
        assert resultado.estado == "silencio"
        assert resultado.faltan == ()

    def test_una_ventana_a_medio_llenar_no_se_juzga(self):
        """Los primeros bloques dejan el bufer mayoritariamente en ceros."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        trozo = rasgueo(DO_MAYOR)[:1008]
        resultado = detector.procesar(trozo, DO_MAYOR)
        assert resultado.estado == "silencio"

    def test_la_ventana_se_llena_con_bloques_sucesivos(self):
        """Alimentado por bloques, acaba juzgando: es un bufer circular."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        largo = rasgueo(DO_MAYOR, muestras=VENTANA_ACORDES * 2)
        estados = [
            detector.procesar(largo[i : i + 1008], DO_MAYOR).estado
            for i in range(0, largo.size - 1008, 1008)
        ]
        assert estados[0] == "silencio"
        assert "completo" in estados

    def test_reiniciar_vacia_el_bufer(self):
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        detector.procesar(rasgueo(DO_MAYOR), DO_MAYOR)
        detector.reiniciar()
        resultado = detector.procesar(rasgueo(DO_MAYOR)[:1008], DO_MAYOR)
        assert resultado.estado == "silencio"

    def test_una_ventana_con_energia_pero_sin_tono_no_da_nan(self):
        """Ruido blanco de nivel alto: la normalizacion no puede dar nan."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        generador = np.random.default_rng(0)
        resultado = detector.procesar(generador.normal(0.0, 0.2, VENTANA_ACORDES), DO_MAYOR)
        assert all(np.isfinite(v) for v in resultado.presencias.values())

    def test_una_constante_continua_no_da_nan(self):
        """Senal sin oscilacion: energia alta, saliencia cero en todo el rango."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        resultado = detector.procesar(np.full(VENTANA_ACORDES, 0.5), DO_MAYOR)
        assert all(np.isfinite(v) for v in resultado.presencias.values())
        assert resultado.estado == "incompleto"


class TestForma:
    def test_el_diccionario_es_el_del_websocket(self):
        resultado = detectar(DO_MAYOR, DO_MAYOR)
        como_dict = resultado.a_dict()
        assert set(como_dict) == {"estado", "presencias", "faltan", "nivel_db"}
        assert como_dict["estado"] == "completo"
        assert como_dict["faltan"] == []
        assert all(isinstance(k, str) for k in como_dict["presencias"])

    def test_una_ventana_absurda_se_rechaza_al_construir(self):
        with pytest.raises(ValueError):
            DetectorAcordes(GUITARRA, ventana=0)

    def test_el_umbral_es_el_de_la_spec(self):
        assert UMBRAL_PRESENCIA == 0.45
        assert VENTANA_ACORDES == 8192
