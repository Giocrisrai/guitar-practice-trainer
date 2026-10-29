import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Carril } from "./Carril";
import { useCarril } from "./useCarril";
import type { EstadoEstudio, RespuestaIniciarEstudio } from "./tiposEstudio";
import type { EstadoCarril, NotaTocada, Pieza } from "./tiposPieza";

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
  secciones: [], ritmo_aproximado: false, tempo_variable: false, compas_variable: false, casillas_de_repeticion: false,
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

/** Lo que el estado de la pasada añade al del carril, en una pasada sin tocar:
 * pieza entera, a tempo escrito, sin bucle, sin pausa (el plan por defecto). */
const ESTUDIO_BASE = {
  instante_pulsos: 0, compas_en_curso: 1, total_de_compases: 1, primer_compas: 1,
  ultimo_compas: 1, repeticion: 1, cuenta_atras_restante_s: 0, factor_tempo: 1,
  tempo_efectivo: 60, en_bucle: false, con_click: false, tempo_automatico: false,
  en_pausa: false, compas_variable: false,
  ritmo_aproximado: false, tramo_terminado: false, click_sonando: false,
  factor_sugerido: null,
};

/** El carril apagado: las mismas claves que con pieza (`_CARRIL_APAGADO`). */
const ESTADO_APAGADO: EstadoEstudio = {
  ...ESTUDIO_BASE,
  arranque: 0,
  instante_s: 0,
  indice_actual: 0,
  total: 0,
  completado: false,
  tocadas: [],
  pausado: false,
};

/** Lo que devuelve `POST /api/piezas/iniciar`: la pieza entera y el estado inicial. */
const RESPUESTA_INICIAR: RespuestaIniciarEstudio = {
  ...ESTUDIO_BASE,
  secciones_en_compases: [],
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
function enCurso(cambios: Partial<EstadoEstudio> = {}): EstadoEstudio {
  return {
    ...ESTUDIO_BASE,
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

  /**
   * El resumen es la pantalla que el alumno mira al terminar, y no decia que nota
   * habia salido mal: todas las filas llevaban el nombre PEDIDO, asi que debajo
   * de «1 de 3 notas acertadas» venian tres lineas que no se distinguian en lo
   * que importa. El color del punto es la desviacion en cents, que es otra cosa.
   */
  it("el resumen dice qué nota salió mal y cuál era la pedida", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    enviarEstado({
      instante_s: 4.0, indice_actual: 2, total: 3, completado: true, pausado: false,
      tocadas: [
        { indice: 0, midi: 40, nombre: "E2", cents: 0, desfase_s: 0.01,
          clasificacion: "a_tiempo", acertada: true, afinada: true },
        // La nota 1 pedia A2 (MIDI 45) y sonó A#2: fallada, y bien afinada.
        { indice: 1, midi: 46, nombre: "A#2", cents: 1.0, desfase_s: 0.02,
          clasificacion: "a_tiempo", acertada: false, afinada: true },
      ],
    });
    expect(await screen.findByText(/1 de 3 notas acertadas/i)).toBeTruthy();
    expect(screen.getByText(/Pedida A2, tocaste A#2/)).toBeTruthy();
    expect(screen.getAllByTestId("fila-fallada")).toHaveLength(1);
    expect(screen.getAllByTestId("fila-acertada")).toHaveLength(1);
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
    // La primera nota de tres: el contador es una CUENTA, no el indice.
    expect(screen.getByText("1 / 3")).toBeTruthy();
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
    expect(screen.getByText("2 / 3")).toBeTruthy();
  });

  /**
   * Cambiar la afinación con una pieza en marcha detiene el carril en el servidor
   * (spec §7: dibujar trastes que tu instrumento no tiene es peor que no dibujar
   * nada). El navegador se enteraba por ningún sitio: el estado del carril
   * apagado llega con `arranque: 0` y la guarda de `recibir` lo descartaba como
   * un paquete ajeno, así que la pantalla seguía con su contador y su lienzo
   * puestos, sin un solo aviso, sobre una pieza que ya no existía.
   */
  it("un carril apagado desde el servidor termina la pieza y lo dice", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    await pulsarEmpezar();

    enviarEstado({
      instante_s: 1.0, indice_actual: 1, total: 3, completado: false, pausado: false,
      tocadas: [],
    });
    expect(screen.getByText("2 / 3")).toBeTruthy();

    act(() => {
      WebSocketFalso.ultimo!.enviar(ESTADO_APAGADO);
    });

    expect(screen.queryByText("2 / 3")).toBeNull();
    expect(screen.queryByTestId("lienzo-carril")).toBeNull();
    expect(screen.getByText(/se detuvo desde el servidor/i)).toBeTruthy();
    expect(screen.getByText(/cambiar de afinación/i)).toBeTruthy();
    // Y se puede volver a empezar: la pantalla es la de elegir pieza.
    expect(screen.getByRole("button", { name: /empezar/i })).toBeTruthy();
  });

  /**
   * Los dos paquetes de carril apagado son indistinguibles por su contenido: el
   * de antes de empezar y el de haberse apagado ya llevan los dos `arranque: 0`.
   * Lo que los separa es el orden del socket, que entrega en orden: uno que llega
   * ANTES del primer paquete de nuestra pieza puede ser del rato anterior al
   * arranque -el carril apagado emite treinta veces por segundo- y no puede
   * tumbar la pieza que se acaba de pedir.
   */
  it("un apagado anterior al primer paquete de la pieza no la tumba", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    await pulsarEmpezar();

    act(() => {
      WebSocketFalso.ultimo!.enviar(ESTADO_APAGADO);
    });

    expect(screen.queryByText(/se detuvo desde el servidor/i)).toBeNull();
    expect(screen.getByTestId("lienzo-carril")).toBeTruthy();
    expect(screen.getByText("1 / 3")).toBeTruthy();
  });

  /**
   * El contador pintaba `indice_actual`, que es un INDICE (base 0), como si fuera
   * una cuenta: en la ultima nota de una pieza de tres se leia «2 / 3», y en una
   * de doce, «11 / 12».
   */
  it("en la última nota el contador llega al total", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    await pulsarEmpezar();

    enviarEstado({
      instante_s: 2.5, indice_actual: 2, total: 3, completado: false, pausado: false,
      tocadas: [],
    });
    expect(screen.getByText("3 / 3")).toBeTruthy();
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
   * La otra puerta al carril: una canción que ya viene elegida de `Canciones`.
   *
   * Quien PIDE la pieza tiene que ser quien la DIBUJA, porque la pieza entera viaja
   * una sola vez en la respuesta de `/iniciar` y el WebSocket no la repite. Así que
   * el traspaso no puede ser «arranca tú y yo te enseño»: llega la petición y la
   * arranca esta pantalla.
   */
  it("arranca la cancion que le pasan, y manda la pista que le dijeron", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril peticion={{ cancion: "x.gp5", pista: 2, perfil: null }} />);

    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();
    // La pieza no viaja desde aquí: viaja qué canción y qué pista, y en base 1.
    expect(cuerpoDeIniciar(fetchFalso)).toEqual({
      cancion: "x.gp5",
      pista: 2,
      perfil: null,
    });
  });

  /**
   * Y UNA SOLA vez, aunque la petición vuelva a llegar.
   *
   * `detener` deja otra vez la pieza en `null`, y quien pasa la petición puede
   * escribirla en el JSX en vez de guardarla en estado, así que cada render trae un
   * objeto nuevo con el mismo contenido. Sin la marca de «ya pedida», esas dos cosas
   * juntas vuelven a lanzar el POST: la canción se rearranca sola después de
   * detenerla, en bucle.
   */
  it("no vuelve a arrancar la cancion aunque la peticion llegue otra vez", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    const { rerender } = render(
      <Carril peticion={{ cancion: "x.gp5", pista: 1, perfil: null }} />
    );
    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();

    await act(async () => {
      screen.getByRole("button", { name: /detener/i }).click();
    });
    await act(async () => {
      rerender(<Carril peticion={{ cancion: "x.gp5", pista: 1, perfil: null }} />);
    });

    expect(
      fetchFalso.mock.calls.filter(([url]) => url === "/api/piezas/iniciar")
    ).toHaveLength(1);
  });

  /** Mientras el POST está en vuelo no se ofrece el configurador de ejercicios: el
   * usuario eligió una canción y un selector de escalas le haría creer que se
   * perdió su elección. */
  it("mientras la cancion llega no ofrece elegir un ejercicio", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const direccion = String(url);
        if (direccion.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (direccion.includes("/api/perfiles")) return responder(PERFILES);
        if (direccion.includes("/api/piezas/iniciar")) return new Promise<Response>(() => {});
        return responder(ESTADO_APAGADO);
      })
    );
    render(<Carril peticion={{ cancion: "x.gp5", pista: 1, perfil: null }} />);

    expect(await screen.findByText(/preparando la canción/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /empezar/i })).toBeNull();
  });

  /** Y si el carril la rechaza -la afinación de la canción no es la activa- se dice
   * el motivo y se vuelve a ofrecer el configurador, que es la salida que queda. */
  it("si el carril rechaza la cancion dice el motivo y deja elegir otra cosa", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const direccion = String(url);
        if (direccion.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (direccion.includes("/api/perfiles")) return responder(PERFILES);
        if (direccion.includes("/api/piezas/iniciar")) {
          return responder({ detail: "la pieza esta escrita en guitarra_drop_d" }, false, 400);
        }
        return responder(ESTADO_APAGADO);
      })
    );
    render(<Carril peticion={{ cancion: "drop.txt", pista: 1, perfil: null }} />);

    expect(
      await screen.findByText("la pieza esta escrita en guitarra_drop_d")
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: /empezar/i })).toBeTruthy();
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

/**
 * El carril dibuja con el tempo EFECTIVO, no con el escrito.
 *
 * Al 50 % el reloj del servidor corre estirado: cada pulso dura el doble. Si el
 * dibujo convirtiera los pulsos con el tempo escrito, las notas viajarían al doble
 * de velocidad que el reloj. Aquí sí hay lienzo: jsdom no lo trae, así que se le
 * pone un contexto falso que apunta cada `fillRect`, y de ahí se lee en qué carril
 * (cuerda) cayó cada nota visible.
 */
describe("Carril: el dibujo sigue al tempo efectivo", () => {
  // Tempo escrito 60: un pulso es un segundo. Al 50 % (tempo efectivo 30) es dos.
  const PIEZA_LARGA: Pieza = {
    ...PIEZA,
    duracion_pulsos: 13,
    notas: [
      { midi: 64, nombre: "E4", cuerda: 1, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
      { midi: 59, nombre: "B3", cuerda: 2, traste: 0, inicio_pulsos: 3, duracion_pulsos: 1 },
      { midi: 55, nombre: "G3", cuerda: 3, traste: 0, inicio_pulsos: 6, duracion_pulsos: 1 },
      { midi: 50, nombre: "D3", cuerda: 4, traste: 0, inicio_pulsos: 12, duracion_pulsos: 1 },
    ],
  };
  const ANCHO = 600; // seis cuerdas: un carril de 100 px cada una
  const MARGEN = 5; // el hueco a cada lado que deja el carril (MARGEN_CARRIL_PX)

  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    delete (HTMLCanvasElement.prototype as { clientWidth?: number }).clientWidth;
    delete (HTMLCanvasElement.prototype as { clientHeight?: number }).clientHeight;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /** Monta el carril con lienzo "de verdad", manda un paquete en el segundo 4 y
   * devuelve `[x, y de la esquina superior, alto]` de cada nota pintada en ese cuadro,
   * con la `x` ya sin el margen del carril. */
  async function carrilesPintados(paquete: Record<string, unknown>): Promise<number[][]> {
    const fetchFalso = vi.fn((url: string) => {
      const direccion = String(url);
      if (direccion.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
      if (direccion.includes("/api/perfiles")) return responder(PERFILES);
      if (direccion.includes("/api/piezas/iniciar")) {
        return responder({ ...RESPUESTA_INICIAR, pieza: PIEZA_LARGA, total: 4 });
      }
      return responder(ESTADO_APAGADO);
    });
    vi.stubGlobal("fetch", fetchFalso);

    const rectangulos: number[][] = [];
    const contexto = {
      setTransform: vi.fn(),
      fillRect: vi.fn((x: number, y: number, ancho: number, alto: number) => {
        rectangulos.push([x, y, ancho, alto]);
      }),
      fillText: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
    };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(contexto as never);
    Object.defineProperty(HTMLCanvasElement.prototype, "clientWidth", {
      configurable: true,
      get: () => ANCHO,
    });
    Object.defineProperty(HTMLCanvasElement.prototype, "clientHeight", {
      configurable: true,
      get: () => 500,
    });
    const cuadros: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      cuadros.push(callback);
      return cuadros.length;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());

    render(<Carril />);
    await pulsarEmpezar();
    await waitFor(() => expect(cuadros.length).toBeGreaterThan(0));
    enviarEstado({ ...enCurso({ instante_s: 4, total: 4 }), ...paquete });

    rectangulos.length = 0;
    act(() => {
      cuadros[cuadros.length - 1](performance.now());
    });
    // El primer `fillRect` de un cuadro es el fondo; las notas vienen después.
    const [fondo, ...notas] = rectangulos;
    expect(fondo).toEqual([0, 0, ANCHO, 500]);
    return notas.map(([x, y, , alto]) => [x - MARGEN, y, alto]);
  }

  it("al 50 % las notas visibles son las del reloj estirado, no las del tempo escrito", async () => {
    // Segundo 4 con un pulso de 2 s: es el pulso 2. Se ve la nota del pulso 3
    // (cuerda 2) y nada más: la del pulso 6 empieza en el segundo 12, fuera de la
    // ventana de 4 s. Con el tempo escrito (60) se verían también la del pulso 6.
    const carriles = await carrilesPintados({ factor_tempo: 0.5, tempo_efectivo: 30 });
    expect(carriles.map(([x]) => x)).toEqual([100]);
    // Y la geometría, no solo la selección: 100 px por segundo y la línea de ataque
    // en el 400. La nota empieza 2 s después del instante (pulso 3 a 2 s por pulso
    // son 6 s, menos los 4 s) y dura 2 s. Con el tempo escrito saldría ya pasada
    // (y = 500) y de 100 px de alto.
    const [, arriba, alto] = carriles[0];
    expect(alto).toBe(200);
    expect(Math.abs(arriba + alto - 200)).toBeLessThan(10);
  });

  it("sin tempo efectivo en el paquete se usa el de la pieza", async () => {
    // El mismo instante, pero a 60: las notas de los pulsos 3 y 6 caen dentro.
    // `undefined` no viaja en el JSON: el paquete llega SIN `tempo_efectivo`.
    const carriles = await carrilesPintados({ tempo_efectivo: undefined });
    expect(carriles.map(([x]) => x)).toEqual([100, 200]);
  });

  it("un tempo efectivo de 0, el del carril apagado, no rompe el dibujo ni lo vacía", async () => {
    const carriles = await carrilesPintados({ tempo_efectivo: 0 });
    expect(carriles.map(([x]) => x)).toEqual([100, 200]);
  });
});

describe("Carril: los controles de la pasada", () => {
  const SECCIONES = [{ nombre: "Intro", primer_compas: 1, ultimo_compas: 2 }];

  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /** Un fetch que además contesta a las tres órdenes; `rechazo` hace que fallen. */
  function fetchConOrdenes(rechazo: string | null = null) {
    return vi.fn((url: string) => {
      const direccion = String(url);
      if (direccion.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
      if (direccion.includes("/api/perfiles")) return responder(PERFILES);
      if (direccion.includes("/api/piezas/iniciar")) {
        return responder({
          ...RESPUESTA_INICIAR, total_de_compases: 4, ultimo_compas: 4,
          secciones_en_compases: SECCIONES,
        });
      }
      if (/\/api\/piezas\/(plan|saltar|pausa)$/.test(direccion)) {
        return rechazo === null
          ? responder(ESTADO_APAGADO)
          : responder({ detail: rechazo }, false, 400);
      }
      return responder(ESTADO_APAGADO);
    });
  }

  /** El cuerpo de la última orden enviada a esa ruta, ya parseado. */
  function cuerpoDe(fetchFalso: ReturnType<typeof vi.fn>, ruta: string): unknown {
    const llamadas = fetchFalso.mock.calls.filter(([url]) => url === ruta);
    expect(llamadas.length).toBeGreaterThan(0);
    return JSON.parse(String((llamadas[llamadas.length - 1][1] as RequestInit).body));
  }

  async function montarEnMarcha(fetchFalso: ReturnType<typeof vi.fn>) {
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    await pulsarEmpezar();
    await screen.findByRole("button", { name: "Pausar" });
  }

  it("las secciones de la respuesta de iniciar llegan a la lista", async () => {
    await montarEnMarcha(fetchConOrdenes());
    const lista = screen.getByLabelText("Sección") as HTMLSelectElement;
    expect(Array.from(lista.options).map((o) => o.textContent)).toEqual([
      "Elige una sección",
      "Intro (compases 1-2)",
    ]);
  });

  it("pausar manda la pausa explícita al servidor", async () => {
    const fetchFalso = fetchConOrdenes();
    await montarEnMarcha(fetchFalso);
    await act(async () => {
      screen.getByRole("button", { name: "Pausar" }).click();
    });
    expect(cuerpoDe(fetchFalso, "/api/piezas/pausa")).toEqual({ activa: true });
  });

  it("reanudar manda la pausa en falso", async () => {
    const fetchFalso = fetchConOrdenes();
    await montarEnMarcha(fetchFalso);
    enviarEstado(enCurso({ en_pausa: true }));
    await act(async () => {
      screen.getByRole("button", { name: "Reanudar" }).click();
    });
    expect(cuerpoDe(fetchFalso, "/api/piezas/pausa")).toEqual({ activa: false });
  });

  it("el tempo que se suelta llega al servidor como parche", async () => {
    const fetchFalso = fetchConOrdenes();
    await montarEnMarcha(fetchFalso);
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Tempo"), { target: { value: "70" } });
      fireEvent.pointerUp(screen.getByLabelText("Tempo"));
    });
    expect(cuerpoDe(fetchFalso, "/api/piezas/plan")).toEqual({ factor_tempo: 0.7 });
  });

  it("un clic fuera del tramo manda el plan y luego el salto, al servidor", async () => {
    const fetchFalso = fetchConOrdenes();
    await montarEnMarcha(fetchFalso);
    // El tramo pasa a ser 1-2 (el servidor lo dice por el WebSocket).
    enviarEstado(enCurso({ total_de_compases: 4, primer_compas: 1, ultimo_compas: 2 }));
    await act(async () => {
      screen.getByRole("button", { name: "Compás 4" }).click();
    });
    await waitFor(() =>
      expect(fetchFalso.mock.calls.some(([url]) => url === "/api/piezas/saltar")).toBe(true),
    );
    const rutas = fetchFalso.mock.calls
      .map(([url]) => url)
      .filter((url) => /\/api\/piezas\/(plan|saltar)$/.test(String(url)));
    expect(rutas).toEqual(["/api/piezas/plan", "/api/piezas/saltar"]);
    expect(cuerpoDe(fetchFalso, "/api/piezas/plan")).toMatchObject({
      primer_compas: 3, ultimo_compas: 4,
    });
    expect(cuerpoDe(fetchFalso, "/api/piezas/saltar")).toEqual({ compas: 4 });
  });

  it("si el servidor rechaza una orden, el motivo se ve y no hay salto", async () => {
    const fetchFalso = fetchConOrdenes("El tempo tiene que estar entre el 40% y el 100%");
    await montarEnMarcha(fetchFalso);
    enviarEstado(enCurso({ total_de_compases: 4, primer_compas: 1, ultimo_compas: 2 }));
    await act(async () => {
      screen.getByRole("button", { name: "Compás 4" }).click();
    });
    expect((await screen.findByText(/El tempo tiene que estar/)).className).toBe("error-ejercicio");
    expect(fetchFalso.mock.calls.some(([url]) => url === "/api/piezas/saltar")).toBe(false);
  });

  it("sin señal NO es pausa del usuario: el aviso es uno y el botón sigue en «Pausar»", async () => {
    await montarEnMarcha(fetchConOrdenes());
    enviarEstado(enCurso({ pausado: true, en_pausa: false }));
    expect(screen.getByText(/no llega señal del cable/)).toBeDefined();
    expect(screen.getByRole("button", { name: "Pausar" })).toBeDefined();
    expect(screen.queryByText(/En pausa/)).toBeNull();
  });

  it("la pausa del usuario NO es falta de señal: no sale el aviso del cable", async () => {
    await montarEnMarcha(fetchConOrdenes());
    enviarEstado(enCurso({ pausado: false, en_pausa: true }));
    expect(screen.getByRole("button", { name: "Reanudar" })).toBeDefined();
    expect(screen.getByText(/En pausa/)).toBeDefined();
    expect(screen.queryByText(/no llega señal del cable/)).toBeNull();
  });
});

describe("useCarril: las órdenes de la pasada", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("cada orden va a su ruta con su cuerpo, y devuelve que fue aceptada", async () => {
    const fetchFalso = vi.fn((_url: string, _opciones?: RequestInit) => responder({}));
    vi.stubGlobal("fetch", fetchFalso);
    const { result } = renderHook(() => useCarril());
    let resultados: boolean[] = [];
    await act(async () => {
      resultados = [
        await result.current.cambiarPlan({ factor_tempo: 0.5 }),
        await result.current.saltar(3),
        await result.current.pausar(false),
      ];
    });
    expect(resultados).toEqual([true, true, true]);
    expect(
      // La lectura de la pieza en marcha al montar no es una orden.
      fetchFalso.mock.calls.filter(([url]) => url !== "/api/piezas/pieza").map(([url, opciones]) => [
        url,
        opciones?.method,
        JSON.parse(String(opciones?.body)),
      ]),
    ).toEqual([
      ["/api/piezas/plan", "POST", { factor_tempo: 0.5 }],
      ["/api/piezas/saltar", "POST", { compas: 3 }],
      ["/api/piezas/pausa", "POST", { activa: false }],
    ]);
    expect(result.current.error).toBeNull();
  });

  it("al detener la pieza las secciones se van con ella", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        responder(
          String(url).includes("/iniciar")
            ? { ...RESPUESTA_INICIAR, secciones_en_compases: [{ nombre: "A", primer_compas: 1, ultimo_compas: 1 }] }
            : {},
        ),
      ),
    );
    const { result } = renderHook(() => useCarril());
    await act(async () => {
      await result.current.iniciar({ familia: "escala", parametros: {} });
    });
    expect(result.current.secciones).toHaveLength(1);
    await act(async () => {
      await result.current.detener();
    });
    expect(result.current.secciones).toEqual([]);
  });

  it("un 400 devuelve false y deja el motivo del servidor en error", async () => {
    vi.stubGlobal("fetch", vi.fn(() => responder({ detail: "El compas 9 no esta" }, false, 400)));
    const { result } = renderHook(() => useCarril());
    let aceptada = true;
    await act(async () => {
      aceptada = await result.current.saltar(9);
    });
    expect(aceptada).toBe(false);
    expect(result.current.error).toBe("El compas 9 no esta");
  });

  it("una orden aceptada limpia el error de la anterior", async () => {
    const respuestas = [responder({ detail: "mal" }, false, 400), responder({})];
    // La lectura de la pieza en marcha al montar no es una orden: no gasta una respuesta.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => (url === "/api/piezas/pieza" ? responder({}) : respuestas.shift()!)),
    );
    const { result } = renderHook(() => useCarril());
    await act(async () => {
      await result.current.pausar(true);
    });
    expect(result.current.error).toBe("mal");
    await act(async () => {
      await result.current.pausar(false);
    });
    expect(result.current.error).toBeNull();
  });

  it("si no hay red devuelve false y lo dice en error, sin lanzar", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("sin red"))));
    const { result } = renderHook(() => useCarril());
    let aceptada = true;
    await act(async () => {
      aceptada = await result.current.cambiarPlan({});
    });
    expect(aceptada).toBe(false);
    expect(result.current.error).toBe("sin red");
  });
});

/** Las rutas a las que se llamó, en orden. */
function rutas(fetchFalso: ReturnType<typeof vi.fn>): string[] {
  return fetchFalso.mock.calls.map(([url]) => String(url));
}

/** Un `fetch` que contesta con lo que se le dé a cada ruta, y {} al resto. */
function fetchCon(respuestas: Record<string, unknown>) {
  return vi.fn((url: string, _opciones?: RequestInit) => {
    const ruta = String(url);
    if (ruta in respuestas) return responder(respuestas[ruta]);
    if (ruta.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
    if (ruta.includes("/api/perfiles")) return responder(PERFILES);
    if (ruta.includes("/api/piezas/iniciar")) return responder(RESPUESTA_INICIAR);
    return responder({});
  });
}

describe("Carril: recargar el navegador y desmontar", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("pide la pieza en marcha al montar y la dibuja, para quien recargó el navegador", async () => {
    // La pieza viaja una sola vez en la respuesta de iniciar: sin esto, recargar
    // a mitad de cancion dejaba el carril en blanco.
    const fetchFalso = fetchCon({
      "/api/piezas/pieza": {
        ...RESPUESTA_INICIAR,
        pieza: { ...PIEZA, nombre: "Una pieza que ya sonaba" },
      },
    });
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    expect(await screen.findByText("Una pieza que ya sonaba")).toBeTruthy();
    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();
    // Y no se arrancó nada: solo se leyó.
    expect(rutas(fetchFalso)).not.toContain("/api/piezas/iniciar");
  });

  it("los paquetes de la pieza recuperada entran, porque adoptó su arranque", async () => {
    vi.stubGlobal("fetch", fetchCon({ "/api/piezas/pieza": RESPUESTA_INICIAR }));
    render(<Carril />);
    await screen.findByTestId("lienzo-carril");
    enviarEstado(enCurso({ indice_actual: 2 }));
    expect(screen.getByText("3 / 3")).toBeTruthy();
  });

  it("si no hay nada en marcha se queda con el configurador", async () => {
    const fetchFalso = fetchCon({ "/api/piezas/pieza": { ...ESTADO_APAGADO, pieza: null } });
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    await waitFor(() => expect(rutas(fetchFalso)).toContain("/api/piezas/pieza"));
    await act(async () => {});
    expect(screen.getByRole("button", { name: /empezar/i })).toBeTruthy();
    expect(screen.queryByTestId("lienzo-carril")).toBeNull();
  });

  it("si la lectura falla, el carril arranca vacío y no revienta", async () => {
    const fetchFalso = vi.fn((url: string) =>
      String(url) === "/api/piezas/pieza"
        ? Promise.reject(new Error("sin red"))
        : responder(FAMILIAS),
    );
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    await waitFor(() => expect(rutas(fetchFalso)).toContain("/api/piezas/pieza"));
    await act(async () => {});
    expect(screen.getByRole("button", { name: /empezar/i })).toBeTruthy();
  });

  it("quien llega con una pieza pedida (desde Canciones) no la vuelve a pedir", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril peticion={{ cancion: "x.gp5", pista: 1, perfil: null }} />);
    // La positiva: la pieza se arrancó y se dibuja; la lectura habría salido ya.
    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();
    expect(rutas(fetchFalso)).toContain("/api/piezas/iniciar");
    expect(rutas(fetchFalso)).not.toContain("/api/piezas/pieza");
  });

  it("una lectura que llega tarde no pisa la pieza que se arrancó mientras tanto", async () => {
    let contestarLaLectura: (cuerpo: unknown) => void = () => {};
    const fetchFalso = vi.fn((url: string) => {
      const ruta = String(url);
      if (ruta === "/api/piezas/pieza") {
        return new Promise<Response>((resolver) => {
          contestarLaLectura = (cuerpo) =>
            resolver({ ok: true, status: 200, json: () => Promise.resolve(cuerpo) } as Response);
        });
      }
      if (ruta.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
      if (ruta.includes("/api/perfiles")) return responder(PERFILES);
      if (ruta.includes("/api/piezas/iniciar")) return responder(RESPUESTA_INICIAR);
      return responder({});
    });
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    await pulsarEmpezar();
    expect(await screen.findByText("Escala de Do mayor")).toBeTruthy();

    await act(async () => {
      contestarLaLectura({
        ...RESPUESTA_INICIAR,
        arranque: ARRANQUE_ANTERIOR,
        pieza: { ...PIEZA, nombre: "La de antes" },
      });
    });
    expect(screen.getByText("Escala de Do mayor")).toBeTruthy();
    expect(screen.queryByText("La de antes")).toBeNull();
  });

  it("detiene la pieza al desmontar, o el click se queda sonando", async () => {
    const fetchFalso = fetchCon({});
    vi.stubGlobal("fetch", fetchFalso);
    const { unmount } = render(<Carril />);
    await act(async () => {});
    expect(rutas(fetchFalso)).not.toContain("/api/piezas/detener");
    unmount();
    await waitFor(() => expect(rutas(fetchFalso)).toContain("/api/piezas/detener"));
    const llamada = fetchFalso.mock.calls.find(([url]) => url === "/api/piezas/detener")!;
    expect((llamada[1] as RequestInit).method).toBe("POST");
  });

  it("cierra el WebSocket ANTES de pedir el detener", async () => {
    // Si el ultimo paquete llegara despues del detener, volveria a pintar una
    // pieza ya detenida.
    const orden: string[] = [];
    class SocketQueApunta extends WebSocketFalso {
      close() {
        orden.push("cerrar");
      }
    }
    vi.stubGlobal("WebSocket", SocketQueApunta);
    const base = fetchCon({});
    const fetchFalso = vi.fn((url: string, opciones?: RequestInit) => {
      if (String(url) === "/api/piezas/detener") orden.push("detener");
      return base(url, opciones);
    });
    vi.stubGlobal("fetch", fetchFalso);
    const { unmount } = render(<Carril />);
    await act(async () => {});
    unmount();
    await waitFor(() => expect(orden).toContain("detener"));
    expect(orden).toEqual(["cerrar", "detener"]);
  });

  it("montar en StrictMode no detiene la pieza que se acaba de pedir", async () => {
    // StrictMode monta, desmonta y vuelve a montar: la limpieza de la primera
    // vez no puede parar la pieza de la segunda.
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(
      <StrictMode>
        <Carril peticion={{ cancion: "x.gp5", pista: 1, perfil: null }} />
      </StrictMode>,
    );
    expect(await screen.findByTestId("lienzo-carril")).toBeTruthy();
    await new Promise((resolver) => setTimeout(resolver, 30));
    expect(rutas(fetchFalso)).not.toContain("/api/piezas/detener");
  });
});

describe("useCarril: machacar y el informe", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /** Las órdenes (POST) que salieron, como [ruta, cuerpo]. */
  function ordenes(fetchFalso: ReturnType<typeof vi.fn>) {
    return fetchFalso.mock.calls
      .filter(([url, opciones]) =>
        (opciones as RequestInit | undefined)?.method === "POST" && url !== "/api/piezas/detener")
      .map(([url, opciones]) => [url, JSON.parse(String((opciones as RequestInit).body))]);
  }

  it("machacar manda primero el plan con el bucle de ese compás y después el salto", async () => {
    const fetchFalso = fetchCon({});
    vi.stubGlobal("fetch", fetchFalso);
    const { result } = renderHook(() => useCarril());
    let aceptada = false;
    await act(async () => {
      aceptada = await result.current.machacar(19);
    });
    expect(aceptada).toBe(true);
    expect(ordenes(fetchFalso)).toEqual([
      ["/api/piezas/plan", { primer_compas: 19, ultimo_compas: 19, en_bucle: true }],
      ["/api/piezas/saltar", { compas: 19 }],
    ]);
  });

  it("si el servidor rechaza el plan no manda el salto, y deja el motivo", async () => {
    const fetchFalso = vi.fn((url: string, _opciones?: RequestInit) =>
      String(url) === "/api/piezas/plan"
        ? responder({ detail: "El compas 19 no existe" }, false, 400)
        : responder({}),
    );
    vi.stubGlobal("fetch", fetchFalso);
    const { result } = renderHook(() => useCarril());
    let aceptada = true;
    await act(async () => {
      aceptada = await result.current.machacar(19);
    });
    expect(aceptada).toBe(false);
    expect(ordenes(fetchFalso).map(([ruta]) => ruta)).toEqual(["/api/piezas/plan"]);
    expect(result.current.error).toBe("El compas 19 no existe");
  });

  it("leerInforme devuelve informe e historial; un 400 da null y deja el motivo", async () => {
    const cuerpo = {
      informe: { compases: [], ritmo_aproximado: false, compas_variable: false, factor_tempo: 1, repeticiones: 1 },
      historial: { pasadas: 2, peores_compases: [] },
    };
    vi.stubGlobal("fetch", vi.fn(() => responder(cuerpo)));
    const { result } = renderHook(() => useCarril(undefined, false));
    let leido: unknown = null;
    await act(async () => {
      leido = await result.current.leerInforme();
    });
    expect(leido).toEqual(cuerpo);

    vi.stubGlobal("fetch", vi.fn(() => responder({ detail: "No hay pieza" }, false, 400)));
    await act(async () => {
      leido = await result.current.leerInforme();
    });
    expect(leido).toBeNull();
    expect(result.current.error).toBe("No hay pieza");
  });
});

describe("Carril: el informe en pantalla", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  const INFORME = {
    informe: {
      compases: [
        {
          numero: 19, notas_escritas: 4, notas_medibles: 4, acertadas: 4, a_tiempo: 2, limpias: 2,
          pronto: 0, tarde: 2, desfase_medio_s: 0.04, tiene_acordes: false,
        },
      ],
      ritmo_aproximado: false, compas_variable: false, factor_tempo: 1, repeticiones: 1,
    },
    historial: { pasadas: 5, peores_compases: [{ compas: 19, falladas: 4, contadas: 5 }] },
  };

  it("ver el informe pide el informe y lo enseña; machacar arma el bucle y salta", async () => {
    const fetchFalso = fetchCon({ "/api/piezas/informe": INFORME });
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril peticion={{ cancion: "x.gp5", pista: 1, perfil: null }} />);
    await screen.findByTestId("lienzo-carril");
    expect(document.querySelector(".informe-pasada")).toBeNull();

    await act(async () => {
      screen.getByRole("button", { name: /ver el informe/i }).click();
    });
    expect(document.querySelector('tr[data-compas="19"] .celda-desfase')!.textContent).toBe(
      "40 ms tarde",
    );

    await act(async () => {
      screen.getByRole("button", { name: "Machacar el compás 19" }).click();
    });
    const posts = fetchFalso.mock.calls
      .filter(([, o]) => (o as RequestInit | undefined)?.method === "POST")
      .map(([url, o]) => [url, JSON.parse(String((o as RequestInit).body ?? "null"))])
      .filter(([url]) => url === "/api/piezas/plan" || url === "/api/piezas/saltar");
    expect(posts).toEqual([
      ["/api/piezas/plan", { primer_compas: 19, ultimo_compas: 19, en_bucle: true }],
      ["/api/piezas/saltar", { compas: 19 }],
    ]);
    // Machacado, el informe viejo se cierra.
    expect(document.querySelector(".informe-pasada")).toBeNull();
  });

  it("el informe de una pieza no sale encima de la siguiente", async () => {
    const arranques = [ARRANQUE_EN_CURSO, ARRANQUE_EN_CURSO + 1];
    const base = fetchCon({ "/api/piezas/informe": INFORME });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, opciones?: RequestInit) =>
        String(url) === "/api/piezas/iniciar"
          ? responder({ ...RESPUESTA_INICIAR, arranque: arranques.shift() })
          : base(url, opciones),
      ),
    );
    render(<Carril />);
    await pulsarEmpezar();
    await screen.findByTestId("lienzo-carril");
    await act(async () => {
      screen.getByRole("button", { name: /ver el informe/i }).click();
    });
    expect(document.querySelector(".informe-pasada")).not.toBeNull();

    await act(async () => {
      screen.getByRole("button", { name: /detener/i }).click();
    });
    await pulsarEmpezar();
    await screen.findByTestId("lienzo-carril");
    expect(screen.getByRole("button", { name: /ver el informe/i })).toBeTruthy();
    expect(document.querySelector(".informe-pasada")).toBeNull();
  });

  it("cerrar el informe lo quita", async () => {
    vi.stubGlobal("fetch", fetchCon({ "/api/piezas/informe": INFORME }));
    render(<Carril peticion={{ cancion: "x.gp5", pista: 1, perfil: null }} />);
    await screen.findByTestId("lienzo-carril");
    await act(async () => {
      screen.getByRole("button", { name: /ver el informe/i }).click();
    });
    expect(document.querySelector(".informe-pasada")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /cerrar el informe/i }));
    expect(document.querySelector(".informe-pasada")).toBeNull();
    expect(screen.getByRole("button", { name: /ver el informe/i })).toBeTruthy();
  });
});
