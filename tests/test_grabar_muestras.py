"""Comprueba que grabar_muestras no revienta con un volcado de pila sin terminal.

Escenario real: alguien ejecuta el script desde un canal sin terminal
interactivo (una tubería, una entrada redirigida). Antes, ``input()`` recibía
EOF de inmediato y el usuario se llevaba un ``Traceback`` de Python. Ahora
debe imprimir un mensaje accionable y salir con código 1, sin llegar a abrir
el dispositivo de audio.
"""

from unittest.mock import Mock

import herramientas.grabar_muestras as grabar_muestras


def test_main_sale_con_error_si_stdin_no_es_terminal(monkeypatch, capsys):
    """Sin terminal interactivo, main() debe devolver 1 sin abrir el audio.

    Ninguna prueba abre el dispositivo de audio real: si ``buscar_rocksmith``
    o ``CapturaAudio`` llegaran a invocarse, el mock de más abajo lo delataría
    lanzando una excepción.
    """
    monkeypatch.setattr(grabar_muestras.sys.stdin, "isatty", lambda: False)

    buscar_rocksmith_mock = Mock(
        side_effect=AssertionError("no debía buscarse el cable sin terminal")
    )
    captura_audio_mock = Mock(
        side_effect=AssertionError("no debía abrirse ninguna captura sin terminal")
    )
    monkeypatch.setattr(grabar_muestras, "buscar_rocksmith", buscar_rocksmith_mock)
    monkeypatch.setattr(grabar_muestras, "CapturaAudio", captura_audio_mock)

    resultado = grabar_muestras.main()

    assert resultado == 1
    buscar_rocksmith_mock.assert_not_called()
    captura_audio_mock.assert_not_called()

    salida = capsys.readouterr().out
    assert "interactivo" in salida
    assert "herramientas.grabar_muestras" in salida
    assert "Traceback" not in salida
