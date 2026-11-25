"""Calibra `UMBRAL_PRESENCIA` con la guitarra real.

El 0,45 que hay escrito en `nucleo/analisis/acordes.py` sale de acordes
SINTÉTICOS: ocho senoides con decaimiento por cuerda. Ahí el hueco entre la
cuerda que suena (0,58 como mínimo) y la que está muda (0,32 como máximo) es
ancho y 0,45 cae cómodamente en medio. Una pastilla electromagnética reparte los
armónicos de otra manera —y el cuerpo de la guitarra, el ataque de la púa y la
resonancia de las cuerdas vecinas también—, así que el hueco real puede ser más
estrecho, estar desplazado, o no existir. Esta herramienta lo MIDE.

Lo que mide, y por qué eso y no otra cosa: el umbral solo decide, y la decisión
es por cuadro. Lo que lo hace bueno o malo son dos números:

- el MÍNIMO de la presencia de una cuerda que SÍ suena, porque por debajo de él
  el programa dirá «te falta esa cuerda» a quien la está tocando;
- el MÁXIMO de la presencia de una cuerda que NO suena, porque por encima de él
  dirá «completo» a un acorde al que le falta una.

Un umbral sirve si cae entre los dos. El hueco entre ellos es el margen, y es lo
que esta herramienta imprime: si sale negativo, ningún umbral separa los dos
casos con esta guitarra y lo que hay que cambiar no es el número, es la medida
(más armónicos, otra ventana, otro ancho de banda).

Las presencias NO dependen del umbral —`DetectorAcordes` las calcula y luego las
compara—, así que esta medición no arrastra el valor que viene de fábrica: se
puede ejecutar con el 0,45 puesto y el resultado no lo sabe.

Uso:  uv run python -m herramientas.calibrar_presencia
      uv run python -m herramientas.calibrar_presencia --acordes do,sol
      uv run python -m herramientas.calibrar_presencia --umbral-ruido -45
"""

import argparse
import sys
import time

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.acordes import UMBRAL_PRESENCIA, DetectorAcordes
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS
from nucleo.captura import CapturaAudio, buscar_rocksmith
from nucleo.ejercicios.generadores.acordes import DIGITACIONES, acorde_de_clave
from servidor.sesion import INTERVALO_ANALISIS

FS = 48000
SEGUNDOS = 3.0
PERFIL = "guitarra_estandar"

# El mismo paso con el que el servidor alimenta al detector en vivo. Calibrar con
# otro paso daría presencias que no son las que verá el programa: el detector
# acumula en su propio búfer y el solape entre ventanas depende de este número.
PASO_ANALISIS = INTERVALO_ANALISIS

# La cuerda que se pide apagar en la segunda toma de cada acorde.
#
# La 1.ª (la más aguda) por tres razones: los ocho acordes de la tabla la usan,
# es la más fácil de apagar con el canto del dedo sin tocar las demás, y es la
# que la spec usó en su propio ejemplo («Do sin la 1.ª»). El número que sale
# valdría igual con cualquier otra: lo que se mide es una cuerda muda, no esa.
CUERDA_MUDA = 1

# Percentiles con los que se resume cada toma.
#
# No se usa el extremo absoluto para recomendar, aunque sí se imprime. Un solo
# cuadro malo —el instante del ataque, en el que el espectro es el del golpe de
# la púa y no el de las notas— arrastraría el umbral hasta donde no sirve. El
# percentil 10 de lo que suena y el 90 de lo que no es el hueco que se da
# CASI SIEMPRE, que es la promesa que un umbral puede cumplir.
PERCENTIL_SONANDO = 10.0
PERCENTIL_MUDA = 90.0

MENSAJE_NO_INTERACTIVO = (
    "Este script es interactivo: pide pulsar Enter antes de grabar cada toma.\n"
    "No se puede ejecutar desde un canal sin terminal (por ejemplo, una tubería\n"
    "o una entrada redirigida).\n"
    "\n"
    "Abre una ventana de Terminal y ejecuta ahí:\n"
    "  cd /Users/giocrisraigodoy/Documents/proyecto_musica && "
    "uv run python -m herramientas.calibrar_presencia"
)


def presencias_de(
    muestras: np.ndarray,
    midis_esperados: tuple[int, ...],
    umbral_ruido_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS,
    frecuencia_muestreo: int = FS,
) -> dict[int, list[float]]:
    """Recorre la grabación como lo haría el servidor y junta las presencias.

    Devuelve, por cada MIDI esperado, la lista de sus presencias cuadro a cuadro.
    Solo entran los cuadros que el detector llegó a juzgar: los que caen bajo la
    compuerta de ruido o con el búfer a medio llenar devuelven "silencio" y no
    traen presencias, igual que en producción. Esa es justamente la selección que
    se quiere —el umbral solo se aplica a cuadros juzgados—, así que no hay que
    recortar la grabación a mano.
    """
    detector = DetectorAcordes(
        PERFILES[PERFIL],
        frecuencia_muestreo=frecuencia_muestreo,
        umbral_ruido_dbfs=umbral_ruido_dbfs,
    )
    bloque = max(1, int(PASO_ANALISIS * frecuencia_muestreo))
    recogidas: dict[int, list[float]] = {midi: [] for midi in midis_esperados}
    for inicio in range(0, len(muestras), bloque):
        resultado = detector.procesar(muestras[inicio : inicio + bloque], midis_esperados)
        for midi, valor in resultado.presencias.items():
            recogidas[midi].append(valor)
    return recogidas


def resumir(valores: list[float], percentil: float) -> tuple[float, float]:
    """(percentil, extremo) de una lista de presencias.

    El extremo es el mínimo cuando se pide un percentil bajo y el máximo cuando
    se pide uno alto: en los dos casos es "el peor cuadro" para el umbral.
    """
    if not valores:
        return (float("nan"), float("nan"))
    arreglo = np.asarray(valores, dtype=np.float64)
    extremo = float(arreglo.min()) if percentil < 50.0 else float(arreglo.max())
    return (float(np.percentile(arreglo, percentil)), extremo)


def recomendar(sonando: list[float], mudas: list[float]) -> tuple[float, float]:
    """(umbral recomendado, margen) a partir de todas las presencias recogidas.

    El umbral va al centro del hueco entre el percentil de lo que suena y el de
    lo que no. El margen es el ancho de ese hueco: negativo significa que no hay
    ningún umbral que separe los dos casos.
    """
    piso, _ = resumir(sonando, PERCENTIL_SONANDO)
    techo, _ = resumir(mudas, PERCENTIL_MUDA)
    return ((piso + techo) / 2.0, piso - techo)


def _grabar(captura: CapturaAudio, segundos: float) -> np.ndarray:
    inicio = captura.total_capturado
    while captura.total_capturado - inicio < FS * segundos:
        time.sleep(0.05)
    return captura.leer_ventana(int(FS * segundos))


def _pedir(texto: str) -> bool:
    """Espera el Enter. Devuelve False si la entrada se cerró."""
    try:
        input(texto)
    except EOFError:
        print()
        print(MENSAJE_NO_INTERACTIVO)
        return False
    return True


def _toma(
    captura: CapturaAudio,
    aviso: str,
    midis: tuple[int, ...],
    umbral_ruido: float,
    segundos: float,
) -> dict[int, list[float]] | None:
    print(f"\n{aviso}")
    if not _pedir(f"  Enter y rasguea durante {segundos:.0f} s..."):
        return None
    muestras = _grabar(captura, segundos)
    recogidas = presencias_de(muestras, midis, umbral_ruido_dbfs=umbral_ruido)
    juzgados = len(next(iter(recogidas.values()), []))
    if juzgados == 0:
        print(
            "  Ningún cuadro pasó la compuerta de ruido: no se oyó nada por encima de "
            f"{umbral_ruido:.1f} dBFS.\n"
            "  Sube el volumen de la guitarra, o baja el umbral con --umbral-ruido."
        )
        return None
    print(f"  {juzgados} cuadros juzgados.")
    return recogidas


def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analizador.add_argument(
        "--acordes",
        default=",".join(DIGITACIONES),
        help="Claves separadas por comas. Por defecto, los ocho de la tabla.",
    )
    analizador.add_argument("--segundos", type=float, default=SEGUNDOS)
    analizador.add_argument(
        "--umbral-ruido",
        type=float,
        default=UMBRAL_RUIDO_POR_DEFECTO_DBFS,
        help="El mismo que uses en el programa, en dBFS. Si tocas flojo, bájalo.",
    )
    opciones = analizador.parse_args(argv)

    claves = [c.strip() for c in opciones.acordes.split(",") if c.strip()]
    desconocidas = [c for c in claves if c not in DIGITACIONES]
    if desconocidas:
        print(f"No conozco: {', '.join(desconocidas)}. Opciones: {', '.join(DIGITACIONES)}")
        return 1
    if not sys.stdin.isatty():
        print(MENSAJE_NO_INTERACTIVO)
        return 1

    cable = buscar_rocksmith()
    if cable is None:
        print("El cable Rocksmith no aparece. Conéctalo y reintenta.")
        return 1

    perfil = PERFILES[PERFIL]
    captura = CapturaAudio(
        indice_dispositivo=cable.indice,
        capacidad_buffer=int(FS * (opciones.segundos + 1)),
    )
    if not captura.iniciar():
        print(f"No se pudo abrir el dispositivo: {captura.ultimo_error}")
        return 1

    print(
        f"\nDos tomas por acorde: una completa y una con la {CUERDA_MUDA}.ª cuerda APAGADA\n"
        "(el canto del dedo encima, sin pisarla). La segunda es la que da la mitad\n"
        "del número: sin una cuerda muda de verdad no hay con qué comparar."
    )

    sonando: list[float] = []
    mudas: list[float] = []
    filas: list[tuple[str, float, float, float, float]] = []

    try:
        for clave in claves:
            nombre, _ = DIGITACIONES[clave]
            acorde = acorde_de_clave(clave, perfil)
            por_cuerda = {p.cuerda: m for p, m in zip(acorde.posiciones, acorde.midis)}
            midi_muda = por_cuerda.get(CUERDA_MUDA)
            if midi_muda is None:
                print(f"\n{nombre} no usa la {CUERDA_MUDA}.ª cuerda: se salta.")
                continue

            completa = _toma(
                captura, f"{nombre}, COMPLETO.", acorde.midis, opciones.umbral_ruido,
                opciones.segundos,
            )
            if completa is None:
                return 1
            # Todas las esperadas suenan, así que todas las presencias son del
            # caso "sí suena".
            de_esta_completa = [v for valores in completa.values() for v in valores]

            muda = _toma(
                captura,
                f"{nombre}, con la {CUERDA_MUDA}.ª APAGADA.",
                acorde.midis,
                opciones.umbral_ruido,
                opciones.segundos,
            )
            if muda is None:
                return 1
            # Aquí la grabación es de un acorde al que le falta una: la cuerda
            # apagada va al montón de "no suena" y el resto al de "sí suena".
            de_esta_muda = muda[midi_muda]
            de_esta_sonando = [
                v for midi, valores in muda.items() if midi != midi_muda for v in valores
            ]

            sonando.extend(de_esta_completa)
            sonando.extend(de_esta_sonando)
            mudas.extend(de_esta_muda)

            piso, minimo = resumir(de_esta_completa + de_esta_sonando, PERCENTIL_SONANDO)
            techo, maximo = resumir(de_esta_muda, PERCENTIL_MUDA)
            filas.append((nombre, piso, minimo, techo, maximo))
    finally:
        captura.detener()

    if not filas:
        print("\nNinguna toma válida: no hay nada que calibrar.")
        return 1

    print("\n                        suena (p10 / mín)   muda (p90 / máx)")
    for nombre, piso, minimo, techo, maximo in filas:
        print(f"  {nombre:<18} {piso:6.2f} / {minimo:5.2f}      {techo:6.2f} / {maximo:5.2f}")

    recomendado, margen = recomendar(sonando, mudas)
    piso_total, minimo_total = resumir(sonando, PERCENTIL_SONANDO)
    techo_total, maximo_total = resumir(mudas, PERCENTIL_MUDA)

    print(f"\nTodo junto: suena desde {piso_total:.2f} (p10), muda hasta {techo_total:.2f} (p90).")
    print(f"Hueco: {margen:.2f}.")
    if margen <= 0.0:
        print(
            "\nNEGATIVO: con esta guitarra no hay ningún umbral que separe la cuerda que\n"
            "suena de la que no. El número no es el problema; la medida sí. Lo que hay que\n"
            "revisar es `saliencia_de_nota` (nucleo/analisis/espectro.py): más armónicos,\n"
            f"otro ancho de banda, u otra ventana (hoy {DetectorAcordes(perfil).ventana} "
            "muestras).\n"
            "No toques UMBRAL_PRESENCIA con este resultado: cualquier valor fallará en uno\n"
            "de los dos casos."
        )
        return 1

    print(f"Recomendado: UMBRAL_PRESENCIA = {recomendado:.2f}   (hoy, {UMBRAL_PRESENCIA:.2f})")
    if margen < 0.1:
        print(
            "\nAviso: el hueco es estrecho. El umbral acertará, pero un día con otra púa o\n"
            "otro volumen puede no acertar. Repite la medición antes de darlo por bueno."
        )
    print(
        f"\nEn el peor cuadro de todos: una cuerda que suena bajó a {minimo_total:.2f} y una\n"
        f"muda subió a {maximo_total:.2f}. El recomendado NO los separa a los dos a propósito:\n"
        "separa lo que pasa casi siempre (ver PERCENTIL_SONANDO en este archivo)."
    )
    print("\nSi difiere del de hoy, actualiza UMBRAL_PRESENCIA en nucleo/analisis/acordes.py")
    print("y anota ahí, al lado de la tabla sintética, los números que acabas de medir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
