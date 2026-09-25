/** Traducciones de datos a pantalla para los ejercicios. Funciones puras. */

/** Fraccion completada del ejercicio, entre 0 y 1. */
export function fraccionProgreso(indice: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(1, indice / total));
}

/**
 * Texto del ultimo fallo, o null si no lo hubo.
 *
 * Decir que sono ademas de que se esperaba es lo que convierte un "mal" en una
 * correccion util: el usuario ve si se equivoco de cuerda, de traste o de octava.
 */
export function mensajeDeFallo(esperada: string | null, sonada: string | null): string | null {
  if (esperada === null || sonada === null) return null;
  return `Esperaba ${esperada} y sono ${sonada}`;
}

/** Resumen en una frase de como fue el ejercicio. */
export function calificacion(aciertosALaPrimera: number, total: number): string {
  if (total <= 0) return "Sin notas";
  if (aciertosALaPrimera === total) return "Perfecto: todas a la primera";
  const proporcion = aciertosALaPrimera / total;
  if (proporcion >= 0.8) return "Muy bien: casi todas a la primera";
  if (proporcion >= 0.5) return "Bien, con algunas que costaron";
  return "Hay material para practicar";
}
