"""La sesion del carril: el reloj lo lleva el servidor y el audio lo alimenta.

Ni una espera real en todo el archivo: el reloj se inyecta y las pruebas lo mueven
a mano. Tampoco se abre ningun dispositivo de audio: la sesion de audio es un
doble con las tres cosas que `SesionCarril` le pide.
"""

import pathlib
import threading

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.piezas.conductor import ESPERA_SIN_CUADROS_S as ESPERA_DEL_NUCLEO
from nucleo.piezas.conductor import TECHO_TRAMO_S as TECHO_DEL_NUCLEO
from nucleo.piezas.estudio import PlanDePasada
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from servidor.configuracion import Configuracion
from servidor.piezas import (
    ARRANQUE_NINGUNO,
    ESPERA_SIN_CUADROS_S,
    TECHO_TRAMO_S,
    SesionCarril,
)
from servidor.sesion import INTERVALO_ANALISIS


class RelojFalso:
    """Reloj que solo avanza cuando se le dice. Ninguna prueba espera de verdad."""

    def __init__(self):
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


def pieza_de(midis, tempo=60):
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=6, traste=i, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i, m in enumerate(midis)
    )
    return Pieza(nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas)


class SesionAudioFalsa:
    """Doble de `Sesion` con `senal_ausente` mutable desde la prueba.

    El nucleo NO lleva un interruptor que solo exista para los tests: el doble
    vive aqui. `SesionCarril` solo necesita de su sesion de audio tres cosas,
    asi que el doble tiene exactamente esas tres.

    `detener()` es una cuarta, pero no la usa `SesionCarril`: la llaman las
    pruebas al terminar, igual que se apagaria una sesion de verdad.
    """

    def __init__(self):
        self.senal_ausente = False
        self.observadores = []

    def registrar_observador(self, observador):
        self.observadores.append(observador)

    def quitar_observador(self, observador):
        if observador in self.observadores:
            self.observadores.remove(observador)

    def detener(self) -> None:
        self.observadores.clear()


def carril(reloj):
    sesion = SesionAudioFalsa()
    return SesionCarril(sesion, reloj=reloj), sesion


def suena(nota, nivel=-25.0, confianza=0.9, cents=0.0):
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=confianza, nivel_db=nivel,
        nota=nota, cents=cents, posiciones=(),
    )


SILENCIO = ResultadoAnalisis(
    estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
    nota=None, cents=None, posiciones=(),
)


# Lo que dura un cuadro de analisis en estas pruebas, que es el paso por omision
# de `publicar` y la cadencia de produccion (21 ms). Como margen de una medicion
# en segundos es lo mas fino que tiene sentido pedir: por debajo de un cuadro, lo
# que se estaria midiendo es en que cuadro cayo la cuenta y no el comportamiento.
PASO_DE_CUADRO_S = 0.021
UN_CUADRO_S = PASO_DE_CUADRO_S


def reloj_del_seguidor(sesion_carril) -> float:
    """El reloj del SEGUIDOR, leido sin pasar por `estado()`.

    Se mete por dentro a proposito, y es el unico sitio del archivo que lo hace.
    `estado()` no sirve para esto: antes de publicar MIRA, y la mirada puede mover
    el reloj, asi que lo que devuelve es el reloj ya arreglado y no el que la
    pausa dejo. Y el espejo publico del servidor (`_instante`) tampoco, porque es
    una copia que se adopta en cada aviso y no el reloj de verdad.

    Lo que el seguidor tiene es la verdad del cabezal (`EstadoEstudio.carril` ES
    `SeguidorPieza.estado`), asi que leerlo aqui es leer el reloj que el nucleo
    lleva mientras entra audio.
    """
    return sesion_carril._estudio._seguidor.estado.instante_s


def publicar(sesion, reloj, resultado, cuadros=1, paso=PASO_DE_CUADRO_S):
    """Publica cuadros de analisis como lo haria la sesion de audio de verdad.

    El instante que acompaña a cada cuadro es el del reloj del ANALISIS, que en
    produccion es `time.monotonic()`; aqui es el mismo reloj falso, que es lo que
    hace el servidor real (los dos son el reloj monotonico de la maquina).
    """
    for _ in range(cuadros):
        for observador in list(sesion.observadores):
            observador(resultado, reloj())
        reloj.avanzar(paso)


def avanzar_mirando(sesion_carril, reloj, segundos, paso=1 / 30.0):
    """Mueve el reloj en pasos, consultando el estado en cada uno.

    Es como se mueve el tiempo en produccion: el WebSocket pregunta a 30 Hz (y el
    audio avisa mas a menudo todavia, cada 21 ms). Ninguna espera real: el paso lo
    da el reloj falso. Devuelve el ultimo estado consultado.
    """
    restante = segundos
    estado = sesion_carril.estado()
    while restante > 1e-9:
        este = min(paso, restante)
        reloj.avanzar(este)
        estado = sesion_carril.estado()
        restante -= este
    return estado


def agotar_cuenta_atras(sesion_carril, reloj, paso=0.0625, tope=600):
    """Mira hasta que se agota la cuenta atras del plan. Devuelve el estado.

    Las pruebas que miden el reloj de la pieza -o lo que el audio le cobra al
    seguidor- necesitan el cabezal ya suelto, y el plan por defecto trae un compas
    de cuenta atras delante (cuatro segundos en 4/4 a 60 ppm). Se agota MIRANDO,
    como lo haria el WebSocket, y no apagandola en el plan.

    Esa distincion es el motivo de que esta funcion exista. Apagar en una prueba
    la caracteristica que esa prueba vigilaria es lo que dejo pasar el Critical de
    la revision final: la cuenta atras moria con el primer cuadro de audio -el
    servidor congelaba el reloj con `colocar_en`, que la cancela- y las dos unicas
    pruebas de este archivo que podian haberlo visto llevaban
    `compases_de_cuenta_atras=0`.

    Hace falta que haya señal y que no haya llegado ningun cuadro todavia: es la
    unica situacion en la que `_mirar` le pasa el tramo transcurrido al estudio.

    Dos detalles que parecen quisquillosos y no lo son, porque sin ellos la cuenta
    se come un tramo de la pieza y todas las medidas de despues salen cortas:

    - El paso es 0,0625 s y no 1/30: divide los 4 s de la cuenta en 64 pasos
      exactos en binario, asi que el ultimo la deja en 0,0 clavado. Con 1/30
      quedaba un residuo de microsegundos y el aviso siguiente -que ya no era de
      la cuenta- se gastaba en apurarlo, de modo que el cabezal perdia un paso.
      Y sigue por debajo de `TECHO_TRAMO_S` (0,1 s), asi que cada paso cuenta
      entero.
    - La condicion mira el campo del nucleo y no el del estado publicado:
      `EstadoEstudio.a_dict` redondea la cuenta a milisegundos, asi que un residuo
      de microsegundos se publica como 0 estando todavia abierta.

    El tope esta para que un fallo sea un fallo y no una suite colgada.
    """
    estudio = sesion_carril._estudio
    # Y lo primero, que HAYA cuenta que agotar: sin esto el ayudante devuelve en
    # silencio con la cuenta ya apagada, y la asercion «mientras la cuenta baja el
    # cabezal no se mueve» pasa identica sin cuenta ninguna. Es la misma trampa que
    # este ayudante existe para evitar, un piso mas abajo.
    assert estudio._cuenta_atras_restante_s > 0, (
        "no hay cuenta atras que agotar: esta prueba se cree que la tiene delante "
        "y no la tiene"
    )
    for _ in range(tope):
        if estudio._cuenta_atras_restante_s == 0:
            return sesion_carril.estado()
        reloj.avanzar(paso)
        sesion_carril.estado()
    raise AssertionError("la cuenta atras del plan no se agoto")



def test_iniciar_devuelve_la_pieza_entera_una_sola_vez():
    """La pieza no viaja por el WebSocket: cientos de notas 30 veces por segundo
    seria tirar el canal en datos que no cambian."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    respuesta = sesion_carril.iniciar(pieza_de([40, 45]))
    assert respuesta["pieza"]["notas"][0]["midi"] == 40
    assert "pieza" not in sesion_carril.estado()
    sesion_carril.detener()


def test_el_instante_avanza_con_el_reloj():
    """Adaptada del brief: el reloj avanza EN PASOS, mirando, como el WebSocket.

    El brief movia el reloj 1,4 s de un salto y exigia que el cabezal se fuera
    1,4 s de una vez. Esa expectativa era el defecto que hizo volver el salto de
    30 s por tres caminos distintos: decia que un hueco largo sin ninguna
    evidencia hay que creerselo entero. Ahora el cabezal avanza como mucho
    `TECHO_TRAMO_S` por aviso, asi que la prueba avanza el reloj como ocurre de
    verdad -a 30 Hz, con el WebSocket preguntando- y comprueba lo que de verdad
    importaba: que el instante sigue al reloj y que el indice lo decide el reloj.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    # CON la cuenta atras del plan por defecto delante, que es como arranca de
    # verdad: primero se agota mirando y despues se mide el seguimiento del reloj.
    # (Esta prueba llevaba `compases_de_cuenta_atras=0`, y era una de las dos que
    # podian haber visto morir la cuenta con el primer cuadro de audio.)
    sesion_carril.iniciar(pieza_de([40, 45]))
    assert sesion_carril.estado()["instante_s"] == 0.0
    # Mientras la cuenta baja, el cabezal no se mueve ni un milimetro.
    assert agotar_cuenta_atras(sesion_carril, reloj)["instante_s"] == pytest.approx(0.0)
    estado = avanzar_mirando(sesion_carril, reloj, 1.4)
    assert estado["instante_s"] == pytest.approx(1.4, abs=0.001)
    assert estado["indice_actual"] == 1
    sesion_carril.detener()
    sesion.detener()


def test_sin_senal_el_carril_se_detiene_y_al_volver_sigue_donde_estaba():
    """Un carril que corre con el cable desenchufado te hace fallar notas que
    nunca sonaron."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    # CON la cuenta atras del plan por defecto: ver `agotar_cuenta_atras`. Esta
    # era la otra prueba que la llevaba apagada.
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    agotar_cuenta_atras(sesion_carril, reloj)
    assert avanzar_mirando(sesion_carril, reloj, 1.0)["instante_s"] == pytest.approx(1.0, abs=0.001)

    sesion.senal_ausente = True
    estado = avanzar_mirando(sesion_carril, reloj, 5.0)
    assert estado["instante_s"] == pytest.approx(1.0, abs=0.001)
    assert estado["pausado"] is True

    sesion.senal_ausente = False
    estado = avanzar_mirando(sesion_carril, reloj, 0.5)
    assert estado["instante_s"] == pytest.approx(1.5, abs=0.001)
    sesion_carril.detener()
    sesion.detener()


def test_perder_la_senal_en_plena_cuenta_atras_no_la_cancela():
    """La otra mitad del Critical: la rama de la pausa por falta de señal.

    Tambien congelaba el reloj del estudio con `colocar_en`, que es la puerta que
    CANCELA la cuenta atras, asi que desenchufar el cable durante la cuenta la
    mataba y el alumno se quedaba sin aviso justo cuando lo volvia a enchufar.
    Congelar el reloj es decir «se queda donde esta», que es lo que la cuenta
    atras quiere, no lo contrario.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    estado = avanzar_mirando(sesion_carril, reloj, 1.0)
    assert estado["cuenta_atras_restante_s"] == pytest.approx(3.0, abs=0.05)

    sesion.senal_ausente = True
    estado = avanzar_mirando(sesion_carril, reloj, 5.0)
    assert estado["pausado"] is True
    # Ni se cancela ni se gasta esperando: el tiempo sin señal no entra en la
    # pieza, y la cuenta atras es parte de la pieza.
    assert estado["cuenta_atras_restante_s"] == pytest.approx(3.0, abs=0.05)

    sesion.senal_ausente = False
    agotar_cuenta_atras(sesion_carril, reloj)
    estado = avanzar_mirando(sesion_carril, reloj, 0.5)
    assert estado["instante_s"] == pytest.approx(0.5, abs=0.05)
    sesion_carril.detener()
    sesion.detener()


def test_una_pieza_en_otra_afinacion_que_la_activa_se_rechaza():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    bajo = Pieza(nombre="p", perfil="bajo_4", tempo=60, compas=(4, 4), notas=())
    try:
        with pytest.raises(ValueError, match="bajo_4"):
            sesion_carril.iniciar(bajo)
    finally:
        sesion_carril.detener()
        sesion.detener()


def test_la_afinacion_activa_sale_de_la_sesion_de_audio_si_la_lleva():
    """El camino de produccion: la afinacion activa es la del afinador.

    La configuracion no esta en la frontera de tres miembros -un doble no tiene
    que inventarse una-, pero cuando la sesion de audio la lleva, como la de
    verdad, es ella la que manda.
    """
    reloj = RelojFalso()
    sesion = SesionAudioFalsa()
    sesion.configuracion = Configuracion(perfil="bajo_4")
    sesion_carril = SesionCarril(sesion, reloj=reloj)
    bajo = Pieza(nombre="p", perfil="bajo_4", tempo=60, compas=(4, 4), notas=())
    try:
        sesion_carril.iniciar(bajo)
        assert sesion_carril.activa is True
        with pytest.raises(ValueError, match="bajo_4"):
            sesion_carril.iniciar(pieza_de([40]))
    finally:
        sesion_carril.detener()
        sesion.detener()


def test_detener_quita_el_observador_y_deja_de_avanzar():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40]))
    sesion_carril.detener()
    reloj.avanzar(3.0)
    assert sesion_carril.activa is False
    assert sesion_carril.estado()["instante_s"] == 0.0
    assert sesion.observadores == []
    sesion.detener()


def test_detener_dos_veces_no_falla_y_la_segunda_deja_el_carril_parado():
    """Y lo deja PARADO: no basta con que no reviente.

    Tal y como estaba, esta prueba sobrevivia a que `detener` fuera un no-op: no
    aseveraba nada. Lo que hay que fijar es que el segundo `detener` no deshace
    el primero -que no vuelve a registrar el observador ni resucita la pieza- y
    que el estado publicado sigue siendo el de un carril apagado.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40]))
    sesion_carril.detener()
    sesion_carril.detener()
    assert sesion_carril.activa is False
    assert sesion_carril.pieza is None
    assert sesion.observadores == []
    estado = sesion_carril.estado()
    assert (estado["total"], estado["instante_s"], estado["arranque"]) == (0, 0.0, 0)
    sesion.detener()


def test_lo_que_oye_el_cable_llega_al_seguidor():
    """La otra mitad del trabajo: sin esto el carril seria un reloj con pantalla.

    Se toca la nota que vive en el segundo 0.0 de la pieza (MIDI 40 = "E2") y se
    comprueba que sale anotada como acertada.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    publicar(sesion, reloj, suena("E2"), cuadros=12)
    tocadas = sesion_carril.estado()["tocadas"]
    assert len(tocadas) == 1
    assert tocadas[0]["nombre"] == "E2"
    assert tocadas[0]["acertada"] is True
    sesion_carril.detener()
    sesion.detener()


def test_el_websocket_mirando_el_estado_no_se_come_las_pulsaciones():
    """El WebSocket llama a `estado()` 30 veces por segundo mientras entra audio.

    Si esas llamadas le movieran el reloj al seguidor a mano, cada una invalidaria
    las pulsaciones EN VUELO -el detector tarda decenas de milisegundos en
    resolver una- y no se anotaria ni una nota en toda la pieza.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    for _ in range(12):
        publicar(sesion, reloj, suena("E2"), cuadros=1)
        sesion_carril.estado()
    assert len(sesion_carril.estado()["tocadas"]) == 1
    sesion_carril.detener()
    sesion.detener()


def test_mientras_no_hay_senal_los_cuadros_no_mueven_el_carril():
    """Los cuadros de silencio siguen llegando con el cable enchufado y callado:
    si alimentaran al seguidor, el carril correria igual que sin pausa."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    publicar(sesion, reloj, SILENCIO, cuadros=10)
    assert sesion_carril.estado()["instante_s"] == pytest.approx(0.21, abs=0.03)

    sesion.senal_ausente = True
    publicar(sesion, reloj, SILENCIO, cuadros=100)
    instante = sesion_carril.estado()["instante_s"]
    assert sesion_carril.estado()["pausado"] is True
    assert instante == pytest.approx(0.21, abs=0.03)

    sesion.senal_ausente = False
    publicar(sesion, reloj, suena("A2"), cuadros=12)
    despues = sesion_carril.estado()
    assert despues["pausado"] is False
    assert despues["instante_s"] > instante
    # Y sigue donde estaba, no donde estaria si los 2,1 s de silencio contaran:
    # al pausar se le congela el reloj tambien al seguidor, que es quien lo lleva
    # mientras entra audio. Sin eso, el primer cuadro tras la vuelta lo colocaria
    # mas de dos segundos dentro de la pieza.
    assert despues["instante_s"] == pytest.approx(instante + 0.25, abs=0.1)


def test_la_pausa_le_congela_el_reloj_tambien_al_seguidor():
    """El reloj DEL SEGUIDOR durante la pausa, leido sin pasar por `estado()`.

    **ESTA PRUEBA MEDIA OTRA COSA QUE SU NOMBRE, y esto es lo que se cambio.** Lo
    que hacia era un apagon de 100 cuadros (2,1 s) y una sola lectura de
    `estado()` al final. Dos problemas:

    1. **El apagon pasaba de `ESPERA_SIN_CUADROS_S`** (0,25 s), asi que lo que
       salvaba el cabezal no era la pausa sino el hueco de audio: al volver la
       señal, `ConductorDeEstudio.observar` ve el hueco en el reloj del analisis y
       recoloca por ese camino. Medido: quitando el `congelar_en` de
       `mover_el_reloj` -o sea, dejando la pausa sin congelar nada- esta prueba
       seguia PASANDO, y la que caia era
       `test_una_pausa_corta_con_audio_entrando_tampoco_mueve_el_cabezal`, que es
       la que si usa una pausa mas corta que esa espera.
    2. **Leia el estado publicado y no el reloj del seguidor**, que es lo que el
       nombre promete. El estado publicado sale de `estado()`, que antes de
       publicarlo MIRA, y la mirada puede recolocar el reloj: lo que se afirmaba
       era el resultado de ese arreglo, no el estado en que la pausa dejo al
       seguidor.

    Lo que mide ahora, con una pausa de 5 cuadros -mas corta que
    `ESPERA_SIN_CUADROS_S`, para que el camino del hueco de audio NO pueda
    taparlo- y sin una sola llamada a `estado()` en medio:

    * el reloj del seguidor **no se mueve en ningun cuadro de la pausa**, y se
      queda exactamente en el espejo del conductor: 0,168 s, un cuadro (21 ms)
      por detras de los 0,189 s a los que lo dejo el ultimo cuadro con señal. Ese
      cuadro de diferencia no es deriva: es la decision escrita en
      `ConductorDeEstudio.observar` de que el espejo lo adopta la MIRADA y no el
      cuadro, para que la pausa congele el cabezal en un punto fijo. Por eso se
      afirma la igualdad con el espejo y no con el ultimo cuadro;
    * y al volver la señal **retoma desde ahi**: 12 cuadros despues esta en
      0,399 s, o sea el punto congelado mas once cuadros (el primero no cuenta,
      porque es el que vuelve a fijar la correspondencia entre los dos relojes).
      Sin congelar, ese primer cuadro le mete la pausa entera en el cabezal y se
      iria a 0,504 s, cinco cuadros mas alla.

    Que la lectura sea del seguidor y no de `estado()` es lo que hace que la
    segunda afirmacion sea del nucleo: sin cliente de WebSocket conectado nadie
    llama a `estado()`, asi que esto es lo que de verdad pasa.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    publicar(sesion, reloj, SILENCIO, cuadros=10)
    con_senal = reloj_del_seguidor(sesion_carril)
    assert con_senal == pytest.approx(0.189, abs=UN_CUADRO_S)

    # La pausa tiene que ser MAS CORTA que la espera sin cuadros, o el camino del
    # hueco de audio recoloca el reloj y esta prueba deja de medir la pausa. Se
    # afirma aqui para que la premisa no se pudra si alguna de las dos cambia.
    assert PASO_DE_CUADRO_S * 5 < ESPERA_SIN_CUADROS_S
    sesion.senal_ausente = True
    congelado = None
    for _ in range(5):
        publicar(sesion, reloj, SILENCIO, cuadros=1)
        ahora = reloj_del_seguidor(sesion_carril)
        if congelado is None:
            congelado = ahora
        # Quieto EXACTAMENTE, cuadro a cuadro: no es una tolerancia, es que
        # `observar` no le da de comer al estudio mientras el reloj esta congelado.
        assert ahora == congelado

    # Congelado donde lo dejo la ultima MIRADA, que es el espejo del conductor, y
    # no donde lo dejo el ultimo cuadro: un cuadro por detras, a proposito.
    assert congelado == sesion_carril._instante
    assert congelado == pytest.approx(con_senal - UN_CUADRO_S, abs=1e-9)

    sesion.senal_ausente = False
    publicar(sesion, reloj, SILENCIO, cuadros=12)
    assert reloj_del_seguidor(sesion_carril) == pytest.approx(
        congelado + 11 * PASO_DE_CUADRO_S, abs=UN_CUADRO_S
    ), "el primer cuadro tras la pausa le metio el apagon en el cabezal"


def test_una_pausa_corta_con_audio_entrando_tampoco_mueve_el_cabezal():
    """La pausa de verdad, la del cable enchufado y callado: los cuadros siguen
    llegando, asi que el seguidor no parece "sin audio" y la unica cosa que impide
    que el hueco entre en el cabezal es que al pausar se le congele el reloj.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    publicar(sesion, reloj, suena("E2"), cuadros=10)
    instante = sesion_carril.estado()["instante_s"]

    sesion.senal_ausente = True
    publicar(sesion, reloj, SILENCIO, cuadros=5)  # menos que ESPERA_SIN_CUADROS_S
    sesion.senal_ausente = False
    publicar(sesion, reloj, suena("A2"), cuadros=12)

    despues = sesion_carril.estado()["instante_s"]
    assert despues == pytest.approx(instante + 0.25, abs=0.06)
    sesion_carril.detener()
    sesion.detener()


def test_un_apagon_que_nadie_mira_no_entra_en_la_pieza():
    """El caso peligroso: nadie mira durante el apagon y la vuelta ya trae señal.

    Es lo que pasa con el WebSocket desconectado y el dispositivo desaparecido:
    no hay cuadros (nadie publica) ni consultas de estado (nadie pregunta), asi
    que nadie observa la falta de señal y el carril nunca se entera de que hubo
    pausa. Sin techo, el primer cuadro de la vuelta metia el apagon entero en el
    cabezal: 30 s de apagon eran 30 s de notas dadas por pasadas.

    Que hoy no ocurriera dependia del orden de dos lineas de OTRO modulo
    (`Sesion._publicar` avisa a los observadores antes de anotar el nivel), y esta
    prueba existe para que deje de depender de eso.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    publicar(sesion, reloj, suena("E2"), cuadros=10)
    instante = sesion_carril.estado()["instante_s"]

    reloj.avanzar(30.0)  # apagon: ni un cuadro, ni una mirada
    publicar(sesion, reloj, SILENCIO, cuadros=1)  # y la vuelta ya trae señal

    despues = sesion_carril.estado()["instante_s"]
    assert despues == pytest.approx(instante, abs=0.15)
    sesion_carril.detener()
    sesion.detener()


def test_empezar_sin_el_cable_puesto_y_enchufarlo_treinta_segundos_despues():
    """El caso del principiante: das a empezar, vas a enchufar la guitarra, vuelves.

    Aqui nunca ha llegado un cuadro -el dispositivo no estaba al arrancar- y nadie
    mira -el WebSocket esta desconectado, o el navegador en segundo plano-, asi que
    el reloj no tiene quien lo desmienta... hasta que llega el primer cuadro. Ese
    cuadro ES la desmentida: dice que hasta el no habia audio. Si el tramo que lo
    trae no llevara techo, el cabezal empezaria 30 s dentro de la pieza y el alumno
    fallaria de golpe todas las notas de esos 30 s.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    reloj.avanzar(30.0)  # ni un cuadro, ni una mirada: se estaba enchufando
    publicar(sesion, reloj, suena("E2"), cuadros=1)  # y aparece ya con señal
    assert sesion_carril.estado()["instante_s"] == pytest.approx(0.0, abs=0.15)
    sesion_carril.detener()
    sesion.detener()


def test_la_vuelta_avisada_por_una_consulta_de_estado_tampoco_traga_el_hueco():
    """El tercer camino: tras el hueco, quien avisa primero es el WebSocket.

    `estado()` y `_observar` son dos eventos asincronos sin ningun orden
    garantizado: el WebSocket puede reconectar y preguntar antes de que termine de
    analizarse el primer cuadro del dispositivo recien enchufado. Y ojo, porque lo
    que hace creible ese tramo es que `Sesion.senal_ausente` es False mientras no
    se haya procesado ningun cuadro: al arrancar, el sistema dice "hay señal" sin
    haber oido nada.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    reloj.avanzar(30.0)  # ni cuadros ni miradas: se estaba enchufando el cable
    assert sesion_carril.estado()["instante_s"] == pytest.approx(0.0, abs=0.15)
    # Y el cuadro que llega detras tampoco puede meterlo.
    publicar(sesion, reloj, suena("E2"), cuadros=1)
    assert sesion_carril.estado()["instante_s"] == pytest.approx(0.0, abs=0.15)
    sesion_carril.detener()
    sesion.detener()


def test_tras_un_apagon_da_igual_quien_avise_primero():
    """El mismo hueco que la prueba del apagon, pero avisado por una consulta.

    Con audio ya en marcha y luego parado, el primero en enterarse puede ser el
    WebSocket o el siguiente cuadro. Los dos ordenes tienen que dar lo mismo.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    publicar(sesion, reloj, suena("E2"), cuadros=10)
    instante = sesion_carril.estado()["instante_s"]

    reloj.avanzar(30.0)
    assert sesion_carril.estado()["instante_s"] == pytest.approx(instante, abs=0.15)
    publicar(sesion, reloj, SILENCIO, cuadros=1)
    assert sesion_carril.estado()["instante_s"] == pytest.approx(instante, abs=0.15)
    sesion_carril.detener()
    sesion.detener()


def test_un_hueco_corto_de_audio_no_mueve_el_cabezal_mas_de_lo_acotado():
    """El cuarto camino que queda, acotado y fijado aqui.

    Entre `TECHO_TRAMO_S` (0,1 s) y `ESPERA_SIN_CUADROS_S` (0,25 s) hay una franja
    en la que el reloj de esta clase ya frena pero el del SEGUIDOR todavia no se
    recoloca (recolocarlo le costaria las pulsaciones en vuelo, y en esa franja
    aun puede haber alguna). Asi que un bache de audio de esa duracion entra en el
    cabezal por la via del seguidor, que es quien publica mientras llegan cuadros.

    No es el agujero de los 30 s: esta acotado por `ESPERA_SIN_CUADROS_S`, no por
    lo que dure el corte, porque pasada esa franja la recolocacion lo corta. Esta
    prueba lo fija para que la cota no crezca en silencio.

    OJO con el primer caso, que es de la etapa 3a y NO PODIA FALLAR: el hueco que
    provoca es de 0,2 s y la cota que exige es 0,28, asi que ninguna
    implementacion puede pasarse -hoy el hueco entra entero y pasa, y pasaria
    igual si el cabezal no se moviera nada-. La rotura que deberia matarla (quitar
    el `min(..., TECHO_TRAMO_S)` de `_mirar`) la dejaba verde, medido. De ahi el
    segundo caso, con un hueco de 0,5 s: ahi el techo SI muerde, y son 0,5 s de
    cabezal con la rotura puesta contra 0,1 sin ella.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    # La cuenta atras del plan por defecto va delante y se agota mirando: con ella
    # abierta el reloj de la pieza esta congelado a proposito y esta prueba no
    # mediria nada (ver `agotar_cuenta_atras`).
    agotar_cuenta_atras(sesion_carril, reloj)
    publicar(sesion, reloj, suena("E2"), cuadros=10)
    instante = sesion_carril.estado()["instante_s"]

    reloj.avanzar(0.2)  # bache de audio, por debajo de ESPERA_SIN_CUADROS_S
    publicar(sesion, reloj, SILENCIO, cuadros=1)

    despues = sesion_carril.estado()["instante_s"]
    assert despues - instante <= ESPERA_SIN_CUADROS_S + 0.03

    # Y un hueco mas largo que el techo del tramo: aqui el techo es lo unico que
    # impide que entre entero, asi que la cota es la del techo y no la del hueco.
    antes_del_hueco = sesion_carril.estado()["instante_s"]
    reloj.avanzar(0.5)
    publicar(sesion, reloj, SILENCIO, cuadros=1)
    tras_el_hueco = sesion_carril.estado()["instante_s"]
    assert tras_el_hueco - antes_del_hueco <= TECHO_TRAMO_S + 0.03, (
        "el hueco de 0,5 s entro en la pieza: el techo del tramo no esta mordiendo"
    )
    sesion_carril.detener()
    sesion.detener()


def test_el_margen_sobre_la_cadencia_del_analisis_sigue_siendo_holgado():
    """Fija el acoplamiento entre `ESPERA_SIN_CUADROS_S` y la tasa de analisis.

    Si los cuadros llegaran mas despacio que `ESPERA_SIN_CUADROS_S`, cada mirada
    del WebSocket le moveria el reloj al seguidor a mano y se comeria TODAS las
    pulsaciones: cero notas en toda la pieza, sin un solo mensaje en ningun log. Y
    solo pasaria con un cliente conectado, asi que ninguna prueba de las de arriba
    lo veria. Medido sobre este codigo: a 4,2 cuadros por segundo las notas se
    anotan; a 3,8 no se anota ninguna.

    Hoy el margen es de 12x. Si alguien baja la tasa de analisis, esta prueba cae
    antes que la experiencia del usuario.
    """
    margen = ESPERA_SIN_CUADROS_S / INTERVALO_ANALISIS
    assert margen >= 4, (
        f"Los cuadros llegan cada {INTERVALO_ANALISIS} s y el carril da el audio "
        f"por parado a los {ESPERA_SIN_CUADROS_S} s: margen {margen:.1f}x. Por "
        "debajo de 4x, `SesionCarril.estado()` empieza a invalidar las "
        "pulsaciones en vuelo y el carril deja de anotar notas."
    )


def test_detener_deja_de_alimentar_al_seguidor():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    observador_visto = []
    sesion_carril.iniciar(pieza_de([40]))
    observador_visto.extend(sesion.observadores)
    sesion_carril.detener()
    # El observador ya no esta registrado; llamarlo a mano tampoco puede tocar
    # nada, porque el seguidor se solto.
    for observador in observador_visto:
        observador(suena("E2"), reloj())
    assert sesion_carril.estado()["tocadas"] == []
    sesion.detener()


def test_cada_arranque_tiene_su_etiqueta_y_el_carril_apagado_no_tiene_ninguna():
    """El `arranque` es lo que le dice al navegador de QUE pieza habla un paquete.

    Hace falta porque el WebSocket y la respuesta de `iniciar` son dos canales que
    se cruzan: un paquete emitido antes del arranque puede llegar despues de la
    respuesta. Sin etiqueta, el navegador tenia que adivinar comparando el numero
    de notas, y dos piezas del mismo tamaño -tocar dos veces la misma escala- se
    confundian: salia el resumen de la anterior sobre la nueva.

    De ahi las tres cosas que se comprueban: que sube en cada arranque, que nunca
    se repite aunque las dos piezas sean iguales, y que un carril sin pieza
    publica una etiqueta que no es de nadie.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)

    assert sesion_carril.estado()["arranque"] == ARRANQUE_NINGUNO

    primera = sesion_carril.iniciar(pieza_de([40, 45, 50]))
    assert primera["arranque"] != ARRANQUE_NINGUNO
    assert sesion_carril.estado()["arranque"] == primera["arranque"]

    # La misma pieza otra vez: el tamaño no distingue nada, la etiqueta si.
    segunda = sesion_carril.iniciar(pieza_de([40, 45, 50]))
    assert segunda["arranque"] != primera["arranque"]
    assert segunda["total"] == primera["total"]

    sesion_carril.detener()
    assert sesion_carril.estado()["arranque"] == ARRANQUE_NINGUNO
    sesion.detener()


def test_con_la_captura_cerrada_el_carril_no_corre():
    """Arrancar sin el cable (o sin permiso de microfono): la sesion reintenta sin
    publicar nada, `senal_ausente` nunca se activa y el carril corria nueve
    segundos fallando la pieza entera sin que el alumno oyera nada."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion.activa = False
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    assert sesion.senal_ausente is False

    estado = avanzar_mirando(sesion_carril, reloj, 9.0)
    assert estado["instante_s"] == pytest.approx(0.0, abs=0.001)
    assert estado["indice_actual"] == 0
    assert estado["pausado"] is True
    # Y la cuenta atras del plan sigue entera: sin captura no hay nada que contar,
    # y gastarla esperando dejaria al alumno sin aviso justo cuando enchufa.
    assert estado["cuenta_atras_restante_s"] == pytest.approx(4.0)

    # Al abrirse la captura el carril arranca desde donde estaba, sin saltos
    # (despues de la cuenta atras, que es lo que se oye al enchufar).
    sesion.activa = True
    agotar_cuenta_atras(sesion_carril, reloj)
    estado = avanzar_mirando(sesion_carril, reloj, 0.5)
    assert estado["pausado"] is False
    assert estado["instante_s"] == pytest.approx(0.5, abs=0.001)
    sesion_carril.detener()
    sesion.detener()


def test_con_una_sesion_real_sin_captura_el_carril_esta_pausado():
    """Lo mismo con la `Sesion` de verdad, sin arrancar: no hay captura abierta."""
    from servidor.sesion import Sesion

    reloj = RelojFalso()
    real = Sesion(Configuracion())
    assert real.activa is False
    sesion_carril = SesionCarril(real, reloj=reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    estado = avanzar_mirando(sesion_carril, reloj, 9.0)
    assert estado["pausado"] is True
    assert estado["instante_s"] == pytest.approx(0.0, abs=0.001)
    sesion_carril.detener()


def test_los_cuadros_con_la_captura_cerrada_pausan_sin_esperar_a_una_consulta():
    """La guarda de `_observar`, sola: no se llama a `estado()` entre medias, que
    es la otra mitad que mira la captura y taparia su ausencia."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    sesion.activa = False
    reloj.avanzar(0.05)
    publicar(sesion, reloj, SILENCIO, cuadros=3)
    assert sesion_carril._pausado is True
    assert sesion_carril._instante == pytest.approx(0.0, abs=1e-9)
    sesion_carril.detener()
    sesion.detener()


def test_desenchufar_con_el_carril_en_marcha_lo_pausa_por_captura_cerrada():
    """Con la `Sesion` de verdad: el dispositivo desaparece, ella cierra la
    captura en su siguiente revision y el carril se pausa por eso -la regla de
    captura cerrada-, no por los 5 s de `senal_ausente`, que sigue en falso."""
    import time

    from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
    from servidor.sesion import Sesion
    from tests.test_sesion import CapturaFalsa

    cable = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
    conectados = [cable]
    real = Sesion(
        Configuracion(),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: list(conectados),
    )
    real.intervalo_revision = 0.05
    real.iniciar()
    sesion_carril = SesionCarril(real)
    try:
        sesion_carril.iniciar(pieza_de([40, 45, 50]))
        assert real.activa is True
        assert sesion_carril.estado()["pausado"] is False

        conectados.clear()
        limite = time.monotonic() + 3.0
        while not sesion_carril.estado()["pausado"] and time.monotonic() < limite:
            time.sleep(0.01)
        assert sesion_carril.estado()["pausado"] is True
        assert real.senal_ausente is False
    finally:
        sesion_carril.detener()
        real.detener()


def test_las_constantes_del_reloj_se_siguen_leyendo_del_servidor():
    """Se mudaron al nucleo en la etapa 3d y aqui se leen donde estaban.

    Este archivo las importa de `servidor.piezas` desde la etapa 3a y las usa en
    media docena de pruebas: reexportarlas es lo que impide que un cambio de
    domicilio rompa a quien las lea, y esta prueba es lo que impide que la
    reexportacion se caiga sin que nadie se entere.
    """
    assert TECHO_TRAMO_S is TECHO_DEL_NUCLEO
    assert ESPERA_SIN_CUADROS_S is ESPERA_DEL_NUCLEO


def candado_tomado(candado) -> bool:
    """Si ese candado esta tomado ahora mismo. No espera a nadie.

    Se pregunta desde OTRO hilo a proposito: un `RLock` se deja tomar otra vez
    por el hilo que ya lo tiene, asi que preguntarselo desde el hilo que lo tomo
    diria siempre "libre" y la prueba no comprobaria nada.
    """
    ajeno = []

    def intentar():
        tomado = candado.acquire(blocking=False)
        ajeno.append(not tomado)
        if tomado:
            candado.release()

    hilo = threading.Thread(target=intentar)
    hilo.start()
    hilo.join()
    return ajeno[0]


def test_el_oyente_del_click_toma_el_candado_del_carril():
    """El oyente del click se protege a si mismo, venga el aviso de donde venga.

    `_ajustar_click` lee y escribe `_metronomo`, `_clave_del_click` y `_pausado`,
    que son de esta clase y los lee el hilo HTTP. Cuando el aviso de la vuelta
    llegaba desde `estado()`, el candado estaba tomado por casualidad -lo tenia
    ese hilo-, y eso bastaba mientras el carril fuera el unico que conducia la
    pasada. Ya no lo es: el gemelo digital conduce `ConductorDeEstudio.mirar`
    directamente, sin ningun candado de este servidor por encima, y el conductor
    avisa con el suyo SUELTO a proposito (si avisara con el tomado, un oyente que
    tomara este invertiria el orden de las tomas y plantaria el servidor). Por ese
    camino el oyente se quedaba sin exclusion ninguna.

    Se comprueba en dos mitades, porque son dos cosas que pueden romperse por
    separado: que lo que el conductor tiene enganchado es la version que toma el
    candado, y que esa version lo toma de verdad. Mira dos campos privados -el
    oyente del conductor y el candado del carril- porque el contrato es
    justamente interno: si se comprobara solo por fuera, volveria a cumplirse por
    casualidad, que es lo que esta prueba existe para impedir.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    estado_inicial = sesion_carril.iniciar(
        pieza_de([40, 41, 42, 43]),
        PlanDePasada(en_bucle=True, compases_de_cuenta_atras=0),
    )
    assert estado_inicial["repeticion"] == 1
    try:
        conductor = sesion_carril._conductor
        # Mitad 1: el enganche. `__func__` porque lo enganchado es un metodo ya
        # ligado a esta instancia.
        assert (
            conductor._al_cambiar_repeticion.__func__
            is SesionCarril._ajustar_click_bajo_candado
        )
        # Mitad 2: la exclusion. Se llama al oyente como lo llamaria el conductor
        # -desde un hilo sin ningun candado de este servidor tomado, que es el
        # caso del gemelo- y se mira desde dentro si el candado esta tomado.
        tomado = []
        sesion_carril._ajustar_click = lambda estado: tomado.append(
            candado_tomado(sesion_carril._candado)
        )
        assert candado_tomado(sesion_carril._candado) is False, (
            "nadie deberia tener el candado antes del aviso"
        )
        conductor._al_cambiar_repeticion(sesion_carril._estudio.estado)
        assert tomado == [True]
    finally:
        sesion_carril.detener()
        sesion.detener()


# -- el resumen de fin de pieza no se contradice con su propio informe -------


def terminar_la_pasada(sesion_carril, reloj, tope_s=30.0):
    """Mira hasta que el carril publica `completado`. Devuelve el estado.

    Mirando y no tocando el nucleo por detras: el final del tramo lo decide el
    reloj de la pasada, y el reloj de la pasada lo mueve la mirada. Despues del
    ultimo cuadro de audio el conductor no mueve nada hasta que pasan
    `ESPERA_SIN_CUADROS_S` (es su invariante: con cuadros recientes, mover el
    reloj a mano le costaria pulsaciones al seguidor), asi que el tope es generoso
    a proposito; ninguna de esas esperas es real, las da el reloj falso.
    """
    mirado = 0.0
    while mirado < tope_s:
        estado = avanzar_mirando(sesion_carril, reloj, 0.5)
        mirado += 0.5
        if estado["completado"]:
            return estado
    raise AssertionError("la pasada no llego a completarse")


def test_al_acabar_la_pieza_el_estado_sigue_diciendo_lo_que_se_toco():
    """El numero grande de «Pieza terminada» y la tabla del informe, de acuerdo.

    Era el defecto: el estado publicado salia con `tocadas` VACIA en cuanto la
    pasada se completaba, asi que la pantalla titulaba «0 de 48 notas acertadas»
    tres centimetros por encima de un informe por compases que sumaba 31. La causa
    es que las dos cifras salian de dos acumuladores distintos y el que alimenta el
    numero grande se vacia justo al terminar: el conductor cierra el tramo con
    `cerrar_repeticion`, cuyo ultimo acto es `olvidar_tramo` sobre la pieza entera,
    y eso poda las `NotaTocada` del seguidor en el MISMO cuadro en que
    `completado` se enciende.

    Se mide la concordancia y no una cifra suelta: «0 de 48» junto a una tabla con
    31 aciertos es una contradiccion en pantalla, y lo que hay que vigilar es que
    los dos numeros digan lo mismo.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    # Las cuatro notas LLENAN el compas, y eso es parte del caso: con una pieza
    # mas corta que su compas el reloj llega al final de la PIEZA antes que al del
    # TRAMO, y entonces no hay cierre de tramo que vacie nada. Lo que el usuario
    # vio en pantalla es una pieza de doce compases con sus cuatro notas cada uno.
    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]), PlanDePasada(compases_de_cuenta_atras=0)
    )
    publicar(sesion, reloj, suena("E2"), cuadros=12)
    assert len(sesion_carril.estado()["tocadas"]) == 1

    terminar_la_pasada(sesion_carril, reloj)
    # Y se mira OTRA VEZ, que es lo que hace la pantalla: el WebSocket sigue
    # pidiendo el estado 30 veces por segundo despues del final. El cuadro en que
    # `completado` se enciende se publica ANTES de que el conductor cierre el tramo
    # (`ConductorDeEstudio.mirar` devuelve el estado leido antes del cierre), asi
    # que el que el usuario tiene delante es cualquiera de los siguientes.
    estado = sesion_carril.estado()
    assert estado["completado"] is True

    en_pantalla = sum(1 for t in estado["tocadas"] if t["acertada"])
    en_el_informe = sum(
        c["acertadas"] for c in sesion_carril.informe()["informe"]["compases"]
    )
    assert en_el_informe == 1, "la tabla por compases es la que ya decia la verdad"
    assert en_pantalla == en_el_informe
    sesion_carril.detener()
    sesion.detener()

# -- no se acusa al cable cuando la sesion no espera notas -------------------


def test_sin_pasada_en_marcha_se_espera_que_el_usuario_toque():
    """El caso legitimo del aviso: nadie esta tocando una pieza, pero el usuario
    puede estar en el afinador intentando que suene algo. Ahi callarse seria
    esconder el unico aviso que le explicaria por que no ve nada."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    assert sesion_carril.esperando_notas is True
    sesion.detener()


def test_con_la_pieza_en_marcha_se_esperan_notas_y_al_acabar_ya_no():
    """La distincion es por ESTADO DE LA SESION y no por un temporizador.

    Mientras la pasada corre, el silencio del cable es un problema y el aviso es
    cierto. En cuanto la pieza termina, la sesion no espera que nadie toque: el
    usuario acaba la pasada, deja de tocar, y acusar entonces al cable es decirle
    que suba el volumen de una guitarra que esta perfectamente bien.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]), PlanDePasada(compases_de_cuenta_atras=0)
    )
    assert sesion_carril.esperando_notas is True

    terminar_la_pasada(sesion_carril, reloj)
    assert sesion_carril.esperando_notas is False

    sesion_carril.detener()
    sesion.detener()


def test_en_la_pausa_del_usuario_se_siguen_esperando_notas_si_nunca_llego_senal():
    """**La pausa NO calla el aviso, y callarla era un defecto medido.**

    Esta prueba afirmaba lo contrario -«la pausa la pidio el usuario, el silencio
    es lo que pidio»- y es el argumento equivocado: el usuario que pausa porque no
    le marca nada es exactamente quien necesita leer que no llega señal. Es el
    mismo argumento con el que `esperando_notas` se queda en True sin pasada en
    marcha («puede estar en el afinador peleandose con el jack»), y la otra mitad
    del aviso -la linea naranja del carril- SI salia en pausa, asi que las dos
    mitades decian lo contrario a la vez.

    Lo que calla el aviso no es quien pidio el silencio: es que el cable ya haya
    demostrado en esta pasada que funciona. Ver `se_esperan_notas`.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]), PlanDePasada(compases_de_cuenta_atras=0)
    )
    sesion_carril.pausa(True)
    sesion.senal_ausente = True
    avanzar_mirando(sesion_carril, reloj, 1.0)

    assert sesion_carril.estado()["pausado"] is True
    assert sesion_carril.esperando_notas is True, (
        "nunca llego señal en esta pasada: el aviso es el unico que le explica "
        "por que no ve nada, y es justo lo que fue a investigar pausando"
    )
    assert sesion_carril.estado()["esperando_notas"] is True

    sesion_carril.detener()
    sesion.detener()


def test_en_un_bucle_el_descanso_entre_vueltas_no_acusa_al_cable():
    """**EL DEFECTO QUE EL REVISOR MIDIO EN EL USO CENTRAL DE LA ETAPA 3C.**

    Medido con el escaparate en `--bucle 2-2 --repeticiones 2`: a los 12,2 s
    `pausado=True` y el diagnostico decia `sin_senal`, o sea «sube el volumen de
    la guitarra» de una guitarra que estaba perfectamente bien. La causa: un tramo
    en bucle NO publica nunca `completado` ni `tramo_terminado` -el bucle no se
    acaba, es su proposito-, asi que la regla de «con la pieza terminada no se
    esperan notas» no muerde nunca y el aviso volvia entero. El commit que
    arreglo el caso sin bucle lo dejo intacto en el caso con bucle, que es como el
    usuario practica: machacar el compas que falla, y descansar la mano entre
    repeticiones.

    La regla que lo cierra no mira si la pasada acabo, que en un bucle no acaba
    nunca: mira si **el cable ya entrego señal en esta pasada**. Si entrego,
    «sube el volumen» es falso y el aviso calla; si no entrego nunca, el aviso es
    el caso legitimo y sigue saliendo (prueba de arriba).
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]),
        PlanDePasada(en_bucle=True, compases_de_cuenta_atras=0),
    )
    # Toca de verdad un par de segundos: el cable entrega señal.
    publicar(sesion, reloj, suena("E2"), cuadros=20)
    avanzar_mirando(sesion_carril, reloj, 0.5)
    assert sesion_carril.esperando_notas is True, "tocando si se esperan notas"

    # Y descansa la mano. A los 5 s sin señal el carril se congela.
    sesion.senal_ausente = True
    estado = avanzar_mirando(sesion_carril, reloj, 7.0)

    assert estado["en_bucle"] is True
    assert estado["completado"] is False, "un bucle no se acaba: es su proposito"
    assert estado["tramo_terminado"] is False
    assert estado["pausado"] is True, "el carril si esta congelado, y lo dice"
    assert sesion_carril.esperando_notas is False, (
        "el cable entrego señal hace un momento: acusarlo ahora es decirle que "
        "suba el volumen de una guitarra que esta bien"
    )
    assert estado["esperando_notas"] is False

    sesion_carril.detener()
    sesion.detener()


def test_los_cuadros_de_silencio_no_cuentan_como_cable_que_entrego():
    """**UN MUTANTE SUPERVIVIENTE, y era el defecto que mas cerca estuvo de colarse.**

    Lo que calla el aviso es que el cable haya entregado señal en esta pasada, y
    ese hecho se deduce DEL CUADRO: un cuadro con nivel por encima del umbral de
    ruido. La tentacion es deducirlo de `senal_ausente` -«no falta señal, luego
    hay señal»- y es falso, porque `senal_ausente` es «cinco segundos seguidos por
    debajo del umbral»: durante los cinco primeros segundos de CUALQUIER pasada es
    falso, tambien de una en la que no llegue nunca nada. Con esa version, el
    aviso se callaba justo en el caso legitimo.

    Aqui los cuadros SI llegan -el cable esta abierto y publicando- pero traen
    silencio a -90 dBFS, muy por debajo del umbral. Eso no es el cable
    entregando: es el cable callado, que es el caso que el aviso existe para
    nombrar.

    El mutante que esto mata: `_cuadro_con_senal` devolviendo `True` siempre.
    Sobrevivia a la suite entera.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]), PlanDePasada(compases_de_cuenta_atras=0)
    )

    publicar(sesion, reloj, SILENCIO, cuadros=60)
    sesion.senal_ausente = True
    estado = avanzar_mirando(sesion_carril, reloj, 7.0)

    assert estado["pausado"] is True
    assert sesion_carril.esperando_notas is True, (
        "llegaron sesenta cuadros y ninguno traia señal: el cable no ha entregado "
        "nada en esta pasada y el aviso es el caso legitimo"
    )
    assert estado["esperando_notas"] is True

    sesion_carril.detener()
    sesion.detener()


def test_lo_que_entrego_el_cable_en_la_pasada_anterior_no_calla_la_nueva():
    """**OTRO MUTANTE SUPERVIVIENTE: el hecho es DE LA PASADA, no de la sesion.**

    Si «el cable entrego señal» se quedara puesto de una pasada para la siguiente,
    el usuario que toca una pieza, la termina, desenchufa y empieza otra se
    quedaria sin el aviso justo cuando lo necesita, porque su pasada anterior
    habia ido bien. Se borra al arrancar y al parar.

    El mutante que esto mata: quitar `self._hubo_senal = False` de `iniciar`.
    Sobrevivia a la suite entera.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)

    # Primera pasada: se toca de verdad y el aviso se calla al descansar.
    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]), PlanDePasada(compases_de_cuenta_atras=0)
    )
    publicar(sesion, reloj, suena("E2"), cuadros=20)
    sesion.senal_ausente = True
    avanzar_mirando(sesion_carril, reloj, 7.0)
    assert sesion_carril.esperando_notas is False

    # Segunda pasada, sin una sola muestra: el aviso vuelve.
    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]), PlanDePasada(compases_de_cuenta_atras=0)
    )
    estado = avanzar_mirando(sesion_carril, reloj, 7.0)

    assert estado["pausado"] is True
    assert sesion_carril.esperando_notas is True, (
        "lo que el cable entrego en la pasada anterior no dice nada de esta"
    )

    sesion_carril.detener()
    sesion.detener()


def test_la_regla_del_aviso_se_decide_una_vez_y_las_dos_mitades_la_leen():
    """**LA COSTURA: el panel de diagnostico y el carril leen el MISMO dato.**

    La regla vivia escrita dos veces -tres clausulas en Python
    (`tramo_terminado`, `carril.completado`, `en_pausa`) y una en TypeScript
    (`!completado`)-, no eran la misma, y un comentario del JSX afirmaba que si.
    Cada mitad tenia su mutante y cada mutante moria en su propio idioma, lo que
    daba la sensacion de estar cubierto. El resultado medible era que en la pausa
    del usuario el diagnostico callaba y el carril acusaba al cable.

    Ahora la regla se decide en `se_esperan_notas` y viaja PUBLICADA en el estado,
    asi que las dos mitades no pueden discrepar: la propiedad que lee
    `/api/diagnostico` y el campo que lee el carril salen de la misma llamada.
    Esto cruza la costura por el lado de Python; por el de TypeScript la cruza
    `Carril.test.tsx`, que dibuja la linea naranja solo con el campo publicado, y
    `test_la_interfaz_no_recalcula_la_regla_del_aviso`, que comprueba que el JSX no
    se la vuelve a inventar.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)

    # Sin pasada: el afinador. Las dos mitades dicen que si.
    assert sesion_carril.esperando_notas is True
    assert sesion_carril.estado()["esperando_notas"] is True

    sesion_carril.iniciar(
        pieza_de([40, 45, 50, 55]), PlanDePasada(compases_de_cuenta_atras=0)
    )
    for paso in ("recien empezada", "en pausa", "sin señal tras tocar", "terminada"):
        if paso == "en pausa":
            sesion_carril.pausa(True)
            sesion_carril.pausa(False)
        elif paso == "sin señal tras tocar":
            publicar(sesion, reloj, suena("E2"), cuadros=20)
            sesion.senal_ausente = True
            avanzar_mirando(sesion_carril, reloj, 7.0)
        elif paso == "terminada":
            sesion.senal_ausente = False
            terminar_la_pasada(sesion_carril, reloj)
        estado = sesion_carril.estado()
        assert estado["esperando_notas"] is sesion_carril.esperando_notas, (
            f"las dos mitades discrepan con la pasada {paso}: el panel de "
            "diagnostico y el carril tienen que leer la misma regla"
        )

    sesion_carril.detener()
    sesion.detener()


def test_la_interfaz_no_recalcula_la_regla_del_aviso():
    """El JSX LEE `esperando_notas`; no se vuelve a inventar la regla.

    Es la otra mitad de la costura, afirmada desde aqui porque es el unico sitio
    donde se puede comparar con la regla de Python. Un comentario que dijera «es la
    misma regla» es exactamente lo que habia antes, y era falso.
    """
    jsx = (
        pathlib.Path(__file__).resolve().parents[1] / "interfaz" / "src" / "Carril.tsx"
    ).read_text(encoding="utf-8")
    # La condicion de la linea naranja: lo que hay entre la llave que la abre y el
    # parrafo que la dibuja.
    corte = jsx.index("Carril pausado")
    condicion = jsx[jsx.rindex("{estado", 0, corte) : corte]

    assert "esperando_notas" in condicion, (
        "la linea del cable tiene que decidirse con el campo PUBLICADO: "
        f"la condicion de hoy es {condicion!r}"
    )
    assert "completado" not in condicion, (
        "y no recalculando la regla aqui, que es lo que hacia que las dos mitades "
        "no fueran la misma"
    )


def test_una_pieza_que_acaba_antes_de_su_barra_de_compas_tampoco_espera_notas():
    """`completado` tiene DOS motivos, y los dos valen para callar el aviso.

    Lo delato un mutante que sobrevivio: mirando solo `tramo_terminado` la prueba
    de arriba pasaba igual, porque su pieza llena el compas y los dos motivos se
    encienden a la vez. Una pieza cuyas notas se acaban ANTES de la barra -dos
    notas en un compas de 4/4- termina por el otro: el reloj pasa el final de la
    PIEZA (`carril.completado`) y se sigue moviendo hasta el final del TRAMO. En
    esos segundos la pantalla ya dice «Pieza terminada» -lo publicado es
    `tramo_terminado or carril.completado`- y el aviso naranja volvia a acusar al
    cable de un silencio que nadie podia evitar.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    # Dos notas en un compas de 4/4 a 60 ppm: la pieza dura 2 s y el tramo, 4.
    sesion_carril.iniciar(pieza_de([40, 45]), PlanDePasada(compases_de_cuenta_atras=0))
    estado = avanzar_mirando(sesion_carril, reloj, 2.5)

    assert estado["completado"] is True, "la pieza se acabo"
    assert estado["tramo_terminado"] is False, "el tramo todavia no"
    assert sesion_carril.esperando_notas is False

    sesion_carril.detener()
    sesion.detener()
