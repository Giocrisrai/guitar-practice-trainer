import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ControlesEstudio } from "./ControlesEstudio";
import type { EstadoEstudio, Plan, SeccionEnCompases } from "./tiposEstudio";

/** Una pasada de 12 compases, entera, a tempo escrito, sin bucle. */
const ESTADO: EstadoEstudio = {
  arranque: 1, instante_s: 0, indice_actual: 0, total: 12, completado: false,
  tocadas: [], pausado: false, instante_pulsos: 0, compas_en_curso: 1,
  total_de_compases: 12, primer_compas: 1, ultimo_compas: 12, repeticion: 1,
  cuenta_atras_restante_s: 0, factor_tempo: 1, tempo_efectivo: 60,
  en_bucle: false, con_click: false, tempo_automatico: false,
  en_pausa: false, compas_variable: false,
  ritmo_aproximado: false, tramo_terminado: false, click_sonando: false,
  factor_sugerido: null,
};

const SECCIONES: SeccionEnCompases[] = [
  { nombre: "Intro", primer_compas: 1, ultimo_compas: 4 },
  { nombre: "Estribillo", primer_compas: 5, ultimo_compas: 12 },
];

function pintar(
  estado: Partial<EstadoEstudio> = {},
  secciones: SeccionEnCompases[] = [],
  respuestaDelPlan: Promise<boolean> | void = undefined,
) {
  const alCambiarPlan = vi.fn((_plan: Plan) => respuestaDelPlan);
  const alPausar = vi.fn();
  const alSaltar = vi.fn();
  const resultado = render(
    <ControlesEstudio
      estado={{ ...ESTADO, ...estado }}
      secciones={secciones}
      alCambiarPlan={alCambiarPlan}
      alPausar={alPausar}
      alSaltar={alSaltar}
    />,
  );
  return { alCambiarPlan, alPausar, alSaltar, ...resultado };
}

const casilla = (nombre: string) => screen.getByLabelText(nombre) as HTMLInputElement;
const deslizador = () => casilla("Tempo");
const compas = (n: number) => screen.getByRole("button", { name: `Compás ${n}` });

/** Arrastra el deslizador por esos porcentajes y lo suelta. */
function arrastrarTempo(...porcentajes: number[]) {
  for (const valor of porcentajes) fireEvent.change(deslizador(), { target: { value: String(valor) } });
  fireEvent.pointerUp(deslizador());
}

describe("el tempo", () => {
  it("el deslizador va del 40 % al 100 % en pasos del 5 % y marca lo que dice el estado", () => {
    pintar({ factor_tempo: 0.7 });
    expect(deslizador().getAttribute("min")).toBe("40");
    expect(deslizador().getAttribute("max")).toBe("100");
    expect(deslizador().getAttribute("step")).toBe("5");
    expect(deslizador().value).toBe("70");
  });

  it("el deslizador sigue al estado: si el servidor mueve el tempo, se mueve", () => {
    const { rerender, alCambiarPlan, alPausar, alSaltar } = pintar({ factor_tempo: 0.7 });
    rerender(
      <ControlesEstudio
        estado={{ ...ESTADO, factor_tempo: 0.85 }}
        secciones={[]}
        alCambiarPlan={alCambiarPlan}
        alPausar={alPausar}
        alSaltar={alSaltar}
      />,
    );
    expect(deslizador().value).toBe("85");
  });

  it("al soltar manda el factor, no el porcentaje, y SOLO el factor", () => {
    // Con rango, bucle y click puestos: el parche no lleva nada de eso.
    const { alCambiarPlan } = pintar({
      primer_compas: 3, ultimo_compas: 5, en_bucle: true, con_click: true,
    });
    arrastrarTempo(70);
    expect(alCambiarPlan).toHaveBeenCalledTimes(1);
    const cuerpo = alCambiarPlan.mock.calls[0][0];
    expect(cuerpo).toEqual({ factor_tempo: 0.7 });
    expect(Object.keys(cuerpo)).toEqual(["factor_tempo"]);
  });

  it("mientras se arrastra no se manda nada, y se ve el valor que se lleva", () => {
    const { alCambiarPlan } = pintar({ factor_tempo: 1 });
    fireEvent.change(deslizador(), { target: { value: "55" } });
    expect(alCambiarPlan).not.toHaveBeenCalled();
    expect(deslizador().value).toBe("55");
    expect(screen.getByText(/55 %/)).toBeDefined();
  });

  it("tres movimientos seguidos y un soltar mandan UNA petición, con el último valor", () => {
    const { alCambiarPlan } = pintar();
    arrastrarTempo(90, 80, 65);
    expect(alCambiarPlan).toHaveBeenCalledTimes(1);
    expect(alCambiarPlan).toHaveBeenCalledWith({ factor_tempo: 0.65 });
  });

  it("con el teclado también: las flechas mueven y al soltar la tecla se manda", () => {
    const { alCambiarPlan } = pintar();
    fireEvent.change(deslizador(), { target: { value: "95" } });
    expect(alCambiarPlan).not.toHaveBeenCalled();
    fireEvent.keyUp(deslizador(), { key: "ArrowLeft" });
    expect(alCambiarPlan).toHaveBeenCalledTimes(1);
    expect(alCambiarPlan).toHaveBeenCalledWith({ factor_tempo: 0.95 });
  });

  it("soltar sin haber movido nada no manda nada", () => {
    const { alCambiarPlan } = pintar();
    fireEvent.pointerUp(deslizador());
    fireEvent.keyUp(deslizador(), { key: "Tab" });
    expect(alCambiarPlan).not.toHaveBeenCalled();
  });

  it("soltar dos veces seguidas no repite la orden", () => {
    const { alCambiarPlan } = pintar();
    arrastrarTempo(70);
    fireEvent.keyUp(deslizador(), { key: "ArrowLeft" });
    expect(alCambiarPlan).toHaveBeenCalledTimes(1);
  });

  it("después de soltar, el deslizador vuelve a seguir al estado", () => {
    pintar({ factor_tempo: 0.8 });
    arrastrarTempo(60);
    expect(deslizador().value).toBe("80");
  });

  it("los pulsos por minuto se redondean al entero", () => {
    const { container } = pintar({ factor_tempo: 0.7, tempo_efectivo: 41.67 });
    expect(container.querySelector(".control-estudio .lectura")?.textContent).toBe(
      "70 % · 42 ppm",
    );
  });

  it("enseña el porcentaje y los pulsos por minuto efectivos", () => {
    // Un 70 % no le dice nada a nadie; «42 ppm» sí.
    const { container } = pintar({ factor_tempo: 0.7, tempo_efectivo: 42 });
    expect(container.querySelector(".control-estudio .lectura")?.textContent).toBe(
      "70 % · 42 ppm",
    );
  });
});

describe("la sugerencia de tempo", () => {
  it("con un factor sugerido lo ofrece, diciendo a qué sube", () => {
    pintar({ factor_tempo: 0.7, factor_sugerido: 0.75 });
    expect(screen.getByRole("button", { name: "Subir el tempo al 75 %" })).toBeDefined();
  });

  it("dice el porcentaje sin ruido de coma flotante (0,57 por 100 da 56,99999)", () => {
    pintar({ factor_tempo: 0.5, factor_sugerido: 0.57 });
    expect(screen.getByRole("button", { name: "Subir el tempo al 57 %" })).toBeDefined();
  });

  it("al aplicarla manda solo ese factor", () => {
    const { alCambiarPlan } = pintar({
      primer_compas: 2, ultimo_compas: 6, en_bucle: true, factor_tempo: 0.7, factor_sugerido: 0.75,
    });
    fireEvent.click(screen.getByRole("button", { name: "Subir el tempo al 75 %" }));
    expect(alCambiarPlan.mock.calls).toEqual([[{ factor_tempo: 0.75 }]]);
  });

  it("sin sugerencia no ofrece nada", () => {
    pintar({ factor_sugerido: null });
    // El deslizador está: los controles se pintaron y lo que falta es el botón.
    expect(deslizador()).toBeDefined();
    expect(screen.queryByRole("button", { name: /subir el tempo/i })).toBeNull();
  });

  it("no la aplica sola: ofrecerla no manda ningún plan", () => {
    const { alCambiarPlan } = pintar({ factor_sugerido: 0.75 });
    expect(alCambiarPlan).not.toHaveBeenCalled();
  });
});

describe("el bucle, el click y el tempo automático", () => {
  it("el interruptor del bucle refleja el estado y manda en_bucle", () => {
    const { alCambiarPlan } = pintar({ en_bucle: false });
    expect(casilla("Bucle").checked).toBe(false);
    fireEvent.click(casilla("Bucle"));
    expect(alCambiarPlan).toHaveBeenCalledWith({ en_bucle: true });
  });

  it("con el bucle en marcha, el interruptor lo APAGA", () => {
    const { alCambiarPlan } = pintar({ en_bucle: true });
    fireEvent.click(casilla("Bucle"));
    expect(alCambiarPlan).toHaveBeenCalledWith({ en_bucle: false });
  });

  it("el interruptor del click refleja el estado sin que nadie lo haya pulsado", () => {
    pintar({ con_click: true });
    expect(casilla("Click").checked).toBe(true);
    expect(casilla("Tempo automático").checked).toBe(false);
  });

  it("el interruptor del tempo automático refleja el estado", () => {
    pintar({ tempo_automatico: true });
    expect(casilla("Tempo automático").checked).toBe(true);
    expect(casilla("Click").checked).toBe(false);
  });

  it("el click manda solo con_click", () => {
    const { alCambiarPlan } = pintar();
    fireEvent.click(casilla("Click"));
    expect(alCambiarPlan.mock.calls).toEqual([[{ con_click: true }]]);
  });

  it("con el click puesto, el interruptor lo APAGA", () => {
    const { alCambiarPlan } = pintar({ con_click: true });
    fireEvent.click(casilla("Click"));
    expect(alCambiarPlan.mock.calls).toEqual([[{ con_click: false }]]);
  });

  it("el tempo automático manda solo tempo_automatico", () => {
    const { alCambiarPlan } = pintar();
    fireEvent.click(casilla("Tempo automático"));
    expect(alCambiarPlan.mock.calls).toEqual([[{ tempo_automatico: true }]]);
  });

  it("con el tempo automático puesto, el interruptor lo APAGA", () => {
    const { alCambiarPlan } = pintar({ tempo_automatico: true });
    fireEvent.click(casilla("Tempo automático"));
    expect(alCambiarPlan.mock.calls).toEqual([[{ tempo_automatico: false }]]);
  });

  it("si el click está pedido pero no suena, lo dice", () => {
    const { container } = pintar({ con_click: true, click_sonando: false });
    expect(casilla("Click").checked).toBe(true);
    expect(container.querySelector(".aviso-click")?.textContent).toBe(
      "Sin click: no hay salida de audio.",
    );
  });

  it("si el click está pedido y suena, no avisa de nada", () => {
    const { container } = pintar({ con_click: true, click_sonando: true });
    expect(casilla("Click").checked).toBe(true);
    expect(container.querySelector(".aviso-click")).toBeNull();
  });

  it("si el click no está pedido, que no suene no es noticia", () => {
    const { container } = pintar({ con_click: false, click_sonando: false });
    expect(casilla("Click").checked).toBe(false);
    expect(container.querySelector(".aviso-click")).toBeNull();
  });
});

describe("las secciones", () => {
  it("elegir una arma el bucle con sus compases, sin tocar lo demás del plan", () => {
    const { alCambiarPlan } = pintar({ factor_tempo: 0.8 }, SECCIONES);
    fireEvent.change(casilla("Sección"), { target: { value: "1" } });
    expect(alCambiarPlan).toHaveBeenCalledWith({ primer_compas: 5, ultimo_compas: 12, en_bucle: true });
  });

  it("la lista ofrece cada sección con su nombre y sus compases", () => {
    pintar({}, SECCIONES);
    const opciones = Array.from(casilla("Sección").querySelectorAll("option")).map(
      (o) => o.textContent,
    );
    expect(opciones).toEqual([
      "Elige una sección",
      "Intro (compases 1-4)",
      "Estribillo (compases 5-12)",
    ]);
  });

  it("marca la sección cuyo bucle está en marcha, según el estado", () => {
    pintar({ en_bucle: true, primer_compas: 5, ultimo_compas: 12 }, SECCIONES);
    expect(casilla("Sección").value).toBe("1");
  });

  it("un rango que solo empieza donde una sección no es esa sección", () => {
    pintar({ en_bucle: true, primer_compas: 5, ultimo_compas: 8 }, SECCIONES);
    expect(casilla("Sección").value).toBe("");
  });

  it("sin bucle no marca ninguna aunque el rango coincida", () => {
    pintar({ en_bucle: false, primer_compas: 5, ultimo_compas: 12 }, SECCIONES);
    expect(casilla("Sección").value).toBe("");
  });

  it("la opción de invitación no manda nada", () => {
    const { alCambiarPlan } = pintar({ en_bucle: true, primer_compas: 5, ultimo_compas: 12 }, SECCIONES);
    fireEvent.change(casilla("Sección"), { target: { value: "" } });
    expect(alCambiarPlan).not.toHaveBeenCalled();
  });

  it("sin secciones, la lista no aparece", () => {
    // Muchas tablaturas y MIDIs no traen marcadores: una lista vacía solo estorba.
    pintar({}, []);
    expect(casilla("Bucle")).toBeDefined();
    expect(screen.queryByLabelText("Sección")).toBeNull();
  });
});

describe("la pausa del usuario", () => {
  it("pausar y reanudar son el mismo botón con dos estados", () => {
    const { alPausar } = pintar({ en_pausa: false });
    expect(screen.queryByRole("button", { name: "Reanudar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Pausar" }));
    expect(alPausar).toHaveBeenCalledWith(true);
  });

  it("en pausa, el botón ofrece reanudar", () => {
    const { alPausar } = pintar({ en_pausa: true });
    expect(screen.queryByRole("button", { name: "Pausar" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reanudar" }));
    expect(alPausar).toHaveBeenCalledWith(false);
  });

  it("la pausa del usuario se dice, y no es la de falta de señal", () => {
    const { container } = pintar({ en_pausa: true, pausado: false });
    expect(container.querySelector(".aviso-pausa-usuario")?.textContent).toBe(
      "En pausa: pulsa Reanudar para seguir.",
    );
    expect(container.textContent).not.toContain("señal");
  });

  it("un carril sin señal NO está en pausa del usuario", () => {
    const { container } = pintar({ pausado: true, en_pausa: false });
    // El botón sigue ofreciendo pausar: quien se ha ido es el cable, no el usuario.
    expect(screen.getByRole("button", { name: "Pausar" })).toBeDefined();
    expect(container.querySelector(".aviso-pausa-usuario")).toBeNull();
  });
});

describe("la repetición y la cuenta atrás", () => {
  it("enseña la repetición cuando hay bucle", () => {
    const { container } = pintar({ en_bucle: true, repeticion: 4 });
    expect(container.textContent).toContain("Repetición 4");
  });

  it("sin bucle no hay repetición que enseñar", () => {
    const { container } = pintar({ en_bucle: false, repeticion: 4 });
    expect(screen.getByRole("button", { name: "Pausar" })).toBeDefined();
    expect(container.textContent).not.toContain("Repetición");
  });

  it("la cuenta atrás se enseña en segundos enteros, redondeando hacia arriba", () => {
    const { container } = pintar({ cuenta_atras_restante_s: 2.4 });
    expect(container.querySelector(".cuenta-atras")?.textContent).toBe("3");
  });

  it("sin cuenta atrás en marcha no se enseña ninguna", () => {
    const { container } = pintar({ cuenta_atras_restante_s: 0 });
    expect(screen.getByRole("button", { name: "Pausar" })).toBeDefined();
    expect(container.querySelector(".cuenta-atras")).toBeNull();
  });
});

describe("pulsar un compás", () => {
  it("dentro del tramo salta directamente, sin tocar el plan", () => {
    const { alCambiarPlan, alSaltar } = pintar({ primer_compas: 3, ultimo_compas: 6 });
    fireEvent.click(compas(5));
    expect(alSaltar).toHaveBeenCalledWith(5);
    expect(alCambiarPlan).not.toHaveBeenCalled();
  });

  it("los extremos del tramo también son de dentro", () => {
    const { alCambiarPlan, alSaltar } = pintar({ primer_compas: 3, ultimo_compas: 6 });
    fireEvent.click(compas(3));
    fireEvent.click(compas(6));
    expect(alSaltar.mock.calls).toEqual([[3], [6]]);
    expect(alCambiarPlan).not.toHaveBeenCalled();
  });

  // Una prueba por borde de fuera: el servidor rechaza con 400 un salto fuera del
  // tramo, así que antes de saltar el rango tiene que incluir el compás.
  it("fuera, por delante: mueve la ventana (misma longitud) y DESPUÉS salta", async () => {
    const orden: string[] = [];
    const { alCambiarPlan, alSaltar } = pintar(
      { primer_compas: 3, ultimo_compas: 4, en_bucle: true },
      [],
      Promise.resolve(true),
    );
    alCambiarPlan.mockImplementation(() => {
      orden.push("plan");
      return Promise.resolve(true);
    });
    alSaltar.mockImplementation(() => orden.push("salto"));
    fireEvent.click(compas(9));
    await vi.waitFor(() => expect(alSaltar).toHaveBeenCalledWith(9));
    expect(alCambiarPlan).toHaveBeenCalledWith({ primer_compas: 9, ultimo_compas: 10 });
    expect(orden).toEqual(["plan", "salto"]);
  });

  it("fuera, por detrás: el compás pedido pasa a ser el primero de la ventana", async () => {
    const { alCambiarPlan, alSaltar } = pintar(
      { primer_compas: 8, ultimo_compas: 10 },
      [],
      Promise.resolve(true),
    );
    fireEvent.click(compas(2));
    await vi.waitFor(() => expect(alSaltar).toHaveBeenCalledWith(2));
    expect(alCambiarPlan).toHaveBeenCalledWith({ primer_compas: 2, ultimo_compas: 4 });
  });

  it("junto al final de la pieza la ventana se corre hacia atrás y sigue conteniendo el compás", async () => {
    const { alCambiarPlan, alSaltar } = pintar(
      { primer_compas: 2, ultimo_compas: 4 },
      [],
      Promise.resolve(true),
    );
    fireEvent.click(compas(12));
    await vi.waitFor(() => expect(alSaltar).toHaveBeenCalledWith(12));
    expect(alCambiarPlan).toHaveBeenCalledWith({ primer_compas: 10, ultimo_compas: 12 });
  });

  it("si el servidor rechaza el plan, no salta", async () => {
    const { alCambiarPlan, alSaltar } = pintar(
      { primer_compas: 3, ultimo_compas: 4 },
      [],
      Promise.resolve(false),
    );
    fireEvent.click(compas(9));
    await vi.waitFor(() => expect(alCambiarPlan).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    expect(alSaltar).not.toHaveBeenCalled();
  });

  it("arrastrar sobre la rejilla arma el bucle con ese rango", () => {
    const { alCambiarPlan } = pintar({ factor_tempo: 0.9 });
    fireEvent.pointerDown(compas(2));
    fireEvent.pointerEnter(compas(4));
    fireEvent.pointerUp(compas(4));
    expect(alCambiarPlan).toHaveBeenCalledWith({ primer_compas: 2, ultimo_compas: 4, en_bucle: true });
  });

  it("la rejilla se dibuja desde el estado: el rango del bucle y el compás en curso", () => {
    pintar({ primer_compas: 3, ultimo_compas: 4, compas_en_curso: 4 });
    expect(compas(3).classList.contains("en-el-bucle")).toBe(true);
    expect(compas(5).classList.contains("en-el-bucle")).toBe(false);
    expect(compas(2).classList.contains("en-el-bucle")).toBe(false);
    expect(compas(4).getAttribute("aria-current")).toBe("true");
  });

  it("la rejilla avisa del compás variable que dice el estado", () => {
    const { container } = pintar({ compas_variable: true });
    expect(container.querySelector(".aviso-compases")?.textContent).toContain("cambia de compás");
  });

  it("sin compás variable la rejilla no avisa de nada", () => {
    const { container } = pintar({ compas_variable: false });
    expect(compas(1)).toBeDefined();
    expect(container.querySelector(".aviso-compases")).toBeNull();
  });
});
