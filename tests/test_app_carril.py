"""Los endpoints y el WebSocket del carril: el puente entre la sesion y el navegador.

Mismo doble de captura y misma `SalidaAudio` de mentira que
`tests/test_app_ejercicios.py`: ninguna prueba abre el dispositivo de audio real.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.app import crear_app
from servidor.configuracion import Configuracion
from servidor.piezas import SesionCarril
from servidor.sesion import Sesion

# El servidor solo atiende peticiones dirigidas a localhost (ver
# `guardia_de_peticiones`), asi que las pruebas llaman por localhost y no por el
# "testserver" que pone TestClient de serie: probar contra un anfitrion que el
# servidor de verdad rechazaria seria probar otro servidor.
BASE_LOCAL = "http://127.0.0.1:8420"

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000


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
def cliente(tmp_path):
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    carril = SesionCarril(sesion)
    app = crear_app(sesion, carril=carril)
    app.state.ruta_config = tmp_path / "config.json"
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        yield cliente
    carril.detener()
    sesion.detener()


def test_desde_ejercicio_devuelve_una_pieza_con_cuerda_y_traste(cliente):
    respuesta = cliente.post(
        "/api/piezas/desde-ejercicio",
        json={"familia": "escala", "parametros": {"tipo": "mayor"}},
    )
    assert respuesta.status_code == 200
    pieza = respuesta.json()
    assert pieza["notas"]
    primera = pieza["notas"][0]
    assert 1 <= primera["cuerda"] <= 6
    assert primera["traste"] >= 0
    assert primera["inicio_pulsos"] == 0.0


def test_una_familia_inexistente_da_400_y_no_500(cliente):
    respuesta = cliente.post("/api/piezas/desde-ejercicio", json={"familia": "solfeo"})
    assert respuesta.status_code == 400
    assert "solfeo" in respuesta.json()["detail"]


def test_un_parametro_mal_escrito_da_400(cliente):
    respuesta = cliente.post(
        "/api/piezas/desde-ejercicio",
        json={"familia": "escala", "parametros": {"traste_minimo": "x"}},
    )
    assert respuesta.status_code == 400


def test_iniciar_devuelve_la_pieza_y_el_estado_no_la_repite(cliente):
    respuesta = cliente.post(
        "/api/piezas/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 3}},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["pieza"]["notas"]
    estado = cliente.get("/api/piezas/estado").json()
    assert "pieza" not in estado
    assert estado["indice_actual"] == 0
    cliente.post("/api/piezas/detener")


def test_el_estado_trae_el_instante_para_que_el_navegador_interpole(cliente):
    cliente.post("/api/piezas/iniciar", json={"familia": "lectura", "parametros": {"repeticiones": 2}})
    estado = cliente.get("/api/piezas/estado").json()
    assert "instante_s" in estado
    assert "pausado" in estado
    cliente.post("/api/piezas/detener")


def test_el_modulo_carril_aparece_junto_a_los_otros(cliente):
    claves = [m["clave"] for m in cliente.get("/api/modulos").json()]
    assert {"afinador", "ejercicios", "carril"} <= set(claves)


def test_el_websocket_emite_estado_sin_la_pieza(cliente):
    cliente.post(
        "/api/piezas/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 2}},
    )
    with cliente.websocket_connect("/ws/piezas") as ws:
        mensaje = ws.receive_json()
    assert "pieza" not in mensaje
    assert "instante_s" in mensaje
    assert "pausado" in mensaje
    cliente.post("/api/piezas/detener")


def test_el_websocket_etiqueta_los_paquetes_con_el_arranque_de_la_pieza(cliente):
    """El paquete dice de que arranque habla, y es el mismo que devolvio `iniciar`.

    Sin esto el navegador no puede distinguir un paquete de la pieza que acaba de
    pedir de uno de la anterior que todavia venia por el canal, y acaba pintando
    el resumen de una pieza sobre otra.
    """
    arranque = cliente.post(
        "/api/piezas/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 2}},
    ).json()["arranque"]
    with cliente.websocket_connect("/ws/piezas") as ws:
        mensaje = ws.receive_json()
    assert mensaje["arranque"] == arranque
    assert cliente.get("/api/piezas/estado").json()["arranque"] == arranque

    cliente.post("/api/piezas/detener")
    assert cliente.get("/api/piezas/estado").json()["arranque"] == 0


def test_cambiar_de_afinacion_detiene_el_carril(cliente):
    """La spec §7, aplicada tambien cuando la afinacion cambia a mitad de pieza.

    Una pieza escrita en otra afinacion que la activa se rechaza con 400 al
    iniciar; pero el perfil tambien se puede cambiar con la pieza ya en marcha, y
    entonces el carril seguia dibujando los trastes de la afinacion vieja y todas
    las notas restantes salian falladas sin que nada lo explicara.
    """
    inicio = cliente.post(
        "/api/piezas/iniciar", json={"familia": "lectura", "parametros": {"repeticiones": 2}}
    )
    assert inicio.status_code == 200
    assert inicio.json()["pieza"]["perfil"] == "guitarra_estandar"

    respuesta = cliente.put("/api/config", json={"perfil": "bajo_4"})
    assert respuesta.status_code == 200

    estado = cliente.get("/api/piezas/estado").json()
    assert estado["total"] == 0
    assert estado["arranque"] == 0


def test_cambiar_otra_cosa_de_la_configuracion_no_detiene_el_carril(cliente):
    """Solo la afinacion detiene la pieza: el umbral de ruido o el dispositivo no.

    Detener el carril con cualquier PUT convertiria un ajuste de volumen en una
    pieza perdida.
    """
    inicio = cliente.post(
        "/api/piezas/iniciar", json={"familia": "lectura", "parametros": {"repeticiones": 2}}
    )
    arranque = inicio.json()["arranque"]

    assert cliente.put("/api/config", json={"umbral_ruido_dbfs": -42.0}).status_code == 200

    estado = cliente.get("/api/piezas/estado").json()
    assert estado["total"] > 0
    assert estado["arranque"] == arranque
    cliente.post("/api/piezas/detener")
