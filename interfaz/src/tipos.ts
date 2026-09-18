/** Formas exactas que llegan del servidor. Espejo de los dataclasses de Python. */

export interface Posicion {
  cuerda: number;
  traste: number;
}

export interface MensajeNota {
  /** El servidor solo emite "nota" o "silencio"; los fallos viajan por /api/diagnostico. */
  estado: "nota" | "silencio";
  frecuencia: number;
  nota: string | null;
  cents: number | null;
  confianza: number;
  nivel_db: number;
  posiciones: Posicion[];
  cuerda_objetivo: number | null;
  /** Veredicto del núcleo. Solo significa algo cuando estado es "nota". */
  afinada: boolean;
  latencia_ms?: number;
}

export interface Modulo {
  clave: string;
  nombre: string;
  descripcion: string;
  icono: string;
  disponible: boolean;
}

export interface Cuerda {
  numero: number;
  nota: string;
  frecuencia: number;
}

export interface PerfilAfinacion {
  clave: string;
  nombre: string;
  trastes: number;
  cuerdas: Cuerda[];
}

/** Una entrada de audio del sistema, tal y como la emite el servidor. */
export interface DispositivoEntrada {
  indice: number;
  nombre: string;
  canales_entrada: number;
  frecuencia_muestreo: number;
}

export interface Diagnostico {
  estado: "ok" | "sin_permiso" | "sin_dispositivo" | "sin_senal" | "otro_dispositivo";
  mensaje: string;
  accion: string;
  dispositivos: DispositivoEntrada[];
}

/** Ajustes que el usuario elige y que el servidor persiste. */
export interface Configuracion {
  dispositivo: number | null;
  perfil: string;
  ganancia: number;
  umbral_ruido_dbfs: number;
  referencia_a4: number;
  confianza_minima: number;
  detector: string;
}

/** Cuerpo de la respuesta de PUT /api/config. */
export interface RespuestaConfig {
  configuracion: Configuracion;
  diagnostico: Diagnostico;
}
