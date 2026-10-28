"""Servidor FastAPI: expone la sesión a la interfaz.

Capa fina. No calcula nada musical: solo publica lo que la sesión ya produce.
"""

import asyncio
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import (
    Body,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from nucleo.afinaciones import PERFILES, PERFILES_DE_FABRICA
from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.teoria import ACORDES, ESCALAS, INTERVALOS
from nucleo.piezas.desde_ejercicio import pieza_desde_ejercicio
from nucleo.piezas.estudio import PlanDePasada
from nucleo.piezas.lectores import importar, pistas_de_archivo
from nucleo.piezas.modelo import Pieza
from servidor import configuracion as config_modulo
from servidor.canciones import (
    MARGEN_MULTIPART_BYTES,
    TAMANO_MAXIMO_BYTES,
    Biblioteca,
    afinacion_de,
    comprobar_tamano,
    formato_de,
    leer_subida,
)
from servidor.ejercicios import SesionPractica
from servidor.modulos import listar_modulos
from servidor.piezas import SesionCarril
from servidor.sesion import Sesion

# La pantalla no muestra más rápido que esto. Emitir más solo añadiría cola y, con
# ella, retardo entre lo que se toca y lo que se ve.
FRECUENCIA_EMISION = 30.0

# Los nombres con los que se puede llamar a este servidor.
#
# Esto es lo que corta el **rebinding de DNS**: el servidor escucha en
# 127.0.0.1:8420, y una web cualquiera no puede leer su respuesta por la política del
# navegador... salvo que su dominio apunte a 127.0.0.1, y entonces el navegador cree
# que sigue hablando con `evil.com` y le deja leerlo todo. Lo único que delata ese
# ataque es la cabecera `Host`, que llega con el nombre del atacante y no con el
# nuestro. Así que un `Host` que no sea uno de estos no se atiende.
ANFITRIONES_LOCALES = frozenset(
    {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0", ""}
)

# Los métodos que CAMBIAN algo y por tanto necesitan que el origen sea el nuestro.
METODOS_QUE_CAMBIAN = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Un `Origin` opaco: lo que manda un navegador cuando la página no tiene origen al
# que atribuirle nada (un `<iframe sandbox="allow-scripts">`, un documento `data:`).
# Se nombra aquí y se rechaza a propósito, no por accidente de parseo: `null` NO es
# «esta máquina», es «no te digo quién soy», y eso es precisamente el ataque.
ORIGENES_OPACOS = frozenset({"null"})


def _solo_nombre(autoridad: str) -> str:
    """El nombre de una autoridad `host:puerto`, en minúsculas y sin el puerto.

    Los corchetes de una IPv6 se conservan (`[::1]:8420` -> `[::1]`) y una IPv6 sin
    corchetes ni puerto se devuelve entera: cortar por el último `:` la partiría.

    Esto es solo para la cabecera `Host`, que no es una URL. Un `Origin` SÍ es una
    URL y se parsea con `_nombre_de_origen`.
    """
    autoridad = autoridad.strip().lower()
    if autoridad.startswith("["):
        return autoridad.split("]")[0] + "]"
    if autoridad.count(":") > 1:
        return autoridad
    return autoridad.rsplit(":", 1)[0] if ":" in autoridad else autoridad


def _nombre_de_origen(origen: str) -> str:
    """El nombre del anfitrión de un `Origin`, o `""` si no tiene ninguno.

    Devolver `""` es decir «este origen no nombra ninguna máquina», y quien llama lo
    rechaza, porque `""` nunca está en el conjunto de orígenes admitidos. Caen aquí
    `null`, `file://`, `https:` y la cadena vacía: todos ellos llegaban a valer como
    «esta máquina» cuando el `Origin` se cortaba con `_solo_nombre(netloc)` y el
    conjunto compartido con el `Host` tenía un `""` dentro.

    Se usa `hostname` y no `netloc` porque `hostname` ya normaliza a minúsculas,
    quita el `usuario@` -que es lo que hace que `http://localhost@atacante.example`
    sea en realidad `atacante.example`- y quita los corchetes de una IPv6, así que
    `http://[::1]:8420` da `::1`.
    """
    if origen.strip().lower() in ORIGENES_OPACOS:
        return ""
    try:
        nombre = urlsplit(origen.strip()).hostname
    except ValueError:
        # Una IPv6 mal cerrada (`http://[::1`) hace que `urlsplit` se queje. Un
        # origen que no se puede parsear no es el nuestro.
        return ""
    return nombre or ""


def _origenes_desde(anfitriones) -> frozenset[str]:
    """Los nombres de `anfitriones` que pueden ser el anfitrión de un `Origin`.

    Se quita la cadena vacía -un `Origin` sin nombre no se admite nunca- y los
    corchetes de las IPv6, porque `_nombre_de_origen` devuelve `::1` y no `[::1]`.
    """
    nombres = {nombre.strip().lower().strip("[]") for nombre in anfitriones}
    return frozenset(nombre for nombre in nombres if nombre)


def _numero_de_pista(valor) -> int:
    """`valor` como número de pista (base 1), o `ValueError` diciendo qué pasa.

    Se exige un entero de verdad y no se convierte nada: `int()` aceptaba `1.9` y
    `true` y los truncaba a 1 sin avisar, así que pedir la pista 1,9 -un error de
    quien llama- importaba la primera como si lo hubiera pedido bien. Y un `"2"` de
    texto se rechaza a propósito: en JSON un número se escribe sin comillas, y
    adivinar lo que quiso decir quien no sigue el formato es cómo se acaba
    adivinando mal.
    """
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ValueError(
            f"La pista se pide con un número entero, y me llegó {valor!r}."
        )
    if valor < 1:
        raise ValueError(
            f"Las pistas se numeran desde 1, así que la {valor} no existe."
        )
    return valor


def _perfil_pedido(valor) -> str | None:
    """`valor` como clave de perfil, o `None`, o `ValueError` diciendo que pasa.

    Solo el TIPO. Que el perfil EXISTA lo decide el nucleo, que ademas enumera los
    que hay (`desde_ascii`: "El perfil 'x' no existe. Opciones: ..."); repetir aqui
    esa lista seria tener dos catalogos y uno de los dos se quedaria viejo.

    Hace falta porque `perfil` llega de un cuerpo sin tipar y acaba en un `in` sobre
    el registro de perfiles, que es un `dict`: `{"perfil": ["x"]}` salia como
    `TypeError: unhashable type: 'list'`, es decir un mensaje interno de Python en
    una respuesta de usuario. Es el mismo problema que tenia el nombre de la cancion
    (`_nombre_seguro`) y se arregla igual, en el sitio por el que pasa el valor.
    """
    if valor is None or isinstance(valor, str):
        return valor
    raise ValueError(
        f"El perfil se pide con su clave en texto, y me llegó {valor!r}."
    )


def _mensaje_peticion_enorme(declarados: int) -> str:
    megas = TAMANO_MAXIMO_BYTES // (1024 * 1024)
    return (
        f"La petición declara {declarados} bytes y el máximo por archivo son "
        f"{megas} MB ({TAMANO_MAXIMO_BYTES} bytes). No la leo."
    )


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
    anfitriones: set[str] | None = None,
) -> FastAPI:
    """Construye la aplicación alrededor de una sesión ya creada.

    `carpeta_canciones` es la biblioteca: `canciones/` si no se dice otra cosa, y
    `tmp_path` en las pruebas, para que ninguna ensucie la carpeta del proyecto.

    `anfitriones` son los nombres por los que se admite que llamen al servidor
    (`ANFITRIONES_LOCALES` si no se dice otra cosa); ver `guardia_de_peticiones`.
    De ahí salen DOS conjuntos y no uno: el del `Host`, tal cual se da, y el de los
    `Origin` admitidos (`_origenes_desde`), que es el mismo sin la cadena vacía.

    **Hoy nadie le pasa `anfitriones`**, y se queda a propósito: es el único modo de
    inyectar esa lista en una prueba sin tocar una constante global del módulo, que
    es lo que hace que una prueba del guardia dependa del orden en que se ejecutan
    los archivos. Si se borra, probar el guardia con otros nombres obliga a
    monkeypatchear `ANFITRIONES_LOCALES`.
    """
    app = FastAPI(title="proyecto_musica")
    app.state.sesion = sesion
    app.state.ruta_config = config_modulo.RUTA_POR_DEFECTO
    app.state.practica = practica or SesionPractica(sesion)
    app.state.carril = carril or SesionCarril(sesion)
    app.state.biblioteca = (
        Biblioteca(carpeta_canciones) if carpeta_canciones is not None else Biblioteca()
    )
    app.state.anfitriones = set(anfitriones or ANFITRIONES_LOCALES)
    app.state.origenes = _origenes_desde(app.state.anfitriones)

    def _anfitrion_ajeno(cabeceras) -> str | None:
        """El nombre del `Host` si NO es uno de los nuestros; `None` si vale.

        Un `Host` ausente se ADMITE, y es una decisión escrita: HTTP/1.0 no lleva esa
        cabecera y las herramientas de terminal tampoco siempre, y la terminal es el
        modo normal de usar este servidor. Lo que delata el rebinding de DNS es un
        `Host` con el nombre del atacante, no uno vacío: un navegador no puede omitir
        esa cabecera. Antes esto pasaba igual, pero por el efecto colateral de tener
        un `""` en el conjunto que compartían `Host` y `Origin`, donde sí abría un
        agujero.
        """
        anfitrion = _solo_nombre(cabeceras.get("host", ""))
        return None if anfitrion in app.state.anfitriones else anfitrion

    def _origen_ajeno(cabeceras) -> str | None:
        """El `Origin` si está presente y NO es el nuestro; `None` si vale o falta.

        Un `Origin` ausente se admite (`curl`); un `Origin` presente que no nombre
        esta máquina se rechaza, y eso incluye todos los que no nombran ninguna:
        `null`, `file://`, `https:` y la cadena vacía (ver `_nombre_de_origen`).
        """
        origen = cabeceras.get("origin")
        if origen is None:
            return None
        return None if _nombre_de_origen(origen) in app.state.origenes else origen

    @app.middleware("http")
    async def guardia_de_peticiones(peticion: Request, siguiente):
        """Rechaza lo que no viene de esta máquina, antes de mirar qué pide.

        El servidor escucha en localhost y no pide contraseña: cualquier web que el
        usuario visite mientras practica puede mandarle un `POST` a
        `127.0.0.1:8420` y cambiarle la afinación, detenerle la pieza o subirle un
        archivo. Eso es CSRF, y aquí se corta en tres reglas:

        1. **`Host` tiene que ser localhost.** Es lo único que delata el rebinding
           de DNS (ver `ANFITRIONES_LOCALES`). Vale para TODOS los métodos, también
           los `GET`: con el rebinding, un `GET` ya se lleva la lista de canciones.
           Un `Host` ausente se admite, por decisión escrita en `_anfitrion_ajeno`.
        2. **Si viene `Origin`, tiene que ser el nuestro.** El navegador la pone
           siempre en las peticiones que cambian estado y NO deja que la página la
           falsee, así que un `Origin: https://cualquier.sitio` es exactamente el
           ataque y se rechaza con 403. Y un `Origin` que no nombra ninguna máquina
           -`null`, `file://`, `https:`, la cadena vacía- se rechaza igual: `null`
           es lo que manda un `<iframe sandbox="allow-scripts">` o un documento
           `data:` de una web ajena, y un `POST` con `FormData` es petición CORS
           simple, así que no hay preflight que lo pare. Cuando el `Origin` se
           comparaba contra el mismo conjunto que el `Host` -con su `""` dentro para
           admitir el `Host` ausente- esos cuatro valían como «esta máquina» y la
           página de un atacante podía subir un archivo a la biblioteca.
        3. **Si no viene `Origin`, se deja pasar.** No es un descuido: `curl`, los
           scripts y las herramientas de línea de comandos no la mandan, y son el
           modo normal de usar este servidor desde la terminal. Un navegador no
           puede omitirla en una petición que cambia estado, así que dejarla pasar
           no abre la puerta que acabamos de cerrar. Ausente no es lo mismo que
           opaca: la regla 2 cubre la diferencia.

        Se compara el NOMBRE y no el puerto, a propósito: el servidor de desarrollo
        de la interfaz vive en `localhost:5173` y hace de proxy hacia el 8420, así
        que exigir el puerto exacto habría roto el modo en que se desarrolla esto.
        Y distinguir puertos no defendería de nada: cualquier proceso de esta máquina
        puede hablar con el servidor sin pasar por un navegador.

        Lo que este guardia NO cubre, y es una decisión escrita y no un descuido:
        **un `GET` con efecto secundario.** La regla 2 solo mira el `Origin` en los
        métodos que cambian algo (`METODOS_QUE_CAMBIAN`), porque da por hecho que un
        `GET` no cambia nada, y hoy hay uno que sí:
        `GET /api/canciones/{id}/pistas` da de alta en `PERFILES` la afinación de
        cada pista del archivo (`desde_guitarpro._clave_de_pista`). Así que un
        `<img src="http://127.0.0.1:8420/api/canciones/x.gp5/pistas">` de una web
        ajena puede provocar esas escrituras: el `Host` que llega es el nuestro, de
        modo que la regla 1 no lo para, y la respuesta no se la lleva nadie —la
        política del navegador se la niega—, pero la escritura ocurre.

        **Se deja así**, y aquí está lo que lo acota y lo que costaría cerrarlo:

        - El alta es un `setdefault` en un diccionario en memoria, derivado de las
          cuerdas del archivo. No escribe en el disco, no cambia la configuración ni
          la afinación activa, y no quita nada: `registrar_perfil` no reemplaza una
          entrada que ya esté. Lo peor que consigue una web ajena es dejar entradas
          en un diccionario del proceso, y solo de archivos que ya están en la
          biblioteca del usuario (el `{id}` se resuelve contra la carpeta).
        - `/api/perfiles` publica las de fábrica más la ACTIVA, así que una entrada
          colada ahí no aparece en el selector del afinador ni se puede elegir.
        - Lo que NO se puede hacer es dejar el alta para el `POST`: la clave que
          propone el aviso de afinación tiene que existir en `PERFILES` cuando el
          usuario pulsa «Afinarme a…», porque `Configuracion` valida el perfil
          contra ese registro y si no está el botón contesta 400. Registrar solo al
          importar es exactamente el fallo que se arregló en esta etapa —el aviso no
          funcionaba la primera vez que abrías la canción—, así que cerrar esto por
          ahí vuelve a romperlo.
        - El arreglo que sí cabría, si algún día molesta: exigir el `Origin` también
          en los `GET` que mutan, con una lista explícita de esas rutas. No rompería
          la terminal —`curl` no manda `Origin` y un `Origin` ausente se admite por
          la regla 3—, así que el coste es la lista: hay que mantenerla a mano, y una
          ruta que empiece a mutar y no se apunte deja el agujero abierto sin que
          nada avise. Mientras el único efecto sea una entrada en un diccionario que
          nadie puede elegir, esa lista cuesta más de lo que cierra.

        Los WebSocket no pasan por este middleware -ASGI no los enruta por aquí-,
        así que montan las mismas comprobaciones por su cuenta antes de aceptar la
        conexión: ver `_vigilar_websocket`.

        De paso, la puerta de `Content-Length`: una subida que ya se declara más
        grande que el techo se rechaza aquí, antes de que el parseador de multipart
        reciba el cuerpo y lo vuelque a un archivo temporal.
        """
        anfitrion = _anfitrion_ajeno(peticion.headers)
        if anfitrion is not None:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": (
                        f"No atiendo peticiones dirigidas a '{anfitrion}'. Este "
                        f"servidor es local: llámalo por localhost."
                    )
                },
            )
        if peticion.method in METODOS_QUE_CAMBIAN:
            origen = _origen_ajeno(peticion.headers)
            if origen is not None:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": (
                            f"'{origen}' no es esta máquina y no puede cambiar nada "
                            f"aquí."
                        )
                    },
                )
        declarado = peticion.headers.get("content-length")
        if declarado is not None and declarado.isdigit():
            if int(declarado) > TAMANO_MAXIMO_BYTES + MARGEN_MULTIPART_BYTES:
                return JSONResponse(
                    status_code=400,
                    content={"detail": _mensaje_peticion_enorme(int(declarado))},
                )
        return await siguiente(peticion)

    async def _vigilar_websocket(websocket: WebSocket) -> bool:
        """`True` si se puede atender este WebSocket; si no, lo cierra con 1008.

        Las mismas comprobaciones de `guardia_de_peticiones`, hechas ANTES de
        `accept()`, porque los WebSocket no pasan por el middleware `http` y sin esto
        una pestaña cualquiera conectaba a `/ws/notas` y se llevaba la telemetría del
        micrófono -qué nota suena, cuándo se toca y con cuánto nivel- a 30 Hz. Y un
        `Host` ajeno pasaba, que es sortear también la defensa de rebinding.

        El `Origin` se exige igual que en http CON UNA DIFERENCIA: aquí la regla 3
        del middleware -«si no viene `Origin`, se deja pasar»- se apoya en que un
        navegador no puede omitirlo, y en los WebSocket eso es aún más cierto (el
        navegador lo manda SIEMPRE, también en el handshake). Así que un `Origin`
        ausente sigue admitiéndose, porque hay clientes de terminal, y un `Origin`
        presente que no sea el nuestro se rechaza.

        Se cierra ANTES de `accept()`, que es rechazar en el handshake, y eso es lo
        correcto: la conexión no llega a existir. El código 1008 que se pasa aquí es
        casi decorativo, y decir que «el cliente tiene que poder distinguir 1008 de
        1000» era inexacto: un cierre previo al `accept()` lo traduce ASGI a un
        HTTP 403 en el handshake, así que ningún cliente real recibe la trama 1008
        -solo `TestClient`, que la sintetiza-. Lo que el cliente ve es el 403, y con
        eso ya distingue «no te quiero» de «ya hemos terminado».
        """
        if (
            _anfitrion_ajeno(websocket.headers) is not None
            or _origen_ajeno(websocket.headers) is not None
        ):
            await websocket.close(code=1008)
            return False
        return True

    @app.get("/api/modulos")
    def leer_modulos() -> list[dict]:
        """Módulos disponibles. La interfaz los descubre aquí, no los tiene escritos."""
        return [modulo.a_dict() for modulo in listar_modulos()]

    @app.get("/api/perfiles")
    def leer_perfiles() -> list[dict]:
        """Perfiles de afinación con sus cuerdas, para dibujar el mástil.

        Se publican los DE FÁBRICA **más el perfil activo si no es de fábrica**, y no
        el registro vivo `PERFILES` entero.

        Por qué no el registro vivo: crece cada vez que se importa una canción en una
        afinación rara (`registrar_perfil`), así que publicarlo entero llenaba el
        selector del afinador de entradas como «Afinación C2 G2 C3 F3 A3 D4 (24
        trastes)»: una afinación que el usuario no eligió y a la que nadie quiere
        afinarse.

        Por qué el activo además: `/pistas` propone la clave de la afinación que pide
        la canción, `PUT /api/config` la acepta, y entonces el afinador se quedaba con
        un perfil que esta lista no incluía. El usuario veía su mástil en Drop C y el
        selector sin ninguna opción marcada, sin forma de volver: la lista de lo
        elegible tiene que contener, como mínimo, lo que está elegido.
        """
        activo = app.state.sesion.configuracion.perfil
        perfiles = dict(PERFILES_DE_FABRICA)
        if activo not in perfiles and activo in PERFILES:
            perfiles[activo] = PERFILES[activo]
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
            for clave, perfil in perfiles.items()
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
        if not await _vigilar_websocket(websocket):
            return
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
        if not await _vigilar_websocket(websocket):
            return
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

    def _pieza_para_el_carril(datos: dict) -> Pieza:
        """La pieza que pide `datos`: un ejercicio generado o una cancion del disco.

        Hay DOS formas de pedir una pieza y son exclusivas:

        - `{familia, parametros}`: un ejercicio del catalogo, traducido a pieza por
          `pieza_desde_ejercicio`. Es la de la etapa 3a.
        - `{cancion, pista, perfil}`: una cancion de la biblioteca, leida del
          archivo con el MISMO `importar(ruta, numero, perfil)` que usa
          `/api/canciones/{id}/importar`. `cancion` es el `id` -el nombre del
          archivo-, `pista` va en base 1 y `perfil` es opcional, igual que alli.

        Que la cancion la lea el SERVIDOR, y no el navegador que la manda ya leida,
        es lo que mantiene una sola puerta al carril: la que aplica la regla de
        afinacion de la etapa 3a (`SesionCarril.iniciar`). Aceptar una `Pieza` del
        cliente seria creerle las notas, el perfil con el que dice estar escrita y,
        con el, la afinacion que el carril tiene que comprobar.

        Las dos formas a la vez, o ninguna, es un pedido mal hecho: 400 diciendo
        cual falta. Decidirlo por la PRESENCIA de la clave y no por su valor es a
        proposito: `{"familia": ""}` es pedir un ejercicio sin decir cual -y el
        generador contesta cuales hay-, no es «no he pedido nada».

        Los TRES valores que trae el cuerpo pasan por `_leer_o_400`, y el de
        `cancion` tambien: aqui salen de un `dict` sin tipar, no de la ruta -donde
        FastAPI ya los tipa `str` antes de que `/importar` los vea-, asi que
        `{"cancion": 123}` llegaba hasta `unicodedata.normalize` y salia como un
        `TypeError` sin capturar, es decir un 500: «el servidor se ha roto», que es
        mentira. Un parametro con un tipo que no es el suyo es un pedido mal hecho,
        igual que una pista que no es entera.

        `_ruta_de_cancion` y `_leer_o_400` viven mas abajo, en la seccion de la
        biblioteca; se llaman desde aqui como cierres, que se resuelven al llamar.
        """
        pide_cancion = "cancion" in datos
        pide_ejercicio = "familia" in datos
        if pide_cancion and pide_ejercicio:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Me has pedido las dos cosas a la vez: un ejercicio "
                    "('familia') y una cancion ('cancion'). Elige una."
                ),
            )
        if not pide_cancion and not pide_ejercicio:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No me has dicho que tocar: hace falta 'familia' (un ejercicio "
                    "del catalogo) o 'cancion' (el id de una cancion de la "
                    "biblioteca)."
                ),
            )
        if pide_cancion:
            ruta = _leer_o_400(lambda: _ruta_de_cancion(datos["cancion"]))
            numero = _leer_o_400(lambda: _numero_de_pista(datos.get("pista", 1)))
            perfil = _leer_o_400(lambda: _perfil_pedido(datos.get("perfil")))
            return _leer_o_400(lambda: importar(ruta, numero, perfil))
        return pieza_desde_ejercicio(_generar_o_400(datos))

    def _campos_del_plan(datos: dict) -> dict:
        """Convierte SOLO los campos del plan que el cuerpo trae.

        Lo ausente no aparece en el resultado: que valga el valor de fabrica
        (`iniciar`) o el del plan vigente (`plan`) lo decide quien lo recibe.
        Un `ultimo_compas` presente y `null` si cuenta y es "hasta el final".
        Un valor de tipo imposible sale como `TypeError`/`ValueError`, que el
        llamador traduce a 400.
        """
        conversores = {
            "primer_compas": int,
            "ultimo_compas": lambda v: None if v is None else int(v),
            "factor_tempo": float,
            "en_bucle": bool,
            "compases_de_cuenta_atras": int,
            "con_click": bool,
            "tempo_automatico": bool,
        }
        return {
            campo: convertir(datos[campo])
            for campo, convertir in conversores.items()
            if campo in datos
        }

    def _plan_pedido(datos: dict) -> PlanDePasada:
        """El plan del cuerpo de `iniciar`: lo que falta es el valor de fabrica.

        Ese es el comportamiento de la etapa 3a. `PlanDePasada` valida lo suyo y
        lanza `ValueError`; el llamador lo traduce a 400.
        """
        return PlanDePasada(**_campos_del_plan(datos))

    @app.post("/api/piezas/iniciar")
    def iniciar_pieza(datos: dict = Body(...)) -> dict:
        """Pone una pieza en marcha: un ejercicio generado o una cancion del disco.

        Las dos formas de pedirla, y por que la cancion la lee el servidor, en
        `_pieza_para_el_carril`.

        Devuelve la pieza ENTERA una sola vez, junto con el estado inicial: el
        navegador la guarda y no vuelve a pedirla. Mandarla tambien por el
        WebSocket, treinta veces por segundo, seria desperdiciar el canal en
        notas que no cambian. Quien recargue el navegador a mitad de cancion la
        vuelve a pedir por `/api/piezas/pieza`.

        `plan` es opcional, y sin el la pasada es la de la etapa 3a: la pieza
        entera, a tempo escrito, sin bucle y sin click.
        """
        pieza = _pieza_para_el_carril(datos)
        try:
            # El plan se construye DENTRO del `try`: un factor imposible es un
            # pedido mal hecho igual que una afinacion que no cuadra, y fuera de
            # aqui su `ValueError` saldria como un 500, es decir "el servidor se
            # ha roto", que es mentira.
            plan = _plan_pedido(datos["plan"]) if datos.get("plan") else None
            return app.state.carril.iniciar(pieza, plan)
        except (TypeError, ValueError) as error:
            # La afinacion de la pieza no coincide con la activa (spec §5), o el
            # plan pide algo que la pieza no tiene: es un pedido mal formado, no
            # una rotura del servidor. El `TypeError` es por lo mismo que en
            # `_generar_o_400`: un valor con un tipo que no es el suyo
            # (`{"primer_compas": null}`) sale de Python como `TypeError`, y
            # dejarlo subir lo convertia en un 500.
            raise HTTPException(status_code=400, detail=str(error))

    @app.post("/api/piezas/detener")
    def detener_pieza() -> dict:
        app.state.carril.detener()
        return app.state.carril.estado()

    @app.get("/api/piezas/estado")
    def leer_estado_pieza() -> dict:
        return app.state.carril.estado()

    @app.post("/api/piezas/plan")
    def cambiar_plan_pieza(datos: dict = Body(...)) -> dict:
        """Cambia el plan de la pasada en caliente, sin reiniciar nada.

        Es un PATCH semantico aunque la ruta sea un POST: cada campo que el
        cuerpo no diga conserva el valor del plan VIGENTE, no el de fabrica. Mandar
        `{"factor_tempo": 0.7}` mueve solo el tempo. (`/api/piezas/iniciar` es
        otra cosa: no hay plan vigente, y lo ausente es el valor de fabrica.)
        Sin pieza en marcha, 400.
        """
        try:
            return app.state.carril.parchar_plan(_campos_del_plan(datos))
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.post("/api/piezas/saltar")
    def saltar_de_compas(datos: dict = Body(...)) -> dict:
        """Mueve el cabezal al principio de un compas del tramo que se estudia."""
        try:
            return app.state.carril.saltar(int(datos["compas"]))
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error) or "Falta el compas")

    @app.post("/api/piezas/pausa")
    def pausar_pieza(datos: dict = Body(...)) -> dict:
        """La pausa DEL USUARIO, que no es la pausa por falta de señal.

        Es explicita (`activa`) y no un interruptor: dos clics seguidos desde dos
        pestañas no pueden dejar el carril en el estado contrario al que las dos
        pidieron.
        """
        try:
            return app.state.carril.pausa(bool(datos.get("activa", True)))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.get("/api/piezas/informe")
    def leer_informe_pieza() -> dict:
        """Lo tocado en esta pasada, compas a compas, y el historial de la pieza."""
        try:
            return app.state.carril.informe()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.get("/api/piezas/pieza")
    def leer_pieza_en_marcha() -> dict:
        """La pieza en marcha, para el navegador que se acaba de recargar."""
        return app.state.carril.pieza_en_marcha()

    @app.websocket("/ws/piezas")
    async def emitir_pieza(websocket: WebSocket) -> None:
        """Emite el estado del carril a 30 Hz, igual que el de los ejercicios.

        Nunca la pieza: ya viajo entera en la respuesta de `/iniciar`. Lo que se
        manda aqui tiene que bastar para mover el cabezal sin que la interfaz
        recalcule nada que el nucleo ya decidio.
        """
        if not await _vigilar_websocket(websocket):
            return
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

    def _sin_rutas(texto: str) -> str:
        """El mensaje sin la ruta absoluta de la carpeta de canciones.

        Los mensajes del sistema -y algunos de los lectores- traen la ruta entera
        (`[Errno 13] Permission denied: '/Users/quien-sea/.../canciones/x.gp5'`).
        Decirle al navegador dónde vive la carpeta y cómo se llama el usuario de la
        máquina no le sirve de nada y se lo cuenta a cualquiera que mire la
        respuesta. El nombre del archivo sí, que es lo que el usuario reconoce.
        """
        carpeta = str(app.state.biblioteca.carpeta.resolve())
        return texto.replace(carpeta + "/", "").replace(carpeta, "")

    def _leer_o_400(accion):
        """Ejecuta una lectura de archivo y traduce sus fallos a un 400.

        Se capturan tres cosas y ninguna sobra:

        - `ValueError`: lo que lanzan los lectores cuando el archivo no sirve o la
          pista pedida no existe, ya con el mensaje escrito para el usuario.
        - `TypeError`: un parámetro con un tipo que no es el suyo sale de Python
          así, igual que en `_generar_o_400`. Es un pedido mal hecho, no una rotura.
        - `OSError`: **la clase, no una lista de nombres**. Los lectores de `.txt` y
          `.tab` abren el archivo ellos mismos, así que de aquí sale todo lo que el
          disco puede decir: `FileNotFoundError` si desapareció entre la
          comprobación y la lectura, `PermissionError` si el archivo llegó de otro
          disco sin permiso de lectura -que es de lo más normal al copiar una
          carpeta de canciones-, `IsADirectoryError`, un error de entrada/salida.
          Antes había una lista nominal con dos de esos nombres y `PermissionError`
          se escapaba como un 500, es decir, «el servidor se ha roto»: mentira, y
          no le decía al usuario que lo que tiene que arreglar son los permisos.
        """
        try:
            return accion()
        except (ValueError, TypeError, OSError) as error:
            raise HTTPException(status_code=400, detail=_sin_rutas(str(error)))

    def _avisos_de(pieza) -> list[str]:
        """Lo que hay que advertir de una pieza recién importada, en frases.

        Cuatro, y los cuatro son cosas que la pieza ya sabe de sí misma y que nadie
        le estaba contando al usuario:

        - El ritmo aproximado de la tablatura de texto.
        - El tempo variable. `Pieza` se queda con el primero, así que una canción
          que acelera se toca entera al tempo del principio.
        - El compás variable. Importa el doble, porque además de tocarse con el
          compás equivocado **la vista escrita trocea la pieza con uno solo**
          (`interfaz/src/vistaEscrita.ts`): con un 3/4 en medio, las barras caen en
          el sitio equivocado desde ahí hasta el final.
        - Las casillas de primera y segunda vez de Guitar Pro, que producen un
          compás de más. Este era el que faltaba, y faltaba solo porque el lector no
          las detectaba: aquí ya estaba el sitio, dicho en este mismo docstring.
          Ahora las detecta (`_tiene_casillas_de_repeticion`), y el compás de más
          sigue sonando: lo que cambia es que el usuario sepa por qué. Arreglar el
          expansor es la etapa 3c.

        El tempo y el compás variables se detectaban, se guardaban en la pieza y no
        llegaban a ninguna parte: el campo estaba puesto y esta función no lo
        miraba. La pantalla pinta estas frases tal cual, así que añadirlas no toca
        la interfaz ni la forma de la respuesta.
        """
        avisos = []
        if pieza.ritmo_aproximado:
            avisos.append(
                "El ritmo de esta pieza es APROXIMADO: el archivo no lo trae y se ha "
                "deducido del espaciado, así que las duraciones pueden no cuadrar."
            )
        if pieza.tempo_variable:
            avisos.append(
                f"La canción CAMBIA DE TEMPO y aquí se toca entera a {pieza.tempo} "
                f"ppm, el primero que trae el archivo."
            )
        if pieza.compas_variable:
            avisos.append(
                f"La canción CAMBIA DE COMPÁS y aquí se toca entera en "
                f"{pieza.compas[0]}/{pieza.compas[1]}, el primero que trae el "
                f"archivo. En la vista escrita, las barras de compás caerán fuera de "
                f"sitio a partir del cambio."
            )
        if pieza.casillas_de_repeticion:
            avisos.append(
                "La canción trae CASILLAS DE PRIMERA Y SEGUNDA VEZ y aquí suenan "
                "TODAS: en la repetición vuelve a sonar la casilla de primera vez, "
                "que solo debería sonar una, así que la pieza lleva un trozo de más. "
                "Con «|: A | B(1ª vez) :|» y C de segunda vez suena A B A B C, "
                "cuando lo correcto es A B A C."
            )
        return avisos

    @app.get("/api/canciones")
    def leer_canciones() -> list[dict]:
        """Las canciones de la carpeta. La carpeta es la base de datos."""
        return app.state.biblioteca.listar()

    @app.post("/api/canciones")
    async def subir_cancion(archivo: UploadFile = File(...)) -> dict:
        """Guarda un archivo en la carpeta y devuelve su ficha.

        El nombre, el formato y el tamaño se comprueban antes de LEER el archivo, y
        el tamaño se mira en `archivo.size`, que ya es el de verdad.

        Lo que no hay que creerse: cuando esta función empieza, Starlette ya ha
        recibido el cuerpo entero y el archivo temporal del `UploadFile` ya está
        volcado al disco. Así que «rechazar antes de leer» significa antes de
        traerlo a memoria y antes de dejarlo en la biblioteca, no antes de
        recibirlo: un `.pdf` de 100 MB se rechaza con 400 cuando los 100 MB ya han
        llegado. Lo único que corta antes es la puerta de `Content-Length` del
        guardia de peticiones. Decirlo importa porque la versión anterior de este
        docstring prometía que no se traía «un solo byte», y era falso.

        El nombre que se usa es el SANEADO (`ruta.name`), el mismo con el que se va
        a guardar, y no el que llegó. Antes el formato se comprobaba sobre el crudo
        y el archivo se guardaba con el saneado, así que `'x.txt '` daba 400 por su
        extensión `'.txt '` mientras `' x.txt'` pasaba y se guardaba como `'x.txt'`,
        pisando lo que hubiera: dos nombres equivalentes, dos destinos distintos.
        """
        try:
            nombre = app.state.biblioteca.ruta_de(archivo.filename or "").name
            formato_de(nombre)
            if archivo.size is not None:
                comprobar_tamano(archivo.size)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=_sin_rutas(str(error)))
        try:
            datos = await leer_subida(archivo.read)
            return app.state.biblioteca.guardar(nombre, datos)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=_sin_rutas(str(error)))
        except OSError as error:
            # Escribir falló: disco lleno, permisos de la carpeta, un nombre que el
            # sistema no acepta. No es culpa de quien subió el archivo, así que es un
            # 500 y no un 400, pero con un mensaje que se pueda leer.
            raise HTTPException(
                status_code=500,
                detail=_sin_rutas(f"No pude guardar '{nombre}': {error}"),
            )
        finally:
            # Cierra el archivo temporal del `UploadFile`. Sin esto, cada subida deja
            # un descriptor abierto -y un archivo en /tmp- hasta que el recolector
            # pase, que en un servidor que no se reinicia es «nunca a tiempo».
            await archivo.close()

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

        **Y se devuelven DOS VECES: por canción y por pista.** El par de nivel
        canción es el de la primera pista usable, es decir el de la pista que se
        importará si el usuario no elige otra, y sirve para avisar antes de elegir
        ninguna. El que decide es el de la PISTA, porque lo que se importa es una
        pista: con un `.gp5` de pista 1 en estándar y pista 2 en Drop C, el de la
        canción decía «coincide» y la pista 2 daba un 400 al arrancar, sin ofrecer
        «Afinarme a...» porque a nivel canción no había nada que avisar. La
        `afinacion` por pista ya se publicaba; el `coincide` por pista es lo que
        faltaba para que la interfaz no tenga que compararlo ella.

        `coincide` es `True`, `False` o **`None`**, y los tres significan cosas
        distintas. `None` es «el archivo no dice en qué afinación está», que es lo
        que pasa con MIDI y con MusicXML sin tablatura: ahí no hay nada a lo que
        afinarse -la pieza se importa en el perfil activo y el carril la acepta-, y
        responder `False` hacía que la pantalla dijera «no cuadra, aféinate a null»
        cuando no había ningún problema que resolver.

        `numero` es el único campo de la pista que identifica una pista, va en base 1
        como en todo el núcleo, y es lo que espera `/importar`. Hubo un `indice` en
        base 0 al lado; publicar los dos era servir la trampa en bandeja.
        """
        ruta = _ruta_de_cancion(identificador)
        pistas = _leer_o_400(lambda: pistas_de_archivo(ruta))
        perfil_activo = app.state.sesion.configuracion.perfil

        def _afinacion(pista) -> dict:
            """La afinación de una pista, con la clave QUE PUSO SU LECTOR.

            `pista.perfil_clave` es la clave con la que el lector dio de alta el
            perfil de esta pista, y es exactamente la que traerá la pieza. Deducirla
            otra vez a partir de las cuerdas proponía otra en cuanto había dos
            perfiles de la misma afinación con distinto número de trastes.
            """
            return afinacion_de(pista.cuerdas_midi, pista.perfil_clave)

        def _coincide(afinacion: dict) -> bool | None:
            """Si la afinación activa es la que pide esta afinación; None si no pide."""
            if not afinacion["declarada"]:
                return None
            return afinacion["clave"] == perfil_activo

        publicadas = []
        for pista in pistas:
            suya = _afinacion(pista)
            publicadas.append(
                {**pista.a_dict(), "afinacion": suya, "coincide": _coincide(suya)}
            )
        usables = [pista for pista in pistas if pista.usable]
        # La afinación de la canción es la de la primera pista que se puede tocar:
        # es la que se va a importar si el usuario no elige otra.
        referencia = (usables or list(pistas))[0] if pistas else None
        afinacion = _afinacion(referencia) if referencia else afinacion_de(())
        return {
            **app.state.biblioteca.entrada_de(identificador),
            "pistas": publicadas,
            "afinacion": afinacion,
            "perfil_activo": perfil_activo,
            "coincide": _coincide(afinacion),
        }

    @app.post("/api/canciones/{identificador}/importar")
    def importar_cancion(identificador: str, datos: dict = Body(default={})) -> dict:
        """Convierte una pista en `Pieza` y la devuelve, SIN ponerla en marcha.

        Devuelve la pieza entera -con sus avisos- y nada más: ponerla en marcha es
        `/api/piezas/iniciar`, que es quien comprueba la afinación activa. Separarlo
        deja previsualizar una canción en otra afinación sin que el carril la
        rechace, que es justo cuando el usuario necesita ver a qué afinarse.

        `pista` es el NÚMERO de pista, en base 1, el mismo que publica `/pistas` y el
        mismo que entiende el núcleo. Empezó en base 0 y se traducía aquí con un
        `+1`: la traducción no se notaba cuando funcionaba y se notaba mal cuando no
        -pedir la pista 99 contestaba «la pista 100 no existe»-, y una interfaz que
        mandara el `numero` en vez del índice importaba la pista SIGUIENTE sin dar
        ningún error. Una sola numeración, la del núcleo, y nadie tiene que traducir.

        `perfil` es opcional y solo cuenta donde el archivo no trae afinación (MIDI,
        MusicXML sin tablatura, texto). Si no se da, manda lo que diga el archivo:
        reinterpretar una tablatura en Drop D con el perfil activo dibujaría trastes
        que la canción no toca.
        """
        ruta = _ruta_de_cancion(identificador)
        numero = _leer_o_400(lambda: _numero_de_pista(datos.get("pista", 1)))
        perfil = _leer_o_400(lambda: _perfil_pedido(datos.get("perfil")))
        pieza = _leer_o_400(lambda: importar(ruta, numero, perfil))
        return {**pieza.a_dict(), "avisos": _avisos_de(pieza)}

    if ruta_interfaz is not None and ruta_interfaz.exists():
        app.mount("/", StaticFiles(directory=ruta_interfaz, html=True), name="interfaz")

    return app
