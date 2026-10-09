# proyecto_musica

Software libre para practicar guitarra en macOS con el cable Rocksmith Real Tone.
Etapa 1: afinador y monitor de notas en el mástil. Etapa 2a: ejercicios
monofónicos (escalas, arpegios, intervalos y lectura) con corrección de nota,
afinación y tempo. Etapa 3a: el carril, para tocar una pieza con la música
corriendo.

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
línea de abajo. Eliges la familia, opcionalmente un tempo, y pulsas **Empezar**.

**La diferencia con los ejercicios es de fondo: aquí la música no espera.** En un
ejercicio la nota pedida aguarda hasta que la aciertas; en el carril el reloj
corre solo. Una nota que no tocas pasa y se queda sin marca; una nota que
tocas queda marcada, acertada o no, y el resumen final dice de cada una si fue *a
tiempo*, *pronto* o *tarde* y por cuántos milisegundos. Si tocaste otra nota en
lugar de la pedida, se ve cuál: tanto en el resumen («Pedida A2, tocaste A#2»)
como en la vista escrita. Fallar no detiene nada: informa.

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
- **La digitación se elige por cercanía al traste anterior**, sin mirar lo que
  viene después. Basta para una escala en una posición; para una canción
  producirá saltos absurdos, porque la elección buena minimiza el movimiento de
  la mano a lo largo de toda la pieza.
- **El pentagrama es aproximado.** Está en clave de sol (las notas se escriben una
  octava por encima de lo que suenan, como se escribe la guitarra, pero la clave
  es un 𝄞 simple, sin el «8» que lo indica) y no lleva indicación de
  compás, ni corchetes en las corcheas, ni silencios, ni puntillos, y escribe los
  bemoles como sostenidos (un si bemol sale como la sostenido). Sirve para leer
  dónde tocar, no para editar partituras.
- **La tablatura cuantiza a semicorcheas**: una nota que empieza entre dos
  casillas se escribe en la más cercana.
- Las piezas que hay hoy son las que salen de los generadores de ejercicios
  (escalas, arpegios, intervalos y lectura). En el carril el intervalo no hace
  sonar la nota de referencia.

**Importar canciones** de Guitar Pro, MusicXML, MIDI y tablatura ASCII es la
**etapa siguiente**, y no se podía hacer sin este modelo de pieza: es el destino
al que esos formatos tienen que traducirse.

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
- `servidor/` — FastAPI: registro de módulos, configuración, diagnóstico y
  emisión por WebSocket. El registro de módulos es lo que permitirá añadir
  ejercicios y canciones en las etapas siguientes sin tocar el armazón.
- `interfaz/` — React + Vite.
- `herramientas/` — utilidades de línea de comandos.
- `docs/superpowers/` — especificación y plan.

## Estado

Etapas 1, 2a y 3a completas. Las siguientes, según el diseño:

2b. Ejercicios de acordes
3b. Importar canciones: Guitar Pro, MusicXML, MIDI y tablatura ASCII
3c. Practicar una pieza entera: compases, bucles y tempo ajustable
4. Grabación de sesiones, medición de progreso, entrenamiento de oído y efectos
