# Guia para armar el informe con capturas

El informe final muestra el simulador funcionando con cada lote de prueba,
como evidencia de que cumple la consigna. Esta guia indica que capturar.

## Atajo: exportar a HTML

Al terminar cada lote, presionar `G` (o ejecutar con `--exportar`): se guarda
toda la simulacion en `resultados/` como HTML con colores. Abriendo ese HTML
en el navegador se pueden sacar las capturas de cada paso con calidad y sin
depender del tamanio de la terminal.

## Preparacion

- Generar el ejecutable con `python3 empaquetar.py` y sacar las capturas
  **desde el ejecutable** (es lo que se entrega).
- Terminal maximizada (al menos 120 columnas) para que las tablas de
  procesos y de memoria salgan una al lado de la otra.
- Fuente monoespaciada y fondo uniforme. Una captura por paso.

## Estructura sugerida

1. **Caratula**: universidad, facultad, materia, grupo 15, integrantes y
   enlace al tablero de Trello.
2. **Indice** (un apartado por lote).
3. **Menu principal**: captura con las opciones y sus descripciones.
4. **Seleccion de archivo**: captura de la opcion 2 con la lista de lotes.
5. **Un apartado por lote** (ver abajo), cada uno con:
   - la pantalla "PROCESOS CARGADOS";
   - una captura por cada paso (cada llegada y cada finalizacion);
   - la captura del informe estadistico final.
6. **Validaciones**: capturas de errores de carga (mas de 10 procesos,
   letras en un numero, proceso de mas de 450K).
7. **Decisiones de diseno**: copiar la seccion 7 del HOWTO (reglas,
   desempate, convencion de tiempos) y la seccion 8 (formulas).

## Que debe verse en cada lote

| Lote | Pasos clave a destacar |
|---|---|
| `procesos_demo.csv` | t=1 P2 apropia a P1; t=4 P5 pasa a LISTO_SUSPENDIDO; t=13 P5 sigue suspendido por fragmentacion externa (230K libres en dos huecos); t=20 P5 entra a memoria |
| `lote_1_best_fit.csv` | t=6 P6 (90K) elige el hueco de 100K y no el de 150K; t=7 P7 (140K) usa el de 150K |
| `lote_2_cupo_10_procesos.csv` | t=0 multiprogramacion 5/5: D y E en LISTO_SUSPENDIDO y F en NUEVO; como entran a medida que terminan otros |
| `lote_3_cpu_ociosa_memoria_exacta.csv` | t=2, t=9 y t=14 CPU OCIOSA; t=15 P5 ocupa los 450K completos |
| `lote_4_empate_srtf.csv` | t=6 P6 llega con 3 ut y P3 tiene 3 ut restantes: P3 conserva la CPU |

## Consejos

- Resaltar (recuadro o flecha) el evento importante de cada captura.
- Debajo de cada captura, una linea explicando que paso en ese instante.
- Verificar que el ID de particion de un proceso no cambie entre pasos.
