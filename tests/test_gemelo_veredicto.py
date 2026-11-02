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

from nucleo.afinaciones import PERFILES
from nucleo.gemelo.cadena import RegistroDeLaCadena, ReporteDeLaCadena
from nucleo.gemelo.interprete import (
    VENTANAS_DE_CABECERA,
    Interpretacion,
    interpretar,
)
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import (
    escala_de_ocho_notas,
    pieza_con_acorde,
    pieza_con_nota_repetida,
)
from nucleo.gemelo.veredicto import Veredicto, juzgar
from nucleo.piezas.compases import pulsos_por_compas, total_de_compases
from nucleo.piezas.modelo import pulsos_a_segundos
from nucleo.piezas.seguimiento import NotaTocada

FUENTE_DEL_VEREDICTO = (
    Path(__file__).resolve().parents[1] / "nucleo/gemelo/veredicto.py"
)

# Lo que la cadena DECIDE y el veredicto no tiene derecho a consultar. Son campos
# de `NotaTocada` y funciones del seguidor: un veredicto que los leyera estaria
# preguntandole a la cadena si la cadena lo hizo bien.
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

    La cuenta atras -la parte del silencio de cabecera que no es tecnica- mas lo
    que ocupan las vueltas anteriores. El tramo se mide de la PIEZA, con los
    ayudantes de produccion, y no de `duracion_s`: asi la cuenta de las pruebas no
    es la misma cuenta que hace el veredicto.
    """
    ventana = PERFILES[interpretacion.pieza.perfil].tamano_ventana(
        interpretacion.frecuencia_muestreo
    )
    tecnica = VENTANAS_DE_CABECERA * ventana / interpretacion.frecuencia_muestreo
    cuenta_atras = interpretacion.silencio_de_cabecera_s - tecnica
    pieza = interpretacion.pieza
    tramo_s = pulsos_a_segundos(
        total_de_compases(pieza) * pulsos_por_compas(pieza), pieza.tempo
    )
    return cuenta_atras + (vuelta - 1) * (cuenta_atras + tramo_s)


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


def test_la_tolerancia_empareja_y_no_juzga():
    """120 ms es holgura de EMPAREJAMIENTO, no de calidad.

    Su trabajo es decidir si el reporte X habla del ataque Y. Un reporte a 100 ms
    es la misma nota y su retraso se anota; a 130 ms ya no se puede afirmar que
    hable de ese ataque, y entonces la nota se perdio y el reporte se invento.
    """
    interpretacion = _interpretacion()

    dentro = juzgar(interpretacion, _todo_reportado(interpretacion, 0.100))
    assert dentro.perdidas == ()
    assert dentro.inventadas == 0
    assert dentro.desfase_introducido_ms == pytest.approx(100.0, abs=0.5)

    fuera = juzgar(interpretacion, _todo_reportado(interpretacion, 0.130))
    assert len(fuera.perdidas) == 8
    assert fuera.inventadas == 8


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
