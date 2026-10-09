/**
 * La vista escrita de una pieza: la misma `Pieza` del carril, repartida en
 * compases, como tablatura y como pentagrama. Puro y sin React ni DOM: lo que
 * puede estar mal (qué nota cae en qué compás, en qué línea de la tablatura va
 * cada traste, a qué altura se escribe cada nota) está aquí y se prueba aquí.
 * `VistaEscrita.tsx` solo pinta lo que este módulo devuelve.
 */

import type { NotaDePieza, Pieza } from "./tiposPieza";

/** Una nota dentro de su compás, con su posición en la pieza entera: es lo que
 * permite reconocer, entre las pulsaciones ya tocadas, la que le corresponde. */
export interface NotaEnCompas extends NotaDePieza {
  indice: number;
}

export interface Compas {
  /** Posición del compás en la pieza, desde 0. */
  numero: number;
  inicio_pulsos: number;
  pulsos: number;
  notas: NotaEnCompas[];
}

/** Una nota colocada en la tablatura: en qué línea (0 = la cuerda más aguda) y
 * desde qué columna de texto empieza su número de traste. */
export interface CeldaDeTablatura {
  indice: number;
  linea: number;
  columna: number;
  texto: string;
}

/** Cuántas casillas de la tablatura caben en un pulso (semicorcheas). */
export const CASILLAS_POR_PULSO = 4;
/** Ancho en caracteres de cada casilla: cabe un traste de dos cifras y un guion. */
export const ANCHO_CASILLA = 3;

/** Margen para que un error de coma flotante no cambie una nota de compás. */
const EPSILON = 1e-9;

/** Pulsos (negras) que dura un compás: 4/4 son 4, 6/8 son 3, 3/4 son 3. */
export function pulsosPorCompas(pieza: Pick<Pieza, "compas">): number {
  const [numerador, denominador] = pieza.compas;
  return (numerador * 4) / denominador;
}

/**
 * Reparte las notas en compases según el compás de la pieza. Un compás sin
 * notas sigue existiendo (un silencio es parte de la música), y las notas
 * conservan su orden.
 */
export function compasesDe(pieza: Pieza): Compas[] {
  const pulsos = pulsosPorCompas(pieza);
  const indiceDe = (inicio: number) => Math.floor(inicio / pulsos + EPSILON);

  const ultimoPorDuracion = Math.ceil(pieza.duracion_pulsos / pulsos - EPSILON);
  const ultimoPorNotas = pieza.notas.reduce(
    (maximo, nota) => Math.max(maximo, indiceDe(nota.inicio_pulsos) + 1),
    0
  );
  const cantidad = Math.max(1, ultimoPorDuracion, ultimoPorNotas);

  const compases: Compas[] = Array.from({ length: cantidad }, (_, numero) => ({
    numero,
    inicio_pulsos: numero * pulsos,
    pulsos,
    notas: [],
  }));
  pieza.notas.forEach((nota, indice) => {
    compases[indiceDe(nota.inicio_pulsos)].notas.push({ ...nota, indice });
  });
  return compases;
}

/** Casilla de la tablatura donde cae una nota, redondeando a la más cercana. */
function casillaDe(compas: Compas, nota: NotaDePieza): number {
  const casillas = Math.round(compas.pulsos * CASILLAS_POR_PULSO);
  const casilla = Math.round((nota.inicio_pulsos - compas.inicio_pulsos) * CASILLAS_POR_PULSO);
  return Math.min(Math.max(casilla, 0), casillas - 1);
}

/**
 * Dónde va cada nota del compás en la tablatura. La línea 0 es la cuerda 1 (la
 * más aguda) y la última es la cuerda más grave: la sexta queda ABAJO, que es
 * como se lee una tablatura. Una nota con la cuerda fuera de rango se descarta
 * antes que escribirla en la línea equivocada.
 */
export function celdasDeTablatura(compas: Compas, cuerdas: number): CeldaDeTablatura[] {
  return compas.notas
    .filter((nota) => nota.cuerda >= 1 && nota.cuerda <= cuerdas)
    .map((nota) => ({
      indice: nota.indice,
      linea: nota.cuerda - 1,
      // +1 por la barra de compás con la que empieza cada línea.
      columna: 1 + casillaDe(compas, nota) * ANCHO_CASILLA,
      texto: String(nota.traste),
    }));
}

/** Las líneas de la tablatura del compás, de la cuerda 1 (arriba) a la más
 * grave (abajo), en texto monoespaciado. */
export function lineaDeTablatura(compas: Compas, cuerdas: number): string[] {
  const casillas = Math.round(compas.pulsos * CASILLAS_POR_PULSO);
  const ancho = casillas * ANCHO_CASILLA;
  const lineas = Array.from({ length: cuerdas }, () => Array<string>(ancho).fill("-"));
  for (const celda of celdasDeTablatura(compas, cuerdas)) {
    [...celda.texto].forEach((caracter, desplazamiento) => {
      lineas[celda.linea][celda.columna - 1 + desplazamiento] = caracter;
    });
  }
  return lineas.map((linea) => `|${linea.join("")}|`);
}

/** Cuántas notas naturales hay antes de cada clase de altura (do = 0 ... si = 6),
 * escribiendo las alteradas como sostenidas. */
const PASO_DIATONICO = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6];
const ES_ALTERADA = [false, true, false, true, false, false, true, false, true, false, true, false];

/** La guitarra suena una octava por debajo de lo que se escribe (clave de sol 8vb). */
const OCTAVA_DE_ESCRITURA = 12;

/** Paso diatónico absoluto (do central escrito = 28) de un MIDI ya transpuesto. */
function pasoAbsoluto(midiEscrito: number): number {
  return Math.floor(midiEscrito / 12) * 7 + PASO_DIATONICO[((midiEscrito % 12) + 12) % 12];
}

/** El fa de la línea superior del pentagrama en clave de sol (fa5). */
const PASO_LINEA_SUPERIOR = pasoAbsoluto(77);

/**
 * La altura a la que se escribe una nota, en medios espacios del pentagrama
 * (un paso de la escala por unidad): 0 es la línea superior, 2 la siguiente, 8
 * la inferior. NÚMERO MENOR = MÁS AGUDA = MÁS ARRIBA, como las coordenadas y de
 * una pantalla. Los valores negativos o mayores que 8 caen fuera del pentagrama
 * y piden líneas adicionales.
 */
export function alturaEnPentagrama(midi: number): number {
  return PASO_LINEA_SUPERIOR - pasoAbsoluto(midi + OCTAVA_DE_ESCRITURA);
}

/** Si la nota se escribe con un sostenido delante. */
export function llevaSostenido(midi: number): boolean {
  return ES_ALTERADA[((midi % 12) + 12) % 12];
}

/** Las alturas pares fuera del pentagrama por las que pasa una línea adicional
 * para llegar hasta la nota. Vacío si la nota cae dentro. */
export function lineasAdicionales(altura: number): number[] {
  const lineas: number[] = [];
  for (let a = -2; a >= altura; a -= 2) lineas.push(a);
  for (let a = 10; a <= altura; a += 2) lineas.push(a);
  return lineas;
}
