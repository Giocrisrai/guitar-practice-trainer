# tests/test_audio_real.py
"""Pruebas sobre grabaciones de la guitarra real.

Una senoide no se parece a una cuerda pulsada: falta el ataque, los armónicos que
decaen a distinto ritmo, el ruido de púa y la inarmonicidad de la cuerda. Estas
pruebas cierran esa brecha y convierten la guitarra concreta del usuario en una
verificación permanente.
"""

from pathlib import Path

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador

AUDIO = Path(__file__).parent / "audio"
GUITARRA = PERFILES["guitarra_estandar"]

CUERDAS = [
    ("cuerda_6_e2.wav", "E2", 6),
    ("cuerda_5_a2.wav", "A2", 5),
    ("cuerda_4_d3.wav", "D3", 4),
    ("cuerda_3_g3.wav", "G3", 3),
    ("cuerda_2_b3.wav", "B3", 2),
    ("cuerda_1_e4.wav", "E4", 1),
]


def analizar_archivo(nombre: str) -> list:
    """Recorre la grabación en ventanas solapadas y devuelve los resultados con nota."""
    ruta = AUDIO / nombre
    if not ruta.exists():
        pytest.skip(f"Falta {nombre}: ejecuta herramientas/grabar_muestras.py")
    muestras, frecuencia_muestreo = soundfile.read(ruta, dtype="float32")
    analizador = Analizador(GUITARRA, frecuencia_muestreo=frecuencia_muestreo)
    ventana = GUITARRA.tamano_ventana(frecuencia_muestreo)
    salto = ventana // 4

    resultados = []
    for inicio in range(0, len(muestras) - ventana, salto):
        resultado = analizador.procesar(muestras[inicio : inicio + ventana])
        if resultado.estado == "nota":
            resultados.append(resultado)
    return resultados


@pytest.mark.parametrize("archivo, nota_esperada, cuerda", CUERDAS)
def test_reconoce_cada_cuerda_real(archivo, nota_esperada, cuerda):
    resultados = analizar_archivo(archivo)
    assert resultados, f"No se detectó ninguna nota en {archivo}"
    correctas = [r for r in resultados if r.nota == nota_esperada]
    proporcion = len(correctas) / len(resultados)
    assert proporcion > 0.8, (
        f"Solo el {proporcion:.0%} de las ventanas dio {nota_esperada}. "
        f"Notas vistas: {sorted({r.nota for r in resultados})}"
    )


@pytest.mark.parametrize("archivo, nota_esperada, cuerda", CUERDAS)
def test_identifica_la_cuerda_correcta(archivo, nota_esperada, cuerda):
    resultados = [r for r in analizar_archivo(archivo) if r.nota == nota_esperada]
    assert resultados
    objetivos = [r.cuerda_objetivo for r in resultados]
    assert max(set(objetivos), key=objetivos.count) == cuerda


@pytest.mark.parametrize("archivo, nota_esperada, cuerda", CUERDAS)
def test_una_cuerda_afinada_se_lee_afinada(archivo, nota_esperada, cuerda):
    """La guitarra estaba afinada al grabar: el afinador debe coincidir."""
    resultados = [r for r in analizar_archivo(archivo) if r.nota == nota_esperada]
    assert resultados
    cents_medianos = float(np.median([r.cents for r in resultados]))
    assert abs(cents_medianos) < 15.0, f"Desviación mediana de {cents_medianos:.1f} cents"
