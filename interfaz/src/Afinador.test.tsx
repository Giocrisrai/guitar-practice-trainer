import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Afinador } from "./Afinador";
import type { Configuracion, DispositivoEntrada, PerfilAfinacion } from "./tipos";

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

const DISPOSITIVOS: DispositivoEntrada[] = [
  { indice: 0, nombre: "MacBook Pro Microphone", canales_entrada: 1, frecuencia_muestreo: 48000 },
  { indice: 3, nombre: "Rocksmith USB Guitar Adapter", canales_entrada: 1, frecuencia_muestreo: 48000 },
];

const CONFIG: Configuracion = {
  dispositivo: 0,
  perfil: "guitarra_estandar",
  ganancia: 1,
  umbral_ruido_dbfs: -60,
  referencia_a4: 440,
  confianza_minima: 0.75,
  detector: "yin",
};

/**
 * Doble de `fetch` que responde a `/api/perfiles`, `/api/dispositivos`,
 * `/api/config` (GET y PUT) y `/api/calibrar`. El comportamiento del PUT y el de
 * la calibración se inyectan por prueba para simular tanto el éxito como el
 * fallo del servidor.
 */
function crearFetchFalso(
  respuestaPut: () => Promise<Response>,
  respuestaCalibrar?: () => Promise<Response>
) {
  return vi.fn((url: string, opciones?: RequestInit) => {
    if (url === "/api/perfiles" && !opciones?.method) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(PERFILES),
      } as Response);
    }
    if (url === "/api/dispositivos" && !opciones?.method) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(DISPOSITIVOS),
      } as Response);
    }
    if (url === "/api/config" && !opciones?.method) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(CONFIG),
      } as Response);
    }
    if (url === "/api/config" && opciones?.method === "PUT") {
      return respuestaPut();
    }
    if (url === "/api/calibrar" && opciones?.method === "POST" && respuestaCalibrar) {
      return respuestaCalibrar();
    }
    return Promise.reject(new Error(`fetch no simulado: ${url}`));
  });
}

/** Cuerpo que devuelve el servidor en un PUT que sí se aplicó. */
function putCorrecto() {
  return Promise.resolve({
    ok: true,
    json: () =>
      Promise.resolve({
        configuracion: CONFIG,
        diagnostico: { estado: "ok", mensaje: "", accion: "", dispositivos: [] },
      }),
  } as Response);
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

describe("Afinador - selector de dispositivo", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra los dispositivos del servidor y guarda el elegido", async () => {
    const fetchFalso = crearFetchFalso(putCorrecto);
    vi.stubGlobal("fetch", fetchFalso);

    render(<Afinador />);

    const selector = (await screen.findByLabelText("Dispositivo")) as HTMLSelectElement;
    await waitFor(() => expect(selector.value).toBe("0"));
    expect(screen.getByText("Rocksmith USB Guitar Adapter")).toBeTruthy();

    fireEvent.change(selector, { target: { value: "3" } });

    await waitFor(() => expect(selector.value).toBe("3"));
    const llamada = fetchFalso.mock.calls.find(
      ([url, opciones]) => url === "/api/config" && opciones?.method === "PUT"
    );
    expect(JSON.parse(String(llamada?.[1]?.body))).toEqual({ dispositivo: 3 });
  });

  it("revierte y muestra el error cuando el PUT del dispositivo falla", async () => {
    const fetchFalso = crearFetchFalso(() =>
      Promise.resolve({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: "dispositivo desconocido" }),
      } as Response)
    );
    vi.stubGlobal("fetch", fetchFalso);

    render(<Afinador />);

    const selector = (await screen.findByLabelText("Dispositivo")) as HTMLSelectElement;
    await waitFor(() => expect(selector.value).toBe("0"));

    fireEvent.change(selector, { target: { value: "3" } });

    await waitFor(() => expect(selector.value).toBe("0"));
    expect(await screen.findByText("dispositivo desconocido")).toBeTruthy();
  });

  it("avisa cuando el PUT se aplica pero el diagnóstico no es ok", async () => {
    // El servidor adjunta el diagnóstico para que un dispositivo que no se pudo
    // abrir llegue al usuario en vez de perderse en un 200 llano.
    const fetchFalso = crearFetchFalso(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            configuracion: CONFIG,
            diagnostico: {
              estado: "sin_dispositivo",
              mensaje: "No se pudo abrir el dispositivo.",
              accion: "Reconecta el cable.",
              dispositivos: [],
            },
          }),
      } as Response)
    );
    vi.stubGlobal("fetch", fetchFalso);

    render(<Afinador />);

    const selector = (await screen.findByLabelText("Dispositivo")) as HTMLSelectElement;
    await waitFor(() => expect(selector.value).toBe("0"));

    fireEvent.change(selector, { target: { value: "3" } });

    expect(
      await screen.findByText("No se pudo abrir el dispositivo. Reconecta el cable.")
    ).toBeTruthy();
  });
});

describe("Afinador - calibración", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("mide el umbral, lo muestra antes y después y lo guarda", async () => {
    const fetchFalso = crearFetchFalso(putCorrecto, () =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ umbral_sugerido: -58.4 }),
      } as Response)
    );
    vi.stubGlobal("fetch", fetchFalso);

    render(<Afinador />);

    expect(await screen.findByText("umbral -60.0 dBFS")).toBeTruthy();

    fireEvent.click(screen.getByText("Calibrar ruido"));

    await waitFor(() => expect(screen.getByText("umbral -58.4 dBFS")).toBeTruthy());
    expect(screen.getByText(/-60.0 → -58.4 dBFS/)).toBeTruthy();

    const llamada = fetchFalso.mock.calls.find(
      ([url, opciones]) => url === "/api/config" && opciones?.method === "PUT"
    );
    expect(JSON.parse(String(llamada?.[1]?.body))).toEqual({ umbral_ruido_dbfs: -58.4 });
  });

  it("muestra el error si la calibración falla y no cambia el umbral", async () => {
    const fetchFalso = crearFetchFalso(putCorrecto, () =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) } as Response)
    );
    vi.stubGlobal("fetch", fetchFalso);

    render(<Afinador />);

    expect(await screen.findByText("umbral -60.0 dBFS")).toBeTruthy();
    fireEvent.click(screen.getByText("Calibrar ruido"));

    expect(await screen.findByText("El servidor respondio 500")).toBeTruthy();
    expect(screen.getByText("umbral -60.0 dBFS")).toBeTruthy();
  });
});
