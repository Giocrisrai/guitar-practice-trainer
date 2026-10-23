/** Formas exactas de los endpoints de la biblioteca de canciones (servidor/app.py). */

import type { Pieza } from "./tiposPieza";

/**
 * Los cuatro formatos que el servidor sabe leer, con el nombre EXACTO con el que
 * los publica (`FORMATOS`, nucleo/piezas/lectores.py). Se escriben aquí como un
 * tipo cerrado y no como `string` porque la pantalla los muestra tal cual: si
 * mañana el núcleo renombra uno, lo que hay que cambiar es esta línea y no buscar
 * una cadena suelta por la interfaz.
 */
export type FormatoCancion = "Guitar Pro" | "MIDI" | "MusicXML" | "Tablatura de texto";

/**
 * Una canción de la carpeta, tal y como la devuelven `GET /api/canciones` y
 * `POST /api/canciones` (`Biblioteca._entrada`, servidor/canciones.py).
 *
 * `id` ES el nombre del archivo CON extensión, porque la carpeta es la base de
 * datos y no hay otro sitio donde guardar un identificador. `nombre` es el mismo
 * sin extensión, y es lo que se le muestra al usuario. No son intercambiables: lo
 * que viaja en la URL es el `id`.
 */
export interface FichaCancion {
  id: string;
  nombre: string;
  formato: FormatoCancion;
  bytes: number;
  /** Cuándo se modificó el archivo, en ISO 8601 y en UTC. */
  modificado: string;
}

/**
 * La afinación que pide un juego de cuerdas al aire (`afinacion_de`,
 * servidor/canciones.py).
 *
 * `clave` es la del perfil al que hay que afinarse, y es lo que hace ACCIONABLE el
 * aviso: con ella la pantalla puede ofrecer el botón que cambia la afinación
 * activa. `null` significa que no hay ningún perfil al que afinarse, así que ahí
 * no se ofrece botón: un botón que no lleva a ninguna parte es peor que ninguno.
 *
 * `declarada` dice si el ARCHIVO trae afinación. MIDI y MusicXML sin tablatura no
 * la traen, y entonces no hay nada que avisar.
 */
export interface AfinacionCancion {
  clave: string | null;
  nombre: string;
  cuerdas_midi: number[];
  declarada: boolean;
}

/**
 * Una pista del archivo, descrita sin convertirla (`PistaDisponible.a_dict()`,
 * nucleo/piezas/lectores.py, más la `afinacion` que añade el servidor).
 *
 * `numero` va en BASE 1 y es lo único que identifica una pista: es el que publica
 * `/pistas` y el mismo que entienden `/importar` y `/piezas/iniciar`. No hay
 * `indice` en base 0 al lado, a propósito.
 *
 * `motivo_no_usable` es la frase, escrita para el usuario, que explica por qué una
 * pista no se puede importar (una de percusión, una vacía, una que no cabe en el
 * mástil). Se muestra tal cual y se enseña junto a la pista: una pista que no se
 * puede elegir sin decir por qué parece un programa roto.
 *
 * **`afinacion` y `coincide` son los de ESTA pista, y son los que deciden.** Lo que
 * se importa es una pista, no una canción: un `.gp5` con la pista 1 en estándar y la
 * pista 2 en Drop C trae un `coincide` de nivel canción que dice `true` -es el de la
 * primera pista usable- mientras la pista 2 da un 400 al arrancar. Significan
 * exactamente lo mismo que los de `DetalleCancion`, incluidos los tres valores de
 * `coincide`, y los decide el mismo servidor con la misma cuenta.
 */
export interface PistaDisponible {
  numero: number;
  nombre: string;
  instrumento: string;
  cuerdas_midi: number[];
  notas: number;
  usable: boolean;
  motivo_no_usable: string | null;
  afinacion: AfinacionCancion;
  coincide: boolean | null;
}

/**
 * Lo que devuelve `GET /api/canciones/{id}/pistas`: la ficha, las pistas y la
 * afinación que pide la canción comparada con la activa.
 *
 * `afinacion` y `coincide` de aquí son los de **la primera pista usable**, que es la
 * que se importará si el usuario no elige otra: valen para avisar ANTES de elegir
 * pista. En cuanto hay una elegida, los que cuentan son los de ella
 * (`PistaDisponible.afinacion`, `PistaDisponible.coincide`).
 *
 * **`coincide` tiene TRES valores y los tres significan cosas distintas:**
 *
 * - `true`: la canción está en la afinación activa. No hay nada que avisar.
 * - `false`: pide otra. Aquí va el aviso, con `afinacion.nombre`, y el botón al
 *   afinador si `afinacion.clave` no es `null`.
 * - `null`: el archivo NO DICE en qué afinación está (MIDI, MusicXML sin
 *   tablatura). Tampoco hay nada que avisar: la pieza se importa en el perfil
 *   activo y el carril la acepta. Tratarlo como `false` es lo que hacía que la
 *   pantalla dijera «no cuadra, aféinate a null».
 */
export interface DetalleCancion extends FichaCancion {
  pistas: PistaDisponible[];
  afinacion: AfinacionCancion;
  perfil_activo: string;
  coincide: boolean | null;
}

/**
 * Lo que devuelve `POST /api/canciones/{id}/importar`: la pieza entera y sus
 * avisos, SIN ponerla en marcha.
 *
 * **Los `avisos` vienen del servidor como frases ya escritas** (`_avisos_de`,
 * servidor/app.py) y se muestran tal cual: el del ritmo aproximado es uno de
 * ellos. La pantalla no decide ninguno ni los reescribe; el único aviso que sale
 * de aquí es el de los acordes, y ése es un cálculo sobre las notas que ya vienen
 * (ver `tieneAcordes` en `Canciones.tsx`), no una decisión que el núcleo publique.
 */
export interface PiezaImportada extends Pieza {
  avisos: string[];
}
