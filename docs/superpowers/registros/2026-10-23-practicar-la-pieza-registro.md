# SDD ledger — plan: docs/superpowers/plans/2026-10-23-practicar-la-pieza.md

Spec: docs/superpowers/specs/2026-10-23-practicar-la-pieza-design.md (legible, autoridad vinculante)
Rama: etapa-3c-practicar, base main = 5e6a418
Repo normal (no worktree), sin remoto configurado.

## Escaneo previo

### Pares de tareas que comparten archivo o interfaz

| A | B | Produce / consume | Hallazgo |
|---|---|---|---|
| T1 | T3 | compas_en, pulsos_del_compas, pulsos_por_compas, total_de_compases | encaja; firmas idénticas |
| T1 | T7 | compases_de_la_seccion → secciones_en_compases | encaja |
| T2 | T3 | SeguidorPieza(factor_tempo=) al final de la firma | encaja |
| T2 | T4 | olvidar_tramo + propiedad duracion_s | **T4 modifica seguimiento.py y su lista de Files no lo decía** → R6 |
| T3 | T4 | _plan, _compases_del_tramo, _segundos | encaja |
| T3 | T5 | EstadoEstudio (+tramo_terminado), el reloj | **defecto del reloj** → R1 |
| T4 | T5 | cerrar_repeticion ← _dar_la_vuelta | encaja tras R4 |
| T4 | T6 | proporcion_limpia, InformeDePasada | encaja |
| T5 | T7 | _ultima_vuelta ← ultima_vuelta | **T7 modifica estudio.py y su lista de Files no lo decía** → R6 |
| T6 | T7 | HistorialDeEstudio.anotar / factor_sugerido | encaja |
| T7 | T8 | servidor/piezas.py, tests/test_app_estudio.py, _ajustar_click desde _instantanea | encaja |
| T7 | T9 | el dict del WS ← EstadoEstudio TS | encaja (click_sonando lo añade T8, y T9 va después) |
| T7 | T10 | secciones_en_compases ← SeccionEnCompases | encaja tras R5 |
| T9 | T10 | tiposEstudio.ts, Carril.tsx, estilos.css | encaja; T10 no redefine nada de T9 |
| T9 | T11 | Informe/Historial TS, Carril.tsx, estilos.css | encaja |
| T10 | T11 | useCarril.ts (acciones vs limpieza del efecto) | encaja; tocan trozos distintos |
| T12 | — | modelo.py y README, nadie más los toca | encaja |

### Cada tarea contra sí misma

| Tarea | ¿Las pruebas que especifica cuadran con el código que especifica? |
|---|---|
| T1 | Sí. Verificado a mano: 7/8 → 3,5 pulsos; nueve pulsos en 4/4 → 3 compases; sección 0 de (0, 8) → (1,2); mensajes contienen el número que la prueba busca. |
| T2 | Sí. 120 ms al 50 % cae dentro de 160 ms; E2 = midi 40, que es lo que `pieza_de` produce; olvidar_tramo(0,9–1,5) deja el índice 0. |
| T3 | **No**: `compas_en_curso` al final de un tramo daba ultimo+1 (intervalo medio abierto) → R2. Y el reloj → R1. Lo demás cuadra. |
| T4 | Sí, con R4: `cerrar_repeticion` tenía que devolver la vuelta sola, no el acumulado. |
| T5 | **No**: la prueba de la pausa exigía que reanudar no saltara, y con una puerta absoluta saltaba → R1. La de "no se cobra durante la cuenta atrás" colocaba el reloj, que cancela la cuenta → reescrita con cuadros. |
| T6 | Sí. Verificado: dos limpias suben 0,05; la racha se consume; los acordes no entran en los peores. |
| T7 | Sí tras R1 y R6. |
| T8 | Sí. El patrón de inyección de `SalidaAudio` es el de `SesionPractica`, que ya existe. |
| T9 | Sí. |
| T10 | Sí tras R5: ya no recalcula compases en TypeScript. |
| T11 | Sí, y el paso de romper dice de antemano que `keepalive` no es comprobable en jsdom, en vez de fingir una prueba. |
| T12 | Sí, es documentación. |

### Nada que el plan mande y la rúbrica trate como defecto

Revisado: ninguna prueba del plan afirma algo trivialmente cierto, ningún bloque de lógica se duplica literalmente, y los tres sitios donde el plan dice "si esta rotura no tira nada, falta una prueba" son lo contrario de una prueba que no puede fallar.

## Rulings del escaneo previo

Ruling: el reloj de `SesionDeEstudio` se parte en dos puertas, `colocar_en(absoluto)` y `avanzar(delta)` — con una sola puerta absoluta, el llamador sigue contando tiempo durante la pausa y al reanudar el cabezal salta el tamaño de la pausa; la prueba de la pausa que yo mismo escribí lo demostraba — si me equivoco, cuesta un método de más y reescribir las llamadas del reloj en T3, T5 y T7.
Ruling: `compas_en_curso` se acota al `ultimo_compas` del plan — los pulsos de un compás son un intervalo medio abierto, así que el reloj parado al final del compás 3 cae en el 4 y un bucle del 2 al 3 decía "compás 4" — si me equivoco, al final de la pieza entera se ve `total` en vez de `total+1`, que sigue siendo lo correcto.
Ruling: `colocar_en` cancela la cuenta atrás — colocar el cabezal es una orden sobre dónde está ahora, y hacerla esperar a una cuenta atrás sería obedecerla a medias — si me equivoco, saltar de compás a mitad de una cuenta atrás se come la cuenta de esa vuelta.
Ruling: `cerrar_repeticion` devuelve el informe de SOLO esa vuelta y el acumulado se queda en `informe` — el historial tiene que juzgar la vuelta que acaba de pasar, no la suma de las ocho anteriores, o "ya te sale" llegaría siempre tarde — si me equivoco, el tempo automático sube con retraso.
Ruling: las secciones viajan del servidor ya convertidas en rangos de compases — la conversión es del núcleo, y una copia de la fórmula en TypeScript habría que arreglarla dos veces el día que el compás variable se arregle — si me equivoco, la interfaz hace una petición con un campo que no usa.
Ruling: las listas de Files de T4 y T7 se amplían (T4 toca `seguimiento.py` para la propiedad `duracion_s`; T7 toca `estudio.py` para `ultima_vuelta`) — el plan ya mandaba esos cambios en su texto pero no los declaraba, y un revisor habría marcado el archivo como fuera de alcance — si me equivoco, no cuesta nada: son dos líneas de cabecera.
Ruling: el historial se guarda por `pieza.nombre` — dos canciones distintas que se llamen igual comparten historial; es un empate declarado y el precio es un "fallas el 19" de otra canción, no un dato perdido — si me equivoco, hay que llavearlo por nombre y perfil.

## Tareas

Task 1: complete (commits dc72d21..3e2cb08, review clean — spec ✅, calidad aprobada)
Task 1: minor (deferred): una seccion que empieza a mitad de compas deja el ultimo compas de la anterior corto; sin prueba que lo fije.
Task 1: minor (deferred): `compas_en` no acota por arriba; un pulso mas alla del final da un compas mayor que `total_de_compases`. Lo cubre el acotado de `EstadoEstudio` (ruling R2), pero el modulo no lo dice.
Task 1: minor (deferred): `pulsos_del_compas` y `total_de_compases` solo tienen prueba en 4/4; en 7/8 el segundo compas seria (3.5, 7.0).

Task 2: implementada en 4d8f432 (suite completa 826 passed, 30 skipped). El implementador cazo por su cuenta una prueba que faltaba: la mutacion `< hasta_s` -> `<= hasta_s` no tiraba ninguna, y escribio test_olvidar_un_tramo_no_incluye_su_extremo_final. El revisor lo verifico parcheando el metodo en memoria: cae esa y solo esa, por AssertionError.
Task 2: el ⚠️ del revisor sobre `duracion_s` y su prueba (fuera del brief) queda resuelto: se lo pedi yo en el despacho para que la tarea 4 no tuviera que reabrir seguimiento.py. No es un hueco.
Ruling: los menores 2 (factor_tempo como property de solo lectura) y 3 (la guarda no rechaza NaN) entran en la ronda de arreglos con el Important, en vez de diferirse — son de una linea, el propio revisor los llama trampas plausibles, y cuatro tareas que consumen ese atributo vienen detras; si me equivoco, cuesta una ronda de arreglos que podria haber esperado a la revision final.
Task 2: minor (deferred): `olvidar_tramo` no se queja de un intervalo invertido (desde_s > hasta_s es un no-op silencioso).
Task 2: minor (deferred): la linea de `_ventana_reclamo_pronto_s` quedo en 100 columnas; ruff format ya marcaba este archivo antes del cambio, asi que no es regresion.
Task 2: fix round 1/5 despachada (Important 1: el docstring de la clase quedo describiendo las constantes sin factor y sin nombrar los tres miembros nuevos; + menores 2 y 3)
Task 2: fix round 1/5 (3 addressed, 0 open; commits 4d8f432..7fbc306)
Task 2: complete (commits 3e2cb08..7fbc306, re-review limpia)

Task 3: implementada en 157f072 (DONE_WITH_CONCERNS; suite 847 passed, 30 skipped). El workspace .superpowers/ esta ignorado por .gitignore:1, asi que el informe no entra en el commit: es lo correcto, no un olvido.
Ruling: en una pieza sin notas, `validar_plan` devuelve el plan TAL CUAL (ultimo_compas sigue None) en vez del `replace(plan, ultimo_compas=0)` que mandaba mi plan — ese 0 lo rechaza `PlanDePasada.__post_init__` por ir antes del primer compas, asi que mi texto era imposible de cumplir; `EstadoEstudio` sigue publicando 0 con `or 0`, y los tres consumidores posteriores (_fin_s, _compases_del_tramo y el `dentro` de cambiar_plan) ya tratan el caso vacio aparte, asi que None nunca les llega — si me equivoco, lo paga la tarea 5 con un None donde esperaba un entero, y se arregla permitiendo el 0 en el plan solo para la pieza vacia.
Task 3: tres defectos MIOS en el brief, cazados por el paso de romper el codigo: quitar el `/ factor_tempo` de `_segundos`, quitar el chequeo `primer_compas > total` y no pasar `factor_tempo` al seguidor NO tiraban ninguna prueba de las que yo habia escrito. El implementador escribio las tres que faltaban. Van doce pruebas que no podian fallar entre las etapas 3b y 3c, y nueve de ellas salieron de mis briefs.
Ruling: ante el borde de la pieza vacia elijo el arreglo DE FONDO y no el cosmetico — `__post_init__` admite `ultimo_compas == 0` como caso "pieza sin compases", `validar_plan` lo produce solo ahi y lo rechaza si la pieza si tiene compases, y asi el tipo publicado es un int de verdad; el motivo es que cuatro tareas haran aritmetica con `plan.ultimo_compas` y un None ahi es un TypeError en una pieza sin notas — si me equivoco, cuesta volver al None documentado y acotar en cada consumidor. Revierte mi ruling anterior de la tarea 3.
Ruling: el retroceso del cabezal con olvido (saltar atras a un compas ya tocado y poder volver a cobrar sus notas) lo posee `saltar_al_compas` en la tarea 5, no `colocar_en` — `colocar_en` es la puerta del reloj y nada mas, y ponerle el olvido dentro haria que cada mirada del servidor sin audio descobrara notas; si me equivoco, volver a tocar un compas al que has saltado no cuenta, y se arregla moviendo el `olvidar_tramo` una capa mas abajo. LO LLEVO AL DESPACHO DE LA TAREA 5 con prueba obligatoria.
Task 3: fix round 1/5 despachada (3 Important: el entero de la pieza vacia, los dos a_dict con valores distintos, dos ramas de validacion sin prueba; + 5 menores, entre ellos el `is not None` que el arreglo de fondo vuelve necesario)
Task 3: fix round 1/5 (8 addressed, 0 open; commits 157f072..2660c2f). El re-revisor mutó diez cosas en una copia de trabajo y cada mutación tiró al menos una prueba.
Task 3: la desviacion del implementador (`max(1, min(compas, ultimo_compas))`) es correcta y necesaria: con ultimo_compas=0 un `min` a secas dejaba el cabezal en el compas 0 de una pieza vacia. Filo de MI arreglo de fondo que no vi.
Task 3: complete (commits 7fbc306..2660c2f, re-review limpia)

Task 4: implementada en 15eb439 (suite 872 passed, 30 skipped). Dos pruebas mas que no podian fallar: la que mi brief anunciaba (min -> acertadas) y la simetrica que no preveia (min -> a_tiempo). El implementador escribio las dos. Y declaro un mutante equivalente con argumento en vez de taparlo con una prueba falsa; el revisor lo confirmo y lo reforzo.
Ruling: `InformeDePasada` gana un campo `repeticiones` y `proporcion_limpia` divide por `medibles * repeticiones` — mi brief dejaba una funcion que promete "0 a 1" devolviendo 2,0 a la segunda vuelta del bucle y 3,0 a la tercera (medido por el revisor sobre la sesion real), y es la funcion que decidira el tempo: un `>= 0.9` se dispara igual con 3,0 y un `< 0.7` no bajaria el tempo nunca mas; si me equivoco, cuesta un campo de mas en el informe y la interfaz lo ignora.
Ruling: las notas limpias se cuentan POR NOTA (`acertada and clasificacion == "a_tiempo"`) y no con el `min(acertadas, a_tiempo)` por compas que mandaba mi brief — el min inventa notas limpias que no existieron: medido 0,5 donde la verdad es 0,0, con una nota acertada-pero-tarde y otra a-tiempo-pero-de-otra-altura, y en una pieza real los dos fallos van juntos nota a nota, asi que el sesgo es sistematico al alza; si me equivoco, el informe trae un campo `limpias` que nadie usa.
Task 4: minor (cerrada en la ronda): test_...se_serializa_con_el_desfase_redondeado... no probaba el redondeo (quitar el round no tiraba nada). Quinceava prueba que no podia fallar.
Task 4: fix round 1/5 despachada (2 Important del brief + 4 menores, entre ellos cachear el reparto por compas porque la tarea 5 publica a 30 Hz)
Task 4: fix round 1/5 (6 addressed, 0 open; commits 15eb439..86fea4a)
Task 4: minor (deferred): la guarda de la clasificacion no tiene prueba que pueda fallar (sustituirla por `is not None` deja 47 passed).
Task 4: minor (deferred): la clave "limpias" del a_dict no tiene asercion; las pruebas leen el atributo, no el dict.
Task 4: complete (commits 2660c2f..86fea4a, re-review limpia)
Ruling: `cerrar_repeticion` gana un parametro `cuenta_como_vuelta=True`, y `cambiar_plan` y `saltar_al_compas` lo llaman con False — las dos vuelcan lo tocado al informe pero NO son una vuelta del bucle, y con el contador de `repeticiones` que acabamos de añadir inflarian el denominador de `proporcion_limpia` y hundirian la proporcion cada vez que el usuario mueve el tempo; si me equivoco, un cambio de tempo a mitad de pasada cuenta como repeticion y la proporcion sale baja. LO LLEVO AL DESPACHO DE LA TAREA 5 con prueba obligatoria.

Task 5: implementada en 4bf4be6 + fe02109 (suite 907 passed, 30 skipped; 78 pruebas en test_estudio.py). El implementador midio 32 roturas una a una y declaro los mutantes equivalentes en vez de taparlos. El revisor verifico cuatro por su cuenta en una copia aparte: el camino con audio llamando avanzar_a tira 20 pruebas, 11 de ellas de tareas anteriores.
Task 5: defecto MIO en el brief, confirmado por el revisor con un argumento mejor: la prueba de "la nota en la frontera del bucle" que pedia NO PUEDE matar su rotura, porque `olvidar_tramo` y `avanzar_a` tocan conjuntos de estado disjuntos y el orden es inobservable en un solo hilo. El orden si importa, pero por concurrencia, y eso no se puede probar sin esperas reales (prohibidas). Los dos espias sobre la secuencia de llamadas son la herramienta correcta y el acoplamiento es el precio.
Ruling: `_al_dia` solo da la vuelta al bucle cuando el reloj ha CRUZADO el final avanzando, no cuando el llamador lo coloco mas alla — `saltar_al_compas` contaba vuelta por la puerta de atras y el revisor lo midio: tres saltos seguidos hundian `proporcion_limpia` de 1,0 a 0,25 mientras el cabezal rebotaba al primer compas del tramo y nunca llegaba al pedido; si me equivoco, colocar el cabezal al final exacto de un bucle ya no da la vuelta y hay que esperar al siguiente avance.
Ruling: `saltar_al_compas` valida contra el TRAMO y no solo contra la pieza, y rechaza un compas de fuera nombrando los dos extremos — el tramo es lo que el usuario eligio y saltar fuera es cambiar el plan, no saltar; si me equivoco, la interfaz tiene que mandar el plan antes del salto, y eso LO LLEVO AL DESPACHO DE LAS TAREAS DE INTERFAZ: un clic en un compas fuera del rango del bucle tiene que cambiar el rango primero.
Task 5: fix round 1/5 despachada (2 Important medidos: la vuelta fantasma de saltar_al_compas y la linea del reanudar con audio sin prueba; + 2 menores)
Task 5: fix round 1/5 (4 addressed, 0 open; commits fe02109..71c0d63). El re-revisor midio las seis roturas en una copia aparte y las cifras coinciden; ademas comprobo que las pruebas reescritas para usar la otra puerta del reloj no se debilitaron (la mutacion de `avanzar` tira 13).
Task 5: complete (commits 86fea4a..71c0d63, re-review limpia)
Ruling: `peores_compases` cuenta un compas como fallado con `limpias < notas_medibles` y no con `acertadas < notas_medibles` — es el mismo criterio que `proporcion_limpia` tras el arreglo de la tarea 4, y un compas que tocas bien pero tarde es un compas que merece machacarse; si me equivoco, el ranking ignora los fallos de ritmo y el usuario no sabe donde practicar el tempo.

Task 6: implementada en b95edce + aca8da4 (suite 940 passed, 30 skipped; 111 pruebas en test_estudio.py). 38 mutantes medidos; de los cuatro vivos con las pruebas del brief, tres eran huecos reales (el round al bajar el factor, el orden por proporcion antes que por fallos, y falladas/contadas simetricos con 1/1) y uno equivalente, declarado.
Task 6: decimosexta prueba que no podia fallar, cazada por el revisor y cerrada por el fondo: se quito del filtro de `peores_compases` una condicion que nada puede ejercer y la prueba se reescribio para medir que un compas sin notas medibles no aparece entre los peores. El re-revisor lo comprobo con 3000 historiales aleatorios: 0 discrepancias con la version anterior.
Task 6: complete (commits 71c0d63..aca8da4, re-review limpia)

Task 7: implementada en 7137bb6 (DONE_WITH_CONCERNS; suite 972 passed, 30 skipped; 41 mutantes, 38 muertos, 3 supervivientes declarados, 8 pruebas nuevas nacidas del paso 5). test_app_carril.py y test_sesion_carril.py verdes SIN tocarlas.
Task 7: defecto MIO en el brief, bien juzgado por el implementador y confirmado por el revisor: mis pruebas arrancaban con POST /api/piezas/iniciar {"pieza": {...}} y ese endpoint NO acepta esa forma a proposito (solo ejercicio del catalogo o cancion del disco), porque aceptar una Pieza del cliente seria creerle las notas y el perfil con los que el carril tiene que comprobar la afinacion (spec 3a §5). No existe deserializador en el arbol: las pruebas del brief eran imposibles. Resuelto sin abrir la puerta.
Task 7: el revisor midio el candado que pregunte: reconstruir el seguidor bajo candado cuesta 0,26 ms con 200 notas, 2,1 ms con 2000 y 8,3 ms con 8000, una vez por vuelta y solo con tempo automatico. No pierde deteccion de ataques. Anotado para la 3d.
Ruling: el tempo automatico SIN bucle ya no llama a `cambiar_plan`: publica `factor_sugerido` en el estado y la interfaz lo aplica al empezar la pasada siguiente — el fragmento de mi brief hacia que al acabar un tramo sin bucle el carril se reiniciara solo (medido: instante_s 8.0 -> 0.0, completado True -> False) porque `cambiar_plan` recoloca el cabezal por contrato; con bucle se sigue aplicando en el acto, que es donde el bucle ya esta recolocando; si me equivoco, el tempo no sube solo en las pasadas enteras y hace falta un clic del usuario. LO LLEVO A LAS TAREAS DE INTERFAZ: tienen que consumir `factor_sugerido`.
Task 7: decimoseptima prueba que no podia fallar, y la mandaba mi brief: test_tras_la_cuenta_atras_el_cabezal_no_salta_hacia_delante sobrevive al mutante que yo mismo le escribi, porque nunca deja pasar tiempo y TECHO_TRAMO_S acota cada mirada a 0,1 s. Rehecha con el reloj inyectado.
Aclaracion para los proximos despachos: la restriccion del codigo es SIN TILDES, no ASCII puro. `señal`, `dueña`, `§` estan en el resto del arbol y se quedan. Se lo di mal en varios despachos.
Task 7: fix round 1/5 despachada (3 Important reproducidos + 3 menores)

## ESTADO AL CORTARSE LA SESION (limite de uso)

Tareas 1-6 COMPLETAS y revisadas (main=5e6a418, rama etapa-3c-practicar, ultimo commit revisado: 7137bb6).
Tarea 7: implementada y revisada; ronda de arreglos 1/5 DESPACHADA Y EN VUELO (agente a656ad9ee2988720c, 3 Important + 3 menores). Al reanudar: pedirle el estado, o mirar `git log` por si ya commiteo; despues toca el re-review ACOTADO del diff de arreglos (7137bb6..HEAD).
Pendientes: tarea 8 (click de metronomo), 9/10/11 (interfaz), 12 (documentacion), revision final de rama, y luego finishing-a-development-branch.
Cosas que tienen que viajar a las tareas de interfaz (9/10/11):
  - consumir `factor_sugerido` del estado y aplicarlo al empezar la pasada siguiente (tempo automatico sin bucle)
  - un clic en un compas FUERA del rango del bucle tiene que cambiar el rango antes de saltar: `saltar_al_compas` rechaza lo de fuera del tramo
  - `secciones_en_compases` viene ya convertido del servidor; la interfaz no convierte pulsos en compases
Aclaracion para todos los despachos: la restriccion es SIN TILDES, no ASCII puro.
Task 7: fix round 1/5 entregada en 7181d76 (suite 975 passed, 30 skipped; 10 mutantes, 9 muertos, 1 superviviente declarado). La prueba de la cuenta atras ahora CAE con los dos mutantes del espejo. La cobertura HTTP de secciones_en_compases en /iniciar NO es alcanzable: las cuatro familias del catalogo dan 0 secciones.
Task 7: hallazgo nuevo del implementador, NO tocado por el: en la frontera de un compas y tras un cambio de factor, `compas_en_curso` lee uno menos por el redondeo de `_pulsos` (4 / 0,95 * 0,95 = 3,9999999999999996). Es `SesionDeEstudio.estado`, nucleo. PENDIENTE DE ARREGLO.
NOTA DE ATRIBUCION: a partir de 2026-10-28 el trailer cambia a `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` (sin "(1M context)"). La linea Claude-Session no cambia.
Task 7: re-review de la ronda 1 limpia (6 addressed, el sexto como "declarado, no alcanzable"; mutantes medidos: espejo 7, regresion 3a 4, los tres de adopcion 1 cada uno).
Task 7: ronda 2 (remates) en 3b0bfcd, suite 979 passed / 30 skipped. La sugerencia se limpia en los tres sitios donde empieza una pasada nueva; el redondeo arreglado en `_pulsos`, en su origen.
Task 7: DECIMOCTAVA prueba que no podia fallar, y salio de MI instruccion de esta ronda: redondear los pulsos a 2 decimales en vez de 9 dejaba las 239 pasando, asi que el arreglo estaba fijado por abajo pero no por arriba y nada impedia "arreglarlo" con una precision gruesa que dibujaria el cabezal a saltitos. El implementador escribio test_el_redondeo_de_los_pulsos_no_se_come_precision_que_se_vea.
Task 7: fix round 2/5 (3 addressed, 0 open; commits 7181d76..3b0bfcd). El re-revisor confirmo que el redondeo esta en el origen y no es un parche en el consumidor, y midio que la prueba de la precision cae desde 1 hasta 5 decimales.
Task 7: complete (commits aca8da4..3b0bfcd, re-review limpia)

Task 8: implementada en 596142c + 4aa2e8a + 4162ead (suite 999 passed, 30 skipped, corrida dos veces). 24 + 6 + 6 mutantes medidos.
Task 8: fallo GRAVE de mi brief, encontrado por el implementador: mi codigo nunca llamaba a `SalidaAudio.abrir()`, asi que `Metronomo.iniciar()` habria devuelto False siempre con una salida real y el click NO HABRIA SONADO NUNCA en produccion; y mi propio doble de prueba (una clase inventada con activa=True) lo habria tapado. Una prueba verde sobre algo que no funciona. Arreglado, y el doble pasa a ser una SalidaAudio real con el stream inyectado mas un espia que LEE `activa` en vez de fingirla.
Ruling: el click se pausa tambien con la pausa del USUARIO y se detiene al terminar el tramo sin bucle — mi brief solo lo pausaba por falta de senal, y un click marcando el compas con el carril en pausa es lo contrario de lo que pide la spec de la 2a: si la musica no avanza, el click no marca nada; si me equivoco, el usuario pierde la referencia de pulso al reanudar y hay que volver a arrancarlo antes.
Task 8: el revisor corrio la suite COMPLETA con el dispositivo de audio sabotado (centinela que revienta _abrir_stream_real y sounddevice): no se abre audio real en ningun sitio. Y encontro una prueba inestable preexistente (carrera con el reloj de pared), que se arreglo pasandola al reloj inyectado.
Task 8: minor (deferred): `click_sonando` sale de `.sonando` pero ninguna prueba fija esa parte; hoy es equivalente, y la prueba que lo cerraria tiene que matar el hilo por su cuenta.
Task 8: fix rounds 1 y 2 (4 y 4 addressed, 0 open). complete (commits 3b0bfcd..4162ead, re-review limpia)

Task 9: implementada en 5fa3638 + 66d77b1 + beb655d (190 pruebas de interfaz, build y lint limpios; 27 + 3 roturas medidas).
Task 9: DECIMONOVENA prueba que no podia fallar, y esta la pedi YO explicitamente: para vigilar la cancelacion del arrastre pedi "soltar fuera y comprobar que el clic siguiente salta sin marcar rango", y pasa en las CINCO roturas porque el pointerdown del clic siguiente pisa el arrastre viejo. El implementador lo midio y escribio dos que si caen, sobre consecuencias que yo no habia visto (pasar el puntero sin pulsar seguia marcando; un pointerup suelto marcaba rango desde el compas viejo).
Task 9: dato que el implementador dio mal y el revisor corrigio: jest-dom SI esta instalado, solo le falta el setupFiles en vite.config.ts. La decision de no usarlo sigue siendo correcta.
Task 9: limite declarado, NO arreglado: con touch-action none y la captura implicita del puntero tactil, el arrastre no marcara rango en pantalla tactil. El usuario practica en un MacBook.
Task 9: la prop del clic se llama `alPedirSalto` (no `alSaltar`): el servidor da 400 si el compas esta fuera del rango del bucle.
Task 9: fix round 1/5 (5 addressed, 0 open; commits 66d77b1..beb655d). El re-revisor comparo los dos tipos de TypeScript campo a campo con los dos a_dict del nucleo: coinciden los diez y los cinco.
Task 9: complete (commits 4162ead..beb655d, re-review limpia)
Task 9: minor (deferred): los comentarios de `limpias` y `repeticiones` en TS no dicen que la proporcion EXCLUYE los compases con acordes. LO LLEVO AL DESPACHO DE LA TAREA 11, que es quien dibuja el informe.
Task 9: minor (deferred): la nota cruzada de tiposPieza.ts sugiere dos respuestas distintas en el cable; en realidad es el MISMO endpoint y el tipo de la 3a es un subconjunto.

Task 10: implementada en a1624cb + d1af020 + 1a6dfc5 (260 pruebas de interfaz; 71 + 20 + 6 roturas medidas, nueve huecos reales cerrados en la primera tanda). Revision: Approved, sin Critical ni Important.
Task 10: el implementador encontro DOS defectos del servidor que nadie habia visto: el estado no publicaba `con_click` ni `tempo_automatico` (dos de los siete campos del plan), asi que los interruptores mentian al recargar; y POST /api/piezas/plan no era un parche, sino que ponia a fabrica todo lo que el cuerpo no dijera. Arreglados en el anadido 10b.
Task 10: minores declarados y NO arreglados, para la revision final: el parpadeo del deslizador al soltar (el arreglo tiene un modo de fallo conocido si el tempo automatico mueve el factor justo entonces); la lectura mezcla el porcentaje del gesto con los ppm del servidor durante el arrastre; y un factor fuera de la rejilla del 5 % se ve ajustado al paso.
Task 10: el `error` del hook es pegajoso: un 400 se queda en pantalla hasta la siguiente orden aceptada. Declarado, tolerable.
Ruling: el tempo se manda AL SOLTAR el deslizador y no en cada paso — cada cambio de factor reconstruye el seguidor bajo el candado que comparte con el hilo de analisis (hasta 8 ms con 8000 notas), asi que un arrastre disparaba decenas de reconstrucciones; el valor que se ve mientras se arrastra es estado local porque es el gesto, no el plan, y esta comentado como tal; si me equivoco, el tempo no se oye cambiar hasta que sueltas.
Ruling: `pointercancel` descarta el gesto del deslizador y `onBlur` lo confirma (decision del implementador, aprobada) — sin ellos, un arrastre interrumpido dejaba el deslizador ensenando un valor que el servidor no tiene.

Anadido 10b (no estaba en el plan; nace del hallazgo de la tarea 10): commits 86b7b92, 2305945 y c2a3b3e. Suite 1008 passed, 30 skipped. El estado publica el plan completo, /api/piezas/plan es un parche de verdad, y la fusion va bajo una sola toma del candado.
Anadido 10b: VIGESIMA prueba que no podia fallar, cazada por el implementador: su primera prueba de dos hilos paraba el hilo DENTRO de cambiar_plan, donde el candado ya esta tomado, asi que no medía la carrera. Rehecha.
Anadido 10b: el revisor DESMINTIO una afirmacion del implementador ("ninguna rotura sobrevive"): la omision de `compases_de_cuenta_asas` en el parche sobrevivia a las 65 pruebas. Era un hueco real, ya cerrado con prueba medida. La frase esta rectificada en el informe.
Anadido 10b: el error de coleccion de tests/test_app_canciones.py que el revisor vio en su copia NO existe en el arbol: colecciona 147 pruebas. Artefacto de su copia.
Task 10: fix round (1 addressed, 0 open; commit 1a6dfc5). El re-revisor midio seis mutaciones y las seis caen; comprobo ademas que la prueba del blur verifica la orden exacta y no solo que el componente no revienta, y que no queda ninguna copia local del plan.
Task 10: minor (deferred): `arrastre` puede quedar sin enviar mientras el foco siga en el deslizador (un `change` sin pointerup/keyup, p. ej. un lector de pantalla). El blur lo rescata, asi que no se pierde, pero mientras tanto es el mismo desajuste. Deducido del codigo, no reproducido.
Task 10: complete (commits beb655d..1a6dfc5 en interfaz, re-review limpia)

Task 11: implementada en 1f526c0 + e7585c5 + 5865e06 + 3b87edf (300 pruebas de interfaz; 48 + 10 + roturas de dos rondas mas). Revision: dos Important, los dos reales, cerrados.
Task 11: el informe en pantalla calcula el porcentaje con la MISMA cuenta que `proporcion_limpia` del nucleo (limpias sobre medibles por repeticiones, saltando los compases con acordes, null != 0,0). El revisor lo comparo linea a linea.
Task 11: VIGESIMOPRIMERA prueba que no podia fallar: "cierra el WebSocket ANTES de pedir el detener" no moria al intercambiar las dos lineas, porque el aplazo a microtarea hace el orden observable identico. El invariante SI estaba protegido, pero por el aplazo, y el comentario atribuia la garantia al orden de las lineas. Rehecha espiando el objeto de detencion.
Task 11: VIGESIMOSEGUNDA, de un tipo nuevo: un `vi.spyOn` sin restaurar en Ejercicios.test.tsx dejaba `programar` como no-op para todas las pruebas siguientes, y entre ellas las dos que vigilaban el arreglo. Cerrada con `vi.restoreAllMocks()`; con la rotura caen ahora 4 donde antes 0.
Task 11: ME EQUIVOQUE con oxlint, y el revisor anterior conmigo: SI corre `react-hooks/exhaustive-deps` (los plugins react y typescript la traen por defecto), asi que la supresion ocultaba dos dependencias que faltaban. El implementador lo arreglo haciendolas estables.
Task 11: la ficha de detencion al salir era por INSTANCIA, asi que un remontaje por `key` nueva dejaba una microtarea sin cancelar que mataba la pieza recien arrancada. Ahora es una por ruta, a nivel de modulo.
Task 11: minor (deferred): dos carriles vivos a la vez comparten la unica pieza del servidor, asi que desmontar uno detiene la del otro. Misma semantica que antes, no es nuevo.
Task 11: complete (commits c2a3b3e..3b87edf, ultimo arreglo medido por el implementador)

Task 12: implementada en cf6766d + 0764cb5. Encontro SIETE frases del README que la etapa habia dejado falsas, ninguna en su encargo: las casillas como etapa 3c, las secciones "para la 3c" (la 3c no las usa), el estado de la etapa, el carril "sin cuenta atras ni metronomo", su propia frase sobre la cuenta atras, la ventana de +-80 ms sin mencionar que se estira, y la primera frase del README. Las cifras del README salen de constantes del codigo, con la ruta de cada una en el informe.
Task 12: de ahi salio el HUECO CONTRA LA SPEC que cierra el anadido 12b: la cuenta atras solo se abria al dar la vuelta el bucle, asi que la primera entrada al tramo no la llevaba, y el usuario pidio "un compas de cuenta atras antes de arrancar y en cada repeticion".

Anadido 12b (no estaba en el plan; nace de la tarea 12): commit 204897e. Suite 1022 passed, 30 skipped. `arrancar()` coloca el cabezal y DESPUES abre la cuenta (al reves se cancelaria), lo llaman SesionCarril.iniciar y reiniciar_pasada, y el constructor sigue sin abrir cuenta. Revision: cumplimiento OK, calidad aprobada, dos menores no bloqueantes.
Anadido 12b: hueco real cazado por el implementador: quitar el `avanzar_a(inicio)` de `avanzar` o de `procesar` NO tiraba nada, porque quien abre la cuenta ya deja el reloj en el inicio, asi que la congelacion estaba sin red. La prueba que lo cierra abre la cuenta tocando un atributo privado; el revisor la llama legitima pero de segunda clase, y propone como alternativa quitar la redundancia del codigo en vez de blindarla. Decision de gusto, no defecto.
Anadido 12b: tres pruebas existentes tocadas (dos de la etapa 3a). El revisor verifico que las tres siguen midiendo lo mismo: a las dos de test_sesion_carril.py se les paso compases_de_cuenta_atras=0 y sus aserciones quedan literales, y la tercera solo amplio el numero de pasos sin aflojar aserciones.
Anadido 12b: minor (deferred): `arrancar()` no mira la pausa del usuario; hoy es inalcanzable porque `iniciar` crea una sesion nueva y `reiniciar_pasada` no tiene llamadores fuera de las pruebas. Conviene decirlo en su docstring.

## Revision final de rama (opus, 35 commits) y su ola de arreglos

Veredicto inicial: NO listo para fusionar. 1 Critical + 6 Important + 6 menores.
Critical: la cuenta atras moria con el PRIMER cuadro de audio, porque `_observar` congelaba con `colocar_en`, que la cancela por contrato. Lo ultimo que construyo la rama no funcionaba con el cable enchufado. Causa raiz del silencio: ninguna prueba publicaba cuadros con una cuenta abierta, y el commit que anadio la cuenta la APAGO (compases_de_cuenta_atras=0) en las dos unicas pruebas que podian haberla matado. Patron nuevo, numero 23 de la familia.
Important: al acabar un tramo sin bucle se recolocaba el reloj en CADA cuadro (109 de 300), perdiendo hasta 250 ms de notas al final de cada pasada y envenenando peores_compases y la regla del tempo; el acento del metronomo caia mal en 6/8 y 7/8 (defecto de MI spec, que decia literalmente `compas = pieza.compas[0]`); el boton decia "Subir el tempo" cuando la sugerencia era bajar; "Pieza terminada - 2 de 12 notas" al acabar un tramo de dos compases; dos frases falsas mas del README (una "corregida" al reves); y `SesionDeEstudio` mutada desde los dos hilos sin candado propio.
Ola de arreglos: commits 253a890, 6573dbb, f2d0759, 46d75d7.
Ruling: acepto la desviacion del implementador en el hallazgo 2 — mi arreglo literal (recolocar una sola vez) NO recupera la nota, porque el detector firma el onset hasta 250 ms despues y esa recolocacion deja la correspondencia sin fijar; el re-revisor lo reprodujo. Su version aplaza la recolocacion mientras la ventana pueda tener algo en vuelo; si me equivoco, el cabezal se pasa hasta 250 ms del final del tramo.
Al devolver la cuenta atras a su valor de fabrica se destaparon ONCE casos mas: seis pruebas de la etapa 3a vivian del Critical y cinco pasaban sin medir nada. El re-revisor verifico las once contra la rotura del invariante que vigila cada una.
Re-revision: los doce hallazgos ADDRESSED, pero el diff introdujo una REGRESION propia (el reloj se escapaba sin tope si el audio se cortaba dentro de la ventana: 47,8 s donde debian ser 8,0).
Ruling: cierro la regresion y DOS lineas de honestidad (el `assert` de `agotar_cuenta_atras` y el caso de 0,5 s de la prueba del hueco, que era la numero 24 que no podia fallar), y APARCO el resto en vez de abrir otra ola — el usuario decide con la lista delante; si me equivoco, la 3d empieza con esa deuda. Commit 2aebd42.

## APARCADO, con lo medido, para la etapa siguiente

- El historial, `peores_compases` y la regla del tempo siguen perdiendo la nota del final cuando el detector la firma despues del tick del WebSocket que cierra la pasada (medido: el informe de pantalla dice acertadas=1 y el anotado en el historial, 0).
- CON BUCLE la ultima nota de cada vuelta se sigue perdiendo, por el `olvidar_tramo` + `avanzar_a` de `_dar_la_vuelta`. Es el mismo defecto y los mismos 250 ms, y es donde el alumno pasa el rato.
- Durante esos 250 ms el exceso se ve: `indice_actual` entra en la nota siguiente y el contador de progreso lo pinta sin la guarda de `completado`.
- Y cobra: un rasgueo posterior al final del tramo, dentro de la ventana, se adjudica a una nota del tramo y sube el informe de pantalla.
- El `congelar_en` de `_observar` es letra muerta (borrarlo deja la suite en 1038); explica como pudo vivir ahi el `colocar_en` que mataba la cuenta.
- `peores_compases` no multiplica por `repeticiones`, al contrario que `proporcion_limpia`.
- `pausar`/`reanudar` quedan fuera del candado nuevo.
- `test_la_pausa_le_congela_el_reloj_tambien_al_seguidor` mide otra cosa que su nombre (sobrevive a quitar justo la congelacion de la pausa).
- El docstring de `Seccion` en `nucleo/piezas/modelo.py` dice "No se usan todavia" cuando el selector de secciones existe: decima frase de la misma familia, y esta vive en el nucleo.
- Mas los menores diferidos de las tareas, triados por la revision final: solo uno pedia arreglo ya (las pruebas en 6/8 y 7/8) y se hizo.

## Estado final verificado en el arbol a integrar

- `uv run pytest -q` -> 1039 passed, 30 skipped (main tenia 940)
- `pnpm test` -> 306 passed, 15 archivos; `pnpm build` y `pnpm lint` limpios
- Repo normal (GIT_DIR == GIT_COMMON), rama etapa-3c-practicar, 40 commits sobre main = 5e6a418, SIN REMOTO
- `git status --porcelain` -> solo `.claude/` sin seguimiento; `canciones/` no existe en la raiz
