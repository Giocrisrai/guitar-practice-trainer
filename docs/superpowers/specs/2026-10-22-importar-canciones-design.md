# Etapa 3b — Importar canciones

**Fecha:** 2026-10-22
**Estado:** propuesta
**Etapas previas:** 1 (núcleo y afinador), 2a (ejercicios), 3a (el carril)

## 1. Qué se construye y por qué

La etapa 3a construyó el carril y el modelo `Pieza`, pero las piezas salen de los
ejercicios que el propio software genera. Esta etapa abre la puerta a **tus
canciones**: Guitar Pro, MusicXML, MIDI y tablatura ASCII entran, y salen `Pieza`.

Era la razón de ser del modelo. `Pieza` se diseñó deliberadamente aislado de
`nucleo/ejercicios/` para que una canción leída de un archivo no tuviera que
parecerse a una escala generada.

### Lo que no se construye aquí

- **Practicar por secciones, bucles, tempo ajustable y dificultad dinámica.** Es
  la etapa 3c. Aquí solo se **importan** los marcadores de sección, porque si se
  tiran al leer, la 3c no puede reconstruirlos.
- **Acompañamiento.** Se elige una pista y se practica esa; las demás no suenan.
- **Transportar una canción a tu afinación.** Decisión tomada: cuando la canción
  pide otra afinación, se te dice cuál y se te lleva al afinador con ese perfil.
- **Editar la tablatura importada.** Esto lee, no escribe.

## 2. Lo que se aprendió mirando las herramientas que ya existen

Se revisaron Rocksmith, Yousician y Fretello, y la literatura sobre práctica
musical. Tres hallazgos cambiaron el diseño:

1. **La unidad de práctica es la sección, no la canción.** Las tres herramientas
   giran alrededor de aislar un pasaje. Y las secciones **vienen en los
   archivos**: Guitar Pro trae marcadores, MusicXML marcas de ensayo, MIDI
   marcadores de texto. Importarlas cuesta un campo; reconstruirlas después es
   imposible.
2. **La dificultad dinámica de Rocksmith** —empezar con pocas notas por frase e ir
   añadiendo según aciertas— necesita saber qué notas son prescindibles. Se puede
   deducir del **peso métrico**: lo que cae en parte fuerte se queda. No hace falta
   guardar nada: se deduce de `inicio_pulsos` y el compás, que ya están en `Pieza`.
3. **La investigación contradice la repetición en bucle.** Carter y Grahn (2016,
   *Frontiers in Psychology*) compararon práctica en bloque —repetir el mismo
   pasaje, que es lo que hace un *Riff Repeater*— contra intercalada, y la
   intercalada gana; son diez sujetos, así que es una señal, no una ley. El
   hallazgo paralelo es más interesante: la mayoría de los participantes **creía**
   que el bloque funcionaba mejor. Se anota aquí para que la etapa 3c lo decida
   con el dato delante.

## 3. El modelo: un solo campo nuevo

```python
@dataclass(frozen=True)
class Seccion:
    """Un trozo con nombre: "Intro", "Estribillo", "Solo"."""
    nombre: str
    inicio_pulsos: float

@dataclass(frozen=True)
class Pieza:
    nombre: str
    perfil: str
    tempo: int
    compas: tuple[int, int]
    notas: tuple[NotaEnPieza, ...]
    secciones: tuple[Seccion, ...] = ()      # <-- lo único que crece
    ritmo_aproximado: bool = False           # <-- y esto, para el ASCII
```

`ritmo_aproximado` existe porque la tablatura ASCII no trae ritmo y hay que
inferirlo: la pantalla tiene que poder decirlo en vez de fingir precisión.

## 4. Los cuatro lectores

Cada uno en su archivo bajo `nucleo/piezas/`, **sin conocerse entre sí**, al lado
del `desde_ejercicio.py` que ya existe. Todos devuelven `Pieza`.

| Archivo | Librería | Trae | Falta |
|---|---|---|---|
| `desde_guitarpro.py` | PyGuitarPro 0.11 (LGPL-3) | cuerda, traste, ritmo, compases, secciones, pistas, afinación | nada |
| `desde_musicxml.py` | music21 10.5 (BSD-3) | ritmo, compases, marcas de ensayo; cuerda y traste **si el archivo los trae** | la digitación, cuando no viene |
| `desde_midi.py` | mido 1.3 (MIT) | ritmo exacto, marcadores | **la digitación entera** |
| `desde_ascii.py` | ninguna | cuerda y traste | **el ritmo entero** |

**Guitar Pro** es el formato bueno: `Note.string`, `Note.value` (el traste),
`Beat.start` en *ticks* y `Beat.duration` dan todo hecho. Devuelve además la lista
de pistas con su nombre, instrumento y afinación, porque un archivo casi nunca
trae una sola.

**MusicXML**: si el archivo trae `<string>` y `<fret>`, se respetan. Quien escribió
esa tablatura sabía más que nuestro algoritmo.

**MIDI** no dice dónde se toca nada: toda la digitación es nuestra.

**La tablatura ASCII** es la incómoda. Las seis líneas dan cuerda y traste; el
ritmo se infiere **de las columnas**, contando guiones entre números. Funciona en
tablaturas bien alineadas y falla en las que no, que son muchas. La pieza se marca
`ritmo_aproximado=True` y la pantalla lo dice.

## 5. La digitación: un camino de coste mínimo

`nucleo/piezas/digitacion.py`. El problema: cada nota vive en hasta seis sitios del
mástil y hay que elegir uno por nota, de modo que la mano se mueva lo menos
posible **en toda la pieza**, no solo respecto a la nota anterior.

Es un camino de coste mínimo sobre un grafo por capas: una capa por nota, un nodo
por posición alcanzable, y el coste de cada arista es lo que cuesta mover la mano.
Se resuelve por programación dinámica en `O(n·k²)` con `k ≤ 6`, así que una canción
de mil notas se resuelve en milisegundos. **Da el mínimo exacto, no una
aproximación** — a diferencia de la heurística de cercanía de la etapa 3a, que mira
una nota hacia atrás y ninguna hacia delante, y que esta etapa sustituye para las
piezas importadas.

Los pesos viven en un `dataclass`, no sueltos por el código:

```python
@dataclass(frozen=True)
class CosteDigitacion:
    por_traste: float = 1.0          # mover la mano un traste
    por_cuerda: float = 0.3          # cambiar de cuerda sin mover la mano
    al_aire: float = 0.0             # una cuerda al aire no cuesta nada
    estiramiento_maximo: int = 5     # más que esto es imposible, no caro
```

Son razonables y **no están medidos tocando**: se dice así en el código, como los
demás umbrales del proyecto. Ajustar una digitación incómoda es cambiar un número.

## 6. La afinación de la canción

Guitar Pro y MusicXML traen la afinación, y casi nunca será la tuya. Cuando no
coincide, el software **te dice a cuál afinarte y te lleva al afinador con ese
perfil puesto**, que es lo que hace un músico: afinar a la canción.

Eso obliga a un cambio real: hoy `PERFILES` es un diccionario fijo de cuatro, y una
canción puede pedir Drop C o siete cuerdas. El perfil pasa a poder **construirse
desde el archivo**, con el mismo `PerfilAfinacion` que ya existe, creado con las
cuerdas que diga la pieza. No sustituye al diccionario: lo complementa.

**Importar y poder tocar son dos cosas distintas, y conviene no confundirlas.** La
importación funciona siempre, afines como afines: la pieza se guarda con el perfil
de la canción. Quien rechaza es el carril, con la regla que la etapa 3a ya tiene —
una pieza en otra afinación que la activa se rechaza con 400, porque dibujar
trastes que tu instrumento no tiene es peor que no dibujar nada. Así que el camino
es: importas, el aviso te manda al afinador, afinas, y entonces el carril la
acepta. Nada de esto cambia la regla de la 3a; esta etapa solo hace que el aviso
sea accionable en vez de un callejón.

## 7. La biblioteca

Una carpeta `canciones/` en el proyecto, **ignorada por git**: las tablaturas son
material de terceros y no se distribuyen con el código. La subida desde el
navegador deja el archivo ahí mismo, de modo que las dos vías acaban en el mismo
sitio y hay un solo lector por debajo.

```
GET  /api/canciones              lista lo que hay en la carpeta
POST /api/canciones              sube un archivo a la carpeta
GET  /api/canciones/{id}/pistas  lee solo la cabecera: pistas y afinación
POST /api/canciones/{id}/importar  convierte la pista elegida en Pieza
```

El `{id}` es el **nombre del archivo**, nada más: la carpeta es la base de datos.
Se resuelve contra la carpeta y se rechaza cualquier nombre que salga de ella —un
`..` en la ruta es un intento de leer el disco, no una canción—. La subida acepta
hasta **10 MB**, que es holgado para cualquiera de los cuatro formatos y corta un
envío absurdo antes de escribirlo.

El listado y las pistas **no importan nada**: leer la cabecera es barato y
convertir no. Solo `importar` hace el trabajo.

## 8. Cuando el archivo viene roto

Y vienen rotos a menudo. **Se rechaza entero**, nombrando qué falló y dónde. Nunca
a medias: una canción importada a la mitad es peor que no tenerla, porque te hace
fallar notas que el archivo nunca tuvo.

| Situación | Qué pasa |
|---|---|
| Formato no reconocido | 400 diciendo qué formatos se leen |
| Archivo corrupto | 400 con el error de la librería, sin traceback |
| Pista sin notas | 400 nombrando la pista |
| Nota fuera del mástil del perfil | 400 nombrando la nota y el compás |
| `.gpx`/`.gp` que la librería no cubre | 400 diciendo que se exporte a `.gp5` |

## 9. Los límites, dichos de antemano

- **Los acordes se importan** —el modelo los admite desde la etapa 3a— pero el
  carril no los sigue, porque el detector de tono es monofónico. La pantalla lo
  avisa al abrir una pieza que los tenga, en vez de dejar que se descubra fallando.
- **Ligados, bends, armónicos y silencios expresivos se ignoran**: la nota entra con
  su altura y su duración, sin el adorno. No se fingen.
- **Las repeticiones y las casillas de primera y segunda vez se expanden** al
  importar, porque el carril es lineal y no sabe volver atrás.
- `.gpx` y `.gp` (Guitar Pro 6 y 7) tienen menos cobertura que `.gp5` en la
  librería.
- El ritmo del ASCII es aproximado y la pieza lo lleva marcado.

## 10. Cómo se prueba

**Sin un solo archivo con derechos de autor en el repositorio.** Las tres librerías
escriben además de leer: PyGuitarPro genera `.gp5`, music21 genera MusicXML y mido
genera MIDI. Las muestras se **fabrican** en las pruebas, pequeñas y a medida de
cada caso. El ASCII se escribe a mano, que es texto.

**La digitación se prueba por propiedades**, no por ejemplos:

1. ninguna nota cae fuera del mástil del perfil;
2. ningún salto supera `estiramiento_maximo`;
3. el coste total **nunca es peor** que el de la heurística de cercanía de la etapa
   3a, medido con la **misma** función de coste y sobre el **mismo** conjunto de
   posiciones por nota: si no, se estarían comparando dos cosas distintas.

La tercera es la que vigila de verdad: es un mínimo, así que esa desigualdad tiene
que cumplirse **siempre**, y si alguna vez falla es que el algoritmo está mal. Se
compara contra lo que ya existe, no contra un número elegido a dedo.

Ninguna prueba abre el dispositivo de audio real, como en las tres etapas
anteriores.

## 11. Riesgos

1. **El ritmo del ASCII.** Es el lector flojo y ya va declarado como aproximado. Si
   resulta inservible con tablaturas reales, la salida es honesta: decir que ese
   formato sirve para ver dónde tocar y no para seguir el carril a tempo.
2. **La cobertura de `.gpx`/`.gp`.** PyGuitarPro cubre `.gp5` mucho mejor. Acotado
   porque el fallo se detecta al leer y se dice.
3. **El peso de music21**: arrastra 23 paquetes. Si molesta, el MIDI ya está
   previsto con mido, que son dos; MusicXML seguiría necesitándolo.
4. **Los pesos de la digitación no están medidos tocando**, igual que la ventana de
   ±80 ms de la etapa 3a. Se cierra igual: tocando y ajustando.
5. **Canciones largas.** Mil notas en el carril a 60 fps es más de lo que la etapa
   3a probó. La geometría ya filtra por ventana visible, pero el filtro recorre el
   array entero en cada cuadro. Si se nota, se ordena por instante y se busca el
   primer visible, que es un cambio pequeño y localizado.
