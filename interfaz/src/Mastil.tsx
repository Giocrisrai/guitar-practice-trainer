import type { PerfilAfinacion, Posicion } from "./tipos";

interface Props {
  perfil: PerfilAfinacion;
  posiciones: Posicion[];
  trastesVisibles?: number;
}

const TRASTES_CON_MARCA = [3, 5, 7, 9, 12, 15, 17, 19, 21];

/**
 * Mástil con las posiciones detectadas resaltadas.
 *
 * Se resaltan TODAS las posiciones que devuelve el servidor, no una. Un La de
 * 110 Hz es tanto la 5ª cuerda al aire como la 6ª en el traste 5; desde la
 * frecuencia no se pueden distinguir y elegir una sería inventar certeza.
 */
export function Mastil({ perfil, posiciones, trastesVisibles = 12 }: Props) {
  const activa = (cuerda: number, traste: number) =>
    posiciones.some((p) => p.cuerda === cuerda && p.traste === traste);

  return (
    <section className="mastil">
      {perfil.cuerdas.map((cuerda) => (
        <div className="cuerda" key={cuerda.numero}>
          <span className="etiqueta">{cuerda.nota.replace(/\d/g, "")}</span>
          {Array.from({ length: trastesVisibles + 1 }, (_, traste) => (
            <span
              key={traste}
              className={
                "traste" +
                (activa(cuerda.numero, traste) ? " activo" : "") +
                (traste === 0 ? " al-aire" : "")
              }
            />
          ))}
        </div>
      ))}
      <div className="numeros">
        {Array.from({ length: trastesVisibles + 1 }, (_, traste) => (
          <span key={traste} className="numero">
            {TRASTES_CON_MARCA.includes(traste) ? traste : ""}
          </span>
        ))}
      </div>
    </section>
  );
}
