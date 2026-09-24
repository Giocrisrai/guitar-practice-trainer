# Motor de ejercicios monofónicos — Plan de implementación (etapa 2a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un motor que genere ejercicios de guitarra (escalas, arpegios, intervalos y lectura del mástil), escuche lo que el usuario toca y lo corrija nota a nota, con metrónomo y notas de referencia sintetizadas.

**Architecture:** `nucleo/ejercicios/` es Python puro: un modelo común de ejercicio, la teoría musical como patrones sobre ℤ₁₂, cuatro generadores que producen ese modelo, un detector de ataques que decide cuándo empieza una nota nueva, y una máquina de estados que corrige. `nucleo/sintesis.py` genera el sonido con numpy y lo saca por CoreAudio. `servidor/` registra el módulo de ejercicios junto al afinador y expone su estado; `interfaz/` dibuja la pantalla reutilizando el mástil de la etapa 1.

**Tech Stack:** Python 3.13.1 gestionado con **uv**, numpy, scipy, sounddevice (PortAudio/CoreAudio), FastAPI, pytest; React + Vite con pnpm.

**Spec:** `docs/superpowers/specs/2026-09-19-ejercicios-monofonicos-design.md`

## Global Constraints

- Python **3.13.1** vía uv (`.python-version`). Los comandos son `uv run ...`, nunca `.venv/bin/...` ni `pip install`.
- Gestor de paquetes JavaScript: **pnpm**. Nunca `npm`.
- Comentarios, nombres de variables, funciones y clases **en español**.
- Docstrings con **notación matemática clara** cuando haya fórmulas.
- Preferir **numpy/scipy** sobre implementaciones manuales.
- Pruebas con **pytest**. Ninguna prueba abre el dispositivo de audio real.
- `nucleo/` **no importa** nada de `servidor/` ni de `interfaz/`.
- Una nota correcta pero desafinada **cuenta como acierto**; la desviación se informa aparte.
- Un fallo **no avanza** el ejercicio: se espera a que el usuario acierte.
- Tras **5** intentos fallidos en la misma nota, el mástil resalta dónde está.
- Salto mínimo de ataque: **6,0 dB**. Periodo refractario: **50 ms**. Espera de estabilización: **60 ms**. Los tres son provisionales y configurables.
- Tolerancia de afinación para el informe: **±5 cents** (la de `nucleo/musica.py`), nunca para bloquear.
- Estado actual que no debe romperse: **148 pruebas de Python** pasan, **18 se saltan** (esperan grabaciones de audio que aún no existen), **23 de interfaz** pasan.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `nucleo/ejercicios/__init__.py` | Paquete |
| `nucleo/ejercicios/modelo.py` | `Ejercicio`, `NotaEsperada`, `IntentoNota`, `ResultadoEjercicio` |
| `nucleo/ejercicios/teoria.py` | Escalas, acordes e intervalos como patrones sobre ℤ₁₂; notas alcanzables del mástil |
| `nucleo/ejercicios/generadores/escalas.py` | Escalas en una posición |
| `nucleo/ejercicios/generadores/arpegios.py` | Arpegios de acorde, nota a nota |
| `nucleo/ejercicios/generadores/intervalos.py` | Intervalos y entrenamiento de oído |
| `nucleo/ejercicios/generadores/lectura.py` | Lectura de notas en el mástil |
| `nucleo/ejercicios/ataques.py` | Detección de ataques a partir de la energía |
| `nucleo/ejercicios/evaluacion.py` | La máquina de estados que corrige |
| `nucleo/sintesis.py` | Tonos y metrónomo, salida por CoreAudio |
| `servidor/ejercicios.py` | Sesión de práctica y endpoints |
| `interfaz/src/Ejercicios.tsx` | La pantalla |
| `interfaz/src/Configurador.tsx` | Elección de familia y parámetros |
| `interfaz/src/Informe.tsx` | El informe final |
| `tests/` | pytest |

**Por qué los generadores viven en su propio subpaquete:** cada familia es una función pura independiente, y añadir la quinta (modos griegos, digitaciones de tres notas por cuerda) debe ser un archivo nuevo sin tocar nada. Separarlos ahora cuesta un directorio; no separarlos cuesta reescribir un archivo que crece.

---

### Task 1: El modelo común del ejercicio

**Files:**
- Create: `nucleo/ejercicios/__init__.py`
- Create: `nucleo/ejercicios/modelo.py`
- Test: `tests/test_modelo_ejercicios.py`

**Interfaces:**
- Consumes: `nucleo.musica.Posicion`, `nucleo.musica.nombre_de_midi`
- Produces:
  - `NotaEsperada(midi: int, posiciones: tuple[Posicion, ...], pulsos: float = 1.0, referencia_midi: int | None = None)` — dataclass congelada, con la propiedad `nombre: str`
  - `Ejercicio(clave: str, nombre: str, descripcion: str, notas: tuple[NotaEsperada, ...], tempo: int, perfil: str)` — dataclass congelada, con `__len__` y `a_dict() -> dict`
  - `IntentoNota(indice: int, midi: int, intentos: int, cents: float | None, instante: float | None, ayuda_mostrada: bool = False)` — dataclass congelada, con las propiedades `nombre`, `acertada`, `a_la_primera`
  - `ResultadoEjercicio(ejercicio: str, notas: tuple[IntentoNota, ...], completado: bool)` — dataclass congelada, con las propiedades `aciertos_a_la_primera`, `desviacion_mediana_cents`, `notas_dificiles`, `regularidad_ms`, y `a_dict() -> dict`

**Contexto para quien implementa.** Este archivo es el vocabulario que comparten las cuatro familias de ejercicios, el evaluador y la pantalla. Que las cuatro produzcan la **misma** estructura es lo que permite escribir el evaluador y la interfaz una sola vez; si cada familia trajera su propio formato, habría cuatro evaluadores.

Tres detalles que merecen atención:

`NotaEsperada.posiciones` es una **tupla de posiciones**, no una. Un Mi puede tocarse en varios sitios del mástil y el ejercicio no debe exigir uno concreto salvo que el generador lo restrinja. Esto hereda la decisión de la etapa 1 de no fingir certeza sobre dónde tocaste.

`IntentoNota.cents` es `None` cuando la nota **no se acertó**. No es cero: cero significa que la acertaste perfectamente afinada. Confundir ambos falsearía el informe.

`regularidad_ms` es la **desviación típica** de los intervalos entre ataques consecutivos, en milisegundos. Mide constancia, no velocidad: tocar lento y parejo da un número bajo, y es lo que interesa al practicar. Necesita al menos tres notas acertadas para tener sentido; con menos devuelve `None`.

`NotaEsperada.referencia_midi` es la nota que el software **hace sonar** antes de pedir la tuya, y es `None` en los ejercicios donde no suena nada. La necesita el entrenamiento de oído: "esto es un Do, tócame la tercera mayor". Va en el modelo desde el principio porque añadir un campo después obliga a revisar el evaluador, la serialización y la pantalla a la vez.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_modelo_ejercicios.py
import pytest

from nucleo.ejercicios.modelo import Ejercicio, IntentoNota, NotaEsperada, ResultadoEjercicio
from nucleo.musica import Posicion


def nota(midi: int, pulsos: float = 1.0) -> NotaEsperada:
    return NotaEsperada(midi=midi, posiciones=(Posicion(cuerda=6, traste=0),), pulsos=pulsos)


def test_la_nota_esperada_conoce_su_nombre():
    assert nota(40).nombre == "E2"


def test_una_nota_puede_tocarse_en_varios_sitios():
    """El ejercicio no exige una posicion concreta salvo que el generador la restrinja."""
    esperada = NotaEsperada(
        midi=45, posiciones=(Posicion(cuerda=5, traste=0), Posicion(cuerda=6, traste=5))
    )
    assert len(esperada.posiciones) == 2


def test_el_ejercicio_sabe_cuantas_notas_tiene():
    ejercicio = Ejercicio(
        clave="escala_do_mayor",
        nombre="Escala de Do mayor",
        descripcion="Una octava en la segunda posicion",
        notas=(nota(48), nota(50), nota(52)),
        tempo=80,
        perfil="guitarra_estandar",
    )
    assert len(ejercicio) == 3


def test_el_ejercicio_se_serializa_para_la_interfaz():
    ejercicio = Ejercicio(
        clave="prueba",
        nombre="Prueba",
        descripcion="",
        notas=(nota(40),),
        tempo=60,
        perfil="guitarra_estandar",
    )
    datos = ejercicio.a_dict()
    assert set(datos) == {"clave", "nombre", "descripcion", "notas", "tempo", "perfil"}
    assert datos["notas"][0] == {
        "midi": 40,
        "nombre": "E2",
        "posiciones": [{"cuerda": 6, "traste": 0}],
        "pulsos": 1.0,
        "referencia_midi": None,
    }


def test_una_nota_puede_llevar_una_referencia_que_suena_antes():
    """El entrenamiento de oido hace sonar una nota y pide otra a cierto intervalo."""
    esperada = NotaEsperada(
        midi=52, posiciones=(Posicion(cuerda=4, traste=2),), referencia_midi=48
    )
    assert esperada.referencia_midi == 48
    assert esperada.a_dict()["referencia_midi"] == 48


def test_sin_referencia_el_campo_es_none():
    assert nota(40).referencia_midi is None


def test_una_nota_sin_acertar_tiene_cents_none_no_cero():
    """Cero cents significa acierto perfecto; None significa que no se acerto."""
    fallada = IntentoNota(indice=0, midi=40, intentos=3, cents=None, instante=None)
    perfecta = IntentoNota(indice=1, midi=42, intentos=1, cents=0.0, instante=1.0)
    assert fallada.acertada is False
    assert perfecta.acertada is True


def test_a_la_primera_exige_acierto_y_un_solo_intento():
    assert IntentoNota(0, 40, 1, 0.0, 1.0).a_la_primera is True
    assert IntentoNota(0, 40, 2, 0.0, 1.0).a_la_primera is False
    assert IntentoNota(0, 40, 1, None, None).a_la_primera is False


def test_el_informe_cuenta_los_aciertos_a_la_primera():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 2.0, 0.0),
            IntentoNota(1, 42, 3, -4.0, 1.0),
            IntentoNota(2, 44, 1, 1.0, 2.0),
        ),
        completado=True,
    )
    assert resultado.aciertos_a_la_primera == 2


def test_el_informe_da_la_desviacion_mediana():
    """Mediana y no media: un golpe desafinado aislado no debe definir la sesion."""
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 2.0, 0.0),
            IntentoNota(1, 42, 1, 4.0, 1.0),
            IntentoNota(2, 44, 1, 60.0, 2.0),
        ),
        completado=True,
    )
    assert resultado.desviacion_mediana_cents == pytest.approx(4.0)


def test_las_notas_sin_acertar_no_entran_en_la_desviacion():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(IntentoNota(0, 40, 1, 6.0, 0.0), IntentoNota(1, 42, 5, None, None)),
        completado=False,
    )
    assert resultado.desviacion_mediana_cents == pytest.approx(6.0)


def test_sin_ninguna_nota_acertada_no_hay_desviacion():
    resultado = ResultadoEjercicio(
        ejercicio="prueba", notas=(IntentoNota(0, 40, 5, None, None),), completado=False
    )
    assert resultado.desviacion_mediana_cents is None


def test_las_notas_dificiles_son_las_que_costaron_tres_intentos_o_mas():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 0.0, 0.0),
            IntentoNota(1, 42, 3, 0.0, 1.0),
            IntentoNota(2, 44, 7, 0.0, 2.0),
        ),
        completado=True,
    )
    assert [n.midi for n in resultado.notas_dificiles] == [42, 44]


def test_la_regularidad_mide_constancia_no_velocidad():
    """Tocar lento pero parejo da una regularidad buena."""
    lento_parejo = ResultadoEjercicio(
        ejercicio="prueba",
        notas=tuple(IntentoNota(i, 40 + i, 1, 0.0, float(i) * 2.0) for i in range(4)),
        completado=True,
    )
    assert lento_parejo.regularidad_ms == pytest.approx(0.0, abs=0.01)


def test_la_regularidad_crece_con_la_irregularidad():
    irregular = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 0.0, 0.0),
            IntentoNota(1, 41, 1, 0.0, 1.0),
            IntentoNota(2, 42, 1, 0.0, 1.2),
            IntentoNota(3, 43, 1, 0.0, 3.0),
        ),
        completado=True,
    )
    assert irregular.regularidad_ms > 300.0


def test_con_menos_de_tres_notas_acertadas_no_hay_regularidad():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(IntentoNota(0, 40, 1, 0.0, 0.0), IntentoNota(1, 41, 1, 0.0, 1.0)),
        completado=True,
    )
    assert resultado.regularidad_ms is None


def test_el_resultado_se_serializa_para_la_interfaz():
    resultado = ResultadoEjercicio(
        ejercicio="prueba", notas=(IntentoNota(0, 40, 1, 2.0, 0.0),), completado=True
    )
    datos = resultado.a_dict()
    assert set(datos) == {
        "ejercicio",
        "completado",
        "notas",
        "aciertos_a_la_primera",
        "desviacion_mediana_cents",
        "regularidad_ms",
    }
    assert datos["notas"][0]["nombre"] == "E2"
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_modelo_ejercicios.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.ejercicios'`

- [ ] **Step 3: Implementar `nucleo/ejercicios/modelo.py`**

```python
"""Vocabulario comun de los ejercicios.

Las cuatro familias de ejercicios producen esta misma estructura. Esa es la razon
de que el evaluador y la pantalla se escriban una sola vez: si cada familia
trajera su propio formato, harian falta cuatro evaluadores.
"""

from dataclasses import dataclass

import numpy as np

from nucleo.musica import Posicion, nombre_de_midi

# A partir de cuantos intentos se considera que una nota costo trabajo.
INTENTOS_NOTA_DIFICIL = 3

# Minimo de notas acertadas para que la regularidad signifique algo: con dos
# ataques solo hay un intervalo y su desviacion tipica es siempre cero.
MINIMO_NOTAS_REGULARIDAD = 3


@dataclass(frozen=True)
class NotaEsperada:
    """Una nota que el ejercicio pide tocar.

    posiciones es una tupla y no una sola posicion a proposito: un Mi puede
    tocarse en varios sitios del mastil, y el ejercicio no debe exigir uno
    concreto salvo que el generador lo restrinja.

    pulsos es la duracion en pulsos de metronomo; el modo por turnos no la usa,
    pero el modo en tiempo real la necesitara y guardarla ahora no cuesta nada.

    referencia_midi es la nota que el software hace sonar antes de pedir esta, y
    es None en los ejercicios donde no suena nada. La necesita el entrenamiento
    de oido: "esto es un Do, tocame la tercera mayor".
    """

    midi: int
    posiciones: tuple[Posicion, ...]
    pulsos: float = 1.0
    referencia_midi: int | None = None

    @property
    def nombre(self) -> str:
        """Nombre en notacion cientifica, por ejemplo "E2"."""
        return nombre_de_midi(self.midi)

    def a_dict(self) -> dict:
        return {
            "midi": self.midi,
            "nombre": self.nombre,
            "posiciones": [{"cuerda": p.cuerda, "traste": p.traste} for p in self.posiciones],
            "pulsos": self.pulsos,
            "referencia_midi": self.referencia_midi,
        }


@dataclass(frozen=True)
class Ejercicio:
    """Un ejercicio generado: que tocar, en que orden y a que tempo."""

    clave: str
    nombre: str
    descripcion: str
    notas: tuple[NotaEsperada, ...]
    tempo: int
    perfil: str

    def __len__(self) -> int:
        return len(self.notas)

    def a_dict(self) -> dict:
        return {
            "clave": self.clave,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "notas": [n.a_dict() for n in self.notas],
            "tempo": self.tempo,
            "perfil": self.perfil,
        }


@dataclass(frozen=True)
class IntentoNota:
    """Lo ocurrido con una nota del ejercicio.

    cents es None cuando la nota NO se acerto. No es cero: cero significa que se
    acerto perfectamente afinada, y confundir ambos falsearia el informe.
    """

    indice: int
    midi: int
    intentos: int
    cents: float | None
    instante: float | None
    ayuda_mostrada: bool = False

    @property
    def nombre(self) -> str:
        return nombre_de_midi(self.midi)

    @property
    def acertada(self) -> bool:
        return self.cents is not None

    @property
    def a_la_primera(self) -> bool:
        return self.acertada and self.intentos == 1

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "midi": self.midi,
            "nombre": self.nombre,
            "intentos": self.intentos,
            "cents": None if self.cents is None else round(self.cents, 1),
            "instante": self.instante,
            "ayuda_mostrada": self.ayuda_mostrada,
        }


@dataclass(frozen=True)
class ResultadoEjercicio:
    """El informe que se muestra al terminar."""

    ejercicio: str
    notas: tuple[IntentoNota, ...]
    completado: bool

    @property
    def _acertadas(self) -> tuple[IntentoNota, ...]:
        return tuple(n for n in self.notas if n.acertada)

    @property
    def aciertos_a_la_primera(self) -> int:
        """Cuantas notas salieron al primer intento."""
        return sum(1 for n in self.notas if n.a_la_primera)

    @property
    def desviacion_mediana_cents(self) -> float | None:
        """Mediana de la desviacion de las notas acertadas, o None si no hay ninguna.

        Se usa la mediana y no la media por el mismo motivo que en el suavizado del
        afinador: un golpe desafinado aislado no debe definir la sesion entera.
        """
        acertadas = self._acertadas
        if not acertadas:
            return None
        return float(np.median([n.cents for n in acertadas]))

    @property
    def notas_dificiles(self) -> tuple[IntentoNota, ...]:
        """Notas que costaron tres intentos o mas: donde conviene insistir."""
        return tuple(n for n in self.notas if n.intentos >= INTENTOS_NOTA_DIFICIL)

    @property
    def regularidad_ms(self) -> float | None:
        """Desviacion tipica de los intervalos entre ataques, en milisegundos.

            regularidad = desv_tipica( t[i+1] - t[i] ) · 1000

        Mide constancia, no velocidad: tocar lento y parejo da un numero bajo, que
        es justo lo que interesa al practicar. Devuelve None con menos de tres
        notas acertadas, porque con dos solo hay un intervalo y su desviacion
        tipica es siempre cero, lo que fingiria una regularidad perfecta.
        """
        instantes = [n.instante for n in self._acertadas if n.instante is not None]
        if len(instantes) < MINIMO_NOTAS_REGULARIDAD:
            return None
        intervalos = np.diff(np.array(instantes, dtype=np.float64))
        return float(np.std(intervalos) * 1000.0)

    def a_dict(self) -> dict:
        mediana = self.desviacion_mediana_cents
        regularidad = self.regularidad_ms
        return {
            "ejercicio": self.ejercicio,
            "completado": self.completado,
            "notas": [n.a_dict() for n in self.notas],
            "aciertos_a_la_primera": self.aciertos_a_la_primera,
            "desviacion_mediana_cents": None if mediana is None else round(mediana, 1),
            "regularidad_ms": None if regularidad is None else round(regularidad, 1),
        }
```

También crear `nucleo/ejercicios/__init__.py` vacío.

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_modelo_ejercicios.py -v`
Esperado: PASS, 17 pruebas.

- [ ] **Step 5: Ejecutar la batería completa**

Run: `uv run pytest -q`
Esperado: 165 pasan, 18 saltadas.

- [ ] **Step 6: Commit**

```bash
git add nucleo/ejercicios/ tests/test_modelo_ejercicios.py
git commit -m "feat: modelo comun de ejercicios e informe de resultados"
```

---

### Task 2: La teoría musical como patrones sobre ℤ₁₂

**Files:**
- Create: `nucleo/ejercicios/teoria.py`
- Test: `tests/test_teoria.py`

**Interfaces:**
- Consumes: `nucleo.afinaciones.PerfilAfinacion`, `nucleo.musica.Posicion`, `nucleo.musica.frecuencia_a_midi`, `nucleo.musica.nombre_de_midi`
- Produces:
  - `ESCALAS: dict[str, tuple[int, ...]]` con las claves `"mayor"`, `"menor_natural"`, `"pentatonica_mayor"`, `"pentatonica_menor"`, `"blues"`
  - `ACORDES: dict[str, tuple[int, ...]]` con las claves `"mayor"`, `"menor"`, `"septima"`, `"menor_septima"`
  - `INTERVALOS: dict[str, int]` con los doce intervalos hasta la octava
  - `NOMBRES_INTERVALOS: dict[int, str]`
  - `clases_del_patron(raiz_midi: int, patron: tuple[int, ...]) -> frozenset[int]`
  - `notas_del_patron(raiz_midi: int, patron: tuple[int, ...], midi_minimo: int, midi_maximo: int) -> tuple[int, ...]`
  - `notas_alcanzables(perfil: PerfilAfinacion, traste_minimo: int, traste_maximo: int) -> dict[int, tuple[Posicion, ...]]`
  - `nombre_de_intervalo(semitonos: int) -> str`

**Contexto para quien implementa.** Aquí está la matemática del proyecto, y conviene entenderla porque hace el resto trivial.

Una escala no es una lista de notas: es un subconjunto de **ℤ₁₂**, el conjunto de las doce clases de altura módulo la octava. La escala mayor es `{0,2,4,5,7,9,11}` medida en semitonos desde su raíz. Transportarla a otra tonalidad es **sumar módulo 12**: Sol mayor es esa misma clase desplazada 7.

Eso convierte "generar la escala de Sol mayor en la quinta posición" en dos operaciones de conjuntos: transportar el patrón para obtener las clases válidas, e **intersecar** con las notas que el mástil alcanza en esa zona. Sin esta abstracción, cada escala en cada tonalidad en cada posición sería una tabla escrita a mano; con ella, añadir la escala dórica es añadir `(0,2,3,5,7,9,10)` al diccionario.

`notas_alcanzables` hace el trabajo sucio: recorre las cuerdas del perfil y los trastes del rango, y devuelve un diccionario de número MIDI a las posiciones donde aparece. Un mismo MIDI sale varias veces —la ambigüedad del mástil que ya conocemos de la etapa 1— y por eso el valor es una tupla.

Ojo con un detalle: `Cuerda.frecuencia` está en Hz y hay que convertirla a MIDI con `frecuencia_a_midi` y redondear. No inventes una tabla paralela de números MIDI por cuerda: duplicarías la fuente de verdad que ya vive en `nucleo/afinaciones.py`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_teoria.py
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.ejercicios.teoria import (
    ACORDES,
    ESCALAS,
    INTERVALOS,
    clases_del_patron,
    nombre_de_intervalo,
    notas_alcanzables,
    notas_del_patron,
)
from nucleo.musica import Posicion

GUITARRA = PERFILES["guitarra_estandar"]
DO3 = 48  # Do de la tercera octava


def test_la_escala_mayor_tiene_siete_grados():
    assert ESCALAS["mayor"] == (0, 2, 4, 5, 7, 9, 11)


def test_las_pentatonicas_tienen_cinco():
    assert len(ESCALAS["pentatonica_mayor"]) == 5
    assert len(ESCALAS["pentatonica_menor"]) == 5


def test_el_acorde_mayor_es_fundamental_tercera_quinta():
    assert ACORDES["mayor"] == (0, 4, 7)


def test_el_acorde_menor_baja_la_tercera():
    assert ACORDES["menor"] == (0, 3, 7)


def test_transportar_es_sumar_modulo_doce():
    """Sol mayor es Do mayor desplazada siete semitonos."""
    do_mayor = clases_del_patron(DO3, ESCALAS["mayor"])
    sol_mayor = clases_del_patron(DO3 + 7, ESCALAS["mayor"])
    assert do_mayor == frozenset({0, 2, 4, 5, 7, 9, 11})
    assert sol_mayor == frozenset({(c + 7) % 12 for c in do_mayor})


def test_la_octava_de_la_raiz_no_cambia_las_clases():
    """Do3 y Do4 generan exactamente el mismo conjunto de clases."""
    assert clases_del_patron(DO3, ESCALAS["mayor"]) == clases_del_patron(DO3 + 12, ESCALAS["mayor"])


def test_las_notas_del_patron_salen_ordenadas_y_dentro_del_rango():
    notas = notas_del_patron(DO3, ESCALAS["mayor"], midi_minimo=DO3, midi_maximo=DO3 + 12)
    assert notas == (48, 50, 52, 53, 55, 57, 59, 60)
    assert list(notas) == sorted(notas)


def test_un_rango_vacio_no_da_notas():
    assert notas_del_patron(DO3, ESCALAS["mayor"], midi_minimo=60, midi_maximo=48) == ()


def test_el_mastil_alcanza_las_seis_cuerdas_al_aire():
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=0)
    assert sorted(alcanzables) == [40, 45, 50, 55, 59, 64]


def test_una_nota_ambigua_aparece_con_todas_sus_posiciones():
    """El La de 110 Hz es la 5a al aire y la 6a en el traste 5."""
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=5)
    assert Posicion(cuerda=5, traste=0) in alcanzables[45]
    assert Posicion(cuerda=6, traste=5) in alcanzables[45]


def test_las_posiciones_van_de_la_cuerda_mas_grave_a_la_mas_aguda():
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=5)
    cuerdas = [p.cuerda for p in alcanzables[45]]
    assert cuerdas == sorted(cuerdas, reverse=True)


def test_el_rango_de_trastes_se_respeta():
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=5, traste_maximo=8)
    for posiciones in alcanzables.values():
        for posicion in posiciones:
            assert 5 <= posicion.traste <= 8


def test_el_bajo_alcanza_sus_cuatro_cuerdas():
    alcanzables = notas_alcanzables(PERFILES["bajo_4"], traste_minimo=0, traste_maximo=0)
    assert sorted(alcanzables) == [28, 33, 38, 43]


def test_la_escala_en_una_posicion_es_la_interseccion_con_el_mastil():
    """Generar un ejercicio es intersecar el patron con lo que el mastil alcanza."""
    alcanzables = notas_alcanzables(GUITARRA, traste_minimo=0, traste_maximo=4)
    clases = clases_del_patron(DO3, ESCALAS["mayor"])
    en_posicion = sorted(m for m in alcanzables if m % 12 in clases)
    assert 40 in en_posicion  # E2 pertenece a Do mayor
    assert 41 not in en_posicion  # F2 tambien... comprobamos una que NO
    assert 42 not in en_posicion  # F#2 no pertenece a Do mayor


@pytest.mark.parametrize(
    "nombre, semitonos",
    [("unisono", 0), ("segunda_mayor", 2), ("tercera_mayor", 4), ("quinta_justa", 7), ("octava", 12)],
)
def test_los_intervalos_tienen_los_semitonos_correctos(nombre, semitonos):
    assert INTERVALOS[nombre] == semitonos


def test_el_intervalo_se_nombra_en_castellano():
    assert nombre_de_intervalo(7) == "quinta justa"
    assert nombre_de_intervalo(4) == "tercera mayor"


def test_un_intervalo_mayor_que_una_octava_se_reduce():
    """Una decima mayor suena como una tercera mayor una octava mas arriba."""
    assert nombre_de_intervalo(16) == nombre_de_intervalo(4)
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_teoria.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.ejercicios.teoria'`

- [ ] **Step 3: Implementar `nucleo/ejercicios/teoria.py`**

```python
"""Teoria musical como patrones sobre Z12.

Una escala no es una lista de notas: es un subconjunto de Z12, el conjunto de las
doce clases de altura modulo la octava. La escala mayor es {0,2,4,5,7,9,11}
medida en semitonos desde su raiz, y transportarla a otra tonalidad es sumar
modulo 12.

Esa abstraccion es lo que hace trivial el resto: generar "Sol mayor en la quinta
posicion" son dos operaciones de conjuntos, transportar el patron e intersecar
con lo que el mastil alcanza. Sin ella, cada escala en cada tonalidad en cada
posicion seria una tabla escrita a mano.
"""

from nucleo.afinaciones import PerfilAfinacion
from nucleo.musica import Posicion, frecuencia_a_midi

# Patrones de escala en semitonos desde la raiz. Anadir la dorica es anadir una
# linea: (0, 2, 3, 5, 7, 9, 10).
ESCALAS: dict[str, tuple[int, ...]] = {
    "mayor": (0, 2, 4, 5, 7, 9, 11),
    "menor_natural": (0, 2, 3, 5, 7, 8, 10),
    "pentatonica_mayor": (0, 2, 4, 7, 9),
    "pentatonica_menor": (0, 3, 5, 7, 10),
    "blues": (0, 3, 5, 6, 7, 10),
}

# Acordes como patrones de intervalos desde la fundamental.
ACORDES: dict[str, tuple[int, ...]] = {
    "mayor": (0, 4, 7),
    "menor": (0, 3, 7),
    "septima": (0, 4, 7, 10),
    "menor_septima": (0, 3, 7, 10),
}

INTERVALOS: dict[str, int] = {
    "unisono": 0,
    "segunda_menor": 1,
    "segunda_mayor": 2,
    "tercera_menor": 3,
    "tercera_mayor": 4,
    "cuarta_justa": 5,
    "tritono": 6,
    "quinta_justa": 7,
    "sexta_menor": 8,
    "sexta_mayor": 9,
    "septima_menor": 10,
    "septima_mayor": 11,
    "octava": 12,
}

NOMBRES_INTERVALOS: dict[int, str] = {
    0: "unisono",
    1: "segunda menor",
    2: "segunda mayor",
    3: "tercera menor",
    4: "tercera mayor",
    5: "cuarta justa",
    6: "tritono",
    7: "quinta justa",
    8: "sexta menor",
    9: "sexta mayor",
    10: "septima menor",
    11: "septima mayor",
    12: "octava",
}


def clases_del_patron(raiz_midi: int, patron: tuple[int, ...]) -> frozenset[int]:
    """Clases de altura del patron transportado a una raiz.

        clases = { (raiz + p) mod 12 : p en patron }

    La octava de la raiz es irrelevante: Do3 y Do4 producen el mismo conjunto,
    porque una clase de altura ignora en que octava suena la nota.
    """
    return frozenset((raiz_midi + paso) % 12 for paso in patron)


def notas_del_patron(
    raiz_midi: int, patron: tuple[int, ...], midi_minimo: int, midi_maximo: int
) -> tuple[int, ...]:
    """Notas concretas del patron dentro de un rango, ordenadas de grave a aguda.

    A diferencia de clases_del_patron, aqui si importa la octava: se devuelven
    numeros MIDI, no clases.
    """
    clases = clases_del_patron(raiz_midi, patron)
    return tuple(midi for midi in range(midi_minimo, midi_maximo + 1) if midi % 12 in clases)


def notas_alcanzables(
    perfil: PerfilAfinacion, traste_minimo: int, traste_maximo: int
) -> dict[int, tuple[Posicion, ...]]:
    """Notas que el mastil alcanza en un rango de trastes, con donde tocarlas.

    Devuelve un diccionario de numero MIDI a las posiciones que lo producen. Un
    mismo MIDI aparece varias veces —la ambiguedad del mastil que ya conocemos
    del afinador— y por eso el valor es una tupla, no una posicion suelta.

    Las posiciones van de la cuerda mas grave a la mas aguda, el mismo orden en
    que se dibuja el mastil.
    """
    limite_superior = min(traste_maximo, perfil.trastes)
    alcanzables: dict[int, list[Posicion]] = {}
    for cuerda in perfil.cuerdas:
        midi_al_aire = round(frecuencia_a_midi(cuerda.frecuencia))
        for traste in range(max(0, traste_minimo), limite_superior + 1):
            midi = midi_al_aire + traste
            alcanzables.setdefault(midi, []).append(Posicion(cuerda=cuerda.numero, traste=traste))
    return {
        midi: tuple(sorted(posiciones, key=lambda p: -p.cuerda))
        for midi, posiciones in alcanzables.items()
    }


def nombre_de_intervalo(semitonos: int) -> str:
    """Nombre en castellano de un intervalo, reducido a una octava.

    Una decima mayor (16 semitonos) se nombra como su tercera mayor equivalente:
    el nombre describe la relacion, no la distancia absoluta.
    """
    if semitonos == 12:
        return NOMBRES_INTERVALOS[12]
    return NOMBRES_INTERVALOS[semitonos % 12]
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_teoria.py -v`
Esperado: PASS, 21 pruebas.

- [ ] **Step 5: Ejecutar la batería completa**

Run: `uv run pytest -q`
Esperado: 186 pasan, 18 saltadas.

- [ ] **Step 6: Commit**

```bash
git add nucleo/ejercicios/teoria.py tests/test_teoria.py
git commit -m "feat: escalas, acordes e intervalos como patrones sobre Z12"
```

---

### Task 3: Generador de escalas

**Files:**
- Create: `nucleo/ejercicios/generadores/__init__.py`
- Create: `nucleo/ejercicios/generadores/escalas.py`
- Test: `tests/test_generador_escalas.py`

**Interfaces:**
- Consumes: `nucleo.ejercicios.modelo.Ejercicio`, `nucleo.ejercicios.modelo.NotaEsperada`, `nucleo.ejercicios.teoria.ESCALAS`, `nucleo.ejercicios.teoria.clases_del_patron`, `nucleo.ejercicios.teoria.notas_alcanzables`, `nucleo.afinaciones.PERFILES`, `nucleo.musica.nombre_de_midi`
- Produces:
  - `DIRECCIONES: tuple[str, ...]` = `("ascendente", "descendente", "ambas")`
  - `generar_escala(perfil_clave: str = "guitarra_estandar", raiz_midi: int = 48, tipo: str = "mayor", traste_minimo: int = 0, traste_maximo: int = 4, tempo: int = 80, direccion: str = "ambas") -> Ejercicio`

**Contexto para quien implementa.** Este es el primer generador y marca el patrón que seguirán los otros tres: una función pura que recibe parámetros y devuelve un `Ejercicio`. Nada de estado, nada de audio, nada de catálogos escritos a mano.

El algoritmo son tres líneas conceptuales: pide al mástil qué notas alcanza en el rango de trastes, pide a la teoría qué clases pertenecen a la escala, y se queda con la intersección ordenada de grave a aguda. Todo el trabajo lo hicieron las tareas 1 y 2.

Dos decisiones de diseño que debes respetar:

**`direccion="ambas"` no repite la nota más aguda.** Subir y bajar una escala es `do re mi fa sol fa mi re do`, no `...sol sol...`. Repetirla suena mal y descuadra la cuenta de notas.

**Una configuración imposible se rechaza al generar, no al tocar.** Si en ese rango de trastes no cae ninguna nota de la escala, la función lanza `ValueError` con un mensaje que diga qué escala y qué rango. La spec §5 exige que este error se detecte al generar: descubrirlo tocando sería descubrirlo tarde.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_generador_escalas.py
import pytest

from nucleo.ejercicios.generadores.escalas import generar_escala
from nucleo.ejercicios.teoria import ESCALAS, clases_del_patron

DO3 = 48


def test_la_escala_sale_ordenada_de_grave_a_aguda():
    ejercicio = generar_escala(raiz_midi=DO3, tipo="mayor", direccion="ascendente")
    midis = [n.midi for n in ejercicio.notas]
    assert midis == sorted(midis)


def test_todas_las_notas_pertenecen_a_la_escala():
    ejercicio = generar_escala(raiz_midi=DO3, tipo="mayor", traste_minimo=0, traste_maximo=4)
    clases = clases_del_patron(DO3, ESCALAS["mayor"])
    assert all(n.midi % 12 in clases for n in ejercicio.notas)


def test_ninguna_nota_cae_fuera_del_rango_de_trastes():
    ejercicio = generar_escala(traste_minimo=5, traste_maximo=8)
    for nota in ejercicio.notas:
        assert all(5 <= p.traste <= 8 for p in nota.posiciones)


def test_ambas_direcciones_sube_y_baja_sin_repetir_la_cumbre():
    """do re mi fa sol fa mi re do, no ...sol sol..."""
    ascendente = generar_escala(raiz_midi=DO3, direccion="ascendente")
    ambas = generar_escala(raiz_midi=DO3, direccion="ambas")
    assert len(ambas.notas) == 2 * len(ascendente.notas) - 1
    midis = [n.midi for n in ambas.notas]
    assert midis == sorted(midis[: len(ascendente.notas)]) + sorted(
        midis[len(ascendente.notas) :], reverse=True
    )


def test_descendente_es_la_ascendente_al_reves():
    ascendente = generar_escala(raiz_midi=DO3, direccion="ascendente")
    descendente = generar_escala(raiz_midi=DO3, direccion="descendente")
    assert [n.midi for n in descendente.notas] == [n.midi for n in ascendente.notas][::-1]


def test_cada_nota_trae_sus_posiciones_en_el_mastil():
    ejercicio = generar_escala()
    assert all(len(n.posiciones) >= 1 for n in ejercicio.notas)


def test_la_pentatonica_tiene_menos_notas_que_la_mayor():
    mayor = generar_escala(tipo="mayor", direccion="ascendente")
    pentatonica = generar_escala(tipo="pentatonica_mayor", direccion="ascendente")
    assert len(pentatonica.notas) < len(mayor.notas)


def test_el_ejercicio_se_describe_de_forma_legible():
    ejercicio = generar_escala(raiz_midi=DO3, tipo="mayor")
    assert "Do" in ejercicio.nombre or "C" in ejercicio.nombre
    assert ejercicio.descripcion


def test_el_tempo_y_el_perfil_viajan_en_el_ejercicio():
    ejercicio = generar_escala(tempo=95, perfil_clave="bajo_4")
    assert ejercicio.tempo == 95
    assert ejercicio.perfil == "bajo_4"


def test_un_tipo_de_escala_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="escala"):
        generar_escala(tipo="inventada")


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_escala(perfil_clave="ukelele")


def test_una_direccion_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="direccion"):
        generar_escala(direccion="en_zigzag")


def test_un_rango_sin_notas_de_la_escala_se_rechaza_al_generar():
    """La spec exige detectar esto al generar, no al tocar."""
    with pytest.raises(ValueError, match="ninguna nota"):
        generar_escala(traste_minimo=30, traste_maximo=30)


def test_el_bajo_genera_su_propia_escala():
    ejercicio = generar_escala(perfil_clave="bajo_5", raiz_midi=31, traste_minimo=0, traste_maximo=5)
    assert len(ejercicio.notas) > 0
    assert ejercicio.perfil == "bajo_5"
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_generador_escalas.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.ejercicios.generadores'`

- [ ] **Step 3: Implementar `nucleo/ejercicios/generadores/escalas.py`**

```python
"""Generador de ejercicios de escala en una posicion del mastil.

Marca el patron de los cuatro generadores: una funcion pura que recibe
parametros y devuelve un Ejercicio. Sin estado, sin audio, sin catalogos
escritos a mano.
"""

from nucleo.afinaciones import PERFILES
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import ESCALAS, clases_del_patron, notas_alcanzables
from nucleo.musica import nombre_de_midi

DIRECCIONES: tuple[str, ...] = ("ascendente", "descendente", "ambas")

NOMBRES_TIPOS: dict[str, str] = {
    "mayor": "mayor",
    "menor_natural": "menor natural",
    "pentatonica_mayor": "pentatonica mayor",
    "pentatonica_menor": "pentatonica menor",
    "blues": "de blues",
}


def generar_escala(
    perfil_clave: str = "guitarra_estandar",
    raiz_midi: int = 48,
    tipo: str = "mayor",
    traste_minimo: int = 0,
    traste_maximo: int = 4,
    tempo: int = 80,
    direccion: str = "ambas",
) -> Ejercicio:
    """Genera una escala dentro de un rango de trastes.

    El algoritmo son tres pasos: pedir al mastil que notas alcanza en el rango,
    pedir a la teoria que clases pertenecen a la escala, y quedarse con la
    interseccion ordenada de grave a aguda.

    Lanza ValueError si la configuracion es imposible. Detectarlo aqui y no
    mientras se toca es lo que pide la spec: descubrirlo tocando seria tarde.
    """
    if perfil_clave not in PERFILES:
        disponibles = ", ".join(sorted(PERFILES))
        raise ValueError(f"El perfil '{perfil_clave}' no existe. Opciones: {disponibles}")
    if tipo not in ESCALAS:
        disponibles = ", ".join(sorted(ESCALAS))
        raise ValueError(f"La escala '{tipo}' no existe. Opciones: {disponibles}")
    if direccion not in DIRECCIONES:
        disponibles = ", ".join(DIRECCIONES)
        raise ValueError(f"La direccion '{direccion}' no existe. Opciones: {disponibles}")

    perfil = PERFILES[perfil_clave]
    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    clases = clases_del_patron(raiz_midi, ESCALAS[tipo])
    midis = sorted(midi for midi in alcanzables if midi % 12 in clases)

    if not midis:
        raise ValueError(
            f"No cae ninguna nota de la escala {NOMBRES_TIPOS[tipo]} de "
            f"{nombre_de_midi(raiz_midi)} entre los trastes {traste_minimo} y "
            f"{traste_maximo} del perfil {perfil.nombre}."
        )

    if direccion == "ascendente":
        secuencia = midis
    elif direccion == "descendente":
        secuencia = midis[::-1]
    else:
        # Subir y bajar sin repetir la cumbre: do re mi fa sol fa mi re do.
        secuencia = midis + midis[-2::-1]

    notas = tuple(
        NotaEsperada(midi=midi, posiciones=alcanzables[midi], pulsos=1.0) for midi in secuencia
    )

    nombre_raiz = nombre_de_midi(raiz_midi)[:-1]  # sin el numero de octava
    return Ejercicio(
        clave=f"escala_{tipo}_{nombre_raiz.lower()}_{traste_minimo}_{traste_maximo}",
        nombre=f"Escala {NOMBRES_TIPOS[tipo]} de {nombre_raiz}",
        descripcion=(
            f"{len(notas)} notas entre los trastes {traste_minimo} y {traste_maximo}, "
            f"{direccion}, a {tempo} pulsos por minuto."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
```

También crear `nucleo/ejercicios/generadores/__init__.py` vacío.

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_generador_escalas.py -v`
Esperado: PASS, 14 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/ejercicios/generadores/ tests/test_generador_escalas.py
git commit -m "feat: generador de ejercicios de escala"
```

---

### Task 4: Generador de arpegios, extrayendo lo común con las escalas

**Files:**
- Create: `nucleo/ejercicios/generadores/comun.py`
- Create: `nucleo/ejercicios/generadores/arpegios.py`
- Modify: `nucleo/ejercicios/generadores/escalas.py` (pasa a apoyarse en `comun.py`)
- Test: `tests/test_generador_arpegios.py`

**Interfaces:**
- Consumes: todo lo de la Task 3, más `nucleo.ejercicios.teoria.ACORDES`
- Produces:
  - En `comun.py`: `DIRECCIONES: tuple[str, ...]`, `validar_parametros(perfil_clave: str, direccion: str) -> PerfilAfinacion`, `secuenciar(midis: list[int], direccion: str) -> list[int]`, `notas_del_patron_en_mastil(perfil, raiz_midi, patron, traste_minimo, traste_maximo) -> tuple[list[int], dict[int, tuple[Posicion, ...]]]`
  - En `arpegios.py`: `generar_arpegio(perfil_clave: str = "guitarra_estandar", raiz_midi: int = 48, tipo: str = "mayor", traste_minimo: int = 0, traste_maximo: int = 4, tempo: int = 80, direccion: str = "ambas") -> Ejercicio`
  - `escalas.py` conserva **exactamente** la firma pública de la Task 3: `generar_escala(...)` y `DIRECCIONES`

**Contexto para quien implementa, y es importante.** Un arpegio se genera igual que una escala: mismo mástil, misma intersección, misma secuenciación. Lo único que cambia es el patrón —`(0,4,7)` en vez de `(0,2,4,5,7,9,11)`— y el texto.

Si copias `escalas.py` y cambias el diccionario, tendrás dos archivos casi idénticos que habrá que corregir en pareja para siempre. Por eso esta tarea **extrae primero lo común** y luego escribe el arpegio encima. Las pruebas de la Task 3 deben seguir pasando **sin tocarlas**: son la red que garantiza que la refactorización no cambió el comportamiento.

Orden de trabajo obligatorio: escribe `comun.py`, refactoriza `escalas.py` para usarlo, **ejecuta las pruebas de escalas y confirma que siguen en verde**, y solo entonces escribe `arpegios.py`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_generador_arpegios.py
import pytest

from nucleo.ejercicios.generadores.arpegios import generar_arpegio
from nucleo.ejercicios.teoria import ACORDES, clases_del_patron

DO3 = 48


def test_el_arpegio_mayor_solo_usa_fundamental_tercera_y_quinta():
    ejercicio = generar_arpegio(raiz_midi=DO3, tipo="mayor", traste_minimo=0, traste_maximo=5)
    clases = clases_del_patron(DO3, ACORDES["mayor"])
    assert all(n.midi % 12 in clases for n in ejercicio.notas)
    assert {n.midi % 12 for n in ejercicio.notas} <= {0, 4, 7}


def test_el_arpegio_menor_baja_la_tercera():
    menor = generar_arpegio(raiz_midi=DO3, tipo="menor", traste_minimo=0, traste_maximo=5)
    assert 3 in {n.midi % 12 for n in menor.notas}
    assert 4 not in {n.midi % 12 for n in menor.notas}


def test_la_septima_anade_una_nota_mas_al_repertorio():
    triada = generar_arpegio(tipo="mayor", direccion="ascendente", traste_maximo=7)
    septima = generar_arpegio(tipo="septima", direccion="ascendente", traste_maximo=7)
    assert len({n.midi % 12 for n in septima.notas}) > len({n.midi % 12 for n in triada.notas})


def test_el_arpegio_tiene_menos_notas_que_la_escala_en_el_mismo_rango():
    from nucleo.ejercicios.generadores.escalas import generar_escala

    escala = generar_escala(direccion="ascendente", traste_maximo=5)
    arpegio = generar_arpegio(direccion="ascendente", traste_maximo=5)
    assert len(arpegio.notas) < len(escala.notas)


def test_ambas_direcciones_no_repite_la_cumbre():
    ascendente = generar_arpegio(direccion="ascendente", traste_maximo=5)
    ambas = generar_arpegio(direccion="ambas", traste_maximo=5)
    assert len(ambas.notas) == 2 * len(ascendente.notas) - 1


def test_un_acorde_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="acorde"):
        generar_arpegio(tipo="disminuido_septima_alterado")


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_arpegio(perfil_clave="ukelele")


def test_un_rango_sin_notas_del_acorde_se_rechaza_al_generar():
    with pytest.raises(ValueError, match="ninguna nota"):
        generar_arpegio(traste_minimo=30, traste_maximo=30)


def test_cada_nota_trae_sus_posiciones():
    ejercicio = generar_arpegio(traste_maximo=5)
    assert all(len(n.posiciones) >= 1 for n in ejercicio.notas)


def test_el_nombre_menciona_el_acorde():
    ejercicio = generar_arpegio(raiz_midi=DO3, tipo="menor_septima", traste_maximo=7)
    assert "menor" in ejercicio.nombre.lower()
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_generador_arpegios.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.ejercicios.generadores.arpegios'`

- [ ] **Step 3: Escribir `nucleo/ejercicios/generadores/comun.py`**

```python
"""Lo que comparten todos los generadores que recorren un patron por el mastil.

Escalas y arpegios se generan igual: mismo mastil, misma interseccion, misma
secuenciacion. Lo unico que cambia es el patron. Extraerlo aqui evita dos
archivos casi identicos que habria que corregir en pareja para siempre.
"""

from nucleo.afinaciones import PERFILES, PerfilAfinacion
from nucleo.ejercicios.teoria import clases_del_patron, notas_alcanzables
from nucleo.musica import Posicion

DIRECCIONES: tuple[str, ...] = ("ascendente", "descendente", "ambas")


def validar_parametros(perfil_clave: str, direccion: str) -> PerfilAfinacion:
    """Comprueba perfil y direccion, y devuelve el perfil resuelto."""
    if perfil_clave not in PERFILES:
        disponibles = ", ".join(sorted(PERFILES))
        raise ValueError(f"El perfil '{perfil_clave}' no existe. Opciones: {disponibles}")
    if direccion not in DIRECCIONES:
        disponibles = ", ".join(DIRECCIONES)
        raise ValueError(f"La direccion '{direccion}' no existe. Opciones: {disponibles}")
    return PERFILES[perfil_clave]


def notas_del_patron_en_mastil(
    perfil: PerfilAfinacion,
    raiz_midi: int,
    patron: tuple[int, ...],
    traste_minimo: int,
    traste_maximo: int,
) -> tuple[list[int], dict[int, tuple[Posicion, ...]]]:
    """Notas del patron que caen en el rango de trastes, y donde tocarlas.

    Devuelve la lista de numeros MIDI ordenada de grave a aguda y el diccionario
    completo de posiciones alcanzables, que el generador necesita para rellenar
    cada NotaEsperada.
    """
    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    clases = clases_del_patron(raiz_midi, patron)
    midis = sorted(midi for midi in alcanzables if midi % 12 in clases)
    return midis, alcanzables


def secuenciar(midis: list[int], direccion: str) -> list[int]:
    """Ordena las notas segun la direccion pedida.

    "ambas" sube y baja sin repetir la nota mas aguda: do re mi fa sol fa mi re
    do. Repetir la cumbre suena mal y descuadra la cuenta de notas.
    """
    if direccion == "ascendente":
        return list(midis)
    if direccion == "descendente":
        return list(midis[::-1])
    return list(midis) + list(midis[-2::-1])
```

- [ ] **Step 4: Refactorizar `escalas.py` para usar `comun.py`**

Sustituye en `escalas.py` la validación de perfil y dirección por `validar_parametros`, el cálculo de notas por `notas_del_patron_en_mastil`, y la secuenciación por `secuenciar`. Reexporta `DIRECCIONES` desde `comun` para no romper a quien lo importe de `escalas`. La validación del tipo de escala y la construcción del `Ejercicio` se quedan en `escalas.py`: son lo propio de esta familia.

- [ ] **Step 5: Confirmar que la refactorización no cambió nada**

Run: `uv run pytest tests/test_generador_escalas.py -v`
Esperado: PASS, las mismas 14 pruebas, **sin haberlas tocado**. Si alguna falla, la refactorización cambió el comportamiento y hay que corregirla antes de seguir.

- [ ] **Step 6: Escribir `nucleo/ejercicios/generadores/arpegios.py`**

```python
"""Generador de arpegios: las notas de un acorde tocadas por separado.

Es monofonico —una nota cada vez— asi que funciona con el detector de tono de la
etapa 1. Ensena a ver los acordes en el mastil antes de rasguearlos.
"""

from nucleo.ejercicios.generadores.comun import (
    DIRECCIONES,
    notas_del_patron_en_mastil,
    secuenciar,
    validar_parametros,
)
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import ACORDES
from nucleo.musica import nombre_de_midi

NOMBRES_ACORDES: dict[str, str] = {
    "mayor": "mayor",
    "menor": "menor",
    "septima": "con septima",
    "menor_septima": "menor con septima",
}

__all__ = ["DIRECCIONES", "generar_arpegio"]


def generar_arpegio(
    perfil_clave: str = "guitarra_estandar",
    raiz_midi: int = 48,
    tipo: str = "mayor",
    traste_minimo: int = 0,
    traste_maximo: int = 4,
    tempo: int = 80,
    direccion: str = "ambas",
) -> Ejercicio:
    """Genera un arpegio dentro de un rango de trastes.

    Lanza ValueError si la configuracion es imposible, igual que el generador de
    escalas: la spec exige detectarlo al generar, no mientras se toca.
    """
    perfil = validar_parametros(perfil_clave, direccion)
    if tipo not in ACORDES:
        disponibles = ", ".join(sorted(ACORDES))
        raise ValueError(f"El acorde '{tipo}' no existe. Opciones: {disponibles}")

    midis, alcanzables = notas_del_patron_en_mastil(
        perfil, raiz_midi, ACORDES[tipo], traste_minimo, traste_maximo
    )
    if not midis:
        raise ValueError(
            f"No cae ninguna nota del acorde {NOMBRES_ACORDES[tipo]} de "
            f"{nombre_de_midi(raiz_midi)} entre los trastes {traste_minimo} y "
            f"{traste_maximo} del perfil {perfil.nombre}."
        )

    secuencia = secuenciar(midis, direccion)
    notas = tuple(
        NotaEsperada(midi=midi, posiciones=alcanzables[midi], pulsos=1.0) for midi in secuencia
    )

    nombre_raiz = nombre_de_midi(raiz_midi)[:-1]
    return Ejercicio(
        clave=f"arpegio_{tipo}_{nombre_raiz.lower()}_{traste_minimo}_{traste_maximo}",
        nombre=f"Arpegio {NOMBRES_ACORDES[tipo]} de {nombre_raiz}",
        descripcion=(
            f"{len(notas)} notas entre los trastes {traste_minimo} y {traste_maximo}, "
            f"{direccion}, a {tempo} pulsos por minuto."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
```

- [ ] **Step 7: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_generador_arpegios.py tests/test_generador_escalas.py -v`
Esperado: PASS, 24 pruebas.

- [ ] **Step 8: Commit**

```bash
git add nucleo/ejercicios/generadores/ tests/test_generador_arpegios.py
git commit -m "feat: generador de arpegios, con lo comun extraido de las escalas"
```

---

### Task 5: Generadores de intervalos y de lectura del mástil

**Files:**
- Create: `nucleo/ejercicios/generadores/intervalos.py`
- Create: `nucleo/ejercicios/generadores/lectura.py`
- Test: `tests/test_generador_intervalos.py`
- Test: `tests/test_generador_lectura.py`

**Interfaces:**
- Consumes: `nucleo.ejercicios.generadores.comun.validar_parametros`, `nucleo.ejercicios.teoria.INTERVALOS`, `nucleo.ejercicios.teoria.nombre_de_intervalo`, `nucleo.ejercicios.teoria.notas_alcanzables`, `nucleo.ejercicios.modelo.Ejercicio`, `nucleo.ejercicios.modelo.NotaEsperada`, `nucleo.musica.nombre_de_midi`
- Produces:
  - `generar_intervalo(perfil_clave: str = "guitarra_estandar", intervalo: str = "tercera_mayor", traste_minimo: int = 0, traste_maximo: int = 7, tempo: int = 70, repeticiones: int = 8, semilla: int | None = None) -> Ejercicio`
  - `generar_lectura(perfil_clave: str = "guitarra_estandar", cuerda: int | None = None, traste_minimo: int = 0, traste_maximo: int = 12, tempo: int = 60, repeticiones: int = 10, semilla: int | None = None) -> Ejercicio`

**Contexto para quien implementa.** Estas dos familias tienen una forma distinta de las anteriores: no recorren un patrón, **eligen notas al azar**. Eso trae dos exigencias.

**La aleatoriedad tiene que ser reproducible.** Ambas funciones aceptan `semilla` y usan `numpy.random.default_rng(semilla)`. Sin eso las pruebas no podrían afirmar nada concreto, y tú no podrías repetir un ejercicio que te salió bien. Con `semilla=None` el ejercicio es distinto cada vez, que es lo que se quiere al practicar.

**En la lectura, restringir la cuerda restringe también las posiciones.** Si el ejercicio dice "encuentra el Fa# en la quinta cuerda", aceptarlo en cualquier cuerda vacía el ejercicio de sentido. Cuando se pasa `cuerda`, cada `NotaEsperada` lleva **solo** la posición de esa cuerda.

Ojo con un detalle del intervalo: la nota objetivo tiene que ser **alcanzable en el mástil**, no solo existir en teoría. Si eliges una referencia cerca del extremo agudo del rango, la tercera mayor por encima puede caerse fuera. La generación debe elegir la referencia **entre las que tienen objetivo válido**, no elegir primero y fallar después.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_generador_intervalos.py
import pytest

from nucleo.ejercicios.generadores.intervalos import generar_intervalo
from nucleo.ejercicios.teoria import INTERVALOS


def test_cada_nota_lleva_su_referencia_que_sonara_antes():
    ejercicio = generar_intervalo(semilla=1)
    assert all(n.referencia_midi is not None for n in ejercicio.notas)


def test_la_distancia_es_exactamente_el_intervalo_pedido():
    ejercicio = generar_intervalo(intervalo="quinta_justa", semilla=2)
    for nota in ejercicio.notas:
        assert nota.midi - nota.referencia_midi == INTERVALOS["quinta_justa"]


def test_se_generan_tantas_repeticiones_como_se_piden():
    assert len(generar_intervalo(repeticiones=5, semilla=3).notas) == 5


def test_la_misma_semilla_da_el_mismo_ejercicio():
    uno = generar_intervalo(semilla=7)
    otro = generar_intervalo(semilla=7)
    assert [n.midi for n in uno.notas] == [n.midi for n in otro.notas]
    assert [n.referencia_midi for n in uno.notas] == [n.referencia_midi for n in otro.notas]


def test_semillas_distintas_dan_ejercicios_distintos():
    uno = generar_intervalo(semilla=7, repeticiones=12)
    otro = generar_intervalo(semilla=8, repeticiones=12)
    assert [n.midi for n in uno.notas] != [n.midi for n in otro.notas]


def test_la_nota_objetivo_siempre_es_alcanzable_en_el_mastil():
    """No basta con que exista en teoria: hay que poder tocarla en el rango."""
    ejercicio = generar_intervalo(intervalo="octava", traste_minimo=0, traste_maximo=5, semilla=4)
    for nota in ejercicio.notas:
        assert len(nota.posiciones) >= 1
        assert all(0 <= p.traste <= 5 for p in nota.posiciones)


def test_el_nombre_menciona_el_intervalo_en_castellano():
    ejercicio = generar_intervalo(intervalo="tercera_mayor", semilla=5)
    assert "tercera mayor" in ejercicio.nombre.lower()


def test_un_intervalo_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="intervalo"):
        generar_intervalo(intervalo="cuarta_aumentada_disminuida")


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_intervalo(perfil_clave="ukelele")


def test_un_rango_sin_pares_validos_se_rechaza_al_generar():
    """Con un solo traste disponible no cabe ninguna octava."""
    with pytest.raises(ValueError, match="ningun"):
        generar_intervalo(intervalo="octava", traste_minimo=0, traste_maximo=0)


def test_cero_repeticiones_se_rechaza():
    with pytest.raises(ValueError, match="repeticiones"):
        generar_intervalo(repeticiones=0)
```

```python
# tests/test_generador_lectura.py
import pytest

from nucleo.afinaciones import PERFILES
from nucleo.ejercicios.generadores.lectura import generar_lectura


def test_se_generan_tantas_notas_como_repeticiones():
    assert len(generar_lectura(repeticiones=6, semilla=1).notas) == 6


def test_ninguna_nota_lleva_referencia_sonora():
    """En lectura no suena nada: se nombra la nota y tu la buscas."""
    ejercicio = generar_lectura(semilla=2)
    assert all(n.referencia_midi is None for n in ejercicio.notas)


def test_restringir_la_cuerda_restringe_tambien_las_posiciones():
    """Si pide el Fa# en la quinta cuerda, aceptarlo en otra vacia el ejercicio."""
    ejercicio = generar_lectura(cuerda=5, semilla=3)
    for nota in ejercicio.notas:
        assert all(p.cuerda == 5 for p in nota.posiciones)


def test_sin_restringir_cuerda_se_usan_todas():
    ejercicio = generar_lectura(repeticiones=20, semilla=4)
    cuerdas = {p.cuerda for n in ejercicio.notas for p in n.posiciones}
    assert len(cuerdas) > 1


def test_la_misma_semilla_da_el_mismo_ejercicio():
    uno = generar_lectura(semilla=9)
    otro = generar_lectura(semilla=9)
    assert [n.midi for n in uno.notas] == [n.midi for n in otro.notas]


def test_todas_las_notas_caen_en_el_rango_de_trastes():
    ejercicio = generar_lectura(traste_minimo=3, traste_maximo=7, semilla=5)
    for nota in ejercicio.notas:
        assert all(3 <= p.traste <= 7 for p in nota.posiciones)


def test_el_nombre_menciona_la_cuerda_cuando_se_restringe():
    ejercicio = generar_lectura(cuerda=5, semilla=6)
    assert "5" in ejercicio.nombre


def test_una_cuerda_que_el_perfil_no_tiene_se_rechaza():
    with pytest.raises(ValueError, match="cuerda"):
        generar_lectura(perfil_clave="bajo_4", cuerda=6)


def test_un_perfil_inexistente_se_rechaza():
    with pytest.raises(ValueError, match="perfil"):
        generar_lectura(perfil_clave="ukelele")


def test_cero_repeticiones_se_rechaza():
    with pytest.raises(ValueError, match="repeticiones"):
        generar_lectura(repeticiones=0)


def test_el_bajo_tambien_sirve_para_leer():
    ejercicio = generar_lectura(perfil_clave="bajo_4", semilla=7)
    assert ejercicio.perfil == "bajo_4"
    cuerdas_validas = {c.numero for c in PERFILES["bajo_4"].cuerdas}
    for nota in ejercicio.notas:
        assert all(p.cuerda in cuerdas_validas for p in nota.posiciones)
```

- [ ] **Step 2: Ejecutar las pruebas y verificar que fallan**

Run: `uv run pytest tests/test_generador_intervalos.py tests/test_generador_lectura.py -v`
Esperado: FAIL con `ModuleNotFoundError`

- [ ] **Step 3: Implementar `nucleo/ejercicios/generadores/intervalos.py`**

```python
"""Generador de ejercicios de intervalo y entrenamiento de oido.

A diferencia de escalas y arpegios, no recorre un patron: elige pares de notas
al azar. El software hace sonar la referencia y tu tocas la nota que esta al
intervalo pedido.
"""

import numpy as np

from nucleo.ejercicios.generadores.comun import validar_parametros
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import INTERVALOS, nombre_de_intervalo, notas_alcanzables


def generar_intervalo(
    perfil_clave: str = "guitarra_estandar",
    intervalo: str = "tercera_mayor",
    traste_minimo: int = 0,
    traste_maximo: int = 7,
    tempo: int = 70,
    repeticiones: int = 8,
    semilla: int | None = None,
) -> Ejercicio:
    """Genera pares (referencia que suena, nota que debes tocar).

    La aleatoriedad es reproducible con `semilla`: sin eso las pruebas no podrian
    afirmar nada y no podrias repetir un ejercicio que te salio bien. Con
    semilla=None el ejercicio cambia cada vez, que es lo que se quiere al
    practicar.

    Las referencias se eligen SOLO entre las que tienen objetivo alcanzable en el
    mastil. Elegir primero y comprobar despues fallaria cerca del extremo agudo.
    """
    perfil = validar_parametros(perfil_clave, "ascendente")
    if intervalo not in INTERVALOS:
        disponibles = ", ".join(sorted(INTERVALOS))
        raise ValueError(f"El intervalo '{intervalo}' no existe. Opciones: {disponibles}")
    if repeticiones < 1:
        raise ValueError("Las repeticiones deben ser al menos 1")

    salto = INTERVALOS[intervalo]
    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    referencias = sorted(midi for midi in alcanzables if midi + salto in alcanzables)
    if not referencias:
        raise ValueError(
            f"No hay ningun par a distancia de {nombre_de_intervalo(salto)} entre los "
            f"trastes {traste_minimo} y {traste_maximo} del perfil {perfil.nombre}."
        )

    generador = np.random.default_rng(semilla)
    elegidas = generador.choice(referencias, size=repeticiones, replace=True)
    notas = tuple(
        NotaEsperada(
            midi=int(referencia) + salto,
            posiciones=alcanzables[int(referencia) + salto],
            pulsos=1.0,
            referencia_midi=int(referencia),
        )
        for referencia in elegidas
    )

    return Ejercicio(
        clave=f"intervalo_{intervalo}_{traste_minimo}_{traste_maximo}",
        nombre=f"Intervalo: {nombre_de_intervalo(salto)}",
        descripcion=(
            f"{repeticiones} repeticiones. Suena una nota y tocas la que esta una "
            f"{nombre_de_intervalo(salto)} por encima, entre los trastes "
            f"{traste_minimo} y {traste_maximo}."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
```

- [ ] **Step 4: Implementar `nucleo/ejercicios/generadores/lectura.py`**

```python
"""Generador de ejercicios de lectura de notas en el mastil.

Se nombra una nota y tienes que encontrarla. No suena nada: ataca directamente el
conocimiento del diapason, que es lo que mas cuesta al principio.
"""

import numpy as np

from nucleo.ejercicios.generadores.comun import validar_parametros
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.ejercicios.teoria import notas_alcanzables


def generar_lectura(
    perfil_clave: str = "guitarra_estandar",
    cuerda: int | None = None,
    traste_minimo: int = 0,
    traste_maximo: int = 12,
    tempo: int = 60,
    repeticiones: int = 10,
    semilla: int | None = None,
) -> Ejercicio:
    """Genera notas sueltas para buscar en el mastil.

    Si se restringe la cuerda, cada nota lleva SOLO la posicion de esa cuerda:
    pedir "el Fa# en la quinta" y aceptarlo en cualquier otra vaciaria el
    ejercicio de sentido.
    """
    perfil = validar_parametros(perfil_clave, "ascendente")
    if repeticiones < 1:
        raise ValueError("Las repeticiones deben ser al menos 1")

    numeros_validos = {c.numero for c in perfil.cuerdas}
    if cuerda is not None and cuerda not in numeros_validos:
        disponibles = ", ".join(str(n) for n in sorted(numeros_validos))
        raise ValueError(
            f"El perfil {perfil.nombre} no tiene la cuerda {cuerda}. Cuerdas: {disponibles}"
        )

    alcanzables = notas_alcanzables(perfil, traste_minimo, traste_maximo)
    if cuerda is not None:
        alcanzables = {
            midi: tuple(p for p in posiciones if p.cuerda == cuerda)
            for midi, posiciones in alcanzables.items()
        }
        alcanzables = {midi: p for midi, p in alcanzables.items() if p}

    candidatas = sorted(alcanzables)
    if not candidatas:
        raise ValueError(
            f"No hay ninguna nota entre los trastes {traste_minimo} y {traste_maximo} "
            f"del perfil {perfil.nombre} con esa restriccion de cuerda."
        )

    generador = np.random.default_rng(semilla)
    elegidas = generador.choice(candidatas, size=repeticiones, replace=True)
    notas = tuple(
        NotaEsperada(midi=int(midi), posiciones=alcanzables[int(midi)], pulsos=1.0)
        for midi in elegidas
    )

    donde = f"en la cuerda {cuerda}" if cuerda is not None else "en cualquier cuerda"
    return Ejercicio(
        clave=f"lectura_{cuerda or 'todas'}_{traste_minimo}_{traste_maximo}",
        nombre=f"Lectura del mastil {donde}",
        descripcion=(
            f"{repeticiones} notas para encontrar {donde}, entre los trastes "
            f"{traste_minimo} y {traste_maximo}."
        ),
        notas=notas,
        tempo=tempo,
        perfil=perfil_clave,
    )
```

- [ ] **Step 5: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_generador_intervalos.py tests/test_generador_lectura.py -v`
Esperado: PASS, 22 pruebas.

- [ ] **Step 6: Commit**

```bash
git add nucleo/ejercicios/generadores/ tests/test_generador_intervalos.py tests/test_generador_lectura.py
git commit -m "feat: generadores de intervalos y de lectura del mastil"
```

---

### Task 6: Detección de ataques — la pieza de mayor riesgo

**Files:**
- Create: `nucleo/ejercicios/ataques.py`
- Test: `tests/test_ataques.py`

**Interfaces:**
- Consumes: `nucleo.analisis.energia.NIVEL_SILENCIO_DBFS`, `nucleo.analisis.energia.UMBRAL_RUIDO_POR_DEFECTO_DBFS`
- Produces:
  - `SALTO_ATAQUE_DB: float` = `6.0`
  - `REFRACTARIO_S: float` = `0.050`
  - `ESPERA_ESTABILIZACION_S: float` = `0.060`
  - `Ataque(instante: float, nivel_db: float)` — dataclass congelada
  - `DetectorAtaques(salto_db: float = 6.0, refractario_s: float = 0.050, muestras_referencia: int = 5, nivel_minimo_dbfs: float = -60.0)` con `procesar(nivel_db: float, instante: float) -> Ataque | None` y `reiniciar() -> None`
  - `registrar_detector(nombre: str, fabrica) -> None`, `obtener_detector(nombre: str)`, `nombres_disponibles() -> list[str]`, con `"energia"` registrado

**Contexto para quien implementa. Esta es la tarea con más riesgo de la etapa y conviene entender por qué existe.**

El afinador solo necesita saber **qué** nota suena ahora. Un ejercicio necesita saber **cuándo empieza una nota nueva**. Si tocas un Do y lo sostienes dos segundos, el analizador emite unos sesenta resultados diciendo "Do", y eso es **una** nota, no sesenta. Si tocas Do, Do, Do repetidos, son **tres**, y el analizador dice exactamente lo mismo. La diferencia no está en la frecuencia: está en la energía.

El algoritmo: se mantiene un historial corto de niveles recientes y se toma su **mediana** como referencia. Hay ataque cuando el nivel actual supera esa referencia por más del salto configurado **y** ha pasado el periodo refractario desde el último. Mediana y no media, por lo mismo de siempre: un valor atípico no debe mover la referencia.

**El refractario no es un adorno.** El transitorio de la púa hace que el nivel suba, baje y vuelva a subir en pocos milisegundos; sin tiempo muerto, una sola pulsación marcaría dos o tres ataques y el ejercicio avanzaría solo.

**Sin historial, la referencia es el silencio absoluto** (−120 dBFS). Así la primera nota de un ejercicio se detecta, en vez de perderse por no tener con qué compararse.

**Un ataque exige señal real.** Sin un suelo, el primer cuadro de puro ruido ya marcaría ataque: comparado con −120 dBFS, hasta el silencio del cable es una subida de 25 dB. Por eso no se marca ataque si el nivel no supera el umbral de la compuerta de ruido (−60 dBFS, el mismo valor que ya usa el afinador). Reutilizar esa constante y no inventar otra mantiene una sola fuente de verdad sobre qué es silencio en este proyecto.

Los tres parámetros son **provisionales**: se calibran con las grabaciones reales del usuario en la Task 11. El registro de detectores existe para poder sustituir este por uno espectral sin tocar el evaluador, igual que el registro de detectores de tono de la etapa 1.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_ataques.py
import pytest

from nucleo.ejercicios.ataques import (
    REFRACTARIO_S,
    SALTO_ATAQUE_DB,
    Ataque,
    DetectorAtaques,
    nombres_disponibles,
    obtener_detector,
    registrar_detector,
)

PASO = 0.021  # el intervalo de analisis de la sesion, en segundos


def alimentar(detector: DetectorAtaques, niveles: list[float], paso: float = PASO) -> list[Ataque]:
    """Pasa una secuencia de niveles al detector y devuelve los ataques marcados."""
    ataques = []
    for indice, nivel in enumerate(niveles):
        ataque = detector.procesar(nivel, indice * paso)
        if ataque is not None:
            ataques.append(ataque)
    return ataques


def test_los_valores_por_defecto_son_los_de_la_spec():
    assert SALTO_ATAQUE_DB == 6.0
    assert REFRACTARIO_S == 0.050


def test_el_silencio_no_produce_ataques():
    """Sin suelo, el primer cuadro de ruido ya marcaria ataque contra los -120 dBFS."""
    assert alimentar(DetectorAtaques(), [-95.0] * 20) == []


def test_una_nota_sostenida_es_un_solo_ataque():
    """Sesenta resultados diciendo Do son UNA nota, no sesenta."""
    niveles = [-95.0] * 5 + [-30.0] * 40
    assert len(alimentar(DetectorAtaques(), niveles)) == 1


def test_dos_pulsaciones_separadas_son_dos_ataques():
    niveles = [-95.0] * 5 + [-30.0] * 20 + [-95.0] * 10 + [-30.0] * 20
    assert len(alimentar(DetectorAtaques(), niveles)) == 2


def test_una_nota_repetida_sin_silencio_intermedio_tambien_son_dos():
    """El decaimiento natural basta para que la siguiente pulsacion destaque."""
    niveles = [-95.0] * 5 + [-30.0, -34.0, -40.0, -46.0, -52.0] + [-30.0] * 10
    assert len(alimentar(DetectorAtaques(), niveles)) == 2


def test_el_decaimiento_lento_no_marca_ataques():
    """Una nota que se apaga no empieza otra vez."""
    niveles = [-95.0] * 5 + [-30.0 - i * 1.5 for i in range(30)]
    assert len(alimentar(DetectorAtaques(), niveles)) == 1


def test_el_refractario_impide_el_doble_disparo_del_transitorio():
    """Sin tiempo muerto, una sola pulsacion marcaria dos o tres ataques."""
    # Sube, baja y vuelve a subir en menos de 50 ms (tres pasos de 21 ms son 63,
    # asi que se usan pasos de 10 ms para quedar dentro del refractario).
    niveles = [-95.0] * 5 + [-30.0, -45.0, -28.0]
    assert len(alimentar(DetectorAtaques(), niveles, paso=0.010)) == 1


def test_pasado_el_refractario_si_se_admite_un_ataque_nuevo():
    niveles = [-95.0] * 5 + [-30.0, -45.0]
    assert len(alimentar(DetectorAtaques(), niveles, paso=0.060)) == 2


def test_la_primera_nota_se_detecta_sin_historial_previo():
    """Sin historial la referencia es el silencio absoluto, no un hueco."""
    assert len(alimentar(DetectorAtaques(), [-30.0] * 10)) == 1


def test_el_ataque_lleva_su_instante_y_su_nivel():
    ataques = alimentar(DetectorAtaques(), [-95.0] * 5 + [-30.0] * 5)
    assert ataques[0].instante == pytest.approx(5 * PASO)
    assert ataques[0].nivel_db == pytest.approx(-30.0)


def test_un_salto_menor_que_el_umbral_no_cuenta():
    """El primer ataque es el inicio de la senal; la subida de 4 dB no anade otro."""
    niveles = [-40.0] * 10 + [-36.0] * 10  # solo 4 dB de subida
    assert len(alimentar(DetectorAtaques(), niveles)) == 1


def test_el_salto_es_configurable():
    """Con el umbral en 3 dB, esa misma subida de 4 dB si cuenta."""
    niveles = [-40.0] * 10 + [-36.0] * 10
    assert len(alimentar(DetectorAtaques(salto_db=3.0), niveles)) == 2


def test_reiniciar_olvida_el_historial():
    detector = DetectorAtaques()
    alimentar(detector, [-30.0] * 10)
    detector.reiniciar()
    assert len(alimentar(detector, [-30.0] * 10)) == 1


def test_el_detector_de_energia_esta_registrado():
    assert "energia" in nombres_disponibles()
    assert isinstance(obtener_detector("energia")(), DetectorAtaques)


def test_se_puede_registrar_otro_detector():
    """Para enchufar uno espectral sin tocar el evaluador."""
    registrar_detector("falso", lambda: DetectorAtaques(salto_db=99.0))
    assert "falso" in nombres_disponibles()


def test_pedir_un_detector_inexistente_es_un_error_claro():
    with pytest.raises(KeyError, match="inexistente"):
        obtener_detector("inexistente")
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_ataques.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.ejercicios.ataques'`

- [ ] **Step 3: Implementar `nucleo/ejercicios/ataques.py`**

```python
"""Deteccion de ataques: cuando empieza una nota nueva.

El afinador solo necesita saber QUE nota suena ahora. Un ejercicio necesita saber
CUANDO empieza una nota nueva. Si tocas un Do y lo sostienes dos segundos, el
analizador emite unos sesenta resultados diciendo "Do", y eso es UNA nota. Si
tocas Do, Do, Do repetidos, son TRES, y el analizador dice exactamente lo mismo.
La diferencia no esta en la frecuencia: esta en la energia.
"""

from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from nucleo.analisis.energia import NIVEL_SILENCIO_DBFS, UMBRAL_RUIDO_POR_DEFECTO_DBFS

# Cuanto debe subir el nivel sobre la referencia reciente para contar como ataque.
# Provisional: se calibra con grabaciones reales de la guitarra del usuario.
SALTO_ATAQUE_DB = 6.0

# Tiempo muerto tras un ataque. El transitorio de la pua hace que el nivel suba,
# baje y vuelva a subir en pocos milisegundos; sin esto una sola pulsacion
# marcaria dos o tres ataques y el ejercicio avanzaria solo.
REFRACTARIO_S = 0.050

# Cuanto espera el evaluador tras un ataque antes de leer la nota. Justo en el
# ataque la senal es caotica y la frecuencia poco fiable.
ESPERA_ESTABILIZACION_S = 0.060


@dataclass(frozen=True)
class Ataque:
    """El instante en que empieza una nota nueva, y con que nivel."""

    instante: float
    nivel_db: float


class DetectorAtaques:
    """Marca ataques a partir de la subida de energia.

    Mantiene un historial corto de niveles recientes y toma su mediana como
    referencia. Hay ataque cuando el nivel supera esa referencia por mas del
    salto configurado y ha pasado el periodo refractario desde el anterior.

    Se usa mediana y no media por lo mismo que en el suavizado del afinador: un
    valor atipico no debe mover la referencia.
    """

    def __init__(
        self,
        salto_db: float = SALTO_ATAQUE_DB,
        refractario_s: float = REFRACTARIO_S,
        muestras_referencia: int = 5,
        nivel_minimo_dbfs: float = UMBRAL_RUIDO_POR_DEFECTO_DBFS,
    ) -> None:
        self.salto_db = salto_db
        self.refractario_s = refractario_s
        self.nivel_minimo_dbfs = nivel_minimo_dbfs
        self._historial: deque[float] = deque(maxlen=muestras_referencia)
        self._instante_ultimo: float | None = None

    def reiniciar(self) -> None:
        """Olvida el historial y el ultimo ataque. Se llama al empezar un ejercicio."""
        self._historial.clear()
        self._instante_ultimo = None

    def _referencia(self) -> float:
        """Nivel contra el que se compara. Sin historial, el silencio absoluto.

        Tomar el silencio como referencia inicial es lo que hace que la primera
        nota de un ejercicio se detecte, en vez de perderse por no tener con que
        compararse.
        """
        if not self._historial:
            return NIVEL_SILENCIO_DBFS
        return float(np.median(self._historial))

    def procesar(self, nivel_db: float, instante: float) -> Ataque | None:
        """Consume un nivel y devuelve el ataque si lo hay, o None."""
        referencia = self._referencia()
        self._historial.append(nivel_db)

        # Un ataque exige senal real: sin este suelo, el primer cuadro de ruido
        # marcaria ataque al compararse con los -120 dBFS del silencio absoluto.
        if nivel_db <= self.nivel_minimo_dbfs:
            return None
        if nivel_db - referencia < self.salto_db:
            return None
        if (
            self._instante_ultimo is not None
            and instante - self._instante_ultimo < self.refractario_s
        ):
            return None

        self._instante_ultimo = instante
        return Ataque(instante=instante, nivel_db=nivel_db)


_DETECTORES: dict[str, Callable[[], DetectorAtaques]] = {}


def registrar_detector(nombre: str, fabrica: Callable[[], DetectorAtaques]) -> None:
    """Anade un detector al registro, sustituyendo el anterior con ese nombre."""
    _DETECTORES[nombre] = fabrica


def obtener_detector(nombre: str) -> Callable[[], DetectorAtaques]:
    """Devuelve la fabrica de un detector por nombre. Lanza KeyError si no existe."""
    if nombre not in _DETECTORES:
        disponibles = ", ".join(sorted(_DETECTORES)) or "ninguno"
        raise KeyError(f"No existe el detector de ataques '{nombre}'. Disponibles: {disponibles}")
    return _DETECTORES[nombre]


def nombres_disponibles() -> list[str]:
    """Nombres de los detectores registrados, ordenados."""
    return sorted(_DETECTORES)


registrar_detector("energia", DetectorAtaques)
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_ataques.py -v`
Esperado: PASS, 16 pruebas.

Si `test_una_nota_repetida_sin_silencio_intermedio_tambien_son_dos` falla dando un solo ataque, la mediana del historial está subiendo demasiado con la nota sostenida: revisa que el historial se actualice **después** de calcular la referencia, no antes.

- [ ] **Step 5: Añadir un fixture que limpie el registro global**

En `tests/test_ataques.py`, añade un fixture `autouse` que guarde y restaure el diccionario `_DETECTORES` alrededor de cada prueba, para que `test_se_puede_registrar_otro_detector` no contamine al resto de la sesión. Es la misma precaución que ya lleva `tests/test_yin.py`.

- [ ] **Step 6: Commit**

```bash
git add nucleo/ejercicios/ataques.py tests/test_ataques.py
git commit -m "feat: deteccion de ataques por energia con registro de detectores"
```

---

### Task 7: El evaluador — la máquina de estados que corrige

**Files:**
- Create: `nucleo/ejercicios/evaluacion.py`
- Test: `tests/test_evaluacion.py`

**Interfaces:**
- Consumes: `nucleo.ejercicios.modelo` (todo), `nucleo.ejercicios.ataques.DetectorAtaques`, `nucleo.ejercicios.ataques.ESPERA_ESTABILIZACION_S`, `nucleo.analisis.pipeline.ResultadoAnalisis`, `nucleo.musica.nombre_de_midi`
- Produces:
  - `INTENTOS_PARA_AYUDA: int` = `5`
  - `CONFIANZA_MINIMA: float` = `0.75`
  - `EstadoEvaluacion(indice: int, total: int, intentos: int, ayuda_visible: bool, completado: bool, nota_actual: NotaEsperada | None, ultimo_fallo: str | None)` — dataclass congelada con `a_dict() -> dict`
  - `EvaluadorEjercicio(ejercicio: Ejercicio, detector_ataques: DetectorAtaques | None = None, confianza_minima: float = 0.75, espera_estabilizacion_s: float = 0.060, intentos_para_ayuda: int = 5)` con `procesar(resultado: ResultadoAnalisis, instante: float) -> EstadoEvaluacion`, la propiedad `estado`, `resultado() -> ResultadoEjercicio` y `reiniciar() -> None`

**Contexto para quien implementa. Aquí está la pedagogía del proyecto, y las tres reglas no son negociables.**

**Regla 1: un ataque sin nota creíble no cuenta como fallo.** Cuenta como que no tocaste nada. Un roce al cambiar de postura, el ruido de la púa al apoyarla, un armónico accidental: nada de eso debe puntuar en contra. Solo se cuenta un intento cuando hay un ataque **y** una nota con confianza suficiente.

**Regla 2: la afinación no bloquea.** Si la nota es la correcta, se acepta y se avanza, aunque esté a 20 cents. La desviación se guarda en el `IntentoNota` y el informe la resume. Saber dónde está una nota y hacerla sonar limpia son dos habilidades distintas, y exigir las dos a la vez convierte una práctica de digitación en una pelea con el instrumento.

**Regla 3: tras cinco intentos fallidos en la misma nota, se muestra la ayuda.** No se salta el ejercicio: el mástil resalta dónde está la nota. Esperar indefinidamente es correcto pedagógicamente y frustrante en la práctica.

**Cómo se compara la nota.** `ResultadoAnalisis` trae el **nombre** de la nota (`"E2"`), no su número MIDI. Compara por nombre contra `nombre_de_midi(esperada.midi)`: la correspondencia es biunívoca y evita volver a derivar el MIDI desde la frecuencia, que sería recalcular algo que el núcleo ya calculó.

**La lectura diferida.** Un ataque no se lee en el instante: se anota que hay una lectura pendiente para `instante + espera_estabilizacion_s`, y se resuelve en la primera llamada posterior a ese momento. Justo en el ataque la señal es caótica y leer ahí daría notas falsas.

**Toda esta lógica se prueba sin audio.** `ResultadoAnalisis` es un dato: se escribe la secuencia exacta que produciría alguien tocando y se verifica el veredicto. Ahí está la mitad del valor de esta arquitectura.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_evaluacion.py
import pytest

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.evaluacion import EvaluadorEjercicio
from nucleo.ejercicios.modelo import Ejercicio, NotaEsperada
from nucleo.musica import Posicion, nombre_de_midi

PASO = 0.021
ESPERA = 0.060


def ejercicio_de(midis: list[int], tempo: int = 80) -> Ejercicio:
    return Ejercicio(
        clave="prueba",
        nombre="Prueba",
        descripcion="",
        notas=tuple(
            NotaEsperada(midi=m, posiciones=(Posicion(cuerda=6, traste=0),)) for m in midis
        ),
        tempo=tempo,
        perfil="guitarra_estandar",
    )


def silencio(nivel: float = -95.0) -> ResultadoAnalisis:
    return ResultadoAnalisis(estado="silencio", frecuencia=0.0, confianza=0.0, nivel_db=nivel)


def suena(midi: int, cents: float = 0.0, confianza: float = 0.95, nivel: float = -30.0):
    return ResultadoAnalisis(
        estado="nota",
        frecuencia=110.0,
        confianza=confianza,
        nivel_db=nivel,
        nota=nombre_de_midi(midi),
        cents=cents,
        posiciones=[Posicion(cuerda=6, traste=0)],
        cuerda_objetivo=6,
        afinada=abs(cents) < 5.0,
    )


def tocar(evaluador: EvaluadorEjercicio, resultado, instante_inicial: float, cuadros: int = 8):
    """Simula una pulsacion: silencio, ataque, y sostenimiento el tiempo suficiente."""
    instante = instante_inicial
    for _ in range(3):
        evaluador.procesar(silencio(), instante)
        instante += PASO
    for _ in range(cuadros):
        estado = evaluador.procesar(resultado, instante)
        instante += PASO
    return estado, instante


def test_al_empezar_apunta_a_la_primera_nota():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    assert evaluador.estado.indice == 0
    assert evaluador.estado.total == 3
    assert evaluador.estado.completado is False
    assert evaluador.estado.nota_actual.midi == 40


def test_la_nota_correcta_avanza_el_ejercicio():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, _ = tocar(evaluador, suena(40), 0.0)
    assert estado.indice == 1
    assert estado.nota_actual.midi == 42


def test_una_secuencia_perfecta_completa_el_ejercicio_sin_fallos():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    instante = 0.0
    for midi in (40, 42, 44):
        _, instante = tocar(evaluador, suena(midi), instante)
    resultado = evaluador.resultado()
    assert resultado.completado is True
    assert resultado.aciertos_a_la_primera == 3
    assert all(n.intentos == 1 for n in resultado.notas)


def test_una_nota_equivocada_cuenta_intento_y_no_avanza():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, instante = tocar(evaluador, suena(45), 0.0)
    assert estado.indice == 0
    assert estado.intentos == 1
    estado, _ = tocar(evaluador, suena(40), instante)
    assert estado.indice == 1


def test_el_informe_registra_los_intentos_que_costo_cada_nota():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(2):
        _, instante = tocar(evaluador, suena(45), instante)
    _, instante = tocar(evaluador, suena(40), instante)
    assert evaluador.resultado().notas[0].intentos == 3


def test_una_nota_correcta_pero_desafinada_cuenta_como_acierto():
    """Regla 2: la afinacion se mide, no bloquea."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, _ = tocar(evaluador, suena(40, cents=20.0), 0.0)
    assert estado.indice == 1
    assert evaluador.resultado().notas[0].cents == pytest.approx(20.0)


def test_un_ataque_sin_nota_creible_no_cuenta_como_fallo():
    """Regla 1: un roce o un armonico accidental no debe puntuar en contra."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    estado, _ = tocar(evaluador, suena(45, confianza=0.2), 0.0)
    assert estado.intentos == 0
    assert estado.indice == 0


def test_el_silencio_no_cuenta_como_fallo():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(30):
        estado = evaluador.procesar(silencio(), instante)
        instante += PASO
    assert estado.intentos == 0


def test_una_nota_sostenida_cuenta_una_sola_vez():
    """Sesenta resultados diciendo Mi son un intento, no sesenta."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    estado, _ = tocar(evaluador, suena(45), 0.0, cuadros=60)
    assert estado.intentos == 1


def test_tras_cinco_fallos_se_muestra_la_ayuda():
    """Regla 3: no se salta el ejercicio, se ayuda."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(5):
        estado, instante = tocar(evaluador, suena(45), instante)
    assert estado.ayuda_visible is True
    assert estado.indice == 0


def test_antes_del_quinto_fallo_no_hay_ayuda():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(4):
        estado, instante = tocar(evaluador, suena(45), instante)
    assert estado.ayuda_visible is False


def test_la_ayuda_queda_registrada_en_el_informe():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    instante = 0.0
    for _ in range(5):
        _, instante = tocar(evaluador, suena(45), instante)
    _, instante = tocar(evaluador, suena(40), instante)
    assert evaluador.resultado().notas[0].ayuda_mostrada is True


def test_el_instante_del_ataque_se_registra_siempre():
    """Aunque el modo por turnos no evalue el tempo, el informe de regularidad lo necesita."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42, 44]))
    instante = 0.0
    for midi in (40, 42, 44):
        _, instante = tocar(evaluador, suena(midi), instante)
    instantes = [n.instante for n in evaluador.resultado().notas]
    assert all(i is not None for i in instantes)
    assert instantes == sorted(instantes)


def test_el_ejercicio_completado_no_sigue_aceptando_notas():
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    _, instante = tocar(evaluador, suena(40), 0.0)
    assert evaluador.estado.completado is True
    estado, _ = tocar(evaluador, suena(42), instante)
    assert estado.completado is True
    assert len(evaluador.resultado().notas) == 1


def test_un_ejercicio_a_medias_da_un_informe_incompleto():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    tocar(evaluador, suena(40), 0.0)
    resultado = evaluador.resultado()
    assert resultado.completado is False
    assert len(resultado.notas) == 1


def test_reiniciar_devuelve_el_evaluador_al_principio():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    tocar(evaluador, suena(40), 0.0)
    evaluador.reiniciar()
    assert evaluador.estado.indice == 0
    assert evaluador.estado.intentos == 0
    assert evaluador.resultado().notas == ()


def test_el_estado_se_serializa_para_la_interfaz():
    evaluador = EvaluadorEjercicio(ejercicio_de([40, 42]))
    datos = evaluador.estado.a_dict()
    assert set(datos) == {
        "indice",
        "total",
        "intentos",
        "ayuda_visible",
        "completado",
        "nota_actual",
        "ultimo_fallo",
    }
    assert datos["nota_actual"]["nombre"] == "E2"


def test_el_ultimo_fallo_dice_que_nota_sono():
    """Para que la pantalla pueda decir 'esperaba Mi, sono La'."""
    evaluador = EvaluadorEjercicio(ejercicio_de([40]))
    estado, _ = tocar(evaluador, suena(45), 0.0)
    assert estado.ultimo_fallo == "A2"
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_evaluacion.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.ejercicios.evaluacion'`

- [ ] **Step 3: Implementar `nucleo/ejercicios/evaluacion.py`**

```python
"""La maquina de estados que corrige lo que tocas.

Consume el mismo flujo de ResultadoAnalisis que alimenta al afinador. Como
ResultadoAnalisis es un dato, toda esta logica se prueba escribiendo la secuencia
exacta que produciria alguien tocando, sin audio y sin hardware.
"""

from dataclasses import dataclass

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.ataques import ESPERA_ESTABILIZACION_S, DetectorAtaques
from nucleo.ejercicios.modelo import Ejercicio, IntentoNota, NotaEsperada, ResultadoEjercicio
from nucleo.musica import nombre_de_midi

# Fallos seguidos en la misma nota antes de resaltar donde esta en el mastil.
INTENTOS_PARA_AYUDA = 5

# Confianza minima del detector de tono para que una lectura cuente como intento.
CONFIANZA_MINIMA = 0.75


@dataclass(frozen=True)
class EstadoEvaluacion:
    """Lo que la pantalla necesita saber en cada instante."""

    indice: int
    total: int
    intentos: int
    ayuda_visible: bool
    completado: bool
    nota_actual: NotaEsperada | None
    ultimo_fallo: str | None = None

    def a_dict(self) -> dict:
        return {
            "indice": self.indice,
            "total": self.total,
            "intentos": self.intentos,
            "ayuda_visible": self.ayuda_visible,
            "completado": self.completado,
            "nota_actual": None if self.nota_actual is None else self.nota_actual.a_dict(),
            "ultimo_fallo": self.ultimo_fallo,
        }


class EvaluadorEjercicio:
    """Corrige un ejercicio nota a nota.

    Tres reglas gobiernan su comportamiento:

    1. Un ataque sin nota creible no cuenta como fallo, sino como que no tocaste
       nada. Un roce o un armonico accidental no deben puntuar en contra.
    2. La afinacion no bloquea: una nota correcta se acepta aunque este a 20
       cents, y la desviacion se guarda para el informe.
    3. Tras INTENTOS_PARA_AYUDA fallos en la misma nota se resalta donde esta. No
       se salta el ejercicio: se ayuda.
    """

    def __init__(
        self,
        ejercicio: Ejercicio,
        detector_ataques: DetectorAtaques | None = None,
        confianza_minima: float = CONFIANZA_MINIMA,
        espera_estabilizacion_s: float = ESPERA_ESTABILIZACION_S,
        intentos_para_ayuda: int = INTENTOS_PARA_AYUDA,
    ) -> None:
        self.ejercicio = ejercicio
        self._detector = detector_ataques or DetectorAtaques()
        self.confianza_minima = confianza_minima
        self.espera_estabilizacion_s = espera_estabilizacion_s
        self.intentos_para_ayuda = intentos_para_ayuda
        self.reiniciar()

    def reiniciar(self) -> None:
        """Vuelve al principio del ejercicio y olvida lo hecho."""
        self._detector.reiniciar()
        self._indice = 0
        self._intentos = 0
        self._ayuda_mostrada = False
        self._ultimo_fallo: str | None = None
        self._lectura_pendiente: float | None = None
        self._instante_ataque: float | None = None
        self._hechas: list[IntentoNota] = []

    @property
    def _nota_actual(self) -> NotaEsperada | None:
        if self._indice >= len(self.ejercicio):
            return None
        return self.ejercicio.notas[self._indice]

    @property
    def estado(self) -> EstadoEvaluacion:
        """Instantanea para la pantalla."""
        return EstadoEvaluacion(
            indice=self._indice,
            total=len(self.ejercicio),
            intentos=self._intentos,
            ayuda_visible=self._ayuda_mostrada,
            completado=self._indice >= len(self.ejercicio),
            nota_actual=self._nota_actual,
            ultimo_fallo=self._ultimo_fallo,
        )

    def procesar(self, resultado: ResultadoAnalisis, instante: float) -> EstadoEvaluacion:
        """Consume un resultado del analisis y devuelve el estado resultante.

        La lectura de la nota es diferida: un ataque no se lee en su instante,
        sino pasada la espera de estabilizacion. Justo en el ataque la senal es
        caotica y leer ahi daria notas falsas.
        """
        if self._indice >= len(self.ejercicio):
            return self.estado

        ataque = self._detector.procesar(resultado.nivel_db, instante)
        if ataque is not None:
            self._lectura_pendiente = ataque.instante + self.espera_estabilizacion_s
            self._instante_ataque = ataque.instante

        if self._lectura_pendiente is not None and instante >= self._lectura_pendiente:
            self._lectura_pendiente = None
            self._resolver(resultado)

        return self.estado

    def _resolver(self, resultado: ResultadoAnalisis) -> None:
        """Decide que hacer con la nota que suena tras un ataque."""
        esperada = self._nota_actual
        if esperada is None:
            return

        # Regla 1: sin nota creible no hubo intento.
        if resultado.estado != "nota" or resultado.nota is None:
            return
        if resultado.confianza < self.confianza_minima:
            return

        self._intentos += 1

        if resultado.nota == nombre_de_midi(esperada.midi):
            # Regla 2: la afinacion se guarda, no bloquea.
            self._hechas.append(
                IntentoNota(
                    indice=self._indice,
                    midi=esperada.midi,
                    intentos=self._intentos,
                    cents=resultado.cents,
                    instante=self._instante_ataque,
                    ayuda_mostrada=self._ayuda_mostrada,
                )
            )
            self._indice += 1
            self._intentos = 0
            self._ayuda_mostrada = False
            self._ultimo_fallo = None
            return

        self._ultimo_fallo = resultado.nota
        # Regla 3: se ayuda, no se salta.
        if self._intentos >= self.intentos_para_ayuda:
            self._ayuda_mostrada = True

    def resultado(self) -> ResultadoEjercicio:
        """Informe de lo hecho hasta ahora."""
        return ResultadoEjercicio(
            ejercicio=self.ejercicio.clave,
            notas=tuple(self._hechas),
            completado=self._indice >= len(self.ejercicio),
        )
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_evaluacion.py -v`
Esperado: PASS, 18 pruebas.

- [ ] **Step 5: Ejecutar la batería completa**

Run: `uv run pytest -q`
Esperado: 260 pasan, 18 saltadas.

- [ ] **Step 6: Commit**

```bash
git add nucleo/ejercicios/evaluacion.py tests/test_evaluacion.py
git commit -m "feat: evaluador de ejercicios con las tres reglas pedagogicas"
```

---

### Task 8: Síntesis de tonos y metrónomo

**Files:**
- Create: `nucleo/sintesis.py`
- Test: `tests/test_sintesis.py`

**Interfaces:**
- Consumes: `nucleo.musica.midi_a_frecuencia`
- Produces:
  - `FRECUENCIA_MUESTREO_SALIDA: int` = `48000`
  - `tono(frecuencia: float, duracion_s: float, frecuencia_muestreo: int = 48000, armonicos: tuple[float, ...] = (1.0, 0.4, 0.2), ataque_s: float = 0.005, caida_s: float = 0.08) -> np.ndarray`
  - `tono_de_midi(midi: int, duracion_s: float = 0.6, referencia_a4: float = 440.0, **kwargs) -> np.ndarray`
  - `click(frecuencia_muestreo: int = 48000, acentuado: bool = False) -> np.ndarray`
  - `SalidaAudio(frecuencia_muestreo: int = 48000, abrir_stream=None)` con `abrir() -> bool`, `reproducir(muestras: np.ndarray) -> bool`, `cerrar() -> None`, y las propiedades `activa: bool`, `ultimo_error: str | None`
  - `Metronomo(tempo: int, compas: int = 4, salida: SalidaAudio | None = None)` con `iniciar() -> bool`, `detener() -> None`, y las propiedades `sonando: bool`, `pulsos_emitidos: int`

**Contexto para quien implementa.** La etapa 1 solo escuchaba; esta es la primera vez que el software **emite** sonido.

**Una ventaja gratuita del cable.** El sonido sale por los altavoces del Mac y el cable Rocksmith solo capta la guitarra: el metrónomo **no contamina la detección**. Con un micrófono habría que resolver la realimentación; aquí el problema no existe. No añadas cancelación de nada.

**La envolvente importa más que la onda.** Una senoide pura que empieza y acaba de golpe produce un chasquido en los extremos, porque la señal salta de cero a su amplitud en una muestra. El ataque y la caída suaves eliminan eso. Son cinco milisegundos de subida: no se oyen como tal, pero sin ellos el tono suena sucio.

**Quedarse sin salida de audio degrada, no aborta.** Si el dispositivo de salida falla, `SalidaAudio.abrir()` devuelve `False` y guarda el error, igual que hace `CapturaAudio`. El ejercicio seguirá funcionando sin metrónomo. La spec §5 es explícita: abortar un ejercicio porque no hay altavoces sería desproporcionado.

`abrir_stream` se inyecta en las pruebas, exactamente como en `nucleo/captura.py`. **Ninguna prueba abre el dispositivo real.**

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_sintesis.py
import numpy as np
import pytest

from nucleo.sintesis import (
    FRECUENCIA_MUESTREO_SALIDA,
    Metronomo,
    SalidaAudio,
    click,
    tono,
    tono_de_midi,
)

FS = FRECUENCIA_MUESTREO_SALIDA


def frecuencia_dominante(muestras: np.ndarray, fs: int = FS) -> float:
    """Frecuencia del pico del espectro, para comprobar que el tono suena donde debe."""
    espectro = np.abs(np.fft.rfft(muestras.astype(np.float64)))
    return float(np.fft.rfftfreq(muestras.size, 1 / fs)[np.argmax(espectro)])


def test_el_tono_dura_lo_que_se_le_pide():
    assert tono(440.0, 0.5).size == int(0.5 * FS)


def test_el_tono_suena_en_la_frecuencia_pedida():
    assert frecuencia_dominante(tono(440.0, 1.0)) == pytest.approx(440.0, abs=2.0)


def test_el_tono_no_satura():
    assert np.max(np.abs(tono(440.0, 0.5))) <= 1.0


def test_el_tono_es_float32():
    assert tono(440.0, 0.1).dtype == np.float32


def test_la_envolvente_evita_el_chasquido_de_los_extremos():
    """Una senoide que empieza de golpe salta de cero a su amplitud en una muestra."""
    muestras = tono(440.0, 0.5)
    assert abs(muestras[0]) < 0.01
    assert abs(muestras[-1]) < 0.01


def test_el_tono_tiene_armonicos_y_no_es_una_senoide_pura():
    """Para que no suene a pitido de test."""
    muestras = tono(220.0, 1.0, armonicos=(1.0, 0.5))
    espectro = np.abs(np.fft.rfft(muestras.astype(np.float64)))
    frecuencias = np.fft.rfftfreq(muestras.size, 1 / FS)
    energia_segundo = espectro[np.argmin(np.abs(frecuencias - 440.0))]
    assert energia_segundo > espectro.max() * 0.1


def test_el_tono_de_una_nota_midi_suena_donde_debe():
    """El La4 de MIDI 69 son 440 Hz."""
    assert frecuencia_dominante(tono_de_midi(69, duracion_s=1.0)) == pytest.approx(440.0, abs=2.0)


def test_el_click_es_corto():
    assert click().size < int(0.1 * FS)


def test_el_click_acentuado_suena_mas_agudo():
    normal = frecuencia_dominante(click(), FS)
    acentuado = frecuencia_dominante(click(acentuado=True), FS)
    assert acentuado > normal


class StreamSalidaFalso:
    """Doble de sounddevice.OutputStream para probar sin hardware."""

    def __init__(self, **kwargs):
        self.escrito = []
        self.cerrado = False

    def start(self):
        pass

    def write(self, muestras):
        self.escrito.append(np.asarray(muestras).copy())

    def stop(self):
        pass

    def close(self):
        self.cerrado = True


def test_la_salida_reproduce_lo_que_se_le_da():
    creados = []

    def abrir(**kwargs):
        stream = StreamSalidaFalso(**kwargs)
        creados.append(stream)
        return stream

    salida = SalidaAudio(abrir_stream=abrir)
    assert salida.abrir() is True
    assert salida.reproducir(tono(440.0, 0.1)) is True
    assert len(creados[0].escrito) == 1
    salida.cerrar()
    assert creados[0].cerrado is True


def test_un_fallo_al_abrir_la_salida_se_guarda_en_lugar_de_reventar():
    """Quedarse sin metronomo degrada el ejercicio; no lo aborta."""

    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    salida = SalidaAudio(abrir_stream=abrir_que_falla)
    assert salida.abrir() is False
    assert salida.activa is False
    assert "No output device" in salida.ultimo_error


def test_reproducir_sin_salida_abierta_devuelve_false_sin_reventar():
    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    salida = SalidaAudio(abrir_stream=abrir_que_falla)
    salida.abrir()
    assert salida.reproducir(tono(440.0, 0.1)) is False


def test_cerrar_dos_veces_no_falla():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    salida.cerrar()
    salida.cerrar()


def test_el_metronomo_emite_pulsos_al_tempo_pedido():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=600, salida=salida)  # 10 pulsos por segundo
    assert metronomo.iniciar() is True
    import time

    time.sleep(0.45)
    metronomo.detener()
    assert 3 <= metronomo.pulsos_emitidos <= 6


def test_detener_el_metronomo_deja_de_emitir():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=600, salida=salida)
    metronomo.iniciar()
    import time

    time.sleep(0.2)
    metronomo.detener()
    emitidos = metronomo.pulsos_emitidos
    time.sleep(0.2)
    assert metronomo.pulsos_emitidos == emitidos
    assert metronomo.sonando is False


def test_detener_dos_veces_no_falla():
    salida = SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    salida.abrir()
    metronomo = Metronomo(tempo=120, salida=salida)
    metronomo.iniciar()
    metronomo.detener()
    metronomo.detener()


def test_el_metronomo_sin_salida_no_arranca_pero_no_revienta():
    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    salida = SalidaAudio(abrir_stream=abrir_que_falla)
    salida.abrir()
    metronomo = Metronomo(tempo=120, salida=salida)
    assert metronomo.iniciar() is False
    assert metronomo.sonando is False
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_sintesis.py -v`
Esperado: FAIL con `ModuleNotFoundError: No module named 'nucleo.sintesis'`

- [ ] **Step 3: Implementar `nucleo/sintesis.py`**

```python
"""Generacion de sonido: tonos de referencia y click de metronomo.

La etapa 1 solo escuchaba; esta es la primera vez que el software emite. El
sonido sale por los altavoces del Mac y el cable Rocksmith solo capta la
guitarra, asi que el metronomo NO contamina la deteccion: con un microfono habria
que resolver la realimentacion, aqui el problema no existe.
"""

import threading
import time
from typing import Callable

import numpy as np

from nucleo.musica import midi_a_frecuencia

FRECUENCIA_MUESTREO_SALIDA = 48000

# Frecuencias del click. El acentuado marca el primer tiempo del compas.
FRECUENCIA_CLICK = 1000.0
FRECUENCIA_CLICK_ACENTUADO = 1500.0
DURACION_CLICK_S = 0.03


def _envolvente(n: int, frecuencia_muestreo: int, ataque_s: float, caida_s: float) -> np.ndarray:
    """Rampa de entrada y salida para evitar el chasquido de los extremos.

    Una senoide que empieza de golpe salta de cero a su amplitud en una sola
    muestra, y eso se oye como un clic sucio. Cinco milisegundos de subida no se
    perciben como tales pero eliminan el artefacto.
    """
    envolvente = np.ones(n, dtype=np.float64)
    muestras_ataque = min(int(ataque_s * frecuencia_muestreo), n // 2)
    muestras_caida = min(int(caida_s * frecuencia_muestreo), n // 2)
    if muestras_ataque > 0:
        envolvente[:muestras_ataque] = np.linspace(0.0, 1.0, muestras_ataque)
    if muestras_caida > 0:
        envolvente[-muestras_caida:] = np.linspace(1.0, 0.0, muestras_caida)
    return envolvente


def tono(
    frecuencia: float,
    duracion_s: float,
    frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA,
    armonicos: tuple[float, ...] = (1.0, 0.4, 0.2),
    ataque_s: float = 0.005,
    caida_s: float = 0.08,
) -> np.ndarray:
    """Tono con armonicos y envolvente suave.

        x(t) = sum_k  a_k · sin(2π · k · f · t)   por la envolvente

    Los armonicos evitan que suene a pitido de test: una senoide pura es
    desagradable y cuesta identificar su altura.
    """
    n = int(duracion_s * frecuencia_muestreo)
    t = np.arange(n) / frecuencia_muestreo
    onda = np.zeros(n, dtype=np.float64)
    for indice, peso in enumerate(armonicos, start=1):
        onda += peso * np.sin(2 * np.pi * frecuencia * indice * t)
    if np.max(np.abs(onda)) > 0:
        onda /= np.max(np.abs(onda))
    onda *= _envolvente(n, frecuencia_muestreo, ataque_s, caida_s)
    return onda.astype(np.float32)


def tono_de_midi(
    midi: int,
    duracion_s: float = 0.6,
    referencia_a4: float = 440.0,
    **argumentos,
) -> np.ndarray:
    """Tono de una nota MIDI, usando la misma conversion que el resto del nucleo."""
    return tono(midi_a_frecuencia(midi, referencia_a4), duracion_s, **argumentos)


def click(
    frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA, acentuado: bool = False
) -> np.ndarray:
    """Click corto de metronomo. El acentuado, mas agudo, marca el primer tiempo."""
    frecuencia = FRECUENCIA_CLICK_ACENTUADO if acentuado else FRECUENCIA_CLICK
    return tono(
        frecuencia,
        DURACION_CLICK_S,
        frecuencia_muestreo=frecuencia_muestreo,
        armonicos=(1.0,),
        ataque_s=0.001,
        caida_s=0.02,
    )


def _abrir_stream_real(**argumentos):
    """Abre un OutputStream de sounddevice. Aislado para poder sustituirlo."""
    import sounddevice

    return sounddevice.OutputStream(**argumentos)


class SalidaAudio:
    """Salida de audio por los altavoces del sistema.

    Quedarse sin salida degrada la experiencia, no la impide: abrir() devuelve
    False y guarda el error en vez de lanzar, para que el ejercicio pueda seguir
    sin metronomo.
    """

    def __init__(
        self,
        frecuencia_muestreo: int = FRECUENCIA_MUESTREO_SALIDA,
        abrir_stream: Callable | None = None,
    ) -> None:
        self.frecuencia_muestreo = frecuencia_muestreo
        self._abrir_stream = abrir_stream or _abrir_stream_real
        self._stream = None
        self._ultimo_error: str | None = None

    @property
    def activa(self) -> bool:
        return self._stream is not None

    @property
    def ultimo_error(self) -> str | None:
        return self._ultimo_error

    def abrir(self) -> bool:
        """Abre el stream de salida. Devuelve False y guarda el error si no se pudo."""
        if self._stream is not None:
            return True
        try:
            self._stream = self._abrir_stream(
                samplerate=self.frecuencia_muestreo, channels=1, dtype="float32"
            )
            self._stream.start()
            self._ultimo_error = None
            return True
        except Exception as error:
            self._stream = None
            self._ultimo_error = str(error)
            return False

    def reproducir(self, muestras: np.ndarray) -> bool:
        """Envia muestras a los altavoces. Devuelve False si no hay salida abierta."""
        if self._stream is None:
            return False
        try:
            self._stream.write(muestras)
            return True
        except Exception as error:
            self._ultimo_error = str(error)
            return False

    def cerrar(self) -> None:
        """Cierra el stream. Seguro de llamar varias veces."""
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None


class Metronomo:
    """Emite un click por pulso en un hilo aparte."""

    def __init__(self, tempo: int, compas: int = 4, salida: SalidaAudio | None = None) -> None:
        if tempo < 1:
            raise ValueError("El tempo debe ser al menos 1 pulso por minuto")
        self.tempo = tempo
        self.compas = compas
        self._salida = salida or SalidaAudio()
        self._hilo: threading.Thread | None = None
        self._parar = threading.Event()
        self._pulsos = 0
        self._click_normal = click(self._salida.frecuencia_muestreo)
        self._click_acentuado = click(self._salida.frecuencia_muestreo, acentuado=True)

    @property
    def sonando(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    @property
    def pulsos_emitidos(self) -> int:
        return self._pulsos

    def iniciar(self) -> bool:
        """Arranca el metronomo. Devuelve False si no hay salida de audio."""
        if self.sonando:
            return True
        if not self._salida.activa:
            return False
        self._parar.clear()
        self._pulsos = 0
        self._hilo = threading.Thread(target=self._trabajar, daemon=True)
        self._hilo.start()
        return True

    def _trabajar(self) -> None:
        """Hilo del metronomo: un click cada 60/tempo segundos."""
        intervalo = 60.0 / self.tempo
        siguiente = time.monotonic()
        while not self._parar.is_set():
            acentuado = self._pulsos % self.compas == 0
            self._salida.reproducir(self._click_acentuado if acentuado else self._click_normal)
            self._pulsos += 1
            siguiente += intervalo
            espera = max(0.0, siguiente - time.monotonic())
            if self._parar.wait(espera):
                return

    def detener(self) -> None:
        """Para el metronomo. Seguro de llamar varias veces."""
        self._parar.set()
        if self._hilo is not None:
            self._hilo.join(timeout=1.0)
            self._hilo = None
```

- [ ] **Step 4: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_sintesis.py -v`
Esperado: PASS, 17 pruebas.

- [ ] **Step 5: Commit**

```bash
git add nucleo/sintesis.py tests/test_sintesis.py
git commit -m "feat: sintesis de tonos y metronomo con salida por CoreAudio"
```

---

### Task 9: Observadores en la sesión de audio, y la sesión de práctica

**Files:**
- Modify: `servidor/sesion.py` (añade el registro de observadores)
- Create: `servidor/ejercicios.py`
- Test: `tests/test_observadores.py`
- Test: `tests/test_sesion_practica.py`

**Interfaces:**
- Consumes: `servidor.sesion.Sesion`, `nucleo.ejercicios.evaluacion.EvaluadorEjercicio`, `nucleo.ejercicios.modelo.Ejercicio`, `nucleo.sintesis.Metronomo`, `nucleo.sintesis.SalidaAudio`, los cuatro generadores
- Produces:
  - En `sesion.py`: `Sesion.registrar_observador(callback: Callable[[ResultadoAnalisis, float], None]) -> None` y `Sesion.quitar_observador(callback) -> None`
  - En `ejercicios.py`: `GENERADORES: dict[str, Callable[..., Ejercicio]]` con las claves `"escala"`, `"arpegio"`, `"intervalo"`, `"lectura"`; `SesionPractica(sesion_audio: Sesion, salida: SalidaAudio | None = None)` con `generar(familia: str, **parametros) -> Ejercicio`, `iniciar(ejercicio: Ejercicio, con_metronomo: bool = True) -> dict`, `detener() -> None`, `estado() -> dict`, y las propiedades `activa: bool`, `ejercicio: Ejercicio | None`

**Contexto para quien implementa. Hay aquí un problema de diseño que no es obvio y que conviene entender antes de escribir nada.**

La `Sesion` de la etapa 1 guarda **solo el último resultado**, deliberadamente: el afinador quiere ver el presente, no una cola. Pero el evaluador necesita **todos** los resultados, porque la detección de ataques trabaja sobre la evolución de la energía. Si la sesión de práctica muestrease el último resultado desde otro hilo, perdería cuadros y se comería ataques.

La solución es un **observador**: la sesión de audio admite funciones que se invocan con cada resultado que produce, en su propio hilo de análisis. El afinador sigue leyendo el último valor como siempre; la práctica se suscribe.

**Dos cautelas que debes respetar al tocar `_trabajar`:**

1. El observador se invoca **dentro del hilo de análisis**, así que debe ser rápido. Documenta esa condición en el docstring de `registrar_observador`. El evaluador cumple: solo hace comparaciones.
2. Una excepción en un observador **no debe matar el hilo**. Ese hilo ya tiene su `try/except` general desde la corrección final de la etapa 1; asegúrate de que la invocación de observadores queda dentro, y de que un observador roto no impide llamar a los demás.

Respeta también el contador de generación: los observadores se invocan solo cuando el resultado se publica de verdad, no cuando se descarta por obsoleto.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_observadores.py
import time

import numpy as np

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from servidor.configuracion import Configuracion
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


def sesion_falsa() -> Sesion:
    return Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )


def test_un_observador_recibe_los_resultados():
    recibidos = []
    sesion = sesion_falsa()
    sesion.registrar_observador(lambda resultado, instante: recibidos.append(resultado))
    sesion.iniciar()
    time.sleep(0.3)
    sesion.detener()
    assert len(recibidos) > 3


def test_el_observador_recibe_tambien_el_instante():
    instantes = []
    sesion = sesion_falsa()
    sesion.registrar_observador(lambda resultado, instante: instantes.append(instante))
    sesion.iniciar()
    time.sleep(0.3)
    sesion.detener()
    assert instantes == sorted(instantes)


def test_quitar_el_observador_deja_de_entregarle():
    recibidos = []

    def observador(resultado, instante):
        recibidos.append(resultado)

    sesion = sesion_falsa()
    sesion.registrar_observador(observador)
    sesion.iniciar()
    time.sleep(0.2)
    sesion.quitar_observador(observador)
    cuantos = len(recibidos)
    time.sleep(0.2)
    sesion.detener()
    assert len(recibidos) == cuantos


def test_un_observador_que_revienta_no_mata_el_hilo_ni_a_los_demas():
    """Un observador roto no puede tumbar el analisis del afinador."""
    buenos = []

    def roto(resultado, instante):
        raise RuntimeError("observador defectuoso")

    sesion = sesion_falsa()
    sesion.registrar_observador(roto)
    sesion.registrar_observador(lambda resultado, instante: buenos.append(resultado))
    sesion.iniciar()
    time.sleep(0.3)
    assert sesion.activa is True
    assert len(buenos) > 3
    sesion.detener()


def test_sin_observadores_la_sesion_funciona_igual():
    sesion = sesion_falsa()
    sesion.iniciar()
    time.sleep(0.2)
    assert sesion.ultimo_resultado() is not None
    sesion.detener()
```

```python
# tests/test_sesion_practica.py
import time

import numpy as np
import pytest

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.sintesis import SalidaAudio
from servidor.configuracion import Configuracion
from servidor.ejercicios import GENERADORES, SesionPractica
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


class StreamSalidaFalso:
    def __init__(self, **kwargs):
        self.cerrado = False

    def start(self):
        pass

    def write(self, muestras):
        pass

    def stop(self):
        pass

    def close(self):
        self.cerrado = True


def practica() -> SesionPractica:
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    return SesionPractica(sesion, salida=SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso()))


def test_las_cuatro_familias_estan_registradas():
    assert set(GENERADORES) == {"escala", "arpegio", "intervalo", "lectura"}


def test_generar_devuelve_un_ejercicio_de_la_familia_pedida():
    sesion = practica()
    ejercicio = sesion.generar("escala", raiz_midi=48, tipo="mayor")
    assert len(ejercicio) > 0
    assert "escala" in ejercicio.clave
    sesion.detener()


def test_una_familia_inexistente_se_rechaza():
    sesion = practica()
    with pytest.raises(ValueError, match="familia"):
        sesion.generar("solfeo")
    sesion.detener()


def test_un_parametro_invalido_se_propaga_con_su_mensaje():
    sesion = practica()
    with pytest.raises(ValueError, match="escala"):
        sesion.generar("escala", tipo="inventada")
    sesion.detener()


def test_iniciar_suscribe_el_evaluador_al_flujo_de_audio():
    sesion = practica()
    ejercicio = sesion.generar("escala", traste_maximo=4)
    sesion.iniciar(ejercicio, con_metronomo=False)
    assert sesion.activa is True
    time.sleep(0.3)
    assert sesion.estado()["evaluacion"]["total"] == len(ejercicio)
    sesion.detener()


def test_detener_desuscribe_y_para_el_metronomo():
    sesion = practica()
    ejercicio = sesion.generar("escala", traste_maximo=4)
    sesion.iniciar(ejercicio)
    sesion.detener()
    assert sesion.activa is False
    assert sesion.ejercicio is None


def test_el_estado_sin_ejercicio_lo_dice_sin_reventar():
    sesion = practica()
    estado = sesion.estado()
    assert estado["ejercicio"] is None
    assert estado["evaluacion"] is None
    sesion.detener()


def test_el_estado_trae_ejercicio_evaluacion_e_informe():
    sesion = practica()
    ejercicio = sesion.generar("lectura", repeticiones=3, semilla=1)
    sesion.iniciar(ejercicio, con_metronomo=False)
    estado = sesion.estado()
    assert set(estado) >= {"ejercicio", "evaluacion", "informe", "metronomo"}
    sesion.detener()


def test_sin_salida_de_audio_el_ejercicio_arranca_igual_sin_metronomo():
    """La spec es explicita: quedarse sin altavoces degrada, no aborta."""
    sesion_audio = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion_audio.iniciar()

    def abrir_que_falla(**kwargs):
        raise OSError("No output device")

    sesion = SesionPractica(sesion_audio, salida=SalidaAudio(abrir_stream=abrir_que_falla))
    ejercicio = sesion.generar("lectura", repeticiones=2, semilla=1)
    estado = sesion.iniciar(ejercicio, con_metronomo=True)
    assert sesion.activa is True
    assert estado["metronomo"] is False
    sesion.detener()


def test_iniciar_dos_veces_reemplaza_el_ejercicio_anterior():
    sesion = practica()
    primero = sesion.generar("lectura", repeticiones=2, semilla=1)
    segundo = sesion.generar("lectura", repeticiones=5, semilla=2)
    sesion.iniciar(primero, con_metronomo=False)
    sesion.iniciar(segundo, con_metronomo=False)
    assert sesion.estado()["evaluacion"]["total"] == 5
    sesion.detener()


def test_detener_dos_veces_no_falla():
    sesion = practica()
    sesion.detener()
    sesion.detener()
```

- [ ] **Step 2: Ejecutar las pruebas y verificar que fallan**

Run: `uv run pytest tests/test_observadores.py tests/test_sesion_practica.py -v`
Esperado: FAIL — `Sesion` no tiene `registrar_observador` y no existe `servidor.ejercicios`.

- [ ] **Step 3: Añadir los observadores a `servidor/sesion.py`**

En el `__init__`, añade `self._observadores: list[Callable] = []`. Añade los dos métodos:

```python
    def registrar_observador(self, observador: Callable) -> None:
        """Suscribe una funcion que recibira (resultado, instante) de cada analisis.

        El afinador lee el ultimo resultado y le basta; el evaluador de ejercicios
        necesita TODOS los resultados, porque la deteccion de ataques trabaja sobre
        la evolucion de la energia y muestrear perderia cuadros.

        El observador se invoca DENTRO del hilo de analisis, asi que debe ser
        rapido: nada de red, nada de disco, nada que bloquee.
        """
        if observador not in self._observadores:
            self._observadores.append(observador)

    def quitar_observador(self, observador: Callable) -> None:
        """Desuscribe un observador. No falla si no estaba."""
        if observador in self._observadores:
            self._observadores.remove(observador)
```

En `_trabajar`, justo después de publicar el resultado bajo el candado y **solo cuando se publica de verdad** (es decir, dentro de la rama donde la generación no cambió), invoca a los observadores:

```python
                        self._ultimo = resultado
                        instante = time.monotonic()
                        for observador in list(self._observadores):
                            try:
                                observador(resultado, instante)
                            except Exception:
                                # Un observador roto no puede tumbar el analisis
                                # del afinador ni impedir que corran los demas.
                                continue
```

Se itera sobre una copia de la lista porque un observador podría desuscribirse a sí mismo durante la llamada.

- [ ] **Step 4: Implementar `servidor/ejercicios.py`**

```python
"""La sesion de practica: une el generador, el evaluador y el metronomo."""

from typing import Callable

from nucleo.ejercicios.evaluacion import EvaluadorEjercicio
from nucleo.ejercicios.generadores.arpegios import generar_arpegio
from nucleo.ejercicios.generadores.escalas import generar_escala
from nucleo.ejercicios.generadores.intervalos import generar_intervalo
from nucleo.ejercicios.generadores.lectura import generar_lectura
from nucleo.ejercicios.modelo import Ejercicio
from nucleo.sintesis import Metronomo, SalidaAudio
from servidor.sesion import Sesion

GENERADORES: dict[str, Callable[..., Ejercicio]] = {
    "escala": generar_escala,
    "arpegio": generar_arpegio,
    "intervalo": generar_intervalo,
    "lectura": generar_lectura,
}


class SesionPractica:
    """Propietaria del ejercicio en curso, su evaluador y su metronomo.

    Se suscribe al flujo de la sesion de audio en lugar de muestrearlo: la
    deteccion de ataques necesita todos los resultados, no el ultimo.
    """

    def __init__(self, sesion_audio: Sesion, salida: SalidaAudio | None = None) -> None:
        self._sesion_audio = sesion_audio
        self._salida = salida or SalidaAudio()
        self._ejercicio: Ejercicio | None = None
        self._evaluador: EvaluadorEjercicio | None = None
        self._metronomo: Metronomo | None = None

    @property
    def activa(self) -> bool:
        return self._evaluador is not None

    @property
    def ejercicio(self) -> Ejercicio | None:
        return self._ejercicio

    def generar(self, familia: str, **parametros) -> Ejercicio:
        """Genera un ejercicio de la familia pedida.

        Los errores de parametros suben tal cual desde el generador: sus mensajes
        ya explican que escala o que perfil no existe.
        """
        if familia not in GENERADORES:
            disponibles = ", ".join(sorted(GENERADORES))
            raise ValueError(f"La familia '{familia}' no existe. Opciones: {disponibles}")
        return GENERADORES[familia](**parametros)

    def _observar(self, resultado, instante: float) -> None:
        """Alimenta al evaluador. Se invoca en el hilo de analisis: solo comparaciones."""
        evaluador = self._evaluador
        if evaluador is not None:
            evaluador.procesar(resultado, instante)

    def iniciar(self, ejercicio: Ejercicio, con_metronomo: bool = True) -> dict:
        """Arranca un ejercicio. Devuelve el estado inicial.

        Si se pide metronomo y no hay salida de audio, el ejercicio arranca igual
        sin el: la spec dice que quedarse sin altavoces degrada la experiencia,
        no la impide.
        """
        self.detener()
        self._ejercicio = ejercicio
        self._evaluador = EvaluadorEjercicio(ejercicio)
        self._sesion_audio.registrar_observador(self._observar)

        sonando = False
        if con_metronomo:
            if self._salida.abrir():
                self._metronomo = Metronomo(ejercicio.tempo, salida=self._salida)
                sonando = self._metronomo.iniciar()
        return {**self.estado(), "metronomo": sonando}

    def detener(self) -> None:
        """Para el ejercicio y suelta todo. Seguro de llamar varias veces."""
        self._sesion_audio.quitar_observador(self._observar)
        if self._metronomo is not None:
            self._metronomo.detener()
            self._metronomo = None
        self._salida.cerrar()
        self._evaluador = None
        self._ejercicio = None

    def estado(self) -> dict:
        """Lo que la interfaz necesita: el ejercicio, el avance y el informe."""
        evaluador = self._evaluador
        return {
            "ejercicio": None if self._ejercicio is None else self._ejercicio.a_dict(),
            "evaluacion": None if evaluador is None else evaluador.estado.a_dict(),
            "informe": None if evaluador is None else evaluador.resultado().a_dict(),
            "metronomo": self._metronomo is not None and self._metronomo.sonando,
        }
```

- [ ] **Step 5: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_observadores.py tests/test_sesion_practica.py tests/test_sesion.py -v`
Esperado: PASS. Las pruebas de `test_sesion.py` de la etapa 1 deben seguir en verde **sin tocarlas**: son la red que garantiza que añadir observadores no rompió el afinador.

- [ ] **Step 6: Commit**

```bash
git add servidor/sesion.py servidor/ejercicios.py tests/test_observadores.py tests/test_sesion_practica.py
git commit -m "feat: observadores en la sesion de audio y sesion de practica"
```

---

### Task 10: Endpoints del módulo de ejercicios

**Files:**
- Modify: `servidor/app.py` (endpoints nuevos y el parámetro `practica`)
- Modify: `servidor/modulos.py` (registra el módulo `"ejercicios"`)
- Modify: `servidor/arranque.py` (construye la `SesionPractica`)
- Test: `tests/test_app_ejercicios.py`

**Interfaces:**
- Consumes: `servidor.ejercicios.SesionPractica`, `servidor.ejercicios.GENERADORES`, `nucleo.ejercicios.teoria.ESCALAS`, `nucleo.ejercicios.teoria.ACORDES`, `nucleo.ejercicios.teoria.INTERVALOS`
- Produces:
  - `crear_app(sesion, ruta_interfaz=None, practica: SesionPractica | None = None) -> FastAPI` — el tercer parámetro es nuevo y opcional
  - `GET /api/ejercicios/familias`, `POST /api/ejercicios/generar`, `POST /api/ejercicios/iniciar`, `POST /api/ejercicios/detener`, `GET /api/ejercicios/estado`, `WS /ws/ejercicios`
  - El módulo `"ejercicios"` registrado en `servidor/modulos.py`

**Contexto para quien implementa.** El servidor sigue siendo una capa fina: no calcula nada, publica lo que la sesión de práctica ya produce.

`GET /api/ejercicios/familias` es lo que permite que el configurador de la interfaz **se construya solo**: devuelve cada familia con sus parámetros y los valores admitidos (los tipos de escala, los acordes, los intervalos). Sin él, la pantalla tendría escritas a mano unas listas que ya viven en `teoria.py`, y añadir la escala dórica obligaría a tocar dos sitios.

El WebSocket de ejercicios emite a los mismos **30 Hz** que el del afinador y por el mismo motivo: la pantalla no muestra más rápido, y saturar el socket solo añade retardo.

Un error de configuración (`ValueError` del generador) responde **400** con el mensaje en español, igual que `PUT /api/config`. Esos mensajes ya explican qué escala o qué perfil no existe: no los reescribas.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_app_ejercicios.py
import numpy as np
import pytest
from fastapi.testclient import TestClient

from nucleo.captura import NOMBRE_ROCKSMITH, DispositivoAudio
from nucleo.sintesis import SalidaAudio
from servidor.app import crear_app
from servidor.configuracion import Configuracion
from servidor.ejercicios import SesionPractica
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


class StreamSalidaFalso:
    def start(self):
        pass

    def write(self, muestras):
        pass

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def cliente(tmp_path):
    sesion = Sesion(
        Configuracion(dispositivo=3),
        crear_captura=lambda **kw: CapturaFalsa(**kw),
        listar=lambda: [CABLE],
    )
    sesion.iniciar()
    practica = SesionPractica(
        sesion, salida=SalidaAudio(abrir_stream=lambda **kw: StreamSalidaFalso())
    )
    app = crear_app(sesion, practica=practica)
    app.state.ruta_config = tmp_path / "config.json"
    with TestClient(app) as cliente:
        yield cliente
    practica.detener()
    sesion.detener()


def test_el_modulo_de_ejercicios_aparece_junto_al_afinador(cliente):
    claves = [m["clave"] for m in cliente.get("/api/modulos").json()]
    assert "afinador" in claves
    assert "ejercicios" in claves


def test_las_familias_traen_sus_parametros_y_valores_admitidos(cliente):
    """Asi el configurador se construye solo, sin listas escritas a mano."""
    familias = cliente.get("/api/ejercicios/familias").json()
    claves = {f["clave"] for f in familias}
    assert claves == {"escala", "arpegio", "intervalo", "lectura"}
    escala = next(f for f in familias if f["clave"] == "escala")
    assert "mayor" in escala["tipos"]
    assert "pentatonica_menor" in escala["tipos"]


def test_generar_devuelve_el_ejercicio_sin_iniciarlo(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "escala", "parametros": {"raiz_midi": 48, "tipo": "mayor"}},
    )
    assert respuesta.status_code == 200
    assert len(respuesta.json()["notas"]) > 0
    assert cliente.get("/api/ejercicios/estado").json()["evaluacion"] is None


def test_una_configuracion_imposible_da_400_con_mensaje_en_espanol(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "escala", "parametros": {"tipo": "inventada"}},
    )
    assert respuesta.status_code == 400
    assert "escala" in respuesta.json()["detail"]


def test_una_familia_inexistente_da_400(cliente):
    respuesta = cliente.post("/api/ejercicios/generar", json={"familia": "solfeo"})
    assert respuesta.status_code == 400
    assert "familia" in respuesta.json()["detail"]


def test_un_rango_de_trastes_sin_notas_da_400(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/generar",
        json={"familia": "escala", "parametros": {"traste_minimo": 30, "traste_maximo": 30}},
    )
    assert respuesta.status_code == 400
    assert "ninguna nota" in respuesta.json()["detail"]


def test_iniciar_deja_el_ejercicio_en_curso(cliente):
    respuesta = cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 4, "semilla": 1}},
    )
    assert respuesta.status_code == 200
    estado = cliente.get("/api/ejercicios/estado").json()
    assert estado["evaluacion"]["total"] == 4
    assert estado["evaluacion"]["indice"] == 0


def test_detener_limpia_el_ejercicio(cliente):
    cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 3, "semilla": 1}},
    )
    assert cliente.post("/api/ejercicios/detener").status_code == 200
    assert cliente.get("/api/ejercicios/estado").json()["evaluacion"] is None


def test_el_estado_sin_ejercicio_responde_sin_reventar(cliente):
    estado = cliente.get("/api/ejercicios/estado").json()
    assert estado["ejercicio"] is None
    assert estado["evaluacion"] is None


def test_el_websocket_emite_el_estado_del_ejercicio(cliente):
    cliente.post(
        "/api/ejercicios/iniciar",
        json={"familia": "lectura", "parametros": {"repeticiones": 3, "semilla": 1}},
    )
    with cliente.websocket_connect("/ws/ejercicios") as socket:
        mensaje = socket.receive_json()
        assert set(mensaje) >= {"ejercicio", "evaluacion", "informe", "metronomo"}
        assert mensaje["evaluacion"]["total"] == 3


def test_el_websocket_emite_aunque_no_haya_ejercicio(cliente):
    with cliente.websocket_connect("/ws/ejercicios") as socket:
        mensaje = socket.receive_json()
        assert mensaje["ejercicio"] is None
```

- [ ] **Step 2: Ejecutar la prueba y verificar que falla**

Run: `uv run pytest tests/test_app_ejercicios.py -v`
Esperado: FAIL — `crear_app` no acepta `practica` y no existen los endpoints.

- [ ] **Step 3: Registrar el módulo en `servidor/modulos.py`**

Al final del archivo, junto al registro del afinador:

```python
registrar_modulo(
    Modulo(
        clave="ejercicios",
        nombre="Ejercicios",
        descripcion="Escalas, arpegios, intervalos y lectura del mastil, con correccion",
        icono="🎯",
    )
)
```

- [ ] **Step 4: Añadir los endpoints a `servidor/app.py`**

Cambia la firma a `crear_app(sesion: Sesion, ruta_interfaz: Path | None = None, practica: SesionPractica | None = None) -> FastAPI` y guarda `app.state.practica = practica or SesionPractica(sesion)`. Dentro de `crear_app`, añade:

```python
    @app.get("/api/ejercicios/familias")
    def leer_familias() -> list[dict]:
        """Familias con sus parametros y valores admitidos.

        Esto es lo que permite que el configurador de la interfaz se construya
        solo: sin este endpoint la pantalla tendria escritas a mano unas listas
        que ya viven en teoria.py, y anadir la escala dorica obligaria a tocar
        dos sitios.
        """
        return [
            {
                "clave": "escala",
                "nombre": "Escalas",
                "descripcion": "Una escala en una posicion del mastil",
                "tipos": sorted(ESCALAS),
                "parametros": ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
            },
            {
                "clave": "arpegio",
                "nombre": "Arpegios",
                "descripcion": "Las notas de un acorde, una a una",
                "tipos": sorted(ACORDES),
                "parametros": ["raiz_midi", "tipo", "traste_minimo", "traste_maximo", "tempo", "direccion"],
            },
            {
                "clave": "intervalo",
                "nombre": "Intervalos",
                "descripcion": "Suena una nota y tocas la que esta al intervalo pedido",
                "tipos": sorted(INTERVALOS),
                "parametros": ["intervalo", "traste_minimo", "traste_maximo", "tempo", "repeticiones"],
            },
            {
                "clave": "lectura",
                "nombre": "Lectura del mastil",
                "descripcion": "Se nombra una nota y tienes que encontrarla",
                "tipos": [],
                "parametros": ["cuerda", "traste_minimo", "traste_maximo", "tempo", "repeticiones"],
            },
        ]

    @app.post("/api/ejercicios/generar")
    def generar_ejercicio(datos: dict = Body(...)) -> dict:
        """Genera un ejercicio sin iniciarlo, para previsualizarlo."""
        try:
            ejercicio = app.state.practica.generar(
                datos.get("familia", ""), **datos.get("parametros", {})
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return ejercicio.a_dict()

    @app.post("/api/ejercicios/iniciar")
    def iniciar_ejercicio(datos: dict = Body(...)) -> dict:
        """Genera un ejercicio y lo pone en marcha."""
        try:
            ejercicio = app.state.practica.generar(
                datos.get("familia", ""), **datos.get("parametros", {})
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))
        return app.state.practica.iniciar(ejercicio, datos.get("con_metronomo", True))

    @app.post("/api/ejercicios/detener")
    def detener_ejercicio() -> dict:
        app.state.practica.detener()
        return app.state.practica.estado()

    @app.get("/api/ejercicios/estado")
    def leer_estado_ejercicio() -> dict:
        return app.state.practica.estado()

    @app.websocket("/ws/ejercicios")
    async def emitir_ejercicio(websocket: WebSocket) -> None:
        """Emite el estado del ejercicio a 30 Hz, igual que el del afinador."""
        await websocket.accept()
        intervalo = 1.0 / FRECUENCIA_EMISION
        try:
            while True:
                await websocket.send_json(app.state.practica.estado())
                await asyncio.sleep(intervalo)
        except WebSocketDisconnect:
            return
```

Añade los imports necesarios: `ESCALAS`, `ACORDES` e `INTERVALOS` de `nucleo.ejercicios.teoria`, y `SesionPractica` de `servidor.ejercicios`.

- [ ] **Step 5: Conectar la sesión de práctica en `servidor/arranque.py`**

En `construir_aplicacion`, crea la `SesionPractica` con la sesión de audio y pásala a `crear_app`. Devuélvela junto a la app y la sesión para poder detenerla, y añade su `detener()` al `finally` de `main`, junto al de la sesión de audio.

- [ ] **Step 6: Ejecutar las pruebas y verificar que pasan**

Run: `uv run pytest tests/test_app_ejercicios.py tests/test_app.py tests/test_arranque.py -v`
Esperado: PASS. Las pruebas del servidor de la etapa 1 deben seguir en verde sin tocarlas.

- [ ] **Step 7: Commit**

```bash
git add servidor/ tests/test_app_ejercicios.py
git commit -m "feat: endpoints del modulo de ejercicios y su registro"
```

---

### Task 11: La pantalla de ejercicios

**Files:**
- Create: `interfaz/src/tiposEjercicio.ts`
- Create: `interfaz/src/presentacionEjercicio.ts`
- Create: `interfaz/src/useEjercicio.ts`
- Create: `interfaz/src/Configurador.tsx`
- Create: `interfaz/src/Informe.tsx`
- Create: `interfaz/src/Ejercicios.tsx`
- Modify: `interfaz/src/App.tsx` (monta el módulo nuevo)
- Modify: `interfaz/src/estilos.css`
- Test: `interfaz/src/presentacionEjercicio.test.ts`
- Test: `interfaz/src/Ejercicios.test.tsx`

**Interfaces:**
- Consumes: los endpoints de la Task 10, `Mastil` de la etapa 1
- Produces:
  - `tiposEjercicio.ts`: `NotaEjercicio`, `EjercicioServidor`, `EvaluacionServidor`, `InformeServidor`, `EstadoEjercicio`, `FamiliaEjercicio`
  - `presentacionEjercicio.ts`: `fraccionProgreso(indice: number, total: number): number`, `mensajeDeFallo(esperada: string | null, sonada: string | null): string | null`, `calificacion(aciertosALaPrimera: number, total: number): string`
  - `useEjercicio(url?: string)` → `{ estado: EstadoEjercicio | null, conectado: boolean }`
  - Componentes `Configurador`, `Informe`, `Ejercicios`

**Contexto para quien implementa.**

**La interfaz no calcula nada musical**, igual que en la etapa 1. Aquí la tentación es mayor: podrías traducir números MIDI a nombres o decidir si una nota está afinada. No lo hagas — el servidor ya manda el `nombre` de cada nota y el veredicto. Si te falta un dato, falta en el servidor.

**El mástil se reutiliza tal cual.** `Mastil` recibe un perfil y una lista de posiciones; para el ejercicio se le pasan las posiciones de la nota actual. No lo dupliques ni lo bifurques: si necesita una capa más, se le añade una propiedad opcional.

**El configurador se construye desde `/api/ejercicios/familias`**, no desde listas escritas a mano. Es el motivo de que ese endpoint exista.

**La ayuda del mástil.** Cuando `evaluacion.ayuda_visible` es `true`, el mástil resalta la nota actual. Cuando es `false`, no se resalta nada: el ejercicio pide que la encuentres tú. Esa es toda la diferencia visual, y es deliberada.

- [ ] **Step 1: Escribir las pruebas que fallan**

```typescript
// interfaz/src/presentacionEjercicio.test.ts
import { describe, expect, it } from "vitest";

import { calificacion, fraccionProgreso, mensajeDeFallo } from "./presentacionEjercicio";

describe("fraccionProgreso", () => {
  it("al empezar el progreso es cero", () => {
    expect(fraccionProgreso(0, 8)).toBe(0);
  });

  it("al terminar el progreso es uno", () => {
    expect(fraccionProgreso(8, 8)).toBe(1);
  });

  it("a mitad de camino es la mitad", () => {
    expect(fraccionProgreso(4, 8)).toBeCloseTo(0.5);
  });

  it("un ejercicio sin notas no divide por cero", () => {
    expect(fraccionProgreso(0, 0)).toBe(0);
  });

  it("nunca se sale de cero a uno", () => {
    expect(fraccionProgreso(12, 8)).toBe(1);
    expect(fraccionProgreso(-3, 8)).toBe(0);
  });
});

describe("mensajeDeFallo", () => {
  it("dice que esperaba y que sono", () => {
    expect(mensajeDeFallo("E2", "A2")).toContain("E2");
    expect(mensajeDeFallo("E2", "A2")).toContain("A2");
  });

  it("sin fallo no hay mensaje", () => {
    expect(mensajeDeFallo("E2", null)).toBeNull();
  });

  it("sin nota esperada tampoco", () => {
    expect(mensajeDeFallo(null, "A2")).toBeNull();
  });
});

describe("calificacion", () => {
  it("todo a la primera se reconoce", () => {
    expect(calificacion(8, 8).toLowerCase()).toContain("perfecto");
  });

  it("un ejercicio sin notas no divide por cero", () => {
    expect(calificacion(0, 0)).toBeTruthy();
  });

  it("pocos aciertos dan un mensaje distinto que muchos", () => {
    expect(calificacion(2, 10)).not.toBe(calificacion(9, 10));
  });
});
```

```tsx
// interfaz/src/Ejercicios.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Ejercicios } from "./Ejercicios";

const FAMILIAS = [
  {
    clave: "escala",
    nombre: "Escalas",
    descripcion: "Una escala en una posicion",
    tipos: ["mayor", "pentatonica_menor"],
    parametros: ["raiz_midi", "tipo"],
  },
  {
    clave: "lectura",
    nombre: "Lectura del mastil",
    descripcion: "Encuentra la nota",
    tipos: [],
    parametros: ["cuerda"],
  },
];

const PERFILES = [
  {
    clave: "guitarra_estandar",
    nombre: "Guitarra estandar",
    trastes: 22,
    cuerdas: [
      { numero: 6, nota: "E2", frecuencia: 82.41 },
      { numero: 1, nota: "E4", frecuencia: 329.63 },
    ],
  },
];

const ESTADO_VACIO = { ejercicio: null, evaluacion: null, informe: null, metronomo: false };

class WebSocketFalso {
  static ultimo: WebSocketFalso | null = null;
  url: string;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((evento: { data: string }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    WebSocketFalso.ultimo = this;
  }

  close() {}

  enviar(datos: unknown) {
    this.onmessage?.({ data: JSON.stringify(datos) });
  }
}

function responder(cuerpo: unknown, ok = true, estado = 200) {
  return Promise.resolve({
    ok,
    status: estado,
    json: () => Promise.resolve(cuerpo),
  } as Response);
}

describe("Ejercicios", () => {
  beforeEach(() => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (url.includes("/api/perfiles")) return responder(PERFILES);
        if (url.includes("/api/ejercicios/estado")) return responder(ESTADO_VACIO);
        return responder(ESTADO_VACIO);
      })
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("el configurador se construye con las familias del servidor", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(screen.getByText("Lectura del mastil")).toBeTruthy();
  });

  it("muestra los tipos de la familia elegida, no una lista escrita a mano", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    expect(screen.getByText("pentatonica_menor")).toBeTruthy();
  });

  it("muestra la nota que toca ahora cuando hay ejercicio en curso", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar({
      ejercicio: {
        clave: "e",
        nombre: "Escala de Do mayor",
        descripcion: "",
        tempo: 80,
        perfil: "guitarra_estandar",
        notas: [
          { midi: 48, nombre: "C3", posiciones: [{ cuerda: 5, traste: 3 }], pulsos: 1, referencia_midi: null },
        ],
      },
      evaluacion: {
        indice: 0,
        total: 1,
        intentos: 0,
        ayuda_visible: false,
        completado: false,
        nota_actual: { midi: 48, nombre: "C3", posiciones: [{ cuerda: 5, traste: 3 }], pulsos: 1, referencia_midi: null },
        ultimo_fallo: null,
      },
      informe: null,
      metronomo: true,
    });
    await waitFor(() => expect(screen.getByText("C3")).toBeTruthy());
  });

  it("avisa de que nota sono cuando fallas", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar({
      ejercicio: {
        clave: "e",
        nombre: "Prueba",
        descripcion: "",
        tempo: 80,
        perfil: "guitarra_estandar",
        notas: [],
      },
      evaluacion: {
        indice: 0,
        total: 3,
        intentos: 2,
        ayuda_visible: false,
        completado: false,
        nota_actual: { midi: 40, nombre: "E2", posiciones: [], pulsos: 1, referencia_midi: null },
        ultimo_fallo: "A2",
      },
      informe: null,
      metronomo: false,
    });
    await waitFor(() => expect(screen.getByText(/A2/)).toBeTruthy());
  });

  it("muestra el informe al completar el ejercicio", async () => {
    render(<Ejercicios />);
    await waitFor(() => expect(WebSocketFalso.ultimo).not.toBeNull());
    WebSocketFalso.ultimo!.enviar({
      ejercicio: null,
      evaluacion: {
        indice: 2,
        total: 2,
        intentos: 0,
        ayuda_visible: false,
        completado: true,
        nota_actual: null,
        ultimo_fallo: null,
      },
      informe: {
        ejercicio: "e",
        completado: true,
        notas: [
          { indice: 0, midi: 40, nombre: "E2", intentos: 1, cents: 2.0, instante: 0, ayuda_mostrada: false },
          { indice: 1, midi: 42, nombre: "F#2", intentos: 4, cents: -8.0, instante: 1, ayuda_mostrada: false },
        ],
        aciertos_a_la_primera: 1,
        desviacion_mediana_cents: -3.0,
        regularidad_ms: null,
      },
      metronomo: false,
    });
    await waitFor(() => expect(screen.getByText(/F#2/)).toBeTruthy());
  });

  it("un error del servidor al generar se muestra al usuario", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, opciones?: RequestInit) => {
        if (url.includes("/api/ejercicios/familias")) return responder(FAMILIAS);
        if (url.includes("/api/perfiles")) return responder(PERFILES);
        if (opciones?.method === "POST") {
          return responder({ detail: "No cae ninguna nota de la escala" }, false, 400);
        }
        return responder(ESTADO_VACIO);
      })
    );
    render(<Ejercicios />);
    await waitFor(() => expect(screen.getByText("Escalas")).toBeTruthy());
    screen.getByRole("button", { name: /empezar/i }).click();
    await waitFor(() => expect(screen.getByText(/No cae ninguna nota/)).toBeTruthy());
  });
});
```

- [ ] **Step 2: Ejecutar las pruebas y verificar que fallan**

Run: `cd interfaz && pnpm test`
Esperado: FAIL, no existen los módulos.

- [ ] **Step 3: Escribir `interfaz/src/tiposEjercicio.ts`**

Espejo exacto de lo que emite el servidor: `NotaEjercicio` (`midi`, `nombre`, `posiciones`, `pulsos`, `referencia_midi`), `EjercicioServidor` (`clave`, `nombre`, `descripcion`, `notas`, `tempo`, `perfil`), `EvaluacionServidor` (`indice`, `total`, `intentos`, `ayuda_visible`, `completado`, `nota_actual`, `ultimo_fallo`), `InformeServidor` (`ejercicio`, `completado`, `notas`, `aciertos_a_la_primera`, `desviacion_mediana_cents`, `regularidad_ms`), `EstadoEjercicio` (`ejercicio`, `evaluacion`, `informe`, `metronomo`) y `FamiliaEjercicio` (`clave`, `nombre`, `descripcion`, `tipos`, `parametros`). Reutiliza `Posicion` de `tipos.ts`; no la redeclares.

- [ ] **Step 4: Escribir `interfaz/src/presentacionEjercicio.ts`**

```typescript
/** Traducciones de datos a pantalla para los ejercicios. Funciones puras. */

/** Fraccion completada del ejercicio, entre 0 y 1. */
export function fraccionProgreso(indice: number, total: number): number {
  if (total <= 0) return 0;
  return Math.max(0, Math.min(1, indice / total));
}

/**
 * Texto del ultimo fallo, o null si no lo hubo.
 *
 * Decir que sono ademas de que se esperaba es lo que convierte un "mal" en una
 * correccion util: el usuario ve si se equivoco de cuerda, de traste o de octava.
 */
export function mensajeDeFallo(esperada: string | null, sonada: string | null): string | null {
  if (esperada === null || sonada === null) return null;
  return `Esperaba ${esperada} y sono ${sonada}`;
}

/** Resumen en una frase de como fue el ejercicio. */
export function calificacion(aciertosALaPrimera: number, total: number): string {
  if (total <= 0) return "Sin notas";
  if (aciertosALaPrimera === total) return "Perfecto: todas a la primera";
  const proporcion = aciertosALaPrimera / total;
  if (proporcion >= 0.8) return "Muy bien: casi todas a la primera";
  if (proporcion >= 0.5) return "Bien, con algunas que costaron";
  return "Hay material para practicar";
}
```

- [ ] **Step 5: Escribir `useEjercicio.ts`, `Configurador.tsx`, `Informe.tsx` y `Ejercicios.tsx`**

`useEjercicio` es idéntico en estructura a `useNotas` de la etapa 1 —incluida la reconexión automática y el descarte de mensajes no válidos— pero apunta a `/ws/ejercicios` y devuelve `EstadoEjercicio`. **Copia su patrón, no lo reinventes**: closures locales para el socket y el indicador de vida, y un `useRef` solo para el identificador del temporizador.

`Configurador` lee `/api/ejercicios/familias` al montarse, deja elegir familia, tipo y los parámetros comunes (tempo, rango de trastes), y al pulsar «Empezar» hace `POST /api/ejercicios/iniciar`. Si la respuesta no es correcta, muestra el `detail` que manda el servidor.

`Informe` recibe el `InformeServidor` y muestra la calificación, las notas que costaron tres intentos o más, la desviación mediana y la regularidad. Si un valor es `null`, no lo pinta en vez de escribir «null».

`Ejercicios` orquesta: sin ejercicio en curso muestra el `Configurador`; con ejercicio muestra la nota actual, el `Mastil` (resaltando la nota solo si `ayuda_visible`), el progreso y el mensaje de fallo; al completarse muestra el `Informe` y un botón para volver a empezar.

En `App.tsx`, añade el caso `activo === "ejercicios"` para montar `<Ejercicios />`.

- [ ] **Step 6: Ejecutar las pruebas y compilar**

Run: `cd interfaz && pnpm test && pnpm build`
Esperado: PASS, 23 anteriores más las nuevas, y el build compila.

- [ ] **Step 7: Commit**

```bash
git add interfaz/src
git commit -m "feat: pantalla de ejercicios con configurador, mastil e informe"
```

---

### Task 12: Calibración con la guitarra real, documentación y cierre

**Files:**
- Create: `herramientas/calibrar_ataques.py`
- Create: `tests/test_ataques_reales.py`
- Modify: `README.md`
- Modify: `nucleo/ejercicios/ataques.py` (solo los tres valores por defecto, si la calibración lo aconseja)

**Interfaces:**
- Consumes: `nucleo.captura`, `nucleo.analisis.energia.nivel_dbfs`, `nucleo.ejercicios.ataques.DetectorAtaques`
- Produces: `herramientas/calibrar_ataques.py` ejecutable con `uv run python -m herramientas.calibrar_ataques`

**Contexto para quien implementa. Esta tarea cierra el riesgo principal de la etapa.**

Los tres parámetros del detector de ataques se eligieron a ojo. Hasta ahora solo se han probado con envolventes sintéticas, que son demasiado limpias: una pulsación real tiene ruido de púa, decaimiento irregular y resonancia de las cuerdas vecinas.

Las grabaciones de la etapa 1 **no bastan**: son notas sostenidas de tres segundos, una por cuerda. Sirven para comprobar que una nota sostenida da **un** ataque, pero no para comprobar que ocho pulsaciones dan **ocho**. Por eso la herramienta graba una muestra nueva.

El procedimiento: el usuario pulsa una cuerda ocho veces separadas, la herramienta recorre las combinaciones de salto y refractario, y propone la que acierta el número de pulsaciones con más margen. «Con más margen» significa la que sigue acertando si el salto varía un decibelio arriba o abajo: un valor que solo funciona en un punto exacto es un valor que fallará mañana.

**Esta tarea requiere al usuario presente con la guitarra conectada.** Los pasos marcados no los puede ejecutar un agente.

- [ ] **Step 1: Escribir `herramientas/calibrar_ataques.py`**

```python
"""Calibra el detector de ataques con la guitarra real.

Los valores por defecto se eligieron a ojo y solo se han probado con envolventes
sinteticas, que son demasiado limpias: una pulsacion real trae ruido de pua,
decaimiento irregular y resonancia de las cuerdas vecinas.

Uso:  uv run python -m herramientas.calibrar_ataques
"""

import sys
import time

import numpy as np

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import nivel_dbfs
from nucleo.captura import CapturaAudio, buscar_rocksmith
from nucleo.ejercicios.ataques import DetectorAtaques

FS = 48000
PULSACIONES_PEDIDAS = 8
SEGUNDOS = 12.0
PASO_ANALISIS = 0.021

SALTOS = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]
REFRACTARIOS = [0.030, 0.050, 0.080, 0.120, 0.200]


def niveles_de(muestras: np.ndarray, ventana: int) -> list[tuple[float, float]]:
    """Convierte la grabacion en la secuencia (instante, nivel) que vera el detector."""
    salto = int(PASO_ANALISIS * FS)
    return [
        (indice / FS, nivel_dbfs(muestras[indice : indice + ventana]))
        for indice in range(0, len(muestras) - ventana, salto)
    ]


def contar_ataques(niveles, salto_db: float, refractario_s: float) -> int:
    detector = DetectorAtaques(salto_db=salto_db, refractario_s=refractario_s)
    return sum(1 for instante, nivel in niveles if detector.procesar(nivel, instante) is not None)


def main() -> int:
    if not sys.stdin.isatty():
        print("Este script es interactivo: pide pulsar Enter antes de grabar.")
        print("Abre una ventana de Terminal y ejecuta ahi:")
        print("  cd /Users/giocrisraigodoy/Documents/proyecto_musica && "
              "uv run python -m herramientas.calibrar_ataques")
        return 1

    cable = buscar_rocksmith()
    if cable is None:
        print("El cable Rocksmith no aparece. Conectalo y reintenta.")
        return 1

    captura = CapturaAudio(indice_dispositivo=cable.indice, capacidad_buffer=int(FS * (SEGUNDOS + 1)))
    if not captura.iniciar():
        print(f"No se pudo abrir el dispositivo: {captura.ultimo_error}")
        return 1

    print(f"\nPulsa UNA cuerda {PULSACIONES_PEDIDAS} veces, separadas y a volumen normal.")
    print(f"Tienes {SEGUNDOS:.0f} segundos desde que pulses Enter.")
    try:
        input("Enter para empezar...")
    except EOFError:
        captura.detener()
        return 1

    inicio = captura.total_capturado
    while captura.total_capturado - inicio < FS * SEGUNDOS:
        time.sleep(0.05)
    muestras = captura.leer_ventana(int(FS * SEGUNDOS))
    captura.detener()

    ventana = PERFILES["guitarra_estandar"].tamano_ventana(FS)
    niveles = niveles_de(muestras, ventana)

    print(f"\nBuscando los parametros que cuentan {PULSACIONES_PEDIDAS} pulsaciones...\n")
    aciertos = []
    for salto in SALTOS:
        fila = []
        for refractario in REFRACTARIOS:
            contados = contar_ataques(niveles, salto, refractario)
            fila.append(contados)
            if contados == PULSACIONES_PEDIDAS:
                aciertos.append((salto, refractario))
        print(f"  salto {salto:5.1f} dB -> " + "  ".join(f"{c:2d}" for c in fila))
    print(f"  refractarios (ms): " + "  ".join(f"{int(r*1000):2d}" for r in REFRACTARIOS))

    if not aciertos:
        print("\nNinguna combinacion acerta el numero de pulsaciones.")
        print("Repite tocando mas separado, o revisa el volumen de la guitarra.")
        return 1

    # Se prefiere el que sigue acertando con el salto un decibelio arriba y abajo:
    # un valor que solo funciona en un punto exacto fallara manana.
    def robustez(par: tuple[float, float]) -> int:
        salto, refractario = par
        return sum(
            1
            for delta in (-1.0, 0.0, 1.0)
            if contar_ataques(niveles, salto + delta, refractario) == PULSACIONES_PEDIDAS
        )

    mejor = max(aciertos, key=robustez)
    print(f"\nRecomendado: salto {mejor[0]:.1f} dB, refractario {int(mejor[1] * 1000)} ms")
    print(f"Margen: acierta en {robustez(mejor)} de 3 variaciones del salto.")
    print("\nSi difiere de los valores por defecto, actualiza SALTO_ATAQUE_DB y")
    print("REFRACTARIO_S en nucleo/ejercicios/ataques.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Escribir `tests/test_ataques_reales.py`**

```python
"""Deteccion de ataques sobre las grabaciones reales de la guitarra del usuario.

Las envolventes sinteticas son demasiado limpias: una cuerda real trae ruido de
pua, decaimiento irregular y resonancia de las vecinas. Estas pruebas se saltan
mientras no existan las grabaciones, igual que las de test_audio_real.py.
"""

from pathlib import Path

import pytest

soundfile = pytest.importorskip("soundfile")

from nucleo.afinaciones import PERFILES
from nucleo.analisis.energia import nivel_dbfs
from nucleo.ejercicios.ataques import DetectorAtaques

AUDIO = Path(__file__).parent / "audio"
GUITARRA = PERFILES["guitarra_estandar"]
PASO_ANALISIS = 0.021

CUERDAS = [
    "cuerda_6_e2.wav",
    "cuerda_5_a2.wav",
    "cuerda_4_d3.wav",
    "cuerda_3_g3.wav",
    "cuerda_2_b3.wav",
    "cuerda_1_e4.wav",
]


def ataques_de(nombre: str) -> list:
    ruta = AUDIO / nombre
    if not ruta.exists():
        pytest.skip(f"Falta {nombre}: ejecuta herramientas/grabar_muestras.py")
    muestras, fs = soundfile.read(ruta, dtype="float32")
    ventana = GUITARRA.tamano_ventana(fs)
    salto = int(PASO_ANALISIS * fs)
    detector = DetectorAtaques()
    ataques = []
    for indice in range(0, len(muestras) - ventana, salto):
        nivel = nivel_dbfs(muestras[indice : indice + ventana])
        ataque = detector.procesar(nivel, indice / fs)
        if ataque is not None:
            ataques.append(ataque)
    return ataques


@pytest.mark.parametrize("archivo", CUERDAS)
def test_una_cuerda_pulsada_una_vez_da_un_solo_ataque(archivo):
    """El decaimiento de una nota real no debe marcar ataques nuevos."""
    ataques = ataques_de(archivo)
    assert len(ataques) == 1, f"{len(ataques)} ataques en {archivo}: revisa el refractario"


@pytest.mark.parametrize("archivo", CUERDAS)
def test_el_ataque_cae_al_principio_de_la_grabacion(archivo):
    """La grabacion empieza con el ataque: el script espera a que suene para grabar."""
    ataques = ataques_de(archivo)
    assert ataques[0].instante < 0.5
```

- [ ] **Step 3: Ejecutar las pruebas y confirmar que se saltan limpiamente**

Run: `uv run pytest tests/test_ataques_reales.py -v -rs`
Esperado: 12 saltadas con el mensaje `Falta cuerda_X.wav`, **sin errores**. Ese es el resultado correcto mientras las grabaciones no existan.

- [ ] **Step 4: Actualizar el README**

Añade a la sección de uso una entrada del módulo de ejercicios: qué familias hay, que el fallo no avanza hasta acertar, que tras cinco intentos se resalta la nota en el mástil, y que una nota correcta pero desafinada cuenta como acierto y su desviación aparece en el informe final.

Añade a la sección de verificación del cable una entrada para la calibración de ataques:

```markdown
## Calibrar la deteccion de ataques

```bash
uv run python -m herramientas.calibrar_ataques
```

Pulsa una cuerda ocho veces separadas y la herramienta propone el salto y el
refractario que mejor cuentan tus pulsaciones. Los valores por defecto estan
elegidos a ojo; esto los ajusta a tu pua y tu pastilla.
```

Actualiza la sección de estado: la etapa 2a queda completa, y las etapas siguientes pasan a ser 2b (acordes), 3 (grabación y progreso) y 4 (tablaturas, oído y efectos).

- [ ] **Step 5: Ejecutar toda la batería**

Run: `uv run pytest -q && cd interfaz && pnpm test && pnpm build`
Esperado: todas las pruebas de Python pasan con las de audio real saltándose, y la interfaz compila.

- [ ] **Step 6: Commit**

```bash
git add herramientas/calibrar_ataques.py tests/test_ataques_reales.py README.md
git commit -m "feat: calibracion del detector de ataques y documentacion de la etapa 2a"
```

- [ ] **Step 7: Calibrar con la guitarra** *(requiere al usuario con el cable conectado)*

```bash
uv run python -m herramientas.calibrar_ataques
```

Si los valores recomendados difieren de los por defecto, actualiza `SALTO_ATAQUE_DB` y `REFRACTARIO_S` en `nucleo/ejercicios/ataques.py`, vuelve a ejecutar `uv run pytest tests/test_ataques.py` para confirmar que las pruebas sintéticas siguen pasando con los valores nuevos, y commitea el cambio.

- [ ] **Step 8: Verificación manual del ejercicio** *(requiere al usuario con el cable conectado)*

```bash
uv run guitarra
```

En el navegador, en el módulo «Ejercicios»:

1. Genera una escala de Do mayor entre los trastes 0 y 4 y compruébala contra el mástil.
2. Toca la primera nota correcta: debe avanzar, y el metrónomo debe sonar por los altavoces sin afectar a la detección.
3. Toca una nota equivocada: no debe avanzar, y debe decir qué nota sonó.
4. Falla cinco veces la misma nota: el mástil debe resaltarla.
5. Toca una nota correcta pero desafinada: debe aceptarla, y su desviación debe salir en el informe final.
6. Completa el ejercicio: el informe debe mostrar los aciertos a la primera, las notas que costaron y la desviación mediana.
7. Prueba un ejercicio de intervalos: debe sonar la nota de referencia antes de pedir la tuya.

---

## Verificación de la etapa completa

| Requisito de la spec | Dónde se cumple |
|---|---|
| Modelo común de ejercicio para las cuatro familias (§4.1) | Task 1 |
| Escalas, acordes e intervalos como patrones sobre ℤ₁₂ (§4.2) | Task 2 |
| Generador de escalas (§4) | Task 3 |
| Generador de arpegios (§4) | Task 4 |
| Generadores de intervalos y lectura (§4) | Task 5 |
| Detección de ataques con parámetros configurables (§4.3) | Task 6 |
| Detectores de ataque intercambiables (§4.3) | Task 6 |
| Regla 1: un ataque sin nota creíble no cuenta como fallo (§4.4) | Task 7 |
| Regla 2: la afinación no bloquea (§2, §4.4) | Task 7 |
| Regla 3: ayuda tras cinco intentos (§4.4) | Task 7 |
| El instante de cada ataque se registra siempre (§4.4) | Tasks 1, 7 |
| Síntesis de tonos y metrónomo (§4.5) | Task 8 |
| Quedarse sin salida degrada, no aborta (§5) | Tasks 8, 9 |
| El módulo de ejercicios junto al afinador (§3) | Task 10 |
| Configuración imposible rechazada al generar (§5) | Tasks 3, 4, 5, 10 |
| Pantalla con mástil reutilizado e informe (§4.6) | Task 11 |
| El evaluador se prueba sin audio ni hardware (§6) | Task 7 |
| Generadores probados exactamente (§6) | Tasks 3, 4, 5 |
| Detector de ataques probado con señal real (§6, §8) | Task 12 |
| La interfaz no calcula nada musical | Task 11 |
