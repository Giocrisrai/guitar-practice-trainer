import pytest

from servidor.modulos import Modulo, listar_modulos, obtener_modulo, registrar_modulo


def test_el_afinador_viene_registrado():
    claves = [modulo.clave for modulo in listar_modulos()]
    assert "afinador" in claves


def test_el_afinador_esta_disponible():
    assert obtener_modulo("afinador").disponible is True


def test_se_puede_registrar_un_modulo_nuevo():
    """Las etapas siguientes añadirán ejercicios y canciones sin tocar el armazón."""
    registrar_modulo(
        Modulo(clave="ejercicios", nombre="Ejercicios", descripcion="Escalas", icono="🎯")
    )
    assert obtener_modulo("ejercicios").nombre == "Ejercicios"
    assert "ejercicios" in [m.clave for m in listar_modulos()]


def test_pedir_un_modulo_inexistente_es_un_error_claro():
    """`efectos` es de una etapa futura; `canciones` ya está registrado y servía."""
    with pytest.raises(KeyError, match="efectos"):
        obtener_modulo("efectos")


def test_el_modulo_se_serializa_para_la_interfaz():
    datos = obtener_modulo("afinador").a_dict()
    assert set(datos) == {"clave", "nombre", "descripcion", "icono", "disponible"}
