"""La sesion de practica: une el generador, el evaluador, el metronomo y el tono."""

from typing import Callable

from nucleo.ejercicios.evaluacion import EstadoEvaluacion, EvaluadorEjercicio
from nucleo.ejercicios.generadores.arpegios import generar_arpegio
from nucleo.ejercicios.generadores.escalas import generar_escala
from nucleo.ejercicios.generadores.intervalos import generar_intervalo
from nucleo.ejercicios.generadores.lectura import generar_lectura
from nucleo.ejercicios.modelo import Ejercicio
from nucleo.sintesis import Metronomo, ReproductorTonos, SalidaAudio
from servidor.sesion import Sesion

GENERADORES: dict[str, Callable[..., Ejercicio]] = {
    "escala": generar_escala,
    "arpegio": generar_arpegio,
    "intervalo": generar_intervalo,
    "lectura": generar_lectura,
}


class SesionPractica:
    """Propietaria del ejercicio en curso, su evaluador, su metronomo y su tono.

    Se suscribe al flujo de la sesion de audio en lugar de muestrearlo: la
    deteccion de ataques necesita todos los resultados, no el ultimo.
    """

    def __init__(self, sesion_audio: Sesion, salida: SalidaAudio | None = None) -> None:
        self._sesion_audio = sesion_audio
        self._salida = salida or SalidaAudio()
        self._ejercicio: Ejercicio | None = None
        self._evaluador: EvaluadorEjercicio | None = None
        self._metronomo: Metronomo | None = None
        self._reproductor: ReproductorTonos | None = None
        # Indice de la nota cuya referencia ya se pidio, para no repetirla en
        # cada cuadro. -1 es "ninguna todavia": el indice 0 es una nota real.
        self._indice_referencia = -1

    @property
    def activa(self) -> bool:
        return self._evaluador is not None

    @property
    def ejercicio(self) -> Ejercicio | None:
        return self._ejercicio

    def generar(self, familia: str, **parametros) -> Ejercicio:
        """Genera un ejercicio de la familia pedida.

        Si nadie pide un perfil de afinacion se usa el que el usuario tiene
        activo en el afinador: pedir notas de guitarra en afinacion estandar a
        quien tiene el bajo enchufado, o la guitarra en Drop D, es pedir notas
        que no estan en su mastil. El perfil viaja igual que los demas
        parametros, asi que quien quiera otro puede mandarlo.

        Los errores de parametros suben tal cual desde el generador: sus mensajes
        ya explican que escala o que perfil no existe.
        """
        if familia not in GENERADORES:
            disponibles = ", ".join(sorted(GENERADORES))
            raise ValueError(f"La familia '{familia}' no existe. Opciones: {disponibles}")
        parametros.setdefault("perfil_clave", self._sesion_audio.configuracion.perfil)
        return GENERADORES[familia](**parametros)

    def _observar(self, resultado, instante: float) -> None:
        """Alimenta al evaluador y reacciona al estado que devuelve.

        Se invoca DENTRO del hilo de analisis, asi que nada de lo que hace aqui
        puede bloquear: pedir un tono deja una peticion en un buzon y vuelve, y
        pausar el metronomo levanta una bandera. Ninguna de las dos cosas espera
        a que la salida de audio escriba nada.
        """
        evaluador = self._evaluador
        if evaluador is None:
            return
        estado = evaluador.procesar(resultado, instante)
        self._sonar_referencia(estado)
        self._ajustar_metronomo()

    def _sonar_referencia(self, estado: EstadoEvaluacion) -> None:
        """Hace sonar la nota de referencia al entrar en una nota nueva.

        Una sola vez por nota, no en cada cuadro: de eso se encarga
        `_indice_referencia`. Las familias sin entrenamiento de oido traen
        `referencia_midi = None` y aqui no suena nada.

        Sin esto, `referencia_midi` viajaba del generador al modelo, al `a_dict()`,
        al WebSocket y a la interfaz sin que nadie lo consumiera, y el ejercicio
        de intervalos que la spec §4.1 describe como entrenamiento de oido era en
        realidad uno de lectura con la respuesta escrita en la pantalla.
        """
        if estado.indice == self._indice_referencia:
            return
        self._indice_referencia = estado.indice
        nota = estado.nota_actual
        if nota is None or nota.referencia_midi is None or self._reproductor is None:
            return
        self._reproductor.pedir(
            nota.referencia_midi, self._sesion_audio.configuracion.referencia_a4
        )

    def _ajustar_metronomo(self) -> None:
        """Pausa el metronomo mientras no hay senal, y lo reanuda al volver.

        La spec §5 pide que al perder la senal el ejercicio se pause. La otra
        mitad de esa pausa, el temporizador de la ayuda, ya no avanza sin senal
        creible (ver `EvaluadorEjercicio`); esta es la mitad audible: un
        metronomo marcando el compas con el cable desenchufado es la misma
        mentira que una pantalla congelada diciendo "ok".
        """
        metronomo = self._metronomo
        if metronomo is None:
            return
        if self._sesion_audio.senal_ausente:
            metronomo.pausar()
        else:
            metronomo.reanudar()

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
        self._indice_referencia = -1

        # La salida se abre tambien sin metronomo cuando el ejercicio trae notas
        # de referencia: es lo que hace sonar el entrenamiento de oido. Si el
        # ejercicio no necesita ninguna de las dos cosas no se toca el
        # dispositivo, para no reservar los altavoces sin motivo.
        quiere_referencias = any(n.referencia_midi is not None for n in ejercicio.notas)
        hay_salida = (con_metronomo or quiere_referencias) and self._salida.abrir()

        if quiere_referencias and hay_salida:
            self._reproductor = ReproductorTonos(salida=self._salida)
            self._reproductor.iniciar()

        sonando = False
        if con_metronomo and hay_salida:
            try:
                self._metronomo = Metronomo(ejercicio.tempo, salida=self._salida)
            except ValueError:
                self._metronomo = None
            else:
                sonando = self._metronomo.iniciar()

        # El observador se registra AL FINAL, cuando el metronomo y el reproductor
        # ya estan en su sitio: si se registrara antes, el primer cuadro podria
        # entrar en `_observar` con `_reproductor` todavia a None y la referencia
        # de la nota 0 no sonaria nunca (su indice ya estaria marcado como visto).
        self._sesion_audio.registrar_observador(self._observar)

        # La referencia de la primera nota se pide aqui y no desde `_observar`
        # porque `_observar` solo corre cuando llega audio: sin cable enchufado no
        # hay cuadros, y el alumno se quedaria esperando un tono que no llega.
        estado = self._evaluador.estado
        self._sonar_referencia(estado)
        return {**self.estado(), "metronomo": sonando}

    def detener(self) -> None:
        """Para el ejercicio y suelta todo. Seguro de llamar varias veces.

        El observador se quita PRIMERO: asi ningun cuadro posterior puede pedir un
        tono o tocar el metronomo que las lineas siguientes estan desmontando.
        """
        self._sesion_audio.quitar_observador(self._observar)
        if self._metronomo is not None:
            self._metronomo.detener()
            self._metronomo = None
        if self._reproductor is not None:
            self._reproductor.detener()
            self._reproductor = None
        self._salida.cerrar()
        self._evaluador = None
        self._ejercicio = None
        self._indice_referencia = -1

    def estado(self) -> dict:
        """Lo que la interfaz necesita: el ejercicio, el avance y el informe.

        Ajusta aqui la pausa del metronomo, ademas de en `_observar`, porque los
        dos sitios cubren mitades distintas del problema: `_observar` solo corre
        cuando llega audio, y el caso que hay que pausar es precisamente el de
        que deje de llegar. Al desaparecer el dispositivo la sesion publica un
        unico resultado de silencio y despues entra en el ciclo de reintento sin
        publicar nada mas, asi que sin esto el metronomo seguiria marcando el
        compas para siempre con el cable desenchufado. Este metodo, en cambio, lo
        llama el WebSocket a 30 Hz. Poner la bandera es idempotente y no
        bloquea, asi que llamarlo desde los dos hilos es seguro.
        """
        self._ajustar_metronomo()
        evaluador = self._evaluador
        metronomo = self._metronomo
        return {
            "ejercicio": None if self._ejercicio is None else self._ejercicio.a_dict(),
            "evaluacion": None if evaluador is None else evaluador.estado.a_dict(),
            "informe": None if evaluador is None else evaluador.resultado().a_dict(),
            "metronomo": metronomo is not None and metronomo.sonando,
            # Pausado por falta de senal (spec §5). Se publica aparte de
            # "metronomo" para no cambiar el significado de un campo que la
            # interfaz ya lee: el hilo sigue vivo, solo no emite.
            "metronomo_pausado": metronomo is not None and metronomo.pausado,
        }
