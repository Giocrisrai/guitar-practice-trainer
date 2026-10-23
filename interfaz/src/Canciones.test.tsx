import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Canciones } from "./Canciones";
import type {
  AfinacionCancion,
  DetalleCancion,
  FichaCancion,
  PiezaImportada,
  PistaDisponible,
} from "./tiposCancion";
import type { NotaDePieza } from "./tiposPieza";

/**
 * Qué se prueba aquí.
 *
 * Esta pantalla no calcula casi nada: los formatos, el motivo por el que una pista
 * no se puede usar, si la afinación cuadra y los avisos de la pieza los publica el
 * servidor ya escritos. Así que lo que se prueba es que cada cosa llegue a la
 * pantalla DESDE donde la decide —y que no se invente ninguna—, más el único
 * cálculo propio: el aviso de acordes, que sale de dos notas con el mismo
 * `inicio_pulsos`.
 *
 * El doble de `fetch` se escribe aquí y no se comparte con `Afinador.test.tsx`: el
 * de allí es local a su archivo y su firma es otra. Las formas que contesta son las
 * REALES de los cuatro endpoints (`servidor/app.py`).
 */

const CANCION: FichaCancion = {
  id: "x.gp5",
  nombre: "x",
  formato: "Guitar Pro",
  bytes: 1234,
  modificado: "2026-10-22T10:00:00+00:00",
};

const ESTANDAR: AfinacionCancion = {
  clave: "guitarra_estandar",
  nombre: "Guitarra estándar",
  cuerdas_midi: [40, 45, 50, 55, 59, 64],
  declarada: true,
};

/** Drop C: una afinación que SÍ tiene perfil al que afinarse. */
const DROP_C: AfinacionCancion = {
  clave: "guitarra_drop_c",
  nombre: "Drop C",
  cuerdas_midi: [36, 43, 48, 53, 57, 62],
  declarada: true,
};

/** Lo que trae un MIDI: el archivo no dice en qué afinación está. */
const SIN_DECLARAR: AfinacionCancion = {
  clave: null,
  nombre: "El archivo no dice en qué afinación está",
  cuerdas_midi: [],
  declarada: false,
};

const PISTA_GUITARRA: PistaDisponible = {
  numero: 1,
  nombre: "Guitarra ritmica",
  instrumento: "Guitarra",
  cuerdas_midi: [40, 45, 50, 55, 59, 64],
  notas: 12,
  usable: true,
  motivo_no_usable: null,
  afinacion: ESTANDAR,
};

const PISTA_BATERIA: PistaDisponible = {
  numero: 2,
  nombre: "Bateria",
  instrumento: "Percusion",
  cuerdas_midi: [],
  notas: 40,
  usable: false,
  motivo_no_usable: "La pista 2 ('Bateria') no se puede importar: es de percusión.",
  afinacion: SIN_DECLARAR,
};

/** Una nota de la pieza, con lo que cada prueba quiera cambiar. */
function nota(cambios: Partial<NotaDePieza> = {}): NotaDePieza {
  return {
    midi: 40,
    nombre: "E2",
    cuerda: 6,
    traste: 0,
    inicio_pulsos: 0,
    duracion_pulsos: 1,
    ...cambios,
  };
}

/** La pieza que devuelve `/importar`: dos notas seguidas y ningún aviso. */
const PIEZA: PiezaImportada = {
  nombre: "x",
  perfil: "guitarra_estandar",
  tempo: 90,
  compas: [4, 4],
  duracion_pulsos: 2,
  notas: [nota({ inicio_pulsos: 0 }), nota({ midi: 45, inicio_pulsos: 1 })],
  avisos: [],
};

/** El aviso del ritmo aproximado, tal y como lo escribe el servidor. */
const AVISO_RITMO =
  "El ritmo de esta pieza es APROXIMADO: el archivo no lo trae y se ha deducido " +
  "del espaciado, así que las duraciones pueden no cuadrar.";

/** Una respuesta sin envolver, para las pruebas que las resuelven a mano. */
function cuerpo(contenido: unknown, ok = true, estado = 200) {
  return {
    ok,
    status: estado,
    json: () => Promise.resolve(contenido),
  } as Response;
}

function responder(contenido: unknown, ok = true, estado = 200) {
  return Promise.resolve(cuerpo(contenido, ok, estado));
}

interface Dobles {
  /** Lo que contesta `GET /api/canciones`. */
  canciones?: FichaCancion[];
  /** Lo que cambia de la respuesta de `/pistas`. */
  detalle?: Partial<DetalleCancion>;
  /** Lo que cambia de la pieza que devuelve `/importar`. */
  pieza?: Partial<PiezaImportada>;
  /** Respuestas que una prueba quiere fallidas, o controladas a mano. */
  lista?: () => Promise<Response>;
  pistas?: () => Promise<Response>;
  importar?: () => Promise<Response>;
  putConfig?: () => Promise<Response>;
  subir?: () => Promise<Response>;
}

/**
 * Un `fetch` que contesta a los cuatro endpoints de la biblioteca y al
 * `PUT /api/config` del botón del afinador.
 */
function crearFetchFalso(dobles: Dobles = {}) {
  const detalle: DetalleCancion = {
    ...CANCION,
    pistas: [PISTA_GUITARRA],
    afinacion: ESTANDAR,
    perfil_activo: "guitarra_estandar",
    coincide: true,
    ...dobles.detalle,
  };
  const pieza: PiezaImportada = { ...PIEZA, ...dobles.pieza };
  return vi.fn((url: string, opciones?: RequestInit) => {
    const direccion = String(url);
    const metodo = opciones?.method ?? "GET";
    if (direccion === "/api/canciones" && metodo === "GET") {
      return (dobles.lista ?? (() => responder(dobles.canciones ?? [CANCION])))();
    }
    if (direccion === "/api/canciones" && metodo === "POST") {
      return (dobles.subir ?? (() => responder(CANCION)))();
    }
    if (direccion.endsWith("/pistas")) return (dobles.pistas ?? (() => responder(detalle)))();
    if (direccion.endsWith("/importar")) {
      return (dobles.importar ?? (() => responder(pieza)))();
    }
    if (direccion === "/api/config" && metodo === "PUT") {
      return (dobles.putConfig ?? (() => responder({ configuracion: {}, diagnostico: {} })))();
    }
    return Promise.reject(new Error(`fetch no simulado: ${direccion}`));
  });
}

/** Monta la pantalla con sus dos dobles de navegación. */
function montar(dobles: Dobles = {}) {
  const fetchFalso = crearFetchFalso(dobles);
  vi.stubGlobal("fetch", fetchFalso);
  const irA = vi.fn();
  const tocar = vi.fn();
  render(<Canciones irA={irA} tocar={tocar} />);
  return { fetchFalso, irA, tocar };
}

/** Elige la canción de la lista. Es la precondición de casi todo, no el sujeto. */
async function elegirLaCancion() {
  fireEvent.click(await screen.findByText("x"));
}

/** El `<input type="file">` de la subida. */
function entradaDeSubida() {
  return screen.findByLabelText(/Añadir una canción/i);
}

/** El cuerpo ya parseado de la primera llamada que cumpla `coincide`. */
function cuerpoDe(
  fetchFalso: ReturnType<typeof crearFetchFalso>,
  coincide: (direccion: string, opciones?: RequestInit) => boolean
): Record<string, unknown> {
  const llamada = fetchFalso.mock.calls.find(([url, opciones]) =>
    coincide(String(url), opciones)
  );
  expect(llamada).toBeDefined();
  return JSON.parse(String((llamada![1] as RequestInit).body));
}

describe("Canciones", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lista las canciones de la carpeta, con su formato", async () => {
    montar();
    expect(await screen.findByText("x")).toBeTruthy();
    // El formato lo nombra el servidor; aquí se muestra tal cual.
    expect(screen.getByText("Guitar Pro")).toBeTruthy();
  });

  it("con la carpeta vacía lo dice en vez de quedarse en blanco", async () => {
    montar({ canciones: [] });
    expect(await screen.findByText(/La carpeta está vacía/i)).toBeTruthy();
  });

  it("al elegir una cancion muestra sus pistas", async () => {
    montar();
    await elegirLaCancion();
    expect(
      await screen.findByRole("button", { name: /guitarra ritmica/i })
    ).toBeTruthy();
  });

  /**
   * Una pista que no se puede elegir y no dice por qué parece un programa roto. El
   * motivo lo escribe el núcleo y se muestra tal cual.
   *
   * La pista usable está en la misma prueba a propósito: sin ella, `disabled` en
   * todos los botones pasaría igual.
   */
  it("una pista que no se puede usar se muestra con su motivo y no se puede elegir", async () => {
    montar({ detalle: { pistas: [PISTA_GUITARRA, PISTA_BATERIA] } });
    await elegirLaCancion();

    expect(await screen.findByText(/es de percusión/i)).toBeTruthy();
    const bateria = await screen.findByRole("button", { name: /bateria/i });
    expect(bateria.hasAttribute("disabled")).toBe(true);
    const guitarra = screen.getByRole("button", { name: /guitarra ritmica/i });
    expect(guitarra.hasAttribute("disabled")).toBe(false);
  });

  it("avisa cuando la cancion pide otra afinacion y ofrece ir al afinador", async () => {
    montar({ detalle: { afinacion: DROP_C, coincide: false } });
    await elegirLaCancion();

    expect(await screen.findByText(/escrita en Drop C/)).toBeTruthy();
    expect(await screen.findByRole("button", { name: /afinador/i })).toBeTruthy();
  });

  /**
   * `coincide` tiene TRES valores. `null` es «el archivo no dice en qué afinación
   * está» (MIDI, MusicXML sin tablatura): la pieza se importa en el perfil activo y
   * el carril la acepta, así que NO hay nada que avisar. Tratarlo como `false` es
   * lo que hacía que la pantalla dijera «no cuadra, aféinate a null».
   */
  it("una cancion que no declara afinacion no genera ningun aviso de afinacion", async () => {
    montar({
      detalle: {
        afinacion: SIN_DECLARAR,
        coincide: null,
        pistas: [{ ...PISTA_GUITARRA, afinacion: SIN_DECLARAR }],
      },
    });
    await elegirLaCancion();

    // La respuesta llegó: las pistas están.
    expect(await screen.findByRole("button", { name: /guitarra ritmica/i })).toBeTruthy();
    expect(screen.queryByText(/escrita en/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /afinador/i })).toBeNull();
  });

  /**
   * Y la otra mitad del mismo asunto, que es la que de verdad era el bug: `null`
   * tampoco impide TOCAR. No basta con callar el aviso —«no cuadra, aféinate a
   * null» tenía una versión peor, «y encima no te dejo tocar»—: la pieza se importa
   * en el perfil activo y el carril la acepta, así que el botón va habilitado.
   */
  it("una cancion que no declara afinacion si se puede tocar", async () => {
    const { tocar } = montar({
      detalle: {
        afinacion: SIN_DECLARAR,
        coincide: null,
        pistas: [{ ...PISTA_GUITARRA, afinacion: SIN_DECLARAR }],
      },
    });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));

    const boton = await screen.findByRole("button", { name: /tocar en el carril/i });
    expect(boton.hasAttribute("disabled")).toBe(false);
    fireEvent.click(boton);
    expect(tocar).toHaveBeenCalledWith({ cancion: "x.gp5", pista: 1, perfil: null });
  });

  /**
   * Y con `coincide === false` pero sin clave no hay perfil al que afinarse: se
   * dice, pero no se ofrece un botón que no lleva a ninguna parte.
   */
  it("una afinacion sin perfil al que afinarse se dice sin boton muerto", async () => {
    const rara: AfinacionCancion = {
      clave: null,
      nombre: "Afinación C2 G2 C3 F3 A3 D4",
      cuerdas_midi: [36, 43, 48, 53, 57, 62],
      declarada: true,
    };
    montar({ detalle: { afinacion: rara, coincide: false } });
    await elegirLaCancion();

    expect(await screen.findByText(/No tengo ningún perfil al que afinarte/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /afinador/i })).toBeNull();
  });

  it("avisa de que el ritmo es aproximado cuando la pieza lo dice", async () => {
    montar({ pieza: { avisos: [AVISO_RITMO] } });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));

    expect(await screen.findByText(/aproximad/i)).toBeTruthy();
  });

  it("avisa de que el carril no sigue acordes cuando la pieza los trae", async () => {
    montar({
      pieza: { notas: [nota({ inicio_pulsos: 0 }), nota({ midi: 45, inicio_pulsos: 0 })] },
    });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));

    expect(await screen.findByText(/acorde/i)).toBeTruthy();
  });

  /** Y no lo avisa cuando no los trae: el aviso es del dato, no del camino. */
  it("sin notas simultaneas no se avisa de acordes", async () => {
    montar();
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));

    // La pieza llegó: su resumen está en pantalla.
    expect(await screen.findByText(/2 notas a 90 pulsos/i)).toBeTruthy();
    expect(screen.queryByText(/acorde/i)).toBeNull();
  });

  /**
   * Lo que viaja al carril es QUÉ canción y QUÉ pista, no la pieza: la lee el
   * servidor. Y la pista viaja con el `numero` que publica `/pistas`, en base 1,
   * sin traducir nada: se elige la SEGUNDA a propósito, porque con la primera un
   * `1` escrito a mano pasaría igual.
   */
  it("al confirmar manda al carril la cancion y el numero de pista elegido", async () => {
    const segunda: PistaDisponible = { ...PISTA_GUITARRA, numero: 2, nombre: "Guitarra solista" };
    const { tocar } = montar({ detalle: { pistas: [PISTA_GUITARRA, segunda] } });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra solista/i }));
    fireEvent.click(await screen.findByRole("button", { name: /tocar en el carril/i }));

    expect(tocar).toHaveBeenCalledWith({ cancion: "x.gp5", pista: 2, perfil: null });
  });

  /**
   * Y la MISMA numeración en la previsualización, que es la otra superficie de base
   * 1 y la que no mira la prueba de arriba: lo que se previsualiza tiene que ser la
   * pista que se va a tocar, o los avisos son de otra pista.
   *
   * `perfil: null` también se afirma: es «manda lo que diga el archivo», y fijar un
   * perfil aquí reinterpretaría una tablatura en Drop D con otra afinación,
   * dibujando trastes que la canción no toca.
   */
  it("la previsualizacion pide la misma pista, en base 1, y sin imponer perfil", async () => {
    const segunda: PistaDisponible = { ...PISTA_GUITARRA, numero: 2, nombre: "Guitarra solista" };
    const { fetchFalso } = montar({ detalle: { pistas: [PISTA_GUITARRA, segunda] } });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra solista/i }));
    // La pieza llegó, así que el POST se hizo y se puede mirar su cuerpo.
    expect(await screen.findByText(/2 notas a 90 pulsos/i)).toBeTruthy();

    expect(
      cuerpoDe(fetchFalso, (direccion, opciones) =>
        direccion === "/api/canciones/x.gp5/importar" && opciones?.method === "POST"
      )
    ).toEqual({ pista: 2, perfil: null });
  });

  /**
   * El carril rechaza una pieza en otra afinación (spec §5), así que ofrecer
   * «Tocar» con `coincide === false` sería ofrecer un 400. Primero el afinador.
   */
  it("con otra afinacion no se puede tocar todavia", async () => {
    const { tocar } = montar({ detalle: { afinacion: DROP_C, coincide: false } });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));

    const boton = await screen.findByRole("button", { name: /tocar en el carril/i });
    expect(boton.hasAttribute("disabled")).toBe(true);
    fireEvent.click(boton);
    expect(tocar).not.toHaveBeenCalled();
  });

  /** La spec §6: «te lleva al afinador con ese perfil puesto». Las dos cosas. */
  it("el boton del afinador deja el perfil puesto y entonces lleva al afinador", async () => {
    const { fetchFalso, irA } = montar({ detalle: { afinacion: DROP_C, coincide: false } });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /afinador/i }));

    await vi.waitFor(() => expect(irA).toHaveBeenCalledWith("afinador"));
    expect(
      cuerpoDe(fetchFalso, (direccion, opciones) =>
        direccion === "/api/config" && opciones?.method === "PUT"
      )
    ).toEqual({ perfil: "guitarra_drop_c" });
  });

  /** Si el PUT falla no se navega en silencio: se dice y te quedas donde estabas. */
  it("si no se pudo cambiar la afinacion lo dice y no lleva al afinador", async () => {
    const { irA } = montar({
      detalle: { afinacion: DROP_C, coincide: false },
      putConfig: () => responder({ detail: "perfil desconocido" }, false, 400),
    });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /afinador/i }));

    expect(await screen.findByText("perfil desconocido")).toBeTruthy();
    expect(irA).not.toHaveBeenCalled();
  });

  /**
   * El `detail` de una subida rechazada viene escrito para el usuario -los formatos
   * que valen, el nombre que no pasa el guardia, los bytes del techo-: se muestra
   * tal cual y no se reescribe aquí.
   */
  it("una subida rechazada muestra el motivo del servidor tal cual", async () => {
    const detalle = "No sé leer archivos '.pdf'. Los que valen: .gp3, .gp4, .gp5, .mid";
    montar({ subir: () => responder({ detail: detalle }, false, 400) });

    fireEvent.change(await entradaDeSubida(), {
      target: { files: [new File(["x"], "apuntes.pdf", { type: "application/pdf" })] },
    });

    expect(await screen.findByText(detalle)).toBeTruthy();
  });

  /**
   * Y la subida que SÍ entra: la canción que acabas de añadir es la que querías, así
   * que la carpeta se vuelve a leer y la canción se abre sola. Sin eso, subes un
   * archivo y no pasa nada visible.
   */
  it("una subida que entra recarga la carpeta y abre la cancion nueva", async () => {
    const { fetchFalso } = montar();
    // Antes de subir ya hay una lectura de la carpeta, la de montar.
    const lecturas = () =>
      fetchFalso.mock.calls.filter(
        ([url, opciones]) =>
          url === "/api/canciones" && (opciones as RequestInit | undefined)?.method === undefined
      ).length;
    expect(await screen.findByText("x")).toBeTruthy();
    expect(lecturas()).toBe(1);

    fireEvent.change(await entradaDeSubida(), {
      target: { files: [new File(["x"], "x.gp5")] },
    });

    // Se abrió sola: sus pistas están en pantalla sin haber pulsado la lista.
    expect(await screen.findByRole("button", { name: /guitarra ritmica/i })).toBeTruthy();
    expect(lecturas()).toBe(2);
  });

  // -------------------------------------------------------------------------
  // Los tres caminos de error del servidor. El `detail` se muestra tal cual.
  // -------------------------------------------------------------------------

  it("si no se puede leer la carpeta lo dice", async () => {
    montar({ lista: () => responder({ detail: "No pude abrir la carpeta" }, false, 500) });
    expect(await screen.findByText("No pude abrir la carpeta")).toBeTruthy();
  });

  it("si no se pueden leer las pistas lo dice", async () => {
    montar({ pistas: () => responder({ detail: "'x.gp5' no es un Guitar Pro" }, false, 400) });
    await elegirLaCancion();
    expect(await screen.findByText("'x.gp5' no es un Guitar Pro")).toBeTruthy();
  });

  it("si no se puede importar la pista lo dice", async () => {
    montar({
      importar: () => responder({ detail: "La pista 1 no cabe en el mástil" }, false, 400),
    });
    await elegirLaCancion();
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));
    expect(await screen.findByText("La pista 1 no cabe en el mástil")).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // Las dos respuestas que llegan fuera de orden
  // -------------------------------------------------------------------------

  /**
   * `fetch` no promete orden de llegada: dos clics rápidos -canción A, canción B-
   * pueden devolver A DESPUÉS de B. Soltar el estado por delante cubre el mientras,
   * no la llegada tardía, y lo que se veía era la lista de pistas de A debajo del
   * título de B; elegir una pista ahí importaba una pista de B.
   */
  it("el detalle que llega tarde de la cancion anterior no se pinta", async () => {
    const A: FichaCancion = { ...CANCION, id: "a.gp5", nombre: "a" };
    const B: FichaCancion = { ...CANCION, id: "b.gp5", nombre: "b" };
    const detalleDe = (ficha: FichaCancion, pista: string): DetalleCancion => ({
      ...ficha,
      pistas: [{ ...PISTA_GUITARRA, nombre: pista }],
      afinacion: ESTANDAR,
      perfil_activo: "guitarra_estandar",
      coincide: true,
    });
    const pendientes = new Map<string, (respuesta: Response) => void>();
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const direccion = String(url);
        if (direccion === "/api/canciones") return responder([A, B]);
        if (direccion.endsWith("/pistas")) {
          return new Promise<Response>((cumplir) => pendientes.set(direccion, cumplir));
        }
        return Promise.reject(new Error(`fetch no simulado: ${direccion}`));
      })
    );
    render(<Canciones irA={vi.fn()} tocar={vi.fn()} />);

    fireEvent.click(await screen.findByText("a"));
    fireEvent.click(await screen.findByText("b"));
    await waitFor(() => expect(pendientes.size).toBe(2));

    // B contesta primero y A después: el orden de llegada es el inverso al de pedida.
    await act(async () => {
      pendientes.get("/api/canciones/b.gp5/pistas")!(cuerpo(detalleDe(B, "Pistas de B")));
    });
    await act(async () => {
      pendientes.get("/api/canciones/a.gp5/pistas")!(cuerpo(detalleDe(A, "Pistas de A")));
    });

    expect(screen.getByRole("button", { name: /pistas de b/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /pistas de a/i })).toBeNull();
  });

  /**
   * Y elegir otra CANCIÓN deja rancia la pieza en vuelo, no solo el detalle: los
   * avisos de una pista de la canción anterior debajo del título de la nueva son
   * los avisos de otra canción.
   *
   * **Declarada como prueba de no-regresión:** esta propiedad está defendida dos
   * veces —el contador de `elegirCancion` y el `setPista(null)` que vacía el bloque
   * de avisos—, así que ninguna mutación de una sola línea la tumba. Medido:
   * quitando solo el contador pasa, quitando solo `setPista(null)` pasa, y quitando
   * las dos cae. Está aquí porque las dos defensas se pueden perder de una en una y
   * esto dice qué se rompería si se pierden las dos.
   */
  it("la pieza que llega tarde de la cancion anterior no se pinta", async () => {
    const A: FichaCancion = { ...CANCION, id: "a.gp5", nombre: "a" };
    const B: FichaCancion = { ...CANCION, id: "b.gp5", nombre: "b" };
    const detalleDe = (ficha: FichaCancion): DetalleCancion => ({
      ...ficha,
      pistas: [PISTA_GUITARRA],
      afinacion: ESTANDAR,
      perfil_activo: "guitarra_estandar",
      coincide: true,
    });
    const pendientes = new Map<string, (respuesta: Response) => void>();
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const direccion = String(url);
        if (direccion === "/api/canciones") return responder([A, B]);
        if (direccion === "/api/canciones/a.gp5/pistas") return responder(detalleDe(A));
        if (direccion === "/api/canciones/b.gp5/pistas") return responder(detalleDe(B));
        if (direccion.endsWith("/importar")) {
          return new Promise<Response>((cumplir) => pendientes.set(direccion, cumplir));
        }
        return Promise.reject(new Error(`fetch no simulado: ${direccion}`));
      })
    );
    render(<Canciones irA={vi.fn()} tocar={vi.fn()} />);

    // Se pide la pista de A y, sin esperarla, se cambia de canción.
    fireEvent.click(await screen.findByText("a"));
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));
    await waitFor(() => expect(pendientes.size).toBe(1));
    fireEvent.click(screen.getByText("b"));
    expect(await screen.findByRole("button", { name: /guitarra ritmica/i })).toBeTruthy();

    // Y entonces contesta la de A, tarde.
    await act(async () => {
      pendientes.get("/api/canciones/a.gp5/importar")!(cuerpo({ ...PIEZA, tempo: 60 }));
    });

    expect(screen.queryByText(/a 60 pulsos/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /tocar en el carril/i })).toBeNull();
  });

  /** Lo mismo con la previsualización: la pieza de la pista anterior que llega tarde
   * dejaría los avisos de una pista debajo de otra. */
  it("la pieza que llega tarde de la pista anterior no se pinta", async () => {
    const segunda: PistaDisponible = { ...PISTA_GUITARRA, numero: 2, nombre: "Guitarra solista" };
    const pendientes = new Map<number, (respuesta: Response) => void>();
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, opciones?: RequestInit) => {
        const direccion = String(url);
        if (direccion === "/api/canciones") return responder([CANCION]);
        if (direccion.endsWith("/pistas")) {
          return responder({
            ...CANCION,
            pistas: [PISTA_GUITARRA, segunda],
            afinacion: ESTANDAR,
            perfil_activo: "guitarra_estandar",
            coincide: true,
          });
        }
        if (direccion.endsWith("/importar")) {
          const { pista } = JSON.parse(String(opciones?.body)) as { pista: number };
          return new Promise<Response>((cumplir) => pendientes.set(pista, cumplir));
        }
        return Promise.reject(new Error(`fetch no simulado: ${direccion}`));
      })
    );
    render(<Canciones irA={vi.fn()} tocar={vi.fn()} />);

    fireEvent.click(await screen.findByText("x"));
    fireEvent.click(await screen.findByRole("button", { name: /guitarra ritmica/i }));
    fireEvent.click(await screen.findByRole("button", { name: /guitarra solista/i }));
    await waitFor(() => expect(pendientes.size).toBe(2));

    // La 2 contesta primero y la 1 después. El tempo distingue las dos piezas.
    await act(async () => {
      pendientes.get(2)!(cuerpo({ ...PIEZA, tempo: 120 }));
    });
    await act(async () => {
      pendientes.get(1)!(cuerpo({ ...PIEZA, tempo: 60 }));
    });

    expect(screen.getByText(/a 120 pulsos/i)).toBeTruthy();
    expect(screen.queryByText(/a 60 pulsos/i)).toBeNull();
  });
});
