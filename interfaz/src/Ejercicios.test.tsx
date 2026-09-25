import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Ejercicios } from "./Ejercicios";

const FAMILIAS = [
  {
    clave: "escala",
    nombre: "Escalas",
    descripcion: "Una escala en una posicion",
    tipos: ["mayor", "pentatonica_menor"],
    parametros: ["raiz_midi", "tipo"],
  },
  {
    clave: "lectura",
    nombre: "Lectura del mastil",
    descripcion: "Encuentra la nota",
    tipos: [],
    parametros: ["cuerda"],
  },
];

const PERFILES = [
  {
    clave: "guitarra_estandar",
    nombre: "Guitarra estandar",
    trastes: 22,
    cuerdas: [
      { numero: 6, nota: "E2", frecuencia: 82.41 },
      { numero: 1, nota: "E4", frecuencia: 329.63 },
    ],
  },
];

const ESTADO_VACIO = { ejercicio: null, evaluacion: null, informe: null, metronomo: false };

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

  close() {}

  enviar(datos: unknown) {
    this.onmessage?.({ data: JSON.stringify(datos) });
  }
}

function responder(cuerpo: unknown, ok = true, estado = 200) {
  return Promise.resolve({
    ok,
    status: estado,
    json: () => Promise.resolve(cuerpo),
  } as Response);
}

describe("Ejercicios", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (url.includes("/api/perfiles")) return responder(PERFILES);
        if (url.includes("/api/ejercicios/estado")) return responder(ESTADO_VACIO);
        return responder(ESTADO_VACIO);
      })
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("el configurador se construye con las familias del servidor", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(screen.getByText("Lectura del mastil")).toBeTruthy();
  });

  it("muestra los tipos de la familia elegida, no una lista escrita a mano", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(screen.getByText("pentatonica_menor")).toBeTruthy();
  });

  it("muestra la nota que toca ahora cuando hay ejercicio en curso", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar({
      ejercicio: {
        clave: "e",
        nombre: "Escala de Do mayor",
        descripcion: "",
        tempo: 80,
        perfil: "guitarra_estandar",
        notas: [
          { midi: 48, nombre: "C3", posiciones: [{ cuerda: 5, traste: 3 }], pulsos: 1, referencia_midi: null },
        ],
      },
      evaluacion: {
        indice: 0,
        total: 1,
        intentos: 0,
        ayuda_visible: false,
        completado: false,
        nota_actual: { midi: 48, nombre: "C3", posiciones: [{ cuerda: 5, traste: 3 }], pulsos: 1, referencia_midi: null },
        ultimo_fallo: null,
      },
      informe: null,
      metronomo: true,
    });
    await waitFor(() => expect(screen.getByText("C3")).toBeTruthy());
  });

  it("avisa de que nota sono cuando fallas", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar({
      ejercicio: {
        clave: "e",
        nombre: "Prueba",
        descripcion: "",
        tempo: 80,
        perfil: "guitarra_estandar",
        notas: [],
      },
      evaluacion: {
        indice: 0,
        total: 3,
        intentos: 2,
        ayuda_visible: false,
        completado: false,
        nota_actual: { midi: 40, nombre: "E2", posiciones: [], pulsos: 1, referencia_midi: null },
        ultimo_fallo: "A2",
      },
      informe: null,
      metronomo: false,
    });
    await waitFor(() => expect(screen.getByText(/A2/)).toBeTruthy());
  });

  it("muestra el informe al completar el ejercicio", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar({
      ejercicio: null,
      evaluacion: {
        indice: 2,
        total: 2,
        intentos: 0,
        ayuda_visible: false,
        completado: true,
        nota_actual: null,
        ultimo_fallo: null,
      },
      informe: {
        ejercicio: "e",
        completado: true,
        notas: [
          { indice: 0, midi: 40, nombre: "E2", intentos: 1, cents: 2.0, instante: 0, ayuda_mostrada: false },
          { indice: 1, midi: 42, nombre: "F#2", intentos: 4, cents: -8.0, instante: 1, ayuda_mostrada: false },
        ],
        aciertos_a_la_primera: 1,
        desviacion_mediana_cents: -3.0,
        regularidad_ms: null,
        notas_dificiles: [
          { indice: 1, midi: 42, nombre: "F#2", intentos: 4, cents: -8.0, instante: 1, ayuda_mostrada: false },
        ],
      },
      metronomo: false,
    });
    await waitFor(() => expect(screen.getByText(/F#2/)).toBeTruthy());
  });

  it("un error del servidor al generar se muestra al usuario", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, opciones?: RequestInit) => {
        if (url.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (url.includes("/api/perfiles")) return responder(PERFILES);
        if (opciones?.method === "POST") {
          return responder({ detail: "No cae ninguna nota de la escala" }, false, 400);
        }
        return responder(ESTADO_VACIO);
      })
    );
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    screen.getByRole("button", { name: /empezar/i }).click();
    await waitFor(() => expect(screen.getByText(/No cae ninguna nota/)).toBeTruthy());
  });
});
