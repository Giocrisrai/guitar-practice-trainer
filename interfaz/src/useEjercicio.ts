import { useEffect, useRef, useState } from "react";

import { crearDetencionAlSalir } from "./detencionAlSalir";
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
  /** Detener el ejercicio al desmontar, o su metrónomo se queda sonando. */
  const detencionAlSalir = useRef(crearDetencionAlSalir("/api/ejercicios/detener"));

  useEffect(() => {
    let vivo = true;
    let socket: WebSocket | null = null;
    const detencion = detencionAlSalir.current;
    detencion.cancelar();

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
      // El socket se cierra ANTES de pedir el detener: si el último paquete
      // llegara después, volvería a pintar un ejercicio ya detenido.
      socket?.close();
      detencion.programar();
    };
  }, [url]);

  return { estado, conectado };
}
