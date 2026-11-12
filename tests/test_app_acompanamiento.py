"""El fondo visto desde fuera: la cancion que lo carga sola y el interruptor.

Lo que esta etapa cablea aqui es lo ULTIMO que le falta al acompañamiento para
existir: quien lo enciende -nadie: se carga solo al empezar la cancion- y donde
lo lee la pantalla -el estado publicado-. Las cuatro decisiones que vigilan
estas pruebas:

1. **El orden es `iniciar` y DESPUES `cargar_acompanamiento`.** `iniciar`
   detiene lo anterior y `detener` suelta el fondo con la pieza, asi que al
   reves el fondo se pierde EN SILENCIO: la pasada arranca igual y el estado
   dice que no hay nada que sonar. Por eso la primera prueba no mira que no
   reviente: mira cuantas voces quedaron cargadas.
2. **El fondo es un EXTRA y nunca un requisito.** Un archivo que el lector de
   fondo no entiende deja la pieza en pie, sin acompañamiento y diciendolo. Que
   una cancion dejase de poder tocarse porque su fondo no se pudo leer seria el
   peor defecto posible de esta tarea.
3. **Un ejercicio del catalogo no sale de un archivo**: no tiene otras pistas,
   asi que suena su propia pieza como guia y `acompanamiento_es_tu_parte` lo
   dice, para que la pantalla lo llame «Guia» y no «Acompañamiento».
4. **Las pistas excluidas se publican con su motivo.** Un fondo al que le falta
   el bajo sin que nada lo diga parece roto.

Ninguna asercion toma su valor de referencia del camino que prueba: el archivo
de prueba lo escribe la propia prueba con tres pistas contadas a mano -una del
usuario, un bajo y una bateria-, asi que «una voz y una excluida» sale de
contar el archivo y no de preguntarle al servidor lo que acaba de hacer. Y
ninguna abre audio: las dos salidas del carril son `SalidaCapturada`.
"""

import mido
import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.gemelo.salida import SalidaCapturada
from servidor.app import crear_app
from servidor.configuracion import Configuracion
from servidor.piezas import SesionCarril
from servidor.sesion import Sesion

# El servidor solo atiende peticiones dirigidas a localhost (ver
# `guardia_de_peticiones`), asi que las pruebas llaman por localhost.
BASE_LOCAL = "http://127.0.0.1:8420"

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
MICROFONO = DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)
FS = 48000
TICKS = 480

# El ejercicio mas corto del catalogo que da una pieza: sirve de pieza sin
# archivo detras, que es el caso de «no hay otras pistas».
EJERCICIO = {"familia": "escala", "parametros": {"tipo": "mayor"}}


class CapturaFalsa:
    def __init__(self, **kwargs):
        self.ultimo_error = None
        self.latencia_ms = 12.0
        self.total_capturado = 0

    def iniciar(self) -> bool:
        return True

    def detener(self) -> None:
        pass

    def leer_ventana(self, n: int):
        self.total_capturado += n
        t = np.arange(n) / FS
        return (0.3 * np.sin(2 * np.pi * 82.41 * t)).astype(np.float32)


@pytest.fixture
def carpeta(tmp_path):
    """La carpeta de canciones, vacia y fuera del proyecto."""
    destino = tmp_path / "canciones"
    destino.mkdir()
    return destino


@pytest.fixture
def sesion():
    """La sesion de audio con el cable enchufado y la captura de mentira."""
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE, MICROFONO],
    )
    sesion.iniciar()
    yield sesion
    sesion.detener()


@pytest.fixture
def carril(sesion):
    """El carril con las DOS salidas capturadas: el sandbox no abre audio."""
    carril = SesionCarril(
        sesion,
        salida=SalidaCapturada(frecuencia_muestreo=FS).salida,
        salida_fondo=SalidaCapturada(frecuencia_muestreo=FS).salida,
    )
    yield carril
    carril.detener()


@pytest.fixture
def cliente(tmp_path, carpeta, sesion, carril):
    app = crear_app(sesion, carril=carril, carpeta_canciones=carpeta)
    app.state.ruta_config = tmp_path / "config.json"
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        yield cliente


def _pista(nombre, notas, canal=0):
    """Una pista MIDI con esas notas (midi, inicio_ticks, duracion_ticks)."""
    pista = mido.MidiTrack()
    pista.append(mido.MetaMessage("track_name", name=nombre, time=0))
    eventos = []
    for midi, inicio, duracion in notas:
        eventos.append((inicio, 1, mido.Message("note_on", note=midi, channel=canal)))
        eventos.append(
            (inicio + duracion, 0, mido.Message("note_off", note=midi, channel=canal))
        )
    reloj = 0
    for tick, _, mensaje in sorted(eventos, key=lambda evento: (evento[0], evento[1])):
        pista.append(mensaje.copy(time=tick - reloj))
        reloj = tick
    return pista


def banda(ruta):
    """Un MIDI de TRES pistas contadas a mano, que es la referencia de todo aqui.

    1. «Guitarra»: la que el usuario toca, dos notas que caben en el mastil.
    2. «Bajo»: la unica que puede sonar de fondo cuando se toca la 1.
    3. «Bateria»: canal 10, la de percusion, que no tiene alturas que sonar y
       por eso se queda fuera DICIENDO POR QUE.

    De aqui salen los dos numeros que las pruebas afirman -una voz de fondo y
    una excluida- sin preguntarselos a nadie.
    """
    archivo = mido.MidiFile(ticks_per_beat=TICKS)
    guitarra = _pista("Guitarra", [(52, 0, TICKS), (57, TICKS, TICKS)])
    guitarra.insert(
        1, mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(100), time=0)
    )
    archivo.tracks.append(guitarra)
    # Las dos primeras caben en el mastil a proposito: la prueba que empieza en
    # la pista 2 la importa, y una nota por debajo de la sexta al aire seria un
    # 400 de la importacion y no una prueba del fondo.
    archivo.tracks.append(_pista("Bajo", [(40, 0, TICKS), (45, TICKS, TICKS)]))
    # El canal 10 del usuario es el 9 de mido, que cuenta desde cero.
    archivo.tracks.append(_pista("Bateria", [(36, 0, TICKS)], canal=9))
    archivo.save(str(ruta))
    return "banda.mid"


# ---------------------------------------------------------------------------
# Las cinco pruebas del brief
# ---------------------------------------------------------------------------


def test_al_empezar_una_cancion_las_demas_pistas_se_cargan_solas(
    cliente, carpeta, carril
):
    """Y se cargan DESPUES de `iniciar`, que es lo que esta prueba mide.

    `iniciar` llama a `detener`, y `detener` suelta el fondo. Cargarlo antes
    deja la pasada en pie y el fondo en la nada, sin un solo error: lo unico
    que lo delata es que el estado diga que no hay ninguna voz.
    """
    cancion = banda(carpeta / "banda.mid")
    respuesta = cliente.post(
        "/api/piezas/iniciar", json={"cancion": cancion, "pista": 1}
    )
    assert respuesta.status_code == 200
    estado = respuesta.json()
    # El bajo, y solo el bajo: la 1 la toca el usuario y la 3 es percusion.
    assert estado["acompanamiento_voces"] == 1
    assert estado["acompanamiento_posible"] is True
    assert estado["acompanamiento_es_tu_parte"] is False
    # Sin que el cliente haya pedido nada: el estado que la pantalla lee ya lo
    # trae.
    assert cliente.get("/api/piezas/estado").json()["acompanamiento_voces"] == 1
    # Y es el bajo, no cualquier voz: la cuenta sola no distingue apartar una
    # pista de apartar otra, que es justo el defecto que esta linea cierra. El
    # nombre no viaja en el estado -la pantalla solo muestra cuantas son- asi
    # que se mira donde esta, que es el fondo cargado en el carril.
    assert [voz.nombre for voz in carril._fondo.voces] == ["Bajo"]


def test_la_pista_que_tocas_no_suena_de_fondo(cliente, carpeta, carril):
    """Tocando el bajo, el fondo es la guitarra: se aparta la pista PEDIDA.

    Empieza en la pista 2 a proposito: una implementacion que aparte siempre la
    primera -o que no le pase el numero al lector del fondo- pasa la prueba de
    arriba y falla esta.
    """
    cancion = banda(carpeta / "banda.mid")
    estado = cliente.post(
        "/api/piezas/iniciar", json={"cancion": cancion, "pista": 2}
    ).json()
    assert estado["acompanamiento_voces"] == 1
    assert estado["acompanamiento_es_tu_parte"] is False
    # LA GUITARRA, que es la que el usuario NO esta tocando ahora. Contar no
    # basta: apartando siempre la pista 1 tambien queda una sola voz, y seria
    # el usuario doblado por la maquina mientras el bajo no suena.
    assert [voz.nombre for voz in carril._fondo.voces] == ["Guitarra"]
    assert [excluida["pista"] for excluida in estado["acompanamiento_excluidas"]] == [
        "Bateria"
    ]


def test_un_ejercicio_no_tiene_acompanamiento_de_otras_pistas(cliente):
    """No sale de un archivo: suena su propia pieza como guia, y lo dice."""
    estado = cliente.post("/api/piezas/iniciar", json=EJERCICIO).json()
    assert estado["acompanamiento_es_tu_parte"] is True
    assert estado["acompanamiento_voces"] == 0
    assert estado["acompanamiento_excluidas"] == []
    # Hay guia, asi que el interruptor significa algo: sin fondo cargado esto
    # seria False y la pantalla no ofreceria nada.
    assert estado["acompanamiento_posible"] is True


def test_el_endpoint_rechaza_un_volumen_fuera_de_rango(cliente, carril):
    """400 nombrando la opcion y el valor, y SIN aplicar nada de lo que venia.

    Lo segundo es la mitad de la prueba: el cuerpo trae tambien `encendido`, y
    un endpoint que aplique lo bueno antes de mirar lo malo deja el fondo
    apagado y contesta 400, o sea un cambio que nadie pidio y que nadie ve.
    """
    cliente.post("/api/piezas/iniciar", json=EJERCICIO)
    assert carril._fondo_encendido is True
    # El de antes, no el de fabrica: lo que se afirma es que NADA se movio, y
    # tomar el numero de la constante de produccion seria afirmar la constante.
    volumen_antes = carril._volumen_del_fondo
    for malo in (-1, 2.5):
        respuesta = cliente.post(
            "/api/piezas/acompanamiento", json={"encendido": False, "volumen": malo}
        )
        assert respuesta.status_code == 400
        detalle = respuesta.json()["detail"]
        assert "volumen" in detalle.lower()
        assert str(malo) in detalle
        assert carril._fondo_encendido is True
        assert carril._volumen_del_fondo == volumen_antes


def test_las_pistas_excluidas_se_publican_con_su_motivo(cliente, carpeta):
    """La bateria esta en el archivo y no suena: hay que decir por que."""
    cancion = banda(carpeta / "banda.mid")
    estado = cliente.post(
        "/api/piezas/iniciar", json={"cancion": cancion, "pista": 1}
    ).json()
    excluidas = estado["acompanamiento_excluidas"]
    assert len(excluidas) == 1
    assert excluidas[0]["pista"] == "Bateria"
    assert "percusion" in excluidas[0]["motivo"].lower()


def test_un_archivo_que_el_lector_no_entiende_no_tumba_la_pasada(
    cliente, carpeta, monkeypatch
):
    """El fondo es un extra: si no se puede leer, la cancion se toca igual.

    Se rompe `voces_de` y no el archivo porque lo que se prueba es justo el
    caso en el que el archivo SI vale para la pista del usuario -se importa sin
    problema- y no vale para el fondo. Un archivo roto del todo no probaria
    nada: no habria pieza que salvar.
    """

    def revienta(*argumentos, **nombrados):
        raise ValueError("este archivo no lo se leer")

    monkeypatch.setattr("servidor.app.voces_de", revienta)
    cancion = banda(carpeta / "banda.mid")
    respuesta = cliente.post(
        "/api/piezas/iniciar", json={"cancion": cancion, "pista": 1}
    )
    assert respuesta.status_code == 200
    estado = respuesta.json()
    # La pieza esta en pie, y es LA SUYA: contar las notas no distingue la
    # guitarra del bajo -las dos pistas tienen dos notas- y es el mismo defecto
    # que la cuenta de voces tapaba. Los midis son los que escribio `banda`.
    assert [nota["midi"] for nota in estado["pieza"]["notas"]] == [52, 57]
    # Y el estado lo dice, en vez de callarlo.
    assert estado["acompanamiento_posible"] is False
    assert estado["acompanamiento_voces"] == 0
    assert estado["acompanamiento_es_tu_parte"] is False
    assert estado["acompanamiento_excluidas"] == []


# ---------------------------------------------------------------------------
# El interruptor y el volumen, que son el resto del endpoint
# ---------------------------------------------------------------------------


def test_el_endpoint_mueve_el_interruptor_y_el_volumen(cliente, carril):
    """Y devuelve el estado publicado, que es lo que la pantalla vuelve a leer."""
    cliente.post("/api/piezas/iniciar", json=EJERCICIO)
    respuesta = cliente.post(
        "/api/piezas/acompanamiento", json={"encendido": False, "volumen": 0.25}
    )
    assert respuesta.status_code == 200
    assert "acompanamiento_sonando" in respuesta.json()
    assert carril._fondo_encendido is False
    assert carril._volumen_del_fondo == 0.25


def test_mandar_solo_el_interruptor_no_mueve_el_volumen(cliente, carril):
    """Lo ausente se queda como estaba. Es la doctrina de `_campos_del_plan`.

    Un cuerpo es un PATCH: `{"encendido": true}` dice una cosa y no dice nada
    de la otra. Convertir ese silencio en un cero deja el fondo mudo con el
    interruptor encendido, que es el peor sitio donde dejarlo: el usuario ve
    que esta puesto y no oye nada.
    """
    cliente.post("/api/piezas/iniciar", json=EJERCICIO)
    cliente.post("/api/piezas/acompanamiento", json={"volumen": 0.42})

    respuesta = cliente.post("/api/piezas/acompanamiento", json={"encendido": True})

    assert respuesta.status_code == 200
    assert carril._volumen_del_fondo == 0.42, "el volumen que nadie toco no se mueve"
    assert carril._fondo_encendido is True


def test_mandar_solo_el_volumen_no_mueve_el_interruptor(cliente, carril):
    """La otra mitad, y empieza con el fondo ENCENDIDO a proposito.

    **Aqui empezo mal la primera version de esta prueba** y el mutante la paso:
    arrancaba con el fondo apagado, y un campo ausente convertido en `False`
    deja un `False` que ya estaba, o sea el mismo estado que respetarlo. El
    defecto solo se ve desde el estado CONTRARIO al que el descuido produce, y
    ese es encendido -que ademas es como cargarlo lo deja-.
    """
    cliente.post("/api/piezas/iniciar", json=EJERCICIO)
    assert carril._fondo_encendido is True, "cargarlo lo deja encendido"

    respuesta = cliente.post("/api/piezas/acompanamiento", json={"volumen": 0.3})

    assert respuesta.status_code == 200
    assert carril._fondo_encendido is True, "el interruptor que nadie toco no se mueve"
    assert carril._volumen_del_fondo == 0.3


def test_un_volumen_que_no_es_un_numero_se_rechaza(cliente, carril):
    """`true` no es 1.0, y `"0.5"` no es medio.

    En JSON un numero se escribe sin comillas y un booleano no es un numero;
    `float(True)` vale 1.0, asi que `{"volumen": true}` se colaba como el fondo
    a tope. Es la misma clase de error que la etapa anterior arreglo en el
    escaparate: un numero aceptado en el formato equivocado.
    """
    cliente.post("/api/piezas/iniciar", json=EJERCICIO)
    volumen_antes = carril._volumen_del_fondo
    for malo in (True, "0.5", None, [0.5]):
        respuesta = cliente.post("/api/piezas/acompanamiento", json={"volumen": malo})
        assert respuesta.status_code == 400, f"{malo!r} no es un volumen"
        assert "volumen" in respuesta.json()["detail"].lower()
        assert carril._volumen_del_fondo == volumen_antes


def test_si_el_fondo_revienta_al_cargarse_la_pasada_sigue_y_no_hay_500(
    cliente, carril, monkeypatch
):
    """La respuesta peor de este endpoint: un 500 con la pasada YA en marcha.

    Debajo de `cargar_acompanamiento` se cierran dispositivos de audio
    -`SalidaAudio.cerrar()` llama a `stream.stop()` y `stream.close()` sin
    protegerlos- y lo que salga de CoreAudio no es ni `TypeError` ni
    `ValueError`. Subia tal cual, y el usuario se quedaba tocando una pieza que
    el servidor acababa de decirle que no habia podido empezar.
    """

    def revienta(*argumentos, **nombrados):
        raise OSError("PortAudio se cayo al cerrar el stream")

    monkeypatch.setattr(carril, "cargar_acompanamiento", revienta)
    respuesta = cliente.post("/api/piezas/iniciar", json=EJERCICIO)

    assert respuesta.status_code == 200, "la pasada esta en marcha: no es un 500"
    assert respuesta.json()["pieza"]["notas"], "y la pieza viaja igual"
    # Y la pasada esta de verdad en marcha, no solo en la respuesta.
    assert cliente.get("/api/piezas/estado").json()["completado"] is False


def test_el_interruptor_se_pide_con_true_o_false_y_no_con_cualquier_cosa(cliente):
    """`{"encendido": "no"}` es un pedido mal hecho, no un encendido.

    Mismo filtro que los booleanos del plan: `bool("no")` vale True, asi que
    apagar el fondo desde una pantalla que mande texto lo encenderia.
    """
    cliente.post("/api/piezas/iniciar", json=EJERCICIO)
    respuesta = cliente.post("/api/piezas/acompanamiento", json={"encendido": "no"})
    assert respuesta.status_code == 400
    assert "encendido" in respuesta.json()["detail"].lower()
