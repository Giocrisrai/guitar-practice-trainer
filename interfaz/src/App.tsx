import { useEffect, useState } from "react";

import { Afinador } from "./Afinador";
import { Ejercicios } from "./Ejercicios";
import "./estilos.css";
import type { Diagnostico, Modulo } from "./tipos";

/**
 * Armazón de la aplicación.
 *
 * Los módulos se leen del servidor en lugar de estar escritos aquí: añadir
 * ejercicios o canciones en las etapas siguientes será registrar un módulo en el
 * servidor y escribir su componente, sin tocar este archivo.
 */
export function App() {
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [activo, setActivo] = useState("afinador");
  const [diagnostico, setDiagnostico] = useState<Diagnostico | null>(null);

  useEffect(() => {
    fetch("/api/modulos").then((r) => r.json()).then(setModulos);
  }, []);

  useEffect(() => {
    const revisar = () =>
      fetch("/api/diagnostico").then((r) => r.json()).then(setDiagnostico);
    revisar();
    const intervalo = window.setInterval(revisar, 3000);
    return () => window.clearInterval(intervalo);
  }, []);

  const problema = diagnostico !== null && diagnostico.estado !== "ok";

  return (
    <div className="aplicacion">
      <header className="cabecera">
        <span className="titulo">proyecto_musica</span>
        <nav className="modulos">
          {modulos.map((modulo) => (
            <button
              key={modulo.clave}
              className={modulo.clave === activo ? "modulo activo" : "modulo"}
              disabled={!modulo.disponible}
              title={modulo.descripcion}
              onClick={() => setActivo(modulo.clave)}
            >
              {modulo.icono} {modulo.nombre}
            </button>
          ))}
        </nav>
      </header>

      {problema && (
        <div className="aviso">
          <strong>{diagnostico!.mensaje}</strong>
          <p>{diagnostico!.accion}</p>
        </div>
      )}

      <main>
        {activo === "afinador" && <Afinador />}
        {activo === "ejercicios" && <Ejercicios />}
      </main>
    </div>
  );
}
