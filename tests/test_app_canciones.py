"""La biblioteca de canciones en el servidor: carpeta, subida y los cuatro endpoints.

Mismo doble de captura que `tests/test_app_carril.py`: ninguna prueba abre el
dispositivo de audio real. Y la carpeta de canciones apunta a `tmp_path`, porque la
carpeta ES la base de datos y una prueba no debe ensuciar la del proyecto.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.app import crear_app
from servidor.canciones import TAMANO_MAXIMO_BYTES, Biblioteca
from servidor.configuracion import Configuracion
from servidor.piezas import SesionCarril
from servidor.sesion import Sesion

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
    with TestClient(app) as cliente:
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
    respuesta = cliente.post("/api/canciones/x.txt/importar", json={"pista": 0})
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


def test_cada_pista_trae_el_indice_con_el_que_se_importa(cliente):
    """`/importar` recibe el ÍNDICE (base 0), no el número que ve el usuario."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pista = cliente.get("/api/canciones/x.txt/pistas").json()["pistas"][0]
    assert pista["indice"] == 0
    assert pista["numero"] == 1
    respuesta = cliente.post(
        "/api/canciones/x.txt/importar", json={"pista": pista["indice"]}
    )
    assert respuesta.status_code == 200


def test_importar_deja_abierto_el_camino_de_los_avisos(cliente):
    """Los avisos viajan junto a la pieza: hoy el ritmo aproximado, mañana más."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pieza = cliente.post("/api/canciones/x.txt/importar", json={"pista": 0}).json()
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
    cliente.post("/api/canciones/raro.txt/importar", json={"pista": 0})
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


def test_ningun_nombre_sale_de_la_carpeta_al_leer(cliente):
    """El `{id}` de la URL pasa por el mismo tamiz que el nombre que se sube."""
    for nombre in ("..%2F..%2Fetc%2Fpasswd", "..%5Cfuera.txt", "%2Fetc%2Fpasswd"):
        respuesta = cliente.get(f"/api/canciones/{nombre}/pistas")
        assert respuesta.status_code in (400, 404), nombre


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
