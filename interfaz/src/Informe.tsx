import { calificacion } from "./presentacionEjercicio";
import type { InformeServidor } from "./tiposEjercicio";

interface Props {
  informe: InformeServidor;
  onReiniciar: () => void;
}

/** Informe final de un ejercicio completado. */
export function Informe({ informe, onReiniciar }: Props) {
  const total = informe.notas.length;
  // Que nota cuenta como "dificil" (INTENTOS_NOTA_DIFICIL) lo decide el
  // nucleo, no la interfaz: notas_dificiles llega ya calculada en el informe.
  const dificiles = informe.notas_dificiles;

  return (
    <section className="informe">
      <h2>{calificacion(informe.aciertos_a_la_primera, total)}</h2>

      <p className="resumen-informe">
        {informe.aciertos_a_la_primera} de {total} notas a la primera
      </p>

      {informe.desviacion_mediana_cents !== null && (
        <p className="desviacion-informe">
          Desviación mediana: {informe.desviacion_mediana_cents} cents
        </p>
      )}

      {informe.regularidad_ms !== null && (
        <p className="regularidad-informe">Regularidad: {informe.regularidad_ms} ms</p>
      )}

      {dificiles.length > 0 && (
        <div className="notas-dificiles">
          <h3>Notas que costaron</h3>
          <ul>
            {dificiles.map((n) => (
              <li key={n.indice}>
                {n.nombre} — {n.intentos} intentos
              </li>
            ))}
          </ul>
        </div>
      )}

      <button type="button" onClick={onReiniciar}>
        Volver a empezar
      </button>
    </section>
  );
}
