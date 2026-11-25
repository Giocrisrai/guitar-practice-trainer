import { nombreDeMidi } from "./presentacionEjercicio";
import type { InformeCambiosServidor } from "./tiposEjercicio";

interface Props {
  informe: InformeCambiosServidor;
  onReiniciar: () => void;
}

/**
 * Informe de un ejercicio de cambios de acorde.
 *
 * La cifra de cabecera es el **tiempo de cambio**, no el porcentaje de acierto:
 * es el número que baja al practicar y lo que distingue a quien sabe los acordes
 * de quien los sabe tocar seguidos.
 *
 * `null` en los tiempos no es cero. No haber logrado ningún cambio no es cambiar
 * instantáneamente, así que en ese caso no se muestra ninguna cifra en vez de un
 * «0,00 s» que sería una mentira halagadora.
 */
export function InformeCambios({ informe, onReiniciar }: Props) {
  const total = informe.acordes.length;
  const medio = informe.tiempo_medio_de_cambio_s;
  const lento = informe.cambio_mas_lento_s;
  const costosos = informe.acordes.filter((a) => a.intentos >= 3);

  return (
    <section className="informe informe-cambios">
      {medio === null ? (
        <h2>Sin cambios medidos todavía</h2>
      ) : (
        <h2>{medio.toFixed(2)} s por cambio</h2>
      )}

      <p className="resumen-informe">
        {informe.logrados} de {total} acordes, {informe.a_la_primera} a la primera
      </p>

      {lento !== null && (
        <p className="cambio-lento">El más lento te costó {lento.toFixed(2)} s</p>
      )}

      {informe.cuerdas_problematicas.length > 0 && (
        <div className="cuerdas-problematicas">
          <h3>Las que más veces no sonaron</h3>
          <ul>
            {informe.cuerdas_problematicas.map((midi) => (
              <li key={midi}>{nombreDeMidi(midi)}</li>
            ))}
          </ul>
        </div>
      )}

      {costosos.length > 0 && (
        <div className="acordes-dificiles">
          <h3>Acordes que costaron</h3>
          <ul>
            {costosos.map((a) => (
              <li key={a.indice}>
                {a.nombre} — {a.intentos} intentos
              </li>
            ))}
          </ul>
        </div>
      )}

      {total > 0 && (
        <div className="tiempos-de-cambio">
          <h3>Cambio a cambio</h3>
          <ul>
            {informe.acordes.map((a) => (
              <li key={a.indice} className={a.logrado ? undefined : "no-acertada"}>
                {a.nombre} — {a.cambio_s === null ? "sin cambio que medir" : `${a.cambio_s.toFixed(2)} s`}
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
