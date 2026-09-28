/** Instante de la pieza entre paquetes del servidor.
 *
 * El servidor manda la verdad treinta veces por segundo; el navegador dibuja
 * sesenta. Este módulo rellena el hueco: guarda el último instante conocido con
 * el momento local en que llegó, y suma el tiempo transcurrido desde entonces.
 *
 * Nunca inventa tiempo propio: en cuanto llega un paquete nuevo, ese manda. Si
 * el carril llevara su reloj, lo que ves y lo que se te puntúa se separarían
 * poco a poco, que es peor que no tener carril.
 *
 * Es un módulo puro: el tiempo local entra siempre por parámetro (`ahoraLocal`,
 * en milisegundos, como los que da `performance.now()`). Nunca se llama aquí a
 * `performance.now()` ni a `Date.now()`, que es justo lo que permite probar
 * este archivo con números fijos y sin esperas reales.
 */

/** Por encima de esta deriva se corrige de golpe en vez de repartirla. */
export const DERIVA_MAXIMA_SUAVE_S = 0.03;

/** En cuántos cuadros se reparte una deriva pequeña. */
export const CUADROS_DE_CORRECCION = 10;

/** Duración asumida de un cuadro de dibujo, para repartir la corrección suave.
 * El brief fija el reparto en "cuadros", no en segundos; como este módulo no
 * recibe la tasa real de refresco, asume los 60 fps que motivan su existencia. */
const SEGUNDOS_POR_CUADRO = 1 / 60;

export interface Reloj {
  /**
   * Registra el instante que trae un paquete del servidor y el momento local
   * (en ms) en que llegó. Ese instante manda: es la única fuente de verdad.
   */
  sincronizar(instanteServidor: number, ahoraLocal: number): void;
  /**
   * Instante de la pieza en `ahoraLocal` (ms locales), interpolado desde el
   * último paquete recibido. Nunca retrocede, ni siquiera si `ahoraLocal` va
   * hacia atrás respecto al de la última sincronización.
   */
  instante(ahoraLocal: number): number;
}

/** Estado interno: el último paquete recibido y la deriva que trajo consigo. */
interface EstadoReloj {
  /** Instante que declaró el servidor en la última sincronización. */
  instanteServidor: number;
  /** Momento local (ms) en que llegó esa sincronización. `null` si nunca hubo una. */
  horaLocalSincronizacion: number | null;
  /**
   * Diferencia, en segundos, entre lo que el servidor declaró y lo que este
   * reloj venía mostrando justo antes de esa sincronización. Se usa para
   * repartir la corrección en varios cuadros cuando es pequeña.
   */
  derivaSegundos: number;
}

const clamp01 = (x: number): number => Math.max(0, Math.min(1, x));

/** Calcula el instante que este reloj reporta en `ahoraLocal`, dado su estado. */
function calcularInstante(estado: EstadoReloj, ahoraLocal: number): number {
  if (estado.horaLocalSincronizacion === null) return 0;

  // El tiempo local nunca retrocede desde el punto de vista del reloj: si
  // `ahoraLocal` llega antes que la última sincronización, se trata como si
  // no hubiera pasado tiempo, en vez de restar y mover la pieza hacia atrás.
  const transcurridoS = Math.max(0, (ahoraLocal - estado.horaLocalSincronizacion) / 1000);
  const objetivo = estado.instanteServidor + transcurridoS;

  if (Math.abs(estado.derivaSegundos) > DERIVA_MAXIMA_SUAVE_S) {
    // Deriva grande: se corrige de golpe. Repartirla sería mentir mientras dura.
    return objetivo;
  }

  // Deriva pequeña: se reparte en CUADROS_DE_CORRECCION cuadros. El cuadro en
  // que llega el paquete ya aporta su parte (por eso el "+1"): de lo
  // contrario el primer instante tras sincronizar no mostraría corrección
  // alguna hasta el cuadro siguiente, y sí que hay que empezar a corregir ya.
  const cuadrosTranscurridos = transcurridoS / SEGUNDOS_POR_CUADRO + 1;
  const fraccionCorregida = clamp01(cuadrosTranscurridos / CUADROS_DE_CORRECCION);
  return objetivo - estado.derivaSegundos * (1 - fraccionCorregida);
}

/** Crea un reloj del carril, sin sincronizar todavía (su instante es 0). */
export function crearReloj(): Reloj {
  let estado: EstadoReloj = {
    instanteServidor: 0,
    horaLocalSincronizacion: null,
    derivaSegundos: 0,
  };

  return {
    sincronizar(instanteServidor: number, ahoraLocal: number): void {
      // La primera sincronización no tiene nada que corregir: fija la línea
      // base sin deriva, en vez de compararse con el instante 0 de partida.
      const derivaSegundos =
        estado.horaLocalSincronizacion === null
          ? 0
          : instanteServidor - calcularInstante(estado, ahoraLocal);

      estado = { instanteServidor, horaLocalSincronizacion: ahoraLocal, derivaSegundos };
    },

    instante(ahoraLocal: number): number {
      return calcularInstante(estado, ahoraLocal);
    },
  };
}
