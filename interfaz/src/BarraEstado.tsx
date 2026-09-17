import { fraccionNivel } from "./presentacion";

interface Props {
  nivelDb: number;
  frecuencia: number;
  latenciaMs: number;
  conectado: boolean;
}

/** Franja inferior: nivel de entrada, frecuencia, latencia y estado del cable. */
export function BarraEstado({ nivelDb, frecuencia, latenciaMs, conectado }: Props) {
  return (
    <footer className="barra-estado">
      <div className="nivel">
        <span>nivel</span>
        <div className="medidor">
          <div className="relleno" style={{ width: `${fraccionNivel(nivelDb) * 100}%` }} />
        </div>
        <span className="dbfs">{nivelDb.toFixed(0)} dBFS</span>
      </div>
      <span>{frecuencia > 0 ? `${frecuencia.toFixed(1)} Hz` : "— Hz"}</span>
      <span>latencia {latenciaMs.toFixed(0)} ms</span>
      <span className={conectado ? "conectado" : "desconectado"}>
        {conectado ? "● conectado" : "○ sin conexión"}
      </span>
    </footer>
  );
}
