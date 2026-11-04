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

import pathlib
from dataclasses import replace

import pytest

from herramientas.gemelo import (
    _analizador_de_argumentos,
    armar_la_pasada,
    codigo_de_salida,
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


def _veredicto(
    perdidas=(), inventadas=0, mal_adjudicadas=(), excluidas=(), tocadas=8
) -> Veredicto:
    """Un `Veredicto` armado a mano, para probar lo que se hace CON el."""
    return Veredicto(
        notas_de_la_pieza=8,
        notas_tocadas=tocadas,
        perdidas=perdidas,
        inventadas=inventadas,
        mal_adjudicadas=mal_adjudicadas,
        excluidas=excluidas,
        desfase_introducido_ms=152.3,
        desfase_maximo_ms=188.3,
    )


def test_el_bucle_se_lee_de_la_forma_primero_guion_ultimo():
    """`"17-20"` es el tramo 17 a 20 y `"17"` es el compas 17 solo."""
    assert leer_bucle("17-20") == (17, 20)
    assert leer_bucle("17") == (17, 17)
    assert leer_bucle(" 2 - 5 ") == (2, 5), "los espacios del usuario no son un error"


@pytest.mark.parametrize("texto", ["20-17", "cero", "0-4", "1-2-3", "", "4-", "-4"])
def test_un_tramo_imposible_se_rechaza_con_el_texto_recibido_dentro(texto):
    """Lo que no es un tramo se rechaza, y el mensaje trae el texto RECIBIDO.

    Sin el texto dentro, quien escribio `17–20` con el guion largo que pone el
    corrector de macOS lee «no sirve» y no ve la diferencia con `17-20`. Es el
    unico dato que convierte el mensaje en algo accionable.
    """
    with pytest.raises(ValueError) as fallo:
        leer_bucle(texto)

    assert repr(texto)[1:-1] in str(fallo.value) or texto in str(fallo.value)


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

    Es la regla del proyecto y aqui queda afirmada sobre lo que git tiene
    seguido, no sobre lo que haya en el disco: lo que importa es lo que se
    publica. La pieza del escaparate se construye en codigo justamente para que
    esta prueba pueda ser verdad.
    """
    partituras = [
        ruta
        for extension in EXTENSIONES_DE_PARTITURA
        for ruta in RAIZ.rglob(f"*{extension}")
        if ".venv" not in ruta.parts and "node_modules" not in ruta.parts
    ]

    assert partituras == [], f"hay partituras en el repositorio: {partituras}"


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
            "--pieza", "/tmp/x.gp5",
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

    assert argumentos.pieza == "/tmp/x.gp5"
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
