"""Pruebas del generador de cambios de acorde."""

import pytest

from nucleo.afinaciones import PERFILES_DE_FABRICA
from nucleo.ejercicios.generadores.acordes import (
    DIGITACIONES,
    acorde_de_clave,
    generar_cambios,
)

GUITARRA = PERFILES_DE_FABRICA["guitarra_estandar"]


class TestLaTabla:
    def test_estan_los_ocho_acordes_de_la_spec(self):
        assert set(DIGITACIONES) == {
            "do",
            "sol",
            "re",
            "la",
            "mi",
            "la_menor",
            "mi_menor",
            "re_menor",
        }

    def test_cada_digitacion_cubre_las_seis_cuerdas(self):
        for clave, (_, trastes) in DIGITACIONES.items():
            assert len(trastes) == 6, clave

    def test_do_mayor_es_x32010(self):
        nombre, trastes = DIGITACIONES["do"]
        assert nombre == "Do mayor"
        assert trastes == (None, 3, 2, 0, 1, 0)

    def test_una_cuerda_al_aire_no_es_una_cuerda_muda(self):
        """0 y None son distintos: al aire suena, muda no se toca."""
        _, do = DIGITACIONES["do"]
        assert do[0] is None
        assert do[3] == 0

    def test_ninguna_digitacion_pide_un_traste_imposible(self):
        for clave, (_, trastes) in DIGITACIONES.items():
            for traste in trastes:
                assert traste is None or 0 <= traste <= 4, clave


class TestAcordeDeClave:
    def test_do_mayor_da_las_cinco_notas_de_grave_a_aguda(self):
        acorde = acorde_de_clave("do", GUITARRA)
        assert acorde.midis == (48, 52, 55, 60, 64)
        assert acorde.nombre == "Do mayor"

    def test_sol_mayor_da_sus_seis(self):
        assert acorde_de_clave("sol", GUITARRA).midis == (43, 47, 50, 55, 59, 67)

    def test_las_posiciones_no_incluyen_la_cuerda_muda(self):
        acorde = acorde_de_clave("do", GUITARRA)
        assert len(acorde.posiciones) == 5
        assert all(p.cuerda != 6 for p in acorde.posiciones)

    def test_mi_menor_usa_las_seis_cuerdas(self):
        assert len(acorde_de_clave("mi_menor", GUITARRA).posiciones) == 6

    def test_las_posiciones_van_en_el_mismo_orden_que_las_notas(self):
        """De grave a aguda las dos listas, para poder emparejarlas por indice."""
        acorde = acorde_de_clave("do", GUITARRA)
        assert [p.cuerda for p in acorde.posiciones] == [5, 4, 3, 2, 1]

    def test_una_clave_que_no_existe_se_rechaza_listando_las_que_si(self):
        with pytest.raises(ValueError, match="do"):
            acorde_de_clave("fa_sostenido_disminuido", GUITARRA)

    def test_un_perfil_que_no_alcanza_la_digitacion_se_rechaza_al_generar(self):
        """Un bajo de 4 cuerdas no toca un Do de 5. Falla aqui, no al tocar."""
        bajo = PERFILES_DE_FABRICA["bajo_4"]
        with pytest.raises(ValueError, match="Do mayor"):
            acorde_de_clave("do", bajo)

    def test_los_ocho_acordes_salen_en_una_guitarra(self):
        for clave in DIGITACIONES:
            acorde = acorde_de_clave(clave, GUITARRA)
            assert len(acorde.midis) >= 4, clave


class TestGenerarCambios:
    def test_tres_acordes_por_cuatro_repeticiones_son_doce(self):
        assert len(generar_cambios(claves=("do", "sol", "re"), repeticiones=4)) == 12

    def test_los_acordes_se_alternan_y_no_se_agrupan(self):
        """Do, Sol, Do, Sol... El cambio es lo que se practica."""
        ejercicio = generar_cambios(claves=("do", "sol"), repeticiones=3)
        nombres = [a.nombre for a in ejercicio.acordes]
        assert nombres == ["Do mayor", "Sol mayor"] * 3

    def test_el_ejercicio_no_trae_notas_sueltas(self):
        assert generar_cambios().notas == ()

    def test_una_sola_clave_se_rechaza_porque_no_hay_cambio_que_practicar(self):
        with pytest.raises(ValueError, match="dos"):
            generar_cambios(claves=("do",))

    def test_la_misma_clave_repetida_tampoco_es_un_cambio(self):
        with pytest.raises(ValueError, match="dos"):
            generar_cambios(claves=("do", "do"))

    def test_cero_repeticiones_se_rechaza(self):
        with pytest.raises(ValueError, match="repeticion"):
            generar_cambios(repeticiones=0)

    def test_un_tempo_imposible_se_rechaza_igual_que_en_los_otros_generadores(self):
        with pytest.raises(ValueError):
            generar_cambios(tempo=1)

    def test_un_perfil_que_no_existe_se_rechaza(self):
        with pytest.raises(ValueError):
            generar_cambios(perfil_clave="ukelele_imaginario")

    def test_la_descripcion_dice_cuantos_acordes_y_a_que_tempo(self):
        ejercicio = generar_cambios(claves=("do", "sol"), repeticiones=2, tempo=70)
        assert "70" in ejercicio.descripcion
        assert "4" in ejercicio.descripcion

    def test_la_clave_distingue_los_acordes_pedidos(self):
        uno = generar_cambios(claves=("do", "sol"))
        otro = generar_cambios(claves=("la", "mi"))
        assert uno.clave != otro.clave

    def test_cada_acorde_dura_un_compas(self):
        for acorde in generar_cambios().acordes:
            assert acorde.pulsos == 4.0
