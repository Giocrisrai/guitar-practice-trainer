import { limpiasDelInforme, textoDelDesfase } from "./calculosInforme";
import type { Historial, Informe } from "./tiposEstudio";

interface PropiedadesInforme {
  informe: Informe;
  historial: Historial;
  /** Arma un bucle en ese compás y lo arranca. Lo resuelve quien sabe del plan. */
  alMachacar: (compas: number) => void;
}

/**
 * El informe de la pasada: compás a compás, con el desfase en palabras, los
 * avisos de lo que no se puede medir bien, y un botón para machacar los peores.
 */
export function InformePasada({ informe, historial, alMachacar }: PropiedadesInforme) {
  const hayAcordes = informe.compases.some((compas) => compas.tiene_acordes);
  const resumen = limpiasDelInforme(informe.compases, informe.repeticiones);

  return (
    <section className="informe-pasada" aria-label="Informe de la pasada">
      <h3>Informe de la pasada</h3>

      {informe.ritmo_aproximado && (
        <p className="aviso-informe">
          El ritmo de esta pieza se dedujo, no estaba escrito: los desfases son
          orientativos.
        </p>
      )}
      {informe.compas_variable && (
        <p className="aviso-informe">
          Esta pieza cambia de compás a mitad: desde el cambio, los números de compás
          pueden no coincidir con la partitura.
        </p>
      )}

      {resumen !== null && (
        <p className="resumen-informe">
          Notas limpias (acertadas y a tiempo): {resumen.limpias} de {resumen.medibles} (
          {Math.round((resumen.limpias / resumen.medibles) * 100)} %)
        </p>
      )}

      <table className="tabla-informe">
        <thead>
          <tr>
            {/* Las tres cifras de la spec §6 (acertadas, a tiempo y desfase) más
                las limpias, que son las que deciden el tempo. Con solo las
                limpias el usuario no distingue un fallo de altura de uno de
                ritmo sin deducirlo de la columna del desfase, y los tres datos ya
                viajan en el paquete. */}
            <th scope="col">Compás</th>
            <th scope="col">Acertadas</th>
            <th scope="col">A tiempo</th>
            <th scope="col">Notas limpias</th>
            <th scope="col">Desfase medio</th>
          </tr>
        </thead>
        <tbody>
          {informe.compases.map((compas) => (
            <tr key={compas.numero} data-compas={compas.numero}>
              <th scope="row">{compas.numero}</th>
              <td className="celda-acertadas">
                {compas.tiene_acordes
                  ? "con acordes"
                  : `${compas.acertadas} de ${compas.notas_medibles * informe.repeticiones}`}
              </td>
              <td className="celda-a-tiempo">
                {compas.tiene_acordes
                  ? "con acordes"
                  : `${compas.a_tiempo} de ${compas.notas_medibles * informe.repeticiones}`}
              </td>
              <td className="celda-limpias">
                {compas.tiene_acordes
                  ? "con acordes"
                  : `${compas.limpias} de ${compas.notas_medibles * informe.repeticiones}`}
              </td>
              <td className="celda-desfase">{textoDelDesfase(compas.desfase_medio_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {hayAcordes && (
        <p className="aviso-informe aviso-acordes">
          En los compases con acordes solo se puede medir una nota de cada acorde, así
          que no entran en el resultado: no significa que los hayas tocado mal.
        </p>
      )}

      <p className="resumen-informe">
        {historial.pasadas === 1
          ? "1 pasada en esta pieza."
          : `${historial.pasadas} pasadas en esta pieza.`}
      </p>

      {historial.peores_compases.length > 0 && (
        <ul className="peores-compases">
          {historial.peores_compases.map((peor) => (
            <li key={peor.compas}>
              <button type="button" onClick={() => alMachacar(peor.compas)}>
                Machacar el compás {peor.compas}
              </button>{" "}
              <span className="cifras-peor">
                no salió limpio en {peor.falladas} de {peor.contadas}{" "}
                {peor.contadas === 1 ? "pasada" : "pasadas"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
