"""El guitarrista sintetico: convierte una `Pieza` en audio y en su propia verdad.

La regla que ordena todo este modulo es que **la verdad se escribe antes que el
sonido**. `interpretar` construye primero la tupla completa de `EventoTocado`
-que nota suena, cuando, cuanto, con cuantos cents de desviacion y si roza el
traste- y solo despues recorre esa tupla generando muestras. Nunca al reves: si
la verdad se dedujera del audio, el gemelo estaria preguntandole al detector de
tono que es lo que paso, y entonces no verificaria nada, se daria la razon.

Todo el azar sale de un unico `numpy.random.default_rng(semilla)` y **el orden en
que se consume es parte del contrato**: por cada nota del tramo, en orden,
fallo -> nota mala -> trasteo -> desfase -> desafinacion -> fuerza. Se consume
SIEMPRE, incluso cuando el perfil tiene esa probabilidad a cero y cuando la nota
ya se ha fallado. Saltarse un sorteo condicionalmente desplazaria todo el azar
posterior, y entonces dos interpretaciones que deberian diferir en una sola cosa
diferirian en todo: el gemelo dejaria de servir para comparar perfiles.

El tramo se dice EN COMPASES, con la misma convencion que `PlanDePasada` (1 es el
primero, `None` es «hasta el final»), para que el gemelo pueda interpretar
exactamente el tramo que el plan de la pasada describe sin traducir compases a
pulsos en dos sitios distintos.
"""

from dataclasses import dataclass

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.gemelo.cuerda import cuerda_pulsada
from nucleo.gemelo.perfiles import PerfilDeDestreza
from nucleo.musica import midi_a_frecuencia
from nucleo.piezas.compases import pulsos_por_compas, total_de_compases
from nucleo.piezas.modelo import NotaEnPieza, Pieza, pulsos_a_segundos

# Cuantas ventanas de analisis de silencio van antes de la primera nota. Es
# OBLIGATORIO y no es estetica: sin cabecera, el primer cuadro que llega a la
# cadena ya contiene la primera nota, el reloj de la pieza se ancla ahi y todo lo
# que viene despues se lee adelantado. La spec lo midio: una sonda sin cabecera
# informaba -69 ms de desfase en una interpretacion PERFECTA, o sea un artefacto
# del gemelo acusando a la cadena. Una ventana y media deja ademas un cuadro
# entero de silencio limpio antes del que coge el ataque.
VENTANAS_DE_CABECERA = 1.5

# Que fraccion del hueco hasta la nota siguiente ocupa una nota con `sustain` 0.
# El 15% restante es el silencio que garantiza que el interprete no solapa dos
# notas por su cuenta.
FRACCION_DE_CORTE = 0.85

# Cuanto se deja sonar la cuerda, en figuras, cuando `sustain` es 1. Pasa de 1 a
# proposito: una cuerda que nadie apaga no se calla en la barra de compas, y si
# el techo fuese la figura EXACTA una pieza de notas pegadas (figura = hueco)
# nunca llegaria a solaparse y los ataques fantasma de la spec §10 no se podrian
# provocar ni medir. Es la unica desviacion de «1 deja sonar la figura entera».
COLA_DE_SUSTAIN = 1.3

# Suciedad que se le pasa a la cuerda cuando la nota sale trasteada. La tabla de
# calibracion de `cuerda.py` midio que con 0,6 el detector lee la nota correcta
# en el 56% de las ventanas y con 0,8 en el 8%: 0,7 deja la nota reconocible a
# ratos, que es lo que hace un dedo mal puesto, en vez de convertirla en ruido.
TRASTEO_DE_LA_NOTA_SUCIA = 0.7

# A que distancia cae el traste equivocado. El dedo se va al de al lado o al
# siguiente, nunca a media octava.
DESVIOS_DE_NOTA_MALA = (-2, -1, 1, 2)

# Separacion entre las semillas de dos notas consecutivas. El ruido inicial de
# cada cuerda sale de su propia semilla, derivada de la global y del SITIO de la
# nota -su puesto dentro del tramo y el numero de vuelta-, para que la misma
# semilla de la misma interpretacion muestra a muestra sin que dos notas
# compartan el mismo ruido.
#
# El sitio y no el orden de llegada: si la semilla se derivase del numero de
# pulsaciones ya generadas, solo creceria con las notas que NO se fallan, y
# entonces subir `probabilidad_de_fallo` cambiaria el timbre de notas que no
# fallaron. El generador global seguiria cumpliendo su contrato, pero este
# segundo flujo de azar incumpliria su espiritu: dos interpretaciones que
# deberian diferir en una cosa diferirian en el ruido de cada cuerda.
PASO_DE_SEMILLA = 7919

# Separacion entre las semillas de dos vueltas. Primo y mucho mayor que el numero
# de notas de cualquier tramo, para que la vuelta 2 no herede las semillas de la
# vuelta 1 desplazadas una nota.
PASO_DE_SEMILLA_POR_VUELTA = 1_000_003


@dataclass(frozen=True)
class EventoTocado:
    """Una pulsacion que de verdad sono, con todo lo que el veredicto necesita.

    `indice_pretendido` es el indice en `Pieza.notas` de la nota a la que el
    guitarrista apuntaba, y es `None` cuando nadie la escribio (no ocurre
    todavia: lo reservan las pulsaciones inventadas que el gemelo podra anadir).
    `midi` es lo que sono DE VERDAD, que con `probabilidad_de_nota_mala` no es lo
    escrito. Una nota fallada no tiene evento: su indice simplemente no aparece.
    """

    indice_pretendido: int | None
    midi: int
    instante_s: float
    duracion_s: float
    cents: float
    trasteada: bool


@dataclass(frozen=True)
class Interpretacion:
    """El audio de una pasada y la verdad de lo que se toco en ella.

    Lleva la `pieza` dentro, y es el primer campo, porque `juzgar` tiene que
    excluir del veredicto los acordes y las notas repetidas consecutivas, y esas
    exclusiones se determinan DESDE LA PIEZA y no desde lo que la cadena hizo. Una
    interpretacion es la interpretacion DE una pieza: sin ella dentro, el
    veredicto no puede cumplir su contrato.
    """

    pieza: Pieza
    muestras: np.ndarray
    eventos: tuple[EventoTocado, ...]
    frecuencia_muestreo: int
    duracion_s: float
    silencio_de_cabecera_s: float


@dataclass(frozen=True)
class _Pulsacion:
    """Un evento mas lo que hace falta para sintetizarlo y no se publica.

    `fuerza` y `trasteo` son del brazo derecho, no de la musica: el veredicto no
    los juzga y no tienen sitio en `EventoTocado`. Pero se sortean en la misma
    pasada que la verdad, antes de generar una sola muestra, para que el orden de
    consumo del generador sea el del contrato.
    """

    evento: EventoTocado
    fuerza: float
    trasteo: float
    semilla: int


def duracion_de_la_nota_s(figura_s: float, hueco_s: float, sustain: float) -> float:
    """Cuanto suena una nota, entre cortarla y dejarla sonar.

    Con `sustain` 0 la nota ocupa como mucho `FRACCION_DE_CORTE` del hueco hasta
    la siguiente -y nunca mas que su figura escrita, para que una corchea suelta
    no suene como una negra-, asi que el interprete NO solapa dos notas por su
    cuenta. Con `sustain` 1 suena su figura entera por `COLA_DE_SUSTAIN`, que si
    solapa. En medio se interpola lineal.

    Solapar a proposito es parte del gemelo (asi se provocan los ataques
    fantasma); solaparlo sin querer seria acusar a la cadena de inventarse notas
    que en realidad se invento el gemelo.
    """
    corte = min(figura_s, FRACCION_DE_CORTE * hueco_s)
    techo = max(corte, figura_s * COLA_DE_SUSTAIN)
    return corte + sustain * (techo - corte)


def interpretar(
    pieza: Pieza,
    perfil: PerfilDeDestreza,
    factor_tempo: float = 1.0,
    primer_compas: int = 1,
    ultimo_compas: int | None = None,
    repeticiones: int = 1,
    segundos_de_cuenta_atras: float = 0.0,
    semilla: int = 0,
    frecuencia_muestreo: int = 48000,
) -> Interpretacion:
    """Toca `pieza` con la destreza de `perfil` y devuelve audio mas verdad.

    Parametros:
        pieza: la pieza escrita. Los acordes se reducen a la nota mas grave.
        perfil: como de bien se toca. `PERFECTO` es el oraculo.
        factor_tempo: 1,0 es el tempo escrito; 0,5 es tocarla al doble de lento.
        primer_compas, ultimo_compas: el tramo, contando desde 1. `None` es hasta
            el final. Una pieza sin notas se interpreta como un compas de silencio.
        repeticiones: cuantas vueltas al tramo, para interpretar un bucle.
        segundos_de_cuenta_atras: silencio antes de CADA vuelta, la primera
            incluida. El de la primera queda dentro de `silencio_de_cabecera_s`.
        semilla: la del generador unico. Misma semilla, misma interpretacion.
        frecuencia_muestreo: muestras por segundo del audio devuelto.

    Lanza `ValueError` si el tramo no existe en la pieza o si alguno de los
    numeros no tiene sentido (tempo o repeticiones no positivos, cuenta atras
    negativa).
    """
    if factor_tempo <= 0.0:
        raise ValueError(
            f"El factor de tempo {factor_tempo} no sirve: tiene que ser mayor que cero"
        )
    if repeticiones < 1:
        raise ValueError(
            f"Las repeticiones {repeticiones} no sirven: tiene que haber al menos una"
        )
    if segundos_de_cuenta_atras < 0.0:
        raise ValueError(
            f"La cuenta atras {segundos_de_cuenta_atras} s no sirve: "
            "no puede ser negativa"
        )

    ancho = pulsos_por_compas(pieza)
    # Una pieza sin notas no tiene compases, pero tiene que poder interpretarse:
    # un compas vacio de una cancion de verdad llega aqui igual y la cadena
    # entera tiene que tragarlo. El tramo minimo es un compas de silencio.
    tope = max(1, total_de_compases(pieza))
    ultimo = tope if ultimo_compas is None else ultimo_compas
    if primer_compas < 1 or ultimo < primer_compas or ultimo > tope:
        raise ValueError(
            f"La pieza '{pieza.nombre}' no tiene el tramo {primer_compas}-{ultimo}: "
            f"sus compases van del 1 al {tope}"
        )

    inicio_tramo = (primer_compas - 1) * ancho
    fin_tramo = ultimo * ancho
    duracion_tramo_s = (
        pulsos_a_segundos(fin_tramo - inicio_tramo, pieza.tempo) / factor_tempo
    )

    a_tocar = _pulsaciones_escritas(pieza, inicio_tramo, fin_tramo)

    ventana = PERFILES[pieza.perfil].tamano_ventana(frecuencia_muestreo)
    cabecera_tecnica_s = VENTANAS_DE_CABECERA * ventana / frecuencia_muestreo
    silencio_de_cabecera_s = cabecera_tecnica_s + segundos_de_cuenta_atras

    generador = np.random.default_rng(semilla)
    pulsaciones: list[_Pulsacion] = []
    for vuelta in range(repeticiones):
        inicio_vuelta_s = (
            cabecera_tecnica_s
            + (vuelta + 1) * segundos_de_cuenta_atras
            + vuelta * duracion_tramo_s
        )
        for puesto, (indice, nota, hueco_pulsos) in enumerate(a_tocar):
            pulsacion = _sortear_pulsacion(
                indice=indice,
                nota=nota,
                hueco_pulsos=hueco_pulsos,
                pieza=pieza,
                perfil=perfil,
                factor_tempo=factor_tempo,
                inicio_tramo=inicio_tramo,
                inicio_vuelta_s=inicio_vuelta_s,
                puesto=puesto,
                vuelta=vuelta,
                semilla=semilla,
                frecuencia_muestreo=frecuencia_muestreo,
                generador=generador,
            )
            if pulsacion is not None:
                pulsaciones.append(pulsacion)

    total_s = cabecera_tecnica_s + repeticiones * (
        segundos_de_cuenta_atras + duracion_tramo_s
    )
    muestras = _generar(pulsaciones, total_s, frecuencia_muestreo)

    return Interpretacion(
        pieza=pieza,
        muestras=muestras,
        eventos=tuple(pulsacion.evento for pulsacion in pulsaciones),
        frecuencia_muestreo=frecuencia_muestreo,
        duracion_s=muestras.size / frecuencia_muestreo,
        silencio_de_cabecera_s=silencio_de_cabecera_s,
    )


def _pulsaciones_escritas(
    pieza: Pieza, inicio_tramo: float, fin_tramo: float
) -> tuple[tuple[int, NotaEnPieza, float], ...]:
    """Las notas del tramo, los acordes ya reducidos, con su hueco a la siguiente.

    De cada grupo de notas que comparten `inicio_pulsos` -eso es un acorde- se
    queda la MAS GRAVE: el detector de tono de produccion es monofonico y el
    gemelo no finge polifonia. El indice que se conserva es el de la nota elegida
    dentro de `Pieza.notas`, que es el que el veredicto compara.

    El hueco de la ultima nota del tramo llega hasta el final del tramo, no hasta
    la nota siguiente de la pieza: lo que viene despues no se va a tocar.
    """
    del_tramo = [
        (indice, nota)
        for indice, nota in enumerate(pieza.notas)
        if inicio_tramo <= nota.inicio_pulsos < fin_tramo
    ]

    elegidas: list[tuple[int, NotaEnPieza]] = []
    for indice, nota in del_tramo:
        if elegidas and elegidas[-1][1].inicio_pulsos == nota.inicio_pulsos:
            if nota.midi < elegidas[-1][1].midi:
                elegidas[-1] = (indice, nota)
            continue
        elegidas.append((indice, nota))

    con_hueco = []
    for puesto, (indice, nota) in enumerate(elegidas):
        siguiente = (
            elegidas[puesto + 1][1].inicio_pulsos
            if puesto + 1 < len(elegidas)
            else fin_tramo
        )
        con_hueco.append((indice, nota, siguiente - nota.inicio_pulsos))
    return tuple(con_hueco)


def _sortear_pulsacion(
    indice: int,
    nota: NotaEnPieza,
    hueco_pulsos: float,
    pieza: Pieza,
    perfil: PerfilDeDestreza,
    factor_tempo: float,
    inicio_tramo: float,
    inicio_vuelta_s: float,
    puesto: int,
    vuelta: int,
    semilla: int,
    frecuencia_muestreo: int,
    generador: np.random.Generator,
) -> _Pulsacion | None:
    """Sortea una nota y devuelve su pulsacion, o `None` si se fallo.

    Los seis sorteos salen SIEMPRE y en este orden, aunque la nota se falle en el
    primero y aunque el perfil tenga la probabilidad a cero: es el contrato de
    reproducibilidad del modulo. Las desviaciones gaussianas se sacan de una
    normal tipica multiplicada por su sigma, y no de `normal(0, sigma)`, para que
    un sigma de cero consuma exactamente igual que cualquier otro.
    """
    falla = generador.random() < perfil.probabilidad_de_fallo
    es_mala = generador.random() < perfil.probabilidad_de_nota_mala
    desvio = DESVIOS_DE_NOTA_MALA[int(generador.integers(0, len(DESVIOS_DE_NOTA_MALA)))]
    trastea = generador.random() < perfil.probabilidad_de_trasteo
    desfase_s = perfil.desfase_medio_s + generador.normal() * perfil.desviacion_desfase_s
    cents = generador.normal() * perfil.cents_de_desafinacion
    fuerza = perfil.fuerza_media + generador.normal() * perfil.desviacion_fuerza

    if falla:
        return None

    midi = nota.midi + desvio if es_mala else nota.midi
    # El instante no puede caer antes del comienzo del audio: un desfase negativo
    # grande en la primera nota de la primera vuelta se queda en el borde. Es la
    # unica vez que el gemelo recorta un sorteo, y recortar la verdad es mejor que
    # publicar un evento que suena fuera del buffer.
    instante_s = max(
        0.0,
        inicio_vuelta_s
        + pulsos_a_segundos(nota.inicio_pulsos - inicio_tramo, pieza.tempo) / factor_tempo
        + desfase_s,
    )
    duracion_s = max(
        duracion_de_la_nota_s(
            figura_s=pulsos_a_segundos(nota.duracion_pulsos, pieza.tempo) / factor_tempo,
            hueco_s=pulsos_a_segundos(hueco_pulsos, pieza.tempo) / factor_tempo,
            sustain=perfil.sustain,
        ),
        _duracion_minima_s(midi + cents / 100.0, frecuencia_muestreo),
    )

    evento = EventoTocado(
        indice_pretendido=indice,
        midi=midi,
        instante_s=instante_s,
        duracion_s=duracion_s,
        cents=cents,
        trasteada=trastea,
    )
    return _Pulsacion(
        evento=evento,
        fuerza=float(np.clip(fuerza, 0.05, 1.0)),
        trasteo=TRASTEO_DE_LA_NOTA_SUCIA if trastea else 0.0,
        semilla=(
            semilla
            + PASO_DE_SEMILLA * (puesto + 1)
            + PASO_DE_SEMILLA_POR_VUELTA * vuelta
        ),
    )


def _duracion_minima_s(midi: float, frecuencia_muestreo: int) -> float:
    """Lo menos que puede sonar una nota: una vuelta del anillo de la cuerda.

    `cuerda_pulsada` rechaza una duracion que no llegue a un periodo de la nota,
    porque por debajo de eso el anillo no da ni una vuelta y lo que sale es ruido
    sin altura. En vez de dejar salir ese error, el interprete ALARGA la nota
    hasta el minimo, y lo alarga en la VERDAD y no solo en el audio, para que
    `EventoTocado.duracion_s` siga diciendo exactamente lo que suena.

    Es tambien lo que hace una cuerda de verdad: no se puede pulsar durante menos
    de un periodo. El minimo es diminuto -12 ms en el E2, 2 ms en el C5- y solo lo
    roza una figura absurda a un tempo absurdo (una negra pegada a la siguiente
    por debajo de los 14 ms son mas de 4000 pulsos por minuto), asi que en la
    practica no alarga nada y el invariante de no solapar aguanta.
    """
    periodo = frecuencia_muestreo / midi_a_frecuencia(midi)
    return (periodo + 2.0) / frecuencia_muestreo


def _generar(
    pulsaciones: list[_Pulsacion], total_s: float, frecuencia_muestreo: int
) -> np.ndarray:
    """Recorre la verdad ya escrita y suma una cuerda pulsada por evento.

    El buffer se dimensiona desde la duracion total calculada y las colas que
    sobresalen se recortan al final: una nota con `sustain` alto al borde del
    tramo suena lo que quepa, igual que si la pasada se acabara.
    """
    muestras = np.zeros(int(round(total_s * frecuencia_muestreo)), dtype=np.float32)
    for pulsacion in pulsaciones:
        evento = pulsacion.evento
        onda = cuerda_pulsada(
            # La altura de verdad lleva los cents dentro: `cuerda_pulsada` solo
            # usa `midi` para una cuenta aritmetica, asi que una altura
            # fraccionaria vale y es la unica forma de que la desafinacion este
            # en el AUDIO y no solo en el campo `cents`.
            midi=evento.midi + evento.cents / 100.0,
            duracion_s=evento.duracion_s,
            frecuencia_muestreo=frecuencia_muestreo,
            fuerza=pulsacion.fuerza,
            trasteo=pulsacion.trasteo,
            semilla=pulsacion.semilla,
        )
        desde = int(evento.instante_s * frecuencia_muestreo)
        if desde >= muestras.size:
            continue
        hasta = min(desde + onda.size, muestras.size)
        muestras[desde:hasta] += onda[: hasta - desde]
    # Dos colas que se solapan suman, y con `sustain` alto la suma se pasa de la
    # escala completa (medido: 1,12 con `CAOS`). Se recorta porque es lo que hace
    # la tarjeta de sonido de verdad: por encima de 1,0 no hay nada que entregar,
    # y un gemelo que entregue 1,12 esta metiendo por el cable una senal que el
    # cable no podria traer. Son unas pocas muestras por interpretacion.
    return np.clip(muestras, -1.0, 1.0, out=muestras)
