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

/** Por encima de esta deriva se corrige casi de golpe en vez de repartirla. */
export const DERIVA_MAXIMA_SUAVE_S = 0.03;

/** En cuántos cuadros se reparte una deriva pequeña. */
export const CUADROS_DE_CORRECCION = 10;

/** Duración asumida de un cuadro de dibujo, para repartir la corrección suave.
 * El brief fija el reparto en "cuadros", no en segundos; como este módulo no
 * recibe la tasa real de refresco, asume los 60 fps que motivan su existencia. */
const SEGUNDOS_POR_CUADRO = 1 / 60;

/**
 * Qué tan deprisa crece la corrección inmediata una vez la deriva supera
 * DERIVA_MAXIMA_SUAVE_S. Con este valor, el doble del umbral ya corrige más del
 * 99.999 % en el mismo instante de sincronizar -indistinguible en la práctica
 * de "de golpe"-, pero la curva es continua: no hay una deriva exacta en la que
 * la corrección salte de un plumazo de "unos milisegundos" a "toda de golpe".
 * Eso es lo que evita el escalón justo en el umbral, que se notaría tanto como
 * el propio tirón que esta rampa existe para evitar.
 */
const PENDIENTE_TRANSICION = 15;

/** Opciones para ajustar el comportamiento del reloj sin tocar las constantes
 * del módulo completo. Con `opciones` vacío u omitido, el reloj usa
 * DERIVA_MAXIMA_SUAVE_S y CUADROS_DE_CORRECCION tal cual. */
export interface OpcionesReloj {
  /** Sustituye a DERIVA_MAXIMA_SUAVE_S para este reloj en particular. */
  derivaMaximaSuaveS?: number;
  /** Sustituye a CUADROS_DE_CORRECCION para este reloj en particular. */
  cuadrosDeCorreccion?: number;
}

export interface Reloj {
  /**
   * Registra el instante que trae un paquete del servidor y el momento local
   * (en ms) en que llegó. Ese instante manda: es la única fuente de verdad.
   */
  sincronizar(instanteServidor: number, ahoraLocal: number): void;
  /**
   * Instante de la pieza en `ahoraLocal` (ms locales), interpolado desde el
   * último paquete recibido. Nunca retrocede: ni cuando `ahoraLocal` va hacia
   * atrás respecto al de la última sincronización, ni cuando el propio
   * servidor manda un instante menor que el que este reloj ya mostró (ocurre
   * al recuperarse de un corte de señal). En ese segundo caso el cabezal se
   * queda quieto hasta que el avance del servidor lo alcanza otra vez.
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
  /**
   * El instante más alto que este reloj ha mostrado o prometido hasta ahora.
   * Solo puede crecer. Si un paquete nuevo trae un instante por debajo de este
   * piso -el servidor recuperándose de un corte, por ejemplo, hasta 0,27 s
   * hacia atrás-, `instante()` se queda anclado aquí en vez de saltar hacia
   * atrás: una nota que retrocede en el carril es peor que cualquier tirón.
   */
  pisoS: number;
}

const clamp01 = (x: number): number => Math.max(0, Math.min(1, x));

/**
 * Fracción de la deriva ya corregida en `transcurridoS`, para una deriva cuya
 * magnitud es `r` veces DERIVA_MAXIMA_SUAVE_S.
 *
 * Es una única curva, sin ramas: en r=1 (justo en el umbral) vale lo mismo que
 * el resto de la rampa suave (1/CUADROS_DE_CORRECCION en el cuadro en que llega
 * el paquete), y por encima de r=1 crece deprisa hacia 1 para que una deriva
 * grande se siga corrigiendo casi de golpe -disimularla sería mentir varios
 * segundos-, pero sin el escalón que tenía una rama "de golpe" separada.
 */
function fraccionCorregida(r: number, transcurridoS: number, cuadrosDeCorreccion: number): number {
  const fraccionInicial =
    r <= 1 ? 1 / cuadrosDeCorreccion : 1 - (1 - 1 / cuadrosDeCorreccion) * Math.exp(-(r - 1) * PENDIENTE_TRANSICION);
  const cuadrosDesdeElInicial = transcurridoS / SEGUNDOS_POR_CUADRO / cuadrosDeCorreccion;
  return clamp01(fraccionInicial + cuadrosDesdeElInicial);
}

/** Calcula el instante que este reloj reporta en `ahoraLocal`, dado su estado. */
function calcularInstante(
  estado: EstadoReloj,
  ahoraLocal: number,
  derivaMaximaSuaveS: number,
  cuadrosDeCorreccion: number
): number {
  if (estado.horaLocalSincronizacion === null) return 0;

  // El tiempo local nunca retrocede desde el punto de vista del reloj: si
  // `ahoraLocal` llega antes que la última sincronización, se trata como si
  // no hubiera pasado tiempo, en vez de restar y mover la pieza hacia atrás.
  const transcurridoS = Math.max(0, (ahoraLocal - estado.horaLocalSincronizacion) / 1000);
  const objetivo = estado.instanteServidor + transcurridoS;

  const r = derivaMaximaSuaveS > 0 ? Math.abs(estado.derivaSegundos) / derivaMaximaSuaveS : Infinity;
  const fraccion = fraccionCorregida(r, transcurridoS, cuadrosDeCorreccion);
  const base = objetivo - estado.derivaSegundos * (1 - fraccion);

  // El piso rige siempre, no solo cuando la deriva es grande: es lo que impide
  // que el cabezal retroceda cuando el servidor manda un instante menor que el
  // que ya se venía mostrando.
  return Math.max(estado.pisoS, base);
}

/** Crea un reloj del carril, sin sincronizar todavía (su instante es 0). */
export function crearReloj(opciones?: OpcionesReloj): Reloj {
  const derivaMaximaSuaveS = opciones?.derivaMaximaSuaveS ?? DERIVA_MAXIMA_SUAVE_S;
  const cuadrosDeCorreccion = opciones?.cuadrosDeCorreccion ?? CUADROS_DE_CORRECCION;

  let estado: EstadoReloj = {
    instanteServidor: 0,
    horaLocalSincronizacion: null,
    derivaSegundos: 0,
    pisoS: 0,
  };

  return {
    sincronizar(instanteServidor: number, ahoraLocal: number): void {
      if (estado.horaLocalSincronizacion === null) {
        // La primera sincronización no tiene nada que corregir ni piso previo
        // que respetar: fija la línea base directamente.
        estado = { instanteServidor, horaLocalSincronizacion: ahoraLocal, derivaSegundos: 0, pisoS: instanteServidor };
        return;
      }

      // Lo que este reloj venía mostrando justo antes de este paquete, con el
      // estado ANTERIOR: es la referencia tanto para medir la deriva como para
      // subir el piso, antes de que el nuevo instanteServidor lo sustituya.
      const valorAntes = calcularInstante(estado, ahoraLocal, derivaMaximaSuaveS, cuadrosDeCorreccion);
      const pisoS = Math.max(estado.pisoS, valorAntes);
      const derivaSegundos = instanteServidor - valorAntes;

      estado = { instanteServidor, horaLocalSincronizacion: ahoraLocal, derivaSegundos, pisoS };
    },

    instante(ahoraLocal: number): number {
      return calcularInstante(estado, ahoraLocal, derivaMaximaSuaveS, cuadrosDeCorreccion);
    },
  };
}
