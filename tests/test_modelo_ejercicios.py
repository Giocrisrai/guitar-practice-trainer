import pytest

from nucleo.ejercicios.modelo import Ejercicio, IntentoNota, NotaEsperada, ResultadoEjercicio
from nucleo.musica import Posicion


def nota(midi: int, pulsos: float = 1.0) -> NotaEsperada:
    return NotaEsperada(midi=midi, posiciones=(Posicion(cuerda=6, traste=0),), pulsos=pulsos)


def test_la_nota_esperada_conoce_su_nombre():
    assert nota(40).nombre == "E2"


def test_una_nota_puede_tocarse_en_varios_sitios():
    """El ejercicio no exige una posicion concreta salvo que el generador la restrinja."""
    esperada = NotaEsperada(
        midi=45, posiciones=(Posicion(cuerda=5, traste=0), Posicion(cuerda=6, traste=5))
    )
    assert len(esperada.posiciones) == 2


def test_el_ejercicio_sabe_cuantas_notas_tiene():
    ejercicio = Ejercicio(
        clave="escala_do_mayor",
        nombre="Escala de Do mayor",
        descripcion="Una octava en la segunda posicion",
        notas=(nota(48), nota(50), nota(52)),
        tempo=80,
        perfil="guitarra_estandar",
    )
    assert len(ejercicio) == 3


def test_el_ejercicio_se_serializa_para_la_interfaz():
    ejercicio = Ejercicio(
        clave="prueba",
        nombre="Prueba",
        descripcion="",
        notas=(nota(40),),
        tempo=60,
        perfil="guitarra_estandar",
    )
    datos = ejercicio.a_dict()
    assert set(datos) == {"clave", "nombre", "descripcion", "notas", "tempo", "perfil"}
    assert datos["notas"][0] == {
        "midi": 40,
        "nombre": "E2",
        "posiciones": [{"cuerda": 6, "traste": 0}],
        "pulsos": 1.0,
        "referencia_midi": None,
    }


def test_una_nota_puede_llevar_una_referencia_que_suena_antes():
    """El entrenamiento de oido hace sonar una nota y pide otra a cierto intervalo."""
    esperada = NotaEsperada(
        midi=52, posiciones=(Posicion(cuerda=4, traste=2),), referencia_midi=48
    )
    assert esperada.referencia_midi == 48
    assert esperada.a_dict()["referencia_midi"] == 48


def test_sin_referencia_el_campo_es_none():
    assert nota(40).referencia_midi is None


def test_una_nota_sin_acertar_tiene_cents_none_no_cero():
    """Cero cents significa acierto perfecto; None significa que no se acerto."""
    fallada = IntentoNota(indice=0, midi=40, intentos=3, cents=None, instante=None)
    perfecta = IntentoNota(indice=1, midi=42, intentos=1, cents=0.0, instante=1.0)
    assert fallada.acertada is False
    assert perfecta.acertada is True


def test_a_la_primera_exige_acierto_y_un_solo_intento():
    assert IntentoNota(0, 40, 1, 0.0, 1.0).a_la_primera is True
    assert IntentoNota(0, 40, 2, 0.0, 1.0).a_la_primera is False
    assert IntentoNota(0, 40, 1, None, None).a_la_primera is False


def test_el_informe_cuenta_los_aciertos_a_la_primera():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 2.0, 0.0),
            IntentoNota(1, 42, 3, -4.0, 1.0),
            IntentoNota(2, 44, 1, 1.0, 2.0),
        ),
        completado=True,
    )
    assert resultado.aciertos_a_la_primera == 2


def test_el_informe_da_la_desviacion_mediana():
    """Mediana y no media: un golpe desafinado aislado no debe definir la sesion."""
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 2.0, 0.0),
            IntentoNota(1, 42, 1, 4.0, 1.0),
            IntentoNota(2, 44, 1, 60.0, 2.0),
        ),
        completado=True,
    )
    assert resultado.desviacion_mediana_cents == pytest.approx(4.0)


def test_las_notas_sin_acertar_no_entran_en_la_desviacion():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(IntentoNota(0, 40, 1, 6.0, 0.0), IntentoNota(1, 42, 5, None, None)),
        completado=False,
    )
    assert resultado.desviacion_mediana_cents == pytest.approx(6.0)


def test_sin_ninguna_nota_acertada_no_hay_desviacion():
    resultado = ResultadoEjercicio(
        ejercicio="prueba", notas=(IntentoNota(0, 40, 5, None, None),), completado=False
    )
    assert resultado.desviacion_mediana_cents is None


def test_las_notas_dificiles_son_las_que_costaron_tres_intentos_o_mas():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 0.0, 0.0),
            IntentoNota(1, 42, 3, 0.0, 1.0),
            IntentoNota(2, 44, 7, 0.0, 2.0),
        ),
        completado=True,
    )
    assert [n.midi for n in resultado.notas_dificiles] == [42, 44]


def test_la_regularidad_mide_constancia_no_velocidad():
    """Tocar lento pero parejo da una regularidad buena."""
    lento_parejo = ResultadoEjercicio(
        ejercicio="prueba",
        notas=tuple(IntentoNota(i, 40 + i, 1, 0.0, float(i) * 2.0) for i in range(4)),
        completado=True,
    )
    assert lento_parejo.regularidad_ms == pytest.approx(0.0, abs=0.01)


def test_la_regularidad_crece_con_la_irregularidad():
    irregular = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(
            IntentoNota(0, 40, 1, 0.0, 0.0),
            IntentoNota(1, 41, 1, 0.0, 1.0),
            IntentoNota(2, 42, 1, 0.0, 1.2),
            IntentoNota(3, 43, 1, 0.0, 3.0),
        ),
        completado=True,
    )
    assert irregular.regularidad_ms > 300.0


def test_con_menos_de_tres_notas_acertadas_no_hay_regularidad():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(IntentoNota(0, 40, 1, 0.0, 0.0), IntentoNota(1, 41, 1, 0.0, 1.0)),
        completado=True,
    )
    assert resultado.regularidad_ms is None


def test_el_resultado_se_serializa_para_la_interfaz():
    resultado = ResultadoEjercicio(
        ejercicio="prueba",
        notas=(IntentoNota(0, 40, 1, 2.0, 0.0), IntentoNota(1, 42, 3, -8.0, 1.0)),
        completado=True,
    )
    datos = resultado.a_dict()
    assert set(datos) == {
        "ejercicio",
        "completado",
        "notas",
        "aciertos_a_la_primera",
        "desviacion_mediana_cents",
        "regularidad_ms",
        "notas_dificiles",
    }
    assert datos["notas"][0]["nombre"] == "E2"
    # La nota con 3 intentos o mas es la unica que aparece como dificil: el
    # umbral (INTENTOS_NOTA_DIFICIL) lo decide el nucleo, no la interfaz.
    assert [n["indice"] for n in datos["notas_dificiles"]] == [1]
