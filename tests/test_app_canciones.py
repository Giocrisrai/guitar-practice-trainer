"""La biblioteca de canciones en el servidor: carpeta, subida y los cuatro endpoints.

Mismo doble de captura que `tests/test_app_carril.py`: ninguna prueba abre el
dispositivo de audio real. Y la carpeta de canciones apunta a `tmp_path`, porque la
carpeta ES la base de datos y una prueba no debe ensuciar la del proyecto.
"""

import io
import os

import mido
import numpy as np
import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.app import crear_app
from servidor.canciones import (
    MARGEN_MULTIPART_BYTES,
    TAMANO_MAXIMO_BYTES,
    Biblioteca,
)
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

# Los tres WebSocket del servidor. El guardia es el mismo para todos, asi que se
# prueban los tres con la misma prueba: si manana uno se olvida de llamarlo, hay una
# prueba que lo dice y no una que prueba el que si se acordo.
RUTAS_WEBSOCKET = ["/ws/notas", "/ws/ejercicios", "/ws/piezas"]

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000

# Una tablatura mínima en afinación estándar: seis líneas, dos notas en la prima.
TABLATURA = (
    b"e|--0--2--|\n"
    b"B|--------|\n"
    b"G|--------|\n"
    b"D|--------|\n"
    b"A|--------|\n"
    b"E|--------|\n"
)


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
    app = crear_app(sesion, carril=carril, carpeta_canciones=tmp_path / "canciones")
    app.state.ruta_config = tmp_path / "config.json"
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        yield cliente
    carril.detener()
    sesion.detener()


def _vacia(carpeta) -> bool:
    """La carpeta no tiene ninguna cancion: ni archivos, ni carpeta siquiera."""
    return not carpeta.exists() or list(carpeta.iterdir()) == []


# ---------------------------------------------------------------------------
# Las diez pruebas del brief
# ---------------------------------------------------------------------------


def test_la_lista_esta_vacia_al_principio(cliente):
    assert cliente.get("/api/canciones").json() == []


def test_subir_un_archivo_lo_deja_en_la_lista(cliente):
    respuesta = cliente.post(
        "/api/canciones",
        files={
            "archivo": (
                "mia.txt",
                b"e|--0--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-----|\n",
            )
        },
    )
    assert respuesta.status_code == 200
    assert [c["id"] for c in cliente.get("/api/canciones").json()] == ["mia.txt"]


def test_un_formato_desconocido_se_rechaza_diciendo_cuales_valen(cliente):
    respuesta = cliente.post("/api/canciones", files={"archivo": ("x.pdf", b"x")})
    assert respuesta.status_code == 400
    assert ".gp5" in respuesta.json()["detail"]


def test_un_archivo_demasiado_grande_se_rechaza(cliente):
    enorme = b"x" * (TAMANO_MAXIMO_BYTES + 1)
    respuesta = cliente.post("/api/canciones", files={"archivo": ("x.mid", enorme)})
    assert respuesta.status_code == 400
    assert "10" in respuesta.json()["detail"]


def test_un_nombre_con_ruta_se_rechaza(cliente):
    """La carpeta es la base de datos; `..` es un intento de leer el disco."""
    respuesta = cliente.post(
        "/api/canciones", files={"archivo": ("../../etc/passwd", b"x")}
    )
    assert respuesta.status_code == 400


def test_pedir_una_cancion_que_no_existe_da_404(cliente):
    assert cliente.get("/api/canciones/inventada.gp5/pistas").status_code == 404


def test_las_pistas_se_leen_sin_importar_la_cancion(cliente, tmp_path):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pistas = cliente.get("/api/canciones/x.txt/pistas").json()
    assert pistas["pistas"][0]["nombre"]
    assert "afinacion" in pistas


def test_importar_devuelve_una_pieza_lista_para_el_carril(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post("/api/canciones/x.txt/importar", json={"pista": 1})
    assert respuesta.status_code == 200
    pieza = respuesta.json()
    assert pieza["notas"]
    assert pieza["ritmo_aproximado"] is True


def test_la_respuesta_dice_si_hay_que_cambiar_de_afinacion(cliente):
    """Lo que hace accionable el aviso: la clave del perfil que pide la cancion."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pistas = cliente.get("/api/canciones/x.txt/pistas").json()
    assert "perfil_activo" in pistas
    assert "coincide" in pistas


def test_importar_una_pista_que_no_existe_da_400(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    assert (
        cliente.post("/api/canciones/x.txt/importar", json={"pista": 99}).status_code
        == 400
    )


# ---------------------------------------------------------------------------
# Lo demás que decide el servidor: la afinación accionable
# ---------------------------------------------------------------------------


def test_una_tablatura_estandar_coincide_con_el_perfil_activo(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pistas = cliente.get("/api/canciones/x.txt/pistas").json()
    assert pistas["perfil_activo"] == "guitarra_estandar"
    assert pistas["afinacion"]["clave"] == "guitarra_estandar"
    assert pistas["coincide"] is True


def test_una_tablatura_en_drop_d_no_coincide_y_dice_a_que_afinarse(cliente):
    """El aviso tiene que decir A QUÉ afinarse, no solo que algo no cuadra."""
    drop_d = TABLATURA.replace(b"E|", b"D|")
    cliente.post("/api/canciones", files={"archivo": ("drop.txt", drop_d)})
    pistas = cliente.get("/api/canciones/drop.txt/pistas").json()
    assert pistas["coincide"] is False
    assert pistas["afinacion"]["clave"] == "guitarra_drop_d"
    assert pistas["afinacion"]["nombre"]


def test_la_pista_se_pide_con_el_numero_que_publica_pistas(cliente):
    """Una sola numeración, la del núcleo: base 1 y ningún `indice` al lado."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pista = cliente.get("/api/canciones/x.txt/pistas").json()["pistas"][0]
    assert pista["numero"] == 1
    assert "indice" not in pista
    respuesta = cliente.post(
        "/api/canciones/x.txt/importar", json={"pista": pista["numero"]}
    )
    assert respuesta.status_code == 200


def test_la_pista_cero_no_existe_y_lo_dice(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post("/api/canciones/x.txt/importar", json={"pista": 0})
    assert respuesta.status_code == 400
    assert "desde 1" in respuesta.json()["detail"]


def test_el_error_de_la_pista_nombra_la_pista_que_se_pidio(cliente):
    """Con el `+1` por medio, pedir la 99 contestaba «la pista 100 no existe»."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    detalle = cliente.post(
        "/api/canciones/x.txt/importar", json={"pista": 99}
    ).json()["detail"]
    assert "99" in detalle
    assert "100" not in detalle


@pytest.mark.parametrize("valor", [1.9, True, "1", None, [1]])
def test_un_numero_de_pista_que_no_es_entero_se_rechaza(cliente, valor):
    """`int()` truncaba `1.9` y `true` a la primera pista sin avisar."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post("/api/canciones/x.txt/importar", json={"pista": valor})
    assert respuesta.status_code == 400


def test_importar_deja_abierto_el_camino_de_los_avisos(cliente):
    """Los avisos viajan junto a la pieza: hoy el ritmo aproximado, mañana más."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pieza = cliente.post("/api/canciones/x.txt/importar", json={"pista": 1}).json()
    assert any("aproximado" in aviso.lower() for aviso in pieza["avisos"])


def test_un_txt_que_no_es_tablatura_se_rechaza_con_400(cliente):
    cliente.post("/api/canciones", files={"archivo": ("nota.txt", b"hola mundo\n")})
    respuesta = cliente.get("/api/canciones/nota.txt/pistas")
    assert respuesta.status_code == 400
    assert "tablatura" in respuesta.json()["detail"].lower()


def test_un_parametro_mal_escrito_no_es_un_500(cliente):
    """`_generar_o_400` captura TypeError por esto mismo; aquí vale igual."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post("/api/canciones/x.txt/importar", json={"pista": "primera"})
    assert respuesta.status_code == 400


def test_el_selector_de_afinaciones_no_se_llena_de_afinaciones_importadas(cliente):
    """`/api/perfiles` publica las de fábrica: el registro vivo no es un menú."""
    antes = {p["clave"] for p in cliente.get("/api/perfiles").json()}
    raro = (
        b"e|--0--|\n"
        b"B|-----|\n"
        b"G|-----|\n"
        b"F|-----|\n"
        b"C|-----|\n"
        b"C|-----|\n"
    )
    cliente.post("/api/canciones", files={"archivo": ("raro.txt", raro)})
    cliente.post("/api/canciones/raro.txt/importar", json={"pista": 1})
    assert {p["clave"] for p in cliente.get("/api/perfiles").json()} == antes


# ---------------------------------------------------------------------------
# Salirse de la carpeta: la carpeta es la base de datos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nombre",
    [
        "../fuera.txt",
        "../../etc/passwd",
        "sub/dentro.txt",
        "/etc/passwd",
        "..\\..\\windows\\system32\\drivers\\etc\\hosts",
        ".",
        "..",
        "   ",
    ],
)
def test_ningun_nombre_sale_de_la_carpeta_al_subir(cliente, nombre, tmp_path):
    respuesta = cliente.post("/api/canciones", files={"archivo": (nombre, TABLATURA)})
    assert respuesta.status_code == 400
    assert _vacia(tmp_path / "canciones")


def test_una_subida_sin_nombre_de_archivo_no_escribe_nada(cliente, tmp_path):
    """Sin `filename` la parte no es un archivo, y FastAPI la rechaza con 422.

    No es un 400 porque no llega a nuestro guardia: es la validación del cuerpo. Lo
    que importa, y es lo que se comprueba, es que no se escribe nada.
    """
    respuesta = cliente.post("/api/canciones", files={"archivo": ("", TABLATURA)})
    assert respuesta.status_code == 422
    assert _vacia(tmp_path / "canciones")


@pytest.mark.parametrize(
    "nombre",
    [
        "../fuera.txt",
        "../../etc/passwd",
        "sub/dentro.txt",
        "/etc/passwd",
        "..\\fuera.txt",
        ".",
        "..",
        "",
        "   ",
        "x\x00.txt",
    ],
)
def test_la_biblioteca_rechaza_todas_las_formas_de_salirse(tmp_path, nombre):
    """El guardia, sin HTTP por medio.

    El byte nulo se prueba aquí y no por HTTP porque el cliente lo manda
    porcentajeado (`x%00.txt`), que es un nombre de archivo legal: la defensa es
    para quien llame a `Biblioteca` sin un navegador en medio.
    """
    biblioteca = Biblioteca(tmp_path / "canciones")
    with pytest.raises(ValueError):
        biblioteca.ruta_de(nombre)
    with pytest.raises(ValueError):
        biblioteca.guardar(nombre, TABLATURA)


def test_los_nombres_codificados_de_la_url_no_leen_nada(cliente, tmp_path):
    """Ninguno de estos llega a leer un archivo, y se dice por qué cada uno.

    Esta prueba NO fija el guardia: los dos primeros ni llegan al handler -el
    enrutador ve las barras ya decodificadas y no encuentra la ruta-, así que darían
    404 aunque `Biblioteca.ruta_de` no comprobara nada. La que sí fija el guardia es
    `test_el_id_de_la_url_pasa_por_el_guardia`, que usa un nombre que llega entero.
    Se queda porque el 404 del enrutador también hay que no perderlo de vista.
    """
    centinela = tmp_path / "centinela.txt"
    centinela.write_bytes(TABLATURA)
    for nombre in ("..%2F..%2Fetc%2Fpasswd", "%2Fetc%2Fpasswd", "..%5Cfuera.txt"):
        respuesta = cliente.get(f"/api/canciones/{nombre}/pistas")
        assert respuesta.status_code in (400, 404), nombre
        assert "pistas" not in respuesta.json(), nombre


def test_el_id_de_la_url_pasa_por_el_guardia(cliente, tmp_path):
    """El `{id}` que SÍ llega al handler y que sin guardia leería fuera.

    Es un enlace simbólico dentro de la carpeta apuntando a un centinela de fuera:
    el nombre (`centinela.txt`) es impecable, llega al handler tal cual y el router
    no tiene nada que objetar. Lo único que lo para es el `resolve()` +
    `is_relative_to` de `Biblioteca.ruta_de`.

    Comprobado por mutación: sustituyendo el cuerpo de `ruta_de` por
    `return self.carpeta / identificador` -sin guardia ninguno- esta prueba falla
    con 200 y el contenido del centinela en la respuesta, mientras las pruebas de
    nombres codificados siguen pasando.
    """
    carpeta = tmp_path / "canciones"
    carpeta.mkdir(exist_ok=True)
    (tmp_path / "centinela.txt").write_bytes(TABLATURA)
    (carpeta / "centinela.txt").symlink_to(tmp_path / "centinela.txt")

    respuesta = cliente.get("/api/canciones/centinela.txt/pistas")
    assert respuesta.status_code == 400
    assert "pistas" not in respuesta.json()

    assert cliente.post(
        "/api/canciones/centinela.txt/importar", json={"pista": 1}
    ).status_code == 400


def test_un_enlace_simbolico_que_apunta_fuera_no_se_lee(cliente, tmp_path):
    """`resolve()` sigue el enlace, así que el destino de fuera se rechaza."""
    carpeta = tmp_path / "canciones"
    carpeta.mkdir(exist_ok=True)
    afuera = tmp_path / "secreto.txt"
    afuera.write_bytes(TABLATURA)
    (carpeta / "enlace.txt").symlink_to(afuera)
    assert cliente.get("/api/canciones/enlace.txt/pistas").status_code == 400
    assert cliente.get("/api/canciones").json() == []


def test_subir_dos_veces_el_mismo_nombre_no_duplica_la_lista(cliente):
    for _ in range(2):
        cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    assert len(cliente.get("/api/canciones").json()) == 1


def test_la_carpeta_ignora_lo_que_no_es_una_cancion(cliente, tmp_path):
    carpeta = tmp_path / "canciones"
    carpeta.mkdir(exist_ok=True)
    (carpeta / "notas.pdf").write_bytes(b"x")
    (carpeta / "subcarpeta").mkdir()
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    assert [c["id"] for c in cliente.get("/api/canciones").json()] == ["x.txt"]


# ---------------------------------------------------------------------------
# La biblioteca, sin servidor por medio
# ---------------------------------------------------------------------------


def test_construir_la_biblioteca_no_toca_el_disco(tmp_path):
    """Y la carpeta aparece cuando hay algo que guardar, no antes."""
    biblioteca = Biblioteca(tmp_path / "nueva" / "canciones")
    assert biblioteca.listar() == []
    assert not (tmp_path / "nueva").exists()
    biblioteca.guardar("x.txt", TABLATURA)
    assert (tmp_path / "nueva" / "canciones").is_dir()


def test_la_biblioteca_rechaza_el_nombre_que_sale_de_la_carpeta(tmp_path):
    biblioteca = Biblioteca(tmp_path / "canciones")
    with pytest.raises(ValueError, match="nombre"):
        biblioteca.ruta_de("../fuera.txt")


def test_la_biblioteca_cuenta_lo_que_guarda(tmp_path):
    biblioteca = Biblioteca(tmp_path / "canciones")
    entrada = biblioteca.guardar("x.txt", TABLATURA)
    assert entrada["id"] == "x.txt"
    assert entrada["bytes"] == len(TABLATURA)
    assert entrada["formato"] == "Tablatura de texto"


# ---------------------------------------------------------------------------
# Lo que el disco puede contestar: permisos, tamaño y lo que no se cuenta
# ---------------------------------------------------------------------------


def test_un_archivo_sin_permiso_de_lectura_no_es_un_500(cliente, tmp_path):
    """Copiar la carpeta de canciones de otro disco deja archivos así.

    `PermissionError` es hijo de `OSError` y no de `ValueError`: con una lista de
    nombres en el `except` se escapaba como un 500, «el servidor se ha roto», que es
    mentira y no le dice al usuario que lo que tiene que arreglar son los permisos.
    """
    if os.geteuid() == 0:
        pytest.skip("root lee hasta lo que no tiene permiso")
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    (tmp_path / "canciones" / "x.txt").chmod(0o000)
    try:
        respuesta = cliente.get("/api/canciones/x.txt/pistas")
        assert respuesta.status_code == 400
        assert "ermis" in respuesta.json()["detail"]  # Permission / permiso
    finally:
        (tmp_path / "canciones" / "x.txt").chmod(0o600)


def test_el_detalle_no_cuenta_donde_vive_la_carpeta(cliente, tmp_path):
    """El navegador no tiene por qué saber el nombre del usuario de la máquina."""
    if os.geteuid() == 0:
        pytest.skip("root lee hasta lo que no tiene permiso")
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    (tmp_path / "canciones" / "x.txt").chmod(0o000)
    try:
        detalle = cliente.get("/api/canciones/x.txt/pistas").json()["detail"]
        assert str(tmp_path) not in detalle
        assert "x.txt" in detalle
    finally:
        (tmp_path / "canciones" / "x.txt").chmod(0o600)


def test_el_tamano_que_se_rechaza_es_el_de_verdad(cliente):
    """`archivo.size` ya lo sabe antes de leer: el mensaje no dice «al menos»."""
    grande = b"x" * (TAMANO_MAXIMO_BYTES + 1024)
    respuesta = cliente.post("/api/canciones", files={"archivo": ("x.mid", grande)})
    assert respuesta.status_code == 400
    assert str(TAMANO_MAXIMO_BYTES + 1024) in respuesta.json()["detail"]


def test_una_peticion_que_se_declara_enorme_no_se_parsea(cliente, tmp_path):
    """La puerta de `Content-Length`: lo único que corta antes del multipart.

    Starlette recibe el cuerpo entero y lo vuelca a un temporal ANTES de que el
    handler empiece, así que el techo del handler no evita recibir nada. Esto sí:
    con el tamaño ya declarado en la cabecera, se contesta sin parsear el cuerpo.
    """
    cuerpo = b"x" * (TAMANO_MAXIMO_BYTES + MARGEN_MULTIPART_BYTES + 1)
    respuesta = cliente.post(
        "/api/canciones",
        content=cuerpo,
        headers={"content-type": "multipart/form-data; boundary=abc"},
    )
    assert respuesta.status_code == 400
    assert "No la leo" in respuesta.json()["detail"]
    assert _vacia(tmp_path / "canciones")


# ---------------------------------------------------------------------------
# La afinación que el archivo no declara, y el selector que la ofrece
# ---------------------------------------------------------------------------


def _midi_de_una_nota() -> bytes:
    pista = mido.MidiTrack()
    pista.append(mido.Message("program_change", program=27, time=0))
    pista.append(mido.Message("note_on", note=52, velocity=80, time=0))
    pista.append(mido.Message("note_off", note=52, velocity=0, time=480))
    archivo = mido.MidiFile()
    archivo.tracks.append(pista)
    memoria = io.BytesIO()
    archivo.save(file=memoria)
    return memoria.getvalue()


def test_un_midi_no_declara_afinacion_y_coincide_no_es_false(cliente):
    """`False` decía «no cuadra, aféinate a null» sin que hubiera nada que arreglar.

    Y la prueba de que no había nada que arreglar: la misma canción se importa y
    sale en el perfil ACTIVO, que es justo el que el carril acepta.
    """
    cliente.post("/api/canciones", files={"archivo": ("x.mid", _midi_de_una_nota())})
    pistas = cliente.get("/api/canciones/x.mid/pistas").json()
    assert pistas["afinacion"]["declarada"] is False
    assert pistas["afinacion"]["clave"] is None
    assert pistas["coincide"] is None

    pieza = cliente.post("/api/canciones/x.mid/importar", json={"pista": 1}).json()
    assert pieza["perfil"] == pistas["perfil_activo"]


def test_una_tablatura_declara_su_afinacion(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    assert cliente.get("/api/canciones/x.txt/pistas").json()["afinacion"]["declarada"]


def test_el_selector_ofrece_el_perfil_activo_aunque_no_sea_de_fabrica(cliente):
    """Nunca se deja al usuario con una afinación que no puede elegir.

    `/pistas` propone la clave de la afinación rara, `PUT /api/config` la acepta, y
    entonces el selector tenía que poder mostrarla: si no, el afinador queda con un
    perfil que la lista no incluye y sin forma de volver.
    """
    raro = (
        b"e|--0--|\n"
        b"B|-----|\n"
        b"G|-----|\n"
        b"F|-----|\n"
        b"C|-----|\n"
        b"C|-----|\n"
    )
    cliente.post("/api/canciones", files={"archivo": ("raro.txt", raro)})
    clave = cliente.get("/api/canciones/raro.txt/pistas").json()["afinacion"]["clave"]
    assert clave is not None and clave.startswith("a_medida_")

    # Antes de elegirla, no está en el selector: no crece con cada importación.
    assert clave not in {p["clave"] for p in cliente.get("/api/perfiles").json()}

    assert cliente.put("/api/config", json={"perfil": clave}).status_code == 200
    perfiles = cliente.get("/api/perfiles").json()
    assert clave in {p["clave"] for p in perfiles}
    assert "guitarra_estandar" in {p["clave"] for p in perfiles}


# ---------------------------------------------------------------------------
# La puerta al carril: `/api/piezas/iniciar` tambien acepta una cancion
#
# Estas pruebas son de `/api/piezas/iniciar` y viven aqui, y no en
# `tests/test_app_carril.py`, porque hace falta la carpeta de canciones: el
# `cliente` de alli construye la app SIN `carpeta_canciones`, asi que su biblioteca
# apunta a la del proyecto. Una prueba no ensucia la carpeta del usuario.
# ---------------------------------------------------------------------------


def _midi_de_dos_pistas() -> bytes:
    """Un MIDI de dos pistas que NO suenan igual: E3 en la primera, A3 en la segunda.

    Que las dos pistas se distingan POR SU CONTENIDO es lo que hace falta: con dos
    pistas iguales, pedir la 1 y pedir la 2 dan lo mismo y la prueba de la
    numeracion no puede fallar.
    """
    archivo = mido.MidiFile()
    for nota in (52, 57):
        pista = mido.MidiTrack()
        pista.append(mido.Message("program_change", program=27, time=0))
        pista.append(mido.Message("note_on", note=nota, velocity=80, time=0))
        pista.append(mido.Message("note_off", note=nota, velocity=0, time=480))
        archivo.tracks.append(pista)
    memoria = io.BytesIO()
    archivo.save(file=memoria)
    return memoria.getvalue()


def test_el_carril_arranca_una_cancion_de_la_biblioteca(cliente):
    """La etapa 3b no tenia puerta al carril: `/importar` no arranca y `/iniciar`
    solo aceptaba un descriptor de ejercicio. Esta es la puerta."""
    cliente.post("/api/canciones", files={"archivo": ("x.mid", _midi_de_una_nota())})
    respuesta = cliente.post(
        "/api/piezas/iniciar", json={"cancion": "x.mid", "pista": 1}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["pieza"]["notas"]
    # Arrancada de verdad, no solo leida: el carril etiqueta un arranque, y el cero
    # es el del carril sin pieza.
    assert cuerpo["arranque"] > 0
    estado = cliente.get("/api/piezas/estado").json()
    assert estado["arranque"] == cuerpo["arranque"]
    assert estado["total"] == len(cuerpo["pieza"]["notas"])
    cliente.post("/api/piezas/detener")


def test_la_pista_que_arranca_es_la_que_se_pidio_en_base_1(cliente):
    """Una sola numeracion, la del nucleo: `pista: 2` toca la segunda, no la tercera."""
    cliente.post(
        "/api/canciones", files={"archivo": ("dos.mid", _midi_de_dos_pistas())}
    )
    segunda = cliente.post(
        "/api/piezas/iniciar", json={"cancion": "dos.mid", "pista": 2}
    ).json()
    assert [nota["midi"] for nota in segunda["pieza"]["notas"]] == [57]
    cliente.post("/api/piezas/detener")

    primera = cliente.post(
        "/api/piezas/iniciar", json={"cancion": "dos.mid", "pista": 1}
    ).json()
    assert [nota["midi"] for nota in primera["pieza"]["notas"]] == [52]
    cliente.post("/api/piezas/detener")


def test_una_cancion_en_otra_afinacion_no_entra_al_carril(cliente):
    """La regla de afinacion de la etapa 3a se aplica tambien a las canciones.

    Es el motivo de que la cancion la lea el SERVIDOR: si el navegador mandara la
    pieza ya leida, el perfil con el que dice estar escrita -lo unico que esta
    comprobacion mira- seria cosa suya.
    """
    drop_d = TABLATURA.replace(b"E|", b"D|")
    cliente.post("/api/canciones", files={"archivo": ("drop.txt", drop_d)})
    respuesta = cliente.post(
        "/api/piezas/iniciar", json={"cancion": "drop.txt", "pista": 1}
    )
    assert respuesta.status_code == 400
    detalle = respuesta.json()["detail"]
    assert "guitarra_drop_d" in detalle
    assert "guitarra_estandar" in detalle
    # Y no se ha quedado nada en marcha: el cero es el carril sin pieza.
    assert cliente.get("/api/piezas/estado").json()["arranque"] == 0


def test_las_dos_formas_de_pedir_una_pieza_a_la_vez_dan_400(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post(
        "/api/piezas/iniciar",
        json={"cancion": "x.txt", "pista": 1, "familia": "escala"},
    )
    assert respuesta.status_code == 400
    detalle = respuesta.json()["detail"]
    assert "familia" in detalle and "cancion" in detalle
    assert cliente.get("/api/piezas/estado").json()["arranque"] == 0


def test_un_iniciar_sin_cancion_ni_familia_dice_cual_falta(cliente):
    respuesta = cliente.post("/api/piezas/iniciar", json={})
    assert respuesta.status_code == 400
    detalle = respuesta.json()["detail"]
    assert "familia" in detalle and "cancion" in detalle


def test_arrancar_una_cancion_que_no_existe_da_404_y_no_arranca_nada(cliente):
    respuesta = cliente.post(
        "/api/piezas/iniciar", json={"cancion": "fantasma.gp5", "pista": 1}
    )
    assert respuesta.status_code == 404
    assert cliente.get("/api/piezas/estado").json()["arranque"] == 0


def test_arrancar_un_nombre_que_sale_de_la_carpeta_da_400(cliente):
    """El `id` llega del navegador tambien por aqui, asi que pasa por el guardia.

    Es el mismo `_ruta_de_cancion` que usa `/importar`, no una copia: una copia es
    lo que se olvida de actualizar cuando el guardia aprende una forma nueva de
    salirse.
    """
    respuesta = cliente.post(
        "/api/piezas/iniciar", json={"cancion": "../../../etc/passwd", "pista": 1}
    )
    assert respuesta.status_code == 400
    assert cliente.get("/api/piezas/estado").json()["arranque"] == 0


def test_la_pista_de_una_cancion_que_arranca_tambien_se_pide_entera(cliente):
    """Un numero de pista que no es entero es un pedido mal hecho, no un 500."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post(
        "/api/piezas/iniciar", json={"cancion": "x.txt", "pista": 1.9}
    )
    assert respuesta.status_code == 400
    assert "1.9" in respuesta.json()["detail"]


def test_el_modulo_canciones_aparece_junto_a_los_otros(cliente):
    claves = {m["clave"] for m in cliente.get("/api/modulos").json()}
    assert {"afinador", "ejercicios", "carril", "canciones"} <= claves


# ---------------------------------------------------------------------------
# El guardia de peticiones: CSRF y rebinding de DNS
# ---------------------------------------------------------------------------


def test_una_web_ajena_no_puede_subir_nada(cliente, tmp_path):
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("x.txt", TABLATURA)},
        headers={"origin": "https://sitio.ajeno.example"},
    )
    assert respuesta.status_code == 403
    assert _vacia(tmp_path / "canciones")


def test_el_origen_propio_si_puede_subir(cliente):
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("x.txt", TABLATURA)},
        headers={"origin": "http://127.0.0.1:8420"},
    )
    assert respuesta.status_code == 200


def test_sin_origen_se_deja_pasar_porque_es_curl(cliente):
    """`curl` y los scripts no mandan `Origin`; un navegador no puede omitirla."""
    respuesta = cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    assert respuesta.status_code == 200
    assert "origin" not in {k.lower() for k in respuesta.request.headers}


def test_una_web_ajena_tampoco_puede_cambiar_la_afinacion(cliente):
    """La guarda es de TODOS los métodos que cambian estado, no solo de la subida."""
    respuesta = cliente.put(
        "/api/config",
        json={"perfil": "guitarra_drop_d"},
        headers={"origin": "https://sitio.ajeno.example"},
    )
    assert respuesta.status_code == 403


def test_un_host_que_no_es_el_nuestro_no_se_atiende(cliente):
    """Rebinding de DNS: el `Host` es lo único que lo delata, también en los GET."""
    assert cliente.get("/api/canciones", headers={"host": "ajeno.example"}).status_code == 400
    assert cliente.get("/api/canciones", headers={"host": "localhost:8420"}).status_code == 200


# ---------------------------------------------------------------------------
# Nombres equivalentes, un solo destino
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nombre", ["x.txt ", " x.txt", "  x.txt  "])
def test_los_espacios_del_nombre_no_cambian_el_destino(cliente, nombre):
    """Antes `'x.txt '` daba 400 y `' x.txt'` se guardaba como `'x.txt'`, pisando.

    El tabulador no se prueba por HTTP: el cliente lo manda porcentajeado
    (`x.txt%09`), que es otro nombre. Va en la prueba de `Biblioteca`.
    """
    respuesta = cliente.post("/api/canciones", files={"archivo": (nombre, TABLATURA)})
    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == "x.txt"


@pytest.mark.parametrize("nombre", ["x.txt ", " x.txt", "x.txt\t", "\nx.txt"])
def test_la_biblioteca_guarda_los_nombres_con_espacios_en_un_solo_sitio(
    tmp_path, nombre
):
    biblioteca = Biblioteca(tmp_path / "canciones")
    assert biblioteca.guardar(nombre, TABLATURA)["id"] == "x.txt"


def test_subir_el_mismo_nombre_con_otras_mayusculas_no_pisa_nada(cliente, tmp_path):
    """En macOS `X.TXT` y `x.txt` son el mismo archivo: pisarlo es perder datos."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post(
        "/api/canciones", files={"archivo": ("X.TXT", b"basura que no es tablatura")}
    )
    assert respuesta.status_code == 400
    assert "x.txt" in respuesta.json()["detail"]
    assert (tmp_path / "canciones" / "x.txt").read_bytes() == TABLATURA


def test_subir_el_mismo_nombre_exacto_si_reemplaza(cliente, tmp_path):
    """Es lo que el usuario pide cuando vuelve a subir la canción corregida."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    otra = TABLATURA.replace(b"--0--2--", b"--3--5--")
    assert (
        cliente.post("/api/canciones", files={"archivo": ("x.txt", otra)}).status_code
        == 200
    )
    assert (tmp_path / "canciones" / "x.txt").read_bytes() == otra


def test_el_servidor_de_desarrollo_de_la_interfaz_puede_subir(cliente):
    """Vite sirve la interfaz en `localhost:5173` y hace de proxy al 8420.

    Se compara el nombre y no el puerto: exigir el puerto exacto habría roto el modo
    en que se desarrolla esto, y no defendería de nada.
    """
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("x.txt", TABLATURA)},
        headers={"origin": "http://localhost:5173"},
    )
    assert respuesta.status_code == 200


# ---------------------------------------------------------------------------
# El guardia y los origenes que no nombran ninguna maquina
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origen", ["null", "file://", "https:", ""])
def test_un_origen_que_no_nombra_ninguna_maquina_no_puede_subir_nada(
    cliente, tmp_path, origen
):
    """`Origin: null` es una web ajena, no esta maquina, y podia ESCRIBIR.

    Lo manda un `<iframe sandbox="allow-scripts">` o un documento `data:`, y un
    `POST` con `FormData` es peticion CORS simple -`multipart/form-data` esta en la
    lista segura-, asi que no hay preflight que lo pare. Los cuatro valores daban 200
    porque el `Origin` se comparaba contra el mismo conjunto que el `Host`, y ese
    conjunto tiene la cadena vacia dentro para admitir el `Host` ausente.

    Esta prueba falla si se vuelve a meter `""` en la lista de origenes.
    """
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("x.txt", TABLATURA)},
        headers={"origin": origen},
    )
    assert respuesta.status_code == 403
    assert _vacia(tmp_path / "canciones")


@pytest.mark.parametrize("origen", ["null", "file://", "https:", ""])
def test_un_origen_opaco_tampoco_puede_cambiar_la_afinacion(cliente, origen):
    """Lo mismo sobre el otro metodo que cambia estado, que no sube archivos."""
    respuesta = cliente.put(
        "/api/config", json={"perfil": "guitarra_drop_d"}, headers={"origin": origen}
    )
    assert respuesta.status_code == 403


@pytest.mark.parametrize(
    "origen",
    [
        "http://localhost:5173",
        "http://LOCALHOST:8420",
        "HTTP://127.0.0.1:8420",
        "http://[::1]:8420",
    ],
)
def test_los_origenes_de_esta_maquina_siguen_pasando(cliente, origen):
    """El proxy de Vite, las mayusculas y la IPv6 con corchetes: todos somos nosotros.

    `hostname` normaliza las mayusculas y quita los corchetes, asi que `[::1]:8420`
    da `::1`, que es como esta escrito en la lista.
    """
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("x.txt", TABLATURA)},
        headers={"origin": origen},
    )
    assert respuesta.status_code == 200


@pytest.mark.parametrize(
    "origen",
    [
        "http://127.0.0.1.atacante.example",
        "http://localhost.atacante.example",
        "http://localhost@atacante.example",
        "http://atacante.example/localhost",
        "http://127.1",
        "http://2130706433",
        "http://localhost.",
    ],
)
def test_los_nombres_que_solo_se_parecen_a_localhost_no_pasan(cliente, tmp_path, origen):
    """Un nombre que CONTIENE 'localhost' no es localhost.

    `localhost@atacante.example` es el caso que mas engaña: la parte de antes del
    `@` es un usuario, no un anfitrion, y el anfitrion de verdad es `atacante.example`.
    """
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("x.txt", TABLATURA)},
        headers={"origin": origen},
    )
    assert respuesta.status_code == 403
    assert _vacia(tmp_path / "canciones")


def test_una_cabecera_host_vacia_se_atiende_igual(cliente):
    """Decision escrita, no efecto colateral: HTTP/1.0 y la terminal la mandan vacia.

    Lo que se ejerce aqui es un `Host` VACIO, no ausente: `TestClient` siempre manda
    la cabecera, asi que `{"host": ""}` es lo unico que se puede ejercer desde aqui
    y el nombre anterior -«sin cabecera host»- prometia otra cosa. Da lo mismo para
    el guardia, porque `_anfitrion_ajeno` compara el NOMBRE y una cabecera ausente
    llega a Starlette como `""`: el mismo camino.

    Se admite porque lo que delata el rebinding de DNS es un `Host` con el nombre del
    atacante, y un navegador no puede omitir esa cabecera. Antes esto salia de tener
    un `""` en el conjunto que compartian `Host` y `Origin`; ahora sale de la lista
    del `Host`, que es la unica donde ese `""` significa algo.
    """
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("x.txt", TABLATURA)},
        headers={"host": ""},
    )
    assert respuesta.status_code == 200


# ---------------------------------------------------------------------------
# El guardia de los WebSocket
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", RUTAS_WEBSOCKET)
def test_un_websocket_con_host_ajeno_se_cierra_sin_emitir(cliente, ruta):
    """Rebinding de DNS por la otra puerta: los WebSocket no pasan por el middleware.

    `/ws/notas` manda la telemetria del microfono -que nota suena, cuando se toca y
    con cuanto nivel- a 30 Hz, legible por cualquier pestaña abierta. Se cierra con
    1008 (violacion de politica) ANTES de aceptar, asi que el cliente ve el cierre al
    conectar y no recibe ni un mensaje.
    """
    with pytest.raises(WebSocketDisconnect) as fallo:
        with cliente.websocket_connect(
            WS_LOCAL + ruta, headers={"host": "ajeno.example"}
        ) as ws:
            ws.receive_json()
    assert fallo.value.code == 1008


@pytest.mark.parametrize("ruta", RUTAS_WEBSOCKET)
@pytest.mark.parametrize("origen", ["https://sitio.ajeno.example", "null", "file://"])
def test_un_websocket_con_origen_ajeno_se_cierra_sin_emitir(cliente, ruta, origen):
    """Un WebSocket de navegador manda `Origin` SIEMPRE, asi que aqui si delata."""
    with pytest.raises(WebSocketDisconnect) as fallo:
        with cliente.websocket_connect(WS_LOCAL + ruta, headers={"origin": origen}) as ws:
            ws.receive_json()
    assert fallo.value.code == 1008


@pytest.mark.parametrize("ruta", RUTAS_WEBSOCKET)
def test_un_websocket_normal_sigue_conectando_y_emitiendo(cliente, ruta):
    """El guardia no puede cerrar la puerta por la que entra la interfaz."""
    with cliente.websocket_connect(WS_LOCAL + ruta) as ws:
        assert ws.receive_json()


@pytest.mark.parametrize("ruta", RUTAS_WEBSOCKET)
def test_un_websocket_sin_origen_sigue_conectando(cliente, ruta):
    """Los clientes de terminal no mandan `Origin` y siguen siendo validos."""
    with cliente.websocket_connect(
        WS_LOCAL + ruta, headers={"host": "localhost:8420"}
    ) as ws:
        assert ws.receive_json()
