# Etapa 4a — Historial de pasadas y medición de progreso

> **Escrito por Claude sin conversación de diseño previa.** El usuario pidió
> avanzar («prefiero que avances tú con todo esto y luego te daré feedback en
> mejoras») en un momento en que no podía conectarse a discutirlo. Así que
> **todas las decisiones de este documento son mías**, y las que podrían haber
> salido distintas están marcadas con **DECISIÓN MÍA** para que el feedback tenga
> dónde aterrizar. Ninguna está acordada.

---

## 0. La etapa 4 son cuatro proyectos, y este es uno

El README dice que lo siguiente es «grabación de sesiones, medición de progreso,
entrenamiento de oído y efectos». Eso no es una etapa: son cuatro cosas que no
comparten casi nada.

- **Historial y progreso** (este documento): el programa recuerda lo que tocaste
  y te lo puede contar.
- **Grabación de audio**: guardar el sonido de la pasada en un archivo para
  volver a oírlo. Comparte el nombre «grabación» con lo anterior y nada más: una
  es datos, la otra son megabytes de audio y una decisión de privacidad.
- **Entrenamiento de oído**: un ejercicio nuevo, con su propia pedagogía.
  Independiente de todo lo demás.
- **Efectos**: proceso de señal sobre el audio de entrada. Independiente, y
  sospechoso de ser un deseo y no una necesidad.

**DECISIÓN MÍA: se hace primero el historial**, por tres razones. Es el único de
los cuatro que *todo lo construido ya pide* —ocho etapas midiendo pasadas que se
tiran a la basura al cerrar la pestaña—. Es el único que contesta a la intención
original del usuario («me va indicando si voy bien, mal, si debo repetir»), que
sin memoria solo puede hablar del compás que acaba de pasar. Y es el que los
otros tres necesitarían: una grabación de audio sin una pasada a la que pertenecer
es un archivo huérfano.

---

## 1. Intención

**Hoy el programa no recuerda nada.** `InformeDePasada` se calcula, se sirve por
HTTP, se pinta y se pierde. Lo único que persiste en todo el repositorio es
`config_local.json`, y ahí solo hay el dispositivo y la afinación.

Eso tiene una consecuencia que no es de comodidad sino de pedagogía: **el programa
no puede decirte lo único que de verdad querrías saber**, que es si estás mejor
que la semana pasada. Puede decirte «el compás 19 lo tocas 40 ms tarde», que ya
es mucho más que «fallas el 19». No puede decirte «el 19 lo tocabas 90 ms tarde
hace diez días y ahora 40», que es la frase que hace volver a sentarse.

Y hay una segunda cosa, menos obvia y puede que más valiosa: **sin historial, el
programa no sabe qué deberías practicar hoy**. Con historial, lo sabe sin que
nadie se lo tenga que pedir, porque ya mide por compás.

### Lo que esto NO es

No es gamificación. No hay rachas, insignias, niveles ni puntos. **DECISIÓN
MÍA**, y la razón es que el usuario es profesor de matemáticas: lo que mueve a
alguien así es ver el número bajar, no una medalla. Si me equivoco en esto, es la
clase de error que conviene corregir pronto, porque contamina el resto del
diseño.

No es una nube. Los datos se quedan en el disco del usuario, en un archivo que
puede abrir, leer y borrar.

---

## 2. Objetivos, no objetivos, anti objetivos

### Objetivos

1. Cada pasada cerrada deja un registro en disco: qué pieza, qué tramo, a qué
   tempo, cuándo, y el informe por compás que ya se calcula.
2. El programa puede responder, por pieza y por compás: cómo va la cosa ahora,
   cómo iba antes, y si la diferencia es real o es ruido.
3. El programa puede proponer **qué practicar hoy**, derivado de lo medido y no
   de una heurística inventada.
4. El historial se puede leer sin el programa: un archivo de texto que se entiende
   abriéndolo.

### No objetivos

- Sincronización entre equipos, cuentas de usuario, compartir con nadie.
- Guardar el audio. Es el proyecto hermano, y tiene su propia decisión de
  privacidad que no quiero mezclar aquí.
- Guardar nota a nota. Ver §4.2: se guarda por compás, y hay una razón medida.
- Gráficas elaboradas. Una línea por compás y una por pieza es suficiente para
  ver una tendencia; lo demás es decoración hasta que el usuario pida otra cosa.

### Anti objetivos — lo que haría fracasar esto aunque funcionara

- **Que el historial mienta sobre el progreso.** Si el programa dice «vas
  mejorando» porque bajaste el tempo, es peor que no decir nada: el usuario
  tomaría decisiones de práctica sobre una medida corrupta. Ver §4.4.
- **Que escribir el registro ralentice la pasada.** El hilo de análisis corre a
  21 ms y acaba de costar un arreglo que llegue ahí (`Sesion._esperar_el_cuadro`).
  Si guardar pone a ese hilo —o al que sirve la instantánea cada 33 ms— a esperar
  un disco, esto rompe lo que arregló aquello. Ver §4.3: el repositorio ya decidió
  dónde puede bloquearse y dónde no.
- **Que el archivo crezca sin cota.** Una sesión de media hora en bucle son
  decenas de pasadas. A tres años eso es un archivo que nadie abre.
- **Que el usuario no pueda borrarlo.** Es un registro de sus fallos. Que exista
  sin poder quitarse es una razón legítima para no usar el programa.

---

## 3. Restricciones

Las de siempre en este repositorio, y se repiten porque son vinculantes:

- **Cero dependencias nuevas.** El historial va en JSON con `json` de la
  biblioteca estándar. No entra sqlite, no entra pandas.
- Comentarios y variables en español. Los `.py` de `nucleo/` **sin vocales
  acentuadas**; `servidor/` y `herramientas/` con acentos.
- numpy/scipy antes que implementaciones manuales. La mediana, la tendencia y el
  contraste de ruido de §4.4 son numpy.
- Pruebas con pytest. `pnpm` para la interfaz.
- **Ningún archivo con derechos de autor entra al repositorio.** El historial
  guarda el *nombre* de la pieza y el hash de su contenido, nunca la pieza.

Y una propia de esta etapa:

- **El hilo de análisis no escribe en disco.** Nunca, por nada.

---

## 4. Cómo funciona

### 4.1 Dónde vive el archivo

`historial.json` junto a `config_local.json`, en la raíz del proyecto, y
**en `.gitignore`**. Es del usuario, no del repositorio.

**DECISIÓN MÍA: un solo archivo, no uno por pieza.** Un archivo se abre, se lee
entero y se entiende; una carpeta con quince archivos obliga a saber cuál mirar.
Si algún día son demasiados registros, el recorte de §4.5 es la respuesta, no la
fragmentación.

### 4.2 Qué se guarda de cada pasada

Un registro por pasada **cerrada**. Una pasada que seguía abierta cuando se acabó
el audio no se anota, con el mismo criterio que `RegistroDeLaCadena.vueltas` ya
aplica y por la misma razón: nadie la cerró, e inventarle un cierre sería anotar
una vuelta que el conductor no anotó.

```json
{
  "instante": "2026-11-25T18:42:07",
  "pieza": {"nombre": "Cambios: Do mayor, Sol mayor", "huella": "a3f9c1d2"},
  "tramo": [1, 8],
  "factor_tempo": 1.0,
  "repeticiones": 4,
  "compases": [
    {"numero": 1, "medibles": 2, "escritas": 6, "acertadas": 6,
     "limpias": 2, "desfase_medio_ms": 29.0}
  ]
}
```

`huella` es un hash corto del contenido de la pieza (notas, tempo, compás): sirve
para saber que dos registros hablan de **la misma** pieza aunque el archivo se
haya renombrado, y para saber que ya no hablan de la misma si la pieza se editó.
Comparar progreso entre dos versiones distintas de una pieza es comparar cosas
distintas, y el hash es lo que lo impide.

**Por compás y no nota a nota, y esto está medido.** La pieza de rasgueos tiene
44 notas en 8 compases; una pasada de cuatro vueltas son 176 reportes de nota
contra 32 de compás. A nota se guardaría cinco veces más para contestar las
mismas preguntas, porque **todo lo que el programa diagnostica ya es por compás**:
`CompasDelInforme` existe precisamente porque «el 19 lo tocas 40 ms tarde» es
accionable y «fallas la nota 137» no lo es.

Se guardan los contadores **crudos** y no las proporciones. Una proporción es una
división que el lector puede hacer; un contador perdido no se recupera. Es el
mismo criterio que `InformeDePasada.repeticiones` ya aplica al exigir que el
denominador viaje con el numerador.

### 4.2.1 Un campo que este diseño olvidó, y lo descubrió construyéndolo

El ejemplo de arriba **no lleva `tiene_acordes`**, y hace falta. Lo escribo aquí
en vez de corregirlo arriba en silencio, porque el error es instructivo.

Parecía un detalle de *cómo se midió*, no un dato que comparar. Pero
`nucleo.piezas.estudio.proporcion_limpia` **excluye los compases con acordes** —su
propio docstring explica por qué— y devuelve `None` para una pieza entera de
acordes, que es «no se puede medir» y no «cero». Sin el campo, quien lea el
historial no puede aplicar esa regla.

Y lo que pasa entonces está medido. Un compás de acorde tiene **una** nota
medible —un rasgueo, un ataque—, así que la proporción limpia solo puede salir
0 % o 100 %. Al gemelo **principiante**, que fallaba una cuerda de cinco y
llegaba 650 ms tarde, la primera versión de la herramienta le dijo
**«100,0 % limpio»**.

Eso es exactamente el anti objetivo de §2: el historial mintiendo sobre el
progreso. Y la lección para el resto de la etapa es más amplia que el campo:
**en una pieza de acordes, la proporción limpia no es la medida de cabecera.** La
medida de progreso de §4.4 y la propuesta de tramo de §4.5 tienen que decir
*cuál* de las dos miran —el ritmo de lo medible, o cuántas cuerdas sonaron— y no
pueden colapsar las dos en un número, porque cada una calla lo que la otra dice.

### 4.3 Quién escribe, y cuándo

El conductor ya avisa del cierre de cada vuelta (`al_cambiar_repeticion`) y el
aviso **lleva dentro la foto del estado en que la vuelta se cerró**, así que no
hay que medir nada nuevo: solo anotar lo que ya existe.

**Y el sitio donde engancharlo ya está decidido por el repositorio, no por mí.**
`SesionCarril._observar` corre en el hilo de análisis, y ahí dentro hay un
comentario que dice exactamente esto:

> «Solo la primera mitad de la mirada: mover el reloj. Cerrar las vueltas se
> queda para `estado()`, porque el cierre acaba avisando al click y
> `Metronomo.detener()` hace `join(timeout=1.0)`: bloquear hasta un segundo aquí
> cegaría la detección de ataques.»

O sea que el cierre de vuelta **ya está deliberadamente fuera del hilo de
análisis**, por el mismo motivo que el anti objetivo de §2 nombra. El historial
engancha donde el click ya engancha y hereda esa garantía. Eso no es una elección
de este diseño: es una restricción que ya existe, y romperla desharía un arreglo
ajeno.

**La trampa, que no había visto hasta mirarlo.** `estado()` es la que sirve la
instantánea al navegador, **cada 33 ms**. Escribir un archivo ahí dentro no
cegaría la detección de ataques, pero daría tirones en la pantalla, que es el
mismo defecto en otro sitio. Así que el aviso del cierre no debe escribir: debe
**encolar** el registro y que lo escriba un hilo aparte. El repositorio ya tiene
ese patrón —`_renderizar` del fondo sale a un `threading.Thread` demonio por una
razón idéntica—, y el constructor debería seguirlo en vez de inventar otro.

Escritura **atómica**: a un archivo temporal y luego `Path.replace`. Si el
programa muere a mitad, el historial anterior sigue íntegro. Un historial medio
escrito es peor que ninguno, porque el lector no puede saber que está roto.

Si la escritura falla —disco lleno, permisos— **la pasada no falla**. Se registra
el error una vez y se sigue. La jerarquía es explícita: tocar la guitarra importa
más que anotarlo.

### 4.4 Cómo se mide el progreso sin mentir

Aquí está la única parte de este diseño que es difícil, y es donde se decide si
esto sirve o engaña.

**El problema: el tempo.** Si tocaste el compás 19 al 70 % y hoy lo tocas al
100 %, un desfase peor no es un empeoramiento: es que la tarea es más difícil.
Comparar los dos números sin más es exactamente la mentira que el anti objetivo
prohíbe.

**DECISIÓN MÍA: solo se comparan pasadas del mismo tramo al mismo factor de
tempo.** No se normaliza, no se corrige, no se estima. La razón: cualquier
corrección sería un modelo de cómo el error escala con el tempo, y **ese modelo
no existe medido** —ni aquí ni en la literatura que yo pueda citar con
honestidad—. Un modelo inventado convertiría el historial en una opinión. Si no
hay dos pasadas comparables, la respuesta correcta es «todavía no se puede decir»,
y el programa la dirá.

**El segundo problema: el ruido.** Dos pasadas del mismo compás al mismo tempo
dan números distintos aunque no hayas cambiado nada. Decir «mejoraste 6 ms»
cuando la dispersión normal son 20 ms es ruido disfrazado de señal.

La medida: por compás y por tempo, se toma la **mediana** de las últimas N
pasadas contra la mediana de las N anteriores, y la diferencia solo se nombra si
supera la dispersión de las propias pasadas. Mediana y no media por lo mismo que
el detector de ataques: una pasada atípica no debe mover la referencia.

**El tamaño de N y el umbral de dispersión quedan sin número en este documento, y
a propósito.** No tengo con qué fijarlos: harían falta varias sesiones reales del
usuario tocando la misma pieza al mismo tempo, y eso no existe todavía —ni puede
existir antes de que esto se construya—. El constructor los deja como constantes
con el razonamiento escrito y **el comentario tiene que decir que no están
calibrados**, igual que `VENTANA_A_TIEMPO_S` y `UMBRAL_PRESENCIA` ya lo dicen.
Fingir un número aquí sería el error que este repositorio no comete.

**El tercer problema, y es el que me preocupa más: el gemelo no puede validar
esto.** El gemelo digital toca con una destreza *fija*: un perfil PERFECTO toca
igual de bien en la pasada 1 y en la 40. No hay aprendizaje que medir, así que el
gemelo puede verificar que la aritmética no revienta y que una serie construida
a mano se lee bien, pero **no puede verificar que la medida detecta progreso
real**. Eso lo decide el usuario practicando semanas. Está en §6 y en el alcance.

### 4.5 Qué practicar hoy

Derivado, no inventado: los compases de la pieza ordenados por lo que peor va,
dentro del mismo factor de tempo, agrupados en tramos contiguos para que la
propuesta sea un tramo tocable y no una lista de compases sueltos.

**«Lo que peor va» son dos cosas y no se pueden sumar** (ver §4.2.1): el ritmo
de lo medible (`limpias / medibles`, sin los compases de acordes) y cuántas
cuerdas sonaron (`acertadas / escritas`, con ellos). Un compás de acorde con
todas las cuerdas mudas y el rasgueo a tiempo saldría perfecto por la primera y
pésimo por la segunda. **DECISIÓN MÍA: manda la segunda cuando el compás tiene
acordes, y la primera cuando no.** La razón es pedagógica: si una cuerda no
suena, el ritmo de ese compás no es todavía el problema.

**DECISIÓN MÍA: se proponen tramos, no compases.** Practicar el compás 19 solo no
es practicar música; practicar del 17 al 20 sí. Dónde cortar el tramo es del
constructor, y lo que el diseño exige es que el tramo propuesto sea uno que el
carril ya sepa estudiar (`PlanDePasada` lo acota por compases).

### 4.6 Recorte

**DECISIÓN MÍA: se guardan todas las pasadas de los últimos 90 días y, de lo más
viejo, una por pieza/tramo/tempo y día** —la mejor de ese día—. Así la tendencia
de un año sigue viéndose y el archivo no crece con las cuarenta vueltas que diste
un martes.

El número 90 es arbitrario y lo digo: es «un trimestre», que es el horizonte en
que a alguien le interesa haber mejorado. No está medido y no puede estarlo.

### 4.7 Qué se ve

Una pantalla con la lista de piezas y, por pieza, dos cosas: la tendencia de lo
limpio en el tiempo y el mapa de compases ordenado por lo que peor va, con el
tramo propuesto señalado.

**DECISIÓN MÍA, y es la que menos confianza me da**: pongo la tendencia *detrás*
del mapa de compases, no delante. La tendencia es la que da gusto mirar; el mapa
es el que te dice qué hacer en los próximos veinte minutos. Si el usuario abre
esto para sentirse bien y no para practicar, me he equivocado en el orden.

---

## 5. Manejo de errores

- **Historial inexistente**: no es un error. Es el primer día.
- **Historial corrupto o de una versión futura**: no se borra nunca. Se renombra
  a `historial.json.roto` y se empieza uno nuevo, avisando. Borrar el registro de
  los fallos de alguien porque el programa no lo entiende es inadmisible.
- **Pieza editada** (la huella cambió): los registros viejos se conservan y
  quedan fuera de la comparación. No se tiran: puede que el usuario deshaga la
  edición.
- **Escritura fallida**: se avisa una vez y la pasada sigue. Ver §4.3.

---

## 6. Estrategia de pruebas

Lo que **sí** se puede afirmar aquí:

- La aritmética de la tendencia y del contraste de ruido, con series construidas
  en código: una serie que mejora se lee como mejora, una plana como plana, y una
  diferencia por debajo de la dispersión **no** se nombra.
- Que dos tempos distintos nunca se comparan entre sí. Es el anti objetivo, y
  merece su prueba explícita.
- Escritura atómica: matar el proceso a mitad deja el historial anterior íntegro.
- Que **ni el hilo de análisis ni el que sirve la instantánea** escriben en disco.
  Con un doble que falle al abrir cualquier archivo, igual que
  `SalidaCapturada(fallar_al_abrir=True)` ya hace con el audio del fondo.
- El recorte: una serie larga construida en código se recorta a lo que §4.6 dice,
  conservando la mejor pasada de cada día viejo.
- Que un historial corrupto se renombra y no se pierde.
- Una pasada del gemelo deja su registro, y el registro dice lo que el informe
  decía.
- **Que un rasgueo con una cuerda muda no salga «100 % limpio».** Es el defecto
  de §4.2.1 convertido en candado: el gemelo principiante tiene que salir peor
  que el perfecto en la cifra que se enseña, o la medida no sirve.

Lo que **no** se puede afirmar aquí, y hay que escribirlo donde se vea:

- **Que la medida detecte progreso real.** El gemelo tiene destreza fija. Ver
  §4.4.
- Que N y el umbral de dispersión sean los correctos.
- Que el tramo propuesto sea el que un profesor propondría. El usuario *es*
  profesor: ese juicio es suyo y vale más que cualquier prueba.

---

## 7. Alcance

Dentro: el registro, su lectura, la medida de progreso, la propuesta de tramo, la
pantalla, el recorte, y el `herramientas/` que imprime el historial en la
terminal sin abrir el navegador.

Fuera: audio grabado, entrenamiento de oído, efectos, nube, cuentas, exportar a
otro formato.

---

## 8. Lo que queda al constructor

- Los nombres de los módulos. Lo natural sería `nucleo/historial/` para el modelo
  y la medida, y `servidor/historial.py` para los endpoints, siguiendo el reparto
  que el repositorio ya tiene.
- La función de hash de la huella.
- El mecanismo de la cola de escritura de §4.3, siguiendo el patrón de
  `_renderizar`.
- Dónde cortar los tramos contiguos de §4.5.
- Los valores iniciales de N y del umbral, **con el comentario diciendo que no
  están calibrados** y qué haría falta para calibrarlos.
- El formato exacto de la pantalla.

---

## 9. Lo que hace falta del usuario, y no puede darlo nadie más

1. **Decir si esto es lo que quería.** Es la pregunta de verdad: todo este
   documento es mi lectura de «me va indicando si voy bien, mal, si debo
   repetir», y esa lectura puede estar equivocada de raíz.
2. Decir si acierto en que no quiere gamificación (§1).
3. Decir si el mapa de compases va delante de la tendencia o al revés (§4.7).
4. Practicar varias semanas la misma pieza al mismo tempo. Es lo único que puede
   calibrar N y el umbral, y lo único que puede decir si la medida detecta
   progreso o solo ruido.
