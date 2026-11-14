import { useEffect, useRef } from "react";

import { colorDeCuerda, colorDeDesviacion } from "./geometriaCarril";
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
            <span className="etiqueta-cuerda" style={{ color: colorDeCuerda(numeroLinea + 1) }}>
              {rotulo}
            </span>
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
        /* La clave de sol OCUPA el pentagrama: a 22 px salia del tamano de una
           letra suelta, encajada entre las lineas de arriba, y no se leia como
           una clave. Y lleva el 8 debajo, que es lo que dice que la guitarra
           suena una octava mas grave que lo escrito (8vb) — la transposicion
           que `alturaEnPentagrama` ya aplica y que el dibujo no declaraba. */
        <g fill={COLOR_LINEA}>
          <text x={1} y={y(7)} fontSize={9 * ESPACIO} fontFamily="serif">
            𝄞
          </text>
          <text x={5} y={y(12.5)} fontSize={2.2 * ESPACIO} fontFamily="serif" textAnchor="middle">
            8
          </text>
        </g>
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

  // El compas que se esta tocando. Se deriva de `actual`, que lo dice el nucleo,
  // buscando cual de ellos contiene esa nota; con la pieza terminada o sin
  // estado no hay ninguno, y dejar uno marcado leeria como que aun te toca algo.
  const numeroEnCurso =
    actual === null
      ? null
      : (compases.find((compas) => compas.notas.some((nota) => nota.indice === actual))?.numero ??
        null);

  return (
    <div className="vista-escrita">
      {compases.map((compas) => (
        <CompasEscrito
          key={compas.numero}
          enCurso={compas.numero === numeroEnCurso}
        >
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
        </CompasEscrito>
      ))}
    </div>
  );
}

/**
 * Un compas de la vista escrita, que se trae solo a la vista cuando le toca.
 *
 * Sin esto la vista escrita no SIGUE a quien toca: es una rejilla quieta, y con
 * una pieza de treinta compases el que estas tocando se va fuera de la pantalla
 * y hay que buscarlo a mano mientras suena. `block: "nearest"` para que no
 * salte si ya se ve, que seria peor que no moverse.
 */
function CompasEscrito({
  enCurso,
  children,
}: {
  enCurso: boolean;
  children: React.ReactNode;
}) {
  const referencia = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!enCurso) return;
    const nodo = referencia.current;
    // `scrollIntoView` no existe en todos los entornos (jsdom, por ejemplo, no
    // lo implementa). Traer el compas a la vista es una comodidad; tumbar la
    // vista escrita entera por no poder hacerlo no lo es.
    if (nodo === null || typeof nodo.scrollIntoView !== "function") return;
    nodo.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [enCurso]);
  return (
    <div
      ref={referencia}
      className={enCurso ? "compas-escrito en-curso" : "compas-escrito"}
    >
      {children}
    </div>
  );
}
