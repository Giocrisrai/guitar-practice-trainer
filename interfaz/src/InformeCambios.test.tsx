import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InformeCambios } from "./InformeCambios";
import type { InformeCambiosServidor } from "./tiposEjercicio";

function informe(cambios: Partial<InformeCambiosServidor> = {}): InformeCambiosServidor {
  return {
    ejercicio: "cambios_do_sol",
    completado: true,
    acordes: [
      {
        indice: 0,
        nombre: "Do mayor",
        intentos: 1,
        logrado: true,
        cambio_s: null,
        faltaron: [],
        ayuda_mostrada: false,
      },
      {
        indice: 1,
        nombre: "Sol mayor",
        intentos: 1,
        logrado: true,
        cambio_s: 1.4,
        faltaron: [],
        ayuda_mostrada: false,
      },
    ],
    logrados: 2,
    a_la_primera: 2,
    tiempo_medio_de_cambio_s: 1.4,
    cambio_mas_lento_s: 1.4,
    cuerdas_problematicas: [],
    ...cambios,
  };
}

describe("InformeCambios", () => {
  it("el tiempo de cambio es la cifra de cabecera", () => {
    render(<InformeCambios informe={informe()} onReiniciar={() => {}} />);
    expect(screen.getByRole("heading", { level: 2 }).textContent).toContain("1.40 s por cambio");
  });

  it("sin ningun cambio medido no inventa un cero", () => {
    render(
      <InformeCambios
        informe={informe({ tiempo_medio_de_cambio_s: null, cambio_mas_lento_s: null })}
        onReiniciar={() => {}}
      />
    );
    expect(screen.getByRole("heading", { level: 2 }).textContent).toContain(
      "Sin cambios medidos"
    );
    expect(screen.queryByText(/0.00 s por cambio/)).toBeNull();
  });

  it("dice cuantos acordes salieron y cuantos a la primera", () => {
    render(<InformeCambios informe={informe()} onReiniciar={() => {}} />);
    expect(screen.getByText(/2 de 2 acordes, 2 a la primera/)).toBeTruthy();
  });

  it("lista las notas que mas veces no sonaron", () => {
    render(
      <InformeCambios
        informe={informe({ cuerdas_problematicas: [64, 60] })}
        onReiniciar={() => {}}
      />
    );
    expect(screen.getByText("E4")).toBeTruthy();
    expect(screen.getByText("C4")).toBeTruthy();
  });

  it("no pone la seccion de cuerdas cuando no fallo ninguna", () => {
    render(<InformeCambios informe={informe()} onReiniciar={() => {}} />);
    expect(screen.queryByText(/no sonaron/)).toBeNull();
  });

  it("lista los acordes que costaron tres intentos o mas", () => {
    const con = informe();
    con.acordes[0] = { ...con.acordes[0], intentos: 4 };
    render(<InformeCambios informe={con} onReiniciar={() => {}} />);
    expect(screen.getByText(/Do mayor — 4 intentos/)).toBeTruthy();
  });

  it("el primer acorde dice que no hay cambio que medir, no cero", () => {
    render(<InformeCambios informe={informe()} onReiniciar={() => {}} />);
    expect(screen.getByText(/Do mayor — sin cambio que medir/)).toBeTruthy();
  });

  it("volver a empezar avisa a quien lo pidio", () => {
    const reiniciar = vi.fn();
    render(<InformeCambios informe={informe()} onReiniciar={reiniciar} />);
    screen.getByRole("button", { name: "Volver a empezar" }).click();
    expect(reiniciar).toHaveBeenCalledOnce();
  });
});
