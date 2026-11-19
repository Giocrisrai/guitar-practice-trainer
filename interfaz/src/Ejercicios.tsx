import { useEffect, useState } from "react";

import { Configurador } from "./Configurador";
import { DiagramaAcorde } from "./DiagramaAcorde";
import { Informe } from "./Informe";
import { InformeCambios } from "./InformeCambios";
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

  const ejercicio = estado?.ejercicio ?? null;
  const perfil = perfiles.find((p) => p.clave === ejercicio?.perfil);

  // Los ejercicios de acordes tienen su propia pantalla y su propio informe: el
  // avance que llega del servidor tiene OTRA forma (ni nota_actual ni cents, y a
  // cambio `faltan` y el tiempo de cambio), y `es_de_acordes` es lo que lo
  // discrimina. Ver la union en tiposEjercicio.ts.
  if (estado?.es_de_acordes) {
    const avance = estado.evaluacion;
    const informe = estado.informe;

    if (avance?.completado && informe) {
      return <InformeCambios informe={informe} onReiniciar={reiniciar} />;
    }

    if (avance) {
      return (
        <section className="ejercicio-en-curso">
          {ejercicio && <h2>{ejercicio.nombre}</h2>}

          <AvisosMetronomo
            pedido={estado.metronomo_pedido}
            sonando={estado.metronomo}
            pausado={estado.metronomo_pausado}
          />

          <div className="progreso">
            <div
              className="progreso-relleno"
              style={{ width: `${fraccionProgreso(avance.indice, avance.total) * 100}%` }}
            />
          </div>
          <p className="contador-progreso">
            {avance.indice} / {avance.total}
          </p>

          {avance.ultimo_cambio_s !== null && (
            <p className="ultimo-cambio">
              Último cambio: {avance.ultimo_cambio_s.toFixed(2)} s
            </p>
          )}

          {avance.acorde_actual && perfil && (
            <DiagramaAcorde
              acorde={avance.acorde_actual}
              perfil={perfil}
              faltan={avance.faltan}
              revelado={avance.ayuda_visible}
            />
          )}

          <button type="button" onClick={reiniciar}>
            Detener
          </button>
        </section>
      );
    }

    return <Configurador />;
  }

  const evaluacion = estado?.evaluacion ?? null;
  const informe = estado?.informe ?? null;

  if (evaluacion?.completado && informe) {
    return <Informe informe={informe} onReiniciar={reiniciar} />;
  }

  if (evaluacion) {
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

        {estado !== null && (
          <AvisosMetronomo
            pedido={estado.metronomo_pedido}
            sonando={estado.metronomo}
            pausado={estado.metronomo_pausado}
          />
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

  return <Configurador />;
}

/**
 * Los dos avisos del metrónomo, que ahora leen las dos pantallas: la de notas y
 * la de acordes. Se extrajo al añadir la segunda, no antes: duplicar el texto
 * habría dejado dos versiones del mismo mensaje que alguien corregiría a medias.
 *
 * Los dos estados son distintos y se dicen distintos: no haber tenido salida de
 * audio es definitivo para este ejercicio; estar pausado por falta de señal se
 * arregla volviendo a tocar (spec §5). Y el primer aviso solo vale cuando el
 * metrónomo se PIDIÓ y no sonó: si el usuario lo desmarcó, no hubo salida de
 * audio que faltara y no hay nada que avisar.
 */
function AvisosMetronomo({
  pedido,
  sonando,
  pausado,
}: {
  pedido: boolean;
  sonando: boolean;
  pausado: boolean;
}) {
  return (
    <>
      {pedido && !sonando && (
        <p className="aviso-metronomo">
          Sin metrónomo: el ejercicio funciona igual, pero nadie marca el compás.
        </p>
      )}
      {pausado && (
        <p className="aviso-metronomo pausado">
          Metrónomo en pausa: no llega señal. Se reanuda en cuanto vuelvas a tocar.
        </p>
      )}
    </>
  );
}
