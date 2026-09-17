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
    rocksmith: DispositivoAudio | None = None,
) -> Diagnostico:
    """Determina en cuál de los cinco estados está el montaje.

    - "sin_permiso": no se ve ninguna entrada de audio (macOS no dio permiso).
    - "sin_dispositivo": no hay ningún dispositivo en uso (`cable` es None).
    - "sin_senal": hay un dispositivo en uso pero el nivel medido no llega al
      umbral.
    - "otro_dispositivo": el dispositivo en uso no es el Rocksmith y el Rocksmith
      sí está presente en la lista; casi siempre significa que el usuario se
      equivocó al elegir, porque el cable está enchufado pero no seleccionado.
    - "ok": el dispositivo en uso tiene señal suficiente, sea o no el Rocksmith.
      Elegir otro dispositivo a propósito es una decisión legítima del usuario
      (por ejemplo para afinar una acústica con el micrófono); el diagnóstico no
      lo prohíbe, solo deja de llamarlo "cable" cuando no lo es.

    nivel_db en None significa que todavía no se ha medido nada: en ese caso no se
    declara falta de señal, porque sería acusar en falso antes de mirar.

    rocksmith es el cable Rocksmith encontrado por nombre en la lista, esté o no
    en uso; se usa solo para distinguir "otro_dispositivo" de una elección
    deliberada sin el cable presente.
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

    if rocksmith is not None and cable.indice != rocksmith.indice:
        return Diagnostico(
            estado="otro_dispositivo",
            mensaje=f"Estás usando {cable.nombre}, no el cable de la guitarra.",
            accion=(
                f"El {rocksmith.nombre} está conectado pero no seleccionado. "
                "Cámbialo en los ajustes si querías tocar la guitarra."
            ),
            dispositivos=dispositivos,
        )

    return Diagnostico(
        estado="ok",
        mensaje=f"Dispositivo activo: {cable.nombre}",
        accion="",
        dispositivos=dispositivos,
    )
