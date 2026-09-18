import { useEffect, useState } from "react";

import { Aguja } from "./Aguja";
import { BarraEstado } from "./BarraEstado";
import { Mastil } from "./Mastil";
import type {
  Configuracion,
  DispositivoEntrada,
  PerfilAfinacion,
  RespuestaConfig,
} from "./tipos";
import { useNotas } from "./useNotas";

/** Segundos que dura la medición del piso de ruido. */
const SEGUNDOS_CALIBRACION = 2;

/**
 * Guarda un cambio de configuración en el servidor.
 *
 * Lanza si el PUT falla, para que quien llama pueda revertir. Si el PUT sale
 * bien pero el diagnóstico que devuelve no es "ok", se devuelve ese aviso en vez
 * de tirarlo: el servidor adjunta el diagnóstico precisamente para que un
 * dispositivo que no se pudo abrir llegue al usuario y no se pierda en un 200
 * llano.
 */
async function guardarConfig(datos: Partial<Configuracion>): Promise<string | null> {
  const respuesta = await fetch("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(datos),
  });
  const cuerpo = (await respuesta.json().catch(() => null)) as
    | (RespuestaConfig & { detail?: string })
    | null;
  if (!respuesta.ok) {
    throw new Error(cuerpo?.detail ?? `El servidor respondio ${respuesta.status}`);
  }
  const diagnostico = cuerpo?.diagnostico;
  if (typeof diagnostico?.estado === "string" && diagnostico.estado !== "ok") {
    return `${diagnostico.mensaje} ${diagnostico.accion ?? ""}`.trim();
  }
  return null;
}

/** Módulo afinador: panel único con aguja, mástil y estado a la vista. */
export function Afinador() {
  const { nota, conectado } = useNotas();
  const [perfiles, setPerfiles] = useState<PerfilAfinacion[]>([]);
  const [clavePerfil, setClavePerfil] = useState("guitarra_estandar");
  const [errorPerfil, setErrorPerfil] = useState<string | null>(null);
  const [dispositivos, setDispositivos] = useState<DispositivoEntrada[]>([]);
  const [dispositivo, setDispositivo] = useState<number | null>(null);
  const [errorDispositivo, setErrorDispositivo] = useState<string | null>(null);
  const [umbral, setUmbral] = useState<number | null>(null);
  const [calibrando, setCalibrando] = useState(false);
  const [mensajeCalibracion, setMensajeCalibracion] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/perfiles").then((r) => r.json()).then(setPerfiles);
    fetch("/api/dispositivos").then((r) => r.json()).then(setDispositivos);
    fetch("/api/config")
      .then((r) => r.json())
      .then((config: Configuracion) => {
        setClavePerfil(config.perfil);
        setDispositivo(config.dispositivo);
        setUmbral(config.umbral_ruido_dbfs);
      });
  }, []);

  const cambiarPerfil = async (clave: string) => {
    const anterior = clavePerfil;
    setClavePerfil(clave);
    setErrorPerfil(null);
    try {
      setErrorPerfil(await guardarConfig({ perfil: clave }));
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

  const cambiarDispositivo = async (valor: string) => {
    const anterior = dispositivo;
    const indice = Number(valor);
    setDispositivo(indice);
    setErrorDispositivo(null);
    try {
      setErrorDispositivo(await guardarConfig({ dispositivo: indice }));
    } catch (error) {
      // Mismo criterio que con la afinación: si el servidor no lo aplicó, el
      // selector no debe mostrarlo como aplicado.
      setDispositivo(anterior);
      setErrorDispositivo(
        error instanceof Error ? error.message : "No se pudo cambiar el dispositivo"
      );
    }
  };

  const calibrar = async () => {
    setCalibrando(true);
    setMensajeCalibracion(
      `No toques nada durante ${SEGUNDOS_CALIBRACION} s: midiendo el ruido de fondo…`
    );
    try {
      const respuesta = await fetch("/api/calibrar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segundos: SEGUNDOS_CALIBRACION }),
      });
      if (!respuesta.ok) {
        throw new Error(`El servidor respondio ${respuesta.status}`);
      }
      const { umbral_sugerido } = (await respuesta.json()) as { umbral_sugerido: number };
      const antes = umbral;
      // La spec §4.2 pide que la calibración guarde el valor: medirlo y no
      // guardarlo deja al usuario con un número que no sirve de nada.
      const aviso = await guardarConfig({ umbral_ruido_dbfs: umbral_sugerido });
      setUmbral(umbral_sugerido);
      const cambio =
        antes === null
          ? `Umbral guardado: ${umbral_sugerido.toFixed(1)} dBFS.`
          : `Umbral: ${antes.toFixed(1)} → ${umbral_sugerido.toFixed(1)} dBFS (guardado).`;
      setMensajeCalibracion(aviso ? `${cambio} ${aviso}` : cambio);
    } catch (error) {
      setMensajeCalibracion(
        error instanceof Error ? error.message : "No se pudo calibrar"
      );
    } finally {
      setCalibrando(false);
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

        <label htmlFor="dispositivo">Dispositivo</label>
        <select
          id="dispositivo"
          value={dispositivo ?? ""}
          onChange={(evento) => cambiarDispositivo(evento.target.value)}
        >
          {dispositivo === null && <option value="">Elige un dispositivo</option>}
          {dispositivos.map((opcion) => (
            <option key={opcion.indice} value={opcion.indice}>
              {opcion.nombre}
            </option>
          ))}
        </select>
        {errorDispositivo && <span className="error-dispositivo">{errorDispositivo}</span>}

        <button type="button" className="calibrar" disabled={calibrando} onClick={calibrar}>
          Calibrar ruido
        </button>
        <span className="umbral">
          umbral {umbral === null ? "—" : `${umbral.toFixed(1)} dBFS`}
        </span>
        {mensajeCalibracion && (
          <span className="mensaje-calibracion">{mensajeCalibracion}</span>
        )}
      </div>

      <Aguja
        estado={nota?.estado ?? null}
        nota={nota?.nota ?? null}
        cents={nota?.cents ?? null}
        afinada={nota?.afinada ?? false}
      />

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
