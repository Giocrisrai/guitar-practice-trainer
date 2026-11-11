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
    la fundamental. Se busca entre 50 y 500 Hz, que es donde vive una guitarra.
    """
    onda = muestras.astype(np.float64)
    onda = onda - onda.mean()
    correlacion = np.correlate(onda, onda, mode="full")[onda.size - 1 :]
    minimo = int(muestreo / 500.0)
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
    distingue es que las otras dos notas ESTEN: 103,8 Hz (el Do#3) no es armonico
    del Mi2, asi que su energia solo puede venir de la segunda nota del acorde.
    """
    acorde = renderizar(
        _voz(
            NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0),
            NotaDeFondo(midi=44, inicio_pulsos=0.0, duracion_pulsos=1.0),
            NotaDeFondo(midi=47, inicio_pulsos=0.0, duracion_pulsos=1.0),
        ),
        tempo=TEMPO,
    )
    solo_la_grave = renderizar(
        _voz(NotaDeFondo(midi=40, inicio_pulsos=0.0, duracion_pulsos=1.0)),
        tempo=TEMPO,
    )
    ventana = MUESTREO // 2
    hertz_de_la_segunda = midi_a_frecuencia(44)
    con_acorde = _energia_cerca_de(acorde.muestras[:ventana], hertz_de_la_segunda)
    sin_acorde = _energia_cerca_de(solo_la_grave.muestras[:ventana], hertz_de_la_segunda)
    assert con_acorde > 10.0 * sin_acorde
    # Y no es la mas grave disfrazada: la semilla de la primera nota del acorde es
    # la misma que la de la nota sola, asi que reducir el acorde a la mas grave
    # daria exactamente el mismo buffer.
    assert not np.array_equal(
        acorde.muestras[: solo_la_grave.muestras.size], solo_la_grave.muestras
    )


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
    minimo_s = 1.0 / midi_a_frecuencia(40)
    assert pieza.duracion_s >= minimo_s
    assert float(np.max(np.abs(pieza.muestras))) > 0.0


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
