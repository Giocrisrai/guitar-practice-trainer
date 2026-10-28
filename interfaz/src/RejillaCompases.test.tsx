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

describe("la rejilla de compases", () => {
  it("dibuja un compás por cada uno de la pieza", () => {
    pintar();
    expect(screen.getAllByRole("button")).toHaveLength(12);
  });

  it("marca el compás en curso y solo ese", () => {
    pintar({ enCurso: 3 });
    expect(screen.getByRole("button", { name: /compás 3/i }).getAttribute("aria-current")).toBe(
      "true",
    );
    expect(screen.getByRole("button", { name: /compás 4/i }).getAttribute("aria-current")).toBe(
      null,
    );
  });

  it("pinta el rango del bucle encima", () => {
    pintar({ primero: 5, ultimo: 7 });
    for (const numero of [5, 6, 7]) {
      expect(
        screen
          .getByRole("button", { name: new RegExp(`compás ${numero}`, "i") })
          .classList.contains("en-el-bucle"),
      ).toBe(true);
    }
    expect(
      screen.getByRole("button", { name: /compás 4/i }).classList.contains("en-el-bucle"),
    ).toBe(false);
  });

  it("un clic pide el salto a ese compás", () => {
    const { alPedirSalto } = pintar();
    fireEvent.click(screen.getByRole("button", { name: /compás 9/i }));
    expect(alPedirSalto).toHaveBeenCalledWith(9);
  });

  it("arrastrar marca el rango, y lo marca en orden aunque se arrastre al revés", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerDown(screen.getByRole("button", { name: /compás 8/i }));
    fireEvent.pointerEnter(screen.getByRole("button", { name: /compás 5/i }));
    fireEvent.pointerUp(screen.getByRole("button", { name: /compás 5/i }));
    expect(alMarcarRango).toHaveBeenCalledWith(5, 8);
  });

  it("un arrastre de un solo compás no se confunde con un clic", () => {
    // Soltar donde se empezó es un clic: salta, no marca un rango de uno.
    const { alPedirSalto, alMarcarRango } = pintar();
    const uno = screen.getByRole("button", { name: /compás 6/i });
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
    fireEvent.pointerDown(screen.getByRole("button", { name: /compás 3/i }));
    expect(marcados()).toEqual(["3"]);
    fireEvent.pointerEnter(screen.getByRole("button", { name: /compás 5/i }));
    expect(marcados()).toEqual(["3", "4", "5"]);
    fireEvent.pointerUp(screen.getByRole("button", { name: /compás 5/i }));
    expect(marcados()).toEqual([]);
  });

  it("pasar el puntero por la rejilla sin haber pulsado no marca nada", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerEnter(screen.getByRole("button", { name: /compás 5/i }));
    fireEvent.pointerUp(screen.getByRole("button", { name: /compás 5/i }));
    expect(screen.getAllByRole("button")).toHaveLength(12);
    expect(alMarcarRango).not.toHaveBeenCalled();
  });

  it("tras un arrastre ya soltado, pasar el puntero por otro compás no sigue marcando", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerDown(screen.getByRole("button", { name: /compás 3/i }));
    fireEvent.pointerEnter(screen.getByRole("button", { name: /compás 5/i }));
    fireEvent.pointerUp(screen.getByRole("button", { name: /compás 5/i }));
    expect(alMarcarRango).toHaveBeenCalledTimes(1);

    fireEvent.pointerEnter(screen.getByRole("button", { name: /compás 9/i }));
    const marcados = screen
      .getAllByRole("button")
      .filter((boton) => boton.classList.contains("marcando"));
    expect(marcados).toHaveLength(0);
    fireEvent.pointerUp(screen.getByRole("button", { name: /compás 9/i }));
    expect(alMarcarRango).toHaveBeenCalledTimes(1);
  });
});
