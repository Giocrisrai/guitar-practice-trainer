import { useEffect, useMemo, useState } from "react";

import { SelectorDeAcordes } from "./SelectorDeAcordes";
import { cuerdasElegibles, raicesElegibles } from "./presentacionEjercicio";
import type { FamiliaEjercicio, InstrumentoEjercicio } from "./tiposEjercicio";

/**
 * Direcciones admitidas.
 *
 * Es el único catálogo que esta pantalla todavía tiene escrito: el endpoint de
 * familias publica el NOMBRE del parámetro `direccion` pero no sus valores
 * admisibles (los tiene `nucleo/ejercicios/generadores/comun.py`). Mientras el
 * servidor no los publique, esta lista puede quedarse obsoleta sin que nada
 * avise; está anotado en el informe de esta ola.
 */
const DIRECCIONES = ["ascendente", "descendente", "ambas"];

/** De qué se sacan las opciones de un desplegable, cuando no es un campo libre. */
type Catalogo = "raices" | "cuerdas" | "direcciones";

interface Control {
  etiqueta: string;
  /** Si el valor viaja al servidor como número. */
  numerico: boolean;
  catalogo?: Catalogo;
  /**
   * Si lo pinta un control propio en vez de un `input` o un `select`.
   *
   * Hace falta porque `claves` no es un valor, es una SECUENCIA de acordes, y
   * ningún campo de los de esta pantalla la representa: viaja como lista y se
   * elige con `SelectorDeAcordes`. Declararlo aquí y no fuera mantiene la regla
   * de que un parámetro que esta tabla no conoce no se pinta y no se envía.
   */
  propio?: "acordes";
}

/**
 * Los controles que esta pantalla sabe pintar, por nombre de parámetro.
 *
 * La lista de parámetros de cada familia la manda el servidor; esto solo dice
 * cómo se pinta cada uno. Un parámetro declarado que no esté aquí no se pinta y
 * no se envía: es mejor que el usuario no lo vea que mandar una clave inventada.
 * Ningún valor por defecto vive aquí: los valores por defecto son de los
 * generadores (escala 80 y 0-4, intervalo 70 y 0-7, lectura 60 y 0-12) y se
 * consiguen NO mandando el parámetro.
 */
const CONTROLES: Record<string, Control> = {
  raiz_midi: { etiqueta: "Raíz", numerico: true, catalogo: "raices" },
  cuerda: { etiqueta: "Cuerda", numerico: true, catalogo: "cuerdas" },
  direccion: { etiqueta: "Dirección", numerico: false, catalogo: "direcciones" },
  tempo: { etiqueta: "Tempo (ppm)", numerico: true },
  traste_minimo: { etiqueta: "Traste mínimo", numerico: true },
  traste_maximo: { etiqueta: "Traste máximo", numerico: true },
  repeticiones: { etiqueta: "Repeticiones", numerico: true },
  claves: { etiqueta: "Acordes", numerico: false, propio: "acordes" },
};

/**
 * Bajo qué clave manda cada familia el valor elegido en el desplegable de tipos.
 *
 * `/api/ejercicios/familias` publica el NOMBRE de cada parámetro, pero no su
 * PAPEL (cuál de ellos hace de "tipo"), así que no hay dato del servidor del
 * que derivarlo sin adivinar. Antes se adivinaba tomando "el primer parámetro
 * sin control propio", y eso elegía la clave equivocada en silencio si una
 * familia llegaba a declarar dos parámetros sin control. Se escribe a mano,
 * por clave de familia, hasta que el endpoint publique el papel de cada
 * parámetro además de su nombre; ese día esta tabla se borra.
 */
const CLAVE_DE_TIPOS: Record<string, string> = {
  escala: "tipo",
  arpegio: "tipo",
  intervalo: "intervalo",
  // "lectura" no tiene tipo: no aparece aquí y claveDeTipos devuelve null.
};

function claveDeTipos(familia: FamiliaEjercicio): string | null {
  return CLAVE_DE_TIPOS[familia.clave] ?? null;
}

/**
 * Configurador del ejercicio.
 *
 * Las familias, sus tipos y sus PARÁMETROS salen de `/api/ejercicios/familias`,
 * no de una lista escrita aquí: añadir una escala nueva —o una familia con otros
 * parámetros— en el núcleo no debe obligar a tocar esta pantalla.
 *
 * Solo viajan al servidor los parámetros que el usuario haya cambiado. Los que
 * no toque se omiten del cuerpo, para que cada generador aplique su propio valor
 * por defecto: el tempo y los trastes de un ejercicio son una decisión musical
 * del núcleo, y repetirla aquí la tapaba (era la tercera vez en este proyecto).
 *
 * Las raíces y las cuerdas elegibles salen de `/api/ejercicios/instrumento`, el
 * perfil de afinación ACTIVO en el afinador, no de la lista completa de
 * `/api/perfiles`: los ejercicios se generan con ese perfil, así que ofrecer
 * cuerdas de otro instrumento (la 5ª o 6ª con el bajo de 4 puesto) es ofrecer
 * algo que el servidor rechaza con un 400 al pulsar "Empezar".
 */
export function Configurador() {
  const [familias, setFamilias] = useState<FamiliaEjercicio[]>([]);
  const [instrumento, setInstrumento] = useState<InstrumentoEjercicio | null>(null);
  const [clave, setClave] = useState("");
  /** Solo los parámetros que el usuario ha tocado. Vacío = todo por defecto. */
  const [valores, setValores] = useState<Record<string, string>>({});
  /**
   * Los acordes elegidos, en orden. Aparte de `valores` porque es una lista y
   * `valores` guarda texto: meter aquí un "do,sol,re" obligaría a partirlo y a
   * volver a unirlo en cada render, y el orden -que ES el ejercicio- quedaría
   * guardado en una cadena en vez de en una lista.
   */
  const [acordes, setAcordes] = useState<string[]>([]);
  const [conMetronomo, setConMetronomo] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    fetch("/api/ejercicios/familias")
      .then((r) => r.json())
      .then((datos: FamiliaEjercicio[]) => {
        setFamilias(datos);
        if (datos.length > 0) setClave(datos[0].clave);
      });
  }, []);

  useEffect(() => {
    fetch("/api/ejercicios/instrumento")
      .then((r) => r.json())
      .then(setInstrumento);
  }, []);

  const familia = familias.find((f) => f.clave === clave);
  const raices = useMemo(() => raicesElegibles(instrumento), [instrumento]);
  const cuerdas = useMemo(() => cuerdasElegibles(instrumento), [instrumento]);

  const elegirFamilia = (nuevaClave: string) => {
    setClave(nuevaClave);
    // Los parámetros de la familia anterior no valen para la nueva: arrastrarlos
    // podría mandar una clave que esta familia no declara.
    setValores({});
    setAcordes([]);
  };

  const cambiar = (nombre: string, valor: string) => {
    setValores((anteriores) => {
      const siguientes = { ...anteriores };
      // Vaciar un control es volver al valor por defecto del generador, así que
      // la clave desaparece en vez de viajar vacía.
      if (valor === "") delete siguientes[nombre];
      else siguientes[nombre] = valor;
      return siguientes;
    });
  };

  const opcionesDe = (catalogo: Catalogo): { valor: string; texto: string }[] => {
    if (catalogo === "raices") return raices.map((r) => ({ valor: String(r.midi), texto: r.nombre }));
    if (catalogo === "cuerdas") return cuerdas.map((n) => ({ valor: String(n), texto: `${n}ª` }));
    return DIRECCIONES.map((d) => ({ valor: d, texto: d }));
  };

  /** El cuerpo que viaja: solo claves que esta familia declara y el usuario tocó. */
  const cuerpoParametros = (elegida: FamiliaEjercicio): Record<string, unknown> => {
    const parametros: Record<string, unknown> = {};
    for (const nombre of elegida.parametros) {
      const control = CONTROLES[nombre];
      // Los acordes viajan como LISTA, y vacía no viaja: sin elegir ninguno el
      // generador aplica su propio valor por defecto, igual que con el tempo.
      if (control?.propio === "acordes") {
        if (acordes.length > 0) parametros[nombre] = acordes;
        continue;
      }
      const valor = valores[nombre];
      if (valor === undefined || valor === "") continue;
      parametros[nombre] = control?.numerico ? Number(valor) : valor;
    }
    return parametros;
  };

  const empezar = async () => {
    if (!familia) return;
    setEnviando(true);
    setError(null);
    try {
      const respuesta = await fetch("/api/ejercicios/iniciar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          familia: clave,
          parametros: cuerpoParametros(familia),
          con_metronomo: conMetronomo,
        }),
      });
      const cuerpo = (await respuesta.json().catch(() => null)) as { detail?: string } | null;
      if (!respuesta.ok) {
        throw new Error(cuerpo?.detail ?? `El servidor respondio ${respuesta.status}`);
      }
    } catch (excepcion) {
      setError(
        excepcion instanceof Error ? excepcion.message : "No se pudo iniciar el ejercicio"
      );
    } finally {
      setEnviando(false);
    }
  };

  const claveTipos = familia ? claveDeTipos(familia) : null;

  return (
    <div className="configurador">
      <div className="selector">
        <label htmlFor="familia">Ejercicio</label>
        <select id="familia" value={clave} onChange={(evento) => elegirFamilia(evento.target.value)}>
          {familias.map((f) => (
            <option key={f.clave} value={f.clave}>
              {f.nombre}
            </option>
          ))}
        </select>

        {familia &&
          familia.parametros.map((nombre) => {
            if (nombre === claveTipos) {
              return (
                <div className="control" key={nombre}>
                  <label htmlFor={`parametro-${nombre}`}>Tipo</label>
                  <select
                    id={`parametro-${nombre}`}
                    value={valores[nombre] ?? ""}
                    onChange={(evento) => cambiar(nombre, evento.target.value)}
                  >
                    <option value="">Por defecto</option>
                    {familia.tipos.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>
              );
            }

            const control = CONTROLES[nombre];
            if (control === undefined) return null;

            if (control.propio === "acordes") {
              return (
                <SelectorDeAcordes key={nombre} elegidas={acordes} alCambiar={setAcordes} />
              );
            }

            return (
              <div className="control" key={nombre}>
                <label htmlFor={`parametro-${nombre}`}>{control.etiqueta}</label>
                {control.catalogo === undefined ? (
                  <input
                    id={`parametro-${nombre}`}
                    type="number"
                    // Sin valor de partida: el hueco significa "el que decida el
                    // generador", y no hay ningún número de la interfaz que tapar.
                    placeholder="por defecto"
                    value={valores[nombre] ?? ""}
                    onChange={(evento) => cambiar(nombre, evento.target.value)}
                  />
                ) : (
                  <select
                    id={`parametro-${nombre}`}
                    value={valores[nombre] ?? ""}
                    onChange={(evento) => cambiar(nombre, evento.target.value)}
                  >
                    <option value="">Por defecto</option>
                    {opcionesDe(control.catalogo).map((o) => (
                      <option key={o.valor} value={o.valor}>
                        {o.texto}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            );
          })}

        <label htmlFor="con-metronomo" className="con-metronomo">
          <input
            id="con-metronomo"
            type="checkbox"
            checked={conMetronomo}
            onChange={(evento) => setConMetronomo(evento.target.checked)}
          />
          Con metrónomo
        </label>

        <button type="button" onClick={empezar} disabled={!clave || enviando}>
          Empezar
        </button>
      </div>

      {familia && <p className="descripcion-familia">{familia.descripcion}</p>}
      {error && <p className="error-ejercicio">{error}</p>}
    </div>
  );
}
