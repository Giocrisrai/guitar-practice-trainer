"""Seguir una pieza: manda el reloj, no los aciertos.

La diferencia con `EvaluadorEjercicio` no es de detalle, es de genero. Un
ejercicio es por turnos: la nota espera a que la aciertes y no avanza hasta
entonces. Una pieza es musica: el reloj corre, la nota pasa, y si no llegaste no
se repite. De ahi sale todo lo que hace este modulo:

- El indice de la nota en curso lo decide el reloj (`avanzar_a`), no el acierto.
- Una pulsacion no hace avanzar nada: solo se anota contra la nota a la que
  corresponde, con su desfase.
- Fallar no bloquea ni descalifica: `acertada` y `clasificacion` informan, igual
  que la afinacion en los ejercicios.

Que nota sono y cuando lo decide `DetectorPulsaciones`, compartido con el
evaluador de ejercicios. Aqui solo se decide a que nota de la pieza le toca cada
pulsacion y como de tarde llego.
"""

import threading
from dataclasses import dataclass

import numpy as np

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones, Pulsacion
from nucleo.musica import midi_de_nombre, nombre_de_midi
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos

# Cuanto puede desviarse una pulsacion del instante escrito y seguir contando
# como "a tiempo".
#
# De donde sale: por debajo de unos 30 ms dos ataques no se perciben como
# separados, asi que una ventana mas estrecha marcaria como error algo que el
# oido no distingue; por encima de unos 100 ms el desfase ya se oye como error, y
# llamarlo "a tiempo" seria mentir. Dentro de ese margen hay que descontar la
# latencia del cable, medida en 13,8 ms, que el alumno no toca mal sino que el
# programa oye tarde. 80 ms cae en ese hueco con sitio para la latencia.
#
# NO esta calibrado tocando: es un valor razonado sobre umbrales de percepcion y
# una latencia medida, no el resultado de sentarse con la guitarra a ver cuando
# un alumno siente que ha llegado tarde. Esa calibracion esta pendiente y es la
# unica que puede justificar mover este numero.
VENTANA_A_TIEMPO_S = 0.080

# Piso de la ventana de reclamo: lo mas lejos que se puede haber tocado una nota
# y seguir siendo un intento de ELLA, por corta que sea la figura.
#
# De donde sale: la ventana de reclamo se deriva de la duracion escrita (ver
# `SeguidorPieza._ventanas_reclamo_s`), y eso solo funciona mientras la figura sea
# larga. Con semicorcheas a 200 ppm la nota dura 75 ms y la ventana se quedaba en
# 155 ms: mas estrecha que el error de un principiante, asi que una nota tocada
# 200 ms tarde -que el brief quiere que cuente como "tarde"- no se adjudicaba a
# nadie y desaparecia del informe. Medio segundo esta muy por encima del retraso
# real de un principiante (los desfases que se ven tocando lento son de decenas de
# milisegundos, no de cientos) y muy por debajo del absurdo que la ventana existe
# para cortar (una pulsacion suelta 30 s despues del final). La ventana es el mayor
# de los dos: el piso manda en figuras cortas y la duracion manda en las largas.
#
# TAMPOCO esta calibrado tocando, igual que VENTANA_A_TIEMPO_S: es un orden de
# magnitud razonado, no el resultado de medirle el retraso a nadie con la guitarra
# en la mano. Esa calibracion sigue pendiente.
VENTANA_RECLAMO_MINIMA_S = 0.500


@dataclass(frozen=True)
class NotaTocada:
    """Una pulsacion ya adjudicada a una nota de la pieza.

    `indice` es la nota de la PIEZA a la que se adjudico; `midi` es lo que
    SONO, que es otra cosa en cuanto el alumno se equivoca (y es justo lo que la
    interfaz necesita para decirle que toco en su lugar). La nota escrita se
    recupera con `indice`, y `acertada` ya compara las dos.

    `desfase_s` es negativo si se toco antes de tiempo. Vale None -y con el
    `clasificacion`- cuando la pulsacion llego sin instante (ver
    `Pulsacion.instante`): no se sabe cuando empezo, y fabricar un desfase con el
    instante del cuadro mediria el retraso del detector, no el del alumno.
    """

    indice: int
    midi: int
    cents: float | None
    desfase_s: float | None
    clasificacion: str | None
    acertada: bool

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "midi": self.midi,
            "nombre": nombre_de_midi(self.midi),
            "cents": None if self.cents is None else round(self.cents, 1),
            "desfase_s": None if self.desfase_s is None else round(self.desfase_s, 3),
            "clasificacion": self.clasificacion,
            "acertada": self.acertada,
        }


@dataclass(frozen=True)
class EstadoCarril:
    """Lo que el carril necesita pintar en cada instante.

    `instante_s` es el reloj de la PIEZA, en segundos desde su comienzo: es la
    posicion del cabezal en el carril, no un instante del reloj del sistema.

    `indice_actual` es la ultima nota que ya empezo segun ese reloj. Antes de la
    primera señala a la primera y pasado el final se queda en la ultima: quien
    quiera saber si la pieza termino mira `completado`, no el indice. Si en ese
    instante hay un ACORDE -varias notas con el mismo inicio- señala a la ultima
    de ellas, que es una eleccion arbitraria entre iguales, porque el seguidor no
    sabe seguir acordes (ver `SeguidorPieza`). Esta frontera es la que lee la
    interfaz, asi que la arbitrariedad se dice aqui y no solo alla.

    `tocadas` solo trae las pulsaciones que se pudieron adjudicar. Una nota que
    nadie toco no aparece: el carril la pinta sin marca, y contar "cuantas
    faltan" es `total` menos lo que hay aqui.
    """

    instante_s: float
    indice_actual: int
    total: int
    completado: bool
    tocadas: tuple[NotaTocada, ...]

    def a_dict(self) -> dict:
        return {
            "instante_s": round(self.instante_s, 3),
            "indice_actual": self.indice_actual,
            "total": self.total,
            "completado": self.completado,
            "tocadas": [tocada.a_dict() for tocada in self.tocadas],
        }


class SeguidorPieza:
    """Sigue una pieza con el reloj por delante y las pulsaciones por detras.

    Dos relojes, y no hay que confundirlos:

    - El reloj de la PIEZA, en segundos desde su comienzo, es el que dice que
      nota toca ahora. Se mueve con `avanzar_a`, que no consume audio: es lo que
      el servidor llama cuando no llega señal y lo que permite probar todo esto
      sin una sola espera real.
    - El reloj del ANALISIS es el que acompaña a cada cuadro de audio en
      `procesar`. Es `time.monotonic()`, con los dias de encendido de la maquina
      dentro. El seguidor guarda la correspondencia entre los dos, fijada en el
      primer cuadro tras colocar el reloj de la pieza, y traduce. Restar sin
      traducir haria que el desfase midiera la antiguedad del proceso en vez del
      error del alumno.

    Como se adjudica una pulsacion: de entre las notas sin cobrar que caen dentro
    de su ventana de reclamo, gana una cuya ALTURA coincida con lo que sono (la
    mas cercana de ellas si hay varias), y solo si ninguna coincide se cae a la
    mas cercana EN EL TIEMPO. La altura es informacion gratis y en un pasaje denso
    -notas a 75 ms unas de otras- es la unica que puede decir cual se quiso tocar:
    por cercania sola, una nota tocada 200 ms tarde se adjudicaba a la vecina y
    salia "a_tiempo" y equivocada. Los fallos de altura siguen yendo por cercania,
    que es donde tienen sentido.

    La altura DESEMPATA, no se salta nada: si la pulsacion cae a menos de
    `ventana_a_tiempo_s` del instante de una nota sin cobrar, se adjudica a una
    nota que el alumno ya haya alcanzado, coincida o no la altura. Una
    coincidencia de altura mas adelante en la pieza -una nota a la que el alumno
    todavia no ha llegado- no puede cobrar por delante de la que tiene debajo del
    dedo (ver `_adjudicar`).

    En ningun caso se adjudica a la nota en curso por estar en curso. Tocar antes
    de tiempo es lo normal -es lo que hace un musico que va con el pulso-,
    y adjudicar esa pulsacion a la nota anterior convertiria un adelanto de 50 ms
    en un fallo y ademas dejaria la nota buena sin cobrar. Cada nota se cobra una
    sola vez, acertada o no: una segunda pulsacion busca otra nota. Y todo esto tiene
    un limite: cada nota solo se puede reclamar desde su ventana de reclamo (su
    duracion escrita mas la ventana de "a tiempo", con un piso de
    `VENTANA_RECLAMO_MINIMA_S`; ver `_ventanas_reclamo_s`), y una pulsacion que no alcanza a ninguna no se anota ni
    cuenta como fallo. Sin ese limite, una nota que el alumno nunca toco acababa en
    el informe como tocada -y acertada- con un desfase absurdo.

    NO SABE SEGUIR ACORDES. `Pieza` admite dos notas con el mismo
    `inicio_pulsos` a proposito (los archivos de Guitar Pro de la etapa 3b los
    traen), pero debajo de este seguidor hay un detector de tono MONOFONICO: de
    un acorde lee una sola altura, y las demas notas de ese instante se quedan
    sin cobrar por muy bien que se toquen. El carril las pintara y las contara
    como no tocadas. Para seguir acordes hace falta deteccion polifonica, que no
    existe en este proyecto, asi que una pieza con acordes se puede pintar pero
    no se puede evaluar de forma justa.

    Candado: este seguidor lleva el suyo (`_candado`) y protege tambien al
    `DetectorPulsaciones`, que no lleva ninguno. `procesar` y `avanzar_a` corren
    en el hilo de analisis y `estado` se lee desde el hilo HTTP/WS (la Task 5 lo
    publica a 30 Hz): sin candado, una instantanea podia mezclar el reloj de
    antes de avanzar con las notas de despues. Toda mutacion del detector pasa
    por aqui; quien añada otro consumidor tiene que traer su propio candado.
    """

    def __init__(
        self,
        pieza: Pieza,
        detector: DetectorPulsaciones | None = None,
        ventana_a_tiempo_s: float = VENTANA_A_TIEMPO_S,
        ventana_reclamo_minima_s: float = VENTANA_RECLAMO_MINIMA_S,
    ) -> None:
        self.pieza = pieza
        self._detector = detector or DetectorPulsaciones()
        self.ventana_a_tiempo_s = ventana_a_tiempo_s
        self.ventana_reclamo_minima_s = ventana_reclamo_minima_s
        # Los instantes escritos, ya en segundos: se consultan en cada cuadro
        # (buscar la nota en curso y la mas cercana) y no cambian nunca.
        self._inicios_s = np.array(
            [pulsos_a_segundos(nota.inicio_pulsos, pieza.tempo) for nota in pieza.notas],
            dtype=float,
        )
        # Hasta donde puede estirarse una pulsacion para reclamar cada nota.
        #
        # Se deriva de la PIEZA y no es un numero clavado: la duracion escrita de
        # la nota mas la ventana de "a tiempo". Al bajar el tempo para practicar
        # lento la nota dura mas y la ventana se ensancha sola, que es lo que hace
        # falta (a 40 ppm nadie llega con la precision de 120).
        #
        # Pero derivarla solo de la duracion se rompe por abajo: con figuras cortas
        # a tempo rapido la ventana se vuelve mas estrecha que el error humano que
        # se quiere tolerar, asi que hay un piso, `VENTANA_RECLAMO_MINIMA_S`, y la
        # ventana es el MAYOR de los dos.
        #
        # Sin este limite, una pulsacion suelta se adjudicaba a la nota huerfana
        # mas cercana por lejos que estuviera: una nota que el alumno NUNCA toco
        # entraba en el informe como tocada y acertada con un desfase de 30 s, y
        # todo lo que se publique encima -porcentaje de acertadas, desfase medio,
        # regularidad- quedaba envenenado.
        self._ventanas_reclamo_s = np.maximum(
            np.array(
                [
                    pulsos_a_segundos(nota.duracion_pulsos, pieza.tempo) + ventana_a_tiempo_s
                    for nota in pieza.notas
                ],
                dtype=float,
            ),
            ventana_reclamo_minima_s,
        )
        # Las alturas escritas, para adjudicar por nombre y no solo por cercania.
        self._midis = np.array([nota.midi for nota in pieza.notas], dtype=int)
        self._duracion_s = pieza.duracion_s
        self._candado = threading.RLock()
        self.reiniciar()

    def reiniciar(self) -> None:
        """Vuelve al comienzo de la pieza y olvida lo tocado."""
        with self._candado:
            self._detector.reiniciar()
            self._instante_pieza = 0.0
            # Instante del reloj del analisis que corresponde a `_instante_pieza`.
            # None es "todavia sin fijar": lo fija el proximo cuadro.
            self._origen_analisis: float | None = None
            # Instante del reloj del analisis desde el que la correspondencia
            # actual es valida: el primer cuadro tras colocar el reloj a mano.
            # Un onset anterior se midio con otra correspondencia (ver `procesar`).
            self._analisis_desde: float | None = None
            self._tocadas: list[NotaTocada] = []
            self._cobradas = np.zeros(len(self._inicios_s), dtype=bool)

    @property
    def estado(self) -> EstadoCarril:
        """Instantanea COHERENTE del carril, construida entera bajo candado."""
        with self._candado:
            return EstadoCarril(
                instante_s=self._instante_pieza,
                indice_actual=self._indice_en_curso(self._instante_pieza),
                total=len(self.pieza),
                completado=self._instante_pieza >= self._duracion_s,
                tocadas=tuple(self._tocadas),
            )

    def avanzar_a(self, instante_s: float) -> EstadoCarril:
        """Mueve el reloj de la pieza a `instante_s`. No consume audio.

        Es la unica forma de mover el reloj sin señal, y por eso es tambien la que
        deja probar el carril sin esperas: las pruebas lo colocan a mano.

        Mover el reloj a mano invalida la correspondencia con el del analisis (el
        cabezal ya no esta donde el ultimo cuadro decia), asi que se vuelve a
        fijar en el proximo cuadro.

        Y invalida algo mas: las pulsaciones EN VUELO. El detector resuelve un
        onset hasta 250 ms despues de que ocurriera, con su instante en el reloj
        del analisis; si el reloj de la pieza salta entremedias, traducir ese
        onset con la correspondencia nueva lo coloca donde no paso nada. Con un
        salto a 3,0 s, una pulsacion tocada en el segundo 1,0 se adjudicaba a la
        nota 3 y "a tiempo". Por eso `_adjudicar` descarta los onsets anteriores
        al primer cuadro posterior a este salto: lo que se toco antes de la pausa
        pertenece al tramo que se acaba de abandonar.
        """
        with self._candado:
            self._instante_pieza = float(instante_s)
            self._origen_analisis = None
            self._analisis_desde = None
            return self.estado

    def procesar(self, resultado: ResultadoAnalisis, instante_analisis: float) -> EstadoCarril:
        """Consume un cuadro de analisis y devuelve el estado del carril.

        `instante_analisis` es del reloj del ANALISIS, no de la pieza. El cuadro
        mueve el reloj de la pieza a traves de la correspondencia entre ambos, y
        al detector se le pasa tal cual: sus esperas (la de estabilizacion, la
        racha estable) estan medidas en su propio reloj.
        """
        with self._candado:
            if self._origen_analisis is None:
                self._origen_analisis = instante_analisis - self._instante_pieza
                self._analisis_desde = instante_analisis
            self._instante_pieza = instante_analisis - self._origen_analisis
            pulsacion = self._detector.procesar(resultado, instante_analisis)
            if pulsacion is not None:
                self._adjudicar(pulsacion)
            return self.estado

    def _indice_en_curso(self, instante_s: float) -> int:
        """Indice de la nota que el reloj señala: la ultima que ya empezo.

        Antes de la primera nota señala a la primera (es la que hay que
        prepararse a tocar), y pasado el final se queda en la ultima; quien
        quiera saber si la pieza termino mira `completado`.

        Con un acorde -varias notas en el mismo instante- devuelve la ultima de
        ellas, que es una eleccion arbitraria entre iguales: este seguidor no
        sabe seguir acordes (ver la clase).
        """
        if len(self._inicios_s) == 0:
            return 0
        indice = int(np.searchsorted(self._inicios_s, instante_s, side="right")) - 1
        return max(0, indice)

    def _adjudicar(self, pulsacion: Pulsacion) -> None:
        """Anota una pulsacion contra la nota sin cobrar mas cercana en el tiempo.

        Cuando `pulsacion.instante` es None no se sabe cuando empezo la nota (ver
        `Pulsacion.instante`): se adjudica con el reloj de la pieza en este cuadro,
        que es lo unico que hay, pero no se publica desfase ni clasificacion,
        porque ese instante llega despues del ataque y el numero que saldria seria
        el retraso del detector disfrazado de retraso del alumno.

        Una pulsacion se DESCARTA, sin anotar nada y sin contar como fallo, en
        tres casos:

        1. Ninguna nota sin cobrar cae dentro de su ventana de reclamo
           (`_ventanas_reclamo_s`). Una pulsacion parasita -o una nota tocada
           muchisimo despues del final- no puede adjudicarse a una nota que el
           alumno nunca toco: eso la meteria en el informe como tocada, y encima
           acertada si coincidia la altura.
        2. La pieza entera esta ya cobrada.
        3. El onset es anterior al primer cuadro de la correspondencia actual, es
           decir, se toco antes del ultimo `avanzar_a` (ver su docstring).

        Descartar no es gratis, y se paga en el detector: el ya ha sellado esa nota
        como la ultima resuelta y ha gastado el instante del ataque antes de que
        aqui se decida nada.
        """
        if not self._cobradas.size or self._cobradas.all():
            return

        if pulsacion.instante is None:
            instante_onset: float | None = None
            instante_para_buscar = self._instante_pieza
        else:
            # `procesar` fija la correspondencia antes de llamar aqui, siempre. Si
            # faltara, el desfase saldria del tamaño de time.monotonic() y una
            # rama defensiva lo taparia en vez de delatarlo.
            assert self._origen_analisis is not None, "sin correspondencia entre relojes"
            if self._analisis_desde is not None and pulsacion.instante < self._analisis_desde:
                return
            instante_onset = pulsacion.instante - self._origen_analisis
            instante_para_buscar = instante_onset

        midi_tocado = midi_de_nombre(pulsacion.nota)
        distancias = np.abs(self._inicios_s - instante_para_buscar)
        reclamables = (~self._cobradas) & (distancias <= self._ventanas_reclamo_s)
        if not reclamables.any():
            return
        # La altura primero, la cercania despues. Cuando las notas van a 75 ms unas
        # de otras el tiempo no puede decir cual se quiso tocar, y el nombre de la
        # nota si: adjudicar solo por cercania mandaba una nota tocada 200 ms tarde
        # a la vecina de al lado, que salia "a_tiempo" y equivocada -un fantasma-
        # en vez de reconocer la nota real tocada tarde. Entre varias notas de la
        # misma altura gana la mas cercana. Si ninguna coincide, se cae a la mas
        # cercana en el tiempo: ahi es donde se anotan los fallos de altura, que
        # siguen saliendo con `acertada=False`.
        coincidentes = reclamables & (self._midis == midi_tocado)
        # Pero la altura DESEMPATA entre candidatas cercanas; no autoriza saltar
        # hacia delante por encima de una nota que esta debajo del dedo. Si hay
        # una nota sin cobrar a menos de `ventana_a_tiempo_s` de la pulsacion, la
        # coincidencia de altura solo puede estar en una nota que el alumno YA
        # haya alcanzado (su instante no queda mas alla de esa misma ventana).
        #
        # Sin este limite, las dos decisiones de rondas anteriores -la ventana de
        # reclamo derivada de la figura y la preferencia por altura- se juntaban
        # y se invertia el veredicto de dos notas: con la escala de C mayor a 80
        # ppm, un dedo un traste bajo sobre la nota 5 (F3, sonando E3) se
        # adjudicaba a la nota 6 (E3, a 750 ms, que el alumno aun no habia
        # alcanzado) y salia ACERTADA, la nota 5 se quedaba sin marca, y al tocar
        # la 6 bien la unica libre cerca era la 5, de otra altura, y salia
        # fallada. Lo correcto salia como error y el error como acierto.
        #
        # El caso que motivo la preferencia por altura sigue intacto, porque ahi
        # la nota de la altura buena esta DETRAS de la pulsacion: la semicorchea
        # a 200 ppm tocada 200 ms tarde se sigue adjudicando a ella y no a la
        # vecina que le cae a 20 ms.
        if (reclamables & (distancias <= self.ventana_a_tiempo_s)).any():
            alcanzadas = self._inicios_s <= instante_para_buscar + self.ventana_a_tiempo_s
            coincidentes = coincidentes & alcanzadas
        candidatas = coincidentes if coincidentes.any() else reclamables
        indice = int(np.argmin(np.where(candidatas, distancias, np.inf)))
        nota = self.pieza.notas[indice]
        self._cobradas[indice] = True

        if instante_onset is None:
            desfase: float | None = None
            clasificacion: str | None = None
        else:
            desfase = float(instante_onset - self._inicios_s[indice])
            clasificacion = self._clasificar(desfase)

        self._tocadas.append(
            NotaTocada(
                indice=indice,
                midi=midi_tocado,
                cents=pulsacion.cents,
                desfase_s=desfase,
                clasificacion=clasificacion,
                acertada=midi_tocado == nota.midi,
            )
        )

    def _clasificar(self, desfase_s: float) -> str:
        """"a_tiempo", "pronto" (negativo) o "tarde" segun la ventana."""
        if abs(desfase_s) <= self.ventana_a_tiempo_s:
            return "a_tiempo"
        return "pronto" if desfase_s < 0 else "tarde"
