"""El registro de una pasada en disco, y el archivo que los acumula.

QUE SE GUARDA Y POR QUE ASI
---------------------------

**Por compas y no nota a nota, y esta medido.** La pieza de rasgueos tiene 44
notas en 8 compases; una pasada de cuatro vueltas son 176 reportes de nota
contra 32 de compas. A nota se guardaria cinco veces mas para contestar las
mismas preguntas, porque TODO lo que el programa diagnostica ya es por compas:
`CompasDelInforme` existe precisamente porque «el 19 lo tocas 40 ms tarde» es
accionable y «fallas la nota 137» no lo es.

**Los contadores crudos y no las proporciones.** Una proporcion es una division
que el lector puede hacer; un contador perdido no se recupera. Es el mismo
criterio que `InformeDePasada.repeticiones` ya aplica al exigir que el
denominador viaje con el numerador.

**El tramo y el factor de tempo, siempre.** Son lo que hace comparable un
registro: dos pasadas del mismo compas a tempos distintos no son dos medidas de
lo mismo, y sin estos dos campos nadie puede saberlo. La regla entera -por que no
se normaliza por tempo- esta en la spec, §4.4.

**La pieza NO se guarda.** Ningun archivo con derechos de autor entra al
repositorio, nunca, y un historial con las notas dentro seria una copia de la
partitura en un archivo que el usuario podria subir sin darse cuenta. Se guarda
el nombre y una HUELLA del contenido.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from nucleo.piezas.estudio import InformeDePasada, PlanDePasada
from nucleo.piezas.modelo import Pieza

_registro = logging.getLogger(__name__)

# La version del formato del archivo. Un archivo con una version que este modulo
# no conoce NO se borra: se aparta (ver `cargar`). Puede venir de un programa mas
# nuevo, y lo que hay dentro son los fallos de alguien.
VERSION = 1

# Cuantos dias se conservan ENTEROS, con todas sus pasadas. De lo anterior queda
# una por pieza/tramo/tempo y dia, la mejor.
#
# El numero es arbitrario y se dice: 90 dias es «un trimestre», que es el
# horizonte en que a alguien le interesa haber mejorado. NO esta medido y no
# puede estarlo: haria falta saber cada cuanto vuelve el usuario a una pieza, y
# eso solo lo dira el propio historial cuando lleve meses lleno. Es el primer
# numero que habra que revisar con datos de verdad.
DIAS_COMPLETOS = 90

# Cuantos caracteres del hash se guardan. Ocho hexadecimales son 32 bits: la
# probabilidad de que dos piezas DEL MISMO USUARIO colisionen es despreciable
# (con mil piezas, del orden de 10^-4), y la huella entera llenaria la linea sin
# que nadie la leyera. No es un hash criptografico ni pretende serlo: aqui nadie
# ataca a nadie, solo se distingue una pieza de otra.
LARGO_DE_LA_HUELLA = 8


def huella_de_la_pieza(pieza: Pieza) -> str:
    """Identifica el CONTENIDO de una pieza, no su nombre.

    Sirve para dos cosas opuestas y las dos hacen falta:

    * Renombrar el archivo NO rompe el historial. Si el nombre entrara en la
      huella, mover una cancion de carpeta tiraria el progreso de meses.
    * Editar la pieza SI lo rompe, y debe romperlo. Si alguien reescribe el
      compas 19, los desfases viejos de ese compas ya no hablan de esto, y
      compararlos seria comparar cosas distintas.

    Entra lo que cambia donde suena cada nota: el tempo escrito, el compas, la
    afinacion con que se escribio y las notas. No entra el nombre.
    """
    partes = [
        pieza.perfil,
        str(pieza.tempo),
        f"{pieza.compas[0]}/{pieza.compas[1]}",
        *(
            f"{n.midi}:{n.cuerda}:{n.traste}:{n.inicio_pulsos:g}:{n.duracion_pulsos:g}"
            for n in pieza.notas
        ),
    ]
    digerido = hashlib.sha256("|".join(partes).encode("utf-8")).hexdigest()
    return digerido[:LARGO_DE_LA_HUELLA]


@dataclass(frozen=True)
class CompasDelRegistro:
    """Lo que se recuerda de un compas de una pasada.

    Es `CompasDelInforme` con lo que no sirve para comparar quitado y el desfase
    en milisegundos, que es la unidad en que se habla de esto. `desfase_medio_ms`
    LLEVA SIGNO -negativo es adelantarse, igual que `NotaTocada.desfase_s`-
    porque perder el signo convierte «te adelantas 40 ms» en «fallas 40 ms», y lo
    segundo no es accionable.

    **`tiene_acordes` ESTA AQUI PORQUE SIN EL EL HISTORIAL MIENTE, y se descubrio
    construyendo.** El diseño no lo pedia: parecia un detalle de como se midio, no
    un dato que comparar. Pero `nucleo.piezas.estudio.proporcion_limpia` EXCLUYE
    los compases con acordes -su propio docstring explica por que- y devuelve
    `None` para una pieza entera de acordes, que es «no se puede medir» y no
    «cero». Sin este campo, quien lea el historial no puede aplicar esa regla, y
    lo que pasa entonces esta medido: con el ejercicio de cambios, un compas de
    acorde tiene UNA nota medible -un rasgueo, un ataque-, asi que la proporcion
    limpia solo puede salir 0 % o 100 %. Al gemelo PRINCIPIANTE, que fallaba una
    cuerda de cinco y llegaba 650 ms tarde, la herramienta le dijo
    **«100,0 % limpio»**. Eso es exactamente el anti objetivo del diseño -que el
    historial mienta sobre el progreso- y lo unico que lo impide es guardar esto.
    """

    numero: int
    escritas: int
    medibles: int
    acertadas: int
    limpias: int
    desfase_medio_ms: float | None
    tiene_acordes: bool

    def a_dict(self) -> dict:
        return {
            "numero": self.numero,
            "escritas": self.escritas,
            "medibles": self.medibles,
            "acertadas": self.acertadas,
            "limpias": self.limpias,
            "desfase_medio_ms": self.desfase_medio_ms,
            "tiene_acordes": self.tiene_acordes,
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> CompasDelRegistro:
        return cls(
            numero=int(datos["numero"]),
            escritas=int(datos["escritas"]),
            medibles=int(datos["medibles"]),
            acertadas=int(datos["acertadas"]),
            limpias=int(datos["limpias"]),
            desfase_medio_ms=(
                None
                if datos["desfase_medio_ms"] is None
                else float(datos["desfase_medio_ms"])
            ),
            tiene_acordes=bool(datos["tiene_acordes"]),
        )


@dataclass(frozen=True)
class RegistroDePasada:
    """Una pasada CERRADA, con lo que hace falta para compararla con otra.

    Una pasada que seguia abierta cuando se acabo el audio no se anota, con el
    mismo criterio que `RegistroDeLaCadena.vueltas` ya aplica y por la misma
    razon: nadie la cerro, e inventarle un cierre seria anotar una vuelta que el
    conductor no anoto.
    """

    instante: datetime
    nombre_de_la_pieza: str
    huella: str
    tramo: tuple[int, int]
    factor_tempo: float
    repeticiones: int
    compases: tuple[CompasDelRegistro, ...]

    @property
    def clave_comparable(self) -> tuple[str, int, int, float]:
        """Lo que tienen que compartir dos pasadas para poder compararse.

        La huella y no el nombre -una pieza renombrada sigue siendo la misma-, el
        tramo, y el factor de tempo REDONDEADO a dos decimales: el deslizador
        avanza de 5 en 5 %, asi que mas precision solo crearia series de una sola
        pasada por error de coma flotante.
        """
        return (self.huella, self.tramo[0], self.tramo[1], round(self.factor_tempo, 2))

    @classmethod
    def desde_el_informe(
        cls,
        instante: datetime,
        pieza: Pieza,
        plan: PlanDePasada,
        informe: InformeDePasada,
    ) -> RegistroDePasada:
        """Anota lo que el informe ya calculo. No mide nada nuevo.

        El tramo sale del plan y no del informe porque `ultimo_compas` a None es
        «hasta el final» y el informe ya trae los compases resueltos: el ultimo
        que anoto es el ultimo del tramo.
        """
        numeros = [c.numero for c in informe.compases]
        primero = plan.primer_compas
        ultimo = plan.ultimo_compas if plan.ultimo_compas is not None else (
            max(numeros) if numeros else primero
        )
        return cls(
            instante=instante,
            nombre_de_la_pieza=pieza.nombre,
            huella=huella_de_la_pieza(pieza),
            tramo=(primero, ultimo),
            factor_tempo=informe.factor_tempo,
            repeticiones=informe.repeticiones,
            compases=tuple(
                CompasDelRegistro(
                    numero=c.numero,
                    escritas=c.notas_escritas,
                    medibles=c.notas_medibles,
                    acertadas=c.acertadas,
                    limpias=c.limpias,
                    desfase_medio_ms=(
                        None
                        if c.desfase_medio_s is None
                        else round(c.desfase_medio_s * 1000.0, 1)
                    ),
                    tiene_acordes=c.tiene_acordes,
                )
                for c in informe.compases
            ),
        )

    def a_dict(self) -> dict:
        return {
            "instante": self.instante.isoformat(timespec="seconds"),
            "pieza": {"nombre": self.nombre_de_la_pieza, "huella": self.huella},
            "tramo": [self.tramo[0], self.tramo[1]],
            "factor_tempo": self.factor_tempo,
            "repeticiones": self.repeticiones,
            "compases": [c.a_dict() for c in self.compases],
        }

    @classmethod
    def desde_dict(cls, datos: dict) -> RegistroDePasada:
        tramo = datos["tramo"]
        return cls(
            instante=datetime.fromisoformat(datos["instante"]),
            nombre_de_la_pieza=datos["pieza"]["nombre"],
            huella=datos["pieza"]["huella"],
            tramo=(int(tramo[0]), int(tramo[1])),
            factor_tempo=float(datos["factor_tempo"]),
            repeticiones=int(datos["repeticiones"]),
            compases=tuple(
                CompasDelRegistro.desde_dict(c) for c in datos["compases"]
            ),
        )


@dataclass(frozen=True)
class Historial:
    """Las pasadas que el programa recuerda, en orden de instante."""

    pasadas: tuple[RegistroDePasada, ...] = ()

    def con(self, pasada: RegistroDePasada) -> Historial:
        """El historial con una pasada mas, ordenado. No muta: devuelve otro."""
        return Historial(
            pasadas=tuple(sorted((*self.pasadas, pasada), key=lambda r: r.instante))
        )


def _limpias_de(pasada: RegistroDePasada) -> int:
    return sum(c.limpias for c in pasada.compases)


def recortar(historial: Historial, ahora: datetime) -> Historial:
    """Conserva enteros los ultimos `DIAS_COMPLETOS` y adelgaza lo anterior.

    De lo viejo queda UNA pasada por clave comparable y dia: la que mas notas
    limpias dejo. Asi la tendencia de un año sigue viendose y el archivo no crece
    con las cuarenta vueltas que alguien dio un martes.

    **Y por eso se conserva la MEJOR y no la ultima.** Sin esto, las cuarenta
    vueltas de un martes pesan cuarenta veces mas en la historia que la unica de
    un miercoles, y la tendencia acaba hablando de cuanto repetiste en vez de
    cuanto mejoraste.

    El recorte respeta la clave comparable entera -huella, tramo y tempo-, no
    solo la pieza: dos tempos del mismo compas son dos series distintas (spec
    §4.4), y juntarlas dejaria la serie de un tempo con un agujero cada vez que
    ese dia hubo una pasada mejor del otro.
    """
    frontera = ahora.timestamp() - DIAS_COMPLETOS * 86400.0
    recientes = []
    mejores: dict[tuple, RegistroDePasada] = {}
    for pasada in historial.pasadas:
        if pasada.instante.timestamp() >= frontera:
            recientes.append(pasada)
            continue
        clave = (*pasada.clave_comparable, pasada.instante.date())
        guardada = mejores.get(clave)
        if guardada is None or _limpias_de(pasada) > _limpias_de(guardada):
            mejores[clave] = pasada
    quedan = [*mejores.values(), *recientes]
    return Historial(pasadas=tuple(sorted(quedan, key=lambda r: r.instante)))


def guardar(
    historial: Historial,
    ruta: Path,
    serializar: Callable[[dict], str] | None = None,
) -> None:
    """Escribe el historial ENTERO o no escribe nada.

    A un temporal y luego `os.replace`, que es atomico en el mismo sistema de
    archivos: si el programa muere a mitad, el historial anterior sigue integro.
    Un historial medio escrito es peor que ninguno, porque el lector no puede
    saber que esta roto.

    El JSON va indentado y con las claves en español porque el cuarto objetivo
    del diseño es que el historial se entienda ABRIENDOLO, sin el programa. Una
    linea de 40 kB cumpliria el formato y no el objetivo.

    `serializar` es la costura de la prueba de atomicidad, que necesita mirar el
    archivo definitivo MIENTRAS el temporal se escribe. No tiene otro uso.
    """
    datos = {
        "version": VERSION,
        "pasadas": [p.a_dict() for p in historial.pasadas],
    }
    texto = (
        json.dumps(datos, ensure_ascii=False, indent=2)
        if serializar is None
        else serializar(datos)
    )
    temporal = ruta.with_name(ruta.name + ".parcial")
    temporal.write_text(texto, encoding="utf-8")
    os.replace(temporal, ruta)


def cargar(ruta: Path) -> Historial:
    """Lee el historial. Un archivo que no existe es el primer dia, no un error.

    **UN ARCHIVO QUE NO SE ENTIENDE NO SE BORRA, SE APARTA.** Se renombra a
    `.roto` y se empieza uno nuevo. Dentro estan los fallos de alguien, anotados
    sesion a sesion: borrarlos porque el programa no entiende el formato -que
    puede ser el de un programa mas nuevo- seria inadmisible. Apartado, el
    usuario puede abrirlo y, si el programa se equivoco, recuperarlo.
    """
    if not ruta.exists():
        return Historial()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if int(datos["version"]) != VERSION:
            raise ValueError(
                f"historial en version {datos['version']}, se esperaba {VERSION}"
            )
        return Historial(
            pasadas=tuple(
                RegistroDePasada.desde_dict(p) for p in datos["pasadas"]
            )
        )
    except (ValueError, KeyError, TypeError, OSError) as error:
        apartado = ruta.with_name(ruta.name + ".roto")
        _registro.error(
            "No se entiende %s (%s). Se aparta en %s y se empieza uno nuevo.",
            ruta,
            error,
            apartado,
        )
        try:
            os.replace(ruta, apartado)
        except OSError as fallo:
            _registro.error("Tampoco se pudo apartar %s: %s", ruta, fallo)
        return Historial()
