import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useNotas } from "./useNotas";

class WebSocketFalso {
  static ultimo: WebSocketFalso | null = null;
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((evento: { data: string }) => void) | null = null;
  cerrado = false;

  constructor(url: string) {
    this.url = url;
    WebSocketFalso.ultimo = this;
  }

  close() {
    this.cerrado = true;
    this.onclose?.();
  }

  abrir() {
    this.onopen?.();
  }

  enviar(datos: unknown) {
    this.onmessage?.({ data: JSON.stringify(datos) });
  }
}

describe("useNotas", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("empieza desconectado y sin nota", () => {
    const { result } = renderHook(() => useNotas());
    expect(result.current.conectado).toBe(false);
    expect(result.current.nota).toBeNull();
  });

  it("se marca conectado al abrirse el socket", () => {
    const { result } = renderHook(() => useNotas());
    act(() => WebSocketFalso.ultimo!.abrir());
    expect(result.current.conectado).toBe(true);
  });

  it("expone el último mensaje recibido", () => {
    const { result } = renderHook(() => useNotas());
    act(() => {
      WebSocketFalso.ultimo!.abrir();
      WebSocketFalso.ultimo!.enviar({ estado: "nota", nota: "E2", cents: -3 });
    });
    expect(result.current.nota?.nota).toBe("E2");
  });

  it("se reconecta solo tras una caída", () => {
    renderHook(() => useNotas());
    const primero = WebSocketFalso.ultimo;
    act(() => {
      primero!.abrir();
      primero!.onclose?.();
      vi.advanceTimersByTime(1500);
    });
    expect(WebSocketFalso.ultimo).not.toBe(primero);
  });

  it("ignora un mensaje que no sea JSON válido", () => {
    const { result } = renderHook(() => useNotas());
    act(() => {
      WebSocketFalso.ultimo!.abrir();
      WebSocketFalso.ultimo!.onmessage?.({ data: "{roto" });
    });
    expect(result.current.nota).toBeNull();
  });
});
