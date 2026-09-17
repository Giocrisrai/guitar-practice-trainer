import { useEffect, useRef, useState } from "react";

import type { MensajeNota } from "./tipos";

/** Espera antes de reintentar la conexión. Desconectar el cable es habitual. */
const ESPERA_RECONEXION_MS = 1000;

/**
 * Suscripción al flujo de notas del servidor.
 *
 * Se reconecta sola: obligar a recargar la página cada vez que se desconecta el
 * cable sería un castigo desproporcionado.
 */
export function useNotas(url = `ws://${window.location.host}/ws/notas`) {
  const [nota, setNota] = useState<MensajeNota | null>(null);
  const [conectado, setConectado] = useState(false);
  const temporizador = useRef<number | null>(null);

  useEffect(() => {
    let vivo = true;
    let socket: WebSocket | null = null;

    const conectar = () => {
      if (!vivo) return;
      socket = new WebSocket(url);

      socket.onopen = () => setConectado(true);

      socket.onmessage = (evento) => {
        try {
          setNota(JSON.parse(evento.data) as MensajeNota);
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
  }, [url]);

  return { nota, conectado };
}
