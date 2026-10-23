# proyecto_musica

Software libre para practicar guitarra en macOS con el cable Rocksmith Real Tone.
Etapa 1: afinador y monitor de notas en el mástil. Etapa 2a: ejercicios
monofónicos (escalas, arpegios, intervalos y lectura) con corrección de nota,
afinación y tempo. Etapa 3a: el carril, para tocar una pieza con la música
corriendo. Etapa 3b: importar canciones de Guitar Pro, MusicXML, MIDI y
tablatura de texto.

## Requisitos

- macOS con permiso de micrófono concedido al terminal
  (Ajustes del Sistema → Privacidad y seguridad → Micrófono)
- Python 3.13 (pyenv) — el archivo `.python-version` fija `3.13.1`, y `uv`
  lo respeta automáticamente al crear el entorno
- [uv](https://docs.astral.sh/uv/) como gestor del entorno Python
- pnpm
- Cable Rocksmith USB Guitar Adapter

## Instalación

```bash
uv sync
cd interfaz && pnpm install && pnpm build && cd ..
```

`uv sync` crea `.venv/` con Python 3.13.1 (según `.python-version`), instala las
dependencias de ejecución y el proyecto en modo editable, según lo fijado en
`uv.lock`.

## Uso

```bash
uv run guitarra
```

Abre `http://127.0.0.1:8420` en el navegador.

Opciones del comando:

- `--puerto`: cambia el puerto en el que escucha el servidor (por defecto 8420).
  Ejemplo: `uv run guitarra --puerto 8080`.
- `--sin-navegador`: levanta el servidor sin abrir el navegador automáticamente.

### El dispositivo se detecta solo

El selector **Dispositivo** viene en **Automático**: el cable Rocksmith se busca
por su nombre en cada intento de apertura, que ocurre cada pocos segundos. Eso
significa que puedes enchufar el cable con el servidor ya abierto y el afinador
lo recogerá sin que toques nada, y que desenchufarlo y volver a enchufarlo
funciona igual aunque macOS le cambie el número de entrada, cosa que hace a
menudo.

Si eliges un dispositivo concreto, se guarda **por su nombre** y se respeta
mientras siga conectado. Guardarlo por índice, como se hacía antes, dejaba el
afinador diciendo «reconéctalo» con el cable enchufado delante en cuanto macOS
renumeraba las entradas. Si el que elegiste desaparece y el cable está presente,
se usa el cable y el aviso de arriba lo dice: sustituirlo en silencio sería peor.

Si el cable está conectado y aun así no captura, mira el mensaje de la barra
superior. `otro_dispositivo` significa que se está capturando otra entrada;
elige el cable en el selector. Un error del sistema al abrirlo
(`PaErrorCode -9986` y parecidos) casi siempre es el permiso de micrófono sin
conceder —**Ajustes del Sistema → Privacidad y seguridad → Micrófono**, para la
aplicación desde la que lanzaste el servidor, y reinicia después— o bien otra
aplicación que tiene el cable tomado.

Si desconectas el cable mientras tocas, el afinador pasa a silencio y vuelve a
abrirlo solo en cuanto lo enchufas de nuevo: no hace falta reiniciar nada.

El botón **Calibrar ruido** mide el piso de ruido de tu equipo durante dos
segundos —no toques nada mientras dura— y guarda el umbral resultante en la
configuración. El valor vigente se muestra siempre junto al botón.

### Ejercicios

Junto al afinador hay un módulo de ejercicios con cuatro familias: escalas,
arpegios, intervalos y lectura (posiciones sueltas en el mástil). Cada
ejercicio se resuelve nota a nota: mientras no toques la nota pedida el
ejercicio no avanza, y si te equivocas se te dice qué nota sonó en su lugar.
Una nota correcta pero desafinada **sí** cuenta como acierto —la afinación no
bloquea el avance—, y su desviación en cents queda registrada para el informe
final. Si fallas la misma nota cinco veces seguidas, el mástil la resalta
para ayudarte a encontrarla.

En los ejercicios de intervalo el software **hace sonar la nota de referencia**
por los altavoces al entrar en cada nota, y tú tocas la que está al intervalo
pedido: eso es lo que los convierte en entrenamiento de oído y no en otro
ejercicio de lectura. Si no hay salida de audio disponible, el ejercicio sigue
sin el tono, igual que sigue sin metrónomo.

Al perder la señal (el cable desenchufado, por ejemplo) el ejercicio se
**pausa**: el metrónomo calla y el temporizador de la ayuda deja de contar.
Ambos vuelven solos en cuanto reaparece la señal.

Al terminar el ejercicio, el informe muestra los aciertos a la primera, las
notas que costaron más intentos y la desviación mediana en cents.

**Límite conocido del evaluador:** dos pulsaciones seguidas de la misma nota
solo se distinguen si entre ellas hay un hueco de unos 63 ms en el que el
detector no dé **ninguna** nota como creíble. La caída de volumen no ayuda: el
evaluador compara **nombres de nota**, no niveles, así que por muy articulada
que sea la segunda pulsación queda descartada mientras el tono siga siendo
creíble. Cuando la nota pedida cambia el problema no existe, porque la altura
nueva sí es algo que el evaluador ve. Los ejercicios generados no piden nunca la
misma nota dos veces seguidas, precisamente por esto: cuando el mástil solo
ofrece una nota alcanzable —un único traste de una única cuerda— el ejercicio
sale de una sola nota en lugar de repetirla. Si aun así te quedas sin poder
avanzar, lo que evita que te atasques es el aviso por tiempo: resalta la nota en
el mástil a los doce segundos de haber detectado señal que pudiera ser un intento
de la nota pedida. Ese reloj se reinicia al acertar, no al fallar.

### El carril

El módulo **Carril** (junto a Afinador y Ejercicios) toma uno de los ejercicios
generados, lo convierte en una **pieza** —cada nota con su cuerda, su traste y su
sitio en el tiempo— y la hace llegar hacia ti: toca cada nota cuando alcance la
línea de ataque, la que cruza el carril cerca del borde de abajo (por debajo de
ella queda la estela de lo que ya sonó). Eliges la familia, opcionalmente un
tempo, y pulsas **Empezar**.

**La diferencia con los ejercicios es de fondo: aquí la música no espera.** En un
ejercicio la nota pedida aguarda hasta que la aciertas; en el carril el reloj
corre solo. Una nota que no tocas pasa y se queda sin marca; una nota que
tocas queda marcada, acertada o no, y el resumen final dice de cada una si fue *a
tiempo*, *pronto* o *tarde* y por cuántos milisegundos. Si tocaste otra nota en
lugar de la pedida, se ve cuál: tanto en el resumen («Pedida A2, tocaste A#2»)
como en la vista escrita. Fallar no detiene nada: informa.

**Cambiar de afinación corta la pieza.** Si cambias el perfil con una pieza en
marcha, el carril se detiene y la pantalla lo dice: la pieza estaba escrita para
la afinación anterior y seguir dibujando sus trastes es peor que no dibujar nada
(spec §7, la misma razón por la que una pieza en otra afinación se rechaza al
empezar). Se vuelve a empezar cuando quieras, ya en la afinación nueva.

El carril se pausa por dos reglas distintas:

- **Cinco segundos por debajo del umbral de ruido**: el cable está puesto pero no
  suena nada, o dejas de tocar. El carril se pausa a los 5 s y sigue donde estaba
  en cuanto vuelves a sonar.
- **Captura cerrada**: desenchufas el cable con el carril en marcha, o arrancas sin
  él (o sin permiso de micrófono). La sesión revisa cada segundo si el dispositivo
  sigue ahí, así que al desenchufar el carril se pausa en cosa de un segundo, no
  de cinco; al arrancar sin captura, desde el primer momento.

**No hay cuenta atrás ni metrónomo.** La primera nota está escrita en el instante
cero, el mismo en que pulsas **Empezar**, así que llegar *a tiempo* a la primera
nota es prácticamente imposible, y nada en el carril marca el pulso: el ritmo lo
llevas tú con lo que ves caer.

**La ventana de ±80 ms.** Una pulsación cuenta como *a tiempo* si cae a menos de
80 ms de donde la nota está escrita; entre 80 ms y el límite de la ventana de
reclamo (más abajo) se marca *pronto* o *tarde*. **Ese
número está razonado, no medido tocando**: sale de que por debajo de unos 30 ms dos
ataques no se oyen separados, de que por encima de unos 100 ms el desfase ya se
oye como error, y de la latencia del cable (13,8 ms según la medición anotada en el código), pero nadie ha
sentado a un alumno con la guitarra a ver cuándo siente que llegó tarde. Si te
parece indulgente o severo, hay que ajustarlo: es la constante `VENTANA_A_TIEMPO_S`
de `nucleo/piezas/seguimiento.py`.

**La ventana de reclamo, y lo que queda fuera de ella.** Para decidir a qué nota
pertenece una pulsación, cada nota solo puede ser reclamada desde una ventana, y
esa ventana es **asimétrica**. Llegando tarde: su duración escrita más 80 ms, con
un **mínimo** de 0,5 s (`VENTANA_RECLAMO_MINIMA_S`, tampoco medido tocando); una
negra a 240 ppm tiene 0,5 s y a 80 ppm, 0,83 s. Llegando pronto: solo ese mínimo
de 0,5 s, porque el argumento de la duración —la nota todavía suena, así que sigue
siendo un intento de ella— solo vale hacia un lado, y aplicado hacia el otro
dejaba reclamar una redonda a 40 ppm seis segundos antes de que existiera. **Una
pulsación que no cae en la ventana de ninguna nota no se marca «tarde»: se
descarta sin dejar rastro**, y no cuenta como fallo ni aparece en el resumen. Las
notas ya cobradas tampoco cuentan como ventana disponible: una pulsación cuya
única nota cercana ya se cobró se descarta igual.

**Lo que ya sonó se queda a la vista.** Una nota tocada no desaparece en cuanto
termina: sigue bajando un segundo por debajo de la línea de ataque, con su color.
Es lo que permite ver el patrón de una afinación de un vistazo —si todas las notas
de una cuerda salen del mismo color, no es tu dedo, es la cuerda—.

**La vista escrita.** El botón **Tablatura y pentagrama** del conmutador de vista
muestra la misma pieza repartida en compases, para leerla antes de tocar y para
repasar después lo tocado. Cada nota ya tocada se pinta con el color de su
desviación: verde si está a menos de 5 cents, ámbar si sonó por encima, azul si
sonó por debajo y gris si no se pudo medir. Así debería verse el patrón de una afinación:
si una cuerda está desafinada, las notas que toques en ella saldrán todas del
mismo color, ámbar o azul. La nota en curso lleva un aro en el pentagrama y un resalte en la
tablatura, y si tocaste otra nota en lugar de la pedida se escribe al lado con su
nombre. **Lo que está comprobado son los colores (pruebas de la interfaz), no
el patrón sobre una guitarra desafinada a propósito**: esa prueba sigue pendiente.

**Límites de esta etapa**, sin maquillar:

- **Una sola voz, sin acordes.** El modelo de pieza admite dos notas en el mismo
  instante, pero el carril no sabe seguirlas: el detector de tono es monofónico y
  de un acorde lee una sola altura. Las demás notas se quedan sin cobrar por muy
  bien que las toques.
- **Sin ligados ni bends.** El modelo de nota no tiene dónde guardarlos.
- **En las piezas que salen de un ejercicio, la digitación se elige por cercanía
  al traste anterior**, sin mirar lo que viene después (`elegir_posicion` de
  `nucleo/piezas/desde_ejercicio.py`). Basta para una escala en una posición. Las
  canciones importadas **no** pasan por ahí: usan el coste mínimo sobre la pieza
  entera que se explica en la sección siguiente.
- **El pentagrama es aproximado.** Está en clave de sol (las notas se escriben una
  octava por encima de lo que suenan, como se escribe la guitarra, pero la clave
  es un 𝄞 simple, sin el «8» que lo indica) y no lleva indicación de
  compás, ni corchetes en las corcheas, ni silencios, ni puntillos, y escribe los
  bemoles como sostenidos (un si bemol sale como la sostenido). Sirve para leer
  dónde tocar, no para editar partituras.
- **La tablatura cuantiza a semicorcheas**: una nota que empieza entre dos
  casillas se escribe en la más cercana.
- Las piezas de esta sección son las que salen de los generadores de ejercicios
  (escalas, arpegios, intervalos y lectura). En el carril el intervalo no hace
  sonar la nota de referencia. Las canciones importadas llegan al mismo carril y
  por la misma puerta; están en la sección siguiente.

### Canciones

El módulo **Canciones** (junto a Afinador, Ejercicios y Carril) importa una
canción de un archivo y la convierte en una **pieza**, el mismo modelo que mueve
el carril. Se llega de dos maneras, y las dos están en la misma pantalla: la
**biblioteca** es la carpeta `canciones/` de la raíz del proyecto, y encima de la
lista hay **Añadir una canción**, que sube un archivo desde el disco. No hay base
de datos: la carpeta ES la base de datos, y el identificador de una canción es el
nombre de su archivo. La carpeta la crea el servidor al guardar la primera
canción; antes de eso no existe.

**La carpeta `canciones/` está fuera de git**, y a propósito: las partituras y las
tablaturas son material de terceros con derechos de autor. El programa es software
libre; su contenido no es nuestro. Está en `.gitignore` y no hay ni un archivo de
canciones registrado en el repositorio.

**Los cuatro formatos, y qué trae cada uno.** Esto es lo que de verdad decide
cuánto se parece lo que ves a lo que el autor escribió:

| Formato | Extensiones | Qué trae |
|---|---|---|
| Guitar Pro | `.gp3` `.gp4` `.gp5` | **Todo**: cuerda, traste, ritmo, tempo, compás, afinación y los marcadores como secciones. El lector no recalcula la digitación: si la canción dice que el sol se toca en el traste 3 de la sexta, se toca ahí. |
| MusicXML | `.xml` `.musicxml` `.mxl` | El **ritmo**, el tempo y el compás siempre; la **tablatura solo a veces** —cuando la nota trae `<string>` y `<fret>`—, y entonces se respeta. Cuando no viene, la pone el algoritmo de digitación. **No declara la afinación** nunca, ni aunque traiga tablatura. |
| MIDI | `.mid` `.midi` | Las **alturas y el ritmo exactos**, y **nada de dónde se toca**: no hay cuerda ni traste. Toda la digitación la pone el algoritmo. No declara la afinación. |
| Tablatura de texto | `.txt` `.tab` | Cuerda y traste —y la afinación, si la primera columna trae las letras de las cuerdas—. **No trae ritmo**: las duraciones se deducen del espaciado, la pieza sale marcada como aproximada y la pantalla lo avisa antes de empezar. |

**`.gpx` y `.gp` no se pueden leer, y se rechazan al subir.** Son los formatos de
Guitar Pro 6 y 7, y la librería que usamos (PyGuitarPro 0.11) solo trae lectores de
gp3, gp4 y gp5: no es menos cobertura, es ninguna. Así que no entran en la
biblioteca —antes se subían y reventaban después, al pedir las pistas, hablando de
versiones en otra pantalla— y el rechazo dice qué hacer: ábrelo en Guitar Pro o en
TuxGuitar y expórtalo como `.gp5`. La regla de la tabla de arriba es esa: **si una
extensión está en la lista, se puede abrir**, y hay una prueba que abre un archivo
de verdad de cada una de las diez para que siga siendo cierto.

**La digitación por coste mínimo.** Donde el archivo no dice dónde se toca cada
nota —MIDI siempre, MusicXML sin tablatura—, la pone `nucleo/piezas/digitacion.py`
resolviendo la pieza **entera** por programación dinámica, no nota a nota: el
estado es la pareja (posición, traste donde está la mano) y el resultado es el
mínimo exacto, no una aproximación. Mil notas se digitan en unos **35 ms**
(mediana de siete pasadas en un MacBook Pro M1 Pro; entre 32 y 37 ms).

Qué mejora, con lo que mide cada número:

- **Nunca cuesta más** que la heurística de cercanía de la etapa 3a, con la misma
  función de coste para las dos (`tests/test_digitacion.py`).
- **El recorrido de la mano baja un 37 %** sobre material aleatorio (200 secuencias
  de 20 notas) y un 98 % en una escala de do mayor de 120 notas. No hay una cifra
  única: depende entero del material.
- **El salto crudo de traste a traste entre notas pisadas sale un 10 % PEOR**, y
  peor en 123 de esas 200 secuencias. No es una contradicción, es qué optimiza: el
  coste mínimo prefiere las cuerdas al aire, que son gratis, y eso separa los
  trastes de las notas pisadas sin mover la mano. Quien lea solo «37 % menos
  movimiento» se lleva una idea falsa del algoritmo.
- **Los pesos están razonados y NO medidos tocando**: mover la mano un traste
  cuesta 1,0, cruzar una cuerda 0,3, una cuerda al aire 0, y los dedos abarcan 5
  trastes (`CosteDigitacion`). Si la digitación sale cómoda o no **lo juzga el
  usuario con la guitarra en las manos**, y eso está sin hacer. Si sale incómoda se
  cambia un número, no el algoritmo.

**Si la canción está en otra afinación, te dice a cuál afinarte y te lleva al
afinador.** Al elegir una canción, el servidor compara la afinación que pide el
archivo con la tuya activa y contesta `coincide`, que tiene **tres** valores y los
tres significan cosas distintas:

- `true`: la canción está en tu afinación. No hay nada que hacer.
- `false`: está en otra. La pantalla lo dice y ofrece **Afinarme a … e ir al
  afinador**, que cambia el perfil activo y te lleva allí.
- `null`: **el archivo no dice en qué afinación está**, que es lo que pasa con
  MIDI y con MusicXML. Entonces no hay nada que avisar: la pieza se importa en el
  perfil activo y el carril la acepta. Aquí no se te pide afinarte nada.

**El carril no la aceptará hasta que lo hagas, y esa es la regla de la etapa 3a, no
una nueva de esta**: una pieza escrita para otra afinación se rechaza con un 400 al
empezar, por la misma razón por la que cambiar de perfil con una pieza en marcha la
corta. Dibujar los trastes de una afinación con la guitarra en otra es peor que no
dibujar nada. Previsualizar sí se puede: importar una canción y ver sus notas no
pasa por el carril, que es justo lo que hace falta para saber a qué afinarte.

**El aviso funciona también con una afinación que no es de fábrica**, y a la
primera. De fábrica son estándar, Drop D y los dos bajos; una canción en Drop C no
está en esa lista, y es precisamente la que necesita que le digan a qué afinarse.
El perfil de una afinación rara se da de alta al **listar** las pistas, no solo al
importarlas, y la clave que propone el listado es exactamente la que va a traer la
pieza: afinarte a lo que te dicen basta para que el carril te acepte. El selector
del afinador no se llena por mirar canciones —publica las de fábrica más la activa—,
así que la afinación rara aparece en él cuando te afinas a ella, que es cuando hace
falta para dibujar bien el mástil.

Un borde que queda, porque la honestidad está en los bordes: **solo Guitar Pro y la
tablatura de texto declaran su afinación.** MIDI y MusicXML no, así que con ellos
`coincide` es siempre `null` y la pieza se lee en tu perfil activo, cuadre o no con
lo que el autor tocaba.

**Poner una canción en el carril** es `POST /api/piezas/iniciar` con
`{cancion, pista, perfil}` —el nombre del archivo, el número de pista en base 1 y,
opcionalmente, la afinación con la que leerla—. Es una forma nueva de esta etapa,
al lado de la `{familia, parametros}` de la etapa 3a. La canción la lee el
**servidor**, no el navegador: así hay una sola puerta al carril, la que comprueba
la afinación.

**El techo de la subida son 10 MB por archivo**, y la letra pequeña importa porque
la versión anterior de esta promesa era falsa. Con un `Content-Length` honesto, la
petición se rechaza antes de leer el cuerpo. Si la cabecera miente, o no viene
(`chunked`), **el cuerpo entero llega** y lo que lo para es la medida real del
archivo ya recibido. Las tres rutas acaban en un 400 con el número de bytes de
verdad; lo que no se promete es que un archivo enorme no viaje por el cable. Una
partitura de una canción entera ocupa decenas de kilobytes: diez megas son dos
órdenes de magnitud de margen.

**Límites de esta etapa**, sin maquillar:

- **Los acordes se importan y no se siguen.** El modelo de pieza admite varias
  notas en el mismo instante y el carril las pinta, pero debajo hay un detector de
  tono monofónico: de un acorde lee una sola altura, se cobra **una** nota y las
  demás quedan sin cobrar por bien que las toques.
- **Ligados, bends y armónicos se ignoran.** No es una decisión, es que la nota de
  una pieza tiene cinco campos —altura, cuerda, traste, instante y duración— y no
  hay dónde guardarlos. En Guitar Pro una ligadura sí hace lo correcto, que es
  alargar la nota anterior en vez de pedir un ataque nuevo, y una nota muerta
  desaparece. En la tablatura de texto `h`, `p`, `b`, `/`, `\`, `~`, `x` y los
  paréntesis se tiran: `5h7` son dos ataques, un 5 y un 7, y la `x` no existe.
- **Las repeticiones se expanden**, que es lo correcto: una repetición corriente
  suena dos veces y la pieza dura lo que suena. Pero **las casillas de primera y
  segunda vez producen un compás de más**: con `|: A | B(1ª vez) :|` y `C` como
  segunda vez, lo que debería sonar es A B A C y lo que suena es A B A B C. El
  compás de más sigue ahí —arreglar el expansor es la etapa 3c—, pero **ya no es
  en silencio**: el lector lee las casillas (`repeatAlternative` de las cabeceras)
  y la pantalla lo avisa antes de empezar, con el ejemplo de lo que suena y de lo
  que debería sonar. Es el estándar de esta etapa: si se detecta, se avisa.
- **Las secciones se importan y todavía no las usa nada.** Los marcadores de
  Guitar Pro, las marcas de ensayo de MusicXML y los marcadores de texto de MIDI
  entran en la pieza porque reconstruirlos después sería imposible, pero ninguna
  pantalla los muestra: son para la etapa 3c.
- **Una canción que cambia de tempo o de compás se toca entera con el primero.**
  `Pieza` guarda uno solo. Eso **sí se avisa** antes de empezar, con el número que
  se va a usar («la canción CAMBIA DE TEMPO y aquí se toca entera a 76 ppm»), pero
  avisar no es tocarlo bien. Y en el caso del compás hay un daño extra: la vista
  escrita trocea la pieza con **un** compás constante, así que con un 3/4 en medio
  las barras caen en el sitio equivocado desde ahí hasta el final —el aviso lo dice
  también—.
- El ritmo que se deduce de una tablatura de texto es una heurística declarada:
  la distancia más corta de toda la tablatura se toma como una negra. Funciona en
  tablaturas bien alineadas y falla sin avisar en las que no.
- **Nada de esto se ha probado con la guitarra en las manos.** Que un `.gp5`
  exportado de verdad entre y se toque, que la digitación salga cómoda, que el
  aviso de afinación sirva con el instrumento delante, que el ritmo de una
  tablatura pegada de un foro se pueda seguir y que una canción de tres minutos no
  atasque el carril: las cinco **están pendientes**, y las cinco necesitan el cable
  y archivos reales.

**Practicar por secciones, con bucles y tempo ajustable, es la etapa 3c.** Y hay
una cosa que conviene tener delante antes de construirla: **la investigación
disponible sugiere alternar pasajes en vez de repetir uno en bucle**, al revés que
el *Riff Repeater* de Rocksmith. Es Carter y Grahn (2016, *Frontiers in
Psychology*), que compararon práctica en bloque contra intercalada y encontraron
que gana la intercalada —y, de propina, que la mayoría de los participantes creía
lo contrario—. **Son diez sujetos**: es una señal, no una ley, y sin ese matiz la
frase suena a verdad establecida.

## Verificar el cable

```bash
uv run python -m herramientas.verificar_cable
```

Comprueba que el dispositivo aparece, mide la latencia y reconoce las notas que toques.

## Calibrar la deteccion de ataques

```bash
uv run python -m herramientas.calibrar_ataques
```

Pulsa una cuerda ocho veces separadas y la herramienta propone el salto y el
refractario que mejor cuentan tus pulsaciones. Los valores por defecto estan
elegidos a ojo; esto los ajusta a tu pua y tu pastilla.

## Pruebas

```bash
uv run pytest             # núcleo y servidor
cd interfaz && pnpm test  # interfaz
```

Las pruebas de `tests/test_audio_real.py` y `tests/test_ataques_reales.py` usan
las mismas grabaciones reales de `tests/audio/`. En un checkout nuevo esas
grabaciones todavía no existen, así que esas pruebas aparecen como saltadas
(`skipped`): es lo esperado, no un fallo. Para regenerarlas:
`uv run python -m herramientas.grabar_muestras`.

## Estructura

- `nucleo/` — captura de audio, análisis y teoría musical. Python puro, sin
  dependencias del servidor ni de la interfaz.
- `servidor/` — FastAPI: registro de módulos, configuración, diagnóstico,
  biblioteca de canciones y emisión por WebSocket. El registro de módulos es lo
  que ha permitido añadir ejercicios, el carril y las canciones sin tocar el
  armazón.
- `canciones/` — tu biblioteca. **No está en git**: son archivos de terceros. La
  crea el servidor al guardar la primera canción.
- `interfaz/` — React + Vite.
- `herramientas/` — utilidades de línea de comandos.
- `docs/superpowers/` — especificación y plan.

## Estado

Etapas 1, 2a, 3a y 3b completas, con la salvedad de que las cinco
comprobaciones de la 3b que necesitan la guitarra y archivos reales siguen
pendientes (están listadas en **Canciones**). Las siguientes, según el diseño:

2b. Ejercicios de acordes
3c. Practicar una pieza entera: secciones, bucles y tempo ajustable
4. Grabación de sesiones, medición de progreso, entrenamiento de oído y efectos
