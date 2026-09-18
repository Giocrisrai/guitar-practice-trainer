// interfaz/src/presentacion.test.ts
import { describe, expect, it } from "vitest";

import { estadoAfinacion, fraccionNivel, posicionAguja } from "./presentacion";

describe("posicionAguja", () => {
  it("centra la aguja cuando la nota está exacta", () => {
    expect(posicionAguja(0)).toBe(0);
  });

  it("va a los extremos en los límites del rango", () => {
    expect(posicionAguja(50)).toBeCloseTo(1);
    expect(posicionAguja(-50)).toBeCloseTo(-1);
  });

  it("se satura en vez de salirse de la pantalla", () => {
    expect(posicionAguja(300)).toBe(1);
    expect(posicionAguja(-300)).toBe(-1);
  });

  it("es proporcional dentro del rango", () => {
    expect(posicionAguja(25)).toBeCloseTo(0.5);
  });
});

describe("estadoAfinacion", () => {
  it("usa el veredicto del servidor, no recalcula la tolerancia", () => {
    expect(estadoAfinacion("nota", 0, true)).toBe("afinada");
    expect(estadoAfinacion("nota", 4.9, true)).toBe("afinada");
    // Aunque la desviación sea diminuta, si el núcleo dice que no, no.
    expect(estadoAfinacion("nota", -0.1, false)).toBe("grave");
  });

  it("distingue grave de aguda", () => {
    expect(estadoAfinacion("nota", -20, false)).toBe("grave");
    expect(estadoAfinacion("nota", 20, false)).toBe("aguda");
  });

  it("sin nota no dice nada", () => {
    expect(estadoAfinacion(null, null, false)).toBe("sin_nota");
  });

  it("en silencio no dice desafinada aunque afinada llegue en false", () => {
    // El servidor envía afinada: false en silencio; ahí no significa "desafinada".
    expect(estadoAfinacion("silencio", null, false)).toBe("sin_nota");
    expect(estadoAfinacion("silencio", -30, false)).toBe("sin_nota");
  });
});

describe("fraccionNivel", () => {
  it("el silencio da cero", () => {
    expect(fraccionNivel(-120)).toBe(0);
  });

  it("una señal fuerte llena la barra", () => {
    expect(fraccionNivel(-5)).toBe(1);
  });

  it("el nivel medido tocando queda a media barra", () => {
    // -45 dBFS fue el nivel medio medido en el equipo real
    const fraccion = fraccionNivel(-45);
    expect(fraccion).toBeGreaterThan(0.4);
    expect(fraccion).toBeLessThan(0.6);
  });
});
