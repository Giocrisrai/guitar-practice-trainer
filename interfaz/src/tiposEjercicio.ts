/** Formas exactas que llegan del servidor para los ejercicios. Espejo de nucleo/ejercicios. */

import type { Posicion } from "./tipos";

/** Una nota pedida por el ejercicio, tal y como la manda el servidor. */
export interface NotaEjercicio {
  midi: number;
  nombre: string;
  posiciones: Posicion[];
  pulsos: number;
  referencia_midi: number | null;
}

/**
 * Un acorde pedido por el ejercicio. Es el hermano de `NotaEjercicio`, no su
 * generalización: `posiciones` aquí son las cuerdas que se tocan A LA VEZ, no
 * alternativas entre las que el alumno elige.
 */
export interface AcordeEjercicio {
  nombre: string;
  posiciones: Posicion[];
  midis: number[];
  nombres: string[];
  pulsos: number;
}

/**
 * Un acorde del catálogo, tal y como lo manda `GET /api/ejercicios/acordes`:
 * la misma forma que `AcordeEjercicio` más la CLAVE con la que se pide.
 *
 * La clave es un identificador (`do`, `la_menor`) y no se muestra nunca: lo que
 * se lee es `nombre`. Las dos cosas viajan juntas desde el servidor para que
 * ninguna pantalla tenga que traducir una en la otra, que es la tabla escrita a
 * mano que este endpoint existe para borrar.
 */
export interface AcordeDelCatalogo extends AcordeEjercicio {
  clave: string;
}

export interface EjercicioServidor {
  clave: string;
  nombre: string;
  descripcion: string;
  notas: NotaEjercicio[];
  /** Vacío en un ejercicio de notas. Un ejercicio trae una cosa o la otra. */
  acordes: AcordeEjercicio[];
  tempo: number;
  perfil: string;
}

export interface EvaluacionServidor {
  indice: number;
  total: number;
  intentos: number;
  ayuda_visible: boolean;
  completado: boolean;
  nota_actual: NotaEjercicio | null;
  ultimo_fallo: string | null;
}

/** Una nota ya resuelta, tal y como aparece en el informe final. */
export interface IntentoNotaServidor {
  indice: number;
  midi: number;
  nombre: string;
  intentos: number;
  cents: number | null;
  instante: number | null;
  ayuda_mostrada: boolean;
}

export interface InformeServidor {
  ejercicio: string;
  completado: boolean;
  notas: IntentoNotaServidor[];
  aciertos_a_la_primera: number;
  desviacion_mediana_cents: number | null;
  regularidad_ms: number | null;
  /** Notas con 3 intentos o mas, ya decididas por el nucleo (INTENTOS_NOTA_DIFICIL). */
  notas_dificiles: IntentoNotaServidor[];
}

/** El avance de un ejercicio de acordes. Hermano de `EvaluacionServidor`. */
export interface EvaluacionCambiosServidor {
  indice: number;
  total: number;
  intentos: number;
  ayuda_visible: boolean;
  completado: boolean;
  acorde_actual: AcordeEjercicio | null;
  /** Los MIDI del acorde actual que no están sonando, de grave a agudo. */
  faltan: number[];
  /** Segundos que costó el último cambio logrado. `null` en el primer acorde. */
  ultimo_cambio_s: number | null;
}

/** Un acorde ya resuelto, tal y como aparece en el informe de cambios. */
export interface IntentoAcordeServidor {
  indice: number;
  nombre: string;
  intentos: number;
  logrado: boolean;
  cambio_s: number | null;
  faltaron: number[];
  ayuda_mostrada: boolean;
}

export interface InformeCambiosServidor {
  ejercicio: string;
  completado: boolean;
  acordes: IntentoAcordeServidor[];
  logrados: number;
  a_la_primera: number;
  /**
   * La cifra de cabecera: la MEDIANA de los tiempos de cambio. `null` cuando no
   * hubo ningún cambio medido, que no es lo mismo que cero.
   */
  tiempo_medio_de_cambio_s: number | null;
  cambio_mas_lento_s: number | null;
  /** MIDI que faltaron más veces, de más a menos. Ya ordenados por el núcleo. */
  cuerdas_problematicas: number[];
}

/** Lo que comparten los dos tipos de estado, de acordes y de notas. */
interface EstadoEjercicioComun {
  ejercicio: EjercicioServidor | null;
  /** Si el metronomo llego a sonar. Sigue siendo true mientras esta pausado. */
  metronomo: boolean;
  /**
   * Pausado por falta de senal (spec §5). Va aparte de `metronomo` a proposito:
   * `metronomo` no cambia de significado al pausarse, la pausa se lee aqui.
   */
  metronomo_pausado: boolean;
  /**
   * Si el usuario pidio metronomo al arrancar. Sin este campo, `metronomo:
   * false` no distingue "no habia salida de audio" (hay que avisar, spec §5)
   * de "el usuario lo desmarco" (no hay nada que avisar).
   */
  metronomo_pedido: boolean;
}

/**
 * Lo que emite /api/ejercicios/estado y /ws/ejercicios.
 *
 * Es una unión discriminada por `es_de_acordes` y no un objeto con los campos de
 * los dos tipos, porque `evaluacion` e `informe` tienen formas DISTINTAS en cada
 * caso: un ejercicio de acordes no tiene `nota_actual` ni cents, y uno de notas
 * no tiene `faltan` ni tiempo de cambio. Con la unión, leer el campo equivocado
 * es un error de compilación en vez de un `undefined` en pantalla.
 */
export interface EstadoEjercicioNotas extends EstadoEjercicioComun {
  es_de_acordes: false;
  evaluacion: EvaluacionServidor | null;
  informe: InformeServidor | null;
}

export interface EstadoEjercicioAcordes extends EstadoEjercicioComun {
  es_de_acordes: true;
  evaluacion: EvaluacionCambiosServidor | null;
  informe: InformeCambiosServidor | null;
}

export type EstadoEjercicio = EstadoEjercicioNotas | EstadoEjercicioAcordes;

/** Una familia de ejercicios, tal y como la describe /api/ejercicios/familias. */
export interface FamiliaEjercicio {
  clave: string;
  nombre: string;
  descripcion: string;
  tipos: string[];
  parametros: string[];
}

/** Una cuerda del instrumento activo, tal y como la manda /api/ejercicios/instrumento. */
export interface CuerdaInstrumento {
  numero: number;
  nota: string;
}

/**
 * El instrumento con el que se van a generar los ejercicios, tal y como lo
 * publica /api/ejercicios/instrumento: el perfil de afinacion ACTIVO en el
 * afinador, no todos los perfiles que el servidor conoce.
 */
export interface InstrumentoEjercicio {
  clave: string;
  nombre: string;
  trastes: number;
  cuerdas: CuerdaInstrumento[];
}
