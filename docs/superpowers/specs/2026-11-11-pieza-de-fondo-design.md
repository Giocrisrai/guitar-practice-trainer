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
  tempo).** Medido con el motor de la 3d en esta máquina: **200 notas en 55 ms**.
  Renderizar una canción entera cuesta décimas de segundo, así que volver a
  renderizarla cuando mueves el tempo es gratis y evita tener que resamplear (que
  cambiaría la afinación). *Precio:* memoria — tres minutos en mono float32 a
  48 kHz son ~34 MB — y una espera de décimas al mover el deslizador de tempo,
  que hay que absorber sin cortar el sonido.
- **M4. Suenan las OTRAS pistas del archivo, no la tuya.** Es la experiencia
  Rocksmith: tú eres el guitarrista que falta. `pistas_de()` ya enumera las pistas
  de un Guitar Pro, y la 3b ya sabe importar cualquiera de ellas. Si la canción
  **solo tiene una pista**, suena la tuya a volumen bajo, como guía — que es lo
  que de verdad quiere quien está aprendiendo la pieza. *Precio:* en una canción
  de una pista, el acompañamiento te sopla la respuesta; por eso va más bajo y se
  puede apagar.
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
  sustituible. El gemelo de la 3d captura las muestras escritas y comprueba, con
  números, que el audio que salió corresponde al cabezal que había. Es la lección
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

Función pura, sin hilos y sin audio: convierte una `Pieza` y un factor de tempo en
un `bytearray` de muestras y el mapa para indexarlo.

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

def renderizar(
    pieza: Pieza,
    factor_tempo: float = 1.0,
    frecuencia_muestreo: int = 48000,
    ganancia: float = 1.0,
    semilla: int | None = 0,
) -> PiezaRenderizada
```

Reglas que esta función fija:

- Cada nota se sintetiza con `cuerda_pulsada` a la altura de `midi`, con duración
  = su figura escrita (en segundos al tempo efectivo) **más una cola**, y se suma
  en su sitio. Los acordes se suman: aquí **sí** se pueden tocar, porque sumar
  ondas no requiere distinguirlas (es el detector monofónico quien no puede, no el
  sintetizador).
- La semilla por defecto es fija: la misma pieza al mismo tempo suena **idéntica**
  dos veces. Es lo que permite afirmar sobre muestras en una prueba.
- Se normaliza al pico una sola vez, al final, sobre la mezcla entera. Normalizar
  nota a nota haría que una nota sola suene igual de fuerte que un acorde de seis.
- Si la pieza no tiene notas, devuelve un buffer de un instante y duración 0.
  Nadie debería tener que preguntar antes de llamar.

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

### 3.3 `servidor/piezas.py` — el cableado

`_ajustar_acompanamiento`, calcada de `_ajustar_click` (misma estructura, mismo
tratamiento de la pausa, mismo «sin salida de audio la pasada sigue en pie»):

- Se llama desde los dos sitios desde los que ya se llama `_ajustar_click`.
- Renderiza cuando cambia la pieza o el factor de tempo, y **solo** entonces. La
  clave de caché es `(id de la pieza, factor_tempo, pista)`.
- Pausa y reanuda con la pasada, incluida la pausa por falta de señal.
- `PlanDePasada` gana dos campos: `con_acompanamiento: bool = False` y
  `volumen_acompanamiento: float = 0.6`. El valor por defecto de lo primero es
  **falso**, y quien lo enciende es la interfaz (§3.5) después de ver el aviso.
- `EstadoEstudio` publica `acompanamiento_sonando: bool` y
  `acompanamiento_posible: bool` — lo segundo es «la entrada es el cable», que es
  lo que decide el aviso de la interfaz, y se decide **en un solo sitio** y viaja
  publicado. Es literalmente la lección de E3 de la 3d: la regla del aviso del
  cable estaba escrita dos veces, en dos idiomas, y las dos no eran la misma.

### 3.4 De dónde sale la pista que suena

- `canciones.py` ya guarda el archivo original. Al elegir la pista para tocar, se
  guardan también **las demás** como pistas de acompañamiento: se importan con el
  lector de la 3b igual que la tuya, y se suman en un solo `PiezaRenderizada`.
- Si no hay ninguna otra pista utilizable, se renderiza la tuya con la ganancia
  por defecto reducida a la mitad, y el estado lo dice (`acompanamiento_es_tu_parte`)
  para que la interfaz pueda llamarlo *guía* y no *acompañamiento*.
- Las pistas que `_motivo_no_usable` rechaza (percusión, sin cuerdas, sin notas)
  se descartan **en silencio para el audio pero no para el usuario**: la interfaz
  dice cuántas pistas suenan y cuántas se quedaron fuera y por qué. Un fondo al que
  le falta el bajo sin que nada lo diga es un fondo que parece roto.

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
   `--con-acompanamiento`, y el gemelo toca la pieza entera con el fondo puesto
   mientras la sesión real corre. Es la única prueba que cruza las cuatro costuras
   a la vez.
7. **El anti-objetivo, medido**: una pasada con el acompañamiento sonando y la
   entrada siendo el gemelo **no** cambia el veredicto respecto a la misma pasada
   sin acompañamiento. Si cambia, el audio se está colando en la entrada.

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
- **Dos emisores sobre una salida.** El click y el acompañamiento escriben en el
  mismo `SalidaAudio`, que serializa con candado. Un bloque de acompañamiento
  (21 ms) puede retrasar un click y al revés. `Metronomo` ya absorbe eso
  realineándose; el acompañante no tiene que absorber nada porque no lleva reloj.
  Hay que medirlo, no suponerlo.
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
