import json

import pytest

from servidor.configuracion import Configuracion, calibrar_umbral, cargar, guardar


def test_los_valores_por_defecto_son_los_de_la_spec():
    config = Configuracion()
    assert config.perfil == "guitarra_estandar"
    assert config.umbral_ruido_dbfs == -60.0
    assert config.referencia_a4 == 440.0
    assert config.ganancia == 1.0
    assert config.detector == "yin"
    assert config.dispositivo is None


def test_un_perfil_inexistente_se_rechaza_con_mensaje_claro():
    with pytest.raises(ValueError, match="perfil"):
        Configuracion(perfil="ukelele").validar()


def test_una_ganancia_negativa_se_rechaza():
    with pytest.raises(ValueError, match="ganancia"):
        Configuracion(ganancia=-1.0).validar()


def test_una_referencia_absurda_se_rechaza():
    with pytest.raises(ValueError, match="referencia"):
        Configuracion(referencia_a4=20.0).validar()


def test_un_detector_inexistente_se_rechaza():
    """El detector se valida contra el registro, no se acepta a ciegas."""
    with pytest.raises(ValueError, match="detector"):
        Configuracion(detector="inexistente").validar()


def test_un_umbral_de_ruido_fuera_de_rango_se_rechaza():
    """Sobre 0 dBFS no hay señal posible; bajo -120 no hay convertidor que llegue."""
    with pytest.raises(ValueError, match="umbral"):
        Configuracion(umbral_ruido_dbfs=20.0).validar()
    with pytest.raises(ValueError, match="umbral"):
        Configuracion(umbral_ruido_dbfs=-300.0).validar()


def test_guardar_y_cargar_conserva_todo(tmp_path):
    ruta = tmp_path / "config.json"
    original = Configuracion(dispositivo="Rocksmith USB Guitar Adapter", perfil="bajo_5", ganancia=2.5)
    guardar(original, ruta)
    assert cargar(ruta) == original


def test_guardar_no_deja_archivos_temporales(tmp_path):
    """La escritura atomica no debe dejar restos: solo el archivo final."""
    ruta = tmp_path / "config.json"
    guardar(Configuracion(), ruta)
    assert list(tmp_path.iterdir()) == [ruta]


def test_cargar_sin_archivo_da_los_valores_por_defecto(tmp_path):
    assert cargar(tmp_path / "no_existe.json") == Configuracion()


def test_un_archivo_corrupto_no_rompe_el_arranque(tmp_path):
    """Preferible arrancar con valores por defecto que no arrancar."""
    ruta = tmp_path / "config.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cargar(ruta) == Configuracion()


def test_un_archivo_con_campos_desconocidos_los_ignora(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"perfil": "bajo_4", "inventado": 1}), encoding="utf-8")
    assert cargar(ruta).perfil == "bajo_4"


def test_la_calibracion_deja_margen_sobre_el_ruido():
    """Niveles medidos en el equipo real: ruido en torno a -74 dBFS."""
    assert calibrar_umbral([-74.4, -74.1, -74.8, -73.9]) == pytest.approx(-60.2, abs=0.5)


def test_la_calibracion_descarta_un_golpe_accidental():
    """Un ruido puntual durante la calibración no debe subir el umbral."""
    con_golpe = calibrar_umbral([-74.0, -74.0, -30.0, -74.0, -74.0])
    assert con_golpe == pytest.approx(-60.0, abs=0.5)


def test_el_margen_de_calibracion_es_ajustable():
    assert calibrar_umbral([-74.0], margen_db=20.0) == pytest.approx(-54.0, abs=0.1)


def test_cargar_un_archivo_con_valores_invalidos_da_los_valores_por_defecto(tmp_path):
    """Un config_local.json editado a mano no debe reventar el arranque.

    Es lo que promete el docstring de cargar(): valores razonables antes que un
    traceback en la cara del usuario.
    """
    ruta = tmp_path / "config.json"
    ruta.write_text(
        json.dumps({"perfil": "ukelele", "detector": "inexistente"}), encoding="utf-8"
    )
    assert cargar(ruta) == Configuracion()
