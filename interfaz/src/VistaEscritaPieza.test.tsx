import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { colorDeDesviacion } from "./geometriaCarril";
import type { EstadoCarril, NotaTocada, Pieza } from "./tiposPieza";
import { VistaEscrita } from "./VistaEscritaPieza";

const PIEZA: Pieza = {
  nombre: "p", perfil: "guitarra_estandar", tempo: 60, compas: [4, 4],
  duracion_pulsos: 8,
  secciones: [], ritmo_aproximado: false, tempo_variable: false, compas_variable: false, casillas_de_repeticion: false,
  notas: [
    { midi: 40, nombre: "E2", cuerda: 6, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
    { midi: 45, nombre: "A2", cuerda: 5, traste: 0, inicio_pulsos: 1, duracion_pulsos: 1 },
    { midi: 50, nombre: "D3", cuerda: 4, traste: 0, inicio_pulsos: 2, duracion_pulsos: 1 },
    { midi: 52, nombre: "E3", cuerda: 4, traste: 2, inicio_pulsos: 4, duracion_pulsos: 2 },
  ],
};

/**
 * Una pulsación tal y como la publica el núcleo, con sus dos veredictos ya
 * decididos: `acertada` compara la altura con la nota escrita de la pieza y
 * `afinada` aplica a los cents la regla de `nucleo.musica.esta_afinada`
 * (`abs(cents) < 5`, estricto). Se calculan aquí porque esto FINGE al servidor;
 * la interfaz no los calcula en ningún sitio, los consume.
 */
function tocada(indice: number, midi: number, nombre: string, cents: number | null): NotaTocada {
  return {
    indice,
    midi,
    nombre,
    cents,
    desfase_s: 0,
    clasificacion: "a_tiempo",
    acertada: midi === PIEZA.notas[indice].midi,
    afinada: cents === null ? null : Math.abs(cents) < 5,
  };
}

function estado(parcial: Partial<EstadoCarril>): EstadoCarril {
  return {
    arranque: 1, instante_s: 0, indice_actual: 0, total: 4, completado: false,
    tocadas: [], pausado: false, ...parcial,
  };
}

const ETIQUETAS = ["E4", "B3", "G3", "D3", "A2", "E2"];

describe("VistaEscrita", () => {
  it("rotula las cuerdas y pone la sexta abajo", () => {
    render(<VistaEscrita pieza={PIEZA} estado={null} cuerdas={6} etiquetas={ETIQUETAS} />);
    const lineas = screen.getByLabelText("Tablatura del compás 1").querySelectorAll("div");
    expect(lineas).toHaveLength(6);
    expect(lineas[0].textContent?.startsWith("E4")).toBe(true);
    expect(lineas[5].textContent?.startsWith("E2")).toBe(true);
    expect(new Set([...lineas].map((l) => l.textContent?.length)).size).toBe(1);
  });

  it("resalta la nota en curso que dice el núcleo, en tablatura y pentagrama", () => {
    const { container } = render(
      <VistaEscrita pieza={PIEZA} estado={estado({ indice_actual: 1 })} cuerdas={6} />
    );
    expect(screen.getAllByTestId("nota-actual")).toHaveLength(1);
    const enTablatura = container.querySelectorAll(".tablatura .traste-actual");
    expect(enTablatura).toHaveLength(1);
    // La nota 1 es la A2: cuerda 5, la segunda línea de abajo.
    const lineas = screen.getByLabelText("Tablatura del compás 1").querySelectorAll("div");
    expect(within(lineas[4] as HTMLElement).getByText("0").className).toBe("traste-actual");
  });

  it("con la pieza terminada ya no hay nota en curso", () => {
    render(<VistaEscrita pieza={PIEZA} estado={estado({ completado: true, indice_actual: 3 })} cuerdas={6} />);
    expect(screen.queryByTestId("nota-actual")).toBeNull();
  });

  it("cents nulo no se pinta como afinada ni se escribe como cero", () => {
    const { container } = render(
      <VistaEscrita
        pieza={PIEZA}
        estado={estado({ tocadas: [tocada(0, 40, "E2", null), tocada(1, 45, "A2", 0)] })}
        cuerdas={6}
      />
    );
    const sinSaber = { cents: null, afinada: null };
    const afinada = { cents: 0, afinada: true };
    expect(colorDeDesviacion(sinSaber)).not.toBe(colorDeDesviacion(afinada));
    const cabezas = container.querySelectorAll("ellipse");
    // Notas con cabeza propia: las dos tocadas, en orden, más la tercera pendiente.
    expect(cabezas[0].getAttribute("stroke")).toBe(colorDeDesviacion(sinSaber));
    expect(cabezas[1].getAttribute("stroke")).toBe(colorDeDesviacion(afinada));
    expect(screen.getByText("?")).toBeTruthy();
    expect(screen.getByText("0 c")).toBeTruthy();
  });

  it("enseña qué tocó el alumno cuando no era la nota pedida", () => {
    render(
      <VistaEscrita
        pieza={PIEZA}
        estado={estado({ tocadas: [tocada(1, 46, "A#2", 12)] })}
        cuerdas={6}
      />
    );
    expect(screen.getByTestId("nota-tocada-distinta")).toBeTruthy();
    expect(screen.getByText("Pedida A2, tocaste A#2 (+12 c)")).toBeTruthy();
  });

  it("no marca como distinta una nota acertada", () => {
    render(
      <VistaEscrita pieza={PIEZA} estado={estado({ tocadas: [tocada(1, 45, "A2", 3)] })} cuerdas={6} />
    );
    expect(screen.queryByTestId("nota-tocada-distinta")).toBeNull();
  });

  /**
   * Quién decide si se acertó: el núcleo. La interfaz comparaba otra vez los
   * MIDIs, que es `!tocada.acertada` recalculado, y el núcleo ya lo publica.
   *
   * Se prueba con un estado que la interfaz no puede fabricar sola: el MIDI
   * tocado COINCIDE con el escrito y el núcleo dice `acertada: false`. Es
   * imposible en el servidor de verdad, y justamente por eso distingue quién
   * manda: recomparando MIDIs la fila no sale; consumiendo el booleano, sí.
   */
  it("el veredicto de acierto lo manda el núcleo, no una comparación propia", () => {
    const discrepante = { ...tocada(1, 45, "A2", 0), acertada: false };
    render(
      <VistaEscrita pieza={PIEZA} estado={estado({ tocadas: [discrepante] })} cuerdas={6} />
    );
    expect(screen.getByTestId("nota-tocada-distinta")).toBeTruthy();
    expect(screen.getByText("Pedida A2, tocaste A2 (0 c)")).toBeTruthy();
  });

  it("dos notas en la misma casilla no descuadran la línea", () => {
    const pieza: Pieza = {
      ...PIEZA,
      notas: [
        { midi: 40, nombre: "E2", cuerda: 6, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
        { midi: 41, nombre: "F2", cuerda: 6, traste: 1, inicio_pulsos: 0, duracion_pulsos: 1 },
      ],
    };
    render(<VistaEscrita pieza={pieza} estado={null} cuerdas={6} />);
    const lineas = screen.getByLabelText("Tablatura del compás 1").querySelectorAll("div");
    expect(new Set([...lineas].map((l) => l.textContent?.length)).size).toBe(1);
  });
});
