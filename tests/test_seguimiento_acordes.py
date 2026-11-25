"""El carril cobrando acordes: el ataque abre la puerta, la presencia reparte.

La mitad monofonica no se prueba aqui -esta en `test_seguimiento_pieza.py`-: lo
que se prueba es la SEGUNDA mitad, la que cobra las cuerdas que no tienen ataque
propio porque el rasgueo fue uno solo (ver la spec de la 2b, §4.4.1).

Ni una espera real: el reloj de la pieza se coloca a mano y la ventana cruda la
da una funcion de prueba, no una tarjeta de sonido.
"""

import numpy as np

from nucleo.afinaciones import PERFILES_DE_FABRICA
from nucleo.analisis.acordes import VENTANA_ACORDES, DetectorAcordes
from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.musica import midi_a_frecuencia, nombre_de_midi
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from nucleo.piezas.seguimiento import SeguidorPieza

FS = 48000
GUITARRA = PERFILES_DE_FABRICA["guitarra_estandar"]

# Do mayor abierto (x32010). La mas grave, C3 (48), es la que se "rasguea" para
# que el detector monofonico tenga una altura que firmar.
DO_MAYOR = (48, 52, 55, 60, 64)


def cuerda(frecuencia: float, muestras: int, semilla: int) -> np.ndarray:
    """Una cuerda pulsada: ocho armonicos con decaimiento y fase al azar.

    Es la misma sintesis que `tests/test_acordes.py`, repetida a proposito en vez
    de importada: estas pruebas son de OTRA capa, y compartir el generador haria
    que un cambio pensado para el detector moviera sin avisar lo que aqui se da por
    audible.
    """
    generador = np.random.default_rng(semilla)
    t = np.arange(muestras) / FS
    onda = np.zeros_like(t)
    for h in range(1, 9):
        onda += (
            (1.0 / h**1.2)
            * np.exp(-t / (1.5 / h))
            * np.sin(2.0 * np.pi * frecuencia * h * t + generador.uniform(0.0, 2.0 * np.pi))
        )
    return onda


def rasgueo(midis, muestras: int = VENTANA_ACORDES) -> np.ndarray:
    mezcla = np.zeros(muestras)
    for indice, midi in enumerate(midis):
        mezcla += cuerda(midi_a_frecuencia(midi), muestras, semilla=indice)
    pico = float(np.max(np.abs(mezcla)))
    return mezcla / pico if pico > 0.0 else mezcla


def pieza_con_acorde(midis=DO_MAYOR, tempo=60) -> Pieza:
    """Un solo acorde en el pulso 0: cinco notas con el mismo `inicio_pulsos`."""
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=5 - i, traste=0, inicio_pulsos=0.0, duracion_pulsos=2.0)
        for i, m in enumerate(midis)
    )
    return Pieza(nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas)


def seguidor_con(pieza, ventana, **kwargs) -> SeguidorPieza:
    """Un seguidor con detector de acordes y una ventana cruda fija.

    `ventana` es lo que el proveedor devuelve siempre, o None para un proveedor
    que nunca tiene audio que dar.
    """
    return SeguidorPieza(
        pieza,
        detector_acordes=DetectorAcordes(GUITARRA, frecuencia_muestreo=FS),
        proveedor_de_muestras=lambda _n: ventana,
        **kwargs,
    )


def silencio() -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
        nota=None, cents=None, posiciones=(),
    )


def suena(midi, cents=0.0) -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="nota", frecuencia=midi_a_frecuencia(midi), confianza=0.9, nivel_db=-25.0,
        nota=nombre_de_midi(midi), cents=cents, posiciones=(),
    )


def rasguear(seguidor, midi_del_ataque, en=0.0, cuadros=12):
    """Coloca el reloj en `en` y da cuadros hasta que el detector firma el ataque.

    `cuadros` son los que se dan DESPUES del silencio. Doce es de sobra para que el
    ataque se firme y para que el grupo abierto se siga cobrando; bajarlo a uno
    sirve para mirar solo el cuadro del ataque, que es otra pregunta.
    """
    instante = en - 0.1
    seguidor.avanzar_a(instante)
    while instante < en:
        seguidor.procesar(silencio(), instante)
        instante += 0.021
    for _ in range(cuadros):
        seguidor.procesar(suena(midi_del_ataque), instante)
        instante += 0.021
    return seguidor.estado.tocadas


class TestLaPuertaDelAtaque:
    def test_sin_detector_de_acordes_solo_se_cobra_una_nota(self):
        """El comportamiento de antes de la tarea 8, que sigue siendo el defecto."""
        seguidor = SeguidorPieza(pieza_con_acorde())
        tocadas = rasguear(seguidor, 48)
        assert len(tocadas) == 1
        assert tocadas[0].por_presencia is False

    def test_con_detector_se_cobra_el_acorde_entero(self):
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        tocadas = rasguear(seguidor, 48)
        assert sorted(t.midi for t in tocadas) == sorted(DO_MAYOR)

    def test_sin_ataque_no_se_cobra_nada_por_mucho_que_suene_el_acorde(self):
        """La puerta: el detector monofonico autoriza y el de acordes reparte.

        La ventana cruda trae el acorde entero sonando, pero no llega un solo
        cuadro de analisis con nota, asi que no hay ataque que firmar. Sin esta
        puerta, los armonicos de un acorde vecino cobrarian uno que nadie rasgueo.
        """
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        instante = 0.0
        seguidor.avanzar_a(0.0)
        for _ in range(40):
            seguidor.procesar(silencio(), instante)
            instante += 0.021
        assert seguidor.estado.tocadas == ()

    def test_una_nota_suelta_no_pasa_por_el_detector_de_acordes(self):
        """Sin grupo no hay resto que cobrar, y el proveedor no se llega a llamar."""
        llamadas = []
        pieza = Pieza(
            nombre="p", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
            notas=(
                NotaEnPieza(midi=48, cuerda=5, traste=3, inicio_pulsos=0.0, duracion_pulsos=1.0),
                NotaEnPieza(midi=52, cuerda=4, traste=2, inicio_pulsos=1.0, duracion_pulsos=1.0),
            ),
        )

        def proveedor(n):
            llamadas.append(n)
            return rasgueo(DO_MAYOR)

        seguidor = SeguidorPieza(
            pieza,
            detector_acordes=DetectorAcordes(GUITARRA, frecuencia_muestreo=FS),
            proveedor_de_muestras=proveedor,
        )
        tocadas = rasguear(seguidor, 48)
        assert len(tocadas) == 1
        assert llamadas == []

    def test_el_proveedor_pide_la_ventana_del_detector(self):
        pedidas = []
        seguidor = SeguidorPieza(
            pieza_con_acorde(),
            detector_acordes=DetectorAcordes(GUITARRA, frecuencia_muestreo=FS),
            proveedor_de_muestras=lambda n: pedidas.append(n) or rasgueo(DO_MAYOR),
        )
        rasguear(seguidor, 48)
        assert pedidas and set(pedidas) == {VENTANA_ACORDES}


class TestElAtaqueQueSeLeeMal:
    """Un rasgueo no es una altura: el detector monofonico lee UNA, y en un
    acorde puede no ser ninguna de las escritas.

    Pasa con un parcial fuerte o con una diferencia entre dos cuerdas. Sin esto,
    `_adjudicar` cobraba la nota mas grave del grupo con `acertada=False` -ningun
    MIDI coincidia, asi que gana la mas cercana en el tiempo, y en un acorde todas
    empatan- y luego la presencia ya no podia revisarla porque estaba cobrada. El
    informe lo leia como «3 de 4»: un error del alumno donde solo hubo una lectura
    de altura mala.
    """

    def test_la_presencia_corrige_el_veredicto_del_ataque(self):
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        # 72 (C5) no es ninguna nota del Do abierto: es el parcial que se leyo.
        tocadas = rasguear(seguidor, 72)

        assert len(tocadas) == len(DO_MAYOR)
        assert all(t.acertada for t in tocadas), "la presencia demuestra que sonaron"

    def test_pero_conserva_el_tiempo_que_si_se_midio(self):
        """El rasgueo tuvo un ataque y su instante es real: lo que no vale es la
        altura. Asi que el desfase y la clasificacion se quedan, y los cents no:
        median la desviacion del parcial leido, no la de esta cuerda."""
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        tocadas = rasguear(seguidor, 72)

        con_ataque = [t for t in tocadas if not t.por_presencia]
        assert len(con_ataque) == 1
        assert con_ataque[0].desfase_s is not None
        assert con_ataque[0].clasificacion is not None
        assert con_ataque[0].cents is None
        assert con_ataque[0].afinada is None

    def test_si_el_acorde_no_suena_el_fallo_se_queda(self):
        """La correccion no es una amnistia: necesita que la presencia lo
        confirme. Con la ventana en silencio, el veredicto malo se mantiene."""
        seguidor = seguidor_con(pieza_con_acorde(), np.zeros(VENTANA_ACORDES))
        tocadas = rasguear(seguidor, 72)

        assert len(tocadas) == 1
        assert tocadas[0].acertada is False


class TestQueSePublica:
    def test_la_nota_del_ataque_conserva_su_desfase_y_sus_cents(self):
        """La mitad monofonica no se toca: el ataque sigue midiendo el tiempo."""
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        tocadas = rasguear(seguidor, 48)
        ataque = [t for t in tocadas if not t.por_presencia]
        assert len(ataque) == 1
        assert ataque[0].midi == 48
        assert ataque[0].desfase_s is not None
        assert ataque[0].clasificacion is not None
        assert ataque[0].cents is not None

    def test_las_cuerdas_sin_ataque_propio_no_inventan_tiempo_ni_afinacion(self):
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        tocadas = rasguear(seguidor, 48)
        presencia = [t for t in tocadas if t.por_presencia]
        assert len(presencia) == 4
        for nota in presencia:
            assert nota.desfase_s is None
            assert nota.clasificacion is None
            assert nota.cents is None
            assert nota.afinada is None
            assert nota.acertada is True

    def test_el_campo_viaja_en_el_diccionario_del_websocket(self):
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        rasguear(seguidor, 48)
        datos = seguidor.estado.a_dict()["tocadas"]
        assert {d["por_presencia"] for d in datos} == {True, False}

    def test_una_nota_suelta_sale_con_el_campo_en_falso(self):
        seguidor = SeguidorPieza(pieza_con_acorde())
        rasguear(seguidor, 48)
        assert seguidor.estado.a_dict()["tocadas"][0]["por_presencia"] is False


class TestLoQueNoSuena:
    def test_la_cuerda_muda_se_queda_sin_cobrar(self):
        """Con E4 (64) muda, el acorde se cobra menos esa: el carril la pinta sin marca."""
        suenan = tuple(m for m in DO_MAYOR if m != 64)
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(suenan))
        tocadas = rasguear(seguidor, 48)
        assert 64 not in {t.midi for t in tocadas}
        assert sorted(t.midi for t in tocadas) == sorted(suenan)

    def test_el_silencio_en_la_ventana_no_cobra_presencias(self):
        """Ataque firmado pero ventana muda: no se midio nada, no se da nada por bueno."""
        seguidor = seguidor_con(pieza_con_acorde(), np.zeros(VENTANA_ACORDES))
        tocadas = rasguear(seguidor, 48)
        assert [t.por_presencia for t in tocadas] == [False]

    def test_sin_ventana_que_dar_el_carril_sigue_siendo_monofonico(self):
        """Arranque de la captura: el proveedor devuelve None y no se cae nada."""
        seguidor = seguidor_con(pieza_con_acorde(), None)
        tocadas = rasguear(seguidor, 48)
        assert len(tocadas) == 1
        assert tocadas[0].por_presencia is False

    def test_el_grupo_abierto_espera_a_que_haya_ventana_con_que_medir(self):
        """Un acorde que no se pudo medir al principio se cobra cuando se puede.

        El detector exige el 90 % de la ventana (eso lo vigila
        `tests/test_acordes.py`), asi que con media ventana el primer cuadro no
        juzga nada. Pero su bufer es CIRCULAR: dos medias ventanas seguidas lo
        llenan, y el grupo -que sigue abierto- se cobra en cuanto hay con que
        medir. Es la razon de ser de `VENTANA_DE_RASGUEO_S`: una sola mirada, en el
        peor instante, perdia el acorde entero.
        """
        media = VENTANA_ACORDES // 2
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR, media))

        tocadas = rasguear(seguidor, 48)

        assert sorted(t.midi for t in tocadas) == sorted(DO_MAYOR)
        assert any(t.por_presencia for t in tocadas)


class TestNoSeCobraDosVeces:
    def test_un_segundo_rasgueo_no_duplica_el_acorde_ya_cobrado(self):
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        rasguear(seguidor, 48)
        primera = len(seguidor.estado.tocadas)
        rasguear(seguidor, 48, en=0.6)
        assert len(seguidor.estado.tocadas) == primera
        assert primera == len(DO_MAYOR)

    def test_olvidar_el_tramo_deja_el_acorde_recobrable(self):
        """Lo que hace que repetir el bucle no salga en blanco la segunda vuelta."""
        seguidor = seguidor_con(pieza_con_acorde(), rasgueo(DO_MAYOR))
        rasguear(seguidor, 48)
        seguidor.olvidar_tramo(0.0, 10.0)
        assert seguidor.estado.tocadas == ()
        tocadas = rasguear(seguidor, 48)
        assert sorted(t.midi for t in tocadas) == sorted(DO_MAYOR)


class TestDosAcordesSeguidos:
    def test_cada_grupo_cobra_el_suyo_y_no_el_del_vecino(self):
        """Dos acordes distintos, uno por pulso: el segundo no cobra notas del primero."""
        primero = (48, 52, 55)
        segundo = (43, 47, 50)
        notas = tuple(
            NotaEnPieza(midi=m, cuerda=5, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
            for m in primero
        ) + tuple(
            NotaEnPieza(midi=m, cuerda=5, traste=0, inicio_pulsos=1.0, duracion_pulsos=1.0)
            for m in segundo
        )
        pieza = Pieza(
            nombre="p", perfil="guitarra_estandar", tempo=60, compas=(4, 4), notas=notas
        )
        ventanas = {"actual": rasgueo(primero)}
        seguidor = SeguidorPieza(
            pieza,
            detector_acordes=DetectorAcordes(GUITARRA, frecuencia_muestreo=FS),
            proveedor_de_muestras=lambda _n: ventanas["actual"],
        )
        rasguear(seguidor, 48, en=0.0)
        assert sorted(t.midi for t in seguidor.estado.tocadas) == sorted(primero)
        ventanas["actual"] = rasgueo(segundo)
        rasguear(seguidor, 43, en=1.0)
        assert sorted(t.midi for t in seguidor.estado.tocadas) == sorted(primero + segundo)


class TestReiniciar:
    def test_reiniciar_vacia_el_bufer_del_detector_de_acordes(self):
        """Sin esto, el primer acorde del tramo nuevo se juzga con audio del viejo."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        detector.procesar(rasgueo(DO_MAYOR), list(DO_MAYOR))
        seguidor = SeguidorPieza(
            pieza_con_acorde(),
            detector_acordes=detector,
            proveedor_de_muestras=lambda _n: None,
        )
        # Construir el seguidor ya llama a `reiniciar`, asi que el bufer que el
        # detector traia lleno tiene que estar a cero: con el proveedor dando None
        # nadie lo rellena, y un acorde no puede salir de la nada.
        assert detector.procesar(np.zeros(0), list(DO_MAYOR)).estado == "silencio"
