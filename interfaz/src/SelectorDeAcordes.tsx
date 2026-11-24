import { useEffect, useState } from "react";

import { colorDeCuerda, colorDeTextoSobre } from "./geometriaCarril";
import type { AcordeDelCatalogo } from "./tiposEjercicio";

/**
 * De la más grave a la más aguda, que es el orden en que se rasguea y el que usa
 * `DiagramaAcorde`. Se escribe aquí porque la forma es un dibujo de SEIS huecos
 * fijos —una cuerda que el acorde no toca también ocupa su sitio— y el catálogo
 * solo trae las que suenan.
 */
const CUERDAS = [6, 5, 4, 3, 2, 1];

/**
 * La digitación de un acorde, del tamaño de una palabra.
 *
 * Seis huecos, uno por cuerda, con el número del traste dentro y el color de su
 * cuerda: el mismo idioma que el carril, la tablatura y el diagrama grande. Un
 * hueco vacío es una cuerda que no se toca, y se dibuja vacío en vez de con una
 * `×` como el diagrama grande: a este tamaño la cruz es una mancha, y lo que hay
 * que leer de un tirón es la FORMA —dónde están los dedos—, no cada cuerda.
 *
 * Es lo que permite elegir sin leer: un Do y un La menor se distinguen por su
 * silueta antes de que el ojo llegue al nombre.
 */
function FormaDelAcorde({ acorde }: { acorde: AcordeDelCatalogo }) {
  const trastePorCuerda = new Map(acorde.posiciones.map((p) => [p.cuerda, p.traste]));
  return (
    <span className="forma-acorde" aria-hidden="true">
      {CUERDAS.map((cuerda) => {
        const traste = trastePorCuerda.get(cuerda);
        if (traste === undefined) {
          return <span className="hueco-acorde vacio" key={cuerda} />;
        }
        const color = colorDeCuerda(cuerda);
        return (
          <span
            className="hueco-acorde"
            key={cuerda}
            style={{ background: color, color: colorDeTextoSobre(color) }}
          >
            {traste === 0 ? "" : traste}
          </span>
        );
      })}
    </span>
  );
}

interface Props {
  /** Las claves elegidas, EN ORDEN: el ejercicio alterna en ese orden. */
  elegidas: string[];
  alCambiar: (claves: string[]) => void;
}

/**
 * Elige los acordes del ejercicio de cambios, y en qué orden.
 *
 * Existe porque `claves` era inalcanzable: la familia lo publica como parámetro
 * y el catálogo publica los ocho acordes, pero ninguna pantalla lo pintaba, así
 * que nunca viajaba y solo se podían practicar los tres del valor por defecto.
 *
 * **El orden es el ejercicio.** `generar_cambios` ALTERNA en el orden recibido
 * —Do, Sol, Re, Do, Sol, Re— porque lo que se practica es el cambio, no el
 * acorde. Así que lo elegido se muestra como la vuelta que es, con las flechas
 * puestas y la última volviendo a la primera; una lista de casillas marcadas
 * diría lo que hay y escondería lo único que importa, que es por dónde se pasa.
 *
 * Un acorde se añade al final al pulsarlo y se quita al volver a pulsarlo: no se
 * puede pedir dos veces el mismo. Reordenar se hace quitando y volviendo a
 * poner, que con ocho acordes y una vuelta de tres o cuatro es menos trabajo que
 * aprenderse un arrastre.
 *
 * Sin nada elegido no viaja el parámetro, y el generador aplica su propio valor
 * por defecto. Es la misma regla que los demás controles de esta pantalla, y por
 * eso aquí no hay escrito ningún acorde concreto: el día que el núcleo cambie
 * esos tres, esta pantalla no miente.
 */
export function SelectorDeAcordes({ elegidas, alCambiar }: Props) {
  const [catalogo, setCatalogo] = useState<AcordeDelCatalogo[]>([]);

  useEffect(() => {
    let vivo = true;
    fetch("/api/ejercicios/acordes")
      .then((r) => r.json())
      .then((datos: AcordeDelCatalogo[]) => {
        if (vivo) setCatalogo(datos);
      })
      .catch(() => {
        // Sin catálogo no se pinta nada y el ejercicio sale con los acordes por
        // defecto: un selector vacío con un error encima sería peor que un
        // ejercicio que funciona.
      });
    return () => {
      vivo = false;
    };
  }, []);

  if (catalogo.length === 0) return null;

  const porClave = new Map(catalogo.map((a) => [a.clave, a]));
  const vuelta = elegidas.map((clave) => porClave.get(clave)).filter((a) => a !== undefined);

  const alternar = (clave: string) => {
    alCambiar(
      elegidas.includes(clave) ? elegidas.filter((c) => c !== clave) : [...elegidas, clave]
    );
  };

  return (
    <div className="selector-acordes">
      <p className="titulo-selector-acordes" id="titulo-selector-acordes">
        Acordes
      </p>

      {vuelta.length === 0 ? (
        <p className="vuelta-vacia">
          Sin elegir ninguno practicarás los que traiga el generador.
        </p>
      ) : (
        <ol className="vuelta-acordes" aria-label="La vuelta que vas a practicar">
          {vuelta.map((acorde, indice) => (
            <li key={acorde.clave}>
              <button
                type="button"
                className="paso-vuelta"
                onClick={() => alternar(acorde.clave)}
                aria-label={`Quitar ${acorde.nombre} de la vuelta`}
              >
                <FormaDelAcorde acorde={acorde} />
                <span className="nombre-paso">{acorde.nombre}</span>
              </button>
              {indice < vuelta.length - 1 && (
                <span className="flecha-vuelta" aria-hidden="true" />
              )}
            </li>
          ))}
          {vuelta.length > 1 && (
            <li className="cierre-vuelta" aria-hidden="true">
              <span className="flecha-vuelta vuelve" />
              <span className="texto-cierre">y otra vez</span>
            </li>
          )}
        </ol>
      )}

      {vuelta.length === 1 && (
        <p className="aviso-selector-acordes">
          Con uno solo no hay cambio que practicar: elige al menos dos.
        </p>
      )}

      <div
        className="catalogo-acordes"
        role="group"
        aria-labelledby="titulo-selector-acordes"
      >
        {catalogo.map((acorde) => {
          const puesto = elegidas.includes(acorde.clave);
          return (
            <button
              type="button"
              key={acorde.clave}
              className={"ficha-acorde" + (puesto ? " puesta" : "")}
              aria-pressed={puesto}
              onClick={() => alternar(acorde.clave)}
            >
              <FormaDelAcorde acorde={acorde} />
              <span className="nombre-ficha">{acorde.nombre}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
