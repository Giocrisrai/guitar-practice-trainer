import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { detenerEjercicioAlSalir } from "./detencionAlSalir";
import { Ejercicios } from "./Ejercicios";
import type { EstadoEjercicio } from "./tiposEjercicio";

/**
 * Las cuatro familias con los parametros REALES que publica
 * `/api/ejercicios/familias` (ver servidor/app.py).
 *
 * Omitir `intervalo` de este fixture es lo que dejo pasar el 500 de la familia de
 * intervalos: el Configurador mandaba `tipo` y ese generador solo acepta
 * `intervalo`. Recortar los parametros tampoco es gratis: los controles se
 * derivan de este array.
 */
const FAMILIAS = [
  {
    clave: "escala",
    nombre: "Escalas",
    descripcion: "Una escala en una posicion del mastil",
    tipos: ["mayor", "pentatonica_menor"],
    parametros: ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
  },
  {
    clave: "arpegio",
    nombre: "Arpegios",
    descripcion: "Las notas de un acorde, una a una",
    tipos: ["mayor", "menor_septima"],
    parametros: ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
  },
  {
    clave: "intervalo",
    nombre: "Intervalos",
    descripcion: "Suena una nota y tocas la que esta al intervalo pedido",
    tipos: ["tercera_mayor", "quinta_justa"],
    parametros: ["intervalo", "traste_minimo", "traste_maximo", "tempo", "repeticiones"],
  },
  {
    clave: "lectura",
    nombre: "Lectura del mastil",
    descripcion: "Se nombra una nota y tienes que encontrarla",
    tipos: [],
    parametros: ["cuerda", "traste_minimo", "traste_maximo", "tempo", "repeticiones"],
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

/** El instrumento ACTIVO que publica /api/ejercicios/instrumento. */
const INSTRUMENTO = {
  clave: "guitarra_estandar",
  nombre: "Guitarra estandar",
  trastes: 22,
  cuerdas: [
    { numero: 6, nota: "E2" },
    { numero: 1, nota: "E4" },
  ],
};

const ESTADO_VACIO = {
  ejercicio: null,
  evaluacion: null,
  informe: null,
  metronomo: false,
  metronomo_pausado: false,
  metronomo_pedido: false,
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

/**
 * Pulsa "Empezar" y espera a que el POST y sus cambios de estado terminen.
 *
 * Dentro de `act` porque `empezar()` es asincrono: sin esto el `setEnviando(false)`
 * cae fuera de la prueba y React avisa de una actualizacion sin envolver.
 */
async function pulsarEmpezar() {
  await act(async () => {
    screen.getByRole("button", { name: /empezar/i }).click();
  });
}

function responder(cuerpo: unknown, ok = true, estado = 200) {
  return Promise.resolve({
    ok,
    status: estado,
    json: () => Promise.resolve(cuerpo),
  } as Response);
}

/** Estado de un ejercicio en curso, con lo que cada prueba quiera cambiar. */
function estadoEnCurso(cambios: Partial<EstadoEjercicio> = {}): EstadoEjercicio {
  const nota = {
    midi: 48,
    nombre: "C3",
    posiciones: [{ cuerda: 6, traste: 8 }],
    pulsos: 1,
    referencia_midi: null,
  };
  return {
    ejercicio: {
      clave: "e",
      nombre: "Escala de Do mayor",
      descripcion: "",
      tempo: 80,
      perfil: "guitarra_estandar",
      notas: [
        { midi: 40, nombre: "E2", posiciones: [{ cuerda: 6, traste: 0 }], pulsos: 1, referencia_midi: null },
        nota,
      ],
    },
    evaluacion: {
      indice: 1,
      total: 2,
      intentos: 0,
      ayuda_visible: false,
      completado: false,
      nota_actual: nota,
      ultimo_fallo: null,
    },
    informe: {
      ejercicio: "e",
      completado: false,
      notas: [
        { indice: 0, midi: 40, nombre: "E2", intentos: 1, cents: 3.0, instante: 0, ayuda_mostrada: false },
      ],
      aciertos_a_la_primera: 1,
      desviacion_mediana_cents: 3.0,
      regularidad_ms: null,
      notas_dificiles: [],
    },
    metronomo: true,
    metronomo_pausado: false,
    metronomo_pedido: true,
    ...cambios,
  };
}

describe("Ejercicios", () => {
  let fetchFalso: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
    fetchFalso = vi.fn((url: string) => {
      if (url.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
      if (url.includes("/api/ejercicios/instrumento")) return responder(INSTRUMENTO);
      if (url.includes("/api/perfiles")) return responder(PERFILES);
      if (url.includes("/api/ejercicios/estado")) return responder(ESTADO_VACIO);
      return responder(ESTADO_VACIO);
    });
    vi.stubGlobal("fetch", fetchFalso);
  });

  afterEach(() => vi.unstubAllGlobals());

  /** El cuerpo del ultimo POST a /api/ejercicios/iniciar, ya parseado. */
  function ultimoCuerpoEnviado(): Record<string, unknown> {
    const llamadas = fetchFalso.mock.calls.filter(
      ([url, opciones]) =>
        String(url).includes("/api/ejercicios/iniciar") &&
        (opciones as RequestInit | undefined)?.method === "POST"
    );
    expect(llamadas.length).toBeGreaterThan(0);
    const ultima = llamadas[llamadas.length - 1];
    return JSON.parse(String((ultima[1] as RequestInit).body));
  }

  it("el configurador se construye con las familias del servidor", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(screen.getByText("Lectura del mastil")).toBeTruthy();
    expect(screen.getByText("Intervalos")).toBeTruthy();
  });

  it("con el bajo activo no ofrece cuerdas ni raices que solo tiene la guitarra", async () => {
    // El defecto: el Configurador derivaba las opciones de TODOS los perfiles
    // que el servidor conoce (/api/perfiles), no del que el usuario tiene
    // activo. Aqui /api/perfiles sigue publicando la guitarra (la necesita el
    // mastil), pero el instrumento ACTIVO es un bajo de 4 cuerdas: las opciones
    // deben salir de ese, o "Empezar" termina en un 400 al pedir la 5a/6a
    // cuerda o una raiz que el bajo no alcanza.
    const BAJO_4 = {
      clave: "bajo_4",
      nombre: "Bajo 4 cuerdas",
      trastes: 24,
      cuerdas: [
        { numero: 4, nota: "E1" },
        { numero: 3, nota: "A1" },
        { numero: 2, nota: "D2" },
        { numero: 1, nota: "G2" },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (url.includes("/api/ejercicios/instrumento")) return responder(BAJO_4);
        if (url.includes("/api/perfiles")) return responder(PERFILES);
        return responder(ESTADO_VACIO);
      })
    );

    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    await waitFor(() => {
      const opciones = [...screen.getByLabelText("Raíz").querySelectorAll("option")];
      expect(opciones.length).toBeGreaterThan(1);
    });

    const opcionesRaiz = [...screen.getByLabelText("Raíz").querySelectorAll("option")]
      .map((o) => o.textContent)
      .filter((texto) => texto !== "Por defecto");
    // Del E1 del bajo al G2 (su cuerda mas aguda) mas sus 24 trastes: G4. La
    // guitarra sube hasta D6, que aqui no debe aparecer.
    expect(opcionesRaiz[opcionesRaiz.length - 1]).toBe("G4");
    expect(opcionesRaiz).not.toContain("D6");

    fireEvent.change(screen.getByLabelText("Ejercicio"), { target: { value: "lectura" } });
    await waitFor(() => expect(screen.getByLabelText("Cuerda")).toBeTruthy());
    const opcionesCuerda = [...screen.getByLabelText("Cuerda").querySelectorAll("option")]
      .map((o) => o.textContent)
      .filter((texto) => texto !== "Por defecto");
    expect(opcionesCuerda).toEqual(["1ª", "2ª", "3ª", "4ª"]);
  });

  it("muestra los tipos de la familia elegida, no una lista escrita a mano", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(screen.getByText("pentatonica_menor")).toBeTruthy();
  });

  it("los controles salen de los parametros que declara la familia", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());

    // Escala declara raiz_midi y direccion, y no declara repeticiones.
    expect(screen.getByLabelText("Raíz")).toBeTruthy();
    expect(screen.getByLabelText("Dirección")).toBeTruthy();
    expect(screen.queryByLabelText("Repeticiones")).toBeNull();

    fireEvent.change(screen.getByLabelText("Ejercicio"), { target: { value: "lectura" } });

    // Lectura declara cuerda y repeticiones, y no declara raiz_midi ni direccion.
    expect(screen.getByLabelText("Cuerda")).toBeTruthy();
    expect(screen.getByLabelText("Repeticiones")).toBeTruthy();
    expect(screen.queryByLabelText("Raíz")).toBeNull();
    expect(screen.queryByLabelText("Dirección")).toBeNull();
    // Sin tipos publicados no hay desplegable de tipos.
    expect(screen.queryByLabelText("Tipo")).toBeNull();
  });

  it("sin tocar nada no se manda ningun parametro, para que el nucleo aplique sus defectos", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());

    await pulsarEmpezar();

    await waitFor(() => expect(ultimoCuerpoEnviado()).toBeTruthy());
    expect(ultimoCuerpoEnviado()).toEqual({
      familia: "escala",
      parametros: {},
      con_metronomo: true,
    });
  });

  it("escala manda el tipo bajo la clave 'tipo' y la raiz por nombre de nota", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());

    // "Sol mayor en la quinta posicion" (spec §4.2): G3 es el MIDI 55.
    fireEvent.change(screen.getByLabelText("Raíz"), { target: { value: "55" } });
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "mayor" } });
    fireEvent.change(screen.getByLabelText("Traste mínimo"), { target: { value: "5" } });
    await pulsarEmpezar();

    await waitFor(() =>
      expect(ultimoCuerpoEnviado().parametros).toEqual({
        raiz_midi: 55,
        tipo: "mayor",
        traste_minimo: 5,
      })
    );
    // Se elige G3 por su nombre; el numero MIDI no se escribe a mano.
    expect(screen.getByRole("option", { name: "G3" })).toBeTruthy();
  });

  it("intervalo manda 'intervalo' y nunca 'tipo': es la clave que esa familia declara", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("Ejercicio"), { target: { value: "intervalo" } });
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "quinta_justa" } });
    await pulsarEmpezar();

    await waitFor(() =>
      expect(ultimoCuerpoEnviado().parametros).toEqual({ intervalo: "quinta_justa" })
    );
    expect(ultimoCuerpoEnviado().parametros).not.toHaveProperty("tipo");
  });

  it("la clave del tipo no se adivina: no se confunde con otro parametro sin control propio", async () => {
    // Si claveDeTipos "adivinara" tomando el primer parametro sin control, esta
    // familia (con un parametro extra, sin control, declarado ANTES de 'tipo')
    // elegiria el equivocado en silencio: pintaria "Tipo" sobre
    // 'extra_sin_control' y el verdadero 'tipo' -que tampoco tiene control
    // propio- desaparecia sin mandarse nunca.
    const escalaConParametroExtra = {
      ...FAMILIAS[0],
      parametros: ["raiz_midi", "extra_sin_control", "tipo", "traste_minimo"],
    };
    const fetchDeEstaPrueba = vi.fn((url: string, _opciones?: RequestInit) => {
      if (url.includes("/api/ejercicios/familias")) return responder([escalaConParametroExtra]);
      if (url.includes("/api/ejercicios/instrumento")) return responder(INSTRUMENTO);
      if (url.includes("/api/perfiles")) return responder(PERFILES);
      return responder(ESTADO_VACIO);
    });
    vi.stubGlobal("fetch", fetchDeEstaPrueba);

    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());

    // Solo debe existir un desplegable "Tipo", y debe ser el del parametro 'tipo'.
    fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: "mayor" } });
    await pulsarEmpezar();

    await waitFor(() => {
      const llamadas = fetchDeEstaPrueba.mock.calls.filter(
        ([url, opciones]) =>
          String(url).includes("/api/ejercicios/iniciar") &&
          (opciones as RequestInit | undefined)?.method === "POST"
      );
      expect(llamadas.length).toBeGreaterThan(0);
      const cuerpo = JSON.parse(String((llamadas[llamadas.length - 1][1] as RequestInit).body));
      expect(cuerpo.parametros).toEqual({ tipo: "mayor" });
    });
  });

  it("cada familia manda solo claves que ella declara", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());

    for (const familia of FAMILIAS) {
      fireEvent.change(screen.getByLabelText("Ejercicio"), { target: { value: familia.clave } });
      // Se toca todo lo que la familia ofrezca, para que el cuerpo lleve el maximo
      // de claves posible y cualquier clave ajena salte aqui.
      if (familia.tipos.length > 0) {
        fireEvent.change(screen.getByLabelText("Tipo"), { target: { value: familia.tipos[0] } });
      }
      for (const [etiqueta, valor] of [
        ["Raíz", "55"],
        ["Cuerda", "6"],
        ["Dirección", "ascendente"],
        ["Tempo (ppm)", "70"],
        ["Traste mínimo", "2"],
        ["Traste máximo", "9"],
        ["Repeticiones", "4"],
      ] as const) {
        const control = screen.queryByLabelText(etiqueta);
        if (control !== null) fireEvent.change(control, { target: { value: valor } });
      }
      await pulsarEmpezar();

      await waitFor(() => expect(ultimoCuerpoEnviado().familia).toBe(familia.clave));
      const parametros = ultimoCuerpoEnviado().parametros as Record<string, unknown>;
      expect(Object.keys(parametros).length).toBeGreaterThan(0);
      for (const clave of Object.keys(parametros)) {
        expect(familia.parametros).toContain(clave);
      }
    }
  });

  it("cambiar de familia no arrastra los parametros de la anterior", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());

    fireEvent.change(screen.getByLabelText("Raíz"), { target: { value: "55" } });
    fireEvent.change(screen.getByLabelText("Ejercicio"), { target: { value: "lectura" } });
    await pulsarEmpezar();

    await waitFor(() => expect(ultimoCuerpoEnviado().familia).toBe("lectura"));
    expect(ultimoCuerpoEnviado().parametros).toEqual({});
  });

  it("muestra la nota que toca ahora cuando hay ejercicio en curso", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar(estadoEnCurso());
    await waitFor(() => expect(screen.getByText("C3")).toBeTruthy());
  });

  it("avisa de que nota sono cuando fallas", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    const estado = estadoEnCurso();
    estado.evaluacion!.ultimo_fallo = "A2";
    WebSocketFalso.ultimo!.enviar(estado);
    await waitFor(() => expect(screen.getByText(/A2/)).toBeTruthy());
  });

  it("avisa de que el ejercicio va sin metronomo cuando se pidio y no sono", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar(estadoEnCurso({ metronomo: false, metronomo_pedido: true }));
    await waitFor(() => expect(screen.getByText(/Sin metrónomo/)).toBeTruthy());
    expect(screen.queryByText(/en pausa/)).toBeNull();
  });

  it("no avisa de falta de metronomo cuando el usuario lo desmarco", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    // metronomo_pedido: false es "el usuario lo desmarco": no hubo salida de
    // audio que faltara, asi que no hay nada que avisar (a diferencia del caso
    // de arriba, donde se pidio y no sono).
    WebSocketFalso.ultimo!.enviar(estadoEnCurso({ metronomo: false, metronomo_pedido: false }));
    await waitFor(() => expect(screen.getByText("C3")).toBeTruthy());
    expect(screen.queryByText(/Sin metrónomo/)).toBeNull();
  });

  it("la pausa del metronomo se distingue de no tenerlo", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    // metronomo sigue siendo true mientras esta pausado: la pausa se lee en
    // metronomo_pausado, y son avisos distintos.
    WebSocketFalso.ultimo!.enviar(estadoEnCurso({ metronomo_pausado: true }));
    await waitFor(() => expect(screen.getByText(/en pausa/)).toBeTruthy());
    expect(screen.queryByText(/Sin metrónomo/)).toBeNull();
  });

  it("el mastil rotula la nota actual siempre y solo revela su posicion con la ayuda", async () => {
    const { container } = render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());

    WebSocketFalso.ultimo!.enviar(estadoEnCurso());
    await waitFor(() => expect(screen.getByText("Ahora: C3")).toBeTruthy());
    expect(container.querySelectorAll(".traste.activo").length).toBe(0);
    // Las ya acertadas se quedan en tenue: E2 al aire en la sexta.
    expect(container.querySelectorAll(".traste.tenue").length).toBe(1);

    const conAyuda = estadoEnCurso();
    conAyuda.evaluacion!.ayuda_visible = true;
    WebSocketFalso.ultimo!.enviar(conAyuda);
    await waitFor(() => expect(container.querySelectorAll(".traste.activo").length).toBe(1));
    expect(container.querySelectorAll(".traste.tenue").length).toBe(1);
  });

  it("muestra el informe al completar el ejercicio, con la desviacion de cada nota", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar({
      ejercicio: null,
      evaluacion: {
        indice: 3,
        total: 3,
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
          { indice: 0, midi: 40, nombre: "E2", intentos: 1, cents: 0.0, instante: 0, ayuda_mostrada: false },
          { indice: 1, midi: 42, nombre: "F#2", intentos: 4, cents: -8.0, instante: 1, ayuda_mostrada: false },
          { indice: 2, midi: 43, nombre: "G2", intentos: 6, cents: null, instante: null, ayuda_mostrada: true },
        ],
        aciertos_a_la_primera: 1,
        desviacion_mediana_cents: -3.0,
        regularidad_ms: null,
        notas_dificiles: [
          { indice: 1, midi: 42, nombre: "F#2", intentos: 4, cents: -8.0, instante: 1, ayuda_mostrada: false },
        ],
      },
      metronomo: false,
      metronomo_pausado: false,
      metronomo_pedido: false,
    });

    await waitFor(() => expect(screen.getByText(/-8.0 cents/)).toBeTruthy());
    // cents 0.0 es acertada y afinada; cents null es no acertada. No se confunden.
    expect(screen.getByText(/E2 — 0.0 cents/)).toBeTruthy();
    expect(screen.getByText(/G2 — no acertada/)).toBeTruthy();
  });

  it("un error del servidor al generar se muestra al usuario", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, opciones?: RequestInit) => {
        if (url.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (url.includes("/api/ejercicios/instrumento")) return responder(INSTRUMENTO);
        if (url.includes("/api/perfiles")) return responder(PERFILES);
        if (opciones?.method === "POST") {
          return responder({ detail: "No cae ninguna nota de la escala" }, false, 400);
        }
        return responder(ESTADO_VACIO);
      })
    );
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    await pulsarEmpezar();
    await waitFor(() => expect(screen.getByText(/No cae ninguna nota/)).toBeTruthy());
  });

  const rutasLlamadas = () => fetchFalso.mock.calls.map(([url]) => String(url));

  it("detiene el ejercicio al desmontar, o su metronomo se queda sonando", async () => {
    const { unmount } = render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(rutasLlamadas()).not.toContain("/api/ejercicios/detener");
    unmount();
    await waitFor(() => expect(rutasLlamadas()).toContain("/api/ejercicios/detener"));
    const llamada = fetchFalso.mock.calls.find(([url]) => url === "/api/ejercicios/detener")!;
    expect((llamada[1] as RequestInit).method).toBe("POST");
  });

  it("cierra el WebSocket ANTES de programar el detener", async () => {
    const orden: string[] = [];
    class SocketQueApunta extends WebSocketFalso {
      close() {
        orden.push("cerrar");
      }
    }
    vi.stubGlobal("WebSocket", SocketQueApunta);
    vi.spyOn(detenerEjercicioAlSalir, "programar").mockImplementation(() => {
      orden.push("programar");
    });
    const { unmount } = render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    unmount();
    expect(orden).toEqual(["cerrar", "programar"]);
  });

  it("remontar por key nueva no detiene el ejercicio del montaje nuevo", async () => {
    const { rerender } = render(<Ejercicios key="uno" />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    rerender(<Ejercicios key="dos" />);
    await act(async () => {});
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(rutasLlamadas()).not.toContain("/api/ejercicios/detener");
  });

  it("montar en StrictMode no detiene el ejercicio", async () => {
    render(
      <StrictMode>
        <Ejercicios />
      </StrictMode>
    );
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    await act(async () => {});
    expect(rutasLlamadas()).not.toContain("/api/ejercicios/detener");
  });
});
