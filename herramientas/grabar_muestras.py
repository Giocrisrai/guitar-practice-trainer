"""Graba las seis cuerdas al aire para usarlas como pruebas permanentes.

Uso:  .venv/bin/python -m herramientas.grabar_muestras
"""

import sys
import time
from pathlib import Path

import numpy as np
import soundfile

from nucleo.afinaciones import PerfilAfinacion, PERFILES
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS, nivel_dbfs
from nucleo.analisis.pipeline import Analizador
from nucleo.captura import CapturaAudio, buscar_rocksmith

DESTINO = Path(__file__).resolve().parent.parent / "tests" / "audio"
SEGUNDOS = 3.0
FS = 48000

# Ventana pequeña para sondear el nivel: suficientemente corta para no retrasar
# la detección del silencio ni la del ataque, suficientemente larga para que el
# RMS no sea puro ruido de cuantización.
VENTANA_NIVEL = 1024

SILENCIO_MINIMO_S = 0.3
ESPERA_SILENCIO_MAXIMA_S = 10.0
ESPERA_ATAQUE_MAXIMA_S = 20.0

MENSAJE_NO_INTERACTIVO = (
    "Este script es interactivo: pide pulsar Enter antes de grabar cada cuerda.\n"
    "No se puede ejecutar desde un canal sin terminal (por ejemplo, una tubería\n"
    "o una entrada redirigida).\n"
    "\n"
    "Abre una ventana de Terminal y ejecuta ahí:\n"
    "  cd /Users/giocrisraigodoy/Documents/proyecto_musica && "
    ".venv/bin/python -m herramientas.grabar_muestras"
)


def _esperar_nivel(
    captura: CapturaAudio,
    bajo_umbral: bool,
    duracion_minima: float,
    limite_espera: float,
) -> bool:
    """Bloquea hasta que el nivel de la señal cumpla la condición pedida.

    Se usa con dos propósitos opuestos y por eso vive en una sola función en vez
    de repetir el bucle:

    - Esperar silencio (bajo_umbral=True, duracion_minima=0.3): antes de grabar
      una cuerda nueva hay que drenar la cola de la anterior, que sigue sonando
      por debajo del umbral de ruido durante un rato después de apagarse. Sin
      esta espera esa cola se mezclaría con el ataque de la siguiente
      grabación. Se exige el nivel bajo sostenido, no un instante, porque un
      trémolo o un armónico pasajero puede cruzar el umbral hacia abajo un
      momento sin que la cuerda haya terminado de sonar.
    - Esperar el ataque (bajo_umbral=False, duracion_minima=0.0): detecta el
      instante en que el usuario pulsa la cuerda. Aquí no hace falta
      sostenimiento: el primer instante por encima del umbral ya es el inicio
      real de la nota, y esperar más solo recortaría el principio de la
      grabación.

    Devuelve True si la condición se cumplió dentro de limite_espera segundos,
    False si se agotó el tiempo sin cumplirse.
    """
    inicio_espera = time.monotonic()
    inicio_condicion: float | None = None
    while time.monotonic() - inicio_espera < limite_espera:
        muestras = captura.leer_ventana(VENTANA_NIVEL)
        if muestras is not None:
            nivel = nivel_dbfs(muestras)
            cumple = (
                nivel <= UMBRAL_RUIDO_POR_DEFECTO_DBFS
                if bajo_umbral
                else nivel > UMBRAL_RUIDO_POR_DEFECTO_DBFS
            )
            if cumple:
                if inicio_condicion is None:
                    inicio_condicion = time.monotonic()
                if time.monotonic() - inicio_condicion >= duracion_minima:
                    return True
            else:
                inicio_condicion = None
        time.sleep(0.02)
    return False


def _verificar_grabacion(
    muestras: np.ndarray, perfil: PerfilAfinacion
) -> tuple[str | None, float, float]:
    """Analiza la grabación en ventanas solapadas, igual que test_audio_real.py.

    tamano_suavizado=1 porque aquí interesa ver cada ventana tal cual, no una
    mediana móvil pensada para una lectura en vivo.

    Devuelve (nota_mayoritaria, proporcion_de_ventanas, cents_medianos). Si
    ninguna ventana detectó una nota, devuelve (None, 0.0, 0.0).
    """
    analizador = Analizador(perfil, frecuencia_muestreo=FS, tamano_suavizado=1)
    ventana = perfil.tamano_ventana(FS)
    salto = ventana // 4

    resultados = []
    for inicio in range(0, len(muestras) - ventana, salto):
        resultado = analizador.procesar(muestras[inicio : inicio + ventana])
        if resultado.estado == "nota":
            resultados.append(resultado)

    if not resultados:
        return None, 0.0, 0.0

    notas = [r.nota for r in resultados]
    nota_mayoritaria = max(set(notas), key=notas.count)
    proporcion = notas.count(nota_mayoritaria) / len(resultados)
    cents_medianos = float(
        np.median([r.cents for r in resultados if r.nota == nota_mayoritaria])
    )
    return nota_mayoritaria, proporcion, cents_medianos


def main() -> int:
    if not sys.stdin.isatty():
        print(MENSAJE_NO_INTERACTIVO)
        return 1

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
        while True:
            try:
                input(f"\nCuerda {cuerda.numero} ({cuerda.nota}) al aire. Enter y púlsala...")
            except EOFError:
                captura.detener()
                print()
                print(MENSAJE_NO_INTERACTIVO)
                return 1

            if not _esperar_nivel(
                captura,
                bajo_umbral=True,
                duracion_minima=SILENCIO_MINIMO_S,
                limite_espera=ESPERA_SILENCIO_MAXIMA_S,
            ):
                print("  Aviso: hay ruido constante, no se detectó silencio. Se continúa igualmente.")

            if not _esperar_nivel(
                captura,
                bajo_umbral=False,
                duracion_minima=0.0,
                limite_espera=ESPERA_ATAQUE_MAXIMA_S,
            ):
                print("  No se detectó ninguna pulsación. Inténtalo de nuevo.")
                continue

            inicio = captura.total_capturado
            while captura.total_capturado - inicio < FS * SEGUNDOS:
                time.sleep(0.05)
            muestras = captura.leer_ventana(int(FS * SEGUNDOS))

            nota_detectada, proporcion, cents_medianos = _verificar_grabacion(
                muestras, perfil
            )
            if nota_detectada is None:
                print("  No se detectó ninguna nota en la grabación. Inténtalo de nuevo.")
                continue

            soundfile.write(DESTINO / nombre, muestras.astype(np.float32), FS)
            if nota_detectada != cuerda.nota:
                print(
                    f"  guardado {nombre}  AVISO: se esperaba {cuerda.nota} pero se "
                    f"detectó {nota_detectada} en el {proporcion:.0%} de las ventanas. "
                    "Revisa la afinación antes de dar la grabación por buena."
                )
            else:
                print(
                    f"  guardado {nombre}  nota {nota_detectada}  "
                    f"{proporcion:.0%} de ventanas correctas  "
                    f"cents medianos {cents_medianos:+.1f}"
                )
            break

    captura.detener()
    print(f"\nGrabaciones en {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
