"""Imprime el historial de pasadas en la terminal, sin abrir el navegador.

Uso:  uv run python -m herramientas.ver_historial
      uv run python -m herramientas.ver_historial --ruta otro_historial.json
      uv run python -m herramientas.ver_historial --compases    # el detalle

Existe por la misma razón que el cuarto objetivo del diseño (§2): el historial
tiene que poder leerse sin el programa. El archivo es JSON indentado y se puede
abrir con cualquier editor; esto es para cuando lo que se quiere es la foto, no
el archivo.

**NO mide progreso.** Esa medida tiene su propia aritmética y su propia
honestidad —solo se comparan pasadas del mismo tramo al mismo tempo, y una
diferencia por debajo del ruido no se nombra (§4.4)— y todavía no está
construida. Lo que esto hace es enseñar lo que hay guardado, agrupado por lo que
*sería* comparable, para que se vea si hay serie con la que comparar.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from nucleo.historial.registro import DIAS_COMPLETOS, RegistroDePasada, cargar

RUTA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "historial.json"


def proporcion_limpia(pasada: RegistroDePasada) -> float | None:
    """Qué fracción de lo medible salió limpia, 0 a 1, o None si no se puede medir.

    **Los compases con acordes quedan FUERA**, exactamente como hace
    `nucleo.piezas.estudio.proporcion_limpia` con el informe, y por la misma
    razón que su docstring explica. `None` es «no se puede medir» —una pieza
    entera de acordes— y hay que distinguirlo de 0,0, que es «lo fallaste todo».

    Esta exclusión no es purismo: se añadió porque sin ella esta herramienta
    mentía. Un compás de acorde tiene UNA nota medible —un rasgueo, un ataque—,
    así que la proporción solo puede salir 0 % o 100 %. Al gemelo PRINCIPIANTE,
    que fallaba una cuerda de cinco y llegaba 650 ms tarde, esta función le decía
    «100,0 % limpio». Ver `CompasDelRegistro.tiene_acordes`.

    El denominador son las notas medibles de TODAS las vueltas que la pasada
    resume (`medibles * repeticiones`): el numerador acumula vueltas y el
    denominador, sin eso, no.
    """
    sin_acordes = [c for c in pasada.compases if not c.tiene_acordes]
    medibles = sum(c.medibles for c in sin_acordes) * max(1, pasada.repeticiones)
    if medibles == 0:
        return None
    return sum(c.limpias for c in sin_acordes) / medibles


def proporcion_acertada(pasada: RegistroDePasada) -> float | None:
    """Qué fracción de lo ESCRITO sonó, 0 a 1. Cuenta los acordes.

    Es la otra mitad, y en una pieza de acordes es la única que habla: el carril
    cobra las demás cuerdas del acorde por presencia, así que `acertadas` tiene
    sentido sobre `escritas` aunque el ritmo solo se mida una vez por rasgueo.
    «Suenan 4 de 5 cuerdas» es un diagnóstico; «100 % limpio» con una cuerda muda
    es una mentira.

    No dice nada del ritmo, y eso también hay que saberlo: una pasada con todas
    las notas acertadas y medio segundo de retraso sale aquí al 100 %.
    """
    escritas = sum(c.escritas for c in pasada.compases) * max(1, pasada.repeticiones)
    if escritas == 0:
        return None
    return sum(c.acertadas for c in pasada.compases) / escritas


def describir_el_tramo(pasada: RegistroDePasada) -> str:
    primero, ultimo = pasada.tramo
    compases = f"compás {primero}" if primero == ultimo else f"compases {primero}-{ultimo}"
    return f"{compases} al {pasada.factor_tempo * 100:.0f}%"


def imprimir(pasadas: tuple[RegistroDePasada, ...], con_compases: bool) -> None:
    por_pieza: dict[tuple[str, str], list[RegistroDePasada]] = defaultdict(list)
    for pasada in pasadas:
        por_pieza[(pasada.nombre_de_la_pieza, pasada.huella)].append(pasada)

    for (nombre, huella), suyas in sorted(por_pieza.items()):
        print(f"\n{nombre}  [{huella}]")
        series: dict[tuple, list[RegistroDePasada]] = defaultdict(list)
        for pasada in suyas:
            series[pasada.clave_comparable].append(pasada)
        for clave in sorted(series, key=lambda c: (c[1], c[2], c[3])):
            serie = sorted(series[clave], key=lambda r: r.instante)
            cabecera = describir_el_tramo(serie[0])
            # Se dice cuántas hay porque es el dato que decide si se puede
            # comparar algo: con una sola pasada no hay progreso que medir, y
            # mejor decirlo que insinuar una tendencia de un punto.
            print(f"  {cabecera}: {len(serie)} pasada(s)")
            for pasada in serie:
                limpia = proporcion_limpia(pasada)
                acertada = proporcion_acertada(pasada)
                # LAS DOS, y el ritmo primero cuando se pudo medir. Con una sola
                # cifra la foto engaña en los dos sentidos: solo «limpio» calla
                # las cuerdas mudas de un acorde, y solo «suenan» calla el
                # retraso. Ver `proporcion_limpia`.
                partes = []
                if limpia is None:
                    # DOS causas distintas para el mismo `None`, y confundirlas
                    # es decirle al alumno que su acorde no tiene notas: o el
                    # tramo son acordes -el ritmo se mide una vez por rasgueo y
                    # queda fuera- o de verdad no habia nada que medir.
                    hay_acordes = any(c.tiene_acordes for c in pasada.compases)
                    partes.append(
                        "ritmo sin medir (acordes)"
                        if hay_acordes
                        else "sin notas medibles"
                    )
                else:
                    partes.append(f"{limpia * 100:5.1f}% a tiempo")
                if acertada is not None:
                    partes.append(f"{acertada * 100:5.1f}% suenan")
                vueltas = "" if pasada.repeticiones == 1 else f"  ×{pasada.repeticiones}"
                dia = pasada.instante.strftime("%Y-%m-%d %H:%M")
                print(f"    {dia}  {', '.join(partes)}{vueltas}")
                if not con_compases:
                    continue
                for compas in pasada.compases:
                    desfase = (
                        "sin medir"
                        if compas.desfase_medio_ms is None
                        else f"{compas.desfase_medio_ms:+.0f} ms"
                    )
                    print(
                        f"        compás {compas.numero:>3}: "
                        f"{compas.limpias}/{compas.medibles} limpias, "
                        f"{compas.acertadas}/{compas.escritas} acertadas, {desfase}"
                    )


def main(argumentos: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(
        prog="python -m herramientas.ver_historial",
        description="Imprime el historial de pasadas guardado en disco.",
    )
    analizador.add_argument(
        "--ruta", type=Path, default=RUTA_POR_DEFECTO, help="Archivo del historial."
    )
    analizador.add_argument(
        "--compases",
        action="store_true",
        help="Enseña el detalle por compás, no solo el total de cada pasada.",
    )
    pedido = analizador.parse_args(argumentos)

    historial = cargar(pedido.ruta)
    if not historial.pasadas:
        if pedido.ruta.exists():
            print(f"{pedido.ruta} no tiene ninguna pasada guardada todavía.")
        else:
            print(
                f"Todavía no hay historial en {pedido.ruta}.\n"
                "Se crea solo, al cerrar la primera pasada."
            )
        return 0

    print(f"{len(historial.pasadas)} pasada(s) en {pedido.ruta}")
    print(
        f"Se guardan enteros los últimos {DIAS_COMPLETOS} días; de lo anterior, la "
        "mejor pasada de cada día."
    )
    imprimir(historial.pasadas, con_compases=pedido.compases)
    print(
        "\nEsto NO mide progreso: solo enseña lo guardado, agrupado por lo que sería\n"
        "comparable (misma pieza, mismo tramo, mismo tempo). La medida de progreso\n"
        "tiene su propia aritmética y todavía no está construida."
    )
    print(
        "«a tiempo» deja fuera los compases con acordes, donde el ritmo se mide una\n"
        "vez por rasgueo; «suenan» cuenta todas las cuerdas y no dice nada del ritmo."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
