import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Afinador } from "./Afinador";
import type { PerfilAfinacion } from "./tipos";

/** Doble mínimo de WebSocket: Afinador usa useNotas, que abre un socket al montar. */
class WebSocketFalso {
  static ultimo: WebSocketFalso | null = null;
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((evento: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    WebSocketFalso.ultimo = this;
  }

  close() {
    this.onclose?.();
  }
}

const PERFILES: PerfilAfinacion[] = [
  {
    clave: "guitarra_estandar",
    nombre: "Guitarra estándar",
    trastes: 22,
    cuerdas: [
      { numero: 6, nota: "E2", frecuencia: 82.41 },
      { numero: 5, nota: "A2", frecuencia: 110.0 },
    ],
  },
  {
    clave: "guitarra_drop_d",
    nombre: "Guitarra Drop D",
    trastes: 22,
    cuerdas: [
      { numero: 6, nota: "D2", frecuencia: 73.42 },
      { numero: 5, nota: "A2", frecuencia: 110.0 },
    ],
  },
];

/**
 * Doble de `fetch` que responde a `/api/perfiles`, `/api/config` (GET) y
 * `/api/config` (PUT). El comportamiento del PUT se inyecta por prueba para
 * simular tanto el éxito como el fallo del servidor.
 */
function crearFetchFalso(respuestaPut: () => Promise<Response>) {
  return vi.fn((url: string, opciones?: RequestInit) => {
    if (url === "/api/perfiles" && !opciones?.method) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(PERFILES),
      } as Response);
    }
    if (url === "/api/config" && !opciones?.method) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ perfil: "guitarra_estandar" }),
      } as Response);
    }
    if (url === "/api/config" && opciones?.method === "PUT") {
      return respuestaPut();
    }
    return Promise.reject(new Error(`fetch no simulado: ${url}`));
  });
}

describe("Afinador - cambio de afinación", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("deja el selector en la nueva afinación y sin error cuando el PUT tiene éxito", async () => {
    const fetchFalso = crearFetchFalso(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ configuracion: {}, diagnostico: {} }),
      } as Response)
    );
    vi.stubGlobal("fetch", fetchFalso);

    render(<Afinador />);

    const selector = (await screen.findByLabelText("Afinación")) as HTMLSelectElement;
    await waitFor(() => expect(selector.value).toBe("guitarra_estandar"));

    fireEvent.change(selector, { target: { value: "guitarra_drop_d" } });

    await waitFor(() => expect(selector.value).toBe("guitarra_drop_d"));
    expect(screen.queryByText(/./, { selector: ".error-perfil" })).toBeNull();
  });

  it("revierte a la afinación anterior y muestra el detalle del error cuando el PUT responde 400", async () => {
    const fetchFalso = crearFetchFalso(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: "perfil desconocido" }),
      } as Response)
    );
    vi.stubGlobal("fetch", fetchFalso);

    render(<Afinador />);

    const selector = (await screen.findByLabelText("Afinación")) as HTMLSelectElement;
    await waitFor(() => expect(selector.value).toBe("guitarra_estandar"));

    fireEvent.change(selector, { target: { value: "guitarra_drop_d" } });

    await waitFor(() => expect(selector.value).toBe("guitarra_estandar"));
    expect(await screen.findByText("perfil desconocido")).toBeTruthy();
  });
});
