/**
 * Formas que llegan del servidor para practicar una pieza con compases, bucles y
 * tempo ajustable (etapa 3c). Espejo de `nucleo/piezas/estudio.py` y de lo que le
 * añade `SesionCarril` (servidor/piezas.py).
 *
 * La interfaz NO convierte pulsos en compases: esa cuenta es del núcleo y viaja
 * hecha (`compas_en_curso`, `total_de_compases`, `secciones_en_compases`). Si
 * hiciera falta una fórmula de pulsos a compases aquí, es que falta un dato en el
 * paquete.
 */
import type { EstadoCarril, Pieza } from "./tiposPieza";

/**
 * El paquete del WebSocket `/ws/piezas`: el `a_dict()` de `EstadoEstudio` MÁS lo
 * que el servidor le añade encima (`pausado`, `arranque`, `click_sonando` y
 * `factor_sugerido`). Por eso extiende `EstadoCarril`, que ya trae `instante_s`,
 * `indice_actual`, `total`, `completado`, `tocadas`, `pausado` y `arranque`.
 *
 * Ojo con dos nombres que se parecen:
 * - `completado` significa «se acabó el TRAMO», no «se acabó la pieza»: el núcleo
 *   lo sobrescribe a propósito (`tramo_terminado` o carril completado).
 * - `pausado` es falta de señal (lo pone el servidor); `en_pausa` es la pausa que
 *   pidió el usuario. No son lo mismo y no se sustituyen.
 */
export interface EstadoEstudio extends EstadoCarril {
  instante_pulsos: number;
  compas_en_curso: number;
  total_de_compases: number;
  primer_compas: number;
  ultimo_compas: number;
  repeticion: number;
  cuenta_atras_restante_s: number;
  factor_tempo: number;
  /** Tempo de la pieza por `factor_tempo`: el que marca el reloj que se oye. */
  tempo_efectivo: number;
  en_bucle: boolean;
  /** Lo que se PIDIÓ, no lo que suena: ver `click_sonando`. */
  con_click: boolean;
  tempo_automatico: boolean;
  en_pausa: boolean;
  compas_variable: boolean;
  ritmo_aproximado: boolean;
  tramo_terminado: boolean;
  /** Lo que SUENA, no lo que se pidió: `false` sin salida de audio aunque el plan
   * diga `con_click`. */
  click_sonando: boolean;
  /** Tempo que el servidor propone tras una racha buena, o `null` si no hay nada
   * que sugerir (casi siempre). Es una propuesta: nunca se aplica sola. */
  factor_sugerido: number | null;
}

/** Una sección de la pieza ya convertida en rango de compases (base 1). */
export interface SeccionEnCompases {
  nombre: string;
  primer_compas: number;
  ultimo_compas: number;
}

/**
 * Lo que devuelve `POST /api/piezas/iniciar`: la pieza, sus secciones en compases
 * y el estado inicial.
 */
export interface RespuestaIniciarEstudio extends EstadoEstudio {
  pieza: Pieza;
  secciones_en_compases: SeccionEnCompases[];
}

/** Lo que devuelve `GET /api/piezas/pieza`: igual, pero `pieza` vale `null` si no
 * hay nada en marcha (no es un error). */
export interface RespuestaPiezaEnMarcha extends EstadoEstudio {
  pieza: Pieza | null;
  secciones_en_compases: SeccionEnCompases[];
}

/** El plan de práctica que se manda al servidor; todo es opcional. */
export interface Plan {
  primer_compas?: number;
  ultimo_compas?: number | null;
  factor_tempo?: number;
  en_bucle?: boolean;
  compases_de_cuenta_atras?: number;
  con_click?: boolean;
  tempo_automatico?: boolean;
}

/** Cómo fue un compás en la pasada, tal y como lo calcula el núcleo. */
export interface CompasDelInforme {
  numero: number;
  notas_escritas: number;
  notas_medibles: number;
  acertadas: number;
  a_tiempo: number;
  pronto: number;
  tarde: number;
  /** Notas acertadas Y a tiempo A LA VEZ, contadas nota a nota: una nota tocada a
   * tiempo pero de otra altura no es limpia. Es lo que entra en la proporción que
   * decide el tempo (`proporcion_limpia`, estudio.py). */
  limpias: number;
  desfase_medio_s: number | null;
  tiene_acordes: boolean;
}

export interface Informe {
  compases: CompasDelInforme[];
  ritmo_aproximado: boolean;
  compas_variable: boolean;
  factor_tempo: number;
  /** Cuántas vueltas del bucle lleva sumadas este informe en sus contadores. La
   * proporción limpia divide entre `medibles * repeticiones`. */
  repeticiones: number;
}

export interface Historial {
  pasadas: number;
  peores_compases: { compas: number; falladas: number; contadas: number }[];
}
