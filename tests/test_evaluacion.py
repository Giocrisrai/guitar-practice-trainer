import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.evaluacion import (
    CUADROS_PARA_NOTA_ESTABLE,
    CUADROS_PARA_OLVIDAR_NOTA,
    EvaluadorEjercicio,
)
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.musica import Posicion, nombre_de_midi

PASO = 0.021


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
    instante = 0.0
    for _ in range(5):
        _, instante = tocar(evaluador, suena(45), instante)
    assert evaluador.estado.ayuda_visible is True
    assert evaluador.estado.ultimo_fallo == "A2"

    evaluador.reiniciar()

    assert evaluador.estado.indice == 0
    assert evaluador.estado.intentos == 0
    assert evaluador.estado.ayuda_visible is False
    assert evaluador.estado.ultimo_fallo is None
    assert evaluador.resultado().notas == ()

    # El estado interno del camino B tambien debe quedar limpio: la misma
    # nota equivocada que antes del reinicio ya habia quedado registrada como
    # "ultima nota resuelta" debe poder contar de nuevo como un fallo nuevo.
    estado, _ = tocar(evaluador, suena(45), 0.0)
    assert estado.intentos == 1


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
    # La segunda, identica y sin ataque de energia, no se distingue: el
    # ejercicio se queda pidiendola sin llegar a la tercera nota.
    assert estado.indice == 1
    assert estado.nota_actual.midi == 40


# --- Ronda de correccion 1: regla 3 inalcanzable, instante mal sellado,
# fallos fantasma del camino A --------------------------------------------
#
# La revision encontro que el diseno del camino B, tal como se penso al
# principio, dejaba tres agujeros: (1) "_ultima_nota_resuelta" no se liberaba
# nunca salvo al reiniciar, asi que una nota equivocada repetida bloqueaba
# ambos caminos para siempre y la regla 3 (mostrar ayuda) se volvia
# inalcanzable; (2) el camino B sellaba el instante en que TERMINABA la
# racha de estabilidad, no en el que EMPEZABA, corrompiendo la regularidad
# calculada sobre el informe; (3) el camino A no tenia el mismo filtro que el
# B contra leer dos veces la misma nota sostenida, asi que un segundo pico de
# energia sobre una nota ya aceptada podia contarse como un fallo fantasma
# contra la nota siguiente, o completar dos notas iguales con una sola
# pulsacion.


def test_la_ayuda_por_tiempo_aparece_aunque_los_intentos_no_lleguen_a_cinco():
    """Respaldo temporal de la regla 3: si ninguno de los dos caminos logra
    volver a contar un intento (nota equivocada repetida sin ninguna caida de
    nivel real de por medio), pasados `segundos_para_ayuda` la ayuda aparece
    igual, con tal de que haya habido al menos un fallo.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]), segundos_para_ayuda=1.0)
    estado, instante = tocar(evaluador, suena(45), 0.0)  # un fallo real
    assert estado.intentos == 1
    assert estado.ayuda_visible is False

    # Deja pasar el tiempo sin que se detecte ninguna pulsacion nueva (nivel
    # constante, sin ataques, y la misma nota ya resuelta bloquea el camino B).
    for _ in range(80):
        estado = evaluador.procesar(suena(45), instante)
        instante += PASO

    assert estado.ayuda_visible is True


def test_la_ayuda_por_tiempo_no_aparece_sin_ningun_intento_fallido():
    """Exigir senal creible (no un fallo) evita que la ayuda salte sola
    mientras el alumno todavia esta leyendo el ejercicio sin haber tocado
    nada: con puro silencio no hay senal creible ni fallo, asi que tampoco
    hay ayuda.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40]), segundos_para_ayuda=0.5)
    instante = 0.0
    estado = None
    for _ in range(60):
        estado = evaluador.procesar(silencio(), instante)
        instante += PASO
    assert estado.ayuda_visible is False


def test_camino_b_registra_cuando_empezo_la_racha_no_cuando_termino():
    """El instante que guarda IntentoNota debe ser el del ataque real (camino
    A) o el del comienzo de la racha estable (camino B), nunca el momento en
    que el camino B confirma la racha (unos `cuadros_para_nota_estable - 1`
    cuadros despues). Si no fuera asi, mezclar ambos caminos en una misma
    secuencia perfectamente regular ensuciaria `regularidad_ms` con el
    retraso de confirmacion del camino B.

    Se construye una secuencia con tempo exacto de 0.5 s: la nota A y la nota
    C se resuelven por el camino B (nivel constante, sin ataque alguno) y la
    nota B se resuelve por el camino A (ataque de energia real, con cuadros
    de confianza insuficiente de por medio para que el camino B no se
    adelante). Los tres instantes registrados deben quedar en 0.5, 1.0 y 1.5
    exactos, y la regularidad, en cero.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))

    # Nota A (40): pura camino B. Silencio hasta t=0.500, luego cuadros
    # consecutivos a nivel constante: nunca hay salto de energia.
    instante = 0.0
    while instante < 0.500:
        evaluador.procesar(silencio(), instante)
        instante += 0.05
    instante = 0.500
    for _ in range(6):
        estado = evaluador.procesar(suena(40, nivel=-20.0), instante)
        instante += PASO
    assert estado.indice == 1

    instante = 0.7
    while instante < 0.999:
        evaluador.procesar(silencio(), instante)
        instante += 0.05

    # Nota B (42): pura camino A. Ataque de energia exacto en t=1.000; los
    # cuadros intermedios traen confianza insuficiente para que el camino B
    # no acumule una racha propia antes de que el camino A resuelva en 1.060.
    instante = 1.000
    evaluador.procesar(suena(42, nivel=-15.0, confianza=0.95), instante)
    instante += 0.02
    for _ in range(2):
        evaluador.procesar(suena(42, nivel=-15.0, confianza=0.3), instante)
        instante += 0.02
    instante = 1.060
    estado = evaluador.procesar(suena(42, nivel=-15.0, confianza=0.95), instante)
    assert estado.indice == 2

    # Nota C (44): pura camino B otra vez, en t=1.500.
    instante = 1.2
    while instante < 1.499:
        evaluador.procesar(silencio(), instante)
        instante += 0.05
    instante = 1.500
    for _ in range(6):
        estado = evaluador.procesar(suena(44, nivel=-20.0), instante)
        instante += PASO

    assert estado.completado is True
    resultado = evaluador.resultado()
    instantes = [n.instante for n in resultado.notas]
    assert instantes == pytest.approx([0.5, 1.0, 1.5])
    assert resultado.regularidad_ms == pytest.approx(0.0, abs=1e-6)


def test_un_segundo_pico_de_energia_sobre_la_nota_aceptada_no_cuenta_como_fallo():
    """Un hinchado de volumen o un vibrato marcado sobre la nota que ya se
    acepto puede generar un segundo ataque de energia legitimo (el nivel baja
    un poco, entra en la referencia del detector, y luego sube mas de 6 dB).
    Sin ningun cuadro sin nota creible de por medio, ese segundo ataque no
    debe leerse contra la nota siguiente del ejercicio.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 40]))
    instante = 0.0
    nivel = -20.0
    estado = None

    # Primera pulsacion: del silencio a nivel normal, se resuelve la primera
    # de las dos notas iguales.
    for _ in range(6):
        estado = evaluador.procesar(suena(40, nivel=nivel), instante)
        instante += PASO
    assert estado.indice == 1

    # La nota sigue sonando sin silencio real de por medio: el nivel baja
    # poco a poco (para que la mediana de referencia del detector baje con
    # el) y luego sube de golpe, como un hinchado de volumen.
    for _ in range(6):
        nivel -= 2.0
        estado = evaluador.procesar(suena(40, nivel=nivel), instante)
        instante += PASO
    nivel += 10.0
    for _ in range(3):
        estado = evaluador.procesar(suena(40, nivel=nivel), instante)
        instante += PASO

    # Sigue esperando la segunda nota (identica a la primera): el segundo
    # pico de energia sobre la nota ya aceptada no la completo de mas.
    assert estado.indice == 1
    assert len(evaluador.resultado().notas) == 1


# --- Ronda de correccion 2: un cuadro dudoso no debe resolver la misma
# pulsacion dos veces -------------------------------------------------------
#
# La correccion 1a de la ronda anterior liberaba `_ultima_nota_resuelta` ante
# CUALQUIER cuadro sin nota creible. Eso era demasiado agresivo: el detector
# de tono puede flaquear un instante a mitad de una nota sostenida sin que la
# pulsacion haya terminado (el pipeline emite "silencio" con el nivel
# intacto), y limpiar el registro justo ahi hacia que la racha se cortara,
# se liberara el registro, y los cuadros siguientes de la MISMA pulsacion
# volvieran a formar racha y se resolvieran otra vez -esta vez contra la nota
# esperada siguiente, como un fallo fantasma. `CUADROS_PARA_OLVIDAR_NOTA`
# exige un hueco de varios cuadros seguidos, no uno solo.


def _pulsacion_con_bache(evaluador: EvaluadorEjercicio, cuadros_dudosos: int):
    """Una unica pulsacion sostenida de la nota 40, con `cuadros_dudosos`
    cuadros de "silencio" (nivel intacto, como haria el pipeline si el
    detector de tono flaquea) insertados a mitad del sostenimiento.
    """
    instante = 0.0
    estado = None
    for _ in range(3):
        evaluador.procesar(silencio(), instante)
        instante += PASO
    for i in range(40):
        if 6 <= i < 6 + cuadros_dudosos:
            # "Silencio" con el nivel intacto: el pipeline no ve energia de
            # menos, solo pierde la confianza en la nota.
            estado = evaluador.procesar(silencio(nivel=-20.0), instante)
        else:
            estado = evaluador.procesar(suena(40), instante)
        instante += PASO
    return estado


def test_un_solo_cuadro_dudoso_a_mitad_de_una_pulsacion_no_la_resuelve_dos_veces():
    """Un unico cuadro sin nota creible en medio del sostenimiento de una
    misma pulsacion no debe contar ningun intento ni fijar `ultimo_fallo`:
    sigue siendo la misma nota que ya se acerto, no una pulsacion nueva.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    estado = _pulsacion_con_bache(evaluador, cuadros_dudosos=1)
    assert estado.indice == 1
    assert estado.intentos == 0
    assert estado.ultimo_fallo is None


def test_tres_cuadros_dudosos_seguidos_si_cuentan_como_hueco_real():
    """A partir de CUADROS_PARA_OLVIDAR_NOTA cuadros sin nota creible
    seguidos, el hueco es real: la nota que suena despues -aunque sea la
    misma altura- vuelve a poder resolverse, y si no coincide con la nota
    esperada en ese momento del ejercicio, cuenta como un fallo nuevo.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    estado = _pulsacion_con_bache(evaluador, cuadros_dudosos=CUADROS_PARA_OLVIDAR_NOTA)
    assert estado.indice == 1
    assert estado.intentos == 1
    assert estado.ultimo_fallo == "E2"


# --- Ronda de correccion 3, hallazgo 2 (Minor): falta la prueba que protege
# el reinicio del contador -------------------------------------------------
#
# Las dos pruebas de la ronda 2 fijan la frontera 1 contra 3, pero pasarian
# igual con un contador que solo incrementara y nunca se reiniciara -que es
# justo la propiedad que distingue ese arreglo del anterior (ronda 1, que
# liberaba el registro ante cualquier cuadro dudoso sin excepcion).


def test_el_contador_de_cuadros_dudosos_se_reinicia_no_solo_acumula():
    """Protege la propiedad que distingue este arreglo del anterior: el
    contador de cuadros sin nota creible se REINICIA en cuanto vuelve un
    cuadro creible, no solo se incrementa. Con un patron estrictamente
    alterno (dudoso, creible, dudoso, creible...) nunca hay dos cuadros
    dudosos seguidos, y mucho menos tres, aunque el total acumulado a lo
    largo de la secuencia sea mucho mayor que CUADROS_PARA_OLVIDAR_NOTA. Si
    el contador solo acumulara sin reiniciarse, la ultima nota resuelta se
    olvidaria de todos modos y esta prueba fallaria.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    instante = 0.0
    estado = None

    # Se resuelve la nota 40 de verdad, por el camino B, a nivel constante.
    for _ in range(6):
        estado = evaluador.procesar(suena(40, nivel=-20.0), instante)
        instante += PASO
    assert estado.indice == 1

    # El alumno sigue insistiendo con la MISMA nota 40 (ya equivocada, se
    # espera la 42), alternando cuadro dudoso y cuadro creible sin parar:
    # diez cuadros dudosos en total, pero nunca mas de uno seguido.
    for _ in range(20):
        estado = evaluador.procesar(silencio(nivel=-20.0), instante)
        instante += PASO
        estado = evaluador.procesar(suena(40, nivel=-20.0), instante)
        instante += PASO
    assert estado.intentos == 0
    assert estado.ultimo_fallo is None

    # Una racha real de tres cuadros creibles seguidos con la MISMA nota: si
    # `_ultima_nota_resuelta` sobrevivio (el contador se reinicio en cada
    # cuadro creible, como debe), esto no cuenta como un intento nuevo.
    for _ in range(3):
        estado = evaluador.procesar(suena(40, nivel=-20.0), instante)
        instante += PASO

    assert estado.indice == 1
    assert estado.intentos == 0
    assert estado.ultimo_fallo is None


# --- Ronda de correccion 3: la ayuda por tiempo tambien debe rescatar al
# alumno cuando el detector de tono oscila --------------------------------
#
# Si el detector de tono alterna con periodo corto (dos cuadros creibles, uno
# dudoso, repetido) los dos contadores del evaluador se hambrean mutuamente:
# `_contador_candidata` (camino B) se reinicia en cada cuadro dudoso, y
# `_cuadros_sin_nota_creible` se reinicia en cada cuadro creible. Ninguno de
# los dos llega nunca a tres, asi que ningun camino resuelve nada, `intentos`
# se queda en cero, y la condicion original del disparador por tiempo
# (`intentos >= 1`) tampoco se cumple nunca. El alumno puede llevar veinte
# segundos tocando la nota equivocada sin que el software diga una palabra.
#
# La condicion se cambio de "hubo al menos un fallo" a "hubo alguna nota
# creible mientras esta nota era la actual": eso es lo que de verdad separa a
# un alumno que esta tocando de uno que todavia no ha tocado nada.


def test_un_detector_que_oscila_dispara_la_ayuda_por_tiempo_aunque_nunca_resuelva_nada():
    """Con el patron de jitter que hambrea a los dos contadores (dos cuadros
    creibles, uno dudoso, repetido) ningun camino llega a resolver ninguna
    pulsacion: `intentos` se queda en cero para siempre. La ayuda por tiempo
    debe aparecer de todos modos, porque hubo senal creible de sobra mientras
    esta nota era la actual.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]), segundos_para_ayuda=0.5)
    instante = 0.0
    estado = None
    ciclo = 0
    # La fase del jitter se elige para que el unico ataque de energia real
    # (el salto inicial desde la referencia de silencio) resuelva sobre un
    # cuadro dudoso y no cuente como intento, aislando asi el efecto del
    # jitter en si mismo.
    while instante < 1.0:
        if ciclo % 3 == 0:
            estado = evaluador.procesar(silencio(nivel=-20.0), instante)
        else:
            estado = evaluador.procesar(suena(45), instante)
        instante += PASO
        ciclo += 1

    assert estado.intentos == 0
    assert estado.ayuda_visible is True


def test_el_silencio_absoluto_durante_el_mismo_tiempo_no_dispara_la_ayuda():
    """Contraparte del jitter: sin ninguna senal creible en absoluto durante
    el mismo tiempo, la ayuda no debe aparecer. Ahi el alumno probablemente
    todavia no ha tocado la guitarra.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]), segundos_para_ayuda=0.5)
    instante = 0.0
    estado = None
    while instante < 1.0:
        estado = evaluador.procesar(silencio(), instante)
        instante += PASO

    assert estado.ayuda_visible is False


def test_acertar_y_luego_silencio_no_dispara_la_ayuda():
    """La ventana temporal de la nota nueva solo debe avanzar si hay senal que
    pueda ser un intento de ELLA. Tras acertar la nota anterior y soltar la
    guitarra, pasen los segundos que pasen, la ayuda no aparece: nadie ha
    tocado nada contra la nota nueva.

    Las otras dos pruebas de no-ayuda arrancan en la nota 0, donde no hay nota
    anterior ni cola que la rearme; por eso este fallo paso desapercibido.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]), segundos_para_ayuda=1.0)
    estado, instante = tocar(evaluador, suena(40), 0.0)
    assert estado.indice == 1
    assert estado.ayuda_visible is False

    fin = instante + 3.0
    while instante < fin:
        estado = evaluador.procesar(silencio(), instante)
        instante += PASO

    assert estado.indice == 1
    assert estado.ayuda_visible is False


def test_acertar_dejar_sonar_la_cola_y_luego_silencio_tampoco_dispara_la_ayuda():
    """La cola de la nota ya resuelta sigue dando cuadros creibles con SU nombre.
    Eso no es un intento de la nota nueva y no debe armar el disparador
    temporal: si lo armara, una pausa para pensar regalaria la respuesta
    resaltada en el mastil y el informe anotaria ayuda_mostrada en una nota
    acertada a la primera.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]), segundos_para_ayuda=1.0)
    estado, instante = tocar(evaluador, suena(40), 0.0)
    assert estado.indice == 1

    # La nota 0 sigue sonando un buen rato despues de haberse resuelto.
    for _ in range(20):
        estado = evaluador.procesar(suena(40), instante)
        instante += PASO
    assert estado.indice == 1

    fin = instante + 3.0
    while instante < fin:
        estado = evaluador.procesar(silencio(), instante)
        instante += PASO

    assert estado.ayuda_visible is False


def test_la_cola_de_la_nota_anterior_no_ensucia_el_informe_de_la_siguiente():
    """Comprobacion del efecto visible del defecto anterior: la nota que se
    acierta despues de una pausa larga debe seguir contando como acierto a la
    primera, sin ayuda mostrada.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]), segundos_para_ayuda=1.0)
    estado, instante = tocar(evaluador, suena(40), 0.0)
    for _ in range(20):
        evaluador.procesar(suena(40), instante)
        instante += PASO
    fin = instante + 3.0
    while instante < fin:
        evaluador.procesar(silencio(), instante)
        instante += PASO

    estado, instante = tocar(evaluador, suena(42), instante)
    assert estado.completado is True
    segunda = evaluador.resultado().notas[1]
    assert segunda.ayuda_mostrada is False
    assert segunda.a_la_primera is True


def test_el_camino_b_anota_el_ataque_cuando_el_tono_tarda_en_ser_creible():
    """Los dos caminos deben anotar el MISMO onset: el del ataque de energia.

    En una guitarra real el detector de tono tarda decenas de milisegundos en
    dar una lectura creible tras el ataque, asi que la lectura diferida del
    camino A puede caer sobre un cuadro dudoso y descartarse; entonces resuelve
    el camino B, y el comienzo de su racha estable llega bastante despues del
    ataque. Si el camino B anotara ese comienzo, `regularidad_ms` mediria el
    retraso del detector de tono como si fuera irregularidad del alumno.

    A diferencia de `test_camino_b_registra_cuando_empezo_la_racha_no_cuando_termino`,
    aqui los dos instantes NO coinciden por construccion: el ataque esta en
    1.000 y la racha creible no empieza hasta 1.105.
    """
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    while instante < 1.0:
        evaluador.procesar(silencio(), instante)
        instante += PASO

    # Ataque de energia real en t=1.000. Los cinco primeros cuadros traen
    # confianza insuficiente, asi que la lectura diferida del camino A (1.060)
    # cae sobre un cuadro dudoso y se descarta.
    instante = 1.000
    for _ in range(5):
        evaluador.procesar(suena(40, nivel=-15.0, confianza=0.3), instante)
        instante += PASO
    assert evaluador.estado.indice == 0

    # Ahora si: la racha creible empieza en 1.105 y el camino B resuelve.
    for _ in range(CUADROS_PARA_NOTA_ESTABLE + 1):
        estado = evaluador.procesar(suena(40, nivel=-15.0), instante)
        instante += PASO

    assert estado.indice == 1
    intento = evaluador.resultado().notas[0]
    assert intento.instante == pytest.approx(1.000)


def test_la_instantanea_es_coherente_mientras_el_analisis_avanza():
    """El hilo HTTP/WS pide `estado` a 30 Hz mientras el hilo de analisis muta el
    evaluador. Cada instantanea tiene que describir un solo momento: sin candado
    podia traer `indice=n` con la `nota_actual` de n+1, o `completado=False` con
    `nota_actual=None`.
    """
    import threading

    evaluador = EvaluadorEjercicio(ejercicio_de(list(range(40, 60))))
    parar = threading.Event()
    incoherencias: list[str] = []

    def mirar():
        while not parar.is_set():
            estado = evaluador.estado
            if estado.completado != (estado.nota_actual is None):
                incoherencias.append(f"completado={estado.completado} nota={estado.nota_actual}")
            elif estado.nota_actual is not None:
                esperada = evaluador.ejercicio.notas[estado.indice]
                if estado.nota_actual is not esperada:
                    incoherencias.append(f"indice={estado.indice} nota={estado.nota_actual}")

    vigilante = threading.Thread(target=mirar, daemon=True)
    vigilante.start()
    try:
        instante = 0.0
        for midi in range(40, 60):
            _, instante = tocar(evaluador, suena(midi), instante)
    finally:
        parar.set()
        vigilante.join(timeout=2.0)

    assert evaluador.estado.completado is True
    assert incoherencias == []
