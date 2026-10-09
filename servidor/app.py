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
from nucleo.piezas.desde_ejercicio import pieza_desde_ejercicio
from servidor import configuracion as config_modulo
from servidor.ejercicios import SesionPractica
from servidor.modulos import listar_modulos
from servidor.piezas import SesionCarril
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
    carril: SesionCarril | None = None,
) -> FastAPI:
    """Construye la aplicación alrededor de una sesión ya creada."""
    app = FastAPI(title="proyecto_musica")
    app.state.sesion = sesion
    app.state.ruta_config = config_modulo.RUTA_POR_DEFECTO
    app.state.practica = practica or SesionPractica(sesion)
    app.state.carril = carril or SesionCarril(sesion)

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

        Y si cambia la AFINACIÓN con una pieza en marcha, se detiene el carril.
        La spec §7 rechaza con 400 una pieza escrita en otra afinación que la
        activa, «porque dibujar trastes que tu instrumento no tiene es peor que no
        dibujar nada», pero eso solo se comprobaba al iniciar: cambiar el perfil
        por aquí dejaba la pieza dibujando los trastes de la afinación vieja y
        todas las notas restantes saliendo falladas sin que nada lo explicara.
        Detenerla es la misma decisión que el 400, tomada en el único momento en
        que se puede tomar.
        """
        perfil_anterior = sesion.configuracion.perfil
        nueva = config_modulo.Configuracion.desde_dict(
            {**sesion.configuracion.a_dict(), **datos}
        )
        try:
            diagnostico = sesion.aplicar(nueva)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        config_modulo.guardar(nueva, app.state.ruta_config)
        if nueva.perfil != perfil_anterior:
            app.state.carril.detener()
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

    @app.get("/api/ejercicios/instrumento")
    def leer_instrumento() -> dict:
        """El instrumento con el que se van a generar los ejercicios.

        Es el perfil que el usuario tiene activo en el afinador, porque es el que
        hereda `SesionPractica.generar`. La interfaz lo necesita para no ofrecer
        una cuerda que el instrumento no tiene: con el bajo de 4 puesto, ofrecer
        la 5a o la 6a produce un 400 que el usuario tiene que descifrar.
        """
        perfil = PERFILES[app.state.sesion.configuracion.perfil]
        return {
            "clave": app.state.sesion.configuracion.perfil,
            "nombre": perfil.nombre,
            "trastes": perfil.trastes,
            "cuerdas": [
                {"numero": cuerda.numero, "nota": cuerda.nota} for cuerda in perfil.cuerdas
            ],
        }

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

    def _generar_o_400(datos: dict):
        """Genera el ejercicio pedido, o responde 400 explicando el problema.

        Se capturan `ValueError` **y** `TypeError`. Los generadores lanzan
        `ValueError` con un mensaje bueno cuando el VALOR no sirve ("el intervalo
        no existe", "el perfil no existe"), pero un parametro con un nombre que
        no existe, o con un tipo que no es el suyo, sale de Python como
        `TypeError` (`traste_minimo="x"` o `repeticion=3`). Esos son
        configuraciones mal pedidas igual que los otros, y la spec §5 dice que se
        rechacen explicando el problema: dejarlos subir los convertia en un 500,
        es decir en "el servidor se ha roto", que es mentira y no dice nada de lo
        que el usuario tiene que corregir.
        """
        try:
            return app.state.practica.generar(
                datos.get("familia", ""), **datos.get("parametros", {})
            )
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.post("/api/ejercicios/generar")
    def generar_ejercicio(datos: dict = Body(...)) -> dict:
        """Genera un ejercicio sin iniciarlo, para previsualizarlo."""
        return _generar_o_400(datos).a_dict()

    @app.post("/api/ejercicios/iniciar")
    def iniciar_ejercicio(datos: dict = Body(...)) -> dict:
        """Genera un ejercicio y lo pone en marcha."""
        ejercicio = _generar_o_400(datos)
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

    @app.post("/api/piezas/desde-ejercicio")
    def generar_pieza(datos: dict = Body(...)) -> dict:
        """Genera un ejercicio y lo traduce a pieza, sin ponerla en marcha.

        El ejercicio sale del mismo generador que usan los ejercicios sueltos
        (`_generar_o_400`): una pieza de esta etapa no es mas que un ejercicio
        con cada nota fijada en cuerda, traste y pulso.
        """
        ejercicio = _generar_o_400(datos)
        return pieza_desde_ejercicio(ejercicio).a_dict()

    @app.post("/api/piezas/iniciar")
    def iniciar_pieza(datos: dict = Body(...)) -> dict:
        """Genera una pieza y la pone en marcha.

        Devuelve la pieza ENTERA una sola vez, junto con el estado inicial: el
        navegador la guarda y no vuelve a pedirla. Mandarla tambien por el
        WebSocket, treinta veces por segundo, seria desperdiciar el canal en
        notas que no cambian.
        """
        ejercicio = _generar_o_400(datos)
        pieza = pieza_desde_ejercicio(ejercicio)
        try:
            return app.state.carril.iniciar(pieza)
        except ValueError as error:
            # La afinacion de la pieza no coincide con la activa (spec §5): es
            # un pedido mal formado, no una rotura del servidor.
            raise HTTPException(status_code=400, detail=str(error))

    @app.post("/api/piezas/detener")
    def detener_pieza() -> dict:
        app.state.carril.detener()
        return app.state.carril.estado()

    @app.get("/api/piezas/estado")
    def leer_estado_pieza() -> dict:
        return app.state.carril.estado()

    @app.websocket("/ws/piezas")
    async def emitir_pieza(websocket: WebSocket) -> None:
        """Emite el estado del carril a 30 Hz, igual que el de los ejercicios.

        Nunca la pieza: ya viajo entera en la respuesta de `/iniciar`. Lo que se
        manda aqui tiene que bastar para mover el cabezal sin que la interfaz
        recalcule nada que el nucleo ya decidio.
        """
        await websocket.accept()
        intervalo = 1.0 / FRECUENCIA_EMISION
        try:
            while True:
                await websocket.send_json(app.state.carril.estado())
                await asyncio.sleep(intervalo)
        except WebSocketDisconnect:
            return

    if ruta_interfaz is not None and ruta_interfaz.exists():
        app.mount("/", StaticFiles(directory=ruta_interfaz, html=True), name="interfaz")

    return app
