import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RejillaCompases } from "./RejillaCompases";

function pintar(props = {}) {
  const alPedirSalto = vi.fn();
  const alMarcarRango = vi.fn();
  render(
    <RejillaCompases
      total={12}
      enCurso={3}
      primero={1}
      ultimo={12}
      compasVariable={false}
      alPedirSalto={alPedirSalto}
      alMarcarRango={alMarcarRango}
      {...props}
    />,
  );
  return { alPedirSalto, alMarcarRango };
}

// Las consultas por nombre accesible van con la cadena EXACTA y no con una
// expresión regular sin anclar: `/compás 1/i` casa con el 1, el 10, el 11 y el 12
// en una pieza de doce, así que la primera prueba que consultara el 1 o el 2
// fallaría por «found multiple elements» y no por el defecto que buscaba. Que hoy
// no fallara era casualidad: ninguna consultaba esos dos números.
describe("la rejilla de compases", () => {
  it("dibuja un compás por cada uno de la pieza", () => {
    pintar();
    expect(screen.getAllByRole("button")).toHaveLength(12);
  });

  it("marca el compás en curso y solo ese", () => {
    pintar({ enCurso: 3 });
    expect(screen.getByRole("button", { name: "Compás 3" }).getAttribute("aria-current")).toBe(
      "true",
    );
    expect(screen.getByRole("button", { name: "Compás 4" }).getAttribute("aria-current")).toBe(
      null,
    );
  });

  it("pinta el rango del bucle encima", () => {
    pintar({ primero: 5, ultimo: 7 });
    for (const numero of [5, 6, 7]) {
      expect(
        screen
          .getByRole("button", { name: `Compás ${numero}` })
          .classList.contains("en-el-bucle"),
      ).toBe(true);
    }
    expect(
      screen.getByRole("button", { name: "Compás 4" }).classList.contains("en-el-bucle"),
    ).toBe(false);
  });

  it("un clic pide el salto a ese compás", () => {
    const { alPedirSalto } = pintar();
    fireEvent.click(screen.getByRole("button", { name: "Compás 9" }));
    expect(alPedirSalto).toHaveBeenCalledWith(9);
  });

  it("arrastrar marca el rango, y lo marca en orden aunque se arrastre al revés", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Compás 8" }));
    fireEvent.pointerEnter(screen.getByRole("button", { name: "Compás 5" }));
    fireEvent.pointerUp(screen.getByRole("button", { name: "Compás 5" }));
    expect(alMarcarRango).toHaveBeenCalledWith(5, 8);
  });

  it("un arrastre de un solo compás no se confunde con un clic", () => {
    // Soltar donde se empezó es un clic: salta, no marca un rango de uno.
    const { alPedirSalto, alMarcarRango } = pintar();
    const uno = screen.getByRole("button", { name: "Compás 6" });
    fireEvent.pointerDown(uno);
    fireEvent.pointerUp(uno);
    fireEvent.click(uno);
    expect(alPedirSalto).toHaveBeenCalledWith(6);
    expect(alMarcarRango).not.toHaveBeenCalled();
  });

  it("avisa cuando la pieza cambia de compás, porque las barras caen mal", () => {
    pintar({ compasVariable: true });
    expect(screen.getByText(/cambia de compás/i)).toBeTruthy();
  });

  it("una pieza sin compases no dibuja rejilla", () => {
    const { container } = render(
      <RejillaCompases
        total={0}
        enCurso={1}
        primero={1}
        ultimo={0}
        compasVariable={false}
        alPedirSalto={vi.fn()}
        alMarcarRango={vi.fn()}
      />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("sin cambio de compás no hay aviso, aunque la rejilla esté dibujada", () => {
    pintar({ compasVariable: false });
    expect(screen.getAllByRole("button")).toHaveLength(12);
    expect(screen.queryByText(/cambia de compás/i)).toBeNull();
  });

  it("solo hay un compás en curso, y es el que dice el estado", () => {
    pintar({ enCurso: 7 });
    const marcados = screen
      .getAllByRole("button")
      .filter((boton) => boton.getAttribute("aria-current") === "true");
    expect(marcados.map((boton) => boton.textContent)).toEqual(["7"]);
  });

  it("el rango del bucle son exactamente los compases del rango, con los dos extremos", () => {
    pintar({ primero: 5, ultimo: 7 });
    const dentro = screen
      .getAllByRole("button")
      .filter((boton) => boton.classList.contains("en-el-bucle"));
    expect(dentro.map((boton) => boton.textContent)).toEqual(["5", "6", "7"]);
  });

  it("mientras se arrastra se ven marcados los compases del arrastre, y al soltar se apagan", () => {
    pintar();
    const marcados = () =>
      screen
        .getAllByRole("button")
        .filter((boton) => boton.classList.contains("marcando"))
        .map((boton) => boton.textContent);
    fireEvent.pointerDown(screen.getByRole("button", { name: "Compás 3" }));
    expect(marcados()).toEqual(["3"]);
    fireEvent.pointerEnter(screen.getByRole("button", { name: "Compás 5" }));
    expect(marcados()).toEqual(["3", "4", "5"]);
    fireEvent.pointerUp(screen.getByRole("button", { name: "Compás 5" }));
    expect(marcados()).toEqual([]);
  });

  it("pasar el puntero por la rejilla sin haber pulsado no marca nada", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerEnter(screen.getByRole("button", { name: "Compás 5" }));
    fireEvent.pointerUp(screen.getByRole("button", { name: "Compás 5" }));
    expect(screen.getAllByRole("button")).toHaveLength(12);
    expect(alMarcarRango).not.toHaveBeenCalled();
  });

  it("tras un arrastre ya soltado, pasar el puntero por otro compás no sigue marcando", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Compás 3" }));
    fireEvent.pointerEnter(screen.getByRole("button", { name: "Compás 5" }));
    fireEvent.pointerUp(screen.getByRole("button", { name: "Compás 5" }));
    expect(alMarcarRango).toHaveBeenCalledTimes(1);

    fireEvent.pointerEnter(screen.getByRole("button", { name: "Compás 9" }));
    const marcados = screen
      .getAllByRole("button")
      .filter((boton) => boton.classList.contains("marcando"));
    expect(marcados).toHaveLength(0);
    fireEvent.pointerUp(screen.getByRole("button", { name: "Compás 9" }));
    expect(alMarcarRango).toHaveBeenCalledTimes(1);
  });

  // OJO: esta prueba documenta un comportamiento que NO depende de la cancelación
  // por `window` (el `pointerdown` del clic siguiente ya pisa el arrastre viejo) y
  // pasa también sin ella. No es la red: la que vigila la cancelación es la
  // siguiente, que mira el marcado al pasar el puntero y el `pointerup` suelto.
  it.each(["pointerUp", "pointerCancel"] as const)(
    "un arrastre que termina fuera de la rejilla (%s) no convierte el clic siguiente en rango",
    (evento) => {
      const { alPedirSalto, alMarcarRango } = pintar();
      fireEvent.pointerDown(screen.getByRole("button", { name: "Compás 8" }));
      fireEvent[evento](document.body); // el puntero se suelta fuera de la rejilla
      expect(alMarcarRango).not.toHaveBeenCalled();

      // Un clic normal en otro compás: pulsar, soltar y click.
      const tres = screen.getByRole("button", { name: "Compás 3" });
      fireEvent.pointerDown(tres);
      fireEvent.pointerUp(tres);
      fireEvent.click(tres);

      expect(alPedirSalto).toHaveBeenCalledWith(3);
      expect(alMarcarRango).not.toHaveBeenCalled();
    },
  );

  it("soltar sobre un compás sigue marcando el rango, aunque también cancele en window", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Compás 2" }));
    fireEvent.pointerEnter(screen.getByRole("button", { name: "Compás 4" }));
    fireEvent.pointerUp(screen.getByRole("button", { name: "Compás 4" }));
    expect(alMarcarRango).toHaveBeenCalledTimes(1);
    expect(alMarcarRango).toHaveBeenCalledWith(2, 4);
  });

  it.each(["pointerUp", "pointerCancel"] as const)(
    "tras terminar fuera de la rejilla (%s), pasar el puntero no sigue marcando ni un pointerup suelto marca un rango",
    (evento) => {
      const { alMarcarRango } = pintar();
      fireEvent.pointerDown(screen.getByRole("button", { name: "Compás 8" }));
      fireEvent[evento](document.body);

      fireEvent.pointerEnter(screen.getByRole("button", { name: "Compás 3" }));
      const marcados = screen
        .getAllByRole("button")
        .filter((boton) => boton.classList.contains("marcando"));
      expect(marcados).toHaveLength(0);

      // Un puntero que se pulsó fuera y se suelta sobre un compás no es un arrastre.
      fireEvent.pointerUp(screen.getByRole("button", { name: "Compás 3" }));
      expect(alMarcarRango).not.toHaveBeenCalled();
      // (Aquí había un `toHaveLength(12)` que esta prueba no puede mover: era
      //  confianza falsa. Lo que sostiene el caso son las dos líneas de arriba.)
    },
  );
});
