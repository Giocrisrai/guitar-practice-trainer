"""La sesion de practica con un ejercicio de acordes.

Las piezas de audio son falsas, igual que en `test_sesion_practica.py`: lo que se
comprueba aqui es el cableado -que la familia "cambios" llega al evaluador de
cambios y no al monofonico, y que el detector recibe la ventana larga-, no la
deteccion en si, que ya tiene sus propias pruebas.
"""

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.acordes import VENTANA_ACORDES
from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.ejercicios.cambios import CUADROS_PARA_ACORDE_ESTABLE
from nucleo.ejercicios.generadores.acordes import acorde_de_clave
from nucleo.gemelo.salida import SalidaCapturada
from nucleo.musica import midi_a_frecuencia
from servidor.configuracion import Configuracion
from servidor.ejercicios import GENERADORES, SesionPractica
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000
DO = (48, 52, 55, 60, 64)


def rasgueo(midis, n: int) -> np.ndarray:
    """Las notas sonando a la vez, con armonicos: lo que el detector espera ver."""
    t = np.arange(n) / FS
    onda = np.zeros_like(t)
    for indice, midi in enumerate(midis):
        f0 = midi_a_frecuencia(midi)
        generador = np.random.default_rng(indice)
        for h in range(1, 9):
            onda += (
                (1.0 / h**1.2)
                * np.exp(-t / (1.5 / h))
                * np.sin(2.0 * np.pi * f0 * h * t + generador.uniform(0.0, 2.0 * np.pi))
            )
    pico = float(np.max(np.abs(onda)))
    return (onda / pico * 0.5).astype(np.float32) if pico > 0.0 else onda.astype(np.float32)


class CapturaDeAcorde:
    """Captura falsa que siempre devuelve un Do mayor rasgueado."""

    def __init__(self, **kwargs):
        self.ultimo_error = None
        self.latencia_ms = 12.0
        self.total_capturado = 0
        self.ventanas_pedidas: list[int] = []

    def iniciar(self) -> bool:
        return True

    def detener(self) -> None:
        pass

    def leer_ventana(self, n: int):
        self.total_capturado += n
        self.ventanas_pedidas.append(n)
        return rasgueo(DO, n)


def practica(captura_clase=CapturaDeAcorde) -> tuple[SesionPractica, list]:
    capturas: list = []

    def crear(**kw):
        captura = captura_clase(**kw)
        capturas.append(captura)
        return captura

    sesion = Sesion(
        Configuracion(dispositivo=None, perfil="guitarra_estandar"),
        crear_captura=crear,
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    return SesionPractica(sesion, salida=SalidaCapturada().salida), capturas


class TestLaFamilia:
    def test_la_familia_de_cambios_esta_registrada(self):
        assert "cambios" in GENERADORES

    def test_generar_cambios_da_un_ejercicio_de_acordes_y_no_de_notas(self):
        sesion, _ = practica()
        try:
            ejercicio = sesion.generar("cambios", claves=("do", "sol"), repeticiones=2)
            assert ejercicio.notas == ()
            assert len(ejercicio.acordes) == 4
        finally:
            sesion.detener()

    def test_una_familia_que_no_existe_sigue_dando_el_mismo_error(self):
        sesion, _ = practica()
        try:
            try:
                sesion.generar("rasgueo_flamenco")
            except ValueError as error:
                assert "cambios" in str(error)
            else:
                raise AssertionError("tenia que rechazarla")
        finally:
            sesion.detener()


class TestElCableado:
    def test_iniciar_un_ejercicio_de_acordes_elige_el_evaluador_de_cambios(self):
        sesion, _ = practica()
        try:
            ejercicio = sesion.generar("cambios", claves=("do", "sol"), repeticiones=1)
            estado = sesion.iniciar(ejercicio, con_metronomo=False)
            assert estado["es_de_acordes"] is True
            assert estado["evaluacion"]["acorde_actual"]["nombre"] == "Do mayor"
        finally:
            sesion.detener()

    def test_un_ejercicio_de_notas_sigue_yendo_al_evaluador_monofonico(self):
        sesion, _ = practica()
        try:
            estado = sesion.iniciar(
                sesion.generar("escala", raiz_midi=48, tipo="mayor"), con_metronomo=False
            )
            assert estado["es_de_acordes"] is False
            assert "nota_actual" in estado["evaluacion"]
        finally:
            sesion.detener()

    def test_el_detector_pide_su_ventana_larga_y_no_la_del_perfil(self):
        """8192 y no 4096: es la razon de que exista `leer_ventana_cruda`."""
        sesion, capturas = practica()
        try:
            ejercicio = sesion.generar("cambios", claves=("do", "sol"), repeticiones=1)
            sesion.iniciar(ejercicio, con_metronomo=False)
            for cuadro in range(CUADROS_PARA_ACORDE_ESTABLE + 2):
                sesion._observar(None, cuadro * 0.021)
            assert VENTANA_ACORDES in capturas[0].ventanas_pedidas
        finally:
            sesion.detener()

    def test_tocar_el_acorde_pedido_avanza_el_ejercicio(self):
        sesion, _ = practica()
        try:
            ejercicio = sesion.generar("cambios", claves=("do", "sol"), repeticiones=1)
            sesion.iniciar(ejercicio, con_metronomo=False)
            for cuadro in range(CUADROS_PARA_ACORDE_ESTABLE + 2):
                sesion._observar(None, cuadro * 0.021)
            assert sesion.estado()["evaluacion"]["indice"] == 1
        finally:
            sesion.detener()

    def test_detener_suelta_el_evaluador_de_cambios(self):
        sesion, _ = practica()
        ejercicio = sesion.generar("cambios", claves=("do", "sol"), repeticiones=1)
        sesion.iniciar(ejercicio, con_metronomo=False)
        assert sesion.activa is True
        sesion.detener()
        assert sesion.activa is False
        assert sesion.estado()["es_de_acordes"] is False

    def test_el_informe_de_cambios_trae_el_tiempo_medio(self):
        sesion, _ = practica()
        try:
            ejercicio = sesion.generar("cambios", claves=("do", "sol"), repeticiones=1)
            sesion.iniciar(ejercicio, con_metronomo=False)
            informe = sesion.estado()["informe"]
            assert "tiempo_medio_de_cambio_s" in informe
            assert "cuerdas_problematicas" in informe
        finally:
            sesion.detener()


class TestLaVentanaCruda:
    def test_sin_captura_abierta_no_hay_ventana(self):
        sesion = Sesion(
            Configuracion(dispositivo=None, perfil="guitarra_estandar"),
            crear_captura=lambda **kw: CapturaDeAcorde(**kw),
            listar=lambda: [],
        )
        assert sesion.leer_ventana_cruda(VENTANA_ACORDES) is None

    def test_con_captura_devuelve_exactamente_lo_que_se_pide(self):
        sesion, _ = practica()
        try:
            # La ventana cruda la sirve la sesion de AUDIO, no la de practica.
            ventana = sesion._sesion_audio.leer_ventana_cruda(VENTANA_ACORDES)
            assert ventana is not None
            assert ventana.size == VENTANA_ACORDES
        finally:
            sesion.detener()


class TestElAcordeEsperado:
    def test_los_midis_que_el_detector_recibe_son_los_del_acorde_en_curso(self):
        """Si esto se desalineara, el detector juzgaria el acorde anterior."""
        esperado = acorde_de_clave("do", PERFILES["guitarra_estandar"])
        assert esperado.midis == DO
