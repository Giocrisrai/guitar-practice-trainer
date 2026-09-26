# Registro de ejecucion — etapa 2a (ejercicios monofonicos)

Copia del cuaderno de bitacora con el que se ejecuto
`docs/superpowers/plans/2026-09-24-ejercicios-monofonicos.md`: la tabla de conflictos
previa, cada tarea con sus commits, y **todas las decisiones** que hubo que tomar por
el camino, cada una con lo que cuesta si esta equivocada. Se conserva porque el
espacio de trabajo del plan no sobrevive al cierre de la etapa, y varias de estas
decisiones explican por que el codigo es como es.


Spec: docs/superpowers/specs/2026-09-19-ejercicios-monofonicos-design.md
Rama: etapa-2a-ejercicios (base a924c35)

Ruling: rama en lugar de worktree — el sandbox solo concede escritura sobre este
directorio de proyecto y su .git. Mismo criterio que en la etapa 1.
Coste si es erroneo: el trabajo comparte checkout con main, reversible.

## Escaneo previo

| Par | Produce -> consume | Resultado |
|---|---|---|
| T1 -> T3,4,5,7 | Ejercicio, NotaEsperada (con referencia_midi) | OK |
| T2 -> T3,4,5 | ESCALAS, ACORDES, INTERVALOS, clases_del_patron, notas_alcanzables | OK |
| T3 -> T4 | T4 refactoriza escalas.py sobre comun.py; las pruebas de T3 son la red | OK, declarado |
| T4 -> T5 | comun.validar_parametros, secuenciar | OK |
| T6 -> T7 | DetectorAtaques, ESPERA_ESTABILIZACION_S | OK |
| T7 -> T9 | EvaluadorEjercicio, EstadoEvaluacion | OK |
| T8 -> T9 | Metronomo, SalidaAudio | OK |
| T9 -> T10 | SesionPractica, GENERADORES, observadores en Sesion | OK |
| T10 -> T11 | endpoints /api/ejercicios/* y /ws/ejercicios | OK |
| T1,T6 -> T12 | ataques.py, grabaciones reales | OK |

Autoconsistencia por tarea: T1 OK, T2 OK, T3 OK, T4 OK, T5 OK, T6 corregida antes de
empezar (ver abajo), T7 OK, T8 OK, T9 OK, T10 OK, T11 OK, T12 OK.

Ruling (aplicado al plan antes de ejecutar): tres pruebas de T6 eran incoherentes con el
codigo que el propio plan especificaba. Raiz comun: sin un suelo de nivel, el detector marca
ataque con el primer cuadro de ruido, porque frente a los -120 dBFS del silencio absoluto
hasta el piso de ruido del cable es una subida de 25 dB. Decision: anadir nivel_minimo_dbfs
reutilizando UMBRAL_RUIDO_POR_DEFECTO_DBFS (-60) del afinador, y ajustar las tres pruebas.
Coste si es erroneo: una nota tocada por debajo de -60 dBFS no marcaria ataque; es el mismo
umbral con el que el afinador ya decide que hay senal.

## Progreso
Ruling (entorno): `uv run` falla en este sandbox porque no puede escribir en ~/.cache/uv.
  Solucion: todos los despachos llevan UV_CACHE_DIR="$TMPDIR/uv-cache". Sin esto los
  implementadores caen en `python -m pytest` y reportan cifras de otra ejecucion.
  Coste si es erroneo: una variable de entorno de mas en los comandos.
Task 1: parked — el informe ejecuto `python -m pytest` en vez de `uv run`, reporto
  "164 pasan, 1 saltada" en vez de las 165/18 reales, y atribuyo al brief una cita que no
  contiene. Ruling: el codigo esta verificado independientemente por mi y por el revisor
  (165 passed, 18 skipped), y nada aguas abajo lee el informe. Corregir un archivo de
  borrador gastaria una ronda sin cambiar el producto. La causa raiz (uv sin cache) queda
  resuelta para las tareas siguientes.
  Coste si es erroneo: un informe de borrador con cifras erroneas en el historial.
Task 1: complete (commits a924c35..bd14928, review clean, 1 parked)
Task 2: Ruling: el implementador corrigio una asercion falsa del PLAN
  (`assert 41 not in en_posicion`, con el comentario "F2 tambien..." contradiciendose a si
  mismo). Verificado: Fa2 es MIDI 41, clase 5, y Do mayor = {0,2,4,5,7,9,11}, asi que SI
  pertenece. Decision: aceptar la correccion; la prueba del plan era matematicamente falsa.
  Coste si es erroneo: ninguno, la aritmetica es comprobable.
Task 2: minor (deferred): el informe afirma usar numpy en teoria.py y no lo usa (frozenset y
  comprensiones). La decision tecnica es correcta —numpy para aritmetica modular sobre 12
  elementos seria sobreingenieria— pero la frase induce a error.
Task 2: minor (deferred): no hay prueba del acotamiento a perfil.trastes cuando se pide un
  traste_maximo mayor que los trastes del instrumento. Verificado a mano que funciona.
Task 2: complete (commits bd14928..0494217, review clean)
Task 3: Ruling: `nombre_de_midi(raiz)[:-1]` se rompe con octavas negativas (MIDI 0-11 dan
  "C-1" -> "C-"). Es LOAD-BEARING: la T4 copia este patron a los arpegios y de ahi a los
  cuatro generadores. Decision: corregirlo ahora y en nucleo/musica.py como
  `nombre_de_clase(midi)`, no en escalas.py, porque es teoria musical y ahi vive ya
  nombre_de_midi; asi T4 y T5 lo reutilizan en vez de replicar el fallo.
  Coste si es erroneo: una funcion mas en musica.py.
Task 3: Ruling: se refuerza test_cada_nota_trae_sus_posiciones_en_el_mastil, que solo afirmaba
  len >= 1 y no habria detectado una regresion que devolviera una sola posicion. El brief pide
  TODAS las posiciones, y esa es la decision de diseno heredada de la etapa 1.
Task 3: minor (deferred): NOMBRES_TIPOS en escalas.py duplica el catalogo de ESCALAS; anadir
  una escala sin tocar ambos daria KeyError en vez de ValueError en espanol.
Task 3: minor (deferred): Ejercicio.clave puede contener '#' (escala_mayor_f#_0_8). Hoy nada
  la consume como identificador de URL o almacenamiento.
Task 3: fix round 1/5 (2 addressed, 0 open; commits 996b14e..c3539d6)
Task 3: complete (commits 0494217..c3539d6, review clean)
Task 4: minor (deferred): NOMBRES_TIPOS y NOMBRES_ACORDES duplican las claves de ESCALAS y
  ACORDES. Anadir una entrada a teoria.py sin tocar el catalogo de nombres da KeyError en vez
  de ValueError en espanol (reproducido por el revisor).
  Ruling: no se corrige ahora. Los generadores de T5 (intervalos, lectura) no usan ese patron
  —intervalos tiene nombre_de_intervalo, que cubre los trece valores, y lectura no tiene
  catalogo—, asi que no se propaga mas alla de estos dos sitios. Queda para el triaje final.
  Coste si es erroneo: un KeyError en vez de un mensaje claro al anadir una escala o acorde.
Task 4: complete (commits c3539d6..271a393, review clean)
Task 5: minor (deferred): con una sola nota candidata en el rango, el ejercicio repite la misma
  nota todas las veces. No contradice el brief (rechazar "rango sin pares validos" no cubre
  "una sola candidata"), pero es un ejercicio degenerado.
Task 5: minor (deferred): la reproducibilidad de la semilla depende de que numpy no cambie el
  algoritmo de default_rng entre versiones mayores. uv.lock lo fija hoy.
Task 5: complete (commits 271a393..fe6e59c, review clean)
Task 6: Ruling (LOAD-BEARING para T7): la revision midio con decaimiento realista de guitarra
  (~8,7 dB/s) que el detector de energia solo detecta una repeticion ~0,69 s despues de la
  anterior: a 90 BPM detecta 1 de 8 pulsaciones. Afecta a las CUATRO familias, no solo a notas
  repetidas: al pulsar la nota siguiente la anterior aun suena y el salto no llega a 6 dB, asi
  que el ejercicio no avanzaria nunca. Es un defecto del algoritmo que especifica el PLAN.
  Decision: el detector de energia se queda (es correcto para lo suyo, y se verifico que el
  decaimiento natural NUNCA dispara un ataque falso, algo estructuralmente garantizado porque la
  mediana del historial es siempre un valor pasado y mayor). La correccion va en T7: el evaluador
  tendra un SEGUNDO DISPARADOR, el cambio estable de nota detectada. Esa informacion ya viaja en
  ResultadoAnalisis y no cuesta nada. Un Mi que pasa a La es una nota nueva aunque la energia no
  salte; una nota sostenida no cambia de altura, asi que no introduce disparos espurios.
  Coste si es erroneo: el evaluador podria avanzar con un cambio de nota que no sea una pulsacion
  real, por ejemplo un armonico que el detector confunda. La puerta de confianza lo amortigua.
Task 6: Ruling: muestras_referencia=5 es el VALOR MAXIMO que funciona con paso 21 ms y
  refractario 50 ms; con 6 una nota sostenida marca un ataque falso. El margen del paso de
  analisis es del 19% y la degradacion es abrupta, no gradual. Decision: exponerlo como
  constante de modulo, documentar la condicion (ceil(n/2)-1)*paso < refractario, y anadir una
  prueba que la vigile. Sin eso, T12 calibraria los tres parametros por separado sin saber que
  estan acoplados.
Task 6: Ruling: se anade una prueba que DOCUMENTA la limitacion con decaimiento realista en vez
  de fingir que no existe. La prueba actual usa 262 dB/s, diez veces mas rapido que una cuerda real.
Task 6: fix round 1/5 (4 addressed, 0 open; commits 22c59a3..6109e4b)
Task 6: complete (commits fe6e59c..6109e4b, review clean)
Task 7: review NO aprobada — 2 Critical + 2 Important, todos consecuencia del cambio de diseno
  que ordene en T6 (el segundo disparador por cambio de nota).
  (a) Critical: _ultima_nota_resuelta no se limpia nunca, asi que repulsar la MISMA nota
      equivocada a nivel constante bloquea el camino B para siempre y el camino A no dispara:
      la Regla 3 (ayuda tras cinco fallos) no se dispara jamas. Justo el escenario que motivo
      anadir el camino B. Ruling: limpiar el registro con el silencio, Y anadir un disparador
      de ayuda POR TIEMPO (SEGUNDOS_PARA_AYUDA = 12), porque el proposito de la regla es
      "el alumno esta atascado, ayudale" y eso se puede detectar por tiempo aunque falle la
      deteccion de pulsaciones. Coste si es erroneo: la ayuda podria aparecer antes de lo
      necesario en una nota que cuesta; se exige al menos un fallo previo para evitarlo.
  (b) Critical: el camino B sella el instante en que TERMINA la racha de estabilidad (+42 ms)
      y el A el del ataque, asi que un ejercicio que mezcle ambos reporta 34 ms de irregularidad
      sobre una ejecucion perfecta. Ruling: el camino B registra el instante en que EMPIEZA la
      racha. Coste si es erroneo: ninguno, es el instante que la semantica ya prometia.
  (c) Important: el camino A no filtra por _ultima_nota_resuelta, asi que un hinchado de volumen
      sobre una nota ya aceptada cuenta un fallo inexistente, y con dos notas iguales una sola
      pulsacion completa las dos. Ruling: aplicar el mismo filtro al camino A. Coste si es
      erroneo: dos pulsaciones de la misma nota sin ninguna caida de nivel entre ellas quedan
      indistinguibles; es un limite fisico real y pasa a documentarse como tal.
  (d) Important: CUADROS_PARA_NOTA_ESTABLE se lee de la constante de modulo y no de self, asi que
      no es inyectable, y su equivalencia a 63 ms depende del salto de analisis sin que nada lo
      verifique. Ruling: parametro del constructor con la constante por defecto, acoplamiento
      documentado como ya hace ataques.py con MUESTRAS_REFERENCIA.
Task 7: fix round 1/5 (5 addressed, 1 rotura nueva Critical; commits 33781b7..5b0e0d6)
Task 7: Ruling: la correccion 1a (limpiar _ultima_nota_resuelta ante cualquier cuadro sin nota
  creible) introdujo un Critical: UN solo cuadro dudoso en mitad de una pulsacion la resuelve dos
  veces y cuenta un fallo fantasma contra la nota siguiente. Realista, porque el pipeline emite
  "silencio" cada vez que el detector de tono flaquea. El re-revisor demostro ademas que 1a no es
  lo que rescata la Regla 3 en el escenario que la motivo: la rescata el disparador por tiempo.
  Decision: acotar en vez de quitar. Se olvida la nota solo tras CUADROS_PARA_OLVIDAR_NOTA = 3
  cuadros seguidos sin nota creible, el mismo criterio de estabilidad del camino B. Un bache de
  21 ms no borra nada; un hueco real entre pulsaciones si.
  Coste si es erroneo: dos pulsaciones separadas por un hueco de menos de 63 ms se contarian como
  una. Es mas corto que el refractario del propio detector de ataques.
Task 7: fix round 2/5 (1 addressed, 0 open; commits 5b0e0d6..13c9dca)
Task 7: Ruling: la re-revision destapo un defecto PREEXISTENTE grave: con un detector que oscila
  (dos cuadros creibles y uno dudoso, repetido) ninguno de los dos contadores llega a tres, la
  pulsacion se pierde entera, y el disparador de ayuda por tiempo tampoco salta porque exige
  intentos >= 1. Resultado: 21 s tocando sin ninguna retroalimentacion.
  Decision: corregirlo aunque sea preexistente. La condicion `intentos >= 1` era mi eleccion y
  esta mal planteada: lo que queria evitar es que la ayuda salte mientras el alumno lee el
  ejercicio sin tocar, y eso se detecta preguntando si ha habido SENAL CREIBLE, no si se conto un
  fallo. Un alumno atascado merece ayuda aunque el software no consiga contar sus errores.
  Coste si es erroneo: la ayuda podria aparecer tras 12 s de tocar notas creibles que no son la
  pedida, que es exactamente el caso en que se quiere.
Task 7: fix round 3/5 (2 addressed, 0 open; commits 13c9dca..633b668)
Task 7: minor (deferred): tras el arreglo de la ronda 3, una nota que costo hasta 12 s y mostro
  ayuda puede quedar registrada como a_la_primera=True y fuera de notas_dificiles, porque
  IntentoNota.intentos cuenta pulsaciones RESUELTAS y en el escenario del detector que oscila no
  se resuelve ninguna. Antes del arreglo esa combinacion era imposible (ayuda_mostrada implicaba
  intentos>=2). El arreglo natural es una linea en modelo.py: a_la_primera exige no ayuda_mostrada.
  No entra en el bucle porque es minor; queda para el triaje de la revision final.
Task 7: minor (deferred): la interaccion de los dos contadores puede perder una pulsacion entera
  con un detector que oscila; la ayuda por tiempo lo compensa pero el intento no se cuenta.
Task 7: complete (commits 6109e4b..633b668, review clean, 3 fix rounds)
Task 8: Ruling: Metronomo.detener() arrastra el MISMO fallo que la etapa 1 corrigio para la
  captura: si el join vence mientras el hilo esta bloqueado en stream.write, el huerfano da otra
  vuelta y puede escribir en un stream que cerrar() ya cerro. Es LOAD-BEARING porque T9 conecta el
  metronomo a una sesion real. Decision: aplicar el mismo contador de generacion de
  servidor/sesion.py, e invertir el orden en SalidaAudio.cerrar() para que self._stream sea None
  antes de cerrar la copia local, cerrando la ventana en que un reproducir() concurrente ve un
  stream que se esta cerrando.
  Coste si es erroneo: una comprobacion mas por pulso del metronomo.
Task 8: Ruling: se pone cota superior al tempo (300 ppm). Sin tope, por encima de ~2000 el
  intervalo baja de los 30 ms que dura el propio click y la escritura bloqueante se lo come.
Task 8: fix round 1/5 (3 addressed, 0 open; commits 00ed77f..2622bc3)
Task 8: desviacion aceptada: doble chequeo de generacion en _trabajar (antes y despues de
  reproducir). El re-revisor quito el segundo y la prueba del huerfano fallo: el primero se evalua
  antes de entrar en la llamada bloqueante y no puede interceptar lo que ocurra dentro.
Task 8: desviacion aceptada: tempo=600 -> 300 en dos pruebas del brief, con las esperas duplicadas.
  Verificado que preserva la proporcion y no relaja ninguna asercion.
Task 8: complete (commits 633b668..2622bc3, review clean)
Task 9: el agente implementador se corto por un limite de uso de la API DESPUES de commitear y
  antes de terminar su informe. Verificado por el controlador: commit 6a71cf6, arbol limpio,
  320 passed / 18 skipped, 33 pruebas de sesion+observadores+practica en verde. Se anadio una nota
  de estado al informe para que el revisor no lo contara como omision.
Task 9: desviacion aceptada: try/except ValueError alrededor de Metronomo(...) para que un tempo
  por encima de 300 ppm no reviente iniciar(), tratandolo como "no hay metronomo". Lo pedia el
  propio texto de la tarea.
Task 9: minor (deferred): esa rama del try/except no tiene prueba permanente. El revisor la
  verifico a mano pero queda como codigo sin red.
Task 9: minor (deferred): _observar lee self._evaluador sin lock; es seguro por el GIL y el
  null-check, pero no esta documentado por que, a diferencia de como Sesion documenta sus candados.
Task 9: minor (deferred): CapturaFalsa y StreamSalidaFalso duplicados en tres archivos de pruebas.
Task 9: complete (commits 2622bc3..6a71cf6, review clean)
Task 10: desviacion aceptada: construir_aplicacion mantiene la tupla de dos valores y expone la
  practica por app.state.practica, porque una tupla de tres rompia tests/test_arranque.py, que la
  tarea prohibia tocar. Verificado que main() si detiene la practica en el finally.
Task 10: minor (deferred, USER-FACING): la descripcion del modulo "ejercicios" en /api/modulos va
  sin tildes ("correccion", "mastil") mientras la del afinador si las tiene. Heredado del plan.
Task 10: minor (deferred): el informe cita una seccion "Lo que ya existe" del brief que no existe;
  el argumento de fondo es correcto pero la atribucion textual no.
Task 10: complete (commits 6a71cf6..6abe24e, review clean)
Task 11: Ruling: el implementador replico el umbral de tres intentos como constante local en
  Informe.tsx porque el servidor no publicaba notas_dificiles. Viola la restriccion global de que
  la interfaz no calcula nada musical, y es la misma clase de defecto que en la etapa 1 obligo a
  corregir una pantalla que recalculaba la tolerancia de afinacion. Decision: publicar
  notas_dificiles desde ResultadoEjercicio.a_dict() —la propiedad ya existia en el nucleo, solo
  faltaba serializarla— y que la interfaz la consuma. Se corrige antes de la revision porque es
  una violacion de restriccion global, no una observacion.
  Coste si es erroneo: una clave mas en el mensaje del WebSocket.
Task 11: minor (deferred): el array `parametros` de cada familia no se usa para decidir que inputs
  muestra el configurador; siempre muestra tempo y rango de trastes, que el brief llama comunes.
  Derivarlos del array seria un rediseno del configurador, fuera del alcance de esta tarea.
Task 11: minor (deferred): el WebSocket de ejercicios sigue emitiendo a 30 Hz mientras el alumno
  lee el informe, porque el servidor no comprueba `completado`. Mismo patron que /ws/notas desde la
  etapa 1; el brief pedia copiarlo, no optimizarlo.
Task 11: minor (deferred): el fixture de la prueba del informe manda ejercicio=null junto a
  completado=true, algo que el servidor real nunca produce. No afecta al componente.
Task 11: minor (deferred): /api/ejercicios/generar existe en el servidor y la interfaz no lo
  consume. Era la previsualizacion del ejercicio antes de empezarlo.
Task 11: complete (commits 6abe24e..0048ed4, review clean, 1 correccion previa a la revision)

- Task 12: revision despachada sobre 0048ed4..756b936 (paquete en review-task-12.md).
Task 12: complete (commits 756b936, d46f174; revision devolvio 1 Important y 2 Minor, los tres corregidos; 331 passed / 30 skipped, interfaz 40 passed, build ok)

Ruling: el parrafo del README sobre el limite del detector se reescribio contra el docstring de EvaluadorEjercicio, no contra mi instruccion original al implementador — mi texto atribuia al camino B (cambio de nota) una compensacion que no puede dar cuando la nota repetida es la misma. Coste si me equivoco: el README describiria mal por que el alumno no se atasca.

## Revision final de la rama (20 commits, a924c35..d46f174)
Veredicto: NO lista para fusionar. 4 Critical, 10 Important, 9 Minor.
Verifique los cuatro Critical ejecutando el codigo antes de aceptarlos:
- C1: repique de la misma nota con caida de 27 dB -> indice 1 de 2 (atascado). lectura 103/500 y intervalo 116/500 ejercicios traen nota repetida adyacente.
- C2: generar_intervalo no acepta el kwarg `tipo` que manda el Configurador -> 500 en la familia Intervalos.
- C3: tono_de_midi solo se llama desde tests; referencia_midi no tiene ningun consumidor.
- C4: tras acertar una nota, 13 s de silencio SIN TOCAR NADA -> ayuda True.

Ruling: parto la ola de arreglos en dos despachos disjuntos y secuenciales (A = nucleo/servidor/tests, B = interfaz) en vez de uno solo. El volumen no cabe en un despacho con calidad, y los dos conjuntos de archivos no se solapan. Coste si me equivoco: dos revisiones acotadas en vez de una.
Ruling: C1 se arregla en los generadores (prohibir duplicados adyacentes), no en el filtro de _resolver, que se endurecio en tres rondas. Coste si me equivoco: el limite del evaluador sigue existiendo, solo deja de ser alcanzable por generacion.
Ruling: el parrafo del README y el docstring del evaluador se reescriben otra vez — el revisor final demostro que mi correccion de la Task 12 seguia siendo falsa (la caida de nivel NO libera el filtro, porque compara nombres de nota). Coste si me equivoco: la documentacion volveria a prometer una mitigacion inexistente.

- Ola A despachada (nucleo + servidor + tests): brief en fix-final-a-brief.md
- Ola A completa: a7cd2bd, b969dc8, acbe762, a34db68 (359 passed / 30 skipped; +28 pruebas). DONE_WITH_CONCERNS con 5 preocupaciones, informe en fix-final-a-report.md. Destapo y arreglo un defecto no listado: escrituras concurrentes en SalidaAudio.
- Ola B despachada (solo interfaz): brief en fix-final-b-brief.md
Ruling: acepto que "metronomo" siga siendo true mientras esta pausado y que la pausa viaje en el campo nuevo "metronomo_pausado" — cambiar el significado de un campo que la interfaz ya lee es peor que añadir uno. Coste si me equivoco: un campo mas en el payload.
Ruling pendiente de decidir tras la ola B: la pausa del metronomo depende de que alguien sondee estado(), porque Sesion publica un unico silencio y calla. Con la pantalla cerrada y el cable desenchufado el metronomo seguiria sonando. Arreglarlo de raiz toca el latch silencio_publicado de Sesion, que tiene su razon documentada.
- Ola B completa: 09d8a55 (interfaz 61 passed, build y lint limpios). DONE_WITH_CONCERNS, 5 preocupaciones, informe en fix-final-b-report.md.
- Arreglo mio del defecto que destapo la ola B: c45ac06 — perfil_clave no viajaba, todos los ejercicios salian en guitarra_estandar aunque el usuario tuviera bajo o Drop D. Ahora la sesion de practica hereda el perfil activo. 361 passed / 30 skipped.
- Re-revision acotada despachada sobre d46f174..c45ac06.

Ruling: la preocupacion 1 de la ola A (la pausa del metronomo depende de que alguien sondee estado()) queda aparcada. Con la pestaña cerrada nadie sondea, pero entonces el ejercicio ya esta desatendido: cerrar la pestaña nunca ha detenido un ejercicio en este diseño, ni antes ni ahora. Tocar el latch silencio_publicado de Sesion para esto arriesga la etapa 1 por un caso en el que el usuario ya no esta mirando. Coste si me equivoco: el metronomo suena a solas hasta que se detiene el ejercicio.
Ruling: aparco tres preocupaciones de la ola B para la etapa 2b, todas de la misma familia — el endpoint de familias publica los NOMBRES de los parametros pero no su tipo, valores admisibles, rango ni defecto, asi que la interfaz aun escribe la lista de direcciones, no distingue "sin salida de audio" de "no quise metronomo" (falta metronomo_pedido) y pinta en tenue todas las posiciones validas de una nota acertada en vez de la que se toco (IntentoNota no publica la posicion resuelta). Coste si me equivoco: la interfaz sigue teniendo tres decisiones que no le corresponden.

## Re-revision de las olas de arreglos (d46f174..c45ac06)
Los cuatro Critical cerrados y verificados con la medida repetida (0/500 repetidos, ayuda False tras 13 s sin tocar, tono una vez por nota, las cuatro familias arrancan). Devolvio 5 Important nuevos y 9 Minor.
- 33a356d: cierro yo I1..I5 y cinco minors de Python. 370 passed / 30 skipped, ruff limpio.
  - I1 reproducido antes del arreglo: 147 ms de onset fabricado. Mi primera prueba NO reproducia el fallo (la nota nueva generaba su propio ataque, que sobrescribia el viejo); la rehice con la nota nueva entrando sin salto de nivel (ligado), que es el caso en que resuelve el camino B.
- Interfaz despachada aparte: tres defectos (cuerdas de otros perfiles, claveDeTipos adivinando, aviso de metronomo ambiguo).
Ruling: I2 se resuelve devolviendo UNA nota cuando solo hay una candidata, no `repeticiones` copias ni un ValueError. Un ejercicio de una nota se puede terminar; el error obligaria al usuario a adivinar que su rango de trastes era el problema. Coste si me equivoco: un ejercicio mas corto de lo pedido en un caso extremo.
Ruling: publico dos campos nuevos del servidor (metronomo_pedido, GET /api/ejercicios/instrumento) en vez de dejar que la interfaz deduzca. Es la cuarta vez en el proyecto que la interfaz calcula lo que el nucleo decide; cortarlo en la fuente es mas barato que corregirlo otra vez. Coste si me equivoco: un endpoint y un campo de mas.
Ruling: los fallos de observador pasan de print a logging. Coste si me equivoco: con logging sin configurar los avisos van a stderr por el handler de ultimo recurso, igual de visibles en la terminal.
