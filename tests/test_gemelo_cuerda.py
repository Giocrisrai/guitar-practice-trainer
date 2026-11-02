# tests/test_gemelo_cuerda.py
"""La cuerda pulsada sintetica, vista por el detector de tono real.

El valor de estas pruebas esta en que no comprueban la sintesis contra si misma:
la altura se verifica con el `Analizador` de produccion, el mismo objeto que
recibe el audio del cable. Si la cuerda sintetica no se parece a una cuerda, el
detector no la reconoce y la prueba cae.
"""

import time

import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador
from nucleo.gemelo.cuerda import cuerda_pulsada
from nucleo.musica import nombre_de_midi

FS = 48000
GUITARRA = PERFILES["guitarra_estandar"]
SALTO = 1008  # el salto de produccion: 21 ms

# Las ocho alturas del gemelo: las seis cuerdas al aire mas dos notas pisadas.
ALTURAS = [40, 45, 50, 55, 59, 64, 67, 72]


def proporcion_de_acierto(onda: np.ndarray, nota_esperada: str) -> float:
    """Fraccion de ventanas con estado "nota" cuyo nombre es el esperado.

    Recorre la onda como lo hace la sesion de estudio: ventanas de
    `perfil.tamano_ventana(FS)` con salto `SALTO`. Las ventanas que el analisis
    declara silencio (por energia, por confianza o por el calentamiento del
    suavizado) no cuentan ni a favor ni en contra.
    """
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    ventana = GUITARRA.tamano_ventana(FS)

    nombres = []
    for inicio in range(0, len(onda) - ventana + 1, SALTO):
        resultado = analizador.procesar(onda[inicio : inicio + ventana])
        if resultado.estado == "nota":
            nombres.append(resultado.nota)

    if not nombres:
        return 0.0
    return sum(nombre == nota_esperada for nombre in nombres) / len(nombres)


def proporcion_sobre_todas_las_ventanas(onda: np.ndarray, nota_esperada: str) -> float:
    """Fraccion de TODAS las ventanas que leen la nota esperada.

    Para medir el trasteo hace falta este denominador y no el de
    `proporcion_de_acierto`: el detector, cuando se decide, acierta el nombre
    casi siempre, y lo que el trasteo le quita es la decision (se calla por
    energia o por confianza). Contando solo las ventanas que ya dieron nota, una
    cuerda muy sucia con dos lecturas buenas saldria con el 100% de acierto.
    """
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    ventana = GUITARRA.tamano_ventana(FS)

    aciertos = 0
    total = 0
    for inicio in range(0, len(onda) - ventana + 1, SALTO):
        resultado = analizador.procesar(onda[inicio : inicio + ventana])
        total += 1
        if resultado.estado == "nota" and resultado.nota == nota_esperada:
            aciertos += 1
    return aciertos / total


def rms(muestras: np.ndarray) -> float:
    """Valor eficaz, la medida de energia de un tramo."""
    return float(np.sqrt(np.mean(np.square(muestras.astype(np.float64)))))


def centroide_espectral(muestras: np.ndarray) -> float:
    """Centro de gravedad del espectro en Hz: cuanto mas agudo, mas alto."""
    espectro = np.abs(np.fft.rfft(muestras.astype(np.float64)))
    frecuencias = np.fft.rfftfreq(muestras.size, 1 / FS)
    return float(np.sum(frecuencias * espectro) / np.sum(espectro))


def quinto(onda: np.ndarray, indice: int) -> np.ndarray:
    """El quinto numero `indice` (desde 0) de la onda."""
    paso = len(onda) // 5
    return onda[indice * paso : (indice + 1) * paso]


@pytest.mark.parametrize("midi", ALTURAS)
def test_la_cuerda_suena_a_la_altura_pedida(midi):
    """El detector real tiene que leer la nota que se pidio sintetizar."""
    esperada = nombre_de_midi(midi)
    onda = cuerda_pulsada(midi, 0.6, semilla=1)
    proporcion = proporcion_de_acierto(onda, esperada)
    assert proporcion > 0.9, (
        f"Solo el {proporcion:.0%} de las ventanas dio {esperada} para midi {midi}"
    )


def test_la_cuerda_decae():
    """Una senoide con envolvente plana pasaria todo lo demas y esto no."""
    onda = cuerda_pulsada(45, 1.0, semilla=3)
    assert rms(quinto(onda, 4)) < rms(quinto(onda, 0))


def test_el_brillo_alto_conserva_mas_agudos_que_el_bajo():
    clara = cuerda_pulsada(50, 0.6, brillo=0.9, semilla=5)
    oscura = cuerda_pulsada(50, 0.6, brillo=0.1, semilla=5)
    assert centroide_espectral(quinto(clara, 1)) > centroide_espectral(
        quinto(oscura, 1)
    )


@pytest.mark.parametrize("fuerza", [0.3, 0.9])
def test_la_fuerza_es_la_amplitud_de_pico(fuerza):
    onda = cuerda_pulsada(64, 0.3, fuerza=fuerza, semilla=11)
    assert np.max(np.abs(onda)) == pytest.approx(fuerza, abs=1e-6)


def test_la_misma_semilla_da_la_misma_onda():
    """El gemelo tiene que ser reproducible: una semilla, una onda."""
    primera = cuerda_pulsada(55, 0.3, semilla=7)
    segunda = cuerda_pulsada(55, 0.3, semilla=7)
    otra = cuerda_pulsada(55, 0.3, semilla=8)
    assert np.array_equal(primera, segunda)
    assert not np.array_equal(primera, otra)


def test_el_trasteo_ensucia_la_nota():
    limpia = cuerda_pulsada(40, 0.6, trasteo=0.0, semilla=13)
    sucia = cuerda_pulsada(40, 0.6, trasteo=0.8, semilla=13)
    esperada = nombre_de_midi(40)
    assert proporcion_sobre_todas_las_ventanas(
        sucia, esperada
    ) < proporcion_sobre_todas_las_ventanas(limpia, esperada)


def test_el_trasteo_cero_no_toca_la_cuerda_limpia():
    """El valor por defecto no puede contaminar al resto de la etapa.

    Todos los perfiles del gemelo salvo uno dejan `trasteo` en cero: si con cero
    se colase algo de ruido o de acortamiento, ensuciaria todas las demas pruebas.
    """
    por_defecto = cuerda_pulsada(50, 0.4, semilla=17)
    explicito = cuerda_pulsada(50, 0.4, trasteo=0.0, semilla=17)
    assert np.array_equal(por_defecto, explicito)


@pytest.mark.parametrize("duracion_s", [0.1, 0.5, 2.0])
def test_la_duracion_es_la_pedida(duracion_s):
    onda = cuerda_pulsada(40, duracion_s)
    assert len(onda) == int(duracion_s * FS)


def test_la_onda_es_float32_y_mono():
    onda = cuerda_pulsada(40, 0.1)
    assert onda.dtype == np.float32
    assert onda.ndim == 1


@pytest.mark.parametrize("duracion_s", [0.0, -1.0])
def test_una_duracion_no_positiva_se_rechaza(duracion_s):
    with pytest.raises(ValueError, match=str(duracion_s)):
        cuerda_pulsada(40, duracion_s)


def test_generar_una_nota_es_barato():
    """La suite genera miles de notas: una de 0,6 s tiene que costar < 5 ms.

    Se mide la mediana de varias repeticiones para que una pausa del recolector
    de basura no haga fallar la prueba.
    """
    costes = []
    for indice in range(9):
        inicio = time.perf_counter()
        cuerda_pulsada(40, 0.6, semilla=indice)
        costes.append(time.perf_counter() - inicio)
    mediana_ms = float(np.median(costes)) * 1000
    assert mediana_ms < 5.0, f"Una nota de 0,6 s costo {mediana_ms:.2f} ms"
