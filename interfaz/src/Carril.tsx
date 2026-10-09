import { useEffect, useMemo, useRef, useState } from "react";

import {
  VENTANA_VISIBLE_S,
  colorDeDesviacion,
  notasVisibles,
  rectanguloDeNota,
  type LienzoCarril,
} from "./geometriaCarril";
import type { PerfilAfinacion } from "./tipos";
import type { FamiliaEjercicio } from "./tiposEjercicio";
import type { Clasificacion, EstadoCarril, NotaDePieza, NotaTocada, Pieza } from "./tiposPieza";
import { useCarril } from "./useCarril";

/**
 * El carril en pantalla: las notas de la pieza vienen hacia ti.
 *
 * Reparto de trabajo, que es lo que explica lo demás:
 *
 * - `useCarril` lleva el WebSocket, la pieza y el RELOJ. Es el único sitio que
 *   llama a `performance.now()`.
 * - `relojCarril` es el único sitio que sabe de interpolación entre paquetes.
 * - `geometriaCarril` decide qué notas entran en la ventana y en qué rectángulo
 *   caen; está probado sin canvas de por medio.
 * - Este archivo no decide nada: pide el instante, pide los rectángulos y los
 *   pinta. Lo único suyo son los colores y el bucle de dibujo.
 */

/** La familia con la que arranca el carril mientras no ha llegado el catálogo de
 * `/api/ejercicios/familias`. El selector la sustituye en cuanto llega: es un
 * valor por defecto, no una copia del catálogo. */
const FAMILIA_POR_DEFECTO = "escala";

const COLOR_FONDO = "#12161b";
const COLOR_SEPARADOR = "#262d36";
const COLOR_LINEA_ATAQUE = "#e6e9ee";
/** Una nota que todavía no se ha tocado: pálida y sin veredicto. Los demás
 * colores los decide `colorDeDesviacion`, que es quien sabe qué significa cada
 * desviación (y que un `cents` nulo no es un cero). */
const COLOR_PENDIENTE = "#cfd6e0";
const COLOR_TRASTE = "#12161b";

/** Hueco a cada lado del carril de una cuerda, en píxeles CSS, para que dos
 * notas simultáneas en cuerdas vecinas no se toquen. */
const MARGEN_CARRIL_PX = 5;
/** Alto mínimo de una nota: una nota muy corta a tempo bajo saldría como una
 * línea de un píxel, invisible. Crece hacia arriba, nunca hacia el ataque. */
const ALTO_MINIMO_PX = 6;
/** Alto por debajo del cual no cabe el número de traste dentro de la nota. */
const ALTO_PARA_TRASTE_PX = 18;

const TEXTO_CLASIFICACION: Record<Clasificacion, string> = {
  a_tiempo: "a tiempo",
  pronto: "pronto",
  tarde: "tarde",
};

/** Cómo llegó una pulsación. `null` NO es "a tiempo": es que no se supo cuándo
 * empezó, y decir que fue puntual sería inventárselo. */
function textoClasificacion(clasificacion: Clasificacion | null): string {
  return clasificacion === null ? "sin instante" : TEXTO_CLASIFICACION[clasificacion];
}

/** El desfase en milisegundos, con signo. Vacío si no se supo. */
function textoDesfase(desfaseS: number | null): string {
  if (desfaseS === null) return "";
  const ms = Math.round(desfaseS * 1000);
  return `(${ms > 0 ? "+" : ""}${ms} ms)`;
}

/** El nombre de la nota, que lo trae la pieza y no la pulsación. */
function nombreDeTocada(pieza: Pieza, tocada: NotaTocada): string {
  return pieza.notas[tocada.indice]?.nombre ?? `MIDI ${tocada.midi}`;
}

/**
 * Cuántos carriles horizontales hay que repartir: las cuerdas del instrumento
 * en el que está escrita la pieza.
 *
 * Mientras no ha llegado `/api/perfiles` se usa la cuerda más alta que la pieza
 * toca, que basta para que ninguna nota caiga fuera del lienzo; en cuanto llega
 * el perfil, los carriles son los del instrumento de verdad.
 */
function cuerdasDeLaPieza(pieza: Pieza, perfiles: PerfilAfinacion[]): number {
  const perfil = perfiles.find((p) => p.clave === pieza.perfil);
  if (perfil !== undefined && perfil.cuerdas.length > 0) return perfil.cuerdas.length;
  return pieza.notas.reduce((maximo, nota) => Math.max(maximo, nota.cuerda), 1);
}

/** El lienzo preparado para pintar: su contexto y su tamaño en píxeles CSS. */
interface LienzoPreparado {
  contexto: CanvasRenderingContext2D;
  ancho: number;
  alto: number;
}

/**
 * Ajusta el lienzo a los píxeles REALES de la pantalla y devuelve su contexto.
 *
 * Sin esto el carril se ve borroso en cualquier pantalla con
 * `devicePixelRatio > 1`: el lienzo tendría un píxel de dibujo por cada píxel
 * CSS y el navegador lo escalaría. Se dibuja en píxeles CSS y la densidad la
 * aplica la transformación del contexto, así que ni la geometría ni los grosores
 * tienen que saber nada de esto.
 *
 * Devuelve `null` cuando todavía no hay nada que pintar: el lienzo aún no tiene
 * tamaño, o no hay contexto 2D (es lo que pasa en jsdom, donde no hay canvas de
 * verdad).
 */
function prepararLienzo(lienzo: HTMLCanvasElement): LienzoPreparado | null {
  const ancho = lienzo.clientWidth;
  const alto = lienzo.clientHeight;
  if (ancho <= 0 || alto <= 0) return null;

  const densidad = window.devicePixelRatio || 1;
  const anchoReal = Math.round(ancho * densidad);
  const altoReal = Math.round(alto * densidad);
  // Asignar `width` o `height` borra el lienzo, así que solo se tocan cuando
  // cambian de verdad (al redimensionar la ventana o cambiar de pantalla).
  if (lienzo.width !== anchoReal) lienzo.width = anchoReal;
  if (lienzo.height !== altoReal) lienzo.height = altoReal;

  const contexto = lienzo.getContext("2d");
  if (contexto === null) return null;
  contexto.setTransform(densidad, 0, 0, densidad, 0, 0);
  return { contexto, ancho, alto };
}

/**
 * Un cuadro del carril.
 *
 * El fondo del lienzo es la línea de ataque: ahí suena la nota que toca ahora, y
 * las futuras bajan hacia ella. `indices` dice en qué posición de la pieza está
 * cada nota, que es lo que permite cruzarla con las pulsaciones ya adjudicadas
 * (`estado.tocadas` habla por índice).
 */
function pintarCuadro(
  contexto: CanvasRenderingContext2D,
  lienzo: LienzoCarril,
  pieza: Pieza,
  estado: EstadoCarril | null,
  instanteS: number,
  indices: Map<NotaDePieza, number>
): void {
  contexto.fillStyle = COLOR_FONDO;
  contexto.fillRect(0, 0, lienzo.ancho, lienzo.alto);

  // Un carril por cuerda, separados por una línea fina.
  const anchoCarril = lienzo.ancho / lienzo.cuerdas;
  contexto.strokeStyle = COLOR_SEPARADOR;
  contexto.lineWidth = 1;
  for (let i = 1; i < lienzo.cuerdas; i += 1) {
    const x = Math.round(i * anchoCarril) + 0.5;
    contexto.beginPath();
    contexto.moveTo(x, 0);
    contexto.lineTo(x, lienzo.alto);
    contexto.stroke();
  }

  const tocadas = new Map<number, NotaTocada>(
    (estado?.tocadas ?? []).map((tocada) => [tocada.indice, tocada])
  );

  contexto.textAlign = "center";
  contexto.font = "600 11px system-ui, sans-serif";
  for (const nota of notasVisibles(pieza.notas, instanteS, pieza.tempo, VENTANA_VISIBLE_S)) {
    const rectangulo = rectanguloDeNota(nota, instanteS, pieza.tempo, lienzo, VENTANA_VISIBLE_S);
    const indice = indices.get(nota);
    const tocada = indice === undefined ? undefined : tocadas.get(indice);

    // `rectangulo.y` es el borde de ATAQUE, el INFERIOR: el que llega primero a
    // la línea de ataque. La esquina superior, que es la que pide `fillRect`,
    // está un alto más arriba. Pasar `y` a secas pintaría fuera del lienzo.
    const alto = Math.max(rectangulo.alto, ALTO_MINIMO_PX);
    const arriba = rectangulo.y - alto;

    contexto.fillStyle = tocada === undefined ? COLOR_PENDIENTE : colorDeDesviacion(tocada.cents);
    contexto.fillRect(
      rectangulo.x + MARGEN_CARRIL_PX,
      arriba,
      Math.max(rectangulo.ancho - 2 * MARGEN_CARRIL_PX, 1),
      alto
    );

    if (alto >= ALTO_PARA_TRASTE_PX) {
      contexto.fillStyle = COLOR_TRASTE;
      contexto.fillText(String(nota.traste), rectangulo.x + rectangulo.ancho / 2, rectangulo.y - 5);
    }
  }

  // La línea de ataque, al final para que ninguna nota la tape.
  contexto.strokeStyle = COLOR_LINEA_ATAQUE;
  contexto.lineWidth = 2;
  contexto.beginPath();
  contexto.moveTo(0, lienzo.alto - 1);
  contexto.lineTo(lienzo.ancho, lienzo.alto - 1);
  contexto.stroke();
}

/** El resumen de la pieza terminada: cómo llegó cada nota que se pudo adjudicar. */
function ResumenCarril({ pieza, estado }: { pieza: Pieza; estado: EstadoCarril }) {
  const acertadas = estado.tocadas.filter((tocada) => tocada.acertada).length;
  return (
    <div className="resumen-carril">
      <h3>Pieza terminada</h3>
      <p className="resumen-informe">
        {acertadas} de {estado.total} notas acertadas
      </p>
      <ul className="desviaciones-carril">
        {estado.tocadas.map((tocada) => (
          <li key={tocada.indice}>
            <span
              className="punto-desviacion"
              style={{ background: colorDeDesviacion(tocada.cents) }}
            />
            {nombreDeTocada(pieza, tocada)} — {textoClasificacion(tocada.clasificacion)}{" "}
            {textoDesfase(tocada.desfase_s)}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Pantalla del carril: elige la pieza, la toca y la resume. */
export function Carril() {
  const { estado, pieza, error, iniciando, instante, iniciar, detener } = useCarril();
  const [familias, setFamilias] = useState<FamiliaEjercicio[]>([]);
  const [perfiles, setPerfiles] = useState<PerfilAfinacion[]>([]);
  const [familia, setFamilia] = useState(FAMILIA_POR_DEFECTO);
  const [tempo, setTempo] = useState("");

  const lienzoRef = useRef<HTMLCanvasElement | null>(null);
  /** El último estado, para que el bucle de dibujo lo lea sin reiniciarse en
   * cada paquete: treinta reinicios por segundo del bucle de animación. */
  const estadoRef = useRef<EstadoCarril | null>(estado);

  useEffect(() => {
    fetch("/api/ejercicios/familias")
      .then((r) => r.json())
      .then(setFamilias);
  }, []);

  useEffect(() => {
    fetch("/api/perfiles")
      .then((r) => r.json())
      .then(setPerfiles);
  }, []);

  useEffect(() => {
    estadoRef.current = estado;
  }, [estado]);

  const cuerdas = useMemo(
    () => (pieza === null ? 1 : cuerdasDeLaPieza(pieza, perfiles)),
    [pieza, perfiles]
  );

  /** En qué posición de la pieza está cada nota. `notasVisibles` devuelve las
   * mismas notas que recibe, así que esta tabla sirve para reconocerlas. */
  const indices = useMemo(() => {
    const mapa = new Map<NotaDePieza, number>();
    pieza?.notas.forEach((nota, indice) => mapa.set(nota, indice));
    return mapa;
  }, [pieza]);

  const completado = estado?.completado === true;
  const dibujando = pieza !== null && !completado;

  useEffect(() => {
    if (!dibujando || pieza === null) return;
    const lienzo = lienzoRef.current;
    if (lienzo === null) return;

    // La marca que da `requestAnimationFrame` es de la misma línea temporal que
    // `performance.now()`, así que sirve tal cual para preguntarle el instante
    // al reloj: no hace falta -ni debe- consultar el tiempo otra vez aquí.
    let cuadro = requestAnimationFrame(function dibujar(ahoraLocal: number) {
      cuadro = requestAnimationFrame(dibujar);
      const preparado = prepararLienzo(lienzo);
      if (preparado === null) return;
      pintarCuadro(
        preparado.contexto,
        { ancho: preparado.ancho, alto: preparado.alto, cuerdas },
        pieza,
        estadoRef.current,
        instante(ahoraLocal),
        indices
      );
    });

    // Un bucle que sobrevive al componente sigue dibujando sobre un canvas que
    // ya no está en el documento.
    return () => cancelAnimationFrame(cuadro);
  }, [dibujando, pieza, cuerdas, indices, instante]);

  if (pieza === null) {
    const empezar = () => {
      const parametros: Record<string, unknown> = {};
      const numero = Number(tempo);
      if (tempo !== "" && Number.isFinite(numero)) parametros.tempo = numero;
      void iniciar({ familia, parametros });
    };

    return (
      <section className="configurador carril-configurador">
        <p className="descripcion-familia">
          Las notas vienen hacia ti: toca cada una cuando llegue a la línea de abajo.
        </p>
        <div className="selector">
          {familias.length > 0 && (
            <>
              <label htmlFor="carril-familia">Ejercicio</label>
              <select
                id="carril-familia"
                value={familia}
                onChange={(evento) => setFamilia(evento.target.value)}
              >
                {familias.map((f) => (
                  <option key={f.clave} value={f.clave}>
                    {f.nombre}
                  </option>
                ))}
              </select>
            </>
          )}

          <div className="control">
            <label htmlFor="carril-tempo">Tempo</label>
            <input
              id="carril-tempo"
              type="number"
              value={tempo}
              placeholder="el del generador"
              onChange={(evento) => setTempo(evento.target.value)}
            />
          </div>
        </div>

        {error !== null && <p className="error-ejercicio">{error}</p>}

        <button type="button" disabled={iniciando} onClick={empezar}>
          Empezar
        </button>
      </section>
    );
  }

  const total = estado?.total ?? pieza.notas.length;

  return (
    <section className="carril-en-curso">
      <h2>{pieza.nombre}</h2>

      {/* La pausa se dice, no se disimula: el carril está quieto porque no llega
          señal del cable, y eso se arregla volviendo a tocar. */}
      {estado?.pausado === true && (
        <p className="aviso-carril pausado">
          Carril pausado: no llega señal del cable. Se reanuda en cuanto vuelvas a tocar.
        </p>
      )}

      {dibujando && (
        <canvas className="lienzo-carril" data-testid="lienzo-carril" ref={lienzoRef} />
      )}

      {completado && estado !== null && <ResumenCarril pieza={pieza} estado={estado} />}

      <p className="contador-progreso">
        {Math.min(estado?.indice_actual ?? 0, total)} / {total}
      </p>

      <button type="button" onClick={() => void detener()}>
        {completado ? "Otra vez" : "Detener"}
      </button>
    </section>
  );
}
