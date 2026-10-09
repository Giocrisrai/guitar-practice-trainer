import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Carril } from "./Carril";
import type { EstadoCarril, NotaTocada, Pieza, RespuestaIniciarPieza } from "./tiposPieza";

/**
 * Qué se puede probar aquí y qué no.
 *
 * En jsdom no hay canvas de verdad: `getContext("2d")` no existe y el lienzo
 * mide cero. Así que estas pruebas comprueban el CABLEADO (qué se le pide al
 * servidor, qué WebSocket se abre, cuándo aparece y desaparece el lienzo, que el
 * bucle de dibujo se cancela) y el TEXTO (la pausa, el resumen). El dibujo en sí
 * se juzga mirándolo, y lo que puede estar mal en él —qué notas entran en la
 * ventana y en qué rectángulo caen— ya está probado en `geometriaCarril.test.ts`
 * sin canvas de por medio.
 */

/** Las familias tal y como las publica `/api/ejercicios/familias`. */
const FAMILIAS = [
  {
    clave: "escala",
    nombre: "Escalas",
    descripcion: "Una escala en una posicion del mastil",
    tipos: ["mayor", "pentatonica_menor"],
    parametros: ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
  },
];

const PERFILES = [
  {
    clave: "guitarra_estandar",
    nombre: "Guitarra estandar",
    trastes: 22,
    cuerdas: [
      { numero: 6, nota: "E2", frecuencia: 82.41 },
      { numero: 5, nota: "A2", frecuencia: 110.0 },
      { numero: 4, nota: "D3", frecuencia: 146.83 },
      { numero: 3, nota: "G3", frecuencia: 196.0 },
      { numero: 2, nota: "B3", frecuencia: 246.94 },
      { numero: 1, nota: "E4", frecuencia: 329.63 },
    ],
  },
];

const PIEZA: Pieza = {
  nombre: "Escala de Do mayor",
  perfil: "guitarra_estandar",
  tempo: 60,
  compas: [4, 4],
  duracion_pulsos: 3,
  notas: [
    { midi: 40, nombre: "E2", cuerda: 6, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
    { midi: 45, nombre: "A2", cuerda: 5, traste: 0, inicio_pulsos: 1, duracion_pulsos: 1 },
    { midi: 50, nombre: "D3", cuerda: 4, traste: 0, inicio_pulsos: 2, duracion_pulsos: 1 },
  ],
};

/** El carril apagado: las mismas claves que con pieza (`_CARRIL_APAGADO`). */
const ESTADO_APAGADO: EstadoCarril = {
  instante_s: 0,
  indice_actual: 0,
  total: 0,
  completado: false,
  tocadas: [],
  pausado: false,
};

/** Lo que devuelve `POST /api/piezas/iniciar`: la pieza entera y el estado inicial. */
const RESPUESTA_INICIAR: RespuestaIniciarPieza = {
  pieza: PIEZA,
  instante_s: 0,
  indice_actual: 0,
  total: 3,
  completado: false,
  tocadas: [],
  pausado: false,
};

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

/** Un `fetch` que contesta a todo lo que el carril pregunta. */
function crearFetchFalso() {
  return vi.fn((url: string) => {
    const direccion = String(url);
    if (direccion.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
    if (direccion.includes("/api/perfiles")) return responder(PERFILES);
    if (direccion.includes("/api/piezas/iniciar")) return responder(RESPUESTA_INICIAR);
    return responder(ESTADO_APAGADO);
  });
}

/**
 * Un paquete tal y como lo escriben estas pruebas.
 *
 * `tocadas` admite pulsaciones sin `nombre` —que el servidor sí manda— porque
 * el carril no lo usa: el nombre de una nota lo da la PIEZA, y la pulsación solo
 * dice a qué índice se adjudicó. Así cada fixture declara lo que importa en su
 * prueba sin obligar a rellenar campos que no se leen.
 */
type PaqueteDePrueba = Omit<EstadoCarril, "tocadas"> & {
  tocadas: (Omit<NotaTocada, "nombre"> & { nombre?: string })[];
};

/**
 * Manda un paquete por el WebSocket del carril.
 *
 * Dentro de `act` porque el paquete provoca un cambio de estado de React: sin
 * esto el repintado cae fuera de la prueba y React avisa de una actualización
 * sin envolver.
 */
function enviarEstado(estado: PaqueteDePrueba) {
  act(() => {
    WebSocketFalso.ultimo!.enviar(estado);
  });
}

/** Pulsa "Empezar" y espera a que el POST y sus cambios de estado terminen. */
async function pulsarEmpezar() {
  await act(async () => {
    screen.getByRole("button", { name: /empezar/i }).click();
  });
}

describe("Carril", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => vi.unstubAllGlobals());

  it("pide una pieza al servidor y la arranca", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    await waitFor(() =>
      expect(
        fetchFalso.mock.calls.some(([url]) => url === "/api/piezas/iniciar")
      ).toBe(true)
    );
  });

  it("no pinta nada hasta que hay pieza", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    expect(screen.queryByTestId("lienzo-carril")).toBeNull();
  });

  it("avisa cuando el carril está pausado por falta de señal", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    enviarEstado({ instante_s: 1.0, indice_actual: 0, total: 3, completado: false,
                   pausado: true, tocadas: [] });
    expect(await screen.findByText(/pausado/i)).toBeTruthy();
  });

  it("al terminar muestra el resumen con los desfases", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    enviarEstado({
      instante_s: 4.0, indice_actual: 3, total: 3, completado: true, pausado: false,
      tocadas: [
        { indice: 0, midi: 40, cents: -5.0, desfase_s: 0.01, clasificacion: "a_tiempo", acertada: true },
        { indice: 1, midi: 45, cents: 3.0, desfase_s: 0.22, clasificacion: "tarde", acertada: true },
      ],
    });
    expect(await screen.findByText(/a tiempo/i)).toBeTruthy();
    expect(await screen.findByText(/tarde/i)).toBeTruthy();
  });

  it("escucha el WebSocket del carril, no el de los ejercicios", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    expect(WebSocketFalso.ultimo!.url).toContain("/ws/piezas");
  });

  it("el lienzo aparece con la pieza y se va al detener", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    await pulsarEmpezar();
    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();

    await act(async () => {
      screen.getByRole("button", { name: /detener/i }).click();
    });
    expect(screen.queryByTestId("lienzo-carril")).toBeNull();
  });

  /**
   * Un bucle de `requestAnimationFrame` que sobrevive al componente sigue
   * dibujando sobre un canvas que ya no está en el documento. Se comprueba de
   * verdad: se sustituyen las dos funciones del navegador, se deja correr un
   * cuadro (que pide el siguiente, como todo bucle de animación), y al desmontar
   * tiene que cancelarse el cuadro pendiente y no pedirse ninguno más.
   */
  it("cancela el bucle de dibujo al desmontar", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    const cuadros: FrameRequestCallback[] = [];
    const pedir = vi.fn((callback: FrameRequestCallback) => {
      cuadros.push(callback);
      return cuadros.length; // el identificador es la posición, empezando en 1
    });
    const cancelar = vi.fn();
    vi.stubGlobal("requestAnimationFrame", pedir);
    vi.stubGlobal("cancelAnimationFrame", cancelar);

    const { unmount } = render(<Carril />);
    await pulsarEmpezar();
    await waitFor(() => expect(cuadros.length).toBeGreaterThan(0));

    // Un cuadro del bucle: tiene que encadenar el siguiente.
    act(() => {
      cuadros[cuadros.length - 1](1234);
    });
    expect(cuadros.length).toBe(2);

    unmount();
    expect(cancelar).toHaveBeenCalledWith(2);
    expect(cuadros.length).toBe(2); // ni un cuadro más tras desmontar
  });
});
