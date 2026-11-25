import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SelectorDeAcordes } from "./SelectorDeAcordes";
import type { AcordeDelCatalogo } from "./tiposEjercicio";

/** Dos acordes del catálogo, tal y como los manda `/api/ejercicios/acordes`. */
const CATALOGO: AcordeDelCatalogo[] = [
  {
    clave: "do",
    nombre: "Do mayor",
    // x32010: la sexta no se toca, y eso tiene que verse como un hueco.
    posiciones: [
      { cuerda: 5, traste: 3 },
      { cuerda: 4, traste: 2 },
      { cuerda: 3, traste: 0 },
      { cuerda: 2, traste: 1 },
      { cuerda: 1, traste: 0 },
    ],
    midis: [48, 52, 55, 60, 64],
    nombres: ["C3", "E3", "G3", "C4", "E4"],
    pulsos: 4,
  },
  {
    clave: "sol",
    nombre: "Sol mayor",
    posiciones: [
      { cuerda: 6, traste: 3 },
      { cuerda: 5, traste: 2 },
      { cuerda: 4, traste: 0 },
      { cuerda: 3, traste: 0 },
      { cuerda: 2, traste: 0 },
      { cuerda: 1, traste: 3 },
    ],
    midis: [43, 47, 50, 55, 59, 67],
    nombres: ["G2", "B2", "D3", "G3", "B3", "G4"],
    pulsos: 4,
  },
];

function fetchDelCatalogo(datos: unknown = CATALOGO) {
  return vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(datos) } as Response));
}

describe("SelectorDeAcordes", () => {
  beforeEach(() => vi.stubGlobal("fetch", fetchDelCatalogo()));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("ofrece los acordes con el nombre que manda el servidor", async () => {
    render(<SelectorDeAcordes elegidas={[]} alCambiar={() => {}} />);
    expect(await screen.findByRole("button", { name: /Do mayor/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Sol mayor/ })).toBeTruthy();
  });

  it("no escribe ningún acorde: sin catálogo no pinta nada", () => {
    vi.stubGlobal("fetch", fetchDelCatalogo([]));
    const { container } = render(<SelectorDeAcordes elegidas={[]} alCambiar={() => {}} />);
    expect(container.querySelector(".selector-acordes")).toBeNull();
  });

  it("pulsar un acorde lo añade al FINAL, porque el orden es el ejercicio", async () => {
    const alCambiar = vi.fn();
    render(<SelectorDeAcordes elegidas={["sol"]} alCambiar={alCambiar} />);
    (await screen.findByRole("button", { name: /Do mayor/ })).click();
    expect(alCambiar).toHaveBeenCalledWith(["sol", "do"]);
  });

  it("volver a pulsarlo lo quita", async () => {
    const alCambiar = vi.fn();
    render(<SelectorDeAcordes elegidas={["sol", "do"]} alCambiar={alCambiar} />);
    const fichas = await screen.findAllByRole("button", { name: /Do mayor/ });
    // La ficha del catálogo, no el paso de la vuelta (que dice "Quitar").
    const ficha = fichas.find((b) => b.className.includes("ficha-acorde"));
    ficha!.click();
    expect(alCambiar).toHaveBeenCalledWith(["sol"]);
  });

  it("marca como pulsadas las que están puestas", async () => {
    render(<SelectorDeAcordes elegidas={["do"]} alCambiar={() => {}} />);
    await waitFor(() => expect(screen.getAllByRole("button").length).toBeGreaterThan(1));
    const fichas = screen.getAllByRole("button").filter((b) =>
      b.className.includes("ficha-acorde")
    );
    const puesta = fichas.find((b) => b.textContent?.includes("Do mayor"));
    const suelta = fichas.find((b) => b.textContent?.includes("Sol mayor"));
    expect(puesta!.getAttribute("aria-pressed")).toBe("true");
    expect(suelta!.getAttribute("aria-pressed")).toBe("false");
  });

  it("dibuja la vuelta en el orden elegido, no en el del catálogo", async () => {
    render(<SelectorDeAcordes elegidas={["sol", "do"]} alCambiar={() => {}} />);
    const vuelta = await screen.findByRole("list", { name: /vuelta/i });
    const pasos = [...vuelta.querySelectorAll(".nombre-paso")].map((n) => n.textContent);
    expect(pasos).toEqual(["Sol mayor", "Do mayor"]);
  });

  it("avisa de que con un acorde solo no hay cambio", async () => {
    render(<SelectorDeAcordes elegidas={["do"]} alCambiar={() => {}} />);
    expect(await screen.findByText(/al menos dos/i)).toBeTruthy();
  });

  it("con dos ya no avisa", async () => {
    render(<SelectorDeAcordes elegidas={["do", "sol"]} alCambiar={() => {}} />);
    await screen.findByRole("list", { name: /vuelta/i });
    expect(screen.queryByText(/al menos dos/i)).toBeNull();
  });

  it("sin elegir nada dice que manda el generador, sin nombrar acordes", async () => {
    render(<SelectorDeAcordes elegidas={[]} alCambiar={() => {}} />);
    const aviso = await screen.findByText(/el generador/i);
    expect(aviso.textContent).not.toMatch(/Do mayor|Sol mayor/);
  });

  it("la forma del acorde deja en hueco la cuerda que no se toca", async () => {
    const { container } = render(<SelectorDeAcordes elegidas={[]} alCambiar={() => {}} />);
    await screen.findByRole("button", { name: /Do mayor/ });
    const formas = container.querySelectorAll(".ficha-acorde .forma-acorde");
    // Seis huecos siempre: una cuerda que no suena ocupa su sitio, o la silueta
    // del acorde no se podría comparar de un vistazo con la de otro.
    expect(formas[0].querySelectorAll(".hueco-acorde")).toHaveLength(6);
    // El Do no toca la sexta, que es la primera por la izquierda.
    expect(formas[0].querySelectorAll(".hueco-acorde")[0].className).toContain("vacio");
    // El Sol las toca todas.
    expect(formas[1].querySelectorAll(".hueco-acorde.vacio")).toHaveLength(0);
  });

  it("un catálogo que no llega no rompe la pantalla", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("sin red"))));
    const { container } = render(<SelectorDeAcordes elegidas={[]} alCambiar={() => {}} />);
    await waitFor(() => expect(container.querySelector(".selector-acordes")).toBeNull());
  });
});
