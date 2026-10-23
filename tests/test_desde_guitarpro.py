"""Pruebas del lector de Guitar Pro.

Las muestras se FABRICAN con PyGuitarPro, que escribe ademas de leer: ningun
archivo con derechos de autor entra al repositorio.
"""

import copy

import guitarpro
import pytest

from nucleo.afinaciones import PERFILES, clave_de_perfil
from nucleo.piezas.desde_guitarpro import pieza_desde_guitarpro, pistas_de

TICKS_NEGRA = guitarpro.Duration.quarterTime


def _cancion_vacia(cuerdas_midi=(64, 59, 55, 50, 45, 40), percusion=False):
    """Una pista afinada y sin una sola nota.

    `cuerdas_midi` va en el orden de `Track.strings`: la cuerda numero 1 primero,
    es decir de la MAS AGUDA a la mas grave. Verificado ejecutando PyGuitarPro, y
    documentado en `gp5.readTrack`: "the strings are stored from the highest to
    the lowest".
    """
    song = guitarpro.Song()
    song.tempo = 90
    pista = song.tracks[0]
    pista.name = "Guitarra"
    pista.isPercussionTrack = percusion
    pista.strings = [
        guitarpro.GuitarString(number=i + 1, value=v) for i, v in enumerate(cuerdas_midi)
    ]
    return song


def cancion(cuerdas_midi=(64, 59, 55, 50, 45, 40), percusion=False):
    """Una cancion de una pista con cuatro negras, fabricada a mano."""
    cuerda = len(cuerdas_midi) or 1
    return con_notas(
        [(pulso, cuerda, traste) for pulso, traste in enumerate((0, 2, 3, 5))],
        cuerdas_midi=cuerdas_midi,
        percusion=percusion,
    )


def escribir(song, tmp_path, nombre="prueba.gp5"):
    ruta = tmp_path / nombre
    for pista in song.tracks:
        if not pista.strings:
            # Dos cosas que el formato gp5 no sabe escribir sin cuerdas: la
            # transposicion de clave, que PyGuitarPro deduce de `strings[-1]`, y
            # las notas, que se guardan como una mascara de cuerdas. Una pista sin
            # cuerdas tampoco tiene notas en la vida real.
            pista.clefTranspose = 0
            pista.clefTransposeSecondary = 0
            for compas in pista.measures:
                for voz in compas.voices:
                    voz.beats.clear()
    guitarpro.write(song, str(ruta))
    return ruta


def _anadir_compases(song, cuantos):
    """Deja la cancion con `cuantos` compases, con sus cabeceras."""
    pista = song.tracks[0]
    while len(pista.measures) < cuantos:
        song.addMeasureHeader(guitarpro.MeasureHeader())
        pista.measures.append(guitarpro.Measure(pista, song.measureHeaders[-1]))


def _pulso(song, pulsos):
    """El compas y el tick absoluto que le corresponden al pulso `pulsos`.

    Cada compas de 4/4 son cuatro negras; el primer compas empieza en el tick 960
    y no en 0, que es la trampa clasica de este formato.
    """
    pista = song.tracks[0]
    indice, resto = divmod(int(pulsos), 4)
    _anadir_compases(song, indice + 1)
    compas = pista.measures[indice]
    return compas, compas.header.start + resto * TICKS_NEGRA


def con_notas(especificaciones, cuerdas_midi=(64, 59, 55, 50, 45, 40), percusion=False):
    """Una cancion con una negra por entrada, en negras consecutivas.

    Cada entrada es `(pulso, cuerda, traste)` para una nota normal, o
    `("silencio" | "ligada" | "apagada", cuerda, traste)` para los tres casos
    raros, que caen en el pulso siguiente al de la entrada anterior.
    """
    song = _cancion_vacia(cuerdas_midi=cuerdas_midi, percusion=percusion)
    siguiente = 0
    for que, cuerda, traste in especificaciones:
        pulso = que if isinstance(que, int) else siguiente
        siguiente = pulso + 1
        compas, tick = _pulso(song, pulso)
        voz = compas.voices[0]
        beat = guitarpro.Beat(
            voice=voz,
            start=tick,
            duration=guitarpro.Duration(value=4),
            # Sin esto el beat sale `empty`, el lector le da duracion cero y todas
            # las notas se apilan en el mismo instante al releer el archivo.
            status=guitarpro.BeatStatus.normal,
        )
        if que == "silencio":
            beat.status = guitarpro.BeatStatus.rest
            beat.notes = []
        else:
            tipo = {
                "ligada": guitarpro.NoteType.tie,
                "apagada": guitarpro.NoteType.dead,
            }.get(que, guitarpro.NoteType.normal)
            beat.notes = [
                guitarpro.Note(beat=beat, value=traste, string=cuerda, type=tipo)
            ]
        voz.beats.append(beat)
    return song


def con_marcadores(marcadores):
    """Una cancion con un marcador en los compases que diga el diccionario."""
    song = con_notas([(indice * 4, 6, 3) for indice in sorted(marcadores)])
    for indice, titulo in marcadores.items():
        song.measureHeaders[indice].marker = guitarpro.Marker(title=titulo)
    return song


def con_cambio_de_tempo(primero, segundo):
    """Una cancion que empieza a `primero` y cambia a `segundo` en el compas 2."""
    song = con_notas([(0, 6, 3), (4, 6, 5)])
    song.tempo = primero
    beat = song.tracks[0].measures[1].voices[0].beats[0]
    beat.effect.mixTableChange = guitarpro.MixTableChange(
        tempo=guitarpro.MixTableItem(value=segundo)
    )
    return song


def _cierre_en_memoria(veces, extension):
    """El `repeatClose` que hay que poner para que el DISCO diga `veces`.

    El byte del archivo cuenta las veces que se toca el trozo: es el "x2" que
    muestra Guitar Pro. PyGuitarPro lo normaliza a pasadas de mas al leer un gp5
    (`gp5.py:328`) y le suma 1 al escribirlo (`gp5.py:1059`), pero en gp3 y gp4 no
    lo toca (`gp3.py:225`). Asi que el mismo archivo se fabrica con un valor
    distinto en memoria segun el formato, y eso es justo lo que hace que una ida y
    vuelta por la libreria NO pueda servir de oraculo: sale estable con cualquier
    convencion. Lo mide `test_el_byte_del_disco_de_un_cierre_cuenta_las_veces`.
    """
    return veces - 1 if extension == "gp5" else veces


def con_repeticion(veces=2, extension="gp5"):
    """Dos compases entre barras de repeticion, tocados `veces` veces."""
    song = con_notas([(0, 6, 3), (4, 6, 5)])
    song.measureHeaders[0].isRepeatOpen = True
    song.measureHeaders[1].repeatClose = _cierre_en_memoria(veces, extension)
    return song


# --- Las doce pruebas del brief -------------------------------------------------


def test_las_pistas_se_listan_con_su_nombre_y_afinacion(tmp_path):
    ruta = escribir(cancion(), tmp_path)
    pistas = pistas_de(ruta)
    assert pistas[0].nombre == "Guitarra"
    assert pistas[0].cuerdas_midi == (64, 59, 55, 50, 45, 40)
    assert pistas[0].motivo_no_usable is None


def test_una_pista_de_percusion_se_lista_pero_no_se_puede_usar(tmp_path):
    """Review Focus 4: Note.string no significa nada en percusion."""
    ruta = escribir(cancion(percusion=True), tmp_path)
    pista = pistas_de(ruta)[0]
    assert pista.motivo_no_usable is not None
    assert "percusi" in pista.motivo_no_usable.lower()


def test_importar_una_pista_de_percusion_se_rechaza(tmp_path):
    ruta = escribir(cancion(percusion=True), tmp_path)
    with pytest.raises(ValueError, match="percusi"):
        pieza_desde_guitarpro(ruta, 1)


def test_una_pista_sin_cuerdas_no_se_puede_usar(tmp_path):
    song = cancion()
    song.tracks[0].strings = []
    ruta = escribir(song, tmp_path)
    motivo = pistas_de(ruta)[0].motivo_no_usable
    assert motivo is not None
    # Que diga que NO HAY CUERDAS, no que no haya notas: sin cuerdas no se sabe
    # como esta afinada, y eso es lo que impide importarla.
    assert "cuerda" in motivo.lower()


def test_importar_una_pista_sin_cuerdas_se_rechaza(tmp_path):
    song = cancion()
    song.tracks[0].strings = []
    ruta = escribir(song, tmp_path)
    with pytest.raises(ValueError, match="cuerda"):
        pieza_desde_guitarpro(ruta, 1)


def test_el_tempo_y_la_afinacion_salen_del_archivo(tmp_path):
    ruta = escribir(cancion(), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.tempo == 90
    assert pieza.perfil == "guitarra_estandar"


def test_una_afinacion_rara_produce_un_perfil_a_medida(tmp_path):
    """Drop C: no esta en PERFILES y hay que construirlo."""
    ruta = escribir(cancion(cuerdas_midi=(62, 57, 53, 48, 43, 36)), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.perfil != "guitarra_estandar"


def test_importar_la_misma_afinacion_rara_dos_veces_no_la_vuelve_conocida(tmp_path):
    """Dar de alta un perfil no debe ensuciar lo que `clave_de_perfil` reconoce."""
    ruta = escribir(cancion(cuerdas_midi=(62, 57, 53, 48, 43, 36)), tmp_path)
    primera = pieza_desde_guitarpro(ruta, 1).perfil
    segunda = pieza_desde_guitarpro(ruta, 1).perfil
    assert primera == segunda
    assert clave_de_perfil(PERFILES[primera]) is None


def test_los_silencios_no_entran_como_notas(tmp_path):
    """Review Focus 2: un silencio no es una nota sin altura, es que no hay nota."""
    ruta = escribir(con_notas([(0, 6, 3), ("silencio", None, None), (2, 6, 5)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.traste for n in pieza.notas] == [3, 5]


def test_una_nota_ligada_alarga_la_anterior_en_vez_de_entrar_dos_veces(tmp_path):
    """Review Focus 1: una ligadura no es un ataque nuevo.

    Si entrara como nota, el carril pediria tocar algo que no se toca y lo contaria
    como fallo.
    """
    ruta = escribir(con_notas([(0, 6, 3), ("ligada", 6, 3)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert len(pieza.notas) == 1
    assert pieza.notas[0].duracion_pulsos == pytest.approx(2.0)


def test_los_marcadores_se_importan_como_secciones(tmp_path):
    ruta = escribir(con_marcadores({0: "Intro", 1: "Estribillo"}), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [s.nombre for s in pieza.secciones] == ["Intro", "Estribillo"]
    assert pieza.secciones[0].inicio_pulsos == 0.0


def test_un_cambio_de_tempo_a_mitad_se_marca_en_vez_de_tirar_la_cancion(tmp_path):
    """Review Focus 3: Pieza tiene UN tempo. Rechazar la cancion seria peor."""
    ruta = escribir(con_cambio_de_tempo(90, 120), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.tempo == 90
    assert pieza.tempo_variable is True


def test_un_archivo_que_no_es_guitar_pro_se_rechaza_con_un_mensaje(tmp_path):
    ruta = tmp_path / "roto.gp5"
    ruta.write_bytes(b"esto no es un gp5")
    with pytest.raises(ValueError) as error:
        pistas_de(ruta)
    assert "gp5" in str(error.value).lower() or "leer" in str(error.value).lower()


def test_una_pista_que_no_existe_se_rechaza_nombrando_las_que_hay(tmp_path):
    ruta = escribir(cancion(), tmp_path)
    with pytest.raises(ValueError, match="1"):
        pieza_desde_guitarpro(ruta, 99)


# --- Lo que el brief no fijaba --------------------------------------------------


def test_el_primer_compas_empieza_en_el_pulso_cero_y_no_en_el_uno(tmp_path):
    """PyGuitarPro cuenta los ticks desde 960, no desde 0."""
    ruta = escribir(con_notas([(0, 6, 3), (1, 6, 5)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 1.0]
    assert [n.duracion_pulsos for n in pieza.notas] == [1.0, 1.0]


def test_una_afinacion_asimetrica_no_sale_del_reves(tmp_path):
    """El orden de las cuerdas, con una afinacion donde invertirlo se note.

    `Track.strings` va de la mas AGUDA a la mas grave y `PerfilAfinacion.cuerdas`
    al contrario, asi que el lector tiene que darle la vuelta. Aqui la tercera
    cuerda esta subida tres semitonos: si se invirtiera el orden, el perfil
    pondria esa rareza en la cuarta y nada mas fallaria.
    """
    # Agudo -> grave: E4, B3, A#3 (G3 + 3), D3, A2, E2.
    ruta = escribir(cancion(cuerdas_midi=(64, 59, 58, 50, 45, 40)), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    perfil = PERFILES[pieza.perfil]
    assert [c.numero for c in perfil.cuerdas] == [6, 5, 4, 3, 2, 1]
    assert [c.nota for c in perfil.cuerdas] == ["E2", "A2", "D3", "A#3", "B3", "E4"]


def test_el_midi_de_la_nota_es_la_cuerda_al_aire_mas_el_traste(tmp_path):
    """Y la cuerda del archivo se conserva tal cual, sin renumerar."""
    ruta = escribir(con_notas([(0, 6, 3), (1, 1, 12)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [(n.cuerda, n.traste, n.midi) for n in pieza.notas] == [
        (6, 3, 43),  # E2 (40) + 3
        (1, 12, 76),  # E4 (64) + 12
    ]


def test_una_nota_apagada_no_entra_porque_no_tiene_altura(tmp_path):
    ruta = escribir(con_notas([(0, 6, 3), ("apagada", 6, 7)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.traste for n in pieza.notas] == [3]


def test_una_ligadura_sin_nota_antes_se_ignora_en_vez_de_reventar(tmp_path):
    ruta = escribir(con_notas([("ligada", 6, 3)]), tmp_path)
    assert pieza_desde_guitarpro(ruta, 1).notas == ()


def test_el_byte_del_disco_de_un_cierre_cuenta_las_veces(tmp_path):
    """El oraculo de las repeticiones, medido en el ARCHIVO y no en la memoria.

    Dos archivos que solo se diferencian en el cierre difieren en un unico byte.
    En gp5 ese byte vale `repeatClose + 1` y en gp3/gp4 vale `repeatClose`: la
    memoria cuenta pasadas de mas en gp5 y veces en los otros dos. Y el byte del
    disco son veces, con minimo 2 -el "x2" de Guitar Pro-, porque si la memoria de
    gp5 contara veces, `RepeatGroup` no veria nunca un cierre: solo lo cuenta si
    `repeatClose > 0` (`models.py:119`) y un "x2" llegaria como 1... que es
    exactamente lo que llega. Dicho al reves: un "x1" no es una repeticion.
    """
    for extension, esperados in (("gp5", (2, 3)), ("gp4", (1, 2)), ("gp3", (1, 2))):
        archivos = []
        for cierre in (1, 2):
            song = con_notas([(0, 6, 3), (4, 6, 5)])
            song.measureHeaders[0].isRepeatOpen = True
            song.measureHeaders[1].repeatClose = cierre
            ruta = escribir(song, tmp_path, f"cierre{cierre}.{extension}")
            archivos.append(ruta.read_bytes())
        distintos = [i for i, (a, b) in enumerate(zip(*archivos)) if a != b]
        assert len(distintos) == 1, extension
        byte = distintos[0]
        assert (archivos[0][byte], archivos[1][byte]) == esperados, extension


def test_un_cierre_de_repeticion_normal_hace_que_el_trozo_suene_dos_veces(tmp_path):
    """El caso que trae cualquier archivo de verdad: un "x2" corriente.

    En memoria llega como `repeatClose == 1`, que es el valor con el que el lector
    tenia la cuenta al reves y se importaba sin repetir: la pieza duraba la mitad
    de lo que suena.
    """
    ruta = escribir(con_repeticion(veces=2), tmp_path)
    assert guitarpro.parse(str(ruta)).measureHeaders[1].repeatClose == 1
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 4.0, 8.0, 12.0]


def test_un_cierre_de_tres_veces_se_toca_tres_veces(tmp_path):
    ruta = escribir(con_repeticion(veces=3), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 4.0, 8.0, 12.0, 16.0, 20.0]


def test_sin_barras_de_repeticion_no_se_repite_nada(tmp_path):
    ruta = escribir(con_notas([(0, 6, 3), (4, 6, 5)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 4.0]


def test_en_gp4_el_cierre_llega_sin_normalizar_y_tambien_se_expande(tmp_path):
    """Mismo archivo, misma musica, otra convencion en memoria."""
    ruta = escribir(con_repeticion(veces=2, extension="gp4"), tmp_path, "dos.gp4")
    assert guitarpro.parse(str(ruta)).measureHeaders[1].repeatClose == 2
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 4.0, 8.0, 12.0]


def test_una_pista_sin_notas_se_lista_pero_no_se_puede_usar(tmp_path):
    ruta = escribir(_cancion_vacia(), tmp_path)
    pista = pistas_de(ruta)[0]
    assert pista.notas == 0
    assert pista.motivo_no_usable is not None


def test_la_pista_usable_dice_cuantas_notas_trae_y_de_que_instrumento(tmp_path):
    ruta = escribir(con_notas([(0, 6, 3), ("silencio", None, None), (2, 6, 5)]), tmp_path)
    pista = pistas_de(ruta)[0]
    assert pista.numero == 1
    assert pista.notas == 2
    assert pista.instrumento == "Guitarra"


def test_un_archivo_que_no_existe_se_rechaza_con_un_mensaje(tmp_path):
    with pytest.raises(ValueError, match="no existe"):
        pistas_de(tmp_path / "fantasma.gp5")


def test_los_trastes_que_declara_la_pista_se_respetan_si_la_afinacion_es_rara(tmp_path):
    """`clave_de_perfil` tira los trastes; en un perfil a medida los conservamos."""
    song = cancion(cuerdas_midi=(62, 57, 53, 48, 43, 36))
    song.tracks[0].fretCount = 24
    ruta = escribir(song, tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert PERFILES[pieza.perfil].trastes == 24


def test_una_afinacion_conocida_con_mas_trastes_de_los_que_usa_sigue_siendo_la_conocida(
    tmp_path,
):
    """Decision: con la afinacion reconocida gana la clave conocida, no fretCount."""
    song = cancion()
    song.tracks[0].fretCount = 24
    ruta = escribir(song, tmp_path)
    assert pieza_desde_guitarpro(ruta, 1).perfil == "guitarra_estandar"


def test_si_la_pista_toca_mas_arriba_del_mastil_conocido_se_hace_un_perfil_a_medida(
    tmp_path,
):
    """Un perfil con 22 trastes no puede describir una nota en el 24."""
    song = con_notas([(0, 1, 24)])
    song.tracks[0].fretCount = 24
    ruta = escribir(song, tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.perfil != "guitarra_estandar"
    assert PERFILES[pieza.perfil].trastes == 24


def test_el_compas_sale_del_archivo(tmp_path):
    song = cancion()
    song.measureHeaders[0].timeSignature.numerator = 3
    ruta = escribir(song, tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.compas == (3, 4)
    assert pieza.compas_variable is False


def test_un_cambio_de_compas_a_mitad_se_marca(tmp_path):
    """`Pieza.compas` es uno solo y quien dibuja la partitura trocea con el.

    Sin la bandera, un 3/4 en medio pone las barras en el sitio equivocado desde
    ahi hasta el final de la cancion y nada avisa.
    """
    song = con_notas([(0, 6, 3), (4, 6, 5)])
    song.measureHeaders[1].timeSignature.numerator = 3
    ruta = escribir(song, tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.compas == (4, 4)
    assert pieza.compas_variable is True
    # Las notas no se descolocan: cada compas se mide con su propia longitud.
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 4.0]


def test_el_nombre_de_la_afinacion_no_depende_de_la_cancion_que_llego_primero(tmp_path):
    """La clave la comparten todas las canciones con la misma afinacion.

    Si el nombre se derivara de la pista, el selector del afinador mostraria
    "Afinacion de 'Guitarra ritmica'" en una afinacion que llego con otra cancion.
    """
    claves = []
    for archivo, nombre_pista in (("a.gp5", "Guitarra ritmica"), ("b.gp5", "Solista")):
        song = cancion(cuerdas_midi=(62, 57, 53, 48, 43, 36))
        song.tracks[0].name = nombre_pista
        claves.append(pieza_desde_guitarpro(escribir(song, tmp_path, archivo), 1).perfil)
    assert claves[0] == claves[1]
    assert PERFILES[claves[0]].nombre == "Afinación C2 G2 C3 F3 A3 D4 (24 trastes)"


# ---------------------------------------------------------------------------
# El alta del perfil: LISTAR tambien la hace, no solo importar
#
# El fallo que estas pruebas fijan: el alta colgaba solo de
# `pieza_desde_guitarpro`, asi que al listar las pistas de una cancion en una
# afinacion rara el perfil no existia todavia, `afinacion_de` devolvia
# `clave: None` y la pantalla decia «no tengo ningun perfil al que afinarte». El
# aviso de afinacion fallaba justo en el unico caso en el que hacia falta -con una
# afinacion de fabrica ya funcionaba- y empezaba a funcionar la SEGUNDA vez que
# abrias la cancion.
# ---------------------------------------------------------------------------

DROP_C = (62, 57, 53, 48, 43, 36)  # orden de Track.strings: de la aguda a la grave


def test_listar_las_pistas_da_de_alta_la_afinacion_rara(tmp_path):
    """Sin importar nada: describir las pistas basta para tener a que afinarse."""
    ruta = escribir(cancion(cuerdas_midi=DROP_C), tmp_path)
    antes = set(PERFILES)

    pistas_de(ruta)

    nuevas = set(PERFILES) - antes
    assert len(nuevas) == 1
    (clave,) = nuevas
    assert clave.startswith("a_medida_")
    # Y las cuerdas del perfil dado de alta son las del archivo, de grave a aguda.
    cuerdas = PERFILES[clave].cuerdas
    assert [c.nota for c in cuerdas] == ["C2", "G2", "C3", "F3", "A3", "D4"]


def test_listar_e_importar_dan_la_misma_clave_de_perfil(tmp_path):
    """La que de verdad protege el aviso.

    Si los dos caminos calculasen la clave por su cuenta, el aviso compararia tu
    afinacion con una clave que la pieza no va a traer: el usuario se afinaria a lo
    que le dicen y el carril seguiria rechazandole la cancion. Por eso el traste
    maximo lo cuenta UNA funcion y los dos caminos pasan por ella.
    """
    song = cancion(cuerdas_midi=DROP_C)
    song.tracks[0].fretCount = 24
    ruta = escribir(song, tmp_path)

    antes = set(PERFILES)
    pistas_de(ruta)
    (al_listar,) = set(PERFILES) - antes

    al_importar = pieza_desde_guitarpro(ruta, 1).perfil
    assert al_listar == al_importar
    assert PERFILES[al_importar].trastes == 24


def test_listar_una_afinacion_de_fabrica_no_da_de_alta_nada(tmp_path):
    """El registro vivo no es un cajon de sastre: lo conocido no se duplica."""
    antes = set(PERFILES)
    pistas_de(escribir(cancion(), tmp_path))
    assert set(PERFILES) == antes


def test_listar_una_pista_sin_afinacion_que_declarar_no_da_de_alta_nada(tmp_path):
    """Percusion y una pista sin cuerdas no tienen afinacion de la que hablar.

    La pista de percusion lleva a proposito unas cuerdas RARAS: con la afinacion
    estandar, saltarse la comprobacion de percusion no daria de alta nada igual
    -estandar ya es de fabrica- y la prueba no distinguiria el caso. En una pista de
    percusion `Note.string` no significa nada, asi que su "afinacion" tampoco, y dar
    de alta un perfil con ella seria ofrecerle al usuario afinarse a la bateria.
    """
    antes = set(PERFILES)
    pistas_de(
        escribir(
            cancion(cuerdas_midi=DROP_C, percusion=True), tmp_path, "percusion.gp5"
        )
    )
    pistas_de(escribir(cancion(cuerdas_midi=()), tmp_path, "sin_cuerdas.gp5"))
    assert set(PERFILES) == antes


def test_el_traste_que_se_toca_cuenta_tambien_al_listar(tmp_path):
    """La cuenta del traste maximo tiene que ser la misma en los dos caminos.

    Una pista en afinacion rara que toca el traste 24 necesita un perfil de 24
    trastes. Si al listar se contara sobre otra cosa -o no se contara-, la clave del
    listado seria `..._22t` y la de la pieza `..._24t`: dos perfiles para una
    afinacion y un aviso que apunta al que no es.
    """
    song = con_notas([(0, 1, 24)], cuerdas_midi=DROP_C)
    ruta = escribir(song, tmp_path)
    antes = set(PERFILES)
    pistas_de(ruta)
    (al_listar,) = set(PERFILES) - antes
    assert PERFILES[al_listar].trastes == 24
    assert pieza_desde_guitarpro(ruta, 1).perfil == al_listar


def test_un_mastil_corto_que_toca_un_traste_alto_da_un_perfil_que_llega(tmp_path):
    """`fretCount` BAJO y nota ALTA: lo unico que mide el `max` de los dos.

    Las tres pruebas que fijaban `trastes == 24` ponian `fretCount = 24` -o se
    apoyaban en el 24 por defecto de PyGuitarPro- Y una nota en el traste 24, asi que
    `max(24, 24)` no afirmaba nada: mutar
    `max(_trastes_declarados(pista), traste_maximo)` a `_trastes_declarados(pista)`
    dejaba la suite entera en verde.

    Aqui la guitarra declara 22 trastes y la pista pisa el 24. El perfil tiene que
    salir con 24 o la pieza llevaria una nota fuera de su propio mastil, que es
    justo lo que el docstring de `_clave_de_la_afinacion` dice que se niega a hacer
    («entonces el perfil conocido seria mentira»).
    """
    song = con_notas([(0, 1, 24)], cuerdas_midi=DROP_C)
    song.tracks[0].fretCount = 22
    ruta = escribir(song, tmp_path)

    pieza = pieza_desde_guitarpro(ruta, 1)
    perfil = PERFILES[pieza.perfil]
    assert perfil.trastes == 24
    assert max(n.traste for n in pieza.notas) <= perfil.trastes
    # Y el listado propone esa misma clave, no la del mastil que declara el archivo.
    (pista,) = pistas_de(ruta)
    assert pista.perfil_clave == pieza.perfil


# ---------------------------------------------------------------------------
# Dos perfiles de la MISMA afinacion y distinto numero de trastes
#
# El unico caso donde el registro puede tapar una clave con otra, y el que faltaba:
# las tres pruebas de arriba usan una cancion de UNA pista y dos afirman ademas
# `len(nuevas) == 1`, lo que obliga a un registro que no puede tapar nada.
#
# El fallo medido: la clave de un perfil a medida lleva los trastes dentro
# (`a_medida_c2-g2-c3-f3-a3-d4_24t`), pero quien proponia el aviso la volvia a
# deducir comparando SOLO el juego de notas MIDI y devolvia la primera entrada que
# encajara. Con dos canciones en Drop C de `fretCount` 22 y 24, el aviso proponia
# `..._22t` para las dos, el usuario se afinaba a eso, el listado contestaba
# `coincide: True` y el carril rechazaba la pieza con un 400.
# ---------------------------------------------------------------------------


def _en_drop_c_con_trastes(trastes, tmp_path, nombre):
    song = con_notas([(0, 6, 3)], cuerdas_midi=DROP_C)
    song.tracks[0].fretCount = trastes
    return escribir(song, tmp_path, nombre)


def test_dos_canciones_de_la_misma_afinacion_y_distintos_trastes_no_se_tapan(tmp_path):
    """Cada una propone SU clave, la que va a traer su pieza.

    La de 22 se mira primero a proposito: su entrada queda antes en el registro, y
    era la que tapaba a la otra cuando la clave se deducia por las notas.
    """
    corta = _en_drop_c_con_trastes(22, tmp_path, "corta.gp5")
    larga = _en_drop_c_con_trastes(24, tmp_path, "larga.gp5")

    (de_la_corta,) = pistas_de(corta)
    (de_la_larga,) = pistas_de(larga)

    assert de_la_corta.perfil_clave == "a_medida_c2-g2-c3-f3-a3-d4_22t"
    assert de_la_larga.perfil_clave == "a_medida_c2-g2-c3-f3-a3-d4_24t"
    # Y lo que de verdad importa: cada clave es la que trae su pieza.
    assert de_la_corta.perfil_clave == pieza_desde_guitarpro(corta, 1).perfil
    assert de_la_larga.perfil_clave == pieza_desde_guitarpro(larga, 1).perfil


def test_dos_pistas_de_la_misma_afinacion_y_distintos_trastes_no_se_tapan(tmp_path):
    """El mismo caso dentro de UN archivo: la pista 1 no puede tapar a la 2.

    Es el peor de los dos, porque las dos claves se dan de alta en la misma llamada
    a `pistas_de`: la primera entra antes en el registro y la segunda la encontraba
    al deducir por las notas.
    """
    song = con_notas([(0, 6, 3)], cuerdas_midi=DROP_C)
    song.tracks[0].name = "Corta"
    song.tracks[0].fretCount = 22
    segunda = copy.deepcopy(song.tracks[0])
    segunda.name = "Larga"
    segunda.number = 2
    segunda.fretCount = 24
    song.tracks.append(segunda)
    ruta = escribir(song, tmp_path, "dos_pistas.gp5")

    corta, larga = pistas_de(ruta)
    assert corta.perfil_clave == "a_medida_c2-g2-c3-f3-a3-d4_22t"
    assert larga.perfil_clave == "a_medida_c2-g2-c3-f3-a3-d4_24t"
    assert corta.perfil_clave == pieza_desde_guitarpro(ruta, 1).perfil
    assert larga.perfil_clave == pieza_desde_guitarpro(ruta, 2).perfil


def test_una_pista_sin_afinacion_que_declarar_no_publica_clave(tmp_path):
    """Percusion y una pista sin cuerdas: no hay clave que proponer, y se dice.

    None no es un descuido: es «esta pista no pide ninguna afinacion». Publicar
    cualquier clave aqui seria ofrecerle al usuario afinarse a la bateria.
    """
    percusion = escribir(
        cancion(cuerdas_midi=DROP_C, percusion=True), tmp_path, "percusion.gp5"
    )
    sin_cuerdas = escribir(cancion(cuerdas_midi=()), tmp_path, "sin_cuerdas.gp5")
    assert pistas_de(percusion)[0].perfil_clave is None
    assert pistas_de(sin_cuerdas)[0].perfil_clave is None

