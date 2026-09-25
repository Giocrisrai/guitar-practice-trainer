"""Calibra el detector de ataques con la guitarra real.

Los valores por defecto se eligieron a ojo y solo se han probado con envolventes
sinteticas, que son demasiado limpias: una pulsacion real trae ruido de pua,
decaimiento irregular y resonancia de las cuerdas vecinas.

Uso:  uv run python -m herramientas.calibrar_ataques
"""

import math
import sys
import time

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import nivel_dbfs
from nucleo.captura import CapturaAudio, buscar_rocksmith
from nucleo.ejercicios.ataques import MUESTRAS_REFERENCIA, DetectorAtaques
from servidor.sesion import INTERVALO_ANALISIS

FS = 48000
PULSACIONES_PEDIDAS = 8
SEGUNDOS = 12.0
# El mismo paso con el que el servidor analiza en vivo: calibrar con otro
# paso daria numeros que no sirven en produccion.
PASO_ANALISIS = INTERVALO_ANALISIS

SALTOS = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]
REFRACTARIOS = [0.030, 0.050, 0.080, 0.120, 0.200]

MENSAJE_NO_INTERACTIVO = (
    "Este script es interactivo: pide pulsar Enter antes de grabar.\n"
    "No se puede ejecutar desde un canal sin terminal (por ejemplo, una tuberia\n"
    "o una entrada redirigida).\n"
    "\n"
    "Abre una ventana de Terminal y ejecuta ahi:\n"
    "  cd /Users/giocrisraigodoy/Documents/proyecto_musica && "
    "uv run python -m herramientas.calibrar_ataques"
)


def niveles_de(muestras: np.ndarray, ventana: int) -> list[tuple[float, float]]:
    """Convierte la grabacion en la secuencia (instante, nivel) que vera el detector."""
    salto = int(PASO_ANALISIS * FS)
    return [
        (indice / FS, nivel_dbfs(muestras[indice : indice + ventana]))
        for indice in range(0, len(muestras) - ventana, salto)
    ]


def contar_ataques(niveles, salto_db: float, refractario_s: float) -> int:
    detector = DetectorAtaques(salto_db=salto_db, refractario_s=refractario_s)
    return sum(1 for instante, nivel in niveles if detector.procesar(nivel, instante) is not None)


def _avisar_acoplamiento(refractario_s: float) -> None:
    """Advierte si el refractario elegido rompe el acoplamiento con MUESTRAS_REFERENCIA.

    La mediana de MUESTRAS_REFERENCIA niveles no refleja el nivel nuevo hasta
    pasadas ceil(n/2)-1 vueltas del intervalo de analisis; hasta entonces lo
    unico que evita un disparo repetido es el refractario. Si esta calibracion
    ajusta el salto y el refractario por separado, sin mirar el tamano del
    historial (MUESTRAS_REFERENCIA, en nucleo/ejercicios/ataques.py), puede
    dar un valor que rompa la deteccion sin que nadie lo note aqui.
    """
    n = MUESTRAS_REFERENCIA
    vueltas = math.ceil(n / 2) - 1
    tiempo_mediana_s = vueltas * PASO_ANALISIS
    margen_s = refractario_s - tiempo_mediana_s
    print(
        f"\nAviso de acoplamiento: MUESTRAS_REFERENCIA={n} en "
        "nucleo/ejercicios/ataques.py esta acoplado al salto y al refractario. "
        f"La mediana de {n} niveles solo refleja el nivel nuevo pasadas {vueltas} "
        f"vueltas del analisis ({tiempo_mediana_s * 1000:.0f} ms); hasta entonces "
        "el refractario es lo unico que evita un disparo repetido."
    )
    if margen_s <= 0:
        print(
            f"  ATENCION: con refractario {int(refractario_s * 1000)} ms ese margen es "
            f"negativo ({margen_s * 1000:.0f} ms): una nota sostenida puede marcar un "
            "ataque falso. No cambies el refractario sin revisar tambien "
            "MUESTRAS_REFERENCIA."
        )
    else:
        print(f"  Margen de acoplamiento: {margen_s * 1000:.0f} ms (positivo, correcto).")


def main() -> int:
    if not sys.stdin.isatty():
        print(MENSAJE_NO_INTERACTIVO)
        return 1

    cable = buscar_rocksmith()
    if cable is None:
        print("El cable Rocksmith no aparece. Conectalo y reintenta.")
        return 1

    captura = CapturaAudio(indice_dispositivo=cable.indice, capacidad_buffer=int(FS * (SEGUNDOS + 1)))
    if not captura.iniciar():
        print(f"No se pudo abrir el dispositivo: {captura.ultimo_error}")
        return 1

    print(f"\nPulsa UNA cuerda {PULSACIONES_PEDIDAS} veces, separadas y a volumen normal.")
    print(f"Tienes {SEGUNDOS:.0f} segundos desde que pulses Enter.")
    try:
        input("Enter para empezar...")
    except EOFError:
        captura.detener()
        print()
        print(MENSAJE_NO_INTERACTIVO)
        return 1

    inicio = captura.total_capturado
    while captura.total_capturado - inicio < FS * SEGUNDOS:
        time.sleep(0.05)
    muestras = captura.leer_ventana(int(FS * SEGUNDOS))
    captura.detener()

    ventana = PERFILES["guitarra_estandar"].tamano_ventana(FS)
    niveles = niveles_de(muestras, ventana)

    print(f"\nBuscando los parametros que cuentan {PULSACIONES_PEDIDAS} pulsaciones...\n")
    aciertos = []
    for salto in SALTOS:
        fila = []
        for refractario in REFRACTARIOS:
            contados = contar_ataques(niveles, salto, refractario)
            fila.append(contados)
            if contados == PULSACIONES_PEDIDAS:
                aciertos.append((salto, refractario))
        print(f"  salto {salto:5.1f} dB -> " + "  ".join(f"{c:2d}" for c in fila))
    print("  refractarios (ms): " + "  ".join(f"{int(r * 1000):2d}" for r in REFRACTARIOS))

    if not aciertos:
        print("\nNinguna combinacion acerta el numero de pulsaciones.")
        print("Repite tocando mas separado, o revisa el volumen de la guitarra.")
        return 1

    # Se prefiere el que sigue acertando con el salto un decibelio arriba y abajo:
    # un valor que solo funciona en un punto exacto fallara manana.
    def robustez(par: tuple[float, float]) -> int:
        salto, refractario = par
        return sum(
            1
            for delta in (-1.0, 0.0, 1.0)
            if contar_ataques(niveles, salto + delta, refractario) == PULSACIONES_PEDIDAS
        )

    mejor = max(aciertos, key=robustez)
    print(f"\nRecomendado: salto {mejor[0]:.1f} dB, refractario {int(mejor[1] * 1000)} ms")
    print(f"Margen: acierta en {robustez(mejor)} de 3 variaciones del salto.")
    _avisar_acoplamiento(mejor[1])
    print("\nSi difiere de los valores por defecto, actualiza SALTO_ATAQUE_DB y")
    print("REFRACTARIO_S en nucleo/ejercicios/ataques.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
