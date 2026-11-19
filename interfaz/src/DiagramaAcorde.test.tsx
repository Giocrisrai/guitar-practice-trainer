import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DiagramaAcorde } from "./DiagramaAcorde";
import { colorDeCuerda } from "./geometriaCarril";
import type { PerfilAfinacion } from "./tipos";
import type { AcordeEjercicio } from "./tiposEjercicio";

const GUITARRA: PerfilAfinacion = {
  clave: "guitarra_estandar",
  nombre: "Guitarra estándar",
  trastes: 22,
  cuerdas: [
    { numero: 6, nota: "E2", frecuencia: 82.41 },
    { numero: 5, nota: "A2", frecuencia: 110.0 },
    { numero: 4, nota: "D3", frecuencia: 146.83 },
    { numero: 3, nota: "G3", frecuencia: 196.0 },
    { numero: 2, nota: "B3", frecuencia: 246.94 },
    { numero: 1, nota: "E4", frecuencia: 329.63 },
  ],
};

/** Do mayor abierto: x32010, de grave a aguda. La 6.ª no se toca. */
const DO: AcordeEjercicio = {
  nombre: "Do mayor",
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
};

function fila(cuerda: number): HTMLElement {
  const nodo = document.querySelector(`.cuerda-acorde[data-cuerda="${cuerda}"]`);
  if (nodo === null) throw new Error(`no hay fila para la cuerda ${cuerda}`);
  return nodo as HTMLElement;
}

describe("DiagramaAcorde", () => {
  it("dibuja una fila por cuerda del instrumento", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} />);
    expect(document.querySelectorAll(".cuerda-acorde")).toHaveLength(6);
  });

  it("nombra el acorde", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} />);
    expect(screen.getByText("Do mayor")).toBeTruthy();
  });

  it("marca la cuerda que no se toca, que no es lo mismo que al aire", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} />);
    // La 6.ª no entra en el acorde: lleva la cruz y ningún traste.
    expect(fila(6).className).toContain("no-se-toca");
    expect(fila(6).querySelector(".marca-muda")).not.toBeNull();
    expect(fila(6).querySelector(".marca-traste")).toBeNull();
    // La 3.ª va al aire: SÍ suena, y lleva su marca con el traste 0.
    expect(fila(3).className).not.toContain("no-se-toca");
    expect(fila(3).querySelector(".marca-traste")?.textContent).toBe("0");
  });

  it("pinta cada cuerda con el color del carril", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} />);
    const marca = fila(5).querySelector(".marca-traste") as HTMLElement;
    expect(marca.style.background).not.toBe("");
    // Mismo idioma visual que el carril: el color va por numero de cuerda.
    expect(colorDeCuerda(5)).toBeTruthy();
  });

  it("senala exactamente la cuerda que no suena", () => {
    // Falta E4 (midi 64), que es la 1.ª cuerda al aire.
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} faltan={[64]} />);
    expect(fila(1).className).toContain("falta");
    expect(fila(1).querySelector(".marca-traste")?.className).toContain("apagada");
    expect(screen.getByText("no suena")).toBeTruthy();
  });

  it("no marca ninguna cuerda cuando el acorde suena entero", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} faltan={[]} />);
    expect(document.querySelectorAll(".cuerda-acorde.falta")).toHaveLength(0);
    expect(screen.queryByText("no suena")).toBeNull();
  });

  it("marca las dos cuerdas cuando faltan dos", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} faltan={[60, 64]} />);
    expect(document.querySelectorAll(".cuerda-acorde.falta")).toHaveLength(2);
  });

  it("no revela los trastes mientras no toca ayudar", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} revelado={false} />);
    expect(fila(5).querySelector(".marca-traste")?.textContent).toBe("");
    expect(screen.getByText(/aparecen si te atascas/)).toBeTruthy();
  });

  it("revela los trastes cuando toca ayudar", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} revelado />);
    expect(fila(5).querySelector(".marca-traste")?.textContent).toBe("3");
    expect(screen.queryByText(/aparecen si te atascas/)).toBeNull();
  });

  it("lista las notas del acorde", () => {
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} />);
    expect(screen.getByText("C3 · E3 · G3 · C4 · E4")).toBeTruthy();
  });

  it("un MIDI que falta y no esta en el acorde no marca nada", () => {
    // Robustez: el servidor no deberia mandar esto, pero marcar una cuerda al
    // azar seria peor que ignorarlo.
    render(<DiagramaAcorde acorde={DO} perfil={GUITARRA} faltan={[99]} />);
    expect(document.querySelectorAll(".cuerda-acorde.falta")).toHaveLength(0);
  });
});
