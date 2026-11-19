"""Pruebas del evaluador de cambios de acorde.

Se prueba sin audio, igual que el evaluador monofonico de la etapa 2a: consume
ResultadoAcorde, que es un dato. Se escribe la secuencia exacta de alguien que
tarda dos segundos en el cambio o que deja muda la primera cuerda.
"""

import pytest

from nucleo.afinaciones import PERFILES_DE_FABRICA
from nucleo.analisis.acordes import ResultadoAcorde
from nucleo.ejercicios.cambios import CUADROS_PARA_ACORDE_ESTABLE, EvaluadorCambios
from nucleo.ejercicios.generadores.acordes import acorde_de_clave, generar_cambios
from nucleo.ejercicios.modelo import Ejercicio

CUADRO_S = 0.021
GUITARRA = PERFILES_DE_FABRICA["guitarra_estandar"]


def completo(midis) -> ResultadoAcorde:
    return ResultadoAcorde(
        estado="completo", nivel_db=-30.0, presencias={m: 0.8 for m in midis}, faltan=()
    )


def incompleto(midis, faltan) -> ResultadoAcorde:
    return ResultadoAcorde(
        estado="incompleto",
        nivel_db=-30.0,
        presencias={m: (0.2 if m in faltan else 0.8) for m in midis},
        faltan=tuple(sorted(faltan)),
    )


def silencio() -> ResultadoAcorde:
    return ResultadoAcorde(estado="silencio", nivel_db=-80.0)


def correr(evaluador, secuencia, desde: float = 0.0):
    """Mete una secuencia de resultados, un cuadro cada CUADRO_S."""
    estado = evaluador.estado
    instante = desde
    for resultado in secuencia:
        estado = evaluador.procesar(resultado, instante)
        instante += CUADRO_S
    return estado, instante


def evaluador() -> EvaluadorCambios:
    return EvaluadorCambios(generar_cambios(claves=("do", "sol"), repeticiones=1))


def sostenido(midis, cuantos: int = CUADROS_PARA_ACORDE_ESTABLE):
    return [completo(midis)] * cuantos


class TestAcierto:
    def test_el_acorde_sostenido_se_da_por_bueno_y_avanza(self):
        ev = evaluador()
        estado, _ = correr(ev, sostenido(ev.ejercicio.acordes[0].midis))
        assert estado.indice == 1

    def test_un_cuadro_suelto_no_basta(self):
        """A mitad del rasgueo el acorde puede estar completo por accidente."""
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado, _ = correr(ev, [completo(midis), incompleto(midis, {midis[0]})])
        assert estado.indice == 0

    def test_terminar_el_ejercicio_lo_marca_completado(self):
        ev = evaluador()
        instante = 0.0
        for acorde in ev.ejercicio.acordes:
            _, instante = correr(ev, sostenido(acorde.midis), instante)
            _, instante = correr(ev, [silencio()] * 5, instante)
        assert ev.estado.completado is True
        assert ev.estado.acorde_actual is None

    def test_un_ejercicio_terminado_ignora_los_cuadros_que_sigan_llegando(self):
        ev = evaluador()
        instante = 0.0
        for acorde in ev.ejercicio.acordes:
            _, instante = correr(ev, sostenido(acorde.midis), instante)
            _, instante = correr(ev, [silencio()] * 5, instante)
        total = ev.estado.indice
        correr(ev, sostenido(ev.ejercicio.acordes[0].midis), instante)
        assert ev.estado.indice == total

    def test_dos_acordes_iguales_seguidos_necesitan_soltar_entre_medias(self):
        """Sin esto, la cola del primero regala el segundo sin mover un dedo."""
        do = acorde_de_clave("do", GUITARRA)
        ejercicio = Ejercicio(
            clave="do_do",
            nombre="Do, Do",
            descripcion="",
            notas=(),
            acordes=(do, do),
            tempo=60,
            perfil="guitarra_estandar",
        )
        ev = EvaluadorCambios(ejercicio)
        estado, _ = correr(ev, sostenido(do.midis, CUADROS_PARA_ACORDE_ESTABLE * 4))
        assert estado.indice == 1, "sostener no puede valer por dos acordes"

    def test_soltar_y_volver_a_tocar_si_cuenta_por_dos(self):
        do = acorde_de_clave("do", GUITARRA)
        ejercicio = Ejercicio(
            clave="do_do",
            nombre="Do, Do",
            descripcion="",
            notas=(),
            acordes=(do, do),
            tempo=60,
            perfil="guitarra_estandar",
        )
        ev = EvaluadorCambios(ejercicio)
        _, instante = correr(ev, sostenido(do.midis))
        _, instante = correr(ev, [silencio()] * 5, instante)
        estado, _ = correr(ev, sostenido(do.midis), instante)
        assert estado.indice == 2

    def test_los_midis_esperados_son_los_del_acorde_que_toca_ahora(self):
        ev = evaluador()
        assert ev.midis_esperados == ev.ejercicio.acordes[0].midis
        correr(ev, sostenido(ev.ejercicio.acordes[0].midis))
        assert ev.midis_esperados == ev.ejercicio.acordes[1].midis


class TestFallo:
    def test_una_cuerda_muda_sale_nombrada_en_el_estado(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado, _ = correr(ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE)
        assert estado.faltan == (midis[-1],)
        assert estado.indice == 0

    def test_el_silencio_no_cuenta_como_intento(self):
        ev = evaluador()
        estado, _ = correr(ev, [silencio()] * 20)
        assert estado.intentos == 0
        assert estado.ayuda_visible is False

    def test_un_solo_rasgueo_torcido_cuenta_un_intento_y_no_cuatro(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        estado, _ = correr(ev, [incompleto(midis, {midis[-1]})] * 20)
        assert estado.intentos == 1

    def test_insistir_mal_cuenta_varios_intentos(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        instante = 0.0
        for _ in range(3):
            _, instante = correr(
                ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE, instante
            )
            _, instante = correr(ev, [silencio()] * 3, instante)
        assert ev.estado.intentos == 3

    def test_tras_los_intentos_pactados_aparece_la_ayuda_sin_saltar_el_acorde(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        instante = 0.0
        for _ in range(ev.intentos_para_ayuda):
            _, instante = correr(
                ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE, instante
            )
            _, instante = correr(ev, [silencio()] * 3, instante)
        assert ev.estado.ayuda_visible is True
        assert ev.estado.indice == 0

    def test_la_ayuda_aparece_tambien_por_tiempo(self):
        """Mismo respaldo que la 2a: no depende de lograr contar intentos."""
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        ev.procesar(incompleto(midis, {midis[-1]}), 0.0)
        estado = ev.procesar(incompleto(midis, {midis[-1]}), ev.segundos_para_ayuda + 0.1)
        assert estado.ayuda_visible is True

    def test_el_reloj_de_la_ayuda_no_corre_mientras_no_se_toca_nada(self):
        """Leer el diagrama no es estar atascado: la ayuda no se regala."""
        ev = evaluador()
        estado = ev.procesar(silencio(), 0.0)
        estado = ev.procesar(silencio(), ev.segundos_para_ayuda * 3)
        assert estado.ayuda_visible is False

    def test_acertar_despues_de_fallar_limpia_la_ayuda(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        instante = 0.0
        for _ in range(ev.intentos_para_ayuda):
            _, instante = correr(
                ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE, instante
            )
            _, instante = correr(ev, [silencio()] * 3, instante)
        _, instante = correr(ev, sostenido(midis), instante)
        assert ev.estado.ayuda_visible is False
        assert ev.estado.indice == 1


class TestTiempoDeCambio:
    def test_el_primer_acorde_no_tiene_tiempo_de_cambio(self):
        ev = evaluador()
        estado, _ = correr(ev, sostenido(ev.ejercicio.acordes[0].midis))
        assert estado.ultimo_cambio_s is None

    def test_el_segundo_mide_los_segundos_desde_el_primero(self):
        ev = evaluador()
        primero, segundo = ev.ejercicio.acordes[0], ev.ejercicio.acordes[1]
        _, instante = correr(ev, sostenido(primero.midis))
        logrado_primero = instante - CUADRO_S
        _, instante = correr(ev, [silencio()] * 50, instante)
        estado, fin = correr(ev, sostenido(segundo.midis), instante)
        esperado = (fin - CUADRO_S) - logrado_primero
        assert estado.ultimo_cambio_s == pytest.approx(esperado, abs=1e-6)
        assert estado.ultimo_cambio_s > 1.0

    def test_el_informe_promedia_los_tiempos_de_cambio(self):
        ev = evaluador()
        instante = 0.0
        for acorde in ev.ejercicio.acordes:
            _, instante = correr(ev, sostenido(acorde.midis), instante)
            _, instante = correr(ev, [silencio()] * 20, instante)
        informe = ev.resultado()
        assert informe.tiempo_medio_de_cambio_s is not None
        assert informe.tiempo_medio_de_cambio_s > 0.0

    def test_un_ejercicio_sin_ningun_cambio_logrado_no_promedia_nada(self):
        """Nunca cambiar no da un tiempo medio de cero: no da ninguno."""
        informe = evaluador().resultado()
        assert informe.tiempo_medio_de_cambio_s is None
        assert informe.cambio_mas_lento_s is None

    def test_un_solo_acorde_logrado_tampoco_da_tiempo_de_cambio(self):
        ev = evaluador()
        correr(ev, sostenido(ev.ejercicio.acordes[0].midis))
        assert ev.resultado().logrados == 1
        assert ev.resultado().tiempo_medio_de_cambio_s is None


class TestInforme:
    def test_el_informe_dice_que_cuerdas_fallaron_mas(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        instante = 0.0
        for _ in range(3):
            _, instante = correr(
                ev, [incompleto(midis, {midis[-1]})] * CUADROS_PARA_ACORDE_ESTABLE, instante
            )
            _, instante = correr(ev, [silencio()] * 3, instante)
        _, instante = correr(ev, sostenido(midis), instante)
        assert midis[-1] in ev.resultado().cuerdas_problematicas

    def test_un_acorde_que_sale_a_la_primera_cuenta_como_tal(self):
        ev = evaluador()
        correr(ev, sostenido(ev.ejercicio.acordes[0].midis))
        assert ev.resultado().a_la_primera == 1

    def test_un_acorde_que_salio_con_la_ayuda_puesta_no_cuenta_a_la_primera(self):
        ev = evaluador()
        midis = ev.ejercicio.acordes[0].midis
        ev.procesar(incompleto(midis, {midis[-1]}), 0.0)
        instante = ev.segundos_para_ayuda + 0.1
        ev.procesar(incompleto(midis, {midis[-1]}), instante)
        correr(ev, [silencio()] * 3, instante + CUADRO_S)
        correr(ev, sostenido(midis), instante + 0.2)
        assert ev.resultado().logrados == 1
        assert ev.resultado().a_la_primera == 0

    def test_el_informe_es_serializable(self):
        ev = evaluador()
        correr(ev, sostenido(ev.ejercicio.acordes[0].midis))
        como_dict = ev.resultado().a_dict()
        assert set(como_dict) == {
            "ejercicio",
            "completado",
            "acordes",
            "logrados",
            "a_la_primera",
            "tiempo_medio_de_cambio_s",
            "cambio_mas_lento_s",
            "cuerdas_problematicas",
        }

    def test_el_diccionario_del_estado_es_serializable(self):
        como_dict = evaluador().estado.a_dict()
        assert set(como_dict) == {
            "indice",
            "total",
            "intentos",
            "ayuda_visible",
            "completado",
            "acorde_actual",
            "faltan",
            "ultimo_cambio_s",
        }
        assert como_dict["acorde_actual"]["nombre"] == "Do mayor"


class TestContrato:
    def test_un_ejercicio_de_notas_no_se_puede_evaluar_aqui(self):
        from nucleo.ejercicios.generadores.escalas import generar_escala

        with pytest.raises(ValueError, match="acordes"):
            EvaluadorCambios(generar_escala())

    def test_cero_cuadros_de_estabilidad_se_rechaza(self):
        with pytest.raises(ValueError, match="cuadro"):
            EvaluadorCambios(generar_cambios(), cuadros_para_acorde_estable=0)

    def test_reiniciar_vuelve_al_principio(self):
        ev = evaluador()
        correr(ev, sostenido(ev.ejercicio.acordes[0].midis))
        ev.reiniciar()
        assert ev.estado.indice == 0
        assert ev.resultado().acordes == ()
