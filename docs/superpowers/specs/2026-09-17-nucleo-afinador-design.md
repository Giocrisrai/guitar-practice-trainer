# Diseño: núcleo de audio y afinador (etapa 1)

Fecha: 2026-09-17
Estado: aprobado para implementación

## 1. Propósito

Construir un software libre y gratuito para practicar guitarra en macOS usando el
cable Rocksmith Real Tone. La etapa 1 entrega el núcleo técnico —captura de audio
y detección de notas— junto con la primera interfaz usable: un afinador y un
monitor de notas en el mástil.

El objetivo de la etapa 1 no es solo el afinador. Es **validar la cadena completa**
(cable → CoreAudio → Python → análisis → pantalla) con hardware real, para que las
etapas siguientes se apoyen en una base medida y no en suposiciones.

## 2. Hardware verificado

Comprobado el 2026-09-17 en el equipo destino (MacBook Pro M1 Pro, macOS 26.3):

| Propiedad | Valor |
|---|---|
| Nombre del dispositivo | `Rocksmith USB Guitar Adapter` |
| Fabricante | Hercules |
| Canales de entrada | 1 (mono) |
| Frecuencia de muestreo | 48000 Hz |
| Transporte | USB, class-compliant (sin drivers) |
| Salida de audio | Ninguna |

Niveles medidos con la guitarra del usuario, volumen al máximo, rasgueo fuerte:

| Medida | Valor |
|---|---|
| Pico | −27 dBFS |
| Medio | −45 dBFS |

Consecuencias de diseño, derivadas de estas mediciones:

- **El cable entrega nivel bajo.** Un pico de −27 dBFS usa el 4,5 % del rango.
  La captura se hace en `float32` con ganancia digital ajustable por el usuario.
  Capturar en entero de 16 bits desperdiciaría la mitad de los bits disponibles.
- **El cable no tiene salida.** El monitoreo (oírse a uno mismo) sale por los
  altavoces o auriculares del Mac, nunca por el cable. La etapa 1 no monitorea.
- **La entrada es mono.** Un solo canal, sin mezcla ni selección de canal.

El sistema tiene además tres dispositivos de audio virtuales instalados (Microsoft
Teams, Zoom, Loom) y el dispositivo de entrada por defecto es el micrófono
integrado del MacBook. Por tanto: **el usuario elige el dispositivo explícitamente
y la elección se guarda.** Tomar "la entrada por defecto" capturaría el micrófono
del portátil en lugar de la guitarra.

## 3. Permisos de macOS

macOS exige permiso de micrófono (TCC) para *enumerar y abrir* entradas de audio.
El permiso se concede a la aplicación anfitriona (Terminal, iTerm, VS Code), no al
comando. Sin él, la lista de dispositivos vuelve vacía en lugar de dar un error.

Verificado: el terminal del usuario **ya tiene** el permiso concedido.

Requisito derivado: el diagnóstico debe distinguir tres estados que a simple vista
producen el mismo síntoma (nada funciona):

1. Permiso denegado → la lista de dispositivos viene vacía.
2. Dispositivo ausente → hay dispositivos, pero no el Rocksmith.
3. Sin señal → el dispositivo abre, pero la energía no supera el umbral.

Cada uno tiene un mensaje propio y una acción sugerida. Un error genérico obligaría
al usuario a adivinar cuál de los tres tiene.

## 4. Arquitectura

Tres capas con una regla que las gobierna: **`nucleo/` no importa nada de
`servidor/` ni de `interfaz/`.** Esto permite usar el núcleo desde un notebook de
Jupyter para experimentar con los algoritmos, y es lo que hará que las etapas 2 a 4
se apoyen en el mismo tronco sin reescribirlo.

```
proyecto_musica/
├── nucleo/
│   ├── captura.py      # hilo de audio, buffer circular
│   ├── analisis.py     # funciones puras: energía, YIN, suavizado
│   ├── musica.py       # teoría: frecuencia↔nota, mástil, afinaciones
│   └── afinaciones.py  # perfiles (guitarra, bajo, drop D, ...)
├── servidor/
│   ├── app.py          # FastAPI: sirve la interfaz y los endpoints
│   ├── websocket.py    # emisión de resultados a ~30 Hz
│   └── diagnostico.py  # los tres estados de la sección 3
├── interfaz/           # React + Vite (pnpm)
├── tests/              # pytest
├── notebooks/          # experimentación
└── docs/
```

### 4.1 `nucleo/captura.py`

Un hilo de audio gestionado por `sounddevice` (PortAudio) lee bloques de 512
muestras a 48 kHz (10,7 ms por bloque).

**Regla única e inviolable del callback de audio: nunca bloquearse.** Sin cálculos
pesados, sin red, sin locks que puedan esperar, sin asignación de memoria. Copia el
bloque al buffer circular y retorna. Un callback que se retrasa produce un chasquido
audible y muestras perdidas.

El buffer circular es preasignado, de tamaño fijo, y sobrescribe lo más antiguo. Si
el consumidor se atrasa, se pierden muestras viejas — que es el comportamiento
correcto para un afinador, donde solo importa el presente.

### 4.2 `nucleo/analisis.py`

Funciones **puras**: mismas muestras de entrada, mismo resultado, sin estado
interno. Esta pureza es lo que hace posible la estrategia de pruebas de la sección 6.

Un hilo consumidor toma del buffer circular una ventana solapada y la procesa en
tres pasos:

**a) Compuerta de ruido.** Si la energía RMS de la ventana está bajo el umbral, el
resultado es `Silencio` y no se calcula nada más. Sin esto, el afinador oscila
permanentemente con el piso de ruido del cable.

El umbral **no se fija por intuición**: se determina midiendo el piso de ruido real
del equipo (guitarra conectada, sin tocar) y situando el umbral por encima con un
margen. El software incluye un comando de calibración que repite esta medición y
guarda el valor en la configuración, de modo que sirva también en otros equipos o
con otras pastillas.

**b) Detección de frecuencia (YIN).** Devuelve dos valores, y ambos importan:

- La frecuencia fundamental estimada.
- Una **medida de confianza**. Sin ella no se puede distinguir una nota real de un
  armónico o de ruido de dedos. Un resultado de baja confianza se descarta en lugar
  de mostrarse.

El **tamaño de la ventana es función del perfil de afinación**, no una constante.
YIN necesita al menos dos periodos completos de la frecuencia más grave a detectar:

| Perfil | Nota más grave | Periodo | Ventana | Duración |
|---|---|---|---|---|
| Guitarra estándar | E2 = 82,41 Hz | 12,1 ms | 4096 muestras | 85 ms |
| Bajo 5 cuerdas | B0 = 30,87 Hz | 32,4 ms | 8192 muestras | 171 ms |

Fijar la ventana en una constante implicaría, o bien no poder detectar un bajo, o
bien imponer a la guitarra el doble de retardo del necesario. Es una decisión que
cuesta poco ahora y mucho después.

**c) Suavizado.** Mediana móvil sobre las últimas detecciones (~100 ms). Se elige
mediana y no media porque la mediana descarta detecciones atípicas aisladas —
justo el tipo de error que produce un salto de octava— en lugar de promediarlas.

Un afinador que salta en cada bloque es inusable; uno que promedia sobre ~100 ms se
lee cómodo y sigue siendo responsivo.

### 4.3 `nucleo/musica.py`

Aritmética pura, sin audio. Convierte frecuencia en nota y desviación:

```
cents = 1200 · log₂(f / f_ref)
```

con `f_ref` = A4 = 440 Hz por defecto, configurable.

También traduce una nota a sus posiciones posibles en el mástil. Aquí existe una
**ambigüedad que la física no resuelve**: un La de 110 Hz puede ser la 5ª cuerda al
aire o la 6ª cuerda en el traste 5. Son la misma frecuencia con timbres apenas
distinguibles.

Decisión: la etapa 1 **resalta todas las posiciones posibles** en lugar de elegir
una. Mostrar una sola posición sería fingir una certeza que el software no tiene, y
enseñaría al usuario a desconfiar de la pantalla.

### 4.4 `nucleo/afinaciones.py`

Un perfil de afinación es un dato, no código: nombre, lista de cuerdas con su nota
y frecuencia, número de trastes. Con esta estructura, el bajo es un perfil más.

Perfiles incluidos en la etapa 1:

| Perfil | Cuerdas (grave → aguda) |
|---|---|
| Guitarra estándar | E2 82,41 · A2 110,00 · D3 146,83 · G3 196,00 · B3 246,94 · E4 329,63 |
| Guitarra Drop D | D2 73,42 · A2 110,00 · D3 146,83 · G3 196,00 · B3 246,94 · E4 329,63 |
| Bajo 4 cuerdas | E1 41,20 · A1 55,00 · D2 73,42 · G2 98,00 |
| Bajo 5 cuerdas | B0 30,87 · E1 41,20 · A1 55,00 · D2 73,42 · G2 98,00 |

### 4.5 `servidor/`

FastAPI sirve la interfaz compilada y expone:

- `GET /api/dispositivos` — lista las entradas de audio disponibles.
- `GET /api/diagnostico` — los tres estados de la sección 3.
- `GET|PUT /api/config` — dispositivo elegido, perfil de afinación, ganancia,
  umbral de ruido, frecuencia de referencia.
- `POST /api/calibrar` — mide el piso de ruido y fija el umbral.
- `WS /ws/notas` — flujo de resultados.

El WebSocket emite a **~30 Hz**, no a la velocidad del análisis. La pantalla no
puede mostrar más rápido que eso, y saturar el socket solo añadiría retardo. Se
envía siempre el último resultado disponible; los cuadros atrasados se descartan.
El usuario ve el presente, nunca una cola acumulada.

Mensaje emitido:

```json
{
  "estado": "nota",
  "frecuencia": 82.4,
  "nota": "E2",
  "cents": -3.2,
  "confianza": 0.94,
  "nivel_db": -31.5,
  "posiciones": [{"cuerda": 6, "traste": 0}],
  "cuerda_objetivo": 6,
  "afinada": true
}
```

`estado` es uno de `nota`, `silencio` o `error`.

### 4.6 `interfaz/`

React + Vite, gestionado con pnpm. Se suscribe al WebSocket y dibuja. **No calcula
nada musical**: solo representa lo que recibe. Si la interfaz necesitara hacer
teoría musical, sería señal de que el núcleo dejó algo sin resolver.

Pantalla única, con todo visible a la vez:

```
┌─ proyecto_musica ────────── ● Rocksmith USB ─┐
│                                               │
│   ♭ ────────────┼──────────── ♯   E2          │
│            -3 cents  ✔ AFINADA                │
│                                               │
│   E ●──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬        │
│   B ───┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼        │
│   G ───┼──┼──┼──┼──●──┼──┼──┼──┼──┼──┼        │
│   D ───┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼        │
│   A ───┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼        │
│   E ───┼──┼──┼──┼──┼──┼──┼──┼──┼──┼──┼        │
│        3     5     7     9    12              │
│                                               │
│  nivel ▁▃▅█▅▃▁   82.4 Hz   latencia 12 ms     │
└───────────────────────────────────────────────┘
```

Elementos: aguja de afinación con tolerancia de ±5 cents para considerar "afinada",
mástil con las posiciones posibles resaltadas, medidor de nivel de entrada,
frecuencia, latencia medida y estado del dispositivo.

## 5. Manejo de errores

Tres fallos son esperables y cada uno tiene su propia presentación:

| Situación | Detección | Qué muestra |
|---|---|---|
| Sin permiso de micrófono | Lista de dispositivos vacía | Instrucción concreta: Ajustes → Privacidad → Micrófono |
| Dispositivo desaparecido | El stream falla o el dispositivo sale de la lista | Aviso de desconexión y reconexión automática al volver |
| Sin señal | Energía bajo el umbral durante más de 5 s | Sugiere revisar el volumen de la guitarra, que es la causa más frecuente |

La reconexión es automática porque desconectar el cable es algo que pasa a menudo y
obligar a reiniciar el programa sería un castigo desproporcionado.

## 6. Estrategia de pruebas

Las funciones de análisis son puras, y de ahí sale toda la estrategia: se puede
generar la entrada con numpy y verificar la salida exactamente, sin hardware y en
milisegundos.

**Pruebas sintéticas** (`pytest`, sin guitarra):

- Senoide de 82,41 Hz → detecta E2 con 0 cents de desviación.
- Barrido por las 6 cuerdas al aire → cada una con su nota correcta.
- Desafinación conocida (±10, ±25, ±50 cents) → devuelve exactamente esos cents.
- Nota con armónicos → detecta la fundamental, no el segundo armónico. Este es el
  modo de fallo clásico de un detector de tono y merece prueba propia.
- Ruido blanco → devuelve `silencio`, no una nota inventada.
- Señal decreciente → verifica en qué energía deja de detectar.
- Nota de bajo a 30,87 Hz con la ventana del perfil correspondiente → detecta B0.

**Pruebas con audio real.** Se graban unos segundos de cada cuerda al aire de la
guitarra del usuario y se guardan como archivos de prueba versionados. Esto
convierte el instrumento concreto en una prueba automática permanente: si un cambio
de algoritmo rompe la detección de la 6ª cuerda, la prueba falla antes de que el
usuario lo note tocando.

**Prueba de latencia.** Se mide el tiempo entre la llegada del bloque y la emisión
por WebSocket, y se muestra en pantalla. La latencia es un dato observable, no una
promesa del diseño.

## 7. Dependencias

Todo libre y gratuito.

| Componente | Herramienta | Motivo |
|---|---|---|
| Python | 3.13.1 (pyenv) | Versión global del equipo |
| Captura de audio | `sounddevice` | Enlace con PortAudio, funciona con CoreAudio sin drivers |
| Cálculo numérico | `numpy`, `scipy` | Preferencia establecida sobre implementaciones manuales |
| Servidor | `fastapi`, `uvicorn` | WebSocket y servidor estático en una sola pieza |
| Pruebas | `pytest` | Preferencia establecida |
| Interfaz | React + Vite, con pnpm | pnpm es el gestor del equipo |

Idioma del código: español en comentarios y nombres de variables.

## 8. Alcance de la etapa 1

**Incluye:** captura desde el dispositivo elegido, detección monofónica de notas,
afinador con desviación en cents, mástil con posiciones posibles, perfiles de
afinación (guitarra y bajo), calibración del umbral de ruido, diagnóstico de los
tres estados de error, medición de latencia, y la batería de pruebas de la
sección 6.

**No incluye, y es deliberado:**

- Detección de acordes (polifonía) — etapa 2.
- Ejercicios y corrección — etapa 2.
- Grabación y análisis de sesiones — etapa 3.
- Efectos y simulación de amplificador — etapa 4, y con la intención de **integrar**
  Neural Amp Modeler o GuitarML antes que escribir procesamiento en tiempo real
  desde cero.
- Empaquetado como aplicación nativa de macOS.

## 9. Etapas siguientes

| Etapa | Contenido | Se apoya en |
|---|---|---|
| 1 | Núcleo, afinador, mástil | — |
| 2 | Ejercicios generados (escalas, acordes, arpegios) con corrección de nota, afinación y tempo; detección de acordes | Detectores intercambiables del núcleo |
| 3 | Grabación de sesiones, transcripción, medición de progreso | Captura y análisis de la etapa 1 |
| 4 | Tablaturas (Guitar Pro, MusicXML), entrenamiento de oído y ritmo, efectos | Todo lo anterior |

Cada etapa recibe su propio diseño cuando se llegue a ella. Este documento cubre la
etapa 1 y fija únicamente las decisiones arquitectónicas que, de no tomarse ahora,
obligarían a reescribir el núcleo más adelante: detectores intercambiables, perfiles
de afinación como dato, ventana de análisis dependiente del perfil, y captura en
float32.
