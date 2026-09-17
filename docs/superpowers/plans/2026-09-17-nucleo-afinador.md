# Núcleo de audio y afinador — Plan de implementación (etapa 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el núcleo de captura y análisis de audio del cable Rocksmith más el primer módulo de la aplicación (afinador y monitor de mástil), dejando registrada la arquitectura de módulos sobre la que se montarán ejercicios, canciones y efectos.

**Architecture:** Tres capas. `nucleo/` es Python puro (captura en un hilo de audio, análisis con funciones puras numpy/scipy, teoría musical) y no importa nada del servidor ni de la interfaz. `servidor/` es FastAPI: expone un registro de módulos, endpoints de configuración y diagnóstico, y emite los resultados del análisis por WebSocket a ~30 Hz. `interfaz/` es React + Vite: un armazón que lista los módulos registrados y dibuja el que esté activo, sin calcular nada musical.

**Tech Stack:** Python 3.13.1 (pyenv), `sounddevice` (PortAudio/CoreAudio), `numpy`, `scipy`, `fastapi`, `uvicorn`, `pytest`; React + Vite gestionado con pnpm.

**Spec:** `docs/superpowers/specs/2026-09-17-nucleo-afinador-design.md`

## Global Constraints

- Python **3.13.1** vía pyenv. No usar el Python de Homebrew ni 3.14.0a3.
- Gestor de paquetes JavaScript: **pnpm**. Nunca `npm`.
- Comentarios, nombres de variables, funciones y clases **en español**.
- Docstrings con **notación matemática clara** cuando haya fórmulas.
- Preferir **numpy/scipy** sobre implementaciones manuales de operaciones numéricas.
- Pruebas con **pytest**.
- Dispositivo de audio: `Rocksmith USB Guitar Adapter`, **1 canal**, **48000 Hz**, sin salida.
- Captura en **float32**. Nunca entero de 16 bits.
- Umbral por defecto de la compuerta de ruido: **−60.0 dBFS RMS**.
- Frecuencia de referencia por defecto: **A4 = 440.0 Hz**.
- Tolerancia para considerar una nota afinada: **±5 cents**.
- Bloque de captura: **512 muestras**. Emisión por WebSocket: **~30 Hz**.
- El callback de audio **nunca** bloquea: sin cálculo, sin red, sin asignación de memoria, sin locks que puedan esperar.
- `nucleo/` **no importa** nada de `servidor/` ni de `interfaz/`.
- Todas las dependencias deben ser libres y gratuitas.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `pyproject.toml` | Dependencias y configuración de pytest |
| `nucleo/afinaciones.py` | Perfiles de afinación como dato (guitarra, bajo) |
| `nucleo/musica.py` | Teoría: frecuencia↔nota, cents, posiciones en el mástil |
| `nucleo/analisis/energia.py` | Nivel RMS en dBFS y compuerta de ruido |
| `nucleo/analisis/yin.py` | Detector YIN: frecuencia + confianza |
| `nucleo/analisis/registro.py` | Registro de detectores intercambiables |
| `nucleo/analisis/pipeline.py` | Encadena compuerta → detector → suavizado |
| `nucleo/captura.py` | Buffer circular, hilo de audio, listado de dispositivos |
| `servidor/configuracion.py` | Configuración persistente y calibración |
| `servidor/diagnostico.py` | Los tres estados de error de la spec |
| `servidor/modulos.py` | Registro de módulos de la aplicación |
| `servidor/app.py` | FastAPI: endpoints REST y archivos estáticos |
| `servidor/emision.py` | Bucle de emisión por WebSocket a ~30 Hz |
| `interfaz/src/` | Armazón React, afinador y mástil |
| `tests/` | pytest: sintéticos y con audio real |

**Nota sobre la extensibilidad.** Dos piezas existen desde la etapa 1 con el único
fin de que las etapas siguientes no obliguen a reescribir el núcleo:
`nucleo/analisis/registro.py` (para enchufar un detector de acordes en la etapa 2)
y `servidor/modulos.py` (para enchufar ejercicios, canciones y efectos como módulos
hermanos del afinador). Ambas son deliberadamente delgadas: un diccionario y un
protocolo. No se añade nada más por adelantado.

---

### Task 1: Andamiaje del proyecto y perfiles de afinación

**Files:**
- Create: `pyproject.toml`
- Create: `nucleo/__init__.py`
- Create: `nucleo/afinaciones.py`
- Create: `.gitignore`
- Test: `tests/test_afinaciones.py`

**Interfaces:**
- Consumes: nada (primera tarea)
- Produces:
  - `Cuerda(numero: int, nota: str, frecuencia: float)` — dataclass congelada
  - `PerfilAfinacion(nombre: str, cuerdas: tuple[Cuerda, ...], trastes: int)` — dataclass congelada
  - `PerfilAfinacion.frecuencia_minima -> float`
  - `PerfilAfinacion.tamano_ventana(frecuencia_muestreo: int = 48000) -> int`
  - `PERFILES: dict[str, PerfilAfinacion]` con claves `"guitarra_estandar"`, `"guitarra_drop_d"`, `"bajo_4"`, `"bajo_5"`

**Contexto para quien implementa.** El tamaño de la ventana de análisis no es una
constante: el detector YIN necesita varios periodos completos de la frecuencia más
grave que deba reconocer. Un bajo de 5 cuerdas baja hasta 30,87 Hz (periodo de
32,4 ms) y necesita una ventana mucho más larga que una guitarra. Fijar una
constante obligaría a elegir entre no soportar el bajo o imponerle a la guitarra el
doble del retardo necesario.

La fórmula es: ventana = la menor potencia de 2 mayor o igual que
`4 · frecuencia_muestreo / frecuencia_minima`. El factor 4 da cuatro periodos de
margen sobre los dos que YIN exige como mínimo. Se redondea a potencia de 2 porque
las FFT de las etapas siguientes lo agradecen.

- [ ] **Step 1: Crear `pyproject.toml`**

```toml
[project]
name = "proyecto-musica"
version = "0.1.0"
description = "Software libre para practicar guitarra con el cable Rocksmith"
requires-python = ">=3.13"
dependencies = [
    "numpy>=2.0",
    "scipy>=1.14",
    "sounddevice>=0.5",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "soundfile>=0.12"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Crear `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
node_modules/
dist/
.pytest_cache/
config_local.json
```

- [ ] **Step 3: Instalar el entorno**

```bash
cd /Users/giocrisraigodoy/Documents/proyecto_musica
pyenv exec python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Esperado: instalación correcta. `sounddevice` necesita PortAudio; si falla,
`brew install portaudio` y reintentar.

- [ ] **Step 4: Escribir la prueba que falla**

```python
# tests/test_afinaciones.py
import pytest

from nucleo.afinaciones import PERFILES, PerfilAfinacion


def test_guitarra_estandar_tiene_seis_cuerdas():
    perfil = PERFILES["guitarra_estandar"]
    assert len(perfil.cuerdas) == 6


def test_guitarra_estandar_cuerda_grave_es_mi2():
    perfil = PERFILES["guitarra_estandar"]
    grave = perfil.cuerdas[0]
    assert grave.numero == 6
    assert grave.nota == "E2"
    assert grave.frecuencia == pytest.approx(82.41, abs=0.01)


def test_bajo_5_baja_hasta_si0():
    perfil = PERFILES["bajo_5"]
    assert perfil.frecuencia_minima == pytest.approx(30.87, abs=0.01)


@pytest.mark.parametrize(
    "clave, ventana_esperada",
    [
        ("guitarra_estandar", 4096),
        ("guitarra_drop_d", 4096),
        ("bajo_4", 8192),
        ("bajo_5", 8192),
    ],
)
def test_tamano_ventana_depende_del_perfil(clave, ventana_esperada):
    """La ventana debe crecer para los perfiles graves, no ser constante."""
    assert PERFILES[clave].tamano_ventana(48000) == ventana_esperada


def test_los_perfiles_son_inmutables():
    perfil = PERFILES["guitarra_estandar"]
    with pytest.raises(Exception):
        perfil.nombre = "otro"
```

- [ ] **Step 5: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_afinaciones.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.afinaciones'`

- [ ] **Step 6: Implementar `nucleo/afinaciones.py`**

```python
"""Perfiles de afinación como dato.

Un perfil describe un instrumento afinado: sus cuerdas, sus frecuencias al aire y
cuántos trastes tiene. Tratarlo como dato y no como código es lo que permite que un
bajo sea simplemente otra entrada del diccionario en lugar de una rama especial.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Cuerda:
    """Una cuerda al aire.

    numero: numeración convencional del instrumento, 1 es la más aguda.
    nota: nombre científico, por ejemplo "E2".
    frecuencia: frecuencia fundamental al aire, en Hz.
    """

    numero: int
    nota: str
    frecuencia: float


@dataclass(frozen=True)
class PerfilAfinacion:
    """Un instrumento afinado. Las cuerdas van de la más grave a la más aguda."""

    nombre: str
    cuerdas: tuple[Cuerda, ...]
    trastes: int

    @property
    def frecuencia_minima(self) -> float:
        """Frecuencia más baja que el análisis debe poder reconocer, en Hz."""
        return min(cuerda.frecuencia for cuerda in self.cuerdas)

    def tamano_ventana(self, frecuencia_muestreo: int = 48000) -> int:
        """Muestras por ventana de análisis, potencia de 2.

        El detector de tono necesita varios periodos completos de la frecuencia más
        grave. Se piden 4 periodos (el doble del mínimo teórico de 2) y se redondea
        hacia arriba a la siguiente potencia de 2:

            ventana = 2^ceil(log2(4 · fs / f_min))

        Para una guitarra estándar (f_min = 82,41 Hz a 48 kHz) da 4096 muestras
        (85 ms); para un bajo de 5 cuerdas (30,87 Hz) da 8192 (171 ms).
        """
        muestras_necesarias = 4.0 * frecuencia_muestreo / self.frecuencia_minima
        exponente = math.ceil(math.log2(muestras_necesarias))
        return 2**exponente


PERFILES: dict[str, PerfilAfinacion] = {
    "guitarra_estandar": PerfilAfinacion(
        nombre="Guitarra estándar",
        cuerdas=(
            Cuerda(6, "E2", 82.41),
            Cuerda(5, "A2", 110.00),
            Cuerda(4, "D3", 146.83),
            Cuerda(3, "G3", 196.00),
            Cuerda(2, "B3", 246.94),
            Cuerda(1, "E4", 329.63),
        ),
        trastes=22,
    ),
    "guitarra_drop_d": PerfilAfinacion(
        nombre="Guitarra Drop D",
        cuerdas=(
            Cuerda(6, "D2", 73.42),
            Cuerda(5, "A2", 110.00),
            Cuerda(4, "D3", 146.83),
            Cuerda(3, "G3", 196.00),
            Cuerda(2, "B3", 246.94),
            Cuerda(1, "E4", 329.63),
        ),
        trastes=22,
    ),
    "bajo_4": PerfilAfinacion(
        nombre="Bajo 4 cuerdas",
        cuerdas=(
            Cuerda(4, "E1", 41.20),
            Cuerda(3, "A1", 55.00),
            Cuerda(2, "D2", 73.42),
            Cuerda(1, "G2", 98.00),
        ),
        trastes=24,
    ),
    "bajo_5": PerfilAfinacion(
        nombre="Bajo 5 cuerdas",
        cuerdas=(
            Cuerda(5, "B0", 30.87),
            Cuerda(4, "E1", 41.20),
            Cuerda(3, "A1", 55.00),
            Cuerda(2, "D2", 73.42),
            Cuerda(1, "G2", 98.00),
        ),
        trastes=24,
    ),
}
```

También crear `nucleo/__init__.py` vacío.

- [ ] **Step 7: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_afinaciones.py -v`
Esperado: PASS, 8 pruebas.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore nucleo/ tests/test_afinaciones.py
git commit -m "feat: perfiles de afinación con ventana dependiente del perfil"
```

---

### Task 2: Teoría musical — frecuencia, notas, cents y mástil

**Files:**
- Create: `nucleo/musica.py`
- Test: `tests/test_musica.py`

**Interfaces:**
- Consumes: `nucleo.afinaciones.PerfilAfinacion`, `nucleo.afinaciones.PERFILES`
- Produces:
  - `NotaDetectada(nombre: str, midi: int, frecuencia_ideal: float, cents: float)` — dataclass congelada
  - `Posicion(cuerda: int, traste: int)` — dataclass congelada
  - `frecuencia_a_midi(frecuencia: float, referencia_a4: float = 440.0) -> float`
  - `midi_a_frecuencia(midi: float, referencia_a4: float = 440.0) -> float`
  - `nombre_de_midi(midi: int) -> str`
  - `frecuencia_a_nota(frecuencia: float, referencia_a4: float = 440.0) -> NotaDetectada`
  - `posiciones_en_mastil(midi: int, perfil: PerfilAfinacion) -> list[Posicion]`
  - `esta_afinada(cents: float, tolerancia: float = 5.0) -> bool`

**Contexto para quien implementa.** Este módulo es aritmética pura: no toca audio ni
numpy en caliente, y por eso se puede probar con exactitud total.

Dos puntos merecen atención. El primero: se trabaja en **número MIDI**, no en
nombres de nota, porque el número MIDI es lineal en semitonos y convierte
"la nota siguiente" en "sumar 1". El nombre se genera al final.

El segundo: `posiciones_en_mastil` devuelve una **lista**, y esto es deliberado. Un
La de 110 Hz puede ser la 5ª cuerda al aire o la 6ª en el traste 5; suenan casi
idénticos y la física no permite distinguirlos desde la frecuencia. Devolver una
sola posición sería inventar una certeza que no tenemos. La interfaz resaltará todas.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_musica.py
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.musica import (
    NotaDetectada,
    Posicion,
    esta_afinada,
    frecuencia_a_midi,
    frecuencia_a_nota,
    midi_a_frecuencia,
    nombre_de_midi,
    posiciones_en_mastil,
)


def test_la4_es_midi_69():
    assert frecuencia_a_midi(440.0) == pytest.approx(69.0)


def test_midi_69_es_la4():
    assert midi_a_frecuencia(69) == pytest.approx(440.0)


def test_una_octava_son_doce_semitonos():
    assert frecuencia_a_midi(880.0) == pytest.approx(81.0)


@pytest.mark.parametrize(
    "midi, nombre",
    [(40, "E2"), (45, "A2"), (50, "D3"), (55, "G3"), (59, "B3"), (64, "E4"), (69, "A4")],
)
def test_nombres_de_las_cuerdas_al_aire(midi, nombre):
    assert nombre_de_midi(midi) == nombre


def test_frecuencia_exacta_da_cero_cents():
    frecuencia = midi_a_frecuencia(40)  # E2 exacto
    nota = frecuencia_a_nota(frecuencia)
    assert nota.nombre == "E2"
    assert nota.midi == 40
    assert nota.cents == pytest.approx(0.0, abs=0.01)


@pytest.mark.parametrize("desviacion", [-50.0, -25.0, -10.0, 10.0, 25.0, 50.0])
def test_desviacion_conocida_se_devuelve_igual(desviacion):
    """Si desafino una nota N cents, el resultado debe decir exactamente N cents."""
    frecuencia = midi_a_frecuencia(40) * 2 ** (desviacion / 1200.0)
    nota = frecuencia_a_nota(frecuencia)
    assert nota.midi == 40
    assert nota.cents == pytest.approx(desviacion, abs=0.01)


def test_la_nota_mas_cercana_gana_pasado_medio_semitono():
    """A +60 cents de E2 ya estamos más cerca de F2."""
    frecuencia = midi_a_frecuencia(40) * 2 ** (60.0 / 1200.0)
    nota = frecuencia_a_nota(frecuencia)
    assert nota.midi == 41
    assert nota.cents == pytest.approx(-40.0, abs=0.01)


def test_la_110_tiene_dos_posiciones_en_guitarra():
    """5ª al aire y 6ª en el traste 5 son la misma frecuencia: hay que mostrar ambas."""
    perfil = PERFILES["guitarra_estandar"]
    posiciones = posiciones_en_mastil(45, perfil)
    assert Posicion(cuerda=5, traste=0) in posiciones
    assert Posicion(cuerda=6, traste=5) in posiciones


def test_mi2_solo_se_toca_en_la_sexta_al_aire():
    perfil = PERFILES["guitarra_estandar"]
    assert posiciones_en_mastil(40, perfil) == [Posicion(cuerda=6, traste=0)]


def test_no_se_devuelven_trastes_fuera_del_mastil():
    perfil = PERFILES["guitarra_estandar"]
    assert posiciones_en_mastil(120, perfil) == []


def test_referencia_alternativa_desplaza_todo():
    """Con A4 = 432 Hz, tocar 440 Hz ya no está afinado."""
    nota = frecuencia_a_nota(440.0, referencia_a4=432.0)
    assert nota.midi == 69
    assert nota.cents == pytest.approx(31.77, abs=0.05)


@pytest.mark.parametrize(
    "cents, esperado", [(0.0, True), (4.9, True), (-4.9, True), (5.1, False), (-5.1, False)]
)
def test_tolerancia_de_afinacion(cents, esperado):
    assert esta_afinada(cents) is esperado
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_musica.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.musica'`

- [ ] **Step 3: Implementar `nucleo/musica.py`**

```python
"""Teoría musical: conversión entre frecuencia, nota y posición en el mástil.

Aritmética pura. Este módulo no conoce el audio ni el hardware; recibe números y
devuelve números. Toda la afinación temperada se apoya en dos identidades:

    midi(f) = 69 + 12 · log2(f / f_ref)        con f_ref = A4
    cents   = 1200 · log2(f / f_ideal)

donde f_ideal es la frecuencia exacta de la nota más cercana.
"""

import math
from dataclasses import dataclass

from nucleo.afinaciones import PerfilAfinacion

NOMBRES_NOTAS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

MIDI_LA4 = 69


@dataclass(frozen=True)
class NotaDetectada:
    """Nota reconocida a partir de una frecuencia.

    nombre: notación científica, por ejemplo "E2".
    midi: número MIDI de la nota más cercana.
    frecuencia_ideal: frecuencia exacta de esa nota, en Hz.
    cents: desviación respecto a la nota ideal. Negativo = grave, positivo = agudo.
    """

    nombre: str
    midi: int
    frecuencia_ideal: float
    cents: float


@dataclass(frozen=True)
class Posicion:
    """Un punto del mástil: número de cuerda y traste. Traste 0 es al aire."""

    cuerda: int
    traste: int


def frecuencia_a_midi(frecuencia: float, referencia_a4: float = 440.0) -> float:
    """Número MIDI (con decimales) de una frecuencia.

        midi(f) = 69 + 12 · log2(f / f_ref)
    """
    if frecuencia <= 0.0:
        raise ValueError("La frecuencia debe ser positiva")
    return MIDI_LA4 + 12.0 * math.log2(frecuencia / referencia_a4)


def midi_a_frecuencia(midi: float, referencia_a4: float = 440.0) -> float:
    """Frecuencia en Hz de un número MIDI.

        f(midi) = f_ref · 2^((midi - 69) / 12)
    """
    return referencia_a4 * 2.0 ** ((midi - MIDI_LA4) / 12.0)


def nombre_de_midi(midi: int) -> str:
    """Nombre en notación científica, por ejemplo 40 -> "E2"."""
    octava = midi // 12 - 1
    return f"{NOMBRES_NOTAS[midi % 12]}{octava}"


def frecuencia_a_nota(frecuencia: float, referencia_a4: float = 440.0) -> NotaDetectada:
    """Nota más cercana a una frecuencia, con su desviación en cents."""
    midi_exacto = frecuencia_a_midi(frecuencia, referencia_a4)
    midi_cercano = round(midi_exacto)
    frecuencia_ideal = midi_a_frecuencia(midi_cercano, referencia_a4)
    cents = 1200.0 * math.log2(frecuencia / frecuencia_ideal)
    return NotaDetectada(
        nombre=nombre_de_midi(midi_cercano),
        midi=midi_cercano,
        frecuencia_ideal=frecuencia_ideal,
        cents=cents,
    )


def posiciones_en_mastil(midi: int, perfil: PerfilAfinacion) -> list[Posicion]:
    """Todas las posiciones del mástil que producen esa nota.

    Devuelve una lista y no una sola posición a propósito: un La de 110 Hz es tanto
    la 5ª cuerda al aire como la 6ª en el traste 5, y desde la frecuencia no hay
    forma de distinguirlas. Elegir una sería fingir una certeza inexistente.

    El resultado va ordenado por número de cuerda descendente (de la más grave a la
    más aguda), que es el orden en que se dibuja el mástil.
    """
    posiciones = []
    for cuerda in perfil.cuerdas:
        midi_al_aire = round(frecuencia_a_midi(cuerda.frecuencia))
        traste = midi - midi_al_aire
        if 0 <= traste <= perfil.trastes:
            posiciones.append(Posicion(cuerda=cuerda.numero, traste=traste))
    return sorted(posiciones, key=lambda p: -p.cuerda)


def esta_afinada(cents: float, tolerancia: float = 5.0) -> bool:
    """Verdadero si la desviación cae dentro de la tolerancia, en cents."""
    return abs(cents) < tolerancia
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_musica.py -v`
Esperado: PASS, 27 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/musica.py tests/test_musica.py
git commit -m "feat: teoría musical, cents y posiciones en el mástil"
```

---

### Task 3: Energía de la señal y compuerta de ruido

**Files:**
- Create: `nucleo/analisis/__init__.py`
- Create: `nucleo/analisis/energia.py`
- Test: `tests/test_energia.py`

**Interfaces:**
- Consumes: nada de tareas anteriores
- Produces:
  - `NIVEL_SILENCIO_DBFS: float` = `-120.0`
  - `UMBRAL_RUIDO_POR_DEFECTO_DBFS: float` = `-60.0`
  - `nivel_dbfs(muestras: np.ndarray) -> float`
  - `hay_senal(muestras: np.ndarray, umbral_dbfs: float = -60.0) -> bool`

**Contexto para quien implementa.** Esta es la primera puerta del análisis: si no
hay energía suficiente, no se calcula nada más. Sin ella el afinador oscilaría
permanentemente persiguiendo el piso de ruido del cable.

El umbral por defecto de **−60,0 dBFS** no es arbitrario: se midió el equipo real.
Con la guitarra sonando el nivel medio fue −45 dBFS; con la guitarra conectada y en
silencio, −74,4 dBFS. El umbral queda 14 dB sobre el ruido y 15 dB bajo la señal,
centrado en el hueco de 29 dB que los separa.

dBFS significa decibelios relativos a escala completa: `20·log10(rms)` donde una
señal que llega al máximo del rango vale 0 dBFS y todo lo demás es negativo. El
logaritmo de cero es menos infinito, así que el silencio absoluto se recorta a
−120 dBFS para que el valor siga siendo un número usable.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_energia.py
import numpy as np
import pytest

from nucleo.analisis.energia import (
    NIVEL_SILENCIO_DBFS,
    UMBRAL_RUIDO_POR_DEFECTO_DBFS,
    hay_senal,
    nivel_dbfs,
)


def senoide(amplitud: float, frecuencia: float = 440.0, muestras: int = 4096) -> np.ndarray:
    t = np.arange(muestras) / 48000.0
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def test_silencio_absoluto_no_devuelve_infinito():
    assert nivel_dbfs(np.zeros(4096, dtype=np.float32)) == NIVEL_SILENCIO_DBFS


def test_senoide_de_amplitud_uno_da_menos_tres_dbfs():
    """El RMS de una senoide de amplitud 1 es 1/sqrt(2), o sea -3,01 dBFS."""
    assert nivel_dbfs(senoide(1.0)) == pytest.approx(-3.01, abs=0.05)


def test_mitad_de_amplitud_baja_seis_decibelios():
    assert nivel_dbfs(senoide(0.5)) == pytest.approx(-9.03, abs=0.05)


def test_el_umbral_por_defecto_es_menos_sesenta():
    """Valor derivado de medir el equipo real: ruido -74,4 dBFS, señal -45 dBFS."""
    assert UMBRAL_RUIDO_POR_DEFECTO_DBFS == -60.0


def test_senal_por_encima_del_umbral_pasa_la_compuerta():
    # -45 dBFS aproximado, el nivel medio medido tocando
    assert hay_senal(senoide(0.008)) is True


def test_piso_de_ruido_medido_no_pasa_la_compuerta():
    # -74 dBFS aproximado, el piso de ruido medido del cable
    generador = np.random.default_rng(1)
    ruido = (generador.normal(0.0, 0.0002, 4096)).astype(np.float32)
    assert hay_senal(ruido) is False


def test_el_umbral_es_ajustable():
    tenue = senoide(0.0005)  # unos -69 dBFS
    assert hay_senal(tenue, umbral_dbfs=-60.0) is False
    assert hay_senal(tenue, umbral_dbfs=-80.0) is True
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_energia.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.analisis'`

- [ ] **Step 3: Implementar `nucleo/analisis/energia.py`**

```python
"""Nivel de señal y compuerta de ruido.

Primera puerta del análisis: por debajo del umbral no se calcula nada más. Sin esta
compuerta el detector de tono perseguiría el piso de ruido del cable y la aguja del
afinador no pararía de bailar.
"""

import numpy as np

# El logaritmo de cero es menos infinito; se recorta aquí para que el silencio
# absoluto siga siendo un número con el que se pueda operar y comparar.
NIVEL_SILENCIO_DBFS = -120.0

# Derivado de medir el equipo real: con la guitarra sonando el nivel medio fue
# -45 dBFS y el piso de ruido -74,4 dBFS. El umbral queda centrado en ese hueco.
UMBRAL_RUIDO_POR_DEFECTO_DBFS = -60.0


def nivel_dbfs(muestras: np.ndarray) -> float:
    """Nivel RMS de la ventana en decibelios relativos a escala completa.

        nivel = 20 · log10( sqrt( media(x²) ) )

    Escala completa (amplitud 1,0) equivale a 0 dBFS; todo lo demás es negativo.
    Una senoide de amplitud 1 da -3,01 dBFS porque su RMS es 1/sqrt(2).
    """
    if muestras.size == 0:
        return NIVEL_SILENCIO_DBFS
    rms = float(np.sqrt(np.mean(np.square(muestras, dtype=np.float64))))
    if rms <= 0.0:
        return NIVEL_SILENCIO_DBFS
    return max(20.0 * np.log10(rms), NIVEL_SILENCIO_DBFS)


def hay_senal(
    muestras: np.ndarray, umbral_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS
) -> bool:
    """Verdadero si la ventana supera el umbral y merece ser analizada."""
    return nivel_dbfs(muestras) > umbral_dbfs
```

También crear `nucleo/analisis/__init__.py` vacío.

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_energia.py -v`
Esperado: PASS, 7 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/analisis/ tests/test_energia.py
git commit -m "feat: nivel en dBFS y compuerta de ruido calibrada"
```

---

### Task 4: Detector de tono YIN y registro de detectores

**Files:**
- Create: `nucleo/analisis/registro.py`
- Create: `nucleo/analisis/yin.py`
- Test: `tests/test_yin.py`

**Interfaces:**
- Consumes: nada de tareas anteriores
- Produces:
  - `ResultadoTono(frecuencia: float, confianza: float)` — dataclass congelada, en `registro.py`
  - `Detector` — `Protocol` con `__call__(muestras: np.ndarray, frecuencia_muestreo: int, frecuencia_minima: float, frecuencia_maxima: float) -> ResultadoTono`
  - `registrar(nombre: str, detector: Detector) -> None`
  - `obtener(nombre: str) -> Detector`
  - `nombres_disponibles() -> list[str]`
  - `detectar_yin(muestras, frecuencia_muestreo, frecuencia_minima, frecuencia_maxima, umbral=0.15) -> ResultadoTono` en `yin.py`, registrado bajo el nombre `"yin"`

**Contexto para quien implementa.** Aquí hay dos ideas y conviene no mezclarlas.

**El registro** es una pieza de tres funciones y un diccionario. Existe porque la
etapa 2 necesitará un detector de acordes (polifónico) junto al monofónico, y sin
registro eso obligaría a tocar el resto del núcleo. Es deliberadamente mínimo: no
se añade prioridad, ni configuración, ni descubrimiento automático.

**YIN** es el algoritmo de detección de tono (Cheveigné y Kawahara, 2002). Funciona
sobre la función de diferencia:

    d(τ) = Σⱼ (x[j] − x[j+τ])²

que vale casi cero cuando τ coincide con el periodo de la señal. El problema es que
d(0) siempre vale exactamente cero, así que YIN la normaliza acumuladamente:

    d′(τ) = d(τ) · τ / Σ_{k=1..τ} d(k)

Con d′ se busca el **primer** mínimo bajo el umbral, no el mínimo global. Esto es
lo que evita el error clásico de los detectores de tono: confundir la fundamental
con su segundo armónico, que también produce un mínimo profundo. Buscar el primero
prioriza el periodo más largo, que es la fundamental.

Dos detalles de implementación importan:

1. `d(τ)` se calcula **vía FFT**, no con bucles. Desarrollando el cuadrado queda
   `d(τ) = Σx[j]² + Σx[j+τ]² − 2·r(τ)`, donde `r` es la autocorrelación, que la FFT
   da entera de una vez. Con bucles en Python esto sería inusable en tiempo real.
2. El mínimo se refina con **interpolación parabólica** sobre los tres puntos
   alrededor. Sin ella la resolución queda limitada a muestras enteras: a 48 kHz,
   un E2 de 82,41 Hz tiene un periodo de 582,5 muestras, y errar por una muestra
   ya son casi 3 cents. Con interpolación el error baja por debajo de 1 cent.

La **confianza** es `1 − d′(τ)` en el mínimo. Vale tanto como la frecuencia: sin
ella no se puede distinguir una nota real de ruido de dedos, y el pipeline la usa
para descartar detecciones dudosas en vez de mostrarlas.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_yin.py
import numpy as np
import pytest

from nucleo.analisis.registro import ResultadoTono, nombres_disponibles, obtener, registrar
from nucleo.analisis.yin import detectar_yin

FS = 48000
F_MIN = 70.0
F_MAX = 1400.0


def senoide(frecuencia: float, muestras: int = 4096, amplitud: float = 0.3) -> np.ndarray:
    t = np.arange(muestras) / FS
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def cuerda_pulsada(fundamental: float, muestras: int = 4096) -> np.ndarray:
    """Imita una cuerda real: fundamental más armónicos decrecientes."""
    t = np.arange(muestras) / FS
    señal = np.zeros(muestras)
    for armonico, peso in enumerate([1.0, 0.6, 0.4, 0.25, 0.15], start=1):
        señal += peso * np.sin(2 * np.pi * fundamental * armonico * t)
    return (0.3 * señal / np.max(np.abs(señal))).astype(np.float32)


def cents_de_error(medida: float, real: float) -> float:
    return abs(1200.0 * np.log2(medida / real))


@pytest.mark.parametrize(
    "frecuencia", [82.41, 110.00, 146.83, 196.00, 246.94, 329.63]
)
def test_detecta_cada_cuerda_al_aire_con_menos_de_un_cent_de_error(frecuencia):
    resultado = detectar_yin(senoide(frecuencia), FS, F_MIN, F_MAX)
    assert cents_de_error(resultado.frecuencia, frecuencia) < 1.0


def test_detecta_la_fundamental_y_no_el_segundo_armonico():
    """El error clásico de un detector de tono: oír 164 Hz donde hay un E2 de 82."""
    resultado = detectar_yin(cuerda_pulsada(82.41), FS, F_MIN, F_MAX)
    assert cents_de_error(resultado.frecuencia, 82.41) < 5.0


def test_una_nota_limpia_tiene_confianza_alta():
    resultado = detectar_yin(senoide(196.0), FS, F_MIN, F_MAX)
    assert resultado.confianza > 0.9


def test_el_ruido_blanco_tiene_confianza_baja():
    """No basta con devolver algo: hay que poder saber que no vale nada."""
    generador = np.random.default_rng(7)
    ruido = generador.normal(0.0, 0.3, 4096).astype(np.float32)
    resultado = detectar_yin(ruido, FS, F_MIN, F_MAX)
    assert resultado.confianza < 0.5


def test_no_devuelve_frecuencias_fuera_del_rango_pedido():
    resultado = detectar_yin(senoide(300.0), FS, 200.0, 400.0)
    assert 200.0 <= resultado.frecuencia <= 400.0


def test_detecta_un_si0_de_bajo_con_la_ventana_larga():
    """30,87 Hz necesita 8192 muestras; con 4096 no hay periodos suficientes."""
    resultado = detectar_yin(senoide(30.87, muestras=8192), FS, 28.0, 400.0)
    assert cents_de_error(resultado.frecuencia, 30.87) < 2.0


def test_desviacion_de_veinte_cents_se_detecta_como_tal():
    real = 110.0 * 2 ** (20.0 / 1200.0)
    resultado = detectar_yin(senoide(real), FS, F_MIN, F_MAX)
    assert cents_de_error(resultado.frecuencia, real) < 1.0


def test_el_detector_yin_esta_registrado():
    assert "yin" in nombres_disponibles()
    assert obtener("yin") is detectar_yin


def test_se_puede_registrar_otro_detector():
    """La etapa 2 enchufará aquí un detector de acordes sin tocar el núcleo."""

    def detector_falso(muestras, frecuencia_muestreo, frecuencia_minima, frecuencia_maxima):
        return ResultadoTono(frecuencia=440.0, confianza=1.0)

    registrar("falso", detector_falso)
    assert obtener("falso") is detector_falso
    assert "falso" in nombres_disponibles()


def test_pedir_un_detector_inexistente_es_un_error_claro():
    with pytest.raises(KeyError, match="inexistente"):
        obtener("inexistente")
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_yin.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.analisis.registro'`

- [ ] **Step 3: Implementar `nucleo/analisis/registro.py`**

```python
"""Registro de detectores de tono intercambiables.

Existe para que la etapa 2 pueda enchufar un detector de acordes junto al
monofónico sin tocar el resto del núcleo. Es deliberadamente mínimo: un diccionario
y tres funciones. Sin prioridades, sin configuración, sin descubrimiento automático.
"""

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class ResultadoTono:
    """Salida de un detector.

    frecuencia: fundamental estimada en Hz, 0.0 si no se detectó nada.
    confianza: entre 0 y 1. Importa tanto como la frecuencia: sin ella no se puede
        distinguir una nota real de ruido de dedos o de un armónico.
    """

    frecuencia: float
    confianza: float


class Detector(Protocol):
    """Contrato que cumple todo detector de tono."""

    def __call__(
        self,
        muestras: np.ndarray,
        frecuencia_muestreo: int,
        frecuencia_minima: float,
        frecuencia_maxima: float,
    ) -> ResultadoTono: ...


_DETECTORES: dict[str, Detector] = {}


def registrar(nombre: str, detector: Detector) -> None:
    """Añade un detector al registro, sustituyendo el anterior con ese nombre."""
    _DETECTORES[nombre] = detector


def obtener(nombre: str) -> Detector:
    """Devuelve un detector por nombre. Lanza KeyError si no existe."""
    if nombre not in _DETECTORES:
        disponibles = ", ".join(sorted(_DETECTORES)) or "ninguno"
        raise KeyError(f"No existe el detector '{nombre}'. Disponibles: {disponibles}")
    return _DETECTORES[nombre]


def nombres_disponibles() -> list[str]:
    """Nombres de los detectores registrados, ordenados."""
    return sorted(_DETECTORES)
```

- [ ] **Step 4: Implementar `nucleo/analisis/yin.py`**

```python
"""Detector de tono YIN (Cheveigné y Kawahara, 2002).

Función pura: mismas muestras, mismo resultado, sin estado interno. Esa pureza es
lo que permite probarlo con señales sintéticas de frecuencia conocida.
"""

import numpy as np

from nucleo.analisis.registro import ResultadoTono, registrar

# Bajo este valor de d'(τ) se considera que hay un periodo creíble. 0,15 es el valor
# propuesto en el artículo original y funciona bien con señal de pastilla eléctrica.
UMBRAL_YIN_POR_DEFECTO = 0.15


def _funcion_diferencia(muestras: np.ndarray, tau_maximo: int) -> np.ndarray:
    """Función de diferencia de YIN, calculada vía FFT.

        d(τ) = Σⱼ (x[j] − x[j+τ])²
             = Σ x[j]² + Σ x[j+τ]² − 2·r(τ)

    donde r es la autocorrelación. Desarrollar el cuadrado permite obtener las tres
    piezas de golpe: las dos sumas con una suma acumulada y r con una FFT. Calcular
    d(τ) con bucles en Python sería inviable en tiempo real.
    """
    x = muestras.astype(np.float64)
    n = x.size

    # Sumas acumuladas de x², para obtener cualquier Σ x[a:b]² en tiempo constante.
    acumulado = np.concatenate(([0.0], np.cumsum(x * x)))

    # Autocorrelación por FFT, con relleno a potencia de 2 para evitar el solape
    # circular que contaminaría los desfases grandes.
    tamano = 1 << (2 * n - 1).bit_length()
    espectro = np.fft.rfft(x, tamano)
    correlacion = np.fft.irfft(espectro * np.conj(espectro), tamano)[:tau_maximo]

    tau = np.arange(tau_maximo)
    energia_inicial = acumulado[n - tau] - acumulado[0]
    energia_desplazada = acumulado[n] - acumulado[tau]
    return energia_inicial + energia_desplazada - 2.0 * correlacion


def _diferencia_normalizada(diferencia: np.ndarray) -> np.ndarray:
    """Diferencia media acumulada normalizada.

        d′(τ) = d(τ) · τ / Σ_{k=1..τ} d(k)

    Normalizar es necesario porque d(0) vale siempre exactamente cero y sería
    siempre el mínimo global. Con d′(0) = 1 por convenio, el resto queda comparable.
    """
    normalizada = np.ones_like(diferencia)
    acumulado = np.cumsum(diferencia[1:])
    tau = np.arange(1, diferencia.size)
    # Donde el acumulado es cero (señal constante) se deja el valor 1: sin periodo.
    seguro = acumulado > 0.0
    normalizada[1:][seguro] = (diferencia[1:] * tau / acumulado)[seguro]
    return normalizada


def _refinar_con_parabola(valores: np.ndarray, indice: int) -> float:
    """Ajusta una parábola a los tres puntos alrededor del mínimo y devuelve su vértice.

    Sin este refinamiento la resolución queda limitada a muestras enteras: a 48 kHz
    el periodo de un E2 son 582,5 muestras y errar por una ya son casi 3 cents.
    """
    if indice <= 0 or indice >= valores.size - 1:
        return float(indice)
    anterior, actual, siguiente = valores[indice - 1], valores[indice], valores[indice + 1]
    denominador = 2.0 * (2.0 * actual - siguiente - anterior)
    if denominador == 0.0:
        return float(indice)
    return float(indice + (siguiente - anterior) / denominador)


def detectar_yin(
    muestras: np.ndarray,
    frecuencia_muestreo: int,
    frecuencia_minima: float,
    frecuencia_maxima: float,
    umbral: float = UMBRAL_YIN_POR_DEFECTO,
) -> ResultadoTono:
    """Estima la frecuencia fundamental de la ventana y la confianza de esa estimación.

    Devuelve frecuencia 0.0 y confianza 0.0 cuando la ventana es demasiado corta
    para contener periodos de la frecuencia mínima pedida.
    """
    tau_minimo = max(2, int(frecuencia_muestreo / frecuencia_maxima))
    tau_maximo = min(muestras.size - 1, int(frecuencia_muestreo / frecuencia_minima) + 1)
    if tau_maximo <= tau_minimo:
        return ResultadoTono(frecuencia=0.0, confianza=0.0)

    diferencia = _funcion_diferencia(muestras, tau_maximo + 1)
    normalizada = _diferencia_normalizada(diferencia)

    # Se busca el PRIMER mínimo bajo el umbral, no el global. Un armónico también
    # produce un mínimo profundo; quedarse con el primero prioriza el periodo más
    # largo, que es el de la fundamental. Aquí se evita el error de octava.
    ventana = normalizada[tau_minimo : tau_maximo + 1]
    candidatos = np.flatnonzero(ventana < umbral)
    if candidatos.size > 0:
        indice = tau_minimo + int(candidatos[0])
        # Descender hasta el fondo de ese valle antes de interpolar.
        while indice + 1 <= tau_maximo and normalizada[indice + 1] < normalizada[indice]:
            indice += 1
    else:
        indice = tau_minimo + int(np.argmin(ventana))

    periodo = _refinar_con_parabola(normalizada, indice)
    if periodo <= 0.0:
        return ResultadoTono(frecuencia=0.0, confianza=0.0)

    frecuencia = frecuencia_muestreo / periodo
    confianza = float(np.clip(1.0 - normalizada[indice], 0.0, 1.0))
    return ResultadoTono(frecuencia=float(frecuencia), confianza=confianza)


registrar("yin", detectar_yin)
```

- [ ] **Step 5: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_yin.py -v`
Esperado: PASS, 15 pruebas.

Si `test_detecta_la_fundamental_y_no_el_segundo_armonico` falla devolviendo una
frecuencia cercana al doble, el problema está en la búsqueda del primer mínimo: se
está tomando el mínimo global en vez del primero bajo el umbral.

- [ ] **Step 6: Commit**

```bash
git add nucleo/analisis/registro.py nucleo/analisis/yin.py tests/test_yin.py
git commit -m "feat: detector YIN con confianza y registro de detectores"
```

---

### Task 5: Suavizado y ensamblado del análisis

**Files:**
- Create: `nucleo/analisis/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `nucleo.afinaciones.PerfilAfinacion`, `nucleo.musica` (todo), `nucleo.analisis.energia`, `nucleo.analisis.registro`
- Produces:
  - `Suavizador(tamano: int = 5)` con `agregar(frecuencia: float) -> float | None`, `reiniciar() -> None`
  - `ResultadoAnalisis` — dataclass congelada con campos `estado: str`, `frecuencia: float`, `nota: str | None`, `cents: float | None`, `confianza: float`, `nivel_db: float`, `posiciones: list[Posicion]`, `cuerda_objetivo: int | None`, `afinada: bool`
  - `ResultadoAnalisis.a_dict() -> dict` — la forma exacta que viaja por WebSocket
  - `Analizador(perfil, frecuencia_muestreo=48000, umbral_ruido_dbfs=-60.0, referencia_a4=440.0, confianza_minima=0.75, nombre_detector="yin", tamano_suavizado=5)` con `procesar(muestras: np.ndarray) -> ResultadoAnalisis`

**Contexto para quien implementa.** Esta tarea junta las piezas anteriores en el
único objeto con estado del análisis.

El **suavizado usa mediana, no media**, y la diferencia importa. Los errores de un
detector de tono no son ruido gaussiano alrededor del valor correcto: son saltos
aislados y grandes, típicamente a la octava. La media los reparte y contamina el
resultado; la mediana simplemente los descarta. Con 5 muestras a un salto de 1024
muestras (21 ms), la ventana de suavizado cubre unos 107 ms: suficiente para que la
aguja se lea cómoda y poco para que siga siendo responsiva.

El `Analizador` decide el `estado` en dos puertas sucesivas, y ambas devuelven
`"silencio"` en vez de inventar: primero la compuerta de energía, después la
confianza del detector. Una nota de baja confianza **no se muestra atenuada**: no
se muestra. Mostrar una lectura poco fiable entrena al usuario a desconfiar de la
pantalla, que es peor que no mostrar nada.

La `cuerda_objetivo` es la cuerda al aire del perfil más cercana a la nota
detectada, en semitonos. Sirve para que el afinador sepa cuál estás afinando sin
que tengas que decírselo.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_pipeline.py
import numpy as np
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador, ResultadoAnalisis, Suavizador
from nucleo.musica import Posicion

FS = 48000
GUITARRA = PERFILES["guitarra_estandar"]


def senoide(frecuencia: float, muestras: int = 4096, amplitud: float = 0.3) -> np.ndarray:
    t = np.arange(muestras) / FS
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def test_el_suavizador_no_responde_hasta_llenarse():
    suavizador = Suavizador(tamano=3)
    assert suavizador.agregar(110.0) is None
    assert suavizador.agregar(110.0) is None
    assert suavizador.agregar(110.0) == pytest.approx(110.0)


def test_la_mediana_descarta_un_salto_de_octava():
    """El fallo típico de un detector de tono es un salto aislado al doble."""
    suavizador = Suavizador(tamano=5)
    for valor in [110.0, 110.0, 220.0, 110.0, 110.0]:
        resultado = suavizador.agregar(valor)
    assert resultado == pytest.approx(110.0)


def test_reiniciar_vacia_el_historial():
    suavizador = Suavizador(tamano=3)
    suavizador.agregar(110.0)
    suavizador.reiniciar()
    assert suavizador.agregar(110.0) is None


def test_el_silencio_no_produce_nota():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    resultado = analizador.procesar(np.zeros(4096, dtype=np.float32))
    assert resultado.estado == "silencio"
    assert resultado.nota is None
    assert resultado.posiciones == []


def test_el_ruido_no_inventa_una_nota():
    """Segunda puerta: pasa la energía pero no la confianza."""
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS)
    generador = np.random.default_rng(3)
    ruido = generador.normal(0.0, 0.2, 4096).astype(np.float32)
    resultado = analizador.procesar(ruido)
    assert resultado.estado == "silencio"


def test_una_cuerda_al_aire_se_identifica_completa():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    resultado = analizador.procesar(senoide(82.41))
    assert resultado.estado == "nota"
    assert resultado.nota == "E2"
    assert resultado.cents == pytest.approx(0.0, abs=3.0)
    assert resultado.afinada is True
    assert resultado.cuerda_objetivo == 6
    assert Posicion(cuerda=6, traste=0) in resultado.posiciones


def test_una_cuerda_desafinada_se_marca_como_tal():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    grave = 82.41 * 2 ** (-20.0 / 1200.0)
    resultado = analizador.procesar(senoide(grave))
    assert resultado.nota == "E2"
    assert resultado.cents == pytest.approx(-20.0, abs=3.0)
    assert resultado.afinada is False


def test_la_nota_ambigua_muestra_todas_sus_posiciones():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    resultado = analizador.procesar(senoide(110.0))
    assert Posicion(cuerda=5, traste=0) in resultado.posiciones
    assert Posicion(cuerda=6, traste=5) in resultado.posiciones


def test_el_umbral_de_confianza_es_configurable():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, confianza_minima=0.0,
                            tamano_suavizado=1)
    generador = np.random.default_rng(3)
    ruido = generador.normal(0.0, 0.2, 4096).astype(np.float32)
    assert analizador.procesar(ruido).estado == "nota"


def test_el_perfil_de_bajo_usa_su_propia_ventana():
    analizador = Analizador(PERFILES["bajo_5"], frecuencia_muestreo=FS, tamano_suavizado=1)
    resultado = analizador.procesar(senoide(30.87, muestras=8192))
    assert resultado.estado == "nota"
    assert resultado.nota == "B0"


def test_el_diccionario_emitido_tiene_la_forma_de_la_spec():
    analizador = Analizador(GUITARRA, frecuencia_muestreo=FS, tamano_suavizado=1)
    emitido = analizador.procesar(senoide(82.41)).a_dict()
    assert set(emitido) == {
        "estado", "frecuencia", "nota", "cents", "confianza",
        "nivel_db", "posiciones", "cuerda_objetivo", "afinada",
    }
    assert emitido["posiciones"] == [{"cuerda": 6, "traste": 0}]
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_pipeline.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.analisis.pipeline'`

- [ ] **Step 3: Implementar `nucleo/analisis/pipeline.py`**

```python
"""Encadena compuerta de ruido, detector de tono, suavizado y traducción musical.

Es el único objeto con estado del análisis: el suavizador necesita recordar las
últimas detecciones. Todo lo que hay debajo son funciones puras.
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from nucleo.afinaciones import PerfilAfinacion
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS, nivel_dbfs
from nucleo.analisis.registro import obtener
from nucleo.musica import (
    Posicion,
    esta_afinada,
    frecuencia_a_midi,
    frecuencia_a_nota,
    posiciones_en_mastil,
)


class Suavizador:
    """Mediana móvil sobre las últimas frecuencias detectadas.

    Se usa mediana y no media a propósito. Los fallos de un detector de tono no son
    ruido alrededor del valor correcto: son saltos aislados y grandes, casi siempre
    a la octava. La media los reparte y contamina el resultado; la mediana los
    descarta sin más.

    Devuelve None hasta tener el historial completo, para no publicar una lectura
    apoyada en menos muestras de las previstas.
    """

    def __init__(self, tamano: int = 5) -> None:
        if tamano < 1:
            raise ValueError("El tamaño del suavizado debe ser al menos 1")
        self._tamano = tamano
        self._historial: deque[float] = deque(maxlen=tamano)

    def agregar(self, frecuencia: float) -> float | None:
        """Añade una detección y devuelve la mediana, o None si falta historial."""
        self._historial.append(frecuencia)
        if len(self._historial) < self._tamano:
            return None
        return float(np.median(self._historial))

    def reiniciar(self) -> None:
        """Vacía el historial. Se llama al entrar en silencio."""
        self._historial.clear()


@dataclass(frozen=True)
class ResultadoAnalisis:
    """Lo que el análisis publica por cada ventana procesada.

    estado es "nota" o "silencio". En silencio, nota y cents son None y posiciones
    está vacía: el análisis no rellena con el último valor conocido.
    """

    estado: str
    frecuencia: float
    confianza: float
    nivel_db: float
    nota: str | None = None
    cents: float | None = None
    posiciones: list[Posicion] = field(default_factory=list)
    cuerda_objetivo: int | None = None
    afinada: bool = False

    def a_dict(self) -> dict:
        """Forma exacta del mensaje que viaja por WebSocket."""
        return {
            "estado": self.estado,
            "frecuencia": round(self.frecuencia, 2),
            "nota": self.nota,
            "cents": None if self.cents is None else round(self.cents, 1),
            "confianza": round(self.confianza, 3),
            "nivel_db": round(self.nivel_db, 1),
            "posiciones": [
                {"cuerda": p.cuerda, "traste": p.traste} for p in self.posiciones
            ],
            "cuerda_objetivo": self.cuerda_objetivo,
            "afinada": self.afinada,
        }


class Analizador:
    """Convierte ventanas de audio en resultados musicales."""

    def __init__(
        self,
        perfil: PerfilAfinacion,
        frecuencia_muestreo: int = 48000,
        umbral_ruido_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS,
        referencia_a4: float = 440.0,
        confianza_minima: float = 0.75,
        nombre_detector: str = "yin",
        tamano_suavizado: int = 5,
    ) -> None:
        self.perfil = perfil
        self.frecuencia_muestreo = frecuencia_muestreo
        self.umbral_ruido_dbfs = umbral_ruido_dbfs
        self.referencia_a4 = referencia_a4
        self.confianza_minima = confianza_minima
        self._detector = obtener(nombre_detector)
        self._suavizador = Suavizador(tamano_suavizado)

        # El rango de búsqueda sale del perfil: un margen bajo la cuerda más grave
        # para poder ver que está desafinada por abajo, y hasta el último traste de
        # la más aguda con margen por arriba.
        self._frecuencia_minima = perfil.frecuencia_minima * 0.85
        aguda = max(cuerda.frecuencia for cuerda in perfil.cuerdas)
        self._frecuencia_maxima = aguda * 2 ** (perfil.trastes / 12.0) * 1.15

    @property
    def tamano_ventana(self) -> int:
        """Muestras por ventana, derivadas del perfil."""
        return self.perfil.tamano_ventana(self.frecuencia_muestreo)

    def _silencio(self, nivel: float, confianza: float = 0.0) -> ResultadoAnalisis:
        self._suavizador.reiniciar()
        return ResultadoAnalisis(
            estado="silencio", frecuencia=0.0, confianza=confianza, nivel_db=nivel
        )

    def _cuerda_mas_cercana(self, midi: int) -> int:
        """Cuerda al aire del perfil más próxima en semitonos a la nota detectada."""
        return min(
            self.perfil.cuerdas,
            key=lambda c: abs(midi - round(frecuencia_a_midi(c.frecuencia, self.referencia_a4))),
        ).numero

    def procesar(self, muestras: np.ndarray) -> ResultadoAnalisis:
        """Analiza una ventana y devuelve el resultado.

        Dos puertas sucesivas devuelven silencio en vez de inventar: la energía y la
        confianza del detector. Una lectura dudosa no se muestra atenuada, no se
        muestra; enseñar al usuario a desconfiar de la pantalla es peor que callar.
        """
        nivel = nivel_dbfs(muestras)
        if nivel <= self.umbral_ruido_dbfs:
            return self._silencio(nivel)

        tono = self._detector(
            muestras,
            self.frecuencia_muestreo,
            self._frecuencia_minima,
            self._frecuencia_maxima,
        )
        if tono.confianza < self.confianza_minima or tono.frecuencia <= 0.0:
            return self._silencio(nivel, tono.confianza)

        suavizada = self._suavizador.agregar(tono.frecuencia)
        if suavizada is None:
            return ResultadoAnalisis(
                estado="silencio",
                frecuencia=0.0,
                confianza=tono.confianza,
                nivel_db=nivel,
            )

        nota = frecuencia_a_nota(suavizada, self.referencia_a4)
        return ResultadoAnalisis(
            estado="nota",
            frecuencia=suavizada,
            confianza=tono.confianza,
            nivel_db=nivel,
            nota=nota.nombre,
            cents=nota.cents,
            posiciones=posiciones_en_mastil(nota.midi, self.perfil),
            cuerda_objetivo=self._cuerda_mas_cercana(nota.midi),
            afinada=esta_afinada(nota.cents),
        )
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/ -v`
Esperado: PASS, toda la batería hasta ahora.

- [ ] **Step 5: Commit**

```bash
git add nucleo/analisis/pipeline.py tests/test_pipeline.py
git commit -m "feat: suavizado por mediana y ensamblado del análisis"
```

---

### Task 6: Captura de audio — buffer circular, hilo y dispositivos

**Files:**
- Create: `nucleo/captura.py`
- Test: `tests/test_captura.py`

**Interfaces:**
- Consumes: nada de tareas anteriores
- Produces:
  - `DispositivoAudio(indice: int, nombre: str, canales_entrada: int, frecuencia_muestreo: float)` — dataclass congelada
  - `listar_dispositivos_entrada() -> list[DispositivoAudio]`
  - `buscar_rocksmith(dispositivos: list[DispositivoAudio] | None = None) -> DispositivoAudio | None`
  - `BufferCircular(capacidad: int)` con `escribir(bloque: np.ndarray) -> None`, `leer_ultimas(n: int) -> np.ndarray | None`, propiedad `total_escrito: int`
  - `CapturaAudio(indice_dispositivo, frecuencia_muestreo=48000, tamano_bloque=512, capacidad_buffer=48000, ganancia=1.0, abrir_stream=None)` con `iniciar()`, `detener()`, `leer_ventana(n)`, propiedades `activa: bool`, `latencia_ms: float`, `ultimo_error: str | None`
  - `NOMBRE_ROCKSMITH: str` = `"Rocksmith USB Guitar Adapter"`

**Contexto para quien implementa.** Esta es la única parte del proyecto sensible al
tiempo real, y tiene una regla que no se negocia: **el callback de audio nunca se
bloquea**. Nada de cálculo, nada de red, nada de asignar memoria, nada de locks que
puedan esperar. Copia el bloque al buffer y retorna. Un callback que se retrasa
produce un chasquido audible y muestras perdidas.

De ahí sale el diseño del `BufferCircular`: memoria **preasignada** de tamaño fijo,
escritura por aritmética de índices, y sobrescritura de lo más antiguo cuando se
llena. Si el consumidor se atrasa se pierden muestras viejas, que es exactamente lo
correcto para un afinador: solo importa el presente.

La captura es en **float32 con ganancia digital**. El cable Rocksmith entrega nivel
de instrumento sin preamplificar: en el equipo real el pico medido fue −27 dBFS, un
4,5 % del rango. En float32 esa señal baja no cuesta precisión; en entero de 16 bits
se tirarían la mitad de los bits a la basura.

`abrir_stream` existe para poder probar el hilo **sin hardware**: por defecto abre
un `sounddevice.InputStream` real, y en las pruebas se inyecta un doble que entrega
bloques sintéticos. Sin esa costura, toda esta clase quedaría sin pruebas.

Nota sobre el entorno: el sistema del usuario tiene dispositivos virtuales
instalados (Teams, Zoom, Loom) y la entrada por defecto es el micrófono del
MacBook. Por eso **no existe** una función que "tome el dispositivo por defecto":
capturaría el micrófono en lugar de la guitarra. El dispositivo se elige siempre.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_captura.py
import numpy as np
import pytest

from nucleo.captura import (
    NOMBRE_ROCKSMITH,
    BufferCircular,
    CapturaAudio,
    DispositivoAudio,
    buscar_rocksmith,
)


def test_el_buffer_devuelve_none_hasta_tener_suficiente():
    buffer = BufferCircular(capacidad=100)
    buffer.escribir(np.arange(10, dtype=np.float32))
    assert buffer.leer_ultimas(20) is None


def test_el_buffer_devuelve_las_ultimas_muestras_en_orden():
    buffer = BufferCircular(capacidad=100)
    buffer.escribir(np.arange(50, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(5), np.arange(45, 50))


def test_el_buffer_sobrescribe_lo_mas_antiguo_al_dar_la_vuelta():
    """Perder muestras viejas es el comportamiento correcto: solo importa el presente."""
    buffer = BufferCircular(capacidad=10)
    buffer.escribir(np.arange(15, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(10), np.arange(5, 15))


def test_el_buffer_maneja_una_escritura_mayor_que_su_capacidad():
    buffer = BufferCircular(capacidad=8)
    buffer.escribir(np.arange(20, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(8), np.arange(12, 20))


def test_el_buffer_es_continuo_tras_varias_vueltas():
    buffer = BufferCircular(capacidad=16)
    for inicio in range(0, 100, 5):
        buffer.escribir(np.arange(inicio, inicio + 5, dtype=np.float32))
    np.testing.assert_array_equal(buffer.leer_ultimas(4), np.arange(96, 100))


def test_no_se_puede_pedir_mas_que_la_capacidad():
    buffer = BufferCircular(capacidad=10)
    buffer.escribir(np.arange(10, dtype=np.float32))
    assert buffer.leer_ultimas(11) is None


def test_reconoce_el_rocksmith_entre_otros_dispositivos():
    dispositivos = [
        DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0),
        DispositivoAudio(1, "ZoomAudioDevice", 2, 48000.0),
        DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0),
    ]
    encontrado = buscar_rocksmith(dispositivos)
    assert encontrado is not None
    assert encontrado.indice == 3


def test_sin_rocksmith_devuelve_none():
    dispositivos = [DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)]
    assert buscar_rocksmith(dispositivos) is None


class StreamFalso:
    """Doble de sounddevice.InputStream para probar el hilo sin hardware."""

    def __init__(self, callback, **kwargs):
        self.callback = callback
        self.latency = 0.012
        self.cerrado = False

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        self.cerrado = True

    def entregar(self, bloque: np.ndarray):
        """Simula que CoreAudio entrega un bloque."""
        self.callback(bloque.reshape(-1, 1), len(bloque), None, None)


def test_la_captura_acumula_los_bloques_entregados():
    creados = []

    def abrir(callback, **kwargs):
        stream = StreamFalso(callback, **kwargs)
        creados.append(stream)
        return stream

    captura = CapturaAudio(indice_dispositivo=3, capacidad_buffer=4096, abrir_stream=abrir)
    captura.iniciar()
    for _ in range(4):
        creados[0].entregar(np.full(512, 0.25, dtype=np.float32))

    ventana = captura.leer_ventana(2048)
    assert ventana is not None
    assert ventana.shape == (2048,)
    assert ventana.dtype == np.float32
    assert np.allclose(ventana, 0.25)
    captura.detener()
    assert creados[0].cerrado is True


def test_la_ganancia_multiplica_la_senal():
    """El cable entrega nivel bajo: la ganancia digital es parte del diseño."""
    creados = []

    def abrir(callback, **kwargs):
        stream = StreamFalso(callback, **kwargs)
        creados.append(stream)
        return stream

    captura = CapturaAudio(
        indice_dispositivo=3, capacidad_buffer=4096, ganancia=4.0, abrir_stream=abrir
    )
    captura.iniciar()
    creados[0].entregar(np.full(1024, 0.1, dtype=np.float32))
    assert np.allclose(captura.leer_ventana(1024), 0.4)
    captura.detener()


def test_la_latencia_se_reporta_en_milisegundos():
    captura = CapturaAudio(
        indice_dispositivo=3, abrir_stream=lambda callback, **kw: StreamFalso(callback)
    )
    captura.iniciar()
    assert captura.latencia_ms == pytest.approx(12.0, abs=0.1)
    captura.detener()


def test_un_fallo_al_abrir_se_guarda_en_lugar_de_reventar():
    def abrir_que_falla(callback, **kwargs):
        raise OSError("Device unavailable")

    captura = CapturaAudio(indice_dispositivo=99, abrir_stream=abrir_que_falla)
    captura.iniciar()
    assert captura.activa is False
    assert "Device unavailable" in captura.ultimo_error
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_captura.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.captura'`

- [ ] **Step 3: Implementar `nucleo/captura.py`**

```python
"""Captura de audio desde el dispositivo elegido.

Única parte del proyecto sensible al tiempo real. Regla que no se negocia: el
callback de audio nunca se bloquea. Sin cálculo, sin red, sin asignar memoria, sin
locks que puedan esperar. Copia el bloque al buffer y retorna.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np

NOMBRE_ROCKSMITH = "Rocksmith USB Guitar Adapter"


@dataclass(frozen=True)
class DispositivoAudio:
    """Una entrada de audio del sistema."""

    indice: int
    nombre: str
    canales_entrada: int
    frecuencia_muestreo: float


class BufferCircular:
    """Almacén de muestras de tamaño fijo que sobrescribe lo más antiguo.

    La memoria se reserva una sola vez al construirlo: asignar memoria dentro del
    callback de audio es justo lo que hay que evitar. Cuando se llena, lo viejo se
    pierde, que es el comportamiento correcto para un afinador donde solo importa el
    presente.
    """

    def __init__(self, capacidad: int) -> None:
        if capacidad < 1:
            raise ValueError("La capacidad debe ser positiva")
        self._capacidad = capacidad
        self._datos = np.zeros(capacidad, dtype=np.float32)
        self._posicion = 0
        self._total = 0

    @property
    def total_escrito(self) -> int:
        """Muestras escritas desde el inicio, incluidas las ya sobrescritas."""
        return self._total

    def escribir(self, bloque: np.ndarray) -> None:
        """Copia un bloque al buffer. Llamado desde el callback de audio."""
        n = bloque.size
        if n >= self._capacidad:
            self._datos[:] = bloque[-self._capacidad :]
            self._posicion = 0
        else:
            fin = self._posicion + n
            if fin <= self._capacidad:
                self._datos[self._posicion : fin] = bloque
            else:
                corte = self._capacidad - self._posicion
                self._datos[self._posicion :] = bloque[:corte]
                self._datos[: n - corte] = bloque[corte:]
            self._posicion = fin % self._capacidad
        self._total += n

    def leer_ultimas(self, n: int) -> np.ndarray | None:
        """Copia de las n muestras más recientes, o None si aún no hay tantas."""
        if n > self._capacidad or self._total < n:
            return None
        inicio = (self._posicion - n) % self._capacidad
        if inicio + n <= self._capacidad:
            return self._datos[inicio : inicio + n].copy()
        corte = self._capacidad - inicio
        return np.concatenate((self._datos[inicio:], self._datos[: n - corte]))


def listar_dispositivos_entrada() -> list[DispositivoAudio]:
    """Entradas de audio disponibles en el sistema.

    Devuelve lista vacía si macOS no ha concedido permiso de micrófono: el sistema
    no da error, simplemente no enseña nada. Distinguir ese caso es trabajo del
    diagnóstico.
    """
    import sounddevice

    dispositivos = []
    for indice, info in enumerate(sounddevice.query_devices()):
        if info["max_input_channels"] > 0:
            dispositivos.append(
                DispositivoAudio(
                    indice=indice,
                    nombre=info["name"],
                    canales_entrada=info["max_input_channels"],
                    frecuencia_muestreo=info["default_samplerate"],
                )
            )
    return dispositivos


def buscar_rocksmith(
    dispositivos: list[DispositivoAudio] | None = None,
) -> DispositivoAudio | None:
    """Busca el cable Rocksmith por nombre. None si no está conectado."""
    if dispositivos is None:
        dispositivos = listar_dispositivos_entrada()
    for dispositivo in dispositivos:
        if NOMBRE_ROCKSMITH.lower() in dispositivo.nombre.lower():
            return dispositivo
    return None


def _abrir_stream_real(callback: Callable, **argumentos):
    """Abre un InputStream de sounddevice. Aislado aquí para poder sustituirlo."""
    import sounddevice

    return sounddevice.InputStream(callback=callback, **argumentos)


class CapturaAudio:
    """Hilo de audio que vuelca el dispositivo elegido en un buffer circular.

    abrir_stream permite inyectar un doble en las pruebas y así ejercitar toda la
    clase sin hardware.
    """

    def __init__(
        self,
        indice_dispositivo: int,
        frecuencia_muestreo: int = 48000,
        tamano_bloque: int = 512,
        capacidad_buffer: int = 48000,
        ganancia: float = 1.0,
        abrir_stream: Callable | None = None,
    ) -> None:
        self.indice_dispositivo = indice_dispositivo
        self.frecuencia_muestreo = frecuencia_muestreo
        self.tamano_bloque = tamano_bloque
        self.ganancia = ganancia
        self._buffer = BufferCircular(capacidad_buffer)
        self._abrir_stream = abrir_stream or _abrir_stream_real
        self._stream = None
        self._ultimo_error: str | None = None
        self._desbordes = 0

    @property
    def activa(self) -> bool:
        """Verdadero si el stream está abierto."""
        return self._stream is not None

    @property
    def ultimo_error(self) -> str | None:
        """Texto del último fallo, o None si no ha habido ninguno."""
        return self._ultimo_error

    @property
    def desbordes(self) -> int:
        """Veces que CoreAudio reportó pérdida de muestras."""
        return self._desbordes

    @property
    def latencia_ms(self) -> float:
        """Latencia de entrada reportada por el dispositivo, en milisegundos."""
        if self._stream is None:
            return 0.0
        return float(self._stream.latency) * 1000.0

    @property
    def total_capturado(self) -> int:
        """Muestras capturadas desde el inicio."""
        return self._buffer.total_escrito

    def _callback(self, datos, cuadros, tiempo, estado) -> None:
        """Callback de audio. NO BLOQUEAR: copiar y salir, nada más."""
        if estado:
            self._desbordes += 1
        self._buffer.escribir(datos[:, 0] * self.ganancia)

    def iniciar(self) -> bool:
        """Abre el stream. Devuelve False y guarda el error si no se pudo."""
        if self._stream is not None:
            return True
        try:
            self._stream = self._abrir_stream(
                self._callback,
                device=self.indice_dispositivo,
                channels=1,
                samplerate=self.frecuencia_muestreo,
                blocksize=self.tamano_bloque,
                dtype="float32",
            )
            self._stream.start()
            self._ultimo_error = None
            return True
        except Exception as error:
            self._stream = None
            self._ultimo_error = str(error)
            return False

    def detener(self) -> None:
        """Cierra el stream y libera el dispositivo."""
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

    def leer_ventana(self, n: int) -> np.ndarray | None:
        """Últimas n muestras capturadas, o None si todavía no hay suficientes."""
        return self._buffer.leer_ultimas(n)
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_captura.py -v`
Esperado: PASS, 12 pruebas, sin tocar el hardware.

- [ ] **Step 5: Commit**

```bash
git add nucleo/captura.py tests/test_captura.py
git commit -m "feat: captura de audio con buffer circular y ganancia digital"
```

---

### Task 7: Verificación con el hardware real y muestras de referencia

**Files:**
- Create: `herramientas/__init__.py`
- Create: `herramientas/verificar_cable.py`
- Create: `herramientas/grabar_muestras.py`
- Create: `tests/test_audio_real.py`
- Create: `tests/audio/` (directorio para las grabaciones)

**Interfaces:**
- Consumes: `nucleo.captura`, `nucleo.analisis.pipeline.Analizador`, `nucleo.afinaciones.PERFILES`
- Produces:
  - `herramientas/verificar_cable.py` ejecutable con `python -m herramientas.verificar_cable`
  - `herramientas/grabar_muestras.py` ejecutable con `python -m herramientas.grabar_muestras`
  - `tests/audio/cuerda_6_mi2.wav` … `tests/audio/cuerda_1_mi4.wav` — seis grabaciones de las cuerdas al aire

**Contexto para quien implementa.** Hasta aquí todo se ha probado con señales
sintéticas. Esta tarea es el primer contacto con la guitarra real y existe por una
razón concreta: una senoide perfecta no se parece a una cuerda pulsada. Una cuerda
real tiene ataque, armónicos que decaen a ritmos distintos, ruido de púa y de
dedos, y una inarmonicidad que hace que sus parciales no sean múltiplos exactos de
la fundamental. Si el análisis solo funciona con senoides, no funciona.

Las grabaciones se versionan en el repositorio. Eso convierte la guitarra concreta
del usuario en una prueba automática permanente: si un cambio futuro rompe la
detección de su 6ª cuerda, la prueba falla antes de que él lo note tocando.

**Esta tarea requiere al usuario presente con la guitarra conectada.** Los pasos que
necesitan hardware están marcados. Las grabaciones son cortas (3 segundos por
cuerda) y el script guía el proceso.

- [ ] **Step 1: Escribir `herramientas/verificar_cable.py`**

```python
"""Comprueba que el cable está conectado, llega señal y el análisis la reconoce.

Uso:  .venv/bin/python -m herramientas.verificar_cable
"""

import sys
import time

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador
from nucleo.captura import CapturaAudio, buscar_rocksmith, listar_dispositivos_entrada


def main() -> int:
    dispositivos = listar_dispositivos_entrada()
    if not dispositivos:
        print("No se ve ninguna entrada de audio.")
        print("Causa más probable: macOS no ha dado permiso de micrófono a esta app.")
        print("Ajustes del Sistema → Privacidad y seguridad → Micrófono")
        return 1

    print(f"Entradas de audio detectadas: {len(dispositivos)}")
    for dispositivo in dispositivos:
        print(f"  [{dispositivo.indice}] {dispositivo.nombre}")

    cable = buscar_rocksmith(dispositivos)
    if cable is None:
        print("\nEl cable Rocksmith no aparece. Revisa que esté conectado al USB.")
        return 1
    print(f"\nCable encontrado: [{cable.indice}] {cable.nombre}")

    perfil = PERFILES["guitarra_estandar"]
    captura = CapturaAudio(indice_dispositivo=cable.indice, capacidad_buffer=96000)
    if not captura.iniciar():
        print(f"No se pudo abrir el dispositivo: {captura.ultimo_error}")
        return 1

    print(f"Latencia de entrada: {captura.latencia_ms:.1f} ms")
    print("\nToca cuerdas durante 10 segundos...\n")

    analizador = Analizador(perfil)
    ventana = perfil.tamano_ventana()
    final = time.monotonic() + 10.0
    notas_vistas = set()

    while time.monotonic() < final:
        muestras = captura.leer_ventana(ventana)
        if muestras is not None:
            resultado = analizador.procesar(muestras)
            if resultado.estado == "nota":
                notas_vistas.add(resultado.nota)
                print(
                    f"  {resultado.nota:>4}  {resultado.cents:+6.1f} cents  "
                    f"{resultado.frecuencia:7.2f} Hz  nivel {resultado.nivel_db:6.1f} dBFS",
                    end="\r",
                )
        time.sleep(0.03)

    captura.detener()
    print("\n")
    if not notas_vistas:
        print("No se detectó ninguna nota.")
        print("Revisa el volumen de la guitarra: es la causa más frecuente.")
        return 1
    print(f"Notas detectadas: {', '.join(sorted(notas_vistas))}")
    print(f"Desbordes de audio: {captura.desbordes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

También crear `herramientas/__init__.py` vacío.

- [ ] **Step 2: Ejecutar la verificación con el cable conectado** *(requiere hardware)*

Run: `.venv/bin/python -m herramientas.verificar_cable`

Esperado: encuentra el dispositivo `Rocksmith USB Guitar Adapter`, reporta una
latencia en el rango de 10 a 30 ms, y al tocar las seis cuerdas al aire imprime
`E2, A2, D3, G3, B3, E4`. Los desbordes deben ser 0.

Si detecta notas pero equivocadas por una octava, el problema está en el umbral de
YIN. Si no detecta nada pese a haber señal, el umbral de ruido de −60 dBFS es
demasiado alto para esta guitarra y hay que recalibrarlo.

- [ ] **Step 3: Escribir `herramientas/grabar_muestras.py`**

```python
"""Graba las seis cuerdas al aire para usarlas como pruebas permanentes.

Uso:  .venv/bin/python -m herramientas.grabar_muestras
"""

import sys
import time
from pathlib import Path

import numpy as np
import soundfile

from nucleo.afinaciones import PERFILES
from nucleo.captura import CapturaAudio, buscar_rocksmith

DESTINO = Path(__file__).resolve().parent.parent / "tests" / "audio"
SEGUNDOS = 3.0
FS = 48000


def main() -> int:
    cable = buscar_rocksmith()
    if cable is None:
        print("El cable Rocksmith no aparece. Conéctalo y reintenta.")
        return 1

    DESTINO.mkdir(parents=True, exist_ok=True)
    perfil = PERFILES["guitarra_estandar"]
    captura = CapturaAudio(
        indice_dispositivo=cable.indice, capacidad_buffer=int(FS * (SEGUNDOS + 1))
    )
    if not captura.iniciar():
        print(f"No se pudo abrir el dispositivo: {captura.ultimo_error}")
        return 1

    for cuerda in perfil.cuerdas:
        nombre = f"cuerda_{cuerda.numero}_{cuerda.nota.lower()}.wav"
        input(f"\nCuerda {cuerda.numero} ({cuerda.nota}) al aire. Enter y púlsala...")
        inicio = captura.total_capturado
        while captura.total_capturado - inicio < FS * SEGUNDOS:
            time.sleep(0.05)
        muestras = captura.leer_ventana(int(FS * SEGUNDOS))
        soundfile.write(DESTINO / nombre, muestras.astype(np.float32), FS)
        print(f"  guardado {nombre}")

    captura.detener()
    print(f"\nGrabaciones en {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Grabar las seis cuerdas** *(requiere hardware)*

Run: `.venv/bin/python -m herramientas.grabar_muestras`

Pulsa cada cuerda al aire con fuerza normal cuando el script lo pida. Antes de
grabar, **afina la guitarra** con un afinador de confianza: estas grabaciones se
convertirán en la referencia y una cuerda mal afinada envenenaría las pruebas.

Esperado: seis archivos en `tests/audio/`.

- [ ] **Step 5: Escribir las pruebas con audio real**

```python
# tests/test_audio_real.py
"""Pruebas sobre grabaciones de la guitarra real.

Una senoide no se parece a una cuerda pulsada: falta el ataque, los armónicos que
decaen a distinto ritmo, el ruido de púa y la inarmonicidad de la cuerda. Estas
pruebas cierran esa brecha y convierten la guitarra concreta del usuario en una
verificación permanente.
"""

from pathlib import Path

import numpy as np
import pytest

soundfile = pytest.importorskip("soundfile")

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador

AUDIO = Path(__file__).parent / "audio"
GUITARRA = PERFILES["guitarra_estandar"]

CUERDAS = [
    ("cuerda_6_e2.wav", "E2", 6),
    ("cuerda_5_a2.wav", "A2", 5),
    ("cuerda_4_d3.wav", "D3", 4),
    ("cuerda_3_g3.wav", "G3", 3),
    ("cuerda_2_b3.wav", "B3", 2),
    ("cuerda_1_e4.wav", "E4", 1),
]


def analizar_archivo(nombre: str) -> list:
    """Recorre la grabación en ventanas solapadas y devuelve los resultados con nota."""
    ruta = AUDIO / nombre
    if not ruta.exists():
        pytest.skip(f"Falta {nombre}: ejecuta herramientas/grabar_muestras.py")
    muestras, frecuencia_muestreo = soundfile.read(ruta, dtype="float32")
    analizador = Analizador(GUITARRA, frecuencia_muestreo=frecuencia_muestreo)
    ventana = GUITARRA.tamano_ventana(frecuencia_muestreo)
    salto = ventana // 4

    resultados = []
    for inicio in range(0, len(muestras) - ventana, salto):
        resultado = analizador.procesar(muestras[inicio : inicio + ventana])
        if resultado.estado == "nota":
            resultados.append(resultado)
    return resultados


@pytest.mark.parametrize("archivo, nota_esperada, cuerda", CUERDAS)
def test_reconoce_cada_cuerda_real(archivo, nota_esperada, cuerda):
    resultados = analizar_archivo(archivo)
    assert resultados, f"No se detectó ninguna nota en {archivo}"
    correctas = [r for r in resultados if r.nota == nota_esperada]
    proporcion = len(correctas) / len(resultados)
    assert proporcion > 0.8, (
        f"Solo el {proporcion:.0%} de las ventanas dio {nota_esperada}. "
        f"Notas vistas: {sorted({r.nota for r in resultados})}"
    )


@pytest.mark.parametrize("archivo, nota_esperada, cuerda", CUERDAS)
def test_identifica_la_cuerda_correcta(archivo, nota_esperada, cuerda):
    resultados = [r for r in analizar_archivo(archivo) if r.nota == nota_esperada]
    assert resultados
    objetivos = [r.cuerda_objetivo for r in resultados]
    assert max(set(objetivos), key=objetivos.count) == cuerda


@pytest.mark.parametrize("archivo, nota_esperada, cuerda", CUERDAS)
def test_una_cuerda_afinada_se_lee_afinada(archivo, nota_esperada, cuerda):
    """La guitarra estaba afinada al grabar: el afinador debe coincidir."""
    resultados = [r for r in analizar_archivo(archivo) if r.nota == nota_esperada]
    assert resultados
    cents_medianos = float(np.median([r.cents for r in resultados]))
    assert abs(cents_medianos) < 15.0, f"Desviación mediana de {cents_medianos:.1f} cents"
```

- [ ] **Step 6: Ejecutar las pruebas con audio real**

Run: `.venv/bin/pytest tests/test_audio_real.py -v`
Esperado: PASS, 18 pruebas.

Si alguna cuerda falla por debajo del 80 %, anota qué notas aparecen en el mensaje
de error: si son la octava de la esperada, hay que bajar el umbral de YIN; si son
notas vecinas, la guitarra estaba desafinada al grabar y hay que regrabar.

- [ ] **Step 7: Commit**

```bash
git add herramientas/ tests/audio/ tests/test_audio_real.py
git commit -m "feat: verificación con hardware real y muestras de referencia"
```

---

### Task 8: Configuración persistente, calibración y diagnóstico

**Files:**
- Create: `servidor/__init__.py`
- Create: `servidor/configuracion.py`
- Create: `servidor/diagnostico.py`
- Test: `tests/test_configuracion.py`
- Test: `tests/test_diagnostico.py`

**Interfaces:**
- Consumes: `nucleo.afinaciones.PERFILES`, `nucleo.captura.DispositivoAudio`, `nucleo.analisis.energia`
- Produces:
  - `Configuracion(dispositivo: int | None = None, perfil: str = "guitarra_estandar", ganancia: float = 1.0, umbral_ruido_dbfs: float = -60.0, referencia_a4: float = 440.0, confianza_minima: float = 0.75, detector: str = "yin")` — dataclass mutable
  - `Configuracion.validar() -> None` — lanza `ValueError` con mensaje en español
  - `Configuracion.a_dict() -> dict` / `Configuracion.desde_dict(datos: dict) -> Configuracion`
  - `RUTA_POR_DEFECTO: Path`
  - `cargar(ruta: Path = RUTA_POR_DEFECTO) -> Configuracion`
  - `guardar(configuracion: Configuracion, ruta: Path = RUTA_POR_DEFECTO) -> None`
  - `calibrar_umbral(niveles_dbfs: list[float], margen_db: float = 14.0) -> float`
  - `Diagnostico(estado: str, mensaje: str, accion: str, dispositivos: list[dict])` — dataclass congelada, con `a_dict()`
  - `diagnosticar(dispositivos, cable, nivel_db=None, umbral_dbfs=-60.0) -> Diagnostico`

**Contexto para quien implementa.** El diagnóstico existe porque tres problemas muy
distintos producen el mismo síntoma para el usuario: no pasa nada. Sin distinguirlos
tendría que adivinar cuál tiene, y el más común —el volumen de la guitarra a cero—
es también el más tonto y el más frustrante de no ver.

Los tres estados y cómo se reconocen:

| Estado | Señal que lo identifica |
|---|---|
| `sin_permiso` | La lista de dispositivos viene **vacía**. macOS no da error: simplemente no enseña nada cuando falta el permiso de micrófono. |
| `sin_dispositivo` | Hay dispositivos, pero ninguno es el Rocksmith. |
| `sin_senal` | El dispositivo abre, pero el nivel no supera el umbral. |
| `ok` | Todo lo anterior en orden. |

La **calibración** toma niveles medidos con la guitarra en silencio y sitúa el
umbral por encima con un margen. El margen por defecto de 14 dB sale de la medición
del equipo real: ruido en −74,4 dBFS y umbral en −60. Se usa la **mediana** de los
niveles y no la media, por la misma razón que en el suavizado: un golpe accidental
durante la calibración es un valor atípico que debe descartarse, no promediarse.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_configuracion.py
import json

import pytest

from servidor.configuracion import Configuracion, calibrar_umbral, cargar, guardar


def test_los_valores_por_defecto_son_los_de_la_spec():
    config = Configuracion()
    assert config.perfil == "guitarra_estandar"
    assert config.umbral_ruido_dbfs == -60.0
    assert config.referencia_a4 == 440.0
    assert config.ganancia == 1.0
    assert config.detector == "yin"
    assert config.dispositivo is None


def test_un_perfil_inexistente_se_rechaza_con_mensaje_claro():
    with pytest.raises(ValueError, match="perfil"):
        Configuracion(perfil="ukelele").validar()


def test_una_ganancia_negativa_se_rechaza():
    with pytest.raises(ValueError, match="ganancia"):
        Configuracion(ganancia=-1.0).validar()


def test_una_referencia_absurda_se_rechaza():
    with pytest.raises(ValueError, match="referencia"):
        Configuracion(referencia_a4=20.0).validar()


def test_guardar_y_cargar_conserva_todo(tmp_path):
    ruta = tmp_path / "config.json"
    original = Configuracion(dispositivo=3, perfil="bajo_5", ganancia=2.5)
    guardar(original, ruta)
    assert cargar(ruta) == original


def test_cargar_sin_archivo_da_los_valores_por_defecto(tmp_path):
    assert cargar(tmp_path / "no_existe.json") == Configuracion()


def test_un_archivo_corrupto_no_rompe_el_arranque(tmp_path):
    """Preferible arrancar con valores por defecto que no arrancar."""
    ruta = tmp_path / "config.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cargar(ruta) == Configuracion()


def test_un_archivo_con_campos_desconocidos_los_ignora(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"perfil": "bajo_4", "inventado": 1}), encoding="utf-8")
    assert cargar(ruta).perfil == "bajo_4"


def test_la_calibracion_deja_margen_sobre_el_ruido():
    """Niveles medidos en el equipo real: ruido en torno a -74 dBFS."""
    assert calibrar_umbral([-74.4, -74.1, -74.8, -73.9]) == pytest.approx(-60.2, abs=0.5)


def test_la_calibracion_descarta_un_golpe_accidental():
    """Un ruido puntual durante la calibración no debe subir el umbral."""
    con_golpe = calibrar_umbral([-74.0, -74.0, -30.0, -74.0, -74.0])
    assert con_golpe == pytest.approx(-60.0, abs=0.5)


def test_el_margen_de_calibracion_es_ajustable():
    assert calibrar_umbral([-74.0], margen_db=20.0) == pytest.approx(-54.0, abs=0.1)
```

```python
# tests/test_diagnostico.py
from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.diagnostico import diagnosticar

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
MICROFONO = DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)


def test_lista_vacia_significa_falta_de_permiso():
    """macOS no da error cuando falta el permiso: devuelve una lista vacía."""
    resultado = diagnosticar(dispositivos=[], cable=None)
    assert resultado.estado == "sin_permiso"
    assert "Micrófono" in resultado.accion


def test_sin_el_cable_lo_dice_sin_hablar_de_permisos():
    resultado = diagnosticar(dispositivos=[MICROFONO], cable=None)
    assert resultado.estado == "sin_dispositivo"
    assert "USB" in resultado.accion


def test_nivel_bajo_sugiere_el_volumen_de_la_guitarra():
    """La causa más frecuente y la más fácil de pasar por alto."""
    resultado = diagnosticar(dispositivos=[CABLE], cable=CABLE, nivel_db=-95.0)
    assert resultado.estado == "sin_senal"
    assert "volumen" in resultado.accion.lower()


def test_todo_en_orden_da_ok():
    resultado = diagnosticar(dispositivos=[CABLE], cable=CABLE, nivel_db=-40.0)
    assert resultado.estado == "ok"


def test_sin_medicion_de_nivel_no_se_declara_falta_de_senal():
    """Antes de capturar no se sabe si hay señal: no se debe acusar en falso."""
    resultado = diagnosticar(dispositivos=[CABLE], cable=CABLE, nivel_db=None)
    assert resultado.estado == "ok"


def test_el_diagnostico_lista_los_dispositivos_para_elegir_a_mano():
    resultado = diagnosticar(dispositivos=[MICROFONO, CABLE], cable=CABLE)
    assert len(resultado.a_dict()["dispositivos"]) == 2
    assert resultado.a_dict()["dispositivos"][1]["nombre"] == NOMBRE_ROCKSMITH
```

- [ ] **Step 2: Ejecutar las pruebas y verificar que fallan**

Run: `.venv/bin/pytest tests/test_configuracion.py tests/test_diagnostico.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'servidor.configuracion'`

- [ ] **Step 3: Implementar `servidor/configuracion.py`**

```python
"""Configuración persistente y calibración del umbral de ruido."""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS

RUTA_POR_DEFECTO = Path(__file__).resolve().parent.parent / "config_local.json"

# Margen sobre el piso de ruido medido. 14 dB es lo que separa el ruido medido en el
# equipo real (-74,4 dBFS) del umbral elegido (-60 dBFS).
MARGEN_CALIBRACION_DB = 14.0


@dataclass
class Configuracion:
    """Ajustes que el usuario elige y que sobreviven entre sesiones."""

    dispositivo: int | None = None
    perfil: str = "guitarra_estandar"
    ganancia: float = 1.0
    umbral_ruido_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS
    referencia_a4: float = 440.0
    confianza_minima: float = 0.75
    detector: str = "yin"

    def validar(self) -> None:
        """Lanza ValueError con un mensaje en español si algo no cuadra."""
        if self.perfil not in PERFILES:
            disponibles = ", ".join(sorted(PERFILES))
            raise ValueError(f"El perfil '{self.perfil}' no existe. Opciones: {disponibles}")
        if self.ganancia <= 0.0:
            raise ValueError("La ganancia debe ser mayor que cero")
        if not 380.0 <= self.referencia_a4 <= 500.0:
            raise ValueError("La referencia A4 debe estar entre 380 y 500 Hz")
        if not 0.0 <= self.confianza_minima <= 1.0:
            raise ValueError("La confianza mínima debe estar entre 0 y 1")

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, datos: dict) -> "Configuracion":
        """Construye desde un diccionario, ignorando campos desconocidos."""
        conocidos = {campo.name for campo in fields(cls)}
        return cls(**{clave: valor for clave, valor in datos.items() if clave in conocidos})


def cargar(ruta: Path = RUTA_POR_DEFECTO) -> Configuracion:
    """Lee la configuración del disco.

    Ante un archivo ausente o corrupto devuelve los valores por defecto en lugar de
    fallar: arrancar con valores razonables es mejor que no arrancar.
    """
    try:
        return Configuracion.desde_dict(json.loads(ruta.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return Configuracion()


def guardar(configuracion: Configuracion, ruta: Path = RUTA_POR_DEFECTO) -> None:
    """Escribe la configuración, validándola antes."""
    configuracion.validar()
    ruta.write_text(
        json.dumps(configuracion.a_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def calibrar_umbral(
    niveles_dbfs: list[float], margen_db: float = MARGEN_CALIBRACION_DB
) -> float:
    """Umbral de la compuerta a partir de niveles medidos en silencio.

        umbral = mediana(niveles) + margen

    Se usa la mediana y no la media porque un golpe accidental durante la
    calibración es un valor atípico que hay que descartar, no promediar.
    """
    if not niveles_dbfs:
        return UMBRAL_RUIDO_POR_DEFECTO_DBFS
    return float(np.median(niveles_dbfs)) + margen_db
```

- [ ] **Step 4: Implementar `servidor/diagnostico.py`**

```python
"""Distingue los tres fallos que para el usuario se ven todos igual: no pasa nada."""

from dataclasses import dataclass

from nucleo.captura import DispositivoAudio


@dataclass(frozen=True)
class Diagnostico:
    """Estado del montaje, con una acción concreta que el usuario puede ejecutar."""

    estado: str
    mensaje: str
    accion: str
    dispositivos: list[DispositivoAudio]

    def a_dict(self) -> dict:
        return {
            "estado": self.estado,
            "mensaje": self.mensaje,
            "accion": self.accion,
            "dispositivos": [
                {
                    "indice": d.indice,
                    "nombre": d.nombre,
                    "canales_entrada": d.canales_entrada,
                    "frecuencia_muestreo": d.frecuencia_muestreo,
                }
                for d in self.dispositivos
            ],
        }


def diagnosticar(
    dispositivos: list[DispositivoAudio],
    cable: DispositivoAudio | None,
    nivel_db: float | None = None,
    umbral_dbfs: float = -60.0,
) -> Diagnostico:
    """Determina en cuál de los cuatro estados está el montaje.

    nivel_db en None significa que todavía no se ha medido nada: en ese caso no se
    declara falta de señal, porque sería acusar en falso antes de mirar.
    """
    if not dispositivos:
        return Diagnostico(
            estado="sin_permiso",
            mensaje="No se ve ninguna entrada de audio en el sistema.",
            accion=(
                "macOS no ha dado permiso de micrófono a esta aplicación. "
                "Ve a Ajustes del Sistema → Privacidad y seguridad → Micrófono "
                "y actívalo para el programa desde el que lanzaste esto."
            ),
            dispositivos=dispositivos,
        )

    if cable is None:
        return Diagnostico(
            estado="sin_dispositivo",
            mensaje="El cable Rocksmith no aparece entre los dispositivos.",
            accion=(
                "Comprueba que el cable esté conectado al puerto USB. "
                "Si lo está, prueba otro puerto o elige el dispositivo a mano."
            ),
            dispositivos=dispositivos,
        )

    if nivel_db is not None and nivel_db <= umbral_dbfs:
        return Diagnostico(
            estado="sin_senal",
            mensaje="El cable está conectado pero no llega señal.",
            accion=(
                "Sube el volumen de la guitarra: es la causa más frecuente. "
                "Verifica también que el jack esté bien insertado en el instrumento."
            ),
            dispositivos=dispositivos,
        )

    return Diagnostico(
        estado="ok",
        mensaje=f"Cable conectado: {cable.nombre}",
        accion="",
        dispositivos=dispositivos,
    )
```

También crear `servidor/__init__.py` vacío.

- [ ] **Step 5: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_configuracion.py tests/test_diagnostico.py -v`
Esperado: PASS, 17 pruebas.

- [ ] **Step 6: Commit**

```bash
git add servidor/ tests/test_configuracion.py tests/test_diagnostico.py
git commit -m "feat: configuración persistente, calibración y diagnóstico"
```

---

### Task 9: Registro de módulos y sesión de análisis

**Files:**
- Create: `servidor/modulos.py`
- Create: `servidor/sesion.py`
- Test: `tests/test_modulos.py`
- Test: `tests/test_sesion.py`

**Interfaces:**
- Consumes: `servidor.configuracion.Configuracion`, `servidor.diagnostico.diagnosticar`, `nucleo.captura`, `nucleo.analisis.pipeline.Analizador`, `nucleo.afinaciones.PERFILES`
- Produces:
  - `Modulo(clave: str, nombre: str, descripcion: str, icono: str, disponible: bool = True)` — dataclass congelada con `a_dict()`
  - `registrar_modulo(modulo: Modulo) -> None`, `listar_modulos() -> list[Modulo]`, `obtener_modulo(clave: str) -> Modulo`
  - `Sesion(configuracion, crear_captura=None, listar=None)` con `iniciar() -> Diagnostico`, `detener() -> None`, `ultimo_resultado() -> ResultadoAnalisis | None`, `aplicar(configuracion: Configuracion) -> None`, `calibrar(segundos: float = 2.0) -> float`, `diagnostico() -> Diagnostico`, propiedades `activa: bool`, `latencia_ms: float`

**Contexto para quien implementa.** Dos piezas, y conviene entender por qué existe
cada una.

**El registro de módulos** es la respuesta a que esto no acabe siendo solo un
afinador. Un módulo es una pantalla de la aplicación con su propósito: el afinador
es el primero, y las etapas siguientes añadirán ejercicios, canciones, grabación y
efectos. Registrarlos significa que la interfaz los descubre en lugar de tenerlos
escritos a mano, y que añadir uno nuevo no obliga a tocar el armazón. Como el
registro de detectores, es deliberadamente mínimo: un diccionario y tres funciones.

**La sesión** es el objeto que une captura y análisis y los mantiene corriendo. Su
hilo de trabajo lee la última ventana, la analiza y guarda el resultado; nadie más
toca ni la captura ni el analizador. Se guarda **solo el último resultado**, no una
cola: un consumidor lento debe ver el presente, no desenterrar el pasado.

`crear_captura` y `listar` se inyectan para poder probar la sesión entera sin
hardware, igual que `abrir_stream` en la captura.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_modulos.py
import pytest

from servidor.modulos import Modulo, listar_modulos, obtener_modulo, registrar_modulo


def test_el_afinador_viene_registrado():
    claves = [modulo.clave for modulo in listar_modulos()]
    assert "afinador" in claves


def test_el_afinador_esta_disponible():
    assert obtener_modulo("afinador").disponible is True


def test_se_puede_registrar_un_modulo_nuevo():
    """Las etapas siguientes añadirán ejercicios y canciones sin tocar el armazón."""
    registrar_modulo(
        Modulo(clave="ejercicios", nombre="Ejercicios", descripcion="Escalas", icono="🎯")
    )
    assert obtener_modulo("ejercicios").nombre == "Ejercicios"
    assert "ejercicios" in [m.clave for m in listar_modulos()]


def test_pedir_un_modulo_inexistente_es_un_error_claro():
    with pytest.raises(KeyError, match="canciones"):
        obtener_modulo("canciones")


def test_el_modulo_se_serializa_para_la_interfaz():
    datos = obtener_modulo("afinador").a_dict()
    assert set(datos) == {"clave", "nombre", "descripcion", "icono", "disponible"}
```

```python
# tests/test_sesion.py
import time

import numpy as np

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.configuracion import Configuracion
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
MICROFONO = DispositivoAudio(0, "MacBook Pro Microphone", 1, 48000.0)
FS = 48000


class CapturaFalsa:
    """Doble de CapturaAudio que devuelve siempre la misma ventana."""

    def __init__(self, frecuencia: float = 82.41, amplitud: float = 0.3, **kwargs):
        self.frecuencia = frecuencia
        self.amplitud = amplitud
        self.iniciada = False
        self.detenida = False
        self.ganancia = kwargs.get("ganancia", 1.0)
        self.ultimo_error = None
        self.latencia_ms = 12.0

    def iniciar(self) -> bool:
        self.iniciada = True
        return True

    def detener(self) -> None:
        self.detenida = True

    def leer_ventana(self, n: int):
        t = np.arange(n) / FS
        return (self.amplitud * np.sin(2 * np.pi * self.frecuencia * t)).astype(np.float32)


def esperar_resultado(sesion, intentos: int = 100):
    for _ in range(intentos):
        resultado = sesion.ultimo_resultado()
        if resultado is not None and resultado.estado == "nota":
            return resultado
        time.sleep(0.02)
    return sesion.ultimo_resultado()


def test_la_sesion_analiza_en_segundo_plano():
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [MICROFONO, CABLE],
    )
    assert sesion.iniciar().estado == "ok"
    resultado = esperar_resultado(sesion)
    assert resultado is not None
    assert resultado.nota == "E2"
    sesion.detener()
    assert sesion.activa is False


def test_sin_dispositivos_la_sesion_no_arranca_y_explica_por_que():
    sesion = Sesion(
        Configuracion(),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [],
    )
    diagnostico = sesion.iniciar()
    assert diagnostico.estado == "sin_permiso"
    assert sesion.activa is False


def test_sin_dispositivo_elegido_se_usa_el_rocksmith():
    """Nunca la entrada por defecto: sería el micrófono del MacBook."""
    creadas = []

    def crear(**kw):
        captura = CapturaFalsa(**kw)
        creadas.append(kw)
        return captura

    sesion = Sesion(Configuracion(), crear_captura=crear, listar=lambda: [MICROFONO, CABLE])
    sesion.iniciar()
    assert creadas[0]["indice_dispositivo"] == 3
    sesion.detener()


def test_cambiar_de_perfil_reinicia_el_analisis():
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(frecuencia=30.87, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    sesion.aplicar(Configuracion(dispositivo=3, perfil="bajo_5"))
    resultado = esperar_resultado(sesion)
    assert resultado.nota == "B0"
    sesion.detener()


def test_la_calibracion_devuelve_un_umbral_sobre_el_ruido():
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(amplitud=0.0002, **kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    umbral = sesion.calibrar(segundos=0.2)
    assert -75.0 < umbral < -45.0
    sesion.detener()


def test_detener_dos_veces_no_falla():
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    sesion.detener()
    sesion.detener()
```

- [ ] **Step 2: Ejecutar las pruebas y verificar que fallan**

Run: `.venv/bin/pytest tests/test_modulos.py tests/test_sesion.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'servidor.modulos'`

- [ ] **Step 3: Implementar `servidor/modulos.py`**

```python
"""Registro de los módulos de la aplicación.

Un módulo es una pantalla con su propósito. El afinador es el primero; las etapas
siguientes añadirán ejercicios, canciones, grabación y efectos. Que la interfaz los
descubra aquí en vez de tenerlos escritos a mano es lo que permite añadir uno nuevo
sin tocar el armazón.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Modulo:
    """Una pantalla de la aplicación.

    disponible en False permite anunciar un módulo futuro sin que se pueda abrir.
    """

    clave: str
    nombre: str
    descripcion: str
    icono: str
    disponible: bool = True

    def a_dict(self) -> dict:
        return asdict(self)


_MODULOS: dict[str, Modulo] = {}


def registrar_modulo(modulo: Modulo) -> None:
    """Añade un módulo al registro, sustituyendo el anterior con esa clave."""
    _MODULOS[modulo.clave] = modulo


def obtener_modulo(clave: str) -> Modulo:
    """Devuelve un módulo por clave. Lanza KeyError si no existe."""
    if clave not in _MODULOS:
        disponibles = ", ".join(sorted(_MODULOS)) or "ninguno"
        raise KeyError(f"No existe el módulo '{clave}'. Disponibles: {disponibles}")
    return _MODULOS[clave]


def listar_modulos() -> list[Modulo]:
    """Módulos registrados, ordenados por clave."""
    return [_MODULOS[clave] for clave in sorted(_MODULOS)]


registrar_modulo(
    Modulo(
        clave="afinador",
        nombre="Afinador",
        descripcion="Afina tu instrumento y mira qué notas tocas en el mástil",
        icono="🎸",
    )
)
```

- [ ] **Step 4: Implementar `servidor/sesion.py`**

```python
"""Une captura y análisis, y los mantiene corriendo en segundo plano."""

import threading
import time
from typing import Callable

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import nivel_dbfs
from nucleo.analisis.pipeline import Analizador, ResultadoAnalisis
from nucleo.captura import CapturaAudio, buscar_rocksmith, listar_dispositivos_entrada
from servidor.configuracion import Configuracion, calibrar_umbral
from servidor.diagnostico import Diagnostico, diagnosticar

# Cada cuánto analiza el hilo de trabajo. 21 ms son 512 muestras a 48 kHz: el mismo
# ritmo al que llegan los bloques, sin analizar más veces de las que hay datos nuevos.
INTERVALO_ANALISIS = 0.021


class Sesion:
    """Propietaria única de la captura y el analizador.

    Guarda solo el último resultado, no una cola: un consumidor lento debe ver el
    presente, no desenterrar el pasado.
    """

    def __init__(
        self,
        configuracion: Configuracion,
        crear_captura: Callable | None = None,
        listar: Callable | None = None,
    ) -> None:
        self.configuracion = configuracion
        self._crear_captura = crear_captura or (lambda **kw: CapturaAudio(**kw))
        self._listar = listar or listar_dispositivos_entrada
        self._captura = None
        self._analizador: Analizador | None = None
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._ultimo: ResultadoAnalisis | None = None
        self._candado = threading.Lock()

    @property
    def activa(self) -> bool:
        return self._captura is not None

    @property
    def latencia_ms(self) -> float:
        return self._captura.latencia_ms if self._captura else 0.0

    def diagnostico(self, nivel_db: float | None = None) -> Diagnostico:
        """Estado actual del montaje."""
        dispositivos = self._listar()
        cable = buscar_rocksmith(dispositivos)
        if self.configuracion.dispositivo is not None:
            elegido = next(
                (d for d in dispositivos if d.indice == self.configuracion.dispositivo), None
            )
            if elegido is not None:
                cable = elegido
        return diagnosticar(
            dispositivos, cable, nivel_db, self.configuracion.umbral_ruido_dbfs
        )

    def _construir_analizador(self) -> Analizador:
        return Analizador(
            PERFILES[self.configuracion.perfil],
            umbral_ruido_dbfs=self.configuracion.umbral_ruido_dbfs,
            referencia_a4=self.configuracion.referencia_a4,
            confianza_minima=self.configuracion.confianza_minima,
            nombre_detector=self.configuracion.detector,
        )

    def iniciar(self) -> Diagnostico:
        """Abre el dispositivo y arranca el hilo de análisis.

        Devuelve el diagnóstico: si no es "ok", la sesión no queda activa y el
        diagnóstico explica qué falta.
        """
        if self.activa:
            return self.diagnostico()

        estado = self.diagnostico()
        if estado.estado in ("sin_permiso", "sin_dispositivo"):
            return estado

        indice = self.configuracion.dispositivo
        if indice is None:
            cable = buscar_rocksmith(self._listar())
            if cable is None:
                return estado
            indice = cable.indice

        self._captura = self._crear_captura(
            indice_dispositivo=indice, ganancia=self.configuracion.ganancia
        )
        if not self._captura.iniciar():
            error = self._captura.ultimo_error
            self._captura = None
            return Diagnostico(
                estado="sin_dispositivo",
                mensaje="No se pudo abrir el dispositivo de audio.",
                accion=f"Error del sistema: {error}. Prueba a reconectar el cable.",
                dispositivos=self._listar(),
            )

        self._analizador = self._construir_analizador()
        self._parar.clear()
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return self.diagnostico()

    def _trabajar(self) -> None:
        """Hilo de análisis. Lee la última ventana, la analiza y guarda el resultado."""
        while not self._parar.is_set():
            captura, analizador = self._captura, self._analizador
            if captura is not None and analizador is not None:
                muestras = captura.leer_ventana(analizador.tamano_ventana)
                if muestras is not None:
                    resultado = analizador.procesar(muestras)
                    with self._candado:
                        self._ultimo = resultado
            time.sleep(INTERVALO_ANALISIS)

    def ultimo_resultado(self) -> ResultadoAnalisis | None:
        """Resultado más reciente, o None si aún no hay ninguno."""
        with self._candado:
            return self._ultimo

    def aplicar(self, configuracion: Configuracion) -> None:
        """Cambia la configuración en caliente.

        Si cambia el dispositivo o la ganancia hay que reabrir el stream; para el
        resto basta con reconstruir el analizador, que es instantáneo.
        """
        configuracion.validar()
        reabrir = (
            configuracion.dispositivo != self.configuracion.dispositivo
            or configuracion.ganancia != self.configuracion.ganancia
        )
        self.configuracion = configuracion
        if reabrir and self.activa:
            self.detener()
            self.iniciar()
        elif self.activa:
            self._analizador = self._construir_analizador()
            with self._candado:
                self._ultimo = None

    def calibrar(self, segundos: float = 2.0) -> float:
        """Mide el piso de ruido durante unos segundos y devuelve el umbral sugerido.

        El usuario debe estar en silencio mientras dura. No modifica la
        configuración: devolver el valor y dejar que el usuario lo acepte es
        preferible a cambiarle los ajustes por sorpresa.
        """
        if not self.activa or self._analizador is None:
            return self.configuracion.umbral_ruido_dbfs
        ventana = self._analizador.tamano_ventana
        niveles = []
        final = time.monotonic() + segundos
        while time.monotonic() < final:
            muestras = self._captura.leer_ventana(ventana)
            if muestras is not None:
                niveles.append(nivel_dbfs(muestras))
            time.sleep(0.05)
        return calibrar_umbral(niveles)

    def detener(self) -> None:
        """Para el hilo y cierra el dispositivo. Seguro de llamar varias veces."""
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
        if self._captura is not None:
            self._captura.detener()
            self._captura = None
        self._analizador = None
        with self._candado:
            self._ultimo = None
```

- [ ] **Step 5: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_modulos.py tests/test_sesion.py -v`
Esperado: PASS, 11 pruebas.

- [ ] **Step 6: Commit**

```bash
git add servidor/modulos.py servidor/sesion.py tests/test_modulos.py tests/test_sesion.py
git commit -m "feat: registro de módulos y sesión de análisis en segundo plano"
```

---

### Task 10: Servidor FastAPI y emisión por WebSocket

**Files:**
- Create: `servidor/app.py`
- Modify: `pyproject.toml` (añadir `httpx` a las dependencias de desarrollo)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `servidor.sesion.Sesion`, `servidor.configuracion`, `servidor.modulos`, `nucleo.afinaciones.PERFILES`
- Produces:
  - `crear_app(sesion: Sesion, ruta_interfaz: Path | None = None) -> FastAPI`
  - `FRECUENCIA_EMISION: float` = `30.0`
  - Endpoints: `GET /api/modulos`, `GET /api/perfiles`, `GET /api/dispositivos`, `GET /api/diagnostico`, `GET /api/config`, `PUT /api/config`, `POST /api/calibrar`, `WS /ws/notas`

**Contexto para quien implementa.** El servidor es una capa fina: no calcula nada,
solo expone lo que la sesión ya produce.

La decisión importante está en el WebSocket. Emite a **30 Hz fijos**, no a la
velocidad del análisis. La pantalla no puede mostrar más rápido que eso, y saturar
el socket solo añadiría retardo: cada mensaje de más es un mensaje que espera cola.
Se envía **siempre el último resultado disponible**, aunque se repita, y nunca se
acumula historial. El usuario ve el presente.

`PUT /api/config` valida antes de aplicar y devuelve `400` con el mensaje en
español que produce `Configuracion.validar()`. La configuración se guarda en disco
en el mismo momento: un ajuste que se pierde al cerrar es un ajuste que el usuario
tiene que rehacer cada vez.

- [ ] **Step 1: Añadir `httpx` a las dependencias de desarrollo**

En `pyproject.toml`, sustituir la línea de `dev` por:

```toml
dev = ["pytest>=8.0", "soundfile>=0.12", "httpx>=0.27"]
```

Luego: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 2: Escribir la prueba que falla**

```python
# tests/test_app.py
import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.app import crear_app
from servidor.configuracion import Configuracion
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000


class CapturaFalsa:
    def __init__(self, **kwargs):
        self.ultimo_error = None
        self.latencia_ms = 12.0

    def iniciar(self) -> bool:
        return True

    def detener(self) -> None:
        pass

    def leer_ventana(self, n: int):
        t = np.arange(n) / FS
        return (0.3 * np.sin(2 * np.pi * 82.41 * t)).astype(np.float32)


@pytest.fixture
def cliente(tmp_path):
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    app = crear_app(sesion)
    app.state.ruta_config = tmp_path / "config.json"
    with TestClient(app) as cliente:
        yield cliente
    sesion.detener()


def test_lista_los_modulos_para_que_la_interfaz_los_descubra(cliente):
    modulos = cliente.get("/api/modulos").json()
    assert any(modulo["clave"] == "afinador" for modulo in modulos)


def test_lista_los_perfiles_de_afinacion(cliente):
    perfiles = cliente.get("/api/perfiles").json()
    claves = {perfil["clave"] for perfil in perfiles}
    assert {"guitarra_estandar", "bajo_5"} <= claves
    guitarra = next(p for p in perfiles if p["clave"] == "guitarra_estandar")
    assert len(guitarra["cuerdas"]) == 6
    assert guitarra["cuerdas"][0]["nota"] == "E2"


def test_lista_los_dispositivos_de_entrada(cliente):
    dispositivos = cliente.get("/api/dispositivos").json()
    assert dispositivos[0]["nombre"] == NOMBRE_ROCKSMITH


def test_el_diagnostico_responde_ok_con_el_cable(cliente):
    assert cliente.get("/api/diagnostico").json()["estado"] == "ok"


def test_devuelve_la_configuracion_actual(cliente):
    assert cliente.get("/api/config").json()["perfil"] == "guitarra_estandar"


def test_cambiar_la_configuracion_la_aplica_y_la_guarda(cliente):
    respuesta = cliente.put("/api/config", json={"dispositivo": 3, "perfil": "bajo_4"})
    assert respuesta.status_code == 200
    assert cliente.get("/api/config").json()["perfil"] == "bajo_4"


def test_una_configuracion_invalida_da_400_con_mensaje_en_espanol(cliente):
    respuesta = cliente.put("/api/config", json={"perfil": "ukelele"})
    assert respuesta.status_code == 400
    assert "perfil" in respuesta.json()["detail"]


def test_la_calibracion_devuelve_un_umbral_sugerido(cliente):
    datos = cliente.post("/api/calibrar", json={"segundos": 0.2}).json()
    assert "umbral_sugerido" in datos


def test_el_websocket_emite_el_resultado_del_analisis(cliente):
    with cliente.websocket_connect("/ws/notas") as socket:
        for _ in range(20):
            mensaje = socket.receive_json()
            if mensaje["estado"] == "nota":
                assert mensaje["nota"] == "E2"
                assert set(mensaje) >= {
                    "estado", "frecuencia", "nota", "cents", "confianza",
                    "nivel_db", "posiciones", "cuerda_objetivo", "afinada", "latencia_ms",
                }
                return
    pytest.fail("El WebSocket no emitió ninguna nota en 20 mensajes")
```

- [ ] **Step 3: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_app.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'servidor.app'`

- [ ] **Step 4: Implementar `servidor/app.py`**

```python
"""Servidor FastAPI: expone la sesión a la interfaz.

Capa fina. No calcula nada musical: solo publica lo que la sesión ya produce.
"""

import asyncio
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from nucleo.afinaciones import PERFILES
from servidor import configuracion as config_modulo
from servidor.modulos import listar_modulos
from servidor.sesion import Sesion

# La pantalla no muestra más rápido que esto. Emitir más solo añadiría cola y, con
# ella, retardo entre lo que se toca y lo que se ve.
FRECUENCIA_EMISION = 30.0


def crear_app(sesion: Sesion, ruta_interfaz: Path | None = None) -> FastAPI:
    """Construye la aplicación alrededor de una sesión ya creada."""
    app = FastAPI(title="proyecto_musica")
    app.state.sesion = sesion
    app.state.ruta_config = config_modulo.RUTA_POR_DEFECTO

    @app.get("/api/modulos")
    def leer_modulos() -> list[dict]:
        """Módulos disponibles. La interfaz los descubre aquí, no los tiene escritos."""
        return [modulo.a_dict() for modulo in listar_modulos()]

    @app.get("/api/perfiles")
    def leer_perfiles() -> list[dict]:
        """Perfiles de afinación con sus cuerdas, para dibujar el mástil."""
        return [
            {
                "clave": clave,
                "nombre": perfil.nombre,
                "trastes": perfil.trastes,
                "cuerdas": [
                    {"numero": c.numero, "nota": c.nota, "frecuencia": c.frecuencia}
                    for c in perfil.cuerdas
                ],
            }
            for clave, perfil in PERFILES.items()
        ]

    @app.get("/api/dispositivos")
    def leer_dispositivos() -> list[dict]:
        """Entradas de audio del sistema, para que el usuario elija a mano."""
        return sesion.diagnostico().a_dict()["dispositivos"]

    @app.get("/api/diagnostico")
    def leer_diagnostico() -> dict:
        """Estado del montaje: permiso, dispositivo, señal."""
        ultimo = sesion.ultimo_resultado()
        nivel = ultimo.nivel_db if ultimo is not None else None
        return sesion.diagnostico(nivel).a_dict()

    @app.get("/api/config")
    def leer_config() -> dict:
        return sesion.configuracion.a_dict()

    @app.put("/api/config")
    def escribir_config(datos: dict = Body(...)) -> dict:
        """Aplica y persiste la configuración. Valida antes de tocar nada."""
        nueva = config_modulo.Configuracion.desde_dict(
            {**sesion.configuracion.a_dict(), **datos}
        )
        try:
            sesion.aplicar(nueva)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        config_modulo.guardar(nueva, app.state.ruta_config)
        return nueva.a_dict()

    @app.post("/api/calibrar")
    def calibrar(datos: dict = Body(default={})) -> dict:
        """Mide el piso de ruido y sugiere un umbral, sin aplicarlo.

        Devolver el valor en vez de imponerlo deja la decisión en el usuario.
        """
        segundos = float(datos.get("segundos", 2.0))
        return {"umbral_sugerido": round(sesion.calibrar(segundos), 1)}

    @app.websocket("/ws/notas")
    async def emitir_notas(websocket: WebSocket) -> None:
        """Emite el último resultado a 30 Hz fijos.

        Siempre el presente, aunque se repita. Nunca una cola de resultados viejos.
        """
        await websocket.accept()
        intervalo = 1.0 / FRECUENCIA_EMISION
        try:
            while True:
                resultado = sesion.ultimo_resultado()
                if resultado is None:
                    mensaje = {
                        "estado": "silencio",
                        "frecuencia": 0.0,
                        "nota": None,
                        "cents": None,
                        "confianza": 0.0,
                        "nivel_db": -120.0,
                        "posiciones": [],
                        "cuerda_objetivo": None,
                        "afinada": False,
                    }
                else:
                    mensaje = resultado.a_dict()
                mensaje["latencia_ms"] = round(sesion.latencia_ms, 1)
                await websocket.send_json(mensaje)
                await asyncio.sleep(intervalo)
        except WebSocketDisconnect:
            return

    if ruta_interfaz is not None and ruta_interfaz.exists():
        app.mount("/", StaticFiles(directory=ruta_interfaz, html=True), name="interfaz")

    return app
```

- [ ] **Step 5: Ejecutar las pruebas y verificar que pasan**

Run: `.venv/bin/pytest tests/test_app.py -v`
Esperado: PASS, 9 pruebas.

- [ ] **Step 6: Commit**

```bash
git add servidor/app.py pyproject.toml tests/test_app.py
git commit -m "feat: servidor FastAPI con emisión de notas por WebSocket"
```

---

### Task 11: Armazón de la interfaz y conexión con el servidor

**Files:**
- Create: `interfaz/package.json`
- Create: `interfaz/vite.config.ts`
- Create: `interfaz/index.html`
- Create: `interfaz/src/main.tsx`
- Create: `interfaz/src/tipos.ts`
- Create: `interfaz/src/useNotas.ts`
- Create: `interfaz/src/App.tsx`
- Test: `interfaz/src/useNotas.test.ts`

Nota: `App.tsx` importa `./estilos.css` y `./Afinador`, que se crean en la Task 12.
Las pruebas de esta tarea (`useNotas`) no dependen de ninguno de los dos; la
interfaz no compila entera hasta terminar la Task 12.

**Interfaces:**
- Consumes: los endpoints de la Task 10
- Produces:
  - `tipos.ts`: `Posicion`, `MensajeNota`, `Modulo`, `PerfilAfinacion`, `Diagnostico`
  - `useNotas.ts`: `useNotas(url?: string)` → `{ nota: MensajeNota | null, conectado: boolean }`
  - `App.tsx`: armazón que lista los módulos del servidor y monta el activo

**Contexto para quien implementa.** La interfaz **no calcula nada musical**. Si en
algún momento aparece aquí una fórmula de cents o una tabla de notas, es señal de
que el núcleo dejó algo sin resolver y hay que moverlo allí.

El armazón lista los módulos que devuelve `/api/modulos` en vez de tenerlos escritos
a mano. En la etapa 1 solo hay uno, así que parece un rodeo; existe precisamente
para que añadir ejercicios o canciones en las etapas siguientes sea registrar un
módulo en el servidor y escribir su componente, sin tocar el armazón.

El hook `useNotas` se reconecta solo. Desconectar el cable es algo que pasa a
menudo, y obligar a recargar la página sería un castigo desproporcionado.

`vite.config.ts` redirige `/api` y `/ws` al servidor Python en el puerto 8000, para
que en desarrollo la interfaz recargue en caliente mientras habla con el backend
real.

- [ ] **Step 1: Crear el proyecto con pnpm**

```bash
cd /Users/giocrisraigodoy/Documents/proyecto_musica
pnpm create vite interfaz --template react-ts
cd interfaz
pnpm install
pnpm add -D vitest jsdom @testing-library/react @testing-library/jest-dom
```

- [ ] **Step 2: Configurar `interfaz/vite.config.ts`**

```typescript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  build: { outDir: "dist" },
  test: { environment: "jsdom", globals: true },
});
```

En `interfaz/package.json`, añadir a `scripts`: `"test": "vitest run"`.

- [ ] **Step 3: Escribir `interfaz/src/tipos.ts`**

```typescript
/** Formas exactas que llegan del servidor. Espejo de los dataclasses de Python. */

export interface Posicion {
  cuerda: number;
  traste: number;
}

export interface MensajeNota {
  estado: "nota" | "silencio" | "error";
  frecuencia: number;
  nota: string | null;
  cents: number | null;
  confianza: number;
  nivel_db: number;
  posiciones: Posicion[];
  cuerda_objetivo: number | null;
  afinada: boolean;
  latencia_ms?: number;
}

export interface Modulo {
  clave: string;
  nombre: string;
  descripcion: string;
  icono: string;
  disponible: boolean;
}

export interface Cuerda {
  numero: number;
  nota: string;
  frecuencia: number;
}

export interface PerfilAfinacion {
  clave: string;
  nombre: string;
  trastes: number;
  cuerdas: Cuerda[];
}

export interface Diagnostico {
  estado: "ok" | "sin_permiso" | "sin_dispositivo" | "sin_senal";
  mensaje: string;
  accion: string;
  dispositivos: { indice: number; nombre: string }[];
}
```

- [ ] **Step 4: Escribir la prueba que falla**

```typescript
// interfaz/src/useNotas.test.ts
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useNotas } from "./useNotas";

class WebSocketFalso {
  static ultimo: WebSocketFalso | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((evento: { data: string }) => void) | null = null;
  cerrado = false;

  constructor(public url: string) {
    WebSocketFalso.ultimo = this;
  }

  close() {
    this.cerrado = true;
    this.onclose?.();
  }

  abrir() {
    this.onopen?.();
  }

  enviar(datos: unknown) {
    this.onmessage?.({ data: JSON.stringify(datos) });
  }
}

describe("useNotas", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("empieza desconectado y sin nota", () => {
    const { result } = renderHook(() => useNotas());
    expect(result.current.conectado).toBe(false);
    expect(result.current.nota).toBeNull();
  });

  it("se marca conectado al abrirse el socket", () => {
    const { result } = renderHook(() => useNotas());
    act(() => WebSocketFalso.ultimo!.abrir());
    expect(result.current.conectado).toBe(true);
  });

  it("expone el último mensaje recibido", () => {
    const { result } = renderHook(() => useNotas());
    act(() => {
      WebSocketFalso.ultimo!.abrir();
      WebSocketFalso.ultimo!.enviar({ estado: "nota", nota: "E2", cents: -3 });
    });
    expect(result.current.nota?.nota).toBe("E2");
  });

  it("se reconecta solo tras una caída", () => {
    renderHook(() => useNotas());
    const primero = WebSocketFalso.ultimo;
    act(() => {
      primero!.abrir();
      primero!.onclose?.();
      vi.advanceTimersByTime(1500);
    });
    expect(WebSocketFalso.ultimo).not.toBe(primero);
  });

  it("ignora un mensaje que no sea JSON válido", () => {
    const { result } = renderHook(() => useNotas());
    act(() => {
      WebSocketFalso.ultimo!.abrir();
      WebSocketFalso.ultimo!.onmessage?.({ data: "{roto" });
    });
    expect(result.current.nota).toBeNull();
  });
});
```

- [ ] **Step 5: Ejecutar la prueba y verificar que falla**

Run: `cd interfaz && pnpm test`
Esperado: FAIL, no existe `./useNotas`

- [ ] **Step 6: Escribir `interfaz/src/useNotas.ts`**

```typescript
import { useEffect, useRef, useState } from "react";

import type { MensajeNota } from "./tipos";

/** Espera antes de reintentar la conexión. Desconectar el cable es habitual. */
const ESPERA_RECONEXION_MS = 1000;

/**
 * Suscripción al flujo de notas del servidor.
 *
 * Se reconecta sola: obligar a recargar la página cada vez que se desconecta el
 * cable sería un castigo desproporcionado.
 */
export function useNotas(url = `ws://${window.location.host}/ws/notas`) {
  const [nota, setNota] = useState<MensajeNota | null>(null);
  const [conectado, setConectado] = useState(false);
  const temporizador = useRef<number | null>(null);

  useEffect(() => {
    let vivo = true;
    let socket: WebSocket | null = null;

    const conectar = () => {
      if (!vivo) return;
      socket = new WebSocket(url);

      socket.onopen = () => setConectado(true);

      socket.onmessage = (evento) => {
        try {
          setNota(JSON.parse(evento.data) as MensajeNota);
        } catch {
          // Un mensaje corrupto se descarta; el siguiente llega en 33 ms.
        }
      };

      socket.onclose = () => {
        setConectado(false);
        if (vivo) {
          temporizador.current = window.setTimeout(conectar, ESPERA_RECONEXION_MS);
        }
      };
    };

    conectar();

    return () => {
      vivo = false;
      if (temporizador.current !== null) window.clearTimeout(temporizador.current);
      socket?.close();
    };
  }, [url]);

  return { nota, conectado };
}
```

- [ ] **Step 7: Escribir `interfaz/src/App.tsx`**

```tsx
import { useEffect, useState } from "react";

import { Afinador } from "./Afinador";
import "./estilos.css";
import type { Diagnostico, Modulo } from "./tipos";

/**
 * Armazón de la aplicación.
 *
 * Los módulos se leen del servidor en lugar de estar escritos aquí: añadir
 * ejercicios o canciones en las etapas siguientes será registrar un módulo en el
 * servidor y escribir su componente, sin tocar este archivo.
 */
export function App() {
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [activo, setActivo] = useState("afinador");
  const [diagnostico, setDiagnostico] = useState<Diagnostico | null>(null);

  useEffect(() => {
    fetch("/api/modulos").then((r) => r.json()).then(setModulos);
  }, []);

  useEffect(() => {
    const revisar = () =>
      fetch("/api/diagnostico").then((r) => r.json()).then(setDiagnostico);
    revisar();
    const intervalo = window.setInterval(revisar, 3000);
    return () => window.clearInterval(intervalo);
  }, []);

  const problema = diagnostico !== null && diagnostico.estado !== "ok";

  return (
    <div className="aplicacion">
      <header className="cabecera">
        <span className="titulo">proyecto_musica</span>
        <nav className="modulos">
          {modulos.map((modulo) => (
            <button
              key={modulo.clave}
              className={modulo.clave === activo ? "modulo activo" : "modulo"}
              disabled={!modulo.disponible}
              title={modulo.descripcion}
              onClick={() => setActivo(modulo.clave)}
            >
              {modulo.icono} {modulo.nombre}
            </button>
          ))}
        </nav>
      </header>

      {problema && (
        <div className="aviso">
          <strong>{diagnostico!.mensaje}</strong>
          <p>{diagnostico!.accion}</p>
        </div>
      )}

      <main>{activo === "afinador" && <Afinador />}</main>
    </div>
  );
}
```

`interfaz/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

`interfaz/index.html`:

```html
<!doctype html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>proyecto_musica</title>
  </head>
  <body>
    <div id="raiz"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 8: Ejecutar las pruebas y verificar que pasan**

Run: `cd interfaz && pnpm test`
Esperado: PASS, 5 pruebas. `App.tsx` todavía no compila porque falta `Afinador`,
que es la Task 12; las pruebas de `useNotas` no dependen de él.

- [ ] **Step 9: Commit**

```bash
git add interfaz/ -- ':!interfaz/node_modules'
git commit -m "feat: armazón de la interfaz y conexión por WebSocket"
```

---

### Task 12: Afinador, mástil y barra de estado

**Files:**
- Create: `interfaz/src/presentacion.ts`
- Create: `interfaz/src/Aguja.tsx`
- Create: `interfaz/src/Mastil.tsx`
- Create: `interfaz/src/BarraEstado.tsx`
- Create: `interfaz/src/Afinador.tsx`
- Create: `interfaz/src/estilos.css`
- Test: `interfaz/src/presentacion.test.ts`

**Interfaces:**
- Consumes: `useNotas`, `tipos.ts`, `GET /api/perfiles`, `GET /api/config`
- Produces:
  - `presentacion.ts`: `posicionAguja(cents: number, maximo?: number): number`, `estadoAfinacion(cents: number | null, tolerancia?: number): "afinada" | "grave" | "aguda" | "sin_nota"`, `fraccionNivel(nivelDb: number, minimo?: number, maximo?: number): number`
  - Componentes `Aguja`, `Mastil`, `BarraEstado`, `Afinador`

**Contexto para quien implementa.** Esta tarea produce la pantalla que el usuario
eligió: panel único con todo visible a la vez, pensado para tener el Mac al lado
mientras se toca.

Las tres funciones de `presentacion.ts` son puras y por eso son las que llevan
prueba. El resto de los componentes solo colocan lo que ellas devuelven; probar el
renderizado de un SVG daría poca información a cambio de mucha fragilidad.

Dos detalles de presentación que importan más de lo que parecen:

**La aguja se satura, no se sale.** Fuera de ±50 cents ya no estás afinando esa
nota, estás en otra; la aguja se queda en el extremo en vez de dispararse fuera de
la pantalla.

**El mástil resalta todas las posiciones que devuelve el servidor**, no una. Un La
de 110 Hz es tanto la 5ª al aire como la 6ª en el traste 5, y desde la frecuencia no
hay forma de distinguirlas. Mostrar una sola sería fingir una certeza inexistente.

- [ ] **Step 1: Escribir la prueba que falla**

```typescript
// interfaz/src/presentacion.test.ts
import { describe, expect, it } from "vitest";

import { estadoAfinacion, fraccionNivel, posicionAguja } from "./presentacion";

describe("posicionAguja", () => {
  it("centra la aguja cuando la nota está exacta", () => {
    expect(posicionAguja(0)).toBe(0);
  });

  it("va a los extremos en los límites del rango", () => {
    expect(posicionAguja(50)).toBeCloseTo(1);
    expect(posicionAguja(-50)).toBeCloseTo(-1);
  });

  it("se satura en vez de salirse de la pantalla", () => {
    expect(posicionAguja(300)).toBe(1);
    expect(posicionAguja(-300)).toBe(-1);
  });

  it("es proporcional dentro del rango", () => {
    expect(posicionAguja(25)).toBeCloseTo(0.5);
  });
});

describe("estadoAfinacion", () => {
  it("marca afinada dentro de la tolerancia", () => {
    expect(estadoAfinacion(0)).toBe("afinada");
    expect(estadoAfinacion(4.9)).toBe("afinada");
  });

  it("distingue grave de aguda", () => {
    expect(estadoAfinacion(-20)).toBe("grave");
    expect(estadoAfinacion(20)).toBe("aguda");
  });

  it("sin nota no dice nada", () => {
    expect(estadoAfinacion(null)).toBe("sin_nota");
  });
});

describe("fraccionNivel", () => {
  it("el silencio da cero", () => {
    expect(fraccionNivel(-120)).toBe(0);
  });

  it("una señal fuerte llena la barra", () => {
    expect(fraccionNivel(-5)).toBe(1);
  });

  it("el nivel medido tocando queda a media barra", () => {
    // -45 dBFS fue el nivel medio medido en el equipo real
    const fraccion = fraccionNivel(-45);
    expect(fraccion).toBeGreaterThan(0.4);
    expect(fraccion).toBeLessThan(0.6);
  });
});
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `cd interfaz && pnpm test`
Esperado: FAIL, no existe `./presentacion`

- [ ] **Step 3: Escribir `interfaz/src/presentacion.ts`**

```typescript
/** Traducciones de datos a posiciones en pantalla. Funciones puras. */

/** Desviación, en cents, que corresponde a cada extremo de la aguja. */
const RANGO_AGUJA_CENTS = 50;

/** Rango de nivel que cubre la barra, en dBFS. */
const NIVEL_MINIMO_DB = -80;
const NIVEL_MAXIMO_DB = -10;

/**
 * Posición de la aguja entre -1 (grave) y 1 (aguda).
 *
 * Se satura en los extremos a propósito: pasados 50 cents ya no estás afinando esa
 * nota sino otra, y una aguja que se dispara fuera de la pantalla no informa de nada.
 */
export function posicionAguja(cents: number, maximo = RANGO_AGUJA_CENTS): number {
  return Math.max(-1, Math.min(1, cents / maximo));
}

/** Estado legible de la afinación, para elegir color y texto. */
export function estadoAfinacion(
  cents: number | null,
  tolerancia = 5
): "afinada" | "grave" | "aguda" | "sin_nota" {
  if (cents === null) return "sin_nota";
  if (Math.abs(cents) < tolerancia) return "afinada";
  return cents < 0 ? "grave" : "aguda";
}

/** Fracción de la barra de nivel, entre 0 y 1. */
export function fraccionNivel(
  nivelDb: number,
  minimo = NIVEL_MINIMO_DB,
  maximo = NIVEL_MAXIMO_DB
): number {
  const fraccion = (nivelDb - minimo) / (maximo - minimo);
  return Math.max(0, Math.min(1, fraccion));
}
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `cd interfaz && pnpm test`
Esperado: PASS, 15 pruebas (5 de `useNotas` y 10 de `presentacion`).

- [ ] **Step 5: Escribir `interfaz/src/Aguja.tsx`**

```tsx
import { estadoAfinacion, posicionAguja } from "./presentacion";

interface Props {
  nota: string | null;
  cents: number | null;
}

/** Aguja de afinación: bemol a la izquierda, sostenido a la derecha. */
export function Aguja({ nota, cents }: Props) {
  const estado = estadoAfinacion(cents);
  const desplazamiento = cents === null ? 0 : posicionAguja(cents) * 50;

  return (
    <section className={`aguja ${estado}`}>
      <div className="nota-grande">{nota ?? "—"}</div>
      <div className="escala">
        <span className="signo">♭</span>
        <div className="pista">
          <div className="centro" />
          <div className="marcador" style={{ left: `${50 + desplazamiento}%` }} />
        </div>
        <span className="signo">♯</span>
      </div>
      <div className="lectura">
        {cents === null ? "sin señal" : `${cents > 0 ? "+" : ""}${cents.toFixed(1)} cents`}
      </div>
      <div className="veredicto">
        {estado === "afinada" && "✔ AFINADA"}
        {estado === "grave" && "▼ grave"}
        {estado === "aguda" && "▲ aguda"}
      </div>
    </section>
  );
}
```

- [ ] **Step 6: Escribir `interfaz/src/Mastil.tsx`**

```tsx
import type { PerfilAfinacion, Posicion } from "./tipos";

interface Props {
  perfil: PerfilAfinacion;
  posiciones: Posicion[];
  trastesVisibles?: number;
}

const TRASTES_CON_MARCA = [3, 5, 7, 9, 12, 15, 17, 19, 21];

/**
 * Mástil con las posiciones detectadas resaltadas.
 *
 * Se resaltan TODAS las posiciones que devuelve el servidor, no una. Un La de
 * 110 Hz es tanto la 5ª cuerda al aire como la 6ª en el traste 5; desde la
 * frecuencia no se pueden distinguir y elegir una sería inventar certeza.
 */
export function Mastil({ perfil, posiciones, trastesVisibles = 12 }: Props) {
  const activa = (cuerda: number, traste: number) =>
    posiciones.some((p) => p.cuerda === cuerda && p.traste === traste);

  return (
    <section className="mastil">
      {perfil.cuerdas.map((cuerda) => (
        <div className="cuerda" key={cuerda.numero}>
          <span className="etiqueta">{cuerda.nota.replace(/\d/g, "")}</span>
          {Array.from({ length: trastesVisibles + 1 }, (_, traste) => (
            <span
              key={traste}
              className={
                "traste" +
                (activa(cuerda.numero, traste) ? " activo" : "") +
                (traste === 0 ? " al-aire" : "")
              }
            />
          ))}
        </div>
      ))}
      <div className="numeros">
        {Array.from({ length: trastesVisibles + 1 }, (_, traste) => (
          <span key={traste} className="numero">
            {TRASTES_CON_MARCA.includes(traste) ? traste : ""}
          </span>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 7: Escribir `interfaz/src/BarraEstado.tsx`**

```tsx
import { fraccionNivel } from "./presentacion";

interface Props {
  nivelDb: number;
  frecuencia: number;
  latenciaMs: number;
  conectado: boolean;
}

/** Franja inferior: nivel de entrada, frecuencia, latencia y estado del cable. */
export function BarraEstado({ nivelDb, frecuencia, latenciaMs, conectado }: Props) {
  return (
    <footer className="barra-estado">
      <div className="nivel">
        <span>nivel</span>
        <div className="medidor">
          <div className="relleno" style={{ width: `${fraccionNivel(nivelDb) * 100}%` }} />
        </div>
        <span className="dbfs">{nivelDb.toFixed(0)} dBFS</span>
      </div>
      <span>{frecuencia > 0 ? `${frecuencia.toFixed(1)} Hz` : "— Hz"}</span>
      <span>latencia {latenciaMs.toFixed(0)} ms</span>
      <span className={conectado ? "conectado" : "desconectado"}>
        {conectado ? "● conectado" : "○ sin conexión"}
      </span>
    </footer>
  );
}
```

- [ ] **Step 8: Escribir `interfaz/src/Afinador.tsx`**

```tsx
import { useEffect, useState } from "react";

import { Aguja } from "./Aguja";
import { BarraEstado } from "./BarraEstado";
import { Mastil } from "./Mastil";
import type { PerfilAfinacion } from "./tipos";
import { useNotas } from "./useNotas";

/** Módulo afinador: panel único con aguja, mástil y estado a la vista. */
export function Afinador() {
  const { nota, conectado } = useNotas();
  const [perfiles, setPerfiles] = useState<PerfilAfinacion[]>([]);
  const [clavePerfil, setClavePerfil] = useState("guitarra_estandar");

  useEffect(() => {
    fetch("/api/perfiles").then((r) => r.json()).then(setPerfiles);
    fetch("/api/config")
      .then((r) => r.json())
      .then((config) => setClavePerfil(config.perfil));
  }, []);

  const cambiarPerfil = (clave: string) => {
    setClavePerfil(clave);
    fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ perfil: clave }),
    });
  };

  const perfil = perfiles.find((p) => p.clave === clavePerfil);

  return (
    <div className="afinador">
      <div className="selector">
        <label htmlFor="perfil">Afinación</label>
        <select
          id="perfil"
          value={clavePerfil}
          onChange={(evento) => cambiarPerfil(evento.target.value)}
        >
          {perfiles.map((opcion) => (
            <option key={opcion.clave} value={opcion.clave}>
              {opcion.nombre}
            </option>
          ))}
        </select>
      </div>

      <Aguja nota={nota?.nota ?? null} cents={nota?.cents ?? null} />

      {perfil && <Mastil perfil={perfil} posiciones={nota?.posiciones ?? []} />}

      <BarraEstado
        nivelDb={nota?.nivel_db ?? -120}
        frecuencia={nota?.frecuencia ?? 0}
        latenciaMs={nota?.latencia_ms ?? 0}
        conectado={conectado}
      />
    </div>
  );
}
```

- [ ] **Step 9: Escribir `interfaz/src/estilos.css`**

```css
:root {
  --fondo: #14161a;
  --panel: #1d2026;
  --texto: #e6e8eb;
  --tenue: #7d848f;
  --afinada: #34d17a;
  --desviada: #e8a33d;
  --borde: #2b2f37;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--fondo);
  color: var(--texto);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
}

.aplicacion { max-width: 960px; margin: 0 auto; padding: 16px; }

.cabecera {
  display: flex; align-items: center; gap: 16px;
  padding-bottom: 12px; border-bottom: 1px solid var(--borde);
}
.titulo { font-weight: 600; letter-spacing: 0.02em; }
.modulos { display: flex; gap: 8px; }
.modulo {
  background: var(--panel); color: var(--texto); border: 1px solid var(--borde);
  border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 14px;
}
.modulo.activo { border-color: var(--afinada); }
.modulo:disabled { opacity: 0.4; cursor: not-allowed; }

.aviso {
  margin-top: 16px; padding: 12px 16px; border-radius: 8px;
  background: #3a2a1a; border: 1px solid var(--desviada);
}
.aviso p { margin: 6px 0 0; color: var(--tenue); font-size: 14px; }

.selector { margin: 16px 0; display: flex; gap: 8px; align-items: center; }
.selector select {
  background: var(--panel); color: var(--texto);
  border: 1px solid var(--borde); border-radius: 6px; padding: 6px 10px;
}

.aguja { text-align: center; padding: 24px 0; }
.nota-grande { font-size: 72px; font-weight: 300; line-height: 1; }
.aguja.afinada .nota-grande { color: var(--afinada); }
.aguja.grave .nota-grande, .aguja.aguda .nota-grande { color: var(--desviada); }

.escala { display: flex; align-items: center; gap: 12px; margin: 16px 0 8px; }
.signo { color: var(--tenue); font-size: 20px; }
.pista {
  position: relative; flex: 1; height: 8px;
  background: var(--panel); border-radius: 4px;
}
.centro {
  position: absolute; left: 50%; top: -6px; width: 2px; height: 20px;
  background: var(--tenue); transform: translateX(-50%);
}
.marcador {
  position: absolute; top: -8px; width: 4px; height: 24px; border-radius: 2px;
  background: var(--desviada); transform: translateX(-50%); transition: left 80ms linear;
}
.aguja.afinada .marcador { background: var(--afinada); }
.lectura { color: var(--tenue); font-variant-numeric: tabular-nums; }
.veredicto { margin-top: 8px; font-weight: 600; }

.mastil { margin: 24px 0; }
.cuerda { display: flex; align-items: center; gap: 2px; margin-bottom: 6px; }
.etiqueta { width: 20px; color: var(--tenue); font-size: 13px; }
.traste {
  flex: 1; height: 18px; border-right: 1px solid var(--borde); border-radius: 2px;
}
.traste.al-aire { flex: 0 0 14px; }
.traste.activo { background: var(--afinada); }
.numeros { display: flex; gap: 2px; padding-left: 22px; }
.numero { flex: 1; text-align: right; color: var(--tenue); font-size: 11px; }

.barra-estado {
  display: flex; align-items: center; gap: 20px;
  padding-top: 12px; border-top: 1px solid var(--borde);
  color: var(--tenue); font-size: 13px; font-variant-numeric: tabular-nums;
}
.nivel { display: flex; align-items: center; gap: 8px; }
.medidor { width: 120px; height: 8px; background: var(--panel); border-radius: 4px; }
.relleno { height: 100%; background: var(--afinada); border-radius: 4px; }
.conectado { color: var(--afinada); }
.desconectado { color: var(--desviada); }
```

- [ ] **Step 10: Compilar la interfaz**

Run: `cd interfaz && pnpm build`
Esperado: compila sin errores de TypeScript y genera `interfaz/dist/`.

- [ ] **Step 11: Commit**

```bash
git add interfaz/src interfaz/package.json interfaz/vite.config.ts interfaz/index.html
git commit -m "feat: afinador con aguja, mástil y barra de estado"
```

---

### Task 13: Arranque, documentación y verificación final

**Files:**
- Create: `servidor/arranque.py`
- Modify: `pyproject.toml` (añadir la sección `[project.scripts]`)
- Create: `README.md`
- Test: `tests/test_arranque.py`

**Interfaces:**
- Consumes: `servidor.app.crear_app`, `servidor.sesion.Sesion`, `servidor.configuracion`
- Produces:
  - `RUTA_INTERFAZ: Path` — apunta a `interfaz/dist`
  - `construir_aplicacion(ruta_config: Path | None = None) -> tuple[FastAPI, Sesion]`
  - `main(argv: list[str] | None = None) -> int` — punto de entrada del comando `guitarra`

**Contexto para quien implementa.** Esta tarea cierra la etapa: un solo comando que
arranca todo y abre el navegador.

El arranque **no falla si el cable no está conectado**. Levanta el servidor igual y
deja que la interfaz muestre el diagnóstico correspondiente, porque es ahí donde el
usuario puede leer qué hacer. Abortar en la terminal con un error escondería el
mensaje justo donde no lo va a buscar.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_arranque.py
from servidor.arranque import RUTA_INTERFAZ, construir_aplicacion


def test_la_aplicacion_se_construye_sin_hardware(tmp_path, monkeypatch):
    """Sin cable no se debe abortar: el servidor levanta y la interfaz explica."""
    monkeypatch.setattr("servidor.sesion.listar_dispositivos_entrada", lambda: [])
    app, sesion = construir_aplicacion(ruta_config=tmp_path / "config.json")
    assert app is not None
    assert sesion.activa is False
    sesion.detener()


def test_la_ruta_de_la_interfaz_apunta_a_dist():
    assert RUTA_INTERFAZ.name == "dist"
    assert RUTA_INTERFAZ.parent.name == "interfaz"


def test_usa_la_configuracion_guardada(tmp_path):
    from servidor.configuracion import Configuracion, guardar

    ruta = tmp_path / "config.json"
    guardar(Configuracion(perfil="bajo_4", ganancia=3.0), ruta)
    _, sesion = construir_aplicacion(ruta_config=ruta)
    assert sesion.configuracion.perfil == "bajo_4"
    assert sesion.configuracion.ganancia == 3.0
    sesion.detener()
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `.venv/bin/pytest tests/test_arranque.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'servidor.arranque'`

- [ ] **Step 3: Implementar `servidor/arranque.py`**

```python
"""Punto de entrada: levanta el servidor y abre la interfaz en el navegador."""

import argparse
import sys
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI

from servidor import configuracion as config_modulo
from servidor.app import crear_app
from servidor.sesion import Sesion

RUTA_INTERFAZ = Path(__file__).resolve().parent.parent / "interfaz" / "dist"

PUERTO_POR_DEFECTO = 8000


def construir_aplicacion(ruta_config: Path | None = None) -> tuple[FastAPI, Sesion]:
    """Crea la sesión y la aplicación.

    No falla si el cable no está conectado: el servidor levanta igual y la interfaz
    muestra el diagnóstico. Abortar aquí escondería el mensaje en la terminal, que
    es donde el usuario no lo va a buscar.
    """
    ruta = ruta_config or config_modulo.RUTA_POR_DEFECTO
    configuracion = config_modulo.cargar(ruta)
    sesion = Sesion(configuracion)
    diagnostico = sesion.iniciar()
    if diagnostico.estado != "ok":
        print(f"Aviso: {diagnostico.mensaje}")
        if diagnostico.accion:
            print(f"  {diagnostico.accion}")

    app = crear_app(sesion, RUTA_INTERFAZ)
    app.state.ruta_config = ruta
    return app, sesion


def main(argv: list[str] | None = None) -> int:
    """Arranca el servidor. Devuelve el código de salida del proceso."""
    analizador = argparse.ArgumentParser(
        prog="guitarra", description="Afinador y monitor de notas por cable Rocksmith"
    )
    analizador.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO)
    analizador.add_argument(
        "--sin-navegador", action="store_true", help="No abrir el navegador al arrancar"
    )
    argumentos = analizador.parse_args(argv)

    if not RUTA_INTERFAZ.exists():
        print("Falta la interfaz compilada.")
        print("Ejecuta:  cd interfaz && pnpm install && pnpm build")
        return 1

    import uvicorn

    app, sesion = construir_aplicacion()
    direccion = f"http://127.0.0.1:{argumentos.puerto}"

    if not argumentos.sin_navegador:
        def abrir() -> None:
            time.sleep(1.0)
            webbrowser.open(direccion)

        threading.Thread(target=abrir, daemon=True).start()

    print(f"Servidor en {direccion}  (Ctrl+C para salir)")
    try:
        uvicorn.run(app, host="127.0.0.1", port=argumentos.puerto, log_level="warning")
    finally:
        sesion.detener()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Añadir el comando a `pyproject.toml`**

```toml
[project.scripts]
guitarra = "servidor.arranque:main"
```

Luego: `.venv/bin/pip install -e ".[dev]"`

- [ ] **Step 5: Ejecutar toda la batería de pruebas**

Run: `.venv/bin/pytest -v && cd interfaz && pnpm test`
Esperado: PASS en ambas. Anotar el número total de pruebas.

- [ ] **Step 6: Escribir `README.md`**

````markdown
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
Para regenerarlas: `.venv/bin/python -m herramientas.grabar_muestras`.

## Estructura

- `nucleo/` — captura de audio, análisis y teoría musical. Python puro, sin
  dependencias del servidor ni de la interfaz.
- `servidor/` — FastAPI: registro de módulos, configuración, diagnóstico y
  emisión por WebSocket.
- `interfaz/` — React + Vite.
- `herramientas/` — utilidades de línea de comandos.
- `docs/superpowers/` — especificación y plan.

## Estado

Etapa 1 completa. Las siguientes, según el diseño:

2. Ejercicios generados con corrección de nota, afinación y tempo
3. Grabación de sesiones y medición de progreso
4. Canciones desde tablatura, entrenamiento de oído y efectos
````

- [ ] **Step 7: Verificación final con hardware** *(requiere el cable conectado)*

```bash
.venv/bin/guitarra
```

Comprobar en el navegador, con la guitarra conectada:

1. La barra inferior muestra `● conectado` y una latencia entre 10 y 30 ms.
2. Al pulsar la 6ª cuerda al aire aparece `E2` y la aguja se centra.
3. Al pulsar la 5ª al aire aparece `A2` y el mástil resalta **dos** posiciones:
   5ª cuerda traste 0 y 6ª cuerda traste 5.
4. Al bajar la afinación de una cuerda, la aguja se va a `▼ grave` y los cents se
   vuelven negativos.
5. Con la guitarra en silencio la nota desaparece; no se queda congelada la última.
6. Al cambiar el selector a "Bajo 4 cuerdas" y recargar, el perfil persiste.
7. Al desconectar el cable, la interfaz muestra el aviso de dispositivo ausente; al
   reconectarlo, vuelve a funcionar sin reiniciar el programa.

- [ ] **Step 8: Commit**

```bash
git add servidor/arranque.py pyproject.toml README.md tests/test_arranque.py
git commit -m "feat: comando de arranque, documentación y verificación de la etapa 1"
```

---

## Verificación de la etapa completa

Al terminar las 13 tareas debe cumplirse todo esto:

| Requisito de la spec | Dónde se cumple |
|---|---|
| Captura en float32 con ganancia digital | Task 6 |
| Dispositivo elegido explícitamente, nunca el por defecto | Tasks 6, 9 |
| Ventana de análisis dependiente del perfil | Tasks 1, 5 |
| Detección monofónica con medida de confianza | Task 4 |
| Detectores intercambiables para la etapa 2 | Task 4 |
| Compuerta de ruido con umbral calibrable | Tasks 3, 8 |
| Suavizado por mediana | Task 5 |
| Cents respecto a una referencia configurable | Task 2 |
| Todas las posiciones del mástil, sin elegir una | Tasks 2, 12 |
| Perfiles de guitarra y bajo | Task 1 |
| Los tres estados de diagnóstico diferenciados | Task 8 |
| Reconexión automática del dispositivo | Tasks 9, 11 |
| Emisión por WebSocket a ~30 Hz sin cola | Task 10 |
| Latencia medida y visible | Tasks 6, 12 |
| Panel único con aguja, mástil y estado | Task 12 |
| Registro de módulos para las etapas siguientes | Task 9 |
| Pruebas sintéticas de frecuencia conocida | Tasks 2, 3, 4, 5 |
| Pruebas con audio real de la guitarra del usuario | Task 7 |
