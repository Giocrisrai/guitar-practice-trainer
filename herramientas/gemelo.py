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

**UN «CON HALLAZGOS» CON EL GEMELO PERFECTO NO ES UN FALLO DEL PRODUCTO, Y EL
RESUMEN LO DICE.** La sesion completa publica su peor ataque a 236-250 ms de que
sonara, contra los 250 ms que el detector admite para seguir hablando del mismo
ataque: no le queda margen, y de ahi salen una o dos notas sin emparejar en algunas
pasadas. La medida y su causa estan en la Task 11; lo que importa aqui es que el
aviso se imprime junto al veredicto -SOLO con el perfil PERFECTO y solo si el
gemelo toco todo lo escrito, ver `al_borde_del_techo_del_detector`- y que la
tolerancia NO se afloja para que el codigo de salida sea cero: la demostracion dice
lo que mide. Con cualquier otro perfil los hallazgos SI son del interprete, y
excusarlos seria mentir.

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
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple
from pathlib import Path

import numpy as np
from scipy.signal import correlate

from nucleo.acompanamiento import renderizar
from nucleo.afinaciones import PERFILES
from nucleo.captura import CapturaAudio
from nucleo.gemelo.dispositivo import (
    NOMBRE_DEL_GEMELO,
    RecolectorDeLaSesion,
    dispositivo_simulado,
    esperar_la_cabecera,
)
from nucleo.gemelo.interprete import Interpretacion, interpretar
from nucleo.gemelo.perfiles import (
    PERFECTO,
    PERFILES_DE_DESTREZA,
    PerfilDeDestreza,
)
from nucleo.gemelo.piezas_de_prueba import pieza_de_demostracion
from nucleo.gemelo.salida import StreamCapturado
from nucleo.gemelo.veredicto import (
    TOLERANCIA_DE_EMPAREJAMIENTO_MS,
    Veredicto,
    juzgar,
)
from nucleo.piezas.compases import pulsos_por_compas
from nucleo.piezas.estudio import PlanDePasada
from nucleo.piezas.lectores import importar
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos
from nucleo.piezas.voces_de_fondo import FondoDisponible, voces_de
from nucleo.sintesis import FRECUENCIA_MUESTREO_SALIDA, SalidaAudio
from servidor.app import crear_app
from servidor.arranque import PUERTO_POR_DEFECTO, RUTA_INTERFAZ
from servidor.configuracion import Configuracion
from servidor.ejercicios import SesionPractica
from servidor.piezas import SesionCarril, voz_de_tu_parte
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

# Desde que desfase se avisa de que los hallazgos pueden ser el borde del detector.
#
# MEDIDO, y es el suelo de lo observado: la sesion completa publica su peor ataque
# entre 236 y 250 ms, y la cadena directa lo publica a 188. El 230 cae entre los
# dos, asi que un veredicto sucio con el peor desfase por debajo de 230 ms NO lleva
# el aviso: ahi todavia quedan 20 ms de margen contra el techo y lo que haya
# encontrado la cadena es cosa suya. Ver `al_borde_del_techo_del_detector`.
AVISO_DESDE_MS = 230.0


# Cuanto se busca, a cada lado del cabezal, donde sono de verdad un bloque del
# fondo. **ES UN TECHO DURO DE MEDIDA**: un bloque cuyo desfase real pasa de
# aqui no se puede medir. Si su mejor parecido cae fuera de la zona fiable (ver
# `FRACCION_FIABLE_DE_LA_VENTANA`) se cuenta como SATURADO (la cifra real es
# mayor y el informe lo dice); si no se parece a nada se cuenta como SIN
# LOCALIZAR. Nadie puede distinguir un desfase mayor que la ventana de un
# impostor que caiga dentro de ella; medido sobre 600 casos entre 0,51 y 2,00 s
# solo 2 se publicaban (520 -> 479 ms y 530 -> 489 ms), y justo esos los cierra
# la fraccion fiable. La prueba de punta a punta exige ademas cero de las dos
# cuentas.
VENTANA_DE_BUSQUEDA_S = 0.5

# Hasta que parte de la ventana se fia la medida: un mejor parecido a mas del 90 %
# del borde (+-450 ms con la ventana de medio segundo) se cuenta saturado. Coste:
# un desfase real de entre 450 y 500 ms se cuenta saturado en vez de publicarse;
# en esa franja el numero ya no era de fiar.
FRACCION_FIABLE_DE_LA_VENTANA = 0.9

# Entre dos lecturas del cabezal que distan mas que esto no se interpola: es una
# vuelta del bucle (el cabezal salta atras) o una pausa, y la recta entre las dos
# lecturas no es el cabezal.
SALTO_MAXIMO_SIN_INTERPOLAR_S = 0.25

# Lo que tiene que parecerse un bloque escrito a la pieza renderizada para darlo
# por localizado (correlacion normalizada). **Este umbral NO DISCRIMINA
# POSICIONES**: sobre el material real decenas de posiciones lo pasan por
# bloque, y el pico bueno (1,0000) convive con impostores a 0,9998-0,9999 a
# +5/+8/+12/+23 ms, dentro de la misma nota. Solo sirve para descartar lo que
# no se parece a la pieza en ninguna parte (un bloque ajeno); la posicion la da el
# maximo, y la resolucion practica sobre material real es del orden de algunas
# decenas de ms, no de la fraccion de ms que la cifra aparenta.
PARECIDO_MINIMO = 0.9

# Por debajo de esta energia un bloque es silencio y no se puede localizar: el
# silencio esta en todas partes de la pieza.
ENERGIA_MINIMA_DEL_BLOQUE = 1e-9


@dataclass(frozen=True)
class InformeDelFondo:
    """Las cifras del fondo capturado, para el informe.

    muestras_escritas: lo que el CAPTURADOR guardo, no lo que el acompañante dice
        haber escrito.
    desfase_maximo_ms: el peor desfase, con signo, entre donde sono cada bloque
        escrito y donde estaba el CABEZAL cuando se escribio; positivo es que el
        fondo sonaba por delante del cabezal. `None` si no se pudo medir ningun
        bloque.
    bloques_medidos / bloques_sin_localizar / bloques_saturados: cuantos bloques
        con sonido se midieron, cuantos no se parecian a la pieza renderizada y
        cuantos cayeron en el borde de la ventana (desfase real MAYOR que la
        cifra: ver `VENTANA_DE_BUSQUEDA_S`).

    **LA CIFRA NO ES SINCRONIA AUDIBLE: ES CONSISTENCIA INTERNA.** El acompañante
    construye cada bloque preguntandole al cabezal del carril, y la traza lee ESE
    MISMO cabezal por HTTP: un error comun a las dos patas -un fondo desplazado
    respecto a lo que se oye en la sala- es invisible por construccion. Y es la
    misma propiedad que la hace robusta bajo carga: las dos patas se retrasan
    juntas. Medir sincronia de verdad necesita el hardware. Ademas la cifra
    INCLUYE el retraso de lectura HTTP (8-30 ms, la mitad del numero).
    """

    muestras_escritas: int
    desfase_maximo_ms: float | None
    bloques_medidos: int
    bloques_sin_localizar: int
    bloques_saturados: int = 0


class MedidaDelDesfase(NamedTuple):
    """Lo que devuelve `desfase_contra_el_cabezal`: el peor y las tres cuentas."""

    peor_ms: float | None
    medidos: int
    sin_localizar: int
    saturados: int


class StreamCapturadoAlRitmo(StreamCapturado):
    """El stream capturado que tarda lo que tardaria un dispositivo de verdad.

    `StreamCapturado` acepta cada escritura al instante, y un acompañante que
    escribe sin esperar nunca gira a la velocidad de la CPU: en una pasada de
    treinta segundos son cientos de miles de bloques y gigas de memoria. Un
    dispositivo real BLOQUEA la escritura hasta que hay hueco; aqui se imita
    esperando a que el reloj alcance lo ya escrito. Y apunta la hora de cada
    escritura, que es lo que permite compararla luego con el cabezal.

    La espera es sobre un `Event` y no un `time.sleep`: no sincroniza ningun hilo,
    solo hace que el tiempo pase.
    """

    def __init__(
        self,
        frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA,
        reloj: Callable[[], float] = time.monotonic,
        esperar: Callable[[float], object] | None = None,
        **argumentos,
    ) -> None:
        super().__init__(**argumentos)
        self._frecuencia = frecuencia_muestreo
        self._reloj = reloj
        # Por omision, una espera sobre un `Event` que nadie activa.
        self._esperar = esperar or threading.Event().wait
        self._horas: list[float] = []
        self._debido: float | None = None

    @property
    def horas(self) -> tuple[float, ...]:
        """La hora (monotonica) en que entro cada escritura, en orden."""
        with self._candado:
            return tuple(self._horas)

    def write(self, muestras: np.ndarray) -> None:
        ahora = self._reloj()
        if self._debido is None:
            self._debido = ahora
        super().write(muestras)
        with self._candado:
            self._horas.append(ahora)
        self._debido += len(muestras) / self._frecuencia
        espera = self._debido - self._reloj()
        if espera > 0:
            self._esperar(espera)


def _salida_del_fondo(
    altavoces: bool, abrir_stream: Callable | None = None
) -> tuple[SalidaAudio, StreamCapturadoAlRitmo | None]:
    """La salida del fondo: los altavoces de verdad, o un capturador.

    **ESTA ES LA DECISION DE LAS DOS BANDERAS.** `--altavoces` abre la salida real
    (`abrir_stream=None` es el `_abrir_stream_real` de `SalidaAudio`); sin ella se
    captura, porque el escaparate existe para correr sin hardware y el sandbox de
    desarrollo no abre audio. `abrir_stream` solo aplica a los altavoces: es el
    seam para que una prueba compruebe CUAL se eligio sin abrir nada.

    Devuelve la salida y el capturador (None con altavoces: no hay nada que leer).
    """
    if altavoces:
        return SalidaAudio(abrir_stream=abrir_stream), None
    capturador = StreamCapturadoAlRitmo()

    def abrir_capturador(**argumentos) -> StreamCapturadoAlRitmo:
        capturador.argumentos = dict(argumentos)
        return capturador

    return SalidaAudio(abrir_stream=abrir_capturador), capturador


def desfase_contra_el_cabezal(
    bloques: list[np.ndarray],
    horas: list[float],
    referencia: np.ndarray,
    frecuencia_muestreo: int,
    pulsos_por_segundo: float,
    traza: list[tuple[float, float]],
) -> MedidaDelDesfase:
    """El peor desfase entre donde sono cada bloque escrito y donde estaba el cabezal.

    **ESTO ES CONSISTENCIA INTERNA, NO SINCRONIA AUDIBLE.** El acompañante pide
    cada bloque al cabezal del carril y `traza` es ese mismo cabezal leido por
    HTTP: un error comun a las dos patas no se ve. Y la cifra INCLUYE el retraso
    de la lectura HTTP (8-30 ms). Ademas, la resolucion practica sobre material
    real es de algunas decenas de ms (ver `PARECIDO_MINIMO`), y el techo es la
    ventana (`VENTANA_DE_BUSQUEDA_S`): lo que la pasa se cuenta como saturado o
    sin localizar, nunca se publica como dato.

    **Una limitacion que HOY no muerde y mañana si.** Las notas repetidas no se
    confunden entre compases porque `renderizar` deriva la semilla de cada nota
    de su indice: dos notas iguales de compases distintos NO son identicas, y los
    impostores caen dentro de la misma nota. Si algun dia el fondo viniera de
    muestras grabadas, dos notas iguales SI serian identicas y este metodo
    publicaria desfases de compases enteros con total confianza.

    `bloques` y `horas` son lo que CAPTURO la salida; `traza` son las lecturas
    `(hora, instante en pulsos)` del cabezal tal como las publica el servidor; y
    `referencia` es la pieza renderizada, que es lo que permite saber QUE parte
    de la pieza era cada bloque. **Nada de esto se le pregunta al acompañante**:
    el instante que el creyo tocar no entra en la cuenta.

    Cada bloque con sonido se LOCALIZA en la referencia -correlacion normalizada
    en una ventana alrededor de donde el cabezal decia que estaba- y se compara
    con el cabezal a la hora en que se escribio. El cabezal se interpola entre
    las dos lecturas que rodean esa hora (salvo si son de un salto: bucle o
    pausa, donde se toma la anterior).

    Devuelve `MedidaDelDesfase(peor en ms con signo, medidos, sin localizar,
    saturados)`. Positivo: el bloque era de un punto de la pieza POSTERIOR al
    cabezal. Los saturados NO entran en el peor: su cifra seria el borde de la
    ventana presentado como dato.
    """
    if not traza or not len(referencia):
        return MedidaDelDesfase(None, 0, 0, 0)
    tiempos = np.array([hora for hora, _ in traza])
    segundos = np.array([pulsos / pulsos_por_segundo for _, pulsos in traza])
    ventana = int(VENTANA_DE_BUSQUEDA_S * frecuencia_muestreo)
    peor: float | None = None
    medidos = 0
    sin_localizar = 0
    saturados = 0
    fiable = FRACCION_FIABLE_DE_LA_VENTANA * ventana
    for bloque, hora in zip(bloques, horas):
        n = len(bloque)
        if n == 0 or float(np.dot(bloque, bloque)) < ENERGIA_MINIMA_DEL_BLOQUE:
            continue
        # El cabezal a la hora de la escritura.
        despues = int(np.searchsorted(tiempos, hora))
        if despues == 0:
            esperado = segundos[0]
        elif despues == len(tiempos):
            esperado = segundos[-1]
        else:
            antes_s, despues_s = segundos[despues - 1], segundos[despues]
            if abs(despues_s - antes_s) > SALTO_MAXIMO_SIN_INTERPOLAR_S:
                esperado = antes_s
            else:
                t0, t1 = tiempos[despues - 1], tiempos[despues]
                fraccion = 0.0 if t1 == t0 else (hora - t0) / (t1 - t0)
                esperado = antes_s + fraccion * (despues_s - antes_s)
        centro = int(round(esperado * frecuencia_muestreo))
        # La referencia con ceros a los lados: una rodaja fuera de la pieza es
        # silencio, igual que en `PiezaRenderizada.rodaja`.
        desde = centro - ventana
        hasta = centro + ventana + n
        trozo = np.zeros(hasta - desde, dtype=np.float64)
        a, b = max(desde, 0), min(hasta, len(referencia))
        if b > a:
            trozo[a - desde : b - desde] = referencia[a:b]
        cruzada = correlate(trozo, bloque.astype(np.float64), mode="valid", method="fft")
        acumulada = np.concatenate(([0.0], np.cumsum(trozo**2)))
        energia = acumulada[n:] - acumulada[:-n]
        energia_del_bloque = float(np.dot(bloque, bloque))
        # El fondo sale con ganancia <= 1, asi que la parte de la pieza de la que
        # salio el bloque tiene AL MENOS su energia. Donde la ventana tiene menos
        # (los ceros del relleno, los bordes) no puede estar, y dividir por una
        # energia casi nula convierte el ruido numerico de la correlacion en un
        # «parecido» enorme: asi se «localizaron» bloques a medio segundo.
        parecido = np.where(
            energia >= 0.5 * energia_del_bloque,
            cruzada / np.sqrt(np.maximum(energia, 1e-30) * energia_del_bloque),
            -1.0,
        )
        mejor = int(np.argmax(parecido))
        if parecido[mejor] < PARECIDO_MINIMO:
            sin_localizar += 1
            continue
        if abs(mejor - ventana) > fiable:
            saturados += 1
            continue
        encontrado = (desde + mejor) / frecuencia_muestreo
        desfase_ms = (encontrado - esperado) * 1000.0
        medidos += 1
        if peor is None or abs(desfase_ms) > abs(peor):
            peor = desfase_ms
    return MedidaDelDesfase(peor, medidos, sin_localizar, saturados)


def informe_del_fondo(
    capturador: StreamCapturadoAlRitmo,
    referencia: np.ndarray,
    pulsos_por_segundo: float,
    traza: list[tuple[float, float]],
) -> InformeDelFondo:
    """Las dos cifras del informe, de el capturador y del cabezal."""
    muestras = capturador.muestras
    cortes = np.cumsum((0,) + capturador.bloques)
    bloques = [muestras[cortes[i] : cortes[i + 1]] for i in range(len(cortes) - 1)]
    medida = desfase_contra_el_cabezal(
        bloques,
        list(capturador.horas),
        referencia,
        FRECUENCIA_MUESTREO_SALIDA,
        pulsos_por_segundo,
        traza,
    )
    return InformeDelFondo(
        len(muestras),
        medida.peor_ms,
        medida.medidos,
        medida.sin_localizar,
        medida.saturados,
    )


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
            f"{primero}, y un tramo no se puede tocar al reves"
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


def al_borde_del_techo_del_detector(
    veredicto: Veredicto, perfil: PerfilDeDestreza, completada: bool
) -> bool:
    """Si los hallazgos de este veredicto caben en el margen que ya no hay.

    La sesion completa publica su peor ataque entre 236 y 250 ms despues de que
    sonara, contra los `TOLERANCIA_DE_EMPAREJAMIENTO_MS` (250 ms) que el detector
    admite para seguir hablando del mismo ataque: **no le queda margen** (la cadena
    directa tiene 60 ms). Medido en la Task 11, con la causa -el hilo de analisis
    de produccion corre a ~30 ms y no a los 21 nominales- en la cabecera de
    `tests/test_gemelo_sesion_completa.py`.

    Cuando el peor desfase emparejado llega ahi arriba, los hallazgos de una
    interpretacion PERFECTA no son hallazgos del producto: son ese borde. Y hace
    falta decirlo donde el usuario lo lee, porque lo que ve si no es «el programa se
    equivoco de nota».

    **LAS CUATRO CONDICIONES SON NECESARIAS, y tres de ellas se añadieron porque la
    primera version MENTIA.** Solo miraba el veredicto, asi que el aviso salia con
    cualquier perfil: medido con `--perfil caos` sobre 35 notas de 48, imprimia «con
    el gemelo PERFECTO esos hallazgos NO son del producto» y excusaba como «el
    borde» trece notas que el perfil habia dejado de tocar a proposito. Un aviso
    que excusa un fallo de verdad es peor que no tener aviso: es el escaparate
    mintiendo justo donde existe para decir la verdad.

    * `perfil == PERFECTO` -- es lo UNICO que justifica la frase. Se compara contra
      el perfil entero y no contra `perfil.nombre`, porque una variante hecha con
      `replace(PERFECTO, probabilidad_de_fallo=0.5)` conserva el nombre y falla
      notas; desde la linea de ordenes solo llegan los cuatro de fabrica, pero la
      funcion es publica y la condicion tiene que ser la de verdad.
    * `completada` -- una pasada que se corto por la mitad tiene hallazgos que
      pueden venir del corte, y el borde no los explica.
    * `veredicto.toco_la_pieza_entera_una_vez` -- el aviso afirma que lo que
      importa de la pasada es que el gemelo toco todo lo escrito, asi que lo
      COMPARA en vez de creerselo. **Y lo compara con las cuatro cantidades, no
      con dos**: aqui estaba `notas_tocadas == notas_de_la_pieza`, que son
      cantidades de clase distinta -tramo x vueltas contra la pieza entera-, y con
      `--bucle 1-6 --repeticiones 2` sobre la pieza de demostracion la igualdad se
      cumplia por coincidencia aritmetica (24 x 2 = 48 == 48): el aviso salia
      diciendo «el gemelo toco las 48 notas de las 48 escritas» de una pasada que
      toco 24 dos veces, y excusaba como «el borde del detector» las perdidas de la
      frontera de vuelta, que son un mecanismo DECLARADO del bucle con nombre
      propio. Reproducido en pasada real por el revisor. La pregunta vive en
      `Veredicto`, que es donde estan los numeros.
    * los dos de siempre: hay hallazgos y el peor desfase llega a `AVISO_DESDE_MS`.

    NO se afloja la tolerancia para que el veredicto salga limpio: ese borde es un
    hecho medido de la cadena, y taparlo convertiria la demostracion en un juez
    complaciente justo donde el usuario lo va a sentir. Lo que se hace es
    explicarlo, y solo cuando la explicacion es cierta.
    """
    return (
        perfil == PERFECTO
        and completada
        and veredicto.toco_la_pieza_entera_una_vez
        and not veredicto.limpio
        and abs(veredicto.desfase_maximo_ms) >= AVISO_DESDE_MS
    )


def resumen(
    veredicto: Veredicto,
    pieza: Pieza,
    perfil: PerfilDeDestreza,
    completada: bool,
    fondo: InformeDelFondo | None = None,
) -> str:
    """El informe que se imprime al acabar la pasada.

    DICE "gemelo" SIEMPRE Y EN LA PRIMERA LINEA: nadie puede leer este informe
    creyendo que alguien toco. Es el mismo motivo por el que el dispositivo se
    llama "(gemelo)" y el diagnostico lo publica; un informe de una pasada
    simulada que se lea igual que uno de una pasada real es peor que no tener
    informe.

    Y CUANDO LOS HALLAZGOS SON EL BORDE DEL DETECTOR, LO DICE. Ver
    `al_borde_del_techo_del_detector`: un escaparate cuya razon de ser es que
    alguien lo mire y opine, que acaba diciendo «CON HALLAZGOS» cuando no hay
    ningun hallazgo del producto, enseña lo contrario de lo que mide.
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
    if fondo is not None:
        lineas.extend(_lineas_del_fondo(fondo))
    for vuelta, indice in veredicto.perdidas:
        lineas.append(f"    perdida: vuelta {vuelta}, nota {indice}")
    for vuelta, indice, midi in veredicto.mal_adjudicadas:
        lineas.append(
            f"    mal adjudicada: vuelta {vuelta}, nota {indice}, "
            f"la cadena dijo midi {midi}"
        )
    if al_borde_del_techo_del_detector(veredicto, perfil, completada):
        lineas.extend(
            [
                "",
                f"  Aviso: el peor reporte llego {veredicto.desfase_maximo_ms:+.1f} ms"
                f" despues de que la nota sonara, y el techo del detector son"
                f" {TOLERANCIA_DE_EMPAREJAMIENTO_MS:.0f} ms: pasado ese plazo ya no"
                " puede atribuir el reporte a esa nota.",
                "  Con el gemelo PERFECTO esos hallazgos NO son del producto: son ese"
                " borde. La sesion completa publica sus ataques 18-44 ms mas tarde"
                " que la cadena directa porque el hilo de analisis corre a ~30 ms y"
                " no a los 21 nominales (medido en la Task 11), y con eso se queda"
                " sin margen.",
                "  Lo que importa de esta pasada es que el gemelo toco las"
                f" {veredicto.notas_tocadas} notas de las"
                f" {veredicto.notas_de_la_pieza} escritas y la pasada se completo."
                " No se ha aflojado ninguna tolerancia para que saliera limpia.",
            ]
        )
    return "\n".join(lineas)


def _lineas_del_fondo(fondo: InformeDelFondo) -> list[str]:
    """Las lineas del fondo: muestras escritas y desfase maximo, con su salvedad.

    La salvedad se escribe DONDE SE LEE LA CIFRA: es consistencia interna y no
    sincronia audible, e incluye el retraso HTTP de la lectura.
    """
    if fondo.desfase_maximo_ms is None:
        desfase = "sin medir (ningun bloque con sonido se pudo comparar con el cabezal)"
    else:
        desfase = (
            f"{fondo.desfase_maximo_ms:+.1f} ms el peor contra el cabezal "
            f"({fondo.bloques_medidos} bloques medidos)"
        )
    lineas = [
        f"  fondo   : {fondo.muestras_escritas} muestras escritas (capturadas, "
        "no por los altavoces)",
        f"  fondo   : desfase {desfase}",
        "            (consistencia interna: compara lo escrito con el MISMO "
        "cabezal que lo pidio, NO es sincronia audible; incluye 8-30 ms de "
        "retraso de lectura HTTP)",
    ]
    if fondo.bloques_saturados or fondo.bloques_sin_localizar:
        lineas.append(
            f"  fondo   : ATENCION, la cifra puede ser MENOR que el desfase real: "
            f"{fondo.bloques_saturados} bloques saturados (desfase fuera de "
            f"+-{VENTANA_DE_BUSQUEDA_S * 1000:.0f} ms) y "
            f"{fondo.bloques_sin_localizar} sin localizar"
        )
    return lineas


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
    pieza: Pieza,
    interpretacion: Interpretacion,
    salida_fondo: SalidaAudio | None = None,
) -> tuple[object, Sesion, SesionCarril, list[CapturaAudio]]:
    """La aplicacion de produccion con el cable del gemelo enchufado.

    Lo UNICO simulado es el cable: `crear_captura` y `listar` son los dos seams
    que `Sesion` ya tenia. La configuracion se construye a mano con el perfil de
    la pieza en vez de leerse del disco porque `SesionCarril.iniciar` rechaza una
    pieza escrita en otra afinacion que la activa, y la demostracion no puede
    depender de la afinacion que el usuario tuviera puesta el martes.

    NO recibe el plan, y antes si: lo pedia en la firma y no lo mencionaba en el
    cuerpo. El plan se aplica despues, en `carril.iniciar(pieza, plan)`, y un
    parametro muerto en la funcion que «monta la app con el cable enchufado» hace
    pensar que el plan entra ahi.
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
    # Sin `salida_fondo` el carril crea la suya, que es la real: solo se pasa una
    # cuando se pidio el fondo (ver `_salida_del_fondo`).
    carril = SesionCarril(sesion, salida_fondo=salida_fondo)
    app = crear_app(
        sesion,
        RUTA_INTERFAZ if RUTA_INTERFAZ.exists() else None,
        SesionPractica(sesion),
        carril,
    )
    return app, sesion, carril, capturas


def _leer_estado(base: str, traza: list[tuple[float, float]] | None) -> dict:
    """Lee el estado publicado y, si hay traza, apunta donde estaba el cabezal."""
    antes = time.monotonic()
    estado = _leer_json(f"{base}/api/piezas/estado")
    if traza is not None:
        traza.append(((antes + time.monotonic()) / 2, float(estado["instante_pulsos"])))
    return estado


def _seguir_la_pasada(
    base: str,
    duracion_s: float,
    repeticiones: int = 1,
    traza: list[tuple[float, float]] | None = None,
) -> tuple[RecolectorDeLaSesion, bool]:
    """Sigue la pasada por HTTP, recogiendo lo que el servidor publica.

    Exactamente lo que mira el navegador, por el mismo endpoint y al mismo ritmo.
    Devuelve lo recogido y si la pasada llego a completarse.

    **UN BUCLE NO PUBLICA `completado` NUNCA, y de ahi venia el segundo defecto que
    la Task 16 midio.** `armar_la_pasada` enciende `en_bucle` en cuanto se piden
    varias vueltas, y un tramo en bucle da la vuelta y sigue: `completado` no llega,
    la espera se agotaba contra `MARGEN_DE_LA_PASADA_S` y el resumen decia «SIN
    COMPLETAR» con codigo 1 aunque todo hubiera ido bien (medido:
    `--bucle 2-3 --repeticiones 2` tardaba 23 s y sacaba 16 notas de 48).

    Asi que con varias vueltas la pasada se da por acabada cuando el carril PASA de
    la ultima vuelta pedida -`repeticion > repeticiones`-, que es el unico instante
    en que se sabe que el bucle ya recorrio todo lo que el gemelo toco. Con una sola
    vuelta manda `completado`, como siempre: en una pasada derecha la vuelta no
    cambia nunca, asi que la cuenta de vueltas sola no serviria.

    Lo que el bucle se deja por el camino y esto NO arregla: la ultima nota de la
    ultima vuelta puede quedarse sin emparejar, porque la cadena tarda ~190 ms en
    publicar un ataque y al dar la vuelta el seguidor olvida el tramo
    (`olvidar_tramo`). Es la propiedad del bucle que `nucleo/gemelo/veredicto.py` y
    `tests/test_gemelo_bucle.py` ya declaran, no algo que el escaparate pueda
    arreglar desde fuera.

    `traza`, si se da, recibe `(hora, instante en pulsos)` de cada lectura: es el
    cabezal tal como lo publica el servidor, y lo que el informe del fondo compara
    contra lo que se escribio. La hora es la del PUNTO MEDIO de la peticion.
    """
    recolector = RecolectorDeLaSesion()
    paso = 1.0 / LECTURAS_POR_SEGUNDO
    limite = time.monotonic() + duracion_s + MARGEN_DE_LA_PASADA_S
    completada = False
    while time.monotonic() < limite:
        estado = _leer_estado(base, traza)
        recolector.recoger(estado)
        if estado["completado"] or int(estado["repeticion"]) > repeticiones:
            completada = True
            break
        time.sleep(paso)
    final = time.monotonic() + COLA_TRAS_COMPLETAR_S
    while time.monotonic() < final:
        recolector.recoger(_leer_estado(base, traza))
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
    analizador.add_argument(
        "--semilla", type=int, default=0, metavar="N",
        help="Semilla del sorteo del interprete; entero no negativo",
    )
    analizador.add_argument(
        "--puerto", type=int, default=PUERTO_POR_DEFECTO, metavar="PUERTO",
        help="Puerto del servidor del escaparate, entre 1 y 65535",
    )
    analizador.add_argument(
        "--con-acompanamiento",
        action="store_true",
        help=(
            "Hace sonar la pieza de fondo CAPTURANDOLA, sin abrir altavoces: para "
            "correr sin hardware. El informe dice las muestras escritas y el "
            "desfase maximo contra el cabezal. No se puede juntar con --altavoces"
        ),
    )
    analizador.add_argument(
        "--altavoces",
        action="store_true",
        help=(
            "Hace sonar la pieza de fondo por los altavoces de verdad, para "
            "OIRLA. No se puede juntar con --con-acompanamiento"
        ),
    )
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

    **LOS DOS NUMEROS QUE SE COMPRUEBAN AQUI Y NO LOS COMPRUEBA NADIE MAS.** El
    resto -tempo, repeticiones, cuenta atras, tramo- los rechazan el plan, el
    interprete o `leer_bucle`, cada uno nombrando su campo. Estos dos no tenian
    quien los rechazara:

    * `--semilla` negativa llegaba hasta `numpy.random.default_rng`, que la
      rechaza con «expected non-negative integer»: un mensaje crudo, en ingles y
      sin nombrar la opcion, de modo que quien tiene seis numeros en su linea de
      ordenes no sabe cual es el malo.
    * `--puerto` fuera de rango no lo rechazaba nadie: `uvicorn` fallaba dentro
      del hilo demonio, `_esperar_al_servidor` agotaba sus 15 s y el escaparate
      acababa aconsejando «prueba con --puerto», que es lo que el usuario acababa
      de hacer. Comprobarlo aqui ahorra los 15 s y el consejo circular.

    El mensaje trae la opcion y el valor RECIBIDO, que es lo que hace el resto del
    modulo (ver `leer_bucle` y `perfil_de_destreza`).
    """
    # **LO PRIMERO, ANTES DE LEER NADA NI LEVANTAR NADA**: dos opciones que se
    # contradicen se rechazan al armar la pasada, no despues de quince segundos de
    # servidor (la leccion de la etapa anterior).
    if argumentos.con_acompanamiento and argumentos.altavoces:
        raise ValueError(
            "`--con-acompanamiento` y `--altavoces` no se pueden pedir a la vez: "
            "la primera captura el fondo sin abrir altavoces y la segunda los abre "
            "de verdad. Elige una"
        )
    if argumentos.semilla < 0:
        raise ValueError(
            f"La semilla {argumentos.semilla} no sirve: `--semilla` tiene que ser "
            "un entero no negativo (0 es la de por omision)"
        )
    if not 1 <= argumentos.puerto <= 65535:
        raise ValueError(
            f"El puerto {argumentos.puerto} no sirve: `--puerto` tiene que estar "
            "entre 1 y 65535"
        )
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


def fondo_pedido(argumentos: argparse.Namespace, pieza: Pieza) -> FondoDisponible | None:
    """El fondo que se pidio, o None si no se pidio ninguno.

    Con `--pieza` salen las voces AJENAS del archivo (la pista 1 es la que toca el
    gemelo, igual que la que lee `pieza_pedida`). Sin ella la pieza de
    demostracion no tiene otras pistas: el fondo es su propia parte, que suena
    como guia (`FondoDisponible` sin voces).

    Lanza `ValueError` u `OSError` si el archivo no se puede leer para el fondo.
    """
    if not (argumentos.con_acompanamiento or argumentos.altavoces):
        return None
    if argumentos.pieza is None:
        return FondoDisponible((), pieza.tempo, ())
    return voces_de(Path(argumentos.pieza), 1)


def _quedarse_vivo() -> None:
    """Se queda esperando a que el usuario mire. Solo sale con Ctrl+C.

    **Es la razon de ser del escaparate** y por eso es una funcion y no tres lineas
    dentro de `main`: asi se puede sustituir en una prueba y afirmar que se la llama
    sin `--salir-al-acabar` y no se la llama con el. Estando dentro de `main`,
    cambiar la condicion por `if False:` -o sea, cerrar el escaparate en cuanto
    acaba la pasada, que es lo contrario de lo que existe para hacer- pasaba la
    suite entera.
    """
    print()
    print(
        "La pasada acabo y el escaparate sigue vivo: la pantalla se queda donde "
        "esta para que puedas mirarla. Ctrl+C para salir."
    )
    while True:
        time.sleep(0.5)


def _levantar_el_servidor(app, puerto: int):
    """Arranca `uvicorn` en un hilo demonio y devuelve el servidor para apagarlo.

    Esta aparte por una razon y es poder probar el ORDEN: lo que una prueba tiene
    que poder mirar es si el servidor estaba apagado cuando el escaparate le dijo al
    usuario que mirara, y eso se mira en `should_exit` de un doble de tres lineas,
    sin abrir ningun puerto. Ver
    `test_el_servidor_sigue_contestando_mientras_el_usuario_mira`.
    """
    import uvicorn

    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="warning")
    )
    threading.Thread(target=servidor.run, daemon=True).start()
    return servidor


def _decir_el_fondo(carril, altavoces: bool) -> None:
    """Dice por donde sale el fondo y avisa si cargarlo NO lo dejo posible.

    Se lee del estado publicado y no se da por hecho: el fondo solo suena con el
    cable como entrada, y si el dispositivo del gemelo dejara de contar como
    cable el escaparate correria «con fondo» sin que sonara nada.
    """
    estado = carril.estado()
    destino = "por los altavoces" if altavoces else "capturado (sin altavoces)"
    print(f"Fondo {destino}: {estado['acompanamiento_voces']} voces ajenas")
    if not estado["acompanamiento_posible"]:
        print(
            "  AVISO: el fondo NO puede sonar: la entrada no es el cable "
            "Rocksmith, y con otra el fondo entraria por ella."
        )


def _informe_del_capturador(
    capturador: StreamCapturadoAlRitmo,
    pieza: Pieza,
    fondo: FondoDisponible,
    plan: PlanDePasada,
    traza: list[tuple[float, float]],
) -> InformeDelFondo:
    """Renderiza la referencia aparte y mide lo capturado contra el cabezal."""
    voces = fondo.voces or (voz_de_tu_parte(pieza),)
    referencia = renderizar(
        voces,
        tempo=pieza.tempo,
        factor_tempo=plan.factor_tempo,
        frecuencia_muestreo=FRECUENCIA_MUESTREO_SALIDA,
    )
    return informe_del_fondo(
        capturador, referencia.muestras, referencia.pulsos_por_segundo, traza
    )


def _correr_la_demostracion(
    pieza: Pieza,
    interpretacion: Interpretacion,
    plan: PlanDePasada,
    puerto: int,
    al_acabar: Callable[..., None],
    fondo: FondoDisponible | None = None,
    altavoces: bool = False,
    abrir_stream: Callable | None = None,
) -> tuple[Veredicto, bool] | None:
    """Levanta el servidor, mete el audio por el cable y devuelve lo que salio.

    Devuelve `(veredicto, completada)`, o `None` cuando la demostracion no se pudo
    montar -el servidor no contesta, el cable no entrega audio, o el usuario la
    interrumpio antes de que hubiera veredicto-, que es otra cosa que un veredicto
    sucio y `main` lo traduce a otro codigo de salida. Un `Ctrl+C` DESPUES del
    veredicto devuelve el veredicto: ver el `except KeyboardInterrupt`.

    **`al_acabar` SE LLAMA DENTRO DEL `try`, CON EL SERVIDOR TODAVIA EN PIE, y ese
    es el contrato entero de este parametro.** Sin el, el defecto que la Task 16
    midio: el `finally` de aqui apagaba uvicorn y solo DESPUES `main` llamaba a
    `_quedarse_vivo()`, asi que el escaparate imprimia «la pantalla se queda donde
    esta para que puedas mirarla» sobre una direccion que ya daba «Connection
    refused». Medido con un sondeo cada medio segundo: contestaba desde el segundo 0
    y dejaba de contestar a los 27,7 s, el instante del veredicto. El usuario abria
    el navegador justo cuando el resumen aparecia -que es lo natural- y no
    encontraba nada.

    Asi que todo lo que el usuario tiene que leer y mirar -el resumen y la espera-
    se lo pasa quien llama en esta funcion, y se hace antes de apagar nada. Con
    `--salir-al-acabar`, `al_acabar` imprime y vuelve en seguida, y el `finally`
    apaga el servidor igual de limpio que antes.

    **CON `fondo`, EL ORDEN ES `iniciar` Y DESPUES `cargar_acompanamiento`**: al
    reves el fondo se pierde en silencio (`iniciar` detiene lo anterior y soltar
    la pieza suelta el fondo). Cargar enciende solo si la entrada es el cable
    -decision M6-, y el dispositivo del gemelo se llama Rocksmith, asi que cuenta;
    se comprueba en el estado publicado y se dice si no. `altavoces` y
    `abrir_stream` son la decision de `_salida_del_fondo`. `al_acabar` recibe el
    `InformeDelFondo` como tercer argumento (None sin fondo o con altavoces).

    Esta aparte de `main` para que las decisiones de `main` -el codigo de salida y
    el quedarse vivo- se puedan probar sin levantar `uvicorn`, sin abrir un puerto
    y sin pagar los 31 s de la pieza de demostracion.
    """
    salida_fondo, capturador = (
        _salida_del_fondo(altavoces, abrir_stream) if fondo is not None else (None, None)
    )
    app, sesion, carril, capturas = (
        _construir(pieza, interpretacion)
        if fondo is None
        else _construir(pieza, interpretacion, salida_fondo=salida_fondo)
    )
    traza: list[tuple[float, float]] = []
    base = f"http://127.0.0.1:{puerto}"
    servidor = _levantar_el_servidor(app, puerto)
    # Lo que haya que devolver, puesto en cuanto existe: el `Ctrl+C` con que el
    # usuario cierra el escaparate llega DESPUES del veredicto y no es «la
    # demostracion no se pudo montar». Ver el `except`.
    firmado: tuple[Veredicto, bool] | None = None
    try:
        if not _esperar_al_servidor(base):
            print(
                f"El servidor no contesto en {base} tras "
                f"{LIMITE_DE_ARRANQUE_S:.0f} s. Si el puerto esta ocupado, prueba "
                "con --puerto."
            )
            return None
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
            return None
        carril.iniciar(pieza, plan)
        if fondo is not None:
            carril.cargar_acompanamiento(fondo)
            _decir_el_fondo(carril, altavoces)
        recolector, completada = _seguir_la_pasada(
            base, interpretacion.duracion_s, interpretacion.repeticiones, traza=traza
        )
        veredicto = juzgar(interpretacion, recolector.registro)
        firmado = (veredicto, completada)
        informe = (
            _informe_del_capturador(capturador, pieza, fondo, plan, traza)
            if capturador is not None
            else None
        )
        # **Una salida que no abrio se dice, con altavoces o sin ellos**:
        # `acompanamiento_posible` solo mira la entrada, y un dispositivo que no
        # abre deja la pasada en pie y muda sin una linea que lo explique. El
        # error queda en la salida (`abrir` lo guarda y no reintenta).
        if salida_fondo is not None and salida_fondo.ultimo_error is not None:
            print(
                "  AVISO: la salida del fondo NO abrio, asi que no sono nada: "
                f"{salida_fondo.ultimo_error}"
            )
        # DENTRO del try, con el servidor todavia contestando: ver el docstring.
        al_acabar(veredicto, completada, informe)
        return firmado
    except KeyboardInterrupt:
        print()
        # **EL `Ctrl+C` DEL CAMINO POR OMISION ENTRA AQUI, Y NO ES UN FALLO.**
        # Sin `--salir-al-acabar`, `al_acabar` llama a `_quedarse_vivo()`, que no
        # vuelve nunca: sale con el `Ctrl+C` del usuario, que es como se cierra el
        # escaparate. Y `al_acabar` corre dentro de este `try` a proposito (ver
        # arriba), asi que esa interrupcion llega hasta aqui con el veredicto ya
        # firmado e impreso. Devolver `None` ahi hacia que `main` tradujera a 2
        # -«la demostracion no llego a montarse»- una pasada completada con su
        # veredicto en pantalla: medido en una pasada real, y era el camino por
        # omision, el documentado en el README.
        #
        # Con `firmado` todavia en `None` si significa eso, y se devuelve: una
        # interrupcion antes del veredicto es una demostracion que no llego a
        # darse.
        return firmado
    finally:
        carril.detener()
        sesion.detener()
        servidor.should_exit = True


def main(argv: list[str] | None = None) -> int:
    """Levanta el escaparate. Devuelve el codigo de salida del proceso.

    Tres codigos y se distinguen a proposito: 0 si el veredicto sale limpio, 1 si
    la cadena tiene hallazgos (o la pasada no se completo), y 2 si la demostracion
    no llego a montarse. Un script tiene que poder diferenciar «la cadena tiene
    hallazgos» de «esto no corrio».

    **Y LOS TRES VALEN CON Y SIN `--salir-al-acabar`.** Sin la bandera el codigo
    era siempre 2: el `Ctrl+C` con que se cierra el escaparate subia por el
    `except KeyboardInterrupt` de `_correr_la_demostracion` y tiraba el veredicto
    que ya estaba impreso en pantalla. Medido en pasada real. Era el camino por
    omision y el que el README documenta, asi que de los tres codigos quedaban
    dos y el tercero mentia.
    """
    argumentos = _analizador_de_argumentos().parse_args(argv)

    try:
        pieza, perfil, interpretacion, plan = armar_la_pasada(argumentos)
        fondo = fondo_pedido(argumentos, pieza)
    except (ValueError, OSError) as error:
        print(f"No se puede montar la demostracion: {error}")
        return 2

    def al_acabar(
        veredicto: Veredicto,
        completada: bool,
        informe_del_fondo: InformeDelFondo | None = None,
    ) -> None:
        """Lo que el usuario lee y mira, CON EL SERVIDOR TODAVIA EN PIE.

        Se le pasa a `_correr_la_demostracion` para que corra dentro de su `try`:
        imprimir el resumen y quedarse esperando despues de que el `finally`
        hubiera apagado uvicorn dejaba al usuario mirando una direccion que ya no
        contestaba. Ver el docstring de `_correr_la_demostracion`.
        """
        print()
        print(resumen(veredicto, pieza, perfil, completada, informe_del_fondo))
        if not argumentos.salir_al_acabar:
            _quedarse_vivo()

    resultado = _correr_la_demostracion(
        pieza,
        interpretacion,
        plan,
        argumentos.puerto,
        al_acabar,
        fondo=fondo,
        altavoces=argumentos.altavoces,
    )
    if resultado is None:
        return 2
    veredicto, completada = resultado

    # Una pasada que no se completo devuelve distinto de cero aunque el veredicto
    # salga limpio: un veredicto sobre media pasada no dice nada de la cadena.
    return codigo_de_salida(veredicto) if completada else 1


if __name__ == "__main__":
    sys.exit(main())
