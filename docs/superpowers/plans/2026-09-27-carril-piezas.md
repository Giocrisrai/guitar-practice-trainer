# Carril de piezas (etapa 3a) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las notas de una pieza vengan hacia ti sobre el mástil y se corrija
lo que tocas contra el tiempo en que debía sonar, no solo contra su altura.

**Architecture:** Un modelo `Pieza` con tiempo absoluto en pulsos vive en
`nucleo/piezas/`, independiente de los ejercicios salvo por un único conversor.
La mitad de abajo del evaluador de ejercicios —*qué nota tocaste y cuándo*— se
extrae a `DetectorPulsaciones` y la comparten los dos modos. El servidor lleva un
reloj monotónico y lo publica; el navegador interpola a 60 fps entre paquetes y
corrige la deriva, dibujando en canvas sobre una capa de geometría pura.

**Tech Stack:** Python 3.13.1 con uv, numpy, FastAPI, WebSocket. React + Vite +
TypeScript con pnpm y vitest. Canvas 2D.

**Spec:** `docs/superpowers/specs/2026-09-27-carril-piezas-design.md`

## Corrección a la especificación, decidida al escribir este plan

La especificación (§4) dice que el carril «envuelve» a `EvaluadorEjercicio`. **No
es posible y el plan no lo intenta.** En el evaluador, el índice de la nota en
curso avanza cuando aciertas; en el carril avanza con el reloj. Son dos máquinas
de estado distintas.

Lo que de verdad comparten es la detección: los dos disparadores (ataque de
energía con lectura diferida, y cambio de nota estable), la regla de credibilidad
y el filtro contra resolver dos veces la misma pulsación. Esa mitad se **extrae**
a `nucleo/ejercicios/pulsaciones.py` sin cambiar su comportamiento —las pruebas
actuales del evaluador son la red— y la usan los dos modos. Duplicarla sería
garantizar que las dos copias se separen.

## Global Constraints

- Python **3.13.1** gestionado con **uv**. Los comandos son `uv run ...`, nunca
  `pip install` ni `.venv/bin/...`. En este entorno hace falta el prefijo
  `UV_CACHE_DIR="$TMPDIR/uv-cache"`.
- Gestor de paquetes JavaScript: **pnpm**, nunca npm.
- Comentarios, nombres de variables, funciones y clases **en español**.
- Preferir **numpy/scipy** sobre implementaciones manuales.
- Pruebas con **pytest**. **Ninguna prueba abre el dispositivo de audio real.**
- Ninguna prueba usa `sleep` para esperar al reloj de la pieza: el reloj se
  inyecta.
- `nucleo/` no importa nada de `servidor/` ni de `interfaz/`.
- `nucleo/piezas/modelo.py` no importa nada de `nucleo/ejercicios/`.
- Lo que decide el núcleo no se recalcula en la interfaz. En la etapa 2a hubo que
  quitarle a la interfaz cuatro cálculos que no le correspondían.
- Los mensajes de commit terminan con:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `nucleo/piezas/modelo.py` | `NotaEnPieza`, `Pieza`, conversión pulsos↔segundos |
| `nucleo/piezas/desde_ejercicio.py` | Traducir un `Ejercicio` a `Pieza`, eligiendo posición |
| `nucleo/ejercicios/pulsaciones.py` | `DetectorPulsaciones` extraído del evaluador |
| `nucleo/piezas/seguimiento.py` | `SeguidorPieza`: reloj → nota en curso, ventana, desfases |
| `servidor/piezas.py` | `SesionCarril`: observadora del análisis, reloj monotónico |
| `servidor/app.py` | Endpoints y WebSocket del carril |
| `interfaz/src/relojCarril.ts` | Interpolación y corrección de deriva (puro) |
| `interfaz/src/geometriaCarril.ts` | Tiempo y cuerda → píxeles (puro) |
| `interfaz/src/Carril.tsx` | Canvas y cableado |
| `interfaz/src/VistaEscrita.tsx` | Tablatura y pentagrama estáticos |

---

### Task 1: El modelo `Pieza`

**Files:**
- Create: `nucleo/piezas/__init__.py`, `nucleo/piezas/modelo.py`
- Test: `tests/test_modelo_piezas.py`

**Interfaces:**
- Consumes: nada.
- Produces: `NotaEnPieza(midi, cuerda, traste, inicio_pulsos, duracion_pulsos)`,
  `Pieza(nombre, perfil, tempo, compas, notas)`, `Pieza.a_dict()`,
  `Pieza.duracion_pulsos`, `Pieza.duracion_s`,
  `pulsos_a_segundos(pulsos, tempo)`, `segundos_a_pulsos(segundos, tempo)`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import pytest

from nucleo.piezas.modelo import (
    NotaEnPieza,
    Pieza,
    pulsos_a_segundos,
    segundos_a_pulsos,
)


def nota(midi=40, cuerda=6, traste=0, inicio=0.0, duracion=1.0) -> NotaEnPieza:
    return NotaEnPieza(
        midi=midi, cuerda=cuerda, traste=traste,
        inicio_pulsos=inicio, duracion_pulsos=duracion,
    )


def pieza(notas, tempo=60) -> Pieza:
    return Pieza(
        nombre="prueba", perfil="guitarra_estandar", tempo=tempo,
        compas=(4, 4), notas=tuple(notas),
    )


def test_a_60_ppm_un_pulso_es_un_segundo():
    assert pulsos_a_segundos(1.0, 60) == pytest.approx(1.0)
    assert pulsos_a_segundos(4.0, 120) == pytest.approx(2.0)


def test_la_conversion_es_reversible():
    assert segundos_a_pulsos(pulsos_a_segundos(3.5, 90), 90) == pytest.approx(3.5)


def test_un_tempo_imposible_se_rechaza():
    """Un tempo de cero o negativo no convierte nada: dividir por el explotaria
    mucho mas lejos y con un traceback en vez de un mensaje."""
    with pytest.raises(ValueError, match="tempo"):
        pulsos_a_segundos(1.0, 0)


def test_la_duracion_es_la_del_final_de_la_ultima_nota():
    """No la suma de las duraciones: las notas pueden solaparse o dejar huecos."""
    p = pieza([nota(inicio=0.0, duracion=1.0), nota(inicio=3.0, duracion=2.0)])
    assert p.duracion_pulsos == pytest.approx(5.0)
    assert p.duracion_s == pytest.approx(5.0)  # 60 ppm


def test_las_notas_tienen_que_venir_ordenadas():
    """El carril recorre la pieza hacia delante; desordenada lo rompe en silencio."""
    with pytest.raises(ValueError, match="orden"):
        pieza([nota(inicio=2.0), nota(inicio=1.0)])


def test_una_duracion_no_positiva_se_rechaza():
    with pytest.raises(ValueError, match="duracion"):
        pieza([nota(duracion=0.0)])


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        Pieza(nombre="x", perfil="ukelele", tempo=60, compas=(4, 4), notas=())


def test_a_dict_publica_todo_lo_que_la_interfaz_necesita():
    p = pieza([nota(midi=45, cuerda=5, traste=0, inicio=0.0, duracion=2.0)])
    d = p.a_dict()
    assert d["tempo"] == 60
    assert d["compas"] == [4, 4]
    assert d["duracion_pulsos"] == pytest.approx(2.0)
    assert d["notas"][0] == {
        "midi": 45, "nombre": "A2", "cuerda": 5, "traste": 0,
        "inicio_pulsos": 0.0, "duracion_pulsos": 2.0,
    }


def test_una_pieza_vacia_dura_cero_y_no_revienta():
    assert pieza([]).duracion_pulsos == 0.0
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_modelo_piezas.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'nucleo.piezas'`

- [ ] **Step 3: Implementa el modelo**

`nucleo/piezas/__init__.py` va vacío. En `nucleo/piezas/modelo.py`:

```python
"""Una pieza: notas con sitio en el mastil y sitio en el tiempo.

A diferencia de `Ejercicio`, que da TODAS las posiciones donde vive cada nota y
deja que el alumno elija, aqui cada nota trae UNA: el carril tiene que dibujarla
en algun sitio. Y a diferencia de el, el tiempo es absoluto.

El tiempo se guarda en PULSOS y no en segundos para que bajar el tempo y
practicar lento sea cambiar un numero, y no reescribir la pieza entera.

Este modulo no importa nada de `nucleo.ejercicios`: una pieza leida de un archivo
de Guitar Pro no tiene nada que ver con un ejercicio generado. El unico puente
entre ambos vive en `desde_ejercicio.py`.
"""

from dataclasses import dataclass

from nucleo.afinaciones import PERFILES
from nucleo.musica import nombre_de_midi


def pulsos_a_segundos(pulsos: float, tempo: int) -> float:
    """Pulsos a segundos: segundos = pulsos * 60 / tempo."""
    if tempo <= 0:
        raise ValueError(f"El tempo {tempo} no sirve: tiene que ser mayor que cero")
    return pulsos * 60.0 / tempo


def segundos_a_pulsos(segundos: float, tempo: int) -> float:
    """La inversa de `pulsos_a_segundos`."""
    if tempo <= 0:
        raise ValueError(f"El tempo {tempo} no sirve: tiene que ser mayor que cero")
    return segundos * tempo / 60.0


@dataclass(frozen=True)
class NotaEnPieza:
    """Una nota con cuerda, traste, instante y duracion."""

    midi: int
    cuerda: int
    traste: int
    inicio_pulsos: float
    duracion_pulsos: float

    @property
    def fin_pulsos(self) -> float:
        return self.inicio_pulsos + self.duracion_pulsos

    def a_dict(self) -> dict:
        return {
            "midi": self.midi,
            "nombre": nombre_de_midi(self.midi),
            "cuerda": self.cuerda,
            "traste": self.traste,
            "inicio_pulsos": self.inicio_pulsos,
            "duracion_pulsos": self.duracion_pulsos,
        }


@dataclass(frozen=True)
class Pieza:
    """Notas ordenadas en el tiempo, con la afinacion con que se escribieron."""

    nombre: str
    perfil: str
    tempo: int
    compas: tuple[int, int]
    notas: tuple[NotaEnPieza, ...]

    def __post_init__(self) -> None:
        if self.perfil not in PERFILES:
            disponibles = ", ".join(sorted(PERFILES))
            raise ValueError(f"El perfil '{self.perfil}' no existe. Opciones: {disponibles}")
        pulsos_a_segundos(1.0, self.tempo)  # valida el tempo con el mismo mensaje
        anterior = None
        for nota in self.notas:
            if nota.duracion_pulsos <= 0:
                raise ValueError(
                    f"La nota {nombre_de_midi(nota.midi)} tiene duracion "
                    f"{nota.duracion_pulsos}: tiene que ser mayor que cero"
                )
            if anterior is not None and nota.inicio_pulsos < anterior:
                raise ValueError(
                    "Las notas tienen que venir en orden de inicio_pulsos: "
                    f"{nota.inicio_pulsos} llega despues de {anterior}"
                )
            anterior = nota.inicio_pulsos

    def __len__(self) -> int:
        return len(self.notas)

    @property
    def duracion_pulsos(self) -> float:
        """Hasta donde llega la pieza, no cuanto suena.

        Es el final de la ultima nota, no la suma de las duraciones: las notas
        pueden dejar huecos entre si.
        """
        return max((nota.fin_pulsos for nota in self.notas), default=0.0)

    @property
    def duracion_s(self) -> float:
        return pulsos_a_segundos(self.duracion_pulsos, self.tempo)

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "perfil": self.perfil,
            "tempo": self.tempo,
            "compas": list(self.compas),
            "duracion_pulsos": self.duracion_pulsos,
            "notas": [nota.a_dict() for nota in self.notas],
        }
```

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_modelo_piezas.py -q`
Expected: PASS, 9 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas tests/test_modelo_piezas.py
git commit -m "feat: el modelo Pieza, con tiempo absoluto en pulsos"
```

---

### Task 2: De ejercicio a pieza, eligiendo dónde se toca

**Files:**
- Create: `nucleo/piezas/desde_ejercicio.py`
- Test: `tests/test_pieza_desde_ejercicio.py`

**Interfaces:**
- Consumes: `Pieza`, `NotaEnPieza` (Task 1); `Ejercicio`, `NotaEsperada` de
  `nucleo/ejercicios/modelo.py`; `Posicion(cuerda, traste)` de `nucleo/musica.py`.
- Produces: `pieza_desde_ejercicio(ejercicio) -> Pieza`,
  `elegir_posicion(posiciones, traste_anterior) -> Posicion`.

`Ejercicio` tiene `clave`, `nombre`, `descripcion`, `notas`, `tempo`, `perfil`.
`NotaEsperada` tiene `midi`, `posiciones: tuple[Posicion, ...]`, `pulsos`,
`referencia_midi`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import pytest

from nucleo.ejercicios.generadores.escalas import generar_escala
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.musica import Posicion
from nucleo.piezas.desde_ejercicio import elegir_posicion, pieza_desde_ejercicio


def ejercicio(notas, tempo=80) -> Ejercicio:
    return Ejercicio(
        clave="prueba", nombre="Prueba", descripcion="",
        notas=tuple(notas), tempo=tempo, perfil="guitarra_estandar",
    )


def test_los_instantes_se_acumulan_con_los_pulsos_de_cada_nota():
    e = ejercicio([
        NotaEsperada(midi=40, posiciones=(Posicion(cuerda=6, traste=0),), pulsos=1.0),
        NotaEsperada(midi=42, posiciones=(Posicion(cuerda=6, traste=2),), pulsos=2.0),
        NotaEsperada(midi=44, posiciones=(Posicion(cuerda=6, traste=4),), pulsos=1.0),
    ])
    p = pieza_desde_ejercicio(e)
    assert [n.inicio_pulsos for n in p.notas] == [0.0, 1.0, 3.0]
    assert [n.duracion_pulsos for n in p.notas] == [1.0, 2.0, 1.0]


def test_se_elige_la_posicion_mas_cercana_al_traste_anterior():
    """Un La de 110 Hz esta en la quinta al aire y en el sexto traste de la sexta.
    Tocando por el traste cinco, la segunda es la que la mano ya tiene debajo."""
    anterior = Posicion(cuerda=6, traste=5)
    opciones = (Posicion(cuerda=5, traste=0), Posicion(cuerda=6, traste=6))
    assert elegir_posicion(opciones, anterior.traste) == Posicion(cuerda=6, traste=6)


def test_a_igualdad_de_distancia_gana_la_cuerda_mas_grave():
    opciones = (Posicion(cuerda=3, traste=4), Posicion(cuerda=5, traste=6))
    assert elegir_posicion(opciones, 5).cuerda == 5


def test_la_primera_nota_toma_el_traste_mas_bajo():
    """Sin nota anterior no hay cercania que medir, y empezar abajo es lo natural."""
    opciones = (Posicion(cuerda=5, traste=7), Posicion(cuerda=6, traste=0))
    assert elegir_posicion(opciones, None) == Posicion(cuerda=6, traste=0)


def test_una_nota_sin_posiciones_es_un_error_de_programacion():
    e = ejercicio([NotaEsperada(midi=40, posiciones=(), pulsos=1.0)])
    with pytest.raises(ValueError, match="E2"):
        pieza_desde_ejercicio(e)


def test_la_pieza_hereda_nombre_tempo_y_perfil_del_ejercicio():
    e = ejercicio([NotaEsperada(midi=40, posiciones=(Posicion(cuerda=6, traste=0),))], tempo=95)
    p = pieza_desde_ejercicio(e)
    assert p.tempo == 95
    assert p.perfil == "guitarra_estandar"
    assert p.nombre == "Prueba"


def test_una_escala_en_una_posicion_no_salta_por_el_mastil():
    """La heuristica es local y en una pieza de verdad no bastaria, pero sobre una
    escala en cuatro trastes tiene que dar una digitacion tocable: ninguna nota
    debe obligar a mover la mano mas de cuatro trastes respecto a la anterior."""
    e = generar_escala(raiz_midi=48, tipo="mayor", traste_minimo=0, traste_maximo=4)
    p = pieza_desde_ejercicio(e)
    trastes = [n.traste for n in p.notas if n.traste > 0]
    assert max(trastes) - min(trastes) <= 4
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_pieza_desde_ejercicio.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implementa el conversor**

```python
"""El unico puente entre un ejercicio y una pieza.

Vive aparte del modelo a proposito: en la etapa 3b tendra al lado un
`desde_guitarpro.py` y un `desde_musicxml.py`, y `modelo.py` no tiene por que
enterarse de ninguno de los tres.
"""

from nucleo.ejercicios.modelo import Ejercicio
from nucleo.musica import Posicion, nombre_de_midi
from nucleo.piezas.modelo import NotaEnPieza, Pieza


def elegir_posicion(
    posiciones: tuple[Posicion, ...], traste_anterior: int | None
) -> Posicion:
    """Donde tocar una nota que vive en varios sitios del mastil.

    HEURISTICA LOCAL, y hay que decirlo: se queda con la posicion cuyo traste
    esta mas cerca del de la nota anterior, sin mirar lo que viene despues. Sobre
    una escala en una posicion acierta siempre, porque todas las notas caben en
    cuatro trastes. Sobre una pieza de verdad producira saltos absurdos: la
    eleccion correcta es la que minimiza el movimiento de la mano a lo largo de
    TODA la pieza, que es un camino de coste minimo y es trabajo de la etapa 3b.

    A igualdad de distancia gana la cuerda mas grave: en esa zona del mastil la
    nota suena mas llena y es donde la mano suele estar.
    """
    if not posiciones:
        raise ValueError("No hay ninguna posicion que elegir")
    if traste_anterior is None:
        return min(posiciones, key=lambda p: (p.traste, -p.cuerda))
    return min(posiciones, key=lambda p: (abs(p.traste - traste_anterior), -p.cuerda))


def pieza_desde_ejercicio(ejercicio: Ejercicio) -> Pieza:
    """Traduce un ejercicio a una pieza, acumulando los pulsos y fijando posicion."""
    notas: list[NotaEnPieza] = []
    inicio = 0.0
    traste_anterior: int | None = None
    for esperada in ejercicio.notas:
        if not esperada.posiciones:
            raise ValueError(
                f"La nota {nombre_de_midi(esperada.midi)} no tiene ninguna posicion "
                "alcanzable: el generador no deberia haberla producido"
            )
        posicion = elegir_posicion(esperada.posiciones, traste_anterior)
        notas.append(
            NotaEnPieza(
                midi=esperada.midi,
                cuerda=posicion.cuerda,
                traste=posicion.traste,
                inicio_pulsos=inicio,
                duracion_pulsos=esperada.pulsos,
            )
        )
        inicio += esperada.pulsos
        traste_anterior = posicion.traste
    return Pieza(
        nombre=ejercicio.nombre,
        perfil=ejercicio.perfil,
        tempo=ejercicio.tempo,
        compas=(4, 4),
        notas=tuple(notas),
    )
```

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_pieza_desde_ejercicio.py -q`
Expected: PASS, 7 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/desde_ejercicio.py tests/test_pieza_desde_ejercicio.py
git commit -m "feat: convertir un ejercicio en pieza eligiendo donde se toca"
```

---

### Task 3: Extraer `DetectorPulsaciones` del evaluador

**Files:**
- Create: `nucleo/ejercicios/pulsaciones.py`
- Modify: `nucleo/ejercicios/evaluacion.py`
- Test: `tests/test_pulsaciones.py`

**Interfaces:**
- Consumes: `DetectorAtaques` de `nucleo/ejercicios/ataques.py`,
  `ResultadoAnalisis` de `nucleo/analisis/pipeline.py`.
- Produces: `Pulsacion(nota, cents, instante)`,
  `DetectorPulsaciones.procesar(resultado, instante) -> Pulsacion | None`,
  `DetectorPulsaciones.senal_de_nota_nueva -> bool`.

**Esto es una refactorización de código que costó tres rondas de correcciones.**
Las 376 pruebas actuales son la red: **ninguna puede cambiar en esta tarea**. Si
alguna falla, el comportamiento cambió y hay que volver atrás, no ajustar la
prueba. Lee entero el docstring de `EvaluadorEjercicio` antes de tocar nada.

Se mueve a `DetectorPulsaciones`, tal cual: el detector de ataques y la lectura
diferida (camino A), el seguimiento de la nota estable (camino B), `_es_creible`,
el filtro contra `_ultima_nota_resuelta`, el contador de cuadros sin nota creíble
que lo libera, y `_onset_camino_b` con su ventana.

Se queda en `EvaluadorEjercicio`: comparar con la nota esperada, contar intentos,
la ayuda, el informe y el reloj de `segundos_para_ayuda`.

- [ ] **Step 1: Escribe las pruebas de la unidad extraída**

```python
import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones

PASO = 0.021


def suena(nota="E2", nivel=-25.0, confianza=0.9, cents=0.0) -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=confianza, nivel_db=nivel,
        nota=nota, cents=cents, posiciones=(),
    )


def silencio() -> ResultadoAnalisis:
    return ResultadoAnalisis(
        estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
        nota=None, cents=None, posiciones=(),
    )


def correr(detector, cuadros, instante=0.0):
    """Pasa una lista de resultados y devuelve las pulsaciones que salieron."""
    salidas = []
    for resultado in cuadros:
        pulsacion = detector.procesar(resultado, instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO
    return salidas


def test_una_pulsacion_limpia_da_una_sola_salida():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena()] * 12)
    assert len(salidas) == 1
    assert salidas[0].nota == "E2"


def test_la_cola_de_la_nota_no_produce_una_segunda():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(nivel=n) for n in range(-25, -5)])
    assert len(salidas) == 1


def test_un_ataque_sin_nota_creible_no_produce_nada():
    """Regla 1: un golpe en la caja o una cuerda apagada no es un intento."""
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(confianza=0.2)] * 12)
    assert salidas == []


def test_tras_un_hueco_la_misma_nota_vuelve_a_contar():
    detector = DetectorPulsaciones()
    cuadros = [silencio()] * 6 + [suena()] * 10 + [silencio()] * 6 + [suena()] * 10
    assert len(correr(detector, cuadros)) == 2


def test_la_pulsacion_trae_los_cents_de_lo_que_sono():
    detector = DetectorPulsaciones()
    salidas = correr(detector, [silencio()] * 6 + [suena(cents=-14.0)] * 12)
    assert salidas[0].cents == pytest.approx(-14.0)


def test_el_instante_es_el_del_ataque_no_el_de_la_lectura():
    """El ataque de energia marca cuando empezo la nota; la lectura del tono llega
    despues. Anotar la lectura convertiria el retraso del detector en desfase del
    alumno."""
    detector = DetectorPulsaciones()
    instante = 0.0
    for _ in range(6):
        detector.procesar(silencio(), instante)
        instante += PASO
    inicio = instante
    salidas = []
    for _ in range(12):
        pulsacion = detector.procesar(suena(), instante)
        if pulsacion is not None:
            salidas.append(pulsacion)
        instante += PASO
    assert salidas[0].instante == pytest.approx(inicio, abs=PASO)


def test_senal_de_nota_nueva_distingue_la_cola_de_un_intento():
    """Lo que la regla de la ayuda por tiempo necesita: senal creible que NO sea
    la nota que se acaba de resolver."""
    detector = DetectorPulsaciones()
    correr(detector, [silencio()] * 6 + [suena()] * 12)
    detector.procesar(suena(), 1.0)          # cola de la misma nota
    assert detector.senal_de_nota_nueva is False
    detector.procesar(suena(nota="A2"), 1.1)  # otra nota: eso si es un intento
    assert detector.senal_de_nota_nueva is True
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_pulsaciones.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'nucleo.ejercicios.pulsaciones'`

- [ ] **Step 3: Mueve la lógica, sin cambiarla**

Crea `nucleo/ejercicios/pulsaciones.py` con `Pulsacion` y `DetectorPulsaciones`,
trasladando desde `evaluacion.py` los métodos `_es_creible`,
`_actualizar_candidata`, `_onset_camino_b` y la parte de `procesar` que decide
que hubo una pulsación, junto con sus constantes y **sus comentarios**, que
explican por qué cada guarda existe.

```python
@dataclass(frozen=True)
class Pulsacion:
    """Una nota que el alumno toco, con cuando empezo y como de afinada iba."""

    nota: str
    cents: float | None
    instante: float


class DetectorPulsaciones:
    """Que nota se toco y cuando, sin saber nada de ejercicios ni de piezas.

    Es la mitad de abajo del evaluador de ejercicios, extraida para que el carril
    la use sin duplicarla. La mitad de arriba -comparar con lo que tocaba,
    contar intentos, ayudar- se queda en quien la use, porque no es la misma en
    los dos modos: en un ejercicio la nota espera a que la aciertes y en una
    pieza la musica sigue.
    """

    def __init__(
        self,
        detector_ataques: DetectorAtaques | None = None,
        confianza_minima: float = CONFIANZA_MINIMA,
        espera_estabilizacion_s: float = ESPERA_ESTABILIZACION_S,
        cuadros_para_nota_estable: int = CUADROS_PARA_NOTA_ESTABLE,
        cuadros_para_olvidar_nota: int = CUADROS_PARA_OLVIDAR_NOTA,
    ) -> None:
        # Mismos campos que hoy tiene EvaluadorEjercicio para esta mitad:
        # _detector, _lectura_pendiente, _instante_ataque, _nota_candidata,
        # _contador_candidata, _instante_inicio_candidata, _ultima_nota_resuelta,
        # _cuadros_sin_nota_creible. Se mueven tal cual, con sus comentarios.

    @property
    def senal_de_nota_nueva(self) -> bool:
        """Si el ultimo cuadro traia senal que podria ser una pulsacion nueva."""

    def procesar(self, resultado, instante: float) -> Pulsacion | None:
        """Devuelve la pulsacion detectada en este cuadro, o None."""
```

Después reescribe `EvaluadorEjercicio` para que delegue: su `procesar` pide una
pulsación al detector y, si la hay, aplica sus reglas sobre la nota esperada.
`_hubo_senal_creible_nota_actual` pasa a leerse de `senal_de_nota_nueva`.

- [ ] **Step 4: Comprueba que TODO pasa, lo nuevo y lo viejo**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS. Las pruebas de `tests/test_evaluacion.py` **no se han tocado** y
siguen pasando: eso es lo que demuestra que el comportamiento no cambió.

- [ ] **Step 5: Commit**

```bash
git add nucleo/ejercicios/pulsaciones.py nucleo/ejercicios/evaluacion.py tests/test_pulsaciones.py
git commit -m "refactor: extraer DetectorPulsaciones del evaluador de ejercicios"
```

---

### Task 4: `SeguidorPieza` — el reloj manda, no los aciertos

**Files:**
- Create: `nucleo/piezas/seguimiento.py`
- Test: `tests/test_seguimiento_pieza.py`

**Interfaces:**
- Consumes: `Pieza`, `NotaEnPieza` (Task 1); `DetectorPulsaciones`, `Pulsacion`
  (Task 3); `pulsos_a_segundos` (Task 1).
- Produces: `VENTANA_A_TIEMPO_S = 0.080`,
  `NotaTocada(indice, midi, cents, desfase_s, clasificacion, acertada)`,
  `EstadoCarril(instante_s, indice_actual, total, completado, tocadas)`,
  `SeguidorPieza(pieza, detector=None, ventana_a_tiempo_s=...)` con
  `procesar(resultado, instante_analisis) -> EstadoCarril`,
  `avanzar_a(instante_s) -> EstadoCarril` y `estado -> EstadoCarril`.

`clasificacion` es `"a_tiempo" | "pronto" | "tarde"`. `desfase_s` es negativo si
se tocó antes de tiempo.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from nucleo.piezas.seguimiento import VENTANA_A_TIEMPO_S, SeguidorPieza


def pieza_de(midis, tempo=60):
    """Una nota por pulso: a 60 ppm, una por segundo."""
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=6, traste=i, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i, m in enumerate(midis)
    )
    return Pieza(nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas)


def suena(nota, nivel=-25.0, confianza=0.9, cents=0.0):
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=confianza, nivel_db=nivel,
        nota=nota, cents=cents, posiciones=(),
    )


def test_la_nota_en_curso_la_decide_el_reloj():
    seguidor = SeguidorPieza(pieza_de([40, 45, 50]))
    assert seguidor.avanzar_a(0.1).indice_actual == 0
    assert seguidor.avanzar_a(1.2).indice_actual == 1
    assert seguidor.avanzar_a(2.5).indice_actual == 2


def test_la_pieza_avanza_aunque_falles():
    """Lo contrario que un ejercicio por turnos: la musica no espera."""
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    assert seguidor.avanzar_a(1.5).indice_actual == 1
    assert seguidor.estado.tocadas == ()


def test_al_pasar_del_final_la_pieza_esta_completada():
    seguidor = SeguidorPieza(pieza_de([40]))
    assert seguidor.avanzar_a(0.5).completado is False
    assert seguidor.avanzar_a(1.5).completado is True


def test_una_nota_en_su_instante_va_a_tiempo():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "E2", en=1.0)
    assert tocada.clasificacion == "a_tiempo"
    assert tocada.desfase_s == pytest.approx(0.0, abs=0.03)


def test_una_nota_adelantada_se_marca_pronto_con_su_desfase():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "E2", en=1.0 - 0.3)
    assert tocada.clasificacion == "pronto"
    assert tocada.desfase_s < -VENTANA_A_TIEMPO_S


def test_una_nota_atrasada_se_marca_tarde():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "E2", en=1.0 + 0.3)
    assert tocada.clasificacion == "tarde"
    assert tocada.desfase_s > VENTANA_A_TIEMPO_S


def test_fuera_de_ventana_pero_correcta_sigue_siendo_acertada():
    """El ritmo informa, no descalifica: la misma regla que la afinacion."""
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "E2", en=1.0 + 0.4)
    assert tocada.midi == 40
    assert tocada.cents is not None


def test_los_cents_de_la_pulsacion_llegan_al_estado():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "E2", en=1.0, cents=-12.0)
    assert tocada.cents == pytest.approx(-12.0)


def test_una_nota_equivocada_no_cuenta_como_la_esperada():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocada = tocar(seguidor, "A2", en=1.0)
    assert tocada.midi != 40
    assert tocada.clasificacion in ("a_tiempo", "pronto", "tarde")
    assert tocada.acertada is False


def test_el_estado_publica_lo_mismo_que_la_interfaz_va_a_pintar():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    d = seguidor.avanzar_a(0.5).a_dict()
    assert set(d) == {"instante_s", "indice_actual", "total", "completado", "tocadas"}
```

Añade este ayudante al principio del archivo de pruebas, debajo de `suena`:

```python
def tocar(seguidor, nota, en, cents=0.0):
    """Toca una nota alrededor del instante `en` y devuelve lo que se anoto.

    El reloj se mueve a mano: ni una espera real en toda la suite.
    """
    instante = en - 0.1
    while instante < en:
        seguidor.procesar(
            ResultadoAnalisis(
                estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
                nota=None, cents=None, posiciones=(),
            ),
            instante,
        )
        instante += 0.021
    for _ in range(12):
        seguidor.procesar(suena(nota, cents=cents), instante)
        instante += 0.021
    return seguidor.estado.tocadas[-1]
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_seguimiento_pieza.py -q`
Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implementa el seguidor**

Puntos que el implementador tiene que respetar:

- El instante del reloj de la pieza y el instante del análisis son **relojes
  distintos**: `procesar` recibe el del análisis y el seguidor guarda la
  correspondencia con el de la pieza fijada en el primer cuadro. Confundirlos
  hace que el desfase mida la antigüedad del proceso.
- Una pulsación se adjudica a la nota **más cercana en el tiempo** de entre las
  que no se han tocado aún, no a la que esté en curso: tocar un poco antes de
  tiempo es lo normal y no debe adjudicarse a la nota anterior.
- `VENTANA_A_TIEMPO_S = 0.080`. El comentario debe decir de dónde sale —por
  debajo de unos 30 ms dos ataques no se perciben separados, por encima de 100 ms
  ya se oye como error, y la latencia medida del cable es de 13,8 ms— y que **no
  está calibrado tocando**.
- `avanzar_a` no consume audio: solo mueve el reloj. Es lo que permite probar sin
  esperas y lo que el servidor llama cuando no llega señal.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_seguimiento_pieza.py -q`
Expected: PASS, 10 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/seguimiento.py tests/test_seguimiento_pieza.py
git commit -m "feat: seguir una pieza con el reloj, no con los aciertos"
```

---

### Task 5: `SesionCarril` — el reloj del servidor

**Files:**
- Create: `servidor/piezas.py`
- Modify: `servidor/modulos.py` (registrar el módulo `carril`)
- Test: `tests/test_sesion_carril.py`

**Interfaces:**
- Consumes: `SeguidorPieza`, `EstadoCarril` (Task 4); `Pieza` (Task 1);
  `pieza_desde_ejercicio` (Task 2); `Sesion.registrar_observador(cb)` y
  `quitar_observador(cb)` de `servidor/sesion.py`; `Sesion.senal_ausente`.
- Produces: `SesionCarril(sesion_audio, reloj=time.monotonic)` con
  `iniciar(pieza) -> dict`, `detener() -> None`, `estado() -> dict`,
  `activa -> bool`. El `estado()` es el `EstadoCarril.a_dict()` de la Task 4
  **más** `"pausado": bool`, que es cosa del servidor y no del núcleo: el
  seguidor no sabe nada de cables.

Copia el patrón de `servidor/ejercicios.py`, que ya resolvió estos problemas:
observadora del análisis, candado para la instantánea que lee el hilo HTTP, y
nada lento dentro del observador.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
import time

import numpy as np

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.piezas.modelo import NotaEnPieza, Pieza
from servidor.configuracion import Configuracion
from servidor.piezas import SesionCarril
from servidor.sesion import Sesion

CABLE = DispositivoAudio(3, NOMBRE_ROCKSMITH, 1, 48000.0)
FS = 48000


class CapturaFalsa:
    def __init__(self, **kwargs):
        self.ultimo_error = None
        self.latencia_ms = 12.0
        self.total_capturado = 0

    def iniciar(self) -> bool:
        return True

    def detener(self) -> None:
        pass

    def leer_ventana(self, n: int):
        self.total_capturado += n
        t = np.arange(n) / FS
        return (0.3 * np.sin(2 * np.pi * 82.41 * t)).astype(np.float32)


class RelojFalso:
    """Reloj que solo avanza cuando se le dice. Ninguna prueba espera de verdad."""

    def __init__(self):
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


def pieza_de(midis, tempo=60):
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=6, traste=i, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i, m in enumerate(midis)
    )
    return Pieza(nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=(4, 4), notas=notas)


class SesionAudioFalsa:
    """Doble de `Sesion` con `senal_ausente` mutable desde la prueba.

    El nucleo NO lleva un interruptor que solo exista para los tests: el doble
    vive aqui. `SesionCarril` solo necesita de su sesion de audio tres cosas,
    asi que el doble tiene exactamente esas tres.
    """

    def __init__(self):
        self.senal_ausente = False
        self.observadores = []

    def registrar_observador(self, observador):
        self.observadores.append(observador)

    def quitar_observador(self, observador):
        if observador in self.observadores:
            self.observadores.remove(observador)


def carril(reloj):
    sesion = SesionAudioFalsa()
    return SesionCarril(sesion, reloj=reloj), sesion


def test_iniciar_devuelve_la_pieza_entera_una_sola_vez():
    """La pieza no viaja por el WebSocket: cientos de notas 30 veces por segundo
    seria tirar el canal en datos que no cambian."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    respuesta = sesion_carril.iniciar(pieza_de([40, 45]))
    assert respuesta["pieza"]["notas"][0]["midi"] == 40
    assert "pieza" not in sesion_carril.estado()
    sesion_carril.detener()


def test_el_instante_avanza_con_el_reloj():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45]))
    assert sesion_carril.estado()["instante_s"] == 0.0
    reloj.avanzar(1.4)
    assert sesion_carril.estado()["instante_s"] == 1.4
    assert sesion_carril.estado()["indice_actual"] == 1
    sesion_carril.detener()
    sesion.detener()


def test_sin_senal_el_carril_se_detiene_y_al_volver_sigue_donde_estaba():
    """Un carril que corre con el cable desenchufado te hace fallar notas que
    nunca sonaron."""
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40, 45, 50]))
    reloj.avanzar(1.0)
    assert sesion_carril.estado()["instante_s"] == 1.0

    sesion.senal_ausente = True
    reloj.avanzar(5.0)
    assert sesion_carril.estado()["instante_s"] == 1.0
    assert sesion_carril.estado()["pausado"] is True

    sesion.senal_ausente = False
    reloj.avanzar(0.5)
    assert sesion_carril.estado()["instante_s"] == 1.5
    sesion_carril.detener()
    sesion.detener()


def test_una_pieza_en_otra_afinacion_que_la_activa_se_rechaza():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    bajo = Pieza(nombre="p", perfil="bajo_4", tempo=60, compas=(4, 4), notas=())
    try:
        with __import__("pytest").raises(ValueError, match="bajo_4"):
            sesion_carril.iniciar(bajo)
    finally:
        sesion_carril.detener()
        sesion.detener()


def test_detener_quita_el_observador_y_deja_de_avanzar():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40]))
    sesion_carril.detener()
    reloj.avanzar(3.0)
    assert sesion_carril.activa is False
    assert sesion_carril.estado()["instante_s"] == 0.0
    sesion.detener()


def test_detener_dos_veces_no_falla():
    reloj = RelojFalso()
    sesion_carril, sesion = carril(reloj)
    sesion_carril.iniciar(pieza_de([40]))
    sesion_carril.detener()
    sesion_carril.detener()
    sesion.detener()
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_sesion_carril.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'servidor.piezas'`

- [ ] **Step 3: Implementa la sesión del carril**

Requisitos del implementador:

- El reloj se **inyecta** (`reloj=time.monotonic` por defecto) para que las
  pruebas lo muevan a mano.
- La pausa por falta de señal se ajusta en `estado()` **y** en el observador, por
  la misma razón que en `servidor/ejercicios.py`: cuando el dispositivo
  desaparece, la sesión de audio publica un único silencio y deja de publicar, de
  modo que el observador ya no vuelve a correr. El WebSocket llama a `estado()` a
  30 Hz y ahí está la otra mitad.
- Al pausar se guarda el instante alcanzado; al reanudar se corre el origen del
  reloj para que el tiempo pausado no cuente. El estado publica `pausado`.
- La instantánea de `estado()` se construye entera bajo candado. En la etapa 2a
  se coló un fallo por leer dos campos sin él y devolver un estado a medias.
- **No añadas a `Sesion` ningún interruptor que solo sirva para los tests.** Las
  pruebas usan un doble (`SesionAudioFalsa`) con `senal_ausente` mutable. Eso
  obliga a que `SesionCarril` dependa solo de tres cosas de su sesión de audio
  —`senal_ausente`, `registrar_observador` y `quitar_observador`—, que es una
  frontera mejor que la que tendría si usara la clase entera.
- Registra el módulo en `servidor/modulos.py`:
  `Modulo(clave="carril", nombre="Carril", descripcion="Las notas vienen hacia ti: toca cuando llegan", icono="🛣️")`,
  con las tildes puestas, que es texto que ve el usuario.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add servidor/piezas.py servidor/modulos.py tests/test_sesion_carril.py
git commit -m "feat: la sesion del carril, con el reloj del servidor"
```

---

### Task 6: Los endpoints y el WebSocket

**Files:**
- Modify: `servidor/app.py`
- Test: `tests/test_app_carril.py`

**Interfaces:**
- Consumes: `SesionCarril` (Task 5), `pieza_desde_ejercicio` (Task 2),
  `SesionPractica.generar(familia, **parametros)` de `servidor/ejercicios.py`.
- Produces: `POST /api/piezas/desde-ejercicio`, `POST /api/piezas/iniciar`,
  `POST /api/piezas/detener`, `GET /api/piezas/estado`, `WS /ws/piezas`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```python
def test_desde_ejercicio_devuelve_una_pieza_con_cuerda_y_traste(cliente):
    respuesta = cliente.post(
        "/api/piezas/desde-ejercicio",
        json={"familia": "escala", "parametros": {"tipo": "mayor"}},
    )
    assert respuesta.status_code == 200
    pieza = respuesta.json()
    assert pieza["notas"]
    primera = pieza["notas"][0]
    assert 1 <= primera["cuerda"] <= 6
    assert primera["traste"] >= 0
    assert primera["inicio_pulsos"] == 0.0


def test_una_familia_inexistente_da_400_y_no_500(cliente):
    respuesta = cliente.post("/api/piezas/desde-ejercicio", json={"familia": "solfeo"})
    assert respuesta.status_code == 400
    assert "solfeo" in respuesta.json()["detail"]


def test_un_parametro_mal_escrito_da_400(cliente):
    respuesta = cliente.post(
        "/api/piezas/desde-ejercicio",
        json={"familia": "escala", "parametros": {"traste_minimo": "x"}},
    )
    assert respuesta.status_code == 400


def test_iniciar_devuelve_la_pieza_y_el_estado_no_la_repite(cliente):
    respuesta = cliente.post(
        "/api/piezas/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 3}},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["pieza"]["notas"]
    estado = cliente.get("/api/piezas/estado").json()
    assert "pieza" not in estado
    assert estado["indice_actual"] == 0
    cliente.post("/api/piezas/detener")


def test_el_estado_trae_el_instante_para_que_el_navegador_interpole(cliente):
    cliente.post("/api/piezas/iniciar", json={"familia": "lectura", "parametros": {"repeticiones": 2}})
    estado = cliente.get("/api/piezas/estado").json()
    assert "instante_s" in estado
    assert "pausado" in estado
    cliente.post("/api/piezas/detener")


def test_el_modulo_carril_aparece_junto_a_los_otros(cliente):
    claves = [m["clave"] for m in cliente.get("/api/modulos").json()]
    assert {"afinador", "ejercicios", "carril"} <= set(claves)
```

Reutiliza el `cliente` de `tests/test_app_ejercicios.py`: mismo doble de captura,
misma `SalidaAudio` con stream falso.

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_app_carril.py -q`
Expected: FAIL con 404 en todas las rutas nuevas.

- [ ] **Step 3: Implementa los endpoints**

- `desde-ejercicio` e `iniciar` generan el ejercicio con el mismo `_generar_o_400`
  que ya existe —captura `ValueError` **y** `TypeError`— y lo convierten con
  `pieza_desde_ejercicio`.
- El WebSocket `/ws/piezas` emite `app.state.carril.estado()` a la misma
  frecuencia que los otros (`FRECUENCIA_EMISION`), y **no incluye la pieza**.
- `crear_app` acepta `carril=None` y construye una `SesionCarril` por defecto,
  igual que hace con `practica`.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, toda la suite.

- [ ] **Step 5: Commit**

```bash
git add servidor/app.py tests/test_app_carril.py
git commit -m "feat: endpoints y websocket del carril"
```

---

### Task 7: El reloj del navegador

**Files:**
- Create: `interfaz/src/relojCarril.ts`
- Test: `interfaz/src/relojCarril.test.ts`

**Interfaces:**
- Consumes: nada.
- Produces: `crearReloj(opciones?) -> Reloj` con
  `Reloj.sincronizar(instanteServidor: number, ahoraLocal: number): void`,
  `Reloj.instante(ahoraLocal: number): number`, y las constantes
  `DERIVA_MAXIMA_SUAVE_S = 0.03` y `CUADROS_DE_CORRECCION = 10`.

Módulo **puro**: el tiempo entra por parámetro, nunca llama a `performance.now()`.
Eso es lo que permite probarlo con números y sin esperas.

- [ ] **Step 1: Escribe las pruebas que fallan**

```typescript
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
```

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test relojCarril`
Expected: FAIL, no existe `./relojCarril`.

- [ ] **Step 3: Implementa el reloj**

```typescript
/** Instante de la pieza entre paquetes del servidor.
 *
 * El servidor manda la verdad treinta veces por segundo; el navegador dibuja
 * sesenta. Este módulo rellena el hueco: guarda el último instante conocido con
 * el momento local en que llegó, y suma el tiempo transcurrido desde entonces.
 *
 * Nunca inventa tiempo propio: en cuanto llega un paquete nuevo, ese manda. Si
 * el carril llevara su reloj, lo que ves y lo que se te puntúa se separarían
 * poco a poco, que es peor que no tener carril.
 */

/** Por encima de esta deriva se corrige de golpe en vez de repartirla. */
export const DERIVA_MAXIMA_SUAVE_S = 0.03;

/** En cuántos cuadros se reparte una deriva pequeña. */
export const CUADROS_DE_CORRECCION = 10;
```

El implementador decide la estructura interna, respetando las pruebas y la
propiedad de no retroceder nunca.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test relojCarril`
Expected: PASS, 6 pruebas.

- [ ] **Step 5: Commit**

```bash
git add interfaz/src/relojCarril.ts interfaz/src/relojCarril.test.ts
git commit -m "feat: el reloj del carril interpola entre paquetes sin derivar"
```

---

### Task 8: La geometría del carril

**Files:**
- Create: `interfaz/src/geometriaCarril.ts`
- Test: `interfaz/src/geometriaCarril.test.ts`

**Interfaces:**
- Consumes: el tipo `NotaDePieza` (lo define esta tarea en
  `interfaz/src/tiposPieza.ts`), con `midi`, `nombre`, `cuerda`, `traste`,
  `inicio_pulsos`, `duracion_pulsos`.
- Produces: `VENTANA_VISIBLE_S = 4.0`,
  `notasVisibles(notas, instanteS, tempo, ventanaS) -> NotaVisible[]`,
  `rectanguloDeNota(nota, instanteS, tempo, lienzo) -> {x, y, ancho, alto}`,
  `colorDeDesviacion(cents) -> string`.

Todo **puro**. Ni canvas, ni React, ni `document`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```typescript
import { describe, expect, it } from "vitest";
import {
  colorDeDesviacion,
  notasVisibles,
  rectanguloDeNota,
  VENTANA_VISIBLE_S,
} from "./geometriaCarril";

const LIENZO = { ancho: 600, alto: 400, cuerdas: 6 };

function nota(inicio: number, cuerda = 6, duracion = 1) {
  return { midi: 40, nombre: "E2", cuerda, traste: 0,
           inicio_pulsos: inicio, duracion_pulsos: duracion };
}

describe("geometría del carril", () => {
  it("solo entran las notas de la ventana visible", () => {
    const notas = [nota(0), nota(2), nota(10)];
    const visibles = notasVisibles(notas, 0, 60, VENTANA_VISIBLE_S);
    expect(visibles.map((n) => n.inicio_pulsos)).toEqual([0, 2]);
  });

  it("una nota que ya pasó deja de estar visible", () => {
    const visibles = notasVisibles([nota(0)], 3.0, 60, VENTANA_VISIBLE_S);
    expect(visibles).toHaveLength(0);
  });

  it("la nota que suena ahora está en la línea de ataque", () => {
    const rect = rectanguloDeNota(nota(2), 2.0, 60, LIENZO);
    expect(rect.y).toBeCloseTo(LIENZO.alto, 0);
  });

  it("una nota futura está más arriba cuanto más lejos", () => {
    const cerca = rectanguloDeNota(nota(2), 1.5, 60, LIENZO);
    const lejos = rectanguloDeNota(nota(4), 1.5, 60, LIENZO);
    expect(lejos.y).toBeLessThan(cerca.y);
  });

  it("cada cuerda tiene su carril y la sexta va a un lado fijo", () => {
    const sexta = rectanguloDeNota(nota(0, 6), 0, 60, LIENZO);
    const primera = rectanguloDeNota(nota(0, 1), 0, 60, LIENZO);
    expect(sexta.x).not.toBeCloseTo(primera.x, 0);
    expect(sexta.x).toBeGreaterThanOrEqual(0);
    expect(primera.x + primera.ancho).toBeLessThanOrEqual(LIENZO.ancho);
  });

  it("el alto de la nota es su duración", () => {
    const corta = rectanguloDeNota(nota(2, 6, 1), 2.0, 60, LIENZO);
    const larga = rectanguloDeNota(nota(2, 6, 2), 2.0, 60, LIENZO);
    expect(larga.alto).toBeGreaterThan(corta.alto);
  });

  it("al doble de tempo, la misma nota llega en la mitad de tiempo", () => {
    const a60 = rectanguloDeNota(nota(2), 0, 60, LIENZO);
    const a120 = rectanguloDeNota(nota(2), 0, 120, LIENZO);
    expect(a120.y).toBeGreaterThan(a60.y);
  });

  it("el color distingue afinada, alta y baja, y null no es cero", () => {
    // cents null significa NO tocada; cero significa perfectamente afinada.
    expect(colorDeDesviacion(0)).not.toBe(colorDeDesviacion(30));
    expect(colorDeDesviacion(30)).not.toBe(colorDeDesviacion(-30));
    expect(colorDeDesviacion(null)).not.toBe(colorDeDesviacion(0));
  });
});
```

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test geometriaCarril`
Expected: FAIL, no existe el módulo.

- [ ] **Step 3: Implementa la geometría**

Crea también `interfaz/src/tiposPieza.ts` con `NotaDePieza`, `Pieza` y
`EstadoCarril`, reflejando **exactamente** lo que publica el servidor. Nada de
recalcular aquí lo que el núcleo ya decidió: la clasificación de cada nota tocada
viene dada, no se deduce del desfase.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test geometriaCarril`
Expected: PASS, 8 pruebas.

- [ ] **Step 5: Commit**

```bash
git add interfaz/src/geometriaCarril.ts interfaz/src/geometriaCarril.test.ts interfaz/src/tiposPieza.ts
git commit -m "feat: la geometria del carril, pura y sin canvas"
```

---

### Task 9: El carril en pantalla

**Files:**
- Create: `interfaz/src/Carril.tsx`, `interfaz/src/useCarril.ts`
- Modify: `interfaz/src/App.tsx` (encaminar el módulo `carril`)
- Test: `interfaz/src/Carril.test.tsx`

**Interfaces:**
- Consumes: `crearReloj` (Task 7), `notasVisibles`, `rectanguloDeNota`,
  `colorDeDesviacion` (Task 8), los endpoints de la Task 6.
- Produces: el componente `Carril`.

- [ ] **Step 1: Escribe las pruebas que fallan**

```typescript
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Carril } from "./Carril";

describe("Carril", () => {
  beforeEach(() => vi.stubGlobal("WebSocket", WebSocketFalso));
  afterEach(() => vi.unstubAllGlobals());

  it("pide una pieza al servidor y la arranca", async () => {
    const fetchFalso = crearFetchFalso();
    vi.stubGlobal("fetch", fetchFalso);
    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    await waitFor(() =>
      expect(
        fetchFalso.mock.calls.some(([url]) => url === "/api/piezas/iniciar")
      ).toBe(true)
    );
  });

  it("no pinta nada hasta que hay pieza", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    expect(screen.queryByTestId("lienzo-carril")).toBeNull();
  });

  it("avisa cuando el carril está pausado por falta de señal", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    enviarEstado({ instante_s: 1.0, indice_actual: 0, total: 3, completado: false,
                   pausado: true, tocadas: [] });
    expect(await screen.findByText(/pausado/i)).toBeTruthy();
  });

  it("al terminar muestra el resumen con los desfases", async () => {
    vi.stubGlobal("fetch", crearFetchFalso());
    render(<Carril />);
    fireEvent.click(await screen.findByRole("button", { name: /empezar/i }));
    enviarEstado({
      instante_s: 4.0, indice_actual: 3, total: 3, completado: true, pausado: false,
      tocadas: [
        { indice: 0, midi: 40, cents: -5.0, desfase_s: 0.01, clasificacion: "a_tiempo", acertada: true },
        { indice: 1, midi: 45, cents: 3.0, desfase_s: 0.22, clasificacion: "tarde", acertada: true },
      ],
    });
    expect(await screen.findByText(/a tiempo/i)).toBeTruthy();
    expect(await screen.findByText(/tarde/i)).toBeTruthy();
  });
});
```

Copia `WebSocketFalso` y el patrón de `enviarEstado` de
`interfaz/src/Ejercicios.test.tsx`, que ya resolvió esto.

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test Carril`
Expected: FAIL, no existe `./Carril`.

- [ ] **Step 3: Implementa el componente**

- `useCarril.ts` abre el WebSocket, guarda el estado y **sincroniza el reloj** con
  cada paquete usando `performance.now()`. Es el único sitio que llama a
  `performance.now()`.
- `Carril.tsx` pinta en `<canvas data-testid="lienzo-carril">` dentro de un bucle
  de `requestAnimationFrame`, que **se cancela al desmontar**: un bucle que
  sobrevive al componente sigue dibujando sobre un canvas que ya no existe.
- El canvas se dimensiona con `devicePixelRatio` para que no se vea borroso en
  pantallas Retina.
- En jsdom no hay canvas de verdad: las pruebas comprueban el cableado y el
  texto, no el dibujo. El dibujo se juzga mirándolo.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test && pnpm build && pnpm lint`
Expected: PASS y build limpio.

- [ ] **Step 5: Commit**

```bash
git add interfaz/src/Carril.tsx interfaz/src/useCarril.ts interfaz/src/Carril.test.tsx interfaz/src/App.tsx
git commit -m "feat: el carril en pantalla, dibujado en canvas a 60 fps"
```

---

### Task 10: La vista escrita: tablatura y pentagrama

**Files:**
- Create: `interfaz/src/vistaEscrita.ts`, `interfaz/src/VistaEscrita.tsx`
- Modify: `interfaz/src/Carril.tsx` (alternar entre carril y vista escrita)
- Test: `interfaz/src/vistaEscrita.test.ts`

**Interfaces:**
- Consumes: `NotaDePieza`, `Pieza` de `tiposPieza.ts` (Task 8).
- Produces: `compasesDe(pieza) -> Compas[]`,
  `lineaDeTablatura(compas, cuerdas) -> string[]`,
  `alturaEnPentagrama(midi) -> number`.

Esto es lo que pediste para **estudiar** la pieza y ver si la afinación queda
bien: el mismo `Pieza` dibujado como se escribe la música.

- [ ] **Step 1: Escribe las pruebas que fallan**

```typescript
import { describe, expect, it } from "vitest";
import { alturaEnPentagrama, compasesDe, lineaDeTablatura } from "./vistaEscrita";

const PIEZA = {
  nombre: "p", perfil: "guitarra_estandar", tempo: 60, compas: [4, 4],
  duracion_pulsos: 8,
  notas: [
    { midi: 40, nombre: "E2", cuerda: 6, traste: 0, inicio_pulsos: 0, duracion_pulsos: 1 },
    { midi: 45, nombre: "A2", cuerda: 5, traste: 0, inicio_pulsos: 1, duracion_pulsos: 1 },
    { midi: 52, nombre: "E3", cuerda: 4, traste: 2, inicio_pulsos: 4, duracion_pulsos: 2 },
  ],
};

describe("vista escrita", () => {
  it("reparte las notas en compases según el compás de la pieza", () => {
    const compases = compasesDe(PIEZA);
    expect(compases).toHaveLength(2);
    expect(compases[0].notas.map((n) => n.midi)).toEqual([40, 45]);
    expect(compases[1].notas.map((n) => n.midi)).toEqual([52]);
  });

  it("la tablatura pone cada traste en la línea de su cuerda", () => {
    const lineas = lineaDeTablatura(compasesDe(PIEZA)[0], 6);
    expect(lineas).toHaveLength(6);
    // La sexta cuerda es la línea de abajo, como se escribe la tablatura.
    expect(lineas[5]).toContain("0");
    expect(lineas[0]).not.toContain("2");
  });

  it("una nota más aguda va más arriba en el pentagrama", () => {
    expect(alturaEnPentagrama(52)).toBeLessThan(alturaEnPentagrama(40));
  });

  it("un compás vacío sigue siendo un compás", () => {
    const pieza = { ...PIEZA, notas: [PIEZA.notas[2]] };
    expect(compasesDe(pieza)).toHaveLength(2);
    expect(compasesDe(pieza)[0].notas).toEqual([]);
  });
});
```

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test vistaEscrita`
Expected: FAIL, no existe el módulo.

- [ ] **Step 3: Implementa la vista**

- La tablatura es texto monoespaciado: seis líneas, la sexta cuerda abajo, que es
  como se escribe. No hace falta canvas.
- El pentagrama se dibuja en SVG, que aquí sí vale: es estático y no se refresca
  sesenta veces por segundo.
- Cada nota ya tocada se acompaña de su desviación en cents, con el mismo color
  que usa el carril, reutilizando `colorDeDesviacion`.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test && pnpm build && pnpm lint`
Expected: PASS y build limpio.

- [ ] **Step 5: Commit**

```bash
git add interfaz/src/vistaEscrita.ts interfaz/src/VistaEscrita.tsx interfaz/src/vistaEscrita.test.ts interfaz/src/Carril.tsx
git commit -m "feat: tablatura y pentagrama para estudiar la pieza"
```

---

### Task 11: Documentación y cierre

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Documenta el carril**

Una sección nueva que diga, con estas palabras o parecidas:

- Qué es el carril y en qué se diferencia de los ejercicios: **aquí la música no
  espera**, la nota fallada pasa y queda marcada.
- Que la ventana de **±80 ms** decide si una nota va a tiempo, y que **ese número
  está razonado pero no medido tocando**: si te parece indulgente o severo, hay
  que ajustarlo.
- Los límites de esta etapa: una sola voz, sin acordes; sin ligados ni bends; la
  digitación se elige por cercanía al traste anterior, lo que basta para una
  escala y no para una canción.
- Que importar canciones de Guitar Pro, MusicXML, MIDI y tablatura ASCII es la
  etapa siguiente, y que no se puede hacer sin este modelo.

- [ ] **Step 2: Comprueba la suite entera**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Run: `cd interfaz && pnpm test && pnpm build && pnpm lint`
Expected: todo verde.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: el carril, con sus limites dichos"
```

---

## Verificación de la etapa completa

| Qué | Cómo |
|---|---|
| Las notas vienen y se tocan | Abrir el carril con una escala y tocarla |
| El desfase es creíble | Tocar a propósito pronto y tarde, mirar lo anotado |
| Los ±80 ms | Tocar a tiempo y ver si lo da por bueno **(lo juzga el usuario)** |
| El carril no deriva | Dejarlo correr un minuto y ver si la nota sigue cayendo donde suena |
| La pausa sin señal | Desenchufar el cable a mitad de pieza |
| La afinación se ve | Desafinar una cuerda a propósito y mirar el patrón de color |

Las tres últimas filas necesitan la guitarra conectada y las hace el usuario.
