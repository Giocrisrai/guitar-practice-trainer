/**
 * Detener lo que corre en el servidor cuando la pantalla se desmonta.
 *
 * Con el click de metrónomo, una pieza o un ejercicio que se quedan corriendo se
 * quedan SONANDO. Pero detener en la limpieza de un efecto a secas es un error en
 * desarrollo: `StrictMode` monta, desmonta y vuelve a montar, y esa limpieza
 * pararía justo la pieza que la pantalla acaba de pedir. Por eso la orden se
 * APLAZA una microtarea y la vuelta a montar la cancela: un desmontaje de verdad no
 * tiene quien la cancele y la orden sale.
 *
 * Quien la use cierra el WebSocket ANTES de `programar()`: si el último paquete
 * llegara después de pedir el detener, volvería a pintar algo ya detenido.
 *
 * `keepalive` pide al navegador que la petición sobreviva a la navegación que
 * desmontó la pantalla. jsdom no lo modela, y no hay prueba que lo vigile.
 */
export interface DetencionAlSalir {
  /** Anula la orden pendiente: la pantalla se volvió a montar. */
  cancelar(): void;
  /** Pide detener en cuanto acabe el desmontaje, salvo que se cancele antes. */
  programar(): void;
}

export function crearDetencionAlSalir(ruta: string): DetencionAlSalir {
  /** Cada `programar` abre una ficha; `cancelar` la rompe. Al tocarle el turno,
   * la orden solo sale si su ficha sigue entera. */
  let pendiente: { anulada: boolean } | null = null;
  return {
    cancelar() {
      if (pendiente !== null) pendiente.anulada = true;
      pendiente = null;
    },
    programar() {
      this.cancelar();
      const ficha = { anulada: false };
      pendiente = ficha;
      // Una microtarea y no un temporizador: el segundo montaje de StrictMode
      // ocurre en la misma tarea que el desmontaje, así que a la microtarea ya
      // le ha dado tiempo de ser cancelada; y, al contrario que un temporizador,
      // no se escapa a lo que venga después.
      void Promise.resolve()
        .then(() => {
          if (ficha.anulada) return;
          pendiente = null;
          // Un rechazo (servidor caído al cerrar la pestaña) no tiene a quién
          // contárselo.
          return fetch(ruta, { method: "POST", keepalive: true });
        })
        .catch(() => undefined);
    },
  };
}
