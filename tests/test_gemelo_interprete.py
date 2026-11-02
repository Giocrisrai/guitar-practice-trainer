# tests/test_gemelo_interprete.py
"""El guitarrista sintetico: sus perfiles de destreza y lo que de verdad toca.

La verdad de una interpretacion (`Interpretacion.eventos`) se escribe antes de
generar una sola muestra, asi que casi todas estas pruebas la comprueban contra
la aritmetica de la pieza y no contra el audio. La excepcion es la desafinacion,
que solo significa algo si el detector de tono REAL la ve: ahi se pasa el audio
por el `Analizador` de produccion, igual que hace la cuerda de la tarea 1.
"""

import re
from dataclasses import replace

import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador
from nucleo.gemelo.interprete import (
    DESVIOS_DE_NOTA_MALA,
    FRACCION_DE_CORTE,
    Interpretacion,
    interpretar,
)
from nucleo.gemelo.perfiles import (
    CAOS,
    INTERMEDIO,
    PERFECTO,
    PERFILES_DE_DESTREZA,
    PRINCIPIANTE,
    PerfilDeDestreza,
)
from nucleo.gemelo.piezas_de_prueba import (
    escala_de_ocho_notas,
    pieza_con_acorde,
    pieza_con_nota_repetida,
    pieza_de_demostracion,
    pieza_vacia,
)
from nucleo.musica import nombre_de_midi
from nucleo.piezas.modelo import NotaEnPieza, Pieza, pulsos_a_segundos

FS = 48000
SALTO = 1008  # el salto de produccion: 21 ms
GUITARRA = PERFILES["guitarra_estandar"]


def cents_por_ventana(interpretacion: Interpretacion) -> list[tuple[float, float]]:
    """(instante final de la ventana, cents) de cada ventana que leyo una nota.

    Recorre el audio como lo hace la sesion de estudio y fecha cada lectura en el
    FINAL de su ventana, que es la convencion que la spec midio: en vivo el cuadro
    se entrega cuando el ultimo bloque acaba de llegar.
    """
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    ventana = GUITARRA.tamano_ventana(FS)
    muestras = interpretacion.muestras

    lecturas = []
    for inicio in range(0, len(muestras) - ventana + 1, SALTO):
        resultado = analizador.procesar(muestras[inicio : inicio + ventana])
        if resultado.estado == "nota":
            lecturas.append(((inicio + ventana) / FS, resultado.cents))
    return lecturas


def proporcion_de_notas_reconocidas(interpretacion: Interpretacion) -> float:
    """Fraccion de TODAS las ventanas en que el detector da la nota que suena.

    El denominador son todas las ventanas y no solo las que dieron nota: lo que el
    trasteo le quita al detector no es el acierto del nombre, es la decision
    (se calla por energia o por confianza). Contando solo las ventanas que ya
    dieron nota, una cuerda muy sucia con dos lecturas buenas saldria al 100%.
    """
    frecuencia = interpretacion.frecuencia_muestreo
    analizador = Analizador(GUITARRA, frecuencia_muestreo=frecuencia)
    ventana = GUITARRA.tamano_ventana(frecuencia)
    muestras = interpretacion.muestras

    aciertos = 0
    total = 0
    for inicio in range(0, len(muestras) - ventana + 1, SALTO):
        resultado = analizador.procesar(muestras[inicio : inicio + ventana])
        total += 1
        evento = evento_sonando(interpretacion, (inicio + ventana) / frecuencia)
        if evento is None:
            continue
        if resultado.estado == "nota" and resultado.nota == nombre_de_midi(evento.midi):
            aciertos += 1
    return aciertos / total


def picos_por_evento(interpretacion: Interpretacion) -> list[float]:
    """Amplitud de pico del audio de cada evento, en su propio tramo.

    Vale porque el perfil no solapa notas: el tramo de un evento solo contiene su
    cuerda.
    """
    frecuencia = interpretacion.frecuencia_muestreo
    picos = []
    for evento in interpretacion.eventos:
        desde = int(evento.instante_s * frecuencia)
        hasta = desde + int(evento.duracion_s * frecuencia)
        picos.append(float(np.max(np.abs(interpretacion.muestras[desde:hasta]))))
    return picos


def evento_sonando(interpretacion: Interpretacion, instante_s: float):
    """El evento que esta sonando en ese instante, o None si no hay ninguno."""
    for evento in interpretacion.eventos:
        if evento.instante_s <= instante_s < evento.instante_s + evento.duracion_s:
            return evento
    return None


def test_el_perfecto_toca_cada_nota_en_su_instante():
    pieza = escala_de_ocho_notas()
    interpretacion = interpretar(pieza, PERFECTO)

    assert interpretacion.pieza is pieza  # la necesita `juzgar` (ruling 1)
    assert len(interpretacion.eventos) == 8
    assert [evento.indice_pretendido for evento in interpretacion.eventos] == list(
        range(8)
    )
    for indice, evento in enumerate(interpretacion.eventos):
        esperado = interpretacion.silencio_de_cabecera_s + indice * pulsos_a_segundos(
            1.0, 100
        )
        assert evento.instante_s == pytest.approx(esperado, abs=1e-6)


def test_hay_silencio_de_cabecera_de_al_menos_una_ventana():
    """Sin cabecera, el reloj de la pieza se ancla en la primera nota.

    La spec lo midio: una sonda sin cabecera informaba -69 ms de desfase en una
    interpretacion perfecta, que es un artefacto del gemelo y no de la cadena.
    """
    interpretacion = interpretar(escala_de_ocho_notas(), PERFECTO)

    assert interpretacion.silencio_de_cabecera_s >= 4096 / 48000
    primera = interpretacion.eventos[0]
    hasta = int(primera.instante_s * interpretacion.frecuencia_muestreo)
    assert np.all(interpretacion.muestras[:hasta] == 0.0)


def test_el_tramo_recorta_por_compases():
    interpretacion = interpretar(
        escala_de_ocho_notas(), PERFECTO, primer_compas=2, ultimo_compas=2
    )

    assert len(interpretacion.eventos) == 4
    assert [evento.indice_pretendido for evento in interpretacion.eventos] == [4, 5, 6, 7]


def test_las_repeticiones_repiten_el_tramo():
    interpretacion = interpretar(
        escala_de_ocho_notas(),
        PERFECTO,
        primer_compas=1,
        ultimo_compas=1,
        repeticiones=3,
    )

    assert len(interpretacion.eventos) == 12
    indices = [evento.indice_pretendido for evento in interpretacion.eventos]
    assert indices == [0, 1, 2, 3] * 3


def test_la_cuenta_atras_mete_silencio_antes_de_cada_vuelta():
    """La cuenta atras de la primera vuelta vive dentro del silencio de cabecera.

    El brief pedia que «el primer evento de la segunda vuelta llegue 1,2 s mas
    tarde»: eso es cierto medido desde el comienzo de la interpretacion PROPIA
    (el primer evento), que es lo que se comprueba abajo. En tiempo absoluto
    llega 2,4 s mas tarde porque la primera vuelta tambien tiene su cuenta, y
    tenerla es obligatorio: la tarea 8 comprueba que la cuenta atras sobrevive al
    primer cuadro de audio, y para eso ese silencio tiene que estar DENTRO del
    audio.
    """
    pieza = escala_de_ocho_notas()
    sin_cuenta = interpretar(pieza, PERFECTO, repeticiones=2)
    con_cuenta = interpretar(
        pieza, PERFECTO, repeticiones=2, segundos_de_cuenta_atras=1.2
    )

    assert con_cuenta.silencio_de_cabecera_s == pytest.approx(
        sin_cuenta.silencio_de_cabecera_s + 1.2, abs=1e-6
    )
    distancia_sin = (
        sin_cuenta.eventos[8].instante_s - sin_cuenta.eventos[0].instante_s
    )
    distancia_con = (
        con_cuenta.eventos[8].instante_s - con_cuenta.eventos[0].instante_s
    )
    assert distancia_con == pytest.approx(distancia_sin + 1.2, abs=1e-6)


def test_el_factor_de_tempo_estira_la_interpretacion():
    pieza = escala_de_ocho_notas()
    normal = interpretar(pieza, PERFECTO)
    lenta = interpretar(pieza, PERFECTO, factor_tempo=0.5)

    for indice in range(len(normal.eventos) - 1):
        paso_normal = (
            normal.eventos[indice + 1].instante_s - normal.eventos[indice].instante_s
        )
        paso_lento = (
            lenta.eventos[indice + 1].instante_s - lenta.eventos[indice].instante_s
        )
        assert paso_lento == pytest.approx(2.0 * paso_normal, abs=1e-6)


def test_el_acorde_se_reduce_a_la_nota_mas_grave():
    """El gemelo no finge polifonia: el detector real es monofonico."""
    pieza = pieza_con_acorde()
    interpretacion = interpretar(pieza, PERFECTO)

    pulso_del_acorde = 1.0
    escritas = [
        nota for nota in pieza.notas if nota.inicio_pulsos == pulso_del_acorde
    ]
    assert len(escritas) == 2

    instante = interpretacion.silencio_de_cabecera_s + pulsos_a_segundos(
        pulso_del_acorde, pieza.tempo
    )
    sonando = [
        evento
        for evento in interpretacion.eventos
        if evento.instante_s == pytest.approx(instante, abs=1e-6)
    ]
    assert len(sonando) == 1
    assert sonando[0].midi == min(nota.midi for nota in escritas)


def test_una_nota_fallada_no_genera_evento():
    perfil = replace(PERFECTO, probabilidad_de_fallo=1.0)
    interpretacion = interpretar(escala_de_ocho_notas(), perfil, semilla=1)

    assert interpretacion.eventos == ()
    assert np.all(interpretacion.muestras == 0.0)


def test_la_nota_mala_suena_a_otra_altura_pero_apunta_a_la_nota_escrita():
    pieza = escala_de_ocho_notas()
    perfil = replace(PERFECTO, probabilidad_de_nota_mala=1.0)
    interpretacion = interpretar(pieza, perfil, semilla=2)

    assert len(interpretacion.eventos) == 8
    for indice, evento in enumerate(interpretacion.eventos):
        assert evento.indice_pretendido == indice
        escrita = pieza.notas[indice].midi
        assert evento.midi != escrita
        assert abs(evento.midi - escrita) in {1, 2}


def test_la_desafinacion_mueve_la_altura_de_verdad():
    """Lo comprueba el detector de produccion, no la aritmetica del gemelo.

    Un gemelo que se desafinase solo en el campo `cents` y no en el audio pasaria
    cualquier prueba que no abriese las muestras, y la etapa 3e pinta en pantalla
    lo que lee el detector.

    La comparacion es POR EVENTO y no por ventana. El brief pedia «|cents| > 15 en
    la mayoria de las ventanas»: con una desviacion tipica de 40 cents eso es una
    afirmacion sobre el sorteo -el 30% de las notas sale dentro de los 15 cents
    por puro azar- y con la semilla equivocada la prueba cae sin que nada este
    roto. Lo que de verdad se quiere afirmar es mas fuerte: que lo que el detector
    lee en cada nota es la desviacion que el gemelo escribio en ella, con su signo.

    Las notas que pasan de 45 cents se dejan fuera: ahi el semitono mas cercano ya
    es el de al lado y `cents` se mide contra ese otro, asi que el signo se
    invierte. No es un defecto del gemelo ni del detector, es lo que significa
    `cents`.
    """
    perfil = replace(PERFECTO, cents_de_desafinacion=40.0)
    interpretacion = interpretar(escala_de_ocho_notas(), perfil, semilla=2)

    lecturas = cents_por_ventana(interpretacion)
    assert lecturas, "el detector no leyo ninguna nota"

    por_evento: dict[int, list[float]] = {}
    for instante, cents in lecturas:
        evento = evento_sonando(interpretacion, instante)
        if evento is not None:
            por_evento.setdefault(evento.indice_pretendido, []).append(cents)

    comparadas = 0
    desviadas = 0
    for evento in interpretacion.eventos:
        leidas = por_evento.get(evento.indice_pretendido)
        if not leidas or abs(evento.cents) > 45.0:
            continue
        comparadas += 1
        leido = float(np.median(leidas))
        assert leido == pytest.approx(evento.cents, abs=12.0)
        if abs(evento.cents) > 15.0:
            desviadas += 1
            assert abs(leido) > 15.0
    assert comparadas >= 6
    assert desviadas >= 3


def test_el_interprete_no_solapa_dos_notas_consecutivas():
    """Las colas solapadas generan ataques fantasma, y el gemelo no los regala.

    Si el interprete los produjese sin querer, acusaria a la cadena de inventarse
    notas que en realidad se invento el. Provocarlos a proposito es `sustain`.

    La desigualdad es ESTRICTA y con el margen que promete `FRACCION_DE_CORTE`, no
    un `<=`: con la figura igual al hueco -el caso de esta escala y de cualquier
    melodia de negras seguidas- un corte al 100% del hueco da igualdad exacta, asi
    que un `<=` pasaria por empate y no por margen, y la constante que el modulo
    llama «lo que garantiza que el interprete no solapa» podria subirse a 1,0 sin
    que nada cayera.
    """
    interpretacion = interpretar(escala_de_ocho_notas(), PERFECTO)

    eventos = interpretacion.eventos
    for actual, siguiente in zip(eventos, eventos[1:], strict=False):
        hueco_s = siguiente.instante_s - actual.instante_s
        silencio_s = siguiente.instante_s - (actual.instante_s + actual.duracion_s)
        assert silencio_s > 0.0
        assert silencio_s >= (1.0 - FRACCION_DE_CORTE) * hueco_s - 1e-9


def test_el_sustain_alto_si_solapa():
    perfil = replace(PERFECTO, sustain=1.0)
    interpretacion = interpretar(escala_de_ocho_notas(), perfil)

    eventos = interpretacion.eventos
    assert any(
        actual.instante_s + actual.duracion_s > siguiente.instante_s
        for actual, siguiente in zip(eventos, eventos[1:], strict=False)
    )


def test_una_pieza_sin_notas_da_una_interpretacion_de_silencio():
    interpretacion = interpretar(pieza_vacia(), PERFECTO)

    assert interpretacion.eventos == ()
    assert interpretacion.muestras.size > 0
    assert np.all(interpretacion.muestras == 0.0)
    assert interpretacion.duracion_s > 0.0


def test_un_tramo_sin_notas_da_una_interpretacion_de_silencio():
    pieza = Pieza(
        nombre="con el tercer compas vacio",
        perfil="guitarra_estandar",
        tempo=100,
        compas=(4, 4),
        notas=(
            NotaEnPieza(
                midi=55, cuerda=3, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0
            ),
            NotaEnPieza(
                midi=57, cuerda=3, traste=2, inicio_pulsos=4.0, duracion_pulsos=1.0
            ),
            NotaEnPieza(
                midi=59, cuerda=2, traste=0, inicio_pulsos=12.0, duracion_pulsos=1.0
            ),
        ),
    )
    interpretacion = interpretar(pieza, PERFECTO, primer_compas=3, ultimo_compas=3)

    assert interpretacion.eventos == ()
    assert np.all(interpretacion.muestras == 0.0)
    duracion_del_compas = pulsos_a_segundos(4.0, pieza.tempo)
    assert interpretacion.duracion_s == pytest.approx(
        interpretacion.silencio_de_cabecera_s + duracion_del_compas, abs=1e-6
    )


def test_la_misma_semilla_da_la_misma_interpretacion():
    pieza = escala_de_ocho_notas()
    primera = interpretar(pieza, PRINCIPIANTE, semilla=5)
    segunda = interpretar(pieza, PRINCIPIANTE, semilla=5)
    otra = interpretar(pieza, PRINCIPIANTE, semilla=6)

    assert np.array_equal(primera.muestras, segunda.muestras)
    assert primera.eventos == segunda.eventos
    assert not np.array_equal(primera.muestras, otra.muestras)
    assert primera.eventos != otra.eventos


def test_los_cuatro_perfiles_de_fabrica_estan_y_el_perfecto_no_falla_nada():
    assert set(PERFILES_DE_DESTREZA) == {
        "perfecto",
        "principiante",
        "intermedio",
        "caos",
    }
    assert PERFILES_DE_DESTREZA["perfecto"] is PERFECTO
    assert PERFILES_DE_DESTREZA["principiante"] is PRINCIPIANTE
    assert PERFILES_DE_DESTREZA["intermedio"] is INTERMEDIO
    assert PERFILES_DE_DESTREZA["caos"] is CAOS

    assert PERFECTO.probabilidad_de_fallo == 0.0
    assert PERFECTO.probabilidad_de_nota_mala == 0.0
    assert PERFECTO.probabilidad_de_trasteo == 0.0
    assert PERFECTO.desfase_medio_s == 0.0
    assert PERFECTO.desviacion_desfase_s == 0.0
    assert PERFECTO.cents_de_desafinacion == 0.0


@pytest.mark.parametrize("valor", [1.5, -0.1])
def test_un_perfil_con_probabilidad_fuera_de_rango_se_rechaza(valor):
    with pytest.raises(ValueError, match=re.escape("probabilidad_de_fallo")):
        PerfilDeDestreza(
            nombre="imposible",
            desfase_medio_s=0.0,
            desviacion_desfase_s=0.0,
            probabilidad_de_fallo=valor,
            probabilidad_de_nota_mala=0.0,
            probabilidad_de_trasteo=0.0,
            cents_de_desafinacion=0.0,
            fuerza_media=0.8,
            desviacion_fuerza=0.0,
            sustain=0.0,
        )


def test_la_pieza_con_nota_repetida_trae_dos_alturas_iguales_seguidas():
    """La necesita el veredicto: las notas repetidas se excluyen del juicio.

    `DetectorPulsaciones` declara por escrito que no distingue dos pulsaciones
    seguidas de la misma nota sin un hueco de tres cuadros sin nota creible.
    """
    notas = pieza_con_nota_repetida().notas
    assert any(
        actual.midi == siguiente.midi
        for actual, siguiente in zip(notas, notas[1:], strict=False)
    )


def test_la_pieza_de_demostracion_dura_unos_treinta_segundos_y_trae_secciones():
    """Es la pieza del escaparate, y el escaparate practica por secciones."""
    pieza = pieza_de_demostracion()

    assert 25.0 < pieza.duracion_s < 35.0
    assert len(pieza.secciones) == 4
    assert [seccion.nombre for seccion in pieza.secciones] == [
        "Intro",
        "Tema",
        "Puente",
        "Final",
    ]


# --- El contrato de reproducibilidad --------------------------------------
#
# Las pruebas de aqui abajo son las que defienden que el azar se consume en el
# orden del contrato y que cada campo del perfil esta conectado a algo. Sin
# ellas, el revisor demostro que se podian hacer los seis sorteos condicionales,
# invertir dos de ellos, anular el trasteo entero, ignorar la fuerza y multiplicar
# el desfase por cero sin que ninguna de las veinte primeras pruebas cayera.


def test_el_orden_en_que_se_consume_el_azar_es_el_del_contrato():
    """El espejo del contrato: por nota, fallo, nota mala, trasteo, desfase,
    desafinacion y fuerza, en ese orden y siempre.

    Esta prueba vuelve a consumir el MISMO generador en el MISMO orden y compara
    evento por evento. Es la unica forma de que el orden sea falsable: dos sorteos
    seguidos del mismo flujo uniforme solo se distinguen contra una referencia, y
    aqui la referencia es el contrato escrito, no unos literales medidos.

    Lo que caza, y nada mas lo cazaba:
      - saltarse un sorteo cuando su probabilidad o su sigma valen cero (el flujo
        se desincroniza y a partir de ahi todo cambia),
      - intercambiar dos sorteos (el valor que decide el fallo pasa a decidir la
        nota mala),
      - no consumir los cinco sorteos restantes cuando la nota ya se fallo.

    El perfil lleva las tres probabilidades altas a proposito: con `INTERMEDIO`
    tal cual (fallo 0,02) ninguna nota falla en ocho tiradas y el sorteo del fallo
    quedaria sin observar.
    """
    perfil = replace(
        INTERMEDIO,
        probabilidad_de_fallo=0.3,
        probabilidad_de_nota_mala=0.3,
        probabilidad_de_trasteo=0.5,
    )
    pieza = escala_de_ocho_notas()
    semilla = 11
    interpretacion = interpretar(pieza, perfil, semilla=semilla)

    espejo = np.random.default_rng(semilla)
    esperados = []
    for indice, nota in enumerate(pieza.notas):
        falla = espejo.random() < perfil.probabilidad_de_fallo
        es_mala = espejo.random() < perfil.probabilidad_de_nota_mala
        desvio = DESVIOS_DE_NOTA_MALA[int(espejo.integers(0, len(DESVIOS_DE_NOTA_MALA)))]
        trastea = espejo.random() < perfil.probabilidad_de_trasteo
        desfase_s = perfil.desfase_medio_s + espejo.normal() * perfil.desviacion_desfase_s
        cents = espejo.normal() * perfil.cents_de_desafinacion
        espejo.normal()  # la fuerza: se consume aunque el evento no la publique
        if falla:
            continue
        esperados.append(
            (
                indice,
                nota.midi + (desvio if es_mala else 0),
                interpretacion.silencio_de_cabecera_s
                + pulsos_a_segundos(nota.inicio_pulsos, pieza.tempo)
                + desfase_s,
                cents,
                trastea,
            )
        )

    # Que el perfil de verdad ejercite los tres sorteos de decision, o la prueba
    # estaria comprobando el orden de un flujo que nadie mira.
    assert 0 < len(esperados) < len(pieza.notas)
    assert any(esperado[4] for esperado in esperados)
    assert any(esperado[1] != pieza.notas[esperado[0]].midi for esperado in esperados)

    assert len(interpretacion.eventos) == len(esperados)
    for evento, esperado in zip(interpretacion.eventos, esperados, strict=True):
        indice, midi, instante_s, cents, trastea = esperado
        assert evento.indice_pretendido == indice
        assert evento.midi == midi
        assert evento.instante_s == pytest.approx(instante_s, abs=1e-9)
        assert evento.cents == pytest.approx(cents, abs=1e-9)
        assert evento.trasteada is trastea


def test_cambiar_la_desafinacion_no_cambia_nada_mas():
    """Dos interpretaciones que difieren en un campo difieren en una sola cosa.

    Es el motivo por el que el azar se consume siempre, tambien cuando el perfil
    tiene el campo a cero: si el sorteo de la desafinacion se saltase con sigma
    cero, todo el azar posterior -de esta nota y de todas las siguientes- se
    desplazaria, y comparar un perfil afinado con el mismo perfil desafinado
    dejaria de medir la desafinacion para medir el desplazamiento.
    """
    pieza = escala_de_ocho_notas()
    afinado = interpretar(
        pieza, replace(INTERMEDIO, cents_de_desafinacion=0.0), semilla=7
    )
    desafinado = interpretar(
        pieza, replace(INTERMEDIO, cents_de_desafinacion=25.0), semilla=7
    )

    assert len(afinado.eventos) == len(desafinado.eventos) > 0
    for limpio, desviado in zip(afinado.eventos, desafinado.eventos, strict=True):
        assert desviado.indice_pretendido == limpio.indice_pretendido
        assert desviado.midi == limpio.midi
        assert desviado.instante_s == pytest.approx(limpio.instante_s, abs=1e-12)
        assert desviado.duracion_s == pytest.approx(limpio.duracion_s, abs=1e-6)
        assert desviado.trasteada is limpio.trasteada

    assert all(evento.cents == 0.0 for evento in afinado.eventos)
    assert all(abs(evento.cents) > 1e-6 for evento in desafinado.eventos)


def test_fallar_notas_no_cambia_el_sonido_de_las_que_si_suenan():
    """La semilla de cada cuerda sale de su SITIO, no del orden de llegada.

    Si saliese del numero de pulsaciones ya generadas -que solo crece con las
    notas que no se fallan-, subir `probabilidad_de_fallo` cambiaria el timbre de
    notas que no fallaron, y el gemelo dejaria de servir para comparar perfiles.
    Se compara el AUDIO muestra a muestra, porque es ahi donde vive ese segundo
    flujo de azar: los eventos ya coincidirian de todas formas.
    """
    pieza = escala_de_ocho_notas()
    entero = interpretar(pieza, replace(PERFECTO, probabilidad_de_fallo=0.0), semilla=13)
    con_fallos = interpretar(
        pieza, replace(PERFECTO, probabilidad_de_fallo=0.4), semilla=13
    )

    assert 0 < len(con_fallos.eventos) < len(entero.eventos)
    for evento in con_fallos.eventos:
        gemelo = next(
            otro
            for otro in entero.eventos
            if otro.indice_pretendido == evento.indice_pretendido
        )
        assert evento == gemelo
        desde = int(evento.instante_s * entero.frecuencia_muestreo)
        hasta = desde + int(evento.duracion_s * entero.frecuencia_muestreo)
        assert np.array_equal(
            entero.muestras[desde:hasta], con_fallos.muestras[desde:hasta]
        )


def test_el_trasteo_del_perfil_llega_a_la_cuerda():
    """`probabilidad_de_trasteo` tiene que ensuciar el audio, no solo un campo.

    Lo juzga el detector de produccion: el trasteo no cambia el nombre de la nota,
    le quita al detector la DECISION (se calla por energia o por confianza), asi
    que el denominador son todas las ventanas y no solo las que dieron nota.
    """
    pieza = escala_de_ocho_notas()
    limpia = interpretar(pieza, replace(PERFECTO, probabilidad_de_trasteo=0.0), semilla=4)
    sucia = interpretar(pieza, replace(PERFECTO, probabilidad_de_trasteo=1.0), semilla=4)

    assert not any(evento.trasteada for evento in limpia.eventos)
    assert all(evento.trasteada for evento in sucia.eventos)
    assert len(sucia.eventos) == len(limpia.eventos)
    assert not np.array_equal(sucia.muestras, limpia.muestras)
    assert proporcion_de_notas_reconocidas(sucia) < proporcion_de_notas_reconocidas(
        limpia
    )


def test_la_fuerza_del_perfil_es_la_amplitud_de_la_pulsacion():
    pieza = escala_de_ocho_notas()
    floja = interpretar(pieza, replace(PERFECTO, fuerza_media=0.3), semilla=4)
    fuerte = interpretar(pieza, replace(PERFECTO, fuerza_media=0.9), semilla=4)

    assert np.max(np.abs(floja.muestras)) == pytest.approx(0.3, abs=1e-6)
    assert np.max(np.abs(fuerte.muestras)) == pytest.approx(0.9, abs=1e-6)


def test_el_temblor_de_la_fuerza_hace_que_no_todas_las_notas_suenen_igual():
    pieza = escala_de_ocho_notas()
    perfil = replace(PERFECTO, fuerza_media=0.6, desviacion_fuerza=0.2)
    temblorosa = interpretar(pieza, perfil, semilla=4)
    firme = interpretar(pieza, replace(perfil, desviacion_fuerza=0.0), semilla=4)

    picos_temblorosos = picos_por_evento(temblorosa)
    picos_firmes = picos_por_evento(firme)
    assert all(pico == pytest.approx(0.6, abs=1e-6) for pico in picos_firmes)
    assert float(np.std(picos_temblorosos)) > 0.05


def test_el_desfase_medio_atrasa_todas_las_notas():
    pieza = escala_de_ocho_notas()
    perfil = replace(PERFECTO, desfase_medio_s=0.050)
    interpretacion = interpretar(pieza, perfil, semilla=4)

    for indice, evento in enumerate(interpretacion.eventos):
        en_su_sitio = interpretacion.silencio_de_cabecera_s + indice * pulsos_a_segundos(
            1.0, pieza.tempo
        )
        assert evento.instante_s == pytest.approx(en_su_sitio + 0.050, abs=1e-9)


def test_el_temblor_del_desfase_dispersa_las_notas():
    """El temblor cae a los dos lados del sitio y no todo al mismo.

    Con sigma cero las ocho notas caen exactamente en la rejilla; con sigma 0,04
    ninguna afirmacion sobre una nota concreta seria estable, asi que lo que se
    afirma es la dispersion y que haya desviaciones de los dos signos.
    """
    pieza = escala_de_ocho_notas()
    perfil = replace(PERFECTO, desviacion_desfase_s=0.040)
    interpretacion = interpretar(pieza, perfil, semilla=4)

    rejilla = [
        interpretacion.silencio_de_cabecera_s
        + indice * pulsos_a_segundos(1.0, pieza.tempo)
        for indice in range(len(interpretacion.eventos))
    ]
    desviaciones = [
        evento.instante_s - sitio
        for evento, sitio in zip(interpretacion.eventos, rejilla, strict=True)
    ]
    assert float(np.std(desviaciones)) > 0.010
    assert any(desviacion > 0.0 for desviacion in desviaciones)
    assert any(desviacion < 0.0 for desviacion in desviaciones)
