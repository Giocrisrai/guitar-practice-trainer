import { useCallback, useEffect, useRef, useState } from "react";

import { crearReloj, type Reloj } from "./relojCarril";
import type { EstadoCarril, Pieza, RespuestaIniciarPieza } from "./tiposPieza";

/** Espera antes de reintentar la conexión. Desconectar el cable es habitual. */
const ESPERA_RECONEXION_MS = 1000;

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
  /** Cuántos paquetes ha traído el WebSocket. Solo sirve para saber si alguno
   * llegó mientras un `POST /iniciar` viajaba (ver `iniciar`). */
  const paquetes = useRef(0);
  /** El último instante que `instante` llegó a devolver, es decir el que se
   * pintó. Es lo que se congela al entrar en pausa (ver `instante`). */
  const instanteMostrado = useRef(0);
  const temporizador = useRef<number | null>(null);

  /** Registra un paquete del servidor: estado nuevo y reloj sincronizado. */
  const recibir = useCallback((nuevo: EstadoCarril) => {
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
    const valor = ultimo.pausado
      ? Math.max(instanteMostrado.current, ultimo.instante_s)
      : reloj.current.instante(ahoraLocal);
    instanteMostrado.current = valor;
    return valor;
  }, []);

  const iniciar = useCallback(
    async (peticion: PeticionPieza) => {
      setIniciando(true);
      setError(null);
      const paquetesAlPedir = paquetes.current;
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
        const enVuelo = paquetes.current === paquetesAlPedir ? null : ultimoEstado.current;
        if (enVuelo === null) {
          recibir(estadoInicial);
        } else if (enVuelo.total === piezaNueva.notas.length) {
          // Llegó un paquete mientras el POST viajaba y cuenta las notas de ESTA
          // pieza, así que habla de ella y es más nuevo que el estado inicial de
          // la respuesta: manda él. Adoptar el inicial haría retroceder el
          // cabezal. Se vuelve a registrar para que sincronice el reloj recién
          // hecho, que es el que va a usar el carril.
          recibir(enVuelo);
        } else {
          // El paquete en vuelo cuenta OTRAS notas: es de la pieza anterior, que
          // seguía en marcha (`total` lo saca el servidor de la pieza). Ni él ni
          // el estado inicial sirven —si se adoptara el inicial y el paquete
          // siguiente fuera más viejo, el cabezal retrocedería—, así que el
          // carril se queda sin estado hasta el primer paquete posterior al POST,
          // 33 ms después.
          //
          // Quedarse con el paquete viejo pintaba el estado de una pieza sobre
          // otra: con una pieza nueva de una nota y un paquete en vuelo que decía
          // `completado, total: 7`, la pantalla mostraba "Pieza terminada", "1 de
          // 7 notas acertadas", el contador en 7/7 y un resumen con una pulsación
          // que en esta pieza no existe.
          setEstado(null);
          ultimoEstado.current = null;
          relojCaduco.current = true;
        }
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
          const nuevo = JSON.parse(evento.data) as EstadoCarril;
          paquetes.current += 1;
          recibir(nuevo);
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
