"""Punto de entrada y menu de consola del simulador KernelFlow."""

import argparse
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import textwrap
from typing import Callable, List, Optional, Sequence

from admision import Admision, ErrorAdmision
from carga import ErrorCargaProcesos, cargar_procesos
from estilo import Estilo, a_ascii, preparar_terminal, quitar_colores
from exportar import guardar_simulacion
from memoria import GestorMemoria
from panel import (
    PanelConsola,
    ancho_terminal as _ancho_terminal,
    centrar_linea as _prefijo_centrado,
    imprimir_bloque as _imprimir_bloque_centrado,
    imprimir_centrado as _imprimir_linea_centrada,
)
from planificador import PlanificadorSRTF
from presentacion import PresentacionConsola, seleccionar_archivo_csv


if getattr(sys, "frozen", False):
    # Ejecutable de PyInstaller: data/ se distribuye junto al ejecutable.
    DIRECTORIO_PROYECTO = Path(sys.executable).resolve().parent
else:
    DIRECTORIO_PROYECTO = Path(__file__).resolve().parent
DIRECTORIO_DATOS = DIRECTORIO_PROYECTO / "data"
RUTA_CSV_PREDETERMINADA = DIRECTORIO_DATOS / "procesos_demo.csv"
RUTA_LOGO_UTN = DIRECTORIO_DATOS / "logo_utn.txt"

DIRECTORIO_RESULTADOS = DIRECTORIO_PROYECTO / "resultados"

# Se define en main() segun la terminal y la opcion --sin-color.
ESTILO = Estilo()
# El panel siempre se arma con colores y bordes Unicode para poder exportarlo
# a HTML; al mostrarlo se adapta a lo que soporta la terminal.
ESTILO_COMPLETO = Estilo(color=True, unicode=True)
# Pantalla fija: se limpia la terminal en cada paso (como un tablero).
PANTALLA_FIJA = False
# Guardar TXT y HTML automaticamente al terminar (opcion --exportar).
EXPORTAR_AL_TERMINAR = False


OPCIONES_MENU = (
    (
        "1",
        "Iniciar simulacion con el CSV de prueba",
        "Ejecuta data/procesos_demo.csv: 6 procesos que muestran apropiacion "
        "SRTF, un proceso en LISTO_SUSPENDIDO y la reutilizacion de memoria.",
    ),
    (
        "2",
        "Elegir otro archivo CSV",
        "Lista los lotes de prueba de la carpeta data/ y permite escribir la "
        "ruta de un archivo propio (hasta 10 procesos, formato: "
        "id,tamanio,arribo,irrupcion).",
    ),
    (
        "3",
        "Ver guia rapida",
        "Explica el formato del CSV, las reglas del simulador (MVT, Best-Fit, "
        "SRTF, multiprogramacion 5), los estados y los controles.",
    ),
    (
        "4",
        "Cambiar modo de pantalla",
        "Alterna entre HISTORIAL (los pasos quedan uno debajo del otro) y "
        "PANTALLA FIJA (se limpia en cada paso, como un tablero). Tambien se "
        "cambia con la tecla F durante la simulacion.",
    ),
    ("0", "Salir", "Cierra el simulador."),
)


def _mostrar_menu() -> None:
    ancho = _ancho_terminal()

    try:
        logo = RUTA_LOGO_UTN.read_text(encoding="utf-8").splitlines()
    except OSError:
        logo = []
    if logo:
        margen_logo = min(
            len(linea) - len(linea.lstrip()) for linea in logo if linea.strip()
        )
        _imprimir_bloque_centrado(
            [ESTILO.c(linea[margen_logo:], "azul") for linea in logo]
        )

    e = ESTILO
    doble = e.c(e.linea(ancho, doble=True), "cian")
    simple = e.c(e.linea(ancho), "gris")
    print(doble)
    _imprimir_linea_centrada(e.c("K E R N E L F L O W", "negrita", "cian"))
    _imprimir_linea_centrada(
        "Simulador de planificacion SRTF y memoria MVT (Best-Fit)"
    )
    print(doble)
    _imprimir_linea_centrada(e.c("GRUPO 15", "negrita"))
    _imprimir_bloque_centrado([e.c(nombre, "gris") for nombre in (
        "BADER SORAIRE Cain Abel",
        "GONZALEZ Carlos Alfredo",
        "LEIVA ROMERO Agustin Nazareno",
        "SEELAFF Mauricio Guillermo",
        "TORRES Alejandro Valentin",
        "WOLKOWYSKI Braian Leonel",
        "ZURANO LANG Lucas Maximiliano",
    )])
    print(simple)
    lineas = []
    ancho_texto = max(30, min(ancho - 10, 72))
    for clave, titulo, descripcion in OPCIONES_MENU:
        lineas.append(e.c(f"[{clave}]", "amarillo", "negrita") + " " + e.c(titulo, "negrita"))
        lineas.extend(
            e.c(linea, "gris") for linea in textwrap.wrap(
                descripcion,
                width=ancho_texto,
                initial_indent="    ",
                subsequent_indent="    ",
            )
        )
        lineas.append("")
    _imprimir_bloque_centrado(lineas[:-1])
    print(simple)
    _imprimir_linea_centrada(
        e.c("Modo de pantalla actual: ", "gris")
        + e.c("PANTALLA FIJA" if PANTALLA_FIJA else "HISTORIAL", "cian", "negrita")
    )


def _mostrar_guia_rapida() -> None:
    """Explica la entrada, las reglas y la lectura de la simulacion."""
    guia = """
============================================================
  GUIA RAPIDA DE KERNELFLOW
============================================================
1. Preparar el archivo CSV
   Una fila representa un proceso. No escriba encabezados.
   Formato: id,tamanio,tiempo_arribo,tiempo_irrupcion
   Ejemplo: P1,120,0,8
   - id: nombre unico del proceso.
   - tamanio: memoria requerida en KB, entre 1 y 450.
   - tiempo_arribo: instante de llegada, desde 0.
   - tiempo_irrupcion: tiempo de irrupcion (rafaga), mayor que 0.
   Se admiten entre 1 y 10 procesos. Los numeros deben ser enteros.

2. Elegir como iniciar
   [1] Usa el CSV de prueba incluido en data/procesos_demo.csv.
   [2] Lista los CSV de la carpeta data/ para elegir uno por
       numero, o permite escribir la ruta de otro archivo.
   [3] Muestra esta guia.
   [0] Cierra el simulador.

3. Que hace el simulador
   - Reserva 100K para el sistema operativo y 450K para procesos.
   - MVT crea particiones variables. Best-Fit asigna el hueco libre
     mas pequeno donde entre cada proceso.
   - Pueden estar admitidos hasta 5 procesos al mismo tiempo
     (EJECUCION + LISTO + LISTO_SUSPENDIDO).
   - SRTF ejecuta el proceso LISTO con menor tiempo restante.
     Si llega otro mas corto, le quita la CPU (apropiacion).
   - Al terminar un proceso, libera su memoria y se vuelve a
     intentar el ingreso de los que esperan.

4. Como leer la pantalla
   Cada paso empieza con "COMIENZO DEL PASO" y termina con
   "FIN DEL PASO". Dentro de cada paso se listan todos los
   cambios de estado ocurridos (llegadas, admisiones,
   suspensiones, apropiaciones y finalizaciones) con su motivo.
   Luego se muestran en tablas: los procesos, la memoria
   principal (particiones), la CPU, la cola LISTO (en el orden
   en que SRTF los elegiria) y la cola LISTO_SUSPENDIDO, con el
   tiempo restante y la espera acumulada de cada proceso.
   Si los colores no se ven bien, use la opcion --sin-color.
   NUEVO espera su llegada o un cupo; LISTO espera la CPU;
   LISTO_SUSPENDIDO espera memoria; EJECUCION usa la CPU;
   TERMINADO ya completo su trabajo. La CPU puede estar OCIOSA.

5. Columnas de la tabla de procesos
   T.Irrup.: tiempo de irrupcion (CPU total que necesita).
   T.Ejec.: tiempo de CPU ya consumido.
   T.Rest.: tiempo de CPU que le falta (lo usa SRTF).
   Espera: tiempo en el sistema sin usar la CPU hasta ahora.
   NUEVO*: el proceso ya llego pero espera cupo (maximo 5).

6. Informe final
   Al terminar se muestran, por proceso, el tiempo de retorno
   (finalizacion - arribo), de espera (retorno - irrupcion) y de
   respuesta (primer uso de CPU - arribo), sus promedios y el
   rendimiento (trabajos terminados / tiempo total).

7. Controles durante la simulacion
   Espacio, Enter o N: ver el siguiente cambio relevante.
   B: volver al paso anterior para revisarlo (Espacio retoma).
   F: alternar entre historial y pantalla fija (tablero).
   Q: detener la simulacion y volver al menu.
   Al terminar (o al detenerla), G guarda la simulacion en la
   carpeta resultados/ como TXT y como HTML con colores.
   El reloj avanza internamente; no hace falta pulsar una tecla
   por cada unidad de tiempo.

8. Graficos
   Mapa de memoria: barra proporcional con el SO, cada particion
   (un color por proceso) y los huecos libres.
   [SRTF]: candidatos ordenados por tiempo restante y el elegido.
   Uso de la CPU: que proceso uso la CPU en cada instante.
   Al final: grafico de barras de retorno/espera y diagrama de
   Gantt con una fila por proceso.
============================================================"""
    _imprimir_bloque_centrado(guia.strip("\n").splitlines())


def _limpiar_pantalla() -> None:
    """Borra la pantalla (incluido el menu) al entrar en otra seccion."""
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")


def _leer_tecla() -> str:
    """Lee una sola tecla sin esperar Enter, en Linux y en Windows."""
    if os.name == "nt":
        import msvcrt

        return msvcrt.getwch()

    import termios
    import tty

    descriptor = sys.stdin.fileno()
    configuracion_anterior = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, configuracion_anterior)


def _esperar_avance() -> bool:
    """Espera una tecla; ``q`` permite volver al menu."""
    print(
        "\n" + _prefijo_centrado(
            "[Espacio/Enter] siguiente cambio  [q] volver al menu: "
        ),
        end="",
        flush=True,
    )
    return _esperar_tecla_avance()


def _esperar_tecla_avance() -> bool:
    """Retorna ``True`` para avanzar y ``False`` si se pidio volver al menu."""
    while True:
        tecla = _leer_tecla()
        if tecla in (" ", "\r", "\n", "n", "N"):
            print()
            return True
        if tecla in ("q", "Q", "", "\x1b"):
            print()
            return False


def _capturar(funcion: Callable, *argumentos) -> str:
    """Ejecuta una funcion que imprime y retorna lo que imprimio."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        funcion(*argumentos)
    return buffer.getvalue()


def _para_pantalla(texto: str) -> str:
    """Adapta una pantalla a lo que soporta la terminal actual."""
    if not ESTILO.color:
        texto = quitar_colores(texto)
    if not ESTILO.unicode:
        texto = a_ascii(texto)
    return texto


def _mostrar_pantalla(texto: str, aviso: str = "") -> None:
    if PANTALLA_FIJA:
        _limpiar_pantalla()
    if aviso:
        print(_para_pantalla(ESTILO_COMPLETO.c(
            f" {aviso} ".center(_ancho_terminal(), "◄"), "negro", "fondo_amarillo")))
    print(_para_pantalla(texto), end="")


def _aviso_revision(indice: int, total: int) -> str:
    if indice >= total - 1:
        return ""
    actual = "los procesos cargados" if indice == 0 else f"el paso {indice}"
    return (f"REVISANDO {actual.upper()} - la simulacion va por el paso "
            f"{total - 1} - [Espacio] para volver a avanzar")


def _navegar(pantallas: List[str], inicio: bool = False) -> bool:
    """Atiende las teclas entre pasos. ``True`` avanza; ``False`` sale.

    Espacio/Enter avanza, B vuelve al paso anterior (para revisar), F cambia
    entre historial y pantalla fija y Q vuelve al menu.
    """
    global PANTALLA_FIJA
    indice = len(pantallas) - 1
    while True:
        revisando = indice < len(pantallas) - 1
        if inicio and not revisando:
            avance = "comenzar la simulacion"
        else:
            avance = "paso siguiente" if revisando else "siguiente cambio"
        fija = "SI" if PANTALLA_FIJA else "NO"
        controles = (
            f"[Espacio/Enter] {avance}   [B] paso anterior   "
            f"[F] pantalla fija: {fija}   [Q] menu: "
        )
        print("\n" + _prefijo_centrado(_para_pantalla(
            ESTILO_COMPLETO.c(controles, "cian"))), end="", flush=True)
        tecla = _leer_tecla()
        print()
        if tecla in (" ", "\r", "\n", "n", "N"):
            if not revisando:
                return True
            indice += 1
        elif tecla in ("b", "B"):
            if indice > 0:
                indice -= 1
        elif tecla in ("f", "F"):
            PANTALLA_FIJA = not PANTALLA_FIJA
        elif tecla in ("q", "Q", "", "\x1b"):
            return False
        else:
            continue
        _mostrar_pantalla(pantallas[indice], _aviso_revision(indice, len(pantallas)))


def _exportar(pantallas: Sequence[str], ruta_csv: Path) -> None:
    try:
        ruta_txt, ruta_html = guardar_simulacion(
            pantallas, DIRECTORIO_RESULTADOS, ruta_csv.name
        )
    except OSError as error:
        _imprimir_linea_centrada(f"No se pudo guardar la simulacion: {error}")
        return
    _imprimir_linea_centrada("Simulacion guardada en:")
    _imprimir_bloque_centrado((f"  {ruta_txt}", f"  {ruta_html}"))


def _cierre(pantallas: Sequence[str], ruta_csv: Path, interactivo: bool) -> int:
    """Ofrece guardar la simulacion y espera para volver al menu."""
    if EXPORTAR_AL_TERMINAR:
        _exportar(pantallas, ruta_csv)
    if not interactivo:
        return 0
    guardada = EXPORTAR_AL_TERMINAR
    while True:
        if guardada:
            opciones = "[Enter] volver al menu"
        else:
            opciones = ("[G] guardar la simulacion (TXT y HTML con colores)   "
                        "[Enter] volver al menu")
        print("\n" + _prefijo_centrado(_para_pantalla(
            ESTILO_COMPLETO.c(opciones + ": ", "cian"))), end="", flush=True)
        tecla = _leer_tecla()
        print()
        if tecla in ("g", "G") and not guardada:
            _exportar(pantallas, ruta_csv)
            guardada = True
        elif tecla in (" ", "\r", "\n", "q", "Q", "", "\x1b"):
            return 0


def _contar_procesos(ruta: Path) -> str:
    """Cuenta las filas no vacias de un CSV para mostrarlas en la lista."""
    try:
        with ruta.open(encoding="utf-8-sig") as archivo:
            cantidad = sum(1 for linea in archivo if linea.strip())
    except (OSError, UnicodeDecodeError):
        return "no se puede leer"
    return f"{cantidad} proceso(s)"


def _elegir_csv() -> Optional[Path]:
    """Muestra los CSV de data/ y permite elegir uno o escribir otra ruta.

    No depende de un entorno grafico; el explorador de archivos queda como
    opcion adicional para quien tenga tkinter disponible.
    """
    archivos = sorted(
        ruta for ruta in DIRECTORIO_DATOS.glob("*.csv") if ruta.is_file()
    )
    while True:
        _limpiar_pantalla()
        ancho = _ancho_terminal()
        print("=" * ancho)
        _imprimir_linea_centrada("SELECCIONAR ARCHIVO CSV")
        print("=" * ancho)
        lineas = []
        if archivos:
            ancho_nombre = max(len(ruta.name) for ruta in archivos)
            for numero, ruta in enumerate(archivos, start=1):
                lineas.append(
                    f"[{numero}] {ruta.name:<{ancho_nombre}}  "
                    f"({_contar_procesos(ruta)})"
                )
        else:
            lineas.append(f"No hay archivos CSV en {DIRECTORIO_DATOS}.")
        lineas.extend((
            "",
            "[R] Escribir la ruta de otro archivo CSV",
            "[E] Buscarlo con el explorador de archivos (requiere entorno grafico)",
            "[0] Volver al menu",
        ))
        _imprimir_bloque_centrado(lineas)
        print("-" * ancho)

        opcion = input(_prefijo_centrado("Opcion: ")).strip().lower()
        if opcion == "0":
            return None
        if opcion.isdigit() and 1 <= int(opcion) <= len(archivos):
            return archivos[int(opcion) - 1]
        if opcion == "r":
            texto = input(_prefijo_centrado("Ruta del archivo CSV: "))
            ruta = Path(texto.strip().strip('"').strip("'")).expanduser()
            if ruta.is_file():
                return ruta
            _imprimir_linea_centrada(f"No se encontro el archivo '{ruta}'.")
        elif opcion == "e":
            ruta = seleccionar_archivo_csv(DIRECTORIO_DATOS)
            if ruta is not None:
                return ruta
            _imprimir_linea_centrada("No se selecciono ningun archivo.")
        else:
            _imprimir_linea_centrada("Opcion no valida.")
        input(_prefijo_centrado("Presione Enter para continuar..."))


def _menu_interactivo() -> int:
    """Permite elegir el archivo y volver al menu tras la simulacion."""
    global PANTALLA_FIJA
    while True:
        _limpiar_pantalla()
        _mostrar_menu()
        try:
            opcion = input(_prefijo_centrado("Opcion: ")).strip()
        except EOFError:
            return 0

        if opcion == "0":
            return 0
        if opcion == "1":
            ruta = RUTA_CSV_PREDETERMINADA
            _limpiar_pantalla()
        elif opcion == "2":
            ruta = _elegir_csv()
            if ruta is None:
                continue
            _limpiar_pantalla()
        elif opcion == "3":
            _limpiar_pantalla()
            _mostrar_guia_rapida()
            input("\n" + _prefijo_centrado("Presione Enter para volver al menu..."))
            continue
        elif opcion == "4":
            PANTALLA_FIJA = not PANTALLA_FIJA
            continue
        else:
            _imprimir_linea_centrada("Opcion no valida.")
            input(_prefijo_centrado("Presione Enter para continuar..."))
            continue

        if ejecutar_simulacion(ruta, modo_visual=True) != 0:
            input("\n" + _prefijo_centrado("Presione Enter para volver al menu..."))


def crear_argumentos(argumentos: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Interpreta los argumentos de la aplicacion de consola."""
    analizador = argparse.ArgumentParser(
        description="Simulador de procesos con SRTF y memoria MVT Best-Fit."
    )
    analizador.add_argument(
        "archivo",
        nargs="?",
        type=Path,
        default=None,
        help="CSV de procesos (por defecto: data/procesos_demo.csv).",
    )
    analizador.add_argument(
        "--sin-color",
        action="store_true",
        help="Muestra la salida sin colores (util si la terminal no los soporta).",
    )
    analizador.add_argument(
        "--pantalla-fija",
        action="store_true",
        help="Limpia la pantalla en cada paso, como un tablero (tecla F).",
    )
    analizador.add_argument(
        "--exportar",
        action="store_true",
        help="Guarda la simulacion en resultados/ (TXT y HTML) al terminar.",
    )
    return analizador.parse_args(argumentos)


def ejecutar_simulacion(ruta_csv: Path, modo_visual: bool = False) -> int:
    """Compone los modulos del simulador y ejecuta el ciclo principal."""
    try:
        procesos = cargar_procesos(ruta_csv)
    except ErrorCargaProcesos as error:
        _imprimir_linea_centrada(f"Error: {error}")
        return 1

    memoria = GestorMemoria()
    try:
        admision = Admision(procesos, memoria)
    except ErrorAdmision as error:
        _imprimir_linea_centrada(f"Error: {error}")
        return 1
    if not modo_visual:
        presentacion = PresentacionConsola(procesos, admision, memoria)
        presentacion.mostrar_inicio(ruta_csv)
        planificador = PlanificadorSRTF(admision, memoria, presentacion.mostrar_evento)
        planificador.simular()
        presentacion.mostrar_fin(planificador.reloj)
        return 0

    panel = PanelConsola(procesos, admision, memoria, ESTILO_COMPLETO)
    eventos_paso: List = []
    planificador = PlanificadorSRTF(admision, memoria, eventos_paso.append)
    panel.linea_tiempo = planificador.linea_tiempo
    interactivo = sys.stdin.isatty() and sys.stdout.isatty()

    # Cada pantalla se guarda para poder volver atras (B) y exportarla.
    pantallas = [_capturar(panel.mostrar_inicio, ruta_csv)]
    _mostrar_pantalla(pantallas[0])
    if interactivo and not _navegar(pantallas, inicio=True):
        return _cierre(pantallas, ruta_csv, interactivo)

    numero_paso = 0
    while True:
        # Los eventos de una finalizacion en t (producidos al ejecutar la
        # unidad t-1) se muestran junto con los arribos del mismo t.
        if admision.hay_procesos_pendientes():
            planificador.procesar_instante()
        if eventos_paso:
            numero_paso += 1
            pantallas.append(_capturar(
                panel.mostrar_paso, eventos_paso, planificador.reloj, numero_paso
            ))
            eventos_paso.clear()
            _mostrar_pantalla(pantallas[-1])
            if interactivo and not _navegar(pantallas):
                _imprimir_linea_centrada(
                    f"Simulacion detenida en t = {planificador.reloj}."
                )
                return _cierre(pantallas, ruta_csv, interactivo)
        if not admision.hay_procesos_pendientes():
            break
        planificador.ejecutar_unidad()

    pantallas.append(_capturar(panel.mostrar_fin, planificador.reloj))
    _mostrar_pantalla(pantallas[-1])
    return _cierre(pantallas, ruta_csv, interactivo)


def main(argumentos: Optional[Sequence[str]] = None) -> int:
    """Ejecuta KernelFlow y retorna un codigo apto para la consola de Linux."""
    global ESTILO, PANTALLA_FIJA, EXPORTAR_AL_TERMINAR
    opciones = crear_argumentos(argumentos)
    preparar_terminal()
    ESTILO = Estilo.detectar(sin_color=opciones.sin_color)
    PANTALLA_FIJA = opciones.pantalla_fija
    EXPORTAR_AL_TERMINAR = opciones.exportar
    try:
        if opciones.archivo is not None:
            return ejecutar_simulacion(opciones.archivo, modo_visual=True)
        if sys.stdin.isatty() and sys.stdout.isatty():
            return _menu_interactivo()
        return ejecutar_simulacion(RUTA_CSV_PREDETERMINADA, modo_visual=True)
    except (EOFError, KeyboardInterrupt):
        print()
        _imprimir_linea_centrada("Simulacion interrumpida.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
