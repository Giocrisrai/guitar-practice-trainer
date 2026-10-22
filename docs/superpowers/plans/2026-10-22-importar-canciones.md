# Importar canciones (etapa 3b) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que tus canciones —Guitar Pro, MusicXML, MIDI y tablatura ASCII— entren al
carril, con la digitación elegida por coste mínimo y no a ojo.

**Architecture:** Cuatro lectores independientes bajo `nucleo/piezas/`, cada uno en su
archivo y sin conocerse, que producen el `Pieza` que la etapa 3a ya define. Lo que no es
leer va aparte: `digitacion.py` resuelve dónde se toca cada nota con un camino de coste
mínimo, y `afinaciones` gana la capacidad de construir un perfil desde el archivo. La
biblioteca —carpeta, subida, elegir pista— es servidor e interfaz, no núcleo.

**Tech Stack:** Python 3.13.1 con uv, numpy, PyGuitarPro (LGPL-3), music21 (BSD-3),
mido (MIT), FastAPI. React + Vite + TypeScript con pnpm y vitest.

**Spec:** `docs/superpowers/specs/2026-10-22-importar-canciones-design.md`

## Global Constraints

- Python **3.13.1** gestionado con **uv**. Los comandos son `uv run ...`, nunca
  `pip install` ni `.venv/bin/...`. En este entorno hace falta el prefijo
  `UV_CACHE_DIR="$TMPDIR/uv-cache"`, también para `ruff`.
- Gestor de paquetes JavaScript: **pnpm**, nunca npm.
- Comentarios, nombres de variables, funciones y clases **en español**.
- Preferir **numpy/scipy** sobre implementaciones manuales.
- Pruebas con **pytest**. **Ninguna prueba abre el dispositivo de audio real.**
- **Ningún archivo con derechos de autor entra al repositorio.** Las muestras de prueba
  se fabrican con las propias librerías, que escriben además de leer.
- `nucleo/` no importa nada de `servidor/` ni de `interfaz/`.
- `nucleo/piezas/modelo.py` no importa nada de `nucleo/ejercicios/`.
- Lo que decide el núcleo no se recalcula en la interfaz.
- Los commits terminan con:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

## Review Focus

Cinco clases de entrada que la especificación da por supuestas y que ninguna prueba
suya ejercita. Son las que más probablemente muerdan a quien use esto, porque **los
archivos reales las traen todas**. Cada una tiene su prueba en la tarea que posee el
código.

1. **Notas ligadas** (`NoteType.tie` en Guitar Pro, `<tie>` en MusicXML). No son
   ataques nuevos: son la misma nota que sigue sonando. Si entran como notas, el carril
   te pedirá tocar algo que no se toca y lo contará como fallo. **Deben fundirse con la
   nota anterior, alargándola.** → Tarea 4 y Tarea 6.
2. **Silencios** (`NoteType.rest`). No son notas. Si entran, lo hacen sin altura y
   revientan la digitación o producen una nota fantasma. **Deben desaparecer.** → Tarea 4.
3. **Cambios de tempo a mitad de canción.** `Pieza` tiene **un** tempo y la
   especificación no dice qué hacer. Son comunísimos. **Se toma el primero y la pieza se
   marca para que la pantalla lo avise**, porque rechazar la canción entera por un
   cambio de tempo sería peor. → Tarea 1 (el campo) y Tareas 4, 5, 6 (detectarlo).
4. **Pistas que no se pueden tocar**: percusión, pistas sin cuerdas, pistas vacías.
   `Note.string` no significa nada ahí. **Se excluyen del listado de pistas, nombrando
   por qué.** → Tarea 4.
5. **Tablaturas ASCII que no son de seis cuerdas** (un bajo de cuatro, una guitarra de
   siete) **o con líneas de distinta longitud**. **El número de líneas decide el
   instrumento, y las longitudes desiguales se rechazan nombrando la línea.** → Tarea 7.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `nucleo/piezas/modelo.py` | +`Seccion`, +`Pieza.secciones`, +`ritmo_aproximado`, +`tempo_variable` |
| `nucleo/piezas/digitacion.py` | `CosteDigitacion` y el camino de coste mínimo |
| `nucleo/afinaciones.py` | +`perfil_desde_midis`: construir un perfil desde el archivo |
| `nucleo/piezas/desde_guitarpro.py` | Leer `.gp3/.gp4/.gp5/.gpx`, listar pistas, importar una |
| `nucleo/piezas/desde_midi.py` | Leer `.mid`, listar pistas, importar una |
| `nucleo/piezas/desde_musicxml.py` | Leer `.xml/.mxl`, respetar la tablatura si viene |
| `nucleo/piezas/desde_ascii.py` | Parsear la tablatura de texto e inferir el ritmo |
| `nucleo/piezas/lectores.py` | El registro: extensión → lector |
| `servidor/canciones.py` | La carpeta, la subida, el listado |
| `servidor/app.py` | Los cuatro endpoints |
| `interfaz/src/Canciones.tsx` | La pantalla: lista, subir, pistas, aviso de afinación |

---

### Task 1: El modelo crece en tres campos

**Files:**
- Modify: `nucleo/piezas/modelo.py`
- Test: `tests/test_modelo_piezas.py`

**Interfaces:**
- Consumes: `Pieza`, `NotaEnPieza` tal como están hoy.
- Produces: `Seccion(nombre, inicio_pulsos)`;
  `Pieza(..., secciones=(), ritmo_aproximado=False, tempo_variable=False)`;
  `Pieza.seccion_en(pulsos) -> Seccion | None`; los tres campos en `a_dict()`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
def test_una_pieza_sin_secciones_sigue_valiendo():
    """Los ejercicios de la etapa 3a no traen secciones y no deben romperse."""
    p = pieza([nota()])
    assert p.secciones == ()
    assert p.ritmo_aproximado is False
    assert p.tempo_variable is False


def test_las_secciones_vienen_ordenadas():
    with pytest.raises(ValueError, match="orden"):
        Pieza(
            nombre="x", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
            notas=(), secciones=(Seccion("Solo", 8.0), Seccion("Intro", 0.0)),
        )


def test_seccion_en_devuelve_la_que_esta_sonando():
    p = Pieza(
        nombre="x", perfil="guitarra_estandar", tempo=60, compas=(4, 4), notas=(),
        secciones=(Seccion("Intro", 0.0), Seccion("Estribillo", 8.0)),
    )
    assert p.seccion_en(0.0).nombre == "Intro"
    assert p.seccion_en(7.9).nombre == "Intro"
    assert p.seccion_en(8.0).nombre == "Estribillo"
    assert p.seccion_en(100.0).nombre == "Estribillo"


def test_sin_secciones_no_hay_seccion_en_ninguna_parte():
    assert pieza([nota()]).seccion_en(0.0) is None


def test_una_seccion_antes_del_principio_se_rechaza():
    with pytest.raises(ValueError, match="negativ"):
        Pieza(nombre="x", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
              notas=(), secciones=(Seccion("Intro", -1.0),))


def test_a_dict_publica_los_tres_campos_nuevos():
    p = Pieza(
        nombre="x", perfil="guitarra_estandar", tempo=60, compas=(4, 4), notas=(),
        secciones=(Seccion("Intro", 0.0),), ritmo_aproximado=True, tempo_variable=True,
    )
    d = p.a_dict()
    assert d["secciones"] == [{"nombre": "Intro", "inicio_pulsos": 0.0}]
    assert d["ritmo_aproximado"] is True
    assert d["tempo_variable"] is True
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_modelo_piezas.py -q`
Expected: FAIL, `ImportError: cannot import name 'Seccion'`

- [ ] **Step 3: Implementa**

```python
@dataclass(frozen=True)
class Seccion:
    """Un trozo con nombre: "Intro", "Estribillo", "Solo".

    Viene de los marcadores del archivo -Guitar Pro los llama marcadores, MusicXML
    marcas de ensayo, MIDI marcadores de texto-. No se usan todavia: la etapa 3c
    practicara por secciones, y si se tiran al importar no hay forma de
    reconstruirlas despues.
    """

    nombre: str
    inicio_pulsos: float

    def a_dict(self) -> dict:
        return {"nombre": self.nombre, "inicio_pulsos": self.inicio_pulsos}
```

En `Pieza` se añaden los tres campos con valor por defecto —los ejercicios de la
etapa 3a construyen `Pieza` sin ellos y no deben romperse—, la validación de orden y
de inicio no negativo en `__post_init__` junto a la que ya existe para las notas, y:

```python
    def seccion_en(self, pulsos: float) -> Seccion | None:
        """La seccion que esta sonando en ese instante, o None si no hay secciones.

        La ultima cuyo inicio no ha pasado todavia. Una pieza sin secciones devuelve
        None en todas partes, que es lo que ocurre con los ejercicios generados.
        """
```

`ritmo_aproximado` y `tempo_variable` son banderas con su docstring: la primera dice
que el ritmo se infirió de una tablatura de texto y no es de fiar; la segunda, que la
canción cambiaba de tempo y se tomó el primero.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, 486 + 6 = 492 passed / 30 skipped.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/modelo.py tests/test_modelo_piezas.py
git commit -m "feat: secciones y banderas de procedencia en Pieza"
```

---

### Task 2: La digitación por coste mínimo

**Files:**
- Create: `nucleo/piezas/digitacion.py`
- Test: `tests/test_digitacion.py`

**Interfaces:**
- Consumes: `PerfilAfinacion` y `PERFILES` de `nucleo/afinaciones.py`;
  `Posicion(cuerda, traste)` de `nucleo/musica.py`;
  `posiciones_en_mastil(midi, perfil) -> tuple[Posicion, ...]` de `nucleo/musica.py`.
- Produces: `CosteDigitacion(por_traste, por_cuerda, al_aire, estiramiento_maximo)`;
  `digitar(midis, perfil, coste=CosteDigitacion()) -> tuple[Posicion, ...]`;
  `coste_total(posiciones, coste) -> float`.

Este es el corazón matemático de la etapa. Cada nota vive en hasta seis sitios del
mástil; hay que elegir uno por nota minimizando el movimiento de la mano **en toda la
pieza**. Es un camino de coste mínimo sobre un grafo por capas, y se resuelve por
programación dinámica en `O(n·k²)` con `k ≤ 6`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.musica import Posicion
from nucleo.piezas.digitacion import CosteDigitacion, coste_total, digitar

GUITARRA = PERFILES["guitarra_estandar"]


def test_una_nota_sola_toma_la_posicion_mas_comoda():
    """Sin nada alrededor, gana la cuerda al aire: cuesta cero."""
    posiciones = digitar([40], GUITARRA)
    assert posiciones == (Posicion(cuerda=6, traste=0),)


def test_una_escala_en_una_posicion_no_salta_por_el_mastil():
    midis = [48, 50, 52, 53, 55, 57, 59, 60]
    trastes = [p.traste for p in digitar(midis, GUITARRA) if p.traste > 0]
    assert max(trastes) - min(trastes) <= 4


def test_el_minimo_nunca_es_peor_que_la_heuristica_de_cercania():
    """La propiedad que de verdad vigila: comparamos contra lo que ya existe.

    `digitar` devuelve un minimo, asi que su coste tiene que ser menor o igual que el
    de cualquier otra eleccion sobre las MISMAS posiciones y con la MISMA funcion de
    coste. Si alguna vez falla, el algoritmo esta mal.
    """
    from nucleo.piezas.desde_ejercicio import elegir_posicion
    from nucleo.musica import posiciones_en_mastil

    coste = CosteDigitacion()
    generador = np.random.default_rng(7)
    for _ in range(50):
        midis = [int(m) for m in generador.integers(40, 76, size=20)]
        optimo = digitar(midis, GUITARRA, coste)

        cercanas = []
        anterior = None
        for midi in midis:
            elegida = elegir_posicion(posiciones_en_mastil(midi, GUITARRA), anterior)
            cercanas.append(elegida)
            anterior = elegida.traste

        assert coste_total(optimo, coste) <= coste_total(tuple(cercanas), coste) + 1e-9


def test_ninguna_posicion_cae_fuera_del_mastil():
    generador = np.random.default_rng(11)
    midis = [int(m) for m in generador.integers(40, 76, size=40)]
    for p in digitar(midis, GUITARRA):
        assert 1 <= p.cuerda <= len(GUITARRA.cuerdas)
        assert 0 <= p.traste <= GUITARRA.trastes


def test_ningun_salto_supera_el_estiramiento_permitido():
    """Salvo cuando la musica obliga: un salto grande entre notas lejanas es legitimo.

    Lo que el coste prohibe es estirar los DEDOS mas de lo humano dentro de una misma
    posicion de la mano, no mover la mano entera.
    """
    coste = CosteDigitacion(estiramiento_maximo=4)
    midis = [40, 41, 42, 43]
    trastes = [p.traste for p in digitar(midis, GUITARRA, coste) if p.traste > 0]
    assert max(trastes) - min(trastes) <= 4


def test_una_nota_que_no_existe_en_el_mastil_se_rechaza():
    with pytest.raises(ValueError, match="C-1|midi 0"):
        digitar([0], GUITARRA)


def test_una_pieza_vacia_da_una_digitacion_vacia():
    assert digitar([], GUITARRA) == ()


def test_los_pesos_son_datos_y_cambiarlos_cambia_la_eleccion():
    """Si encarecer el cambio de cuerda no cambia nada, los pesos no se estan usando."""
    midis = [52, 57]
    barato = digitar(midis, GUITARRA, CosteDigitacion(por_cuerda=0.0))
    caro = digitar(midis, GUITARRA, CosteDigitacion(por_cuerda=50.0))
    assert barato != caro


def test_mil_notas_se_digitan_en_un_pestaneo():
    """O(n*k^2) con k<=6: una cancion larga no puede tardar."""
    import time

    generador = np.random.default_rng(3)
    midis = [int(m) for m in generador.integers(40, 76, size=1000)]
    inicio = time.monotonic()
    digitar(midis, GUITARRA)
    assert time.monotonic() - inicio < 1.0
```

Añade `import numpy as np` al principio del archivo de pruebas.

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_digitacion.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'nucleo.piezas.digitacion'`

- [ ] **Step 3: Implementa el camino de coste mínimo**

```python
"""Donde se toca cada nota: el camino de coste minimo sobre el mastil.

Una nota vive en hasta seis sitios de una guitarra. Elegir el sitio de cada una es
elegir UN camino entre capas: una capa por nota, un nodo por posicion alcanzable, y
el coste de cada arista es lo que cuesta mover la mano de una a otra.

Se resuelve por programacion dinamica, que aqui da el MINIMO EXACTO y no una
aproximacion: con k <= 6 posiciones por nota, el coste es O(n*k^2). Es la diferencia
con la heuristica de `desde_ejercicio.py`, que mira una nota hacia atras y ninguna
hacia delante y esta documentada como provisional.

Los pesos viven en `CosteDigitacion` y son DATOS: si una digitacion sale incomoda se
cambia un numero, no el algoritmo. **No estan medidos tocando**, igual que los demas
umbrales del proyecto.
"""

@dataclass(frozen=True)
class CosteDigitacion:
    """Lo que cuesta cada cosa que la mano puede hacer.

    por_traste: mover la mano un traste a lo largo del mastil. Es el movimiento caro.
    por_cuerda: cambiar de cuerda sin mover la mano. Barato: lo hacen los dedos.
    al_aire: llegar a una cuerda al aire no cuesta nada, venga la mano de donde venga.
    estiramiento_maximo: mas trastes que esto entre dos notas seguidas sin mover la
        mano no es caro, es imposible, asi que esa arista no existe.
    """

    por_traste: float = 1.0
    por_cuerda: float = 0.3
    al_aire: float = 0.0
    estiramiento_maximo: int = 5
```

`digitar` construye la lista de posiciones por nota con `posiciones_en_mastil`, lanza
`ValueError` nombrando la nota si alguna capa queda vacía, y recorre las capas
acumulando el coste mínimo y el predecesor, con numpy para la matriz de costes entre
capas. Al final reconstruye el camino hacia atrás desde el mínimo de la última capa.

`coste_total` suma el coste de las aristas de una secuencia ya elegida: es lo que usa
la prueba de la desigualdad, y tiene que usar **exactamente** la misma función de
coste que `digitar`, o la comparación no significa nada.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_digitacion.py -q`
Expected: PASS, 9 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/digitacion.py tests/test_digitacion.py
git commit -m "feat: la digitacion por coste minimo sobre todo el mastil"
```

---

### Task 3: Un perfil construido desde el archivo

**Files:**
- Modify: `nucleo/afinaciones.py`
- Test: `tests/test_afinaciones.py`

**Interfaces:**
- Consumes: `Cuerda(numero, nota, frecuencia)`, `PerfilAfinacion(nombre, cuerdas, trastes)`.
- Produces: `perfil_desde_midis(nombre, midis, trastes=22) -> PerfilAfinacion`;
  `clave_de_perfil(perfil) -> str | None` (la clave de `PERFILES` si coincide con uno
  conocido, `None` si es a medida).

Hoy `PERFILES` es un diccionario fijo de cuatro. Una canción puede pedir Drop C, medio
tono abajo o siete cuerdas, y hay que poder construir ese perfil al vuelo sin tocar el
diccionario.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
def test_un_perfil_a_medida_tiene_las_cuerdas_que_se_le_den():
    """Drop C: la sexta baja dos tonos y el resto uno."""
    perfil = perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62])
    assert len(perfil.cuerdas) == 6
    assert perfil.cuerdas[0].numero == 6
    assert perfil.cuerdas[0].nota == "C2"
    assert perfil.cuerdas[-1].numero == 1


def test_las_frecuencias_salen_de_los_midis():
    perfil = perfil_desde_midis("estandar", [40, 45, 50, 55, 59, 64])
    assert perfil.cuerdas[0].frecuencia == pytest.approx(82.41, abs=0.01)


def test_siete_cuerdas_tambien_vale():
    perfil = perfil_desde_midis("siete", [35, 40, 45, 50, 55, 59, 64])
    assert len(perfil.cuerdas) == 7
    assert perfil.cuerdas[0].numero == 7


def test_un_perfil_a_medida_que_coincide_con_uno_conocido_se_reconoce():
    """Si la cancion pide afinacion estandar, no inventamos un perfil nuevo."""
    perfil = perfil_desde_midis("lo que diga el archivo", [40, 45, 50, 55, 59, 64])
    assert clave_de_perfil(perfil) == "guitarra_estandar"


def test_un_perfil_raro_no_coincide_con_ninguno():
    assert clave_de_perfil(perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62])) is None


def test_sin_cuerdas_no_hay_perfil():
    with pytest.raises(ValueError, match="cuerda"):
        perfil_desde_midis("vacio", [])


def test_el_perfil_a_medida_sirve_para_digitar():
    """La prueba que importa: lo que se construye tiene que funcionar aguas abajo."""
    from nucleo.piezas.digitacion import digitar

    perfil = perfil_desde_midis("Drop C", [36, 43, 48, 53, 57, 62])
    assert len(digitar([36, 48, 60], perfil)) == 3
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_afinaciones.py -q`
Expected: FAIL, `ImportError: cannot import name 'perfil_desde_midis'`

- [ ] **Step 3: Implementa**

Las cuerdas se numeran de la más grave a la más aguda igual que los perfiles que ya
existen: la primera de la lista es la de número más alto. El nombre de cada cuerda sale
de `nombre_de_midi` y la frecuencia de `midi_a_frecuencia`, las dos de `nucleo/musica.py`.
`clave_de_perfil` compara las frecuencias al aire con las de cada perfil conocido con
una tolerancia de un cent, para no fallar por el redondeo.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add nucleo/afinaciones.py tests/test_afinaciones.py
git commit -m "feat: construir un perfil de afinacion desde lo que diga el archivo"
```

---

### Task 4: El lector de Guitar Pro

**Files:**
- Create: `nucleo/piezas/desde_guitarpro.py`, `nucleo/piezas/lectores.py` (solo con
  `PistaDisponible`; el registro lo añade la Tarea 8 al mismo archivo)
- Modify: `pyproject.toml` (dependencia `PyGuitarPro>=0.11`), `uv.lock`
- Test: `tests/test_desde_guitarpro.py`

**Interfaces:**
- Consumes: `Pieza`, `NotaEnPieza`, `Seccion` (Tarea 1); `digitar` (Tarea 2);
  `perfil_desde_midis`, `clave_de_perfil` (Tarea 3).
- Produces: `PistaDisponible(numero, nombre, instrumento, cuerdas_midi, notas, motivo_no_usable)`
  **en `nucleo/piezas/lectores.py`**, para que los cuatro lectores lo compartan sin que
  ninguno dependa de otro;
  `pistas_de(ruta) -> tuple[PistaDisponible, ...]`;
  `pieza_desde_guitarpro(ruta, numero_pista) -> Pieza`.

**Lo que hay que saber del modelo de PyGuitarPro**, verificado ejecutándolo:

- `guitarpro.parse(ruta) -> Song`, con `Song.tracks`, `Song.tempo`, `Song.measureHeaders`.
- `Track.name`, `Track.strings` (lista de `GuitarString(number, value)` donde `value`
  es el **MIDI de la cuerda al aire**), `Track.fretCount`, `Track.measures`,
  `Track.isPercussionTrack`.
- `Measure.voices` → `Voice.beats` → `Beat.start` (**tick absoluto**), `Beat.duration`,
  `Beat.notes` → `Note.string` (número de cuerda), `Note.value` (**el traste**),
  `Note.type` (`NoteType.rest`, `normal`, `tie`, `dead`).
- **`Duration.quarterTime == 960`**: los ticks por negra. `pulsos = (start - inicio) / 960`.
- `MeasureHeader.marker.title` es el nombre de la sección, `MeasureHeader.start` su tick,
  `MeasureHeader.timeSignature.numerator/.denominator` el compás.

- [ ] **Step 1: Escribe las pruebas que fallan**

Las muestras se **fabrican**: PyGuitarPro escribe `.gp5`. Ningún archivo ajeno entra al
repositorio.

```python
import guitarpro
import pytest

from nucleo.piezas.desde_guitarpro import pieza_desde_guitarpro, pistas_de

TICKS_NEGRA = guitarpro.Duration.quarterTime


def cancion(cuerdas_midi=(64, 59, 55, 50, 45, 40), percusion=False):
    """Una cancion de una pista con cuatro negras, fabricada a mano."""
    song = guitarpro.Song()
    song.tempo = 90
    pista = song.tracks[0]
    pista.name = "Guitarra"
    pista.isPercussionTrack = percusion
    pista.strings = [
        guitarpro.GuitarString(number=i + 1, value=v) for i, v in enumerate(cuerdas_midi)
    ]
    return song


def escribir(song, tmp_path, nombre="prueba.gp5"):
    ruta = tmp_path / nombre
    guitarpro.write(song, str(ruta))
    return ruta


def test_las_pistas_se_listan_con_su_nombre_y_afinacion(tmp_path):
    ruta = escribir(cancion(), tmp_path)
    pistas = pistas_de(ruta)
    assert pistas[0].nombre == "Guitarra"
    assert pistas[0].cuerdas_midi == (64, 59, 55, 50, 45, 40)
    assert pistas[0].motivo_no_usable is None


def test_una_pista_de_percusion_se_lista_pero_no_se_puede_usar(tmp_path):
    """Review Focus 4: Note.string no significa nada en percusion."""
    ruta = escribir(cancion(percusion=True), tmp_path)
    pista = pistas_de(ruta)[0]
    assert pista.motivo_no_usable is not None
    assert "percusi" in pista.motivo_no_usable.lower()


def test_importar_una_pista_de_percusion_se_rechaza(tmp_path):
    ruta = escribir(cancion(percusion=True), tmp_path)
    with pytest.raises(ValueError, match="percusi"):
        pieza_desde_guitarpro(ruta, 1)


def test_una_pista_sin_cuerdas_no_se_puede_usar(tmp_path):
    song = cancion()
    song.tracks[0].strings = []
    ruta = escribir(song, tmp_path)
    assert pistas_de(ruta)[0].motivo_no_usable is not None


def test_el_tempo_y_la_afinacion_salen_del_archivo(tmp_path):
    ruta = escribir(cancion(), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.tempo == 90
    assert pieza.perfil == "guitarra_estandar"


def test_una_afinacion_rara_produce_un_perfil_a_medida(tmp_path):
    """Drop C: no esta en PERFILES y hay que construirlo."""
    ruta = escribir(cancion(cuerdas_midi=(62, 57, 53, 48, 43, 36)), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.perfil != "guitarra_estandar"


def test_los_silencios_no_entran_como_notas(tmp_path):
    """Review Focus 2: un silencio no es una nota sin altura, es que no hay nota."""
    ruta = escribir(con_notas([(0, 6, 3), ("silencio", None, None), (2, 6, 5)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [n.traste for n in pieza.notas] == [3, 5]


def test_una_nota_ligada_alarga_la_anterior_en_vez_de_entrar_dos_veces(tmp_path):
    """Review Focus 1: una ligadura no es un ataque nuevo.

    Si entrara como nota, el carril pediria tocar algo que no se toca y lo contaria
    como fallo.
    """
    ruta = escribir(con_notas([(0, 6, 3), ("ligada", 6, 3)]), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert len(pieza.notas) == 1
    assert pieza.notas[0].duracion_pulsos == pytest.approx(2.0)


def test_los_marcadores_se_importan_como_secciones(tmp_path):
    ruta = escribir(con_marcadores({0: "Intro", 1: "Estribillo"}), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert [s.nombre for s in pieza.secciones] == ["Intro", "Estribillo"]
    assert pieza.secciones[0].inicio_pulsos == 0.0


def test_un_cambio_de_tempo_a_mitad_se_marca_en_vez_de_tirar_la_cancion(tmp_path):
    """Review Focus 3: Pieza tiene UN tempo. Rechazar la cancion seria peor."""
    ruta = escribir(con_cambio_de_tempo(90, 120), tmp_path)
    pieza = pieza_desde_guitarpro(ruta, 1)
    assert pieza.tempo == 90
    assert pieza.tempo_variable is True


def test_un_archivo_que_no_es_guitar_pro_se_rechaza_con_un_mensaje(tmp_path):
    ruta = tmp_path / "roto.gp5"
    ruta.write_bytes(b"esto no es un gp5")
    with pytest.raises(ValueError) as error:
        pistas_de(ruta)
    assert "gp5" in str(error.value).lower() or "leer" in str(error.value).lower()


def test_una_pista_que_no_existe_se_rechaza_nombrando_las_que_hay(tmp_path):
    ruta = escribir(cancion(), tmp_path)
    with pytest.raises(ValueError, match="1"):
        pieza_desde_guitarpro(ruta, 99)
```

Los tres ayudantes —`con_notas`, `con_marcadores`, `con_cambio_de_tempo`— construyen la
`Song` a mano sobre `cancion()`: añaden `Measure`, `Voice` y `Beat` con `start` en
múltiplos de `TICKS_NEGRA`, ponen `Note(string=..., value=..., type=...)` y, para los
marcadores, `measureHeaders[i].marker = guitarpro.Marker(title=...)`. El implementador
los escribe; son veinte líneas y el modelo está arriba.

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_desde_guitarpro.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'guitarpro'`

- [ ] **Step 3: Añade la dependencia e implementa**

```bash
UV_CACHE_DIR="$TMPDIR/uv-cache" uv add "PyGuitarPro>=0.11"
```

El lector: `pistas_de` abre la canción y describe cada pista sin convertir nada —el
listado tiene que ser barato—; marca `motivo_no_usable` en las de percusión, las que no
tienen cuerdas y las que no tienen notas. `pieza_desde_guitarpro` convierte una:

- Instante y duración en pulsos: `(beat.start - inicio) / Duration.quarterTime`, donde
  `inicio` es el `start` del primer compás, porque PyGuitarPro empieza en 960 y no en 0.
- `NoteType.rest` se salta; `NoteType.tie` **alarga la nota anterior de la misma cuerda
  y traste** en vez de añadir una; `NoteType.dead` se salta, porque una nota apagada no
  tiene altura que seguir.
- El MIDI de cada nota es `cuerda_al_aire + traste`.
- El perfil sale de `Track.strings` con `perfil_desde_midis`, y si `clave_de_perfil` lo
  reconoce se usa esa clave: una canción en afinación estándar no debe inventar un perfil.
- Las repeticiones se expanden recorriendo los compases según `repeatOpen`/`repeatClose`.
- Si el archivo trae más de un tempo, se toma el primero y `tempo_variable=True`.
- Cualquier fallo de la librería se traduce a `ValueError` con un mensaje que diga qué
  pasó, **sin traceback**: quien lee el mensaje es el usuario, no un programador.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/desde_guitarpro.py tests/test_desde_guitarpro.py pyproject.toml uv.lock
git commit -m "feat: leer canciones de Guitar Pro"
```

---

### Task 5: El lector de MIDI

**Files:**
- Create: `nucleo/piezas/desde_midi.py`
- Modify: `pyproject.toml` (dependencia `mido>=1.3`), `uv.lock`
- Test: `tests/test_desde_midi.py`

**Interfaces:**
- Consumes: `Pieza`, `Seccion` (Tarea 1); `digitar` (Tarea 2); `PERFILES`.
- Produces: `pistas_de_midi(ruta) -> tuple[PistaDisponible, ...]`;
  `pieza_desde_midi(ruta, numero_pista, perfil_clave="guitarra_estandar") -> Pieza`.

MIDI da alturas y ritmo exactos y **no dice dónde se toca nada**: toda la digitación es
nuestra, con `digitar`. El perfil no viene en el archivo, así que se recibe: es la
afinación que tenga el usuario.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import mido
import pytest

from nucleo.piezas.desde_midi import pieza_desde_midi, pistas_de_midi

TICKS = 480


def midi_de(notas, tempo_bpm=120, marcadores=(), nombre_pista="Guitarra"):
    """Fabrica un .mid con las notas dadas como (midi, inicio_ticks, duracion_ticks)."""
    archivo = mido.MidiFile(ticks_per_beat=TICKS)
    pista = mido.MidiTrack()
    archivo.tracks.append(pista)
    pista.append(mido.MetaMessage("track_name", name=nombre_pista, time=0))
    pista.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    for titulo, tick in marcadores:
        pista.append(mido.MetaMessage("marker", text=titulo, time=tick))
    reloj = 0
    for midi, inicio, duracion in notas:
        pista.append(mido.Message("note_on", note=midi, time=inicio - reloj))
        pista.append(mido.Message("note_off", note=midi, time=duracion))
        reloj = inicio + duracion
    return archivo


def test_las_notas_y_el_ritmo_salen_exactos(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS), (45, TICKS, TICKS * 2)]).save(str(ruta))
    pieza = pieza_desde_midi(ruta, 0)
    assert [n.midi for n in pieza.notas] == [40, 45]
    assert [n.inicio_pulsos for n in pieza.notas] == [0.0, 1.0]
    assert [n.duracion_pulsos for n in pieza.notas] == [1.0, 2.0]


def test_la_digitacion_la_pone_el_algoritmo(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS)]).save(str(ruta))
    nota = pieza_desde_midi(ruta, 0).notas[0]
    assert nota.cuerda == 6 and nota.traste == 0


def test_el_tempo_sale_del_archivo(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS)], tempo_bpm=90).save(str(ruta))
    assert pieza_desde_midi(ruta, 0).tempo == 90


def test_un_cambio_de_tempo_se_marca(tmp_path):
    """Review Focus 3."""
    ruta = tmp_path / "x.mid"
    archivo = midi_de([(40, 0, TICKS), (45, TICKS, TICKS)], tempo_bpm=90)
    archivo.tracks[0].append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(140), time=0))
    archivo.save(str(ruta))
    pieza = pieza_desde_midi(ruta, 0)
    assert pieza.tempo == 90
    assert pieza.tempo_variable is True


def test_los_marcadores_se_importan_como_secciones(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS)], marcadores=[("Intro", 0)]).save(str(ruta))
    assert [s.nombre for s in pieza_desde_midi(ruta, 0).secciones] == ["Intro"]


def test_una_nota_que_no_cabe_en_el_mastil_se_rechaza_nombrandola(tmp_path):
    """Un MIDI de piano trae notas que una guitarra no tiene."""
    ruta = tmp_path / "x.mid"
    midi_de([(20, 0, TICKS)]).save(str(ruta))
    with pytest.raises(ValueError) as error:
        pieza_desde_midi(ruta, 0)
    assert "G#0" in str(error.value) or "20" in str(error.value)


def test_una_pista_sin_notas_no_se_puede_usar(tmp_path):
    ruta = tmp_path / "x.mid"
    midi_de([]).save(str(ruta))
    assert pistas_de_midi(ruta)[0].motivo_no_usable is not None


def test_dos_notas_a_la_vez_entran_las_dos(tmp_path):
    """Un acorde: el modelo lo admite, el carril no lo sigue. Lo avisa la pantalla."""
    ruta = tmp_path / "x.mid"
    midi_de([(40, 0, TICKS), (47, 0, TICKS)]).save(str(ruta))
    pieza = pieza_desde_midi(ruta, 0)
    assert len(pieza.notas) == 2
    assert pieza.notas[0].inicio_pulsos == pieza.notas[1].inicio_pulsos
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_desde_midi.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'mido'`

- [ ] **Step 3: Añade la dependencia e implementa**

```bash
UV_CACHE_DIR="$TMPDIR/uv-cache" uv add "mido>=1.3"
```

Los tiempos de mido son **delta**: hay que acumularlos. `pulsos = tick / ticks_per_beat`.
Un `note_on` con `velocity=0` es un `note_off`, que es la trampa clásica del formato. El
compás sale de `time_signature` si está, y si no, 4/4. La digitación se pide a `digitar`
con todos los midis de golpe, que es lo que hace que el resultado sea un mínimo sobre la
pieza entera y no por nota.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/desde_midi.py tests/test_desde_midi.py pyproject.toml uv.lock
git commit -m "feat: leer canciones de MIDI, con la digitacion calculada"
```

---

### Task 6: El lector de MusicXML

**Files:**
- Create: `nucleo/piezas/desde_musicxml.py`
- Modify: `pyproject.toml` (dependencia `music21>=10.5`), `uv.lock`
- Test: `tests/test_desde_musicxml.py`

**Interfaces:**
- Consumes: `Pieza`, `Seccion` (Tarea 1); `digitar` (Tarea 2); `perfil_desde_midis` (Tarea 3).
- Produces: `pistas_de_musicxml(ruta) -> tuple[PistaDisponible, ...]`;
  `pieza_desde_musicxml(ruta, numero_pista, perfil_clave="guitarra_estandar") -> Pieza`.

MusicXML trae ritmo y compases siempre, y **a veces** trae cuerda y traste, en
`<technical><string>` y `<fret>`. Cuando vienen se respetan: quien escribió esa
tablatura sabía más que nuestro algoritmo. Cuando no, va a `digitar`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import pytest
from music21 import articulations, note, stream, tempo

from nucleo.piezas.desde_musicxml import pieza_desde_musicxml, pistas_de_musicxml


def partitura(midis_y_duraciones, con_tablatura=False, bpm=100):
    parte = stream.Part()
    parte.partName = "Guitarra"
    parte.append(tempo.MetronomeMark(number=bpm))
    for midi, duracion in midis_y_duraciones:
        n = note.Note(midi)
        n.quarterLength = duracion
        if con_tablatura:
            indicacion = articulations.StringIndication()
            indicacion.number = 6
            traste = articulations.FretIndication()
            traste.number = midi - 40
            n.articulations.extend([indicacion, traste])
        parte.append(n)
    obra = stream.Score()
    obra.append(parte)
    return obra


def escribir(obra, tmp_path, nombre="x.xml"):
    ruta = tmp_path / nombre
    obra.write("musicxml", fp=str(ruta))
    return ruta


def test_el_ritmo_y_las_alturas_salen_del_archivo(tmp_path):
    ruta = escribir(partitura([(40, 1.0), (45, 2.0)]), tmp_path)
    pieza = pieza_desde_musicxml(ruta, 0)
    assert [n.midi for n in pieza.notas] == [40, 45]
    assert [n.duracion_pulsos for n in pieza.notas] == [1.0, 2.0]


def test_si_el_archivo_trae_tablatura_se_respeta(tmp_path):
    """El que la escribio sabia mas que nuestro algoritmo."""
    ruta = escribir(partitura([(45, 1.0)], con_tablatura=True), tmp_path)
    nota = pieza_desde_musicxml(ruta, 0).notas[0]
    assert nota.cuerda == 6 and nota.traste == 5


def test_sin_tablatura_la_pone_el_algoritmo(tmp_path):
    ruta = escribir(partitura([(45, 1.0)]), tmp_path)
    nota = pieza_desde_musicxml(ruta, 0).notas[0]
    assert nota.cuerda == 5 and nota.traste == 0


def test_el_tempo_sale_del_archivo(tmp_path):
    ruta = escribir(partitura([(40, 1.0)], bpm=76), tmp_path)
    assert pieza_desde_musicxml(ruta, 0).tempo == 76


def test_un_cambio_de_tempo_se_marca(tmp_path):
    """Review Focus 3."""
    obra = partitura([(40, 1.0), (45, 1.0)], bpm=76)
    obra.parts[0].insert(1.0, tempo.MetronomeMark(number=120))
    ruta = escribir(obra, tmp_path)
    pieza = pieza_desde_musicxml(ruta, 0)
    assert pieza.tempo == 76
    assert pieza.tempo_variable is True


def test_una_nota_ligada_alarga_la_anterior(tmp_path):
    """Review Focus 1, otra vez: una ligadura no es un ataque nuevo."""
    from music21 import tie

    obra = partitura([(40, 1.0), (40, 1.0)])
    obra.parts[0].notes[0].tie = tie.Tie("start")
    obra.parts[0].notes[1].tie = tie.Tie("stop")
    ruta = escribir(obra, tmp_path)
    pieza = pieza_desde_musicxml(ruta, 0)
    assert len(pieza.notas) == 1
    assert pieza.notas[0].duracion_pulsos == pytest.approx(2.0)


def test_las_marcas_de_ensayo_se_importan_como_secciones(tmp_path):
    from music21 import expressions

    obra = partitura([(40, 1.0), (45, 1.0)])
    obra.parts[0].insert(1.0, expressions.RehearsalMark("B"))
    ruta = escribir(obra, tmp_path)
    assert [s.nombre for s in pieza_desde_musicxml(ruta, 0).secciones] == ["B"]


def test_un_archivo_ilegible_se_rechaza_con_mensaje(tmp_path):
    ruta = tmp_path / "roto.xml"
    ruta.write_text("<esto no es musicxml>")
    with pytest.raises(ValueError):
        pistas_de_musicxml(ruta)


def test_una_parte_sin_notas_no_se_puede_usar(tmp_path):
    ruta = escribir(partitura([]), tmp_path)
    assert pistas_de_musicxml(ruta)[0].motivo_no_usable is not None
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_desde_musicxml.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'music21'`

- [ ] **Step 3: Añade la dependencia e implementa**

```bash
UV_CACHE_DIR="$TMPDIR/uv-cache" uv add "music21>=10.5"
```

music21 da `offset` y `quarterLength` ya en negras, que **son** nuestros pulsos: no hay
conversión. Las ligaduras se detectan por `nota.tie`, y una con `tie.type` en
`("stop", "continue")` funde con la anterior. La tablatura vive en
`nota.articulations` como `StringIndication` y `FretIndication`. Los dos tienen que
venir para fiarse: una sola de las dos no dice dónde se toca.

Las repeticiones se expanden igual que en Guitar Pro: music21 lo hace solo con
`obra.expandRepeats()`, que es una línea y evita escribirlo a mano. Si la partitura tiene
repeticiones mal formadas, la librería lanza; se traduce a `ValueError` con su mensaje.

Este import tarda: `music21` arrastra 23 paquetes y su primera carga no es instantánea.
Impórtalo **dentro de la función**, no en la cabecera del módulo, para que arrancar el
servidor no pague ese precio cuando nadie va a leer un MusicXML.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/desde_musicxml.py tests/test_desde_musicxml.py pyproject.toml uv.lock
git commit -m "feat: leer canciones de MusicXML, respetando su tablatura si la trae"
```

---

### Task 7: El lector de tablatura ASCII

**Files:**
- Create: `nucleo/piezas/desde_ascii.py`
- Test: `tests/test_desde_ascii.py`

**Interfaces:**
- Consumes: `Pieza`, `NotaEnPieza` (Tarea 1); `perfil_desde_midis`, `clave_de_perfil`
  (Tarea 3).
- Produces: `pieza_desde_ascii(texto, tempo=90, perfil_clave=None) -> Pieza`.

Es el lector flojo y hay que decirlo sin adornos: la tablatura de texto **no trae
ritmo**. Se infiere de las columnas —cuántos guiones hay entre un número y el
siguiente— y eso funciona en tablaturas bien alineadas y falla en las que no, que son
muchas. La pieza sale con `ritmo_aproximado=True` y la pantalla lo dice.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import pytest

from nucleo.piezas.desde_ascii import pieza_desde_ascii

ESTANDAR = """\
e|---------------|
B|---------------|
G|---------------|
D|---------------|
A|---------------|
E|--0---2---3----|
"""


def test_las_seis_lineas_dan_cuerda_y_traste():
    pieza = pieza_desde_ascii(ESTANDAR)
    assert [(n.cuerda, n.traste) for n in pieza.notas] == [(6, 0), (6, 2), (6, 3)]


def test_la_sexta_cuerda_es_la_linea_de_abajo():
    """La convencion de la tablatura, al reves de como se leen las listas."""
    texto = "e|--3--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-----|\n"
    assert pieza_desde_ascii(texto).notas[0].cuerda == 1


def test_el_ritmo_se_infiere_de_las_columnas():
    """Cuatro guiones entre notas: la misma duracion para las dos primeras."""
    pieza = pieza_desde_ascii(ESTANDAR)
    assert pieza.notas[0].duracion_pulsos == pytest.approx(pieza.notas[1].duracion_pulsos)


def test_la_pieza_sale_marcada_como_de_ritmo_aproximado():
    """Fingir que una tablatura de foro trae ritmo seria mentir."""
    assert pieza_desde_ascii(ESTANDAR).ritmo_aproximado is True


def test_un_traste_de_dos_digitos_se_lee_entero():
    texto = "e|-----|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-12--|\n"
    assert pieza_desde_ascii(texto).notas[0].traste == 12


def test_cuatro_lineas_se_leen_como_un_bajo():
    """Review Focus 5: el numero de lineas decide el instrumento."""
    texto = "G|--5--|\nD|-----|\nA|-----|\nE|--0--|\n"
    pieza = pieza_desde_ascii(texto)
    assert pieza.notas[1].cuerda == 4
    assert "bajo" in pieza.perfil.lower() or len(pieza.perfil) > 0


def test_siete_lineas_tambien_se_leen():
    texto = "\n".join("x|--0--|" for _ in range(7)) + "\n"
    assert len(pieza_desde_ascii(texto).notas) == 7


def test_lineas_de_distinta_longitud_se_rechazan_nombrando_la_linea():
    """Review Focus 5: es el sintoma de una tablatura copiada a medias."""
    texto = "e|--3--|\nB|--3-|\nG|--3--|\nD|--3--|\nA|--3--|\nE|--3--|\n"
    with pytest.raises(ValueError, match="2|linea"):
        pieza_desde_ascii(texto)


def test_un_texto_que_no_es_una_tablatura_se_rechaza():
    with pytest.raises(ValueError):
        pieza_desde_ascii("Esto es la letra de la cancion, no una tablatura")


def test_dos_numeros_en_la_misma_columna_son_un_acorde():
    texto = "e|-----|\nB|-----|\nG|--0--|\nD|--2--|\nA|--2--|\nE|--0--|\n"
    pieza = pieza_desde_ascii(texto)
    assert len(pieza.notas) == 4
    assert len({n.inicio_pulsos for n in pieza.notas}) == 1


def test_el_tempo_se_recibe_porque_el_texto_no_lo_trae():
    assert pieza_desde_ascii(ESTANDAR, tempo=120).tempo == 120
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_desde_ascii.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implementa**

El parseo: se quedan las líneas que parezcan de tablatura —las que son mayoría de
guiones y dígitos—, se comprueba que todas midan lo mismo y se rechaza nombrando la
primera que no, se lee cada columna buscando números de uno o dos dígitos, y la línea
de más abajo es la cuerda de número más alto.

El ritmo: la distancia en columnas entre un ataque y el siguiente es su duración, y la
unidad se elige de modo que **la distancia más corta de la tablatura sea una negra**,
que es la convención implícita de quien las escribe. Es una heurística y el docstring
tiene que decirlo con todas las letras, igual que el de `elegir_posicion`.

El perfil: el número de líneas decide el instrumento —seis guitarra, cuatro bajo,
siete una guitarra de siete—, y si la primera columna trae las letras de las cuerdas se
usan para construir el perfil con `perfil_desde_midis`. Si no, se asume la afinación
estándar del instrumento de ese número de cuerdas.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/desde_ascii.py tests/test_desde_ascii.py
git commit -m "feat: leer tablatura ASCII, con el ritmo declarado como aproximado"
```

---

### Task 8: El registro de lectores

**Files:**
- Create: `nucleo/piezas/lectores.py`
- Test: `tests/test_lectores.py`

**Interfaces:**
- Consumes: los cuatro lectores de las Tareas 4 a 7.
- Produces: `FORMATOS: dict[str, str]` (extensión → nombre legible);
  `pistas_de_archivo(ruta) -> tuple[PistaDisponible, ...]`;
  `importar(ruta, numero_pista, perfil_clave=None) -> Pieza`.
  `PistaDisponible` ya vive en este archivo desde la Tarea 4; aquí se le añade el
  registro, no se mueve nada.

Un registro fino, como el de detectores de la etapa 1 y el de generadores de la 2a:
despacha por extensión y **no sabe nada** de los formatos.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
def test_los_cuatro_formatos_estan_registrados():
    assert {".gp5", ".mid", ".xml", ".txt"} <= set(FORMATOS)


def test_una_extension_desconocida_se_rechaza_diciendo_cuales_valen(tmp_path):
    ruta = tmp_path / "cancion.pdf"
    ruta.write_text("x")
    with pytest.raises(ValueError) as error:
        pistas_de_archivo(ruta)
    assert ".gp5" in str(error.value)


def test_el_registro_despacha_al_lector_correcto(tmp_path, monkeypatch):
    """No comprueba el contenido: comprueba que llama a quien debe."""
    llamados = []
    monkeypatch.setitem(_LECTORES, ".mid", lambda ruta: llamados.append("midi") or ())
    ruta = tmp_path / "x.mid"
    ruta.write_bytes(b"")
    pistas_de_archivo(ruta)
    assert llamados == ["midi"]


def test_la_extension_no_distingue_mayusculas(tmp_path):
    ruta = tmp_path / "CANCION.GP5"
    ruta.write_bytes(b"no importa")
    with pytest.raises(ValueError) as error:
        pistas_de_archivo(ruta)
    assert "gp5" not in str(error.value).lower() or "leer" in str(error.value).lower()
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_lectores.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implementa**

**Una costura que hay que resolver aquí:** `pieza_desde_ascii` recibe **texto** y no una
ruta, porque una tablatura también puede llegar pegada en un cuadro de texto. El registro
es quien lee el archivo y le pasa el contenido; los otros tres reciben la ruta, porque son
binarios o porque su librería abre el archivo ella misma. Que la costura esté aquí y no en
el lector es deliberado: así el lector de ASCII sirve para las dos cosas.

Las extensiones: `.gp3`, `.gp4`, `.gp5`, `.gpx`, `.gp` → Guitar Pro; `.mid`, `.midi` →
MIDI; `.xml`, `.musicxml`, `.mxl` → MusicXML; `.txt`, `.tab` → ASCII. En minúsculas
siempre, porque los archivos descargados vienen como vienen.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/lectores.py tests/test_lectores.py
git commit -m "feat: el registro de lectores despacha por extension"
```

---

### Task 9: La biblioteca en el servidor

**Files:**
- Create: `servidor/canciones.py`
- Modify: `servidor/app.py`, `.gitignore`
- Test: `tests/test_app_canciones.py`

**Interfaces:**
- Consumes: `pistas_de_archivo`, `importar`, `FORMATOS` (Tarea 8);
  `clave_de_perfil` (Tarea 3); `Sesion.configuracion.perfil`.
- Produces: `Biblioteca(carpeta)` con `listar()`, `guardar(nombre, datos)`,
  `ruta_de(id)`; `TAMANO_MAXIMO_BYTES = 10 * 1024 * 1024`; y los cuatro endpoints.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
def test_la_lista_esta_vacia_al_principio(cliente):
    assert cliente.get("/api/canciones").json() == []


def test_subir_un_archivo_lo_deja_en_la_lista(cliente):
    respuesta = cliente.post(
        "/api/canciones",
        files={"archivo": ("mia.txt", b"e|--0--|\nB|-----|\nG|-----|\nD|-----|\nA|-----|\nE|-----|\n")},
    )
    assert respuesta.status_code == 200
    assert [c["id"] for c in cliente.get("/api/canciones").json()] == ["mia.txt"]


def test_un_formato_desconocido_se_rechaza_diciendo_cuales_valen(cliente):
    respuesta = cliente.post("/api/canciones", files={"archivo": ("x.pdf", b"x")})
    assert respuesta.status_code == 400
    assert ".gp5" in respuesta.json()["detail"]


def test_un_archivo_demasiado_grande_se_rechaza(cliente):
    enorme = b"x" * (10 * 1024 * 1024 + 1)
    respuesta = cliente.post("/api/canciones", files={"archivo": ("x.mid", enorme)})
    assert respuesta.status_code == 400
    assert "10" in respuesta.json()["detail"]


def test_un_nombre_con_ruta_se_rechaza(cliente):
    """La carpeta es la base de datos; `..` es un intento de leer el disco."""
    respuesta = cliente.post("/api/canciones", files={"archivo": ("../../etc/passwd", b"x")})
    assert respuesta.status_code == 400


def test_pedir_una_cancion_que_no_existe_da_404(cliente):
    assert cliente.get("/api/canciones/inventada.gp5/pistas").status_code == 404


def test_las_pistas_se_leen_sin_importar_la_cancion(cliente, tmp_path):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pistas = cliente.get("/api/canciones/x.txt/pistas").json()
    assert pistas["pistas"][0]["nombre"]
    assert "afinacion" in pistas


def test_importar_devuelve_una_pieza_lista_para_el_carril(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    respuesta = cliente.post("/api/canciones/x.txt/importar", json={"pista": 0})
    assert respuesta.status_code == 200
    pieza = respuesta.json()
    assert pieza["notas"]
    assert pieza["ritmo_aproximado"] is True


def test_la_respuesta_dice_si_hay_que_cambiar_de_afinacion(cliente):
    """Lo que hace accionable el aviso: la clave del perfil que pide la cancion."""
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    pistas = cliente.get("/api/canciones/x.txt/pistas").json()
    assert "perfil_activo" in pistas
    assert "coincide" in pistas


def test_importar_una_pista_que_no_existe_da_400(cliente):
    cliente.post("/api/canciones", files={"archivo": ("x.txt", TABLATURA)})
    assert cliente.post("/api/canciones/x.txt/importar", json={"pista": 99}).status_code == 400
```

El fixture `cliente` es el de `tests/test_app_carril.py`, con la carpeta de canciones
apuntando a `tmp_path` para no ensuciar el proyecto.

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_app_canciones.py -q`
Expected: FAIL con 404 en todas las rutas.

- [ ] **Step 3: Implementa**

`Biblioteca` guarda en una carpeta que recibe por parámetro —`canciones/` en producción,
`tmp_path` en las pruebas— y **resuelve cada nombre contra ella**, rechazando lo que
salga: `(carpeta / nombre).resolve()` tiene que seguir estando dentro de
`carpeta.resolve()`. Un `..` no es un nombre de canción.

`/pistas` devuelve además `perfil_activo`, la clave del perfil que pide la canción y si
coinciden: **eso es lo que hace accionable el aviso**, y lo decide el servidor, no la
interfaz.

Añade `canciones/` a `.gitignore` con un comentario que diga por qué: son archivos de
terceros y no se distribuyen con el código.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add servidor/canciones.py servidor/app.py tests/test_app_canciones.py .gitignore
git commit -m "feat: la biblioteca de canciones, con carpeta y subida"
```

---

### Task 10: La pantalla de canciones

**Files:**
- Create: `interfaz/src/Canciones.tsx`, `interfaz/src/tiposCancion.ts`
- Modify: `interfaz/src/App.tsx`, `interfaz/src/estilos.css`
- Test: `interfaz/src/Canciones.test.tsx`

**Interfaces:**
- Consumes: los cuatro endpoints de la Tarea 9; `Pieza` de `tiposPieza.ts`.
- Produces: el componente `Canciones`, y el módulo `canciones` en `servidor/modulos.py`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```typescript
it("lista las canciones de la carpeta", async () => {
  vi.stubGlobal("fetch", crearFetchFalso({ canciones: [{ id: "x.gp5", nombre: "x", formato: "Guitar Pro" }] }));
  render(<Canciones />);
  expect(await screen.findByText("x")).toBeTruthy();
});

it("al elegir una cancion muestra sus pistas", async () => {
  const fetchFalso = crearFetchFalso({ canciones: [{ id: "x.gp5", nombre: "x", formato: "Guitar Pro" }] });
  vi.stubGlobal("fetch", fetchFalso);
  render(<Canciones />);
  fireEvent.click(await screen.findByText("x"));
  expect(await screen.findByText(/guitarra/i)).toBeTruthy();
});

it("una pista que no se puede usar se muestra con su motivo y no se puede elegir", async () => {
  vi.stubGlobal("fetch", crearFetchFalso({
    pistas: [{ numero: 1, nombre: "Bateria", motivo_no_usable: "es una pista de percusion" }],
  }));
  render(<Canciones />);
  fireEvent.click(await screen.findByText("x"));
  expect(await screen.findByText(/percusi/i)).toBeTruthy();
  expect((await screen.findByRole("button", { name: /bateria/i })).hasAttribute("disabled")).toBe(true);
});

it("avisa cuando la cancion pide otra afinacion y ofrece ir al afinador", async () => {
  vi.stubGlobal("fetch", crearFetchFalso({ coincide: false, perfil_cancion: "Drop C" }));
  render(<Canciones />);
  fireEvent.click(await screen.findByText("x"));
  expect(await screen.findByText(/Drop C/)).toBeTruthy();
  expect(await screen.findByRole("button", { name: /afinador/i })).toBeTruthy();
});

it("avisa de que el ritmo es aproximado cuando la pieza lo dice", async () => {
  vi.stubGlobal("fetch", crearFetchFalso({ pieza: { ritmo_aproximado: true, notas: [] } }));
  render(<Canciones />);
  fireEvent.click(await screen.findByText("x"));
  fireEvent.click(await screen.findByRole("button", { name: /guitarra/i }));
  expect(await screen.findByText(/aproximad/i)).toBeTruthy();
});

it("avisa de que el carril no sigue acordes cuando la pieza los trae", async () => {
  vi.stubGlobal("fetch", crearFetchFalso({
    pieza: { notas: [{ inicio_pulsos: 0 }, { inicio_pulsos: 0 }] },
  }));
  render(<Canciones />);
  fireEvent.click(await screen.findByText("x"));
  fireEvent.click(await screen.findByRole("button", { name: /guitarra/i }));
  expect(await screen.findByText(/acorde/i)).toBeTruthy();
});
```

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test Canciones`
Expected: FAIL, no existe `./Canciones`.

- [ ] **Step 3: Implementa**

La pantalla: lista a la izquierda con un botón de subir, pistas a la derecha al elegir
una canción, y los avisos antes de empezar —afinación distinta con botón al afinador,
ritmo aproximado, acordes que el carril no sigue—. Al confirmar, la pieza va al carril.

**El aviso de acordes se decide mirando si hay dos notas con el mismo `inicio_pulsos`.**
Eso es un cálculo sobre datos que ya vienen, no una decisión duplicada: el núcleo no
publica «esta pieza tiene acordes» y no hace falta que lo haga. Si en la revisión parece
lo contrario, dilo en vez de dejarlo.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test && pnpm build && pnpm lint`
Expected: PASS y build limpio.

- [ ] **Step 5: Commit**

```bash
git add interfaz/src/Canciones.tsx interfaz/src/tiposCancion.ts interfaz/src/Canciones.test.tsx interfaz/src/App.tsx interfaz/src/estilos.css servidor/modulos.py
git commit -m "feat: la pantalla de canciones, con los avisos antes de empezar"
```

---

### Task 11: Documentación y cierre

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Documenta la etapa**

**El párrafo del límite del evaluador de este README se escribió tres veces y las dos
primeras eran falsas; el de la etapa 3a necesitó cuatro pasadas.** La regla aquí es la
misma: **cada afirmación se comprueba ejecutando algo**, y lo que no se pueda comprobar
se dice que no está medido.

Hay que documentar:

- Los cuatro formatos, y **qué trae cada uno**: Guitar Pro lo da todo; MusicXML da el
  ritmo y a veces la tablatura; MIDI no dice dónde se toca nada; la tablatura ASCII no
  trae ritmo y la pieza sale marcada como aproximada.
- **La carpeta `canciones/` y que está fuera de git**, porque las tablaturas son
  material de terceros.
- **Que al abrir una canción en otra afinación te dice a cuál afinarte y te lleva al
  afinador**, y que el carril no la aceptará hasta que lo hagas — es la regla de la
  etapa 3a, no una nueva.
- **La digitación por coste mínimo**, diciendo que los pesos están razonados y **no
  medidos tocando**.
- Los límites: acordes importados pero no seguidos; ligados, bends y armónicos
  ignorados; repeticiones expandidas; `.gpx`/`.gp` con menos cobertura que `.gp5`.
- Que practicar por secciones, con bucles y tempo ajustable, es la etapa 3c, y **que la
  investigación disponible sugiere alternar pasajes en vez de repetir uno en bucle**,
  al revés que Rocksmith, con el matiz de que son diez sujetos.

- [ ] **Step 2: Comprueba la suite entera**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Run: `cd interfaz && pnpm test && pnpm build && pnpm lint`
Expected: todo verde.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: importar canciones, con lo que cada formato no trae"
```

---

## Verificación de la etapa completa

| Qué | Cómo |
|---|---|
| Un `.gp5` real entra y se toca | Exportar uno desde Guitar Pro o TuxGuitar y abrirlo |
| La digitación es cómoda | Mirar una canción importada y juzgar si la mano salta **(lo juzga el usuario)** |
| El aviso de afinación funciona | Abrir algo en Drop C y seguir el botón al afinador |
| El ritmo del ASCII | Pegar una tablatura de un foro y ver si se puede seguir **(lo juzga el usuario)** |
| Una canción larga no atasca el carril | Importar algo de tres minutos y mirar si va fluido |

Las cinco necesitan la guitarra y archivos de verdad, y las hace el usuario.
