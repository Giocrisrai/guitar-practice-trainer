import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador, ResultadoAnalisis, Suavizador
from nucleo.musica import Posicion

FS = 48000
GUITARRA = PERFILES["guitarra_estandar"]


def senoide(frecuencia: float, muestras: int = 4096, amplitud: float = 0.3) -> np.ndarray:
    t = np.arange(muestras) / FS
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def test_el_suavizador_no_responde_hasta_llenarse():
    suavizador = Suavizador(tamano=3)
    assert suavizador.agregar(110.0) is None
    assert suavizador.agregar(110.0) is None
    assert suavizador.agregar(110.0) == pytest.approx(110.0)


def test_la_mediana_descarta_un_salto_de_octava():
    """El fallo típico de un detector de tono es un salto aislado al doble."""
    suavizador = Suavizador(tamano=5)
    for valor in [110.0, 110.0, 220.0, 110.0, 110.0]:
        resultado = suavizador.agregar(valor)
    assert resultado == pytest.approx(110.0)


def test_reiniciar_vacia_el_historial():
    suavizador = Suavizador(tamano=3)
    suavizador.agregar(110.0)
    suavizador.reiniciar()
    assert suavizador.agregar(110.0) is None


def test_el_silencio_no_produce_nota():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    resultado = analizador.procesar(np.zeros(4096, dtype=np.float32))
    assert resultado.estado == "silencio"
    assert resultado.nota is None
    assert resultado.posiciones == []


def test_el_ruido_no_inventa_una_nota():
    """Segunda puerta: pasa la energía pero no la confianza."""
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    generador = np.random.default_rng(3)
    ruido = generador.normal(0.0, 0.2, 4096).astype(np.float32)
    resultado = analizador.procesar(ruido)
    assert resultado.estado == "silencio"


def test_una_cuerda_al_aire_se_identifica_completa():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    resultado = analizador.procesar(senoide(82.41))
    assert resultado.estado == "nota"
    assert resultado.nota == "E2"
    assert resultado.cents == pytest.approx(0.0, abs=3.0)
    assert resultado.afinada is True
    assert resultado.cuerda_objetivo == 6
    assert Posicion(cuerda=6, traste=0) in resultado.posiciones


def test_una_cuerda_desafinada_se_marca_como_tal():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    grave = 82.41 * 2 ** (-20.0 / 1200.0)
    resultado = analizador.procesar(senoide(grave))
    assert resultado.nota == "E2"
    assert resultado.cents == pytest.approx(-20.0, abs=3.0)
    assert resultado.afinada is False


def test_la_nota_ambigua_muestra_todas_sus_posiciones():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    resultado = analizador.procesar(senoide(110.0))
    assert Posicion(cuerda=5, traste=0) in resultado.posiciones
    assert Posicion(cuerda=6, traste=5) in resultado.posiciones


def test_el_umbral_de_confianza_es_configurable():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, confianza_minima=0.0,
                            tamano_suavizado=1)
    generador = np.random.default_rng(3)
    ruido = generador.normal(0.0, 0.2, 4096).astype(np.float32)
    assert analizador.procesar(ruido).estado == "nota"


def test_el_perfil_de_bajo_usa_su_propia_ventana():
    analizador = Analizador(PERFILES["bajo_5"], frecuencia_muestreo=FS, tamano_suavizado=1)
    resultado = analizador.procesar(senoide(30.87, muestras=8192))
    assert resultado.estado == "nota"
    assert resultado.nota == "B0"


def test_el_diccionario_emitido_tiene_la_forma_de_la_spec():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    emitido = analizador.procesar(senoide(82.41)).a_dict()
    assert set(emitido) == {
        "estado", "frecuencia", "nota", "cents", "confianza",
        "nivel_db", "posiciones", "cuerda_objetivo", "afinada",
    }
    assert emitido["posiciones"] == [{"cuerda": 6, "traste": 0}]
