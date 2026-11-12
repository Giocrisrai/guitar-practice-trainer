"""El acompañamiento cableado al carril: su puerta, su salida y su candado.

Lo que esta etapa añade al carril es la pieza de fondo sonando mientras el
usuario toca, y lo que estas pruebas vigilan son las cuatro decisiones que lo
gobiernan:

1. **El fondo entra por una puerta PROPIA.** `iniciar(pieza, plan)` es la puerta
   unica del carril y no cambia de firma: se comprueba con `inspect.signature`.
2. **La salida de audio es PROPIA, no la del click.** `_parar_click` cierra la
   suya sin condiciones treinta veces por segundo.
3. **Ni el interruptor ni el volumen viven en `PlanDePasada`**, porque todo
   cambio de plan cierra la repeticion.
4. **La regla «la entrada es el cable» se decide UNA vez** -en
   `Sesion.entrada_es_el_cable`- y viaja publicada, igual que
   `se_esperan_notas`.

Y, por encima de todas, **el candado**: la clausura que le da el cabezal al
acompañante lo intenta sin bloquear y lanza `BloqueadoAhora` si esta ocupado. El
hilo de audio la llama cada 21 ms; si espera ahi, se oye.

Ni un `time.sleep` para sincronizar con hilos: el reloj es falso y lo mueven las
pruebas, el render se espera con un `join` sobre el hilo que lo hace y las
escrituras con un `Condition` que levanta el propio stream. Toda la salida va
por `SalidaCapturada`: el sandbox no puede abrir audio.

Ninguna asercion toma su valor de referencia del camino que prueba: los pulsos
esperados se calculan a mano desde el tempo y el reloj, y las muestras
esperadas se renderizan aparte en la prueba, nunca preguntandole al carril por
lo que acaba de hacer.
"""

import inspect
import pathlib
import threading

import numpy as np
import pytest

from nucleo.acompanamiento import renderizar
from nucleo.acompanante import BloqueadoAhora
from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.gemelo.salida import SalidaCapturada, StreamCapturado
from nucleo.piezas.estudio import PlanDePasada
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from nucleo.piezas.voces_de_fondo import FondoDisponible, NotaDeFondo, VozDeFondo
from servidor.piezas import GANANCIA_DE_TU_PARTE, SesionCarril

# Nada en este archivo espera de verdad salvo cuando algo ha fallado: los
# limites son el tope que convierte un cuelgue en un rojo.
LIMITE_S = 10.0
MUESTREO = 48000
TEMPO = 60
BLOQUE = 1024


class RelojFalso:
    """Reloj que solo avanza cuando se le dice."""

    def __init__(self):
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


class SesionAudioFalsa:
    """Doble de `Sesion` con lo que `SesionCarril` le pide, cable incluido.

    `entrada_es_el_cable` es el cuarto miembro de la frontera y se puede mover
    desde la prueba: en la sesion de verdad lo decide `_abrir_captura` mirando el
    dispositivo que abrio, y aqui lo decide la prueba, que es lo que permite
    comprobar que el carril lo LEE en vez de volver a calcularlo.
    """

    def __init__(self, entrada_es_el_cable: bool = True):
        self.senal_ausente = False
        self.entrada_es_el_cable = entrada_es_el_cable
        self.observadores = []

    def registrar_observador(self, observador):
        self.observadores.append(observador)

    def quitar_observador(self, observador):
        if observador in self.observadores:
            self.observadores.remove(observador)

    def detener(self) -> None:
        self.observadores.clear()


class StreamQueCuenta(StreamCapturado):
    """`StreamCapturado` que avisa cuando ya lleva `n` escrituras.

    Es lo que sustituye a dormir un rato: la prueba espera en un `Condition` que
    el propio stream levanta al escribir, asi que no hay ni una espera que
    dependa de lo rapido que vaya la maquina.
    """

    def __init__(self, **argumentos) -> None:
        super().__init__(**argumentos)
        self._condicion = threading.Condition()
        self.escrituras = 0

    def write(self, muestras) -> None:
        super().write(muestras)
        with self._condicion:
            self.escrituras += 1
            self._condicion.notify_all()

    def esperar_escrituras(self, cuantas: int, limite: float = LIMITE_S) -> bool:
        with self._condicion:
            return self._condicion.wait_for(
                lambda: self.escrituras >= cuantas, timeout=limite
            )


class SalidaQueCuenta(SalidaCapturada):
    """`SalidaCapturada` cuyo stream avisa de cada escritura."""

    def __init__(self, **argumentos) -> None:
        super().__init__(**argumentos)
        self._stream = StreamQueCuenta()

    def esperar_escrituras(self, cuantas: int, limite: float = LIMITE_S) -> bool:
        return self._stream.esperar_escrituras(cuantas, limite)

    @property
    def escrituras(self) -> int:
        return self._stream.escrituras


class RenderContado:
    """`renderizar` sustituido: hace el de verdad y cuenta cuantas veces.

    Cuenta al ENTRAR, que es lo que mide la pregunta «cuantas veces se
    sintetiza»; quien necesite ademas el buffer entregado espera al hilo con
    `esperar_el_render`.
    """

    def __init__(self) -> None:
        self.llamadas = 0
        self.factores: list[float] = []
        self._condicion = threading.Condition()

    def __call__(self, voces, **argumentos):
        with self._condicion:
            self.llamadas += 1
            self.factores.append(argumentos.get("factor_tempo", 1.0))
            self._condicion.notify_all()
        return renderizar(voces, **argumentos)

    def esperar_llamadas(self, cuantas: int, limite: float = LIMITE_S) -> bool:
        with self._condicion:
            return self._condicion.wait_for(
                lambda: self.llamadas >= cuantas, timeout=limite
            )


def pieza_de(midis, tempo=TEMPO):
    notas = tuple(
        NotaEnPieza(
            midi=m, cuerda=6, traste=i, inicio_pulsos=float(i), duracion_pulsos=1.0
        )
        for i, m in enumerate(midis)
    )
    return Pieza(
        nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas
    )


def voz_de(midis, nombre="Bajo"):
    return VozDeFondo(
        nombre=nombre,
        instrumento="Bass",
        notas=tuple(
            NotaDeFondo(midi=float(m), inicio_pulsos=float(i), duracion_pulsos=1.0)
            for i, m in enumerate(midis)
        ),
    )


def fondo_de(midis=(40, 45, 50, 55), tempo=TEMPO):
    """Un `FondoDisponible` con una voz. Sin `midis`, un fondo SIN voces."""
    voces = (voz_de(midis),) if midis else ()
    return FondoDisponible(voces=voces, tempo=tempo, excluidas=())


SIN_CUENTA = PlanDePasada(compases_de_cuenta_atras=0)


def carril(reloj, entrada_es_el_cable=True, **argumentos):
    """Un carril con dos salidas capturadas distintas: la del click y la del fondo.

    Distintas a proposito y no por comodidad: que sean dos es justo lo que estas
    pruebas tienen que poder mirar por separado.
    """
    sesion = SesionAudioFalsa(entrada_es_el_cable=entrada_es_el_cable)
    argumentos.setdefault("salida", SalidaCapturada(frecuencia_muestreo=MUESTREO))
    argumentos.setdefault("salida_fondo", SalidaQueCuenta(frecuencia_muestreo=MUESTREO))
    captura_click = argumentos["salida"]
    captura_fondo = argumentos["salida_fondo"]
    sesion_carril = SesionCarril(
        sesion,
        reloj=reloj,
        salida=captura_click.salida,
        salida_fondo=captura_fondo.salida,
    )
    return sesion_carril, sesion, captura_fondo, captura_click


def avanzar_mirando(sesion_carril, reloj, segundos, paso=1 / 30.0):
    """Mueve el reloj en pasos de 30 Hz, mirando el estado en cada uno."""
    restante = segundos
    estado = sesion_carril.estado()
    while restante > 1e-9:
        este = min(paso, restante)
        reloj.avanzar(este)
        estado = sesion_carril.estado()
        restante -= este
    return estado


def esperar_el_render(sesion_carril, limite=LIMITE_S) -> None:
    """Espera al hilo que sintetiza. Con `join`, no durmiendo."""
    hilo = sesion_carril._hilo_del_render
    assert hilo is not None, "nadie mando renderizar nada"
    hilo.join(timeout=limite)
    assert not hilo.is_alive(), "el render no termino"


def muestra_del_pulso(pulso, tempo=TEMPO, factor_tempo=1.0, muestreo=MUESTREO) -> int:
    """El indice de muestra de un pulso, A MANO.

    Escrita aqui igual que en `test_acompanante.py`: preguntarle a `rodaja`
    donde empieza el bloque seria comparar el mapa consigo mismo.
    """
    return int(round(pulso * 60.0 / (tempo * factor_tempo) * muestreo))


SILENCIO = ResultadoAnalisis(
    estado="silencio",
    frecuencia=None,
    confianza=0.0,
    nivel_db=-90.0,
    nota=None,
    cents=None,
    posiciones=(),
)


def cerrar(sesion_carril, sesion) -> None:
    sesion_carril.detener()
    sesion.detener()


# --------------------------------------------------------------------------
# La puerta
# --------------------------------------------------------------------------


def test_cargar_acompanamiento_no_pasa_por_iniciar():
    """La puerta unica del carril NO cambia de firma, y el fondo tiene la suya.

    `iniciar(pieza, plan)` la llama medio proyecto -el gemelo digital, los
    generadores de ejercicios, el endpoint- y ninguno sabe de archivos de fondo.
    Meter el fondo ahi obligaria al carril a saber de que archivo salio su pieza,
    que hoy no sabe y no necesita, y a todos los demas a aprender un parametro
    que no usan.
    """
    firma = inspect.signature(SesionCarril.iniciar)
    assert list(firma.parameters) == ["self", "pieza", "plan"], (
        "la firma de la puerta unica del carril cambio: el acompañamiento tiene "
        f"que entrar por la suya, y hoy `iniciar` es {firma}"
    )
    assert firma.parameters["plan"].default is None

    reloj = RelojFalso()
    sesion_carril, sesion, captura_fondo, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())
    estado = sesion_carril.estado()

    assert estado["acompanamiento_posible"] is True
    assert estado["acompanamiento_sonando"] is True
    cerrar(sesion_carril, sesion)


def test_sin_fondo_cargado_nada_cambia():
    """Sin llamar a la puerta, el carril corre EXACTAMENTE como antes.

    Review Focus 1. Ni se abre la salida del fondo, ni hay hilo, ni el estado
    ofrece encender nada; y la pasada avanza igual que en la etapa 3d.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, captura_fondo, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)

    estado = avanzar_mirando(sesion_carril, reloj, 2.0)

    assert estado["acompanamiento_sonando"] is False
    assert estado["acompanamiento_posible"] is False
    assert estado["acompanamiento_es_tu_parte"] is False
    assert sesion_carril._acompanante is None
    assert captura_fondo.arranques == 0, "no se toco el dispositivo de salida"
    # Y la pasada corre: a 60 ppm, dos segundos son dos pulsos (a mano).
    assert estado["instante_s"] == pytest.approx(2.0, abs=0.05)
    cerrar(sesion_carril, sesion)


def test_el_fondo_se_suelta_con_la_pieza():
    """`detener()` para el fondo y lo OLVIDA: es de la pieza que acaba de morir.

    Un fondo que sobreviviera sonaria encima de la pieza siguiente, que es otra
    cancion y casi nunca el mismo tempo.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, captura_fondo, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())
    assert sesion_carril.estado()["acompanamiento_sonando"] is True

    sesion_carril.detener()

    assert sesion_carril._acompanante is None
    assert sesion_carril._fondo is None
    estado = sesion_carril.estado()
    assert estado["acompanamiento_sonando"] is False
    assert estado["acompanamiento_posible"] is False
    sesion.detener()


# --------------------------------------------------------------------------
# La regla del cable
# --------------------------------------------------------------------------


def test_con_el_microfono_el_acompanamiento_no_es_posible():
    """Con el microfono el fondo vuelve a entrar, y el recordatorio NO se va.

    Review Focus 5. El fondo sale por los altavoces y un microfono abierto lo
    recoge: el detector ve la suma del fondo y del alumno, el carril le adjudica
    notas que no ha tocado y el informe deja de ser suyo.

    Pero no es una compuerta: el usuario puede tener auriculares y saber lo que
    hace, asi que encenderlo lo hace sonar igual. Lo que no se puede es callar el
    aviso -ahi es donde se pierde la medicion sin que nadie lo sepa-, y por eso
    `acompanamiento_sonando` dice True y `acompanamiento_posible` sigue diciendo
    False al mismo tiempo.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj, entrada_es_el_cable=False)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())

    estado = sesion_carril.acompanamiento(encendido=True)

    assert estado["acompanamiento_posible"] is False, (
        "con el microfono el fondo se retroalimenta: el recordatorio tiene que "
        "seguir ahi"
    )
    assert estado["acompanamiento_sonando"] is True, (
        "y aun asi suena: manda el usuario, no el servidor"
    )
    cerrar(sesion_carril, sesion)


def test_la_regla_del_cable_se_decide_UNA_vez_y_viaja_publicada():
    """La regla vive en `Sesion.entrada_es_el_cable` y el carril la LEE.

    Es la leccion de la etapa 3d (`se_esperan_notas`): la regla del aviso del
    cable estaba escrita dos veces, en dos idiomas, las dos no eran la misma, y
    cada mitad tenia su mutante muriendo en su propio idioma. Aqui se cierra por
    los dos lados:

    - **Comportamiento**: mover el dato en la sesion de audio mueve el campo
      publicado. Si el carril se lo volviera a preguntar al sistema por su
      cuenta, no se moveria.
    - **Fuente**: `buscar_rocksmith` -la unica forma de saber si la entrada es el
      cable- no aparece en el carril, y el campo publicado se escribe en UN solo
      sitio del archivo.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj, entrada_es_el_cable=False)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())

    assert sesion_carril.estado()["acompanamiento_posible"] is False
    sesion.entrada_es_el_cable = True
    assert sesion_carril.estado()["acompanamiento_posible"] is True, (
        "el campo publicado tiene que salir de `Sesion.entrada_es_el_cable`, no "
        "de una segunda copia de la regla dentro del carril"
    )

    raiz = pathlib.Path(__file__).resolve().parents[1]
    carril_py = (raiz / "servidor" / "piezas.py").read_text(encoding="utf-8")
    assert "buscar_rocksmith(" not in carril_py, (
        "la regla se decide en `servidor/sesion.py` y el carril la lee: una "
        "segunda llamada aqui es la segunda copia de la regla"
    )
    assert carril_py.count('"acompanamiento_posible":') == 1, (
        "el campo publicado se escribe en un solo sitio; dos sitios en el mismo "
        "archivo bastan para que empiecen a discrepar"
    )
    sesion_py = (raiz / "servidor" / "sesion.py").read_text(encoding="utf-8")
    assert sesion_py.count("buscar_rocksmith(") == 3, (
        "en la sesion de audio el cable se busca donde siempre -el indice "
        "objetivo y el diagnostico- mas la regla nueva; una cuarta llamada es "
        "una regla nueva escondida"
    )
    cerrar(sesion_carril, sesion)


# --------------------------------------------------------------------------
# El candado: lo que decide si el fondo suena o se calla
# --------------------------------------------------------------------------


def test_la_clausura_del_cabezal_no_espera_el_candado():
    """**El mutante mas caro de la tarea**: esperar el candado en la clausura.

    El hilo de audio llama a esta clausura una vez por bloque (21 ms). Si espera
    el candado, no es que vaya lento: `_parar_acompanamiento` corre CON el
    candado tomado y hace `Acompanante.detener()`, que es un `join(timeout=1.0)`
    sobre ese mismo hilo. El hilo esperaria un candado que tiene en la mano
    quien lo quiere parar, el join venceria al segundo y quedaria un hilo
    huerfano escribiendo sobre una salida que la linea siguiente cierra.

    Se mide desde OTRO hilo, porque el candado del carril es reentrante y
    tomarlo desde el hilo de la prueba no lo dejaria ocupado para ella misma.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.estado()

    tomado = threading.Event()
    soltar = threading.Event()

    def ocupar_el_candado():
        with sesion_carril._candado:
            tomado.set()
            soltar.wait(LIMITE_S)

    resultado = {}

    def preguntar_el_cabezal():
        try:
            resultado["valor"] = sesion_carril._cabezal_del_carril()
        except BloqueadoAhora:
            resultado["bloqueado"] = True

    duenyo = threading.Thread(target=ocupar_el_candado, daemon=True)
    duenyo.start()
    assert tomado.wait(LIMITE_S), "el hilo que ocupa el candado no arranco"

    pregunton = threading.Thread(target=preguntar_el_cabezal, daemon=True)
    pregunton.start()
    pregunton.join(timeout=0.5)
    quedo_esperando = pregunton.is_alive()
    soltar.set()
    duenyo.join(timeout=LIMITE_S)
    pregunton.join(timeout=LIMITE_S)

    assert not quedo_esperando, (
        "la clausura del cabezal se quedo esperando el candado: el hilo de audio "
        "no puede esperar a nadie, tiene que lanzar BloqueadoAhora y dejar que el "
        "acompañante repita el ultimo instante"
    )
    assert resultado.get("bloqueado") is True, (
        "con el candado ocupado la clausura tiene que lanzar BloqueadoAhora, que "
        "es lo que el acompañante sabe tratar"
    )
    cerrar(sesion_carril, sesion)


def test_el_cabezal_que_lee_el_acompanante_es_el_del_carril():
    """El cabezal sale del carril: cuenta atras, pasada y final, los tres.

    El acompañante no lleva reloj propio, asi que todo lo que sabe de donde va la
    musica es lo que esta clausura le cuente. Los valores de referencia se
    calculan a mano: a 60 ppm, un segundo es un pulso.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj)
    # Con cuenta atras: un compas de 4/4 a 60 ppm son cuatro segundos.
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), PlanDePasada())
    sesion_carril.estado()

    assert sesion_carril._cabezal_del_carril() is None, (
        "durante la cuenta atras no suena nada: un fondo tocando el compas 1 "
        "mientras el click cuenta cuatro haria entrar al alumno encima de la nota"
    )

    avanzar_mirando(sesion_carril, reloj, 4.0)
    avanzar_mirando(sesion_carril, reloj, 2.0)
    assert sesion_carril._cabezal_del_carril() == pytest.approx(2.0, abs=0.1), (
        "pasada la cuenta, el cabezal son los pulsos de la pasada: a 60 ppm, dos "
        "segundos son dos pulsos"
    )

    avanzar_mirando(sesion_carril, reloj, 6.0)
    assert sesion_carril.estado()["completado"] is True
    assert sesion_carril._cabezal_del_carril() is None, (
        "acabada la pasada no hay nada que sonar"
    )
    cerrar(sesion_carril, sesion)


# --------------------------------------------------------------------------
# La salida propia, la pausa y el render
# --------------------------------------------------------------------------


def test_el_acompanamiento_no_comparte_la_salida_del_click():
    """Treinta instantaneas sin click NO le cierran el stream al fondo.

    `_parar_click` llama a `self._salida.cerrar()` SIN condiciones, y con
    `con_click` apagado eso ocurre en cada instantanea. Hoy es inocuo porque el
    stream del click ya esta en None; compartiendo la salida seria cerrarle el
    stream al acompañamiento treinta veces por segundo, o sea un fondo que no
    suena y nadie sabe por que.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, captura_fondo, captura_click = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())
    assert sesion_carril.estado()["acompanamiento_sonando"] is True
    arranques = captura_fondo.arranques

    avanzar_mirando(sesion_carril, reloj, 1.0)

    assert captura_fondo.cierres == 0, (
        "el stream del fondo se cerro durante la pasada: la salida del "
        f"acompañamiento tiene que ser SUYA ({captura_fondo.cierres} cierres)"
    )
    assert captura_fondo.arranques == arranques, "ni se reabrio"
    assert sesion_carril.estado()["acompanamiento_sonando"] is True
    cerrar(sesion_carril, sesion)


def test_el_acompanamiento_se_pausa_con_la_pasada():
    """Las dos pausas paran el fondo, igual que el click: la del usuario y la del cable.

    En las dos la musica no avanza, y un fondo tocando solo mientras el alumno
    tiene el carril parado es exactamente lo que el click ya no hace.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())
    sesion_carril.estado()
    acompanante = sesion_carril._acompanante
    assert acompanante is not None and acompanante.pausado is False

    sesion_carril.pausa(True)
    assert acompanante.pausado is True, "la pausa del usuario no paro el fondo"
    sesion_carril.pausa(False)
    assert acompanante.pausado is False

    sesion.senal_ausente = True
    avanzar_mirando(sesion_carril, reloj, 0.2)
    assert acompanante.pausado is True, "la falta de señal no paro el fondo"
    sesion.senal_ausente = False
    avanzar_mirando(sesion_carril, reloj, 0.2)
    assert acompanante.pausado is False, "y al volver la señal, vuelve el fondo"

    assert acompanante.sonando is True, "pausar no es detener: el hilo sigue vivo"
    cerrar(sesion_carril, sesion)


def test_sin_voces_el_acompanamiento_suena_tu_parte_y_lo_dice():
    """Sin otra voz suena la propia parte, a la MITAD, y el estado lo dice.

    Un archivo de una sola pista no tiene ninguna voz que el usuario no toque.
    Sonar su parte sigue sirviendo -es la guia con la que se aprende una melodia
    nueva- siempre que se diga, porque a volumen de acompañamiento el alumno no
    distingue su guitarra de la grabacion y cree que toca limpio lo que esta
    tocando la maquina.

    Las muestras esperadas se renderizan AQUI, desde las notas de la pieza
    escritas a mano, y se rebanan con el indice calculado a mano: ni una sale de
    preguntarle al carril lo que acaba de escribir.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, captura_fondo, _ = carril(reloj)
    pieza = pieza_de([40, 45, 50, 55])
    sesion_carril.iniciar(pieza, SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de(midis=()), volumen=1.0)
    estado = sesion_carril.estado()

    assert estado["acompanamiento_es_tu_parte"] is True
    esperaba = renderizar(
        (
            VozDeFondo(
                nombre=pieza.nombre,
                instrumento="Tu parte",
                notas=tuple(
                    NotaDeFondo(
                        midi=float(nota.midi),
                        inicio_pulsos=nota.inicio_pulsos,
                        duracion_pulsos=nota.duracion_pulsos,
                    )
                    for nota in pieza.notas
                ),
            ),
        ),
        tempo=pieza.tempo,
        factor_tempo=1.0,
        frecuencia_muestreo=MUESTREO,
    )
    esperar_el_render(sesion_carril)
    # El reloj no se mueve, asi que el cabezal se queda en el pulso 0 y todos los
    # bloques salen del mismo sitio. Se cuenta desde el render entregado: los
    # bloques de antes son el silencio que el fondo escribe mientras se
    # sintetiza -«hasta que el buffer este, no suena»- y uno mas de margen por
    # el que pudiera estar en vuelo justo al entregarse.
    hechos = captura_fondo.escrituras
    assert captura_fondo.esperar_escrituras(hechos + 3), "el fondo no llego a sonar"
    desde = muestra_del_pulso(0.0)
    cual = hechos + 1
    assert captura_fondo.bloques[cual] == BLOQUE
    escrito = captura_fondo.muestras[cual * BLOQUE : (cual + 1) * BLOQUE]
    rodaja = esperaba.muestras[desde : desde + BLOQUE]

    assert np.allclose(escrito, rodaja * GANANCIA_DE_TU_PARTE, atol=1e-6), (
        "lo que suena tiene que ser la parte del usuario a la mitad de ganancia"
    )
    assert not np.allclose(escrito, 0.0), "y no silencio, que pasaria cualquier cosa"
    cerrar(sesion_carril, sesion)


def test_el_volumen_no_toca_el_plan():
    """Veinte cambios de volumen NO cierran ni una repeticion.

    Todo cambio de plan pasa por `SesionDeEstudio.cambiar_plan`, que hace
    `cerrar_repeticion(cuenta_como_vuelta=False)` para volcar lo tocado antes de
    tirar el seguidor. Con el volumen metido en `PlanDePasada`, arrastrar el
    deslizador serian decenas de cierres de repeticion -y el informe de la pasada
    reconstruido en cada paso- por mover un numero que no cambia la pasada.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())
    estudio = sesion_carril._estudio
    plan_de_antes = estudio.plan
    cierres = []
    real = estudio.cerrar_repeticion

    def contar(*argumentos, **nombrados):
        cierres.append(True)
        return real(*argumentos, **nombrados)

    estudio.cerrar_repeticion = contar

    for paso in range(20):
        sesion_carril.acompanamiento(volumen=paso / 20.0)

    assert cierres == [], (
        f"mover el volumen cerro la repeticion {len(cierres)} veces: el volumen "
        "es un control VIVO y no parte del plan"
    )
    assert estudio.plan == plan_de_antes, "ni toco el plan"
    assert sesion_carril.estado()["repeticion"] == 1
    cerrar(sesion_carril, sesion)


def test_el_interruptor_tampoco_toca_el_plan():
    """Encender y apagar el fondo no corta la vuelta que el alumno esta tocando.

    El hermano del anterior, y el caso que de verdad duele: encender el fondo a
    mitad de pasada con el interruptor dentro del plan cerraria la repeticion en
    curso, o sea que el alumno perderia lo tocado de esa vuelta por darle a un
    boton que solo manda audio a los altavoces.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())
    estudio = sesion_carril._estudio
    cierres = []
    real = estudio.cerrar_repeticion

    def contar(*argumentos, **nombrados):
        cierres.append(True)
        return real(*argumentos, **nombrados)

    estudio.cerrar_repeticion = contar

    apagado = sesion_carril.acompanamiento(encendido=False)
    encendido = sesion_carril.acompanamiento(encendido=True)

    assert cierres == [], "el interruptor del fondo no cierra repeticiones"
    assert apagado["acompanamiento_sonando"] is False
    assert encendido["acompanamiento_sonando"] is True
    cerrar(sesion_carril, sesion)


def test_cambiar_el_factor_de_tempo_renderiza_de_nuevo_UNA_vez(monkeypatch):
    """Se sintetiza al cambiar el archivo o el factor, y NO en cada instantanea.

    La instantanea corre treinta veces por segundo y sintetizar tres minutos de
    musica no es que vaya lento: no termina nunca. La clave
    `(fondo, factor de tempo)` es lo unico que separa un render por pasada de un
    render por paquete del WebSocket.
    """
    contado = RenderContado()
    monkeypatch.setattr("servidor.piezas.renderizar", contado)
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())

    avanzar_mirando(sesion_carril, reloj, 1.0)
    esperar_el_render(sesion_carril)

    assert contado.llamadas == 1, (
        f"treinta instantaneas con el mismo fondo y el mismo factor renderizaron "
        f"{contado.llamadas} veces"
    )

    sesion_carril.parchar_plan({"factor_tempo": 0.5})
    avanzar_mirando(sesion_carril, reloj, 1.0)
    esperar_el_render(sesion_carril)

    assert contado.llamadas == 2, (
        f"el factor nuevo tiene que renderizar otra vez, y una sola: "
        f"{contado.llamadas} llamadas"
    )
    assert contado.factores == [1.0, 0.5], (
        "y el render sigue al factor del plan, que es lo que mueve el cabezal"
    )
    cerrar(sesion_carril, sesion)


def test_sin_salida_de_audio_la_pasada_sigue_en_pie():
    """Sin dispositivo no hay fondo, y la pasada corre igual.

    El mismo contrato que el click de la etapa 3c y que `Acompanante.iniciar`:
    quedarse sin fondo degrada la experiencia y no la impide. Tumbar la pasada
    por el acompañamiento seria cambiar un lujo por lo esencial.
    """
    reloj = RelojFalso()
    sin_dispositivo = SalidaQueCuenta(frecuencia_muestreo=MUESTREO, fallar_al_abrir=True)
    sesion_carril, sesion, _, _ = carril(reloj, salida_fondo=sin_dispositivo)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)
    sesion_carril.cargar_acompanamiento(fondo_de())

    estado = avanzar_mirando(sesion_carril, reloj, 2.0)

    assert estado["acompanamiento_sonando"] is False, (
        "sin salida no suena, y el estado lo dice en vez de enseñar un "
        "interruptor encendido que no hace nada"
    )
    assert estado["acompanamiento_posible"] is True, (
        "pero posible SI: hay fondo y la entrada es el cable; lo que falta es el "
        "dispositivo, que es otra cosa y otro aviso"
    )
    # Y la pasada, en pie: a 60 ppm dos segundos son dos pulsos (a mano).
    assert estado["instante_s"] == pytest.approx(2.0, abs=0.05)
    assert estado["completado"] is False
    cerrar(sesion_carril, sesion)


def test_el_volumen_fuera_de_rango_se_rechaza():
    """Un volumen imposible es `ValueError` -o sea un 400-, no un recorte mudo.

    Quien lo manda es un deslizador: un valor fuera de rango es un defecto de
    quien llama, y recortarlo en silencio lo deja vivo.
    """
    reloj = RelojFalso()
    sesion_carril, sesion, _, _ = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50, 55]), SIN_CUENTA)

    with pytest.raises(ValueError, match="volumen"):
        sesion_carril.cargar_acompanamiento(fondo_de(), volumen=1.5)
    with pytest.raises(ValueError, match="volumen"):
        sesion_carril.acompanamiento(volumen=-0.1)
    cerrar(sesion_carril, sesion)
