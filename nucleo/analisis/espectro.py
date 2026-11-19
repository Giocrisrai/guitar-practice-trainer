"""Espectro de magnitud y saliencia armonica: la capa pura de la polifonia.

Funciones puras, sin estado: mismas muestras, mismo resultado. Es lo que permite
probar la deteccion de acordes con senal sintetica y sin hardware, igual que la
pureza de `yin.py` permite probar el detector monofonico.

El metodo no transcribe, verifica. Dada una nota concreta, mide cuanta energia hay
donde esa nota deberia tenerla. La spec de la etapa 2b explica por que eso basta:
en los dos casos de uso -el ejercicio de cambios y el carril- el programa ya sabe
que notas espera, asi que la pregunta cerrada "estan sonando estas cinco notas"
sustituye a la abierta "que acorde es esto", que es un problema de investigacion.
"""

import numpy as np

from nucleo.musica import midi_a_frecuencia

# Cuantos armonicos se suman como prueba de que una nota suena.
#
# Seis y no mas: por encima del sexto los armonicos de las distintas notas de un
# acorde se solapan tanto que dejan de distinguir cual suena. Y no menos, porque
# la fundamental de una cuerda grave es debil en una pastilla electrica -el
# segundo y el tercer armonico suelen pesar mas- y quedarse en dos o tres haria
# depender el veredicto justo del armonico mas flojo.
ARMONICOS_POR_DEFECTO = 6

# Medio ancho de la banda alrededor de cada armonico, en cents.
#
# 35 cents es un tercio de semitono: tolera que la cuerda real este algo
# desafinada y que sus armonicos no sean multiplos exactos de la fundamental
# (inarmonicidad de una cuerda con rigidez), sin llegar a invadir el semitono
# vecino, que esta a 100.
ANCHO_BANDA_CENTS = 35.0


def espectro_de_magnitud(
    muestras: np.ndarray, frecuencia_muestreo: int
) -> tuple[np.ndarray, np.ndarray]:
    """Magnitud del espectro de la ventana, y la frecuencia de cada bin.

    Se aplica una ventana de Hann antes de la FFT, y no es decorativo: sin ella el
    suelo de fuga espectral de la nota mas fuerte del acorde tapa a las mas
    debiles, que son justo las que hay que detectar. Sin ventana (es decir, con un
    rectangulo) los lobulos laterales caen a -13 dB; con Hann, a -31 dB.
    """
    x = np.asarray(muestras, dtype=np.float64).ravel()
    if x.size == 0:
        return np.zeros(0), np.zeros(0)
    magnitud = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    frecuencias = np.fft.rfftfreq(x.size, 1.0 / frecuencia_muestreo)
    return frecuencias, magnitud


def saliencia_de_nota(
    frecuencias: np.ndarray,
    magnitud: np.ndarray,
    midi: int,
    armonicos: int = ARMONICOS_POR_DEFECTO,
    ancho_cents: float = ANCHO_BANDA_CENTS,
    referencia_a4: float = 440.0,
) -> float:
    """Cuanta prueba hay de que la nota `midi` esta sonando en esta ventana.

        saliencia = suma sobre h de  max{ |X(f)| : f en banda(h·f0) } / h

    El maximo dentro de una banda, y no el valor de un bin: ni la cuerda esta
    exactamente afinada ni sus armonicos caen exactamente en h·f0. La ponderacion
    1/h baja el peso de los armonicos altos porque los comparten varias notas del
    acorde y prueban menos sobre cual de ellas suena.

    Devuelve 0.0 cuando no hay donde medir: espectro vacio, o una nota cuyos
    armonicos caen todos por encima de Nyquist.
    """
    if armonicos < 1:
        raise ValueError("Hacen falta al menos 1 armonico para medir saliencia")
    if ancho_cents <= 0.0:
        raise ValueError("El ancho de banda en cents tiene que ser positivo")
    if frecuencias.size == 0:
        return 0.0

    f0 = midi_a_frecuencia(midi, referencia_a4)
    factor = 2.0 ** (ancho_cents / 1200.0)
    total = 0.0
    for h in range(1, armonicos + 1):
        centro = f0 * h
        if centro >= frecuencias[-1]:
            break
        banda = magnitud[(frecuencias >= centro / factor) & (frecuencias <= centro * factor)]
        if banda.size > 0:
            total += float(np.max(banda)) / h
    return total
