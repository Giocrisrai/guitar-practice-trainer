import { colorDeCuerda } from "./geometriaCarril";
import type { PerfilAfinacion, Posicion } from "./tipos";
import type { AcordeEjercicio } from "./tiposEjercicio";

interface Props {
  acorde: AcordeEjercicio;
  perfil: PerfilAfinacion;
  /**
   * Los MIDI del acorde que no están sonando, tal y como los da el servidor.
   * Es lo que convierte este diagrama en algo útil mientras toca: no dice «mal»,
   * dice **qué cuerda** no suena, que es lo que un profesor diría.
   */
  faltan?: number[];
  /**
   * Si se revelan los trastes. Con `false` se dibuja el diagrama con las cuerdas
   * y su estado pero sin los números, igual que el mástil del ejercicio
   * monofónico reserva las posiciones para cuando toca ayudar.
   */
  revelado?: boolean;
}

/**
 * Diagrama de un acorde: una fila por cuerda, de la más grave arriba.
 *
 * Tres estados por cuerda, y los tres son distintos a propósito:
 *
 * - **No se toca** (no aparece en `posiciones`): una `×`. No es lo mismo que al
 *   aire. Confundirlos haría que el alumno rasgueara una cuerda que el acorde no
 *   lleva y el detector contara como intrusa una nota que el diagrama le pidió.
 * - **Suena**: con el color de su cuerda, el mismo del carril (`colorDeCuerda`),
 *   para que el idioma visual sea uno solo en todo el programa.
 * - **Falta** (su MIDI está en `faltan`): apagada y marcada. Es el caso que el
 *   ejercicio existe para enseñar.
 *
 * El diagrama es vertical por cuerdas y no el diagrama de acorde clásico
 * (cuerdas verticales, trastes horizontales) porque reutiliza la orientación del
 * mástil que la pantalla de ejercicios ya usa: dos orientaciones distintas en la
 * misma pantalla obligan a releer cuál es cuál.
 */
export function DiagramaAcorde({ acorde, perfil, faltan = [], revelado = true }: Props) {
  const porCuerda = new Map<number, Posicion>();
  acorde.posiciones.forEach((posicion) => porCuerda.set(posicion.cuerda, posicion));

  // El MIDI de cada cuerda, para poder decir si ESA cuerda es una de las que
  // faltan. `posiciones` y `midis` vienen en el mismo orden (de grave a aguda,
  // garantizado por el generador), así que se emparejan por índice.
  const midiDeCuerda = new Map<number, number>();
  acorde.posiciones.forEach((posicion, indice) => {
    midiDeCuerda.set(posicion.cuerda, acorde.midis[indice]);
  });

  const faltantes = new Set(faltan);

  return (
    <section className="diagrama-acorde" aria-label={`Acorde ${acorde.nombre}`}>
      <p className="nombre-acorde">{acorde.nombre}</p>
      {perfil.cuerdas.map((cuerda) => {
        const posicion = porCuerda.get(cuerda.numero);
        const midi = midiDeCuerda.get(cuerda.numero);
        const falta = midi !== undefined && faltantes.has(midi);
        const color = colorDeCuerda(cuerda.numero);

        return (
          <div
            className={
              "cuerda-acorde" +
              (posicion === undefined ? " no-se-toca" : "") +
              (falta ? " falta" : "")
            }
            key={cuerda.numero}
            data-cuerda={cuerda.numero}
          >
            <span className="etiqueta-cuerda" style={{ color: falta ? undefined : color }}>
              {cuerda.nota.replace(/\d/g, "")}
            </span>
            {posicion === undefined ? (
              <span className="marca-muda" aria-label="no se toca">
                ×
              </span>
            ) : (
              <span
                className={"marca-traste" + (falta ? " apagada" : "")}
                style={{ background: falta ? undefined : color }}
              >
                {revelado ? posicion.traste : ""}
              </span>
            )}
            {falta && <span className="aviso-falta">no suena</span>}
          </div>
        );
      })}
      {!revelado && <p className="pista-oculta">Los trastes aparecen si te atascas.</p>}
      <p className="notas-del-acorde">{acorde.nombres.join(" · ")}</p>
    </section>
  );
}
