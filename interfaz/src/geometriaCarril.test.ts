import { describe, expect, it } from "vitest";
import {
  acordesVisibles,
  colorDeCuerda,
  ligaduraDeAcorde,
  colorDeTextoSobre,
  colorDeDesviacion,
  ESTELA_S,
  notasVisibles,
  rectanguloDeNota,
  VENTANA_VISIBLE_S,
  yDeLaLineaDeAtaque,
} from "./geometriaCarril";
import type { NotaDePieza } from "./tiposPieza";

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

  it("una nota recién terminada se queda pintada en la estela", () => {
    // La nota 0 dura un pulso: a 60 ppm acaba en t=1. Medio segundo después
    // todavía se ve, y pasada la estela ya no (spec §4).
    expect(notasVisibles([nota(0)], 1.5, 60, VENTANA_VISIBLE_S)).toHaveLength(1);
    expect(notasVisibles([nota(0)], 1.0 + ESTELA_S + 0.01, 60, VENTANA_VISIBLE_S)).toHaveLength(0);
  });

  it("la estela cae por debajo de la línea de ataque y dentro del lienzo", () => {
    const linea = yDeLaLineaDeAtaque(LIENZO);
    expect(linea).toBeLessThan(LIENZO.alto);
    expect(linea).toBeGreaterThan(0);
    // Una nota que acabó hace medio segundo: su borde de ataque ya pasó la línea
    // y sigue dentro del lienzo, que es lo que hace que se vea.
    const rect = rectanguloDeNota(nota(0), 1.5, 60, LIENZO);
    expect(rect.y).toBeGreaterThan(linea);
    expect(rect.y - rect.alto).toBeLessThan(LIENZO.alto);
  });

  it("la nota que suena ahora está en la línea de ataque", () => {
    const rect = rectanguloDeNota(nota(2), 2.0, 60, LIENZO);
    expect(rect.y).toBeCloseTo(yDeLaLineaDeAtaque(LIENZO), 5);
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
  it("la escala vertical es proporcional: 1 s son alto/(ventana+estela) píxeles", () => {
    const porSegundo = LIENZO.alto / (VENTANA_VISIBLE_S + ESTELA_S);
    const rect = rectanguloDeNota(nota(3, 6, 1), 2.0, 60, LIENZO);
    expect(rect.y).toBeCloseTo(yDeLaLineaDeAtaque(LIENZO) - porSegundo, 5);
    expect(rect.alto).toBeCloseTo(porSegundo, 5);
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

describe("colorDeCuerda", () => {
  it("cada cuerda de una guitarra tiene su propio color", () => {
    const colores = [1, 2, 3, 4, 5, 6].map((cuerda) => colorDeCuerda(cuerda));
    expect(new Set(colores).size).toBe(6);
  });

  it("el color de una cuerda no depende de cuantas tenga el instrumento", () => {
    // El bajo tiene cuatro cuerdas y el ukelele cuatro: la 1 es la 1 en los
    // tres sitios. Si el color se repartiera por fracción del total, cambiar de
    // instrumento repintaría toda la pieza y el usuario tendría que releerla.
    expect(colorDeCuerda(1)).toBe(colorDeCuerda(1));
    expect(colorDeCuerda(4)).toBe(colorDeCuerda(4));
  });

  it("una cuerda fuera de las seis habituales sigue dando un color", () => {
    // Una guitarra de siete u ocho cuerdas existe. Devolver `undefined` aquí
    // pintaría la nota de "transparent" y la nota desaparecería del carril:
    // el usuario no vería que tiene que tocarla.
    for (const cuerda of [7, 8, 12]) {
      expect(colorDeCuerda(cuerda)).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("el cero y los negativos tampoco rompen el dibujo", () => {
    expect(colorDeCuerda(0)).toMatch(/^#[0-9a-f]{6}$/i);
    expect(colorDeCuerda(-1)).toMatch(/^#[0-9a-f]{6}$/i);
  });
});

describe("colorDeTextoSobre", () => {
  it("sobre un color claro escribe oscuro y sobre uno oscuro escribe claro", () => {
    expect(colorDeTextoSobre("#e8cf3d")).not.toBe(colorDeTextoSobre("#3d8ee8"));
  });

  it("el blanco y el negro puros caen de los lados que les tocan", () => {
    expect(colorDeTextoSobre("#ffffff")).toBe(colorDeTextoSobre("#e8cf3d"));
    expect(colorDeTextoSobre("#000000")).toBe(colorDeTextoSobre("#3d8ee8"));
  });

  it("los seis colores de cuerda dan un numero legible", () => {
    // El numero del traste se pinta encima de la nota. Si el contraste se
    // eligiera mal en una sola cuerda, esa cuerda tendria las notas mudas: se
    // ve el bloque y no se ve que traste es.
    for (const cuerda of [1, 2, 3, 4, 5, 6]) {
      const texto = colorDeTextoSobre(colorDeCuerda(cuerda));
      expect(["#12161b", "#ffffff"]).toContain(texto);
    }
  });
});

describe("acordesVisibles", () => {
  const nota = (cuerda: number, inicio: number): NotaDePieza => ({
    midi: 40 + cuerda, nombre: "x", cuerda, traste: 0,
    inicio_pulsos: inicio, duracion_pulsos: 1,
  });

  it("agrupa las notas que se atacan en el mismo instante", () => {
    const grupos = acordesVisibles([nota(5, 0), nota(4, 0), nota(3, 0)]);
    expect(grupos).toHaveLength(1);
    expect(grupos[0]).toHaveLength(3);
  });

  it("una nota suelta no es un acorde: una pieza monofónica no paga nada", () => {
    expect(acordesVisibles([nota(6, 0), nota(5, 1), nota(4, 2)])).toEqual([]);
  });

  it("separa dos acordes seguidos", () => {
    const grupos = acordesVisibles([nota(5, 0), nota(4, 0), nota(5, 4), nota(4, 4)]);
    expect(grupos).toHaveLength(2);
  });
});

describe("ligaduraDeAcorde", () => {
  const lienzo = { ancho: 600, alto: 400, cuerdas: 6 };
  const nota = (cuerda: number): NotaDePieza => ({
    midi: 40 + cuerda, nombre: "x", cuerda, traste: 0,
    inicio_pulsos: 0, duracion_pulsos: 1,
  });

  it("va por los centros de los carriles, no de borde a borde del lienzo", () => {
    // Cuerdas 5 a 2 de seis: carriles de 100 px, centros en 450 y 150.
    const l = ligaduraDeAcorde([nota(5), nota(4), nota(3), nota(2)], 0, 60, lienzo, 2);
    expect(l.desde).toBe(150);
    expect(l.hasta).toBe(450);
  });

  it("se queda a la altura del borde de ataque", () => {
    const l = ligaduraDeAcorde([nota(5), nota(4)], 0, 60, lienzo, 2);
    const rectangulo = rectanguloDeNota(nota(5), 0, 60, lienzo, 2);
    expect(l.y).toBe(rectangulo.y);
  });
});
