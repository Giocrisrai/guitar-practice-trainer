"""El cable falso: un dispositivo de audio que entrega lo que el gemelo toco.

La cadena directa (`nucleo.gemelo.cadena`) recorre el audio del gemelo en tiempo
VIRTUAL: el reloj sale de las muestras y nueve segundos de audio se recorren en
menos de uno de pared. Eso es lo que le permite correr en cada suite, y es
tambien lo unico que no puede verificar: los hilos, el buffer circular, el reloj
de pared de la pasada y la cadencia con la que el hilo de analisis mira el
dispositivo son codigo de produccion que la cadena directa NO ejecuta.

Este modulo cierra ese hueco por el otro lado: en vez de recorrer el audio a
mano, lo mete por donde entra el audio de verdad. `dispositivo_simulado` devuelve
los dos cierres que `CapturaAudio` y `Sesion` admiten como seams -`abrir_stream`
y `listar`-, y con ellos la sesion ENTERA corre sin tocar el dispositivo real:
`CapturaAudio` con su buffer circular, el hilo de trabajo de `Sesion`, el
`Analizador`, el `SesionCarril` y el `ConductorDeEstudio`. Lo unico simulado es el
cable.

El precio es el reloj: aqui se paga tiempo de pared, segundo por segundo, porque
es justo el reloj de pared lo que se quiere verificar. De ahi que las pruebas de
este camino vayan marcadas `slow` y sean pocas y cortas.

**EL NOMBRE DICE LAS DOS COSAS.** Lleva "Rocksmith" para que `buscar_rocksmith` lo
encuentre por el mismo camino que el cable de verdad -si se llamara de otra forma,
la sesion no lo abriria y lo que se verificaria seria el camino de "elegido a
mano", que no es el normal- y lleva "(gemelo)" para que nadie confunda una sesion
simulada con una real: el diagnostico publica `Dispositivo activo: <nombre>`, asi
que con este nombre el estado "ok" dice en voz alta que esta hablando con el
gemelo. Las dos marcas se COMPRUEBAN sobre el nombre que se pide, y no solo sobre
el de fabrica: un nombre a medida que se olvidara una de las dos romperia una de
las dos propiedades en silencio.

**AGOTADO EL AUDIO, EL STREAM SIGUE EMPUJANDO SILENCIO INDEFINIDAMENTE Y EL
DISPOSITIVO NUNCA DESAPARECE DE `listar`.** Es una decision tomada, no una
omision, y es lo que hace un cable enchufado a una guitarra que nadie toca. Es
ademas el unico camino en que las ultimas notas llegan a cobrarse, porque la
cadena tarda en publicar un ataque (~185 ms medidos en
`tests/test_gemelo_oraculo.py`) y las dos alternativas lo impiden:

* Si el stream dejara de empujar bloques, `total_capturado` se quedaria quieto y
  a los `TIEMPO_SIN_MUESTRAS_SILENCIO` (0,5 s) la sesion publicaria silencio y
  dejaria de analizar; a los `SEGUNDOS_SIN_SENAL` (5 s) el carril se pausaria por
  falta de señal y el cabezal se quedaria clavado.
* Si el dispositivo desapareciera de `listar`, el hilo de trabajo cierra la
  captura **de inmediato** en su siguiente revision (`_dispositivo_sigue_presente`)
  y publica silencio, asi que el final de la pasada se perderia entero.

Quien conduzca este dispositivo es quien decide cuando se acabo: mirando el estado
publicado (`completado`), que es lo que mira el navegador, y no el final del
audio.

**Y LA PASADA NO SE ARRANCA AL ABRIR EL STREAM, SINO UNA CABECERA TECNICA
DESPUES.** La cadena directa pone el cabezal a cero en el final de la cabecera
tecnica del gemelo DESPLAZANDO un eje; aqui no hay eje que desplazar, porque el
cabezal de la sesion completa lo mueve el reloj de pared. Lo que se hace es
esperar: el stream entrega en tiempo real, asi que esperar
`desplazamiento_del_cabezal_s` en el reloj es esperar ese mismo audio en muestras,
con el error de un bloque (10,67 ms). Quien arranque la pasada antes le estaria
cobrando al guitarrista sintetico un silencio que es un requisito del gemelo y no
tiempo musical -128 ms de retraso en TODAS las notas-, y el veredicto, que
descuenta esa cabecera porque supone que el cabezal no corrio durante ella, la
contaria dos veces.
"""

import threading
import time
from typing import Callable

import numpy as np

from nucleo.captura import DispositivoAudio
from nucleo.gemelo.cadena import (  # noqa: F401  (reexportado a proposito)
    RegistroDeLaCadena,
    ReporteDeLaCadena,
    desplazamiento_del_cabezal_s,
)
from nucleo.gemelo.interprete import Interpretacion
from nucleo.piezas.seguimiento import NotaTocada

# El nombre con el que el gemelo se anuncia al sistema. Las dos marcas que lleva
# -y por que las lleva- estan en la cabecera del modulo.
NOMBRE_DEL_GEMELO = "Rocksmith USB Guitar Adapter (gemelo)"

# Las dos marcas que el nombre de un dispositivo del gemelo tiene que llevar.
MARCAS_DEL_NOMBRE = ("Rocksmith", "(gemelo)")

# El indice con el que se anuncia. Es 0 y da igual que lo sea: `listar` devuelve
# SOLO este dispositivo, asi que no hay ningun otro con el que chocar, y la sesion
# lo busca por nombre y no por indice (`Sesion._indice_objetivo`).
INDICE_DEL_GEMELO = 0

# Lo que el callback de audio recibe en el parametro `estado`. Un entero cero
# porque `CapturaAudio._callback` solo pregunta `if estado:` -cuenta un desborde
# cuando es verdadero-, y el gemelo no pierde muestras: empuja un bloque, el
# buffer lo copia y no hay tarjeta de sonido que se quede atras. `sounddevice`
# entrega ahi un `CallbackFlags`, que tambien es falso cuando no hay avisos.
SIN_AVISOS = 0


class StreamSimulado:
    """Un hilo con reloj de pared que empuja la interpretacion bloque a bloque.

    Imita de `sounddevice.InputStream` lo que `CapturaAudio` usa de verdad y nada
    mas: `latency`, `start`, `stop` y `close`, y un callback con la firma
    `(datos, cuadros, tiempo, estado)` donde `datos` es un array de dos
    dimensiones `(cuadros, 1)` en `float32`, que es lo que
    `CapturaAudio._callback` indexa con `datos[:, 0]`.

    `latency` NO es decorativo: `CapturaAudio.latencia_ms` lo lee y lo multiplica
    por mil, asi que un stream sin ese atributo revienta el diagnostico la primera
    vez que alguien pida la latencia del dispositivo. El valor que declara es
    `tamano_bloque / frecuencia_muestreo`, o sea 10,67 ms con los 512 bloques de
    fabrica a 48 kHz: plausible porque es el orden de magnitud de lo que reporta
    una tarjeta de verdad, y DERIVADO en vez de inventado porque es exactamente
    cuanto audio hay en el bloque que el callback acaba de recibir. Un numero
    suelto aqui se desacoplaria del tamaño de bloque el dia que alguien lo cambie.

    EL BLOQUE DE SILENCIO SE REUTILIZA, igual que `sounddevice` reutiliza su
    propio buffer: quien reciba el callback tiene que copiar lo que le dan, que es
    lo que `BufferCircular.escribir` hace.

    `esperar` es el seam de la espera entre bloques, y lo que existe para poder
    probar esta mal: ver el comentario de `self._esperar`.
    """

    def __init__(
        self,
        callback: Callable,
        muestras: np.ndarray,
        tamano_bloque: int,
        frecuencia_muestreo: int,
        esperar: Callable[[float], object] | None = None,
    ) -> None:
        if tamano_bloque < 1:
            raise ValueError(
                f"El tamaño de bloque {tamano_bloque} no sirve: "
                "tiene que ser de al menos una muestra"
            )
        if frecuencia_muestreo < 1:
            raise ValueError(
                f"La frecuencia {frecuencia_muestreo} Hz no sirve: "
                "tiene que ser positiva"
            )
        self._callback = callback
        self._muestras = np.asarray(muestras, dtype=np.float32)
        self._tamano_bloque = tamano_bloque
        self._frecuencia_muestreo = frecuencia_muestreo
        self.latency = tamano_bloque / frecuencia_muestreo
        self._silencio = np.zeros((tamano_bloque, 1), dtype=np.float32)
        self._entregadas = 0
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        # El seam de la ESPERA, y hace falta uno. Lo que el lazo de abajo protege
        # es que el audio siga el reloj aunque cada espera se pase de largo, y eso
        # no se puede comprobar sin un temporizador que se pase de largo: en una
        # maquina en reposo `Event.wait(10,67 ms)` mide 12,98 ms y hasta un lazo
        # roto entrega el 99% del audio. Bajo carga -el hilo del analisis
        # publicando y el hilo HTTP leyendo el estado- es cuando se pasa de verdad,
        # y una prueba que dependiera de reproducir esa carga mediria la maquina.
        # Inyectando la espera, la prueba reproduce un temporizador lento en una
        # linea. Es el mismo reparto que el `reloj` de `SesionCarril`, que tambien
        # se inyecta para que las pruebas lo muevan a mano.
        self._esperar = self._parar.wait if esperar is None else esperar

    # No hay `muestras_entregadas` ni `audio_agotado`, y estuvieron: quien
    # necesita saber cuanto audio ha entrado mira `CapturaAudio.total_capturado`,
    # que es el contador de PRODUCCION y el que `esperar_la_cabecera` usa. Un
    # segundo contador aqui no lo leia nadie, asi que ninguna prueba podia
    # falsearlo: habria sido codigo que parece vigilado y no lo esta.

    def start(self) -> None:
        """Arranca el hilo que empuja los bloques. Idempotente, como el de verdad."""
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._parar.clear()
        self._hilo = threading.Thread(target=self._empujar, daemon=True)
        self._hilo.start()

    def stop(self) -> None:
        """Para el hilo y espera a que salga. Seguro de llamar varias veces.

        La espera tiene techo: el hilo no hace E/S y sale en cuanto mira el
        evento, pero un `join` sin limite en el camino de cierre de un dispositivo
        es la clase de linea que cuelga un servidor entero. El techo son dos
        periodos de bloque, que es mas de lo que el hilo puede tardar.
        """
        self._parar.set()
        hilo, self._hilo = self._hilo, None
        if hilo is not None:
            hilo.join(timeout=2.0 * self._tamano_bloque / self._frecuencia_muestreo + 0.5)

    def close(self) -> None:
        """Cierra el stream. Para el hilo si hacia falta, como `InputStream.close`."""
        self.stop()

    def _empujar(self) -> None:
        """Un bloque cada `tamano_bloque / fs` segundos, con reloj de pared.

        CUANTOS BLOQUES VAN NO LO DECIDE LA ESPERA, LO DECIDE EL RELOJ, y esto
        esta MEDIDO: `Event.wait(0,021)` tarda 27 ms en este equipo, porque macOS
        agrupa los temporizadores y no despierta a un hilo con la puntualidad que
        se le pide. Con bloques de 10,67 ms eso significa que una espera por
        bloque entrega la mitad del audio que deberia, y un lazo que ademas
        reanclase el plazo en el presente tras cada retraso perderia la deuda en
        cada vuelta: el audio sonaria al 60% de su velocidad sin que nada se
        quejara. Medido antes de arreglarlo: la ultima nota de una escala de 4,9 s
        llegaba 370 ms tarde, con la deriva creciendo nota a nota, y la pasada se
        completaba -el cabezal va con el reloj de pared- antes de que sonara.

        Asi que cada vuelta empuja TODOS los bloques que el reloj ya debe, no uno:
        `entregados` se compara con `(ahora - inicio) / periodo` y el lazo se pone
        al dia. Es lo que hace un dispositivo de verdad, y por la misma razon: su
        reloj es el del hardware y no se desvia, de modo que el sistema operativo
        llegando tarde a la cita no ralentiza el audio, solo lo entrega a rachas.

        EL PRIMER BLOQUE TAMBIEN SE ESPERA, y tampoco es un detalle: un
        dispositivo de verdad entrega el primer bloque cuando lo ha CAPTURADO, o
        sea un periodo despues de arrancar, no en el mismo instante. De ahi que la
        cuenta use `int(...)` y no `int(...) + 1`: en el instante cero no hay
        ningun bloque capturado todavia, y el audio entregado va asi medio bloque
        POR DETRAS del reloj de pared, que es lo mismo que la ventana de analisis
        lleva de retraso respecto al presente.

        Una parada larga del proceso (una recoleccion de basura gorda, la maquina
        dormida) se recupera empujando los bloques debidos de seguido, sin tirar
        ninguno. El buffer circular puede sobrescribir lo que nadie analizo
        todavia, que es exactamente el desborde que reporta una tarjeta de verdad
        cuando el consumidor no llega: el gemelo no inventa un camino distinto
        para eso.
        """
        periodo = self._tamano_bloque / self._frecuencia_muestreo
        inicio = time.monotonic()
        entregados = 0
        while not self._parar.is_set():
            debidos = int((time.monotonic() - inicio) / periodo)
            while entregados < debidos:
                self._callback(
                    self._siguiente_bloque(), self._tamano_bloque, None, SIN_AVISOS
                )
                entregados += 1
                if self._parar.is_set():
                    return
            espera = inicio + (entregados + 1) * periodo - time.monotonic()
            if espera > 0.0:
                self._esperar(espera)

    def _siguiente_bloque(self) -> np.ndarray:
        """El bloque que toca, y silencio para siempre cuando el audio se acaba.

        El ultimo bloque de la interpretacion casi nunca cae justo: lo que falta
        se rellena con ceros, que es lo que hay detras de la ultima nota.
        """
        desde = self._entregadas
        if desde >= self._muestras.size:
            return self._silencio
        self._entregadas = desde + self._tamano_bloque
        trozo = self._muestras[desde : desde + self._tamano_bloque]
        if trozo.size == self._tamano_bloque:
            return trozo.reshape(-1, 1)
        bloque = np.zeros((self._tamano_bloque, 1), dtype=np.float32)
        bloque[: trozo.size, 0] = trozo
        return bloque


def _con_el_ambiente(
    muestras: np.ndarray, audio_ambiente: np.ndarray | None
) -> np.ndarray:
    """Lo que el cable entrega: lo que el gemelo toco mas lo que suena alrededor.

    **ES EL CAMINO QUE HACE MEDIBLE EL ANTI-OBJETIVO DE LA ETAPA 3e.** Con un
    microfono abierto, lo que sale por los altavoces -la pieza de fondo- vuelve a
    entrar por la entrada, el detector de ataques lo cobra como notas del usuario
    y el informe se llena de aciertos y fallos que no toco nadie. Hasta que esto
    existio, la entrada del gemelo y la salida del acompanamiento eran dos streams
    sin ningun camino entre ellos, de modo que ninguna prueba podia reproducir esa
    realimentacion ni queriendo. Quien la mide es
    `tests/test_gemelo_realimentacion.py`.

    `None` -el valor por omision- devuelve **el mismo array**, sin copiarlo y sin
    tocar ni una muestra: es lo que corre en todas las demas pruebas del gemelo y
    en `herramientas/gemelo.py`, y que no cambie esta comprobado con
    `np.array_equal` contra la verdad del interprete.

    **EL RESULTADO ES TAN LARGO COMO EL MAS LARGO DE LOS DOS**, y no se recorta al
    audio del gemelo: el microfono sigue oyendo el fondo despues de que el alumno
    haya tocado su ultima nota, y la cola del fondo es justo donde la cadena no
    tiene ni una nota de verdad con la que confundirse. Recortarla seria quitarle
    al montaje su caso mas limpio.

    **Y NO SE RECORTA A [-1, 1].** El cable entrega lo que le dan: quien pida una
    suma que se sale de la escala tiene un problema de niveles, y un recorte
    silencioso aqui lo taparia distorsionando el audio en vez de dejarlo ver.
    """
    if audio_ambiente is None:
        return muestras
    ambiente = np.asarray(audio_ambiente, dtype=np.float32)
    if ambiente.ndim != 1:
        raise ValueError(
            f"El audio ambiente tiene {ambiente.ndim} dimensiones: el cable "
            "entrega un solo canal, asi que tiene que ser mono"
        )
    suma = np.zeros(max(muestras.size, ambiente.size), dtype=np.float32)
    suma[: muestras.size] = muestras
    suma[: ambiente.size] += ambiente
    return suma


def dispositivo_simulado(
    interpretacion: Interpretacion,
    tamano_bloque: int = 512,
    nombre: str = NOMBRE_DEL_GEMELO,
    audio_ambiente: np.ndarray | None = None,
) -> tuple[Callable, Callable]:
    """Los dos cierres con los que la sesion entera toca lo que el gemelo toco.

    Devuelve `(abrir_stream, listar)`:

    * `abrir_stream` es el seam de `CapturaAudio`: se le llama con el callback y
      los mismos argumentos con que se abriria un `InputStream` de verdad
      (`device`, `channels`, `samplerate`, `blocksize`, `dtype`). `device`,
      `channels` y `dtype` se ignoran a proposito -el gemelo entrega un solo canal
      en `float32` y no hay mas de un dispositivo-, pero `samplerate` NO: una
      frecuencia distinta de la de la interpretacion recorreria el audio a otra
      velocidad, asi que se rechaza en vez de mentir.
    * `listar` es el seam de `Sesion`: devuelve SIEMPRE una lista con el
      dispositivo del gemelo, tambien despues de que el audio se acabe (ver la
      cabecera del modulo).

    `tamano_bloque` es el que se usa cuando quien abre no pide ninguno; cuando
    pide uno (`blocksize`), manda el suyo, porque un stream de verdad entrega los
    bloques del tamaño que se le pidio y `CapturaAudio` pasa siempre el que lleva.

    `audio_ambiente` es lo que suena en la habitacion y el microfono recoge: se
    SUMA a lo que el gemelo toco, que es la unica forma de reproducir el
    anti-objetivo de la etapa 3e. Ver `_con_el_ambiente`, que es donde esta
    escrito lo que la suma promete; con `None` el cable entrega exactamente lo
    mismo que entregaba antes de que este parametro existiera.

    Lanza `ValueError` si el nombre no lleva las dos marcas obligatorias o si el
    audio ambiente no es mono.
    """
    faltan = [marca for marca in MARCAS_DEL_NOMBRE if marca not in nombre]
    if faltan:
        raise ValueError(
            f"El nombre '{nombre}' no sirve para el dispositivo del gemelo: "
            f"le falta {' y '.join(faltan)}. Hace falta 'Rocksmith' para que "
            "`buscar_rocksmith` lo encuentre y '(gemelo)' para que nadie confunda "
            "una sesion simulada con una real"
        )
    frecuencia = interpretacion.frecuencia_muestreo
    # La mezcla se hace UNA vez y no en cada apertura: `abrir_stream` puede
    # llamarse varias veces -la sesion reabre la captura cuando el dispositivo
    # cambia- y las dos aperturas tienen que entregar lo mismo.
    entregable = _con_el_ambiente(interpretacion.muestras, audio_ambiente)

    def listar() -> list[DispositivoAudio]:
        return [
            DispositivoAudio(
                indice=INDICE_DEL_GEMELO,
                nombre=nombre,
                canales_entrada=1,
                frecuencia_muestreo=float(frecuencia),
            )
        ]

    def abrir_stream(callback: Callable, **argumentos) -> StreamSimulado:
        pedida = argumentos.get("samplerate", frecuencia)
        if pedida is not None and int(pedida) != frecuencia:
            raise ValueError(
                f"El gemelo tiene el audio a {frecuencia} Hz y se le piden "
                f"{int(pedida)} Hz: entregarlo igual lo recorreria a otra "
                "velocidad"
            )
        bloque = argumentos.get("blocksize") or tamano_bloque
        return StreamSimulado(callback, entregable, int(bloque), frecuencia)

    return abrir_stream, listar


def esperar_la_cabecera(
    captura, interpretacion: Interpretacion, tamano_ventana: int, limite_s: float = 5.0
) -> bool:
    """Espera a que el dispositivo haya entregado la cabecera tecnica del gemelo.

    Es el momento en que hay que arrancar la pasada, y por que esta en la cabecera
    del modulo. Devuelve False si se agota `limite_s` sin llegar, que es lo que
    pasa cuando el dispositivo no se abrio: quien llama tiene que decirlo en vez de
    arrancar una pasada contra un cable que no entrega nada.

    `captura` es cualquier cosa con `total_capturado` -en produccion una
    `CapturaAudio`-, y se mira ESE contador y no el reloj. Dormir la cabecera en el
    reloj parecia equivalente y no lo es: entre abrir el stream y el primer bloque
    hay un hilo que arrancar y los imports perezosos del analizador, y medido asi
    la pasada arrancaba hasta 350 ms antes de que el audio llegase a su sitio.
    Trescientos cincuenta milisegundos de desalineacion no son ruido: se comen la
    ventana de altura del seguidor (250 ms) y la pasada entera se adjudica corrida
    una nota, que es como se ve este fallo desde fuera.

    `tamano_ventana` es la del analizador que va a recorrer el audio
    (`PERFILES[pieza.perfil].tamano_ventana(fs)`), porque de ella sale el suelo del
    desplazamiento.
    """
    objetivo = (
        desplazamiento_del_cabezal_s(interpretacion, tamano_ventana)
        * interpretacion.frecuencia_muestreo
    )
    limite = time.monotonic() + limite_s
    while time.monotonic() < limite:
        if captura.total_capturado >= objetivo:
            return True
        time.sleep(0.001)
    return False


class RecolectorDeLaSesion:
    """Recoge en un `RegistroDeLaCadena` lo que la sesion completa PUBLICA.

    Es el equivalente del `_recoger` de la cadena directa para el otro camino, y
    recoge de otro sitio porque en la sesion completa no hay de donde recoger lo
    mismo: ahi el conductor lo mueve el hilo de analisis y los `EstadoEstudio` que
    devuelve no los ve nadie mas. Lo que si se puede mirar es el estado
    PUBLICADO -el diccionario de `SesionCarril.estado()`, que es exactamente lo que
    sale por `/api/piezas/estado` y lo que lee el navegador-, asi que es de ahi de
    donde se recoge, y con eso el escaparate puede recoger por HTTP sin ninguna
    pieza aparte.

    Se compara por VALOR y por vuelta, igual que en la cadena directa: el seguidor
    puede tirar lo que lleva anotado -`_tocadas` se poda en `olvidar_tramo`, al que
    se llega por la vuelta de un bucle, por `saltar_al_compas` o por
    `cambiar_plan`-, asi que la lista no solo crece y contar cuantas van no basta.
    Los indices se repiten vuelta a vuelta, de modo que la nota 2 de la vuelta 3 es
    un reporte distinto de la nota 2 de la vuelta 1.

    **POR QUE HAY QUE RECOGER DEPRISA, Y NO ES POR PERDER NOTAS.** En una pasada
    DERECHA -sin bucle y sin que el usuario salte, que es como corre el escaparate-
    no se poda nada: una nota publicada sigue publicada hasta el final, y leer
    despacio no pierde ninguna. Lo que se estropea es el INSTANTE: aqui se anota
    `instante_pasada_s` de la PRIMERA lectura en que la nota se ve, asi que cada
    lectura que se tarda en mirar se le suma al desfase que el veredicto publica.
    Medido sobre la pieza de demostracion leyendo a 5 Hz: las 48 notas se recogen
    igual, pero la mediana del desfase sube de +181,9 a +226,1 ms y aparecen 37
    perdidas por emparejamiento, porque los reportes se salen de los 250 ms que el
    detector admite. O sea: leer despacio no pierde reportes, los ENVEJECE, y el
    veredicto se lo cobra a la cadena.

    Perder notas de verdad solo pasa por los dos caminos que si podan -un bucle o
    una accion del usuario- y leyendo mas despacio que ellos.
    """

    def __init__(self) -> None:
        self._vistas: dict[int, set[NotaTocada]] = {}
        self._reportes: list[ReporteDeLaCadena] = []

    def recoger(self, estado: dict) -> None:
        """Anota las notas de este estado publicado que no se hubieran visto ya."""
        repeticion = int(estado["repeticion"])
        instante = float(estado["instante_s"])
        ya = self._vistas.setdefault(repeticion, set())
        for publicada in estado["tocadas"]:
            tocada = _tocada_desde(publicada)
            if tocada in ya:
                continue
            ya.add(tocada)
            self._reportes.append(
                ReporteDeLaCadena(
                    repeticion=repeticion, tocada=tocada, instante_pasada_s=instante
                )
            )

    @property
    def registro(self) -> RegistroDeLaCadena:
        """Lo recogido hasta ahora, listo para `juzgar`.

        Sin `vueltas` ni `estado_final`: los informes de las vueltas cerradas no
        viajan en el estado publicado -el servidor los sirve aparte, por
        `/api/piezas/informe`- y el estado final es un objeto del nucleo que un
        diccionario no reconstruye. `juzgar` no lee ninguno de los dos.
        """
        return RegistroDeLaCadena(reportes=tuple(self._reportes))


def _tocada_desde(publicada: dict) -> NotaTocada:
    """Rehace una `NotaTocada` del diccionario con que se publico.

    `a_dict` añade `nombre` -el nombre de la nota, que se deriva del midi- y
    redondea `cents` y `desfase_s`; nada de eso se deshace aqui, y no hace falta:
    el veredicto solo mira `indice` y `midi`, y el redondeo es determinista, asi
    que dos lecturas de la misma nota siguen siendo iguales y la comparacion por
    valor sigue valiendo.
    """
    return NotaTocada(
        indice=publicada["indice"],
        midi=publicada["midi"],
        cents=publicada["cents"],
        desfase_s=publicada["desfase_s"],
        clasificacion=publicada["clasificacion"],
        acertada=publicada["acertada"],
        afinada=publicada["afinada"],
    )
