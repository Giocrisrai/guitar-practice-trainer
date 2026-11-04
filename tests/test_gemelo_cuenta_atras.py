"""LA CUENTA ATRAS, vista desde el audio. La prueba de la T8.

La revision final de la etapa 3c encontro que la cuenta atras moria con el primer
cuadro de audio: el servidor congelaba su espejo del reloj con `colocar_en`, que
CANCELA la cuenta por contrato, y `_ultimo_cuadro` empieza a None, asi que el
primer `observar` tras `arrancar()` pasaba por ahi y se llevaba la cuenta que se
acababa de abrir -unos 21 ms despues de pulsar «empezar»-. Se arreglo con
`congelar_en`, la hermana que mueve el reloj sin opinar sobre la cuenta, y **nunca
se comprobo con audio entrando de verdad**. Este archivo es esa comprobacion.

**EL ARREGLO DE LA 3c AGUANTA.** Las cuatro pruebas que el brief pide pasaron sin
tocar una linea del nucleo. Medido con `escala_de_ocho_notas()`, `PERFECTO`,
semilla 0 y el salto de produccion (21 ms): en el cuadro 1 la cuenta sigue entera
-2,400 s de 2,400- y el reloj esta clavado en el inicio del tramo.

**TODOS los numeros de este archivo estan MEDIDOS**, no elegidos, sobre esa misma
configuracion. Si uno se queda corto, la respuesta no es ensancharlo: es mirar por
que la cadena cambio. El margen de las aserciones de tiempo es `MARGEN_MS`, menos
de un cuadro de analisis, igual que en `test_gemelo_oraculo.py` y
`test_gemelo_bucle.py`: ni un cuadro de deriva puede pasar desapercibido.

**EL ARRASTRE DEL BUCLE CON CUENTA ATRAS: ENCONTRADO AQUI Y ARREGLADO AQUI.** La
primera version de este archivo lo dejo en `xfail(strict=True)`; hoy las pruebas
son verdes y el `xfail` se ha ido. Lo que habia, medido con ocho vueltas de un
interprete PERFECTO:

    desfase medio por vuelta   antes  -7,9 / -44,6 / -89,3 / -123,4 / -162,7 /
                                      -199,5 / -231,0 ms   (37 ms por vuelta)
                              ahora  +24,8 / +27,8 / +23,0 / +28,6 / -26,2 /
                                      +29,3 / +37,6 / +32,7
    limpias por vuelta         antes  8 / 8 / 1 / 1 / 1 / 1 / 1
                              ahora  8 / 8 / 8 / 8 / 7 / 8 / 7 / 7
    vueltas cerradas de ocho   antes  7        ahora  8

Eran **las dos causas que la T7 le quito a la vuelta del bucle, volviendo por el
camino de la cuenta atras**, y las dos se arreglan donde estaban:

1. *El exceso del cruce se tiraba.* `_dar_la_vuelta` conserva el exceso con que el
   reloj cruzo el final del tramo, pero el primer cuadro de la cuenta clavaba el
   reloj en el inicio y se lo llevaba por delante (~15 ms). Ahora el exceso se le
   DEBITA A LA CUENTA, que es quien gasta ese tiempo: la cuenta empieza en la
   frontera y no en el cuadro que se entero.
2. *El cuadro que agotaba la cuenta se congelaba.* Ese cuadro volvia con el reloj
   en el inicio y la correspondencia sin fijar, asi que el reloj no arrancaba
   hasta el cuadro siguiente: 21 ms por vuelta. Ahora lo que sobra del cuadro
   -`delta` menos lo que le quedaba a la cuenta- se le entrega al reloj en ese
   mismo cuadro, y la correspondencia la escribe el `procesar` de abajo desde ahi.

**NO SE TOCO NINGUN CONTRATO**: el salto del final de la cuenta es ORDINARIO -sin
frontera ni correspondencia-, asi que sigue descartando lo que estuviera en vuelo
y sigue poniendo el origen del analisis en ese cuadro, que es literalmente
«durante la cuenta atras no se cobra nada». La maquinaria del salto continuo de la
T7 no hacia falta aqui, y por eso no se uso.

La prueba que lo sujeta por arriba es
`test_el_cabezal_de_cada_vuelta_es_el_reloj_del_analisis_menos_la_cuenta`: con la
cuenta agotada, el cabezal de la vuelta `v` es `t - (v * cuenta + (v-1) * tramo)`
**al microsegundo, en los 1828 cuadros de ocho vueltas**. Un arrastre no se puede
esconder de eso.

**LO QUE SE MIDIO DEL DEFECTO CONOCIDO DE LA FRONTERA.**
`tests/test_gemelo_bucle.py` dejo anotado, como anterior a la T7 y abierto, que
«con cuenta atras la nota de la frontera se pierde igual, porque mientras la
cuenta dura los cuadros no llegan al seguidor». Eso sigue siendo verdad del
mecanismo -la cuenta no le da los cuadros al seguidor, y eso no lo cambia el
arreglo del arrastre- pero **no muerde sobre el instrumento de la etapa**: la
ultima nota del tramo se ataca 600 ms antes del final -una nota por pulso a 100
ppm- y la cadena publica su ataque unos 152 ms despues, con la vuelta todavia
abierta. Para que muerda haria falta una nota atacada a menos de ~150 ms del final
del tramo, y las piezas que se armaron para provocarlo chocaron con otro limite
del detector antes de llegar a este -dos ataques a 150 ms uno del otro en la barra
de compas, o una figura tan corta que no se resuelve-, asi que **no es afirmable
con esta cadena y no se inscribe un `xfail` que no podria fallar por su motivo**.

Lo que SI se pierde en ocho vueltas es UNA nota de 64, la `(5, 7)`, y no es la
frontera: es el error de OCTAVA del detector de tono que
`test_gemelo_bucle.py::test_las_ocho_vueltas_siguen_sin_arrastre` ya tiene
inscrito **con el mismo numero, la misma vuelta y el mismo indice** en la
configuracion SIN cuenta atras. Que las dos configuraciones pierdan exactamente la
misma nota es el dato: el defecto es del detector y es independiente de la cuenta.
Antes del arreglo del arrastre esa nota NO se perdia con cuenta atras, y tampoco
era merito de nadie: el arrastre mantenia el cabezal por detras del audio y le
ensanchaba el margen. Estaba avisado en el informe de esta tarea.
"""

import dataclasses

import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import VENTANA_ATAQUE_COMO_ONSET_S
from nucleo.gemelo.cadena import RegistroDeLaCadena, pasar_por_la_cadena
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.gemelo.veredicto import Veredicto, juzgar
from nucleo.piezas.compases import pulsos_por_compas
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import (
    EstadoEstudio,
    InformeDePasada,
    PlanDePasada,
    SesionDeEstudio,
)
from nucleo.piezas.modelo import pulsos_a_segundos

# Las notas de `escala_de_ocho_notas()`: ocho, ninguna repetida y ningun acorde.
NOTAS = 8

# Lo que dura el tramo entero de esa pieza al tempo escrito, en segundos de la
# pasada: dos compases de 4/4 a 100 ppm.
TRAMO_S = 4.8

# Lo que se le concede a un tiempo medido antes de llamarlo otra cosa, en ms. Es
# MENOS de un cuadro de analisis (21 ms), igual que en el oraculo y en el bucle.
MARGEN_MS = 15.0

# Lo que la cuenta atras puede desviarse de su formula, en segundos. Es el 1 ms
# que el brief pide, y la medida sale clavada: la cuenta consume exactamente el
# reloj del analisis, asi que el error es de redondeo binario y no de cuadros.
TOLERANCIA_DE_LA_DURACION_S = 0.001

# Cuanto tarda la cadena en publicar el ataque de la primera nota de cada vuelta
# contado DESDE que la cuenta atras de esa vuelta se acaba, en ms, MEDIDO sobre
# cuatro vueltas: +182,3 / +185,3 / +188,3 / +191,3.
#
# Son el ancla de que la cuenta de CADA vuelta se agoto entera: si una se hubiera
# muerto, su primer ataque se habria cobrado antes de que la cuenta terminara y
# estos numeros saldrian negativos. Y van afirmados con su valor y no solo con el
# signo, porque un retraso de publicacion que se fuera a 500 ms seria otro defecto
# y con un `> 0` pelado no se veria.
RETRASOS_TRAS_LA_CUENTA_MS = (182.3, 185.3, 188.3, 191.3)

# El desfase medio de cada vuelta del bucle CON cuenta atras, en ms, MEDIDO.
# Antes de arreglar el arrastre eran -7,9 / -44,6 / -89,3 con cuatro vueltas (37 ms
# por vuelta, y la cuarta no llegaba a cerrarse) y bajaban hasta -231,0 en la
# octava. Sin cuenta atras los cuatro son +36,1 / +32,0 / +22,6 / +31,6 (ver
# `tests/test_gemelo_bucle.py`), y siguen siendo esos: el arreglo no toco ese
# camino.
#
# El -26,2 de la vuelta 5 de las ocho NO es arrastre: es el error de octava del
# detector de tono que pierde la nota (5, 7), el mismo que la configuracion sin
# cuenta atras tiene inscrito en esa misma vuelta (alli firma -11,9).
DESFASES_CON_CUENTA_POR_VUELTA_MS = (24.8, 27.8, 23.0, 28.6)
DESFASES_CON_CUENTA_EN_OCHO_VUELTAS_MS = (
    24.8, 27.8, 23.0, 28.6, -26.2, 29.3, 37.6, 32.7,
)

# Las limpias de cada vuelta con cuenta atras, ocho vueltas, MEDIDAS. Antes del
# arreglo del arrastre: 8 / 8 / 1 / 1 / 1 / 1 / 1 -y solo siete vueltas cerradas-.
# El 7 de la vuelta 5 es el error de octava; los de la 7 y la 8, el temblor del
# onset que el oraculo tiene en `xfail`.
LIMPIAS_CON_CUENTA_EN_OCHO_VUELTAS = (8, 8, 8, 8, 7, 8, 7, 7)

# La nota que el detector pierde por un error de OCTAVA en la vuelta 5, con y sin
# cuenta atras. Ver `test_gemelo_bucle.py::test_las_ocho_vueltas_siguen_sin_arrastre`.
PERDIDA_POR_EL_ERROR_DE_OCTAVA = (5, 7)

# Lo mas que pueden separarse dos vueltas cualesquiera SIN que haya arrastre: un
# cuadro de analisis, el mismo numero que `test_gemelo_bucle.py` inscribe.
RECORRIDO_SIN_ARRASTRE_MS = 21.0


class ConductorQueAnota:
    """Envuelve al conductor DE VERDAD y anota el estado de cada cuadro.

    No sustituye a nadie: `mirar`, `observar` y `fijar_la_mirada` van al conductor
    de produccion y lo que esta clase guarda es lo que ese conductor devolvio. Es
    la unica forma de ver la cuenta atras CUADRO A CUADRO sin reimplementar el
    bucle de `pasar_por_la_cadena` en una prueba, que seria medir una copia
    paralela de la cadena en vez de la cadena.

    Es la hermana de `AnalizadorEspia` de `tests/test_gemelo_cadena.py`, con el
    mismo oficio y por el mismo motivo.
    """

    def __init__(self, real: ConductorDeEstudio) -> None:
        self._real = real
        # `(instante_analisis, EstadoEstudio)` de cada cuadro, en orden.
        self.cuadros: list[tuple[float, EstadoEstudio]] = []

    @property
    def estudio(self) -> SesionDeEstudio:
        return self._real.estudio

    @property
    def historial(self):
        return self._real.historial

    @property
    def vueltas_cerradas(self) -> tuple[InformeDePasada, ...]:
        return self._real.vueltas_cerradas

    def fijar_la_mirada(self, ahora: float) -> None:
        self._real.fijar_la_mirada(ahora)

    def mirar(self, ahora: float, senal_ausente: bool) -> EstadoEstudio:
        return self._real.mirar(ahora, senal_ausente)

    def observar(
        self, resultado: ResultadoAnalisis, instante_analisis: float
    ) -> EstadoEstudio:
        estado = self._real.observar(resultado, instante_analisis)
        self.cuadros.append((instante_analisis, estado))
        return estado


def _cuenta_atras_s(pieza, compases_de_aviso: int, factor_tempo: float) -> float:
    """Lo que dura la cuenta atras del plan, con los ayudantes de PRODUCCION.

    Es la misma cuenta que `SesionDeEstudio._segundos_de_cuenta_atras` hace, con
    los mismos ayudantes, y asi tiene que ser: la cuenta atras del plan y los
    `segundos_de_cuenta_atras` del gemelo tienen que ser la MISMA, que es la
    condicion de uso que `juzgar` declara y que no puede comprobar.
    """
    return (
        pulsos_a_segundos(pulsos_por_compas(pieza) * compases_de_aviso, pieza.tempo)
        / factor_tempo
    )


def _pasada_con_cuenta_atras(
    compases_de_aviso: int = 1,
    factor_tempo: float = 1.0,
    repeticiones: int = 1,
    en_bucle: bool = False,
    cuenta_en_el_audio: bool = True,
    segundos_de_audio: float | None = None,
) -> tuple[Veredicto, RegistroDeLaCadena, ConductorQueAnota, float, Interpretacion]:
    """Una pasada CON cuenta atras por la cadena, y las cuatro cosas que deja.

    El silencio de la cuenta atras va DENTRO del audio y antes de cada vuelta, la
    primera incluida (el de la primera vive dentro de `silencio_de_cabecera_s`),
    asi que el plan y la interpretacion llevan la misma cuenta por omision. Eso es
    lo que hace que los dos relojes se puedan comparar.

    `cuenta_en_el_audio=False` es la EXCEPCION a proposito, y solo la usa la
    prueba del interprete que toca durante la cuenta: el plan abre su cuenta y el
    audio no tiene silencio delante, asi que las notas suenan mientras la cuenta
    corre.

    `segundos_de_audio` recorta las MUESTRAS, que es como se simula que el audio
    se acaba antes -el alumno para- sin tocar las vueltas pedidas.

    `al_cambiar_repeticion=None` NO es un detalle: ese aviso es del servidor para
    rearrancar el metronomo, y el metronomo abre audio.
    """
    pieza = escala_de_ocho_notas()
    cuenta_s = _cuenta_atras_s(pieza, compases_de_aviso, factor_tempo)
    interpretacion = interpretar(
        pieza,
        PERFECTO,
        factor_tempo=factor_tempo,
        semilla=0,
        repeticiones=repeticiones,
        segundos_de_cuenta_atras=cuenta_s if cuenta_en_el_audio else 0.0,
    )
    if segundos_de_audio is not None:
        cuantas = int(round(segundos_de_audio * interpretacion.frecuencia_muestreo))
        interpretacion = dataclasses.replace(
            interpretacion, muestras=interpretacion.muestras[:cuantas]
        )
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(
            factor_tempo=factor_tempo,
            en_bucle=en_bucle,
            compases_de_cuenta_atras=compases_de_aviso,
        ),
    )
    estudio.arrancar()
    conductor = ConductorQueAnota(
        ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    )

    registro = pasar_por_la_cadena(interpretacion, conductor)
    return (
        juzgar(interpretacion, registro),
        registro,
        conductor,
        cuenta_s,
        interpretacion,
    )


def _suma(informe: InformeDePasada, contador: str) -> int:
    return sum(getattr(compas, contador) for compas in informe.compases)


def _desfase_medio_ms(informe: InformeDePasada) -> float:
    """El desfase medio de un informe, en ms, pesado por notas con desfase.

    `CompasDelInforme.desfase_medio_s` es la media DE ESE COMPAS, asi que la media
    de la vuelta no es la media de las medias: hay que pesar cada compas por
    cuantas notas suyas se clasificaron. Es el mismo ayudante que
    `tests/test_gemelo_bucle.py`, y tiene que medir lo mismo para que los dos
    archivos sean comparables: ahi esta la mitad del hallazgo del arrastre.
    """
    total = 0.0
    cuantas = 0
    for compas in informe.compases:
        if compas.desfase_medio_s is None:
            continue
        con_desfase = compas.a_tiempo + compas.pronto + compas.tarde
        total += compas.desfase_medio_s * con_desfase
        cuantas += con_desfase
    assert cuantas > 0, "un informe sin una sola nota clasificada no tiene desfase"
    return total / cuantas * 1000.0


def _primer_cuadro_con_cobro(conductor: ConductorQueAnota) -> dict[int, float]:
    """El instante del ANALISIS en que cada vuelta cobro su primera nota.

    Se lee de los cuadros y no de los reportes porque lo que se quiere fechar es
    el CUADRO: `ReporteDeLaCadena` lleva el reloj de la pasada -el cabezal-, que
    durante la cuenta atras esta congelado y no sirve para decir cuando acabo la
    cuenta.
    """
    primeros: dict[int, float] = {}
    for instante, estado in conductor.cuadros:
        if estado.carril.tocadas and estado.repeticion not in primeros:
            primeros[estado.repeticion] = instante
    return primeros


def test_la_cuenta_atras_sobrevive_al_primer_cuadro_de_audio():
    """**LA PRUEBA DE LA 3c, con audio entrando de verdad.** Y aguanta.

    El primer cuadro de una pasada entra en `ConductorDeEstudio.observar` con
    `_ultimo_cuadro` todavia a None, asi que `_sin_cuadros` es verdad y el
    conductor le recoloca el reloj al estudio antes de darle de comer. Esa
    recolocacion es la que mataba la cuenta atras cuando se hacia con
    `colocar_en`, que la cancela por contrato.

    Medido: en el cuadro 1 la cuenta sigue ENTERA -2,400 s de 2,400- y el reloj
    esta en el inicio del tramo. Y sigue entera en los tres primeros cuadros, no
    por casualidad: sus ventanas acaban dentro de la cabecera tecnica del gemelo,
    asi que la cadena les da el instante cero y no hay tiempo que descontar.

    Las tres aserciones hacen falta:

    * la cuenta esta entera en el cuadro 1, que es el defecto de la 3c;
    * el reloj esta en el inicio, porque una cuenta viva con el cabezal corriendo
      seria media cuenta;
    * y la cuenta NO esta congelada: en el cuadro en que el reloj del analisis
      empieza a correr ya ha descontado exactamente lo que el analisis avanzo. Sin
      esta tercera, un mutante que dejara la cuenta clavada para siempre pasaria
      las dos primeras.
    """
    _, _, conductor, cuenta_s, _ = _pasada_con_cuenta_atras(segundos_de_audio=0.5)

    assert conductor.cuadros, "sin un solo cuadro no hay nada que comprobar"
    instante_1, estado_1 = conductor.cuadros[0]
    assert instante_1 == 0.0, (
        "el primer cuadro de la cadena cae dentro de la cabecera tecnica y su "
        f"instante es cero; este llego en {instante_1}"
    )
    assert estado_1.cuenta_atras_restante_s == pytest.approx(cuenta_s, abs=1e-9), (
        f"la cuenta atras llego al primer cuadro con {estado_1.cuenta_atras_restante_s} s "
        f"de los {cuenta_s} que `arrancar()` abrio: el primer cuadro se la ha comido"
    )
    assert estado_1.carril.instante_s == 0.0, (
        "durante la cuenta atras el reloj se queda en el inicio del tramo, y este "
        f"esta en {estado_1.carril.instante_s} s"
    )

    for instante, estado in conductor.cuadros:
        assert estado.cuenta_atras_restante_s == pytest.approx(
            cuenta_s - instante, abs=1e-9
        ), (
            f"en el cuadro del instante {instante} s la cuenta lleva "
            f"{estado.cuenta_atras_restante_s} s y tendria que llevar "
            f"{cuenta_s - instante}: la cuenta no consume el reloj del analisis"
        )
        assert estado.carril.instante_s == 0.0


def test_durante_la_cuenta_atras_no_se_cobra_nada():
    """Un interprete que toca DURANTE la cuenta: ninguna nota entra en el informe.

    El plan abre su compas de aviso y el audio NO lleva silencio delante, asi que
    el guitarrista entra a tocar mientras la cuenta corre -lo que hace un alumno
    que no espera el click-. El audio se corta en 2,0 s, por debajo de los 2,4 de
    la cuenta, para que toda la pasada caiga dentro de ella.

    Medido: cuatro notas suenan en esos 2,0 s y la cadena no reporta NI UNA, el
    informe sale a cero en todos sus contadores y la cuenta sigue viva al acabar.
    El veredicto del gemelo las da por perdidas, y esta vez perdidas es lo
    correcto: no se tocaron en la pasada, se tocaron antes de que empezara.

    Las notas sonadas se afirman en cuatro y no «mas de cero»: si el interprete
    dejara de tocar ahi, un informe a cero no probaria nada y esta prueba se
    habria convertido en decoracion sin ponerse roja.
    """
    _, registro, conductor, cuenta_s, interpretacion = _pasada_con_cuenta_atras(
        cuenta_en_el_audio=False, segundos_de_audio=2.0
    )

    assert registro.reportes == (), (
        f"la cadena cobro {len(registro.reportes)} notas durante la cuenta atras: "
        "mientras la cuenta dura no se puede cobrar nada"
    )
    informe = conductor.estudio.informe
    for contador in ("acertadas", "a_tiempo", "pronto", "tarde", "limpias"):
        assert _suma(informe, contador) == 0, (
            f"el informe cuenta {_suma(informe, contador)} en '{contador}' de una "
            "pasada que no salio de la cuenta atras"
        )
    assert registro.estado_final.cuenta_atras_restante_s > 0, (
        "el audio se corta antes de que la cuenta acabe, asi que la cuenta tiene "
        "que seguir viva"
    )
    assert registro.estado_final.carril.instante_s == 0.0

    # Las cuatro notas que SI sonaron dentro de esos 2,0 s de audio: son las que
    # hacen que el informe a cero signifique algo. Se cuentan de los EVENTOS, que
    # son la verdad de lo que sono, y acotadas al audio que de verdad se metio.
    cuantas_sonaron = sum(
        1 for evento in interpretacion.eventos if evento.instante_s < 2.0
    )
    assert cuantas_sonaron == 4, (
        f"sonaron {cuantas_sonaron} notas dentro de la cuenta atras y se esperaban "
        "cuatro: con menos, un informe a cero no prueba nada"
    )
    assert cuenta_s == pytest.approx(2.4)


@pytest.mark.parametrize("factor_tempo", (1.0, 0.5), ids=("tempo escrito", "al 50%"))
def test_la_cuenta_atras_de_un_compas_dura_un_compas(factor_tempo):
    """La duracion de la cuenta, MEDIDA con audio, contra su formula.

    La formula es `pulsos_por_compas * 60 / (tempo * factor)` -un compas al tempo
    de la pasada- y la medida sale de los cuadros, no del campo: en cada cuadro,
    **lo que el reloj del analisis ya avanzo mas lo que la cuenta dice que le
    queda** es lo que la cuenta va a durar en total. Se comprueba en TODOS los
    cuadros en que la cuenta esta viva, con 1 ms de tolerancia.

    Medido: 2,400000000 s al tempo escrito y 4,800000000 al 50 %, clavados. La
    medida no tiene error de cuadro porque no se lee del cuadro en que la cuenta
    llega a cero -eso daria 21 ms de resolucion- sino de la suma, que es exacta.

    Los dos factores hacen falta: con uno solo, un mutante que se olvidara de
    dividir por el factor pasaria la prueba del tempo escrito, donde el factor es
    1 y no se ve.

    Y se afirma ademas que la cuenta SE ACABA, y en el cuadro que le toca: sin
    esto, una cuenta que no bajara nunca de su valor inicial cumpliria la suma.
    """
    esperada_s = pulsos_por_compas(escala_de_ocho_notas()) * 60.0 / (100.0 * factor_tempo)
    _, _, conductor, cuenta_s, _ = _pasada_con_cuenta_atras(
        factor_tempo=factor_tempo, segundos_de_audio=esperada_s + 0.5
    )
    assert cuenta_s == pytest.approx(esperada_s, abs=TOLERANCIA_DE_LA_DURACION_S)

    vivos = [
        (instante, estado)
        for instante, estado in conductor.cuadros
        if estado.cuenta_atras_restante_s > 0
    ]
    assert len(vivos) > 10, (
        f"solo {len(vivos)} cuadros con la cuenta viva: la medida necesita varios"
    )
    for instante, estado in vivos:
        medida_s = instante + estado.cuenta_atras_restante_s
        assert medida_s == pytest.approx(esperada_s, abs=TOLERANCIA_DE_LA_DURACION_S), (
            f"en el cuadro del instante {instante} s la cuenta mide {medida_s} s y "
            f"la formula dice {esperada_s}"
        )

    agotados = [
        instante
        for instante, estado in conductor.cuadros
        if estado.cuenta_atras_restante_s == 0.0
    ]
    assert agotados, "la cuenta atras no se acabo en toda la pasada"
    # El primer cuadro sin cuenta cae DESPUES de la duracion y a menos de un
    # cuadro de analisis de ella: es el primero que la cruza.
    assert esperada_s <= agotados[0] <= esperada_s + RECORRIDO_SIN_ARRASTRE_MS / 1000.0
    assert vivos[-1][0] < esperada_s


def test_la_cuenta_atras_de_cada_vuelta_tambien_sobrevive():
    """Con bucle, las CUATRO vueltas tienen su cuenta atras completa.

    `_dar_la_vuelta` abre una cuenta nueva en cada vuelta -la spec pide el compas
    de aviso antes de arrancar Y en cada repeticion-, y esa cuenta corre con los
    cuadros entrando, que es justo el camino que no se habia comprobado.

    Lo que se afirma es el instante en que cada vuelta cobra su PRIMERA nota,
    fechado en el reloj del analisis, contra el instante en que la cuenta de esa
    vuelta se acaba (`vuelta * cuenta + (vuelta - 1) * tramo`, que es la geometria
    del audio que el gemelo genero). Medido: +182,3 / +185,3 / +188,3 / +191,3 ms
    DESPUES de su cuenta, que es el retraso con que la cadena publica un ataque.
    Si una cuenta se hubiera muerto, su primera nota se habria cobrado antes de que
    la cuenta terminara y ese numero saldria negativo.

    Se afirma el valor y no solo el signo: con un `> 0` pelado, un retraso de
    publicacion que se fuera a medio segundo -otro defecto- no se veria.

    Y se afirma que el cabezal de ese primer cobro esta DENTRO DEL PRIMER PULSO
    del tramo: una cuenta atras que no congelara el reloj lo habria dejado
    corriendo durante los 2,4 s de silencio, y la nota se habria cobrado con el
    cabezal cerca del final del tramo (o fuera de el, con la vuelta ya dada).

    **LAS CUATRO VUELTAS SE CIERRAN, y antes del arreglo del arrastre solo tres.**
    No era una vuelta «que se queda abierta porque el audio se acaba»: era que el
    reloj iba 37 ms por vuelta por detras del audio y la cuarta vuelta no llegaba a
    cruzar el final del tramo antes de que las muestras se terminaran. Cuatro
    vueltas de audio son cuatro vueltas.
    """
    _, registro, conductor, cuenta_s, _ = _pasada_con_cuenta_atras(
        repeticiones=4, en_bucle=True
    )

    assert len(registro.vueltas) == 4, (
        "cuatro vueltas de audio cierran cuatro informes con el reloj sin "
        f"arrastre; estas cerraron {len(registro.vueltas)}"
    )
    assert [_suma(informe, "acertadas") for informe in registro.vueltas] == [NOTAS] * 4

    primeros = _primer_cuadro_con_cobro(conductor)
    assert sorted(primeros) == [1, 2, 3, 4], (
        f"las cuatro vueltas tienen que cobrar algo; cobraron {sorted(primeros)}"
    )
    for vuelta, inscrito_ms in enumerate(RETRASOS_TRAS_LA_CUENTA_MS, start=1):
        fin_de_su_cuenta_s = vuelta * cuenta_s + (vuelta - 1) * TRAMO_S
        retraso_ms = (primeros[vuelta] - fin_de_su_cuenta_s) * 1000.0
        assert retraso_ms > 0.0, (
            f"la vuelta {vuelta} cobro su primera nota {retraso_ms:+.1f} ms antes de "
            "que su cuenta atras acabara: la cuenta de esa vuelta se murio"
        )
        assert retraso_ms == pytest.approx(inscrito_ms, abs=MARGEN_MS), (
            f"la vuelta {vuelta} cobro su primera nota {retraso_ms:+.1f} ms tras su "
            f"cuenta y el suelo medido es {inscrito_ms:+.1f}"
        )

    # El cabezal de ese primer cobro, vuelta a vuelta: dentro del primer pulso del
    # tramo (0,6 s). Con la cuenta muerta el reloj habria corrido 2,4 s de silencio.
    un_pulso_s = 60.0 / 100.0
    for reporte in registro.reportes:
        if reporte.tocada.indice != 0:
            continue
        assert 0.0 < reporte.instante_pasada_s < un_pulso_s, (
            f"la vuelta {reporte.repeticion} cobro su primera nota con el cabezal en "
            f"{reporte.instante_pasada_s:.3f} s, fuera del primer pulso del tramo"
        )


def test_la_nota_de_la_frontera_no_se_pierde_con_cuenta_atras():
    """El defecto conocido de la frontera, MEDIDO con cuenta atras: no aparece.

    `tests/test_gemelo_bucle.py` lo dejo anotado como anterior a la T7 y abierto:
    «mientras la cuenta dura, el estudio no le da los cuadros al seguidor, asi que
    un ataque de la frontera que se resuelva ya dentro de la cuenta se pierde
    igual». Esto es su medida con audio: **ocho vueltas, ocho cerradas, 64 notas,
    y la unica que se pierde no es la de la frontera.**

    El mecanismo existe -durante la cuenta `procesar` vuelve antes de llamar al
    seguidor, asi que un onset sin resolver no se resuelve nunca- pero sobre el
    instrumento de la etapa no tiene donde morder: la ultima nota del tramo se
    ataca 600 ms antes del final (una nota por pulso a 100 ppm) y la cadena
    publica su ataque unos 152 ms despues, con la vuelta todavia abierta. Haria
    falta una nota atacada a menos de ~150 ms del final del tramo, y ese caso no
    es construible con esta cadena sin chocar antes con otro limite del detector.

    Por eso esto es una prueba VERDE con el numero medido y no un `xfail`: un
    `xfail(strict=True)` exige que la prueba falle, y esta no falla.

    **LA NOTA QUE SI SE PIERDE ES LA `(5, 7)`, Y ES OTRA COSA:** el error de
    OCTAVA del detector de tono -firma midi 77 donde sono un 65- que
    `test_gemelo_bucle.py::test_las_ocho_vueltas_siguen_sin_arrastre` tiene
    inscrito con **el mismo numero, la misma vuelta y el mismo indice** en la
    configuracion SIN cuenta atras. Que las dos pierdan exactamente la misma nota
    es el dato: el defecto es del detector y no de la cuenta ni del bucle.

    Y aparecio con el arreglo del arrastre, no antes: mientras el reloj iba por
    detras del audio, esa nota se salvaba por el margen que el propio arrastre le
    regalaba. El informe de esta tarea lo dejo avisado.

    Se afirma UNA perdida y la suya, no «pocas»: si aparece otra, no es este
    defecto conocido. `limpias` no se afirma aqui -lo hace la prueba del
    arrastre-, pero `acertadas` si, vuelta a vuelta, porque es donde se veria que
    la frontera se cae.
    """
    veredicto, registro, _, _, _ = _pasada_con_cuenta_atras(
        repeticiones=8, en_bucle=True
    )

    assert len(registro.vueltas) == 8
    assert [_suma(informe, "acertadas") for informe in registro.vueltas] == [
        NOTAS, NOTAS, NOTAS, NOTAS, NOTAS - 1, NOTAS, NOTAS, NOTAS
    ]
    assert veredicto.notas_tocadas == NOTAS * 8
    assert len(veredicto.perdidas) == 1, (
        f"se perdieron {len(veredicto.perdidas)} notas de 64: {veredicto.perdidas}"
    )
    assert veredicto.perdidas == (PERDIDA_POR_EL_ERROR_DE_OCTAVA,)
    assert veredicto.mal_adjudicadas == ()
    assert veredicto.excluidas == ()


def test_el_cabezal_de_cada_vuelta_es_el_reloj_del_analisis_menos_la_cuenta():
    """**LA PRUEBA DEL ARRASTRE POR ARRIBA.** El cabezal, al microsegundo.

    Es la afirmacion mas fuerte del archivo y la mas corta de explicar: con la
    cuenta atras ya agotada, el cabezal de la vuelta `v` tiene que valer
    exactamente el reloj del analisis menos lo que el audio lleva gastado en
    cuentas y vueltas anteriores,

        cabezal = t - (v * cuenta + (v - 1) * tramo)

    porque la cadena alinea el eje del cabezal con el final de la cabecera tecnica
    y el resto del audio es exactamente esa geometria. **Medido: desvio maximo
    0,000000 ms sobre los 1828 cuadros de ocho vueltas.**

    Un arrastre no se puede esconder de esto, y ahi esta su valor frente a las
    medias por vuelta: 37 ms por vuelta son 1,7 cuadros, y las medias hay que
    leerlas comparando vueltas, mientras que esto falla en el primer cuadro de la
    segunda vuelta. La tolerancia es de MICROsegundos y no de un cuadro porque no
    hay nada que redondear: el reloj del seguidor sale de una resta entre dos
    numeros exactos.

    Se cuentan los cuadros comprobados y se exige un suelo: sin eso, un filtro que
    dejara la lista vacia -o una cuenta que no se agotara nunca- daria la prueba
    por buena sin haber comparado un solo cuadro.
    """
    _, _, conductor, cuenta_s, _ = _pasada_con_cuenta_atras(
        repeticiones=8, en_bucle=True
    )

    comprobados = 0
    peor_ms = 0.0
    for instante, estado in conductor.cuadros:
        if estado.cuenta_atras_restante_s > 0:
            continue
        gastado_s = estado.repeticion * cuenta_s + (estado.repeticion - 1) * TRAMO_S
        esperado_s = instante - gastado_s
        if esperado_s < 0:
            # El cuadro en que la cuenta se agota puede dejar el reloj justo en el
            # inicio con el analisis todavia por debajo del reparto: no hay nada
            # que comparar ahi.
            continue
        comprobados += 1
        peor_ms = max(peor_ms, abs(estado.carril.instante_s - esperado_s) * 1000.0)

    assert comprobados > 1500, (
        f"solo {comprobados} cuadros comparados de los 1828 de ocho vueltas: el "
        "filtro se ha comido la prueba"
    )
    assert peor_ms < 0.001, (
        f"el cabezal se desvia hasta {peor_ms:.6f} ms de su sitio: el reloj del "
        "bucle con cuenta atras arrastra"
    )


def test_el_bucle_con_cuenta_atras_no_arrastra_el_reloj():
    """**LA PRUEBA DEL DEFECTO QUE ESTA TAREA ENCONTRO.** Estuvo roja; hoy no.

    El interprete es PERFECTO y no cambia nada entre vueltas, asi que si el
    desfase que la cadena firma cambia de una vuelta a otra, lo que se movio es el
    reloj y no el guitarrista. Es la misma afirmacion que
    `test_el_bucle_no_arrastra_el_reloj_entre_vueltas` hace SIN cuenta atras, con
    el mismo ayudante y el mismo margen de un cuadro, y por eso se pueden
    comparar.

    Medido con cuatro vueltas: `+24,8 / +27,8 / +23,0 / +28,6` ms, recorrido
    5,6 ms. **Antes del arreglo: `-7,9 / -44,6 / -89,3` -37 ms por vuelta,
    recorrido 81,4 ms, y la cuarta vuelta sin cerrar-.** Sin cuenta atras los
    cuatro numeros son `+36,1 / +32,0 / +22,6 / +31,6` y **no se han movido ni una
    decima** con el arreglo, que es la comprobacion de que no alcanzo mas de lo que
    debia.

    El signo tambien es parte del dato y por eso se afirma aparte: los desfases
    son POSITIVOS, o sea que la cadena publica tarde, que es latencia real del
    detector. Negativos serian el cabezal por DETRAS del audio -el alumno toca a
    tiempo y el carril le dice que se adelanta-, que es lo que el arrastre hacia
    desde la primera vuelta.

    Las aserciones son las del bucle sin cuenta y no se rebajan: el recorrido de
    las vueltas cabe en un cuadro, y cada vuelta cae en su numero medido con el
    margen de un cuadro -la cota POR ABAJO, sin la cual una cadena que dejara de
    retrasar pasaria la primera sin tocarla-.
    """
    _, registro, _, _, _ = _pasada_con_cuenta_atras(repeticiones=4, en_bucle=True)

    assert len(registro.vueltas) == 4
    desfases = [_desfase_medio_ms(informe) for informe in registro.vueltas]
    for vuelta, (medido, inscrito) in enumerate(
        zip(desfases, DESFASES_CON_CUENTA_POR_VUELTA_MS, strict=True), start=1
    ):
        assert medido == pytest.approx(inscrito, abs=MARGEN_MS), (
            f"la vuelta {vuelta} firma {medido:+.1f} ms y el numero medido es "
            f"{inscrito:+.1f}"
        )
    assert max(desfases) - min(desfases) <= RECORRIDO_SIN_ARRASTRE_MS, (
        f"las vueltas se reparten {max(desfases) - min(desfases):.1f} ms, mas de un "
        "cuadro de analisis: el reloj del bucle con cuenta atras arrastra"
    )
    assert all(desfase > 0.0 for desfase in desfases), (
        f"hay vueltas con desfase negativo ({desfases}): el cabezal se ha quedado "
        "por detras del audio"
    )
    assert max(abs(desfase) for desfase in desfases) < (
        VENTANA_ATAQUE_COMO_ONSET_S * 1000.0
    )
    assert [_suma(informe, "limpias") for informe in registro.vueltas] == [NOTAS] * 4, (
        "las cuatro vueltas tienen que salir limpias enteras: con el arrastre, la "
        "tercera bajaba a 1 de 8"
    )


def test_las_ocho_vueltas_con_cuenta_atras_siguen_sin_arrastre():
    """Ocho vueltas, que es donde el arrastre se veia a simple vista.

    Cuatro no bastan para esta afirmacion y por eso esta prueba existe aparte,
    igual que su hermana sin cuenta atras: con 37 ms por vuelta, la octava vuelta
    firmaba **-231,0 ms** y las limpias llevaban cinco vueltas en 1 de 8. Hoy la
    octava firma +32,7 y esta a 7,9 ms de la primera.

    Las limpias se afirman EXACTAS -`8/8/8/8/7/8/7/7`- y no con un suelo, porque
    los tres numeros que no son ocho tienen nombre: el 7 de la vuelta 5 es el error
    de octava del detector (la nota `(5, 7)`, la misma que sin cuenta atras) y los
    de la 7 y la 8 son el temblor del onset que el oraculo tiene en
    `xfail(strict=True)`. Antes del arreglo la lista era `8/8/1/1/1/1/1`, con siete
    vueltas y no ocho.

    El recorrido de las ocho NO se afirma como un cuadro, y se dice por que: la
    vuelta 5 firma -26,2 ms por ese error de octava -sin cuenta atras firma -11,9
    por lo mismo- y eso ensancha el recorrido a 63,8 ms sin que haya arrastre
    ninguno. Lo que se afirma en su lugar es mas fuerte que un recorrido: cada
    vuelta contra su numero medido con margen de un cuadro, y la octava contra la
    primera. La cota global del cabezal la pone
    `test_el_cabezal_de_cada_vuelta_es_el_reloj_del_analisis_menos_la_cuenta`, que
    no tiene que tolerar nada.
    """
    _, registro, _, _, _ = _pasada_con_cuenta_atras(repeticiones=8, en_bucle=True)

    assert len(registro.vueltas) == 8, (
        "ocho vueltas de audio cierran ocho informes con el reloj sin arrastre; "
        f"estas cerraron {len(registro.vueltas)}"
    )
    desfases = [_desfase_medio_ms(informe) for informe in registro.vueltas]
    for vuelta, (medido, inscrito) in enumerate(
        zip(desfases, DESFASES_CON_CUENTA_EN_OCHO_VUELTAS_MS, strict=True), start=1
    ):
        assert medido == pytest.approx(inscrito, abs=MARGEN_MS), (
            f"la vuelta {vuelta} firma {medido:+.1f} ms y el numero medido es "
            f"{inscrito:+.1f}"
        )
    assert abs(desfases[7] - desfases[0]) <= RECORRIDO_SIN_ARRASTRE_MS, (
        f"la vuelta 8 ({desfases[7]:+.1f} ms) se ha ido de la vuelta 1 "
        f"({desfases[0]:+.1f} ms)"
    )
    assert tuple(
        _suma(informe, "limpias") for informe in registro.vueltas
    ) == LIMPIAS_CON_CUENTA_EN_OCHO_VUELTAS
