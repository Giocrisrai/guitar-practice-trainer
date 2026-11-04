"""La cadena directa: el audio del gemelo recorriendo la ruta real en tiempo virtual.

El camino rapido, el que corre en la suite. No abre audio, no abre hilos y no
espera nada: **el reloj sale de las muestras**. El instante de cada ventana es su
final, y entre dos ventanas pasa exactamente un salto; nueve segundos de audio se
recorren en menos de un segundo de reloj de pared, y eso es la condicion de que
la cadena directa se corra en cada suite y no una vez al mes a mano.

Lo que recorre es la RUTA DE PRODUCCION, sin atajos: el `Analizador` de verdad,
el `ConductorDeEstudio` de verdad y la `SesionDeEstudio` de verdad. Lo unico
simulado es el cable. Un gemelo que reimplementase cualquiera de esas tres
piezas estaria verificando una copia paralela y se daria la razon a si mismo.

EL INSTANTE DE CADA VENTANA ES SU FINAL, y esto esta MEDIDO, no razonado. En vivo
el cuadro se entrega cuando el ultimo bloque acaba de llegar: la ventana termina
en «ahora». Una sonda de la spec §3.4 midio el error entre el ataque real y el
que firma el detector con las tres convenciones, sobre ocho notas sinteticas:

    principio de la ventana   -78,7 ms
    centro de la ventana      -36,0 ms
    final de la ventana       +6,7 ms

El +6,7 ms es la latencia propia del detector, que es real y debe aparecer. Los
-36 ms del centro son un sesgo inventado por la convencion: un gemelo construido
sobre el centro habria acusado a la cadena de adelantar cada nota 36 ms, y
cualquier asercion de desfase habria estado corrupta.

Y EL CABEZAL NO CORRE DURANTE LA CABECERA TECNICA DEL GEMELO. El instante de cada
cuadro es el final de su ventana MENOS ese silencio, asi que el cabezal marca cero
cuando suena la nota que la pieza escribe en cero. Es una decision de diseño y no
una medida: la cabecera es un requisito del gemelo -que la primera ventana de
analisis llegue completa-, no tiempo musical, igual que al usuario no se le cobra
el tiempo que el buffer tarda en llenarse.

Lo que se arregla con ello esta medido. Con el cabezal arrancando en la muestra
cero, los desfases que el seguidor firmaba sobre una interpretacion PERFECTA eran

    +148,3  +136,3  +166,3  +217,3  +163,3  +193,3  +139,3  +148,3   ms

contra una ventana de acierto de 80 ms: las OCHO notas «tarde» y cero limpias. El
primer sumando de cada una son los 128 ms de cabecera. Descontados, quedan

    +20,3   +8,3   +38,3   +89,3   +35,3   +65,3   +11,3   +20,3    ms

y salen SIETE limpias de ocho. La que queda fuera, la nota 3 con 89,3 ms, es el
temblor del propio detector de ataques, no la cabecera: esa es otra discusion -si
la clasificacion debe cobrarle al alumno la latencia que el detector sabe que
añade- y no se decide aqui.

El descuento nunca es menor que una ventana, para que una interpretacion armada a
mano sin cabecera -un buffer de silencio de una prueba- tampoco pague el llenado
del primer cuadro. Eso es lo que hizo innecesario el relleno de miradas que la T4
puso aqui: un reloj que no avanza no se puede quedar corto contra el techo de
`mover_el_reloj`, que es lo que le pasaba al perfil de bajo (ventana de 171 ms
contra un techo de 100).

POR QUE EL REGISTRO Y NO EL ESTADO FINAL. `EstadoCarril.tocadas` solo trae lo que
el seguidor lleva sin volcar, y `cerrar_repeticion` lo vacia en cada vuelta: al
acabar cuatro repeticiones, el estado final solo conoce la ultima. Y los indices
se repiten vuelta a vuelta, asi que «se perdio la nota 11» no distingue «en la
vuelta 3» de «en todas». El registro se recoge MIENTRAS la cadena pasa, que es el
unico momento en que esa informacion existe.
"""

from dataclasses import dataclass

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import INTERVALO_DE_ANALISIS_S, Analizador
from nucleo.gemelo.interprete import Interpretacion
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import EstadoEstudio, InformeDePasada
from nucleo.piezas.seguimiento import NotaTocada

# El salto por omision es el de PRODUCCION, y sale de `nucleo.analisis.pipeline`,
# que es donde vive la cadencia del analisis: la misma constante que alimenta el
# hilo de trabajo del servidor alimenta esta cadena, que es la unica forma de que
# el gemelo verifique la cadencia que produccion usa de verdad.
#
# NO es negociable, y 512 muestras no sirven aunque sean mas rapidas: las
# constantes del detector estan acopladas a estos 21 ms
# -`CUADROS_PARA_NOTA_ESTABLE = 3` son 63 ms a 21 ms y 32 ms a 10,7 ms, y
# `nucleo/ejercicios/pulsaciones.py` advierte por escrito de que quien cambie la
# tasa de analisis tiene que revisarlas-, asi que recorrer el audio a otra
# cadencia es ejercitar un detector que nunca corre. Las sondas del diseño usaron
# un salto de 512 y por eso sus numeros son indicativos y no de referencia.


@dataclass(frozen=True)
class ReporteDeLaCadena:
    """Una `NotaTocada` tal y como la cadena la publico, con su vuelta.

    `instante_pasada_s` es el reloj de la PASADA cuando el reporte se vio por
    primera vez, no el de la ventana: es lo que el carril estaba pintando en ese
    momento, que es contra lo que el veredicto compara.
    """

    repeticion: int
    tocada: NotaTocada
    instante_pasada_s: float


@dataclass(frozen=True)
class RegistroDeLaCadena:
    """TODO lo que la cadena reporto, vuelta a vuelta, sin perder nada.

    `vueltas` son los informes que el conductor CERRO durante esta pasada, en
    orden y uno por cierre. La ultima vuelta de un bucle suele quedarse fuera, y
    no es un defecto: el audio se acaba antes de que el bucle de la vuelta, asi
    que esa vuelta sigue abierta y nadie la ha cerrado. Inventarle un cierre seria
    anotar una vuelta que el conductor no anoto.
    """

    reportes: tuple[ReporteDeLaCadena, ...]
    vueltas: tuple[InformeDePasada, ...]
    estado_final: EstadoEstudio


def pasar_por_la_cadena(
    interpretacion: Interpretacion,
    conductor: ConductorDeEstudio,
    analizador: Analizador | None = None,
    salto: int | None = None,
) -> RegistroDeLaCadena:
    """Mete el audio de `interpretacion` por la cadena y devuelve lo que reporto.

    Parametros:
        interpretacion: el audio y la verdad de lo que sono. Solo se leen las
            muestras y la frecuencia de muestreo; la verdad es del veredicto.
        conductor: el conductor del estudio, YA ARRANCADO por quien lo construyo
            (`SesionDeEstudio.arrancar`) y con `al_cambiar_repeticion=None`: ese
            aviso existe para que el servidor rearranque el click, y el click abre
            audio. La cadena directa no tiene click.
        analizador: el de produccion si no se da, construido con el perfil de la
            pieza del conductor. Su frecuencia de muestreo tiene que ser la de la
            interpretacion, porque de ella sale la ventana.
        salto: muestras entre dos ventanas. `None` es el de produccion, 21 ms
            (1008 muestras a 48 kHz). Ver `INTERVALO_DE_ANALISIS_S`.

    Lanza `ValueError` si el analizador no trabaja a la frecuencia de la
    interpretacion o si el salto no es positivo.

    UN `salto` DE MAS DE `ESPERA_SIN_CUADROS_S` (0,25 s, unas 12000 muestras a
    48 kHz) NO RECORRE LA MISMA CADENA, y no se impide porque no es un error sino
    otra cosa: el conductor lo lee como un HUECO DE AUDIO -`_hueco_de_audio` mide
    exactamente ese umbral en el reloj del analisis- y en cada cuadro le recoloca
    el reloj al estudio con `congelar_en` antes de darle de comer. El cabezal
    deja entonces de avanzar con el audio y la pasada se queda clavada. Quien
    quiera medir asi tiene que saber que esta midiendo el camino del apagon, no
    el del audio; para eso el techo practico del salto es `ESPERA_SIN_CUADROS_S`.
    """
    frecuencia = interpretacion.frecuencia_muestreo
    analizador = _analizador_de(analizador, conductor, frecuencia)
    ventana = analizador.tamano_ventana
    paso = round(INTERVALO_DE_ANALISIS_S * frecuencia) if salto is None else salto
    if paso < 1:
        raise ValueError(f"El salto {paso} no sirve: tiene que ser de al menos una muestra")

    muestras = interpretacion.muestras
    # EL ORIGEN DEL EJE DEL CABEZAL ES EL FINAL DE LA CABECERA TECNICA, no la
    # muestra cero, y de aqui cuelga todo lo que la cadena le cuenta al estudio.
    #
    # La cabecera tecnica -el silencio que `interpretar` mete delante de la
    # primera nota- NO ES TIEMPO MUSICAL: es un requisito del gemelo para que la
    # primera ventana de analisis llegue completa. Con el cabezal arrancando en la
    # muestra cero, ese silencio se le cobraba al interprete: el guitarrista
    # PERFECTO tocaba 128 ms tarde por construccion, el seguidor clasificaba las
    # ocho notas como «tarde» y el oraculo sacaba 0 limpias de 8. Un gemelo
    # estructuralmente tarde no es un oraculo, es un interprete tarde, y entonces
    # lo que la cadena diga de el ya no distingue un defecto de la cadena.
    #
    # Al usuario tampoco se le cobra: en produccion la pasada empieza cuando hay
    # audio que analizar, no cuando el buffer empieza a llenarse.
    #
    # El desplazamiento es la cabecera TECNICA y no el silencio de cabecera
    # entero: la cuenta atras si es tiempo de la pasada -el estudio la modela,
    # congelando el cabezal mientras dura-, asi que descontarla aqui la contaria
    # dos veces. Y nunca es menor que una ventana, para que una interpretacion
    # armada a mano sin cabecera -un buffer de silencio de una prueba- tampoco
    # tenga que tragarse el llenado de la primera ventana en la primera mirada:
    # con el perfil de bajo eso eran 171 ms contra el techo de 100 ms de
    # `mover_el_reloj`, que es el defecto que la T4 arreglaba con un relleno de
    # miradas. Ese relleno se ha ido: sin reloj corriendo durante el llenado, no
    # hay nada que rellenar.
    #
    # EL MINIMO DE UNA VENTANA NO ES LA ALINEACION: la ventana esta dentro del
    # `max` solo como suelo para las interpretaciones sin cabecera. Alinear al
    # final de la PRIMERA VENTANA (85,3 ms) en vez del final de la cabecera
    # (128 ms) es otra cosa, se considero y se descarto con la medida: dejaba
    # 42,7 ms de deuda en todas las notas, el suelo subia a +195,0 ms de mediana y
    # +231,0 de maximo -a 19 ms del techo del detector- y el oraculo sacaba 5
    # notas limpias de 8 en vez de 7.
    cabecera_tecnica_s = max(
        0.0,
        interpretacion.silencio_de_cabecera_s - interpretacion.segundos_de_cuenta_atras,
    )
    desplazamiento_s = max(cabecera_tecnica_s, ventana / frecuencia)

    # La mirada se fija en el origen del eje del cabezal. Hace falta fijarla
    # porque el conductor que llegue con una mirada puesta en el reloj de pared
    # -el servidor la fija al arrancar la pasada- contaria en su primera mirada un
    # tramo de miles de segundos, o de miles negativos.
    conductor.fijar_la_mirada(0.0)

    reportes: list[ReporteDeLaCadena] = []
    # Las `NotaTocada` ya recogidas, por vuelta. Por vuelta y no en un solo
    # conjunto porque los indices se repiten vuelta a vuelta: la nota 2 de la
    # vuelta 3 es un reporte distinto de la nota 2 de la vuelta 1.
    vistas: dict[int, set[NotaTocada]] = {}
    # Las vueltas que el conductor ya tenia cerradas ANTES de esta pasada. Un
    # conductor se puede conducir dos veces -el escaparate lo hace-, y el
    # registro es de ESTA pasada.
    cerradas_al_empezar = len(conductor.vueltas_cerradas)

    # Sin un solo cuadro, la mirada final cae en CERO: la ventana no se llega a
    # llenar, asi que no ha pasado tiempo que meter en la pieza.
    instante = 0.0
    for inicio in range(0, len(muestras), paso):
        # EL INSTANTE DE CADA VENTANA ES SU FINAL, menos la cabecera que no es
        # tiempo musical. El final y no el centro ni el principio esta medido (ver
        # la cabecera del modulo); el descuento es lo que pone el cabezal a cero
        # cuando suena la nota que la pieza escribe en cero.
        #
        # Los cuadros que caen DENTRO de la cabecera se entregan igual, con el
        # instante acotado a cero: el detector necesita ese silencio para tener
        # nivel de referencia con el que ver el primer ataque, y como todos
        # cuentan el mismo instante, sus miradas avanzan el cabezal cero.
        instante = max(0.0, (inicio + ventana) / frecuencia - desplazamiento_s)
        # MIRAR antes de OBSERVAR, y con el mismo instante, que es el orden del
        # servidor (ver `ConductorDeEstudio.observar`: «quien conduce mira y en
        # seguida observa con el mismo instante»).
        #
        # Y hacen falta las dos llamadas, no solo `observar`: el cierre de las
        # vueltas del bucle y el aviso de la repeticion viven en `mirar`, no en
        # `observar` -el hilo del analisis del servidor no es sitio para un
        # callback-, asi que una cadena que solo observara dejaria
        # `vueltas_cerradas` VACIO y el registro no tendria ni un informe. En el
        # servidor son dos caminos, uno por hilo; aqui no hay hilos, asi que los
        # dos caminos se recorren uno detras del otro en cada cuadro.
        #
        # De la mirada NO se recoge nada, y es deliberado: lo unico que apila
        # `NotaTocada` es `SeguidorPieza.procesar`, al que solo se llega por
        # `observar`. Lo que la mirada puede hacerle a esa tupla es TIRARLA
        # (`cerrar_repeticion`, `olvidar_tramo` al dar la vuelta), nunca añadirle
        # nada, asi que recoger de la mirada no podia recoger ni un reporte que el
        # cuadro anterior no hubiera dado ya. Estaba, y era codigo que ninguna
        # prueba podia falsear.
        #
        # `senal_ausente=False` siempre: el cable del gemelo esta enchufado y
        # entregando cuadros. Un audio en silencio son cuadros de silencio, que
        # es otra cosa -y el reloj de la pasada no se congela por ellos, igual que
        # no se congela con la guitarra callada y el cable puesto-.
        conductor.mirar(instante, False)
        resultado = analizador.procesar(_ventana_en(muestras, inicio, ventana))
        _recoger(conductor.observar(resultado, instante), vistas, reportes)

    # La mirada final, con el ultimo instante y sin cuadro detras: es la que
    # cierra lo que el ultimo cuadro dejo terminado. Sin ella, una pasada sin
    # bucle acaba con `tramo_terminado` puesto y su vuelta sin cerrar, porque el
    # cuadro que la termino no la cierra -`observar` no cierra nada- y ya no viene
    # ningun cuadro mas.
    estado_final = conductor.mirar(instante, False)

    return RegistroDeLaCadena(
        reportes=tuple(reportes),
        vueltas=tuple(conductor.vueltas_cerradas[cerradas_al_empezar:]),
        estado_final=estado_final,
    )


def _analizador_de(
    analizador: Analizador | None, conductor: ConductorDeEstudio, frecuencia: int
) -> Analizador:
    """El analizador de produccion, con el perfil de la pieza que se estudia.

    `Pieza.perfil` es una CLAVE de `PERFILES` y no un `PerfilAfinacion`, y de ese
    perfil sale la ventana (`tamano_ventana`): 4096 muestras con guitarra
    estandar. La frecuencia tiene que coincidir con la de la interpretacion
    porque la ventana se deriva de ella, y un analizador a 44,1 kHz recorreria el
    audio de 48 kHz con una ventana que no es la suya.
    """
    if analizador is None:
        return Analizador(
            PERFILES[conductor.estudio.pieza.perfil], frecuencia_muestreo=frecuencia
        )
    if analizador.frecuencia_muestreo != frecuencia:
        raise ValueError(
            f"El analizador trabaja a {analizador.frecuencia_muestreo} Hz y la "
            f"interpretacion viene a {frecuencia} Hz: la ventana saldria de la "
            "frecuencia equivocada"
        )
    return analizador


def _ventana_en(muestras: np.ndarray, inicio: int, ventana: int) -> np.ndarray:
    """La ventana que empieza en `inicio`, rellenada con ceros si se sale.

    El recorrido llega hasta la ultima ventana que EMPIEZA dentro del audio, y no
    hasta la ultima que CABE entera, y el relleno es lo que lo hace posible. Es
    lo que pasa en vivo: el audio se acaba y los cuadros siguen llegando, con la
    cola de la pasada y silencio detras. Parando en la ultima ventana entera se
    perderian los ultimos cuatro cuadros -la ventana son cuatro saltos-, que son
    justo los que resuelven el ataque de la ultima nota del tramo.
    """
    trozo = muestras[inicio : inicio + ventana]
    if len(trozo) == ventana:
        return trozo
    relleno = np.zeros(ventana, dtype=muestras.dtype)
    relleno[: len(trozo)] = trozo
    return relleno


def _recoger(
    estado: EstadoEstudio,
    vistas: dict[int, set[NotaTocada]],
    reportes: list[ReporteDeLaCadena],
) -> None:
    """Anota las `NotaTocada` de este estado que no se hubieran visto ya.

    Se compara con las ya vistas DE ESA VUELTA, y por valor y no por posicion: el
    seguidor puede tirar lo que lleva anotado (`olvidar_tramo` al dar la vuelta, y
    `cerrar_repeticion` al cerrarla), asi que la tupla no solo crece y contar
    cuantas van no basta.

    Lo que se anota de la ventana es el reloj de la PASADA, que es donde el carril
    tenia el cabezal cuando el reporte aparecio.
    """
    ya = vistas.setdefault(estado.repeticion, set())
    for tocada in estado.carril.tocadas:
        if tocada in ya:
            continue
        ya.add(tocada)
        reportes.append(
            ReporteDeLaCadena(
                repeticion=estado.repeticion,
                tocada=tocada,
                instante_pasada_s=estado.carril.instante_s,
            )
        )
