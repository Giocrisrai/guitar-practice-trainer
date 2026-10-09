import { colorDeDesviacion } from "./geometriaCarril";
import type { EstadoCarril, NotaTocada, Pieza } from "./tiposPieza";
import {
  alturaEnPentagrama,
  celdasDeTablatura,
  compasesDe,
  lineaDeTablatura,
  lineasAdicionales,
  llevaSostenido,
  type Compas,
} from "./vistaEscrita";

/**
 * La pieza como se escribe: tablatura y pentagrama, para estudiarla y para
 * repasar lo tocado. No decide nada: lo que va en cada compás, línea y altura lo
 * devuelve `vistaEscrita.ts`; aquí solo se pinta. El pentagrama es SVG porque es
 * estático (no se refresca sesenta veces por segundo, a diferencia del carril).
 *
 * Una nota ya tocada se pinta con `colorDeDesviacion`, el mismo que usa el
 * carril, y lleva su desviación en cents. Un `cents` nulo es "no se supo", que
 * tiene su propio color y su propio texto: nunca se muestra como 0.
 */

export interface PropiedadesVistaEscrita {
  pieza: Pieza;
  estado: EstadoCarril | null;
  /** Cuántas cuerdas hay: las del perfil, o la más alta que la pieza toca. */
  cuerdas: number;
  /** Nombre de cada cuerda, de la 1 (aguda) a la última (grave): "E4", "B3"...
   * Si faltan, las líneas se rotulan con el número de cuerda. */
  etiquetas?: string[];
}

const COLOR_PENDIENTE = "#cfd6e0";
const COLOR_LINEA = "#6b7686";
/** La nota en curso: el aro que dice "esta es la que toca ahora". */
const COLOR_ACTUAL = "#ffd166";
const ANCHO_ETIQUETA = 3;

const ANCHO_COMPAS = 240;
const MARGEN_X = 14;
const ESPACIO = 5; // píxeles por medio espacio del pentagrama
const MARGEN_Y = 16;

function tocadasPorIndice(estado: EstadoCarril | null): Map<number, NotaTocada> {
  return new Map((estado?.tocadas ?? []).map((tocada) => [tocada.indice, tocada]));
}

/** "+12 c", "-5 c", o "?" cuando no se supo. */
function textoCents(cents: number | null): string {
  if (cents === null) return "?";
  const redondeado = Math.round(cents);
  return `${redondeado > 0 ? "+" : ""}${redondeado} c`;
}

/** La nota que el alumno tocó cuando no era la pedida; `null` si acertó la altura
 * o aún no tocó.
 *
 * El veredicto es `acertada`, que ya lo publica el núcleo
 * (`seguimiento.py:_adjudicar`, `tiposPieza.ts`). Aquí se comparaban otra vez
 * los MIDIs, que es literalmente ese booleano recalculado: la misma duplicación
 * que en la etapa 2a hubo que quitar cuatro veces. */
function tocadaDistinta(tocada: NotaTocada | undefined): NotaTocada | null {
  return tocada !== undefined && !tocada.acertada ? tocada : null;
}

function titulo(nombre: string, tocada: NotaTocada | undefined): string {
  if (tocada === undefined) return nombre;
  return tocada.cents === null
    ? `${nombre}: tocada, desviación sin medir`
    : `${nombre}: ${textoCents(tocada.cents)}`;
}

function Tablatura({
  compas,
  cuerdas,
  tocadas,
  actual,
  etiquetas,
}: {
  compas: Compas;
  cuerdas: number;
  tocadas: Map<number, NotaTocada>;
  actual: number | null;
  etiquetas: string[] | undefined;
}) {
  const lineas = lineaDeTablatura(compas, cuerdas);
  const celdas = celdasDeTablatura(compas, cuerdas);
  return (
    <pre className="tablatura" aria-label={`Tablatura del compás ${compas.numero + 1}`}>
      {lineas.map((linea, numeroLinea) => {
        const suyas = celdas
          .filter((celda) => celda.linea === numeroLinea)
          .sort((a, b) => a.columna - b.columna);
        const trozos = [];
        let cursor = 0;
        for (const celda of suyas) {
          // Una celda que empieza antes del cursor ya está cubierta por la línea.
          if (celda.columna < cursor) continue;
          if (celda.columna > cursor) trozos.push(linea.slice(cursor, celda.columna));
          const tocada = tocadas.get(celda.indice);
          const enCurso = celda.indice === actual;
          trozos.push(
            tocada === undefined && !enCurso ? (
              celda.texto
            ) : (
              <span
                key={celda.indice}
                className={enCurso ? "traste-actual" : undefined}
                style={tocada === undefined ? undefined : { color: colorDeDesviacion(tocada) }}
              >
                {celda.texto}
              </span>
            )
          );
          cursor = celda.columna + celda.texto.length;
        }
        trozos.push(linea.slice(cursor));
        const rotulo = (etiquetas?.[numeroLinea] ?? String(numeroLinea + 1)).padEnd(ANCHO_ETIQUETA);
        return (
          <div key={numeroLinea}>
            <span className="etiqueta-cuerda">{rotulo}</span>
            {trozos}
          </div>
        );
      })}
    </pre>
  );
}

/** Lo que el alumno tocó cuando no era la nota pedida, dicho con palabras: es lo
 * que deja ver una cuerda desafinada más de un semitono. */
function Equivocadas({ compas, tocadas }: { compas: Compas; tocadas: Map<number, NotaTocada> }) {
  const filas = compas.notas.flatMap((nota) => {
    const distinta = tocadaDistinta(tocadas.get(nota.indice));
    return distinta === null ? [] : [{ nota, distinta }];
  });
  if (filas.length === 0) return null;
  return (
    <ul className="equivocadas">
      {filas.map(({ nota, distinta }) => (
        <li key={nota.indice} style={{ color: colorDeDesviacion(distinta) }}>
          Pedida {nota.nombre}, tocaste {distinta.nombre} ({textoCents(distinta.cents)})
        </li>
      ))}
    </ul>
  );
}

function Pentagrama({
  compas,
  tocadas,
  actual,
  alturaMinima,
  alturaMaxima,
}: {
  compas: Compas;
  tocadas: Map<number, NotaTocada>;
  actual: number | null;
  alturaMinima: number;
  alturaMaxima: number;
}) {
  const y = (altura: number) => MARGEN_Y + (altura - alturaMinima) * ESPACIO;
  const alto = y(alturaMaxima) + MARGEN_Y;
  const x = (pulso: number) =>
    MARGEN_X + 14 + ((pulso - compas.inicio_pulsos) / compas.pulsos) * (ANCHO_COMPAS - 2 * MARGEN_X - 20);

  return (
    <svg
      className="pentagrama"
      width={ANCHO_COMPAS}
      height={alto}
      role="img"
      aria-label={`Pentagrama del compás ${compas.numero + 1}`}
    >
      {[0, 2, 4, 6, 8].map((altura) => (
        <line
          key={altura}
          x1={0}
          x2={ANCHO_COMPAS}
          y1={y(altura)}
          y2={y(altura)}
          stroke={COLOR_LINEA}
        />
      ))}
      <line x1={ANCHO_COMPAS} x2={ANCHO_COMPAS} y1={y(0)} y2={y(8)} stroke={COLOR_LINEA} />
      {compas.numero === 0 && (
        <text x={2} y={y(5)} fontSize={22} fill={COLOR_LINEA} fontFamily="serif">
          𝄞
        </text>
      )}
      {compas.notas.map((nota) => {
        const altura = alturaEnPentagrama(nota.midi);
        const cx = x(nota.inicio_pulsos);
        const tocada = tocadas.get(nota.indice);
        const color = tocada === undefined ? COLOR_PENDIENTE : colorDeDesviacion(tocada);
        const hueca = nota.duracion_pulsos >= 2;
        const distinta = tocadaDistinta(tocada);
        return (
          <g key={nota.indice}>
            <title>{titulo(nota.nombre, tocada)}</title>
            {lineasAdicionales(altura).map((a) => (
              <line
                key={a}
                x1={cx - 8}
                x2={cx + 8}
                y1={y(a)}
                y2={y(a)}
                stroke={COLOR_LINEA}
              />
            ))}
            {nota.indice === actual && (
              <circle
                data-testid="nota-actual"
                cx={cx}
                cy={y(altura)}
                r={ESPACIO * 2.2}
                fill="none"
                stroke={COLOR_ACTUAL}
                strokeWidth={2}
              />
            )}
            {distinta !== null && (
              <g data-testid="nota-tocada-distinta">
                <ellipse
                  cx={cx + 3 * ESPACIO}
                  cy={y(alturaEnPentagrama(distinta.midi))}
                  rx={ESPACIO * 1.1}
                  ry={ESPACIO * 0.8}
                  fill="none"
                  stroke={colorDeDesviacion(distinta)}
                  strokeDasharray="2 2"
                />
                <text
                  x={cx + 3 * ESPACIO}
                  y={y(alturaEnPentagrama(distinta.midi)) - ESPACIO * 1.5}
                  fontSize={9}
                  textAnchor="middle"
                  fill={colorDeDesviacion(distinta)}
                >
                  {distinta.nombre}
                </text>
              </g>
            )}
            {llevaSostenido(nota.midi) && (
              <text x={cx - 17} y={y(altura) + 4} fontSize={12} fill={color}>
                #
              </text>
            )}
            <ellipse
              cx={cx}
              cy={y(altura)}
              rx={ESPACIO * 1.2}
              ry={ESPACIO * 0.9}
              fill={hueca ? "none" : color}
              stroke={color}
              strokeWidth={1.5}
            />
            {nota.duracion_pulsos < 4 && (
              <line
                x1={cx + ESPACIO * 1.2}
                x2={cx + ESPACIO * 1.2}
                y1={y(altura)}
                y2={y(altura) - 6 * ESPACIO}
                stroke={color}
              />
            )}
            {tocada !== undefined && (
              <text
                x={cx}
                y={y(altura) + 3 * ESPACIO}
                fontSize={9}
                textAnchor="middle"
                fill={color}
              >
                {textoCents(tocada.cents)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function VistaEscrita({ pieza, estado, cuerdas, etiquetas }: PropiedadesVistaEscrita) {
  const compases = compasesDe(pieza);
  const tocadas = tocadasPorIndice(estado);
  // La nota en curso la dice el núcleo (`indice_actual`); no se deduce. Con la
  // pieza terminada ya no hay ninguna en curso.
  const actual = estado === null || estado.completado ? null : estado.indice_actual;

  // El mismo rango vertical en todos los compases, para que se lean alineados.
  const alturas = [
    ...pieza.notas.map((nota) => alturaEnPentagrama(nota.midi)),
    ...[...tocadas.values()].map((t) => alturaEnPentagrama(t.midi)),
  ];
  const alturaMinima = Math.min(-2, ...alturas.map((a) => a - 6)); // sitio para la plica
  const alturaMaxima = Math.max(10, ...alturas.map((a) => a + 4)); // y para los cents

  return (
    <div className="vista-escrita">
      {compases.map((compas) => (
        <div className="compas-escrito" key={compas.numero}>
          <div className="numero-compas">{compas.numero + 1}</div>
          <Pentagrama
            compas={compas}
            tocadas={tocadas}
            actual={actual}
            alturaMinima={alturaMinima}
            alturaMaxima={alturaMaxima}
          />
          <Tablatura
            compas={compas}
            cuerdas={cuerdas}
            tocadas={tocadas}
            actual={actual}
            etiquetas={etiquetas}
          />
          <Equivocadas compas={compas} tocadas={tocadas} />
        </div>
      ))}
    </div>
  );
}
