import { useEffect, useMemo, useRef, useState } from "react";

import {
  VENTANA_VISIBLE_S,
  colorDeDesviacion,
  notasVisibles,
  rectanguloDeNota,
  yDeLaLineaDeAtaque,
  type LienzoCarril,
} from "./geometriaCarril";
import { ControlesEstudio } from "./ControlesEstudio";
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
  const tempoEfectivo = tempoParaDibujar(pieza, estado);
  for (const nota of notasVisibles(pieza.notas, instanteS, tempoEfectivo, VENTANA_VISIBLE_S)) {
    const rectangulo = rectanguloDeNota(nota, instanteS, tempoEfectivo, lienzo, VENTANA_VISIBLE_S);
    const indice = indices.get(nota);
    const tocada = indice === undefined ? undefined : tocadas.get(indice);

    // `rectangulo.y` es el borde de ATAQUE, el INFERIOR: el que llega primero a
    // la línea de ataque. La esquina superior, que es la que pide `fillRect`,
    // está un alto más arriba. Pasar `y` a secas pintaría fuera del lienzo.
    const alto = Math.max(rectangulo.alto, ALTO_MINIMO_PX);
    const arriba = rectangulo.y - alto;

    contexto.fillStyle = tocada === undefined ? COLOR_PENDIENTE : colorDeDesviacion(tocada);
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

  // La línea de ataque, al final para que ninguna nota la tape. No va en el
  // borde de abajo: debajo queda la estela de las notas que ya sonaron, y donde
  // cae lo dice la geometría (`yDeLaLineaDeAtaque`), no este archivo.
  const lineaAtaque = yDeLaLineaDeAtaque(lienzo, VENTANA_VISIBLE_S);
  contexto.strokeStyle = COLOR_LINEA_ATAQUE;
  contexto.lineWidth = 2;
  contexto.beginPath();
  contexto.moveTo(0, lineaAtaque);
  contexto.lineTo(lienzo.ancho, lineaAtaque);
  contexto.stroke();
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
            className={tocada.acertada ? undefined : "nota-fallada"}
            data-testid={tocada.acertada ? "fila-acertada" : "fila-fallada"}
          >
            <span
              className="punto-desviacion"
              style={{ background: colorDeDesviacion(tocada) }}
            />
            {textoDeFila(pieza, tocada)} — {textoClasificacion(tocada.clasificacion)}{" "}
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

    const empezar = () => {
      const parametros: Record<string, unknown> = {};
      const numero = Number(tempo);
      if (tempo !== "" && Number.isFinite(numero)) parametros.tempo = numero;
      // Si el catálogo todavía no ha llegado, la familia viaja vacía y el
      // servidor contesta cuáles hay (`SesionPractica.generar`). Es mejor que
      // adivinar una clave: lo que se ve seleccionado y lo que viaja son siempre
      // lo mismo.
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

  const pedirInforme = async () => setInforme(await leerInforme());
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
          señal del cable, y eso se arregla volviendo a tocar. */}
      {estado?.pausado === true && (
        <p className="aviso-carril pausado">
          Carril pausado: no llega señal del cable. Se reanuda en cuanto vuelvas a tocar.
        </p>
      )}

      {/* Un rechazo del servidor a una orden (tempo, salto, pausa) no se pierde. */}
      {error !== null && <p className="error-ejercicio">{error}</p>}

      {estado !== null && (
        <ControlesEstudio
          estado={estado}
          secciones={secciones}
          alCambiarPlan={cambiarPlan}
          alPausar={(activa) => void pausar(activa)}
          alSaltar={(compas) => void saltar(compas)}
        />
      )}

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

      {dibujando && (
        <canvas className="lienzo-carril" data-testid="lienzo-carril" ref={lienzoRef} />
      )}

      {completado && estado !== null && <ResumenCarril pieza={pieza} estado={estado} />}

      {/* `indice_actual` es un INDICE (base 0) y esto es una CUENTA: en la
          ultima nota de una pieza de 12 se leia «11 / 12». La cuenta de la nota
          en curso es su indice mas uno, y no pasa del total. */}
      <p className="contador-progreso">
        {Math.min((estado?.indice_actual ?? 0) + 1, total)} / {total}
      </p>

      <button type="button" onClick={() => void detener()}>
        {completado ? "Otra vez" : "Detener"}
      </button>
    </section>
  );
}
