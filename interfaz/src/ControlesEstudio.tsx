import { useState } from "react";

import { RejillaCompases } from "./RejillaCompases";
import type {
  AjusteAcompanamiento,
  EstadoEstudio,
  Plan,
  SeccionEnCompases,
} from "./tiposEstudio";

/** Los límites del deslizador, en porcentaje. Son los del núcleo
 * (`FACTOR_MINIMO` y `FACTOR_MAXIMO` en estudio.py), que es quien rechaza lo de fuera. */
const TEMPO_MINIMO_PORCIENTO = 40;
const TEMPO_MAXIMO_PORCIENTO = 100;
const PASO_TEMPO_PORCIENTO = 5;

/**
 * El volumen con el que el servidor carga el fondo, en porcentaje
 * (`VOLUMEN_DEL_FONDO_POR_OMISION` en servidor/piezas.py).
 *
 * Es el PUNTO DE PARTIDA del deslizador y nada más: el volumen vivo NO viaja en
 * el estado publicado —los cinco campos del fondo que llegan son otros—, así que
 * aquí no hay nada que seguir y lo que se ve después de la primera orden es lo
 * que el usuario puso. Si algún día el servidor lo publica, este deslizador debe
 * pasar a leerlo como el de tempo lee `factor_tempo`, y esta constante sobra.
 */
const VOLUMEN_DEL_FONDO_POR_OMISION_PORCIENTO = 60;
const PASO_VOLUMEN_PORCIENTO = 5;

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
  /** Manda SOLO lo que cambia: el servidor conserva el resto del plan vigente.
   * Devuelve si el servidor lo aceptó (`false` corta el
   * salto que iba detrás); `void` se toma como aceptado. */
  alCambiarPlan: (plan: Plan) => Promise<boolean> | void;
  alPausar: (activa: boolean) => void;
  alSaltar: (compas: number) => void;
  /** El interruptor y el volumen del fondo. Como `alCambiarPlan`, manda SOLO lo
   * que cambia y devuelve si el servidor lo aceptó (`void` se toma por aceptado). */
  alAjustarAcompanamiento: (ajuste: AjusteAcompanamiento) => Promise<boolean> | void;
}

/**
 * Los controles de la pasada: tempo, bucle, secciones, click, tempo automático,
 * pausa y la rejilla de compases.
 *
 * Se dibujan DESDE EL ESTADO RECIBIDO, no desde uno propio: el plan vigente lo dice
 * el servidor (el tempo automático lo mueve solo) y una copia aquí se
 * desincronizaría. Cada orden manda SOLO lo que cambia, porque
 * `POST /api/piezas/plan` es un parche. Lo único local es el gesto del
 * deslizador mientras se arrastra (ver `arrastre`).
 *
 * Las dos pausas son distintas y se dicen por separado: `pausado` (sin señal del
 * cable) lo avisa `Carril`; `en_pausa` (la del usuario) es lo que cambia el botón.
 *
 * OJO: la rejilla de compases se monta AQUÍ y no en `Carril`, aunque el plan de la
 * etapa la pone en `Carril`. Pulsar un compás fuera del bucle obliga a mandar antes
 * un plan con un rango nuevo y después el salto (`pedirSalto`), y eso necesita el
 * estado, `alCambiarPlan` y `alSaltar`, que ya están en este componente: sacarla
 * obligaría a pasar la lógica de `rangoQueIncluye` a `Carril`.
 */
export function ControlesEstudio({
  estado,
  secciones,
  alCambiarPlan,
  alPausar,
  alSaltar,
  alAjustarAcompanamiento,
}: PropiedadesControles) {
  /**
   * El porcentaje que se VE mientras el deslizador está agarrado; `null` cuando no
   * se está arrastrando.
   *
   * No es estado del plan, es el gesto en curso: el plan vigente sigue siendo el
   * del servidor (`estado.factor_tempo`) y esto solo existe entre que se agarra el
   * deslizador y se suelta. La orden se manda al soltar y no en cada paso, porque
   * cada cambio de factor reconstruye el seguidor en el núcleo y un arrastre
   * dispararía decenas de reconstrucciones y de peticiones.
   */
  const [arrastre, setArrastre] = useState<number | null>(null);

  /**
   * El valor YA MANDADO que se sigue mostrando hasta que el servidor conteste.
   *
   * Sin esto el deslizador parpadeaba al soltar: `arrastre` se borraba en el acto
   * y el deslizador volvia por un momento al `estado.factor_tempo` viejo -el
   * valor retrocedia a la vista- hasta que llegaba el estado nuevo, un latido
   * despues. Se guarda tambien el factor que el servidor decia al mandarlo
   * (`factorPrevio`): el valor mandado deja de pintarse en cuanto el estado se
   * mueve a CUALQUIER otra cosa, que es la senal de que el servidor ya contesto,
   * sea con lo que pedimos o con otra cosa (el tempo automatico tambien lo mueve).
   */
  const [mandado, setMandado] = useState<{ porciento: number; factorPrevio: number } | null>(
    null,
  );

  // El estado ya se movio: lo mandado caduca y no puede resucitar mas tarde (el
  // tempo automatico puede devolver el factor al de antes un rato despues). Se
  // ajusta EN EL RENDER y no en un efecto: es estado derivado de una propiedad
  // nueva, no una sincronizacion con nada de fuera.
  if (mandado !== null && estado.factor_tempo !== mandado.factorPrevio) setMandado(null);

  /** Lo que se VE: el gesto en curso, si no lo ya mandado, si no el servidor. */
  const tempoMostrado =
    arrastre ??
    (mandado !== null && estado.factor_tempo === mandado.factorPrevio
      ? mandado.porciento
      : porciento(estado.factor_tempo));

  /** El gesto en curso del deslizador del fondo; `null` si no se arrastra nada. */
  const [arrastreVolumen, setArrastreVolumen] = useState<number | null>(null);
  /**
   * El volumen del fondo que se VE, en porcentaje.
   *
   * Es local porque el servidor no publica el volumen vivo (ver
   * `VOLUMEN_DEL_FONDO_POR_OMISION_PORCIENTO`), y se adopta EN EL ACTO al soltar,
   * antes de saber si la orden llegó. Es la lección del deslizador de tempo de la
   * 3d: esperar a la respuesta para adoptarlo devuelve el deslizador al valor
   * anterior durante el viaje de la petición, y ese retroceso a la vista es el
   * parpadeo. Solo retrocede si el servidor RECHAZA, que es cuando el valor
   * anterior volvió a ser la verdad.
   */
  const [volumenFondo, setVolumenFondo] = useState(VOLUMEN_DEL_FONDO_POR_OMISION_PORCIENTO);

  /** Manda SOLO lo que cambia: el servidor conserva el resto del plan vigente. */
  const mandar = (cambios: Plan) => alCambiarPlan(cambios);

  /**
   * Un gesto que se interrumpe (en táctil, al empezar un scroll el navegador manda
   * `pointercancel`) se DESCARTA: el usuario no quiso soltar ahí, y mandar el
   * valor a medias sería inventarse una orden. Sin esto el número del gesto se
   * quedaba pegado enseñando algo que el servidor no tiene.
   */
  const descartarTempo = () => setArrastre(null);

  const soltarTempo = () => {
    if (arrastre === null) return;
    setArrastre(null);
    setMandado({ porciento: arrastre, factorPrevio: estado.factor_tempo });
    const respuesta = mandar({ factor_tempo: arrastre / 100 });
    // Un rechazo no va a mover el estado nunca: el valor mandado se tira y el
    // deslizador vuelve al vigente, que es la verdad.
    void Promise.resolve(respuesta).then((aceptado) => {
      if (aceptado === false) setMandado(null);
    });
  };

  const volumenMostrado = arrastreVolumen ?? volumenFondo;

  const descartarVolumen = () => setArrastreVolumen(null);

  const soltarVolumen = () => {
    if (arrastreVolumen === null) return;
    const pedido = arrastreVolumen;
    const anterior = volumenFondo;
    setArrastreVolumen(null);
    // SE ADOPTA YA, no al contestar: mover esta línea dentro del `then` es
    // exactamente el parpadeo que la 3d arregló en el de tempo.
    setVolumenFondo(pedido);
    // El volumen viaja de 0 a 1, como lo pide el endpoint; el deslizador habla
    // en porcentaje porque es lo que el usuario lee.
    void Promise.resolve(alAjustarAcompanamiento({ volumen: pedido / 100 })).then(
      (aceptado) => {
        if (aceptado === false) setVolumenFondo(anterior);
      },
    );
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
  /**
   * El servidor escribe `factor_sugerido` EN LAS DOS DIRECCIONES: dos pasadas
   * buenas suben un paso, y una sola por debajo del 70 % baja uno sin esperar a
   * la segunda. El botón decía siempre «Subir», así que una pasada mala al 50 %
   * pintaba «Subir el tempo al 45 %», que es lo contrario de lo que iba a pasar.
   * La dirección se saca comparando con el factor vigente y no de un campo nuevo:
   * los dos números ya viajan en el estado.
   */
  const verbo = sugerido !== null && sugerido < estado.factor_tempo ? "Bajar" : "Subir";

  /**
   * Si hay algo que ofrecer: un archivo de fondo cargado, con voces ajenas o con
   * la propia parte como guía.
   *
   * NO es `acompanamiento_posible`, y la diferencia es el motivo de que esto
   * exista: ese campo es `hay fondo Y la entrada es el cable`, así que vale
   * `false` tanto cuando no hay nada que sonar como cuando sí lo hay y la entrada
   * es un micrófono. En el primer caso no hay control que enseñar; en el segundo
   * hay control, apagado, y sobre todo hay un aviso que dar. Esto no rehace la
   * regla del servidor: la lee de los campos que publica (`es_tu_parte` es
   * `hay fondo y sin voces ajenas`, así que los dos juntos son «hay fondo»).
   */
  const hayFondo = estado.acompanamiento_voces > 0 || estado.acompanamiento_es_tu_parte;
  /** Lo que suena no se llama igual: sin otras pistas, lo que vuelve es tu propia
   * parte más bajita, y llamar a eso «Acompañamiento» hace creer al alumno que
   * oye a otro tocando lo que en realidad está tocando él. */
  const nombreDelFondo = estado.acompanamiento_es_tu_parte ? "Guía" : "Acompañamiento";
  const excluidas = estado.acompanamiento_excluidas;

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
          value={tempoMostrado}
          onChange={(evento) => setArrastre(Number(evento.target.value))}
          onPointerUp={soltarTempo}
          onKeyUp={soltarTempo}
          onPointerCancel={descartarTempo}
          // Perder el foco con un valor ya movido y sin soltar CONFIRMA el gesto,
          // como el `change` de un campo de formulario: el usuario puso ese valor
          // a propósito. Si ya se soltó, `arrastre` es null y no hace nada.
          onBlur={soltarTempo}
        />
        {/* Un 70 % no le dice nada a nadie; «42 ppm» sí. */}
        <span className="lectura">
          {tempoMostrado} % · {Math.round(estado.tempo_efectivo)} ppm
        </span>
        {sugerido !== null && (
          <button
            type="button"
            className="sugerencia-tempo"
            onClick={() => void mandar({ factor_tempo: sugerido })}
          >
            {verbo} el tempo al {porciento(sugerido)} %
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
            checked={estado.con_click}
            onChange={(evento) => void mandar({ con_click: evento.target.checked })}
          />
          Click
        </label>
        <label>
          <input
            type="checkbox"
            checked={estado.tempo_automatico}
            onChange={(evento) => void mandar({ tempo_automatico: evento.target.checked })}
          />
          Tempo automático
        </label>
        {/* El click pedido que no suena (sin salida de audio) se dice: un
            interruptor encendido que no hace nada sería mentir. */}
        {estado.con_click && !estado.click_sonando && (
          <span className="aviso-click">Sin click: no hay salida de audio.</span>
        )}
      </div>

      {hayFondo && (
        <div className="control-estudio control-acompanamiento">
          <label>
            {/* Lo que SUENA, no lo que se pidió: con la entrada equivocada el
                pestillo del servidor lo deja callado y la casilla sale apagada,
                igual que el click sin salida de audio. La regla de cuándo suena
                NO se decide aquí: llega publicada. */}
            <input
              type="checkbox"
              checked={estado.acompanamiento_sonando}
              onChange={(evento) =>
                void alAjustarAcompanamiento({ encendido: evento.target.checked })
              }
            />
            {nombreDelFondo}
          </label>

          <label htmlFor="estudio-volumen-fondo">Volumen del fondo</label>
          <input
            id="estudio-volumen-fondo"
            type="range"
            min={0}
            max={100}
            step={PASO_VOLUMEN_PORCIENTO}
            value={volumenMostrado}
            onChange={(evento) => setArrastreVolumen(Number(evento.target.value))}
            onPointerUp={soltarVolumen}
            onKeyUp={soltarVolumen}
            onPointerCancel={descartarVolumen}
            onBlur={soltarVolumen}
          />
          <span className="lectura">{volumenMostrado} %</span>

          {/* Cuántas voces suenan y cuántas no. Un fondo al que le falta el bajo
              sin que nada lo diga parece roto, y quien lee la cuenta necesita
              saber si faltan dos voces o si nunca las hubo. */}
          <span className="voces-del-fondo">
            {estado.acompanamiento_es_tu_parte
              ? "La canción no traía otras pistas: suena tu propia parte como guía, más bajita."
              : // El verbo concuerda con la cuenta: «Suenan 1 voz» canta.
                `${estado.acompanamiento_voces === 1 ? "Suena" : "Suenan"} ${
                  estado.acompanamiento_voces
                } ${estado.acompanamiento_voces === 1 ? "voz" : "voces"} de fondo.`}
          </span>
          {excluidas.length > 0 && (
            <span className="voces-excluidas">
              {excluidas.length === 1
                ? "1 pista se quedó fuera"
                : `${excluidas.length} pistas se quedaron fuera`}
              : {excluidas.map((e) => `${e.pista} (${e.motivo})`).join("; ")}.
            </span>
          )}

          {/* EL AVISO, y es el anti-objetivo de la etapa entera: si la entrada no
              es el cable, el fondo vuelve a entrar por ella, el detector de
              ataques lo cobra como notas tuyas y el informe se llena de aciertos
              que no tocó nadie —sin que se note, porque los números salen—.

              Se enseña SIEMPRE que `acompanamiento_posible` es `false`, también
              —sobre todo— mientras el fondo suena: el usuario puede encenderlo a
              mano, es su equipo y su decisión, y el servidor deja el campo quieto
              a propósito para que el recordatorio no se vaya. Un aviso que
              desaparece en cuanto le desobedeces no es un aviso.

              La condición es el campo publicado, tal cual. Aquí no se busca el
              cable ni se deduce nada: la lección de `esperando_notas`. */}
          {!estado.acompanamiento_posible && (
            <p className="aviso-acompanamiento">
              La entrada no es el cable: lo que suene de fondo entra otra vez por el
              micrófono y el informe lo cuenta como notas tuyas. Con auriculares no pasa.
            </p>
          )}
        </div>
      )}

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
