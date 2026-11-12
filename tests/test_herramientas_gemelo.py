"""El escaparate, por sus piezas separables. NINGUNA prueba levanta el servidor.

Es una decision y no una comodidad: levantar `uvicorn` en una prueba abre un
puerto de la maquina, y un puerto ocupado -por otra copia del escaparate, por
otro proyecto, por la suite corriendo dos veces a la vez- pondria la suite roja
por algo que no tiene nada que ver con lo que mide. Lo que el servidor añade
-que la pasada entera atraviesa la sesion de verdad a tiempo real- ya esta
medido en `tests/test_gemelo_sesion_completa.py`, que lo hace sin HTTP por
medio. Lo que queda aqui son las piezas que deciden: como se lee el tramo, de
donde sale la pieza, que perfil se acepta, que codigo de salida sale y que dice
el informe.

El paso del brief que SI levanta el servidor de verdad se ejecuta a mano una vez
y su salida queda en el informe de la tarea, que es donde sirve de algo.
"""

import os
import pathlib
import socket
import statistics
import subprocess
import sys
import threading
import time
import types
import urllib.error
from dataclasses import replace

import numpy as np
import pytest

from herramientas.gemelo import (
    LECTURAS_POR_SEGUNDO,
    InformeDelFondo,
    StreamCapturadoAlRitmo,
    _salida_del_fondo,
    desfase_contra_el_cabezal,
    fondo_pedido,
    informe_del_fondo,
    _analizador_de_argumentos,
    _construir,
    _decir_el_fondo,
    _informe_del_capturador,
    _correr_la_demostracion,
    _esperar_al_servidor,
    _seguir_la_pasada,
    al_borde_del_techo_del_detector,
    armar_la_pasada,
    codigo_de_salida,
    main,
    leer_bucle,
    perfil_de_destreza,
    pieza_pedida,
    resumen,
    segundos_de_cuenta_atras,
)
from nucleo.gemelo.perfiles import (
    CAOS,
    INTERMEDIO,
    PERFECTO,
    PERFILES_DE_DESTREZA,
    PRINCIPIANTE,
)
from nucleo.acompanamiento import renderizar
from nucleo.gemelo.dispositivo import RecolectorDeLaSesion
from nucleo.gemelo.interprete import interpretar
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas, pieza_de_demostracion
from nucleo.gemelo.veredicto import Veredicto
from nucleo.piezas.compases import pulsos_por_compas
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio
from nucleo.piezas.voces_de_fondo import FondoDisponible, NotaDeFondo, VozDeFondo
from nucleo.sintesis import _abrir_stream_real
from servidor.diagnostico import Diagnostico
from servidor.piezas import voz_de_tu_parte

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Las extensiones que `nucleo.piezas.lectores` sabe leer y que son PARTITURAS de
# verdad. `.txt`, `.tab` y `.xml` se quedan fuera a proposito: el repositorio
# esta lleno de archivos con esas extensiones que no son musica (configuracion,
# tablaturas de prueba escritas aqui), asi que incluirlas convertiria la prueba
# de los derechos de autor en una lista de excepciones.
EXTENSIONES_DE_PARTITURA = (".gp3", ".gp4", ".gp5", ".mid", ".midi", ".mxl", ".musicxml")

# Una ruta de ejemplo para las pruebas de la linea de ordenes. Sale de `$TMPDIR` y
# no de `/tmp` -la restriccion de la etapa-, y nadie la abre: `argparse` solo guarda
# la cadena. Se nombra aqui porque una ruta de ejemplo en una prueba es lo que
# alguien copia.
RUTA_DE_EJEMPLO = pathlib.Path(os.environ.get("TMPDIR", "/var/tmp")) / "x.gp5"


def _veredicto(
    perdidas=(),
    inventadas=0,
    mal_adjudicadas=(),
    excluidas=(),
    tocadas=8,
    maximo=188.3,
    del_tramo=8,
    vueltas=1,
) -> Veredicto:
    """Un `Veredicto` armado a mano, para probar lo que se hace CON el.

    `maximo` es el peor desfase emparejado, y se puede fijar porque de el depende
    si el resumen avisa de que los hallazgos son el borde del detector.

    `del_tramo` y `vueltas` valen por omision lo de una pasada de la pieza entera
    de una sola vuelta -8 notas, 1 vuelta-, que es el caso del que hablan casi
    todas las pruebas de aqui. Quien pruebe un bucle los pone: son las dos
    cantidades con las que `toco_la_pieza_entera_una_vez` distingue las 8 notas de
    una pieza entera de las 4 x 2 de un tramo repetido.
    """
    return Veredicto(
        notas_de_la_pieza=8,
        notas_tocadas=tocadas,
        notas_del_tramo=del_tramo,
        vueltas=vueltas,
        perdidas=perdidas,
        inventadas=inventadas,
        mal_adjudicadas=mal_adjudicadas,
        excluidas=excluidas,
        desfase_introducido_ms=152.3,
        desfase_maximo_ms=maximo,
    )


def test_el_bucle_se_lee_de_la_forma_primero_guion_ultimo():
    """`"17-20"` es el tramo 17 a 20 y `"17"` es el compas 17 solo."""
    assert leer_bucle("17-20") == (17, 20)
    assert leer_bucle("17") == (17, 17)
    assert leer_bucle(" 2 - 5 ") == (2, 5), "los espacios del usuario no son un error"


@pytest.mark.parametrize("texto", ["20-17", "cero", "0-4", "1-2-3", "", "4-", "-4"])
def test_un_tramo_imposible_se_rechaza_con_el_texto_recibido_dentro(texto):
    """Lo que no es un tramo se rechaza, y el mensaje trae el texto RECIBIDO.

    Sin el texto dentro, quien escribio `17-20` con el guion largo que pone el
    corrector de macOS lee «no sirve» y no ve la diferencia con el guion normal. Es
    el unico dato que convierte el mensaje en algo accionable.

    El texto se busca ENTRE COMILLAS (`'...'`) y no suelto, que es como el mensaje lo
    escribe. Antes se buscaba suelto con un `or` de dos ramas, y con el texto vacio
    -uno de los casos- la segunda rama era verdad siempre: de ese caso solo se
    comprobaba que lanzaba, no que el mensaje dijera nada. Una asercion que no puede
    fallar en un caso parametrizado es peor que no tener el caso.
    """
    with pytest.raises(ValueError) as fallo:
        leer_bucle(texto)

    assert f"'{texto}'" in str(fallo.value), (
        f"el mensaje no trae el texto recibido entre comillas: {fallo.value}"
    )


def test_sin_pieza_usa_la_de_demostracion_construida_en_codigo(monkeypatch):
    """Sin `--pieza` la pieza sale de codigo y NO se lee ningun archivo.

    Las dos mitades hacen falta. Que sea la de demostracion se comprueba
    comparandola; que no venga de un archivo se comprueba rompiendo el lector, que
    es lo unico que distingue «se construyo» de «se leyo de un sitio que casualmente
    tiene lo mismo». Es la regla de los derechos de autor del proyecto, y este es
    el sitio donde se podria romper sin que se notara.
    """

    def no_se_lee_nada(*args, **kwargs):
        raise AssertionError(
            "la pieza por omision no puede salir de ningun archivo: "
            f"se intento leer {args!r}"
        )

    monkeypatch.setattr("herramientas.gemelo.importar", no_se_lee_nada)

    pieza = pieza_pedida(None, "guitarra_estandar")

    assert pieza == pieza_de_demostracion()
    assert pieza.notas, "una demostracion sin notas no demuestra nada"
    assert pieza.secciones, "la demostracion practica por secciones"


def test_el_repositorio_no_lleva_ninguna_partitura_dentro():
    """Ningun archivo con derechos de autor entra al repositorio. Nunca.

    **SE PREGUNTA A GIT, Y NO AL DISCO**, porque lo que importa es lo que se
    PUBLICA. La version anterior recorria el disco con `rglob` -lo que el docstring
    prometia y el codigo no hacia-, y eso la ponia roja en la maquina del usuario en
    cuanto usara la funcion principal del programa: `servidor/canciones.py` crea
    `canciones/` al guardar la primera cancion, esa carpeta esta en el `.gitignore`
    a proposito, y la prueba acusaba al usuario de meter material con derechos de
    autor en el repositorio por tener su propia musica en su propio disco. La
    biblioteca del usuario no es el repositorio.

    `git ls-files` lista exactamente lo seguido, incluido lo que este en el indice
    sin cometer todavia, que es lo que hay que vigilar: una partitura añadida con
    `git add` ya esta a un `commit` de publicarse.

    Se salta si no hay git (un tarball del codigo, sin `.git`): la prueba no puede
    afirmar nada sobre lo publicado si no hay con quien hablar, y fingir que si es
    peor que decirlo.
    """
    try:
        seguidos = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"sin git no se puede preguntar que hay seguido: {error}")

    partituras = [
        nombre
        for nombre in seguidos.split("\0")
        if nombre.lower().endswith(EXTENSIONES_DE_PARTITURA)
    ]

    assert partituras == [], f"hay partituras seguidas por git: {partituras}"
    # Y la lista no esta vacia por un fallo de la orden: si `git ls-files` no
    # devolviera nada, la asercion de arriba pasaria sin haber mirado nada.
    assert "pyproject.toml" in seguidos.split("\0"), (
        "git ls-files no devolvio los archivos del proyecto: la prueba no ha "
        "comprobado nada"
    )


def test_con_pieza_se_lee_el_archivo_que_el_usuario_da(monkeypatch, tmp_path):
    """`--pieza` lee la PRIMERA pista del archivo del usuario, con `importar`.

    El mismo lector que usa el servidor, y la pista 1 porque el escaparate no
    tiene donde preguntar cual: quien quiera otra la importa desde la pantalla de
    canciones, que es donde ese selector vive.
    """
    vistos = []

    def espiar(ruta, numero, perfil):
        vistos.append((ruta, numero, perfil))
        return escala_de_ocho_notas()

    monkeypatch.setattr("herramientas.gemelo.importar", espiar)
    archivo = tmp_path / "la_mia.gp5"

    pieza = pieza_pedida(str(archivo), "guitarra_estandar")

    assert pieza == escala_de_ocho_notas()
    assert vistos == [(pathlib.Path(archivo), 1, "guitarra_estandar")]


def test_el_perfil_desconocido_se_rechaza_nombrando_los_validos():
    """Un perfil que no existe se rechaza, y el mensaje trae la lista de cuatro.

    Nombrarlos es la diferencia entre un mensaje que se arregla solo y uno que
    manda al usuario a leer el codigo fuente de un modulo que no sabe donde esta.
    """
    with pytest.raises(ValueError) as fallo:
        perfil_de_destreza("virtuoso")

    mensaje = str(fallo.value)
    assert "virtuoso" in mensaje
    for nombre in PERFILES_DE_DESTREZA:
        assert nombre in mensaje, f"el mensaje no nombra el perfil valido '{nombre}'"


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("perfecto", PERFECTO),
        ("principiante", PRINCIPIANTE),
        ("intermedio", INTERMEDIO),
        ("caos", CAOS),
        ("PERFECTO", PERFECTO),
        ("  caos  ", CAOS),
    ],
)
def test_los_cuatro_perfiles_se_piden_por_nombre(nombre, esperado):
    """Los cuatro, y sin que las mayusculas ni los espacios estorben."""
    assert perfil_de_destreza(nombre) is esperado


def test_el_codigo_de_salida_es_cero_con_veredicto_limpio_y_otro_si_no():
    """Cero solo si la cadena vio todo lo que paso y nada mas.

    Las exclusiones NO manchan el veredicto -son un limite declarado del programa,
    no un defecto de la cadena-, asi que una pasada con exclusiones y nada mas sale
    con cero. Esa regla vive en `Veredicto.limpio` y aqui se comprueba que el
    escaparate la usa en vez de tener su propia copia.
    """
    assert codigo_de_salida(_veredicto()) == 0
    assert codigo_de_salida(_veredicto(excluidas=((1, 3),))) == 0
    assert codigo_de_salida(_veredicto(perdidas=((1, 2),))) == 1
    assert codigo_de_salida(_veredicto(inventadas=1)) == 1
    assert codigo_de_salida(_veredicto(mal_adjudicadas=((1, 2, 60),))) == 1


def test_el_resumen_dice_que_fue_el_gemelo_y_no_una_guitarra():
    """El texto que se imprime dice "gemelo" y dice que nadie toco.

    Nadie debe poder leer este informe creyendo que alguien toco. Es la misma
    regla que pone "(gemelo)" en el nombre del dispositivo: un informe de una
    pasada simulada que se lea igual que uno de una pasada real es peor que no
    tener informe.
    """
    texto = resumen(_veredicto(), escala_de_ocho_notas(), PERFECTO, completada=True)

    assert "gemelo" in texto.lower()
    assert "nadie toco" in texto.lower()
    assert texto.splitlines()[0].lower().count("gemelo") >= 1, (
        "lo tiene que decir en la primera linea, no enterrado al final"
    )
    assert "LIMPIO" in texto
    assert "Escala de ocho notas" in texto
    assert "perfecto" in texto


def test_el_resumen_nombra_lo_que_la_cadena_perdio_y_adjudico_mal():
    """Un veredicto con hallazgos los enumera: sin eso no se puede diagnosticar nada.

    Un informe que dijera solo "CON HALLAZGOS" obliga a volver a correr la pasada
    con un depurador para saber QUE nota, y la pasada no es reproducible: lleva un
    reloj de pared dentro.
    """
    texto = resumen(
        _veredicto(perdidas=((2, 5),), inventadas=1, mal_adjudicadas=((1, 3, 61),)),
        escala_de_ocho_notas(),
        CAOS,
        completada=False,
    )

    assert "CON HALLAZGOS" in texto
    assert "SIN COMPLETAR" in texto
    assert "vuelta 2, nota 5" in texto
    assert "vuelta 1, nota 3" in texto
    assert "61" in texto


def test_el_resumen_explica_los_hallazgos_que_son_el_borde_del_detector():
    """Un «CON HALLAZGOS» al borde del techo se explica DONDE EL USUARIO LO LEE.

    El escaparate sale con codigo 1 sobre una interpretacion PERFECTA con las 48
    notas tocadas y la pasada completada, y lo que el usuario leia era «mal
    adjudicadas: 1» sin nada mas: o sea «el programa se equivoco de nota». La causa
    -la sesion completa no tiene margen contra el techo de 250 ms del detector-
    vivia solo en el informe de la tarea y en una cabecera de pruebas, que son los
    dos sitios donde el usuario no va a mirar.

    No se afloja ninguna tolerancia para que salga limpio: el borde es un hecho
    medido y taparlo convertiria la demostracion en un juez complaciente. Lo que se
    añade es la explicacion, con la cifra y la causa.
    """
    al_borde = _veredicto(mal_adjudicadas=((1, 39, 62),), maximo=239.1)

    texto = resumen(al_borde, pieza_de_demostracion(), PERFECTO, completada=True)

    assert "CON HALLAZGOS" in texto
    assert "Aviso" in texto
    assert "239.1" in texto, "el aviso tiene que traer el desfase medido"
    assert "250" in texto, "y el techo del detector contra el que choca"
    assert "no son del producto" in texto.lower() or "NO son del producto" in texto
    assert "Task 11" in texto, "la causa tiene que quedar localizable"


def test_el_resumen_no_avisa_cuando_el_hallazgo_no_es_el_borde():
    """Y no lo dice cuando no toca: un aviso que sale siempre no avisa de nada.

    Con el peor desfase lejos del techo todavia hay margen, asi que lo que la cadena
    haya encontrado es cosa suya y el escaparate no tiene nada que disculpar. Lo
    mismo con un veredicto limpio: ahi no hay hallazgo ninguno.
    """
    lejos = _veredicto(perdidas=((1, 2),), maximo=188.3)
    limpio = _veredicto(maximo=249.0)

    assert "Aviso" not in resumen(lejos, escala_de_ocho_notas(), PERFECTO, True)
    assert "Aviso" not in resumen(limpio, escala_de_ocho_notas(), PERFECTO, True)


@pytest.mark.parametrize("perfil", [CAOS, PRINCIPIANTE, INTERMEDIO])
def test_el_aviso_del_borde_no_sale_con_un_perfil_que_falla_notas(perfil):
    """**Una REGRESION medida, y la peor clase: el aviso excusaba fallos de verdad.**

    La primera version del aviso solo miraba el veredicto. Medido por el revisor con
    `--perfil caos` sobre 35 notas de 48 y un peor desfase de +226,3 ms -a 4 ms del
    umbral, asi que no es hipotetico-: el escaparate imprimia «con el gemelo PERFECTO
    esos hallazgos NO son del producto» y daba por el borde del detector trece notas
    que el perfil habia dejado de tocar A PROPOSITO.

    Con un perfil que falla notas los hallazgos SI son del interprete, que es
    justamente lo que esos perfiles existen para provocar. Excusarlos convierte la
    demostracion en un juez complaciente en el unico texto que el usuario lee.
    """
    sucio_en_el_borde = _veredicto(
        perdidas=((1, 5),), inventadas=1, maximo=248.0, tocadas=5
    )

    texto = resumen(sucio_en_el_borde, escala_de_ocho_notas(), perfil, completada=True)

    assert "CON HALLAZGOS" in texto
    assert "Aviso" not in texto, (
        f"el aviso del borde no puede salir con el perfil '{perfil.nombre}': "
        "excusaria notas que el interprete dejo de tocar"
    )
    assert "NO son del producto" not in texto


def test_el_aviso_del_borde_no_afirma_que_llego_todo_si_no_llego():
    """La ultima linea del aviso COMPARA contra el total escrito, no lo supone.

    Decia «las 35 notas llegaron» leyendo `notas_tocadas` como si fuera el total de
    la pieza: con trece notas falladas afirmaba que habia llegado todo. Ahora el
    aviso solo sale cuando lo tocado coincide con lo escrito, y la linea nombra los
    dos numeros para que la afirmacion no pueda salir sin ser verdad.
    """
    incompleto = _veredicto(perdidas=((1, 5),), inventadas=1, maximo=248.0, tocadas=5)
    entero = _veredicto(perdidas=((1, 5),), inventadas=1, maximo=248.0, tocadas=8)

    sin_aviso = resumen(incompleto, escala_de_ocho_notas(), PERFECTO, True)
    con_aviso = resumen(entero, escala_de_ocho_notas(), PERFECTO, True)

    assert "Aviso" not in sin_aviso, (
        "con menos notas tocadas que escritas el aviso no puede afirmar que llego todo"
    )
    assert "Aviso" in con_aviso
    assert "las 8 notas de las 8 escritas" in con_aviso, (
        "la linea tiene que nombrar lo tocado Y lo escrito; decia solo lo tocado"
    )


def test_el_aviso_del_borde_no_sale_en_bucle_aunque_la_aritmetica_cuadre():
    """**El defecto que el revisor reprodujo en una pasada real del escaparate.**

    La condicion era `notas_tocadas == notas_de_la_pieza`, y esas dos cantidades
    son de clase distinta: la primera es tramo x vueltas y la segunda es la pieza
    entera. Con `--bucle 1-6 --repeticiones 2` sobre la pieza de demostracion la
    igualdad se cumple por coincidencia aritmetica (24 x 2 = 48 == 48) y el aviso
    salia afirmando «el gemelo toco las 48 notas de las 48 escritas» de una
    pasada que toco 24 notas dos veces.

    Y peor que la frase: en un bucle, perder la ultima nota de cada vuelta es un
    mecanismo DECLARADO del bucle -lo escriben `veredicto.py` y
    `test_gemelo_bucle.py`-, asi que el aviso estaba atribuyendo al «borde del
    detector» perdidas que tienen otro nombre y otra causa. Un aviso que excusa un
    fallo de verdad es peor que no tener aviso.

    Aqui se afirman los dos casos con la MISMA aritmetica: 4 notas de tramo por 2
    vueltas y 8 notas de una pieza entera de una vuelta dan los dos
    `notas_tocadas == 8`, y solo el segundo puede afirmar la frase.
    """
    en_bucle = _veredicto(
        perdidas=((2, 3),), maximo=248.0, tocadas=8, del_tramo=4, vueltas=2
    )
    entera = _veredicto(perdidas=((1, 3),), maximo=248.0, tocadas=8)

    sin_aviso = resumen(en_bucle, escala_de_ocho_notas(), PERFECTO, True)
    con_aviso = resumen(entera, escala_de_ocho_notas(), PERFECTO, True)

    assert en_bucle.notas_tocadas == en_bucle.notas_de_la_pieza, (
        "la coincidencia aritmetica tiene que seguir en pie: es el caso del defecto"
    )
    assert "Aviso" not in sin_aviso, (
        "en bucle el aviso no puede hablar: ni la frase es cierta ni las perdidas "
        "de la frontera de vuelta son del borde del detector"
    )
    assert "Aviso" in con_aviso


def test_el_aviso_del_borde_no_sale_sobre_una_pasada_sin_completar():
    """Una pasada cortada por la mitad tiene hallazgos que pueden venir del corte.

    El borde del detector no los explica, asi que el aviso no se los atribuye. Y la
    linea del aviso dice «la pasada se completo»: sin esta condicion lo diria de una
    pasada que no se completo, con «SIN COMPLETAR» tres lineas mas arriba.
    """
    sucio = _veredicto(perdidas=((1, 5),), inventadas=1, maximo=248.0)

    texto = resumen(sucio, escala_de_ocho_notas(), PERFECTO, completada=False)

    assert "SIN COMPLETAR" in texto
    assert "Aviso" not in texto


def test_el_aviso_del_borde_no_se_cuela_por_una_variante_del_perfil_perfecto():
    """Se compara el perfil ENTERO, no su nombre.

    `replace(PERFECTO, probabilidad_de_fallo=0.5)` conserva `nombre="perfecto"` y
    falla la mitad de las notas. Desde la linea de ordenes solo llegan los cuatro
    perfiles de fabrica, pero `al_borde_del_techo_del_detector` es publica y la
    condicion tiene que ser la de verdad: lo que justifica la frase es que el
    interprete no pueda fallar, no como se llame.
    """
    disfrazado = replace(PERFECTO, probabilidad_de_fallo=0.5)
    sucio = _veredicto(perdidas=((1, 5),), inventadas=1, maximo=248.0)

    assert disfrazado.nombre == "perfecto"
    assert al_borde_del_techo_del_detector(sucio, PERFECTO, True) is True
    assert al_borde_del_techo_del_detector(sucio, disfrazado, True) is False


@pytest.mark.parametrize("compas, pulsos", [((4, 4), 4), ((3, 4), 3), ((7, 8), 3.5)])
def test_la_cuenta_atras_es_la_misma_que_la_del_estudio(compas, pulsos):
    """La cuenta atras del gemelo y la del plan tienen que ser EL MISMO numero.

    Es la condicion de uso que `juzgar` declara y que no puede comprobar: si las
    dos se separan, los dos relojes se separan con ellas y el veredicto le acusa a
    la cadena de la diferencia. Se compara contra lo que la sesion de estudio de
    PRODUCCION calcula —su propio metodo, no una formula copiada aqui—.

    **VA PARAMETRIZADA POR COMPAS, y es por un mutante que sobrevivio.** Con solo
    la escala de 4/4, un escaparate que supusiera «cuatro pulsos por compas» en vez
    de preguntarselo a la pieza pasaba la prueba: 4/4 es justo el caso en que la
    constante y la cuenta correcta valen lo mismo. Una pieza en 3/4 o en 7/8 lo
    delata, y las canciones de verdad las traen.
    """
    pieza = replace(escala_de_ocho_notas(), compas=compas)
    assert pulsos_por_compas(pieza) == pulsos, "el caso no es el que dice ser"

    for compases in (0, 1, 2):
        for factor in (1.0, 0.5):
            estudio = SesionDeEstudio(
                pieza,
                PlanDePasada(compases_de_cuenta_atras=compases, factor_tempo=factor),
            )
            assert segundos_de_cuenta_atras(pieza, compases, factor) == pytest.approx(
                estudio._segundos_de_cuenta_atras()
            ), f"con {compases} compases y factor {factor}"

    # Y el factor de tempo divide: tocar al doble de lento alarga la cuenta atras,
    # porque la cuenta atras son compases y no segundos.
    assert segundos_de_cuenta_atras(pieza, 1, 1.0) == pytest.approx(
        pulsos * 60.0 / 100.0
    )
    assert segundos_de_cuenta_atras(pieza, 1, 0.5) == pytest.approx(
        2 * pulsos * 60.0 / 100.0
    )


def test_la_interpretacion_y_el_plan_se_arman_de_acuerdo():
    """El tramo, el factor y la cuenta atras son LOS MISMOS en los dos.

    Es la condicion que `juzgar` declara y no puede comprobar, y por eso los dos se
    arman en la misma funcion. Esta prueba es la que lo vigila: si alguien cambia
    uno de los dos y no el otro, los dos relojes de la pasada se separan y el
    veredicto culpa a la cadena de la diferencia.
    """
    argumentos = _analizador_de_argumentos().parse_args(
        ["--bucle", "2-3", "--tempo", "0.5", "--repeticiones", "3",
         "--cuenta-atras", "1", "--semilla", "4"]
    )

    pieza, perfil, interpretacion, plan = armar_la_pasada(argumentos)

    assert perfil is PERFECTO
    assert pieza == pieza_de_demostracion()
    assert (plan.primer_compas, plan.ultimo_compas) == (2, 3)
    assert (interpretacion.primer_compas, interpretacion.ultimo_compas) == (2, 3)
    assert plan.factor_tempo == interpretacion.factor_tempo == 0.5
    assert interpretacion.repeticiones == 3
    assert interpretacion.segundos_de_cuenta_atras == pytest.approx(
        segundos_de_cuenta_atras(pieza, plan.compases_de_cuenta_atras, 0.5)
    )
    assert plan.compases_de_cuenta_atras == 1


@pytest.mark.parametrize("repeticiones, en_bucle", [(1, False), (2, True), (5, True)])
def test_el_bucle_solo_se_enciende_con_varias_vueltas(repeticiones, en_bucle):
    """Con una sola vuelta el plan NO va en bucle, y es lo que deja imprimir algo.

    Un tramo en bucle no se acaba nunca: la pasada no se completa, el escaparate se
    queda esperando hasta el limite y no imprime ningun veredicto. Con una sola
    vuelta eso seria el comportamiento por omision, o sea el de la orden que el
    brief documenta.
    """
    argumentos = _analizador_de_argumentos().parse_args(
        ["--repeticiones", str(repeticiones)]
    )

    _, _, interpretacion, plan = armar_la_pasada(argumentos)

    assert plan.en_bucle is en_bucle
    assert interpretacion.repeticiones == repeticiones


def test_la_semilla_cambia_lo_que_el_gemelo_toca():
    """`--semilla` llega al interprete, y es lo que hace la pasada reproducible.

    **La escribi porque un mutante sobrevivio:** con la semilla clavada a cero
    -que es su valor por omision- la suite entera pasaba, asi que `--semilla` era
    una bandera decorativa. Dos semillas distintas con un perfil que falla notas
    tienen que tocar cosas distintas, y la misma semilla la misma cosa: sin eso,
    «se me rompio con la semilla 7» no es un informe reproducible.
    """

    def tocado(semilla: int, perfil: str = "caos"):
        argumentos = _analizador_de_argumentos().parse_args(
            ["--perfil", perfil, "--semilla", str(semilla), "--bucle", "1-2"]
        )
        return armar_la_pasada(argumentos)[2].eventos

    assert tocado(1) != tocado(2), "dos semillas distintas tocan lo mismo"
    assert tocado(7) == tocado(7), "la misma semilla no es reproducible"


def test_el_plan_del_escaparate_nunca_pide_click():
    """El click abre un dispositivo de SALIDA de audio, y aqui no se abre ninguno.

    El escaparate tiene que poder correr en una maquina sin altavoces y dentro de un
    script sin que eso cambie lo que mide. No hay bandera para encenderlo: no es un
    olvido.
    """
    _, _, _, plan = armar_la_pasada(_analizador_de_argumentos().parse_args([]))

    assert plan.con_click is False
    assert "--click" not in _analizador_de_argumentos().format_help()


@pytest.mark.parametrize(
    "linea",
    [
        ["--perfil", "virtuoso"],
        ["--bucle", "9-2"],
        ["--tempo", "0"],
        ["--repeticiones", "0"],
        ["--cuenta-atras", "-1"],
        ["--bucle", "900"],
    ],
)
def test_una_pasada_imposible_se_rechaza_antes_de_levantar_nada(linea):
    """Lo que no se puede tocar se rechaza al armarlo, no al mitad de la pasada.

    Importa que sea ANTES: `armar_la_pasada` corre antes de que `main` abra un
    puerto o un dispositivo, asi que un tramo que la pieza no tiene o un tempo
    imposible salen como un mensaje y un codigo 2, no como un servidor levantado
    sobre una demostracion que no existe.
    """
    argumentos = _analizador_de_argumentos().parse_args(linea)

    with pytest.raises(ValueError):
        armar_la_pasada(argumentos)


@pytest.mark.parametrize(
    ("linea", "opcion", "recibido"),
    [
        (["--semilla", "-7"], "--semilla", "-7"),
        (["--puerto", "99999"], "--puerto", "99999"),
        (["--puerto", "0"], "--puerto", "0"),
        (["--puerto", "-1"], "--puerto", "-1"),
    ],
)
def test_un_numero_imposible_se_rechaza_nombrando_su_opcion(linea, opcion, recibido):
    """El mensaje NOMBRA la opcion y el valor recibido, como todo el resto del modulo.

    Los dos defectos que esto cierra los midio el revisor por el camino del
    usuario:

    - `--semilla -7` salia con «No se puede montar la demostracion: expected
      non-negative integer», que es el texto crudo de
      `numpy.random.default_rng` y no nombra la opcion. Quien lo lee no sabe cual
      de los seis numeros de su linea de ordenes es el malo.
    - `--puerto 99999` no se rechazaba: `uvicorn` fallaba DENTRO del hilo demonio,
      `_esperar_al_servidor` agotaba sus 15 s y el escaparate aconsejaba «si el
      puerto esta ocupado, prueba con --puerto», que es justo lo que el usuario
      acababa de hacer. El error de verdad (`[Errno 8]`) salia por el logger de
      uvicorn, mezclado con lo demas.

    El modelo es `leer_bucle`, que mete el texto recibido en el mensaje para que
    quien escribio un guion largo pueda ver la diferencia.
    """
    argumentos = _analizador_de_argumentos().parse_args(linea)

    with pytest.raises(ValueError) as fallo:
        armar_la_pasada(argumentos)

    mensaje = str(fallo.value)
    assert opcion in mensaje, f"el mensaje no nombra la opcion: {mensaje!r}"
    assert recibido in mensaje, f"el mensaje no trae el valor recibido: {mensaje!r}"
    assert "non-negative" not in mensaje, "ni una palabra en ingles de numpy"


def test_el_puerto_imposible_se_rechaza_sin_esperar_al_servidor(monkeypatch):
    """Y se rechaza ANTES de los 15 s: ese era la mitad del coste del defecto.

    `armar_la_pasada` corre antes de que `main` levante nada, asi que la
    comprobacion del puerto ahorra el arranque entero del servidor y la espera.
    """
    monkeypatch.setattr(
        "herramientas.gemelo._correr_la_demostracion",
        lambda *argumentos, **nombrados: pytest.fail(
            "con un puerto imposible no se levanta nada"
        ),
    )

    codigo = main(["--puerto", "99999"])

    assert codigo == 2


def test_los_valores_de_fabrica_de_la_linea_de_ordenes():
    """Lo que sale sin pasar ni un argumento: la demostracion, perfecta, en 8420.

    Son los valores que la orden del brief usa, y por eso estan afirmados: si el
    puerto o el perfil por omision cambiaran, la orden documentada dejaria de
    hacer lo que dice y nadie se enteraria.
    """
    argumentos = _analizador_de_argumentos().parse_args([])

    assert argumentos.pieza is None
    assert argumentos.perfil == "perfecto"
    assert argumentos.tempo == 1.0
    assert argumentos.bucle is None
    assert argumentos.repeticiones == 1
    assert argumentos.cuenta_atras == 0
    assert argumentos.semilla == 0
    assert argumentos.puerto == 8420
    assert argumentos.salir_al_acabar is False


def test_salir_al_acabar_es_un_interruptor_y_los_demas_se_leen_enteros():
    """La linea de ordenes completa del brief se lee, y cada cosa en su sitio."""
    argumentos = _analizador_de_argumentos().parse_args(
        [
            "--pieza", str(RUTA_DE_EJEMPLO),
            "--perfil", "caos",
            "--tempo", "0.6",
            "--bucle", "3-7",
            "--repeticiones", "4",
            "--cuenta-atras", "2",
            "--semilla", "9",
            "--puerto", "9100",
            "--salir-al-acabar",
        ]
    )

    assert argumentos.pieza == str(RUTA_DE_EJEMPLO)
    assert argumentos.perfil == "caos"
    assert argumentos.tempo == 0.6
    assert leer_bucle(argumentos.bucle) == (3, 7)
    assert argumentos.repeticiones == 4
    assert argumentos.cuenta_atras == 2
    assert argumentos.semilla == 9
    assert argumentos.puerto == 9100
    assert argumentos.salir_al_acabar is True


def test_el_analizador_no_tiene_argumentos_posicionales():
    """Todo se pide por nombre: una ruta suelta no es una pieza.

    Es lo que hace que `python -m herramientas.gemelo mi_cancion.gp5` falle
    diciendo que sobra un argumento, en vez de ignorarlo en silencio y tocar la
    demostracion mientras el usuario cree estar oyendo su cancion.
    """
    analizador = _analizador_de_argumentos()

    posicionales = [
        accion for accion in analizador._actions if not accion.option_strings
    ]

    assert posicionales == []


# ---------------------------------------------------------------------------
# El PEGAMENTO: `main`, `_seguir_la_pasada` y `_esperar_al_servidor`.
#
# Estas pruebas existen porque faltaban, y faltaban de la peor manera: tres
# mutantes del revisor sobrevivian las 39 pruebas anteriores, y uno de ellos
# -`if False:` en `--salir-al-acabar`- borra el requisito central del brief. Las
# 39 exigian mucho de las piezas separables y nada del cableado, que es donde
# vive cada decision de integracion.
#
# NINGUNA levanta servidor: lo que se sustituye es `_leer_json`, que es la unica
# linea del modulo que habla por la red. Levantar `uvicorn` abriria un puerto de
# la maquina, y un puerto ocupado pondria la suite roja por algo que no tiene nada
# que ver con lo que mide.
# ---------------------------------------------------------------------------

# Cada cuanto cambia de cuadro el guion de los estados publicados.
#
# Cincuenta milisegundos, y el numero esta entre dos cotas que hay que respetar a
# la vez. Por abajo: tiene que ser VARIAS lecturas del escaparate (8,3 ms a 120 Hz)
# para que un cuadro no se pueda saltar por el temblor de los hilos; con 16,7 ms la
# prueba era inestable en la suite entera -medido, un cuadro perdido- aunque
# pasara aislada. Por arriba: tiene que ser bastante MENOR que la lectura del
# mutante que se quiere matar (200 ms a 5 Hz), para que un lector lento se salte
# cuadros enteros por construccion y no por suerte. 50 ms son seis lecturas buenas
# por cuadro y un cuarto de la lectura del mutante.
PASO_DEL_GUION_S = 0.05

# Lo mas que el muestreo del escaparate puede añadirle de mediana al desfase que el
# veredicto publica.
#
# MEDIDO sobre este mismo guion, tres pasadas por ritmo:
#
#     120 Hz (el del escaparate)   2,8  3,4  4,1  ms
#      30 Hz (el del WebSocket)   12,9 15,2 16,6  ms
#       5 Hz (el mutante)         77,8 81,0 82,6  ms
#
# **ESTE TECHO YA NO SE AFIRMA, y la tabla de arriba explica por que se intento.**
# Quince milisegundos eran cuatro veces la mediana medida, y aun asi la prueba fallo
# una de cada pocas pasadas cuando la maquina estaba cargada -lo cazo el
# implementador de la etapa 3e corriendo un arnes de mutantes al mismo tiempo-. Es
# exactamente el defecto que el ruling 29 de la 3d prohibio y que aqui sobrevivio:
# una asercion cuyo valor de referencia se midio en una maquina EN REPOSO. Un techo
# generoso no arregla eso, solo lo hace mas raro, y una prueba que falla a veces
# ensena a desconfiar de la suite entera.
#
# La prueba quedo partida en los dos trabajos que hacia a la vez (ver
# `test_seguir_la_pasada_lee_mas_fino_de_lo_que_mide`):
#   - el MECANISMO se afirma contra la cadencia que esa misma pasada logro;
#   - el REGIMEN se afirma contra la constante, que no tiene sensibilidad temporal.
# La tabla se queda porque es la medicion que justifica el suelo del regimen.
#
# El suelo de lecturas por segundo por debajo del cual el escaparate deja de medir
# lo que cree medir. 60 Hz es el doble del ritmo del WebSocket (30 Hz) y doce veces
# el regimen del mutante (5 Hz).
LECTURAS_POR_SEGUNDO_MINIMAS = 60.0


def _nota_publicada(indice: int, midi: int = 55) -> dict:
    """Una `NotaTocada` tal y como el servidor la publica en `/api/piezas/estado`."""
    return {
        "indice": indice,
        "midi": midi,
        "nombre": "G3",
        "cents": 0.0,
        "desfase_s": 0.0,
        "clasificacion": "a_tiempo",
        "acertada": True,
        "afinada": True,
    }


class ServidorDeGuion:
    """Un `/api/piezas/estado` de mentira cuyo contenido depende del RELOJ.

    **ACUMULA, como el carril de verdad**, y la version anterior no: publicaba cada
    nota un cuadro y la tiraba, diciendo que era «lo que hace `SesionCarril`». No lo
    es, y lo comprobo el re-revisor. Rastreado: `SesionCarril._instantanea` publica
    `estado.a_dict()`, que trae `tocadas=tuple(self._tocadas)`
    (`nucleo/piezas/seguimiento.py:420`), y `_tocadas` **solo se poda en
    `olvidar_tramo`** (`:404`), al que se llega por `_dar_la_vuelta` del bucle, por
    `saltar_al_compas` o por `cambiar_plan` -o sea, la vuelta de un bucle o una
    accion del usuario-. La demostracion corre con `en_bucle=False`, asi que **en
    una pasada derecha no se tira nada** y una nota publicada en el cuadro N sigue
    publicada hasta el final.

    Asi que el ritmo de lectura NO importa por perder notas. Importa por el
    INSTANTE: `RecolectorDeLaSesion` anota `instante_pasada_s` **de la primera
    lectura en que ve la nota**, de modo que leer despacio empuja ese instante mas
    tarde, sube la mediana del desfase y acerca el veredicto al techo de 250 ms del
    detector. Medido en la ejecucion real a 5 Hz: **no se pierde ni una** de las 48
    notas, pero la mediana sube de +181,9 a +226,1 ms y aparecen 37 perdidas por
    emparejamiento. Ese es el mecanismo, y es el que estas pruebas afirman ahora.

    El guion se indexa por tiempo transcurrido y no por numero de llamada, para que
    un lector que lea la mitad de veces vea los cuadros mas tarde y no los mismos
    cuadros al mismo ritmo.

    `instante_s` NO se cuantiza al cuadro: es el tiempo transcurrido tal cual, que
    es lo que hace el cabezal de verdad. De esa forma el retraso que el muestreo
    introduce se puede medir -es `instante_s` de la lectura menos el instante en que
    la nota aparecio- en vez de quedar escondido en el redondeo del cuadro.
    """

    def __init__(
        self,
        notas_antes: int = 8,
        notas_tras_completar: int = 1,
        cuadros_hasta_completar: int = 10,
    ) -> None:
        self.notas_antes = notas_antes
        self.notas_tras_completar = notas_tras_completar
        self.cuadros_hasta_completar = cuadros_hasta_completar
        self.arranque = time.monotonic()
        self.peticiones: list[str] = []

    def instante_de_la_nota(self, indice: int) -> float:
        """Cuando aparece la nota `indice`, en el reloj de la pasada del guion.

        Las de antes de completarse, una por cuadro desde el cero; las de despues,
        una por cuadro desde el cuadro en que la pasada se completa.
        """
        if indice < self.notas_antes:
            return indice * PASO_DEL_GUION_S
        puesto = indice - self.notas_antes
        return (self.cuadros_hasta_completar + puesto) * PASO_DEL_GUION_S

    def __call__(self, url: str, limite_s: float = 5.0) -> dict:
        self.peticiones.append(url)
        transcurrido = time.monotonic() - self.arranque
        cuadro = int(transcurrido / PASO_DEL_GUION_S)
        completado = cuadro >= self.cuadros_hasta_completar
        # ACUMULADAS: todas las que ya aparecieron siguen publicadas.
        publicadas = self.notas_antes + self.notas_tras_completar
        tocadas = [
            _nota_publicada(indice)
            for indice in range(publicadas)
            if transcurrido >= self.instante_de_la_nota(indice)
        ]
        return {
            "repeticion": 1,
            "instante_s": round(transcurrido, 4),
            "tocadas": tocadas,
            "completado": completado,
        }


def test_seguir_la_pasada_lee_mas_fino_de_lo_que_mide(monkeypatch):
    """**Mata el mutante `LECTURAS_POR_SEGUNDO = 5`, y por el mecanismo de verdad.**

    Lo que el ritmo de lectura decide no es cuantas notas se recogen -el carril
    acumula, asi que no se pierde ninguna- sino **con que instante se anotan**:
    `RecolectorDeLaSesion` apunta el reloj del cabezal de la primera lectura en que
    ve la nota, de modo que cada lectura que se tarda en mirar se suma al desfase
    que el veredicto publica. Medido en la pasada real a 5 Hz: 48 de 48 notas
    recogidas y la mediana del desfase subiendo de +181,9 a +226,1 ms, a 24 ms del
    techo de 250 ms del detector.

    **Esta prueba hacia dos trabajos con una sola asercion, y por eso era
    intermitente.** Afirmaba la mediana del retraso contra un techo de 15 ms medido
    en una maquina en reposo, que es justo lo que el ruling 29 de la etapa 3d
    prohibio: con la maquina cargada -un arnes de mutantes corriendo al lado- las
    lecturas se retrasan, la mediana sube y la prueba se pone roja sin que nada se
    haya roto. Ahora son dos aserciones y cada una hace un trabajo:

    1. **El MECANISMO, independiente de la carga.** El recolector anota el instante
       de la PRIMERA lectura que ve la nota, asi que el retraso esta acotado por UN
       intervalo de lectura. Se mide el intervalo que esta misma pasada logro
       -tiempo transcurrido entre las lecturas que de verdad se hicieron- y se exige
       la mediana contra el. Si la maquina va lenta, las dos cifras crecen juntas y
       la relacion aguanta; lo que no aguanta es que el recolector anote el instante
       equivocado, que es el defecto que importa.
    2. **El REGIMEN, sin sensibilidad temporal ninguna.** `LECTURAS_POR_SEGUNDO`
       tiene que estar por encima de `LECTURAS_POR_SEGUNDO_MINIMAS`. Es una
       asercion sobre una constante, asi que mata el mutante `= 5` **siempre**, con
       la maquina a cero o a tope. La tabla medida que justifica ese suelo esta
       junto a la constante.
    """
    assert LECTURAS_POR_SEGUNDO >= LECTURAS_POR_SEGUNDO_MINIMAS, (
        f"el escaparate lee a {LECTURAS_POR_SEGUNDO:.0f} Hz y por debajo de "
        f"{LECTURAS_POR_SEGUNDO_MINIMAS:.0f} deja de medir lo que cree medir: el "
        "instante que publica es el de la lectura, no el de la nota"
    )

    guion = ServidorDeGuion(notas_antes=8, notas_tras_completar=0)
    monkeypatch.setattr("herramientas.gemelo._leer_json", guion)

    comienzo = time.monotonic()
    recolector, completada = _seguir_la_pasada("http://127.0.0.1:0", duracion_s=0.5)
    transcurrido_ms = 1000.0 * (time.monotonic() - comienzo)

    assert completada is True
    reportes = recolector.registro.reportes
    recogidos = sorted(reporte.tocada.indice for reporte in reportes)
    assert recogidos == list(range(8)), (
        f"el carril acumula, asi que no se puede perder ninguna: {recogidos}"
    )

    retrasos_ms = [
        1000.0
        * (
            reporte.instante_pasada_s
            - guion.instante_de_la_nota(reporte.tocada.indice)
        )
        for reporte in reportes
    ]
    # **Por que no se compara contra 0.0 pelado.** Los dos lados de la resta son
    # flotantes calculados por caminos distintos -`instante_s` sale de
    # `round(transcurrido, 4)` y el instante de la nota de `indice *
    # PASO_DEL_GUION_S`-, asi que una nota mirada exactamente en el instante en que
    # aparece da un retraso de -5,5e-14 ms en vez de cero. Medido: 2 de 25 pasadas.
    # Eso no es que el recolector mire al pasado, es el ultimo bit de un float, y
    # una prueba que se pone roja por el ultimo bit de un float ensena a desconfiar
    # de la suite. La cota es ruido de coma flotante y nada mas: ocho ordenes de
    # magnitud por debajo del cuanto de 0,1 ms con que el guion publica el reloj.
    RUIDO_DE_COMA_FLOTANTE_MS = 1e-6
    assert min(retrasos_ms) >= -RUIDO_DE_COMA_FLOTANTE_MS, (
        f"el instante anotado no puede ser anterior a que la nota apareciera, y "
        f"el minimo salio {min(retrasos_ms):.3e} ms"
    )
    # El intervalo que ESTA pasada logro, no el que la constante pide: es lo que
    # hace la asercion independiente de la carga. Con la maquina lenta crecen los
    # dos lados a la vez.
    intervalo_logrado_ms = transcurrido_ms / len(guion.peticiones)
    mediana_ms = statistics.median(retrasos_ms)
    assert mediana_ms <= intervalo_logrado_ms, (
        f"el recolector anota el instante de la PRIMERA lectura que ve la nota, "
        f"asi que el retraso esta acotado por un intervalo de lectura: esta pasada "
        f"logro {intervalo_logrado_ms:.1f} ms de intervalo "
        f"({len(guion.peticiones)} lecturas en {transcurrido_ms:.0f} ms) y la "
        f"mediana del retraso salio {mediana_ms:.1f} ms"
    )

    assert guion.peticiones, "no se llamo al endpoint"
    assert all(url.endswith("/api/piezas/estado") for url in guion.peticiones), (
        "la pasada se sigue por el mismo endpoint que lee el navegador"
    )


def test_seguir_la_pasada_sigue_leyendo_despues_de_completarse(monkeypatch):
    """La cola: los ultimos ataques se publican DESPUES de que el cabezal acabe.

    **Mata el mutante `COLA_TRAS_COMPLETAR_S = 0`.** La cadena tarda unos 190 ms en
    publicar un ataque, asi que la ultima nota del tramo aparece cuando la pasada ya
    esta completada. Sin cola se perderia SIEMPRE, y el escaparate acusaria a la
    cadena de algo que hizo bien.

    Esta SI es una perdida de notas, y no se contradice con que el carril acumule
    (ver `ServidorDeGuion`): lo que acumula se publica mientras alguien lea, y sin
    cola nadie lee despues del final. La nota no se tira; es que nadie la mira.
    """
    guion = ServidorDeGuion(
        notas_antes=4, notas_tras_completar=2, cuadros_hasta_completar=5
    )
    monkeypatch.setattr("herramientas.gemelo._leer_json", guion)

    recolector, completada = _seguir_la_pasada("http://127.0.0.1:0", duracion_s=0.2)

    assert completada is True
    recogidos = sorted(reporte.tocada.indice for reporte in recolector.registro.reportes)
    assert recogidos == [0, 1, 2, 3, 4, 5], (
        "las notas publicadas tras completarse la pasada tambien se recogen; "
        f"se recogieron {recogidos}"
    )


def test_seguir_la_pasada_se_rinde_si_la_pasada_no_se_completa(monkeypatch):
    """Una pasada que no acaba no deja el escaparate colgado para siempre.

    Devuelve `completada=False`, y `main` lo traduce en un codigo distinto de cero:
    un veredicto sobre una pasada a medias no dice nada de la cadena.
    """
    estado = {"repeticion": 1, "instante_s": 0.0, "tocadas": [], "completado": False}
    monkeypatch.setattr(
        "herramientas.gemelo._leer_json", lambda url, limite_s=5.0: estado
    )
    monkeypatch.setattr("herramientas.gemelo.MARGEN_DE_LA_PASADA_S", 0.1)
    monkeypatch.setattr("herramientas.gemelo.COLA_TRAS_COMPLETAR_S", 0.0)

    _, completada = _seguir_la_pasada("http://127.0.0.1:0", duracion_s=0.0)

    assert completada is False


def test_esperar_al_servidor_distingue_que_contesta_de_que_acepta(monkeypatch):
    """Se comprueba que el servidor CONTESTA la API, no que el puerto acepte.

    `uvicorn` abre el socket antes de tener la aplicacion lista, asi que una pasada
    arrancada contra un puerto que acepta pero no responde pierde los primeros
    cuadros. Por eso se pide `/api/diagnostico` y no se abre un socket a pelo.
    """
    intentos = []

    def contesta_a_la_tercera(url: str, limite_s: float = 5.0) -> dict:
        intentos.append(url)
        if len(intentos) < 3:
            raise urllib.error.URLError("conexion rechazada")
        return {"estado": "ok"}

    monkeypatch.setattr("herramientas.gemelo._leer_json", contesta_a_la_tercera)

    assert _esperar_al_servidor("http://127.0.0.1:0", limite_s=5.0) is True
    assert len(intentos) == 3
    assert all(url.endswith("/api/diagnostico") for url in intentos)


def test_esperar_al_servidor_se_rinde_y_lo_dice(monkeypatch):
    """Si no contesta nunca, se agota el limite y se devuelve False.

    Quien llama tiene que poder decir «el servidor no contesto» en vez de arrancar
    una pasada contra nada.
    """

    def nunca(url: str, limite_s: float = 5.0) -> dict:
        raise urllib.error.URLError("conexion rechazada")

    monkeypatch.setattr("herramientas.gemelo._leer_json", nunca)

    assert _esperar_al_servidor("http://127.0.0.1:0", limite_s=0.2) is False


class DemostracionDeMentira:
    """Un doble de `_correr_la_demostracion`: devuelve el veredicto que se le diga.

    Es el seam que permite probar las decisiones de `main` -el codigo de salida y
    el quedarse vivo- sin levantar `uvicorn`, sin abrir un puerto y sin pagar los
    31 s de la pieza de demostracion.

    **GUARDA LO QUE RECIBE, y la version anterior no.** Contaba las veces y tiraba
    los cuatro argumentos, asi que nadie comprobaba que llegaran: tres mutantes del
    re-revisor sobrevivian la suite entera por esto -el puerto cambiado por el de
    fabrica (o sea, `--puerto` ignorado), el plan cambiado por `None` (y con el
    `--tempo`, `--bucle`, `--repeticiones` y `--cuenta-atras` tirados de golpe) y
    `completada` cambiado por `True` al imprimir-. Un doble que no mira lo que le
    dan solo prueba que lo llaman.
    """

    def __init__(self, veredicto, completada: bool = True) -> None:
        self.veredicto = veredicto
        self.completada = completada
        self.veces = 0
        self.recibido: list[dict] = []

    def __call__(
        self, pieza, interpretacion, plan, puerto, al_acabar, fondo=None, altavoces=False
    ):
        self.veces += 1
        self.recibido.append(
            {
                "pieza": pieza,
                "interpretacion": interpretacion,
                "plan": plan,
                "puerto": puerto,
                "al_acabar": al_acabar,
                "fondo": fondo,
                "altavoces": altavoces,
            }
        )
        if self.veredicto is None:
            return None
        # LLAMA A `al_acabar`, como la de verdad y en el mismo sitio: es ahi donde
        # el escaparate imprime el resumen y espera a que el usuario mire, con el
        # servidor todavia en pie. Un doble que no lo llamara haria pasar un `main`
        # que nunca imprimiera nada.
        al_acabar(self.veredicto, self.completada)
        return self.veredicto, self.completada

    @property
    def ultimo(self) -> dict:
        """Lo que se le paso en la ultima llamada."""
        assert self.recibido, "no se la llamo ni una vez"
        return self.recibido[-1]


def _main_con_doble(monkeypatch, argv, veredicto, completada=True):
    """Corre `main` con la demostracion y la espera sustituidas. Devuelve lo visto."""
    demostracion = DemostracionDeMentira(veredicto, completada)
    miradas = []
    monkeypatch.setattr("herramientas.gemelo._correr_la_demostracion", demostracion)
    monkeypatch.setattr(
        "herramientas.gemelo._quedarse_vivo", lambda: miradas.append(True)
    )
    codigo = main(argv)
    return codigo, demostracion, miradas


def test_sin_salir_al_acabar_el_escaparate_se_queda_vivo(monkeypatch, capsys):
    """**El requisito central del brief, y no tenia ni una prueba.**

    Mata el mutante `if False:` sobre `--salir-al-acabar`: con ese cambio el
    escaparate termina siempre solo, que es lo contrario de lo que el brief pide y
    de lo que la cabecera del modulo promete. Su razon de ser es que alguien MIRE:
    un escaparate que se cierra en cuanto acaba la pasada no se puede mirar.
    """
    codigo, demostracion, miradas = _main_con_doble(
        monkeypatch, [], _veredicto()
    )

    assert demostracion.veces == 1
    assert miradas == [True], "sin --salir-al-acabar el escaparate tiene que quedarse"
    assert codigo == 0
    assert "LIMPIO" in capsys.readouterr().out


def test_con_salir_al_acabar_el_escaparate_termina(monkeypatch, capsys):
    """Y con la bandera termina, que es la forma de usarlo desde un script."""
    codigo, demostracion, miradas = _main_con_doble(
        monkeypatch, ["--salir-al-acabar"], _veredicto()
    )

    assert demostracion.veces == 1
    assert miradas == [], "con --salir-al-acabar no se espera a nadie"
    assert codigo == 0
    assert "LIMPIO" in capsys.readouterr().out


@pytest.mark.parametrize(
    "veredicto, completada, esperado",
    [
        (_veredicto(), True, 0),
        (_veredicto(excluidas=((1, 3),)), True, 0),
        (_veredicto(perdidas=((1, 2),)), True, 1),
        (_veredicto(mal_adjudicadas=((1, 2, 60),)), True, 1),
        (_veredicto(), False, 1),
    ],
)
def test_el_codigo_que_main_devuelve_sale_del_veredicto(
    monkeypatch, veredicto, completada, esperado
):
    """**Mata el mutante `codigo = 0` fijo en `main`.**

    `codigo_de_salida` ya estaba probada sobre un `Veredicto` armado a mano, pero el
    CABLEADO -que `main` use esa funcion y no se invente el numero- no lo miraba
    nadie. El ultimo caso es el que la funcion sola no puede cubrir: una pasada que
    no se completa devuelve distinto de cero aunque el veredicto salga limpio,
    porque un veredicto sobre media pasada no dice nada de la cadena.
    """
    codigo, _, _ = _main_con_doble(
        monkeypatch, ["--salir-al-acabar"], veredicto, completada=completada
    )

    assert codigo == esperado


def test_si_la_demostracion_no_se_puede_montar_main_devuelve_dos(monkeypatch, capsys):
    """Un fallo de montaje no es un veredicto sucio: es otro codigo.

    Dos y no uno, para que un script pueda distinguir «la cadena tiene hallazgos»
    de «la demostracion no llego a correr». Y no se imprime ningun resumen: un
    resumen de una pasada que no existio seria el peor informe posible.
    """
    codigo, _, miradas = _main_con_doble(
        monkeypatch, ["--salir-al-acabar"], None
    )

    assert codigo == 2
    assert miradas == [], "sin pasada no hay nada que mirar"
    assert "GEMELO" not in capsys.readouterr().out


def test_una_linea_de_ordenes_imposible_no_llega_a_levantar_nada(monkeypatch, capsys):
    """El tramo del reves se rechaza antes de tocar el puerto, con codigo 2."""
    demostracion = DemostracionDeMentira(_veredicto())
    monkeypatch.setattr("herramientas.gemelo._correr_la_demostracion", demostracion)

    codigo = main(["--bucle", "9-2", "--salir-al-acabar"])

    assert codigo == 2
    assert demostracion.veces == 0, "no se monta nada con una linea de ordenes mala"
    assert "9-2" in capsys.readouterr().out


def test_main_le_pasa_a_la_demostracion_el_puerto_y_el_plan_que_se_pidieron():
    """Lo que `main` monta tiene que LLEGAR a la demostracion, y nadie lo miraba.

    Tres mutantes del re-revisor vivian aqui: cambiar `argumentos.puerto` por el
    puerto de fabrica -o sea, ignorar `--puerto` por completo-, y cambiar el `plan`
    por `None`, que tira de golpe `--tempo`, `--bucle`, `--repeticiones` y
    `--cuenta-atras`. Los dos pasaban las 55 pruebas porque el doble contaba las
    llamadas y tiraba los argumentos.

    El plan se compara contra el que `armar_la_pasada` construye con la misma linea
    de ordenes, que es la fuente de verdad: comparar campo a campo contra numeros
    escritos aqui seria una segunda copia de la regla.
    """
    linea = [
        "--puerto", "9321",
        "--tempo", "0.6",
        "--bucle", "2-3",
        "--repeticiones", "2",
        "--cuenta-atras", "1",
        "--salir-al-acabar",
    ]
    demostracion = DemostracionDeMentira(_veredicto())
    with pytest.MonkeyPatch.context() as parche:
        parche.setattr("herramientas.gemelo._correr_la_demostracion", demostracion)
        main(linea)

    esperados = armar_la_pasada(_analizador_de_argumentos().parse_args(linea))
    pieza_esperada, _, _, plan_esperado = esperados

    assert demostracion.ultimo["puerto"] == 9321, "se ignoro --puerto"
    assert demostracion.ultimo["plan"] == plan_esperado, (
        "el plan que llega a la demostracion no es el que se pidio"
    )
    assert demostracion.ultimo["pieza"] == pieza_esperada
    # La interpretacion no se compara por igualdad -lleva un array de muestras
    # dentro-, asi que se comprueba que es la del tramo y el tempo pedidos.
    recibida = demostracion.ultimo["interpretacion"]
    assert (recibida.primer_compas, recibida.ultimo_compas) == (2, 3)
    assert recibida.factor_tempo == 0.6
    assert recibida.repeticiones == 2


def test_el_resumen_que_main_imprime_dice_si_la_pasada_se_completo(monkeypatch, capsys):
    """`completada` tiene que LLEGAR al resumen, y tampoco lo miraba nadie.

    Mata el mutante que pasa `True` fijo a `resumen`: el escaparate podia imprimir
    «pasada : completada» sobre una pasada que no se completo mientras devolvia 1,
    que es la contradiccion mas desconcertante que puede tener este informe -el
    numero dice que algo fue mal y el texto dice que todo acabo bien-.
    """
    codigo, _, _ = _main_con_doble(
        monkeypatch, ["--salir-al-acabar"], _veredicto(), completada=False
    )
    salida_cortada = capsys.readouterr().out

    codigo_entero, _, _ = _main_con_doble(
        monkeypatch, ["--salir-al-acabar"], _veredicto(), completada=True
    )
    salida_entera = capsys.readouterr().out

    assert codigo == 1 and "SIN COMPLETAR" in salida_cortada
    assert "pasada  : completada" not in salida_cortada
    assert codigo_entero == 0 and "pasada  : completada" in salida_entera
    assert "SIN COMPLETAR" not in salida_entera


# ---------------------------------------------------------------------------
# Los dos defectos que la Task 16 encontro corriendo las ordenes del README como
# las corre el usuario, y que ni la revision, ni la re-revision, ni treinta y un
# mutantes vieron. Los dos son del contrato de `_correr_la_demostracion`.
# ---------------------------------------------------------------------------


class ServidorDeMentira:
    """Un doble del `uvicorn.Server`: solo lleva la cuenta de si se le apago.

    `should_exit` es el unico miembro que el escaparate le toca, y es por donde se
    observa el defecto: el servidor no puede estar apagado mientras el usuario
    todavia tiene algo que mirar.
    """

    def __init__(self) -> None:
        self.should_exit = False


class CarrilDeMentira:
    def __init__(self) -> None:
        self.iniciado = []
        self.detenido = 0
        # El orden en que se le hablo, para poder afirmarlo.
        self.llamadas: list = []

    def iniciar(self, pieza, plan) -> dict:
        self.iniciado.append((pieza, plan))
        self.llamadas.append("iniciar")
        return {}

    def cargar_acompanamiento(self, fondo) -> None:
        self.llamadas.append(("cargar_acompanamiento", fondo))

    def estado(self) -> dict:
        return {"acompanamiento_voces": 0, "acompanamiento_posible": True}

    def detener(self) -> None:
        self.detenido += 1


class SesionDeMentira:
    def __init__(self) -> None:
        self.detenida = 0

    def iniciar(self):
        return Diagnostico(
            estado="ok",
            mensaje="Dispositivo activo: Rocksmith USB Guitar Adapter (gemelo)",
            accion="",
            dispositivos=[],
        )

    def detener(self) -> None:
        self.detenida += 1


class CapturaDeMentira:
    total_capturado = 10**9


def _demostracion_sin_red(monkeypatch, completada=True):
    """Deja `_correr_la_demostracion` corriendo sin puerto, sin audio y sin esperas.

    Se sustituyen sus cinco colaboradores y se devuelve el `ServidorDeMentira`, que
    es lo que las dos pruebas del defecto miran. No se sustituye
    `_correr_la_demostracion`: es justo la funcion que se quiere ejercitar.
    """
    servidor = ServidorDeMentira()
    carril = CarrilDeMentira()
    sesion = SesionDeMentira()
    monkeypatch.setattr(
        "herramientas.gemelo._construir",
        lambda pieza, interpretacion, salida_fondo=None: (
            object(),
            sesion,
            carril,
            [CapturaDeMentira()],
        ),
    )
    monkeypatch.setattr(
        "herramientas.gemelo._levantar_el_servidor",
        lambda app, puerto: servidor,
    )
    monkeypatch.setattr("herramientas.gemelo._esperar_al_servidor", lambda base: True)
    monkeypatch.setattr(
        "herramientas.gemelo.esperar_la_cabecera",
        lambda captura, interpretacion, ventana: True,
    )
    seguimientos = []

    def seguir(base, duracion_s, repeticiones=1, traza=None):
        seguimientos.append(
            {"base": base, "duracion_s": duracion_s, "repeticiones": repeticiones}
        )
        return RecolectorDeLaSesion(), completada

    monkeypatch.setattr("herramientas.gemelo._seguir_la_pasada", seguir)
    return servidor, carril, sesion, seguimientos


def test_el_servidor_sigue_contestando_mientras_el_usuario_mira(monkeypatch, capsys):
    """**EL DEFECTO: el servidor moria en el instante del veredicto.**

    Medido por la Task 16 con un sondeo cada medio segundo sobre el escaparate de
    verdad: contestaba desde el segundo 0 y **dejaba de contestar a los 27,7 s**, el
    mismo instante en que se imprime el veredicto y el mensaje «la pantalla se queda
    donde esta para que puedas mirarla». Despues, «Connection refused» en `/`, en
    `/api/diagnostico` y en `/api/piezas/estado`.

    O sea que el usuario corria la orden, leia «abre esa direccion en el navegador»,
    abria el navegador cuando la pasada acababa -que es lo natural, porque el resumen
    acaba de aparecer- y no encontraba nada. La tarea 12 existe para que el usuario
    se vea tocar sin tocar: un escaparate cuyo servidor muere al imprimir el
    veredicto no cumple su unico proposito.

    La causa era de ORDEN: `_quedarse_vivo()` lo llamaba `main` DESPUES de que el
    `finally` de `_correr_la_demostracion` hubiera apagado uvicorn. Lo que se afirma
    aqui es ese orden: todo lo que el usuario tiene que leer y mirar ocurre mientras
    el servidor sigue contestando.
    """
    servidor, carril, sesion, _ = _demostracion_sin_red(monkeypatch)
    apagado_al_informar = []

    def informar(veredicto, completada, informe_del_fondo=None) -> None:
        apagado_al_informar.append(servidor.should_exit)

    resultado = _correr_la_demostracion(
        pieza_de_demostracion(),
        interpretar(pieza_de_demostracion(), PERFECTO, ultimo_compas=1),
        PlanDePasada(),
        8420,
        al_acabar=informar,
    )

    assert resultado is not None
    assert apagado_al_informar == [False], (
        "el servidor ya estaba apagado cuando se le dijo al usuario que mirara: "
        "esto es el defecto que la Task 16 midio"
    )
    # Y al salir de la funcion si se apaga, con el carril y la sesion detenidos.
    assert servidor.should_exit is True
    assert carril.detenido == 1
    assert sesion.detenida == 1


def test_con_salir_al_acabar_el_servidor_se_apaga_y_no_se_espera_a_nadie(
    monkeypatch, capsys
):
    """La otra mitad: con la bandera no se mira nada, asi que se apaga todo.

    Es lo que convierte la orden en algo usable desde un script, y lo que distingue
    el arreglo de «dejar el servidor abierto siempre»: la bandera sigue apagandolo
    limpio.
    """
    servidor, carril, sesion, _ = _demostracion_sin_red(monkeypatch)
    miradas = []
    monkeypatch.setattr(
        "herramientas.gemelo._quedarse_vivo", lambda: miradas.append(True)
    )

    codigo = main(["--salir-al-acabar", "--bucle", "1"])

    assert miradas == [], "con --salir-al-acabar no se espera a nadie"
    assert servidor.should_exit is True, "con la bandera el servidor tiene que apagarse"
    assert carril.detenido == 1
    assert sesion.detenida == 1
    assert codigo in (0, 1)
    assert "GEMELO" in capsys.readouterr().out


def test_sin_la_bandera_se_espera_con_el_servidor_todavia_en_pie(monkeypatch, capsys):
    """Y sin la bandera, `_quedarse_vivo` corre ANTES de apagar el servidor.

    Es la misma afirmacion que la prueba de arriba vista desde `main`, que es donde
    vive la decision de esperar: asi el orden queda afirmado en los dos sitios que
    lo pueden romper.
    """
    servidor, _, _, _ = _demostracion_sin_red(monkeypatch)
    apagado_al_esperar = []
    monkeypatch.setattr(
        "herramientas.gemelo._quedarse_vivo",
        lambda: apagado_al_esperar.append(servidor.should_exit),
    )

    main(["--bucle", "1"])

    assert apagado_al_esperar == [False], (
        "se dejo al usuario mirando una direccion que ya no contesta"
    )
    assert servidor.should_exit is True, "al salir del todo si se apaga"


def test_un_bucle_de_varias_vueltas_se_da_por_completado(monkeypatch):
    """**EL SEGUNDO DEFECTO: `--repeticiones > 1` nunca completaba.**

    Medido dos veces por la Task 16: `--bucle 2-3 --repeticiones 2` tardaba 23 s,
    sacaba `tocadas 16 de 48`, `SIN COMPLETAR` y codigo 1 aunque todo hubiera ido
    bien; la misma orden sin `--repeticiones` salia `completada` y `LIMPIO`.

    La causa: `armar_la_pasada` enciende `en_bucle` con varias vueltas, y un tramo en
    bucle **no publica `completado` nunca** -da la vuelta y sigue-, asi que
    `_seguir_la_pasada` esperaba hasta agotar `MARGEN_DE_LA_PASADA_S`.

    Lo que se afirma: con varias vueltas la pasada se da por acabada cuando el
    carril pasa de la ultima vuelta pedida, que es el unico momento en que se sabe
    que el bucle ya recorrio todo lo que el gemelo toco.
    """
    vueltas = []

    def carril_en_bucle(url: str, limite_s: float = 5.0) -> dict:
        # Un tramo en bucle: `completado` SIEMPRE False, y la vuelta subiendo.
        vueltas.append(len(vueltas))
        repeticion = 1 + len(vueltas) // 3
        return {
            "repeticion": repeticion,
            "instante_s": 0.1 * len(vueltas),
            "tocadas": [],
            "completado": False,
        }

    monkeypatch.setattr("herramientas.gemelo._leer_json", carril_en_bucle)
    monkeypatch.setattr("herramientas.gemelo.COLA_TRAS_COMPLETAR_S", 0.0)

    _, completada = _seguir_la_pasada(
        "http://127.0.0.1:0", duracion_s=0.2, repeticiones=2
    )

    assert completada is True, (
        "con --repeticiones 2 la pasada acaba al pasar de la vuelta 2, no al agotar "
        "la espera"
    )


def test_una_pasada_derecha_sigue_acabando_por_completado(monkeypatch):
    """Y con una sola vuelta nada cambia: se acaba por `completado`, como siempre.

    Es la mitad que impide que el arreglo del bucle se coma el camino normal: con
    `repeticiones=1` el estado publica `completado` y es eso lo que manda, sin
    esperar a que la vuelta cambie (que en una pasada derecha no cambia nunca).
    """
    estados = [
        {"repeticion": 1, "instante_s": 0.0, "tocadas": [], "completado": False},
        {"repeticion": 1, "instante_s": 0.1, "tocadas": [], "completado": True},
    ]
    leidos = []

    def por_turnos(url: str, limite_s: float = 5.0) -> dict:
        estado = estados[min(len(leidos), len(estados) - 1)]
        leidos.append(estado)
        return estado

    monkeypatch.setattr("herramientas.gemelo._leer_json", por_turnos)
    monkeypatch.setattr("herramientas.gemelo.COLA_TRAS_COMPLETAR_S", 0.0)

    _, completada = _seguir_la_pasada(
        "http://127.0.0.1:0", duracion_s=0.5, repeticiones=1
    )

    assert completada is True
    assert len(leidos) == 2, (
        "se acabo por `completado` en la segunda lectura, no por la cuenta de vueltas"
    )


def test_las_vueltas_pedidas_llegan_a_quien_sigue_la_pasada(monkeypatch):
    """`--repeticiones` tiene que llegar hasta `_seguir_la_pasada`, y no llegaba.

    **La escribi porque un mutante sobrevivio:** con las repeticiones clavadas al
    valor por omision, `_seguir_la_pasada` no sabria cuando se acabo el bucle y
    volveria el defecto que esta misma ronda arregla -«SIN COMPLETAR» con codigo 1
    sobre una pasada que fue bien-. Que el numero salga de la INTERPRETACION y no de
    los argumentos es a proposito: es la interpretacion la que sabe cuantas vueltas
    de audio se generaron, y es contra eso contra lo que hay que contar.
    """
    servidor, _, _, seguimientos = _demostracion_sin_red(monkeypatch)
    monkeypatch.setattr("herramientas.gemelo._quedarse_vivo", lambda: None)

    main(["--repeticiones", "3", "--bucle", "1", "--salir-al-acabar"])

    assert len(seguimientos) == 1
    assert seguimientos[0]["repeticiones"] == 3, (
        "las vueltas pedidas no llegaron a quien sigue la pasada: el bucle no sabria "
        "cuando acaba"
    )
    assert seguimientos[0]["base"] == "http://127.0.0.1:8420"
    assert servidor.should_exit is True


def test_el_ctrl_c_con_el_veredicto_firmado_devuelve_el_codigo_del_veredicto(
    monkeypatch, capsys
):
    """**EL DEFECTO DEL CAMINO POR OMISION: el proceso salia siempre con 2.**

    Medido por el revisor en una pasada real (puerto 8431): pasada completada,
    veredicto impreso con 13 perdidas, `Ctrl+C`, y el proceso devolvia **2**, que
    el docstring de `main` define como «la demostracion no llego a montarse».
    Con `--salir-al-acabar` el mismo caso devolvia 1. O sea que los tres codigos
    que `main` distingue a proposito se reducian a dos y el tercero mentia, justo
    en el modo por omision -el que existe para mirar- y el que el README
    documenta.

    La causa: el arreglo de la Task 16 metio `al_acabar` -y con el
    `_quedarse_vivo()`- DENTRO del `try` de `_correr_la_demostracion`, que es
    correcto y hace falta para que el servidor siga en pie. El efecto lateral es
    que el `Ctrl+C` con que el usuario cierra el escaparate entra por el
    `except KeyboardInterrupt` de esa funcion, que devolvia `None` sin mirar si ya
    habia un veredicto firmado.

    **Y NINGUNA PRUEBA PODIA VERLO**, que es la otra mitad del hallazgo: todas
    sustituian `_quedarse_vivo` por un `lambda` que VUELVE, y la funcion de verdad
    no vuelve nunca: espera un `Ctrl+C`. El doble que hacia la prueba posible era
    lo que escondia el defecto. Aqui el doble LANZA, que es lo que la de verdad
    hace.
    """
    servidor, carril, sesion, _ = _demostracion_sin_red(monkeypatch)

    def ctrl_c_del_usuario() -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("herramientas.gemelo._quedarse_vivo", ctrl_c_del_usuario)

    codigo = main(["--bucle", "1"])

    salida = capsys.readouterr().out
    assert "GEMELO" in salida, "el veredicto se imprimio antes del Ctrl+C"
    assert "CON HALLAZGOS" in salida, "y es un veredicto sucio: el registro va vacio"
    assert codigo == 1, (
        "con el veredicto ya firmado el codigo tiene que ser el del veredicto (1), "
        "no el 2 de «la demostracion no llego a montarse»"
    )
    # Y el escaparate se cierra limpio igual que con la bandera.
    assert servidor.should_exit is True
    assert carril.detenido == 1
    assert sesion.detenida == 1


def test_el_ctrl_c_antes_del_veredicto_sigue_valiendo_dos(monkeypatch, capsys):
    """La otra mitad: interrumpir ANTES del veredicto sigue siendo «no se monto».

    Es la condicion que mantiene al codigo 2 significando algo. Sin ella el
    arreglo de arriba se convertiria en «el 2 no sale nunca», que es el mismo
    defecto con el signo cambiado.
    """
    _demostracion_sin_red(monkeypatch)

    def ctrl_c_a_media_pasada(base, duracion_s, repeticiones=1, traza=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "herramientas.gemelo._seguir_la_pasada", ctrl_c_a_media_pasada
    )
    monkeypatch.setattr(
        "herramientas.gemelo._quedarse_vivo",
        lambda: pytest.fail("sin veredicto no hay nada que mirar"),
    )

    codigo = main(["--bucle", "1"])

    assert codigo == 2
    assert "GEMELO" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# El escaparate toca con fondo (Task 7).
#
# Dos banderas: `--con-acompanamiento` CAPTURA (es la de por omision: el
# escaparate corre sin hardware y el sandbox no abre audio) y `--altavoces` abre
# la salida de verdad. Esta ultima NO se ejecuta nunca aqui: se comprueba CUAL
# salida se eligio.
#
# **Una leccion de esta etapa, aplicada a cada prueba: la asercion tiene que
# mirar un valor en el que el mutante y el original DIFIEREN en el estado donde
# la prueba EMPIEZA.** Las pruebas del desfase parten de bloques cortados a
# mano en un sitio y de un cabezal puesto en OTRO (40 ms de diferencia): si el
# cabezal coincidiera con donde se corto, un desfase calculado contra «donde el
# acompañante cree estar» tambien daria 0 y no se notaria.
# ---------------------------------------------------------------------------

FS_FONDO = 48000
TAM_BLOQUE = 1024


_REFERENCIA_REAL: list[np.ndarray] = []


def _referencia() -> np.ndarray:
    """La pieza de demostracion RENDERIZADA DE VERDAD, a 48 kHz y pico 1.

    **Ya no es ruido blanco**, que es el unico regimen sin ambiguedad: el fondo
    real es cuasi-periodico y hay posiciones vecinas que se le parecen casi tanto
    como la buena. El localizador se prueba en el caso dificil. Se renderiza una
    vez por proceso.
    """
    if not _REFERENCIA_REAL:
        pieza = pieza_de_demostracion()
        _REFERENCIA_REAL.append(
            renderizar(
                (voz_de_tu_parte(pieza),),
                tempo=pieza.tempo,
                frecuencia_muestreo=FS_FONDO,
            ).muestras
        )
    return _REFERENCIA_REAL[0]


def _bloques_cortados(referencia, inicios_s, ganancia=0.6):
    """Los bloques que escribiria el acompañante si estuviera en `inicios_s`.

    **COMO SALEN DE VERDAD, NO COMO SALEN LIMPIOS.** El acompañante corta con
    `PiezaRenderizada.rodaja` en un indice de muestra entero y arbitrario, y un
    bloque que cambia de ganancia lleva una RAMPA lineal de 1,0 a la ganancia
    pedida repartida por sus 1024 muestras (`Acompanante._con_ganancia`). Cortarlos
    exactos y con ganancia constante probaba el localizador en el unico caso en
    que el parecido es 1,0000 y el impostor mejor no puede empatar. (Un corte a
    media muestra, por interpolacion, tambien lo probe: no es como salen los
    bloques de produccion y el localizador se pierde ahi -13 a 60 ms de error-;
    ver el informe.)
    """
    rampa = np.linspace(1.0, ganancia, TAM_BLOQUE)
    bloques = []
    for t in inicios_s:
        desde = int(t * FS_FONDO)
        bloques.append((referencia[desde : desde + TAM_BLOQUE] * rampa).astype(np.float32))
    return bloques


def _traza_recta(pps, hasta_s=3.0, paso_s=0.01):
    """El cabezal de una pasada derecha: a la hora t, el instante t (en pulsos)."""
    return [(t, t * pps) for t in np.arange(0.0, hasta_s, paso_s)]


def test_el_desfase_se_mide_contra_el_cabezal_y_no_contra_donde_el_fondo_cree_estar():
    """**El cabezal dice 1,000 s y el bloque es del 1,040 s: son 40 ms, con signo.**

    Un desfase calculado preguntandole al acompañante «donde crees estar» daria 0:
    el bloque ES lo que el creyo tocar. El estado de partida distingue las dos
    cosas porque el cabezal y el bloque NO coinciden.
    """
    referencia = _referencia()
    pps = 1.5
    traza = _traza_recta(pps)
    # Escrito a la hora 1,000 (cabezal en 1,000 s) pero cortado del 1,040 s.
    bloques = _bloques_cortados(referencia, [1.040])

    peor, medidos, sin_localizar, saturados = desfase_contra_el_cabezal(
        bloques, [1.000], referencia, FS_FONDO, pps, traza
    )

    assert (medidos, sin_localizar, saturados) == (1, 0, 0)
    assert peor == pytest.approx(40.0, abs=0.1), "el desfase es contra el cabezal"


def test_el_desfase_tiene_signo_y_se_queda_con_el_peor():
    """Un bloque adelantado 10 ms, otro atrasado 25 ms y uno justo: el peor es -25."""
    referencia = _referencia()
    pps = 1.5
    bloques = _bloques_cortados(referencia, [0.510, 1.475, 2.000])

    peor, medidos, _, _ = desfase_contra_el_cabezal(
        bloques, [0.500, 1.500, 2.000], referencia, FS_FONDO, pps, _traza_recta(pps)
    )

    assert medidos == 3
    assert peor == pytest.approx(-25.0, abs=0.1)


def test_un_bloque_que_no_se_parece_a_la_pieza_no_se_mide_se_cuenta_aparte():
    """Ruido ajeno no se localiza: sale en `sin_localizar` y no inventa un desfase."""
    referencia = _referencia()
    ajeno = (np.random.default_rng(99).standard_normal(TAM_BLOQUE) * 0.1).astype(np.float32)

    resultado = desfase_contra_el_cabezal(
        [ajeno], [1.0], referencia, FS_FONDO, 1.5, _traza_recta(1.5)
    )

    assert tuple(resultado) == (None, 0, 1, 0)


def test_el_silencio_no_se_mide():
    """El silencio esta en todas partes de la pieza: no hay a que cabezal compararlo."""
    silencio = np.zeros(TAM_BLOQUE, dtype=np.float32)

    resultado = desfase_contra_el_cabezal(
        [silencio], [1.0], _referencia(), FS_FONDO, 1.5, _traza_recta(1.5)
    )

    assert tuple(resultado) == (None, 0, 0, 0)


def test_las_muestras_escritas_salen_del_capturador_y_el_desfase_del_cabezal():
    """Las dos cifras del informe, con escrituras hechas a mano y un reloj de mentira.

    Se escriben 3 bloques de 1024 y uno de 500: 3572 muestras, contadas aqui y no
    leidas de nadie. El cabezal esta 40 ms por detras de donde se cortaron.
    """
    referencia = _referencia()
    pps = 1.5
    reloj = types.SimpleNamespace(ahora=1.0)
    # Un reloj que no avanza y una espera que no espera: lo que se prueba es la
    # cuenta, no el ritmo.
    capturador = StreamCapturadoAlRitmo(reloj=lambda: reloj.ahora)
    capturador._debido = float("-inf")  # sin espera: ver StreamCapturadoAlRitmo.write
    inicios = [1.040, 1.040, 1.040]
    for bloque in _bloques_cortados(referencia, inicios):
        capturador.write(bloque)
    capturador.write(np.zeros(500, dtype=np.float32))

    informe = informe_del_fondo(capturador, referencia, pps, _traza_recta(pps))

    assert informe.muestras_escritas == 3 * 1024 + 500
    assert informe.desfase_maximo_ms == pytest.approx(40.0, abs=0.1)
    assert informe.bloques_medidos == 3


def test_el_capturador_al_ritmo_apunta_la_hora_de_cada_escritura_y_espera():
    """Cada escritura deja su hora, y la segunda espera a que pase lo escrito antes."""
    horas = iter([10.0, 10.0, 10.0, 10.0, 10.5, 10.5])
    esperas = []
    capturador = StreamCapturadoAlRitmo(
        frecuencia_muestreo=1000, reloj=lambda: next(horas), esperar=esperas.append
    )
    capturador.write(np.zeros(500, dtype=np.float32))  # dura 0,5 s
    capturador.write(np.zeros(500, dtype=np.float32))

    assert capturador.horas == (10.0, 10.0)
    # Lo escrito debe a la tarjeta 0,5 s y luego 1,0 s en total; el reloj marca
    # 10,0 las dos veces, asi que esperas de 0,5 y de 1,0.
    assert esperas == pytest.approx([0.5, 1.0])
    assert len(capturador.muestras) == 1000


def test_con_acompanamiento_captura_y_no_abre_altavoces(monkeypatch):
    """**Captura sin tocar `sounddevice`**: el escaparate corre sin hardware.

    Se planta una trampa en `sys.modules`: si se pidiera la salida real,
    `_abrir_stream_real` importaria la trampa y su `OutputStream` fallaria; como
    `SalidaAudio.abrir` se traga las excepciones, lo que delata el error es que
    `abrir()` devuelve False y que nada se capturo.
    """
    pedidos = []

    def trampa(**argumentos):
        pedidos.append(argumentos)
        raise AssertionError("se intento abrir la salida REAL")

    monkeypatch.setitem(
        sys.modules, "sounddevice", types.SimpleNamespace(OutputStream=trampa)
    )

    salida, capturador = _salida_del_fondo(altavoces=False)

    assert capturador is not None
    assert salida._abrir_stream is not _abrir_stream_real
    assert salida.abrir() is True, "con captura la salida tiene que abrirse"
    salida.reproducir(np.ones(8, dtype=np.float32))
    assert pedidos == [], "se abrio el dispositivo real"
    assert len(capturador.muestras) == 8, "lo escrito tiene que quedar capturado"


def test_altavoces_pide_la_salida_de_verdad():
    """**No se ejecuta: se comprueba CUAL se eligio.** Por omision es la real."""
    salida, capturador = _salida_del_fondo(altavoces=True)

    assert salida._abrir_stream is _abrir_stream_real
    assert capturador is None, "con altavoces no hay nada que capturar"


def test_altavoces_usa_el_stream_que_se_le_inyecta():
    """El seam: lo inyectado se usa tal cual, y es lo que prueba que se pidio abrir."""
    abiertos = []

    class StreamDeMentira:
        def start(self):
            pass

    def abrir(**argumentos):
        abiertos.append(argumentos)
        return StreamDeMentira()

    salida, _ = _salida_del_fondo(altavoces=True, abrir_stream=abrir)

    assert salida.abrir() is True
    assert len(abiertos) == 1


def test_main_pasa_a_la_demostracion_cual_salida_se_pidio(monkeypatch):
    """Cada bandera llega a la demostracion como lo que es; sin ellas, sin fondo."""
    resultados = {}
    for nombre, linea in [
        ("nada", []),
        ("captura", ["--con-acompanamiento"]),
        ("altavoces", ["--altavoces"]),
    ]:
        _, demostracion, _ = _main_con_doble(
            monkeypatch, linea + ["--bucle", "1", "--salir-al-acabar"], _veredicto()
        )
        resultados[nombre] = (demostracion.ultimo["fondo"], demostracion.ultimo["altavoces"])

    assert resultados["nada"] == (None, False)
    assert resultados["captura"][0] is not None and resultados["captura"][1] is False
    assert resultados["altavoces"][0] is not None and resultados["altavoces"][1] is True


def test_sin_pieza_el_fondo_es_la_propia_parte_y_con_pieza_son_las_voces_ajenas(monkeypatch):
    """Sin archivo no hay otras pistas (guia); con archivo salen las del archivo."""
    analizador = _analizador_de_argumentos()
    pieza = pieza_de_demostracion()

    sin = fondo_pedido(analizador.parse_args(["--con-acompanamiento"]), pieza)
    assert sin is not None and sin.voces == ()

    pedida = []
    voz = VozDeFondo("bajo", "bajo", (NotaDeFondo(40.0, 0.0, 1.0),))
    monkeypatch.setattr(
        "herramientas.gemelo.voces_de",
        lambda ruta, excluida: pedida.append((str(ruta), excluida))
        or FondoDisponible((voz,), 90, ()),
    )
    con = fondo_pedido(
        analizador.parse_args(["--altavoces", "--pieza", str(RUTA_DE_EJEMPLO)]), pieza
    )
    assert con is not None and con.voces == (voz,)
    assert pedida == [(str(RUTA_DE_EJEMPLO), 1)]

    assert fondo_pedido(analizador.parse_args([]), pieza) is None


def test_las_dos_banderas_juntas_fallan_al_armar_nombrando_las_dos():
    analizador = _analizador_de_argumentos()

    with pytest.raises(ValueError) as error:
        armar_la_pasada(analizador.parse_args(["--con-acompanamiento", "--altavoces"]))

    assert "--con-acompanamiento" in str(error.value)
    assert "--altavoces" in str(error.value)


def test_los_dos_juntos_fallan_antes_de_levantar_nada(monkeypatch, capsys):
    """**Instantaneo y antes de levantar el servidor**: la leccion de la etapa anterior.

    No se sustituye `_correr_la_demostracion`: se dejan trampas en lo que levanta
    cosas. Un error de opciones que saltara DESPUES de levantar el servidor
    -quince segundos despues- pasaria por ellas.
    """
    def trampa(*args, **kwargs):
        raise AssertionError("se levanto algo antes de rechazar las opciones")

    monkeypatch.setattr("herramientas.gemelo._levantar_el_servidor", trampa)
    monkeypatch.setattr("herramientas.gemelo._construir", trampa)
    monkeypatch.setattr("herramientas.gemelo._esperar_al_servidor", trampa)

    inicio = time.monotonic()
    codigo = main(["--con-acompanamiento", "--altavoces", "--salir-al-acabar"])

    assert codigo == 2
    assert time.monotonic() - inicio < 2.0
    salida = capsys.readouterr().out
    assert "--con-acompanamiento" in salida and "--altavoces" in salida


def test_el_orden_es_iniciar_y_despues_cargar_el_acompanamiento(monkeypatch):
    """Al reves el fondo se pierde en silencio. Se mira el ORDEN de las llamadas."""
    _, carril, _, _ = _demostracion_sin_red(monkeypatch)

    main(["--con-acompanamiento", "--bucle", "1", "--salir-al-acabar"])

    assert [llamada if isinstance(llamada, str) else llamada[0] for llamada in carril.llamadas] == [
        "iniciar",
        "cargar_acompanamiento",
    ]


def test_sin_fondo_no_se_carga_nada(monkeypatch):
    _, carril, _, _ = _demostracion_sin_red(monkeypatch)

    main(["--bucle", "1", "--salir-al-acabar"])

    assert carril.llamadas == ["iniciar"]


def test_el_fondo_queda_cargado_y_encendible_con_el_carril_de_verdad(monkeypatch, capsys):
    """**Con el carril y la sesion REALES**: el fondo sobrevive y el gemelo es el cable.

    Se sustituye solo lo que levanta el puerto y espera. Cuando la pasada se
    «sigue» el fondo ya se cargo, y se lee del estado PUBLICADO: una voz cargada
    (si se cargara antes de `iniciar` serian 0: `iniciar` lo suelta), y
    `acompanamiento_posible` verdadero, que solo lo es si la entrada cuenta como
    el cable Rocksmith -que es lo que hace falta para que cargar encienda-.
    """
    voz = VozDeFondo("bajo", "bajo", (NotaDeFondo(40.0, 0.0, 1.0),))
    fondo = FondoDisponible((voz,), 90, ())
    construidos = []
    construir_de_verdad = _construir

    def construir(pieza, interpretacion, salida_fondo=None):
        resultado = construir_de_verdad(pieza, interpretacion, salida_fondo=salida_fondo)
        construidos.append(resultado)
        return resultado

    monkeypatch.setattr("herramientas.gemelo._construir", construir)
    monkeypatch.setattr(
        "herramientas.gemelo._levantar_el_servidor", lambda app, puerto: ServidorDeMentira()
    )
    monkeypatch.setattr("herramientas.gemelo._esperar_al_servidor", lambda base: True)
    vistos = []

    def seguir(base, duracion_s, repeticiones=1, traza=None):
        vistos.append(construidos[0][2].estado())
        return RecolectorDeLaSesion(), True

    monkeypatch.setattr("herramientas.gemelo._seguir_la_pasada", seguir)
    pieza = pieza_de_demostracion()

    _correr_la_demostracion(
        pieza,
        interpretar(pieza, PERFECTO, ultimo_compas=1),
        PlanDePasada(ultimo_compas=1),
        8420,
        al_acabar=lambda *args: None,
        fondo=fondo,
    )

    estado = vistos[0]
    assert estado["acompanamiento_voces"] == 1, "el fondo se perdio: orden invertido"
    assert estado["acompanamiento_posible"] is True, (
        "el dispositivo del gemelo no cuenta como el cable: cargar no encenderia"
    )
    assert "Fondo capturado" in capsys.readouterr().out


def test_el_resumen_lleva_las_dos_cifras_del_fondo_y_sin_fondo_no_las_lleva():
    pieza = pieza_de_demostracion()
    informe = InformeDelFondo(251904, -30.1, 242, 0)

    con = resumen(_veredicto(), pieza, PERFECTO, True, informe)
    sin = resumen(_veredicto(), pieza, PERFECTO, True)

    assert "251904 muestras escritas" in con
    assert "-30.1 ms el peor contra el cabezal" in con
    assert "242 bloques medidos" in con
    assert "fondo" not in sin


def test_el_resumen_dice_cuando_el_desfase_no_se_pudo_medir():
    informe = InformeDelFondo(0, None, 0, 0)

    texto = resumen(_veredicto(), pieza_de_demostracion(), PERFECTO, True, informe)

    assert "0 muestras escritas" in texto
    assert "sin medir" in texto


def _puerto_libre() -> int:
    with socket.socket() as conexion:
        conexion.bind(("127.0.0.1", 0))
        return conexion.getsockname()[1]


def test_una_pasada_de_verdad_con_fondo_captura_muestras_y_mide_el_desfase():
    """**De punta a punta**: servidor real, cable del gemelo, fondo capturado.

    Un compas, unos cuatro segundos. Lo que se afirma son las cotas medidas a mano
    -una pasada de ~2,6 s escribe cientos de miles de muestras a 48 kHz, y el peor
    desfase contra el cabezal salio entre -30 y +30 ms en cinco corridas-, con
    margen: la cota de 150 ms es la mitad de un cuarto de segundo, que es lo que
    ya se oye como un fondo que no va con la pieza.
    """
    pieza = pieza_de_demostracion()
    recibido = []

    resultado = _correr_la_demostracion(
        pieza,
        interpretar(pieza, PERFECTO, ultimo_compas=1),
        PlanDePasada(ultimo_compas=1),
        _puerto_libre(),
        al_acabar=lambda veredicto, completada, informe=None: recibido.append(informe),
        fondo=FondoDisponible((), pieza.tempo, ()),
    )

    assert resultado is not None
    informe = recibido[0]
    assert informe is not None
    assert informe.muestras_escritas > 48000, "el fondo no sono: no se escribio ni un segundo"
    assert informe.bloques_medidos > 20
    # La cota solo vale si NADA cayo fuera de lo medible: un bloque saturado o sin
    # localizar es justo un desfase grande que la cifra no ve.
    assert informe.bloques_saturados == 0 and informe.bloques_sin_localizar == 0
    assert informe.desfase_maximo_ms is not None
    assert abs(informe.desfase_maximo_ms) < 150.0


def test_la_ventana_con_relleno_de_ceros_no_produce_localizaciones_falsas():
    """**El defecto que el primer escaparate real tuvo: bloques «localizados» a medio segundo.**

    El cabezal dice 0,10 s y la ventana de busqueda empieza 0,4 s ANTES del
    comienzo de la pieza: ahi la referencia es relleno de ceros. Sin la mascara de
    energia, el ruido numerico de la correlacion dividido por una energia casi
    nula daba un «parecido» enorme y el bloque se «localizaba» en el relleno,
    publicando un desfase de -450 ms que no existia. Se parte de un estado donde
    el relleno ESTA en la ventana; con el cabezal a mitad de pieza no se veria.

    Y con una referencia FUERTE (pico ~3, como una pieza renderizada normalizada
    a 1 que suena sin pausa): el ruido de la correlacion crece con el nivel, y
    con la referencia floja de las demas pruebas (pico ~0,8) el defecto no asoma
    -lo medi: esa version de la prueba pasaba con la mascara quitada-.
    """
    referencia = _referencia() * 5.0
    pps = 1.5
    traza = [(t, 0.10 * pps) for t in np.arange(0.0, 2.0, 0.01)]

    peor, medidos, sin_localizar, saturados = desfase_contra_el_cabezal(
        _bloques_cortados(referencia, [0.10]), [1.0], referencia, FS_FONDO, pps, traza
    )

    assert (medidos, sin_localizar, saturados) == (1, 0, 0)
    assert peor == pytest.approx(0.0, abs=0.1)


def test_el_fondo_avisa_cuando_cargarlo_no_lo_deja_posible(capsys):
    """Si la entrada no es el cable el escaparate lo DICE; con el cable, no avisa."""
    class CarrilQueDice:
        def __init__(self, posible):
            self._posible = posible

        def estado(self):
            return {"acompanamiento_voces": 2, "acompanamiento_posible": self._posible}

    _decir_el_fondo(CarrilQueDice(False), altavoces=False)
    sin_cable = capsys.readouterr().out
    _decir_el_fondo(CarrilQueDice(True), altavoces=True)
    con_cable = capsys.readouterr().out

    assert "AVISO" in sin_cable and "Rocksmith" in sin_cable
    assert "AVISO" not in con_cable
    assert "2 voces" in con_cable and "por los altavoces" in con_cable
    assert "capturado" in sin_cable


def test_la_referencia_se_renderiza_al_factor_de_tempo_del_plan():
    """**Con `--tempo 0,5` la pieza dura el doble: la referencia tiene que saberlo.**

    El estado de partida tiene el factor en 0,5 y no en 1,0: con 1,0 una
    referencia renderizada sin el factor coincidiria con la buena y no se
    notaria. Los bloques se cortan de una pieza que la PRUEBA renderiza al
    factor 0,5, y el cabezal avanza al ritmo de ese factor.
    """
    pieza = pieza_de_demostracion()
    fondo = FondoDisponible((), pieza.tempo, ())
    plan = PlanDePasada(factor_tempo=0.5)
    de_la_prueba = renderizar(
        (voz_de_tu_parte(pieza),), tempo=pieza.tempo, factor_tempo=0.5,
        frecuencia_muestreo=FS_FONDO,
    )
    # Un reloj que avanza 10 s por escritura, y un cabezal que a la hora de cada
    # escritura esta exactamente donde se corto el bloque.
    ticks = iter(range(0, 1000))
    capturador = StreamCapturadoAlRitmo(
        reloj=lambda: float(next(ticks)) * 10.0, esperar=lambda s: None
    )
    traza = []
    for numero, inicio in enumerate((0.5, 1.0, 1.5, 2.0)):
        trozo = de_la_prueba.muestras[int(inicio * FS_FONDO) :][:TAM_BLOQUE]
        capturador.write(trozo * 0.6)
        # Dos lecturas, una antes y otra despues de la hora de la escritura.
        traza.append((numero * 20.0 - 1.0, inicio * de_la_prueba.pulsos_por_segundo))
        traza.append((numero * 20.0 + 1.0, inicio * de_la_prueba.pulsos_por_segundo))

    informe = _informe_del_capturador(capturador, pieza, fondo, plan, traza)

    assert informe.bloques_medidos >= 3, "la referencia no era la del factor pedido"
    assert abs(informe.desfase_maximo_ms) < 1.0


def test_sin_lecturas_del_cabezal_no_hay_nada_que_medir_y_no_revienta():
    """Una pasada que no llego a leer el cabezal ni una vez: sin cifra, sin error."""
    referencia = _referencia()

    resultado = desfase_contra_el_cabezal(
        _bloques_cortados(referencia, [1.0]), [1.0], referencia, FS_FONDO, 1.5, []
    )

    assert tuple(resultado) == (None, 0, 0, 0)


def test_la_vuelta_del_bucle_no_se_interpola_como_si_fuera_un_cabezal_que_avanza():
    """El cabezal salta de 3,0 s a 0,0 s entre dos lecturas: el bloque es del 3,0 s.

    Interpolar en linea recta entre las dos lecturas daria un cabezal «esperado»
    a mitad de camino (1,5 s) y un desfase de segundo y medio que no existe. El
    estado de partida ES el salto, que es lo unico donde las dos formas de
    calcular el esperado difieren.
    """
    referencia = _referencia()
    pps = 1.5
    traza = [(0.99, 3.0 * pps), (1.01, 0.0)]

    peor, medidos, _, _ = desfase_contra_el_cabezal(
        _bloques_cortados(referencia, [3.0]), [1.0], referencia, FS_FONDO, pps, traza
    )

    assert medidos == 1
    assert peor == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------------
# Ronda de la revision: la medida dice lo que es, dice cuando satura, y
# `--altavoces` queda cableado en el camino real sin abrir audio.
# ---------------------------------------------------------------------------


def test_un_desfase_grande_se_mide_y_no_se_recorta():
    """300 ms de desfase publican 300 ms: ni se recorta a un tope ni se achica la ventana.

    Estado de partida: el desfase real (300 ms) esta MUY por encima de lo que
    mediria un tope de +-100 ms o una ventana de 50 ms, que es donde los dos
    mutantes se distinguen del original.
    """
    referencia = _referencia()
    pps = 1.5

    peor, medidos, _, saturados = desfase_contra_el_cabezal(
        _bloques_cortados(referencia, [1.300]), [1.000], referencia, FS_FONDO, pps,
        _traza_recta(pps),
    )

    assert (medidos, saturados) == (1, 0)
    assert peor == pytest.approx(300.0, abs=0.1)


@pytest.mark.parametrize(
    "desplazamiento_s", [0.455, 0.495, 0.600, 1.000, -0.455, -0.495, -0.600]
)
def test_un_desfase_mayor_que_la_zona_fiable_no_se_publica_como_dato(desplazamiento_s):
    """**El techo de la medida, declarado y por los dos lados.**

    +455, +495, +600 y +1000 ms, y los mismos con signo negativo: ninguno es un
    dato. El revisor midio sobre la pieza real que +600 ms publicaba +498,8 ms (el
    borde de la ventana) sin avisar, y que con un borde sin vigilar -el negativo-
    se publicaba -495 tan tranquilo. Ahora el bloque se cuenta como saturado o
    como sin localizar y NO entra en el peor: una asercion `< 150` sobre esta cifra
    no puede aprobar un desfase de medio segundo.
    """
    referencia = _referencia()
    pps = 1.5

    peor, medidos, sin_localizar, saturados = desfase_contra_el_cabezal(
        _bloques_cortados(referencia, [1.5 + desplazamiento_s]), [1.5], referencia,
        FS_FONDO, pps, _traza_recta(pps),
    )

    assert medidos == 0, "un desfase fuera de la zona fiable no se puede medir"
    assert peor is None
    assert saturados + sin_localizar == 1, "el bloque tiene que contarse en algun sitio"


@pytest.mark.parametrize("desplazamiento_s", [0.440, -0.440])
def test_justo_dentro_de_la_zona_fiable_todavia_se_mide(desplazamiento_s):
    """La otra cara del corte del 90 %: a 440 ms (por los dos lados) SI se publica."""
    referencia = _referencia()
    pps = 1.5

    peor, medidos, _, saturados = desfase_contra_el_cabezal(
        _bloques_cortados(referencia, [1.5 + desplazamiento_s]), [1.5], referencia,
        FS_FONDO, pps, _traza_recta(pps),
    )

    assert (medidos, saturados) == (1, 0)
    assert peor == pytest.approx(desplazamiento_s * 1000.0, abs=0.5)


def test_el_borde_saturado_se_dice_en_el_informe_y_la_salvedad_siempre():
    """Los saturados y los sin localizar salen en una linea de ATENCION; la salvedad, siempre."""
    sano = _lineas_texto(
        InformeDelFondo(1000, 12.0, 50, bloques_sin_localizar=0, bloques_saturados=0)
    )
    roto = _lineas_texto(
        InformeDelFondo(1000, 12.0, 50, bloques_sin_localizar=3, bloques_saturados=2)
    )

    for texto in (sano, roto):
        assert "consistencia interna" in texto
        assert "NO es sincronia audible" in texto
        assert "HTTP" in texto
    assert "ATENCION" not in sano
    assert "ATENCION" in roto
    assert "2 bloques saturados" in roto and "3 sin localizar" in roto


def _lineas_texto(informe) -> str:
    return resumen(_veredicto(), pieza_de_demostracion(), PERFECTO, True, informe)


def test_la_hora_de_cada_lectura_es_el_punto_medio_de_la_peticion(monkeypatch):
    """La lectura HTTP tarda 40 ms: la hora apuntada es la del MEDIO, ni el inicio ni el final."""
    horas = iter([10.0, 10.04])
    monkeypatch.setattr(
        "herramientas.gemelo.time", types.SimpleNamespace(monotonic=lambda: next(horas))
    )
    monkeypatch.setattr(
        "herramientas.gemelo._leer_json", lambda url: {"instante_pulsos": 3.0}
    )
    traza = []

    from herramientas.gemelo import _leer_estado

    _leer_estado("http://127.0.0.1:1", traza)

    assert traza == [(pytest.approx(10.02), 3.0)]


def test_las_notas_repetidas_no_son_identicas_y_por_eso_el_metodo_no_las_confunde():
    """**El supuesto que sostiene al localizador, escrito y probado.**

    `renderizar` deriva la semilla de cada nota de su indice: dos notas iguales de
    compases distintos NO suenan identicas. Si el fondo viniera algun dia de
    muestras grabadas -dos notas iguales identicas-, esta prueba falla y el
    localizador publicaria desfases de compases enteros con total confianza.
    """
    voz = VozDeFondo(
        "dos iguales",
        "guitarra",
        (NotaDeFondo(40.0, 0.0, 2.0), NotaDeFondo(40.0, 8.0, 2.0)),
    )
    pieza = renderizar((voz,), tempo=60, frecuencia_muestreo=FS_FONDO)
    primera = pieza.muestras[: 8000]
    segunda = pieza.muestras[8 * FS_FONDO : 8 * FS_FONDO + 8000]

    assert float(np.abs(primera).max()) > 0.01 and float(np.abs(segunda).max()) > 0.01
    assert not np.allclose(primera, segunda, atol=1e-4)


# -- `--altavoces` por el camino REAL, sin abrir audio ------------------------


class StreamEspia:
    """Un stream de mentira que cuenta, avisa de la primera escritura y no guarda nada."""

    def __init__(self) -> None:
        self.arranques = 0
        self.escrituras = 0
        self.escribio = threading.Event()

    def start(self) -> None:
        self.arranques += 1

    def write(self, muestras) -> None:
        self.escrituras += 1
        self.escribio.set()
        # Un dispositivo real bloquea hasta que hay hueco; sin esto el hilo giraria.
        threading.Event().wait(0.005)

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


def _correr_con_el_carril_real(monkeypatch, capsys, altavoces, abrir_stream):
    """Corre `_correr_la_demostracion` con carril y sesion REALES, sin servidor ni espera.

    Solo se sustituye lo que abre el puerto. El «seguimiento» llama a
    `carril.estado()` -que es lo que arranca el acompañante- y, si hay stream
    espia, espera con un `Event` a que escriba (no con un sleep).
    """
    construidos = []

    def construir(pieza, interpretacion, salida_fondo=None):
        resultado = _construir(pieza, interpretacion, salida_fondo=salida_fondo)
        construidos.append(resultado)
        return resultado

    monkeypatch.setattr("herramientas.gemelo._construir", construir)
    monkeypatch.setattr(
        "herramientas.gemelo._levantar_el_servidor", lambda app, puerto: ServidorDeMentira()
    )
    monkeypatch.setattr("herramientas.gemelo._esperar_al_servidor", lambda base: True)

    def seguir(base, duracion_s, repeticiones=1, traza=None):
        construidos[0][2].estado()
        espia = getattr(abrir_stream, "espia", None)
        if espia is not None:
            assert espia.escribio.wait(timeout=10.0), (
                "el fondo nunca escribio por la salida que se le pidio"
            )
        return RecolectorDeLaSesion(), True

    monkeypatch.setattr("herramientas.gemelo._seguir_la_pasada", seguir)
    pieza = pieza_de_demostracion()
    _correr_la_demostracion(
        pieza,
        interpretar(pieza, PERFECTO, ultimo_compas=1),
        PlanDePasada(ultimo_compas=1),
        8420,
        al_acabar=lambda *args: None,
        fondo=FondoDisponible((), pieza.tempo, ()),
        altavoces=altavoces,
        abrir_stream=abrir_stream,
    )
    return capsys.readouterr().out


def test_altavoces_escribe_por_la_salida_que_se_le_da_y_lo_dice(monkeypatch, capsys):
    """**La bandera que el coordinador no puede ejecutar, cableada de punta a punta.**

    Con `altavoces=True` el acompañante REAL del carril REAL abre y escribe por el
    stream inyectado (el que haria el altavoz), el aviso dice «por los
    altavoces» y no «capturado», y no aparece ningun aviso de salida rota. Los
    mutantes -que `--altavoces` capture en silencio, o que el aviso mienta- se
    notan aqui: si el stream espia no llega a escribir, la espera de 10 s falla.
    """
    espia = StreamEspia()

    def abrir(**argumentos):
        return espia

    abrir.espia = espia

    salida = _correr_con_el_carril_real(monkeypatch, capsys, True, abrir)

    assert espia.arranques == 1 and espia.escrituras >= 1
    assert "Fondo por los altavoces" in salida
    assert "capturado" not in salida
    assert "NO abrio" not in salida


def test_una_salida_que_no_abre_se_dice_con_su_error(monkeypatch, capsys):
    """Los altavoces desenchufados: la pasada sigue y el escaparate DICE por que no sono."""
    pedidos = []

    def abrir(**argumentos):
        pedidos.append(argumentos)
        raise OSError("sin altavoces (simulado)")

    salida = _correr_con_el_carril_real(monkeypatch, capsys, True, abrir)

    assert len(pedidos) == 1, "un intento por fondo: el pestillo no se rompe"
    assert "AVISO: la salida del fondo NO abrio" in salida
    assert "sin altavoces (simulado)" in salida


def test_con_captura_el_aviso_dice_capturado(monkeypatch, capsys):
    """La otra mitad del aviso: sin `--altavoces` dice «capturado» y no «por los altavoces»."""
    salida = _correr_con_el_carril_real(monkeypatch, capsys, False, None)

    assert "Fondo capturado" in salida
    assert "por los altavoces" not in salida
    assert "NO abrio" not in salida


@pytest.mark.parametrize(
    "sin_localizar, saturados, dice",
    [(3, 0, "0 bloques saturados"), (0, 2, "0 sin localizar")],
)
def test_la_atencion_sale_con_cualquiera_de_las_dos_cuentas(sin_localizar, saturados, dice):
    """Basta UNA de las dos cuentas distinta de cero para que salga la atencion."""
    texto = _lineas_texto(
        InformeDelFondo(
            1000, 12.0, 50, bloques_sin_localizar=sin_localizar, bloques_saturados=saturados
        )
    )

    assert "ATENCION" in texto
    assert dice in texto


def test_el_informe_del_fondo_trae_las_tres_cuentas_de_la_medida():
    """Del capturador al informe: un bloque saturado y uno ajeno llegan a sus campos.

    Dos bloques cortados 0,495 s por delante del cabezal (saturados), un ruido ajeno
    (sin localizar) y tres buenos: tres cuentas distintas, para que ninguna
    se pueda intercambiar o perder por el camino sin que se note.
    """
    referencia = _referencia()
    pps = 1.5
    ticks = iter(range(0, 1000))
    capturador = StreamCapturadoAlRitmo(
        reloj=lambda: 1.0 + float(next(ticks)) * 0.0, esperar=lambda s: None
    )
    # Tres medidos, DOS saturados y UNO sin localizar: las tres cuentas distintas
    # entre si, para que dos campos intercambiados no puedan pasar (con 1, 1 y 1
    # el intercambio no se veia).
    for bloque in _bloques_cortados(referencia, [1.0, 1.0, 1.0]):  # buenos
        capturador.write(bloque)
    for bloque in _bloques_cortados(referencia, [1.495, 1.495]):  # saturados
        capturador.write(bloque)
    capturador.write((np.random.default_rng(5).standard_normal(TAM_BLOQUE) * 0.1).astype(np.float32))

    informe = informe_del_fondo(capturador, referencia, pps, _traza_recta(pps))

    assert informe.bloques_medidos == 3
    assert informe.bloques_saturados == 2
    assert informe.bloques_sin_localizar == 1
    assert informe.desfase_maximo_ms == pytest.approx(0.0, abs=0.1)


def test_sin_cifra_el_informe_sigue_diciendo_la_salvedad_y_la_atencion():
    """Cuando no hay numero es cuando mas hace falta explicar por que."""
    texto = _lineas_texto(
        InformeDelFondo(0, None, 0, bloques_sin_localizar=4, bloques_saturados=2)
    )

    assert "sin medir" in texto
    assert "consistencia interna" in texto and "HTTP" in texto
    assert "ATENCION" in texto
    assert "2 bloques saturados" in texto and "4 sin localizar" in texto


# N4: el aviso de salida rota tambien con captura.
def test_una_salida_de_captura_que_no_abre_tambien_se_dice(monkeypatch, capsys):
    """El aviso no es cosa de `--altavoces`: con captura tambien tiene que decirse."""
    from nucleo.gemelo.salida import SalidaCapturada

    monkeypatch.setattr(
        "herramientas.gemelo._salida_del_fondo",
        lambda altavoces, abrir_stream=None: (
            SalidaCapturada(fallar_al_abrir=True).salida,
            None,
        ),
    )

    salida = _correr_con_el_carril_real(monkeypatch, capsys, False, None)

    assert "AVISO: la salida del fondo NO abrio" in salida
    assert "sin dispositivo de audio (simulado)" in salida
