/** Geometría del carril: de tiempo y cuerda a píxeles.
 *
 * Es un módulo puro: ni canvas, ni React, ni `document`. Recibe el instante de
 * la pieza y el tamaño del lienzo por parámetro, y devuelve rectángulos; quien
 * lo llame decide cómo y dónde se pintan.
 *
 * No decide nada musical: la clasificación de cada pulsación ("a_tiempo",
 * "pronto", "tarde") ya viene dada por el núcleo en `NotaTocada.clasificacion`
 * (ver `tiposPieza.ts`) y este módulo no la toca ni la deriva del desfase. Lo
 * único que este módulo decide es de qué color se pinta una desviación en
 * cents, que es una elección puramente visual, no un veredicto.
 */

import type { NotaDePieza } from "./tiposPieza";

/** Cuántos segundos de pieza caben en el carril a la vez. */
export const VENTANA_VISIBLE_S = 4.0;

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
 * Qué notas de la pieza caben en la ventana visible ahora mismo.
 *
 * Una nota es visible si todavía no ha terminado de sonar (su fin está en el
 * futuro) y ya empezó a estar dentro del horizonte que se ve por delante
 * (`ventanaS`). Una nota que ya terminó de sonar deja de estar visible aunque
 * su inicio siga "cerca": lo que importa para dejar de dibujarla es cuándo
 * acaba, no cuándo empezó.
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
    return finS > instanteS && inicioS < instanteS + ventanaS;
  });
}

/**
 * El rectángulo de una nota en el instante `instanteS`.
 *
 * Vertical: el fondo del lienzo (`lienzo.alto`) es la línea de ataque, donde
 * suena la nota que toca AHORA. Una nota futura se dibuja más arriba (`y`
 * menor) cuanto más lejos esté en el tiempo, a razón de `lienzo.alto /
 * ventanaS` píxeles por segundo; esa misma escala fija el alto del
 * rectángulo a partir de la duración de la nota. Subir el tempo acorta en
 * segundos la distancia hasta cualquier nota (los mismos pulsos caben en
 * menos tiempo), así que a más tempo la nota llega antes: más cerca de la
 * línea de ataque para el mismo instante.
 *
 * OJO con `y`: es el borde de ATAQUE de la nota, es decir su borde INFERIOR
 * (el que llega primero a la línea de ataque), no el superior. La nota que
 * suena ahora da `y = lienzo.alto`. El rectángulo ocupa por tanto de `y -
 * alto` a `y`; quien use `fillRect` debe pasar `y - alto` como esquina
 * superior, o pintará fuera del lienzo.
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
  const pixelesPorSegundo = lienzo.alto / ventanaS;

  const inicioS = pulsosASegundos(nota.inicio_pulsos, tempo);
  const duracionS = pulsosASegundos(nota.duracion_pulsos, tempo);
  const faltanS = inicioS - instanteS; // segundos hasta que la nota llegue a la línea de ataque

  const y = lienzo.alto - faltanS * pixelesPorSegundo;
  const alto = duracionS * pixelesPorSegundo;

  const anchoCarril = lienzo.ancho / lienzo.cuerdas;
  const indiceCuerda = nota.cuerda - 1;
  const x = indiceCuerda * anchoCarril;

  return { x, y, ancho: anchoCarril, alto };
}

/** Escala de color que IMITA la tolerancia del núcleo
 * (`nucleo.musica.esta_afinada`: `abs(cents) < 5.0`, estricto). Es una copia
 * visual, no la fuente de verdad: algún día debería venir dada por el núcleo.
 * No hay ningún veredicto de acierto que dependa de este número. */
const TOLERANCIA_AFINADA_CENTS = 5;

const COLOR_DESCONOCIDO = "#7d848f"; // gris: la desviación no se supo
const COLOR_AFINADA = "#34d17a"; // verde: dentro de la tolerancia
const COLOR_ALTA = "#e8a33d"; // ámbar: sonó por encima
const COLOR_BAJA = "#3d8ee8"; // azul: sonó por debajo

/**
 * Color para pintar la desviación en cents de una nota tocada.
 *
 * `cents === null` significa que la desviación no se supo (el detector no la
 * dio; es independiente de si se supo el instante, ver `NotaTocada` en
 * `tiposPieza.ts`), NO que sonara perfectamente afinada: por eso tiene su
 * propio color, distinto del de `cents === 0`. Confundirlos pintaría en verde
 * una nota de la que no se sabe nada.
 */
export function colorDeDesviacion(cents: number | null): string {
  if (cents === null) return COLOR_DESCONOCIDO;
  if (Math.abs(cents) < TOLERANCIA_AFINADA_CENTS) return COLOR_AFINADA;
  return cents > 0 ? COLOR_ALTA : COLOR_BAJA;
}
