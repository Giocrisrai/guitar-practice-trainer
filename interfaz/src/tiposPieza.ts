/** Formas exactas que llegan del servidor para las piezas. Espejo de nucleo/piezas. */

/** Una nota de la pieza, con su sitio en el mástil y su sitio en el tiempo.
 * Tal y como la manda `NotaEnPieza.a_dict()` (nucleo/piezas/modelo.py). */
export interface NotaDePieza {
  midi: number;
  nombre: string;
  cuerda: number;
  traste: number;
  inicio_pulsos: number;
  duracion_pulsos: number;
}

/**
 * La pieza entera: la manda `GET /api/piezas/desde-ejercicio` y también viaja
 * dentro de la respuesta de `POST /api/piezas/iniciar` (bajo la clave `pieza`).
 * El WebSocket `/ws/piezas` NUNCA la manda: viajó una sola vez al iniciar, y
 * repetirla treinta veces por segundo desperdiciaría el canal en notas que no
 * cambian (`Pieza.a_dict()`, nucleo/piezas/modelo.py).
 */
export interface Pieza {
  nombre: string;
  perfil: string;
  tempo: number;
  compas: [number, number];
  duracion_pulsos: number;
  notas: NotaDePieza[];
}

/** Cómo llegó una pulsación respecto al instante escrito de su nota.
 * La decide el núcleo (`SeguidorPieza._clasificar`); la interfaz no la deduce. */
export type Clasificacion = "a_tiempo" | "pronto" | "tarde";

/**
 * Una pulsación ya adjudicada a una nota de la pieza, tal y como la manda
 * `NotaTocada.a_dict()` (nucleo/piezas/seguimiento.py).
 *
 * `cents`, `desfase_s` y `clasificacion` valen `null` juntos cuando la
 * pulsación llegó sin instante: no se supo cuándo empezó, así que no hay ni
 * desviación ni desfase ni clasificación que atribuirle. `null` NO significa
 * "cero" ni "a tiempo": significa que no se supo. Confundirlo pintaría en
 * verde, o marcaría a tiempo, una nota de la que no sabemos nada.
 */
export interface NotaTocada {
  indice: number;
  midi: number;
  nombre: string;
  cents: number | null;
  desfase_s: number | null;
  clasificacion: Clasificacion | null;
  acertada: boolean;
}

/**
 * Lo que manda `GET /api/piezas/estado` y el WebSocket `/ws/piezas`: el
 * estado del carril, SIN la pieza. `pausado` lo añade el servidor (falta de
 * señal), no el núcleo: `SesionCarril.estado()`, servidor/piezas.py.
 *
 * `indice_actual` es la última nota que ya empezó según el reloj de la pieza;
 * para saber si terminó se mira `completado`, no el índice.
 *
 * `tocadas` solo trae las pulsaciones que se pudieron adjudicar. Una nota que
 * nadie tocó no aparece aquí.
 */
export interface EstadoCarril {
  instante_s: number;
  indice_actual: number;
  total: number;
  completado: boolean;
  tocadas: NotaTocada[];
  pausado: boolean;
}

/**
 * Lo que devuelve `POST /api/piezas/iniciar`: la pieza entera, de una vez,
 * más el mismo estado inicial que después repite el WebSocket
 * (`SesionCarril.iniciar()`, servidor/piezas.py).
 */
export interface RespuestaIniciarPieza extends EstadoCarril {
  pieza: Pieza;
}
