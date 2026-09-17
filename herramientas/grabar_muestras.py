"""Graba las seis cuerdas al aire para usarlas como pruebas permanentes.

Uso:  .venv/bin/python -m herramientas.grabar_muestras
"""

import sys
import time
from pathlib import Path

import numpy as np
import soundfile

from nucleo.afinaciones import PERFILES
from nucleo.captura import CapturaAudio, buscar_rocksmith

DESTINO = Path(__file__).resolve().parent.parent / "tests" / "audio"
SEGUNDOS = 3.0
FS = 48000


def main() -> int:
    cable = buscar_rocksmith()
    if cable is None:
        print("El cable Rocksmith no aparece. Conéctalo y reintenta.")
        return 1

    DESTINO.mkdir(parents=True, exist_ok=True)
    perfil = PERFILES["guitarra_estandar"]
    captura = CapturaAudio(
        indice_dispositivo=cable.indice, capacidad_buffer=int(FS * (SEGUNDOS + 1))
    )
    if not captura.iniciar():
        print(f"No se pudo abrir el dispositivo: {captura.ultimo_error}")
        return 1

    for cuerda in perfil.cuerdas:
        nombre = f"cuerda_{cuerda.numero}_{cuerda.nota.lower()}.wav"
        input(f"\nCuerda {cuerda.numero} ({cuerda.nota}) al aire. Enter y púlsala...")
        inicio = captura.total_capturado
        while captura.total_capturado - inicio < FS * SEGUNDOS:
            time.sleep(0.05)
        muestras = captura.leer_ventana(int(FS * SEGUNDOS))
        soundfile.write(DESTINO / nombre, muestras.astype(np.float32), FS)
        print(f"  guardado {nombre}")

    captura.detener()
    print(f"\nGrabaciones en {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
