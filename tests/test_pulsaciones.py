import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones

PASO = 0.021


def suena(nota="E2", nivel=-25.0, confianza=0.9, cents=0.0) -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=confianza, nivel_db=nivel,
        nota=nota, cents=cents, posiciones=(),
    )


def silencio() -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
        nota=None, cents=None, posiciones=(),
    )


def correr(detector, cuadros, instante=0.0):
    """Pasa una lista de resultados y devuelve las pulsaciones que salieron."""
    salidas = []
    for resultado in cuadros:
        pulsacion = detector.procesar(resultado, instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO
    return salidas


def test_una_pulsacion_limpia_da_una_sola_salida():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena()] * 12)
    assert len(salidas) == 1
    assert salidas[0].nota == "E2"


def test_la_cola_de_la_nota_no_produce_una_segunda():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(nivel=n) for n in range(-25, -5)])
    assert len(salidas) == 1


def test_un_ataque_sin_nota_creible_no_produce_nada():
    """Regla 1: un golpe en la caja o una cuerda apagada no es un intento."""
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(confianza=0.2)] * 12)
    assert salidas == []


def test_tras_un_hueco_la_misma_nota_vuelve_a_contar():
    detector = DetectorPulsaciones()
    cuadros = [silencio()] * 6 + [suena()] * 10 + [silencio()] * 6 + [suena()] * 10
    assert len(correr(detector, cuadros)) == 2


def test_la_pulsacion_trae_los_cents_de_lo_que_sono():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(cents=-14.0)] * 12)
    assert salidas[0].cents == pytest.approx(-14.0)


def test_el_instante_es_el_del_ataque_no_el_de_la_lectura():
    """El ataque de energia marca cuando empezo la nota; la lectura del tono llega
    despues. Anotar la lectura convertiria el retraso del detector en desfase del
    alumno."""
    detector = DetectorPulsaciones()
    instante = 0.0
    for _ in range(6):
        detector.procesar(silencio(), instante)
        instante += PASO
    inicio = instante
    salidas = []
    for _ in range(12):
        pulsacion = detector.procesar(suena(), instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO
    assert salidas[0].instante == pytest.approx(inicio, abs=PASO)


def test_senal_de_nota_nueva_distingue_la_cola_de_un_intento():
    """Lo que la regla de la ayuda por tiempo necesita: senal creible que NO sea
    la nota que se acaba de resolver."""
    detector = DetectorPulsaciones()
    correr(detector, [silencio()] * 6 + [suena()] * 12)
    detector.procesar(suena(), 1.0)          # cola de la misma nota
    assert detector.senal_de_nota_nueva is False
    detector.procesar(suena(nota="A2"), 1.1)  # otra nota: eso si es un intento
    assert detector.senal_de_nota_nueva is True


# Las cuatro correcciones que costaron tres rondas en la etapa anterior estaban
# fijadas solo a traves del evaluador de ejercicios. A partir de la Task 4 hay
# quien usa este detector sin evaluador delante, asi que se fijan aqui tambien,
# en el punto donde se usan. Ninguna toca lo privado: se montan las secuencias de
# cuadros que reproducen cada fallo y se mira lo que sale.


def dudoso(nota="E2", nivel=-25.0) -> ResultadoAnalisis:
    """Lectura con nota pero sin confianza: el detector de tono flaqueando.

    Mismo nivel que la nota que suena, a proposito: asi no hay salto de energia
    y el bache no arrastra consigo un ataque que confundiria lo que se mide.
    """
    return suena(nota=nota, nivel=nivel, confianza=0.2)


def test_un_ataque_sobre_la_nota_ya_resuelta_no_firma_el_onset_de_la_siguiente():
    """Un hinchado de volumen o un roce sobre la nota aceptada marca un ataque de
    energia que el filtro de nombre descarta. Si ese ataque se quedara guardado,
    `_onset_camino_b` lo firmaria como onset de la pulsacion SIGUIENTE, que puede
    llegar hasta VENTANA_ATAQUE_COMO_ONSET_S despues: el informe diria que esa
    nota sono antes de que sonara.
    """
    detector = DetectorPulsaciones()
    instante = 0.0
    salidas = []

    def dar(resultado):
        nonlocal instante
        pulsacion = detector.procesar(resultado, instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO

    for _ in range(6):
        dar(silencio())
    # Primera pulsacion, resuelta con su propio ataque.
    for _ in range(12):
        dar(suena())

    # Hinchado: la MISMA nota sube 15 dB. Eso es un ataque de energia, y el
    # filtro de nombre lo descarta porque E2 ya se resolvio.
    instante_hinchado = instante
    for _ in range(4):
        dar(suena(nivel=-10.0))

    # La nota cambia SIN salto de energia (mismo nivel): nadie marca un ataque
    # nuevo, asi que el unico ataque que `_onset_camino_b` podria tomar es el del
    # hinchado, y todavia esta dentro de su ventana.
    instante_nota_nueva = instante
    for _ in range(6):
        dar(suena(nota="A2", nivel=-10.0))

    assert len(salidas) == 2
    assert salidas[1].nota == "A2"
    assert instante_nota_nueva - instante_hinchado < 0.25  # dentro de la ventana
    assert salidas[1].instante == pytest.approx(instante_nota_nueva)
    assert salidas[1].instante > instante_hinchado


def test_un_solo_cuadro_dudoso_no_resuelve_dos_veces_la_misma_nota():
    """El detector de tono flaquea a mitad de una nota sostenida sin que la
    pulsacion haya terminado. Olvidar la ultima nota resuelta al primer bache
    haria que esa misma pulsacion se contara otra vez. Hacen falta
    `cuadros_para_olvidar_nota` cuadros SEGUIDOS sin nota creible.
    """
    detector = DetectorPulsaciones()
    con_un_bache = correr(
        detector,
        [silencio()] * 6 + [suena()] * 8 + [dudoso()] + [suena()] * 8,
    )
    assert len(con_un_bache) == 1

    # Y con el hueco completo si: un hueco real es la frontera entre pulsaciones.
    otro = DetectorPulsaciones()
    con_hueco = correr(
        otro,
        [silencio()] * 6
        + [suena()] * 8
        + [dudoso()] * otro.cuadros_para_olvidar_nota
        + [suena()] * 8,
    )
    assert len(con_hueco) == 2


def test_el_onset_del_camino_b_es_el_comienzo_de_la_racha_no_el_final():
    """`regularidad_ms` mide huecos entre onsets, asi que sellar el final de la
    racha estable en vez de su comienzo fabrica irregularidad sobre una ejecucion
    perfecta: a `cuadros_para_nota_estable` cuadros de 21 ms, 42 ms de sesgo.

    El caso se monta para que los tres instantes candidatos sean distintos por
    construccion: el ataque de energia (descartado aqui por viejo), el comienzo
    de la racha creible y el cuadro en que la racha se da por estable.
    """
    detector = DetectorPulsaciones()
    instante = 0.0
    salidas = []

    def dar(resultado):
        nonlocal instante
        pulsacion = detector.procesar(resultado, instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO

    for _ in range(3):
        dar(silencio())

    # Hay ataque de energia, pero el tono tarda en cuajar: 14 cuadros con nivel
    # pero sin confianza. Cuando la racha creible resuelva, ese ataque sera mas
    # viejo que VENTANA_ATAQUE_COMO_ONSET_S y no podra firmar el onset.
    instante_ataque = instante
    for _ in range(14):
        dar(dudoso())

    # Aqui empieza la racha creible, y aqui es donde debe quedar el onset.
    instante_inicio_racha = instante
    for _ in range(6):
        dar(suena())

    assert len(salidas) == 1
    onset = salidas[0].instante
    instante_racha_estable = (
        instante_inicio_racha + (detector.cuadros_para_nota_estable - 1) * PASO
    )
    assert instante_racha_estable - instante_ataque > 0.25  # el ataque ya es viejo
    assert instante_racha_estable > instante_inicio_racha  # comienzo != final
    assert onset == pytest.approx(instante_inicio_racha)


def cuadros_con_descarte_del_camino_b(cuadros_de_la_nota_nueva: int):
    """La secuencia exacta del defecto del onset nulo.

    1. Seis cuadros de silencio y doce de E2: la pulsacion se resuelve y E2 queda
       sellada como `_ultima_nota_resuelta`.
    2. Tres cuadros de E2 diez dB mas fuerte: un hinchado de volumen sobre la
       nota que ya se conto. El salto marca un ataque nuevo, asi que el camino A
       se anota una lectura pendiente para 60 ms despues; el camino B, que lleva
       la racha de E2, resuelve antes y la DESCARTA por nombre.
    3. La nota cambia a A2 justo en el cuadro en que vencia la lectura pendiente.
    """
    return (
        [silencio()] * 6
        + [suena()] * 12
        + [suena(nivel=-15.0)] * 3
        + [suena("A2", nivel=-15.0)] * cuadros_de_la_nota_nueva
    )


def test_el_descarte_por_nombre_no_deja_al_camino_a_resolver_sin_onset():
    """El descarte del camino B borraba el ataque pero no la lectura pendiente.

    Asi que el camino A resolvia despues con `instante=None`: una pulsacion
    fantasma -un solo cuadro de A2, que el camino B no habria dado por estable- y
    encima sin onset. En un ejercicio costaba una muestra de `regularidad_ms`; en
    el carril, el seguidor se queda sin onset y busca con el reloj del cuadro,
    hasta 250 ms despues del ataque real, con lo que puede cobrar la nota
    siguiente.
    """
    detector = DetectorPulsaciones()
    salidas = correr(detector, cuadros_con_descarte_del_camino_b(1))
    assert [pulsacion.nota for pulsacion in salidas] == ["E2"]
    assert all(pulsacion.instante is not None for pulsacion in salidas)


def test_la_nota_nueva_que_de_verdad_suena_se_resuelve_igual_y_con_su_onset():
    """La otra mitad: cancelar la lectura pendiente no se come ninguna nota real.

    Si A2 sigue sonando, el camino B la da por estable y la resuelve con su
    propio onset. Lo que se pierde es solo la pulsacion de un unico cuadro que
    ningun camino habria confirmado.
    """
    detector = DetectorPulsaciones()
    salidas = correr(detector, cuadros_con_descarte_del_camino_b(4))
    assert [pulsacion.nota for pulsacion in salidas] == ["E2", "A2"]
    assert all(pulsacion.instante is not None for pulsacion in salidas)
