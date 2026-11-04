"""El veredicto: lo que el gemelo firma despues de comparar verdad y reporte.

Aqui se juntan las dos mitades de la etapa: lo que el guitarrista sintetico toco
DE VERDAD (`Interpretacion.eventos`, escrita antes de generar una sola muestra) y
lo que la cadena reporto al recorrer ese audio (`RegistroDeLaCadena`). El
veredicto dice tres cosas, y solo tres: que notas no vio la cadena, cuantas se
invento y cuantos milisegundos añadio.

**EL VEREDICTO NO CONSULTA LAS REGLAS DE LA CADENA, y es el anti-objetivo de la
spec §2.** No reimplementa la ventana de acierto, ni la clasificacion del
retraso, ni el umbral de cents; tampoco los lee. De una `NotaTocada` solo mira
`indice` y `midi`, que son hechos («la cadena dijo que en el puesto 3 sono un
60»), y no los campos donde la cadena ya se ha pronunciado. Un veredicto que
leyera esos campos estaria preguntandole a la cadena si la cadena lo hizo bien, y
una prueba de este modulo lo vigila con `ast`.

**LAS EXCLUSIONES SALEN DE LA PIEZA, no de lo que la cadena hizo.** Los acordes
(varias notas en el mismo `inicio_pulsos`) y las notas repetidas consecutivas se
excluyen porque el programa declara por escrito que no las distingue: el detector
de tono es monofonico y `DetectorPulsaciones` necesita un hueco de tres cuadros
sin nota creible para contar dos pulsaciones seguidas de la misma altura.
Dedujeras las exclusiones de lo que la cadena no reporto, y el veredicto no
podria perder una nota jamas: todo lo perdido se llamaria «excluido».

**LOS DOS EJES DE TIEMPO.** `EventoTocado.instante_s` esta en el eje del AUDIO,
con el silencio de cabecera dentro. `ReporteDeLaCadena.instante_pasada_s` esta en
el eje del CABEZAL: la posicion que el carril pintaba cuando el reporte aparecio.
No es un cronometro de la pasada, y esto es lo que hace la traduccion menos obvia
de lo que parece. Esta MEDIDO, no razonado (sonda sobre `escala_de_ocho_notas`
con `PERFECTO` y el salto de produccion):

* La cabecera tecnica (`VENTANAS_DE_CABECERA`, 128 ms con guitarra estandar a
  48 kHz) NO se descuenta. La cadena arranca con `fijar_la_mirada(0.0)` en la
  muestra cero y el cabezal avanza desde ahi con cada mirada, asi que cuando la
  primera nota suena -128 ms dentro del audio- el cabezal ya marca 128 ms. Los
  reportes salen entonces entre +71 y +188 ms de su ataque, mediana +130 ms, que
  es lo que la cadena tarda en PUBLICAR un ataque (unos 20 ms de deteccion mas
  unos 165 de estabilizacion: mediana de 5 del suavizador, 60 ms de espera y tres
  cuadros de racha). Descontando la cabecera salian +199 a +316 ms: 128 ms de
  sesgo inventado por la traduccion.
* La cuenta atras SI se descuenta, porque ahi los dos relojes se separan de
  verdad: mientras dura, `SesionDeEstudio` recoloca el cabezal en el inicio en
  cada mirada y en cada cuadro, asi que el cabezal se queda quieto mientras el
  audio del gemelo sigue corriendo.
* **En un bucle, el cabezal VUELVE ATRAS en cada vuelta**, asi que el reporte de
  la nota 0 de la vuelta 3 llega con el cabezal en 0,2 s y no en 10 s. Medido:
  con tres vueltas de la escala, los reportes de las vueltas 2 y 3 empiezan otra
  vez cerca de cero (0,189 y 0,252). Sin descontarlo, un bucle salia con todas
  las notas de las vueltas 2 y 3 perdidas e inventadas, y el arreglo del bucle de
  la T7 no habria tenido como medirse.
* **El cabezal de un tramo que no empieza en el compas 1 no arranca en cero**:
  arranca en el instante escrito de ese compas. Medido con el tramo 2-2 de la
  escala: los reportes de la vuelta 1 caen en 2,6 s mientras los ataques estan a
  0,128 s del audio. Ese instante se suma, y por eso `Interpretacion` lleva dentro
  el tramo, el factor de tempo, las vueltas y la cuenta atras con que se toco: sin
  ellos esta traduccion no se puede hacer, y las secciones de una cancion casi
  nunca empiezan en el compas 1.

Queda UNA condicion que el veredicto no puede comprobar, y por eso se escribe: la
cuenta atras del plan de la pasada y los `segundos_de_cuenta_atras` de la
interpretacion tienen que ser la misma, y el tramo del plan el mismo que el de la
interpretacion. Si quien conduce estudia otro tramo del que el gemelo toco, los
dos relojes se separan por esa diferencia y el veredicto no puede saberlo: el
registro no dice con que plan se condujo.

**LA TOLERANCIA ES DE EMPAREJAMIENTO, NO DE CALIDAD.** Su unico trabajo es
decidir si el reporte X habla del ataque Y; la calidad -si esa nota estaba a
tiempo- la decide la cadena y no es asunto de aqui. Es el techo del propio
detector, `VENTANA_ATAQUE_COMO_ONSET_S`, y no un numero escrito aqui: ver el
comentario de `TOLERANCIA_DE_EMPAREJAMIENTO_MS`.
"""

from dataclasses import dataclass

import numpy as np

from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.gemelo.cadena import RegistroDeLaCadena, ReporteDeLaCadena
from nucleo.gemelo.interprete import Interpretacion
from nucleo.piezas.compases import pulsos_por_compas, total_de_compases
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos

# La holgura de emparejamiento por omision: EL TECHO DEL PROPIO DETECTOR, no un
# numero elegido aqui.
#
# `VENTANA_ATAQUE_COMO_ONSET_S` es lo mas viejo que un ataque puede ser para que
# el detector lo firme como el onset de la pulsacion que esta resolviendo, o sea
# exactamente lo que la cadena puede tardar en hablar de un ataque. Un reporte mas
# tardio que eso ya no habla de ese ataque, y uno mas temprano si. Se nombra la
# constante y no se escribe el numero para que la holgura siga al detector el dia
# que alguien mueva su techo: un 250 suelto aqui se desacoplaria en silencio.
#
# Y 120 ms no servia, medido: la escala de ocho notas con `PERFECTO` salia con 5
# de 8 notas perdidas, porque `instante_pasada_s` no lleva el instante del onset
# sino el del cabezal CUANDO EL REPORTE SE PUBLICA, y entre los dos hay otros
# ~165 ms de estabilizacion. Con la holgura en el techo del detector, cero
# perdidas. Apretarla es como se pone un oraculo rojo por construccion: la prueba
# mediria la tolerancia y no la cadena.
TOLERANCIA_DE_EMPAREJAMIENTO_MS = VENTANA_ATAQUE_COMO_ONSET_S * 1000.0


@dataclass(frozen=True)
class Veredicto:
    """Lo que la cadena perdio, lo que se invento y lo que retraso.

    `perdidas`, `mal_adjudicadas` y `excluidas` llevan la VUELTA dentro porque
    los indices se repiten vuelta a vuelta: «se perdio la nota 11» no distingue
    «en la vuelta 3» de «en todas», y en un bucle esa diferencia es el
    diagnostico entero.

    `mal_adjudicadas` es `(vuelta, indice_pretendido, midi_reportado)`: el indice
    dice de QUE nota se habla -es el unico dato que la identifica dentro de la
    vuelta- y el midi dice que altura le puso la cadena a ese ataque. La altura
    que de verdad sono se saca de `Interpretacion.eventos`, que es la verdad, y no
    se repite aqui.

    Los dos desfases van en milisegundos y CON SIGNO: una cadena que reporta
    tarde y una que reporta pronto se arreglan por caminos distintos, y un valor
    absoluto las dejaria iguales. `desfase_maximo_ms` es el emparejado de mayor
    valor absoluto, con su signo. Con nada emparejado los dos valen 0,0, que es
    lo honesto: no hay medicion, no hay numero.
    """

    notas_de_la_pieza: int
    notas_tocadas: int
    perdidas: tuple[tuple[int, int], ...]
    inventadas: int
    mal_adjudicadas: tuple[tuple[int, int, int], ...]
    excluidas: tuple[tuple[int, int], ...]
    desfase_introducido_ms: float
    desfase_maximo_ms: float

    @property
    def limpio(self) -> bool:
        """True solo si la cadena vio todo lo que paso y nada mas.

        Las exclusiones NO lo manchan: no son un defecto de la cadena sino un
        limite declarado del programa, y el ejecutable del escaparate elige su
        codigo de salida con esta propiedad.
        """
        return not self.perdidas and not self.inventadas and not self.mal_adjudicadas

    def a_dict(self) -> dict:
        return {
            "notas_de_la_pieza": self.notas_de_la_pieza,
            "notas_tocadas": self.notas_tocadas,
            "perdidas": [list(perdida) for perdida in self.perdidas],
            "inventadas": self.inventadas,
            "mal_adjudicadas": [list(mala) for mala in self.mal_adjudicadas],
            "excluidas": [list(excluida) for excluida in self.excluidas],
            "desfase_introducido_ms": round(self.desfase_introducido_ms, 1),
            "desfase_maximo_ms": round(self.desfase_maximo_ms, 1),
            "limpio": self.limpio,
        }


def juzgar(
    interpretacion: Interpretacion,
    registro: RegistroDeLaCadena,
    tolerancia_de_emparejamiento_ms: float = TOLERANCIA_DE_EMPAREJAMIENTO_MS,
) -> Veredicto:
    """Compara lo que se toco con lo que la cadena reporto y firma el veredicto.

    Parametros:
        interpretacion: la verdad. Se leen `eventos`, `pieza` y el silencio de
            cabecera; las muestras no se tocan.
        registro: lo que la cadena publico, vuelta a vuelta. Solo se leen
            `reportes`; `vueltas` y `estado_final` son de quien mire la pasada.
        tolerancia_de_emparejamiento_ms: la holgura con la que un reporte se
            atribuye a un ataque. Ver el docstring del modulo.

    El emparejamiento es por `(repeticion, indice_pretendido)`: de cada evento se
    busca el reporte de esa vuelta y ese puesto, y vale si cae dentro de la
    tolerancia. Sin reporte, o con uno que queda fuera, la nota se perdio; con
    reporte de otra altura, se adjudico mal. Lo que queda sin emparejar se invento
    la cadena.

    Lanza `ValueError` si la tolerancia es negativa: una tolerancia negativa no
    empareja nada y convertiria la pasada entera en perdidas e invenciones sin que
    nada se quejara.
    """
    if tolerancia_de_emparejamiento_ms < 0.0:
        raise ValueError(
            f"La tolerancia {tolerancia_de_emparejamiento_ms} ms no sirve: "
            "no puede ser negativa"
        )
    tolerancia_s = tolerancia_de_emparejamiento_ms / 1000.0

    vueltas = _vueltas_de_los_eventos(interpretacion)
    tocados: dict[int, set[int]] = {}
    for evento, vuelta in zip(interpretacion.eventos, vueltas, strict=True):
        if evento.indice_pretendido is not None:
            tocados.setdefault(vuelta, set()).add(evento.indice_pretendido)
    adelantos_s = _adelantos_por_vuelta(interpretacion, vueltas)

    excluidas = _excluidas(interpretacion, tocados)
    por_puesto = _reportes_por_puesto(registro)

    perdidas: list[tuple[int, int]] = []
    mal_adjudicadas: list[tuple[int, int, int]] = []
    desfases_s: list[float] = []
    # Las POSICIONES de los reportes ya emparejados, que es lo que queda para
    # contar las inventadas: lo que nadie reclamo.
    emparejados: set[int] = set()

    for evento, vuelta in zip(interpretacion.eventos, vueltas, strict=True):
        if evento.indice_pretendido is None:
            # Una pulsacion que no apunta a ninguna nota escrita no se puede
            # emparejar por puesto, asi que no se juzga. Hoy no existe -el
            # interprete no las genera todavia-, y cuando exista hara falta
            # emparejarla por altura e instante, que es otra tarea.
            continue
        puesto = (vuelta, evento.indice_pretendido)
        instante_real_s = evento.instante_s - adelantos_s[vuelta]
        posicion = por_puesto.get(puesto)
        reporte = None if posicion is None else registro.reportes[posicion]
        if reporte is None or not _habla_del_ataque(
            reporte, instante_real_s, tolerancia_s
        ):
            if puesto not in excluidas:
                perdidas.append(puesto)
            continue
        emparejados.add(posicion)
        # El desfase se anota tambien de lo excluido y de lo mal adjudicado: es
        # una MEDICION del retraso de la cadena sobre un ataque que de verdad
        # sono, no un juicio sobre esa nota.
        desfases_s.append(reporte.instante_pasada_s - instante_real_s)
        if puesto in excluidas:
            continue
        if reporte.tocada.midi != evento.midi:
            mal_adjudicadas.append(
                (vuelta, evento.indice_pretendido, reporte.tocada.midi)
            )

    inventadas = sum(
        1
        for posicion, reporte in enumerate(registro.reportes)
        if posicion not in emparejados
        and (reporte.repeticion, reporte.tocada.indice) not in excluidas
    )

    return Veredicto(
        notas_de_la_pieza=len(interpretacion.pieza.notas),
        notas_tocadas=len(interpretacion.eventos),
        perdidas=tuple(sorted(perdidas)),
        inventadas=inventadas,
        mal_adjudicadas=tuple(sorted(mal_adjudicadas)),
        excluidas=tuple(sorted(excluidas)),
        desfase_introducido_ms=_mediana_ms(desfases_s),
        desfase_maximo_ms=_maximo_con_signo_ms(desfases_s),
    )


def _tramo_en_pulsos(interpretacion: Interpretacion) -> tuple[float, float]:
    """El `[inicio, fin)` en pulsos del tramo que se interpreto.

    Sale de los compases que `Interpretacion` registra, con la misma convencion
    que `interpretar`: una pieza sin compases se interpreta como un compas de
    silencio, y `ultimo_compas` ya llega resuelto (pero se vuelve a resolver aqui
    por si alguien armo la interpretacion a mano con un `None`).

    Lo usan las dos mitades del modulo -la traduccion de los ejes y las
    exclusiones- y esa es la razon de que sea una funcion: las dos tienen que
    estar hablando del MISMO tramo.
    """
    pieza = interpretacion.pieza
    ancho = pulsos_por_compas(pieza)
    tope = max(1, total_de_compases(pieza))
    ultimo = (
        tope if interpretacion.ultimo_compas is None else interpretacion.ultimo_compas
    )
    return ((interpretacion.primer_compas - 1) * ancho, ultimo * ancho)


def _adelantos_por_vuelta(
    interpretacion: Interpretacion, vueltas: tuple[int, ...]
) -> dict[int, float]:
    """Lo que hay que descontarle al eje del audio, vuelta a vuelta, para caer en
    el eje del cabezal.

    **Esta traduccion esta MEDIDA, y la intuicion de que hay que restar el
    silencio de cabecera entero es la equivocada.** Queda escrito aqui con los
    numeros porque es la trampa de este modulo y el proximo que lo lea va a tener
    la misma intuicion.

    Lo que `instante_pasada_s` lleva dentro no es un cronometro de la pasada: es
    la POSICION DEL CABEZAL cuando el reporte se publico. Y el cabezal arranca en
    la muestra cero -la cadena hace `fijar_la_mirada(0.0)`- y avanza con cada
    mirada, asi que **durante la cabecera tecnica el cabezal ya corre**: cuando la
    primera nota suena, 128 ms dentro del audio, el cabezal ya marca 128 ms.
    Sonda sobre la escala de ocho notas con `PERFECTO` y el salto de produccion:

        ataque(audio)  cabezal al publicar   crudo    restando la cabecera
            0,1280           0,3163        +188,3 ms       +316,3 ms
            0,7280           0,7993         +71,3           +199,3
            1,3280           1,4923        +164,3           +292,3
            ...              ...            ...              ...
                                   mediana +130 ms      mediana +258 ms

    La columna cruda (mediana +130 ms) es lo que la cadena tarda en PUBLICAR un
    ataque: ~20 ms de deteccion mas ~165 de estabilizacion. La otra pasa del techo
    del propio detector (250 ms) y es un sesgo inventado por la traduccion.

    La comprobacion independiente, que es la que zanja el asunto: el `desfase_s`
    que la cadena firma para la nota 0 es **148,3 ms = 128 de cabecera + 20 de
    deteccion**. Si el cabezal fuera 128 ms por DETRAS del audio, ese desfase
    habria salido 20 ms. Salio 148: el cabezal va con el audio, y restar la
    cabecera es meter el sesgo, no quitarlo.

    Lo que si se descuenta son las tres cosas en las que los dos ejes se separan
    de verdad, y las tres salen de los argumentos que `Interpretacion` registra:

    * La cuenta atras, en TODAS las vueltas: mientras dura, `SesionDeEstudio`
      recoloca el cabezal en el inicio en cada mirada y en cada cuadro, asi que se
      queda quieto mientras el audio sigue corriendo.
    * Lo que ocupan las vueltas anteriores (cuenta atras mas tramo), porque el
      cabezal vuelve atras en cada vuelta.
    * Y en sentido contrario SE SUMA el inicio del tramo, porque el cabezal de una
      pasada que estudia del compas 2 al 2 arranca en el instante escrito de ese
      compas. Es `_inicio_s` de `SesionDeEstudio`, calculado igual: pulsos a
      segundos, divididos por el factor de tempo.
    """
    pieza = interpretacion.pieza
    inicio_pulsos, fin_pulsos = _tramo_en_pulsos(interpretacion)
    factor = interpretacion.factor_tempo
    inicio_tramo_s = pulsos_a_segundos(inicio_pulsos, pieza.tempo) / factor
    tramo_s = pulsos_a_segundos(fin_pulsos - inicio_pulsos, pieza.tempo) / factor
    cuenta_atras_s = interpretacion.segundos_de_cuenta_atras

    total = max(interpretacion.repeticiones, max(vueltas, default=1))
    return {
        vuelta: cuenta_atras_s
        + (vuelta - 1) * (cuenta_atras_s + tramo_s)
        - inicio_tramo_s
        for vuelta in range(1, total + 1)
    }


def _vueltas_de_los_eventos(interpretacion: Interpretacion) -> tuple[int, ...]:
    """La vuelta de cada evento, contando desde 1 como la cuenta el estudio.

    `EventoTocado` no lleva la vuelta dentro, asi que se deduce del orden: el
    interprete genera las vueltas una detras de otra y dentro de cada una los
    indices CRECEN estrictamente (`_pulsaciones_escritas` recorre la pieza en
    orden y se queda una nota por `inicio_pulsos`), asi que un indice que no sube
    es una vuelta nueva. Una nota fallada no rompe esto: simplemente falta.

    Deducirla es mas barato que meterla en `EventoTocado`, pero no es gratis: si
    alguna vez el interprete emitiera los eventos desordenados, esto mentiria. La
    prueba del bucle de este modulo es la que lo sujeta.
    """
    vueltas: list[int] = []
    vuelta = 1
    anterior: int | None = None
    for evento in interpretacion.eventos:
        indice = evento.indice_pretendido
        if indice is not None:
            if anterior is not None and indice <= anterior:
                vuelta += 1
            anterior = indice
        vueltas.append(vuelta)
    return tuple(vueltas)


def _excluidas(
    interpretacion: Interpretacion, tocados: dict[int, set[int]]
) -> set[tuple[int, int]]:
    """Los `(vuelta, indice)` que no se juzgan, deducidos DE LA PIEZA.

    Dos familias, las dos por un limite declarado del programa y no por un fallo:

    * Los acordes. Varias notas con el mismo `inicio_pulsos` son un acorde, el
      detector de tono es monofonico y el interprete toca solo la mas grave. Las
      demas no sonaron.
    * Las notas repetidas consecutivas. `DetectorPulsaciones` declara que no
      distingue dos pulsaciones seguidas de la misma altura sin un hueco de tres
      cuadros sin nota creible. Se excluye la SEGUNDA, que es la que el detector
      se come.

    **Las dos reglas se leen DENTRO DEL TRAMO INTERPRETADO**, no sobre la pieza
    entera, y no es un detalle: si la primera nota del tramo repite la altura de
    la nota anterior de la pieza -que en esta pasada nadie toca- no hay dos
    pulsaciones seguidas que el detector pueda confundir, y excluirla seria tapar
    una perdida de verdad, que es lo peor que este modulo puede hacer. El acotado
    por `tocados` no lo evitaba porque el testigo de una repetida es ella misma.

    `tocados` -los indices que tienen evento en cada vuelta- decide solo en QUE
    VUELTAS se anota cada exclusion, para que una vuelta que no se llego a tocar
    no arrastre exclusiones. No decide QUE se excluye, que es cosa de la pieza y
    del tramo: con el registro vacio las exclusiones son exactamente las mismas.
    """
    inicio_tramo, fin_tramo = _tramo_en_pulsos(interpretacion)
    testigos = _testigos_de_las_exclusiones(
        interpretacion.pieza, inicio_tramo, fin_tramo
    )
    return {
        (vuelta, excluida)
        for excluida, testigo in testigos.items()
        for vuelta, indices in tocados.items()
        if testigo in indices
    }


def _testigos_de_las_exclusiones(
    pieza: Pieza, inicio_tramo: float, fin_tramo: float
) -> dict[int, int]:
    """Cada indice excluido con el indice cuyo evento prueba que se llego a tocar.

    El testigo de una nota de acorde es la nota del acorde que SI suena (la mas
    grave); el de una repetida es ella misma, porque se toca y lo que se come el
    detector es el reporte.

    La nota anterior arranca en `None` en el borde del tramo, y ahi esta el
    arreglo de la sobre-exclusion: la primera nota del tramo no tiene con quien
    repetirse.
    """
    sonadas = _reduccion_de_los_acordes(pieza, inicio_tramo, fin_tramo)
    testigos: dict[int, int] = {}

    for indices, elegida in sonadas:
        for indice in indices:
            if indice != elegida:
                testigos[indice] = elegida

    anterior = None
    for _, elegida in sonadas:
        actual = pieza.notas[elegida]
        if anterior is not None and actual.midi == anterior.midi:
            testigos[elegida] = elegida
        anterior = actual
    return testigos


def _reduccion_de_los_acordes(
    pieza: Pieza, inicio_tramo: float, fin_tramo: float
) -> tuple[tuple[tuple[int, ...], int], ...]:
    """El tramo reducido a lo que una guitarra monofonica puede tocar.

    Devuelve un grupo por `inicio_pulsos`, con los indices del grupo y el del que
    suena. La regla es la del interprete -la mas grave, y de dos iguales la
    primera-, sobre las notas del tramo y en su orden, que es exactamente lo que
    `_pulsaciones_escritas` recorre.

    Se replica y no se importa: la del interprete devuelve ademas el hueco hasta
    la nota siguiente y se usa para sintetizar: compartirla engancharia el
    veredicto a una firma pensada para generar audio. Si una de las dos cambia sin
    la otra, las pruebas de exclusiones de este modulo se ponen rojas, y esta
    medido.
    """
    grupos: list[tuple[list[int], int]] = []
    for indice, nota in enumerate(pieza.notas):
        if not inicio_tramo <= nota.inicio_pulsos < fin_tramo:
            continue
        if grupos and pieza.notas[grupos[-1][0][0]].inicio_pulsos == nota.inicio_pulsos:
            indices, elegida = grupos[-1]
            indices.append(indice)
            if nota.midi < pieza.notas[elegida].midi:
                grupos[-1] = (indices, indice)
            continue
        grupos.append(([indice], indice))
    return tuple((tuple(indices), elegida) for indices, elegida in grupos)


def _reportes_por_puesto(
    registro: RegistroDeLaCadena,
) -> dict[tuple[int, int], int]:
    """La POSICION de cada reporte en `registro.reportes`, por su puesto.

    El puesto es `(repeticion, indice)`, y hay UNO por puesto, no una lista: la
    cadena no publica dos veces la misma nota de la misma vuelta, y la T4 lo tiene
    probado (`test_no_se_reporta_la_misma_nota_dos_veces`, que afirma que las
    claves del registro no se repiten).

    Si un registro armado a mano trae dos reportes del mismo puesto, se queda el
    PRIMERO y el otro sale como inventada, que es lo que dos reportes del mismo
    puesto significan: uno de los dos sobra. Se identifica por posicion y no por
    valor porque dos reportes pueden ser iguales campo a campo, y un conjunto de
    reportes se comeria uno de los dos.
    """
    por_puesto: dict[tuple[int, int], int] = {}
    for posicion, reporte in enumerate(registro.reportes):
        por_puesto.setdefault((reporte.repeticion, reporte.tocada.indice), posicion)
    return por_puesto


def _habla_del_ataque(
    reporte: ReporteDeLaCadena, instante_real_s: float, tolerancia_s: float
) -> bool:
    """Si ese reporte se puede atribuir a ese ataque.

    Se mide en valor absoluto porque el emparejamiento no tiene direccion: un
    reporte 20 ms antes del ataque habla de ese ataque igual que uno 20 ms
    despues. El SIGNO se conserva luego, en el desfase, que es lo que diagnostica.

    La igualdad exacta con la tolerancia **empareja** (`<=`), y es deliberado: la
    tolerancia es el techo del detector, o sea el ultimo instante en que la cadena
    todavia puede estar hablando de ese ataque, y no el primero en que ya no.
    Un reporte justo en el techo es el caso que el techo describe. Hay prueba de
    los dos lados de esa igualdad.
    """
    return abs(reporte.instante_pasada_s - instante_real_s) <= tolerancia_s


def _mediana_ms(desfases_s: list[float]) -> float:
    """La mediana de los desfases emparejados, en milisegundos y con signo.

    Mediana y no media porque un solo reporte raro -una nota que la cadena
    adjudico al ataque de al lado- arrastraria la media de la pasada entera.
    """
    if not desfases_s:
        return 0.0
    return float(np.median(desfases_s)) * 1000.0


def _maximo_con_signo_ms(desfases_s: list[float]) -> float:
    """El desfase de mayor valor absoluto, devuelto CON su signo."""
    if not desfases_s:
        return 0.0
    return max(desfases_s, key=abs) * 1000.0
