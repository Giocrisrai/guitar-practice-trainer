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
