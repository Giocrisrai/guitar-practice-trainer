import { useCallback, useEffect, useRef, useState } from "react";

import type { DetalleCancion, FichaCancion, PiezaImportada } from "./tiposCancion";
import type { RespuestaConfig } from "./tipos";
import type { PeticionCancion } from "./useCarril";

/**
 * La pantalla de canciones: elige la canción, elige la pista, avisa y arranca.
 *
 * Usa DOS endpoints y cada uno para lo suyo, que es lo que permite ver los avisos
 * antes de comprometerse a nada:
 *
 * - `POST /api/canciones/{id}/importar` PREVISUALIZA: devuelve la pieza y sus
 *   avisos sin poner en marcha el carril, así que una canción en otra afinación se
 *   puede mirar aunque el carril todavía vaya a rechazarla. Justo cuando hace
 *   falta, porque es cuando el usuario necesita ver a qué afinarse.
 * - `POST /api/piezas/iniciar` TOCA, y se le manda `{cancion, pista, perfil}`: la
 *   pieza no viaja desde aquí. La lee el servidor, que es quien comprueba la
 *   afinación activa (ver `PeticionCancion` en `useCarril.ts`).
 *
 * Lo que esta pantalla NO decide: ni los formatos que valen, ni por qué una pista
 * no se puede usar, ni si la afinación cuadra, ni los avisos de la pieza. Todo eso
 * lo publica el servidor ya escrito y aquí se muestra tal cual. El único cálculo
 * propio es `tieneAcordes`, y es un cálculo sobre datos que ya vienen.
 */

/**
 * El aviso de los acordes, que es el único que no viene del servidor.
 *
 * No es una decisión duplicada: el núcleo no publica «esta pieza tiene acordes» y
 * no hace falta que lo haga, porque dos notas con el mismo `inicio_pulsos` SON un
 * acorde por definición del modelo (`Pieza`, nucleo/piezas/modelo.py) y la cuenta
 * se hace sobre las notas que ya han llegado. Lo que el núcleo sí decide, y aquí
 * no se repite, es qué puede seguir el seguidor.
 */
const AVISO_ACORDES =
  "Esta pista trae ACORDES: hay notas que suenan a la vez y el detector de tono " +
  "es monofónico, así que de cada acorde solo se podrá seguir una nota.";

/** Si la pieza trae acordes: dos notas que empiezan en el mismo pulso. */
function tieneAcordes(pieza: PiezaImportada): boolean {
  const inicios = new Set<number>();
  for (const nota of pieza.notas) {
    if (inicios.has(nota.inicio_pulsos)) return true;
    inicios.add(nota.inicio_pulsos);
  }
  return false;
}

/**
 * El cuerpo de una respuesta, o un `Error` con el `detail` que mandó el servidor.
 *
 * El `detail` viene escrito para el usuario -los nombres que valen, por qué el
 * nombre no pasa el guardia, cuántos bytes pasa del techo- y se muestra TAL CUAL.
 * Reescribirlo aquí sería perder lo único que le dice al usuario qué arreglar.
 */
async function pedir<T>(url: string, opciones?: RequestInit): Promise<T> {
  const respuesta = await fetch(url, opciones);
  const cuerpo = (await respuesta.json().catch(() => null)) as
    | (T & { detail?: string })
    | null;
  if (!respuesta.ok || cuerpo === null) {
    throw new Error(cuerpo?.detail ?? `El servidor respondio ${respuesta.status}`);
  }
  return cuerpo;
}

/** El mensaje de una excepción, con un respaldo para lo que no es un `Error`. */
function mensajeDe(excepcion: unknown, respaldo: string): string {
  return excepcion instanceof Error ? excepcion.message : respaldo;
}

/** El `id` de una canción, listo para ir en una ruta. */
function ruta(identificador: string, cola: string): string {
  return `/api/canciones/${encodeURIComponent(identificador)}${cola}`;
}

interface PropiedadesCanciones {
  /** Lleva a otro módulo. La usa el botón del aviso de afinación, que tiene que
   * poder llevar al afinador; el módulo activo lo guarda `App`. */
  irA(clave: string): void;
  /** Pone esta canción en el carril. `App` la lleva al módulo del carril, que es
   * quien dibuja: esta pantalla elige y avisa, no pinta notas. */
  tocar(peticion: PeticionCancion): void;
}

export function Canciones({ irA, tocar }: PropiedadesCanciones) {
  const [canciones, setCanciones] = useState<FichaCancion[]>([]);
  const [errorLista, setErrorLista] = useState<string | null>(null);
  const [errorSubida, setErrorSubida] = useState<string | null>(null);
  /** El `id` de la canción elegida, que es el nombre de su archivo. */
  const [elegida, setElegida] = useState<string | null>(null);
  const [detalle, setDetalle] = useState<DetalleCancion | null>(null);
  const [errorPistas, setErrorPistas] = useState<string | null>(null);
  /** El NÚMERO de la pista elegida, en base 1. `null` mientras no hay ninguna. */
  const [pista, setPista] = useState<number | null>(null);
  /** La pieza previsualizada: de aquí salen los avisos, y nada más. No se manda
   * al carril (ver la cabecera de este archivo). */
  const [pieza, setPieza] = useState<PiezaImportada | null>(null);
  const [errorPieza, setErrorPieza] = useState<string | null>(null);
  const [errorAfinador, setErrorAfinador] = useState<string | null>(null);

  /**
   * Contadores de petición: cada llamada se queda con un número y solo escribe en
   * la pantalla si al volver sigue siendo la última.
   *
   * Soltar el estado por delante -como hace `elegirCancion`- cubre el MIENTRAS, que
   * es otra cosa: cubre que no se vean las pistas de A con el título de B durante la
   * espera, pero no la LLEGADA fuera de orden. `fetch` no promete orden, así que dos
   * clics rápidos -canción A, canción B- dejaban el detalle de A debajo del título
   * de B en cuanto el de A llegaba tarde, y entonces elegir una pista de la lista de
   * A importaba una pista de B.
   *
   * Son TRES, uno por petición que escribe en la pantalla, y no uno solo, porque
   * las tres no caducan igual: elegir otra pista deja rancia la pieza en vuelo pero
   * no el detalle ni la lista; elegir otra canción deja rancias la pieza y el
   * detalle pero no la lista; y la lista solo la deja rancia otra lectura de la
   * lista (la del montaje contra la de una subida, o dos subidas seguidas).
   */
  const ultimaLista = useRef(0);
  const ultimoDetalle = useRef(0);
  const ultimaPieza = useRef(0);

  /** Vuelve a leer la carpeta. Al montar y después de cada subida. */
  const cargarLista = useCallback(() => {
    const mia = (ultimaLista.current += 1);
    return pedir<FichaCancion[]>("/api/canciones").then(
      (lista) => {
        if (ultimaLista.current !== mia) return;
        setCanciones(lista);
        setErrorLista(null);
      },
      (excepcion: unknown) => {
        if (ultimaLista.current !== mia) return;
        setErrorLista(mensajeDe(excepcion, "No pude leer la carpeta de canciones"));
      }
    );
  }, []);

  useEffect(() => {
    void cargarLista();
  }, [cargarLista]);

  const elegirCancion = useCallback(async (ficha: FichaCancion) => {
    // Todo lo que hablaba de la canción anterior se suelta antes de preguntar por
    // la nueva: dejar las pistas, los avisos o el error de la otra en pantalla
    // mientras llega la respuesta es enseñar datos de una canción con el título de
    // otra.
    setElegida(ficha.id);
    setDetalle(null);
    setPista(null);
    setPieza(null);
    setErrorPistas(null);
    setErrorPieza(null);
    setErrorAfinador(null);
    // Esta petición es la última del detalle, y además deja rancia cualquier pieza
    // que siga en vuelo: era de la canción anterior.
    //
    // Esa segunda línea es defensa en profundidad y hoy NO se ve: el bloque de los
    // avisos exige también una pista elegida, y `setPista(null)` de arriba ya la
    // quita, así que una pieza rancia que entrara aquí se guardaría sin pintarse.
    // Se queda porque lo que sostiene es el invariante —`pieza` y `detalle` hablan
    // siempre de la misma canción— y no el píxel. Medido, y las dos parejas están
    // en el informe: quitarla sola no rompe ninguna prueba, y quitarla junto con
    // `setPista(null)` sí; quitarla junto con el `pista !== null` del render —que es
    // justo el escenario futuro que esto para, pintar la pieza sin exigir pista—
    // también.
    const mia = (ultimoDetalle.current += 1);
    ultimaPieza.current += 1;
    try {
      const recibido = await pedir<DetalleCancion>(ruta(ficha.id, "/pistas"));
      if (ultimoDetalle.current === mia) setDetalle(recibido);
    } catch (excepcion) {
      if (ultimoDetalle.current === mia) {
        setErrorPistas(mensajeDe(excepcion, "No pude leer las pistas de esta canción"));
      }
    }
  }, []);

  /** `numero` va en base 1: es el que publica `/pistas` y el que entiende el
   * núcleo. Aquí no se traduce nada, que es justo lo que hacía importar la pista
   * siguiente sin dar ningún error. */
  const elegirPista = async (identificador: string, numero: number) => {
    setPista(numero);
    setPieza(null);
    setErrorPieza(null);
    const mia = (ultimaPieza.current += 1);
    try {
      const recibida = await pedir<PiezaImportada>(ruta(identificador, "/importar"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // `perfil` solo cuenta donde el archivo no trae afinación, y entonces
        // manda el perfil activo: no se elige uno desde aquí, porque
        // reinterpretar una tablatura en Drop D con otro perfil dibujaría
        // trastes que la canción no toca.
        body: JSON.stringify({ pista: numero, perfil: null }),
      });
      if (ultimaPieza.current === mia) setPieza(recibida);
    } catch (excepcion) {
      if (ultimaPieza.current === mia) {
        setErrorPieza(mensajeDe(excepcion, "No pude importar esta pista"));
      }
    }
  };

  /**
   * Deja puesta la afinación que pide la canción y lleva al afinador.
   *
   * El orden importa: si el `PUT` falla, NO se navega. Llevar al afinador con la
   * afinación sin cambiar sería mandar al usuario a arreglar algo que esta
   * pantalla ya decidió por él y no consiguió hacer, sin decírselo.
   */
  const afinarse = async (clave: string) => {
    setErrorAfinador(null);
    try {
      await pedir<RespuestaConfig>("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ perfil: clave }),
      });
      irA("afinador");
    } catch (excepcion) {
      setErrorAfinador(
        mensajeDe(excepcion, "No pude cambiar la afinación, así que no te llevo al afinador")
      );
    }
  };

  const subir = async (archivo: File) => {
    setErrorSubida(null);
    const cuerpo = new FormData();
    cuerpo.append("archivo", archivo);
    try {
      // Sin `Content-Type`: lo pone el navegador con el separador del multipart,
      // y escribirlo a mano a pelo rompe el parseo en el servidor.
      const ficha = await pedir<FichaCancion>("/api/canciones", {
        method: "POST",
        body: cuerpo,
      });
      await cargarLista();
      // La canción que acabas de subir es la que querías: se abre sola.
      await elegirCancion(ficha);
    } catch (excepcion) {
      setErrorSubida(mensajeDe(excepcion, "No pude subir el archivo"));
    }
  };

  /** La pista elegida, buscada por su `numero` (base 1), o `null` si no hay. */
  const pistaElegida =
    detalle !== null && pista !== null
      ? (detalle.pistas.find((disponible) => disponible.numero === pista) ?? null)
      : null;

  /**
   * De quién es el aviso de afinación: de la PISTA elegida, y de la canción solo
   * mientras no hay ninguna.
   *
   * Lo que se importa es una pista, no una canción, así que es la afinación de la
   * pista la que decide. Medido con un `.gp5` de pista 1 en estándar y pista 2 en
   * Drop C: el `coincide` de nivel canción -el de la primera pista usable- decía
   * `true`, el botón salía habilitado, importar la pista 2 daba 200 y arrancarla un
   * 400, y encima no se ofrecía «Afinarme a...» porque a nivel canción no había
   * nada que avisar. El dato por pista ya lo publicaba el servidor y esta pantalla
   * no lo leía.
   *
   * Mientras no hay pista elegida se usa el de la canción, que es el de la pista que
   * se importará si el usuario no elige otra: así el aviso sigue apareciendo al
   * abrir la canción y no solo al elegir una pista.
   *
   * Las dos formas traen `afinacion` y `coincide` con el mismo significado y la
   * misma cuenta del servidor (ver `tiposCancion.ts`), así que aquí no se compara
   * nada: se elige de quién es el dato.
   */
  const avisoDeAfinacion: Pick<DetalleCancion, "afinacion" | "coincide"> | null =
    pistaElegida ?? detalle;

  /**
   * Si el carril va a aceptar esta pista.
   *
   * `coincide === false` es el único caso que lo impide. `null` NO lo impide: es
   * «el archivo no dice en qué afinación está», y entonces la pieza se importa en
   * el perfil activo y el carril la acepta.
   */
  const carrilLaAcepta =
    avisoDeAfinacion !== null && avisoDeAfinacion.coincide !== false;

  return (
    <section className="canciones">
      <div className="biblioteca">
        <h2>Canciones</h2>

        <label className="subir" htmlFor="subir-cancion">
          Añadir una canción
        </label>
        <input
          id="subir-cancion"
          type="file"
          onChange={(evento) => {
            const archivo = evento.target.files?.[0];
            if (archivo !== undefined) void subir(archivo);
          }}
        />
        {errorSubida !== null && <p className="error-cancion">{errorSubida}</p>}
        {errorLista !== null && <p className="error-cancion">{errorLista}</p>}

        {canciones.length === 0 && errorLista === null && (
          <p className="descripcion-familia">
            La carpeta está vacía. Añade un archivo de Guitar Pro, MusicXML, MIDI o
            una tablatura de texto.
          </p>
        )}

        <ul className="lista-canciones">
          {canciones.map((ficha) => (
            <li key={ficha.id}>
              <button
                type="button"
                aria-pressed={ficha.id === elegida}
                onClick={() => void elegirCancion(ficha)}
              >
                <span className="nombre-cancion">{ficha.nombre}</span>
                <span className="formato-cancion">{ficha.formato}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="pistas-cancion">
        {elegida === null && (
          <p className="descripcion-familia">
            Elige una canción para ver sus pistas.
          </p>
        )}
        {errorPistas !== null && <p className="error-cancion">{errorPistas}</p>}

        {detalle !== null && (
          <>
            <h3>{detalle.nombre}</h3>

            {/* El aviso de afinación, SOLO con `coincide === false`. Con `null` el
                archivo no dice en qué afinación está y no hay nada que avisar. Y es
                el de la PISTA elegida en cuanto hay una (ver `avisoDeAfinacion`). */}
            {avisoDeAfinacion !== null && avisoDeAfinacion.coincide === false && (
              <div className="aviso-cancion">
                <p>
                  {pistaElegida !== null ? "Esta pista" : "Esta canción"} está escrita
                  en {avisoDeAfinacion.afinacion.nombre} y tú tienes puesta{" "}
                  {detalle.perfil_activo}: el carril no la va a aceptar así.
                </p>
                {avisoDeAfinacion.afinacion.clave !== null ? (
                  <button
                    type="button"
                    onClick={() => void afinarse(avisoDeAfinacion.afinacion.clave!)}
                  >
                    Afinarme a {avisoDeAfinacion.afinacion.nombre} e ir al afinador
                  </button>
                ) : (
                  // Sin clave no hay perfil al que afinarse. Se dice, pero no se
                  // ofrece un botón que no lleva a ninguna parte.
                  <p>
                    No tengo ningún perfil al que afinarte para esta canción, así que
                    tendrás que elegir otra pista u otra canción.
                  </p>
                )}
                {errorAfinador !== null && (
                  <p className="error-cancion">{errorAfinador}</p>
                )}
              </div>
            )}

            <ul className="lista-pistas">
              {detalle.pistas.map((disponible) => (
                <li key={disponible.numero}>
                  <button
                    type="button"
                    disabled={!disponible.usable}
                    aria-pressed={disponible.numero === pista}
                    onClick={() => void elegirPista(detalle.id, disponible.numero)}
                  >
                    {disponible.numero}. {disponible.nombre} — {disponible.instrumento}{" "}
                    ({disponible.notas} notas)
                  </button>
                  {/* Una pista que no se puede elegir y no dice por qué parece un
                      programa roto. El motivo lo escribe el núcleo. */}
                  {disponible.motivo_no_usable !== null && (
                    <p className="motivo-no-usable">{disponible.motivo_no_usable}</p>
                  )}
                </li>
              ))}
            </ul>

            {errorPieza !== null && <p className="error-cancion">{errorPieza}</p>}

            {pieza !== null && pista !== null && (
              <div className="antes-de-empezar">
                {/* Los avisos del servidor, tal cual los escribió (el del ritmo
                    aproximado es uno de ellos). */}
                {pieza.avisos.map((aviso) => (
                  <p key={aviso} className="aviso-cancion">
                    {aviso}
                  </p>
                ))}
                {tieneAcordes(pieza) && <p className="aviso-cancion">{AVISO_ACORDES}</p>}

                <p className="descripcion-familia">
                  {pieza.notas.length} notas a {pieza.tempo} pulsos por minuto.
                </p>

                <button
                  type="button"
                  disabled={!carrilLaAcepta}
                  onClick={() => tocar({ cancion: detalle.id, pista, perfil: null })}
                >
                  Tocar en el carril
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
