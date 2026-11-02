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

import ast
import threading
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


# El modulo bajo prueba, por ruta ABSOLUTA. Con `Path("nucleo/piezas/...")` las
# dos pruebas de dependencias se rompian con `FileNotFoundError` al ejecutar
# pytest desde otro directorio, y una prueba que falla al cambiar de carpeta no
# comprueba lo que dice: dice "el conductor no abre audio" y en realidad decia
# "el cwd es la raiz del repo".
FUENTE_DEL_CONDUCTOR = (
    Path(__file__).resolve().parents[1] / "nucleo" / "piezas" / "conductor.py"
)


def modulos_importados(ruta: Path) -> set[str]:
    """Los modulos que ese archivo importa, leidos del arbol sintactico.

    Con `ast` y no buscando texto. Buscar "interfaz" o "servidor" en el archivo
    entero legisla tambien los COMENTARIOS: la primera version de estas pruebas
    obligo a reescribir una frase que nombraba a la interfaz para hablar de quien
    aplica la sugerencia del tempo, y una prueba que opina sobre la prosa es una
    prueba que alguien acabara silenciando. Esto dice exactamente lo que se quiere
    decir: de donde importa este modulo.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    modulos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos |= {alias.name for alias in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module is not None:
            modulos.add(nodo.module)
    return modulos


def test_el_conductor_no_abre_audio():
    """La regla de dependencias del nucleo, comprobada sobre el propio archivo.

    `nucleo/piezas/estudio.py` lo dice en su primera pagina -NO ABRE AUDIO- y
    esto es lo mismo un piso mas arriba: el click se queda en el servidor. Se
    comprueba leyendo el modulo porque es una regla sobre el codigo, no sobre una
    ejecucion, y merece una prueba y no confianza.
    """
    fuente = FUENTE_DEL_CONDUCTOR.read_text(encoding="utf-8")
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
    for modulo in modulos_importados(FUENTE_DEL_CONDUCTOR):
        raiz = modulo.split(".")[0]
        assert raiz not in ("servidor", "interfaz"), (
            f"el conductor importa de `{modulo}`: el nucleo no puede"
        )



def test_un_hueco_de_audio_no_entra_en_la_pieza():
    """El cuadro que llega tras un apagon no empuja el cabezal con el hueco.

    Es el defecto que `observar` documenta y que la suite de 1108 pruebas no
    cazaba. `procesar` calcula el instante de la pieza restandole al reloj del
    analisis un origen fijado ANTES del hueco, asi que sin recolocar antes
    (`congelar_en`) el hueco entero entra en el cabezal: con los 5 s de esta
    prueba el cabezal se va a 5,0 s y el alumno falla de golpe todas las notas de
    esos 5 s sin haber oido ninguna. Medido quitando la recolocacion: 5,0 s.

    Y se conduce SIN mirada por medio, que es lo que hace esta prueba distinta de
    las que ya habia. Con una mirada entre los dos cuadros el hueco tampoco entra,
    pero no por merito de `observar`: la mirada mueve el reloj con `avanzar`, eso
    acaba en `avanzar_a` y `avanzar_a` invalida la correspondencia entre los dos
    relojes, de modo que el cuadro siguiente la fija de nuevo y el salto no se ve.
    Por eso una prueba con mirada por medio sigue verde aunque se quite la
    recolocacion: no comprueba nada. El servidor siempre mira antes de observar
    -y por eso nunca vio el defecto-, pero el gemelo digital conduce `observar`
    directamente y el hueco era suyo.
    """
    conductor = conductor_de()
    conductor.mirar(1000.0, senal_ausente=False)
    conductor.observar(SILENCIO, 1000.0)
    # El audio se para 5 s y vuelve, y nadie mira mientras: es el apagon con el
    # WebSocket desconectado, o el gemelo que solo mete cuadros.
    estado = conductor.observar(SILENCIO, 1005.0)
    assert estado.carril.instante_s == pytest.approx(0.0, abs=1e-6)


def test_el_aviso_de_la_vuelta_sale_sin_el_candado_del_conductor():
    """El oyente se protege a si mismo: el conductor no le presta su exclusion.

    Es un contrato y no una casualidad, y por eso hay prueba. Hasta la primera
    ronda de revision el aviso salia con el candado del conductor tomado y lo
    unico que protegia al oyente del servidor -que lee y escribe su metronomo, su
    clave de click y su pausa- era que el aviso llegase siempre desde el hilo del
    WebSocket, que ya tenia tomado el candado del carril. El gemelo digital
    conduce `mirar` directamente y sin ningun candado de servidor por encima: ese
    dia el oyente se quedaba sin exclusion ninguna, o la tomaba el mismo e
    invertia el orden de las tomas.

    Se comprueba desde DENTRO del aviso, intentando tomar el candado del conductor
    desde otro hilo: si se consigue, el conductor no lo tiene tomado, y entonces
    ninguna exclusion suya se esta heredando. Y se conduce `mirar` a pelo, sin
    ningun candado alrededor, que es como lo hara el gemelo.
    """
    libre = []

    def oyente(estado):
        libre.append(se_puede_tomar(conductor._candado))

    conductor = conductor_de(
        plan=PlanDePasada(en_bucle=True, compases_de_cuenta_atras=0),
        al_cambiar_repeticion=oyente,
    )
    mirar_hasta(conductor, COMPAS_S + 0.5)
    assert libre == [True]


def se_puede_tomar(candado) -> bool:
    """Si OTRO hilo puede tomar ese candado ahora mismo. No espera.

    Tiene que ser otro hilo: un `RLock` se deja tomar dos veces por el hilo que ya
    lo tiene, asi que preguntarselo desde aqui diria siempre "si" y la prueba no
    comprobaria nada.
    """
    resultado = []

    def intentar():
        tomado = candado.acquire(blocking=False)
        resultado.append(tomado)
        if tomado:
            candado.release()

    hilo = threading.Thread(target=intentar)
    hilo.start()
    hilo.join()
    return resultado[0]
