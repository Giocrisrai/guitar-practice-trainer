import { useState } from "react";

import { RejillaCompases } from "./RejillaCompases";
import type { EstadoEstudio, Plan, SeccionEnCompases } from "./tiposEstudio";

/** Los límites del deslizador, en porcentaje. Son los del núcleo
 * (`FACTOR_MINIMO` y `FACTOR_MAXIMO` en estudio.py), que es quien rechaza lo de fuera. */
const TEMPO_MINIMO_PORCIENTO = 40;
const TEMPO_MAXIMO_PORCIENTO = 100;
const PASO_TEMPO_PORCIENTO = 5;

/** Los compases de cuenta atrás de todo plan que sale de aquí: no hay control para
 * cambiarlos, y es el valor por defecto del núcleo. */
const COMPASES_DE_CUENTA_ATRAS = 1;

/**
 * Lo que el usuario pidió y el servidor NO publica en el paquete.
 *
 * El plan viaja ENTERO (`_plan_pedido` en servidor/app.py: lo que el cuerpo no diga
 * vuelve a su valor por defecto), y el estado solo devuelve cuatro de sus siete
 * campos: el rango, el factor y el bucle. `con_click` y `tempo_automatico` no
 * viajan —`click_sonando` es lo que SUENA, no lo que se pidió—. Sin recordarlos,
 * mover el deslizador apagaría el click y el tempo automático sin que nadie lo
 * hubiera pedido.
 *
 * Es la única copia local del plan, y se tolera porque el servidor nunca mueve
 * estos dos por su cuenta (el tempo automático mueve el FACTOR, que sí se lee del
 * estado). El día que `a_dict()` publique el plan, esto sobra.
 */
interface Interruptores {
  con_click: boolean;
  tempo_automatico: boolean;
}

const INTERRUPTORES_POR_DEFECTO: Interruptores = { con_click: false, tempo_automatico: false };

/**
 * El plan entero que describe el estado, con lo que se quiera cambiar encima.
 * Todo sale del paquete recibido salvo los dos interruptores.
 */
function planCompleto(
  estado: EstadoEstudio,
  interruptores: Interruptores,
  cambios: Plan
): Plan {
  return {
    primer_compas: estado.primer_compas,
    ultimo_compas: estado.ultimo_compas,
    factor_tempo: estado.factor_tempo,
    en_bucle: estado.en_bucle,
    compases_de_cuenta_atras: COMPASES_DE_CUENTA_ATRAS,
    ...interruptores,
    ...cambios,
  };
}

function porciento(factor: number): number {
  return Math.round(factor * 100);
}

/**
 * El rango que sirve para saltar a un compás que cae FUERA del bucle.
 *
 * El servidor valida el salto contra el tramo del plan y no contra la pieza: un
 * compás de fuera es un 400. Así que antes de saltar hay que mover el rango, y el
 * razonable es MOVER la ventana conservando su longitud, con el compás pedido de
 * primero (que es donde aterriza el salto). Se descartan las otras dos opciones:
 * - Ensanchar hasta abarcar los dos (del 3-4 al 40 al pulsar el 40) fabrica un
 *   bucle larguísimo que nadie pidió y que no se deshace con un clic.
 * - Un rango de un solo compás tira la longitud que el usuario eligió.
 * Si no cabe antes del final de la pieza, la ventana se corre hacia atrás: sigue
 * conteniendo el compás pedido.
 */
function rangoQueIncluye(estado: EstadoEstudio, compas: number): [number, number] {
  const longitud = estado.ultimo_compas - estado.primer_compas + 1;
  const ultimo = Math.min(estado.total_de_compases, compas + longitud - 1);
  const primero = Math.max(1, Math.min(compas, ultimo - longitud + 1));
  return [primero, ultimo];
}

interface PropiedadesControles {
  estado: EstadoEstudio;
  secciones: SeccionEnCompases[];
  /** Manda el plan ENTERO. Devuelve si el servidor lo aceptó (`false` corta el
   * salto que iba detrás); `void` se toma como aceptado. */
  alCambiarPlan: (plan: Plan) => Promise<boolean> | void;
  alPausar: (activa: boolean) => void;
  alSaltar: (compas: number) => void;
}

/**
 * Los controles de la pasada: tempo, bucle, secciones, click, tempo automático,
 * pausa y la rejilla de compases.
 *
 * Se dibujan DESDE EL ESTADO RECIBIDO, no desde uno propio: el plan vigente lo dice
 * el servidor (el tempo automático lo mueve solo) y una copia aquí se
 * desincronizaría. La excepción, acotada, son los dos `Interruptores`.
 *
 * Las dos pausas son distintas y se dicen por separado: `pausado` (sin señal del
 * cable) lo avisa `Carril`; `en_pausa` (la del usuario) es lo que cambia el botón.
 *
 * La rejilla vive aquí y no en `Carril` porque pulsar un compás fuera del bucle
 * obliga a mandar antes un plan, y el plan necesita los interruptores.
 */
export function ControlesEstudio({
  estado,
  secciones,
  alCambiarPlan,
  alPausar,
  alSaltar,
}: PropiedadesControles) {
  const [interruptores, setInterruptores] = useState<Interruptores>(INTERRUPTORES_POR_DEFECTO);

  const mandar = (cambios: Plan) =>
    alCambiarPlan(planCompleto(estado, interruptores, cambios));

  const cambiarInterruptor = (cambios: Partial<Interruptores>) => {
    const nuevos = { ...interruptores, ...cambios };
    setInterruptores(nuevos);
    void alCambiarPlan(planCompleto(estado, nuevos, {}));
  };

  /** Pedir un salto: si el compás cae fuera del tramo, primero se mueve el rango. */
  const pedirSalto = async (compas: number) => {
    if (compas < estado.primer_compas || compas > estado.ultimo_compas) {
      const [primero, ultimo] = rangoQueIncluye(estado, compas);
      const aceptado = await mandar({ primer_compas: primero, ultimo_compas: ultimo });
      if (aceptado === false) return;
    }
    alSaltar(compas);
  };

  const seccionElegida = estado.en_bucle
    ? secciones.findIndex(
        (s) => s.primer_compas === estado.primer_compas && s.ultimo_compas === estado.ultimo_compas
      )
    : -1;

  const elegirSeccion = (valor: string) => {
    if (valor === "") return;
    const seccion = secciones[Number(valor)];
    if (seccion === undefined) return;
    void mandar({
      primer_compas: seccion.primer_compas,
      ultimo_compas: seccion.ultimo_compas,
      en_bucle: true,
    });
  };

  const sugerido = estado.factor_sugerido;

  return (
    <div className="controles-estudio">
      <div className="control-estudio">
        <label htmlFor="estudio-tempo">Tempo</label>
        <input
          id="estudio-tempo"
          type="range"
          min={TEMPO_MINIMO_PORCIENTO}
          max={TEMPO_MAXIMO_PORCIENTO}
          step={PASO_TEMPO_PORCIENTO}
          value={porciento(estado.factor_tempo)}
          onChange={(evento) => void mandar({ factor_tempo: Number(evento.target.value) / 100 })}
        />
        {/* Un 70 % no le dice nada a nadie; «42 ppm» sí. */}
        <span className="lectura">
          {porciento(estado.factor_tempo)} % · {Math.round(estado.tempo_efectivo)} ppm
        </span>
        {sugerido !== null && (
          <button
            type="button"
            className="sugerencia-tempo"
            onClick={() => void mandar({ factor_tempo: sugerido })}
          >
            Subir el tempo al {porciento(sugerido)} %
          </button>
        )}
      </div>

      <div className="control-estudio">
        <label>
          <input
            type="checkbox"
            checked={estado.en_bucle}
            onChange={(evento) => void mandar({ en_bucle: evento.target.checked })}
          />
          Bucle
        </label>
        <label>
          <input
            type="checkbox"
            checked={interruptores.con_click}
            onChange={(evento) => cambiarInterruptor({ con_click: evento.target.checked })}
          />
          Click
        </label>
        <label>
          <input
            type="checkbox"
            checked={interruptores.tempo_automatico}
            onChange={(evento) =>
              cambiarInterruptor({ tempo_automatico: evento.target.checked })
            }
          />
          Tempo automático
        </label>
        {/* El click pedido que no suena (sin salida de audio) se dice: un
            interruptor encendido que no hace nada sería mentir. */}
        {interruptores.con_click && !estado.click_sonando && (
          <span className="aviso-click">Sin click: no hay salida de audio.</span>
        )}
      </div>

      {secciones.length > 0 && (
        <div className="control-estudio">
          <label htmlFor="estudio-seccion">Sección</label>
          <select
            id="estudio-seccion"
            value={seccionElegida === -1 ? "" : String(seccionElegida)}
            onChange={(evento) => elegirSeccion(evento.target.value)}
          >
            <option value="">Elige una sección</option>
            {secciones.map((seccion, indice) => (
              <option key={`${seccion.nombre}-${indice}`} value={String(indice)}>
                {seccion.nombre} (compases {seccion.primer_compas}-{seccion.ultimo_compas})
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="control-estudio">
        <button type="button" onClick={() => alPausar(!estado.en_pausa)}>
          {estado.en_pausa ? "Reanudar" : "Pausar"}
        </button>
        {estado.en_pausa && (
          <span className="aviso-pausa-usuario">En pausa: pulsa Reanudar para seguir.</span>
        )}
        {estado.en_bucle && <span className="lectura">Repetición {estado.repeticion}</span>}
        {estado.cuenta_atras_restante_s > 0 && (
          <span className="cuenta-atras">{Math.ceil(estado.cuenta_atras_restante_s)}</span>
        )}
      </div>

      <RejillaCompases
        total={estado.total_de_compases}
        enCurso={estado.compas_en_curso}
        primero={estado.primer_compas}
        ultimo={estado.ultimo_compas}
        compasVariable={estado.compas_variable}
        alPedirSalto={(compas) => void pedirSalto(compas)}
        alMarcarRango={(primero, ultimo) =>
          void mandar({ primer_compas: primero, ultimo_compas: ultimo, en_bucle: true })
        }
      />
    </div>
  );
}
