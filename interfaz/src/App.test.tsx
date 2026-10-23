import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

/**
 * El armazón: qué módulo se abre y qué se le pasa.
 *
 * Lo que se prueba aquí y no se puede probar en otro sitio es el TRASPASO de una
 * canción al carril. `Canciones` elige y avisa; el carril arranca y dibuja, y tiene
 * que ser él quien haga el POST porque la pieza entera viaja una sola vez en la
 * respuesta de `/iniciar` y el WebSocket no la repite. El camino pasa por `App`,
 * que es quien guarda el módulo activo.
 */

/** Los módulos tal y como los publica `/api/modulos`, con descripciones distintas
 * para poder pulsar cada botón de la cabecera por su `title`. */
const MODULOS = [
  { clave: "afinador", nombre: "Afinador", descripcion: "afina", icono: "🎸", disponible: true },
  { clave: "canciones", nombre: "Canciones", descripcion: "importa", icono: "🎵", disponible: true },
  { clave: "carril", nombre: "Carril", descripcion: "toca", icono: "🛣️", disponible: true },
];

const CANCION = {
  id: "x.gp5",
  nombre: "x",
  formato: "Guitar Pro",
  bytes: 1234,
  modificado: "2026-10-22T10:00:00+00:00",
};

const AFINACION = {
  clave: "guitarra_estandar",
  nombre: "Guitarra estándar",
  cuerdas_midi: [40, 45, 50, 55, 59, 64],
  declarada: true,
};

const DETALLE = {
  ...CANCION,
  pistas: [
    {
      numero: 1,
      nombre: "Guitarra ritmica",
      instrumento: "Guitarra",
      cuerdas_midi: [40, 45, 50, 55, 59, 64],
      notas: 2,
      usable: true,
      motivo_no_usable: null,
      afinacion: AFINACION,
    },
  ],
  afinacion: AFINACION,
  perfil_activo: "guitarra_estandar",
  coincide: true,
};

const NOTAS = [
  { midi: 40, nombre: "E2", cuerda: 6, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
  { midi: 45, nombre: "A2", cuerda: 5, traste: 0, inicio_pulsos: 1, duracion_pulsos: 1 },
];

const PIEZA = {
  nombre: "x",
  perfil: "guitarra_estandar",
  tempo: 90,
  compas: [4, 4],
  duracion_pulsos: 2,
  notas: NOTAS,
};

const ESTADO_APAGADO = {
  arranque: 0,
  instante_s: 0,
  indice_actual: 0,
  total: 0,
  completado: false,
  tocadas: [],
  pausado: false,
};

const RESPUESTA_INICIAR = {
  pieza: PIEZA,
  arranque: 1,
  instante_s: 0,
  indice_actual: 0,
  total: 2,
  completado: false,
  tocadas: [],
  pausado: false,
};

/** Doble mínimo de WebSocket: el afinador y el carril abren uno al montar. */
class WebSocketFalso {
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((evento: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
  }

  close() {}
}

function responder(cuerpo: unknown) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(cuerpo),
  } as Response);
}

/** Un `fetch` que contesta a todo lo que pregunta la aplicación entera. */
function crearFetchFalso() {
  return vi.fn((url: string, opciones?: RequestInit) => {
    const direccion = String(url);
    const metodo = opciones?.method ?? "GET";
    if (direccion === "/api/modulos") return responder(MODULOS);
    if (direccion === "/api/diagnostico") {
      return responder({ estado: "ok", mensaje: "", accion: "", dispositivos: [] });
    }
    if (direccion === "/api/perfiles") return responder([]);
    if (direccion === "/api/dispositivos") return responder([]);
    if (direccion === "/api/config" && metodo === "GET") {
      return responder({
        dispositivo: null,
        perfil: "guitarra_estandar",
        ganancia: 1,
        umbral_ruido_dbfs: -60,
        referencia_a4: 440,
        confianza_minima: 0.75,
        detector: "yin",
      });
    }
    if (direccion === "/api/ejercicios/familias") return responder([]);
    if (direccion === "/api/canciones" && metodo === "GET") return responder([CANCION]);
    if (direccion.endsWith("/pistas")) return responder(DETALLE);
    if (direccion.endsWith("/importar")) return responder({ ...PIEZA, avisos: [] });
    if (direccion === "/api/piezas/iniciar") return responder(RESPUESTA_INICIAR);
    return responder(ESTADO_APAGADO);
  });
}

/** Los POST a `/api/piezas/iniciar` que se han hecho, ya parseados. */
function arranques(fetchFalso: ReturnType<typeof crearFetchFalso>) {
  return fetchFalso.mock.calls
    .filter(([url]) => url === "/api/piezas/iniciar")
    .map(([, opciones]) => JSON.parse(String((opciones as RequestInit).body)));
}

describe("App", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("abre el modulo de canciones desde la cabecera", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<App />);
    fireEvent.click(await screen.findByTitle("importa"));
    expect(await screen.findByText("x")).toBeTruthy();
  });

  it("la cancion elegida en Canciones la arranca y la dibuja el carril", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(<App />);

    fireEvent.click(await screen.findByTitle("importa"));
    fireEvent.click(await screen.findByText("x"));
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));
    fireEvent.click(await screen.findByRole("button", { name: /tocar en el carril/i }));

    // El lienzo es del carril: la pieza llegó a quien la dibuja.
    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();
    expect(arranques(fetchFalso)).toEqual([
      { cancion: "x.gp5", pista: 1, perfil: null },
    ]);
  });

  /**
   * La canción pendiente es del traspaso, no del módulo. Sin soltarla al navegar,
   * abrir el carril desde la cabecera horas después volvía a arrancar la canción de
   * entonces en vez de ofrecer el configurador.
   */
  it("volver al carril desde la cabecera no rearranca la cancion de antes", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(<App />);

    fireEvent.click(await screen.findByTitle("importa"));
    fireEvent.click(await screen.findByText("x"));
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));
    fireEvent.click(await screen.findByRole("button", { name: /tocar en el carril/i }));
    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByTitle("afina"));
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle("toca"));
    });

    expect(await screen.findByRole("button", { name: /empezar/i })).toBeTruthy();
    expect(arranques(fetchFalso)).toHaveLength(1);
  });
});
