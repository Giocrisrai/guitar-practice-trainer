"""El carril: seguir una pieza donde manda el reloj, no los aciertos.

Ni una espera real en todo el archivo: el reloj de la pieza se mueve a mano con
`avanzar_a` y el del analisis se pasa como argumento a `procesar`.
"""

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import Pulsacion
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from nucleo.piezas.seguimiento import VENTANA_A_TIEMPO_S, SeguidorPieza


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
