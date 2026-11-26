"""El historial de pasadas: lo que el programa recuerda de lo que tocaste.

Hasta la etapa 4a el programa no recordaba nada. `InformeDePasada` se calculaba,
se servia por HTTP, se pintaba y se perdia; lo unico que persistia en todo el
repositorio era `config_local.json`. Estas pruebas cubren la primera rebanada:
el registro en disco, su lectura, la huella de la pieza y el recorte.

El diseño esta en
`docs/superpowers/specs/2026-11-25-historial-y-progreso-design.md`.
"""

import json
from datetime import datetime, timedelta

import pytest

from nucleo.historial.registro import (
    DIAS_COMPLETOS,
    Historial,
    RegistroDePasada,
    cargar,
    guardar,
    huella_de_la_pieza,
    recortar,
)
from nucleo.piezas.estudio import CompasDelInforme, InformeDePasada, PlanDePasada
from nucleo.piezas.modelo import NotaEnPieza, Pieza

AHORA = datetime(2026, 11, 25, 18, 42, 7)


def pieza_de_dos_notas(tempo: int = 60) -> Pieza:
    return Pieza(
        nombre="Dos notas",
        perfil="guitarra_estandar",
        tempo=tempo,
        compas=(4, 4),
        notas=(
            NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0),
            NotaEnPieza(midi=45, cuerda=5, traste=0, inicio_pulsos=1.0, duracion_pulsos=1.0),
        ),
    )


def compas(
    numero: int,
    limpias: int = 2,
    desfase_s: float | None = 0.029,
    tiene_acordes: bool = False,
    escritas: int = 2,
    medibles: int = 2,
    acertadas: int = 2,
) -> CompasDelInforme:
    return CompasDelInforme(
        numero=numero,
        notas_escritas=escritas,
        notas_medibles=medibles,
        acertadas=acertadas,
        a_tiempo=limpias,
        pronto=0,
        tarde=max(0, medibles - limpias),
        limpias=limpias,
        desfase_medio_s=desfase_s,
        tiene_acordes=tiene_acordes,
    )


def informe(
    *compases: CompasDelInforme, repeticiones: int = 1, factor_tempo: float = 1.0
) -> InformeDePasada:
    return InformeDePasada(
        compases=compases or (compas(1),),
        ritmo_aproximado=False,
        compas_variable=False,
        factor_tempo=factor_tempo,
        repeticiones=repeticiones,
    )


def registro(
    instante: datetime = AHORA,
    factor_tempo: float = 1.0,
    tramo: tuple[int, int] = (1, 1),
    limpias: int = 2,
    pieza: Pieza | None = None,
) -> RegistroDePasada:
    pieza = pieza or pieza_de_dos_notas()
    return RegistroDePasada.desde_el_informe(
        instante=instante,
        pieza=pieza,
        plan=PlanDePasada(
            primer_compas=tramo[0], ultimo_compas=tramo[1], factor_tempo=factor_tempo
        ),
        informe=informe(compas(tramo[0], limpias=limpias), factor_tempo=factor_tempo),
    )


# -- la huella de la pieza ----------------------------------------------------
#
# Sirve para saber que dos registros hablan de la MISMA pieza aunque el archivo
# se haya renombrado, y para saber que ya no hablan de la misma si se edito.
# Comparar progreso entre dos versiones distintas de una pieza es comparar cosas
# distintas, y la huella es lo que lo impide.


def test_la_misma_pieza_da_la_misma_huella():
    assert huella_de_la_pieza(pieza_de_dos_notas()) == huella_de_la_pieza(
        pieza_de_dos_notas()
    )


def test_el_nombre_no_entra_en_la_huella():
    """Renombrar el archivo NO rompe el historial: la huella es del contenido.

    Es la mitad util de la huella. Si el nombre entrara, mover una cancion de
    carpeta tiraria el progreso de meses.
    """
    otra = Pieza(
        nombre="Otro nombre completamente distinto",
        perfil=pieza_de_dos_notas().perfil,
        tempo=pieza_de_dos_notas().tempo,
        compas=pieza_de_dos_notas().compas,
        notas=pieza_de_dos_notas().notas,
    )
    assert huella_de_la_pieza(otra) == huella_de_la_pieza(pieza_de_dos_notas())


def test_editar_una_nota_cambia_la_huella():
    """La otra mitad: una pieza editada ya no es la misma, y no se compara con ella."""
    editada = Pieza(
        nombre="Dos notas",
        perfil="guitarra_estandar",
        tempo=60,
        compas=(4, 4),
        notas=(
            NotaEnPieza(midi=41, cuerda=6, traste=1, inicio_pulsos=0.0, duracion_pulsos=1.0),
            pieza_de_dos_notas().notas[1],
        ),
    )
    assert huella_de_la_pieza(editada) != huella_de_la_pieza(pieza_de_dos_notas())


def test_cambiar_el_tempo_escrito_cambia_la_huella():
    """El tempo ESCRITO es de la pieza, no de la pasada.

    No confundir con `factor_tempo`, que es como se toco esta vez y viaja en el
    registro. Si alguien reescribe la pieza a 80 ppm, las notas suenan en otros
    instantes y los desfases viejos ya no hablan de esto.
    """
    assert huella_de_la_pieza(pieza_de_dos_notas(tempo=80)) != huella_de_la_pieza(
        pieza_de_dos_notas(tempo=60)
    )


# -- el registro --------------------------------------------------------------


def test_el_registro_guarda_los_contadores_crudos_y_no_las_proporciones():
    """Una proporcion la calcula el lector; un contador perdido no se recupera.

    Es el mismo criterio que `InformeDePasada.repeticiones` ya aplica al exigir
    que el denominador viaje con el numerador.
    """
    guardado = registro().a_dict()
    uno = guardado["compases"][0]
    assert uno["limpias"] == 2
    assert uno["medibles"] == 2
    assert uno["escritas"] == 2
    assert "proporcion" not in uno
    assert "limpio" not in uno


def test_el_registro_lleva_el_tramo_y_el_factor_de_tempo():
    """Sin estos dos, el registro no se puede comparar con nada (spec 4.4)."""
    guardado = registro(tramo=(3, 7), factor_tempo=0.7).a_dict()
    assert guardado["tramo"] == [3, 7]
    assert guardado["factor_tempo"] == pytest.approx(0.7)


def test_el_registro_lleva_las_repeticiones_que_resume():
    """El denominador viaja con el numerador, o la proporcion sale mal."""
    reg = RegistroDePasada.desde_el_informe(
        instante=AHORA,
        pieza=pieza_de_dos_notas(),
        plan=PlanDePasada(primer_compas=1, ultimo_compas=1),
        informe=informe(compas(1), repeticiones=4),
    )
    assert reg.a_dict()["repeticiones"] == 4


def test_el_desfase_se_guarda_en_milisegundos_enteros_con_signo():
    """Milisegundos porque es la unidad en que se habla de esto, y con SIGNO.

    Negativo es adelantarse, con la misma convencion que `NotaTocada.desfase_s`.
    Perder el signo convertiria "te adelantas 40 ms" en "fallas 40 ms", que no es
    accionable.
    """
    adelantado = RegistroDePasada.desde_el_informe(
        instante=AHORA,
        pieza=pieza_de_dos_notas(),
        plan=PlanDePasada(primer_compas=1, ultimo_compas=1),
        informe=informe(compas(1, desfase_s=-0.040)),
    )
    assert adelantado.a_dict()["compases"][0]["desfase_medio_ms"] == pytest.approx(-40.0)


def test_un_compas_sin_desfase_medido_lo_guarda_como_nulo():
    """`None` es "no se midio", que es distinto de cero."""
    sin_medir = RegistroDePasada.desde_el_informe(
        instante=AHORA,
        pieza=pieza_de_dos_notas(),
        plan=PlanDePasada(primer_compas=1, ultimo_compas=1),
        informe=informe(compas(1, desfase_s=None)),
    )
    assert sin_medir.a_dict()["compases"][0]["desfase_medio_ms"] is None


def test_el_registro_no_guarda_la_pieza_solo_su_nombre_y_su_huella():
    """Ningun archivo con derechos de autor entra al repositorio. Nunca.

    El historial guarda el NOMBRE y la HUELLA, jamas las notas: un historial con
    las notas dentro seria una copia de la partitura en un archivo que el usuario
    podria subir sin darse cuenta.
    """
    guardado = registro().a_dict()
    assert set(guardado["pieza"]) == {"nombre", "huella"}
    # Los campos de una nota, por su nombre: si alguno apareciera, el historial
    # llevaria la partitura dentro. No se busca la palabra "notas" porque la
    # pieza de prueba se LLAMA "Dos notas" y su nombre si se guarda.
    texto = json.dumps(guardado)
    for campo in ("midi", "cuerda", "traste", "inicio_pulsos", "duracion_pulsos"):
        assert campo not in texto, f"el registro lleva '{campo}', que es de la nota"


# -- escritura y lectura ------------------------------------------------------


def test_lo_guardado_se_lee_igual(tmp_path):
    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(registro(),)), ruta)
    assert cargar(ruta).pasadas == (registro(),)


def test_un_historial_que_no_existe_no_es_un_error_es_el_primer_dia(tmp_path):
    assert cargar(tmp_path / "todavia_no.json").pasadas == ()


def test_el_archivo_se_escribe_entero_o_no_se_escribe(tmp_path):
    """Escritura atomica: un historial a medias es peor que ninguno.

    Se comprueba por donde se puede comprobar sin matar el proceso: que durante
    la escritura el archivo definitivo NUNCA contiene un JSON incompleto. El
    temporal se mira desde un `default` del serializador, que corre con el
    temporal ya abierto y el definitivo todavia intacto.
    """
    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(registro(),)), ruta)
    vistas = []

    class Espia:
        """Un objeto que al serializarse mira el archivo definitivo."""

        def __repr__(self) -> str:
            vistas.append(ruta.read_text(encoding="utf-8"))
            return "espia"

    reg = registro(limpias=1)
    sucio = Historial(pasadas=(reg, reg))
    guardar(sucio, ruta, serializar=lambda datos: json.dumps(datos) + repr(Espia()))
    assert vistas, "el serializador no corrio, asi que la prueba no comprobo nada"
    # Mientras se escribia, el definitivo seguia siendo el de antes y era valido.
    for texto in vistas:
        assert json.loads(texto)["pasadas"][0]["compases"][0]["limpias"] == 2


def test_un_historial_corrupto_se_aparta_y_no_se_borra(tmp_path):
    """Es el registro de los fallos de alguien. Borrarlo seria inadmisible.

    Se renombra a `.roto` y se empieza uno nuevo. El usuario puede abrirlo, y si
    el programa se equivoco, recuperarlo.
    """
    ruta = tmp_path / "historial.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cargar(ruta).pasadas == ()
    roto = ruta.with_suffix(".json.roto")
    assert roto.exists(), "el historial corrupto desaparecio en vez de apartarse"
    assert roto.read_text(encoding="utf-8") == "{esto no es json"


def test_un_historial_de_una_version_futura_tampoco_se_borra(tmp_path):
    """Un formato que no entendemos NO es basura: puede ser de un programa mas nuevo."""
    ruta = tmp_path / "historial.json"
    ruta.write_text(json.dumps({"version": 99, "pasadas": []}), encoding="utf-8")
    assert cargar(ruta).pasadas == ()
    assert ruta.with_suffix(".json.roto").exists()


def test_el_archivo_se_puede_leer_abriendolo(tmp_path):
    """Objetivo 4 de la spec: el historial se entiende sin el programa.

    O sea: JSON indentado con las claves en español, no una linea de 40 kB.
    """
    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(registro(),)), ruta)
    texto = ruta.read_text(encoding="utf-8")
    assert texto.count("\n") > 10, "el historial salio en una sola linea"
    assert '"factor_tempo"' in texto


# -- el recorte ---------------------------------------------------------------
#
# Anti objetivo: que el archivo crezca sin cota. Una sesion de media hora en
# bucle son decenas de pasadas; a tres años, un archivo que nadie abre.


def test_las_pasadas_recientes_se_conservan_todas():
    """Dentro de la frontera no se tira ni una, aunque sean cuarenta del mismo dia.

    Se comparan ordenadas porque `recortar` devuelve la serie en orden de
    instante -lo afirma su propia prueba- y aqui se construyen al reves a
    proposito, para que el orden de la entrada no se cuele en la asercion.
    """
    recientes = tuple(
        registro(instante=AHORA - timedelta(days=dia), limpias=dia % 3)
        for dia in range(DIAS_COMPLETOS)
    )
    quedan = recortar(Historial(pasadas=recientes), AHORA).pasadas
    assert sorted(quedan, key=lambda r: r.instante) == sorted(
        recientes, key=lambda r: r.instante
    )


def test_de_lo_viejo_queda_una_por_dia_y_es_la_mejor():
    """La mejor del dia, para que la tendencia de un año siga viendose.

    Sin esto, las cuarenta vueltas de un martes pesan cuarenta veces mas en la
    historia que la unica de un miercoles, y la tendencia habla de cuanto
    repetiste, no de cuanto mejoraste.
    """
    viejo = AHORA - timedelta(days=DIAS_COMPLETOS + 10)
    pasadas = (
        registro(instante=viejo, limpias=0),
        registro(instante=viejo + timedelta(hours=1), limpias=2),
        registro(instante=viejo + timedelta(hours=2), limpias=1),
    )
    quedan = recortar(Historial(pasadas=pasadas), AHORA).pasadas
    assert len(quedan) == 1
    assert quedan[0].compases[0].limpias == 2


def test_lo_viejo_se_guarda_por_pieza_tramo_y_tempo_por_separado():
    """Dos tempos del mismo compas son dos series distintas (spec 4.4).

    Si el recorte las juntara, se perderia la unica de un tempo porque ese dia
    hubo una mejor del otro, y la serie comparable quedaria con un agujero.
    """
    viejo = AHORA - timedelta(days=DIAS_COMPLETOS + 10)
    pasadas = (
        registro(instante=viejo, factor_tempo=1.0, limpias=2),
        registro(instante=viejo + timedelta(hours=1), factor_tempo=0.7, limpias=0),
    )
    quedan = recortar(Historial(pasadas=pasadas), AHORA).pasadas
    assert len(quedan) == 2, "el recorte junto dos tempos que no se comparan"
    assert {round(r.factor_tempo, 2) for r in quedan} == {1.0, 0.7}


def test_el_recorte_deja_las_pasadas_en_orden_de_instante():
    """Quien lea el historial lee una serie temporal, no un conjunto."""
    viejo = AHORA - timedelta(days=DIAS_COMPLETOS + 10)
    pasadas = (
        registro(instante=AHORA, tramo=(2, 2)),
        registro(instante=viejo, tramo=(1, 1)),
    )
    quedan = recortar(Historial(pasadas=pasadas), AHORA).pasadas
    assert [r.instante for r in quedan] == sorted(r.instante for r in quedan)


def test_recortar_un_historial_vacio_no_revienta():
    assert recortar(Historial(pasadas=()), AHORA).pasadas == ()


# -- la herramienta de terminal -----------------------------------------------
#
# El cuarto objetivo del diseño es que el historial se lea sin el programa. Estas
# pruebas no comprueban el formato exacto de la salida -eso seria afirmar
# decoracion- sino las dos cosas que si importan: que no revienta en los casos
# raros y que NO insinua un progreso que no ha medido.


def test_sin_historial_la_herramienta_lo_dice_y_no_falla(tmp_path, capsys):
    from herramientas.ver_historial import main

    assert main(["--ruta", str(tmp_path / "nada.json")]) == 0
    assert "Todavía no hay historial" in capsys.readouterr().out


def test_un_historial_vacio_no_es_lo_mismo_que_no_tener_historial(tmp_path, capsys):
    """Un archivo que existe y esta vacio es otra cosa, y se dice distinto."""
    from herramientas.ver_historial import main

    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=()), ruta)
    assert main(["--ruta", str(ruta)]) == 0
    assert "no tiene ninguna pasada" in capsys.readouterr().out


def test_la_herramienta_dice_cuantas_pasadas_hay_en_cada_serie(tmp_path, capsys):
    """Es el dato que decide si se puede comparar algo.

    Con una sola pasada no hay progreso que medir, y decirlo es mejor que
    insinuar una tendencia de un punto.
    """
    from herramientas.ver_historial import main

    ruta = tmp_path / "historial.json"
    guardar(
        Historial(
            pasadas=(
                registro(instante=AHORA, factor_tempo=1.0),
                registro(instante=AHORA + timedelta(days=1), factor_tempo=1.0),
                registro(instante=AHORA, factor_tempo=0.7),
            )
        ),
        ruta,
    )
    assert main(["--ruta", str(ruta)]) == 0
    salida = capsys.readouterr().out
    assert "2 pasada(s)" in salida, "no dijo que una serie tiene dos"
    assert "1 pasada(s)" in salida, "no dijo que la otra tiene una"


def test_la_herramienta_no_dice_que_mide_progreso(tmp_path, capsys):
    """ESTO es la prueba que importa de la herramienta.

    El anti objetivo del diseño es que el historial mienta sobre el progreso. Una
    herramienta que imprime dos numeros seguidos invita a leer una tendencia, asi
    que tiene que decir en voz alta que no la ha medido: la medida honesta
    descarta las diferencias por debajo del ruido, y eso no esta construido.
    """
    from herramientas.ver_historial import main

    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(registro(),)), ruta)
    assert main(["--ruta", str(ruta)]) == 0
    assert "NO mide progreso" in capsys.readouterr().out


def test_una_pasada_sin_notas_medibles_no_divide_por_cero(tmp_path, capsys):
    """Un tramo de solo silencios es raro pero legal, y no puede reventar."""
    from herramientas.ver_historial import main

    vacio = CompasDelInforme(
        numero=1,
        notas_escritas=0,
        notas_medibles=0,
        acertadas=0,
        a_tiempo=0,
        pronto=0,
        tarde=0,
        limpias=0,
        desfase_medio_s=None,
        tiene_acordes=False,
    )
    reg = RegistroDePasada.desde_el_informe(
        instante=AHORA,
        pieza=pieza_de_dos_notas(),
        plan=PlanDePasada(primer_compas=1, ultimo_compas=1),
        informe=informe(vacio),
    )
    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(reg,)), ruta)
    assert main(["--ruta", str(ruta)]) == 0
    assert "sin notas medibles" in capsys.readouterr().out


def test_la_herramienta_detalla_por_compas_cuando_se_le_pide(tmp_path, capsys):
    from herramientas.ver_historial import main

    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(registro(tramo=(19, 19)),)), ruta)
    assert main(["--ruta", str(ruta), "--compases"]) == 0
    salida = capsys.readouterr().out
    assert "compás  19" in salida
    assert "+29 ms" in salida, "el desfase perdio el signo o la unidad"


def test_el_registro_recuerda_si_el_compas_tenia_acordes(tmp_path):
    """Sin este campo el historial no puede aplicar la regla de los acordes.

    `nucleo.piezas.estudio.proporcion_limpia` EXCLUYE los compases con acordes, y
    quien lea el historial tiene que poder hacer lo mismo. Se guarda y se lee de
    vuelta, porque un campo que se escribe y no se recupera no sirve de nada.
    """
    reg = RegistroDePasada.desde_el_informe(
        instante=AHORA,
        pieza=pieza_de_dos_notas(),
        plan=PlanDePasada(primer_compas=1, ultimo_compas=1),
        informe=informe(compas(1, tiene_acordes=True)),
    )
    assert reg.a_dict()["compases"][0]["tiene_acordes"] is True
    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(reg,)), ruta)
    assert cargar(ruta).pasadas[0].compases[0].tiene_acordes is True


def test_un_rasgueo_con_una_cuerda_muda_no_sale_cien_por_cien_limpio(tmp_path, capsys):
    """EL DEFECTO QUE ESTA REBANADA DESTAPO, y es el anti objetivo del diseño.

    Un compas de acorde tiene UNA nota medible -un rasgueo, un ataque-, asi que
    la proporcion limpia solo puede salir 0 % o 100 %. Al gemelo PRINCIPIANTE,
    que fallaba una cuerda de cinco y llegaba 650 ms tarde, la herramienta le
    decia **«100,0 % limpio»**: la nota medible la acerto a tiempo, y la cuerda
    muda no aparecia en ningun sitio.

    Lo que se afirma aqui es que ya no pasa: en un compas con acordes el ritmo se
    declara SIN MEDIR y la cifra que se da es la de cuantas cuerdas sonaron.
    """
    from herramientas.ver_historial import main

    acorde = compas(
        1, limpias=1, medibles=1, escritas=5, acertadas=4, tiene_acordes=True
    )
    reg = RegistroDePasada.desde_el_informe(
        instante=AHORA,
        pieza=pieza_de_dos_notas(),
        plan=PlanDePasada(primer_compas=1, ultimo_compas=1),
        informe=informe(acorde),
    )
    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(reg,)), ruta)
    assert main(["--ruta", str(ruta)]) == 0
    salida = capsys.readouterr().out
    assert "100.0% limpio" not in salida, "volvio la mentira del 100 % limpio"
    assert "ritmo sin medir (acordes)" in salida
    # 4 de 5 cuerdas: ESE es el diagnostico que el alumno necesita.
    assert "80.0% suenan" in salida


def test_una_pieza_con_acordes_y_sin_ellos_mide_el_ritmo_de_los_que_puede(
    tmp_path, capsys
):
    """La exclusion es por compas, no por pieza: una cancion mixta mide lo que puede."""
    from herramientas.ver_historial import main

    reg = RegistroDePasada.desde_el_informe(
        instante=AHORA,
        pieza=pieza_de_dos_notas(),
        plan=PlanDePasada(primer_compas=1, ultimo_compas=2),
        informe=informe(
            compas(1, limpias=2),
            compas(2, limpias=1, medibles=1, escritas=5, acertadas=5, tiene_acordes=True),
        ),
    )
    ruta = tmp_path / "historial.json"
    guardar(Historial(pasadas=(reg,)), ruta)
    assert main(["--ruta", str(ruta)]) == 0
    salida = capsys.readouterr().out
    # Dos medibles sin acordes, las dos limpias: 100 % del ritmo MEDIBLE.
    assert "100.0% a tiempo" in salida
    assert "ritmo sin medir" not in salida
