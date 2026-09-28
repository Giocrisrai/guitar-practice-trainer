import pytest

from nucleo.afinaciones import PERFILES
from nucleo.musica import (
    NotaDetectada,
    Posicion,
    esta_afinada,
    frecuencia_a_midi,
    frecuencia_a_nota,
    midi_a_frecuencia,
    midi_de_nombre,
    nombre_de_clase,
    nombre_de_midi,
    posiciones_en_mastil,
)


def test_la4_es_midi_69():
    assert frecuencia_a_midi(440.0) == pytest.approx(69.0)


def test_midi_69_es_la4():
    assert midi_a_frecuencia(69) == pytest.approx(440.0)


def test_una_octava_son_doce_semitonos():
    assert frecuencia_a_midi(880.0) == pytest.approx(81.0)


@pytest.mark.parametrize(
    "midi, nombre",
    [(40, "E2"), (45, "A2"), (50, "D3"), (55, "G3"), (59, "B3"), (64, "E4"), (69, "A4")],
)
def test_nombres_de_las_cuerdas_al_aire(midi, nombre):
    assert nombre_de_midi(midi) == nombre


def test_frecuencia_exacta_da_cero_cents():
    frecuencia = midi_a_frecuencia(40)  # E2 exacto
    nota = frecuencia_a_nota(frecuencia)
    assert nota.nombre == "E2"
    assert nota.midi == 40
    assert nota.cents == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("desviacion", [-49.0, -25.0, -10.0, 10.0, 25.0, 49.0])
def test_desviacion_conocida_se_devuelve_igual(desviacion):
    """Si desafino una nota N cents, el resultado debe decir exactamente N cents."""
    frecuencia = midi_a_frecuencia(40) * 2 ** (desviacion / 1200.0)
    nota = frecuencia_a_nota(frecuencia)
    assert nota.midi == 40
    assert nota.cents == pytest.approx(desviacion, abs=0.01)


def test_la_nota_mas_cercana_gana_pasado_medio_semitono():
    """A +60 cents de E2 ya estamos más cerca de F2."""
    frecuencia = midi_a_frecuencia(40) * 2 ** (60.0 / 1200.0)
    nota = frecuencia_a_nota(frecuencia)
    assert nota.midi == 41
    assert nota.cents == pytest.approx(-40.0, abs=0.01)


def test_la_110_tiene_dos_posiciones_en_guitarra():
    """5ª al aire y 6ª en el traste 5 son la misma frecuencia: hay que mostrar ambas."""
    perfil = PERFILES["guitarra_estandar"]
    posiciones = posiciones_en_mastil(45, perfil)
    assert Posicion(cuerda=5, traste=0) in posiciones
    assert Posicion(cuerda=6, traste=5) in posiciones


def test_mi2_solo_se_toca_en_la_sexta_al_aire():
    perfil = PERFILES["guitarra_estandar"]
    assert posiciones_en_mastil(40, perfil) == [Posicion(cuerda=6, traste=0)]


def test_no_se_devuelven_trastes_fuera_del_mastil():
    perfil = PERFILES["guitarra_estandar"]
    assert posiciones_en_mastil(120, perfil) == []


def test_referencia_alternativa_desplaza_todo():
    """Con A4 = 432 Hz, tocar 440 Hz ya no está afinado."""
    nota = frecuencia_a_nota(440.0, referencia_a4=432.0)
    assert nota.midi == 69
    assert nota.cents == pytest.approx(31.77, abs=0.05)


@pytest.mark.parametrize(
    "cents, esperado", [(0.0, True), (4.9, True), (-4.9, True), (5.1, False), (-5.1, False)]
)
def test_tolerancia_de_afinacion(cents, esperado):
    assert esta_afinada(cents) is esperado


def test_nombre_de_clase_nota_natural():
    """Nota natural sin octava: 40 (E2) -> "E"."""
    assert nombre_de_clase(40) == "E"


def test_nombre_de_clase_con_sostenido():
    """Nota con sostenido sin octava: 42 (F#2) -> "F#"."""
    assert nombre_de_clase(42) == "F#"


def test_nombre_de_clase_octava_negativa():
    """Octava -1 sin sufijo: 0 (C-1) -> "C" (no "C-")."""
    assert nombre_de_clase(0) == "C"


@pytest.mark.parametrize("nombre,midi", [("E2", 40), ("A2", 45), ("C#3", 49), ("C-1", 0)])
def test_midi_de_nombre_es_la_inversa_de_nombre_de_midi(nombre, midi):
    assert midi_de_nombre(nombre) == midi
    assert nombre_de_midi(midi) == nombre


@pytest.mark.parametrize(
    "nombre", ["", "H2", "E", "mi2", "40", " E2 ", "E2 ", "C99", "E02", "E+2", "E2.0"]
)
def test_midi_de_nombre_rechaza_lo_que_no_es_una_nota(nombre):
    """Solo acepta lo que `nombre_de_midi` produce: ni espacios, ni octavas irreales.

    "C99" da un MIDI aritmeticamente valido (1200) que ninguna guitarra alcanza, y
    " E2 " o "E02" son cadenas que nadie escribe: adivinarlas convertiria en nota
    cualquier cosa parecida, y este es el sitio por donde entra lo que publica el
    detector de tono.
    """
    with pytest.raises(ValueError):
        midi_de_nombre(nombre)
