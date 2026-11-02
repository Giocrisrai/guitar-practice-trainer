# El gemelo digital de la sesión — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un guitarrista sintético que toca una `Pieza` con errores controlados y mete ese audio por la ruta real del cable, para que la cadena entera se verifique sin guitarra, y con él cerrar los defectos que la etapa 3c dejó aparcados.

**Architecture:** `nucleo/gemelo/` sintetiza cuerdas pulsadas (Karplus-Strong, numpy), las ordena en una interpretación con su verdad escrita de antemano, y las pasa por el `Analizador` y el `ConductorDeEstudio` reales a dos velocidades: tiempo virtual para la suite y tiempo real a través de `Sesion` y el servidor para la demostración. La política del estudio se extrae de `servidor/piezas.py` a `nucleo/piezas/conductor.py` para que el gemelo juzgue la política de verdad y no una copia.

**Tech Stack:** Python 3.13 (uv), numpy, pytest. Ninguna dependencia nueva. Interfaz: React + TypeScript (pnpm, vitest) solo en la Tarea 15.

**Spec:** `docs/superpowers/specs/2026-11-02-gemelo-digital-design.md`

## Global Constraints

- **Idioma español** en comentarios, variables, funciones, clases y nombres de prueba. El Python va **sin tildes** (las eñes sí: no es ASCII puro). Los documentos y los mensajes de la interfaz sí llevan tildes.
- **`uv`**, nunca `pip install`. En este entorno hace falta `UV_CACHE_DIR="$TMPDIR/uv-cache"`. **`pnpm`**, nunca npm.
- **Ninguna dependencia nueva** de ejecución ni de desarrollo. `httpx` está solo en `dev`: `herramientas/gemelo.py` usa `urllib.request`.
- Preferir numpy/scipy sobre implementaciones manuales. Pruebas con pytest.
- **`nucleo/` no importa de `servidor/` ni de `interfaz/`.** `nucleo/piezas/modelo.py` no importa de `nucleo/ejercicios/`. `nucleo/gemelo/` puede importar de `nucleo/piezas/` y `nucleo/analisis/`.
- **`nucleo/` no abre audio.** El click se queda en el servidor, enganchado a `al_cambiar_repeticion`.
- **Ningún archivo con derechos de autor entra al repositorio.** Las piezas de prueba y la de demostración se construyen en código. `canciones/` no debe existir en la raíz tras la suite.
- **Ninguna prueba abre el dispositivo de audio real.**
- Puerto 8420.
- Ventana de análisis: `perfil.tamano_ventana(fs)` = 4096 muestras con guitarra estándar a 48 kHz. Cadencia: `INTERVALO_ANALISIS = 0.021` s = 1008 muestras de salto. No se usan otros valores.
- `VENTANA_ATAQUE_COMO_ONSET_S = 0.25`, `ESPERA_ESTABILIZACION_S = 0.060`, `CUADROS_PARA_NOTA_ESTABLE = 3`, `TECHO_TRAMO_S = 0.100`. Son de producción: ninguna tarea los cambia.
- Atribución de cada commit:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01UFZ4N9AgEgdhaVjnDEERDZ
  ```

## Review Focus

Las cinco cosas que la spec implica, que ninguna tarea cubriría por su cuenta, y que más probablemente muerden a quien use esto. Cada una lleva su prueba a la tarea que posee el código.

1. **Una pieza sin notas, o un tramo sin notas dentro de una pieza con notas.** `interpretar` tiene que devolver una interpretación válida con audio de silencio y cero eventos, no reventar ni devolver un array vacío que luego rompa el troceado. → Tarea 2.
2. **La misma semilla tiene que dar la misma interpretación, y dos semillas distintas no.** Sin esto el gemelo no es reproducible y un fallo no se puede volver a provocar, que es la mitad de su valor. → Tarea 2.
3. **El audio se acaba en mitad de una vuelta del bucle.** Es lo normal: el usuario para. La cadena no debe inventarse la vuelta que no terminó ni contarla en el historial. → Tarea 7.
4. **Dos notas consecutivas de la misma altura.** El detector declara que no las distingue; el veredicto tiene que EXCLUIRLAS, no contarlas como perdidas, o el oráculo sale rojo por una limitación aceptada. → Tarea 5.
5. **El factor de tempo en su extremo (0,40).** La ventana de acierto se escala con el tempo y el bucle da vueltas más largas; el arrastre del reloj y el aplazamiento del final tienen que seguir correctos ahí, no solo al 100 %. → Tarea 7.

---

## Estructura de archivos

**Se crean:**

| Archivo | Responsabilidad |
|---|---|
| `nucleo/gemelo/__init__.py` | Vacío. |
| `nucleo/gemelo/cuerda.py` | Una cuerda pulsada: `cuerda_pulsada`. Nada más. |
| `nucleo/gemelo/perfiles.py` | `PerfilDeDestreza` y los cuatro de fábrica. |
| `nucleo/gemelo/interprete.py` | `EventoTocado`, `Interpretacion`, `interpretar`. |
| `nucleo/gemelo/dispositivo.py` | `StreamSimulado`, `dispositivo_simulado`. |
| `nucleo/gemelo/cadena.py` | `ReporteDeLaCadena`, `RegistroDeLaCadena`, `pasar_por_la_cadena`. |
| `nucleo/gemelo/veredicto.py` | `Veredicto`, `juzgar`. |
| `nucleo/gemelo/piezas_de_prueba.py` | Las piezas construidas en código que usan la suite y la demostración. |
| `nucleo/piezas/conductor.py` | `ConductorDeEstudio`: la política del reloj y del cierre de vueltas, extraída del servidor. |
| `herramientas/gemelo.py` | El ejecutable del escaparate. |

**Se modifican:** `servidor/piezas.py` (usa el conductor), `nucleo/piezas/estudio.py` (los arreglos del bucle), `nucleo/piezas/seguimiento.py` (solo si la Tarea 7 lo exige), `nucleo/piezas/modelo.py` (docstring de `Seccion`), `interfaz/src/RejillaCompases.tsx`, `interfaz/src/ControlesEstudio.tsx`, `README.md`.

---

## Task 1: La cuerda pulsada

**Files:**
- Create: `nucleo/gemelo/__init__.py`, `nucleo/gemelo/cuerda.py`
- Test: `tests/test_gemelo_cuerda.py`

**Interfaces:**
- Consumes: `nucleo.afinaciones.PERFILES`, `nucleo.analisis.pipeline.Analizador` (solo en las pruebas).
- Produces:
  ```python
  def cuerda_pulsada(
      midi: int,
      duracion_s: float,
      frecuencia_muestreo: int = 48000,
      brillo: float = 0.5,
      fuerza: float = 0.8,
      trasteo: float = 0.0,
      semilla: int | None = None,
  ) -> np.ndarray   # float32, mono, longitud int(duracion_s * fs)
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_la_cuerda_suena_a_la_altura_pedida():
    # Para cada midi de [40, 45, 50, 55, 59, 64, 67, 72]: el Analizador real
    # recorre la onda en ventanas de perfil.tamano_ventana(48000) con salto 1008
    # y mas del 90% de las ventanas con estado "nota" dan el nombre esperado.

def test_la_cuerda_decae():
    # La energia RMS del ultimo quinto de la onda es menor que la del primer
    # quinto. Una senoide con envolvente plana pasaria todo lo demas y esto no.

def test_el_brillo_alto_conserva_mas_agudos_que_el_bajo():
    # Mismo midi y misma semilla con brillo=0.9 y brillo=0.1: el centroide
    # espectral (numpy.fft.rfft) del segundo quinto de la onda es mayor con 0.9.

def test_la_fuerza_es_la_amplitud_de_pico():
    # np.max(np.abs(onda)) == pytest.approx(fuerza, abs=1e-6) para fuerza 0.3 y 0.9.

def test_la_misma_semilla_da_la_misma_onda():
    # Dos llamadas con semilla=7 son identicas byte a byte (np.array_equal);
    # con semilla=8 no lo son.

def test_el_trasteo_ensucia_la_nota():
    # Con trasteo=0.8 la proporcion de ventanas que dan el nombre esperado es
    # MENOR que con trasteo=0.0, para el mismo midi y la misma semilla.

def test_la_duracion_es_la_pedida():
    # len(onda) == int(duracion_s * frecuencia_muestreo) para 0.1, 0.5 y 2.0 s.

def test_una_duracion_no_positiva_se_rechaza():
    # pytest.raises(ValueError) con duracion_s de 0.0 y de -1.0, y el mensaje
    # nombra el valor recibido.
```

- [ ] **Step 2: Run them and verify they fail**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_gemelo_cuerda.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'nucleo.gemelo'`

- [ ] **Step 3: Implement `cuerda_pulsada` in `nucleo/gemelo/cuerda.py`**

Karplus-Strong. Línea de retardo de `max(2, round(fs / f0))` muestras inicializada con ruido uniforme en `[-1, 1)` del generador `numpy.random.default_rng(semilla)`; en cada muestra se emite la posición actual y se reemplaza por la media ponderada de ella y la siguiente, con el peso derivado de `brillo` (0,5 es media simple; más brillo conserva más agudo). `f0` sale de `440.0 * 2 ** ((midi - 69) / 12)`. `trasteo` añade ruido blanco escalado y acorta el decaimiento. Al final se normaliza al pico `fuerza`.

El bucle muestra a muestra en Python es demasiado lento para la suite (una nota de 0,6 s son 29 000 iteraciones y la suite genera miles de notas): vectorizar por periodos con `scipy.signal.lfilter` sobre la línea de retardo, o generar el ruido una vez y aplicar el filtro de peine con `lfilter`, que es la forma numpy/scipy de esto. **Medir**: una nota de 0,6 s tiene que costar menos de 5 ms.

- [ ] **Step 4: Run them and verify they pass**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_gemelo_cuerda.py -v`
Expected: PASS (8 pruebas)

- [ ] **Step 5: Rompe el código y di cuántas cayeron**

Introduce por turnos estos tres mutantes, corre la suite del archivo, anota cuántas pruebas caen con cada uno, y deshaz:
1. `brillo` ignorado (peso fijo 0.5).
2. La normalización al pico quitada.
3. `semilla` ignorada (generador sin semilla).

Un mutante que no mata ninguna prueba es un hueco: escribe la prueba que lo mata antes de seguir. Anota los tres números en el informe de la tarea.

- [ ] **Step 6: Commit**

```bash
git add nucleo/gemelo/__init__.py nucleo/gemelo/cuerda.py tests/test_gemelo_cuerda.py
git commit -m "feat: la cuerda pulsada del gemelo, reconocida por el detector real"
```

---

## Task 2: Los perfiles y el intérprete

**Files:**
- Create: `nucleo/gemelo/perfiles.py`, `nucleo/gemelo/interprete.py`, `nucleo/gemelo/piezas_de_prueba.py`
- Test: `tests/test_gemelo_interprete.py`

**Interfaces:**
- Consumes: `cuerda_pulsada` (Tarea 1); `nucleo.piezas.modelo.{Pieza, NotaEnPieza, pulsos_a_segundos}`; `nucleo.piezas.compases.{pulsos_por_compas, total_de_compases}`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class PerfilDeDestreza:
      nombre: str
      desfase_medio_s: float
      desviacion_desfase_s: float
      probabilidad_de_fallo: float
      probabilidad_de_nota_mala: float
      probabilidad_de_trasteo: float
      cents_de_desafinacion: float
      fuerza_media: float
      desviacion_fuerza: float
      sustain: float          # 0 corta siempre, 1 deja sonar la figura entera

  PERFECTO: PerfilDeDestreza      # todo a cero, fuerza_media 0.8, sustain 0.0
  PRINCIPIANTE: PerfilDeDestreza
  INTERMEDIO: PerfilDeDestreza
  CAOS: PerfilDeDestreza          # sustain alto, para provocar los fantasmas
  PERFILES_DE_DESTREZA: dict[str, PerfilDeDestreza]   # por nombre, en minusculas

  @dataclass(frozen=True)
  class EventoTocado:
      indice_pretendido: int | None
      midi: int
      instante_s: float
      duracion_s: float
      cents: float
      trasteada: bool

  @dataclass(frozen=True)
  class Interpretacion:
      pieza: Pieza            # la pieza interpretada: la necesita `juzgar` para
                              # excluir acordes y notas repetidas (ruling previo 1)
      muestras: np.ndarray
      eventos: tuple[EventoTocado, ...]
      frecuencia_muestreo: int
      duracion_s: float
      silencio_de_cabecera_s: float

  def interpretar(
      pieza: Pieza,
      perfil: PerfilDeDestreza,
      factor_tempo: float = 1.0,
      primer_compas: int = 1,
      ultimo_compas: int | None = None,
      repeticiones: int = 1,
      segundos_de_cuenta_atras: float = 0.0,
      semilla: int = 0,
      frecuencia_muestreo: int = 48000,
  ) -> Interpretacion
  ```
  Y en `piezas_de_prueba.py`:
  ```python
  def escala_de_ocho_notas(tempo: int = 100) -> Pieza   # 8 notas, 2 compases de 4/4, una por pulso
  def pieza_con_acorde(tempo: int = 100) -> Pieza        # incluye dos notas en el mismo pulso
  def pieza_con_nota_repetida(tempo: int = 100) -> Pieza # dos notas consecutivas de la misma altura
  def pieza_vacia(tempo: int = 100) -> Pieza             # sin notas
  def pieza_de_demostracion(tempo: int = 92) -> Pieza    # ~30 s, cuatro secciones con nombre
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_el_perfecto_toca_cada_nota_en_su_instante():
    # escala_de_ocho_notas(), PERFECTO, factor 1.0: hay 8 eventos, sus
    # indice_pretendido son 0..7 en orden, y cada instante_s es
    # silencio_de_cabecera_s + i * pulsos_a_segundos(1.0, 100), con abs=1e-6.

def test_hay_silencio_de_cabecera_de_al_menos_una_ventana():
    # silencio_de_cabecera_s >= 4096 / 48000, y las muestras anteriores al
    # primer evento son todas cero.

def test_el_tramo_recorta_por_compases():
    # primer_compas=2, ultimo_compas=2 sobre la escala: 4 eventos, y sus
    # indice_pretendido son 4..7.

def test_las_repeticiones_repiten_el_tramo():
    # repeticiones=3 sobre un tramo de 4 notas: 12 eventos, y los
    # indice_pretendido vuelven a empezar en cada vuelta.

def test_la_cuenta_atras_mete_silencio_antes_de_cada_vuelta():
    # segundos_de_cuenta_atras=1.2 con repeticiones=2: el primer evento de la
    # segunda vuelta llega 1.2 s mas tarde de lo que llegaria sin cuenta atras.

def test_el_factor_de_tempo_estira_la_interpretacion():
    # factor 0.5: la distancia entre eventos consecutivos se duplica.

def test_el_acorde_se_reduce_a_la_nota_mas_grave():
    # pieza_con_acorde(): en el pulso del acorde hay UN evento, y su midi es el
    # menor de los dos escritos.

def test_una_nota_fallada_no_genera_evento():
    # probabilidad_de_fallo=1.0: eventos == (), y las muestras son todas cero.

def test_la_nota_mala_suena_a_otra_altura_pero_apunta_a_la_nota_escrita():
    # probabilidad_de_nota_mala=1.0: hay 8 eventos, cada indice_pretendido es el
    # suyo, y ningun midi coincide con el escrito; la diferencia esta en {1,2}
    # en valor absoluto.

def test_la_desafinacion_mueve_la_altura_de_verdad():
    # cents_de_desafinacion=40 con semilla fija: el Analizador real sobre el
    # audio da |cents| > 15 en la mayoria de las ventanas con nota, y el
    # EventoTocado.cents correspondiente tiene el mismo signo.

def test_el_interprete_no_solapa_dos_notas_consecutivas():
    # PERFECTO con sustain=0.0 sobre la escala: para cada par consecutivo,
    # evento.instante_s + evento.duracion_s <= siguiente.instante_s.

def test_el_sustain_alto_si_solapa():
    # El mismo con sustain=1.0: existe al menos un par donde no se cumple.

def test_una_pieza_sin_notas_da_una_interpretacion_de_silencio():
    # pieza_vacia(): eventos == (), muestras no vacias y todas cero,
    # duracion_s > 0. No lanza. (Review Focus 1.)

def test_un_tramo_sin_notas_da_una_interpretacion_de_silencio():
    # Una pieza cuyo compas 3 esta vacio, con primer_compas=3, ultimo_compas=3:
    # eventos == () y audio de la duracion del compas. (Review Focus 1.)

def test_la_misma_semilla_da_la_misma_interpretacion():
    # PRINCIPIANTE con semilla=5 dos veces: np.array_equal de las muestras y
    # eventos iguales. Con semilla=6, distintos. (Review Focus 2.)

def test_los_cuatro_perfiles_de_fabrica_estan_y_el_perfecto_no_falla_nada():
    # PERFILES_DE_DESTREZA tiene las cuatro claves en minusculas; PERFECTO
    # tiene probabilidad_de_fallo, probabilidad_de_nota_mala,
    # probabilidad_de_trasteo, desfase_medio_s, desviacion_desfase_s y
    # cents_de_desafinacion todos a 0.0.

def test_un_perfil_con_probabilidad_fuera_de_rango_se_rechaza():
    # pytest.raises(ValueError) construyendo PerfilDeDestreza con
    # probabilidad_de_fallo=1.5 y con -0.1, y el mensaje nombra el campo.
```

- [ ] **Step 2: Run them and verify they fail**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_gemelo_interprete.py -v`
Expected: FAIL por módulo inexistente.

- [ ] **Step 3: Implement the three modules**

`perfiles.py`: el dataclass con `__post_init__` que valida que las tres probabilidades están en `[0, 1]` y que `sustain` también, con el mensaje nombrando el campo; y los cuatro perfiles.

`interprete.py`: un único `numpy.random.default_rng(semilla)` para todo el azar. El orden de consumo del generador es parte del contrato de reproducibilidad: por cada nota del tramo, en orden, se consume fallo → nota mala → trasteo → desfase → desafinación → fuerza. La verdad (`eventos`) se construye **antes** de generar una sola muestra, y la generación la recorre. El buffer se dimensiona desde la duración total calculada y las ondas se suman con `+=` recortando al final del buffer.

`piezas_de_prueba.py`: las cinco piezas, construidas a mano con `NotaEnPieza`. `pieza_de_demostracion` lleva `Seccion`es con nombre, porque la demostración del escaparate practica por secciones.

- [ ] **Step 4: Run them and verify they pass**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_gemelo_interprete.py -v`
Expected: PASS (17 pruebas)

- [ ] **Step 5: Rompe el código y di cuántas cayeron**

Mutantes: (1) el silencio de cabecera a cero; (2) `factor_tempo` ignorado; (3) la verdad construida DESPUÉS del audio leyendo las muestras; (4) el acorde reducido a la nota más aguda. Anota las cuatro cuentas.

- [ ] **Step 6: Commit**

```bash
git add nucleo/gemelo/perfiles.py nucleo/gemelo/interprete.py nucleo/gemelo/piezas_de_prueba.py tests/test_gemelo_interprete.py
git commit -m "feat: el interprete sintetico y sus cuatro perfiles de destreza"
```

---

## Task 3: El conductor del estudio, extraído del servidor

**Files:**
- Create: `nucleo/piezas/conductor.py`
- Modify: `servidor/piezas.py` (`SesionCarril._observar`, `_mirar`, `_sin_cuadros`, `_cerrar_lo_que_termino` pasan a delegar)
- Test: `tests/test_conductor.py`

**Esta tarea no añade comportamiento. Es un refactor y su criterio de éxito es que `tests/test_app_estudio.py` (1734 líneas) siga pasando SIN TOCARLO.** Si una prueba de ahí hay que cambiarla, el refactor cambió comportamiento: para y dilo en el informe.

**Interfaces:**
- Consumes: `nucleo.piezas.estudio.{SesionDeEstudio, HistorialDeEstudio, EstadoEstudio, InformeDePasada}`, `nucleo.analisis.pipeline.ResultadoAnalisis`.
- Produces:
  ```python
  TECHO_TRAMO_S: float = 0.100
  ESPERA_SIN_CUADROS_S: float          # = VENTANA_ATAQUE_COMO_ONSET_S

  class ConductorDeEstudio:
      def __init__(
          self,
          estudio: SesionDeEstudio,
          historial: HistorialDeEstudio | None = None,
          al_cambiar_repeticion: Callable[[EstadoEstudio], None] | None = None,
          techo_tramo_s: float = TECHO_TRAMO_S,
          espera_sin_cuadros_s: float = ESPERA_SIN_CUADROS_S,
      ) -> None: ...
      @property
      def estudio(self) -> SesionDeEstudio: ...
      @property
      def historial(self) -> HistorialDeEstudio: ...
      @property
      def vueltas_cerradas(self) -> tuple[InformeDePasada, ...]: ...
      @property
      def factor_sugerido(self) -> float | None: ...
      def observar(self, resultado: ResultadoAnalisis, instante_analisis: float) -> EstadoEstudio: ...
      def mirar(self, ahora: float, senal_ausente: bool) -> EstadoEstudio: ...
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_observar_mueve_el_reloj_con_el_cuadro():
    # Dos cuadros separados 0.021 s: el instante_s del estado avanza 0.021.

def test_mirar_sin_cuadros_avanza_con_techo():
    # Sin ningun cuadro previo y con un salto de 5 s de reloj, el estado avanza
    # como mucho techo_tramo_s.

def test_mirar_con_cuadros_recientes_no_mueve_el_reloj():
    # Tras un observar, un mirar inmediato no cambia instante_s: los cuadros
    # mandan y el reloj a mano le costaria una pulsacion.

def test_la_transicion_de_vuelta_cierra_el_informe_y_lo_anota():
    # Con plan en bucle y el reloj cruzando el final: vueltas_cerradas crece en
    # uno y historial.pasadas crece en uno.

def test_al_cambiar_repeticion_se_llama_una_vez_por_vuelta():
    # Un callback que cuenta: tras dos vueltas, se llamo dos veces, y el estado
    # que recibe trae la repeticion nueva.

def test_el_conductor_no_abre_audio():
    # El modulo nucleo/piezas/conductor.py no menciona `sintesis`, `Metronomo`,
    # `SalidaAudio` ni `sounddevice`. Se comprueba leyendo el propio archivo:
    # es la regla de dependencias del nucleo y merece una prueba, no confianza.

def test_la_senal_ausente_no_mueve_el_reloj():
    # mirar(ahora, senal_ausente=True) deja instante_s quieto.
```

- [ ] **Step 2: Run them and verify they fail**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_conductor.py -v`
Expected: FAIL por módulo inexistente.

- [ ] **Step 3: Move the policy**

Lee `servidor/piezas.py` y traslada a `ConductorDeEstudio` el cuerpo de `_observar`, `_mirar`, `_sin_cuadros` y `_cerrar_lo_que_termino`, **con sus comentarios**: explican defectos ya pagados y perderlos es perder la razón de cada línea. `TECHO_TRAMO_S` y `ESPERA_SIN_CUADROS_S` se mudan al nuevo módulo; `servidor/piezas.py` los reimporta desde allí para no romper a nadie que los lea.

Lo que **no** se muda y se queda en `SesionCarril`: el click (`_ajustar_click`, `_parar_click`, `_periodo_del_acento`), el espejo del estado, la pausa por falta de señal como concepto HTTP, y todo lo que toca FastAPI o el WebSocket. El click se engancha pasándole a `al_cambiar_repeticion` el método que hoy rearranca el metrónomo.

- [ ] **Step 4: Verify the new tests pass AND the old suite is untouched**

```bash
UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_conductor.py -v
UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_app_estudio.py tests/test_app_carril.py tests/test_estudio.py -q
git diff --stat tests/test_app_estudio.py   # tiene que estar vacio
```
Expected: las nuevas PASS; las viejas con el mismo número de pruebas que antes del refactor y en verde; `git diff` de `tests/test_app_estudio.py` vacío.

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/conductor.py servidor/piezas.py tests/test_conductor.py
git commit -m "refactor: la politica del estudio sale del servidor al nucleo"
```

---

## Task 4: La cadena directa y su registro

**Files:**
- Create: `nucleo/gemelo/cadena.py`
- Test: `tests/test_gemelo_cadena.py`

**Interfaces:**
- Consumes: `Interpretacion` (T2), `ConductorDeEstudio` (T3), `nucleo.analisis.pipeline.Analizador`, `nucleo.afinaciones.PERFILES`.
- Produces: `ReporteDeLaCadena`, `RegistroDeLaCadena` y
  ```python
  def pasar_por_la_cadena(
      interpretacion: Interpretacion,
      conductor: ConductorDeEstudio,
      analizador: Analizador | None = None,
      salto: int | None = None,
  ) -> RegistroDeLaCadena
  ```
  con los campos que fija la spec §3.5.

- [ ] **Step 1: Write the failing tests**

```python
def test_el_instante_de_cada_ventana_es_su_final():
    # Un conductor de doble que anota los instantes recibidos: el primero es
    # ventana / fs y la diferencia entre consecutivos es salto / fs.

def test_el_salto_por_omision_es_el_de_produccion():
    # salto=None sobre 1 s de audio produce round(1.0 / 0.021) cuadros, con
    # tolerancia de uno. NO 48000/512.

def test_el_registro_guarda_las_notas_de_todas_las_vueltas():
    # Perfecto, tramo de 4 notas, 3 repeticiones: los reportes cubren las tres
    # repeticiones (1, 2 y 3 aparecen en el campo repeticion), aunque el estado
    # final solo conozca la ultima.

def test_el_registro_guarda_un_informe_por_vuelta_cerrada():
    # len(registro.vueltas) == vueltas que se cerraron.

def test_no_se_reporta_la_misma_nota_dos_veces():
    # Los (repeticion, tocada.indice) del registro no tienen duplicados.

def test_la_cadena_no_abre_hilos_ni_duerme():
    # El modulo no menciona `threading`, `time.sleep` ni `monotonic`: el reloj
    # es virtual y viene de las muestras.

def test_una_interpretacion_de_silencio_no_reporta_nada():
    # Audio todo ceros: reportes == () y no lanza.
```

- [ ] **Step 2: Run them and verify they fail**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_gemelo_cadena.py -v`
Expected: FAIL por módulo inexistente.

- [ ] **Step 3: Implement `pasar_por_la_cadena`**

Recorre `interpretacion.muestras` en ventanas de `perfil.tamano_ventana(fs)` con el salto dado, y para cada una llama a `analizador.procesar(ventana)` y a `conductor.observar(resultado, (inicio + ventana) / fs)` — **el final de la ventana**, que es la convención medida en la spec §3.4. Recoge en el registro cada `NotaTocada` nueva que aparezca en `estado.tocadas` (comparando con las ya vistas de esa repetición) y cada informe que `conductor.vueltas_cerradas` añada. El perfil del analizador sale de `conductor.estudio.pieza.perfil`.

- [ ] **Step 4: Run them and verify they pass**

- [ ] **Step 5: Rompe el código y di cuántas cayeron**

Mutantes: (1) el instante al centro de la ventana; (2) el salto fijo a 512; (3) el registro quedándose solo con la última vuelta. Anota las tres cuentas; el (1) y el (3) son los dos errores que esta tarea existe para impedir.

- [ ] **Step 6: Commit**

```bash
git add nucleo/gemelo/cadena.py tests/test_gemelo_cadena.py
git commit -m "feat: la cadena directa del gemelo, en tiempo virtual"
```

---

## Task 5: El veredicto

**Files:**
- Create: `nucleo/gemelo/veredicto.py`
- Test: `tests/test_gemelo_veredicto.py`

**Interfaces:**
- Consumes: `Interpretacion` (T2), `RegistroDeLaCadena` (T4).
- Produces: `Veredicto` y `juzgar(interpretacion, registro, tolerancia_de_emparejamiento_ms=120.0) -> Veredicto`, con los campos de la spec §3.5.

- [ ] **Step 1: Write the failing tests**

Con registros construidos a mano, sin pasar por la cadena: así el veredicto se prueba solo.

```python
def test_sin_perdidas_cuando_todo_se_reporto():
    # Un evento y su reporte a 30 ms: perdidas == () e inventadas == 0.

def test_la_nota_no_reportada_sale_como_perdida_con_su_vuelta():
    # Dos eventos, un reporte: perdidas == ((1, indice_del_otro),).

def test_el_reporte_sin_evento_sale_como_inventado():
    # inventadas == 1.

def test_el_reporte_de_otra_altura_sale_como_mal_adjudicado():
    # mal_adjudicadas == ((vuelta, pretendido, reportado),).

def test_el_desfase_lleva_signo():
    # Reportes 40 ms DESPUES de sus eventos: desfase_introducido_ms > 0.
    # Reportes antes: < 0. Un valor absoluto escondería la direccion, que es
    # justo lo que diagnostica.

def test_la_tolerancia_empareja_y_no_juzga():
    # Un reporte a 100 ms de su evento, con tolerancia 120: NO es perdida, y su
    # desfase cuenta 100 ms. A 130 ms: es perdida e inventada.

def test_la_nota_repetida_consecutiva_se_excluye_en_vez_de_perderse():
    # pieza_con_nota_repetida interpretada perfecta, con el registro al que le
    # falta la segunda de las dos: esa nota esta en `excluidas` y NO en
    # `perdidas`, e inventadas == 0. (Review Focus 4.)

def test_las_notas_de_un_acorde_se_excluyen():
    # pieza_con_acorde: las notas del acorde que el interprete no toco estan en
    # excluidas, no en perdidas.

def test_el_veredicto_no_importa_reglas_del_seguidor():
    # El modulo no menciona `_clasificar`, `ventana_de_acierto`, `esta_afinada`
    # ni importa de `nucleo.piezas.seguimiento` mas que tipos. Es el
    # anti-objetivo de la spec §2 convertido en prueba: un veredicto que
    # consulte las reglas de la cadena se da la razon.

def test_un_veredicto_limpio_se_distingue_de_uno_sucio():
    # Una propiedad `limpio` es True solo si perdidas, inventadas y
    # mal_adjudicadas estan vacias.
```

- [ ] **Step 2: Run them and verify they fail**

- [ ] **Step 3: Implement `juzgar`**

Empareja por `(repeticion, indice_pretendido)`: para cada evento con índice, busca el reporte de esa repetición y ese índice; si no hay, perdida; si hay y la altura no coincide, mal adjudicada. El desfase es `reporte.instante_pasada_s - evento.instante_s` corregido por el silencio de cabecera, y la mediana se calcula con `numpy.median` sobre los emparejados. Las notas excluidas se determinan **desde la pieza** (acordes: varias notas con el mismo `inicio_pulsos`; repetidas: nota consecutiva del mismo midi), no desde lo que la cadena hizo.

- [ ] **Step 4: Run them and verify they pass**

- [ ] **Step 5: Rompe el código y di cuántas cayeron**

Mutantes: (1) el desfase en valor absoluto; (2) las excluidas tratadas como perdidas; (3) la tolerancia a 15 ms. Anota las tres.

- [ ] **Step 6: Commit**

```bash
git add nucleo/gemelo/veredicto.py tests/test_gemelo_veredicto.py
git commit -m "feat: el veredicto del gemelo, que no consulta las reglas de la cadena"
```

---

## Task 6: El oráculo sin bucle, y el suelo medido

**Files:**
- Test: `tests/test_gemelo_oraculo.py`

Esta tarea no escribe código de producción: **mide**. Es la que fija los números que las tareas siguientes usan como referencia, y la que descubre si la cadena está bien sin bucle.

**Interfaces:**
- Consumes: todo lo de T1–T5.
- Produces: en el informe de la tarea, el suelo medido de `desfase_introducido_ms` y `desfase_maximo_ms` del oráculo sin bucle, que las pruebas de este archivo inscriben como constantes con su margen.

- [ ] **Step 1: Measure before asserting**

Escribe un script temporal (fuera del repositorio, en `$TMPDIR`) que interprete `escala_de_ocho_notas()` con `PERFECTO`, la pase por la cadena sin bucle y imprima el veredicto completo. Corre y **anota los números**. No inventes la aserción: la aserción sale de aquí.

- [ ] **Step 2: Write the tests with the measured numbers**

```python
SUELO_DESFASE_MS = ...   # el medido en el paso 1, redondeado hacia arriba
MARGEN_MS = 15.0

def test_el_oraculo_sin_bucle_no_pierde_ninguna_nota():
    # perdidas == () e inventadas == 0 y mal_adjudicadas == ().

def test_el_oraculo_sin_bucle_acierta_todas_las_notas_del_informe():
    # En el informe final, sum(acertadas) == 8 sobre 8 notas medibles.

def test_el_oraculo_sin_bucle_las_cuenta_todas_como_limpias():
    # sum(limpias) == 8. Si esta falla, la cadena le dice a un interprete
    # perfecto que no toca a tiempo, y eso es un defecto, no una tolerancia que
    # relajar: arreglalo o escalalo, NO cambies el numero esperado.

def test_el_desfase_que_introduce_la_cadena_es_el_suelo_conocido():
    # abs(desfase_introducido_ms) <= SUELO_DESFASE_MS + MARGEN_MS.

def test_el_oraculo_aguanta_el_tempo_minimo():
    # factor_tempo=0.40: lo mismo que arriba. (Review Focus 5.)
```

- [ ] **Step 3: Run them**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_gemelo_oraculo.py -v`

Si alguna falla, **es un hallazgo, no un problema de la prueba**. Anótalo en el informe con sus números, arréglalo si el arreglo cabe en esta tarea, y si no, dilo claramente: la Tarea 7 toca ese código.

- [ ] **Step 4: Commit**

```bash
git add tests/test_gemelo_oraculo.py
git commit -m "test: el oraculo sin bucle, con el suelo de desfase medido"
```

---

## Task 7: El bucle arreglado

**Files:**
- Modify: `nucleo/piezas/estudio.py` (`_dar_la_vuelta`, `_al_dia`, `cerrar_repeticion`)
- Modify (solo si es inevitable): `nucleo/piezas/seguimiento.py`
- Test: `tests/test_gemelo_bucle.py`, y las pruebas de unidad que haga falta añadir a `tests/test_estudio.py`

Esta es la tarea central del plan. Cierra los defectos 1, 2 y 3 del §8 de la spec.

**El defecto, medido.** Intérprete perfecto, ocho notas, tramo de dos compases, cuatro vueltas: vuelta 1 → 8 acertadas, 5 limpias, −69 ms; vueltas 2, 3 y 4 → 7 acertadas, **0 limpias**, −91, −101 y −123 ms. El intérprete no cambió nada entre vueltas.

**Las dos causas y los dos arreglos**, decididos en la spec §8:

1. **El exceso perdido.** `_dar_la_vuelta` hace `avanzar_a(self._inicio_s())` y tira el exceso con que el reloj cruzó el final. Arreglo: dar la vuelta a `inicio + exceso`, donde `exceso = instante_s - fin_s` acotado a la longitud del tramo (un exceso mayor que el tramo entero significa un salto de reloj, no una vuelta).
2. **La nota de la frontera.** `avanzar_a` deja `_analisis_desde` sin fijar y `_adjudicar` descarta los onsets anteriores al primer cuadro posterior al salto, así que la última nota de cada vuelta cae en el agujero de 250 ms del detector. Arreglo: **retener las pulsaciones en vuelo y volcarlas al informe de la vuelta que cierra**, sin cirugía en `seguimiento.py`. **Una nota pertenece a la vuelta en que se ATACÓ, no a la vuelta en que el detector la resolvió.**

- [ ] **Step 1: Write the failing tests**

```python
def test_el_bucle_no_arrastra_el_reloj_entre_vueltas():
    # Perfecto, 8 notas, 4 vueltas: el desfase_medio_s de la vuelta 4 no difiere
    # del de la vuelta 1 en mas de 10 ms. ESTA es la prueba del defecto.

def test_el_bucle_cuenta_las_mismas_limpias_en_todas_las_vueltas():
    # Las cuatro vueltas dan sum(limpias) == 8.

def test_el_bucle_no_pierde_ninguna_nota_en_ninguna_vuelta():
    # El veredicto: perdidas == () con 4 repeticiones.

def test_la_nota_del_final_cuenta_en_la_vuelta_que_cierra():
    # Un interprete que toca la ultima nota del tramo 50 ms antes del final:
    # aparece en el informe de esa vuelta y NO en el de la siguiente.

def test_la_vuelta_que_no_termino_no_se_cuenta():
    # Audio que se corta a mitad de la vuelta 3: vueltas cerradas == 2, y el
    # historial tiene 2 pasadas, no 3. (Review Focus 3.)

def test_el_bucle_aguanta_el_tempo_minimo():
    # factor_tempo=0.40 con 3 vueltas: sin arrastre y sin perdidas.
    # (Review Focus 5.)

def test_un_exceso_mayor_que_el_tramo_no_se_arrastra():
    # Un avanzar(delta) enorme que cruza el final varias veces da UNA vuelta y
    # deja el reloj dentro del tramo, no mas alla.
```

- [ ] **Step 2: Run them and verify they fail, with numbers**

Run: `UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest tests/test_gemelo_bucle.py -v`
Expected: FAIL. **Anota en el informe el desfase y las limpias de cada vuelta tal y como están ANTES del arreglo**, para poder comparar.

- [ ] **Step 3: Fix the drift**

En `_dar_la_vuelta`, conservar el exceso. Corre las pruebas y anota cuáles pasan ya solo con esto: separa lo que arregla cada causa, porque si una sola basta, la otra es código sin motivo.

- [ ] **Step 4: Fix the boundary note**

Retén las pulsaciones que el detector firme dentro de `VENTANA_ATAQUE_COMO_ONSET_S` después de la transición y cuyo instante de ataque sea anterior al final del tramo, y vuélcalas al informe de la vuelta que cerró. `cerrar_repeticion` necesita poder recibir ese añadido después de haber cerrado: si eso obliga a cambiar su firma, cámbiala y dilo.

**Si al llegar aquí la única salida es tocar `nucleo/piezas/seguimiento.py`**, pára y escríbelo en el informe antes de hacerlo: la spec eligió no tocarlo y el controlador tiene que saber que la elección no se sostuvo.

- [ ] **Step 5: Run the whole suite**

```bash
UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q
```
Expected: todo en verde. Las pruebas de la 3c que midan el comportamiento viejo del bucle van a fallar: cada una que cambies se justifica en el informe diciendo qué medía y por qué lo que medía era el defecto.

- [ ] **Step 6: Rompe el código y di cuántas cayeron**

Mutantes: (1) el exceso otra vez tirado; (2) la retención de la frontera quitada; (3) la nota de la frontera volcada a la vuelta que ABRE en vez de a la que cierra. El (3) es la semántica de la spec: si no mata ninguna prueba, escríbela.

- [ ] **Step 7: Commit**

```bash
git add nucleo/piezas/estudio.py tests/test_gemelo_bucle.py tests/test_estudio.py
git commit -m "fix: el bucle deja de arrastrar el reloj y de perder la nota de la frontera"
```

---

## Task 8: La cuenta atrás, vista desde el audio

**Files:**
- Test: `tests/test_gemelo_cuenta_atras.py`
- Modify: `nucleo/piezas/estudio.py` solo si las pruebas lo exigen

La revisión final de la 3c encontró que la cuenta atrás moría con el primer cuadro de audio. Se arregló con `congelar_en`, pero nunca se comprobó con audio entrando de verdad.

- [ ] **Step 1: Write the failing tests**

```python
def test_la_cuenta_atras_sobrevive_al_primer_cuadro_de_audio():
    # compases_de_cuenta_atras=1, audio con el silencio de la cuenta atras
    # dentro: en el cuadro 1 la cuenta sigue viva y el reloj esta en el inicio.

def test_durante_la_cuenta_atras_no_se_cobra_nada():
    # Un interprete que toca DURANTE la cuenta atras: ninguna de esas notas
    # entra en el informe.

def test_la_cuenta_atras_de_cada_vuelta_tambien_sobrevive():
    # Con bucle y cuenta atras, las cuatro vueltas tienen su cuenta completa:
    # el instante del primer evento cobrado de cada vuelta esta despues de ella.

def test_la_cuenta_atras_de_un_compas_dura_un_compas():
    # Al tempo de la pieza y con el factor aplicado: la duracion medida coincide
    # con pulsos_por_compas * 60 / (tempo * factor), con 1 ms de tolerancia.
```

- [ ] **Step 2–4: Fail, fix if needed, pass**

Si pasan sin tocar nada, dilo: es el resultado válido y significa que el arreglo de la 3c aguanta con audio. Si falla alguna, el arreglo está en `_al_dia`/`procesar` y se hace aquí.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gemelo_cuenta_atras.py nucleo/piezas/estudio.py
git commit -m "test: la cuenta atras comprobada con audio entrando de verdad"
```

---

## Task 9: El informe y la regla del tempo, comprobados contra la verdad

**Files:**
- Modify: `nucleo/piezas/estudio.py` (`HistorialDeEstudio.peores_compases`)
- Test: `tests/test_gemelo_informe.py`

Cierra el defecto 4 del §8: `peores_compases` no multiplica por `repeticiones`.

- [ ] **Step 1: Write the failing tests**

```python
def test_el_informe_senala_el_compas_que_se_toco_tarde():
    # Un perfil que retrasa 120 ms SOLO las notas del compas 2 (un perfil hecho
    # en la prueba, no de fabrica): el CompasDelInforme del 2 tiene
    # desfase_medio_s positivo y mayor que el del 1, y el del 1 no se nomina.

def test_el_informe_senala_el_compas_que_se_fallo():
    # Un perfil que falla solo las notas del compas 2: limpias del 2 es 0 y del
    # 1 es completo.

def test_peores_compases_cuenta_las_repeticiones():
    # Historial con dos informes de 4 repeticiones cada uno: el total de notas
    # que peores_compases atribuye a un compas es notas_medibles * repeticiones,
    # no notas_medibles. ESTA es la prueba del defecto 4.

def test_el_tempo_sube_tras_dos_pasadas_perfectas():
    # Dos pasadas con PERFECTO al factor 0.5: factor_sugerido == 0.55.

def test_el_tempo_no_sube_con_una_pasada_mala():
    # Una pasada con un perfil que falla la mitad: factor_sugerido no sube.

def test_el_tempo_no_sube_nunca_a_base_de_vueltas_de_bucle_malas():
    # 4 vueltas malas en bucle: no sube. Es el caso que el defecto del bucle
    # hacia imposible de ver.
```

- [ ] **Step 2–4: Fail, fix `peores_compases`, pass**

- [ ] **Step 5: Rompe el código y di cuántas cayeron**

Mutantes: (1) `repeticiones` otra vez ignorado en `peores_compases`; (2) `UMBRAL_PARA_SUBIR` a 0.5; (3) `PASADAS_BUENAS_PARA_SUBIR` a 1.

- [ ] **Step 6: Commit**

```bash
git add nucleo/piezas/estudio.py tests/test_gemelo_informe.py
git commit -m "fix: peores_compases cuenta las repeticiones, y el informe comprobado contra la verdad"
```

---

## Task 10: El trasteo y los ataques fantasma

**Files:**
- Test: `tests/test_gemelo_sonido_sucio.py`

Esta tarea **no arregla** los fantasmas: los deja medidos y nombrados en una prueba que dice lo que hoy pasa, porque tocar el detector de ataques es el corazón de las etapas 2a y 3a y merece su propia decisión (spec §10).

- [ ] **Step 1: Write the tests**

```python
def test_el_trasteo_no_cuenta_como_nota_limpia():
    # probabilidad_de_trasteo=1.0 con el resto perfecto: sum(limpias) es menor
    # que el numero de notas.

def test_las_notas_que_se_solapan_generan_ataques_fantasma():
    # PERFECTO con sustain=1.0 sobre la escala: el veredicto tiene
    # inventadas > 0. La prueba AFIRMA el defecto conocido; su nombre lo dice y
    # su docstring remite a la spec §10. El dia que se arregle, esta prueba se
    # invierte a proposito, no se borra por molesta.

def test_sin_solape_no_hay_fantasmas():
    # sustain=0.0: inventadas == 0. Es la mitad que demuestra que la causa es el
    # solape y no el gemelo.

def test_la_desafinacion_se_ve_en_el_informe():
    # cents_de_desafinacion=50: las NotaTocada reportadas traen afinada=False en
    # la mayoria.
```

- [ ] **Step 2–3: Run, record the numbers in the report**

- [ ] **Step 4: Commit**

```bash
git add tests/test_gemelo_sonido_sucio.py
git commit -m "test: el trasteo y los ataques fantasma del solape, medidos y nombrados"
```

---

## Task 11: El dispositivo simulado y la sesión completa

**Files:**
- Create: `nucleo/gemelo/dispositivo.py`
- Test: `tests/test_gemelo_dispositivo.py`, `tests/test_gemelo_sesion_completa.py`

**Interfaces:**
- Consumes: `Interpretacion` (T2); el contrato de `nucleo.captura.CapturaAudio` (`abrir_stream`) y de `servidor.sesion.Sesion` (`crear_captura`, `listar`).
- Produces:
  ```python
  class StreamSimulado:
      latency: float          # valor plausible y declarado; CapturaAudio lo lee
      def start(self) -> None: ...
      def stop(self) -> None: ...
      def close(self) -> None: ...

  def dispositivo_simulado(
      interpretacion: Interpretacion,
      tamano_bloque: int = 512,
      nombre: str = "Rocksmith USB Guitar Adapter (gemelo)",
  ) -> tuple[Callable, Callable]    # (abrir_stream, listar)
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_el_dispositivo_se_anuncia_como_gemelo_y_como_rocksmith():
    # listar() devuelve un DispositivoAudio cuyo nombre contiene "Rocksmith"
    # -para que buscar_rocksmith lo encuentre- y "(gemelo)", para que nadie
    # confunda una sesion simulada con una real.

def test_el_stream_empuja_el_audio_en_bloques():
    # CapturaAudio con este abrir_stream: tras arrancar y esperar, el buffer
    # tiene las muestras de la interpretacion en orden.

def test_al_acabarse_el_audio_sigue_empujando_silencio():
    # Pasada la duracion de la interpretacion, total_capturado SIGUE creciendo y
    # lo que llega es silencio. Es la decision de la spec §3.8: un cable
    # enchufado a una guitarra que nadie toca.

def test_el_dispositivo_no_desaparece_de_listar():
    # listar() sigue devolviendolo despues de acabarse el audio.

def test_el_stream_expone_latency():
    # CapturaAudio.latencia_ms no lanza y devuelve un numero. Sin este atributo
    # el diagnostico reventaba la primera vez que alguien lo pidiera.

def test_ninguna_prueba_abre_el_dispositivo_real():
    # El modulo no importa `sounddevice`.
```

Y en `test_gemelo_sesion_completa.py`, marcadas lentas con `@pytest.mark.slow` y con el tiempo de reloj acotado:

```python
def test_la_pieza_corta_atraviesa_la_sesion_entera():
    # Una pieza de ~3 s interpretada con PERFECTO, Sesion real con el
    # dispositivo simulado, SesionCarril real: el veredicto sale limpio.

def test_la_sesion_completa_concuerda_con_la_cadena_directa():
    # La misma interpretacion por los dos caminos: el numero de notas acertadas
    # coincide, y el desfase mediano no difiere en mas de 25 ms. Es la prueba
    # que vigila el riesgo §10 de que los dos niveles divergan.
```

Declara `slow` en `pyproject.toml` (`[tool.pytest.ini_options] markers`) si no existe; no lo desactives por omisión: una prueba lenta que nadie corre no vigila nada.

- [ ] **Step 2–4: Fail, implement, pass**

El stream arranca un hilo con reloj real que empuja un bloque cada `tamano_bloque / fs` segundos y, agotado el audio, sigue empujando ceros.

- [ ] **Step 5: Commit**

```bash
git add nucleo/gemelo/dispositivo.py tests/test_gemelo_dispositivo.py tests/test_gemelo_sesion_completa.py pyproject.toml
git commit -m "feat: el cable falso, y la sesion completa a tiempo real"
```

---

## Task 12: El escaparate

**Files:**
- Create: `herramientas/gemelo.py`
- Test: `tests/test_herramientas_gemelo.py`

**Interfaces:**
- Consumes: todo lo anterior; `servidor.arranque`; `urllib.request`.
- Produces: un módulo ejecutable con `argparse`:
  `--pieza RUTA` (sin ella, `pieza_de_demostracion()`), `--perfil {perfecto,principiante,intermedio,caos}`, `--tempo FACTOR`, `--bucle PRIMERO-ULTIMO`, `--repeticiones N`, `--cuenta-atras COMPASES`, `--semilla N`, `--puerto 8420`, `--salir-al-acabar`.

- [ ] **Step 1: Write the failing tests**

No arrancan servidor: prueban las piezas separables.

```python
def test_el_bucle_se_lee_de_la_forma_primero_guion_ultimo():
    # "17-20" -> (17, 20). "17" -> (17, 17). "20-17" y "cero" -> ValueError con
    # el texto recibido en el mensaje.

def test_sin_pieza_usa_la_de_demostracion_construida_en_codigo():
    # Y esa pieza no viene de ningun archivo: es la regla de los derechos de
    # autor, y aqui es donde se podria romper.

def test_el_perfil_desconocido_se_rechaza_nombrando_los_validos():

def test_el_codigo_de_salida_es_cero_con_veredicto_limpio_y_otro_si_no():
    # Sobre un Veredicto construido a mano, con la funcion que lo traduce.

def test_el_resumen_dice_que_fue_el_gemelo_y_no_una_guitarra():
    # El texto que imprime contiene "gemelo": nadie debe leer este informe
    # creyendo que alguien toco.
```

- [ ] **Step 2–4: Fail, implement, pass**

El módulo levanta `uvicorn` en un hilo con la app real y la `Sesion` apuntando al dispositivo simulado, llama a los endpoints con `urllib.request` (no `httpx`: está solo en `dev`), imprime el veredicto al completarse la pasada y se queda vivo salvo con `--salir-al-acabar`.

- [ ] **Step 5: Verify it runs for real, once**

```bash
UV_CACHE_DIR="$TMPDIR/uv-cache" uv run python -m herramientas.gemelo --perfil perfecto --salir-al-acabar
```
Expected: imprime un veredicto y sale con 0. Pega la salida en el informe de la tarea. Si el sandbox bloquea el puerto o la red local, dilo en el informe: no lo rodees.

- [ ] **Step 6: Commit**

```bash
git add herramientas/gemelo.py tests/test_herramientas_gemelo.py
git commit -m "feat: el escaparate del gemelo, para verse tocar sin tocar"
```

---

## Task 13: El gemelo contra la guitarra real

**Files:**
- Test: `tests/test_gemelo_contra_real.py`

Se salta mientras `tests/audio/` esté vacío, igual que `tests/test_audio_real.py`. Las tolerancias se escriben **ahora**, para que el día que existan las grabaciones nadie las elija a conveniencia de lo que salga.

- [ ] **Step 1: Write the tests**

```python
def test_el_detector_le_da_la_misma_nota_al_gemelo_y_a_la_guitarra():
    # Para las seis cuerdas al aire: misma nota dominante.

def test_el_gemelo_no_es_mas_facil_que_la_guitarra():
    # La proporcion de ventanas acertadas del gemelo no supera la de la
    # grabacion real en mas de 0.10. Si el gemelo es mas facil, se quiere
    # saber: es el riesgo principal del §10 de la spec.

def test_el_decaimiento_es_del_mismo_orden():
    # El tiempo hasta que la energia RMS cae a la mitad queda dentro de un
    # factor 2 del de la grabacion.
```

Cada una con `pytest.skip` si falta el `.wav`, con el mensaje que ya usa `test_audio_real.py` (`"Falta {nombre}: ejecuta herramientas/grabar_muestras.py"`).

- [ ] **Step 2–3: Run (se saltan), commit**

```bash
git add tests/test_gemelo_contra_real.py
git commit -m "test: el gemelo contra la guitarra real, con las tolerancias escritas de antemano"
```

---

## Task 14: Los cuatro defectos pequeños del núcleo

**Files:**
- Modify: `nucleo/piezas/estudio.py` (`congelar_en`/`_observar`, `pausar`, `reanudar`), `nucleo/piezas/modelo.py` (docstring de `Seccion`), `tests/test_sesion_carril.py:402` (la prueba que miente — comprobado con grep: NO está en `test_app_estudio.py`)
- Test: `tests/test_estudio.py`

Cuatro arreglos a la vista, agrupados porque son el mismo tamaño y un solo repaso los cubre.

- [ ] **Step 1: El `congelar_en` que es letra muerta**

Averigua si `_observar` lo llama alguna vez con efecto. Si es letra muerta, **bórralo con su prueba si la tiene**, y di en el informe qué lo dejó muerto. Si no lo es, escribe la prueba que demuestra que hace algo.

- [ ] **Step 2: `pausar` y `reanudar` dentro del candado**

Hoy están fuera. Mételos dentro (`self._candado` es `RLock`, así que no hay riesgo de reentrada) y escribe la prueba que lo exige: dos hilos, uno pausando y otro procesando cuadros, y el estado final consistente.

- [ ] **Step 3: La prueba cuyo nombre miente**

`test_la_pausa_le_congela_el_reloj_tambien_al_seguidor` mide otra cosa que su nombre. Haz que mida lo que promete: que **el reloj del seguidor**, no solo el del estudio, se queda quieto durante la pausa. Si al medirlo falla, es un defecto: arréglalo y dilo.

- [ ] **Step 4: El docstring de `Seccion`**

Dice «No se usan todavia: la etapa 3c practicara por secciones». La 3c ya pasó y las usa. Reescríbelo diciendo quién las usa hoy (`servidor/piezas.py:_secciones_en_compases`, y la rejilla de la interfaz). Vive en el núcleo: es la décima frase falsa de esta familia y por eso se arregla aquí.

- [ ] **Step 5: Run the whole suite and commit**

```bash
UV_CACHE_DIR="$TMPDIR/uv-cache" uv run pytest -q
git add -A nucleo tests
git commit -m "fix: el candado de la pausa, el congelar_en muerto, una prueba que mentia y un docstring falso"
```

---

## Task 15: Los dos defectos de la interfaz

**Files:**
- Modify: `interfaz/src/RejillaCompases.tsx`, `interfaz/src/ControlesEstudio.tsx`
- Test: `interfaz/src/RejillaCompases.test.tsx`, `interfaz/src/ControlesEstudio.test.tsx`

**Interfaces:** nada nuevo hacia fuera. El TypeScript también va en español, y aquí **sí** llevan tildes los textos de pantalla.

- [ ] **Step 1: Write the failing tests**

```tsx
test("el arrastre de la rejilla funciona con el dedo", () => {
  // pointerdown/pointermove/pointerup con pointerType "touch" sobre dos
  // compases: el rango queda seleccionado igual que con el raton.
});

test("el arrastre con el dedo no hace scroll de la pagina", () => {
  // touch-action o preventDefault: el gesto no se va al scroll. Sin esto el
  // arrastre tactil "funciona" en la prueba y no en el telefono.
});

test("el deslizador de tempo no parpadea al soltar", () => {
  // Durante el arrastre el deslizador muestra el valor local; al soltar, manda
  // el valor y NO vuelve al valor del servidor antes de que llegue el estado
  // nuevo. Se comprueba que el valor mostrado nunca retrocede.
});
```

- [ ] **Step 2–4: Fail, fix, pass**

```bash
cd interfaz && pnpm test && pnpm lint && pnpm build
```

- [ ] **Step 5: Commit**

```bash
git add interfaz/src
git commit -m "fix: el arrastre tactil de la rejilla y el parpadeo del deslizador"
```

---

## Task 16: El README deja de callarse la etapa

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write it**

Añade la etapa 3d a la primera línea de etapas. Documenta `herramientas/gemelo.py` con su línea de ejecución y **para qué sirve**: ver la sesión correr sin guitarra. Di en claro que el gemelo **no sustituye** la prueba con el cable y enlaza la spec. Renumera la promesa de la 3c: la pieza sonando de fondo es la 3e, no la 3d.

- [ ] **Step 2: Verify the README does not lie**

Comprueba una por una que cada orden que el README manda ejecutar existe y hace lo que dice. La rama 3c tuvo que arreglar esto después: hacerlo aquí cuesta cinco minutos.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: el README cuenta el gemelo y renumera la pieza de fondo a la 3e"
```

---

## Orden y dependencias

```
T1 cuerda ──► T2 interprete ──┬──► T4 cadena ──► T5 veredicto ──► T6 oraculo ──► T7 bucle ──► T8 cuenta atras ──► T9 informe ──► T10 sonido sucio
                              │         ▲
T3 conductor ─────────────────┴─────────┘
                                                                     T11 dispositivo ──► T12 escaparate
T13, T14, T15, T16 son independientes y pueden ir al final.
```

T3 (el refactor del servidor) no depende de T1 ni T2 y puede hacerse en paralelo conceptualmente, pero **no se despacha en paralelo**: toca `servidor/piezas.py`, que T11 y T12 también leen.

T6 es la puerta: si el oráculo sin bucle no sale limpio, T7 cambia de tamaño y el controlador tiene que saberlo antes de despachar T7.

## Lo que el plan NO cubre, a propósito

El §6 de la spec —que el gemelo mueva la **interfaz real** en un navegador— no es
ninguna de estas tareas, porque no es código del proyecto. Lo hace el controlador
al terminar la ejecución: levanta `herramientas/gemelo.py`, conduce Chrome contra
el servidor y deja constancia de lo que se ve. Meter Playwright en el repositorio
para automatizarlo en la suite es una decisión de dependencia que la spec deja
anotada para el usuario, no tomada.
