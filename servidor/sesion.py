"""Une captura y análisis, y los mantiene corriendo en segundo plano."""

import threading
import time
from typing import Callable

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import nivel_dbfs
from nucleo.analisis.pipeline import Analizador, ResultadoAnalisis
from nucleo.captura import CapturaAudio, buscar_rocksmith, listar_dispositivos_entrada
from servidor.configuracion import Configuracion, calibrar_umbral
from servidor.diagnostico import Diagnostico, diagnosticar

# Cada cuánto analiza el hilo de trabajo. 21 ms son 512 muestras a 48 kHz: el mismo
# ritmo al que llegan los bloques, sin analizar más veces de las que hay datos nuevos.
INTERVALO_ANALISIS = 0.021


class Sesion:
    """Propietaria única de la captura y el analizador.

    Guarda solo el último resultado, no una cola: un consumidor lento debe ver el
    presente, no desenterrar el pasado.
    """

    def __init__(
        self,
        configuracion: Configuracion,
        crear_captura: Callable | None = None,
        listar: Callable | None = None,
    ) -> None:
        self.configuracion = configuracion
        self._crear_captura = crear_captura or (lambda **kw: CapturaAudio(**kw))
        self._listar = listar or listar_dispositivos_entrada
        self._captura = None
        self._analizador: Analizador | None = None
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._ultimo: ResultadoAnalisis | None = None
        self._candado = threading.Lock()

    @property
    def activa(self) -> bool:
        return self._captura is not None

    @property
    def latencia_ms(self) -> float:
        return self._captura.latencia_ms if self._captura else 0.0

    def diagnostico(self, nivel_db: float | None = None) -> Diagnostico:
        """Estado actual del montaje."""
        dispositivos = self._listar()
        rocksmith = buscar_rocksmith(dispositivos)
        cable = rocksmith
        if self.configuracion.dispositivo is not None:
            elegido = next(
                (d for d in dispositivos if d.indice == self.configuracion.dispositivo), None
            )
            if elegido is None:
                # El dispositivo elegido a mano ya no está: decirlo, no sustituirlo
                # en silencio por el Rocksmith.
                return Diagnostico(
                    estado="sin_dispositivo",
                    mensaje=(
                        f"El dispositivo elegido (índice {self.configuracion.dispositivo}) "
                        "ya no está disponible."
                    ),
                    accion=(
                        "Reconéctalo si es un dispositivo USB, o elige otro "
                        "dispositivo en los ajustes."
                    ),
                    dispositivos=dispositivos,
                )
            cable = elegido
        return diagnosticar(
            dispositivos,
            cable,
            nivel_db,
            self.configuracion.umbral_ruido_dbfs,
            rocksmith,
        )

    def _construir_analizador(self) -> Analizador:
        return Analizador(
            PERFILES[self.configuracion.perfil],
            umbral_ruido_dbfs=self.configuracion.umbral_ruido_dbfs,
            referencia_a4=self.configuracion.referencia_a4,
            confianza_minima=self.configuracion.confianza_minima,
            nombre_detector=self.configuracion.detector,
        )

    def iniciar(self) -> Diagnostico:
        """Abre el dispositivo y arranca el hilo de análisis.

        Devuelve el diagnóstico: si no es "ok", la sesión no queda activa y el
        diagnóstico explica qué falta.
        """
        if self.activa:
            return self.diagnostico()

        estado = self.diagnostico()
        if estado.estado in ("sin_permiso", "sin_dispositivo"):
            return estado

        indice = self.configuracion.dispositivo
        if indice is None:
            cable = buscar_rocksmith(self._listar())
            if cable is None:
                return estado
            indice = cable.indice

        self._captura = self._crear_captura(
            indice_dispositivo=indice, ganancia=self.configuracion.ganancia
        )
        if not self._captura.iniciar():
            error = self._captura.ultimo_error
            self._captura = None
            return Diagnostico(
                estado="sin_dispositivo",
                mensaje="No se pudo abrir el dispositivo de audio.",
                accion=f"Error del sistema: {error}. Prueba a reconectar el cable.",
                dispositivos=self._listar(),
            )

        self._analizador = self._construir_analizador()
        self._parar.clear()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return self.diagnostico()

    def _trabajar(self) -> None:
        """Hilo de análisis. Lee la última ventana, la analiza y guarda el resultado."""
        while not self._parar.is_set():
            captura, analizador = self._captura, self._analizador
            if captura is not None and analizador is not None:
                muestras = captura.leer_ventana(analizador.tamano_ventana)
                if muestras is not None:
                    resultado = analizador.procesar(muestras)
                    with self._candado:
                        self._ultimo = resultado
            time.sleep(INTERVALO_ANALISIS)

    def ultimo_resultado(self) -> ResultadoAnalisis | None:
        """Resultado más reciente, o None si aún no hay ninguno."""
        with self._candado:
            return self._ultimo

    def aplicar(self, configuracion: Configuracion) -> None:
        """Cambia la configuración en caliente.

        Si cambia el dispositivo o la ganancia hay que reabrir el stream; para el
        resto basta con reconstruir el analizador, que es instantáneo.
        """
        configuracion.validar()
        reabrir = (
            configuracion.dispositivo != self.configuracion.dispositivo
            or configuracion.ganancia != self.configuracion.ganancia
        )
        self.configuracion = configuracion
        if reabrir and self.activa:
            self.detener()
            self.iniciar()
        elif self.activa:
            self._analizador = self._construir_analizador()
            with self._candado:
                self._ultimo = None

    def calibrar(self, segundos: float = 2.0) -> float:
        """Mide el piso de ruido durante unos segundos y devuelve el umbral sugerido.

        El usuario debe estar en silencio mientras dura. No modifica la
        configuración: devolver el valor y dejar que el usuario lo acepte es
        preferible a cambiarle los ajustes por sorpresa.
        """
        if not self.activa or self._analizador is None:
            return self.configuracion.umbral_ruido_dbfs
        ventana = self._analizador.tamano_ventana
        niveles = []
        final = time.monotonic() + segundos
        while time.monotonic() < final:
            muestras = self._captura.leer_ventana(ventana)
            if muestras is not None:
                niveles.append(nivel_dbfs(muestras))
            time.sleep(0.05)
        return calibrar_umbral(niveles)

    def detener(self) -> None:
        """Para el hilo y cierra el dispositivo. Seguro de llamar varias veces."""
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
        if self._captura is not None:
            self._captura.detener()
            self._captura = None
        self._analizador = None
        with self._candado:
            self._ultimo = None
