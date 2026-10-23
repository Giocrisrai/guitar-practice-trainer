import pytest

from nucleo.afinaciones import (
    PERFILES,
    PERFILES_DE_FABRICA,
    PerfilAfinacion,
    clave_de_perfil,
    perfil_desde_midis,
    registrar_perfil,
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


def test_un_perfil_a_medida_se_da_de_alta_para_que_una_pieza_pueda_nombrarlo():
    """`Pieza.perfil` es una clave de `PERFILES`, no un perfil."""
    perfil = perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62], trastes=24)
    clave = registrar_perfil(perfil)
    assert PERFILES[clave].cuerdas == perfil.cuerdas
    assert PERFILES[clave].trastes == 24
    assert clave not in PERFILES_DE_FABRICA


def test_dar_de_alta_el_mismo_perfil_dos_veces_no_lo_duplica():
    midis = [36, 43, 48, 53, 57, 62]
    primera = registrar_perfil(perfil_desde_midis("Drop C", midis))
    cuantos = len(PERFILES)
    segunda = registrar_perfil(perfil_desde_midis("Drop C otra vez", midis))
    assert primera == segunda
    assert len(PERFILES) == cuantos


def test_el_nombre_de_un_perfil_dado_de_alta_sale_de_sus_cuerdas():
    """La clave la comparten varias canciones, asi que el nombre no puede ser el
    que trajera la primera."""
    midis = [36, 43, 48, 53, 57, 62]
    clave = registrar_perfil(perfil_desde_midis("lo que diga el archivo", midis))
    assert PERFILES[clave].nombre == "Afinación C2 G2 C3 F3 A3 D4 (22 trastes)"


def test_dar_de_alta_un_perfil_no_lo_vuelve_una_afinacion_conocida():
    """Si no, importar la misma cancion rara dos veces la reconoceria a si misma."""
    perfil = perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62])
    registrar_perfil(perfil)
    assert clave_de_perfil(perfil) is None
