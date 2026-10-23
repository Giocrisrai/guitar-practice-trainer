import pytest

from nucleo.afinaciones import (
    PERFILES,
    PerfilAfinacion,
    clave_de_perfil,
    perfil_desde_midis,
)


def test_guitarra_estandar_tiene_seis_cuerdas():
    perfil = PERFILES["guitarra_estandar"]
    assert len(perfil.cuerdas) == 6


def test_guitarra_estandar_cuerda_grave_es_mi2():
    perfil = PERFILES["guitarra_estandar"]
    grave = perfil.cuerdas[0]
    assert grave.numero == 6
    assert grave.nota == "E2"
    assert grave.frecuencia == pytest.approx(82.41, abs=0.01)


def test_bajo_5_baja_hasta_si0():
    perfil = PERFILES["bajo_5"]
    assert perfil.frecuencia_minima == pytest.approx(30.87, abs=0.01)


@pytest.mark.parametrize(
    "clave, ventana_esperada",
    [
        ("guitarra_estandar", 4096),
        ("guitarra_drop_d", 4096),
        ("bajo_4", 8192),
        ("bajo_5", 8192),
    ],
)
def test_tamano_ventana_depende_del_perfil(clave, ventana_esperada):
    """La ventana debe crecer para los perfiles graves, no ser constante."""
    assert PERFILES[clave].tamano_ventana(48000) == ventana_esperada


def test_los_perfiles_son_inmutables():
    perfil = PERFILES["guitarra_estandar"]
    with pytest.raises(Exception):
        perfil.nombre = "otro"


def test_un_perfil_a_medida_tiene_las_cuerdas_que_se_le_den():
    """Drop C: la sexta baja dos tonos y el resto uno."""
    perfil = perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62])
    assert len(perfil.cuerdas) == 6
    assert perfil.cuerdas[0].numero == 6
    assert perfil.cuerdas[0].nota == "C2"
    assert perfil.cuerdas[-1].numero == 1


def test_las_frecuencias_salen_de_los_midis():
    perfil = perfil_desde_midis("estandar", [40, 45, 50, 55, 59, 64])
    assert perfil.cuerdas[0].frecuencia == pytest.approx(82.41, abs=0.01)


def test_siete_cuerdas_tambien_vale():
    perfil = perfil_desde_midis("siete", [35, 40, 45, 50, 55, 59, 64])
    assert len(perfil.cuerdas) == 7
    assert perfil.cuerdas[0].numero == 7


def test_un_perfil_a_medida_que_coincide_con_uno_conocido_se_reconoce():
    """Si la cancion pide afinacion estandar, no inventamos un perfil nuevo."""
    perfil = perfil_desde_midis("lo que diga el archivo", [40, 45, 50, 55, 59, 64])
    assert clave_de_perfil(perfil) == "guitarra_estandar"


def test_un_perfil_raro_no_coincide_con_ninguno():
    assert (
        clave_de_perfil(perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62])) is None
    )


def test_sin_cuerdas_no_hay_perfil():
    with pytest.raises(ValueError, match="cuerda"):
        perfil_desde_midis("vacio", [])


def test_el_perfil_a_medida_sirve_para_digitar():
    """La prueba que importa: lo que se construye tiene que funcionar aguas abajo."""
    from nucleo.piezas.digitacion import digitar

    perfil = perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62])
    assert len(digitar([36, 48, 60], perfil)) == 3
