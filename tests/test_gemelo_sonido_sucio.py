"""El sonido sucio del gemelo: el trasteo, el solape y la desafinacion.

**ESTE ARCHIVO NO ARREGLA NADA.** Deja medidos y nombrados dos comportamientos de
la cadena que la spec §10 declara conocidos, y uno de ellos es un DEFECTO que
sigue abierto a proposito: las notas que se solapan le hacen firmar al detector
ataques que nadie toco. Arreglarlo es cambiar `DetectorPulsaciones`, que es el
corazon de las etapas 2a y 3a, y eso merece su propia decision. Lo que aqui se
hace es que el defecto deje de ser una frase de un informe y pase a ser un numero
que la suite vigila.

`test_las_notas_que_se_solapan_generan_ataques_fantasma` y
`test_el_detector_firma_mas_ataques_que_notas_cuando_las_colas_se_solapan`
**AFIRMAN EL DEFECTO A PROPOSITO**: su nombre lo dice y sus numeros son los de
hoy. El dia que el detector se arregle, esas dos pruebas se ponen rojas, y lo que
toca entonces es INVERTIRLAS -ocho ataques de ocho notas, cero inventadas- y
dejar escrito quien lo arreglo. No se borran por molestas: son el unico sitio del
programa donde esta escrito que esto pasaba.

**Los numeros de la mitad del solape reproducen la sonda de la spec §10 a la
cadencia de produccion.** La spec midio «ocho notas sinteticas que suenan el 95 %
del pulso producen DOCE pulsaciones, con parejas separadas 32 ms». Aqui, con la
escala de ocho notas al tempo escrito y `sustain=1.0` -notas de 780 ms cada 600,
o sea 180 ms de cola sonando encima de la nota siguiente-, el detector de
produccion firma **doce** pulsaciones de ocho notas, exactamente el numero de la
spec. Lo que NO se reproduce es la separacion de 32 ms de las parejas: la sonda
de la spec recorria el audio con un salto de 512 muestras (10,7 ms) y 32 ms son
sus tres cuadros, mientras que aqui el salto es el de produccion (21 ms) y las
parejas salen a 126 ms (seis cuadros). La separacion es del salto; el doce es del
detector, y es el que se afirma.

**Y no es un artefacto del gemelo.** En una guitarra de verdad las cuerdas si
siguen sonando unas sobre otras: una pieza con notas largas y un alumno que no
apaga las cuerdas es el caso normal, no el raro. Por eso el solape se provoca
desde el perfil (`sustain`) y no desde una pieza inventada, y por eso la mitad de
control -`test_sin_solape_no_hay_fantasmas`- tiene que estar: lo que demuestra
que la causa es el SOLAPE y no el gemelo es que con `sustain=0.0`, el mismo
interprete sobre la misma pieza, no hay ni un fantasma.

Los perfiles de las cuatro pruebas se construyen con `dataclasses.replace` sobre
`PERFECTO`, que es la forma que fijo `nucleo/gemelo/perfiles.py`: asi en cada
prueba esta escrito que lo UNICO que cambia respecto del oraculo es ese campo.
Variar un campo a la vez es lo que permite atribuirle a el lo que se mide.
"""

from dataclasses import replace

import pytest

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import INTERVALO_DE_ANALISIS_S, Analizador
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones
from nucleo.gemelo.cadena import (
    RegistroDeLaCadena,
    _ventana_en,
    pasar_por_la_cadena,
)
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.gemelo.veredicto import Veredicto, juzgar
from nucleo.musica import esta_afinada
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import InformeDePasada, PlanDePasada, SesionDeEstudio

# Las notas de `escala_de_ocho_notas()`: ocho, una por pulso, ninguna repetida y
# ningun acorde, asi que las ocho son medibles y ninguna se excluye.
NOTAS = 8

# Cuantas pulsaciones firma el detector de produccion sobre la escala con las
# colas solapadas, MEDIDO: doce de ocho notas. Es el numero de la spec §10, y es
# el defecto: cuatro de esas doce no las toco nadie.
ATAQUES_CON_SOLAPE = 12

# Lo que se le concede a una medicion de cents antes de llamarla otra cosa. El
# maximo medido entre lo que el gemelo desafino y lo que la cadena leyo es de
# 2,2 cents (la nota 6), asi que 3,0 no deja pasar ni media coma.
MARGEN_CENTS = 3.0


def _pasada(
    perfil, semilla: int = 0
) -> tuple[Interpretacion, RegistroDeLaCadena, Veredicto, InformeDePasada]:
    """Una pasada entera por la cadena de produccion con el perfil que se le de.

    Es el mismo montaje que `tests/test_gemelo_oraculo.py`, con el mismo tramo y
    sin bucle ni cuenta atras: asi lo unico que separa estas pruebas del oraculo
    es el campo del perfil que cada una cambia, y lo que se mide se le puede
    atribuir a el.

    `al_cambiar_repeticion=None` NO es un detalle: ese aviso existe para que el
    servidor rearranque el metronomo, y el metronomo abre audio. Una suite que lo
    pasara abriria un dispositivo de sonido en cada prueba.

    Devuelve las cuatro cosas que la pasada deja -la verdad, los reportes crudos,
    el veredicto y el informe de la vuelta- porque las pruebas de este archivo
    miran la misma pasada desde sitios distintos y montarla cuatro veces seria
    tardar el cuadruple en medir lo mismo.
    """
    pieza = escala_de_ocho_notas()
    interpretacion = interpretar(pieza, perfil, semilla=semilla)
    estudio = SesionDeEstudio(
        pieza, PlanDePasada(en_bucle=False, compases_de_cuenta_atras=0)
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)

    registro = pasar_por_la_cadena(interpretacion, conductor)
    veredicto = juzgar(interpretacion, registro)

    assert len(registro.vueltas) == 1, (
        "una pasada sin bucle cierra exactamente una vuelta; "
        f"esta cerro {len(registro.vueltas)}"
    )
    return interpretacion, registro, veredicto, registro.vueltas[-1]


def _suma(informe: InformeDePasada, contador: str) -> int:
    """Un contador del informe sumado sobre los compases del tramo."""
    return sum(getattr(compas, contador) for compas in informe.compases)


def _ataques_firmados(interpretacion: Interpretacion) -> list:
    """Las pulsaciones que el detector de produccion firma sobre este audio.

    Es la sonda de la spec §10 hecha con el detector de verdad y a la cadencia de
    verdad: `Analizador` de produccion, `DetectorPulsaciones` de produccion y el
    salto de `INTERVALO_DE_ANALISIS_S`. No pasa por la sesion de estudio a
    proposito: lo que se cuenta aqui son los ATAQUES, antes de que nadie los
    adjudique a una nota escrita, que es el unico sitio donde «doce de ocho» se
    puede ver como lo que es. El veredicto los ve ya adjudicados y entonces el
    exceso aparece repartido entre inventadas, perdidas y mal adjudicadas.

    `_ventana_en` se importa de la cadena en vez de repetirlo aqui: el relleno de
    la ultima ventana es parte de como se recorre el audio -los cuatro ultimos
    cuadros son los que resuelven el ataque de la ultima nota- y una copia local
    seria un segundo recorrido que podria divergir del que corre en produccion.
    """
    frecuencia = interpretacion.frecuencia_muestreo
    analizador = Analizador(
        PERFILES[interpretacion.pieza.perfil], frecuencia_muestreo=frecuencia
    )
    detector = DetectorPulsaciones()
    ventana = analizador.tamano_ventana
    paso = round(INTERVALO_DE_ANALISIS_S * frecuencia)

    firmadas = []
    for inicio in range(0, interpretacion.muestras.size, paso):
        resultado = analizador.procesar(
            _ventana_en(interpretacion.muestras, inicio, ventana)
        )
        # El instante de cada ventana es su FINAL, como en la cadena: es lo que
        # pasa en vivo y es lo que esta medido (ver la cabecera de
        # `nucleo/gemelo/cadena.py`).
        pulsacion = detector.procesar(resultado, (inicio + ventana) / frecuencia)
        if pulsacion is not None:
            firmadas.append(pulsacion)
    return firmadas


@pytest.mark.parametrize("semilla", (0, 1, 2, 3, 7, 11))
def test_el_trasteo_no_cuenta_como_nota_limpia(semilla):
    """Una nota que roza el traste suena, pero la cadena no la da por buena.

    El perfil es `PERFECTO` con `probabilidad_de_trasteo=1.0` y nada mas: las
    ocho notas suenan a su hora, a su altura y con su fuerza, y lo unico que
    cambia es que las ocho salen rozando el traste
    (`TRASTEO_DE_LA_NOTA_SUCIA = 0.7` de suciedad en `cuerda_pulsada`).

    Medido, y es mas fuerte que lo que el brief pedia: no es que las notas
    trasteadas no salgan LIMPIAS, es que la cadena **no las reconoce en absoluto**.
    Con las seis semillas, cero limpias y cero acertadas de ocho; con las semillas
    0 a 3 la cadena no publica ni un reporte y las ocho notas se pierden, y con
    las semillas 7 y 11 publica uno solo, con la altura equivocada (38 y 43 contra
    un 57 escrito). De ahi la asercion de que perdidas mas mal adjudicadas son las
    ocho: ni una nota llega bien adjudicada por ningun camino.

    Y cuadra con la tabla de calibracion de `nucleo/gemelo/cuerda.py`, que midio
    que con 0,8 de trasteo el detector lee la nota correcta en el 8 % de las
    ventanas: a 0,7 ya casi no queda altura que leer. El gemelo no esta fallando
    las notas -`notas_tocadas` son las ocho y las ocho vienen con
    `trasteada=True`-: las esta tocando sucias.

    Las ocho siguen siendo MEDIBLES, y eso es lo que hace que esto cuente: la
    cadena las esperaba y no las vio, no es que las descartara.
    """
    trasteado = replace(PERFECTO, nombre="trasteado", probabilidad_de_trasteo=1.0)
    interpretacion, _, veredicto, informe = _pasada(trasteado, semilla=semilla)

    assert veredicto.notas_tocadas == NOTAS
    assert sum(1 for evento in interpretacion.eventos if evento.trasteada) == NOTAS

    assert _suma(informe, "notas_medibles") == NOTAS
    assert _suma(informe, "limpias") == 0
    assert _suma(informe, "acertadas") == 0
    assert _suma(informe, "limpias") < NOTAS

    assert len(veredicto.perdidas) + len(veredicto.mal_adjudicadas) == NOTAS
    assert veredicto.inventadas == 0
    assert veredicto.limpio is False


def test_las_notas_que_se_solapan_generan_ataques_fantasma():
    """**DEFECTO MEDIDO Y AFIRMADO A PROPOSITO** (spec §10). No se arregla aqui.

    `PERFECTO` con `sustain=1.0` y nada mas: el interprete toca las ocho notas a
    su hora y a su altura, pero no apaga ninguna. Cada nota dura 780 ms
    (`COLA_DE_SUSTAIN = 1.3` sobre una figura de 600 ms) y la siguiente entra 600
    ms despues, asi que hay **180 ms de cola sonando encima** de cada nota nueva.
    Eso es lo que hace una guitarra de verdad cuando nadie apaga las cuerdas.

    Lo que la cadena hace con ese audio, medido con la semilla por omision:

        inventadas          3
        perdidas            las notas 2, 3 y 4 de la vuelta 1
        mal adjudicadas     la nota 1 con un 55 (sono un 57)
                            la nota 7 con un 43 (sono un 67)

    Los tres reportes inventados son las pulsaciones que el detector firma en
    medio de dos notas, donde no empezo ninguna; las tres perdidas son las notas
    de verdad cuyo sitio en el emparejamiento se quedo ocupado por uno de esos
    fantasmas. Son dos caras del mismo hecho, y por eso se afirman las dos: un
    arreglo que solo quitara las invenciones y dejara las perdidas no seria un
    arreglo.

    **El 55 de la nota 1 y el 43 de la nota 7 son la firma del fantasma**, no
    ruido: el 55 es la nota ANTERIOR (su cola sigue sonando cuando el detector
    sella el ataque) y el 43 esta dos octavas por debajo del 67 escrito, que es
    lo que sale de dos colas sumadas en el anillo de la cuerda.

    **Nada de esto se arregla bajando los numeros.** La causa esta en
    `DetectorPulsaciones`, y tocarla es tocar el corazon de las etapas 2a y 3a.
    El dia que se decida, esta prueba se invierte -`inventadas == 0`, nada perdido
    y nada mal adjudicado- y se dice en su docstring quien lo decidio.
    """
    solapado = replace(PERFECTO, nombre="solapado", sustain=1.0)
    interpretacion, _, veredicto, _ = _pasada(solapado)

    # El solape que el perfil provoca, que es la causa de todo lo de abajo: cada
    # nota sigue sonando 180 ms despues de que entre la siguiente.
    duraciones = {round(evento.duracion_s, 3) for evento in interpretacion.eventos}
    assert duraciones == {0.780}
    assert interpretacion.eventos[1].instante_s - interpretacion.eventos[0].instante_s == (
        pytest.approx(0.600, abs=0.001)
    )

    # EL DEFECTO. La afirmacion de que hay fantasmas va antes y por separado del
    # recuento exacto: si algun dia el numero cambia sin desaparecer, lo que tiene
    # que quedar escrito es que seguia habiendo.
    assert veredicto.inventadas > 0
    assert veredicto.inventadas == 3
    assert veredicto.perdidas == ((1, 2), (1, 3), (1, 4))
    assert veredicto.mal_adjudicadas == ((1, 1, 55), (1, 7, 43))
    assert veredicto.limpio is False

    # Y el gemelo toco las ocho notas que la pieza escribe, ni una mas: las que
    # sobran las firma la cadena.
    assert veredicto.notas_tocadas == NOTAS
    assert veredicto.excluidas == ()


def test_sin_solape_no_hay_fantasmas():
    """La mitad que demuestra que la causa es el SOLAPE y no el gemelo.

    Mismo interprete, misma pieza, misma semilla y mismo recorrido; lo unico que
    cambia es `sustain=0.0`, que es lo que hace que el interprete corte cada nota
    antes de la siguiente (`FRACCION_DE_CORTE`: 510 ms de los 600 del hueco, con
    90 ms de silencio garantizado entre dos notas). Medido: cero inventadas, cero
    perdidas, cero mal adjudicadas.

    Sin esta prueba, la de arriba no probaria lo que dice: unos fantasmas que
    aparecieran tambien sin solape serian un defecto del gemelo -o del montaje- y
    no de lo que la spec §10 describe.

    `sustain=0.0` es el valor que `PERFECTO` ya trae, y se escribe con `replace`
    igualmente: lo que esta prueba afirma es la pareja del campo, y que el cero se
    lea en la prueba es justo lo que la hace la mitad de la de arriba.
    """
    cortado = replace(PERFECTO, nombre="cortado", sustain=0.0)
    interpretacion, _, veredicto, _ = _pasada(cortado)

    duraciones = {round(evento.duracion_s, 3) for evento in interpretacion.eventos}
    assert duraciones == {0.510}

    assert veredicto.inventadas == 0
    assert veredicto.perdidas == ()
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.limpio is True


@pytest.mark.parametrize(
    ("sustain", "ataques"),
    ((1.0, ATAQUES_CON_SOLAPE), (0.0, NOTAS)),
    ids=("con solape", "sin solape"),
)
def test_el_detector_firma_mas_ataques_que_notas_cuando_las_colas_se_solapan(
    sustain, ataques
):
    """**EL DEFECTO DE LA SPEC §10, EN SU FORMA CRUDA.** Afirmado a proposito.

    Es la misma cosa que `test_las_notas_que_se_solapan_generan_ataques_fantasma`
    medida un paso antes: ahi los ataques llegan ya adjudicados a notas escritas y
    el exceso se reparte entre invenciones, perdidas y malas adjudicaciones; aqui
    se cuentan tal y como el detector los firma, y entonces el defecto se ve como
    un solo numero. La spec midio **doce pulsaciones de ocho notas** con una
    sonda propia; esta prueba la reproduce con el detector de produccion y el
    salto de produccion y sale el mismo doce.

    Con `sustain=0.0` salen ocho exactas, que es la mitad de control: el detector
    no se inventa nada mientras las notas no se pisen.

    El dia que el detector se arregle, lo que hay que escribir aqui es ocho en los
    dos casos. Bajar el doce a «mas de ocho» no seria lo mismo: lo que esta
    medido es cuantos, y de los doce hay cuatro que nadie toco.
    """
    perfil = replace(PERFECTO, nombre=f"sustain {sustain}", sustain=sustain)
    pieza = escala_de_ocho_notas()
    interpretacion = interpretar(pieza, perfil, semilla=0)

    firmados = _ataques_firmados(interpretacion)

    assert len(firmados) == ataques
    assert len(interpretacion.eventos) == NOTAS


def test_la_desafinacion_se_ve_en_el_informe():
    """Lo que el gemelo desafina, la cadena lo lee desafinado. **No es un defecto.**

    `PERFECTO` con `cents_de_desafinacion=50.0` y nada mas: las ocho notas suenan
    a su hora y en su traste, pero con la altura corrida. La desafinacion esta en
    el AUDIO -el interprete le pasa `midi + cents/100` a `cuerda_pulsada`- y no
    solo en el campo `cents` de la verdad, asi que esto mide al afinador de
    produccion y no a un numero que el gemelo se haya copiado a si mismo.

    Medido con la semilla por omision: las ocho notas llegan al informe, **siete
    de las ocho con `afinada=False`**, y la que falta no es un fallo del afinador
    sino un acierto: es la nota 1, que el sorteo desafino solo 2,1 cents y cae
    dentro de los 5 cents de `esta_afinada`. Por eso la prueba no afirma «la
    mayoria vienen desafinadas» sino la correspondencia NOTA A NOTA con la verdad:
    una prueba que solo contara las desafinadas la pasaria igual un afinador que
    dijera «desafinada» siempre, que es el defecto que nadie veria.

    Y los cents leidos son los escritos: el mayor desacuerdo entre lo que el
    gemelo desafino y lo que la cadena midio es de 2,2 cents (la nota 6), muy por
    debajo del umbral de 5 con que se decide `afinada`.

    La desafinacion no le cuesta a la cadena ni una nota: el veredicto sale limpio
    -ocho notas vistas, nada inventado y nada mal adjudicado-, porque 50 cents de
    desviacion tipica es medio semitono y el semitono mas cercano sigue siendo el
    escrito.
    """
    desafinado = replace(PERFECTO, nombre="desafinado", cents_de_desafinacion=50.0)
    interpretacion, registro, veredicto, _ = _pasada(desafinado)

    assert veredicto.limpio is True
    assert len(registro.reportes) == NOTAS

    verdad = {evento.indice_pretendido: evento for evento in interpretacion.eventos}
    desafinadas = 0
    for reporte in registro.reportes:
        evento = verdad[reporte.tocada.indice]
        assert reporte.tocada.cents == pytest.approx(evento.cents, abs=MARGEN_CENTS)
        # El veredicto de la cadena contra el de la verdad, con la REGLA DEL
        # PROGRAMA (`nucleo.musica.esta_afinada`) aplicada a los cents escritos.
        # Repetir aqui el umbral de 5 cents seria copiarse una regla que el nucleo
        # ya publica, que es la duplicacion que la etapa 2a hubo que quitar cuatro
        # veces.
        assert reporte.tocada.afinada is esta_afinada(evento.cents)
        if reporte.tocada.afinada is False:
            desafinadas += 1

    # Siete de ocho, no ocho de ocho: la nota 1 salio con 2,1 cents y esta
    # afinada de verdad. El numero se afirma para que una cadena que empezara a
    # llamar desafinado a todo tampoco pasara por aqui.
    assert desafinadas == NOTAS - 1
