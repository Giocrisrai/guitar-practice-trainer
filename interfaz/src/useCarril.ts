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
    // Pausado: el cabezal se queda donde el servidor lo dejó. Interpolar aquí
    // sería inventar tiempo de pieza que el servidor no está contando.
    if (ultimo.pausado) return ultimo.instante_s;
    return reloj.current.instante(ahoraLocal);
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
        if (paquetes.current === paquetesAlPedir) {
          // Reloj nuevo con cada pieza: el de la anterior tiene por suelo un
          // instante que en esta pieza está en el futuro, y el suelo solo sube.
          reloj.current = crearReloj();
          relojCaduco.current = false;
          recibir(estadoInicial);
        } else {
          // Llegó un paquete mientras el POST viajaba. Ese paquete es MÁS NUEVO
          // que este estado inicial, así que manda él: adoptar el inicial haría
          // retroceder el cabezal. Pero puede venir todavía de la pieza
          // anterior, y un instante viejo se le queda al reloj como suelo para
          // siempre; por eso se declara caduco y el paquete siguiente —33 ms—
          // hará uno nuevo tomando su instante como línea base limpia.
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
