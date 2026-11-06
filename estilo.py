"""Estilo de la consola: colores ANSI y tablas con bordes.

No usa librerias externas. Los colores se activan solo si la salida es una
terminal y no se pidio desactivarlos (opcion ``--sin-color`` o variable de
entorno ``NO_COLOR``). Si la terminal no puede mostrar los caracteres de
borde Unicode, las tablas se dibujan con ``+``, ``-`` y ``|``.
"""

import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

_PATRON_ANSI = re.compile(r"\x1b\[[0-9;]*m")

CODIGOS = {
    "negrita": "1",
    "tenue": "2",
    "rojo": "91",
    "verde": "92",
    "amarillo": "93",
    "azul": "94",
    "magenta": "95",
    "cian": "96",
    "blanco": "97",
    "gris": "90",
    "negro": "30",
    "fondo_rojo": "41",
    "fondo_verde": "42",
    "fondo_amarillo": "43",
    "fondo_azul": "44",
    "fondo_magenta": "45",
    "fondo_cian": "46",
    "fondo_blanco": "47",
    "fondo_gris": "100",
}

# Colores asignados a cada proceso (en orden de carga) para que se reconozca
# igual en el mapa de memoria, el diagrama de Gantt y las tablas.
PALETA_PROCESOS = ("cian", "amarillo", "verde", "azul", "rojo", "blanco")

# Equivalentes ASCII de los caracteres especiales (mismo ancho: 1 a 1).
_A_ASCII = str.maketrans({
    "┌": "+", "┬": "+", "┐": "+", "├": "+", "┼": "+", "┤": "+",
    "└": "+", "┴": "+", "┘": "+", "─": "-", "│": "|", "═": "=",
    "█": "#", "░": ".", "▒": ":", "►": ">", "◄": "<", "·": ".",
    "→": ">", "≤": "<",
})


def quitar_colores(texto: str) -> str:
    """Elimina los codigos de color ANSI."""
    return _PATRON_ANSI.sub("", texto)


def a_ascii(texto: str) -> str:
    """Reemplaza bordes y simbolos Unicode por equivalentes ASCII."""
    return texto.translate(_A_ASCII)

_BORDES_UNICODE = {
    "sup": ("┌", "┬", "┐"),
    "med": ("├", "┼", "┤"),
    "inf": ("└", "┴", "┘"),
    "h": "─",
    "v": "│",
}
_BORDES_ASCII = {
    "sup": ("+", "+", "+"),
    "med": ("+", "+", "+"),
    "inf": ("+", "+", "+"),
    "h": "-",
    "v": "|",
}


def largo_visible(texto: str) -> int:
    """Largo del texto en pantalla, sin contar los codigos de color."""
    return len(_PATRON_ANSI.sub("", texto))


def rellenar(texto: str, ancho: int, alineacion: str = "<") -> str:
    """Completa con espacios hasta ``ancho`` columnas visibles."""
    falta = max(0, ancho - largo_visible(texto))
    if alineacion == ">":
        return " " * falta + texto
    if alineacion == "^":
        izquierda = falta // 2
        return " " * izquierda + texto + " " * (falta - izquierda)
    return texto + " " * falta


@dataclass(frozen=True)
class Celda:
    """Valor de una tabla con estilos de color opcionales."""

    texto: object
    estilos: Tuple[str, ...] = ()
    alineacion: Optional[str] = None


ValorCelda = Union[Celda, object]


class Estilo:
    """Decide si se usan colores y bordes Unicode, y aplica el formato."""

    def __init__(self, color: bool = False, unicode: bool = False) -> None:
        self.color = color
        self.unicode = unicode
        self.bordes = _BORDES_UNICODE if unicode else _BORDES_ASCII

    @classmethod
    def detectar(cls, flujo=None, sin_color: bool = False) -> "Estilo":
        flujo = flujo if flujo is not None else sys.stdout
        es_terminal = hasattr(flujo, "isatty") and flujo.isatty()
        color = (
            es_terminal
            and not sin_color
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb"
        )
        codificacion = getattr(flujo, "encoding", None) or "ascii"
        try:
            "┌─┐│└┘├┼┤┬┴═".encode(codificacion)
            unicode = es_terminal
        except (LookupError, UnicodeEncodeError):
            unicode = False
        return cls(color=color, unicode=unicode)

    def c(self, texto: object, *estilos: str) -> str:
        """Aplica estilos de color a un texto (si los colores estan activos)."""
        texto = str(texto)
        if not self.color or not estilos:
            return texto
        codigos = ";".join(CODIGOS[nombre] for nombre in estilos if nombre)
        return f"\x1b[{codigos}m{texto}\x1b[0m" if codigos else texto

    def linea(self, ancho: int, doble: bool = False) -> str:
        """Linea horizontal de separacion."""
        if self.unicode:
            return ("═" if doble else "─") * ancho
        return ("=" if doble else "-") * ancho

    def tabla(
        self,
        encabezados: Sequence[str],
        filas: Sequence[Sequence[ValorCelda]],
        titulo: str = "",
        color_titulo: Sequence[str] = ("negrita", "cian"),
        vacia: str = "(vacia)",
    ) -> List[str]:
        """Dibuja una tabla con bordes y la retorna como lista de lineas.

        Los numeros se alinean a la derecha y el texto a la izquierda. Si no
        hay filas, se muestra una fila con el texto ``vacia``.
        """
        celdas: List[List[Celda]] = []
        for fila in filas:
            celdas.append([
                valor if isinstance(valor, Celda) else Celda(valor)
                for valor in fila
            ])

        anchos = [len(str(nombre)) for nombre in encabezados]
        for fila in celdas:
            for indice, celda in enumerate(fila):
                anchos[indice] = max(anchos[indice], largo_visible(str(celda.texto)))
        ancho_interior = sum(anchos) + 3 * len(anchos) - 1
        if not celdas:
            ancho_extra = len(vacia) + 2 - ancho_interior
            if ancho_extra > 0:
                anchos[-1] += ancho_extra
                ancho_interior += ancho_extra

        b = self.bordes
        gris = ("gris",)

        def borde(tipo: str) -> str:
            izquierda, medio, derecha = b[tipo]
            tramo = medio.join(b["h"] * (ancho + 2) for ancho in anchos)
            return self.c(izquierda + tramo + derecha, *gris)

        separador = self.c(b["v"], *gris)

        def formar(valores: Sequence[Celda], negrita: bool = False) -> str:
            partes = []
            for celda, ancho in zip(valores, anchos):
                alineacion = celda.alineacion or (
                    ">" if _es_numero(celda.texto) else "<"
                )
                texto = rellenar(str(celda.texto), ancho, alineacion)
                estilos = celda.estilos + (("negrita",) if negrita else ())
                partes.append(" " + self.c(texto, *estilos) + " ")
            return separador + separador.join(partes) + separador

        lineas = []
        if titulo:
            ancho_total = ancho_interior + 2
            lineas.append(rellenar(self.c(titulo, *color_titulo), ancho_total, "^")
                          if len(titulo) <= ancho_total
                          else self.c(titulo, *color_titulo))
        lineas.append(borde("sup"))
        lineas.append(formar([Celda(e, ("cian",)) for e in encabezados], negrita=True))
        lineas.append(borde("med"))
        if celdas:
            lineas.extend(formar(fila) for fila in celdas)
        else:
            texto = rellenar(self.c(vacia, "gris"), ancho_interior, "^")
            lineas.append(separador + texto + separador)
        lineas.append(borde("inf"))
        return lineas


def _es_numero(valor: object) -> bool:
    if isinstance(valor, bool):
        return False
    if isinstance(valor, (int, float)):
        return True
    texto = str(valor).strip()
    return bool(texto) and texto.replace(".", "", 1).isdigit()


def acomodar_en_filas(
    bloques: Sequence[List[str]], ancho_maximo: int, separacion: int = 3
) -> List[str]:
    """Ubica bloques de lineas uno al lado del otro mientras entren.

    Los que no entran en el ancho disponible pasan a la fila siguiente.
    """
    lineas: List[str] = []
    fila_actual: List[List[str]] = []
    ancho_actual = 0

    def volcar() -> None:
        if not fila_actual:
            return
        anchos = [max(largo_visible(l) for l in bloque) for bloque in fila_actual]
        alto = max(len(bloque) for bloque in fila_actual)
        if lineas:
            lineas.append("")
        for indice in range(alto):
            partes = []
            for bloque, ancho in zip(fila_actual, anchos):
                texto = bloque[indice] if indice < len(bloque) else ""
                partes.append(rellenar(texto, ancho))
            lineas.append((" " * separacion).join(partes).rstrip())

    for bloque in bloques:
        if not bloque:
            continue
        ancho = max(largo_visible(linea) for linea in bloque)
        necesario = ancho if not fila_actual else ancho_actual + separacion + ancho
        if fila_actual and necesario > ancho_maximo:
            volcar()
            fila_actual, ancho_actual = [], 0
            necesario = ancho
        fila_actual.append(bloque)
        ancho_actual = necesario
    volcar()
    return lineas


def preparar_terminal() -> None:
    """Habilita colores ANSI y UTF-8 en la consola de Windows."""
    if os.name != "nt":
        return
    os.system("")  # activa el procesamiento de secuencias ANSI en conhost
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None and flujo.isatty():
            try:
                reconfigurar(encoding="utf-8")
            except (ValueError, OSError):
                pass
