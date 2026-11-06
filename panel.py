"""Panel de consola de la simulacion: tablas, mapa de memoria y Gantt.

Solo consulta el estado de procesos, admision, memoria y la linea de tiempo
del planificador; no decide transiciones ni selecciona la CPU.
"""

import math
import re
import shutil
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from admision import GRADO_MAXIMO_MULTIPROGRAMACION
from estadisticas import calcular_estadisticas
from estilo import (
    PALETA_PROCESOS,
    Celda,
    Estilo,
    acomodar_en_filas,
    largo_visible,
    rellenar,
)
from memoria import GestorMemoria
from planificador import (
    TIPO_APROPIACION,
    TIPO_ARRIBO,
    TIPO_CPU_OCIOSA,
    TIPO_FINALIZACION,
    TIPO_INICIO,
    TIPO_MEMORIA_LIBERADA,
    TIPO_NUEVA_ADMISION,
    TIPO_SIGUE_SUSPENDIDO,
    AdministradorAdmision,
    EventoPlanificador,
)
from presentacion import PresentacionConsola
from proceso import (
    ESTADO_EJECUCION,
    ESTADO_LISTO,
    ESTADO_LISTO_SUSPENDIDO,
    ESTADO_NUEVO,
    ESTADO_TERMINADO,
    Proceso,
)

COLOR_ESTADO = {
    ESTADO_NUEVO: ("gris",),
    ESTADO_LISTO: ("cian",),
    ESTADO_LISTO_SUSPENDIDO: ("amarillo",),
    ESTADO_EJECUCION: ("verde", "negrita"),
    ESTADO_TERMINADO: ("azul",),
}
NOMBRE_ESTADO = {ESTADO_LISTO_SUSPENDIDO: "LISTO/SUSP."}

# (etiqueta, colores) de cada tipo de evento.
ETIQUETA_EVENTO = {
    TIPO_ARRIBO: ("LLEGADA", ("cian",)),
    TIPO_NUEVA_ADMISION: ("ADMISION", ("verde",)),
    TIPO_SIGUE_SUSPENDIDO: ("SIN MEMORIA", ("amarillo",)),
    TIPO_APROPIACION: ("APROPIACION", ("magenta", "negrita")),
    TIPO_INICIO: ("CPU", ("verde", "negrita")),
    TIPO_FINALIZACION: ("FIN", ("azul", "negrita")),
    TIPO_MEMORIA_LIBERADA: ("MEMORIA", ("azul",)),
    TIPO_CPU_OCIOSA: ("CPU OCIOSA", ("gris",)),
}
ETIQUETA_SUSPENSION = ("SUSPENSION", ("amarillo", "negrita"))
ANCHO_ETIQUETA = max(len(e) for e, _ in ETIQUETA_EVENTO.values()) + 2
CELDAS_PROGRESO = 8


def ancho_terminal() -> int:
    return shutil.get_terminal_size(fallback=(120, 30)).columns


def centrar_linea(texto: str) -> str:
    return " " * max(0, (ancho_terminal() - largo_visible(texto)) // 2) + texto


def imprimir_centrado(texto: str) -> None:
    print(centrar_linea(texto))


def imprimir_bloque(lineas: Sequence[str]) -> None:
    """Centra un bloque respetando la alineacion interna de sus lineas."""
    if not lineas:
        return
    ancho_bloque = max(largo_visible(linea) for linea in lineas)
    margen = " " * max(0, (ancho_terminal() - ancho_bloque) // 2)
    for linea in lineas:
        print(margen + linea if linea else "")


class PanelConsola(PresentacionConsola):
    """Vista de la simulacion para la terminal, con tablas y graficos."""

    def __init__(
        self,
        procesos: Sequence[Proceso],
        admision: AdministradorAdmision,
        memoria: GestorMemoria,
        estilo: Optional[Estilo] = None,
    ) -> None:
        super().__init__(procesos, admision, memoria)
        self.estilo = estilo if estilo is not None else Estilo.detectar()
        # El planificador comparte su lista; se completa a medida que avanza.
        self.linea_tiempo: List[Optional[str]] = []
        self._color_proceso: Dict[str, str] = {
            proceso.id: PALETA_PROCESOS[indice % len(PALETA_PROCESOS)]
            for indice, proceso in enumerate(procesos)
        }
        self._estados_previos: Dict[str, str] = {
            proceso.id: proceso.estado for proceso in procesos
        }
        ids = sorted((re.escape(p.id) for p in procesos), key=len, reverse=True)
        self._patron_ids = (
            re.compile(r"(?<![\w])(" + "|".join(ids) + r")(?![\w])") if ids else None
        )

    # ------------------------------------------------------------------
    # Pantallas
    # ------------------------------------------------------------------

    def mostrar_inicio(self, ruta_csv: Path) -> None:
        e = self.estilo
        self._encabezado("PROCESOS CARGADOS", f"Archivo: {ruta_csv.name}")
        imprimir_centrado(
            f"{len(self.procesos)} proceso(s) leido(s) correctamente. Todos "
            "comienzan en " + e.c("NUEVO", "gris") + " y esperan su arribo."
        )
        print()
        imprimir_bloque(self._tabla_procesos(tiempo=None, cambiados=set(),
                                             titulo="Procesos del lote"))
        print()
        imprimir_bloque(self._mapa_memoria())
        print()
        imprimir_bloque((
            e.c("Memoria:", "negrita") + " 100K para el SO + 450K para usuario"
            " (particiones variables MVT, Best-Fit)",
            e.c("CPU:", "negrita") + " SRTF apropiativo   "
            + e.c("Multiprogramacion maxima:", "negrita") + " 5",
        ))

    def mostrar_paso(
        self, eventos: Sequence[EventoPlanificador], tiempo: int, numero: int
    ) -> None:
        e = self.estilo
        cambiados = {
            proceso.id for proceso in self.procesos
            if proceso.estado != self._estados_previos.get(proceso.id)
        }
        print()
        self._encabezado(f"PASO {numero}", f"Reloj: t = {tiempo} ut")
        imprimir_centrado(e.c("EVENTOS DE ESTE PASO", "negrita"))
        imprimir_bloque(self._lineas_eventos(eventos) + [""] + self._decision_srtf())
        print()
        imprimir_bloque(self._mapa_memoria())
        print()
        imprimir_bloque(acomodar_en_filas(
            [self._tabla_procesos(tiempo, cambiados), self._tabla_particiones()],
            ancho_terminal() - 2,
        ))
        print()
        imprimir_bloque(acomodar_en_filas(
            [
                self._tabla_cpu(tiempo),
                self._tabla_listos(tiempo),
                self._tabla_suspendidos(tiempo),
            ],
            ancho_terminal() - 2,
        ))
        print()
        imprimir_bloque(self._linea_cpu(tiempo))
        print()
        imprimir_centrado(self._barra_estado(tiempo))
        print(e.c(f" FIN DEL PASO {numero} ".center(ancho_terminal(), "─"
                                                     if e.unicode else "-"),
                  "gris"))
        self._estados_previos = {p.id: p.estado for p in self.procesos}

    def mostrar_fin(self, tiempo: int) -> None:
        e = self.estilo
        print()
        self._encabezado(
            "SIMULACION FINALIZADA",
            f"t = {tiempo} ut   Memoria de usuario libre: "
            f"{self.memoria.memoria_libre_total()}K",
        )
        informe = calcular_estadisticas(self.procesos, tiempo)
        filas = [
            (
                self._id(fila.id),
                fila.tiempo_arribo,
                fila.tiempo_irrupcion,
                fila.tiempo_inicio,
                fila.tiempo_finalizacion,
                Celda(fila.tiempo_retorno, ("verde",)),
                Celda(fila.tiempo_espera, ("amarillo",)),
                Celda(fila.tiempo_respuesta, ("cian",)),
            )
            for fila in informe.procesos
        ]
        filas.append((
            Celda("PROMEDIO", ("negrita",)), "", "", "", "",
            Celda(f"{informe.retorno_promedio:.2f}", ("verde", "negrita"), ">"),
            Celda(f"{informe.espera_promedio:.2f}", ("amarillo", "negrita"), ">"),
            Celda(f"{informe.respuesta_promedio:.2f}", ("cian", "negrita"), ">"),
        ))
        imprimir_bloque(e.tabla(
            ("ID", "T.Arribo", "T.Irrup.", "T.Inicio", "T.Final.",
             "T.Retorno", "T.Espera", "T.Resp."),
            filas,
            titulo="Informe estadistico por proceso",
        ))
        print()
        imprimir_bloque(e.tabla(
            ("Metrica", "Valor", "Formula"),
            [
                ("Tiempo de retorno promedio",
                 Celda(f"{informe.retorno_promedio:.2f} ut", ("verde", "negrita")),
                 "T. Finalizacion - T. Arribo"),
                ("Tiempo de espera promedio",
                 Celda(f"{informe.espera_promedio:.2f} ut", ("amarillo", "negrita")),
                 "T. Retorno - T. Irrupcion"),
                ("Tiempo de respuesta promedio",
                 Celda(f"{informe.respuesta_promedio:.2f} ut", ("cian", "negrita")),
                 "Primer uso de CPU - T. Arribo"),
                ("Rendimiento del sistema",
                 Celda(f"{informe.rendimiento:.4f} trab./ut", ("magenta", "negrita")),
                 f"{informe.trabajos_terminados} trabajos / "
                 f"{informe.tiempo_total} ut"),
            ],
            titulo="Resumen",
        ))
        print()
        imprimir_bloque(self._grafico_barras(informe))
        print()
        imprimir_bloque(self._gantt(tiempo))

    # ------------------------------------------------------------------
    # Bloques de cada paso
    # ------------------------------------------------------------------

    def _encabezado(self, titulo: str, subtitulo: str = "") -> None:
        e = self.estilo
        ancho = ancho_terminal()
        print(e.c(e.linea(ancho, doble=True), "cian"))
        imprimir_centrado(e.c(titulo, "negrita", "blanco"))
        if subtitulo:
            imprimir_centrado(e.c(subtitulo, "cian"))
        print(e.c(e.linea(ancho, doble=True), "cian"))

    def _lineas_eventos(self, eventos: Sequence[EventoPlanificador]) -> List[str]:
        e = self.estilo
        ancho = max(40, min(ancho_terminal() - 6, 118))
        lineas: List[str] = []
        for evento in eventos:
            etiqueta, colores = ETIQUETA_EVENTO.get(evento.tipo, ("EVENTO", ()))
            if "a LISTO_SUSPENDIDO" in evento.detalle and evento.tipo in (
                TIPO_ARRIBO, TIPO_NUEVA_ADMISION
            ):
                etiqueta, colores = ETIQUETA_SUSPENSION
            ancho_prefijo = 6 + ANCHO_ETIQUETA + 1
            envueltas = textwrap.wrap(evento.detalle, width=ancho - ancho_prefijo) or [""]
            for indice, texto in enumerate(envueltas):
                texto = self._resaltar_ids(texto)
                if indice == 0:
                    lineas.append(
                        e.c(f"t={evento.tiempo:<3} ", "gris")
                        + e.c(f"[{etiqueta}]".ljust(ANCHO_ETIQUETA), *colores)
                        + " " + texto
                    )
                else:
                    lineas.append(" " * ancho_prefijo + texto)
        return lineas

    def _decision_srtf(self) -> List[str]:
        """Explica por que el proceso en CPU es el elegido por SRTF."""
        e = self.estilo
        etiqueta = e.c("[SRTF]".ljust(ANCHO_ETIQUETA), "magenta", "negrita")
        prefijo = " " * 6 + etiqueta + " "
        en_cpu = self.proceso_en_cpu()
        candidatos = list(self.admision.obtener_listos())
        if en_cpu is not None:
            candidatos.append(en_cpu)
        if not candidatos:
            return [prefijo + "No hay procesos en LISTO: la CPU queda "
                    + e.c("OCIOSA", "gris") + "."]

        def clave(proceso: Proceso):
            # El proceso en CPU va primero entre los empatados (conserva la CPU).
            return (proceso.tiempo_restante, proceso is not en_cpu,
                    proceso.tiempo_arribo, proceso.id)

        ordenados = sorted(candidatos, key=clave)
        partes = []
        for indice, proceso in enumerate(ordenados):
            if indice > 0:
                igual = proceso.tiempo_restante == ordenados[indice - 1].tiempo_restante
                partes.append(" = " if igual else " < ")
            texto = f"{proceso.id}({proceso.tiempo_restante})"
            partes.append(e.c(texto, "verde", "negrita") if proceso is en_cpu
                          else self._resaltar_ids(texto))
        explicacion = "Menor tiempo restante: " + "".join(partes)
        empatados = []
        if en_cpu is not None:
            explicacion += e.c(" → ", "gris") + "usa la CPU " + e.c(en_cpu.id, "verde", "negrita")
            empatados = [p for p in ordenados
                         if p is not en_cpu and p.tiempo_restante == en_cpu.tiempo_restante]
        lineas = [prefijo + explicacion]
        if en_cpu is not None and empatados:
            lineas.append(" " * (6 + ANCHO_ETIQUETA + 1) + e.c(
                "Empate de tiempo restante: el proceso que ya esta en CPU la conserva.",
                "gris"))
        return lineas

    def _mapa_memoria(self) -> List[str]:
        """Barra proporcional de la memoria: SO, particiones y huecos libres."""
        e = self.estilo
        resumen = self.memoria.obtener_resumen_memoria()
        particiones = [resumen["particion_so"], *resumen["particiones_usuario"]]
        total = self.memoria.memoria_total_kb
        ancho = max(40, min(ancho_terminal() - 12, 110)) - len(particiones) - 1
        anchos = _repartir(
            [particion.tamanio for particion in particiones], total, ancho, minimo=3
        )
        separador = e.c("│", "gris")
        segmentos = []
        for particion, columnas in zip(particiones, anchos):
            if particion.libre:
                etiqueta = _etiqueta_que_entra(
                    (f"libre {particion.tamanio}K", "libre", ""), columnas)
                sobra = columnas - len(etiqueta)
                izquierda = sobra // 2
                texto = "░" * izquierda + etiqueta + "░" * (sobra - izquierda)
                segmentos.append(e.c(texto, "verde"))
            elif particion.proceso_id == "SO":
                etiqueta = _etiqueta_que_entra((f"SO {particion.tamanio}K", "SO"), columnas)
                segmentos.append(e.c(rellenar(etiqueta, columnas, "^"),
                                     "negro", "fondo_magenta"))
            else:
                pid = particion.proceso_id
                etiqueta = _etiqueta_que_entra(
                    (f"{pid} {particion.tamanio}K", pid, pid[:columnas]), columnas)
                color = self._color_proceso.get(pid, "blanco")
                segmentos.append(e.c(rellenar(etiqueta, columnas, "^"),
                                     "negro", f"fondo_{color}"))
        barra = separador + separador.join(segmentos) + separador

        # Escala de direcciones: el inicio de cada particion y el final.
        escala = [" "] * (sum(anchos) + len(anchos) + 1)
        columna = 0
        ocupado_hasta = -1
        for particion, columnas in zip(particiones, anchos):
            texto = str(particion.direccion_inicio)
            if columna > ocupado_hasta:
                escala[columna:columna + len(texto)] = texto
                ocupado_hasta = columna + len(texto)
            columna += columnas + 1
        final = str(total)
        inicio_final = len(escala) - len(final)
        if inicio_final > ocupado_hasta:
            escala[inicio_final:] = final

        huecos = self.memoria.obtener_huecos()
        lineas = [
            e.c("Mapa de memoria", "negrita", "cian")
            + e.c(f"  (aprox. a escala, {total}K; direcciones en K)", "gris"),
            barra,
            e.c("".join(escala)[:len(escala)], "gris"),
        ]
        if len(huecos) > 1:
            lineas.append(e.c(
                f"Fragmentacion externa: {self.memoria.memoria_libre_total()}K "
                f"libres repartidos en {len(huecos)} huecos (el mayor: "
                f"{self.memoria.mayor_hueco_libre()}K)", "amarillo"))
        return lineas

    def _tabla_procesos(
        self, tiempo: Optional[int], cambiados=frozenset(), titulo: str = "Procesos"
    ) -> List[str]:
        e = self.estilo
        filas = []
        hay_sin_cupo = False
        for proceso in self.procesos:
            estado = NOMBRE_ESTADO.get(proceso.estado, proceso.estado)
            if (
                tiempo is not None
                and proceso.estado == ESTADO_NUEVO
                and proceso.tiempo_arribo <= tiempo
            ):
                estado += "*"
                hay_sin_cupo = True
            cambio = proceso.id in cambiados
            estilos_estado = COLOR_ESTADO.get(proceso.estado, ())
            if cambio:
                estilos_estado = estilos_estado + ("negrita",)
            filas.append((
                Celda("►" if cambio else " ", ("magenta", "negrita")),
                self._id(proceso.id),
                proceso.tamanio,
                proceso.tiempo_arribo,
                proceso.tiempo_irrupcion,
                Celda(self._progreso(proceso), ()),
                Celda(proceso.tiempo_restante,
                      ("negrita",) if proceso.estado == ESTADO_EJECUCION else (), ">"),
                Celda(estado, estilos_estado),
            ))
        lineas = e.tabla(
            (" ", "ID", "KB", "Arribo", "T.Irrup.", "Progreso (ejecutado)",
             "T.Rest.", "Estado"),
            filas,
            titulo=titulo,
        )
        if cambiados:
            lineas.append(e.c("► cambio de estado en este paso", "magenta"))
        if hay_sin_cupo:
            lineas.append(e.c("* llego y espera cupo de multiprogramacion", "gris"))
        return lineas

    def _progreso(self, proceso: Proceso) -> str:
        """Barra de progreso de CPU, por ejemplo ``████░░░░ 4/8``."""
        e = self.estilo
        ejecutado = proceso.tiempo_irrupcion - proceso.tiempo_restante
        llenas = round(CELDAS_PROGRESO * ejecutado / proceso.tiempo_irrupcion)
        if ejecutado and not llenas:
            llenas = 1
        color = "azul" if proceso.estado == ESTADO_TERMINADO else (
            "verde" if proceso.estado == ESTADO_EJECUCION else "cian")
        barra = e.c("█" * llenas, color) + e.c("░" * (CELDAS_PROGRESO - llenas), "gris")
        ancho = len(str(proceso.tiempo_irrupcion))
        return f"{barra} {ejecutado:>{ancho}}/{proceso.tiempo_irrupcion}"

    def _tabla_particiones(self) -> List[str]:
        resumen = self.memoria.obtener_resumen_memoria()
        filas = []
        for particion in [resumen["particion_so"], *resumen["particiones_usuario"]]:
            if particion.libre:
                proceso, estado, frag = Celda("-", ("gris",)), Celda("Libre", ("verde",)), "-"
            elif particion.proceso_id == "SO":
                proceso, estado, frag = (
                    Celda("SO", ("magenta",)), Celda("Sistema", ("magenta",)), "-"
                )
            else:
                proceso = self._id(particion.proceso_id)
                estado, frag = Celda("Ocupada", ("rojo",)), "0"
            filas.append((
                Celda("-", ("gris",), ">") if particion.numero is None
                else particion.numero,
                particion.direccion_inicio,
                particion.tamanio,
                proceso,
                frag,
                estado,
            ))
        lineas = self.estilo.tabla(
            ("Part.", "Inicio", "Tamanio", "Proceso", "Frag.Int.", "Estado"),
            filas,
            titulo="Memoria principal (KB)",
        )
        huecos = self.memoria.obtener_huecos()
        lineas.append(self.estilo.c(
            f"Libre: {self.memoria.memoria_libre_total()}K en {len(huecos)} "
            f"hueco(s); mayor hueco: {self.memoria.mayor_hueco_libre()}K",
            "gris",
        ))
        return lineas

    def _tabla_cpu(self, tiempo: int) -> List[str]:
        en_cpu = self.proceso_en_cpu()
        filas = [] if en_cpu is None else [(
            self._id(en_cpu.id),
            en_cpu.tamanio,
            self._numero_particion(en_cpu),
            en_cpu.tiempo_irrupcion - en_cpu.tiempo_restante,
            Celda(en_cpu.tiempo_restante, ("verde", "negrita")),
        )]
        return self.estilo.tabla(
            ("ID", "KB", "Part.", "T.Ejec.", "T.Rest."),
            filas,
            titulo="CPU - EJECUCION",
            color_titulo=("negrita", "verde"),
            vacia="CPU OCIOSA",
        )

    def _tabla_listos(self, tiempo: int) -> List[str]:
        filas = [
            (
                orden,
                self._id(proceso.id),
                proceso.tamanio,
                self._numero_particion(proceso),
                proceso.tiempo_arribo,
                Celda(proceso.tiempo_restante, ("cian",)),
                self._espera_acumulada(proceso, tiempo),
            )
            for orden, proceso in enumerate(self._ordenar_srtf(
                self.admision.obtener_listos()), start=1)
        ]
        return self.estilo.tabla(
            ("Orden", "ID", "KB", "Part.", "Arribo", "T.Rest.", "Espera"),
            filas,
            titulo="Cola LISTO (en memoria)",
            color_titulo=("negrita", "cian"),
            vacia="sin procesos",
        )

    def _tabla_suspendidos(self, tiempo: int) -> List[str]:
        filas = [
            (
                orden,
                self._id(proceso.id),
                proceso.tamanio,
                proceso.tiempo_arribo,
                Celda(proceso.tiempo_restante, ("amarillo",)),
                self._espera_acumulada(proceso, tiempo),
            )
            for orden, proceso in enumerate(
                self.admision.obtener_listos_suspendidos(), start=1)
        ]
        return self.estilo.tabla(
            ("Orden", "ID", "KB", "Arribo", "T.Rest.", "Espera"),
            filas,
            titulo="Cola LISTO_SUSPENDIDO (sin memoria)",
            color_titulo=("negrita", "amarillo"),
            vacia="sin procesos",
        )

    def _linea_cpu(self, tiempo: int) -> List[str]:
        """Gantt compacto de la CPU desde t = 0 hasta el instante actual."""
        e = self.estilo
        if not self.linea_tiempo:
            return []
        unidades, columnas = _escala_gantt(len(self.linea_tiempo), ancho_terminal() - 20)
        barra, escala = self._barra_gantt(self.linea_tiempo, unidades, columnas)
        return [
            e.c("Uso de la CPU hasta ahora", "negrita", "cian")
            + e.c("  (· = CPU ociosa)", "gris"),
            barra,
            e.c(escala, "gris"),
        ]

    def _barra_estado(self, tiempo: int) -> str:
        e = self.estilo
        en_cpu = self.proceso_en_cpu()
        terminados = sum(p.estado == ESTADO_TERMINADO for p in self.procesos)
        sep = e.c(" | ", "gris")
        partes = [
            e.c("t = ", "gris") + e.c(f"{tiempo} ut", "negrita"),
            e.c("CPU: ", "gris") + (
                e.c(en_cpu.id, "verde", "negrita") if en_cpu else e.c("OCIOSA", "gris")
            ),
            e.c("Multiprogramacion: ", "gris") + e.c(
                f"{self.admision.grado_multiprogramacion()}/"
                f"{GRADO_MAXIMO_MULTIPROGRAMACION}", "negrita"),
            e.c("Memoria libre: ", "gris") + e.c(
                f"{self.memoria.memoria_libre_total()}K/"
                f"{self.memoria.memoria_usuario_kb}K", "negrita"),
            e.c("Terminados: ", "gris") + e.c(
                f"{terminados}/{len(self.procesos)}", "negrita"),
        ]
        return sep.join(partes)

    # ------------------------------------------------------------------
    # Graficos del informe final
    # ------------------------------------------------------------------

    def _grafico_barras(self, informe) -> List[str]:
        """Barras horizontales de retorno y espera por proceso."""
        e = self.estilo
        if not informe.procesos:
            return []
        maximo = max(fila.tiempo_retorno for fila in informe.procesos) or 1
        largo = 40
        ancho_id = max(len(fila.id) for fila in informe.procesos)
        lineas = [e.c("Retorno y espera por proceso", "negrita", "cian")
                  + e.c("  (" + e.c("█", "verde") + e.c(" retorno  ", "gris")
                        + e.c("█", "amarillo") + e.c(" espera)", "gris"), "gris")]
        for fila in informe.procesos:
            for nombre, valor, color in (
                ("retorno", fila.tiempo_retorno, "verde"),
                ("espera", fila.tiempo_espera, "amarillo"),
            ):
                celdas = round(largo * valor / maximo)
                if valor and not celdas:
                    celdas = 1
                etiqueta = fila.id if nombre == "retorno" else ""
                lineas.append(
                    self._resaltar_ids(etiqueta.ljust(ancho_id)) + " "
                    + e.c(nombre.ljust(7), "gris") + " "
                    + e.c("█" * celdas, color) + " " + str(valor)
                )
        return lineas

    def _gantt(self, tiempo: int) -> List[str]:
        """Diagrama de Gantt: una fila por proceso y la fila de la CPU."""
        e = self.estilo
        linea = self.linea_tiempo[:tiempo]
        if not linea:
            return []
        ancho_id = max(4, max(len(p.id) for p in self.procesos))
        unidades, ancho_columna = _escala_gantt(len(linea), ancho_terminal() - ancho_id - 12)
        columnas = math.ceil(len(linea) / unidades)
        detalle_escala = (f"cada {ancho_columna} columnas = 1 ut" if unidades == 1
                          else f"cada columna = {unidades} ut")

        lineas = [
            e.c("Diagrama de Gantt", "negrita", "cian")
            + e.c(f"  ({detalle_escala};  █ usa la CPU  ░ espera en el sistema)", "gris"),
        ]
        for proceso in self.procesos:
            fin = proceso.tiempo_finalizacion if proceso.tiempo_finalizacion is not None else tiempo
            celdas = []
            for columna in range(columnas):
                desde = columna * unidades
                tramo = linea[desde:desde + unidades]
                if proceso.id in tramo:
                    celdas.append(e.c("█" * ancho_columna,
                                      self._color_proceso.get(proceso.id, "blanco")))
                elif proceso.tiempo_arribo <= desde < fin:
                    celdas.append(e.c("░" * ancho_columna, "gris"))
                else:
                    celdas.append(" " * ancho_columna)
            lineas.append(self._resaltar_ids(proceso.id.ljust(ancho_id)) + " "
                          + e.c("│", "gris") + "".join(celdas) + e.c("│", "gris"))
        barra, escala = self._barra_gantt(linea, unidades, ancho_columna)
        lineas.append(e.c("CPU".ljust(ancho_id), "negrita") + " " + barra)
        lineas.append(" " * (ancho_id + 1) + e.c(escala, "gris"))
        return lineas

    def _barra_gantt(
        self, linea: Sequence[Optional[str]], unidades: int, ancho_columna: int
    ):
        """Barra de CPU con un tramo coloreado por cada rafaga y su escala.

        Cada columna logica abarca ``unidades`` ut y ocupa ``ancho_columna``
        caracteres.
        """
        e = self.estilo
        columnas = [linea[i] for i in range(0, len(linea), unidades)]
        tramos = []
        for pid in columnas:
            if tramos and tramos[-1][0] == pid:
                tramos[-1][1] += 1
            else:
                tramos.append([pid, 1])
        partes = []
        for pid, cantidad in tramos:
            largo = cantidad * ancho_columna
            if pid is None:
                partes.append(e.c("·" * largo, "gris"))
            else:
                etiqueta = pid if len(pid) <= largo else pid[:largo]
                color = self._color_proceso.get(pid, "blanco")
                partes.append(e.c(rellenar(etiqueta, largo, "^"),
                                  "negro", f"fondo_{color}"))
        barra = e.c("│", "gris") + "".join(partes) + e.c("│", "gris")

        escala = [" "] * (len(columnas) * ancho_columna + 6)
        paso = 5 if ancho_columna > 1 or len(columnas) <= 60 else 10
        for columna in range(0, len(columnas) + 1, paso):
            texto = str(columna * unidades)
            posicion = columna * ancho_columna
            if posicion + len(texto) <= len(escala):
                escala[posicion:posicion + len(texto)] = texto
        return barra, " " + "".join(escala).rstrip()

    # ------------------------------------------------------------------
    # Auxiliares
    # ------------------------------------------------------------------

    def _id(self, proceso_id: str) -> Celda:
        return Celda(proceso_id, ("amarillo",))

    def _resaltar_ids(self, texto: str) -> str:
        if not self.estilo.color or self._patron_ids is None:
            return texto
        return self._patron_ids.sub(
            lambda m: self.estilo.c(m.group(1), "amarillo"), texto
        )

    def _numero_particion(self, proceso: Proceso) -> object:
        particion = self.memoria.obtener_asignacion(proceso)
        if particion is None or particion.numero is None:
            return "-"
        return particion.numero

    @staticmethod
    def _espera_acumulada(proceso: Proceso, tiempo: int) -> int:
        """Tiempo en el sistema sin usar la CPU hasta el instante actual."""
        ejecutado = proceso.tiempo_irrupcion - proceso.tiempo_restante
        return max(0, tiempo - proceso.tiempo_arribo - ejecutado)

    @staticmethod
    def _ordenar_srtf(procesos: Sequence[Proceso]) -> List[Proceso]:
        """Orden en que SRTF los elegiria: menor restante, arribo e ID."""
        return sorted(
            procesos,
            key=lambda p: (p.tiempo_restante, p.tiempo_arribo, p.id),
        )


def _escala_gantt(unidades_totales: int, ancho_disponible: int):
    """Elige cuantas ut entran por columna y cuantos caracteres ocupa cada una.

    Si hay lugar, cada ut ocupa hasta 3 caracteres para que entren los IDs;
    si no, se agrupan varias ut por columna.
    """
    ancho_disponible = max(20, ancho_disponible)
    if unidades_totales <= ancho_disponible:
        return 1, max(1, min(3, ancho_disponible // max(1, unidades_totales)))
    return math.ceil(unidades_totales / ancho_disponible), 1


def _etiqueta_que_entra(opciones: Sequence[str], columnas: int) -> str:
    """Devuelve la primera etiqueta que entra en ``columnas`` con margen."""
    for opcion in opciones:
        if len(opcion) + 2 <= columnas or (len(opcion) <= columnas and opcion):
            return opcion
    return ""


def _repartir(tamanios: Sequence[int], total: int, ancho: int, minimo: int) -> List[int]:
    """Reparte ``ancho`` columnas en proporcion a los tamanios (con minimo)."""
    exactos = [tamanio * ancho / total for tamanio in tamanios]
    anchos = [max(minimo, int(valor)) for valor in exactos]
    diferencia = ancho - sum(anchos)
    if diferencia > 0:
        orden = sorted(range(len(anchos)),
                       key=lambda i: exactos[i] - int(exactos[i]), reverse=True)
    else:
        orden = sorted(range(len(anchos)), key=lambda i: anchos[i], reverse=True)
    intentos = 0
    while diferencia != 0 and orden and intentos < 10 * ancho:
        indice = orden[intentos % len(orden)]
        if diferencia > 0:
            anchos[indice] += 1
            diferencia -= 1
        elif anchos[indice] > minimo:
            anchos[indice] -= 1
            diferencia += 1
        intentos += 1
    return anchos
