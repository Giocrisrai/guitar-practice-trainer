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


def test_usar_el_microfono_con_el_rocksmith_conectado_avisa_del_error_probable():
    """El cable está enchufado pero no elegido: casi siempre es una equivocación."""
    resultado = diagnosticar(
        dispositivos=[MICROFONO, CABLE], cable=MICROFONO, nivel_db=-40.0, rocksmith=CABLE
    )
    assert resultado.estado == "otro_dispositivo"
    assert NOMBRE_ROCKSMITH in resultado.accion


def test_usar_el_microfono_sin_el_rocksmith_presente_respeta_la_eleccion():
    """Sin el cable en la lista, elegir el micrófono es una decisión legítima."""
    resultado = diagnosticar(
        dispositivos=[MICROFONO], cable=MICROFONO, nivel_db=-40.0, rocksmith=None
    )
    assert resultado.estado == "ok"
    assert resultado.mensaje == "Dispositivo activo: MacBook Pro Microphone"


def test_si_la_sesion_no_espera_notas_el_silencio_no_acusa_al_cable():
    """El defecto: una alarma falsa en cuanto el usuario deja de tocar.

    Al terminar la pasada el usuario deja de tocar, el nivel se cae y la pantalla
    le decia que subiera el volumen de una guitarra que esta perfectamente bien.
    El silencio de una sesion que no espera notas es lo normal, no una averia, y
    acusar al cable ahi es gastar el aviso justo cuando es falso.

    La distincion es por ESTADO DE LA SESION y no por un temporizador: quien
    pregunta dice si esta esperando que alguien toque, y esa es toda la regla.
    """
    resultado = diagnosticar(
        dispositivos=[CABLE], cable=CABLE, nivel_db=-95.0, esperando_notas=False
    )
    assert resultado.estado == "ok"
    assert "volumen" not in resultado.accion.lower()


def test_el_aviso_del_cable_sigue_saliendo_cuando_si_se_esperan_notas():
    """La positiva de la de arriba, que es el caso legitimo del aviso y el que no
    se puede perder: el usuario SI esta intentando tocar y no llega señal."""
    resultado = diagnosticar(
        dispositivos=[CABLE], cable=CABLE, nivel_db=-95.0, esperando_notas=True
    )
    assert resultado.estado == "sin_senal"


def test_sin_esperar_notas_los_demas_fallos_se_siguen_diciendo():
    """Solo se calla la falta de señal. Que el cable no aparezca, que no haya
    permiso o que el dispositivo en uso no sea el cable son hechos del montaje y
    no dependen de que nadie este tocando."""
    sin_permiso = diagnosticar(dispositivos=[], cable=None, esperando_notas=False)
    assert sin_permiso.estado == "sin_permiso"
    sin_cable = diagnosticar(
        dispositivos=[MICROFONO], cable=None, esperando_notas=False
    )
    assert sin_cable.estado == "sin_dispositivo"
    otro = diagnosticar(
        dispositivos=[MICROFONO, CABLE],
        cable=MICROFONO,
        nivel_db=-95.0,
        rocksmith=CABLE,
        esperando_notas=False,
    )
    assert otro.estado == "otro_dispositivo"
