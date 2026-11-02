# tests/test_gemelo_cadena.py
"""La cadena directa del gemelo: el audio recorriendo la ruta real en tiempo
virtual.

Ni un hilo ni una espera en todo el archivo, y eso no es una comodidad de las
pruebas: el reloj de la cadena sale de las MUESTRAS -el instante de cada ventana
es su final- y por eso una pasada de nueve segundos de audio se recorre en la
suite en menos de un segundo. Una de las pruebas de abajo lee el propio archivo
fuente para que siga siendo verdad.

Lo que se vigila aqui es que la cadena RECOJA lo que la cadena reporto, vuelta a
vuelta: el estado final solo conoce la ultima -`cerrar_repeticion` vacia el
seguidor en cada vuelta-, asi que un registro armado desde el estado final
perderia las tres primeras vueltas de un bucle de cuatro sin que nada se
quejara. De ahi que el registro se recoja mientras la cadena pasa, que es el
unico momento en que esa informacion existe.
"""

from pathlib import Path

import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador
from nucleo.gemelo.cadena import (
    INTERVALO_DE_ANALISIS_S,
    RegistroDeLaCadena,
    pasar_por_la_cadena,
)
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFECTO
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas
from nucleo.piezas.conductor import ConductorDeEstudio
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio

FS = 48000
GUITARRA = PERFILES["guitarra_estandar"]
VENTANA = GUITARRA.tamano_ventana(FS)
SALTO_DE_PRODUCCION = 1008  # 21 ms a 48 kHz


class ConductorDeDoble:
    """Un conductor que no conduce nada: solo anota con que instantes se le llama.

    Existe para poder afirmar la CONVENCION DEL RELOJ sin que el estudio de
    verdad pueda enmascararla. Lleva los mismos cuatro metodos que la cadena usa
    -`fijar_la_mirada`, `mirar`, `observar` y `vueltas_cerradas`- y nada mas: si
    la cadena empieza a necesitar otra cosa del conductor, esta prueba se rompe y
    se entera quien la lea.
    """

    def __init__(self):
        self.instantes_observados: list[float] = []
        self.instantes_mirados: list[float] = []
        self.mirada_fijada: float | None = None
        self.vueltas_cerradas: tuple = ()

    def fijar_la_mirada(self, ahora):
        self.mirada_fijada = ahora

    def mirar(self, ahora, senal_ausente):
        self.instantes_mirados.append(ahora)
        return _ESTADO_VACIO

    def observar(self, resultado, instante_analisis):
        self.instantes_observados.append(instante_analisis)
        return _ESTADO_VACIO


class _CarrilVacio:
    instante_s = 0.0
    tocadas = ()


class _EstadoVacio:
    """Lo minimo que la cadena le lee a un estado: la vuelta y el carril."""

    repeticion = 1
    carril = _CarrilVacio()


_ESTADO_VACIO = _EstadoVacio()


def un_segundo_de_audio(pieza=None):
    """Una interpretacion de exactamente FS muestras, para contar cuadros."""
    return Interpretacion(
        pieza=pieza or escala_de_ocho_notas(),
        muestras=np.zeros(FS, dtype=np.float32),
        eventos=(),
        frecuencia_muestreo=FS,
        duracion_s=1.0,
        silencio_de_cabecera_s=0.0,
    )


def bucle_de_un_compas(repeticiones=3, tempo=100):
    """Interpretacion PERFECTA del primer compas, con su conductor en bucle.

    El tramo es un compas de cuatro notas -`escala_de_ocho_notas` trae dos- y el
    plan lo repite, que es el caso que esta tarea existe para poder afirmar: con
    tres vueltas, el estado final solo conoce la tercera.
    """
    pieza = escala_de_ocho_notas(tempo=tempo)
    interpretacion = interpretar(
        pieza,
        PERFECTO,
        primer_compas=1,
        ultimo_compas=1,
        repeticiones=repeticiones,
        frecuencia_muestreo=FS,
    )
    estudio = SesionDeEstudio(
        pieza,
        PlanDePasada(
            primer_compas=1,
            ultimo_compas=1,
            en_bucle=True,
            compases_de_cuenta_atras=0,
        ),
    )
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    return interpretacion, conductor


def test_el_instante_de_cada_ventana_es_su_final():
    """El primero es `ventana / fs`, y de ahi en adelante un salto cada vez.

    Es la convencion que la spec §3.4 MIDIO con una sonda: principio de la
    ventana da -78,7 ms de error, centro -36,0 ms y final +6,7 ms, que es la
    latencia propia del detector y debe aparecer. Con el centro, el gemelo
    acusaria a la cadena de adelantar cada nota 36 ms y toda asercion de desfase
    quedaria corrupta.
    """
    doble = ConductorDeDoble()
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)

    pasar_por_la_cadena(un_segundo_de_audio(), doble, analizador=analizador)

    instantes = doble.instantes_observados
    assert instantes, "la cadena no observo ni un cuadro"
    assert instantes[0] == pytest.approx(VENTANA / FS), (
        "el primer instante tiene que ser el FINAL de la primera ventana "
        f"({VENTANA / FS:.4f} s), no su centro ni su principio"
    )
    diferencias = np.diff(instantes)
    assert diferencias == pytest.approx(SALTO_DE_PRODUCCION / FS), (
        "entre dos cuadros consecutivos hay exactamente un salto"
    )


def test_la_mirada_se_fija_en_el_origen_del_audio():
    """El reloj virtual arranca en la muestra cero, y la cadena lo dice.

    Sin fijarla, el conductor que venga con una mirada puesta en el reloj de
    pared del servidor contaria un tramo de miles de segundos en su primera
    mirada.
    """
    doble = ConductorDeDoble()
    pasar_por_la_cadena(
        un_segundo_de_audio(), doble, analizador=Analizador(GUITARRA, frecuencia_muestreo=FS)
    )
    assert doble.mirada_fijada == 0.0


def test_el_salto_por_omision_es_el_de_produccion():
    """`salto=None` es 21 ms, no 48000/512.

    Las constantes del detector estan acopladas a esos 21 ms
    (`CUADROS_PARA_NOTA_ESTABLE = 3` son 63 ms a 21 ms y 32 ms a 10,7 ms, y
    `nucleo/ejercicios/pulsaciones.py` advierte por escrito de ello), asi que
    recorrer el audio a otra cadencia es ejercitar un detector que nunca corre.
    """
    doble = ConductorDeDoble()
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)

    pasar_por_la_cadena(un_segundo_de_audio(), doble, analizador=analizador)

    cuadros = len(doble.instantes_observados)
    esperados = round(1.0 / INTERVALO_DE_ANALISIS_S)
    assert abs(cuadros - esperados) <= 1, (
        f"un segundo de audio son {esperados} cuadros de 21 ms, no {cuadros}"
    )
    assert cuadros != FS // 512, "512 es el salto de la sonda, no el de produccion"


def test_el_registro_guarda_las_notas_de_todas_las_vueltas():
    """Las tres vueltas aparecen en los reportes, aunque el estado final no.

    `cerrar_repeticion` vacia el seguidor en cada vuelta, asi que al acabar las
    tres el estado final solo conoce la ultima: si la cadena no recogiera los
    reportes al pasar, las dos primeras vueltas no existirian en ninguna parte.
    """
    interpretacion, conductor = bucle_de_un_compas(repeticiones=3)

    registro = pasar_por_la_cadena(interpretacion, conductor)

    vueltas_reportadas = {reporte.repeticion for reporte in registro.reportes}
    assert vueltas_reportadas == {1, 2, 3}, (
        f"se reporto en las vueltas {sorted(vueltas_reportadas)}, y el bucle dio tres"
    )
    # La cuarta vuelta se abre sola, y no es un defecto de la cadena: el audio
    # lleva delante el silencio de cabecera (`VENTANAS_DE_CABECERA`), asi que
    # dura mas que los tres tramos y el bucle da una vuelta mas con la cola.
    assert registro.estado_final.repeticion >= 3


def test_el_registro_guarda_un_informe_por_vuelta_cerrada():
    """`registro.vueltas` es exactamente lo que el conductor cerro.

    El cierre de vueltas vive en `mirar`, NO en `observar`: una cadena que solo
    observara dejaria `vueltas_cerradas` vacio y este registro no tendria ni un
    informe. Por eso la cuenta se afirma tambien por lo bajo.
    """
    interpretacion, conductor = bucle_de_un_compas(repeticiones=3)

    registro = pasar_por_la_cadena(interpretacion, conductor)

    assert len(registro.vueltas) == len(conductor.vueltas_cerradas)
    assert len(registro.vueltas) == 3, (
        "tres vueltas de audio cierran tres informes, uno por vuelta"
    )
    assert all(informe.repeticiones == 1 for informe in registro.vueltas), (
        "cada informe es el de SOLO esa vuelta, no el acumulado"
    )


def test_no_se_reporta_la_misma_nota_dos_veces():
    interpretacion, conductor = bucle_de_un_compas(repeticiones=3)

    registro = pasar_por_la_cadena(interpretacion, conductor)

    claves = [(reporte.repeticion, reporte.tocada.indice) for reporte in registro.reportes]
    assert len(claves) == len(set(claves)), (
        f"hay notas reportadas dos veces en la misma vuelta: {claves}"
    )


def test_la_cadena_no_abre_hilos_ni_duerme():
    """El reloj es virtual y sale de las muestras: no hay nada que esperar.

    Es la condicion de que la cadena directa se pueda correr en la suite, que es
    a su vez la condicion de que se corra. Si algun dia hace falta un hilo o una
    espera, eso es el nivel de sesion completa y vive en otro modulo.
    """
    from nucleo.gemelo import cadena

    fuente = Path(cadena.__file__).read_text(encoding="utf-8")
    for prohibido in ("threading", "time.sleep", "monotonic"):
        assert prohibido not in fuente, (
            f"`{prohibido}` en la cadena directa: su reloj sale de las muestras"
        )


def test_una_interpretacion_de_silencio_no_reporta_nada():
    """Audio de ceros: ni un reporte y ni una excepcion.

    Un compas vacio de una cancion de verdad llega aqui igual, y la cadena entera
    tiene que tragarlo.
    """
    pieza = escala_de_ocho_notas()
    estudio = SesionDeEstudio(pieza, PlanDePasada(compases_de_cuenta_atras=0))
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)

    registro = pasar_por_la_cadena(un_segundo_de_audio(pieza), conductor)

    assert isinstance(registro, RegistroDeLaCadena)
    assert registro.reportes == ()


def test_un_audio_vacio_no_lanza():
    """Cero muestras es un caso de borde, no un error: el registro sale vacio."""
    pieza = escala_de_ocho_notas()
    estudio = SesionDeEstudio(pieza, PlanDePasada(compases_de_cuenta_atras=0))
    estudio.arrancar()
    conductor = ConductorDeEstudio(estudio, al_cambiar_repeticion=None)
    interpretacion = Interpretacion(
        pieza=pieza,
        muestras=np.zeros(0, dtype=np.float32),
        eventos=(),
        frecuencia_muestreo=FS,
        duracion_s=0.0,
        silencio_de_cabecera_s=0.0,
    )

    registro = pasar_por_la_cadena(interpretacion, conductor)

    assert registro.reportes == ()
    assert registro.estado_final is not None


def test_el_analizador_se_saca_del_perfil_de_la_pieza():
    """Sin analizador, la cadena lo construye con el perfil de la pieza.

    `Pieza.perfil` es una CLAVE de `PERFILES`, y la ventana sale de ahi
    (`perfil.tamano_ventana(fs)`): 4096 muestras con guitarra estandar. Si la
    cadena se inventara otra ventana, el detector leeria menos periodos de los
    que lee en produccion.
    """
    doble = ConductorDeDoble()
    doble.estudio = type("E", (), {"pieza": escala_de_ocho_notas()})()

    pasar_por_la_cadena(un_segundo_de_audio(), doble)

    assert doble.instantes_observados[0] == pytest.approx(VENTANA / FS)


def test_un_analizador_con_otra_frecuencia_es_un_error_claro():
    doble = ConductorDeDoble()
    analizador = Analizador(GUITARRA, frecuencia_muestreo=44100)

    with pytest.raises(ValueError, match="44100"):
        pasar_por_la_cadena(un_segundo_de_audio(), doble, analizador=analizador)
