"""La sesion del carril: el reloj lo lleva el servidor y el audio lo alimenta.

Ni una espera real en todo el archivo: el reloj se inyecta y las pruebas lo mueven
a mano. Tampoco se abre ningun dispositivo de audio: la sesion de audio es un
doble con las tres cosas que `SesionCarril` le pide.
"""

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from servidor.configuracion import Configuracion
from servidor.piezas import ESPERA_SIN_CUADROS_S, SesionCarril
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
    sesion_carril.iniciar(pieza_de([40, 45]))
    assert sesion_carril.estado()["instante_s"] == 0.0
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
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
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


def test_una_pausa_corta_con_audio_entrando_tampoco_mueve_el_cabezal():
    """La pausa de verdad, la del cable enchufado y callado: los cuadros siguen
    llegando, asi que el seguidor no parece "sin audio" y la unica cosa que impide
    que el hueco entre en el cabezal es que al pausar se le congele el reloj.
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
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
    """
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    publicar(sesion, reloj, suena("E2"), cuadros=10)
    instante = sesion_carril.estado()["instante_s"]

    reloj.avanzar(0.2)  # bache de audio, por debajo de ESPERA_SIN_CUADROS_S
    publicar(sesion, reloj, SILENCIO, cuadros=1)

    despues = sesion_carril.estado()["instante_s"]
    assert despues - instante <= ESPERA_SIN_CUADROS_S + 0.03
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
