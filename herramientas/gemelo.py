"""El escaparate del gemelo: verse tocar sin tocar.

Esto NO es una herramienta de pruebas, y de ahi salen casi todas sus decisiones.
Es una DEMOSTRACION: levanta el servidor de verdad, le enchufa un guitarrista
sintetico por donde entra el audio de la guitarra, y deja el navegador abierto
sobre la pantalla del carril mientras la pasada corre sola. Quien no tiene el
cable delante -o no puede tocar hoy- puede abrirla, verla correr y opinar sobre
si engancha, que es la unica pregunta que las pruebas no pueden contestar.

Por eso:

* **No termina solo.** Imprime el veredicto cuando la pasada se completa y se
  queda vivo, porque su razon de ser es que alguien MIRE. Con
  `--salir-al-acabar` termina y devuelve el codigo de salida, que es la forma de
  usarlo desde un script.
* **El servidor se levanta de verdad, con `uvicorn`**, y no con un cliente de
  pruebas: la razon de ser del escaparate es que el navegador del usuario se
  conecte a el. `uvicorn` es dependencia de ejecucion, asi que no se añade nada.
* **Los endpoints se llaman con `urllib.request`**, de la biblioteca estandar, y
  no con `httpx`: `httpx` esta solo en el grupo `dev` del `pyproject.toml`, asi
  que un escaparate que lo usara no arrancaria en una instalacion normal. Lo que
  se sigue por HTTP es lo mismo que sigue el navegador -`/api/piezas/estado`-, que
  es ademas la unica forma honesta de saber que la pantalla esta viendo lo que el
  veredicto juzga.
* **Ningun archivo con derechos de autor entra al repositorio.** La pieza por
  omision se construye EN CODIGO (`pieza_de_demostracion`), siempre. `--pieza`
  existe para que el usuario toque la suya desde su disco, y lo que lee es la
  ruta que el usuario da; nada se copia a ninguna parte.

LA PIEZA SE PONE EN MARCHA POR `SesionCarril.iniciar` Y NO POR
`/api/piezas/iniciar`, y no es por comodidad: ese endpoint admite dos formas de
pedir una pieza -un ejercicio del catalogo o una cancion de la biblioteca- y la
pieza de demostracion no es ninguna de las dos. Meterla por ahi obligaria a
escribirla en un archivo y a dejarla en la carpeta de canciones del usuario, o a
abrirle al endpoint una tercera puerta por la que se le pueda pasar una `Pieza`
entera, que es precisamente la puerta que la etapa 3a cerro. Asi que el
escaparate arranca la pasada por la MISMA puerta que el endpoint usa por dentro
-la que aplica la regla de la afinacion- y sigue la pasada por HTTP.
"""

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from nucleo.afinaciones import PERFILES
from nucleo.captura import CapturaAudio
from nucleo.gemelo.dispositivo import (
    NOMBRE_DEL_GEMELO,
    RecolectorDeLaSesion,
    dispositivo_simulado,
    esperar_la_cabecera,
)
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import PERFILES_DE_DESTREZA, PerfilDeDestreza
from nucleo.gemelo.piezas_de_prueba import pieza_de_demostracion
from nucleo.gemelo.veredicto import Veredicto, juzgar
from nucleo.piezas.compases import pulsos_por_compas
from nucleo.piezas.estudio import PlanDePasada
from nucleo.piezas.lectores import importar
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos
from servidor.app import crear_app
from servidor.arranque import PUERTO_POR_DEFECTO, RUTA_INTERFAZ
from servidor.configuracion import Configuracion
from servidor.ejercicios import SesionPractica
from servidor.piezas import SesionCarril
from servidor.sesion import Sesion

# Cada cuanto se le pregunta al servidor por el estado de la pasada.
#
# MAS FINO QUE LOS 30 Hz DEL WEBSOCKET DE PRODUCCION, y esta medido por que. Lo
# que se anota de cada reporte es el reloj del cabezal CUANDO SE LEE, asi que el
# muestreo tiene que ser mas fino que lo que se mide con el: a 30 Hz cada reporte
# llega con hasta 33 ms de retraso prestado por el propio muestreo. Medido sobre la
# pieza de demostracion con `--perfil perfecto`, la misma pasada y el mismo
# veredicto:
#
#     30 Hz  -> +200,0 ms de mediana, 4 perdidas, 4 inventadas, 2 mal adjudicadas
#     120 Hz -> +185,3 ms de mediana, 1 perdida,  1 inventada,  0 mal adjudicadas
#
# Quince milisegundos de la mediana y casi todos los hallazgos eran del muestreo y
# no de la cadena, que es exactamente la clase de numero que no se puede publicar.
# La interfaz dibuja a 30 Hz y eso no cambia: ahi 33 ms no se ven, y aqui se
# publican.
#
# Mas grueso tampoco se puede: el estado publicado tira las notas anotadas al
# cerrar una vuelta, asi que lo que no se lea entre dos cierres no se recupera.
LECTURAS_POR_SEGUNDO = 120.0

# Lo que se sigue leyendo despues de que la pasada se complete.
#
# MEDIDO: la cadena tarda unos 190 ms en publicar un ataque, asi que las ultimas
# notas se publican DESPUES de que el cabezal pase el final del tramo. Sin esta
# cola, el veredicto de la demostracion perderia siempre la ultima nota y acusaria
# a la cadena de algo que hizo bien.
COLA_TRAS_COMPLETAR_S = 1.0

# Lo que se le concede al servidor para empezar a aceptar conexiones.
LIMITE_DE_ARRANQUE_S = 15.0

# Margen sobre la duracion del audio antes de dar la pasada por colgada.
MARGEN_DE_LA_PASADA_S = 10.0


def leer_bucle(texto: str) -> tuple[int, int]:
    """Lee `--bucle` en la forma PRIMERO-ULTIMO. `"17"` es el compas 17 solo.

    Un solo numero no es un error: practicar UN compas es el caso mas comun del
    bucle, y obligar a escribir `17-17` seria pedirle al usuario que repita lo
    obvio.

    Lanza `ValueError` con el texto RECIBIDO dentro del mensaje si no es eso: sin
    el texto, el usuario que escribio `17–20` con un guion largo -el que pone el
    corrector del sistema- lee «no es un tramo» y no ve la diferencia.
    """
    partes = texto.split("-")
    if len(partes) > 2:
        raise ValueError(
            f"El tramo '{texto}' no sirve: se escribe PRIMERO-ULTIMO, "
            "con un solo guion"
        )
    try:
        numeros = [int(parte.strip()) for parte in partes]
    except ValueError:
        raise ValueError(
            f"El tramo '{texto}' no sirve: los compases son numeros, "
            "y se escriben PRIMERO-ULTIMO"
        ) from None
    primero = numeros[0]
    ultimo = numeros[-1]
    if primero < 1:
        raise ValueError(
            f"El tramo '{texto}' no sirve: los compases se cuentan desde 1"
        )
    if ultimo < primero:
        raise ValueError(
            f"El tramo '{texto}' no sirve: el compas {ultimo} va antes del "
            f"{primero}, y un tramo no se puede tocar del revés"
        )
    return primero, ultimo


def perfil_de_destreza(nombre: str) -> PerfilDeDestreza:
    """El perfil de destreza que se pide por nombre, en minusculas.

    Lanza `ValueError` NOMBRANDO LOS VALIDOS: un «perfil desconocido» a secas
    obliga a ir a buscar la lista al codigo, y la lista es de cuatro nombres.
    """
    clave = nombre.strip().lower()
    if clave not in PERFILES_DE_DESTREZA:
        validos = ", ".join(sorted(PERFILES_DE_DESTREZA))
        raise ValueError(
            f"El perfil de destreza '{nombre}' no existe. Opciones: {validos}"
        )
    return PERFILES_DE_DESTREZA[clave]


def pieza_pedida(ruta: str | None, perfil_afinacion: str) -> Pieza:
    """La pieza que se va a tocar: la del disco si se pide, y si no la de codigo.

    **SIN `--pieza` LA PIEZA SE CONSTRUYE EN CODIGO**, nunca se lee de ningun
    archivo: es la regla de los derechos de autor del proyecto, y este es el sitio
    donde se podria romper sin que se notara -una demostracion quiere sonar bien y
    la tentacion de dejar un archivo «de ejemplo» en el repositorio es exactamente
    aqui-.

    Con `--pieza` se lee la primera pista del archivo del usuario con el mismo
    `importar` que usa el servidor. `perfil_afinacion` solo cuenta donde el archivo
    no trae afinacion propia.
    """
    if ruta is None:
        return pieza_de_demostracion()
    return importar(Path(ruta), 1, perfil_afinacion)


def codigo_de_salida(veredicto: Veredicto) -> int:
    """0 si la cadena vio todo lo que paso y nada mas; 1 si no.

    Se decide con `Veredicto.limpio`, que es donde esa regla vive: las exclusiones
    NO lo manchan -son un limite declarado del programa y no un defecto de la
    cadena- y repetir aqui la regla seria tener dos respuestas a la misma pregunta.
    """
    return 0 if veredicto.limpio else 1


def resumen(
    veredicto: Veredicto, pieza: Pieza, perfil: PerfilDeDestreza, completada: bool
) -> str:
    """El informe que se imprime al acabar la pasada.

    DICE "gemelo" SIEMPRE Y EN LA PRIMERA LINEA: nadie puede leer este informe
    creyendo que alguien toco. Es el mismo motivo por el que el dispositivo se
    llama "(gemelo)" y el diagnostico lo publica; un informe de una pasada
    simulada que se lea igual que uno de una pasada real es peor que no tener
    informe.
    """
    lineas = [
        f"Pasada del GEMELO digital (nadie toco): {NOMBRE_DEL_GEMELO}",
        f"  pieza   : {pieza.nombre} ({len(pieza.notas)} notas, {pieza.tempo} ppm)",
        f"  destreza: {perfil.nombre}",
        f"  pasada  : {'completada' if completada else 'SIN COMPLETAR'}",
        f"  tocadas : {veredicto.notas_tocadas} de {veredicto.notas_de_la_pieza}",
        f"  perdidas: {len(veredicto.perdidas)}  inventadas: {veredicto.inventadas}"
        f"  mal adjudicadas: {len(veredicto.mal_adjudicadas)}"
        f"  excluidas: {len(veredicto.excluidas)}",
        f"  desfase : {veredicto.desfase_introducido_ms:+.1f} ms de mediana, "
        f"{veredicto.desfase_maximo_ms:+.1f} ms el peor",
        f"  veredicto: {'LIMPIO' if veredicto.limpio else 'CON HALLAZGOS'}",
    ]
    for vuelta, indice in veredicto.perdidas:
        lineas.append(f"    perdida: vuelta {vuelta}, nota {indice}")
    for vuelta, indice, midi in veredicto.mal_adjudicadas:
        lineas.append(
            f"    mal adjudicada: vuelta {vuelta}, nota {indice}, "
            f"la cadena dijo midi {midi}"
        )
    return "\n".join(lineas)


def segundos_de_cuenta_atras(
    pieza: Pieza, compases_de_aviso: int, factor_tempo: float
) -> float:
    """Lo que dura la cuenta atras del plan, con los ayudantes de PRODUCCION.

    Tiene que salir exactamente igual que `SesionDeEstudio._segundos_de_cuenta_atras`
    y por eso se calcula con los mismos ayudantes: la cuenta atras del plan y los
    `segundos_de_cuenta_atras` del gemelo tienen que ser LA MISMA, que es la
    condicion de uso que `juzgar` declara y que no puede comprobar. Si se separan,
    los dos relojes se separan con ellas y el veredicto acusa a la cadena de la
    diferencia.
    """
    if compases_de_aviso == 0:
        return 0.0
    return (
        pulsos_a_segundos(pulsos_por_compas(pieza) * compases_de_aviso, pieza.tempo)
        / factor_tempo
    )


def _leer_json(url: str, limite_s: float = 5.0) -> dict:
    """Un GET a un endpoint del servidor, con `urllib.request` y nada mas.

    Sin `httpx` a proposito (ver la cabecera del modulo). El `Host` que manda
    `urllib` es `127.0.0.1:<puerto>`, que es uno de los que el guardia del
    servidor admite, y un GET no lleva `Origin`: el escaparate pasa por el mismo
    guardia que el navegador, sin excepciones.
    """
    with urllib.request.urlopen(url, timeout=limite_s) as respuesta:  # noqa: S310
        return json.loads(respuesta.read().decode("utf-8"))


def _esperar_al_servidor(base: str, limite_s: float = LIMITE_DE_ARRANQUE_S) -> bool:
    """Espera a que el servidor conteste de verdad a una peticion de la API.

    No se comprueba que el puerto acepte conexiones, se comprueba que CONTESTA:
    `uvicorn` abre el socket antes de tener la aplicacion lista, y una pasada
    arrancada contra un servidor a medio levantar pierde los primeros cuadros.
    """
    final = time.monotonic() + limite_s
    while time.monotonic() < final:
        try:
            _leer_json(f"{base}/api/diagnostico", limite_s=1.0)
            return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.1)
    return False


def _construir(
    pieza: Pieza, interpretacion: Interpretacion, plan: PlanDePasada
) -> tuple[object, Sesion, SesionCarril, list[CapturaAudio]]:
    """La aplicacion de produccion con el cable del gemelo enchufado.

    Lo UNICO simulado es el cable: `crear_captura` y `listar` son los dos seams
    que `Sesion` ya tenia. La configuracion se construye a mano con el perfil de
    la pieza en vez de leerse del disco porque `SesionCarril.iniciar` rechaza una
    pieza escrita en otra afinacion que la activa, y la demostracion no puede
    depender de la afinacion que el usuario tuviera puesta el martes.
    """
    abrir_stream, listar = dispositivo_simulado(interpretacion)
    capturas: list[CapturaAudio] = []

    def crear_captura(**argumentos) -> CapturaAudio:
        captura = CapturaAudio(abrir_stream=abrir_stream, **argumentos)
        capturas.append(captura)
        return captura

    sesion = Sesion(
        Configuracion(perfil=pieza.perfil),
        crear_captura=crear_captura,
        listar=listar,
    )
    carril = SesionCarril(sesion)
    app = crear_app(
        sesion,
        RUTA_INTERFAZ if RUTA_INTERFAZ.exists() else None,
        SesionPractica(sesion),
        carril,
    )
    return app, sesion, carril, capturas


def _seguir_la_pasada(base: str, duracion_s: float) -> tuple[RecolectorDeLaSesion, bool]:
    """Sigue la pasada por HTTP, recogiendo lo que el servidor publica.

    Exactamente lo que mira el navegador, por el mismo endpoint y al mismo ritmo.
    Devuelve lo recogido y si la pasada llego a completarse.
    """
    recolector = RecolectorDeLaSesion()
    paso = 1.0 / LECTURAS_POR_SEGUNDO
    limite = time.monotonic() + duracion_s + MARGEN_DE_LA_PASADA_S
    completada = False
    while time.monotonic() < limite:
        estado = _leer_json(f"{base}/api/piezas/estado")
        recolector.recoger(estado)
        if estado["completado"]:
            completada = True
            break
        time.sleep(paso)
    final = time.monotonic() + COLA_TRAS_COMPLETAR_S
    while time.monotonic() < final:
        recolector.recoger(_leer_json(f"{base}/api/piezas/estado"))
        time.sleep(paso)
    return recolector, completada


def _analizador_de_argumentos() -> argparse.ArgumentParser:
    analizador = argparse.ArgumentParser(
        prog="python -m herramientas.gemelo",
        description=(
            "Levanta el servidor con un guitarrista sintetico tocando por el "
            "cable, para verse tocar sin tocar. Nadie toca: todo lo que suena lo "
            "toca el gemelo digital."
        ),
    )
    analizador.add_argument(
        "--pieza",
        default=None,
        metavar="RUTA",
        help=(
            "Archivo de la pieza (Guitar Pro, MIDI, MusicXML, texto). Sin esto se "
            "usa la pieza de demostracion, que se construye en codigo."
        ),
    )
    analizador.add_argument(
        "--perfil",
        default="perfecto",
        help=(
            "Destreza del guitarrista sintetico: "
            + ", ".join(sorted(PERFILES_DE_DESTREZA))
        ),
    )
    analizador.add_argument(
        "--tempo", type=float, default=1.0, metavar="FACTOR",
        help="Factor sobre el tempo escrito; 0,5 es tocarla al doble de lento",
    )
    analizador.add_argument(
        "--bucle", default=None, metavar="PRIMERO-ULTIMO",
        help="Tramo de compases a estudiar; un solo numero es ese compas",
    )
    analizador.add_argument(
        "--repeticiones", type=int, default=1, metavar="N",
        help="Vueltas al tramo",
    )
    analizador.add_argument(
        "--cuenta-atras", type=int, default=0, metavar="COMPASES",
        help="Compases de cuenta atras antes de cada vuelta",
    )
    analizador.add_argument("--semilla", type=int, default=0, metavar="N")
    analizador.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO)
    analizador.add_argument(
        "--salir-al-acabar",
        action="store_true",
        help=(
            "Terminar al completarse la pasada y devolver el codigo de salida. "
            "Sin esto el escaparate se queda vivo, que es para lo que existe."
        ),
    )
    return analizador


def armar_la_pasada(
    argumentos: argparse.Namespace,
) -> tuple[Pieza, PerfilDeDestreza, Interpretacion, PlanDePasada]:
    """Lo que se va a tocar y el plan con que se va a estudiar, de una pieza.

    **LOS DOS SE ARMAN AQUI Y JUNTOS, y es lo que hace esta funcion.** `juzgar`
    declara una condicion de uso que no puede comprobar: el tramo, el factor de
    tempo y la cuenta atras del PLAN tienen que ser los mismos que los de la
    INTERPRETACION. Si se separan, los dos relojes se separan con ellos y el
    veredicto le acusa a la cadena de la diferencia sin tener forma de saberlo.
    Armarlos en dos sitios distintos era la manera de que se separaran.

    `en_bucle` se enciende SOLO con varias vueltas: con una, un tramo en bucle no
    se acaba nunca, la pasada no se completa y la demostracion no imprime ningun
    veredicto. `con_click` va siempre a False porque el click abre un dispositivo
    de SALIDA de audio, y el escaparate tiene que poder correr en una maquina sin
    altavoces -o dentro de un script- sin que eso cambie lo que mide.

    Lanza `ValueError` (tramo, perfil o numeros imposibles) u `OSError` (el archivo
    de `--pieza` no se puede leer).
    """
    perfil = perfil_de_destreza(argumentos.perfil)
    primer_compas, ultimo_compas = (
        leer_bucle(argumentos.bucle) if argumentos.bucle else (1, None)
    )
    pieza = pieza_pedida(argumentos.pieza, Configuracion().perfil)
    interpretacion = interpretar(
        pieza,
        perfil,
        factor_tempo=argumentos.tempo,
        primer_compas=primer_compas,
        ultimo_compas=ultimo_compas,
        repeticiones=argumentos.repeticiones,
        segundos_de_cuenta_atras=segundos_de_cuenta_atras(
            pieza, argumentos.cuenta_atras, argumentos.tempo
        ),
        semilla=argumentos.semilla,
    )
    plan = PlanDePasada(
        primer_compas=primer_compas,
        ultimo_compas=ultimo_compas,
        factor_tempo=argumentos.tempo,
        en_bucle=argumentos.repeticiones > 1,
        compases_de_cuenta_atras=argumentos.cuenta_atras,
        con_click=False,
    )
    return pieza, perfil, interpretacion, plan


def main(argv: list[str] | None = None) -> int:
    """Levanta el escaparate. Devuelve el codigo de salida del proceso."""
    argumentos = _analizador_de_argumentos().parse_args(argv)

    try:
        pieza, perfil, interpretacion, plan = armar_la_pasada(argumentos)
    except (ValueError, OSError) as error:
        print(f"No se puede montar la demostracion: {error}")
        return 2

    import uvicorn

    app, sesion, carril, capturas = _construir(pieza, interpretacion, plan)
    base = f"http://127.0.0.1:{argumentos.puerto}"
    servidor = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=argumentos.puerto, log_level="warning"
        )
    )
    hilo = threading.Thread(target=servidor.run, daemon=True)
    hilo.start()
    codigo = 1
    try:
        if not _esperar_al_servidor(base):
            print(
                f"El servidor no contesto en {base} tras "
                f"{LIMITE_DE_ARRANQUE_S:.0f} s. Si el puerto esta ocupado, prueba "
                "con --puerto."
            )
            return 2
        diagnostico = sesion.iniciar()
        print(f"Servidor en {base}")
        print(f"Dispositivo: {diagnostico.mensaje}")
        if diagnostico.estado != "ok":
            print(f"  {diagnostico.accion}")
        print("Abre esa direccion en el navegador para ver la pasada.")

        ventana = PERFILES[pieza.perfil].tamano_ventana(
            interpretacion.frecuencia_muestreo
        )
        if not capturas or not esperar_la_cabecera(
            capturas[0], interpretacion, ventana
        ):
            print("El cable del gemelo no entrego audio: no hay pasada que mirar.")
            return 2
        carril.iniciar(pieza, plan)
        recolector, completada = _seguir_la_pasada(base, interpretacion.duracion_s)
        veredicto = juzgar(interpretacion, recolector.registro)
        print()
        print(resumen(veredicto, pieza, perfil, completada))
        codigo = codigo_de_salida(veredicto) if completada else 1

        if not argumentos.salir_al_acabar:
            print()
            print(
                "La pasada acabo y el escaparate sigue vivo: la pantalla se queda "
                "donde esta para que puedas mirarla. Ctrl+C para salir."
            )
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        print()
    finally:
        carril.detener()
        sesion.detener()
        servidor.should_exit = True
    return codigo


if __name__ == "__main__":
    sys.exit(main())
