"""La biblioteca de canciones: una carpeta en el disco y nada más.

No hay base de datos. **La carpeta ES la base de datos** y el `id` de una canción es
el nombre de su archivo. Eso es lo que hace que esta clase sea, antes que nada, un
guardia: todo lo que llega del navegador —el nombre del archivo que se sube y el
`{id}` de la URL— se resuelve contra la carpeta y se rechaza si sale de ella.

    (carpeta / nombre).resolve() tiene que seguir estando dentro de carpeta.resolve()

Un `..` en la ruta no es el nombre de una canción, es un intento de leer el disco.
Las formas de salirse que se cubren, y por qué cada comprobación está donde está,
se explican en `ruta_de`.

Lo que esta clase NO hace: leer el contenido musical. De eso sabe
`nucleo/piezas/lectores.py`, y aquí solo se usa su tabla `FORMATOS` para saber qué
extensiones se admiten. El núcleo no sabe que existe un servidor.
"""

import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from nucleo.piezas.lectores import FORMATOS

# Lo más que se admite subir, por archivo.
#
# No es un límite de disco, es un límite de confianza: una partitura de Guitar Pro
# de una canción entera ocupa decenas de kilobytes y un MIDI algo menos, así que
# diez megas ya son dos órdenes de magnitud de margen.
#
# Qué limita de verdad y qué no, medido y sin adornos: cuando el handler empieza a
# correr, Starlette YA ha recibido el cuerpo entero y el `SpooledTemporaryFile` del
# `UploadFile` ya está volcado a disco. Así que este techo no evita recibir el
# archivo; evita leerlo a memoria y dejarlo en la biblioteca. Lo que sí corta antes
# de parsear nada es la puerta de `Content-Length` del guardia de peticiones
# (`servidor/app.py`), y aun esa no impide que el cuerpo viaje por el cable.
TAMANO_MAXIMO_BYTES = 10 * 1024 * 1024

# Cuánto se lee de golpe al recibir una subida. Un megabyte es bastante para que la
# lectura no sea un ir y venir de trozos pequeños y poco para que el techo de arriba
# se note en la memoria.
TROZO_BYTES = 1024 * 1024

# Lo que se le perdona a una petición de subida por encima del propio archivo: las
# cabeceras de la parte multipart, el separador y el nombre. Doscientos bytes bastan
# de sobra; 64 KiB es para no rechazar nunca un archivo bueno por la cuenta de los
# bytes del sobre, que es un error peor que admitir una petición un pelo más grande
# (al archivo lo mide después, exactamente, `comprobar_tamano`).
MARGEN_MULTIPART_BYTES = 64 * 1024

# La carpeta de producción: `canciones/` junto al código, igual que `interfaz/dist`
# (ver `servidor/arranque.py`), y no relativa al directorio de trabajo. Si dependiera
# del directorio desde el que se arranca, la biblioteca del usuario cambiaría según
# dónde abrió la terminal, que es la clase de sorpresa que hace perder archivos.
# Está en `.gitignore`: son archivos de terceros y no se distribuyen con el código.
CARPETA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "canciones"

# Separadores de ruta que se rechazan SIEMPRE, sea cual sea el sistema operativo.
# La barra invertida no separa nada en macOS ni en Linux -ahí `..\..\x` es un nombre
# de archivo legal y rarísimo-, así que sin esta lista un servidor en POSIX guardaría
# un archivo llamado `..\..\etc\hosts` que en Windows, o en un disco compartido,
# sería una ruta de verdad. No se guarda un nombre que en otra máquina es una ruta.
SEPARADORES = ("/", "\\")


def _nombre_seguro(nombre: str) -> str:
    """El nombre de archivo que `nombre` pretende ser, o `ValueError` explicándolo.

    Esta es la primera de las dos redes, y la que da los mensajes buenos. La segunda
    -resolver contra la carpeta- está en `ruta_de` y es la que manda.

    Lo primero que se comprueba es el TIPO, y se comprueba aquí y no en quien llama
    porque aquí es por donde pasan todos los nombres. La anotación dice `str`, pero
    por este camino entran valores de un cuerpo JSON sin tipar
    (`POST /api/piezas/iniciar` manda `{"cancion": ...}`), y un `nombre or ""`
    aceptaba cualquier valor veraz: un `123` llegaba hasta
    `unicodedata.normalize`, que exige `str`, y salía como
    `TypeError: normalize() argument 2 must be str, not int`. Eso acabó en una
    respuesta de usuario, que es lo que no puede pasar: el mensaje tiene que decirle
    que lo que manda no es un nombre de archivo, igual que `_numero_de_pista` le
    dice que la pista se pide con un número entero.
    """
    if not isinstance(nombre, str):
        raise ValueError(
            f"El nombre de una canción es un texto, y me llegó {nombre!r}."
        )
    # NFC: macOS entrega los nombres en NFD y el navegador suele mandarlos en NFC.
    # Normalizar aquí evita que "canción.txt" se guarde con una forma y luego no se
    # encuentre con la otra. No tiene nada que ver con la seguridad; está aquí
    # porque es el único sitio por el que pasan todos los nombres.
    nombre = unicodedata.normalize("NFC", nombre).strip()
    if not nombre:
        raise ValueError("El archivo tiene que traer un nombre.")
    if "\x00" in nombre:
        # Un byte nulo corta la cadena para quien la mire como texto de C: el
        # nombre que valida Python y el que abre el sistema podrían no ser el mismo.
        raise ValueError("El nombre del archivo trae caracteres que no son válidos.")
    if any(separador in nombre for separador in SEPARADORES):
        raise ValueError(
            f"'{nombre}' es una ruta, no el nombre de una canción: "
            "la carpeta de canciones no tiene subcarpetas."
        )
    if nombre in (".", ".."):
        raise ValueError(f"'{nombre}' no es el nombre de una canción.")
    # Después de quitar separadores, `Path(nombre).name` solo cambia si el nombre
    # era algo que Python no considera un archivo suelto (una raíz, por ejemplo).
    if Path(nombre).name != nombre:
        raise ValueError(f"'{nombre}' no es el nombre de una canción.")
    return nombre


def formato_de(nombre: str) -> str:
    """El nombre legible del formato de `nombre`, o `ValueError` con los que valen."""
    extension = Path(nombre).suffix.lower()
    if extension not in FORMATOS:
        validas = ", ".join(sorted(FORMATOS))
        raise ValueError(
            f"No sé leer archivos '{extension or 'sin extensión'}'. "
            f"Los que valen: {validas}"
        )
    return FORMATOS[extension]


class Biblioteca:
    """Las canciones que hay en una carpeta.

    La carpeta se recibe por parámetro -`canciones/` en producción, `tmp_path` en
    las pruebas- y se crea cuando hace falta escribir en ella, no al construir la
    biblioteca: construirla no toca el disco. Si lo hiciera, cada prueba de las otras
    partes del servidor -que llaman a `crear_app` sin decir nada de canciones- dejaría
    una carpeta vacía en el directorio del proyecto.
    """

    def __init__(self, carpeta: Path | str = CARPETA_POR_DEFECTO) -> None:
        self.carpeta = Path(carpeta)
        # Se guarda resuelta UNA vez: es con esta con la que se comparan las rutas,
        # y resolverla en cada comprobación haría que el guardia dependiera de que
        # nadie haya movido la carpeta por debajo. `resolve()` no exige que exista.
        self._carpeta_resuelta = self.carpeta.resolve()

    # -- el guardia ---------------------------------------------------------

    def ruta_de(self, identificador: str) -> Path:
        """La ruta del archivo de `identificador`, garantizada dentro de la carpeta.

        Lanza `ValueError` si el nombre no es un nombre de archivo o si, resuelto,
        cae fuera. Las dos comprobaciones son a propósito redundantes:

        - `_nombre_seguro` rechaza por la FORMA del nombre (`..`, `/`, `\\`, vacío,
          byte nulo, nombre absoluto). Da los mensajes que el usuario entiende.
        - `resolve()` + `is_relative_to` rechaza por el DESTINO, que es lo único que
          de verdad importa. Y como `resolve()` sigue los enlaces simbólicos, aquí
          cae también el caso que la forma del nombre no puede delatar: un
          `enlace.txt` dentro de la carpeta apuntando a `/etc/passwd`. El nombre es
          impecable; el destino, no.

        Lo que NO cubre, dicho sin adornos: un enlace simbólico que apunte a otro
        sitio DENTRO de la carpeta se acepta (y debe aceptarse, el destino es legal);
        un montaje o un disco compartido cuyo contenido no controlamos, siendo
        legal como ruta, es legal aquí; y quien pueda escribir en la carpeta ya
        tiene el disco, así que esto no le defiende de sí mismo.
        """
        nombre = _nombre_seguro(identificador)
        ruta = (self.carpeta / nombre).resolve()
        if not ruta.is_relative_to(self._carpeta_resuelta):
            raise ValueError(
                f"'{identificador}' no es el nombre de una canción de la biblioteca."
            )
        return ruta

    # -- consultas ----------------------------------------------------------

    def listar(self) -> list[dict]:
        """Las canciones de la carpeta, por nombre.

        Se salta lo que no sea un archivo de un formato conocido -subcarpetas,
        apuntes en PDF, archivos a medio copiar- y también lo que no pase el guardia:
        un enlace simbólico a un archivo de fuera existe en la carpeta, pero no es
        una canción de la biblioteca, y listarlo sería ofrecer un 400 en un menú.
        """
        if not self.carpeta.is_dir():
            return []
        canciones = []
        for ruta in sorted(self.carpeta.iterdir(), key=lambda r: r.name.lower()):
            try:
                formato = formato_de(ruta.name)
                resuelta = self.ruta_de(ruta.name)
            except ValueError:
                continue
            if not resuelta.is_file():
                continue
            canciones.append(self._entrada(ruta.name, formato, resuelta))
        return canciones

    def _entrada(self, nombre: str, formato: str, ruta: Path) -> dict:
        estado = ruta.stat()
        return {
            # El id ES el nombre del archivo: no hay otra base de datos donde
            # guardar un identificador, y uno inventado habría que guardarlo.
            "id": nombre,
            "nombre": Path(nombre).stem,
            "formato": formato,
            "bytes": estado.st_size,
            "modificado": datetime.fromtimestamp(
                estado.st_mtime, tz=timezone.utc
            ).isoformat(),
        }

    def entrada_de(self, identificador: str) -> dict:
        """La ficha de una canción que existe, o `FileNotFoundError`."""
        ruta = self.ruta_de(identificador)
        if not ruta.is_file():
            raise FileNotFoundError(f"No tengo ninguna canción llamada '{identificador}'.")
        return self._entrada(ruta.name, formato_de(ruta.name), ruta)

    # -- subida -------------------------------------------------------------

    def guardar(self, nombre: str, datos: bytes) -> dict:
        """Guarda `datos` como `nombre` y devuelve su ficha.

        Valida el nombre y el formato ANTES de escribir, y el tamaño también: una
        subida que se va a rechazar no deja nada en la carpeta. Subir dos veces el
        mismo nombre reemplaza el archivo, que es lo que el usuario espera de una
        carpeta y no deja copias con nombres inventados.
        """
        ruta = self.ruta_de(nombre)
        formato = formato_de(ruta.name)
        comprobar_tamano(len(datos))
        if not datos:
            raise ValueError(f"'{ruta.name}' llegó vacío.")
        self._comprobar_colision_de_mayusculas(ruta.name)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(datos)
        return self._entrada(ruta.name, formato, ruta)

    def _comprobar_colision_de_mayusculas(self, nombre: str) -> None:
        """Rechaza `X.TXT` cuando ya hay un `x.txt`, en vez de pisarlo.

        En macOS -y en Windows- el sistema de archivos no distingue mayúsculas, así
        que `X.TXT` y `x.txt` son el MISMO archivo y guardar uno borra el otro sin
        decir nada. Eso es pérdida de datos silenciosa: el usuario ve dos canciones
        en su escritorio, sube las dos y en la biblioteca solo queda la segunda.
        Reemplazar el mismo nombre exacto sí se permite; es lo que el usuario pide
        cuando vuelve a subir una canción corregida.
        """
        if not self.carpeta.is_dir():
            return
        for existente in self.carpeta.iterdir():
            if existente.name.lower() == nombre.lower() and existente.name != nombre:
                raise ValueError(
                    f"Ya tengo una canción llamada '{existente.name}', que en este "
                    f"disco es el mismo archivo que '{nombre}'. Si quieres "
                    f"reemplazarla, súbela con su nombre exacto; si son dos "
                    f"canciones distintas, cámbiale el nombre a una."
                )




async def leer_subida(leer) -> bytes:
    """El cuerpo de una subida, cortando en cuanto pasa del techo.

    `leer` es la lectura por trozos del archivo subido (`UploadFile.read`). Es la
    SEGUNDA red: la primera es `comprobar_tamano(archivo.size)`, que ya sabe el
    tamaño exacto antes de leer nada. Esta queda para cuando no hay tamaño declarado,
    y cuenta mientras lee para no traer a memoria más de un trozo de más.
    """
    trozos: list[bytes] = []
    total = 0
    while True:
        trozo = await leer(TROZO_BYTES)
        if not trozo:
            return b"".join(trozos)
        total += len(trozo)
        comprobar_tamano(total)
        trozos.append(trozo)


def afinacion_de(cuerdas_midi) -> dict:
    """La afinación que pide un juego de cuerdas al aire: clave, nombre y cuerdas.

    `clave` es la del perfil al que hay que afinarse, y es lo que hace ACCIONABLE el
    aviso: con ella la interfaz puede ofrecer el botón que cambia la afinación activa,
    en vez de decir "esto no cuadra" y dejar al alumno buscando. Se busca en dos
    sitios, en este orden:

    1. `clave_de_perfil`, que reconoce las afinaciones DE FÁBRICA. Una canción en
       Drop D tiene que decir `guitarra_drop_d`, no una clave inventada.
    2. El registro vivo `PERFILES`, donde los lectores dan de alta las afinaciones
       raras al leer el archivo. Esto es para qué sirve el registro vivo: la canción
       en Drop C ya tiene clave porque el lector se la puso, y repetirle el cálculo
       aquí -con otros trastes, por ejemplo- habría inventado una clave distinta de
       la que va a traer la pieza.

    Si no aparece en ninguno de los dos, `clave` es None y el nombre se deriva de las
    notas. None es la respuesta honesta: no hay perfil al que afinarse todavía, y
    fabricar uno aquí ensuciaría el registro con afinaciones que nadie ha importado.

    `declarada` dice si el ARCHIVO trae afinación. MIDI y MusicXML sin tablatura no
    la traen (`cuerdas_midi` vacío), y entonces no hay nada a lo que afinarse: la
    pieza se importará en el perfil activo y el carril la aceptará. Quien pregunte
    tiene que poder distinguir "pide otra afinación" de "no pide ninguna", porque si
    no la pantalla acaba diciendo «no cuadra, aféinate a null».

    El ORDEN del archivo no se usa para identificar la afinación: los lectores
    entregan las cuerdas como las trae el archivo, y una afinación es el juego de
    cuerdas, no su orden. Se comparan ordenadas de grave a aguda.
    """
    # Importación local: `nucleo.afinaciones` es barato, pero este módulo lo usa
    # solo aquí y así queda claro que la biblioteca es carpeta, no teoría musical.
    from nucleo.afinaciones import PERFILES, clave_de_perfil, perfil_desde_midis
    from nucleo.musica import midi_de_nombre, nombre_de_midi

    midis = tuple(sorted(cuerdas_midi))
    if not midis:
        return {
            "clave": None,
            "nombre": "El archivo no dice en qué afinación está",
            "cuerdas_midi": [],
            "declarada": False,
        }
    clave = clave_de_perfil(perfil_desde_midis("De la canción", midis))
    if clave is None:
        clave = _clave_en_registro(PERFILES, midis, midi_de_nombre)
    if clave is not None:
        nombre = PERFILES[clave].nombre
    else:
        nombre = "Afinación " + " ".join(nombre_de_midi(midi) for midi in midis)
    return {
        "clave": clave,
        "nombre": nombre,
        "cuerdas_midi": list(midis),
        "declarada": True,
    }


def _clave_en_registro(perfiles: dict, midis: tuple[int, ...], midi_de_nombre) -> str | None:
    """La clave del perfil del registro vivo con estas mismas cuerdas al aire, o None.

    Se compara por nota MIDI y no por frecuencia porque los perfiles que registran
    los lectores salen de notas MIDI: la comparación es exacta por construcción.
    """
    for clave, perfil in perfiles.items():
        suyas = tuple(sorted(midi_de_nombre(cuerda.nota) for cuerda in perfil.cuerdas))
        if suyas == midis:
            return clave
    return None


def comprobar_tamano(medidos: int) -> None:
    """Lanza `ValueError` si `medidos` pasa del techo, con el número de verdad."""
    if medidos > TAMANO_MAXIMO_BYTES:
        raise ValueError(_mensaje_demasiado_grande(medidos))


def _mensaje_demasiado_grande(medidos: int) -> str:
    megas = TAMANO_MAXIMO_BYTES // (1024 * 1024)
    return (
        f"El archivo pasa de {megas} MB ({TAMANO_MAXIMO_BYTES} bytes) y no lo acepto; "
        f"este trae {medidos} bytes. Una partitura de una canción entera ocupa "
        f"muchísimo menos."
    )
