"""Los cinco endpoints de estudio: el plan, el salto, la pausa, el informe y la pieza.

Mismo doble de captura y misma fixture que `tests/test_app_carril.py`: ninguna
prueba abre el dispositivo de audio real.

La pieza de las pruebas se construye EN CODIGO y se le entrega al carril por su
propio `iniciar`, no por `/api/piezas/iniciar`. La razon es que ese endpoint solo
acepta dos formas de pedir una pieza -un ejercicio del catalogo o una cancion del
disco- y no una pieza en el cuerpo de la peticion: aceptarla seria creerle al
cliente las notas y la afinacion con la que dice estar escritas, que es justo lo
que la puerta unica del carril existe para comprobar (ver `_pieza_para_el_carril`
en `servidor/app.py`). Lo que esta tarea abre -las cinco rutas nuevas, el plan de
`/iniciar` y el WebSocket- se prueba por HTTP, que es donde vive.

Y al final del archivo hay una seccion con el RELOJ INYECTADO, con los dos dobles
de `tests/test_sesion_carril.py`: lo que hay que ver ahi -el historial, el tempo
automatico y lo que pasa sin señal- depende de que el tramo se acabe, y con el
reloj de pared eso son decimas de segundo de espera y una carrera por medio. Con
el reloj a mano no hay ni espera ni carrera.
"""

import time
from dataclasses import replace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.piezas.estudio import FACTOR_MINIMO, PASO_DEL_FACTOR, PlanDePasada
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion
from nucleo.sintesis import Metronomo, SalidaAudio
from servidor import piezas as modulo_piezas
from servidor.app import crear_app
from servidor.configuracion import Configuracion
from servidor.piezas import SesionCarril
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


def pieza_de_doce_compases(secciones=()):
    """Doce compases de 4/4 a 60 ppm, una nota al principio de cada uno."""
    return Pieza(
        nombre="estudio",
        perfil="guitarra_estandar",
        tempo=60,
        compas=(4, 4),
        notas=tuple(
            NotaEnPieza(
                midi=40, cuerda=6, traste=0,
                inicio_pulsos=i * 4.0, duracion_pulsos=1.0,
            )
            for i in range(12)
        ),
        secciones=tuple(secciones),
    )


def pieza_rapida():
    """La misma pieza a 600 ppm: un compas de 4/4 dura 0,4 s de reloj de pared.

    El reloj de este carril es el de verdad -la fixture es la del servidor, no un
    reloj inyectado-, asi que las pruebas que necesitan ver acabarse un tramo lo
    hacen con una pieza en la que acabarse cuesta decimas de segundo. A 60 ppm
    serian cuatro segundos por compas, y eso en una suite de mil pruebas se nota.
    """
    return Pieza(
        nombre="rapida",
        perfil="guitarra_estandar",
        tempo=600,
        compas=(4, 4),
        notas=tuple(
            NotaEnPieza(
                midi=40, cuerda=6, traste=0,
                inicio_pulsos=i * 4.0, duracion_pulsos=1.0,
            )
            for i in range(4)
        ),
    )


def esperar(cliente, condicion, limite=5.0):
    """Consulta el estado hasta que `condicion` se cumpla. Devuelve el estado.

    El limite esta para que un fallo sea un fallo y no una suite colgada.
    """
    final = time.monotonic() + limite
    estado = cliente.get("/api/piezas/estado").json()
    while not condicion(estado) and time.monotonic() < final:
        time.sleep(0.01)
        estado = cliente.get("/api/piezas/estado").json()
    return estado


def iniciar(cliente, pieza=None, **plan):
    """Pone en marcha la pieza de doce compases con el plan pedido.

    Por la puerta del carril y no por HTTP, por lo que dice la cabecera del
    archivo. Devuelve lo MISMO que devolveria el endpoint, porque es la misma
    llamada: la pieza, las secciones en compases y el estado.
    """
    carril = cliente.app.state.carril
    return carril.iniciar(
        pieza_de_doce_compases() if pieza is None else pieza,
        PlanDePasada(**plan) if plan else None,
    )


def iniciar_por_http(cliente, **plan):
    """Pone en marcha un ejercicio del catalogo, con plan, por el endpoint.

    La escala son nueve compases, que es lo que hace falta para pedir un tramo de
    verdad. Es el camino del navegador: la pieza la elige el servidor y el plan
    viaja en el cuerpo.
    """
    cuerpo = {"familia": "escala", "parametros": {"tipo": "mayor"}}
    if plan:
        cuerpo["plan"] = plan
    return cliente.post("/api/piezas/iniciar", json=cuerpo)


def test_iniciar_sin_plan_se_comporta_como_la_etapa_3a(cliente):
    datos = iniciar(cliente)
    assert datos["factor_tempo"] == 1.0
    assert datos["en_bucle"] is False
    assert datos["primer_compas"] == 1
    assert datos["ultimo_compas"] == 12
    assert datos["compas_en_curso"] == 1
    # Y sigue trayendo la pieza entera una sola vez, como la etapa 3a.
    assert len(datos["pieza"]["notas"]) == 12


def test_iniciar_con_plan_arranca_en_el_compas_pedido(cliente):
    datos = iniciar(cliente, primer_compas=5, ultimo_compas=8, en_bucle=True)
    assert datos["compas_en_curso"] == 5
    assert datos["en_bucle"] is True
    # (Que el cabezal arranque en el compas 5 y no en cero se mide con el reloj
    # inyectado, en `test_con_un_plan_que_empieza_en_el_compas_cinco_el_cabezal_no_arranca_en_cero`:
    # con el reloj de pared el instante depende de cuanto tarde la prueba.)


def test_el_plan_del_cuerpo_llega_al_carril(cliente):
    """El camino del navegador: `/api/piezas/iniciar` con `plan`."""
    datos = iniciar_por_http(cliente, primer_compas=3, ultimo_compas=5, en_bucle=True).json()
    assert datos["compas_en_curso"] == 3
    assert datos["ultimo_compas"] == 5
    assert datos["en_bucle"] is True


def test_un_factor_fuera_de_rango_se_rechaza_con_cuatrocientos(cliente):
    respuesta = iniciar_por_http(cliente, factor_tempo=2.0)
    assert respuesta.status_code == 400
    assert "100" in respuesta.json()["detail"]


def test_un_compas_que_no_existe_se_rechaza_con_cuatrocientos(cliente):
    respuesta = iniciar_por_http(cliente, primer_compas=40)
    assert respuesta.status_code == 400
    assert "40" in respuesta.json()["detail"]


def test_un_plan_con_un_valor_de_otro_tipo_no_es_un_quinientos(cliente):
    """`{"primer_compas": null}` sale de Python como `TypeError`, no `ValueError`.

    Dejarlo subir lo convertia en un 500 -"el servidor se ha roto"-, que es
    mentira: es un pedido mal hecho, igual que un factor fuera de rango.
    """
    respuesta = iniciar_por_http(cliente, primer_compas=None)
    assert respuesta.status_code == 400
    assert cliente.post("/api/piezas/plan", json={"compases_de_cuenta_atras": "x"}).status_code == 400


def test_un_booleano_del_plan_que_no_es_booleano_se_rechaza(cliente):
    """`bool(...)` acepta cualquier cosa: `{"en_bucle": "no"}` valia True.

    Una cadena no vacia, un numero o una lista pasaban como True y el usuario se
    encontraba con un bucle que no habia pedido en vez de un 400 que se lo
    dijera. `int` y `float` ya rechazan lo que no es un numero; `bool` no rechaza
    nada, asi que el filtro de los tres booleanos del plan va en el servidor.
    """
    iniciar(cliente)
    for valor in ("no", "false", "", [], {}, 1, 0, None):
        assert cliente.post(
            "/api/piezas/plan", json={"en_bucle": valor}
        ).status_code == 400, f"en_bucle={valor!r} tenia que ser un 400"
    for campo in ("con_click", "tempo_automatico"):
        assert cliente.post("/api/piezas/plan", json={campo: "si"}).status_code == 400

    # Y los de verdad siguen pasando, por las dos puertas.
    datos = cliente.post(
        "/api/piezas/plan", json={"en_bucle": True, "con_click": False}
    ).json()
    assert datos["en_bucle"] is True
    assert datos["con_click"] is False
    assert iniciar_por_http(cliente, en_bucle="no").status_code == 400
    assert iniciar_por_http(cliente, en_bucle=True).json()["en_bucle"] is True


def test_cambiar_el_plan_no_reinicia_la_pasada(cliente):
    iniciar(cliente)
    cliente.post("/api/piezas/saltar", json={"compas": 6})
    datos = cliente.post("/api/piezas/plan", json={"factor_tempo": 0.5}).json()
    assert datos["factor_tempo"] == 0.5
    assert datos["compas_en_curso"] == 6
    assert datos["tempo_efectivo"] == 30.0


PLAN_COMPLETO = {
    "primer_compas": 3,
    "ultimo_compas": 6,
    "factor_tempo": 0.8,
    "en_bucle": True,
    "con_click": True,
    "tempo_automatico": True,
}


def test_el_estado_publica_el_click_y_el_tempo_automatico_del_plan(cliente):
    datos = iniciar(cliente, con_click=True, tempo_automatico=True)
    assert datos["con_click"] is True
    assert datos["tempo_automatico"] is True
    assert cliente.get("/api/piezas/estado").json()["tempo_automatico"] is True
    por_defecto = iniciar(cliente)
    assert por_defecto["con_click"] is False
    assert por_defecto["tempo_automatico"] is False
    # Y el carril apagado los publica en su valor de "nada que practicar".
    cliente.post("/api/piezas/detener")
    apagado = cliente.get("/api/piezas/estado").json()
    assert apagado["con_click"] is False
    assert apagado["tempo_automatico"] is False


def test_el_plan_con_solo_el_tempo_deja_intacto_lo_demas(cliente):
    iniciar(cliente, **PLAN_COMPLETO)
    datos = cliente.post("/api/piezas/plan", json={"factor_tempo": 0.7}).json()
    assert datos["factor_tempo"] == 0.7
    assert datos["primer_compas"] == 3
    assert datos["ultimo_compas"] == 6
    assert datos["en_bucle"] is True
    assert datos["con_click"] is True
    assert datos["tempo_automatico"] is True


def test_el_plan_con_solo_el_click_no_mueve_el_factor(cliente):
    iniciar(cliente, **PLAN_COMPLETO)
    datos = cliente.post("/api/piezas/plan", json={"con_click": False}).json()
    assert datos["con_click"] is False
    assert datos["factor_tempo"] == 0.8
    assert datos["primer_compas"] == 3
    assert datos["ultimo_compas"] == 6
    assert datos["en_bucle"] is True
    assert datos["tempo_automatico"] is True


def test_el_parche_conserva_y_cambia_los_compases_de_cuenta_atras(cliente):
    """El septimo campo del plan, el unico que el estado no publica.

    Por eso se lee en el plan vigente del nucleo: si el parche lo olvidara, volveria
    a su valor de fabrica (1) sin que nada del estado lo delatara.
    """
    iniciar(cliente, compases_de_cuenta_atras=0)
    cliente.post("/api/piezas/plan", json={"factor_tempo": 0.7})
    assert cliente.app.state.carril._estudio.plan.compases_de_cuenta_atras == 0
    cliente.post("/api/piezas/plan", json={"compases_de_cuenta_atras": 2})
    plan = cliente.app.state.carril._estudio.plan
    assert plan.compases_de_cuenta_atras == 2
    assert plan.factor_tempo == 0.7


def test_un_ultimo_compas_nulo_en_el_parche_vale_hasta_el_final(cliente):
    iniciar(cliente, **PLAN_COMPLETO)
    datos = cliente.post("/api/piezas/plan", json={"ultimo_compas": None}).json()
    assert datos["ultimo_compas"] == 12
    assert datos["primer_compas"] == 3


def test_dos_parches_de_campos_distintos_conservan_los_dos_cambios(cliente):
    iniciar(cliente, **PLAN_COMPLETO)
    cliente.post("/api/piezas/plan", json={"factor_tempo": 0.6})
    datos = cliente.post("/api/piezas/plan", json={"tempo_automatico": False}).json()
    assert datos["factor_tempo"] == 0.6
    assert datos["tempo_automatico"] is False
    assert datos["en_bucle"] is True
    assert datos["primer_compas"] == 3


def test_un_parche_a_medias_no_deja_que_otro_lea_el_plan_viejo(cliente, monkeypatch):
    """La carrera: el segundo parche NO puede fusionarse con el plan de antes.

    El primer parche se queda parado JUSTO DESPUES de leer el plan vigente. Con
    la lectura y el cambio en dos tomas del candado, el segundo parche leia ese
    mismo plan viejo, lo aplicaba, y luego el primero lo pisaba con el suyo: se
    perdia un cambio en silencio. Con una sola toma, el segundo espera y se
    fusiona sobre el plan nuevo. El `sleep` solo da tiempo a una implementacion
    mala de equivocarse: con la buena la prueba es determinista.
    """
    import threading

    from nucleo.piezas.estudio import SesionDeEstudio

    iniciar(cliente, **PLAN_COMPLETO)
    carril = cliente.app.state.carril
    dentro, soltar, primera = threading.Event(), threading.Event(), [True]
    leer = SesionDeEstudio.plan.fget

    def plan_lento(self):
        plan = leer(self)
        if primera[0]:
            primera[0] = False
            dentro.set()
            assert soltar.wait(5)
        return plan

    monkeypatch.setattr(SesionDeEstudio, "plan", property(plan_lento))
    uno = threading.Thread(target=carril.parchar_plan, args=({"factor_tempo": 0.6},))
    otro = threading.Thread(target=carril.parchar_plan, args=({"tempo_automatico": False},))
    uno.start()
    assert dentro.wait(5)
    otro.start()
    time.sleep(0.2)
    soltar.set()
    uno.join(5)
    otro.join(5)
    monkeypatch.undo()
    plan = carril._estudio.plan
    assert plan.factor_tempo == 0.6
    assert plan.tempo_automatico is False


def test_iniciar_con_un_plan_parcial_rellena_con_los_valores_de_fabrica(cliente):
    # Hay un plan vigente distinto del de fabrica, y `iniciar` NO lo hereda.
    iniciar(cliente, **PLAN_COMPLETO)
    datos = iniciar_por_http(cliente, factor_tempo=0.7).json()
    assert datos["factor_tempo"] == 0.7
    assert datos["primer_compas"] == 1
    assert datos["ultimo_compas"] == 9
    assert datos["en_bucle"] is False
    assert datos["con_click"] is False
    assert datos["tempo_automatico"] is False


def test_iniciar_sin_plan_da_el_plan_de_fabrica_aunque_hubiera_otro_vigente(cliente):
    iniciar(cliente, **PLAN_COMPLETO)
    datos = iniciar_por_http(cliente).json()
    assert datos["factor_tempo"] == 1.0
    assert datos["primer_compas"] == 1
    assert datos["en_bucle"] is False
    assert datos["con_click"] is False
    assert datos["tempo_automatico"] is False


def test_saltar_a_un_compas_mueve_el_cabezal(cliente):
    iniciar(cliente)
    datos = cliente.post("/api/piezas/saltar", json={"compas": 9}).json()
    assert datos["compas_en_curso"] == 9


def test_saltar_a_un_compas_que_no_existe_se_rechaza(cliente):
    iniciar(cliente)
    respuesta = cliente.post("/api/piezas/saltar", json={"compas": 99})
    assert respuesta.status_code == 400
    assert "99" in respuesta.json()["detail"]


def test_saltar_sin_decir_el_compas_se_rechaza_diciendolo(cliente):
    iniciar(cliente)
    respuesta = cliente.post("/api/piezas/saltar", json={})
    assert respuesta.status_code == 400
    assert "compas" in respuesta.json()["detail"].lower()


def test_la_pausa_del_usuario_es_distinta_de_la_falta_de_senal(cliente):
    iniciar(cliente)
    datos = cliente.post("/api/piezas/pausa", json={"activa": True}).json()
    # Las dos a la vez, y con valores distintos: el usuario ha pausado y el cable
    # sigue dando señal. Son dos cosas, no una con dos nombres.
    assert datos["en_pausa"] is True
    assert datos["pausado"] is False
    datos = cliente.post("/api/piezas/pausa", json={"activa": False}).json()
    assert datos["en_pausa"] is False
    assert datos["pausado"] is False


def test_la_pausa_del_usuario_congela_el_cabezal(cliente):
    """Que la pausa no sea solo una bandera: el reloj tiene que pararse.

    El carril de verdad lleva el reloj de pared, asi que si la pausa no llegara
    hasta el estudio -o el estudio no la respetara- el cabezal seguiria corriendo
    con la pantalla diciendo "en pausa".
    """
    iniciar(cliente)
    cliente.post("/api/piezas/pausa", json={"activa": True})
    antes = cliente.get("/api/piezas/estado").json()["instante_s"]
    for _ in range(20):
        despues = cliente.get("/api/piezas/estado").json()["instante_s"]
    assert despues == antes


def test_el_informe_trae_los_compases_del_tramo_y_el_historial(cliente):
    iniciar(cliente, primer_compas=2, ultimo_compas=3)
    datos = cliente.get("/api/piezas/informe").json()
    assert [c["numero"] for c in datos["informe"]["compases"]] == [2, 3]
    assert datos["historial"]["pasadas"] == 0
    assert datos["historial"]["peores_compases"] == []


def test_una_vuelta_del_bucle_suma_una_pasada_al_historial(cliente):
    """El detector de final, por el camino del bucle.

    Con un tramo de un compas, sin cuenta atras y sin señal que lo mueva, el reloj
    de pared basta para dar la vuelta: cada vuelta es una pasada del historial,
    porque la pregunta "ya te sale?" es sobre la vuelta que acaba de pasar.
    """
    iniciar(
        cliente, pieza=pieza_rapida(), primer_compas=1, ultimo_compas=1,
        en_bucle=True, compases_de_cuenta_atras=0,
    )
    estado = esperar(cliente, lambda e: e["repeticion"] > 1)
    assert estado["repeticion"] > 1
    assert cliente.get("/api/piezas/informe").json()["historial"]["pasadas"] == 1


def test_el_tramo_que_acaba_sin_bucle_suma_una_sola_pasada(cliente):
    """Sin bucle la pasada acaba UNA vez, y el historial no la cuenta mas.

    La instantanea se construye treinta veces por segundo: sin la marca
    `_termino_anunciado`, el final del tramo anotaria una pasada en cada mirada.
    """
    iniciar(cliente, pieza=pieza_rapida(), primer_compas=1, ultimo_compas=1)
    assert esperar(cliente, lambda e: e["completado"])["completado"] is True
    for _ in range(30):
        cliente.get("/api/piezas/estado")
    assert cliente.get("/api/piezas/informe").json()["historial"]["pasadas"] == 1


def test_el_historial_sobrevive_a_empezar_otra_pasada_de_la_misma_pieza(cliente):
    """Es justo para lo que esta: comparar la pasada de ahora con las de antes."""
    iniciar(cliente, pieza=pieza_rapida(), primer_compas=1, ultimo_compas=1)
    esperar(cliente, lambda e: e["completado"])
    assert cliente.get("/api/piezas/informe").json()["historial"]["pasadas"] == 1
    # La misma pieza otra vez: el historial es de la pieza, no de la pasada.
    iniciar(cliente, pieza=pieza_rapida(), primer_compas=1, ultimo_compas=1)
    assert cliente.get("/api/piezas/informe").json()["historial"]["pasadas"] == 1


def test_las_secciones_viajan_ya_convertidas_en_compases(cliente):
    # La interfaz no repite la cuenta del nucleo: elige de esta lista.
    pieza = pieza_de_doce_compases(
        secciones=(
            Seccion(nombre="Intro", inicio_pulsos=0.0),
            Seccion(nombre="Estribillo", inicio_pulsos=16.0),
        )
    )
    datos = iniciar(cliente, pieza=pieza)
    assert datos["secciones_en_compases"] == [
        {"nombre": "Intro", "primer_compas": 1, "ultimo_compas": 4},
        {"nombre": "Estribillo", "primer_compas": 5, "ultimo_compas": 12},
    ]
    # Y tambien al volver a pedir la pieza, que es quien las necesita de verdad:
    # el navegador recargado no tiene la respuesta de `iniciar`.
    assert cliente.get("/api/piezas/pieza").json()["secciones_en_compases"] == (
        datos["secciones_en_compases"]
    )


def test_sin_secciones_la_lista_viaja_vacia(cliente):
    assert iniciar(cliente)["secciones_en_compases"] == []


def test_la_pieza_en_marcha_se_puede_volver_a_pedir(cliente):
    # Es la deuda de la etapa 3a: la pieza viajaba una sola vez, asi que recargar
    # el navegador a mitad de cancion dejaba el carril en blanco.
    iniciar(cliente)
    datos = cliente.get("/api/piezas/pieza").json()
    assert datos["pieza"]["nombre"] == "estudio"
    assert len(datos["pieza"]["notas"]) == 12
    assert datos["compas_en_curso"] == 1


def test_sin_pieza_en_marcha_la_pieza_es_nula_y_no_es_un_error(cliente):
    datos = cliente.get("/api/piezas/pieza").json()
    assert datos["pieza"] is None
    assert datos["secciones_en_compases"] == []


def test_el_carril_apagado_publica_las_mismas_claves_que_el_encendido(cliente):
    """Una sola forma de estado: la interfaz no distingue dos.

    Si el estado apagado se quedara con los campos de la etapa 3a, cada lector
    tendria que preguntarse si hay pieza antes de leer `compas_en_curso`.
    """
    encendido = set(iniciar(cliente)) - {"pieza", "secciones_en_compases"}
    cliente.post("/api/piezas/detener")
    apagado = cliente.get("/api/piezas/estado").json()
    assert set(apagado) == encendido
    assert apagado["factor_sugerido"] is None


def test_los_endpoints_de_estudio_sin_pieza_en_marcha_dan_cuatrocientos(cliente):
    for metodo, ruta, cuerpo in (
        ("post", "/api/piezas/plan", {"factor_tempo": 0.5}),
        ("post", "/api/piezas/saltar", {"compas": 2}),
        ("post", "/api/piezas/pausa", {"activa": True}),
    ):
        respuesta = getattr(cliente, metodo)(ruta, json=cuerpo)
        assert respuesta.status_code == 400, ruta
        assert "pieza" in respuesta.json()["detail"].lower(), ruta
    assert cliente.get("/api/piezas/informe").status_code == 400


def test_el_websocket_publica_los_campos_del_estudio(cliente):
    iniciar(cliente, primer_compas=2, ultimo_compas=3, en_bucle=True)
    with cliente.websocket_connect(WS_LOCAL + "/ws/piezas") as ws:
        datos = ws.receive_json()
    for clave in ("compas_en_curso", "total_de_compases", "repeticion",
                  "cuenta_atras_restante_s", "factor_tempo", "tempo_efectivo",
                  "en_bucle", "en_pausa", "primer_compas", "ultimo_compas"):
        assert clave in datos, clave
    # Y los de la etapa 3a siguen donde estaban.
    for clave in ("instante_s", "indice_actual", "total", "completado", "tocadas",
                  "pausado", "arranque"):
        assert clave in datos, clave


# ---------------------------------------------------------------------------
# Con el reloj inyectado: el historial, el tempo automatico y la falta de señal
# ---------------------------------------------------------------------------


class RelojFalso:
    """Reloj que solo avanza cuando se le dice. Ninguna prueba espera de verdad."""

    def __init__(self):
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


class SesionAudioFalsa:
    """Doble de `Sesion` con `senal_ausente` mutable desde la prueba.

    Copiado de `tests/test_sesion_carril.py`: `SesionCarril` solo necesita de su
    sesion de audio tres cosas, asi que el doble tiene exactamente esas tres.
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


def _sin_dispositivo(**kwargs):
    raise OSError("sin dispositivo de audio")


def carril_a_mano(salida=None):
    """Un carril con el reloj y la señal en la mano de la prueba.

    Sin `salida` se le da una que NO tiene dispositivo: ninguna prueba abre el
    audio real, ni siquiera por descuido.
    """
    reloj = RelojFalso()
    sesion = SesionAudioFalsa()
    salida = salida or SalidaAudio(abrir_stream=_sin_dispositivo)
    return SesionCarril(sesion, reloj=reloj, salida=salida), sesion, reloj


def mirar_hasta(carril, reloj, condicion, pasos=400, paso=1 / 30.0):
    """Mueve el reloj en pasos de 33 ms consultando el estado, como el WebSocket.

    El tope de pasos esta para que un fallo sea un fallo y no una suite colgada.
    """
    estado = carril.estado()
    for _ in range(pasos):
        if condicion(estado):
            return estado
        reloj.avanzar(paso)
        estado = carril.estado()
    return estado


def test_iniciar_sin_senal_no_se_lleva_el_cabezal_al_principio():
    """El cabezal arranca donde diga el plan, tambien con el cable desenchufado.

    Es el cruce de las dos cosas: `iniciar` deja el reloj del servidor donde el
    estudio dice -compas 5, no cero-, y la primera mirada sin señal RECOLOCA el
    estudio en ese reloj. Si el reloj hubiera arrancado en cero, esa recolocacion
    se habria llevado el cabezal al principio de la pieza nada mas empezar.
    """
    carril, sesion, _ = carril_a_mano()
    sesion.senal_ausente = True
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(primer_compas=5))
        estado = carril.estado()
        assert estado["pausado"] is True
        assert estado["compas_en_curso"] == 5
        assert estado["instante_s"] == pytest.approx(16.0, abs=0.001)
    finally:
        carril.detener()
        sesion.detener()


def test_el_tempo_automatico_baja_el_factor_cuando_la_vuelta_sale_mal():
    """La vuelta entera sin tocar una nota: el carril baja un paso el tempo.

    Es el unico sitio donde el historial decide algo, y sin esta prueba la casilla
    `tempo_automatico` del plan podia quedarse sin conectar y nadie lo notaba.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(
                primer_compas=1, ultimo_compas=1, en_bucle=True,
                compases_de_cuenta_atras=0, tempo_automatico=True,
            ),
        )
        assert mirar_hasta(carril, reloj, lambda e: e["repeticion"] > 1)["repeticion"] == 2
        # La instantanea se arma ANTES de anotar la vuelta -el estado publicado es
        # el que se leyo, no el de despues-, asi que el factor nuevo se ve en la
        # mirada siguiente: 33 ms de retraso, que no se notan en pantalla.
        assert carril.estado()["factor_tempo"] == pytest.approx(1.0 - PASO_DEL_FACTOR)
    finally:
        carril.detener()
        sesion.detener()


def test_el_tempo_automatico_que_no_cambia_nada_no_se_come_la_cuenta_atras():
    """Con el factor ya en el suelo no hay nada que cambiar, y hay que NO tocarlo.

    `cambiar_plan` cancela la cuenta atras -es su contrato-, asi que llamarlo con
    el mismo factor que ya habia, solo porque el tempo automatico esta encendido,
    le quita al alumno el compas de preparacion de cada vuelta.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(
                primer_compas=1, ultimo_compas=1, en_bucle=True,
                compases_de_cuenta_atras=1, factor_tempo=FACTOR_MINIMO,
                tempo_automatico=True,
            ),
        )
        # Mas pasos que el defecto: ahora la primera entrada tambien lleva su cuenta
        # atras, asi que la primera vuelta tarda un compas mas en llegar.
        vuelta = mirar_hasta(carril, reloj, lambda e: e["repeticion"] > 1, pasos=1000)
        assert vuelta["repeticion"] == 2
        # La mirada SIGUIENTE a la vuelta, que es donde ya se ve lo que el
        # historial haya decidido (o no) hacer con el plan.
        estado = carril.estado()
        assert estado["factor_tempo"] == FACTOR_MINIMO
        assert estado["cuenta_atras_restante_s"] > 0
    finally:
        carril.detener()
        sesion.detener()


def test_cada_pieza_tiene_su_propio_historial():
    """Dos canciones distintas no comparten pasadas: la clave es el nombre.

    Sin esto, el "fallas el compas 19" de una cancion aparecia practicando otra.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(ultimo_compas=1))
        mirar_hasta(carril, reloj, lambda e: e["completado"])
        assert carril.informe()["historial"]["pasadas"] == 1

        otra = pieza_rapida()                 # se llama "rapida", no "estudio"
        carril.iniciar(otra, PlanDePasada(ultimo_compas=1))
        assert carril.informe()["historial"]["pasadas"] == 0
        # Y la primera no ha perdido la suya: volver a ella la encuentra.
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(ultimo_compas=1))
        assert carril.informe()["historial"]["pasadas"] == 1
    finally:
        carril.detener()
        sesion.detener()


def test_la_cuenta_atras_del_cuerpo_de_la_peticion_llega_al_plan(cliente):
    """`compases_de_cuenta_atras` no se publica en el estado, pero se nota.

    Con cero, la vuelta del bucle empieza a tocar enseguida; el valor por defecto
    es uno, asi que un ayudante que se olvidara de leer esta clave del cuerpo
    daria un compas de cuenta atras que nadie pidio.
    """
    iniciar(cliente, pieza=pieza_rapida())
    datos = cliente.post(
        "/api/piezas/plan",
        json={"ultimo_compas": 1, "en_bucle": True, "compases_de_cuenta_atras": 0},
    ).json()
    assert datos["en_bucle"] is True
    estado = esperar(cliente, lambda e: e["repeticion"] > 1)
    assert estado["repeticion"] > 1
    assert estado["cuenta_atras_restante_s"] == 0.0


def suena(nota):
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=0.9, nivel_db=-25.0,
        nota=nota, cents=0.0, posiciones=(),
    )


SILENCIO = ResultadoAnalisis(
    estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
    nota=None, cents=None, posiciones=(),
)


def publicar(sesion, reloj, resultado, cuadros=1, paso=0.021):
    """Publica cuadros de analisis como lo haria la sesion de audio de verdad.

    Copiado de `tests/test_sesion_carril.py`: el instante que acompaña a cada
    cuadro es el del reloj del ANALISIS, que en produccion es el mismo
    `time.monotonic()` que el del servidor.
    """
    for _ in range(cuadros):
        for observador in list(sesion.observadores):
            observador(resultado, reloj())
        reloj.avanzar(paso)


def pieza_de_dos_notas():
    """Dos notas en el compas 1, en los pulsos 0 y 2. A 60 ppm, 0 s y 2 s."""
    return Pieza(
        nombre="dos", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
        notas=(
            NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0),
            NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=2.0, duracion_pulsos=1.0),
        ),
    )


def test_el_historial_anota_la_vuelta_y_no_el_acumulado_de_la_pasada():
    """Una vuelta mala y una buena: la buena no arrastra los fallos de la mala.

    Es lo que distingue anotar `cerrar_repeticion()` -el informe de SOLO esa
    vuelta- de anotar `informe`, el acumulado de la pasada: con el acumulado, la
    vuelta limpia sale a medias porque las notas falladas de la anterior siguen
    contando, y el tempo automatico no deja de bajar nunca aunque el alumno ya lo
    haya sacado.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_dos_notas(),
            PlanDePasada(
                primer_compas=1, ultimo_compas=1, en_bucle=True,
                compases_de_cuenta_atras=0, tempo_automatico=True,
            ),
        )
        # Primera vuelta sin tocar nada: el tempo baja un paso.
        mirar_hasta(carril, reloj, lambda e: e["repeticion"] > 1)
        assert carril.estado()["factor_tempo"] == pytest.approx(1.0 - PASO_DEL_FACTOR)

        # Segunda vuelta con las dos notas tocadas en su sitio, y un silencio en
        # medio para que sean dos ataques y no uno sostenido.
        publicar(sesion, reloj, suena("E2"), cuadros=12)
        publicar(sesion, reloj, SILENCIO, cuadros=85)
        publicar(sesion, reloj, suena("E2"), cuadros=12)
        publicar(sesion, reloj, SILENCIO, cuadros=110)
        assert carril.estado()["repeticion"] == 3, "la segunda vuelta no se acabo"
        # Las dos notas de la vuelta buena salieron limpias, asi que su proporcion
        # es 1 y el tempo no vuelve a bajar. Si lo que se anotara fuera el
        # acumulado, esa misma vuelta valdria 2 de 4 -la mitad- y el factor
        # bajaria otro paso.
        assert carril.informe()["historial"]["pasadas"] == 2
        assert carril.estado()["factor_tempo"] == pytest.approx(1.0 - PASO_DEL_FACTOR)
    finally:
        carril.detener()
        sesion.detener()


def test_una_vuelta_se_anota_una_sola_vez_aunque_se_mire_mil_veces():
    """La marca `_repeticion_anunciada` es lo que lo impide.

    La instantanea se arma treinta veces por segundo, y la transicion que mira el
    detector de final -que `repeticion` haya cambiado- sigue siendo verdad en
    todas las miradas siguientes si la marca no se actualiza. Sin ella, una sola
    vuelta se anotaba treinta veces por segundo: el historial se llenaba de
    pasadas que nadie toco y el tempo automatico bajaba al suelo en un segundo.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(
                primer_compas=1, ultimo_compas=1, en_bucle=True,
                compases_de_cuenta_atras=0,
            ),
        )
        mirar_hasta(carril, reloj, lambda e: e["repeticion"] > 1)
        # Sin mover el reloj: no hay vuelta nueva que anotar, solo miradas.
        for _ in range(30):
            carril.estado()
        assert carril.informe()["historial"]["pasadas"] == 1
    finally:
        carril.detener()
        sesion.detener()


def test_la_pieza_siguiente_anota_su_pasada_y_no_hereda_las_marcas():
    """Las marcas del detector son de la pieza que estaba, no de la que viene.

    Si sobrevivieran a `detener` y a `iniciar`, la pieza nueva arrancaria con "el
    tramo ya termino" y "la repeticion ya cambio" puestos, y su pasada no se
    anotaria NUNCA: el historial de la segunda cancion de la tarde se quedaba
    vacio para siempre.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(ultimo_compas=1))
        mirar_hasta(carril, reloj, lambda e: e["completado"])
        assert carril.informe()["historial"]["pasadas"] == 1

        carril.iniciar(pieza_rapida(), PlanDePasada(ultimo_compas=1))
        mirar_hasta(carril, reloj, lambda e: e["completado"])
        assert carril.informe()["historial"]["pasadas"] == 1
    finally:
        carril.detener()
        sesion.detener()


def test_tras_la_cuenta_atras_el_cabezal_no_salta_hacia_delante():
    """La regla del reloj, medida dejando que la cuenta atras se agote de verdad.

    Es la prueba del paso 5 del brief, reescrita con el reloj inyectado. La que
    venia alli -mirar el estado sin dejar pasar tiempo y pedir `instante_s <= 1`-
    no podia fallar: `TECHO_TRAMO_S` acota cada mirada a 0,1 s, asi que ese limite
    era cierto para cualquier implementacion, y la prueba llevaba el nombre de la
    regla sin vigilarla.

    Lo que se vigila aqui es el salto de verdad: durante la cuenta atras el reloj
    del estudio esta QUIETO en el inicio del tramo, y si el servidor llevara su
    propia cuenta en paralelo, al acabarla el cabezal estaria un compas entero mas
    adelante -los 4 s de la cuenta- en vez de en el inicio. El tramo es el compas
    2 (de 4 s a 8 s) para que el inicio no sea cero y el error no se confunda con
    un cabezal en reposo.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(
                primer_compas=2, ultimo_compas=2, en_bucle=True,
                compases_de_cuenta_atras=1,
            ),
        )
        assert carril.estado()["instante_s"] == pytest.approx(4.0, abs=0.001)

        # Una vuelta entera, que abre la cuenta atras de un compas (4 s).
        estado = mirar_hasta(carril, reloj, lambda e: e["repeticion"] > 1)
        assert estado["repeticion"] == 2
        assert estado["cuenta_atras_restante_s"] == pytest.approx(4.0, abs=0.05)

        # Y la cuenta se agota mirando, como en produccion.
        estado = mirar_hasta(carril, reloj, lambda e: e["cuenta_atras_restante_s"] == 0)
        assert estado["cuenta_atras_restante_s"] == 0.0
        assert estado["instante_s"] == pytest.approx(4.0, abs=0.05), (
            "el cabezal salto hacia delante el tamaño de la cuenta atras"
        )
        assert estado["compas_en_curso"] == 2

        # Y a partir de ahi el tramo corre desde su inicio, no desde el salto.
        estado = mirar_hasta(carril, reloj, lambda e: e["instante_s"] >= 5.0)
        assert estado["instante_s"] == pytest.approx(5.0, abs=0.05)
        # Con la señal perdida, el cabezal se queda donde esta: la rama de la
        # pausa coloca el estudio en el reloj de esta clase, asi que si ese reloj
        # no fuera el espejo del estudio, aqui se veria.
        sesion.senal_ausente = True
        estado = carril.estado()
        assert estado["pausado"] is True
        assert estado["instante_s"] == pytest.approx(5.0, abs=0.05)
    finally:
        carril.detener()
        sesion.detener()


def test_el_reloj_se_clava_en_el_final_aunque_el_audio_se_corte_dentro_de_la_ventana():
    """El tope del aplazamiento de `_al_dia`, que es donde el diff se rompio solo.

    Acabar el tramo CON audio entrando abre la ventana de ataques en vuelo, y esa
    ventana se mide con el reloj del ANALISIS, que solo mueve `procesar`. Asi que
    si el audio se para justo despues -el caso normal: el alumno acaba la pasada y
    deja de tocar, o desenchufa-, la resta se congela por debajo de la ventana y
    decia «si» para siempre: `_al_dia` no clavaba el reloj nunca y el `avanzar` sin
    cuadros lo empujaba `TECHO_TRAMO_S` por mirada, sin limite. Medido con el tramo
    acabando en 8,0 s: a los 10 s de miradas el cabezal iba por 17,8, y a los 40 s
    por 47,8.

    Es exactamente el invariante que el aplazamiento prometia conservar, asi que la
    prueba mide lo prometido: pasada la ventana, el cabezal se queda en el final del
    tramo por muchas miradas que pasen.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        # A 600 ppm el compas 1 de 4/4 acaba en 0,4 s, y la cuenta atras del plan
        # por defecto dura otros 0,4: los dos se agotan con cuadros de audio, que es
        # lo que hace falta aqui (el tramo tiene que acabarse CON audio).
        carril.iniciar(pieza_rapida(), PlanDePasada(primer_compas=1, ultimo_compas=1))
        final_del_tramo = 0.4
        for _ in range(200):
            publicar(sesion, reloj, SILENCIO, cuadros=1)
            if carril.estado()["tramo_terminado"]:
                break
        estado = carril.estado()
        assert estado["tramo_terminado"] is True, "el tramo no se acabo con audio"
        # Con audio el cabezal se pasa del final mientras la ventana esta abierta, y
        # el exceso esta acotado por ella: es el precio declarado del aplazamiento.
        exceso = estado["instante_s"] - final_del_tramo
        assert 0 <= exceso <= 0.25 + 0.03, f"exceso de {exceso:.3f} s con audio"

        # Y ahora se corta el audio: ni un cuadro mas, solo las miradas del
        # WebSocket. Diez segundos de miradas y el cabezal sigue en el final.
        estado = mirar_hasta(carril, reloj, lambda e: False, pasos=300)
        assert estado["instante_s"] == pytest.approx(final_del_tramo, abs=1e-6)
        # Y no es que se haya quedado quieto un rato: cuarenta segundos despues,
        # igual. Sin el tope, aqui iba por 47,8.
        estado = mirar_hasta(carril, reloj, lambda e: False, pasos=1200)
        assert estado["instante_s"] == pytest.approx(final_del_tramo, abs=1e-6)
        assert estado["tramo_terminado"] is True
    finally:
        carril.detener()
        sesion.detener()


def test_el_tempo_automatico_sin_bucle_sugiere_y_no_reinicia_la_pasada():
    """Sin bucle la pasada se ha acabado, y no hay nada que acelerar.

    Aplicar el plan aqui arrancaba solo un bucle que nadie pidio: `cambiar_plan`
    recoloca el cabezal cuando el pulso cae fuera del tramo y limpia
    `tramo_terminado`, asi que la pantalla decia "terminado" una mirada y luego el
    carril volvia al principio y se ponia a correr, y esa pasada fantasma no se
    anotaba nunca. La sugerencia viaja en el estado y la aplica la interfaz al
    empezar la pasada siguiente.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(primer_compas=2, ultimo_compas=2, tempo_automatico=True),
        )
        estado = mirar_hasta(carril, reloj, lambda e: e["completado"])
        assert estado["completado"] is True
        acabado = estado["instante_s"]
        assert acabado == pytest.approx(8.0, abs=0.05)

        # La mirada siguiente, que es donde el detector ya ha anotado la pasada.
        estado = carril.estado()
        assert estado["factor_sugerido"] == pytest.approx(1.0 - PASO_DEL_FACTOR)
        assert estado["factor_tempo"] == 1.0, "el plan no se toca con la pasada acabada"
        assert estado["completado"] is True
        assert estado["compas_en_curso"] == 2
        assert estado["instante_s"] == pytest.approx(acabado, abs=0.001)

        # Y sigue quieto mirada tras mirada: nadie arranca una pasada nueva.
        estado = mirar_hasta(carril, reloj, lambda e: False, pasos=30)
        assert estado["instante_s"] == pytest.approx(acabado, abs=0.001)
        assert estado["completado"] is True
        # Una sola pasada anotada, no una por mirada.
        assert carril.informe()["historial"]["pasadas"] == 1

        # Y la sugerencia es de la pasada que acabo: la siguiente empieza limpia,
        # porque si no la pantalla ofreceria bajar un tempo que ya esta bajado.
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(primer_compas=2, ultimo_compas=2, tempo_automatico=True),
        )
        assert carril.estado()["factor_sugerido"] is None
    finally:
        carril.detener()
        sesion.detener()


def test_el_tempo_automatico_con_bucle_aplica_el_factor_y_no_sugiere_nada():
    """Con bucle la vuelta siguiente empieza ya, asi que el factor se aplica.

    El cabezal lo esta recolocando el propio bucle, de modo que `cambiar_plan` no
    puede arrancar nada que no estuviera arrancado. Y entonces no hay nada que
    sugerir: `factor_sugerido` se queda a None, porque ya esta hecho.

    El tramo es el compas 2 y la señal se pierde SIN ninguna mirada por medio, y
    las dos cosas son a proposito: `cambiar_plan` deja el cabezal en el mismo
    PULSO, que con el factor nuevo es otro segundo (4 / 0,95 = 4,21), asi que si
    el carril no adoptara el reloj que devuelve esa llamada, la primera mirada sin
    señal recolocaria el cabezal 0,21 s antes de donde el estudio lo tiene. Con el
    tramo empezando en el compas 1 los dos numeros serian cero y no se veria.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(
                primer_compas=2, ultimo_compas=2, en_bucle=True,
                compases_de_cuenta_atras=0, tempo_automatico=True,
            ),
        )
        mirar_hasta(carril, reloj, lambda e: e["repeticion"] > 1)
        # Sin mirar: la vuelta acaba de pasar y el factor acaba de cambiar.
        sesion.senal_ausente = True
        estado = carril.estado()
        assert estado["factor_tempo"] == pytest.approx(1.0 - PASO_DEL_FACTOR)
        assert estado["factor_sugerido"] is None
        assert estado["pausado"] is True
        # El cabezal cae en el inicio del tramo MAS el exceso con que el reloj
        # cruzo el final, y el exceso de una mirada es como mucho un paso de
        # mirada (33 ms), que el cambio de factor divide por 0,95. La igualdad
        # pelada con 4/0,95 que habia aqui media el defecto que la T7 arreglo: el
        # exceso se tiraba, y tirarlo es lo que arrastraba el reloj del bucle 36 ms
        # por vuelta. Lo que esta prueba vigila de verdad sigue vigilado: la
        # distancia a 4/0,95 es de una mirada, no de los 0,21 s que saldrian si el
        # carril no adoptara el reloj que `cambiar_plan` devuelve.
        #
        # Los 2 ms de holgura por arriba son el redondeo a tres decimales de
        # `a_dict`, no margen de medicion.
        assert 4.0 / 0.95 <= estado["instante_s"] <= (4.0 + 1 / 30.0) / 0.95 + 0.002
        # El cabezal esta clavado en la frontera del compas 2, que es donde el
        # viaje de segundos a pulsos por el factor se equivocaba de compas antes
        # de que `_pulsos` redondeara (ver `test_el_compas_de_la_frontera_...` en
        # `tests/test_estudio.py`).
        assert estado["compas_en_curso"] == 2
    finally:
        carril.detener()
        sesion.detener()


def test_una_orden_del_usuario_no_se_pierde_si_la_senal_ya_se_fue():
    """El caso de la etapa 3a: dispositivo desaparecido y nadie mirando.

    La rama de la pausa coloca el estudio en `self._instante`, asi que si ese
    reloj solo se refrescara al final de la mirada, la primera orden del usuario
    tras el apagon se perdia: el salto -o el plan nuevo- se iba al sitio de antes.
    A 30 Hz lo tapa el WebSocket, pero el caso que importa es justo el que no
    tiene a nadie mirando.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(pieza_de_doce_compases())
        mirar_hasta(carril, reloj, lambda e: e["instante_s"] >= 1.0)

        # La señal se va, y NADIE mira entre eso y la orden: la orden misma es la
        # primera mirada, la unica que entra por la rama de la pausa.
        sesion.senal_ausente = True
        assert carril.saltar(9)["compas_en_curso"] == 9
        assert carril.estado()["compas_en_curso"] == 9

        # Y lo mismo con el plan, que es la otra orden que mueve el cabezal. Hay
        # que volver a perder la señal desde cero: con el carril ya pausado, la
        # rama de la pausa no se vuelve a pisar y el fallo no se veria.
        sesion.senal_ausente = False
        mirar_hasta(carril, reloj, lambda e: e["instante_s"] >= 33.0)
        sesion.senal_ausente = True
        assert carril.cambiar_plan(
            PlanDePasada(primer_compas=4, ultimo_compas=6)
        )["compas_en_curso"] == 4
        assert carril.estado()["compas_en_curso"] == 4
    finally:
        carril.detener()
        sesion.detener()


def test_la_sugerencia_no_sobrevive_a_empezar_otra_pasada_con_un_salto():
    """Saltar es empezar a tocar otra vez, y la sugerencia era de la pasada vieja.

    Medido: tras acabar un tramo sin bucle y saltar al compas de salida, el estado
    daba `completado False` y `instante_s` en el inicio -o sea, pasada nueva- con
    el `factor_sugerido` de la anterior todavia puesto. Si el usuario ignora la
    sugerencia y toca una pasada cuyo resultado no mueve el factor, la pantalla
    seguiria ofreciendo un cambio que el historial ya no dice: el detector solo
    escribe la sugerencia, nunca la borra.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(primer_compas=2, ultimo_compas=2, tempo_automatico=True),
        )
        mirar_hasta(carril, reloj, lambda e: e["completado"])
        assert carril.estado()["factor_sugerido"] == pytest.approx(1.0 - PASO_DEL_FACTOR)

        estado = carril.saltar(2)
        assert estado["completado"] is False      # la pasada nueva ya ha empezado
        assert estado["instante_s"] == pytest.approx(4.0, abs=0.001)
        assert estado["factor_sugerido"] is None
    finally:
        carril.detener()
        sesion.detener()


def test_aplicar_la_sugerencia_con_un_plan_nuevo_la_deja_a_cero():
    """Quien aplica la sugerencia manda un plan, y entonces ya no hay nada que ofrecer.

    Sin esto, la interfaz aplicaria el factor sugerido y seguiria viendo la misma
    sugerencia publicada, asi que ofreceria aplicar otra vez lo que acaba de hacer.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(primer_compas=2, ultimo_compas=2, tempo_automatico=True),
        )
        mirar_hasta(carril, reloj, lambda e: e["completado"])
        sugerido = carril.estado()["factor_sugerido"]
        assert sugerido == pytest.approx(1.0 - PASO_DEL_FACTOR)

        estado = carril.cambiar_plan(
            PlanDePasada(
                primer_compas=2, ultimo_compas=2, factor_tempo=sugerido,
                tempo_automatico=True,
            )
        )
        assert estado["factor_tempo"] == pytest.approx(sugerido)
        assert estado["factor_sugerido"] is None
    finally:
        carril.detener()
        sesion.detener()


# ---------------------------------------------------------------------------
# El click de metronomo
# ---------------------------------------------------------------------------


class StreamFalso:
    """Un stream de salida que cuenta las escrituras. Nunca abre audio."""

    def __init__(self, **kwargs) -> None:
        self.escrituras = 0
        self.cerrado = False

    def start(self) -> None:
        pass

    def write(self, muestras) -> None:
        self.escrituras += 1

    def stop(self) -> None:
        pass

    def close(self) -> None:
        self.cerrado = True


def salida_falsa():
    """Una `SalidaAudio` de verdad sobre un stream de mentira, y el stream."""
    streams = []

    def abrir_stream(**kwargs):
        streams.append(StreamFalso(**kwargs))
        return streams[-1]

    return SalidaAudio(abrir_stream=abrir_stream), streams


def salida_muda():
    """Una `SalidaAudio` a la que le falla el dispositivo: `activa` es False."""
    return SalidaAudio(abrir_stream=_sin_dispositivo)


@pytest.fixture
def cliente_con_salida(tmp_path):
    """El mismo cliente, con la salida de audio que le pase la prueba."""
    abiertos = []

    def construir(salida):
        sesion = Sesion(
            Configuracion(dispositivo=3),
            crear_captura=lambda **kw: CapturaFalsa(**kw),
            listar=lambda: [CABLE],
        )
        sesion.iniciar()
        carril = SesionCarril(sesion, salida=salida)
        app = crear_app(sesion, carril=carril)
        app.state.ruta_config = tmp_path / "config.json"
        abiertos.append((sesion, carril))
        return app

    yield construir
    for sesion, carril in abiertos:
        carril.detener()
        sesion.detener()


def test_con_click_el_estado_dice_que_suena(cliente_con_salida):
    salida, streams = salida_falsa()
    with TestClient(cliente_con_salida(salida), base_url=BASE_LOCAL) as cliente:
        assert iniciar(cliente, con_click=True)["click_sonando"] is True
        # Y suena de verdad: el hilo del metronomo escribe en la salida.
        esperar_a = time.monotonic() + 3.0
        while streams[0].escrituras == 0 and time.monotonic() < esperar_a:
            time.sleep(0.01)
        assert streams[0].escrituras > 0


def test_sin_salida_de_audio_el_click_no_miente(cliente_con_salida):
    # El interruptor estaba pedido, pero no hay dispositivo: el estado dice que
    # NO suena, para que la interfaz escriba "sin click" en vez de mostrar un
    # interruptor encendido que no hace nada.
    with TestClient(cliente_con_salida(salida_muda()), base_url=BASE_LOCAL) as cliente:
        datos = iniciar(cliente, con_click=True)
        assert datos["click_sonando"] is False
        assert datos["pausado"] is False


def test_sin_pedir_click_no_suena_ni_se_abre_la_salida(cliente_con_salida):
    salida, streams = salida_falsa()
    with TestClient(cliente_con_salida(salida), base_url=BASE_LOCAL) as cliente:
        assert iniciar(cliente)["click_sonando"] is False
        assert streams == []


def test_apagar_el_click_desde_el_plan_lo_para_y_encenderlo_lo_devuelve(cliente_con_salida):
    salida, streams = salida_falsa()
    with TestClient(cliente_con_salida(salida), base_url=BASE_LOCAL) as cliente:
        iniciar(cliente, con_click=True)
        datos = cliente.post("/api/piezas/plan", json={"con_click": False}).json()
        assert datos["click_sonando"] is False
        assert streams[0].cerrado is True
        datos = cliente.post("/api/piezas/plan", json={"con_click": True}).json()
        assert datos["click_sonando"] is True


def test_un_tempo_que_el_metronomo_no_acepta_deja_la_pasada_en_pie(cliente_con_salida):
    # 400 ppm esta por encima de TEMPO_MAXIMO_PPM: el Metronomo lo rechaza. La
    # pasada no se cae, solo se queda sin click.
    salida, streams = salida_falsa()
    with TestClient(cliente_con_salida(salida), base_url=BASE_LOCAL) as cliente:
        pieza = replace(pieza_de_doce_compases(), tempo=400)
        datos = iniciar(cliente, pieza=pieza, con_click=True)
        assert datos["click_sonando"] is False
        assert datos["total_de_compases"] == 12
        assert cliente.get("/api/piezas/estado").status_code == 200


def test_un_tempo_redondeado_a_cero_tampoco_tumba_la_pasada(cliente_con_salida):
    # Tempo 1 con el factor minimo redondea a 0: por debajo de 1 el Metronomo
    # tambien lo rechaza.
    salida, _ = salida_falsa()
    with TestClient(cliente_con_salida(salida), base_url=BASE_LOCAL) as cliente:
        pieza = replace(pieza_de_doce_compases(), tempo=1)
        datos = iniciar(cliente, pieza=pieza, con_click=True, factor_tempo=FACTOR_MINIMO)
        assert datos["click_sonando"] is False


def test_detener_la_pieza_para_el_click_y_cierra_la_salida(cliente_con_salida):
    salida, streams = salida_falsa()
    with TestClient(cliente_con_salida(salida), base_url=BASE_LOCAL) as cliente:
        iniciar(cliente, con_click=True)
        assert cliente.post("/api/piezas/detener").json()["click_sonando"] is False
        assert streams[0].cerrado is True


class MetronomoEspia(Metronomo):
    """Un metronomo sin hilo: valida y pausa como el de verdad, y apunta todo.

    Con el hilo real una prueba tendria que esperar y mirar clicks; aqui lo que se
    comprueba es CUANDO el carril lo crea, con que tempo y compas, y si lo pausa.
    """

    creados: list = []

    def __init__(self, tempo, compas=4, salida=None):
        super().__init__(tempo, compas, salida)
        self.vivo = False
        MetronomoEspia.creados.append(self)

    @property
    def sonando(self) -> bool:
        return self.vivo

    def iniciar(self) -> bool:
        self.vivo = self._salida.activa
        return self.vivo

    def detener(self) -> None:
        self.vivo = False


@pytest.fixture
def espia(monkeypatch):
    MetronomoEspia.creados = []
    monkeypatch.setattr(modulo_piezas, "Metronomo", MetronomoEspia)
    return MetronomoEspia.creados


PLAN_DE_BUCLE_CON_CLICK = dict(
    primer_compas=1, ultimo_compas=1, en_bucle=True,
    compases_de_cuenta_atras=0, con_click=True,
)


def test_el_click_nace_con_el_tempo_efectivo_y_el_compas_de_la_pieza(espia):
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        pieza = replace(pieza_de_doce_compases(), tempo=75, compas=(3, 4))
        carril.iniciar(pieza, PlanDePasada(con_click=True, factor_tempo=0.85))
        assert len(espia) == 1
        # round(75 * 0.85) = round(63,75) = 64 (int daria 63). Y el periodo del
        # acento son los PULSOS del compas: un 3/4 son tres negras, o sea 3. En
        # 3/4 coincide con el numerador; donde no coincide lo mide
        # `test_el_acento_del_click_cuenta_los_pulsos_del_compas...`.
        assert (espia[0].tempo, espia[0].compas) == (64, 3)
    finally:
        carril.detener()
        sesion.detener()


@pytest.mark.parametrize(
    "compas, periodo", [((4, 4), 4), ((3, 4), 3), ((6, 8), 3), ((7, 8), 4)]
)
def test_el_acento_del_click_cuenta_los_pulsos_del_compas_y_no_el_numerador(
    espia, compas, periodo
):
    """El `Metronomo` acentua cada `compas` CLICKS, y un click es un PULSO.

    El pulso del modelo es la negra -`compases.pulsos_por_compas` convierte con
    `num*4/den`-, asi que pasarle el numerador acierta en 4/4 y en 3/4, donde los
    dos numeros coinciden, y falla en todo lo demas: en 6/8 el compas son 3 negras
    y el acento caia cada 6, y en 7/8 son 3,5 y caia cada 7, o sea cada dos
    compases y nunca sobre la misma nota. Dentro de la propia etapa las dos
    cuentas se contradecian, porque la cuenta atras si usa `pulsos_por_compas`.

    La spec §5 decia literalmente `compas = pieza.compas[0]` y la implementacion
    la copio: es un defecto de la spec, y se decide contra ella. En 7/8 el periodo
    es 4 porque el metronomo cuenta clicks enteros y `round(3.5)` es 4.
    """
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        pieza = replace(pieza_de_doce_compases(), compas=compas)
        carril.iniciar(pieza, PlanDePasada(con_click=True))
        assert len(espia) == 1
        assert espia[0].compas == periodo
    finally:
        carril.detener()
        sesion.detener()


def test_el_click_se_rearranca_en_cada_repeticion_y_solo_en_ellas(espia):
    salida, streams = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(**PLAN_DE_BUCLE_CON_CLICK))
        assert len(espia) == 1
        # Mirar muchas veces dentro de la misma vuelta no lo toca.
        for _ in range(5):
            reloj.avanzar(1 / 30.0)
            carril.estado()
        assert len(espia) == 1
        mirar_hasta(carril, reloj, lambda e: e["repeticion"] == 2)
        assert len(espia) == 2
        assert espia[0].vivo is False and espia[1].vivo is True
        mirar_hasta(carril, reloj, lambda e: e["repeticion"] == 3)
        assert len(espia) == 3
        # La salida no se cierra y se reabre en cada compas: es la misma.
        assert len(streams) == 1 and streams[0].cerrado is False
    finally:
        carril.detener()
        sesion.detener()


def test_un_cambio_de_tempo_rearranca_el_click(espia):
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(con_click=True))
        carril.cambiar_plan(PlanDePasada(con_click=True, factor_tempo=0.5))
        assert [m.tempo for m in espia] == [60, 30]
        assert espia[0].vivo is False and espia[1].vivo is True
    finally:
        carril.detener()
        sesion.detener()


def test_el_click_se_pausa_sin_senal_y_se_reanuda_al_volver(espia):
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(con_click=True))
        assert espia[0].pausado is False
        sesion.senal_ausente = True
        reloj.avanzar(1 / 30.0)
        estado = carril.estado()
        assert estado["pausado"] is True
        assert espia[0].pausado is True
        # Pausado no es parado: el estado sigue diciendo que el click existe.
        assert estado["click_sonando"] is True
        sesion.senal_ausente = False
        reloj.avanzar(1 / 30.0)
        carril.estado()
        assert espia[0].pausado is False
        assert len(espia) == 1
    finally:
        carril.detener()
        sesion.detener()


def test_un_click_que_no_se_pudo_abrir_no_reintenta_el_dispositivo_en_cada_mirada(espia):
    # El estado se consulta a 30 Hz: reabrir el dispositivo en cada consulta, con
    # los altavoces desenchufados, seria un intento de abrir audio 30 veces por
    # segundo bajo el candado. Se reintenta en la vuelta siguiente, no antes.
    intentos = []

    def abrir_stream(**kwargs):
        intentos.append(1)
        raise OSError("sin dispositivo")

    carril, sesion, reloj = carril_a_mano(SalidaAudio(abrir_stream=abrir_stream))
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(**PLAN_DE_BUCLE_CON_CLICK))
        for _ in range(10):
            reloj.avanzar(1 / 30.0)
            assert carril.estado()["click_sonando"] is False
        assert len(intentos) == 1
        mirar_hasta(carril, reloj, lambda e: e["repeticion"] == 2)
        assert len(intentos) == 2
    finally:
        carril.detener()
        sesion.detener()


def test_el_observador_no_toca_el_click(espia):
    # El click se ajusta desde la instantanea y NO desde el hilo de analisis, donde
    # `Metronomo.detener()` bloquearia hasta un segundo. Aqui el audio hace dar la
    # vuelta al bucle sin que nadie pida el estado: el click no se entera hasta
    # que alguien lo pide.
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(**PLAN_DE_BUCLE_CON_CLICK))
        assert len(espia) == 1
        publicar(sesion, reloj, SILENCIO, cuadros=250)
        assert len(espia) == 1
        assert carril.estado()["repeticion"] >= 2
        assert len(espia) == 2
    finally:
        carril.detener()
        sesion.detener()


def test_el_click_se_pausa_con_la_pausa_del_usuario_y_se_reanuda(espia):
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(con_click=True))
        assert espia[0].pausado is False
        carril.pausa(True)
        assert espia[0].pausado is True
        assert carril.estado()["click_sonando"] is True  # pausado no es parado
        carril.pausa(False)
        assert espia[0].pausado is False
        assert len(espia) == 1  # sin rearrancar: pausar no paga el join
    finally:
        carril.detener()
        sesion.detener()


def test_la_pausa_del_usuario_y_la_de_senal_no_se_pisan_el_click(espia):
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(con_click=True))
        carril.pausa(True)
        sesion.senal_ausente = True
        reloj.avanzar(1 / 30.0)
        carril.estado()
        sesion.senal_ausente = False
        reloj.avanzar(1 / 30.0)
        carril.estado()
        # Vuelve la señal pero el usuario sigue en pausa: el click sigue callado.
        assert espia[0].pausado is True
    finally:
        carril.detener()
        sesion.detener()


def test_al_acabar_el_tramo_sin_bucle_el_click_se_para_y_la_pasada_siguiente_lo_arranca(espia):
    salida, streams = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(
                primer_compas=1, ultimo_compas=1, compases_de_cuenta_atras=0, con_click=True
            ),
        )
        assert carril.estado()["click_sonando"] is True
        estado = mirar_hasta(carril, reloj, lambda e: e["tramo_terminado"])
        assert estado["tramo_terminado"] is True
        estado = carril.estado()
        assert estado["click_sonando"] is False
        assert espia[0].vivo is False
        assert streams[0].cerrado is True
        # Mirar el informe cien veces no lo vuelve a arrancar.
        for _ in range(5):
            reloj.avanzar(1 / 30.0)
            assert carril.estado()["click_sonando"] is False
        assert len(espia) == 1
        # La pasada siguiente (saltar al principio) lo arranca de nuevo.
        assert carril.saltar(1)["click_sonando"] is True
        assert len(espia) == 2
    finally:
        carril.detener()
        sesion.detener()


def test_con_bucle_el_click_no_se_para_al_llegar_al_final_del_tramo(espia):
    salida, _ = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(pieza_de_doce_compases(), PlanDePasada(**PLAN_DE_BUCLE_CON_CLICK))
        estado = mirar_hasta(carril, reloj, lambda e: e["repeticion"] == 2)
        assert estado["click_sonando"] is True
        # OJO: esto es un TESTIGO de frontera y NO cubre la guarda `and not
        # estado.en_bucle` de `_ajustar_click`: con bucle el nucleo nunca pone
        # `tramo_terminado`, asi que esta prueba pasaria igual sin la guarda.
    finally:
        carril.detener()
        sesion.detener()


def test_con_un_plan_que_empieza_en_el_compas_cinco_el_cabezal_no_arranca_en_cero():
    """El compas 5 de 4/4 a 60 ppm son 16 s. Con el reloj inyectado no hay carrera."""
    carril, sesion, _ = carril_a_mano()
    try:
        datos = carril.iniciar(
            pieza_de_doce_compases(),
            PlanDePasada(primer_compas=5, ultimo_compas=8, en_bucle=True),
        )
        assert datos["compas_en_curso"] == 5
        assert datos["instante_s"] == pytest.approx(16.0, abs=0.001)
    finally:
        carril.detener()
        sesion.detener()


def test_un_tempo_rechazado_a_mitad_de_pasada_no_deja_la_salida_abierta(espia):
    """Suena a 1 ppm; el factor minimo lo deja en round(0,4) = 0, que el metronomo
    rechaza, y el click se para. La salida tiene que cerrarse con el: abierta y
    sin nada que suene retendria el dispositivo del usuario."""
    salida, streams = salida_falsa()
    carril, sesion, reloj = carril_a_mano(salida)
    try:
        carril.iniciar(replace(pieza_de_doce_compases(), tempo=1), PlanDePasada(con_click=True))
        assert len(streams) == 1 and streams[0].cerrado is False
        estado = carril.cambiar_plan(PlanDePasada(con_click=True, factor_tempo=FACTOR_MINIMO))
        assert estado["click_sonando"] is False
        assert len(streams) == 1
        assert streams[0].cerrado is True
        assert salida.activa is False
        # Y no se reabre en cada consulta mientras el tempo siga rechazado.
        for _ in range(5):
            reloj.avanzar(1 / 30.0)
            carril.estado()
        assert len(streams) == 1
    finally:
        carril.detener()
        sesion.detener()


def test_un_metronomo_que_no_arranca_con_la_salida_abierta_la_cierra(monkeypatch):
    """`abrir()` salio bien pero `iniciar()` dice que no: la salida no se queda
    abierta sin nada que suene."""

    class MetronomoQueNoArranca(MetronomoEspia):
        def iniciar(self) -> bool:
            return False

    monkeypatch.setattr(modulo_piezas, "Metronomo", MetronomoQueNoArranca)
    salida, streams = salida_falsa()
    carril, sesion, _ = carril_a_mano(salida)
    try:
        estado = carril.iniciar(pieza_de_doce_compases(), PlanDePasada(con_click=True))
        assert estado["click_sonando"] is False
        assert len(streams) == 1 and streams[0].cerrado is True
    finally:
        carril.detener()
        sesion.detener()


# ---------------------------------------------------------------------------
# La cuenta atras de la primera entrada (`SesionDeEstudio.arrancar`)
# ---------------------------------------------------------------------------


def test_iniciar_por_http_ya_trae_la_cuenta_atras_con_el_plan_por_defecto(cliente):
    datos = iniciar_por_http(cliente).json()
    assert datos["cuenta_atras_restante_s"] > 0


def test_iniciar_por_http_sin_compases_de_cuenta_atras_no_la_abre(cliente):
    datos = iniciar_por_http(cliente, compases_de_cuenta_atras=0).json()
    assert datos["cuenta_atras_restante_s"] == 0


def test_la_pieza_espera_la_cuenta_atras_de_la_primera_entrada_y_luego_corre():
    carril, sesion, reloj = carril_a_mano()
    try:
        datos = carril.iniciar(pieza_de_doce_compases())
        # Compas de 4/4 a 60 ppm: cuatro segundos de cuenta.
        assert datos["cuenta_atras_restante_s"] == pytest.approx(4.0)
        # Dos segundos de reloj: la cuenta baja y el cabezal no se mueve.
        estado = mirar_hasta(carril, reloj, lambda e: False, pasos=60)
        assert estado["cuenta_atras_restante_s"] == pytest.approx(2.0, abs=0.1)
        assert estado["instante_s"] == pytest.approx(0.0)
        # Agotada la cuenta, la pieza empieza a correr desde el inicio.
        estado = mirar_hasta(carril, reloj, lambda e: e["cuenta_atras_restante_s"] == 0)
        assert estado["instante_s"] == pytest.approx(0.0, abs=0.1)
        estado = mirar_hasta(carril, reloj, lambda e: False, pasos=60)
        assert estado["instante_s"] == pytest.approx(2.0, abs=0.15)
    finally:
        carril.detener()
        sesion.detener()


def test_los_cuadros_de_audio_no_matan_la_cuenta_atras():
    """El Critical de la revision final: la cuenta moria con el primer cuadro.

    `iniciar()` deja `_ultimo_cuadro` a None, asi que `_sin_cuadros` es verdad en
    el PRIMER `_observar` tras arrancar, y ahi el servidor congelaba el reloj del
    estudio con `colocar_en`, que es la puerta que CANCELA la cuenta atras. Medido:
    la cuenta que `arrancar()` acababa de abrir moria unos 21 ms despues de pulsar
    «empezar». Con el cable enchufado -el unico caso que importa- no habia cuenta
    atras en absoluto, y el README prometia que si.

    Ninguna prueba de este archivo publicaba cuadros de audio con una cuenta
    abierta, y esa ausencia es la causa raiz del defecto. Esta es esa prueba.
    """
    carril, sesion, reloj = carril_a_mano()
    try:
        datos = carril.iniciar(pieza_de_doce_compases())
        # Un compas de 4/4 a 60 ppm: cuatro segundos de cuenta.
        assert datos["cuenta_atras_restante_s"] == pytest.approx(4.0)

        publicar(sesion, reloj, suena("E2"), cuadros=20)  # 0,4 s de audio
        estado = carril.estado()
        # La cuenta sigue bajando con los cuadros, que es lo que se rompia...
        assert 3.0 < estado["cuenta_atras_restante_s"] < 4.0
        # ...y mientras baja, el cabezal no se mueve y no se cobra nada.
        assert estado["instante_s"] == pytest.approx(0.0, abs=1e-9)
        assert estado["tocadas"] == []

        # Y un hueco de audio mas largo que `ESPERA_SIN_CUADROS_S` dentro de la
        # cuenta tampoco la mata: es el otro camino del mismo defecto, el que
        # pasaba en cada cuenta de vuelta del bucle.
        reloj.avanzar(0.3)
        publicar(sesion, reloj, suena("E2"), cuadros=1)
        estado = carril.estado()
        assert estado["cuenta_atras_restante_s"] > 0
        assert estado["instante_s"] == pytest.approx(0.0, abs=1e-9)

        # Y agotada la cuenta con los cuadros, la pieza corre y se cobra.
        publicar(sesion, reloj, SILENCIO, cuadros=200)
        estado = carril.estado()
        assert estado["cuenta_atras_restante_s"] == 0
        assert estado["instante_s"] > 0
    finally:
        carril.detener()
        sesion.detener()


def test_arrancar_con_cuenta_atras_y_click_no_deja_el_click_sonando_antes_de_hora(
    cliente_con_salida,
):
    salida, streams = salida_falsa()
    with TestClient(cliente_con_salida(salida), base_url=BASE_LOCAL) as cliente:
        datos = iniciar(cliente, con_click=True)
        # El click suena desde el primer pulso de la cuenta, que es lo que se
        # quiere, y el cabezal esta en el inicio del tramo, no descolocado.
        assert datos["click_sonando"] is True
        assert datos["cuenta_atras_restante_s"] > 0
        assert datos["instante_s"] == 0
        for _ in range(5):
            estado = cliente.get("/api/piezas/estado").json()
        # Cinco miradas en plena cuenta no rearrancan el click (una sola salida
        # abierta) ni mueven el cabezal.
        assert len(streams) == 1
        assert estado["click_sonando"] is True
        assert estado["instante_s"] == 0
