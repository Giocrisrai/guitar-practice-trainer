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
  /** Si el silencio de ahora mismo puede ser una avería del cable. Lo decide el
   * servidor (`se_esperan_notas`, en `servidor/piezas.py`) y de él cuelgan las DOS
   * mitades del mismo aviso: el `sin_senal` de `/api/diagnostico` y la línea
   * naranja del carril. **No se recalcula aquí**: estaba escrito dos veces, las
   * dos reglas no eran la misma, y un comentario del JSX afirmaba que sí. */
  esperando_notas: boolean;
  /** Lo que SUENA, no lo que se pidió: `false` sin salida de audio aunque el plan
   * diga `con_click`. */
  click_sonando: boolean;
  /** Si el fondo SUENA ahora mismo, no si está pedido: sin salida de audio, sin
   * buffer renderizado o con el pestillo de la entrada echado, esto es `false`
   * aunque el interruptor esté puesto. Mismo criterio que `click_sonando`. Es lo
   * que dice la FRASE de al lado de la casilla («…pero ahora mismo no suena
   * nada»); la casilla en sí sigue a `acompanamiento_encendido`. */
  acompanamiento_sonando: boolean;
  /** El interruptor PEDIDO, que no es lo que suena. Con el micrófono elegido el
   * fondo se queda encendido y CALLADO: esto es `true` y `acompanamiento_sonando`
   * es `false`. Es lo que marca la casilla, porque una casilla que siguiera a lo
   * que suena saldría apagada en ese estado y su único clic posible mandaría
   * `encendido: true` —justo el que pone el fondo encima del micrófono— sin que
   * exista forma de apagarlo de verdad. Que no se oiga lo dice la frase. */
  acompanamiento_encendido: boolean;
  /** Si encender el fondo tiene sentido ahora mismo: hay fondo cargado Y la
   * entrada es el cable. Lo decide el servidor (`acompanamiento_posible`, en
   * `servidor/piezas.py`) y **no se recalcula aquí**, por lo mismo que
   * `esperando_notas`: la misma regla escrita dos veces nunca es la misma regla.
   *
   * **No es una compuerta, es un recordatorio.** El usuario puede encender el
   * fondo a mano con el micrófono abierto —es su equipo, y con auriculares no hay
   * realimentación—, y entonces esto SIGUE valiendo `false` mientras suena, para
   * que el aviso no se vaya. Un aviso que se va en cuanto obedeces no es un aviso. */
  acompanamiento_posible: boolean;
  /** La canción no traía otras pistas, así que lo que suena de fondo es la parte
   * PROPIA del usuario como guía, a media ganancia. Hay que decirlo: si no, el
   * alumno cree que oye el acompañamiento y se está oyendo a sí mismo. */
  acompanamiento_es_tu_parte: boolean;
  /** Cuántas voces AJENAS suenan detrás. Cero sin fondo y cero también cuando lo
   * que suena es la propia parte (`acompanamiento_es_tu_parte`). */
  acompanamiento_voces: number;
  /** Las pistas que el archivo traía y que no pueden sonar, con el motivo ya
   * escrito para el usuario. Se dice porque un fondo al que le falta el bajo sin
   * que nada lo diga parece roto. */
  acompanamiento_excluidas: PistaExcluida[];
  /** El volumen PEDIDO para el fondo, de 0 a 1 —no la ganancia que se aplica,
   * que con la guía va a la mitad—. Viaja publicado porque el deslizador no
   * tiene otro sitio del que sacarlo: `cargar_acompanamiento` lo repone por su
   * cuenta al entrar otro fondo, y un deslizador que enseñe un número distinto
   * del que vas a oír es peor que no tener deslizador. */
  acompanamiento_volumen: number;
  /** Tempo que el servidor propone para la pasada siguiente, o `null` si no hay
   * nada que sugerir (casi siempre). Va en LAS DOS DIRECCIONES: dos pasadas
   * seguidas por encima del 90 % de notas limpias lo suben un paso, y una sola
   * por debajo del 70 % lo baja uno. Quien lo pinte tiene que comparar con
   * `factor_tempo` para saber si es subir o bajar. Es una propuesta: nunca se
   * aplica sola. */
  factor_sugerido: number | null;
}

/** Una pista del archivo que NO suena de fondo, con el motivo ya escrito para el
 * usuario. El servidor la manda con nombre (`{pista, motivo}`) y no como par, para
 * que quien la pinte escriba `excluida.motivo` y no `excluida[1]`. */
export interface PistaExcluida {
  pista: string;
  motivo: string;
}

/** Lo que acepta `POST /api/piezas/acompanamiento`: el interruptor, el volumen, o
 * los dos. Es un PARCHE —lo que no viaja no se mueve—, y va por su propia puerta
 * y no por `/api/piezas/plan` porque todo cambio de plan cierra la repetición: un
 * deslizador de volumen arrastrado serían decenas de vueltas partidas. */
export interface AjusteAcompanamiento {
  encendido?: boolean;
  /** De 0 a 1, no en porcentaje: fuera de ese rango es un 400. */
  volumen?: number;
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
