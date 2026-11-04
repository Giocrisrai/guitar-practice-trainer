import pytest

from nucleo.analisis.pipeline import TAMANO_SUAVIZADO, ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import (
    CUADROS_PARA_NOTA_ESTABLE,
    VENTANA_ATAQUE_COMO_ONSET_S,
    DetectorPulsaciones,
)

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


# La secuencia del defecto del gemelo digital, en miniatura. Los indices son
# parte del caso y por eso tienen nombre: lo que hace la trampa es que la espera
# de estabilizacion del camino A VENZA mientras el suavizador del pipeline
# todavia publica la altura de la nota anterior.
#
#   0-5    silencio
#   6-15   D4 a -25 dB: la primera pulsacion, que deja D4 sellada
#   16-18  D4 sin confianza a -40 dB: el hueco que libera `_ultima_nota_resuelta`
#   19-20  D4 sin confianza a -15 dB: el transitorio de la pua. EL ATAQUE ES AQUI
#   21-22  D4 creible a -15 dB: los dos cuadros que el suavizador publica tarde
#   23+    E4 creible: la altura que de verdad suena desde el cuadro 19
CUADRO_DEL_ATAQUE = 19
CUADROS_DE_ALTURA_VIEJA = (21, 22)


def cuadros_con_la_altura_vieja_publicada_tarde():
    """La frontera entre dos notas tal y como el pipeline la publica de verdad.

    Reproduce con dobles lo medido sobre el gemelo: tras el ataque de la nota
    nueva, el pipeline sigue publicando la altura de la ANTERIOR durante dos
    cuadros, porque su suavizador es una mediana de cinco y no gira hasta que
    tres de sus cinco entradas son nuevas. Esos dos cuadros son dos SIEMPRE
    -medido sobre 30 semillas de sintesis y 7 fronteras de nota: 2 en los 150
    casos, nunca 1 y nunca 3-, y la espera de estabilizacion del camino A
    (60 ms, menos de tres cuadros) vence dentro de ellos.
    """
    return (
        [silencio()] * 6
        + [suena("D4", nivel=-25.0)] * 10
        + [dudoso("D4", nivel=-40.0)] * 3
        + [dudoso("D4", nivel=-15.0)] * 2
        + [suena("D4", nivel=-15.0)] * 2
        + [suena("E4", nivel=-15.0)] * 8
    )


def test_el_camino_a_no_sella_la_altura_vieja_que_el_suavizador_publica_tarde():
    """**LA CAUSA del defecto del oraculo de la Task 6b, clavada aqui.**

    El camino A no debe leer la nota de un cuadro suelto. Cuando su espera de
    estabilizacion vence, la altura que el pipeline publica puede ser todavia la
    de la nota ANTERIOR: la ventana de analisis mide 85,3 ms y el suavizador de
    mediana 5 añade 42 ms, asi que el giro llega hasta 127 ms despues del ataque
    y la espera son 60 ms. Leyendo ahi, el camino A sellaba el ataque de la nota
    nueva CON LA ALTURA DE LA VIEJA.

    Lo que eso costaba, medido sobre el gemelo: 5 de 30 semillas de sintesis
    daban un veredicto sucio con un interprete PERFECTO, con la cola del tramo
    perdida y desfases de hasta -460,7 ms. Esta prueba es la causa; el sintoma
    esta en `test_el_oraculo_sin_bucle_sigue_limpio_con_otra_semilla`.

    Contrafactual MEDIDO contra el detector de antes del arreglo, con esta misma
    secuencia: salian TRES pulsaciones -D4 en el cuadro 8, un D4 FANTASMA en el
    22 firmado con el ataque de la nota nueva (0,399) y E4 en el 25 con el
    comienzo de la racha (0,483) en vez de con su ataque-. Las tres aserciones
    de abajo son una por cada cosa que estaba mal.

    QUE MATA Y QUE NO, dicho para que nadie se confie. Mata el mutante que
    importa: quitarle al camino A la condicion de racha estable, es decir
    deshacer el arreglo, devuelve las tres pulsaciones y la prueba se pone roja.
    NO mata el mutante que apaga el camino A entero, y eso no es un descuido
    suyo: con el ataque reciente, `_onset_camino_b` devuelve el mismo instante
    que el camino A habria firmado, asi que los dos caminos producen aqui
    exactamente la misma pulsacion. El caso que los distingue existe, es rarisimo
    y hubo que encontrarlo por fuerza bruta; esta en
    `test_el_camino_a_reinicia_la_racha_y_eso_salva_el_onset_siguiente`.
    """
    detector = DetectorPulsaciones()
    cuadros = cuadros_con_la_altura_vieja_publicada_tarde()

    # La secuencia tiene que tender la trampa de verdad: la espera de
    # estabilizacion vence DENTRO de los cuadros que publican la altura vieja.
    instante_ataque = CUADRO_DEL_ATAQUE * PASO
    vencimiento = instante_ataque + detector.espera_estabilizacion_s
    primero, ultimo = CUADROS_DE_ALTURA_VIEJA
    assert cuadros[primero].nota == cuadros[ultimo].nota == "D4"
    assert cuadros[ultimo + 1].nota == "E4"
    assert primero * PASO < vencimiento <= ultimo * PASO

    salidas = correr(detector, cuadros)

    # Una pulsacion por nota y ninguna fantasma: el D4 del cuadro 22 no esta.
    assert [pulsacion.nota for pulsacion in salidas] == ["D4", "E4"]
    # Y la nota nueva conserva el onset de SU ataque, no el comienzo de su racha:
    # el camino A sigue aportando el onset aunque ahora espere a la altura.
    assert salidas[1].instante == pytest.approx(instante_ataque)


def test_la_racha_estable_supera_al_suavizador():
    """El margen del arreglo del camino A, AFIRMADO donde se puede romper.

    Lo que impide que el camino A vuelva a sellar el ataque de una nota con la
    altura de la ANTERIOR es una desigualdad entre dos modulos:

        CUADROS_PARA_NOTA_ESTABLE > TAMANO_SUAVIZADO // 2

    Una mediana movil de n no gira hasta que `n // 2 + 1` de sus entradas son
    nuevas, asi que tras un cambio de altura el pipeline publica la altura vieja
    durante `n // 2` cuadros: 2 con el suavizador de cinco. Si la racha que el
    camino A exige no superara esa cifra, esperar a la racha no serviria de nada
    y el defecto de la Task 6b volveria entero.

    Se cuenta en CUADROS por los dos lados, asi que la desigualdad no depende
    de la frecuencia de muestreo, ni del tempo, ni del salto de analisis: es la
    parte robusta del margen y por eso es la que se afirma.

    **NO es todo el margen, y conviene no leerla como una garantia.** La racha
    vieja real es `TAMANO_SUAVIZADO // 2` MAS los cuadros cuya ventana de
    analisis cruza la frontera entre dos notas y aun publican la altura vieja de
    forma creible, y ese segundo sumando depende del perfil de afinacion. Medido
    sobre 30 semillas de sintesis x 7 fronteras de nota:

        guitarra estandar  ventana  85,3 ms (4,1 cuadros)  racha vieja 2  margen 1
        bajo de 4 cuerdas  ventana 170,7 ms (8,1 cuadros)  racha vieja 3  margen 0
        bajo de 5 cuerdas  ventana 170,7 ms (8,1 cuadros)  racha vieja 3  margen 0

    Con el bajo el margen es CERO. Esta prueba seguiria verde y el defecto
    estaria de vuelta, asi que no cubre el bajo: lo dice para que nadie crea que
    si. Ver el docstring de `nucleo/ejercicios/pulsaciones.py`.

    **Y hay un segundo limite, del mismo tipo:** se afirma sobre la CONSTANTE del
    modulo, pero `Suavizador(tamano=...)` y `Analizador(tamano_suavizado=...)`
    aceptan cualquier valor, asi que un suavizador construido a mano con siete
    entradas publicaria la altura vieja durante tres cuadros y tampoco lo veria
    nadie. Y el parametro SE USA: `herramientas/grabar_muestras.py` construye el
    analizador con `tamano_suavizado=1` para ver cada ventana tal cual, y
    `tests/test_pipeline.py` pasa 1, 3 y 5. Lo que hoy salva la desigualdad es
    que todos esos valores son MENORES O IGUALES que la constante -y 1 es ademas
    el caso sin retraso ninguno-, no que nadie toque el parametro. Nada lo
    impone: pasar 7 romperia el margen en silencio. Se deja nombrado y no
    cubierto porque la comprobacion correcta tendria que mirar el tamaño de la
    INSTANCIA del suavizador, y el detector de pulsaciones no tiene acceso a
    ella; el dia que haga falta, ese es el sitio por donde empezar.
    """
    assert CUADROS_PARA_NOTA_ESTABLE > TAMANO_SUAVIZADO // 2


def test_una_altura_que_solo_cuaja_dos_cuadros_no_se_cuenta():
    """El CASO DEGRADADO del arreglo del camino A, escrito y probado.

    Desde que el camino A espera racha estable, una pulsacion cuya altura solo
    se publica de forma creible durante menos de `cuadros_para_nota_estable`
    cuadros no se cuenta: ni el camino A (no hay racha) ni el camino B (igual)
    la resuelven. Antes el camino A la habria cobrado leyendo un solo cuadro.

    Es el precio del arreglo y no un defecto nuevo, pero es un precio REAL: son
    notas muy cortas o muy apagadas -un staccato seco, una nota cortada con la
    palma, un armonico que se apaga enseguida-. Con guitarra estandar no se ha
    observado en audio (las rachas creibles de una nota normal duran veinte
    cuadros y mas), asi que el caso se deja escrito aqui, no corregido: el dia
    que aparezca tocando, esta prueba es donde empieza la conversacion, y
    cambiarla sera deliberado.
    """
    detector = DetectorPulsaciones()
    salidas = correr(
        detector,
        [silencio()] * 6
        + [suena("E4")] * (detector.cuadros_para_nota_estable - 1)
        + [silencio()] * 6,
    )
    assert salidas == []

    # Y la contraprueba, para que la de arriba no pase por un motivo tonto: con
    # un cuadro creible mas, la misma pulsacion si se cuenta.
    otro = DetectorPulsaciones()
    con_uno_mas = correr(
        otro,
        [silencio()] * 6
        + [suena("E4")] * otro.cuadros_para_nota_estable
        + [silencio()] * 6,
    )
    assert [pulsacion.nota for pulsacion in con_uno_mas] == ["E4"]


# El paso de las dos pruebas de la caducidad NO es el de produccion (21 ms), y
# es a proposito: 0,25/16 = 0,015625 es exacto en binario, asi que
# `ataque + 16 pasos - ataque` da EXACTAMENTE `VENTANA_ATAQUE_COMO_ONSET_S` y el
# borde se puede probar en la igualdad en vez de cerca de ella. Con 21 ms la
# resta no cae nunca justo en el filo y el borde quedaria sin clavar.
PASO_FINO = VENTANA_ATAQUE_COMO_ONSET_S / 16
INSTANTE_DEL_ATAQUE = 0.25


def secuencia_que_envejece_el_ataque(cuadros_dudosos: int):
    """Un ataque y una racha creible que llega `cuadros_dudosos + 1` pasos despues.

    El ataque cae en un cuadro SIN confianza -el transitorio de la pua-, detras
    van cuadros dudosos al mismo nivel (que no marcan ataque nuevo: el
    refractario y la mediana de la referencia lo impiden, y la prueba lo
    comprueba) y al final tres cuadros creibles de otra altura.
    """
    sec = [(0.0, silencio()), (0.1, silencio()), (INSTANTE_DEL_ATAQUE, dudoso("D4", nivel=-15.0))]
    for k in range(1, cuadros_dudosos + 1):
        sec.append((INSTANTE_DEL_ATAQUE + k * PASO_FINO, dudoso("D4", nivel=-15.0)))
    for k in range(cuadros_dudosos + 1, cuadros_dudosos + 4):
        sec.append((INSTANTE_DEL_ATAQUE + k * PASO_FINO, suena("E4", nivel=-15.0)))
    return sec


def correr_con_instantes(detector, instantes_y_cuadros):
    """Como `correr`, pero con el instante de cada cuadro escrito a mano."""
    salidas = []
    for instante, resultado in instantes_y_cuadros:
        pulsacion = detector.procesar(resultado, instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
    return salidas


def test_un_ataque_justo_en_el_filo_todavia_firma_el_onset():
    """El borde de la caducidad del camino A: la igualdad TODAVIA firma.

    La lectura pendiente del camino A se abandona cuando el ataque envejece MAS
    de `VENTANA_ATAQUE_COMO_ONSET_S`, no cuando llega a esa edad, y la
    desigualdad estricta no es un detalle de estilo: tiene que coincidir con la
    de `_onset_camino_b`, que usa `<=` y por tanto SI firma con un ataque de
    exactamente esa edad. Si una usara `>` y la otra `<=` con otro valor, el
    mismo ataque seria a la vez demasiado viejo para esperarlo y lo bastante
    joven para firmarlo, que es incoherente.

    Aqui la racha cuaja a los 16 pasos finos del ataque, o sea exactamente
    `VENTANA_ATAQUE_COMO_ONSET_S` despues, y el onset tiene que ser el del
    ataque. Cambiar el `>` por `>=` deja el onset en el comienzo de la racha.
    """
    detector = DetectorPulsaciones()
    salidas = correr_con_instantes(detector, secuencia_que_envejece_el_ataque(13))

    assert [pulsacion.nota for pulsacion in salidas] == ["E4"]
    assert salidas[0].instante == pytest.approx(INSTANTE_DEL_ATAQUE)


def test_un_ataque_pasado_el_filo_se_abandona_y_el_onset_es_la_racha():
    """El otro lado del borde: un paso mas y el ataque ya no vale.

    La racha cuaja a los 17 pasos finos, que es mas de
    `VENTANA_ATAQUE_COMO_ONSET_S`: la lectura pendiente se abandona y resuelve
    el camino B con el comienzo de la racha. Es lo que impide que un ataque
    viejisimo firme una racha que no es suya, y lo que una caducidad con el
    umbral subido -a un segundo, por ejemplo- rompe: con ella el onset volveria
    a ser el del ataque.
    """
    detector = DetectorPulsaciones()
    salidas = correr_con_instantes(detector, secuencia_que_envejece_el_ataque(14))

    assert [pulsacion.nota for pulsacion in salidas] == ["E4"]
    comienzo_de_la_racha = INSTANTE_DEL_ATAQUE + 15 * PASO_FINO
    assert salidas[0].instante == pytest.approx(comienzo_de_la_racha)
    # Y se dice tambien en negativo, que es lo que la caducidad existe para
    # impedir: el onset NO es el del ataque, que ya era demasiado viejo.
    assert salidas[0].instante != pytest.approx(INSTANTE_DEL_ATAQUE)


def secuencia_donde_el_camino_a_salva_el_ataque_siguiente():
    """Los ocho cuadros donde el camino A cambia el resultado, y no otros.

    Salieron de una busqueda EXHAUSTIVA sobre secuencias de cuadros sinteticos,
    comparando el detector con camino A contra el mismo detector con el camino A
    apagado.

    **LA CIFRA DE SECUENCIAS QUE DIFIEREN NO ES UN INVARIANTE: es funcion del
    alfabeto y del largo**, y se escriben los dos para que la medicion se pueda
    rehacer. El alfabeto usado aqui son estas seis lecturas, con el paso de
    cuadro de produccion (21 ms):

        silencio a -90 dB
        silencio a -15 dB
        D4 con confianza 0,2 a -15 dB      (dudoso)
        D4 con confianza 0,9 a -15 dB
        E4 con confianza 0,9 a -15 dB
        E4 con confianza 0,9 a -40 dB

        largo 7, 6 lecturas:    279.936 secuencias ->  0 difieren
        largo 8, 6 lecturas:  1.679.616 secuencias ->  9 difieren
        largo 6, 8 lecturas:    262.144 secuencias ->  0 difieren

    Hacen falta OCHO cuadros para que el caso aparezca -el testigo los usa
    todos-, y con otro alfabeto de seis lecturas una revision independiente conto
    116 en vez de 9: trece veces mas, misma conclusion. Asi que el numero que
    importa no es el 9 sino lo que no cambia con el alfabeto: la fraccion es
    minuscula, **la diferencia esta siempre en el ONSET** -nunca en la altura ni
    en cuantas pulsaciones hay, comprobado en las tres filas de arriba- y con
    audio real del gemelo es CERO.

        0  nivel pero sin nota (el ataque de la primera pulsacion)
        1  E4 creible a -15 dB
        2  E4 creible a -40 dB   el nivel baja: entra en la referencia
        3  E4 creible a -40 dB   aqui resuelve la primera pulsacion
        4  E4 creible a -15 dB   el nivel sube 12,5 dB sobre la mediana: ATAQUE
        5  D4 creible a -15 dB   empieza la racha de la segunda nota
        6  D4 creible a -15 dB
        7  D4 creible a -15 dB   aqui resuelve la segunda pulsacion
    """
    return (
        [dudoso("E4", nivel=-15.0)]
        + [suena("E4", nivel=-15.0), suena("E4", nivel=-40.0), suena("E4", nivel=-40.0)]
        + [suena("E4", nivel=-15.0)]
        + [suena("D4", nivel=-15.0)] * 3
    )


def test_el_camino_a_reinicia_la_racha_y_eso_salva_el_onset_siguiente():
    """Para que sirve el camino A ahora que los dos caminos leen la misma racha.

    Sirve por su REINICIO, no por su lectura. Cuando el camino A sella, pone a
    cero la cuenta de la racha; el camino B no la toca. Y esa diferencia decide
    el onset de la pulsacion SIGUIENTE:

    - Con camino A: la racha de E4 queda a cero en el cuadro 3, asi que en el 4
      no hay `nota_estable`, nadie llama a `_sellar` y el ataque del cuadro 4
      SOBREVIVE. En el cuadro 7 el camino A firma el D4 con el, 0,084.
    - Sin camino A: la racha de E4 sigue viva en el cuadro 4, `_sellar` la
      descarta por nombre y el descarte BORRA el ataque (es lo que evita que
      firme la pulsacion siguiente cuando no le toca). En el cuadro 7 ya no hay
      ataque y `_onset_camino_b` cae al comienzo de la racha, 0,105.

    Son 21 ms de onset, y van en la direccion que importa: 0,084 es el ataque de
    verdad y 0,105 es cuando el detector de tono acabo de cuajar.

    **Es la unica prueba del archivo que muere si el camino A desaparece**, y por
    eso existe. Las demas no pueden: con el ataque reciente, `_onset_camino_b`
    devuelve el mismo instante que el camino A habria firmado -eso es la
    unificacion del onset, y es deliberada-, asi que en el caso normal los dos
    caminos dan exactamente el mismo resultado. Buscar el caso que los distingue
    hubo que hacerlo por fuerza bruta.
    """
    detector = DetectorPulsaciones()
    salidas = correr(detector, secuencia_donde_el_camino_a_salva_el_ataque_siguiente())

    assert [pulsacion.nota for pulsacion in salidas] == ["E4", "D4"]
    instante_del_ataque = 4 * PASO
    comienzo_de_la_racha = 5 * PASO
    assert salidas[1].instante == pytest.approx(instante_del_ataque)
    assert salidas[1].instante != pytest.approx(comienzo_de_la_racha)
