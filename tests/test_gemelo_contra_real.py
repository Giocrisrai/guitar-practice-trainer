"""El gemelo contra la guitarra real: las seis cuerdas al aire, cara a cara.

**ESTE ARCHIVO SE SALTA HOY, Y ESO ESTA BIEN.** `tests/audio/` esta vacio salvo
el `.gitkeep` porque el usuario todavia no ha grabado sus seis cuerdas, igual que
pasa con `tests/test_audio_real.py`, y cada prueba se salta con el mensaje que ese
archivo ya usa. El dia que las grabaciones existan, estas tres pruebas empiezan a
correr sin tocar nada.

**LAS TOLERANCIAS SE ESCRIBEN AHORA, DE ANTEMANO, Y ESO ES EL PUNTO DEL ARCHIVO.**
Si se escribieran el dia que existan las grabaciones, se elegirian a conveniencia
de lo que saliera: cualquier numero que dejara las tres verdes pareceria
razonable, y entonces el archivo no mediria nada. Escritas antes, lo que digan es
una prediccion falsable sobre una guitarra que nadie ha grabado todavia. Las tres
pueden salir rojas, y una roja aqui es informacion y no una averia de la suite.

**LA QUE MAS IMPORTA ES `test_el_gemelo_no_es_mas_facil_que_la_guitarra`**, porque
es el riesgo principal de toda la etapa (spec §10): si el sonido del gemelo es mas
limpio que el de una guitarra de verdad, la cadena aprueba con el gemelo y falla
con el cable, y entonces las cuarenta y tantas pruebas que esta etapa ha escrito
dan una seguridad que no existe. El gemelo reduce la sorpresa, no la elimina.

**Y hay motivos medidos para esperar que esa prueba sea la que salte.** Sobre el
audio sintetico de las seis cuerdas (3 s, `cuerda_pulsada` con la semilla 0), el
detector de produccion acierta el **97,1 %** de TODAS las ventanas en las seis, y
el 100 % de las que llegan a dar una nota, con una desviacion mediana de 0,0
cents. `tests/test_audio_real.py` solo le exige a la guitarra de verdad el 80 % de
las ventanas que dan nota. Si la guitarra se queda donde ese 80 % la deja, la
diferencia pasa del margen y esta prueba lo dira. **La respuesta entonces NO es
subir el margen**: es que el gemelo tiene que ensuciarse -trasteo, desafinacion,
mas ruido de pua- hasta que deje de ser mas facil.

**EL DECAIMIENTO NO SE MIDE CON EL TIEMPO HASTA LA MITAD DEL RMS, Y ESO FUE UN
ARREGLO.** La primera version de este archivo lo media asi, y esa medida depende
mas de la semilla del ruido de pua que del timbre: con el MISMO sintetizador, la
misma cuerda y la misma fuerza, la primera cuerda pasa de 0,768 s (semilla 0) a
0,149 s (semilla 1), un factor **5,1**, muy por encima del factor 2 que se le
exigia. La causa es que el RMS total mezcla todos los parciales y el reparto de
energia entre ellos SALE DEL RUIDO INICIAL del anillo, asi que el umbral de la
mitad se cruza donde la semilla diga. Una tolerancia mas fina que el ruido de su
propia metrica no mide el timbre: mide la semilla.

Lo que se mide ahora es **cuantos dB por segundo pierde el FUNDAMENTAL de la
nota** (`_decaimiento_db_s`). La semilla de Karplus-Strong solo fija la amplitud
INICIAL de cada parcial; el ritmo al que ese parcial se apaga lo fija el filtro
del lazo, que es deterministico. Una pendiente en dB/s de UNA componente es un
cociente de amplitudes de esa misma componente, asi que el factor de escala que
la semilla introduce se cancela. Medido sobre ocho semillas (0, 1, 2, 3, 5, 7, 42
y 99) y las seis cuerdas, la dispersion que queda es de **1,005 en el peor caso**
-la sexta; en la cuarta es 1,001 y en las otras cuatro 1,000-, contra el 5,1 de
la medida vieja.

Lo que el gemelo da hoy, y es reproducible semilla a semilla: **-0,015 dB/s en la
sexta (E2), -0,028 (A2), -0,102 (D3), -0,243 (G3), -0,327 (B3) y -1,133 en la
primera (E4)**. En la sexta eso son 0,045 dB en tres segundos: el fundamental del
gemelo practicamente **no decae** en las cuerdas graves, y lo que se oye apagarse
son los parciales. Lo que una cuerda de verdad hace con su fundamental no se
puede saber aqui -no hay grabacion-, pero una cuerda que pierde energia por el
puente decae, asi que lo esperable es que esta prueba salte por el lado de que
**el gemelo sostiene demasiado**, que es la misma direccion que el riesgo de
arriba y lo contrario de lo que decia la version anterior de este docstring (que
razonaba desde los 0,405-0,768 s de la semilla 0, el valor atipico: lo tipico de
la medida vieja era 0,15-0,30 s).

**Y EL ARREGLO NO ES GIRAR EL `brillo`.** Esto estaba escrito tres veces en este
archivo como el consejo a seguir y es falso, que es peor que un docstring falso
cualquiera: es una INSTRUCCION, y el dia que las grabaciones existan alguien va a
girar el parametro, va a ver que no sirve y va a desconfiar de la prueba en vez
del consejo. Barrido del recorrido ENTERO de `brillo`, en dB/s:

    brillo    0,00     0,25     0,50     0,75     1,00    razon
    E2     -0,0114  -0,0132  -0,0149  -0,0146  -0,0121     1,31
    A2     -0,0364  -0,0258  -0,0277  -0,0294  -0,0260     1,41
    D3     -0,1155  -0,1147  -0,1019  -0,0772  -0,0406     2,85
    G3     -0,2746  -0,2730  -0,2429  -0,1845  -0,0977     2,81
    B3     -0,4003  -0,2766  -0,3269  -0,3419  -0,3002     1,45
    E4     -0,9455  -1,1066  -1,1328  -1,0240  -0,7803     1,45

De punta a punta, el parametro mueve E2 un factor 1,31 y lo deja en 0,01 dB/s,
que sigue a dos ordenes de magnitud de los varios dB/s de una cuerda real. **Y la
razon es estructural, no de calibracion**: la atenuacion del promedio de dos
tomas en `f0` va como ω², asi que el decaimiento en dB/s va como **`f0`³** y se
desvanece en las graves con cualquier peso. Comprobado: `dB/s` dividido por `f0`³
se queda entre 2,1 y 3,2e-8 en las seis cuerdas, o sea casi constante a lo largo
de un rango de 4 en `f0` que cambia la pendiente por 76.

Lo que haria falta es **otra familia de arreglo, en la sintesis y no en un
parametro**: una perdida INDEPENDIENTE DE LA FRECUENCIA en el lazo -una ganancia
escalar por vuelta, que da `dB/s` proporcional a `f0` en vez de a `f0`³- o una
envolvente global en `cuerda_pulsada`, que daria los mismos dB/s en las seis.
**Eso no se decide aqui ni ahora**: se decide con las grabaciones delante, no a
ciegas contra una guitarra imaginaria.

**NINGUNA PRUEBA DE ESTE ARCHIVO ABRE EL DISPOSITIVO DE AUDIO.** Lee archivos
`.wav` del disco y sintetiza en memoria; el cable solo hizo falta el dia que se
grabo.
"""

from pathlib import Path

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador
from nucleo.gemelo.cuerda import cuerda_pulsada
from nucleo.musica import midi_a_frecuencia, midi_de_nombre

AUDIO = Path(__file__).parent / "audio"
GUITARRA = PERFILES["guitarra_estandar"]

# Las seis cuerdas con el nombre de archivo que `herramientas/grabar_muestras.py`
# escribe, DERIVADO del perfil y no copiado a mano: el nombre lo construye esa
# herramienta con la misma expresion, asi que una afinacion distinta o una cuerda
# renombrada no deja aqui una tabla que mienta. `test_audio_real.py` si la lleva a
# mano, y es lo que habria que unificar el dia que alguien toque las dos.
CUERDAS = tuple(
    (f"cuerda_{cuerda.numero}_{cuerda.nota.lower()}.wav", cuerda)
    for cuerda in GUITARRA.cuerdas
)

# La semilla del ruido de la pulsacion sintetica. Fija para que la comparacion sea
# la misma cada vez: lo que se compara es la guitarra contra UN gemelo concreto, y
# un gemelo que cambiara de ruido en cada ejecucion convertiria un fallo en una
# anecdota.
SEMILLA = 0

# Cuanto se le permite al gemelo ser MAS FACIL que la guitarra, en proporcion de
# ventanas acertadas. Diez puntos es holgado a proposito: lo que esta prueba
# persigue no es una diferencia fina sino la grande, la que invalidaria la etapa.
# Que el gemelo sea mas DIFICIL no se limita: un gemelo mas duro que el cable no
# aprueba nada que el cable suspenda, y esa direccion no es el riesgo.
MARGEN_DE_FACILIDAD = 0.10

# Dentro de que factor tiene que caer el decaimiento del gemelo respecto del de la
# guitarra. Un factor 2 no es una medicion fina: es la diferencia entre «decae
# como una cuerda» y «decae como otra cosa». El decaimiento importa porque de el
# depende cuantas ventanas siguen teniendo nota que leer, o sea la mitad de la
# prueba de arriba.
#
# El factor se queda en 2 y lo que se arreglo fue la METRICA (ver la cabecera del
# modulo): la medida vieja -el tiempo hasta la mitad del RMS- tenia un ruido de
# semilla de 5,1, o sea mas que su propia tolerancia, y entonces el 2 no decidia
# nada. Con la pendiente del fundamental el ruido de semilla es 1,005 y el factor
# 2 deja casi todo su margen para el timbre, que es lo que tiene que juzgar.
#
# Y si el factor salta en las graves, lo que NO lo arregla es girar el `brillo`:
# el decaimiento del lazo va como `f0`³ y en las graves se desvanece con
# cualquier peso. El barrido y la familia de arreglo que si valdria estan en la
# cabecera del modulo.
FACTOR_DEL_DECAIMIENTO = 2.0

# Los tres numeros de la medida del decaimiento, y por que son estos:
#
# - se empieza en 0,10 s para dejar fuera el ATAQUE, donde la amplitud del
#   fundamental todavia esta subiendo y la pendiente no significa nada;
# - cada punto se mide sobre 0,20 s, que son unos 16 periodos del E2 (el mas
#   grave): bastante para que la amplitud de la componente este bien estimada y
#   poco para que la pendiente no se promedie consigo misma;
# - y los puntos se toman cada 0,05 s, o sea solapados, para que una nota de tres
#   segundos de una ventanas de sobra al ajuste.
COMIENZO_DE_LA_MEDIDA_S = 0.10
LARGO_DE_LA_MEDIDA_S = 0.20
PASO_DE_LA_MEDIDA_S = 0.05

# Hasta donde por debajo del maximo se sigue creyendo la medida. Por debajo de
# 40 dB de su propio maximo, lo que queda del fundamental de una GRABACION es
# ruido de fondo, y los puntos de ahi abajo doblan el ajuste hacia la horizontal.
# No afecta al gemelo -que no baja tanto- y es lo que hace que la medida valga
# igual para una grabacion real.
PISO_DE_LA_MEDIDA_DB = 40.0

# Lo menos que hace falta para ajustar una recta a algo. Con el paso y el largo de
# arriba, ocho puntos son 0,55 s de nota por encima del piso.
PUNTOS_MINIMOS_DE_LA_MEDIDA = 8

# Lo menos que una grabacion tiene que acertar para servir de patron, en VENTANAS
# y no en proporcion. Una ventana suelta puede ser casualidad -un armonico, un
# golpe-; diez no. Se pone en absoluto y bajo a proposito: una guitarra que
# acierte poco es justo lo que la prueba de la facilidad tiene que poder ver, asi
# que este guardia solo descarta la grabacion INSERVIBLE (muda, con la guitarra
# desafinada media octava, grabada sin cable), no la dificil.
VENTANAS_ACERTADAS_MINIMAS = 10


def _grabacion(nombre: str) -> tuple[np.ndarray, int]:
    """Las muestras de la grabacion real, o se salta la prueba si no existe.

    El mensaje es EL MISMO que usa `tests/test_audio_real.py`, literalmente, para
    que quien vea un salto en la suite encuentre siempre la misma frase y la misma
    orden que lo arregla.
    """
    ruta = AUDIO / nombre
    if not ruta.exists():
        pytest.skip(f"Falta {nombre}: ejecuta herramientas/grabar_muestras.py")
    muestras, frecuencia_muestreo = soundfile.read(ruta, dtype="float32")
    return muestras, frecuencia_muestreo


def _gemelo_como(muestras_reales: np.ndarray, nota: str, frecuencia_muestreo: int):
    """La cuerda sintetica que se compara con esa grabacion, igualada a ella.

    Se igualan las TRES cosas que no son el sonido y que falsearian la
    comparacion si se dejaran al azar:

    - la duracion, para que las dos tengan el mismo numero de ventanas;
    - la frecuencia de muestreo, de la que sale el tamaño de la ventana;
    - el pico, porque el detector tiene umbral de ruido y una grabacion mas
      flojita que el gemelo perderia ventanas por volumen y no por timbre. El
      gemelo se sintetiza con el pico de la grabacion, no al reves: la guitarra
      es el patron.

    Lo que NO se iguala es el timbre, que es justo lo que se esta comparando.
    """
    pico = float(np.max(np.abs(muestras_reales)))
    return cuerda_pulsada(
        midi_de_nombre(nota),
        duracion_s=muestras_reales.size / frecuencia_muestreo,
        frecuencia_muestreo=frecuencia_muestreo,
        # `cuerda_pulsada` exige un pico en (0, 1]. Una grabacion muda no se
        # puede igualar, y el suelo deja que la prueba siga y falle por lo que
        # mide en vez de lanzar desde el montaje.
        fuerza=min(1.0, max(0.01, pico)),
        semilla=SEMILLA,
    )


def _ventanas(muestras: np.ndarray, frecuencia_muestreo: int) -> list:
    """Recorre el audio en ventanas solapadas con el analizador de produccion.

    Mismo recorrido que `test_audio_real.py` -ventana del perfil, salto de un
    cuarto- pero **se devuelven TODAS las ventanas, tambien las que no dan nota**.
    Esa es la diferencia que hace que la prueba de la facilidad mida algo: una
    ventana en la que el detector no reconoce nada no es una ventana acertada, y
    contar solo las que ya traen nota esconde exactamente la ventaja que el gemelo
    podria tener (sostener la nota durante tres segundos enteros cuando la
    guitarra de verdad se apaga antes).
    """
    analizador = Analizador(GUITARRA, frecuencia_muestreo=frecuencia_muestreo)
    ventana = GUITARRA.tamano_ventana(frecuencia_muestreo)
    salto = ventana // 4
    return [
        analizador.procesar(muestras[inicio : inicio + ventana])
        for inicio in range(0, len(muestras) - ventana, salto)
    ]


def _proporcion_acertada(resultados: list, nota: str) -> float:
    """Que fraccion de TODAS las ventanas leyo la nota que de verdad sonaba."""
    if not resultados:
        return 0.0
    return sum(1 for r in resultados if r.nota == nota) / len(resultados)


def _nota_dominante(resultados: list) -> str | None:
    """La nota que mas ventanas leyeron, mirando solo las que dieron alguna."""
    notas = [r.nota for r in resultados if r.estado == "nota" and r.nota is not None]
    if not notas:
        return None
    return max(set(notas), key=notas.count)


def _amplitud_del_fundamental(
    muestras: np.ndarray, f0: float, desde_s: float, frecuencia_muestreo: int
) -> float:
    """Amplitud de la componente de `f0` en el tramo que empieza en `desde_s`.

    Es un solo punto de la transformada -el producto de la señal por la
    exponencial compleja de `f0`, con una ventana de Hann para que las frecuencias
    vecinas no se cuelen por los lobulos laterales-, y no una FFT entera: lo que
    interesa es esa frecuencia y no el espectro.

    Se mide a la frecuencia TEORICA de la nota al aire y no a la que el detector
    diga: la cuerda del usuario puede estar unos cents corrida, y 0,20 s de
    ventana son unos 5 Hz de resolucion, asi que unos cents no mueven la medida.
    Lo que si la moveria es un error de medio tono, y eso ya lo caza la primera
    prueba del archivo antes de llegar aqui.
    """
    desde = int(desde_s * frecuencia_muestreo)
    largo = int(LARGO_DE_LA_MEDIDA_S * frecuencia_muestreo)
    tramo = muestras[desde : desde + largo].astype(np.float64)
    if tramo.size < largo:
        return 0.0
    ventana = np.hanning(tramo.size)
    giro = np.exp(-2j * np.pi * f0 * np.arange(tramo.size) / frecuencia_muestreo)
    return float(np.abs(np.sum(tramo * ventana * giro)) / np.sum(ventana) * 2.0)


def _decaimiento_db_s(muestras: np.ndarray, frecuencia_muestreo: int, nota: str) -> float:
    """Cuantos dB por segundo pierde el FUNDAMENTAL de `nota`. Negativo decae.

    **Por que el fundamental y no la energia total.** Lo primero que este archivo
    midio fue el tiempo hasta que el RMS cae a la mitad, y esa medida depende de
    la semilla del ruido de pua mas que del timbre: factor 5,1 entre dos semillas
    del MISMO sintetizador, contra el factor 2 que la prueba exige. El RMS total
    suma todos los parciales, y cuanta energia le toca a cada uno lo decide el
    ruido inicial del anillo.

    Una pendiente en dB/s de una sola componente es un cociente de amplitudes de
    ESA componente, asi que la escala que la semilla introduce se cancela y lo que
    queda es el filtro del lazo, que es deterministico. Medido sobre ocho semillas
    y las seis cuerdas: dispersion de 1,005 en el peor caso.

    El ajuste es por minimos cuadrados sobre `20*log10(amplitud)` contra el
    tiempo, saltando el ataque y tirando los puntos que caen mas de
    `PISO_DE_LA_MEDIDA_DB` por debajo del maximo (en una grabacion, eso ya es
    ruido de fondo y doblaria la recta hacia la horizontal).

    **EL PISO ESTA REFERIDO AL MAXIMO MEDIDO Y NO AL RUIDO, y eso es un limite
    declarado de esta medida.** El bin de `f0` no baja de donde el suelo de ruido
    de la grabacion lo deje, asi que con una relacion señal-ruido modesta -menos
    de esos 40 dB- el piso NO se activa, los puntos del final se quedan pegados al
    ruido y la pendiente sale **subestimada**, hacia la horizontal. Y eso es el
    mismo sesgo que esta prueba vigila entrando por otra puerta: una grabacion con
    poco margen de ruido parece decaer MENOS de lo que decae, o sea mas parecida
    al gemelo que lo que es. El otro limite de la misma familia -el batido de las
    dos polarizaciones de una cuerda real, que ondula la envolvente del
    fundamental y que el ajuste lineal promedia- esta en el informe de la tarea.
    Los dos solo se pueden medir con grabaciones delante.

    Devuelve `nan` si no quedan puntos suficientes, que es un resultado y no un
    error: significa que esta señal no tiene fundamental medible, y la prueba lo
    dice con su propio mensaje.
    """
    f0 = midi_a_frecuencia(midi_de_nombre(nota))
    duracion_s = muestras.size / frecuencia_muestreo
    instantes, decibelios = [], []
    desde_s = COMIENZO_DE_LA_MEDIDA_S
    while desde_s + LARGO_DE_LA_MEDIDA_S <= duracion_s:
        amplitud = _amplitud_del_fundamental(muestras, f0, desde_s, frecuencia_muestreo)
        if amplitud > 0.0:
            instantes.append(desde_s + LARGO_DE_LA_MEDIDA_S / 2.0)
            decibelios.append(20.0 * np.log10(amplitud))
        desde_s += PASO_DE_LA_MEDIDA_S

    if len(instantes) < PUNTOS_MINIMOS_DE_LA_MEDIDA:
        return float("nan")
    instantes, decibelios = np.array(instantes), np.array(decibelios)
    sobre_el_piso = decibelios >= decibelios.max() - PISO_DE_LA_MEDIDA_DB
    instantes, decibelios = instantes[sobre_el_piso], decibelios[sobre_el_piso]
    if instantes.size < PUNTOS_MINIMOS_DE_LA_MEDIDA:
        return float("nan")
    return float(np.polyfit(instantes, decibelios, 1)[0])


@pytest.mark.parametrize("archivo, cuerda", CUERDAS, ids=[c.nota for _, c in CUERDAS])
def test_el_detector_le_da_la_misma_nota_al_gemelo_y_a_la_guitarra(archivo, cuerda):
    """Lo minimo: el detector no confunde de nota a la cuerda sintetica.

    Es la primera de las tres y la que puede fallar por la razon mas tonta -una
    octava, un armonico tomado por fundamental-, asi que va sola: si esta falla,
    las otras dos no dicen nada.

    Se comprueba que las dos dan la MISMA nota dominante y que esa nota es la que
    la cuerda tiene al aire. Lo segundo hace falta: dos señales que coincidieran
    en una nota equivocada -las dos una octava arriba, por ejemplo- pasarian una
    prueba escrita solo como «la misma».
    """
    muestras_reales, frecuencia_muestreo = _grabacion(archivo)
    sintetica = _gemelo_como(muestras_reales, cuerda.nota, frecuencia_muestreo)

    real = _nota_dominante(_ventanas(muestras_reales, frecuencia_muestreo))
    gemelo = _nota_dominante(_ventanas(sintetica, frecuencia_muestreo))

    assert real == cuerda.nota, f"la grabacion de {archivo} suena a {real}"
    assert gemelo == cuerda.nota, f"el gemelo de {cuerda.nota} suena a {gemelo}"
    assert gemelo == real


@pytest.mark.parametrize("archivo, cuerda", CUERDAS, ids=[c.nota for _, c in CUERDAS])
def test_el_gemelo_no_es_mas_facil_que_la_guitarra(archivo, cuerda):
    """**LA PRUEBA QUE IMPORTA: el riesgo principal de la etapa (spec §10).**

    Si el gemelo es mas facil que la guitarra, todo lo que la cadena apruebe con
    el gemelo puede fallar con el cable, y las pruebas de la etapa dan una
    seguridad que no existe. Por eso la direccion de la desigualdad no es
    simetrica: que el gemelo acierte MENOS que la guitarra no se limita -un gemelo
    mas duro no aprueba nada que el cable suspenda- y que acierte mas de diez
    puntos por encima si.

    La proporcion es sobre TODAS las ventanas analizadas y no solo sobre las que
    dan nota (ver `_ventanas`): la ventaja que se busca es precisamente la de
    sostener la nota legible mas tiempo del que la sostiene una cuerda de verdad.

    Las dos señales se comparan con la misma duracion, la misma frecuencia de
    muestreo y el mismo pico (ver `_gemelo_como`), asi que lo que quede de
    diferencia es del timbre.

    **Si esta prueba se pone roja, la respuesta no es subir `MARGEN_DE_FACILIDAD`**:
    es ensuciar el gemelo -trasteo, desafinacion, mas ruido de pua- hasta que deje
    de ser mas facil, y volver a medir. El margen esta escrito antes de existir
    las grabaciones justamente para que nadie pueda elegirlo despues.
    """
    muestras_reales, frecuencia_muestreo = _grabacion(archivo)
    sintetica = _gemelo_como(muestras_reales, cuerda.nota, frecuencia_muestreo)

    ventanas_reales = _ventanas(muestras_reales, frecuencia_muestreo)
    real = _proporcion_acertada(ventanas_reales, cuerda.nota)
    gemelo = _proporcion_acertada(_ventanas(sintetica, frecuencia_muestreo), cuerda.nota)

    # El guardia es en VENTANAS y no en proporcion, y es bajo a proposito (ver
    # `VENTANAS_ACERTADAS_MINIMAS`): una guitarra que acierte poco es justo el
    # hallazgo que esta prueba busca, asi que esto solo descarta la grabacion
    # inservible. `real > 0.0` no era un suelo: una ventana suelta de 137 lo
    # cumplia.
    acertadas = sum(1 for r in ventanas_reales if r.nota == cuerda.nota)
    assert acertadas >= VENTANAS_ACERTADAS_MINIMAS, (
        f"la grabacion de {archivo} solo dio {acertadas} ventanas con "
        f"{cuerda.nota} de {len(ventanas_reales)}: no sirve de patron. Vuelve a "
        "grabarla con herramientas/grabar_muestras.py"
    )
    assert gemelo - real <= MARGEN_DE_FACILIDAD, (
        f"el gemelo de {cuerda.nota} acierta el {gemelo:.1%} de las ventanas y la "
        f"guitarra el {real:.1%}: {gemelo - real:.1%} mas facil, por encima del "
        f"{MARGEN_DE_FACILIDAD:.0%} que se le permite. El gemelo tiene que "
        "ensuciarse, no el margen subir"
    )


@pytest.mark.parametrize("archivo, cuerda", CUERDAS, ids=[c.nota for _, c in CUERDAS])
def test_el_decaimiento_es_del_mismo_orden(archivo, cuerda):
    """Que la cuerda sintetica se apague como una cuerda, no como otra cosa.

    Lo que se compara son los **dB por segundo que pierde el fundamental**, y
    tiene que quedar dentro de un factor 2 del de la grabacion por los dos lados:
    un gemelo que se apague demasiado pronto no llega a parecerse a lo que el
    detector ve en vivo, y uno que no se apague nunca es la version timbrica de
    ser mas facil -tres segundos de nota perfectamente legible donde la guitarra
    da uno-.

    **La metrica se cambio porque la primera era mas ruidosa que su tolerancia.**
    Media el tiempo hasta la mitad del RMS, y eso depende de la semilla del ruido
    de pua: factor 5,1 entre dos semillas del mismo sintetizador. La pendiente del
    fundamental tiene 1,005 de dispersion sobre ocho semillas. El por que esta en
    `_decaimiento_db_s` y en la cabecera del modulo.

    El factor 2 es grueso a proposito: el decaimiento de una cuerda depende de la
    pua, del dedo que la apaga y de la guitarra, asi que una tolerancia fina
    mediria al guitarrista. Lo que esto descarta es el orden de magnitud
    equivocado. Y ahora casi todo ese margen es para el timbre, porque el ruido de
    la medida ya no se lo come.

    Medido hoy en el gemelo, reproducible semilla a semilla: **-0,015 dB/s (E2),
    -0,028 (A2), -0,102 (D3), -0,243 (G3), -0,327 (B3), -1,133 (E4)**. En la sexta
    son 0,045 dB en tres segundos, o sea que **el fundamental del gemelo casi no
    decae en las graves**: lo esperable es que esto salte por ahi.

    **Y SI SALTA AHI, NO SE ARREGLA GIRANDO EL `brillo`.** El decaimiento del lazo
    va como `f0`³ -la atenuacion del promedio de dos tomas en `f0` va como ω²-, asi
    que en las graves se desvanece con cualquier peso: el recorrido entero del
    parametro mueve E2 un factor 1,31 y lo deja en 0,01 dB/s, a dos ordenes de
    magnitud de una cuerda real. La tabla del barrido y la familia de arreglo que
    si valdria -una perdida independiente de la frecuencia en el lazo, o una
    envolvente global en `cuerda_pulsada`: un cambio de la SINTESIS, no un giro de
    parametro- estan en la cabecera del modulo. Lo que no hay que mover es este
    factor.

    **Y SE SABE EXACTAMENTE LO QUE DISCRIMINA**, medido con guitarras de mentira
    iguales al gemelo mas un decaimiento extra uniforme:

        extra      -0,1    -0,3    -1,0    -3,0  dB/s
        cuerdas       2       4       5       6  de 6 fallan

    O sea: es monotono, fino y **anidado** -las cuerdas caen en orden, E2, A2, D3,
    G3, B3, E4, que es el orden de `f0`³-. Y en las graves es **casi de un solo
    lado**, porque el factor 2 sobre -0,015 dB/s son 0,015 dB/s de margen
    absoluto: cualquier cuerda real que decaiga de verdad hace saltar E2 y A2. Eso
    **no es ruido de la medida** -la medida tiene 1,005 de dispersion- sino el
    hallazgo: el gemelo sostiene su fundamental mas que una cuerda. Si sale rojo
    ahi, no se busque un defecto en la prueba.
    """
    muestras_reales, frecuencia_muestreo = _grabacion(archivo)
    sintetica = _gemelo_como(muestras_reales, cuerda.nota, frecuencia_muestreo)

    real = _decaimiento_db_s(muestras_reales, frecuencia_muestreo, cuerda.nota)
    gemelo = _decaimiento_db_s(sintetica, frecuencia_muestreo, cuerda.nota)

    assert np.isfinite(real), (
        f"{archivo} no tiene fundamental medible: sin decaimiento no hay nada con "
        "que comparar"
    )
    assert np.isfinite(gemelo), (
        f"el gemelo de {cuerda.nota} no tiene fundamental medible en "
        f"{muestras_reales.size / frecuencia_muestreo:.1f} s"
    )
    # El signo va aparte y antes del factor: los dos tienen que DECAER. Una
    # grabacion cuyo fundamental suba -porque la nota entra tarde, o porque lo
    # que se midio es ruido- daria una pendiente positiva, y el factor sobre dos
    # numeros de signos distintos no significa nada.
    assert real < 0.0, f"el fundamental de {archivo} no decae: {real:+.3f} dB/s"
    assert gemelo < 0.0, (
        f"el fundamental del gemelo de {cuerda.nota} no decae: {gemelo:+.3f} dB/s"
    )
    assert (
        abs(real) / FACTOR_DEL_DECAIMIENTO
        <= abs(gemelo)
        <= abs(real) * FACTOR_DEL_DECAIMIENTO
    ), (
        f"el fundamental del gemelo de {cuerda.nota} decae {gemelo:.3f} dB/s y el "
        f"de la guitarra {real:.3f} dB/s, fuera del factor "
        f"{FACTOR_DEL_DECAIMIENTO:g}. Lo que se mueve es el `brillo` del anillo, "
        "no el factor"
    )
