import { useEffect, useState } from "react";

import type { FamiliaEjercicio } from "./tiposEjercicio";

/** Valores de partida de los parametros comunes, antes de que el usuario los toque. */
const TEMPO_POR_DEFECTO = 80;
const TRASTE_MINIMO_POR_DEFECTO = 0;
const TRASTE_MAXIMO_POR_DEFECTO = 12;

/**
 * Configurador del ejercicio.
 *
 * Las familias y sus tipos salen de `/api/ejercicios/familias`, no de una lista
 * escrita aqui: anadir una escala nueva en el nucleo no debe obligar a tocar
 * esta pantalla.
 */
export function Configurador() {
  const [familias, setFamilias] = useState<FamiliaEjercicio[]>([]);
  const [clave, setClave] = useState("");
  const [tipo, setTipo] = useState("");
  const [tempo, setTempo] = useState(TEMPO_POR_DEFECTO);
  const [trasteMinimo, setTrasteMinimo] = useState(TRASTE_MINIMO_POR_DEFECTO);
  const [trasteMaximo, setTrasteMaximo] = useState(TRASTE_MAXIMO_POR_DEFECTO);
  const [conMetronomo, setConMetronomo] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    fetch("/api/ejercicios/familias")
      .then((r) => r.json())
      .then((datos: FamiliaEjercicio[]) => {
        setFamilias(datos);
        if (datos.length > 0) {
          setClave(datos[0].clave);
          setTipo(datos[0].tipos[0] ?? "");
        }
      });
  }, []);

  const familia = familias.find((f) => f.clave === clave);

  const elegirFamilia = (nuevaClave: string) => {
    setClave(nuevaClave);
    const nueva = familias.find((f) => f.clave === nuevaClave);
    setTipo(nueva?.tipos[0] ?? "");
  };

  const empezar = async () => {
    setEnviando(true);
    setError(null);
    try {
      const parametros: Record<string, unknown> = {
        tempo,
        traste_minimo: trasteMinimo,
        traste_maximo: trasteMaximo,
      };
      if (familia && familia.tipos.length > 0) parametros.tipo = tipo;

      const respuesta = await fetch("/api/ejercicios/iniciar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ familia: clave, parametros, con_metronomo: conMetronomo }),
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

        {familia && familia.tipos.length > 0 && (
          <>
            <label htmlFor="tipo">Tipo</label>
            <select id="tipo" value={tipo} onChange={(evento) => setTipo(evento.target.value)}>
              {familia.tipos.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </>
        )}

        <label htmlFor="tempo">Tempo (ppm)</label>
        <input
          id="tempo"
          type="number"
          value={tempo}
          onChange={(evento) => setTempo(Number(evento.target.value))}
        />

        <label htmlFor="traste-minimo">Traste mínimo</label>
        <input
          id="traste-minimo"
          type="number"
          value={trasteMinimo}
          onChange={(evento) => setTrasteMinimo(Number(evento.target.value))}
        />

        <label htmlFor="traste-maximo">Traste máximo</label>
        <input
          id="traste-maximo"
          type="number"
          value={trasteMaximo}
          onChange={(evento) => setTrasteMaximo(Number(evento.target.value))}
        />

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
