# Etapa 3e — La pieza sonando de fondo mientras la sigues

> Diseño de la etapa que sigue a la 3d (el gemelo digital, fusionada en `main`).
> Spec anterior: `docs/superpowers/specs/2026-11-02-gemelo-digital-design.md`.

## 1. Qué se construye y por qué

Hoy el carril es **música muda**. Las notas caen, el detector las juzga, el
informe cuenta los aciertos — y no suena nada salvo un click opcional. Lo que el
usuario pidió desde el principio no es un instrumento de medida:

> «no solo que pienso en guitar hero rocksmith y quiero darle esa experiencia»
> «va siendo dinamico se va mostrando y voy tocando y me va indicando si voy bien
> mal sei debo repetir etc»
> «poder integrar una buena experiencia mientras aprendemos y tocamos y nos
> divertimos aprendemos»

En Guitar Hero y en Rocksmith **la canción suena**. Es lo que convierte una
columna de rectángulos cayendo en tocar música: el pulso lo llevas de oído, sabes
si vas tarde antes de que te lo diga el programa, y equivocarte **se oye**. Esta
etapa pone eso.

Lo que la hace posible es la 3d: el motor de síntesis de cuerda pulsada
(`nucleo/gemelo/cuerda.py`) ya existe, está medido y es determinista. No hace
falta ningún archivo de audio ni ninguna dependencia nueva para que una pieza
suene: la pieza **ya trae las notas**, y sabemos convertir una nota en sonido.

### Decisiones del usuario, tomadas en la conversación

Ninguna. Al abrir esta etapa el usuario dijo «avanza» tres veces y pidió
expresamente saltarse las preguntas de diseño. Todo lo que sigue es mío, y por eso
va enumerado y con su precio: es lo que él tiene que poder revisar y tumbar.

El marco que sí viene de él, de las etapas anteriores y sigue vigente:

- La experiencia manda sobre la medición.
- No puede probar con la guitarra ahora mismo, así que **todo tiene que poder
  verse sin hardware** (es la razón de existir de la 3d).
- Software libre, sin dependencias de terceros si se puede evitar.
- Español en código, comentarios y pruebas; los `.py` sin tildes.

### Decisiones mías, que el usuario no tomó

- **M1. La pieza de fondo se SINTETIZA de la partitura. No hay archivos de
  audio.** Las canciones entran como `.gp5`, MusicXML, MIDI o tablatura (etapa
  3b): son partituras, no grabaciones, así que no hay un audio que reproducir
  aunque quisiéramos. Y pedirle al usuario el MP3 de cada canción añadiría un
  problema de licencias a un programa libre. *Precio si me equivoco:* suena a
  cuerda pulsada sintética y no a la banda del disco; una canción que el usuario
  conoce bien va a sonar pobre comparada con su recuerdo.
- **M2. El acompañamiento NO lleva reloj propio: lee el cabezal del carril en cada
  bloque.** En cada bloque de salida pregunta a la sesión por dónde va
  (`instante_pulsos`) y escribe la rodaja de audio que corresponde a ese instante.
  Por qué: cualquier reloj propio **deriva** del carril, y el carril ya sabe de
  bucles, cuenta atrás, saltos de compás, pausa por falta de señal y factor de
  tempo. Un segundo reloj sería un segundo sitio donde el bucle puede
  equivocarse, y la 3d gastó una etapa entera demostrando que dos copias de la
  misma regla nunca son la misma regla. *Precio:* la latencia es de un bloque
  (~21 ms) y si el cabezal salta, el sonido salta — que es lo correcto: si saltas
  de compás, la música salta contigo.
- **M3. Se renderiza la pieza entera por adelantado, una vez por (pieza, factor de
  tempo).** Medido con el motor de la 3d en esta máquina: **200 notas de medio segundo en
  55 ms**, y las mismas 200 notas de segundo y medio en **151 ms** — el coste
  escala con la **duración sonando**, no con el número de notas, que es lo que
  importa cuando el usuario baja el tempo al 50 % y cada nota dura el doble.
  Renderizar una canción entera cuesta décimas de segundo, así que volver a
  renderizarla cuando mueves el tempo es gratis y evita tener que resamplear (que
  cambiaría la afinación). *Precio:* memoria — tres minutos en mono float32 a
  48 kHz son ~34 MB — y una espera de décimas al mover el deslizador de tempo,
  que hay que absorber sin cortar el sonido.
- **M4. Suenan las OTRAS pistas del archivo, no la tuya.** Es la experiencia
  Rocksmith: tú eres el guitarrista que falta. `pistas_de()` ya enumera las pistas
  de un Guitar Pro. Si la canción **solo tiene una pista**, suena la tuya a
  volumen bajo, como guía — que es lo que de verdad quiere quien está aprendiendo
  la pieza. *Precio:* en una canción de una pista, el acompañamiento te sopla la
  respuesta; por eso va más bajo y se puede apagar.
- **M8. El acompañamiento NO pasa por `Pieza`.** Es la corrección más importante
  que trajo la revisión de constructor. `Pieza` exige **cuerda y traste por nota**,
  y los lectores de MIDI y MusicXML **lanzan `ValueError`** cuando una pista no
  cabe en la afinación del usuario (`desde_midi.py:165-210`,
  `desde_musicxml.py:186-226`): o sea, el caso normal de un piano, un bajo de
  cinco cuerdas, unas cuerdas o una voz. Pero para **sonar** no hace falta
  digitar nada: hacen falta alturas e instantes. Así que el fondo viaja en un tipo
  propio, `VozDeFondo`, y el acompañamiento funciona en los cuatro formatos en vez
  de solo en Guitar Pro. *Precio:* un tipo más y un camino de lectura más que
  mantener, a cambio de que la etapa no quede reducida a un formato.
- **M5. La percusión queda FUERA de esta etapa, y se dice en el README.**
  Karplus-Strong sintetiza una cuerda pulsada; una batería no es una cuerda. Una
  pista de percusión ni siquiera entra al modelo `Pieza` (no declara cuerdas, y
  `_motivo_no_usable` ya lo explica). Hacer batería es otro motor de síntesis y
  otra etapa. *Precio:* el fondo no tiene groove, y en una canción de rock eso es
  justo lo que marca el pulso. Lo compensa el click, que ya existe.
- **M6. El acompañamiento arranca APAGADO cuando la entrada no es el cable, y la
  interfaz dice por qué.** Ver §2 anti-objetivos y §5: es el riesgo central de la
  etapa. *Precio:* un usuario con cable y un dispositivo que no se llame
  «Rocksmith» (otra interfaz de audio) tiene que encenderlo a mano una vez.
- **M7. La salida de audio se inyecta, y el gemelo digital verifica la
  sincronía sin altavoces.** `SalidaAudio` ya admite un `abrir_stream`
  sustituible — eso es verdad y está comprobado (`nucleo/sintesis.py:142-146`).
  Lo que **no** existe todavía, y mi primera versión de esta spec daba por hecho,
  es el capturador: el gemelo de la 3d simula la **entrada**
  (`nucleo/gemelo/dispositivo.py`), no la salida, y los capturadores de muestras
  viven solo dentro de dos pruebas (`tests/test_sesion_practica.py:205`,
  `tests/test_app_estudio.py:1213`). **Esta etapa lo construye**, en
  `nucleo/gemelo/`, al lado del cable falso: es su hermano simétrico. Es la lección
  de la 3d hecha requisito: **si no se puede ver sin hardware, no se verifica**, y
  cuatro de los defectos reales de la 3d salieron de correr el programa y mirarlo,
  no de las pruebas.

## 2. Objetivos, no-objetivos y anti-objetivos

**Objetivos**

1. Que la pieza suene mientras la tocas, sincronizada con el cabezal del carril,
   sin deriva acumulada por larga que sea la pasada.
2. Que respete lo que el carril ya hace: cuenta atrás, bucle de un tramo, salto de
   compás, factor de tempo, pausa por falta de señal, fin de pasada.
3. Que se pueda encender, apagar y subir o bajar **en caliente**, sin cortar la
   pasada.
4. Que el gemelo digital lo verifique entero sin altavoces ni guitarra, con
   aserciones sobre muestras, no sobre la fe.
5. Que el usuario sepa, sin leer código, cuándo el acompañamiento puede
   envenenar su puntuación y qué hacer (auriculares).

**No-objetivos**

- Percusión (M5).
- Reproducir audio grabado: MP3, WAV, stems (M1).
- Mezcla por pistas con volumen independiente de cada una. Una pista de
  acompañamiento, un volumen. Si hace falta más, es otra etapa.
- Efectos: distorsión, reverb, amplificadores. La etapa 4 los nombra.
- Exportar el acompañamiento a un archivo.
- Transportar de tono o cambiar la afinación del acompañamiento.

**Anti-objetivos** — cosas que harían fracasar la etapa aunque funcionara

- **Que el programa se puntúe a sí mismo.** Si la entrada es el micrófono del
  portátil, el acompañamiento entra por la entrada y el detector de ataques lo
  cobra como notas tuyas: el informe se llena de aciertos y fallos que no tocó
  nadie. Es la peor forma de fallar que tiene esta etapa, porque **no se nota**:
  los números salen y están mal. Por eso M6.
- Que el fondo vaya desacompasado. Un acompañamiento que se desfasa 200 ms es
  peor que el silencio: desaprendes el pulso.
- Que el audio corte la pasada. Quedarse sin salida de audio tiene que degradar
  la experiencia, nunca tumbar la sesión — igual que el metrónomo de la 3c.
- Que el deslizador de tempo chasquee o deje un silencio al moverlo.

## 3. Las piezas

### 3.1 `nucleo/acompanamiento.py` — la pieza renderizada

Función pura, sin hilos y sin audio: convierte unas **voces de fondo** y un factor
de tempo en un buffer de muestras y el mapa para indexarlo.

**Es un módulo nuevo, no un refactor de `interprete._generar`.** Ya existe ahí un
render determinista que suma `cuerda_pulsada` sobre un buffer
(`nucleo/gemelo/interprete.py:426-467`), y la revisión de constructor hizo bien en
preguntar por qué no se reutiliza. Difieren en tres cosas que son decisiones, no
detalles:

1. **Acordes.** El intérprete reduce un acorde a su nota más grave, porque simula
   a un guitarrista que va a ser juzgado por un detector monofónico. El
   acompañamiento los **suma**: la limitación es del detector, no del sintetizador,
   y un fondo sin acordes no es un fondo.
2. **Normalización.** El intérprete recorta; el acompañamiento normaliza al pico
   **una sola vez sobre la mezcla entera**, porque si normalizara nota a nota una
   nota sola sonaría igual de fuerte que un acorde de seis.
3. **El eje.** El intérprete mide el tramo con su silencio de cabecera (es una
   *pasada*); el acompañamiento mide la **pieza entera** desde su pulso cero,
   porque a él lo indexa el cabezal.

Lo que **sí** se reutiliza, y no se copia: la guarda del mínimo
(`duracion_minima_s`, hoy en `nucleo/gemelo/cuerda.py:114`, que es adonde la
subió la Task 2; cuando se escribió esta especificación vivía como
`interprete._duracion_minima_s`).
`cuerda_pulsada` **lanza** si la nota no llega a un periodo
(`nucleo/gemelo/cuerda.py:84-97`), así que esa guarda es obligatoria y tener dos
copias de ella sería exactamente el defecto que la 3d persiguió toda la etapa.
Se sube a un sitio común y los dos la importan.

```python
@dataclass(frozen=True)
class PiezaRenderizada:
    muestras: np.ndarray        # mono float32, normalizada
    frecuencia_muestreo: int
    pulsos_por_segundo: float   # tempo efectivo / 60
    duracion_s: float

    def rodaja(self, instante_pulsos: float, cuantas: int) -> np.ndarray:
        """Las `cuantas` muestras que suenan en ese instante de la pieza.

        Devuelve silencio -no lanza- antes del comienzo y despues del final:
        el cabezal vive en la PASADA, que incluye cuenta atras, y una pasada
        puede quedarse parada mas alla del final de la pieza.
        """

@dataclass(frozen=True)
class VozDeFondo:
    """Una pista que solo tiene que SONAR, y por eso no pasa por `Pieza`.

    `Pieza` exige cuerda y traste por nota porque su destino es el carril, que
    te dice donde poner los dedos. Un piano, una voz o un bajo de cinco cuerdas
    no caben ahi -los lectores de MIDI y MusicXML lanzan `ValueError`- y no
    tienen por que: para sonar bastan alturas e instantes.
    """

    nombre: str
    instrumento: str                  # la familia General MIDI, informativa
    notas: tuple[NotaDeFondo, ...]    # midi: float, inicio_pulsos, duracion_pulsos


def renderizar(
    voces: tuple[VozDeFondo, ...],
    tempo: int,
    factor_tempo: float = 1.0,
    frecuencia_muestreo: int = 48000,
    ganancia: float = 1.0,
    semilla: int | None = 0,
) -> PiezaRenderizada
```

Reglas que esta función fija:

- Cada nota se sintetiza con `cuerda_pulsada` a la altura de `midi`, con duración
  = su figura escrita (en segundos al tempo efectivo) **más una cola**, y se suma
  en su sitio. Los acordes se suman (ver arriba).
- La semilla por defecto es fija: la misma pieza al mismo tempo suena **idéntica**
  dos veces. Es lo que permite afirmar sobre muestras en una prueba.
- Se normaliza al pico una sola vez, al final, sobre la mezcla entera. Normalizar
  nota a nota haría que una nota sola suene igual de fuerte que un acorde de seis.
- Sin voces, o con voces sin notas, devuelve un buffer de un instante y duración
  0. Nadie debería tener que preguntar antes de llamar.

### 3.2 `nucleo/acompanante.py` — el que lo hace sonar

La clase con hilo, hermana de `Metronomo` y construida con su misma forma
(generación, bandera de pausa, escritura bloqueante, `join(timeout=1.0)`), porque
esa forma ya está probada contra el hilo huérfano.

```python
class Acompanante:
    def __init__(self, salida: SalidaAudio | None = None,
                 bloque: int = 1024) -> None
    @property
    def sonando(self) -> bool
    @property
    def muestras_escritas(self) -> int
    def cargar(self, renderizada: PiezaRenderizada) -> None
    def iniciar(self, cabezal: Callable[[], float | None]) -> bool
    def pausar(self) -> None
    def reanudar(self) -> None
    def ganancia(self, valor: float) -> None
    def detener(self) -> None
```

- **`cabezal` es una función**, no un objeto de sesión: el acompañante no sabe qué
  es una `SesionDeEstudio` y no puede tocarla. Devuelve el instante de la pieza en
  pulsos, o `None` si ahora mismo no hay nada que suene (cuenta atrás, pasada
  terminada, sin pasada). Con `None` escribe silencio, no para el hilo: parar y
  arrancar el stream en cada cuenta atrás es un chasquido.
- El hilo **no acumula posición**. Cada bloque: pregunta el cabezal, calcula la
  rodaja, la escribe. Si el cabezal salta, la música salta. No hay deriva posible
  porque no hay nada que derive.
- `cargar()` puede llamarse **con el hilo sonando** (es lo que pasa al mover el
  tempo). El cambio de buffer se hace bajo candado y se aplica en el bloque
  siguiente.
- `ganancia()` también en caliente, y se aplica suavizada a lo largo del bloque:
  multiplicar de golpe es un chasquido audible.

### 3.3 El cableado: POR ENCIMA del carril, no dentro

La revisión de constructor encontró el agujero de mi primera versión: el carril
tiene **una sola puerta** —`SesionCarril.iniciar(pieza, plan)` recibe una `Pieza`
y nada más—, y el identificador de la canción y el número de pista se quedan
arriba, en el endpoint (`servidor/app.py:643-700, 748-771`). Eso es deliberado y
no se rompe. Mi spec pedía que el carril supiera de qué archivo salió su pieza, y
eso habría abierto una segunda puerta.

**Decisión:** el acompañamiento vive en `SesionCarril` —que es donde está el
cabezal— pero **entra por una puerta propia**, no por `iniciar`. Así la puerta
única de `iniciar(pieza, plan)` queda intacta y el carril nunca tiene que saber de
qué archivo salió su pieza. Con eso:

- `SesionCarril` gana `_acompanante`, `_ajustar_acompanamiento` —llamada desde los
  dos sitios desde los que ya se llama `_ajustar_click`, con la misma forma: misma
  pausa, mismo «sin salida de audio la pasada sigue en pie»— y un método nuevo
  `cargar_acompanamiento(voces, volumen)`, que es la puerta.
- Quien resuelve las voces de fondo es el endpoint que ya elige la pista, porque es
  el único que tiene la ruta del archivo (`servidor/app.py:696-700`). Las pasa
  hechas por esa puerta; no se re-leen en cada instantánea. Si nadie llama a la
  puerta, no hay acompañamiento y nada cambia.
- **Salida de audio propia, no la del click.** Compartirla no se puede:
  `_parar_click` llama a `self._salida.cerrar()` sin condiciones
  (`servidor/piezas.py:795-806`) y, con `con_click` falso, eso ocurre en cada
  instantánea, treinta veces por segundo. Hoy es inocuo —el stream ya está en
  `None` y `cerrar()` coge el candado y vuelve— pero con el acompañamiento
  compartiendo esa salida sería cerrarle el stream treinta veces por segundo.
  Dos `SalidaAudio` son dos streams de CoreAudio, que es lo que hace cualquier
  programa con dos fuentes de sonido. *Esto corrige la frase falsa de mi §5.*
- **Ni el interruptor ni el volumen van en `PlanDePasada`.** Todo cambio de plan
  hace `cerrar_repeticion(cuenta_como_vuelta=False)`
  (`nucleo/piezas/estudio.py:1001-1028`): un deslizador de volumen arrastrado
  serían decenas de cierres de repetición, y encender el fondo a mitad de pasada
  te cortaría la vuelta. Son controles **vivos** del acompañante, con su propio
  endpoint, y no tocan el plan.
- `EstadoEstudio` publica tres campos: `acompanamiento_sonando`,
  `acompanamiento_posible` y `acompanamiento_es_tu_parte`. El segundo es «la
  entrada es el cable», y se decide **en un solo sitio** y viaja publicado. Es
  literalmente la lección de E3 de la 3d: la regla del aviso del cable estaba
  escrita dos veces, en dos idiomas, y las dos no eran la misma.

### 3.4 De dónde salen las voces de fondo

Un módulo nuevo, `nucleo/piezas/voces_de_fondo.py`, con un camino por formato que
**no digita nada** (M8):

- `voces_de(ruta, pista_excluida) -> tuple[VozDeFondo, ...]`. Lee el archivo con el
  mismo parser que ya usa el lector de ese formato y saca altura e instante de cada
  nota. No construye `Pieza`, no llama a `digitacion.py`, no puede lanzar
  `ValueError` por afinación.
- Funciona en los cuatro formatos de la 3b, no solo en Guitar Pro.
- `pista_excluida` es la tuya: lo que suena es el resto (M4).
- Las pistas de **percusión** se descartan, y se dice cuántas y por qué (M5). El
  resto de pistas sin notas también.
- Si no queda ninguna voz, el llamante renderiza **tu propia pieza** con la
  ganancia a la mitad y el estado lo marca con `acompanamiento_es_tu_parte`, para
  que la interfaz lo llame *Guía* y no *Acompañamiento*.
- La interfaz dice cuántas voces suenan y cuántas se quedaron fuera y por qué: un
  fondo al que le falta el bajo sin que nada lo diga es un fondo que parece roto.

### 3.5 La interfaz

Un control en `ControlesEstudio.tsx`, al lado del click: interruptor y deslizador
de volumen. Y el aviso, que es la mitad importante:

- Con `acompanamiento_posible` falso: el interruptor sale apagado y, al tocarlo,
  explica que la entrada no es el cable Rocksmith, que el sonido del programa va a
  entrar por el micrófono y contar como notas tuyas, y que con auriculares no pasa.
  Se puede encender de todas formas — es su equipo y su decisión — y entonces el
  carril lleva un recordatorio permanente mientras suene.
- Con el acompañamiento sonando y la pista siendo la tuya, el control se llama
  **Guía**, no **Acompañamiento**.

## 4. Lo que el gemelo digital tiene que verificar

Esta sección es el requisito que la 3d compró con una etapa entera de trabajo. Todo
lo de abajo se verifica **sin altavoces y sin guitarra**, con la salida inyectada.

1. **Sincronía**: con un cabezal falso que avanza a pulsos conocidos, la muestra
   escrita en el bloque *n* es la que el mapa dice que corresponde a ese instante.
   Afirmado contra el mapa, **no** contra lo que devolvió `rodaja()` — que es el
   error que esta rama registró nueve veces: *la aserción tomaba su valor de
   referencia del mismo camino de código que probaba*.
2. **Cero deriva**: diez mil bloques seguidos, y el error entre el instante pedido
   y el instante escrito no **crece**. Se afirma el crecimiento, no un umbral
   medido en una máquina en reposo (lección de la 3d, ruling 29).
3. **El bucle**: con el cabezal dando vueltas a un tramo, el audio vuelve al
   principio del tramo y no sigue recto.
4. **La cuenta atrás**: cabezal `None` → silencio exacto, y el hilo sigue vivo.
5. **El tempo en caliente**: `cargar()` durante la reproducción no produce ni un
   corte ni una muestra del buffer viejo después del cambio.
6. **La pasada completa por el escaparate**: `herramientas/gemelo.py` gana
   `--con-acompanamiento`, que **captura** las muestras y no abre altavoces, y
   `--altavoces`, que sí los abre. Por defecto captura, por dos razones: el
   escaparate existe para poder correr sin hardware (hoy pone `con_click=False`
   justo por eso, `herramientas/gemelo.py:546`) y además el sandbox de desarrollo
   no deja abrir audio. Con `--altavoces` es el usuario quien lo oye, que es la
   otra mitad de su razón de ser. El informe del escaparate dice cuántas muestras
   escribió y con qué desfase máximo contra el cabezal.
7. **El anti-objetivo, medido de verdad.** Mi primera versión decía «medido» y no
   medía nada: la entrada del gemelo y la salida del acompañamiento son dos
   streams sin ningún camino entre ellos (`nucleo/captura.py:112-116` y
   `nucleo/sintesis.py:142-146`), así que esa prueba no podía fallar por
   realimentación ni queriendo. La prueba real **construye el camino**: se suma el
   render del acompañamiento al audio que el cable falso entrega por la entrada,
   simulando el micrófono abierto, y se afirman las dos mitades:
   - **con** la suma, el veredicto empeora (aparecen notas inventadas) — eso
     demuestra que la contaminación es real y que el riesgo no es teórico;
   - **sin** la suma, que es el caso del cable, el veredicto es idéntico al de la
     misma pasada sin acompañamiento, muestra a muestra.
   Las dos mitades juntas son lo único que convierte §5 en un hecho medido en vez
   de en una precaución escrita.

## 5. Riesgos

- **Realimentación (el grande).** Micrófono del portátil + acompañamiento por los
  altavoces = el programa se puntúa a sí mismo, y los números salen bonitos y
  falsos. Mitigado por M6 y por §4.7, que lo mide. Lo que **no** puede mitigar el
  programa: el usuario con auriculares a volumen de concierto y micrófono abierto.
  El aviso es lo único que hay ahí.
- **Suena pobre.** Una canción que el usuario se conoce de memoria va a sonar a
  cuerda sintética sin batería. Es el precio de M1 y M5 y hay que decirlo en el
  README antes de que lo descubra: esto es una **guía de estudio**, no el disco.
- **El coste de renderizar en el hilo equivocado.** 55 ms por 200 notas es barato,
  pero una canción de 2000 notas son ~0,6 s, y hacerlo en el hilo del WebSocket
  congelaría la interfaz. Va en un hilo aparte, y hasta que esté el fondo no suena
  — nunca al revés, nunca a medias.
- **El candado de la sesión, que sí hay que absorber.** Esta era la otra frase
  falsa de mi primera versión: escribí que «el acompañante no tiene que absorber
  nada porque no lleva reloj». Al contrario. Leer el cabezal exige el candado de
  la sesión, y ese candado lo retiene el hilo HTTP mientras `_ajustar_click`
  espera a un `stream.write()` en vuelo — un coste que el propio código ya tiene
  medido y documentado (hoy en el docstring de
  `SesionCarril._ajustar_click`, `servidor/piezas.py:943`; la cita original
  apuntaba a las líneas 707-721, que el código ya movió). Si el hilo del
  acompañamiento se queda esperando ese candado, se queda sin escribir su bloque y
  eso **se oye**. Decisión: el hilo del acompañamiento **nunca espera** el candado.
  Lo intenta sin bloquear y, si está ocupado, reutiliza el último cabezal conocido
  para ese bloque, lo que como máximo repite 21 ms de audio en vez de abrir un
  hueco de silencio. Hay que medir cuántas veces pasa, no suponerlo.
- **Dos streams de salida.** El click y el acompañamiento tienen cada uno su
  `SalidaAudio` (§3.3), así que son dos streams de CoreAudio abiertos a la vez. Es
  lo normal, pero hay que comprobarlo en el equipo del usuario: dos streams con
  tamaños de bloque distintos pueden pelearse por el dispositivo.
- **Memoria.** Una canción larga al 50 % de tempo es el doble de muestras. Un
  tope, dicho en voz alta, y un fallo limpio por encima de él.

## 6. Dependencias

Ninguna nueva. `numpy` y `sounddevice` ya están; el motor de síntesis es de la 3d.

## 7. Lo que sigue siendo del usuario

Lo que ninguna prueba puede juzgar y que él tiene que decir cuando conecte:

- Si el fondo sintético **ayuda o estorba**. Es la pregunta que decide si esta
  etapa valió la pena.
- Si 0,6 es el volumen correcto de partida, y si la guía de una sola pista debe
  sonar más baja aún.
- Si la latencia de un bloque se nota al tocar.
- Si falta la batería tanto como creo que falta.
- Y la que sigue abierta de la 3d: si la ventana de aceptación escalada se siente
  justa al 50 %, si un compás de cuenta atrás basta, si el click acentuado ayuda,
  y si «dos pasadas al 90 %» es el umbral correcto para subir.

## 8. Lo que la revisión de constructor tumbó, y queda inscrito

Esta spec se escribió y luego la leyó un constructor independiente **contra el
código**, antes de planificar nada. Encontró **seis afirmaciones mías falsas**. Van
aquí enteras porque la lección de la 3d fue que los defectos no los encuentra
quien escribió el texto:

1. «La 3b ya sabe importar cualquiera de las pistas» — **falso**: solo Guitar Pro.
   MIDI y MusicXML lanzan `ValueError` si la pista no cabe en la afinación
   (`desde_midi.py:165-210`, `desde_musicxml.py:186-226`). De aquí salió M8, que
   es la mejor decisión de la etapa: el fondo no pasa por `Pieza`.
2. «El gemelo de la 3d captura las muestras escritas» — **falso**: no existe. El
   gemelo simula la entrada, no la salida. Esta etapa lo construye (M7).
3. «La clave de caché es (id de la pieza, …)» — **falso**: `Pieza` no tiene id, y
   el carril no recibe ni canción ni pista. De aquí salió §3.3 entera.
4. «§4.7: el anti-objetivo, medido» — **falso**: no había camino entre la salida y
   la entrada, así que esa prueba no podía fallar. Reescrita con las dos mitades.
5. «El click y el acompañamiento escriben en el mismo `SalidaAudio`» —
   **incompatible** con `_parar_click`, que cierra esa salida sin condiciones.
   Salida propia.
6. «El acompañante no tiene que absorber nada porque no lleva reloj» — **al
   revés**: tiene que absorber el candado de la sesión. De aquí salió la regla de
   no esperarlo nunca.

Y una medición que corrigió un número mío: el coste de renderizar escala con la
**duración sonando**, no con el número de notas (200 notas de 0,5 s = 55 ms;
las mismas de 1,5 s = 151 ms). Importa porque bajar el tempo alarga las notas.

Las siete preguntas que esa revisión dejó abiertas las decidí yo, no el usuario:
él pidió expresamente saltarse las preguntas de diseño. Están resueltas en M8,
§3.1, §3.3, §3.4, §4.6, §4.7 y §5, y cada una dice qué cuesta si me equivoqué.
