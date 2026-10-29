import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { textoDelDesfase } from "./calculosInforme";
import { InformePasada } from "./InformePasada";
import type { CompasDelInforme, Historial, Informe } from "./tiposEstudio";

function compas(numero: number, extra: Partial<CompasDelInforme> = {}): CompasDelInforme {
  return {
    numero, notas_escritas: 4, notas_medibles: 4, acertadas: 4, a_tiempo: 4, limpias: 4,
    pronto: 0, tarde: 0, desfase_medio_s: 0.01, tiene_acordes: false, ...extra,
  };
}

function pintar(informe: Partial<Informe> = {}, historial: Partial<Historial> = {}) {
  const alMachacar = vi.fn();
  render(
    <InformePasada
      informe={{
        compases: [compas(1)], ritmo_aproximado: false, compas_variable: false,
        factor_tempo: 1, repeticiones: 1, ...informe,
      }}
      historial={{ pasadas: 1, peores_compases: [], ...historial }}
      alMachacar={alMachacar}
    />,
  );
  return { alMachacar };
}

/** La fila de un compás, o falla: así una consulta vacía no pasa por buena. */
function fila(numero: number): HTMLElement {
  const encontrada = document.querySelector<HTMLElement>(`tr[data-compas="${numero}"]`);
  expect(encontrada).not.toBeNull();
  return encontrada!;
}

function celda(numero: number, clase: "celda-limpias" | "celda-desfase"): string {
  const elemento = fila(numero).querySelector(`.${clase}`);
  expect(elemento).not.toBeNull();
  return elemento!.textContent ?? "";
}

const FRASE_ACORDES = "solo se puede medir una nota de cada acorde";

afterEach(cleanup);

describe("el desfase en palabras", () => {
  it("tarde, pronto, a tiempo y nada", () => {
    expect(textoDelDesfase(0.04)).toBe("40 ms tarde");
    expect(textoDelDesfase(-0.04)).toBe("40 ms pronto");
    expect(textoDelDesfase(0)).toBe("a tiempo");
    expect(textoDelDesfase(0.0004)).toBe("a tiempo");
    expect(textoDelDesfase(null)).toBe("");
  });
});

describe("el informe de la pasada", () => {
  it("enseña el desfase medio con signo y en milisegundos", () => {
    // "40 ms tarde" es un diagnostico; "fallas el 19" no lo es.
    pintar({ compases: [compas(19, { desfase_medio_s: 0.04 })] });
    expect(celda(19, "celda-desfase")).toBe("40 ms tarde");
  });

  it("adelantarse se dice como adelantarse, no como un número negativo", () => {
    pintar({ compases: [compas(19, { desfase_medio_s: -0.04 })] });
    expect(celda(19, "celda-desfase")).toBe("40 ms pronto");
    expect(fila(19).textContent).not.toContain("-");
  });

  it("un compás que nadie tocó no inventa un desfase", () => {
    pintar({
      compases: [
        compas(3, { desfase_medio_s: 0.02 }),
        compas(4, { acertadas: 0, a_tiempo: 0, limpias: 0, desfase_medio_s: null }),
      ],
    });
    // La positiva: el compás 3 sí tiene desfase, así que la tabla no está vacía.
    expect(celda(3, "celda-desfase")).toBe("20 ms tarde");
    expect(celda(4, "celda-desfase")).toBe("");
    expect(celda(4, "celda-limpias")).toBe("0 de 4");
  });

  it("enseña las notas limpias de cada compás, no las acertadas", () => {
    // 4 acertadas pero solo 2 limpias: dos salieron fuera de tiempo.
    pintar({ compases: [compas(5, { acertadas: 4, a_tiempo: 2, limpias: 2 })] });
    expect(celda(5, "celda-limpias")).toBe("2 de 4");
  });

  it("explica los compases con acordes en vez de contarlos como fallados", () => {
    pintar({
      compases: [
        compas(2),
        compas(7, { notas_escritas: 4, notas_medibles: 1, acertadas: 0, limpias: 0, tiene_acordes: true }),
      ],
    });
    expect(celda(7, "celda-limpias")).toBe("con acordes");
    // La explicación sale una sola vez y la dice el texto, no la tabla.
    const avisos = document.querySelectorAll(".aviso-acordes");
    expect(avisos.length).toBe(1);
    expect(avisos[0].textContent).toContain(FRASE_ACORDES);
  });

  it("sin acordes no hay explicación de acordes", () => {
    pintar({ compases: [compas(1)] });
    expect(celda(1, "celda-limpias")).toBe("4 de 4");
    expect(document.querySelectorAll(".aviso-acordes").length).toBe(0);
  });

  it("una pieza entera de acordes no deja el informe vacío sin explicación", () => {
    // El caso del .gp5 normal: si no se dice nada, el usuario ve una tabla a
    // ceros y cree que lo hizo todo mal.
    pintar({
      compases: [
        compas(1, { notas_medibles: 1, acertadas: 0, limpias: 0, tiene_acordes: true }),
        compas(2, { notas_medibles: 1, acertadas: 0, limpias: 0, tiene_acordes: true }),
      ],
    });
    expect(document.querySelectorAll("tbody tr").length).toBe(2);
    expect(document.querySelector(".aviso-acordes")!.textContent).toContain(FRASE_ACORDES);
    // Y no inventa un 0 % que no se midió.
    expect(document.body.textContent).not.toContain("%");
  });

  it("el resumen deja fuera los compases con acordes", () => {
    // 4 de 4 limpias en el compás 1; el 2 tiene acordes y 0 limpias: no cuenta.
    pintar({
      compases: [
        compas(1),
        compas(2, { notas_medibles: 1, acertadas: 0, limpias: 0, tiene_acordes: true }),
      ],
    });
    expect(document.querySelector(".resumen-informe")!.textContent).toContain("4 de 4 (100 %)");
  });

  it("el resumen divide por las repeticiones: nunca pasa del cien por cien", () => {
    // 3 vueltas del bucle: los contadores suman 12 limpias de 4 * 3 medibles.
    pintar({ compases: [compas(1, { limpias: 6 })], repeticiones: 3 });
    expect(celda(1, "celda-limpias")).toBe("6 de 12");
    expect(document.querySelector(".resumen-informe")!.textContent).toContain("6 de 12 (50 %)");
  });

  it("avisa arriba de que el ritmo es inventado, y solo si lo es", () => {
    pintar({ ritmo_aproximado: true });
    const avisos = [...document.querySelectorAll(".aviso-informe")].map((a) => a.textContent);
    expect(avisos.length).toBe(1);
    expect(avisos[0]).toContain("El ritmo de esta pieza se dedujo");
    cleanup();
    pintar({ ritmo_aproximado: false });
    expect(document.querySelectorAll(".aviso-informe").length).toBe(0);
    expect(document.querySelectorAll("tbody tr").length).toBe(1);
  });

  it("avisa del compás variable, y solo si lo es", () => {
    pintar({ compas_variable: true });
    const avisos = [...document.querySelectorAll(".aviso-informe")].map((a) => a.textContent);
    expect(avisos.length).toBe(1);
    expect(avisos[0]).toContain("cambia de compás");
    cleanup();
    pintar({ compas_variable: false });
    expect(document.querySelectorAll(".aviso-informe").length).toBe(0);
    expect(document.querySelectorAll("tbody tr").length).toBe(1);
  });

  it("ofrece machacar los peores compases con sus cifras", () => {
    const { alMachacar } = pintar({}, {
      pasadas: 5,
      peores_compases: [{ compas: 19, falladas: 4, contadas: 5 }],
    });
    const boton = screen.getByRole("button", { name: "Machacar el compás 19" });
    expect(document.querySelector(".cifras-peor")!.textContent).toContain("4 de 5 pasadas");
    fireEvent.click(boton);
    expect(alMachacar).toHaveBeenCalledTimes(1);
    expect(alMachacar).toHaveBeenCalledWith(19);
  });

  it("cada peor compás tiene su botón, y el botón machaca el suyo", () => {
    const { alMachacar } = pintar({}, {
      pasadas: 4,
      peores_compases: [
        { compas: 19, falladas: 3, contadas: 4 },
        { compas: 7, falladas: 1, contadas: 1 },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "Machacar el compás 7" }));
    expect(alMachacar).toHaveBeenCalledWith(7);
    expect(screen.getAllByRole("button").length).toBe(2);
    expect(document.body.textContent).toContain("1 de 1 pasada");
  });

  it("sin peores compases no ofrece machacar nada", () => {
    pintar({}, { pasadas: 3, peores_compases: [] });
    // La positiva: el historial sí se pinta, así que el componente no está vacío.
    expect(document.body.textContent).toContain("3 pasadas en esta pieza");
    expect(screen.queryAllByRole("button").length).toBe(0);
  });
});
