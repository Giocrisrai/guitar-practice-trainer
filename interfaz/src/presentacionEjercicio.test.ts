import { describe, expect, it } from "vitest";

import { calificacion, fraccionProgreso, mensajeDeFallo } from "./presentacionEjercicio";

describe("fraccionProgreso", () => {
  it("al empezar el progreso es cero", () => {
    expect(fraccionProgreso(0, 8)).toBe(0);
  });

  it("al terminar el progreso es uno", () => {
    expect(fraccionProgreso(8, 8)).toBe(1);
  });

  it("a mitad de camino es la mitad", () => {
    expect(fraccionProgreso(4, 8)).toBeCloseTo(0.5);
  });

  it("un ejercicio sin notas no divide por cero", () => {
    expect(fraccionProgreso(0, 0)).toBe(0);
  });

  it("nunca se sale de cero a uno", () => {
    expect(fraccionProgreso(12, 8)).toBe(1);
    expect(fraccionProgreso(-3, 8)).toBe(0);
  });
});

describe("mensajeDeFallo", () => {
  it("dice que esperaba y que sono", () => {
    expect(mensajeDeFallo("E2", "A2")).toContain("E2");
    expect(mensajeDeFallo("E2", "A2")).toContain("A2");
  });

  it("sin fallo no hay mensaje", () => {
    expect(mensajeDeFallo("E2", null)).toBeNull();
  });

  it("sin nota esperada tampoco", () => {
    expect(mensajeDeFallo(null, "A2")).toBeNull();
  });
});

describe("calificacion", () => {
  it("todo a la primera se reconoce", () => {
    expect(calificacion(8, 8).toLowerCase()).toContain("perfecto");
  });

  it("un ejercicio sin notas no divide por cero", () => {
    expect(calificacion(0, 0)).toBeTruthy();
  });

  it("pocos aciertos dan un mensaje distinto que muchos", () => {
    expect(calificacion(2, 10)).not.toBe(calificacion(9, 10));
  });
});
