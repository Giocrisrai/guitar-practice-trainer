import pytest

from nucleo.afinaciones import PERFILES, PerfilAfinacion


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
