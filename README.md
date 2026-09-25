# proyecto_musica

Software libre para practicar guitarra en macOS con el cable Rocksmith Real Tone.
Etapa 1: afinador y monitor de notas en el mástil. Etapa 2a: ejercicios
monofónicos (escalas, arpegios, intervalos y lectura) con corrección de nota,
afinación y tempo.

## Requisitos

- macOS con permiso de micrófono concedido al terminal
  (Ajustes del Sistema → Privacidad y seguridad → Micrófono)
- Python 3.13 (pyenv) — el archivo `.python-version` fija `3.13.1`, y `uv`
  lo respeta automáticamente al crear el entorno
- [uv](https://docs.astral.sh/uv/) como gestor del entorno Python
- pnpm
- Cable Rocksmith USB Guitar Adapter

## Instalación

```bash
uv sync
cd interfaz && pnpm install && pnpm build && cd ..
```

`uv sync` crea `.venv/` con Python 3.13.1 (según `.python-version`), instala las
dependencias de ejecución y el proyecto en modo editable, según lo fijado en
`uv.lock`.

## Uso

```bash
uv run guitarra
```

Abre `http://127.0.0.1:8000` en el navegador.

Opciones del comando:

- `--puerto`: cambia el puerto en el que escucha el servidor (por defecto 8000).
  Ejemplo: `uv run guitarra --puerto 8080`.
- `--sin-navegador`: levanta el servidor sin abrir el navegador automáticamente.

Si con el cable conectado el afinador avisa con el estado `otro_dispositivo`, es
que el sistema está capturando otra entrada de audio (por ejemplo el micrófono
del portátil) en vez del cable Rocksmith, aunque este esté enchufado. Elige el
cable en el selector **Dispositivo** de la pantalla del afinador, junto al de
afinación; la elección se guarda y se reutiliza en el siguiente arranque.

Si desconectas el cable mientras tocas, el afinador pasa a silencio y vuelve a
abrirlo solo en cuanto lo enchufas de nuevo: no hace falta reiniciar nada.

El botón **Calibrar ruido** mide el piso de ruido de tu equipo durante dos
segundos —no toques nada mientras dura— y guarda el umbral resultante en la
configuración. El valor vigente se muestra siempre junto al botón.

### Ejercicios

Junto al afinador hay un módulo de ejercicios con cuatro familias: escalas,
arpegios, intervalos y lectura (posiciones sueltas en el mástil). Cada
ejercicio se resuelve nota a nota: mientras no toques la nota pedida el
ejercicio no avanza, y si te equivocas se te dice qué nota sonó en su lugar.
Una nota correcta pero desafinada **sí** cuenta como acierto —la afinación no
bloquea el avance—, y su desviación en cents queda registrada para el informe
final. Si fallas la misma nota cinco veces seguidas, el mástil la resalta
para ayudarte a encontrarla.

Al terminar el ejercicio, el informe muestra los aciertos a la primera, las
notas que costaron más intentos y la desviación mediana en cents.

**Límite conocido del evaluador:** dos pulsaciones seguidas de la misma nota
solo se distinguen si entre ellas hay un hueco de unos 63 ms en el que el
detector de tono deja de dar esa nota como creíble. La caída de volumen no
ayuda: el evaluador compara **nombres de nota**, no niveles, así que por muy
articulada que sea la segunda pulsación queda descartada mientras el tono siga
siendo creíble. Cuando la nota pedida cambia el problema no existe, porque la
altura nueva sí es algo que el evaluador ve. Los ejercicios generados nunca
piden la misma nota dos veces seguidas, precisamente por esto; si aun así te
quedas sin poder avanzar, lo que evita que te atasques es el aviso por tiempo,
que resalta la nota en el mástil a los doce segundos de haber detectado señal
sin resolver ninguna pulsación.

## Verificar el cable

```bash
uv run python -m herramientas.verificar_cable
```

Comprueba que el dispositivo aparece, mide la latencia y reconoce las notas que toques.

## Calibrar la deteccion de ataques

```bash
uv run python -m herramientas.calibrar_ataques
```

Pulsa una cuerda ocho veces separadas y la herramienta propone el salto y el
refractario que mejor cuentan tus pulsaciones. Los valores por defecto estan
elegidos a ojo; esto los ajusta a tu pua y tu pastilla.

## Pruebas

```bash
uv run pytest             # núcleo y servidor
cd interfaz && pnpm test  # interfaz
```

Las pruebas de `tests/test_audio_real.py` y `tests/test_ataques_reales.py` usan
las mismas grabaciones reales de `tests/audio/`. En un checkout nuevo esas
grabaciones todavía no existen, así que esas pruebas aparecen como saltadas
(`skipped`): es lo esperado, no un fallo. Para regenerarlas:
`uv run python -m herramientas.grabar_muestras`.

## Estructura

- `nucleo/` — captura de audio, análisis y teoría musical. Python puro, sin
  dependencias del servidor ni de la interfaz.
- `servidor/` — FastAPI: registro de módulos, configuración, diagnóstico y
  emisión por WebSocket. El registro de módulos es lo que permitirá añadir
  ejercicios y canciones en las etapas siguientes sin tocar el armazón.
- `interfaz/` — React + Vite.
- `herramientas/` — utilidades de línea de comandos.
- `docs/superpowers/` — especificación y plan.

## Estado

Etapas 1 y 2a completas. Las siguientes, según el diseño:

2b. Ejercicios de acordes
3. Grabación de sesiones y medición de progreso
4. Canciones desde tablatura, entrenamiento de oído y efectos
