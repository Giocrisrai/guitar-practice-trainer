import { describe, expect, it } from "vitest";
import {
  alturaEnPentagrama,
  celdasDeTablatura,
  compasesDe,
  lineasAdicionales,
  lineaDeTablatura,
  llevaSostenido,
} from "./vistaEscrita";

const PIEZA = {
  nombre: "p", perfil: "guitarra_estandar", tempo: 60, compas: [4, 4] as [number, number],
  duracion_pulsos: 8,
  secciones: [], ritmo_aproximado: false, tempo_variable: false, compas_variable: false, casillas_de_repeticion: false,
  notas: [
    { midi: 40, nombre: "E2", cuerda: 6, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
    { midi: 45, nombre: "A2", cuerda: 5, traste: 0, inicio_pulsos: 1, duracion_pulsos: 1 },
    { midi: 52, nombre: "E3", cuerda: 4, traste: 2, inicio_pulsos: 4, duracion_pulsos: 2 },
  ],
};

describe("vista escrita", () => {
  it("reparte las notas en compases según el compás de la pieza", () => {
    const compases = compasesDe(PIEZA);
    expect(compases).toHaveLength(2);
    expect(compases[0].notas.map((n) => n.midi)).toEqual([40, 45]);
    expect(compases[1].notas.map((n) => n.midi)).toEqual([52]);
  });

  it("la tablatura pone cada traste en la línea de su cuerda", () => {
    const lineas = lineaDeTablatura(compasesDe(PIEZA)[0], 6);
    expect(lineas).toHaveLength(6);
    // La sexta cuerda es la línea de abajo, como se escribe la tablatura.
    expect(lineas[5]).toContain("0");
    expect(lineas[0]).not.toContain("2");
  });

  it("una nota más aguda va más arriba en el pentagrama", () => {
    expect(alturaEnPentagrama(52)).toBeLessThan(alturaEnPentagrama(40));
  });

  it("un compás vacío sigue siendo un compás", () => {
    const pieza = { ...PIEZA, notas: [PIEZA.notas[2]] };
    expect(compasesDe(pieza)).toHaveLength(2);
    expect(compasesDe(pieza)[0].notas).toEqual([]);
  });

  it("la cuerda 1 queda arriba y la 6 abajo, y el traste cae en su columna", () => {
    const compas = compasesDe({
      ...PIEZA,
      notas: [
        { midi: 64, nombre: "E4", cuerda: 1, traste: 12, inicio_pulsos: 1, duracion_pulsos: 1 },
        PIEZA.notas[0],
      ],
    })[0];
    const lineas = lineaDeTablatura(compas, 6);
    expect(lineas[0]).toContain("12");
    expect(lineas[5]).toContain("0");
    const celdas = celdasDeTablatura(compas, 6);
    expect(celdas.find((c) => c.linea === 0)?.columna).toBeGreaterThan(
      celdas.find((c) => c.linea === 5)?.columna ?? Infinity
    );
    // Todas las líneas miden lo mismo, o los compases no se alinean.
    expect(new Set(lineas.map((l) => l.length)).size).toBe(1);
  });

  it("un compás de 6/8 dura tres pulsos y reparte según eso", () => {
    const pieza = {
      ...PIEZA, compas: [6, 8] as [number, number], duracion_pulsos: 6,
      notas: [PIEZA.notas[0], { ...PIEZA.notas[1], inicio_pulsos: 3 }],
    };
    const compases = compasesDe(pieza);
    expect(compases).toHaveLength(2);
    expect(compases[1].notas.map((n) => n.midi)).toEqual([45]);
  });

  it("las notas conservan su posición en la pieza", () => {
    expect(compasesDe(PIEZA)[1].notas[0].indice).toBe(2);
  });

  it("alturas conocidas: mi4 escrito (guitarra mi3) en la línea de abajo, sol en la segunda", () => {
    expect(alturaEnPentagrama(52)).toBe(8); // E3 suena, E4 se escribe
    expect(alturaEnPentagrama(55)).toBe(6);
    expect(alturaEnPentagrama(40)).toBe(15);
  });

  it("las líneas adicionales llegan hasta la nota y solo fuera del pentagrama", () => {
    expect(lineasAdicionales(8)).toEqual([]);
    expect(lineasAdicionales(10)).toEqual([10]);
    expect(lineasAdicionales(15)).toEqual([10, 12, 14]);
    expect(lineasAdicionales(-2)).toEqual([-2]);
  });

  it("los sostenidos se reconocen", () => {
    expect(llevaSostenido(42)).toBe(true);
    expect(llevaSostenido(40)).toBe(false);
  });

  it("la tablatura de un compás exacto: guiones, barras y el traste en su casilla", () => {
    const lineas = lineaDeTablatura(compasesDe(PIEZA)[0], 6);
    const vacia = "|" + "-".repeat(48) + "|";
    expect(lineas[5]).toBe("|0" + "-".repeat(47) + "|"); // E2 en el pulso 0
    expect(lineas[4]).toBe("|---" + "-".repeat(9) + "0" + "-".repeat(35) + "|"); // A2 en el pulso 1
    expect(lineas[0]).toBe(vacia);
  });

  it("dos notas en la misma casilla de una cuerda: la línea sigue cuadrada y las celdas dicen lo escrito", () => {
    const compas = compasesDe({
      ...PIEZA,
      notas: [
        { midi: 40, nombre: "E2", cuerda: 6, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
        { midi: 41, nombre: "F2", cuerda: 6, traste: 1, inicio_pulsos: 0, duracion_pulsos: 1 },
      ],
    })[0];
    const lineas = lineaDeTablatura(compas, 6);
    expect(new Set(lineas.map((l) => l.length)).size).toBe(1);
    expect(lineas[5].startsWith("|1")).toBe(true);
    const celdas = celdasDeTablatura(compas, 6);
    expect(celdas).toHaveLength(1);
    expect(celdas[0].texto).toBe("1");
  });

  it("una escala ascendente sube de forma monótona en el pentagrama, con alteradas", () => {
    for (let midi = 40; midi < 88; midi += 1) {
      expect(alturaEnPentagrama(midi + 1)).toBeLessThanOrEqual(alturaEnPentagrama(midi));
    }
    // Do y do# comparten altura (el sostenido se dice con el símbolo); do y re no.
    expect(alturaEnPentagrama(61)).toBe(alturaEnPentagrama(60));
    expect(alturaEnPentagrama(62)).toBeLessThan(alturaEnPentagrama(60));
  });

  it("un compás de 3/4 dura tres pulsos", () => {
    const pieza = { ...PIEZA, compas: [3, 4] as [number, number], duracion_pulsos: 6 };
    expect(compasesDe(pieza)).toHaveLength(2);
    expect(compasesDe(pieza)[0].pulsos).toBe(3);
  });
});
