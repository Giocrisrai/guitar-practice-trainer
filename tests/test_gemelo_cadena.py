# tests/test_gemelo_cadena.py
"""La cadena directa del gemelo: el audio recorriendo la ruta real en tiempo
virtual.

Ni un hilo ni una espera en todo el archivo, y eso no es una comodidad de las
pruebas: el reloj de la cadena sale de las MUESTRAS -el instante de cada ventana
es su final- y por eso una pasada de siete segundos de audio se recorre en la
suite en menos de un segundo. Una de las pruebas de abajo lee el propio archivo
fuente, con `ast` y no con `in`, para que siga siendo verdad.

Lo que se vigila aqui es que la cadena RECOJA lo que la cadena reporto, vuelta a
vuelta: el estado final solo conoce la ultima -`cerrar_repeticion` vacia el
seguidor en cada vuelta-, asi que un registro armado desde el estado final
perderia las tres primeras vueltas de un bucle de cuatro sin que nada se
quejara.

**Las tres decisiones de la cadena se afirman con doble, no con el estudio de
verdad**, y es la correccion de la primera ronda de revision: con el estudio
delante, mover el orden de `mirar` y `observar`, borrar la mirada final o fijar
la ventana a la de guitarra dejaba las once pruebas verdes. El `ConductorDeDoble`
anota POR ORDEN con que se le llama, y eso es lo que las hace falsables.
"""

import ast
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import INTERVALO_DE_ANALISIS_S, Analizador
from nucleo.gemelo.cadena import RegistroDeLaCadena, pasar_por_la_cadena
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.piezas.conductor import TECHO_TRAMO_S, ConductorDeEstudio
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from nucleo.piezas.seguimiento import NotaTocada

FS = 48000
GUITARRA = PERFILES["guitarra_estandar"]
BAJO = PERFILES["bajo_4"]
VENTANA = GUITARRA.tamano_ventana(FS)  # 4096 muestras, 85,3 ms
VENTANA_DEL_BAJO = BAJO.tamano_ventana(FS)  # 8192 muestras, 170,7 ms
SALTO_DE_PRODUCCION = 1008  # 21 ms a 48 kHz

FUENTE_DE_LA_CADENA = Path(__file__).resolve().parents[1] / "nucleo/gemelo/cadena.py"


# -- los instrumentos ---------------------------------------------------------


class _Carril:
    def __init__(self, tocadas=(), instante_s=0.0):
        self.tocadas = tocadas
        self.instante_s = instante_s


class _Estado:
    """Lo minimo que la cadena le lee a un estado: la vuelta y el carril."""

    def __init__(self, repeticion=1, tocadas=(), instante_s=0.0):
        self.repeticion = repeticion
        self.carril = _Carril(tocadas, instante_s)


class ConductorDeDoble:
    """Un conductor que no conduce nada: solo anota POR ORDEN con que se le llama.

    Lleva los cuatro metodos que la cadena usa -`fijar_la_mirada`, `mirar`,
    `observar` y `vueltas_cerradas`- y nada mas: si la cadena empieza a necesitar
    otra cosa del conductor, las pruebas que lo usan se rompen y se entera quien
    las lea.

    `llamadas` es la lista de `(nombre, instante)` en el orden en que ocurrieron,
    y es lo que hace falsables el ORDEN de las dos llamadas y la existencia de la
    mirada final. Sin ella, las dos decisiones centrales de la tarea no tenian
    ninguna prueba que las pudiera tumbar.
    """

    def __init__(self, pieza=None, estados=None):
        self.llamadas: list[tuple[str, float]] = []
        self.mirada_fijada: float | None = None
        self.vueltas_cerradas: tuple = ()
        # Los estados que `observar` va devolviendo, uno por cuadro. `None` es
        # «siempre el mismo estado vacio», que es lo que quieren las pruebas del
        # reloj.
        self._estados = list(estados) if estados is not None else None
        if pieza is not None:
            self.estudio = type("EstudioDeDoble", (), {"pieza": pieza})()

    @property
    def instantes_mirados(self) -> list[float]:
        return [cuando for nombre, cuando in self.llamadas if nombre == "mirar"]

    @property
    def instantes_observados(self) -> list[float]:
        return [cuando for nombre, cuando in self.llamadas if nombre == "observar"]

    def fijar_la_mirada(self, ahora):
        self.mirada_fijada = ahora

    def mirar(self, ahora, senal_ausente):
        self.llamadas.append(("mirar", ahora))
        return _Estado()

    def observar(self, resultado, instante_analisis):
        self.llamadas.append(("observar", instante_analisis))
        if self._estados is None:
            return _Estado()
        cuantos = len(self.instantes_observados) - 1
        return self._estados[min(cuantos, len(self._estados) - 1)]


class AnalizadorEspia:
    """Envuelve al analizador de verdad y anota el tamaño de cada ventana.

    Es lo que hace falsable el relleno de ceros: sin el, una cadena que entregara
    las cuatro ultimas ventanas cortas pasaba todas las pruebas.
    """

    def __init__(self, real: Analizador):
        self._real = real
        self.tamanos: list[int] = []

    @property
    def tamano_ventana(self):
        return self._real.tamano_ventana

    @property
    def frecuencia_muestreo(self):
        return self._real.frecuencia_muestreo

    def procesar(self, muestras):
        self.tamanos.append(len(muestras))
        return self._real.procesar(muestras)


def pieza_de_bajo():
    """Una pieza con `perfil = "bajo_4"`, cuya ventana es el DOBLE de la estandar.

    Es la pieza que hace falsable que la ventana salga del perfil de la pieza, y
    tambien la que prueba el techo del tramo: 8192 muestras son 0,1707 s, muy por
    encima de `TECHO_TRAMO_S`.
    """
    notas = tuple(
        NotaEnPieza(
            midi=40 + indice, cuerda=4, traste=indice, inicio_pulsos=float(indice),
            duracion_pulsos=1.0,
        )
        for indice in range(4)
    )
    return Pieza(
        nombre="Pieza de bajo", perfil="bajo_4", tempo=100, compas=(4, 4), notas=notas
    )


def un_segundo_de_audio(pieza=None):
    """Una interpretacion de exactamente FS muestras, para contar cuadros."""
    return Interpretacion(
        pieza=pieza or escala_de_ocho_notas(),
        muestras=np.zeros(FS, dtype=np.float32),
        eventos=(),
        frecuencia_muestreo=FS,
        duracion_s=1.0,
        silencio_de_cabecera_s=0.0,
    )


def bucle_de_un_compas(repeticiones=3, tempo=100):
    """Interpretacion PERFECTA del primer compas, con su conductor en bucle.

    El tramo es un compas de cuatro notas -`escala_de_ocho_notas` trae dos- y el
    plan lo repite, que es el caso que esta tarea existe para poder afirmar: con
    tres vueltas, el estado final solo conoce la tercera.
    """
    pieza = escala_de_ocho_notas(tempo=tempo)
    interpretacion = interpretar(
        pieza,
        PERFECTO,
        primer_compas=1,
        ultimo_compas=1,
        repeticiones=repeticiones,
        frecuencia_muestreo=FS,
    )
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(
            primer_compas=1,
            ultimo_compas=1,
            en_bucle=True,
            compases_de_cuenta_atras=0,
        ),
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    return interpretacion, conductor


def conductor_de_verdad(pieza=None, plan=None):
    pieza = pieza or escala_de_ocho_notas()
    estudio = SesionDeEstudio(pieza, plan or PlanDePasada(compases_de_cuenta_atras=0))
    estudio.arrancar()
    return ConductorDeEstudio(estudio, al_cambiar_repeticion=None)


def llamadas_de_los_cuadros(doble: ConductorDeDoble) -> list[tuple[str, float]]:
    """Las llamadas de `doble` fechadas en un instante de cuadro, en orden.

    Deja fuera las miradas que llenan la primera ventana, que caen en multiplos
    del salto y nunca coinciden con un instante de cuadro (el cuadro va desplazado
    por la ventana, que no es multiplo del salto).
    """
    instantes = set(doble.instantes_observados)
    return [llamada for llamada in doble.llamadas if llamada[1] in instantes]


# -- el reloj -----------------------------------------------------------------


def test_el_instante_de_cada_ventana_es_su_final():
    """El primero es `ventana / fs`, y de ahi en adelante un salto cada vez.

    Es la convencion que la spec §3.4 MIDIO con una sonda: principio de la
    ventana da -78,7 ms de error, centro -36,0 ms y final +6,7 ms, que es la
    latencia propia del detector y debe aparecer. Con el centro, el gemelo
    acusaria a la cadena de adelantar cada nota 36 ms y toda asercion de desfase
    quedaria corrupta.
    """
    doble = ConductorDeDoble()
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)

    pasar_por_la_cadena(un_segundo_de_audio(), doble, analizador=analizador)

    instantes = doble.instantes_observados
    # La guarda es por LO BAJO y con dos: con un solo cuadro, la asercion de las
    # diferencias compara una lista vacia y pasa sin mirar nada.
    assert len(instantes) >= 2, f"la cadena observo {len(instantes)} cuadros"
    assert instantes[0] == pytest.approx(VENTANA / FS), (
        "el primer instante tiene que ser el FINAL de la primera ventana "
        f"({VENTANA / FS:.4f} s), no su centro ni su principio"
    )
    diferencias = np.diff(instantes)
    assert diferencias == pytest.approx(SALTO_DE_PRODUCCION / FS), (
        "entre dos cuadros consecutivos hay exactamente un salto"
    )


def test_la_mirada_se_fija_en_el_origen_del_audio():
    """El reloj virtual arranca en la muestra cero, y la cadena lo dice.

    Sin fijarla, el conductor que venga con una mirada puesta en el reloj de
    pared del servidor contaria un tramo de miles de segundos en su primera
    mirada.
    """
    doble = ConductorDeDoble()
    pasar_por_la_cadena(
        un_segundo_de_audio(), doble, analizador=Analizador(GUITARRA, frecuencia_muestreo=FS)
    )
    assert doble.mirada_fijada == 0.0


def test_cada_cuadro_se_mira_antes_de_observarse():
    """`mirar` va DELANTE de `observar`, y con el mismo instante.

    No es estetica. `observar` toma su reloj de pared de la ULTIMA MIRADA, y sin
    ninguna mirada hecha cae a `instante_analisis` y entra por `_sin_cuadros`
    congelando el reloj: la ventana entera que tarda en llenarse el primer cuadro
    no entraba nunca en la pieza. Es ademas el contrato que el docstring de
    `ConductorDeEstudio.observar` fija: «quien conduce mira y en seguida observa
    con el mismo instante».

    Esta prueba existe porque invertir las dos llamadas dejaba verdes las once
    pruebas de la primera entrega.
    """
    doble = ConductorDeDoble()
    pasar_por_la_cadena(
        un_segundo_de_audio(), doble, analizador=Analizador(GUITARRA, frecuencia_muestreo=FS)
    )

    llamadas = llamadas_de_los_cuadros(doble)
    for posicion, (nombre, cuando) in enumerate(llamadas):
        if nombre != "observar":
            continue
        assert posicion > 0 and llamadas[posicion - 1] == ("mirar", cuando), (
            f"el cuadro de {cuando:.4f} s se observo sin mirar antes: "
            f"{llamadas[max(0, posicion - 1) : posicion + 1]}"
        )


def test_la_cadena_acaba_con_una_mirada_sin_cuadro():
    """La ultima llamada es una mirada, y repite el instante del ultimo cuadro.

    Es la que cierra lo que el ultimo cuadro dejo terminado: el cierre de vueltas
    vive en `mirar` y mira la transicion que el cuadro ANTERIOR provoco, asi que
    sin esta mirada lo que termina el ultimo cuadro no lo cierra nadie. Repite el
    instante en vez de inventarse uno nuevo porque la cadena no tiene mas tiempo
    que el que hay en las muestras.

    Esta prueba existe porque borrar la mirada final dejaba verdes las once
    pruebas de la primera entrega.
    """
    doble = ConductorDeDoble()
    pasar_por_la_cadena(
        un_segundo_de_audio(), doble, analizador=Analizador(GUITARRA, frecuencia_muestreo=FS)
    )

    nombre, cuando = doble.llamadas[-1]
    assert nombre == "mirar", f"la cadena acabo en `{nombre}` y no en una mirada"
    assert cuando == doble.instantes_observados[-1]
    cuadros = len(doble.instantes_observados)
    assert len(llamadas_de_los_cuadros(doble)) == 2 * cuadros + 1, (
        "una mirada y un cuadro por ventana, mas la mirada final"
    )


def test_el_tramo_que_acaba_en_el_ultimo_cuadro_se_cierra_igual():
    """Si el ULTIMO cuadro es el que termina el tramo, la mirada final lo cierra.

    Es la consecuencia observable de la mirada final, y no un caso rebuscado: un
    audio que se acaba donde se acaba el tramo es lo que entrega un dispositivo
    que para al terminar la pieza. `observar` no cierra nada, asi que el informe
    de esa pasada dependeria entera de una mirada que ya no iba a llegar.

    El audio se corta en 227000 muestras (4,729 s) a proposito: el tramo acaba en
    4,8 s y el ultimo cuadro cae en 4,8103 s, que es el PRIMERO que lo pasa. Con
    una muestra menos de la cuenta -225 cuadros, 4,7893 s- el tramo no acaba y no
    hay nada que cerrar, y esa es la frontera que hace la prueba exacta.
    """
    pieza = escala_de_ocho_notas()
    entera = interpretar(pieza, PERFECTO, frecuencia_muestreo=FS)
    justo = replace(
        entera, muestras=entera.muestras[:227000], duracion_s=227000 / FS
    )
    corta = replace(
        entera, muestras=entera.muestras[:226000], duracion_s=226000 / FS
    )

    cerrada = pasar_por_la_cadena(justo, conductor_de_verdad(pieza))
    abierta = pasar_por_la_cadena(corta, conductor_de_verdad(pieza))

    assert cerrada.estado_final.tramo_terminado is True
    assert len(cerrada.vueltas) == 1, (
        "el tramo acabo en el ultimo cuadro y su informe tiene que estar cerrado"
    )
    assert abierta.estado_final.tramo_terminado is False
    assert abierta.vueltas == (), "sin tramo acabado no hay nada que cerrar"


def test_ninguna_mirada_se_traga_mas_del_techo_del_tramo():
    """Entre dos miradas no pasa nunca mas de `TECHO_TRAMO_S`, ni al arrancar.

    `mover_el_reloj` acota lo que entra en la pieza por cada aviso a 0,100 s y lo
    acota SIEMPRE, sin excepciones. Con una sola mirada para toda la primera
    ventana, el techo MORDIA: `PERFILES["bajo_4"].tamano_ventana(48000)` son 8192
    muestras, o sea 0,1707 s, asi que con cualquier pieza de bajo el cabezal
    arrancaba 71 ms corto y en silencio. Por eso la ventana se llena con varias
    miradas, que es lo que pasa en produccion (el WebSocket mira a 30 Hz mientras
    el primer cuadro se llena).
    """
    doble = ConductorDeDoble(pieza=pieza_de_bajo())

    pasar_por_la_cadena(un_segundo_de_audio(pieza_de_bajo()), doble)

    # Desde el origen del reloj, que es donde quedo fijada la mirada.
    miradas = [0.0, *doble.instantes_mirados]
    huecos = np.diff(miradas)
    assert huecos.max() <= TECHO_TRAMO_S + 1e-9, (
        f"una mirada tendria que tragarse {huecos.max():.4f} s y el techo son "
        f"{TECHO_TRAMO_S} s: lo que pase de ahi no entra en la pieza"
    )


def test_el_salto_por_omision_es_el_de_produccion():
    """`salto=None` es 21 ms, no 48000/512.

    Las constantes del detector estan acopladas a esos 21 ms
    (`CUADROS_PARA_NOTA_ESTABLE = 3` son 63 ms a 21 ms y 32 ms a 10,7 ms, y
    `nucleo/ejercicios/pulsaciones.py` advierte por escrito de ello), asi que
    recorrer el audio a otra cadencia es ejercitar un detector que nunca corre.
    """
    doble = ConductorDeDoble()
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)

    pasar_por_la_cadena(un_segundo_de_audio(), doble, analizador=analizador)

    cuadros = len(doble.instantes_observados)
    esperados = round(1.0 / INTERVALO_DE_ANALISIS_S)
    assert abs(cuadros - esperados) <= 1, (
        f"un segundo de audio son {esperados} cuadros de 21 ms, no {cuadros}"
    )
    assert cuadros != FS // 512, "512 es el salto de la sonda, no el de produccion"


# -- la ventana ---------------------------------------------------------------


def test_la_ventana_sale_del_perfil_de_la_pieza():
    """Sin analizador, la ventana es la del perfil DE LA PIEZA, no la estandar.

    `Pieza.perfil` es una CLAVE de `PERFILES` y de ese perfil sale la ventana
    (`perfil.tamano_ventana(fs)`): 4096 muestras con guitarra y 8192 con un bajo,
    porque una cuerda de bajo necesita el doble de muestras para que quepan los
    mismos periodos. Una cadena que fijara la de guitarra haria leer al detector
    la mitad de los periodos que lee en produccion con cualquier pieza de bajo.

    Se comprueba por el PRIMER INSTANTE, que es `ventana / fs` y por tanto la
    delata: 0,1707 s con el bajo contra 0,0853 s con la guitarra.
    """
    con_bajo = ConductorDeDoble(pieza=pieza_de_bajo())
    con_guitarra = ConductorDeDoble(pieza=escala_de_ocho_notas())

    pasar_por_la_cadena(un_segundo_de_audio(pieza_de_bajo()), con_bajo)
    pasar_por_la_cadena(un_segundo_de_audio(), con_guitarra)

    assert con_bajo.instantes_observados[0] == pytest.approx(VENTANA_DEL_BAJO / FS)
    assert con_guitarra.instantes_observados[0] == pytest.approx(VENTANA / FS)
    assert VENTANA_DEL_BAJO == 2 * VENTANA, "si esto cambia, la prueba ya no distingue"


def test_todas_las_ventanas_llegan_completas_al_analizador():
    """Ni una ventana corta, tampoco las de la cola del audio.

    El recorrido llega hasta la ultima ventana que EMPIEZA dentro del audio, no
    hasta la ultima que cabe entera, y las que se salen se rellenan con ceros. Es
    lo que pasa en vivo -el audio se acaba y los cuadros siguen llegando- y es lo
    que hace que los cuatro ultimos cuadros existan: son justo los que resuelven
    el ataque de la ultima nota del tramo. Sin relleno, el detector recibiria esas
    cuatro ventanas cortas y leeria menos periodos de los que lee en produccion.
    """
    doble = ConductorDeDoble()
    espia = AnalizadorEspia(Analizador(GUITARRA, frecuencia_muestreo=FS))

    pasar_por_la_cadena(un_segundo_de_audio(), doble, analizador=espia)

    assert set(espia.tamanos) == {VENTANA}, (
        f"llegaron ventanas de {sorted(set(espia.tamanos))} muestras y todas tienen "
        f"que ser de {VENTANA}"
    )
    assert len(espia.tamanos) == len(doble.instantes_observados)


# -- el registro --------------------------------------------------------------


def test_el_registro_guarda_las_notas_de_todas_las_vueltas():
    """Las tres vueltas aparecen en los reportes, aunque el estado final no.

    `cerrar_repeticion` vacia el seguidor en cada vuelta, asi que al acabar las
    tres el estado final solo conoce la ultima: si la cadena no recogiera los
    reportes al pasar, las dos primeras vueltas no existirian en ninguna parte.
    """
    interpretacion, conductor = bucle_de_un_compas(repeticiones=3)

    registro = pasar_por_la_cadena(interpretacion, conductor)

    vueltas_reportadas = {reporte.repeticion for reporte in registro.reportes}
    assert vueltas_reportadas == {1, 2, 3}, (
        f"se reporto en las vueltas {sorted(vueltas_reportadas)}, y el bucle dio tres"
    )
    # La CUARTA vuelta se abre, y el numero es exacto, no «al menos tres»: el
    # tramo son 2,4 s (cuatro pulsos a 100 ppm) y el audio dura 7,328 s, o sea
    # tres tramos MAS los 0,128 s de silencio de cabecera que `interpretar` pone
    # delante (`VENTANAS_DE_CABECERA = 1,5`). Esa cola de 128 ms cae ya en la
    # cuarta vuelta. Si alguien mueve la cabecera, esta prueba falla, y falla por
    # el motivo correcto.
    assert interpretacion.duracion_s == pytest.approx(3 * 2.4 + 0.128, abs=1e-3)
    assert registro.estado_final.repeticion == 4


def test_el_registro_guarda_un_informe_por_vuelta_cerrada():
    """Tres informes, y la razon es que el bucle dio TRES vueltas, no que haya
    tres repeticiones de audio.

    Una vuelta se cierra AL DAR LA SIGUIENTE (`_dar_la_vuelta` guarda su informe y
    `mirar` lo anota al ver cambiar `repeticion`), asi que tres informes exigen
    tres transiciones: 1→2, 2→3 y 3→4. La tercera transicion solo ocurre porque
    los 0,128 s de silencio de cabecera hacen que el audio dure mas que los tres
    tramos; sin esa cola, la tercera vuelta se quedaria ABIERTA y aqui habria dos
    informes. No es «un informe por repeticion de audio»: es un informe por
    vuelta cerrada, que es otra cosa y es la que el nombre dice.

    El cierre de vueltas vive en `mirar`, NO en `observar`: una cadena que solo
    observara dejaria `vueltas_cerradas` vacio y esto saldria a cero.
    """
    interpretacion, conductor = bucle_de_un_compas(repeticiones=3)

    registro = pasar_por_la_cadena(interpretacion, conductor)

    assert len(registro.vueltas) == len(conductor.vueltas_cerradas)
    assert len(registro.vueltas) == 3
    assert registro.estado_final.repeticion == 4, (
        "tres informes son tres transiciones, y la tercera deja la vuelta cuatro abierta"
    )
    assert all(informe.repeticiones == 1 for informe in registro.vueltas), (
        "cada informe es el de SOLO esa vuelta, no el acumulado"
    )


def test_no_se_reporta_la_misma_nota_dos_veces():
    interpretacion, conductor = bucle_de_un_compas(repeticiones=3)

    registro = pasar_por_la_cadena(interpretacion, conductor)

    claves = [(reporte.repeticion, reporte.tocada.indice) for reporte in registro.reportes]
    assert len(claves) == len(set(claves)), (
        f"hay notas reportadas dos veces en la misma vuelta: {claves}"
    )


def test_la_misma_nota_en_dos_vueltas_son_dos_reportes():
    """La deduplicacion es POR VUELTA, y con un conductor de guion se demuestra.

    Los indices se repiten vuelta a vuelta: la nota 2 de la vuelta 3 es un reporte
    distinto de la nota 2 de la vuelta 1. Con un conjunto global de vistas, una
    vuelta que repitiera una `NotaTocada` identica a la de la vuelta anterior
    desapareceria del registro, y el veredicto la daria por perdida sin que la
    cadena la hubiera perdido.

    Hace falta el guion porque con el estudio de verdad dos vueltas nunca dan una
    `NotaTocada` identica -los cents y el desfase son flotantes y el interprete
    usa una semilla por vuelta-, asi que la dedup global pasaba todas las pruebas.
    """
    la_misma = NotaTocada(
        indice=2, midi=59, cents=0.0, desfase_s=0.01, clasificacion="a_tiempo",
        acertada=True, afinada=True,
    )
    doble = ConductorDeDoble(
        estados=[
            _Estado(repeticion=1, tocadas=(la_misma,), instante_s=1.0),
            _Estado(repeticion=1, tocadas=(la_misma,), instante_s=1.1),
            _Estado(repeticion=2, tocadas=(la_misma,), instante_s=0.2),
            _Estado(repeticion=2, tocadas=(la_misma,), instante_s=0.3),
        ]
    )
    interpretacion = un_segundo_de_audio()

    registro = pasar_por_la_cadena(
        interpretacion, doble, analizador=Analizador(GUITARRA, frecuencia_muestreo=FS)
    )

    assert [reporte.repeticion for reporte in registro.reportes] == [1, 2], (
        "la misma nota en dos vueltas son dos reportes, y dentro de una vuelta uno"
    )
    assert [reporte.instante_pasada_s for reporte in registro.reportes] == [1.0, 0.2], (
        "cada reporte lleva el reloj de la pasada de cuando se vio por primera vez"
    )


def test_el_registro_es_de_esta_pasada_y_no_de_la_anterior():
    """Conducir dos veces el mismo conductor no mete las vueltas viejas en el
    registro nuevo.

    `vueltas_cerradas` es acumulativo y vive en el conductor, no en la pasada: el
    escaparate conduce el mismo conductor varias veces, y un registro que
    devolviera la tupla entera le atribuiria a la segunda pasada los informes de
    la primera.
    """
    interpretacion, conductor = bucle_de_un_compas(repeticiones=3)

    primero = pasar_por_la_cadena(interpretacion, conductor)
    segundo = pasar_por_la_cadena(interpretacion, conductor)

    assert len(primero.vueltas) + len(segundo.vueltas) == len(conductor.vueltas_cerradas)
    assert segundo.vueltas == conductor.vueltas_cerradas[len(primero.vueltas) :]
    assert len(segundo.vueltas) < len(conductor.vueltas_cerradas), (
        "la segunda pasada no puede devolver tambien las vueltas de la primera"
    )


# -- los casos de borde y las reglas del modulo -------------------------------


def _importados_y_nombrados(ruta: Path) -> tuple[set[str], set[str]]:
    """Los modulos que importa el archivo y los nombres y atributos que usa.

    Con `ast` y no con `in`, que es la leccion de la Tarea 3: una comprobacion
    textual la burla `from time import sleep` -no aparece la cadena `time.sleep`-
    y la rompe un comentario que mencione `threading` sin que nada este mal. Una
    prueba que opina sobre la prosa es una prueba que alguien acabara silenciando.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    usados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                modulos.add(alias.name.split(".")[0])
                usados.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(nodo, ast.ImportFrom) and nodo.module is not None:
            modulos.add(nodo.module.split(".")[0])
            usados |= {alias.asname or alias.name for alias in nodo.names}
        elif isinstance(nodo, ast.Attribute):
            usados.add(nodo.attr)
        elif isinstance(nodo, ast.Name):
            usados.add(nodo.id)
    return modulos, usados


def test_la_cadena_no_abre_hilos_ni_duerme():
    """El reloj es virtual y sale de las muestras: no hay nada que esperar.

    Es la condicion de que la cadena directa se pueda correr en la suite, que es
    a su vez la condicion de que se corra. Si algun dia hace falta un hilo o una
    espera, eso es el nivel de sesion completa y vive en otro modulo.
    """
    modulos, usados = _importados_y_nombrados(FUENTE_DE_LA_CADENA)

    for modulo in ("threading", "time", "asyncio", "concurrent"):
        assert modulo not in modulos, (
            f"la cadena importa `{modulo}`: su reloj sale de las muestras"
        )
    for nombre in ("sleep", "monotonic", "perf_counter", "Thread", "wait"):
        assert nombre not in usados, (
            f"la cadena usa `{nombre}`: su reloj sale de las muestras"
        )


def test_una_interpretacion_de_silencio_no_reporta_nada():
    """Audio de ceros: ni un reporte y ni una excepcion.

    Las dos aserciones de la cola son lo que distingue «la cadena paso y no
    reporto» de «la cadena no paso»: un cuerpo vacio tambien devolveria reportes
    vacios. El analizador recibio sus 48 cuadros y el reloj de la pasada avanzo
    con ellos.
    """
    conductor = conductor_de_verdad()
    espia = AnalizadorEspia(Analizador(GUITARRA, frecuencia_muestreo=FS))

    registro = pasar_por_la_cadena(
        un_segundo_de_audio(), conductor, analizador=espia
    )

    assert isinstance(registro, RegistroDeLaCadena)
    assert registro.reportes == ()
    cuadros = len(espia.tamanos)
    assert cuadros == round(1.0 / INTERVALO_DE_ANALISIS_S)
    # El reloj de la pasada acaba en el FINAL DE LA ULTIMA VENTANA, 1:1 con el
    # reloj virtual: es la alineacion de la que cuelga todo el veredicto, porque
    # el desfase que la T5 va a medir es la diferencia entre este reloj y el
    # instante del ataque. Si la cadena se dejara por el camino los 85 ms de la
    # primera ventana, o los metiera dos veces, esta cuenta no cuadraria.
    ultima_ventana_s = ((cuadros - 1) * SALTO_DE_PRODUCCION + VENTANA) / FS
    assert registro.estado_final.carril.instante_s == pytest.approx(
        ultima_ventana_s, abs=1e-6
    ), "el cabezal avanza con los cuadros aunque no suene nada, y 1:1 con ellos"


def test_un_audio_vacio_no_lanza():
    """Cero muestras es un caso de borde, no un error: el registro sale vacio.

    Y el reloj NO se mueve: sin un solo cuadro no hay ventana que llenar, asi que
    tampoco hay miradas que la llenen.
    """
    conductor = conductor_de_verdad()
    interpretacion = Interpretacion(
        pieza=escala_de_ocho_notas(),
        muestras=np.zeros(0, dtype=np.float32),
        eventos=(),
        frecuencia_muestreo=FS,
        duracion_s=0.0,
        silencio_de_cabecera_s=0.0,
    )

    registro = pasar_por_la_cadena(interpretacion, conductor)

    assert registro.reportes == ()
    assert registro.vueltas == ()
    assert registro.estado_final.carril.instante_s == pytest.approx(0.0)


def test_un_analizador_con_otra_frecuencia_es_un_error_claro():
    doble = ConductorDeDoble()
    analizador = Analizador(GUITARRA, frecuencia_muestreo=44100)

    with pytest.raises(ValueError, match="44100"):
        pasar_por_la_cadena(un_segundo_de_audio(), doble, analizador=analizador)


def test_un_salto_que_no_avanza_es_un_error_claro():
    """Salto cero es un bucle infinito, y se dice en vez de colgarse."""
    doble = ConductorDeDoble()
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)

    with pytest.raises(ValueError, match="salto"):
        pasar_por_la_cadena(
            un_segundo_de_audio(), doble, analizador=analizador, salto=0
        )
