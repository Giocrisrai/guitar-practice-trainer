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

        # Parte de la frontera con el seguidor desde la etapa 2b: el ataque

        # cuyo nombre de nota no cuajo. Este doble no finge rasgueos.

        ataque_sin_altura = None


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

        # Parte de la frontera con el seguidor desde la etapa 2b: el ataque

        # cuyo nombre de nota no cuajo. Este doble no finge rasgueos.

        ataque_sin_altura = None


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


@pytest.mark.parametrize("factor", [float("nan"), -1.0])
def test_un_factor_nan_o_negativo_se_rechaza(factor):
    with pytest.raises(ValueError, match="factor"):
        SeguidorPieza(pieza_de([40]), factor_tempo=factor)


def test_el_factor_es_de_solo_lectura():
    seguidor = SeguidorPieza(pieza_de([40]), factor_tempo=0.5)
    assert seguidor.factor_tempo == 0.5
    with pytest.raises(AttributeError):
        seguidor.factor_tempo = 0.7


# -- El salto CONTINUO y la cola de la vuelta (Task 7) ----------------------


class DetectorDeUnSoloOnset:
    """Suelta UNA pulsacion, en el cuadro que se le diga y con el onset que se le diga.

    El onset se fija a mano a proposito: lo que estas pruebas miden es que el
    seguidor decida bien a QUE tramo pertenece un onset, y eso se decide
    comparandolo con la frontera del salto. Con el detector de verdad, el onset
    saldria de la energia del audio y la prueba mediria dos cosas a la vez.
    """

    def __init__(self, nota, onset, en_el_cuadro):
        self.nota = nota
        self.onset = onset
        self.en_el_cuadro = en_el_cuadro
        self.cuadros = 0

    # Parte de la frontera con el seguidor desde la etapa 2b: el ataque

    # cuyo nombre de nota no cuajo. Este doble no finge rasgueos.

    ataque_sin_altura = None


    def reiniciar(self):
        self.cuadros = 0

    def procesar(self, resultado, instante):
        self.cuadros += 1
        if self.cuadros == self.en_el_cuadro:
            return Pulsacion(nota=self.nota, cents=0.0, instante=self.onset)
        return None


def _hasta_la_vuelta(seguidor, fin=4.0, desde=2.9, paso=0.021):
    """Da una vuelta de bucle sobre el tramo [0, `fin`) y devuelve el cuadro siguiente.

    Imita a `SesionDeEstudio._dar_la_vuelta` con audio, porque el reparto de la
    frontera solo tiene sentido contra esa vuelta: cuadros hasta que el reloj
    CRUZA el final, y entonces `olvidar_tramo` mas un salto continuo al `exceso`
    con que el reloj se paso, con la frontera -y la correspondencia- en el
    instante en que el reloj paso por el final, que es `exceso` segundos antes del
    cuadro que lo vio.

    Imitarlo entero no es ceremonia: es lo que hace que la correspondencia mande
    el instante 4,0 del reloj del analisis al 0,0 de la pieza, o sea que el reloj
    sea CONTINUO en la frontera, y los numeros de estas pruebas sean redondos
    porque lo son y no porque se hayan redondeado.

    Devuelve el instante del cuadro SIGUIENTE al que dio la vuelta, que es donde
    estas pruebas meten la pulsacion que el detector firma tarde.
    """
    silencio = suena("E2", nivel=-90.0, confianza=0.0)
    seguidor.avanzar_a(desde)
    instante = desde
    while True:
        estado = seguidor.procesar(silencio, instante)
        if estado.instante_s >= fin:
            break
        instante += paso
    exceso = estado.instante_s - fin
    seguidor.olvidar_tramo(0.0, fin)
    seguidor.avanzar_a(
        exceso,
        frontera_del_salto_s=instante - exceso,
        instante_analisis_s=instante,
    )
    return instante + paso


def test_un_onset_de_antes_de_la_frontera_se_retiene_en_la_cola():
    """La nota atacada antes de la vuelta es de la vuelta que CIERRA.

    **Es la semantica de la Task 7 medida en el sitio donde se decide.** El onset
    esta en 3,9 -el reloj de la pieza marcaba 3,9 cuando se ataco, con la nota 3
    escrita en 3,0- y el detector lo firma en un cuadro POSTERIOR a la vuelta, que
    es lo que pasa de verdad: el detector tarda hasta 250 ms en firmar un ataque.

    Lo que se afirma es que no se descarta (eso era el defecto), que NO sale en
    `estado.tocadas` -el carril pinta el tramo que corre, y esa nota no es de este
    tramo- y que el desfase se mide con el reloj de ANTES del salto: +0,9 s sobre
    la nota 3, «tarde». Medido con la correspondencia nueva saldria −3,05 s y la
    nota seria otra.
    """
    detector = DetectorDeUnSoloOnset("D3", onset=3.9, en_el_cuadro=1)
    seguidor = SeguidorPieza(pieza_de([40, 45, 47, 50]), detector=detector)
    instante = _hasta_la_vuelta(seguidor)
    # El contador del detector fingido se pone a cero DESPUES de la vuelta: asi
    # la pulsacion sale en el primer cuadro de la vuelta nueva, que es cuando el
    # detector de verdad firma el ataque del final del tramo anterior.
    detector.cuadros = 0

    estado = seguidor.procesar(suena("D3"), instante)

    assert estado.tocadas == (), "la nota de la vuelta anterior no se pinta en esta"
    cola = seguidor.recoger_la_cola()
    assert len(cola) == 1
    assert cola[0].indice == 3
    assert cola[0].acertada is True
    assert cola[0].desfase_s == pytest.approx(0.9)
    assert cola[0].clasificacion == "tarde"
    # Se entrega UNA vez: quien la cobro no la vuelve a cobrar.
    assert seguidor.recoger_la_cola() == ()


def test_un_onset_de_despues_de_la_frontera_es_de_la_vuelta_que_abre():
    """Y la de despues es de la vuelta que ABRE. Sin este lado no hay frontera.

    Mismo montaje y resultado contrario: el onset esta en 4,02, o sea 20 ms
    DESPUES del instante en que el reloj paso por el final del tramo, asi que se
    ataco ya en la vuelta nueva. Se adjudica con la correspondencia del salto -el
    reloj de la pieza marca 0,02 en ese onset-, va a la nota 0 «a tiempo» y sale
    en `estado.tocadas`, que es donde el carril la pinta.

    **El 4,02 esta elegido y no es cualquier numero posterior a la frontera.** El
    cuadro que dio la vuelta cae en 4,013 y el siguiente en 4,034, asi que 4,02
    esta en la ventana que ANTES de la Task 7 se descartaba entera: `_adjudicar`
    tiraba todo onset anterior al primer cuadro posterior al salto, y ese cuadro
    era el 4,034. Esa era la perdida que el gemelo media una vez cada tres
    vueltas: la primera nota de la vuelta.

    Con un onset posterior a 4,034 esta prueba no mediria nada -seria el camino de
    siempre, y pasaria igual sin la frontera-, y asi estaba escrita: lo dijo una
    revision y tenia razon.
    """
    detector = DetectorDeUnSoloOnset("E2", onset=4.02, en_el_cuadro=1)
    seguidor = SeguidorPieza(pieza_de([40, 45, 47, 50]), detector=detector)
    instante = _hasta_la_vuelta(seguidor)
    assert 4.0 < 4.02 < instante, (
        "el onset tiene que caer entre la frontera y el primer cuadro posterior "
        f"al salto ({instante}), que es la ventana que antes se descartaba"
    )
    detector.cuadros = 0

    estado = seguidor.procesar(suena("E2"), instante)

    assert [t.indice for t in estado.tocadas] == [0]
    assert estado.tocadas[0].acertada is True
    assert estado.tocadas[0].desfase_s == pytest.approx(0.02)
    assert estado.tocadas[0].clasificacion == "a_tiempo"
    assert seguidor.recoger_la_cola() == ()


def test_sin_frontera_el_salto_sigue_descartando_lo_que_estaba_en_vuelo():
    """El contrato de siempre, intacto: un salto ORDINARIO tira lo que venia.

    Es la mitad que no cambio, y hace falta afirmarla: `avanzar_a` sin frontera -o
    sea colocar, congelar, saltar de compas, la pausa, la cuenta atras- tiene que
    seguir descartando un onset anterior al salto, porque ahi el reloj SI se fue a
    otra parte y traducir ese onset lo colocaria donde no paso nada.

    Mismo onset de 3,9 que la prueba de la cola: sin frontera no se anota en
    ninguna parte, ni en `tocadas` ni en la cola.
    """
    detector = DetectorDeUnSoloOnset("D3", onset=3.9, en_el_cuadro=1)
    seguidor = SeguidorPieza(pieza_de([40, 45, 47, 50]), detector=detector)
    seguidor.avanzar_a(2.9)
    instante = 2.9
    while instante < 4.0:
        seguidor.procesar(suena("E2", nivel=-90.0, confianza=0.0), instante)
        instante += 0.021
    seguidor.olvidar_tramo(0.0, 4.0)
    seguidor.avanzar_a(0.0)
    detector.cuadros = 0

    estado = seguidor.procesar(suena("D3"), instante)

    assert estado.tocadas == ()
    assert seguidor.recoger_la_cola() == ()


def test_un_salto_ordinario_tira_la_cola_que_nadie_recogio():
    """Una cola sin recoger no sobrevive a abandonar el tramo de verdad.

    Si entre la vuelta y la recogida el usuario salta de compas o cambia el plan,
    esa nota es de un tramo que ya no se esta estudiando y cobrarla la meteria en
    el informe de otra cosa.
    """
    detector = DetectorDeUnSoloOnset("D3", onset=3.9, en_el_cuadro=1)
    seguidor = SeguidorPieza(pieza_de([40, 45, 47, 50]), detector=detector)
    instante = _hasta_la_vuelta(seguidor)
    detector.cuadros = 0
    seguidor.procesar(suena("D3"), instante)

    seguidor.avanzar_a(2.0)

    assert seguidor.recoger_la_cola() == ()


def test_dos_pulsaciones_de_la_cola_no_se_adjudican_a_la_misma_nota():
    """La cola no cobra dos veces la misma nota, igual que el camino normal.

    Dos ataques pegados a la frontera -machacando un compas no es nada exotico-
    que el detector firma los dos despues de la vuelta: los dos entran por la
    cola, y el segundo NO puede volver a cobrar la nota que el primero cobro. Sin
    esto, el informe de la vuelta acabaria con mas acertadas que notas escritas,
    que es justo lo que la regla 1 de `_adjudicar` promete que no pasa.

    El segundo no se lo lleva otra nota: la mas cercana libre es la 2, a 1,95 s de
    su onset, muy fuera de su ventana de reclamo (1,08 s), asi que se descarta sin
    anotar nada y sin contar como fallo. Es lo mismo que hace el camino normal con
    una pulsacion que no alcanza a ninguna nota reclamable.

    La otra mitad de este reparto -que la cola no cobre lo que la VUELTA ya habia
    cobrado por el camino normal- no se puede decidir aqui y no se decide aqui: el
    que repite llama a `olvidar_tramo` antes del salto, asi que para cuando el
    salto llega el seguidor ya no sabe que llevaba cobrado el tramo que se va. Lo
    sabe quien cerro la vuelta, y ahi esta vigilado
    (`SesionDeEstudio._cobrar_la_cola`, con su prueba en `tests/test_estudio.py`).

    Esta prueba se escribio en la segunda ronda de la Task 7, pero lo que sujeta
    -el marcado por-cola de `_adjudicar`- es de la primera: se añadio con la cola
    misma y estaba sin prueba. Conviene no leerla como el testigo del arreglo del
    doble cobro, que es el del estudio.
    """
    class DetectorDeLaCola:
        """Suelta los dos onsets, pero solo cuando se le abre (tras la vuelta)."""

        def __init__(self):
            self.onsets = []

        # Parte de la frontera con el seguidor desde la etapa 2b: el ataque

        # cuyo nombre de nota no cuajo. Este doble no finge rasgueos.

        ataque_sin_altura = None


        def reiniciar(self):
            pass

        def procesar(self, resultado, instante):
            if self.onsets:
                return Pulsacion(nota="D3", cents=0.0, instante=self.onsets.pop(0))
            return None

    detector = DetectorDeLaCola()
    seguidor = SeguidorPieza(pieza_de([40, 45, 47, 50]), detector=detector)
    instante = _hasta_la_vuelta(seguidor)
    # Los dos ataques son ANTERIORES a la frontera (4,0) y el detector los firma
    # despues de la vuelta, que es lo que los mete por la cola.
    detector.onsets = [3.9, 3.95]

    seguidor.procesar(suena("D3"), instante)
    seguidor.procesar(suena("D3"), instante + 0.021)

    cola = seguidor.recoger_la_cola()
    assert [t.indice for t in cola] == [3], (
        "la segunda pulsacion de la cola no puede cobrar la nota que cobro la "
        f"primera; la cola trae {[t.indice for t in cola]}"
    )
    assert cola[0].desfase_s == pytest.approx(0.9)
