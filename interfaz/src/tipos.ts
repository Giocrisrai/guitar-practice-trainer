/** Formas exactas que llegan del servidor. Espejo de los dataclasses de Python. */

export interface Posicion {
  cuerda: number;
  traste: number;
}

export interface MensajeNota {
  estado: "nota" | "silencio" | "error";
  frecuencia: number;
  nota: string | null;
  cents: number | null;
  confianza: number;
  nivel_db: number;
  posiciones: Posicion[];
  cuerda_objetivo: number | null;
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

export interface Diagnostico {
  estado: "ok" | "sin_permiso" | "sin_dispositivo" | "sin_senal" | "otro_dispositivo";
  mensaje: string;
  accion: string;
  dispositivos: { indice: number; nombre: string }[];
}
