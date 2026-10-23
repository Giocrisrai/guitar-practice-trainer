"""Servidor FastAPI: expone la sesión a la interfaz.

Capa fina. No calcula nada musical: solo publica lo que la sesión ya produce.
"""

import asyncio
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from nucleo.afinaciones import PERFILES, PERFILES_DE_FABRICA
from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.teoria import ACORDES, ESCALAS, INTERVALOS
from nucleo.piezas.desde_ejercicio import pieza_desde_ejercicio
from nucleo.piezas.lectores import importar, pistas_de_archivo
from servidor import configuracion as config_modulo
from servidor.canciones import Biblioteca, afinacion_de, formato_de, leer_subida
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
    carpeta_canciones: Path | None = None,
) -> FastAPI:
    """Construye la aplicación alrededor de una sesión ya creada.

    `carpeta_canciones` es la biblioteca: `canciones/` si no se dice otra cosa, y
    `tmp_path` en las pruebas, para que ninguna ensucie la carpeta del proyecto.
    """
    app = FastAPI(title="proyecto_musica")
    app.state.sesion = sesion
    app.state.ruta_config = config_modulo.RUTA_POR_DEFECTO
    app.state.practica = practica or SesionPractica(sesion)
    app.state.carril = carril or SesionCarril(sesion)
    app.state.biblioteca = (
        Biblioteca(carpeta_canciones) if carpeta_canciones is not None else Biblioteca()
    )

    @app.get("/api/modulos")
    def leer_modulos() -> list[dict]:
        """Módulos disponibles. La interfaz los descubre aquí, no los tiene escritos."""
        return [modulo.a_dict() for modulo in listar_modulos()]

    @app.get("/api/perfiles")
    def leer_perfiles() -> list[dict]:
        """Perfiles de afinación con sus cuerdas, para dibujar el mástil.

        Se publican los DE FÁBRICA, no el registro vivo `PERFILES`. El registro vivo
        crece cada vez que se importa una canción en una afinación rara
        (`registrar_perfil`), así que publicarlo entero llenaba el selector del
        afinador de entradas como «Afinación C2 G2 C3 F3 A3 D4 (24 trastes)»: una
        afinación que el usuario no eligió, que no sabe de dónde salió y a la que
        nadie quiere afinarse. El registro vivo sigue existiendo para lo que es,
        resolver la clave de la afinación que pide una canción (ver `afinacion_de`).
        """
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
            for clave, perfil in PERFILES_DE_FABRICA.items()
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

    # -----------------------------------------------------------------------
    # La biblioteca de canciones: la carpeta, la subida y los dos lectores.
    # -----------------------------------------------------------------------

    def _ruta_de_cancion(identificador: str) -> Path:
        """La ruta de una canción que existe, o 400 / 404 explicando qué pasa.

        El `{id}` de la URL es el nombre del archivo y llega del navegador, así que
        pasa por el guardia de `Biblioteca` antes de tocar el disco: un nombre que
        sale de la carpeta es una peticion mal formada (400), no una canción que
        falta (404), y distinguirlos importa porque son dos arreglos distintos.
        """
        try:
            ruta = app.state.biblioteca.ruta_de(identificador)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        if not ruta.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"No tengo ninguna canción llamada '{identificador}'.",
            )
        return ruta

    def _leer_o_400(accion):
        """Ejecuta una lectura de archivo y traduce sus fallos a un 400.

        Se capturan tres excepciones y ninguna sobra:

        - `ValueError`: lo que lanzan los lectores cuando el archivo no sirve o la
          pista pedida no existe, ya con el mensaje escrito para el usuario.
        - `TypeError`: un parámetro con un tipo que no es el suyo sale de Python
          así, igual que en `_generar_o_400`. Es un pedido mal hecho, no una rotura.
        - `FileNotFoundError`: los lectores de `.txt` y `.tab` leen el archivo
          directamente y, si desaparece entre la comprobación y la lectura, lanzan
          esto y no `ValueError` como los otros tres formatos. Capturar solo
          `ValueError` dejaba ese único caso escapándose como un 500.
        """
        try:
            return accion()
        except (ValueError, TypeError, FileNotFoundError) as error:
            raise HTTPException(status_code=400, detail=str(error))

    def _avisos_de(pieza) -> list[str]:
        """Lo que hay que advertir de una pieza recién importada, en frases.

        Hoy solo el ritmo aproximado de la tablatura de texto. El sitio existe
        porque hay al menos un aviso más que dar y no está dado: las casillas de
        primera y segunda vez de Guitar Pro producen un compás de más, en silencio,
        y cuando el lector sepa detectarlo su frase va aquí, sin tocar la forma de
        la respuesta ni la interfaz.
        """
        avisos = []
        if pieza.ritmo_aproximado:
            avisos.append(
                "El ritmo de esta pieza es APROXIMADO: el archivo no lo trae y se ha "
                "deducido del espaciado, así que las duraciones pueden no cuadrar."
            )
        return avisos

    @app.get("/api/canciones")
    def leer_canciones() -> list[dict]:
        """Las canciones de la carpeta. La carpeta es la base de datos."""
        return app.state.biblioteca.listar()

    @app.post("/api/canciones")
    async def subir_cancion(archivo: UploadFile = File(...)) -> dict:
        """Guarda un archivo en la carpeta y devuelve su ficha.

        El nombre y el formato se validan ANTES de leer el cuerpo: un `.pdf` se
        rechaza sin haber traído un solo byte a la memoria.
        """
        nombre = archivo.filename or ""
        try:
            app.state.biblioteca.ruta_de(nombre)
            formato_de(nombre)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        try:
            datos = await leer_subida(archivo.read)
            return app.state.biblioteca.guardar(nombre, datos)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.get("/api/canciones/{identificador}/pistas")
    def leer_pistas(identificador: str) -> dict:
        """Las pistas del archivo y LA AFINACIÓN QUE PIDE, sin importar nada.

        Listar es barato: no se convierte ninguna nota, solo se describe lo que el
        archivo trae para que el usuario elija la pista.

        Además de las pistas se devuelven `afinacion`, `perfil_activo` y `coincide`,
        y eso LO DECIDE EL SERVIDOR. Es lo que hace accionable el aviso de «aféinate
        a esto»: la interfaz recibe la clave del perfil al que hay que afinarse y
        puede ofrecer el botón que lo cambia, en vez de comparar listas de cuerdas
        por su cuenta -que es la decisión del núcleo que esta interfaz ya ha
        duplicado siete veces- y acabar diciendo «algo no cuadra».

        `indice` de cada pista es lo que espera `/importar`, y va en base 0; `numero`
        es el que ve el usuario, y va en base 1 como en todo el núcleo. Van los dos
        porque son dos cosas distintas y confundirlas importaba una pista.
        """
        ruta = _ruta_de_cancion(identificador)
        pistas = _leer_o_400(lambda: pistas_de_archivo(ruta))
        usables = [pista for pista in pistas if pista.usable]
        # La afinación de la canción es la de la primera pista que se puede tocar:
        # es la que se va a importar si el usuario no elige otra.
        referencia = (usables or list(pistas))[0] if pistas else None
        afinacion = afinacion_de(referencia.cuerdas_midi if referencia else ())
        perfil_activo = app.state.sesion.configuracion.perfil
        return {
            **app.state.biblioteca.entrada_de(identificador),
            "pistas": [
                {
                    **pista.a_dict(),
                    "indice": indice,
                    "afinacion": afinacion_de(pista.cuerdas_midi),
                }
                for indice, pista in enumerate(pistas)
            ],
            "afinacion": afinacion,
            "perfil_activo": perfil_activo,
            "coincide": afinacion["clave"] == perfil_activo,
        }

    @app.post("/api/canciones/{identificador}/importar")
    def importar_cancion(identificador: str, datos: dict = Body(default={})) -> dict:
        """Convierte una pista en `Pieza` y la devuelve, SIN ponerla en marcha.

        Devuelve la pieza entera -con sus avisos- y nada más: ponerla en marcha es
        `/api/piezas/iniciar`, que es quien comprueba la afinación activa. Separarlo
        deja previsualizar una canción en otra afinación sin que el carril la
        rechace, que es justo cuando el usuario necesita ver a qué afinarse.

        `pista` es el ÍNDICE que trae `/pistas` (base 0) y aquí se traduce al número
        de pista del núcleo (base 1), que es el que entiende `importar`.

        `perfil` es opcional y solo cuenta donde el archivo no trae afinación (MIDI,
        MusicXML sin tablatura, texto). Si no se da, manda lo que diga el archivo:
        reinterpretar una tablatura en Drop D con el perfil activo dibujaría trastes
        que la canción no toca.
        """
        ruta = _ruta_de_cancion(identificador)
        indice = _leer_o_400(lambda: int(datos.get("pista", 0)))
        perfil = datos.get("perfil")
        pieza = _leer_o_400(lambda: importar(ruta, indice + 1, perfil))
        return {**pieza.a_dict(), "avisos": _avisos_de(pieza)}

    if ruta_interfaz is not None and ruta_interfaz.exists():
        app.mount("/", StaticFiles(directory=ruta_interfaz, html=True), name="interfaz")

    return app
