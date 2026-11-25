import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.sintesis import SalidaAudio
from servidor.app import crear_app
from servidor.configuracion import Configuracion
from servidor.ejercicios import SesionPractica
from servidor.sesion import Sesion

# El servidor solo atiende peticiones dirigidas a localhost (ver
# `guardia_de_peticiones`), asi que las pruebas llaman por localhost y no por el
# "testserver" que pone TestClient de serie: probar contra un anfitrion que el
# servidor de verdad rechazaria seria probar otro servidor.
BASE_LOCAL = "http://127.0.0.1:8420"

# Y los WebSocket se piden con la URL ENTERA: `websocket_connect` de Starlette no
# mira el `base_url` del cliente, resuelve las rutas relativas contra
# "ws://testserver" y manda ese `Host`, que el guardia rechaza con razon (lo
# rechazaria tambien el servidor de verdad).
WS_LOCAL = "ws://127.0.0.1:8420"

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


class StreamSalidaFalso:
    def start(self):
        pass

    def write(self, muestras):
        pass

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def cliente(tmp_path):
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    practica = SesionPractica(
        sesion, salida=SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    )
    app = crear_app(sesion, practica=practica)
    app.state.ruta_config = tmp_path / "config.json"
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        yield cliente
    practica.detener()
    sesion.detener()


def test_el_modulo_de_ejercicios_aparece_junto_al_afinador(cliente):
    claves = [m["clave"] for m in cliente.get("/api/modulos").json()]
    assert "afinador" in claves
    assert "ejercicios" in claves


def test_el_instrumento_publicado_es_el_perfil_activo(cliente):
    """La interfaz no puede ofrecer una cuerda que el instrumento no tiene."""
    instrumento = cliente.get("/api/ejercicios/instrumento").json()
    assert instrumento["clave"] == "guitarra_estandar"
    assert [c["numero"] for c in instrumento["cuerdas"]] == [6, 5, 4, 3, 2, 1]
    assert instrumento["trastes"] == 22


def test_con_el_bajo_activo_el_instrumento_publicado_tiene_cuatro_cuerdas(cliente):
    assert cliente.put("/api/config", json={"perfil": "bajo_4"}).status_code == 200
    instrumento = cliente.get("/api/ejercicios/instrumento").json()
    assert instrumento["clave"] == "bajo_4"
    assert [c["numero"] for c in instrumento["cuerdas"]] == [4, 3, 2, 1]
    assert instrumento["trastes"] == 24


def test_el_estado_dice_si_el_metronomo_se_pidio(cliente):
    """"metronomo: False" solo es un aviso cuando se habia pedido."""
    cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 2}, "con_metronomo": False},
    )
    assert cliente.get("/api/ejercicios/estado").json()["metronomo_pedido"] is False
    cliente.post("/api/ejercicios/detener")
    cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 2}, "con_metronomo": True},
    )
    assert cliente.get("/api/ejercicios/estado").json()["metronomo_pedido"] is True
    cliente.post("/api/ejercicios/detener")


def test_las_familias_traen_sus_parametros_y_valores_admitidos(cliente):
    """Asi el configurador se construye solo, sin listas escritas a mano."""
    familias = cliente.get("/api/ejercicios/familias").json()
    claves = {f["clave"] for f in familias}
    assert claves == {"escala", "arpegio", "intervalo", "lectura", "cambios"}
    escala = next(f for f in familias if f["clave"] == "escala")
    assert "mayor" in escala["tipos"]
    assert "pentatonica_menor" in escala["tipos"]
    # "cambios" es la familia de acordes de la etapa 2b, y sus "tipos" son las
    # digitaciones de la tabla, no patrones de intervalos.
    cambios = next(f for f in familias if f["clave"] == "cambios")
    assert "do" in cambios["tipos"]
    assert "mi_menor" in cambios["tipos"]


def test_generar_devuelve_el_ejercicio_sin_iniciarlo(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "escala", "parametros": {"raiz_midi": 48, "tipo": "mayor"}},
    )
    assert respuesta.status_code == 200
    assert len(respuesta.json()["notas"]) > 0
    assert cliente.get("/api/ejercicios/estado").json()["evaluacion"] is None


def test_una_configuracion_imposible_da_400_con_mensaje_en_espanol(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "escala", "parametros": {"tipo": "inventada"}},
    )
    assert respuesta.status_code == 400
    assert "escala" in respuesta.json()["detail"]


def test_una_familia_inexistente_da_400(cliente):
    respuesta = cliente.post("/api/ejercicios/generar", json={"familia": "solfeo"})
    assert respuesta.status_code == 400
    assert "familia" in respuesta.json()["detail"]


def test_un_rango_de_trastes_sin_notas_da_400(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "escala", "parametros": {"traste_minimo": 30, "traste_maximo": 30}},
    )
    assert respuesta.status_code == 400
    assert "ninguna nota" in respuesta.json()["detail"]


def test_iniciar_deja_el_ejercicio_en_curso(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 4, "semilla": 1}},
    )
    assert respuesta.status_code == 200
    estado = cliente.get("/api/ejercicios/estado").json()
    assert estado["evaluacion"]["total"] == 4
    assert estado["evaluacion"]["indice"] == 0


def test_detener_limpia_el_ejercicio(cliente):
    cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 3, "semilla": 1}},
    )
    assert cliente.post("/api/ejercicios/detener").status_code == 200
    assert cliente.get("/api/ejercicios/estado").json()["evaluacion"] is None


def test_el_estado_sin_ejercicio_responde_sin_reventar(cliente):
    estado = cliente.get("/api/ejercicios/estado").json()
    assert estado["ejercicio"] is None
    assert estado["evaluacion"] is None


def test_el_websocket_emite_el_estado_del_ejercicio(cliente):
    cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 3, "semilla": 1}},
    )
    with cliente.websocket_connect(WS_LOCAL + "/ws/ejercicios") as socket:
        mensaje = socket.receive_json()
        assert set(mensaje) >= {"ejercicio", "evaluacion", "informe", "metronomo"}
        assert mensaje["evaluacion"]["total"] == 3


def test_el_websocket_emite_aunque_no_haya_ejercicio(cliente):
    with cliente.websocket_connect(WS_LOCAL + "/ws/ejercicios") as socket:
        mensaje = socket.receive_json()
        assert mensaje["ejercicio"] is None


def test_un_tipo_de_parametro_erroneo_da_400_y_no_500(cliente):
    """Spec §5: la configuracion invalida se rechaza explicando el problema. Un
    valor del tipo equivocado sale de Python como TypeError, no ValueError, y
    dejarlo subir lo convertia en un 500: "el servidor se ha roto", que es
    mentira y no dice al usuario que tiene que corregir.
    """
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "escala", "parametros": {"traste_minimo": "x"}},
    )
    assert respuesta.status_code == 400
    assert respuesta.json()["detail"]


def test_un_parametro_que_no_existe_da_400(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "lectura", "parametros": {"repeticion": 3}},
    )
    assert respuesta.status_code == 400
    assert "repeticion" in respuesta.json()["detail"]


def test_iniciar_con_un_parametro_del_tipo_erroneo_tambien_da_400(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": "tres"}},
    )
    assert respuesta.status_code == 400
