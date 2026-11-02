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
  vez cerca de cero. Por eso de cada vuelta se descuenta tambien lo que las
  anteriores ocupan en el audio, que sale de la aritmetica de `interpretar`:
  `(duracion_s - cabecera_tecnica) / vueltas` es cuenta atras mas tramo. Sin eso,
  un bucle salia con todas las notas de las vueltas 2 y 3 perdidas e inventadas,
  y el arreglo del bucle de la T7 no habria tenido como medirse.

Dos condiciones que el veredicto NO puede comprobar, y por eso se escriben:

1. La cuenta atras del plan de la pasada y los `segundos_de_cuenta_atras` de la
   interpretacion tienen que ser la misma. Si quien conduce pide un compas de
   aviso que el gemelo no toco (o al contrario), los dos relojes se separan por
   esa diferencia.
2. **El tramo tiene que empezar en el principio de la pieza.** El cabezal no
   arranca en cero cuando la pasada estudia del compas 3 al 5: arranca en el
   instante escrito de ese compas (medido: con el tramo 2-2 de la escala, los
   reportes de la vuelta 1 caen en 2,6 s). Ese desplazamiento es el instante de
   inicio del tramo, y `Interpretacion` no lo lleva dentro -ni el tramo ni el
   `factor_tempo` con el que se toco-, asi que el veredicto no puede calcularlo.
   Juzgar un tramo que no empieza en el compas 1 saca todas las notas perdidas.
   El arreglo es de una sola linea, pero no es de aqui: es añadir el inicio del
   tramo a `Interpretacion`, en el modulo del interprete.

**LA TOLERANCIA ES DE EMPAREJAMIENTO, NO DE CALIDAD.** 120 ms, no 15. Su unico
trabajo es decidir si el reporte X habla del ataque Y; la calidad -si esa nota
estaba a tiempo- la decide la cadena y no es asunto de aqui. Con 15 ms casi toda
nota saldria perdida y el oraculo seria rojo por construccion, midiendo la
tolerancia en vez de la cadena.
"""

from dataclasses import dataclass

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.gemelo.cadena import RegistroDeLaCadena, ReporteDeLaCadena
from nucleo.gemelo.interprete import VENTANAS_DE_CABECERA, Interpretacion
from nucleo.piezas.modelo import Pieza

# La holgura de emparejamiento por omision, en milisegundos. Ver el docstring del
# modulo: es la que decide si un reporte habla de un ataque, y nada mas.
TOLERANCIA_DE_EMPAREJAMIENTO_MS = 120.0


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
    busca el reporte de esa vuelta y ese puesto, y entre los que caen dentro de la
    tolerancia se coge el mas cercano en el tiempo. Sin reporte, la nota se
    perdio; con reporte de otra altura, se adjudico mal. Lo que queda sin
    emparejar se invento la cadena.

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

    excluidas = _excluidas(interpretacion.pieza, tocados)
    por_puesto = _reportes_por_puesto(registro)

    perdidas: list[tuple[int, int]] = []
    mal_adjudicadas: list[tuple[int, int, int]] = []
    desfases_s: list[float] = []
    # Los reportes ya emparejados, por su POSICION en `registro.reportes`: dos
    # reportes distintos pueden ser iguales campo a campo -la cadena publica por
    # valor- y entonces un conjunto de reportes se comeria uno de los dos.
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
        posicion_del_reporte = _mas_cercano(
            por_puesto.get(puesto, ()),
            instante_real_s=instante_real_s,
            tolerancia_s=tolerancia_s,
            ya_emparejados=emparejados,
        )
        if posicion_del_reporte is None:
            if puesto not in excluidas:
                perdidas.append(puesto)
            continue
        emparejados.add(posicion_del_reporte)
        reporte = registro.reportes[posicion_del_reporte]
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


def _adelantos_por_vuelta(
    interpretacion: Interpretacion, vueltas: tuple[int, ...]
) -> dict[int, float]:
    """Lo que hay que descontarle al eje del audio, vuelta a vuelta, para caer en
    el eje del cabezal.

    Son dos terminos, y el docstring del modulo dice de donde sale cada uno:

    * La cuenta atras, en todas las vueltas. Es lo que queda del silencio de
      cabecera al quitarle la cabecera tecnica -que NO se descuenta, porque
      durante ella el cabezal ya corre-, y la tecnica se calcula igual que en
      `interpretar`: ventana y media del perfil de la pieza.
    * Lo que ocupan en el audio las vueltas anteriores, porque el cabezal vuelve
      atras en cada una. `(duracion_s - cabecera_tecnica) / vueltas` es cuenta
      atras mas tramo, que es exactamente lo que `interpretar` pone entre dos
      vueltas; no se estima de los eventos para que una nota fallada en la
      frontera no desplace el eje de la vuelta entera.

    El numero de vueltas se cuenta de los eventos, asi que una ultima vuelta en
    la que se fallaran TODAS las notas no se veria y el paso saldria largo. Con
    ocho notas y el peor perfil es uno entre diez mil, y el precio de equivocarse
    es un veredicto sucio -nunca uno limpio de mentira-, asi que se acepta y se
    escribe.
    """
    ventana = PERFILES[interpretacion.pieza.perfil].tamano_ventana(
        interpretacion.frecuencia_muestreo
    )
    tecnica_s = VENTANAS_DE_CABECERA * ventana / interpretacion.frecuencia_muestreo
    cuenta_atras_s = max(0.0, interpretacion.silencio_de_cabecera_s - tecnica_s)
    total = max(vueltas, default=1)
    paso_s = max(0.0, interpretacion.duracion_s - tecnica_s) / total
    return {
        vuelta: cuenta_atras_s + (vuelta - 1) * paso_s
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


def _excluidas(pieza: Pieza, tocados: dict[int, set[int]]) -> set[tuple[int, int]]:
    """Los `(vuelta, indice)` que no se juzgan, deducidos DE LA PIEZA.

    Dos familias, las dos por un limite declarado del programa y no por un fallo:

    * Los acordes. Varias notas con el mismo `inicio_pulsos` son un acorde, el
      detector de tono es monofonico y el interprete toca solo la mas grave. Las
      demas no sonaron.
    * Las notas repetidas consecutivas. `DetectorPulsaciones` declara que no
      distingue dos pulsaciones seguidas de la misma altura sin un hueco de tres
      cuadros sin nota creible. Se excluye la SEGUNDA, que es la que el detector
      se come.

    `tocados` -los indices que tienen evento en cada vuelta- solo decide el
    ALCANCE: una exclusion se anota en las vueltas en las que su grupo se toco, y
    asi una pieza interpretada por tramos no arrastra exclusiones de notas que
    nadie iba a tocar. No decide QUE se excluye, que es cosa de la pieza: con el
    registro vacio las exclusiones son exactamente las mismas.
    """
    testigos = _testigos_de_las_exclusiones(pieza)
    return {
        (vuelta, excluida)
        for excluida, testigo in testigos.items()
        for vuelta, indices in tocados.items()
        if testigo in indices
    }


def _testigos_de_las_exclusiones(pieza: Pieza) -> dict[int, int]:
    """Cada indice excluido con el indice cuyo evento prueba que se llego a tocar.

    El testigo de una nota de acorde es la nota del acorde que SI suena (la mas
    grave); el de una repetida es ella misma, porque se toca y lo que se come el
    detector es el reporte.
    """
    sonadas = _reduccion_de_los_acordes(pieza)
    testigos: dict[int, int] = {}

    for indices, elegida in sonadas:
        for indice in indices:
            if indice != elegida:
                testigos[indice] = elegida

    anterior = None
    for indices, elegida in sonadas:
        actual = pieza.notas[elegida]
        if anterior is not None and actual.midi == anterior.midi:
            testigos[elegida] = elegida
        anterior = actual
    return testigos


def _reduccion_de_los_acordes(pieza: Pieza) -> tuple[tuple[tuple[int, ...], int], ...]:
    """La pieza reducida a lo que una guitarra monofonica puede tocar.

    Devuelve un grupo por `inicio_pulsos`, con los indices del grupo y el del que
    suena. La regla es la del interprete -la mas grave, y de dos iguales la
    primera-, replicada aqui y no importada porque la del interprete trabaja
    sobre un TRAMO y lo que el veredicto necesita es la pieza entera. Si una de
    las dos cambiara sin la otra, las pruebas de exclusiones de este modulo se
    pondrian rojas.
    """
    grupos: list[tuple[list[int], int]] = []
    for indice, nota in enumerate(pieza.notas):
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
) -> dict[tuple[int, int], list[tuple[int, ReporteDeLaCadena]]]:
    """Los reportes agrupados por `(repeticion, indice)`, que es el puesto.

    Cada uno va con su POSICION en `registro.reportes`, que es lo que lo
    identifica: puede haber mas de un reporte en el mismo puesto -la cadena
    publica por valor, asi que dos lecturas distintas de la misma nota son dos
    reportes- y dos de ellos pueden ser iguales campo a campo.
    """
    por_puesto: dict[tuple[int, int], list[tuple[int, ReporteDeLaCadena]]] = {}
    for posicion, reporte in enumerate(registro.reportes):
        clave = (reporte.repeticion, reporte.tocada.indice)
        por_puesto.setdefault(clave, []).append((posicion, reporte))
    return por_puesto


def _mas_cercano(
    candidatos: list[tuple[int, ReporteDeLaCadena]],
    instante_real_s: float,
    tolerancia_s: float,
    ya_emparejados: set[int],
) -> int | None:
    """La posicion del reporte libre mas cercano al ataque, o `None` si ninguno
    llega a tiempo.

    Se mide en valor absoluto porque el emparejamiento no tiene direccion: un
    reporte 20 ms antes del ataque habla de ese ataque igual que uno 20 ms
    despues. El SIGNO se conserva despues, en el desfase, que es lo que
    diagnostica.
    """
    mejor: int | None = None
    mejor_distancia = tolerancia_s
    for posicion, reporte in candidatos:
        if posicion in ya_emparejados:
            continue
        distancia = abs(reporte.instante_pasada_s - instante_real_s)
        if distancia <= mejor_distancia:
            mejor = posicion
            mejor_distancia = distancia
    return mejor


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
