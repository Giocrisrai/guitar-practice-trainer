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

from herramientas.gemelo import StreamCapturadoAlRitmo
from nucleo.acompanamiento import PiezaRenderizada, renderizar
from nucleo.acompanante import Acompanante
from nucleo.gemelo.cadena import RegistroDeLaCadena, pasar_por_la_cadena
from nucleo.gemelo.dispositivo import _con_el_ambiente, dispositivo_simulado
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.gemelo.veredicto import Veredicto, juzgar
from nucleo.musica import midi_a_frecuencia
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio
from nucleo.piezas.voces_de_fondo import NotaDeFondo, VozDeFondo
from nucleo.sintesis import SalidaAudio
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
# `(nivel, inventadas, perdidas, mal_adjudicadas, pico)`, MEDIDO sobre el
# guitarrista PERFECTO tocando la escala al tempo 160 con la semilla 0, que sin
# fondo firma un veredicto LIMPIO: cero invenciones, cero perdidas y cero malas
# adjudicaciones. `pico` es el valor absoluto mayor de lo que el cable entrega.
#
# Los numeros son exactos y no un rango porque este camino es determinista: el
# cable entrega un contenido que solo depende de sus dos entradas y la cadena
# directa recorre el audio en tiempo virtual. Van uno a uno -y no resumidos en
# «empeora»- para que el dia que algo cambie se sepa en que nivel cambio; el
# invariante que dice que hay defecto se afirma aparte y antes que ellos.
#
# **EL BARRIDO TIENE SUELO Y SE DECLARA.** La primera fila sale LIMPIA: con el
# fondo entrando al 0,15 el veredicto es el mismo que sin fondo, y tambien lo es
# al 0,10 y al 0,05 (medido, no en la tabla para no pagar tres vaciados mas por
# tres ceros). El defecto aparece **desde el 0,20**. Asi que lo que esta medido
# no es «da igual el nivel» sino «da igual el nivel POR ENCIMA DE ~0,2», que es
# una frase distinta: un microfono malo y lejano -el caso del suelo- no ensucia
# el informe, y decir lo contrario seria vender la medicion por mas de lo que es.
# La fila del suelo esta en la tabla para que ese borde sea un dato vigilado y no
# una nota al pie.
#
# **Y LA ULTIMA FILA SE SALE DE LA ESCALA A PROPOSITO** (pico 1,163 > 1). Es la
# unica que puede ver el contrato de `_con_el_ambiente` que dice que la suma NO
# se recorta a [-1, 1]: con las cinco de arriba el pico se queda por debajo del
# techo -la mas alta, a 13 milesimas- y entonces recortar y no recortar dan
# exactamente lo mismo, o sea que el contrato y su negacion coinciden en el
# estado donde la prueba empieza. Un fondo que vuelve mas fuerte de lo que salio
# no es ademas un caso inventado: es el altavoz cerca del microfono.
REALIMENTACION_MEDIDA = (
    (0.15, 0, 0, 0, 0.818),
    (0.20, 2, 2, 1, 0.827),
    (0.25, 1, 1, 2, 0.837),
    (0.50, 4, 4, 2, 0.887),
    (1.00, 3, 3, 3, 0.987),
    (1.50, 1, 1, 6, 1.163),
)

# El mayor nivel que todavia deja el veredicto limpio, o sea el suelo del defecto.
NIVEL_DEL_SUELO = 0.15

NIVELES_DEL_MICROFONO = tuple(fila[0] for fila in REALIMENTACION_MEDIDA)

# Las alturas que la cadena firma sobre los ataques colados, con las notas que
# estaban sonando cuando las firmo: `(colada, (midis que sonaban))`. MEDIDO al
# nivel 0,5; el mecanismo esta en el docstring de
# `test_la_forma_de_la_realimentacion_al_nivel_medio`.
SUBARMONICOS_MEDIDOS = ((45, (57, 64)), (41, (60, 65)), (47, (59,)))

# Lo que se le concede a un pico medido. Tres milesimas: los picos son
# deterministas, asi que la holgura es solo para no escribir quince decimales.
MARGEN_DEL_PICO = 0.003

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
    return _vaciar(abrir_stream, interpretacion, cuantas)


def _vaciar(
    abrir_stream, interpretacion: Interpretacion, cuantas: int
) -> np.ndarray:
    """Una apertura de ese cable, vaciada hasta tener `cuantas` muestras.

    Esta aparte de `_vaciar_el_cable` para que la prueba de las dos aperturas
    pueda abrir DOS VECES EL MISMO cable, que es lo que `CapturaAudio` hace
    cuando se reabre; con el dispositivo construido dentro, abrir dos veces
    serian dos cables distintos y la prueba no miraria lo que dice.
    """
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

    **Y se afirma en todo el barrido de `REALIMENTACION_MEDIDA`** -de un fondo
    que apenas vuelve hasta uno que vuelve mas fuerte de lo que salio- para que
    lo medido sea el defecto y no un volumen afortunado. **Con su suelo**: la
    fila del 0,15 sale limpia y se afirma limpia, porque un barrido que empezara
    donde el defecto ya esta diria «da igual el nivel» sin haber mirado abajo.

    **Y LOS REPORTES SIGUEN SIENDO OCHO EN TODOS LOS CASOS**, que es la frase
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

    for nivel, inventadas, perdidas, mal_adjudicadas, pico in REALIMENTACION_MEDIDA:
        pasada = con_suma[nivel]
        veredicto = pasada.veredicto
        medido = float(np.max(np.abs(pasada.entregado)))
        if nivel > NIVEL_DEL_SUELO:
            # EL DEFECTO, antes del recuento: con el fondo entrando por la
            # entrada la cadena firma notas que nadie toco, y eso vale de 0,20
            # para arriba.
            assert veredicto.inventadas > sin_suma.veredicto.inventadas, (
                f"con el fondo al {nivel} entrando por la entrada la cadena firmo "
                f"{veredicto.inventadas} invenciones, las mismas que sin el: "
                "el montaje no esta midiendo la realimentacion"
            )
            assert veredicto.limpio is False
            # Y cada invencion cuesta una nota de verdad: el reporte inventado
            # ocupa el puesto del emparejamiento y la que de verdad sono se queda
            # sin el. Es el mismo mecanismo que el fantasma del solape
            # (`tests/test_gemelo_sonido_sucio.py`), llegado por otra puerta.
            assert len(veredicto.perdidas) == veredicto.inventadas
        else:
            # EL SUELO, declarado: por debajo de el, el fondo entra y no se cobra
            # nada. No vigila el defecto -eso lo hacen las filas de arriba-, dice
            # hasta donde llega lo que este archivo puede afirmar.
            assert veredicto.limpio is True
        # El numero medido de este nivel.
        assert veredicto.inventadas == inventadas
        assert len(veredicto.perdidas) == perdidas
        assert len(veredicto.mal_adjudicadas) == mal_adjudicadas
        # Y el pico de lo que el cable entrego, que es lo que dice que la suma
        # llego entera: por encima de 1 en la ultima fila, donde un recorte a
        # [-1, 1] se veria.
        assert medido == pytest.approx(pico, abs=MARGEN_DEL_PICO)
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

    **Y las alturas de los ataques colados -45, 47 y 41- son SUBARMONICOS de lo
    que estaba sonando**, no basura numerica. El detector de tono busca el
    **primer** minimo de la diferencia normalizada y no el global
    (`nucleo/analisis/yin.py`: «quedarse con el primero prioriza el periodo mas
    largo, que es el de la fundamental»), que es lo que evita el error de octava
    con UNA cuerda; con DOS a la vez el primer minimo cae en el periodo comun de
    las dos, o sea en el **subarmonico comun**:

        45 = 110,0 Hz   = el comun de 220,0 (el 57 del alumno)
                          y 329,6 (el 64 del fondo), que van en razon 2:3
        41 =  87,3 Hz   = el comun de 261,6 (el 60 del alumno)
                          y 349,2 (el 65 del fondo), que van en razon 3:4
        47 = 123,5 Hz   = la octava justa debajo de 246,9, el 59 del alumno

    **Asi que decir que esas alturas «no son de nadie» seria falso**, y la
    primera version de esta prueba lo decia: las tres comparten clase de altura
    con una nota que estaba sonando y un `midi % 12` las emparejaria. Lo que si
    es cierto -y es lo que se afirma- es que ninguna de las tres es una nota
    ESCRITA, ni en la escala del alumno ni en la pista del fondo: lo que el
    informe recibe no es «sono el 64 del fondo», que se podria filtrar, sino una
    altura que no esta en ningun sitio.

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

    # Ninguna de las tres coladas es una nota ESCRITA, ni del alumno ni del fondo.
    coladas = (45, 47, 41)
    escritas = {evento.midi for evento in interpretacion.eventos} | {
        midi for midi, _ in NOTAS_DEL_FONDO
    }
    assert not set(coladas) & escritas
    # Y las tres son el subarmonico comun de notas que SI estaban sonando: su
    # frecuencia cabe un numero entero de veces en la de cada una de ellas. La
    # cuenta se hace con `midi_a_frecuencia`, que es la del nucleo, y la razon
    # entera es lo que distingue un subarmonico de una altura cualquiera.
    for colada, sonando in SUBARMONICOS_MEDIDOS:
        comun = midi_a_frecuencia(colada)
        for midi in sonando:
            veces = midi_a_frecuencia(midi) / comun
            assert veces == pytest.approx(round(veces), abs=0.01), (
                f"el {colada} no es subarmonico del {midi}: cabe {veces} veces"
            )
            assert round(veces) >= 2

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
    `SalidaAudio` de produccion con el stream capturado, pidiendole cada bloque a
    un cabezal que corre con el mismo reloj de pared que el cable. Que sono se
    comprueba sobre lo escrito -muestras distintas de cero-, no sobre lo que el
    acompanante diga de si mismo.

    **Y EL CAPTURADOR ES EL QUE ESPERA, QUE NO ES UN DETALLE DE ESTILO SINO EL
    ARREGLO DE UN DEFECTO DE ESTA PRUEBA.** `StreamCapturado` acepta cada
    escritura al instante, al reves que un dispositivo de verdad, que BLOQUEA
    hasta que hay hueco; con el, el hilo del acompanante gira a la velocidad de
    la CPU. Medido en esta misma prueba antes de arreglarla: **1.048.470 bloques
    en 3,4 s, o sea 22.367 segundos de audio retenidos en una lista, y 4,53 GB de
    pico de RSS** (`getrusage`) contra los 0,13 GB del proceso. Y no tiene techo:
    crece con lo que dure la pasada, en un equipo de 16 GB. `StreamCapturadoAlRitmo`
    -de `herramientas/gemelo.py`, que existe justo para esto- espera lo que
    tardaria la tarjeta, y entonces se retienen **151 bloques, 3,22 s de audio y
    4 MB**. La prueba lo AFIRMA abajo, para que el defecto no pueda volver en
    silencio.

    Y el veredicto se compara CAMPO A CAMPO contra la pasada de referencia, no
    consigo mismo: los dos `Veredicto` son dataclases congeladas, asi que la
    igualdad los compara entero por entero y tupla por tupla.
    """
    capturador = StreamCapturadoAlRitmo()
    salida = SalidaAudio(abrir_stream=lambda **argumentos: capturador)
    assert salida.abrir() is True
    acompanante = Acompanante(salida=salida, bloque=TAMANO_DE_BLOQUE_DEL_FONDO)
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
        salida.cerrar()

    # El fondo sono: hay escrituras y lo escrito no es silencio.
    escrito = capturador.muestras
    assert len(capturador.bloques) > 1
    assert float(np.max(np.abs(escrito))) > 0.0

    # Y se escribio al RITMO DE UNA TARJETA, no a la de la CPU: lo retenido es
    # del orden de lo que duro la pasada. El doble es holgura de sobra para una
    # maquina cargada y sigue estando cuatro ordenes de magnitud por debajo de
    # los 22.367 s que esta prueba llego a guardar.
    assert escrito.size <= 2 * interpretacion.duracion_s * interpretacion.frecuencia_muestreo

    # Y el cable entrego lo mismo, muestra a muestra, con el fondo sonando.
    #
    # Las dos mitades de la comparacion son DOS PASADAS DISTINTAS, y se afirma:
    # un veredicto comparado consigo mismo sale igual pase lo que pase, y esa es
    # la forma que tendria esta prueba de aprobar sin mirar nada. Lo que las hace
    # dos es que `sin_suma` se vacio sin ningun acompanante vivo.
    assert con_fondo_sonando is not sin_suma
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

    Y la segunda asercion es el contrato escrito de `_con_el_ambiente`: con
    `None` devuelve **el mismo array**, no una copia igual. Lo que se evita con
    eso son los 600 KB por apertura de una copia que nadie necesita, y sin
    afirmarlo nadie se enteraria de perderlo. Es la unica linea del archivo que
    mira una funcion privada, y por eso: la identidad no se ve desde fuera del
    modulo.
    """
    assert np.array_equal(
        sin_suma.entregado[: interpretacion.muestras.size], interpretacion.muestras
    )
    assert _con_el_ambiente(interpretacion.muestras, None) is interpretacion.muestras


def _interpretacion_de_juguete(muestras: np.ndarray) -> Interpretacion:
    """Una `Interpretacion` armada alrededor de unas muestras, sin sintetizar nada.

    El cable solo lee `muestras` y `frecuencia_muestreo`; el resto esta para que
    el dataclass se pueda construir. Es el mismo atajo que usa
    `tests/test_gemelo_dispositivo.py`, y por el mismo motivo: lo que se mide
    aqui es el cable, y montar una interpretacion de verdad seria pagar un
    segundo de sintesis y tres de reloj para no mirarlos.
    """
    return Interpretacion(
        pieza=escala_de_ocho_notas(tempo=TEMPO),
        muestras=muestras,
        eventos=(),
        frecuencia_muestreo=48000,
        duracion_s=muestras.size / 48000,
        silencio_de_cabecera_s=0.0,
    )


@pytest.mark.parametrize(
    ("bloques_del_gemelo", "bloques_del_ambiente"),
    ((8, 16), (16, 8)),
    ids=("el ambiente dura mas", "el alumno dura mas"),
)
def test_la_suma_es_muestra_a_muestra_y_dura_lo_que_el_mas_largo_de_los_dos(
    bloques_del_gemelo, bloques_del_ambiente
):
    """La suma de cerca, con un audio de juguete: exacta, entera y sin recortar.

    No paga reloj y por eso no va marcada `slow`: ocho o dieciseis bloques, o sea
    85 o 171 ms. Las de arriba miden lo que la suma le hace al VEREDICTO, que es
    lo que la etapa teme; esta mide la suma.

    Tres cosas, y ninguna de las tres la puede ver el barrido de niveles:

    * **Es muestra a muestra.** La referencia es la suma hecha aqui con numpy
      sobre los dos arrays que entraron, que es la definicion de lo que se pide
      y no un segundo recorrido del codigo que se prueba.
    * **Dura lo que el mas largo de los dos, SEA CUAL SEA DE LOS DOS**, y de ahi
      los dos casos: en todas las demas pruebas del archivo el ambiente es el mas
      largo -el microfono sigue oyendo el fondo cuando el alumno ya callo-, asi
      que la otra rama del `max()` no se ejecutaba en ningun sitio y un cable que
      recortara al ambiente pasaba el archivo entero.
    * **Y LA SUMA SE SALE DE [-1, 1] Y SALE ENTERA.** Los dos juguetes llegan a
      1,85 de pico, porque un montaje que se quedara por debajo del techo no
      podria distinguir el contrato («no se recorta») de su contrario: con picos
      de 0,9 un `np.clip` da exactamente lo mismo. Que un cable entregue algo
      fuera de escala no es ademas un capricho de la prueba: es lo que un
      conversor de verdad recibe cuando el altavoz esta encima del microfono, y
      recortarlo aqui en silencio taparia el problema de niveles en vez de
      dejarlo ver.
    """
    bloque = 512
    gemelo = np.linspace(0.1, 0.9, bloques_del_gemelo * bloque, dtype=np.float32)
    ambiente = np.linspace(0.6, 0.95, bloques_del_ambiente * bloque, dtype=np.float32)

    entregado = _vaciar_el_cable(
        _interpretacion_de_juguete(gemelo), audio_ambiente=ambiente
    )

    esperado = np.zeros(max(gemelo.size, ambiente.size), dtype=np.float32)
    esperado[: gemelo.size] = gemelo
    esperado[: ambiente.size] += ambiente
    assert entregado.size == max(gemelo.size, ambiente.size)
    assert np.array_equal(entregado, esperado)
    # Y la suma se salio de la escala de verdad, que es lo que hace falta para
    # que la igualdad de arriba vigile el contrato del recorte.
    assert float(np.max(np.abs(entregado))) > 1.0


def test_dos_aperturas_del_mismo_cable_entregan_lo_mismo():
    """Abrir DOS VECES el mismo cable entrega la misma suma, que es lo prometido.

    `CapturaAudio` se reabre cuando el dispositivo cambia, asi que `abrir_stream`
    se llama mas de una vez en la vida de un cable. La mezcla se calcula una sola
    vez al construirlo justamente por eso, y el comentario que lo dice no lo
    vigilaba nadie: una mezcla que se consumiera o se recalculara mal en la
    segunda apertura dejaria la sesion muda a mitad de pasada.
    """
    bloque = 512
    gemelo = np.linspace(0.1, 0.9, 4 * bloque, dtype=np.float32)
    ambiente = np.full(4 * bloque, 0.3, dtype=np.float32)
    interpretacion = _interpretacion_de_juguete(gemelo)
    abrir_stream, _ = dispositivo_simulado(interpretacion, audio_ambiente=ambiente)

    primera = _vaciar(abrir_stream, interpretacion, gemelo.size)
    segunda = _vaciar(abrir_stream, interpretacion, gemelo.size)

    assert np.array_equal(primera, segunda)
    assert np.array_equal(primera, gemelo + ambiente)


@pytest.mark.parametrize(
    ("ambiente", "dimensiones"),
    (
        (np.zeros((512, 2), dtype=np.float32), 2),
        (np.zeros((2, 512, 1), dtype=np.float32), 3),
        (np.float32(0.5), 0),
    ),
    ids=("estereo entrelazado", "tres dimensiones", "un escalar"),
)
def test_un_ambiente_que_no_es_mono_se_rechaza_al_abrir_el_dispositivo(
    ambiente, dimensiones
):
    """Un ambiente que no sea un canal no se suma a medias: se rechaza y se dice.

    El cable entrega UN canal -`CapturaAudio._callback` indexa `datos[:, 0]`- y
    cualquier otra forma aqui se sumaria por difusion o reventaria dentro del
    hilo del stream, que es donde las excepciones mueren sin que nadie las vea y
    el audio simplemente deja de llegar. Quien le pase al cable el buffer
    estereo de una tarjeta se entera al abrir, no por un gemelo mudo.

    **Y se prueban tres formas, no solo la estereo**, que es la unica que le
    pasaria a alguien de verdad: con un solo caso de dos dimensiones, una guarda
    escrita `ndim == 2` -que dejaria pasar un escalar y un array de tres ejes,
    los dos con difusion silenciosa- seria indistinguible de la que esta escrita,
    `ndim != 1`. El escalar no es rebuscado: es lo que sale de `render[0]` o de
    una ganancia pasada por error en el sitio del audio.

    El mensaje trae el numero de dimensiones recibido, que es el dato que le dice
    a quien lo lee que lo que paso fue eso y no otra cosa.
    """
    interpretacion = _interpretacion_de_juguete(
        np.linspace(0.1, 0.9, 512, dtype=np.float32)
    )

    with pytest.raises(ValueError) as fallo:
        dispositivo_simulado(interpretacion, audio_ambiente=ambiente)

    assert f"{dimensiones} dimensiones" in str(fallo.value)
    assert "mono" in str(fallo.value)
