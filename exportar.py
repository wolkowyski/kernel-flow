"""Exporta una simulacion a archivos de texto y HTML.

El HTML conserva los colores de la terminal, para armar el informe con
capturas o adjuntarlo directamente.
"""

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from estilo import quitar_colores

_PATRON_SGR = re.compile(r"\x1b\[([0-9;]*)m")

_COLOR_TEXTO: Dict[str, str] = {
    "30": "#1e1e1e", "90": "#8b8b8b", "91": "#ff6b6b", "92": "#5fd068",
    "93": "#ffd75f", "94": "#6ca8ff", "95": "#e47cff", "96": "#4fd6e6",
    "97": "#ffffff",
}
_COLOR_FONDO: Dict[str, str] = {
    "41": "#e05555", "42": "#4cbf5a", "43": "#e6c34a", "44": "#4f86e0",
    "45": "#c45fe0", "46": "#3cc3d4", "47": "#e6e6e6", "100": "#6b6b6b",
}


def ansi_a_html(texto: str) -> str:
    """Convierte texto con codigos de color ANSI en HTML con estilos."""
    partes: List[str] = []
    estado: Dict[str, str] = {}
    abierto = False
    posicion = 0
    for coincidencia in _PATRON_SGR.finditer(texto):
        partes.append(html.escape(texto[posicion:coincidencia.start()]))
        posicion = coincidencia.end()
        if abierto:
            partes.append("</span>")
            abierto = False
        for codigo in (coincidencia.group(1) or "0").split(";"):
            if codigo in ("", "0"):
                estado.clear()
            elif codigo == "1":
                estado["font-weight"] = "bold"
            elif codigo == "2":
                estado["opacity"] = "0.7"
            elif codigo in _COLOR_TEXTO:
                estado["color"] = _COLOR_TEXTO[codigo]
            elif codigo in _COLOR_FONDO:
                estado["background"] = _COLOR_FONDO[codigo]
        if estado:
            estilo = ";".join(f"{clave}:{valor}" for clave, valor in estado.items())
            partes.append(f'<span style="{estilo}">')
            abierto = True
    partes.append(html.escape(texto[posicion:]))
    if abierto:
        partes.append("</span>")
    return "".join(partes)


def guardar_simulacion(
    pantallas: Sequence[str], carpeta: Path, nombre_lote: str
) -> Tuple[Path, Path]:
    """Guarda todas las pantallas en ``.txt`` y ``.html``; retorna sus rutas."""
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = carpeta / f"simulacion_{Path(nombre_lote).stem}_{marca}"
    contenido = "\n".join(pantallas)

    ruta_txt = base.with_suffix(".txt")
    ruta_txt.write_text(quitar_colores(contenido), encoding="utf-8")

    titulo = html.escape(f"KernelFlow - {nombre_lote}")
    documento = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{titulo}</title>
<style>
  body {{ background:#141414; color:#d4d4d4; margin:0; padding:24px; }}
  h1 {{ font-family:system-ui,sans-serif; font-size:18px; color:#4fd6e6; }}
  pre {{ font-family:Consolas,"DejaVu Sans Mono",monospace; font-size:13px;
        line-height:1.25; white-space:pre; }}
</style>
</head>
<body>
<h1>{titulo}</h1>
<pre>{ansi_a_html(contenido)}</pre>
</body>
</html>
"""
    ruta_html = base.with_suffix(".html")
    ruta_html.write_text(documento, encoding="utf-8")
    return ruta_txt, ruta_html
