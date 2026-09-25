import { calificacion } from "./presentacionEjercicio";
import type { InformeServidor } from "./tiposEjercicio";

interface Props {
  informe: InformeServidor;
  onReiniciar: () => void;
}

/**
 * Notas que costaron tres intentos o mas.
 *
 * Mismo umbral que usa el evaluador para decidir donde conviene insistir
 * (ver nucleo/ejercicios/modelo.py, INTENTOS_NOTA_DIFICIL); el servidor no lo
 * manda como campo aparte, asi que se filtra aqui sobre los intentos ya
 * contados, sin inventar ningun juicio musical nuevo.
 */
const INTENTOS_NOTA_DIFICIL = 3;

/** Informe final de un ejercicio completado. */
export function Informe({ informe, onReiniciar }: Props) {
  const total = informe.notas.length;
  const dificiles = informe.notas.filter((n) => n.intentos >= INTENTOS_NOTA_DIFICIL);

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
