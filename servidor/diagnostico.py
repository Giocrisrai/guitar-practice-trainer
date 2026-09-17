"""Distingue los tres fallos que para el usuario se ven todos igual: no pasa nada."""

from dataclasses import dataclass

from nucleo.captura import DispositivoAudio


@dataclass(frozen=True)
class Diagnostico:
    """Estado del montaje, con una acción concreta que el usuario puede ejecutar."""

    estado: str
    mensaje: str
    accion: str
    dispositivos: list[DispositivoAudio]

    def a_dict(self) -> dict:
        return {
            "estado": self.estado,
            "mensaje": self.mensaje,
            "accion": self.accion,
            "dispositivos": [
                {
                    "indice": d.indice,
                    "nombre": d.nombre,
                    "canales_entrada": d.canales_entrada,
                    "frecuencia_muestreo": d.frecuencia_muestreo,
                }
                for d in self.dispositivos
            ],
        }


def diagnosticar(
    dispositivos: list[DispositivoAudio],
    cable: DispositivoAudio | None,
    nivel_db: float | None = None,
    umbral_dbfs: float = -60.0,
) -> Diagnostico:
    """Determina en cuál de los cuatro estados está el montaje.

    nivel_db en None significa que todavía no se ha medido nada: en ese caso no se
    declara falta de señal, porque sería acusar en falso antes de mirar.
    """
    if not dispositivos:
        return Diagnostico(
            estado="sin_permiso",
            mensaje="No se ve ninguna entrada de audio en el sistema.",
            accion=(
                "macOS no ha dado permiso de micrófono a esta aplicación. "
                "Ve a Ajustes del Sistema → Privacidad y seguridad → Micrófono "
                "y actívalo para el programa desde el que lanzaste esto."
            ),
            dispositivos=dispositivos,
        )

    if cable is None:
        return Diagnostico(
            estado="sin_dispositivo",
            mensaje="El cable Rocksmith no aparece entre los dispositivos.",
            accion=(
                "Comprueba que el cable esté conectado al puerto USB. "
                "Si lo está, prueba otro puerto o elige el dispositivo a mano."
            ),
            dispositivos=dispositivos,
        )

    if nivel_db is not None and nivel_db <= umbral_dbfs:
        return Diagnostico(
            estado="sin_senal",
            mensaje="El cable está conectado pero no llega señal.",
            accion=(
                "Sube el volumen de la guitarra: es la causa más frecuente. "
                "Verifica también que el jack esté bien insertado en el instrumento."
            ),
            dispositivos=dispositivos,
        )

    return Diagnostico(
        estado="ok",
        mensaje=f"Cable conectado: {cable.nombre}",
        accion="",
        dispositivos=dispositivos,
    )
