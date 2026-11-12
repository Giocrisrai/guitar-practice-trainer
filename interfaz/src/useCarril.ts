import { useCallback, useEffect, useRef, useState } from "react";

import { detenerPiezaAlSalir } from "./detencionAlSalir";
import { crearReloj, type Reloj } from "./relojCarril";
import type {
  AjusteAcompanamiento,
  EstadoEstudio,
  Historial,
  Informe,
  Plan,
  RespuestaIniciarEstudio,
  RespuestaPiezaEnMarcha,
  SeccionEnCompases,
} from "./tiposEstudio";
import type { Pieza } from "./tiposPieza";

/** Espera antes de reintentar la conexión. Desconectar el cable es habitual. */
const ESPERA_RECONEXION_MS = 1000;

/**
 * Lo más que el cabezal congelado puede ir por delante del instante que declaró
 * el servidor. Es el mismo techo que `TECHO_TRAMO_S` en `servidor/piezas.py`, y
 * por el mismo motivo: un hueco largo no entra en la pieza por ningún camino.
 *
 * Los tres tapones del hueco de 30 s son del servidor; este reloj no tenía
 * ninguno. Interpolando sin paquetes, `relojCarril` crece sin techo —con el
 * WebSocket caído 30 s, `sincronizar(2.0)` y 30 s después da 32.0— y eso es
 * CORRECTO mientras el servidor siga contando, porque con audio entrando su
 * reloj avanza con los cuadros aunque el canal esté roto. Deja de serlo en
 * cuanto el servidor se pausa por falta de señal: ahí su instante está parado a
 * propósito, y congelar lo interpolado dejaba el cabezal en el segundo 32 de una
 * pieza que va por el 2. Y al volver la señal, el carril retrocedía esos 30 s
 * —lo único que la Task 7 declaró intolerable— porque el piso de no-retroceso
 * vive DENTRO de la instancia del reloj y al reanudar se tira el reloj.
 *
 * Así que la pausa congela como mucho un techo por delante de lo que el servidor
 * dice. El margen sigue absorbiendo lo que la pausa tiene que absorber: los
 * hasta 33 ms que el reloj llevaba interpolados sobre el último paquete, que es
 * la razón por la que no se congela en el instante del servidor a secas.
 */
const TECHO_TRAMO_S = 0.1;

/** El `arranque` que publica un carril SIN pieza (`ARRANQUE_NINGUNO` en
 * servidor/piezas.py). Los arranques de verdad empiezan en 1, así que el cero no
 * es el de ninguna pieza. */
const ARRANQUE_NINGUNO = 0;

/**
 * Lo que se le dice al alumno cuando el carril se apaga desde el servidor.
 *
 * No dice el motivo porque el navegador no lo sabe: el carril apagado se publica
 * igual lo apague quien lo apague. Hoy el camino que lo provoca es cambiar la
 * afinación con una pieza en marcha (`PUT /api/config`, servidor/app.py), que es
 * la spec §7 aplicada a mitad de pieza: dibujar trastes que tu instrumento no
 * tiene es peor que no dibujar nada.
 */
const AVISO_APAGADO_DESDE_EL_SERVIDOR =
  "El carril se detuvo desde el servidor. Pasa, por ejemplo, al cambiar de " +
  "afinación con una pieza en marcha: la pieza estaba escrita para la anterior.";

/** Un ejercicio del catálogo. Misma forma que el cuerpo de
 * `/api/ejercicios/iniciar`, porque una pieza se genera del mismo catálogo de
 * familias (`POST /api/piezas/iniciar`, servidor/app.py). */
export interface PeticionEjercicio {
  familia: string;
  parametros: Record<string, unknown>;
}

/**
 * Una canción de la biblioteca: la lee el SERVIDOR y la pone en el carril.
 *
 * `cancion` es el `id` de la ficha, que es el nombre del archivo con extensión;
 * `pista` va en base 1, como en todo el núcleo; `perfil` es opcional y solo cuenta
 * donde el archivo no trae afinación.
 *
 * La pieza NO viaja desde el navegador. Se manda qué canción y qué pista, y el
 * servidor la importa con el mismo `importar(ruta, numero, perfil)` que usa
 * `/api/canciones/{id}/importar`: así hay una sola puerta al carril —la que aplica
 * la regla de afinación de la etapa 3a—, y aceptar una `Pieza` del cliente sería
 * creerle las notas y el perfil con el que dice estar escrita.
 */
export interface PeticionCancion {
  cancion: string;
  pista: number;
  perfil?: string | null;
}

/**
 * Lo que hace falta para pedir una pieza: un ejercicio o una canción. Son las dos
 * formas que acepta `POST /api/piezas/iniciar`, y son exclusivas —mandar las dos a
 * la vez, o ninguna, es un 400 que dice cuál falta—.
 */
export type PeticionPieza = PeticionEjercicio | PeticionCancion;

/** Lo que devuelve `GET /api/piezas/informe`: lo tocado en esta pasada y el
 * historial de la pieza. */
export interface InformeConHistorial {
  informe: Informe;
  historial: Historial;
}

export interface SesionCarril {
  /** El último paquete del WebSocket. `null` mientras no llegó ninguno. */
  estado: EstadoEstudio | null;
  /** La pieza en curso. Llega una sola vez, en la respuesta de `/iniciar`. */
  pieza: Pieza | null;
  /** Las secciones de la pieza ya convertidas en compases, tal como las calcula el
   * núcleo. Llegan con la respuesta de `/iniciar`; vacías mientras no hay pieza. */
  secciones: SeccionEnCompases[];
  conectado: boolean;
  /** El motivo por el que no se pudo arrancar la pieza, tal y como lo dio el
   * servidor (afinación que no coincide, parámetros imposibles). */
  error: string | null;
  /** Hay un `POST /iniciar` en vuelo. */
  iniciando: boolean;
  /**
   * El instante de la pieza, en segundos, para pintar en el momento local
   * `ahoraLocal` (milisegundos de la misma línea temporal que
   * `performance.now()`, que es la de las marcas de `requestAnimationFrame`).
   *
   * Su identidad no cambia entre renders a propósito: el bucle de dibujo
   * depende de ella y no debe reiniciarse en cada paquete.
   */
  instante(ahoraLocal: number): number;
  iniciar(peticion: PeticionPieza): Promise<void>;
  detener(): Promise<void>;
  /**
   * Cambia el plan de la pasada SIN reiniciarla. Es un PARCHE: el servidor
   * conserva del plan vigente todo campo que el cuerpo no traiga, así que se manda
   * solo lo que cambia.
   *
   * Ninguna de las tres acciones guarda el plan: el vigente lo dice el servidor y
   * llega por el WebSocket. Una copia aquí se desincronizaría en cuanto el tempo
   * automático lo moviera por su cuenta. Devuelven si el servidor las aceptó; si
   * no, el motivo queda en `error`.
   */
  cambiarPlan(plan: Plan): Promise<boolean>;
  /** Mueve el cabezal al principio de un compás DEL TRAMO (fuera de él, 400). */
  saltar(compas: number): Promise<boolean>;
  /** La pausa del usuario, explícita (`activa`) y no un interruptor. No es el
   * `pausado` del estado, que es falta de señal. */
  pausar(activa: boolean): Promise<boolean>;
  /**
   * El interruptor y el volumen de la pieza de fondo. Los dos opcionales: es un
   * parche, y lo que no viaja se queda como estaba.
   *
   * Va por `POST /api/piezas/acompanamiento` y NO por `/plan` a propósito: todo
   * cambio de plan cierra la repetición en el núcleo, así que arrastrar el
   * volumen por el plan le partiría la vuelta al alumno.
   */
  acompanamiento(ajuste: AjusteAcompanamiento): Promise<boolean>;
  /**
   * Machacar un compás: arma un bucle de ESE compás y lo arranca. Son dos
   * órdenes y el orden importa: el servidor rechaza con 400 un salto a un compás
   * fuera del tramo vigente, así que primero va el plan con el rango nuevo y
   * después el salto, y por último se quita la pausa del usuario. Cada paso solo
   * va si el anterior fue aceptado.
   */
  machacar(compas: number): Promise<boolean>;
  /** Lo tocado en esta pasada. `null` si el servidor lo rechaza (el motivo queda
   * en `error`). */
  leerInforme(): Promise<InformeConHistorial | null>;
}

/**
 * La sesión del carril en el navegador: el WebSocket, la pieza y el reloj.
 *
 * Es la hermana de `useEjercicio` y copia su forma (reconexión sola, un mensaje
 * corrupto se descarta), con dos diferencias que vienen del servidor:
 *
 * - La PIEZA no viaja por el WebSocket. Llega entera una sola vez, en la
 *   respuesta de `POST /api/piezas/iniciar`, y se guarda aquí; el canal solo
 *   trae el estado, treinta veces por segundo.
 * - Hay un RELOJ. Cada paquete sincroniza `relojCarril`, que es el único sitio
 *   del proyecto que sabe de interpolación. Este archivo es también el único
 *   que llama a `performance.now()`: el bucle de dibujo usa la marca que le da
 *   `requestAnimationFrame`, que es de la misma línea temporal.
 */
export function useCarril(
  url = `ws://${window.location.host}/ws/piezas`,
  /** Pedir al servidor la pieza en marcha al montar, por si se recargó el
   * navegador. Quien llega con una pieza ya pedida (desde `Canciones`) la trae en
   * la respuesta de `iniciar` y pasa `false`: pedirla otra vez sería una petición
   * de más, y además llegaría cruzada con la suya. */
  recuperarPieza = true
): SesionCarril {
  const [estado, setEstado] = useState<EstadoEstudio | null>(null);
  const [secciones, setSecciones] = useState<SeccionEnCompases[]>([]);
  const [pieza, setPieza] = useState<Pieza | null>(null);
  const [conectado, setConectado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [iniciando, setIniciando] = useState(false);

  const reloj = useRef<Reloj>(crearReloj());
  /** El último estado recibido, para que `instante` lo lea sin cambiar de
   * identidad en cada render. */
  const ultimoEstado = useRef<EstadoEstudio | null>(null);
  /**
   * El reloj actual ya no sirve y hay que hacer otro antes de sincronizarlo.
   *
   * Pasa al pausarse el carril: el servidor congela `instante_s` mientras no
   * hay señal, pero un reloj sincronizado hace rato sigue interpolando hacia
   * delante, y su suelo —que solo sabe subir— se quedaría muy por encima de la
   * pieza. Al reanudar, un reloj recién hecho toma el instante del servidor
   * como línea base sin nada que corregir, que es exactamente lo que se quiere.
   */
  const relojCaduco = useRef(false);
  /**
   * El arranque de la pieza que tenemos, tal y como lo etiquetó el servidor.
   * `null` mientras no hay pieza.
   *
   * Es lo que decide qué paquetes son nuestros. Hace falta porque el WebSocket y
   * la respuesta de `/iniciar` son dos canales que se cruzan: un paquete emitido
   * antes del arranque puede llegar después de la respuesta, y uno emitido
   * después puede llegar antes.
   */
  const arranque = useRef<number | null>(null);
  /**
   * El último paquete que no era de nuestra pieza, guardado por si un
   * `POST /iniciar` en vuelo resulta ser el suyo.
   *
   * Un paquete puede llegar ANTES de que sepamos el arranque de la pieza que
   * acabamos de pedir —el socket va por su cuenta y el POST tarda lo que tarda—.
   * Descartarlo sin más perdería el paquete más nuevo de la pieza nueva, que es
   * justo el que debe mandar sobre el estado inicial de la respuesta. Así que se
   * aparta uno, el último, y al llegar la respuesta se decide con su etiqueta: si
   * es de esta pieza se adopta, y si no se olvida.
   */
  const paqueteEnEspera = useRef<EstadoEstudio | null>(null);
  /**
   * Si el SOCKET ya trajo un paquete de la pieza que tenemos.
   *
   * Es lo que permite distinguir los dos paquetes de carril apagado, que son
   * indistinguibles por su contenido (los dos llevan `arranque: 0`): el de antes
   * de empezar y el de haberse apagado ya. Un socket entrega en orden, así que un
   * apagado que llega DESPUÉS de un paquete nuestro se emitió después y habla del
   * final de nuestra pieza; uno que llega antes puede ser del rato anterior al
   * arranque, y ése se descarta como siempre.
   *
   * El estado inicial de la respuesta de `/iniciar` no cuenta: viene por el otro
   * canal y no está ordenado respecto a los paquetes del socket.
   */
  const vistoPorElSocket = useRef(false);
  /** El último instante que `instante` llegó a devolver, es decir el que se
   * pintó. Es lo que se congela al entrar en pausa (ver `instante`). */
  const instanteMostrado = useRef(0);
  const temporizador = useRef<number | null>(null);

  /** Deja de haber pieza: sin estado, sin arranque nuestro y sin reloj válido.
   * Lo comparten `detener` -que además lo pide al servidor- y el apagado que
   * llega por el socket. */
  const soltarLaPieza = useCallback(() => {
    setPieza(null);
    setSecciones([]);
    setEstado(null);
    ultimoEstado.current = null;
    relojCaduco.current = true;
    instanteMostrado.current = 0;
    vistoPorElSocket.current = false;
    // Sin pieza no hay arranque nuestro, así que ningún paquete vuelve a entrar
    // hasta que se arranque otra.
    arranque.current = null;
    paqueteEnEspera.current = null;
  }, []);

  /**
   * Registra un paquete del servidor: estado nuevo y reloj sincronizado.
   *
   * Un paquete que no lleve el arranque de la pieza que tenemos se DESCARTA, sin
   * mirar nada más: no habla de lo que hay en pantalla. Cubre los dos cruces de
   * los dos canales —el paquete de la pieza anterior que todavía venía por el
   * socket y el que se emitió antes del arranque y llegó después de la
   * respuesta— y también el caso de todos los días, el carril apagado
   * (`arranque: 0`) emitiendo treinta veces por segundo antes de empezar.
   *
   * Con UNA excepción: un carril apagado que llega por el socket DESPUÉS de un
   * paquete de nuestra pieza es el final de la nuestra, no un paquete ajeno (ver
   * `vistoPorElSocket` y `AVISO_APAGADO_DESDE_EL_SERVIDOR`).
   *
   * Esto sustituye a una heurística anterior que comparaba el número de notas
   * para adivinar de qué pieza venía un paquete. Adivinaba mal justo en el caso
   * más normal: dos piezas del mismo tamaño -tocar dos veces la misma escala, o
   * recargar la pieza al terminarla- tienen el mismo total, así que el resumen
   * de la anterior salía encima de la nueva.
   */
  const recibir = useCallback(
    (nuevo: EstadoEstudio, delSocket = false) => {
      if (nuevo.arranque !== arranque.current) {
        // Salvo uno: el carril APAGADO que llega después de un paquete de
        // nuestra pieza no es un paquete ajeno, es el final de la nuestra,
        // decidido fuera del navegador (hoy, cambiar la afinación a mitad de
        // pieza). Descartarlo dejaba la pantalla con el contador y el lienzo de
        // una pieza que ya no existe y sin un solo aviso.
        if (
          delSocket &&
          nuevo.arranque === ARRANQUE_NINGUNO &&
          arranque.current !== null &&
          vistoPorElSocket.current
        ) {
          soltarLaPieza();
          setError(AVISO_APAGADO_DESDE_EL_SERVIDOR);
          return;
        }
        paqueteEnEspera.current = nuevo;
        return;
      }
      if (delSocket) vistoPorElSocket.current = true;
      ultimoEstado.current = nuevo;
      setEstado(nuevo);
      if (nuevo.pausado) {
        // Sin señal no hay nada que interpolar: el instante del servidor está
        // parado a propósito y es lo que se pinta tal cual (ver `instante`).
        relojCaduco.current = true;
        return;
      }
      if (relojCaduco.current) {
        reloj.current = crearReloj();
        relojCaduco.current = false;
        // El cabezal pintado era del reloj que se acaba de tirar, y su piso de
        // no-retroceso se ha ido con él: arrastrarlo a la próxima pausa
        // congelaría el carril en un instante que ya no describe esta pieza.
        instanteMostrado.current = 0;
      }
      reloj.current.sincronizar(nuevo.instante_s, performance.now());
    },
    [soltarLaPieza]
  );

  const instante = useCallback((ahoraLocal: number): number => {
    const ultimo = ultimoEstado.current;
    if (ultimo === null) return 0;
    // Pausado: el cabezal se queda quieto, porque interpolar aquí sería inventar
    // tiempo de pieza que el servidor no está contando.
    //
    // Se congela en lo ÚLTIMO QUE SE PINTÓ, no en el instante del servidor: el
    // reloj venía interpolando por delante del último paquete (hasta 33 ms, unos
    // tres píxeles), y volver al valor del servidor haría retroceder el cabezal
    // justo al entrar en pausa. Que el cabezal no retroceda nunca es la garantía
    // por la que existe `relojCarril`; contradecirla aquí, aunque sea por tres
    // píxeles, es contradecirla.
    //
    // Pero con TECHO: lo pintado solo vale por delante del servidor hasta
    // `TECHO_TRAMO_S` (ver la constante). Un reloj que llevaba mucho rato sin
    // paquetes se congelaba en un valor desbocado, y al reanudar el carril
    // retrocedía de golpe. Acotar aquí no contradice el no-retroceso: lo
    // sostiene, porque corta el único valor desde el que el cabezal podía
    // retroceder.
    const valor = ultimo.pausado
      ? Math.min(
          Math.max(instanteMostrado.current, ultimo.instante_s),
          ultimo.instante_s + TECHO_TRAMO_S
        )
      : reloj.current.instante(ahoraLocal);
    instanteMostrado.current = valor;
    return valor;
  }, []);

  /**
   * Hace suya una pieza que el servidor tiene en marcha: la guarda, tira el reloj
   * de la anterior y fija el arranque que decide qué paquetes son nuestros. La
   * comparten `iniciar` (la pieza que acabamos de pedir) y la recuperación al
   * montar (la que ya estaba corriendo cuando se recargó el navegador).
   */
  const adoptarPieza = useCallback(
    (cuerpo: RespuestaIniciarEstudio) => {
      const { pieza: piezaNueva, secciones_en_compases: seccionesNuevas, ...estadoInicial } =
        cuerpo;
      setPieza(piezaNueva);
      setSecciones(seccionesNuevas ?? []);
      // Reloj nuevo con cada pieza: el de la anterior tiene por suelo un
      // instante que en esta pieza está en el futuro, y el suelo solo sube.
      reloj.current = crearReloj();
      relojCaduco.current = false;
      instanteMostrado.current = 0;
      // Pieza nueva, socket todavía sin decir nada de ella (ver
      // `vistoPorElSocket`).
      vistoPorElSocket.current = false;
      // A partir de aquí, los paquetes de esta pieza son los que traen este
      // arranque; cualquier otro se descarta en `recibir`. El estado inicial de
      // la respuesta viene de la misma llamada que fijó el arranque, así que
      // habla de esta pieza por construcción.
      arranque.current = cuerpo.arranque;
      // Si un paquete se adelantó a la respuesta y es de esta pieza, es más
      // nuevo que el estado inicial y manda él; si no, manda el inicial, que
      // vino de la misma llamada que fijó el arranque. Esta comparación solo
      // ELIGE entre los dos: lo que impide que entre un paquete ajeno es la
      // guarda de `recibir`, que vuelve a mirar la etiqueta.
      const enEspera = paqueteEnEspera.current;
      paqueteEnEspera.current = null;
      recibir(
        enEspera !== null && enEspera.arranque === cuerpo.arranque ? enEspera : estadoInicial
      );
    },
    [recibir]
  );

  const iniciar = useCallback(
    async (peticion: PeticionPieza) => {
      setIniciando(true);
      setError(null);
      try {
        const respuesta = await fetch("/api/piezas/iniciar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(peticion),
        });
        const cuerpo = (await respuesta.json().catch(() => null)) as
          | (RespuestaIniciarEstudio & { detail?: string })
          | null;
        if (!respuesta.ok || cuerpo === null) {
          throw new Error(cuerpo?.detail ?? `El servidor respondio ${respuesta.status}`);
        }
        adoptarPieza(cuerpo);
      } catch (excepcion) {
        setError(
          excepcion instanceof Error ? excepcion.message : "No se pudo iniciar la pieza"
        );
      } finally {
        setIniciando(false);
      }
    },
    [adoptarPieza]
  );

  const detener = useCallback(async () => {
    await fetch("/api/piezas/detener", { method: "POST" });
    soltarLaPieza();
  }, [soltarLaPieza]);

  /**
   * El molde de las órdenes: un POST con cuerpo JSON y nada que guardar.
   * El estado nuevo llega por el WebSocket. Un rechazo del servidor (400) no se
   * pierde en la consola: queda en `error`, que la pantalla enseña.
   */
  const pedir = useCallback(async (ruta: string, cuerpo: unknown): Promise<boolean> => {
    try {
      const respuesta = await fetch(ruta, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cuerpo),
      });
      if (!respuesta.ok) {
        const datos = (await respuesta.json().catch(() => null)) as { detail?: string } | null;
        setError(datos?.detail ?? `El servidor respondio ${respuesta.status}`);
        return false;
      }
      setError(null);
      return true;
    } catch (excepcion) {
      setError(excepcion instanceof Error ? excepcion.message : "No se pudo contactar al servidor");
      return false;
    }
  }, []);

  const cambiarPlan = useCallback((plan: Plan) => pedir("/api/piezas/plan", plan), [pedir]);
  const saltar = useCallback(
    (compas: number) => pedir("/api/piezas/saltar", { compas }),
    [pedir]
  );
  const pausar = useCallback(
    (activa: boolean) => pedir("/api/piezas/pausa", { activa }),
    [pedir]
  );

  const acompanamiento = useCallback(
    (ajuste: AjusteAcompanamiento) => pedir("/api/piezas/acompanamiento", ajuste),
    [pedir]
  );

  /**
   * El informe de la pasada. Es una LECTURA, no una orden: no guarda nada aquí y
   * quien lo pide decide cuándo repetirlo. Un 400 (no hay pieza) queda en `error`.
   */
  const leerInforme = useCallback(async (): Promise<InformeConHistorial | null> => {
    try {
      const respuesta = await fetch("/api/piezas/informe");
      const datos = (await respuesta.json().catch(() => null)) as
        | (Partial<InformeConHistorial> & { detail?: string })
        | null;
      if (!respuesta.ok || !datos?.informe || !datos.historial) {
        setError(datos?.detail ?? `El servidor respondio ${respuesta.status}`);
        return null;
      }
      setError(null);
      return { informe: datos.informe, historial: datos.historial };
    } catch (excepcion) {
      setError(excepcion instanceof Error ? excepcion.message : "No se pudo contactar al servidor");
      return null;
    }
  }, []);

  const machacar = useCallback(
    async (compas: number): Promise<boolean> => {
      // Primero el plan y después el salto: un salto fuera del tramo vigente es
      // un 400. El rango de un solo compás lo contiene por construcción.
      // Y al final, quitar la pausa del usuario: el botón promete EMPEZAR a
      // practicar ese compás, y en pausa el bucle quedaría armado sin moverse.
      // Es `pausa(false)`, explícita, no un interruptor.
      const armado = await cambiarPlan({
        primer_compas: compas,
        ultimo_compas: compas,
        en_bucle: true,
      });
      if (!armado) return false;
      if (!(await saltar(compas))) return false;
      return pausar(false);
    },
    [cambiarPlan, saltar, pausar]
  );

  // La pieza en marcha, para quien acaba de recargar el navegador. Se pide una
  // sola vez al montar y SOLO si no tenemos pieza ni venimos de pedir una: quien
  // llega desde `Canciones` la trae en la respuesta de `iniciar`, y pedirla otra
  // vez sería una petición de más en el camino normal.
  useEffect(() => {
    if (!recuperarPieza) return;
    let vivo = true;
    fetch("/api/piezas/pieza")
      .then((respuesta) => respuesta.json())
      .then((datos: RespuestaPiezaEnMarcha) => {
        // `arranque.current !== null`: mientras la petición volaba, el usuario
        // arrancó una pieza; la suya es más nueva que lo que preguntamos.
        if (!vivo || !datos.pieza || arranque.current !== null) return;
        adoptarPieza(datos as RespuestaIniciarEstudio);
      })
      .catch(() => {
        // Sin servidor o con una respuesta rara no hay nada que recuperar: el
        // carril arranca vacío, como antes.
      });
    return () => {
      vivo = false;
    };
    // Las dos dependencias son estables en la práctica (`adoptarPieza` no cambia de
    // identidad y `recuperarPieza` es constante por pantalla), así que es UNA vez, al
    // montar.
  }, [recuperarPieza, adoptarPieza]);

  useEffect(() => {
    let vivo = true;
    let socket: WebSocket | null = null;
    // Montar cancela la detención pendiente de un desmontaje anterior (el de
    // StrictMode o el de una `key` nueva): ver `detencionAlSalir.ts`.
    detenerPiezaAlSalir.cancelar();

    const conectar = () => {
      if (!vivo) return;
      socket = new WebSocket(url);

      socket.onopen = () => setConectado(true);

      socket.onmessage = (evento) => {
        try {
          recibir(JSON.parse(evento.data) as EstadoEstudio, true);
        } catch {
          // Un mensaje corrupto se descarta; el siguiente llega en 33 ms.
        }
      };

      socket.onclose = () => {
        setConectado(false);
        if (vivo) {
          temporizador.current = window.setTimeout(conectar, ESPERA_RECONEXION_MS);
        }
      };
    };

    conectar();

    return () => {
      vivo = false;
      if (temporizador.current !== null) window.clearTimeout(temporizador.current);
      // Cerrar el socket y pedir el detener, en este orden por claridad. Lo que
      // GARANTIZA que el detener salga después del cierre no es el orden de estas
      // líneas sino el aplazo de `programar` (una microtarea; el cierre es
      // síncrono): ver `detencionAlSalir.ts`. Así un último paquete no vuelve a
      // pintar una pieza ya detenida.
      socket?.close();
      detenerPiezaAlSalir.programar();
    };
  }, [url, recibir]);

  return {
    estado,
    pieza,
    secciones,
    conectado,
    error,
    iniciando,
    instante,
    iniciar,
    detener,
    cambiarPlan,
    saltar,
    pausar,
    acompanamiento,
    machacar,
    leerInforme,
  };
}
