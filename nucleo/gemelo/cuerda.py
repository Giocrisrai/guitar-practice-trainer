"""Una cuerda pulsada sintetica: el ladrillo del gemelo digital.

El gemelo necesita audio que el detector de tono real reconozca, y una senoide no
lo es: le falta el ataque, los armonicos que mueren a distinto ritmo y el ruido de
la pua. Lo que si lo es, con cuatro lineas de aritmetica, es Karplus-Strong: se
llena un anillo de ruido tan largo como un periodo de la nota y se hace circular
pasandolo por un promedio de dos muestras. El anillo fija la altura; el promedio
es un filtro paso bajo que en cada vuelta se come un poco de agudo, y de ahi sale
sola la envolvente de una cuerda: ataque brillante, cola oscura.

El anillo no mide un numero entero de muestras. Si midiese `round(fs / f0)`, la
altura solo podria caer en las frecuencias que dividen exacto los 48 kHz y el
resto saldrian desafinadas hasta 10 cents, que es desafinacion audible y ademas
mentira: una guitarra afinada no la tiene. Asi que el retardo del lazo es
fraccionario, interpolando linealmente entre las dos muestras que rodean el
periodo exacto. El lazo completo son tres tomas:

    y[m] = a · y[m-M] + b · y[m-M-1] + c · y[m-M-2]

y su retardo —la suma de cada toma por su peso— se iguala al periodo exacto
`fs / f0`. Ver `_pesos_del_lazo`.
"""

import numpy as np

from nucleo.musica import midi_a_frecuencia

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
        duracion_s: duracion en segundos. Tiene que ser positiva y dar para al
            menos un periodo de la nota; por debajo de eso el anillo no da ni
            una vuelta y lo que saldria es ruido sin altura, asi que se rechaza.
        frecuencia_muestreo: muestras por segundo.
        brillo: 0 es la media simple del anillo (la pulsacion mas oscura, la que
            decae mas rapido) y 1 la mas brillante. Se recorta a [0, 1].
            Atencion: **el 0 es la media simple, no el 0,5**. El filtro del
            anillo tiene la misma respuesta en magnitud con peso p que con 1-p,
            asi que un mapa centrado en 0,5 haria que `brillo` 0,1 y 0,9 sonasen
            exactamente igual. Ver `_peso_del_promedio`.
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
    periodo = frecuencia_muestreo / midi_a_frecuencia(midi)
    peso = _peso_del_promedio(brillo)
    largo_anillo, pesos = _pesos_del_lazo(periodo, peso)
    if total < largo_anillo:
        minimo = largo_anillo / frecuencia_muestreo
        raise ValueError(
            f"la duracion {duracion_s} s no llega a un periodo de la nota midi "
            f"{midi}: hacen falta al menos {minimo:.4f} s ({largo_anillo} muestras) "
            f"para que el anillo de una vuelta, y por debajo de eso no hay altura"
        )

    generador = np.random.default_rng(semilla)
    onda = _anillo_de_karplus_strong(largo_anillo, pesos, total, generador)

    if trasteo > 0.0:
        # El ruido del traste y la cuerda que se apaga antes. Las dos cosas van
        # dentro del `if` para que `trasteo` = 0 no toque ni la onda ni el estado
        # del generador: la cuerda limpia tiene que ser bit a bit la misma.
        suciedad = float(np.clip(trasteo, 0.0, 1.0))
        onda += suciedad * RUIDO_DE_TRASTEO * generador.uniform(-1.0, 1.0, total)
        segundos = np.arange(total) / frecuencia_muestreo
        onda *= np.exp(-suciedad * AMORTIGUACION_DE_TRASTEO * segundos)

    return _normalizada_al_pico(onda, fuerza)


def _peso_del_promedio(brillo: float) -> float:
    """Peso del promedio del anillo a partir de `brillo`, en [0, 1].

    `brillo` = 0 da la media simple (`PESO_MINIMO`) y 1 el promedio que menos
    filtra (`PESO_MAXIMO`). El mapa es monotono en todo el rango a proposito: la
    respuesta en magnitud del promedio, |p + (1-p)e^{jω}|, es simetrica al
    cambiar p por 1-p, asi que un peso de 0,3 suena exactamente igual que uno de
    0,7 y cualquier mapa centrado en 0,5 dejaria media escala de `brillo`
    duplicando la otra mitad.
    """
    return PESO_MINIMO + (PESO_MAXIMO - PESO_MINIMO) * float(np.clip(brillo, 0.0, 1.0))


def _pesos_del_lazo(
    periodo: float, peso: float
) -> tuple[int, tuple[float, float, float]]:
    """Largo entero del anillo y los tres pesos del lazo, para un periodo exacto.

    El lazo encadena dos filtros: el promedio de dos muestras que oscurece la
    cuerda (pesos `peso` y `1 - peso`, retardo `1 - peso`) y un interpolador
    lineal que reparte el retardo entre dos muestras vecinas (pesos `1 - δ` y
    `δ`, retardo `δ`). Convolucionarlos da tres tomas a los retardos M, M+1 y
    M+2, cuyo retardo total es M + (1 - peso) + δ. Igualarlo al periodo exacto
    deja M = ⌊periodo - 1 + peso⌋ y δ la parte fraccionaria.

    Se usa el retardo en continua, que para un filtro FIR es Σ k·h[k]; en la
    frecuencia fundamental el retardo real difiere en centesimas de muestra, muy
    por debajo del cent.
    """
    retardo = max(2.0, periodo - 1.0 + peso)
    largo_anillo = int(retardo)
    fraccion = retardo - largo_anillo
    pesos = (
        (1.0 - fraccion) * peso,
        (1.0 - fraccion) * (1.0 - peso) + fraccion * peso,
        fraccion * (1.0 - peso),
    )
    return largo_anillo, pesos


def _anillo_de_karplus_strong(
    largo_anillo: int,
    pesos: tuple[float, float, float],
    total: int,
    generador: np.random.Generator,
) -> np.ndarray:
    """Hace circular un anillo de ruido y devuelve `total` muestras en float64.

    Se recorre por periodos y no muestra a muestra: las tres tomas del lazo estan
    a retardos M, M+1 y M+2, todos mayores o iguales que el largo del anillo, asi
    que un bloque entero de M muestras depende solo de muestras anteriores a el y
    sale de tres multiplicaciones de numpy. Para una nota de 0,6 s son ~50
    vueltas en lugar de 29 000 pasos de Python, que es la diferencia entre
    microsegundos y decimas de segundo.

    Las dos muestras de prehistoria en cabeza son las que leen las tomas M+1 y
    M+2 durante la primera vuelta; valen cero y no se devuelven.
    """
    primera, segunda, tercera = pesos
    vueltas = -(-total // largo_anillo)  # division entera hacia arriba
    buzon = np.zeros(2 + vueltas * largo_anillo, dtype=np.float64)
    buzon[2 : 2 + largo_anillo] = generador.uniform(-1.0, 1.0, largo_anillo)

    for vuelta in range(1, vueltas):
        inicio = 2 + vuelta * largo_anillo
        anterior = inicio - largo_anillo
        buzon[inicio : inicio + largo_anillo] = (
            primera * buzon[anterior:inicio]
            + segunda * buzon[anterior - 1 : inicio - 1]
            + tercera * buzon[anterior - 2 : inicio - 2]
        )

    return buzon[2 : 2 + total]


def _normalizada_al_pico(onda: np.ndarray, fuerza: float) -> np.ndarray:
    """Escala la onda a pico exactamente `fuerza` y la pasa a float32.

    Se divide en float64 y se multiplica ya en float32 para que el pico sobreviva
    al cambio de precision: la muestra mayor vale 1,0 exacto antes de la conversion.
    """
    normalizada = (onda / np.max(np.abs(onda))).astype(np.float32)
    normalizada *= np.float32(fuerza)
    return normalizada
