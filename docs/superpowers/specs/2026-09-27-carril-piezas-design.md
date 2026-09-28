# Etapa 3a — El carril: piezas que vienen hacia ti

**Fecha:** 2026-09-27
**Estado:** propuesta
**Etapas previas:** 1 (núcleo y afinador), 2a (ejercicios monofónicos)

## 1. Qué se construye y por qué

Hoy el software te dice **qué** nota tocar y espera a que la aciertes. Eso enseña
a encontrar notas en el mástil, pero no a tocar música: en una pieza real la
música no espera, y la nota que llega tarde ya no vale igual.

Esta etapa introduce el **carril**: una vista en la que las notas se acercan
sobre el mástil y hay que tocarlas cuando llegan, al estilo de Rocksmith. Con
ella entra en el modelo algo que hasta ahora no existía, el **tiempo absoluto**:
cada nota tiene un instante y una duración, no solo un turno.

Es también la base de las dos etapas siguientes, que no se pueden construir sin
ella: importar canciones de Guitar Pro, MusicXML, MIDI y tablatura ASCII (3b), y
practicar una pieza entera con compases, bucles y tempo ajustable (3c).

### Fuera de alcance, deliberadamente

- **Importar archivos.** Toda la etapa 3b. Aquí las piezas salen de los
  generadores de ejercicios que ya existen.
- **Acordes.** Una sola voz. El detector de tono es monofónico: dos cuerdas a la
  vez no se distinguen, y fingir lo contrario daría correcciones falsas.
- **Ligados, bends, armónicos y silencios expresivos.** El modelo los ignora.
- **Digitación óptima.** Se elige la posición más cercana a la anterior, que es
  suficiente para una escala y claramente insuficiente para una pieza. El
  problema de verdad —minimizar el movimiento de la mano sobre toda la pieza— es
  de la etapa 3b.
- **Puntuación y progresión.** No hay estrellas, ni niveles, ni historial.

## 2. El modelo: `Pieza`

Vive en `nucleo/piezas/modelo.py`, junto a `nucleo/ejercicios/`. **El modelo no
importa nada de `ejercicios`**: una pieza leída de un archivo de Guitar Pro no
tiene nada que ver con un ejercicio generado, y atar los dos ahora obligaría a
desatarlos en 3b. La traducción entre ambos existe, pero vive aislada en
`nucleo/piezas/desde_ejercicio.py`, que sí importa los dos: es el único punto de
contacto, y en 3b tendrá al lado un `desde_guitarpro.py` sin que el modelo
cambie.

```python
@dataclass(frozen=True)
class NotaEnPieza:
    """Una nota con su sitio en el mástil y su sitio en el tiempo."""
    midi: int
    cuerda: int              # numeración del perfil: 6 es la más grave
    traste: int              # 0 es al aire
    inicio_pulsos: float     # desde el comienzo de la pieza
    duracion_pulsos: float

@dataclass(frozen=True)
class Pieza:
    nombre: str
    perfil: str              # clave de PERFILES: la afinación con que se escribió
    tempo: int               # pulsos por minuto
    compas: tuple[int, int]  # (4, 4)
    notas: tuple[NotaEnPieza, ...]   # ordenadas por inicio_pulsos
```

**Dos decisiones que conviene justificar.**

*Una sola posición por nota, no todas.* `NotaEsperada`, el modelo de los
ejercicios, publica **todas** las posiciones donde vive esa nota, porque en un
ejercicio por turnos da igual dónde la toques: un La de 110 Hz está en la quinta
al aire y en el sexto traste de la sexta, y las dos valen. El carril tiene que
dibujar **una**, así que la elige. Eso convierte la elección en una decisión del
software, y por tanto en algo que puede estar mal.

*El tiempo en pulsos, no en segundos.* Practicar lento es bajar el tempo, y si
las notas guardaran segundos habría que reescribir la pieza entera para hacerlo.
Con pulsos, el tempo es un factor de conversión: `segundos = pulsos · 60 / tempo`.

### Conversión desde un ejercicio

`nucleo/piezas/desde_ejercicio.py` traduce un `Ejercicio` en una `Pieza`:

- El instante de cada nota es la suma de los `pulsos` de las anteriores, que el
  modelo de ejercicios ya trae.
- La posición se elige minimizando `|traste - traste_anterior|` entre las
  `posiciones` que la nota ofrece; a igualdad, gana la cuerda más grave. La
  primera nota toma la posición de traste más bajo. **Es una heurística local y
  se documenta como tal**: sobre una escala en una posición del mástil acierta
  siempre porque todas las notas caben en cuatro trastes, y sobre una pieza real
  produciría saltos absurdos. La sustituye la etapa 3b.
- Una nota sin ninguna posición alcanzable es un error de programación aguas
  arriba, no un caso a tolerar: se lanza `ValueError` nombrando la nota.

## 3. El reloj, que es lo que hace que esto funcione o no

El estado del ejercicio ya viaja por WebSocket a **30 Hz**. Un carril refrescado
a 30 Hz se ve a tirones, y uno que interpolara con su propio reloj se separaría
poco a poco de lo que el evaluador puntúa: verías la nota llegar y el software te
diría que la tocaste pronto.

**La regla:** hay un solo reloj, el del hilo de análisis, y el navegador nunca
inventa tiempo, solo lo rellena.

- El servidor publica en cada paquete `instante_pieza`: segundos transcurridos
  desde que la pieza arrancó, medidos con el mismo `time.monotonic()` con el que
  el evaluador sella los ataques.
- El navegador guarda ese valor junto al `performance.now()` de cuando llegó, y
  entre paquetes dibuja a 60 fps con `requestAnimationFrame` sumando el tiempo
  local transcurrido.
- Al llegar el paquete siguiente **corrige la deriva**, sin saltos: si la
  diferencia es menor que un umbral (30 ms) se absorbe repartiéndola en los
  cuadros siguientes; si es mayor —una pausa del sistema, una pestaña en segundo
  plano— se salta de golpe, porque disimular medio segundo es peor que el salto.

## 4. Qué se corrige, y en qué se diferencia de los ejercicios

**El evaluador no se reescribe.** `EvaluadorEjercicio` ya decide cuándo una nota
se da por tocada, con dos disparadores y tres reglas no negociables que costaron
tres rondas de correcciones. El carril lo envuelve, no lo sustituye.

Lo que añade es la **ventana temporal**. En el modo por turnos la nota espera;
aquí no:

| | Ejercicio por turnos | Carril |
|---|---|---|
| Si fallas | la nota espera a que la aciertes | la nota pasa y queda marcada |
| Si tardas | no importa | se anota el desfase |
| Ayuda | tras 5 fallos | no hay: la pieza no se detiene |

Cada nota tocada se clasifica por su desfase respecto al instante ideal:
**a tiempo** (±80 ms), **pronto** o **tarde**. El umbral de 80 ms no es
arbitrario: por debajo de unos 30 ms dos ataques no se perciben separados, y por
encima de 100 ms el oyente ya lo oye como error rítmico; 80 ms deja margen para
la latencia del sistema (13,8 ms medidos con este cable) sin volverse indulgente.
**Es un valor que hay que ajustar tocando**, y se expone como parámetro.

**La afinación no descalifica y el ritmo tampoco.** Una nota correcta fuera de
ventana cuenta como acertada, con su desfase anotado: es la misma regla que ya
gobierna la afinación, por la misma razón — el software informa, no castiga.

**Lo que ves de tu afinación.** Cada nota tocada se queda pintada en el carril
con su desviación en cents y un color que la distingue de un vistazo. Eso
convierte un problema de afinación en un **patrón visible**: si todas las notas
de una cuerda salen bajas, no es tu dedo, es la cuerda.

## 5. Lo que el servidor publica

Un módulo nuevo, `servidor/piezas.py`, con `SesionCarril`, hermana de
`SesionPractica`: se suscribe al flujo de análisis como observadora, envuelve al
evaluador y lleva el reloj. Se registra como módulo `carril` en el registro que
ya existe, así que aparece en la pantalla sin tocar la navegación.

```
GET  /api/piezas/desde-ejercicio   genera un ejercicio y lo devuelve como Pieza
POST /api/piezas/iniciar           arranca el carril
POST /api/piezas/detener
GET  /api/piezas/estado
WS   /ws/piezas                    estado a 30 Hz, con instante_pieza
```

**La pieza no viaja por el WebSocket.** Se devuelve entera en la respuesta de
`/iniciar` y el navegador la guarda; mandar cientos de notas treinta veces por
segundo sería desperdiciar el canal en datos que no cambian. Por el WebSocket va
solo lo que cambia: `instante_pieza`, el índice de la nota en curso, y lo ya
tocado con su desfase y sus cents. **Lo que la interfaz no calcula**: qué nota está en curso, si una nota fue
a tiempo, y la clasificación de la desviación. Todo eso lo decide el núcleo, por
la misma razón que en la etapa 2a hubo que quitárselo cuatro veces a la interfaz.

## 6. La interfaz

`interfaz/src/Carril.tsx` dibuja en **`<canvas>`**, no en SVG: a 60 fps, React
tendría que reconciliar cientos de nodos por cuadro. Pero todo lo que puede estar
mal sale a `interfaz/src/geometriaCarril.ts`, un módulo **puro y sin canvas**:

- `notasVisibles(pieza, instante, ventana_s)` — cuáles caen en pantalla
- `posicionDeNota(nota, instante, alto, ancho)` — a qué píxel
- `colorDeDesviacion(cents)` — la escala de color de la afinación

El canvas solo pinta lo que esas funciones devuelven. Las pruebas van contra
ellas, con números.

Junto al carril, una **vista escrita** del mismo `Pieza`: tablatura de seis
líneas y pentagrama, estáticas, para estudiar la pieza y repasar lo tocado. Es la
misma estructura dibujada de otra manera, y se prueba igual: una función pura que
coloca cada nota, y el dibujo encima.

## 7. Cuando algo va mal

| Situación | Qué pasa |
|---|---|
| Se pierde la señal | El carril **se detiene**, igual que el metrónomo. Un carril que sigue corriendo con el cable desenchufado te hace fallar notas que nunca sonaron. Al volver la señal, se reanuda donde estaba. |
| La pieza está en otra afinación que la activa | Se rechaza con 400 nombrando las dos: dibujar trastes que tu instrumento no tiene es peor que no dibujar nada. |
| La pestaña pasa a segundo plano | `requestAnimationFrame` se detiene solo. Al volver, el primer paquete corrige el salto de golpe. |
| El navegador va lento | Se dibuja lo que dé tiempo: el reloj manda, no el número de cuadros. |
| No hay salida de audio | El carril funciona sin metrónomo, como los ejercicios. |

## 8. Cómo se prueba

- **Geometría y tiempo:** funciones puras, pruebas con números. Ni canvas ni
  navegador.
- **El reloj:** se inyecta uno falso y se avanza a mano; se comprueba qué debería
  estar visible y qué desfase se anota. Nada de `sleep`.
- **La conversión desde ejercicio:** que los instantes acumulan bien, que la
  posición elegida es la más cercana, y que una escala de una posición no salta
  de traste.
- **La ventana temporal:** una nota a tiempo, una pronto y una tarde, con el
  desfase exacto esperado.
- **Ninguna prueba abre el dispositivo de audio.** Como en las dos etapas
  anteriores.

Lo que **no** tiene prueba automática es si se ve bien y si se juega bien. Eso se
verifica tocando, y queda anotado como tal.

## 9. Riesgos

1. **Los 80 ms de ventana no están medidos con una guitarra.** Salen del umbral
   de percepción y de la latencia medida, no de tocar. Es el mismo riesgo que los
   parámetros del detector de ataques en la etapa 2a, y se cierra igual: tocando
   y ajustando.
2. **El detector de tono tarda en dar una lectura creíble tras el ataque.** Ya se
   sabe de la etapa 2a, y por eso el instante que cuenta es el del ataque de
   energía. Si en el carril ese retraso resultara mayor que la ventana, habría
   que ensancharla, no cambiar el reloj.
3. **La heurística de digitación es local.** Sobre las escalas de la etapa 2a
   acierta por construcción; sobre una pieza importada no. Está acotado porque en
   3a no hay piezas importadas.
4. **60 fps en un canvas con el análisis corriendo.** El hilo de análisis va a
   47 Hz y el navegador es otro proceso, así que no deberían estorbarse. Si se
   notara, se baja a 30 fps: se ve peor, no se rompe.
