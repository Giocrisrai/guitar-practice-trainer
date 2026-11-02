"""El conductor del estudio: la politica de la pasada, conducida a mano.

Ni una espera real ni un dispositivo de audio en todo el archivo: al conductor se
le pasa el reloj por parametro -no lo lee de ninguna parte- y el audio entra como
`ResultadoAnalisis`, que es lo mismo que le llega al servidor.

Estas pruebas son las del REFACTOR de la etapa 3d: la politica que decide cuando
da la vuelta el bucle, que se anota en el historial y cuando sube el tempo salio
de `servidor/piezas.py` al nucleo para que el gemelo digital pueda conducirla sin
FastAPI. Lo que esa politica hace ya lo vigilan `tests/test_app_estudio.py` y
`tests/test_sesion_carril.py` desde el servidor; aqui se vigila que se pueda
conducir desde fuera de el.
"""

from pathlib import Path

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.piezas.conductor import (
    ESPERA_SIN_CUADROS_S,
    TECHO_TRAMO_S,
    ConductorDeEstudio,
)
from nucleo.piezas.estudio import HistorialDeEstudio, PlanDePasada, SesionDeEstudio
from nucleo.piezas.modelo import NotaEnPieza, Pieza

# Un compas de 4/4 a 60 ppm son cuatro segundos, y la pieza es exactamente ese
# compas: asi el final del tramo cae en un numero redondo y el bucle da la vuelta
# donde la prueba dice, sin tener que contar notas.
COMPAS_S = 4.0


def pieza_de_un_compas(tempo=60):
    notas = tuple(
        NotaEnPieza(
            midi=40 + i, cuerda=6, traste=i, inicio_pulsos=float(i), duracion_pulsos=1.0
        )
        for i in range(4)
    )
    return Pieza(
        nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas
    )


def conductor_de(plan=None, historial=None, al_cambiar_repeticion=None, ahora=1000.0):
    """Un conductor ya arrancado y con la mirada puesta en `ahora`.

    La cuenta atras va a cero salvo que el plan diga otra cosa: estas pruebas
    miden el reloj de la pasada, y con cuenta atras delante el cabezal se queda
    quieto en el inicio mientras la cuenta se gasta (eso lo vigila
    `tests/test_estudio.py`, que es de quien es).
    """
    estudio = SesionDeEstudio(
        pieza_de_un_compas(), plan or PlanDePasada(compases_de_cuenta_atras=0)
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(
        estudio,
        historial=historial,
        al_cambiar_repeticion=al_cambiar_repeticion,
    )
    conductor.fijar_la_mirada(ahora)
    return conductor


SILENCIO = ResultadoAnalisis(
    estado="silencio",
    frecuencia=None,
    confianza=0.0,
    nivel_db=-90.0,
    nota=None,
    cents=None,
    posiciones=(),
)


def mirar_hasta(conductor, segundos, desde=1000.0, paso=0.05):
    """Conduce el reloj a mano en pasos por debajo del techo del tramo.

    Es como se mueve el tiempo en produccion sin audio: el WebSocket pregunta a
    30 Hz (33 ms) y cada mirada entra entera porque no llega al techo. Devuelve el
    ultimo estado.
    """
    ahora = desde
    estado = None
    restante = segundos
    while restante > 1e-9:
        este = min(paso, restante)
        ahora += este
        estado = conductor.mirar(ahora, senal_ausente=False)
        restante -= este
    return estado


def test_observar_mueve_el_reloj_con_el_cuadro():
    """Dos cuadros separados 0,021 s: el instante de la pasada avanza 0,021.

    Es el camino CON audio, el unico que no pierde las pulsaciones en vuelo: el
    reloj lo mueve la correspondencia entre el reloj del analisis y el de la
    pieza, no el tramo de la mirada.
    """
    conductor = conductor_de()
    conductor.mirar(1000.0, senal_ausente=False)
    conductor.observar(SILENCIO, 1000.0)
    conductor.mirar(1000.021, senal_ausente=False)
    estado = conductor.observar(SILENCIO, 1000.021)
    assert estado.carril.instante_s == pytest.approx(0.021, abs=1e-6)


def test_mirar_sin_cuadros_avanza_con_techo():
    """Sin ningun cuadro previo y con un salto de 5 s, el reloj avanza el techo.

    Un hueco largo no entra en la pieza por ningun camino: es el invariante que
    `TECHO_TRAMO_S` existe para sostener.
    """
    conductor = conductor_de()
    estado = conductor.mirar(1005.0, senal_ausente=False)
    assert estado.carril.instante_s == pytest.approx(TECHO_TRAMO_S, abs=1e-9)


def test_mirar_con_cuadros_recientes_no_mueve_el_reloj():
    """Tras un cuadro, una mirada inmediata no toca el reloj.

    Los cuadros mandan mientras llegan: moverlo a mano con audio entrando le
    costaria al seguidor las pulsaciones en vuelo (ver `ESPERA_SIN_CUADROS_S`).
    """
    conductor = conductor_de()
    conductor.mirar(1000.0, senal_ausente=False)
    conductor.observar(SILENCIO, 1000.0)
    antes = conductor.estudio.estado.carril.instante_s
    estado = conductor.mirar(1000.0 + ESPERA_SIN_CUADROS_S / 2, senal_ausente=False)
    assert estado.carril.instante_s == pytest.approx(antes, abs=1e-9)


def test_la_senal_ausente_no_mueve_el_reloj():
    """El tiempo sin señal no entra en la pieza (spec §5).

    Un carril que corre con el cable desenchufado hace fallar notas que nunca
    sonaron.
    """
    conductor = conductor_de()
    estado = conductor.mirar(1000.05, senal_ausente=True)
    assert estado.carril.instante_s == pytest.approx(0.0, abs=1e-9)


def test_la_transicion_de_vuelta_cierra_el_informe_y_lo_anota():
    """Con bucle y el reloj cruzando el final: una vuelta cerrada y una anotada.

    Son las dos mitades de la misma transicion, y hacen falta las dos: el informe
    de SOLO esa vuelta lo cierra el estudio, y el conductor lo anota en el
    historial para que el tempo automatico tenga de donde decidir.
    """
    historial = HistorialDeEstudio()
    conductor = conductor_de(
        plan=PlanDePasada(en_bucle=True, compases_de_cuenta_atras=0),
        historial=historial,
    )
    estado = mirar_hasta(conductor, COMPAS_S + 0.5)
    assert estado.repeticion == 2
    assert len(conductor.vueltas_cerradas) == 1
    assert historial.pasadas == 1


def test_al_cambiar_repeticion_se_llama_una_vez_por_vuelta():
    """El enganche del click: una llamada por vuelta, con la repeticion nueva.

    El conductor no abre audio y no sabe que hay un metronomo al otro lado: pide
    que le avisen cuando cambie la repeticion, y quien lo conduce decide si eso
    significa rearrancar un click o no significa nada.
    """
    repeticiones = []
    conductor = conductor_de(
        plan=PlanDePasada(en_bucle=True, compases_de_cuenta_atras=0),
        al_cambiar_repeticion=lambda estado: repeticiones.append(estado.repeticion),
    )
    mirar_hasta(conductor, 2 * COMPAS_S + 0.5)
    assert repeticiones == [2, 3]


def test_el_conductor_no_abre_audio():
    """La regla de dependencias del nucleo, comprobada sobre el propio archivo.

    `nucleo/piezas/estudio.py` lo dice en su primera pagina -NO ABRE AUDIO- y
    esto es lo mismo un piso mas arriba: el click se queda en el servidor. Se
    comprueba leyendo el modulo porque es una regla sobre el codigo, no sobre una
    ejecucion, y merece una prueba y no confianza.
    """
    fuente = Path("nucleo/piezas/conductor.py").read_text(encoding="utf-8")
    for prohibido in ("sintesis", "Metronomo", "SalidaAudio", "sounddevice"):
        assert prohibido not in fuente, (
            f"`{prohibido}` aparece en el conductor: el nucleo no abre audio"
        )


def test_el_conductor_no_importa_del_servidor():
    """Y no importa de `servidor/` ni de `interfaz/`: es para lo que se extrajo.

    Si el conductor pudiera importar del servidor, `nucleo/gemelo/` tendria que
    reimplementar esta politica para poder conducirla, y entonces el gemelo se
    estaria dando la razon a si mismo en vez de verificar el codigo de verdad.
    """
    fuente = Path("nucleo/piezas/conductor.py").read_text(encoding="utf-8")
    assert "import servidor" not in fuente
    assert "from servidor" not in fuente
    assert "interfaz" not in fuente


def test_el_servidor_reexporta_las_constantes():
    """Quien las lea desde `servidor.piezas` sigue leyendo las mismas.

    Se mudaron al nucleo, pero las pruebas del carril y cualquier otro lector las
    piden donde estaban: reimportarlas es lo que impide que un refactor rompa a
    terceros por un cambio de domicilio.
    """
    from servidor import piezas

    assert piezas.TECHO_TRAMO_S == TECHO_TRAMO_S
    assert piezas.ESPERA_SIN_CUADROS_S == ESPERA_SIN_CUADROS_S
