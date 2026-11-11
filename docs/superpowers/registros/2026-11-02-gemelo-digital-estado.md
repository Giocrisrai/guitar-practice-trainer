# Etapa 3d (el gemelo digital) — estado al parar

**Fecha:** 2026-11-02
**Rama:** `etapa-3d-gemelo`, base `main` = `7546fe5`
**Plan:** `docs/superpowers/plans/2026-11-02-gemelo-digital.md` (16 tareas)
**Spec:** `docs/superpowers/specs/2026-11-02-gemelo-digital-design.md`

Se paró por límite de uso, no por un problema. El ledger completo, con las 14
decisiones y sus costes, está en `.superpowers/sdd/2026-11-02-gemelo-digital/progress.md`
(fuera de git: si se borra, se recupera de `git log`).

## Dónde está

| Tarea | Estado |
|---|---|
| 1. La cuerda pulsada | completa, revisada (`37c534e`) |
| 2. El intérprete y los perfiles | completa, revisada (`dc07ee4`) |
| 3. El conductor, fuera del servidor | completa, revisada, 1 aparcado (`be7a257`) |
| 4. La cadena directa | completa, revisada, 1 aparcado (`10b33ff`) |
| 5. El veredicto | implementada y con dos rulings aplicados (`def1698`), **SIN REVISAR** |
| 6–16 | sin empezar |

Suite: **1148 passed, 30 skipped** (en `main` eran 1039). Árbol limpio.

## Lo primero que tiene que hacer quien reanude

1. Revisar la Tarea 5 (paquete: `review-package <plan> 10b33ff HEAD`). No está
   completa hasta que pase su revisión y su re-revisión acotada.
2. La Tarea 6 (el oráculo) ya tiene su número medido y **no hace falta volver a
   medirlo**: el peor máximo de desfase introducido es **206,3 ms** (pieza
   entera al 40 % de tempo), 44 ms por debajo del techo del detector. Las cinco
   configuraciones medidas salieron limpias.

## Los tres defectos del bucle, ya medidos, que la Tarea 7 tiene que cerrar

Los tres son el mismo sitio visto desde tres sondas distintas, y juntos dicen que
el bucle —el uso central de la etapa 3c, «machacar el compás que fallé»— está roto
de una forma que 1039 pruebas no veían:

1. **El reloj se arrastra ~18 ms por vuelta** y desde la segunda vuelta **ninguna
   nota cuenta como limpia** (−69, −91, −101, −123 ms en cuatro vueltas, con un
   intérprete perfecto). Consecuencia: el tempo automático no puede subir nunca
   con el bucle puesto.
2. **Desde la segunda vuelta las notas se adjudican corridas un índice, y aparece
   un índice que el plan había excluido del tramo.** Quien machaca un compás
   recibe un informe sobre notas que no tocó.
3. **La vuelta 2 entera se desplaza una nota** (`mal_adjudicadas = ((2, 0, 67))`,
   y el midi 67 es la última nota de la vuelta 1), y la vuelta 3 sale limpia: la
   nota de la frontera arrastra la adjudicación de la vuelta siguiente.

Y un cuarto, escalado desde la Tarea 4 y confirmado leyendo el código: **las notas
adjudicadas en el mismo cuadro que da la vuelta desaparecen de `tocadas` antes de
que `observar` retorne**, y no hay API pública que las recupere. El arreglo cabe en
una línea donde ya se guarda `_ultima_vuelta`: guardar también las `tocadas`.

## Dos defectos de producción que el gemelo ya arregló

Ninguno se habría visto sin meter audio por la cadena, que es el argumento de la etapa:

- Con un perfil de **bajo**, la ventana de análisis son 170 ms contra un techo de
  reloj de 100, así que el cabezal arrancaba **70,667 ms corto y en silencio**.
  Con guitarra, el arreglo no cambia nada bit a bit.
- Un **hueco de audio de 5 s entraba entero en la pieza** como si fuera música, y
  la prueba que debía cazarlo quedaba verde porque una mirada por medio refijaba
  la correspondencia del reloj.

## Lo que esta etapa está enseñando

En las cinco tareas, el agujero de pruebas estaba **exactamente en lo que el
implementador había razonado con más cuidado**. Lo bien argumentado se da por
probado y no lo está. Casos concretos:

- El contrato de reproducibilidad del azar, que mi propio brief llamaba «el más
  fácil de romper sin que nada lo note», estaba sin notar: dos mutantes pasaban
  las 20 pruebas.
- Siete mutantes sobrevivían las 11 pruebas de la cadena directa, y la
  instrumentación que los habría matado existía y estaba sin usar.
- Una prueba mentía su nombre e **inflaba el recuento de mutantes**: el poder real
  era 1/1/2 donde se declaraba 2/2/2.

El antídoto que funciona sigue siendo «rompe el código y di cuántas pruebas
cayeron», con los mutantes aplicados de verdad y no razonados.

## Tres defectos de mi propio plan, encontrados por quien lo ejecutaba

1. Pedí una prueba **matemáticamente imposible**: que `brillo` 0,1 y 0,9 sonaran
   distinto con un mapa centrado en 0,5, cuando el filtro del anillo tiene
   magnitud simétrica.
2. La prueba de desafinación que escribí afirmaba algo **sobre el sorteo
   aleatorio**, no sobre el código: pasaba o fallaba según la semilla.
3. La pista que di para traducir entre los dos relojes estaba **al revés**: dije
   que se restara el silencio de cabecera, y restar es justo lo que metía un sesgo
   de 128 ms, porque el cabezal arranca en la muestra cero y corre durante esa
   cabecera.

## Lo que sigue siendo tuyo

El gemelo no juzga nada de esto y la etapa no pretende que lo juzgue: si la ventana
de acierto escalada se siente justa al 50 %, si la cuenta atrás de un compás da
tiempo a colocar la mano, si el click acentuado ayuda o estorba, si los pasos del
5 % son finos o bastos, y si «dos pasadas al 90 %» es la frontera correcta. Y
siguen pendientes grabar las seis cuerdas al aire
(`uv run python -m herramientas.grabar_muestras`) y calibrar el detector de ataques
(`uv run python -m herramientas.calibrar_ataques`).
