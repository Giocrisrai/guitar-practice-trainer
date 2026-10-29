import type { CompasDelInforme } from "./tiposEstudio";

/**
 * El desfase medio dicho en palabras: «40 ms tarde», «40 ms pronto».
 *
 * Un número con signo no es un diagnóstico. `null` quiere decir que en este
 * compás no se midió ningún desfase, que no es lo mismo que cero: no se inventa
 * nada y la celda queda vacía. Un desfase que redondea a 0 ms es «a tiempo».
 */
export function textoDelDesfase(desfaseS: number | null): string {
  if (desfaseS === null) return "";
  const milisegundos = Math.round(Math.abs(desfaseS) * 1000);
  if (milisegundos === 0) return "a tiempo";
  return `${milisegundos} ms ${desfaseS > 0 ? "tarde" : "pronto"}`;
}

/**
 * Lo limpio sobre lo medible de los compases SIN acordes, o `null` si no hay
 * ninguno. Es la misma cuenta que hace el núcleo (`proporcion_limpia`):
 *
 *   sum(limpias) / sum(notas_medibles * repeticiones)   para los compases sin acordes
 *
 * Los contadores del informe suman las vueltas del bucle, así que el
 * denominador se multiplica por `repeticiones`; y los compases con acordes
 * quedan fuera porque el detector es monofónico y de un acorde solo se mide una
 * nota: contarlos haría que cualquier canción de Guitar Pro saliera fallada.
 */
export function limpiasDelInforme(
  compases: CompasDelInforme[],
  repeticiones: number
): { limpias: number; medibles: number } | null {
  let limpias = 0;
  let medibles = 0;
  for (const compas of compases) {
    if (compas.tiene_acordes) continue;
    limpias += compas.limpias;
    medibles += compas.notas_medibles * repeticiones;
  }
  return medibles === 0 ? null : { limpias, medibles };
}
