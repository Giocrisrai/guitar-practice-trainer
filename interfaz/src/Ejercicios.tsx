import { useEffect, useState } from "react";

import { Configurador } from "./Configurador";
import { Informe } from "./Informe";
import { Mastil } from "./Mastil";
import { fraccionProgreso, mensajeDeFallo, posicionesAcertadas } from "./presentacionEjercicio";
import type { PerfilAfinacion } from "./tipos";
import { useEjercicio } from "./useEjercicio";

/**
 * Pantalla de ejercicios: orquesta el configurador, el ejercicio en curso y el
 * informe final.
 *
 * Sin ejercicio en curso se muestra el `Configurador`. Con ejercicio en curso se
 * muestran las tres capas que pide la spec §4.6 —la nota que toca ahora, las ya
 * acertadas en tenue y la barra de progreso—, y el mástil solo revela las
 * posiciones concretas cuando el servidor dice `ayuda_visible`. Al completarse se
 * muestra el `Informe`.
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
    // Las posiciones concretas de la nota actual solo se revelan cuando el
    // servidor dice que toca ayudar: resaltarlas siempre convertiria cualquier
    // ejercicio en uno de copiar del dibujo. Que nota toca, en cambio, se rotula
    // siempre (ver `notaObjetivo` en Mastil).
    const posiciones = evaluacion.ayuda_visible ? notaActual?.posiciones ?? [] : [];
    const tenues = posicionesAcertadas(ejercicio, informe);
    const mensaje = mensajeDeFallo(notaActual?.nombre ?? null, evaluacion.ultimo_fallo);

    return (
      <section className="ejercicio-en-curso">
        {ejercicio && <h2>{ejercicio.nombre}</h2>}

        {/* Los dos estados del metronomo son distintos y se dicen distintos: no
            haber tenido salida de audio es definitivo para este ejercicio; estar
            pausado por falta de senal se arregla volviendo a tocar (spec §5). */}
        {estado !== null && !estado.metronomo && (
          <p className="aviso-metronomo">
            Sin metrónomo: el ejercicio funciona igual, pero nadie marca el compás.
          </p>
        )}
        {estado?.metronomo_pausado && (
          <p className="aviso-metronomo pausado">
            Metrónomo en pausa: no llega señal. Se reanuda en cuanto vuelvas a tocar.
          </p>
        )}

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

        {perfil && (
          <Mastil
            perfil={perfil}
            posiciones={posiciones}
            posicionesTenues={tenues}
            notaObjetivo={notaActual?.nombre ?? null}
          />
        )}

        <button type="button" onClick={reiniciar}>
          Detener
        </button>
      </section>
    );
  }

  return <Configurador perfiles={perfiles} />;
}
