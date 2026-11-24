import { useEffect, useMemo, useRef, useState } from "react";

import {
  VENTANA_VISIBLE_S,
  acordesVisibles,
  colorDeCuerda,
  colorDeDesviacion,
  colorDeTextoSobre,
  ligaduraDeAcorde,
  notasVisibles,
  rectanguloDeNota,
  yDeLaLineaDeAtaque,
  type LienzoCarril,
} from "./geometriaCarril";
import { ControlesEstudio } from "./ControlesEstudio";
import { SelectorDeAcordes } from "./SelectorDeAcordes";
import type { PerfilAfinacion } from "./tipos";
import type { FamiliaEjercicio } from "./tiposEjercicio";
import type { EstadoEstudio } from "./tiposEstudio";
import type { Clasificacion, NotaDePieza, NotaTocada, Pieza } from "./tiposPieza";
import { InformePasada } from "./InformePasada";
import { useCarril, type InformeConHistorial, type PeticionPieza } from "./useCarril";
import { VistaEscrita } from "./VistaEscritaPieza";

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

const COLOR_FONDO = "#12161b";
const COLOR_SEPARADOR = "#262d36";
const COLOR_LINEA_ATAQUE = "#e6e9ee";

/** Hueco a cada lado del carril de una cuerda, en píxeles CSS, para que dos
 * notas simultáneas en cuerdas vecinas no se toquen. */
const MARGEN_CARRIL_PX = 5;
/** Alto mínimo de una nota: una nota muy corta a tempo bajo saldría como una
 * línea de un píxel, invisible. Crece hacia arriba, nunca hacia el ataque. */
const ALTO_MINIMO_PX = 6;
/** Alto por debajo del cual no cabe el número de traste dentro de la nota. */
const ALTO_PARA_TRASTE_PX = 18;

/** Hueco vertical entre una nota y la siguiente de la MISMA cuerda.
 *
 * Se lo quita al alto por el borde de arriba, nunca por el de ataque: el borde
 * inferior es el que marca cuándo suena y moverlo mentiría sobre el tiempo. Sin
 * este hueco, tres notas seguidas en una cuerda se pintaban pegadas y se leían
 * como un solo bloque alto. */
const SEPARACION_NOTAS_PX = 3;

/** Radio de la esquina redondeada de una nota. */
const RADIO_NOTA_PX = 4;

/** Cuánto se apaga la nota más lejana del carril, de 0 (nada) a 1 (invisible).
 *
 * Da profundidad: lo que viene de lejos se ve más tenue y lo inminente destaca,
 * que es lo que hace que el carril se lea como algo que viene hacia ti y no
 * como una lista. No llega nunca a 1: una nota invisible es una nota que el
 * usuario no sabe que tiene que tocar. */
const DESVANECIDO_MAXIMO = 0.55;

/** La franja de debajo de la línea de ataque, donde queda la estela. */
const COLOR_ESTELA = "#0b0e12";
/** Tinte del carril de cada cuerda sobre el fondo. */
const ALFA_FRANJA_CUERDA = 0.05;
/** El borde que distingue una nota YA TOCADA de una pendiente, además del
 * color: los colores de cuerda y los del veredicto comparten gama, y la
 * posición (encima o debajo de la línea) no basta en el instante del cruce. */
const COLOR_BORDE_TOCADA = "#ffffff";
/**
 * La ligadura que une las notas de un acorde: un trazo a la altura del ataque,
 * del centro de la cuerda más grave al de la más aguda del grupo.
 *
 * Es BLANCA y no del color de ninguna cuerda porque no es de ninguna: cada
 * cuerda ya tiene su color, y pintar la ligadura de uno de ellos diría que esa
 * manda. Y es el único trazo blanco del lienzo además de la línea de ataque, que
 * es lo que las empareja: la línea dice *cuándo* se toca y la ligadura *qué* se
 * toca de una vez.
 *
 * Tenue (`ALFA_LIGADURA`) a propósito: une sin tapar. Lo que se lee es la nota y
 * su traste; la ligadura solo dice que van juntas.
 */
const COLOR_LIGADURA = "#e6e9ee";
/**
 * Lo que mide la CABEZA de una nota, en pixeles, por larga que sea la nota.
 *
 * 54 px es algo menos de un tercio de segundo a la velocidad del carril: lo
 * bastante para que quepa el numero del traste dentro y para que el ojo la lea
 * como una ficha, no como una franja.
 */
const ALTO_CABEZA_PX = 54;
/** El ancho de la cola, en fraccion del carril de la cuerda. */
const FRACCION_COLA = 0.34;
const ALFA_COLA = 0.45;
const ALFA_LIGADURA = 0.6;
/**
 * Lo que la ligadura se separa del borde de arriba de las cabezas.
 *
 * Pegada al borde se come la mitad de su grosor con la cabeza y lo que queda es
 * una pestaña gris que no parece dibujada a propósito. Cinco píxeles bastan para
 * que se lea como una barra que ata las cabezas.
 */
const SEPARACION_LIGADURA_PX = 5;
const GROSOR_LIGADURA_PX = 3;

const TEXTO_CLASIFICACION: Record<Clasificacion, string> = {
  a_tiempo: "a tiempo",
  pronto: "pronto",
  tarde: "tarde",
};

/**
 * Cómo llegó una nota, y por qué camino se supo.
 *
 * Tres casos y tres textos distintos, porque son tres cosas distintas:
 *
 * - Una nota cobrada por PRESENCIA (`por_presencia`) es una cuerda de un acorde
 *   que no tuvo ataque propio: el rasgueo fue uno solo. No es que su instante se
 *   perdiera, es que no existe, así que se dice "en el acorde" y no "sin
 *   instante", que sonaría a medición fallida.
 * - `clasificacion` nula con ataque sí es una medición que no se pudo hacer: no se
 *   supo cuándo empezó.
 * - Y si hay clasificación, se dice.
 *
 * En ninguno de los dos primeros casos se dice "a tiempo": sería inventárselo.
 */
function textoClasificacion(tocada: NotaTocada): string {
  if (tocada.por_presencia) return "en el acorde";
  return tocada.clasificacion === null
    ? "sin instante"
    : TEXTO_CLASIFICACION[tocada.clasificacion];
}

/** El desfase en milisegundos, con signo. Vacío si no se supo. */
function textoDesfase(desfaseS: number | null): string {
  if (desfaseS === null) return "";
  const ms = Math.round(desfaseS * 1000);
  return `(${ms > 0 ? "+" : ""}${ms} ms)`;
}

/**
 * Las clases de una fila del resumen. Dos marcas independientes: fallar es una
 * cosa y haberse sabido por presencia es otra, y una nota de acorde ausente no
 * aparece en esta lista (se queda sin cobrar), así que las dos nunca coinciden
 * hoy. Se escriben como clases separadas igualmente, porque combinarlas en una
 * sola obligaría a tocar las dos el día que cambie una.
 */
function clasesDeFila(tocada: NotaTocada): string | undefined {
  const clases = [
    tocada.acertada ? null : "nota-fallada",
    tocada.por_presencia ? "nota-por-presencia" : null,
  ].filter((c) => c !== null);
  return clases.length === 0 ? undefined : clases.join(" ");
}

/** El nombre de la nota PEDIDA, que lo trae la pieza y no la pulsación. */
function nombrePedido(pieza: Pieza, tocada: NotaTocada): string {
  return pieza.notas[tocada.indice]?.nombre ?? `MIDI ${tocada.midi}`;
}

/**
 * Qué nota es cada fila del resumen: la pedida, y lo que sonó cuando no fue esa.
 *
 * Todas las filas decían el nombre ESPERADO, así que debajo de «3 de 9 notas
 * acertadas» venían nueve líneas idénticas en lo que importa y nada distinguía
 * las acertadas de las falladas. El color del punto es la desviación en cents,
 * que es otra cosa: una nota equivocada puede estar perfectamente afinada. El
 * veredicto es `acertada`, que lo publica el núcleo, y la forma de decirlo es la
 * misma que ya usa la vista escrita.
 */
function textoDeFila(pieza: Pieza, tocada: NotaTocada): string {
  const pedida = nombrePedido(pieza, tocada);
  return tocada.acertada ? pedida : `Pedida ${pedida}, tocaste ${tocada.nombre}`;
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
 * La línea de ataque es donde suena la nota que toca ahora: las futuras bajan
 * hacia ella y las que ya sonaron siguen bajando por debajo, en la estela, para
 * que se vea de un vistazo el patrón de lo que acabas de tocar (spec §4).
 * `indices` dice en qué posición de la pieza está cada nota, que es lo que
 * permite cruzarla con las pulsaciones ya adjudicadas (`estado.tocadas` habla
 * por índice).
 */
function pintarCuadro(
  contexto: CanvasRenderingContext2D,
  lienzo: LienzoCarril,
  pieza: Pieza,
  estado: EstadoEstudio | null,
  instanteS: number,
  indices: Map<NotaDePieza, number>
): void {
  contexto.fillStyle = COLOR_FONDO;
  contexto.fillRect(0, 0, lienzo.ancho, lienzo.alto);

  const anchoCarril = lienzo.ancho / lienzo.cuerdas;
  const lineaAtaque = yDeLaLineaDeAtaque(lienzo, VENTANA_VISIBLE_S);

  // El carril de cada cuerda, tenido con SU color. Es el mismo idioma que el de
  // las notas: la franja dice de quien es el carril aunque este vacio.
  for (let i = 0; i < lienzo.cuerdas; i += 1) {
    contexto.globalAlpha = ALFA_FRANJA_CUERDA;
    contexto.fillStyle = colorDeCuerda(i + 1);
    contexto.fillRect(i * anchoCarril, 0, anchoCarril, lienzo.alto);
    contexto.globalAlpha = 1;
  }

  // La estela, mas oscura que el resto: separa de un vistazo lo que YA sono de
  // lo que viene, sin tener que localizar la linea.
  contexto.fillStyle = COLOR_ESTELA;
  contexto.fillRect(0, lineaAtaque, lienzo.ancho, lienzo.alto - lineaAtaque);

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
  contexto.textBaseline = "middle";
  const tempoEfectivo = tempoParaDibujar(pieza, estado);
  const visibles = notasVisibles(pieza.notas, instanteS, tempoEfectivo, VENTANA_VISIBLE_S);

  for (const nota of visibles) {
    const rectangulo = rectanguloDeNota(nota, instanteS, tempoEfectivo, lienzo, VENTANA_VISIBLE_S);
    const indice = indices.get(nota);
    const tocada = indice === undefined ? undefined : tocadas.get(indice);

    // `rectangulo.y` es el borde de ATAQUE, el INFERIOR: el que llega primero a
    // la linea de ataque. La esquina superior esta un alto mas arriba. El hueco
    // entre notas se le quita a ese borde de arriba, nunca al de ataque.
    const alto = Math.max(rectangulo.alto - SEPARACION_NOTAS_PX, ALTO_MINIMO_PX);
    const arriba = rectangulo.y - alto;
    const x = rectangulo.x + MARGEN_CARRIL_PX;
    const ancho = Math.max(rectangulo.ancho - 2 * MARGEN_CARRIL_PX, 1);

    // Profundidad: lo que esta lejos de la linea se pinta mas tenue. Por debajo
    // de la linea -la estela- no se desvanece: ya sono y es lo que se mira para
    // ver el patron.
    const distancia = Math.min(Math.max((lineaAtaque - rectangulo.y) / lineaAtaque, 0), 1);
    contexto.globalAlpha = 1 - DESVANECIDO_MAXIMO * distancia;

    const colorNota =
      tocada === undefined ? colorDeCuerda(nota.cuerda) : colorDeDesviacion(tocada);

    // CABEZA Y COLA.
    //
    // Una nota larga -un acorde dura un compas entero, cuatro segundos a 60 ppm-
    // pintada de una pieza es un bloque de color mas alto que la ventana: cinco
    // de ellos a la vez son un muro, y el acorde deja de leerse. Asi que la nota
    // se parte en lo que de verdad son dos cosas distintas: el ATAQUE, que es un
    // instante y es lo que hay que acertar, y lo que dura, que es dejarla sonar.
    //
    // La cabeza mide siempre lo mismo y va pegada al borde de ataque; la cola es
    // el resto, mas estrecha y mas tenue. Una nota corta no tiene cola y se pinta
    // exactamente como antes: esto no cambia el carril monofonico.
    const altoCabeza = Math.min(alto, ALTO_CABEZA_PX);
    const arribaCabeza = rectangulo.y - altoCabeza;
    if (alto > altoCabeza) {
      const anchoCola = Math.max(ancho * FRACCION_COLA, 2);
      const alfa = contexto.globalAlpha;
      contexto.globalAlpha = alfa * ALFA_COLA;
      contexto.fillStyle = colorNota;
      dibujarNota(
        contexto, x + (ancho - anchoCola) / 2, arriba, anchoCola, alto - altoCabeza
      );
      contexto.fill();
      contexto.globalAlpha = alfa;
    }

    contexto.fillStyle = colorNota;
    dibujarNota(contexto, x, arribaCabeza, ancho, altoCabeza);
    contexto.fill();

    if (tocada !== undefined) {
      contexto.strokeStyle = COLOR_BORDE_TOCADA;
      contexto.lineWidth = 2;
      dibujarNota(contexto, x, arribaCabeza, ancho, altoCabeza);
      contexto.stroke();
    }

    if (altoCabeza >= ALTO_PARA_TRASTE_PX) {
      contexto.fillStyle = colorDeTextoSobre(colorNota);
      contexto.font = "700 13px system-ui, sans-serif";
      contexto.fillText(String(nota.traste), x + ancho / 2, arribaCabeza + altoCabeza / 2);
    } else {
      // No cabe dentro: va justo encima, en el color de la cuerda, para que una
      // nota corta no se quede sin decir que traste es.
      contexto.fillStyle = colorNota;
      contexto.font = "700 11px system-ui, sans-serif";
      contexto.fillText(String(nota.traste), x + ancho / 2, arribaCabeza - 8);
    }
    contexto.globalAlpha = 1;
  }

  // La ligadura del rasgueo, por ENCIMA de las cabezas: un acorde es un gesto,
  // no cinco notas que coinciden. Sin ella hay que comparar cinco alturas para
  // saber si hay que rasguear o puntear, y es lo primero que la mano necesita
  // saber. Va despues del bucle de las notas porque en el borde de ataque -el
  // sitio obvio- quedaba debajo de las cabezas y encima de la linea, tapada por
  // las dos.
  for (const grupo of acordesVisibles(visibles)) {
    const ligadura = ligaduraDeAcorde(
      grupo, instanteS, tempoEfectivo, lienzo, VENTANA_VISIBLE_S, ALTO_CABEZA_PX
    );
    const distancia = Math.min(Math.max((lineaAtaque - ligadura.y) / lineaAtaque, 0), 1);
    // Se desvanece con la distancia igual que las notas: si no, un acorde del
    // fondo del carril llegaba antes al ojo que la nota que hay que tocar ahora.
    contexto.globalAlpha = (1 - DESVANECIDO_MAXIMO * distancia) * ALFA_LIGADURA;
    contexto.strokeStyle = COLOR_LIGADURA;
    contexto.lineWidth = GROSOR_LIGADURA_PX;
    contexto.lineCap = "round";
    contexto.beginPath();
    const yLigadura = ligadura.y - SEPARACION_LIGADURA_PX;
    contexto.moveTo(ligadura.desde, yLigadura);
    contexto.lineTo(ligadura.hasta, yLigadura);
    contexto.stroke();
    contexto.globalAlpha = 1;
  }

  // La linea de ataque, al final para que ninguna nota la tape. No va en el
  // borde de abajo: debajo queda la estela, y donde cae lo dice la geometria.
  // Se pinta con un halo -tres trazos cada vez mas anchos y mas tenues- porque
  // una linea de 2 px se perdia entre las notas justo donde hay que mirar.
  for (const [grosor, alfa] of [
    [10, 0.1],
    [5, 0.2],
    [2, 1],
  ] as const) {
    contexto.globalAlpha = alfa;
    contexto.strokeStyle = COLOR_LINEA_ATAQUE;
    contexto.lineWidth = grosor;
    contexto.beginPath();
    contexto.moveTo(0, lineaAtaque);
    contexto.lineTo(lienzo.ancho, lineaAtaque);
    contexto.stroke();
  }
  contexto.globalAlpha = 1;

  // La diana de cada cuerda sobre la linea: dice de que color es cada carril
  // aunque no venga ninguna nota, que es como se aprende el codigo de colores.
  for (let i = 0; i < lienzo.cuerdas; i += 1) {
    contexto.fillStyle = colorDeCuerda(i + 1);
    contexto.fillRect(i * anchoCarril + MARGEN_CARRIL_PX, lineaAtaque - 1, 
      Math.max(anchoCarril - 2 * MARGEN_CARRIL_PX, 1), 3);
  }
}

/** El contorno de una nota: un rectangulo de esquinas redondeadas.
 *
 * `roundRect` no existe en jsdom ni en navegadores viejos, asi que se degrada a
 * un rectangulo recto en vez de romper el dibujo entero. */
function dibujarNota(
  contexto: CanvasRenderingContext2D,
  x: number,
  y: number,
  ancho: number,
  alto: number
): void {
  contexto.beginPath();
  if (typeof contexto.roundRect === "function") {
    contexto.roundRect(x, y, ancho, alto, Math.min(RADIO_NOTA_PX, ancho / 2, alto / 2));
  } else {
    contexto.rect(x, y, ancho, alto);
  }
}


/**
 * El tempo con el que se convierten los pulsos en segundos al dibujar.
 *
 * Es el EFECTIVO (tempo escrito por el factor de práctica), porque el reloj del
 * servidor ya corre estirado: a la mitad de velocidad, cada pulso dura el doble. Con
 * el tempo escrito las notas viajarían al doble de velocidad que el reloj. Mientras
 * no ha llegado un paquete que lo traiga -o llega el del carril apagado, que lo
 * manda a 0 y dividir entre él no dibuja nada- vale el de la pieza.
 */
function tempoParaDibujar(pieza: Pieza, estado: EstadoEstudio | null): number {
  const efectivo = estado?.tempo_efectivo;
  return efectivo !== undefined && efectivo > 0 ? efectivo : pieza.tempo;
}

/**
 * Si el tramo que se estudia es la pieza ENTERA.
 *
 * Hace falta porque `completado` significa ahora «se acabó el TRAMO» (el núcleo lo
 * sobrescribe a propósito), y `estado.total` sigue siendo las notas de la pieza
 * entera: practicando los compases 3-4 de una pieza de 12 y acertando las dos
 * notas, `ResumenCarril` titulaba «Pieza terminada» y decía «2 de 12». En la etapa
 * 3a el resumen era correcto porque `completado` solo significaba el final de la
 * pieza; la ampliación del significado es de la 3c, así que era una regresión.
 *
 * Se decide con los compases y no contando qué notas caen en el tramo: la interfaz
 * NO convierte pulsos en compases (ver `tiposEstudio.ts`), y para contar las notas
 * del tramo habría que hacer justo esa cuenta. Quien sí la sabe hacer es el núcleo,
 * y su respuesta es el informe por compases, que se abre al lado y dice la verdad.
 */
function elTramoEsLaPiezaEntera(estado: EstadoEstudio): boolean {
  return estado.primer_compas === 1 && estado.ultimo_compas === estado.total_de_compases;
}

/** El resumen de la pieza terminada: cómo llegó cada nota que se pudo adjudicar. */
function ResumenCarril({ pieza, estado }: { pieza: Pieza; estado: EstadoEstudio }) {
  const acertadas = estado.tocadas.filter((tocada) => tocada.acertada).length;
  return (
    <div className="resumen-carril">
      <h3>Pieza terminada</h3>
      <p className="resumen-informe">
        {acertadas} de {estado.total} notas acertadas
      </p>
      <ul className="desviaciones-carril">
        {estado.tocadas.map((tocada) => (
          <li
            key={tocada.indice}
            className={clasesDeFila(tocada)}
            data-testid={tocada.acertada ? "fila-acertada" : "fila-fallada"}
            data-por-presencia={tocada.por_presencia ? "si" : undefined}
          >
            <span
              className="punto-desviacion"
              style={{ background: colorDeDesviacion(tocada) }}
            />
            {textoDeFila(pieza, tocada)} — {textoClasificacion(tocada)}{" "}
            {textoDesfase(tocada.desfase_s)}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface PropiedadesCarril {
  /**
   * Una pieza que YA viene elegida de otra pantalla: hoy, la canción y la pista
   * que el usuario escogió en `Canciones`. Se arranca al montar y entonces no se
   * ofrece el configurador de ejercicios, que no es lo que el usuario pidió.
   *
   * `null` -o nada- es el carril de siempre: elige tú el ejercicio aquí.
   */
  peticion?: PeticionPieza | null;
}

/** Pantalla del carril: elige la pieza, la toca y la resume. */
export function Carril({ peticion = null }: PropiedadesCarril) {
  const {
    estado,
    pieza,
    secciones,
    conectado,
    error,
    iniciando,
    instante,
    iniciar,
    detener,
    cambiarPlan,
    saltar,
    pausar,
    acompanamiento,
    machacar,
    leerInforme,
  } = useCarril(undefined, peticion === null);
  const [familias, setFamilias] = useState<FamiliaEjercicio[]>([]);
  const [perfiles, setPerfiles] = useState<PerfilAfinacion[]>([]);
  // La familia la elige el usuario de entre las que publica el servidor. Nunca
  // se escribe aquí una clave del catálogo: la primera que llega es la que queda
  // seleccionada, igual que en `Configurador`.
  const [familia, setFamilia] = useState("");
  const [tempo, setTempo] = useState("");
  /**
   * Los acordes elegidos para la familia de cambios, en orden. Vacío = los que
   * traiga el generador.
   *
   * El carril se alimenta del MISMO catálogo de familias que el configurador de
   * ejercicios, así que «Cambios de acorde» es elegible aquí; y desde que
   * `pieza_desde_ejercicio` traduce los acordes a grupos de notas simultáneas,
   * tocarlos en el carril es una pasada de verdad, con su informe.
   */
  const [acordesElegidos, setAcordesElegidos] = useState<string[]>([]);
  // Carril para tocar a tempo; escrita para leer la pieza y repasar lo tocado.
  const [vista, setVista] = useState<"carril" | "escrita">("carril");
  // El informe de la pasada, tal como estaba al pedirlo: es una foto, no se
  // actualiza solo. Lleva el arranque de la pieza que lo pidió, y solo se enseña
  // mientras sea la que está en pantalla: así no sale encima de la siguiente.
  const [pedido, setPedido] = useState<{ arranque: number; datos: InformeConHistorial } | null>(
    null
  );
  const informe = pedido !== null && pedido.arranque === estado?.arranque ? pedido.datos : null;
  const setInforme = (datos: InformeConHistorial | null) =>
    setPedido(datos === null || estado === null ? null : { arranque: estado.arranque, datos });

  const lienzoRef = useRef<HTMLCanvasElement | null>(null);
  /** El último estado, para que el bucle de dibujo lo lea sin reiniciarse en
   * cada paquete: treinta reinicios por segundo del bucle de animación. */
  const estadoRef = useRef<EstadoEstudio | null>(estado);

  useEffect(() => {
    fetch("/api/ejercicios/familias")
      .then((r) => r.json())
      .then((datos: FamiliaEjercicio[]) => {
        setFamilias(datos);
        if (datos.length > 0) setFamilia(datos[0].clave);
      });
  }, []);

  useEffect(() => {
    fetch("/api/perfiles")
      .then((r) => r.json())
      .then(setPerfiles);
  }, []);

  useEffect(() => {
    estadoRef.current = estado;
  }, [estado]);

  /**
   * La pieza que viene pedida de otra pantalla se arranca al montar y UNA SOLA
   * vez. La marca hace falta porque `detener` vuelve a dejar `pieza` en `null`:
   * sin ella, el efecto la arrancaría otra vez, y otra, en bucle.
   *
   * NO se reinicia cuando `peticion` cambia, a propósito: no hay forma de
   * distinguir «otra canción» de «el mismo pedido en otro objeto», que es lo que
   * llega en cada render si quien la pasa la escribe en el JSX. El precio es que una
   * petición de verdad nueva sobre un carril ya montado se descartaría, y de eso se
   * encarga quien la pasa: `App` le pone una `key` que cambia con cada traspaso, así
   * que un pedido nuevo monta un carril nuevo con la marca limpia.
   */
  const yaPedida = useRef(false);
  useEffect(() => {
    if (peticion === null || yaPedida.current) return;
    yaPedida.current = true;
    void iniciar(peticion);
  }, [peticion, iniciar]);

  /**
   * Al terminar la pasada el informe aparece solo: el usuario acaba de tocar y
   * mira la pantalla, y pedirle un clic es pedirle que sepa que hay algo que
   * pedir. UNA vez por pasada: el carril publica a 30 Hz y `completado` se queda en
   * `true`, así que se recuerda que ya se pidió y se olvida al empezar otra
   * (`completado` vuelve a `false`, o la pieza se suelta y no hay estado).
   */
  const informePedidoAlTerminar = useRef<number | null>(null);
  const terminada = estado?.completado === true;
  const arranqueDeLaPasada = estado?.arranque;
  useEffect(() => {
    if (!terminada || arranqueDeLaPasada === undefined) {
      informePedidoAlTerminar.current = null;
      return;
    }
    // La ref guarda el arranque para el que ya se pidió: una pieza nueva que llegara
    // ya terminada en su primer paquete también pide el suyo.
    if (informePedidoAlTerminar.current === arranqueDeLaPasada) return;
    informePedidoAlTerminar.current = arranqueDeLaPasada;
    void leerInforme().then((datos) => {
      if (datos !== null) setPedido({ arranque: arranqueDeLaPasada, datos });
    });
  }, [terminada, arranqueDeLaPasada, leerInforme]);

  const cuerdas = useMemo(
    () => (pieza === null ? 1 : cuerdasDeLaPieza(pieza, perfiles)),
    [pieza, perfiles]
  );

  /** Cómo se llama cada cuerda del perfil, de la 1 a la última. */
  const etiquetas = useMemo(() => {
    const perfil = perfiles.find((p) => p.clave === pieza?.perfil);
    return perfil?.cuerdas
      .slice()
      .sort((a, b) => a.numero - b.numero)
      .map((cuerda) => cuerda.nota);
  }, [pieza, perfiles]);

  /** En qué posición de la pieza está cada nota. `notasVisibles` devuelve las
   * mismas notas que recibe, así que esta tabla sirve para reconocerlas. */
  const indices = useMemo(() => {
    const mapa = new Map<NotaDePieza, number>();
    pieza?.notas.forEach((nota, indice) => mapa.set(nota, indice));
    return mapa;
  }, [pieza]);

  const completado = estado?.completado === true;
  const dibujando = pieza !== null && !completado && vista === "carril";

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
    // Mientras el POST de una pieza pedida fuera está en vuelo no se ofrece el
    // configurador de ejercicios: el usuario eligió una canción y ver un selector
    // de escalas le haría creer que su elección se perdió. Si el arranque falla
    // (afinación que no coincide, archivo roto), `error` deja de ser nulo y abajo
    // se ve el motivo con el configurador, que es la salida que le queda.
    if (peticion !== null && error === null) {
      return <p className="aviso-carril">Preparando la canción…</p>;
    }

    /**
     * Si la familia elegida pide acordes. Se deduce de los PARÁMETROS que el
     * servidor publica para ella, no de su clave: comparar con "cambios" sería
     * escribir aquí una clave del catálogo, que es justo lo que esta pantalla
     * evita (ver `familia`).
     */
    const elegida = familias.find((f) => f.clave === familia);
    const pideAcordes = elegida?.parametros.includes("claves") === true;

    const empezar = () => {
      const parametros: Record<string, unknown> = {};
      const numero = Number(tempo);
      if (tempo !== "" && Number.isFinite(numero)) parametros.tempo = numero;
      // Solo si la familia elegida los declara: mandar `claves` a una escala es
      // un 400, y la lista vacía deja que el generador ponga los suyos.
      if (pideAcordes && acordesElegidos.length > 0) parametros.claves = acordesElegidos;
      // Si el catálogo todavía no ha llegado, la familia viaja vacía y el
      // servidor contesta cuáles hay (`SesionPractica.generar`). Es mejor que
      // adivinar una clave: lo que se ve seleccionado y lo que viaja son siempre
      // lo mismo.
      void iniciar({ familia, parametros });
    };

    return (
      <section className="configurador carril-configurador">
        <p className="descripcion-familia">
          {pideAcordes
            ? "Los acordes vienen hacia ti: rasguea cada uno cuando llegue a la línea de abajo."
            : "Las notas vienen hacia ti: toca cada una cuando llegue a la línea de abajo."}
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

          {pideAcordes && (
            <SelectorDeAcordes elegidas={acordesElegidos} alCambiar={setAcordesElegidos} />
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

  const pedirInforme = async () => setInforme(await leerInforme());
  /**
   * Machacar un compás del informe. OJO: esto NO usa la regla de los clics de la
   * rejilla (`rangoQueIncluye`, en `ControlesEstudio`), y la diferencia es a
   * propósito, no una incoherencia que arreglar:
   *
   * - Clic en la rejilla = «llévame ahí». Si el compás cae fuera del bucle, se
   *   MUEVE la ventana conservando su longitud, porque quien hizo clic quería ir a
   *   un sitio, no cambiar cuánto estudia.
   * - Machacar = «quiero ESTE compás». El bucle es de ese compás solo, y la
   *   longitud del bucle anterior no cuenta: conservarla metería en el bucle
   *   compases que nadie pidió machacar.
   *
   * Lo único que comparten es la regla del servidor (el compás tiene que estar en
   * el rango vigente antes del salto), que un bucle de un compás cumple por
   * construcción. Son dos cálculos distintos; no hay nada que unificar.
   */
  const machacarDesdeElInforme = async (compas: number) => {
    if (await machacar(compas)) setInforme(null);
  };

  return (
    <section className="carril-en-curso">
      <h2>{pieza.nombre}</h2>

      {/* Un WebSocket caído deja el carril quieto; decirlo es la diferencia
          entre "no llega el estado" y "el programa no funciona". Se reconecta
          solo, así que el aviso se va sin que el usuario haga nada. */}
      {!conectado && (
        <p className="aviso-carril pausado">
          Sin conexión con el servidor: el carril está quieto. Se reconecta solo.
        </p>
      )}

      {/* La pausa se dice, no se disimula: el carril está quieto porque no llega
          señal del cable, y eso se arregla volviendo a tocar.

          **PERO LA REGLA DE CUÁNDO SE ACUSA AL CABLE NO SE DECIDE AQUÍ**: viene
          decidida y publicada en `esperando_notas` (`se_esperan_notas`, en
          `servidor/piezas.py`), y esta línea la LEE. Aquí había una condición
          propia (`!completado`) y un comentario que afirmaba que era «la misma
          regla» del servidor; no lo era —al servidor le faltaba la pausa del
          usuario y a esta línea le faltaba todo lo demás—, así que en la pausa el
          panel de diagnóstico callaba y esta línea acusaba, y en un bucle las dos
          acusaban a quien descansaba la mano entre repeticiones. Dos mitades del
          mismo aviso con dos reglas distintas y un comentario diciendo que eran
          una.

          El precio, dicho: descansando en medio de un bucle esta línea ya no sale,
          y el carril se queda quieto sin decir nada. Es exactamente el silencio
          que la sesión ya no trata como avería —el usuario dejó de tocar y lo
          sabe—, y la alternativa medida era llamarle avería a su descanso. */}
      {estado?.pausado === true && estado.esperando_notas === true && (
        <p className="aviso-carril pausado">
          Carril pausado: no llega señal del cable. Se reanuda en cuanto vuelvas a tocar.
        </p>
      )}

      {/* Un rechazo del servidor a una orden (tempo, salto, pausa) no se pierde. */}
      {error !== null && <p className="error-ejercicio">{error}</p>}

      <div className="conmutador-vista" role="group" aria-label="Vista">
        <button type="button" aria-pressed={vista === "carril"} onClick={() => setVista("carril")}>
          Carril
        </button>
        <button type="button" aria-pressed={vista === "escrita"} onClick={() => setVista("escrita")}>
          Tablatura y pentagrama
        </button>
      </div>

      {vista === "escrita" && (
        <VistaEscrita pieza={pieza} estado={estado} cuerdas={cuerdas} etiquetas={etiquetas} />
      )}

      {dibujando && (
        <canvas className="lienzo-carril" data-testid="lienzo-carril" ref={lienzoRef} />
      )}

      {estado !== null && (
        <ControlesEstudio
          estado={estado}
          secciones={secciones}
          alCambiarPlan={cambiarPlan}
          alPausar={(activa) => void pausar(activa)}
          alSaltar={(compas) => void saltar(compas)}
          alAjustarAcompanamiento={acompanamiento}
        />
      )}

      {/* El resumen cuenta sobre la pieza ENTERA, así que solo se muestra cuando
          el tramo es la pieza entera. Acabar un tramo de dos compases no es
          terminar la pieza, y decirlo con las cifras de la pieza era mentir; el
          informe de la pasada, que sí sabe qué notas son del tramo, va debajo. */}
      {completado &&
        estado !== null &&
        (elTramoEsLaPiezaEntera(estado) ? (
          <ResumenCarril pieza={pieza} estado={estado} />
        ) : (
          <p className="aviso-carril">
            Tramo terminado: compases {estado.primer_compas} a {estado.ultimo_compas} de{" "}
            {estado.total_de_compases}. Lo tocado, compás a compás, está en el informe de
            la pasada.
          </p>
        ))}

      {/* `indice_actual` es un INDICE (base 0) y esto es una CUENTA: en la
          ultima nota de una pieza de 12 se leia «11 / 12». La cuenta de la nota
          en curso es su indice mas uno, y no pasa del total. */}
      <p className="contador-progreso">
        {Math.min((estado?.indice_actual ?? 0) + 1, total)} / {total}
      </p>

      <button type="button" onClick={() => void detener()}>
        {completado ? "Otra vez" : "Detener"}
      </button>

      {/* El informe va DEBAJO del lienzo y de los botones, no encima: al acabar la
          pasada aparece justo donde el usuario tiene los ojos, y si empujara el
          carril hacia abajo lo movería bajo su mirada. */}
      {informe === null ? (
        <button type="button" onClick={() => void pedirInforme()}>
          Ver el informe de la pasada
        </button>
      ) : (
        <>
          <InformePasada
            informe={informe.informe}
            historial={informe.historial}
            alMachacar={(compas) => void machacarDesdeElInforme(compas)}
          />
          <button type="button" onClick={() => void pedirInforme()}>
            Actualizar el informe
          </button>
          <button type="button" onClick={() => setInforme(null)}>
            Cerrar el informe
          </button>
        </>
      )}
    </section>
  );
}
