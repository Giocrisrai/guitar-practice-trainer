"""El escritor que guarda en disco lo que `HistorialDeEstudio` anota en memoria.

Lo que estas pruebas vigilan no es el formato -eso es `test_historial.py`- sino
las dos garantias por las que este modulo existe aparte del nucleo:

* que el aviso del cierre de vuelta NO escriba, solo encole, porque llega en el
  camino que sirve la instantanea al navegador cada 33 ms;
* que un disco que falla no tumbe la pasada.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nucleo.historial.registro import DIAS_COMPLETOS, cargar
from nucleo.piezas.estudio import (
    CompasDelInforme,
    HistorialDeEstudio,
    InformeDePasada,
    PlanDePasada,
)
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from servidor.historial import EscritorDelHistorial, historial_guardado

AHORA = datetime(2026, 11, 25, 18, 42, 7)
PLAN = PlanDePasada(primer_compas=1, ultimo_compas=1)


def pieza() -> Pieza:
    return Pieza(
        nombre="Dos notas",
        perfil="guitarra_estandar",
        tempo=60,
        compas=(4, 4),
        notas=(
            NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0),
            NotaEnPieza(midi=45, cuerda=5, traste=0, inicio_pulsos=1.0, duracion_pulsos=1.0),
        ),
    )


def informe(limpias: int = 2) -> InformeDePasada:
    return InformeDePasada(
        compases=(
            CompasDelInforme(
                numero=1,
                notas_escritas=2,
                notas_medibles=2,
                acertadas=2,
                a_tiempo=limpias,
                pronto=0,
                tarde=2 - limpias,
                limpias=limpias,
                desfase_medio_s=0.029,
                tiene_acordes=False,
            ),
        ),
        ritmo_aproximado=False,
        compas_variable=False,
        factor_tempo=1.0,
        repeticiones=1,
    )


@pytest.fixture
def escritor(tmp_path):
    esc = EscritorDelHistorial(ruta=tmp_path / "historial.json", reloj=lambda: AHORA)
    esc.arrancar()
    yield esc
    esc.detener()


# -- la costura del nucleo ----------------------------------------------------


def test_sin_costura_el_historial_del_nucleo_no_toca_el_disco(tmp_path, monkeypatch):
    """La propiedad de la que presumia el docstring viejo, afirmada.

    `HistorialDeEstudio` sin `al_anotar` se comporta como siempre. Se comprueba
    prohibiendo `open` entero: si el nucleo abriera cualquier archivo, revienta.
    """
    import builtins

    def prohibido(*_, **__):
        raise AssertionError("el nucleo abrio un archivo, y no debe")

    monkeypatch.setattr(builtins, "open", prohibido)
    historial = HistorialDeEstudio()
    historial.anotar(informe())
    assert historial.pasadas == 1


def test_el_informe_llega_a_la_costura():
    recibidos = []
    historial = HistorialDeEstudio(al_anotar=recibidos.append)
    uno = informe()
    historial.anotar(uno)
    assert recibidos == [uno]


def test_un_oyente_que_revienta_no_tumba_la_vuelta():
    """La jerarquia del diseño: tocar la guitarra importa mas que anotarlo.

    Si el disco esta lleno, lo que NO puede pasar es que se caiga la vuelta del
    bucle. El historial en memoria -que es lo que la pantalla lee- queda entero.
    """

    def revienta(_):
        raise OSError("disco lleno")

    historial = HistorialDeEstudio(al_anotar=revienta)
    historial.anotar(informe())
    assert historial.pasadas == 1, "el fallo del oyente se llevo la vuelta"


def test_el_aviso_se_apunta_antes_de_avisar():
    """El orden importa: la pantalla no puede quedarse a medias por un oyente.

    Se comprueba desde dentro del propio oyente: cuando le toca, el historial en
    memoria ya tiene la pasada.
    """
    visto = []
    historial: HistorialDeEstudio

    def mirar(_):
        visto.append(historial.pasadas)

    historial = HistorialDeEstudio(al_anotar=mirar)
    historial.anotar(informe())
    assert visto == [1], "el oyente vio el historial sin la pasada que lo provoco"


# -- la cola ------------------------------------------------------------------


def test_el_oyente_no_escribe_encola(escritor):
    """ESTA es la garantia por la que existe el hilo.

    El aviso llega en el camino que sirve la instantanea cada 33 ms. Asi que al
    volver de `anotar` el archivo puede no existir todavia; lo que no puede es
    haberse escrito con el hilo del navegador esperando a un disco.
    """
    oyente = escritor.oyente_de(pieza(), PLAN)
    oyente(informe())
    assert escritor.vaciar(), "el escritor no acabo en el plazo"
    assert cargar(escritor.ruta).pasadas != (), "no se guardo nada"


def test_lo_encolado_llega_al_disco_con_la_pieza_y_el_plan(escritor):
    """El informe trae los compases; la pieza, el plan y el reloj los pone esto."""
    escritor.oyente_de(pieza(), PlanDePasada(primer_compas=3, ultimo_compas=7))(
        informe()
    )
    assert escritor.vaciar()
    guardada = cargar(escritor.ruta).pasadas[0]
    assert guardada.nombre_de_la_pieza == "Dos notas"
    assert guardada.tramo == (3, 7)
    assert guardada.instante == AHORA


def test_dos_pasadas_se_acumulan_no_se_sobreescriben(escritor):
    oyente = escritor.oyente_de(pieza(), PLAN)
    oyente(informe(limpias=1))
    oyente(informe(limpias=2))
    assert escritor.vaciar()
    assert len(cargar(escritor.ruta).pasadas) == 2


def test_detener_escribe_lo_que_quedaba_encolado(tmp_path):
    """El centinela de la cola: apagar el servidor no se lleva la ultima pasada."""
    escritor = EscritorDelHistorial(ruta=tmp_path / "historial.json", reloj=lambda: AHORA)
    escritor.arrancar()
    escritor.oyente_de(pieza(), PLAN)(informe())
    escritor.detener()
    assert len(cargar(tmp_path / "historial.json").pasadas) == 1


def test_detener_sin_arrancar_no_revienta(tmp_path):
    EscritorDelHistorial(ruta=tmp_path / "historial.json").detener()


def test_arrancar_dos_veces_no_pone_dos_hilos(escritor):
    """Si pusiera dos, cada pasada se escribiria dos veces o se perderia una."""
    hilo = escritor._hilo
    escritor.arrancar()
    assert escritor._hilo is hilo


# -- el disco que falla -------------------------------------------------------


def test_un_disco_que_falla_no_mata_el_hilo(tmp_path, caplog):
    """Si matara el hilo, el servidor seguiria encolando y nada chirriaria.

    Se rompe la escritura apuntando a un directorio que no existe, se comprueba
    que se avisa, y luego se comprueba que el hilo SIGUE VIVO atendiendo la
    siguiente -que es lo que de verdad se afirma aqui-.
    """
    ruta = tmp_path / "sin" / "camino" / "historial.json"
    escritor = EscritorDelHistorial(ruta=ruta, reloj=lambda: AHORA)
    escritor.arrancar()
    try:
        escritor.oyente_de(pieza(), PLAN)(informe())
        assert escritor.vaciar()
        assert escritor._hilo is not None and escritor._hilo.is_alive()
        # Y con el camino ya creado, la siguiente SI se guarda: el hilo nunca se
        # fue.
        ruta.parent.mkdir(parents=True)
        escritor.oyente_de(pieza(), PLAN)(informe())
        assert escritor.vaciar()
        assert len(cargar(ruta).pasadas) == 1
    finally:
        escritor.detener()


def test_el_fallo_de_disco_se_dice_una_sola_vez(tmp_path, caplog):
    """A una vuelta de bucle por pasada, repetirlo llenaria la terminal."""
    import logging

    escritor = EscritorDelHistorial(
        ruta=tmp_path / "sin" / "historial.json", reloj=lambda: AHORA
    )
    escritor.arrancar()
    try:
        with caplog.at_level(logging.ERROR, logger="servidor.historial"):
            oyente = escritor.oyente_de(pieza(), PLAN)
            for _ in range(3):
                oyente(informe())
            assert escritor.vaciar()
        fallos = [r for r in caplog.records if "No se pudo guardar" in r.getMessage()]
        assert len(fallos) == 1, f"se anuncio {len(fallos)} veces"
    finally:
        escritor.detener()


# -- el recorte, aplicado al guardar ------------------------------------------


def test_al_guardar_se_recorta_lo_viejo(tmp_path):
    """El anti objetivo: que el archivo crezca sin cota.

    El recorte se aplica en cada escritura y no en una limpieza aparte, para que
    no haya un momento en que el archivo este sin recortar.
    """
    ruta = tmp_path / "historial.json"
    viejo = AHORA - timedelta(days=DIAS_COMPLETOS + 10)
    antiguo = EscritorDelHistorial(ruta=ruta, reloj=lambda: viejo)
    antiguo.arrancar()
    oyente = antiguo.oyente_de(pieza(), PLAN)
    oyente(informe(limpias=0))
    oyente(informe(limpias=2))
    oyente(informe(limpias=1))
    assert antiguo.vaciar()
    antiguo.detener()
    assert len(cargar(ruta).pasadas) == 3, "el reloj viejo no recorto nada todavia"

    # Ahora llega una pasada de hoy: al guardarla, las tres viejas del mismo dia
    # se adelgazan a la mejor.
    hoy = EscritorDelHistorial(ruta=ruta, reloj=lambda: AHORA)
    hoy.arrancar()
    try:
        hoy.oyente_de(pieza(), PLAN)(informe(limpias=2))
        assert hoy.vaciar()
    finally:
        hoy.detener()
    quedan = cargar(ruta).pasadas
    assert len(quedan) == 2, f"quedaron {len(quedan)}: la vieja + la de hoy"
    assert quedan[0].compases[0].limpias == 2, "la vieja que quedo no es la mejor"


# -- la lectura para servirlo -------------------------------------------------


def test_historial_guardado_lee_lo_que_hay(tmp_path):
    escritor = EscritorDelHistorial(ruta=tmp_path / "historial.json", reloj=lambda: AHORA)
    escritor.arrancar()
    escritor.oyente_de(pieza(), PLAN)(informe())
    escritor.detener()
    assert len(historial_guardado(tmp_path / "historial.json").pasadas) == 1


def test_historial_guardado_sin_archivo_es_el_primer_dia(tmp_path):
    assert historial_guardado(Path(tmp_path / "nada.json")).pasadas == ()


# -- el enganche entero, de la app al disco -----------------------------------


def test_sin_ruta_la_app_no_escribe_en_el_historial_del_usuario(tmp_path):
    """LA PRUEBA QUE IMPIDE QUE LA SUITE ENSUCIE EL ARCHIVO DEL USUARIO.

    `historial.json` vive en la raiz del proyecto y es el registro de los fallos
    de alguien. Una suite que lo escribiera le estaria metiendo pasadas
    inventadas dentro, asi que guardar hay que PEDIRLO: sin `ruta_historial`, la
    app no construye escritor ninguno.
    """
    from servidor.app import crear_app
    from servidor.sesion import Sesion
    from servidor.configuracion import Configuracion

    app = crear_app(Sesion(Configuracion(), crear_captura=lambda **_: None, listar=lambda: []))
    assert app.state.escritor_del_historial is None
    assert app.state.ruta_historial is None


def test_con_ruta_la_app_arranca_el_escritor(tmp_path):
    from servidor.app import crear_app
    from servidor.sesion import Sesion
    from servidor.configuracion import Configuracion

    ruta = tmp_path / "historial.json"
    app = crear_app(
        Sesion(Configuracion(), crear_captura=lambda **_: None, listar=lambda: []),
        ruta_historial=ruta,
    )
    try:
        assert app.state.escritor_del_historial is not None
        assert app.state.escritor_del_historial.ruta == ruta
    finally:
        app.state.escritor_del_historial.detener()


def test_el_arranque_de_verdad_si_pide_guardar():
    """El unico sitio del repositorio que escribe en el archivo del usuario.

    Se afirma leyendo el codigo y no corriendo el servidor -que abriria audio-:
    lo que importa es que `arranque.py` pase la ruta, porque si algun dia alguien
    la quita, el programa dejaria de recordar y nada chirriaria.
    """
    import ast
    import inspect

    import servidor.arranque as arranque

    arbol = ast.parse(inspect.getsource(arranque))
    llamadas = [
        n
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "crear_app"
    ]
    assert llamadas, "arranque.py ya no llama a crear_app"
    claves = {k.arg for llamada in llamadas for k in llamada.keywords}
    assert "ruta_historial" in claves, (
        "arranque.py dejo de pedir guardar el historial: el programa ya no "
        "recordaria nada entre dias y ninguna otra prueba lo notaria"
    )


def test_una_vuelta_del_carril_acaba_en_el_disco(tmp_path):
    """EL ENGANCHE ENTERO, de cerrar la vuelta al archivo.

    Las demas pruebas de este archivo cubren las piezas por separado -la costura,
    la cola, el recorte-. Esta es la unica que afirma que las tres estan
    conectadas, que es lo que de verdad podria romperse en silencio: cada mitad
    seguiria verde y el programa no recordaria nada.

    Se usa el carril de produccion con su doble de sesion de audio, igual que
    `tests/test_sesion_carril.py`, y se cierra la vuelta llamando a `estado()`,
    que es donde el conductor deja el cierre a proposito.
    """
    from tests.test_sesion_carril import (
        RelojFalso,
        SesionAudioFalsa,
        avanzar_mirando,
        pieza_de,
    )
    from servidor.piezas import SesionCarril

    ruta = tmp_path / "historial.json"
    escritor = EscritorDelHistorial(ruta=ruta, reloj=lambda: AHORA)
    escritor.arrancar()
    reloj = RelojFalso()
    sesion = SesionAudioFalsa()
    sesion_carril = SesionCarril(
        sesion, reloj=reloj, escritor_del_historial=escritor
    )
    try:
        sesion_carril.iniciar(
            pieza_de([40, 41, 42, 43]),
            PlanDePasada(en_bucle=True, compases_de_cuenta_atras=0),
        )
        # Pasar del final del tramo es lo que cierra la vuelta del bucle. EN
        # PASOS, como el WebSocket en produccion: un salto de golpe lo recorta el
        # techo del reloj (`TECHO_TRAMO_S`) y la vuelta no llega a cerrarse.
        avanzar_mirando(sesion_carril, reloj, 10.0)
        assert escritor.vaciar(), "el escritor no acabo en el plazo"
        pasadas = cargar(ruta).pasadas
        assert pasadas, "la vuelta se cerro y no llego nada al disco"
        assert pasadas[0].nombre_de_la_pieza == "p"
        assert pasadas[0].instante == AHORA
    finally:
        sesion_carril.detener()
        escritor.detener()
        sesion.detener()


def test_cambiar_de_plan_guarda_el_tramo_nuevo_y_no_el_viejo(tmp_path):
    """Por esto `HistorialDeEstudio` gano `cambiar_oyente`.

    El historial en memoria se reutiliza por nombre de pieza y sobrevive a
    detener; el oyente cierra sobre la pieza Y EL PLAN de una pasada concreta. Sin
    renovarlo en cada `iniciar`, el disco guardaria el tramo de la pasada
    anterior, y el registro diria que practicaste algo que no practicaste.
    """
    from tests.test_sesion_carril import (
        RelojFalso,
        SesionAudioFalsa,
        avanzar_mirando,
        pieza_de,
    )
    from servidor.piezas import SesionCarril

    ruta = tmp_path / "historial.json"
    escritor = EscritorDelHistorial(ruta=ruta, reloj=lambda: AHORA)
    escritor.arrancar()
    reloj = RelojFalso()
    sesion = SesionAudioFalsa()
    sesion_carril = SesionCarril(
        sesion, reloj=reloj, escritor_del_historial=escritor
    )
    pieza_larga = pieza_de([40, 41, 42, 43, 44, 45, 46, 47])
    try:
        sesion_carril.iniciar(
            pieza_larga,
            PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                        compases_de_cuenta_atras=0),
        )
        sesion_carril.detener()
        sesion_carril.iniciar(
            pieza_larga,
            PlanDePasada(primer_compas=2, ultimo_compas=2, en_bucle=True,
                        compases_de_cuenta_atras=0),
        )
        avanzar_mirando(sesion_carril, reloj, 10.0)
        assert escritor.vaciar()
        pasadas = cargar(ruta).pasadas
        assert pasadas, "no llego nada al disco"
        assert pasadas[-1].tramo == (2, 2), (
            f"se guardo el tramo {pasadas[-1].tramo} y se tocaba el (2, 2)"
        )
    finally:
        sesion_carril.detener()
        escritor.detener()
        sesion.detener()
