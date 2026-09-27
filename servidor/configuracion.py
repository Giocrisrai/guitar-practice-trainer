"""Configuración persistente y calibración del umbral de ruido."""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS
from nucleo.analisis.registro import nombres_disponibles

RUTA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "config_local.json"

# Margen sobre el piso de ruido medido. 14 dB es lo que separa el ruido medido en el
# equipo real (-74,4 dBFS) del umbral elegido (-60 dBFS).
MARGEN_CALIBRACION_DB = 14.0

# Rango admisible del umbral de la compuerta. 0 dBFS es la saturación digital (un
# umbral ahí dejaría fuera toda señal posible) y -120 dBFS está por debajo del
# piso de ruido de cualquier convertidor real, así que fuera de este intervalo el
# valor no puede ser deliberado.
UMBRAL_MINIMO_DBFS = -120.0
UMBRAL_MAXIMO_DBFS = 0.0


@dataclass
class Configuracion:
    """Ajustes que el usuario elige y que sobreviven entre sesiones."""

    # NOMBRE del dispositivo de entrada, no su indice: macOS renumera las
    # entradas cada vez que se enchufa o desenchufa algo, asi que un numero
    # guardado deja de significar lo mismo entre una sesion y la siguiente. None
    # es "automatico": se busca el cable por nombre, que es lo que el usuario
    # quiere casi siempre.
    dispositivo: str | None = None
    perfil: str = "guitarra_estandar"
    ganancia: float = 1.0
    umbral_ruido_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS
    referencia_a4: float = 440.0
    confianza_minima: float = 0.75
    detector: str = "yin"

    def validar(self) -> None:
        """Lanza ValueError con un mensaje en español si algo no cuadra."""
        if self.dispositivo is not None and not isinstance(self.dispositivo, str):
            raise ValueError("El dispositivo se identifica por su nombre, no por su indice")
        if self.perfil not in PERFILES:
            disponibles = ", ".join(sorted(PERFILES))
            raise ValueError(f"El perfil '{self.perfil}' no existe. Opciones: {disponibles}")
        if self.ganancia <= 0.0:
            raise ValueError("La ganancia debe ser mayor que cero")
        if not 380.0 <= self.referencia_a4 <= 500.0:
            raise ValueError("La referencia A4 debe estar entre 380 y 500 Hz")
        if not 0.0 <= self.confianza_minima <= 1.0:
            raise ValueError("La confianza mínima debe estar entre 0 y 1")
        detectores = nombres_disponibles()
        if self.detector not in detectores:
            opciones = ", ".join(detectores) or "ninguno"
            raise ValueError(
                f"El detector '{self.detector}' no existe. Opciones: {opciones}"
            )
        if not UMBRAL_MINIMO_DBFS <= self.umbral_ruido_dbfs <= UMBRAL_MAXIMO_DBFS:
            raise ValueError(
                "El umbral de ruido debe estar entre "
                f"{UMBRAL_MINIMO_DBFS:.0f} y {UMBRAL_MAXIMO_DBFS:.0f} dBFS"
            )

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> "Configuracion":
        """Construye desde un diccionario, ignorando campos desconocidos.

        `dispositivo` fue un indice hasta que se vio que no sobrevive a
        reconectar el USB. Un numero guardado de antes se descarta y se queda en
        automatico: reinterpretarlo como nombre seria absurdo, y conservarlo como
        indice es justamente lo que dejaba al usuario sin afinador con el cable
        enchufado delante.
        """
        conocidos = {campo.name for campo in fields(cls)}
        limpios = {clave: valor for clave, valor in datos.items() if clave in conocidos}
        if isinstance(limpios.get("dispositivo"), (int, bool)):
            limpios["dispositivo"] = None
        return cls(**limpios)


def cargar(ruta: Path = RUTA_POR_DEFECTO) -> Configuracion:
    """Lee la configuración del disco.

    Ante un archivo ausente, corrupto o con valores inválidos devuelve los valores
    por defecto en lugar de fallar: arrancar con valores razonables es mejor que
    no arrancar. Lo leído se valida, porque un `config_local.json` editado a mano
    con un perfil o un detector inexistente reventaría después, mucho más lejos de
    aquí y con un traceback en vez de un afinador.
    """
    try:
        configuracion = Configuracion.desde_dict(
            json.loads(ruta.read_text(encoding="utf-8"))
        )
        configuracion.validar()
        return configuracion
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return Configuracion()


def guardar(configuracion: Configuracion, ruta: Path = RUTA_POR_DEFECTO) -> None:
    """Escribe la configuración, validándola antes.

    La escritura es atómica: primero a un archivo temporal en el mismo directorio
    y después `os.replace`, que en un mismo sistema de archivos sustituye de golpe.
    Escribir directamente sobre el destino lo truncaría antes de escribir, y una
    interrupción a mitad dejaría al usuario sin sus ajustes.
    """
    configuracion.validar()
    contenido = json.dumps(configuracion.a_dict(), indent=2, ensure_ascii=False)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(contenido, encoding="utf-8")
    os.replace(temporal, ruta)


def calibrar_umbral(
    niveles_dbfs: list[float], margen_db: float = MARGEN_CALIBRACION_DB
) -> float:
    """Umbral de la compuerta a partir de niveles medidos en silencio.

        umbral = mediana(niveles) + margen

    Se usa la mediana y no la media porque un golpe accidental durante la
    calibración es un valor atípico que hay que descartar, no promediar.
    """
    if not niveles_dbfs:
        return UMBRAL_RUIDO_POR_DEFECTO_DBFS
    return float(np.median(niveles_dbfs)) + margen_db
