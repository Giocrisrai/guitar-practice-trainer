/** Traducciones de datos a posiciones en pantalla. Funciones puras. */

import type { MensajeNota } from "./tipos";

/** Desviación, en cents, que corresponde a cada extremo de la aguja. */
const RANGO_AGUJA_CENTS = 50;

/** Rango de nivel que cubre la barra, en dBFS. */
const NIVEL_MINIMO_DB = -80;
const NIVEL_MAXIMO_DB = -10;

/**
 * Posición de la aguja entre -1 (grave) y 1 (aguda).
 *
 * Se satura en los extremos a propósito: pasados 50 cents ya no estás afinando esa
 * nota sino otra, y una aguja que se dispara fuera de la pantalla no informa de nada.
 */
export function posicionAguja(cents: number, maximo = RANGO_AGUJA_CENTS): number {
  return Math.max(-1, Math.min(1, cents / maximo));
}

/**
 * Estado legible de la afinación, para elegir color y texto.
 *
 * El veredicto de "afinada" lo calcula el núcleo (`nucleo/musica.esta_afinada`) y
 * viaja en el mensaje: repetir aquí la tolerancia de ±5 cents crearía dos fuentes
 * de verdad para el mismo juicio, que es justo lo que la spec §4.6 prohíbe (la
 * interfaz no calcula nada musical, solo representa lo que recibe).
 *
 * Se comprueba `estado` primero, y no `afinada`, porque en "silencio" el servidor
 * envía `afinada: false`, que ahí no significa "desafinada" sino "no hay nota".
 */
export function estadoAfinacion(
  estado: MensajeNota["estado"] | null,
  cents: number | null,
  afinada: boolean
): "afinada" | "grave" | "aguda" | "sin_nota" {
  if (estado !== "nota" || cents === null) return "sin_nota";
  if (afinada) return "afinada";
  return cents < 0 ? "grave" : "aguda";
}

/** Fracción de la barra de nivel, entre 0 y 1. */
export function fraccionNivel(
  nivelDb: number,
  minimo = NIVEL_MINIMO_DB,
  maximo = NIVEL_MAXIMO_DB
): number {
  const fraccion = (nivelDb - minimo) / (maximo - minimo);
  return Math.max(0, Math.min(1, fraccion));
}
