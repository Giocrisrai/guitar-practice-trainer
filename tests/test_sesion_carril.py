"""La sesion del carril: el reloj lo lleva el servidor y el audio lo alimenta.

Ni una espera real en todo el archivo: el reloj se inyecta y las pruebas lo mueven
a mano. Tampoco se abre ningun dispositivo de audio: la sesion de audio es un
doble con las tres cosas que `SesionCarril` le pide.
"""

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from servidor.configuracion import Configuracion
from servidor.piezas import SesionCarril


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


def publicar(sesion, reloj, resultado, cuadros=1, paso=0.021):
    """Publica cuadros de analisis como lo haria la sesion de audio de verdad.

    El instante que acompaña a cada cuadro es el del reloj del ANALISIS, que en
    produccion es `time.monotonic()`; aqui es el mismo reloj falso, que es lo que
    hace el servidor real (los dos son el reloj monotonico de la maquina).
    """
    for _ in range(cuadros):
        for observador in list(sesion.observadores):
            observador(resultado, reloj())
        reloj.avanzar(paso)


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
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45]))
    assert sesion_carril.estado()["instante_s"] == 0.0
    reloj.avanzar(1.4)
    assert sesion_carril.estado()["instante_s"] == 1.4
    assert sesion_carril.estado()["indice_actual"] == 1
    sesion_carril.detener()
    sesion.detener()


def test_sin_senal_el_carril_se_detiene_y_al_volver_sigue_donde_estaba():
    """Un carril que corre con el cable desenchufado te hace fallar notas que
    nunca sonaron."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    reloj.avanzar(1.0)
    assert sesion_carril.estado()["instante_s"] == 1.0

    sesion.senal_ausente = True
    reloj.avanzar(5.0)
    assert sesion_carril.estado()["instante_s"] == 1.0
    assert sesion_carril.estado()["pausado"] is True

    sesion.senal_ausente = False
    reloj.avanzar(0.5)
    assert sesion_carril.estado()["instante_s"] == 1.5
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


def test_detener_dos_veces_no_falla():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40]))
    sesion_carril.detener()
    sesion_carril.detener()
    sesion.detener()


def test_lo_que_oye_el_cable_llega_al_seguidor():
    """La otra mitad del trabajo: sin esto el carril seria un reloj con pantalla.

    Se toca la nota que vive en el segundo 0.0 de la pieza (MIDI 40 = "E2") y se
    comprueba que sale anotada como acertada.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45]))
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
    """Sin mirar el estado en medio: la pausa tiene que bastarse sola.

    Mientras entra audio, el reloj del carril lo lleva el SEGUIDOR (cuadro a
    cuadro), asi que pausar sin congelarselo deja su origen viejo, y el primer
    cuadro de la vuelta lo coloca tantos segundos dentro de la pieza como haya
    durado la pausa. `estado()` lo tapa cuando alguien lo llama -mueve el reloj a
    mano en cuanto los cuadros se quedan viejos-, y por eso esta prueba no lo
    llama hasta el final: sin cliente de WebSocket conectado nadie lo llamaria.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    publicar(sesion, reloj, SILENCIO, cuadros=10)
    sesion.senal_ausente = True
    publicar(sesion, reloj, SILENCIO, cuadros=100)
    sesion.senal_ausente = False
    publicar(sesion, reloj, SILENCIO, cuadros=12)
    assert sesion_carril.estado()["instante_s"] == pytest.approx(0.21 + 0.25, abs=0.1)


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
