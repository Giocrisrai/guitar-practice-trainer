/**
 * Formas que llegan del servidor para las piezas, de `nucleo/piezas`.
 *
 * **Espejo COMPLETO.** Cada interfaz de este archivo declara todos los campos que
 * manda el servidor. Antes `Pieza` omitía cinco a propósito, porque nada los leía;
 * la etapa 3c los consume y por eso ya están. Lo que es exacto es el NOMBRE y el
 * TIPO: si el núcleo renombra un campo, lo que hay que cambiar es esta línea.
 */

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
 * La pieza entera: la manda `POST /api/piezas/desde-ejercicio` (con cuerpo) y también viaja
 * dentro de la respuesta de `POST /api/piezas/iniciar` (bajo la clave `pieza`).
 * El WebSocket `/ws/piezas` NUNCA la manda: viajó una sola vez al iniciar, y
 * repetirla treinta veces por segundo desperdiciaría el canal en notas que no
 * cambian (`Pieza.a_dict()`, nucleo/piezas/modelo.py).
 *
 * `ritmo_aproximado`, `tempo_variable`, `compas_variable` y `casillas_de_repeticion`
 * dicen en qué se aparta de la partitura lo que se pudo leer; además llegan ya
 * convertidos en frases dentro de `avisos` (`_avisos_de`, servidor/app.py), que es
 * lo que pintan las pantallas de canciones. `secciones` da el inicio de cada una en
 * pulsos: para saber en qué compases caen NO se calcula aquí, el servidor lo manda
 * hecho (`secciones_en_compases`, ver `tiposEstudio.ts`).
 */
export interface Pieza {
  nombre: string;
  perfil: string;
  tempo: number;
  compas: [number, number];
  duracion_pulsos: number;
  notas: NotaDePieza[];
  secciones: { nombre: string; inicio_pulsos: number }[];
  ritmo_aproximado: boolean;
  tempo_variable: boolean;
  compas_variable: boolean;
  casillas_de_repeticion: boolean;
}

/** Cómo llegó una pulsación respecto al instante escrito de su nota.
 * La decide el núcleo (`SeguidorPieza._clasificar`); la interfaz no la deduce. */
export type Clasificacion = "a_tiempo" | "pronto" | "tarde";

/**
 * Una pulsación ya adjudicada a una nota de la pieza, tal y como la manda
 * `NotaTocada.a_dict()` (nucleo/piezas/seguimiento.py).
 *
 * `desfase_s` y `clasificacion` valen `null` juntos cuando la pulsación llegó
 * sin instante: no se supo cuándo empezó (`SeguidorPieza`, seguimiento.py).
 * `cents` es independiente de eso: sale de `pulsacion.cents`, que es
 * `float | None` por motivos propios, así que una pulsación sin instante puede
 * traer cents válidos, y una con instante puede traerlos nulos. No se deduce
 * uno del otro. En ningún caso `null` significa "cero" ni "a tiempo": significa
 * que ese dato no se supo, y pintarlo como afinado o puntual sería mentir.
 *
 * `acertada` y `afinada` son los dos VEREDICTOS, y los dos los decide el núcleo:
 * `acertada` compara la altura con la nota escrita y `afinada` aplica a `cents`
 * la misma regla que el resto del programa (`nucleo.musica.esta_afinada`). La
 * interfaz los consume; no vuelve a comparar MIDIs ni a copiarse el umbral de
 * cents. `afinada` es `null` cuando `cents` lo es: no se supo, que no es ni
 * afinada ni desafinada.
 */
export interface NotaTocada {
  indice: number;
  midi: number;
  nombre: string;
  cents: number | null;
  desfase_s: number | null;
  clasificacion: Clasificacion | null;
  acertada: boolean;
  afinada: boolean | null;
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
  /**
   * Qué arranque del carril describe este estado: un contador que el servidor
   * sube con cada `iniciar` y que no reutiliza nunca (`SesionCarril._arranque`).
   * Vale 0 cuando no hay pieza, que no es el arranque de ninguna.
   *
   * Es lo que le permite al navegador saber de QUÉ pieza habla un paquete. Hace
   * falta porque el WebSocket y la respuesta de `/iniciar` son dos canales que se
   * cruzan: un paquete emitido antes del arranque puede llegar después de la
   * respuesta, y uno emitido después puede llegar antes. Compararlo con el
   * arranque que trajo la pieza es la única forma de no adivinar; el número de
   * notas no sirve, porque dos piezas del mismo tamaño -tocar dos veces la misma
   * escala- lo tienen igual.
   */
  arranque: number;
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
 * (`SesionCarril.iniciar()`, servidor/piezas.py). De ahí sale el `arranque` con
 * el que se reconocen después los paquetes de esta pieza.
 *
 * **Es la respuesta de la etapa 3a y la que usa hoy `useCarril.ts`.** La de la etapa
 * 3c es `RespuestaIniciarEstudio` (`tiposEstudio.ts`): trae esta misma `pieza` más
 * `secciones_en_compases` y todos los campos del estudio (compases, bucle, tempo).
 * Conviven hasta que el hook migre; después, esta sobra.
 */
export interface RespuestaIniciarPieza extends EstadoCarril {
  pieza: Pieza;
}
