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

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.piezas.estudio import FACTOR_MINIMO, PASO_DEL_FACTOR, PlanDePasada
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion
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
    # Y el cabezal no arranca en cero: el compas 5 de 4/4 a 60 ppm son 16 s.
    assert datos["instante_s"] == pytest.approx(16.0, abs=0.001)


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


def test_cambiar_el_plan_no_reinicia_la_pasada(cliente):
    iniciar(cliente)
    cliente.post("/api/piezas/saltar", json={"compas": 6})
    datos = cliente.post("/api/piezas/plan", json={"factor_tempo": 0.5}).json()
    assert datos["factor_tempo"] == 0.5
    assert datos["compas_en_curso"] == 6
    assert datos["tempo_efectivo"] == 30.0


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


def carril_a_mano():
    """Un carril con el reloj y la señal en la mano de la prueba."""
    reloj = RelojFalso()
    sesion = SesionAudioFalsa()
    return SesionCarril(sesion, reloj=reloj), sesion, reloj


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
        assert mirar_hasta(carril, reloj, lambda e: e["repeticion"] > 1)["repeticion"] == 2
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
        assert estado["instante_s"] == pytest.approx(4.0 / 0.95, abs=0.02)
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
