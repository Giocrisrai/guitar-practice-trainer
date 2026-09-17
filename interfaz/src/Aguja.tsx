import { estadoAfinacion, posicionAguja } from "./presentacion";
import type { MensajeNota } from "./tipos";

interface Props {
  estado: MensajeNota["estado"] | null;
  nota: string | null;
  cents: number | null;
  /** Veredicto del servidor. La interfaz no lo recalcula. */
  afinada: boolean;
}

/** Aguja de afinación: bemol a la izquierda, sostenido a la derecha. */
export function Aguja({ estado: estadoNota, nota, cents, afinada }: Props) {
  const estado = estadoAfinacion(estadoNota, cents, afinada);
  const desplazamiento = cents === null ? 0 : posicionAguja(cents) * 50;

  return (
    <section className={`aguja ${estado}`}>
      <div className="nota-grande">{nota ?? "—"}</div>
      <div className="escala">
        <span className="signo">♭</span>
        <div className="pista">
          <div className="centro" />
          <div className="marcador" style={{ left: `${50 + desplazamiento}%` }} />
        </div>
        <span className="signo">♯</span>
      </div>
      <div className="lectura">
        {cents === null ? "sin señal" : `${cents > 0 ? "+" : ""}${cents.toFixed(1)} cents`}
      </div>
      <div className="veredicto">
        {estado === "afinada" && "✔ AFINADA"}
        {estado === "grave" && "▼ grave"}
        {estado === "aguda" && "▲ aguda"}
      </div>
    </section>
  );
}
