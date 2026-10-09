/** Geometría del carril: de tiempo y cuerda a píxeles.
 *
 * Es un módulo puro: ni canvas, ni React, ni `document`. Recibe el instante de
 * la pieza y el tamaño del lienzo por parámetro, y devuelve rectángulos; quien
 * lo llame decide cómo y dónde se pintan.
 *
 * No decide nada musical: la clasificación de cada pulsación ("a_tiempo",
 * "pronto", "tarde") y el veredicto de la afinación (`NotaTocada.afinada`) ya
 * vienen dados por el núcleo (ver `tiposPieza.ts`) y este módulo no los toca ni
 * los deriva del desfase o de los cents. Lo único que este módulo decide es de
 * qué color se pinta una desviación ya juzgada, que es una elección puramente
 * visual, no un veredicto.
 */

import type { NotaDePieza } from "./tiposPieza";

/** Cuántos segundos de pieza caben en el carril a la vez, POR DELANTE de la
 * línea de ataque. Por detrás hay además `ESTELA_S`. */
export const VENTANA_VISIBLE_S = 4.0;

/**
 * Cuánto se sigue viendo una nota después de sonar: la estela.
 *
 * La spec §4 dice que «cada nota tocada se queda pintada en el carril con su
 * desviación en cents y un color que la distingue de un vistazo», porque es lo
 * que convierte un problema de afinación en un patrón visible —si todas las
 * notas de una cuerda salen bajas, no es tu dedo, es la cuerda—. Sin una franja
 * por detrás de la línea de ataque no había donde pintarlas: la línea era el
 * borde de abajo del lienzo, así que una nota desaparecía en cuanto terminaba de
 * sonar y el patrón no se llegaba a ver nunca.
 *
 * Un segundo, y no más: la estela se come alto del lienzo, que es lo que se ve
 * por delante, y lo que viene es lo que hay que tocar.
 */
export const ESTELA_S = 1.0;

/** Una nota dentro de la ventana visible. Misma forma que `NotaDePieza`: este
 * módulo no le añade nada, solo decide cuáles entran. */
export type NotaVisible = NotaDePieza;

/** Tamaño del lienzo donde se dibuja el carril, en píxeles, y cuántas cuerdas
 * tiene el instrumento (cuántos carriles horizontales hay que repartir). */
export interface LienzoCarril {
  ancho: number;
  alto: number;
  cuerdas: number;
}

/** Un rectángulo en píxeles, listo para pintar. */
export interface RectanguloNota {
  x: number;
  y: number;
  ancho: number;
  alto: number;
}

/** Pulsos a segundos, igual que `pulsos_a_segundos` en nucleo/piezas/modelo.py:
 * segundos = pulsos * 60 / tempo. */
function pulsosASegundos(pulsos: number, tempo: number): number {
  return (pulsos * 60) / tempo;
}

/**
 * Qué notas de la pieza caben en el carril ahora mismo.
 *
 * Una nota es visible si ya empezó a estar dentro del horizonte que se ve por
 * delante (`ventanaS`) y todavía no ha salido por detrás: terminar de sonar no
 * la borra, se queda la estela (`ESTELA_S`), que es lo que permite ver de un
 * vistazo el patrón de lo que acabas de tocar. Lo que importa para dejar de
 * dibujarla es cuándo acaba, no cuándo empezó.
 */
export function notasVisibles(
  notas: readonly NotaDePieza[],
  instanteS: number,
  tempo: number,
  ventanaS: number
): NotaVisible[] {
  return notas.filter((nota) => {
    const inicioS = pulsosASegundos(nota.inicio_pulsos, tempo);
    const finS = inicioS + pulsosASegundos(nota.duracion_pulsos, tempo);
    return finS > instanteS - ESTELA_S && inicioS < instanteS + ventanaS;
  });
}

/**
 * A qué píxel cae la línea de ataque: ahí suena la nota que toca AHORA.
 *
 * No es el borde de abajo del lienzo, porque debajo va la estela de las notas
 * que ya sonaron (ver `ESTELA_S`). Lo dice este módulo y no quien pinta, para
 * que la línea y los rectángulos no puedan discrepar.
 */
export function yDeLaLineaDeAtaque(
  lienzo: LienzoCarril,
  ventanaS: number = VENTANA_VISIBLE_S
): number {
  return lienzo.alto - ESTELA_S * pixelesPorSegundoDe(lienzo, ventanaS);
}

/** Píxeles por segundo de pieza: el alto del lienzo reparte la ventana que se ve
 * por delante MAS la estela que se ve por detrás. */
function pixelesPorSegundoDe(lienzo: LienzoCarril, ventanaS: number): number {
  return lienzo.alto / (ventanaS + ESTELA_S);
}

/**
 * El rectángulo de una nota en el instante `instanteS`.
 *
 * Vertical: la línea de ataque (`yDeLaLineaDeAtaque`) es donde suena la nota
 * que toca AHORA, y por debajo de ella queda la estela de las que ya sonaron.
 * Una nota futura se dibuja más arriba (`y` menor) cuanto más lejos esté en el
 * tiempo, a razón de `lienzo.alto / (ventanaS + ESTELA_S)` píxeles por segundo;
 * esa misma escala fija el alto del rectángulo a partir de la duración de la
 * nota. Subir el tempo acorta en segundos la distancia hasta cualquier nota
 * (los mismos pulsos caben en menos tiempo), así que a más tempo la nota llega
 * antes: más cerca de la línea de ataque para el mismo instante.
 *
 * OJO con `y`: es el borde de ATAQUE de la nota, es decir su borde INFERIOR
 * (el que llega primero a la línea de ataque), no el superior. La nota que
 * suena ahora da `y = yDeLaLineaDeAtaque(lienzo, ventanaS)`. El rectángulo
 * ocupa por tanto de `y - alto` a `y`; quien use `fillRect` debe pasar
 * `y - alto` como esquina superior, o pintará fuera del lienzo.
 *
 * `ventanaS` es la misma ventana que se le dio a `notasVisibles`; si se usa
 * una distinta de la por defecto hay que pasarla aquí también, o una nota
 * visible caería fuera del lienzo.
 *
 * Horizontal: cada cuerda tiene su propio carril, repartiendo `lienzo.ancho`
 * en `lienzo.cuerdas` franjas iguales; la cuerda 1 va al carril de más a la
 * izquierda y la última cuerda al de más a la derecha, un lado fijo para cada
 * una.
 */
export function rectanguloDeNota(
  nota: NotaDePieza,
  instanteS: number,
  tempo: number,
  lienzo: LienzoCarril,
  ventanaS: number = VENTANA_VISIBLE_S
): RectanguloNota {
  const pixelesPorSegundo = pixelesPorSegundoDe(lienzo, ventanaS);

  const inicioS = pulsosASegundos(nota.inicio_pulsos, tempo);
  const duracionS = pulsosASegundos(nota.duracion_pulsos, tempo);
  const faltanS = inicioS - instanteS; // segundos hasta que la nota llegue a la línea de ataque

  const y = yDeLaLineaDeAtaque(lienzo, ventanaS) - faltanS * pixelesPorSegundo;
  const alto = duracionS * pixelesPorSegundo;

  const anchoCarril = lienzo.ancho / lienzo.cuerdas;
  const indiceCuerda = nota.cuerda - 1;
  const x = indiceCuerda * anchoCarril;

  return { x, y, ancho: anchoCarril, alto };
}

const COLOR_DESCONOCIDO = "#7d848f"; // gris: la desviación no se supo
const COLOR_AFINADA = "#34d17a"; // verde: dentro de la tolerancia
const COLOR_ALTA = "#e8a33d"; // ámbar: sonó por encima
const COLOR_BAJA = "#3d8ee8"; // azul: sonó por debajo

/** Lo que hace falta para pintar una desviación: cuánta fue y si el núcleo la da
 * por afinada. Es la parte de `NotaTocada` que este módulo necesita, y nada más:
 * así se puede pintar también algo que no sea una nota de la pieza. */
export interface DesviacionPintable {
  cents: number | null;
  afinada: boolean | null;
}

/**
 * Color para pintar la desviación en cents de una nota tocada.
 *
 * El VEREDICTO -si está afinada- lo trae el núcleo en `afinada`, con la misma
 * regla que el resto del programa (`nucleo.musica.esta_afinada`). Este módulo
 * solo elige el color, que es una decisión visual; antes se copiaba aquí el
 * umbral de 5 cents, y un umbral duplicado es un umbral que algún día dirá otra
 * cosa que el núcleo.
 *
 * `cents === null` significa que la desviación no se supo (el detector no la
 * dio; es independiente de si se supo el instante, ver `NotaTocada` en
 * `tiposPieza.ts`), NO que sonara perfectamente afinada: por eso tiene su
 * propio color, distinto del de `cents === 0`. Confundirlos pintaría en verde
 * una nota de la que no se sabe nada. `afinada === null` dice lo mismo desde el
 * otro lado y se trata igual.
 */
export function colorDeDesviacion({ cents, afinada }: DesviacionPintable): string {
  if (cents === null || afinada === null) return COLOR_DESCONOCIDO;
  if (afinada) return COLOR_AFINADA;
  return cents > 0 ? COLOR_ALTA : COLOR_BAJA;
}
