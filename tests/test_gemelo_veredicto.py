# tests/test_gemelo_veredicto.py
"""El veredicto del gemelo: lo que perdio la cadena, lo que se invento y los
milisegundos que añadio.

**Los registros se construyen A MANO**, reporte a reporte, y no pasando el audio
por la cadena. Son dos razones y las dos importan. La primera es que asi el
veredicto se prueba SOLO: si una prueba de aqui se pone roja, es de `juzgar` y de
nada mas. La segunda es que la cadena tiene hoy un defecto conocido -las notas
adjudicadas en el mismo cuadro que da la vuelta del bucle desaparecen de
`tocadas` antes de que `observar` retorne, y no llegan al registro; lo cierra la
T7-, asi que un registro recogido de la cadena traeria perdidas que no son del
veredicto y estas pruebas estarian midiendo ese defecto.

La interpretacion, en cambio, es la de verdad: `interpretar` con `PERFECTO`, que
es el oraculo. De ella salen los instantes reales de los ataques, y los reportes
de cada prueba se colocan a mano RESPECTO de esos instantes, que es lo que deja
escribir «este reporte llega 100 ms tarde» sin calcular nada a mano.

`estado_final` de los registros va a `None` a proposito: el veredicto no lo mira,
y si algun dia lo mirase, todas estas pruebas se caerian con un `AttributeError`
en vez de pasar en silencio.
"""

import ast
from dataclasses import fields, replace
from pathlib import Path

import pytest

from nucleo.gemelo.cadena import (
    RegistroDeLaCadena,
    ReporteDeLaCadena,
    pasar_por_la_cadena,
)
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import (
    escala_de_ocho_notas,
    pieza_con_acorde,
    pieza_con_nota_repetida,
    pieza_de_demostracion,
)
from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.gemelo.veredicto import (
    TOLERANCIA_DE_EMPAREJAMIENTO_MS,
    Veredicto,
    juzgar,
)
from nucleo.afinaciones import PERFILES
from nucleo.piezas.compases import pulsos_del_compas, pulsos_por_compas
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio
from nucleo.piezas.digitacion import digitar
from nucleo.piezas.modelo import NotaEnPieza, Pieza, pulsos_a_segundos
from nucleo.piezas.seguimiento import NotaTocada

FUENTE_DEL_VEREDICTO = (
    Path(__file__).resolve().parents[1] / "nucleo/gemelo/veredicto.py"
)

# Lo que la cadena DECIDE y el veredicto no tiene derecho a consultar. Son campos
# de `NotaTocada` y funciones del seguidor: un veredicto que los leyera estaria
# preguntandole a la cadena si la cadena lo hizo bien.
# Lo que la cadena tardo en PUBLICAR cada uno de los ocho ataques de
# `escala_de_ocho_notas` interpretada por `PERFECTO`, medido con el salto de
# produccion. Es el numero que decide si una holgura de emparejamiento sirve.
#
# Remedido en la T6d, con el camino A del detector ya arreglado (T6c) y el cabezal
# alineado: la mediana es +152,3 ms y el maximo +188,3. El retraso de publicacion
# NO cambio con la alineacion -los dos ejes se movieron juntos- sino con el
# arreglo del detector, que hace esperar a que la racha cuaje.
#
# «Los dos ejes se movieron juntos» vale para esta configuracion y para cuatro
# mas, pero NO es una identidad: medido en las seis, la que lleva cuenta atras se
# movio 2,0 ms (+94,0/+169,0 pasaron a +96,0/+171,0), porque el cabezal solo se
# suelta de la cuenta atras en un cuadro y el instante exacto cae dentro de uno.
RETRASOS_MEDIDOS_MS = (188.3, 113.3, 164.3, 131.3, 140.3, 170.3, 116.3, 167.3)

# Las REGLAS del seguidor: funciones que deciden si una nota valio. No son campos
# de `NotaTocada`, asi que no se pueden derivar, y van a mano.
REGLAS_DE_LA_CADENA = frozenset({"_clasificar", "ventana_de_acierto", "esta_afinada"})

# Los campos de `NotaTocada` que son una DECISION de la cadena: todos menos los
# dos hechos. Se DERIVAN del dataclass y no se escriben a mano, para que un campo
# de decision nuevo quede vigilado el dia que alguien lo añada.
HECHOS_DE_LA_TOCADA = frozenset({"indice", "midi"})
DECISIONES_DE_LA_TOCADA = frozenset(
    campo.name for campo in fields(NotaTocada)
) - HECHOS_DE_LA_TOCADA


# -- los instrumentos ---------------------------------------------------------


def _interpretacion(pieza=None, **extras) -> Interpretacion:
    """El oraculo tocando la pieza: ni una nota fallada, ni un milisegundo de
    desfase propio."""
    return interpretar(pieza or escala_de_ocho_notas(), PERFECTO, **extras)


def _vueltas_de(interpretacion: Interpretacion) -> tuple[int, ...]:
    """La vuelta de cada evento, deducida como la deduce el veredicto.

    Las pruebas la necesitan para colocar los reportes con su `repeticion`, y se
    calcula aqui -del indice que baja- y no llamando al ayudante privado del
    veredicto: si el veredicto la deduce mal, las pruebas que usan bucle se
    rompen, que es justo lo que se quiere.
    """
    vueltas: list[int] = []
    vuelta = 1
    anterior: int | None = None
    for evento in interpretacion.eventos:
        if anterior is not None and evento.indice_pretendido <= anterior:
            vuelta += 1
        anterior = evento.indice_pretendido
        vueltas.append(vuelta)
    return tuple(vueltas)


def _reporte(
    interpretacion: Interpretacion,
    evento,
    vuelta: int,
    retraso_s: float = 0.0,
    midi: int | None = None,
    indice: int | None = None,
) -> ReporteDeLaCadena:
    """El reporte que la cadena habria publicado de `evento`, con `retraso_s` de
    mas.

    El instante se escribe en el eje del CABEZAL, y la traduccion desde el eje del
    audio se calcula aqui a mano -no se le pide al modulo que se prueba, que es lo
    que la hace falsable-: se descuenta la cuenta atras, porque el cabezal se
    queda quieto mientras dura, y lo que ocupan las vueltas anteriores, porque el
    cabezal vuelve atras en cada vuelta. La cabecera tecnica NO se descuenta:
    durante ella el cabezal ya corre.
    """
    return ReporteDeLaCadena(
        repeticion=vuelta,
        tocada=NotaTocada(
            indice=evento.indice_pretendido if indice is None else indice,
            midi=evento.midi if midi is None else midi,
            cents=0.0,
            desfase_s=None,
            clasificacion=None,
            acertada=True,
            afinada=True,
        ),
        instante_pasada_s=(
            evento.instante_s - _adelanto_s(interpretacion, vuelta) + retraso_s
        ),
    )


def _adelanto_s(interpretacion: Interpretacion, vuelta: int) -> float:
    """Cuanto va el eje del audio por delante del eje del cabezal en esa vuelta.

    El silencio de cabecera ENTERO -cabecera tecnica mas cuenta atras-, mas lo que
    ocupan las vueltas anteriores, menos el instante en que empieza el tramo, que
    es donde el cabezal arranca cuando la pasada no estudia desde el compas 1.

    La cabecera tecnica entra desde la T6d: la cadena ya no deja correr el cabezal
    durante el llenado de la primera ventana, asi que el cabezal marca cero cuando
    suena la nota que la pieza escribe en cero. Antes de ese arreglo NO entraba, y
    las dos cosas son coherentes: lo que se traduce es la cadena que hay.

    El tramo se mide con `pulsos_del_compas`, que es el mismo ayudante con el que
    `SesionDeEstudio._inicio_s` coloca el cabezal, y no repitiendo la aritmetica
    del veredicto: asi la cuenta de las pruebas llega por otro camino que la del
    modulo que se prueba.
    """
    pieza = interpretacion.pieza
    factor = interpretacion.factor_tempo
    desde, _ = pulsos_del_compas(pieza, interpretacion.primer_compas)
    _, hasta = pulsos_del_compas(pieza, interpretacion.ultimo_compas)
    inicio_tramo_s = pulsos_a_segundos(desde, pieza.tempo) / factor
    tramo_s = pulsos_a_segundos(hasta - desde, pieza.tempo) / factor
    cuenta_atras = interpretacion.segundos_de_cuenta_atras
    return (
        interpretacion.silencio_de_cabecera_s
        + (vuelta - 1) * (cuenta_atras + tramo_s)
        - inicio_tramo_s
    )


def _registro(*reportes: ReporteDeLaCadena) -> RegistroDeLaCadena:
    """Un registro de mentira con los reportes dados y nada mas dentro."""
    return RegistroDeLaCadena(reportes=tuple(reportes), vueltas=(), estado_final=None)


def _todo_reportado(
    interpretacion: Interpretacion, retraso_s: float = 0.0, saltar=()
) -> RegistroDeLaCadena:
    """El registro de una cadena que lo vio todo, menos los `(vuelta, indice)` de
    `saltar`."""
    vueltas = _vueltas_de(interpretacion)
    return _registro(
        *(
            _reporte(interpretacion, evento, vuelta, retraso_s)
            for evento, vuelta in zip(interpretacion.eventos, vueltas, strict=True)
            if (vuelta, evento.indice_pretendido) not in saltar
        )
    )


# -- lo que la cadena vio -----------------------------------------------------


def test_sin_perdidas_cuando_todo_se_reporto():
    """Cada evento con su reporte a 30 ms: no hay nada perdido ni inventado."""
    interpretacion = _interpretacion()
    veredicto = juzgar(interpretacion, _todo_reportado(interpretacion, 0.030))

    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.notas_de_la_pieza == 8
    assert veredicto.notas_tocadas == 8


def test_la_nota_no_reportada_sale_como_perdida_con_su_vuelta():
    """La perdida lleva la vuelta dentro, porque los indices se repiten.

    Con dos vueltas, «se perdio la nota 3» no distingue la vuelta 1 de la 2, y el
    bucle es el caso en el que la cadena pierde notas de verdad.
    """
    interpretacion = _interpretacion(repeticiones=2)
    veredicto = juzgar(interpretacion, _todo_reportado(interpretacion, saltar={(2, 3)}))

    assert veredicto.perdidas == ((2, 3),)
    assert veredicto.inventadas == 0
    assert veredicto.notas_tocadas == 16


def test_el_reporte_sin_evento_sale_como_inventado():
    """Un reporte de una nota que nadie toco es una nota inventada."""
    interpretacion = _interpretacion(ultimo_compas=1)
    sobrante = _reporte(
        interpretacion, interpretacion.eventos[0], vuelta=1, indice=5, midi=64
    )
    registro = _registro(*_todo_reportado(interpretacion).reportes, sobrante)

    veredicto = juzgar(interpretacion, registro)

    assert veredicto.notas_tocadas == 4
    assert veredicto.inventadas == 1
    assert veredicto.perdidas == ()


def test_el_reporte_de_otra_altura_sale_como_mal_adjudicado():
    """La cadena vio el ataque pero le puso otra altura: no es perdida, es mal
    adjudicada, y se firma con la altura que reporto."""
    interpretacion = _interpretacion()
    vueltas = _vueltas_de(interpretacion)
    reportes = [
        _reporte(
            interpretacion,
            evento,
            vuelta,
            midi=evento.midi + 3 if evento.indice_pretendido == 2 else None,
        )
        for evento, vuelta in zip(interpretacion.eventos, vueltas, strict=True)
    ]

    veredicto = juzgar(interpretacion, _registro(*reportes))

    esperado = interpretacion.eventos[2].midi + 3
    assert veredicto.mal_adjudicadas == ((1, 2, esperado),)
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0


# -- los milisegundos que la cadena añadio ------------------------------------


def test_el_desfase_lleva_signo():
    """Un valor absoluto esconderia la direccion, que es justo lo que diagnostica.

    Una cadena que reporta tarde y una que reporta pronto se arreglan por caminos
    distintos, y con el valor absoluto las dos salen iguales.
    """
    interpretacion = _interpretacion()

    tarde = juzgar(interpretacion, _todo_reportado(interpretacion, 0.040))
    pronto = juzgar(interpretacion, _todo_reportado(interpretacion, -0.040))

    assert tarde.desfase_introducido_ms == pytest.approx(40.0, abs=0.5)
    assert tarde.desfase_maximo_ms == pytest.approx(40.0, abs=0.5)
    assert pronto.desfase_introducido_ms == pytest.approx(-40.0, abs=0.5)
    assert pronto.desfase_maximo_ms == pytest.approx(-40.0, abs=0.5)


def test_los_dos_ejes_de_tiempo_se_traducen_por_el_silencio_de_cabecera():
    """El eje del audio y el del cabezal se traducen por el silencio de cabecera
    ENTERO, cabecera tecnica incluida, y esa es la historia completa.

    **Hubo dos cadenas y esta prueba cambio de numero con ella.** Antes de la T6d,
    la cadena hacia `fijar_la_mirada(0.0)` en la muestra cero y el cabezal corria
    durante la cabecera tecnica, asi que NO habia que descontarla: medido, los
    reportes salian entre +71 y +188 ms de su ataque y descontandola salian entre
    +199 y +316, o sea 128 ms de sesgo inventado. La comprobacion independiente de
    entonces: el `desfase_s` que la cadena firmaba para la nota 0 era 148,3 ms =
    128 de cabecera + 20 de deteccion; si el cabezal hubiera ido 128 ms por
    detras, habria sido 20.

    La T6d cambio la cadena, y por una razon que no es de medida sino de diseño: la
    cabecera tecnica NO ES TIEMPO MUSICAL -es el silencio que el gemelo necesita
    para que la primera ventana llegue completa-, y cobrarsela al interprete hacia
    que el guitarrista PERFECTO tocara 128 ms tarde por construccion y que el
    oraculo sacara 0 notas limpias de 8. Ahora la cadena no mueve el cabezal
    durante ese llenado, el `desfase_s` de la nota 0 es +20,3 ms -la deteccion
    sola- y el oraculo saca 7 limpias de 8.

    Asi que hoy se descuenta el silencio de cabecera entero: la cabecera tecnica
    porque la cadena la alinea, y la cuenta atras porque el estudio congela el
    cabezal mientras dura. Esta prueba afirma los dos terminos con el mismo
    retraso de 40 ms: si uno de los dos se cae, su caso sale desviado por su
    cantidad. El de la cuenta atras lo ancla ademas, fuera de esta formula, la
    prueba que pasa por la cadena de verdad.
    """
    sin_cuenta = _interpretacion()
    con_cuenta = _interpretacion(segundos_de_cuenta_atras=1.0)

    assert sin_cuenta.silencio_de_cabecera_s == pytest.approx(0.128)
    assert con_cuenta.silencio_de_cabecera_s == pytest.approx(1.128)

    for interpretacion in (sin_cuenta, con_cuenta):
        veredicto = juzgar(interpretacion, _todo_reportado(interpretacion, 0.040))
        assert veredicto.desfase_introducido_ms == pytest.approx(40.0, abs=0.5)
        assert veredicto.perdidas == ()


def test_el_cabezal_vuelve_atras_en_cada_vuelta():
    """En un bucle, el reporte de la nota 0 de la vuelta 3 llega con el cabezal
    otra vez cerca de cero, no en el segundo diez.

    Medido en la cadena de verdad: con tres vueltas de la escala, los reportes de
    las vueltas 2 y 3 vuelven a empezar cerca de cero, porque lo que
    `instante_pasada_s` lleva es la POSICION del cabezal y el cabezal vuelve atras
    en cada vuelta. Un veredicto que no lo descontara daria por perdidas e
    inventadas todas las notas de las vueltas 2 y 3 -y el arreglo del bucle de la
    T7 no tendria con que medirse-.
    """
    interpretacion = _interpretacion(repeticiones=3)
    registro = _todo_reportado(interpretacion, 0.040)

    tercera = next(
        reporte
        for reporte in registro.reportes
        if reporte.repeticion == 3 and reporte.tocada.indice == 0
    )
    assert interpretacion.duracion_s == pytest.approx(3 * 4.8 + 0.128)
    assert tercera.instante_pasada_s < 1.0

    veredicto = juzgar(interpretacion, registro)

    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.notas_tocadas == 24
    assert veredicto.desfase_introducido_ms == pytest.approx(40.0, abs=0.5)


def test_la_tolerancia_es_el_techo_del_detector_y_no_un_numero_de_aqui():
    """La holgura de emparejamiento ES `VENTANA_ATAQUE_COMO_ONSET_S`.

    Esa constante es lo mas viejo que un ataque puede ser para que el detector lo
    firme como el onset de la pulsacion que esta resolviendo: justo lo que la
    cadena puede tardar en hablar de un ataque. Si alguien mueve el techo del
    detector, la holgura tiene que moverse con el, y un numero suelto en el
    veredicto se habria desacoplado en silencio.
    """
    assert TOLERANCIA_DE_EMPAREJAMIENTO_MS == pytest.approx(
        VENTANA_ATAQUE_COMO_ONSET_S * 1000.0
    )


def test_la_tolerancia_empareja_y_no_juzga():
    """La holgura es de EMPAREJAMIENTO, no de calidad, y se afirman sus dos lados.

    Su trabajo es decidir si el reporte X habla del ataque Y. Un reporte 20 ms por
    dentro del techo del detector es la misma nota y su retraso se anota; 20 ms
    por fuera ya no se puede afirmar que hable de ese ataque, y entonces la nota
    se perdio y el reporte se invento. Los dos lados se escriben RESPECTO de la
    constante, no con numeros: con literales, subir el techo del detector dejaba
    esta prueba verde midiendo otra cosa.
    """
    interpretacion = _interpretacion()
    margen_s = 0.020
    techo_s = TOLERANCIA_DE_EMPAREJAMIENTO_MS / 1000.0

    dentro = juzgar(interpretacion, _todo_reportado(interpretacion, techo_s - margen_s))
    assert dentro.perdidas == ()
    assert dentro.inventadas == 0
    assert dentro.desfase_introducido_ms == pytest.approx(
        TOLERANCIA_DE_EMPAREJAMIENTO_MS - 1000.0 * margen_s, abs=0.5
    )

    fuera = juzgar(interpretacion, _todo_reportado(interpretacion, techo_s + margen_s))
    assert len(fuera.perdidas) == 8
    assert fuera.inventadas == 8


def test_apretar_la_tolerancia_pone_el_oraculo_rojo_por_construccion():
    """Con los retrasos MEDIDOS de la cadena, una tolerancia de 120 ms pierde
    seis de ocho notas de un interprete perfecto.

    Los ocho retrasos son los que la sonda midio sobre `escala_de_ocho_notas` con
    `PERFECTO` y el salto de produccion: lo que la cadena tarda en PUBLICAR cada
    ataque, que es lo que `instante_pasada_s` lleva dentro. Seis de los ocho pasan
    de 120 ms.

    Esta prueba existe para que nadie «arregle» un oraculo rojo apretando la
    tolerancia: apretarla no mejora la cadena, hace que el veredicto deje de
    reconocer sus reportes, y entonces la prueba mide la tolerancia en vez de la
    cadena. Con la holgura en el techo del detector, las ocho se emparejan.
    """
    interpretacion = _interpretacion()
    vueltas = _vueltas_de(interpretacion)
    registro = _registro(
        *(
            _reporte(interpretacion, evento, vuelta, retraso_s=retraso_ms / 1000.0)
            for evento, vuelta, retraso_ms in zip(
                interpretacion.eventos, vueltas, RETRASOS_MEDIDOS_MS, strict=True
            )
        )
    )

    apretada = juzgar(interpretacion, registro, tolerancia_de_emparejamiento_ms=120.0)
    assert len(apretada.perdidas) == 6
    assert apretada.inventadas == 6

    honesta = juzgar(interpretacion, registro)
    assert honesta.perdidas == ()
    assert honesta.inventadas == 0
    assert honesta.limpio is True
    assert honesta.desfase_introducido_ms == pytest.approx(152.3, abs=0.5)
    assert honesta.desfase_maximo_ms == pytest.approx(188.3, abs=0.5)


# -- lo que no se juzga -------------------------------------------------------


def test_la_nota_repetida_consecutiva_se_excluye_en_vez_de_perderse():
    """`DetectorPulsaciones` declara que no distingue dos pulsaciones seguidas de
    la misma altura sin un hueco de tres cuadros sin nota creible, y una cuerda
    que sigue sonando puede no abrirlo nunca.

    Juzgarla pondria el oraculo rojo por una limitacion aceptada del programa en
    vez de por un defecto.
    """
    interpretacion = _interpretacion(pieza_con_nota_repetida())
    registro = _todo_reportado(interpretacion, saltar={(1, 1)})

    veredicto = juzgar(interpretacion, registro)

    assert veredicto.excluidas == ((1, 1),)
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.limpio is True


def test_las_notas_de_un_acorde_se_excluyen():
    """El detector de tono es monofonico y el interprete reduce el acorde a la
    nota mas grave: las otras no sonaron y no se pueden echar en falta."""
    interpretacion = _interpretacion(pieza_con_acorde())
    registro = _todo_reportado(interpretacion)

    veredicto = juzgar(interpretacion, registro)

    # Las notas 1 y 2 comparten `inicio_pulsos`; suena la mas grave, la 1.
    assert veredicto.excluidas == ((1, 2),)
    assert veredicto.perdidas == ()
    assert veredicto.notas_de_la_pieza == 4
    assert veredicto.notas_tocadas == 3


def test_las_exclusiones_salen_de_la_pieza_y_no_de_lo_que_la_cadena_hizo():
    """Las exclusiones no dependen de que la cadena reportara nada.

    Si se dedujeran de lo que la cadena hizo -«lo que no reporto, exclusion»- el
    veredicto no podria perder una nota nunca: con el registro VACIO, la nota
    repetida sigue excluida y las otras tres siguen perdidas.
    """
    interpretacion = _interpretacion(pieza_con_nota_repetida())

    veredicto = juzgar(interpretacion, _registro())

    assert veredicto.excluidas == ((1, 1),)
    assert veredicto.perdidas == ((1, 0), (1, 2), (1, 3))
    assert veredicto.limpio is False


# -- juez, no parte -----------------------------------------------------------


def test_el_veredicto_no_importa_reglas_del_seguidor():
    """El anti-objetivo de la spec §2, convertido en prueba.

    Se lee el modulo con `ast` y no con `in`, para que los docstrings puedan
    EXPLICAR por que no se consultan los veredictos de la cadena sin que la prueba
    se caiga por nombrarlos.

    Y se afirma por LISTA BLANCA, que es la correccion de la primera version: con
    una lista negra de siete nombres, `cents` no estaba en ella, asi que el
    veredicto podia leer `reporte.tocada.cents` y la prueba seguia verde; y un
    campo de decision nuevo en `NotaTocada` habria entrado sin que nadie se
    enterase. Ahora se afirma lo que el docstring del modulo promete -de una
    `NotaTocada` solo se leen `indice` y `midi`- y la lista de lo prohibido se
    DERIVA del dataclass. La prueba se rompe cuando alguien añade una lectura, no
    cuando alguien añade un campo a una lista que hay que mantener a mano.
    """
    arbol = ast.parse(FUENTE_DEL_VEREDICTO.read_text(encoding="utf-8"))

    importados = {
        alias.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "nucleo.piezas.seguimiento"
        for alias in nodo.names
    }
    assert importados <= {"NotaTocada"}

    # Lo que el modulo le lee a una `NotaTocada`: todo lo que cuelga de un
    # `.tocada`, se llegue a ella por `reporte.tocada` o por un `tocada` suelto.
    leido_de_la_tocada = {
        nodo.attr
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.Attribute) and _es_una_tocada(nodo.value)
    }
    assert leido_de_la_tocada <= HECHOS_DE_LA_TOCADA
    # Y es una lista blanca de verdad solo si de verdad lee algo: si un dia nadie
    # lee nada de la tocada, el emparejamiento por altura se ha ido con ello.
    assert leido_de_la_tocada == HECHOS_DE_LA_TOCADA

    usados = {
        nodo.attr for nodo in ast.walk(arbol) if isinstance(nodo, ast.Attribute)
    } | {nodo.id for nodo in ast.walk(arbol) if isinstance(nodo, ast.Name)}
    assert usados & (DECISIONES_DE_LA_TOCADA | REGLAS_DE_LA_CADENA) == set()


def _es_una_tocada(nodo: ast.expr) -> bool:
    """Si ese trozo de arbol es una `NotaTocada`: un `.tocada` o un `tocada`."""
    if isinstance(nodo, ast.Attribute):
        return nodo.attr == "tocada"
    return isinstance(nodo, ast.Name) and nodo.id == "tocada"


def test_un_veredicto_limpio_se_distingue_de_uno_sucio():
    """`limpio` es True solo si no se perdio, ni se invento, ni se mal adjudico
    nada: es lo que el ejecutable del escaparate mira para elegir su codigo de
    salida."""
    base = Veredicto(
        notas_de_la_pieza=8,
        notas_tocadas=8,
        perdidas=(),
        inventadas=0,
        mal_adjudicadas=(),
        excluidas=((1, 3),),
        desfase_introducido_ms=130.0,
        desfase_maximo_ms=188.0,
    )

    assert base.limpio is True
    assert base.a_dict()["limpio"] is True
    assert replace(base, perdidas=((1, 2),)).limpio is False
    assert replace(base, inventadas=1).limpio is False
    assert replace(base, mal_adjudicadas=((1, 2, 64),)).limpio is False


# -- el tramo que no empieza en el compas 1 -----------------------------------


def test_un_tramo_que_no_empieza_en_el_compas_uno_se_juzga_bien():
    """El cabezal de una pasada que estudia el compas 2 arranca en 2,4 s, no en 0.

    Es el caso NORMAL, no un borde: las secciones de una cancion casi nunca
    empiezan en el compas 1 y el escaparate practica por secciones. Antes de que
    `Interpretacion` registrara el tramo, el veredicto no podia saberlo y daba las
    cuatro notas por perdidas.

    La primera asercion es la que impide que esta prueba pase por casualidad: los
    reportes de este registro NO estan cerca de cero, estan cerca de 2,4 s, asi
    que un veredicto que no sumara el inicio del tramo no emparejaria ninguno.
    """
    interpretacion = _interpretacion(ultimo_compas=2, primer_compas=2)
    registro = _todo_reportado(interpretacion, 0.030)

    assert [evento.indice_pretendido for evento in interpretacion.eventos] == [4, 5, 6, 7]
    # 2,4 del inicio del tramo + los 30 ms de retraso del reporte, y nada mas.
    # Los 0,128 de cabecera tecnica estaban aqui antes de la T6d, cuando el
    # cabezal corria durante el llenado de la primera ventana; ahora la cadena lo
    # alinea, asi que la cabecera ya no esta en este eje. Si vuelve a aparecer, es
    # que alguien deshizo la alineacion.
    assert registro.reportes[0].instante_pasada_s == pytest.approx(2.4 + 0.030)

    veredicto = juzgar(interpretacion, registro)

    assert veredicto.limpio is True
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.notas_tocadas == 4
    assert veredicto.desfase_introducido_ms == pytest.approx(30.0, abs=0.5)


def test_una_seccion_entera_se_juzga_limpia_pasando_por_la_cadena_de_verdad():
    """La unica prueba del archivo que pasa por la cadena, y esta aqui por un
    motivo: un registro a mano demuestra que la traduccion es coherente consigo
    misma, no que coincida con lo que la cadena hace de verdad.

    Se estudia la seccion «Puente» de la pieza de demostracion -compases 7 a 9,
    doce notas, que no empieza en el compas 1- con el interprete perfecto. Medido
    con el cabezal alineado (T6d): veredicto limpio, **mediana +164,4 ms y maximo
    +204,6 ms**, y los dos se afirman con su margen y no solo contra el techo del
    detector, que dejaba 85 ms de holgura -bastante para no notar un error de eje-.
    Con el tramo sin registrar, esto daba doce perdidas y doce inventadas.

    No hay bucle a proposito: el defecto del bucle es de la T7 y esta prueba no es
    el sitio donde medirlo.
    """
    pieza = pieza_de_demostracion()
    interpretacion = interpretar(
        pieza, PERFECTO, primer_compas=7, ultimo_compas=9
    )
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(primer_compas=7, ultimo_compas=9, compases_de_cuenta_atras=0),
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)

    veredicto = juzgar(interpretacion, pasar_por_la_cadena(interpretacion, conductor))

    assert veredicto.notas_tocadas == 12
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.limpio is True
    assert veredicto.desfase_introducido_ms < TOLERANCIA_DE_EMPAREJAMIENTO_MS
    assert veredicto.desfase_introducido_ms == pytest.approx(164.4, abs=15.0)
    assert veredicto.desfase_maximo_ms == pytest.approx(204.6, abs=15.0)


def test_la_cuenta_atras_se_traduce_pasando_por_la_cadena_de_verdad():
    """El unico ancla EXTERNA del termino de la cuenta atras, y por eso existe.

    Las otras dos partes de la traduccion tienen ancla: el inicio del tramo la
    tiene en la asercion literal de `2,4 + 0,030` de la prueba del tramo y en la
    prueba de la seccion, y la vuelta la tiene en que el reporte de la tercera
    vuelta llega con el cabezal por debajo del segundo. El termino de la cuenta
    atras no tenia NINGUNA: `_adelanto_s`, el ayudante de las pruebas, replica la
    formula, asi que un mutante que quitara la cuenta atras del modulo Y del
    ayudante dejaba las pruebas verdes. Esta prueba lo mata, porque aqui los
    instantes los pone la cadena y no una copia de la formula.

    El compas de aviso del plan y la cuenta atras del gemelo tienen que ser la
    misma -es la condicion de uso que el modulo declara-, asi que los segundos se
    calculan con los mismos ayudantes de produccion con los que
    `SesionDeEstudio._segundos_de_cuenta_atras` los calcula.

    **Medido con el reloj de la cuenta atras ya exacto (T8): veredicto limpio,
    mediana +131,3 ms y maximo +206,3 ms**, y los dos se AFIRMAN con su margen, no
    solo contra el techo del detector. Afirmar solo que caben en los 250 ms dejaba
    79 ms de holgura, suficiente para tragarse un error de eje de 128 ms sin
    pestañear: es lo que dejo pasar que este docstring siguiera diciendo los
    numeros del eje viejo (+67,0 y +169,0) despues de alinear.

    **LOS NUMEROS SE MOVIERON EN LA T8 Y LO QUE MEDIAN ERA UN DEFECTO.** Eran
    +96,0 y +171,0, y traian dentro 35,3 ms de cabezal atrasado: el cuadro que
    agotaba la cuenta atras volvia con el reloj clavado en el inicio y la
    correspondencia sin fijar, asi que el reloj no arrancaba hasta el cuadro
    siguiente y ademas tiraba lo que sobraba del cuadro. Este archivo lo tenia
    escrito como una rareza aceptada -«el cabezal solo se suelta de la cuenta atras
    en un cuadro»- y era el defecto que el bucle con cuenta atras amplificaba a
    37 ms por vuelta. Arreglado en `SesionDeEstudio.procesar` y
    `_dar_la_vuelta`, el cabezal vale ahora `t - cuenta` AL MICROSEGUNDO
    (`tests/test_gemelo_cuenta_atras.py`), y lo que este suelo mide -la distancia
    entre el ataque y la publicacion- sube a +131,3 / +206,3.

    Sigue 21 ms por debajo de la mediana sin cuenta atras (+152,3) y eso NO es eje:
    con 2,4 s de silencio delante, el detector tiene nivel de referencia limpio y
    firma algunas notas un cuadro antes. El maximo, en cambio, sube por encima del
    de sin cuenta (+188,3), asi que no es un desplazamiento del eje -un eje movido
    movería los dos en el mismo sentido-.

    Con el termino de la cuenta atras quitado del modulo salen 8 perdidas y 8
    inventadas de 8.
    """
    pieza = escala_de_ocho_notas()
    compases_de_aviso = 1
    cuenta_atras_s = pulsos_a_segundos(
        pulsos_por_compas(pieza) * compases_de_aviso, pieza.tempo
    )
    interpretacion = interpretar(
        pieza, PERFECTO, segundos_de_cuenta_atras=cuenta_atras_s
    )
    # El audio lleva la cuenta atras DENTRO, delante de la cabecera tecnica.
    assert cuenta_atras_s == pytest.approx(2.4)
    assert interpretacion.silencio_de_cabecera_s == pytest.approx(2.4 + 0.128)

    estudio = SesionDeEstudio(
        pieza, PlanDePasada(compases_de_cuenta_atras=compases_de_aviso)
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)

    veredicto = juzgar(interpretacion, pasar_por_la_cadena(interpretacion, conductor))

    assert veredicto.notas_tocadas == 8
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 0
    assert veredicto.limpio is True
    assert veredicto.desfase_maximo_ms < TOLERANCIA_DE_EMPAREJAMIENTO_MS
    # Los dos numeros medidos, cada uno con su margen por los dos lados. El
    # margen es menos de un cuadro de analisis (21 ms), asi que ni un cuadro de
    # deriva pasa desapercibido, y mucho menos los 128 ms de la cabecera.
    assert veredicto.desfase_introducido_ms == pytest.approx(131.3, abs=15.0)
    assert veredicto.desfase_maximo_ms == pytest.approx(206.3, abs=15.0)


def test_la_primera_nota_del_tramo_no_se_excluye_por_la_nota_de_antes():
    """Una exclusion de mas tapa una perdida de verdad, que es lo peor que este
    modulo puede hacer.

    La pieza tiene la misma altura a los dos lados de la barra del compas 2. Si la
    regla de la nota repetida se leyera sobre la pieza ENTERA, al estudiar solo el
    compas 2 su primera nota saldria excluida -y por tanto imperdible- aunque en
    esa pasada nadie toque la nota de antes y el detector no tenga con que
    confundirla. El acotado por `tocados` no lo evita, porque el testigo de una
    repetida es ella misma.

    Las dos mitades de la prueba son la frontera: estudiando el compas 2, la nota 4
    se juzga y se puede perder; estudiando la pieza entera, se excluye de verdad.
    """
    pieza = _pieza_con_la_repeticion_en_la_barra()

    solo_el_segundo = _interpretacion(pieza, primer_compas=2, ultimo_compas=2)
    assert [evento.indice_pretendido for evento in solo_el_segundo.eventos] == [
        4,
        5,
        6,
        7,
    ]
    veredicto = juzgar(solo_el_segundo, _todo_reportado(solo_el_segundo, saltar={(1, 4)}))
    assert veredicto.excluidas == ()
    assert veredicto.perdidas == ((1, 4),)

    entera = _interpretacion(pieza)
    completo = juzgar(entera, _todo_reportado(entera, saltar={(1, 4)}))
    assert completo.excluidas == ((1, 4),)
    assert completo.perdidas == ()


def _pieza_con_la_repeticion_en_la_barra() -> Pieza:
    """Dos compases de 4/4 con la misma altura a los dos lados de la barra.

    La nota 3 cierra el primer compas y la 4 abre el segundo, las dos en 62. No
    esta en `piezas_de_prueba` porque es el caso de UNA prueba de este archivo: la
    frontera del tramo, no un caso que otras pruebas vayan a compartir.
    """
    midis = (55, 57, 59, 62, 62, 64, 65, 67)
    posiciones = digitar(list(midis), PERFILES["guitarra_estandar"])
    return Pieza(
        nombre="Pieza con la repeticion en la barra",
        perfil="guitarra_estandar",
        tempo=100,
        compas=(4, 4),
        notas=tuple(
            NotaEnPieza(
                midi=midi,
                cuerda=posicion.cuerda,
                traste=posicion.traste,
                inicio_pulsos=float(indice),
                duracion_pulsos=1.0,
            )
            for indice, (midi, posicion) in enumerate(zip(midis, posiciones, strict=True))
        ),
    )


def test_el_segundo_reporte_de_un_puesto_sale_como_inventado():
    """La cadena no publica dos veces la misma nota de la misma vuelta -la T4 lo
    tiene probado-, asi que el veredicto no busca el mas cercano entre varios: se
    queda con el primero del puesto.

    Esta prueba fija lo que pasa con el segundo, que es la unica forma de que esa
    decision este sujeta: se queda sin emparejar y cuenta como inventada. Dos
    reportes del mismo puesto significan que uno de los dos sobra.
    """
    interpretacion = _interpretacion()
    vueltas = _vueltas_de(interpretacion)
    primero = _reporte(interpretacion, interpretacion.eventos[0], vueltas[0], 0.030)
    repetido = _reporte(interpretacion, interpretacion.eventos[0], vueltas[0], 0.040)
    registro = _registro(*_todo_reportado(interpretacion, 0.030).reportes, repetido)

    veredicto = juzgar(interpretacion, registro)

    assert registro.reportes[0] == primero
    assert veredicto.perdidas == ()
    assert veredicto.inventadas == 1


def test_un_reporte_justo_en_el_techo_todavia_habla_del_ataque():
    """La igualdad exacta con la tolerancia empareja, y los dos lados se afirman.

    La tolerancia es el techo del detector: el ultimo instante en que la cadena
    todavia puede estar hablando de ese ataque, no el primero en que ya no. Las
    otras pruebas usan techo ± 20 ms y no tocaban este borde.

    Los instantes se eligen exactos en binario -ataque en 1,0 s, techo de 0,25 s-
    para que la resta del modulo no caiga en el lado equivocado por un bit de
    redondeo, que es lo que pasaria con los 0,128 s de la cabecera.
    """
    base = _interpretacion()
    evento = replace(base.eventos[0], instante_s=1.0)
    # Y sin silencio de cabecera, para que la traduccion del eje sea una resta de
    # cero y no meta un bit de redondeo en el borde que se mide aqui. Lo que esta
    # prueba afirma es la frontera de la tolerancia, no la traduccion.
    interpretacion = replace(base, eventos=(evento,), silencio_de_cabecera_s=0.0)
    techo_s = TOLERANCIA_DE_EMPAREJAMIENTO_MS / 1000.0
    assert techo_s == 0.25

    def veredicto_con(instante_pasada_s: float) -> Veredicto:
        return juzgar(
            interpretacion,
            _registro(
                ReporteDeLaCadena(
                    repeticion=1,
                    tocada=NotaTocada(
                        indice=evento.indice_pretendido,
                        midi=evento.midi,
                        cents=0.0,
                        desfase_s=None,
                        clasificacion=None,
                        acertada=True,
                        afinada=True,
                    ),
                    instante_pasada_s=instante_pasada_s,
                )
            ),
        )

    justo = veredicto_con(1.0 + techo_s)
    assert justo.perdidas == ()
    assert justo.inventadas == 0
    assert justo.desfase_introducido_ms == pytest.approx(250.0)

    pasado = veredicto_con(1.0 + techo_s + 1e-6)
    assert pasado.perdidas == ((1, 0),)
    assert pasado.inventadas == 1
