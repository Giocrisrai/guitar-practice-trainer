import { describe, expect, it } from "vitest";

import {
  calificacion,
  cuerdasElegibles,
  fraccionProgreso,
  mensajeDeFallo,
  midiDeNombre,
  nombreDeMidi,
  posicionesAcertadas,
  raicesElegibles,
  textoDesviacion,
} from "./presentacionEjercicio";

describe("fraccionProgreso", () => {
  it("al empezar el progreso es cero", () => {
    expect(fraccionProgreso(0, 8)).toBe(0);
  });

  it("al terminar el progreso es uno", () => {
    expect(fraccionProgreso(8, 8)).toBe(1);
  });

  it("a mitad de camino es la mitad", () => {
    expect(fraccionProgreso(4, 8)).toBeCloseTo(0.5);
  });

  it("un ejercicio sin notas no divide por cero", () => {
    expect(fraccionProgreso(0, 0)).toBe(0);
  });

  it("nunca se sale de cero a uno", () => {
    expect(fraccionProgreso(12, 8)).toBe(1);
    expect(fraccionProgreso(-3, 8)).toBe(0);
  });
});

describe("mensajeDeFallo", () => {
  it("dice que esperaba y que sono", () => {
    expect(mensajeDeFallo("E2", "A2")).toContain("E2");
    expect(mensajeDeFallo("E2", "A2")).toContain("A2");
  });

  it("sin fallo no hay mensaje", () => {
    expect(mensajeDeFallo("E2", null)).toBeNull();
  });

  it("sin nota esperada tampoco", () => {
    expect(mensajeDeFallo(null, "A2")).toBeNull();
  });
});

describe("calificacion", () => {
  it("todo a la primera se reconoce", () => {
    expect(calificacion(8, 8).toLowerCase()).toContain("perfecto");
  });

  it("un ejercicio sin notas no divide por cero", () => {
    expect(calificacion(0, 0)).toBeTruthy();
  });

  it("pocos aciertos dan un mensaje distinto que muchos", () => {
    expect(calificacion(2, 10)).not.toBe(calificacion(9, 10));
  });
});

describe("textoDesviacion", () => {
  it("una nota no acertada no se pinta como afinada", () => {
    expect(textoDesviacion(null)).toBe("no acertada");
  });

  it("cero cents es acertada y perfectamente afinada, no ausente", () => {
    expect(textoDesviacion(0)).toBe("0.0 cents");
  });

  it("dice el signo de la desviacion", () => {
    expect(textoDesviacion(8)).toBe("+8.0 cents");
    expect(textoDesviacion(-8)).toBe("-8.0 cents");
  });
});

describe("nombres de nota", () => {
  it("el nombre en notacion cientifica coincide con el del nucleo", () => {
    expect(nombreDeMidi(40)).toBe("E2");
    expect(nombreDeMidi(55)).toBe("G3");
    expect(nombreDeMidi(69)).toBe("A4");
  });

  it("el nombre y el numero MIDI son la misma nota en los dos sentidos", () => {
    for (const midi of [40, 48, 55, 69, 88]) {
      expect(midiDeNombre(nombreDeMidi(midi))).toBe(midi);
    }
  });

  it("un nombre que no es una nota no se inventa un numero", () => {
    expect(midiDeNombre("H2")).toBeNull();
    expect(midiDeNombre("")).toBeNull();
  });
});

describe("raicesElegibles y cuerdasElegibles", () => {
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

  it("el rango de raices sale del perfil, no de una constante", () => {
    const raices = raicesElegibles(PERFILES);
    // De la cuerda mas grave (E2 = 40) a la mas aguda mas sus trastes (64 + 22).
    expect(raices[0]).toEqual({ midi: 40, nombre: "E2" });
    expect(raices[raices.length - 1].midi).toBe(86);
  });

  it("sin perfiles no se ofrece ninguna raiz inventada", () => {
    expect(raicesElegibles([])).toEqual([]);
  });

  it("las cuerdas elegibles son las que el perfil tiene", () => {
    expect(cuerdasElegibles(PERFILES)).toEqual([1, 6]);
  });
});

describe("posicionesAcertadas", () => {
  const ejercicio = {
    clave: "e",
    nombre: "E",
    descripcion: "",
    tempo: 80,
    perfil: "guitarra_estandar",
    notas: [
      { midi: 40, nombre: "E2", posiciones: [{ cuerda: 6, traste: 0 }], pulsos: 1, referencia_midi: null },
      { midi: 45, nombre: "A2", posiciones: [{ cuerda: 5, traste: 0 }], pulsos: 1, referencia_midi: null },
    ],
  };

  function informe(notas: { indice: number; cents: number | null }[]) {
    return {
      ejercicio: "e",
      completado: false,
      notas: notas.map((n) => ({
        indice: n.indice,
        midi: 40,
        nombre: "E2",
        intentos: 1,
        cents: n.cents,
        instante: 0,
        ayuda_mostrada: false,
      })),
      aciertos_a_la_primera: 0,
      desviacion_mediana_cents: null,
      regularidad_ms: null,
      notas_dificiles: [],
    };
  }

  it("una nota acertada aporta sus posiciones", () => {
    expect(posicionesAcertadas(ejercicio, informe([{ indice: 0, cents: 0 }]))).toEqual([
      { cuerda: 6, traste: 0 },
    ]);
  });

  it("una nota no acertada (cents null) no aporta ninguna", () => {
    expect(posicionesAcertadas(ejercicio, informe([{ indice: 1, cents: null }]))).toEqual([]);
  });

  it("sin ejercicio o sin informe no hay capa tenue", () => {
    expect(posicionesAcertadas(null, informe([{ indice: 0, cents: 0 }]))).toEqual([]);
    expect(posicionesAcertadas(ejercicio, null)).toEqual([]);
  });
});
