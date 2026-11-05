# Etapa 3d — El gemelo digital de la sesión

**Fecha:** 2026-11-02
**Estado:** propuesta
**Etapas previas:** 1 (núcleo y afinador), 2a (ejercicios monofónicos), 3a (el carril), 3b (importar canciones), 3c (practicar la pieza)
**Etapa siguiente, ya nombrada:** 3e — la experiencia de juego (incluye la pieza
sonando de fondo, que la spec de la 3c aparcó anunciándola como «la 3d»; esta
etapa se cuela delante y renumera aquella promesa, que pasa a la 3e)

## 1. Qué se construye y por qué

El usuario dijo para qué es todo esto, y no era medir: **«pienso en Guitar Hero y
Rocksmith y quiero darle esa experiencia»**, y la quiere «dinámica, se va
mostrando y voy tocando y me va indicando si voy bien, mal, si debo repetir».
Eso es la etapa 3e.

Esta etapa construye lo que hace posible la 3e, y resuelve un problema que ya
duele: **nada de lo que llevamos construido ha pasado por el cable.** La 3a, la
3b y la 3c enteras existen solo como pruebas sobre dobles. Cuando la 3c terminó,
la revisión final encontró que *la cuenta atrás moría con el primer cuadro de
audio*: lo último que construyó la rama no habría funcionado con la guitarra
enchufada, y 1039 pruebas en verde no lo sabían. Y la propia 3c dejó aparcado,
medido, que **con bucle se pierde la última nota de cada vuelta**.

El gemelo digital es un guitarrista sintético que toca una pieza de verdad —con
errores a propósito— y mete ese sonido por la misma ruta que el cable:

```
intérprete sintético → dispositivo simulado → CapturaAudio → Analizador
   → SeguidorPieza → SesionDeEstudio → servidor → WebSocket → interfaz
```

Y hace dos cosas que ninguna prueba con dobles puede hacer:

1. **Firma un veredicto.** Sabe exactamente qué tocó, así que puede decir qué
   perdió la cadena, qué se inventó, a qué nota se lo apuntó y cuántos
   milisegundos le añadió. «La cadena perdió 1 nota de 48» es una aserción, no
   una impresión.
2. **Es el escaparate.** El usuario puede abrir el navegador y **verse tocar sin
   tocar**: la sesión corre sola, a tempo real, con el perfil de un principiante
   o de un intérprete perfecto. Es lo que le deja opinar sobre si la experiencia
   engancha antes de tener la guitarra delante, que es exactamente lo que pidió
   («no puedo conectar y probar, prefiero que avances y luego te doy feedback»).

### Decisiones del usuario, tomadas en la conversación

1. El gemelo abarca **toda la sesión, incluida la interfaz**: no solo el cable y
   la señal, sino un conductor que mueve la interfaz real contra el servidor.
2. El gemelo **prepara** las pruebas con la guitarra, no las sustituye: deja la
   cadena verificada y los defectos aparcados cerrados, y al usuario le queda
   confirmar lo que solo se juzga tocando.
3. El objetivo final es la experiencia de juego, y esta etapa es el medio.

### Decisiones mías, que el usuario no tomó

Van marcadas así en todo el documento. El usuario pidió avanzar con criterio
propio; estas son las que cambian lo que se construye y por tanto las que querrá
revisar primero.

- **(mía)** El orden: gemelo antes que juego, porque sin cable el gemelo es lo
  único que deja comprobar que lo divertido funciona, y porque además es la
  demostración que permite opinar sobre lo divertido.
- **(mía)** Sin dependencias nuevas de Python ni de la interfaz (ver §7).
- **(mía)** El navegador lo conduzco yo durante la sesión con las herramientas de
  Chrome que ya tengo; **no entra Playwright en el proyecto** (ver §6).
- **(mía)** La etapa cierra además los nueve defectos que la 3c aparcó (§8),
  porque el gemelo los convierte en pruebas y arreglarlos sin él era adivinar.

## 2. Objetivos, no-objetivos y anti-objetivos

**Objetivos**

- Un guitarrista sintético determinista que toca cualquier `Pieza` con un perfil
  de destreza, y que sabe lo que tocó.
- Un sonido lo bastante parecido a una cuerda pulsada como para que el detector
  real se juegue algo: ataque, armónicos que decaen a distinto ritmo, ruido de
  púa, inarmonicidad.
- Dos velocidades de gemelo: **cadena directa** (tiempo virtual, rápida,
  determinista, para la suite) y **sesión completa** (tiempo real, con hilos y
  servidor, para la demostración y para unas pocas pruebas lentas).
- Un veredicto comparable y accionable: notas perdidas, inventadas, mal
  adjudicadas, desfase introducido.
- Cerrar los defectos de la 3c que el gemelo destapa.

**No-objetivos**

- No es un sintetizador bonito. El sonido solo tiene que ser lo bastante duro
  para el detector; nadie va a escuchar el gemelo por gusto.
- No hay polifonía. El detector es monofónico y la 3c ya saca los compases con
  acordes de todas las cuentas; el gemelo toca una nota a la vez y los acordes
  siguen fuera.
- No sustituye al cable. La lista de lo que solo el usuario puede juzgar sigue
  entera.
- No toca la experiencia de juego. Eso es la 3e.

**Anti-objetivos** (lo que haría fracasar la etapa aunque funcione)

- **Un gemelo que aprueba porque las dos partes comparten código.** La verdad de
  lo tocado se escribe **antes** de generar el audio y no consulta al
  `SeguidorPieza` ni a sus reglas. Si el veredicto importara de `seguimiento.py`
  lo que cuenta como acierto, el gemelo no verificaría nada: se daría la razón.
- **Un gemelo tan lento que nadie lo corre.** La cadena directa tiene que
  comprobar una canción de tres minutos en menos de un segundo. Si para
  verificar hay que esperar tres minutos, se verifica una vez y nunca más.
- **Un gemelo que solo prueba el camino feliz.** El perfil perfecto es el oráculo
  (todo limpio obliga a la cadena a decir «todo limpio»), pero el perfil que
  encuentra defectos es el malo.

## 3. Las piezas

Todo vive en `nucleo/gemelo/`, nuevo paquete. Respeta las reglas de
dependencias del proyecto: `nucleo/` no importa de `servidor/` ni de `interfaz/`.
`nucleo/gemelo/` sí puede importar de `nucleo/piezas/` y de `nucleo/analisis/`.
El conductor de la sesión completa, que necesita el servidor, vive en
`herramientas/`, no en `nucleo/`.

### 3.1 `nucleo/gemelo/cuerda.py` — la cuerda pulsada

Síntesis por **Karplus-Strong**: un pulso de ruido recorre una línea de retardo
de longitud `frecuencia_muestreo / f0` con un filtro de media móvil de dos
muestras a la salida. Es el método clásico de cuerda pulsada, son treinta líneas
de numpy, y da gratis lo que una senoide no tiene: armónicos presentes al
principio y desaparecidos al final, decaimiento más rápido en los agudos,
transitorio de ataque, y la inarmonicidad que introduce el redondeo de la línea
de retardo a muestras enteras.

```python
def cuerda_pulsada(
    midi: int,
    duracion_s: float,
    frecuencia_muestreo: int = 48000,
    brillo: float = 0.5,
    fuerza: float = 0.8,
    trasteo: float = 0.0,
    semilla: int | None = None,
) -> np.ndarray
```

- `brillo` mezcla el filtro: 0 apaga los agudos enseguida (púa blanda), 1 los
  mantiene (púa dura).
- `fuerza` es la amplitud de pico.
- `trasteo` añade ruido de banda ancha y acorta el decaimiento: la cuerda que
  roza el traste. Es lo que simula el dedo mal puesto que suena pero suena mal.
- `semilla` fija el ruido inicial. Sin ella no hay gemelo reproducible.

**Por qué importa que no sea una senoide.** El detector real (`Analizador`, con
YIN) sobre una senoide acierta siempre, y una suite que lo alimente con senoides
dice que el detector funciona cuando lo único que ha demostrado es que YIN sabe
sumar. Sobre una cuerda pulsada aparecen los errores de octava, el transitorio
que no tiene altura definida, y el final en que la señal baja del umbral. El
gemelo tiene que atravesar eso.

**Calibración contra la guitarra real.** `tests/audio/` ya tiene (o tendrá,
cuando el usuario corra `herramientas.grabar_muestras`) las seis cuerdas al aire
grabadas. Una prueba compara el gemelo con la grabación real en lo que se puede
comparar sin oído: que el detector le dé la misma nota, y que el perfil de
decaimiento de energía y el reparto de armónicos queden en el mismo orden de
magnitud. Si falta la grabación, la prueba se salta, como las que ya existen.

### 3.2 `nucleo/gemelo/interprete.py` — el guitarrista

```python
@dataclass(frozen=True)
class PerfilDeDestreza:
    nombre: str
    desfase_medio_s: float          # sesgo: toca adelantado o atrasado
    desviacion_desfase_s: float     # temblor, gaussiano
    probabilidad_de_fallo: float    # la nota no suena
    probabilidad_de_nota_mala: float  # traste equivocado: ±1 o ±2 semitonos
    probabilidad_de_trasteo: float  # suena pero roza
    cents_de_desafinacion: float    # desviación típica, en cents
    fuerza_media: float
    desviacion_fuerza: float
```

Perfiles de fábrica: `PERFECTO`, `PRINCIPIANTE`, `INTERMEDIO`, `CAOS`.
`PERFECTO` es el oráculo: cero fallo, cero desfase, cero desafinación. Lo que
la cadena diga de una interpretación perfecta y no sea «todo limpio» es un
defecto de la cadena, no del gemelo.

```python
@dataclass(frozen=True)
class EventoTocado:
    indice_pretendido: int | None  # la nota de la pieza a la que apuntaba
    midi: int                      # lo que sonó de verdad
    instante_s: float              # cuándo empezó a sonar
    duracion_s: float              # cuánto sonó: la prosa del §3.9 la pedía
    cents: float
    trasteada: bool

@dataclass(frozen=True)
class Interpretacion:
    pieza: Pieza                   # la pieza DE la que esto es interpretación
    muestras: np.ndarray
    eventos: tuple[EventoTocado, ...]
    frecuencia_muestreo: int
    duracion_s: float
    silencio_de_cabecera_s: float
    # Los argumentos con que se tocó, porque sin ellos `juzgar` no puede
    # traducir del eje del audio al del cabezal (ver abajo).
    primer_compas: int = 1
    ultimo_compas: int | None = None
    factor_tempo: float = 1.0
    repeticiones: int = 1
    segundos_de_cuenta_atras: float = 0.0

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

El tramo se dice **en compases y no en pulsos**, con los mismos nombres y la
misma convención que `PlanDePasada` (1 es el primer compás, `None` es «hasta el
final»): el gemelo tiene que poder interpretar exactamente el tramo que el plan
de la pasada describe, y traducir compases a pulsos en dos sitios distintos es
cómo se desalinean. `repeticiones` existe para poder interpretar **un bucle**, que
es donde la 3c sabe que se pierden notas, y `segundos_de_cuenta_atras` mete el
silencio de la cuenta atrás, porque ahí murió la cuenta atrás en la 3c.

**`Interpretacion` LLEVA LA PIEZA Y LOS ARGUMENTOS DENTRO, y la primera versión
de esta spec no se los daba.** (Corregido tras medirlo en la etapa: el bloque de
arriba decía `Interpretacion` con cuatro campos.) Los seis son load-bearing:

- `pieza`, porque `juzgar` tiene que excluir los acordes y las notas repetidas
  consecutivas, y esas exclusiones se determinan DESDE LA PIEZA y no desde lo que
  la cadena hizo. Una interpretación es la interpretación DE una pieza.
- el tramo, el factor de tempo, las vueltas y la cuenta atrás, porque el cabezal
  de una pasada que estudia del compás 2 al 2 NO arranca en cero: arranca en el
  instante escrito de ese compás. Medido con el tramo 2-2 de la escala: los
  reportes de la vuelta 1 caen en 2,6 s mientras los ataques están a 0,128 s del
  audio, y un veredicto que no supiera el tramo daba las cuatro notas por
  perdidas sin poder decir por qué.
- `silencio_de_cabecera_s`, porque es el eje: lo que se mide es desde dónde.

`EventoTocado.duracion_s` existe por lo que la prosa del §3.9 ya pedía (el solape
se provoca con notas largas) y porque el veredicto no puede deducir del sonido
cuánto sonó una nota.

Reglas:

- Los acordes (varias notas en el mismo pulso) se reducen a la más grave y se
  anotan: el gemelo no finge polifonía.
- Una nota «fallada» no genera audio y su evento no existe; el índice
  pretendido simplemente no aparece en `eventos`. El veredicto lo sabe
  comparando con la pieza.
- `eventos` se escribe **antes** de generar el audio, y la generación lo lee.
  Nunca al revés: la verdad no se deduce del sonido.
- Todo el azar sale de un único `numpy.random.default_rng(semilla)`. La misma
  semilla y el mismo perfil dan byte a byte la misma interpretación, en
  cualquier máquina.
- **Silencio de cabecera obligatorio** antes de la primera nota, de al menos una
  ventana de análisis (4096 muestras, 85 ms a 48 kHz). Sin él, el primer cuadro
  que llega a la cadena ya contiene la primera nota, el reloj de la pieza se
  ancla ahí, y todo lo que viene después se lee 85 ms adelantado. Medido: una
  sonda sin cabecera informaba −69 ms de desfase en una interpretación perfecta.
  Es un artefacto del gemelo, no de la cadena, y por eso se arregla en el
  gemelo.

### 3.3 `nucleo/gemelo/dispositivo.py` — el cable falso

`CapturaAudio` ya acepta `abrir_stream`, y `Sesion` acepta `crear_captura` y
`listar`. El gemelo no necesita parchear nada:

```python
class StreamSimulado:
    """Cumple el contrato que CapturaAudio le pide a sounddevice."""
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...

def dispositivo_simulado(
    interpretacion: Interpretacion,
    tamano_bloque: int = 512,
    nombre: str = NOMBRE_DEL_GEMELO,
) -> tuple[Callable, Callable]:
    """Devuelve (abrir_stream, listar) listos para Sesion y CapturaAudio."""
```

**NO HAY `en_bucle`, y esta spec lo pedía.** (Corregido tras construirlo.) El
bucle no se hace aquí: el intérprete ya genera las vueltas DENTRO del audio
(`repeticiones` en el §3.2), así que un dispositivo que repitiera el buffer
estaría tocando vueltas que la verdad de la interpretación no conoce, y el
veredicto no podría adjudicar ni una. Lo que el dispositivo gana en su lugar es
`nombre`, para que el diagnóstico pueda decir en voz alta con quién habla.

`listar` anuncia un `DispositivoAudio` con un nombre que contiene
`"Rocksmith"` para que `buscar_rocksmith` lo encuentre, y
`"(gemelo)"` para que nadie confunda una sesión simulada con una real: **el
diagnóstico tiene que decir en voz alta que está hablando con el gemelo.**

El stream empuja bloques por el callback en un hilo con reloj real.

### 3.4 `nucleo/gemelo/cadena.py` — la cadena directa, en tiempo virtual

El camino rápido, el que corre en la suite. No abre hilos, no duerme, no toca
`Sesion`:

```python
def pasar_por_la_cadena(
    interpretacion: Interpretacion,
    conductor: ConductorDeEstudio,
    analizador: Analizador | None = None,
    salto: int | None = None,
) -> RegistroDeLaCadena
```

Toma el **conductor** (ver §3.7), no un `SeguidorPieza`: lo que esta etapa viene a
verificar —el bucle, la cuenta atrás, el informe, la regla del tempo— no vive en
el seguidor, y un gemelo que solo llegue al seguidor no prueba ninguna de las
cinco primeras pruebas del §5.

**La ventana y la cadencia son las de producción, y eso no es negociable:** la
ventana es `perfil.tamano_ventana(fs)` (4096 muestras con guitarra estándar,
85 ms a 48 kHz) y el salto es `INTERVALO_ANALISIS = 0.021` s, o sea 1008
muestras (`servidor/sesion.py`). `salto=None` significa exactamente eso. La razón
es que las constantes del detector están acopladas a esos 21 ms
—`CUADROS_PARA_NOTA_ESTABLE = 3` son 63 ms a 21 ms y 32 ms a 10,7 ms, y
`pulsaciones.py` advierte por escrito de que quien cambie la tasa de análisis
tiene que revisarlas—, así que recorrer el audio a otra cadencia es ejercitar un
detector que nunca corre: el anti-objetivo del §2 entrando por la otra puerta.
Las sondas de este diseño usaron un salto de 512 y por eso sus números son
indicativos, no de referencia.

Una pieza de tres minutos son 180 / 0,021 = 8571 análisis. (La primera versión de
esta spec decía «94 Hz»: eso era 48000/512, el salto de la sonda, no el de
producción.)

Recorre las muestras en ventanas solapadas, llama al `Analizador` real, y le
pasa cada resultado al `SeguidorPieza` real con el instante **virtual** de la
ventana (el que correspondería al reloj si el audio fuese en vivo).

**Ese instante es el FINAL de la ventana**, no su centro ni su principio, y esto
está medido, no razonado. En vivo, el cuadro se entrega cuando el último bloque
acaba de llegar: la ventana termina en «ahora». Una sonda de este diseño midió
el error entre el onset real y el que firma el detector con las tres
convenciones, sobre ocho notas sintéticas:

| convención | error mediano |
|---|---|
| principio de la ventana | −78,7 ms |
| centro de la ventana | −36,0 ms |
| **final de la ventana** | **+6,7 ms** |

El +6,7 ms es la latencia propia del detector, que es real y debe aparecer. Los
−36 ms del centro son un sesgo inventado por la convención: un gemelo construido
sobre el centro habría acusado a la cadena de adelantar cada nota 36 ms, y
cualquier aserción de desfase habría estado corrupta. La primera versión de esta
spec decía «el centro»; la sonda la corrigió antes de escribir una línea de
código, que es para lo que sirven las sondas.

Una canción de tres minutos a 48 kHz son unos 8600 análisis, y la cadena directa
los hace en segundos sin dormir ni abrir hilos. Eso la hace viable en la suite,
que es la condición para que se corra. (Esta frase decía «a 48000/512 ≈ 94 Hz»,
que es el salto de la SONDA de este diseño y no el de producción: dos párrafos
más arriba esta misma sección declara que el salto es de 21 ms y que los números
de la sonda a 512 son indicativos. La cuenta de los 8600 análisis sale de los
21 ms y es la que se sostiene.)

**(mía)** Esta separación en dos niveles es la decisión arquitectónica de la
etapa. La alternativa —un solo gemelo en tiempo real— habría obligado a que cada
prueba del bucle esperase los segundos de audio que dura el bucle, y la suite,
que hoy tarda 29 segundos, habría pasado de los diez minutos. Lo que se paga es
que la cadena directa no ejercita los hilos de `Sesion`; eso lo cubre el nivel
de sesión completa, con pocas pruebas y lentas.

### 3.5 `nucleo/gemelo/veredicto.py` — lo que firma el gemelo

```python
@dataclass(frozen=True)
class ReporteDeLaCadena:
    # Una NotaTocada tal y como la cadena la publico, con su vuelta.
    repeticion: int
    tocada: NotaTocada
    instante_pasada_s: float   # el reloj de la pasada cuando se publico

@dataclass(frozen=True)
class RegistroDeLaCadena:
    # TODO lo que la cadena reporto, vuelta a vuelta, sin perder nada.
    reportes: tuple[ReporteDeLaCadena, ...]
    vueltas: tuple[InformeDePasada, ...]
    estado_final: EstadoEstudio

@dataclass(frozen=True)
class Veredicto:
    notas_de_la_pieza: int         # la pieza ENTERA
    notas_tocadas: int             # eventos que el interprete genero: tramo x vueltas
    notas_del_tramo: int           # las escritas en el tramo interpretado
    vueltas: int                   # las repeticiones de ese tramo
    perdidas: tuple[tuple[int, int], ...]   # (vuelta, indice) no reportados
    inventadas: int                # reportadas que nadie toco
    mal_adjudicadas: tuple[tuple[int, int, int], ...]  # (vuelta, pretendido, reportado)
    excluidas: tuple[tuple[int, int], ...]  # (vuelta, indice) que no se juzgan
    desfase_introducido_ms: float  # mediana de (reportado - real), CON signo
    desfase_maximo_ms: float

def juzgar(
    interpretacion: Interpretacion,
    registro: RegistroDeLaCadena,
    tolerancia_de_emparejamiento_ms: float = TOLERANCIA_DE_EMPAREJAMIENTO_MS,
) -> Veredicto
```

**LAS CUATRO CANTIDADES DE ARRIBA NO SE COMPARAN ENTRE SÍ A LA LIGERA**, y el
escaparate lo hizo: comparar `notas_tocadas` con `notas_de_la_pieza` por igualdad
es comparar tramo x vueltas con la pieza entera, y con un tramo de 24 notas a dos
vueltas la igualdad se cumple sobre una pasada que tocó la mitad dos veces. De ahí
`notas_del_tramo`, `vueltas` y la propiedad `toco_la_pieza_entera_una_vez`, que es
la pregunta que se quería hacer. No decide nada del veredicto: `limpio` sigue
siendo lo único que juzga a la cadena.

**Por qué un registro y no un `EstadoCarril`.** `EstadoCarril.tocadas` solo trae
lo que el seguidor lleva sin volcar, y `cerrar_repeticion` lo vacía en cada
vuelta: al acabar cuatro repeticiones, el estado final solo conoce la última. Y
los índices se repiten vuelta a vuelta, así que «se perdió la nota 11» no
distingue «en la vuelta 3» de «en todas». El registro lo recoge la cadena directa
mientras pasa, que es el único momento en que esa información existe.

**`tolerancia_de_emparejamiento_ms` ES EL TECHO DEL PROPIO DETECTOR: 250 ms, y no
un número de aquí.** Es holgura de EMPAREJAMIENTO, no de calidad: su trabajo es
decidir si el reporte X habla del ataque Y, y el detector firma un onset hasta
`VENTANA_ATAQUE_COMO_ONSET_S` (250 ms) después del ataque, con la mediana de 5 del
`Suavizador`, `ESPERA_ESTABILIZACION_S = 0,060` y tres cuadros de racha estable
por delante. Con 15 ms casi toda nota saldría «perdida» y el oráculo sería rojo
por construcción: la prueba habría medido la tolerancia, no la cadena.

**Esta spec decía 120 ms y defendía el 120 en un párrafo entero. Es falso, y lo
corrige una medición de la etapa:** con 120 ms salían **5 de 8 notas perdidas** en
una interpretación perfecta, porque el retraso que la cadena introduce de verdad
llega a +249 ms en la sesión completa. La constante se deriva ahora de
`VENTANA_ATAQUE_COMO_ONSET_S` y no se escribe suelta, para que mover el techo del
detector mueva la holgura con él en vez de desacoplarlas en silencio.

**El oráculo NO afirma `desfase_introducido_ms == 0`.** Hay un suelo real y no
nulo que ningún perfil puede anular, el de los retardos de arriba. La primera
tarea del plan es MEDIRLO sobre el oráculo e inscribir el número medido en la
prueba, con margen. Escribir la aserción suponiendo cero es como se empieza una
etapa con una prueba roja que no delata ningún defecto y que se «arregla»
tocando la cadena buena.

**Las notas repetidas se EXCLUYEN, como los acordes, y se declara.**
`DetectorPulsaciones` declara por escrito que no distingue dos pulsaciones
seguidas de la misma nota sin un hueco de tres cuadros sin nota creíble, y una
cuerda que sigue sonando puede no abrir ese hueco nunca. Si el veredicto las
juzgara, el oráculo saldría rojo por una limitación aceptada del programa en vez
de por un defecto, y el ejecutable del §4 saldría siempre con error. Van a
`excluidas`, con el mismo argumento que los acordes: no es un fallo del alumno,
es un límite del programa. Cerrar esa limitación del detector no es esta etapa.

`juzgar` no importa nada de `seguimiento.py` salvo los tipos que lee. No
reimplementa la ventana de acierto ni la clasificación: compara eventos con
reportes por instante y altura, y ya. Lo que la cadena *decide* (acertada,
afinada, a tiempo) es asunto de la cadena; el veredicto solo dice si la cadena
**vio** lo que pasó.

`tolerancia_ms` es la holgura de emparejamiento, no de calidad: una nota
reportada 8 ms después de sonar es la misma nota, y el gemelo lo anota en
`desfase_introducido_ms` en vez de llamarla perdida.

### 3.6 `nucleo/gemelo/perfiles.py`

Los cuatro perfiles de fábrica y nada más, para que `interprete.py` no cargue con
constantes y para que una prueba pueda añadir el suyo sin tocar el módulo.

### 3.7 `nucleo/piezas/conductor.py` — la política del estudio, sacada del servidor

**(mía, y es la decisión que más cambia el tamaño de esta etapa.)**

La política que de verdad decide cómo se estudia no está en `nucleo/`: está en
`SesionCarril` (`servidor/piezas.py`). Ahí viven `_observar`, `_mirar` con su
`TECHO_TRAMO_S = 0,100`, `_sin_cuadros` con `ESPERA_SIN_CUADROS_S`, y
`_cerrar_lo_que_termino`, que es quien detecta la transición de vuelta, llama a
`cerrar_repeticion`, anota en el `HistorialDeEstudio` y aplica `factor_sugerido`.
Es decir: **los cuatro primeros defectos del §8 viven en código del servidor**, y
`nucleo/gemelo/` no puede importar de `servidor/` (regla del proyecto).

Las dos salidas posibles eran malas:

- Que la cadena directa reimplemente esa política para poder correr sin FastAPI.
  Entonces el gemelo valida una política paralela, y el riesgo del §10 —«la
  cadena directa puede divergir de la real»— se materializa exactamente en el
  código que la etapa viene a arreglar. Es el anti-objetivo del §2 con otro
  disfraz: el gemelo se daría la razón.
- Que el gemelo llegue solo hasta `SeguidorPieza`. Entonces las pruebas 2, 3, 4 y
  5 del §5 no son ejecutables en el nivel rápido y caen todas al nivel lento,
  que esta spec quiere mínimo. O sea: la etapa no verificaría el bucle, que es su
  motivo.

Así que **se extrae**. `ConductorDeEstudio` se lleva de `SesionCarril` la política
del reloj y del cierre de vueltas, sin FastAPI, sin WebSocket y sin audio:

```python
class ConductorDeEstudio:
    def __init__(
        self,
        estudio: SesionDeEstudio,
        historial: HistorialDeEstudio | None = None,
        al_cambiar_repeticion: Callable[[EstadoEstudio], None] | None = None,
        techo_tramo_s: float = TECHO_TRAMO_S,
        espera_sin_cuadros_s: float = ESPERA_SIN_CUADROS_S,
    ) -> None: ...

    def observar(self, resultado: ResultadoAnalisis, instante_analisis: float) -> EstadoEstudio: ...
    def mirar(self, ahora: float, senal_ausente: bool) -> EstadoEstudio: ...
    @property
    def vueltas_cerradas(self) -> tuple[InformeDePasada, ...]: ...
```

El click **no** entra: se queda en el servidor, enganchado a
`al_cambiar_repeticion`. Esa es la línea que mantiene a `nucleo/` libre del
dispositivo de sonido, que es una regla que ya existe y que la etapa 3c cumple
igual (`estudio.py` lo dice en su primera página: «NO ABRE AUDIO»).

Después de la extracción, `SesionCarril` se queda con lo que de verdad es del
servidor: HTTP, WebSocket, el click, el espejo del estado y la pausa por falta de
señal.

**Lo que esto cuesta, dicho en claro.** Es un refactor de `servidor/piezas.py`
(898 líneas) con 1734 líneas de pruebas vivas en `tests/test_app_estudio.py` que
tienen que seguir pasando sin tocarlas. No es gratis y no es lo que el usuario
pidió: él pidió un gemelo. Lo hago porque sin esto el gemelo no puede juzgar el
bucle, y juzgar el bucle es para lo que existe. **Si el usuario prefiere no
mover el servidor, la alternativa honesta es renunciar a las pruebas 2 a 5 en el
nivel rápido y aceptar un gemelo que solo llega al seguidor**; está a tiempo de
decirlo y es una vuelta atrás de una tarea, no de la etapa.

### 3.8 Lo que el dispositivo simulado hace cuando se acaba el audio

Tres caminos distintos en `Sesion`, y el documento no elegía ninguno:

- Si el stream deja de empujar bloques, `total_capturado` se congela y a los 0,5 s
  (`TIEMPO_SIN_MUESTRAS_SILENCIO`) se publica silencio; a los 5 s
  (`SEGUNDOS_SIN_SENAL`) el carril se pausa por falta de señal.
- Si el dispositivo desaparece de `listar`, el hilo cierra la captura y la señal
  se da por ausente **de inmediato**.

**Decisión (mía): el stream sigue empujando silencio indefinidamente y el
dispositivo nunca desaparece de `listar`.** Es lo que hace un cable enchufado a
una guitarra que nadie toca, es el único camino en que las últimas notas llegan a
cobrarse antes de que algo pause la pasada, y es la condición para que la prueba
8 del §5 pueda afirmar «veredicto limpio».

Y `StreamSimulado` tiene que cumplir el contrato entero, no solo
`start/stop/close`: `CapturaAudio.latencia_ms` lee `self._stream.latency`, así
que sin ese atributo el diagnóstico reventaría la primera vez que alguien lo
pidiera. Expone `latency` con un valor plausible y declarado.

El ejecutable del §4 **no termina solo**: imprime el veredicto cuando la pasada
se completa y se queda vivo, porque su razón de ser es que el usuario mire. Con
`--salir-al-acabar` termina y devuelve el código de salida, que es la forma de
usarlo desde un script.

### 3.9 Cómo suena cada nota

`EventoTocado` gana `duracion_s`. La nota se renderiza por su figura escrita y se
deja decaer, pero **el intérprete nunca solapa dos notas consecutivas por su
cuenta**: corta la anterior al 85 % del hueco hasta la siguiente. La razón está
medida en el §10: las colas que se solapan generan ataques fantasma, y un gemelo
que los produzca sin querer acusará a la cadena de inventarse notas que en
realidad se inventó él.

Producirlos **a propósito** sí es parte del gemelo: `PerfilDeDestreza` gana
`sustain` (0 corta siempre, 1 deja sonar la figura entera), y el perfil `CAOS` lo
lleva alto. Así el fantasma se puede provocar, medir y nombrar en una prueba que
dice lo que hoy pasa, sin pretender arreglarlo aquí.

## 4. La sesión completa

`herramientas/gemelo.py`, un módulo ejecutable:

```bash
uv run python -m herramientas.gemelo --pieza canciones/x.gp5 --perfil intermedio \
    --tempo 0.8 --bucle 17-20 --repeticiones 4
```

Qué hace:

1. Construye la `Pieza` (de un archivo, o del generador de ejercicios si no se
   le da archivo: así funciona sin ningún archivo con derechos de autor).
2. Interpreta con el perfil pedido.
3. Arranca el servidor de verdad en el puerto 8420 con `Sesion(crear_captura=...,
   listar=...)` apuntando al dispositivo simulado.
4. Llama a los endpoints de la 3c (`/api/piezas/plan`, `iniciar`) como los
   llamaría la interfaz, con `urllib.request` de la biblioteca estándar: `httpx`
   está en el grupo `dev` del `pyproject.toml`, no en las dependencias de
   ejecución, y usarlo aquí rompería el §7. El servidor sí se levanta de verdad
   con `uvicorn`, que sí es dependencia de ejecución, porque la razón de ser de
   este módulo es que el navegador del usuario se conecte a él.
5. Imprime el veredicto al terminar, y sale con código distinto de cero si hay
   notas perdidas o inventadas.

El usuario abre `http://localhost:8420` y lo ve correr. Ese es el escaparate.

**Ningún archivo con derechos de autor entra al repositorio.** La pieza de
demostración por omisión se construye en código, como todas las de la suite.

## 5. Qué pruebas trae

Lo que el gemelo hace posible y hoy no existe:

1. **El oráculo.** Perfil `PERFECTO`, pieza entera, sin bucle: la cadena reporta
   todas las notas, ninguna inventada, ninguna mal adjudicada.
2. **El oráculo con bucle.** Lo mismo con `--bucle` y cuatro repeticiones. **Esta
   es la prueba que la 3c dejó aparcada y que hoy falla**: se pierde la última
   nota de cada vuelta.
3. **El oráculo con cuenta atrás.** Con `compases_de_cuenta_atras=1`, que es
   donde la revisión de la 3c encontró que la cuenta atrás moría con el primer
   cuadro de audio.
4. **El informe dice la verdad.** Perfil con un compás sistemáticamente tarde:
   `InformeDePasada` tiene que señalar ese compás, y no otro, y decir «tarde».
5. **La regla del tempo.** Perfil perfecto dos pasadas: el tempo sube. Perfil
   malo: no sube.
6. **El trasteo no cuenta como acierto limpio.**
7. **El gemelo contra la guitarra real** (se salta sin grabaciones): el detector
   le da la misma nota a los dos, la proporción de ventanas acertadas del gemelo
   no es MAYOR que la de la grabación real más 0,10 —si el gemelo es más fácil
   que la guitarra, se quiere saber, y esa es la forma de preguntarlo—, y el
   tiempo hasta que la energía cae a la mitad queda dentro de un factor 2 del de
   la grabación. Hoy `tests/audio/` está vacío salvo `.gitkeep` y la prueba se
   salta siempre; las tolerancias están escritas ahora para que el día que
   existan las grabaciones nadie las elija a conveniencia de lo que salga.
8. **La sesión completa, a tiempo real** (marcada lenta): una pieza corta
   atraviesa `Sesion`, el servidor y el WebSocket, y el veredicto sale limpio.
   Pocas, porque cuestan segundos de reloj.

Ninguna prueba abre el dispositivo de audio real, que es la regla del proyecto:
el gemelo es precisamente lo contrario de abrir el dispositivo.

## 6. El navegador

El usuario pidió que el gemelo moviera la interfaz real. Lo hace, y **(mía)** lo
hace sin añadir dependencias: durante la sesión conduzco Chrome con las
herramientas que ya tengo, contra el servidor que levanta
`herramientas/gemelo.py`, y lo que queda grabado es lo que el usuario mira. La
interfaz, además, ya tiene 306 pruebas propias.

Meter Playwright en el proyecto para automatizarlo en la suite es una decisión de
dependencia con coste (navegadores que descargar, una suite nueva que mantener) y
no la tomo yo sola: queda anotada para cuando el usuario quiera pruebas de
extremo a extremo en CI.

## 7. Dependencias

Ninguna nueva. Karplus-Strong es numpy. El veredicto es Python. El dispositivo
simulado cumple el contrato que ya existe. `soundfile` solo se usa, como hoy, en
las pruebas que leen grabaciones y se saltan si falta.

## 8. Los defectos de la 3c que esta etapa cierra

La 3c los aparcó medidos. El gemelo los convierte en pruebas, así que se arreglan
aquí:

1. **El bucle arrastra el reloj unos 18 ms por vuelta, y desde la segunda vuelta
   NINGUNA nota cuenta como limpia.** La 3c aparcó esto como «con bucle se pierde
   la última nota de cada vuelta (250 ms)». Una sonda de este diseño lo midió y
   es bastante peor. Intérprete perfecto, ocho notas, tramo de dos compases,
   cuatro vueltas:

   | vuelta | acertadas | limpias | desfase que informa |
   |---|---|---|---|
   | 1 | 8/8 | 5/8 | −69 ms |
   | 2 | 7/8 | **0/8** | −91 ms |
   | 3 | 7/8 | **0/8** | −101 ms |
   | 4 | 7/8 | **0/8** | −123 ms |

   El alumno no cambió nada entre vueltas: el intérprete es perfecto en las
   cuatro. Lo que cambia es que `_al_dia` da la vuelta en cuanto el reloj CRUZA
   el final, sin esperar como sí espera la rama sin bucle, y cada vuelta se
   re-ancla perdiendo el exceso. El efecto compuesto es que el programa le dice a
   quien machaca un compás que se adelanta cada vez más, y que el tempo
   automático **nunca puede subir con el bucle puesto** porque la proporción
   limpia es cero desde la segunda vuelta.

   Esto convierte el defecto en el más grave de la lista: el bucle es el uso
   central de la 3c -«machacar el compás que fallé»- y está roto de una forma que
   1039 pruebas no ven, porque todas las del bucle usan dobles que avanzan el
   reloj a mano.
   **Cómo se arregla (mía).** Son dos causas, no una, y la segunda solo la vio la
   sonda:

   - **El exceso perdido.** `_dar_la_vuelta` llama a `avanzar_a(inicio)` y tira el
     exceso con que el reloj cruzó el final. El audio de la vuelta siguiente
     empieza donde tocaba, pero el reloj empieza re-anclado, y la diferencia se
     acumula vuelta a vuelta: son los ~18 ms por vuelta de la tabla. Se arregla
     dando la vuelta a `inicio + exceso` en vez de a `inicio`: el reloj conserva
     lo que ya había corrido, que es lo único que mantiene las dos líneas de
     tiempo juntas.
   - **La nota de la frontera.** `avanzar_a` deja `_analisis_desde` sin fijar y
     `_adjudicar` descarta por contrato los onsets anteriores al primer cuadro
     posterior al salto; el detector firma hasta 250 ms después, así que la última
     nota de cada vuelta cae siempre en ese agujero. La salida que usó la 3c sin
     bucle —APLAZAR la recolocación— aquí no sirve: la vuelta tiene que darse a
     tiempo o deja de ser música.

     De las tres opciones posibles elijo **retener las pulsaciones en vuelo y
     volcarlas al informe de la vuelta que cierra**, sin cirugía en
     `seguimiento.py`. Es la que no toca el módulo que el propio código declara
     el más delicado del proyecto, y la que deja la semántica donde pertenece.

     **La semántica, dicha en claro: una nota pertenece a la vuelta en que se
     ATACÓ, no a la vuelta en que el detector la resolvió.** Una nota atacada 50
     ms antes del final del tramo cuenta en la vuelta que cierra, aunque su onset
     se firme ya dentro de la vuelta nueva. Es lo que diría cualquiera mirando sus
     propios dedos, y la alternativa —cobrarla en la vuelta que abre— le regala a
     la vuelta nueva una nota que no tocó en ella y se la roba a la que la pagó.

   El defecto 4 (`peores_compases` no multiplica por `repeticiones`) **no cae por
   sí solo** con esta elección: sigue siendo un arreglo independiente, y por eso
   está en la lista con su propio número.

2. El historial, `peores_compases` y la regla del tempo pierden la nota del final
   cuando el detector la firma tras el tick del WebSocket.
3. Durante esos 250 ms, `indice_actual` y el contador de progreso delatan el
   exceso, y un rasgueo posterior cobra.
4. `peores_compases` no multiplica por `repeticiones`.
5. El `congelar_en` de `_observar` es letra muerta.
6. `pausar`/`reanudar` quedan fuera del candado.
7. `test_la_pausa_le_congela_el_reloj_tambien_al_seguidor` mide otra cosa que su
   nombre.
8. El docstring de `Seccion` en `modelo.py` dice «No se usan todavia» y es
   mentira desde la 3c (y vive en el núcleo).
9. El arrastre de la rejilla de compases no funciona en pantalla táctil, y el
   deslizador de tempo parpadea al soltar.

Del 1 al 4 los encuentra y los verifica el gemelo. Del 5 al 9 son arreglos a la
vista que no necesitan gemelo pero sí necesitan hacerse: están en la etapa porque
dejarlos otra vuelta más es cómo se acumulan.

## 9. Lo que sigue siendo del usuario

El gemelo no juzga nada de esto, y la etapa no pretende que lo juzgue:

- si la ventana de acierto escalada se siente justa al 50 %
- si la cuenta atrás de un compás da tiempo a colocar la mano
- si el click acentuado ayuda o estorba con ritmo aproximado
- si los pasos del 5 % de tempo son demasiado finos o bastos
- si «dos pasadas al 90 %» es la frontera correcta para subir
- si un `.gp5` real se toca, si la mano salta al importar, si el aviso de
  afinación acierta con la guitarra

Y siguen pendientes, de sesiones anteriores: grabar las seis cuerdas al aire
(`uv run python -m herramientas.grabar_muestras`) y calibrar el detector de
ataques (`uv run python -m herramientas.calibrar_ataques`). La prueba 7 del §5
empieza a dar valor en cuanto existan esas grabaciones.

## 10. Riesgos

- **El gemelo puede ser demasiado fácil.** Si su sonido es más limpio que una
  guitarra real, la cadena aprobará con él y fallará con el cable. Mitigación: la
  prueba 7 del §5, y perfiles con trasteo y desafinación de verdad. Es un riesgo
  que no desaparece: el gemelo reduce la sorpresa, no la elimina.
- **El veredicto puede volverse juez y parte.** Mitigación: el anti-objetivo
  del §2 y la regla del §3.5 de no importar reglas de `seguimiento.py`. Una
  revisión que vea `juzgar` consultando la ventana de acierto tiene que
  rechazarlo.
- **La cadena directa puede divergir de la real.** Mitigación: el nivel de sesión
  completa, con sus pocas pruebas lentas, existe justamente para detectar esa
  divergencia.
- **Las notas que se solapan generan ataques fantasma, y eso es de la cadena, no
  del gemelo.** Medido en la etapa, a la cadencia de PRODUCCIÓN y sobre nueve
  semillas (`tests/test_gemelo_sonido_sucio.py`): ocho notas que siguen sonando
  cuando entra la siguiente —`sustain=1.0`, 180 ms de cola encima de cada nota
  nueva— le hacen firmar al detector de **9 a 12** pulsaciones de ocho notas, y el
  veredicto cuenta de **1 a 5** invenciones; cada invención cuesta además una nota
  de verdad, porque el reporte inventado ocupa el puesto del emparejamiento. Con
  `sustain=0.0`, el mismo intérprete sobre la misma pieza, no hay ni un fantasma:
  la causa es el solape.

  (**Las dos cifras que esta spec traía eran de una sonda y no son reproducibles.**
  El «doce» sale solo con dos de las nueve semillas, y era además otra pieza —`B2`
  y `D3`— en otro régimen —95 % del pulso—. Y los «32 ms» no son un dato del
  detector: son `CUADROS_PARA_NOTA_ESTABLE` (3) por el salto de 512 muestras de
  aquella sonda (10,67 ms). A la cadencia de producción toda separación es
  múltiplo de 21 ms, así que 32 ms es **imposible por construcción**; el número
  estructuralmente análogo es el suelo de tres cuadros, **63 ms**, y con
  `sustain=1.0` y la semilla 0 las separaciones medidas por debajo de 200 ms son
  tres, de **105, 126 y 168 ms**. Los tres números, y el suelo de 63 ms, son
  mediciones de sonda que NINGUNA prueba afirma: quien los use en la etapa 3e
  vuelve a medirlos antes. Y el «60 % del pulso», que esta spec traía como
  régimen donde «salen ocho exactas», pertenece al mismo juego de sondas no
  reproducibles: no se afirma nada de él.) En una guitarra de verdad las
  cuerdas SÍ siguen sonando unas sobre otras, así que esto no es un artefacto de
  laboratorio: es un acierto fantasma esperando a pasar, y en la etapa 3e -donde
  un acierto fantasma rompe una racha o la regala- importa el doble. El gemelo
  tiene que poder producirlo a propósito (notas largas, perfil con sustain) y la
  cadena tiene que decidir qué hace con él. Esta spec NO lo arregla: lo deja
  medido y nombrado, porque arreglarlo es cambiar el detector de ataques, que es
  el corazón de las etapas 2a y 3a, y eso merece su propia decisión.
