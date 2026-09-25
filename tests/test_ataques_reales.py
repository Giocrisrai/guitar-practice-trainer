"""Deteccion de ataques sobre las grabaciones reales de la guitarra del usuario.

Las envolventes sinteticas son demasiado limpias: una cuerda real trae ruido de
pua, decaimiento irregular y resonancia de las vecinas. Estas pruebas se saltan
mientras no existan las grabaciones, igual que las de test_audio_real.py.
"""

from pathlib import Path

import pytest

soundfile = pytest.importorskip("soundfile")

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import nivel_dbfs
from nucleo.ejercicios.ataques import DetectorAtaques
from servidor.sesion import INTERVALO_ANALISIS

AUDIO = Path(__file__).parent / "audio"
GUITARRA = PERFILES["guitarra_estandar"]
# El mismo paso con el que el servidor analiza en vivo: calibrar con otro
# paso daria numeros que no sirven en produccion.
PASO_ANALISIS = INTERVALO_ANALISIS

CUERDAS = [
    "cuerda_6_e2.wav",
    "cuerda_5_a2.wav",
    "cuerda_4_d3.wav",
    "cuerda_3_g3.wav",
    "cuerda_2_b3.wav",
    "cuerda_1_e4.wav",
]


def ataques_de(nombre: str) -> list:
    ruta = AUDIO / nombre
    if not ruta.exists():
        pytest.skip(f"Falta {nombre}: ejecuta herramientas/grabar_muestras.py")
    muestras, fs = soundfile.read(ruta, dtype="float32")
    ventana = GUITARRA.tamano_ventana(fs)
    salto = int(PASO_ANALISIS * fs)
    detector = DetectorAtaques()
    ataques = []
    for indice in range(0, len(muestras) - ventana, salto):
        nivel = nivel_dbfs(muestras[indice : indice + ventana])
        ataque = detector.procesar(nivel, indice / fs)
        if ataque is not None:
            ataques.append(ataque)
    return ataques


@pytest.mark.parametrize("archivo", CUERDAS)
def test_una_cuerda_pulsada_una_vez_da_un_solo_ataque(archivo):
    """El decaimiento de una nota real no debe marcar ataques nuevos."""
    ataques = ataques_de(archivo)
    assert len(ataques) == 1, f"{len(ataques)} ataques en {archivo}: revisa el refractario"


@pytest.mark.parametrize("archivo", CUERDAS)
def test_el_ataque_cae_al_principio_de_la_grabacion(archivo):
    """La grabacion empieza con el ataque: el script espera a que suene para grabar."""
    ataques = ataques_de(archivo)
    assert ataques, f"ningun ataque en {archivo}: revisa el salto y el umbral de ruido"
    assert ataques[0].instante < 0.5
