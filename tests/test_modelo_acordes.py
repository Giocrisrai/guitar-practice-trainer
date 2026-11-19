"""Pruebas del modelo cuando el ejercicio son acordes y no notas."""

import pytest

from nucleo.ejercicios.modelo import AcordeEsperado, Ejercicio, NotaEsperada
from nucleo.musica import Posicion

DO = AcordeEsperado(
    nombre="Do mayor",
    posiciones=(
        Posicion(cuerda=5, traste=3),
        Posicion(cuerda=4, traste=2),
        Posicion(cuerda=3, traste=0),
        Posicion(cuerda=2, traste=1),
        Posicion(cuerda=1, traste=0),
    ),
    midis=(48, 52, 55, 60, 64),
)
UNA_NOTA = NotaEsperada(midi=48, posiciones=(Posicion(cuerda=5, traste=3),))


def ejercicio(**extra) -> Ejercicio:
    base = {
        "clave": "cambios",
        "nombre": "Cambios",
        "descripcion": "",
        "notas": (),
        "tempo": 60,
        "perfil": "guitarra_estandar",
    }
    return Ejercicio(**{**base, **extra})


class TestAcordeEsperado:
    def test_el_nombre_de_cada_nota_sale_en_notacion_cientifica(self):
        assert DO.nombres == ("C3", "E3", "G3", "C4", "E4")

    def test_el_diccionario_lleva_todo_lo_que_la_pantalla_dibuja(self):
        como_dict = DO.a_dict()
        assert set(como_dict) == {"nombre", "posiciones", "midis", "nombres", "pulsos"}
        assert como_dict["posiciones"][0] == {"cuerda": 5, "traste": 3}
        assert como_dict["pulsos"] == 4.0

    def test_un_acorde_sin_notas_se_rechaza(self):
        with pytest.raises(ValueError, match="acorde"):
            AcordeEsperado(nombre="vacio", posiciones=(), midis=())

    def test_un_acorde_con_posiciones_pero_sin_midis_se_rechaza(self):
        with pytest.raises(ValueError, match="acorde"):
            AcordeEsperado(
                nombre="a medias", posiciones=(Posicion(cuerda=1, traste=0),), midis=()
            )


class TestEjercicioConAcordes:
    def test_un_ejercicio_de_acordes_se_mide_en_acordes(self):
        assert len(ejercicio(acordes=(DO, DO))) == 2

    def test_un_ejercicio_de_notas_sigue_midiendose_en_notas(self):
        assert len(ejercicio(notas=(UNA_NOTA,))) == 1

    def test_notas_y_acordes_a_la_vez_se_rechaza(self):
        """Un ejercicio tiene una cosa o la otra. Un tipo ambiguo se paga luego."""
        with pytest.raises(ValueError, match="notas y acordes"):
            ejercicio(notas=(UNA_NOTA,), acordes=(DO,))

    def test_un_ejercicio_sin_nada_se_rechaza(self):
        with pytest.raises(ValueError, match="vacio"):
            ejercicio()

    def test_el_diccionario_lleva_los_acordes(self):
        como_dict = ejercicio(acordes=(DO,)).a_dict()
        assert como_dict["acordes"][0]["nombre"] == "Do mayor"
        assert como_dict["notas"] == []

    def test_el_diccionario_de_un_ejercicio_de_notas_lleva_acordes_vacio(self):
        """La interfaz lee siempre las dos claves; una ausente seria undefined."""
        assert ejercicio(notas=(UNA_NOTA,)).a_dict()["acordes"] == []
