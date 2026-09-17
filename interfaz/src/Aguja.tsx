import { estadoAfinacion, posicionAguja } from "./presentacion";

interface Props {
  nota: string | null;
  cents: number | null;
}

/** Aguja de afinación: bemol a la izquierda, sostenido a la derecha. */
export function Aguja({ nota, cents }: Props) {
  const estado = estadoAfinacion(cents);
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
