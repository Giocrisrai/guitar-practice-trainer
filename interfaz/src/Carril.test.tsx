import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Carril } from "./Carril";
import { useCarril } from "./useCarril";
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

/**
 * Las familias tal y como las publica `/api/ejercicios/familias`.
 *
 * La primera a propósito NO es `escala`: así una prueba puede comprobar que la
 * familia que viaja en el POST sale del catálogo del servidor y no de una clave
 * escrita en la interfaz.
 */
const FAMILIAS = [
  {
    clave: "arpegio",
    nombre: "Arpegios",
    descripcion: "Las notas de un acorde, una a una",
    tipos: ["mayor", "menor_septima"],
    parametros: ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
  },
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

/**
 * El arranque que el servidor le pone a la pieza de estas pruebas, y el de la
 * anterior. Son dos piezas de TRES notas cada una: el tamaño no las distingue,
 * y por eso hace falta la etiqueta (`EstadoCarril.arranque`).
 */
const ARRANQUE_EN_CURSO = 2;
const ARRANQUE_ANTERIOR = 1;

/** El carril apagado: las mismas claves que con pieza (`_CARRIL_APAGADO`). */
const ESTADO_APAGADO: EstadoCarril = {
  arranque: 0,
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
  arranque: ARRANQUE_EN_CURSO,
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
type PaqueteDePrueba = Omit<EstadoCarril, "tocadas" | "arranque"> & {
  tocadas: (Omit<NotaTocada, "nombre"> & { nombre?: string })[];
  /** El arranque del que habla el paquete. Omitirlo es decir "el de la pieza en
   * curso", que es lo que quieren las pruebas que no hablan de este asunto. */
  arranque?: number;
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
    WebSocketFalso.ultimo!.enviar({ arranque: ARRANQUE_EN_CURSO, ...estado });
  });
}

/** Un paquete de la pieza en curso, con lo que cada prueba quiera cambiar. */
function enCurso(cambios: Partial<EstadoCarril> = {}): EstadoCarril {
  return {
    arranque: ARRANQUE_EN_CURSO,
    instante_s: 0,
    indice_actual: 0,
    total: PIEZA.notas.length,
    completado: false,
    tocadas: [],
    pausado: false,
    ...cambios,
  };
}

/** El cuerpo del POST a `/api/piezas/iniciar`, ya parseado. */
function cuerpoDeIniciar(fetchFalso: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const llamada = fetchFalso.mock.calls.find(([url]) => url === "/api/piezas/iniciar");
  expect(llamada).toBeDefined();
  return JSON.parse(String((llamada![1] as RequestInit).body));
}

/** Pulsa "Empezar" y espera a que el POST y sus cambios de estado terminen. */
async function pulsarEmpezar() {
  await act(async () => {
    screen.getByRole("button", { name: /empezar/i }).click();
  });
}

describe("Carril", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

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
        { indice: 0, midi: 40, cents: -5.0, desfase_s: 0.01, clasificacion: "a_tiempo", acertada: true,
          afinada: false },
        { indice: 1, midi: 45, cents: 3.0, desfase_s: 0.22, clasificacion: "tarde", acertada: true,
          afinada: true },
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
   * El estado de una pieza no se pinta nunca sobre otra.
   *
   * El WebSocket y la respuesta del POST son dos canales que se cruzan, así que
   * un paquete de la pieza ANTERIOR puede llegar mientras entra la nueva. Lo que
   * los distingue es el `arranque` que el servidor etiqueta en cada estado; el
   * número de notas no vale, y este es justo el caso que lo demuestra: las dos
   * piezas tienen tres notas, así que una comparación de totales las confunde.
   *
   * No es un caso raro: es tocar dos veces la misma escala, o recargar la pieza
   * después de terminarla. Y lo que se veía era un fotograma de salida falsa
   * —«Pieza terminada», el contador y el resumen de la anterior sobre una pieza
   * que acaba de empezar—.
   */
  it("un paquete de la pieza anterior no entra, aunque tenga las mismas notas", async () => {
    const pendiente: { responder?: (respuesta: Response) => void } = {};
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const direccion = String(url);
        if (direccion.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (direccion.includes("/api/perfiles")) return responder(PERFILES);
        if (direccion.includes("/api/piezas/iniciar")) {
          return new Promise<Response>((cumplir) => {
            pendiente.responder = cumplir;
          });
        }
        return responder(ESTADO_APAGADO);
      })
    );

    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    await waitFor(() => expect(pendiente.responder).toBeDefined());

    // La pieza anterior, de tres notas como la nueva, ya terminada.
    enviarEstado({
      arranque: ARRANQUE_ANTERIOR,
      instante_s: 9.0,
      indice_actual: 3,
      total: 3,
      completado: true,
      pausado: false,
      tocadas: [
        { indice: 2, midi: 52, cents: 0, desfase_s: 0, clasificacion: "a_tiempo", acertada: true,
          afinada: true },
      ],
    });

    await act(async () => {
      pendiente.responder!({
        ok: true,
        status: 200,
        json: () => Promise.resolve(RESPUESTA_INICIAR),
      } as Response);
    });

    expect(screen.queryByText(/pieza terminada/i)).toBeNull();
    expect(screen.queryByText(/notas acertadas/i)).toBeNull();
    expect(screen.queryByText(/a tiempo/i)).toBeNull();
    // La pieza nueva, en su primer cuadro y con el lienzo puesto.
    expect(screen.getByTestId("lienzo-carril")).toBeTruthy();
    expect(screen.getByText("0 / 3")).toBeTruthy();
  });

  /**
   * El otro cruce de los dos canales: un paquete que el servidor emitió ANTES del
   * arranque puede llegar por el socket DESPUÉS de la respuesta del POST. No hay
   * orden de llegada que lo detecte; la etiqueta sí.
   */
  it("un paquete viejo que llega tarde tampoco entra, y el bueno sí", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    await pulsarEmpezar();

    enviarEstado({
      arranque: ARRANQUE_ANTERIOR,
      instante_s: 9.0,
      indice_actual: 3,
      total: 3,
      completado: true,
      pausado: false,
      tocadas: [
        { indice: 2, midi: 52, cents: 0, desfase_s: 0, clasificacion: "a_tiempo", acertada: true,
          afinada: true },
      ],
    });
    expect(screen.queryByText(/pieza terminada/i)).toBeNull();

    // Y la guarda no rechaza todo: el paquete de esta pieza sí mueve el contador.
    enviarEstado({
      instante_s: 1.0,
      indice_actual: 1,
      total: 3,
      completado: false,
      pausado: false,
      tocadas: [],
    });
    expect(screen.getByText("1 / 3")).toBeTruthy();
  });

  it("la familia que viaja es la que publica el servidor", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    // La primera familia del catálogo es `arpegio`, no `escala`.
    await waitFor(() => expect(screen.getByText("Arpegios")).toBeTruthy());
    await pulsarEmpezar();
    expect(cuerpoDeIniciar(fetchFalso).familia).toBe("arpegio");
  });

  /**
   * Y si el catálogo todavía no ha llegado, no se inventa ninguna familia: viaja
   * vacía y el servidor contesta cuáles hay. Una clave escrita en la interfaz
   * sobreviviría a su desaparición del catálogo, y entonces lo que se ve
   * seleccionado y lo que viaja en el POST dejarían de coincidir.
   */
  it("sin catálogo todavía no se inventa una familia", async () => {
    const fetchFalso = vi.fn((url: string) => {
      const direccion = String(url);
      // El catálogo no contesta nunca en esta prueba.
      if (direccion.includes("/api/ejercicios/familias")) return new Promise<Response>(() => {});
      if (direccion.includes("/api/perfiles")) return responder(PERFILES);
      if (direccion.includes("/api/piezas/iniciar")) return responder(RESPUESTA_INICIAR);
      return responder(ESTADO_APAGADO);
    });
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    await pulsarEmpezar();
    expect(cuerpoDeIniciar(fetchFalso).familia).toBe("");
  });

  it("avisa mientras el WebSocket no conecta, y calla al conectar", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    await pulsarEmpezar();
    expect(screen.getByText(/sin conexión/i)).toBeTruthy();

    act(() => {
      WebSocketFalso.ultimo!.onopen?.();
    });
    expect(screen.queryByText(/sin conexión/i)).toBeNull();
  });

  /**
   * El cabezal no retrocede NUNCA, ni los tres píxeles de entrar en pausa.
   *
   * Entre dos paquetes el reloj interpola, así que cuando llega la pausa el
   * cabezal va por delante del último instante que mandó el servidor (hasta
   * 33 ms). Congelar en el valor del servidor lo haría retroceder justo ahí, y
   * que no retroceda es la única garantía por la que `relojCarril` existe.
   *
   * Se prueba sobre el hook porque es donde vive el reloj: en jsdom no hay canvas
   * y el cabezal no se puede leer de la pantalla.
   */
  it("al entrar en pausa el cabezal se congela en lo último que se pintó", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    vi.spyOn(performance, "now").mockReturnValue(1000);

    const { result } = renderHook(() => useCarril());
    await act(async () => {
      await result.current.iniciar({ familia: "escala", parametros: {} });
    });

    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 1.0 }));
    });
    // 30 ms después del paquete: el reloj ya ha interpolado por delante de 1,0.
    const pintado = result.current.instante(1030);
    expect(pintado).toBeGreaterThan(1.0);

    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 1.0, pausado: true }));
    });
    expect(result.current.instante(1040)).toBe(pintado);
  });

  /**
   * El quinto camino del hueco de 30 s: el reloj del navegador.
   *
   * Los tres tapones del hueco son del servidor; aquí no había ninguno.
   * `relojCarril` interpola sin techo —`sincronizar(2.0)` y 30 s sin un solo
   * paquete dan 32.0—, y eso es correcto mientras el servidor siga contando. Deja
   * de serlo cuando el servidor se pausa por falta de señal: su instante está
   * parado a propósito, y congelar lo interpolado dejaba el cabezal en el segundo
   * 32 de una pieza que va por el 2; al volver la señal, el carril retrocedía
   * esos 30 s, que es lo único declarado intolerable.
   */
  it("al pausar, el cabezal no se congela más de un techo por delante del servidor", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    vi.spyOn(performance, "now").mockReturnValue(1000);

    const { result } = renderHook(() => useCarril());
    await act(async () => {
      await result.current.iniciar({ familia: "escala", parametros: {} });
    });

    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 2.0 }));
    });
    // El WebSocket se cae (o el portátil se suspende) y pasan 30 s sin paquetes:
    // el reloj sigue interpolando y pinta el segundo 32 de la pieza.
    expect(result.current.instante(31000)).toBeCloseTo(32.0, 1);

    // Vuelve el canal, pero el servidor está pausado por falta de señal: su
    // instante sigue donde estaba. El cabezal se congela ahí, no en el 32.
    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 2.1, pausado: true }));
    });
    expect(result.current.instante(31000)).toBeCloseTo(2.2, 5);
  });

  /**
   * Y el cabezal pintado se suelta al sustituir el reloj, no solo al iniciar otra
   * pieza: el piso de no-retroceso vive dentro de la instancia del reloj, así que
   * cuando `relojCaduco` la tira, lo que pintó deja de describir nada.
   */
  it("el cabezal pintado no sobrevive al reloj que lo pintó", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    vi.spyOn(performance, "now").mockReturnValue(1000);

    const { result } = renderHook(() => useCarril());
    await act(async () => {
      await result.current.iniciar({ familia: "escala", parametros: {} });
    });

    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 2.0 }));
    });
    // 30 s sin paquetes: el reloj viejo pinta el segundo 32.
    expect(result.current.instante(31000)).toBeCloseTo(32.0, 1);
    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 2.1, pausado: true }));
    });
    // Congelado en 2,2: el techo sobre lo que el reloj viejo llegó a pintar.
    expect(result.current.instante(31000)).toBeCloseTo(2.2, 5);

    // Vuelve la señal (reloj nuevo) y se va otra vez sin que se haya pintado un
    // solo cuadro con él. Lo único que describe la pieza es el instante del
    // servidor; el 2,2 del reloj anterior ya no cuenta.
    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 2.1 }));
    });
    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 2.15, pausado: true }));
    });
    expect(result.current.instante(1000)).toBeCloseTo(2.15, 5);
  });

  /**
   * Y el cabezal congelado no se hereda: es del arranque que lo congeló. Sin
   * soltarlo al iniciar, una pieza nueva pausada se quedaría clavada en el
   * instante de la anterior, que puede estar minutos por delante.
   */
  it("una pieza nueva no hereda el cabezal congelado de la anterior", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    vi.spyOn(performance, "now").mockReturnValue(1000);

    const { result } = renderHook(() => useCarril());
    await act(async () => {
      await result.current.iniciar({ familia: "escala", parametros: {} });
    });
    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 5.0, pausado: true }));
    });
    expect(result.current.instante(1000)).toBe(5.0);

    await act(async () => {
      await result.current.iniciar({ familia: "escala", parametros: {} });
    });
    act(() => {
      WebSocketFalso.ultimo!.enviar(enCurso({ instante_s: 0.5, pausado: true }));
    });
    expect(result.current.instante(1000)).toBe(0.5);
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
