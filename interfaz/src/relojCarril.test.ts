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

  it("un instante de servidor menor que el ya mostrado no hace retroceder la pieza", () => {
    // El servidor puede mandar un instante hasta ~0.27 s menor al recuperarse de
    // un corte de señal. "En cuanto llega un paquete, ese manda" no puede
    // significar "salta hacia atrás": el cabezal se queda quieto en el punto más
    // alto ya mostrado hasta que el propio avance del servidor lo alcanza.
    const reloj = crearReloj();
    reloj.sincronizar(2.0, 1000);
    const techo = reloj.instante(1096);
    expect(techo).toBeCloseTo(2.096, 5);

    reloj.sincronizar(1.8, 1100); // el servidor retrocede 0.3 s: deriva grande

    // Justo tras el paquete que retrocede, el reloj no debe mostrar menos de lo
    // que ya mostraba.
    expect(reloj.instante(1100)).toBeGreaterThanOrEqual(techo);
    // Casi 200 ms después el servidor (1.8 + 0.192 = 1.992) sigue sin alcanzar
    // el techo (2.1): la pieza sigue quieta, no ha retrocedido.
    expect(reloj.instante(1292)).toBeGreaterThanOrEqual(techo);
    // En cuanto el avance del propio servidor alcanza el techo (en 1.8 + 0.3 =
    // 2.1, es decir ahoraLocal 1400), el reloj retoma el seguimiento normal.
    expect(reloj.instante(1450)).toBeCloseTo(1.8 + 0.35, 5);
  });

  it("el instante nunca es menor en ningún punto tras un retroceso del servidor", () => {
    // No basta con comprobar dos muestras sueltas: el máximo mostrado hasta
    // ahora nunca debe bajar en ninguna lectura posterior, por mucho que se
    // muestree. Crucial: el bucle empieza ANTES del segundo sincronizar, para
    // que el pico previo (~2.1, alcanzado mientras el reloj sigue al primer
    // paquete) quede registrado antes de que el servidor retroceda.
    const reloj = crearReloj();
    reloj.sincronizar(2.0, 1000);
    let maximo = -Infinity;
    for (let ahoraLocal = 1000; ahoraLocal <= 1500; ahoraLocal += 10) {
      if (ahoraLocal === 1100) reloj.sincronizar(1.8, 1100);
      const valor = reloj.instante(ahoraLocal);
      expect(valor).toBeGreaterThanOrEqual(maximo);
      maximo = Math.max(maximo, valor);
    }
  });

  it("la corrección es continua al cruzar DERIVA_MAXIMA_SUAVE_S, sin escalón", () => {
    // Antes, una deriva de exactamente el umbral corregía ~10 % en el primer
    // cuadro, y una deriva apenas por encima corregía el 100 %: un salto de
    // ~27 ms, del mismo orden que el tirón que esta rampa existe para evitar.
    // Cruzar el umbral por una diferencia infinitesimal no debe notarse.
    const valorEn = (derivaExtra: number) => {
      const reloj = crearReloj();
      reloj.sincronizar(2.0, 1000);
      reloj.sincronizar(2.0 + DERIVA_MAXIMA_SUAVE_S + derivaExtra, 1000);
      return reloj.instante(1000);
    };

    const justoDebajo = valorEn(-1e-6);
    const enElUmbral = valorEn(0);
    const justoEncima = valorEn(1e-6);

    expect(Math.abs(enElUmbral - justoDebajo)).toBeLessThan(0.001);
    expect(Math.abs(justoEncima - enElUmbral)).toBeLessThan(0.001);
  });
});
