import { useEffect, useState } from "react";

import { Configurador } from "./Configurador";
import { Informe } from "./Informe";
import { Mastil } from "./Mastil";
import { fraccionProgreso, mensajeDeFallo } from "./presentacionEjercicio";
import type { PerfilAfinacion } from "./tipos";
import { useEjercicio } from "./useEjercicio";

/**
 * Pantalla de ejercicios: orquesta el configurador, el ejercicio en curso y el
 * informe final.
 *
 * Sin ejercicio en curso se muestra el `Configurador`. Con ejercicio en curso se
 * muestra la nota actual, el mástil —resaltando esa nota solo si el servidor
 * dice `ayuda_visible`— y el progreso. Al completarse se muestra el `Informe`.
 */
export function Ejercicios() {
  const { estado } = useEjercicio();
  const [perfiles, setPerfiles] = useState<PerfilAfinacion[]>([]);

  useEffect(() => {
    fetch("/api/perfiles")
      .then((r) => r.json())
      .then(setPerfiles);
  }, []);

  const reiniciar = () => {
    fetch("/api/ejercicios/detener", { method: "POST" });
  };

  const evaluacion = estado?.evaluacion ?? null;
  const ejercicio = estado?.ejercicio ?? null;
  const informe = estado?.informe ?? null;

  if (evaluacion?.completado && informe) {
    return <Informe informe={informe} onReiniciar={reiniciar} />;
  }

  if (evaluacion) {
    const perfil = perfiles.find((p) => p.clave === ejercicio?.perfil);
    const notaActual = evaluacion.nota_actual;
    // La ayuda del mastil: solo se resalta la nota actual cuando el servidor
    // dice que toca ayudar. Si no, el mastil se queda vacio a proposito.
    const posiciones = evaluacion.ayuda_visible ? notaActual?.posiciones ?? [] : [];
    const mensaje = mensajeDeFallo(notaActual?.nombre ?? null, evaluacion.ultimo_fallo);

    return (
      <section className="ejercicio-en-curso">
        {ejercicio && <h2>{ejercicio.nombre}</h2>}

        <div className="progreso">
          <div
            className="progreso-relleno"
            style={{ width: `${fraccionProgreso(evaluacion.indice, evaluacion.total) * 100}%` }}
          />
        </div>
        <p className="contador-progreso">
          {evaluacion.indice} / {evaluacion.total}
        </p>

        <div className="nota-actual">{notaActual?.nombre ?? "—"}</div>

        {mensaje && <p className="mensaje-fallo">{mensaje}</p>}

        {perfil && <Mastil perfil={perfil} posiciones={posiciones} />}

        <button type="button" onClick={reiniciar}>
          Detener
        </button>
      </section>
    );
  }

  return <Configurador />;
}
