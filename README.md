# proyecto_musica

Software libre para practicar guitarra en macOS con el cable Rocksmith Real Tone.
Etapa 1: afinador y monitor de notas en el mástil.

## Requisitos

- macOS con permiso de micrófono concedido al terminal
  (Ajustes del Sistema → Privacidad y seguridad → Micrófono)
- Python 3.13 (pyenv)
- pnpm
- Cable Rocksmith USB Guitar Adapter

## Instalación

```bash
pyenv exec python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd interfaz && pnpm install && pnpm build && cd ..
```

## Uso

```bash
.venv/bin/guitarra
```

Abre `http://127.0.0.1:8000` en el navegador.

Opciones del comando:

- `--puerto`: cambia el puerto en el que escucha el servidor (por defecto 8000).
  Ejemplo: `.venv/bin/guitarra --puerto 8080`.
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

## Verificar el cable

```bash
.venv/bin/python -m herramientas.verificar_cable
```

Comprueba que el dispositivo aparece, mide la latencia y reconoce las notas que toques.

## Pruebas

```bash
.venv/bin/pytest          # núcleo y servidor
cd interfaz && pnpm test  # interfaz
```

Las pruebas de `tests/test_audio_real.py` usan grabaciones reales en `tests/audio/`.
En un checkout nuevo esas grabaciones todavía no existen, así que esas pruebas
aparecen como saltadas (`skipped`): es lo esperado, no un fallo. Para
regenerarlas: `.venv/bin/python -m herramientas.grabar_muestras`.

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

Etapa 1 completa. Las siguientes, según el diseño:

2. Ejercicios generados con corrección de nota, afinación y tempo
3. Grabación de sesiones y medición de progreso
4. Canciones desde tablatura, entrenamiento de oído y efectos
