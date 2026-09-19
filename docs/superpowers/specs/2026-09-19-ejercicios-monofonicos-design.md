# Diseño: motor de ejercicios monofónicos (etapa 2a)

Fecha: 2026-09-19
Estado: pendiente de revisión del usuario

## 1. Propósito

Añadir al software un motor de ejercicios que genere qué practicar, escuche lo
que tocas y te corrija. La etapa 1 entregó el afinador: sabe qué nota suena. Esta
etapa convierte ese dato en enseñanza.

El motor cubre cuatro familias de ejercicios —escalas, arpegios, intervalos y
lectura de notas en el mástil— todas **monofónicas**, porque el detector de tono
de la etapa 1 reconoce una nota a la vez y funciona bien. Los acordes son
polifonía, un problema distinto, y quedan para la etapa 2b con su propia spec.

## 2. Decisiones que gobiernan el diseño

Cinco decisiones tomadas con el usuario antes de diseñar. Todo lo demás se deriva
de ellas.

| Decisión | Consecuencia |
|---|---|
| El motor debe servir al modo **por turnos** y al de **tiempo real**, construyendo primero el de turnos | El evaluador registra el instante de cada ataque desde el principio, aunque el modo por turnos no lo exija |
| Las cuatro familias de ejercicios entran en esta etapa | Un modelo común de ejercicio y cuatro generadores, no cuatro subsistemas |
| El metrónomo y el entrenamiento de oído suenan con **tonos sintetizados en Python** | Subsistema de síntesis nuevo, con salida por CoreAudio |
| Un fallo **no avanza**: el ejercicio espera a que aciertes | Máquina de estados con reintentos contados, y un guardián contra el atasco |
| Una nota correcta pero desafinada **cuenta como acierto**, y la desviación se informa aparte | La afinación se mide siempre y no bloquea nunca |

La última decisión merece explicación porque no es obvia. Saber dónde está una
nota y hacerla sonar limpia son dos habilidades distintas. Si el ejercicio exige
las dos a la vez, una guitarra con la acción alta o una cuerda algo baja
convierten una práctica de digitación en una pelea con el instrumento. Se miden
las dos, se exige una.

## 3. Lo que ya existe y esta etapa reutiliza

De la etapa 1, sin modificar:

- `nucleo/musica.py`: conversión frecuencia ↔ nota, cents, posiciones en el mástil.
- `nucleo/afinaciones.py`: los cuatro perfiles y sus cuerdas.
- `nucleo/analisis/pipeline.py`: el `Analizador` que emite `ResultadoAnalisis` con
  `estado`, `nota`, `cents`, `confianza`, `nivel_db` y `posiciones`.
- `nucleo/captura.py`: la captura de audio y su buffer circular.
- `servidor/sesion.py`: la sesión que mantiene el análisis corriendo.
- `servidor/modulos.py`: el registro de módulos. El afinador es el primero; los
  ejercicios serán el segundo, y por eso la interfaz los descubre sin cambios.
- `nucleo/analisis/registro.py`: el registro de detectores intercambiables.

**Nada de la etapa 1 necesita reescribirse.** Las piezas que se añadieron
pensando en esto —los dos registros— cumplen aquí su función.

## 4. Arquitectura

```
nucleo/ejercicios/
├── modelo.py         # Ejercicio, NotaEsperada, ResultadoEjercicio
├── teoria.py         # escalas e intervalos como patrones sobre Z12
├── generadores/
│   ├── escalas.py
│   ├── arpegios.py
│   ├── intervalos.py
│   └── lectura.py
├── ataques.py        # deteccion de ataques a partir de la energia
└── evaluacion.py     # la maquina de estados que corrige
nucleo/sintesis.py    # tonos y metronomo, salida por CoreAudio
servidor/ejercicios.py  # endpoints y estado de la sesion de practica
interfaz/src/Ejercicios.tsx  # la pantalla
```

La regla de la etapa 1 se mantiene: **`nucleo/` no importa nada de `servidor/`
ni de `interfaz/`**.

### 4.1 `modelo.py` — el vocabulario común

```
NotaEsperada
    midi: int
    posiciones: list[Posicion]   # donde puede tocarse, de nucleo.musica
    pulsos: float                # duracion en pulsos de metronomo

Ejercicio
    clave: str
    nombre: str
    descripcion: str
    notas: tuple[NotaEsperada, ...]
    tempo: int                   # pulsos por minuto
    perfil: str                  # clave del perfil de afinacion
```

Las cuatro familias producen esta misma estructura. Esa es la razón de que el
evaluador y la pantalla se escriban una sola vez, y de que añadir una quinta
familia sea un archivo nuevo y ningún cambio.

`ResultadoEjercicio` recoge lo ocurrido: por cada nota, los intentos que costó,
la desviación en cents del acierto y el instante del ataque.

### 4.2 `teoria.py` — la aritmética musical

Una escala es un subconjunto de ℤ₁₂ y transportarla es sumar módulo 12:

```
MAYOR            = (0, 2, 4, 5, 7, 9, 11)
MENOR_NATURAL    = (0, 2, 3, 5, 7, 8, 10)
PENTATONICA_MAYOR = (0, 2, 4, 7, 9)
PENTATONICA_MENOR = (0, 3, 5, 7, 10)
BLUES            = (0, 3, 5, 6, 7, 10)
```

Generar "Sol mayor en la quinta posición" es transportar el patrón a la raíz,
expandirlo a los números MIDI del rango, e intersecar con las notas que el perfil
alcanza en esa zona del mástil. Aritmética pura, verificable exactamente.

Los acordes se declaran igual, como patrones de intervalos: mayor `(0, 4, 7)`,
menor `(0, 3, 7)`, séptima dominante `(0, 4, 7, 10)`, menor séptima
`(0, 3, 7, 10)`.

### 4.3 `ataques.py` — la pieza de mayor riesgo

El afinador solo necesita saber qué nota suena ahora. Un ejercicio necesita saber
**cuándo empieza una nota nueva**. Si tocas un Do y lo sostienes dos segundos, el
analizador emite unos sesenta resultados diciendo "Do", y eso es **una** nota. Si
tocas Do, Do, Do repetidos, son **tres**, y el analizador dice exactamente lo
mismo. La diferencia no está en la frecuencia: está en la energía.

Un ataque se marca cuando `nivel_db` sube más de un salto configurable sobre el
nivel reciente, seguido de un **periodo refractario** durante el cual no se marca
otro. Sin el refractario, el transitorio de la púa dispara dos o tres ataques por
pulsación.

| Parámetro | Valor inicial | Qué gobierna |
|---|---|---|
| Salto mínimo | 6,0 dB | Cuánto debe subir la energía para considerarse ataque |
| Periodo refractario | 50 ms | Tiempo muerto tras un ataque |
| Espera de estabilización | 60 ms | Cuánto se espera antes de leer la nota |

**Los tres valores son provisionales y se calibran con las grabaciones reales del
usuario.** Justo en el ataque la señal es caótica y la frecuencia poco fiable;
por eso se espera a que se estabilice antes de leer la nota.

El detector se registra en un registro de detectores de ataque, del mismo estilo
que el de detectores de tono, para poder sustituirlo sin tocar el evaluador.

### 4.4 `evaluacion.py` — la máquina de estados

Consume el mismo flujo de `ResultadoAnalisis` que alimenta al afinador.

```
esperando ──ataque + nota creible──▶ coincide con la esperada?
                                      │
                    si ──────────────┴────────── no
                    │                             │
            avanza a la siguiente          cuenta el intento
            (guarda cents e instante)      y sigue esperando la misma
```

Tres reglas que definen el comportamiento:

1. **Un ataque sin nota creíble no cuenta como fallo.** Cuenta como que no
   tocaste nada. Un roce accidental o el ruido de cambiar de postura no deben
   puntuar en contra.
2. **La afinación no bloquea.** Un acierto guarda su desviación en cents y
   avanza. El informe final la resume.
3. **Guardián contra el atasco.** Tras cinco intentos fallidos en la misma nota,
   el mástil resalta dónde está. No salta el ejercicio: ayuda. Esperar
   indefinidamente es correcto pedagógicamente y frustrante en la práctica.

El instante de cada ataque se registra **siempre**, aunque el modo por turnos no
evalúe el tempo. Eso da el informe de regularidad sin coste añadido y es
exactamente lo que el modo en tiempo real necesitará: activarlo será añadir una
regla, no reescribir el motor.

### 4.5 `sintesis.py` — que el software suene

Generación de ondas con numpy y salida por CoreAudio con `sounddevice`, la misma
librería que ya se usa para capturar.

- **Click de metrónomo**: un pulso corto con envolvente abrupta, acentuado en el
  primer tiempo del compás.
- **Notas de referencia** para el entrenamiento de oído: senoide con unos pocos
  armónicos y envolvente suave, para que no suene a pitido de test.

**Una ventaja gratuita del cable.** El sonido sale por los altavoces del Mac y el
cable Rocksmith solo capta la guitarra: el metrónomo **no contamina la
detección**. Con un micrófono habría que resolver la realimentación; aquí el
problema no existe.

### 4.6 La pantalla

Reutiliza el mástil de la etapa 1 con tres capas: la nota actual resaltada, las
ya acertadas en tenue, y la barra de progreso. Arriba el configurador del
ejercicio; al terminar, el informe.

El informe muestra: notas acertadas a la primera, notas que costaron varios
intentos, desviación media en cents y en qué notas te fuiste, y la regularidad
entre ataques.

## 5. Manejo de errores

| Situación | Cuándo se detecta | Qué muestra |
|---|---|---|
| El ejercicio pide una nota que el perfil no alcanza | Al **generar**, no al tocar | Se rechaza la configuración explicando qué nota y qué perfil |
| La señal desaparece a mitad de ejercicio | Tras 5 s sin señal | Pausa el ejercicio y reutiliza el aviso del afinador |
| La salida de audio falla | Al iniciar la síntesis | El ejercicio funciona sin metrónomo, avisando; no se aborta |

El tercero es deliberado: quedarse sin metrónomo degrada la experiencia, no la
impide. Abortar un ejercicio porque no hay salida de audio sería
desproporcionado.

## 6. Estrategia de pruebas

**El evaluador se prueba sin audio y sin hardware.** Consume `ResultadoAnalisis`,
que es un dato: se puede escribir la secuencia exacta que produciría alguien
tocando una escala —con sus fallos, sus silencios y sus notas dudosas— y
verificar el veredicto en milisegundos. Toda la lógica pedagógica queda cubierta
por pruebas deterministas.

- Secuencia perfecta → todas a la primera, sin fallos.
- Secuencia con una nota equivocada y luego la correcta → dos intentos en esa nota.
- Nota correcta desafinada 20 cents → acierto, con la desviación registrada.
- Ataque sin nota creíble → no cuenta como intento.
- Cinco fallos seguidos → se activa la ayuda del mástil.

**Los generadores se prueban exactamente**, por ser funciones puras: la escala de
Do mayor tiene esas siete clases de notas y no otras; un arpegio de La menor da
La, Do y Mi; ninguna posición cae fuera del mástil del perfil.

**El detector de ataques necesita señal real.** Se prueba con envolventes
sintéticas (ataque abrupto, nota sostenida, dos pulsaciones seguidas, decaimiento
lento) y **con las grabaciones de la guitarra del usuario**, que es donde se
calibran los tres parámetros de la sección 4.3.

## 7. Alcance

**Incluye:** el modelo de ejercicio, la teoría de escalas y acordes como
patrones, los cuatro generadores, la detección de ataques, el evaluador por
turnos, la síntesis de tonos y metrónomo, la pantalla de ejercicios con su
informe, y las pruebas de la sección 6.

**No incluye, y es deliberado:**

- **Acordes** (detección polifónica y ejercicios de cambios) — etapa 2b.
- **Modo en tiempo real** — el motor lo contempla y registra los instantes, pero
  la regla de evaluación por tempo no se activa aquí.
- **Guardar el progreso entre sesiones** — etapa 3. El informe se ve al terminar
  y no persiste.
- **Tablaturas y canciones** — etapa 4.

## 8. Riesgos conocidos

1. **La detección de ataques es la pieza incierta.** Si el salto de 6 dB resulta
   mal elegido para la guitarra del usuario, notas ligadas o tocadas con los dedos
   podrían no marcarse. Mitigación: parámetros configurables, detectores
   intercambiables, y calibración con grabaciones reales.
2. **Las grabaciones del usuario siguen sin existir.** Sin ellas, los tres
   parámetros se ajustan a ojo y las pruebas con señal real no pueden escribirse.
   Es la dependencia externa de esta etapa.
3. **La síntesis comparte el dispositivo de audio con la captura.** Abrir un
   stream de salida mientras hay uno de entrada es habitual en CoreAudio, pero no
   se ha probado en este equipo.
