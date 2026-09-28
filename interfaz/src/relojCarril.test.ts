import { describe, expect, it } from "vitest";
import { crearReloj, DERIVA_MAXIMA_SUAVE_S } from "./relojCarril";

describe("reloj del carril", () => {
  it("entre paquetes rellena el tiempo con el reloj local", () => {
    const reloj = crearReloj();
    reloj.sincronizar(2.0, 1000);
    expect(reloj.instante(1000)).toBeCloseTo(2.0, 5);
    expect(reloj.instante(1016)).toBeCloseTo(2.016, 3);
    expect(reloj.instante(1033)).toBeCloseTo(2.033, 3);
  });

  it("una deriva pequeña se reparte en varios cuadros, sin saltos", () => {
    // Un salto visible de 20 ms en una nota que viene hacia ti se ve como un
    // tirón; repartido en diez cuadros no se nota.
    const reloj = crearReloj();
    reloj.sincronizar(2.0, 1000);
    reloj.sincronizar(2.02, 1000); // el servidor va 20 ms por delante
    const primero = reloj.instante(1000);
    expect(primero).toBeGreaterThan(2.0);
    expect(primero).toBeLessThan(2.02);
    expect(reloj.instante(1200)).toBeCloseTo(2.02 + 0.2, 2);
  });

  it("una deriva grande se corrige de golpe", () => {
    // Medio segundo de desfase -la pestaña estuvo en segundo plano- no se puede
    // disimular: disimularlo sería mentir durante cinco segundos.
    const reloj = crearReloj();
    reloj.sincronizar(2.0, 1000);
    reloj.sincronizar(5.0, 1000);
    expect(reloj.instante(1000)).toBeCloseTo(5.0, 5);
  });

  it("el umbral entre suave y de golpe es DERIVA_MAXIMA_SUAVE_S", () => {
    const reloj = crearReloj();
    reloj.sincronizar(2.0, 1000);
    reloj.sincronizar(2.0 + DERIVA_MAXIMA_SUAVE_S * 2, 1000);
    expect(reloj.instante(1000)).toBeCloseTo(2.0 + DERIVA_MAXIMA_SUAVE_S * 2, 5);
  });

  it("sin sincronizar nunca, el instante es cero y no NaN", () => {
    expect(crearReloj().instante(1234)).toBe(0);
  });

  it("el tiempo local que va hacia atrás no hace retroceder la pieza", () => {
    // performance.now() no debería retroceder, pero un reloj que lo asume y se
    // equivoca dibuja las notas yendo hacia atrás.
    const reloj = crearReloj();
    reloj.sincronizar(2.0, 1000);
    expect(reloj.instante(900)).toBeGreaterThanOrEqual(2.0);
  });
});
