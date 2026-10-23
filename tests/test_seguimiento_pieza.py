"""El carril: seguir una pieza donde manda el reloj, no los aciertos.

Ni una espera real en todo el archivo: el reloj de la pieza se mueve a mano con
`avanzar_a` y el del analisis se pasa como argumento a `procesar`.
"""

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import Pulsacion
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from nucleo.piezas.seguimiento import (
    VENTANA_A_TIEMPO_S,
    VENTANA_ALTURA_S,
    VENTANA_RECLAMO_MINIMA_S,
    SeguidorPieza,
)


def pieza_de(midis, tempo=60):
    """Una nota por pulso: a 60 ppm, una por segundo."""
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=6, traste=i, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i, m in enumerate(midis)
    )
    return Pieza(nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas)


def suena(nota, nivel=-25.0, confianza=0.9, cents=0.0):
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=confianza, nivel_db=nivel,
        nota=nota, cents=cents, posiciones=(),
    )


def tocar(seguidor, nota, en, cents=0.0):
    """Toca una nota alrededor del instante `en` y devuelve lo que se anoto.

    El reloj se mueve a mano: ni una espera real en toda la suite.

    `en` es un instante del RELOJ DE LA PIEZA, y el reloj de la pieza se coloca
    ahi antes del primer cuadro, igual que hace el servidor mientras no llega
    señal. Sin esa colocacion, el seguidor fijaria la correspondencia entre los
    dos relojes en el primer cuadro de audio y la pieza empezaria en ese cuadro,
    asi que la nota caeria siempre 0.1 s dentro de la pieza y `en` no significaria
    nada (todas las pruebas de desfase medirian lo mismo). Es una linea añadida al
    ayudante del brief; el resto es literal.
    """
    instante = en - 0.1
    seguidor.avanzar_a(instante)
    while instante < en:
        seguidor.procesar(
            ResultadoAnalisis(
                estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
                nota=None, cents=None, posiciones=(),
            ),
            instante,
        )
        instante += 0.021
    for _ in range(12):
        seguidor.procesar(suena(nota, cents=cents), instante)
        instante += 0.021
    return seguidor.estado.tocadas[-1]


def test_la_nota_en_curso_la_decide_el_reloj():
    seguidor = SeguidorPieza(pieza_de([40, 45, 50]))
    assert seguidor.avanzar_a(0.1).indice_actual == 0
    assert seguidor.avanzar_a(1.2).indice_actual == 1
    assert seguidor.avanzar_a(2.5).indice_actual == 2


def test_la_pieza_avanza_aunque_falles():
    """Lo contrario que un ejercicio por turnos: la musica no espera."""
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    assert seguidor.avanzar_a(1.5).indice_actual == 1
    assert seguidor.estado.tocadas == ()


def test_al_pasar_del_final_la_pieza_esta_completada():
    seguidor = SeguidorPieza(pieza_de([40]))
    assert seguidor.avanzar_a(0.5).completado is False
    assert seguidor.avanzar_a(1.5).completado is True


def test_una_nota_en_su_instante_va_a_tiempo():
    """Se toca "A2" porque el MIDI 45 -la nota que vive en el segundo 1.0- ES "A2".

    El brief tocaba "E2" en todas estas pruebas de tiempo. Miden bien el tiempo
    igual, porque la clasificacion no depende de la altura, pero estaban tocando
    la nota equivocada en el hueco de la buena y decian menos de lo que su nombre
    promete. Con la nota correcta, cada una comprueba tambien que acertar de
    altura y medir el desfase son cosas independientes.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "A2", en=1.0)
    assert tocada.indice == 1
    assert tocada.acertada is True
    assert tocada.clasificacion == "a_tiempo"
    assert tocada.desfase_s == pytest.approx(0.0, abs=0.03)


def test_una_nota_adelantada_se_marca_pronto_con_su_desfase():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "A2", en=1.0 - 0.3)
    assert tocada.acertada is True
    assert tocada.clasificacion == "pronto"
    assert tocada.desfase_s < -VENTANA_A_TIEMPO_S


def test_una_nota_atrasada_se_marca_tarde():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "A2", en=1.0 + 0.3)
    assert tocada.acertada is True
    assert tocada.clasificacion == "tarde"
    assert tocada.desfase_s > VENTANA_A_TIEMPO_S


def test_fuera_de_ventana_pero_correcta_sigue_siendo_acertada():
    """El ritmo informa, no descalifica: la misma regla que la afinacion.

    El brief tocaba "E2" en el hueco del MIDI 45, asi que la prueba titulada
    "correcta sigue siendo acertada" demostraba lo contrario (`acertada=False`) y
    el principio se quedaba sin cubrir en toda la suite. Se toca la nota que de
    verdad toca, 400 ms tarde: fuera de ventana y acertada a la vez.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "A2", en=1.0 + 0.4)
    assert tocada.midi == 45
    assert tocada.clasificacion == "tarde"
    assert tocada.acertada is True
    assert tocada.cents is not None


def test_los_cents_de_la_pulsacion_llegan_al_estado():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "A2", en=1.0, cents=-12.0)
    assert tocada.cents == pytest.approx(-12.0)


def test_una_nota_equivocada_no_cuenta_como_la_esperada():
    """La nota tocada (C3) no es ninguna de las dos de la pieza.

    El brief tocaba "A2" en el instante 1.0, pero en `pieza_de([40, 45])` la nota
    que vive en 1.0 es justo el MIDI 45, que es "A2": era la nota correcta, no una
    equivocada, y con la adjudicacion a la nota mas cercana sin tocar -la que el
    propio brief pide- `acertada` no podia salir falso. Se cambia la nota tocada,
    que es lo que la prueba quiere decir.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "C3", en=1.0)
    assert tocada.midi != 40
    assert tocada.clasificacion in ("a_tiempo", "pronto", "tarde")
    assert tocada.acertada is False


def test_el_estado_publica_lo_mismo_que_la_interfaz_va_a_pintar():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    d = seguidor.avanzar_a(0.5).a_dict()
    assert set(d) == {"instante_s", "indice_actual", "total", "completado", "tocadas"}


def test_el_desfase_no_mide_la_antiguedad_del_proceso():
    """Los dos relojes son distintos y el desfase es del alumno, no del proceso.

    El reloj del analisis es `time.monotonic()`: llega con dias de encendido
    encima. Si el seguidor lo confundiera con el de la pieza, el desfase seria esa
    cifra entera en vez de los milisegundos que el alumno se desvio.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    reloj_analisis = 987654.0
    seguidor.avanzar_a(0.9)
    instante = reloj_analisis
    while instante < reloj_analisis + 0.1:
        seguidor.procesar(
            ResultadoAnalisis(
                estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
                nota=None, cents=None, posiciones=(),
            ),
            instante,
        )
        instante += 0.021
    for _ in range(12):
        seguidor.procesar(suena("A2"), instante)
        instante += 0.021
    tocada = seguidor.estado.tocadas[-1]
    assert tocada.acertada is True
    assert tocada.clasificacion == "a_tiempo"
    assert tocada.desfase_s == pytest.approx(0.0, abs=0.03)


def test_una_pulsacion_sin_instante_no_inventa_desfase():
    """`Pulsacion.instante` es `float | None`; el caso raro no puede reventar."""

    class DetectorFingido:
        """Suelta una pulsacion sin instante en el primer cuadro y nada mas."""

        def __init__(self):
            self.cuadros = 0

        def reiniciar(self):
            self.cuadros = 0

        def procesar(self, resultado, instante):
            self.cuadros += 1
            if self.cuadros == 1:
                return Pulsacion(nota="E2", cents=3.0, instante=None)
            return None

    seguidor = SeguidorPieza(pieza_de([40, 45]), detector=DetectorFingido())
    seguidor.avanzar_a(0.0)
    tocada = seguidor.procesar(suena("E2"), 0.0).tocadas[-1]
    assert tocada.midi == 40
    assert tocada.acertada is True
    assert tocada.desfase_s is None
    assert tocada.clasificacion is None


def test_dos_pulsaciones_no_se_adjudican_a_la_misma_nota():
    """Cada nota se cobra una vez: la segunda pulsacion busca otra.

    Las dos van a su nota, no a la misma. La version anterior de esta prueba
    mandaba la segunda pulsacion a la nota 0 con un desfase de 1,6 s y lo dejaba
    grabado como esperado: eso era el defecto de la ventana de reclamo ilimitada,
    no el comportamiento que se queria.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45, 50]))
    primera = tocar(seguidor, "A2", en=1.0)
    segunda = tocar(seguidor, "D3", en=2.0)
    assert (primera.indice, primera.acertada) == (1, True)
    assert (segunda.indice, segunda.acertada) == (2, True)
    assert len(seguidor.estado.tocadas) == 2


def test_una_pieza_sin_notas_esta_completada_y_no_anota_nada():
    seguidor = SeguidorPieza(pieza_de([]))
    estado = seguidor.avanzar_a(0.0)
    assert estado.total == 0
    assert estado.completado is True
    assert estado.tocadas == ()



def test_una_pulsacion_dentro_de_la_ventana_de_reclamo_se_adjudica():
    """El borde de dentro: la nota dura 1 pulso (1,0 s a 60 ppm) mas 80 ms."""
    seguidor = SeguidorPieza(pieza_de([40]))
    tocada = tocar(seguidor, "E2", en=1.0)
    assert tocada.indice == 0
    assert tocada.clasificacion == "tarde"
    assert tocada.desfase_s == pytest.approx(1.005, abs=0.02)


def test_una_pulsacion_fuera_de_la_ventana_de_reclamo_no_se_adjudica():
    """El borde de fuera: 1,2 s pasa de 1,08 s y no hay nota que reclamar.

    No se anota ni como acertada ni como fallo: no hay ninguna nota de la que esa
    pulsacion pueda ser un intento.
    """
    seguidor = SeguidorPieza(pieza_de([40]))
    seguidor.avanzar_a(1.1)
    instante = 1.1
    while instante < 1.2:
        seguidor.procesar(
            ResultadoAnalisis(
                estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
                nota=None, cents=None, posiciones=(),
            ),
            instante,
        )
        instante += 0.021
    for _ in range(12):
        seguidor.procesar(suena("E2"), instante)
        instante += 0.021
    assert seguidor.estado.tocadas == ()


def test_una_pulsacion_treinta_segundos_despues_del_final_deja_el_informe_limpio():
    """Una nota que nadie toco no puede entrar en el informe como tocada.

    Sin ventana de reclamo, esta pulsacion se adjudicaba a la nota 0 con
    `desfase_s = 30.005`, `"tarde"` y `acertada True`, y envenenaba cualquier
    porcentaje o promedio calculado encima.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    seguidor.avanzar_a(31.9)
    instante = 31.9
    while instante < 32.0:
        seguidor.procesar(
            ResultadoAnalisis(
                estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
                nota=None, cents=None, posiciones=(),
            ),
            instante,
        )
        instante += 0.021
    for _ in range(12):
        seguidor.procesar(suena("E2"), instante)
        instante += 0.021
    estado = seguidor.estado
    assert estado.completado is True
    assert estado.tocadas == ()


def test_una_pulsacion_en_vuelo_no_sobrevive_a_un_salto_del_reloj():
    """El detector resuelve tarde; si el reloj salta entremedias, se descarta.

    Sin esta guarda, la pulsacion tocada en el segundo ~1,0 se traducia con el
    origen nuevo y se adjudicaba a la nota del segundo 3,0 como "a_tiempo": una
    nota regalada por una pausa. La Task 5 va a usar `avanzar_a` justo para esas
    pausas por falta de señal.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45, 50, 55]))
    seguidor.avanzar_a(0.9)
    instante = 0.9
    while instante < 1.0:
        seguidor.procesar(
            ResultadoAnalisis(
                estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
                nota=None, cents=None, posiciones=(),
            ),
            instante,
        )
        instante += 0.021
    # Dos cuadros con sonido: el ataque ya ocurrio, pero ningun camino del
    # detector ha resuelto todavia. La pulsacion esta en vuelo.
    for _ in range(2):
        seguidor.procesar(suena("A2"), instante)
        instante += 0.021
    assert seguidor.estado.tocadas == ()
    seguidor.avanzar_a(3.0)
    for _ in range(12):
        seguidor.procesar(suena("A2"), instante)
        instante += 0.021
    estado = seguidor.estado
    assert estado.indice_actual == 3
    assert estado.tocadas == ()


def acorde_de(midis):
    """Una pieza con todas las notas en el mismo instante: un acorde."""
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=6 - i, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
        for i, m in enumerate(midis)
    )
    return Pieza(nombre="acorde", perfil="guitarra_estandar", tempo=60, compas=(4, 4), notas=notas)


def test_de_un_acorde_solo_se_cobra_una_nota():
    """La limitacion declarada, escrita como prueba: el detector es monofonico.

    De dos notas en el mismo instante, una pulsacion cobra una y la otra se queda
    sin tocar por muy bien que se toque. Y `indice_actual` señala a la ultima del
    acorde, que es arbitrario entre iguales.
    """
    seguidor = SeguidorPieza(acorde_de([40, 47]))
    tocada = tocar(seguidor, "E2", en=0.0)
    estado = seguidor.estado
    assert estado.indice_actual == 1
    assert len(estado.tocadas) == 1
    assert (tocada.indice, tocada.acertada) == (0, True)


def pieza_rapida(midis, tempo=200, duracion_pulsos=0.25):
    """Semicorcheas a 200 ppm: cada nota dura 75 ms y la siguiente llega a 75 ms.

    Es el tempo donde derivar la ventana de reclamo de la duracion escrita se
    queda corto: 75 + 80 = 155 ms, mas estrecho que el error de un principiante.
    """
    notas = tuple(
        NotaEnPieza(
            midi=m,
            cuerda=6,
            traste=0,
            inicio_pulsos=i * duracion_pulsos,
            duracion_pulsos=duracion_pulsos,
        )
        for i, m in enumerate(midis)
    )
    return Pieza(
        nombre="rapida", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas
    )


def test_con_figuras_cortas_la_ventana_no_baja_del_piso():
    """200 ms tarde sobre una semicorchea a 200 ppm: tarde, no inexistente.

    Sin el piso, la ventana de esa nota seria de 155 ms y esta pulsacion no se
    adjudicaba a nadie: se descartaba en silencio, justo el caso que el brief
    quiere que cuente como "tarde".
    """
    seguidor = SeguidorPieza(pieza_rapida([40]))
    tocada = tocar(seguidor, "E2", en=0.2)
    assert tocada.indice == 0
    assert tocada.acertada is True
    assert tocada.clasificacion == "tarde"
    assert tocada.desfase_s == pytest.approx(0.205, abs=0.02)
    assert tocada.desfase_s < VENTANA_RECLAMO_MINIMA_S


def test_en_un_pasaje_denso_manda_la_altura_y_no_la_vecina():
    """Notas a 75 ms: el tiempo no distingue, el nombre de la nota si.

    La nota 0 se toca 200 ms tarde. Por cercania sola, la vecina mas proxima es la
    3 (a 20 ms del onset) y la pulsacion salia adjudicada a ella, "a_tiempo" y
    equivocada: un fantasma de nota mal tocada en lugar de la nota real tocada
    tarde.
    """
    seguidor = SeguidorPieza(pieza_rapida([40, 45, 50, 55, 59]))
    tocada = tocar(seguidor, "E2", en=0.2)
    assert tocada.indice == 0
    assert tocada.acertada is True
    assert tocada.clasificacion == "tarde"


def test_en_un_pasaje_denso_manda_la_altura_tambien_si_el_alumno_se_adelanta():
    """Adelantarse es tan normal como retrasarse, y la altura vale igual.

    La nota 3 (G3) se toca 200 ms PRONTO. Por cercania sola cae en la vecina, que
    saldria "a_tiempo" y equivocada mientras la nota 3 se queda sin cobrar: el
    mismo fantasma que la preferencia por altura vino a matar, en el otro sentido.
    Un tope por direccion -la altura solo hacia atras- lo reintroducia; el tope de
    distancia vale por los dos lados.
    """
    seguidor = SeguidorPieza(pieza_rapida([40, 45, 50, 55, 59]))
    tocada = tocar(seguidor, "G3", en=0.225 - 0.2)
    assert tocada.indice == 3
    assert tocada.acertada is True
    assert tocada.clasificacion == "pronto"


def test_en_un_pasaje_denso_una_altura_que_no_esta_sigue_yendo_por_cercania():
    """Los fallos de altura no cambian: van a la nota mas cercana y no aciertan.

    "C4" (MIDI 60) no esta escrito en ningun sitio de la pieza, asi que no hay
    coincidencia de altura a la que irse y manda la cercania, como antes.
    """
    seguidor = SeguidorPieza(pieza_rapida([40, 45, 50, 55, 59]))
    tocada = tocar(seguidor, "C4", en=0.2)
    assert tocada.midi == 60
    assert tocada.indice == 3
    assert tocada.acertada is False
    assert tocada.clasificacion == "a_tiempo"


# La escala de C mayor "ambas" como la devuelve `generar_escala`: C3 D3 E3 F3 G3
# F3 E3 D3 C3, negras, al tempo por defecto de 80 ppm (0,75 s por nota).
ESCALA_C_MAYOR_AMBAS = (48, 50, 52, 53, 55, 53, 52, 50, 48)
NOMBRES_ESCALA = ("C3", "D3", "E3", "F3", "G3", "F3", "E3", "D3", "C3")
PULSO_A_80_S = 60.0 / 80.0


def test_la_altura_no_cobra_una_nota_que_el_alumno_no_ha_alcanzado():
    """Un traste bajo marca la nota que se estaba tocando, no la de mas adelante.

    El alumno acierta las cinco primeras y en la sexta (F3) pone el dedo un
    traste bajo, sonando E3. Esa altura existe mas adelante en la pieza -la nota
    6, a 750 ms-, y la preferencia por altura se la adjudicaba a ella: salia
    ACERTADA una nota que el alumno todavia no habia alcanzado, la que de verdad
    fallo se quedaba sin marca, y al tocar la 6 bien la unica libre cerca era la
    5, de otra altura, asi que el acierto salia fallado. Lo correcto como error y
    el error como acierto.
    """
    seguidor = SeguidorPieza(pieza_de(ESCALA_C_MAYOR_AMBAS, tempo=80))
    for indice in range(5):
        tocar(seguidor, NOMBRES_ESCALA[indice], en=indice * PULSO_A_80_S)

    fallo = tocar(seguidor, "E3", en=5 * PULSO_A_80_S)
    assert (fallo.indice, fallo.acertada) == (5, False)
    assert fallo.clasificacion == "a_tiempo"

    siguiente = tocar(seguidor, "E3", en=6 * PULSO_A_80_S)
    assert (siguiente.indice, siguiente.acertada) == (6, True)
    assert [t.indice for t in seguidor.estado.tocadas] == [0, 1, 2, 3, 4, 5, 6]


def test_el_espejo_de_lo_mismo_hacia_atras():
    """Una nota que el alumno NUNCA toco no puede salir acertada hacia atras.

    Misma escala, mismo tempo, misma magnitud, el otro sentido: el alumno se salta
    la nota 0 y en la 1 (D3) deja el dedo un traste bajo, sonando C3. Esa altura
    existe en la nota 0, a 755 ms POR DETRAS, y se le adjudicaba a ella: salia
    `acertada=True` y "tarde" una nota que nunca se toco, la nota 1 -la que de
    verdad fallo- se quedaba sin marca, y al llegar a la 2 y tocarla bien la unica
    libre cerca era la 1, de otra altura, asi que el acierto salia fallado.

    Es el agujero que una guarda por direccion no tapa, porque la nota 1 esta a
    5 ms del dedo: la nota que cobraba estaba DETRAS, no delante. Lo que lo cierra
    es el tope de distancia de `VENTANA_ALTURA_S`.
    """
    seguidor = SeguidorPieza(pieza_de(ESCALA_C_MAYOR_AMBAS, tempo=80))

    fallo = tocar(seguidor, "C3", en=1 * PULSO_A_80_S)
    assert (fallo.indice, fallo.acertada) == (1, False)
    assert fallo.clasificacion == "a_tiempo"

    siguiente = tocar(seguidor, "E3", en=2 * PULSO_A_80_S)
    assert (siguiente.indice, siguiente.acertada) == (2, True)


def test_una_altura_que_coincide_lejos_no_es_la_nota_que_se_intentaba():
    """El borde de `VENTANA_ALTURA_S`: a 0,4 s, la misma altura ya es otra nota.

    A 150 ppm la negra son 0,4 s, asi que la nota 3 (D3) sigue siendo RECLAMABLE
    desde el instante de la nota 2 -el piso de reclamo son 0,5 s-, pero esta fuera
    de la vecindad de la altura. La pieza es C3 G3 E3 D3 E3: tocar D3 en el
    instante de la nota 2 es un fallo de altura sobre la nota 2, no un acierto
    adelantado de la 3.
    """
    seguidor = SeguidorPieza(pieza_de((48, 55, 52, 50, 52), tempo=150))
    pulso_s = 60.0 / 150.0
    tocada = tocar(seguidor, "D3", en=2 * pulso_s)
    assert (tocada.indice, tocada.acertada) == (2, False)
    assert pulso_s > VENTANA_ALTURA_S  # reclamable, pero no por altura


def pieza_con_redonda_a_40():
    """Nota 0: E3 negra en t=0. Nota 1: A2 REDONDA en t=1,5 (40 ppm, pulso 1,5 s).

    La redonda dura 4 pulsos, 6 s, asi que su ventana de reclamo hacia atras es
    de 6,08 s. Aplicada tambien hacia delante, autorizaba reclamarla 6,08 s ANTES
    de su instante.
    """
    notas = (
        NotaEnPieza(midi=52, cuerda=4, traste=2, inicio_pulsos=0.0, duracion_pulsos=1.0),
        NotaEnPieza(midi=45, cuerda=5, traste=0, inicio_pulsos=1.0, duracion_pulsos=4.0),
    )
    return Pieza(
        nombre="redonda", perfil="guitarra_estandar", tempo=40, compas=(4, 4), notas=notas
    )


def test_una_figura_larga_no_se_puede_reclamar_de_lejos_hacia_atras():
    """La duracion acota el lado TARDE; el lado pronto lo acota el piso.

    El alumno toca A2 en t=0,5: la nota equivocada, medio segundo tarde sobre la
    nota 0, que sigue sonando y es de quien es el intento. Con la ventana
    simetrica eso se adjudicaba a la nota 1 -la redonda, un segundo en el futuro-
    con `acertada=True` y "pronto": un acierto fabricado antes de que la nota
    exista, y la nota 0 sin marca.

    Medio segundo, y no cero, para que lo que se mide sea la ventana y no la
    cercania: a 0,5 s de la nota 0 no hay ninguna nota dentro de la ventana de "a
    tiempo", asi que la preferencia por altura puede mirar donde quiera y lo
    unico que la detiene es el lado pronto de la ventana.
    """
    seguidor = SeguidorPieza(pieza_con_redonda_a_40())
    tocada = tocar(seguidor, "A2", en=0.5)
    assert (tocada.indice, tocada.acertada) == (0, False)


def test_una_figura_larga_si_se_puede_reclamar_tarde():
    """El otro lado sigue como estaba: la nota todavia suena, sigue siendo suya.

    A2 tocada 2 s despues de su instante esta muy fuera del piso de 0,5 s y se
    adjudica igual, porque la redonda dura 6 s.
    """
    seguidor = SeguidorPieza(pieza_con_redonda_a_40())
    tocada = tocar(seguidor, "A2", en=1.5 + 2.0)
    assert (tocada.indice, tocada.acertada) == (1, True)
    assert tocada.clasificacion == "tarde"


def test_en_el_instante_exacto_de_una_nota_el_indice_ya_es_suyo():
    """El borde de `_indice_en_curso`: la nota en curso es la que YA empezo.

    Las dos conductas del borde estan prometidas en los docstrings de
    `EstadoCarril` y de `_indice_en_curso`, las lee la interfaz para el cursor y
    el contador, y no las fijaba ninguna prueba: cambiar el `side="right"` de la
    busqueda por `side="left"` dejaba la suite entera en verde mientras el
    cabezal se quedaba una nota por detras en el instante del ataque, que es
    justo el instante que importa.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45, 50, 55], tempo=80))  # 0, 0,75, 1,5, 2,25
    assert seguidor.avanzar_a(0.0).indice_actual == 0
    assert seguidor.avanzar_a(0.74).indice_actual == 0
    assert seguidor.avanzar_a(0.75).indice_actual == 1
    assert seguidor.avanzar_a(0.76).indice_actual == 1
    assert seguidor.avanzar_a(1.5).indice_actual == 2


def test_un_acorde_en_su_propio_instante_senala_a_su_ultima_nota():
    """La arbitrariedad declarada, medida DONDE se nota: en el instante del acorde.

    Con dos notas en el mismo inicio, `indice_actual` señala a la ultima de
    ellas. Es arbitrario entre iguales -el seguidor no sabe seguir acordes-, pero
    es lo que lee la interfaz, y medido un cuadro mas tarde la prueba no
    distinguia esa eleccion de la contraria.
    """
    notas = (
        NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0),
        NotaEnPieza(midi=47, cuerda=5, traste=2, inicio_pulsos=1.0, duracion_pulsos=1.0),
        NotaEnPieza(midi=52, cuerda=4, traste=2, inicio_pulsos=1.0, duracion_pulsos=1.0),
        NotaEnPieza(midi=55, cuerda=3, traste=0, inicio_pulsos=2.0, duracion_pulsos=1.0),
    )
    pieza = Pieza(
        nombre="con acorde", perfil="guitarra_estandar", tempo=80, compas=(4, 4), notas=notas
    )
    seguidor = SeguidorPieza(pieza)
    assert seguidor.avanzar_a(0.75).indice_actual == 2
    assert seguidor.avanzar_a(0.76).indice_actual == 2


def test_el_veredicto_de_la_afinacion_lo_publica_el_nucleo():
    """`afinada` con la misma regla que el resto del programa, no un umbral copiado.

    La interfaz se copiaba el umbral de 5 cents de `nucleo.musica.esta_afinada`
    para elegir el color de la desviacion. El veredicto lo decide el nucleo y la
    interfaz lo consume, como ya hace con `acertada` y `clasificacion`.
    """
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    assert tocar(seguidor, "A2", en=1.0, cents=-4.9).afinada is True

    seguidor.reiniciar()
    assert tocar(seguidor, "A2", en=1.0, cents=5.0).afinada is False


def test_una_desviacion_que_no_se_supo_no_es_ni_afinada_ni_desafinada():
    """`cents` None es "no se supo": `afinada` tambien es None, nunca True."""

    class DetectorSinCents:
        def __init__(self):
            self.cuadros = 0

        def reiniciar(self):
            self.cuadros = 0

        def procesar(self, resultado, instante):
            self.cuadros += 1
            if self.cuadros == 1:
                return Pulsacion(nota="E2", cents=None, instante=instante)
            return None

    seguidor = SeguidorPieza(pieza_de([40, 45]), detector=DetectorSinCents())
    seguidor.avanzar_a(0.0)
    tocada = seguidor.procesar(suena("E2"), 0.0).tocadas[-1]
    assert tocada.cents is None
    assert tocada.afinada is None
    assert tocada.a_dict()["afinada"] is None


def test_el_factor_estira_los_instantes_de_la_pieza():
    # Al 50 %, una pieza de tres notas a 60 ppm dura el doble: la nota 2 ya no
    # empieza en el segundo 1 sino en el 2.
    seguidor = SeguidorPieza(pieza_de([40, 45, 50]), factor_tempo=0.5)
    seguidor.avanzar_a(1.5)
    assert seguidor.estado.indice_actual == 0
    seguidor.avanzar_a(2.5)
    assert seguidor.estado.indice_actual == 1


def test_el_factor_estira_las_tres_ventanas():
    seguidor = SeguidorPieza(pieza_de([40]), factor_tempo=0.5)
    assert seguidor.ventana_a_tiempo_s == pytest.approx(VENTANA_A_TIEMPO_S * 2)
    assert seguidor.ventana_reclamo_minima_s == pytest.approx(VENTANA_RECLAMO_MINIMA_S * 2)
    assert seguidor.ventana_altura_s == pytest.approx(VENTANA_ALTURA_S * 2)


def test_al_cincuenta_por_ciento_un_desfase_de_ciento_veinte_milisegundos_es_a_tiempo():
    # La decision del usuario: la ventana escala con el tempo, asi que lo que se
    # juzga es la colocacion DENTRO del compas. A tempo escrito, 120 ms es tarde;
    # a la mitad, los +-80 ms se vuelven +-160 y el mismo retraso es a tiempo.
    rapido = SeguidorPieza(pieza_de([40]))
    assert tocar(rapido, "E2", en=0.120).clasificacion == "tarde"
    lento = SeguidorPieza(pieza_de([40]), factor_tempo=0.5)
    assert tocar(lento, "E2", en=0.120).clasificacion == "a_tiempo"


def test_un_factor_que_no_es_positivo_se_rechaza():
    with pytest.raises(ValueError, match="factor"):
        SeguidorPieza(pieza_de([40]), factor_tempo=0.0)


def test_olvidar_un_tramo_deja_volver_a_cobrar_sus_notas():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocar(seguidor, "E2", en=0.0)
    assert len(seguidor.estado.tocadas) == 1
    seguidor.olvidar_tramo(0.0, 0.5)
    assert seguidor.estado.tocadas == ()
    # Y se puede volver a cobrar: es lo que hace falta para repetir el bucle.
    seguidor.avanzar_a(0.0)
    tocar(seguidor, "E2", en=0.0)
    assert len(seguidor.estado.tocadas) == 1


def test_olvidar_un_tramo_no_toca_lo_de_fuera():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocar(seguidor, "E2", en=0.0)
    tocar(seguidor, "A2", en=1.0)
    seguidor.olvidar_tramo(0.9, 1.5)
    assert [t.indice for t in seguidor.estado.tocadas] == [0]


def test_olvidar_un_tramo_vacio_no_hace_nada():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocar(seguidor, "E2", en=0.0)
    seguidor.olvidar_tramo(5.0, 9.0)
    assert len(seguidor.estado.tocadas) == 1


def test_al_cincuenta_por_ciento_la_pieza_dura_el_doble():
    normal = SeguidorPieza(pieza_de([40, 45, 50]))
    lento = SeguidorPieza(pieza_de([40, 45, 50]), factor_tempo=0.5)
    assert lento.duracion_s == pytest.approx(2 * normal.duracion_s)


def test_olvidar_un_tramo_no_incluye_su_extremo_final():
    # El tramo es [desde, hasta): la nota que empieza justo en `hasta` es la
    # primera del tramo siguiente y no se olvida.
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocar(seguidor, "E2", en=0.0)
    tocar(seguidor, "A2", en=1.0)
    seguidor.olvidar_tramo(0.0, 1.0)
    assert [t.indice for t in seguidor.estado.tocadas] == [1]
