# Registro de ejecucion — etapa 3b (importar canciones)

Copia del cuaderno con el que se ejecuto
`docs/superpowers/plans/2026-10-22-importar-canciones.md`: cada tarea con sus commits y
**todas las decisiones** que hubo que tomar por el camino, cada una con lo que cuesta si
esta equivocada. Son 34. Varias explican por que el codigo es como es, y **nueve son
rectificaciones de defectos de mis propios briefs**, no del trabajo de los
implementadores.

Dos cosas que este registro guarda y que conviene leer antes de la etapa 3c:

- **La trampa del empate.** Aparecieron **diez** pruebas que no podian fallar, porque
  elegian un caso donde lo verificado coincidia con lo que el codigo haria igualmente.
  Varias salian de mis briefs. La novena la cazo el propio implementador antes de
  entregar; la decima la cazo la re-revision en el ultimo commit. El antidoto que acabo
  funcionando: no «escribe una prueba», sino «rompe el codigo y di cuantas cayeron».
- **Las cifras no contadas.** Un informe trajo tres mal, el README llevaba una que no
  era reproducible, y dos veces la cifra equivocada fue mia. De ahi la regla de la
  tarea 11: cada afirmacion con el comando que la produce, y lo que no se mide se
  escribe «no medido».

Spec: docs/superpowers/specs/2026-10-22-importar-canciones-design.md
Rama: etapa-3b-canciones, base main (8d4b53a).

# SDD ledger — plan: docs/superpowers/plans/2026-10-22-importar-canciones.md

Spec: docs/superpowers/specs/2026-10-22-importar-canciones-design.md (legible)
Rama: etapa-3b-canciones, base main (2ae14ff).

Ruling (entorno): rama en vez de worktree — el sandbox solo concede escritura sobre este directorio y su .git. Coste si me equivoco: el trabajo no queda aislado en un directorio aparte, pero si en una rama.

## Escaneo previo del plan

### Pares de tareas que comparten archivo o interfaz

| Produce | Consume | Qué produce vs. qué consume | Hallazgo |
|---|---|---|---|
| T1 `Seccion`, `Pieza.secciones/ritmo_aproximado/tempo_variable` | T4, T5, T6, T7 | los cuatro lectores construyen `Pieza` con esos campos | limpio |
| T2 `digitar`, `CosteDigitacion`, `coste_total` | T5, T6, T7 | T5 y T6 llaman `digitar(midis, perfil)`; T7 no la necesita (el ASCII ya trae traste) | limpio |
| T2 `coste_total` | T2 (su propia prueba) | compara contra `elegir_posicion` de `desde_ejercicio.py`, que existe desde la etapa 3a | limpio |
| T3 `perfil_desde_midis`, `clave_de_perfil` | T4, T7, T9 | T4 desde `Track.strings`, T7 desde el número de líneas, T9 para el aviso | limpio |
| T4 crea `lectores.py` con `PistaDisponible` | T5, T6, T7 lo importan; T8 le añade el registro | tras la corrección del auto-repaso, nadie lo mueve | limpio |
| T4..T7 lectores | T8 registro | T8 despacha por extensión | limpio |
| T7 `pieza_desde_ascii(texto, ...)` | T8 `importar(ruta, ...)` | firmas distintas: texto frente a ruta | **resuelto en el plan**: el registro lee el archivo y pasa el contenido, dicho explícitamente en T8 |
| T8 `pistas_de_archivo`, `importar`, `FORMATOS` | T9 servidor | T9 los llama tal cual | limpio |
| T9 endpoints | T10 interfaz | las cuatro rutas coinciden en los dos lados | limpio |
| T9 `perfil_activo`/`coincide` | T10 aviso de afinación | el servidor decide, la interfaz pinta | limpio |
| T1 `Pieza.a_dict()` | T10 `tiposCancion.ts` | claves nuevas: secciones, ritmo_aproximado, tempo_variable | limpio |

### Coherencia interna de cada tarea

| Tarea | Las pruebas que pide vs. el código que pide | Hallazgo |
|---|---|---|
| T1 | 6 pruebas contra la API declarada | limpio |
| T2 | 9 pruebas; una compara contra `elegir_posicion`, que existe | limpio |
| T3 | 7 pruebas; la última verifica que el perfil a medida sirve para digitar | limpio |
| T4 | 12 pruebas; las muestras se fabrican con PyGuitarPro | limpio |
| T5 | 8 pruebas; las muestras se fabrican con mido | limpio |
| T6 | 9 pruebas; las muestras se fabrican con music21 | limpio |
| T7 | 11 pruebas; el ASCII se escribe a mano | limpio |
| T8 | 4 pruebas; una usa monkeypatch sobre `_LECTORES`, privado | ver ruling |
| T9 | 10 pruebas contra el cliente HTTP | limpio |
| T10 | 6 pruebas de interfaz | limpio |
| T11 | documentación | limpio |

Ruling: la prueba de T8 que hace `monkeypatch.setitem(_LECTORES, ...)` toca un nombre privado, cosa que el rubro de revision suele marcar. La mantengo: lo que comprueba —que el registro DESPACHA al lector correcto— no se puede observar desde fuera sin fabricar los cuatro formatos, que es justo lo que las otras tareas ya prueban. Coste si me equivoco: una prueba acoplada al nombre del diccionario interno.

### Contradicciones con las restricciones globales

Ninguna. Verificado: ninguna tarea pide pip ni npm, ni nombres en ingles, ni que `nucleo/` importe de `servidor/`, ni que `nucleo/piezas/modelo.py` importe de `nucleo/ejercicios/`, ni que una prueba abra el audio real, ni que entre un archivo con derechos de autor.

### Contradicciones con la especificacion

Ninguna. Las tres correcciones del auto-repaso (el tipo compartido, la costura texto/ruta y las repeticiones de MusicXML) ya estan en el plan.

Task 1: implementada (70ff768, 492 passed / 30 skipped). Revision despachada. El "cambio ajeno en modelo.py" que informo el implementador era el aviso del harness, no una edicion: verificado con git log y git status, el commit toca solo los dos archivos esperados.
Task 1: revision aprobada, sin Critical ni Important. 3 Minor. El revisor probo seccion_en en seis casos propios (limite, antes de la primera, una sola, pasado el final, negativos, empate) y los seis salen defendibles.
Task 1: minor (deferred): un inicio_pulsos NaN pasa las validaciones (nan < 0 es falso). Coherente con las notas, que tampoco lo validan. Un lector de archivo corrupto podria producirlo.
Task 1: minor (deferred): dos secciones en el mismo instante se aceptan y la primera nunca se devuelve en seccion_en. Inocuo y determinista, sin prueba.
Task 1: minor (deferred): a_dict no tiene prueba del caso por defecto (secciones vacias, banderas en False), que es justo lo que vera la interfaz con cualquier ejercicio.
Task 1: no verificable desde el diff, RESUELTO POR MI: (a) los tipos TypeScript de la T10 se escribiran contra a_dict, no es un hueco; (b) la interfaz actual tolera claves de mas, porque TypeScript es estructural y en ejecucion se ignoran; (c) que un importador emita NaN o secciones duplicadas se lleva como aviso a los despachos de T4 a T7.
Task 1: complete (commits 8d4b53a..70ff768, review clean)
Task 2: implementada (a1a4f73, 501 passed / 30 skipped). DONE_WITH_CONCERNS con un defecto DE MI PLAN, no del implementador.
Ruling: adopto el modelo del ANCLA que el implementador propone, y autorizo cambiar la interfaz que mi brief fijaba (un nodo por posicion, O(n*k^2), coste_total sin perfil). Mi modelo llamaba "imposible" a lo que es un desplazamiento de la mano: verificado, F2 (midi 41) solo vive en el traste 1 de la sexta y Si4 (midi 71) no baja del traste 7, asi que con estiramiento_maximo=5 no habia arista entre las dos — y ese salto lo toca cualquiera moviendo la mano. El efecto medido por el implementador: 28 parejas de midi sin arista legal, presentes en 11 de los 50 ensayos de la prueba de la desigualdad, que ahi compara inf <= inf y por tanto no vigila nada. Con el ancla en el estado siempre hay arista y desaparecen el inf y la minimizacion lexicografica. Coste si me equivoco: mas estado y una firma distinta en coste_total, que solo usan las pruebas de esta tarea.
Task 2: fix round 1/5 despachado (modelo del ancla, repetir la verificacion exhaustiva, medir cuantos de los 50 ensayos vigilan de verdad, y prueba del caso F2 -> Si4).
Task 2: fix round 1/5 (ADDRESSED; commits a1a4f73..477d1c8; 502 passed / 30 skipped). El re-revisor monto su PROPIO oraculo sin programacion dinamica: 260 casos, 0 discrepancias, incluidos pesos degenerados que el implementador no probo. Mas tres identidades extra. Conto los 50 ensayos: 50 estrictos, 0 empates, 0 vacuos (antes 34/2/14). Mil notas en 34 ms; la digitacion mueve la mano un 39 % menos que la heuristica.
Task 2: el re-revisor confirmo ademas que el recorte de anclas a los extremos [f - est, f] es seguro (240 instancias, exceso maximo 0,0), asi que la rejilla completa es claridad y no necesidad.
Task 2: minor (deferred): con el ancla en el estado, estiramiento_maximo se comporta como una banda de movimiento gratis — el coste baja monotonamente al crecerlo y con est >= trastes todo el movimiento sale gratis. Es consecuencia del modelo correcto, no un error, y el docstring lo dice bien.
Task 2: minor (deferred): por_cuerda se cobra plano y no proporcional, asi que cruzar cinco cuerdas cuesta igual que cruzar una. Medido: casi dobla los cruces largos frente al proporcional. Esta como el brief lo fijaba; el cambio es una linea y hay que decidirlo tocando.
Task 2: minor (deferred): el docstring de test_mil_notas_se_digitan_en_un_pestaneo dice O(n*k^2) cuando el modulo ya documenta O(n*k^2*T^2).
Task 2: minor (deferred), PREEXISTENTE: ruff format --check querria reformatear 16 archivos del repo. No lo introduce esta rama.
Task 2: complete (commits 70ff768..477d1c8, review clean)
Task 3: implementada (c591657, 509 passed / 30 skipped). Revision despachada.
Task 3: revision aprobada, sin Critical ni Important. 6 Minor. El revisor verifico a mano el orden de las cuerdas contra los cuatro perfiles y aguas abajo (posiciones_en_mastil, digitar, tamano_ventana) con siete cuerdas, bajo de 4 y Drop C: correcto. Y probo la tolerancia de clave_de_perfil en diez casos: no hay falso positivo realista, porque dos afinaciones con midis enteros difieren al menos 100 cents.
Task 3: minor (deferred) PERO LOAD-BEARING: la prueba que yo mismo senale como la que importa (test_el_perfil_a_medida_sirve_para_digitar) solo comprueba len(...) == 3, que sale igual con las cuerdas invertidas. El codigo es correcto —el revisor lo verifico a mano— pero el orden de las cuerdas queda sin proteccion, y de el dependen T4, T6 y T7. Lo llevo como aviso a esos despachos y a la revision final.
Task 3: minor (deferred): clave_de_perfil compara solo frecuencias y descarta trastes, asi que una guitarra de 12 trastes en afinacion estandar devuelve "guitarra_estandar", que tiene 22. Quien use la clave para recuperar el perfil conocido pierde esos trastes. Decision razonable, sin documentar.
Task 3: minor (deferred): perfil_desde_midis no valida las notas (un midi negativo da "G-2" a 6 Hz; un float rompe con un TypeError confuso).
Task 3: minor (deferred): el import de PerfilAfinacion en nucleo/musica.py es solo para una anotacion de tipo y crea el ciclo que obliga al import diferido. Ponerlo bajo `if TYPE_CHECKING:` lo cerraria.
Task 3: complete (commits 477d1c8..c591657, review clean)
Task 4: implementada (12dfb3f, 7f0ec17; 538 passed / 30 skipped). DONE_WITH_CONCERNS con seis preocupaciones.
Ruling: MI AVISO SOBRE EL ORDEN DE LAS CUERDAS ESTABA INVERTIDO. Track.strings de PyGuitarPro va de la mas AGUDA a la mas grave (la numero 1 primero): lo documenta gp5.readTrack y lo confirma la Song() por defecto. El implementador le da la vuelta antes de perfil_desde_midis y lo fija con una afinacion asimetrica, que es justo lo que pedi. Coste si me equivoco: ninguno, el error era mio y esta corregido con prueba.
Ruling: acepto registrar_perfil y la separacion PERFILES_DE_FABRICA / registro vivo, que el brief no preveia. Pieza.perfil es una CLAVE de PERFILES, asi que una cancion en Drop C no se podia importar en absoluto. La alternativa —que Pieza lleve el objeto PerfilAfinacion— toca toda la pila de la etapa 3a. Coste si me equivoco: un registro global mutable, con el riesgo de contaminacion entre pruebas que eso trae; el implementador ya demostro que sin la separacion se rompia una prueba de la Tarea 3 segun el orden de ejecucion.
Ruling: la preocupacion 3 —servidor/app.py publica PERFILES entero, asi que el selector del afinador crecera con cada cancion rara importada— se resuelve en la Tarea 9 publicando PERFILES_DE_FABRICA. Lo llevo a ese despacho. Coste si me equivoco: el selector del afinador se llena de afinaciones de canciones.
Task 4: revision NO aprobada. 3 Critical, 2 Important, 7 Minor. Verifico ejecutando las cuatro trampas del formato, el offset de 960 sin desplazamiento acumulado, y el perfil asimetrico nota a nota: todo correcto.
C1: repeatClose interpretado al reves. El revisor lo zanjo leyendo la libreria (gp5 resta 1 al leer y suma 1 al escribir; gp3/gp4 no; RepeatGroup exige > 0 con defecto -1), asi que en memoria son PASADAS ADICIONALES y el total es repeatClose + 1. Medido: un |: :| corriente se importa SIN REPETIR y la pieza dura la mitad de lo que suena.
C2: la prueba de las repeticiones no puede detectar C1, porque el oraculo y la entrada comparten la misma suposicion: con_repeticion fija el valor en memoria, la libreria suma al escribir y resta al leer, asi que la ida y vuelta es estable con cualquier convencion.
C3: la suite no pasa en otro orden. registrar_perfil usa setdefault y gana el primero que llega; hoy el alfabeto ordena los archivos a favor. Falta una fixture que restaure PERFILES.
Ruling: I1 se arregla ahora con compas_variable en el modelo. Mi informe y el del implementador daban por inocuo el cambio de compas porque las notas no se descolocan, y es verdad; lo que se descoloca es la REJILLA de vistaEscrita.ts, que trocea con un compas constante y pone las notas en el compas equivocado para el resto de la cancion. Anadirlo ahora es gratis; despues obliga a tocar el modelo con la etapa cerrada. Coste si me equivoco: un campo mas que hoy nadie consume, igual que tempo_variable.
Task 4: fix round 1/5 despachado (C1 repeticiones, C2 su prueba, C3 contaminacion entre pruebas, I1 compas_variable, I2 el nombre segun quien importo antes, mas cuatro menores).
Task 4: fix round 1/5 (3 Critical + 2 Important + 3 de 4 Minor addressed; commits 7f0ec17..7f9f4fd; 546 passed / 30 skipped). El re-revisor fabrico sus PROPIAS muestras para no heredar la suposicion: dos archivos que solo difieren en el cierre difieren en un byte, que vale repeatClose+1 en gp5 y repeatClose en gp3/gp4. La misma musica en los tres formatos da a_dict() identico. Suite verde en alfabetico, inverso y 8 ordenes aleatorios.
Task 4: minor (deferred) NOT ADDRESSED: test_una_pista_sin_notas_se_lista_pero_no_se_puede_usar sigue con "is not None" y no distingue entre los tres motivos.
Task 4: minor (deferred): el informe sobreafirma que sin la fixture de conftest la suite falla segun el orden. El re-revisor lo probo con autouse=False en alfabetico, inverso y 8 semillas: sigue pasando. El arreglo real fue derivar el nombre dentro de registrar_perfil; la fixture es higiene preventiva. Hay que corregir la frase para que nadie la borre creyendo que no hace nada ni la mantenga creyendo que arreglo algo.
Task 4: minor (deferred): un docstring cita un nombre de prueba obsoleto, y _veces_que_se_toca daria TypeError con una Song en memoria (versionTuple None), inalcanzable por la API publica.
Task 4: PARA LA TAREA QUE CABLEE LA IMPORTACION (8 o 10), confirmado inalcanzable hoy porque nada fuera del modulo llama al lector: (a) servidor/app.py:63 publica PERFILES entero en el selector del afinador y crecera con cada cancion importada; (b) las casillas de primera y segunda vez producen UN COMPAS DE MAS en silencio —medido: trastes [0,1,0,1,2] donde lo correcto es [0,1,0,2]—, asi que merecen una bandera del tipo repeticiones_aproximadas.
Task 4: minor (deferred), DEUDA PREEXISTENTE: interfaz/src/tiposPieza.ts dice ser espejo exacto de a_dict() y le faltan ya cuatro campos (secciones, ritmo_aproximado, tempo_variable, compas_variable).
Task 4: complete (commits c591657..7f9f4fd, review clean)
Task 5: implementada (f00d5ce, 561 passed / 30 skipped, verde tambien en orden inverso). DONE_WITH_CONCERNS con tres desviaciones, las tres por defectos de mi brief.
Ruling: acepto la base 1 para el numero de pista. Mi brief llamaba pieza_desde_midi(ruta, 0) mientras PistaDisponible.numero y el lector de Guitar Pro cuentan desde 1; con base 0 los dos lectores dejarian de comportarse igual y el registro de la Tarea 8 tendria que saber cual es cual. Coste si me equivoco: una llamada distinta en las pruebas del brief.
Ruling: acepto que reescribiera el ayudante midi_de. El mio generaba un delta NEGATIVO cuando dos notas empiezan a la vez, asi que la prueba del acorde fallaba al fabricar el archivo, no al leerlo. Defecto de mi brief. Coste si me equivoco: ninguno.
Ruling: acepto mover FAMILIAS_GM de desde_guitarpro.py a lectores.py. Mi propia regla dice que los lectores no se conocen entre si, y tenerla en uno obligaba al otro a importarlo. Coste si me equivoco: un sitio mas donde mirar para una tabla de instrumentos.
Task 5: revision aprobada con 2 Important y 6 Minor. Verifico ejecutando los cinco puntos: velocity=0 cierra bien, 400 notas sin desplazamiento, varias pistas con relojes independientes, el mensaje nombra la nota sin traceback, y las dos banderas se comportan como en Guitar Pro.
I1: ninguna prueba vigila que la digitacion se pida DE UNA VEZ para toda la pista. El revisor lo mostro mutando a nota a nota: las 15 pruebas siguen pasando, y el coste pasa de 50,3 a 82,5. El codigo esta bien; la propiedad no tiene red.
Ruling: pido ademas arreglar el acorde, que el revisor clasifico como Minor y yo subo de categoria. Tres notas simultaneas salen como 6/0, 5/0 y 5/4: las dos ultimas en la misma cuerda a la vez, que es fisicamente imposible. Que el carril no siga acordes es una limitacion declarada; dibujar una digitacion intocable es una respuesta equivocada, y alguien la vera en la tablatura. Doy a elegir entre evitar la colision de cuerda o marcar la pieza para que la pantalla avise, con la condicion de que si elige lo segundo lo declare como limitacion y no como solucion. Coste si me equivoco: trabajo de mas en una tarea que ya estaba aprobada.
Task 5: fix round 1/5 despachado (I1 la prueba que falta, I2 pruebas de delta debiles, mas el acorde).
Task 5: fix round 1/5 (3 addressed; commits f00d5ce..48668c8; 567 passed / 30 skipped, verde en orden inverso). Verificado por mutacion: la prueba del minimo global muere al pasar a nota a nota; la pieza de 400 notas atrapa dos desplazamientos sutiles que ninguna otra prueba ve; las tres de acordes mueren sin la reasignacion. Confirmado que (40,45,49) es imposible en guitarra.
Ruling: la limitacion nueva del arreglo —cuerdas distintas NO implica acorde tocable, con aperturas medidas de hasta 12 trastes— se DECLARA, no se arregla. Meter la apertura en el coste seria entrar en la voz del acorde, y esta etapa declara que los acordes se importan pero no se siguen. El estandar del proyecto es decir lo que no se cubre en vez de disimularlo. Coste si me equivoco: la tablatura puede dibujar un acorde que nadie puede tocar, dicho en el docstring y en el informe.
Task 5: fix round 2/5 despachado (declarar la limitacion con el ejemplo medido, anotar el caso hermano de las notas solapadas con inicio distinto, y un import mal ordenado).
Task 5: fix round 2/5 (4 addressed; commits 48668c8..4103544; 567 passed / 30 skipped). El re-revisor REPRODUJO lo declarado: el Mi menor sale exactamente con los trastes del docstring, y el caso de las notas solapadas con inicio distinto comparte cuerda de verdad. Una declaracion falsa habria sido peor que no declarar nada.
Task 5: minor (deferred): el docstring dice "tramo de 10 trastes" contando desde la cuerda al aire; entre trastes pisados son 8. No es falso pero puede leerse mal.
Task 5: minor (deferred): el informe cita 566 passed cuando son 567.
Task 5: minor (deferred), PREEXISTENTE: ruff marca un import sin usar en tests/test_afinaciones.py, ya senalado en la Task 3. El proyecto solo corre ruff sobre nucleo/ y servidor/.
Task 5: complete (commits 7f9f4fd..4103544, review clean)
Task 6: implementada (46be01a, 578 passed / 30 skipped, verde en orden inverso). DONE_WITH_CONCERNS.
Ruling: acepto que la tablatura del archivo solo se respete si DA ESA ALTURA en el perfil elegido, y si no, la nota vaya a digitar. Es un anadido del implementador que mi brief no pedia y es correcto: una tablatura escrita para Drop C leida con afinacion estandar daria notas equivocadas, y respetarla a ciegas convertiria el dato bueno del archivo en un error silencioso. Coste si me equivoco: una tablatura valida podria ignorarse si el perfil elegido no es el suyo, que es justo cuando no deberia respetarse.
Ruling: acepto el cambio de la prueba test_sin_tablatura_la_pone_el_algoritmo. Mi brief esperaba cuerda 5 traste 0 para un 45 suelto, y con una nota sola 5/0 y 6/5 EMPATAN en coste, asi que digitar devuelve 6/5. El supuesto era mio y estaba mal; la prueba usa ahora una frase de tres notas que si desempata. Coste si me equivoco: ninguno.
Task 6: revision NO aprobada. 0 Critical, 5 Important, todos huecos de prueba medidos por mutacion. El codigo se comporta bien en los seis puntos verificados ejecutando.
La trampa del EMPATE volvio a aparecer: test_si_el_archivo_trae_tablatura_se_respeta usa una nota suelta cuyo valor coincide con lo que el algoritmo elegiria, asi que pasa aunque se ignore la tablatura entera. Es el mismo defecto que el implementador ya habia corregido en otra prueba del mismo archivo.
Task 6: fix round 1/5 despachado (cinco pruebas: tablatura que contradice al algoritmo, coherencia con el perfil, ligadura continue, traste solo, repeticion mal formada; mas averiguar si music21 escribe .music21rc en el home del usuario).
Task 6: fix round 1/5 (5 addressed; commits 46be01a..bc95a82; 583 passed / 30 skipped, verde en orden inverso). El re-revisor repitio las cinco mutaciones del implementador Y busco las suyas propias para las dos del requisito central: cuatro mutaciones distintas matan la prueba de la tablatura, asi que no esta escrita alrededor de una sola. Confirmo tambien que el 52 en 6/12 no es un empate disfrazado, y que parsear el archivo una vez da salida identica.
Task 6: minor (deferred): el test_si_el_archivo_trae_tablatura_se_respeta ORIGINAL sigue sin poder fallar. Ahora es redundante con el nuevo; conviene borrarlo o reforzarlo para que nadie lo lea como cobertura.
Task 6: music21 NO deja rastro en el home del usuario: verificado por el implementador con HOME apuntando a un directorio vacio, y comprobado por mi que ~/.music21rc y ~/.music21 no existen.
Task 6: complete (commits 4103544..bc95a82, review clean)
Task 7: implementada (e069760, 609 passed / 30 skipped, verde en orden inverso). DONE_WITH_CONCERNS.
El implementador encontro TRES pruebas de mi brief que no pueden fallar solas: la 3 pasa con duracion constante porque las dos distancias son iguales; la 6 termina en "or len(perfil) > 0", que siempre es cierto; la 8 casa con "2|linea", que encaja con casi cualquier mensaje. Las dejo tal cual y escribio 15 nuevas que las refuerzan. Es la cuarta vez que la trampa aparece en esta etapa, y la primera que la detecta quien escribe las pruebas en vez de quien las revisa.
Ruling: acepto que un bajo de CINCO cuerdas se rechace salvo que se pase perfil_clave. Mi brief solo especifico 4, 6 y 7 lineas, y cinco lineas son ambiguas de verdad: un bajo de cinco y una guitarra a la que le falta una linea se ven igual en texto. Rechazar nombrando el problema es mejor que adivinar. Coste si me equivoco: quien tenga un bajo de cinco tiene que elegir la afinacion a mano una vez.
Task 7: revision NO aprobada. 2 Important, 4 Minor. El revisor probo mas de 40 tablaturas y 17 mutaciones; las quince pruebas nuevas muerden todas.
I1: la `b` minuscula se lee como si bemol, porque endswith("b") la toma por un bemol. Con e|b|g|d|a|e —la convencion mas comun de los foros— la segunda cuerda entra un semitono baja y nada falla.
Ruling: el orden de los acordes pasa a GRAVE PRIMERO, como los otros tres lectores, y mi prueba del bajo que lo impedia se cambia. Importa porque seguimiento.py senala la ultima nota de un acorde: con tres lectores esa es la aguda y con el cuarto seria la grave, asi que el carril se comportaria distinto segun de donde viniera la cancion. La prueba era mia y estaba mal. Coste si me equivoco: una prueba del brief cambia y el orden queda fijado explicitamente para el proximo lector.
Task 7: fix round 1/5 despachado (I1 la b minuscula, I2 el orden de los acordes, tres menores, y borrar las pruebas vacias del brief que las nuevas ya dominan).
Task 7: fix round 1/5 (6 addressed; commits e069760..7e2d4c0; 609 passed / 30 skipped, verde en orden inverso). Verificado: la tablatura en minusculas da afinacion estandar; los bemoles de verdad (Bb, eb, Eb) siguen funcionando; el orden de acordes coincide con los otros tres lectores; y para cada prueba borrada el revisor identifico cual la domina y lo comprobo por mutacion. El commit contiene solo lo que dice.
Task 7: minor (deferred), PARA LA REVISION FINAL: con afinaciones raras —una cuerda mas aguda que suena mas grave— el orden de acordes de Guitar Pro (por cuerda) y el de MIDI/MusicXML (por altura) pueden diferir. Con afinaciones normales los cuatro coinciden.
Task 7: el re-revisor senalo que el trailer del commit deberia decir otro modelo. Se equivoca: la atribucion que esta sesion tiene indicada es la que llevan los commits.
Task 7: complete (commits bc95a82..7e2d4c0, review clean)
Task 8: implementada (04d3c16, 625 passed / 30 skipped, verde en orden inverso). DONE_WITH_CONCERNS.
La trampa de la prueba que no puede fallar aparece por QUINTA vez: la cuarta del brief, la de mayusculas, se cumple igual sin .lower() porque el mensaje de error lista .gp5 de todos modos. El implementador la reforzo parcheando el lector y comprobando que recibe la ruta.
Ruling: acepto que el registro lea el archivo como UTF-8 y caiga a cp1252 si no decodifica. Las tablaturas de foro vienen de todas partes y rechazar por codificacion seria rechazar por algo que no tiene que ver con la musica. Coste si me equivoco: una tablatura en una codificacion rara entra con algun caracter mal, no con notas mal.
Task 8: revision aprobada, sin Critical ni Important. 5 Minor. El revisor parcheo las funciones reales de cada lector y recorrio las 12 extensiones en las dos tablas: cada una cae donde debe y las claves de FORMATOS, _LECTORES y _CONVERSORES son identicas. Confirmo que el ciclo de imports es real.
Task 8: minor (deferred): una asercion de prueba usa "or len(pieza.notas) == 4", asi que la primera mitad no obliga a nada. Sexta aparicion de la misma familia; la prueba se salva por sus otras dos aserciones.
Task 8: minor (deferred): un docstring dice Latin-1 donde el codigo usa cp1252; ninguna prueba cubre el BOM; y las extensiones estan escritas en cuatro sitios, con una sola prueba impidiendo que se desalineen.
Task 8: PARA LA TAREA 9: un .txt o .tab inexistente lanza FileNotFoundError mientras que los otros tres formatos lanzan ValueError. Quien capture solo ValueError en el servidor dejara escapar ese caso.
Task 8: complete (commits 7e2d4c0..04d3c16, review clean)
Task 9: implementada (e10efe1, 668 passed / 30 skipped, verde en orden inverso). DONE_WITH_CONCERNS.
Seguridad: el implementador cubrio con prueba .. en cualquier posicion, subcarpetas, nombres absolutos, separadores de Windows, ".", "..", vacio y en blanco, byte nulo, y ENLACE SIMBOLICO que apunta fuera. Declaro lo no cubierto: enlace dentro de la carpeta, montajes, y que macOS no distingue mayusculas, asi que X.TXT y x.txt son la misma cancion.
Ruling: el endpoint de importar pasa a BASE 1, como el nucleo y como el campo "numero" que /pistas publica, y cambio la prueba de mi brief que usaba 0. Es el mismo defecto que ya corregi en la Task 5 y volvi a cometer aqui. Publicar indice y numero a la vez mitiga pero deja la trampa: si la interfaz manda "numero" importa la pista SIGUIENTE sin error visible, que es un off-by-one silencioso. Coste si me equivoco: una prueba del brief cambia y la interfaz tiene un solo campo que mandar.
Ruling: acepto python-multipart como dependencia nueva, que mi brief no preveia. FastAPI no acepta UploadFile sin ella. Coste si me equivoco: una dependencia mas, de las pequenas.
Task 9: revision NO aprobada. 5 Important, 9 Minor. El revisor ataco el guardia de nombres con ~25 vectores propios (URL-encoding simple/doble/mixto, UTF-8 overlong, U+2025, fullwidth, UNC, "..;/", RTL, NFD, enlaces simbolicos) y NINGUNO se salio de la carpeta; dejo un centinela fuera y seguia intacto. Senalo que el orden es correcto: NFC antes de buscar separadores, y NFC y no NFKC.
I2: el techo de 10 MB no limita lo que dice. Instrumentado: con 200 MB el SpooledTemporaryFile YA esta volcado a disco antes de la primera lectura, y el docstring afirma que un .pdf se rechaza "sin traer un solo byte a memoria", que es falso.
I5: septima prueba vacia de la etapa. La que promete fijar el guardia sobre el {id} de la URL pasa con el guardia DESMONTADO, porque dos de sus tres casos ni llegan al handler.
Ruling: /api/perfiles publica las de fabrica MAS el perfil activo si no esta entre ellas. Hoy /pistas propone una clave que el selector no ofrece, y PUT /api/config la acepta, dejando al afinador con un perfil sin opcion. Publicar el registro vivo entero llenaria el selector; no publicar nada deja al usuario sin poder afinar a la cancion. Coste si me equivoco: el selector tiene una entrada mas cuando la afinacion activa es rara.
Ruling: la guarda anti-CSRF se aplica a TODOS los metodos que cambian estado, no solo al endpoint nuevo que la revision automatica marco, y deja pasar las peticiones SIN Origin para no romper curl ni la linea de comandos. Hoy cualquier web que el usuario visite puede hacer POST a 127.0.0.1:8420 y cambiarle la afinacion. Coste si me equivoco: un cliente de navegador con Origin raro se queda fuera.
Task 9: fix round 1/5 despachado (I1 PermissionError, I2 el techo, I3 coincide con formatos sin afinacion, I4 el perfil no listable, I5 la prueba vacia, mas base 1 y la guarda anti-CSRF).

## Tarea 9 — ronda de arreglos 2 (BASE 70c5110)
Re-revisión de la ronda 1: los 7 hallazgos ADDRESSED. Dos nuevos, misma raíz
(el `""` compartido entre Host y Origin):
- `Origin: null` / `file://` / `https:` pasan el guardia y pueden ESCRIBIR
  (iframe sandbox + FormData = petición CORS simple, sin preflight). Medido: 200.
- Los tres WebSocket no pasan por el middleware http: `Host` y `Origin` ajenos
  conectan y emiten telemetría del micrófono a 30 Hz.
Ruling: se arreglan los dos antes de fusionar, en una sola ronda — el commit en
revisión es justo «el guardia de peticiones», así que dejarlos fuera convierte un
commit de seguridad en un commit que declara una defensa que no tiene. Coincide
con el segundo aviso de seguridad automática, que señala la misma cadena vacía.
Si me equivoco, el coste es un commit extra de ~40 líneas en una rama sin fusionar.
Brief: task-9-fix2-brief.md
Arreglo: 0473310 «el Origin se valida como URL y los WebSocket pasan por el guardia».
Dos conjuntos derivados del mismo parámetro (firma de `crear_app` intacta):
`anfitriones` con el `""` para el Host, `origenes` sin él; `urlsplit(...).hostname`,
`null` rechazado por nombre (`ORIGENES_OPACOS`); `_vigilar_websocket` cierra con
1008 antes de `accept()` en los tres. 736 passed / 30 skipped (+38 por
parametrizacion), ruff limpio. Cuatro desmontajes declarados: 14 / 12 / 1 / 1.
Hallazgo de paso: `TestClient.websocket_connect` ignora el `base_url` y manda
`Host: testserver`, asi que las seis pruebas de WebSocket que ya existian probaban
contra un anfitrion que el servidor real rechaza; pasan a usar la URL entera.
Re-revision acotada de 70c5110..0473310 despachada.

## Tarea 10 — exploracion previa y tres rulings (antes de despachar)
Mirando el brief contra el codigo real aparecen tres defectos del plan:

1. **No hay puerta al carril para una pieza importada.** `/api/piezas/iniciar`
   (`servidor/app.py:565`) solo acepta un descriptor de ejercicio
   (`familia`/`parametros`) y genera la pieza con `pieza_desde_ejercicio`; no hay
   ningun endpoint que acepte una `Pieza` ya leida. `/importar` declara
   explicitamente «SIN ponerla en marcha» y remite a `/api/piezas/iniciar`, que no
   puede. El paso 3 del brief dice «al confirmar, la pieza va al carril» y la spec
   §6 describe el camino importas → afinas → el carril la acepta. Es un hueco de
   interfaz entre T9 y T10, no de la spec.
   Ruling: `/api/piezas/iniciar` acepta TAMBIEN `{cancion, pista, perfil}` como
   alternativa a `{familia, parametros}`, importa en el servidor y arranca. Una
   sola puerta al carril —la que ya aplica la regla de afinacion de la 3a— y la
   pieza no viaja al navegador para volver: aceptar una `Pieza` que manda el
   cliente seria creerle las notas. T10 toca por tanto `servidor/app.py`, que el
   brief no lista. Si me equivoco, el coste es mover el endpoint de sitio.
2. **`crearFetchFalso({...})` del brief no existe.** El unico con ese nombre esta
   en `interfaz/src/Afinador.test.tsx:67`, es local al archivo y su firma es
   `(respuestaPut, respuestaCalibrar?)`, no un objeto de datos.
   Ruling: las pruebas del brief son bocetos de forma, no codigo que compile. T10
   escribe su propio doble local en `Canciones.test.tsx`, y las formas que valen
   son las de los endpoints reales, no las abreviadas del brief.
3. **Los casos 3 a 6 del brief hacen `click` en «x» sin que el doble devuelva la
   lista de canciones.** Ruling: cada caso monta la lista entera; ese click es la
   precondicion, no el sujeto de la prueba.

T10 se despacha cuando cierre la re-revision de T9: comparten `servidor/app.py`.

Re-revision de 70c5110..0473310: hallazgos A y B **ADDRESSED**, medidos contra un
uvicorn de verdad (no TestClient) con handshake WS a mano. Los cuatro desmontajes
cuadran (14/12/1/1). 736 passed / 30 skipped, ruff limpio, arbol limpio.
Aviso de metodo que corrige a la revision anterior: `curl -H "Origin: "` BORRA la
cabecera, asi que el caso del Origin vacio medido con curl media «sin Origin».
Con socket crudo da 403: el arreglo si lo cubre.
Correccion al informe del implementador: dice que ninguna prueba nueva es un
empate, y 18 de los 38 casos pasan verbatim con el app.py de 70c5110; 16 no caen
bajo ninguno de los cuatro desmontajes declarados. Ninguna pasa por un motivo
falso —son guardias de no-regresion que el brief pidio— pero la frase del informe
es falsa. Es un fallo del informe, no del codigo.
Tambien: el parametro `anfitriones=` de `crear_app` no tiene ningun llamador; el
informe dice que las pruebas lo inyectan y no es cierto.
Tarea 9: complete.

Minors parkeados (van en el despacho de T10, que ya toca servidor/app.py):
- El 1008 de `_vigilar_websocket` no se ve en el cable: al cerrar antes de
  `accept()`, ASGI lo traduce a un HTTP 403 en el handshake y ningun cliente real
  recibe la trama. El docstring afirma lo contrario. Ruling: se corrige el
  docstring, no el codigo — rechazar en el handshake es lo correcto.
- `test_sin_cabecera_host_se_atiende_igual` manda un `Host` vacio, no ausente.
  Los dos dan 200, pero el nombre promete mas de lo que ejerce. Ruling: renombrar.
Minors no accionados, con motivo: el esquema del `Origin` se ignora (ningun
navegador emite `https://localhost` apuntando a algo que confundamos con nosotros);
`Host` duplicado gana el primero (h11 no lo rechaza, y aqui no hay proxy);
`0.0.0.0` como Origin (mismo trato que `localhost:3000`, que el diseno admite).

## Tarea 10 — la pantalla de canciones
Implementada: 19b8852 «la pantalla de canciones, con los avisos antes de empezar».
745 passed / 30 skipped (Python), 154 passed (interfaz), build y lint limpios.
31 mutaciones declaradas, 31 caidas; dos no cayeron a la primera y las dos eran
codigo suyo sin cubrir (la prop nueva de `Carril.tsx` y la marca `yaPedida`).

DONE_WITH_CONCERNS. La desviacion que declara, y mi ruling:
El brief pedia que `Canciones` arrancara la pieza y que no reescribiera
`Carril.tsx`. Las dos cosas juntas no se pueden: la pieza entera viaja una sola
vez en la respuesta de `POST /api/piezas/iniciar` y el WebSocket no la repite, asi
que la sesion de `useCarril` que no hizo ese POST no tiene pieza que pintar.
Resolvio con una prop opcional `peticion` en `Carril` (+36 lineas, sus 43 pruebas
intactas) y el traspaso en `App.tsx`.
Ruling: aceptado. Quien PIDE la pieza tiene que ser quien la DIBUJA, y entregar lo
literal daba una app rota —el carril con el configurador de escalas mientras el
servidor ya seguia el audio de la cancion—. Mi brief era el que estaba mal: pedi
«al confirmar, la pieza va al carril» sin mirar por donde viaja la pieza. Si me
equivoco, el coste es mover el POST de componente, ~60 lineas en dos archivos.
Dos cambios fuera de su lista, los dos declarados: `tests/test_modulos.py` usaba
`"canciones"` como el modulo que no existe (ahora `"efectos"`), y las pruebas del
endpoint fueron a `test_app_canciones.py` porque el `cliente` de
`test_app_carril.py` construye la app sin `carpeta_canciones`.
Deuda que confirma: `tiposPieza.ts` le faltan exactamente cuatro campos de
`a_dict()` —`secciones`, `ritmo_aproximado`, `tempo_variable`, `compas_variable`—
y añadirlos rompe la compilacion de todos los literales de `Pieza` en
`Carril.test.tsx` y `VistaEscritaPieza.test.tsx`. Va a la revision final.
Tambien: tocar una cancion y cambiar de modulo deja la pieza en marcha en el
servidor (la deuda de `/api/piezas/detener` al desmontar, ya anotada); el camino
para alcanzarla es ahora uno mas.
Revision de tarea despachada (0473310..19b8852).

Revision de T10: recomienda aceptar. Sin Critical. Verifico por su cuenta las 31
mutaciones (caen las 31) y construyo 30 adicionales: **ninguna de las 32 pruebas
nuevas es un empate** — primera tarea de la etapa en que se cumple. Tambien
verifico el razonamiento de la desviacion en el codigo: `estado()` no lleva la
pieza (`servidor/piezas.py:238`), el WebSocket solo manda `estado()`
(`app.py:664`), `recibir()` nunca llama a `setPieza` (`useCarril.ts:220`). Y el
`useEffect` del POST es seguro bajo StrictMode, con control para que la prueba no
fuera otro empate: confirmo primero que StrictMode duplica efectos de verdad
(4 WebSocket para 2 montajes) y entonces que el POST se hace una sola vez.

Alternativa mas pequena que el implementador no listo, por si la revision final la
quiere: que el servidor publique la pieza en curso (`GET /api/piezas/pieza`) y el
carril la cargue al montar — sin prop nueva ni fontaneria en `App`, y arreglaria un
hueco preexistente (recargar el navegador a mitad de cancion deja el carril en
blanco). Coste: un segundo camino por el que la pieza llega al cliente, que es lo
que la 3a evito; pero su motivo declarado («desperdiciar el canal», 30 Hz) no
aplica a una peticion por montaje.
Ruling: no se cambia ahora. Lo entregado funciona y es pequeno, y reabrir por donde
viaja la pieza a estas alturas de la etapa es rehacer T10 por una mejora que no
pide la spec. Queda anotado para la revision final. Si me equivoco, el coste es
que la 3c herede la prop en vez del endpoint.

Ronda de arreglos 1 despachada (implementador reanudado): I-1 `cancion` sin validar
tipo da HTTP 500 (`{"cancion": 123}` -> TypeError sin capturar); I-2 el `null` de
`coincide` probado a medias, la mutacion `coincide === true` sobrevive a las 154;
I-3 el cuerpo del POST a `/importar` no lo afirma nadie (base 1 otra vez); I-4
carrera de respuesta rancia en `elegirCancion`/`elegirPista`; mas M-1, M-2, M-4,
M-5, M-8, M-9, M-10. M-3 y M-6 parkeados.
M-7: tres cifras del informe no cuadraban (20 pruebas, no 43; +34/-2, no +24; 63
archivos sin formatear, no 40). Senalado como lo que mas me importa de la ronda.

Ronda 1 de T10: 7192ccc. 754 passed / 30 skipped, 164 en interfaz.
Re-revision de 19b8852..7192ccc: los cuatro Important **ADDRESSED**, los seis Minor
tambien. 89 peticiones contra `/iniciar` con 21 valores x 4 posiciones del dict mas
5 cuerpos que no son dict: ni un 500. Las 18 mutaciones declaradas verificadas una
por una: 16 caen, 2 no, exactamente como dice la tabla, y las dos no-caidas estaban
declaradas. Las cifras de la tabla: **cero mal esta vez** (la ronda anterior tuvo
tres). Fusionaria.
La carrera de I-4 era peor de lo que la revision describio: no era la lista de
pistas de A bajo el titulo de B, era el detalle entero de A sobrescribiendo el de
B, titulo incluido, con B seleccionada.
Las dos dudas, resueltas a favor del implementador y con mejor defensa de la que
el midio: la mutacion que su propio comentario nombra —quitar el `pista !== null`
del render— no cae sola, y cae junto al contador; o sea que el escenario futuro
que describe esta demostrado y el contador es lo que lo para. La `key={traspasos}`
vale, con una consecuencia no dicha: en el remontaje `useCarril` cierra el
WebSocket pero no llama a `/api/piezas/detener`.

Ronda 2 despachada, dos cosas:
- N-1: arreglar la RAIZ de I-1 en `servidor/canciones.py:76` (`nombre or ""` acepta
  cualquier valor veraz no-str) con un `isinstance`, para que el 400 deje de
  llevar «normalize() argument 2 must be str, not int» como mensaje de usuario.
  Mismo problema, anterior: `{"perfil": ["x"]}` -> «unhashable type: 'list'».
- N-2: el parametro `None` de la parametrizada es una tautologia —`None` es falso,
  `nombre or ""` lo hace `""` y ya daba 400 antes del arreglo—, sin declarar.
N-4 a su criterio (`cargarLista` sin contador). N-5 informativo y fuera de alcance:
`pnpm lint` sale con codigo 0 aunque oxlint reporte avisos, verificado plantando
un `debugger`; ese comando no serviria de puerta en CI.

## Tarea 11 — el README
Brief preparado con apendice: tabla obligatoria de afirmacion -> comando -> lo que
salio, una fila por afirmacion, y las no medibles con las palabras «no medido».
Despachada en paralelo con la ronda 2 de T10: T11 solo toca README.md.

Ronda 2 de T10: 22ace2a. 757 passed / 30 skipped, 165 en interfaz. 8 mutaciones,
8 caidas. Sin dudas.
N-1 arreglado en la raiz: `isinstance(nombre, str)` como primera comprobacion de
`_nombre_seguro`, y `nombre or ""` pasa a `nombre` porque ese `or` solo tapaba lo
que ahora se rechaza. La prueba fija el mensaje, el `repr` del valor y que no
aparezca `normalize`.
Hallazgo suyo: el mismo `isinstance` **no** cubria el `perfil`, que va a un `in`
sobre un dict y no por `_nombre_seguro`. Lo arreglo aparte en `_perfil_pedido`,
solo el tipo —la existencia la sigue decidiendo el nucleo con su lista—, por las
dos puertas, con una tercera prueba para que la comprobacion no se convierta en
«ningun perfil pasa».
N-2: el arreglo si cambia el caso. El docstring dice ahora que los seis valores
entran por la rama del tipo, `None` incluido, y que el unico que sigue cayendo por
la del nombre vacio es `""`, que tiene su prueba.
N-4: tercer contador puesto, con prueba que mira el boton de la lista y no el texto
a secas (sin ese cuidado pasaba con la mutacion puesta).
Shas fijados en la tabla de cifras. Re-revision corta despachada (sonnet).

Re-revision de 7192ccc..22ace2a: N-1, N-2 y N-4 ADDRESSED. Ningun 500 en los dos
endpoints con 13 tipos raros por campo, y ningun `detail` con `normalize`,
`unhashable` ni nombres de funciones de Python. Las 8 mutaciones caen. La cuarta
fila confirmada. Todas las cifras cuadran, verificadas con un worktree por sha
(0473310: 132 tests; 19b8852: 154; 7192ccc: 164; 22ace2a: 165).
ADDRESSED CON UN AGUJERO en el perfil: ninguna prueba pasa un `perfil` de texto
valido por `/api/piezas/iniciar`. Mutar `importar(ruta, numero, perfil)` a
`importar(ruta, numero, None)` en `_pieza_para_el_carril` deja **132 de 132 en
verde**: esa puerta puede ignorar el perfil entero sin que nadie se entere. Era asi
antes de T10, pero es justo el riesgo que yo pedi vigilar y la prueba vigilaba la
otra puerta.
Ronda 3 despachada (ultima): esa prueba, el camino de error de `cargarLista` (M-1
otra vez, cerrado para las otras dos peticiones y no para esta), y una tilde en el
mensaje del perfil.
El ` M README.md` que vio la re-revision es T11 escribiendo en paralelo, no un
proceso perdido.

Ronda 3 de T10: 4d6cd2c. 758 passed / 30 skipped, 166 en interfaz. 5 mutaciones,
5 caidas, incluidas las dos que estaban en verde. Sin dudas.
Reprodujo mi medicion antes de tocar nada (132/132 en verde con el perfil
ignorado). La prueba nueva pone la afinacion activa en Drop D e importa el MIDI,
que no declara la suya, asi que el perfil es lo unico que decide: un perfil
ignorado hace que el lector ponga `guitarra_estandar` y el carril conteste 400.
Es un 400 contra un 200, no un 200 contra otro — por eso puede fallar.
Nota de proceso suya que vale la pena guardar: añadio sus tres archivos por nombre
en vez de `git add -A`, que es lo que uso en las dos rondas anteriores y hoy se
habria llevado por delante el README a medio escribir de T11.

Ruling: NO se despacha re-revision de la ronda 3. Son tres items, +2 pruebas, y el
implementador reprodujo la medicion del agujero antes de arreglarlo y declaro que
hace falible cada prueba nueva. La revision final de rama es el paso siguiente y
lee el diff entero, asi que verificar esto dos veces en media hora es gastar una
revision donde ya va a pasar otra. Si me equivoco, la revision final lo encuentra,
que es su trabajo.
Tarea 10: complete.

## Tarea 11 — el README
cf9a7c0, solo README.md (173+/16-). 758 passed / 30 skipped, 166 en interfaz.
Tabla de 60 filas: afirmacion -> comando -> lo que salio. **Medir cambio cinco
cosas que el apendice creia:**

1. `.gpx` y `.gp` no tienen «menos cobertura»: **no tienen ninguna**. PyGuitarPro
   0.11 solo trae gp3/gp4/gp5; un `.gp` real (ZIP con Content/score.gpif) y un
   `.gpx` real (cabecera BCFZ) mueren con `unsupported version`. Y como las
   extensiones estan en `FORMATOS`, el archivo **se sube** y falla despues.
2. **El «39 % menos movimiento» no existe como cifra.** No hay script ni prueba que
   la produzca; la prueba solo comprueba `optimo <= heuristico`. Medido: el
   recorrido del ancla baja 37,2 % con la semilla de la prueba, 43,2 % con mil
   notas, 97,9 % en una escala — pero **el salto crudo de traste a traste sale
   9,6 % PEOR, y peor en 123 de 200 secuencias**, porque el coste minimo prefiere
   las cuerdas al aire, que son gratis. Los 34 ms si reproducen (mediana 35,1).
3. Las casillas de primera y segunda vez: confirmado. `|: A | B(1a) :|` + C suena
   `0,1,0,1,2,3` cuando lo correcto es `0,1,0,2,3`.
4. **MusicXML NUNCA declara su afinacion**, ni con tablatura (`cuerdas_midi=()`
   escrito a mano en `_describir`), asi que con MIDI y MusicXML `coincide` es
   siempre `null`. Y un cambio de tempo o de compas se detecta, se guarda y **no
   llega ningun aviso**: `_avisos_de` solo mira `ritmo_aproximado`.
5. **El aviso de afinacion es inutil la primera vez con una afinacion rara.**

Verificado por mi: `_clave_de_la_afinacion` —quien llama a `registrar_perfil`—
solo se alcanza desde `pieza_desde_guitarpro`, no desde `pistas_de`.

Rulings de la ronda 1 de T11:
- `.gpx`/`.gp` **se rechazan en la puerta**, con un 400 que diga que si funcionan
  `.gp3`/`.gp4`/`.gp5`. Un archivo que se sube y falla despues es peor que uno que
  no entra: el usuario ya lo copio a su biblioteca y el error le llega en otro
  sitio hablando de versiones. Si esta en `FORMATOS`, tiene que funcionar.
- **El perfil se da de alta tambien al listar**, en los formatos que declaran
  afinacion (Guitar Pro y ASCII). Rompe la decision que el usuario tomo para esta
  etapa —decirle a cual afinarse y llevarlo al afinador— y la rompe en el unico
  caso donde hacia falta: con afinacion de fabrica el aviso ya funciona; quien
  necesita que le digan es el de Drop C. Un aviso que funciona la segunda vez que
  abres la cancion no es un aviso. El argumento del docstring de `afinacion_de`
  (no ensuciar el registro con afinaciones que nadie importo) no se sostiene
  cuando el usuario ha abierto la cancion: listar sus pistas es un acto de
  intencion igual que importarla. Si me equivoco, el coste es una entrada de
  registro por cada cancion que el usuario mira y no importa.
- `_avisos_de` gana las frases de `tempo_variable` y `compas_variable`. El sitio
  existia declarado para esto.
- El parrafo de la digitacion **conserva las cifras** y recorta la prosa: el
  contraejemplo del 9,6 % peor es la frase mas valiosa, porque es el tipo de cosa
  que este README ha afirmado mal cinco veces al reves. Que el «39 %» no tenia de
  donde salir va al informe, no al README.
- Las dos filas marcadas como deduccion se quedan marcadas. No se montan dos
  pruebas de interfaz a estas alturas para eso.
- No se arreglan: las casillas de primera/segunda vez (medido y documentado como
  limite; arreglarlo es rehacer el expansor de repeticiones), que MusicXML no
  declare afinacion (es como esta escrito el lector, queda como limite),
  `tiposPieza.ts`.

Octava prueba defectuosa de la etapa: `Canciones.test.tsx`, «la lista que llega
tarde…», usaba `getByText` con el nombre presente dos veces. Se arreglo sola en
4d6cd2c. Esa cuenta va al mensaje final de la rama.

Ronda 1 de T11: fbe9cfe (codigo y pruebas, +29) y b10bd99 (README donde dejo de
ser verdad). 786 passed / 30 skipped, 166 en interfaz.
Hallazgo suyo que no se veia desde fuera y que habria sido peor que el fallo
original: el traste maximo entra en la clave del perfil a medida, y el camino de
importar lo sacaba de las notas **ya convertidas**, que al listar no existen. Si
cada camino lo calculaba a su manera, el listado habria propuesto
`a_medida_…_22t` y la pieza habria traido `…_24t`: el usuario se afina a lo que le
dice la pantalla y el carril le sigue rechazando la cancion, o sea que parece que
obedecer no sirve. Lo cuenta una sola funcion (`_traste_maximo`) y los dos caminos
pasan por ella. Coste medido: recorre los beats que `_contar_notas` ya recorria en
el mismo bucle, y la suite no se movio (23,4 s -> 23,4 s con 29 pruebas mas).
Barrido de `FORMATOS`: no queda ninguna otra extension rota. Fabrico un archivo de
verdad de cada una de las diez; `.mxl` como contenedor comprimido real con su
META-INF, no renombrando un `.xml`. Quedo como prueba parametrizada sobre
`sorted(FORMATOS)`, asi que crece sola.
La tablatura ASCII ya registraba al listar y no se toco. Verificado con una
afinacion rara, no con Drop D, que es de fabrica y no habria probado nada.
**Novena prueba defectuosa evitada por el implementador**: la de percusion pasaba
igual con el arreglo roto porque usaba la afinacion estandar, que no se da de alta
de todas formas. La cambio a una rara y lo dejo en el docstring. Nueve mutaciones,
nueve fallos.

Ruling sobre su duda 1: el alta al listar registra el perfil de TODAS las pistas y
asi se queda. Cada pista publica su afinacion y necesita su clave para su propio
aviso; registrar solo la de referencia devuelve el fallo que acabamos de arreglar
para cualquier pista que no sea la primera. Lo que ensucia es un diccionario en
memoria hasta reiniciar, y no el selector (publica fabrica + activa, medido).
`NO_LEIBLES` con solo lo medido (.gpx, .gp) es correcto: no inventar entradas para
formatos no probados.
Tarea 11: complete.

Ruling: la revision de tarea de T11 se funde con la revision final de rama, que es
el paso siguiente, va en el modelo mas capaz y lee el diff entero. Revisar lo mismo
dos veces en media hora gasta una revision donde ya va a pasar otra; los tres
arreglos de `fbe9cfe` van nombrados como foco en el despacho para que no se pierdan.

## Revision final de rama
Despachada: 8d4b53a..HEAD, 26 commits, 38 archivos, ~8800 lineas (sin uv.lock).
Diff en review-final-rama.diff. Focos: la trampa del empate en las pruebas que
sostienen las afirmaciones centrales, los tres arreglos de `fbe9cfe` que entraron
despues de la ultima revision de tarea, las ocho deudas conocidas con juicio de si
bloquean, las afirmaciones del README comprobadas de nuevo, si el endpoint nuevo
hereda las protecciones de sus vecinos, y la coherencia de once tareas como una
sola cosa.

Revision final: «el resto de la rama es el trabajo mejor medido que he revisado,
pero C1 deja a una cancion real permanentemente intocable mientras la pantalla
afirma que estas bien afinado». Veredicto: fusionar cerrando C1.

**C1 (Critical).** `_clave_en_registro` (`servidor/canciones.py:352`) compara solo
el juego de notas MIDI y devuelve la PRIMERA entrada que encaje, pero la clave de
un perfil a medida **incluye los trastes**. Con dos perfiles de la misma afinacion
y distinto numero de trastes, el listado propone el que no es. Medido de punta a
punta: te afinas a lo que te dice la pantalla, **el listado contesta `coincide:
True`**, el carril contesta 400, y `..._24t` nunca es elegible porque
`/api/perfiles` publica solo fabrica + activa. Desde la interfaz **no hay salida**.
El implementador de T11 tenia razon a medias: `_traste_maximo` si es una sola
funcion y los dos caminos DEL LECTOR coinciden; la divergencia esta en la
**tercera** implementacion, que es la que usa el aviso. `fbe9cfe` no lo introdujo
—`cf9a7c0` tambien divergia— pero lo convirtio en el camino normal.
Y esto responde a mi pregunta de si el alta de todas las pistas tenia consecuencias
que nadie vio: **si, esta** — la clave de la pista 1 tapa la de la pista 2 dentro
del mismo archivo.
Las tres pruebas que guardan la propiedad usan una cancion de UNA pista y dos
afirman `len(nuevas) == 1`, lo que OBLIGA a un registro que no puede tapar nada.
No son empates, pero eligen el unico caso donde el fallo no sale.

**I1.** El aviso es de la CANCION y la importacion de la PISTA: `coincide` sale de
la primera pista usable. Pista 1 en estandar y pista 2 en Drop C -> boton
habilitado, importar 200, arrancar 400, y sin «Afinarme a...». El dato por pista
**ya se publica y ya esta tipado**; la interfaz nunca lo lee.
**I2.** Novena prueba que no puede fallar, en el commit menos revisado: mutar
`max(_trastes_declarados, traste_maximo)` a secas deja la suite entera en verde,
porque las tres pruebas ponen `fretCount = 24` Y una nota en el traste 24. Y la
expresion si es load-bearing.
**I3.** El orden grave-primero sobrevive a la mutacion en Guitar Pro, MIDI y
MusicXML; solo cae en ASCII. La prueba que fija el invariante entre cuatro lectores
vigila solo el suyo. Importa porque `indice_actual` señala la ultima nota del
acorde, asi que el orden decide que nota resalta el carril.
**I4.** MusicXML dibuja acordes con dos notas en la misma cuerda: no tiene nada
equivalente a `_separar_cuerdas_de_acordes` de MIDI. El Mi menor sale `[4,4,2,2]`.
El ruling de T5 llamo «una respuesta equivocada» a dibujar una digitacion
intocable y lo arreglo para MIDI; MusicXML se quedo sin el.

Deudas juzgadas por la revision: `X.TXT` **ya cerrada** donde habia perdida de
datos (subir con otras mayusculas se rechaza; queda un alias de lectura inocuo).
Aparcar `GET /api/piezas/pieza` **fue correcto**, y ahora tiene un segundo motivo
para volver en 3c: con el endpoint la interfaz podria descubrir la pieza que el
servidor sigue tocando y detenerla, asi que cierra tambien la deuda del `detener`
al desmontar. Las dos juntas en 3c. El resto a 3c.

Ola de arreglos final despachada: C1, I1, I2, I3, I4, el aviso de las casillas de
primera/segunda vez (detectar es leer `repeatAlternative`, tres lineas, y
`_avisos_de` tiene el sitio declarado: es el unico punto donde la rama incumple su
propio estandar de «si se detecta, se avisa»), y siete afirmaciones falsas, entre
ellas la del README que C1 desmiente —seria la sexta— y el «98 %» que no es
reproducible (diente de sierra 27,1 %, sube-y-baja 55,7 %, una octava 100 %).
Brief: final-fix-brief.md.
Ruling sobre I4: se reusa la funcion de MIDI, no se escribe otra; si no es
reutilizable, se declara como limite en el README. Una segunda implementacion del
mismo reparto es como nacio C1.

Ola final: f63f5ba (C1 + I1 + I2), 358547d (I3), 6f1a56d (I4), c54d366 (el aviso
de las casillas), 51c2df3 (las siete afirmaciones falsas + `herramientas/
medir_digitacion.py` + la decision de seguridad declarada).
804 passed / 30 skipped (+18), 168 en interfaz, build y lint limpios.
C1 arreglado como pedi: la clave viaja desde el lector y **`_clave_en_registro`
borrada**, asi que ya no hay tercera implementacion. I4 por reuso de verdad:
`separar_cuerdas_de_acordes` pasa a `digitacion.py` y la usan MIDI y MusicXML.
Los cinco guiones de la revision reprodujeron clavados antes de tocar nada, asi que
ninguna medicion se cayo. 12 mutaciones, ninguna prueba nueva sobrevivio. Las tres
pruebas que nombre quedan intactas y al lado estan las que si ejercen el caso de
los dos numeros de trastes (dos archivos, y dos pistas del mismo archivo).
Re-revision acotada despachada.

Dudas del informe, pendientes de adjudicar con la re-revision:
1. La raiz de C1 sigue ahi: dos perfiles de la misma afinacion fisica (22t y 24t,
   mismas seis cuerdas) piden «afinarse» de uno a otro cuando en la guitarra no hay
   nada que tocar. Acotado, declarado y siempre accionable (200 tras el clic). Las
   dos salidas que ve cambian que es un perfil, o la regla del 400 del carril, que
   es de la 3a.
2. `Pieza` gano `casillas_de_repeticion`: `tiposPieza.ts` es espejo parcial con
   cinco campos ausentes en vez de cuatro.
3. El aviso de las casillas no distingue el caso inofensivo (casillas sin cierre de
   repeticion): avisa de mas.
4. Mi brief decia 28 archivos sin formatear y `ruff format` ve 63: los 28 eran de
   `nucleo/ servidor/` y los 63 del repo entero. La cifra mala era mia, no suya.
   Delta cero en los 15 `.py` que toco.

Re-revision de la ola final (b10bd99..HEAD): **veredicto fusionar**, cerrando una
sola prueba. C1 ADDRESSED en los cinco casos medidos de punta a punta (propone ->
importa -> PUT -> iniciar: 200 en todos; `div_formatos.py` y `div_e2e.py` pasan de
400 a 200, y la cancion a la que NO te afinas sigue dando 400, que es lo correcto).
I4 ADDRESSED por reuso real: una sola `def separar_cuerdas_de_acordes` y dos
importadores; MIDI clavado, MusicXML ya no colisiona; direccion de dependencias
intacta por barrido AST.

**Caso que no estaba en mi lista y que vindica el arreglo elegido**: un `.gp5` en
afinacion DE FABRICA con una nota en el traste 23. El lector registra
`a_medida_e2-...-_24t` y la pieza lo trae; la deduccion vieja contestaba
`guitarra_estandar`. Esa divergencia venia de la PRIMERA rama de `afinacion_de`
(`clave_de_perfil`, solo fabrica), **no** del registro vivo, asi que mi plan B
—comparar tambien los trastes en `_clave_en_registro`— **no lo habria cerrado**.
Hacer que la clave viaje desde el lector si. El arreglo es estrictamente mas fuerte
que la alternativa que yo ofreci.

Adjudicacion de las cuatro dudas:
1. La raiz de C1 **no es un Critical disfrazado**: medido, el aviso siempre lleva a
   un perfil que el carril acepta (400 sin el clic, 200 despues) y ningun archivo
   queda inalcanzable. A la 3c. Coste que la duda no nombraba (N3): `pisa23.gp5`
   prueba que una pieza puede pasar de 22 trastes, asi que comparar solo cuerdas
   dibujaria un mastil de 22 para una pieza que pisa el 23; quien la tome tiene que
   quedarse con el maximo de los dos mastiles.
2. `tiposPieza.ts` con cinco ausentes: correcto, nombrados con su motivo. No bloquea.
3. El aviso de las casillas avisa de mas: **confirmado midiendolo**. Con
   `repeatAlternative` sin `repeatClose` la pieza suena `[0,1,2]` —ningun compas de
   mas— y la frase es falsa. El implementador dijo que acotarlo era entender las
   casillas; la re-revision mide que son dos tokens. Va a la ultima ronda.
4. 63 vs 28: **mi error de alcance, no deriva suya**. 28 nucleo+servidor, 33 tests,
   2 herramientas, 63 el repo entero. Delta cero en los tres.

La decision de seguridad del GET que muta estado: ADDRESSED, «honesta y
defendible», medida contra la app corriendo (GET con Origin ajeno 200 y el alta
ocurre; PUT 403). El docstring describe la realidad sin suavizarla, y el coste de
cerrarlo cuadra: mover el alta al POST reabre el fallo que esta etapa arreglo.

**N1: la decima prueba que no puede fallar**, y en el ultimo commit.
`test_una_tablatura_que_no_choca_con_nadie_se_queda_quieta` es copia literal de
`test_si_el_archivo_trae_tablatura_se_respeta` con **una nota sola**, asi que nunca
entra en un grupo de acorde. Aplanar la matriz de coste a 0.0 deja 804 passed —y no
es un no-op: el Mi menor pasa de `4/2,5/10,2/0,3/9` a `4/2,3/0,2/0,1/0`—. La
propiedad «se cambia lo minimo» tiene cero cobertura, y el informe afirmaba tenerla
probada. Unico punto donde ese informe se paso.
Ultima ronda despachada: N1, el acotado del aviso de casillas, y dos lineas de
docstring (N2, N3).
