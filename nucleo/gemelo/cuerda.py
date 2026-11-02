"""Una cuerda pulsada sintetica: el ladrillo del gemelo digital.

El gemelo necesita audio que el detector de tono real reconozca, y una senoide no
lo es: le falta el ataque, los armonicos que mueren a distinto ritmo y el ruido de
la pua. Lo que si lo es, con cuatro lineas de aritmetica, es Karplus-Strong: se
llena un anillo de ruido tan largo como un periodo de la nota y se hace circular
pasandolo por un promedio de dos muestras. El anillo fija la altura; el promedio
es un filtro paso bajo que en cada vuelta se come un poco de agudo, y de ahi sale
sola la envolvente de una cuerda: ataque brillante, cola oscura.

    y[m] = p · y[m-N] + (1-p) · y[m-N+1]

con N = max(2, round(fs / f0)) muestras de anillo y p el peso que sale de `brillo`.
"""

import numpy as np

# Pesos del promedio del anillo. 0,5 es la media simple (el maximo de
# amortiguacion: anula del todo la frecuencia de Nyquist en cada vuelta) y hacia
# 1 el promedio filtra cada vez menos, asi que conserva mas agudo y decae mas
# despacio. No se llega a 1: ahi el anillo no pierde nada y la nota no decaeria.
PESO_MINIMO = 0.5
PESO_MAXIMO = 0.95

# Cuanto ruido de banda ancha mete el trasteo, como fraccion del pico de la
# cuerda, y cuantos nepers por segundo le acorta el decaimiento, los dos a
# `trasteo` = 1. Calibrados midiendo el detector real sobre un E2 de 0,6 s: la
# proporcion de ventanas que leen la nota correcta baja de 0,84 con trasteo 0 a
# 0,56 con 0,6 y a 0,08 con 0,8. Es un degradado, no un interruptor.
RUIDO_DE_TRASTEO = 0.3
AMORTIGUACION_DE_TRASTEO = 3.0


def frecuencia_de_midi(midi: int, referencia_a4: float = 440.0) -> float:
    """Frecuencia de una nota MIDI en Hz: f = f_A4 · 2^((midi - 69) / 12)."""
    return referencia_a4 * 2.0 ** ((midi - 69) / 12.0)


def cuerda_pulsada(
    midi: int,
    duracion_s: float,
    frecuencia_muestreo: int = 48000,
    brillo: float = 0.5,
    fuerza: float = 0.8,
    trasteo: float = 0.0,
    semilla: int | None = None,
) -> np.ndarray:
    """Sintetiza una cuerda pulsada a la altura `midi`.

    Parametros:
        midi: altura de la nota (69 es el La4 de 440 Hz).
        duracion_s: duracion en segundos, estrictamente positiva.
        frecuencia_muestreo: muestras por segundo.
        brillo: 0 es la media simple del anillo (la pulsacion mas oscura, la que
            decae mas rapido) y 1 la mas brillante. Se recorta a [0, 1].
        fuerza: amplitud de pico exacta de la onda devuelta.
        trasteo: suciedad de la pulsacion, en [0, 1]. Anade ruido de banda ancha
            y acorta el decaimiento. Con 0,0 la cuerda sale exactamente limpia:
            ni una muestra de ruido ni un neper de amortiguacion extra, porque
            es el valor que usa casi todo el gemelo y cualquier contaminacion
            aqui ensuciaria el resto de la etapa.
        semilla: semilla del generador de ruido. Con la misma semilla la onda es
            identica muestra a muestra; con None cada llamada es distinta.

    Devuelve un `np.ndarray` float32 mono de `int(duracion_s * frecuencia_muestreo)`
    muestras, con pico exactamente `fuerza`.
    """
    if duracion_s <= 0.0:
        raise ValueError(f"la duracion tiene que ser positiva, no {duracion_s}")

    total = int(duracion_s * frecuencia_muestreo)
    if total <= 0:
        raise ValueError(
            f"la duracion {duracion_s} s a {frecuencia_muestreo} Hz no da ni una muestra"
        )

    generador = np.random.default_rng(semilla)
    peso = PESO_MINIMO + (PESO_MAXIMO - PESO_MINIMO) * float(np.clip(brillo, 0.0, 1.0))
    onda = _anillo_de_karplus_strong(
        largo_anillo=max(2, round(frecuencia_muestreo / frecuencia_de_midi(midi))),
        total=total,
        peso=peso,
        generador=generador,
    )

    if trasteo > 0.0:
        # El ruido del traste y la cuerda que se apaga antes. Las dos cosas van
        # dentro del `if` para que `trasteo` = 0 no toque ni la onda ni el estado
        # del generador: la cuerda limpia tiene que ser bit a bit la misma.
        suciedad = float(np.clip(trasteo, 0.0, 1.0))
        onda += suciedad * RUIDO_DE_TRASTEO * generador.uniform(-1.0, 1.0, total)
        segundos = np.arange(total) / frecuencia_muestreo
        onda *= np.exp(-suciedad * AMORTIGUACION_DE_TRASTEO * segundos)

    return _normalizada_al_pico(onda, fuerza)


def _anillo_de_karplus_strong(
    largo_anillo: int, total: int, peso: float, generador: np.random.Generator
) -> np.ndarray:
    """Hace circular un anillo de ruido y devuelve `total` muestras en float64.

    Se recorre por periodos y no muestra a muestra: el bloque de muestras de una
    vuelta del anillo depende entero del bloque anterior, asi que cada vuelta son
    dos operaciones de numpy sobre vectores de `largo_anillo` y no `largo_anillo`
    iteraciones de Python. Para una nota de 0,6 s son ~50 vueltas en lugar de
    29 000 pasos, que es la diferencia entre microsegundos y decimas de segundo.

    El unico detalle del troceo es la ultima muestra de cada bloque: su "siguiente"
    ya pertenece al bloque nuevo (es su primera muestra, recien calculada), no al
    viejo.
    """
    vueltas = -(-total // largo_anillo)  # division entera hacia arriba
    buzon = np.empty(vueltas * largo_anillo, dtype=np.float64)
    buzon[:largo_anillo] = generador.uniform(-1.0, 1.0, largo_anillo)

    for vuelta in range(1, vueltas):
        anterior = buzon[(vuelta - 1) * largo_anillo : vuelta * largo_anillo]
        actual = buzon[vuelta * largo_anillo : (vuelta + 1) * largo_anillo]
        actual[:-1] = peso * anterior[:-1] + (1.0 - peso) * anterior[1:]
        actual[-1] = peso * anterior[-1] + (1.0 - peso) * actual[0]

    return buzon[:total]


def _normalizada_al_pico(onda: np.ndarray, fuerza: float) -> np.ndarray:
    """Escala la onda a pico exactamente `fuerza` y la pasa a float32.

    Se divide en float64 y se multiplica ya en float32 para que el pico sobreviva
    al cambio de precision: la muestra mayor vale 1,0 exacto antes de la conversion.
    """
    pico = float(np.max(np.abs(onda)))
    if pico == 0.0:
        return np.zeros(onda.size, dtype=np.float32)
    normalizada = (onda / pico).astype(np.float32)
    normalizada *= np.float32(fuerza)
    return normalizada
