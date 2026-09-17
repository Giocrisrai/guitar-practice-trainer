from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.diagnostico import diagnosticar

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
MICROFONO = DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)


def test_lista_vacia_significa_falta_de_permiso():
    """macOS no da error cuando falta el permiso: devuelve una lista vacía."""
    resultado = diagnosticar(dispositivos=[], cable=None)
    assert resultado.estado == "sin_permiso"
    assert "Micrófono" in resultado.accion


def test_sin_el_cable_lo_dice_sin_hablar_de_permisos():
    resultado = diagnosticar(dispositivos=[MICROFONO], cable=None)
    assert resultado.estado == "sin_dispositivo"
    assert "USB" in resultado.accion


def test_nivel_bajo_sugiere_el_volumen_de_la_guitarra():
    """La causa más frecuente y la más fácil de pasar por alto."""
    resultado = diagnosticar(dispositivos=[CABLE], cable=CABLE, nivel_db=-95.0)
    assert resultado.estado == "sin_senal"
    assert "volumen" in resultado.accion.lower()


def test_todo_en_orden_da_ok():
    resultado = diagnosticar(dispositivos=[CABLE], cable=CABLE, nivel_db=-40.0)
    assert resultado.estado == "ok"


def test_sin_medicion_de_nivel_no_se_declara_falta_de_senal():
    """Antes de capturar no se sabe si hay señal: no se debe acusar en falso."""
    resultado = diagnosticar(dispositivos=[CABLE], cable=CABLE, nivel_db=None)
    assert resultado.estado == "ok"


def test_el_diagnostico_lista_los_dispositivos_para_elegir_a_mano():
    resultado = diagnosticar(dispositivos=[MICROFONO, CABLE], cable=CABLE)
    assert len(resultado.a_dict()["dispositivos"]) == 2
    assert resultado.a_dict()["dispositivos"][1]["nombre"] == NOMBRE_ROCKSMITH
