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
from dataclasses import replace
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
from nucleo.piezas.compases import pulsos_del_compas
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio
from nucleo.piezas.modelo import pulsos_a_segundos
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
RETRASOS_MEDIDOS_MS = (188.3, 71.3, 164.3, 131.3, 98.3, 128.3, 74.3, 167.3)

DECISIONES_DE_LA_CADENA = frozenset(
    {
        "acertada",
        "afinada",
        "clasificacion",
        "_clasificar",
        "ventana_de_acierto",
        "esta_afinada",
        "desfase_s",
    }
)


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

    La cuenta atras, mas lo que ocupan las vueltas anteriores, menos el instante
    en que empieza el tramo -que es donde el cabezal arranca cuando la pasada no
    estudia desde el compas 1-. La cabecera tecnica NO entra: durante ella el
    cabezal ya corre.

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
    return cuenta_atras + (vuelta - 1) * (cuenta_atras + tramo_s) - inicio_tramo_s


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
    """Un valor absoluto escondería la direccion, que es justo lo que diagnostica.

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


def test_los_dos_ejes_de_tiempo_se_traducen_sin_sesgo():
    """El eje del audio y el de la pasada se traducen por la CUENTA ATRAS, y no
    por el silencio de cabecera entero.

    Medido sobre la cadena de verdad (escala de ocho notas, `PERFECTO`, salto de
    produccion): el reloj de la pasada arranca en la muestra cero -la cadena hace
    `fijar_la_mirada(0.0)`- y avanza 1:1 con el audio, cabecera tecnica incluida,
    porque durante esos 128 ms el cabezal ya corre. Los reportes salen entonces
    entre 71 y 188 ms despues de su ataque, mediana 130, que es la latencia real
    del detector. Restando la cabecera entera salian entre 199 y 316, o sea 128 ms
    de sesgo inventado por la traduccion, por encima del techo declarado del
    detector.

    La cuenta atras es otra cosa: el estudio CONGELA el cabezal mientras dura
    (`SesionDeEstudio.avanzar` recoloca el reloj en el inicio en cada mirada), asi
    que ahi los dos relojes si se separan, y por eso es la unica parte del
    silencio de cabecera que se descuenta. Esta prueba afirma los dos casos con el
    mismo retraso de 40 ms: si la traduccion se equivoca, uno de los dos sale
    desviado por su termino.
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
    cinco de ocho notas de un interprete perfecto.

    Los ocho retrasos son los que la sonda midio sobre `escala_de_ocho_notas` con
    `PERFECTO` y el salto de produccion: lo que la cadena tarda en PUBLICAR cada
    ataque, que es lo que `instante_pasada_s` lleva dentro. Cinco de los ocho pasan
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
    assert len(apretada.perdidas) == 5
    assert apretada.inventadas == 5

    honesta = juzgar(interpretacion, registro)
    assert honesta.perdidas == ()
    assert honesta.inventadas == 0
    assert honesta.limpio is True
    assert honesta.desfase_introducido_ms == pytest.approx(129.8, abs=0.5)
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
    EXPLICAR por que no se consultan `acertada` ni la clasificacion sin que la
    prueba se caiga por nombrarlas. Lo que se vigila son los nombres que el codigo
    usa de verdad: de `nucleo.piezas.seguimiento` solo puede entrar el tipo
    `NotaTocada`, y de una `NotaTocada` solo se pueden leer `indice` y `midi`.
    Cualquier otro campo es una decision de la cadena, y un veredicto que
    consultara las decisiones de la cadena se estaria dando la razon.
    """
    arbol = ast.parse(FUENTE_DEL_VEREDICTO.read_text(encoding="utf-8"))

    importados = {
        alias.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "nucleo.piezas.seguimiento"
        for alias in nodo.names
    }
    assert importados <= {"NotaTocada"}

    usados = {
        nodo.attr for nodo in ast.walk(arbol) if isinstance(nodo, ast.Attribute)
    } | {nodo.id for nodo in ast.walk(arbol) if isinstance(nodo, ast.Name)}
    assert usados & DECISIONES_DE_LA_CADENA == set()


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
    # 2,4 del inicio del tramo + 0,128 de cabecera tecnica (que el cabezal
    # recorre) + los 30 ms de retraso del reporte.
    assert registro.reportes[0].instante_pasada_s == pytest.approx(2.4 + 0.128 + 0.030)

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
    doce notas, que no empieza en el compas 1- con el interprete perfecto. Medido:
    veredicto limpio, mediana +164,4 ms y maximo +204,6 ms, los dos por debajo del
    techo del detector. Con el tramo sin registrar, esto daba doce perdidas y doce
    inventadas.

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
