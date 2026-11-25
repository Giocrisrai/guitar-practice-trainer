import pytest

from nucleo.ejercicios.generadores.acordes import generar_cambios
from nucleo.ejercicios.generadores.escalas import generar_escala
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.musica import Posicion
from nucleo.piezas.desde_ejercicio import elegir_posicion, pieza_desde_ejercicio


def ejercicio(notas, tempo=80) -> Ejercicio:
    return Ejercicio(
        clave="prueba", nombre="Prueba", descripcion="",
        notas=tuple(notas), tempo=tempo, perfil="guitarra_estandar",
    )


def test_los_instantes_se_acumulan_con_los_pulsos_de_cada_nota():
    e = ejercicio([
        NotaEsperada(midi=40, posiciones=(Posicion(cuerda=6, traste=0),), pulsos=1.0),
        NotaEsperada(midi=42, posiciones=(Posicion(cuerda=6, traste=2),), pulsos=2.0),
        NotaEsperada(midi=44, posiciones=(Posicion(cuerda=6, traste=4),), pulsos=1.0),
    ])
    p = pieza_desde_ejercicio(e)
    assert [n.inicio_pulsos for n in p.notas] == [0.0, 1.0, 3.0]
    assert [n.duracion_pulsos for n in p.notas] == [1.0, 2.0, 1.0]


def test_se_elige_la_posicion_mas_cercana_al_traste_anterior():
    """Un La de 110 Hz esta en la quinta al aire y en el sexto traste de la sexta.
    Tocando por el traste cinco, la segunda es la que la mano ya tiene debajo."""
    anterior = Posicion(cuerda=6, traste=5)
    opciones = (Posicion(cuerda=5, traste=0), Posicion(cuerda=6, traste=6))
    assert elegir_posicion(opciones, anterior.traste) == Posicion(cuerda=6, traste=6)


def test_a_igualdad_de_distancia_gana_la_cuerda_mas_grave():
    opciones = (Posicion(cuerda=3, traste=4), Posicion(cuerda=5, traste=6))
    assert elegir_posicion(opciones, 5).cuerda == 5


def test_la_primera_nota_toma_el_traste_mas_bajo():
    """Sin nota anterior no hay cercania que medir, y empezar abajo es lo natural."""
    opciones = (Posicion(cuerda=5, traste=7), Posicion(cuerda=6, traste=0))
    assert elegir_posicion(opciones, None) == Posicion(cuerda=6, traste=0)


def test_una_nota_sin_posiciones_es_un_error_de_programacion():
    e = ejercicio([NotaEsperada(midi=40, posiciones=(), pulsos=1.0)])
    with pytest.raises(ValueError, match="E2"):
        pieza_desde_ejercicio(e)


def test_la_pieza_hereda_nombre_tempo_y_perfil_del_ejercicio():
    e = ejercicio([NotaEsperada(midi=40, posiciones=(Posicion(cuerda=6, traste=0),))], tempo=95)
    p = pieza_desde_ejercicio(e)
    assert p.tempo == 95
    assert p.perfil == "guitarra_estandar"
    assert p.nombre == "Prueba"


def test_una_escala_en_una_posicion_no_salta_por_el_mastil():
    """La heuristica es local y en una pieza de verdad no bastaria, pero sobre una
    escala en cuatro trastes tiene que dar una digitacion tocable: ninguna nota
    debe obligar a mover la mano mas de cuatro trastes respecto a la anterior."""
    e = generar_escala(raiz_midi=48, tipo="mayor", traste_minimo=0, traste_maximo=4)
    p = pieza_desde_ejercicio(e)
    trastes = [n.traste for n in p.notas if n.traste > 0]
    assert max(trastes) - min(trastes) <= 4


class TestUnEjercicioDeAcordes:
    """Un ejercicio de cambios tambien se puede llevar al carril.

    Antes no: `pieza_desde_ejercicio` solo recorria `ejercicio.notas`, que en un
    ejercicio de acordes esta vacio por construccion -trae notas o acordes, nunca
    las dos cosas-, asi que devolvia una pieza SIN NOTAS. El carril la aceptaba
    -`Pieza` no rechaza una pieza vacia- y el alumno veia un lienzo en blanco y un
    informe vacio tras cuatro segundos de cuenta atras, sin un solo mensaje.

    Ahora se traduce, y es lo que la tarea 8 hizo posible: el carril sabe cobrar
    varias notas con el mismo instante.
    """

    @staticmethod
    def _cambios():
        return generar_cambios(claves=("do", "sol"), repeticiones=1)

    def test_cada_acorde_es_un_grupo_de_notas_con_el_mismo_instante(self):
        p = pieza_desde_ejercicio(self._cambios())
        ejercicio = self._cambios()
        por_instante: dict[float, list[int]] = {}
        for nota in p.notas:
            por_instante.setdefault(nota.inicio_pulsos, []).append(nota.midi)

        assert len(por_instante) == len(ejercicio.acordes)
        for acorde, instante in zip(ejercicio.acordes, sorted(por_instante)):
            assert sorted(por_instante[instante]) == sorted(acorde.midis)

    def test_los_instantes_se_acumulan_acorde_a_acorde(self):
        ejercicio = self._cambios()
        p = pieza_desde_ejercicio(ejercicio)
        instantes = sorted({n.inicio_pulsos for n in p.notas})
        esperados = []
        inicio = 0.0
        for acorde in ejercicio.acordes:
            esperados.append(inicio)
            inicio += acorde.pulsos
        assert instantes == esperados
        assert p.duracion_pulsos == inicio

    def test_la_cuerda_y_el_traste_son_los_de_la_digitacion_escrita(self):
        """No se elige posicion: un acorde abierto YA dice en que cuerda va cada
        nota, y `elegir_posicion` -que mira el traste anterior- produciria una
        digitacion que ninguna mano toca."""
        ejercicio = self._cambios()
        p = pieza_desde_ejercicio(ejercicio)
        primero = ejercicio.acordes[0]
        del_primer_acorde = [n for n in p.notas if n.inicio_pulsos == 0.0]
        assert {(n.cuerda, n.traste) for n in del_primer_acorde} == {
            (pos.cuerda, pos.traste) for pos in primero.posiciones
        }

    def test_cada_nota_dura_lo_que_dura_el_acorde(self):
        ejercicio = self._cambios()
        p = pieza_desde_ejercicio(ejercicio)
        assert {n.duracion_pulsos for n in p.notas} == {
            acorde.pulsos for acorde in ejercicio.acordes
        }

    def test_la_pieza_hereda_el_nombre_el_tempo_y_el_perfil(self):
        ejercicio = self._cambios()
        p = pieza_desde_ejercicio(ejercicio)
        assert p.nombre == ejercicio.nombre
        assert p.tempo == ejercicio.tempo
        assert p.perfil == ejercicio.perfil
