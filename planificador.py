"""Planificacion apropiativa SRTF y reloj discreto de la simulacion."""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Protocol, Sequence

from memoria import GestorMemoria
from proceso import ESTADO_NUEVO, Proceso


TIPO_INICIO = "INICIO_EJECUCION"
TIPO_ARRIBO = "ARRIBO"
TIPO_APROPIACION = "APROPIACION"
TIPO_FINALIZACION = "FINALIZACION"
TIPO_CPU_OCIOSA = "CPU_OCIOSA"
TIPO_MEMORIA_LIBERADA = "MEMORIA_LIBERADA"
TIPO_NUEVA_ADMISION = "NUEVA_ADMISION"
TIPO_SIGUE_SUSPENDIDO = "SIGUE_SUSPENDIDO"


class TransicionAdmision(Protocol):
    """Datos minimos de una transicion registrada por admision."""

    proceso: Proceso
    origen: str
    destino: str
    motivo: str


@dataclass(frozen=True)
class EventoPlanificador:
    """Describe un cambio relevante producido por el planificador."""

    tiempo: int
    tipo: str
    proceso_id: Optional[str] = None
    detalle: str = ""


class AdministradorAdmision(Protocol):
    """Contrato que HU-03 debe ofrecer al planificador.

    La admision conserva la propiedad de las colas y de las transiciones de
    estado. El planificador solo solicita los cambios que corresponden a SRTF.
    """

    def procesar_arribos(self, tiempo: int) -> Sequence[Proceso]:
        """Procesa los procesos cuyo tiempo de arribo coincide con ``tiempo``."""

    def obtener_listos(self) -> Sequence[Proceso]:
        """Retorna una vista de los procesos que pueden usar la CPU."""

    def obtener_listos_suspendidos(self) -> Sequence[Proceso]:
        """Retorna la cola de procesos que esperan memoria."""

    def enviar_a_ejecucion(self, proceso: Proceso) -> None:
        """Pasa un proceso LISTO a EJECUCION."""

    def devolver_a_listo(self, proceso: Proceso) -> None:
        """Devuelve a LISTO un proceso apropiado."""

    def finalizar(self, proceso: Proceso) -> None:
        """Pasa un proceso en EJECUCION a TERMINADO."""

    def reintentar_suspendidos(self) -> Sequence[Proceso]:
        """Reintenta admitir procesos luego de liberar memoria."""

    def hay_procesos_pendientes(self) -> bool:
        """Indica si quedan procesos sin terminar."""

    def extraer_transiciones(self) -> Sequence[TransicionAdmision]:
        """Retorna y vacia los cambios de estado producidos por admision."""

    def grado_multiprogramacion(self) -> int:
        """Cuenta los procesos en EJECUCION, LISTO y LISTO_SUSPENDIDO."""


ObservadorEventos = Callable[[EventoPlanificador], None]


class PlanificadorSRTF:
    """Coordina la CPU con Shortest Remaining Time First apropiativo.

    Convencion temporal: los arribos del instante ``t`` se procesan antes de
    elegir la CPU. Una unidad ejecutada en ``t`` termina en ``t + 1``.

    Desempate: el proceso que ya ocupa la CPU continua si empata en tiempo
    restante con el mejor proceso LISTO. Cuando la CPU esta libre, se elige por
    menor tiempo restante, luego menor tiempo de arribo y finalmente menor ID.
    """

    def __init__(
        self,
        admision: AdministradorAdmision,
        memoria: GestorMemoria,
        observador: Optional[ObservadorEventos] = None,
    ) -> None:
        self.admision = admision
        self.memoria = memoria
        self.observador = observador
        self.reloj = 0
        self.proceso_en_ejecucion: Optional[Proceso] = None
        self.cambios_contexto = 0
        self._cpu_ociosa_informada = False
        # linea_tiempo[t] es el ID del proceso que uso la CPU en [t, t+1),
        # o None si estuvo ociosa. Se usa para el diagrama de Gantt.
        self.linea_tiempo: List[Optional[str]] = []

    @staticmethod
    def seleccionar_srtf(procesos: Sequence[Proceso]) -> Optional[Proceso]:
        """Selecciona en forma determinista el proceso con menor tiempo restante."""
        if not procesos:
            return None

        for proceso in procesos:
            if proceso.tiempo_restante is None or proceso.tiempo_restante <= 0:
                raise ValueError(
                    f"El proceso '{proceso.id}' no tiene tiempo restante positivo."
                )

        return min(
            procesos,
            key=lambda proceso: (
                proceso.tiempo_restante,
                proceso.tiempo_arribo,
                proceso.id,
            ),
        )

    def simular(self) -> None:
        """Ejecuta automaticamente hasta que admision no tenga trabajo pendiente."""
        while self.admision.hay_procesos_pendientes():
            self.avanzar_unidad()

    def avanzar_unidad(self) -> None:
        """Procesa arribos, reevalua SRTF y avanza una unidad discreta."""
        self.procesar_instante()
        self.ejecutar_unidad()

    def procesar_instante(self) -> None:
        """Atiende los arribos del instante actual y reevalua la CPU (SRTF).

        No avanza el reloj: luego de llamarlo, el estado observable es el del
        instante ``self.reloj``.
        """
        arribados = self.admision.procesar_arribos(self.reloj)
        self._informar_arribos(arribados, self.admision.extraer_transiciones())
        self._reevaluar_cpu()
        if self.proceso_en_ejecucion is None:
            self._informar_cpu_ociosa()

    def ejecutar_unidad(self) -> None:
        """Ejecuta una unidad de CPU y avanza el reloj de ``t`` a ``t + 1``.

        Si el proceso termina, se informa en ``t + 1`` junto con la liberacion
        de memoria, las nuevas admisiones y el siguiente proceso en CPU.
        """
        if self.proceso_en_ejecucion is None:
            self.linea_tiempo.append(None)
            self.reloj += 1
            return

        self._cpu_ociosa_informada = False
        proceso = self.proceso_en_ejecucion
        self.linea_tiempo.append(proceso.id)
        if proceso.tiempo_inicio is None:
            proceso.tiempo_inicio = self.reloj

        proceso.tiempo_restante -= 1
        self.reloj += 1

        if proceso.tiempo_restante == 0:
            self._finalizar(proceso)

    def _reevaluar_cpu(self) -> None:
        listos = list(self.admision.obtener_listos())
        elegido = self.seleccionar_srtf(listos)
        actual = self.proceso_en_ejecucion

        if actual is not None:
            if elegido is None or actual.tiempo_restante <= elegido.tiempo_restante:
                return

            self.admision.devolver_a_listo(actual)
            self.admision.enviar_a_ejecucion(elegido)
            self.proceso_en_ejecucion = elegido
            self.cambios_contexto += 1
            self._emitir(
                TIPO_APROPIACION,
                elegido,
                f"{elegido.id} apropia la CPU a {actual.id}: tiene menor "
                f"tiempo restante ({elegido.tiempo_restante} ut contra "
                f"{actual.tiempo_restante} ut). {elegido.id} pasa de LISTO a "
                f"EJECUCION y {actual.id} pasa de EJECUCION a LISTO.",
            )
            return

        if elegido is not None:
            self._asignar_cpu(elegido)
            self._informar_inicio(elegido)

    def _asignar_cpu(self, proceso: Proceso) -> None:
        """Ocupa una CPU libre con un proceso LISTO en el mismo instante."""
        self.admision.enviar_a_ejecucion(proceso)
        self.proceso_en_ejecucion = proceso
        self.cambios_contexto += 1

    def _finalizar(self, proceso: Proceso) -> None:
        proceso.tiempo_finalizacion = self.reloj
        self.admision.finalizar(proceso)
        self.proceso_en_ejecucion = None

        particion = self.memoria.obtener_asignacion(proceso)
        memoria_liberada = self.memoria.liberar(proceso)
        libre_tras_liberar = self.memoria.memoria_libre_total()
        self.admision.reintentar_suspendidos()
        transiciones_reintento = self.admision.extraer_transiciones()
        # Los arribos de este mismo instante participan de la eleccion SRTF.
        arribados = self.admision.procesar_arribos(self.reloj)
        transiciones_arribo = self.admision.extraer_transiciones()
        siguiente = self.seleccionar_srtf(self.admision.obtener_listos())
        if siguiente is not None:
            self._asignar_cpu(siguiente)

        # Se informan los cambios en el orden en que ocurrieron.
        self._emitir(
            TIPO_FINALIZACION,
            proceso,
            f"{proceso.id} finaliza: completa su tiempo de irrupcion "
            f"({proceso.tiempo_irrupcion} ut) y pasa de EJECUCION a TERMINADO.",
        )

        if memoria_liberada and particion is not None:
            self._emitir(
                TIPO_MEMORIA_LIBERADA,
                proceso,
                f"Se libera la memoria de {proceso.id} (particion "
                f"{particion.numero}): {particion.tamanio}K en "
                f"[{particion.direccion_inicio}K - {particion.direccion_fin}K). "
                f"Quedan {libre_tras_liberar}K libres para reintentar admisiones.",
            )

        for transicion in transiciones_reintento:
            self._informar_transicion(transicion)

        self._informar_arribos(arribados, transiciones_arribo)

        if siguiente is not None:
            self._informar_inicio(siguiente)

    def _informar_inicio(self, proceso: Proceso) -> None:
        self._emitir(
            TIPO_INICIO,
            proceso,
            f"{proceso.id} pasa de LISTO a EJECUCION (ingresa a la CPU con "
            f"{proceso.tiempo_restante} ut restantes).",
        )

    def _informar_arribos(
        self,
        arribados: Sequence[Proceso],
        transiciones: Sequence[TransicionAdmision],
    ) -> None:
        """Informa cada arribo junto con el estado al que pasa y el motivo."""
        ids_arribados = {proceso.id for proceso in arribados}
        por_proceso: Dict[str, TransicionAdmision] = {}
        otras: List[TransicionAdmision] = []
        for transicion in transiciones:
            proceso_id = transicion.proceso.id
            if (
                proceso_id in ids_arribados
                and transicion.origen == ESTADO_NUEVO
                and proceso_id not in por_proceso
            ):
                por_proceso[proceso_id] = transicion
            else:
                otras.append(transicion)

        for proceso in arribados:
            transicion = por_proceso.get(proceso.id)
            if transicion is None:
                detalle = (
                    f"{proceso.id} llega y permanece en NUEVO (sin cupo de "
                    "multiprogramacion: ya hay "
                    f"{self.admision.grado_multiprogramacion()} procesos "
                    "admitidos)."
                )
            else:
                detalle = (
                    f"{proceso.id} llega y pasa a {transicion.destino} "
                    f"({transicion.motivo})."
                )
            self._emitir(TIPO_ARRIBO, proceso, detalle)

        for transicion in otras:
            self._informar_transicion(transicion)

    def _informar_transicion(self, transicion: TransicionAdmision) -> None:
        proceso = transicion.proceso
        if transicion.origen == transicion.destino:
            self._emitir(
                TIPO_SIGUE_SUSPENDIDO,
                proceso,
                f"{proceso.id} permanece en {transicion.destino} "
                f"({transicion.motivo}).",
            )
            return
        self._emitir(
            TIPO_NUEVA_ADMISION,
            proceso,
            f"{proceso.id} pasa de {transicion.origen} a {transicion.destino} "
            f"({transicion.motivo}).",
        )

    def _informar_cpu_ociosa(self) -> None:
        if not self._cpu_ociosa_informada:
            self._emitir(
                TIPO_CPU_OCIOSA,
                detalle="La CPU se encuentra ociosa (no hay procesos en LISTO).",
            )
            self._cpu_ociosa_informada = True

    def _emitir(
        self,
        tipo: str,
        proceso: Optional[Proceso] = None,
        detalle: str = "",
    ) -> None:
        if self.observador is not None:
            self.observador(
                EventoPlanificador(
                    tiempo=self.reloj,
                    tipo=tipo,
                    proceso_id=None if proceso is None else proceso.id,
                    detalle=detalle,
                )
            )
