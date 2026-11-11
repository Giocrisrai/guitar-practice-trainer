"""La pieza de fondo convertida en muestras, de forma determinista.

Funcion pura: ni hilos, ni dispositivo, ni reloj. Entran las voces que el usuario
NO esta tocando (`nucleo.piezas.voces_de_fondo`) y sale un buffer mono con el mapa
para indexarlo desde el cabezal del carril. Quien lo hace sonar es otro modulo; a
este solo se le pide que la misma pieza al mismo tempo salga **identica**, porque
es lo unico que permite que una prueba afirme sobre muestras.

**Es un modulo nuevo y no un refactor de `interprete._generar`**, aunque los dos
sumen `cuerda_pulsada` sobre un buffer de ceros. Difieren en tres decisiones:

1. **Los acordes se SUMAN.** El interprete reduce un acorde a su nota mas grave
   porque simula a un guitarrista al que va a juzgar un detector de tono
   monofonico. Aqui no se simula a nadie: la limitacion era del detector, no del
   sintetizador, y un fondo sin acordes no es un fondo.
2. **Se normaliza UNA vez, sobre la mezcla entera.** El interprete recorta a
   [-1, 1] nota por nota ya sumada. Si aqui se normalizara nota a nota, una nota
   sola sonaria igual de fuerte que un acorde de seis.
3. **El eje es la pieza entera desde su pulso cero.** El interprete mide un tramo
   con su silencio de cabecera, porque lo suyo es una *pasada*. A esto lo indexa
   el cabezal, que ya sabe en que pulso va.

Lo que si se reutiliza, y no se copia, es la guarda del minimo:
`cuerda.duracion_minima_s`, que vive al lado de la funcion que impone la
restriccion y la importan los dos.

**El tempo entra por parametro y no sale de `FondoDisponible`.** El tempo de un
archivo puede no ser el de la `Pieza` que el usuario toca -en MusicXML sale de la
obra entera y en una tablatura de texto es un 90 por omision-, y el fondo que se
renderizara con un tempo distinto del que mueve el cabezal derivaria por
construccion. Manda el de la `Pieza`, y lo pasa quien llama.
"""

from dataclasses import dataclass

import numpy as np

from nucleo.gemelo.cuerda import cuerda_pulsada, duracion_minima_s
from nucleo.piezas.voces_de_fondo import VozDeFondo

# Cuanto se deja sonar cada nota, en figuras escritas. Pasa de 1 por lo mismo que
# `interprete.COLA_DE_SUSTAIN`: una cuerda que nadie apaga no se calla en la barra
# de compas, y un fondo cortado en seco a cada figura suena a maquina de escribir.
# La cola se mide en FIGURAS y no en segundos para que `factor_tempo` escale el eje
# entero por igual: con una cola constante en segundos, practicar al 50 % no
# doblaria la duracion de la pieza, la doblaria casi.
COLA_DE_LA_FIGURA = 1.3

# Tope de memoria, dicho en voz alta. Doce minutos a 48 kHz son 34,56 millones de
# muestras. Sin este tope, una cancion larga al 25 % de tempo reserva cientos de
# megas y el proceso muere sin decir por que.
#
# **El buffer y el pico de renderizarlo no son el mismo numero**, y conviene no
# confundirlos: el buffer que se devuelve son 138 MB (float32), pero al final del
# render conviven la mezcla en float64 -276 MB, porque sumar un acorde en float32
# iria perdiendo bits- y el float32 que sale de ella. Medido con `getrusage` en el
# tope exacto: **449,6 MB de pico**, de los que 34,7 son el interprete y numpy.
# Antes de normalizar en sitio eran 708,7 MB, porque `np.abs(mezcla)` y
# `mezcla / pico` copiaban la mezcla entera una vez cada uno; ver `_normalizada`.
# Si alguien sube este tope, el pico sube con el a razon de 0,58 MB por segundo de
# audio a 48 kHz (12 bytes por muestra entre los dos buffers), y es el pico -no el
# buffer- lo que decide si el proceso muere.
MUESTRAS_MAXIMAS = 48000 * 60 * 12

# Cuanto separa la semilla de una nota de la de la siguiente. La semilla por nota
# se DERIVA de la base y del indice -y no es la base a secas- para que dos notas
# de la misma altura y la misma figura no salgan bit a bit iguales: un acorde de
# octavas con la misma semilla suena a una sola cuerda con el volumen doblado, y
# no a dos cuerdas. Un primo grande para que dos piezas renderizadas con semillas
# base vecinas no compartan ni una nota.
PASO_DE_SEMILLA = 7919


@dataclass(frozen=True)
class PiezaRenderizada:
    """Las muestras de la pieza de fondo y el mapa para indexarlas por pulsos.

    muestras: mono float32, ya normalizada y con la ganancia aplicada.
    pulsos_por_segundo: el tempo EFECTIVO (tempo x factor) partido por 60. Es el
        mapa: un instante en pulsos se convierte en muestra dividiendo por el.
    duracion_s: lo que dura la pieza entera, colas incluidas.
    """

    muestras: np.ndarray
    frecuencia_muestreo: int
    pulsos_por_segundo: float
    duracion_s: float

    def rodaja(self, instante_pulsos: float, cuantas: int) -> np.ndarray:
        """Las `cuantas` muestras que suenan en ese instante de la pieza.

        Devuelve silencio -no lanza y no recorta el bloque- antes del comienzo y
        despues del final: el cabezal vive en la PASADA, que incluye cuenta atras
        (pulsos negativos) y puede quedarse parada mas alla del final de la pieza.
        Quien la llama escribe en una tarjeta de sonido y necesita SIEMPRE el
        bloque completo; un bloque corto seria un chasquido.
        """
        if cuantas <= 0:
            return np.zeros(0, dtype=np.float32)
        bloque = np.zeros(cuantas, dtype=np.float32)
        desde = _muestra_del_pulso(
            instante_pulsos, self.pulsos_por_segundo, self.frecuencia_muestreo
        )
        # Los dos bordes se recortan contra la pieza y el hueco se queda en
        # silencio: `desde` negativo es la cuenta atras y `desde` mas alla del
        # final es una pasada parada despues de la ultima nota.
        inicio = max(0, desde)
        fin = min(self.muestras.size, desde + cuantas)
        if fin > inicio:
            bloque[inicio - desde : fin - desde] = self.muestras[inicio:fin]
        return bloque


def renderizar(
    voces: tuple[VozDeFondo, ...],
    tempo: int,
    factor_tempo: float = 1.0,
    frecuencia_muestreo: int = 48000,
    ganancia: float = 1.0,
    semilla: int | None = 0,
) -> PiezaRenderizada:
    """Sintetiza las voces de fondo enteras, desde su pulso cero.

    Parametros:
        voces: las pistas que el usuario no esta tocando. Sin voces, o con voces
            sin notas, devuelve un buffer vacio de duracion 0: nadie tiene que
            preguntar antes de llamar.
        tempo: el de la `Pieza` que el usuario toca, en negras por minuto. NO el de
            `FondoDisponible`, que es informativo (ver el docstring del modulo).
        factor_tempo: 0,5 es practicar a la mitad de velocidad. Estira el eje y la
            duracion de cada nota; **no toca la afinacion**, porque se vuelve a
            sintetizar en vez de remuestrear.
        frecuencia_muestreo: muestras por segundo.
        ganancia: multiplica la mezcla ya normalizada, asi que fija el pico.
        semilla: con un entero la pieza sale identica muestra a muestra cada vez,
            que es el punto de este modulo. Con `None` cada render es distinto.

    Lanza `ValueError` si el tempo o el factor no son positivos, y si la pieza al
    factor pedido pasa de `MUESTRAS_MAXIMAS`, ANTES de reservar el buffer.
    """
    if tempo <= 0:
        raise ValueError(f"El tempo {tempo} no sirve: tiene que ser mayor que cero")
    if factor_tempo <= 0:
        raise ValueError(
            f"El factor de tempo {factor_tempo} no sirve: tiene que ser mayor que cero"
        )

    pulsos_por_segundo = tempo * factor_tempo / 60.0
    planeadas = _planear(voces, pulsos_por_segundo, frecuencia_muestreo)
    if not planeadas:
        return PiezaRenderizada(
            muestras=np.zeros(0, dtype=np.float32),
            frecuencia_muestreo=frecuencia_muestreo,
            pulsos_por_segundo=pulsos_por_segundo,
            duracion_s=0.0,
        )

    duracion_s = max(
        inicio_pulsos / pulsos_por_segundo + duracion
        for _, inicio_pulsos, duracion in planeadas
    )
    total = int(round(duracion_s * frecuencia_muestreo))
    _comprobar_el_tope(total, frecuencia_muestreo)

    # La mezcla se suma en float64 y se pasa a float32 al final: un acorde de seis
    # notas se sale de la escala antes de normalizar, y sumarlo en float32 iria
    # perdiendo bits de las ultimas notas contra las primeras.
    mezcla = np.zeros(total, dtype=np.float64)
    for indice, (midi, inicio_pulsos, duracion) in enumerate(planeadas):
        onda = cuerda_pulsada(
            midi=midi,
            duracion_s=duracion,
            frecuencia_muestreo=frecuencia_muestreo,
            semilla=None if semilla is None else semilla + PASO_DE_SEMILLA * (indice + 1),
        )
        # Aqui esta la decision 1 del modulo: se SUMA. Dos notas en el mismo
        # instante son un acorde, no una nota con dos nombres.
        _sumar_en_su_sitio(
            mezcla,
            onda,
            _muestra_del_pulso(inicio_pulsos, pulsos_por_segundo, frecuencia_muestreo),
        )

    return PiezaRenderizada(
        muestras=_normalizada(mezcla, ganancia),
        frecuencia_muestreo=frecuencia_muestreo,
        pulsos_por_segundo=pulsos_por_segundo,
        duracion_s=duracion_s,
    )


def _muestra_del_pulso(
    instante_pulsos: float, pulsos_por_segundo: float, frecuencia_muestreo: int
) -> int:
    """El indice de muestra de un instante en pulsos. El mapa, en una linea.

    La usan `renderizar` para colocar cada nota y `rodaja` para leerla, y es LA
    MISMA a proposito: con dos cuentas distintas -una al escribir y otra al leer-
    el fondo iria desplazado medio bloque y nadie sabria de cual de las dos.
    """
    return int(round(instante_pulsos / pulsos_por_segundo * frecuencia_muestreo))


def _planear(
    voces: tuple[VozDeFondo, ...], pulsos_por_segundo: float, frecuencia_muestreo: int
) -> list[tuple[float, float, float]]:
    """(midi, inicio en pulsos, duracion en segundos) de cada nota, en orden.

    El orden -voz a voz, nota a nota, como vienen del archivo- es parte del
    contrato: de el sale el indice que deriva la semilla, asi que reordenar las
    notas cambiaria el audio.

    La duracion es la figura escrita al tempo efectivo por `COLA_DE_LA_FIGURA`,
    acotada por abajo con `duracion_minima_s`. La cota no es un detalle: sin ella
    `cuerda_pulsada` LANZA para una figura mas corta que un periodo de su altura,
    y entonces una cancion entera no suena por una nota de un milisegundo.
    """
    planeadas: list[tuple[float, float, float]] = []
    for voz in voces:
        for nota in voz.notas:
            figura_s = COLA_DE_LA_FIGURA * nota.duracion_pulsos / pulsos_por_segundo
            duracion = max(figura_s, duracion_minima_s(nota.midi, frecuencia_muestreo))
            planeadas.append((nota.midi, nota.inicio_pulsos, duracion))
    return planeadas


def _comprobar_el_tope(total: int, frecuencia_muestreo: int) -> None:
    """Falla limpio y DICIENDOLO si la pieza no cabe, antes de reservar nada."""
    if total <= MUESTRAS_MAXIMAS:
        return
    minutos = total / frecuencia_muestreo / 60.0
    tope_en_minutos = MUESTRAS_MAXIMAS / frecuencia_muestreo / 60.0
    raise ValueError(
        f"La pieza de fondo ocuparia {minutos:.1f} minutos de audio "
        f"({total} muestras) y el tope son {tope_en_minutos:.1f} minutos "
        f"({MUESTRAS_MAXIMAS} muestras): sube el factor de tempo o toca un tramo "
        "mas corto."
    )


def _sumar_en_su_sitio(destino: np.ndarray, onda: np.ndarray, desde: int) -> None:
    """Suma `onda` sobre `destino` a partir de `desde`, recortando lo que no cabe.

    Una rodaja de numpy y no un bucle por muestra. `desde` puede ser negativo -una
    rodaja que empieza antes de la pieza- o caer fuera por la derecha, y las dos
    cosas son normales: la cola de la ultima nota sobresale del eje y el cabezal
    pide bloques antes del pulso cero.
    """
    if desde >= destino.size or desde + onda.size <= 0:
        return
    recorte = max(0, -desde)
    inicio = desde + recorte
    cuantas = min(onda.size - recorte, destino.size - inicio)
    destino[inicio : inicio + cuantas] += onda[recorte : recorte + cuantas]


def _normalizada(mezcla: np.ndarray, ganancia: float) -> np.ndarray:
    """Escala la mezcla ENTERA al pico 1,0 una sola vez y aplica la ganancia.

    **Consume `mezcla`**: la divide en sitio, asi que quien la llama no puede
    volver a usarla. Lo hace porque la mezcla de una pieza al tope de este modulo
    pesa 276 MB y copiarla para dividirla es doblar el pico de memoria por nada.

    Aqui esta la decision 2 del modulo. Normalizar nota a nota -lo que hace
    `cuerda_pulsada` con su parametro `fuerza`- igualaria el pico de una nota sola
    al de un acorde de seis, y entonces el fondo no tendria dinamica ninguna: una
    melodia a una voz sonaria tan gorda como el tutti.

    Un pico de cero -imposible con una nota dentro, porque `cuerda_pulsada`
    devuelve pico `fuerza`- se deja pasar sin dividir por cero.

    **Las dos cuentas estan escritas para no copiar la mezcla.** `np.abs(mezcla)`
    reservaria una mezcla entera mas en float64 y `mezcla / pico` otra, y en una
    pieza al tope del modulo eso son 552 MB de temporales que nadie necesita: el
    pico sale de los dos extremos, que no copian nada, y la division va en sitio
    sobre una mezcla que es local y recien hecha. El resultado es bit a bit el
    mismo -son las mismas operaciones IEEE sobre los mismos numeros- y esta
    comprobado con `np.array_equal` sobre cinco piezas, acorde incluido.
    """
    pico = max(abs(float(mezcla.max())), abs(float(mezcla.min()))) if mezcla.size else 0.0
    if pico > 0.0:
        mezcla /= pico
    muestras = mezcla.astype(np.float32)
    muestras *= np.float32(ganancia)
    return muestras
