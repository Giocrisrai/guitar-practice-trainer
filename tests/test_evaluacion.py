import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.evaluacion import CUADROS_PARA_NOTA_ESTABLE, EvaluadorEjercicio
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.musica import Posicion, nombre_de_midi

PASO = 0.021
ESPERA = 0.060


def ejercicio_de(midis: list[int], tempo: int = 80) -> Ejercicio:
    return Ejercicio(
        clave="prueba",
        nombre="Prueba",
        descripcion="",
        notas=tuple(
            NotaEsperada(midi=m, posiciones=(Posicion(cuerda=6, traste=0),)) for m in midis
        ),
        tempo=tempo,
        perfil="guitarra_estandar",
    )


def silencio(nivel: float = -95.0) -> ResultadoAnalisis:
    return ResultadoAnalisis(estado="silencio", frecuencia=0.0, confianza=0.0, nivel_db=nivel)


def suena(midi: int, cents: float = 0.0, confianza: float = 0.95, nivel: float = -30.0):
    return ResultadoAnalisis(
        estado="nota",
        frecuencia=110.0,
        confianza=confianza,
        nivel_db=nivel,
        nota=nombre_de_midi(midi),
        cents=cents,
        posiciones=[Posicion(cuerda=6, traste=0)],
        cuerda_objetivo=6,
        afinada=abs(cents) < 5.0,
    )


def tocar(evaluador: EvaluadorEjercicio, resultado, instante_inicial: float, cuadros: int = 8):
    """Simula una pulsacion: silencio, ataque, y sostenimiento el tiempo suficiente."""
    instante = instante_inicial
    for _ in range(3):
        evaluador.procesar(silencio(), instante)
        instante += PASO
    for _ in range(cuadros):
        estado = evaluador.procesar(resultado, instante)
        instante += PASO
    return estado, instante


def test_al_empezar_apunta_a_la_primera_nota():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    assert evaluador.estado.indice == 0
    assert evaluador.estado.total == 3
    assert evaluador.estado.completado is False
    assert evaluador.estado.nota_actual.midi == 40


def test_la_nota_correcta_avanza_el_ejercicio():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, _ = tocar(evaluador, suena(40), 0.0)
    assert estado.indice == 1
    assert estado.nota_actual.midi == 42


def test_una_secuencia_perfecta_completa_el_ejercicio_sin_fallos():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    instante = 0.0
    for midi in (40, 42, 44):
        _, instante = tocar(evaluador, suena(midi), instante)
    resultado = evaluador.resultado()
    assert resultado.completado is True
    assert resultado.aciertos_a_la_primera == 3
    assert all(n.intentos == 1 for n in resultado.notas)


def test_una_nota_equivocada_cuenta_intento_y_no_avanza():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, instante = tocar(evaluador, suena(45), 0.0)
    assert estado.indice == 0
    assert estado.intentos == 1
    estado, _ = tocar(evaluador, suena(40), instante)
    assert estado.indice == 1


def test_el_informe_registra_los_intentos_que_costo_cada_nota():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(2):
        _, instante = tocar(evaluador, suena(45), instante)
    _, instante = tocar(evaluador, suena(40), instante)
    assert evaluador.resultado().notas[0].intentos == 3


def test_una_nota_correcta_pero_desafinada_cuenta_como_acierto():
    """Regla 2: la afinacion se mide, no bloquea."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, _ = tocar(evaluador, suena(40, cents=20.0), 0.0)
    assert estado.indice == 1
    assert evaluador.resultado().notas[0].cents == pytest.approx(20.0)


def test_un_ataque_sin_nota_creible_no_cuenta_como_fallo():
    """Regla 1: un roce o un armonico accidental no debe puntuar en contra."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    estado, _ = tocar(evaluador, suena(45, confianza=0.2), 0.0)
    assert estado.intentos == 0
    assert estado.indice == 0


def test_el_silencio_no_cuenta_como_fallo():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(30):
        estado = evaluador.procesar(silencio(), instante)
        instante += PASO
    assert estado.intentos == 0


def test_una_nota_sostenida_cuenta_una_sola_vez():
    """Sesenta resultados diciendo Mi son un intento, no sesenta.

    Con el camino B activo esta nota se resuelve casi siempre antes que el
    camino A (el ataque de energia sigue disparandose porque hay un salto real
    desde el silencio, pero su lectura queda cancelada al resolver el camino B
    primero). La prueba sigue verificando lo mismo que en el brief: sostener
    una nota no debe inflar el contador de intentos.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, _ = tocar(evaluador, suena(45), 0.0, cuadros=60)
    assert estado.intentos == 1


def test_tras_cinco_fallos_se_muestra_la_ayuda():
    """Regla 3: no se salta el ejercicio, se ayuda."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(5):
        estado, instante = tocar(evaluador, suena(45), instante)
    assert estado.ayuda_visible is True
    assert estado.indice == 0


def test_antes_del_quinto_fallo_no_hay_ayuda():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(4):
        estado, instante = tocar(evaluador, suena(45), instante)
    assert estado.ayuda_visible is False


def test_la_ayuda_queda_registrada_en_el_informe():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(5):
        _, instante = tocar(evaluador, suena(45), instante)
    _, instante = tocar(evaluador, suena(40), instante)
    assert evaluador.resultado().notas[0].ayuda_mostrada is True


def test_el_instante_del_ataque_se_registra_siempre():
    """Aunque el modo por turnos no evalue el tempo, el informe de regularidad lo necesita."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    instante = 0.0
    for midi in (40, 42, 44):
        _, instante = tocar(evaluador, suena(midi), instante)
    instantes = [n.instante for n in evaluador.resultado().notas]
    assert all(i is not None for i in instantes)
    assert instantes == sorted(instantes)


def test_el_ejercicio_completado_no_sigue_aceptando_notas():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    _, instante = tocar(evaluador, suena(40), 0.0)
    assert evaluador.estado.completado is True
    estado, _ = tocar(evaluador, suena(42), instante)
    assert estado.completado is True
    assert len(evaluador.resultado().notas) == 1


def test_un_ejercicio_a_medias_da_un_informe_incompleto():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    tocar(evaluador, suena(40), 0.0)
    resultado = evaluador.resultado()
    assert resultado.completado is False
    assert len(resultado.notas) == 1


def test_reiniciar_devuelve_el_evaluador_al_principio():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    tocar(evaluador, suena(40), 0.0)
    evaluador.reiniciar()
    assert evaluador.estado.indice == 0
    assert evaluador.estado.intentos == 0
    assert evaluador.resultado().notas == ()


def test_el_estado_se_serializa_para_la_interfaz():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    datos = evaluador.estado.a_dict()
    assert set(datos) == {
        "indice",
        "total",
        "intentos",
        "ayuda_visible",
        "completado",
        "nota_actual",
        "ultimo_fallo",
    }
    assert datos["nota_actual"]["nombre"] == "E2"


def test_el_ultimo_fallo_dice_que_nota_sono():
    """Para que la pantalla pueda decir 'esperaba Mi, sono La'."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    estado, _ = tocar(evaluador, suena(45), 0.0)
    assert estado.ultimo_fallo == "A2"


# --- Camino B: cambio estable de nota, sin depender del ataque de energia ---
#
# El brief original hace que el evaluador dependa solo del ataque de energia.
# Medido con el decaimiento real de una guitarra (~8.7 dB/s), eso no funciona a
# tempo normal: cuando se pulsa la nota siguiente, la anterior todavia suena y
# el salto no llega a los 6 dB que exige el detector. Estas pruebas verifican
# el segundo camino de disparo que soluciona eso.


def test_cambio_de_nota_sin_ataque_de_energia_avanza_el_ejercicio():
    """La prueba que justifica todo el cambio: nivel constante, sin ningun
    salto de energia, pero con la nota cambiando de la esperada anterior a la
    siguiente. El ejercicio debe avanzar de todos modos, por el camino B.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    instante = 0.0
    nivel = -20.0

    # Ceba la primera nota (habra un salto inicial inevitable desde el
    # silencio de referencia, pero eso no es lo que se esta probando aqui).
    for _ in range(6):
        evaluador.procesar(suena(40, nivel=nivel), instante)
        instante += PASO
    assert evaluador.estado.indice == 1
    assert evaluador.estado.nota_actual.midi == 42

    # Ahora cambia la nota SIN variar el nivel en absoluto: no hay ningun
    # ataque de energia posible entre estos dos cuadros y los anteriores.
    estado = None
    for _ in range(CUADROS_PARA_NOTA_ESTABLE + 2):
        estado = evaluador.procesar(suena(42, nivel=nivel), instante)
        instante += PASO

    assert estado.indice == 2
    assert estado.completado is True


def test_cambio_de_nota_fugaz_no_dispara_nada():
    """Un armonico de un par de cuadros no es una nota: hacen falta
    CUADROS_PARA_NOTA_ESTABLE cuadros seguidos para que el camino B dispare.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    instante = 0.0
    nivel = -20.0

    for _ in range(6):
        evaluador.procesar(suena(40, nivel=nivel), instante)
        instante += PASO
    assert evaluador.estado.indice == 1

    estado = evaluador.estado
    for _ in range(CUADROS_PARA_NOTA_ESTABLE - 1):
        estado = evaluador.procesar(suena(44, nivel=nivel), instante)
        instante += PASO

    assert estado.indice == 1
    assert estado.intentos == 0


def test_una_nota_sostenida_correcta_no_vuelve_a_dispararse_por_camino_b():
    """Tras resolverse una nota correcta, sostenerla no debe seguir avanzando
    el ejercicio nota tras nota.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    instante = 0.0
    nivel = -20.0

    estado = None
    for _ in range(20):
        estado = evaluador.procesar(suena(40, nivel=nivel), instante)
        instante += PASO

    assert estado.indice == 1
    assert estado.nota_actual.midi == 42
    assert len(evaluador.resultado().notas) == 1
    assert evaluador.resultado().notas[0].intentos == 1


def test_dos_notas_iguales_seguidas_sin_ataque_no_avanza():
    """Limitacion conocida y documentada en EvaluadorEjercicio: si el ejercicio
    pide la misma nota dos veces seguidas, el camino B no distingue la segunda
    de la primera porque no hay cambio de altura. Sin un ataque de energia real
    (aqui el nivel se mantiene constante a proposito) el camino A tampoco tiene
    nada que resolver, asi que el ejercicio se queda esperando en la segunda
    nota repetida.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 40, 42]))
    instante = 0.0
    nivel = -20.0

    estado = None
    for _ in range(40):
        estado = evaluador.procesar(suena(40, nivel=nivel), instante)
        instante += PASO

    # La primera nota si se resuelve (fue el primer cambio de "nada" a "Mi").
    assert estado.indice == 1
    assert estado.nota_actual.midi == 40
    # La segunda, identica y sin ataque de energia, no se distingue: el
    # ejercicio no llega a la tercera nota.
    assert estado.indice != 2
