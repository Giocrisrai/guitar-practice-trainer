"""EL ANTI-OBJETIVO DE LA ETAPA, MEDIDO: el fondo colandose por la entrada.

La etapa 3e hace que la pieza suene de fondo mientras el usuario toca, y lo que
la haria fracasar aunque todo funcionara es que **el programa se puntue a si
mismo**: si la entrada es el microfono del portatil, el sonido del fondo vuelve a
entrar por ella, el detector de ataques lo cobra como notas del usuario y el
informe se llena de aciertos y fallos que no toco nadie. Lo peor es que no se
nota: los numeros salen y estan mal.

Toda la etapa esta construida alrededor de ese riesgo -el fondo arranca apagado
si la entrada no es el cable (`acompanamiento_posible`), el aviso no se va
mientras suena-, **pero hasta esta tarea nadie lo habia medido**. Y no se podia:
la entrada del gemelo (`nucleo/gemelo/dispositivo.py`) y la salida del
acompanamiento (`nucleo/acompanante.py` sobre `nucleo/sintesis.py`) son dos
streams sin ningun camino entre ellos, asi que una prueba de realimentacion
escrita sobre ellos **no podia fallar por realimentacion ni queriendo**. Lo que
este archivo hace, antes de medir nada, es CONSTRUIR ese camino:
`dispositivo_simulado(..., audio_ambiente=...)` suma al audio que el cable falso
entrega el que suene en la habitacion, que es lo que un microfono abierto hace.

**LAS DOS MITADES, Y HACEN FALTA LAS DOS.**

1. Con la suma, el veredicto EMPEORA: aparecen notas inventadas que no toco
   nadie. Esto es lo que demuestra que el riesgo es real y no una precaucion
   escrita.
2. Sin la suma -el caso del cable-, el veredicto es IDENTICO campo a campo
   aunque el acompanamiento este sonando de verdad por la salida. Es la mitad de
   control, la hermana de `test_sin_solape_no_hay_fantasmas`: sin ella, la
   primera no probaria que la causa es la SUMA y no el fondo por el mero hecho de
   existir.

**POR QUE SE MIDE CON LA CADENA DIRECTA Y NO CON LA SESION ENTERA.** El cable se
usa de verdad -se abre, su hilo empuja los bloques a tiempo real y se recoge lo
que entrega por el callback-, pero quien juzga lo entregado es
`pasar_por_la_cadena`, que recorre el audio en tiempo VIRTUAL y es DETERMINISTA.
La sesion completa (`tests/test_gemelo_sesion_completa.py`) no lo es: su propio
archivo tiene medido que 2 de 22 pasadas pierden exactamente una nota segun como
el sistema operativo reparta los hilos. Con ella, «el veredicto es identico campo
a campo» habria sido una prueba intermitente, o sea una prueba que un dia se
pondria roja sin que nadie hubiera colado ningun audio.

**EL PRECIO ES EL RELOJ**, y por eso las pruebas van marcadas `slow` y comparten
una sola bateria de pasadas: el cable entrega a tiempo real, asi que vaciarlo
cuesta tantos segundos como audio tenga la pieza.
"""

import threading
import time
from dataclasses import dataclass, replace

import numpy as np
import pytest

from nucleo.acompanamiento import PiezaRenderizada, renderizar
from nucleo.acompanante import Acompanante
from nucleo.gemelo.cadena import RegistroDeLaCadena, pasar_por_la_cadena
from nucleo.gemelo.dispositivo import dispositivo_simulado
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.gemelo.salida import SalidaCapturada
from nucleo.gemelo.veredicto import Veredicto, juzgar
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio
from nucleo.piezas.voces_de_fondo import NotaDeFondo, VozDeFondo
from servidor.piezas import VOLUMEN_DEL_FONDO_POR_OMISION

# Las ocho notas de la escala: ninguna repetida y ningun acorde, asi que las ocho
# son medibles y ninguna se excluye del veredicto.
NOTAS = 8

# El tempo de la pieza. 160 y no el escrito (100) por lo mismo que en
# `tests/test_gemelo_sesion_completa.py`: la pasada dura 3,1 s en vez de 4,9, y
# cada segundo de audio es un segundo de reloj que este archivo paga tres veces.
TEMPO = 160

# La semilla del interprete. LA MISMA EN LAS TRES PASADAS, que es la condicion de
# que «el veredicto es identico» signifique algo: con semillas distintas el audio
# del guitarrista ya seria otro y no habria nada que comparar.
SEMILLA = 0

# El plan de la pasada: sin bucle, sin cuenta atras y sin click. El click ABRE
# AUDIO, y ninguna prueba abre un dispositivo de sonido.
PLAN = PlanDePasada(en_bucle=False, compases_de_cuenta_atras=0, con_click=False)

# Cuanto del fondo vuelve a entrar por el microfono, sobre el volumen al que el
# fondo sale. **Es una eleccion, no una medida**, y se escribe asi para que nadie
# la cite como si alguien hubiera medido una habitacion: lo que el microfono de
# un portatil recoge de sus propios altavoces depende del portatil, del volumen y
# de donde este el alumno.
#
# Lo que si esta medido es que el defecto NO depende de acertar este numero: la
# tabla `REALIMENTACION_MEDIDA` barre tres niveles -de un cuarto al volumen
# entero- y el veredicto empeora en los tres. Por eso la prueba afirma la tabla y
# no un nivel afortunado.
#
# `(nivel, inventadas, perdidas, mal_adjudicadas)`, MEDIDO sobre el guitarrista
# PERFECTO tocando la escala al tempo 160 con la semilla 0, que sin fondo firma un
# veredicto LIMPIO: cero invenciones, cero perdidas y cero malas adjudicaciones.
#
# Los numeros son exactos y no un rango porque este camino es determinista: el
# cable entrega un contenido que solo depende de sus dos entradas y la cadena
# directa recorre el audio en tiempo virtual. Van uno a uno -y no resumidos en
# «empeora»- para que el dia que algo cambie se sepa en que nivel cambio; el
# invariante que dice que hay defecto se afirma aparte y antes que ellos.
REALIMENTACION_MEDIDA = (
    (0.25, 1, 1, 2),
    (0.5, 4, 4, 2),
    (1.0, 3, 3, 3),
)

NIVELES_DEL_MICROFONO = tuple(nivel for nivel, _, _, _ in REALIMENTACION_MEDIDA)

# El volumen al que el fondo SALE, que es el del proyecto y no uno inventado
# aqui: `servidor.piezas.VOLUMEN_DEL_FONDO_POR_OMISION`. Lo que se simula es el
# fondo del programa volviendo por el microfono, no un ruido cualquiera.
VOLUMEN_DEL_FONDO = VOLUMEN_DEL_FONDO_POR_OMISION

# Las notas del acompanamiento que suena detras: a CONTRATIEMPO, en el medio de
# cada hueco del alumno.
#
# A contratiempo y no al unisono porque un acompanamiento que atacara en el mismo
# instante que el alumno seria el caso benigno -el detector veria un solo ataque,
# mas fuerte- y mediria el riesgo por su lado flojo. Un fondo de verdad rellena
# los huecos, y son esos ataques de relleno los que el detector no tiene forma de
# atribuirle a nadie.
#
# Las alturas van por la misma zona que la escala (G3-G4), que es donde el
# detector de tono trabaja comodo: un fondo inaudible para el detector no probaria
# nada, y la pista de acompanamiento de una cancion de guitarra esta justo ahi.
NOTAS_DEL_FONDO = ((60, 0.5), (64, 1.5), (62, 2.5), (65, 3.5),
                   (59, 4.5), (64, 5.5), (62, 6.5), (67, 7.5))

# Lo que se le concede a cada vaciado del cable por encima de la duracion de su
# audio. El cable entrega a tiempo real, asi que el vaciado dura lo que dure la
# pieza; cinco segundos de mas es holgura para una maquina cargada y a la vez lo
# bastante corto para que un cable que no entrega se note como un fallo y no como
# una suite que no acaba.
MARGEN_DE_ESPERA_S = 5.0

# El bloque con el que el acompanante alimenta la salida en la pasada de control.
# Es el suyo de fabrica; se nombra aqui solo para poder afirmar que lo capturado
# son bloques de verdad y no una escritura unica.
TAMANO_DE_BLOQUE_DEL_FONDO = 1024


@dataclass(frozen=True)
class Pasada:
    """Lo que una pasada deja: lo que el cable entrego y lo que se firmo con ello."""

    entregado: np.ndarray
    registro: RegistroDeLaCadena
    veredicto: Veredicto


def _interpretacion() -> Interpretacion:
    """El guitarrista PERFECTO tocando la escala. La misma en las tres pasadas."""
    return interpretar(escala_de_ocho_notas(tempo=TEMPO), PERFECTO, semilla=SEMILLA)


def _voz_del_fondo() -> VozDeFondo:
    """La pista de acompanamiento que suena detras del alumno."""
    return VozDeFondo(
        nombre="Acompanamiento",
        instrumento="guitarra",
        notas=tuple(
            NotaDeFondo(midi=float(midi), inicio_pulsos=inicio, duracion_pulsos=0.5)
            for midi, inicio in NOTAS_DEL_FONDO
        ),
    )


def _render_del_fondo() -> PiezaRenderizada:
    """El fondo sintetizado por el codigo de produccion, al tempo de la pieza."""
    return renderizar(
        (_voz_del_fondo(),),
        tempo=TEMPO,
        ganancia=VOLUMEN_DEL_FONDO,
    )


def _ambiente(render: PiezaRenderizada, interpretacion: Interpretacion,
              nivel: float) -> np.ndarray:
    """El fondo tal y como entraria por un microfono abierto, en el eje del cable.

    Dos cosas, y las dos son del montaje y no del dispositivo:

    * **Se alinea.** El render empieza en el pulso cero de la pieza, que en el eje
      del audio del gemelo cae en `silencio_de_cabecera_s` (la cabecera tecnica
      que el interprete mete delante). Sumarlo en la muestra cero adelantaria el
      fondo esos 128 ms respecto de lo que el alumno toca, que es un desajuste
      inventado por la prueba.
    * **Se atenua.** `nivel` es cuanto del fondo vuelve por el microfono.

    No se recorta a la longitud del audio del alumno: el microfono sigue oyendo el
    fondo despues de la ultima nota, y el cable esta hecho para entregar eso (ver
    `dispositivo_simulado`).
    """
    desde = round(interpretacion.silencio_de_cabecera_s * interpretacion.frecuencia_muestreo)
    ambiente = np.zeros(desde + render.muestras.size, dtype=np.float32)
    ambiente[desde:] = render.muestras * nivel
    return ambiente


def _vaciar_el_cable(
    interpretacion: Interpretacion, audio_ambiente: np.ndarray | None = None
) -> np.ndarray:
    """Abre el cable del gemelo, recoge lo que entrega y lo devuelve entero.

    Es el dispositivo DE VERDAD: su hilo, su reloj de pared y su callback con la
    firma de `sounddevice`. Se copia cada bloque porque el stream reutiliza el
    suyo, igual que hace `BufferCircular.escribir`.

    Se espera con un `Event` que el propio callback levanta cuando ya hay
    bastante, nunca durmiendo un plazo: lo que decide cuando parar es el audio
    entregado, no el reloj.

    Devuelve tantas muestras como tenga lo que haya que entregar -el audio del
    alumno, o el ambiente si es mas largo-, sin el silencio que el cable sigue
    empujando despues.
    """
    cuantas = max(
        interpretacion.muestras.size,
        0 if audio_ambiente is None else audio_ambiente.size,
    )
    abrir_stream, _ = dispositivo_simulado(interpretacion, audio_ambiente=audio_ambiente)
    bloques: list[np.ndarray] = []
    recogidas = 0
    bastante = threading.Event()

    def callback(datos, cuadros, tiempo, estado) -> None:
        nonlocal recogidas
        bloques.append(np.array(datos[:, 0], copy=True))
        recogidas += cuadros
        if recogidas >= cuantas:
            bastante.set()

    stream = abrir_stream(callback, samplerate=interpretacion.frecuencia_muestreo)
    stream.start()
    try:
        limite = interpretacion.duracion_s + cuantas / interpretacion.frecuencia_muestreo
        assert bastante.wait(limite + MARGEN_DE_ESPERA_S), (
            f"el cable no entrego las {cuantas} muestras: se quedo en {recogidas}"
        )
    finally:
        stream.stop()
    return np.concatenate(bloques)[:cuantas]


def _juzgar_lo_entregado(
    interpretacion: Interpretacion, entregado: np.ndarray
) -> tuple[RegistroDeLaCadena, Veredicto]:
    """Mete por la cadena de produccion lo que el cable entrego y firma el veredicto.

    La VERDAD con la que se juzga sigue siendo la del interprete -sus eventos,
    su pieza y su cabecera-: lo unico que se sustituye son las muestras, que son
    lo que el cable cambia. Un veredicto juzgado contra una verdad que tambien
    llevara el fondo dentro no mediria nada, porque el fondo seria entonces parte
    de lo que se esperaba oir.
    """
    conducida = replace(interpretacion, muestras=entregado)
    estudio = SesionDeEstudio(interpretacion.pieza, PLAN)
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    registro = pasar_por_la_cadena(conducida, conductor)
    return registro, juzgar(conducida, registro)


def _pasada(
    interpretacion: Interpretacion, audio_ambiente: np.ndarray | None = None
) -> Pasada:
    """Una pasada entera: vaciar el cable y juzgar lo que entrego."""
    entregado = _vaciar_el_cable(interpretacion, audio_ambiente=audio_ambiente)
    registro, veredicto = _juzgar_lo_entregado(interpretacion, entregado)
    return Pasada(entregado=entregado, registro=registro, veredicto=veredicto)


@pytest.fixture(scope="module")
def interpretacion() -> Interpretacion:
    return _interpretacion()


@pytest.fixture(scope="module")
def sin_suma(interpretacion) -> Pasada:
    """El caso del cable: el fondo no entra por ningun sitio. La referencia."""
    return _pasada(interpretacion)


@pytest.fixture(scope="module")
def con_suma(interpretacion) -> dict[float, Pasada]:
    """El caso del microfono abierto, a cada nivel de la tabla."""
    render = _render_del_fondo()
    return {
        nivel: _pasada(interpretacion, _ambiente(render, interpretacion, nivel))
        for nivel in NIVELES_DEL_MICROFONO
    }


@pytest.mark.slow
def test_con_el_fondo_colandose_por_la_entrada_el_veredicto_EMPEORA(
    interpretacion, sin_suma, con_suma
):
    """**EL ANTI-OBJETIVO, MEDIDO.** El fondo entra por la entrada y se cobra notas.

    El montaje es el mismo audio del mismo guitarrista PERFECTO con la misma
    semilla, por la misma cadena, con la misma verdad. Lo UNICO que cambia es que
    el cable suma lo que suena en la habitacion, que es lo que hace un microfono
    abierto. Lo que aparece son invenciones: notas que la cadena firma y que el
    alumno no toco.

    **La referencia no sale de este camino**: es la misma pasada sin suma
    (`sin_suma`), que sale limpia. Sin ella, un veredicto con invenciones no
    probaria nada, porque la cadena ya se inventa notas cuando las colas se
    solapan (`tests/test_gemelo_sonido_sucio.py`).

    **Y se afirma en los tres niveles de `REALIMENTACION_MEDIDA`** para que lo
    medido sea el defecto y no un volumen afortunado.

    **Y LOS REPORTES SIGUEN SIENDO OCHO EN LOS CUATRO CASOS**, que es la frase
    entera de la spec: el fondo no hace que la cadena publique mas notas, hace que
    las ocho que publica hablen de notas distintas de las que el alumno toco. Por
    eso esto no se nota desde fuera -el informe sale con sus ocho notas y sus
    numeros- y por eso hace falta medirlo aqui.
    """
    assert sin_suma.veredicto.limpio is True, (
        "la referencia tiene que salir limpia: si el cable sin fondo ya ensucia "
        "el veredicto, lo que la otra mitad mida no sera del fondo"
    )
    assert sin_suma.veredicto.inventadas == 0
    assert sin_suma.veredicto.perdidas == ()
    assert sin_suma.veredicto.mal_adjudicadas == ()
    assert len(sin_suma.registro.reportes) == NOTAS

    for nivel, inventadas, perdidas, mal_adjudicadas in REALIMENTACION_MEDIDA:
        pasada = con_suma[nivel]
        veredicto = pasada.veredicto
        # EL DEFECTO, antes del recuento: con el fondo entrando por la entrada la
        # cadena firma notas que nadie toco, y eso vale para los tres niveles.
        assert veredicto.inventadas > sin_suma.veredicto.inventadas, (
            f"con el fondo al {nivel} entrando por la entrada la cadena firmo "
            f"{veredicto.inventadas} invenciones, las mismas que sin el: "
            "el montaje no esta midiendo la realimentacion"
        )
        assert veredicto.limpio is False
        # Y cada invencion cuesta una nota de verdad: el reporte inventado ocupa
        # el puesto del emparejamiento y la que de verdad sono se queda sin el.
        # Es el mismo mecanismo que el fantasma del solape
        # (`tests/test_gemelo_sonido_sucio.py`), llegado por otra puerta.
        assert len(veredicto.perdidas) == veredicto.inventadas
        # El numero medido de este nivel.
        assert veredicto.inventadas == inventadas
        assert len(veredicto.perdidas) == perdidas
        assert len(veredicto.mal_adjudicadas) == mal_adjudicadas
        # Ocho notas tocadas y ocho reportes publicados, como sin fondo: lo que
        # cambia no es cuantas notas hay en el informe, es de que notas hablan.
        assert veredicto.notas_tocadas == NOTAS
        assert len(pasada.registro.reportes) == NOTAS


@pytest.mark.slow
def test_la_forma_de_la_realimentacion_al_nivel_medio(
    interpretacion, sin_suma, con_suma
):
    """La realimentacion de cerca: QUE le pasa al informe cuando el fondo entra.

    Es la unica prueba del archivo que fija un solo nivel, y lo dice en el
    nombre; el barrido esta en `REALIMENTACION_MEDIDA`. Existe porque el reparto
    exacto es lo que enseña el MECANISMO, y un recuento no lo enseña.

    **Los ocho reportes, con el nivel 0,5, contra los ocho sin fondo** (puesto,
    altura y el instante del cabezal al publicarse, en segundos):

        sin fondo   0:55 0,188  1:57 0,503  2:59 0,860  3:60 1,259
                    4:62 1,637  5:64 2,036  6:65 2,372  7:67 2,750
        con fondo   0:55 0,188  1:57 0,503  2:45 0,692  3:59 0,881
                    4:47 1,070  5:41 1,427  6:62 1,994  7:65 2,372

    **El mecanismo esta entero en esa tabla, y no es que se añadan reportes: es
    que los ataques del fondo se COLAN EN LA FILA.** Los reportes 2, 4 y 5 caen
    en instantes en los que el alumno no toco nada -el fondo ataca a
    contratiempo, en el medio de cada hueco- y a partir del primero de ellos la
    numeracion va corrida: el 59 que el reporte 3 publica es la altura de la nota
    2, que acaba de sonar, y el 65 del reporte 7 es la de la nota 6. Cada ataque
    del fondo le roba el puesto a una nota de verdad, y de ahi que las perdidas
    sean exactamente tantas como las invenciones.

    **Y las alturas de los ataques colados -45, 47 y 41- no son ni del alumno ni
    del fondo**: ninguna de las tres esta en la escala (55-67) ni en
    `NOTAS_DEL_FONDO`. Son lo que un detector de tono monofonico devuelve cuando
    le llegan dos cuerdas a la vez. Asi que el informe no trae ninguna pista de
    donde salieron: no hay nada que filtrar mirandolo.

    **Y el desfase que el veredicto firma MEJORA**, de +131,3 ms sin fondo a
    +35,3 con el. No es que la cadena vaya mas rapida: es que los instantes que
    mide ya no son los de los ataques del alumno. Un numero de calidad que mejora
    cuando el informe se estropea es la mejor descripcion de por que este defecto
    no se nota.

    Si esto se pone rojo y la tabla sigue verde, lo que cambio es el reparto y no
    el defecto.
    """
    pasada = con_suma[0.5]
    veredicto = pasada.veredicto

    alturas = tuple(reporte.tocada.midi for reporte in pasada.registro.reportes)
    assert alturas == (55, 57, 45, 59, 47, 41, 62, 65)
    # Las tres alturas coladas no estan ni en la escala que el alumno toca ni en
    # la pista que suena detras: no hay en el informe ninguna pista de su origen.
    coladas = {45, 47, 41}
    assert not coladas & {evento.midi for evento in interpretacion.eventos}
    assert not coladas & {midi for midi, _ in NOTAS_DEL_FONDO}

    assert veredicto.inventadas == 4
    assert veredicto.perdidas == ((1, 4), (1, 5), (1, 6), (1, 7))
    assert veredicto.mal_adjudicadas == ((1, 2, 45), (1, 3, 59))
    assert veredicto.desfase_introducido_ms == pytest.approx(35.3, abs=0.1)
    assert sin_suma.veredicto.desfase_introducido_ms == pytest.approx(131.3, abs=0.1)


@pytest.mark.slow
def test_sin_la_suma_el_veredicto_es_IDENTICO_muestra_a_muestra(
    interpretacion, sin_suma
):
    """El caso del cable: el acompanamiento SUENA y el veredicto no se entera.

    La mitad de control, y sin ella la de arriba no probaria lo que dice: unas
    invenciones que aparecieran tambien con el fondo sonando por su sitio serian
    un defecto del montaje -o del gemelo- y no la realimentacion que la etapa
    teme.

    El fondo suena DE VERDAD: un `Acompanante` de produccion escribiendo en una
    `SalidaAudio` de produccion con el stream capturado, al compas de un cabezal
    que corre con el mismo reloj de pared que el cable. Que sono se comprueba
    sobre lo escrito -muestras distintas de cero-, no sobre lo que el acompanante
    diga de si mismo.

    Y el veredicto se compara CAMPO A CAMPO contra la pasada de referencia, no
    consigo mismo: los dos `Veredicto` son dataclases congeladas, asi que la
    igualdad los compara entero por entero y tupla por tupla.
    """
    capturada = SalidaCapturada()
    assert capturada.abrir() is True
    acompanante = Acompanante(
        salida=capturada.salida, bloque=TAMANO_DE_BLOQUE_DEL_FONDO
    )
    acompanante.cargar(_render_del_fondo())
    pulsos_por_segundo = TEMPO / 60.0
    arranque = time.monotonic()
    assert acompanante.iniciar(
        lambda: (time.monotonic() - arranque) * pulsos_por_segundo
    ) is True
    try:
        con_fondo_sonando = _pasada(interpretacion)
    finally:
        acompanante.detener()
        capturada.salida.cerrar()

    # El fondo sono: hay escrituras y lo escrito no es silencio.
    assert len(capturada.bloques) > 1
    assert float(np.max(np.abs(capturada.muestras))) > 0.0

    # Y el cable entrego lo mismo, muestra a muestra, con el fondo sonando.
    assert np.array_equal(con_fondo_sonando.entregado, sin_suma.entregado)
    assert con_fondo_sonando.veredicto == sin_suma.veredicto


@pytest.mark.slow
def test_con_audio_ambiente_None_el_cable_entrega_lo_mismo_que_entregaba_antes(
    interpretacion, sin_suma
):
    """El parametro nuevo, apagado, no mueve ni una muestra.

    `audio_ambiente=None` es el valor por omision y es el que corre en las demas
    pruebas del gemelo y en `herramientas/gemelo.py`, asi que lo que esta prueba
    sujeta es que la tarea no cambio nada de lo que ya habia.

    **La referencia es `interpretacion.muestras`, no otra pasada por el cable**, y
    esa es la diferencia que hace la asercion valida: contra otra pasada, un
    dispositivo que le sumara una constante a TODO lo que entrega seguiria
    saliendo igual a si mismo. Contra la verdad del interprete, no.
    """
    assert np.array_equal(
        sin_suma.entregado[: interpretacion.muestras.size], interpretacion.muestras
    )
