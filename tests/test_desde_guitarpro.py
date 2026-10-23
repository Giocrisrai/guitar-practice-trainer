"""Pruebas del lector de Guitar Pro.

Las muestras se FABRICAN con PyGuitarPro, que escribe ademas de leer: ningun
archivo con derechos de autor entra al repositorio.
"""

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


def con_repeticion(veces=2):
    """Dos compases entre barras de repeticion, tocados `veces` veces."""
    song = con_notas([(0, 6, 3), (4, 6, 5)])
    song.measureHeaders[0].isRepeatOpen = True
    song.measureHeaders[1].repeatClose = veces
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
    assert pistas_de(ruta)[0].motivo_no_usable is not None


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


def test_las_repeticiones_se_expanden(tmp_path):
    ruta = escribir(con_repeticion(veces=2), tmp_path)
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
    assert pieza_desde_guitarpro(ruta, 1).compas == (3, 4)
