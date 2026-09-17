"""Punto de entrada: levanta el servidor y abre la interfaz en el navegador."""

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI

from servidor import configuracion as config_modulo
from servidor.app import crear_app
from servidor.sesion import Sesion

RUTA_INTERFAZ = Path(__file__).resolve().parent.parent / "interfaz" / "dist"

PUERTO_POR_DEFECTO = 8000


def construir_aplicacion(ruta_config: Path | None = None) -> tuple[FastAPI, Sesion]:
    """Crea la sesión y la aplicación.

    No falla si el cable no está conectado: el servidor levanta igual y la interfaz
    muestra el diagnóstico. Abortar aquí escondería el mensaje en la terminal, que
    es donde el usuario no lo va a buscar.
    """
    ruta = ruta_config or config_modulo.RUTA_POR_DEFECTO
    configuracion = config_modulo.cargar(ruta)
    sesion = Sesion(configuracion)
    diagnostico = sesion.iniciar()
    if diagnostico.estado != "ok":
        print(f"Aviso: {diagnostico.mensaje}")
        if diagnostico.accion:
            print(f"  {diagnostico.accion}")

    app = crear_app(sesion, RUTA_INTERFAZ)
    app.state.ruta_config = ruta
    return app, sesion


def main(argv: list[str] | None = None) -> int:
    """Arranca el servidor. Devuelve el código de salida del proceso."""
    analizador = argparse.ArgumentParser(
        prog="guitarra", description="Afinador y monitor de notas por cable Rocksmith"
    )
    analizador.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO)
    analizador.add_argument(
        "--sin-navegador", action="store_true", help="No abrir el navegador al arrancar"
    )
    argumentos = analizador.parse_args(argv)

    if not RUTA_INTERFAZ.exists():
        print("Falta la interfaz compilada.")
        print("Ejecuta:  cd interfaz && pnpm install && pnpm build")
        return 1

    import uvicorn

    app, sesion = construir_aplicacion()
    direccion = f"http://127.0.0.1:{argumentos.puerto}"

    if not argumentos.sin_navegador:
        def abrir() -> None:
            time.sleep(1.0)
            webbrowser.open(direccion)

        threading.Thread(target=abrir, daemon=True).start()

    print(f"Servidor en {direccion}  (Ctrl+C para salir)")
    try:
        uvicorn.run(app, host="127.0.0.1", port=argumentos.puerto, log_level="warning")
    finally:
        sesion.detener()
    return 0


if __name__ == "__main__":
    sys.exit(main())
