"""La sesion de estudio: el plan, el reloj de la pasada y lo que ve la interfaz.

Ni una espera real: el reloj se mueve a mano con `avanzar_a`, igual que en
`tests/test_seguimiento_pieza.py`.
"""

import threading

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import Pulsacion
from nucleo.piezas.estudio import (
    FACTOR_MAXIMO,
    FACTOR_MINIMO,
    PASADAS_BUENAS_PARA_SUBIR,
    PASO_DEL_FACTOR,
    UMBRAL_PARA_BAJAR,
    UMBRAL_PARA_SUBIR,
    CompasDelInforme,
    HistorialDeEstudio,
    InformeDePasada,
    PlanDePasada,
    SesionDeEstudio,
    proporcion_limpia,
    validar_plan,
)
from nucleo.piezas.modelo import NotaEnPieza, Pieza


def pieza_de(inicios, tempo=60, compas=(4, 4), **extra):
    """Una nota de un pulso en cada inicio. A 60 ppm, un pulso es un segundo."""
    notas = tuple(
        NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i in inicios
    )
    return Pieza(
        nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=compas,
        notas=notas, **extra,
    )


def pieza_de_doce_compases():
    """Doce compases de 4/4 con una nota al principio de cada uno."""
    return pieza_de([i * 4 for i in range(12)])


def test_el_plan_por_defecto_es_la_pieza_entera_a_tempo_escrito():
    plan = PlanDePasada()
    assert plan.primer_compas == 1
    assert plan.ultimo_compas is None
    assert plan.factor_tempo == 1.0
    assert plan.en_bucle is False
    assert plan.con_click is False
    assert plan.tempo_automatico is False


def test_el_plan_sin_ultimo_compas_se_resuelve_al_ultimo_de_la_pieza():
    resuelto = validar_plan(pieza_de_doce_compases(), PlanDePasada())
    assert resuelto.ultimo_compas == 12


def test_un_factor_por_debajo_del_suelo_se_rechaza():
    with pytest.raises(ValueError, match="40"):
        PlanDePasada(factor_tempo=0.2)


def test_un_factor_por_encima_del_tempo_escrito_se_rechaza():
    with pytest.raises(ValueError, match="100"):
        PlanDePasada(factor_tempo=1.5)


def test_el_ultimo_compas_antes_del_primero_se_rechaza():
    with pytest.raises(ValueError, match="compas"):
        PlanDePasada(primer_compas=8, ultimo_compas=3)


def test_un_compas_fuera_de_la_pieza_se_rechaza_con_los_dos_numeros():
    pieza = pieza_de_doce_compases()
    with pytest.raises(ValueError, match="20"):
        validar_plan(pieza, PlanDePasada(primer_compas=20))
    with pytest.raises(ValueError, match="99"):
        validar_plan(pieza, PlanDePasada(ultimo_compas=99))


def test_la_pasada_arranca_al_principio_del_primer_compas_del_plan():
    # El compas 5 de una pieza de 4/4 a 60 ppm empieza en el pulso 16, es decir
    # en el segundo 16.
    sesion = SesionDeEstudio(pieza_de_doce_compases(), PlanDePasada(primer_compas=5))
    assert sesion.estado.carril.instante_s == pytest.approx(16.0)
    assert sesion.estado.compas_en_curso == 5


def test_el_estado_dice_en_que_compas_va_el_cabezal():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.colocar_en(9.0)
    assert sesion.estado.compas_en_curso == 3
    assert sesion.estado.instante_pulsos == pytest.approx(9.0)


def test_al_cincuenta_por_ciento_el_mismo_compas_llega_al_doble_de_segundos():
    sesion = SesionDeEstudio(pieza_de_doce_compases(), PlanDePasada(factor_tempo=0.5))
    sesion.colocar_en(9.0)
    # Nueve segundos de pasada son 4,5 pulsos de la pieza: todavia el compas 2.
    assert sesion.estado.compas_en_curso == 2
    assert sesion.estado.instante_pulsos == pytest.approx(4.5)


def test_el_tempo_efectivo_es_lo_que_la_interfaz_usa_para_dibujar():
    sesion = SesionDeEstudio(pieza_de([0.0], tempo=120), PlanDePasada(factor_tempo=0.5))
    assert sesion.estado.tempo_efectivo == pytest.approx(60.0)


def test_el_estado_arrastra_los_avisos_de_la_pieza():
    pieza = pieza_de([0.0], ritmo_aproximado=True, compas_variable=True)
    estado = SesionDeEstudio(pieza).estado
    assert estado.ritmo_aproximado is True
    assert estado.compas_variable is True


def test_el_dict_del_estado_lleva_lo_del_carril_al_mismo_nivel():
    # La interfaz de la etapa 3a ya lee `instante_s`, `indice_actual`, `total`,
    # `completado` y `tocadas` del paquete del WebSocket: si esta etapa los
    # anidara dentro de "carril", habria que tocar `useCarril` sin ningun motivo.
    datos = SesionDeEstudio(pieza_de_doce_compases()).estado.a_dict()
    for clave in ("instante_s", "indice_actual", "total", "completado", "tocadas"):
        assert clave in datos
    assert datos["compas_en_curso"] == 1
    assert datos["total_de_compases"] == 12


def test_el_compas_en_curso_no_se_sale_del_tramo():
    # Los pulsos de un compas son un intervalo medio abierto: parado en el final
    # del compas 3 el reloj cae ya en el 4. Un bucle del 2 al 3 no puede decir
    # que va por el 4.
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=2, ultimo_compas=3)
    )
    sesion.colocar_en(12.0)
    assert sesion.estado.compas_en_curso == 3


def test_avanzar_suma_y_colocar_coloca():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.colocar_en(5.0)
    sesion.avanzar(2.0)
    assert sesion.estado.carril.instante_s == pytest.approx(7.0)
    sesion.colocar_en(2.0)
    assert sesion.estado.carril.instante_s == pytest.approx(2.0)


def test_una_pieza_sin_notas_no_rompe_la_sesion():
    estado = SesionDeEstudio(pieza_de([])).estado
    assert estado.total_de_compases == 0
    assert estado.compas_en_curso == 1
    assert estado.ultimo_compas == 0


def test_a_medio_tempo_el_primer_compas_del_plan_cae_al_doble_de_segundos():
    # El compas 5 empieza en el pulso 16: a tempo escrito, segundo 16; al 50 %,
    # segundo 32. Sin esta prueba nada fija la conversion de pulsos a segundos
    # de la pasada (la otra mitad la fija `instante_pulsos`).
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=5, factor_tempo=0.5)
    )
    assert sesion.estado.carril.instante_s == pytest.approx(32.0)
    assert sesion.estado.compas_en_curso == 5
    assert sesion.estado.instante_pulsos == pytest.approx(16.0)


def test_un_primer_compas_fuera_de_la_pieza_se_rechaza_nombrando_el_total():
    with pytest.raises(ValueError, match="12 compases"):
        validar_plan(pieza_de_doce_compases(), PlanDePasada(primer_compas=20))


def test_el_seguidor_de_la_sesion_recibe_el_factor_y_estira_la_duracion():
    # La pieza dura 45 pulsos. A tempo escrito el carril esta completo en el
    # segundo 60; al 50 % la pasada dura 90 s y a los 60 s sigue sin acabar.
    entera = SesionDeEstudio(pieza_de_doce_compases())
    entera.colocar_en(60.0)
    assert entera.estado.carril.completado is True
    lenta = SesionDeEstudio(pieza_de_doce_compases(), PlanDePasada(factor_tempo=0.5))
    lenta.colocar_en(60.0)
    assert lenta.estado.carril.completado is False


def test_validar_plan_en_una_pieza_sin_notas_da_un_ultimo_compas_entero():
    resuelto = validar_plan(pieza_de([]), PlanDePasada())
    assert resuelto.ultimo_compas == 0
    assert isinstance(resuelto.ultimo_compas, int)


def test_un_ultimo_compas_cero_en_una_pieza_con_compases_se_rechaza():
    with pytest.raises(ValueError, match="12 compases.*0"):
        validar_plan(pieza_de_doce_compases(), PlanDePasada(ultimo_compas=0))


def test_el_dict_del_plan_lleva_sus_siete_claves():
    plan = PlanDePasada(primer_compas=2, ultimo_compas=5, factor_tempo=0.75,
                        en_bucle=True, compases_de_cuenta_atras=2,
                        con_click=True, tempo_automatico=True)
    assert plan.a_dict() == {
        "primer_compas": 2,
        "ultimo_compas": 5,
        "factor_tempo": 0.75,
        "en_bucle": True,
        "compases_de_cuenta_atras": 2,
        "con_click": True,
        "tempo_automatico": True,
    }


def test_el_plan_y_el_estado_dicen_lo_mismo_del_ultimo_compas_de_una_pieza_vacia():
    sesion = SesionDeEstudio(pieza_de([]))
    assert sesion.plan.a_dict()["ultimo_compas"] == 0
    assert sesion.estado.a_dict()["ultimo_compas"] == 0


def test_un_primer_compas_menor_que_uno_se_rechaza():
    with pytest.raises(ValueError, match="primer compas"):
        PlanDePasada(primer_compas=0)


def test_unos_compases_de_cuenta_atras_negativos_se_rechazan():
    with pytest.raises(ValueError, match="cuenta atras"):
        PlanDePasada(compases_de_cuenta_atras=-1)


def test_un_delta_negativo_no_mueve_el_cabezal():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.colocar_en(5.0)
    sesion.avanzar(-3.0)
    assert sesion.estado.carril.instante_s == pytest.approx(5.0)


def test_las_constantes_del_contrato_tienen_nombre_y_valor_fijos():
    assert FACTOR_MINIMO == 0.40
    assert FACTOR_MAXIMO == 1.00
    assert PASO_DEL_FACTOR == 0.05


def test_procesar_mueve_el_carril_con_un_cuadro_de_analisis():
    sesion = SesionDeEstudio(pieza_de([0.0, 1.0]))
    sesion.colocar_en(0.0)
    silencio = ResultadoAnalisis(
        estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
        nota=None, cents=None, posiciones=(),
    )
    suena = ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=0.9, nivel_db=-25.0,
        nota="E2", cents=0.0, posiciones=(),
    )
    instante = 0.0
    for _ in range(3):
        sesion.procesar(silencio, instante)
        instante += 0.021
    for _ in range(12):
        sesion.procesar(suena, instante)
        instante += 0.021
    assert len(sesion.estado.carril.tocadas) == 1
    assert sesion.estado.carril.tocadas[0].acertada is True


# -- el informe por compases ------------------------------------------------


def suena(nota, cents=0.0):
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=0.9, nivel_db=-25.0,
        nota=nota, cents=cents, posiciones=(),
    )


SILENCIO = ResultadoAnalisis(
    estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
    nota=None, cents=None, posiciones=(),
)


def tocar(sesion, nota, en):
    """Toca `nota` alrededor del instante `en` del reloj de la PASADA.

    Mismo patron que `tests/test_seguimiento_pieza.py`: el reloj se coloca a mano
    antes del primer cuadro, porque si no el seguidor fijaria la
    correspondencia entre sus dos relojes en el primer cuadro de audio y `en` no
    significaria nada.
    """
    instante = en - 0.1
    sesion.colocar_en(instante)
    while instante < en:
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    for _ in range(12):
        sesion.procesar(suena(nota), instante)
        instante += 0.021


def compas_numero(informe, numero):
    return next(c for c in informe.compases if c.numero == numero)


def test_el_informe_cubre_el_tramo_del_plan_y_no_la_pieza_entera():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=3, ultimo_compas=5)
    )
    assert [c.numero for c in sesion.informe.compases] == [3, 4, 5]


def test_un_compas_tocado_a_tiempo_sale_acertado_y_a_tiempo():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    primero = compas_numero(sesion.informe, 1)
    assert primero.notas_escritas == 1
    assert primero.notas_medibles == 1
    assert primero.acertadas == 1
    assert primero.a_tiempo == 1
    assert primero.tarde == 0


def test_el_desfase_medio_lleva_signo_y_adelantarse_es_negativo():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=-0.3)
    assert compas_numero(sesion.informe, 1).desfase_medio_s < 0


def test_un_compas_que_nadie_toco_tiene_desfase_medio_none():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    assert compas_numero(sesion.informe, 4).desfase_medio_s is None


def test_de_un_acorde_solo_una_nota_es_medible_y_el_compas_queda_marcado():
    # Tres notas en el mismo instante: el detector es monofonico y lee una sola
    # altura, asi que las otras dos no se pueden medir por bien que se toquen.
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=c, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
        for m, c in ((40, 6), (47, 5), (52, 4))
    )
    pieza = Pieza(
        nombre="acorde", perfil="guitarra_estandar", tempo=60, compas=(4, 4), notas=notas
    )
    primero = compas_numero(SesionDeEstudio(pieza).informe, 1)
    assert primero.notas_escritas == 3
    assert primero.notas_medibles == 1
    assert primero.tiene_acordes is True


def test_un_compas_con_acordes_no_entra_en_la_proporcion_limpia():
    # La proporcion es la que alimenta la regla del tempo: si los compases con
    # acordes contaran, la regla bajaria el tempo para siempre en cualquier
    # cancion de Guitar Pro.
    acorde = tuple(
        NotaEnPieza(midi=m, cuerda=c, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
        for m, c in ((40, 6), (47, 5))
    )
    sola = (NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=4.0, duracion_pulsos=1.0),)
    pieza = Pieza(
        nombre="mixta", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
        notas=acorde + sola,
    )
    sesion = SesionDeEstudio(pieza)
    tocar(sesion, "E2", en=4.0)
    # Solo cuenta el compas 2, que es el unico sin acordes: una de una.
    assert proporcion_limpia(sesion.informe) == pytest.approx(1.0)


def test_una_pieza_entera_de_acordes_no_da_proporcion_y_no_miente():
    acorde = tuple(
        NotaEnPieza(midi=m, cuerda=c, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
        for m, c in ((40, 6), (47, 5))
    )
    pieza = Pieza(
        nombre="solo acordes", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
        notas=acorde,
    )
    assert proporcion_limpia(SesionDeEstudio(pieza).informe) is None


def test_el_informe_arrastra_el_aviso_del_ritmo_inventado():
    # En una tablatura de foro el ritmo lo infirio el lector de la etapa 3b:
    # presentar un desfase contra un ritmo inventado como diagnostico seria
    # mentira, asi que el aviso viaja con el informe.
    pieza = pieza_de([0.0], ritmo_aproximado=True)
    informe = SesionDeEstudio(pieza).informe
    assert informe.ritmo_aproximado is True
    assert informe.a_dict()["ritmo_aproximado"] is True


def test_el_ultimo_compas_incompleto_cuenta_sus_notas():
    # Nueve pulsos en 4/4: el compas 3 tiene una nota sola y es un compas de
    # verdad. Es como acaba casi cualquier cancion.
    sesion = SesionDeEstudio(pieza_de([0.0, 4.0, 8.0]))
    tercero = compas_numero(sesion.informe, 3)
    assert tercero.notas_escritas == 1
    assert tercero.notas_medibles == 1


def test_cerrar_la_repeticion_acumula_y_no_cuenta_dos_veces():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.cerrar_repeticion()
    assert compas_numero(sesion.informe, 1).acertadas == 1
    # Cerrar otra vez sin tocar nada no puede sumar nada.
    sesion.cerrar_repeticion()
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_el_informe_de_una_pieza_sin_notas_esta_vacio_y_no_rompe():
    informe = SesionDeEstudio(pieza_de([])).informe
    assert informe.compases == ()
    assert proporcion_limpia(informe) is None


def test_cerrar_la_repeticion_devuelve_solo_esa_vuelta():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    primera = sesion.cerrar_repeticion()
    assert compas_numero(primera, 1).acertadas == 1
    segunda = sesion.cerrar_repeticion()
    assert compas_numero(segunda, 1).acertadas == 0      # esta vuelta: nada
    assert compas_numero(sesion.informe, 1).acertadas == 1  # la pasada: uno


def test_una_nota_acertada_pero_tarde_no_cuenta_en_la_proporcion_limpia():
    # Acertar la altura 0,4 s tarde es acertada y NO a tiempo: la proporcion
    # pide las dos cosas a la vez. Sin esta prueba, contar solo `acertadas`
    # pasaria desapercibido.
    sesion = SesionDeEstudio(pieza_de([0.0]))
    tocar(sesion, "E2", en=0.4)
    compas = compas_numero(sesion.informe, 1)
    assert compas.acertadas == 1
    assert compas.tarde == 1
    assert compas.a_tiempo == 0
    assert proporcion_limpia(sesion.informe) == pytest.approx(0.0)


def test_el_informe_de_una_pieza_sin_compases_es_vacio_aunque_el_plan_diga_cero():
    # Tras validar_plan, ultimo_compas vale 0 en la pieza vacia: el tramo no
    # puede salir como range(1, 1) disfrazado de algo, ni romper.
    sesion = SesionDeEstudio(pieza_de([]))
    assert sesion.plan.ultimo_compas == 0
    assert sesion.informe.compases == ()
    assert sesion.cerrar_repeticion().compases == ()


def test_el_informe_se_serializa_con_el_desfase_y_none_intacto():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=-0.3)
    datos = sesion.informe.a_dict()
    assert datos["factor_tempo"] == 1.0
    assert datos["compases"][0]["desfase_medio_s"] < 0
    assert datos["compases"][3]["desfase_medio_s"] is None
    assert isinstance(sesion.informe, InformeDePasada)
    assert isinstance(sesion.informe.compases[0], CompasDelInforme)


def test_una_nota_a_tiempo_pero_con_otra_altura_no_cuenta_en_la_proporcion_limpia():
    # La otra mitad del `min`: a tiempo y NO acertada. Contar solo `a_tiempo`
    # premiaria tocar cualquier cosa con buen pulso.
    sesion = SesionDeEstudio(pieza_de([0.0]))
    tocar(sesion, "A2", en=0.0)
    compas = compas_numero(sesion.informe, 1)
    assert compas.a_tiempo == 1
    assert compas.acertadas == 0
    assert proporcion_limpia(sesion.informe) == pytest.approx(0.0)


def test_el_desfase_medio_se_redondea_a_milisegundos_al_serializar():
    compas = CompasDelInforme(
        numero=1, notas_escritas=1, notas_medibles=1, acertadas=1, a_tiempo=1,
        pronto=0, tarde=0, limpias=1, desfase_medio_s=0.123456, tiene_acordes=False,
    )
    assert compas.a_dict()["desfase_medio_s"] == 0.123
    sin_medir = CompasDelInforme(
        numero=2, notas_escritas=1, notas_medibles=1, acertadas=0, a_tiempo=0,
        pronto=0, tarde=0, limpias=0, desfase_medio_s=None, tiene_acordes=False,
    )
    assert sin_medir.a_dict()["desfase_medio_s"] is None


def test_dos_vueltas_limpias_seguidas_dan_proporcion_uno_y_no_dos():
    sesion = SesionDeEstudio(pieza_de([0.0]))
    tocar(sesion, "E2", en=0.0)
    sesion.cerrar_repeticion()
    tocar(sesion, "E2", en=0.0)
    informe = sesion.informe
    assert informe.repeticiones == 2
    assert compas_numero(informe, 1).limpias == 2
    assert proporcion_limpia(informe) == pytest.approx(1.0)
    assert informe.a_dict()["repeticiones"] == 2


def test_el_informe_de_cerrar_la_repeticion_dice_que_lleva_una_sola_vuelta():
    sesion = SesionDeEstudio(pieza_de([0.0]))
    tocar(sesion, "E2", en=0.0)
    assert sesion.cerrar_repeticion().repeticiones == 1
    assert sesion.cerrar_repeticion().repeticiones == 1
    assert sesion.informe.repeticiones == 3


def test_acertada_pero_tarde_y_a_tiempo_pero_de_otra_altura_no_suman_una_limpia():
    # Dos notas en el mismo compas: una acertada 0,4 s tarde y otra a tiempo pero
    # de otra altura. Hay un acierto y un "a tiempo", pero ninguna nota fue las
    # dos cosas: la proporcion verdadera es 0,0 y no 0,5.
    sesion = SesionDeEstudio(pieza_de([0.0, 1.0]))
    tocar(sesion, "A2", en=0.0)
    tocar(sesion, "E2", en=1.4)
    compas = compas_numero(sesion.informe, 1)
    assert compas.acertadas == 1
    assert compas.a_tiempo == 1
    assert compas.limpias == 0
    assert proporcion_limpia(sesion.informe) == pytest.approx(0.0)


# -- el bucle, la cuenta atras, la pausa y el cambio de plan ----------------


def test_al_llegar_al_final_del_bucle_vuelve_al_principio_y_sube_la_repeticion():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=2, ultimo_compas=3, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    assert sesion.estado.compas_en_curso == 2
    assert sesion.estado.repeticion == 1
    # El compas 4 empieza en el pulso 12, es decir el segundo 12 a 60 ppm.
    sesion.avanzar(8.0)
    assert sesion.estado.compas_en_curso == 2
    assert sesion.estado.repeticion == 2


def test_sin_bucle_el_reloj_se_para_al_final_del_tramo():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=2, ultimo_compas=3)
    )
    sesion.colocar_en(50.0)
    assert sesion.estado.compas_en_curso == 3
    assert sesion.estado.tramo_terminado is True
    assert sesion.estado.a_dict()["completado"] is True


def test_la_cuenta_atras_dura_un_compas_al_tempo_de_la_pasada():
    pieza = pieza_de_doce_compases()
    normal = SesionDeEstudio(
        pieza, PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    normal.avanzar(4.0)
    assert normal.estado.cuenta_atras_restante_s == pytest.approx(4.0)
    lenta = SesionDeEstudio(
        pieza,
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True, factor_tempo=0.5),
    )
    lenta.avanzar(8.0)
    assert lenta.estado.cuenta_atras_restante_s == pytest.approx(8.0)


def test_durante_la_cuenta_atras_el_reloj_no_avanza():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.avanzar(4.0)
    quieto = sesion.estado.carril.instante_s
    sesion.avanzar(1.0)
    assert sesion.estado.carril.instante_s == pytest.approx(quieto)
    assert sesion.estado.cuenta_atras_restante_s == pytest.approx(3.0)
    # Y al agotarse, el reloj vuelve a correr desde el inicio del tramo.
    sesion.avanzar(3.5)
    assert sesion.estado.cuenta_atras_restante_s == 0.0
    assert sesion.estado.carril.instante_s == pytest.approx(0.0)


def test_durante_la_cuenta_atras_no_se_cobra_nada():
    # Se alimenta con CUADROS y no colocando el reloj, porque `colocar_en`
    # cancela la cuenta atras a proposito: una colocacion explicita es una orden
    # sobre donde esta el cabezal. Lo que pasa de verdad durante la cuenta es
    # que siguen llegando cuadros de audio, y es eso lo que hay que probar.
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.avanzar(4.0)
    assert sesion.estado.cuenta_atras_restante_s > 0
    instante = 100.0
    for _ in range(20):
        sesion.procesar(suena("E2"), instante)
        instante += 0.021
    assert sesion.estado.carril.tocadas == ()


def test_un_apagon_en_plena_cuenta_atras_no_la_gasta_ni_mueve_el_cabezal():
    """**UN HUECO DE AUDIO NO ES TIEMPO TRANSCURRIDO.** Defecto medido.

    El caso es real y no de laboratorio: el alumno desenchufa el cable -o el
    dispositivo desaparece- a media cuenta atras y lo vuelve a enchufar. El cuadro
    que llega entonces trae el hueco ENTERO en la resta de `_delta_del_analisis`,
    porque `congelar_en` -lo que el conductor llama al detectar el hueco- mueve el
    reloj pero NO reinicia `_ultimo_analisis`.

    Lo que tiene que pasar es que la cuenta siga DONDE LA DEJO. No reiniciada
    -nadie ha vuelto a pulsar «empezar»- y no gastada: `congelar_en` existe
    precisamente para que perder la señal en plena cuenta no sea motivo para
    tirarla, y el tiempo sin señal no entra en la pieza por ninguna puerta.

    Lo que pasaba, medido con un hueco de 30 s: el hueco se tragaba la cuenta de
    golpe y lo que sobraba de el se le daba al reloj, que se iba al final del tramo
    y le hacia dar al bucle una **VUELTA FANTASMA** -repeticion 2- que nadie toco,
    con el cable desenchufado. Las tres aserciones son las tres mitades de eso.
    """
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=1),
    )
    sesion.arrancar()
    sesion.procesar(SILENCIO, 100.0)
    entera = sesion.estado.cuenta_atras_restante_s
    assert entera == pytest.approx(4.0)

    sesion.procesar(SILENCIO, 130.0)

    estado = sesion.estado
    assert estado.cuenta_atras_restante_s == pytest.approx(entera), (
        "el apagon se comio la cuenta atras: el tiempo sin señal no entra en la "
        "pieza, y perder la señal no es motivo para tirar la cuenta"
    )
    assert estado.carril.instante_s == pytest.approx(0.0), (
        "el cabezal se fue del inicio del tramo por un hueco de audio"
    )
    assert estado.repeticion == 1, (
        "el bucle dio una vuelta que nadie toco: el hueco entro en el reloj"
    )
    # Y el cuadro siguiente, ya sin hueco, descuenta lo que le toca y nada mas.
    sesion.procesar(SILENCIO, 130.021)
    assert sesion.estado.cuenta_atras_restante_s == pytest.approx(entera - 0.021)


def test_tras_la_vuelta_del_bucle_las_notas_se_pueden_volver_a_cobrar():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    tocar(sesion, "E2", en=0.0)
    assert len(sesion.estado.carril.tocadas) == 1
    sesion.avanzar(4.0)             # da la vuelta
    assert sesion.estado.carril.tocadas == ()
    tocar(sesion, "E2", en=0.0)
    assert len(sesion.estado.carril.tocadas) == 1
    # Y las dos vueltas estan en el informe: dos aciertos en el compas 1.
    assert compas_numero(sesion.informe, 1).acertadas == 2


def test_un_bucle_sobre_un_compas_sin_notas_no_se_queda_clavado():
    # Compases 1 y 3 con notas, el 2 vacio. Un rango vacio no puede dividir por
    # cero ni dejar el cabezal parado: el reloj lo cruza y da la vuelta igual.
    sesion = SesionDeEstudio(
        pieza_de([0.0, 8.0]),
        PlanDePasada(primer_compas=2, ultimo_compas=2, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    assert sesion.estado.compas_en_curso == 2
    sesion.avanzar(4.0)
    assert sesion.estado.repeticion == 2
    assert sesion.estado.compas_en_curso == 2
    assert sesion.informe.compases[0].notas_escritas == 0


def test_un_bucle_de_un_solo_compas_con_una_nota_sola_funciona():
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    tocar(sesion, "E2", en=0.0)
    sesion.avanzar(4.0)
    assert sesion.estado.repeticion == 2
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_cambiar_el_tempo_a_mitad_conserva_el_compas_y_lo_ya_tocado():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.colocar_en(9.0)                      # compas 3
    sesion.cambiar_plan(PlanDePasada(factor_tempo=0.5))
    assert sesion.estado.compas_en_curso == 3
    assert sesion.estado.instante_pulsos == pytest.approx(9.0)
    assert sesion.estado.factor_tempo == 0.5
    # El reloj de la pasada se ha estirado: 9 pulsos al 50 % son 18 segundos.
    assert sesion.estado.carril.instante_s == pytest.approx(18.0)
    # Y el acierto del compas 1 sigue en el informe.
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_cambiar_a_un_rango_que_no_contiene_el_cabezal_lo_lleva_al_nuevo_inicio():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.colocar_en(1.0)
    sesion.cambiar_plan(PlanDePasada(primer_compas=7, ultimo_compas=8, en_bucle=True))
    assert sesion.estado.compas_en_curso == 7


def test_saltar_a_un_compas_coloca_el_cabezal_y_no_borra_el_informe():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.saltar_al_compas(9)
    assert sesion.estado.compas_en_curso == 9
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_saltar_a_un_compas_que_no_existe_se_rechaza():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    with pytest.raises(ValueError, match="99"):
        sesion.saltar_al_compas(99)


def test_un_compas_que_no_existe_se_rechaza_con_el_mensaje_del_tramo():
    """La guarda del tramo va ANTES de `pulsos_del_compas`, y se nota en el texto.

    Al reves, un compas que la pieza no tiene salia con el mensaje de
    `compases.py` ("la pieza no tiene compas 99: va del 1 al 12"), que no es el
    que documenta este metodo: el suyo nombra los dos extremos del TRAMO y dice
    que hay que cambiar el plan, que es lo unico que le permite al usuario
    arreglarlo. Fuera del tramo es fuera del tramo, exista el compas o no.
    """
    sesion = SesionDeEstudio(pieza_de_doce_compases(), plan_2_a_3_en_bucle())
    with pytest.raises(ValueError, match=r"99.*fuera del tramo.*2.*3"):
        sesion.saltar_al_compas(99)


def test_reiniciar_la_pasada_vuelve_al_inicio_y_olvida_el_informe():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.colocar_en(9.0)
    sesion.reiniciar_pasada()
    assert sesion.estado.compas_en_curso == 1
    assert sesion.estado.repeticion == 1
    assert compas_numero(sesion.informe, 1).acertadas == 0


def test_en_pausa_el_reloj_no_avanza_y_al_reanudar_sigue_donde_estaba():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.colocar_en(5.0)
    sesion.pausar()
    # Quince segundos de reloj de pared que NO son de la pieza. Con una puerta
    # absoluta, al reanudar el cabezal se iria a los 20 s; con un delta, el
    # tiempo que no se cuenta no se pasa.
    sesion.avanzar(15.0)
    assert sesion.estado.carril.instante_s == pytest.approx(5.0)
    assert sesion.estado.en_pausa is True
    sesion.reanudar()
    sesion.avanzar(1.0)
    assert sesion.estado.carril.instante_s == pytest.approx(6.0)


# -- las pruebas que el brief no traia ----------------------------------------


def test_cambiar_el_tempo_a_mitad_no_sube_las_repeticiones_pero_dar_la_vuelta_si():
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    tocar(sesion, "E2", en=0.0)
    sesion.cambiar_plan(PlanDePasada(
        primer_compas=1, ultimo_compas=1, en_bucle=True,
        compases_de_cuenta_atras=0, factor_tempo=0.5,
    ))
    informe = sesion.informe
    assert informe.repeticiones == 1
    assert compas_numero(informe, 1).limpias == 1
    assert proporcion_limpia(informe) == pytest.approx(1.0)
    # Dar la vuelta al bucle (4 pulsos al 50 % son 8 s) si es una repeticion.
    sesion.avanzar(8.0)
    assert sesion.informe.repeticiones == 2


def test_saltar_al_compas_no_sube_las_repeticiones():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.saltar_al_compas(5)
    sesion.saltar_al_compas(2)
    assert sesion.informe.repeticiones == 1


def test_saltar_al_mismo_compas_y_volver_a_tocarlo_se_cobra_otra_vez():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.saltar_al_compas(3)
    tocar(sesion, "E2", en=8.0)
    assert compas_numero(sesion.informe, 3).acertadas == 1
    sesion.saltar_al_compas(3)
    assert sesion.estado.carril.tocadas == ()
    tocar(sesion, "E2", en=8.0)
    assert len(sesion.estado.carril.tocadas) == 1
    assert compas_numero(sesion.informe, 3).acertadas == 2


def test_reiniciar_la_pasada_vuelve_a_dejar_las_repeticiones_en_uno():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    sesion.avanzar(4.0)
    sesion.avanzar(4.0)
    assert sesion.informe.repeticiones == 3
    sesion.reiniciar_pasada()
    assert sesion.informe.repeticiones == 1


def test_una_nota_de_la_frontera_del_bucle_se_cuenta_en_la_vuelta_que_acaba():
    sesion = SesionDeEstudio(
        pieza_de([3.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    assert sesion.ultima_vuelta is None
    tocar(sesion, "E2", en=3.0)
    # La nota ya esta anotada; los cuadros de silencio llevan el reloj al final.
    assert len(sesion.estado.carril.tocadas) == 1
    instante = 50.0
    for _ in range(300):        # tope: un fallo no debe colgar la suite
        if sesion.estado.repeticion != 1:
            break
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    assert sesion.estado.repeticion == 2
    assert compas_numero(sesion.ultima_vuelta, 1).acertadas == 1
    # La vuelta nueva empieza en blanco y la pasada conserva el acierto.
    assert sesion.estado.carril.tocadas == ()
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_el_bucle_da_la_vuelta_con_cuadros_de_audio_y_sin_cuenta_atras():
    # El camino CON audio: `procesar` mueve el reloj y no `avanzar_a`.
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    instante = 0.0
    for _ in range(300):
        if sesion.estado.repeticion != 1:
            break
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    assert sesion.estado.repeticion == 2
    assert sesion.estado.carril.instante_s < 1.0


# -- El bucle sin arrastre y la nota de la frontera (Task 7) ----------------
#
# El reloj del bucle perdia tiempo en cada vuelta por DOS sumideros, y los dos
# se miden aqui por separado porque se arreglan por separado:
#
# 1. El EXCESO con que el reloj cruzaba el final del tramo se tiraba.
# 2. Con audio, `avanzar_a` invalida la correspondencia entre los dos relojes del
#    seguidor y no se vuelve a fijar hasta el cuadro siguiente, asi que el reloj
#    se quedaba quieto UN CUADRO en cada vuelta.
#
# Lo que esos dos sumideros le hacian a una pasada de verdad esta medido con el
# gemelo en `tests/test_gemelo_bucle.py`: 36 ms por vuelta, y a las ocho vueltas
# cero notas limpias. Aqui se miden los mecanismos, con numeros exactos.


def test_la_vuelta_del_bucle_conserva_el_exceso_del_reloj():
    """El reloj no se re-ancla en el inicio: se re-ancla en inicio + exceso.

    Sin audio y con numeros redondos, asi que el exceso es exacto y no hay nada
    que estimar: el tramo es el compas 1 (0 a 4 s) y la segunda mirada cruza el
    final con 0,5 s de exceso. Tirarlo -lo que se hacia- dejaba el reloj en 0,0 y
    perdia medio segundo de pasada.
    """
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    sesion.avanzar(3.0)
    sesion.avanzar(1.5)
    assert sesion.estado.repeticion == 2
    assert sesion.estado.carril.instante_s == pytest.approx(0.5)


def test_el_camino_sin_audio_no_arrastra_el_reloj_en_treinta_vueltas():
    """Treinta vueltas con miradas que no caen nunca en la frontera: cero deriva.

    Es la afirmacion fuerte del exceso, y se hace sin audio porque ahi el reloj se
    puede comprobar EXACTO: tras N miradas de 0,3 s sobre un tramo de 4 s, el
    reloj tiene que valer `0,3 N` modulo 4 y la repeticion `0,3 N // 4 + 1`. Nada
    de margenes: lo que el bucle pierda por vuelta aparece aqui multiplicado por
    treinta.

    Con el exceso tirado, tras 400 miradas el reloj iba 23,1 s por detras -el
    equivalente a casi seis vueltas enteras- y la cuenta de repeticiones salia 25
    en vez de 31.
    """
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    paso = 0.3
    for mirada in range(1, 401):
        sesion.avanzar(paso)
        transcurrido = paso * mirada
        estado = sesion.estado
        # La invariante, y no el reloj modulo cuatro: lo recorrido en esta vuelta
        # MAS lo que ocupan las vueltas ya dadas es el tiempo que ha pasado.
        # Escrita con el modulo, una mirada que cae en la frontera a 2e-15 por
        # debajo de 4,0 -y hay dos en 400- parece un error de cuatro segundos
        # cuando lo que pasa es que la vuelta llega una mirada despues. La
        # invariante no se entera de eso y sigue viendo el arrastre, que es lo que
        # aqui se mide.
        recorrido = estado.carril.instante_s + (estado.repeticion - 1) * 4.0
        assert recorrido == pytest.approx(transcurrido, abs=1e-9), (
            f"el reloj se ha ido en la mirada {mirada}"
        )
    # Y las vueltas se han contado: 120 s de miradas sobre un tramo de 4 s son
    # treinta vueltas, y la trigesima esta a punto de darse -el reloj marca 4,0
    # menos 1,8e-14, porque 0,3 x 400 en binario no llega a 120 exacto-. La vuelta
    # llega con la mirada siguiente, y eso es el redondeo del llamador, no
    # arrastre: el arrastre lo vigila la invariante de dentro del bucle, mirada a
    # mirada.
    assert sesion.estado.repeticion == 30
    assert sesion.estado.carril.instante_s == pytest.approx(4.0, abs=1e-9)


def test_un_exceso_mayor_que_el_tramo_no_se_arrastra():
    """Un salto enorme da UNA vuelta y deja el reloj dentro del tramo.

    Un exceso mayor que el tramo entero no es una vuelta: es un salto de reloj -un
    `avanzar` con un delta absurdo, una mirada tras un apagon- y arrastrarlo
    dejaria el cabezal MUY por delante del final del tramo que acaba de empezar.
    Acotado a la longitud del tramo, el reloj acaba como mas tarde en el final del
    tramo: sin el tope saldria 96,0, que son veinticuatro tramos por delante.
    """
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    sesion.avanzar(100.0)
    assert sesion.estado.repeticion == 2
    assert sesion.estado.carril.instante_s == pytest.approx(4.0)
    assert sesion.estado.compas_en_curso == 1


def test_la_vuelta_con_audio_no_se_come_un_cuadro_de_analisis():
    """Con cuadros, la vuelta no congela el reloj: la pasada cuadra al milimetro.

    **Es el segundo sumidero, y no se ve con una sola vuelta.** Con audio el reloj
    de la pieza lo mueve solo la correspondencia entre los dos relojes del
    seguidor; `avanzar_a` la invalida y la vuelve a fijar el cuadro SIGUIENTE, con
    el reloj donde la vuelta lo dejo, asi que entre los dos cuadros el reloj se
    quedaba quieto un cuadro entero.

    La invariante que se afirma es exacta y es la definicion de «no arrastra»: lo
    recorrido por el cabezal MAS lo que ocupan las vueltas ya dadas tiene que ser
    el tiempo de analisis transcurrido. Con el cuadro perdido en cada vuelta, tras
    las cuatro vueltas de esta prueba faltaban 84 ms: cuatro cuadros.

    Se comprueba en cada cuadro MENOS en el que da la vuelta, donde el reloj va un
    cuadro por delante a proposito (es la compensacion, que se adelanta al hueco
    que viene); el cuadro siguiente lo cuadra.
    """
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    paso = 0.021
    arranque = 100.0
    sesion.colocar_en(0.0)
    vueltas = 0
    for cuadro in range(800):
        instante = arranque + cuadro * paso
        antes = sesion.estado.repeticion
        estado = sesion.procesar(SILENCIO, instante)
        dio_la_vuelta = estado.repeticion != antes
        vueltas = estado.repeticion - 1
        if dio_la_vuelta:
            continue
        recorrido = estado.carril.instante_s + vueltas * 4.0
        assert recorrido == pytest.approx(instante - arranque, abs=1e-9), (
            f"en el cuadro {cuadro} el cabezal lleva {recorrido:.6f} s y el "
            f"analisis {instante - arranque:.6f} s"
        )
    assert vueltas == 4, f"800 cuadros de 21 ms son 16,8 s, o sea cuatro vueltas de 4 s"


def test_la_nota_del_final_cuenta_en_la_vuelta_que_cierra():
    """Una nota atacada 50 ms antes del final es de la vuelta que CIERRA.

    **La semantica de la tarea, afirmada: una nota pertenece a la vuelta en que se
    ATACO, no a la vuelta en que el detector la resolvio.** El detector firma un
    ataque hasta 250 ms despues de que ocurriera (`VENTANA_ATAQUE_COMO_ONSET_S`),
    asi que esta nota se resuelve con la vuelta siguiente ya abierta.

    La nota esta escrita en el pulso 3,98 -a 60 ppm, el segundo 3,98 de un tramo
    que acaba en 4,0- y se ataca en el cuadro 3,963. El detector le pone el onset
    en 3,984 y la sella dos cuadros despues, en 4,026, ya pasada la vuelta (que
    ocurre en el cuadro 4,005).

    Antes de la T7 esta nota NO existia en ninguna parte: `_adjudicar` la
    descartaba por ser anterior al primer cuadro posterior al salto. Hoy sale en el
    informe de la vuelta que cerro, con su desfase medido (+4 ms, «a tiempo»), y
    la vuelta nueva empieza EN BLANCO, que es la otra mitad de la afirmacion: lo
    contrario le regalaria a la vuelta nueva una nota que nadie toco en ella.
    """
    sesion = SesionDeEstudio(
        pieza_de([3.98]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    sesion.colocar_en(3.9)
    instante = 3.9
    for _ in range(20):
        sesion.procesar(SILENCIO if instante < 3.963 else suena("E2"), instante)
        instante += 0.021

    assert sesion.estado.repeticion == 2
    cerrada = compas_numero(sesion.ultima_vuelta, 1)
    assert cerrada.acertadas == 1, "la nota de la frontera es de la vuelta que cerro"
    assert cerrada.a_tiempo == 1
    assert cerrada.desfase_medio_s == pytest.approx(0.004, abs=0.021)
    # La vuelta nueva, en blanco: no se le regala una nota que no se toco en ella.
    assert sesion.estado.carril.tocadas == ()
    # Y la pasada entera la cuenta UNA vez, ni cero ni dos.
    assert compas_numero(sesion.informe, 1).acertadas == 1
    assert [t.indice for t in sesion.tocadas_de_la_ultima_vuelta] == [0]


def test_la_nota_atacada_tras_la_frontera_cuenta_en_la_vuelta_que_abre():
    """El otro lado de la misma frontera, y es lo que la hace una frontera.

    Misma mecanica que la prueba de arriba y resultado CONTRARIO: la nota se ataca
    en el cuadro 4,005, que es el cuadro en que el reloj cruza el final del tramo,
    o sea DESPUES del instante en que el reloj paso por el final (4,0). Se ataco ya
    en la vuelta nueva, asi que es de la vuelta nueva.

    La pieza tiene dos notas -el pulso 0 y el 3,98- porque la pregunta es a QUE
    nota se le adjudica: a la nota 0 de la vuelta que abre, no a la del final de la
    que cierra.

    Medido: la nota 0 sale en `estado.carril.tocadas` de la vuelta nueva, «a
    tiempo» con +5 ms, y el informe de la vuelta cerrada se queda a cero. Si las
    dos pruebas dieran lo mismo, la frontera no estaria decidiendo nada: es el
    mutante 3 del informe de la tarea.
    """
    sesion = SesionDeEstudio(
        pieza_de([0.0, 3.98]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    sesion.colocar_en(3.9)
    instante = 3.9
    for _ in range(20):
        sesion.procesar(SILENCIO if instante < 4.005 else suena("E2"), instante)
        instante += 0.021

    assert sesion.estado.repeticion == 2
    assert compas_numero(sesion.ultima_vuelta, 1).acertadas == 0, (
        "nada se ataco dentro de la vuelta que cerro"
    )
    assert sesion.tocadas_de_la_ultima_vuelta == ()
    tocadas = sesion.estado.carril.tocadas
    assert [t.indice for t in tocadas] == [0]
    assert tocadas[0].clasificacion == "a_tiempo"
    assert tocadas[0].desfase_s == pytest.approx(0.005, abs=0.021)


def test_lo_adjudicado_en_el_cuadro_que_da_la_vuelta_se_puede_leer():
    """Una nota sellada EN el cuadro de la vuelta no desaparece sin que nadie la vea.

    **El cuarto defecto de la tarea, y era invisible por construccion.**
    `SesionDeEstudio.procesar` llama al seguidor y, en la misma llamada, acaba en
    `_dar_la_vuelta` -> `cerrar_repeticion`, cuyo ultimo acto es `olvidar_tramo`, y
    devuelve el estado DESPUES de eso: lo adjudicado en ese cuadro no aparece en
    `estado.carril.tocadas` de NINGUNA llamada. El informe no lo salvaba porque
    solo lleva conteos por compas, no notas.

    Aqui la nota se ataca en el cuadro 3,942, el detector le pone el onset en 3,963
    y la sella dos cuadros despues, en 4,005, que es exactamente el cuadro en que
    el reloj cruza el final. Se comprueban las tres cosas: que no aparece en
    ninguna de las veinte miradas, que el informe de la vuelta la cuenta, y que
    `tocadas_de_la_ultima_vuelta` la entrega -que es la unica forma de leerla-.
    """
    sesion = SesionDeEstudio(
        pieza_de([3.98]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    sesion.colocar_en(3.9)
    instante = 3.9
    vistas = 0
    for _ in range(20):
        estado = sesion.procesar(
            SILENCIO if instante < 3.942 else suena("E2"), instante
        )
        vistas += len(estado.carril.tocadas)
        instante += 0.021

    assert vistas == 0, (
        "la nota del cuadro de la vuelta no sale en ningun estado publicado, y "
        "por eso hay que poder leerla aparte"
    )
    assert compas_numero(sesion.ultima_vuelta, 1).acertadas == 1
    assert [t.indice for t in sesion.tocadas_de_la_ultima_vuelta] == [0]
    assert sesion.tocadas_de_la_ultima_vuelta[0].desfase_s == pytest.approx(
        -0.017, abs=0.021
    )


def test_las_tocadas_de_la_ultima_vuelta_se_olvidan_al_reiniciar_la_pasada():
    """Reiniciar la pasada no deja las notas de la vuelta anterior colgando.

    Es la hermana de `test_reiniciar_la_pasada_olvida_la_ultima_vuelta_de_la_anterior`:
    lo que vale para el informe vale para las notas, y por el mismo motivo -dejarlas
    seria una repeticion fantasma en la pasada nueva-.
    """
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    tocar(sesion, "E2", en=0.0)
    sesion.avanzar(4.0)
    assert len(sesion.tocadas_de_la_ultima_vuelta) == 1
    sesion.reiniciar_pasada()
    assert sesion.tocadas_de_la_ultima_vuelta == ()


def test_una_pieza_sin_compases_en_bucle_no_da_vueltas_ni_se_da_por_terminada():
    sesion = SesionDeEstudio(pieza_de([]), PlanDePasada(en_bucle=True))
    sesion.avanzar(5.0)
    assert sesion.estado.repeticion == 1
    assert sesion.estado.tramo_terminado is False


def test_en_pausa_los_cuadros_de_audio_no_mueven_el_reloj_ni_cobran():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.colocar_en(0.0)
    sesion.pausar()
    instante = 10.0
    for _ in range(20):
        sesion.procesar(suena("E2"), instante)
        instante += 0.021
    assert sesion.estado.carril.instante_s == pytest.approx(0.0)
    assert sesion.estado.carril.tocadas == ()


class EspiaDelSeguidor:
    """Anota en orden las llamadas de la sesion a `olvidar_tramo` y `avanzar_a`."""

    def __init__(self, seguidor, llamadas):
        self._seguidor = seguidor
        self._llamadas = llamadas

    def olvidar_tramo(self, desde_s, hasta_s):
        self._llamadas.append(("olvidar_tramo", desde_s, hasta_s))
        return self._seguidor.olvidar_tramo(desde_s, hasta_s)

    def avanzar_a(self, instante_s, frontera_del_salto_s=None, instante_analisis_s=None):
        # La frontera se anota tambien: es lo que distingue un salto CONTINUO -la
        # vuelta del bucle, que retiene las pulsaciones en vuelo y trae su
        # correspondencia escrita- de un salto ordinario, que las tira. Una espia
        # que se la comiera no podria notar la diferencia.
        self._llamadas.append(("avanzar_a", instante_s, frontera_del_salto_s))
        return self._seguidor.avanzar_a(
            instante_s,
            frontera_del_salto_s=frontera_del_salto_s,
            instante_analisis_s=instante_analisis_s,
        )

    def __getattr__(self, nombre):
        return getattr(self._seguidor, nombre)


def espiar(sesion):
    # Alcanza `sesion._seguidor`, que es privado. El acoplamiento se acepta SOLO
    # porque el orden que fija no tiene comportamiento observable en un solo
    # hilo; que nadie lo copie como patron en pruebas donde si haya algo que medir.
    llamadas = []
    sesion._seguidor = EspiaDelSeguidor(sesion._seguidor, llamadas)
    return llamadas


def test_la_vuelta_del_bucle_olvida_el_tramo_antes_de_colocar_el_reloj():
    # Contrato de orden: `olvidar_tramo` primero y la colocacion del reloj
    # despues. Como las dos operaciones no se pisan, el resultado final no
    # distingue el orden; por eso se mide la secuencia.
    #
    # El motivo del orden cambio con la T7 y conviene no citar el viejo: `avanzar_a`
    # ya no es «quien descarta las pulsaciones en vuelo», porque en la vuelta del
    # bucle las RETIENE (ver `SeguidorPieza.avanzar_a`). El orden se mantiene
    # porque olvidar el tramo es lo que deja las notas recobrables para la vuelta
    # nueva, y hacerlo despues de colocar el reloj no tendria nada que ver con la
    # colocacion.
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=2, ultimo_compas=3, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    llamadas = espiar(sesion)
    sesion.avanzar(8.0)
    # Tras la colocacion del llamador y el volcado del informe, vienen estas dos.
    # Sin frontera, porque este camino es el de SIN AUDIO: no hay correspondencia
    # entre relojes que retirar ni, por tanto, pulsacion en vuelo que retener.
    assert llamadas[-2:] == [
        ("olvidar_tramo", 4.0, 12.0),
        ("avanzar_a", 4.0, None),
    ]


def test_saltar_al_compas_olvida_su_tramo_y_despues_coloca_el_reloj():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    llamadas = espiar(sesion)
    sesion.saltar_al_compas(3)
    # Del compas 3 (segundo 8) al final del tramo (segundo 48), y luego el reloj.
    # Sin frontera: saltar de compas NO es un salto continuo -el reloj se va a
    # otra parte-, asi que las pulsaciones del tramo abandonado se tiran, que es
    # lo que ha hecho `avanzar_a` siempre.
    assert llamadas[-2:] == [
        ("olvidar_tramo", 8.0, 48.0),
        ("avanzar_a", 8.0, None),
    ]


def test_la_cuenta_atras_se_agota_con_cuadros_de_audio_y_despues_la_pasada_corre():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.avanzar(4.0)
    assert sesion.estado.cuenta_atras_restante_s == pytest.approx(4.0)
    instante = 100.0
    for _ in range(100):
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    assert 0 < sesion.estado.cuenta_atras_restante_s < 4.0
    for _ in range(150):
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    assert sesion.estado.cuenta_atras_restante_s == 0.0
    sesion.procesar(SILENCIO, instante)
    instante += 0.021
    sesion.procesar(SILENCIO, instante)
    assert sesion.estado.carril.instante_s > 0.0


def test_un_cuadro_con_el_reloj_hacia_atras_no_alarga_la_cuenta_atras():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.avanzar(4.0)
    sesion.procesar(SILENCIO, 10.0)
    sesion.procesar(SILENCIO, 11.0)
    restante = sesion.estado.cuenta_atras_restante_s
    sesion.procesar(SILENCIO, 9.0)
    assert sesion.estado.cuenta_atras_restante_s == restante


def test_colocar_el_cabezal_en_plena_cuenta_atras_la_cancela():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=2, en_bucle=True)
    )
    sesion.avanzar(8.0)
    assert sesion.estado.cuenta_atras_restante_s > 0
    sesion.colocar_en(1.0)
    assert sesion.estado.cuenta_atras_restante_s == 0.0
    assert sesion.estado.carril.instante_s == pytest.approx(1.0)


def test_sin_bucle_el_reloj_queda_clavado_en_el_final_del_tramo():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=2, ultimo_compas=3)
    )
    sesion.colocar_en(50.0)
    assert sesion.estado.carril.instante_s == pytest.approx(12.0)


def tocar_hasta_pasar_el_final(sesion, nota, desde, cuadros=40, paso=0.021):
    """Ataca `nota` en el instante `desde` y sigue dando cuadros pasado el final.

    Es el caso de la ultima nota de una pasada: se toca a tiempo, justo antes de
    la barra, y el detector la firma unas decenas de milisegundos DESPUES, cuando
    el reloj ya ha cruzado el final del tramo. Hacen falta los cuadros de despues:
    sin ellos el onset no llega a resolverse nunca y la prueba no mediria nada.
    """
    instante = desde - 0.1
    sesion.colocar_en(instante)
    while instante < desde:
        sesion.procesar(SILENCIO, instante)
        instante += paso
    for _ in range(cuadros):
        sesion.procesar(suena(nota), instante)
        instante += paso
    return instante


def test_una_nota_del_final_del_tramo_entra_en_el_informe():
    """El tramo que acaba NO puede recolocar el reloj mientras haya algo en vuelo.

    Acabar el tramo sin bucle llega por `procesar`, o sea CON AUDIO entrando, y la
    condicion «el reloj paso del final» sigue siendo verdad en todos los cuadros
    siguientes: recolocando el reloj en cada uno (109 veces en 300 cuadros,
    medido) se invalida la correspondencia entre los dos relojes del seguidor y
    `_adjudicar` descarta el onset del ataque, que el detector firma hasta 250 ms
    despues de que ocurriera. La nota escrita en el pulso 3,95 de un tramo que
    acaba en el 4,0 y atacada en el 3,98 salia con `acertadas=0` y `limpias=0`
    (medido: con la rotura puesta sigue saliendo asi, y es la prueba siguiente).

    Y con ella salia sin limpias el ultimo compas de CADA pasada entera, asi que
    `peores_compases` lo nominaba siempre y el tempo automatico no subia nunca.
    """
    sesion = SesionDeEstudio(
        pieza_de([0.0, 3.95]), PlanDePasada(primer_compas=1, ultimo_compas=1)
    )
    tocar_hasta_pasar_el_final(sesion, "E2", 3.98)
    assert sesion.estado.tramo_terminado is True, "el tramo tenia que haberse acabado"
    primero = compas_numero(sesion.informe, 1)
    assert primero.acertadas == 1
    assert primero.limpias == 1


def test_recolocar_el_reloj_en_cada_cuadro_se_come_la_nota_del_final():
    """La ROTURA de la prueba de arriba, para que no sea una prueba que no falla.

    Se vuelve al comportamiento viejo -recolocar el reloj en el final en cada
    cuadro posterior al que acaba el tramo- y la nota del final desaparece del
    informe. Si alguien «simplifica» el aplazamiento de `_al_dia`, esta prueba es
    la que dice que se ha vuelto a romper.
    """
    sesion = SesionDeEstudio(
        pieza_de([0.0, 3.95]), PlanDePasada(primer_compas=1, ultimo_compas=1)
    )
    # La rotura: la ventana de ataques en vuelo nunca esta abierta, asi que el
    # reloj se clava en el final en todos los cuadros, como antes del arreglo.
    sesion._ataques_en_vuelo = lambda: False
    tocar_hasta_pasar_el_final(sesion, "E2", 3.98)
    assert sesion.estado.tramo_terminado is True
    assert compas_numero(sesion.informe, 1).acertadas == 0


def test_sin_audio_el_reloj_se_queda_clavado_en_el_final_del_tramo_mirada_tras_mirada():
    """La otra mitad del aplazamiento: sin audio no hay nada que esperar.

    `avanzar` solo lo llama el servidor cuando NO llegan cuadros, asi que ahi
    clavar el reloj no le cuesta una pulsacion a nadie, y tiene que clavarlo en
    cada mirada: si el aplazamiento rigiera tambien sin audio, el cabezal seguiria
    corriendo despues de «terminado» un segundo por segundo.
    """
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=2, ultimo_compas=3)
    )
    sesion.colocar_en(8.0)
    for _ in range(200):  # 6,6 s: de sobra para pasarse del final, que esta en 12,0
        sesion.avanzar(1 / 30.0)
    assert sesion.estado.tramo_terminado is True
    assert sesion.estado.carril.instante_s == pytest.approx(12.0)


def test_tras_cambiar_el_tempo_las_notas_se_miden_con_el_tempo_nuevo():
    # La nota escrita en el segundo 4 cae en el 8 al 50 %. Si el seguidor no se
    # reconstruyera, seguiria esperandola en el 4 y tocarla en el 8 saldria tarde.
    sesion = SesionDeEstudio(pieza_de([4.0]))
    sesion.cambiar_plan(PlanDePasada(factor_tempo=0.5))
    tocar(sesion, "E2", en=8.0)
    tocada = sesion.estado.carril.tocadas[0]
    assert tocada.acertada is True
    assert tocada.clasificacion == "a_tiempo"


def test_cambiar_el_plan_despues_de_terminar_el_tramo_lo_reabre():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=2, ultimo_compas=3)
    )
    sesion.colocar_en(50.0)
    assert sesion.estado.tramo_terminado is True
    sesion.cambiar_plan(PlanDePasada(primer_compas=2, ultimo_compas=12))
    assert sesion.estado.tramo_terminado is False


def test_reiniciar_la_pasada_olvida_la_ultima_vuelta_de_la_anterior():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    sesion.avanzar(4.0)
    assert sesion.ultima_vuelta is not None
    sesion.reiniciar_pasada()
    assert sesion.ultima_vuelta is None


def test_con_audio_reanudar_no_mueve_el_cabezal_el_tamano_de_la_pausa():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    instante = 10.0
    for _ in range(5):
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    antes = sesion.estado.carril.instante_s
    sesion.pausar()
    for _ in range(500):            # 10,5 s de reloj de pared en pausa
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    assert sesion.estado.carril.instante_s == pytest.approx(antes)
    sesion.reanudar()
    sesion.procesar(SILENCIO, instante)
    instante += 0.021
    sesion.procesar(SILENCIO, instante)
    assert sesion.estado.carril.instante_s == pytest.approx(antes + 0.021, abs=0.01)


def plan_2_a_3_en_bucle():
    return PlanDePasada(primer_compas=2, ultimo_compas=3, en_bucle=True,
                        compases_de_cuenta_atras=0)


def test_saltar_dentro_del_tramo_no_sube_las_repeticiones_ni_mueve_la_proporcion():
    sesion = SesionDeEstudio(pieza_de_doce_compases(), plan_2_a_3_en_bucle())
    tocar(sesion, "E2", en=4.0)
    # Una de las dos notas medibles del tramo (compases 2 y 3) esta limpia.
    assert proporcion_limpia(sesion.informe) == pytest.approx(0.5)
    for _ in range(3):
        sesion.saltar_al_compas(3)
        assert sesion.estado.compas_en_curso == 3
    assert sesion.estado.repeticion == 1
    assert sesion.informe.repeticiones == 1
    assert proporcion_limpia(sesion.informe) == pytest.approx(0.5)


def test_saltar_fuera_del_tramo_se_rechaza_nombrando_el_compas_y_los_dos_extremos():
    sesion = SesionDeEstudio(pieza_de_doce_compases(), plan_2_a_3_en_bucle())
    for fuera in (9, 1):
        with pytest.raises(ValueError, match=rf"{fuera}.*2.*3"):
            sesion.saltar_al_compas(fuera)
    assert sesion.estado.compas_en_curso == 2


def test_colocar_el_cabezal_mas_alla_del_final_no_da_la_vuelta_ni_cuenta_repeticion():
    sesion = SesionDeEstudio(pieza_de_doce_compases(), plan_2_a_3_en_bucle())
    sesion.colocar_en(30.0)
    assert sesion.estado.repeticion == 1
    assert sesion.informe.repeticiones == 1
    assert sesion.ultima_vuelta is None


def test_procesar_y_cambiar_plan_no_se_cruzan_sobre_la_misma_sesion():
    """El candado propio de `SesionDeEstudio`: `procesar` corre en OTRO hilo.

    El servidor llama a `procesar` a proposito FUERA de su propio candado
    (`SesionCarril._observar` no hace nada lento dentro), asi que mientras ese
    `procesar` corre en el hilo de analisis, el hilo HTTP puede estar en
    `cambiar_plan` sobre el MISMO objeto. Y `cambiar_plan` REEMPLAZA
    `self._seguidor`: colado entre el `procesar` del seguidor y el `_al_dia` de la
    misma llamada, la pulsacion de ese cuadro se adjudicaba a un seguidor que se
    estaba tirando y `_al_dia` juzgaba contra el seguidor y el final nuevos.

    El candado del `SeguidorPieza` no cubria nada de esto: protege el interior del
    seguidor, no los campos que esta etapa anadio en la sesion.

    Aqui se para el `procesar` del seguidor a mitad y se comprueba que el
    `cambiar_plan` del otro hilo ESPERA. La espera corta solo le da tiempo a una
    implementacion sin candado a equivocarse; con el candado es determinista.
    """
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    dentro, soltar, cambiado = threading.Event(), threading.Event(), threading.Event()
    original = sesion._seguidor.procesar

    def procesar_lento(resultado, instante):
        dentro.set()
        soltar.wait(2.0)
        return original(resultado, instante)

    sesion._seguidor.procesar = procesar_lento
    analisis = threading.Thread(target=lambda: sesion.procesar(SILENCIO, 0.0))
    analisis.start()
    assert dentro.wait(2.0), "el cuadro no llego al seguidor"

    def cambiar():
        sesion.cambiar_plan(PlanDePasada(primer_compas=3, ultimo_compas=4))
        cambiado.set()

    http = threading.Thread(target=cambiar)
    http.start()
    assert not cambiado.wait(0.2), "cambiar_plan se colo dentro de un procesar"

    soltar.set()
    analisis.join(2.0)
    http.join(2.0)
    assert cambiado.is_set()
    assert sesion.plan.primer_compas == 3


def informe_de(filas, ritmo_aproximado=False):
    """Un informe a mano: (numero, escritas, medibles, acertadas, a_tiempo, acordes).

    Las notas limpias valen lo mismo que las acertadas.
    """
    compases = tuple(
        CompasDelInforme(
            numero=n, notas_escritas=e, notas_medibles=m, acertadas=a, a_tiempo=t,
            pronto=0, tarde=0, limpias=a, desfase_medio_s=None, tiene_acordes=acordes,
        )
        for n, e, m, a, t, acordes in filas
    )
    return InformeDePasada(
        compases=compases, ritmo_aproximado=ritmo_aproximado,
        compas_variable=False, factor_tempo=1.0, repeticiones=1,
    )


def pasada_limpia():
    return informe_de([(1, 10, 10, 10, 10, False)])


def pasada_mala():
    return informe_de([(1, 10, 10, 6, 6, False)])


def test_dos_pasadas_buenas_seguidas_suben_el_tempo_un_cinco_por_ciento():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.65)


def test_tras_subir_la_racha_se_consume_y_no_vuelve_a_subir_sola():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.65)
    assert historial.factor_sugerido(0.65) == pytest.approx(0.65)


def test_una_pasada_mala_baja_el_tempo_sin_esperar_a_la_segunda():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_mala())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.55)


def test_el_tempo_no_pasa_del_escrito_ni_baja_del_suelo():
    arriba = HistorialDeEstudio()
    arriba.anotar(pasada_limpia())
    arriba.anotar(pasada_limpia())
    assert arriba.factor_sugerido(FACTOR_MAXIMO) == pytest.approx(FACTOR_MAXIMO)
    abajo = HistorialDeEstudio()
    abajo.anotar(pasada_mala())
    assert abajo.factor_sugerido(FACTOR_MINIMO) == pytest.approx(FACTOR_MINIMO)


def test_una_pieza_entera_de_acordes_nunca_mueve_el_tempo():
    # Sin notas medibles no hay proporcion, y sin proporcion no hay juicio: el
    # tempo se queda donde el usuario lo puso.
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 3, 1, 0, 0, True)]))
    historial.anotar(informe_de([(1, 3, 1, 0, 0, True)]))
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)


def test_los_peores_compases_salen_ordenados_con_sus_cifras():
    historial = HistorialDeEstudio()
    for _ in range(5):
        # El 19 siempre fallado, el 4 fallado una vez, el 7 nunca.
        historial.anotar(informe_de([
            (4, 4, 4, 4, 4, False),
            (7, 4, 4, 4, 4, False),
            (19, 4, 4, 1, 1, False),
        ]))
    historial.anotar(informe_de([
        (4, 4, 4, 2, 2, False),
        (7, 4, 4, 4, 4, False),
        (19, 4, 4, 0, 0, False),
    ]))
    peores = historial.peores_compases(2)
    assert peores[0] == (19, 6, 6)
    assert peores[1] == (4, 1, 6)


def test_los_compases_con_acordes_no_aparecen_entre_los_peores():
    # Esta es la prueba que impide que el boton de machacar mande al usuario a un
    # compas que nunca podra pasar.
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 4, 1, 0, 0, True), (2, 4, 4, 1, 1, False)]))
    assert [c for c, _, _ in historial.peores_compases()] == [2]


def test_un_historial_sin_pasadas_no_tiene_peores_ni_mueve_el_tempo():
    historial = HistorialDeEstudio()
    assert historial.pasadas == 0
    assert historial.peores_compases() == ()
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)


def pasada_con_proporcion(buenas, de=100):
    return informe_de([(1, de, de, buenas, buenas, False)])


def test_las_constantes_de_la_regla_del_tempo_tienen_nombre_y_valor_fijos():
    assert UMBRAL_PARA_SUBIR == 0.90
    assert UMBRAL_PARA_BAJAR == 0.70
    assert PASADAS_BUENAS_PARA_SUBIR == 2


def test_justo_en_el_umbral_de_subir_sube_y_un_punto_por_debajo_no():
    for buenas, esperado in ((90, 0.65), (89, 0.60)):
        historial = HistorialDeEstudio()
        historial.anotar(pasada_con_proporcion(buenas))
        historial.anotar(pasada_con_proporcion(buenas))
        assert historial.factor_sugerido(0.60) == pytest.approx(esperado)


def test_justo_en_el_umbral_de_bajar_no_baja_y_un_punto_por_debajo_si():
    for buenas, esperado in ((70, 0.60), (69, 0.55)):
        historial = HistorialDeEstudio()
        historial.anotar(pasada_con_proporcion(buenas))
        assert historial.factor_sugerido(0.60) == pytest.approx(esperado)


def test_una_sola_pasada_buena_no_sube_el_tempo():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)


def test_las_dos_pasadas_buenas_tienen_que_ser_las_dos_ultimas():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    historial.anotar(pasada_con_proporcion(80))
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)


def test_una_pasada_regular_entre_dos_buenas_corta_la_racha_aunque_no_baje():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    historial.anotar(pasada_con_proporcion(80))
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.65)


def test_una_pasada_mala_antes_de_dos_buenas_no_impide_subir():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_mala())
    historial.anotar(pasada_limpia())
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.65)


def test_una_pasada_mala_tras_dos_buenas_baja_en_vez_de_subir():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    historial.anotar(pasada_limpia())
    historial.anotar(pasada_mala())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.55)


def test_tras_bajar_la_racha_se_consume_y_no_vuelve_a_bajar_sola():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_mala())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.55)
    assert historial.factor_sugerido(0.55) == pytest.approx(0.55)


def test_una_pasada_de_solo_acordes_en_medio_no_corta_la_racha():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    historial.anotar(informe_de([(1, 3, 1, 0, 0, True)]))
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.65)


def test_el_paso_es_el_del_deslizador_y_no_acumula_error_de_coma_flotante():
    historial = HistorialDeEstudio()
    factor = 0.45
    for _ in range(3):
        historial.anotar(pasada_limpia())
        historial.anotar(pasada_limpia())
        factor = historial.factor_sugerido(factor)
    assert factor == 0.60
    assert PASO_DEL_FACTOR == pytest.approx(0.05)


def test_un_compas_acertado_pero_tarde_cuenta_como_fallado_en_los_peores():
    # Tocado bien pero tarde: acertadas = medibles, limpias = 0.
    compas = CompasDelInforme(
        numero=5, notas_escritas=4, notas_medibles=4, acertadas=4, a_tiempo=0,
        pronto=0, tarde=4, limpias=0, desfase_medio_s=0.1, tiene_acordes=False,
    )
    historial = HistorialDeEstudio()
    historial.anotar(InformeDePasada(
        compases=(compas,), ritmo_aproximado=False, compas_variable=False,
        factor_tempo=1.0,
    ))
    assert historial.peores_compases() == ((5, 1, 1),)


def test_los_peores_compases_respetan_el_limite_y_el_orden_de_desempate():
    historial = HistorialDeEstudio()
    # Los compases 8, 3 y 6 fallan una vez de una pasada; el 2 falla una de dos.
    historial.anotar(informe_de([
        (8, 4, 4, 0, 0, False), (3, 4, 4, 0, 0, False),
        (6, 4, 4, 0, 0, False), (2, 4, 4, 0, 0, False), (9, 4, 4, 4, 4, False),
    ]))
    historial.anotar(informe_de([(2, 4, 4, 4, 4, False)]))
    assert historial.peores_compases(10) == (
        (3, 1, 1), (6, 1, 1), (8, 1, 1), (2, 1, 2),
    )
    assert historial.peores_compases(2) == ((3, 1, 1), (6, 1, 1))
    assert len(historial.peores_compases()) == 3


def test_entre_dos_compases_con_los_mismos_fallos_va_primero_el_de_peor_proporcion():
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 4, 4, 0, 0, False), (2, 4, 4, 0, 0, False)]))
    historial.anotar(informe_de([(1, 4, 4, 4, 4, False)]))
    assert historial.peores_compases(2) == ((2, 1, 1), (1, 1, 2))


def test_un_compas_sin_notas_medibles_no_aparece_entre_los_peores():
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 0, 0, 0, 0, False), (2, 4, 4, 2, 2, False)]))
    assert historial.peores_compases() == ((2, 1, 1),)
    solo_vacio = HistorialDeEstudio()
    solo_vacio.anotar(informe_de([(1, 0, 0, 0, 0, False)]))
    assert solo_vacio.peores_compases() == ()


def test_un_compas_nunca_fallado_no_aparece_entre_los_peores():
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 4, 4, 4, 4, False)]))
    assert historial.peores_compases() == ()


def test_el_dict_del_historial_lleva_las_pasadas_y_los_peores_compases():
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(7, 4, 4, 1, 1, False)]))
    assert historial.pasadas == 1
    assert historial.a_dict() == {
        "pasadas": 1,
        "peores_compases": [{"compas": 7, "falladas": 1, "contadas": 1}],
    }


def test_anotar_cuenta_las_pasadas_una_a_una():
    historial = HistorialDeEstudio()
    for esperado in (1, 2, 3):
        historial.anotar(pasada_limpia())
        assert historial.pasadas == esperado


def test_el_dict_distingue_las_falladas_de_las_contadas():
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(7, 4, 4, 1, 1, False)]))
    historial.anotar(informe_de([(7, 4, 4, 4, 4, False)]))
    historial.anotar(informe_de([(7, 4, 4, 4, 4, False)]))
    assert historial.a_dict()["peores_compases"] == [
        {"compas": 7, "falladas": 1, "contadas": 3}
    ]


def test_bajar_el_tempo_no_deja_basura_de_coma_flotante():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_mala())
    assert historial.factor_sugerido(0.60) == 0.55


def test_primero_las_pasadas_falladas_y_luego_la_proporcion():
    # El 1 falla una vez de una (100 %); el 2 falla dos veces de cuatro (50 %).
    # Gana el que mas veces se ha fallado, no el de peor proporcion.
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 4, 4, 0, 0, False), (2, 4, 4, 0, 0, False)]))
    historial.anotar(informe_de([(2, 4, 4, 0, 0, False)]))
    historial.anotar(informe_de([(2, 4, 4, 4, 4, False)]))
    historial.anotar(informe_de([(2, 4, 4, 4, 4, False)]))
    assert historial.peores_compases(2) == ((2, 2, 4), (1, 1, 1))


def test_el_compas_de_la_frontera_no_se_equivoca_con_un_factor_de_tempo():
    """El viaje de segundos a pulsos y vuelta no puede perder un compas.

    Con `factor_tempo=0.95`, el inicio del compas 2 son 4 pulsos, que salen como
    4,2105... segundos de pasada y volvian como 3,9999999999999996 pulsos: un
    pelo por debajo de cuatro, asi que `compas_en` leia compas 1. El numero de
    compas de la pantalla se equivocaba justo al cruzar la barra.
    """
    sesion = SesionDeEstudio(pieza_de_doce_compases(), PlanDePasada(factor_tempo=0.95))
    sesion.colocar_en(4.0 / 0.95)
    assert sesion.estado.instante_pulsos == 4.0
    assert sesion.estado.compas_en_curso == 2
    # Y la frontera de cada compas del tramo, por si el 2 fuera suerte.
    for numero in range(1, 13):
        sesion.colocar_en((numero - 1) * 4.0 / 0.95)
        assert sesion.estado.compas_en_curso == numero, numero


def test_el_redondeo_de_los_pulsos_no_se_come_precision_que_se_vea():
    """El arreglo de la frontera no puede pagarse con un cabezal a saltos.

    Redondear el viaje de vuelta a pulsos arregla el compas de la frontera, pero
    con pocos decimales seria otro defecto: el cabezal se iria al pulso redondo
    mas cercano y la pantalla lo dibujaria a saltitos. Nueve decimales estan muy
    por debajo de cualquier figura -la semifusa de un 4/4 es 0,0625 pulsos-, y
    esta prueba lo fija por si alguien decide que con dos basta.
    """
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.colocar_en(1.2345678)
    assert sesion.estado.instante_pulsos == pytest.approx(1.2345678, abs=1e-7)


# -- arrancar: la cuenta atras de la PRIMERA entrada al tramo ---------------


def test_construir_la_sesion_no_abre_la_cuenta_atras_aunque_el_plan_la_pida():
    # El constructor no es "empezar a tocar": las pruebas del nucleo que colocan
    # el reloj y esperan que la pieza avance dependen de esto.
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    assert sesion.plan.compases_de_cuenta_atras == 1
    assert sesion.estado.cuenta_atras_restante_s == 0.0
    sesion.avanzar(1.0)
    assert sesion.estado.carril.instante_s == pytest.approx(1.0)


def test_tras_arrancar_el_reloj_espera_la_cuenta_atras_y_solo_despues_corre():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    estado = sesion.arrancar()
    # Un compas de 4/4 a 60 ppm: cuatro segundos.
    assert estado.cuenta_atras_restante_s == pytest.approx(4.0)
    assert estado.carril.instante_s == pytest.approx(0.0)
    # Pasa el tiempo, a pasos como el servidor: el reloj de la pieza no se mueve
    # y la cuenta baja.
    for _ in range(3):
        sesion.avanzar(1.0)
        assert sesion.estado.carril.instante_s == pytest.approx(0.0)
    assert sesion.estado.cuenta_atras_restante_s == pytest.approx(1.0)
    # Se agota: ese paso solo gasta la cuenta, y el siguiente ya mueve la pieza.
    sesion.avanzar(1.0)
    assert sesion.estado.cuenta_atras_restante_s == 0.0
    assert sesion.estado.carril.instante_s == pytest.approx(0.0)
    sesion.avanzar(2.0)
    assert sesion.estado.carril.instante_s == pytest.approx(2.0)


def test_arrancar_coloca_el_cabezal_al_inicio_del_tramo_y_no_en_el_compas_uno():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=3, ultimo_compas=4)
    )
    sesion.colocar_en(30.0)
    estado = sesion.arrancar()
    assert estado.compas_en_curso == 3
    assert estado.carril.instante_s == pytest.approx(8.0)
    assert estado.cuenta_atras_restante_s == pytest.approx(4.0)


def test_la_cuenta_de_arrancar_sigue_el_tempo_de_la_pasada():
    sesion = SesionDeEstudio(pieza_de_doce_compases(), PlanDePasada(factor_tempo=0.5))
    assert sesion.arrancar().cuenta_atras_restante_s == pytest.approx(8.0)


def test_durante_la_cuenta_de_arrancar_no_se_cobra_ninguna_nota():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.arrancar()
    # Medio segundo de cuadros con la E2 sonando, que la pieza (nota en el
    # instante 0) cobraria si el reloj corriera. Son menos de los 4 s de cuenta.
    instante = 100.0
    for _ in range(24):
        sesion.procesar(suena("E2"), instante)
        instante += 0.021
    assert sesion.estado.cuenta_atras_restante_s > 0
    assert sesion.estado.carril.tocadas == ()
    assert sesion.estado.carril.instante_s == pytest.approx(0.0)


def test_acabada_la_cuenta_de_arrancar_las_notas_si_se_cobran():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.arrancar()
    instante = 100.0
    # Acotado: si la cuenta nunca bajara, que falle en vez de colgar la suite.
    for _ in range(400):
        if sesion.estado.cuenta_atras_restante_s == 0:
            break
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    assert sesion.estado.cuenta_atras_restante_s == 0
    for _ in range(12):
        sesion.procesar(suena("E2"), instante)
        instante += 0.021
    assert len(sesion.estado.carril.tocadas) == 1


def test_arrancar_con_cero_compases_de_cuenta_no_abre_ninguna_y_la_pieza_corre():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(compases_de_cuenta_atras=0)
    )
    estado = sesion.arrancar()
    assert estado.cuenta_atras_restante_s == 0.0
    sesion.avanzar(1.5)
    assert sesion.estado.carril.instante_s == pytest.approx(1.5)


def test_reiniciar_la_pasada_abre_la_cuenta_igual_que_arrancar():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.arrancar()
    sesion.avanzar(4.0)
    sesion.avanzar(5.0)
    assert sesion.estado.carril.instante_s == pytest.approx(5.0)
    estado = sesion.reiniciar_pasada()
    assert estado.cuenta_atras_restante_s == pytest.approx(4.0)
    assert estado.carril.instante_s == pytest.approx(0.0)
    assert estado.repeticion == 1
    sesion.avanzar(2.0)
    assert sesion.estado.carril.instante_s == pytest.approx(0.0)


def test_reiniciar_la_pasada_sin_cuenta_en_el_plan_no_abre_ninguna():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(compases_de_cuenta_atras=0)
    )
    sesion.avanzar(5.0)
    assert sesion.reiniciar_pasada().cuenta_atras_restante_s == 0.0


def test_la_congelacion_de_la_cuenta_atras_no_depende_de_quien_la_abra():
    # Las dos puertas del reloj recolocan el cabezal en el inicio en cada mirada
    # mientras dura la cuenta, ademas de no avanzarlo: es una DEFENSA por si algun
    # dia la cuenta se abre sin colocar el cabezal (hoy lo hacen `arrancar` y
    # `_dar_la_vuelta`, que ya lo colocan, y sin esta prueba quitar las dos lineas
    # no tira nada). Por eso se abre a mano, tocando el atributo privado.
    for puerta in ("avanzar", "procesar"):
        sesion = SesionDeEstudio(
            pieza_de_doce_compases(), PlanDePasada(compases_de_cuenta_atras=0)
        )
        sesion.avanzar(2.5)
        assert sesion.estado.carril.instante_s == pytest.approx(2.5)
        sesion._cuenta_atras_restante_s = 4.0
        if puerta == "avanzar":
            sesion.avanzar(1.0)
        else:
            sesion.procesar(suena("E2"), 100.0)
        assert sesion.estado.carril.instante_s == pytest.approx(0.0), puerta


class DetectorDeOnsetsDichos:
    """Suelta pulsaciones con el onset que se le diga, en el cuadro que se le diga.

    Lo que estas pruebas miden es el reparto de un onset entre dos vueltas, y el
    onset se pone a mano para que la prueba no mida ademas la energia del audio ni
    la espera del detector de verdad. Mismo recurso que en
    `tests/test_seguimiento_pieza.py`.
    """

    def __init__(self, onsets_por_cuadro):
        self.onsets_por_cuadro = dict(onsets_por_cuadro)
        self.cuadros = 0

    def reiniciar(self):
        self.cuadros = 0

    def procesar(self, resultado, instante):
        self.cuadros += 1
        onset = self.onsets_por_cuadro.pop(self.cuadros, None)
        if onset is None:
            return None
        return Pulsacion(nota="E2", cents=0.0, instante=onset)


def test_la_cola_no_cobra_una_nota_que_la_vuelta_ya_habia_cobrado():
    """**Un compas no puede salir con mas acertadas que notas escritas.**

    El caso, medido por una revision: la unica nota del tramo se cobra a tiempo
    por el camino normal, y despues de la vuelta el detector firma OTRO ataque
    tambien anterior a la frontera, que entra por la cola y la cobraba OTRA VEZ.
    Dos ataques cerca de la frontera no es nada exotico: es lo que pasa machacando
    un compas. El informe de la vuelta salia con `acertadas=2` sobre
    `notas_escritas=1`, y de esos contadores cuelga el tempo automatico.

    Por que no lo puede arreglar el seguidor: el que repite llama a
    `olvidar_tramo` ANTES del salto -es su contrato, para que la vuelta nueva
    pueda volver a cobrar-, asi que cuando el salto llega el seguidor ya no sabe
    que llevaba cobrado el tramo que se va. El unico que lo sabe es quien cerro la
    vuelta, y por eso la guarda vive en `_cobrar_la_cola`.

    Lo repetido se descarta, no se re-adjudica a otra nota: es lo mismo que hace
    `_adjudicar` con una pulsacion que no alcanza a ninguna nota reclamable.
    """
    # Cuadro 1: el ataque bueno, en 2,95, que la nota de 3,0 reclama «a tiempo».
    # Cuadro 60: ya pasada la vuelta, otro ataque de 3,9 -anterior a la frontera-
    # que entra por la cola y apunta a la misma nota.
    detector = DetectorDeOnsetsDichos({1: 2.95, 60: 3.9})
    sesion = SesionDeEstudio(
        pieza_de([3.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
        detector=detector,
    )
    sesion.colocar_en(2.9)
    instante = 2.9
    for _ in range(62):
        sesion.procesar(SILENCIO, instante)
        instante += 0.021

    assert sesion.estado.repeticion == 2
    cerrada = compas_numero(sesion.ultima_vuelta, 1)
    assert cerrada.notas_escritas == 1
    assert cerrada.acertadas == 1, (
        "la cola volvio a cobrar una nota que la vuelta ya tenia cobrada: "
        f"{cerrada.acertadas} acertadas sobre 1 nota escrita"
    )
    assert cerrada.a_tiempo == 1
    assert cerrada.tarde == 0
    assert [t.indice for t in sesion.tocadas_de_la_ultima_vuelta] == [0]
    # Y la pasada tampoco la cuenta dos veces.
    assert compas_numero(sesion.informe, 1).acertadas == 1


@pytest.mark.parametrize("paso", (0.0075, 0.021, 0.040, 0.100))
def test_la_vuelta_no_se_come_tiempo_a_ninguna_cadencia(paso):
    """La invariante del reloj, a cuatro cadencias de cuadro distintas.

    **Esta prueba existe porque su ausencia era un agujero.** El nucleo no conoce
    la cadencia del hilo de analisis de quien lo conduce -`INTERVALO_DE_ANALISIS_S`
    es la de produccion, no la del llamador-, y por eso la vuelta del bucle le pasa
    al seguidor la correspondencia ESCRITA en vez de estimar un cuadro. Pero toda
    prueba del camino con audio corria a exactamente 21 ms por cuadro, asi que un
    numero clavado habria pasado igual: el argumento de diseño que mas se defiende
    en este codigo no lo sujetaba nada.

    Medido con la version que estimaba: a `paso=0.040` el reloj se desvia 76 ms
    sobre esta pasada, y con la correspondencia escrita se desvia 0,000.

    Las cuatro cadencias son reales: 7,5 ms es un bloque de 360 muestras a 48 kHz,
    21 ms es la de produccion, 40 y 100 ms son las de un hilo de analisis lento (y
    100 ms es el techo de `mover_el_reloj`, o sea lo mas que el servidor deja
    pasar entre dos avisos).
    """
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    arranque = 100.0
    sesion.colocar_en(0.0)
    cuadros = int(12.0 / paso)
    vueltas = 0
    for cuadro in range(cuadros):
        instante = arranque + cuadro * paso
        antes = sesion.estado.repeticion
        estado = sesion.procesar(SILENCIO, instante)
        vueltas = estado.repeticion - 1
        if estado.repeticion != antes:
            continue
        recorrido = estado.carril.instante_s + vueltas * 4.0
        assert recorrido == pytest.approx(instante - arranque, abs=1e-9), (
            f"a {paso * 1000:.1f} ms por cuadro, en el cuadro {cuadro} el cabezal "
            f"lleva {recorrido:.6f} s y el analisis {instante - arranque:.6f} s"
        )
    assert vueltas >= 2, (
        "la pasada tiene que dar al menos dos vueltas, o no mide el arrastre"
    )


def test_un_hueco_de_audio_en_la_frontera_no_se_cuenta_dos_veces():
    """Un cuadro que llega TARDE justo al cruzar el final no descoloca la vuelta.

    **Era un defecto que este mismo arreglo introdujo y que una revision midio.**
    La version anterior le sumaba al exceso «la cadencia recien medida»; si el
    cuadro que cruza el final llegaba tarde, ese retraso entraba en el exceso -que
    es correcto, el reloj si avanzo- **y otra vez** en la cadencia, que era lo que
    se sumaba. Con un hueco de 300 ms en la frontera, la vuelta nueva arrancaba en
    0,359 s en vez de 0,059, y con un tramo corto el tope se lo comia entero y la
    vuelta se saltaba. Ninguna prueba alimentaba una cadencia irregular, asi que
    nada lo vio.

    Aqui la cadencia es irregular a proposito: cuadros de 21 ms y UNO de 300 ms
    colocado para que sea el que cruza el final del tramo. Lo que se afirma es la
    misma invariante que a cadencia regular -el cabezal mas las vueltas dadas es
    el tiempo de analisis transcurrido-, que con el hueco contado dos veces se
    rompe por los 300 ms justos.
    """
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    arranque = 100.0
    sesion.colocar_en(0.0)
    # El cuadro del hueco se coloca en 3,9: el siguiente cae en 4,2, o sea 200 ms
    # PASADO el final del tramo, que es el cuadro que da la vuelta.
    instante = arranque
    transcurrido = 0.0
    hueco_dado = False
    vueltas = 0
    for _ in range(700):
        antes = sesion.estado.repeticion
        estado = sesion.procesar(SILENCIO, instante)
        vueltas = estado.repeticion - 1
        if estado.repeticion == antes:
            recorrido = estado.carril.instante_s + vueltas * 4.0
            assert recorrido == pytest.approx(transcurrido, abs=1e-9), (
                f"con el hueco dentro, el cabezal lleva {recorrido:.6f} s y el "
                f"analisis {transcurrido:.6f} s"
            )
        paso = 0.021
        if not hueco_dado and transcurrido >= 3.9:
            paso = 0.300
            hueco_dado = True
        instante += paso
        transcurrido += paso
    assert hueco_dado
    assert vueltas >= 2
