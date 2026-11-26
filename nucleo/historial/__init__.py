"""El historial de pasadas: lo que el programa recuerda de lo que tocaste.

Hasta aqui el programa no recordaba nada. `InformeDePasada` se calculaba, se
servia por HTTP, se pintaba y se perdia; lo unico que persistia en todo el
repositorio era `config_local.json`, y ahi solo hay el dispositivo y la
afinacion. Eso no era una incomodidad: era la razon por la que el programa no
podia decirle al alumno lo unico que de verdad querria saber, que es si esta
mejor que la semana pasada.

El diseño esta en
`docs/superpowers/specs/2026-11-25-historial-y-progreso-design.md`.
"""
