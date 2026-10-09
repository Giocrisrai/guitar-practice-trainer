import { describe, expect, it } from "vitest";
import {
  colorDeDesviacion,
  notasVisibles,
  rectanguloDeNota,
  VENTANA_VISIBLE_S,
} from "./geometriaCarril";

const LIENZO = { ancho: 600, alto: 400, cuerdas: 6 };

function nota(inicio: number, cuerda = 6, duracion = 1) {
  return { midi: 40, nombre: "E2", cuerda, traste: 0,
           inicio_pulsos: inicio, duracion_pulsos: duracion };
}

describe("geometría del carril", () => {
  it("solo entran las notas de la ventana visible", () => {
    const notas = [nota(0), nota(2), nota(10)];
    const visibles = notasVisibles(notas, 0, 60, VENTANA_VISIBLE_S);
    expect(visibles.map((n) => n.inicio_pulsos)).toEqual([0, 2]);
  });

  it("una nota que ya pasó deja de estar visible", () => {
    const visibles = notasVisibles([nota(0)], 3.0, 60, VENTANA_VISIBLE_S);
    expect(visibles).toHaveLength(0);
  });

  it("la nota que suena ahora está en la línea de ataque", () => {
    const rect = rectanguloDeNota(nota(2), 2.0, 60, LIENZO);
    expect(rect.y).toBeCloseTo(LIENZO.alto, 0);
  });

  it("una nota futura está más arriba cuanto más lejos", () => {
    const cerca = rectanguloDeNota(nota(2), 1.5, 60, LIENZO);
    const lejos = rectanguloDeNota(nota(4), 1.5, 60, LIENZO);
    expect(lejos.y).toBeLessThan(cerca.y);
  });

  it("cada cuerda tiene su carril y la sexta va a un lado fijo", () => {
    const sexta = rectanguloDeNota(nota(0, 6), 0, 60, LIENZO);
    const primera = rectanguloDeNota(nota(0, 1), 0, 60, LIENZO);
    expect(sexta.x).not.toBeCloseTo(primera.x, 0);
    expect(sexta.x).toBeGreaterThanOrEqual(0);
    expect(primera.x + primera.ancho).toBeLessThanOrEqual(LIENZO.ancho);
  });

  it("el alto de la nota es su duración", () => {
    const corta = rectanguloDeNota(nota(2, 6, 1), 2.0, 60, LIENZO);
    const larga = rectanguloDeNota(nota(2, 6, 2), 2.0, 60, LIENZO);
    expect(larga.alto).toBeGreaterThan(corta.alto);
  });

  it("al doble de tempo, la misma nota llega en la mitad de tiempo", () => {
    const a60 = rectanguloDeNota(nota(2), 0, 60, LIENZO);
    const a120 = rectanguloDeNota(nota(2), 0, 120, LIENZO);
    expect(a120.y).toBeGreaterThan(a60.y);
  });

  it("el color distingue afinada, alta y baja, y null no es cero", () => {
    // cents null significa NO tocada; cero significa perfectamente afinada.
    expect(colorDeDesviacion({ cents: 0, afinada: true })).not.toBe(
      colorDeDesviacion({ cents: 30, afinada: false })
    );
    expect(colorDeDesviacion({ cents: 30, afinada: false })).not.toBe(
      colorDeDesviacion({ cents: -30, afinada: false })
    );
    expect(colorDeDesviacion({ cents: null, afinada: null })).not.toBe(
      colorDeDesviacion({ cents: 0, afinada: true })
    );
  });

  // Refuerzos (no son del brief).
  it("la escala vertical es proporcional: 1 s son alto/ventana píxeles", () => {
    const rect = rectanguloDeNota(nota(3, 6, 1), 2.0, 60, LIENZO);
    expect(rect.y).toBeCloseTo(LIENZO.alto - 100, 5);
    expect(rect.alto).toBeCloseTo(100, 5);
  });

  it("con otra ventana, una nota visible sigue cayendo dentro del lienzo", () => {
    const ventana = 2.0;
    const n = nota(1.9);
    expect(notasVisibles([n], 0, 60, ventana)).toHaveLength(1);
    const rect = rectanguloDeNota(n, 0, 60, LIENZO, ventana);
    expect(rect.y).toBeGreaterThan(0);
  });

  it("el veredicto lo manda el núcleo, no el número de cents", () => {
    // Este módulo ya no sabe donde esta el umbral de la afinacion: lo trae
    // `NotaTocada.afinada`. Con los mismos cents y veredictos contrarios, los
    // colores son contrarios; con cents distintos y el mismo veredicto, iguales.
    expect(colorDeDesviacion({ cents: 4, afinada: false })).not.toBe(
      colorDeDesviacion({ cents: 4, afinada: true })
    );
    expect(colorDeDesviacion({ cents: 4, afinada: true })).toBe(
      colorDeDesviacion({ cents: 40, afinada: true })
    );
  });

  it("una desviación sin veredicto se pinta como desconocida", () => {
    expect(colorDeDesviacion({ cents: 12, afinada: null })).toBe(
      colorDeDesviacion({ cents: null, afinada: null })
    );
  });
});
