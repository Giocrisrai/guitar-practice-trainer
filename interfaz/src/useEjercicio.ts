import { useEffect, useRef, useState } from "react";

import { detenerEjercicioAlSalir } from "./detencionAlSalir";
import type { EstadoEjercicio } from "./tiposEjercicio";

/** Espera antes de reintentar la conexión. Desconectar el cable es habitual. */
const ESPERA_RECONEXION_MS = 1000;

/**
 * Suscripción al estado del ejercicio en curso.
 *
 * Mismo patrón que `useNotas`: se reconecta sola, para no obligar a recargar la
 * página cada vez que se desconecta el cable.
 */
export function useEjercicio(url = `ws://${window.location.host}/ws/ejercicios`) {
  const [estado, setEstado] = useState<EstadoEjercicio | null>(null);
  const [conectado, setConectado] = useState(false);
  const temporizador = useRef<number | null>(null);

  useEffect(() => {
    let vivo = true;
    let socket: WebSocket | null = null;
    // Montar cancela la detención pendiente de un desmontaje anterior (StrictMode
    // o una `key` nueva): ver `detencionAlSalir.ts`.
    detenerEjercicioAlSalir.cancelar();

    const conectar = () => {
      if (!vivo) return;
      socket = new WebSocket(url);

      socket.onopen = () => setConectado(true);

      socket.onmessage = (evento) => {
        try {
          setEstado(JSON.parse(evento.data) as EstadoEjercicio);
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
      // GARANTIZA el orden es el aplazo de `programar` (ver `detencionAlSalir.ts`),
      // no el de estas líneas. El detener evita que el metrónomo se quede sonando.
      socket?.close();
      detenerEjercicioAlSalir.programar();
    };
  }, [url]);

  return { estado, conectado };
}
