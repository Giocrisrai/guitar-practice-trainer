import { useCallback, useEffect, useRef, useState } from "react";

import { crearReloj, type Reloj } from "./relojCarril";
import type { EstadoCarril, Pieza, RespuestaIniciarPieza } from "./tiposPieza";

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

/** Lo que hace falta para pedir una pieza. Misma forma que el cuerpo de
 * `/api/ejercicios/iniciar`, porque una pieza se genera del mismo catálogo de
 * familias (`POST /api/piezas/iniciar`, servidor/app.py). */
export interface PeticionPieza {
  familia: string;
  parametros: Record<string, unknown>;
}

export interface SesionCarril {
  /** El último paquete del WebSocket. `null` mientras no llegó ninguno. */
  estado: EstadoCarril | null;
  /** La pieza en curso. Llega una sola vez, en la respuesta de `/iniciar`. */
  pieza: Pieza | null;
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
export function useCarril(url = `ws://${window.location.host}/ws/piezas`): SesionCarril {
  const [estado, setEstado] = useState<EstadoCarril | null>(null);
  const [pieza, setPieza] = useState<Pieza | null>(null);
  const [conectado, setConectado] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [iniciando, setIniciando] = useState(false);

  const reloj = useRef<Reloj>(crearReloj());
  /** El último estado recibido, para que `instante` lo lea sin cambiar de
   * identidad en cada render. */
  const ultimoEstado = useRef<EstadoCarril | null>(null);
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
  const paqueteEnEspera = useRef<EstadoCarril | null>(null);
  /** El último instante que `instante` llegó a devolver, es decir el que se
   * pintó. Es lo que se congela al entrar en pausa (ver `instante`). */
  const instanteMostrado = useRef(0);
  const temporizador = useRef<number | null>(null);

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
   * Esto sustituye a una heurística anterior que comparaba el número de notas
   * para adivinar de qué pieza venía un paquete. Adivinaba mal justo en el caso
   * más normal: dos piezas del mismo tamaño -tocar dos veces la misma escala, o
   * recargar la pieza al terminarla- tienen el mismo total, así que el resumen
   * de la anterior salía encima de la nueva.
   */
  const recibir = useCallback((nuevo: EstadoCarril) => {
    if (nuevo.arranque !== arranque.current) {
      paqueteEnEspera.current = nuevo;
      return;
    }
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
      // no-retroceso se ha ido con él: arrastrarlo a la próxima pausa congelaría
      // el carril en un instante que ya no describe esta pieza.
      instanteMostrado.current = 0;
    }
    reloj.current.sincronizar(nuevo.instante_s, performance.now());
  }, []);

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
          | (RespuestaIniciarPieza & { detail?: string })
          | null;
        if (!respuesta.ok || cuerpo === null) {
          throw new Error(cuerpo?.detail ?? `El servidor respondio ${respuesta.status}`);
        }
        const { pieza: piezaNueva, ...estadoInicial } = cuerpo;
        setPieza(piezaNueva);
        // Reloj nuevo con cada pieza: el de la anterior tiene por suelo un
        // instante que en esta pieza está en el futuro, y el suelo solo sube.
        reloj.current = crearReloj();
        relojCaduco.current = false;
        instanteMostrado.current = 0;
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
      } catch (excepcion) {
        setError(
          excepcion instanceof Error ? excepcion.message : "No se pudo iniciar la pieza"
        );
      } finally {
        setIniciando(false);
      }
    },
    [recibir]
  );

  const detener = useCallback(async () => {
    await fetch("/api/piezas/detener", { method: "POST" });
    setPieza(null);
    setEstado(null);
    ultimoEstado.current = null;
    relojCaduco.current = true;
    instanteMostrado.current = 0;
    // Sin pieza no hay arranque nuestro, así que ningún paquete vuelve a entrar
    // hasta que se arranque otra.
    arranque.current = null;
    paqueteEnEspera.current = null;
  }, []);

  useEffect(() => {
    let vivo = true;
    let socket: WebSocket | null = null;

    const conectar = () => {
      if (!vivo) return;
      socket = new WebSocket(url);

      socket.onopen = () => setConectado(true);

      socket.onmessage = (evento) => {
        try {
          recibir(JSON.parse(evento.data) as EstadoCarril);
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
      socket?.close();
    };
  }, [url, recibir]);

  return { estado, pieza, conectado, error, iniciando, instante, iniciar, detener };
}
