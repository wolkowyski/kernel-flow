"""Pruebas de las mejoras visuales: mapa de memoria, Gantt, SRTF y exportacion."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from admision import Admision
from carga import cargar_procesos
from estilo import Estilo, a_ascii, largo_visible, quitar_colores
from exportar import ansi_a_html, guardar_simulacion
from memoria import GestorMemoria
from panel import PanelConsola, _escala_gantt, _repartir
from planificador import PlanificadorSRTF
from proceso import Proceso


def _armar(procesos):
    memoria = GestorMemoria()
    admision = Admision(procesos, memoria)
    panel = PanelConsola(procesos, admision, memoria, Estilo(color=True, unicode=True))
    eventos = []
    planificador = PlanificadorSRTF(admision, memoria, eventos.append)
    panel.linea_tiempo = planificador.linea_tiempo
    return panel, planificador, eventos


class TestLineaDeTiempo(unittest.TestCase):
    def test_registra_cada_unidad_de_cpu_y_las_ociosas(self):
        procesos = [Proceso("P1", 50, 2, 2), Proceso("P2", 50, 2, 1)]
        _, planificador, _ = _armar(procesos)
        planificador.simular()
        self.assertEqual(planificador.linea_tiempo, [None, None, "P2", "P1", "P1"])

    def test_demo_coincide_con_la_traza_esperada(self):
        procesos = cargar_procesos(Path("data/procesos_demo.csv"))
        _, planificador, _ = _armar(procesos)
        planificador.simular()
        traza = "".join(pid[-1] for pid in planificador.linea_tiempo)
        self.assertEqual(traza, "1222246664444111111155333333333")


class TestAuxiliares(unittest.TestCase):
    def test_repartir_respeta_el_ancho_y_el_minimo(self):
        anchos = _repartir([100, 120, 150, 100, 80], 550, 90, minimo=3)
        self.assertEqual(sum(anchos), 90)
        self.assertTrue(all(ancho >= 3 for ancho in anchos))
        self.assertGreater(anchos[2], anchos[4])

    def test_repartir_con_huecos_muy_chicos(self):
        anchos = _repartir([100, 2, 448], 550, 60, minimo=3)
        self.assertEqual(sum(anchos), 60)
        self.assertEqual(anchos[1], 3)

    def test_escala_gantt(self):
        self.assertEqual(_escala_gantt(31, 120), (1, 3))
        self.assertEqual(_escala_gantt(100, 120), (1, 1))
        self.assertEqual(_escala_gantt(300, 100), (3, 1))

    def test_a_ascii_conserva_el_ancho(self):
        texto = "┌─┐│█░►·═"
        self.assertEqual(len(a_ascii(texto)), len(texto))
        self.assertTrue(a_ascii(texto).isascii())


class TestPanelVisual(unittest.TestCase):
    def _paso_demo(self, hasta_tiempo):
        procesos = cargar_procesos(Path("data/procesos_demo.csv"))
        panel, planificador, eventos = _armar(procesos)
        while planificador.reloj < hasta_tiempo:
            planificador.procesar_instante()
            eventos.clear()
            planificador.ejecutar_unidad()
        planificador.procesar_instante()
        salida = io.StringIO()
        with redirect_stdout(salida), mock.patch("panel.ancho_terminal", return_value=170):
            panel.mostrar_paso(eventos, planificador.reloj, 9)
        return quitar_colores(salida.getvalue())

    def test_paso_con_fragmentacion_muestra_mapa_srtf_y_cambios(self):
        texto = self._paso_demo(13)
        self.assertIn("Mapa de memoria", texto)
        self.assertIn("Fragmentacion externa: 230K libres repartidos en 2 huecos", texto)
        self.assertIn("libre 150K", texto)
        self.assertIn("Menor tiempo restante: P1(7) < P3(9)", texto)
        self.assertIn("usa la CPU P1", texto)
        self.assertIn("► cambio de estado en este paso", texto)
        self.assertIn("█░░░░░░░ 1/8", texto)
        self.assertIn("Uso de la CPU hasta ahora", texto)

    def test_empate_srtf_se_explica(self):
        procesos = [Proceso("P1", 50, 0, 4), Proceso("P2", 50, 2, 2)]
        panel, planificador, eventos = _armar(procesos)
        for _ in range(2):
            planificador.procesar_instante()
            planificador.ejecutar_unidad()
        planificador.procesar_instante()
        salida = io.StringIO()
        with redirect_stdout(salida):
            panel.mostrar_paso(eventos, planificador.reloj, 1)
        texto = quitar_colores(salida.getvalue())
        self.assertIn("P1(2) = P2(2)", texto)
        self.assertIn("Empate de tiempo restante: el proceso que ya esta en CPU la conserva", texto)

    def test_fin_muestra_gantt_y_barras(self):
        procesos = cargar_procesos(Path("data/procesos_demo.csv"))
        panel, planificador, _ = _armar(procesos)
        planificador.simular()
        salida = io.StringIO()
        with redirect_stdout(salida), mock.patch("panel.ancho_terminal", return_value=170):
            panel.mostrar_fin(planificador.reloj)
        texto = quitar_colores(salida.getvalue())
        self.assertIn("Diagrama de Gantt", texto)
        self.assertIn("Retorno y espera por proceso", texto)
        filas_gantt = [l for l in texto.splitlines() if l.strip().startswith(("P1 ", "CPU "))]
        self.assertTrue(any("█" in fila for fila in filas_gantt))

    def test_tablas_con_barras_de_progreso_quedan_alineadas(self):
        procesos = cargar_procesos(Path("data/procesos_demo.csv"))
        panel, _, _ = _armar(procesos)
        lineas = panel._tabla_procesos(0, {"P1"})
        tabla = [l for l in lineas if "│" in l or "┌" in l or "└" in l]
        self.assertGreater(len(tabla), 6)
        self.assertEqual(len({largo_visible(l) for l in tabla}), 1)


class TestExportar(unittest.TestCase):
    def test_ansi_a_html(self):
        estilo = Estilo(color=True)
        html = ansi_a_html(estilo.c("P1", "amarillo", "negrita") + " <ok>")
        self.assertRegex(html, r'<span style="[^"]*color:#ffd75f[^"]*">P1</span>')
        self.assertIn("font-weight:bold", html)
        self.assertIn("&lt;ok&gt;", html)

    def test_guardar_simulacion_crea_txt_y_html(self):
        estilo = Estilo(color=True)
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_txt, ruta_html = guardar_simulacion(
                [estilo.c("PASO 1", "cian"), "linea"], Path(carpeta), "lote.csv"
            )
            self.assertEqual(ruta_txt.read_text(encoding="utf-8"), "PASO 1\nlinea")
            self.assertIn("color:#4fd6e6", ruta_html.read_text(encoding="utf-8"))
            self.assertIn("simulacion_lote_", ruta_txt.name)


if __name__ == "__main__":
    unittest.main()
