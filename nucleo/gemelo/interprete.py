"""El guitarrista sintetico: convierte una `Pieza` en audio y en su propia verdad.

La regla que ordena todo este modulo es que **la verdad se escribe antes que el
sonido**. `interpretar` construye primero la tupla completa de `EventoTocado`
-que nota suena, cuando, cuanto, con cuantos cents de desviacion y si roza el
traste- y solo despues recorre esa tupla generando muestras. Nunca al reves: si
la verdad se dedujera del audio, el gemelo estaria preguntandole al detector de
tono que es lo que paso, y entonces no verificaria nada, se daria la razon.

Todo el azar sale de un unico `numpy.random.default_rng(semilla)` y **el orden en
que se consume es parte del contrato**: por cada nota del tramo, en orden y
CONTANDO TODAS LAS CUERDAS DE CADA ACORDE, fallo -> nota mala -> trasteo ->
desfase -> desafinacion -> fuerza. Se consume
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
from nucleo.gemelo.cuerda import cuerda_pulsada, duracion_minima_s
from nucleo.gemelo.perfiles import PerfilDeDestreza
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

# Cuanto separa dos cuerdas consecutivas del mismo rasgueo.
#
# Un acorde no suena en un instante: la mano barre las cuerdas de la mas grave a
# la mas aguda y cada una entra un poco despues que la anterior. Ocho
# milisegundos por cuerda son 40 ms de barrido en un acorde de seis, que es un
# rasgueo normal (los rasgueos de verdad van de 10 a 30 ms entre cuerdas segun el
# brio, y aqui se toma el borde rapido).
#
# EL TECHO NO ES ESTETICA. `CUADROS_PARA_NOTA_ESTABLE = 3` a 21 ms de analisis son
# 63 ms: un barrido mas largo que eso deja de ser UN ataque para el detector
# monofonico y el carril veria dos pulsaciones donde la mano hizo un gesto. 40 ms
# caben con margen; subir esta constante obliga a volver a mirar esa de alla.
DESFASE_DE_RASGUEO_S = 0.008

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

    Y LLEVA DENTRO LOS ARGUMENTOS CON QUE SE TOCO -el tramo, el factor de tempo,
    las vueltas y la cuenta atras-, porque sin ellos `juzgar` no puede traducir
    del eje del audio al del cabezal. El cabezal de una pasada que estudia del
    compas 2 al 2 NO arranca en cero: arranca en el instante escrito de ese
    compas, que es `pulsos_a_segundos(inicio_del_tramo) / factor_tempo`. Medido
    con el tramo 2-2 de la escala: los reportes de la vuelta 1 caen en 2,6 s
    mientras los ataques estan a 0,128 s del audio, y un veredicto que no supiera
    el tramo daba las cuatro notas por perdidas sin poder decir por que. Las
    secciones de una cancion casi nunca empiezan en el compas 1, asi que esto es
    el caso normal y no un borde.

    Los valores por omision son los mismos que los de `interpretar`, para que una
    interpretacion armada a mano -un buffer de silencio, por ejemplo- no tenga que
    repetirlos.
    """

    pieza: Pieza
    muestras: np.ndarray
    eventos: tuple[EventoTocado, ...]
    frecuencia_muestreo: int
    duracion_s: float
    silencio_de_cabecera_s: float
    primer_compas: int = 1
    ultimo_compas: int | None = None
    factor_tempo: float = 1.0
    repeticiones: int = 1
    segundos_de_cuenta_atras: float = 0.0


@dataclass(frozen=True)
class _Escrita:
    """Una nota del tramo lista para sortear, con su sitio dentro del rasgueo.

    `puesto_en_el_grupo` es 0 para la cuerda mas grave del acorde y crece hacia la
    mas aguda; una nota suelta es un grupo de una y siempre vale 0. De ese numero
    salen las dos cosas que hacen de un acorde un gesto y no un monton de notas:
    cuanto se retrasa la cuerda en el barrido, y quien sortea el desfase que todas
    heredan.
    """

    indice: int
    nota: NotaEnPieza
    hueco_pulsos: float
    puesto_en_el_grupo: int


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


@dataclass(frozen=True)
class _Sorteo:
    """Lo que sale de sortear una nota: su pulsacion, si sono, y su desfase.

    El desfase viaja FUERA de la pulsacion porque lo heredan las demas cuerdas del
    acorde y la cuerda grave puede fallarse: guardado dentro de un `None`, una
    sexta muteada desharia el barrido de las cinco que si suenan.
    """

    pulsacion: _Pulsacion | None
    desfase_s: float


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
        pieza: la pieza escrita. Los acordes se rasguean enteros, cuerda a
            cuerda (ver `_pulsaciones_escritas`).
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
        # El desfase del gesto en curso: lo sortea la cuerda mas grave del acorde
        # y lo heredan las demas. Arranca a cero porque la primera nota de la
        # vuelta es cabeza de grupo y no lo mira.
        desfase_del_grupo_s = 0.0
        for puesto, escrita in enumerate(a_tocar):
            sorteo = _sortear_pulsacion(
                escrita=escrita,
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
                desfase_del_grupo_s=(
                    None if escrita.puesto_en_el_grupo == 0 else desfase_del_grupo_s
                ),
            )
            desfase_del_grupo_s = sorteo.desfase_s
            if sorteo.pulsacion is not None:
                pulsaciones.append(sorteo.pulsacion)

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
        primer_compas=primer_compas,
        # El tramo se guarda YA RESUELTO: `ultimo` es el tope de la pieza cuando
        # llega `None`, y asi quien lea la interpretacion no tiene que volver a
        # resolverlo (ni equivocarse al resolverlo) para saber donde acababa.
        ultimo_compas=ultimo,
        factor_tempo=factor_tempo,
        repeticiones=repeticiones,
        segundos_de_cuenta_atras=segundos_de_cuenta_atras,
    )


def _pulsaciones_escritas(
    pieza: Pieza, inicio_tramo: float, fin_tramo: float
) -> tuple[_Escrita, ...]:
    """Las notas del tramo, con su hueco al grupo siguiente y su sitio en el rasgueo.

    Las notas que comparten `inicio_pulsos` -eso es un acorde- SE TOCAN TODAS, de
    la mas grave a la mas aguda y separadas por `DESFASE_DE_RASGUEO_S`, porque un
    acorde es un barrido de la mano y no un monton de notas simultaneas.

    Hasta la etapa 2b este modulo se quedaba la cuerda mas grave y lo justificaba
    por escrito: «el detector de tono de produccion es monofonico y el gemelo no
    finge polifonia». Era verdad mientras el carril no sabia cobrar mas que una
    nota por ataque. Ya no lo es: `nucleo.piezas.seguimiento` cobra el resto del
    acorde por PRESENCIA contra la ventana cruda, y un gemelo que rasgueara una
    sola cuerda no podria ejercitar ese camino -justamente la mitad nueva de la
    etapa- ni hacer que fallara cuando esta mal.

    El hueco es hasta el GRUPO siguiente y lo comparten todas las cuerdas del
    acorde: cuanto se deja sonar es del gesto, no de cada cuerda. El de la ultima
    nota del tramo llega hasta el final del tramo, no hasta la nota siguiente de
    la pieza: lo que viene despues no se va a tocar.
    """
    grupos: list[list[tuple[int, NotaEnPieza]]] = []
    for indice, nota in enumerate(pieza.notas):
        if not inicio_tramo <= nota.inicio_pulsos < fin_tramo:
            continue
        if grupos and grupos[-1][0][1].inicio_pulsos == nota.inicio_pulsos:
            grupos[-1].append((indice, nota))
            continue
        grupos.append([(indice, nota)])

    escritas: list[_Escrita] = []
    for puesto_del_grupo, grupo in enumerate(grupos):
        inicio = grupo[0][1].inicio_pulsos
        siguiente = (
            grupos[puesto_del_grupo + 1][0][1].inicio_pulsos
            if puesto_del_grupo + 1 < len(grupos)
            else fin_tramo
        )
        # De grave a aguda, que es el orden del rasgueo hacia abajo Y el orden en
        # que el generador consume sus sorteos: tiene que quedar fijado aqui y no
        # depender de en que orden la pieza escribio las cuerdas del acorde, o dos
        # ficheros con el mismo acorde darian dos interpretaciones distintas con la
        # misma semilla. El indice rompe el empate de dos cuerdas a la misma altura.
        for puesto, (indice, nota) in enumerate(
            sorted(grupo, key=lambda par: (par[1].midi, par[0]))
        ):
            escritas.append(
                _Escrita(
                    indice=indice,
                    nota=nota,
                    hueco_pulsos=siguiente - inicio,
                    puesto_en_el_grupo=puesto,
                )
            )
    return tuple(escritas)


def _sortear_pulsacion(
    escrita: _Escrita,
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
    desfase_del_grupo_s: float | None = None,
) -> _Sorteo:
    """Sortea una nota y devuelve su pulsacion -o ninguna, si se fallo- y su desfase.

    Los seis sorteos salen SIEMPRE y en este orden, aunque la nota se falle en el
    primero y aunque el perfil tenga la probabilidad a cero: es el contrato de
    reproducibilidad del modulo. Las desviaciones gaussianas se sacan de una
    normal tipica multiplicada por su sigma, y no de `normal(0, sigma)`, para que
    un sigma de cero consuma exactamente igual que cualquier otro.

    `desfase_del_grupo_s` es el desfase que ya sorteo la cuerda mas grave de este
    acorde, o `None` si esta nota es esa cuerda. EL DESFASE ES DEL GESTO: la mano
    derecha llega tarde o pronto UNA vez por rasgueo, no una por cuerda. Sorteado
    por cuerda, un acorde habria salido desparramado al azar y el barrido no se
    habria podido ni ver ni medir. El sorteo se consume igual en todas las cuerdas,
    que es el contrato del modulo: lo que se tira es el valor, no la tirada.

    Un fallo, en cambio, SI es de la cuerda: una cuerda que el dedo apaga sin
    querer es exactamente lo que le pasa a quien esta aprendiendo un acorde, y es
    el caso que la mitad por presencia tiene que saber nombrar.
    """
    nota = escrita.nota
    falla = generador.random() < perfil.probabilidad_de_fallo
    es_mala = generador.random() < perfil.probabilidad_de_nota_mala
    desvio = DESVIOS_DE_NOTA_MALA[int(generador.integers(0, len(DESVIOS_DE_NOTA_MALA)))]
    trastea = generador.random() < perfil.probabilidad_de_trasteo
    desfase_sorteado_s = (
        perfil.desfase_medio_s + generador.normal() * perfil.desviacion_desfase_s
    )
    cents = generador.normal() * perfil.cents_de_desafinacion
    fuerza = perfil.fuerza_media + generador.normal() * perfil.desviacion_fuerza

    desfase_s = (
        desfase_sorteado_s if desfase_del_grupo_s is None else desfase_del_grupo_s
    )
    if falla:
        return _Sorteo(pulsacion=None, desfase_s=desfase_s)

    midi = nota.midi + desvio if es_mala else nota.midi
    # El instante no puede caer antes del comienzo del audio: un desfase negativo
    # grande en la primera nota de la primera vuelta se queda en el borde. Es la
    # unica vez que el gemelo recorta un sorteo, y recortar la verdad es mejor que
    # publicar un evento que suena fuera del buffer.
    # EL BARRIDO NO SE ESTIRA CON EL TEMPO, a diferencia de todo lo demas de esta
    # cuenta: es la velocidad de la mano cruzando las cuerdas, no una figura
    # musical. Tocar la misma pieza al doble de lento no hace el rasgueo mas
    # lento, igual que no hace el dedo mas gordo.
    instante_s = max(
        0.0,
        inicio_vuelta_s
        + pulsos_a_segundos(nota.inicio_pulsos - inicio_tramo, pieza.tempo) / factor_tempo
        + desfase_s
        + escrita.puesto_en_el_grupo * DESFASE_DE_RASGUEO_S,
    )
    duracion_s = max(
        duracion_de_la_nota_s(
            figura_s=pulsos_a_segundos(nota.duracion_pulsos, pieza.tempo) / factor_tempo,
            hueco_s=pulsos_a_segundos(escrita.hueco_pulsos, pieza.tempo) / factor_tempo,
            sustain=perfil.sustain,
        ),
        duracion_minima_s(midi + cents / 100.0, frecuencia_muestreo),
    )

    evento = EventoTocado(
        indice_pretendido=escrita.indice,
        midi=midi,
        instante_s=instante_s,
        duracion_s=duracion_s,
        cents=cents,
        trasteada=trastea,
    )
    return _Sorteo(
        pulsacion=_Pulsacion(
            evento=evento,
            fuerza=float(np.clip(fuerza, 0.05, 1.0)),
            trasteo=TRASTEO_DE_LA_NOTA_SUCIA if trastea else 0.0,
            semilla=(
                semilla
                + PASO_DE_SEMILLA * (puesto + 1)
                + PASO_DE_SEMILLA_POR_VUELTA * vuelta
            ),
        ),
        desfase_s=desfase_s,
    )


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
