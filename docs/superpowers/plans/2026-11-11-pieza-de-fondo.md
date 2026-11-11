# Etapa 3e — La pieza sonando de fondo: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que la pieza suene mientras la tocas, sincronizada con el cabezal del carril, sintetizada de la partitura y sin una sola dependencia nueva.

**Architecture:** tres capas que no se conocen entre sí. `voces_de_fondo.py` saca alturas e instantes de un archivo sin digitar nada; `acompanamiento.py` las convierte en un buffer de muestras determinista; `acompanante.py` lo hace sonar en un hilo que **lee el cabezal del carril en cada bloque** y no lleva reloj propio, así que no puede derivar. El cableado entra en `SesionCarril` por una puerta nueva, nunca por `iniciar`.

**Tech Stack:** Python 3.13, numpy, sounddevice (ya presentes), React + Vite para el control.

**Spec:** `docs/superpowers/specs/2026-11-11-pieza-de-fondo-design.md`

## Global Constraints

- Español en código, comentarios, docstrings y pruebas. Los `.py` **sin tildes**; el TS/TSX **sí** las lleva en los textos de pantalla.
- `uv run pytest` necesita `UV_CACHE_DIR` dentro de un directorio escribible: `export UV_CACHE_DIR="$TMPDIR/uv-cache"`.
- `pnpm`, nunca `npm`. En `interfaz/`: `pnpm test && pnpm lint && pnpm build`.
- **Cero dependencias nuevas.** Si una tarea parece necesitar una, es que la tarea está mal.
- Nada de audio real en las pruebas: la salida se inyecta siempre (`SalidaAudio(abrir_stream=...)`). El sandbox de desarrollo no puede abrir audio y `open`/`osascript` están bloqueados.
- Preferir numpy sobre bucles a mano.
- Toda prueba que afirme un valor medido lo toma de un **origen distinto** del camino que prueba. Es la lección de las nueve veces que esta rama se equivocó en la 3d: *la aserción tomaba su valor de referencia del mismo camino de código que probaba.*
- Toda prueba de tiempo real afirma el **crecimiento** o la cadencia medida en esa misma pasada, nunca un umbral medido en una máquina en reposo.

## Review Focus

Cinco cosas que la spec implica, que ninguna tarea de abajo prueba por sí sola, y que van a morder al usuario. Cada una lleva su prueba asignada a la tarea que posee el código:

1. **Una pieza sin notas, o un archivo cuyas demás pistas están todas vacías.** Esperado: silencio y ningún error; el interruptor no debe poder encenderse sobre la nada. → prueba en Task 2 (`renderizar` con voces vacías) y Task 5 (el estado dice que no hay acompañamiento posible).
2. **Una nota más corta que un periodo de su propia altura.** `cuerda_pulsada` **lanza** ahí (`nucleo/gemelo/cuerda.py:84-97`). Esperado: se alarga al mínimo, como hace el intérprete, y no revienta el render de la canción entera. → prueba en Task 2.
3. **Mover el tempo mientras suena.** Esperado: ni un corte ni una muestra del buffer viejo después del cambio. → prueba en Task 4.
4. **El candado de la sesión ocupado cuando el hilo de audio quiere el cabezal.** Esperado: el bloque sale repitiendo el último cabezal conocido, nunca un hueco de silencio, y nunca esperando. → prueba en Task 4.
5. **El usuario con el micrófono del portátil.** Esperado: el interruptor sale apagado, el aviso explica que el sonido del programa va a contar como notas suyas, y si lo enciende de todas formas el recordatorio no se va. → prueba en Task 5 (Python) y Task 8 (pantalla), y **medido** en Task 9.

---

### Task 1: Las voces de fondo, sin digitar nada

**Files:**
- Create: `nucleo/piezas/voces_de_fondo.py`
- Test: `tests/test_voces_de_fondo.py`

**Interfaces:**
- Consumes: los parsers que ya usan los lectores de la 3b (`nucleo/piezas/desde_guitarpro.py`, `desde_midi.py`, `desde_musicxml.py`, `desde_ascii.py`) y `nucleo/piezas/lectores.py:307 pistas_de_archivo`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class NotaDeFondo:
      midi: float
      inicio_pulsos: float
      duracion_pulsos: float

  @dataclass(frozen=True)
  class VozDeFondo:
      nombre: str
      instrumento: str
      notas: tuple[NotaDeFondo, ...]

  @dataclass(frozen=True)
  class FondoDisponible:
      voces: tuple[VozDeFondo, ...]
      tempo: int
      excluidas: tuple[tuple[str, str], ...]   # (nombre de la pista, motivo)

  def voces_de(ruta: Path | str, pista_excluida: int) -> FondoDisponible
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_las_demas_pistas_suenan_y_la_tuya_no():
    # Un .gp5 de dos pistas: voces_de(ruta, 1) trae UNA voz, la de la pista 2,
    # y su nombre es el de esa pista.

def test_una_pista_de_percusion_se_excluye_y_se_dice_por_que():
    # La voz no esta en `voces`, y `excluidas` trae su nombre con el motivo de
    # `desde_guitarpro._motivo_no_usable`. Afirmado contra ese motivo, no contra
    # una copia del texto.

def test_una_pista_que_no_cabe_en_la_afinacion_SI_suena():
    # El caso que M8 existe para arreglar: una pista cuyas alturas no caben en
    # ninguna afinacion de guitarra -un piano- entra como voz de fondo sin
    # lanzar ValueError. Es lo que `importar` NO puede hacer
    # (desde_midi.py:165-210).

def test_el_tempo_sale_del_archivo_y_no_se_inventa():
    # FondoDisponible.tempo es el del archivo, comparado contra el que
    # `importar` pone en la Pieza de la misma cancion.

def test_sin_mas_pistas_no_hay_voces_pero_tampoco_error():
    # Un archivo de una sola pista: voces == () y excluidas == (), sin excepcion.

def test_los_cuatro_formatos_dan_voces():
    # gp5, MIDI, MusicXML y tablatura ASCII. En ASCII, que no tiene pistas, el
    # resultado es voces == () y no una excepcion.
```

- [ ] **Step 2: Run them and see them fail**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest tests/test_voces_de_fondo.py -v`
Expected: FAIL, `ModuleNotFoundError: nucleo.piezas.voces_de_fondo`.

- [ ] **Step 3: Implement `voces_de`**

Un camino por formato, despachado por extensión igual que `lectores._extension` ya lo hace. Cada camino abre el archivo con el **mismo parser** que su lector hermano y recorre las notas sacando `midi`, `inicio_pulsos` y `duracion_pulsos`. **No** construye `Pieza`, **no** llama a `nucleo/piezas/digitacion.py`, **no** mira afinaciones: por eso no puede lanzar `ValueError` por una pista que no cabe. Las pistas que `_motivo_no_usable` rechaza por percusión o por estar vacías van a `excluidas` con su motivo tal cual. La tablatura ASCII no tiene pistas: devuelve vacío.

- [ ] **Step 4: Run them and see them pass**

- [ ] **Step 5: Commit**

```bash
git add nucleo/piezas/voces_de_fondo.py tests/test_voces_de_fondo.py
git commit -m "feat: las voces de fondo salen del archivo sin pasar por la digitacion"
```

---

### Task 2: El render determinista

**Files:**
- Create: `nucleo/acompanamiento.py`
- Modify: `nucleo/gemelo/interprete.py` (subir `_duracion_minima_s` a un sitio común e importarla)
- Test: `tests/test_acompanamiento.py`

**Interfaces:**
- Consumes: `nucleo/gemelo/cuerda.py:44 cuerda_pulsada(midi, duracion_s, frecuencia_muestreo, brillo, fuerza, trasteo, semilla)`; `VozDeFondo` y `NotaDeFondo` de Task 1.
- Produces:
  ```python
  @dataclass(frozen=True)
  class PiezaRenderizada:
      muestras: np.ndarray          # mono float32
      frecuencia_muestreo: int
      pulsos_por_segundo: float
      duracion_s: float
      def rodaja(self, instante_pulsos: float, cuantas: int) -> np.ndarray

  def renderizar(
      voces: tuple[VozDeFondo, ...],
      tempo: int,
      factor_tempo: float = 1.0,
      frecuencia_muestreo: int = 48000,
      ganancia: float = 1.0,
      semilla: int | None = 0,
  ) -> PiezaRenderizada
  ```

- [ ] **Step 1: Write the failing tests**

```python
def test_la_misma_pieza_al_mismo_tempo_suena_identica():
    # Dos renders, `np.array_equal`. Es lo que permite afirmar sobre muestras.

def test_un_acorde_SUMA_y_no_se_queda_con_la_mas_grave():
    # Tres notas en el mismo `inicio_pulsos`: el pico de la mezcla es mayor que
    # el de cualquiera de las tres renderizadas sola. El interprete reduce a la
    # mas grave (interprete.py); esto es la decision contraria y a proposito.

def test_se_normaliza_UNA_vez_sobre_la_mezcla_entera():
    # Una pieza con una nota sola y un acorde de seis: el pico global es 1.0 y
    # la nota sola NO llega a 1.0. Normalizar nota a nota daria lo contrario.

def test_la_nota_mas_corta_que_su_periodo_se_alarga_y_no_lanza():
    # Review Focus 2. Una nota de 1 ms a 82 Hz: `cuerda_pulsada` lanzaria
    # (cuerda.py:84-97). El render la alarga al minimo y sale.

def test_rodaja_devuelve_silencio_antes_y_despues_de_la_pieza():
    # instante_pulsos = -4.0 y = duracion + 100: ceros, no excepcion ni recorte
    # corto. Siempre `cuantas` muestras.

def test_rodaja_cae_donde_el_mapa_dice():
    # El instante de una nota se calcula de `tempo`, `factor_tempo` y
    # `frecuencia_muestreo` -NO llamando a rodaja ni leyendo
    # pulsos_por_segundo-, y ahi la rodaja trae energia; un pulso antes, no.

def test_el_factor_de_tempo_estira_la_duracion_y_no_la_afinacion():
    # Al 50 %, duracion_s se dobla. La afinacion se comprueba por el periodo
    # dominante de la primera nota, que NO cambia: es la razon de renderizar de
    # nuevo en vez de resamplear.

def test_sin_voces_devuelve_un_buffer_de_duracion_cero():
    # Review Focus 1. Y con una voz cuya tupla de notas esta vacia, igual.

def test_por_encima_del_tope_de_memoria_falla_LIMPIO_y_lo_dice():
    # El §5 de la spec pide un tope dicho en voz alta: MUESTRAS_MAXIMAS =
    # 48000 * 60 * 12, doce minutos a 48 kHz, que en float32 son 138 MB. Una
    # cancion que al factor pedido pase de ahi levanta ValueError nombrando los
    # minutos que ocuparia y el tope, ANTES de reservar el buffer. Sin esto, una
    # cancion larga al 25 % de tempo reserva cientos de megas y el proceso muere
    # sin decir por que.
```

- [ ] **Step 2: Run them and see them fail**

- [ ] **Step 3: Subir `_duracion_minima_s` y escribir `renderizar`**

`_duracion_minima_s` vive hoy en `nucleo/gemelo/interprete.py:407-424` y la necesitan los dos. Súbela a `nucleo/gemelo/cuerda.py` como `duracion_minima_s` (pública, junto a la función que impone la restricción) y deja al intérprete importándola. **No** la copies: dos copias de esa guarda es el defecto que la 3d persiguió toda la etapa.

`renderizar` suma cada nota en su sitio sobre un buffer de ceros del largo total, con la duración = figura escrita en segundos al tempo efectivo más una cola, acotada por abajo con `duracion_minima_s`. Normaliza al pico una sola vez al final y aplica `ganancia`. La semilla por nota se deriva de la semilla base y del índice de la nota, para que dos notas iguales no suenen a clon exacto y el render siga siendo determinista.

- [ ] **Step 4: Run them and see them pass**

- [ ] **Step 5: Commit**

```bash
git add nucleo/acompanamiento.py nucleo/gemelo/interprete.py nucleo/gemelo/cuerda.py tests/test_acompanamiento.py
git commit -m "feat: el render determinista de las voces de fondo, con los acordes sumados"
```

---

### Task 3: El capturador de salida, hermano del cable falso

**Files:**
- Create: `nucleo/gemelo/salida.py`
- Test: `tests/test_gemelo_salida.py`

**Interfaces:**
- Consumes: `nucleo/sintesis.py:100 SalidaAudio(frecuencia_muestreo, abrir_stream)`.
- Produces:
  ```python
  class StreamCapturado:
      """Lo que `SalidaAudio` cree que es un stream de salida."""
      def start(self) -> None
      def write(self, muestras: np.ndarray) -> None
      def stop(self) -> None
      def close(self) -> None

  class SalidaCapturada:
      """`SalidaAudio` con el stream sustituido, y lo escrito a mano."""
      salida: SalidaAudio
      @property
      def muestras(self) -> np.ndarray      # todo lo escrito, concatenado
      @property
      def bloques(self) -> tuple[int, ...]  # el tamano de cada escritura
      def abrir(self) -> bool
  ```

**Por qué existe:** la spec M7 daba por hecho que el gemelo de la 3d capturaba la salida y **no es verdad** — el gemelo simula la entrada (`nucleo/gemelo/dispositivo.py`) y los capturadores viven dentro de dos pruebas (`tests/test_sesion_practica.py:205`, `tests/test_app_estudio.py:1213`). Esta tarea lo construye donde le corresponde: al lado del cable falso, porque es su hermano simétrico.

- [ ] **Step 1: Write the failing tests**

```python
def test_lo_escrito_se_guarda_en_orden_y_entero():
    # Tres escrituras de tamanos distintos: `muestras` es su concatenacion
    # exacta y `bloques` sus tres tamanos.

def test_la_salida_capturada_se_comporta_como_la_de_verdad():
    # abrir() dos veces es True las dos; cerrar() dos veces no lanza;
    # reproducir() tras cerrar devuelve False sin tocar lo guardado. Es el
    # contrato que `SalidaAudio` ya promete, y el doble tiene que cumplirlo o no
    # sirve para probar a nadie.

def test_un_stream_que_falla_al_escribir_no_mata_a_quien_escribe():
    # Con `fallar_en=2`, la tercera escritura lanza: SalidaAudio lo recoge en
    # `ultimo_error` y devuelve False, que es lo que el acompanante necesita
    # para degradar en vez de tumbar la pasada.
```

- [ ] **Step 2: Run them and see them fail**

- [ ] **Step 3: Implement both classes**

`StreamCapturado` acepta `fallar_en: int | None` para la tercera prueba. `SalidaCapturada` construye `SalidaAudio(abrir_stream=...)` con una **clausura** que devuelve el stream capturado, igual que `nucleo/gemelo/dispositivo.py` hace con `listar` — y, como allí, la clausura no puede vaciarse ni agotarse.

- [ ] **Step 4: Run them and see them pass**

- [ ] **Step 5: Commit**

```bash
git add nucleo/gemelo/salida.py tests/test_gemelo_salida.py
git commit -m "feat: el capturador de salida del gemelo, que la spec daba por hecho y no existia"
```

---

### Task 4: El acompañante, que no lleva reloj

**Files:**
- Create: `nucleo/acompanante.py`
- Test: `tests/test_acompanante.py`

**Interfaces:**
- Consumes: `PiezaRenderizada` (Task 2), `SalidaCapturada` (Task 3), `nucleo/sintesis.py:197 ReproductorTonos` y `:329 Metronomo` como patrón de hilo.
- Produces:
  ```python
  class BloqueadoAhora(Exception):
      """El cabezal no se pudo leer sin esperar. La lanza la clausura que el
      llamante pasa a `iniciar`, y el acompanante la trata reutilizando el
      ultimo cabezal conocido. Vive aqui porque el que la trata es este
      modulo, y quien la lanza (servidor/piezas.py, Task 5) la importa."""


  class Acompanante:
      def __init__(self, salida: SalidaAudio | None = None, bloque: int = 1024) -> None
      @property
      def sonando(self) -> bool
      @property
      def muestras_escritas(self) -> int
      @property
      def cabezales_repetidos(self) -> int   # cuantas veces el candado estaba ocupado
      def cargar(self, renderizada: PiezaRenderizada) -> None
      def iniciar(self, cabezal: Callable[[], float | None]) -> bool
      def pausar(self) -> None
      def reanudar(self) -> None
      def ganancia(self, valor: float) -> None
      def detener(self) -> None
  ```

**La forma del hilo se copia de `Metronomo` y no se inventa:** contador de generación incrementado **antes** que nada en `detener()`, bandera de pausa con `Event`, `join(timeout=1.0)`, y la comprobación de generación **después** de que `reproducir()` retorne. Ese código ya está probado contra el hilo huérfano que sobrevive a un `join` vencido y el docstring de `Metronomo.detener` explica por qué. Lo que **no** se copia es el reloj: `Metronomo` lleva el suyo; el acompañante no lleva ninguno.

- [ ] **Step 1: Write the failing tests**

```python
def test_cada_bloque_sale_del_cabezal_y_no_de_un_contador():
    # Cabezal falso que devuelve SIEMPRE el mismo instante: los diez bloques
    # escritos son identicos entre si. Con un contador propio avanzarian.
    # Es el mutante que mata la idea de un reloj interno.

def test_un_cabezal_que_salta_hace_saltar_el_audio():
    # El cabezal salta del pulso 0 al 8: el bloque siguiente es el del pulso 8,
    # comparado contra `renderizada.rodaja(8.0, bloque)`... NO: contra el mapa
    # calculado a mano desde tempo y frecuencia. Afirmar contra `rodaja` seria
    # tomar la referencia del mismo camino que se prueba.

def test_cabezal_None_escribe_silencio_y_el_hilo_sigue_vivo():
    # Review Focus: la cuenta atras. Ceros exactos, `sonando` sigue True.
    # Parar y arrancar el stream en cada cuenta atras es un chasquido.

def test_cero_deriva_en_diez_mil_bloques():
    # El error entre el instante pedido y el escrito no CRECE entre el primer
    # decil y el ultimo. Se afirma el crecimiento, no un umbral medido en
    # reposo.

def test_cargar_en_caliente_no_deja_pasar_una_muestra_del_buffer_viejo():
    # Review Focus 3. Buffer A (todo 0.5) sonando; cargar(B) (todo -0.5); desde
    # el primer bloque posterior al cambio no hay ni una muestra positiva.

def test_el_candado_ocupado_repite_el_ultimo_cabezal_y_no_abre_silencio():
    # Review Focus 4. El cabezal lanza `BloqueadoAhora` (lo que hara el
    # `acquire(blocking=False)` fallido): el bloque repite el audio anterior,
    # `cabezales_repetidos` sube a 1, y NO hay ceros.

def test_sin_salida_de_audio_iniciar_devuelve_False_y_no_lanza():
    # Degradar, nunca tumbar: es el contrato que el metronomo de la 3c ya tiene.

def test_la_ganancia_se_aplica_suavizada_dentro_del_bloque():
    # De 1.0 a 0.0: el bloque del cambio no empieza en 0 ni acaba en el valor
    # viejo, y el salto maximo entre dos muestras consecutivas es menor que el
    # que daria multiplicar de golpe. Un escalon es un chasquido audible.

def test_detener_mientras_una_escritura_esta_bloqueada_no_vuelve_a_escribir():
    # El mutante del hilo huerfano, el mismo que `Metronomo` ya defiende:
    # el stream se queda 1.5 s dentro de write(), detener() vence su join, y
    # cuando el hilo despierta no escribe ni una muestra mas.
```

- [ ] **Step 2: Run them and see them fail**

- [ ] **Step 3: Implement `Acompanante`**

El hilo, por bloque: pide el cabezal; si lanza `BloqueadoAhora` reutiliza el último y cuenta uno en `cabezales_repetidos`; si es `None` escribe ceros; si no, calcula la rodaja, le aplica la ganancia suavizada y la escribe. `cargar()` y `ganancia()` mutan bajo un candado propio del acompañante (no el de la sesión) y se aplican en el bloque siguiente.

- [ ] **Step 4: Run them and see them pass**

- [ ] **Step 5: Commit**

```bash
git add nucleo/acompanante.py tests/test_acompanante.py
git commit -m "feat: el acompanante lee el cabezal en cada bloque y no lleva reloj propio"
```

---

### Task 5: El cableado en `SesionCarril`, y la regla del micrófono

**Files:**
- Modify: `servidor/piezas.py`, `nucleo/piezas/estudio.py` (los tres campos de `EstadoEstudio`)
- Test: `tests/test_sesion_carril_acompanamiento.py`

**Interfaces:**
- Consumes: `Acompanante` (Task 4), `renderizar` (Task 2), `FondoDisponible` (Task 1).
- Produces:
  - `SesionCarril.cargar_acompanamiento(fondo: FondoDisponible | None, volumen: float = 0.6) -> None`
  - `SesionCarril.acompanamiento(encendido: bool | None = None, volumen: float | None = None) -> dict`
  - `EstadoEstudio` gana `acompanamiento_sonando: bool`, `acompanamiento_posible: bool`, `acompanamiento_es_tu_parte: bool`, y los tres salen en `a_dict()`.
  - `servidor/sesion.py`: `Sesion.entrada_es_el_cable -> bool`, decidido en **un solo sitio** con `nucleo/captura.py:100 buscar_rocksmith`.

- [ ] **Step 1: Write the failing tests**

```python
def test_cargar_acompanamiento_no_pasa_por_iniciar():
    # La puerta unica de iniciar(pieza, plan) no cambia de firma: se comprueba
    # con `inspect.signature` contra la de hoy.

def test_con_el_microfono_el_acompanamiento_no_es_posible():
    # Review Focus 5. Entrada que no es el cable: `acompanamiento_posible` es
    # False y encenderlo deja `acompanamiento_sonando` True pero el estado sigue
    # diciendo que no es posible -el recordatorio no se va-.

def test_la_regla_del_cable_se_decide_UNA_vez_y_viaja_publicada():
    # El mutante que esto mata: una segunda copia de la regla. Se comprueba que
    # `acompanamiento_posible` sale de `Sesion.entrada_es_el_cable` y que nadie
    # mas decide lo mismo por su cuenta. Es la leccion de E3 de la 3d.

def test_el_acompanamiento_se_pausa_con_la_pasada():
    # Pausa del usuario Y pausa por falta de senal: las dos pausan el
    # acompanante, igual que el click.

def test_sin_voces_el_acompanamiento_suena_tu_parte_y_lo_dice():
    # fondo con voces == (): se renderiza la pieza del carril a la mitad de
    # ganancia y `acompanamiento_es_tu_parte` es True.

def test_sin_fondo_cargado_nada_cambia():
    # Review Focus 1. Sin llamar a la puerta: el estado dice no sonando, no
    # posible encender, y la pasada corre igual que hoy.

def test_el_volumen_no_toca_el_plan():
    # Mover el volumen NO llama a `cerrar_repeticion`: la repeticion sigue
    # siendo la misma despues de veinte cambios de volumen.

def test_cambiar_el_factor_de_tempo_renderiza_de_nuevo_UNA_vez():
    # Dos instantaneas con el mismo factor renderizan una sola vez; cambiarlo
    # renderiza otra. Se cuenta sustituyendo `renderizar`.

def test_sin_salida_de_audio_la_pasada_sigue_en_pie():
    # Igual que el click de la 3c: el acompanamiento no arranca y la pasada
    # corre.
```

- [ ] **Step 2: Run them and see them fail**

- [ ] **Step 3: Implement the wiring**

`_ajustar_acompanamiento` calcada de `_ajustar_click` (`servidor/piezas.py:725-806`): misma estructura, mismo tratamiento de la pausa, mismo «sin salida de audio la pasada sigue en pie». **Salida propia**, no la del click: `_parar_click` llama a `self._salida.cerrar()` sin condiciones, así que compartirla sería cerrarle el stream al acompañamiento treinta veces por segundo. El cabezal se le pasa al acompañante como una clausura que intenta el candado **sin bloquear** y lanza `BloqueadoAhora` si está ocupado. Renderiza solo cuando cambia el factor de tempo o el fondo, y **en un hilo aparte**: hasta que el buffer esté, no suena.

- [ ] **Step 4: Run them and see them pass, and run the whole suite**

Run: `export UV_CACHE_DIR="$TMPDIR/uv-cache" && uv run pytest -q`
Expected: las 1367 de hoy siguen verdes.

- [ ] **Step 5: Commit**

```bash
git add servidor/piezas.py servidor/sesion.py nucleo/piezas/estudio.py tests/test_sesion_carril_acompanamiento.py
git commit -m "feat: el acompanamiento entra por su puerta y la regla del microfono se decide una vez"
```

---

### Task 6: El endpoint y las voces de la canción elegida

**Files:**
- Modify: `servidor/app.py:643-700` (donde ya se resuelven canción y pista)
- Test: `tests/test_app_acompanamiento.py`

**Interfaces:**
- Consumes: `voces_de` (Task 1), `cargar_acompanamiento` y `acompanamiento` (Task 5).
- Produces: `POST /api/piezas/acompanamiento` con `{encendido?: bool, volumen?: float}` → el `dict` de `SesionCarril.acompanamiento`. Y `GET /api/piezas/estado` gana los tres campos.

- [ ] **Step 1: Write the failing tests**

```python
def test_al_empezar_una_cancion_las_demas_pistas_se_cargan_solas():
    # POST con {cancion, pista: 1}: el estado dice `acompanamiento_posible` y
    # cuantas voces hay, sin que el cliente haya pedido nada.

def test_un_ejercicio_no_tiene_acompanamiento_de_otras_pistas():
    # Un ejercicio del catalogo no sale de un archivo: suena su propia pieza
    # como guia, y `acompanamiento_es_tu_parte` es True.

def test_el_endpoint_rechaza_un_volumen_fuera_de_rango():
    # -1 y 2.5 -> 400 nombrando la opcion y el valor, instantaneo. Es la
    # leccion de E9 de la 3d.

def test_las_pistas_excluidas_se_publican_con_su_motivo():
    # Una cancion con bateria: el estado dice que una pista se quedo fuera y por
    # que. Un fondo al que le falta algo sin decirlo parece roto.

def test_un_archivo_que_el_lector_no_entiende_no_tumba_la_pasada():
    # `voces_de` lanzando: la pieza se carga igual, sin acompanamiento, y el
    # estado lo dice. El fondo es un extra, no un requisito.
```

- [ ] **Step 2–4: Fail, implement, pass**

- [ ] **Step 5: Commit**

```bash
git add servidor/app.py tests/test_app_acompanamiento.py
git commit -m "feat: la cancion carga sus otras pistas como fondo, y el fondo que falla no tumba la pasada"
```

---

### Task 7: El escaparate toca con fondo

**Files:**
- Modify: `herramientas/gemelo.py`
- Test: `tests/test_herramientas_gemelo.py`

**Interfaces:**
- Consumes: `SalidaCapturada` (Task 3), el cableado (Tasks 5 y 6).
- Produces: `--con-acompanamiento` (captura, no abre altavoces) y `--altavoces` (los abre). El informe gana dos líneas: muestras escritas y desfase máximo contra el cabezal.

- [ ] **Step 1: Write the failing tests**

```python
def test_con_acompanamiento_captura_y_no_abre_altavoces():
    # El escaparate existe para correr sin hardware -por eso pone
    # con_click=False, herramientas/gemelo.py:546- y el sandbox no puede abrir
    # audio. Se comprueba que `abrir_stream` inyectado se uso y que
    # `sounddevice` no se importo.

def test_altavoces_pide_la_salida_de_verdad():
    # Con --altavoces se usa `_abrir_stream_real`. No se ejecuta: se comprueba
    # cual se paso.

def test_el_informe_dice_las_muestras_y_el_desfase_maximo():
    # Las dos cifras salen del capturador y del cabezal, no de lo que el
    # acompanante diga de si mismo.

def test_los_dos_juntos_fallan_al_armar_la_pasada():
    # --con-acompanamiento --altavoces: error nombrando las dos opciones,
    # instantaneo, antes de levantar nada.
```

- [ ] **Step 2–4: Fail, implement, pass**

- [ ] **Step 5: Commit**

```bash
git add herramientas/gemelo.py tests/test_herramientas_gemelo.py
git commit -m "feat: el escaparate toca con fondo, capturando por defecto y por altavoces si se pide"
```

---

### Task 8: El control y el aviso en pantalla

**Files:**
- Modify: `interfaz/src/ControlesEstudio.tsx`, `interfaz/src/Carril.tsx`, `interfaz/src/tiposEstudio.ts`
- Test: `interfaz/src/ControlesEstudio.test.tsx`, `interfaz/src/Carril.test.tsx`

**Interfaces:**
- Consumes: los tres campos del estado (Task 5) y `POST /api/piezas/acompanamiento` (Task 6).

- [ ] **Step 1: Write the failing tests**

```tsx
test("el interruptor sale apagado cuando la entrada no es el cable", () => {
  // Y al tocarlo aparece el aviso: que el sonido del programa va a entrar por
  // el microfono y contar como notas tuyas, y que con auriculares no pasa.
});

test("encenderlo con el microfono deja el recordatorio puesto", () => {
  // Review Focus 5: el recordatorio no se va mientras suene. Es su equipo y su
  // decision, pero no en silencio.
});

test("con la pista propia el control se llama Guia y no Acompanamiento", () => {
  // `acompanamiento_es_tu_parte`.
});

test("el deslizador de volumen no parpadea al soltar", () => {
  // El mismo defecto que la 3d arreglo en el de tempo: se muestra el valor
  // local hasta que el estado se mueve, y el valor mostrado nunca retrocede.
});

test("dice cuantas voces suenan y cuantas se quedaron fuera", () => {
  // Con el motivo. Un fondo incompleto en silencio parece roto.
});
```

- [ ] **Step 2–4: Fail, implement, pass**

Run: `cd interfaz && pnpm test && pnpm lint && pnpm build`

- [ ] **Step 5: Commit**

```bash
git add interfaz/src
git commit -m "feat: el control del fondo, con el aviso del microfono que no se va"
```

---

### Task 9: El anti-objetivo, medido de verdad

**Files:**
- Create: `tests/test_gemelo_realimentacion.py`
- Modify: `nucleo/gemelo/dispositivo.py` (sumar audio ajeno al que entrega)
- Test: el archivo nuevo

**Interfaces:**
- Consumes: `renderizar` (Task 2), `dispositivo_simulado` (`nucleo/gemelo/dispositivo.py`), la cadena de la 3d.
- Produces: `dispositivo_simulado(..., audio_ambiente: np.ndarray | None = None)`, que suma ese audio al que el cable falso entrega, simulando el micrófono abierto.

**Por qué esta tarea es la más importante del plan:** la spec §4.7 decía «el anti-objetivo, medido» y **no medía nada** — la entrada del gemelo y la salida del acompañamiento son dos streams sin ningún camino entre ellos (`nucleo/captura.py:112-116`, `nucleo/sintesis.py:142-146`), así que esa prueba no podía fallar por realimentación ni queriendo. Esta tarea construye el camino.

- [ ] **Step 1: Write the failing tests**

```python
def test_con_el_fondo_colandose_por_la_entrada_el_veredicto_EMPEORA():
    # Se suma el render al audio del cable falso. Aparecen notas inventadas:
    # el veredicto tiene mas invenciones que la misma pasada sin suma. Esto es
    # lo que demuestra que el riesgo es real y no una precaucion escrita.

def test_sin_la_suma_el_veredicto_es_IDENTICO_muestra_a_muestra():
    # El caso del cable. Dos pasadas con la misma semilla, una con
    # acompanamiento sonando y otra sin el: el veredicto es el mismo campo a
    # campo. Si cambia, el audio se esta colando por algun sitio que nadie vio.
```

- [ ] **Step 2: Run them and see the FIRST one fail for the right reason**

El primero tiene que fallar porque hoy no hay `audio_ambiente`, no porque el veredicto no empeore. Compruébalo leyendo el error.

- [ ] **Step 3: Implement `audio_ambiente`**

Un parámetro más del dispositivo simulado, sumado al cuadro que entrega. El valor por omisión es `None` y entonces no cambia **ni una muestra** de lo que el gemelo entregaba antes: compruébalo con `np.array_equal` contra una pasada de la misma semilla.

- [ ] **Step 4: Run them and see them pass**

- [ ] **Step 5: Commit**

```bash
git add nucleo/gemelo/dispositivo.py tests/test_gemelo_realimentacion.py
git commit -m "test: la realimentacion del acompanamiento, medida por los dos lados"
```

---

### Task 10: El README deja de callarse la etapa

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write it**

Añade la 3e a la lista de etapas y quítala de las pendientes. Documenta el fondo con lo que el usuario necesita saber **antes** de encenderlo:

- Que **se sintetiza de la partitura**: es una guía de estudio, no el disco. Suena a cuerda pulsada y **no hay batería** (M5), y eso se nota en una canción de rock.
- Que con el **micrófono del portátil** el programa se puntúa a sí mismo, que por eso arranca apagado, y que con auriculares no pasa. Es lo primero que hay que leer de esta etapa.
- Que en una canción de una sola pista lo que suena es **tu propia parte** como guía, más bajita.
- Que mover el tempo vuelve a renderizar, y que eso tarda décimas.

- [ ] **Step 2: Verify the README does not lie**

Corre **una por una** cada orden que el README manda ejecutar, y mira su código de salida. En la 3d, cuatro defectos reales salieron de esta actividad y de mirar la pantalla, después de que tres revisiones con mutantes no encontraran ninguno.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: el README cuenta el fondo, y lo primero que cuenta es el microfono"
```

---

## Orden y dependencias

```
T1 voces ──┐
           ├──► T2 render ──┬──► T4 acompanante ──► T5 cableado ──┬──► T6 endpoint ──► T8 pantalla
T3 salida ─┘                │                                     │
                            └──────────► T9 realimentacion ◄──────┘
                                                      T7 escaparate ◄── T5, T6
                            T10 README al final
```

- **T1 y T3 son independientes** y pueden ir en cualquier orden; T3 no depende de nada del proyecto salvo `SalidaAudio`.
- **T2 es la puerta:** si el render no es determinista, ninguna prueba de T4 ni de T9 puede afirmar sobre muestras, y el plan cambia de tamaño. El controlador tiene que saberlo antes de despachar T4.
- **T9 depende de T2 y de T5**, pero no de T6 ni de T8: es el gemelo contra la cadena, no contra el servidor.
- **T5 y T6 tocan los dos `servidor/`**, así que no se despachan en paralelo.

## Lo que el plan NO cubre, a propósito

- **Percusión** (M5). Otro motor de síntesis, otra etapa.
- **Audio grabado** (M1). No hay audio de las canciones y pedirlo añadiría licencias a un programa libre.
- **Volumen por pista.** Una pista de fondo, un volumen.
- **Oír el resultado.** El sandbox de desarrollo no puede abrir audio y `open`/`osascript` están bloqueados, así que `--altavoces` se construye y se prueba por el stream que elige, pero **nadie de este lado lo va a oír**. Es del usuario, y está en el §7 de la spec: si el fondo sintético ayuda o estorba es la pregunta que decide si la etapa valió la pena.
