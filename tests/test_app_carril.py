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
    with TestClient(app) as cliente:
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
