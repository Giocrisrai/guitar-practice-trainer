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
import subprocess
import time
import urllib.error
from dataclasses import replace

import pytest

from herramientas.gemelo import (
    _analizador_de_argumentos,
    _esperar_al_servidor,
    _seguir_la_pasada,
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
from nucleo.gemelo.piezas_de_prueba import escala_de_ocho_notas, pieza_de_demostracion
from nucleo.gemelo.veredicto import Veredicto
from nucleo.piezas.compases import pulsos_por_compas
from nucleo.piezas.estudio import PlanDePasada, SesionDeEstudio

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
) -> Veredicto:
    """Un `Veredicto` armado a mano, para probar lo que se hace CON el.

    `maximo` es el peor desfase emparejado, y se puede fijar porque de el depende
    si el resumen avisa de que los hallazgos son el borde del detector.
    """
    return Veredicto(
        notas_de_la_pieza=8,
        notas_tocadas=tocadas,
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

    Cada nota aparece en UN SOLO cuadro del guion y desaparece despues, que es lo
    que de verdad hace el servidor: `SesionCarril` publica lo que el seguidor lleva
    anotado y el seguidor lo TIRA al cerrar una vuelta o al dar la vuelta al tramo.
    De ahi que el ritmo de lectura importe: lo que no se lea mientras esta
    publicado no se recupera.

    El guion se indexa por tiempo transcurrido y no por numero de llamada, para
    que un lector que lea la mitad de veces vea la mitad de los cuadros y no los
    mismos cuadros mas tarde. Es lo que convierte «leer despacio» en «perder
    notas», que es la propiedad que se quiere afirmar.
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

    def _cuadro(self) -> int:
        return int((time.monotonic() - self.arranque) / PASO_DEL_GUION_S)

    def __call__(self, url: str, limite_s: float = 5.0) -> dict:
        self.peticiones.append(url)
        cuadro = self._cuadro()
        completado = cuadro >= self.cuadros_hasta_completar
        if cuadro < self.notas_antes:
            # Antes de completarse: la nota `cuadro` y solo ella.
            tocadas = [_nota_publicada(cuadro)]
        elif completado:
            # Despues de completarse la cadena sigue publicando los ultimos
            # ataques, uno por cuadro: es lo que la cola existe para recoger.
            puesto = cuadro - self.cuadros_hasta_completar
            tocadas = (
                [_nota_publicada(self.notas_antes + puesto)]
                if puesto < self.notas_tras_completar
                else []
            )
        else:
            tocadas = []
        return {
            "repeticion": 1,
            "instante_s": round(cuadro * PASO_DEL_GUION_S, 3),
            "tocadas": tocadas,
            "completado": completado,
        }


def test_seguir_la_pasada_recoge_todo_lo_que_se_publico_mientras_corria(monkeypatch):
    """Lee lo bastante deprisa para no perder ni una nota publicada.

    **Mata el mutante `LECTURAS_POR_SEGUNDO = 5`.** Cada nota del guion esta
    publicada durante un solo cuadro de 50 ms, asi que un lector a 5 Hz -una
    lectura cada 200 ms- se salta tres de cada cuatro. No es una prueba del servidor
    de mentira: es la propiedad de la que cuelga el veredicto del escaparate, y el
    informe de la tarea ya media que a 30 Hz «casi todos los hallazgos eran del
    muestreo y no de la cadena».
    """
    guion = ServidorDeGuion(notas_antes=8, notas_tras_completar=0)
    monkeypatch.setattr("herramientas.gemelo._leer_json", guion)

    recolector, completada = _seguir_la_pasada("http://127.0.0.1:0", duracion_s=0.5)

    assert completada is True
    recogidos = sorted(reporte.tocada.indice for reporte in recolector.registro.reportes)
    assert recogidos == list(range(8)), (
        f"se perdieron notas publicadas: se recogieron {recogidos}"
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
    """

    def __init__(self, veredicto, completada: bool = True) -> None:
        self.veredicto = veredicto
        self.completada = completada
        self.veces = 0

    def __call__(self, pieza, interpretacion, plan, puerto):
        self.veces += 1
        if self.veredicto is None:
            return None
        return self.veredicto, self.completada


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
