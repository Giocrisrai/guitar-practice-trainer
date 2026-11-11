"""El cable falso: lo que el dispositivo simulado promete y cumple.

Estas pruebas NO son lentas. Todas usan un audio de juguete de unos 85 ms -ocho
bloques- en vez de una interpretacion de verdad, y lo que esperan se mide en
decenas de milisegundos. Las que cuestan segundos de reloj son las de
`tests/test_gemelo_sesion_completa.py`, que son otra cosa: ahi se mide la sesion
entera, aqui solo el cable.

El audio de juguete es una RAMPA de valores distintos y todos positivos, y las
dos cosas importan: distintos para que «las muestras llegan en orden» sea una
afirmacion falsable -con un audio constante, un stream que entregara los bloques
al reves pasaria la prueba-, y positivos para que el silencio del final se pueda
distinguir del audio por el valor y no solo por la posicion.
"""

import ast
import pathlib
import threading
import time

import numpy as np
import pytest

from nucleo.captura import CapturaAudio, buscar_rocksmith
from nucleo.gemelo import dispositivo as modulo_dispositivo
from nucleo.gemelo.dispositivo import (
    MARCAS_DEL_NOMBRE,
    NOMBRE_DEL_GEMELO,
    RecolectorDeLaSesion,
    StreamSimulado,
    dispositivo_simulado,
    esperar_la_cabecera,
)
from nucleo.gemelo.interprete import Interpretacion
from nucleo.gemelo.piezas_de_prueba import pieza_vacia

FS = 48000
TAMANO_BLOQUE = 512
BLOQUES_DE_AUDIO = 8
MUESTRAS_DE_AUDIO = BLOQUES_DE_AUDIO * TAMANO_BLOQUE

# Cuanto se le concede a una espera antes de darla por colgada. El audio de
# juguete entero son 85 ms, asi que un segundo es doce veces lo que cualquiera de
# estas pruebas necesita y a la vez lo bastante corto para que un fallo se note
# como un fallo y no como una suite que no acaba.
LIMITE_DE_ESPERA_S = 1.0

# Cuanto se pasa de largo la espera inyectada en
# `test_el_audio_no_se_ralentiza_cuando_las_esperas_se_pasan_de_largo`. El triple de
# lo que se le pide, que es mas de lo que macOS se pasa de verdad (`Event.wait` de
# 10,67 ms mide 12,98) y por tanto una prueba mas dura que la realidad.
VECES_QUE_SE_PASA_LA_ESPERA = 3.0

# Lo que el retraso del stream puede CRECER entre dos medidas separadas, en bloques.
#
# Sale de la espera inyectada y no de una medida en reposo: una espera que tarda el
# triple cubre tres periodos, asi que un lazo correcto puede estar hasta tres
# bloques por detras en un instante cualquiera, y entre dos instantes el retraso
# puede moverse esos tres mas uno de redondeo. Cuatro es esa cota.
#
# Medido, para que se vea que no es un colchon: el lazo bueno crece -1, +2 y 0 con
# cero, cuatro y ocho hilos quemando CPU; el lazo roto crece +17, +21 y +24. La
# tabla esta en el docstring de la prueba.
CRECIMIENTO_DEL_RETRASO_TOLERADO = 4


def _audio_de_juguete(muestras: int = MUESTRAS_DE_AUDIO) -> np.ndarray:
    """Una rampa de valores distintos y positivos. Ver la cabecera del modulo."""
    return np.linspace(0.1, 0.9, muestras, dtype=np.float32)


def _interpretacion(muestras: np.ndarray) -> Interpretacion:
    """Una `Interpretacion` armada a mano alrededor de unas muestras.

    Sin eventos y sin cabecera: lo que estas pruebas ejercitan es el cable, y el
    cable solo lee `muestras` y `frecuencia_muestreo`. Montarla con `interpretar`
    costaria sintetizar audio que nadie va a juzgar.
    """
    return Interpretacion(
        pieza=pieza_vacia(),
        muestras=muestras,
        eventos=(),
        frecuencia_muestreo=FS,
        duracion_s=muestras.size / FS,
        silencio_de_cabecera_s=0.0,
    )


def _captura_del_gemelo(
    interpretacion: Interpretacion, capacidad_buffer: int = 48000, **argumentos
) -> tuple[CapturaAudio, callable]:
    """Una `CapturaAudio` DE VERDAD enchufada al cable del gemelo, y su `listar`."""
    abrir_stream, listar = dispositivo_simulado(interpretacion, **argumentos)
    captura = CapturaAudio(
        indice_dispositivo=0,
        frecuencia_muestreo=FS,
        tamano_bloque=TAMANO_BLOQUE,
        capacidad_buffer=capacidad_buffer,
        abrir_stream=abrir_stream,
    )
    return captura, listar


def _esperar(condicion, limite_s: float = LIMITE_DE_ESPERA_S) -> bool:
    """Espera activa y corta hasta que `condicion` se cumpla."""
    final = time.monotonic() + limite_s
    while time.monotonic() < final:
        if condicion():
            return True
        time.sleep(0.001)
    return False


def test_el_dispositivo_se_anuncia_como_gemelo_y_como_rocksmith():
    """Las dos marcas del nombre, y las dos tienen un lector distinto.

    "Rocksmith" lo lee `buscar_rocksmith`, que es por donde la sesion encuentra el
    cable cuando el usuario no ha elegido nada -el caso normal-: sin esa marca, la
    sesion no abriria el gemelo y lo que se verificaria seria otro camino.
    "(gemelo)" lo lee el usuario en el diagnostico, que publica
    `Dispositivo activo: <nombre>`: sin esa marca, una sesion simulada se lee igual
    que una real.
    """
    _, listar = _captura_del_gemelo(_interpretacion(_audio_de_juguete()))

    dispositivos = listar()

    assert len(dispositivos) == 1, "el gemelo anuncia un dispositivo y solo uno"
    (dispositivo,) = dispositivos
    assert "Rocksmith" in dispositivo.nombre
    assert "(gemelo)" in dispositivo.nombre
    # Y no solo esta en el nombre: se encuentra por el mismo camino que el cable.
    assert buscar_rocksmith(dispositivos) == dispositivo
    assert dispositivo.canales_entrada == 1
    assert dispositivo.frecuencia_muestreo == float(FS)


@pytest.mark.parametrize(
    "nombre, marca_que_falta",
    [
        ("Interfaz de audio (gemelo)", "Rocksmith"),
        ("Rocksmith USB Guitar Adapter", "(gemelo)"),
        ("Cualquier otra cosa", "Rocksmith"),
    ],
)
def test_un_nombre_sin_las_dos_marcas_se_rechaza_nombrando_la_que_falta(
    nombre, marca_que_falta
):
    """El nombre a medida tambien pasa por la regla, y el mensaje dice que falta.

    Las dos marcas son el contrato del modulo, no un detalle del valor de fabrica:
    un nombre a medida que se olvidara una de las dos rompe una de las dos
    propiedades EN SILENCIO -la sesion no encuentra el cable, o el diagnostico no
    avisa de que es simulado-, y los dos sintomas son desconcertantes.
    """
    with pytest.raises(ValueError) as fallo:
        dispositivo_simulado(_interpretacion(_audio_de_juguete()), nombre=nombre)

    assert marca_que_falta in str(fallo.value)
    assert nombre in str(fallo.value), "el mensaje tiene que traer el nombre recibido"


def test_el_nombre_de_fabrica_lleva_las_dos_marcas():
    """Lo que el modulo trae puesto cumple su propia regla.

    Es una prueba de una linea y existe porque la regla se comprueba sobre el
    ARGUMENTO: si el valor de fabrica dejara de cumplirla, nadie se enteraria
    hasta que alguien construyera el dispositivo sin pasar nombre, que es
    justamente como se construye siempre.
    """
    assert all(marca in NOMBRE_DEL_GEMELO for marca in MARCAS_DEL_NOMBRE)


def test_el_stream_empuja_el_audio_en_bloques():
    """Las muestras de la interpretacion llegan al buffer, enteras y en orden.

    Se para la captura ANTES de leer, y no es comodidad: el stream sigue
    empujando silencio mientras esta vivo, asi que entre preguntar
    `total_capturado` y leer la ventana el buffer se habria movido y la
    comparacion hablaria de otra cosa.
    """
    audio = _audio_de_juguete()
    captura, _ = _captura_del_gemelo(_interpretacion(audio))

    assert captura.iniciar() is True
    try:
        assert _esperar(lambda: captura.total_capturado >= audio.size), (
            f"el stream no entrego las {audio.size} muestras del audio "
            f"en {LIMITE_DE_ESPERA_S} s"
        )
    finally:
        captura.detener()

    escrito = captura.total_capturado
    ventana = captura.leer_ventana(escrito)
    assert ventana is not None
    assert np.allclose(ventana[: audio.size], audio), (
        "las muestras no llegaron enteras y en orden"
    )
    assert np.all(ventana[audio.size :] == 0.0), "detras del audio solo va silencio"


def test_el_audio_entregado_no_va_por_delante_del_reloj():
    """El stream entrega tiempo real, y nunca de mas.

    Es la propiedad de la que cuelga la alineacion de la pasada: quien arranca la
    pasada espera a que el dispositivo haya entregado la cabecera tecnica del
    gemelo, asi que un stream que entregara el audio mas deprisa que el reloj
    pondria el cero del cabezal en el sitio equivocado.

    El suelo del 80% esta aqui por completitud y NO es el que vigila el
    ralentizado: en una maquina en reposo hasta un lazo roto entrega el 99% (ver
    `test_el_audio_no_se_ralentiza_cuando_las_esperas_se_pasan_de_largo`, que es la
    que lo vigila de verdad). Lo que esta prueba vigila es el TECHO: ni una
    muestra mas de las que caben en el tiempo transcurrido.
    """
    audio = _audio_de_juguete(muestras=FS)  # un segundo, para que la cuenta se vea
    captura, _ = _captura_del_gemelo(_interpretacion(audio))

    assert captura.iniciar() is True
    arranque = time.monotonic()
    try:
        time.sleep(0.3)
        entregadas = captura.total_capturado
        transcurrido = time.monotonic() - arranque
    finally:
        captura.detener()

    techo = transcurrido * FS
    assert entregadas <= techo, (
        f"entrego {entregadas} muestras en {transcurrido:.3f} s, que son mas de las "
        f"{techo:.0f} que caben en ese tiempo: el audio va por delante del reloj"
    )
    # El suelo se afloja hasta el 80% porque un arranque de hilo lento es normal;
    # lo que no es normal es el 60% que medimos con la espera por bloque.
    assert entregadas >= 0.8 * techo, (
        f"entrego {entregadas} muestras en {transcurrido:.3f} s y deberia haber "
        f"entregado cerca de {techo:.0f}: el audio va por detras del reloj"
    )


def test_el_audio_no_se_ralentiza_cuando_las_esperas_se_pasan_de_largo():
    """Aunque cada espera tarde el triple de lo pedido, el audio sigue al reloj.

    **ES LA PRUEBA QUE FALTABA, y la escribi porque dos mutantes sobrevivieron.**
    El defecto real que esta tarea encontro era el audio entregado al 60% de su
    velocidad, con la deriva creciendo nota a nota (medido: la ultima nota de una
    escala de 4,9 s llegaba 370 ms tarde). Pero las dos versiones rotas del lazo
    -una espera por bloque con reanclaje, y ponerse al dia durmiendo un periodo
    entero- pasaban la suite entera, porque en una maquina EN REPOSO
    `Event.wait(10,67 ms)` mide 12,98 ms y las dos entregan el 99% del audio. El
    defecto solo aparece bajo carga, y una prueba que intentara reproducir la carga
    estaria midiendo la maquina.

    Asi que la espera se inyecta y se hace tardar el triple a proposito. Con el
    lazo que se pone al dia, el audio sigue al reloj: lo que se pierde en una
    espera se recupera en la vuelta siguiente, igual que un dispositivo de verdad,
    cuyo reloj es el del hardware.

    **LO QUE SE AFIRMA ES QUE EL RETRASO NO CRECE, y no una fraccion del audio.**
    La primera version exigia `entregados >= 0,9 * debidos`, un suelo medido en
    reposo, y era INTERMITENTE: fallo una de cada cuatro pasadas de la suite en
    `e24935d` y otra en la octava de veinte de la ronda 3. La razon esta medida: con
    cuatro hilos quemando CPU el lazo BUENO entrega el 0,86 del audio -por debajo
    del 0,9- aunque no haya perdido ni un bloque de deuda, porque al hilo le robaron
    el turno. Un suelo fijo sobre una fraccion no distingue «el lazo pierde la
    deuda» de «el hilo se quedo sin CPU».

    Lo que si los distingue, y es lo que el lazo controla: **el lazo roto entrega
    una FRACCION del audio, asi que su retraso crece con el tiempo; un hilo sin CPU
    tiene un retraso acotado por lo que le robaron.** Medido, retraso en bloques
    entre t=0,2 s y t=0,6 s:

        carga     lazo bueno      lazo roto
          0       3 -> 2  (-1)    9 -> 26  (+17)
          4       6 -> 8  (+2)   14 -> 35  (+21)
          8       4 -> 4  ( 0)   18 -> 42  (+24)

    El crecimiento del lazo bueno no pasa de +2 con la maquina a ocho hilos de
    carga; el del roto no baja de +17. El techo inscrito es
    `CRECIMIENTO_DEL_RETRASO_TOLERADO`, y sale de la propia espera inyectada: ver su
    comentario.

    El techo de arriba (`entregados <= debidos + 1`) se queda tal cual: es exacto y
    no depende de la carga, porque el lazo no puede entregar mas audio del que cabe
    en el tiempo transcurrido.
    """
    esperas: list[float] = []

    def esperar_pasandose(segundos: float) -> bool:
        esperas.append(segundos)
        time.sleep(VECES_QUE_SE_PASA_LA_ESPERA * segundos)
        return False

    bloques: list[int] = []
    stream = StreamSimulado(
        lambda datos, cuadros, tiempo, estado: bloques.append(cuadros),
        _audio_de_juguete(muestras=FS),
        TAMANO_BLOQUE,
        FS,
        esperar=esperar_pasandose,
    )

    def retraso_ahora() -> tuple[float, int, int]:
        """El reloj, los bloques que ya deberia haber entregado y los que faltan."""
        transcurrido = time.monotonic() - arranque
        debidos = int(transcurrido / (TAMANO_BLOQUE / FS))
        return transcurrido, debidos, debidos - len(bloques)

    arranque = time.monotonic()
    stream.start()
    try:
        medidas = []
        for objetivo in (0.2, 0.6):
            while time.monotonic() - arranque < objetivo:
                time.sleep(0.005)
            medidas.append(retraso_ahora())
        transcurrido, debidos, _ = medidas[-1]
        entregados = len(bloques)
    finally:
        stream.stop()

    assert esperas, "la espera inyectada no se uso: el seam no esta enganchado"
    crecimiento = medidas[-1][2] - medidas[0][2]
    assert crecimiento <= CRECIMIENTO_DEL_RETRASO_TOLERADO, (
        f"con las esperas tardando {VECES_QUE_SE_PASA_LA_ESPERA:.0f} veces lo "
        f"pedido, el retraso del stream crecio de {medidas[0][2]} a {medidas[-1][2]} "
        f"bloques entre {medidas[0][0]:.2f} s y {medidas[-1][0]:.2f} s: el audio se "
        "esta ralentizando con el temporizador en vez de ponerse al dia"
    )
    assert entregados <= debidos + 1, (
        f"entrego {entregados} bloques y solo caben {debidos} en "
        f"{transcurrido:.3f} s"
    )


def test_al_acabarse_el_audio_sigue_empujando_silencio():
    """Agotado el audio, el cable sigue entregando: es un cable enchufado.

    `total_capturado` SIGUE creciendo y lo que llega es silencio. La decision y sus
    dos alternativas descartadas estan en la cabecera de
    `nucleo/gemelo/dispositivo.py`: sin esto, la sesion publica silencio a los
    0,5 s y pausa el carril a los 5 s, y las ultimas notas -que la cadena tarda
    ~190 ms en publicar- no llegan a cobrarse nunca.
    """
    audio = _audio_de_juguete()
    captura, _ = _captura_del_gemelo(_interpretacion(audio))
    cola = 3 * TAMANO_BLOQUE

    assert captura.iniciar() is True
    try:
        assert _esperar(lambda: captura.total_capturado >= audio.size + cola), (
            "el stream dejo de empujar al acabarse el audio"
        )
        detenido = captura.total_capturado
        assert _esperar(lambda: captura.total_capturado > detenido), (
            f"el stream se quedo clavado en {detenido} muestras"
        )
        ventana = captura.leer_ventana(cola)
    finally:
        captura.detener()

    assert ventana is not None
    assert np.all(ventana == 0.0), "lo que llega despues del audio tiene que ser silencio"


def test_el_dispositivo_no_desaparece_de_listar():
    """Agotado el audio, `listar` sigue devolviendolo.

    Es la otra mitad de la misma decision: el hilo de trabajo de la sesion cierra
    la captura EN CUANTO el dispositivo no esta en la lista, asi que un gemelo que
    se desenchufara al acabar el audio se llevaria por delante el final de la
    pasada.
    """
    audio = _audio_de_juguete()
    captura, listar = _captura_del_gemelo(_interpretacion(audio))

    assert captura.iniciar() is True
    try:
        assert _esperar(lambda: captura.total_capturado > audio.size + TAMANO_BLOQUE)
        dispositivos = listar()
    finally:
        captura.detener()

    assert len(dispositivos) == 1
    assert "(gemelo)" in dispositivos[0].nombre
    # Y sigue estando despues de cerrar el stream: `listar` es del dispositivo, no
    # de la captura.
    assert len(listar()) == 1


def test_el_stream_expone_latency():
    """`CapturaAudio.latencia_ms` no lanza y devuelve un numero plausible.

    Sin el atributo `latency` el diagnostico reventaba con `AttributeError` la
    primera vez que alguien pidiera la latencia del dispositivo, y eso es lo que
    pide la pantalla del afinador en cada sondeo. El valor es el audio que cabe en
    un bloque, que es de donde sale: 512 muestras a 48 kHz son 10,67 ms.
    """
    captura, _ = _captura_del_gemelo(_interpretacion(_audio_de_juguete()))

    assert captura.latencia_ms == 0.0, "sin stream abierto no hay latencia que dar"
    assert captura.iniciar() is True
    try:
        latencia = captura.latencia_ms
    finally:
        captura.detener()

    assert isinstance(latencia, float)
    assert latencia == pytest.approx(1000.0 * TAMANO_BLOQUE / FS)
    assert 0.0 < latencia < 50.0, "una latencia de entrada fuera de esto no es plausible"


def test_el_bloque_que_se_pide_manda_sobre_el_de_fabrica():
    """`CapturaAudio` pide un `blocksize` y el stream entrega ESE tamaño.

    Un dispositivo de verdad entrega los bloques del tamaño que se le pidio, y
    `CapturaAudio` pide siempre el suyo. El `tamano_bloque` de fabrica es para
    quien abra el stream sin pedir ninguno, y de ahi sale tambien la latencia
    declarada: si el stream se quedara con el de fabrica, la latencia hablaria de
    un bloque que nadie entrega.
    """
    interpretacion = _interpretacion(_audio_de_juguete())
    abrir_stream, _ = dispositivo_simulado(interpretacion, tamano_bloque=512)

    stream = abrir_stream(lambda *args: None, samplerate=FS, blocksize=256)
    sin_pedir = abrir_stream(lambda *args: None, samplerate=FS)

    assert stream.latency == pytest.approx(256 / FS)
    assert sin_pedir.latency == pytest.approx(512 / FS)


def test_una_frecuencia_que_no_es_la_del_audio_se_rechaza():
    """Entregar el audio a otra frecuencia seria recorrerlo a otra velocidad.

    No se adapta y no se reconvierte: el gemelo tiene el audio a una frecuencia y
    punto. Entregarlo igual haria que la pasada entera corriera mas deprisa o mas
    despacio que la musica, y el sintoma -todas las notas desplazandose- se parece
    demasiado a un defecto de la cadena.
    """
    abrir_stream, _ = dispositivo_simulado(_interpretacion(_audio_de_juguete()))

    with pytest.raises(ValueError) as fallo:
        abrir_stream(lambda *args: None, samplerate=44100)

    assert "44100" in str(fallo.value)
    assert str(FS) in str(fallo.value)


def test_parar_el_stream_deja_de_empujar():
    """`stop` para de verdad, y `close` y `stop` se pueden repetir sin romper nada.

    El hilo es un demonio, asi que un `stop` que no parara no se veria en la suite
    como un fallo: se veria como un hilo de mas empujando audio al buffer de una
    prueba que ya acabo.
    """
    bloques: list[int] = []
    candado = threading.Lock()

    def contar(datos, cuadros, tiempo, estado) -> None:
        with candado:
            bloques.append(cuadros)

    stream = StreamSimulado(contar, _audio_de_juguete(), TAMANO_BLOQUE, FS)
    stream.start()
    stream.start()  # idempotente, como el de verdad
    assert _esperar(lambda: len(bloques) >= 2), "el stream no empujo ni dos bloques"
    stream.stop()

    con_el_parado = len(bloques)
    time.sleep(5.0 * TAMANO_BLOQUE / FS)
    assert len(bloques) == con_el_parado, "el stream siguio empujando tras pararlo"

    stream.stop()
    stream.close()
    stream.close()
    assert all(cuadros == TAMANO_BLOQUE for cuadros in bloques)


def test_un_bloque_o_una_frecuencia_imposibles_se_rechazan():
    """Ni cero muestras por bloque ni cero muestras por segundo.

    Las dos dividen: el periodo del lazo es `tamano_bloque / frecuencia`, asi que
    un cero cuelga el hilo o lo revienta, y lo haria DENTRO de un hilo demonio,
    donde la traza no llega a ninguna parte.
    """
    with pytest.raises(ValueError):
        StreamSimulado(lambda *args: None, _audio_de_juguete(), 0, FS)
    with pytest.raises(ValueError):
        StreamSimulado(lambda *args: None, _audio_de_juguete(), TAMANO_BLOQUE, 0)


def test_esperar_la_cabecera_no_se_cuelga_sin_dispositivo():
    """Sin audio que llegue, la espera se agota y lo DICE en vez de seguir.

    Quien arranca la pasada tiene que poder distinguir «el cable entrego la
    cabecera» de «no llego nada»: arrancar la pasada contra un dispositivo que no
    entrega es una pasada que se falla entera sin que nadie sepa por que.
    """

    class CapturaMuerta:
        total_capturado = 0

    interpretacion = _interpretacion(_audio_de_juguete())

    assert esperar_la_cabecera(CapturaMuerta(), interpretacion, 4096, limite_s=0.05) is False


def test_esperar_la_cabecera_vuelve_cuando_el_audio_llego():
    """Y con el cable entregando, vuelve en cuanto la cabecera esta dentro."""
    audio = _audio_de_juguete(muestras=FS)
    captura, _ = _captura_del_gemelo(_interpretacion(audio))

    assert captura.iniciar() is True
    try:
        llego = esperar_la_cabecera(captura, _interpretacion(audio), 4096, limite_s=1.0)
        entregadas = captura.total_capturado
    finally:
        captura.detener()

    assert llego is True
    # La cabecera de esta interpretacion armada a mano es el suelo de una ventana.
    assert entregadas >= 4096


def test_el_recolector_no_cuenta_dos_veces_la_misma_nota():
    """Lo que se publica treinta veces por segundo se recoge UNA.

    El estado publicado repite las notas ya anotadas en cada paquete, asi que un
    recolector que no deduplicara contaria cada nota tantas veces como se la
    publicaran y el veredicto saldria con cientos de notas inventadas.
    """
    recolector = RecolectorDeLaSesion()
    nota = {
        "indice": 0,
        "midi": 55,
        "nombre": "G3",
        "cents": 1.0,
        "desfase_s": 0.01,
        "clasificacion": "a_tiempo",
        "acertada": True,
        "afinada": True,
    }

    for _ in range(5):
        recolector.recoger({"repeticion": 1, "instante_s": 0.5, "tocadas": [nota]})

    assert len(recolector.registro.reportes) == 1
    assert recolector.registro.reportes[0].tocada.indice == 0
    assert recolector.registro.reportes[0].instante_pasada_s == 0.5
    # Lo que el estado publicado no trae no se inventa.
    assert recolector.registro.vueltas == ()
    assert recolector.registro.estado_final is None


def test_el_recolector_separa_las_vueltas():
    """La misma nota en dos vueltas son dos reportes, no uno repetido.

    Los indices se repiten vuelta a vuelta: «la nota 2» de la vuelta 1 y la de la
    vuelta 2 son dos cosas distintas, y un recolector que las confundiera haria
    desaparecer una vuelta entera del veredicto de un bucle.
    """
    recolector = RecolectorDeLaSesion()
    nota = {
        "indice": 2,
        "midi": 59,
        "nombre": "B3",
        "cents": 0.0,
        "desfase_s": 0.0,
        "clasificacion": "a_tiempo",
        "acertada": True,
        "afinada": True,
    }

    recolector.recoger({"repeticion": 1, "instante_s": 1.2, "tocadas": [nota]})
    recolector.recoger({"repeticion": 2, "instante_s": 0.3, "tocadas": [nota]})

    reportes = recolector.registro.reportes
    assert [reporte.repeticion for reporte in reportes] == [1, 2]
    assert [reporte.instante_pasada_s for reporte in reportes] == [1.2, 0.3]


def test_ninguna_prueba_abre_el_dispositivo_real():
    """El modulo del gemelo no importa `sounddevice`, ni directa ni indirectamente.

    Se lee con `ast` y no con un `in` sobre el texto, porque este mismo docstring
    nombra la biblioteca y un `in` lo contaria como un import. Lo que se comprueba
    es que ningun `import` del modulo la nombra: si lo hiciera, la primera prueba
    que construyera un dispositivo simulado abriria CoreAudio, y en una maquina sin
    permiso de microfono la suite se volveria roja por algo que no tiene nada que
    ver con lo que mide.
    """
    fuente = pathlib.Path(modulo_dispositivo.__file__).read_text(encoding="utf-8")
    importados: set[str] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Import):
            importados.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])

    assert "sounddevice" not in importados, (
        f"el cable del gemelo no puede tocar el audio real; importa {sorted(importados)}"
    )
