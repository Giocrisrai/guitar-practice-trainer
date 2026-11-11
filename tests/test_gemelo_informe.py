"""EL INFORME POR COMPASES Y LA REGLA DEL TEMPO, contra la verdad. La prueba de la T9.

Lo que aqui se comprueba no es que el informe sea coherente consigo mismo -eso ya
lo hace `tests/test_estudio.py` con el seguidor colocado a mano- sino que **lo que
el informe dice de cada compas coincide con lo que de verdad se toco en ese
compas**, con el audio entrando por la cadena de produccion. El gemelo es el unico
que puede firmar eso, porque es el unico que escribe la verdad antes de generar el
sonido.

**LOS DOS DEFECTOS QUE ESTA TAREA CIERRA, con sus numeros de antes.**

1. *`HistorialDeEstudio.peores_compases` no multiplicaba por `repeticiones`*
   (defecto 4 del §8). `limpias` acumula TODAS las vueltas que el informe lleva
   dentro y `notas_medibles` es lo que hay escrito en el compas, que no se repite.
   Un informe de cuatro vueltas con un compas de cuatro notas daba el compas por
   bueno con **cuatro limpias de las dieciseis** que se tocaron -tres vueltas
   enteras falladas- y el boton de machacar no lo nominaba nunca. Lo mide
   `test_peores_compases_cuenta_las_repeticiones`.

2. *`informe.repeticiones` valia 2 en una pasada SIN bucle.*
   `ConductorDeEstudio._cerrar` llamaba a `cerrar_repeticion()` al terminar el
   tramo aunque no hubiera bucle, el `_vueltas_cerradas` del estudio subia a 1 y
   `informe` -que es `_vueltas_cerradas + 1`- salia 2. El seguidor ya esta vacio,
   asi que el numerador de `proporcion_limpia` no sube y el denominador se
   duplica: **ocho notas limpias de ocho salian 0,5**. Y ese numero es el que la
   pantalla publica y el que decide si el tempo sube solo, asi que no hacia falta
   el gemelo para verlo: cualquier alumno que terminara un tramo sin bucle veia su
   proporcion a la mitad. Lo mide
   `test_una_pasada_sin_bucle_no_cuenta_dos_vueltas`.

**TODOS los numeros estan MEDIDOS** sobre `escala_de_ocho_notas()`, semilla 0 y el
salto de produccion (21 ms). Si uno se queda corto, la respuesta no es
ensancharlo: es mirar por que la cadena cambio.

**POR QUE LAS DOS PRUEBAS DE COMPASES VAN AL 40 % DEL TEMPO.** Al tempo escrito, el
compas 1 de esta pieza sale con 3 limpias de 4 por un defecto conocido y ajeno a
esta tarea -la nota 3 se firma 89,3 ms despues de su ataque contra una ventana de
acierto de 80 ms, el `xfail(strict=True)` de `tests/test_gemelo_oraculo.py`-, asi
que `peores_compases` lo nomina y la afirmacion «el compas 1 no se nomina» no se
podria escribir sin mentir. Al 40 % la ventana de acierto se estira con el factor
(80 / 0,40 = 200 ms), el compas 1 sale limpio del todo y el unico compas nominado
es el que esta prueba estropea a proposito. Por eso el retraso del perfil del
compas 2 son **300 ms y no 120**: con 120 ms al 40 % las cuatro notas siguen
entrando en la ventana de 200 (medido: 4 limpias de 4), y una prueba del «compas
tocado tarde» en la que nada sale tarde no mide nada.
"""

import dataclasses

import numpy as np
import pytest

from nucleo.gemelo.cadena import RegistroDeLaCadena, pasar_por_la_cadena
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO, PerfilDeDestreza
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.gemelo.veredicto import juzgar
from nucleo.piezas.compases import pulsos_por_compas
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import (
    FACTOR_MINIMO,
    PASADAS_BUENAS_PARA_SUBIR,
    PASO_DEL_FACTOR,
    CompasDelInforme,
    HistorialDeEstudio,
    InformeDePasada,
    PlanDePasada,
    SesionDeEstudio,
    proporcion_limpia,
)
from nucleo.piezas.modelo import pulsos_a_segundos

# Las notas de `escala_de_ocho_notas()`: ocho, cuatro por compas, ninguna repetida
# y ningun acorde, asi que las ocho son medibles.
NOTAS = 8
NOTAS_POR_COMPAS = 4

# Lo que se le concede a un desfase medido antes de llamarlo otra cosa, en ms:
# menos de un cuadro de analisis (21 ms), igual que en el oraculo y en el bucle.
MARGEN_MS = 15.0

# El retraso que el perfil del compas 2 mete en sus notas, en segundos. Ver la
# cabecera del modulo: 300 ms al 40 % del tempo, para pasarse de la ventana de
# acierto estirada (200 ms).
RETRASO_DEL_COMPAS_2_S = 0.300

# El desfase medio que la cadena firma para cada compas al 40 % del tempo, en ms,
# MEDIDO: el compas 1 lo toca el oraculo y el 2 va 300 ms tarde.
DESFASE_DEL_COMPAS_1_MS = 27.8
DESFASE_DEL_COMPAS_2_TARDE_MS = 327.8

# La proporcion limpia de una pasada PERFECTA sin bucle, MEDIDA en las dos
# configuraciones. Al tempo escrito son 7 limpias de 8 por el temblor del onset
# (el `xfail` del oraculo); al 40 % son las ocho.
#
# **Son los dos numeros del defecto 2**: con `repeticiones=2` salian 0,4375 y 0,5.
PROPORCION_PERFECTA_AL_TEMPO_ESCRITO = 7 / 8
PROPORCION_PERFECTA_AL_40 = 1.0


def _audio_por_compases(
    perfil_del_compas_1: PerfilDeDestreza,
    perfil_del_compas_2: PerfilDeDestreza,
    factor_tempo: float = 1.0,
) -> Interpretacion:
    """Una interpretacion de la pieza entera con UN PERFIL POR COMPAS.

    Es el instrumento que las dos primeras pruebas necesitan y que `interpretar`
    no da: su perfil vale para el tramo entero, asi que no hay forma de pedirle
    que solo el compas 2 se toque tarde. Lo que si da es un tramo y una cuenta
    atras, y con esas dos cosas el audio se arma en dos mitades que se SUMAN:

    * el compas 1 se interpreta como el tramo 1-1, sin cuenta atras, asi que sus
      notas caen donde la pieza las escribe;
    * el compas 2 se interpreta como el tramo 2-2 con una cuenta atras de un
      compas, que es exactamente el silencio que lo coloca en su sitio dentro de
      la pieza (2,4 s al tempo escrito), sin que esta prueba tenga que desplazar
      muestras a mano ni recalcular ni un instante.

    La verdad se concatena en el mismo orden -los indices del compas 1 y luego los
    del 2, que suben-, que es lo que `juzgar` necesita para deducir la vuelta.

    El `Interpretacion` resultante declara el tramo ENTERO (1-2) y **cuenta atras
    cero**, porque el audio de la mitad de arriba no lleva ninguna: la cuenta de
    la segunda mitad es el relleno que la coloca, no una cuenta de la pasada, y
    declararla descontaria 2,4 s del eje del cabezal dos veces.

    Las dos mitades se suman y se recortan a la escala completa, igual que
    `interprete._generar`: dos colas que se solapan suman, y por encima de 1,0 no
    hay nada que el cable pueda traer.
    """
    pieza = escala_de_ocho_notas()
    cuenta_del_segundo_s = (
        pulsos_a_segundos(pulsos_por_compas(pieza), pieza.tempo) / factor_tempo
    )
    primero = interpretar(
        pieza,
        perfil_del_compas_1,
        factor_tempo=factor_tempo,
        semilla=0,
        primer_compas=1,
        ultimo_compas=1,
    )
    segundo = interpretar(
        pieza,
        perfil_del_compas_2,
        factor_tempo=factor_tempo,
        semilla=0,
        primer_compas=2,
        ultimo_compas=2,
        segundos_de_cuenta_atras=cuenta_del_segundo_s,
    )
    muestras = np.zeros(
        max(primero.muestras.size, segundo.muestras.size), dtype=primero.muestras.dtype
    )
    muestras[: primero.muestras.size] += primero.muestras
    muestras[: segundo.muestras.size] += segundo.muestras
    np.clip(muestras, -1.0, 1.0, out=muestras)
    return Interpretacion(
        pieza=pieza,
        muestras=muestras,
        eventos=primero.eventos + segundo.eventos,
        frecuencia_muestreo=primero.frecuencia_muestreo,
        duracion_s=muestras.size / primero.frecuencia_muestreo,
        silencio_de_cabecera_s=primero.silencio_de_cabecera_s,
        primer_compas=1,
        ultimo_compas=2,
        factor_tempo=factor_tempo,
        repeticiones=1,
        segundos_de_cuenta_atras=0.0,
    )


def _pasar(
    interpretacion: Interpretacion,
    factor_tempo: float = 1.0,
    en_bucle: bool = False,
    tempo_automatico: bool = False,
    historial: HistorialDeEstudio | None = None,
) -> tuple[RegistroDeLaCadena, ConductorDeEstudio]:
    """Mete una interpretacion por la cadena de produccion y devuelve lo que dejo.

    `al_cambiar_repeticion=None` NO es un detalle: ese aviso es del servidor para
    rearrancar el metronomo, y el metronomo abre audio.
    """
    estudio = SesionDeEstudio(
        interpretacion.pieza,
        PlanDePasada(
            factor_tempo=factor_tempo,
            en_bucle=en_bucle,
            compases_de_cuenta_atras=0,
            tempo_automatico=tempo_automatico,
        ),
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(
        estudio, historial=historial, al_cambiar_repeticion=None
    )
    return pasar_por_la_cadena(interpretacion, conductor), conductor


def _compas(informe: InformeDePasada, numero: int) -> CompasDelInforme:
    fila = next(c for c in informe.compases if c.numero == numero)
    return fila


def _informe_de_una_pasada(
    perfil_del_compas_2: PerfilDeDestreza, factor_tempo: float = 0.40
) -> tuple[InformeDePasada, ConductorDeEstudio]:
    """La pasada de las dos pruebas de compases: el compas 1 perfecto y el 2 no."""
    interpretacion = _audio_por_compases(
        PERFECTO, perfil_del_compas_2, factor_tempo=factor_tempo
    )
    registro, conductor = _pasar(interpretacion, factor_tempo=factor_tempo)
    veredicto = juzgar(interpretacion, registro)
    # El emparejamiento del gemelo tiene que estar limpio ANTES de creerse el
    # informe: si la cadena hubiera adjudicado las notas del compas 2 a las del 1,
    # los contadores por compas hablarian de otra cosa y la prueba seguiria verde.
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert len(registro.vueltas) == 1, (
        f"una pasada sin bucle cierra una vuelta; esta cerro {len(registro.vueltas)}"
    )
    return registro.vueltas[-1], conductor


def test_el_informe_senala_el_compas_que_se_toco_tarde():
    """El compas 2 se toca 300 ms tarde y el informe lo dice, con su numero.

    El perfil del compas 2 se hace en la prueba con `dataclasses.replace`, que es
    lo que `nucleo/gemelo/perfiles.py` pide por escrito: los cuatro perfiles de
    fabrica son constantes en las que se apoya la etapa entera y una variante no
    se añade como un quinto perfil.

    Medido al 40 % del tempo: el compas 1 firma +27,8 ms -el retraso de
    publicacion de la cadena, que es real- y el compas 2 firma +327,8, o sea los
    mismos 27,8 mas los 300 del perfil. Las cuatro notas del compas 2 salen
    «tarde» y ninguna limpia; las cuatro del 1 salen limpias.

    Se afirman cuatro cosas y las cuatro hacen falta:

    * el desfase del compas 2 es POSITIVO, que es «tocaste tarde» y no «la cadena
      reporta antes de que suene»;
    * es MAYOR que el del compas 1, que es el diagnostico que el informe existe
      para dar («el 2 lo tocas tarde», no «fallas»);
    * la DIFERENCIA entre los dos es el retraso que el perfil metio, con margen de
      menos de un cuadro: sin esto, una cadena que inflara los dos desfases por
      igual pasaria las dos primeras;
    * y `peores_compases` nomina al 2 y **solo** al 2.
    """
    tarde = dataclasses.replace(PERFECTO, desfase_medio_s=RETRASO_DEL_COMPAS_2_S)
    informe, conductor = _informe_de_una_pasada(tarde)

    primero, segundo = _compas(informe, 1), _compas(informe, 2)
    assert primero.desfase_medio_s is not None
    assert segundo.desfase_medio_s is not None
    assert segundo.desfase_medio_s > 0.0, (
        f"el compas 2 firma {segundo.desfase_medio_s * 1000:+.1f} ms: la cadena no "
        "puede reportar un ataque antes de que suene"
    )
    assert segundo.desfase_medio_s > primero.desfase_medio_s
    assert primero.desfase_medio_s * 1000.0 == pytest.approx(
        DESFASE_DEL_COMPAS_1_MS, abs=MARGEN_MS
    )
    assert segundo.desfase_medio_s * 1000.0 == pytest.approx(
        DESFASE_DEL_COMPAS_2_TARDE_MS, abs=MARGEN_MS
    )
    diferencia_ms = (segundo.desfase_medio_s - primero.desfase_medio_s) * 1000.0
    assert diferencia_ms == pytest.approx(RETRASO_DEL_COMPAS_2_S * 1000.0, abs=MARGEN_MS), (
        f"el informe dice que el compas 2 va {diferencia_ms:.1f} ms mas tarde que el "
        f"1, y el perfil le metio {RETRASO_DEL_COMPAS_2_S * 1000:.0f}"
    )

    # Las notas: el 2 entero tarde y sin limpias, el 1 entero limpio.
    assert segundo.acertadas == NOTAS_POR_COMPAS, (
        "las notas del compas 2 suenan con la altura correcta, solo tarde"
    )
    assert segundo.tarde == NOTAS_POR_COMPAS
    assert segundo.limpias == 0
    assert primero.limpias == NOTAS_POR_COMPAS

    assert conductor.historial.peores_compases() == ((2, 1, 1),), (
        "el compas nominado tiene que ser el 2 y solo el 2; el 1 se toco limpio: "
        f"{conductor.historial.peores_compases()}"
    )


def test_el_informe_senala_el_compas_que_se_fallo():
    """El compas 2 no se toca y el informe lo dice: 0 limpias, y el 1 completo.

    Es otra cosa que la prueba de arriba y por eso existe aparte: un compas tarde
    y un compas fallado salen los dos con `limpias=0`, y lo que los distingue es
    `acertadas` -4 y 0- y el desfase -un numero y None-. Una pasada que confundiera
    las dos cosas le diria al alumno que machaque el ritmo de un compas que no esta
    tocando.

    Medido al 40 % del tempo: el compas 2 sale con 0 acertadas, 0 limpias y
    `desfase_medio_s` a None -no hay ni una medicion-, y el compas 1 con sus cuatro
    notas limpias. `peores_compases` nomina al 2 y solo al 2.
    """
    fallado = dataclasses.replace(PERFECTO, probabilidad_de_fallo=1.0)
    informe, conductor = _informe_de_una_pasada(fallado)

    primero, segundo = _compas(informe, 1), _compas(informe, 2)
    assert segundo.notas_medibles == NOTAS_POR_COMPAS, (
        "el compas 2 sigue teniendo cuatro notas escritas: no se tocaron, pero estan"
    )
    assert segundo.acertadas == 0
    assert segundo.a_tiempo == 0
    assert segundo.tarde == 0
    assert segundo.pronto == 0
    assert segundo.limpias == 0
    assert segundo.desfase_medio_s is None, (
        "sin una sola nota medida no hay desfase que publicar, y un 0,0 ahi diria "
        "que el compas se toco a tiempo"
    )

    assert primero.notas_medibles == NOTAS_POR_COMPAS
    assert primero.acertadas == NOTAS_POR_COMPAS
    assert primero.limpias == NOTAS_POR_COMPAS

    assert conductor.historial.peores_compases() == ((2, 1, 1),)


def test_una_pasada_sin_bucle_no_cuenta_dos_vueltas():
    """**EL DEFECTO 2.** Una pasada sin bucle es UNA vuelta, no dos.

    `ConductorDeEstudio` cierra el tramo al terminarlo aunque no haya bucle, y lo
    hacia contando una vuelta: `_vueltas_cerradas` subia a 1 y
    `informe.repeticiones` -que es `_vueltas_cerradas + 1`- salia 2 con el seguidor
    ya vacio. El numerador de `proporcion_limpia` no sube y el denominador se
    duplica, asi que **ocho notas limpias de ocho salian 0,5**: medido, y con el
    tempo automatico colgando de ese numero.

    Las dos configuraciones se afirman porque las dos salen mal con el defecto y
    los dos numeros son distintos: al 40 % la proporcion es 1,0 (y era 0,5) y al
    tempo escrito es 0,875 -7 de 8, el temblor del onset del `xfail` del oraculo-
    (y era 0,4375). Con una sola configuracion, un mutante que dividiera por 2 solo
    en un caso pasaria.

    Se afirma ademas lo que NO cambia: el historial anota UNA pasada, y el informe
    que anota es el de solo esa vuelta, con `repeticiones=1`. Si el arreglo se
    hubiera hecho dejando de cerrar la repeticion, el historial se quedaria vacio
    y el tempo automatico no se moveria nunca.
    """
    for factor, proporcion in (
        (0.40, PROPORCION_PERFECTA_AL_40),
        (1.00, PROPORCION_PERFECTA_AL_TEMPO_ESCRITO),
    ):
        interpretacion = interpretar(
            escala_de_ocho_notas(), PERFECTO, factor_tempo=factor, semilla=0
        )
        registro, conductor = _pasar(interpretacion, factor_tempo=factor)

        informe = conductor.estudio.informe
        assert informe.repeticiones == 1, (
            f"al factor {factor} el informe de la pasada dice "
            f"{informe.repeticiones} vueltas, y solo se dio una"
        )
        assert proporcion_limpia(informe) == pytest.approx(proporcion), (
            f"al factor {factor} la proporcion limpia sale "
            f"{proporcion_limpia(informe)} y lo tocado da {proporcion}"
        )
        assert len(registro.vueltas) == 1
        assert registro.vueltas[-1].repeticiones == 1
        assert conductor.historial.pasadas == 1


def test_peores_compases_cuenta_las_repeticiones():
    """**EL DEFECTO 4.** Las notas de un compas se multiplican por las vueltas.

    Dos informes de CUATRO repeticiones cada uno, armados a mano porque lo que se
    mide es la cuenta y no la cadena -el gemelo no hace falta para esto, y una
    pasada de audio de cuatro vueltas la mediria peor: `limpias` dependeria del
    detector-. El compas 1 trae `limpias=4` con `notas_medibles=4` y
    `repeticiones=4`: se tocaron DIECISEIS notas y solo cuatro salieron limpias, o
    sea tres vueltas enteras falladas. El compas 2 trae las dieciseis limpias.

    Antes del arreglo, `peores_compases` comparaba `limpias < notas_medibles` -4 <
    4, falso- y daba el compas 1 por bueno: devolvia `()` y el boton de machacar
    no lo nominaba nunca. Hoy devuelve `((1, 2, 2))`: fallado en las dos pasadas
    contadas.

    El compas 2 esta en la prueba para que el arreglo no pueda ser «nominar
    siempre»: con `limpias = medibles * repeticiones` no se nomina, y si apareciera
    en la respuesta el remedio seria peor que el defecto.
    """
    cuatro_vueltas = InformeDePasada(
        compases=(
            _fila(numero=1, limpias=NOTAS_POR_COMPAS),
            _fila(numero=2, limpias=NOTAS_POR_COMPAS * 4),
        ),
        ritmo_aproximado=False,
        compas_variable=False,
        factor_tempo=1.0,
        repeticiones=4,
    )
    historial = HistorialDeEstudio()
    for _ in range(2):
        historial.anotar(cuatro_vueltas)

    assert historial.pasadas == 2
    assert historial.peores_compases() == ((1, 2, 2),), (
        "el compas 1 tiene 4 limpias de las 16 que se tocaron y tiene que salir "
        f"fallado en las dos pasadas: {historial.peores_compases()}"
    )
    # Y la proporcion limpia de ese informe, que es la otra mitad de la misma
    # cuenta y ya dividia por las vueltas: 20 limpias de 32 medibles.
    assert proporcion_limpia(cuatro_vueltas) == pytest.approx(20 / 32)


def _fila(numero: int, limpias: int) -> CompasDelInforme:
    """Un compas del informe con `limpias` limpias de cuatro notas escritas.

    `acertadas` y `a_tiempo` se ponen en `limpias` porque es la unica combinacion
    coherente -una nota limpia es acertada Y a tiempo- y porque `peores_compases`
    no las mira: mira `limpias` contra `notas_medibles`. Ponerlas a otro valor
    seria armar un informe que el estudio no puede producir.
    """
    return CompasDelInforme(
        numero=numero,
        notas_escritas=NOTAS_POR_COMPAS,
        notas_medibles=NOTAS_POR_COMPAS,
        acertadas=limpias,
        a_tiempo=limpias,
        pronto=0,
        tarde=0,
        limpias=limpias,
        desfase_medio_s=0.0,
        tiene_acordes=False,
    )


def test_el_tempo_sube_tras_dos_pasadas_perfectas():
    """Dos pasadas PERFECTAS al 50 %: el tempo sugerido sube un paso, a 0,55.

    Es la regla del tempo recorrida por el camino de produccion entero: el audio
    entra por la cadena, el conductor cierra cada pasada, el historial apunta su
    proporcion y `factor_sugerido` decide. El historial se comparte entre las dos
    pasadas porque es lo que hace el servidor -uno por NOMBRE de pieza-, y sin eso
    la racha no existiria.

    Medido: proporcion 1,0 en las dos pasadas (al 50 % la ventana de acierto son
    160 ms y se come el temblor del onset), `factor_sugerido` None tras la primera
    y **0,55** tras la segunda.

    Las dos mitades hacen falta. La primera -None tras una sola pasada- es la que
    sujeta `PASADAS_BUENAS_PARA_SUBIR`: con el umbral en una pasada, el tempo
    subiria con la primera que saliera bien y esta prueba se quedaria verde si solo
    mirara la segunda.

    Y SIN BUCLE el factor no se aplica, se SUGIERE: `cerrar_lo_que_termino` lo
    publica en `factor_sugerido` y quien conduce lo aplicara al empezar la pasada
    siguiente, porque `cambiar_plan` con la pasada ya acabada arrancaria solo un
    bucle que nadie pidio. Por eso el plan sigue en 0,50.
    """
    historial = HistorialDeEstudio()
    factor = 0.50
    conductores = []
    for _ in range(PASADAS_BUENAS_PARA_SUBIR):
        interpretacion = interpretar(
            escala_de_ocho_notas(), PERFECTO, factor_tempo=factor, semilla=0
        )
        registro, conductor = _pasar(
            interpretacion,
            factor_tempo=factor,
            tempo_automatico=True,
            historial=historial,
        )
        assert [
            proporcion_limpia(informe) for informe in registro.vueltas
        ] == [pytest.approx(1.0)]
        conductores.append(conductor)

    assert historial.pasadas == PASADAS_BUENAS_PARA_SUBIR
    assert conductores[0].factor_sugerido is None, (
        "una sola pasada buena no mueve el tempo, y con "
        f"{PASADAS_BUENAS_PARA_SUBIR} hacen falta dos"
    )
    assert conductores[-1].factor_sugerido == pytest.approx(factor + PASO_DEL_FACTOR)
    assert conductores[-1].factor_sugerido == pytest.approx(0.55)
    assert conductores[-1].estudio.plan.factor_tempo == pytest.approx(factor), (
        "sin bucle el factor se sugiere, no se aplica: aplicarlo con la pasada ya "
        "acabada arrancaria un bucle que nadie pidio"
    )


def test_el_tempo_no_sube_con_una_pasada_mala():
    """Una pasada que falla la mitad de las notas: el tempo NO sube.

    El perfil se hace en la prueba (`probabilidad_de_fallo=0.5`) y medido con la
    semilla 0 falla exactamente la mitad: proporcion 0,50. Esta por debajo de
    `UMBRAL_PARA_BAJAR`, asi que el tempo BAJA un paso -a 0,45- sin esperar a la
    segunda pasada, que es lo que la regla dice: quien falla mucho no necesita
    confirmacion.

    Se afirma las dos cosas: que no sube -que es lo que el brief pide- y el numero
    exacto al que baja. Sin el numero, un historial que devolviera siempre el
    factor actual pasaria la prueba.
    """
    factor = 0.50
    malo = dataclasses.replace(PERFECTO, probabilidad_de_fallo=0.5)
    interpretacion = interpretar(
        escala_de_ocho_notas(), malo, factor_tempo=factor, semilla=0
    )
    historial = HistorialDeEstudio()
    registro, conductor = _pasar(
        interpretacion, factor_tempo=factor, tempo_automatico=True, historial=historial
    )

    assert len(registro.vueltas) == 1
    assert proporcion_limpia(registro.vueltas[-1]) == pytest.approx(0.5), (
        "el perfil falla la mitad de las notas y la proporcion tiene que decirlo"
    )
    assert conductor.factor_sugerido is not None
    assert conductor.factor_sugerido < factor, (
        f"con la mitad de las notas falladas el tempo no puede subir: sugirio "
        f"{conductor.factor_sugerido} desde {factor}"
    )
    assert conductor.factor_sugerido == pytest.approx(factor - PASO_DEL_FACTOR)


def test_el_tempo_no_sube_nunca_a_base_de_vueltas_de_bucle_malas():
    """Cuatro vueltas malas en bucle: el tempo baja y nunca sube.

    Es el caso que el defecto del bucle de la T7 hacia imposible de ver: con el
    reloj arrastrando, las vueltas se deformaban unas a otras y lo que se midiera
    de la cuarta no decia nada del guitarrista. Hoy las vueltas se cierran limpias
    y se puede afirmar la regla del tempo sobre ellas.

    CON bucle el factor se APLICA en el acto y no se sugiere -la vuelta siguiente
    empieza ya y el cabezal lo esta recolocando el propio bucle-, asi que lo que se
    mira es el plan. Medido con el perfil que falla la mitad: tres vueltas cerradas
    con proporciones 0,500 / 0,125 / 0,000, cada una por debajo del umbral de
    bajar, y el plan acaba en `FACTOR_MINIMO` (0,40) desde 0,50. Dos bajadas de un
    paso y la tercera ya no puede bajar mas, que es el suelo del deslizador.

    Las proporciones se afirman: sin ellas, un bucle que no cerrara ni una vuelta
    dejaria el plan quieto en 0,50 y la prueba del «no sube» pasaria sin haber
    medido nada.
    """
    factor = 0.50
    malo = dataclasses.replace(PERFECTO, probabilidad_de_fallo=0.5)
    interpretacion = interpretar(
        escala_de_ocho_notas(), malo, factor_tempo=factor, semilla=0, repeticiones=4
    )
    historial = HistorialDeEstudio()
    registro, conductor = _pasar(
        interpretacion,
        factor_tempo=factor,
        en_bucle=True,
        tempo_automatico=True,
        historial=historial,
    )

    assert len(registro.vueltas) == 3, (
        "cuatro vueltas de audio cierran tres informes -la cuarta se queda "
        f"abierta-; estas cerraron {len(registro.vueltas)}"
    )
    assert [
        round(proporcion_limpia(informe), 3) for informe in registro.vueltas
    ] == [0.5, 0.125, 0.0]
    assert historial.pasadas == 3
    assert conductor.estudio.plan.factor_tempo <= factor, (
        "ninguna racha de vueltas malas puede subir el tempo: el plan acabo en "
        f"{conductor.estudio.plan.factor_tempo} desde {factor}"
    )
    assert conductor.estudio.plan.factor_tempo == pytest.approx(FACTOR_MINIMO)
    assert conductor.factor_sugerido is None, (
        "con bucle el factor se aplica, no se sugiere"
    )
