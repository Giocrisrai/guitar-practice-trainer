"""Detector de tono YIN (Cheveigné y Kawahara, 2002).

Función pura: mismas muestras, mismo resultado, sin estado interno. Esa pureza es
lo que permite probarlo con señales sintéticas de frecuencia conocida.
"""

import numpy as np

from nucleo.analisis.registro import ResultadoTono, registrar

# Bajo este valor de d'(τ) se considera que hay un periodo creíble. 0,15 es el valor
# propuesto en el artículo original y funciona bien con señal de pastilla eléctrica.
UMBRAL_YIN_POR_DEFECTO = 0.15


def _funcion_diferencia(muestras: np.ndarray, tau_maximo: int) -> np.ndarray:
    """Función de diferencia de YIN, calculada vía FFT.

        d(τ) = Σⱼ (x[j] − x[j+τ])²
             = Σ x[j]² + Σ x[j+τ]² − 2·r(τ)

    donde r es la autocorrelación. Desarrollar el cuadrado permite obtener las tres
    piezas de golpe: las dos sumas con una suma acumulada y r con una FFT. Calcular
    d(τ) con bucles en Python sería inviable en tiempo real.
    """
    x = muestras.astype(np.float64)
    n = x.size

    # Sumas acumuladas de x², para obtener cualquier Σ x[a:b]² en tiempo constante.
    acumulado = np.concatenate(([0.0], np.cumsum(x * x)))

    # Autocorrelación por FFT, con relleno a potencia de 2 para evitar el solape
    # circular que contaminaría los desfases grandes.
    tamano = 1 << (2 * n - 1).bit_length()
    espectro = np.fft.rfft(x, tamano)
    correlacion = np.fft.irfft(espectro * np.conj(espectro), tamano)[:tau_maximo]

    tau = np.arange(tau_maximo)
    energia_inicial = acumulado[n - tau] - acumulado[0]
    energia_desplazada = acumulado[n] - acumulado[tau]
    return energia_inicial + energia_desplazada - 2.0 * correlacion


def _diferencia_normalizada(diferencia: np.ndarray) -> np.ndarray:
    """Diferencia media acumulada normalizada.

        d′(τ) = d(τ) · τ / Σ_{k=1..τ} d(k)

    Normalizar es necesario porque d(0) vale siempre exactamente cero y sería
    siempre el mínimo global. Con d′(0) = 1 por convenio, el resto queda comparable.
    """
    normalizada = np.ones_like(diferencia)
    acumulado = np.cumsum(diferencia[1:])
    tau = np.arange(1, diferencia.size)
    # Donde el acumulado es cero (señal constante) se deja el valor 1: sin periodo.
    seguro = acumulado > 0.0
    normalizada[1:][seguro] = (diferencia[1:] * tau / acumulado)[seguro]
    return normalizada


def _refinar_con_parabola(valores: np.ndarray, indice: int) -> float:
    """Ajusta una parábola a los tres puntos alrededor del mínimo y devuelve su vértice.

    Sin este refinamiento la resolución queda limitada a muestras enteras: a 48 kHz
    el periodo de un E2 son 582,5 muestras y errar por una ya son casi 3 cents.
    """
    if indice <= 0 or indice >= valores.size - 1:
        return float(indice)
    anterior, actual, siguiente = valores[indice - 1], valores[indice], valores[indice + 1]
    denominador = 2.0 * (2.0 * actual - siguiente - anterior)
    if denominador == 0.0:
        return float(indice)
    return float(indice + (siguiente - anterior) / denominador)


def detectar_yin(
    muestras: np.ndarray,
    frecuencia_muestreo: int,
    frecuencia_minima: float,
    frecuencia_maxima: float,
    umbral: float = UMBRAL_YIN_POR_DEFECTO,
) -> ResultadoTono:
    """Estima la frecuencia fundamental de la ventana y la confianza de esa estimación.

    Devuelve frecuencia 0.0 y confianza 0.0 cuando la ventana es demasiado corta
    para contener periodos de la frecuencia mínima pedida.
    """
    tau_minimo = max(2, int(frecuencia_muestreo / frecuencia_maxima))
    tau_maximo = min(muestras.size - 1, int(frecuencia_muestreo / frecuencia_minima) + 1)
    if tau_maximo <= tau_minimo:
        return ResultadoTono(frecuencia=0.0, confianza=0.0)

    diferencia = _funcion_diferencia(muestras, tau_maximo + 1)
    normalizada = _diferencia_normalizada(diferencia)

    # Se busca el PRIMER mínimo bajo el umbral, no el global. Un armónico también
    # produce un mínimo profundo; quedarse con el primero prioriza el periodo más
    # largo, que es el de la fundamental. Aquí se evita el error de octava.
    ventana = normalizada[tau_minimo : tau_maximo + 1]
    candidatos = np.flatnonzero(ventana < umbral)
    if candidatos.size > 0:
        indice = tau_minimo + int(candidatos[0])
        # Descender hasta el fondo de ese valle antes de interpolar.
        while indice + 1 <= tau_maximo and normalizada[indice + 1] < normalizada[indice]:
            indice += 1
    else:
        indice = tau_minimo + int(np.argmin(ventana))

    periodo = _refinar_con_parabola(normalizada, indice)
    if periodo <= 0.0:
        return ResultadoTono(frecuencia=0.0, confianza=0.0)

    frecuencia = frecuencia_muestreo / periodo
    confianza = float(np.clip(1.0 - normalizada[indice], 0.0, 1.0))
    return ResultadoTono(frecuencia=float(frecuencia), confianza=confianza)


registrar("yin", detectar_yin)
