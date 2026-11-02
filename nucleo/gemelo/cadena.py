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
from nucleo.analisis.pipeline import Analizador
from nucleo.gemelo.interprete import Interpretacion
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import EstadoEstudio, InformeDePasada
from nucleo.piezas.seguimiento import NotaTocada

# Cada cuanto se analiza una ventana, en segundos de la pasada. Es el intervalo
# de produccion (`INTERVALO_ANALISIS` en `servidor/sesion.py`), y esta copiado y
# no importado porque `nucleo/` no importa de `servidor/`: la cadena directa
# existe precisamente para poder verificar la ruta del audio sin el servidor
# delante.
#
# NO es negociable, y 512 muestras no sirven aunque sean mas rapidas: las
# constantes del detector estan acopladas a estos 21 ms
# -`CUADROS_PARA_NOTA_ESTABLE = 3` son 63 ms a 21 ms y 32 ms a 10,7 ms, y
# `nucleo/ejercicios/pulsaciones.py` advierte por escrito de que quien cambie la
# tasa de analisis tiene que revisarlas-, asi que recorrer el audio a otra
# cadencia es ejercitar un detector que nunca corre. Las sondas del diseño usaron
# un salto de 512 y por eso sus numeros son indicativos y no de referencia.
INTERVALO_DE_ANALISIS_S = 0.021


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
    """
    frecuencia = interpretacion.frecuencia_muestreo
    analizador = _analizador_de(analizador, conductor, frecuencia)
    ventana = analizador.tamano_ventana
    paso = round(INTERVALO_DE_ANALISIS_S * frecuencia) if salto is None else salto
    if paso < 1:
        raise ValueError(f"El salto {paso} no sirve: tiene que ser de al menos una muestra")

    muestras = interpretacion.muestras
    # El origen del reloj virtual es la MUESTRA CERO, y la mirada se fija ahi.
    #
    # Hacen falta las dos cosas. Fijarla, porque el conductor que llegue con una
    # mirada puesta en el reloj de pared -el servidor la fija al arrancar la
    # pasada- contaria en su primera mirada un tramo de miles de segundos, o de
    # miles negativos. Y fijarla en CERO y no en el primer instante, porque entre
    # la muestra cero y el primer cuadro pasa una ventana entera de tiempo real
    # (85 ms con guitarra estandar a 48 kHz) que en produccion tambien pasa: ahi
    # el audio ya esta entrando y las miradas del WebSocket mueven el cabezal
    # mientras el primer cuadro se llena. Con la mirada fijada en el primer
    # instante, esos 85 ms desaparecian y el cabezal quedaba adelantado respecto
    # del audio por una cantidad que no corresponde a nada.
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

    instante = ventana / frecuencia
    for inicio in range(0, len(muestras), paso):
        instante = (inicio + ventana) / frecuencia
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
        # `senal_ausente=False` siempre: el cable del gemelo esta enchufado y
        # entregando cuadros. Un audio en silencio son cuadros de silencio, que
        # es otra cosa -y el reloj de la pasada no se congela por ellos, igual que
        # no se congela con la guitarra callada y el cable puesto-.
        _recoger(conductor.mirar(instante, False), vistas, reportes)
        resultado = analizador.procesar(_ventana_en(muestras, inicio, ventana))
        _recoger(conductor.observar(resultado, instante), vistas, reportes)

    # La mirada final, con el ultimo instante y sin cuadro detras: es la que
    # cierra lo que el ultimo cuadro dejo terminado. Sin ella, una pasada sin
    # bucle acaba con `tramo_terminado` puesto y su vuelta sin cerrar, porque el
    # cuadro que la termino no la cierra -`observar` no cierra nada- y ya no viene
    # ningun cuadro mas.
    estado_final = conductor.mirar(instante, False)
    _recoger(estado_final, vistas, reportes)

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
