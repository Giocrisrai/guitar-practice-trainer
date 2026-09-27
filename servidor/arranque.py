"""Punto de entrada: levanta el servidor y abre la interfaz en el navegador."""

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI

from servidor import configuracion as config_modulo
from servidor.app import crear_app
from servidor.ejercicios import SesionPractica
from servidor.sesion import Sesion

RUTA_INTERFAZ = Path(__file__).resolve().parent.parent / "interfaz" / "dist"

# 8000 es el puerto por defecto de medio mundo (contenedores, otros proyectos),
# y chocar con uno ajeno da un sintoma desconcertante: el navegador abre en 8000 y
# muestra OTRA aplicacion, porque quien escucha en 127.0.0.1 gana sobre quien
# escucha en *. 8420 no es el puerto por defecto de nada conocido.
PUERTO_POR_DEFECTO = 8420


def _esperar_al_servidor(puerto: int, limite_espera: float = 15.0) -> bool:
    """Espera a que el servidor acepte conexiones en el puerto.

    Abrir el navegador tras una espera fija dejaba al usuario ante una pestana
    con error de conexion si uvicorn tardaba mas de lo previsto en arrancar.
    Devuelve True si el puerto acepta antes del limite, False si se agota.
    """
    final = time.monotonic() + limite_espera
    while time.monotonic() < final:
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.1)
    return False


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

    practica = SesionPractica(sesion)
    app = crear_app(sesion, RUTA_INTERFAZ, practica)
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
            if _esperar_al_servidor(argumentos.puerto):
                webbrowser.open(direccion)
            else:
                print(
                    f"El servidor tardó más de lo esperado en arrancar. "
                    f"Abre {direccion} a mano."
                )

        threading.Thread(target=abrir, daemon=True).start()

    print(f"Servidor en {direccion}  (Ctrl+C para salir)")
    try:
        uvicorn.run(app, host="127.0.0.1", port=argumentos.puerto, log_level="warning")
    finally:
        app.state.practica.detener()
        sesion.detener()
    return 0


if __name__ == "__main__":
    sys.exit(main())
