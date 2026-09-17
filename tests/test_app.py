import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.app import crear_app
from servidor.configuracion import Configuracion
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000


class CapturaFalsa:
    def __init__(self, **kwargs):
        self.ultimo_error = None
        self.latencia_ms = 12.0
        self._total = 0
        self.instante_ultimo_bloque = time.monotonic()

    @property
    def total_capturado(self) -> int:
        """Cada consulta simula que siguen llegando bloques del dispositivo."""
        self._total += 512
        self.instante_ultimo_bloque = time.monotonic()
        return self._total

    def iniciar(self) -> bool:
        return True

    def detener(self) -> None:
        pass

    def leer_ventana(self, n: int):
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
    app = crear_app(sesion)
    app.state.ruta_config = tmp_path / "config.json"
    with TestClient(app) as cliente:
        yield cliente
    sesion.detener()


def test_lista_los_modulos_para_que_la_interfaz_los_descubra(cliente):
    modulos = cliente.get("/api/modulos").json()
    assert any(modulo["clave"] == "afinador" for modulo in modulos)


def test_lista_los_perfiles_de_afinacion(cliente):
    perfiles = cliente.get("/api/perfiles").json()
    claves = {perfil["clave"] for perfil in perfiles}
    assert {"guitarra_estandar", "bajo_5"} <= claves
    guitarra = next(p for p in perfiles if p["clave"] == "guitarra_estandar")
    assert len(guitarra["cuerdas"]) == 6
    assert guitarra["cuerdas"][0]["nota"] == "E2"


def test_lista_los_dispositivos_de_entrada(cliente):
    dispositivos = cliente.get("/api/dispositivos").json()
    assert dispositivos[0]["nombre"] == NOMBRE_ROCKSMITH


def test_el_diagnostico_responde_ok_con_el_cable(cliente):
    assert cliente.get("/api/diagnostico").json()["estado"] == "ok"


def test_devuelve_la_configuracion_actual(cliente):
    assert cliente.get("/api/config").json()["perfil"] == "guitarra_estandar"


def test_cambiar_la_configuracion_la_aplica_y_la_guarda(cliente):
    respuesta = cliente.put("/api/config", json={"dispositivo": 3, "perfil": "bajo_4"})
    assert respuesta.status_code == 200
    assert cliente.get("/api/config").json()["perfil"] == "bajo_4"


def test_la_respuesta_del_put_incluye_configuracion_y_diagnostico(cliente):
    """PUT /api/config debe devolver tanto la configuración guardada como el
    diagnóstico de aplicarla, porque un dispositivo que falla al abrir se
    guarda igualmente y el usuario necesita saber que la apertura falló."""
    respuesta = cliente.put("/api/config", json={"dispositivo": 3, "perfil": "bajo_4"})
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"configuracion", "diagnostico"}
    assert cuerpo["configuracion"]["perfil"] == "bajo_4"
    assert "estado" in cuerpo["diagnostico"]


def test_una_configuracion_invalida_da_400_con_mensaje_en_espanol(cliente):
    respuesta = cliente.put("/api/config", json={"perfil": "ukelele"})
    assert respuesta.status_code == 400
    assert "perfil" in respuesta.json()["detail"]


def test_un_put_invalido_no_encalla_la_configuracion(cliente):
    """Un campo inválido debe dar 400 y dejar la sesión tan usable como estaba.

    Antes, `detector` no se validaba y `aplicar()` asignaba la configuración
    antes de construir el analizador: el 500 dejaba la sesión con una
    configuración imposible y todos los PUT siguientes fallaban también.
    """
    respuesta = cliente.put("/api/config", json={"detector": "inexistente"})
    assert respuesta.status_code == 400
    assert "detector" in respuesta.json()["detail"]

    siguiente = cliente.put("/api/config", json={"perfil": "bajo_4"})
    assert siguiente.status_code == 200
    assert cliente.get("/api/config").json()["perfil"] == "bajo_4"
    assert cliente.get("/api/config").json()["detector"] == "yin"


def test_la_calibracion_devuelve_un_umbral_sugerido(cliente):
    datos = cliente.post("/api/calibrar", json={"segundos": 0.2}).json()
    assert "umbral_sugerido" in datos


def test_el_websocket_emite_el_resultado_del_analisis(cliente):
    with cliente.websocket_connect("/ws/notas") as socket:
        for _ in range(20):
            mensaje = socket.receive_json()
            if mensaje["estado"] == "nota":
                assert mensaje["nota"] == "E2"
                assert set(mensaje) >= {
                    "estado", "frecuencia", "nota", "cents", "confianza",
                    "nivel_db", "posiciones", "cuerda_objetivo", "afinada", "latencia_ms",
                }
                return
    pytest.fail("El WebSocket no emitió ninguna nota en 20 mensajes")


def test_el_mensaje_de_silencio_tiene_la_misma_forma_que_el_del_analisis(tmp_path):
    """El WebSocket emite una sola forma de mensaje, venga de donde venga.

    Cuando aún no hay resultado, el servidor construye el mismo dataclass que
    usa el análisis en vez de escribir el diccionario a mano: dos sitios que
    había que cambiar juntos y que nada comparaba.
    """
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    app = crear_app(sesion)
    app.state.ruta_config = tmp_path / "config.json"

    esperado = ResultadoAnalisis(
        estado="silencio", frecuencia=0.0, confianza=0.0, nivel_db=-120.0
    ).a_dict()

    with TestClient(app) as cliente:
        with cliente.websocket_connect("/ws/notas") as socket:
            mensaje = socket.receive_json()

    assert mensaje["estado"] == "silencio"
    del mensaje["latencia_ms"]
    assert mensaje == esperado
    sesion.detener()
