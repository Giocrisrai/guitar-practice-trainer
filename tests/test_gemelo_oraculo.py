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

**Y YA NO HAY NINGUNA DESACTUALIZADA.** `SUELO_DESFASE_MS` estuvo valiendo
+130 ms -lo medido antes del arreglo del camino A de la Task 6c- mientras el eje
del cabezal estaba por decidir, para no inscribir dos veces un numero
provisional. La Task 6d lo decidio: la cadena alinea el cabezal con el final del
silencio de cabecera del gemelo. Remedido con esa cadena, el suelo es **+152,3 ms
de mediana y +188,3 de maximo**, y aqui estan inscritos los dos. El retraso de
publicacion NO cambio con la alineacion, porque los dos ejes se movieron juntos y
la distancia entre ellos es lo que este suelo mide: lo que lo movio fue el arreglo
del detector. **Eso vale para cinco de las seis configuraciones medidas, no para
las seis**: la que lleva cuenta atras se movio 2,0 ms (+94,0/+169,0 pasaron a
+96,0/+171,0), porque el cabezal solo se suelta de la cuenta atras en un cuadro y
el instante exacto en que deberia soltarse cae dentro de uno.

**EL SIGNO ES PARTE DEL DATO.** Los desfases medidos son todos POSITIVOS: la
cadena reporta las notas mas TARDE de lo que sonaron, porque tarda en publicar un
ataque (~20 ms de deteccion mas ~165 de estabilizacion). Eso es latencia real y
tiene que aparecer en el suelo, no desaparecer en un valor absoluto; por eso las
pruebas comprueban ademas que el desfase es positivo. El dia que salga negativo,
una asercion en valor absoluto lo dejaria pasar y seria exactamente el defecto que
nadie veria.

**UNA PRUEBA DE ESTE ARCHIVO ESTA EN `xfail(strict=True)`, y no es una tolerancia
relajada.** Va en `strict` para que el dia que deje de fallar la suite se ponga
ROJA y haya que venir aqui a quitar la marca: un `xfail` no estricto la dejaria
desaparecer en silencio. Su numero esperado es el correcto y no se toca -8 notas
limpias de 8-.

- `..._las_cuenta_todas_como_limpias`: defecto medido que sigue abierto, pero ya
  no es el mismo. Era «la cabecera tecnica (128 ms) mas el temblor del onset» y
  sacaba 0 limpias de 8; la Task 6d se llevo la cabecera y ahora salen **7 de 8**.
  Lo que queda es solo el temblor del detector de ataques: la nota 3 se firma
  89,3 ms despues de su ataque exacto y la ventana de acierto son 80 ms. Su
  docstring lo descompone.

Las dos que SI se arreglaron y ya no llevan marca:

- `..._sigue_limpio_con_otra_semilla`: era el hallazgo gordo de la Task 6b y la
  Task 6c lo cerro en `nucleo/ejercicios/pulsaciones.py`.
- `..._la_mediana_del_desfase_sigue_en_el_suelo_inscrito`: estaba esperando a que
  el eje del cabezal se decidiera. Decidido en la Task 6d, el numero se remidio y
  se inscribio una sola vez.
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

# La mediana del desfase que la cadena introduce, MEDIDA sobre la escala entera al
# tempo escrito con el cabezal ya alineado (Task 6d): +152,3 ms. Redondeada hacia
# arriba.
#
# Es el numero DEFINITIVO de la etapa, y por eso se inscribio aqui y no antes: el
# suelo se movio dos veces -el arreglo del camino A del detector (Task 6c) lo
# subio de +129,8 a +152,3, y la alineacion del cabezal (Task 6d) no lo movio-, y
# reinscribirlo en cada pasada habria sido publicar numeros provisionales con cara
# de definitivos. Si se queda corto, la respuesta no es subirlo: es mirar por que
# la cadena cambio.
SUELO_DESFASE_MS = 153.0

# El peor desfase de esa misma pasada, MEDIDO: +188,3 ms, y sigue siendo +188,3
# tras el arreglo del camino A y tras la alineacion del cabezal: el maximo no se
# ha movido ni un milisegundo en toda la etapa. No es la mediana con
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

# Los dos tramos MEDIDOS en la Task 6d, con su mediana y su maximo en ms:
# `(primer_compas, ultimo_compas, factor_tempo, mediana, maximo)`.
#
# Existen porque eran las dos configuraciones de la etapa que no tenian prueba de
# ningun tipo: sus numeros vivian en un informe. Un numero medido que no esta
# afirmado en ninguna parte no es un suelo, es una anecdota, y estos dos son los
# que dicen que la traduccion del eje tambien vale cuando el cabezal NO arranca en
# cero -el tramo 2-2 empieza en 2,4 s de pieza-, que es el caso normal en cuanto
# se practica por secciones.
TRAMOS_MEDIDOS = (
    (2, 2, 1.0, 138.8, 167.3),
    (2, 2, 0.5, 164.3, 185.3),
)

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
    factor_tempo: float = 1.0,
    semilla: int = 0,
    primer_compas: int = 1,
    ultimo_compas: int | None = None,
) -> tuple[Veredicto, RegistroDeLaCadena, InformeDePasada]:
    """La pasada entera del oraculo SIN BUCLE, y las tres cosas que deja.

    Las tres se devuelven juntas porque las tres pruebas del brief miran la misma
    pasada desde sitios distintos -el veredicto del gemelo, los reportes crudos y
    el informe que la cadena firma- y montar la pasada tres veces seria tardar el
    triple en medir lo mismo.

    `en_bucle` se queda en False (el defecto del bucle es de la T7) y
    `compases_de_cuenta_atras` en 0: la cuenta atras del plan y la del gemelo
    tienen que ser la misma -es la condicion de uso que el veredicto declara- y la
    forma mas corta de que lo sean es que no haya ninguna. La configuracion CON
    cuenta atras tiene su propia prueba, que pasa por la cadena igual que esta, en
    `tests/test_gemelo_veredicto.py`.

    El tramo va al PLAN y a la interpretacion a la vez, con los mismos compases:
    si se separaran, los dos relojes se separarian con ellos y el veredicto no
    tiene como saberlo.

    `al_cambiar_repeticion=None` NO es un detalle: ese aviso existe para que el
    servidor rearranque el metronomo, y el metronomo abre audio. Una suite que lo
    pasara abriria un dispositivo de sonido en cada prueba.
    """
    pieza = escala_de_ocho_notas()
    interpretacion = interpretar(
        pieza,
        PERFECTO,
        factor_tempo=factor_tempo,
        semilla=semilla,
        primer_compas=primer_compas,
        ultimo_compas=ultimo_compas,
    )
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(
            factor_tempo=factor_tempo,
            en_bucle=False,
            compases_de_cuenta_atras=0,
            primer_compas=primer_compas,
            ultimo_compas=ultimo_compas,
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
        "DEFECTO MEDIDO, no una tolerancia: al tempo escrito salen 7 notas limpias "
        "de 8, no 8. La que falta es la nota 3, que el detector de ataques firma "
        "89,3 ms despues de su ataque exacto contra una ventana de acierto de "
        "80 ms. Eran 0 de 8 hasta la Task 6d, que alineo el cabezal con el final "
        "de la cabecera tecnica del gemelo y se llevo los 128 ms sistematicos; lo "
        "que queda es SOLO el temblor del onset. Arreglarlo no es de esta tarea y "
        "no se arregla bajando el 8 ni subiendo la ventana de acierto: la pregunta "
        "que plantea -si la clasificacion debe cobrarle al alumno la latencia que "
        "el detector sabe que añade- es de diseño."
    ),
)
def test_el_oraculo_sin_bucle_las_cuenta_todas_como_limpias():
    """Las ocho notas acertadas Y a tiempo. **ROJA por UNA nota, y es un hallazgo.**

    El numero esperado es 8 y se queda en 8: si la cadena le dice a un interprete
    PERFECTO que no toca a tiempo, el defecto es de la cadena y bajar el 8 solo
    serviria para dejar de verlo.

    **Eran 0 limpias de 8 y ahora son 7.** Lo que habia eran DOS cosas sumadas, y
    la Task 6d se llevo la primera:

    1. *La cabecera tecnica, 128 ms, sistematica.* El gemelo mete un silencio
       delante de la primera nota para que la primera ventana de analisis llegue
       completa, y el cabezal corria durante el: el guitarrista perfecto tocaba
       128 ms tarde POR CONSTRUCCION y el seguidor tenia razon en quejarse. Los
       desfases firmados eran
       `+148,3 +136,3 +166,3 +217,3 +163,3 +193,3 +139,3 +148,3` ms contra una
       ventana de 80, o sea las ocho «tarde». Hoy la cadena alinea el cabezal con
       el final de esa cabecera y los desfases son
       `+20,3 +8,3 +38,3 +89,3 +35,3 +65,3 +11,3 +20,3`: los mismos menos 128.
    2. *El temblor del onset, hasta 89,3 ms, por nota.* Es lo que queda, y es lo
       que deja esta prueba roja: la **nota 3** se firma 89,3 ms despues de su
       ataque exacto y se pasa de los 80 ms de `VENTANA_A_TIEMPO_S` por 9,3 ms.
       Las otras siete entran.

    Ese residuo es la latencia propia del detector de ataques sobre un ataque
    perfecto, y **no se arregla aqui ni tocando la ventana de acierto**. Plantea
    una pregunta de diseño que no es de esta tarea: si la clasificacion debe
    cobrarle al alumno la latencia que el detector sabe que añade. Mientras no se
    responda, esta prueba se queda roja con el 8 escrito, que es la unica forma de
    que la pregunta no se pierda.

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
    # LA COTA POR ABAJO, que es la mitad que faltaba. Un suelo afirmado solo como
    # techo no es un suelo: con `> 0.0` como unico limite inferior, una cadena que
    # dejara de retrasar -o un error de eje que se comiera el retraso- pasaba esta
    # prueba sin tocarla. Medido: el mutante que multiplica la mediana por 0,01
    # (1,5 ms) pasaba el archivo entero.
    assert abs(veredicto.desfase_maximo_ms) >= SUELO_MAXIMO_MS - MARGEN_MS
    # Y EL MAXIMO NO ES LA MEDIANA CON OTRO NOMBRE: son dos cantidades distintas y
    # el maximo esta 36 ms por encima (188,3 contra 152,3). El otro mutante que
    # sobrevivia era precisamente devolver la mediana como maximo.
    assert veredicto.desfase_maximo_ms > veredicto.desfase_introducido_ms


def test_la_mediana_del_desfase_sigue_en_el_suelo_inscrito():
    """La quinta afirmacion del suelo: el numero, ya inscrito. **Verde desde la
    Task 6d.**

    Estuvo en `xfail(strict=True)` esperando a que el eje del cabezal se
    decidiera, con +130 ms inscritos -lo medido antes del arreglo del camino A- y
    con la razon escrita: el suelo iba a moverse otra vez y reinscribirlo dos
    veces habria sido tirar la primera medida.

    El eje se decidio en la Task 6d y el numero se remidio con esa cadena:
    **+152,3 ms**, que es lo que `SUELO_DESFASE_MS` dice ahora. La subida respecto
    de los +129,8 originales es toda del arreglo del camino A y la razon es buena:
    antes algunas notas resolvian pronto CON LA ALTURA EQUIVOCADA y ahora todas
    esperan a que la racha cuaje, con lo que la dispersion sobre 30 semillas se
    estrecha de 43,5 a 34,5 ms. La alineacion del cabezal no lo movio: mueve los
    dos ejes a la vez, asi que la distancia entre ellos -que es lo que esto mide-
    no cambia.

    Sigue aislada en su propia prueba, con UNA sola asercion, porque asi fue como
    se pudo dejar en `xfail` sin que las otras cuatro afirmaciones del suelo
    dejaran de vigilar.
    """
    veredicto, _, _ = _pasada_del_oraculo()

    assert abs(veredicto.desfase_introducido_ms) <= SUELO_DESFASE_MS + MARGEN_MS
    assert abs(veredicto.desfase_introducido_ms) >= SUELO_DESFASE_MS - MARGEN_MS


def test_el_oraculo_aguanta_el_tempo_minimo():
    """El tempo minimo del plan (40 % del escrito), que es el caso peor del suelo.

    Es el caso peor y no una repeticion del anterior: al 40 % el tramo dura dos
    veces y media mas, el cabezal recorre mas segundos por cada ataque y el
    desfase que la cadena introduce SUBE. Medido: mediana +164,3 ms y maximo
    +206,3 ms, contra +152,3 y +188,3 al tempo escrito. Sigue por debajo del techo
    del detector, con 44 ms de holgura, que es la menor de todas las
    configuraciones medidas.

    Y aqui las ocho notas si salen limpias, porque la ventana de acierto se estira
    con el factor (80 ms / 0,40 = 200 ms) y se come de sobra el temblor del onset
    -que al 40 % llega a 65,3 ms-. Es la contraprueba de que lo que deja la prueba
    de arriba en 7 de 8 es ese temblor contra una ventana de 80 ms, y no que el
    seguidor cuente mal.
    """
    veredicto, _, informe = _pasada_del_oraculo(factor_tempo=0.40)

    assert veredicto.notas_tocadas == NOTAS
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.limpio is True

    assert veredicto.desfase_introducido_ms > 0.0
    assert abs(veredicto.desfase_introducido_ms) == pytest.approx(
        SUELO_DESFASE_AL_TEMPO_MINIMO_MS, abs=MARGEN_MS
    )
    assert abs(veredicto.desfase_maximo_ms) == pytest.approx(
        SUELO_MAXIMO_AL_TEMPO_MINIMO_MS, abs=MARGEN_MS
    )
    assert abs(veredicto.desfase_maximo_ms) < TECHO_DEL_DETECTOR_MS
    assert veredicto.desfase_maximo_ms > veredicto.desfase_introducido_ms

    assert _suma(informe, "acertadas") == NOTAS
    assert _suma(informe, "limpias") == NOTAS


@pytest.mark.parametrize(
    ("primer_compas", "ultimo_compas", "factor_tempo", "mediana_ms", "maximo_ms"),
    TRAMOS_MEDIDOS,
    ids=("tramo 2-2", "tramo 2-2 al 50%"),
)
def test_el_oraculo_de_un_tramo_que_no_empieza_en_el_compas_uno(
    primer_compas, ultimo_compas, factor_tempo, mediana_ms, maximo_ms
):
    """El oraculo de un tramo suelto, con su suelo MEDIDO e inscrito.

    Es el caso normal en cuanto se practica por secciones, y no un borde: el
    cabezal de una pasada que estudia el compas 2 no arranca en cero sino en el
    instante escrito de ese compas (2,4 s), asi que aqui se ejercita la traduccion
    del eje en el unico sitio donde puede salir mal por una cantidad que no se
    parece a nada.

    Los dos numeros se afirman con su margen por los dos lados, no contra el techo
    del detector: contra el techo quedaban 80 ms de holgura, que es suficiente para
    tragarse un error de eje de 128 ms sin que nada se queje. Y se afirma que el
    maximo esta por encima de la mediana, porque son dos cantidades distintas.

    Las CUATRO notas salen limpias, no siete de ocho como la pieza entera, y es
    por una razon que conviene saber: la nota con el temblor gordo del onset
    -89,3 ms, la nota 3- esta en el primer compas y este tramo no la toca.
    """
    veredicto, _, informe = _pasada_del_oraculo(
        factor_tempo=factor_tempo,
        primer_compas=primer_compas,
        ultimo_compas=ultimo_compas,
    )

    assert veredicto.notas_tocadas == 4
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.excluidas == ()
    assert veredicto.limpio is True

    assert veredicto.desfase_introducido_ms == pytest.approx(mediana_ms, abs=MARGEN_MS)
    assert veredicto.desfase_maximo_ms == pytest.approx(maximo_ms, abs=MARGEN_MS)
    assert veredicto.desfase_maximo_ms > veredicto.desfase_introducido_ms
    assert veredicto.desfase_maximo_ms < TECHO_DEL_DETECTOR_MS

    assert _suma(informe, "notas_medibles") == 4
    assert _suma(informe, "acertadas") == 4
    assert _suma(informe, "limpias") == 4


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
