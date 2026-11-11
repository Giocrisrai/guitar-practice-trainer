"""El acompañante, el hilo que hace sonar la pieza de fondo sin reloj propio.

La decision que gobierna el modulo -y por tanto estas pruebas- es que el
acompañante NO lleva reloj: en cada bloque pregunta el cabezal del carril,
calcula la rodaja y la escribe. No acumula posicion, no cuenta bloques, no
interpola. Cualquier reloj propio DERIVA del carril, que ya sabe de bucles,
cuenta atras, saltos de compas, pausa por falta de señal y factor de tempo; un
segundo reloj seria un segundo sitio donde el bucle puede equivocarse.

**Ni una asercion toma su valor de referencia del camino que prueba.** El
instante de muestra se calcula aqui a mano -de `tempo`, `factor_tempo` y
`frecuencia_muestreo`, con `_muestra_del_pulso`- y NUNCA llamando a
`PiezaRenderizada.rodaja`, que es justo lo que el acompañante usa. Las rodajas
esperadas se sacan troceando `renderizada.muestras` con esos indices.

**Ni un `time.sleep` para sincronizar con el hilo.** Todas las esperas son
condiciones con limite: `CabezalFalso.esperar_llamadas` bloquea en un `Event`
que el propio cabezal levanta, y `StreamCapturadoBloqueante` avisa por otro
cuando entra en `write()`. Esta rama ya ha arreglado dos pruebas intermitentes.

Toda la salida va por `SalidaCapturada` (o, cuando hace falta bloquear una
escritura, por su `StreamCapturado` metido en una `SalidaAudio` de verdad):
el sandbox de desarrollo no puede abrir audio.
"""

import threading
import time

import numpy as np
import pytest

from nucleo.acompanamiento import PiezaRenderizada, renderizar
from nucleo.acompanante import Acompanante, BloqueadoAhora
from nucleo.gemelo.salida import SalidaCapturada, StreamCapturado
from nucleo.piezas.voces_de_fondo import NotaDeFondo, VozDeFondo
from nucleo.sintesis import SalidaAudio

TEMPO = 120
MUESTREO = 48000
LIMITE_S = 10.0


def _muestra_del_pulso(
    pulso: float, tempo: int = TEMPO, factor_tempo: float = 1.0, muestreo: int = MUESTREO
) -> int:
    """El indice de muestra de un pulso, A MANO.

        segundos = pulsos * 60 / (tempo * factor_tempo)
        muestras = segundos * frecuencia_muestreo

    Escrita aqui a proposito, igual que en `test_acompanamiento.py`: si se
    preguntara a `rodaja()` donde empieza el bloque, la prueba del mapa estaria
    comparando el mapa consigo mismo.
    """
    segundos = pulso * 60.0 / (tempo * factor_tempo)
    return int(round(segundos * muestreo))


def _pieza_con_notas(ultimo_pulso: int = 12) -> PiezaRenderizada:
    """Una pieza de verdad -renderizada- con una nota en cada pulso.

    Hace falta audio NO silencioso en los pulsos que las pruebas piden: una
    prueba que compara dos bloques de ceros no distingue nada.
    """
    notas = tuple(
        NotaDeFondo(midi=52.0 + (pulso % 5), inicio_pulsos=float(pulso), duracion_pulsos=1.0)
        for pulso in range(ultimo_pulso + 1)
    )
    voces = (VozDeFondo(nombre="Bajo", instrumento="Bass", notas=notas),)
    return renderizar(voces, tempo=TEMPO, frecuencia_muestreo=MUESTREO, semilla=7)


def _pieza_constante(valor: float, muestras: int = 400000) -> PiezaRenderizada:
    """Una pieza falsa cuyo buffer entero vale lo mismo.

    No pasa por `renderizar`: es un doble, y sirve para que una asercion sobre
    ganancia o sobre un cambio de buffer no tenga que pelearse con la forma de
    onda de una cuerda pulsada. Los pulsos por segundo son los de `TEMPO`
    calculados a mano.
    """
    return PiezaRenderizada(
        muestras=np.full(muestras, valor, dtype=np.float32),
        frecuencia_muestreo=MUESTREO,
        pulsos_por_segundo=TEMPO / 60.0,
        duracion_s=muestras / MUESTREO,
    )


def _pieza_numerada(muestras: int) -> PiezaRenderizada:
    """Una pieza falsa donde la muestra `i` vale `i + 1`.

    Asi el primer valor de un bloque escrito DICE de que indice de muestra
    salio, que es lo unico que permite medir la deriva sin preguntarle al
    acompañante donde cree que va. El `+ 1` evita que el indice 0 se confunda
    con el silencio que escribe un cabezal `None`. float32 representa exactos
    los enteros hasta 2**24, muy por encima de lo que estas pruebas usan.
    """
    return PiezaRenderizada(
        muestras=(np.arange(muestras, dtype=np.float64) + 1.0).astype(np.float32),
        frecuencia_muestreo=MUESTREO,
        pulsos_por_segundo=TEMPO / 60.0,
        duracion_s=muestras / MUESTREO,
    )


class CabezalFalso:
    """El cabezal del carril, de pruebas: contesta lo que le digan y avisa.

    `respuesta(n)` recibe el NUMERO de llamada (empezando en 1) y devuelve el
    instante en pulsos, `None`, o lanza `BloqueadoAhora`.

    `esperar_llamadas(n)` bloquea en un `Event` hasta que llegue la llamada `n`.
    Cuidado con la cuenta: el acompañante pregunta ANTES de escribir, asi que
    esperar `n + 1` llamadas es lo que garantiza que el bloque `n` ya esta
    escrito.
    """

    def __init__(self, respuesta) -> None:
        self.respuesta = respuesta
        self.llamadas = 0
        self._candado = threading.Lock()
        self._objetivo: int | None = None
        self._alcanzado = threading.Event()

    def __call__(self) -> float | None:
        with self._candado:
            self.llamadas += 1
            numero = self.llamadas
            if self._objetivo is not None and numero >= self._objetivo:
                self._alcanzado.set()
        # Fuera del candado: `respuesta` puede lanzar `BloqueadoAhora`, y la
        # llamada ya quedo contada igual que la contaria un cabezal real.
        return self.respuesta(numero)

    def esperar_llamadas(
        self, cuantas: int, limite: float = LIMITE_S, sin_avance: float = 2.0
    ) -> bool:
        """Espera hasta la llamada `cuantas`, o hasta que deje de haber avance.

        La espera va a trozos de `sin_avance` segundos y se rinde si en uno de
        ellos no entra NI UNA llamada nueva: un hilo que ya se murio -o que dejo
        de preguntar el cabezal porque se puso un reloj propio- no va a llegar
        nunca, y agotar el limite entero solo consigue que una prueba en rojo
        tarde en decirlo mientras el hilo sigue llenando el capturador.
        """
        final = time.monotonic() + limite
        while True:
            with self._candado:
                if self.llamadas >= cuantas:
                    return True
                previas = self.llamadas
                self._objetivo = cuantas
                self._alcanzado.clear()
            restante = final - time.monotonic()
            if restante <= 0.0:
                return False
            if self._alcanzado.wait(min(sin_avance, restante)):
                return True
            with self._candado:
                if self.llamadas >= cuantas:
                    return True
                if self.llamadas == previas:
                    return False


class StreamCapturadoBloqueante(StreamCapturado):
    """`StreamCapturado` cuya `write()` espera a que la prueba la libere.

    Reproduce a voluntad el escenario del hilo huerfano -el mismo que
    `Metronomo` ya defiende-: la escritura sigue dentro de `write()` cuando el
    `join(timeout=1.0)` de `detener()` ya vencio y devolvio el control. Hereda de
    `StreamCapturado` para seguir guardando lo escrito igual que el capturador
    de la Task 3.
    """

    def __init__(self, **argumentos) -> None:
        super().__init__(**argumentos)
        self.dentro_de_write = threading.Event()
        self._liberar = threading.Event()

    def write(self, muestras) -> None:
        self.dentro_de_write.set()
        self._liberar.wait()
        super().write(muestras)

    def liberar(self) -> None:
        self._liberar.set()


def _por_bloques(captura: SalidaCapturada, bloque: int) -> np.ndarray:
    """Lo escrito, troceado en filas de `bloque` muestras.

    Se llama con el hilo ya detenido, para que la concatenacion no pille una
    escritura a medio camino.
    """
    muestras = captura.muestras
    enteros = muestras.size // bloque
    return muestras[: enteros * bloque].reshape(enteros, bloque)


def _arrancado(
    cabezal: CabezalFalso,
    renderizada: PiezaRenderizada | None = None,
    bloque: int = 512,
    captura: SalidaCapturada | None = None,
) -> tuple[Acompanante, SalidaCapturada]:
    """Un acompañante ya sonando sobre una salida capturada."""
    captura = captura or SalidaCapturada(frecuencia_muestreo=MUESTREO)
    assert captura.abrir() is True
    acompanante = Acompanante(salida=captura.salida, bloque=bloque)
    if renderizada is not None:
        acompanante.cargar(renderizada)
    assert acompanante.iniciar(cabezal) is True
    return acompanante, captura


# --------------------------------------------------------------------------
# El corazon: de donde sale cada bloque
# --------------------------------------------------------------------------


def test_cada_bloque_sale_del_cabezal_y_no_de_un_contador():
    """Un cabezal clavado en el mismo instante da diez bloques IDENTICOS.

    Es el mutante que mata la idea de un reloj interno: con un contador propio
    -de bloques escritos o de muestras acumuladas- los diez bloques avanzarian
    por el buffer y serian distintos entre si. El acompañante no acumula nada:
    pregunta, y si le dicen el mismo pulso escribe el mismo audio.
    """
    renderizada = _pieza_con_notas()
    bloque = 512
    cabezal = CabezalFalso(lambda numero: 2.0)
    acompanante, captura = _arrancado(cabezal, renderizada, bloque)
    try:
        assert cabezal.esperar_llamadas(11) is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= 10

    desde = _muestra_del_pulso(2.0)
    esperado = renderizada.muestras[desde : desde + bloque]
    assert np.any(esperado != 0.0), "la prueba no distingue nada si el pulso 2 es silencio"
    for indice, fila in enumerate(filas[:10]):
        assert np.array_equal(fila, esperado), f"el bloque {indice} no es el del pulso 2"


def test_un_cabezal_que_salta_hace_saltar_el_audio():
    """El cabezal pasa del pulso 0 al 8 y el audio salta con el.

    Si el cabezal salta -un bucle, un salto de compas-, el audio salta: eso es
    lo correcto. La referencia NO es `rodaja(8.0, bloque)`, que seria el mismo
    camino de codigo que se prueba, sino el trozo de `renderizada.muestras` que
    empieza en el indice calculado a mano desde tempo y frecuencia.
    """
    renderizada = _pieza_con_notas()
    bloque = 512
    cabezal = CabezalFalso(lambda numero: 0.0 if numero <= 3 else 8.0)
    acompanante, captura = _arrancado(cabezal, renderizada, bloque)
    try:
        assert cabezal.esperar_llamadas(7) is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= 6

    desde_cero = _muestra_del_pulso(0.0)
    desde_ocho = _muestra_del_pulso(8.0)
    antes = renderizada.muestras[desde_cero : desde_cero + bloque]
    despues = renderizada.muestras[desde_ocho : desde_ocho + bloque]
    assert not np.array_equal(antes, despues), "los dos pulsos suenan igual: no prueba nada"

    for indice in range(3):
        assert np.array_equal(filas[indice], antes), f"el bloque {indice} no es el del pulso 0"
    for indice in range(3, 6):
        assert np.array_equal(filas[indice], despues), f"el bloque {indice} no salto al pulso 8"


def test_cabezal_None_escribe_silencio_y_el_hilo_sigue_vivo():
    """`None` es la cuenta atras: ceros exactos, y el hilo NO para.

    Parar y arrancar el stream en cada cuenta atras es un chasquido en cada
    pasada del bucle. El cabezal devuelve `None` cuando ahora mismo no hay nada
    que suene -cuenta atras, pasada terminada, sin pasada- y el acompañante
    responde con silencio sin tocar el dispositivo.
    """
    renderizada = _pieza_constante(0.5)
    bloque = 256
    cabezal = CabezalFalso(lambda numero: None)
    acompanante, captura = _arrancado(cabezal, renderizada, bloque)
    try:
        assert cabezal.esperar_llamadas(9) is True
        assert acompanante.sonando is True, "el silencio no debe matar el hilo"
        assert captura.arranques == 1
        assert captura.cierres == 0
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= 8
    assert np.array_equal(filas, np.zeros_like(filas)), "no son ceros exactos"
    assert acompanante.muestras_escritas >= 8 * bloque
    # Y el stream nunca se cerro ni se volvio a abrir por el camino.
    assert captura.arranques == 1
    assert captura.cierres == 0


def test_cero_deriva_en_diez_mil_bloques():
    """El error entre el instante pedido y el escrito no CRECE con el tiempo.

    Se afirma el CRECIMIENTO -el primer decil contra el ultimo- y no un umbral
    medido en una maquina en reposo. El cabezal de la prueba avanza 101,37
    muestras por bloque, a proposito un numero que NO es el tamaño del bloque:
    un acompañante que contara bloques coincidiria con un cabezal que avanzara
    exactamente un bloque por vuelta, y la prueba no veria nada.

    La pieza esta numerada (`_pieza_numerada`), asi que el primer valor de cada
    bloque escrito dice de que indice de muestra salio. El error esperado es
    solo el del redondeo al entero mas cercano, o sea media muestra como mucho,
    y no depende de cuantos bloques hayan pasado.
    """
    paso = 101.37
    primer_indice = 1000.0
    bloques_pedidos = 10000
    bloque = 64
    muestras = int(primer_indice + paso * (bloques_pedidos + 100)) + bloque + 2
    renderizada = _pieza_numerada(muestras)
    pulsos_por_segundo = TEMPO / 60.0  # a mano: tempo x factor / 60

    def objetivo(numero: int) -> float:
        """El indice de muestra que la prueba quiere, para la llamada `numero`."""
        return primer_indice + paso * (numero - 1)

    def respuesta(numero: int) -> float:
        indice = min(objetivo(numero), float(muestras - bloque - 2))
        # El pulso que corresponde a ese indice, a mano y en el sentido inverso
        # al de la produccion: muestras -> segundos -> pulsos.
        return indice / MUESTREO * pulsos_por_segundo

    cabezal = CabezalFalso(respuesta)
    acompanante, captura = _arrancado(cabezal, renderizada, bloque)
    try:
        assert cabezal.esperar_llamadas(bloques_pedidos + 1, limite=60.0) is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= bloques_pedidos

    # El indice del que salio cada bloque, leido del propio audio.
    leidos = filas[:bloques_pedidos, 0].astype(np.float64) - 1.0
    pedidos = np.array([objetivo(numero) for numero in range(1, bloques_pedidos + 1)])
    error = np.abs(leidos - pedidos)

    decil = bloques_pedidos // 10
    primero = float(error[:decil].mean())
    ultimo = float(error[-decil:].mean())
    assert ultimo <= primero * 1.5, (
        f"el error crece con el tiempo: primer decil {primero:.4f} muestras, "
        f"ultimo decil {ultimo:.4f}. Eso es un reloj propio derivando del carril."
    )
    # Y en terminos absolutos no pasa de medio redondeo en ningun bloque: no es
    # un umbral de tiempo, es la aritmetica del mapa.
    assert float(error.max()) <= 0.5 + 1e-6


# --------------------------------------------------------------------------
# Cambios en caliente: el candado del acompañante
# --------------------------------------------------------------------------


def test_cargar_en_caliente_no_deja_pasar_una_muestra_del_buffer_viejo():
    """El buffer nuevo entra en el bloque SIGUIENTE, entero y de golpe.

    La pieza A vale 0,5 en todas sus muestras y la B vale -0,5. `cargar(B)` se
    llama DESDE EL CABEZAL, o sea en el peor momento posible: justo despues de
    que el hilo tomara su foto del bloque y antes de cortar la rodaja. El bloque
    en vuelo tiene que salir entero de A -mezclar medio bloque de cada una es un
    chasquido- y a partir del siguiente no puede quedar ni una muestra positiva.
    """
    bloque = 256
    pieza_a = _pieza_constante(0.5)
    pieza_b = _pieza_constante(-0.5)
    cambio = 5
    guardado: dict[str, Acompanante] = {}

    def respuesta(numero: int) -> float:
        if numero == cambio:
            guardado["acompanante"].cargar(pieza_b)
        return 0.0

    cabezal = CabezalFalso(respuesta)
    captura = SalidaCapturada(frecuencia_muestreo=MUESTREO)
    assert captura.abrir() is True
    acompanante = Acompanante(salida=captura.salida, bloque=bloque)
    guardado["acompanante"] = acompanante
    acompanante.cargar(pieza_a)
    assert acompanante.iniciar(cabezal) is True
    try:
        assert cabezal.esperar_llamadas(cambio + 4) is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= cambio + 3

    viejos = filas[:cambio]
    nuevos = filas[cambio:]
    assert np.all(viejos == np.float32(0.5)), (
        "el buffer nuevo se aplico dentro del bloque en vuelo: `cargar()` tiene "
        "que verse en el bloque siguiente, no en el de la llamada"
    )
    assert np.all(nuevos == np.float32(-0.5)), "algun bloque salio mezclado"
    assert not np.any(nuevos > 0.0), "paso una muestra del buffer viejo"


def test_el_candado_ocupado_repite_el_ultimo_cabezal_y_no_abre_silencio():
    """`BloqueadoAhora` repite el audio anterior; no abre un agujero de ceros.

    Es lo que hara la clausura de la Task 5 cuando su `acquire(blocking=False)`
    falle porque la sesion esta ocupada. Esperar el candado dejaria el
    dispositivo sin alimentar; escribir ceros seria un hueco audible en medio de
    la pieza. Repetir el ultimo cabezal conocido es, como mucho, un bloque de
    21 ms que suena dos veces.
    """
    renderizada = _pieza_con_notas()
    bloque = 512

    def respuesta(numero: int) -> float:
        if numero == 3:
            raise BloqueadoAhora("la sesion estaba ocupada (simulado)")
        return 4.0

    cabezal = CabezalFalso(respuesta)
    captura = SalidaCapturada(frecuencia_muestreo=MUESTREO)
    assert captura.abrir() is True
    acompanante = Acompanante(salida=captura.salida, bloque=bloque)
    acompanante.cargar(renderizada)
    # Antes de arrancar, para que la foto no se la pueda comer el hilo: una vez
    # arrancado, el bloqueo del tercer bloque puede haber pasado ya.
    assert acompanante.cabezales_repetidos == 0
    assert acompanante.iniciar(cabezal) is True
    try:
        assert cabezal.esperar_llamadas(5) is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= 4
    assert acompanante.cabezales_repetidos == 1

    desde = _muestra_del_pulso(4.0)
    esperado = renderizada.muestras[desde : desde + bloque]
    assert np.any(esperado != 0.0), "el pulso 4 es silencio: la prueba no distingue nada"
    assert np.array_equal(filas[2], esperado), "el bloque bloqueado no repitio el pulso 4"
    assert np.any(filas[2] != 0.0), "el bloque bloqueado abrio un agujero de ceros"


def test_un_bloqueo_sin_cabezal_previo_escribe_silencio_y_no_lanza():
    """Si el primerisimo cabezal se bloquea no hay nada que repetir: ceros.

    El caso de borde del anterior. No puede lanzar, y no puede leer un ultimo
    instante que todavia no existe.
    """
    renderizada = _pieza_constante(0.5)
    bloque = 128

    def respuesta(numero: int) -> float:
        if numero == 1:
            raise BloqueadoAhora("ocupada desde el primer bloque (simulado)")
        return 0.0

    cabezal = CabezalFalso(respuesta)
    acompanante, captura = _arrancado(cabezal, renderizada, bloque)
    try:
        assert cabezal.esperar_llamadas(4) is True
        assert acompanante.sonando is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= 3
    assert acompanante.cabezales_repetidos == 1
    assert np.array_equal(filas[0], np.zeros(bloque, dtype=np.float32))
    assert np.all(filas[1:] == np.float32(0.5))


def test_la_ganancia_se_aplica_suavizada_dentro_del_bloque():
    """De 1,0 a 0,0: el bloque del cambio es una rampa, no un escalon.

    Multiplicar de golpe mete un salto del tamaño entero del cambio entre dos
    muestras consecutivas, y eso es un chasquido audible. El bloque del cambio
    empieza en el valor VIEJO y acaba en el NUEVO, y el salto maximo entre dos
    muestras seguidas (contando la frontera con el bloque anterior) es mucho
    menor que el que daria el escalon, calculado aqui a mano.
    """
    valor = 0.5
    bloque = 1024
    renderizada = _pieza_constante(valor)
    cabezal = CabezalFalso(lambda numero: 0.0)
    acompanante, captura = _arrancado(cabezal, renderizada, bloque)
    try:
        assert cabezal.esperar_llamadas(4) is True
        acompanante.ganancia(0.0)
        assert cabezal.esperar_llamadas(cabezal.llamadas + 5) is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    # El bloque del cambio: el primero que no sale entero a ganancia 1,0.
    cambiados = [
        indice for indice, fila in enumerate(filas) if not np.all(fila == np.float32(valor))
    ]
    assert cambiados, "la ganancia no llego a aplicarse"
    indice = cambiados[0]
    assert indice >= 1, "hace falta un bloque anterior para medir la frontera"
    fila = filas[indice]

    assert fila[0] == pytest.approx(valor, abs=1e-6), (
        "el bloque del cambio empieza ya en la ganancia nueva: eso es el escalon"
    )
    assert fila[-1] == pytest.approx(0.0, abs=1e-6), (
        "el bloque del cambio acaba en la ganancia vieja: la rampa no termino"
    )
    assert np.all(np.diff(fila) <= 1e-7), "la rampa no es monotona"

    # El salto de golpe, A MANO: la muestra entera pasaria de 0,5 a 0,0.
    salto_de_golpe = valor * abs(1.0 - 0.0)
    frontera = np.concatenate(([filas[indice - 1][-1]], fila))
    salto_medido = float(np.abs(np.diff(frontera)).max())
    assert salto_medido < salto_de_golpe, (
        f"el salto medido {salto_medido:.6f} no mejora el escalon {salto_de_golpe:.6f}"
    )
    # Y en concreto es del orden de un bloque de rampa, no de un escalon.
    assert salto_medido < salto_de_golpe / 10.0

    # Pasada la rampa, la ganancia nueva se queda puesta.
    assert np.all(filas[indice + 1 :] == np.float32(0.0))


def test_la_ganancia_pedida_antes_de_arrancar_sale_ya_en_el_primer_bloque():
    """`ganancia()` sin hilo vivo no se pierde: la coge el primer bloque."""
    renderizada = _pieza_constante(1.0)
    bloque = 128
    captura = SalidaCapturada(frecuencia_muestreo=MUESTREO)
    assert captura.abrir() is True
    acompanante = Acompanante(salida=captura.salida, bloque=bloque)
    acompanante.cargar(renderizada)
    acompanante.ganancia(0.25)
    cabezal = CabezalFalso(lambda numero: 0.0)
    assert acompanante.iniciar(cabezal) is True
    try:
        assert cabezal.esperar_llamadas(4) is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= 3
    # El primer bloque sube de 1,0 a 0,25 en rampa; del segundo en adelante ya
    # esta plano en el valor pedido.
    assert np.all(filas[1:] == np.float32(0.25))


# --------------------------------------------------------------------------
# Degradar, nunca tumbar
# --------------------------------------------------------------------------


def test_sin_salida_de_audio_iniciar_devuelve_False_y_no_lanza():
    """Es el contrato que el metronomo de la 3c ya tiene: degradar, no tumbar.

    En una maquina sin dispositivo la pieza de fondo no suena, y el carril sigue
    funcionando igual. Lo que no puede pasar es que la sesion reviente.
    """
    captura = SalidaCapturada(frecuencia_muestreo=MUESTREO, fallar_al_abrir=True)
    assert captura.abrir() is False
    acompanante = Acompanante(salida=captura.salida, bloque=256)
    acompanante.cargar(_pieza_constante(0.5))
    cabezal = CabezalFalso(lambda numero: 0.0)

    assert acompanante.iniciar(cabezal) is False
    assert acompanante.sonando is False
    assert acompanante.muestras_escritas == 0
    assert cabezal.llamadas == 0
    # Y lo demas sigue siendo seguro de llamar.
    acompanante.pausar()
    acompanante.reanudar()
    acompanante.ganancia(0.5)
    acompanante.detener()
    assert acompanante.sonando is False


def test_sin_pieza_cargada_escribe_silencio_y_no_lanza():
    """Arrancar antes de `cargar()` no es un error: es silencio."""
    bloque = 128
    cabezal = CabezalFalso(lambda numero: 3.0)
    acompanante, captura = _arrancado(cabezal, None, bloque)
    try:
        assert cabezal.esperar_llamadas(4) is True
        assert acompanante.sonando is True
    finally:
        acompanante.detener()

    filas = _por_bloques(captura, bloque)
    assert len(filas) >= 3
    assert np.array_equal(filas, np.zeros_like(filas))


def test_una_escritura_que_falla_no_cuenta_ni_mata_el_hilo():
    """Un `OSError` de la tarjeta no para la pieza y no se cuenta como escrito.

    `muestras_escritas` dice lo que SE ESCRIBIO, no lo que se intento: si
    contara los intentos, un dispositivo que falla la mitad de las escrituras
    mentiria el doble.
    """
    bloque = 128
    captura = SalidaCapturada(frecuencia_muestreo=MUESTREO, fallar_en=2)
    cabezal = CabezalFalso(lambda numero: 0.0)
    acompanante, captura = _arrancado(cabezal, _pieza_constante(0.5), bloque, captura)
    try:
        assert cabezal.esperar_llamadas(7) is True
        assert acompanante.sonando is True, "un fallo de escritura mato el hilo"
    finally:
        acompanante.detener()

    grabadas = captura.muestras.size
    escritas = acompanante.muestras_escritas
    assert grabadas >= 3 * bloque
    assert escritas <= grabadas, "se contaron muestras que la salida rechazo"
    # Como mucho queda sin contar el bloque que estaba en vuelo cuando
    # `detener()` cambio la generacion.
    assert grabadas - escritas <= bloque


# --------------------------------------------------------------------------
# La forma del hilo, copiada de `Metronomo`
# --------------------------------------------------------------------------


def test_detener_mientras_una_escritura_esta_bloqueada_no_vuelve_a_escribir():
    """El hilo huerfano, el mismo que `Metronomo` ya defiende.

    El stream se queda dentro de `write()`; `detener()` incrementa la generacion
    y su `join(timeout=1.0)` vence, asi que devuelve el control con el hilo
    todavia vivo. Cuando ese hilo despierta, la comprobacion de generacion de
    DESPUES de `reproducir()` tiene que retirarlo: ni una muestra mas contada ni
    otra vuelta escribiendo sobre una salida que la sesion ya pudo cerrar.
    """
    stream = StreamCapturadoBloqueante()
    salida = SalidaAudio(frecuencia_muestreo=MUESTREO, abrir_stream=lambda **kw: stream)
    assert salida.abrir() is True
    bloque = 256
    cabezal = CabezalFalso(lambda numero: 0.0)
    acompanante = Acompanante(salida=salida, bloque=bloque)
    acompanante.cargar(_pieza_constante(0.5))
    assert acompanante.iniciar(cabezal) is True
    hilo = acompanante._hilo  # el huerfano: `detener()` suelta su referencia

    # El hilo ya esta dentro de write(), bloqueado.
    assert stream.dentro_de_write.wait(LIMITE_S) is True

    arranque = time.monotonic()
    acompanante.detener()
    vencido = time.monotonic() - arranque
    assert vencido >= 1.0, "el join(timeout=1.0) tendria que haber esperado y vencido"
    assert acompanante.muestras_escritas == 0

    # Ahora se libera la escritura: el huerfano puede continuar.
    stream.liberar()
    assert hilo is not None
    hilo.join(timeout=LIMITE_S)
    assert hilo.is_alive() is False, "el hilo huerfano no se retiro"

    assert stream.bloques == (bloque,), (
        "el hilo huerfano escribio otro bloque: falta la comprobacion de "
        "generacion de despues de reproducir()"
    )
    assert acompanante.muestras_escritas == 0, (
        "el hilo huerfano conto como escrito un bloque que nadie oyo"
    )


def test_detener_mientras_el_cabezal_esta_bloqueado_no_escribe_el_bloque_en_vuelo():
    """La otra mitad de la defensa: la comprobacion de generacion de ANTES.

    El hilo huerfano no solo se cuela por la escritura; tambien se cuela por el
    cabezal, que es codigo AJENO (la clausura de la Task 5, que toca el candado
    de la sesion) y puede tardar lo que quiera. Aqui el hilo se queda dentro del
    cabezal, el `join(timeout=1.0)` de `detener()` vence, y cuando el cabezal
    por fin contesta el bloque ya no se debe escribir: la salida pudo cerrarse
    mientras tanto.
    """
    bloque = 256
    captura = SalidaCapturada(frecuencia_muestreo=MUESTREO)
    assert captura.abrir() is True
    acompanante = Acompanante(salida=captura.salida, bloque=bloque)
    acompanante.cargar(_pieza_constante(0.5))

    dentro = threading.Event()
    soltar = threading.Event()

    def respuesta(numero: int) -> float:
        dentro.set()
        soltar.wait(LIMITE_S)
        return 0.0

    cabezal = CabezalFalso(respuesta)
    assert acompanante.iniciar(cabezal) is True
    hilo = acompanante._hilo
    assert dentro.wait(LIMITE_S) is True

    arranque = time.monotonic()
    acompanante.detener()
    assert time.monotonic() - arranque >= 1.0, "el join(timeout=1.0) no vencio"

    soltar.set()
    assert hilo is not None
    hilo.join(timeout=LIMITE_S)
    assert hilo.is_alive() is False

    assert captura.bloques == (), (
        "el hilo huerfano escribio el bloque que traia en vuelo: falta la "
        "comprobacion de generacion de ANTES de reproducir()"
    )
    assert acompanante.muestras_escritas == 0


def test_pausar_no_pregunta_el_cabezal_ni_escribe_y_reanudar_no_reabre_el_stream():
    """La pausa por falta de señal: deja de sonar sin matar el hilo.

    Con una bandera y no con `detener()`, por lo mismo que el metronomo: quien
    lo pide es el hilo de analisis y un `join(timeout=1.0)` ahi cegaria la
    deteccion de ataques. Y al reanudar no se reabre el stream: el bloque
    siguiente sale del cabezal, que ya sabe donde esta la pasada.
    """
    bloque = 128
    cabezal = CabezalFalso(lambda numero: 0.0)
    acompanante, captura = _arrancado(cabezal, _pieza_constante(0.5), bloque)
    try:
        assert cabezal.esperar_llamadas(3) is True
        acompanante.pausar()
        assert acompanante.pausado is True
        # El bloque en vuelo puede todavia gastar una llamada mas: se le espera
        # con limite (puede llegar o no) y despues se toma la foto.
        cabezal.esperar_llamadas(cabezal.llamadas + 1, limite=0.5)
        quietas = cabezal.llamadas
        escritas = acompanante.muestras_escritas
        # Ya parado de verdad: ni una llamada mas al cabezal ni una escritura.
        assert cabezal.esperar_llamadas(quietas + 1, limite=0.5) is False
        assert cabezal.llamadas == quietas
        assert acompanante.muestras_escritas == escritas
        assert acompanante.sonando is True

        acompanante.reanudar()
        assert acompanante.pausado is False
        assert cabezal.esperar_llamadas(quietas + 3) is True
        assert acompanante.muestras_escritas > escritas
    finally:
        acompanante.detener()

    assert captura.arranques == 1
    assert captura.cierres == 0


def test_todos_los_bloques_tienen_el_tamano_pedido():
    """Un bloque corto es un chasquido: `rodaja` siempre devuelve `cuantas`.

    Tambien en los bordes: el cabezal pide pulsos negativos (cuenta atras) y
    pulsos mas alla del final de la pieza (pasada parada), y los dos tienen que
    salir del tamaño entero y rellenos de silencio.
    """
    renderizada = _pieza_con_notas(ultimo_pulso=4)
    bloque = 333
    instantes = (-4.0, -0.5, 0.0, 2.0, 4.0, 400.0, 10000.0)
    cabezal = CabezalFalso(lambda numero: instantes[(numero - 1) % len(instantes)])
    acompanante, captura = _arrancado(cabezal, renderizada, bloque)
    try:
        assert cabezal.esperar_llamadas(len(instantes) * 2 + 1) is True
        assert acompanante.sonando is True
    finally:
        acompanante.detener()

    tamanos = captura.bloques
    assert len(tamanos) >= len(instantes) * 2
    assert set(tamanos) == {bloque}
    # El bloque en vuelo cuando `detener()` cambio la generacion puede quedar
    # grabado y sin contar: de ahi el margen de uno.
    assert acompanante.muestras_escritas in (
        len(tamanos) * bloque,
        (len(tamanos) - 1) * bloque,
    )


def test_iniciar_dos_veces_no_arranca_un_segundo_hilo():
    """Idempotente, como `Metronomo.iniciar()`: True y el mismo hilo."""
    bloque = 128
    cabezal = CabezalFalso(lambda numero: 0.0)
    acompanante, captura = _arrancado(cabezal, _pieza_constante(0.5), bloque)
    try:
        hilo = acompanante._hilo
        otro = CabezalFalso(lambda numero: 8.0)
        assert acompanante.iniciar(otro) is True
        assert acompanante._hilo is hilo
        assert cabezal.esperar_llamadas(3) is True
        assert otro.llamadas == 0, "arranco un segundo hilo con el cabezal nuevo"
    finally:
        acompanante.detener()
    assert captura.arranques == 1


def test_detener_es_idempotente_y_sin_iniciar_no_lanza():
    """Seguro de llamar varias veces, y antes de arrancar tambien."""
    captura = SalidaCapturada(frecuencia_muestreo=MUESTREO)
    assert captura.abrir() is True
    acompanante = Acompanante(salida=captura.salida, bloque=128)
    acompanante.detener()
    acompanante.detener()
    assert acompanante.sonando is False

    cabezal = CabezalFalso(lambda numero: 0.0)
    acompanante.cargar(_pieza_constante(0.5))
    assert acompanante.iniciar(cabezal) is True
    assert cabezal.esperar_llamadas(2) is True
    acompanante.detener()
    acompanante.detener()
    assert acompanante.sonando is False


def test_un_bloque_que_no_es_un_entero_positivo_se_rechaza_al_construir():
    """Fallar al construir y no en el hilo, donde nadie ve la excepcion."""
    for malo in (0, -1):
        with pytest.raises(ValueError):
            Acompanante(salida=SalidaCapturada(frecuencia_muestreo=MUESTREO).salida, bloque=malo)
