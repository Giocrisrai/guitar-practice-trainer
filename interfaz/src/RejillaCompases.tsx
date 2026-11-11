import { useEffect, useState } from "react";

/**
 * Los compases de la pieza, para orientarse y para armar el bucle.
 *
 * Es un botón por compás y no un lienzo a propósito: lo que hace falta aquí es
 * poder pulsar y arrastrar, y un `<button>` ya trae el foco, el teclado y el
 * nombre accesible. El carril, que sí dibuja a 60 fps, es el lienzo.
 *
 * La diferencia entre un clic y un arrastre está en si se suelta donde se empezó:
 * soltar en el mismo compás es un clic -salta ahí- y soltar en otro es un rango.
 * Sin esa distinción, cada salto armaba además un bucle de un compás.
 *
 * OJO para quien cablea `alPedirSalto`: la rejilla deja pulsar CUALQUIER compás,
 * pero el servidor rechaza con 400 un salto a un compás fuera del rango del bucle
 * (`saltar_al_compas` valida contra el tramo del plan, no contra la pieza). Por eso
 * la prop se llama «pedir» y no «saltar»: quien la recibe puede tener que cambiar
 * antes el rango del plan para que el compás pulsado quepa, y recién entonces
 * saltar. Este componente no hace peticiones ni decide eso.
 */
export function RejillaCompases({
  total,
  enCurso,
  primero,
  ultimo,
  compasVariable,
  alPedirSalto,
  alMarcarRango,
}: {
  total: number;
  enCurso: number;
  primero: number;
  ultimo: number;
  compasVariable: boolean;
  /** Se pulsó este compás. Puede estar fuera del rango del bucle: ver arriba. */
  alPedirSalto: (compas: number) => void;
  alMarcarRango: (primero: number, ultimo: number) => void;
}) {
  // Estado y no `useRef`: lo que se está arrastrando también se PINTA (`marcando`).
  const [desde, setDesde] = useState<number | null>(null);
  const [hasta, setHasta] = useState<number | null>(null);

  // Mientras hay un arrastre en curso, soltar o cancelar el puntero EN CUALQUIER
  // sitio lo cancela. Sin esto, soltar fuera de la rejilla dejaba el arrastre
  // abierto, y el siguiente clic del usuario se leía como su final y marcaba un
  // rango que nadie pidió. Si se suelta sobre un compás, su propio `onPointerUp`
  // corre antes (el evento sube hasta `window`) y ya marcó el rango.
  const arrastrando = desde !== null;
  useEffect(() => {
    if (!arrastrando) return;
    const cancelar = () => {
      setDesde(null);
      setHasta(null);
    };
    window.addEventListener("pointerup", cancelar);
    window.addEventListener("pointercancel", cancelar);
    return () => {
      window.removeEventListener("pointerup", cancelar);
      window.removeEventListener("pointercancel", cancelar);
    };
  }, [arrastrando]);

  /**
   * El dedo arrastra como el raton solo si se SUELTA LA CAPTURA IMPLICITA.
   *
   * En tactil el navegador le da al elemento del `pointerdown` la captura del
   * puntero: desde ese momento todos los `pointermove` y el `pointerup` llegan a
   * ese mismo compas aunque el dedo ya este sobre otro, y tampoco hay
   * `pointerenter` en los vecinos. Por eso el arrastre funcionaba con raton (que
   * no captura) y en el telefono solo marcaba el compas donde se habia pulsado.
   * Soltando la captura, los eventos vuelven a ir al elemento de debajo del dedo.
   *
   * Se pregunta antes por `hasPointerCapture` porque soltar una captura que no
   * existe -el caso del raton- es un `NotFoundError`, y se comprueba que los dos
   * metodos existan porque jsdom (las pruebas) no implementa ninguno.
   */
  const soltarCaptura = (elemento: HTMLElement, puntero: number) => {
    if (typeof elemento.hasPointerCapture !== "function") return;
    if (typeof elemento.releasePointerCapture !== "function") return;
    if (!elemento.hasPointerCapture(puntero)) return;
    elemento.releasePointerCapture(puntero);
  };

  if (total === 0) return null;

  const compases = Array.from({ length: total }, (_, i) => i + 1);

  const soltar = (numero: number) => {
    setDesde(null);
    setHasta(null);
    if (desde === null || desde === numero) return;
    alMarcarRango(Math.min(desde, numero), Math.max(desde, numero));
  };

  return (
    <div className="rejilla-compases">
      {compasVariable && (
        <p className="aviso-compases">
          Esta canción cambia de compás y solo se guardó el primero: las barras
          caen en el sitio equivocado desde el cambio hasta el final.
        </p>
      )}
      <div className="compases">
        {compases.map((numero) => {
          const dentro = numero >= primero && numero <= ultimo;
          const marcando =
            desde !== null &&
            hasta !== null &&
            numero >= Math.min(desde, hasta) &&
            numero <= Math.max(desde, hasta);
          return (
            <button
              key={numero}
              className={[
                "compas",
                dentro ? "en-el-bucle" : "",
                marcando ? "marcando" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-current={numero === enCurso ? "true" : undefined}
              aria-label={`Compás ${numero}`}
              // `touch-action` NO se hereda: va en el elemento que el dedo toca.
              // Sin esto el navegador se queda el gesto para hacer scroll de la
              // pagina y el arrastre no llega a existir en el telefono.
              style={{ touchAction: "none" }}
              onPointerDown={(evento) => {
                soltarCaptura(evento.currentTarget, evento.pointerId);
                setDesde(numero);
                setHasta(numero);
              }}
              onPointerEnter={() => {
                if (desde !== null) setHasta(numero);
              }}
              // El dedo no manda `pointerenter` a los vecinos: el unico aviso de
              // que paso por aqui es el `pointermove` (ya sin captura).
              onPointerMove={() => {
                if (desde !== null) setHasta(numero);
              }}
              onPointerUp={() => soltar(numero)}
              onClick={() => alPedirSalto(numero)}
            >
              {numero}
            </button>
          );
        })}
      </div>
    </div>
  );
}
