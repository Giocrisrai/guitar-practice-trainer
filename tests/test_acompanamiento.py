"""El render determinista de las voces de fondo.

Estas pruebas son la puerta de la etapa: si el render no fuese determinista,
ninguna prueba posterior podria afirmar sobre muestras.

**Ni una asercion toma su valor de referencia del camino que prueba.** El
instante de muestra de una nota se calcula aqui a mano -de `tempo`,
`factor_tempo` y `frecuencia_muestreo`- y NO llamando a `rodaja` ni leyendo
`pulsos_por_segundo`: `_muestra_del_pulso` es la cuenta escrita a mano, y es la
unica que esta permitida en una asercion.
"""

import numpy as np
import pytest

from nucleo.acompanamiento import MUESTRAS_MAXIMAS, renderizar
from nucleo.musica import midi_a_frecuencia
from nucleo.piezas.voces_de_fondo import NotaDeFondo, VozDeFondo

TEMPO = 120
MUESTREO = 48000


def _voz(*notas: NotaDeFondo) -> tuple[VozDeFondo, ...]:
    """Una sola voz con las notas dadas, que es lo que casi todas necesitan."""
    return (VozDeFondo(nombre="Bajo", instrumento="Bass", notas=notas),)


def _muestra_del_pulso(
    pulso: float, tempo: int = TEMPO, factor_tempo: float = 1.0, muestreo: int = MUESTREO
) -> int:
    """El indice de muestra de un pulso, A MANO.

    segundos = pulsos * 60 / (tempo * factor_tempo), muestras = segundos * fs.
    Escrita aqui a proposito: si se preguntara a `PiezaRenderizada`, la prueba del
    mapa estaria comparando el mapa consigo mismo.
    """
    segundos = pulso * 60.0 / (tempo * factor_tempo)
    return int(round(segundos * muestreo))


def _frecuencia_del_periodo_dominante(
    muestras: np.ndarray, muestreo: int = MUESTREO
) -> float:
    """La afinacion leida del audio, por el PERIODO dominante.

    Autocorrelacion y no el maximo del espectro: una cuerda pulsada tiene el
    ataque lleno de armonicos y el bin mas alto de su espectro cae a menudo en el
    noveno (medido: 742 Hz para un Mi2 de 82,4). El periodo, en cambio, es el de
    la fundamental.

    Se busca entre 50 y 1500 Hz y no hasta 500: una guitarra no llega a 1500, pero
    si el techo fuese 500 una nota transportada una OCTAVA ARRIBA caeria fuera del
    rango de busqueda y la funcion contestaria el doble del periodo, o sea la
    altura correcta, y el error quedaria invisible. Medido en las siete alturas que
    usan las pruebas: el error del periodo detectado es del 0,3 % como maximo.
    """
    onda = muestras.astype(np.float64)
    onda = onda - onda.mean()
    correlacion = np.correlate(onda, onda, mode="full")[onda.size - 1 :]
    minimo = int(muestreo / 1500.0)
    maximo = int(muestreo / 50.0)
    retardo = minimo + int(np.argmax(correlacion[minimo:maximo]))
    return muestreo / retardo


def _energia_cerca_de(muestras: np.ndarray, hertz: float, muestreo: int = MUESTREO) -> float:
    """Magnitud del espectro en una banda estrecha alrededor de `hertz`."""
    espectro = np.abs(np.fft.rfft(muestras.astype(np.float64)))
    frecuencias = np.fft.rfftfreq(muestras.size, 1.0 / muestreo)
    banda = (frecuencias > hertz - 3.0) & (frecuencias < hertz + 3.0)
    return float(espectro[banda].max())


def test_la_misma_pieza_al_mismo_tempo_suena_identica():
    """Es lo que permite afirmar sobre muestras en todas las pruebas que vienen."""
    voces = _voz(
        NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0),
        NotaDeFondo(midi=47, inicio_pulsos=1.0, duracion_pulsos=1.0),
        NotaDeFondo(midi=52, inicio_pulsos=2.0, duracion_pulsos=2.0),
    )
    primera = renderizar(voces, tempo=TEMPO)
    segunda = renderizar(voces, tempo=TEMPO)
    assert np.array_equal(primera.muestras, segunda.muestras)
    assert primera.duracion_s == segunda.duracion_s


def test_un_acorde_SUMA_y_no_se_queda_con_la_mas_grave():
    """El interprete reduce a la mas grave; esto es la decision contraria.

    Se mide por el espectro y no por el pico porque los dos renders salen
    normalizados al pico 1,0 por construccion -lo fija la prueba siguiente-, asi
    que el pico no distingue una mezcla de tres de una nota sola. Lo que si
    distingue es que las notas ESTEN, y se comprueba **nota a nota anadida**: con
    una sola medida, un render que sumara dos de las tres pasaria.

    Mi2 82,4 Hz, Do#3 103,8 y Si2 123,5. Ninguna de las dos ultimas es armonico de
    las anteriores -los armonicos del Mi2 son 164,8, 247,2...-, asi que la energia
    en su banda solo puede venir de su propia nota.
    """
    notas = (
        NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0),
        NotaDeFondo(midi=44, inicio_pulsos=0.0, duracion_pulsos=1.0),
        NotaDeFondo(midi=47, inicio_pulsos=0.0, duracion_pulsos=1.0),
    )
    ventana = MUESTREO // 2
    renders = [renderizar(_voz(*notas[:cuantas]), tempo=TEMPO) for cuantas in (1, 2, 3)]
    for anadida, pieza in enumerate(renders[1:], start=1):
        antes = renders[anadida - 1]
        hertz = midi_a_frecuencia(notas[anadida].midi)
        con = _energia_cerca_de(pieza.muestras[:ventana], hertz)
        sin = _energia_cerca_de(antes.muestras[:ventana], hertz)
        assert con > 10.0 * sin, f"la nota {anadida + 1} del acorde no esta sonando"
    # Y no es la mas grave disfrazada: la semilla de la primera nota del acorde es
    # la misma que la de la nota sola, asi que reducir el acorde a la mas grave
    # daria exactamente el mismo buffer.
    assert not np.array_equal(
        renders[2].muestras[: renders[0].muestras.size], renders[0].muestras
    )



def test_todas_las_notas_entran_con_el_MISMO_peso():
    """Estar presente no es sumarse: las tres notas pesan lo mismo, exactamente.

    `cuerda_pulsada` devuelve cada nota con pico exactamente `fuerza`, asi que
    tres notas separadas en el tiempo -nada que se solape- tienen el MISMO pico
    antes de la mezcla. Una sola normalizacion global las divide a las tres por el
    mismo numero, asi que el pico de cada region tiene que salir identico: 1,0.

    Es la asercion que de verdad dice «se suman todas con su peso». Un render que
    atenuara una nota, o que las pesara distinto por su puesto, por su altura o por
    su voz, rompe esta igualdad y no rompe ninguna medida de presencia.

    Primero lo intente comparando la banda de cada nota en el acorde contra la
    banda de la misma nota con la misma semilla en un render donde las otras dos
    estaban lejos. Esa prueba era ciega: la nota conserva su puesto en los dos
    renders, asi que una atenuacion POR PUESTO se aplicaba en los dos y la razon
    no se movia. El mutante -la tercera nota al 80 %- sobrevivio, y por eso esta
    prueba mide picos y no bandas.
    """
    notas = ((40, 0.0), (44, 4.0), (47, 8.0))
    pieza = renderizar(
        _voz(
            *(
                NotaDeFondo(midi=midi, inicio_pulsos=pulso, duracion_pulsos=1.0)
                for midi, pulso in notas
            )
        ),
        tempo=TEMPO,
    )
    # La nota dura un pulso y la cola la deja en 0,65 s; van cada dos pulsos (1,0 s),
    # asi que cada region lleva una nota entera y nada de la vecina.
    largo = int(0.65 * MUESTREO)
    picos = [
        float(np.max(np.abs(pieza.muestras[_muestra_del_pulso(pulso) :][:largo])))
        for _, pulso in notas
    ]
    assert picos == [pytest.approx(1.0, abs=1e-6)] * 3, f"pesos distintos: {picos}"

def test_se_normaliza_UNA_vez_sobre_la_mezcla_entera():
    """Una nota sola y un acorde de seis: el pico global es 1,0 y la sola no llega.

    Normalizar nota a nota daria lo contrario: la nota sola llegaria tambien a
    1,0 y sonaria igual de fuerte que el acorde de seis.
    """
    acorde = tuple(
        NotaDeFondo(midi=midi, inicio_pulsos=4.0, duracion_pulsos=1.0)
        for midi in (40, 45, 50, 55, 59, 64)
    )
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0), *acorde),
        tempo=TEMPO,
    )
    assert float(np.max(np.abs(pieza.muestras))) == pytest.approx(1.0, abs=1e-6)
    hasta_el_acorde = _muestra_del_pulso(3.0)
    pico_de_la_sola = float(np.max(np.abs(pieza.muestras[:hasta_el_acorde])))
    assert pico_de_la_sola < 0.75


def test_la_nota_mas_corta_que_su_periodo_se_alarga_y_no_lanza():
    """`cuerda_pulsada` lanzaria; el render la alarga al minimo y sale.

    A 120 bpm, 0,002 pulsos son 1 ms, y un periodo del Mi2 son 12 ms.
    """
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=0.002)),
        tempo=TEMPO,
    )
    # El minimo exacto, escrito a mano: el periodo del Mi2 en muestras mas las dos
    # de prehistoria que lee el lazo de tres tomas, en segundos. Se afirma en
    # VALOR y no con un «mayor que un periodo», porque un minimo de 1/f -sin las
    # dos muestras- tampoco haria lanzar a `cuerda_pulsada` y pasaria inadvertido.
    minimo_s = (MUESTREO / midi_a_frecuencia(40) + 2.0) / MUESTREO
    assert pieza.duracion_s == pytest.approx(minimo_s, rel=1e-12)
    assert float(np.max(np.abs(pieza.muestras))) > 0.0
    # Y el minimo se mide en LA frecuencia de muestreo que se pide, no en 48000:
    # el periodo en muestras no es el mismo numero a 24 kHz, y un 48000 cableado
    # aqui dejaria la nota corta 42 microsegundos larga -que no lanza y no se oye-
    # hasta el dia que alguien renderice a 8 kHz y la guarda no alcance.
    a_la_mitad = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=0.002)),
        tempo=TEMPO,
        frecuencia_muestreo=24000,
    )
    minimo_a_24k = (24000 / midi_a_frecuencia(40) + 2.0) / 24000
    assert a_la_mitad.duracion_s == pytest.approx(minimo_a_24k, rel=1e-12)


def test_rodaja_devuelve_silencio_antes_y_despues_de_la_pieza():
    """El cabezal vive en la PASADA, que empieza antes y puede pararse despues."""
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0)),
        tempo=TEMPO,
    )
    antes = pieza.rodaja(-4.0, 512)
    despues = pieza.rodaja(1000.0, 512)
    assert antes.size == 512
    assert despues.size == 512
    assert not antes.any()
    assert not despues.any()


def test_rodaja_cae_donde_el_mapa_dice():
    """La rodaja del pulso de la nota trae energia; la de un pulso antes, no.

    El indice de muestra sale de `_muestra_del_pulso`, escrita a mano en esta
    prueba.
    """
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=4.0, duracion_pulsos=1.0)),
        tempo=TEMPO,
    )
    desde = _muestra_del_pulso(4.0)
    cuantas = 1024
    assert np.array_equal(pieza.rodaja(4.0, cuantas), pieza.muestras[desde : desde + cuantas])
    assert float(np.max(np.abs(pieza.rodaja(4.0, cuantas)))) > 0.0
    assert not pieza.rodaja(3.0, cuantas).any()


def test_el_factor_de_tempo_estira_la_duracion_y_no_la_afinacion():
    """Al 50 %, `duracion_s` se dobla y la afinacion no se mueve.

    Es la razon de renderizar de nuevo en vez de resamplear: resamplear al 50 %
    bajaria la pieza una octava.
    """
    voces = _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=2.0))
    normal = renderizar(voces, tempo=TEMPO)
    lenta = renderizar(voces, tempo=TEMPO, factor_tempo=0.5)
    assert lenta.duracion_s == pytest.approx(2.0 * normal.duracion_s)
    esperada = midi_a_frecuencia(40)
    ventana = MUESTREO // 2
    assert _frecuencia_del_periodo_dominante(normal.muestras[:ventana]) == pytest.approx(
        esperada, rel=0.03
    )
    assert _frecuencia_del_periodo_dominante(lenta.muestras[:ventana]) == pytest.approx(
        esperada, rel=0.03
    )


def test_sin_voces_devuelve_un_buffer_de_duracion_cero():
    """Nadie deberia tener que preguntar antes de llamar."""
    vacia = renderizar((), tempo=TEMPO)
    assert vacia.muestras.size == 0
    assert vacia.duracion_s == 0.0
    assert not vacia.rodaja(0.0, 256).any()
    sin_notas = renderizar(_voz(), tempo=TEMPO)
    assert sin_notas.muestras.size == 0
    assert sin_notas.duracion_s == 0.0
    # Y el mapa del buffer vacio lleva el factor de tempo, igual que el del lleno:
    # el acompanante lee `pulsos_por_segundo` sin preguntar si hay notas dentro.
    a_la_mitad = renderizar((), tempo=TEMPO, factor_tempo=0.5)
    assert a_la_mitad.pulsos_por_segundo == pytest.approx(TEMPO * 0.5 / 60.0)


def test_por_encima_del_tope_de_memoria_falla_LIMPIO_y_lo_dice():
    """Una cancion larga al 10 % de tempo reservaria cientos de megas y moriria.

    El tope son doce minutos a 48 kHz; una nota en el pulso 200 al 10 % cae en el
    minuto 16.
    """
    voces = _voz(NotaDeFondo(midi=40, inicio_pulsos=200.0, duracion_pulsos=1.0))
    with pytest.raises(ValueError, match="minutos") as fallo:
        renderizar(voces, tempo=TEMPO, factor_tempo=0.1)
    mensaje = str(fallo.value)
    assert "16" in mensaje
    assert "12" in mensaje
    assert MUESTRAS_MAXIMAS == 48000 * 60 * 12


def test_dos_notas_iguales_no_son_el_mismo_clon():
    """La semilla por nota se deriva del INDICE, no es una constante.

    Con la semilla fija en un numero las dos notas saldrian bit a bit iguales, y
    un acorde de octavas sonaria a una sola cuerda doblada en volumen.
    """
    pieza = renderizar(
        _voz(
            NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0),
            NotaDeFondo(midi=40, inicio_pulsos=4.0, duracion_pulsos=1.0),
        ),
        tempo=TEMPO,
    )
    cuantas = 4096
    primera = pieza.muestras[:cuantas]
    segunda = pieza.muestras[_muestra_del_pulso(4.0) : _muestra_del_pulso(4.0) + cuantas]
    assert primera.any()
    assert segunda.any()
    assert not np.array_equal(primera, segunda)


def test_la_ganancia_escala_el_pico_de_la_mezcla():
    """`ganancia` se aplica DESPUES de normalizar, asi que fija el pico."""
    voces = _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0))
    assert float(np.max(np.abs(renderizar(voces, tempo=TEMPO).muestras))) == pytest.approx(
        1.0, abs=1e-6
    )
    a_medias = renderizar(voces, tempo=TEMPO, ganancia=0.5)
    assert float(np.max(np.abs(a_medias.muestras))) == pytest.approx(0.5, abs=1e-6)


# --- Las pruebas de la ronda de arreglos 1/5: nueve mutantes que vivian ---


def test_suenan_TODAS_las_voces_y_TODAS_sus_notas():
    """Sumar varias pistas es la razon de existir del modulo.

    Con las once pruebas de la primera vuelta, renderizar solo `voces[:1]` -o
    solo la primera nota de cada voz- pasaba: ninguna usaba mas de una voz. Aqui
    hay dos voces de tres y dos notas, separadas dos pulsos, y se comprueba el
    ataque de cada una por su indice calculado a mano.

    Las notas duran un pulso -0,65 s con la cola a 120 bpm- y van cada dos pulsos
    -1,0 s-, asi que antes de cada ataque hay silencio de verdad y «la muestra
    anterior es cero» significa algo.
    """
    el_bajo = ((0.0, 40), (2.0, 45), (4.0, 50))
    el_piano = ((6.0, 60), (8.0, 64))
    voces = (
        VozDeFondo(
            nombre="Bajo",
            instrumento="Bass",
            notas=tuple(
                NotaDeFondo(midi=midi, inicio_pulsos=pulso, duracion_pulsos=1.0)
                for pulso, midi in el_bajo
            ),
        ),
        VozDeFondo(
            nombre="Piano",
            instrumento="Piano",
            notas=tuple(
                NotaDeFondo(midi=midi, inicio_pulsos=pulso, duracion_pulsos=1.0)
                for pulso, midi in el_piano
            ),
        ),
    )
    pieza = renderizar(voces, tempo=TEMPO)
    for pulso, midi in el_bajo + el_piano:
        desde = _muestra_del_pulso(pulso)
        if desde > 0:
            assert pieza.muestras[desde - 1] == 0.0, f"hay sonido antes del pulso {pulso}"
        assert pieza.muestras[desde] != 0.0, f"no hay ataque en el pulso {pulso}"
        # Y la ALTURA de cada una, que es lo que el usuario oye. Sin esto, un
        # render que transportara todas las voces menos la primera -o que les
        # cambiara la altura entera- dejaria las pruebas verdes y al usuario con un
        # fondo desafinado. La ventana son 0,3 s y la nota anterior se acabo 0,35 s
        # antes, asi que dentro solo esta esta nota.
        ventana = pieza.muestras[desde : desde + int(0.3 * MUESTREO)]
        assert _frecuencia_del_periodo_dominante(ventana) == pytest.approx(
            midi_a_frecuencia(midi), rel=0.02
        ), f"la nota del pulso {pulso} no suena a midi {midi}"


def test_el_ataque_cae_EXACTAMENTE_en_la_muestra_del_mapa():
    """Ni una muestra antes ni una despues, y con un reparto que no es entero.

    A 140 bpm el pulso mide 20571,43 muestras, asi que el pulso 2 cae en la
    41142,86: redondear da 41143 y truncar 41142. La prueba distingue las dos, que
    es la unica forma de que un desplazamiento de una muestra -o de cien- se vea.
    """
    tempo_que_no_cuadra = 140
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=2.0, duracion_pulsos=1.0)),
        tempo=tempo_que_no_cuadra,
    )
    desde = _muestra_del_pulso(2.0, tempo=tempo_que_no_cuadra)
    assert desde == 41143  # la cuenta a mano, escrita tambien en decimal
    assert pieza.muestras[desde - 1] == 0.0
    assert pieza.muestras[desde] != 0.0
    assert not pieza.muestras[:desde].any()


def test_el_factor_de_tempo_llega_al_MAPA_y_no_solo_a_la_duracion():
    """La decision M2 de la spec: el cabezal indexa por aqui.

    Si `pulsos_por_segundo` se guardara sin el factor, el fondo se desincronizaria
    en cuanto el usuario baja el tempo -el defecto mas caro de la etapa- y
    `duracion_s` seguiria siendo correcta, asi que la prueba del factor no lo
    veria. El indice se calcula a mano CON el factor dentro.
    """
    factor = 0.5
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=4.0, duracion_pulsos=1.0)),
        tempo=TEMPO,
        factor_tempo=factor,
    )
    desde = _muestra_del_pulso(4.0, factor_tempo=factor)
    assert desde == 192000  # 4 pulsos a 60 bpm efectivos: 4 s a 48 kHz
    assert pieza.muestras[desde - 1] == 0.0
    assert pieza.muestras[desde] != 0.0
    cuantas = 1024
    assert np.array_equal(
        pieza.rodaja(4.0, cuantas), pieza.muestras[desde : desde + cuantas]
    )


def test_la_duracion_total_lleva_la_cola_escrita_de_la_figura():
    """`duracion_s` en valor absoluto: una blanca a 120 bpm son 1,0 s y la cola 1,3.

    El 1,3 se escribe aqui y no se importa del modulo: una prueba que lea la
    constante que prueba no prueba nada.
    """
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=2.0)),
        tempo=TEMPO,
    )
    figura_s = 2.0 * 60.0 / TEMPO
    assert pieza.duracion_s == pytest.approx(1.3 * figura_s)
    assert pieza.muestras.size == int(round(1.3 * figura_s * MUESTREO))


def test_la_semilla_base_cambia_el_render_y_None_lo_hace_distinto_cada_vez():
    """Con otra semilla, otro ruido; con `None`, ni dos veces igual."""
    voces = _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0))
    assert not np.array_equal(
        renderizar(voces, tempo=TEMPO, semilla=0).muestras,
        renderizar(voces, tempo=TEMPO, semilla=1).muestras,
    )
    assert not np.array_equal(
        renderizar(voces, tempo=TEMPO, semilla=None).muestras,
        renderizar(voces, tempo=TEMPO, semilla=None).muestras,
    )


def test_rodaja_a_medias_por_la_izquierda_y_por_la_derecha():
    """Los dos bordes parciales, que son los que de verdad pasan en una pasada.

    El bloque que pide el acompanante cae a caballo del pulso cero al arrancar y a
    caballo del final al acabar, y en los dos casos la mitad buena tiene que estar
    EN SU SITIO dentro del bloque: desplazada, repite audio o abre un hueco.
    """
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=2.0)),
        tempo=TEMPO,
    )
    cuantas = 1024

    # Izquierda: -0,01 pulsos a 120 bpm son -240 muestras.
    desde = _muestra_del_pulso(-0.01)
    assert desde == -240
    bloque = pieza.rodaja(-0.01, cuantas)
    assert not bloque[:240].any()
    assert np.array_equal(bloque[240:], pieza.muestras[: cuantas - 240])

    # Derecha: el bloque que empieza 300 muestras antes del final.
    fuera = 300
    pulso = (pieza.muestras.size - fuera) * (TEMPO / 60.0) / MUESTREO
    bloque = pieza.rodaja(pulso, cuantas)
    assert np.array_equal(bloque[:fuera], pieza.muestras[-fuera:])
    assert not bloque[fuera:].any()


def test_un_tempo_o_un_factor_que_no_sirven_se_dicen_en_vez_de_dividir_por_cero():
    """Sin la guarda, un factor 0 es una division por cero diez lineas despues."""
    voces = _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0))
    for tempo_malo in (0, -120):
        with pytest.raises(ValueError, match="tempo"):
            renderizar(voces, tempo=tempo_malo)
    for factor_malo in (0.0, -1.0):
        with pytest.raises(ValueError, match="factor"):
            renderizar(voces, tempo=TEMPO, factor_tempo=factor_malo)


def test_a_otra_frecuencia_de_muestreo_cambian_las_muestras_y_no_la_musica():
    """A 24 kHz la pieza dura lo mismo, ocupa la mitad y suena a la misma altura.

    Ninguna prueba de la primera vuelta salia de los 48000, asi que una
    frecuencia de muestreo cableada dentro pasaba.
    """
    muestreo = 24000
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=2.0, duracion_pulsos=2.0)),
        tempo=TEMPO,
        frecuencia_muestreo=muestreo,
    )
    figura_s = 2.0 * 60.0 / TEMPO
    assert pieza.frecuencia_muestreo == muestreo
    assert pieza.duracion_s == pytest.approx(2.0 * 60.0 / TEMPO + 1.3 * figura_s)
    assert pieza.muestras.size == int(round(pieza.duracion_s * muestreo))
    desde = _muestra_del_pulso(2.0, muestreo=muestreo)
    assert desde == 24000
    assert pieza.muestras[desde - 1] == 0.0
    assert pieza.muestras[desde] != 0.0
    assert _frecuencia_del_periodo_dominante(
        pieza.muestras[desde : desde + muestreo // 2], muestreo=muestreo
    ) == pytest.approx(midi_a_frecuencia(40), rel=0.03)
    # Y la RODAJA, que es la que el hilo de audio llama en cada bloque: si usara
    # 48000 cableado, pediria el doble de muestras adentro y el fondo iria
    # desincronizado justo en el camino que de verdad suena.
    cuantas = 512
    assert np.array_equal(
        pieza.rodaja(2.0, cuantas), pieza.muestras[desde : desde + cuantas]
    )
    assert not pieza.rodaja(1.0, cuantas).any()


def test_las_muestras_son_float32_y_tambien_las_de_la_rodaja():
    """Lo que escribe el acompanante en la tarjeta, y el `dtype` que ella espera.

    Un float64 que colase aqui dobla la memoria y rompe la escritura del stream,
    asi que el `dtype` se afirma apuntandole, y no de rebote.
    """
    pieza = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0)),
        tempo=TEMPO,
    )
    assert pieza.muestras.dtype == np.float32
    assert pieza.rodaja(0.0, 256).dtype == np.float32
    assert pieza.rodaja(-9.0, 256).dtype == np.float32
    vacia = renderizar((), tempo=TEMPO)
    assert vacia.muestras.dtype == np.float32
    assert vacia.rodaja(0.0, 256).dtype == np.float32


def test_la_duracion_la_marca_la_nota_que_acaba_MAS_TARDE():
    """Una nota larga temprana y una corta tardia: manda el final mas lejano.

    Es el caso que ninguna prueba multinota cubria, porque en todas la ultima nota
    era tambien la mas tardia. Dos cuentas equivocadas pasaban: «el final de la
    ultima nota» corta el buffer a 1,3 s y deja la nota larga a medias -se oye
    como un corte en seco-, y «el inicio mas tardio mas la duracion mas larga» da
    6,2 s y deja un segundo de silencio pegado al final.

    A 120 bpm: la larga son 8 pulsos (4,0 s de figura, 5,2 s con la cola) desde el
    pulso 0; la corta son 0,5 pulsos (0,25 s de figura, 0,325 con la cola) desde el
    pulso 2 (1,0 s), o sea que acaba en 1,325 s.
    """
    pieza = renderizar(
        _voz(
            NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=8.0),
            NotaDeFondo(midi=52, inicio_pulsos=2.0, duracion_pulsos=0.5),
        ),
        tempo=TEMPO,
    )
    final_de_la_larga = 1.3 * 8.0 * 60.0 / TEMPO
    final_de_la_corta = 2.0 * 60.0 / TEMPO + 1.3 * 0.5 * 60.0 / TEMPO
    assert final_de_la_corta < final_de_la_larga  # la premisa de la prueba
    assert pieza.duracion_s == pytest.approx(final_de_la_larga)
    # Y la nota larga sigue sonando al borde del buffer: no se corto antes de
    # acabar, que es lo que se oiria.
    assert pieza.muestras[-64:].any()


def test_el_tope_de_memoria_deja_pasar_el_limite_EXACTO_y_rechaza_una_muestra_mas():
    """El tope es `<=`: justo en el limite se renderiza, una muestra mas se rechaza.

    El limite exacto es donde un fallo limpio importa, asi que se prueba ahi y no
    «muy por encima». Los dos renders se construyen a mano: se pide la duracion que
    da exactamente `MUESTRAS_MAXIMAS` muestras, y luego la que da una mas.
    """
    duracion_pulsos = 0.25
    cola_s = 1.3 * duracion_pulsos * 60.0 / TEMPO
    def inicio_para(muestras: int) -> float:
        """Los pulsos de inicio que hacen que la pieza mida `muestras` muestras."""
        return (muestras / MUESTREO - cola_s) * TEMPO / 60.0

    justo = renderizar(
        _voz(
            NotaDeFondo(
                midi=40,
                inicio_pulsos=inicio_para(MUESTRAS_MAXIMAS),
                duracion_pulsos=duracion_pulsos,
            )
        ),
        tempo=TEMPO,
    )
    assert justo.muestras.size == MUESTRAS_MAXIMAS
    with pytest.raises(ValueError, match="minutos"):
        renderizar(
            _voz(
                NotaDeFondo(
                    midi=40,
                    inicio_pulsos=inicio_para(MUESTRAS_MAXIMAS + 1),
                    duracion_pulsos=duracion_pulsos,
                )
            ),
            tempo=TEMPO,
        )
