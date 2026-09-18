"""Comprueba que el cable está conectado, llega señal y el análisis la reconoce.

Uso:  .venv/bin/python -m herramientas.verificar_cable
"""

import sys
import time

from nucleo.afinaciones import PERFILES
from nucleo.analisis.pipeline import Analizador
from nucleo.captura import CapturaAudio, buscar_rocksmith, listar_dispositivos_entrada


def main() -> int:
    dispositivos = listar_dispositivos_entrada()
    if not dispositivos:
        print("No se ve ninguna entrada de audio.")
        print("Causa más probable: macOS no ha dado permiso de micrófono a esta app.")
        print("Ajustes del Sistema → Privacidad y seguridad → Micrófono")
        return 1

    print(f"Entradas de audio detectadas: {len(dispositivos)}")
    for dispositivo in dispositivos:
        print(f"  [{dispositivo.indice}] {dispositivo.nombre}")

    cable = buscar_rocksmith(dispositivos)
    if cable is None:
        print("\nEl cable Rocksmith no aparece. Revisa que esté conectado al USB.")
        return 1
    print(f"\nCable encontrado: [{cable.indice}] {cable.nombre}")

    perfil = PERFILES["guitarra_estandar"]
    captura = CapturaAudio(indice_dispositivo=cable.indice, capacidad_buffer=96000)
    if not captura.iniciar():
        print(f"No se pudo abrir el dispositivo: {captura.ultimo_error}")
        return 1

    print(f"Latencia de entrada: {captura.latencia_ms:.1f} ms")
    print("\nToca cuerdas durante 10 segundos...\n")

    analizador = Analizador(perfil)
    ventana = perfil.tamano_ventana()
    final = time.monotonic() + 10.0
    notas_vistas = set()

    while time.monotonic() < final:
        muestras = captura.leer_ventana(ventana)
        if muestras is not None:
            resultado = analizador.procesar(muestras)
            if resultado.estado == "nota":
                notas_vistas.add(resultado.nota)
                print(
                    f"  {resultado.nota:>4}  {resultado.cents:+6.1f} cents  "
                    f"{resultado.frecuencia:7.2f} Hz  nivel {resultado.nivel_db:6.1f} dBFS",
                    end="\r",
                )
        time.sleep(0.03)

    captura.detener()
    print("\n")
    if not notas_vistas:
        print("No se detectó ninguna nota.")
        print("Revisa el volumen de la guitarra: es la causa más frecuente.")
        return 1
    print(f"Notas detectadas: {', '.join(sorted(notas_vistas))}")
    print(f"Desbordes de audio: {captura.desbordes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
