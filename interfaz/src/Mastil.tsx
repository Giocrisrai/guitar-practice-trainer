import type { PerfilAfinacion, Posicion } from "./tipos";

interface Props {
  perfil: PerfilAfinacion;
  /** Capa fuerte: lo que hay que ver ahora (nota detectada, o la ayuda del ejercicio). */
  posiciones: Posicion[];
  /**
   * Capa tenue: posiciones que ya se resolvieron y se dejan como rastro. El
   * afinador no la usa y por eso es opcional: sin ella el mástil se comporta
   * exactamente como antes.
   */
  posicionesTenues?: Posicion[];
  /**
   * Nombre de la nota que se pide ahora. Se rotula sobre el mástil siempre que
   * exista, tanto si la ayuda está puesta como si no: decir QUÉ nota toca no
   * revela DÓNDE está, y es la única forma de resaltar la nota actual sin
   * regalar la respuesta que la capa de ayuda reserva para después.
   */
  notaObjetivo?: string | null;
  trastesVisibles?: number;
}

const TRASTES_CON_MARCA = [3, 5, 7, 9, 12, 15, 17, 19, 21];

/**
 * Mástil con hasta tres capas: la nota que se pide ahora (rótulo), las
 * posiciones fuertes y las posiciones tenues.
 *
 * Se resaltan TODAS las posiciones que devuelve el servidor, no una. Un La de
 * 110 Hz es tanto la 5ª cuerda al aire como la 6ª en el traste 5; desde la
 * frecuencia no se pueden distinguir y elegir una sería inventar certeza. Lo
 * mismo vale para la capa tenue: el servidor dice qué nota se acertó, no en qué
 * posición se tocó, así que se marcan todas las que valían.
 */
export function Mastil({
  perfil,
  posiciones,
  posicionesTenues = [],
  notaObjetivo = null,
  trastesVisibles,
}: Props) {
  // El número de trastes sale del perfil, no de una constante fija: guitarras y
  // bajos tienen 22 o 24 trastes (ver nucleo/afinaciones.py). Fijar 12 escondía
  // más de la mitad del mástil sin avisar, y una posición detectada más allá del
  // traste 12 no encontraba celda y se descartaba en silencio.
  const trastes = trastesVisibles ?? perfil.trastes;

  const estaEn = (lista: Posicion[], cuerda: number, traste: number) =>
    lista.some((p) => p.cuerda === cuerda && p.traste === traste);

  const claseDeCelda = (cuerda: number, traste: number) => {
    // La capa fuerte gana a la tenue: una nota que ya se acertó y que además es
    // donde está la nota actual debe leerse como la actual.
    if (estaEn(posiciones, cuerda, traste)) return " activo";
    if (estaEn(posicionesTenues, cuerda, traste)) return " tenue";
    return "";
  };

  return (
    <section className="mastil">
      {notaObjetivo && <p className="nota-objetivo">Ahora: {notaObjetivo}</p>}
      {perfil.cuerdas.map((cuerda) => (
        <div className="cuerda" key={cuerda.numero}>
          <span className="etiqueta">{cuerda.nota.replace(/\d/g, "")}</span>
          {Array.from({ length: trastes + 1 }, (_, traste) => (
            <span
              key={traste}
              className={
                "traste" + claseDeCelda(cuerda.numero, traste) + (traste === 0 ? " al-aire" : "")
              }
            />
          ))}
        </div>
      ))}
      <div className="numeros">
        {Array.from({ length: trastes + 1 }, (_, traste) => (
          <span key={traste} className="numero">
            {TRASTES_CON_MARCA.includes(traste) ? traste : ""}
          </span>
        ))}
      </div>
    </section>
  );
}
