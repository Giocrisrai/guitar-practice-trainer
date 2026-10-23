"""Mide cuánto recorrido de mano ahorra `digitar` frente a la heurística de la 3a.

Uso:  uv run python -m herramientas.medir_digitacion

Existe porque la cifra del README no se podía comprobar. Decía «un 98 % en una
escala de do mayor de 120 notas» sin decir QUÉ escala, y el ahorro depende entero
de la FORMA del material: la misma escala de do mayor de 120 notas da entre un
27 % y un 100 % según cómo esté recorrida. Una cifra que no se puede reproducir no
es una medida, así que el README publica ahora el rango con las cuatro formas que
lo producen y este script es el que las produce.

Qué compara, y por qué así:

- `digitar` resuelve la pieza entera por programación dinámica (el mínimo exacto).
- `elegir_posicion` (`nucleo/piezas/desde_ejercicio.py`) es la heurística de la
  etapa 3a: mira una nota hacia atrás y ninguna hacia delante.
- La vara de medir es `coste_total` con **por_cuerda = 0 y al_aire = 0**, es decir
  SOLO el recorrido de la mano por el mástil. Con los pesos de verdad (1,0 / 0,3 /
  0) la comparación mezclaría el recorrido con el cruce de cuerdas, y lo que la
  frase del README dice es «el recorrido de la mano baja un X %».

    ahorro = 100 · (1 − coste(digitar) / coste(heurística))
"""

from nucleo.afinaciones import PERFILES
from nucleo.musica import posiciones_en_mastil
from nucleo.piezas.desde_ejercicio import elegir_posicion
from nucleo.piezas.digitacion import CosteDigitacion, coste_total, digitar

# Solo el movimiento de la mano: ver el docstring del módulo.
SOLO_LA_MANO = CosteDigitacion(por_traste=1.0, por_cuerda=0.0, al_aire=0.0)

# Los grados de la escala mayor, en semitonos desde la tónica.
MAYOR = (0, 2, 4, 5, 7, 9, 11)

NOTAS_POR_FORMA = 120


def _escala(desde_midi: int, grados: int = 22) -> list[int]:
    """`grados` notas de la escala mayor subiendo desde `desde_midi`."""
    return [desde_midi + 12 * (i // 7) + MAYOR[i % 7] for i in range(grados)]


def _en_bucle(patron: list[int], cuantas: int = NOTAS_POR_FORMA) -> list[int]:
    return [patron[i % len(patron)] for i in range(cuantas)]


def formas() -> dict[str, list[int]]:
    """Las cuatro formas de recorrer una escala, de la peor a la mejor para `digitar`."""
    subida = _escala(48)  # C3..C6
    return {
        "diente de sierra (sube y vuelve a empezar), C3..C6": _en_bucle(subida),
        "sube y baja, C3..C6": _en_bucle(subida + subida[-2:0:-1]),
        "diente de sierra, C2..C5 (más grave)": _en_bucle(_escala(40)),
        "una octava en bucle, C3..C4": _en_bucle(subida[:8]),
    }


def _heuristica(midis: list[int], perfil) -> tuple:
    """Lo que elegiría la heurística de cercanía de la etapa 3a."""
    elegidas, anterior = [], None
    for midi in midis:
        posicion = elegir_posicion(posiciones_en_mastil(midi, perfil), anterior)
        elegidas.append(posicion)
        anterior = posicion.traste
    return tuple(elegidas)


def ahorro(midis: list[int], perfil) -> float:
    """El % de recorrido de mano que `digitar` ahorra sobre la heurística."""
    optimo = coste_total(digitar(midis, perfil), perfil, SOLO_LA_MANO)
    cercania = coste_total(_heuristica(midis, perfil), perfil, SOLO_LA_MANO)
    if cercania == 0:
        return 0.0
    return 100.0 * (1.0 - optimo / cercania)


def main() -> int:
    perfil = PERFILES["guitarra_estandar"]
    print(f"{NOTAS_POR_FORMA} notas por forma, {perfil.nombre}, solo el recorrido")
    print("de la mano (por_cuerda = 0, al_aire = 0).\n")
    for nombre, midis in formas().items():
        print(
            f"{ahorro(midis, perfil):5.1f} % menos recorrido  <- {nombre} "
            f"(midi {min(midis)}..{max(midis)})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
