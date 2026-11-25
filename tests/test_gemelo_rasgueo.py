# tests/test_gemelo_rasgueo.py
"""El gemelo rasgueando: el grifo de audio crudo y el acorde recorriendo la cadena.

El grifo (`GrifoDeAudio`) es el equivalente de `Sesion.leer_ventana_cruda` para el
gemelo: el seguidor cobra el resto de un acorde midiendo PRESENCIA sobre 8192
muestras, y esa ventana no viaja dentro del `ResultadoAnalisis`, asi que se pide
aparte. Lo que las primeras pruebas vigilan es que lo que el grifo sirve sea el
audio que de verdad acababa de sonar, porque un grifo que sirviera siempre la
misma ventana dejaria el cobro por presencia en verde sin estar mirando el acorde.

**Y ESTE ARCHIVO ES LA RAZON DE QUE EL GEMELO SEPA RASGUEAR.** En cuanto supo, lo
primero que encontro fue que el carril no oia los acordes EN ABSOLUTO: los dos
caminos de `DetectorPulsaciones` necesitan una nota creible y un acorde no la da,
asi que una pasada de dos acordes abiertos no producia ni un reporte. Ninguna
prueba podia verlo porque todas las del cobro por presencia fabricaban el ataque a
mano (`tests/test_seguimiento_acordes.py`). De ahi
`SeguidorPieza._cobrar_el_rasgueo_sin_altura`, y de ahi que lo que se afirme abajo
sean numeros MEDIDOS de las presencias y no un «sale limpio».
"""

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.acordes import VENTANA_ACORDES, DetectorAcordes
from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.gemelo.cadena import GrifoDeAudio, pasar_por_la_cadena
from nucleo.gemelo.interprete import interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas, pieza_de_rasgueos
from nucleo.gemelo.veredicto import juzgar
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio

# Dos compases: dos acordes, uno de cada clave. Bastan para un cambio, que es lo
# que el ejercicio practica, y recorrer la pieza entera serian 44 notas de audio
# por cada prueba sin comprobar nada mas.
ULTIMO_COMPAS = 2


def interpretacion_de_rasgueos(**extras):
    """El oraculo rasgueando dos acordes abiertos."""
    pieza = pieza_de_rasgueos()
    return pieza, interpretar(pieza, PERFECTO, ultimo_compas=ULTIMO_COMPAS, **extras)


def conducir_con_grifo(pieza, interpretacion):
    """La pasada completa: el conductor de verdad, con el grifo en los dos sitios.

    El grifo va a la `SesionDeEstudio` -de donde el seguidor lo saca- Y a
    `pasar_por_la_cadena`, que es quien le mueve el cursor cuadro a cuadro. Es la
    condicion de uso que `GrifoDeAudio` declara y que ninguna de las dos mitades
    puede comprobar por su cuenta.
    """
    grifo = GrifoDeAudio(interpretacion)
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(ultimo_compas=ULTIMO_COMPAS, compases_de_cuenta_atras=0),
        detector_acordes=grifo.detector,
        proveedor_de_muestras=grifo.leer,
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    return pasar_por_la_cadena(interpretacion, conductor, grifo=grifo)


# -- el grifo -----------------------------------------------------------------


def test_el_grifo_no_sirve_una_ventana_a_medio_llenar():
    """`None` y no ceros: una ventana incompleta no se puede juzgar.

    Es lo que hace `Sesion.leer_ventana_cruda` mientras el bufer de la captura no
    tiene bastantes muestras, y quien la pida tiene que poder distinguir "no hay
    bastante" de "hay silencio".
    """
    _, interpretacion = interpretacion_de_rasgueos()
    grifo = GrifoDeAudio(interpretacion)

    grifo.colocar(VENTANA_ACORDES - 1)
    assert grifo.leer(VENTANA_ACORDES) is None

    grifo.colocar(VENTANA_ACORDES)
    servida = grifo.leer(VENTANA_ACORDES)
    assert servida is not None
    assert servida.size == VENTANA_ACORDES


def test_el_grifo_sirve_las_ultimas_muestras_hasta_el_cursor():
    """Las de ANTES del cursor, que es el final del cuadro en curso."""
    _, interpretacion = interpretacion_de_rasgueos()
    grifo = GrifoDeAudio(interpretacion)
    fin = 3 * VENTANA_ACORDES

    grifo.colocar(fin)

    assert np.array_equal(
        grifo.leer(VENTANA_ACORDES), interpretacion.muestras[fin - VENTANA_ACORDES : fin]
    )


def test_pasado_el_final_del_audio_el_grifo_sirve_la_cola_y_ceros():
    """Es lo que pasa en vivo: el guitarrista para y el cable sigue entregando.

    Devolver `None` ahi seria decir "no hay bastante audio" de un momento en que
    lo que hay es silencio, que es un dato distinto.
    """
    _, interpretacion = interpretacion_de_rasgueos()
    grifo = GrifoDeAudio(interpretacion)
    total = interpretacion.muestras.size
    sobran = VENTANA_ACORDES // 4

    grifo.colocar(total + sobran)
    servida = grifo.leer(VENTANA_ACORDES)

    assert servida is not None
    reales = VENTANA_ACORDES - sobran
    assert np.array_equal(servida[:reales], interpretacion.muestras[total - reales :])
    assert not servida[reales:].any()


def test_el_grifo_monta_el_detector_con_el_perfil_de_la_pieza():
    """De el sale el rango de notas sobre el que la presencia se normaliza."""
    pieza, interpretacion = interpretacion_de_rasgueos()
    grifo = GrifoDeAudio(interpretacion)

    assert isinstance(grifo.detector, DetectorAcordes)
    assert grifo.detector.perfil is PERFILES[pieza.perfil]
    assert grifo.detector.frecuencia_muestreo == interpretacion.frecuencia_muestreo


def test_el_detector_que_se_le_da_al_grifo_es_el_que_usa():
    """Quien quiera otro umbral de presencia lo puede inyectar."""
    pieza, interpretacion = interpretacion_de_rasgueos()
    mio = DetectorAcordes(PERFILES[pieza.perfil], umbral_presencia=0.9)

    grifo = GrifoDeAudio(interpretacion, detector=mio)

    assert grifo.detector is mio


def test_la_cadena_mueve_el_cursor_del_grifo_con_los_cuadros():
    """Sin esto el seguidor mediria siempre la misma ventana.

    Se comprueba con un grifo espia, y lo que se afirma es que el cursor acaba en
    el final de la ultima ventana del recorrido: no se le puede pedir al seguidor
    que lo confiese, porque solo lo consulta cuando cobra un acorde.
    """
    pieza, interpretacion = interpretacion_de_rasgueos()
    grifo = GrifoDeAudio(interpretacion)
    cursores: list[int] = []
    original = grifo.colocar

    def espiar(fin: int) -> None:
        cursores.append(fin)
        original(fin)

    grifo.colocar = espiar  # type: ignore[method-assign]
    estudio = SesionDeEstudio(
        pieza, PlanDePasada(ultimo_compas=ULTIMO_COMPAS, compases_de_cuenta_atras=0)
    )
    estudio.arrancar()
    pasar_por_la_cadena(
        interpretacion,
        ConductorDeEstudio(estudio, al_cambiar_repeticion=None),
        grifo=grifo,
    )

    assert len(cursores) > 10
    assert cursores == sorted(cursores)
    assert cursores[-1] >= interpretacion.muestras.size


def test_sin_grifo_la_cadena_sigue_recorriendo_el_audio():
    """El parametro es opcional: una pieza sin acordes no necesita ninguno."""
    pieza, interpretacion = interpretacion_de_rasgueos()
    estudio = SesionDeEstudio(
        pieza, PlanDePasada(ultimo_compas=ULTIMO_COMPAS, compases_de_cuenta_atras=0)
    )
    estudio.arrancar()

    registro = pasar_por_la_cadena(
        interpretacion, ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    )

    assert registro.estado_final is not None


# -- el acorde recorriendo la cadena ------------------------------------------


def test_el_oraculo_rasguea_los_dos_acordes_completos():
    """Once cuerdas de verdad -cinco del Do y seis del Sol-, ninguna fallada."""
    _, interpretacion = interpretacion_de_rasgueos()

    assert len(interpretacion.eventos) == 11
    por_instante = sorted(evento.instante_s for evento in interpretacion.eventos)
    assert por_instante == sorted(set(por_instante))


def test_el_carril_cobra_el_rasgueo_entero_menos_la_tercera_del_sol():
    """El camino completo de la etapa 2b sin cable, con su limite MEDIDO.

    Lo que recorre: el gemelo rasguea, `DetectorAtaques` oye el gesto por nivel,
    la altura NO cuaja (un acorde no tiene una), `_cobrar_el_rasgueo_sin_altura`
    lo resuelve por presencia contra la ventana cruda del grifo y el veredicto
    compara las once cuerdas que sonaron con las que la cadena reporto.

    **DIEZ DE ONCE, Y LA QUE FALTA ES UNA MEDIDA, no un defecto de este camino.**
    En el cuadro en que el ataque caduca -0,25 s despues del rasgueo,
    `VENTANA_ATAQUE_COMO_ONSET_S`- las presencias son

        Do mayor (5 cuerdas)   48:0,56  52:0,70  55:0,88  60:1,00  64:0,73
        Sol mayor (6 cuerdas)  43:0,87  47:0,40  50:0,55  55:0,94  59:0,47  67:0,70

    contra `UMBRAL_PRESENCIA = 0,45`. El Do entra completo con holgura; en el Sol
    las DOS terceras -B2 y B3- caen al borde y la grave se queda fuera. La causa
    se lee en los numeros: el Sol esta doblado en tres octavas (43, 55, 67), la
    saliencia se normaliza contra la nota mas fuerte de todo el mastil y las
    terceras pierden esa carrera. Medio segundo mas tarde las dos pasan de 0,45,
    asi que es cuando se mira y no si suena.

    Esta prueba fija ese numero para que un cambio lo mueva a la vista. Lo que
    hay que hacer con el -recalibrar el umbral con la guitarra del usuario
    (`herramientas/calibrar_presencia.py`), o dejar el grupo abierto unos cuadros
    en vez de mirar una sola ventana- es una decision con medidas de guitarra de
    verdad detras, y no se toma desde audio sintetico.
    """
    pieza, interpretacion = interpretacion_de_rasgueos()

    registro = conducir_con_grifo(pieza, interpretacion)
    veredicto = juzgar(interpretacion, registro)

    assert veredicto.inventadas == 0
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.notas_tocadas == 11
    # La nota 6 es el B2 del Sol: la tercera grave, con 0,40 de presencia.
    assert veredicto.perdidas == ((1, 6),)
    assert int(pieza.notas[6].midi) == 47


def test_el_rasgueo_llega_al_carril_con_su_ritmo_medido():
    """Una cuerda por acorde trae desfase; las demas, presencia sin tiempo.

    El gesto fue uno, asi que da UNA medida de tiempo. Si todas trajeran desfase,
    un acorde de seis cuerdas pesaria seis veces en la regularidad del compas; si
    no lo trajera ninguna, un ejercicio de cambios -donde lo que se mide es cuanto
    tardas en cambiar- se quedaria sin ritmo que medir.
    """
    pieza, interpretacion = interpretacion_de_rasgueos()

    registro = conducir_con_grifo(pieza, interpretacion)

    con_tiempo = [
        reporte for reporte in registro.reportes if reporte.tocada.desfase_s is not None
    ]
    assert len(con_tiempo) == 2
    assert all(not reporte.tocada.por_presencia for reporte in con_tiempo)
    assert all(reporte.tocada.clasificacion is not None for reporte in con_tiempo)
    # Y son las dos cuerdas mas graves de cada acorde: la primera del grupo que
    # la presencia confirma.
    assert [reporte.tocada.indice for reporte in con_tiempo] == [0, 5]
    # El oraculo toca a tiempo, asi que el desfase que queda es el del detector.
    assert all(
        abs(reporte.tocada.desfase_s) < VENTANA_ATAQUE_COMO_ONSET_S
        for reporte in con_tiempo
    )
    del pieza


def test_sin_altura_que_leer_una_nota_suelta_sigue_sin_reportarse():
    """El ataque de energia no prueba por si solo que haya sonado nada.

    Un golpe cuya altura no cuaja lo produce tambien un apagado o un roce. Sobre
    un acorde la presencia lo resuelve -verifica las cuerdas escritas-, pero con
    una nota suelta no hay nada que verificar: la presencia de una sola nota no la
    distingue de un armonico de su vecina. Asi que ese camino no se abre, y una
    pieza monofonica se comporta exactamente como antes de la etapa 2b.
    """
    pieza = escala_de_ocho_notas()
    interpretacion = interpretar(pieza, PERFECTO)
    grifo = GrifoDeAudio(interpretacion)
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(compases_de_cuenta_atras=0),
        detector_acordes=grifo.detector,
        proveedor_de_muestras=grifo.leer,
    )
    estudio.arrancar()

    registro = pasar_por_la_cadena(
        interpretacion,
        ConductorDeEstudio(estudio, al_cambiar_repeticion=None),
        grifo=grifo,
    )

    # Ocho notas sueltas, ocho reportes con altura leida y ninguno por presencia.
    assert len(registro.reportes) == 8
    assert all(not reporte.tocada.por_presencia for reporte in registro.reportes)


def test_sin_cobro_de_acordes_el_veredicto_pierde_las_cuerdas_de_arriba():
    """Y es LO QUE TIENE QUE PASAR: el gemelo lo delata en vez de taparlo.

    Un carril armado sin detector de acordes cobra una nota por ataque, asi que de
    cada rasgueo se queda una cuerda. Antes de la etapa 2b el veredicto excluia las
    demas y esta pasada salia igual de limpia que la de arriba: dos cadenas muy
    distintas firmaban el mismo veredicto, que es exactamente lo que un gemelo no
    puede hacer.
    """
    pieza, interpretacion = interpretacion_de_rasgueos()
    estudio = SesionDeEstudio(
        pieza, PlanDePasada(ultimo_compas=ULTIMO_COMPAS, compases_de_cuenta_atras=0)
    )
    estudio.arrancar()

    registro = pasar_por_la_cadena(
        interpretacion, ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    )
    veredicto = juzgar(interpretacion, registro)

    assert veredicto.limpio is False
    assert len(veredicto.perdidas) == 11
