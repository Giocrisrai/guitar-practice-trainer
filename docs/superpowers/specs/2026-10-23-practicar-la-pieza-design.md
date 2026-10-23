# Etapa 3c — Practicar la pieza: compases, bucles y tempo

**Fecha:** 2026-10-23
**Estado:** propuesta
**Etapas previas:** 1 (núcleo y afinador), 2a (ejercicios monofónicos), 3a (el carril), 3b (importar canciones)

## 1. Qué se construye y por qué

Desde la etapa 3b puedes importar una canción y verla venir por el carril. Lo que
no puedes es **estudiarla**: la canción empieza, pasa, y termina. Si el compás 19
se te resiste, la única forma de volver a él es tocarla entera otra vez, y a la
velocidad del disco.

Esta etapa convierte el carril en un sitio donde se practica:

- **Compases a la vista.** Una rejilla con el número del compás en curso, para
  orientarse y para poder decir «el 19».
- **Bucle.** Eliges un rango de compases y se repite, con una cuenta atrás entre
  repeticiones para colocar la mano.
- **Tempo ajustable.** Del 40 % al 100 % del tempo escrito, con click de
  metrónomo opcional.
- **Informe por compases.** Al terminar la pasada, dónde fallaste y, más útil,
  **hacia dónde**: «el 19 lo tocas entero 40 ms tarde».
- **Subida automática del tempo**, cuando el informe dice que ya te sale.

El ciclo que esto permite es el que el usuario pidió, en sus palabras: machacar un
trozo difícil, tocar la canción entera y ver dónde falló, leer con los compases a
la vista, y subir el tempo poco a poco sin tener que decidirlo él.

### Decisiones del usuario, tomadas en el brainstorming

1. **Los cuatro usos** (machacar, pasada entera con informe, navegación por
   compases, subida automática) entran en esta etapa.
2. **El bucle se elige de tres maneras**, que rellenan el mismo rango: a mano por
   compases, por sección de la canción, y desde el informe («machacar el 19, que
   has fallado 4 de 5 veces»). Con cuenta atrás entre repeticiones.
3. **Click de metrónomo con interruptor**, acentuando el primer tiempo del compás
   de la pieza, más un compás de cuenta atrás antes de arrancar y en cada
   repetición. El interruptor apagado es la opción «solo el carril».
4. **La pieza sonando de fondo queda fuera**: es la etapa 3d, con su propia spec.
   Requiere síntesis polifónica, mezcla y calibración de latencia contra el
   detector de ataques, y nada de eso se parece al resto de esta etapa.
5. **El historial dura lo que dure el servidor.** Nada se escribe en disco. «Lo
   fallas 4 de 5 veces» cuenta las pasadas de hoy.
6. **La ventana de acierto escala con el tempo.** Al 50 %, los ±80 ms se vuelven
   ±160 ms: lo que se juzga es la colocación dentro del compás, con la misma
   indulgencia a cualquier velocidad, y al subir el tempo la ventana se cierra
   sola.
7. **Las casillas de primera y segunda vez no entran.** `nucleo/piezas/modelo.py`
   prometía que arreglarlas era esta etapa; es un defecto de **lectura** de 3b, no
   de práctica. Esta etapa corrige esa frase para que no prometa una etapa
   equivocada, y el aviso al usuario se queda donde está, que es lo honesto.

### Fuera de alcance, deliberadamente

- **La pieza sonando.** Etapa 3d (decisión 4).
- **Las casillas de repetición.** Defecto de lectura de 3b (decisión 7).
- **Persistencia del progreso.** Nada en disco (decisión 5). El día que se quiera,
  el `HistorialDeEstudio` es el único sitio que habría que cambiar.
- **Acordes bien medidos.** Imposible con un detector monofónico; esta etapa no
  lo arregla, lo **declara** y lo saca de las cuentas (ver §4).
- **Cambios de compás dentro de la pieza.** `Pieza` no los guarda (ver §3).
- **Puntuación, estrellas, niveles.** Como en 3a y 3b: no hay.
- **Tempo por encima del escrito.** El techo es el 100 %. Practicar más rápido que
  el original es otra cosa.

## 2. Arquitectura: un objeto nuevo que envuelve al seguidor

Tres candidatos se consideraron, y la elección importa porque `SeguidorPieza`
tiene 509 líneas, dos relojes y una adjudicación de pulsaciones que costó mucho
dejar correcta:

- **Dentro de `SeguidorPieza`**: un tercer reloj (tiempo de pasada ≠ tiempo de
  pieza) en el archivo más delicado del proyecto. Descartado.
- **Dentro de `SesionCarril`, en el servidor**: el bucle solo se podría probar
  levantando el servidor, y el factor de tempo no cabe ahí porque los instantes
  son del seguidor. Descartado.
- **Un objeto nuevo en el núcleo que envuelve al seguidor**: elegido. Lo nuevo en
  un archivo nuevo; lo viejo y delicado gana solo lo que no puede vivir en otro
  sitio.

Lo que ya estaba resuelto y esta etapa aprovecha: **`avanzar_a` ya sabe hacer el
salto del bucle**. No solo mueve el reloj: invalida la correspondencia con el
reloj del análisis y descarta las pulsaciones **en vuelo** anteriores al salto
(`nucleo/piezas/seguimiento.py`, `avanzar_a`). Sin eso, una nota tocada al final
de una repetición se adjudicaría al principio de la siguiente. Está hecho desde
la etapa 3a y esta etapa solo tiene que no estropearlo, con una prueba que lo
vigile.

```
interfaz/src/Carril.tsx ── rejilla de compases, controles, informe
          │  POST /api/piezas/{iniciar,plan,saltar,pausa}  GET /api/piezas/{pieza,informe}  WS /ws/piezas
servidor/piezas.py  SesionCarril ── delega el plan y el informe
          │
nucleo/piezas/estudio.py  SesionDeEstudio ── el plan, el salto del bucle, el informe
          │                    usa
nucleo/piezas/compases.py ── pulsos ↔ compases        nucleo/sintesis.py  Metronomo (ya existe)
          │                    envuelve
nucleo/piezas/seguimiento.py  SeguidorPieza ── +factor_tempo, +olvidar_tramo
```

## 3. `nucleo/piezas/compases.py`: el único que sabe de compases

Nadie en el proyecto convierte hoy pulsos en «compás 19», y lo necesitan cuatro
cosas a la vez: la rejilla, el rango del bucle, el acento del metrónomo y el
informe. Por eso es **un solo módulo**, y no una cuenta repetida en cuatro
sitios.

```python
def total_de_compases(pieza: Pieza) -> int:
    """Cuántos compases ocupa la pieza, contando desde 1."""

def compas_en(pieza: Pieza, pulsos: float) -> int:
    """En qué compás cae ese pulso. El primero es el 1, como cuentan los músicos."""

def pulsos_del_compas(pieza: Pieza, numero: int) -> tuple[float, float]:
    """[inicio, fin) en pulsos del compás `numero`. ValueError si no existe."""

def compases_de_la_seccion(pieza: Pieza, indice: int) -> tuple[int, int]:
    """Primer y último compás de la sección `indice`, para armar el bucle con ella."""
```

**La sección se pide por índice, no por nombre**, y es a propósito: `Seccion` solo
guarda `nombre` e `inicio_pulsos` (`modelo.py`), y los nombres **se repiten** —una
canción con dos estribillos trae dos secciones llamadas «Estribillo»—. Pedir «la
sección Estribillo» obligaría a elegir una de las dos en silencio, que es
exactamente la clase de empate que costó un Critical en la etapa 3b. La interfaz
manda el índice de la lista que ya recibió.

Y como `Seccion` **no guarda dónde acaba**, el último compás de una sección es el
anterior al comienzo de la siguiente, o el último de la pieza si es la última
sección.

**El pulso es el del denominador.** Con `compas = (7, 8)` el pulso es la corchea,
así que el compás ocupa 7 pulsos de corchea; con `(4, 4)`, 4 de negra. La
conversión usa el denominador y no un 4 fijo, porque `Pieza.tempo` está en pulsos
por minuto y el pulso lo define el compás.

**Una pieza sin notas tiene 0 compases**, y `compas_en` devuelve 1 en ella: no hay
compás donde caer, y 1 es el único número que no miente sobre el sitio del
cabezal. La rejilla, con 0 compases, no se dibuja.

**Numeración desde 1.** El núcleo cuenta las cuerdas desde 1 y los músicos cuentan
los compases desde 1. Los índices de notas de `EstadoCarril` siguen desde 0, que
es lo que ya publica. No se mezclan: lo que viaja como `compas` es siempre
1-basado y lo que viaja como `indice` es siempre 0-basado.

**Límite declarado: `compas_variable`.** `Pieza` guarda **un solo** compás, el del
principio (`modelo.py`, campo `compas_variable`), porque los lectores de 3b se
quedaron con el primero. Con un 3/4 en medio de un 4/4, las barras caen mal desde
el cambio hasta el final. Es el mismo defecto que ya tiene la vista escrita, y la
pieza ya trae la bandera. Esta etapa **no lo arregla** —haría falta guardar los
cambios de compás en el modelo, que es tocar los cuatro lectores— y en su lugar:
la rejilla y el informe muestran el aviso de la pieza, y la bandera viaja al
cliente. Fingir precisión aquí sería peor que no tener rejilla.

## 4. `nucleo/piezas/estudio.py`: el plan, el bucle y el informe

### El plan

```python
@dataclass(frozen=True)
class PlanDePasada:
    """Cómo se toca esta vez. No cambia la pieza: cambia la pasada."""
    primer_compas: int = 1
    ultimo_compas: int | None = None      # None es "hasta el final"
    factor_tempo: float = 1.0             # 0.5 es la mitad de rápido
    en_bucle: bool = False
    compases_de_cuenta_atras: int = 1
    con_click: bool = False
    tempo_automatico: bool = False
```

Valores por defecto = el comportamiento de la etapa 3a: pieza entera, tempo
escrito, sin bucle, sin click. Las piezas que vienen de los ejercicios no cambian
en nada.

Validación, con `ValueError` y mensaje en español:
`FACTOR_MINIMO = 0.40` ≤ `factor_tempo` ≤ `FACTOR_MAXIMO = 1.00`; `primer_compas`
≥ 1 y dentro de la pieza; `ultimo_compas` ≥ `primer_compas` y dentro de la pieza.
El suelo del 40 % está puesto porque más abajo el carril ya no se parece a música;
el techo del 100 % porque el tempo escrito es la meta.

### El factor de tempo escala los instantes **y las ventanas**

`SeguidorPieza` calcula `_inicios_s` una vez en `__init__` y su comentario dice
«no cambian nunca». El factor se aplica **al construirlo**, no después:

- `factor_tempo` entra como argumento del constructor y divide los instantes
  (`pulsos_a_segundos(...) / factor`), de modo que al 50 % todo dura el doble.
- Y multiplica las **tres** ventanas (`ventana_a_tiempo_s`,
  `ventana_reclamo_minima_s`, `ventana_altura_s`) por `1 / factor`. Esto es la
  decisión 6: al 50 %, ±80 ms se vuelven ±160 ms sin tocar la constante
  `VENTANA_A_TIEMPO_S`, que sigue siendo la referencia al tempo escrito.

Cambiar el factor a mitad de pasada reconstruye el seguidor en el compás en curso.
Es correcto y es lo único coherente: los instantes son inmutables por diseño.

### El añadido mínimo al seguidor

Dos cosas, y nada más:

```python
def __init__(
    self,
    pieza,
    detector=None,
    ventana_a_tiempo_s=VENTANA_A_TIEMPO_S,
    ventana_reclamo_minima_s=VENTANA_RECLAMO_MINIMA_S,
    ventana_altura_s=VENTANA_ALTURA_S,
    factor_tempo: float = 1.0,   # el último: los cinco de antes no cambian de sitio
) -> None

def olvidar_tramo(self, desde_s: float, hasta_s: float) -> None:
    """Deja sin cobrar las notas de [desde_s, hasta_s) y borra sus anotaciones."""
```

`factor_tempo` va **al final** de la firma y no antes de las ventanas: moverlas de
sitio, o volverlas de solo palabra clave, rompería las llamadas que ya existen en
`tests/test_seguimiento_pieza.py`. Un argumento nuevo no debe reordenar los
viejos.

`olvidar_tramo` es lo que permite repetir: al volver al principio del bucle, las
notas de ese tramo tienen que poder cobrarse otra vez. Borra su marca en
`_cobradas` y quita sus `NotaTocada` de `_tocadas` —que ya se habrán archivado en
el informe de la repetición que acaba—, todo bajo el candado que el seguidor ya
tiene.

### La sesión de estudio

```python
class SesionDeEstudio:
    """Un seguidor, un plan, y el informe de lo que va pasando.

    Traduce entre el tiempo de la PASADA (lo que el alumno está viviendo, con
    cuentas atrás y repeticiones) y el tiempo de la PIEZA (lo que está escrito).
    """
    def __init__(
        self,
        pieza: Pieza,
        plan: PlanDePasada = PlanDePasada(),
        detector: DetectorPulsaciones | None = None,
    ) -> None
    def avanzar_a(self, instante_pasada_s: float) -> EstadoEstudio
    def procesar(self, resultado, instante_analisis) -> EstadoEstudio
    def cambiar_plan(self, plan: PlanDePasada) -> EstadoEstudio
    def saltar_al_compas(self, numero: int) -> EstadoEstudio
    def pausar(self) -> None
    def reanudar(self) -> None
    @property
    def informe(self) -> InformeDePasada
    @property
    def historial(self) -> HistorialDeEstudio
```

`EstadoEstudio` envuelve el `EstadoCarril` que ya publica el seguidor y le añade
lo que la interfaz necesita para dibujar: `compas_en_curso`, `primer_compas` y
`ultimo_compas` del bucle, `repeticion` (cuántas van), `cuenta_atras_restante_s`,
`factor_tempo` vigente, `en_pausa`, y los avisos de la pieza
(`compas_variable`, `ritmo_aproximado`).

**El ciclo del bucle**, con cuatro cosas en orden que no se pueden intercambiar:
al llegar el reloj al final del último compás, (1) se cierra el informe de la
repetición, (2) se llama `olvidar_tramo` sobre el rango, (3) se llama
`avanzar_a(inicio_del_rango)` en el seguidor —que es lo que descarta las
pulsaciones en vuelo—, y (4) se abre la cuenta atrás. Durante la cuenta atrás el
reloj de la pieza se queda quieto en el inicio del rango: las notas no avanzan,
el click marca, y nada se puede cobrar.

### El informe

```python
@dataclass(frozen=True)
class CompasDelInforme:
    numero: int
    notas_escritas: int
    notas_medibles: int        # escritas menos las que un acorde tapa
    acertadas: int
    a_tiempo: int
    pronto: int
    tarde: int
    desfase_medio_s: float | None   # con signo: negativo es adelantarse
    tiene_acordes: bool

@dataclass(frozen=True)
class InformeDePasada:
    compases: tuple[CompasDelInforme, ...]
    ritmo_aproximado: bool
    compas_variable: bool
    factor_tempo: float
```

El dato que de verdad diagnostica es `desfase_medio_s` **con signo**: «el 19 lo
tocas entero 40 ms tarde» es accionable; «fallas el 19» no lo es. Sale de los
`NotaTocada.desfase_s` que el seguidor ya produce.

**Los acordes salen de la cuenta, y es obligatorio que salgan.** El seguidor dice
de sí mismo que no sabe seguir acordes: debajo hay un detector de tono
**monofónico**, así que de un acorde lee una sola altura y las demás notas de ese
instante «se quedan sin cobrar por muy bien que se toquen». En una canción de
Guitar Pro con acordes —la mayoría— eso haría que los compases con acordes
salieran siempre fallados, y el botón de «machacar el compás que fallas» te
mandaría sistemáticamente a los compases que **nunca** vas a poder pasar. Así
que: un compás con dos notas en el mismo `inicio_pulsos` se marca
`tiene_acordes=True`, sus notas tapadas no cuentan en `notas_medibles`, y el
compás no entra ni en el ranking de fallos ni en la regla del tempo.

**El aviso del ritmo inventado.** En una pieza con `ritmo_aproximado=True` —las
tablaturas de foro— el ritmo lo infirió el lector de 3b. Medir el desfase contra
un ritmo inventado y presentarlo como diagnóstico sería mentira, así que el
informe lo lleva en cabecera y la interfaz lo muestra arriba, no en una nota al
pie.

### El historial y la subida automática

```python
class HistorialDeEstudio:
    """Las pasadas de esta sesión. En memoria: al apagar el servidor se olvida."""
    def anotar(self, informe: InformeDePasada) -> None
    def peores_compases(self, cuantos: int = 3) -> tuple[tuple[int, int, int], ...]
        """(compás, pasadas falladas, pasadas contadas), peor primero."""
```

`peores_compases` es quien contesta «el 19 lo fallas 4 de 5 veces» y quien arma el
bucle de un botón. Los compases con acordes no aparecen.

**La regla del tempo automático**, con los números que el usuario aprobó:

- Dos pasadas seguidas con **≥ 90 %** de las notas **medibles** acertadas y a
  tiempo → el factor sube **0,05**.
- Una pasada por debajo del **70 %** → baja **0,05**.
- Techo **1,00**, suelo **0,40**.

Son cuatro constantes con nombre en un sitio, para que se puedan discutir tocando
y no leyendo código.

## 5. Servidor

`POST /api/piezas/iniciar` acepta un `plan` **opcional**; sin él, el carril se
comporta exactamente como hoy. Nuevos:

| Endpoint | Qué hace |
|---|---|
| `POST /api/piezas/plan` | Cambia tempo, bucle, click o tempo automático **sin reiniciar** la pasada |
| `POST /api/piezas/saltar` | Salta al compás *n* |
| `POST /api/piezas/pausa` | Pausa y reanuda a voluntad del usuario |
| `GET /api/piezas/informe` | El informe de la pasada en curso y los peores compases del historial |
| `GET /api/piezas/pieza` | La pieza en marcha (ver §7) |

`pausa` es un endpoint nuevo y no un reuso: el `pausado` que hoy publica
`SesionCarril` significa «no llega señal del cable», que es otra cosa, y
confundirlos haría que al desenchufar el cable pareciera que el usuario pulsó
pausa.

El estado del WebSocket `/ws/piezas` pasa a ser el `EstadoEstudio`: lo que ya
mandaba más compás en curso, repetición, cuenta atrás, factor y avisos.

### El metrónomo

`Metronomo(tempo, compas)` ya existe desde la etapa 2a, ya acentúa el primer
tiempo del compás que se le diga, y ya tiene `pausar`/`reanudar` sin bloquear el
hilo de análisis (`nucleo/sintesis.py`). El carril lo usa con
`round(pieza.tempo * factor)` y `compas = pieza.compas[0]`.

**El metrónomo lo tiene el servidor, no `SesionDeEstudio`.** El núcleo no abre
dispositivos de audio —lo mismo hace `SesionPractica` con los ejercicios— y
`SesionDeEstudio` tiene que poder probarse entera sin sonido. Pero el click hay
que rearrancarlo en cada repetición del bucle, y quien decide el salto es la
sesión de estudio. Se resuelve sin que el núcleo sepa de audio: `EstadoEstudio`
publica `repeticion`, y el servidor rearranca el metrónomo cuando ese número
cambia. Un contador es un dato; un `Metronomo` en el núcleo sería una dependencia.

Dos cosas declaradas en vez de escondidas:

1. **`iniciar()` devuelve `False` si no hay salida de audio.** Entonces el estado
   dice `click_sonando: False` y la interfaz escribe «sin click», en lugar de
   mostrar un interruptor encendido que no suena. Es el mismo estándar que la
   etapa 2a aplicó al «Sin metrónomo» silencioso.
2. **El click puede derivar.** Corre en su propio hilo con esperas de `60/tempo`,
   mientras el reloj del carril viene de los cuadros de análisis. En un bucle no
   se nota, porque cada repetición lo rearranca —hay que hacerlo igualmente por la
   cuenta atrás—; en una pasada entera de tres minutos puede separarse. Queda
   dicho aquí y en el docstring. Atarlo al reloj del carril sería emitir los
   clicks desde el hilo de análisis, y eso es otra etapa.

## 6. Interfaz

- **Rejilla de compases** bajo el carril: barras con el número del compás en
  curso destacado, y el rango del bucle pintado encima. Clic en un compás salta
  ahí; arrastrar sobre la rejilla marca el rango del bucle.
- **Controles**: tempo (deslizador del 40 % al 100 %, en pasos del 5 %), bucle
  sí/no, click sí/no, tempo automático sí/no, pausa.
- **Elegir el bucle por sección**: una lista con las secciones de la pieza, si las
  trae. Si no las trae, la lista no aparece —muchas tablaturas y MIDIs no tienen
  secciones— y queda el rango a mano.
- **Panel de informe** al terminar la pasada: tabla por compases con acertadas,
  a tiempo y desfase medio con signo; los compases con acordes marcados y
  explicados; los avisos de ritmo aproximado y compás variable en cabecera; y un
  botón «machacar el compás N» por cada uno de los peores, que arma el bucle y
  arranca.
- `interfaz/src/tiposPieza.ts` recibe los cinco campos que le faltan
  (`secciones`, `ritmo_aproximado`, `tempo_variable`, `compas_variable`,
  `casillas_de_repeticion`): ya decía ser espejo **parcial** de `Pieza.a_dict()`, y
  esta etapa necesita cuatro de los cinco. Añadirlos toca literales de prueba en
  dos archivos.

## 7. Dos deudas de 3a/3b que esta etapa tiene que cerrar

No son mejoras oportunistas: con bucles y click, las dos se vuelven visibles.

1. **Recargar el navegador a mitad de canción deja el carril en blanco.** La pieza
   viaja una sola vez, en la respuesta de `POST /api/piezas/iniciar`, y el
   WebSocket no la repite, así que la sesión que no hizo ese POST no tiene nada
   que pintar (está escrito en `interfaz/src/App.tsx`). Estudiando un bucle vas a
   recargar. Lo cierra `GET /api/piezas/pieza`.
2. **`POST /api/piezas/detener` no se llama al desmontar.** `useCarril.ts` cierra
   el WebSocket y se va, así que la pieza sigue corriendo en el servidor. Hasta
   ahora era invisible; **con el click sonando, se queda sonando**. Se llama en la
   limpieza del efecto, en el carril y en los ejercicios.

## 8. Errores

Todos con 400 y mensaje en español, como el resto del proyecto:

- Plan inválido: último compás antes del primero, compás fuera de la pieza, factor
  fuera de [0,40 – 1,00].
- `plan`, `saltar`, `pausa` o `informe` sin pieza en marcha: 400 diciendo que no
  hay nada que practicar.
- Sección que no existe en la pieza.
- Pieza sin notas: el bucle y el informe no se caen; `total_de_compases` es 0 y la
  rejilla no se dibuja.

## 9. Pruebas

**Núcleo, sin audio y sin servidor**, moviendo el reloj a mano con `avanzar_a`,
que es lo que la etapa 3a dejó preparado para esto:

- `compases.py`: 4/4, 3/4, 7/8 (el pulso es la corchea), el último compás
  incompleto, pieza vacía, compás fuera de rango, secciones a compases.
- El factor de tempo escala los instantes y **las tres** ventanas.
- `olvidar_tramo` deja volver a cobrar lo del tramo y no toca lo de fuera.
- **El salto del bucle no adjudica a la repetición nueva una pulsación de la
  anterior.** Es el caso que `avanzar_a` ya protege desde 3a; la prueba está para
  que nadie lo deshaga sin enterarse.
- La cuenta atrás no deja cobrar nada y no mueve el reloj de la pieza.
- El informe: desfase medio con signo, un compás con acorde marcado y sus notas
  tapadas fuera de `notas_medibles`, un compás con acordes fuera del ranking.
- La regla del tempo: sube a las dos pasadas buenas, no a la primera; baja con una
  mala; respeta techo y suelo.

**Servidor**: los cinco endpoints, los planes inválidos, el estado del WebSocket
con los campos nuevos, y que `iniciar` sin `plan` siga comportándose como hoy.

**Interfaz**: la rejilla marca el compás en curso, el clic salta, el arrastre
arma el rango, el panel de informe muestra los avisos, el botón de machacar arma
el bucle.

**Restricciones de prueba de las etapas anteriores, que siguen vigentes:**

- Ninguna prueba abre el dispositivo de audio real: el metrónomo se inyecta, como
  ya se inyecta en los ejercicios.
- Ningún archivo con derechos de autor entra en el repositorio: las piezas de
  prueba se construyen en código.
- `canciones/` no debe existir en la raíz al terminar la suite.
- `nucleo/` no importa de `servidor/` ni de `interfaz/`, y `modelo.py` no importa
  de `nucleo/ejercicios/`.

**Y la lección de la etapa 3b, escrita aquí porque volverá a pasar:** aparecieron
diez pruebas que no podían fallar, varias nacidas de los briefs. El antídoto que
funcionó no es «escribe una prueba», es **«rompe el código y di cuántas
cayeron»**. Quien ejecute este plan lo aplica a cada tarea.

## 10. Lo que solo el usuario puede juzgar

Con el cable y la guitarra, cuando esté hecho:

- Si la ventana escalada se siente justa al 50 % o si regala aciertos.
- Si la cuenta atrás de un compás da tiempo a colocar la mano.
- Si el click acentuado ayuda o estorba en una pieza con ritmo aproximado.
- Si los pasos del 5 % en el tempo son demasiado finos o demasiado bastos.
- Si «dos pasadas al 90 %» es la frontera correcta para subir, o es demasiado
  exigente para un compás de verdad difícil.
