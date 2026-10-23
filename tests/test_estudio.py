"""La sesion de estudio: el plan, el reloj de la pasada y lo que ve la interfaz.

Ni una espera real: el reloj se mueve a mano con `avanzar_a`, igual que en
`tests/test_seguimiento_pieza.py`.
"""

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.piezas.estudio import (
    FACTOR_MAXIMO,
    FACTOR_MINIMO,
    PASO_DEL_FACTOR,
    CompasDelInforme,
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
    sesion.colocar_en(12.0)
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
    normal.colocar_en(4.0)
    assert normal.estado.cuenta_atras_restante_s == pytest.approx(4.0)
    lenta = SesionDeEstudio(
        pieza,
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True, factor_tempo=0.5),
    )
    lenta.colocar_en(8.0)
    assert lenta.estado.cuenta_atras_restante_s == pytest.approx(8.0)


def test_durante_la_cuenta_atras_el_reloj_no_avanza():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.colocar_en(4.0)
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
    sesion.colocar_en(4.0)
    assert sesion.estado.cuenta_atras_restante_s > 0
    instante = 100.0
    for _ in range(20):
        sesion.procesar(suena("E2"), instante)
        instante += 0.021
    assert sesion.estado.carril.tocadas == ()


def test_tras_la_vuelta_del_bucle_las_notas_se_pueden_volver_a_cobrar():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    tocar(sesion, "E2", en=0.0)
    assert len(sesion.estado.carril.tocadas) == 1
    sesion.colocar_en(4.0)          # da la vuelta
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
    sesion.colocar_en(8.0)
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
    sesion.colocar_en(4.0)
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
    sesion.colocar_en(8.0)
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
    sesion.colocar_en(4.0)
    sesion.colocar_en(4.0)
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

    def avanzar_a(self, instante_s):
        self._llamadas.append(("avanzar_a", instante_s))
        return self._seguidor.avanzar_a(instante_s)

    def __getattr__(self, nombre):
        return getattr(self._seguidor, nombre)


def espiar(sesion):
    llamadas = []
    sesion._seguidor = EspiaDelSeguidor(sesion._seguidor, llamadas)
    return llamadas


def test_la_vuelta_del_bucle_olvida_el_tramo_antes_de_colocar_el_reloj():
    # Contrato de orden: `avanzar_a` es quien descarta las pulsaciones en vuelo
    # y va DESPUES de `olvidar_tramo`. Como las dos operaciones no se pisan, el
    # resultado final no distingue el orden; por eso se mide la secuencia.
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=2, ultimo_compas=3, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    llamadas = espiar(sesion)
    sesion.colocar_en(12.0)
    # Tras la colocacion del llamador y el volcado del informe, vienen estas dos.
    assert llamadas[-2:] == [("olvidar_tramo", 4.0, 12.0), ("avanzar_a", 4.0)]


def test_saltar_al_compas_olvida_su_tramo_y_despues_coloca_el_reloj():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    llamadas = espiar(sesion)
    sesion.saltar_al_compas(3)
    # Del compas 3 (segundo 8) al final del tramo (segundo 48), y luego el reloj.
    assert llamadas[-2:] == [("olvidar_tramo", 8.0, 48.0), ("avanzar_a", 8.0)]


def test_la_cuenta_atras_se_agota_con_cuadros_de_audio_y_despues_la_pasada_corre():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.colocar_en(4.0)
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
    sesion.colocar_en(4.0)
    sesion.procesar(SILENCIO, 10.0)
    sesion.procesar(SILENCIO, 11.0)
    restante = sesion.estado.cuenta_atras_restante_s
    sesion.procesar(SILENCIO, 9.0)
    assert sesion.estado.cuenta_atras_restante_s <= restante


def test_colocar_el_cabezal_en_plena_cuenta_atras_la_cancela():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=2, en_bucle=True)
    )
    sesion.colocar_en(8.0)
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
    sesion.colocar_en(4.0)
    assert sesion.ultima_vuelta is not None
    sesion.reiniciar_pasada()
    assert sesion.ultima_vuelta is None
