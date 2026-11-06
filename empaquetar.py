"""Genera el paquete de entrega de KernelFlow.

Uso (desde la raiz del proyecto):

    python3 -m pip install pyinstaller
    python3 empaquetar.py                  (deja el paquete en entrega/)
    python3 empaquetar.py otra_carpeta     (elige la carpeta de salida)

PyInstaller no compila para otro sistema operativo: el ejecutable de Linux se
genera en Linux y el de Windows en Windows. El resultado queda en
``entrega/KernelFlow-<sistema>.zip`` con esta estructura:

    KernelFlow-<sistema>/
    |-- HOWTO.txt
    |-- ejecutable/
    |   |-- KernelFlow(.exe)
    |   `-- data/            (lotes CSV y logo)
    `-- codigo_fuente/       (codigo, pruebas, datos y documentacion)
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ARCHIVOS_FUENTE = (
    "main.py",
    "proceso.py",
    "carga.py",
    "memoria.py",
    "estados.py",
    "admision.py",
    "planificador.py",
    "presentacion.py",
    "panel.py",
    "estilo.py",
    "exportar.py",
    "estadisticas.py",
    "kernelflow.spec",
    "empaquetar.py",
    "README.md",
    "HOWTO.md",
    "LICENSE",
)
CARPETAS_FUENTE = ("data", "tests", "docs")


def _nombre_sistema() -> str:
    sistema = platform.system().lower()
    return {"darwin": "macos"}.get(sistema, sistema)


def _ignorar_cache(_directorio, nombres):
    return [nombre for nombre in nombres if nombre == "__pycache__"]


def main(argumentos=None) -> int:
    argumentos = sys.argv[1:] if argumentos is None else argumentos
    carpeta_salida = RAIZ / (argumentos[0] if argumentos else "entrega")

    print("1/4 Ejecutando las pruebas...")
    pruebas = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=RAIZ,
    )
    if pruebas.returncode != 0:
        print("Las pruebas fallaron: no se genera el paquete.")
        return 1

    print("2/4 Generando el ejecutable con PyInstaller...")
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "kernelflow.spec"],
            cwd=RAIZ,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            "No se pudo ejecutar PyInstaller. Instalelo con:\n"
            "    python3 -m pip install pyinstaller"
        )
        return 1

    nombre_ejecutable = "KernelFlow.exe" if sys.platform == "win32" else "KernelFlow"
    ejecutable = RAIZ / "dist" / nombre_ejecutable
    if not ejecutable.is_file():
        print(f"No se encontro el ejecutable esperado: {ejecutable}")
        return 1

    print("3/4 Armando la carpeta de entrega...")
    nombre_paquete = f"KernelFlow-{_nombre_sistema()}"
    destino = carpeta_salida / nombre_paquete
    if destino.exists():
        shutil.rmtree(destino)

    carpeta_ejecutable = destino / "ejecutable"
    carpeta_ejecutable.mkdir(parents=True)
    shutil.copy2(ejecutable, carpeta_ejecutable / nombre_ejecutable)
    shutil.copytree(RAIZ / "data", carpeta_ejecutable / "data")

    carpeta_fuente = destino / "codigo_fuente"
    carpeta_fuente.mkdir()
    for archivo in ARCHIVOS_FUENTE:
        if (RAIZ / archivo).is_file():
            shutil.copy2(RAIZ / archivo, carpeta_fuente / archivo)
    for carpeta in CARPETAS_FUENTE:
        if (RAIZ / carpeta).is_dir():
            shutil.copytree(
                RAIZ / carpeta, carpeta_fuente / carpeta, ignore=_ignorar_cache
            )

    shutil.copy2(RAIZ / "HOWTO.md", destino / "HOWTO.txt")

    print("4/4 Comprimiendo...")
    archivo_zip = shutil.make_archive(
        str(destino), "zip", root_dir=destino.parent, base_dir=nombre_paquete
    )
    print(f"\nPaquete listo: {archivo_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
