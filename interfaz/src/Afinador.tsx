import { useEffect, useState } from "react";

import { Aguja } from "./Aguja";
import { BarraEstado } from "./BarraEstado";
import { Mastil } from "./Mastil";
import type { PerfilAfinacion } from "./tipos";
import { useNotas } from "./useNotas";

/** Módulo afinador: panel único con aguja, mástil y estado a la vista. */
export function Afinador() {
  const { nota, conectado } = useNotas();
  const [perfiles, setPerfiles] = useState<PerfilAfinacion[]>([]);
  const [clavePerfil, setClavePerfil] = useState("guitarra_estandar");
  const [errorPerfil, setErrorPerfil] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/perfiles").then((r) => r.json()).then(setPerfiles);
    fetch("/api/config")
      .then((r) => r.json())
      .then((config) => setClavePerfil(config.perfil));
  }, []);

  const cambiarPerfil = async (clave: string) => {
    const anterior = clavePerfil;
    setClavePerfil(clave);
    setErrorPerfil(null);
    try {
      const respuesta = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ perfil: clave }),
      });
      if (!respuesta.ok) {
        const datos = await respuesta.json().catch(() => null);
        throw new Error(datos?.detail ?? `El servidor respondio ${respuesta.status}`);
      }
    } catch (error) {
      // Si el PUT falla (400 por configuración inválida, error de red, etc.) se
      // revierte al valor anterior: dejar el selector mostrando una afinación que
      // el servidor nunca aplicó le mentiría al usuario sobre el estado real.
      setClavePerfil(anterior);
      setErrorPerfil(
        error instanceof Error ? error.message : "No se pudo cambiar la afinacion"
      );
    }
  };

  const perfil = perfiles.find((p) => p.clave === clavePerfil);

  return (
    <div className="afinador">
      <div className="selector">
        <label htmlFor="perfil">Afinación</label>
        <select
          id="perfil"
          value={clavePerfil}
          onChange={(evento) => cambiarPerfil(evento.target.value)}
        >
          {perfiles.map((opcion) => (
            <option key={opcion.clave} value={opcion.clave}>
              {opcion.nombre}
            </option>
          ))}
        </select>
        {errorPerfil && <span className="error-perfil">{errorPerfil}</span>}
      </div>

      <Aguja nota={nota?.nota ?? null} cents={nota?.cents ?? null} />

      {perfil && <Mastil perfil={perfil} posiciones={nota?.posiciones ?? []} />}

      <BarraEstado
        nivelDb={nota?.nivel_db ?? -120}
        frecuencia={nota?.frecuencia ?? 0}
        latenciaMs={nota?.latencia_ms ?? 0}
        conectado={conectado}
      />
    </div>
  );
}
