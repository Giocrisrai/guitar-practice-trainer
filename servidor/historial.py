"""Guarda en disco las pasadas que `HistorialDeEstudio` anota en memoria.

POR QUÉ AQUÍ Y NO EN EL NÚCLEO
------------------------------

`nucleo/piezas/estudio.py` presumía de no tocar el disco —«ni una sola prueba
que toque el disco»— y esa propiedad vale la pena conservarla. Así que
`HistorialDeEstudio` solo gana una costura (`al_anotar`) y quien sabe de
archivos, de piezas y de relojes es este módulo, que ya vive en `servidor/`
junto a `configuracion.py`.

POR QUÉ UNA COLA Y NO ESCRIBIR AL RECIBIR EL AVISO
--------------------------------------------------

**Porque el aviso llega en el camino que sirve la pantalla.** El cierre de
vuelta ocurre en `estado()` —el conductor lo deja ahí a propósito, y su
comentario explica por qué: hacerlo en `_observar`, que corre en el hilo de
análisis, cegaría la detección de ataques—. Pero `estado()` sirve la instantánea
al navegador **cada 33 ms**: escribir un archivo ahí dentro no cegaría el
detector, daría tirones en la pantalla, que es el mismo defecto en otro sitio.

Así que el aviso solo **encola** y escribe un hilo demonio aparte. Es el patrón
que `SesionCarril._renderizar` ya usa para el audio de fondo, por una razón
idéntica.

Y por eso la cola **no tiene tope**: cada elemento es un registro de unos cientos
de bytes y entran uno por vuelta de bucle, o sea uno cada varios segundos como
mucho. Un tope solo podría descartar pasadas del usuario para ahorrar kilobytes.
"""

import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from nucleo.historial.registro import (
    Historial,
    RegistroDePasada,
    cargar,
    guardar,
    recortar,
)
from nucleo.piezas.estudio import InformeDePasada, PlanDePasada
from nucleo.piezas.modelo import Pieza

_registro = logging.getLogger(__name__)

RUTA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "historial.json"

# Cuánto espera `detener` a que el hilo acabe de escribir lo que tiene encolado.
# Dos segundos son de sobra para un archivo de kilobytes y lo bastante poco para
# que apagar el servidor no se note. Si se agota, lo que se pierde es la última
# pasada, no el historial: la escritura es atómica.
ESPERA_AL_PARAR_S = 2.0


class EscritorDelHistorial:
    """Recibe pasadas cerradas y las guarda en disco, desde su propio hilo.

    Se arranca una vez y se le pide `oyente_de(pieza, plan)` por cada pasada que
    empieza: esa función es lo que se le pone a `HistorialDeEstudio` como
    `al_anotar`. El informe trae los compases; la pieza, el plan y el reloj los
    pone esta clase, porque el núcleo no los lleva en el aviso.
    """

    def __init__(
        self,
        ruta: Path = RUTA_POR_DEFECTO,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self.ruta = ruta
        # El reloj es inyectable por lo de siempre: un instante real no es
        # afirmable, y el registro lleva uno dentro.
        self._reloj = reloj or datetime.now
        self._cola: queue.Queue[RegistroDePasada | None] = queue.Queue()
        self._hilo: threading.Thread | None = None
        self._fallo_anunciado = False

    def arrancar(self) -> None:
        """Pone en marcha el hilo que escribe. Seguro de llamar varias veces."""
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._hilo = threading.Thread(
            target=self._trabajar, name="historial", daemon=True
        )
        self._hilo.start()

    def detener(self) -> None:
        """Pide al hilo que acabe lo encolado y se vaya. Seguro de repetir.

        El `None` de la cola es el centinela: así el hilo escribe lo que ya tenía
        antes de salir, en vez de dejar la última pasada sin guardar.
        """
        hilo = self._hilo
        if hilo is None:
            return
        self._cola.put(None)
        hilo.join(timeout=ESPERA_AL_PARAR_S)
        self._hilo = None

    def oyente_de(
        self, pieza: Pieza, plan: PlanDePasada
    ) -> Callable[[InformeDePasada], None]:
        """La función que se le pasa a `HistorialDeEstudio(al_anotar=...)`.

        Cierra sobre la pieza y el plan de ESTA pasada, que es lo que el aviso del
        núcleo no lleva. Cada `iniciar` pide una nueva, igual que cada `iniciar`
        construye un conductor nuevo.
        """

        def anotar(informe: InformeDePasada) -> None:
            self._cola.put(
                RegistroDePasada.desde_el_informe(
                    instante=self._reloj(), pieza=pieza, plan=plan, informe=informe
                )
            )

        return anotar

    def vaciar(self, plazo_s: float = ESPERA_AL_PARAR_S) -> bool:
        """Espera a que lo encolado esté escrito. La usan las pruebas.

        Devuelve False si se agotó el plazo, que es información y no una
        excepción: quien espera decide si le importa. No se usa `Queue.join()`
        porque no acepta plazo, y una prueba que puede colgarse para siempre es
        peor que una que falla.
        """
        limite = time.monotonic() + plazo_s
        while self._cola.unfinished_tasks and time.monotonic() < limite:
            time.sleep(0.005)
        return self._cola.unfinished_tasks == 0

    def _trabajar(self) -> None:
        """Lee la cola y escribe. Una excepción no mata el hilo.

        Si matara el hilo, el servidor seguiría encolando pasadas que nadie
        escribe y nada chirriaría: la misma forma de fallo que el hilo de análisis
        tiene cubierta con su try/except, y por la misma razón.
        """
        while True:
            pendiente = self._cola.get()
            try:
                if pendiente is None:
                    return
                self._guardar_una(pendiente)
            except Exception as error:  # noqa: BLE001 - se registra y se sigue
                self._anunciar_una_vez(error)
            finally:
                self._cola.task_done()

    def _guardar_una(self, pasada: RegistroDePasada) -> None:
        """Lee el historial, le añade la pasada, lo recorta y lo escribe entero.

        Se vuelve a leer en cada pasada en vez de guardar el historial en memoria,
        y es deliberado: así una edición a mano del archivo entre dos pasadas no
        se pierde, y no hay dos versiones de la verdad. El coste es leer unos
        kilobytes cada varios segundos, en un hilo que no sirve a nadie.
        """
        historial = cargar(self.ruta)
        guardar(recortar(historial.con(pasada), self._reloj()), self.ruta)

    def _anunciar_una_vez(self, error: Exception) -> None:
        """Un fallo de disco se dice UNA vez, no una por vuelta del bucle."""
        if self._fallo_anunciado:
            return
        self._fallo_anunciado = True
        _registro.error(
            "No se pudo guardar el historial en %s: %s: %s. "
            "La pasada sigue; tocar importa mas que anotarlo.",
            self.ruta,
            type(error).__name__,
            error,
        )


def historial_guardado(ruta: Path = RUTA_POR_DEFECTO) -> Historial:
    """Lo que hay en disco, para servirlo. Un archivo que no existe es el primer día."""
    return cargar(ruta)
