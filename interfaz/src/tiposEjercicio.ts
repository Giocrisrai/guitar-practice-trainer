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

export interface EjercicioServidor {
  clave: string;
  nombre: string;
  descripcion: string;
  notas: NotaEjercicio[];
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

/** Lo que emite /api/ejercicios/estado y /ws/ejercicios. */
export interface EstadoEjercicio {
  ejercicio: EjercicioServidor | null;
  evaluacion: EvaluacionServidor | null;
  informe: InformeServidor | null;
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
