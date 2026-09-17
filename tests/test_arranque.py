from servidor.arranque import RUTA_INTERFAZ, _esperar_al_servidor, construir_aplicacion


def test_la_aplicacion_se_construye_sin_hardware(tmp_path, monkeypatch):
    """Sin cable no se debe abortar: el servidor levanta y la interfaz explica."""
    monkeypatch.setattr("servidor.sesion.listar_dispositivos_entrada", lambda: [])
    app, sesion = construir_aplicacion(ruta_config=tmp_path / "config.json")
    assert app is not None
    assert sesion.activa is False
    sesion.detener()


def test_la_ruta_de_la_interfaz_apunta_a_dist():
    assert RUTA_INTERFAZ.name == "dist"
    assert RUTA_INTERFAZ.parent.name == "interfaz"


def test_usa_la_configuracion_guardada(tmp_path):
    from servidor.configuracion import Configuracion, guardar

    ruta = tmp_path / "config.json"
    guardar(Configuracion(perfil="bajo_4", ganancia=3.0), ruta)
    _, sesion = construir_aplicacion(ruta_config=ruta)
    assert sesion.configuracion.perfil == "bajo_4"
    assert sesion.configuracion.ganancia == 3.0
    sesion.detener()


def test_esperar_al_servidor_agota_el_limite_si_nadie_escucha():
    """Si el puerto no acepta conexiones, debe devolver False sin colgarse.

    Se usa un límite muy corto (0,3 s) y un puerto alto del rango efímero donde
    no hay nada escuchando: no se levanta ningún servidor real ni se ocupa un
    puerto (no se hace ``bind``, solo se intenta conectar), así que basta con
    comprobar el camino del límite agotado.
    """
    puerto_sin_nada_escuchando = 47125
    assert _esperar_al_servidor(puerto_sin_nada_escuchando, limite_espera=0.3) is False
