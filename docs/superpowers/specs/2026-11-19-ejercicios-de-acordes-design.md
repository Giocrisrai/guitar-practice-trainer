# Etapa 2b — Ejercicios de acordes

> Diseño. La etapa 2a dejó esto fuera por escrito: «Los acordes son polifonía, un
> problema distinto, y quedan para la etapa 2b con su propia spec»
> (`2026-09-19-ejercicios-monofonicos-design.md` §1 y §7).

## 1. Intención

Un acorde es lo primero que se toca de una canción de verdad y lo último que este
programa sabe ver. Hoy rasgueas un Do y el detector dice `C3`: la fundamental, y
nada más. El carril se lo salta —«de un acorde lee una sola altura»— y el informe
marca el compás «con acordes» en vez de contarlo.

Esta etapa cierra ese hueco por los dos lados que el usuario pidió, y pidió
**ambos**:

1. **Ejercicios de cambio de acorde**: te pide Do, luego Sol, luego Re, y mide si
   el acorde sonó completo y cuánto tardaste en pasar de uno al siguiente.
2. **Acordes dentro de la canción**: el carril deja de excluirlos y una nota de un
   acorde se cobra como cualquier otra.

Los dos descansan sobre un solo núcleo nuevo: saber si un acorde suena.

### Por qué verificar y no transcribir

La decisión central de la etapa, y la que la hace viable con numpy y sin
dependencias nuevas:

**No hace falta reconocer acordes. Hace falta comprobarlos.**

En los dos casos de uso el software ya sabe qué notas espera: el ejercicio porque
las generó, el carril porque están en la pieza. El problema no es «¿qué acorde es
esto?» —transcripción polifónica, un problema de investigación— sino «¿están
sonando estas cinco notas?», que es una pregunta cerrada y se responde midiendo
la energía en los armónicos de cada nota esperada.

Comprobado con señal sintética (cuerdas pulsadas: ocho armónicos con decaimiento
por armónico y fase aleatoria), ventana de 8192 muestras a 48 kHz = 171 ms,
presencia relativa de cada nota esperada respecto de la nota más saliente de la
ventana:

| Caso | Presencia mínima | Media | Qué se puede decir |
|---|---|---|---|
| Do mayor completo (C3 E3 G3 C4 E4) | 0,71 | 0,87 | correcto |
| Do con la 1.ª muda (falta E4) | **0,27 en E4** | 0,71 | incompleto, **y cuál falta** |
| Do con la 2.ª muda (falta C4) | **0,32 en C4** | 0,74 | incompleto, y cuál falta |
| Suena Sol mayor, se pide Do | 0,03 | 0,32 | acorde equivocado |
| Sol mayor completo (G2 B2 D3 G3 B3 G4) | 0,58 | 0,84 | correcto |
| Suena Do mayor, se pide Sol | 0,04 | 0,31 | acorde equivocado |

Los tres veredictos quedan separados por márgenes anchos, y el del medio es el
que importa de verdad: **nombra la cuerda que no sonó**.

Lo que la transcripción daría y esto no: nombrar un acorde que toques por tu
cuenta, sin que nadie lo haya pedido. Queda fuera a propósito (§7) y el README
tiene que decirlo donde hoy dice que los acordes no se siguen.

### La pregunta pedagógica que esto contesta

En la conversación de diseño quedó abierta: «cuando practicas un cambio y sale
mal, ¿qué es lo que sale mal?». El spike la contesta, al menos para lo que el
software puede ver: sale **mudo un dedo**. Una cuerda que no suena baja a 0,27 de
presencia mientras el resto del acorde se queda por encima de 0,70, y el software
puede decir *qué* cuerda. Eso es lo que un profesor dice y una pantalla de
«incorrecto» no.

Así que el ejercicio de cambios **no se limita a acertar o fallar**: cuando el
acorde sale incompleto, dice qué cuerda faltó.

## 2. Objetivos, no objetivos, anti objetivos

**Objetivos**

- Saber, cuadro a cuadro, si un acorde esperado está sonando, y si no, qué nota
  de él falta.
- Un ejercicio de cambios de acorde que mida dos cosas: si el acorde salió
  completo y cuánto tardó el cambio.
- Que el carril cobre las notas de un acorde en vez de saltárselas.
- Cero dependencias nuevas. Todo con numpy, como el resto del núcleo.

**No objetivos**

- Reconocer un acorde que no se ha pedido (transcripción polifónica libre).
- Distinguir inversiones o voicings alternativos del mismo acorde: se comprueban
  las notas de la digitación concreta que el ejercicio generó.
- Medir la afinación de cada nota dentro del acorde. En polifonía los cents por
  nota no son fiables con este método, y prometerlos sería mentir.
- Rasgueo: ritmo de mano derecha, patrones, mute. Otra etapa.

**Anti objetivos** (harían fracasar la etapa aunque funcionase)

- **Un veredicto que no se puede explicar.** Si el programa dice «mal» y el
  usuario no sabe qué cuerda arreglar, el ejercicio no sirve: para eso ya está el
  oído.
- **Cobrar notas que nadie tocó.** El riesgo de medir energía en bandas anchas es
  dar por sonada una nota que solo está como armónico de otra. Más vale decir
  «no lo sé» que inflar el informe.
- **Romper lo monofónico.** El afinador y los cuatro ejercicios de la 2a
  funcionan y están medidos. El detector de acordes se suma, no sustituye.

## 3. Restricciones

- Python puro + numpy en `nucleo/`, sin dependencias nuevas (igual que todas las
  etapas anteriores).
- `.py` sin vocales acentuadas. Los `.ts`/`.tsx` sí llevan acentos en el texto de
  pantalla. Todo en castellano.
- pytest. pnpm, nunca npm.
- La cadencia de análisis es `INTERVALO_DE_ANALISIS_S = 0.021` y **no se toca**:
  está acoplada por escrito a las constantes del detector de pulsaciones.
- El detector de acordes necesita una ventana más larga que el análisis
  monofónico (8192 muestras, 171 ms, frente a 4096) para separar semitonos
  graves: a E2 dos semitonos vecinos distan 4,9 Hz y 4096 muestras dan 11,7 Hz
  por bin. Por tanto **el detector de acordes lleva su propio búfer**, alimentado
  a la misma cadencia pero acumulando más historia. No se cambia
  `PerfilAfinacion.tamano_ventana`, que es lo que el afinador tiene medido.
- Un acorde se sostiene; una nota suelta no. 171 ms de latencia es aceptable para
  un acorde y no lo sería para una escala rápida — otra razón para no unificar las
  dos ventanas.

## 4. Cómo funciona

### 4.1 `nucleo/analisis/espectro.py` — la capa pura

Dos funciones, sin estado, probables con señal sintética:

- `espectro_de_magnitud(muestras, frecuencia_muestreo)` → `(frecuencias, magnitud)`.
  Ventana de Hann y `np.fft.rfft`. La ventana de Hann no es decorativa: sin ella
  el suelo de fuga espectral de una nota fuerte tapa a las débiles del acorde.
- `saliencia_de_nota(frecuencias, magnitud, midi, armonicos=6, ancho_cents=35)` →
  `float`. Suma de la magnitud máxima en una banda de ±35 cents alrededor de cada
  armónico `h` de la nota, ponderada `1/h`.

  Por qué el máximo en una banda y no el valor del bin: la cuerda real no está
  exactamente afinada ni sus armónicos son exactamente múltiplos (inarmonicidad),
  y ±35 cents es un tercio de semitono, suficiente para tolerarlo sin invadir el
  semitono vecino. Por qué `1/h`: los armónicos altos los comparten varias notas
  del acorde y pesan menos como prueba de que *esta* nota suena.

### 4.2 `nucleo/analisis/acordes.py` — el detector

```
DetectorAcordes(frecuencia_muestreo=48000, ventana=8192)
    .procesar(muestras, midis_esperados) -> ResultadoAcorde
```

Es el único objeto con estado de la capa: mantiene un búfer circular de las
últimas `ventana` muestras, porque quien lo alimenta entrega bloques de 1008.

`ResultadoAcorde` (congelado, con `a_dict()` como todo lo que viaja por
WebSocket):

| Campo | Qué es |
|---|---|
| `estado` | `"silencio"`, `"incompleto"` o `"completo"` |
| `presencias` | `dict[int, float]`: por cada MIDI esperado, su presencia relativa 0–1 |
| `faltan` | `tuple[int, ...]`: los MIDI por debajo del umbral, de grave a agudo |
| `nivel_db` | nivel de la ventana, para la misma compuerta de ruido de siempre |

Reglas, en orden:

1. Si el nivel no supera `umbral_ruido_dbfs`, `"silencio"` y `presencias` vacío.
   Es la misma primera puerta que `Analizador.procesar`, y por el mismo motivo.
2. Presencia de cada nota esperada = `saliencia_de_nota(...)` dividida por la
   saliencia máxima sobre **todo el rango del perfil**, no solo sobre las notas
   esperadas. Normalizar contra las esperadas haría que un acorde completamente
   equivocado saliera «completo»: la nota más fuerte de las esperadas valdría 1
   por construcción.
3. `faltan` = las esperadas con presencia `< UMBRAL_PRESENCIA` (0,45; el spike
   separa 0,27–0,32 de 0,58–0,71, así que 0,45 cae en medio del hueco por los dos
   lados).
4. `estado` = `"completo"` si `faltan` está vacío, `"incompleto"` si no.

No hay estado `"equivocado"` aparte: un acorde equivocado es uno al que le faltan
casi todas las notas (media 0,31 en el spike), y `faltan` ya lo dice sin inventar
una categoría más. La pantalla puede decir «te falta la 1.ª» con una ausencia y
«ese no es el acorde» con cuatro, pero esa es una decisión de presentación, no del
núcleo.

### 4.3 El ejercicio de cambios

**Generador nuevo**, quinta familia, al lado de los cuatro de la 2a:
`nucleo/ejercicios/generadores/acordes.py`.

```
generar_cambios(perfil_clave="guitarra_estandar",
                raices=("C", "G", "D"), tipos=("mayor",),
                repeticiones=4, tempo=60) -> Ejercicio
```

El problema de forma: `NotaEsperada` es una nota, y un acorde son varias. Dos
caminos posibles y la razón de elegir el segundo:

- Añadir un campo `midis: tuple[int, ...]` a `NotaEsperada`. Rechazado: el
  evaluador monofónico, el detector de pulsaciones y la pantalla de ejercicios
  leen `NotaEsperada.midi` en todas partes, y un campo que a veces es una nota y
  a veces cinco es el tipo de ambigüedad que luego se paga.
- **Un tipo hermano**, `AcordeEsperado`, y un `Ejercicio` que lleve uno de los
  dos. Es lo que se hace: `Ejercicio.acordes: tuple[AcordeEsperado, ...]` por
  defecto vacía, junto a `notas`. Un ejercicio tiene o notas o acordes, nunca
  ambas, y eso se valida al construirlo.

```
AcordeEsperado:
    nombre: str                       # "Do mayor"
    posiciones: tuple[Posicion, ...]  # la digitacion concreta
    midis: tuple[int, ...]            # derivado de posiciones + perfil
    pulsos: float = 4.0               # un compas por acorde, a 60 ppm = 4 s
```

Las digitaciones son una tabla escrita a mano —`DIGITACIONES`, en ese mismo
módulo— y no se derivan del patrón de intervalos. Un Do mayor abierto es
`x32010` porque así se toca, no porque sea la intersección óptima del conjunto
`{0,4,7}` con el mástil; derivarlo produciría digitaciones que nadie usa. Se
incluyen los acordes abiertos que hacen falta para empezar: **Do, Sol, Re, La,
Mi, La menor, Mi menor, Re menor**. Ocho entradas, cada una con su `nombre` y sus
posiciones, y las cuerdas al aire marcadas aparte de las que no se tocan
(`x` no es lo mismo que traste 0).

**Evaluador nuevo**: `nucleo/ejercicios/cambios.py`, con
`EvaluadorCambios(ejercicio)`. No reutiliza `EvaluadorEjercicio`, y la razón es
que casi nada de ese se aplica: no hay `DetectorPulsaciones` (un rasgueo no es
una pulsación de altura estable), no hay cents, y la unidad de acierto es un
acorde sostenido, no un ataque. Lo que **sí** se copia deliberadamente, porque
funciona y está medido en la 2a:

- **La afinación no bloquea.** Aquí es: la presencia no tiene que ser perfecta.
- **Tras varios intentos se ayuda, no se salta.** Mismo número
  (`INTENTOS_PARA_AYUDA = 5`) y mismo disparador temporal de respaldo.
- **Un cuadro dudoso no cuenta como fallo.** Silencio no es error.

Regla de acierto: el acorde se da por tocado cuando sale `"completo"` durante
`CUADROS_PARA_ACORDE_ESTABLE = 4` cuadros seguidos (84 ms a la cadencia de
análisis). Un cuadro suelto no basta: durante el rasgueo las cuerdas entran una
tras otra y hay un instante en que el acorde está «completo» por accidente a
mitad de camino.

Lo que mide, y es la medida nueva de esta etapa: **el tiempo de cambio**, los
segundos entre el acorde anterior dado por bueno y este. Es el número que un
guitarrista principiante quiere ver bajar.

Informe al terminar: por cada acorde, cuántos intentos, qué cuerdas fallaron más
veces y el tiempo de cambio; y la media de los tiempos de cambio, que es la cifra
de cabecera.

### 4.4 El carril deja de excluir acordes

Hoy el carril lee una sola altura de un acorde y el informe marca el compás «con
acordes». El cambio: cuando el cabezal del carril llega a un grupo de notas que
comparten `inicio_pulsos`, se usa el detector de acordes con los MIDI de ese
grupo y se cobran **todas** las que salgan presentes, cada una con su veredicto.

Lo que no cambia: las notas sueltas siguen yendo por el camino monofónico, que es
el que da cents y afinación. Un acorde da presencia, no cents, y el informe tiene
que distinguirlo en vez de dejar un hueco donde antes decía «con acordes».

### 4.4.1 Qué significan `desfase_s`, `clasificacion` y `cents` en una nota de acorde

Esto la §4.4 no lo resolvió, y sin resolverlo no hay código: el informe del carril
está escrito entero en cents y desfase, y una nota cobrada por presencia no tiene
ni lo uno ni lo otro. La decisión, tomada al implementar la tarea 8:

**Un acorde del carril se cobra en dos mitades, y las dos se dicen distintas.**

1. **El rasgueo tiene UN ataque**, y ese ataque se adjudica como siempre:
   `DetectorPulsaciones` da una `Pulsacion`, `_adjudicar` la lleva a una nota del
   grupo por altura y cercanía, y esa nota sale con su `desfase_s`, su
   `clasificacion` y sus `cents` reales. No cambia nada del camino monofónico.
2. **El resto de las notas del grupo se cobran por presencia**, con el detector de
   acordes sobre la ventana cruda. Las que suenan salen con `cents=None`,
   `desfase_s=None`, `clasificacion=None`, `afinada=None` y un campo nuevo,
   `por_presencia=True`.

**Por qué `None` y no un número prestado.** `NotaTocada` ya define `None` como «no
se supo», y una cuerda sin ataque propio genuinamente no tiene desviación ni
desfase medibles. Copiarle el desfase a la nota hermana que sí tuvo ataque
publicaría la colocación del rasgueo como si fuera la de cada cuerda, y el informe
promediaría seis copias del mismo número: la estadística de tiempo saldría seis
veces más segura de lo que es. `por_presencia` es justo lo que las mantiene fuera
de esas cuentas.

**El ataque sigue siendo obligatorio.** La presencia solo se cobra sobre un grupo
que ya tiene una nota cobrada por ataque en este mismo cuadro. Sin esa puerta, los
armónicos de un acorde vecino cobrarían un acorde que nadie tocó —el falso
positivo medido en el umbral— y lo harían encima sin que suene un ataque. Con
ella, el detector monofónico es el que autoriza y el de acordes solo reparte.

**Qué no cubre.** Una nota de acorde que no suena no deja marca de fallo: queda sin
cobrar, igual que hoy queda una nota suelta que nadie tocó. Decir *qué cuerda* del
acorde escrito falló es la pantalla de ejercicios, no el carril.

## 5. Manejo de errores

| Situación | Cuándo se detecta | Qué muestra |
|---|---|---|
| Se pide un acorde que el perfil no alcanza (bajo de 4 cuerdas, digitación de 6) | Al **generar** | Se rechaza nombrando el acorde y el perfil |
| Una raíz sin digitación en la tabla | Al **generar** | Se rechaza listando las disponibles |
| Un `Ejercicio` con notas y acordes a la vez | Al **construirlo** | `ValueError` |
| La señal desaparece a mitad de ejercicio | Igual que en la 2a | Pausa y reutiliza el aviso del afinador |
| Una cuerda nunca llega a sonar | Tras `INTENTOS_PARA_AYUDA` | Se resalta esa cuerda en el mástil, no se salta el acorde |

## 6. Estrategia de pruebas

**La capa pura se prueba exactamente.** `espectro_de_magnitud` y
`saliencia_de_nota` son funciones de numpy a numpy: una senoide de 440 Hz tiene
su máximo donde debe, una nota con armónicos da saliencia alta en su fundamental
y baja en el semitono vecino, una ventana en silencio da cero.

**El detector se prueba con acordes sintéticos**, que es lo que hizo el spike y
lo que permitió decidir el diseño antes de escribirlo. Los casos de la tabla de
§1 se convierten en pruebas, con sus números: Do completo da `"completo"`; Do sin
la 1.ª da `"incompleto"` con `faltan == (64,)`; Sol contra Do esperado da
`"incompleto"` con cuatro ausencias. **Esas pruebas afirman el comportamiento, no
los valores exactos del spike**: una prueba que fije 0,71 se rompería al cambiar
el número de armónicos sin que nada estuviera mal.

**El evaluador de cambios se prueba sin audio**, igual que el de la 2a: consume
`ResultadoAcorde`, que es un dato. Se escribe la secuencia exacta de alguien que
tarda dos segundos en el cambio, o que deja muda la primera cuerda tres veces, y
se verifica el informe en milisegundos.

**El carril con acordes se prueba contra una pieza con un acorde**, que ya existe
en las pruebas (`pieza_con_acorde` en `tests/test_gemelo_interprete.py`) y hoy
afirma lo contrario: «el gemelo no finge polifonía: el detector real es
monofónico». Esa prueba cambia de sentido en esta etapa, y el cambio tiene que
ser explícito, no silencioso.

**Lo que necesita al usuario y su guitarra**, y por tanto queda listado como
pendiente y no como hecho:

- Rasguear cada uno de los ocho acordes de la tabla y comprobar que sale
  `"completo"`. El spike usa cuerdas sintéticas; una pastilla real tiene otro
  reparto de armónicos.
- Dejar una cuerda muda a propósito y comprobar que el software nombra **esa**.
- Calibrar `UMBRAL_PRESENCIA` con señal real. 0,45 sale del hueco del spike, y el
  hueco real puede ser más estrecho.

## 7. Alcance

**Incluye:** la capa de espectro, el detector de acordes por verificación, el
generador de cambios con su tabla de ocho digitaciones, el evaluador de cambios
con el tiempo de cambio y el informe, el carril cobrando acordes, la pantalla de
ejercicios de cambios, y las pruebas de §6.

**No incluye, y es deliberado:**

- **Transcripción polifónica libre** (nombrar un acorde que no se ha pedido). La
  §1 explica por qué no hace falta para esta etapa; si alguna vez hace falta, es
  otra etapa y otro método.
- **Cents por nota dentro del acorde.** No son fiables con este método.
- **Rasgueo**: patrones de mano derecha, acentos, mute.
- **Cejilla y digitaciones con barra** más allá de las ocho de la tabla.
- **Inversiones y voicings alternativos.**

## 8. Lo que queda al constructor

- El orden de las tareas. El recomendado es el que la conversación fijó:
  detección primero (es lo que todo lo demás necesita), después el ejercicio de
  cambios, y al final levantar la exclusión del carril.
- Los nombres exactos de las constantes y los módulos, dentro de lo que §4
  nombra.
- Cómo se dibuja un acorde en la pantalla de ejercicios. El requisito es que se
  vea la digitación en el mástil y que, cuando falte una cuerda, se vea **cuál**.
  La forma concreta —diagrama de acorde vertical, el mástil que ya existe— es del
  constructor.
- Si el carril necesita una franja visual distinta para un acorde. El requisito
  es que una nota de acorde se cobre; que se vea distinta es deseable, no
  obligatorio.
