# proyecto_musica

Software libre para practicar guitarra en macOS con el cable Rocksmith Real Tone.
Etapa 1: afinador y monitor de notas en el mástil. Etapa 2a: ejercicios
monofónicos (escalas, arpegios, intervalos y lectura) con corrección de nota,
afinación y tempo. Etapa 3a: el carril, para tocar una pieza con la música
corriendo. Etapa 3b: importar canciones de Guitar Pro, MusicXML, MIDI y
tablatura de texto. Etapa 3c: practicar la pieza con compases, bucles y tempo
ajustable. Etapa 3d: un **gemelo digital** —un guitarrista sintético que genera
audio de verdad y lo mete por donde entra el cable— para poder ver la sesión
correr sin tener la guitarra enchufada.

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

**Pausarse no es acusarte del silencio.** El aviso «no llega señal del cable» —en
la barra de diagnóstico y en el carril, que son dos mitades de lo mismo— sale
cuando el silencio puede ser una avería: la pasada en marcha y el cable sin
entregar una sola muestra, estés tocando o en pausa. **No** sale cuando el cable
ya entregó señal en esta pasada y luego te callas, que es lo que hace quien
descansa la mano entre dos vueltas de un bucle: ahí «sube el volumen de la
guitarra» sería falso, y un aviso falso justo cuando más se ve es un aviso que se
deja de leer. Tampoco sale con la pieza terminada. El carril se pausa igual en
todos los casos y sigue donde estaba en cuanto vuelves a tocar.

**El precio de esa regla, dicho en claro:** si el cable se rompe *a mitad* de la
pasada —el jack se afloja, el volumen de la guitarra se va a cero— el aviso **no**
sale, porque el cable ya había entregado señal y para el programa eres tú quien
ha dejado de tocar. Verás el carril pausado y ningún texto naranja. Es una
elección deliberada: silenciar un fallo poco frecuente que notas en cuanto miras
el cable, a cambio de no gritarte en falso cada vez que descansas la mano en un
bucle, que es lo que se hace en cada sesión de práctica. Si el carril se pausa y
no entiendes por qué, lo primero que hay que mirar es el jack.

**Hay cuenta atrás desde el primer compás, y no hay metrónomo salvo que lo
pidas.** El plan de fábrica trae **un compás de cuenta atrás** antes de la primera
entrada —y antes de cada vuelta del bucle—, así que la primera nota, que está
escrita en el instante cero de la pieza, no te cae encima al pulsar **Empezar**:
durante la cuenta el cabezal no se mueve y no se cobra ninguna nota. Con
`compases_de_cuenta_atras: 0` en el plan no hay cuenta, y entonces sí es
prácticamente imposible llegar *a tiempo* a la primera nota. Lo que no hay de
serie es nada que marque el pulso: el click es opcional (etapa 3c, más abajo) y
sin él el ritmo lo llevas tú con lo que ves caer.

**La ventana de ±80 ms.** Una pulsación cuenta como *a tiempo* si cae a menos de
80 ms de donde la nota está escrita; entre 80 ms y el límite de la ventana de
reclamo (más abajo) se marca *pronto* o *tarde*. **Ese
número está razonado, no medido tocando**: sale de que por debajo de unos 30 ms dos
ataques no se oyen separados, de que por encima de unos 100 ms el desfase ya se
oye como error, y de la latencia del cable (13,8 ms según la medición anotada en el código), pero nadie ha
sentado a un alumno con la guitarra a ver cuándo siente que llegó tarde. Si te
parece indulgente o severo, hay que ajustarlo: es la constante `VENTANA_A_TIEMPO_S`
de `nucleo/piezas/seguimiento.py`. Todo esto es al tempo escrito: con el tempo
ajustable de la etapa 3c las ventanas se estiran con él (al 50 %, ±160 ms).

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
  de 20 notas). Con una escala no hay una cifra única, y no porque sea difícil de
  medir: **depende entero de la FORMA del recorrido**, y la misma escala de do mayor
  de 120 notas da **del 27 % al 100 %** según cómo esté recorrida. Las cuatro formas
  medidas, que las reproduce `uv run python -m herramientas.medir_digitacion`:
  diente de sierra C3..C6 **27,1 %**, sube y baja **55,7 %**, diente de sierra en un
  rango más grave (C2..C5) **65,6 %**, una octava en bucle **100 %**. Aquí había un
  «98 % en una escala de do mayor de 120 notas» que no se podía comprobar: no decía
  qué escala y el script que lo produjo no estaba en el repositorio.
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

**El aviso es de la PISTA que eliges**, no de la canción. Lo que se importa es una
pista, así que es su afinación la que decide: un `.gp5` con la pista 1 en estándar y
la pista 2 en Drop C avisa al elegir la segunda y no al abrir la canción. Mientras no
has elegido ninguna, el aviso es el de la primera pista usable, que es la que se
importaría si no eliges otra.

> **El bajo está en el selector y el carril no lo acompaña todavía.** `bajo_4` y
> `bajo_5` son perfiles de fábrica, pero el carril se equivoca en casi cada nota
> con ellos, y está medido en esta etapa (no es una sospecha): la ventana de
> análisis de un bajo son 8192 muestras —**170,7 ms**— y con ella el margen de la
> racha estable del detector se queda en **cero**, así que el ataque se sella con
> la altura de la nota ANTERIOR; y esos mismos 170,7 ms empujan el retraso de la
> cadena por encima de los 250 ms que el detector admite para seguir hablando del
> mismo ataque, de modo que la pasada entera se desadjudica (**30 de 30** semillas
> sucias en la medición). El afinador sí funciona: lo que no funciona es seguir
> una pieza con el carril. Si tocas el bajo, afínalo y úsalo en el afinador, pero
> cuenta con que el carril no te va a marcar bien hasta que esto se arregle. Está
> declarado con todas las letras en `nucleo/ejercicios/pulsaciones.py`, y el
> gemelo digital —la herramienta con la que se comprobaría— solo sabe de guitarra
> estándar.

**El aviso funciona también con una afinación que no es de fábrica**, y a la
primera. De fábrica son estándar, Drop D y los dos bajos; una canción en Drop C no
está en esa lista, y es precisamente la que necesita que le digan a qué afinarse.
El perfil de una afinación rara se da de alta al **listar** las pistas, no solo al
importarlas, y **la clave que propone el listado la pone el lector que dio de alta
el perfil**, que es el mismo que va a leer la pieza: por eso es exactamente la que la
pieza va a traer, y afinarte a lo que te dicen basta para que el carril te acepte. El
selector del afinador no se llena por mirar canciones —publica las de fábrica más la
activa—, así que la afinación rara aparece en él cuando te afinas a ella, que es
cuando hace falta para dibujar bien el mástil.

Eso incluye el caso que lo rompía, medido de punta a punta: la misma canción en
Drop C como `.txt` (22 trastes) y como `.gp5` (24, los que declara el archivo) son
**dos perfiles distintos de la misma afinación**, y cada archivo propone el suyo.
Antes la clave se volvía a deducir comparando las notas de las cuerdas y se quedaba
con el primer perfil que encajara, así que el `.gp5` proponía el del `.txt`, el
listado decía que estabas bien afinado y el carril contestaba 400: desde la pantalla
no había salida, porque el perfil que la pieza traía no era elegible en ninguna
parte. Hoy cada archivo propone el suyo y, afinándote a lo que te dice, el carril
acepta los dos.

Dos bordes que quedan, porque la honestidad está en los bordes:

- **Dos perfiles de la misma afinación física piden afinarse por separado.** El de
  22 trastes y el de 24 tienen las mismas seis cuerdas, así que pasar del `.txt` al
  `.gp5` del ejemplo te pide un cambio de afinación que **en la guitarra no es
  ningún cambio**: es un clic y nada que tocar. Es ruido, no un callejón sin salida,
  y el aviso siempre lleva al perfil que el carril acepta.
- **Solo Guitar Pro y la tablatura de texto declaran su afinación.** MIDI y MusicXML
  no, así que con ellos `coincide` es siempre `null` y la pieza se lee en tu perfil
  activo, cuadre o no con lo que el autor tocaba.

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
  compás de más sigue ahí —arreglar el expansor es un defecto de lectura, no de
  práctica: se consideró para la etapa 3c y se descartó, y irá a su propia
  etapa—, pero **ya no es en silencio**: el lector lee las casillas (`repeatAlternative` de las cabeceras)
  y la pantalla lo avisa antes de empezar, con el ejemplo de lo que suena y de lo
  que debería sonar. Es el estándar de esta etapa: si se detecta, se avisa.
- **Las secciones se importan y, en el carril, se pueden estudiar.** Los
  marcadores de Guitar Pro, las marcas de ensayo de MusicXML y los marcadores de
  texto de MIDI entran en la pieza, y la pantalla del carril trae un selector
  **Elige una sección** que arma el bucle con el primer y el último compás de la
  que elijas (etapa 3c, spec §6). Lo que sigue sin usarlas es la vista escrita,
  que no dibuja sus nombres encima de la partitura. Y como `Seccion` no guarda
  dónde acaba, el último compás de una sección es el anterior al comienzo de la
  siguiente: si el archivo trae un marcador suelto a mitad de un pasaje, la
  sección se estira hasta el marcador siguiente.
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

### Practicar la pieza

La etapa 3c convierte el carril en un sitio donde **estudiar** una pieza, no solo
tocarla de principio a fin. Todo está en la pantalla del carril:

- **Compases a la vista**: una rejilla con todos los compases de la pieza y el
  del cabezal marcado, y se puede saltar a cualquiera con un clic.
- **Bucle por rango de compases**: se arrastra sobre la rejilla para marcar desde
  qué compás hasta cuál, y el tramo se repite. También se puede elegir el tramo
  por **secciones** de la canción, con el selector **Elige una sección**, cuando
  el archivo las trae.
- **Cuenta atrás de compases** antes de la primera entrada y al dar cada vuelta
  del bucle (uno por defecto; con 0 no hay). Durante la cuenta el cabezal no se
  mueve y no se cobra ninguna nota, y el click —si lo pides— se oye desde su
  primer pulso.
- **Tempo del 40 % al 100 % del escrito, en pasos del 5 %**, con un **click de
  metrónomo opcional**. No se pasa del 100 %: practicar más rápido que el
  original es otra cosa y no se construye aquí.
- **Informe por compases al terminar la pasada**: de cada compás, las notas
  acertadas, las que llegaron a tiempo, las **limpias** (acertadas y a tiempo a
  la vez, que son las que deciden el tempo automático) y el desfase medio dicho
  en palabras, más un botón para **machacar** los compases que más fallas.
- **Subida automática del tempo**, opcional: dos pasadas seguidas con el 90 % o
  más de notas limpias suben un paso; una sola por debajo del 70 % baja uno. Con
  bucle se aplica en el acto; sin bucle la pantalla lo **sugiere** y se aplica al
  empezar la pasada siguiente, para no arrancar sola un bucle que nadie pidió.

**Los cinco endpoints nuevos**, al lado de los de la etapa 3a:

- `POST /api/piezas/plan` — cambia tempo, bucle, click o tempo automático **sin
  reiniciar** la pasada. Es un **parche**: lo que no mandas conserva el valor del
  plan vigente, no el de fábrica (`{"factor_tempo": 0.7}` mueve solo el tempo).
  Sin pieza en marcha, 400.
- `POST /api/piezas/saltar` — `{compas}`: mueve el cabezal al principio de ese
  compás, que tiene que estar dentro del tramo que se estudia.
- `POST /api/piezas/pausa` — `{activa}`: la pausa del usuario, explícita y no un
  interruptor, y distinta de la pausa por falta de señal.
- `GET /api/piezas/informe` — lo tocado en esta pasada, compás a compás, y el
  historial de la pieza.
- `GET /api/piezas/pieza` — la pieza en marcha, para el navegador que se acaba de
  recargar (`/iniciar` la manda entera una sola vez).

`POST /api/piezas/iniciar` acepta además un `plan` opcional; sin él la pasada es
la de la etapa 3a.

**La ventana de acierto escala con el tempo.** Los ±80 ms de una nota son los del
tempo escrito: al 50 %, el compás dura el doble y la ventana también, así que son
±160 ms. Lo que se juzga es la colocación **dentro del compás**, con la misma
indulgencia a cualquier velocidad, no cuántos milisegundos de reloj te
equivocaste.

**El historial dura lo que dure el servidor.** Vive en memoria y **no se guarda en
disco**: al parar el servidor se pierde. Es una decisión tomada a propósito, no
una carencia por llenar. Además se guarda por **nombre** de pieza, así que dos
canciones distintas que se llamen igual comparten historial: es un empate
declarado, y el precio de equivocarse es un «fallas el compás 19» de otra
canción, no un dato perdido.

**Límites de esta etapa**, sin maquillar:

- **Una pieza con compás variable pinta mal las barras.** El modelo guarda un solo
  compás, así que con un 3/4 en medio las barras caen en el sitio equivocado desde
  el cambio hasta el final, y los números de compás pueden no coincidir con la
  partitura. Se avisa antes de empezar y en el informe; avisar no es dibujarlo
  bien.
- **En los compases con acordes solo se puede medir una nota de cada uno**, porque
  el detector de tono es monofónico. Por eso esos compases **no entran** en el
  ranking de fallos ni en la regla del tempo automático (saldrían fallados para
  siempre), y el informe lo dice en pantalla —«con acordes»— en vez de contarlos
  como fallados.
- **El click puede derivar del carril en una pasada larga**: corre en su propio
  hilo, con su propio reloj. Cada repetición del bucle lo rearranca, así que
  estudiando un bucle no se nota; tocando una pieza entera de seguido, sí puede.
- **En una pieza con ritmo aproximado** —las tablaturas de texto— el ritmo lo
  infirió el lector de la etapa 3b, así que medir el desfase contra él no es un
  diagnóstico de fiar. El informe lo avisa en la cabecera.
- **Marcar el rango arrastrando sobre la rejilla ya funciona con el dedo**
  (arreglado en la 3d). Estaba hecho solo para el ratón: en táctil el navegador le
  da al compás donde se pulsa la captura del puntero, así que el arrastre no
  pasaba de ese compás. Ahora la rejilla suelta esa captura y escucha
  `pointermove`, y cada compás lleva `touch-action: none` para que el gesto no se
  lo quede el scroll de la página. **Probado en jsdom, no en un teléfono de
  verdad**: lo que se puede afirmar es que el arrastre marca el rango y que el
  gesto no se va al scroll, no cómo se siente con el dedo.
- **En un compás cuyo denominador no es 4, el acento del click se redondea.** El
  metrónomo da un click por negra, así que acentúa cada número **entero** de
  pulsos: en 6/8 acierta (3 negras), y en 7/8 el compás son 3,5 negras y el acento
  cae cada 4. Es lo más cerca que se puede estar del compás con un click por
  negra; un click por corchea sería otro metrónomo.
- **Al acabar un tramo que no es la pieza entera no hay resumen nota a nota.** El
  resumen del final cuenta sobre la pieza completa, así que en un tramo parcial se
  dice solo que el tramo terminó y lo que se tocó se lee en el informe por
  compases, que sí sabe qué notas son del tramo.
- **La pieza no suena de fondo.** Solo se oye tu guitarra (y el click, si lo
  pides): que la pieza suene mientras la sigues es la **etapa 3e**.
- **Nada de esto se ha probado con la guitarra en las manos**: lo que hay son
  pruebas automáticas. Siguen pendientes de ensayo real si la cuenta atrás de un
  compás da tiempo a colocar la mano, si el click acentuado ayuda o estorba, si
  los pasos del 5 % son finos o bastos, y si «dos pasadas al 90 %» es la frontera
  correcta para subir.

La investigación disponible sugiere **alternar pasajes en vez de repetir uno en
bucle**, al revés que el *Riff Repeater* de Rocksmith: Carter y Grahn (2016,
*Frontiers in Psychology*) compararon práctica en bloque contra intercalada y
encontraron que gana la intercalada —y, de propina, que la mayoría de los
participantes creía lo contrario—. **Son diez sujetos**: es una señal, no una
ley. El bucle está porque es lo que se pidió; la alternancia no está construida.

## El gemelo digital: verse tocar sin tocar

```bash
uv run python -m herramientas.gemelo
```

Levanta el servidor de verdad, le enchufa un **guitarrista sintético** por donde
entra el audio del cable y toca la pieza de demostración solo. Sirve para lo que
las pruebas automáticas no contestan: **ver la sesión correr** —el carril, la
rejilla, el informe por compases— y opinar sobre si engancha, sin tener la
guitarra enchufada y sin tocar una nota. Nadie toca: todo lo que suena lo genera
el gemelo, y el dispositivo se anuncia como «(gemelo)» en el diagnóstico para
que ningún informe se pueda leer como una pasada real.

Abre `http://127.0.0.1:8420` en cuanto el escaparate imprima la dirección: la
pasada de la pieza de demostración dura unos 30 segundos y es lo que hay que
mirar. Si llegas tarde no pasa nada —el servidor sigue contestando mientras el
proceso viva—, pero la pasada solo se ve moverse una vez. La pieza por omisión
**se construye en código**: no hay ni habrá archivos de terceros en el
repositorio.

Opciones:

- `--perfil`: destreza del guitarrista sintético —`perfecto`, `principiante`,
  `intermedio`, `caos`—. Por omisión, `perfecto`.
- `--tempo FACTOR`: factor sobre el tempo escrito; `0.5` es tocarla al doble de
  lento.
- `--bucle PRIMERO-ULTIMO`: tramo de compases a estudiar; un solo número es ese
  compás (`--bucle 17`).
- `--repeticiones N`: vueltas al tramo. La pasada se da por acabada cuando el
  carril pasa de la última vuelta pedida.
- `--cuenta-atras COMPASES`: compases de cuenta atrás antes de cada vuelta.
- `--semilla N`: la semilla del azar del intérprete, para repetir una pasada.
- `--pieza RUTA`: toca un archivo tuyo (Guitar Pro, MIDI, MusicXML, tablatura de
  texto) en vez de la pieza de demostración. Se lee de donde esté; no se copia a
  ninguna parte. **Toca siempre la PISTA 1 y no se puede elegir otra**: si la
  primera pista de tu `.gp5` es la batería o el bajo, la demostración no tendrá
  ningún sentido (el servidor sí deja elegir pista; el escaparate todavía no).
  Y una canción de verdad trae acordes y notas repetidas, que el veredicto
  **excluye** y cuenta aparte: con un archivo tuyo el número de `excluidas` deja
  de ser cero y lo que el veredicto juzga es menos que lo que suena. La pieza de
  demostración no tiene ni acordes ni repetidas, así que ese camino solo está
  recorrido por las pruebas de unidad.
- `--puerto`: el puerto del servidor (por omisión 8420).
- `--salir-al-acabar`: terminar en cuanto la pasada acaba, que es la forma de
  usarlo desde un script. Sin esta bandera el proceso se queda en primer plano
  **con el servidor todavía contestando**, así que el navegador se puede abrir
  también después de que el resumen aparezca (Ctrl+C para salir).

**Los tres códigos de salida valen en los dos modos**: `0` si el veredicto sale
limpio, `1` si la cadena tiene hallazgos o la pasada no se completó, y `2` si la
demostración no llegó a montarse. Sin la bandera, el `Ctrl+C` con que cierras el
escaparate devuelve el código del veredicto que acabas de leer, no un error: antes
devolvía siempre `2` —«no llegó a montarse»— sobre una pasada completada y con su
veredicto impreso en pantalla.

### Que salga con código 1 y el perfil perfecto NO es un fallo

La sesión completa publica su peor ataque **entre 236 y 250 ms** después de que
la nota sonara, contra los **250 ms** que el detector admite para seguir
hablando del mismo ataque: **margen cero**. De ahí salen una o dos notas sin
emparejar en algunas pasadas, el veredicto sale «CON HALLAZGOS» y el proceso
devuelve 1 aunque el gemelo haya tocado las 48 notas escritas.

> **Y dos ejecuciones idénticas pueden dar veredictos distintos: el veredicto del
> escaparate NO es reproducible.** Con margen cero, lo que decide de qué lado cae
> cada nota no es la cadena sino el planificador de hilos del sistema. Medido en
> cuatro pasadas: tres planes distintos dieron peores desfases de **+249,7**,
> **+249,9** y **+250,0 ms** contra el techo de 250 —con 1, 3 y 2 notas sin
> emparejar—, y una cuarta pasada del **mismo plan** que la de +250,0 dio
> **+230,1 ms** y 3 notas. Así que si corres el escaparate dos veces y ves 1
> pérdida y luego 3, no ha cambiado nada: es este margen. Lo que el gemelo mide de
> forma estable es lo que la suite afirma con sus rangos; el número de una pasada
> suelta no es un dato del programa. (La semilla con `--semilla` fija el azar del
> INTÉRPRETE —lo que se toca sale igual byte a byte—, no el reparto de hilos del
> servidor, que es lo que varía.)

El escaparate **imprime un aviso** explicándolo junto al veredicto —solo con el
perfil perfecto, solo si la pasada fue la pieza **entera, una vez** y el gemelo
tocó todo lo escrito—, y aquí se dice también para que nadie lea ese 1 como «el
programa se equivocó de nota». La tolerancia **no** se afloja para que el código
sea cero: la demostración dice lo que mide. Con cualquier otro perfil los
hallazgos sí son del intérprete.

**Con `--bucle` ese aviso no sale, y es a propósito.** En un bucle, perder la
última nota de cada vuelta es un mecanismo propio del bucle con su propia causa
—está más abajo—, así que el borde del detector no lo explica y el aviso callaría
diciendo algo falso. Lo decía: con `--bucle 1-6 --repeticiones 2` sobre la pieza
de demostración afirmaba «el gemelo tocó las 48 notas de las 48 escritas» de una
pasada que tocó 24 dos veces.

### Los milisegundos de esta etapa son más benignos que el programa real

**El gemelo es unos 30 ms más benigno que la cadena de producción, y está
medido.** El hilo de análisis del servidor no corre a los 21 ms que declara su
constante, sino a unos 30 (mediana 29,91 ms sobre 133 cuadros seguidos): espera
con `Event.wait(0,021)` y en este equipo esa espera tarda 27 ms —macOS agrupa los
temporizadores—. No es el trabajo: analizar la ventana cuesta 0,15 ms. Es un
**defecto abierto**, no una decisión, y está nombrado en
`nucleo/gemelo/cadena.py`; el arreglo —esperar con plazo acumulado— obliga a
remedir la etapa entera. **Hoy no hay ninguna prueba que vigile esa cadencia.**
Así que cualquier milisegundo que salga de esta etapa **subestima la cadena real
en ese tanto**: la cadena a cadencia nominal publica los ataques entre 18 y 44 ms
antes que la sesión completa.

### El gemelo NO sustituye la prueba con el cable

Lo que el gemelo verifica es que la cadena ve lo que pasó y nada más. **Si el
sonido sintético no se parece bastante a una guitarra real, la cadena aprueba con
él y falla con el cable**, y eso el gemelo no lo puede saber. La lista de cosas
que **solo la guitarra en las manos** puede juzgar —si la cuenta atrás de un
compás da tiempo a colocar la mano, si el click acentuado ayuda o estorba, si los
pasos del 5 % son finos o bastos, si la digitación sale cómoda, si engancha—
**sigue entera y pendiente**. El diseño lo dice en sus no-objetivos:
[`docs/superpowers/specs/2026-11-02-gemelo-digital-design.md`](docs/superpowers/specs/2026-11-02-gemelo-digital-design.md).

### Dos cosas que el escaparate hacía mal y ya no

Las dos las encontró la verificación del README corriendo las órdenes como las
corre el usuario, y las dos están arregladas. Se cuentan aquí porque el
comportamiento de antes era desconcertante y alguien puede recordarlo.

- **El servidor sigue contestando mientras el proceso vive.** Antes se cerraba en
  el mismo instante en que se imprimía el veredicto (medido: a los 27,7 s de una
  pasada de la pieza de demostración), así que el navegador que se abriera después
  recibía «conexión rechazada» —justo lo natural de hacer, porque el resumen acaba
  de aparecer— y el mensaje «la pantalla se queda donde está para que puedas
  mirarla» prometía más de lo que hacía. Ahora el resumen y la espera ocurren con
  el servidor en pie: remedido con un sondeo cada segundo, el veredicto se imprime
  a los 7 s y el puerto sigue contestando a los 33 s, hasta que se corta el
  proceso. Con `--salir-al-acabar` se apaga limpio, como siempre.
- **`--repeticiones` mayor que 1 se da por completada.** Antes el escaparate
  esperaba a que el estado publicase `completado`, y un tramo en bucle no lo
  publica nunca: la pasada se cortaba al agotarse el margen, el resumen decía «SIN
  COMPLETAR» y el proceso devolvía 1 aunque todo hubiera ido bien. Ahora la pasada
  acaba cuando el carril pasa de la última vuelta pedida. Remedido con
  `--bucle 2-3 --repeticiones 2`: «pasada: completada», 16 notas tocadas (las 8 del
  tramo, dos veces).

  Lo que sigue siendo así, y es del bucle y no del escaparate: **la última nota de
  cada vuelta puede quedarse sin emparejar**. La cadena tarda unos 190 ms en
  publicar un ataque y al dar la vuelta el seguidor olvida el tramo, así que ese
  reporte llega cuando su nota ya no se puede reclamar. Está declarado en
  `nucleo/gemelo/veredicto.py` y medido en `tests/test_gemelo_bucle.py`.

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
- `nucleo/gemelo/` — el gemelo digital: la cuerda sintética, el intérprete, el
  cable falso y el veredicto. Python puro, como el resto del núcleo.
- `herramientas/` — utilidades de línea de comandos, incluido el escaparate del
  gemelo (`herramientas/gemelo.py`).
- `docs/superpowers/` — especificación y plan.

## Estado

Etapas 1, 2a, 3a, 3b, 3c y 3d completas, con la salvedad de que las cinco
comprobaciones de la 3b que necesitan la guitarra y archivos reales siguen
pendientes (están listadas en **Canciones**), y que **nada se ha probado con el
cable todavía**: el gemelo digital de la 3d deja ver la sesión correr, pero no
sustituye esa prueba (ver **El gemelo digital**). Las siguientes, según el
diseño:

2b. Ejercicios de acordes
3e. La pieza sonando de fondo mientras la sigues (la etapa siguiente a la 3d)
4. Grabación de sesiones, medición de progreso, entrenamiento de oído y efectos
