"""La sesion de practica: une el generador, el evaluador y el metronomo."""

from typing import Callable

from nucleo.ejercicios.evaluacion import EvaluadorEjercicio
from nucleo.ejercicios.generadores.arpegios import generar_arpegio
from nucleo.ejercicios.generadores.escalas import generar_escala
from nucleo.ejercicios.generadores.intervalos import generar_intervalo
from nucleo.ejercicios.generadores.lectura import generar_lectura
from nucleo.ejercicios.modelo import Ejercicio
from nucleo.sintesis import Metronomo, SalidaAudio
from servidor.sesion import Sesion

GENERADORES: dict[str, Callable[..., Ejercicio]] = {
    "escala": generar_escala,
    "arpegio": generar_arpegio,
    "intervalo": generar_intervalo,
    "lectura": generar_lectura,
}


class SesionPractica:
    """Propietaria del ejercicio en curso, su evaluador y su metronomo.

    Se suscribe al flujo de la sesion de audio en lugar de muestrearlo: la
    deteccion de ataques necesita todos los resultados, no el ultimo.
    """

    def __init__(self, sesion_audio: Sesion, salida: SalidaAudio | None = None) -> None:
        self._sesion_audio = sesion_audio
        self._salida = salida or SalidaAudio()
        self._ejercicio: Ejercicio | None = None
        self._evaluador: EvaluadorEjercicio | None = None
        self._metronomo: Metronomo | None = None

    @property
    def activa(self) -> bool:
        return self._evaluador is not None

    @property
    def ejercicio(self) -> Ejercicio | None:
        return self._ejercicio

    def generar(self, familia: str, **parametros) -> Ejercicio:
        """Genera un ejercicio de la familia pedida.

        Los errores de parametros suben tal cual desde el generador: sus mensajes
        ya explican que escala o que perfil no existe.
        """
        if familia not in GENERADORES:
            disponibles = ", ".join(sorted(GENERADORES))
            raise ValueError(f"La familia '{familia}' no existe. Opciones: {disponibles}")
        return GENERADORES[familia](**parametros)

    def _observar(self, resultado, instante: float) -> None:
        """Alimenta al evaluador. Se invoca en el hilo de analisis: solo comparaciones."""
        evaluador = self._evaluador
        if evaluador is not None:
            evaluador.procesar(resultado, instante)

    def iniciar(self, ejercicio: Ejercicio, con_metronomo: bool = True) -> dict:
        """Arranca un ejercicio. Devuelve el estado inicial.

        Si se pide metronomo y no hay salida de audio, o el tempo del ejercicio
        no es uno que el metronomo acepte (por encima de TEMPO_MAXIMO_PPM), el
        ejercicio arranca igual sin el: la spec dice que quedarse sin metronomo
        degrada la experiencia, no la impide. Los cuatro generadores producen
        tempos de 60 a 95 por defecto, asi que esto ultimo no deberia ocurrir en
        la practica, pero un ejercicio con un tempo fuera de rango no debe poder
        tumbar `iniciar()`.
        """
        self.detener()
        self._ejercicio = ejercicio
        self._evaluador = EvaluadorEjercicio(ejercicio)
        self._sesion_audio.registrar_observador(self._observar)

        sonando = False
        if con_metronomo and self._salida.abrir():
            try:
                self._metronomo = Metronomo(ejercicio.tempo, salida=self._salida)
            except ValueError:
                self._metronomo = None
            else:
                sonando = self._metronomo.iniciar()
        return {**self.estado(), "metronomo": sonando}

    def detener(self) -> None:
        """Para el ejercicio y suelta todo. Seguro de llamar varias veces."""
        self._sesion_audio.quitar_observador(self._observar)
        if self._metronomo is not None:
            self._metronomo.detener()
            self._metronomo = None
        self._salida.cerrar()
        self._evaluador = None
        self._ejercicio = None

    def estado(self) -> dict:
        """Lo que la interfaz necesita: el ejercicio, el avance y el informe."""
        evaluador = self._evaluador
        return {
            "ejercicio": None if self._ejercicio is None else self._ejercicio.a_dict(),
            "evaluacion": None if evaluador is None else evaluador.estado.a_dict(),
            "informe": None if evaluador is None else evaluador.resultado().a_dict(),
            "metronomo": self._metronomo is not None and self._metronomo.sonando,
        }
