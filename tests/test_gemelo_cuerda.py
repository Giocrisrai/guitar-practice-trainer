# tests/test_gemelo_cuerda.py
"""La cuerda pulsada sintetica, vista por el detector de tono real.

El valor de estas pruebas esta en que no comprueban la sintesis contra si misma:
la altura se verifica con el `Analizador` de produccion, el mismo objeto que
recibe el audio del cable. Si la cuerda sintetica no se parece a una cuerda, el
detector no la reconoce y la prueba cae.
"""

import re
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


def cents_leidos(onda: np.ndarray) -> list[float]:
    """Desviacion en cents que el detector real lee en cada ventana con nota."""
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    ventana = GUITARRA.tamano_ventana(FS)

    cents = []
    for inicio in range(0, len(onda) - ventana + 1, SALTO):
        resultado = analizador.procesar(onda[inicio : inicio + ventana])
        if resultado.estado == "nota":
            cents.append(resultado.cents)
    return cents


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


@pytest.mark.parametrize("midi", ALTURAS)
def test_la_cuerda_esta_afinada(midi):
    """La cuerda sintetica no puede salir desafinada, y menos sin motivo.

    Con un anillo de un numero entero de muestras la altura solo cae exacta en
    las frecuencias que dividen los 48 kHz y el resto salen hasta 10 cents altas.
    Eso no es inarmonicidad de una cuerda real: es desafinacion, y `cents` y
    `afinada` del `Analizador` se leen en tareas posteriores y se pintan en
    pantalla. El retardo fraccionario del lazo es lo que mantiene esto por
    debajo de 5 cents.
    """
    cents = cents_leidos(cuerda_pulsada(midi, 0.6, semilla=1))
    assert cents, f"El detector no leyo ninguna nota para midi {midi}"
    peor = max(abs(valor) for valor in cents)
    assert peor < 5.0, f"midi {midi} sale {peor:.2f} cents desafinado"


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


# Las ocho primeras muestras y el valor eficaz de `cuerda_pulsada(50, 0.05,
# semilla=17)`, medidos sobre la cuerda limpia. Son valores dorados: los unicos
# de la suite que no se derivan de nada. Existen porque la decision "trasteo=0,0
# es exactamente la cuerda limpia" no se puede comprobar comparando dos llamadas
# —las dos pasarian cero y recorrerian el mismo camino— sino solo contra una
# referencia externa. Si una llamada con el trasteo por defecto deja de dar esto,
# algo contamino el camino limpio. Para regenerarlos cuando cambie la sintesis a
# proposito: imprimir `onda[:8].tolist()` y el RMS de esa misma llamada.
MUESTRAS_DORADAS = (
    0.554600179195404,
    -0.5448800921440125,
    0.0928063616156578,
    -0.2120203822851181,
    -0.458141952753067,
    -0.18350228667259216,
    -0.11545318365097046,
    0.17894934117794037,
)
RMS_DORADO = 0.2692625431203252


def test_el_trasteo_cero_da_exactamente_la_cuerda_limpia():
    """El valor por defecto no puede contaminar al resto de la etapa.

    Casi todas las notas del gemelo se pulsan con `trasteo` en cero: el perfil
    `PERFECTO`, que es el oraculo de la etapa, lo deja a cero SIEMPRE, y los otros
    tres solo lo levantan en las notas que sortean trasteadas (del 5% al 50%
    segun el perfil). Si con cero se colase algo de ruido o de acortamiento,
    ensuciaria todas las demas pruebas. El RMS vigila toda la onda y no solo la cabeza, para que un
    acortamiento del decaimiento tampoco pueda pasar: un trasteo de 0,01, cien
    veces menor que el que usa la prueba de suciedad, ya mueve las dos medidas.
    """
    onda = cuerda_pulsada(50, 0.05, semilla=17)
    assert onda[:8].tolist() == pytest.approx(MUESTRAS_DORADAS, abs=1e-7)
    assert rms(onda) == pytest.approx(RMS_DORADO, rel=1e-9)


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
    with pytest.raises(ValueError, match=re.escape(str(duracion_s))):
        cuerda_pulsada(40, duracion_s)


def test_una_nota_mas_corta_que_un_periodo_se_rechaza():
    """Por debajo de una vuelta del anillo no hay altura, hay ruido.

    No esta en el brief, pero las tareas siguientes generan notas cortas a
    tempos rapidos y una nota sin altura haria fallar sus pruebas de
    reconocimiento por el motivo equivocado. Mejor un error que lo diga. El
    limite es diminuto: un periodo del E2 son 12 ms y uno del C5, 2 ms.
    """
    un_periodo_de_e2 = 1.0 / 82.41
    with pytest.raises(ValueError, match="periodo"):
        cuerda_pulsada(40, un_periodo_de_e2 * 0.9)
    # Justo por encima del limite si sale, y sale con la duracion pedida.
    onda = cuerda_pulsada(40, un_periodo_de_e2 * 1.1)
    assert len(onda) == int(un_periodo_de_e2 * 1.1 * FS)


@pytest.mark.parametrize("midi", [40, 72])
def test_generar_una_nota_es_barato(midi):
    """La suite genera miles de notas: una de 0,6 s tiene que costar < 5 ms.

    Las dos alturas son los dos extremos del coste: el E2 tiene un anillo de 582
    muestras y da ~50 vueltas, y el C5 lo tiene de 91 y da ~316, asi que el caso
    aguda es el que de verdad roza el tope.

    Se mide la mediana de varias repeticiones para que una pausa del recolector
    de basura no haga fallar la prueba.
    """
    costes = []
    for indice in range(9):
        inicio = time.perf_counter()
        cuerda_pulsada(midi, 0.6, semilla=indice)
        costes.append(time.perf_counter() - inicio)
    mediana_ms = float(np.median(costes)) * 1000
    assert mediana_ms < 5.0, (
        f"Una nota de 0,6 s en midi {midi} costo {mediana_ms:.2f} ms"
    )
