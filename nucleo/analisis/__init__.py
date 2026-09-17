"""Análisis de audio: energía, detección de tono y ensamblado.

Importar `yin` aquí hace que el detector se registre al importar el paquete. Sin
esto, quien solo importe `registro` obtendría un registro vacío y `obtener("yin")`
fallaría con KeyError.
"""

from nucleo.analisis import yin as _yin  # noqa: F401  (import por su efecto de registro)
