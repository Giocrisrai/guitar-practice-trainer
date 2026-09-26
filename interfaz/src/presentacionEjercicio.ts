/** Traducciones de datos a pantalla para los ejercicios. Funciones puras. */

import type { PerfilAfinacion, Posicion } from "./tipos";
import type { EjercicioServidor, InformeServidor } from "./tiposEjercicio";

/**
 * Nombres de las doce clases de nota, en el orden del estándar MIDI.
 *
 * No es una decisión musical de este proyecto (eso vive en el núcleo): es la
 * tabla del propio estándar, la misma que usa `nucleo/musica.py`, y hace falta
 * aquí solo para poder ofrecer la raíz por nombre en vez de por número MIDI. El
 * día que el servidor publique los valores admisibles de cada parámetro, este
 * par de funciones se borra.
 */
const NOMBRES_NOTAS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

/** Nombre en notación científica: 40 -> "E2". */
export function nombreDeMidi(midi: number): string {
  const octava = Math.floor(midi / 12) - 1;
  return `${NOMBRES_NOTAS[((midi % 12) + 12) % 12]}${octava}`;
}

/** Número MIDI de un nombre en notación científica: "E2" -> 40. null si no se entiende. */
export function midiDeNombre(nombre: string): number | null {
  const partes = /^([A-G]#?)(-?\d+)$/.exec(nombre.trim());
  if (partes === null) return null;
  const clase = NOMBRES_NOTAS.indexOf(partes[1]);
  if (clase < 0) return null;
  return clase + 12 * (Number(partes[2]) + 1);
}

/**
 * Raíces que se pueden ofrecer, derivadas de los perfiles del servidor.
 *
 * El rango no se escribe aquí: va de la cuerda más grave de cualquier perfil a
 * la más aguda más sus trastes, todo dato que el servidor publica en
 * `/api/perfiles`. Elegir a mano "de C2 a C6" sería inventar un rango musical en
 * la interfaz, que es justo el defecto que este proyecto ya arrastró tres veces.
 */
export function raicesElegibles(perfiles: PerfilAfinacion[]): { midi: number; nombre: string }[] {
  const midis: number[] = [];
  let trastes = 0;
  for (const perfil of perfiles) {
    trastes = Math.max(trastes, perfil.trastes);
    for (const cuerda of perfil.cuerdas) {
      const midi = midiDeNombre(cuerda.nota);
      if (midi !== null) midis.push(midi);
    }
  }
  if (midis.length === 0) return [];
  const desde = Math.min(...midis);
  const hasta = Math.max(...midis) + trastes;
  return Array.from({ length: hasta - desde + 1 }, (_, i) => ({
    midi: desde + i,
    nombre: nombreDeMidi(desde + i),
  }));
}

/** Números de cuerda que existen en algún perfil del servidor, de aguda a grave. */
export function cuerdasElegibles(perfiles: PerfilAfinacion[]): number[] {
  const numeros = new Set<number>();
  for (const perfil of perfiles) {
    for (const cuerda of perfil.cuerdas) numeros.add(cuerda.numero);
  }
  return [...numeros].sort((a, b) => a - b);
}

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

/**
 * Desviacion de una nota del informe, en palabras.
 *
 * `cents === null` significa que la nota NO se acerto; `0.0` significa acertada y
 * perfectamente afinada. Son cosas distintas y aqui se dicen distintas: tratar
 * el null como un cero pintaria como impecable justo la nota que nunca salio.
 */
export function textoDesviacion(cents: number | null): string {
  if (cents === null) return "no acertada";
  const signo = cents > 0 ? "+" : "";
  return `${signo}${cents.toFixed(1)} cents`;
}

/**
 * Posiciones de las notas que ya se acertaron, para la capa tenue del mastil.
 *
 * Es un cruce de dos arrays que el servidor ya publica —el informe dice que
 * notas se acertaron y con que indice, y el ejercicio dice donde cae cada
 * indice—, no un calculo propio. Una nota puede valer en varias posiciones y el
 * servidor no publica en cual se toco, asi que se marcan todas las que valian.
 */
export function posicionesAcertadas(
  ejercicio: EjercicioServidor | null,
  informe: InformeServidor | null
): Posicion[] {
  if (ejercicio === null || informe === null) return [];
  const posiciones: Posicion[] = [];
  for (const intento of informe.notas) {
    if (intento.cents === null) continue;
    const nota = ejercicio.notas[intento.indice];
    if (nota !== undefined) posiciones.push(...nota.posiciones);
  }
  return posiciones;
}

/**
 * Resumen en una frase de como fue el ejercicio.
 *
 * Los 0,8 y 0,5 son umbrales de PRESENTACION: deciden el adjetivo de una frase y
 * nada mas. Cualquier umbral que afecte a la CORRECCION —cuantos intentos hacen
 * dificil una nota, cuantos fallos abren la ayuda, cuantos cents siguen siendo
 * acierto— vive en el nucleo y llega ya decidido en el payload. Esa frontera ya
 * se cruzo dos veces en este proyecto (la tolerancia de afinacion y el umbral de
 * notas dificiles acabaron migrando al nucleo): si algun dia uno de estos dos
 * numeros empieza a cambiar un veredicto, su sitio es el nucleo, no este archivo.
 */
export function calificacion(aciertosALaPrimera: number, total: number): string {
  if (total <= 0) return "Sin notas";
  if (aciertosALaPrimera === total) return "Perfecto: todas a la primera";
  const proporcion = aciertosALaPrimera / total;
  if (proporcion >= 0.8) return "Muy bien: casi todas a la primera";
  if (proporcion >= 0.5) return "Bien, con algunas que costaron";
  return "Hay material para practicar";
}
