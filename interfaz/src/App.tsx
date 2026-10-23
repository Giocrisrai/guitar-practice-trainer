import { useEffect, useState } from "react";

import { Afinador } from "./Afinador";
import { Canciones } from "./Canciones";
import { Carril } from "./Carril";
import { Ejercicios } from "./Ejercicios";
import "./estilos.css";
import type { Diagnostico, Modulo } from "./tipos";
import type { PeticionCancion } from "./useCarril";

/**
 * Armazón de la aplicación.
 *
 * Los módulos se leen del servidor en lugar de estar escritos aquí: añadir
 * ejercicios o canciones en las etapas siguientes será registrar un módulo en el
 * servidor y escribir su componente, sin tocar este archivo.
 *
 * Lo que sí vive aquí, y no puede vivir en otro sitio, es el módulo activo. Por eso
 * los hijos reciben `irA`: una pantalla que necesita llevar a otra -el aviso de
 * «aféinate a Drop C» de `Canciones`, que tiene que acabar en el afinador- no puede
 * cambiar un `useState` que no es suyo.
 */
export function App() {
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [activo, setActivo] = useState("afinador");
  /**
   * La canción que el carril tiene que arrancar en cuanto se abra, o `null`.
   *
   * El traspaso pasa por aquí porque quien PIDE la pieza tiene que ser quien la
   * DIBUJA: la pieza entera viaja una sola vez, en la respuesta de
   * `POST /api/piezas/iniciar`, y el WebSocket no la repite, así que la sesión del
   * carril que no haya hecho ese POST no tiene pieza que pintar. `Canciones` elige
   * y avisa; el carril arranca y dibuja.
   */
  const [peticionCarril, setPeticionCarril] = useState<PeticionCancion | null>(null);
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

  /**
   * Abre un módulo. Suelta la canción pendiente, que es del traspaso de
   * `Canciones` y no del módulo: sin esto, abrir el carril desde la cabecera horas
   * después volvería a arrancar la canción de entonces en vez de ofrecer el
   * configurador.
   */
  const irA = (clave: string) => {
    setPeticionCarril(null);
    setActivo(clave);
  };

  /** Lleva esta canción al carril, que es quien la arranca y la dibuja. */
  const tocarEnElCarril = (peticion: PeticionCancion) => {
    setPeticionCarril(peticion);
    setActivo("carril");
  };

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
              onClick={() => irA(modulo.clave)}
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
        {activo === "canciones" && <Canciones irA={irA} tocar={tocarEnElCarril} />}
        {activo === "carril" && <Carril peticion={peticionCarril} />}
      </main>
    </div>
  );
}
