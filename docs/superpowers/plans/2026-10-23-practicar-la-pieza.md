# Etapa 3c — Practicar la pieza: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el carril en un sitio donde se estudia una pieza: compases a la vista, bucle por rango de compases con cuenta atrás, tempo del 40 % al 100 % con click de metrónomo, informe por compases al terminar y subida automática del tempo.

**Architecture:** Un objeto nuevo del núcleo, `SesionDeEstudio`, **envuelve** al `SeguidorPieza` en vez de modificarlo: él tiene el plan de la pasada, decide el salto del bucle y acumula el informe. Al seguidor solo se le añaden dos cosas (`factor_tempo` en el constructor y `olvidar_tramo`). Un módulo aparte, `compases.py`, es el único sitio del proyecto que convierte pulsos en compases, y lo usan la rejilla, el bucle, el acento del metrónomo y el informe.

**Tech Stack:** Python 3.13.1 con uv, numpy, FastAPI, pytest. React + TypeScript con pnpm y vitest. `nucleo/sintesis.Metronomo`, que ya existe desde la etapa 2a.

**Spec:** `docs/superpowers/specs/2026-10-23-practicar-la-pieza-design.md`

## Global Constraints

- **Idioma español** en todo: comentarios, variables, funciones, clases, mensajes de error y nombres de prueba. También en TypeScript.
- **pnpm**, nunca npm. **uv** para Python; nunca `pip install`. En el sandbox hace falta `UV_CACHE_DIR="$TMPDIR/uv-cache"`, también para `ruff`.
- Preferir **numpy/scipy** sobre implementaciones manuales. Pruebas con **pytest**.
- `nucleo/` **no importa** de `servidor/` ni de `interfaz/`. `nucleo/piezas/modelo.py` **no importa** de `nucleo/ejercicios/`.
- **Ninguna prueba abre el dispositivo de audio real.** El metrónomo se inyecta, igual que en `servidor/ejercicios.py` (`SesionPractica(sesion_audio, salida=...)`).
- **Ningún archivo con derechos de autor** entra en el repositorio: las piezas de prueba se construyen en código.
- `canciones/` **no debe existir** en la raíz al terminar la suite.
- Puerto por defecto **8420**.
- Numeración: los **compases cuentan desde 1**; los **índices de nota siguen desde 0**, que es lo que ya publica `EstadoCarril`. No se mezclan.
- Límites del tempo: `FACTOR_MINIMO = 0.40`, `FACTOR_MAXIMO = 1.00`, paso del 5 %.
- Regla automática: sube 0,05 tras **dos** pasadas seguidas con **≥ 90 %** de notas medibles acertadas y a tiempo; baja 0,05 con una pasada **< 70 %**.
- Cada commit termina con:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
  ```

### La lección de la etapa 3b, que es una restricción y no un consejo

En la etapa anterior aparecieron **diez pruebas que no podían fallar**, varias nacidas de los briefs. Antes de dar una tarea por hecha: **rompe el código y di cuántas pruebas cayeron.** Una prueba nueva que no cae cuando se rompe lo que vigila no está terminada. Esto va en el informe de cada tarea.

## Review Focus

Cinco cosas que la spec implica, que ninguna tarea exploraría por su cuenta, y que le van a pasar al usuario tocando. Cada una tiene su prueba asignada a la tarea que posee el código:

1. **El bucle con una sola nota, o con un compás sin notas.** Un rango vacío no debe dividir por cero ni quedarse clavado: el reloj lo cruza y salta igual. → Tarea 5.
2. **Cambiar el tempo a mitad de pasada no debe perder lo ya tocado ni teletransportar el cabezal.** Reconstruir el seguidor en el compás en curso es la parte frágil. → Tarea 5.
3. **Una pieza cuyo último compás está incompleto** (la mayoría de las canciones de verdad): el último compás existe, se puede elegir como fin del bucle, y el informe lo cuenta con las notas que tenga. → Tarea 1 y Tarea 4.
4. **Perder la señal del cable durante el bucle**: el click se pausa y el reloj no avanza, y al volver no aparecen fallos fantasma de las notas que pasaron mientras no había audio. → Tarea 8.
5. **Una pieza entera de acordes** (un `.gp5` normal): el informe no puede dejar el ranking vacío y el botón de machacar no puede mandar al usuario a un compás que nunca podrá pasar; tiene que decir que ahí no se puede medir. → Tarea 4 y Tarea 11.

---

## Estructura de archivos

**Se crean:**

| Archivo | Responsabilidad |
|---|---|
| `nucleo/piezas/compases.py` | Pulsos ↔ compases. El único sitio que lo hace. |
| `nucleo/piezas/estudio.py` | `PlanDePasada`, `SesionDeEstudio`, `EstadoEstudio`, el informe y el historial. |
| `tests/test_compases.py` | Tarea 1. |
| `tests/test_estudio.py` | Tareas 3, 4, 5, 6. |
| `tests/test_app_estudio.py` | Tareas 7 y 8. |
| `interfaz/src/tiposEstudio.ts` | Espejo de `EstadoEstudio` y del informe. |
| `interfaz/src/RejillaCompases.tsx` | La rejilla: dibujo, clic y arrastre. |
| `interfaz/src/ControlesEstudio.tsx` | Tempo, bucle, click, automático, pausa, secciones. |
| `interfaz/src/InformePasada.tsx` | La tabla por compases y los botones de machacar. |
| `interfaz/src/RejillaCompases.test.tsx`, `ControlesEstudio.test.tsx`, `InformePasada.test.tsx` | Tareas 9, 10, 11. |

**Se modifican:**

| Archivo | Qué cambia |
|---|---|
| `nucleo/piezas/seguimiento.py` | `factor_tempo` al final del constructor; `olvidar_tramo`. |
| `nucleo/piezas/modelo.py` | Solo la frase que promete que las casillas son la etapa 3c (Tarea 12). |
| `servidor/piezas.py` | `SesionCarril` pasa a sostener una `SesionDeEstudio` y el metrónomo. |
| `servidor/app.py` | `plan` en `iniciar`; `plan`, `saltar`, `pausa`, `informe`, `pieza`. |
| `interfaz/src/tiposPieza.ts` | Los cinco campos que le faltan. |
| `interfaz/src/useCarril.ts` | Campos nuevos del estado, `tempo_efectivo`, `detener` al desmontar. |
| `interfaz/src/Carril.tsx` | Monta rejilla, controles e informe; usa `tempo_efectivo`; pide la pieza al montar. |
| `interfaz/src/Ejercicios.tsx` | `detener` al desmontar. |
| `README.md` | La etapa 3c (Tarea 12). |

## El contrato del tiempo, que todas las tareas comparten

Hay que tenerlo claro antes de la Tarea 2 o nada encaja:

- El `SeguidorPieza` trabaja en **segundos de la pasada**: con `factor_tempo=0.5`, una pieza de 10 s escritos dura 20 s de pasada. Lo consigue dividiendo **todas** sus conversiones por el factor, y multiplicando sus **tres** ventanas por `1/factor`.
- Lo que viaja a la interfaz para dibujar es `tempo_efectivo = pieza.tempo * factor` (un `float`). La interfaz ya convierte pulsos a segundos con `pieza.tempo` en dos sitios (`Carril.tsx:180-181`); pasarle el efectivo hace que las notas viajen más despacio y cuadren con el reloj, sin tocar la geometría.
- Lo que viaja para **situarse** (compás en curso, rejilla, informe) es `instante_pulsos`, que no depende del tempo. `segundos_a_pulsos` ya existe en `nucleo/piezas/modelo.py`.
- `pulsos_a_segundos(pulsos, tempo)` **valida el tempo** y lo quiere entero. Nunca se le pasa un tempo multiplicado por el factor: el factor se aplica **dividiendo el resultado**.

---

### Task 1: `compases.py`, el único que sabe de compases

**Files:**
- Create: `nucleo/piezas/compases.py`
- Test: `tests/test_compases.py`

**Interfaces:**
- Consumes: `nucleo.piezas.modelo.Pieza` (campos `compas: tuple[int, int]`, `notas`, `secciones`, `duracion_pulsos`).
- Produces:
  ```python
  def pulsos_por_compas(pieza: Pieza) -> float
  def total_de_compases(pieza: Pieza) -> int
  def compas_en(pieza: Pieza, pulsos: float) -> int
  def pulsos_del_compas(pieza: Pieza, numero: int) -> tuple[float, float]
  def compases_de_la_seccion(pieza: Pieza, indice: int) -> tuple[int, int]
  ```

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `tests/test_compases.py`:

```python
"""Pulsos a compases: el unico sitio del proyecto que hace esta cuenta."""

import pytest

from nucleo.piezas.compases import (
    compas_en,
    compases_de_la_seccion,
    pulsos_del_compas,
    pulsos_por_compas,
    total_de_compases,
)
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion


def pieza_de(inicios, compas=(4, 4), secciones=()):
    """Una pieza con una nota de un pulso en cada inicio dado."""
    notas = tuple(
        NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i in inicios
    )
    return Pieza(
        nombre="p",
        perfil="guitarra_estandar",
        tempo=60,
        compas=compas,
        notas=notas,
        secciones=secciones,
    )


def test_en_cuatro_por_cuatro_el_compas_tiene_cuatro_pulsos():
    assert pulsos_por_compas(pieza_de([0])) == 4.0


def test_en_siete_por_ocho_el_pulso_es_la_corchea():
    # El tempo esta en pulsos por minuto y el pulso lo define el denominador:
    # en 7/8 el compas son siete corcheas, no siete negras.
    assert pulsos_por_compas(pieza_de([0], compas=(7, 8))) == 3.5


def test_el_primer_compas_es_el_uno():
    pieza = pieza_de([0.0, 3.9])
    assert compas_en(pieza, 0.0) == 1
    assert compas_en(pieza, 3.9) == 1


def test_el_pulso_cuatro_ya_es_el_segundo_compas():
    assert compas_en(pieza_de([0.0, 4.0]), 4.0) == 2


def test_una_pieza_sin_notas_no_tiene_compases_y_el_cabezal_esta_en_el_uno():
    vacia = pieza_de([])
    assert total_de_compases(vacia) == 0
    assert compas_en(vacia, 0.0) == 1


def test_el_ultimo_compas_incompleto_cuenta_como_compas():
    # Nueve pulsos de musica en 4/4 son tres compases: el tercero tiene una
    # negra y tres silencios, y sigue siendo el compas 3. Es el caso de casi
    # cualquier cancion de verdad.
    pieza = pieza_de([0.0, 4.0, 8.0])
    assert total_de_compases(pieza) == 3
    assert compas_en(pieza, 8.5) == 3


def test_los_pulsos_del_compas_son_un_intervalo_medio_abierto():
    assert pulsos_del_compas(pieza_de([0.0, 4.0]), 2) == (4.0, 8.0)


def test_un_compas_que_no_existe_se_rechaza_con_su_numero():
    pieza = pieza_de([0.0])
    with pytest.raises(ValueError, match="compas 7"):
        pulsos_del_compas(pieza, 7)
    with pytest.raises(ValueError, match="compas 0"):
        pulsos_del_compas(pieza, 0)


def test_una_seccion_acaba_donde_empieza_la_siguiente():
    pieza = pieza_de(
        [0.0, 4.0, 8.0, 12.0],
        secciones=(Seccion(nombre="Intro", inicio_pulsos=0.0),
                   Seccion(nombre="Estribillo", inicio_pulsos=8.0)),
    )
    assert compases_de_la_seccion(pieza, 0) == (1, 2)


def test_la_ultima_seccion_acaba_al_final_de_la_pieza():
    pieza = pieza_de(
        [0.0, 4.0, 8.0, 12.0],
        secciones=(Seccion(nombre="Intro", inicio_pulsos=0.0),
                   Seccion(nombre="Estribillo", inicio_pulsos=8.0)),
    )
    assert compases_de_la_seccion(pieza, 1) == (3, 4)


def test_dos_secciones_con_el_mismo_nombre_se_distinguen_por_indice():
    # Por esto la seccion se pide por INDICE y no por nombre: una cancion con
    # dos estribillos trae dos secciones llamadas igual, y elegir una de las dos
    # en silencio es la clase de empate que costo un Critical en la etapa 3b.
    pieza = pieza_de(
        [0.0, 4.0, 8.0, 12.0],
        secciones=(Seccion(nombre="Estribillo", inicio_pulsos=0.0),
                   Seccion(nombre="Estribillo", inicio_pulsos=8.0)),
    )
    assert compases_de_la_seccion(pieza, 0) == (1, 2)
    assert compases_de_la_seccion(pieza, 1) == (3, 4)


def test_una_seccion_que_no_existe_se_rechaza():
    with pytest.raises(ValueError, match="seccion 2"):
        compases_de_la_seccion(pieza_de([0.0]), 2)
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_compases.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nucleo.piezas.compases'`

- [ ] **Step 3: Escribe el módulo**

Crea `nucleo/piezas/compases.py`:

```python
"""Pulsos a compases, y al reves. El unico sitio del proyecto que hace esta cuenta.

Lo necesitan cuatro cosas a la vez -la rejilla de la interfaz, el rango del
bucle, el acento del metronomo y el informe por compases-, y una cuenta repetida
en cuatro sitios es una cuenta que se arregla en tres.

LIMITE DECLARADO: `Pieza` guarda UN SOLO compas, el del principio, porque los
lectores de la etapa 3b se quedaron con el primero y avisan con
`Pieza.compas_variable`. Con un 3/4 en medio de un 4/4, las barras caen mal desde
el cambio hasta el final. Este modulo NO lo arregla -haria falta guardar los
cambios en el modelo, que es tocar los cuatro lectores-: quien dibuje encima
tiene que mostrar ese aviso. Fingir precision aqui seria peor que no tener
rejilla.
"""

from nucleo.piezas.modelo import Pieza


def pulsos_por_compas(pieza: Pieza) -> float:
    """Cuantos pulsos ocupa un compas de esta pieza.

    El pulso lo define el DENOMINADOR del compas, no un 4 fijo: `Pieza.tempo`
    esta en pulsos por minuto, y en 7/8 el pulso es la corchea, asi que el compas
    son 7 corcheas = 3,5 negras. Devolver 7 aqui pondria las barras al doble de
    distancia de donde van.
    """
    numerador, denominador = pieza.compas
    return numerador * 4.0 / denominador


def total_de_compases(pieza: Pieza) -> int:
    """Cuantos compases ocupa la pieza, contando desde 1.

    El ultimo compas incompleto CUENTA: nueve pulsos en 4/4 son tres compases, y
    el tercero es un compas de verdad con una negra y tres silencios. Casi
    cualquier cancion de verdad acaba asi.
    """
    if len(pieza) == 0:
        return 0
    import math

    return max(1, math.ceil(pieza.duracion_pulsos / pulsos_por_compas(pieza)))


def compas_en(pieza: Pieza, pulsos: float) -> int:
    """En que compas cae ese pulso. El primero es el 1, como cuentan los musicos.

    En una pieza sin notas devuelve 1: no hay compas donde caer, y 1 es el unico
    numero que no miente sobre el sitio del cabezal.
    """
    if pulsos <= 0:
        return 1
    return int(pulsos // pulsos_por_compas(pieza)) + 1


def pulsos_del_compas(pieza: Pieza, numero: int) -> tuple[float, float]:
    """[inicio, fin) en pulsos del compas `numero`.

    Medio abierto a proposito: el pulso 4 en 4/4 es el primero del compas 2, no el
    ultimo del 1, y asi dos compases consecutivos no se solapan en una nota.
    """
    total = total_de_compases(pieza)
    if numero < 1 or numero > total:
        raise ValueError(
            f"La pieza '{pieza.nombre}' no tiene compas {numero}: "
            f"va del 1 al {total}"
        )
    ancho = pulsos_por_compas(pieza)
    return ((numero - 1) * ancho, numero * ancho)


def compases_de_la_seccion(pieza: Pieza, indice: int) -> tuple[int, int]:
    """Primer y ultimo compas de la seccion `indice`, para armar el bucle con ella.

    Se pide por INDICE y no por nombre: `Seccion` solo guarda `nombre` e
    `inicio_pulsos`, y los nombres se repiten -una cancion con dos estribillos
    trae dos secciones llamadas "Estribillo"-, asi que pedirla por nombre
    obligaria a elegir una de las dos en silencio.

    Y como `Seccion` NO guarda donde acaba, el ultimo compas de una seccion es el
    anterior al comienzo de la siguiente, o el ultimo de la pieza si es la ultima.
    """
    if indice < 0 or indice >= len(pieza.secciones):
        raise ValueError(
            f"La pieza '{pieza.nombre}' no tiene seccion {indice}: "
            f"tiene {len(pieza.secciones)}"
        )
    primero = compas_en(pieza, pieza.secciones[indice].inicio_pulsos)
    if indice + 1 < len(pieza.secciones):
        siguiente = pieza.secciones[indice + 1].inicio_pulsos
        ultimo = max(primero, compas_en(pieza, siguiente) - 1)
    else:
        ultimo = max(primero, total_de_compases(pieza))
    return (primero, ultimo)
```

Sube `import math` al principio del archivo, con el resto de los imports.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_compases.py -q`
Expected: PASS, 12 pruebas.

- [ ] **Step 5: Rompe el código y cuenta**

Cambia `+ 1` por `+ 0` en `compas_en` y corre las pruebas: tienen que caer varias. Cambia `4.0 / denominador` por `1.0` y corre: tiene que caer la de 7/8. Devuelve los dos cambios. **Apunta en el informe cuántas cayeron con cada rotura**; si alguna rotura no tira ninguna prueba, falta una prueba.

- [ ] **Step 6: Commit**

```bash
git add nucleo/piezas/compases.py tests/test_compases.py
git commit -m "$(cat <<'FIN'
feat: pulsos a compases, en un solo sitio

El pulso lo define el denominador (7/8 son 3,5 negras), el ultimo compas
incompleto cuenta, y la seccion se pide por indice porque los nombres se
repiten.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 2: el seguidor gana `factor_tempo` y `olvidar_tramo`

**Files:**
- Modify: `nucleo/piezas/seguimiento.py` (el `__init__` y un método nuevo)
- Test: `tests/test_seguimiento_pieza.py` (se añade al final)

**Interfaces:**
- Consumes: nada nuevo.
- Produces:
  ```python
  SeguidorPieza(
      pieza, detector=None,
      ventana_a_tiempo_s=VENTANA_A_TIEMPO_S,
      ventana_reclamo_minima_s=VENTANA_RECLAMO_MINIMA_S,
      ventana_altura_s=VENTANA_ALTURA_S,
      factor_tempo: float = 1.0,          # el ultimo: los cinco de antes no se mueven
  )
  seguidor.factor_tempo -> float
  seguidor.olvidar_tramo(desde_s: float, hasta_s: float) -> None
  ```

**Por qué `factor_tempo` va al final:** `tests/test_seguimiento_pieza.py` ya llama al constructor con argumentos posicionales y de palabra clave. Meterlo antes de las ventanas, o volverlas de solo palabra clave con un `*`, rompería esas llamadas. Un argumento nuevo no reordena los viejos.

- [ ] **Step 1: Escribe las pruebas que fallan**

Añade al final de `tests/test_seguimiento_pieza.py`:

```python
def test_el_factor_estira_los_instantes_de_la_pieza():
    # Al 50 %, una pieza de tres notas a 60 ppm dura el doble: la nota 2 ya no
    # empieza en el segundo 1 sino en el 2.
    seguidor = SeguidorPieza(pieza_de([40, 45, 50]), factor_tempo=0.5)
    seguidor.avanzar_a(1.5)
    assert seguidor.estado.indice_actual == 0
    seguidor.avanzar_a(2.5)
    assert seguidor.estado.indice_actual == 1


def test_el_factor_estira_las_tres_ventanas():
    seguidor = SeguidorPieza(pieza_de([40]), factor_tempo=0.5)
    assert seguidor.ventana_a_tiempo_s == pytest.approx(VENTANA_A_TIEMPO_S * 2)
    assert seguidor.ventana_reclamo_minima_s == pytest.approx(VENTANA_RECLAMO_MINIMA_S * 2)
    assert seguidor.ventana_altura_s == pytest.approx(VENTANA_ALTURA_S * 2)


def test_al_cincuenta_por_ciento_un_desfase_de_ciento_veinte_milisegundos_es_a_tiempo():
    # La decision del usuario: la ventana escala con el tempo, asi que lo que se
    # juzga es la colocacion DENTRO del compas. A tempo escrito, 120 ms es tarde;
    # a la mitad, los +-80 ms se vuelven +-160 y el mismo retraso es a tiempo.
    rapido = SeguidorPieza(pieza_de([40]))
    assert tocar(rapido, "E2", en=0.120).clasificacion == "tarde"
    lento = SeguidorPieza(pieza_de([40]), factor_tempo=0.5)
    assert tocar(lento, "E2", en=0.120).clasificacion == "a_tiempo"


def test_un_factor_que_no_es_positivo_se_rechaza():
    with pytest.raises(ValueError, match="factor"):
        SeguidorPieza(pieza_de([40]), factor_tempo=0.0)


def test_olvidar_un_tramo_deja_volver_a_cobrar_sus_notas():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocar(seguidor, "E2", en=0.0)
    assert len(seguidor.estado.tocadas) == 1
    seguidor.olvidar_tramo(0.0, 0.5)
    assert seguidor.estado.tocadas == ()
    # Y se puede volver a cobrar: es lo que hace falta para repetir el bucle.
    seguidor.avanzar_a(0.0)
    tocar(seguidor, "E2", en=0.0)
    assert len(seguidor.estado.tocadas) == 1


def test_olvidar_un_tramo_no_toca_lo_de_fuera():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocar(seguidor, "E2", en=0.0)
    tocar(seguidor, "A2", en=1.0)
    seguidor.olvidar_tramo(0.9, 1.5)
    assert [t.indice for t in seguidor.estado.tocadas] == [0]


def test_olvidar_un_tramo_vacio_no_hace_nada():
    seguidor = SeguidorPieza(pieza_de([40, 45]))
    tocar(seguidor, "E2", en=0.0)
    seguidor.olvidar_tramo(5.0, 9.0)
    assert len(seguidor.estado.tocadas) == 1
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_seguimiento_pieza.py -q -k "factor or olvidar"`
Expected: FAIL — `TypeError: unexpected keyword argument 'factor_tempo'` y `AttributeError: olvidar_tramo`.

- [ ] **Step 3: Implementa**

En `nucleo/piezas/seguimiento.py`, añade `factor_tempo` **al final** de la lista de parámetros del `__init__` y, justo después de guardar las ventanas, aplica el factor. El patrón: una función local que convierte pulsos a **segundos de la pasada**, usada en los dos sitios que hoy llaman a `pulsos_a_segundos`.

```python
        factor_tempo: float = 1.0,
    ) -> None:
        if factor_tempo <= 0:
            raise ValueError(
                f"El factor de tempo es {factor_tempo}: tiene que ser mayor que cero"
            )
        self.pieza = pieza
        self._detector = detector or DetectorPulsaciones()
        self.factor_tempo = float(factor_tempo)
        # Las tres ventanas se ESTIRAN con el factor, y es una decision de la
        # etapa 3c, no un efecto secundario: practicando al 50 % lo que se juzga
        # es la colocacion dentro del compas, con la misma indulgencia a
        # cualquier velocidad, y al subir el tempo la ventana se cierra sola. Las
        # constantes siguen siendo la referencia AL TEMPO ESCRITO.
        self.ventana_a_tiempo_s = ventana_a_tiempo_s / self.factor_tempo
        self.ventana_reclamo_minima_s = ventana_reclamo_minima_s / self.factor_tempo
        self.ventana_altura_s = ventana_altura_s / self.factor_tempo

        def segundos(pulsos: float) -> float:
            """Pulsos a segundos DE LA PASADA: el factor estira el reloj entero.

            El factor divide el resultado y NO multiplica el tempo: `tempo` es un
            entero validado por `pulsos_a_segundos`, y 0,7 x 100 no es un tempo.
            """
            return pulsos_a_segundos(pulsos, pieza.tempo) / self.factor_tempo
```

Después, sustituye las tres conversiones que ya existen por `segundos(...)`:

- `self._inicios_s`: `[segundos(nota.inicio_pulsos) for nota in pieza.notas]`
- `self._ventanas_reclamo_s`: `segundos(nota.duracion_pulsos) + self.ventana_a_tiempo_s`, y el piso pasa a ser `self.ventana_reclamo_minima_s`
- `self._ventana_reclamo_pronto_s = max(self.ventana_a_tiempo_s, self.ventana_reclamo_minima_s)`
- `self._duracion_s = pieza.duracion_s / self.factor_tempo`

Dentro de la clase, los usos de `ventana_altura_s` pasan de la variable local al atributo `self.ventana_altura_s` si no lo eran ya.

Y el método nuevo, junto a `reiniciar`:

```python
    def olvidar_tramo(self, desde_s: float, hasta_s: float) -> None:
        """Deja sin cobrar las notas de [desde_s, hasta_s) y borra sus anotaciones.

        Es lo que permite REPETIR: al volver al principio del bucle, las notas de
        ese tramo tienen que poder cobrarse otra vez o la segunda pasada saldria
        entera en blanco.

        Los instantes son del reloj de la PASADA, los mismos que `avanzar_a`.

        No toca el reloj ni el detector: quien repite llama ademas a `avanzar_a`,
        que es lo que invalida la correspondencia con el reloj del analisis y
        descarta las pulsaciones en vuelo del tramo que se abandona. Las dos
        cosas van juntas y en ese orden.
        """
        with self._candado:
            dentro = (self._inicios_s >= desde_s) & (self._inicios_s < hasta_s)
            self._cobradas[dentro] = False
            indices = set(np.flatnonzero(dentro).tolist())
            self._tocadas = [t for t in self._tocadas if t.indice not in indices]
```

- [ ] **Step 4: Comprueba que pasan, y que no se rompió nada**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_seguimiento_pieza.py -q`
Expected: PASS, todas las de antes más las siete nuevas.

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS. Si algo del servidor o de las piezas cae aquí, es que una conversión quedó sin dividir.

- [ ] **Step 5: Rompe el código y cuenta**

Quita el `/ self.factor_tempo` de `ventana_a_tiempo_s` y corre: tiene que caer la de los 120 ms. Cambia `>= desde_s` por `> desde_s` en `olvidar_tramo` y corre: tiene que caer la de volver a cobrar. Devuelve los dos cambios y **apunta las cifras**.

- [ ] **Step 6: Commit**

```bash
git add nucleo/piezas/seguimiento.py tests/test_seguimiento_pieza.py
git commit -m "$(cat <<'FIN'
feat: el seguidor acepta un factor de tempo y sabe olvidar un tramo

El factor estira los instantes y las TRES ventanas: al 50 %, los +-80 ms se
vuelven +-160, que es la decision del usuario sobre practicar lento. Va al
final de la firma para no reordenar los cinco argumentos que ya tenia.

olvidar_tramo es lo que permitira repetir el bucle sin que la segunda pasada
salga en blanco.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 3: `PlanDePasada` y `SesionDeEstudio` sin bucle todavía

**Files:**
- Create: `nucleo/piezas/estudio.py`
- Test: `tests/test_estudio.py`

**Interfaces:**
- Consumes: `compases.py` (Tarea 1); `SeguidorPieza(..., factor_tempo=...)` (Tarea 2); `nucleo.piezas.modelo.{Pieza, pulsos_a_segundos, segundos_a_pulsos}`; `nucleo.piezas.seguimiento.{EstadoCarril, NotaTocada, DetectorPulsaciones}`.
- Produces:
  ```python
  FACTOR_MINIMO = 0.40
  FACTOR_MAXIMO = 1.00
  PASO_DEL_FACTOR = 0.05

  @dataclass(frozen=True)
  class PlanDePasada:
      primer_compas: int = 1
      ultimo_compas: int | None = None
      factor_tempo: float = 1.0
      en_bucle: bool = False
      compases_de_cuenta_atras: int = 1
      con_click: bool = False
      tempo_automatico: bool = False

  @dataclass(frozen=True)
  class EstadoEstudio:
      carril: EstadoCarril
      instante_pulsos: float
      compas_en_curso: int
      total_de_compases: int
      primer_compas: int
      ultimo_compas: int
      repeticion: int
      cuenta_atras_restante_s: float
      factor_tempo: float
      tempo_efectivo: float
      en_bucle: bool
      en_pausa: bool
      compas_variable: bool
      ritmo_aproximado: bool
      def a_dict(self) -> dict   # el dict del carril MAS estos campos, al mismo nivel

  def validar_plan(pieza: Pieza, plan: PlanDePasada) -> PlanDePasada  # devuelve el plan con ultimo_compas resuelto

  class SesionDeEstudio:
      def __init__(self, pieza, plan=PlanDePasada(), detector=None)
      @property
      def estado(self) -> EstadoEstudio
      @property
      def plan(self) -> PlanDePasada
      def avanzar_a(self, instante_pasada_s: float) -> EstadoEstudio
      def procesar(self, resultado, instante_analisis: float) -> EstadoEstudio
  ```

**El contrato del tiempo** (está en la cabecera del plan, y esta tarea lo fija): el reloj de la pasada **es** el del seguidor, ya estirado por el factor. `instante_pulsos` se saca de vuelta con `segundos_a_pulsos(instante_s * factor, pieza.tempo)`, y es lo que no depende del tempo. `tempo_efectivo = pieza.tempo * factor` es un `float` y solo viaja a la interfaz: nunca entra en `pulsos_a_segundos`.

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `tests/test_estudio.py`:

```python
"""La sesion de estudio: el plan, el reloj de la pasada y lo que ve la interfaz.

Ni una espera real: el reloj se mueve a mano con `avanzar_a`, igual que en
`tests/test_seguimiento_pieza.py`.
"""

import pytest

from nucleo.piezas.estudio import (
    FACTOR_MAXIMO,
    FACTOR_MINIMO,
    EstadoEstudio,
    PlanDePasada,
    SesionDeEstudio,
    validar_plan,
)
from nucleo.piezas.modelo import NotaEnPieza, Pieza, Seccion


def pieza_de(inicios, tempo=60, compas=(4, 4), **extra):
    """Una nota de un pulso en cada inicio. A 60 ppm, un pulso es un segundo."""
    notas = tuple(
        NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=float(i), duracion_pulsos=1.0)
        for i in inicios
    )
    return Pieza(
        nombre="p", perfil="guitarra_estandar", tempo=tempo, compas=compas,
        notas=notas, **extra,
    )


def pieza_de_doce_compases():
    """Doce compases de 4/4 con una nota al principio de cada uno."""
    return pieza_de([i * 4 for i in range(12)])


def test_el_plan_por_defecto_es_la_pieza_entera_a_tempo_escrito():
    plan = PlanDePasada()
    assert plan.primer_compas == 1
    assert plan.ultimo_compas is None
    assert plan.factor_tempo == 1.0
    assert plan.en_bucle is False
    assert plan.con_click is False
    assert plan.tempo_automatico is False


def test_el_plan_sin_ultimo_compas_se_resuelve_al_ultimo_de_la_pieza():
    resuelto = validar_plan(pieza_de_doce_compases(), PlanDePasada())
    assert resuelto.ultimo_compas == 12


def test_un_factor_por_debajo_del_suelo_se_rechaza():
    with pytest.raises(ValueError, match="40"):
        PlanDePasada(factor_tempo=0.2)


def test_un_factor_por_encima_del_tempo_escrito_se_rechaza():
    with pytest.raises(ValueError, match="100"):
        PlanDePasada(factor_tempo=1.5)


def test_el_ultimo_compas_antes_del_primero_se_rechaza():
    with pytest.raises(ValueError, match="compas"):
        PlanDePasada(primer_compas=8, ultimo_compas=3)


def test_un_compas_fuera_de_la_pieza_se_rechaza_con_los_dos_numeros():
    pieza = pieza_de_doce_compases()
    with pytest.raises(ValueError, match="20"):
        validar_plan(pieza, PlanDePasada(primer_compas=20))
    with pytest.raises(ValueError, match="99"):
        validar_plan(pieza, PlanDePasada(ultimo_compas=99))


def test_la_pasada_arranca_al_principio_del_primer_compas_del_plan():
    # El compas 5 de una pieza de 4/4 a 60 ppm empieza en el pulso 16, es decir
    # en el segundo 16.
    sesion = SesionDeEstudio(pieza_de_doce_compases(), PlanDePasada(primer_compas=5))
    assert sesion.estado.carril.instante_s == pytest.approx(16.0)
    assert sesion.estado.compas_en_curso == 5


def test_el_estado_dice_en_que_compas_va_el_cabezal():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.avanzar_a(9.0)
    assert sesion.estado.compas_en_curso == 3
    assert sesion.estado.instante_pulsos == pytest.approx(9.0)


def test_al_cincuenta_por_ciento_el_mismo_compas_llega_al_doble_de_segundos():
    sesion = SesionDeEstudio(pieza_de_doce_compases(), PlanDePasada(factor_tempo=0.5))
    sesion.avanzar_a(9.0)
    # Nueve segundos de pasada son 4,5 pulsos de la pieza: todavia el compas 2.
    assert sesion.estado.compas_en_curso == 2
    assert sesion.estado.instante_pulsos == pytest.approx(4.5)


def test_el_tempo_efectivo_es_lo_que_la_interfaz_usa_para_dibujar():
    sesion = SesionDeEstudio(pieza_de([0.0], tempo=120), PlanDePasada(factor_tempo=0.5))
    assert sesion.estado.tempo_efectivo == pytest.approx(60.0)


def test_el_estado_arrastra_los_avisos_de_la_pieza():
    pieza = pieza_de([0.0], ritmo_aproximado=True, compas_variable=True)
    estado = SesionDeEstudio(pieza).estado
    assert estado.ritmo_aproximado is True
    assert estado.compas_variable is True


def test_el_dict_del_estado_lleva_lo_del_carril_al_mismo_nivel():
    # La interfaz de la etapa 3a ya lee `instante_s`, `indice_actual`, `total`,
    # `completado` y `tocadas` del paquete del WebSocket: si esta etapa los
    # anidara dentro de "carril", habria que tocar `useCarril` sin ningun motivo.
    datos = SesionDeEstudio(pieza_de_doce_compases()).estado.a_dict()
    for clave in ("instante_s", "indice_actual", "total", "completado", "tocadas"):
        assert clave in datos
    assert datos["compas_en_curso"] == 1
    assert datos["total_de_compases"] == 12


def test_una_pieza_sin_notas_no_rompe_la_sesion():
    estado = SesionDeEstudio(pieza_de([])).estado
    assert estado.total_de_compases == 0
    assert estado.compas_en_curso == 1
    assert estado.ultimo_compas == 0
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nucleo.piezas.estudio'`

- [ ] **Step 3: Escribe el módulo**

Crea `nucleo/piezas/estudio.py`:

```python
"""Estudiar una pieza: el plan de la pasada, el bucle y el informe.

Este objeto ENVUELVE al `SeguidorPieza` en vez de modificarlo, y la razon esta
escrita en la spec: el seguidor tiene dos relojes y una adjudicacion de
pulsaciones que costo mucho dejar correcta, y meterle un tercer reloj seria tocar
justo lo que no conviene tocar. Aqui vive todo lo que la etapa 3c anade; alli solo
llegaron `factor_tempo` y `olvidar_tramo`.

EL RELOJ DE LA PASADA ES EL DEL SEGUIDOR, ya estirado por el factor: con
`factor_tempo=0.5` una pieza de 10 s escritos dura 20 s de pasada. Lo que no
depende del tempo es `instante_pulsos`, y es lo que usan los compases.

NO ABRE AUDIO. El click lo pone el servidor, igual que con los ejercicios: aqui
solo se publica `repeticion`, y el servidor rearranca el metronomo cuando ese
numero cambia. Un contador es un dato; un `Metronomo` seria una dependencia del
nucleo con el dispositivo de sonido, y esta clase tiene que poder probarse entera
en silencio.
"""

from dataclasses import dataclass, replace

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.pulsaciones import DetectorPulsaciones
from nucleo.piezas.compases import (
    compas_en,
    pulsos_del_compas,
    pulsos_por_compas,
    total_de_compases,
)
from nucleo.piezas.modelo import Pieza, pulsos_a_segundos, segundos_a_pulsos
from nucleo.piezas.seguimiento import EstadoCarril, SeguidorPieza

# Mas abajo del 40 % el carril ya no se parece a musica; por encima del 100 % se
# estaria practicando mas rapido que el original, que es otra cosa y no se
# construye aqui. El paso es el del deslizador de la interfaz.
FACTOR_MINIMO = 0.40
FACTOR_MAXIMO = 1.00
PASO_DEL_FACTOR = 0.05


@dataclass(frozen=True)
class PlanDePasada:
    """Como se toca esta vez. No cambia la pieza: cambia la pasada.

    Los valores por defecto son el comportamiento de la etapa 3a -pieza entera,
    tempo escrito, sin bucle, sin click-, asi que las piezas que vienen de los
    generadores de ejercicios no cambian en nada.

    `ultimo_compas` a None es "hasta el final": no se puede poner el numero aqui
    porque el plan se construye sin ver la pieza. Lo resuelve `validar_plan`.
    """

    primer_compas: int = 1
    ultimo_compas: int | None = None
    factor_tempo: float = 1.0
    en_bucle: bool = False
    compases_de_cuenta_atras: int = 1
    con_click: bool = False
    tempo_automatico: bool = False

    def __post_init__(self) -> None:
        if not FACTOR_MINIMO <= self.factor_tempo <= FACTOR_MAXIMO:
            raise ValueError(
                f"El tempo tiene que estar entre el {FACTOR_MINIMO:.0%} y el "
                f"{FACTOR_MAXIMO:.0%} del escrito, y pediste "
                f"{self.factor_tempo:.0%}"
            )
        if self.primer_compas < 1:
            raise ValueError(
                f"El primer compas es el 1, y pediste {self.primer_compas}"
            )
        if self.ultimo_compas is not None and self.ultimo_compas < self.primer_compas:
            raise ValueError(
                f"El ultimo compas ({self.ultimo_compas}) no puede ir antes del "
                f"primero ({self.primer_compas})"
            )
        if self.compases_de_cuenta_atras < 0:
            raise ValueError(
                "Los compases de cuenta atras no pueden ser negativos, y pediste "
                f"{self.compases_de_cuenta_atras}"
            )

    def a_dict(self) -> dict:
        return {
            "primer_compas": self.primer_compas,
            "ultimo_compas": self.ultimo_compas,
            "factor_tempo": self.factor_tempo,
            "en_bucle": self.en_bucle,
            "compases_de_cuenta_atras": self.compases_de_cuenta_atras,
            "con_click": self.con_click,
            "tempo_automatico": self.tempo_automatico,
        }


def validar_plan(pieza: Pieza, plan: PlanDePasada) -> PlanDePasada:
    """Comprueba el plan CONTRA la pieza y devuelve `ultimo_compas` resuelto.

    `PlanDePasada` valida lo que puede sin ver la pieza (el factor, el orden de
    los compases); lo que solo se sabe con la pieza delante -si el compas 20
    existe- se valida aqui. El mensaje nombra el compas pedido y el ultimo que
    hay, que es lo unico que le permite al usuario arreglarlo.
    """
    total = total_de_compases(pieza)
    if total == 0:
        return replace(plan, ultimo_compas=0)
    if plan.primer_compas > total:
        raise ValueError(
            f"La pieza '{pieza.nombre}' tiene {total} compases y pediste empezar "
            f"en el {plan.primer_compas}"
        )
    ultimo = total if plan.ultimo_compas is None else plan.ultimo_compas
    if ultimo > total:
        raise ValueError(
            f"La pieza '{pieza.nombre}' tiene {total} compases y pediste acabar "
            f"en el {ultimo}"
        )
    return replace(plan, ultimo_compas=ultimo)


@dataclass(frozen=True)
class EstadoEstudio:
    """Lo que la interfaz necesita: el estado del carril mas el de la pasada.

    `a_dict` publica los campos del carril AL MISMO NIVEL y no anidados: la
    interfaz de la etapa 3a ya lee `instante_s`, `indice_actual`, `total`,
    `completado` y `tocadas` del paquete del WebSocket, y anidarlos obligaria a
    tocar `useCarril.ts` sin ningun motivo.
    """

    carril: EstadoCarril
    instante_pulsos: float
    compas_en_curso: int
    total_de_compases: int
    primer_compas: int
    ultimo_compas: int
    repeticion: int
    cuenta_atras_restante_s: float
    factor_tempo: float
    tempo_efectivo: float
    en_bucle: bool
    en_pausa: bool
    compas_variable: bool
    ritmo_aproximado: bool

    def a_dict(self) -> dict:
        return {
            **self.carril.a_dict(),
            "instante_pulsos": round(self.instante_pulsos, 3),
            "compas_en_curso": self.compas_en_curso,
            "total_de_compases": self.total_de_compases,
            "primer_compas": self.primer_compas,
            "ultimo_compas": self.ultimo_compas,
            "repeticion": self.repeticion,
            "cuenta_atras_restante_s": round(self.cuenta_atras_restante_s, 3),
            "factor_tempo": self.factor_tempo,
            "tempo_efectivo": round(self.tempo_efectivo, 2),
            "en_bucle": self.en_bucle,
            "en_pausa": self.en_pausa,
            "compas_variable": self.compas_variable,
            "ritmo_aproximado": self.ritmo_aproximado,
        }


class SesionDeEstudio:
    """Un seguidor, un plan, y el informe de lo que va pasando."""

    def __init__(
        self,
        pieza: Pieza,
        plan: PlanDePasada = PlanDePasada(),
        detector: DetectorPulsaciones | None = None,
    ) -> None:
        self.pieza = pieza
        self._plan = validar_plan(pieza, plan)
        self._detector = detector
        self._repeticion = 1
        self._en_pausa = False
        self._cuenta_atras_restante_s = 0.0
        self._seguidor = self._nuevo_seguidor()
        self._seguidor.avanzar_a(self._inicio_s())

    # -- construccion y conversiones -------------------------------------

    def _nuevo_seguidor(self) -> SeguidorPieza:
        return SeguidorPieza(
            self.pieza, self._detector, factor_tempo=self._plan.factor_tempo
        )

    def _segundos(self, pulsos: float) -> float:
        """Pulsos de la pieza a segundos DE LA PASADA."""
        return pulsos_a_segundos(pulsos, self.pieza.tempo) / self._plan.factor_tempo

    def _pulsos(self, segundos_de_pasada: float) -> float:
        return segundos_a_pulsos(
            segundos_de_pasada * self._plan.factor_tempo, self.pieza.tempo
        )

    def _inicio_s(self) -> float:
        """Donde empieza el tramo del plan, en segundos de la pasada."""
        if total_de_compases(self.pieza) == 0:
            return 0.0
        desde, _ = pulsos_del_compas(self.pieza, self._plan.primer_compas)
        return self._segundos(desde)

    def _fin_s(self) -> float:
        """Donde acaba el tramo del plan, en segundos de la pasada."""
        if total_de_compases(self.pieza) == 0:
            return 0.0
        _, hasta = pulsos_del_compas(self.pieza, self._plan.ultimo_compas)
        return self._segundos(hasta)

    # -- lo que ve el de fuera -------------------------------------------

    @property
    def plan(self) -> PlanDePasada:
        return self._plan

    @property
    def estado(self) -> EstadoEstudio:
        carril = self._seguidor.estado
        pulsos = self._pulsos(carril.instante_s)
        return EstadoEstudio(
            carril=carril,
            instante_pulsos=pulsos,
            compas_en_curso=compas_en(self.pieza, pulsos),
            total_de_compases=total_de_compases(self.pieza),
            primer_compas=self._plan.primer_compas,
            ultimo_compas=self._plan.ultimo_compas or 0,
            repeticion=self._repeticion,
            cuenta_atras_restante_s=self._cuenta_atras_restante_s,
            factor_tempo=self._plan.factor_tempo,
            tempo_efectivo=self.pieza.tempo * self._plan.factor_tempo,
            en_bucle=self._plan.en_bucle,
            en_pausa=self._en_pausa,
            compas_variable=self.pieza.compas_variable,
            ritmo_aproximado=self.pieza.ritmo_aproximado,
        )

    def avanzar_a(self, instante_pasada_s: float) -> EstadoEstudio:
        """Mueve el reloj de la pasada. No consume audio."""
        self._seguidor.avanzar_a(instante_pasada_s)
        return self.estado

    def procesar(
        self, resultado: ResultadoAnalisis, instante_analisis: float
    ) -> EstadoEstudio:
        """Consume un cuadro de analisis."""
        self._seguidor.procesar(resultado, instante_analisis)
        return self.estado
```

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q`
Expected: PASS, 14 pruebas.

- [ ] **Step 5: Rompe el código y cuenta**

Quita el `/ self._plan.factor_tempo` de `_segundos` y corre: tienen que caer las de empezar en el compás 5 y la del 50 %. Cambia `**self.carril.a_dict()` por `"carril": self.carril.a_dict()` y corre: tiene que caer la del dict. Devuelve los dos cambios y **apunta las cifras**.

- [ ] **Step 6: Commit**

```bash
git add nucleo/piezas/estudio.py tests/test_estudio.py
git commit -m "$(cat <<'FIN'
feat: el plan de la pasada y la sesion de estudio

El reloj de la pasada es el del seguidor ya estirado por el factor; lo que no
depende del tempo es instante_pulsos, y es lo que usan los compases. El dict
del estado lleva los campos del carril al mismo nivel para no tocar useCarril.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 4: el informe por compases, con los acordes fuera de la cuenta

**Files:**
- Modify: `nucleo/piezas/estudio.py`
- Test: `tests/test_estudio.py` (se añade)

**Interfaces:**
- Consumes: todo lo de la Tarea 3.
- Produces:
  ```python
  @dataclass(frozen=True)
  class CompasDelInforme:
      numero: int
      notas_escritas: int
      notas_medibles: int
      acertadas: int
      a_tiempo: int
      pronto: int
      tarde: int
      desfase_medio_s: float | None
      tiene_acordes: bool
      def a_dict(self) -> dict

  @dataclass(frozen=True)
  class InformeDePasada:
      compases: tuple[CompasDelInforme, ...]
      ritmo_aproximado: bool
      compas_variable: bool
      factor_tempo: float
      def a_dict(self) -> dict

  def proporcion_limpia(informe: InformeDePasada) -> float | None

  # en SesionDeEstudio:
  @property
  def informe(self) -> InformeDePasada
  def cerrar_repeticion(self) -> InformeDePasada
  ```

**Por qué los acordes salen de la cuenta, y por qué es obligatorio:** `SeguidorPieza` dice de sí mismo que no sabe seguir acordes — debajo hay un detector de tono **monofónico**, así que de un acorde lee una sola altura y las demás notas de ese instante «se quedan sin cobrar por muy bien que se toquen». En un `.gp5` normal, eso haría que todos los compases con acordes salieran siempre fallados, y el botón de «machacar el compás que fallas» (Tarea 11) mandaría al usuario justo a los compases que **nunca** va a poder pasar.

Las notas de un acorde comparten `inicio_pulsos`, así que las **medibles** de un compás son **cuántos instantes distintos** hay en él: de un acorde de cuatro notas se puede medir una.

- [ ] **Step 1: Escribe las pruebas que fallan**

Añade a `tests/test_estudio.py` (y los imports nuevos arriba: `CompasDelInforme`, `InformeDePasada`, `proporcion_limpia`, y `from nucleo.analisis.pipeline import ResultadoAnalisis`):

```python
def suena(nota, cents=0.0):
    return ResultadoAnalisis(
        estado="nota", frecuencia=82.41, confianza=0.9, nivel_db=-25.0,
        nota=nota, cents=cents, posiciones=(),
    )


SILENCIO = ResultadoAnalisis(
    estado="silencio", frecuencia=None, confianza=0.0, nivel_db=-90.0,
    nota=None, cents=None, posiciones=(),
)


def tocar(sesion, nota, en):
    """Toca `nota` alrededor del instante `en` del reloj de la PASADA.

    Mismo patron que `tests/test_seguimiento_pieza.py`: el reloj se coloca a mano
    antes del primer cuadro, porque si no el seguidor fijaria la
    correspondencia entre sus dos relojes en el primer cuadro de audio y `en` no
    significaria nada.
    """
    instante = en - 0.1
    sesion.avanzar_a(instante)
    while instante < en:
        sesion.procesar(SILENCIO, instante)
        instante += 0.021
    for _ in range(12):
        sesion.procesar(suena(nota), instante)
        instante += 0.021


def compas_numero(informe, numero):
    return next(c for c in informe.compases if c.numero == numero)


def test_el_informe_cubre_el_tramo_del_plan_y_no_la_pieza_entera():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=3, ultimo_compas=5)
    )
    assert [c.numero for c in sesion.informe.compases] == [3, 4, 5]


def test_un_compas_tocado_a_tiempo_sale_acertado_y_a_tiempo():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    primero = compas_numero(sesion.informe, 1)
    assert primero.notas_escritas == 1
    assert primero.notas_medibles == 1
    assert primero.acertadas == 1
    assert primero.a_tiempo == 1
    assert primero.tarde == 0


def test_el_desfase_medio_lleva_signo_y_adelantarse_es_negativo():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=-0.3)
    assert compas_numero(sesion.informe, 1).desfase_medio_s < 0


def test_un_compas_que_nadie_toco_tiene_desfase_medio_none():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    assert compas_numero(sesion.informe, 4).desfase_medio_s is None


def test_de_un_acorde_solo_una_nota_es_medible_y_el_compas_queda_marcado():
    # Tres notas en el mismo instante: el detector es monofonico y lee una sola
    # altura, asi que las otras dos no se pueden medir por bien que se toquen.
    notas = tuple(
        NotaEnPieza(midi=m, cuerda=c, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
        for m, c in ((40, 6), (47, 5), (52, 4))
    )
    pieza = Pieza(
        nombre="acorde", perfil="guitarra_estandar", tempo=60, compas=(4, 4), notas=notas
    )
    primero = compas_numero(SesionDeEstudio(pieza).informe, 1)
    assert primero.notas_escritas == 3
    assert primero.notas_medibles == 1
    assert primero.tiene_acordes is True


def test_un_compas_con_acordes_no_entra_en_la_proporcion_limpia():
    # La proporcion es la que alimenta la regla del tempo: si los compases con
    # acordes contaran, la regla bajaria el tempo para siempre en cualquier
    # cancion de Guitar Pro.
    acorde = tuple(
        NotaEnPieza(midi=m, cuerda=c, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
        for m, c in ((40, 6), (47, 5))
    )
    sola = (NotaEnPieza(midi=40, cuerda=6, traste=0, inicio_pulsos=4.0, duracion_pulsos=1.0),)
    pieza = Pieza(
        nombre="mixta", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
        notas=acorde + sola,
    )
    sesion = SesionDeEstudio(pieza)
    tocar(sesion, "E2", en=4.0)
    # Solo cuenta el compas 2, que es el unico sin acordes: una de una.
    assert proporcion_limpia(sesion.informe) == pytest.approx(1.0)


def test_una_pieza_entera_de_acordes_no_da_proporcion_y_no_miente():
    acorde = tuple(
        NotaEnPieza(midi=m, cuerda=c, traste=0, inicio_pulsos=0.0, duracion_pulsos=1.0)
        for m, c in ((40, 6), (47, 5))
    )
    pieza = Pieza(
        nombre="solo acordes", perfil="guitarra_estandar", tempo=60, compas=(4, 4),
        notas=acorde,
    )
    assert proporcion_limpia(SesionDeEstudio(pieza).informe) is None


def test_el_informe_arrastra_el_aviso_del_ritmo_inventado():
    # En una tablatura de foro el ritmo lo infirio el lector de la etapa 3b:
    # presentar un desfase contra un ritmo inventado como diagnostico seria
    # mentira, asi que el aviso viaja con el informe.
    pieza = pieza_de([0.0], ritmo_aproximado=True)
    informe = SesionDeEstudio(pieza).informe
    assert informe.ritmo_aproximado is True
    assert informe.a_dict()["ritmo_aproximado"] is True


def test_el_ultimo_compas_incompleto_cuenta_sus_notas():
    # Nueve pulsos en 4/4: el compas 3 tiene una nota sola y es un compas de
    # verdad. Es como acaba casi cualquier cancion.
    sesion = SesionDeEstudio(pieza_de([0.0, 4.0, 8.0]))
    tercero = compas_numero(sesion.informe, 3)
    assert tercero.notas_escritas == 1
    assert tercero.notas_medibles == 1


def test_cerrar_la_repeticion_acumula_y_no_cuenta_dos_veces():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.cerrar_repeticion()
    assert compas_numero(sesion.informe, 1).acertadas == 1
    # Cerrar otra vez sin tocar nada no puede sumar nada.
    sesion.cerrar_repeticion()
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_el_informe_de_una_pieza_sin_notas_esta_vacio_y_no_rompe():
    informe = SesionDeEstudio(pieza_de([])).informe
    assert informe.compases == ()
    assert proporcion_limpia(informe) is None
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q -k "informe or acorde or proporcion or cerrar or desfase or incompleto"`
Expected: FAIL — `ImportError: cannot import name 'CompasDelInforme'`

- [ ] **Step 3: Implementa**

En `nucleo/piezas/estudio.py`, añade las dos dataclases y la función, y dentro de `SesionDeEstudio` el acumulador.

```python
@dataclass(frozen=True)
class CompasDelInforme:
    """Lo que paso en un compas de una pasada.

    `notas_medibles` son menos que `notas_escritas` cuando hay acordes: las notas
    de un acorde comparten instante, el detector de tono es MONOFONICO y lee una
    sola altura, asi que de un acorde de cuatro notas solo una se puede medir. Las
    otras tres no se cuentan como falladas porque no son un fallo del alumno, son
    un limite del programa.

    `desfase_medio_s` lleva SIGNO, y es el dato que de verdad diagnostica:
    "el 19 lo tocas entero 40 ms tarde" es accionable, "fallas el 19" no. Negativo
    es adelantarse, con la misma convencion que `NotaTocada.desfase_s`. Vale None
    cuando no se midio ni un desfase en ese compas.
    """

    numero: int
    notas_escritas: int
    notas_medibles: int
    acertadas: int
    a_tiempo: int
    pronto: int
    tarde: int
    desfase_medio_s: float | None
    tiene_acordes: bool

    def a_dict(self) -> dict:
        return {
            "numero": self.numero,
            "notas_escritas": self.notas_escritas,
            "notas_medibles": self.notas_medibles,
            "acertadas": self.acertadas,
            "a_tiempo": self.a_tiempo,
            "pronto": self.pronto,
            "tarde": self.tarde,
            "desfase_medio_s": (
                None if self.desfase_medio_s is None else round(self.desfase_medio_s, 3)
            ),
            "tiene_acordes": self.tiene_acordes,
        }


@dataclass(frozen=True)
class InformeDePasada:
    """El informe del tramo que se esta estudiando, compas a compas."""

    compases: tuple[CompasDelInforme, ...]
    ritmo_aproximado: bool
    compas_variable: bool
    factor_tempo: float

    def a_dict(self) -> dict:
        return {
            "compases": [c.a_dict() for c in self.compases],
            "ritmo_aproximado": self.ritmo_aproximado,
            "compas_variable": self.compas_variable,
            "factor_tempo": self.factor_tempo,
        }


def proporcion_limpia(informe: InformeDePasada) -> float | None:
    """Que fraccion de las notas medibles se acerto Y a tiempo, 0 a 1.

    Los compases con acordes quedan FUERA, y es la decision que hace que la regla
    del tempo sirva: contandolos, cualquier cancion de Guitar Pro bajaria el tempo
    para siempre. Devuelve None cuando no hay ni una nota medible sin acordes -una
    pieza entera de acordes-, y quien lea esto tiene que distinguir None de 0,0:
    uno es "no se puede medir" y el otro es "lo fallaste todo".
    """
    medibles = sum(c.notas_medibles for c in informe.compases if not c.tiene_acordes)
    if medibles == 0:
        return None
    buenas = sum(
        min(c.acertadas, c.a_tiempo) for c in informe.compases if not c.tiene_acordes
    )
    return buenas / medibles
```

El acumulador, dentro de `SesionDeEstudio`. En `__init__`, antes de crear el seguidor:

```python
        # Contadores por compas de ESTA pasada, con lo de las repeticiones ya
        # cerradas. Lo que todavia esta en el seguidor se suma al leer el informe
        # y se vuelca aqui en `cerrar_repeticion`: asi nada se cuenta dos veces y
        # el informe esta siempre al dia.
        self._acumulado: dict[int, dict] = {}
```

Y los métodos:

```python
    def _compases_del_tramo(self) -> tuple[int, ...]:
        if total_de_compases(self.pieza) == 0:
            return ()
        return tuple(range(self._plan.primer_compas, (self._plan.ultimo_compas or 0) + 1))

    def _indices_por_compas(self) -> dict[int, list[int]]:
        """Que notas de la pieza caen en cada compas, por indice."""
        reparto: dict[int, list[int]] = {}
        for indice, nota in enumerate(self.pieza.notas):
            reparto.setdefault(compas_en(self.pieza, nota.inicio_pulsos), []).append(indice)
        return reparto

    @staticmethod
    def _contadores() -> dict:
        return {"acertadas": 0, "a_tiempo": 0, "pronto": 0, "tarde": 0,
                "suma_desfase": 0.0, "con_desfase": 0}

    def _contar(self, tocadas, reparto: dict[int, list[int]]) -> dict[int, dict]:
        """Reparte por compas una lista de `NotaTocada`."""
        de_cada_indice = {
            indice: numero for numero, indices in reparto.items() for indice in indices
        }
        cuenta: dict[int, dict] = {}
        for tocada in tocadas:
            numero = de_cada_indice.get(tocada.indice)
            if numero is None:
                continue
            fila = cuenta.setdefault(numero, self._contadores())
            if tocada.acertada:
                fila["acertadas"] += 1
            if tocada.clasificacion is not None:
                fila[tocada.clasificacion] += 1
            if tocada.desfase_s is not None:
                fila["suma_desfase"] += tocada.desfase_s
                fila["con_desfase"] += 1
        return cuenta

    def _armar_informe(
        self, reparto: dict[int, list[int]], cuenta: dict[int, dict], acumulado: dict[int, dict]
    ) -> InformeDePasada:
        """Monta un informe sumando dos cuentas por compas. Sin efectos."""
        filas = []
        for numero in self._compases_del_tramo():
            indices = reparto.get(numero, [])
            escritas = len(indices)
            medibles = len({self.pieza.notas[i].inicio_pulsos for i in indices})
            suma = acumulado.get(numero, self._contadores())
            ahora = cuenta.get(numero, self._contadores())
            con_desfase = suma["con_desfase"] + ahora["con_desfase"]
            total_desfase = suma["suma_desfase"] + ahora["suma_desfase"]
            filas.append(
                CompasDelInforme(
                    numero=numero,
                    notas_escritas=escritas,
                    notas_medibles=medibles,
                    acertadas=suma["acertadas"] + ahora["acertadas"],
                    a_tiempo=suma["a_tiempo"] + ahora["a_tiempo"],
                    pronto=suma["pronto"] + ahora["pronto"],
                    tarde=suma["tarde"] + ahora["tarde"],
                    desfase_medio_s=(
                        None if con_desfase == 0 else total_desfase / con_desfase
                    ),
                    tiene_acordes=medibles < escritas,
                )
            )
        return InformeDePasada(
            compases=tuple(filas),
            ritmo_aproximado=self.pieza.ritmo_aproximado,
            compas_variable=self.pieza.compas_variable,
            factor_tempo=self._plan.factor_tempo,
        )

    @property
    def informe(self) -> InformeDePasada:
        """El informe de la PASADA al dia: lo acumulado mas lo que el seguidor lleva.

        Acumula todas las repeticiones del bucle: es lo que la interfaz muestra
        como "esta pasada". Lo de UNA repeticion lo devuelve `cerrar_repeticion`.
        """
        reparto = self._indices_por_compas()
        en_vuelo = self._contar(self._seguidor.estado.tocadas, reparto)
        return self._armar_informe(reparto, en_vuelo, self._acumulado)

    def cerrar_repeticion(self) -> InformeDePasada:
        """Vuelca lo que el seguidor lleva anotado al acumulador y lo deja limpio.

        **Devuelve el informe de SOLO esa repeticion**, sin lo acumulado, y eso es
        lo que la Tarea 7 anota en el historial: estudiando un bucle, la pregunta
        "¿ya te sale?" es sobre la vuelta que acaba de pasar, no sobre la suma de
        las ocho anteriores. El informe acumulado sigue disponible en `informe`.

        Se llama al dar la vuelta el bucle y antes de reconstruir el seguidor por
        un cambio de tempo: en los dos casos las `NotaTocada` del seguidor estan a
        punto de desaparecer, y sin este volcado el informe perderia la
        repeticion entera.

        Vaciar el seguidor despues es lo que impide contar dos veces: el informe
        suma lo acumulado MAS lo que el seguidor tenga.
        """
        reparto = self._indices_por_compas()
        cuenta = self._contar(self._seguidor.estado.tocadas, reparto)
        solo_esta_vuelta = self._armar_informe(reparto, cuenta, {})
        for numero, fila in cuenta.items():
            destino = self._acumulado.setdefault(numero, self._contadores())
            for clave, valor in fila.items():
                destino[clave] += valor
        self._seguidor.olvidar_tramo(0.0, self._seguidor.duracion_s + 1.0)
        return solo_esta_vuelta
```

**Un detalle que no es cosmético:** `olvidar_tramo` necesita saber hasta dónde llega la pieza, y eso vive en el privado `_duracion_s` del seguidor. No lo leas desde fuera: añade al seguidor una propiedad pública

```python
    @property
    def duracion_s(self) -> float:
        """Lo que dura la pieza en segundos DE LA PASADA (con el factor aplicado)."""
        return self._duracion_s
```

y usa esa. Un privado leído desde fuera es una dependencia que nadie ve.

Añade también esta prueba, que es la que vigila que el informe de la vuelta no arrastre las anteriores:

```python
def test_cerrar_la_repeticion_devuelve_solo_esa_vuelta():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    primera = sesion.cerrar_repeticion()
    assert compas_numero(primera, 1).acertadas == 1
    segunda = sesion.cerrar_repeticion()
    assert compas_numero(segunda, 1).acertadas == 0      # esta vuelta: nada
    assert compas_numero(sesion.informe, 1).acertadas == 1  # la pasada: uno
```

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q`
Expected: PASS, todas las de `tests/test_estudio.py` (las 14 de la Tarea 3 mas las 12 de esta).

- [ ] **Step 5: Rompe el código y cuenta**

Cambia `medibles < escritas` por `False` y corre: tienen que caer las dos de acordes. Quita el `olvidar_tramo` del final de `cerrar_repeticion` y corre: tiene que caer la de no contar dos veces. Cambia `min(c.acertadas, c.a_tiempo)` por `c.acertadas` y comprueba si cae algo: si no cae nada, **falta una prueba** de una nota acertada pero tarde, y la escribes. Devuelve los cambios y **apunta las cifras**.

- [ ] **Step 6: Commit**

```bash
git add nucleo/piezas/estudio.py tests/test_estudio.py
git commit -m "$(cat <<'FIN'
feat: el informe por compases, con los acordes fuera de la cuenta

De un acorde el detector monofonico lee una sola altura, asi que solo una nota
por instante es medible y el compas queda marcado. Sin esto, cualquier cancion
de Guitar Pro saldria enteramente fallada y el boton de machacar mandaria al
usuario a los compases que nunca podria pasar.

El desfase medio lleva signo, que es lo que diagnostica.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 5: el bucle, la cuenta atrás, la pausa y el cambio de plan

**Files:**
- Modify: `nucleo/piezas/estudio.py`
- Test: `tests/test_estudio.py` (se añade)

**Interfaces:**
- Consumes: todo lo de las Tareas 3 y 4.
- Produces:
  ```python
  # en SesionDeEstudio:
  def cambiar_plan(self, plan: PlanDePasada) -> EstadoEstudio
  def saltar_al_compas(self, numero: int) -> EstadoEstudio
  def reiniciar_pasada(self) -> EstadoEstudio
  def pausar(self) -> None
  def reanudar(self) -> None
  # y en EstadoEstudio, un campo mas:
  tramo_terminado: bool
  ```

**Lo que hay que entender antes de escribir una línea.** El seguidor tiene dos caminos y esta tarea respeta los dos, porque confundirlos rompe la medición del desfase:

- **Con audio**: `procesar` mueve el reloj de la pieza a través de la correspondencia entre el reloj de la pieza y el del análisis. **No se puede llamar `avanzar_a` en cada cuadro** en este camino: `avanzar_a` invalida esa correspondencia, y `_adjudicar` descarta los onsets anteriores al primer cuadro posterior al salto, así que llamándolo siempre **ningún** ataque se anotaría nunca.
- **Sin audio**: `avanzar_a` coloca el reloj a mano. Es el camino que usa el servidor cuando no llega señal, y el que usan todas las pruebas.

Y una regla nueva que la Tarea 7 implementa en el servidor: **el reloj de la sesión de estudio es la verdad**. El servidor le pasa instantes y después adopta el que la sesión devuelve (`estado.carril.instante_s`), en vez de llevar su propia cuenta. Sin esta regla, durante la cuenta atrás el reloj del servidor seguiría creciendo y al acabar la cuenta el cabezal daría un salto.

**El ciclo del bucle, en cuatro pasos que no se pueden intercambiar:**

1. `cerrar_repeticion()` — vuelca lo tocado al informe, o la repetición se pierde.
2. `olvidar_tramo(inicio, fin)` — las notas del tramo vuelven a poder cobrarse.
3. `seguidor.avanzar_a(inicio)` — **esto** es lo que descarta las pulsaciones en vuelo del final de la repetición anterior. Si fuera antes del paso 2, el `olvidar_tramo` borraría anotaciones que el salto va a descartar igual, y una nota tocada justo en la frontera se contaría en la repetición equivocada.
4. abrir la cuenta atrás.

- [ ] **Step 1: Escribe las pruebas que fallan**

Añade a `tests/test_estudio.py`:

```python
def test_al_llegar_al_final_del_bucle_vuelve_al_principio_y_sube_la_repeticion():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=2, ultimo_compas=3, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    assert sesion.estado.compas_en_curso == 2
    assert sesion.estado.repeticion == 1
    # El compas 4 empieza en el pulso 12, es decir el segundo 12 a 60 ppm.
    sesion.avanzar_a(12.0)
    assert sesion.estado.compas_en_curso == 2
    assert sesion.estado.repeticion == 2


def test_sin_bucle_el_reloj_se_para_al_final_del_tramo():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=2, ultimo_compas=3)
    )
    sesion.avanzar_a(50.0)
    assert sesion.estado.compas_en_curso == 3
    assert sesion.estado.tramo_terminado is True
    assert sesion.estado.a_dict()["completado"] is True


def test_la_cuenta_atras_dura_un_compas_al_tempo_de_la_pasada():
    pieza = pieza_de_doce_compases()
    normal = SesionDeEstudio(
        pieza, PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    normal.avanzar_a(4.0)
    assert normal.estado.cuenta_atras_restante_s == pytest.approx(4.0)
    lenta = SesionDeEstudio(
        pieza,
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True, factor_tempo=0.5),
    )
    lenta.avanzar_a(8.0)
    assert lenta.estado.cuenta_atras_restante_s == pytest.approx(8.0)


def test_durante_la_cuenta_atras_el_reloj_no_avanza():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.avanzar_a(4.0)
    quieto = sesion.estado.carril.instante_s
    sesion.avanzar_a(5.0)
    assert sesion.estado.carril.instante_s == pytest.approx(quieto)
    assert sesion.estado.cuenta_atras_restante_s == pytest.approx(3.0)
    # Y al agotarse, el reloj vuelve a correr desde el inicio del tramo.
    sesion.avanzar_a(8.5)
    assert sesion.estado.cuenta_atras_restante_s == 0.0
    assert sesion.estado.carril.instante_s == pytest.approx(0.0)


def test_durante_la_cuenta_atras_no_se_cobra_nada():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(), PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True)
    )
    sesion.avanzar_a(4.0)
    tocar(sesion, "E2", en=4.5)
    assert sesion.estado.carril.tocadas == ()


def test_tras_la_vuelta_del_bucle_las_notas_se_pueden_volver_a_cobrar():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    tocar(sesion, "E2", en=0.0)
    assert len(sesion.estado.carril.tocadas) == 1
    sesion.avanzar_a(4.0)          # da la vuelta
    assert sesion.estado.carril.tocadas == ()
    tocar(sesion, "E2", en=0.0)
    assert len(sesion.estado.carril.tocadas) == 1
    # Y las dos vueltas estan en el informe: dos aciertos en el compas 1.
    assert compas_numero(sesion.informe, 1).acertadas == 2


def test_un_bucle_sobre_un_compas_sin_notas_no_se_queda_clavado():
    # Compases 1 y 3 con notas, el 2 vacio. Un rango vacio no puede dividir por
    # cero ni dejar el cabezal parado: el reloj lo cruza y da la vuelta igual.
    sesion = SesionDeEstudio(
        pieza_de([0.0, 8.0]),
        PlanDePasada(primer_compas=2, ultimo_compas=2, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    assert sesion.estado.compas_en_curso == 2
    sesion.avanzar_a(8.0)
    assert sesion.estado.repeticion == 2
    assert sesion.estado.compas_en_curso == 2
    assert sesion.informe.compases[0].notas_escritas == 0


def test_un_bucle_de_un_solo_compas_con_una_nota_sola_funciona():
    sesion = SesionDeEstudio(
        pieza_de([0.0]),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    tocar(sesion, "E2", en=0.0)
    sesion.avanzar_a(4.0)
    assert sesion.estado.repeticion == 2
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_cambiar_el_tempo_a_mitad_conserva_el_compas_y_lo_ya_tocado():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.avanzar_a(9.0)                      # compas 3
    sesion.cambiar_plan(PlanDePasada(factor_tempo=0.5))
    assert sesion.estado.compas_en_curso == 3
    assert sesion.estado.instante_pulsos == pytest.approx(9.0)
    assert sesion.estado.factor_tempo == 0.5
    # El reloj de la pasada se ha estirado: 9 pulsos al 50 % son 18 segundos.
    assert sesion.estado.carril.instante_s == pytest.approx(18.0)
    # Y el acierto del compas 1 sigue en el informe.
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_cambiar_a_un_rango_que_no_contiene_el_cabezal_lo_lleva_al_nuevo_inicio():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.avanzar_a(1.0)
    sesion.cambiar_plan(PlanDePasada(primer_compas=7, ultimo_compas=8, en_bucle=True))
    assert sesion.estado.compas_en_curso == 7


def test_saltar_a_un_compas_coloca_el_cabezal_y_no_borra_el_informe():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.saltar_al_compas(9)
    assert sesion.estado.compas_en_curso == 9
    assert compas_numero(sesion.informe, 1).acertadas == 1


def test_saltar_a_un_compas_que_no_existe_se_rechaza():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    with pytest.raises(ValueError, match="99"):
        sesion.saltar_al_compas(99)


def test_reiniciar_la_pasada_vuelve_al_inicio_y_olvida_el_informe():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    tocar(sesion, "E2", en=0.0)
    sesion.avanzar_a(9.0)
    sesion.reiniciar_pasada()
    assert sesion.estado.compas_en_curso == 1
    assert sesion.estado.repeticion == 1
    assert compas_numero(sesion.informe, 1).acertadas == 0


def test_en_pausa_el_reloj_no_avanza_y_al_reanudar_sigue_donde_estaba():
    sesion = SesionDeEstudio(pieza_de_doce_compases())
    sesion.avanzar_a(5.0)
    sesion.pausar()
    sesion.avanzar_a(20.0)
    assert sesion.estado.carril.instante_s == pytest.approx(5.0)
    assert sesion.estado.en_pausa is True
    sesion.reanudar()
    sesion.avanzar_a(21.0)
    assert sesion.estado.carril.instante_s == pytest.approx(6.0)
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q -k "bucle or cuenta or pausa or saltar or cambiar or reiniciar or tramo"`
Expected: FAIL — `AttributeError: 'SesionDeEstudio' object has no attribute 'cambiar_plan'` y `tramo_terminado`.

- [ ] **Step 3: Implementa**

**La pausa y la cuenta atrás necesitan deltas, no instantes absolutos.** Guarda el último instante que te pidieron y resta. En `__init__`:

```python
        self._tramo_terminado = False
        # El informe de la ultima vuelta del bucle que se cerro, o None si
        # todavia no se cerro ninguna. Lo lee el servidor para el historial.
        self._ultima_vuelta: InformeDePasada | None = None
        # El ultimo instante que nos pidieron, para sacar deltas: la pausa y la
        # cuenta atras necesitan saber CUANTO paso, no en que momento estamos.
        # Los dos que nos llaman (el servidor y las pruebas) son monotonos.
        self._ultimo_pedido: float | None = None
```

Añade `tramo_terminado: bool` a `EstadoEstudio`, pásalo en `estado`, y en su `a_dict` **sobrescribe** `completado`:

```python
            # `completado` del carril es "se acabo la PIEZA"; para quien practica
            # un tramo, lo que se acabo es el tramo. Se publica con el mismo
            # nombre porque es lo que la interfaz de la etapa 3a ya lee.
            "completado": self.tramo_terminado or self.carril.completado,
```

Los métodos nuevos y el reparto del tiempo:

```python
    def _segundos_de_cuenta_atras(self) -> float:
        if self._plan.compases_de_cuenta_atras == 0:
            return 0.0
        return self._segundos(
            pulsos_por_compas(self.pieza) * self._plan.compases_de_cuenta_atras
        )

    def _delta(self, instante: float) -> float:
        """Cuanto tiempo paso desde la ultima vez, nunca negativo."""
        anterior = self._ultimo_pedido
        self._ultimo_pedido = instante
        if anterior is None:
            return 0.0
        return max(0.0, instante - anterior)

    def _dar_la_vuelta(self) -> None:
        """Los cuatro pasos del bucle, en este orden y no en otro.

        El informe de la vuelta que acaba se guarda en `_ultima_vuelta`, porque
        quien lo necesita -el historial, en la Tarea 7- se entera de la vuelta
        mirando `repeticion` DESPUES de que esto haya pasado, y entonces ya no
        podria pedirlo.
        """
        self._ultima_vuelta = self.cerrar_repeticion()
        inicio, fin = self._inicio_s(), self._fin_s()
        self._seguidor.olvidar_tramo(inicio, fin)
        self._seguidor.avanzar_a(inicio)
        self._repeticion += 1
        self._cuenta_atras_restante_s = self._segundos_de_cuenta_atras()

    def _al_dia(self, instante: float) -> None:
        """Lo que hay que mirar tras mover el reloj: la cuenta atras y el final.

        La llaman los dos caminos -con audio y sin audio-, porque el bucle tiene
        que dar la vuelta igual cuando el cable esta desenchufado.
        """
        if self._cuenta_atras_restante_s > 0:
            return
        if self._seguidor.estado.instante_s < self._fin_s():
            return
        if self._plan.en_bucle:
            self._dar_la_vuelta()
        else:
            self._tramo_terminado = True
            self._seguidor.avanzar_a(self._fin_s())

    def avanzar_a(self, instante_pasada_s: float) -> EstadoEstudio:
        """Camino SIN audio: coloca el reloj a mano.

        El instante que llega es absoluto, pero la pausa y la cuenta atras se
        miden con el delta: mientras una de las dos esta activa, el reloj de la
        pieza se queda donde esta y lo unico que corre es la cuenta.
        """
        delta = self._delta(instante_pasada_s)
        if self._en_pausa:
            return self.estado
        if self._cuenta_atras_restante_s > 0:
            self._cuenta_atras_restante_s = max(
                0.0, self._cuenta_atras_restante_s - delta
            )
            # Colocar el reloj en el inicio en cada mirada es lo que lo congela, y
            # ademas descarta las pulsaciones en vuelo: durante la cuenta atras no
            # se puede cobrar nada.
            self._seguidor.avanzar_a(self._inicio_s())
            return self.estado
        self._seguidor.avanzar_a(instante_pasada_s)
        self._al_dia(instante_pasada_s)
        return self.estado

    def procesar(self, resultado: ResultadoAnalisis, instante_analisis: float) -> EstadoEstudio:
        """Camino CON audio: el cuadro mueve el reloj por su correspondencia.

        Aqui NO se llama `avanzar_a` cuando la pasada corre: invalidaria la
        correspondencia entre el reloj de la pieza y el del analisis, y
        `_adjudicar` descarta los onsets anteriores al primer cuadro posterior a
        un salto, asi que ningun ataque se anotaria nunca.
        """
        delta = self._delta(instante_analisis)
        if self._en_pausa:
            self._seguidor.avanzar_a(self._seguidor.estado.instante_s)
            return self.estado
        if self._cuenta_atras_restante_s > 0:
            self._cuenta_atras_restante_s = max(
                0.0, self._cuenta_atras_restante_s - delta
            )
            self._seguidor.avanzar_a(self._inicio_s())
            return self.estado
        self._seguidor.procesar(resultado, instante_analisis)
        self._al_dia(instante_analisis)
        return self.estado

    def cambiar_plan(self, plan: PlanDePasada) -> EstadoEstudio:
        """Cambia tempo, bucle, click o rango SIN reiniciar la pasada.

        Un factor nuevo obliga a reconstruir el seguidor, porque sus instantes se
        calculan una vez y no cambian nunca (es lo que dice su propio comentario).
        Antes de tirarlo se cierra la repeticion: asi lo ya tocado sigue en el
        informe en vez de desaparecer con el seguidor viejo.

        El cabezal se queda en el MISMO PULSO, no en el mismo segundo: cambiar de
        tempo no mueve a nadie de sitio dentro de la musica.
        """
        nuevo = validar_plan(self.pieza, plan)
        pulsos = self._pulsos(self._seguidor.estado.instante_s)
        self.cerrar_repeticion()
        cambia_el_factor = nuevo.factor_tempo != self._plan.factor_tempo
        self._plan = nuevo
        if cambia_el_factor:
            self._seguidor = self._nuevo_seguidor()
        self._tramo_terminado = False
        self._cuenta_atras_restante_s = 0.0
        dentro = (
            nuevo.primer_compas <= compas_en(self.pieza, pulsos) <= (nuevo.ultimo_compas or 0)
        )
        destino = self._segundos(pulsos) if dentro else self._inicio_s()
        self._seguidor.avanzar_a(destino)
        return self.estado

    def saltar_al_compas(self, numero: int) -> EstadoEstudio:
        """Coloca el cabezal al principio del compas `numero`.

        No borra el informe: lo que ya tocaste sigue contando. Cancela la cuenta
        atras, porque la cuenta atras es para empezar donde ya estabas.
        """
        desde, _ = pulsos_del_compas(self.pieza, numero)
        self.cerrar_repeticion()
        self._cuenta_atras_restante_s = 0.0
        self._tramo_terminado = False
        self._seguidor.avanzar_a(self._segundos(desde))
        return self.estado

    def reiniciar_pasada(self) -> EstadoEstudio:
        """Vuelve al principio del tramo y olvida el informe. Empieza otra pasada."""
        self._acumulado = {}
        self._repeticion = 1
        self._tramo_terminado = False
        self._cuenta_atras_restante_s = 0.0
        self._seguidor = self._nuevo_seguidor()
        self._seguidor.avanzar_a(self._inicio_s())
        return self.estado

    def pausar(self) -> None:
        """Pausa a voluntad del usuario. No es lo mismo que perder la señal."""
        self._en_pausa = True

    def reanudar(self) -> None:
        self._en_pausa = False
```

`pulsos_del_compas` ya lanza `ValueError` con el número pedido y el total, así que `saltar_al_compas(99)` sale validado sin escribir otra comprobación.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q`
Expected: PASS, todas las de `tests/test_estudio.py`: las de las Tareas 3 y 4 mas las 14 de esta.

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, nada de las etapas anteriores se mueve.

- [ ] **Step 5: Rompe el código y cuenta**

Cuatro roturas, una por decisión que costó pensar:

1. En `_dar_la_vuelta`, mueve `self._seguidor.avanzar_a(inicio)` **antes** de `olvidar_tramo` y corre.
2. Quita el `self.cerrar_repeticion()` de `_dar_la_vuelta` y corre: tiene que caer la de los dos aciertos.
3. En `procesar`, sustituye la rama normal por `self._seguidor.avanzar_a(instante_analisis)` y corre: tienen que caer **muchas**, porque ningún ataque se anotaría.
4. En `cambiar_plan`, usa `self._seguidor.estado.instante_s` como destino en vez de `self._segundos(pulsos)` y corre: tiene que caer la del cambio de tempo.

Devuelve los cuatro cambios y **apunta cuántas cayeron con cada uno**. Si la 1 no tira ninguna, escribe la prueba que falta: una nota tocada en la frontera del final del bucle tiene que contarse en la repetición que acaba, no en la que empieza.

- [ ] **Step 6: Commit**

```bash
git add nucleo/piezas/estudio.py tests/test_estudio.py
git commit -m "$(cat <<'FIN'
feat: el bucle, la cuenta atras, la pausa y el cambio de plan en caliente

Los cuatro pasos del salto van en orden: cerrar el informe, olvidar el tramo,
avanzar_a (que es quien descarta las pulsaciones en vuelo) y abrir la cuenta
atras. Durante la cuenta el reloj se congela colocandolo en el inicio en cada
mirada, que de paso impide cobrar.

El camino con audio NO llama avanzar_a: invalidaria la correspondencia entre
los dos relojes del seguidor y ningun ataque se anotaria.

Cambiar el tempo conserva el PULSO, no el segundo.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 6: el historial y la subida automática del tempo

**Files:**
- Modify: `nucleo/piezas/estudio.py`
- Test: `tests/test_estudio.py` (se añade)

**Interfaces:**
- Consumes: `InformeDePasada`, `proporcion_limpia` (Tarea 4); `FACTOR_MINIMO`, `FACTOR_MAXIMO`, `PASO_DEL_FACTOR` (Tarea 3).
- Produces:
  ```python
  UMBRAL_PARA_SUBIR = 0.90
  UMBRAL_PARA_BAJAR = 0.70
  PASADAS_BUENAS_PARA_SUBIR = 2

  class HistorialDeEstudio:
      def anotar(self, informe: InformeDePasada) -> None
      @property
      def pasadas(self) -> int
      def peores_compases(self, cuantos: int = 3) -> tuple[tuple[int, int, int], ...]
      def factor_sugerido(self, factor_actual: float) -> float
      def a_dict(self) -> dict
  ```

**En memoria y nada más**, que es la decisión del usuario: al apagar el servidor se olvida. El día que se quiera guardar en disco, esta clase es el único sitio que habría que cambiar.

- [ ] **Step 1: Escribe las pruebas que fallan**

Añade a `tests/test_estudio.py` (e importa `HistorialDeEstudio`, `UMBRAL_PARA_SUBIR`, `UMBRAL_PARA_BAJAR`):

```python
def informe_de(filas, ritmo_aproximado=False):
    """Un informe a mano: (numero, escritas, medibles, acertadas, a_tiempo, acordes)."""
    compases = tuple(
        CompasDelInforme(
            numero=n, notas_escritas=e, notas_medibles=m, acertadas=a, a_tiempo=t,
            pronto=0, tarde=0, desfase_medio_s=None, tiene_acordes=acordes,
        )
        for n, e, m, a, t, acordes in filas
    )
    return InformeDePasada(
        compases=compases, ritmo_aproximado=ritmo_aproximado,
        compas_variable=False, factor_tempo=1.0,
    )


def pasada_limpia():
    return informe_de([(1, 10, 10, 10, 10, False)])


def pasada_mala():
    return informe_de([(1, 10, 10, 6, 6, False)])


def test_dos_pasadas_buenas_seguidas_suben_el_tempo_un_cinco_por_ciento():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.65)


def test_tras_subir_la_racha_se_consume_y_no_vuelve_a_subir_sola():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_limpia())
    historial.anotar(pasada_limpia())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.65)
    assert historial.factor_sugerido(0.65) == pytest.approx(0.65)


def test_una_pasada_mala_baja_el_tempo_sin_esperar_a_la_segunda():
    historial = HistorialDeEstudio()
    historial.anotar(pasada_mala())
    assert historial.factor_sugerido(0.60) == pytest.approx(0.55)


def test_el_tempo_no_pasa_del_escrito_ni_baja_del_suelo():
    arriba = HistorialDeEstudio()
    arriba.anotar(pasada_limpia())
    arriba.anotar(pasada_limpia())
    assert arriba.factor_sugerido(FACTOR_MAXIMO) == pytest.approx(FACTOR_MAXIMO)
    abajo = HistorialDeEstudio()
    abajo.anotar(pasada_mala())
    assert abajo.factor_sugerido(FACTOR_MINIMO) == pytest.approx(FACTOR_MINIMO)


def test_una_pieza_entera_de_acordes_nunca_mueve_el_tempo():
    # Sin notas medibles no hay proporcion, y sin proporcion no hay juicio: el
    # tempo se queda donde el usuario lo puso.
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 3, 1, 0, 0, True)]))
    historial.anotar(informe_de([(1, 3, 1, 0, 0, True)]))
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)


def test_los_peores_compases_salen_ordenados_con_sus_cifras():
    historial = HistorialDeEstudio()
    for _ in range(5):
        # El 19 siempre fallado, el 4 fallado una vez, el 7 nunca.
        historial.anotar(informe_de([
            (4, 4, 4, 4, 4, False),
            (7, 4, 4, 4, 4, False),
            (19, 4, 4, 1, 1, False),
        ]))
    historial.anotar(informe_de([
        (4, 4, 4, 2, 2, False),
        (7, 4, 4, 4, 4, False),
        (19, 4, 4, 0, 0, False),
    ]))
    peores = historial.peores_compases(2)
    assert peores[0] == (19, 6, 6)
    assert peores[1] == (4, 1, 6)


def test_los_compases_con_acordes_no_aparecen_entre_los_peores():
    # Esta es la prueba que impide que el boton de machacar mande al usuario a un
    # compas que nunca podra pasar.
    historial = HistorialDeEstudio()
    historial.anotar(informe_de([(1, 4, 1, 0, 0, True), (2, 4, 4, 1, 1, False)]))
    assert [c for c, _, _ in historial.peores_compases()] == [2]


def test_un_historial_sin_pasadas_no_tiene_peores_ni_mueve_el_tempo():
    historial = HistorialDeEstudio()
    assert historial.pasadas == 0
    assert historial.peores_compases() == ()
    assert historial.factor_sugerido(0.60) == pytest.approx(0.60)
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q -k "historial or peores or tempo or pasada"`
Expected: FAIL — `ImportError: cannot import name 'HistorialDeEstudio'`

- [ ] **Step 3: Implementa**

```python
# La frontera para subir y la para bajar, separadas a proposito: con una sola,
# una pasada al 89 % bajaria el tempo que la del 90 % acababa de subir, y el
# tempo oscilaria sin que el alumno mejorara ni empeorara.
UMBRAL_PARA_SUBIR = 0.90
UMBRAL_PARA_BAJAR = 0.70
PASADAS_BUENAS_PARA_SUBIR = 2


class HistorialDeEstudio:
    """Las pasadas de esta sesion. En memoria: al apagar el servidor se olvida.

    Es la decision del usuario, y el precio esta medido: no hay formato de
    archivo que versionar, ni escritura atomica, ni una sola prueba que toque el
    disco. El dia que se quiera recordar entre dias, esta clase es el unico sitio
    que cambia.
    """

    def __init__(self) -> None:
        self._pasadas: list[InformeDePasada] = []
        # Proporciones desde la ultima vez que se decidio mover el tempo. Se
        # vacia al decidir, y por eso `factor_sugerido` no sube dos veces con la
        # misma racha.
        self._racha: list[float] = []

    def anotar(self, informe: InformeDePasada) -> None:
        self._pasadas.append(informe)
        proporcion = proporcion_limpia(informe)
        if proporcion is not None:
            self._racha.append(proporcion)

    @property
    def pasadas(self) -> int:
        return len(self._pasadas)

    def peores_compases(self, cuantos: int = 3) -> tuple[tuple[int, int, int], ...]:
        """(compas, pasadas falladas, pasadas contadas), el peor primero.

        Un compas esta "fallado" en una pasada si no se acertaron todas sus notas
        medibles. Los compases con acordes NO entran: ahi solo se puede medir una
        nota de cada acorde, asi que saldrian fallados siempre y el boton de
        machacar mandaria al usuario justo a los compases que nunca podra pasar.
        """
        fallos: dict[int, list[int]] = {}
        for informe in self._pasadas:
            for compas in informe.compases:
                if compas.tiene_acordes or compas.notas_medibles == 0:
                    continue
                marca = fallos.setdefault(compas.numero, [0, 0])
                marca[1] += 1
                if compas.acertadas < compas.notas_medibles:
                    marca[0] += 1
        ordenados = sorted(
            ((numero, fallo, contadas) for numero, (fallo, contadas) in fallos.items()),
            key=lambda fila: (-fila[1], -fila[1] / fila[2], fila[0]),
        )
        return tuple(fila for fila in ordenados[:cuantos] if fila[1] > 0)

    def factor_sugerido(self, factor_actual: float) -> float:
        """Que factor deberia tener la proxima pasada. CONSUME la racha al decidir.

        Dos pasadas seguidas por encima de `UMBRAL_PARA_SUBIR` suben un paso; una
        sola por debajo de `UMBRAL_PARA_BAJAR` baja un paso, sin esperar a la
        segunda, porque quien falla mucho no necesita confirmacion. Las pasadas
        sin proporcion medible -una pieza entera de acordes- no cuentan para
        ninguna de las dos cosas.
        """
        if not self._racha:
            return factor_actual
        if self._racha[-1] < UMBRAL_PARA_BAJAR:
            self._racha = []
            return max(FACTOR_MINIMO, round(factor_actual - PASO_DEL_FACTOR, 2))
        ultimas = self._racha[-PASADAS_BUENAS_PARA_SUBIR:]
        if (
            len(ultimas) == PASADAS_BUENAS_PARA_SUBIR
            and all(p >= UMBRAL_PARA_SUBIR for p in ultimas)
        ):
            self._racha = []
            return min(FACTOR_MAXIMO, round(factor_actual + PASO_DEL_FACTOR, 2))
        return factor_actual

    def a_dict(self) -> dict:
        return {
            "pasadas": self.pasadas,
            "peores_compases": [
                {"compas": c, "falladas": f, "contadas": t}
                for c, f, t in self.peores_compases()
            ],
        }
```

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_estudio.py -q`
Expected: PASS, todas las de `tests/test_estudio.py`: las de las Tareas 3, 4 y 5 mas las 8 de esta.

- [ ] **Step 5: Rompe el código y cuenta**

Quita `self._racha = []` de la rama de subir y corre: tiene que caer la de la racha consumida. Quita el `if compas.tiene_acordes` del filtro y corre: tiene que caer la de los acordes entre los peores. Cambia `PASADAS_BUENAS_PARA_SUBIR` por 1 y corre: tiene que caer la de «una sola no sube». Devuelve los cambios y **apunta las cifras**.

- [ ] **Step 6: Commit**

```bash
git add nucleo/piezas/estudio.py tests/test_estudio.py
git commit -m "$(cat <<'FIN'
feat: el historial de la sesion y la regla del tempo automatico

Dos pasadas al 90 % suben un paso, una al 70 % baja uno, y la racha se
consume al decidir para no subir dos veces con lo mismo. Las fronteras son
dos y no una para que el tempo no oscile.

Los compases con acordes no aparecen entre los peores: ahi solo se puede
medir una nota de cada acorde.

En memoria y nada mas, que es la decision del usuario.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 7: el servidor sostiene la sesión de estudio y abre los cinco endpoints

**Files:**
- Modify: `servidor/piezas.py` (`SesionCarril`)
- Modify: `servidor/app.py` (`iniciar_pieza` y cinco endpoints)
- Test: `tests/test_app_estudio.py` (nuevo)

**Interfaces:**
- Consumes: `PlanDePasada`, `SesionDeEstudio`, `HistorialDeEstudio`, `validar_plan` (Tareas 3-6).
- Produces:
  ```python
  # SesionCarril
  def iniciar(self, pieza: Pieza, plan: PlanDePasada | None = None) -> dict
  def cambiar_plan(self, plan: PlanDePasada) -> dict
  def saltar(self, numero: int) -> dict
  def pausa(self, activa: bool) -> dict
  def informe(self) -> dict      # {"informe": ..., "historial": ...}
  def pieza_en_marcha(self) -> dict  # {"pieza": ... | None, "secciones_en_compases": [...], **estado}
  ```
  Las respuestas de `iniciar` y de `pieza_en_marcha` llevan además
  `secciones_en_compases`: `[{"nombre": str, "primer_compas": int, "ultimo_compas": int}]`,
  construido con `compases_de_la_seccion` (Tarea 1). **La interfaz no convierte
  pulsos en compases**: esa cuenta es del núcleo, y una copia en TypeScript se
  desincronizaría el día que el compás variable se arregle. Lista vacía si la
  pieza no trae secciones.
  Endpoints: `POST /api/piezas/plan`, `POST /api/piezas/saltar`, `POST /api/piezas/pausa`, `GET /api/piezas/informe`, `GET /api/piezas/pieza`.

**Tres reglas que esta tarea tiene que respetar, y que ya están razonadas en el código que vas a tocar:**

1. **`self._seguidor` pasa a ser `self._estudio`**, y todas sus llamadas (`avanzar_a`, `procesar`, `estado`) van ahora a la `SesionDeEstudio`, que tiene los mismos nombres a propósito. Lo que **no** cambia: el candado, el observador, `ESPERA_SIN_CUADROS_S`, `TECHO_TRAMO_S` y la pausa por falta de señal. Todo eso costó tres rondas de arreglos en la etapa 3a; no se toca.
2. **El reloj de la sesión de estudio es la verdad.** Después de cada llamada, `self._instante = estado.carril.instante_s`. Sin esto, durante la cuenta atrás el reloj del servidor seguiría creciendo y al acabar la cuenta el cabezal daría un salto hacia delante del tamaño de la cuenta.
3. **Hay dos pausas y son distintas.** `self._pausado` es «no llega señal del cable» y la decide el servidor mirando el audio; `estudio.en_pausa` la decide el usuario. Ni se mezclan ni se sobreescriben: el estado publica las dos (`pausado` y `en_pausa`), y la interfaz dice cosas distintas.

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `tests/test_app_estudio.py`. Copia la cabecera, `CapturaFalsa`, `CABLE`, `FS`, `BASE_LOCAL` y la fixture `cliente` de `tests/test_app_carril.py` **tal cual** (el comentario de por qué `BASE_LOCAL` es localhost y no `testserver` incluido: el guardia de peticiones rechaza lo demás, con razón), y añade:

```python
def pieza_de_doce_compases():
    """Doce compases de 4/4 a 60 ppm, una nota al principio de cada uno."""
    return {
        "nombre": "estudio",
        "perfil": "guitarra_estandar",
        "tempo": 60,
        "compas": [4, 4],
        "notas": [
            {"midi": 40, "cuerda": 6, "traste": 0,
             "inicio_pulsos": i * 4.0, "duracion_pulsos": 1.0}
            for i in range(12)
        ],
    }


def iniciar(cliente, **plan):
    cuerpo = {"pieza": pieza_de_doce_compases()}
    if plan:
        cuerpo["plan"] = plan
    return cliente.post("/api/piezas/iniciar", json=cuerpo)


def test_iniciar_sin_plan_se_comporta_como_la_etapa_3a(cliente):
    datos = iniciar(cliente).json()
    assert datos["factor_tempo"] == 1.0
    assert datos["en_bucle"] is False
    assert datos["primer_compas"] == 1
    assert datos["ultimo_compas"] == 12
    assert datos["compas_en_curso"] == 1
    # Y sigue trayendo la pieza entera una sola vez, como la etapa 3a.
    assert len(datos["pieza"]["notas"]) == 12


def test_iniciar_con_plan_arranca_en_el_compas_pedido(cliente):
    datos = iniciar(cliente, primer_compas=5, ultimo_compas=8, en_bucle=True).json()
    assert datos["compas_en_curso"] == 5
    assert datos["en_bucle"] is True


def test_un_factor_fuera_de_rango_se_rechaza_con_cuatrocientos(cliente):
    respuesta = iniciar(cliente, factor_tempo=2.0)
    assert respuesta.status_code == 400
    assert "100" in respuesta.json()["detail"]


def test_un_compas_que_no_existe_se_rechaza_con_cuatrocientos(cliente):
    respuesta = iniciar(cliente, primer_compas=40)
    assert respuesta.status_code == 400
    assert "40" in respuesta.json()["detail"]


def test_cambiar_el_plan_no_reinicia_la_pasada(cliente):
    iniciar(cliente)
    cliente.post("/api/piezas/saltar", json={"compas": 6})
    datos = cliente.post("/api/piezas/plan", json={"factor_tempo": 0.5}).json()
    assert datos["factor_tempo"] == 0.5
    assert datos["compas_en_curso"] == 6
    assert datos["tempo_efectivo"] == 30.0


def test_saltar_a_un_compas_mueve_el_cabezal(cliente):
    iniciar(cliente)
    datos = cliente.post("/api/piezas/saltar", json={"compas": 9}).json()
    assert datos["compas_en_curso"] == 9


def test_saltar_a_un_compas_que_no_existe_se_rechaza(cliente):
    iniciar(cliente)
    respuesta = cliente.post("/api/piezas/saltar", json={"compas": 99})
    assert respuesta.status_code == 400
    assert "99" in respuesta.json()["detail"]


def test_la_pausa_del_usuario_es_distinta_de_la_falta_de_senal(cliente):
    iniciar(cliente)
    datos = cliente.post("/api/piezas/pausa", json={"activa": True}).json()
    assert datos["en_pausa"] is True
    assert "pausado" in datos          # el de la señal sigue existiendo, aparte
    datos = cliente.post("/api/piezas/pausa", json={"activa": False}).json()
    assert datos["en_pausa"] is False


def test_el_informe_trae_los_compases_del_tramo_y_el_historial(cliente):
    iniciar(cliente, primer_compas=2, ultimo_compas=3)
    datos = cliente.get("/api/piezas/informe").json()
    assert [c["numero"] for c in datos["informe"]["compases"]] == [2, 3]
    assert datos["historial"]["pasadas"] == 0
    assert datos["historial"]["peores_compases"] == []


def test_las_secciones_viajan_ya_convertidas_en_compases(cliente):
    # La interfaz no repite la cuenta del nucleo: elige de esta lista.
    pieza = pieza_de_doce_compases()
    pieza["secciones"] = [
        {"nombre": "Intro", "inicio_pulsos": 0.0},
        {"nombre": "Estribillo", "inicio_pulsos": 16.0},
    ]
    datos = cliente.post("/api/piezas/iniciar", json={"pieza": pieza}).json()
    assert datos["secciones_en_compases"] == [
        {"nombre": "Intro", "primer_compas": 1, "ultimo_compas": 4},
        {"nombre": "Estribillo", "primer_compas": 5, "ultimo_compas": 12},
    ]


def test_sin_secciones_la_lista_viaja_vacia(cliente):
    assert iniciar(cliente).json()["secciones_en_compases"] == []


def test_la_pieza_en_marcha_se_puede_volver_a_pedir(cliente):
    # Es la deuda de la etapa 3a: la pieza viajaba una sola vez, asi que recargar
    # el navegador a mitad de cancion dejaba el carril en blanco.
    iniciar(cliente)
    datos = cliente.get("/api/piezas/pieza").json()
    assert datos["pieza"]["nombre"] == "estudio"
    assert len(datos["pieza"]["notas"]) == 12
    assert datos["compas_en_curso"] == 1


def test_sin_pieza_en_marcha_la_pieza_es_nula_y_no_es_un_error(cliente):
    datos = cliente.get("/api/piezas/pieza").json()
    assert datos["pieza"] is None


def test_los_endpoints_de_estudio_sin_pieza_en_marcha_dan_cuatrocientos(cliente):
    for metodo, ruta, cuerpo in (
        ("post", "/api/piezas/plan", {"factor_tempo": 0.5}),
        ("post", "/api/piezas/saltar", {"compas": 2}),
        ("post", "/api/piezas/pausa", {"activa": True}),
    ):
        respuesta = getattr(cliente, metodo)(ruta, json=cuerpo)
        assert respuesta.status_code == 400, ruta
        assert "pieza" in respuesta.json()["detail"].lower(), ruta
    assert cliente.get("/api/piezas/informe").status_code == 400


def test_el_websocket_publica_los_campos_del_estudio(cliente):
    iniciar(cliente, primer_compas=2, ultimo_compas=3, en_bucle=True)
    with cliente.websocket_connect("ws://127.0.0.1:8420/ws/piezas") as ws:
        datos = ws.receive_json()
    for clave in ("compas_en_curso", "total_de_compases", "repeticion",
                  "cuenta_atras_restante_s", "factor_tempo", "tempo_efectivo",
                  "en_bucle", "en_pausa", "primer_compas", "ultimo_compas"):
        assert clave in datos, clave
    # Y los de la etapa 3a siguen donde estaban.
    for clave in ("instante_s", "indice_actual", "total", "completado", "tocadas",
                  "pausado", "arranque"):
        assert clave in datos, clave
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_app_estudio.py -q`
Expected: FAIL — 404 en los endpoints nuevos y `KeyError: 'compas_en_curso'`.

- [ ] **Step 3: Implementa el servidor**

En `servidor/piezas.py`:

```python
from nucleo.piezas.estudio import HistorialDeEstudio, PlanDePasada, SesionDeEstudio
```

- `self._seguidor: SeguidorPieza | None` pasa a `self._estudio: SesionDeEstudio | None`, y `activa` mira `self._estudio is not None`.
- En `__init__`, añade el historial por pieza:

```python
        # Un historial por NOMBRE de pieza, porque el historial tiene que
        # sobrevivir a empezar otra pasada de la misma cancion: es justo para eso.
        # Se vacia al apagar el servidor, que es la decision del usuario.
        #
        # La clave es el nombre y no la pieza entera: dos canciones distintas que
        # se llamen igual comparten historial. Es un empate declarado, y el precio
        # de equivocarse es un "fallas el 19" de otra cancion, no un dato perdido.
        self._historiales: dict[str, HistorialDeEstudio] = {}
```

- `iniciar(self, pieza, plan=None)`: igual que hoy, más
  ```python
                self._estudio = SesionDeEstudio(pieza, plan or PlanDePasada())
                self._historial = self._historiales.setdefault(
                    pieza.nombre, HistorialDeEstudio()
                )
  ```
  y el `self._instante = 0.0` de hoy pasa a `self._instante = self._estudio.estado.carril.instante_s`, porque con un plan que empieza en el compás 5 el cabezal **no** arranca en cero. `SesionDeEstudio` lanza `ValueError` con un plan imposible, y `iniciar_pieza` ya traduce `ValueError` a 400.

- En `_mirar`, `_observar` y `_instantanea`, cambia `seguidor` por `estudio` y **adopta el reloj** tras cada llamada. En `_instantanea`:

```python
        sin_cuadros = self._sin_cuadros(ahora)
        estado = estudio.avanzar_a(self._instante) if sin_cuadros else estudio.estado
        # El reloj de la sesion de estudio es la verdad: ella congela durante la
        # cuenta atras y da la vuelta al bucle, asi que esta clase adopta lo que
        # ella diga en vez de llevar su propia cuenta. Sin esto, el cabezal
        # saltaba hacia delante al acabar cada cuenta atras.
        self._instante = estado.carril.instante_s
        self._cerrar_lo_que_termino(estado)
        return {**estado.a_dict(), "pausado": self._pausado, "arranque": self._arranque}
```

- El detector de final, que es quien alimenta el historial y el tempo automático:

```python
    def _cerrar_lo_que_termino(self, estado) -> None:
        """Anota en el historial lo que acabo de cerrarse, y mueve el tempo si toca.

        Se llama BAJO candado, desde la instantanea, porque es ahi donde se ve el
        estado nuevo. Lo que mira son dos transiciones, y hacen falta las dos:

        - Cambio de `repeticion`: estudiando un bucle, la pregunta "¿ya te sale?"
          es sobre la vuelta que acaba de pasar, asi que cada vuelta es una
          pasada del historial.
        - `tramo_terminado` de False a True: sin bucle, la pasada acaba una vez.

        `cerrar_repeticion` devuelve el informe de SOLO esa vuelta, que es lo que
        se anota: anotar el acumulado contaria las vueltas anteriores otra vez.
        """
        estudio = self._estudio
        if estudio is None:
            return
        termino = estado.tramo_terminado and not self._termino_anunciado
        dio_la_vuelta = estado.repeticion != self._repeticion_anunciada
        if not termino and not dio_la_vuelta:
            return
        self._termino_anunciado = estado.tramo_terminado
        self._repeticion_anunciada = estado.repeticion
        # Al dar la vuelta, `_dar_la_vuelta` ya cerro la repeticion por dentro y
        # su informe se perdio: lo que se anota aqui es lo que el estudio tenga
        # cerrado. Por eso `SesionDeEstudio._dar_la_vuelta` guarda el informe de
        # la vuelta en `self._ultima_vuelta`, y aqui se lee.
        informe = estudio.ultima_vuelta if dio_la_vuelta else estudio.cerrar_repeticion()
        if informe is None:
            return
        self._historial.anotar(informe)
        if estudio.plan.tempo_automatico:
            sugerido = self._historial.factor_sugerido(estudio.plan.factor_tempo)
            if sugerido != estudio.plan.factor_tempo:
                from dataclasses import replace

                estudio.cambiar_plan(replace(estudio.plan, factor_tempo=sugerido))
```

  `_ultima_vuelta` ya lo guarda `_dar_la_vuelta` (Tarea 5); lo que falta es **publicarlo**: añade a `SesionDeEstudio` una propiedad `ultima_vuelta: InformeDePasada | None` que lo devuelva, y esta prueba en `tests/test_estudio.py`:

```python
def test_la_ultima_vuelta_guarda_el_informe_de_la_repeticion_que_acabo():
    sesion = SesionDeEstudio(
        pieza_de_doce_compases(),
        PlanDePasada(primer_compas=1, ultimo_compas=1, en_bucle=True,
                     compases_de_cuenta_atras=0),
    )
    assert sesion.ultima_vuelta is None
    tocar(sesion, "E2", en=0.0)
    sesion.avanzar_a(4.0)
    assert compas_numero(sesion.ultima_vuelta, 1).acertadas == 1
```

  Y en `__init__` de `SesionCarril`, las dos marcas: `self._termino_anunciado = False` y `self._repeticion_anunciada = 1`, que se reinician en `iniciar` y en `detener`.

- Los métodos nuevos, todos con el mismo molde (candado, estudio o `ValueError`):

```python
    def _estudio_o_falla(self) -> SesionDeEstudio:
        estudio = self._estudio
        if estudio is None:
            raise ValueError("No hay ninguna pieza en marcha que practicar")
        return estudio

    def cambiar_plan(self, plan: PlanDePasada) -> dict:
        with self._candado:
            self._estudio_o_falla().cambiar_plan(plan)
        return self.estado()

    def saltar(self, numero: int) -> dict:
        with self._candado:
            self._estudio_o_falla().saltar_al_compas(numero)
        return self.estado()

    def pausa(self, activa: bool) -> dict:
        """Pausa a voluntad del usuario. Explicita y no un interruptor: dos clics
        seguidos desde dos pestañas no pueden dejar el carril en el estado
        contrario al que las dos pidieron."""
        with self._candado:
            estudio = self._estudio_o_falla()
            estudio.pausar() if activa else estudio.reanudar()
        return self.estado()

    def informe(self) -> dict:
        with self._candado:
            estudio = self._estudio_o_falla()
            return {
                "informe": estudio.informe.a_dict(),
                "historial": self._historial.a_dict(),
            }

    def _secciones_en_compases(self, pieza: Pieza) -> list[dict]:
        """Las secciones de la pieza, ya convertidas en rangos de compases.

        La conversion es del NUCLEO (`compases_de_la_seccion`) y viaja hecha: la
        interfaz no repite la formula. Es la misma regla que la etapa 2a aplico
        cuatro veces con el umbral de los cents, y aqui ademas el dia que el
        compas variable se arregle habria que arreglarlo en dos idiomas.
        """
        return [
            {
                "nombre": seccion.nombre,
                "primer_compas": compases_de_la_seccion(pieza, indice)[0],
                "ultimo_compas": compases_de_la_seccion(pieza, indice)[1],
            }
            for indice, seccion in enumerate(pieza.secciones)
        ]

    def pieza_en_marcha(self) -> dict:
        """La pieza que suena ahora, para quien recargo el navegador.

        `pieza` vale None sin nada en marcha, y NO es un error: el navegador que
        arranca de cero pregunta y se encuentra con que no hay nada, que es una
        respuesta.
        """
        pieza = self._pieza
        return {
            "pieza": None if pieza is None else pieza.a_dict(),
            "secciones_en_compases": (
                [] if pieza is None else self._secciones_en_compases(pieza)
            ),
            **self.estado(),
        }
```

Y el `return` de `iniciar` pasa a llevarlas también:

```python
        return {
            "pieza": pieza.a_dict(),
            "secciones_en_compases": self._secciones_en_compases(pieza),
            **self.estado(),
        }
```

con `from nucleo.piezas.compases import compases_de_la_seccion` arriba.

En `servidor/app.py`, un ayudante y los cinco endpoints:

```python
    def _plan_pedido(datos: dict) -> PlanDePasada:
        """Construye el plan del cuerpo de la peticion.

        `PlanDePasada` valida lo suyo y lanza `ValueError`; el llamador lo
        traduce a 400, igual que ya hace `iniciar_pieza` con la afinacion.
        """
        return PlanDePasada(
            primer_compas=int(datos.get("primer_compas", 1)),
            ultimo_compas=(
                None if datos.get("ultimo_compas") is None else int(datos["ultimo_compas"])
            ),
            factor_tempo=float(datos.get("factor_tempo", 1.0)),
            en_bucle=bool(datos.get("en_bucle", False)),
            compases_de_cuenta_atras=int(datos.get("compases_de_cuenta_atras", 1)),
            con_click=bool(datos.get("con_click", False)),
            tempo_automatico=bool(datos.get("tempo_automatico", False)),
        )

    @app.post("/api/piezas/plan")
    def cambiar_plan_pieza(datos: dict = Body(...)) -> dict:
        try:
            return app.state.carril.cambiar_plan(_plan_pedido(datos))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.post("/api/piezas/saltar")
    def saltar_de_compas(datos: dict = Body(...)) -> dict:
        try:
            return app.state.carril.saltar(int(datos["compas"]))
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error) or "Falta el compas")

    @app.post("/api/piezas/pausa")
    def pausar_pieza(datos: dict = Body(...)) -> dict:
        try:
            return app.state.carril.pausa(bool(datos.get("activa", True)))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.get("/api/piezas/informe")
    def leer_informe_pieza() -> dict:
        try:
            return app.state.carril.informe()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error))

    @app.get("/api/piezas/pieza")
    def leer_pieza_en_marcha() -> dict:
        """La pieza en marcha, para el navegador que se acaba de recargar."""
        return app.state.carril.pieza_en_marcha()
```

Y en `iniciar_pieza`, el plan opcional:

```python
        pieza = _pieza_para_el_carril(datos)
        plan = _plan_pedido(datos["plan"]) if datos.get("plan") else None
        try:
            return app.state.carril.iniciar(pieza, plan)
```

con el `try` cubriendo también la construcción del plan, para que un factor imposible salga 400 y no 500. Mueve la línea del plan dentro del `try`.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_app_estudio.py -q`
Expected: PASS, las 15 de esta tarea.

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS. `tests/test_app_carril.py` y `tests/test_piezas_sesion.py` tienen que seguir verdes **sin tocarlas**: si alguna cae, el plan por defecto no es equivalente a la etapa 3a y hay que arreglar eso, no la prueba.

- [ ] **Step 5: Rompe el código y cuenta**

Quita la línea `self._instante = estado.carril.instante_s` de `_instantanea` y corre la suite entera: si no cae nada, **falta una prueba**, y es esta — escríbela:

```python
def test_tras_la_cuenta_atras_el_cabezal_no_salta_hacia_delante(cliente):
    # El reloj del servidor no puede seguir corriendo durante la cuenta atras:
    # al acabarla, el cabezal saltaria el tamaño de la cuenta.
    iniciar(cliente, primer_compas=1, ultimo_compas=1, en_bucle=True)
    cliente.post("/api/piezas/saltar", json={"compas": 1})
    datos = cliente.get("/api/piezas/estado").json()
    assert datos["instante_s"] <= 1.0
```

Cambia `estado.repeticion != self._repeticion_anunciada` por `False` y corre: tiene que caer algo del historial; si no, falta la prueba de que una vuelta del bucle suma una pasada. **Apunta las cifras.**

- [ ] **Step 6: Commit**

```bash
git add servidor/piezas.py servidor/app.py nucleo/piezas/estudio.py tests/test_app_estudio.py tests/test_estudio.py
git commit -m "$(cat <<'FIN'
feat: el carril sostiene la sesion de estudio y abre los cinco endpoints

El reloj de la sesion de estudio es la verdad y el servidor lo adopta: sin eso,
el cabezal saltaba hacia delante al acabar cada cuenta atras.

Las dos pausas son distintas: pausado es la falta de senal y la decide el
servidor; en_pausa la decide el usuario. El estado publica las dos.

GET /api/piezas/pieza cierra la deuda de la etapa 3a: recargar el navegador a
mitad de cancion dejaba el carril en blanco.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 8: el click de metrónomo en el carril

**Files:**
- Modify: `servidor/piezas.py`
- Test: `tests/test_app_estudio.py` (se añade)

**Interfaces:**
- Consumes: `nucleo.sintesis.{Metronomo, SalidaAudio, TEMPO_MAXIMO_PPM}`; `EstadoEstudio.repeticion`.
- Produces: `SesionCarril(sesion_audio, reloj=..., perfil_activo=..., salida: SalidaAudio | None = None)`; el estado gana `click_sonando: bool`.

**El patrón ya existe**: `SesionPractica.__init__(self, sesion_audio, salida: SalidaAudio | None = None)` en `servidor/ejercicios.py`, y las pruebas le pasan una `SalidaAudio` de mentira. Cópialo, no lo inventes. `Metronomo(tempo, compas)` ya acentúa el primer tiempo del compás que le digas y ya tiene `pausar`/`reanudar` sin bloquear el hilo de análisis.

**Cuatro cosas, y las cuatro están en la spec:**

1. `tempo = round(pieza.tempo * factor)` y `compas = pieza.compas[0]`. Si el tempo redondeado sale por encima de `TEMPO_MAXIMO_PPM` o por debajo de 1, el `Metronomo` lo rechaza con `ValueError`: eso **no** puede tumbar la pasada, se queda sin click y el estado lo dice.
2. `iniciar()` devuelve `False` si no hay salida de audio: entonces `click_sonando` es `False` y la interfaz escribe «sin click» en vez de mostrar un interruptor encendido que no suena. Es el mismo estándar que la etapa 2a aplicó al «Sin metrónomo» silencioso.
3. **Se rearranca en cada repetición**, mirando `estado.repeticion`: así la cuenta atrás se oye desde el principio y, de paso, la deriva del hilo del metrónomo se reinicia cada vuelta.
4. **Se pausa al perder la señal**, igual que `SesionPractica._ajustar_metronomo`: un click marcando el compás con el cable desenchufado es lo contrario de lo que pide la spec §5 de la etapa 2a.

- [ ] **Step 1: Escribe las pruebas que fallan**

Añade a `tests/test_app_estudio.py`:

```python
class SalidaFalsa:
    """Una salida que dice estar activa y se queda las muestras. Nunca abre audio."""

    frecuencia_muestreo = 48000

    def __init__(self) -> None:
        self.activa = True
        self.escrituras = 0

    def abrir(self) -> bool:
        return True

    def escribir(self, muestras) -> bool:
        self.escrituras += 1
        return True

    def cerrar(self) -> None:
        pass


class SalidaMuda(SalidaFalsa):
    """Como la anterior, pero sin dispositivo: `activa` es False."""

    def __init__(self) -> None:
        super().__init__()
        self.activa = False


@pytest.fixture
def cliente_con_salida(tmp_path):
    """El mismo cliente, con una salida de audio de mentira que podemos mirar."""
    def construir(salida):
        sesion = Sesion(
            Configuracion(dispositivo=3),
            crear_captura=lambda **kw: CapturaFalsa(**kw),
            listar=lambda: [CABLE],
        )
        sesion.iniciar()
        carril = SesionCarril(sesion, salida=salida)
        app = crear_app(sesion, carril=carril)
        app.state.ruta_config = tmp_path / "config.json"
        return sesion, carril, app
    return construir


def test_con_click_el_estado_dice_que_suena(cliente_con_salida):
    sesion, carril, app = cliente_con_salida(SalidaFalsa())
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        datos = iniciar(cliente, con_click=True).json()
        assert datos["click_sonando"] is True
    carril.detener()
    sesion.detener()


def test_sin_salida_de_audio_el_click_no_miente(cliente_con_salida):
    # El interruptor estaba pedido, pero no hay dispositivo: el estado dice que
    # NO suena, para que la interfaz pueda escribir "sin click" en vez de
    # mostrar un interruptor encendido que no hace nada.
    sesion, carril, app = cliente_con_salida(SalidaMuda())
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        datos = iniciar(cliente, con_click=True).json()
        assert datos["click_sonando"] is False
    carril.detener()
    sesion.detener()


def test_sin_pedir_click_no_suena(cliente_con_salida):
    sesion, carril, app = cliente_con_salida(SalidaFalsa())
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        assert iniciar(cliente).json()["click_sonando"] is False
    carril.detener()
    sesion.detener()


def test_apagar_el_click_desde_el_plan_lo_para(cliente_con_salida):
    sesion, carril, app = cliente_con_salida(SalidaFalsa())
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        iniciar(cliente, con_click=True)
        datos = cliente.post("/api/piezas/plan", json={"con_click": False}).json()
        assert datos["click_sonando"] is False
    carril.detener()
    sesion.detener()


def test_un_tempo_que_el_metronomo_no_acepta_deja_la_pasada_en_pie(cliente_con_salida):
    # 400 ppm esta por encima de TEMPO_MAXIMO_PPM: el Metronomo lo rechaza. La
    # pasada no se cae, solo se queda sin click.
    sesion, carril, app = cliente_con_salida(SalidaFalsa())
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        pieza = pieza_de_doce_compases()
        pieza["tempo"] = 400
        respuesta = cliente.post(
            "/api/piezas/iniciar", json={"pieza": pieza, "plan": {"con_click": True}}
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["click_sonando"] is False
    carril.detener()
    sesion.detener()


def test_detener_la_pieza_para_el_click(cliente_con_salida):
    sesion, carril, app = cliente_con_salida(SalidaFalsa())
    with TestClient(app, base_url=BASE_LOCAL) as cliente:
        iniciar(cliente, con_click=True)
        assert cliente.post("/api/piezas/detener").json()["click_sonando"] is False
    carril.detener()
    sesion.detener()
```

- [ ] **Step 2: Comprueba que fallan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_app_estudio.py -q -k click`
Expected: FAIL — `TypeError: unexpected keyword argument 'salida'` y `KeyError: 'click_sonando'`.

- [ ] **Step 3: Implementa**

```python
from nucleo.sintesis import Metronomo, SalidaAudio
```

En `__init__`: `self._salida = salida or SalidaAudio()` y `self._metronomo: Metronomo | None = None`.

```python
    def _ajustar_click(self, estado) -> None:
        """Arranca, para o rearranca el click segun el plan y la señal. BAJO candado.

        Rearranca en cada repeticion (`estado.repeticion`) por dos razones: la
        cuenta atras tiene que oirse desde su primer pulso, y el hilo del
        metronomo lleva su propio reloj con esperas de 60/tempo, asi que cada
        rearranque borra la deriva acumulada respecto al carril.

        Un tempo que el metronomo no acepta -por encima de TEMPO_MAXIMO_PPM-
        deja la pasada sin click y en pie: tumbarla por el metronomo seria
        cambiar un lujo por lo esencial.
        """
        estudio = self._estudio
        if estudio is None or not estudio.plan.con_click:
            self._parar_click()
            return
        hace_falta_rearrancar = (
            self._metronomo is None
            or self._tempo_del_click != round(self.pieza.tempo * estudio.plan.factor_tempo)
            or self._repeticion_del_click != estado.repeticion
        )
        if hace_falta_rearrancar:
            self._parar_click()
            tempo = round(self.pieza.tempo * estudio.plan.factor_tempo)
            try:
                metronomo = Metronomo(tempo, self.pieza.compas[0], self._salida)
            except ValueError:
                return
            if not metronomo.iniciar():
                return
            self._metronomo = metronomo
            self._tempo_del_click = tempo
            self._repeticion_del_click = estado.repeticion
        if self._metronomo is not None:
            self._metronomo.pausar() if self._pausado else self._metronomo.reanudar()

    def _parar_click(self) -> None:
        if self._metronomo is not None:
            self._metronomo.detener()
        self._metronomo = None
        self._tempo_del_click = None
        self._repeticion_del_click = None
```

`_ajustar_click` se llama desde `_instantanea`, junto a `_cerrar_lo_que_termino`, y `_parar_click` desde `detener`. El estado publica `"click_sonando": self._metronomo is not None and self._metronomo.sonando`.

**Dónde NO llamarlo:** no lo llames desde `_observar`. Corre en el hilo de análisis, y `Metronomo.detener()` hace `join(timeout=1.0)`: bloquear ahí hasta un segundo cegaría la detección de ataques, que es exactamente lo que el docstring de `Metronomo.pausar` explica. La instantanea la llama el hilo HTTP/WS a 30 Hz, que es donde esto puede costar tiempo sin romper nada.

- [ ] **Step 4: Comprueba que pasan**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_app_estudio.py -q`
Expected: PASS, las 13 de la Tarea 7 más las 6 de esta.

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS, y ni una prueba abre el dispositivo real.

- [ ] **Step 5: Rompe el código y cuenta**

Quita el `if not metronomo.iniciar(): return` y corre: tiene que caer la de la salida muda. Quita `self._repeticion_del_click != estado.repeticion` de la condición y comprueba si cae algo: si no, **falta la prueba** de que el click se rearranca al dar la vuelta el bucle, y la escribes mirando `SalidaFalsa.escrituras`. Devuelve los cambios y **apunta las cifras**.

- [ ] **Step 6: Commit**

```bash
git add servidor/piezas.py tests/test_app_estudio.py
git commit -m "$(cat <<'FIN'
feat: el click de metronomo en el carril, sin mentir cuando no suena

Rearranca en cada repeticion -la cuenta atras tiene que oirse desde su primer
pulso, y de paso borra la deriva del hilo-, se pausa al perder la senal, y si
no hay salida de audio el estado dice click_sonando: false en vez de mostrar
un interruptor encendido que no hace nada.

Se ajusta desde la instantanea y NO desde el observador: detener() hace un
join de hasta un segundo y eso cegaria la deteccion de ataques.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 9: los tipos y la rejilla de compases

**Files:**
- Modify: `interfaz/src/tiposPieza.ts`
- Create: `interfaz/src/tiposEstudio.ts`
- Create: `interfaz/src/RejillaCompases.tsx`
- Create: `interfaz/src/RejillaCompases.test.tsx`
- Modify: `interfaz/src/estilos.css`
- Test: `interfaz/src/RejillaCompases.test.tsx`

**Interfaces:**
- Consumes: el `a_dict()` de `EstadoEstudio` (Tarea 3) y de `InformeDePasada` (Tarea 4).
- Produces:
  ```ts
  // tiposEstudio.ts
  // Espejo del paquete del WebSocket: el `a_dict()` de `EstadoEstudio` MAS lo que
  // el servidor le añade encima (`pausado`, `arranque`, `click_sonando`), que es
  // por lo que extiende `EstadoCarril` en vez de repetir sus campos.
  export interface EstadoEstudio extends EstadoCarril {
    instante_pulsos: number; compas_en_curso: number; total_de_compases: number;
    primer_compas: number; ultimo_compas: number; repeticion: number;
    cuenta_atras_restante_s: number; factor_tempo: number; tempo_efectivo: number;
    en_bucle: boolean; en_pausa: boolean; compas_variable: boolean;
    ritmo_aproximado: boolean; click_sonando: boolean;
  }
  export interface Plan { primer_compas?: number; ultimo_compas?: number | null;
    factor_tempo?: number; en_bucle?: boolean; compases_de_cuenta_atras?: number;
    con_click?: boolean; tempo_automatico?: boolean; }
  export interface CompasDelInforme { numero: number; notas_escritas: number;
    notas_medibles: number; acertadas: number; a_tiempo: number; pronto: number;
    tarde: number; desfase_medio_s: number | null; tiene_acordes: boolean; }
  export interface Informe { compases: CompasDelInforme[]; ritmo_aproximado: boolean;
    compas_variable: boolean; factor_tempo: number; }
  export interface SeccionEnCompases { nombre: string; primer_compas: number; ultimo_compas: number; }
  export interface Historial { pasadas: number;
    peores_compases: { compas: number; falladas: number; contadas: number }[]; }

  // RejillaCompases.tsx
  export function RejillaCompases(props: {
    total: number; enCurso: number; primero: number; ultimo: number;
    compasVariable: boolean;
    alSaltar: (compas: number) => void;
    alMarcarRango: (primero: number, ultimo: number) => void;
  }): JSX.Element | null
  ```

**`tiposPieza.ts` recibe por fin los cinco campos que le faltan.** Su propio comentario dice que `secciones` «la va a consumir la etapa 3c, que es cuando toca declararla»: es ahora. Añade `secciones: { nombre: string; inicio_pulsos: number }[]`, `ritmo_aproximado: boolean`, `tempo_variable: boolean`, `compas_variable: boolean`, `casillas_de_repeticion: boolean`, y **cambia el comentario**: ya no es un espejo parcial por elección, es un espejo completo. Esto rompe los literales de `Canciones.test.tsx` y `VistaEscritaPieza.test.tsx`; arréglalos añadiendo los campos que falten (`secciones: []`, los cuatro booleanos a `false`), que es trabajo mecánico y es el precio ya anunciado.

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `interfaz/src/RejillaCompases.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RejillaCompases } from "./RejillaCompases";

function pintar(props = {}) {
  const alSaltar = vi.fn();
  const alMarcarRango = vi.fn();
  render(
    <RejillaCompases
      total={12}
      enCurso={3}
      primero={1}
      ultimo={12}
      compasVariable={false}
      alSaltar={alSaltar}
      alMarcarRango={alMarcarRango}
      {...props}
    />,
  );
  return { alSaltar, alMarcarRango };
}

describe("la rejilla de compases", () => {
  it("dibuja un compás por cada uno de la pieza", () => {
    pintar();
    expect(screen.getAllByRole("button")).toHaveLength(12);
  });

  it("marca el compás en curso y solo ese", () => {
    pintar({ enCurso: 3 });
    expect(screen.getByRole("button", { name: /compás 3/i })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(screen.getByRole("button", { name: /compás 4/i })).not.toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("pinta el rango del bucle encima", () => {
    pintar({ primero: 5, ultimo: 7 });
    for (const numero of [5, 6, 7]) {
      expect(screen.getByRole("button", { name: new RegExp(`compás ${numero}`, "i") }))
        .toHaveClass("en-el-bucle");
    }
    expect(screen.getByRole("button", { name: /compás 4/i })).not.toHaveClass("en-el-bucle");
  });

  it("un clic salta a ese compás", () => {
    const { alSaltar } = pintar();
    fireEvent.click(screen.getByRole("button", { name: /compás 9/i }));
    expect(alSaltar).toHaveBeenCalledWith(9);
  });

  it("arrastrar marca el rango, y lo marca en orden aunque se arrastre al revés", () => {
    const { alMarcarRango } = pintar();
    fireEvent.pointerDown(screen.getByRole("button", { name: /compás 8/i }));
    fireEvent.pointerEnter(screen.getByRole("button", { name: /compás 5/i }));
    fireEvent.pointerUp(screen.getByRole("button", { name: /compás 5/i }));
    expect(alMarcarRango).toHaveBeenCalledWith(5, 8);
  });

  it("un arrastre de un solo compás no se confunde con un clic", () => {
    // Soltar donde se empezó es un clic: salta, no marca un rango de uno.
    const { alSaltar, alMarcarRango } = pintar();
    const uno = screen.getByRole("button", { name: /compás 6/i });
    fireEvent.pointerDown(uno);
    fireEvent.pointerUp(uno);
    fireEvent.click(uno);
    expect(alSaltar).toHaveBeenCalledWith(6);
    expect(alMarcarRango).not.toHaveBeenCalled();
  });

  it("avisa cuando la pieza cambia de compás, porque las barras caen mal", () => {
    pintar({ compasVariable: true });
    expect(screen.getByText(/cambia de compás/i)).toBeInTheDocument();
  });

  it("una pieza sin compases no dibuja rejilla", () => {
    const { container } = render(
      <RejillaCompases
        total={0}
        enCurso={1}
        primero={1}
        ultimo={0}
        compasVariable={false}
        alSaltar={vi.fn()}
        alMarcarRango={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test RejillaCompases`
Expected: FAIL — no se puede resolver `./RejillaCompases`.

- [ ] **Step 3: Escribe el componente**

Crea `interfaz/src/RejillaCompases.tsx`:

```tsx
import { useRef, useState } from "react";

/**
 * Los compases de la pieza, para orientarse y para armar el bucle.
 *
 * Es un botón por compás y no un lienzo a propósito: lo que hace falta aquí es
 * poder pulsar y arrastrar, y un `<button>` ya trae el foco, el teclado y el
 * nombre accesible. El carril, que sí dibuja a 60 fps, es el lienzo.
 *
 * La diferencia entre un clic y un arrastre está en si se suelta donde se empezó:
 * soltar en el mismo compás es un clic -salta ahí- y soltar en otro es un rango.
 * Sin esa distinción, cada salto armaba además un bucle de un compás.
 */
export function RejillaCompases({
  total,
  enCurso,
  primero,
  ultimo,
  compasVariable,
  alSaltar,
  alMarcarRango,
}: {
  total: number;
  enCurso: number;
  primero: number;
  ultimo: number;
  compasVariable: boolean;
  alSaltar: (compas: number) => void;
  alMarcarRango: (primero: number, ultimo: number) => void;
}) {
  const arrastreDesde = useRef<number | null>(null);
  const [hasta, setHasta] = useState<number | null>(null);

  if (total === 0) return null;

  const compases = Array.from({ length: total }, (_, i) => i + 1);

  const soltar = (numero: number) => {
    const desde = arrastreDesde.current;
    arrastreDesde.current = null;
    setHasta(null);
    if (desde === null || desde === numero) return;
    alMarcarRango(Math.min(desde, numero), Math.max(desde, numero));
  };

  return (
    <div className="rejilla-compases">
      {compasVariable && (
        <p className="aviso-compases">
          Esta canción cambia de compás y solo se guardó el primero: las barras
          caen en el sitio equivocado desde el cambio hasta el final.
        </p>
      )}
      <div className="compases">
        {compases.map((numero) => {
          const dentro = numero >= primero && numero <= ultimo;
          const marcando =
            arrastreDesde.current !== null &&
            hasta !== null &&
            numero >= Math.min(arrastreDesde.current, hasta) &&
            numero <= Math.max(arrastreDesde.current, hasta);
          return (
            <button
              key={numero}
              className={[
                "compas",
                dentro ? "en-el-bucle" : "",
                marcando ? "marcando" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              aria-current={numero === enCurso ? "true" : undefined}
              aria-label={`Compás ${numero}`}
              onPointerDown={() => {
                arrastreDesde.current = numero;
                setHasta(numero);
              }}
              onPointerEnter={() => {
                if (arrastreDesde.current !== null) setHasta(numero);
              }}
              onPointerUp={() => soltar(numero)}
              onClick={() => alSaltar(numero)}
            >
              {numero}
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

En `estilos.css`, añade `.rejilla-compases`, `.compases` (una fila que envuelve), `.compas`, `.compas.en-el-bucle`, `.compas.marcando`, `.compas[aria-current="true"]` y `.aviso-compases`, en el mismo estilo que el resto del archivo.

**Y el `tempo_efectivo`**: en `Carril.tsx`, las dos llamadas de la línea 180-181 pasan de `pieza.tempo` a `tempoEfectivo` (el del estado, con `pieza.tempo` como valor de reserva mientras no haya llegado un paquete). Es lo que hace que al 50 % las notas viajen a la mitad de velocidad y cuadren con el reloj.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test` y `pnpm build` y `pnpm lint`
Expected: PASS las 8 nuevas, y las de `Canciones.test.tsx` y `VistaEscritaPieza.test.tsx` arregladas con los campos nuevos.

- [ ] **Step 5: Rompe el código y cuenta**

Quita la condición `desde === numero` de `soltar` y corre: tiene que caer la de «un arrastre de un solo compás no se confunde con un clic». Cambia `Math.min`/`Math.max` por `desde, numero` y corre: tiene que caer la del arrastre al revés. Devuelve los cambios y **apunta las cifras**.

- [ ] **Step 6: Commit**

```bash
git add interfaz/src/tiposPieza.ts interfaz/src/tiposEstudio.ts interfaz/src/RejillaCompases.tsx interfaz/src/RejillaCompases.test.tsx interfaz/src/estilos.css interfaz/src/Carril.tsx interfaz/src/Canciones.test.tsx interfaz/src/VistaEscritaPieza.test.tsx
git commit -m "$(cat <<'FIN'
feat: la rejilla de compases, y tiposPieza deja de ser un espejo parcial

Un boton por compas y no un lienzo: aqui hace falta pulsar y arrastrar, y un
button ya trae foco, teclado y nombre accesible. Soltar donde se empezo es un
clic y soltar en otro compas es un rango, para que cada salto no arme ademas
un bucle de un compas.

El carril dibuja con tempo_efectivo: al 50 % las notas viajan a la mitad.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 10: los controles de la pasada

**Files:**
- Create: `interfaz/src/ControlesEstudio.tsx`, `interfaz/src/ControlesEstudio.test.tsx`
- Modify: `interfaz/src/useCarril.ts` (las tres acciones nuevas)
- Modify: `interfaz/src/Carril.tsx`, `interfaz/src/estilos.css`

**Interfaces:**
- Consumes: `EstadoEstudio`, `Plan` (Tarea 9); `POST /api/piezas/{plan,saltar,pausa}` (Tarea 7).
- Produces:
  ```ts
  export function ControlesEstudio(props: {
    estado: EstadoEstudio;
    secciones: SeccionEnCompases[];
    alCambiarPlan: (plan: Plan) => void;
    alPausar: (activa: boolean) => void;
  }): JSX.Element
  // en useCarril: cambiarPlan(plan: Plan), saltar(compas: number), pausar(activa: boolean)
  ```

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `interfaz/src/ControlesEstudio.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ControlesEstudio } from "./ControlesEstudio";
import type { EstadoEstudio } from "./tiposEstudio";

const ESTADO: EstadoEstudio = {
  arranque: 1, instante_s: 0, indice_actual: 0, total: 12, completado: false,
  tocadas: [], pausado: false, instante_pulsos: 0, compas_en_curso: 1,
  total_de_compases: 12, primer_compas: 1, ultimo_compas: 12, repeticion: 1,
  cuenta_atras_restante_s: 0, factor_tempo: 1, tempo_efectivo: 60,
  en_bucle: false, en_pausa: false, compas_variable: false,
  ritmo_aproximado: false, click_sonando: false,
} as unknown as EstadoEstudio;

function pintar(estado: Partial<EstadoEstudio> = {}, secciones = []) {
  const alCambiarPlan = vi.fn();
  const alPausar = vi.fn();
  render(
    <ControlesEstudio
      estado={{ ...ESTADO, ...estado }}
      secciones={secciones}
      alCambiarPlan={alCambiarPlan}
      alPausar={alPausar}
    />,
  );
  return { alCambiarPlan, alPausar };
}

describe("los controles de la pasada", () => {
  it("el deslizador del tempo va del 40 % al 100 % en pasos del 5 %", () => {
    pintar();
    const tempo = screen.getByLabelText(/tempo/i);
    expect(tempo).toHaveAttribute("min", "40");
    expect(tempo).toHaveAttribute("max", "100");
    expect(tempo).toHaveAttribute("step", "5");
  });

  it("mover el tempo manda el factor, no el porcentaje", () => {
    const { alCambiarPlan } = pintar();
    fireEvent.change(screen.getByLabelText(/tempo/i), { target: { value: "70" } });
    expect(alCambiarPlan).toHaveBeenCalledWith({ factor_tempo: 0.7 });
  });

  it("enseña el tempo en pulsos por minuto además del porcentaje", () => {
    // Un 70 % no le dice nada a nadie; "42 ppm" sí.
    pintar({ factor_tempo: 0.7, tempo_efectivo: 42 });
    expect(screen.getByText(/42 ppm/)).toBeInTheDocument();
  });

  it("el interruptor del bucle manda en_bucle", () => {
    const { alCambiarPlan } = pintar();
    fireEvent.click(screen.getByLabelText(/bucle/i));
    expect(alCambiarPlan).toHaveBeenCalledWith({ en_bucle: true });
  });

  it("pausar y reanudar son la misma tecla con dos estados", () => {
    const { alPausar } = pintar({ en_pausa: false });
    fireEvent.click(screen.getByRole("button", { name: /pausar/i }));
    expect(alPausar).toHaveBeenCalledWith(true);
  });

  it("en pausa, el botón ofrece reanudar", () => {
    const { alPausar } = pintar({ en_pausa: true });
    fireEvent.click(screen.getByRole("button", { name: /reanudar/i }));
    expect(alPausar).toHaveBeenCalledWith(false);
  });

  it("si el click está pedido pero no suena, lo dice", () => {
    // No hay salida de audio: un interruptor encendido que no suena seria
    // mentir, y el servidor ya nos manda click_sonando en false.
    pintar({ click_sonando: false, en_bucle: false });
    fireEvent.click(screen.getByLabelText(/click/i));
    expect(screen.getByText(/sin click/i)).toBeInTheDocument();
  });

  it("la lista de secciones arma el bucle con la que elijas", () => {
    const { alCambiarPlan } = pintar({}, [
      { nombre: "Intro", primer_compas: 1, ultimo_compas: 4 },
      { nombre: "Estribillo", primer_compas: 5, ultimo_compas: 12 },
    ]);
    fireEvent.change(screen.getByLabelText(/sección/i), { target: { value: "1" } });
    expect(alCambiarPlan).toHaveBeenCalledWith({
      primer_compas: 5, ultimo_compas: 12, en_bucle: true,
    });
    // Los compases los calculó el núcleo: aquí solo se eligen de la lista.
  });

  it("sin secciones, la lista no aparece", () => {
    // Muchas tablaturas y MIDIs no traen marcadores: una lista vacía solo
    // estorba.
    pintar({}, []);
    expect(screen.queryByLabelText(/sección/i)).not.toBeInTheDocument();
  });

  it("la cuenta atrás se enseña en segundos enteros mientras corre", () => {
    pintar({ cuenta_atras_restante_s: 2.4 });
    expect(screen.getByText(/3/)).toBeInTheDocument();
  });

  it("enseña la repetición cuando hay bucle", () => {
    pintar({ en_bucle: true, repeticion: 4 });
    expect(screen.getByText(/repetición 4/i)).toBeInTheDocument();
  });
});
```

**La interfaz no convierte pulsos en compases.** Lo hace el núcleo (`compases_de_la_seccion`, Tarea 1) y lo publica el servidor: las respuestas de `iniciar` y de `GET /api/piezas/pieza` traen `secciones_en_compases: [{nombre, primer_compas, ultimo_compas}]` (Tarea 7). El componente recibe esa lista tal cual, así que `secciones` aquí es de ese tipo y no el `inicio_pulsos` del modelo. Es la misma regla que la etapa 2a aplicó cuatro veces: los veredictos y las cuentas los decide el núcleo, y una copia de la fórmula en TypeScript se desincroniza el día que el compás variable se arregle.

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test ControlesEstudio`
Expected: FAIL — no se puede resolver `./ControlesEstudio`.

- [ ] **Step 3: Escribe el componente y las acciones**

El componente: un `<input type="range" min=40 max=100 step=5>` cuyo `onChange` manda `{ factor_tempo: Number(valor) / 100 }`; tres `<input type="checkbox">` para bucle, click y tempo automático; un `<button>` que alterna entre «Pausar» y «Reanudar» llamando `alPausar(!estado.en_pausa)`; un `<select>` de secciones que solo se pinta si hay alguna; y las etiquetas de repetición, cuenta atrás (`Math.ceil`) y «sin click» cuando el interruptor está puesto y `click_sonando` es `false`.

En `useCarril.ts`, tres acciones con el mismo molde que las que ya hay, devueltas por el hook:

```ts
  /**
   * Cambia el plan de la pasada SIN reiniciarla. El estado nuevo llega por el
   * WebSocket como todo lo demás: esta función no lo guarda, solo lo pide, para
   * que no haya dos verdades sobre el plan vigente.
   */
  const cambiarPlan = useCallback(async (plan: Plan) => {
    await fetch("/api/piezas/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(plan),
    });
  }, []);
```

y las dos hermanas, `saltar` (`/api/piezas/saltar`, `{ compas }`) y `pausar` (`/api/piezas/pausa`, `{ activa }`). **Que no guarden estado local** es la decisión que importa: el plan vigente lo dice el servidor, y una copia en el navegador se desincroniza en cuanto el tempo automático lo mueva por su cuenta.

`Carril.tsx` monta `<ControlesEstudio>` y `<RejillaCompases>` con el estado del hook.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test` y `pnpm build` y `pnpm lint`
Expected: PASS.

- [ ] **Step 5: Rompe el código y cuenta**

Haz que el `onChange` del tempo mande `{ factor_tempo: Number(valor) }` (el porcentaje en vez del factor) y corre: tiene que caer la prueba del factor. Haz que la lista de secciones se pinte siempre y corre: tiene que caer la de «sin secciones no aparece». Devuelve los cambios y **apunta las cifras**.

- [ ] **Step 6: Commit**

```bash
git add interfaz/src/ControlesEstudio.tsx interfaz/src/ControlesEstudio.test.tsx interfaz/src/useCarril.ts interfaz/src/Carril.tsx interfaz/src/tiposEstudio.ts interfaz/src/estilos.css
git commit -m "$(cat <<'FIN'
feat: los controles de la pasada: tempo, bucle, click, automatico y pausa

El deslizador manda el factor y no el porcentaje, y ensena los ppm efectivos
porque un 70 % no le dice nada a nadie. Ninguna accion guarda estado local: el
plan vigente lo dice el servidor, y una copia aqui se desincronizaria en cuanto
el tempo automatico lo moviera.

La lista de secciones solo aparece si la cancion trae marcadores.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 11: el informe en pantalla, el botón de machacar, y las dos deudas

**Files:**
- Create: `interfaz/src/InformePasada.tsx`, `interfaz/src/InformePasada.test.tsx`
- Modify: `interfaz/src/Carril.tsx`, `interfaz/src/useCarril.ts`, `interfaz/src/Ejercicios.tsx`, `interfaz/src/estilos.css`
- Test: `interfaz/src/InformePasada.test.tsx`, `interfaz/src/Carril.test.tsx`

**Interfaces:**
- Consumes: `Informe`, `Historial`, `CompasDelInforme` (Tarea 9); `GET /api/piezas/informe` y `GET /api/piezas/pieza` (Tarea 7).
- Produces:
  ```ts
  export function InformePasada(props: {
    informe: Informe; historial: Historial;
    alMachacar: (compas: number) => void;
  }): JSX.Element
  ```

**Las dos deudas que esta tarea cierra**, y por qué aquí: con bucles y click dejan de ser invisibles.

1. **Recargar el navegador a mitad de canción deja el carril en blanco**, porque la pieza viaja una sola vez en la respuesta de `iniciar` (está escrito en `App.tsx`). Estudiando un bucle se recarga. `useCarril` pide `GET /api/piezas/pieza` al montar si no tiene pieza, y si la respuesta trae una, la adopta con su `arranque`.
2. **`POST /api/piezas/detener` no se llama al desmontar**: `useCarril.ts` cierra el WebSocket y se va. Hasta ahora era invisible; **con el click sonando, se queda sonando**. Se llama en la limpieza del efecto, en el carril y en los ejercicios (`Ejercicios.tsx` tiene la misma deuda con `/api/ejercicios/detener`).

- [ ] **Step 1: Escribe las pruebas que fallan**

Crea `interfaz/src/InformePasada.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InformePasada } from "./InformePasada";
import type { CompasDelInforme, Historial, Informe } from "./tiposEstudio";

function compas(numero: number, extra: Partial<CompasDelInforme> = {}): CompasDelInforme {
  return {
    numero, notas_escritas: 4, notas_medibles: 4, acertadas: 4, a_tiempo: 4,
    pronto: 0, tarde: 0, desfase_medio_s: 0.01, tiene_acordes: false, ...extra,
  };
}

function pintar(informe: Partial<Informe> = {}, historial: Partial<Historial> = {}) {
  const alMachacar = vi.fn();
  render(
    <InformePasada
      informe={{
        compases: [compas(1)], ritmo_aproximado: false, compas_variable: false,
        factor_tempo: 1, ...informe,
      }}
      historial={{ pasadas: 1, peores_compases: [], ...historial }}
      alMachacar={alMachacar}
    />,
  );
  return { alMachacar };
}

describe("el informe de la pasada", () => {
  it("enseña el desfase medio con signo y en milisegundos", () => {
    // "40 ms tarde" es un diagnostico; "fallas el 19" no lo es.
    pintar({ compases: [compas(19, { desfase_medio_s: 0.04 })] });
    expect(screen.getByText(/40 ms tarde/i)).toBeInTheDocument();
  });

  it("adelantarse se dice como adelantarse, no como un número negativo", () => {
    pintar({ compases: [compas(19, { desfase_medio_s: -0.04 })] });
    expect(screen.getByText(/40 ms pronto/i)).toBeInTheDocument();
  });

  it("un compás que nadie tocó no inventa un desfase", () => {
    pintar({ compases: [compas(4, { acertadas: 0, a_tiempo: 0, desfase_medio_s: null })] });
    expect(screen.queryByText(/ms/)).not.toBeInTheDocument();
  });

  it("explica los compases con acordes en vez de contarlos como fallados", () => {
    pintar({
      compases: [compas(7, { notas_escritas: 4, notas_medibles: 1, acertadas: 0, tiene_acordes: true })],
    });
    expect(screen.getByText(/solo se puede medir una nota de cada acorde/i)).toBeInTheDocument();
  });

  it("avisa arriba de que el ritmo es inventado", () => {
    pintar({ ritmo_aproximado: true });
    expect(screen.getByText(/el ritmo de esta pieza se dedujo/i)).toBeInTheDocument();
  });

  it("ofrece machacar los peores compases con sus cifras", () => {
    const { alMachacar } = pintar({}, {
      pasadas: 5,
      peores_compases: [{ compas: 19, falladas: 4, contadas: 5 }],
    });
    const boton = screen.getByRole("button", { name: /machacar el compás 19/i });
    expect(screen.getByText(/4 de 5/)).toBeInTheDocument();
    fireEvent.click(boton);
    expect(alMachacar).toHaveBeenCalledWith(19);
  });

  it("sin peores compases no ofrece machacar nada", () => {
    pintar({}, { pasadas: 3, peores_compases: [] });
    expect(screen.queryByRole("button", { name: /machacar/i })).not.toBeInTheDocument();
  });

  it("una pieza entera de acordes no deja el informe vacío sin explicación", () => {
    // El caso del .gp5 normal: si no se dice nada, el usuario ve una tabla a
    // ceros y cree que lo hizo todo mal.
    pintar({
      compases: [compas(1, { notas_medibles: 1, acertadas: 0, tiene_acordes: true })],
    }, { pasadas: 1, peores_compases: [] });
    expect(screen.getByText(/solo se puede medir una nota de cada acorde/i)).toBeInTheDocument();
  });
});
```

Y en `interfaz/src/Carril.test.tsx`, las dos deudas:

```tsx
it("pide la pieza en marcha al montar, para quien recargó el navegador", async () => {
  // La pieza viaja una sola vez en la respuesta de iniciar, asi que sin esto
  // recargar a mitad de cancion dejaba el carril en blanco.
  const llamadas: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    llamadas.push(String(url));
    return { ok: true, json: async () => ({ pieza: null }) } as Response;
  }));
  render(<Carril peticion={null} />);
  await waitFor(() => expect(llamadas).toContain("/api/piezas/pieza"));
});

it("detiene la pieza al desmontar, o el click se queda sonando", async () => {
  const llamadas: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    llamadas.push(String(url));
    return { ok: true, json: async () => ({ pieza: null }) } as Response;
  }));
  const { unmount } = render(<Carril peticion={null} />);
  unmount();
  await waitFor(() => expect(llamadas).toContain("/api/piezas/detener"));
});
```

Adapta estas dos a cómo `Carril.test.tsx` ya finge `fetch` y el WebSocket: **no inventes un doble nuevo si el archivo ya tiene uno**, úsalo.

- [ ] **Step 2: Comprueba que fallan**

Run: `cd interfaz && pnpm test InformePasada Carril`
Expected: FAIL — no se resuelve `./InformePasada`, y las dos deudas fallan porque nadie llama a esos dos endpoints.

- [ ] **Step 3: Escribe el componente y cierra las deudas**

`InformePasada.tsx`: una tabla con una fila por compás (número, acertadas de medibles, el desfase medio traducido a «40 ms tarde» / «40 ms pronto» con `Math.abs` y el signo convertido en palabra, y nada cuando es `null`), la explicación en los compases con acordes, los dos avisos en cabecera (ritmo aproximado y compás variable), y un botón «Machacar el compás N» por cada uno de los peores, con sus cifras.

En `useCarril.ts`:

```ts
  // La pieza en marcha, para quien acaba de recargar el navegador. Se pide una
  // sola vez al montar y SOLO si no tenemos pieza: quien llega desde `Canciones`
  // la trae en la respuesta de `iniciar`, y pedirla otra vez seria una peticion
  // de mas en el camino normal.
  useEffect(() => {
    if (pieza !== null) return;
    let vivo = true;
    fetch("/api/piezas/pieza")
      .then((r) => r.json())
      .then((datos) => {
        if (!vivo || datos.pieza === null) return;
        adoptarPieza(datos.pieza, datos.arranque);
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);
```

y en la limpieza del efecto que cierra el WebSocket, añade la llamada a detener:

```ts
      // Detener la pieza al desmontar. Hasta la etapa 3c esto era invisible -la
      // pieza seguia corriendo en el servidor hasta que el `iniciar` de la
      // siguiente la paraba-, pero con el click de metronomo se queda SONANDO.
      // `keepalive` para que la peticion sobreviva a la navegacion que la
      // provoco.
      fetch("/api/piezas/detener", { method: "POST", keepalive: true }).catch(() => {});
```

Lo mismo en `Ejercicios.tsx` con `/api/ejercicios/detener`, que tiene la misma deuda y el mismo metrónomo.

**Cuidado con el orden:** la limpieza tiene que cerrar el WebSocket **antes** de pedir el detener, como hace hoy, o el último paquete puede llegar después y volver a pintar una pieza ya detenida.

- [ ] **Step 4: Comprueba que pasan**

Run: `cd interfaz && pnpm test` y `pnpm build` y `pnpm lint`
Expected: PASS.

Run (la suite entera, que es lo que vale): `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Rompe el código y cuenta**

Quita el `keepalive` y comprueba si cae algo: probablemente no, y eso está bien —es una garantía del navegador que jsdom no modela—, así que **dilo en el informe** en vez de inventar una prueba que no prueba nada. Quita la llamada a `/api/piezas/detener` y corre: tiene que caer la de la deuda. Haz que el efecto pida la pieza siempre, incluso con pieza ya puesta, y comprueba si cae algo: si no, **falta la prueba** de que llegando desde `Canciones` no se pide de más, y la escribes. **Apunta las cifras.**

- [ ] **Step 6: Commit**

```bash
git add interfaz/src/InformePasada.tsx interfaz/src/InformePasada.test.tsx interfaz/src/Carril.tsx interfaz/src/Carril.test.tsx interfaz/src/useCarril.ts interfaz/src/Ejercicios.tsx interfaz/src/estilos.css
git commit -m "$(cat <<'FIN'
feat: el informe en pantalla, el boton de machacar, y las dos deudas cerradas

El desfase se dice en palabras -"40 ms tarde", "40 ms pronto"- porque un
numero con signo no es un diagnostico. Los compases con acordes se explican en
vez de contarse como fallados: en un .gp5 normal, una tabla a ceros sin
explicacion le hace creer al usuario que lo hizo todo mal.

Y las dos deudas de la etapa 3a: la pieza se puede volver a pedir al recargar,
y detener se llama al desmontar, porque con el click el carril se quedaba
sonando.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```

---

### Task 12: la documentación, y la promesa que `modelo.py` no debe hacer

**Files:**
- Modify: `nucleo/piezas/modelo.py` (solo el comentario de `casillas_de_repeticion`)
- Modify: `README.md`

**Interfaces:** ninguna. Es documentación, y va al final porque describe lo que las once tareas anteriores dejaron hecho.

- [ ] **Step 1: Corrige la promesa del modelo**

`nucleo/piezas/modelo.py`, en el comentario de `casillas_de_repeticion`, dice hoy:

> *Detectarlo y arreglarlo son dos cosas distintas -arreglarlo es la etapa 3c- y esta es la primera, que es la que cumple el estandar de la rama: si se detecta, se avisa.*

La etapa 3c **no** lo arregla: es un defecto de lectura de la 3b, no de práctica, y el usuario decidió que vaya a su propia etapa. Cambia esa frase por:

```python
    # La cancion traia casillas de primera y segunda vez y el expansor de
    # repeticiones no las entiende: se toca un trozo de mas. Detectarlo y
    # arreglarlo son dos cosas distintas, y esta es la primera, que es la que
    # cumple el estandar de la rama: si se detecta, se avisa. Arreglarlo es
    # rehacer el expansor de `desde_guitarpro.py` y NO es la etapa 3c (se
    # considero y se descarto: es un defecto de lectura, no de practica).
    casillas_de_repeticion: bool = False
```

- [ ] **Step 2: Escribe la etapa en el README**

Añade la sección de la etapa 3c donde están las anteriores, con el mismo tono. Lo que tiene que decir, y **solo** lo que se pueda comprobar en el código:

- Qué hace: compases a la vista, bucle por rango con cuenta atrás, tempo del 40 % al 100 % con click opcional, informe por compases y subida automática del tempo.
- Los cinco endpoints nuevos, con una línea cada uno.
- **Los tres límites declarados**, que no se esconden: en una pieza con `compas_variable` las barras caen mal desde el cambio (el modelo guarda un solo compás); en los compases con acordes solo se puede medir una nota de cada uno, porque el detector es monofónico; y el click puede derivar del carril en una pasada larga, aunque cada repetición del bucle lo rearranque.
- Que el historial dura lo que dure el servidor y no se guarda en disco.
- Que la pieza sonando de fondo **no** está: es la etapa siguiente.

**Ni una cifra que no hayas medido tú corriendo el comando.** En la etapa 3b hubo que sustituir un «98 %» que no era reproducible, y dos cifras equivocadas más. Si quieres poner el número de pruebas, córrelo y cópialo.

- [ ] **Step 3: Comprueba que no rompiste nada**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add README.md nucleo/piezas/modelo.py
git commit -m "$(cat <<'FIN'
docs: la etapa 3c en el README, y modelo.py deja de prometerla

El comentario de casillas_de_repeticion decia que arreglarlas era la etapa 3c.
No lo es: es un defecto de lectura de la 3b, y el usuario decidio que vaya a su
propia etapa. El aviso al usuario se queda, que es lo honesto.

El README dice los tres limites declarados: las barras con compas variable, la
nota unica medible por acorde, y la posible deriva del click.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
FIN
)"
```
