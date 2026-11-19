# Ejercicios de acordes (etapa 2b) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que el programa sepa si un acorde esperado está sonando, use eso para un ejercicio de cambios de acorde que mida el tiempo de cambio, y deje de saltarse los acordes en el carril.

**Architecture:** una capa pura de espectro (`nucleo/analisis/espectro.py`) y un detector con búfer propio (`nucleo/analisis/acordes.py`) que **verifica** notas esperadas en vez de transcribir. Encima, un tipo hermano de `NotaEsperada` (`AcordeEsperado`), un generador de cambios con tabla de digitaciones escrita a mano, y un evaluador propio que no reutiliza el monofónico.

**Tech Stack:** Python 3.13 + numpy en `nucleo/`, FastAPI en `servidor/`, React + Vite + TypeScript en `interfaz/`. pytest y vitest. Cero dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-19-ejercicios-de-acordes-design.md`

## Global Constraints

- **Cero dependencias nuevas.** numpy y lo que ya está en `pyproject.toml`.
- **`.py` sin vocales acentuadas** en ningún sitio, comentarios y docstrings incluidos. `.ts`/`.tsx` sí llevan acentos en el texto de pantalla.
- **Todo en castellano**: nombres, comentarios, docstrings, mensajes.
- **pnpm, nunca npm.**
- **`INTERVALO_DE_ANALISIS_S = 0.021` no se toca.** Está acoplado por escrito a `nucleo/ejercicios/pulsaciones.py`.
- **`PerfilAfinacion.tamano_ventana` no se toca.** El detector de acordes lleva su propio búfer de 8192.
- **Preferir numpy a bucles.**
- **El camino monofónico no se modifica.** `Analizador`, `detectar_yin`, `EvaluadorEjercicio` y `DetectorPulsaciones` se quedan como están.
- **Pruebas que afirman comportamiento, no los valores del spike.** Nada de `assert presencia == 0.71`.
- Commits frecuentes, mensaje en castellano, terminando con las líneas de atribución del proyecto.

## Review Focus

Las cinco cosas que la spec implica, que ninguna tarea prueba de forma obvia, y que más probablemente muerdan a quien use esto:

1. **Ventana a medio llenar.** El detector arranca con el búfer vacío y recibe bloques de 1008 muestras: durante los primeros ~8 cuadros la ventana es mayoritariamente ceros. Sin guarda, la saliencia se calcula sobre basura y el primer veredicto es inventado. Prueba en Task 2.
2. **Normalizar contra cero.** Si la saliencia máxima del rango es 0 (ventana en silencio que pasó la compuerta por los pelos, o perfil degenerado), la división explota o da `nan`. Prueba en Task 2.
3. **Lista de esperadas vacía.** El carril puede llegar a un grupo de notas y el llamante puede pasar una tupla vacía. El detector no debe decir `"completo"` por vacuidad. Prueba en Task 2.
4. **Un acorde cuyas notas caen fuera del rango del perfil** (MIDI por encima del último traste, o un perfil de bajo con digitación de 6 cuerdas). Tiene que fallar **al generar**, nombrando el acorde y el perfil, nunca al tocar. Prueba en Task 4.
5. **Dos acordes iguales seguidos.** Si el ejercicio pide Do, Do, el evaluador puede dar el segundo por bueno con la cola del primero sin que el usuario mueva un dedo. Hace falta exigir que el acorde deje de estar completo entre uno y otro. Prueba en Task 5.

---

### Task 1: La capa pura de espectro

**Files:**
- Create: `nucleo/analisis/espectro.py`
- Test: `tests/test_espectro.py`

**Interfaces:**
- Consumes: nada. numpy solo.
- Produces:
  - `espectro_de_magnitud(muestras: np.ndarray, frecuencia_muestreo: int) -> tuple[np.ndarray, np.ndarray]` → `(frecuencias, magnitud)`
  - `saliencia_de_nota(frecuencias: np.ndarray, magnitud: np.ndarray, midi: int, armonicos: int = ARMONICOS_POR_DEFECTO, ancho_cents: float = ANCHO_BANDA_CENTS, referencia_a4: float = 440.0) -> float`
  - `ARMONICOS_POR_DEFECTO = 6`, `ANCHO_BANDA_CENTS = 35.0`

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""Pruebas de la capa pura de espectro."""

import numpy as np
import pytest

from nucleo.analisis.espectro import (
    ANCHO_BANDA_CENTS,
    ARMONICOS_POR_DEFECTO,
    espectro_de_magnitud,
    saliencia_de_nota,
)
from nucleo.musica import midi_a_frecuencia

FS = 48000


def senoide(frecuencia: float, muestras: int, fs: int = FS) -> np.ndarray:
    t = np.arange(muestras) / fs
    return np.sin(2.0 * np.pi * frecuencia * t)


def cuerda(frecuencia: float, muestras: int, armonicos: int = 8, fs: int = FS) -> np.ndarray:
    """Cuerda pulsada tosca: armonicos con decaimiento y fase aleatoria."""
    generador = np.random.default_rng(abs(int(frecuencia)))
    t = np.arange(muestras) / fs
    onda = np.zeros_like(t)
    for h in range(1, armonicos + 1):
        onda += (
            (1.0 / h**1.2)
            * np.exp(-t / (1.5 / h))
            * np.sin(2.0 * np.pi * frecuencia * h * t + generador.uniform(0.0, 2.0 * np.pi))
        )
    return onda


class TestEspectroDeMagnitud:
    def test_una_senoide_tiene_su_maximo_en_su_frecuencia(self):
        frecuencias, magnitud = espectro_de_magnitud(senoide(440.0, 8192), FS)
        pico = frecuencias[int(np.argmax(magnitud))]
        assert abs(pico - 440.0) < 10.0

    def test_el_silencio_no_tiene_magnitud(self):
        _, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        assert float(np.max(magnitud)) == 0.0

    def test_las_frecuencias_llegan_a_nyquist(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        assert frecuencias.size == magnitud.size
        assert frecuencias[0] == 0.0
        assert abs(frecuencias[-1] - FS / 2) < 1.0

    def test_una_ventana_vacia_no_rompe(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(0), FS)
        assert frecuencias.size == 0
        assert magnitud.size == 0


class TestSalienciaDeNota:
    def test_la_nota_que_suena_sale_mas_saliente_que_el_semitono_vecino(self):
        midi = 48  # C3
        frecuencias, magnitud = espectro_de_magnitud(
            cuerda(midi_a_frecuencia(midi), 8192), FS
        )
        suya = saliencia_de_nota(frecuencias, magnitud, midi)
        vecina = saliencia_de_nota(frecuencias, magnitud, midi + 1)
        assert suya > 2.0 * vecina

    def test_el_silencio_da_saliencia_cero(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        assert saliencia_de_nota(frecuencias, magnitud, 48) == 0.0

    def test_mas_armonicos_no_puede_bajar_la_saliencia(self):
        """Es una suma de terminos no negativos: anadir sumandos no resta."""
        frecuencias, magnitud = espectro_de_magnitud(
            cuerda(midi_a_frecuencia(48), 8192), FS
        )
        pocos = saliencia_de_nota(frecuencias, magnitud, 48, armonicos=2)
        muchos = saliencia_de_nota(frecuencias, magnitud, 48, armonicos=6)
        assert muchos >= pocos

    def test_una_nota_sobre_nyquist_no_rompe_ni_inventa(self):
        """Sus armonicos caen fuera del espectro: no hay donde medir."""
        frecuencias, magnitud = espectro_de_magnitud(
            cuerda(midi_a_frecuencia(48), 8192), FS
        )
        assert saliencia_de_nota(frecuencias, magnitud, 140) == 0.0

    def test_la_banda_tolera_una_cuerda_algo_desafinada(self):
        """Un tercio de semitono de margen: 20 cents no debe perder la nota."""
        midi = 48
        desafinada = midi_a_frecuencia(midi) * 2.0 ** (20.0 / 1200.0)
        frecuencias, magnitud = espectro_de_magnitud(cuerda(desafinada, 8192), FS)
        suya = saliencia_de_nota(frecuencias, magnitud, midi)
        vecina = saliencia_de_nota(frecuencias, magnitud, midi + 1)
        assert suya > vecina

    def test_un_ancho_de_banda_absurdo_se_rechaza(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        with pytest.raises(ValueError):
            saliencia_de_nota(frecuencias, magnitud, 48, ancho_cents=0.0)

    def test_pedir_cero_armonicos_se_rechaza(self):
        frecuencias, magnitud = espectro_de_magnitud(np.zeros(8192), FS)
        with pytest.raises(ValueError):
            saliencia_de_nota(frecuencias, magnitud, 48, armonicos=0)

    def test_las_constantes_son_las_de_la_spec(self):
        assert ARMONICOS_POR_DEFECTO == 6
        assert ANCHO_BANDA_CENTS == 35.0
```

- [ ] **Step 2: Comprobar que fallan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_espectro.py -q`
Expected: FAIL — `ModuleNotFoundError: nucleo.analisis.espectro`

- [ ] **Step 3: Escribir `nucleo/analisis/espectro.py`**

```python
"""Espectro de magnitud y saliencia armonica: la capa pura de la polifonia.

Funciones puras, sin estado: mismas muestras, mismo resultado. Es lo que permite
probar la deteccion de acordes con senal sintetica y sin hardware.

El metodo no transcribe, verifica. Dada una nota concreta, mide cuanta energia
hay donde esa nota deberia tenerla. La spec de la etapa 2b explica por que eso
basta: en los dos casos de uso -el ejercicio y el carril- el programa ya sabe que
notas espera.
"""

import numpy as np

from nucleo.musica import midi_a_frecuencia

# Cuantos armonicos se suman como prueba de que una nota suena.
#
# Seis y no mas: por encima del sexto los armonicos de las distintas notas de un
# acorde se solapan tanto que dejan de distinguir cual suena. Y no menos, porque
# la fundamental de una cuerda grave es debil en una pastilla electrica -el
# segundo y el tercer armonico suelen pesar mas- y quedarse en dos o tres haria
# depender el veredicto justo del armonico mas flojo.
ARMONICOS_POR_DEFECTO = 6

# Medio ancho de la banda alrededor de cada armonico, en cents.
#
# 35 cents es un tercio de semitono: tolera que la cuerda real este algo
# desafinada y que sus armonicos no sean multiplos exactos de la fundamental
# (inarmonicidad de una cuerda con rigidez), sin llegar a invadir el semitono
# vecino, que esta a 100.
ANCHO_BANDA_CENTS = 35.0


def espectro_de_magnitud(
    muestras: np.ndarray, frecuencia_muestreo: int
) -> tuple[np.ndarray, np.ndarray]:
    """Magnitud del espectro de la ventana, y las frecuencias de cada bin.

    Se aplica una ventana de Hann antes de la FFT, y no es decorativo: sin ella,
    el suelo de fuga espectral de la nota mas fuerte del acorde tapa a las mas
    debiles, que son justo las que hay que detectar. Con un rectangulo (es decir,
    sin ventana) los lobulos laterales caen a -13 dB; con Hann, a -31 dB.
    """
    x = np.asarray(muestras, dtype=np.float64)
    if x.size == 0:
        return np.zeros(0), np.zeros(0)
    magnitud = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    frecuencias = np.fft.rfftfreq(x.size, 1.0 / frecuencia_muestreo)
    return frecuencias, magnitud


def saliencia_de_nota(
    frecuencias: np.ndarray,
    magnitud: np.ndarray,
    midi: int,
    armonicos: int = ARMONICOS_POR_DEFECTO,
    ancho_cents: float = ANCHO_BANDA_CENTS,
    referencia_a4: float = 440.0,
) -> float:
    """Cuanta prueba hay de que la nota `midi` esta sonando en esta ventana.

        saliencia = suma sobre h de  max{ |X(f)| : f en banda(h·f0) } / h

    El maximo dentro de una banda, y no el valor de un bin: ni la cuerda esta
    exactamente afinada ni sus armonicos caen exactamente en h·f0. La ponderacion
    1/h baja el peso de los armonicos altos porque los comparten varias notas del
    acorde y prueban menos sobre cual de ellas suena.

    Devuelve 0.0 cuando no hay donde medir: espectro vacio, o una nota cuyos
    armonicos caen todos por encima de Nyquist.
    """
    if armonicos < 1:
        raise ValueError("Hacen falta al menos 1 armonico para medir saliencia")
    if ancho_cents <= 0.0:
        raise ValueError("El ancho de banda en cents tiene que ser positivo")
    if frecuencias.size == 0:
        return 0.0

    f0 = midi_a_frecuencia(midi, referencia_a4)
    factor = 2.0 ** (ancho_cents / 1200.0)
    total = 0.0
    for h in range(1, armonicos + 1):
        centro = f0 * h
        if centro >= frecuencias[-1]:
            break
        banda = magnitud[(frecuencias >= centro / factor) & (frecuencias <= centro * factor)]
        if banda.size > 0:
            total += float(np.max(banda)) / h
    return total
```

- [ ] **Step 4: Comprobar que pasan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_espectro.py -q`
Expected: PASS, 13 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/analisis/espectro.py tests/test_espectro.py
git commit -m "feat: espectro y saliencia armonica, la capa pura de la polifonia"
```

---

### Task 2: El detector de acordes

**Files:**
- Create: `nucleo/analisis/acordes.py`
- Test: `tests/test_acordes.py`

**Interfaces:**
- Consumes: `espectro_de_magnitud`, `saliencia_de_nota`, `ARMONICOS_POR_DEFECTO`, `ANCHO_BANDA_CENTS` de Task 1; `nivel_dbfs`, `UMBRAL_RUIDO_POR_DEFECTO_DBFS` de `nucleo.analisis.energia`; `PerfilAfinacion` de `nucleo.afinaciones`.
- Produces:
  - `ResultadoAcorde(estado: str, presencias: dict[int, float], faltan: tuple[int, ...], nivel_db: float)` con `a_dict()`
  - `DetectorAcordes(perfil, frecuencia_muestreo=48000, ventana=VENTANA_ACORDES, umbral_ruido_dbfs=..., umbral_presencia=UMBRAL_PRESENCIA)` con `.procesar(muestras, midis_esperados) -> ResultadoAcorde` y `.reiniciar()`
  - `VENTANA_ACORDES = 8192`, `UMBRAL_PRESENCIA = 0.45`
  - Estados: `"silencio"`, `"incompleto"`, `"completo"`

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""Pruebas del detector de acordes por verificacion."""

import numpy as np
import pytest

from nucleo.afinaciones import PERFILES_DE_FABRICA
from nucleo.analisis.acordes import (
    UMBRAL_PRESENCIA,
    VENTANA_ACORDES,
    DetectorAcordes,
    ResultadoAcorde,
)
from nucleo.musica import midi_a_frecuencia

FS = 48000
GUITARRA = PERFILES_DE_FABRICA["guitarra_estandar"]

# Do mayor abierto (x32010) y Sol mayor abierto (320003), en MIDI.
DO_MAYOR = (48, 52, 55, 60, 64)
SOL_MAYOR = (43, 47, 50, 55, 59, 67)


def cuerda(frecuencia: float, muestras: int, semilla: int, fs: int = FS) -> np.ndarray:
    generador = np.random.default_rng(semilla)
    t = np.arange(muestras) / fs
    onda = np.zeros_like(t)
    for h in range(1, 9):
        onda += (
            (1.0 / h**1.2)
            * np.exp(-t / (1.5 / h))
            * np.sin(2.0 * np.pi * frecuencia * h * t + generador.uniform(0.0, 2.0 * np.pi))
        )
    return onda


def rasgueo(midis, muestras: int = VENTANA_ACORDES) -> np.ndarray:
    """Las notas de un acorde sonando a la vez, normalizadas a amplitud 1."""
    mezcla = np.zeros(muestras)
    for indice, midi in enumerate(midis):
        mezcla += cuerda(midi_a_frecuencia(midi), muestras, semilla=indice)
    pico = float(np.max(np.abs(mezcla)))
    return mezcla / pico if pico > 0.0 else mezcla


def detectar(midis_sonando, midis_esperados) -> ResultadoAcorde:
    detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
    return detector.procesar(rasgueo(midis_sonando), midis_esperados)


class TestVeredicto:
    def test_el_acorde_completo_sale_completo(self):
        resultado = detectar(DO_MAYOR, DO_MAYOR)
        assert resultado.estado == "completo"
        assert resultado.faltan == ()

    def test_sol_completo_tambien(self):
        resultado = detectar(SOL_MAYOR, SOL_MAYOR)
        assert resultado.estado == "completo"
        assert resultado.faltan == ()

    def test_una_cuerda_muda_sale_nombrada(self):
        """Do sin la primera: falta E4 (midi 64) y solo esa."""
        resultado = detectar(DO_MAYOR[:-1], DO_MAYOR)
        assert resultado.estado == "incompleto"
        assert resultado.faltan == (64,)

    def test_la_cuerda_muda_del_medio_tambien(self):
        """Do sin la segunda: falta C4 (midi 60)."""
        suena = tuple(m for m in DO_MAYOR if m != 60)
        resultado = detectar(suena, DO_MAYOR)
        assert resultado.estado == "incompleto"
        assert resultado.faltan == (60,)

    def test_el_acorde_equivocado_falla_por_varias_notas(self):
        """Suena Sol, se pide Do: no es una cuerda muda, es otro acorde."""
        resultado = detectar(SOL_MAYOR, DO_MAYOR)
        assert resultado.estado == "incompleto"
        assert len(resultado.faltan) >= 3

    def test_las_ausencias_van_de_grave_a_aguda(self):
        resultado = detectar(SOL_MAYOR, DO_MAYOR)
        assert list(resultado.faltan) == sorted(resultado.faltan)

    def test_la_presencia_de_una_nota_muda_es_menor_que_la_de_una_que_suena(self):
        resultado = detectar(DO_MAYOR[:-1], DO_MAYOR)
        assert resultado.presencias[64] < resultado.presencias[48]


class TestPuertas:
    def test_el_silencio_es_silencio_y_no_dice_que_falte_nada(self):
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        resultado = detector.procesar(np.zeros(VENTANA_ACORDES), DO_MAYOR)
        assert resultado.estado == "silencio"
        assert resultado.presencias == {}
        assert resultado.faltan == ()

    def test_sin_notas_esperadas_no_hay_acorde_completo(self):
        """Una tupla vacia no se cumple por vacuidad: no hay acorde que juzgar."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        resultado = detector.procesar(rasgueo(DO_MAYOR), ())
        assert resultado.estado == "silencio"
        assert resultado.faltan == ()

    def test_una_ventana_a_medio_llenar_no_se_juzga(self):
        """Los primeros bloques dejan el bufer mayoritariamente en ceros."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        trozo = rasgueo(DO_MAYOR)[:1008]
        resultado = detector.procesar(trozo, DO_MAYOR)
        assert resultado.estado == "silencio"

    def test_la_ventana_se_llena_con_bloques_sucesivos(self):
        """Alimentado por bloques, acaba juzgando: es un bufer circular."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        largo = rasgueo(DO_MAYOR, muestras=VENTANA_ACORDES * 2)
        estados = [
            detector.procesar(largo[i : i + 1008], DO_MAYOR).estado
            for i in range(0, largo.size - 1008, 1008)
        ]
        assert estados[0] == "silencio"
        assert "completo" in estados

    def test_reiniciar_vacia_el_bufer(self):
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        detector.procesar(rasgueo(DO_MAYOR), DO_MAYOR)
        detector.reiniciar()
        resultado = detector.procesar(rasgueo(DO_MAYOR)[:1008], DO_MAYOR)
        assert resultado.estado == "silencio"

    def test_una_ventana_con_energia_pero_sin_tono_no_da_nan(self):
        """Ruido blanco de nivel alto: la normalizacion no puede dividir por cero."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        generador = np.random.default_rng(0)
        resultado = detector.procesar(
            generador.normal(0.0, 0.2, VENTANA_ACORDES), DO_MAYOR
        )
        assert all(np.isfinite(v) for v in resultado.presencias.values())

    def test_una_constante_continua_no_da_nan(self):
        """Senal sin oscilacion: energia alta, saliencia cero en todo el rango."""
        detector = DetectorAcordes(GUITARRA, frecuencia_muestreo=FS)
        resultado = detector.procesar(np.full(VENTANA_ACORDES, 0.5), DO_MAYOR)
        assert all(np.isfinite(v) for v in resultado.presencias.values())
        assert resultado.estado == "incompleto"


class TestForma:
    def test_el_diccionario_es_el_del_websocket(self):
        resultado = detectar(DO_MAYOR, DO_MAYOR)
        como_dict = resultado.a_dict()
        assert set(como_dict) == {"estado", "presencias", "faltan", "nivel_db"}
        assert como_dict["estado"] == "completo"
        assert como_dict["faltan"] == []
        assert all(isinstance(k, str) for k in como_dict["presencias"])

    def test_una_ventana_absurda_se_rechaza_al_construir(self):
        with pytest.raises(ValueError):
            DetectorAcordes(GUITARRA, ventana=0)

    def test_el_umbral_es_el_de_la_spec(self):
        assert UMBRAL_PRESENCIA == 0.45
        assert VENTANA_ACORDES == 8192
```

- [ ] **Step 2: Comprobar que fallan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_acordes.py -q`
Expected: FAIL — `ModuleNotFoundError: nucleo.analisis.acordes`

- [ ] **Step 3: Escribir `nucleo/analisis/acordes.py`**

```python
"""Deteccion de acordes por verificacion.

No transcribe: comprueba. Dada una lista de notas esperadas -que el ejercicio
genero o que la pieza trae escritas- mide cuanta prueba hay de que cada una esta
sonando y responde con las que faltan. La spec de la etapa 2b razona por que eso
basta y por que la transcripcion polifonica libre no hace falta aqui.

Es el unico objeto con estado de la deteccion de acordes, y lo es por una razon
concreta: necesita una ventana de 8192 muestras (171 ms) para separar semitonos
graves -a E2 dos semitonos vecinos distan 4,9 Hz, y 4096 muestras dan 11,7 Hz por
bin- mientras que quien lo alimenta entrega bloques de unas 1008. De ahi el bufer
circular.
"""

from dataclasses import dataclass, field

import numpy as np

from nucleo.afinaciones import PerfilAfinacion
from nucleo.analisis.energia import UMBRAL_RUIDO_POR_DEFECTO_DBFS, nivel_dbfs
from nucleo.analisis.espectro import (
    ANCHO_BANDA_CENTS,
    ARMONICOS_POR_DEFECTO,
    espectro_de_magnitud,
    saliencia_de_nota,
)
from nucleo.musica import frecuencia_a_midi

# Muestras por ventana de deteccion de acordes.
#
# **NO es `PerfilAfinacion.tamano_ventana`**, y la diferencia es deliberada. El
# afinador usa 4096 porque le basta y porque menos latencia hace mejor aguja. Un
# acorde necesita separar semitonos en la zona grave, donde 4096 muestras no
# llegan: a 48 kHz dan 11,7 Hz por bin, y entre E2 (82,41) y F2 (87,31) hay 4,9.
# Con 8192 el bin baja a 5,9 Hz y las notas del acorde se distinguen.
#
# El coste es latencia: 171 ms. Es aceptable justo porque un acorde se sostiene.
# Para una escala rapida no lo seria, y por eso las dos ventanas no se unifican.
VENTANA_ACORDES = 8192

# Presencia relativa minima para dar una nota por sonada.
#
# Medido con acordes sinteticos (ver la spec): una nota que suena queda entre
# 0,58 y 0,87, y una cuerda muda entre 0,27 y 0,32. 0,45 cae en medio de ese
# hueco por los dos lados.
#
# **Esta por calibrar con la guitarra del usuario.** El hueco real puede ser mas
# estrecho que el sintetico: una pastilla electrica reparte los armonicos de otra
# manera.
UMBRAL_PRESENCIA = 0.45

# Fraccion de la ventana que tiene que estar llena antes de juzgar nada.
#
# Alimentado por bloques, el bufer arranca en ceros. Sin esta guarda los primeros
# cuadros se juzgarian sobre una ventana mayoritariamente vacia, cuyo espectro no
# es el del acorde sino el del escalon entre los ceros y la senal. Un veredicto
# asi no es dudoso: es inventado, y la etapa 2a ya fijo la regla de que una
# lectura dudosa se calla en vez de mostrarse atenuada.
FRACCION_MINIMA_LLENA = 0.9


@dataclass(frozen=True)
class ResultadoAcorde:
    """Lo que el detector publica por cada ventana.

    estado es "silencio", "incompleto" o "completo". En silencio, presencias esta
    vacio y faltan tambien: el detector no rellena con el ultimo valor conocido,
    igual que el analisis monofonico.

    No hay estado "equivocado". Un acorde equivocado es uno al que le faltan casi
    todas las notas, y `faltan` ya lo dice. Decidir si eso se le cuenta al usuario
    como "te falta la primera" o como "ese no es el acorde" es presentacion, y la
    presentacion no vive en el nucleo.
    """

    estado: str
    nivel_db: float
    presencias: dict[int, float] = field(default_factory=dict)
    faltan: tuple[int, ...] = ()

    def a_dict(self) -> dict:
        """Forma exacta del mensaje que viaja por WebSocket.

        Las claves de `presencias` van como texto porque JSON no admite claves
        numericas; quien lo lea tendra que volver a convertirlas.
        """
        return {
            "estado": self.estado,
            "nivel_db": round(self.nivel_db, 1),
            "presencias": {str(k): round(v, 3) for k, v in self.presencias.items()},
            "faltan": list(self.faltan),
        }


class DetectorAcordes:
    """Comprueba si las notas esperadas de un acorde estan sonando."""

    def __init__(
        self,
        perfil: PerfilAfinacion,
        frecuencia_muestreo: int = 48000,
        ventana: int = VENTANA_ACORDES,
        umbral_ruido_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS,
        umbral_presencia: float = UMBRAL_PRESENCIA,
        armonicos: int = ARMONICOS_POR_DEFECTO,
        ancho_cents: float = ANCHO_BANDA_CENTS,
        referencia_a4: float = 440.0,
    ) -> None:
        if ventana < 2:
            raise ValueError("La ventana de acordes tiene que tener al menos 2 muestras")
        self.perfil = perfil
        self.frecuencia_muestreo = frecuencia_muestreo
        self.ventana = ventana
        self.umbral_ruido_dbfs = umbral_ruido_dbfs
        self.umbral_presencia = umbral_presencia
        self.armonicos = armonicos
        self.ancho_cents = ancho_cents
        self.referencia_a4 = referencia_a4

        # El rango sobre el que se normaliza: todo lo que el mastil alcanza, con
        # un semitono de margen por abajo. Normalizar contra las notas ESPERADAS
        # haria que un acorde completamente equivocado saliera completo, porque
        # la mas fuerte de las esperadas valdria 1 por construccion.
        grave = round(frecuencia_a_midi(perfil.frecuencia_minima, referencia_a4)) - 1
        aguda = max(
            round(frecuencia_a_midi(cuerda.frecuencia, referencia_a4))
            for cuerda in perfil.cuerdas
        )
        self._rango = tuple(range(grave, aguda + perfil.trastes + 1))

        self._bufer = np.zeros(ventana, dtype=np.float64)
        self._llenas = 0

    def reiniciar(self) -> None:
        """Vacia el bufer. Se llama al parar o al cambiar de pieza."""
        self._bufer[:] = 0.0
        self._llenas = 0

    def _acumular(self, muestras: np.ndarray) -> None:
        """Mete el bloque por el final del bufer circular."""
        bloque = np.asarray(muestras, dtype=np.float64).ravel()
        if bloque.size == 0:
            return
        if bloque.size >= self.ventana:
            self._bufer[:] = bloque[-self.ventana :]
            self._llenas = self.ventana
            return
        self._bufer[:] = np.concatenate((self._bufer[bloque.size :], bloque))
        self._llenas = min(self.ventana, self._llenas + bloque.size)

    def _silencio(self, nivel: float) -> ResultadoAcorde:
        return ResultadoAcorde(estado="silencio", nivel_db=nivel)

    def procesar(
        self, muestras: np.ndarray, midis_esperados: tuple[int, ...]
    ) -> ResultadoAcorde:
        """Acumula el bloque y juzga el acorde esperado sobre la ventana completa.

        Tres puertas devuelven silencio en vez de inventar, en este orden: la
        ventana a medio llenar, la lista de esperadas vacia y la compuerta de
        ruido. La segunda importa mas de lo que parece: una lista vacia se
        cumpliria por vacuidad y daria "completo" sin que suene nada.
        """
        self._acumular(muestras)
        nivel = nivel_dbfs(self._bufer[-self._llenas :]) if self._llenas else nivel_dbfs(self._bufer)

        if self._llenas < FRACCION_MINIMA_LLENA * self.ventana:
            return self._silencio(nivel)
        if not midis_esperados:
            return self._silencio(nivel)
        if nivel <= self.umbral_ruido_dbfs:
            return self._silencio(nivel)

        frecuencias, magnitud = espectro_de_magnitud(self._bufer, self.frecuencia_muestreo)
        salientes = [
            saliencia_de_nota(
                frecuencias,
                magnitud,
                midi,
                armonicos=self.armonicos,
                ancho_cents=self.ancho_cents,
                referencia_a4=self.referencia_a4,
            )
            for midi in self._rango
        ]
        tope = max(salientes) if salientes else 0.0

        if tope <= 0.0:
            # Energia sin ninguna saliencia en todo el mastil: ruido o continua.
            # Dividir aqui daria nan y un nan nunca supera un umbral, asi que el
            # veredicto seria "incompleto" por accidente. Se dice explicitamente.
            presencias = {midi: 0.0 for midi in midis_esperados}
        else:
            presencias = {
                midi: saliencia_de_nota(
                    frecuencias,
                    magnitud,
                    midi,
                    armonicos=self.armonicos,
                    ancho_cents=self.ancho_cents,
                    referencia_a4=self.referencia_a4,
                )
                / tope
                for midi in midis_esperados
            }

        faltan = tuple(
            sorted(midi for midi, valor in presencias.items() if valor < self.umbral_presencia)
        )
        return ResultadoAcorde(
            estado="completo" if not faltan else "incompleto",
            nivel_db=nivel,
            presencias=presencias,
            faltan=faltan,
        )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_acordes.py -q`
Expected: PASS, 19 pruebas. Si `test_una_cuerda_muda_sale_nombrada` falla por margen, **no se toca el umbral para que pase**: se mide la presencia real, se apunta el número en el docstring de `UMBRAL_PRESENCIA` y se decide con el dato delante.

- [ ] **Step 5: Commit**

```bash
git add nucleo/analisis/acordes.py tests/test_acordes.py
git commit -m "feat: el detector de acordes dice que nota del acorde no suena"
```

---

### Task 3: `AcordeEsperado` y un ejercicio que lleve acordes

**Files:**
- Modify: `nucleo/ejercicios/modelo.py`
- Test: `tests/test_modelo_acordes.py`

**Interfaces:**
- Consumes: `Posicion`, `nombre_de_midi` de `nucleo.musica`.
- Produces:
  - `AcordeEsperado(nombre: str, posiciones: tuple[Posicion, ...], midis: tuple[int, ...], pulsos: float = 4.0)` con `a_dict()`
  - `Ejercicio.acordes: tuple[AcordeEsperado, ...] = ()`, validado en `__post_init__`: no puede haber notas y acordes a la vez, ni ninguno de los dos.
  - `Ejercicio.__len__` devuelve el número de notas **o** de acordes, el que haya.
  - `Ejercicio.a_dict()` incluye `"acordes"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""Pruebas del modelo cuando el ejercicio son acordes y no notas."""

import pytest

from nucleo.ejercicios.modelo import AcordeEsperado, Ejercicio, NotaEsperada
from nucleo.musica import Posicion

DO = AcordeEsperado(
    nombre="Do mayor",
    posiciones=(
        Posicion(cuerda=5, traste=3),
        Posicion(cuerda=4, traste=2),
        Posicion(cuerda=3, traste=0),
        Posicion(cuerda=2, traste=1),
        Posicion(cuerda=1, traste=0),
    ),
    midis=(48, 52, 55, 60, 64),
)
UNA_NOTA = NotaEsperada(midi=48, posiciones=(Posicion(cuerda=5, traste=3),))


def ejercicio(**extra) -> Ejercicio:
    base = {
        "clave": "cambios",
        "nombre": "Cambios",
        "descripcion": "",
        "notas": (),
        "tempo": 60,
        "perfil": "guitarra_estandar",
    }
    return Ejercicio(**{**base, **extra})


class TestAcordeEsperado:
    def test_el_nombre_de_cada_nota_sale_en_notacion_cientifica(self):
        assert DO.nombres == ("C3", "E3", "G3", "C4", "E4")

    def test_el_diccionario_lleva_todo_lo_que_la_pantalla_dibuja(self):
        como_dict = DO.a_dict()
        assert set(como_dict) == {"nombre", "posiciones", "midis", "nombres", "pulsos"}
        assert como_dict["posiciones"][0] == {"cuerda": 5, "traste": 3}
        assert como_dict["pulsos"] == 4.0

    def test_un_acorde_sin_notas_se_rechaza(self):
        with pytest.raises(ValueError, match="acorde"):
            AcordeEsperado(nombre="vacio", posiciones=(), midis=())


class TestEjercicioConAcordes:
    def test_un_ejercicio_de_acordes_se_mide_en_acordes(self):
        ejer = ejercicio(acordes=(DO, DO))
        assert len(ejer) == 2

    def test_un_ejercicio_de_notas_sigue_midiendose_en_notas(self):
        assert len(ejercicio(notas=(UNA_NOTA,))) == 1

    def test_notas_y_acordes_a_la_vez_se_rechaza(self):
        """Un ejercicio tiene una cosa o la otra. Un tipo ambiguo se paga luego."""
        with pytest.raises(ValueError, match="notas y acordes"):
            ejercicio(notas=(UNA_NOTA,), acordes=(DO,))

    def test_un_ejercicio_sin_nada_se_rechaza(self):
        with pytest.raises(ValueError, match="vacio"):
            ejercicio()

    def test_el_diccionario_lleva_los_acordes(self):
        como_dict = ejercicio(acordes=(DO,)).a_dict()
        assert como_dict["acordes"][0]["nombre"] == "Do mayor"
        assert como_dict["notas"] == []
```

- [ ] **Step 2: Comprobar que fallan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_modelo_acordes.py -q`
Expected: FAIL — `ImportError: cannot import name 'AcordeEsperado'`

- [ ] **Step 3: Añadir `AcordeEsperado` a `nucleo/ejercicios/modelo.py`**

Después de `NotaEsperada`, antes de `Ejercicio`:

```python
@dataclass(frozen=True)
class AcordeEsperado:
    """Un acorde que el ejercicio pide tocar.

    Es un tipo HERMANO de NotaEsperada, no una generalizacion suya, y eso es una
    decision. La alternativa era darle a NotaEsperada un campo `midis` plural: se
    rechazo porque el evaluador monofonico, el detector de pulsaciones y la
    pantalla de ejercicios leen `NotaEsperada.midi` en todas partes, y un campo
    que a veces es una nota y a veces cinco es la clase de ambiguedad que se paga
    despues.

    posiciones es la digitacion CONCRETA, no todas las formas de tocar el acorde.
    A diferencia de NotaEsperada -donde varias posiciones son alternativas
    validas- aqui todas las posiciones se tocan a la vez.

    pulsos vale 4 por defecto: un compas de 4/4 por acorde, que a 60 ppm son
    cuatro segundos. Un cambio de acorde necesita mas tiempo que una nota.
    """

    nombre: str
    posiciones: tuple[Posicion, ...]
    midis: tuple[int, ...]
    pulsos: float = 4.0

    def __post_init__(self) -> None:
        if not self.midis or not self.posiciones:
            raise ValueError(f"El acorde '{self.nombre}' no tiene ninguna nota que tocar")

    @property
    def nombres(self) -> tuple[str, ...]:
        """Nombres en notacion cientifica, de grave a aguda."""
        return tuple(nombre_de_midi(midi) for midi in self.midis)

    def a_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "posiciones": [{"cuerda": p.cuerda, "traste": p.traste} for p in self.posiciones],
            "midis": list(self.midis),
            "nombres": list(self.nombres),
            "pulsos": self.pulsos,
        }
```

Y en `Ejercicio`: añadir el campo, la validación y el `a_dict`.

```python
    notas: tuple[NotaEsperada, ...]
    tempo: int
    perfil: str
    acordes: tuple[AcordeEsperado, ...] = ()

    def __post_init__(self) -> None:
        """Un ejercicio tiene notas o acordes, nunca las dos y nunca ninguna.

        Se valida al construirlo y no al evaluarlo porque hay dos evaluadores
        distintos -el monofonico y el de cambios- y cada uno lee un campo. Un
        ejercicio con los dos llenos iria a uno de ellos y el otro contenido se
        perderia en silencio.
        """
        if self.notas and self.acordes:
            raise ValueError(
                f"El ejercicio '{self.clave}' trae notas y acordes a la vez: "
                "tiene que traer una cosa o la otra"
            )
        if not self.notas and not self.acordes:
            raise ValueError(f"El ejercicio '{self.clave}' esta vacio")

    def __len__(self) -> int:
        return len(self.acordes) if self.acordes else len(self.notas)
```

En `a_dict()`, añadir `"acordes": [a.a_dict() for a in self.acordes]`.

- [ ] **Step 4: Comprobar que pasan, y que la 2a sigue en pie**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_modelo_acordes.py tests/test_ejercicios.py tests/test_estudio.py -q`
Expected: PASS. Si alguna prueba de la 2a construía un `Ejercicio` con `notas=()`, ahora falla: es un `Ejercicio` vacío y la validación nueva es correcta. Arreglar la prueba, no la validación.

- [ ] **Step 5: Commit**

```bash
git add nucleo/ejercicios/modelo.py tests/test_modelo_acordes.py
git commit -m "feat: un ejercicio puede pedir acordes, y no notas y acordes a la vez"
```

---

### Task 4: El generador de cambios y la tabla de digitaciones

**Files:**
- Create: `nucleo/ejercicios/generadores/acordes.py`
- Test: `tests/test_generador_acordes.py`

**Interfaces:**
- Consumes: `AcordeEsperado`, `Ejercicio` de Task 3; `validar_parametros` de `nucleo.ejercicios.generadores.comun`; `PerfilAfinacion`, `PERFILES_DE_FABRICA`.
- Produces:
  - `DIGITACIONES: dict[str, tuple[str, tuple[int | None, ...]]]` — clave → (nombre en castellano, trastes por cuerda de la 6.ª a la 1.ª, `None` = no se toca)
  - `generar_cambios(perfil_clave="guitarra_estandar", claves=("do", "sol", "re"), repeticiones=4, tempo=60) -> Ejercicio`
  - `acorde_de_clave(clave: str, perfil: PerfilAfinacion) -> AcordeEsperado`

**Tabla** (trastes de la 6.ª a la 1.ª; `None` es cuerda que no se toca):

| clave | nombre | 6 | 5 | 4 | 3 | 2 | 1 |
|---|---|---|---|---|---|---|---|
| `do` | Do mayor | – | 3 | 2 | 0 | 1 | 0 |
| `sol` | Sol mayor | 3 | 2 | 0 | 0 | 0 | 3 |
| `re` | Re mayor | – | – | 0 | 2 | 3 | 2 |
| `la` | La mayor | – | 0 | 2 | 2 | 2 | 0 |
| `mi` | Mi mayor | 0 | 2 | 2 | 1 | 0 | 0 |
| `la_menor` | La menor | – | 0 | 2 | 2 | 1 | 0 |
| `mi_menor` | Mi menor | 0 | 2 | 2 | 0 | 0 | 0 |
| `re_menor` | Re menor | – | – | 0 | 2 | 3 | 1 |

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""Pruebas del generador de cambios de acorde."""

import pytest

from nucleo.afinaciones import PERFILES_DE_FABRICA
from nucleo.ejercicios.generadores.acordes import (
    DIGITACIONES,
    acorde_de_clave,
    generar_cambios,
)

GUITARRA = PERFILES_DE_FABRICA["guitarra_estandar"]


class TestLaTabla:
    def test_estan_los_ocho_acordes_de_la_spec(self):
        assert set(DIGITACIONES) == {
            "do", "sol", "re", "la", "mi", "la_menor", "mi_menor", "re_menor",
        }

    def test_cada_digitacion_cubre_las_seis_cuerdas(self):
        for clave, (_, trastes) in DIGITACIONES.items():
            assert len(trastes) == 6, clave

    def test_do_mayor_es_x32010(self):
        nombre, trastes = DIGITACIONES["do"]
        assert nombre == "Do mayor"
        assert trastes == (None, 3, 2, 0, 1, 0)

    def test_una_cuerda_al_aire_no_es_una_cuerda_muda(self):
        """0 y None son distintos: al aire suena, muda no se toca."""
        _, do = DIGITACIONES["do"]
        assert do[0] is None
        assert do[3] == 0


class TestAcordeDeClave:
    def test_do_mayor_da_las_cinco_notas_de_grave_a_aguda(self):
        acorde = acorde_de_clave("do", GUITARRA)
        assert acorde.midis == (48, 52, 55, 60, 64)
        assert acorde.nombre == "Do mayor"

    def test_las_posiciones_no_incluyen_la_cuerda_muda(self):
        acorde = acorde_de_clave("do", GUITARRA)
        assert len(acorde.posiciones) == 5
        assert all(p.cuerda != 6 for p in acorde.posiciones)

    def test_mi_menor_usa_las_seis_cuerdas(self):
        assert len(acorde_de_clave("mi_menor", GUITARRA).posiciones) == 6

    def test_una_clave_que_no_existe_se_rechaza_listando_las_que_si(self):
        with pytest.raises(ValueError, match="do"):
            acorde_de_clave("fa_sostenido_disminuido", GUITARRA)

    def test_un_perfil_que_no_alcanza_la_digitacion_se_rechaza_al_generar(self):
        """Un bajo de 4 cuerdas no toca un Do de 5. Falla aqui, no al tocar."""
        bajo = PERFILES_DE_FABRICA["bajo_estandar"]
        with pytest.raises(ValueError, match="Do mayor"):
            acorde_de_clave("do", bajo)


class TestGenerarCambios:
    def test_tres_acordes_por_cuatro_repeticiones_son_doce(self):
        ejercicio = generar_cambios(claves=("do", "sol", "re"), repeticiones=4)
        assert len(ejercicio) == 12

    def test_los_acordes_se_alternan_y_no_se_agrupan(self):
        """Do, Sol, Re, Do, Sol, Re... El cambio es lo que se practica."""
        ejercicio = generar_cambios(claves=("do", "sol"), repeticiones=3)
        nombres = [a.nombre for a in ejercicio.acordes]
        assert nombres == ["Do mayor", "Sol mayor"] * 3

    def test_el_ejercicio_no_trae_notas_sueltas(self):
        assert generar_cambios().notas == ()

    def test_una_sola_clave_se_rechaza_porque_no_hay_cambio_que_practicar(self):
        with pytest.raises(ValueError, match="dos"):
            generar_cambios(claves=("do",))

    def test_cero_repeticiones_se_rechaza(self):
        with pytest.raises(ValueError, match="repeticion"):
            generar_cambios(repeticiones=0)

    def test_un_tempo_imposible_se_rechaza_igual_que_en_los_otros_generadores(self):
        with pytest.raises(ValueError):
            generar_cambios(tempo=1)

    def test_la_descripcion_dice_cuantos_cambios_y_a_que_tempo(self):
        ejercicio = generar_cambios(claves=("do", "sol"), repeticiones=2, tempo=70)
        assert "70" in ejercicio.descripcion
        assert "4" in ejercicio.descripcion

    def test_la_clave_distingue_los_acordes_pedidos(self):
        uno = generar_cambios(claves=("do", "sol"))
        otro = generar_cambios(claves=("la", "mi"))
        assert uno.clave != otro.clave
```

- [ ] **Step 2: Comprobar que fallan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_generador_acordes.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Escribir el generador**

```python
"""Generador de cambios de acorde: la quinta familia de ejercicios.

Las digitaciones son una tabla escrita a mano y NO se derivan del patron de
intervalos de `teoria.ACORDES`. Un Do mayor abierto es x32010 porque asi se toca;
derivarlo como "la interseccion optima del conjunto {0,4,7} con el mastil"
produciria digitaciones correctas en teoria que nadie usa y que ninguna mano
alcanza. El arpegio si se deriva -ahi se toca nota a nota-; el acorde, no.
"""

from nucleo.afinaciones import PerfilAfinacion
from nucleo.ejercicios.generadores.comun import validar_parametros
from nucleo.ejercicios.modelo import AcordeEsperado, Ejercicio
from nucleo.musica import Posicion, frecuencia_a_midi

__all__ = ["DIGITACIONES", "acorde_de_clave", "generar_cambios"]

# Clave -> (nombre en castellano, trastes de la 6.a cuerda a la 1.a).
#
# None NO es lo mismo que 0: None es una cuerda que no se toca y 0 es una cuerda
# al aire, que suena. Confundirlos haria que el detector buscase una nota que
# nadie esta tocando y la contase como muda.
DIGITACIONES: dict[str, tuple[str, tuple[int | None, ...]]] = {
    "do": ("Do mayor", (None, 3, 2, 0, 1, 0)),
    "sol": ("Sol mayor", (3, 2, 0, 0, 0, 3)),
    "re": ("Re mayor", (None, None, 0, 2, 3, 2)),
    "la": ("La mayor", (None, 0, 2, 2, 2, 0)),
    "mi": ("Mi mayor", (0, 2, 2, 1, 0, 0)),
    "la_menor": ("La menor", (None, 0, 2, 2, 1, 0)),
    "mi_menor": ("Mi menor", (0, 2, 2, 0, 0, 0)),
    "re_menor": ("Re menor", (None, None, 0, 2, 3, 1)),
}

# Pulsos que dura cada acorde: un compas de 4/4.
PULSOS_POR_ACORDE = 4.0


def acorde_de_clave(clave: str, perfil: PerfilAfinacion) -> AcordeEsperado:
    """Traduce una digitacion de la tabla a notas concretas de este perfil.

    Lanza ValueError si el perfil no alcanza la digitacion -un bajo de cuatro
    cuerdas no toca un Do de cinco-, y lo hace AQUI, al generar, no mientras se
    toca. Es la misma regla que los cuatro generadores de la etapa 2a.
    """
    if clave not in DIGITACIONES:
        disponibles = ", ".join(sorted(DIGITACIONES))
        raise ValueError(f"El acorde '{clave}' no esta en la tabla. Opciones: {disponibles}")

    nombre, trastes = DIGITACIONES[clave]
    por_numero = {cuerda.numero: cuerda for cuerda in perfil.cuerdas}

    posiciones: list[Posicion] = []
    midis: list[int] = []
    # La tabla va de la 6.a a la 1.a; el numero de cuerda baja al avanzar.
    for indice, traste in enumerate(trastes):
        numero = len(trastes) - indice
        if traste is None:
            continue
        if numero not in por_numero:
            raise ValueError(
                f"El acorde {nombre} necesita la cuerda {numero} y el perfil "
                f"{perfil.nombre} no la tiene."
            )
        if traste > perfil.trastes:
            raise ValueError(
                f"El acorde {nombre} pide el traste {traste} y el perfil "
                f"{perfil.nombre} solo tiene {perfil.trastes}."
            )
        posiciones.append(Posicion(cuerda=numero, traste=traste))
        midis.append(round(frecuencia_a_midi(por_numero[numero].frecuencia)) + traste)

    orden = sorted(range(len(midis)), key=lambda i: midis[i])
    return AcordeEsperado(
        nombre=nombre,
        posiciones=tuple(posiciones[i] for i in orden),
        midis=tuple(midis[i] for i in orden),
        pulsos=PULSOS_POR_ACORDE,
    )


def generar_cambios(
    perfil_clave: str = "guitarra_estandar",
    claves: tuple[str, ...] = ("do", "sol", "re"),
    repeticiones: int = 4,
    tempo: int = 60,
) -> Ejercicio:
    """Alterna los acordes pedidos tantas veces como se diga.

    Alterna y no agrupa: Do, Sol, Re, Do, Sol, Re. Lo que se practica es el
    CAMBIO, asi que cuatro Do seguidos no son el ejercicio.
    """
    perfil = validar_parametros(perfil_clave, "ascendente", tempo)
    if len(claves) < 2:
        raise ValueError("Un ejercicio de cambios necesita al menos dos acordes distintos")
    if repeticiones < 1:
        raise ValueError("Hacen falta al menos 1 repeticion")

    acordes = tuple(acorde_de_clave(clave, perfil) for clave in claves) * repeticiones
    nombres = ", ".join(DIGITACIONES[clave][0] for clave in claves)
    return Ejercicio(
        clave=f"cambios_{'_'.join(claves)}",
        nombre=f"Cambios: {nombres}",
        descripcion=(
            f"{len(acordes)} acordes alternando {nombres}, a {tempo} pulsos por "
            f"minuto. Se mide si el acorde suena completo y cuanto tardas en cambiar."
        ),
        notas=(),
        acordes=acordes,
        tempo=tempo,
        perfil=perfil_clave,
    )
```

- [ ] **Step 4: Comprobar que pasan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_generador_acordes.py -q`
Expected: PASS, 17 pruebas. `validar_parametros` recibe `"ascendente"` porque la dirección no significa nada en un ejercicio de acordes y ese parámetro valida contra `DIRECCIONES`; si al leerlo resulta que exige otra cosa, pasar la que acepte y dejarlo comentado.

- [ ] **Step 5: Commit**

```bash
git add nucleo/ejercicios/generadores/acordes.py tests/test_generador_acordes.py
git commit -m "feat: ocho acordes abiertos y un ejercicio que alterna entre ellos"
```

---

### Task 5: El evaluador de cambios

**Files:**
- Create: `nucleo/ejercicios/cambios.py`
- Test: `tests/test_cambios.py`

**Interfaces:**
- Consumes: `ResultadoAcorde` de Task 2; `Ejercicio`, `AcordeEsperado` de Task 3; `INTENTOS_PARA_AYUDA`, `SEGUNDOS_PARA_AYUDA` de `nucleo.ejercicios.evaluacion`.
- Produces:
  - `CUADROS_PARA_ACORDE_ESTABLE = 4`
  - `EstadoCambios(indice, total, intentos, ayuda_visible, completado, acorde_actual, faltan, ultimo_cambio_s)` con `a_dict()`
  - `EvaluadorCambios(ejercicio, intentos_para_ayuda=..., segundos_para_ayuda=..., cuadros_para_acorde_estable=...)` con `.procesar(resultado, instante_s) -> EstadoCambios`, `.estado`, `.resultado()`, `.reiniciar()`
  - `InformeCambios` con `tiempo_medio_de_cambio_s`, `por_acorde`, `cuerdas_problematicas`

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""Pruebas del evaluador de cambios de acorde.

Se prueba sin audio, igual que el evaluador monofonico de la 2a: consume
ResultadoAcorde, que es un dato. Se escribe la secuencia exacta de alguien que
tarda dos segundos en el cambio o que deja muda la primera cuerda.
"""

import pytest

from nucleo.analisis.acordes import ResultadoAcorde
from nucleo.ejercicios.cambios import CUADROS_PARA_ACORDE_ESTABLE, EvaluadorCambios
from nucleo.ejercicios.generadores.acordes import generar_cambios

CUADRO_S = 0.021


def completo(midis) -> ResultadoAcorde:
    return ResultadoAcorde(
        estado="completo",
        nivel_db=-30.0,
        presencias={m: 0.8 for m in midis},
        faltan=(),
    )


def incompleto(midis, faltan) -> ResultadoAcorde:
    return ResultadoAcorde(
        estado="incompleto",
        nivel_db=-30.0,
        presencias={m: (0.2 if m in faltan else 0.8) for m in midis},
        faltan=tuple(sorted(faltan)),
    )


def silencio() -> ResultadoAcorde:
    return ResultadoAcorde(estado="silencio", nivel_db=-80.0)


def correr(evaluador, secuencia, desde: float = 0.0):
    """Mete una secuencia de resultados, un cuadro cada CUADRO_S."""
    estado = None
    instante = desde
    for resultado in secuencia:
        estado = evaluador.procesar(resultado, instante)
        instante += CUADRO_S
    return estado, instante


def evaluador():
    return EvaluadorCambios(generar_cambios(claves=("do", "sol"), repeticiones=1))


class TestAcierto:
    def test_el_acorde_sostenido_se_da_por_bueno_y_avanza(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado, _ = correr(ev, [completo(midis)] * CUADROS_PARA_ACORDE_ESTABLE)
        assert estado.indice == 1

    def test_un_cuadro_suelto_no_basta(self):
        """A mitad del rasgueo el acorde puede estar completo por accidente."""
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado, _ = correr(ev, [completo(midis), incompleto(midis, {midis[0]})])
        assert estado.indice == 0

    def test_terminar_el_ejercicio_lo_marca_completado(self):
        ev = evaluador()
        instante = 0.0
        for acorde in ev.ejercicio.acordes:
            _, instante = correr(
                ev, [completo(acorde.midis)] * CUADROS_PARA_ACORDE_ESTABLE, instante
            )
            _, instante = correr(ev, [silencio()] * CUADROS_PARA_ACORDE_ESTABLE, instante)
        assert ev.estado.completado is True

    def test_dos_acordes_iguales_seguidos_necesitan_soltar_entre_medias(self):
        """Sin esto, la cola del primero regala el segundo sin mover un dedo."""
        ev = EvaluadorCambios(generar_cambios(claves=("do", "do_bis"), repeticiones=1))
        ...  # ver nota de implementacion: se usa una pareja de claves distintas
```

> **Nota para quien implemente**: la prueba de dos acordes iguales seguidos no se
> puede escribir con `generar_cambios`, porque el generador exige claves
> distintas. Se escribe construyendo el `Ejercicio` a mano con el mismo
> `AcordeEsperado` dos veces:
>
> ```python
> def test_dos_acordes_iguales_seguidos_necesitan_soltar_entre_medias(self):
>     do = acorde_de_clave("do", PERFILES_DE_FABRICA["guitarra_estandar"])
>     ejercicio = Ejercicio(
>         clave="do_do", nombre="Do, Do", descripcion="", notas=(),
>         acordes=(do, do), tempo=60, perfil="guitarra_estandar",
>     )
>     ev = EvaluadorCambios(ejercicio)
>     estado, _ = correr(ev, [completo(do.midis)] * (CUADROS_PARA_ACORDE_ESTABLE * 3))
>     assert estado.indice == 1, "sostener no puede valer por dos acordes"
> ```

```python
class TestFallo:
    def test_una_cuerda_muda_sale_nombrada_en_el_estado(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado, _ = correr(ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE)
        assert estado.faltan == (midis[-1],)
        assert estado.indice == 0

    def test_el_silencio_no_cuenta_como_intento(self):
        ev = evaluador()
        estado, _ = correr(ev, [silencio()] * 20)
        assert estado.intentos == 0

    def test_insistir_mal_cuenta_intentos(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        for _ in range(3):
            correr(ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE)
            correr(ev, [silencio()] * CUADROS_PARA_ACORDE_ESTABLE)
        assert ev.estado.intentos >= 3

    def test_tras_los_intentos_pactados_aparece_la_ayuda_sin_saltar_el_acorde(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        for _ in range(ev.intentos_para_ayuda):
            correr(ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE)
            correr(ev, [silencio()] * CUADROS_PARA_ACORDE_ESTABLE)
        assert ev.estado.ayuda_visible is True
        assert ev.estado.indice == 0

    def test_la_ayuda_aparece_tambien_por_tiempo(self):
        """Mismo respaldo temporal que la 2a: no depende de contar intentos."""
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado = ev.procesar(incompleto(midis, {midis[-1]}), 0.0)
        estado = ev.procesar(incompleto(midis, {midis[-1]}), ev.segundos_para_ayuda + 0.1)
        assert estado.ayuda_visible is True


class TestTiempoDeCambio:
    def test_el_primer_acorde_no_tiene_tiempo_de_cambio(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado, _ = correr(ev, [completo(midis)] * CUADROS_PARA_ACORDE_ESTABLE)
        assert estado.ultimo_cambio_s is None

    def test_el_segundo_mide_los_segundos_desde_el_primero(self):
        ev = evaluador()
        primero, segundo = ev.ejercicio.acordes[0], ev.ejercicio.acordes[1]
        _, instante = correr(ev, [completo(primero.midis)] * CUADROS_PARA_ACORDE_ESTABLE)
        _, instante = correr(ev, [silencio()] * 50, instante)  # algo mas de un segundo
        estado, _ = correr(ev, [completo(segundo.midis)] * CUADROS_PARA_ACORDE_ESTABLE, instante)
        assert estado.ultimo_cambio_s == pytest.approx(instante, abs=0.2)

    def test_el_informe_promedia_los_tiempos_de_cambio(self):
        ev = evaluador()
        instante = 0.0
        for acorde in ev.ejercicio.acordes:
            _, instante = correr(
                ev, [completo(acorde.midis)] * CUADROS_PARA_ACORDE_ESTABLE, instante
            )
            _, instante = correr(ev, [silencio()] * 20, instante)
        informe = ev.resultado()
        assert informe.tiempo_medio_de_cambio_s is not None
        assert informe.tiempo_medio_de_cambio_s > 0.0

    def test_un_ejercicio_sin_ningun_cambio_logrado_no_promedia_nada(self):
        """Nunca sonar ningun acorde no da un tiempo medio de cero: da ninguno."""
        ev = evaluador()
        informe = ev.resultado()
        assert informe.tiempo_medio_de_cambio_s is None


class TestInforme:
    def test_el_informe_dice_que_cuerdas_fallaron_mas(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        for _ in range(3):
            correr(ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE)
            correr(ev, [silencio()] * CUADROS_PARA_ACORDE_ESTABLE)
        assert midis[-1] in ev.resultado().cuerdas_problematicas

    def test_el_diccionario_del_estado_es_serializable(self):
        ev = evaluador()
        como_dict = ev.estado.a_dict()
        assert set(como_dict) >= {
            "indice", "total", "intentos", "ayuda_visible", "completado",
            "acorde_actual", "faltan", "ultimo_cambio_s",
        }

    def test_un_ejercicio_de_notas_no_se_puede_evaluar_aqui(self):
        from nucleo.ejercicios.generadores.escalas import generar_escala

        with pytest.raises(ValueError, match="acordes"):
            EvaluadorCambios(generar_escala())
```

- [ ] **Step 2: Comprobar que fallan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_cambios.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Escribir `nucleo/ejercicios/cambios.py`**

Reglas que el código tiene que implementar, todas razonadas en la spec §4.3:

1. **Constructor** rechaza un `Ejercicio` sin `acordes` (`ValueError` nombrando «acordes»).
2. **Acierto**: `estado == "completo"` durante `cuadros_para_acorde_estable` cuadros seguidos. Al acertar, se avanza el índice, se registra el instante y se exige **soltar** (un cuadro que no sea `"completo"`) antes de poder acertar el siguiente. Ese «soltar» es lo que impide que sostener un acorde valga por dos.
3. **Intento fallido**: una racha de `cuadros_para_acorde_estable` cuadros `"incompleto"` seguidos cuenta **un** intento y guarda las ausencias. La racha se reinicia al salir de `"incompleto"`, de modo que insistir cuenta varios intentos y un solo rasgueo torcido cuenta uno.
4. **El silencio no cuenta.** Ni intento ni fallo; rompe las dos rachas.
5. **Ayuda** tras `intentos_para_ayuda` intentos fallidos en el mismo acorde, **o** tras `segundos_para_ayuda` desde el primer cuadro con señal (no silencio) que pudiera ser un intento de este acorde. Igual que la 2a, y por el mismo motivo: el conteo de intentos puede no llegar nunca.
6. **Tiempo de cambio**: segundos entre el acierto anterior y este. `None` para el primer acorde.
7. **Candado reentrante** (`threading.RLock`), como `EvaluadorEjercicio`: se muta desde el hilo de análisis y se lee desde el hilo HTTP a 30 Hz.
8. `resultado()` devuelve `InformeCambios` con `tiempo_medio_de_cambio_s` (`None` si no hubo ningún cambio medido), `por_acorde` (intentos y tiempo de cambio por acorde) y `cuerdas_problematicas` (MIDI que faltaron más veces, de más a menos).

- [ ] **Step 4: Comprobar que pasan**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_cambios.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nucleo/ejercicios/cambios.py tests/test_cambios.py
git commit -m "feat: el evaluador de cambios mide el acorde completo y el tiempo de cambio"
```

---

### Task 6: Enchufar la familia en el servidor

**Files:**
- Modify: `servidor/ejercicios.py`, `servidor/app.py`
- Test: `tests/test_servidor_cambios.py`

**Interfaces:**
- Consumes: `generar_cambios`, `DIGITACIONES` de Task 4; `EvaluadorCambios` de Task 5; `DetectorAcordes` de Task 2.
- Produces: la familia `"cambios"` en el generador de `SesionPractica`, y `DIGITACIONES` expuesto en el endpoint de catálogo junto a `ACORDES`, `ESCALAS` e `INTERVALOS`.

Lo que hay que hacer, leyendo primero `servidor/ejercicios.py` completo:

- [ ] **Step 1**: leer `servidor/ejercicios.py` y `servidor/app.py` y anotar cómo se despacha la familia y dónde se elige el evaluador.
- [ ] **Step 2**: escribir las pruebas: generar la familia `"cambios"` por el endpoint devuelve un ejercicio con `acordes` y sin `notas`; iniciarlo construye un `EvaluadorCambios` y no un `EvaluadorEjercicio`; el catálogo lista las ocho digitaciones; una familia inexistente sigue dando el mismo error que antes.
- [ ] **Step 3**: en `SesionPractica`, despachar `"cambios"` a `generar_cambios` y, al iniciar, elegir el evaluador según `ejercicio.acordes`. El hilo de análisis alimenta además un `DetectorAcordes` cuando el ejercicio es de acordes.
- [ ] **Step 4**: `uv run pytest tests/ -q` — **toda** la suite, porque esto toca el armazón.
- [ ] **Step 5**: commit.

---

### Task 7: La pantalla de cambios

**Files:**
- Modify: `interfaz/src/` — pantalla de ejercicios, según lo que haya allí.
- Test: los `.test.tsx` de los componentes tocados.

El requisito de la spec §8: se ve la digitación en el mástil y, cuando falta una cuerda, se ve **cuál**. Los colores por cuerda de `geometriaCarril.ts` (`colorDeCuerda`) ya existen y son el idioma visual del proyecto: una cuerda que falta se marca con su color apagado o tachada, no con un texto.

- [ ] **Step 1**: leer la pantalla de ejercicios actual y el tipo que recibe.
- [ ] **Step 2**: escribir las pruebas con vitest: un acorde se dibuja con sus seis cuerdas; una cuerda muda (`None`) se distingue de una al aire (0); con `faltan` no vacío, esa cuerda se marca; el tiempo de cambio se muestra cuando lo hay y no cuando es `null`.
- [ ] **Step 3**: implementar.
- [ ] **Step 4**: `cd interfaz && pnpm test && pnpm lint && pnpm build`.
- [ ] **Step 5**: commit.

---

### Task 8: El carril deja de excluir acordes

**Files:**
- Modify: el seguimiento del carril (`nucleo/piezas/` y `servidor/piezas.py`, según lo que haya).
- Test: `tests/test_estudio.py`, `tests/test_gemelo_interprete.py`.

- [ ] **Step 1**: leer cómo el carril resuelve la nota actual y dónde marca `tiene_acordes`.
- [ ] **Step 2**: escribir la prueba: una pieza con un acorde cobra **todas** sus notas, y `tiene_acordes` deja de significar «no medible». Cambiar explícitamente `test_el_acorde_se_reduce_a_la_nota_mas_grave` y `test_de_un_acorde_solo_una_nota_es_medible_y_el_compas_queda_marcado`, que hoy afirman lo contrario: el cambio de sentido de esas dos pruebas es parte del trabajo, no un daño colateral.
- [ ] **Step 3**: implementar: al llegar a un grupo de notas con el mismo `inicio_pulsos`, usar `DetectorAcordes` con sus MIDI y cobrar las presentes.
- [ ] **Step 4**: `uv run pytest tests/ -q`.
- [ ] **Step 5**: commit.

---

### Task 9: El README deja de decir que los acordes no se siguen

**Files:**
- Modify: `README.md`

Hay al menos siete sitios que afirman la limitación que esta etapa levanta: líneas ~222, ~401, ~511, ~750 y la lista de etapas (~961). Todos tienen que cambiar, y el que **no** cambia es el que dice que no hay transcripción libre: eso sigue siendo verdad y ahora hay que escribirlo donde antes no hacía falta.

- [ ] **Step 1**: `grep -n "acorde" README.md` y listar cada sitio.
- [ ] **Step 2**: reescribir cada uno. Añadir lo nuevo: qué mide el ejercicio de cambios, que el tiempo de cambio es la cifra de cabecera, y la limitación que queda (no se nombra un acorde que no se haya pedido; no hay cents por nota dentro del acorde).
- [ ] **Step 3**: añadir a los pendientes del usuario las tres comprobaciones con guitarra de la spec §6: rasguear los ocho acordes, dejar una cuerda muda a propósito, y calibrar `UMBRAL_PRESENCIA`.
- [ ] **Step 4**: mover la 2b de «siguientes» a «completas» en **Estado**, con la salvedad de que nada se ha probado con el cable.
- [ ] **Step 5**: commit.
