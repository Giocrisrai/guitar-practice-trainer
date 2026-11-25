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
from nucleo.piezas.seguimiento import VENTANA_A_TIEMPO_S
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


def retrasos_del_cruce(niveles, salto_db: float, refractario_s: float) -> list[float]:
    """Cuánto tarda el cruce de los dB en llegar, desde que la energía empezó a subir.

    CONTAR BIEN LOS ATAQUES NO ES MARCARLOS EN EL SITIO, y el resto de esta
    herramienta solo comprueba lo primero. `DetectorAtaques` firma el ataque en el
    cuadro donde el nivel supera la referencia por `salto_db`, que es DESPUÉS de que
    la cuerda empezara a sonar: la referencia es la mediana de los últimos
    `MUESTRAS_REFERENCIA` niveles, así que cuanto más alto esté lo que ya sonaba
    -una nota anterior que no se ha apagado, las cuerdas vecinas de un acorde-, más
    tarda el salto en alcanzarse. Ese retraso lo paga el alumno: el carril se lo
    cuenta como haber tocado tarde.

    Esto devuelve, por cada ataque, los milisegundos entre el mínimo local de la
    envolvente que lo precede -donde la subida empieza- y el cuadro donde el
    detector lo firma.

    MEDIDO SOBRE AUDIO SINTÉTICO, que es lo único que había al escribirlo, con los
    valores por defecto y el gemelo PERFECTO (o sea: todo retraso es del detector,
    porque el gemelo toca exactamente en el instante escrito):

        escala de ocho notas sueltas   0  21  21  42  21  84  21   0   ms
        ocho acordes abiertos          0   0  63   0  63   0  63  ...  ms

    Contra una ventana de acierto de 80 ms, los 84 ms de la escala son el borde
    entero: esa es la nota que el carril firmaba a +89 ms y marcaba «tarde» con el
    gemelo tocando perfecto. El peor caso está en una nota SUELTA, no en un acorde,
    que es lo contrario de lo que parecía. En los acordes el patrón es alterno -el
    detector marca dos ataques por rasgueo, el primero en su sitio y el segundo 63
    ms tarde- y la mediana sale cero: el problema es del PEOR caso, no del típico, y
    por eso la corrección tendría que ser un retroceso y no un descuento fijo.

    **POR ESO ESTÁ AQUÍ Y NO CORREGIDO EN EL DETECTOR.** Retroceder el instante del
    ataque hasta el inicio de la subida es la corrección obvia, y no se puede
    calibrar con audio sintético: la rapidez con que sube la envolvente es
    precisamente lo que distingue una pulsación real -ruido de púa, decaimiento
    irregular, resonancia de las vecinas- de un seno con sobretonos. Retroceder
    demasiado sería peor que no retroceder, porque marcaría el ataque ANTES de que
    la cuerda sonara y le daría la razón a un alumno que llegó tarde. Este número,
    medido sobre la guitarra del usuario, es lo que decide si la corrección vale la
    pena y de cuánto.
    """
    detector = DetectorAtaques(salto_db=salto_db, refractario_s=refractario_s)
    suelo = detector.nivel_minimo_dbfs
    valores = np.array([nivel for _, nivel in niveles], dtype=float)
    retrasos = []
    for indice, (instante, nivel) in enumerate(niveles):
        if detector.procesar(nivel, instante) is None:
            continue
        # Hacia atrás mientras la energía siga subiendo: el mínimo local anterior
        # es donde empezó la subida que acabó cruzando el umbral.
        #
        # CON EL SUELO DE RUIDO COMO TOPE, y no es un detalle. Sin él, un golpe
        # seco sobre silencio -el caso en que el detector acierta el instante- se
        # mediría con un cuadro de retraso, porque el cuadro anterior está más
        # bajo y el retroceso se mete en él. Pero ese cuadro era SILENCIO, no la
        # nota empezando: retroceder hasta ahí es marcar el ataque antes de que la
        # cuerda sonara, que es el error que esta medida existe para no cometer.
        inicio = indice
        while (
            inicio > 0
            and valores[inicio - 1] < valores[inicio]
            and valores[inicio - 1] > suelo
        ):
            inicio -= 1
        retrasos.append((indice - inicio) * PASO_ANALISIS * 1000.0)
    return retrasos


def _informar_del_retraso(niveles, salto_db: float, refractario_s: float) -> None:
    """Imprime dónde se marcan los ataques, no solo cuántos hay. Ver `retrasos_del_cruce`."""
    retrasos = retrasos_del_cruce(niveles, salto_db, refractario_s)
    if not retrasos:
        return
    serie = np.array(retrasos)
    print(
        f"\nDónde se marcan: el cruce llega {np.median(serie):.0f} ms de mediana "
        f"(peor caso {serie.max():.0f} ms) después de que la energía empezara a subir."
    )
    print(
        "  Ese retraso no es tuyo: el carril lo cuenta como haber tocado tarde. "
        f"La ventana de acierto son {VENTANA_A_TIEMPO_S * 1000:.0f} ms."
    )
    if serie.max() >= VENTANA_A_TIEMPO_S * 1000.0:
        print(
            "  ATENCION: el peor caso se come la ventana entera, asi que hay notas "
            "bien tocadas que saldran 'tarde'. Apunta estos numeros: son los que "
            "deciden si el detector tiene que retroceder el instante del ataque "
            "hasta el inicio de la subida, y de cuanto."
        )
    else:
        print(
            "  El peor caso cabe en la ventana, asi que retroceder el instante del "
            "ataque no hace falta con esta guitarra y estos valores."
        )


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
    _informar_del_retraso(niveles, mejor[0], mejor[1])
    _avisar_acoplamiento(mejor[1])
    print("\nSi difiere de los valores por defecto, actualiza SALTO_ATAQUE_DB y")
    print("REFRACTARIO_S en nucleo/ejercicios/ataques.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
