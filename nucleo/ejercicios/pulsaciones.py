"""Que nota se toco y cuando: la deteccion de pulsaciones, sin saber de ejercicios.

Consume el mismo flujo de ResultadoAnalisis que alimenta al afinador. Como
ResultadoAnalisis es un dato, toda esta logica se prueba escribiendo la secuencia
exacta que produciria alguien tocando, sin audio y sin hardware.

Una pulsacion (una lectura que cuenta como intento de tocar algo) puede
dispararse por dos caminos independientes, resueltos a lo sumo uno por cuadro:

Camino A - ataque de energia. `DetectorAtaques` marca un ataque por el salto de
nivel; se anota una lectura pendiente para `instante + espera_estabilizacion_s`
y se resuelve en la primera llamada posterior a ese momento EN QUE LA NOTA YA
LLEVA RACHA ESTABLE. Es el camino que describe la Task 7 original, con la
condicion de racha añadida en la Task 6c (ver mas abajo).

Camino B - cambio estable de nota. Se cuenta cuantos cuadros seguidos trae la
misma nota con confianza suficiente. Al llegar a `cuadros_para_nota_estable`
cuadros, y si esa nota es distinta de la ultima ya resuelta, se dispara el
evento sin esperar ningun salto de energia.

LOS DOS CAMINOS LEEN LA MISMA RACHA ESTABLE. Desde la Task 6c, el camino A ya no
lee la altura del PRIMER cuadro posterior a su espera, sino la de una racha de
`cuadros_para_nota_estable` cuadros creibles seguidos (tres, no uno). Y esto esta
MEDIDO, no elegido: la altura que el pipeline PUBLICA llega tarde respecto del
ataque real, y `espera_estabilizacion_s` (60 ms) no alcanza a cubrir ese retraso.

    ventana de analisis (4096 muestras a 48 kHz)        85,3 ms
    suavizador de mediana 5 (nucleo/analisis/pipeline)  42,0 ms
    -------------------------------------------------------------
    la nota publicada gira hasta                       127,3 ms despues

Leyendo a los 60 ms, el camino A caia uno o dos cuadros antes de ese giro y
sellaba el ataque de la nota nueva CON LA ALTURA DE LA ANTERIOR. Medido con el
gemelo digital (interprete PERFECTO, escala de ocho notas, sin bucle): 5 de 30
semillas de sintesis daban un veredicto sucio -una nota con la altura de la
anterior y, a partir de ahi, la cola del tramo perdida- y la cadena firmaba
desfases de hasta -460,7 ms. Con la racha exigida, 0 de 30. El diagnostico
completo esta en `.superpowers/sdd/2026-11-02-gemelo-digital/task-6b-diagnostico.md`.

No se subio `espera_estabilizacion_s` a 128 ms, que habria tapado lo mismo,
porque seria ACOPLAR este modulo al tamaño de la ventana del pipeline y al de
su suavizador: dos numeros que este detector no conoce ni debe conocer, y que
cambian con el perfil de afinacion. Exigir la racha no necesita saber cuanto
tarda el tono en cuajar: espera a que cuaje.

ENTONCES, ¿PARA QUE SIRVE HOY EL CAMINO A? NO para firmar el onset con el ataque,
y conviene decirlo claro porque es lo que uno supondria. Cuando el ataque sigue
vigente, `_onset_camino_b` firma EL MISMO instante que el camino A habria
firmado -eso es la unificacion del onset, y es deliberada-, asi que en el caso
normal los dos caminos producen exactamente la misma pulsacion. Medido por fuerza
bruta sobre secuencias de cuadros sinteticos: la fraccion que los distingue es
minuscula -del orden de 10^-6 a 10^-4, y el numero exacto DEPENDE DEL ALFABETO Y
DEL LARGO de la busqueda, asi que no se inscribe aqui como si fuera una
propiedad del detector; los parametros y las cifras estan en el docstring de
`test_el_camino_a_reinicia_la_racha_y_eso_salva_el_onset_siguiente`-, la
diferencia es SIEMPRE en el onset y nunca en la altura ni en el recuento, y con
AUDIO REAL del gemelo (escala de ocho notas y demostracion de cuarenta y ocho,
doce semillas cada una) es CERO.

Lo que el camino A aporta de verdad es su REINICIO DE LA RACHA. Al sellar pone
`_nota_candidata` y su contador a cero; el camino B no los toca. Y eso decide el
onset de la pulsacion SIGUIENTE: con la racha a cero, el cuadro siguiente no
tiene `nota_estable`, nadie llama a `_sellar` y un ataque recien detectado
SOBREVIVE para firmar la nota que viene. Sin ese reinicio, la racha de la nota
vieja sigue viva, `_sellar` la descarta por nombre y el descarte BORRA el ataque
-el borrado existe para que un ataque ya gastado no firme la pulsacion
siguiente-, de modo que la nota que viene pierde su ataque y se queda con el
comienzo de su racha. Medido sobre el testigo, variando cuantos cuadros publican
la altura vieja tras el ataque: 21 ms de diferencia con un cuadro, 42 ms con DOS
-que es la racha del perfil real, o sea que el mecanismo no es un borde, crece
con el retraso del suavizador- y 0 ms con tres, porque ahi la racha vieja se come
el margen y los dos caminos acaban firmando el mismo onset tardio. Esta clavado en
`tests/test_pulsaciones.py::test_el_camino_a_reinicia_la_racha_y_eso_salva_el_onset_siguiente`,
la unica prueba de la suite que muere si el camino A desaparece.

DEUDA ANOTADA: EL CAMINO A MERECE UNA RUTA DE RETIRADA, y no se hace aqui. Lo
que aporta es COMPENSATORIO: tapa una sobre-reaccion del descarte por nombre de
`_sellar`, que borra el ataque incluso cuando ese ataque acaba de detectarse y
pertenece a la nota que todavia no ha cuajado. El arreglo mas honesto y mas
pequeño estaria ahi, en `_sellar`: no borrar el ataque cuando el descarte por
nombre coincide con un ataque recien detectado. Hecho eso, el camino A se queda
sin ninguna aportacion propia y se puede retirar, dejando un solo camino de
disparo con un onset que sabe de ataques. No se hace en esta tarea porque obliga
a rehacer un contrato que tiene prueba propia
(`test_el_descarte_por_nombre_no_deja_al_camino_a_resolver_sin_onset` y
`test_la_nota_nueva_que_de_verdad_suena_se_resuelve_igual_y_con_su_onset`), y
porque el camino A fue justamente el componente que causo el defecto que la
Task 6c vino a arreglar: tocar las dos cosas a la vez seria rehacer el modulo
con una sola red. La PRUEBA DE ACEPTACION de esa retirada ya existe y es
`test_el_camino_a_reinicia_la_racha_y_eso_salva_el_onset_siguiente`: quien
arregle `_sellar` tiene que dejarla verde con el camino A quitado.

EL MARGEN ES DE UN CUADRO, Y ES UN UMBRAL CALIBRADO, NO UN INVARIANTE. Lo que
protege de volver a sellar la altura vieja es una desigualdad:

    cuadros_para_nota_estable  >  racha de cuadros creibles con la ALTURA VIEJA

El lado derecho tiene dos sumandos. El primero es estructural y vale para
cualquier instrumento: una mediana de n publica la altura vieja durante
`n // 2` cuadros, o sea 2 con el suavizador de cinco (ver `TAMANO_SUAVIZADO` en
`nucleo/analisis/pipeline.py`, donde la desigualdad esta escrita, y
`tests/test_pulsaciones.py::test_la_racha_estable_supera_al_suavizador`, donde
esta afirmada). El segundo son los cuadros cuya VENTANA cruza la frontera entre
dos notas, y ese depende del perfil: con guitarra estandar son 4,1 cuadros y en
la medicion salieron DUDOSOS por el transitorio de la pua -o sea que no
contaron-, pero eso es una propiedad del sintetizador, no una garantia.

Medido sobre 30 semillas x 7 fronteras de nota, con el salto de produccion:

    guitarra estandar  ventana 4096 ( 85,3 ms, 4,1 cuadros)  racha vieja 2  margen 1
    bajo de 4 cuerdas  ventana 8192 (170,7 ms, 8,1 cuadros)  racha vieja 3  margen 0
    bajo de 5 cuerdas  ventana 8192 (170,7 ms, 8,1 cuadros)  racha vieja 3  margen 0

**CON PERFIL DE BAJO EL MARGEN ES CERO Y EL DEFECTO VUELVE.** No es una
hipotesis: con la racha vieja en 3 el camino A sella otra vez la altura de la
nota anterior. Hoy no se nota porque una pieza de bajo ya sale sucia de la
cadena por otra razon independiente y anterior a este arreglo -los 171 ms de
ventana empujan el retraso de la cadena por encima de los 250 ms de
`VENTANA_ATAQUE_COMO_ONSET_S` y de la tolerancia de emparejamiento del
veredicto, asi que la pasada entera se desadjudica: medido 30 de 30 semillas
sucias ANTES y DESPUES de este arreglo, con los mismos reportes-. O sea que el
bajo esta fuera del sobre de la cadena por dos motivos a la vez, y quien lo
meta dentro tiene que arreglar los dos. No hay segunda linea de defensa: el
filtro de nombre de `_sellar` esta desarmado en toda frontera de nota, porque
el hueco de cuadros no creibles libera `_ultima_nota_resuelta` justo antes.

CASO DEGRADADO CONOCIDO, y es el precio del arreglo: una pulsacion cuya altura
solo llega a publicarse de forma creible durante menos de
`cuadros_para_nota_estable` cuadros NO se cuenta. Antes el camino A la habria
cobrado con un solo cuadro. Son notas muy cortas o muy apagadas -un staccato
seco, una nota cortada con la palma, un armonico que se apaga enseguida-, y con
guitarra estandar el caso no se ha observado en audio (las rachas creibles de
una nota normal duran veinte cuadros y mas). Esta probado en
`tests/test_pulsaciones.py::test_una_altura_que_solo_cuaja_dos_cuadros_no_se_cuenta`
para que el dia que alguien lo vea tocando encuentre el caso escrito y no lo
descubra desde cero.

LA LECTURA PENDIENTE CADUCA. Como el camino A ya no resuelve en el primer
cuadro posterior a su espera, puede quedarse esperando una racha que no llega;
si siguiera esperando sin limite, firmaria con un ataque viejisimo la primera
racha que apareciera, que pertenece a otra pulsacion. Asi que la lectura
pendiente se abandona en cuanto el ataque pasa de `VENTANA_ATAQUE_COMO_ONSET_S`
(0,25 s), que es el mismo techo con el que `_onset_camino_b` decide si un
ataque todavia puede firmar un onset: pasado ese punto el ataque no sirve para
nada en este modulo, ni para firmar ni para esperar. Lo que llegue despues lo
resuelve el camino B con el comienzo de la racha, que es lo unico cierto que
queda.

Se necesito el camino B porque, con el decaimiento real de una guitarra
(unos 8.7 dB/s), a tempo normal la nota anterior todavia suena casi al mismo
nivel cuando se pulsa la siguiente: el salto no llega a los 6 dB que exige el
detector de energia y el ejercicio no avanza nunca. Medido con negras:

    60 BPM (1.000 s entre notas) -> 8 de 8 ataques detectados
    90 BPM (0.667 s)             -> 1 de 8
    120 BPM (0.500 s)            -> 1 de 8

El camino B no depende de la energia, asi que detecta el cambio de nota aunque
el nivel apenas se mueva. Exigir estabilidad (varios cuadros seguidos, no uno
solo) es lo que evita que el caos del transitorio de la pua dispare con un
armonico falso.

Ambos caminos comparten el mismo filtro: una lectura que coincide con la
ultima nota ya resuelta (`_ultima_nota_resuelta`) no vuelve a contarse. Eso
evita que un segundo pico de energia sobre una nota que ya sonaba (un hinchado
de volumen, un vibrato) se lea contra la nota siguiente, y evita que una racha
estable ya resuelta por el camino B se cuente otra vez cuando el camino A
llega tarde a leer el mismo sonido. Ese registro se libera cuando se acumulan
`cuadros_para_olvidar_nota` cuadros SEGUIDOS sin nota creible (silencio o
confianza insuficiente): un hueco real es la frontera entre pulsaciones y le
devuelve a ambos caminos la capacidad de volver a contar la misma nota. No
basta un solo cuadro dudoso: el detector de tono flaquea a mitad de una nota
sostenida sin que la pulsacion haya terminado, y limpiar al primer bache
resolveria dos veces la misma pulsacion (ver CUADROS_PARA_OLVIDAR_NOTA).
"""

from dataclasses import dataclass

from nucleo.analisis.pipeline import ResultadoAnalisis
from nucleo.ejercicios.ataques import ESPERA_ESTABILIZACION_S, DetectorAtaques

# Confianza minima del detector de tono para que una lectura cuente como intento.
CONFIANZA_MINIMA = 0.75

# Cuadros seguidos con la misma nota creible para que el camino B la de por
# estable. A 21 ms por cuadro son unos 63 ms: el mismo orden que la espera de
# estabilizacion del camino A (60 ms), y esa cercania es intencional, no
# casual: si el camino B tardara mucho mas que el camino A en confirmar,
# dejaria de aportar nada sobre una pulsacion normal. La equivalencia en
# milisegundos esta ACOPLADA al intervalo entre cuadros de analisis (aqui 21
# ms, el de las pruebas): con un intervalo mayor, los mismos cuadros
# representan mas tiempo, y con uno menor, menos. Nada en este modulo verifica
# ese acoplamiento porque el intervalo de analisis no es una constante propia
# del detector, sino de quien lo alimenta (el pipeline de audio); quien
# cambie la tasa de analisis debe revisar si `cuadros_para_nota_estable` sigue
# teniendo sentido.
CUADROS_PARA_NOTA_ESTABLE = 3

# Cuadros seguidos sin nota creible antes de olvidar la ultima nota resuelta.
# Uno solo no basta: el detector de tono flaquea a mitad de una nota sostenida y
# el pipeline emite "silencio" con el nivel intacto, asi que limpiar al primer
# bache haria que una misma pulsacion se resolviera dos veces. Se usa el mismo
# criterio de estabilidad que el camino B: tres cuadros, unos 63 ms al intervalo
# de analisis habitual.
CUADROS_PARA_OLVIDAR_NOTA = 3

# Cuanto puede haber pasado desde un ataque de energia para que el camino B lo
# tome como el onset de la pulsacion que esta resolviendo (ver
# _onset_camino_b). El detector de tono tarda decenas de milisegundos en dar una
# lectura creible tras el ataque de la pua, y el camino B necesita ademas
# `cuadros_para_nota_estable` cuadros seguidos: 0.25 s cubre ese retraso con
# holgura. Y sigue estando muy por debajo del hueco entre notas a cualquier
# tempo de practica (los generadores producen de 60 a 95 ppm, es decir de 1.0 a
# 0.63 s por nota), asi que un ataque mas viejo que esto pertenece a otra
# pulsacion y no debe firmar este onset.
#
# TIENE UN SEGUNDO USO, y es el mismo criterio visto del otro lado: tambien es
# cuanto espera el camino A a que la nota cuaje antes de abandonar su lectura
# pendiente (ver `procesar`). Un ataque que ya no puede firmar un onset tampoco
# merece que se le siga esperando: lo que llegue despues es de otra pulsacion.
# Los dos usos tienen que mover juntos, que es la razon de que sea una sola
# constante y no dos con el mismo valor.
VENTANA_ATAQUE_COMO_ONSET_S = 0.25


@dataclass(frozen=True)
class Pulsacion:
    """Una nota que el alumno toco, con cuando empezo y como de afinada iba.

    `instante` es el onset que se anota en el informe: el instante del ataque de
    energia siempre que hubo uno, o el comienzo de la racha estable cuando no lo
    hubo (ver `DetectorPulsaciones._onset_camino_b`). Puede ser None en el caso
    raro en que el camino A resuelve con el ataque ya gastado por un descarte
    previo; `IntentoNota.instante` admite None por lo mismo, y `regularidad_ms`
    ignora esos instantes.
    """

    nota: str
    cents: float | None
    instante: float | None


class DetectorPulsaciones:
    """Que nota se toco y cuando, sin saber nada de ejercicios ni de piezas.

    Es la mitad de abajo del evaluador de ejercicios, extraida para que el carril
    la use sin duplicarla. La mitad de arriba -comparar con lo que tocaba,
    contar intentos, ayudar- se queda en quien la use, porque no es la misma en
    los dos modos: en un ejercicio la nota espera a que la aciertes y en una
    pieza la musica sigue.

    Los dos caminos de disparo (el ataque de energia y el cambio estable de
    nota) y el filtro que comparten estan explicados en el docstring del modulo.

    Limitacion conocida: dos pulsaciones seguidas de la MISMA nota no se
    distinguen si entre ellas no hay un hueco de `cuadros_para_olvidar_nota`
    cuadros (unos 63 ms al intervalo de analisis habitual) SEGUIDOS sin ninguna
    nota creible. El nivel no interviene: el filtro compara NOMBRES DE NOTA, no
    niveles, asi que por muy marcada que sea la caida de volumen entre las dos
    pulsaciones el camino A queda filtrado igual, y el camino B no ve ninguna
    altura nueva. Ojo con el detalle: no basta con que deje de darse ESA nota,
    porque cualquier otra lectura creible reinicia el contador del hueco; con una
    nota de guitarra que sigue sonando, eso puede no llegar nunca. Quien use el
    detector decide como salir de ese atasco (el evaluador de ejercicios lo hace
    con su disparador de ayuda por tiempo).

    No lleva candado propio: quien lo use desde varios hilos DEBE protegerlo el
    mismo. `procesar` muta todo el estado interno del detector, asi que una
    lectura concurrente puede ver medio cuadro. Hoy el unico consumidor es
    `EvaluadorEjercicio`, que lo envuelve en su `_candado`; el siguiente que lo
    use tiene que hacer lo propio.
    """

    def __init__(
        self,
        detector_ataques: DetectorAtaques | None = None,
        confianza_minima: float = CONFIANZA_MINIMA,
        espera_estabilizacion_s: float = ESPERA_ESTABILIZACION_S,
        cuadros_para_nota_estable: int = CUADROS_PARA_NOTA_ESTABLE,
        cuadros_para_olvidar_nota: int = CUADROS_PARA_OLVIDAR_NOTA,
    ) -> None:
        self._detector = detector_ataques or DetectorAtaques()
        self.confianza_minima = confianza_minima
        self.espera_estabilizacion_s = espera_estabilizacion_s
        self.cuadros_para_nota_estable = cuadros_para_nota_estable
        self.cuadros_para_olvidar_nota = cuadros_para_olvidar_nota
        self.reiniciar()

    def reiniciar(self) -> None:
        """Olvida todo lo oido. Se llama al empezar un ejercicio o una pieza."""
        self._detector.reiniciar()
        # Camino A: cuando toca leer la nota del ataque, y el instante del ataque
        # que origino esa lectura diferida.
        self._lectura_pendiente: float | None = None
        self._instante_ataque: float | None = None
        # Camino B: nota candidata, cuantos cuadros seguidos lleva y cuando
        # empezo esa racha (para registrar el instante correcto del evento).
        self._nota_candidata: str | None = None
        self._contador_candidata = 0
        self._instante_inicio_candidata: float | None = None
        # Ultima nota resuelta por cualquiera de los dos caminos; se libera
        # cuando se acumulan cuadros_para_olvidar_nota cuadros SEGUIDOS sin
        # nota creible (ver _cuadros_sin_nota_creible mas abajo).
        self._ultima_nota_resuelta: str | None = None
        self._cuadros_sin_nota_creible = 0
        self._senal_de_nota_nueva = False

    @property
    def senal_de_nota_nueva(self) -> bool:
        """Si el ultimo cuadro traia senal que podria ser una pulsacion nueva.

        Es decir: nota creible que NO es `_ultima_nota_resuelta`. Un cuadro
        creible cuya nota es la ultima ya resuelta es la cola de esa pulsacion,
        que se conto y sigue sonando: no es que el alumno este intentando nada.
        Esa distincion la necesita quien decide si el alumno esta tocando de
        verdad (ver la regla de la ayuda por tiempo en `EvaluadorEjercicio`):
        tomar cualquier cuadro creible por senal nueva hacia que la cola
        rearmara la bandera justo despues de cada nota resuelta, y entonces una
        pausa para pensar -o el cable desenchufado- regalaba la ayuda sin haber
        tocado nada.
        """
        return self._senal_de_nota_nueva

    def procesar(self, resultado: ResultadoAnalisis, instante: float) -> Pulsacion | None:
        """Devuelve la pulsacion detectada en este cuadro, o None.

        Evalua los dos caminos de disparo y resuelve a lo sumo uno por cuadro:

        Camino A. La lectura de un ataque es diferida DOS VECES: no se lee en su
        propio instante -justo en el ataque la senal es caotica y leer ahi daria
        notas falsas-, sino pasada la espera de estabilizacion Y cuando la nota
        de este cuadro ya lleva racha estable. La segunda condicion es la que
        impide sellar el ataque con la altura de la nota ANTERIOR, que el
        pipeline sigue publicando hasta 42 ms despues de que su detector de tono
        haya girado (ver el docstring del modulo). Si la racha no llega, la
        lectura pendiente se abandona al pasar `VENTANA_ATAQUE_COMO_ONSET_S`
        desde el ataque.

        Camino B. Se sigue cuantos cuadros lleva la misma nota creible. La
        cuenta la lleva `_actualizar_candidata`, que se ejecuta UNA VEZ por
        cuadro y ANTES de los dos caminos, porque los dos leen su resultado: el
        camino A para saber si ya puede sellar y el camino B para saber si le
        toca disparar. Si el camino A resuelve en este cuadro, la cuenta se
        reinicia (ese ataque ya se leyo) y el camino B no vuelve a disparar con
        la nota que sigue sonando. Si es el camino B el que resuelve, se cancela
        cualquier lectura pendiente del camino A para esa misma nota sostenida,
        evitando contar el mismo evento dos veces.

        Ademas, cuando se acumulan `cuadros_para_olvidar_nota` cuadros SEGUIDOS
        sin nota creible (silencio o confianza insuficiente) se libera
        `_ultima_nota_resuelta`: un hueco real es la frontera entre
        pulsaciones, y sin esa liberacion una nota equivocada repetida
        bloquearia ambos caminos para siempre (ver la limitacion documentada
        en la clase). Un solo cuadro dudoso no cuenta como hueco: el contador
        se reinicia en cuanto vuelve un cuadro con nota creible, para no
        resolver dos veces la misma pulsacion solo porque el detector de tono
        flaqueo un instante a mitad de la nota.

        Ojo, el detector CONSUME estado antes de que quien lo llama decida que
        hacer con la pulsacion: al detectarla ya ha sellado
        `_ultima_nota_resuelta` con esa nota y ha gastado `_instante_ataque`. Si
        quien la recibe la descarta (porque no era la nota que tocaba, porque la
        pieza ya paso por ahi), el detector ha avanzado igual y esa nota no
        volvera a dispararse hasta que se abra un hueco sin nota creible.
        """
        self._senal_de_nota_nueva = False

        if self._es_creible(resultado):
            self._cuadros_sin_nota_creible = 0
            # `senal_de_nota_nueva` solo se arma con senal que PODRIA ser una
            # pulsacion nueva: un cuadro creible cuya nota es
            # `_ultima_nota_resuelta` es la cola de la anterior (ver la
            # propiedad). Se calcula ANTES de resolver, contra la nota resuelta
            # con la que empezo el cuadro.
            if resultado.nota != self._ultima_nota_resuelta:
                self._senal_de_nota_nueva = True
        else:
            self._cuadros_sin_nota_creible += 1
            if self._cuadros_sin_nota_creible >= self.cuadros_para_olvidar_nota:
                self._ultima_nota_resuelta = None

        ataque = self._detector.procesar(resultado.nivel_db, instante)
        if ataque is not None:
            self._lectura_pendiente = ataque.instante + self.espera_estabilizacion_s
            self._instante_ataque = ataque.instante

        pulsacion: Pulsacion | None = None

        # La racha se actualiza UNA VEZ y antes de los dos caminos, porque los
        # dos la leen: el camino A exige racha para poder sellar (si no, sellaria
        # con la altura vieja que el suavizador sigue publicando) y el camino B
        # dispara cuando la racha llega a su tope.
        nota_estable = self._actualizar_candidata(resultado, instante)

        # El ataque caduca cuando deja de estar vigente, que es LA MISMA decision
        # con la que `_onset_camino_b` decide si puede firmar un onset: un solo
        # predicado, `_ataque_vigente`, para que las dos no se puedan separar (la
        # razon esta en su docstring). Sin esta caducidad, una lectura que se
        # queda esperando una racha que no llega acabaria firmando con un ataque
        # viejisimo la primera racha que apareciera, que es de otra nota: medido,
        # un ataque de 350 ms de antiguedad firmando el onset de la racha
        # siguiente (ver
        # test_el_onset_del_camino_b_es_el_comienzo_de_la_racha_no_el_final).
        if self._lectura_pendiente is not None and not self._ataque_vigente(instante):
            self._lectura_pendiente = None

        if (
            self._lectura_pendiente is not None
            and instante >= self._lectura_pendiente
            and nota_estable is not None
        ):
            self._lectura_pendiente = None
            pulsacion = self._sellar(resultado, self._instante_ataque)
            if pulsacion is not None:
                # Este ataque ya se leyo: el camino B empieza a contar de nuevo
                # para no repetir el mismo evento con la nota que sigue sonando.
                self._nota_candidata = None
                self._contador_candidata = 0
                self._instante_inicio_candidata = None

        if pulsacion is None and nota_estable is not None:
            pulsacion = self._sellar(resultado, self._onset_camino_b(instante))
            # Esta nota ya la vio el camino B: si habia una lectura pendiente
            # del camino A para el mismo sonido, se cancela.
            #
            # Se cancela tanto si se sello como si se DESCARTO por nombre, y
            # eso ultimo es lo que faltaba: el descarte por nombre borra
            # `_instante_ataque` (para no firmar con el el onset de la
            # pulsacion siguiente) pero dejaba la lectura pendiente puesta,
            # asi que el camino A resolvia despues con `instante=None`. En un
            # ejercicio eso costaba una muestra de `regularidad_ms`; en el
            # carril, `SeguidorPieza._adjudicar` se queda sin onset y busca
            # con el reloj del cuadro -hasta 250 ms despues del ataque real-,
            # con lo que puede cobrar la nota siguiente.
            #
            # Con `nota_estable` puesto el cuadro era creible, asi que el
            # unico descarte posible de `_sellar` es el de nombre.
            self._lectura_pendiente = None

        return pulsacion

    def _es_creible(self, resultado: ResultadoAnalisis) -> bool:
        """Si esta lectura trae una nota que se puede tomar en serio."""
        return (
            resultado.estado == "nota"
            and resultado.nota is not None
            and resultado.confianza >= self.confianza_minima
        )

    def _actualizar_candidata(
        self, resultado: ResultadoAnalisis, instante: float
    ) -> str | None:
        """Sigue la pista de cuantos cuadros seguidos suena la misma nota creible.

        Devuelve el nombre de la nota en cuanto lleva `cuadros_para_nota_estable`
        cuadros seguidos, o None si no hay racha suficiente (sin nota creible,
        o racha mas corta). No compara aqui contra la ultima nota resuelta: ese
        filtro es responsabilidad de `_sellar`, el mismo para los dos caminos.
        """
        if not self._es_creible(resultado):
            self._nota_candidata = None
            self._contador_candidata = 0
            self._instante_inicio_candidata = None
            return None

        if resultado.nota == self._nota_candidata:
            self._contador_candidata += 1
        else:
            self._nota_candidata = resultado.nota
            self._contador_candidata = 1
            self._instante_inicio_candidata = instante

        if self._contador_candidata >= self.cuadros_para_nota_estable:
            return self._nota_candidata
        return None

    def _onset_camino_b(self, instante: float) -> float | None:
        """Instante que se anota como comienzo de la nota cuando resuelve el camino B.

        Los dos caminos deben anotar la MISMA definicion de onset, porque
        `regularidad_ms` mide la desviacion tipica de los huecos entre onsets
        consecutivos. El camino A anota el instante del ataque de energia; el
        comienzo de la racha estable del camino B llega, en una guitarra real,
        decenas de milisegundos DESPUES de ese ataque (el transitorio de la pua
        no tiene altura definida, asi que el detector de tono tarda en dar una
        lectura creible). Un ejercicio que resolviera unas notas por A y otras
        por B mezclaria las dos definiciones y arrastraria a `regularidad_ms` un
        sesgo del orden de lo que se quiere medir.

        Se unifica asi: si hay un ataque de energia lo bastante reciente
        (`VENTANA_ATAQUE_COMO_ONSET_S`), es el ataque de esta misma pulsacion y
        ese es el instante que se anota; solo cuando no hay ninguno -nivel
        constante, ningun salto que el detector viera- se recurre al comienzo de
        la racha, que es lo unico disponible.
        """
        if self._ataque_vigente(instante):
            return self._instante_ataque
        return self._instante_inicio_candidata

    def _ataque_vigente(self, instante: float) -> bool:
        """Si el ultimo ataque todavia puede hablar de la pulsacion de este cuadro.

        **ES UN SOLO SITIO A PROPOSITO, y la razon no es ahorrar lineas.** De esta
        decision cuelgan las dos cosas que el detector hace con un ataque: firmar
        con el un onset (`_onset_camino_b`) y seguir esperando a que la nota
        cuaje para leerla (la caducidad de la lectura pendiente, en `procesar`).
        Las dos tienen que contestar lo MISMO sobre el mismo ataque, porque un
        ataque demasiado viejo para firmar tampoco merece que se le espere, y uno
        lo bastante joven para esperarlo tiene que poder firmar.

        Escrito como dos comparaciones -una con `<=` aqui y otra con `>` alla- la
        coincidencia era una convencion que nada sostenia: cambiar el borde de
        una sola dejaba al mismo ataque siendo a la vez demasiado viejo para
        esperarlo y bastante joven para firmarlo, y ninguna prueba de la suite se
        enteraba (medido: el mutante que cambia `>` por `>=` en la caducidad
        mataba CERO pruebas, porque al filo exacto el onset salia igual por los
        dos caminos). Con una sola comparacion ese mutante no se puede escribir:
        mover el borde mueve las dos decisiones juntas, y entonces
        `test_un_ataque_justo_en_el_filo_todavia_firma_el_onset` lo mata.

        La igualdad con el techo TODAVIA cuenta como vigente (`<=`): el techo es
        el ultimo instante en que el ataque puede hablar, no el primero en que ya
        no. Es el mismo criterio que usa el veredicto del gemelo para emparejar
        un reporte con un ataque, y hay prueba de los dos lados del borde.

        El caso «no hay ataque» se contesta AQUI tambien, y por eso quien llama
        no lo vuelve a comprobar: sin ataque no hay nada vigente. La caducidad de
        `procesar` llevaba esa comprobacion repetida al lado de esta llamada, lo
        que dejaba la decision sobre `None` en dos sitios mientras este docstring
        presumia de uno. Quitarla no cambia nada, y esta medido: el estado
        «lectura pendiente puesta con el ataque ya borrado» no se da NUNCA
        -0 veces en 60.000 secuencias aleatorias sobre un alfabeto de diez
        lecturas y en las 279.936 secuencias de largo 7 de un alfabeto de seis-,
        porque la lectura pendiente y el ataque se ponen juntos (con un ataque
        nuevo) y se limpian juntos (en `_sellar`).
        """
        return (
            self._instante_ataque is not None
            and instante - self._instante_ataque <= VENTANA_ATAQUE_COMO_ONSET_S
        )

    def _sellar(
        self, resultado: ResultadoAnalisis, instante_evento: float | None
    ) -> Pulsacion | None:
        """Convierte en pulsacion la nota que suena al disparar un evento, o la descarta.

        `instante_evento` es el onset que se anota (el ataque de energia, o lo
        que devuelva `_onset_camino_b`).

        Devuelve None si el evento se descarta: sin nota creible (un golpe en la
        caja o una cuerda apagada no es un intento), o porque la nota leida es la
        misma que la ultima ya resuelta, en cuyo caso no hubo forma de distinguir
        esta lectura de la que la origino.
        """
        # Sin nota creible no hubo intento.
        if not self._es_creible(resultado):
            return None

        # Misma nota que la ultima ya resuelta: sin un cuadro sin nota creible
        # de por medio, no hay forma de saber si es una pulsacion nueva o el
        # mismo sonido que ya se conto (un segundo pico de energia sobre la
        # nota aceptada, o el resto de la racha que el camino B ya resolvio).
        if resultado.nota == self._ultima_nota_resuelta:
            # Este ataque pertenece a una pulsacion que ya se conto (un hinchado,
            # un vibrato o un roce sobre la nota aceptada). Si se quedara puesto,
            # `_onset_camino_b` lo firmaria como onset de la pulsacion SIGUIENTE
            # y falsearia `regularidad_ms` hasta en VENTANA_ATAQUE_COMO_ONSET_S.
            # Ojo: esto NO vale para el descarte por falta de nota creible de
            # arriba, donde el ataque es real y su lectura solo llego antes de
            # tiempo.
            self._instante_ataque = None
            return None

        self._ultima_nota_resuelta = resultado.nota
        # El ataque que origino este evento ya se gasto: dejarlo puesto haria
        # que `_onset_camino_b` lo firmara como onset de la pulsacion siguiente.
        self._instante_ataque = None

        return Pulsacion(
            nota=resultado.nota,
            cents=resultado.cents,
            instante=instante_evento,
        )
