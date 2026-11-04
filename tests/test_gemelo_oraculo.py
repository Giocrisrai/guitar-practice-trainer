"""El oraculo sin bucle: una interpretacion PERFECTA atravesando la cadena entera.

Esta es la prueba que la etapa existe para poder escribir: el guitarrista
sintetico toca sin un solo error, el audio entra por la ruta de produccion -el
`Analizador` de verdad, el `ConductorDeEstudio` de verdad, la `SesionDeEstudio`
de verdad- y al otro lado se comprueba que no se perdio nada. Sin bucle a
proposito: el bucle tiene un defecto conocido que arregla la T7 y no es lo que
aqui se mide.

**TODAS las constantes de este archivo estan MEDIDAS, no elegidas.** Salen de una
sonda sobre `escala_de_ocho_notas()` con `PERFECTO`, la semilla por omision y el
salto de produccion, y van redondeadas hacia arriba al milisegundo. Si alguna se
queda corta, la respuesta no es subirla: es mirar por que la cadena cambio.

**Y UNA DE ELLAS ESTA DESACTUALIZADA A PROPOSITO: `SUELO_DESFASE_MS`.** Sigue
valiendo lo medido ANTES del arreglo del camino A de la Task 6c (+129,8 ms),
cuando lo que hoy se mide son +152,3 ms. No es un descuido ni una medicion que se
quedo corta: es un numero que se va a mover otra vez en la tarea siguiente -la
que alinea el reloj de la pieza con el final del silencio de cabecera del
gemelo-, y reinscribirlo dos veces seria tirar la primera medida. La unica
asercion que lo usa esta aislada en
`test_la_mediana_del_desfase_sigue_en_el_suelo_inscrito`, en `xfail(strict=True)`
y con la razon escrita. Las demas constantes estan al dia, `SUELO_MAXIMO_MS`
incluida: el maximo no se movio con el arreglo.

**EL SIGNO ES PARTE DEL DATO.** Los desfases medidos son todos POSITIVOS: la
cadena reporta las notas mas TARDE de lo que sonaron, porque tarda en publicar un
ataque (~20 ms de deteccion mas ~165 de estabilizacion). Eso es latencia real y
tiene que aparecer en el suelo, no desaparecer en un valor absoluto; por eso las
pruebas comprueban ademas que el desfase es positivo. El dia que salga negativo,
una asercion en valor absoluto lo dejaria pasar y seria exactamente el defecto que
nadie veria.

**DOS PRUEBAS DE ESTE ARCHIVO ESTAN EN `xfail(strict=True)` y no es una tolerancia
relajada**, pero ya no son las mismas dos que al escribir el archivo. Van en
`strict` para que el dia que dejen de fallar la suite se ponga ROJA y haya que
venir aqui a quitar la marca: un `xfail` no estricto las dejaria desaparecer en
silencio.

Los numeros ESPERADOS de esas pruebas son los correctos y no se tocan -8 notas
limpias de 8-. Lo que si esta desactualizado, y dicho arriba, es la constante
`SUELO_DESFASE_MS` contra la que compara la segunda.

- `..._las_cuenta_todas_como_limpias`: defecto medido que sigue abierto, la
  cabecera tecnica sin descontar en el eje del cabezal (128 ms) mas el temblor
  del onset. Su docstring lo descompone.
- `..._la_mediana_del_desfase_sigue_en_el_suelo_inscrito`: NO es un defecto,
  es una medicion **pendiente de
  remedir**. El arreglo del camino A de la Task 6c movio la mediana del suelo y
  la tarea siguiente la va a mover otra vez; el numero se reinscribe una sola
  vez, cuando el eje del cabezal este decidido. Su razon de `xfail` lo explica.

La que SI se arreglo y ya no lleva marca es
`..._sigue_limpio_con_otra_semilla`: era el hallazgo gordo de la Task 6b y la
Task 6c lo cerro en `nucleo/ejercicios/pulsaciones.py`.
"""

import pytest

from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.gemelo.cadena import RegistroDeLaCadena, pasar_por_la_cadena
from nucleo.gemelo.interprete import interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.gemelo.veredicto import Veredicto, juzgar
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import InformeDePasada, PlanDePasada, SesionDeEstudio

# Las notas de `escala_de_ocho_notas()`: ocho, una por pulso, ninguna repetida y
# ningun acorde, asi que las ocho son medibles y ninguna se excluye.
NOTAS = 8

# La mediana del desfase que la cadena introduce, MEDIDA: +129,8 ms sobre la
# escala entera al tempo escrito. Redondeada hacia arriba.
#
# **ES LA MEDIDA DE ANTES DEL ARREGLO DEL CAMINO A (Task 6c), y sigue aqui a
# proposito: hoy la mediana es +152,3 ms.** Ver la cabecera del archivo y la
# razon del `xfail` de `test_la_mediana_del_desfase_sigue_en_el_suelo_inscrito`,
# que es la unica asercion que la usa. No subirla sin remedir: el numero se mueve
# otra vez en cuanto se decida el eje del cabezal.
SUELO_DESFASE_MS = 130.0

# El peor desfase de esa misma pasada, MEDIDO: +188,3 ms, y sigue siendo +188,3
# tras el arreglo del camino A: el maximo no se movio ni un milisegundo, asi que
# esta constante esta AL DIA. No es la mediana con
# otro nombre: es el que decide si la cadena se acerca al techo del detector, y
# por eso tiene su propio suelo.
SUELO_MAXIMO_MS = 189.0

# Lo mismo al tempo minimo (`factor_tempo=0,40`), MEDIDO: mediana +164,3 ms y
# maximo +206,3 ms. Son MAS ALTOS que al tempo escrito y tienen que ir aparte:
# reutilizar el suelo del tempo escrito con un margen mas gordo habria escondido
# que el tempo lento retrasa a la cadena, que es justo lo que el tempo minimo
# existe para medir.
SUELO_DESFASE_AL_TEMPO_MINIMO_MS = 165.0
SUELO_MAXIMO_AL_TEMPO_MINIMO_MS = 207.0

# Lo que se le concede a una medicion antes de llamarla otra cosa. 15 ms es
# menos de un cuadro de analisis (21 ms), o sea que ni un cuadro de deriva pasa
# desapercibido.
MARGEN_MS = 15.0

# El techo del propio detector: lo mas viejo que un ataque puede ser para que la
# cadena todavia pueda estar hablando de el. El suelo medido tiene que quedar por
# DEBAJO, y esa es la afirmacion central de la etapa: la cadena introduce retraso,
# pero no tanto como para dejar de reconocer la nota que lo causo.
TECHO_DEL_DETECTOR_MS = VENTANA_ATAQUE_COMO_ONSET_S * 1000.0


def _pasada_del_oraculo(
    factor_tempo: float = 1.0, semilla: int = 0
) -> tuple[Veredicto, RegistroDeLaCadena, InformeDePasada]:
    """La pasada entera del oraculo SIN BUCLE, y las tres cosas que deja.

    Las tres se devuelven juntas porque las tres pruebas del brief miran la misma
    pasada desde sitios distintos -el veredicto del gemelo, los reportes crudos y
    el informe que la cadena firma- y montar la pasada tres veces seria tardar el
    triple en medir lo mismo.

    `en_bucle` se queda en False (el defecto del bucle es de la T7) y
    `compases_de_cuenta_atras` en 0: la cuenta atras del plan y la del gemelo
    tienen que ser la misma -es la condicion de uso que el veredicto declara- y la
    forma mas corta de que lo sean es que no haya ninguna.

    `al_cambiar_repeticion=None` NO es un detalle: ese aviso existe para que el
    servidor rearranque el metronomo, y el metronomo abre audio. Una suite que lo
    pasara abriria un dispositivo de sonido en cada prueba.
    """
    pieza = escala_de_ocho_notas()
    interpretacion = interpretar(
        pieza, PERFECTO, factor_tempo=factor_tempo, semilla=semilla
    )
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(
            factor_tempo=factor_tempo, en_bucle=False, compases_de_cuenta_atras=0
        ),
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)

    registro = pasar_por_la_cadena(interpretacion, conductor)
    veredicto = juzgar(interpretacion, registro)

    # El informe de la VUELTA CERRADA, no `estudio.informe`. Los dos traen los
    # mismos contadores, pero el de la sesion sale de esta pasada con
    # `repeticiones=2` -la mirada final de la cadena cierra la vuelta y el
    # contador de la sesion ya va por la siguiente-, y `proporcion_limpia` divide
    # por ese numero: con el informe de la sesion, ocho notas limpias de ocho
    # salian 0,5. Medido. Lo que esta pasada cerro es UNA vuelta.
    assert len(registro.vueltas) == 1, (
        "una pasada sin bucle cierra exactamente una vuelta; "
        f"esta cerro {len(registro.vueltas)}"
    )
    return veredicto, registro, registro.vueltas[-1]


def _suma(informe: InformeDePasada, contador: str) -> int:
    """Un contador del informe sumado sobre los compases del tramo."""
    return sum(getattr(compas, contador) for compas in informe.compases)


def test_el_oraculo_sin_bucle_no_pierde_ninguna_nota():
    """Lo minimo que una cadena tiene que cumplir: vio todo lo que paso y nada mas.

    Medido: cero perdidas, cero inventadas, cero mal adjudicadas y cero
    exclusiones sobre las ocho notas. Las exclusiones se afirman en cero porque
    esta pieza no tiene acordes ni notas repetidas: si apareciera una, seria una
    nota que el veredicto dejo de juzgar, y una perdida escondida detras de una
    exclusion es el peor fallo posible de este modulo.
    """
    veredicto, _, _ = _pasada_del_oraculo()

    assert veredicto.notas_tocadas == NOTAS
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.excluidas == ()
    assert veredicto.limpio is True


def test_el_oraculo_sin_bucle_acierta_todas_las_notas_del_informe():
    """Las ocho notas llegan al informe de la cadena con la altura correcta.

    Es otra cosa que la prueba de arriba y por eso existe: el veredicto empareja
    por puesto y compara alturas POR SU CUENTA, mientras que `acertadas` es lo que
    el seguidor de produccion decidio. Que las dos mitades digan ocho es lo que
    descarta que una de las dos se este equivocando a favor.

    Medido: 8 medibles y 8 acertadas.
    """
    _, _, informe = _pasada_del_oraculo()

    assert _suma(informe, "notas_escritas") == NOTAS
    assert _suma(informe, "notas_medibles") == NOTAS
    assert _suma(informe, "acertadas") == NOTAS


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DEFECTO MEDIDO, no una tolerancia: la cadena clasifica las OCHO notas de "
        "una interpretacion perfecta como 'tarde' al tempo escrito, asi que salen "
        "0 limpias de 8. Ver el docstring de la prueba para la descomposicion."
    ),
)
def test_el_oraculo_sin_bucle_las_cuenta_todas_como_limpias():
    """Las ocho notas acertadas Y a tiempo. **ROJA, y es un hallazgo.**

    El numero esperado es 8 y se queda en 8: si la cadena le dice a un interprete
    PERFECTO que no toca a tiempo, el defecto es de la cadena y bajar el 8 solo
    serviria para dejar de verlo.

    Medido al tempo escrito: `limpias=0`, `a_tiempo=0`, `pronto=0`, `tarde=8`. Los
    desfases que la cadena firma nota a nota, en ms:

        +148,3  +136,3  +166,3  +217,3  +163,3  +193,3  +139,3  +148,3

    y `VENTANA_A_TIEMPO_S` son 80 ms al tempo escrito, asi que las ocho se pasan.
    La descomposicion de la primera, que es la que explica el resto:

        +148,3 ms = 128,0 de CABECERA TECNICA + 20,3 de deteccion

    Los 128 ms son `VENTANAS_DE_CABECERA` (1,5 ventanas de analisis), el silencio
    que el gemelo mete delante de la primera nota y que es OBLIGATORIO: sin el, el
    primer cuadro que llega a la cadena ya trae el ataque, el reloj de la pieza se
    ancla ahi y todo lo que sigue se lee adelantado. Pero nadie lo descuenta en el
    eje del CABEZAL: la cadena hace `fijar_la_mirada(0.0)` en la muestra cero, asi
    que el cabezal ya marca 128 ms cuando suena una nota que la pieza escribe en
    0,0. Visto desde el seguidor, el gemelo toca 128 ms tarde **por
    construccion**, y el seguidor tiene razon en decirlo.

    Que esto no se arregla aqui esta medido tambien: descontando los 128 ms a
    mano, los desfases quedan en +20,3 +8,3 +38,3 +89,3 +35,3 +65,3 +11,3 +20,3,
    y **la nota 3 sigue fuera de la ventana de 80 ms**. O sea que son DOS cosas y
    no una: la cabecera sin descontar (128 ms, sistematica) y el temblor del onset
    del detector (hasta 89 ms sobre un ataque exacto), que es del orden de la
    propia ventana de acierto. Arreglar solo la primera dejaria 7 de 8.

    Lo que SI pasa, y esta probado abajo, es el tempo minimo: la ventana de
    acierto se estira con el factor (80 ms / 0,40 = 200 ms) y ahi las ocho notas
    salen limpias.
    """
    _, _, informe = _pasada_del_oraculo()

    assert _suma(informe, "limpias") == NOTAS


def test_el_desfase_que_introduce_la_cadena_habla_tarde_y_cabe_en_el_techo():
    """El suelo, la parte que NO depende del numero inscrito. **Verde, y tiene
    que seguir verde**: es la que delata un defecto de verdad.

    Son las cuatro afirmaciones del suelo que el arreglo del camino A de la Task
    6c dejo intactas, y estan aqui -separadas de la quinta, la de la mediana-
    porque `xfail(strict=True)` solo exige que una prueba FALLE, no que falle por
    el motivo declarado. Con las cinco juntas bajo un `xfail`, un desfase
    NEGATIVO o un maximo que cruzara el techo del detector dejaban la prueba
    igual de roja y la suite igual de verde: justo el defecto que nadie veria.

    El signo se afirma aparte y antes del valor absoluto: positivo es «la cadena
    habla tarde», que es la latencia real del detector. Negativo seria que la
    cadena reporta ataques ANTES de que suenen, que es imposible y por tanto un
    defecto; una asercion escrita solo en valor absoluto lo dejaria pasar. Era
    exactamente el sintoma del defecto de la Task 6b, que firmaba desfases de
    -460,7 ms.

    Medido tras el arreglo: mediana +152,3 ms y maximo +188,3 ms. El maximo no se
    movio ni un milisegundo respecto de antes, asi que su suelo inscrito sigue
    valiendo y se afirma aqui; la mediana subio y su asercion se fue a la prueba
    de abajo.
    """
    veredicto, _, _ = _pasada_del_oraculo()

    assert veredicto.desfase_introducido_ms > 0.0
    assert veredicto.desfase_maximo_ms > 0.0
    assert abs(veredicto.desfase_maximo_ms) <= SUELO_MAXIMO_MS + MARGEN_MS
    assert abs(veredicto.desfase_maximo_ms) < TECHO_DEL_DETECTOR_MS


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PENDIENTE DE REMEDIR, no una tolerancia relajada ni un defecto: el "
        "arreglo del camino A (Task 6c) subio la mediana del suelo de +129,8 a "
        "+152,3 ms, por encima de SUELO_DESFASE_MS + MARGEN_MS (145). El numero "
        "NO se reinscribe aqui porque la tarea siguiente alinea el reloj de la "
        "pieza con el final del silencio de cabecera del gemelo, lo que mueve el "
        "suelo OTRA VEZ y por mas (los 128 ms de cabecera que hoy nadie "
        "descuenta). Inscribir +152,3 ahora seria publicar un numero provisional "
        "con cara de definitivo y tirarlo en la pasada siguiente. Se remide y se "
        "reinscribe cuando el eje del cabezal este decidido; entonces esta marca "
        "se cae sola y hay que venir a quitarla. ESTA PRUEBA LLEVA UNA SOLA "
        "ASERCION a proposito: las otras cuatro del suelo viven en "
        "test_el_desfase_que_introduce_la_cadena_habla_tarde_y_cabe_en_el_techo "
        "y siguen vigilando, porque un xfail no distingue por que se falla."
    ),
)
def test_la_mediana_del_desfase_sigue_en_el_suelo_inscrito():
    """La quinta afirmacion del suelo, la unica que el arreglo movio.

    `SUELO_DESFASE_MS` sigue siendo +130 ms, que es lo medido ANTES del arreglo
    del camino A. Hoy la mediana es +152,3 ms y la razon es buena: antes algunas
    notas resolvian pronto CON LA ALTURA EQUIVOCADA y ahora todas esperan a que
    la racha cuaje. La dispersion sobre 30 semillas se estrecha de 43,5 a
    34,5 ms con el arreglo puesto, asi que la cadena es mas previsible, no menos.

    No se reinscribe el numero aqui: ver la razon del `xfail`.
    """
    veredicto, _, _ = _pasada_del_oraculo()

    assert abs(veredicto.desfase_introducido_ms) <= SUELO_DESFASE_MS + MARGEN_MS


def test_el_oraculo_aguanta_el_tempo_minimo():
    """El tempo minimo del plan (40 % del escrito), que es el caso peor del suelo.

    Es el caso peor y no una repeticion del anterior: al 40 % el tramo dura dos
    veces y media mas, el cabezal recorre mas segundos por cada ataque y el
    desfase que la cadena introduce SUBE. Medido: mediana +164,3 ms y maximo
    +206,3 ms, contra +129,8 y +188,3 al tempo escrito. Sigue por debajo del techo
    del detector, con 44 ms de holgura, que es la menor de todas las
    configuraciones medidas.

    Y aqui las ocho notas si salen limpias, porque la ventana de acierto se estira
    con el factor (80 ms / 0,40 = 200 ms) y se come los 128 de cabecera. Es la
    contraprueba de que el defecto de arriba es la cabecera y el temblor del
    onset, y no que el seguidor cuente mal.
    """
    veredicto, _, informe = _pasada_del_oraculo(factor_tempo=0.40)

    assert veredicto.notas_tocadas == NOTAS
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.limpio is True

    assert veredicto.desfase_introducido_ms > 0.0
    assert (
        abs(veredicto.desfase_introducido_ms)
        <= SUELO_DESFASE_AL_TEMPO_MINIMO_MS + MARGEN_MS
    )
    assert (
        abs(veredicto.desfase_maximo_ms) <= SUELO_MAXIMO_AL_TEMPO_MINIMO_MS + MARGEN_MS
    )
    assert abs(veredicto.desfase_maximo_ms) < TECHO_DEL_DETECTOR_MS

    assert _suma(informe, "acertadas") == NOTAS
    assert _suma(informe, "limpias") == NOTAS


@pytest.mark.parametrize("semilla", (3, 9))
def test_el_oraculo_sin_bucle_sigue_limpio_con_otra_semilla(semilla):
    """El oraculo sale limpio SIEMPRE, no solo con la semilla por omision.

    `PERFECTO` tiene a cero todas sus desviaciones -ni desfase, ni temblor, ni
    fallos, ni trasteo, ni desafinacion, ni variacion de fuerza-, asi que la
    semilla no cambia NADA de lo que se toca: los `instante_s` y los `midi` de
    los ocho eventos son identicos con cualquier semilla (comprobado sobre 30).
    Lo que si cambia es el audio, porque la sintesis de la cuerda saca de la
    misma semilla el ruido de la pulsacion. Si ese ruido bastara para que la
    cadena perdiera notas, el defecto seria de la cadena.

    **ESTA PRUEBA ESTUVO EN `xfail(strict=True)` Y SE ARREGLO EN LA TASK 6c.**
    Lo que media: 5 de 30 semillas (3, 9, 11, 27 y 29) daban un veredicto SUCIO,
    siempre con la misma forma -una nota adjudicada con la altura de la ANTERIOR
    y, a partir de ahi, la cola del tramo perdida con sus reportes contados como
    inventados-, y con la semilla 3 la cadena firmaba desfases de -343,7 y
    -460,7 ms: medio segundo ANTES de que el ataque existiera.

        semilla  3: perdidas (1,6) (1,7), inventadas 2, mal adjudicada (1,5,62)
        semilla  9: perdidas (1,4)..(1,7), inventadas 4, mal adjudicada (1,3,59)

    La causa estaba en el camino A de `DetectorPulsaciones`, que sellaba el
    ataque con la nota de UN cuadro suelto cuando el suavizador del pipeline
    todavia publicaba la altura de la nota anterior. Hoy el camino A exige racha
    estable y el barrido sale 0 de 30. El diagnostico completo esta en
    `.superpowers/sdd/2026-11-02-gemelo-digital/task-6b-diagnostico.md`.

    **Las dos semillas son las dos FORMAS del defecto, no una repetida**: la 3
    falla en la nota 5 con un cuadro de adelanto (-21 ms de margen) y pierde dos
    notas; la 9 falla en la nota 3 con DOS cuadros (-42 ms) y pierde cuatro. Es
    el caso peor medido del barrido, asi que es el que hay que tener clavado.
    Son dos pasadas de nueve segundos de audio en tiempo virtual, no un barrido
    de treinta: la suite no se entera.

    Esto NO es el defecto del bucle de la T7: aqui `en_bucle` es False y la
    vuelta es la primera.
    """
    veredicto, _, _ = _pasada_del_oraculo(semilla=semilla)

    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.limpio is True
