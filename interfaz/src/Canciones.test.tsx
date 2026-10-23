import { fireEvent, render, screen } from "@testing-library/react";
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

function responder(cuerpo: unknown, ok = true, estado = 200) {
  return Promise.resolve({
    ok,
    status: estado,
    json: () => Promise.resolve(cuerpo),
  } as Response);
}

interface Dobles {
  /** Lo que contesta `GET /api/canciones`. */
  canciones?: FichaCancion[];
  /** Lo que cambia de la respuesta de `/pistas`. */
  detalle?: Partial<DetalleCancion>;
  /** Lo que cambia de la pieza que devuelve `/importar`. */
  pieza?: Partial<PiezaImportada>;
  /** Respuestas que una prueba quiere fallidas. */
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
      return responder(dobles.canciones ?? [CANCION]);
    }
    if (direccion === "/api/canciones" && metodo === "POST") {
      return (dobles.subir ?? (() => responder(CANCION)))();
    }
    if (direccion.endsWith("/pistas")) return responder(detalle);
    if (direccion.endsWith("/importar")) return responder(pieza);
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

    const entrada = (await screen.findByLabelText(/Añadir una canción/i)) as HTMLInputElement;
    fireEvent.change(entrada, {
      target: { files: [new File(["x"], "apuntes.pdf", { type: "application/pdf" })] },
    });

    expect(await screen.findByText(detalle)).toBeTruthy();
  });
});
