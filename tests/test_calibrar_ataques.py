"""La medida de DONDE se marca el ataque, no solo de cuantos hay.

El resto de `herramientas/calibrar_ataques.py` busca los parametros que CUENTAN
bien las pulsaciones. Eso deja pasar un detector que acierta el numero y marca
cada ataque decenas de milisegundos despues de que la cuerda sonara, que es
precisamente lo que el carril le cobra al alumno como "tarde".

Las envolventes se construyen aqui, en niveles de dB ya calculados, porque lo que
se afirma es la aritmetica del retroceso y no el analisis del audio: entrar por
muestras metaria la ventana y el suavizador en una prueba que no habla de ellos.
El suelo de ruido por omision son -60 dBFS, asi que un cuadro a -60 es silencio
para el detector y por debajo no hay ataque posible.
"""

import numpy as np
import pytest

from herramientas.calibrar_ataques import PASO_ANALISIS, retrasos_del_cruce
from nucleo.ejercicios.ataques import REFRACTARIO_S, SALTO_ATAQUE_DB

MS_POR_CUADRO = PASO_ANALISIS * 1000.0


def niveles_de(db: list[float]) -> list[tuple[float, float]]:
    """La secuencia (instante, nivel) que vera el detector, a la cadencia real."""
    return [(indice * PASO_ANALISIS, valor) for indice, valor in enumerate(db)]


def medir(db: list[float]) -> list[float]:
    return retrasos_del_cruce(niveles_de(db), SALTO_ATAQUE_DB, REFRACTARIO_S)


def test_un_golpe_seco_sobre_silencio_no_tiene_nada_que_retroceder():
    """El caso en que el detector ACIERTA el instante: la medida dice cero.

    Importa que diga cero y no un cuadro: el cuadro anterior esta mas bajo, asi que
    un retroceso sin tope se metria en el, y ese cuadro era silencio. Es lo que el
    suelo de ruido impide (ver `retrasos_del_cruce`).
    """
    assert medir([-60.0] * 6 + [-20.0] + [-21.0] * 20)[0] == pytest.approx(0.0)


def test_una_subida_que_empieza_antes_se_mide_desde_donde_empezo():
    """La cuerda ya sonaba un cuadro antes de que el nivel cruzara los 6 dB.

    Es la forma de una pulsacion sobre algo que todavia suena: la energia sube poco
    a poco hasta despegarse de la referencia, y el detector no firma hasta el ultimo
    de esos cuadros. El anterior ya era la nota, y el alumno lo paga.
    """
    assert medir([-60.0] * 6 + [-55.0, -48.0, -40.0, -30.0] + [-31.0] * 20)[0] == (
        pytest.approx(MS_POR_CUADRO)
    )


def test_el_retroceso_para_en_el_valle_y_no_se_come_la_nota_anterior():
    """ESTO es lo que hace la medida utilizable en vez de peligrosa.

    Retroceder sin tope marcaria el ataque antes de que la cuerda sonara y le daria
    la razon a un alumno que llego tarde. Aqui hay una nota que decae seis cuadros,
    un valle, y luego la subida de dos que cruza el umbral: se miden los DOS, no los
    ocho, porque el retroceso se detiene en cuanto la energia deja de subir.
    """
    decae = [-20.0, -26.0, -32.0, -38.0, -44.0, -50.0]
    retrasos = medir([-60.0] * 4 + decae + [-40.0, -24.0] + [-25.0] * 20)
    assert len(retrasos) == 2, f"se marcaron {len(retrasos)} ataques y se esperaban 2"
    assert retrasos[1] == pytest.approx(2 * MS_POR_CUADRO)


def test_se_mide_un_retraso_por_cada_ataque_marcado():
    """Tantas medidas como ataques, ni una inventada ni una perdida."""
    una = [-55.0, -48.0, -30.0] + [-31.0] * 20
    otra = [-50.0, -25.0] + [-26.0] * 20
    retrasos = medir([-60.0] * 6 + una + otra)
    assert len(retrasos) == 3, f"se marcaron {len(retrasos)} ataques y se esperaban 3"
    assert all(valor >= 0.0 for valor in retrasos)


def test_sin_ataques_no_se_inventa_ninguna_medida():
    """Por debajo del suelo de ruido no hay ataques, asi que tampoco retrasos."""
    assert medir([-90.0] * 20) == []


def _retrasos_del_gemelo(pieza) -> np.ndarray:
    """Los retrasos que el detector acumula sobre el gemelo PERFECTO tocando `pieza`.

    El gemelo toca exactamente en el instante escrito, asi que todo retraso que
    salga de aqui es del detector y de nadie mas. Va sobre el gemelo porque es el
    unico audio que el repo puede tener: ningun archivo con derechos de autor entra
    aqui, y las grabaciones reales del usuario -las que de verdad deciden si la
    correccion vale la pena- no estan todavia.
    """
    from nucleo.afinaciones import PERFILES
    from nucleo.analisis.energia import nivel_dbfs
    from nucleo.gemelo.interprete import interpretar
    from nucleo.gemelo.perfiles import PERFECTO

    interpretacion = interpretar(pieza, PERFECTO)
    fs = interpretacion.frecuencia_muestreo
    ventana = PERFILES[pieza.perfil].tamano_ventana(fs)
    salto = int(round(PASO_ANALISIS * fs))
    muestras = interpretacion.muestras
    niveles = [
        (indice / fs, nivel_dbfs(muestras[indice : indice + ventana]))
        for indice in range(0, muestras.size - ventana, salto)
    ]
    return np.array(retrasos_del_cruce(niveles, SALTO_ATAQUE_DB, REFRACTARIO_S))


def test_el_peor_retraso_de_una_nota_suelta_se_come_la_ventana_entera():
    """El hallazgo, y es el contrario del que se buscaba: el peor caso es SUELTO.

    Medido 84 ms sobre la escala de ocho notas con el gemelo tocando PERFECTO,
    contra una ventana de acierto de 80: esa es la nota que el carril firmaba a
    +89 ms y marcaba «tarde» sin que nadie tocara mal.

    No es una prueba de calidad del detector, es el candado de la medida inscrita en
    `retrasos_del_cruce`: si este numero se mueve hay que reescribir ese docstring,
    no esta asercion.
    """
    from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas

    retrasos = _retrasos_del_gemelo(escala_de_ocho_notas())
    assert retrasos.size == 8, f"se marcaron {retrasos.size} ataques en ocho notas"
    assert retrasos.max() >= 80.0, (
        f"el peor retraso salio {retrasos.max():.0f} ms y estaba medido en 84: si "
        "bajo, el detector mejoro y hay que reescribir la medida inscrita en "
        "`retrasos_del_cruce`"
    )


def test_en_un_rasgueo_el_detector_marca_dos_ataques_y_el_segundo_llega_tarde():
    """Los acordes no tienen el peor caso, tienen el patron alterno.

    Medido: 15 ataques para ocho acordes -o sea dos por rasgueo- y los retrasos van
    0, 0, 63, 0, 63... El primero de cada acorde se marca en su sitio y el segundo
    63 ms tarde. La mediana sale CERO, y eso es lo que decide la forma de la
    correccion: el problema es del peor caso, no del tipico, asi que un descuento
    fijo estropearia los que ya estan bien y lo que hace falta es un retroceso.
    """
    from nucleo.gemelo.piezas_de_prueba import pieza_de_rasgueos

    retrasos = _retrasos_del_gemelo(pieza_de_rasgueos())
    assert retrasos.size > 8, (
        f"se marcaron {retrasos.size} ataques para ocho acordes: si ya no son mas de "
        "uno por rasgueo, el detector cambio y hay que remedir"
    )
    assert np.median(retrasos) <= 21.0, (
        f"la mediana salio {np.median(retrasos):.0f} ms y estaba medida en 0"
    )
    assert retrasos.max() >= 60.0, (
        f"el peor retraso salio {retrasos.max():.0f} ms y estaba medido en 63"
    )
