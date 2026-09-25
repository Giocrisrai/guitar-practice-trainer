"""Servidor FastAPI: expone la sesión a la interfaz.

Capa fina. No calcula nada musical: solo publica lo que la sesión ya produce.
"""

import asyncio
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.teoria import ACORDES, ESCALAS, INTERVALOS
from servidor import configuracion as config_modulo
from servidor.ejercicios import SesionPractica
from servidor.modulos import listar_modulos
from servidor.sesion import Sesion

# La pantalla no muestra más rápido que esto. Emitir más solo añadiría cola y, con
# ella, retardo entre lo que se toca y lo que se ve.
FRECUENCIA_EMISION = 30.0

# Lo que se emite mientras el análisis todavía no ha producido nada.
SILENCIO_INICIAL = ResultadoAnalisis(
    estado="silencio", frecuencia=0.0, confianza=0.0, nivel_db=-120.0
)


def crear_app(
    sesion: Sesion,
    ruta_interfaz: Path | None = None,
    practica: SesionPractica | None = None,
) -> FastAPI:
    """Construye la aplicación alrededor de una sesión ya creada."""
    app = FastAPI(title="proyecto_musica")
    app.state.sesion = sesion
    app.state.ruta_config = config_modulo.RUTA_POR_DEFECTO
    app.state.practica = practica or SesionPractica(sesion)

    @app.get("/api/modulos")
    def leer_modulos() -> list[dict]:
        """Módulos disponibles. La interfaz los descubre aquí, no los tiene escritos."""
        return [modulo.a_dict() for modulo in listar_modulos()]

    @app.get("/api/perfiles")
    def leer_perfiles() -> list[dict]:
        """Perfiles de afinación con sus cuerdas, para dibujar el mástil."""
        return [
            {
                "clave": clave,
                "nombre": perfil.nombre,
                "trastes": perfil.trastes,
                "cuerdas": [
                    {"numero": c.numero, "nota": c.nota, "frecuencia": c.frecuencia}
                    for c in perfil.cuerdas
                ],
            }
            for clave, perfil in PERFILES.items()
        ]

    @app.get("/api/dispositivos")
    def leer_dispositivos() -> list[dict]:
        """Entradas de audio del sistema, para que el usuario elija a mano."""
        return sesion.diagnostico().a_dict()["dispositivos"]

    @app.get("/api/diagnostico")
    def leer_diagnostico() -> dict:
        """Estado del montaje: permiso, dispositivo, señal."""
        ultimo = sesion.ultimo_resultado()
        nivel = ultimo.nivel_db if ultimo is not None else None
        return sesion.diagnostico(nivel).a_dict()

    @app.get("/api/config")
    def leer_config() -> dict:
        return sesion.configuracion.a_dict()

    @app.put("/api/config")
    def escribir_config(datos: dict = Body(...)) -> dict:
        """Aplica y persiste la configuración. Valida antes de tocar nada.

        Devuelve la configuración junto con el diagnóstico de aplicarla, no la
        configuración a secas: `Sesion.aplicar()` no revierte si la reapertura del
        dispositivo falla, así que la configuración pedida se guarda igual. Si
        solo devolviéramos la configuración con un 200 llano, el usuario creería
        que todo salió bien mientras el afinador deja de mostrar notas sin
        explicación. El diagnóstico es la única forma de que se entere de que la
        apertura falló y con qué error del sistema.
        """
        nueva = config_modulo.Configuracion.desde_dict(
            {**sesion.configuracion.a_dict(), **datos}
        )
        try:
            diagnostico = sesion.aplicar(nueva)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        config_modulo.guardar(nueva, app.state.ruta_config)
        return {"configuracion": nueva.a_dict(), "diagnostico": diagnostico.a_dict()}

    @app.post("/api/calibrar")
    def calibrar(datos: dict = Body(default={})) -> dict:
        """Mide el piso de ruido y sugiere un umbral, sin aplicarlo.

        Devolver el valor en vez de imponerlo deja la decisión en el usuario.
        """
        segundos = float(datos.get("segundos", 2.0))
        return {"umbral_sugerido": round(sesion.calibrar(segundos), 1)}

    @app.websocket("/ws/notas")
    async def emitir_notas(websocket: WebSocket) -> None:
        """Emite el último resultado a 30 Hz fijos.

        Siempre el presente, aunque se repita. Nunca una cola de resultados viejos.
        """
        await websocket.accept()
        intervalo = 1.0 / FRECUENCIA_EMISION
        try:
            while True:
                resultado = sesion.ultimo_resultado()
                if resultado is None:
                    # Se construye el mismo dataclass que usa el análisis en vez
                    # de escribir el diccionario a mano: así la forma del mensaje
                    # tiene un solo dueño y añadir un campo al resultado no deja
                    # este camino emitiendo una forma distinta en silencio.
                    resultado = SILENCIO_INICIAL
                mensaje = resultado.a_dict()
                mensaje["latencia_ms"] = round(sesion.latencia_ms, 1)
                await websocket.send_json(mensaje)
                await asyncio.sleep(intervalo)
        except WebSocketDisconnect:
            return

    @app.get("/api/ejercicios/familias")
    def leer_familias() -> list[dict]:
        """Familias con sus parametros y valores admitidos.

        Esto es lo que permite que el configurador de la interfaz se construya
        solo: sin este endpoint la pantalla tendria escritas a mano unas listas
        que ya viven en teoria.py, y anadir la escala dorica obligaria a tocar
        dos sitios.
        """
        return [
            {
                "clave": "escala",
                "nombre": "Escalas",
                "descripcion": "Una escala en una posicion del mastil",
                "tipos": sorted(ESCALAS),
                "parametros": ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
            },
            {
                "clave": "arpegio",
                "nombre": "Arpegios",
                "descripcion": "Las notas de un acorde, una a una",
                "tipos": sorted(ACORDES),
                "parametros": ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
            },
            {
                "clave": "intervalo",
                "nombre": "Intervalos",
                "descripcion": "Suena una nota y tocas la que esta al intervalo pedido",
                "tipos": sorted(INTERVALOS),
                "parametros": ["intervalo", "traste_minimo", "traste_maximo", "tempo", "repeticiones"],
            },
            {
                "clave": "lectura",
                "nombre": "Lectura del mastil",
                "descripcion": "Se nombra una nota y tienes que encontrarla",
                "tipos": [],
                "parametros": ["cuerda", "traste_minimo", "traste_maximo", "tempo", "repeticiones"],
            },
        ]

    @app.post("/api/ejercicios/generar")
    def generar_ejercicio(datos: dict = Body(...)) -> dict:
        """Genera un ejercicio sin iniciarlo, para previsualizarlo."""
        try:
            ejercicio = app.state.practica.generar(
                datos.get("familia", ""), **datos.get("parametros", {})
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return ejercicio.a_dict()

    @app.post("/api/ejercicios/iniciar")
    def iniciar_ejercicio(datos: dict = Body(...)) -> dict:
        """Genera un ejercicio y lo pone en marcha."""
        try:
            ejercicio = app.state.practica.generar(
                datos.get("familia", ""), **datos.get("parametros", {})
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return app.state.practica.iniciar(ejercicio, datos.get("con_metronomo", True))

    @app.post("/api/ejercicios/detener")
    def detener_ejercicio() -> dict:
        app.state.practica.detener()
        return app.state.practica.estado()

    @app.get("/api/ejercicios/estado")
    def leer_estado_ejercicio() -> dict:
        return app.state.practica.estado()

    @app.websocket("/ws/ejercicios")
    async def emitir_ejercicio(websocket: WebSocket) -> None:
        """Emite el estado del ejercicio a 30 Hz, igual que el del afinador."""
        await websocket.accept()
        intervalo = 1.0 / FRECUENCIA_EMISION
        try:
            while True:
                await websocket.send_json(app.state.practica.estado())
                await asyncio.sleep(intervalo)
        except WebSocketDisconnect:
            return

    if ruta_interfaz is not None and ruta_interfaz.exists():
        app.mount("/", StaticFiles(directory=ruta_interfaz, html=True), name="interfaz")

    return app
