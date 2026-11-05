"""Perfiles de destreza: como de bien toca el guitarrista sintetico.

Un perfil es una CONSTANTE DE FABRICA, no una configuracion: describe una forma
de tocar -perfecta, de principiante, de intermedio, de desastre- y las pruebas de
la etapa se apoyan en que esas cuatro no cambian. Por eso son `frozen`. Una
prueba que necesite una variante no anade un quinto perfil: usa
`dataclasses.replace(PERFECTO, sustain=1.0)`, que es la forma de la biblioteca
estandar y deja escrito en la propia prueba que lo unico que cambia es ese campo.

`PERFECTO` es el ORACULO de la etapa: no falla notas, no se desafina, no se
adelanta ni se atrasa y corta cada nota antes de la siguiente. Lo que la cadena
diga de una interpretacion perfecta y no sea «todo limpio» es un defecto de la
cadena, no del gemelo. Los otros tres existen para lo contrario: el perfil que
encuentra defectos es el malo.

Los numeros de los tres perfiles imperfectos son ELEGIDOS, no medidos contra
guitarristas de verdad: lo que importa de ellos es el orden (principiante peor
que intermedio en todos los campos) y que `CAOS` sea lo bastante bruto para
provocar los fantasmas del solape que la spec §10 quiere medir.
"""

from dataclasses import dataclass

# Campos que son probabilidades o fracciones y por tanto viven en [0, 1].
_CAMPOS_EN_LA_UNIDAD = (
    "probabilidad_de_fallo",
    "probabilidad_de_nota_mala",
    "probabilidad_de_trasteo",
    "sustain",
)

# Campos que son desviaciones tipicas o magnitudes: cero vale, negativo no.
_CAMPOS_NO_NEGATIVOS = (
    "desviacion_desfase_s",
    "cents_de_desafinacion",
    "desviacion_fuerza",
)


@dataclass(frozen=True)
class PerfilDeDestreza:
    """Una forma de tocar, como dato.

    Campos:
        nombre: clave en minusculas con la que se pide el perfil.
        desfase_medio_s: sesgo con signo. Positivo es tocar ATRASADO (la nota
            suena despues de su sitio), negativo adelantado.
        desviacion_desfase_s: temblor gaussiano alrededor de ese sesgo.
        probabilidad_de_fallo: que la nota no suene en absoluto.
        probabilidad_de_nota_mala: que suene a +-1 o +-2 semitonos de la escrita,
            que es el traste de al lado.
        probabilidad_de_trasteo: que suene pero rozando el traste.
        cents_de_desafinacion: desviacion tipica, en cents, de la altura real.
        fuerza_media: amplitud de pico media de la pulsacion.
        desviacion_fuerza: temblor gaussiano de esa amplitud.
        sustain: 0 corta siempre la nota antes de la siguiente, 1 la deja sonar
            su figura entera y un poco mas, hasta solaparse con la siguiente. Ver
            `nucleo.gemelo.interprete.duracion_de_la_nota_s`.
    """

    nombre: str
    desfase_medio_s: float
    desviacion_desfase_s: float
    probabilidad_de_fallo: float
    probabilidad_de_nota_mala: float
    probabilidad_de_trasteo: float
    cents_de_desafinacion: float
    fuerza_media: float
    desviacion_fuerza: float
    sustain: float

    def __post_init__(self) -> None:
        for nombre_del_campo in _CAMPOS_EN_LA_UNIDAD:
            valor = getattr(self, nombre_del_campo)
            if not 0.0 <= valor <= 1.0:
                raise ValueError(
                    f"El perfil '{self.nombre}' tiene {nombre_del_campo}={valor}: "
                    "tiene que estar entre 0 y 1"
                )
        for nombre_del_campo in _CAMPOS_NO_NEGATIVOS:
            valor = getattr(self, nombre_del_campo)
            if valor < 0.0:
                raise ValueError(
                    f"El perfil '{self.nombre}' tiene {nombre_del_campo}={valor}: "
                    "no puede ser negativo"
                )
        if not 0.0 < self.fuerza_media <= 1.0:
            raise ValueError(
                f"El perfil '{self.nombre}' tiene fuerza_media={self.fuerza_media}: "
                "tiene que estar entre 0 (excluido) y 1"
            )


PERFECTO = PerfilDeDestreza(
    nombre="perfecto",
    desfase_medio_s=0.0,
    desviacion_desfase_s=0.0,
    probabilidad_de_fallo=0.0,
    probabilidad_de_nota_mala=0.0,
    probabilidad_de_trasteo=0.0,
    cents_de_desafinacion=0.0,
    fuerza_media=0.8,
    desviacion_fuerza=0.0,
    sustain=0.0,
)

PRINCIPIANTE = PerfilDeDestreza(
    nombre="principiante",
    # Atrasado y tembloroso: el principiante llega tarde a la nota porque la
    # busca en el mastil antes de pulsarla.
    desfase_medio_s=0.030,
    desviacion_desfase_s=0.040,
    probabilidad_de_fallo=0.08,
    probabilidad_de_nota_mala=0.06,
    probabilidad_de_trasteo=0.18,
    cents_de_desafinacion=18.0,
    fuerza_media=0.55,
    desviacion_fuerza=0.18,
    # No apaga las cuerdas: deja sonar casi media figura de mas.
    sustain=0.35,
)

INTERMEDIO = PerfilDeDestreza(
    nombre="intermedio",
    desfase_medio_s=0.010,
    desviacion_desfase_s=0.018,
    probabilidad_de_fallo=0.02,
    probabilidad_de_nota_mala=0.015,
    probabilidad_de_trasteo=0.05,
    cents_de_desafinacion=8.0,
    fuerza_media=0.70,
    desviacion_fuerza=0.08,
    sustain=0.15,
)

CAOS = PerfilDeDestreza(
    nombre="caos",
    # Sin sesgo pero con un temblor enorme: cae a los dos lados de su sitio.
    desfase_medio_s=0.0,
    desviacion_desfase_s=0.090,
    probabilidad_de_fallo=0.20,
    probabilidad_de_nota_mala=0.25,
    probabilidad_de_trasteo=0.50,
    cents_de_desafinacion=35.0,
    fuerza_media=0.60,
    desviacion_fuerza=0.30,
    # El sustain alto es lo que provoca los ataques fantasma del solape, que la
    # spec §10 quiere poder medir y nombrar.
    sustain=0.90,
)

PERFILES_DE_DESTREZA: dict[str, PerfilDeDestreza] = {
    perfil.nombre: perfil for perfil in (PERFECTO, PRINCIPIANTE, INTERMEDIO, CAOS)
}
