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

Lo mismo con el decaimiento. El tiempo que tarda la energia RMS del gemelo en
caer a la mitad, medido sobre esas mismas seis cuerdas, va de **0,405 s** (la
sexta) a **0,768 s** (la primera y la segunda). Una cuerda de verdad bien pulsada
sostiene mas que eso, asi que el factor 2 de la tercera prueba tambien puede
quedarse corto; si lo hace, el numero a mover es el `brillo` del anillo de
Karplus-Strong -que es lo que gobierna el decaimiento- y no el factor.

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
from nucleo.musica import midi_de_nombre

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
FACTOR_DEL_DECAIMIENTO = 2.0


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


def _tiempo_hasta_la_mitad(muestras: np.ndarray, frecuencia_muestreo: int) -> float:
    """Segundos hasta que la energia RMS cae a la mitad de su maximo.

    Se mide por ventanas y no muestra a muestra porque el RMS de una muestra no
    existe; la ventana es la del analisis, que es la escala en la que el detector
    ve la energia. El instante que se devuelve es el CENTRO de la primera ventana
    que baja del umbral: el principio adelantaria la medida media ventana en las
    dos señales y el final la atrasaria.

    Devuelve `inf` si la energia no llega a bajar a la mitad en todo el audio, que
    es un resultado y no un error: una cuerda que no decae en tres segundos tiene
    un decaimiento mayor que lo grabado y la prueba lo dira con ese infinito.
    """
    ventana = GUITARRA.tamano_ventana(frecuencia_muestreo)
    salto = ventana // 4
    energias = [
        (
            (inicio + ventana / 2) / frecuencia_muestreo,
            float(np.sqrt(np.mean(muestras[inicio : inicio + ventana].astype(np.float64) ** 2))),
        )
        for inicio in range(0, len(muestras) - ventana, salto)
    ]
    if not energias:
        return float("inf")
    pico = max(energia for _, energia in energias)
    for instante, energia in energias:
        if energia <= pico / 2.0:
            return instante
    return float("inf")


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

    real = _proporcion_acertada(
        _ventanas(muestras_reales, frecuencia_muestreo), cuerda.nota
    )
    gemelo = _proporcion_acertada(_ventanas(sintetica, frecuencia_muestreo), cuerda.nota)

    assert real > 0.0, (
        f"la grabacion de {archivo} no dio ni una ventana con {cuerda.nota}: "
        "sin un patron contra el que comparar, esta prueba no mide nada"
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

    El tiempo hasta que la energia RMS cae a la mitad tiene que quedar dentro de
    un factor 2 del de la grabacion, por los dos lados: un gemelo que se apague
    demasiado pronto no llega a parecerse a lo que el detector ve en vivo, y uno
    que no se apague nunca es la version timbrica de ser mas facil -tres segundos
    de nota perfectamente legible donde la guitarra da uno-.

    El factor 2 es grueso a proposito: el decaimiento de una cuerda depende de la
    pua, del dedo que la apaga y de la guitarra, asi que una tolerancia fina
    mediria al guitarrista. Lo que esto descarta es el orden de magnitud
    equivocado.

    Medido hoy en el gemelo, para que se sepa de donde sale su mitad: de 0,405 s
    en la sexta a 0,768 s en la primera. Si la prueba salta, lo que hay que mover
    es el `brillo` del anillo de `cuerda_pulsada`, que es lo que gobierna el
    decaimiento, y no este factor.
    """
    muestras_reales, frecuencia_muestreo = _grabacion(archivo)
    sintetica = _gemelo_como(muestras_reales, cuerda.nota, frecuencia_muestreo)

    real = _tiempo_hasta_la_mitad(muestras_reales, frecuencia_muestreo)
    gemelo = _tiempo_hasta_la_mitad(sintetica, frecuencia_muestreo)

    assert np.isfinite(real), (
        f"la energia de {archivo} no cae a la mitad en toda la grabacion: "
        "sin decaimiento medido no hay nada con que comparar"
    )
    assert np.isfinite(gemelo), (
        f"la energia del gemelo de {cuerda.nota} no cae a la mitad en "
        f"{muestras_reales.size / frecuencia_muestreo:.1f} s"
    )
    assert real / FACTOR_DEL_DECAIMIENTO <= gemelo <= real * FACTOR_DEL_DECAIMIENTO, (
        f"el gemelo de {cuerda.nota} cae a la mitad en {gemelo:.3f} s y la "
        f"guitarra en {real:.3f} s, fuera del factor {FACTOR_DEL_DECAIMIENTO:g}"
    )
