KERNELFLOW - GUIA DE EJECUCION (HOWTO)
======================================

Simulador de asignacion de memoria (MVT, Best-Fit) y planificacion de
procesos (SRTF apropiativo). Sistemas Operativos - UTN FRRe - Grupo 15.


1. CONTENIDO DEL PAQUETE
------------------------

    KernelFlow-<sistema>/
    |-- HOWTO.txt            esta guia
    |-- ejecutable/
    |   |-- KernelFlow       programa listo para usar (KernelFlow.exe en Windows)
    |   `-- data/            lotes de prueba (.csv) y logo
    `-- codigo_fuente/       codigo Python, pruebas, lotes y documentacion

IMPORTANTE: el ejecutable busca la carpeta data/ a su lado. No los separe.


2. EJECUTAR EL PROGRAMA (sin instalar nada)
-------------------------------------------

Linux:
    cd KernelFlow-linux/ejecutable
    chmod +x KernelFlow        (solo la primera vez, si no tiene permiso)
    ./KernelFlow

Windows:
    Doble clic en ejecutable\KernelFlow.exe
    (o desde una consola: cd ejecutable  y luego  KernelFlow.exe)

Se recomienda la terminal maximizada (al menos 130 columnas) para ver las
tablas una al lado de la otra; con menos ancho se acomodan una debajo de otra.

Si los colores no se ven bien, ejecute con la opcion --sin-color:
    ./KernelFlow --sin-color          (Windows: KernelFlow.exe --sin-color)


3. EJECUTAR DESDE EL CODIGO FUENTE
----------------------------------

Requisitos: Python 3.8 o superior. No usa librerias externas.

    cd codigo_fuente
    python3 main.py                          menu interactivo
    python3 main.py data/lote_1_best_fit.csv simula un archivo directamente

En Windows use "py" en lugar de "python3".

Pruebas automaticas:
    python3 -m unittest discover -s tests -v


4. USO DEL MENU
---------------

    [1] Simula el lote de demostracion (data/procesos_demo.csv).
    [2] Muestra una lista numerada de los CSV de la carpeta data/.
        Escriba el numero del archivo, o:
          R  para escribir la ruta de un CSV propio,
          E  para buscarlo con el explorador (requiere entorno grafico),
          0  para volver.
    [3] Guia rapida: formato del CSV, reglas, estados y controles.
    [0] Salir.

Durante la simulacion:
    Espacio o Enter   avanza al siguiente cambio relevante
    B                 vuelve al paso anterior para revisarlo
    F                 alterna entre historial y pantalla fija
    Q                 detiene la simulacion y vuelve al menu

Al terminar (o al detenerla con Q):
    G                 guarda la simulacion en la carpeta resultados/,
                      como .txt y como .html con colores
    Enter             vuelve al menu

    [4] del menu      cambia entre HISTORIAL (los pasos quedan uno debajo
                      del otro) y PANTALLA FIJA (se limpia en cada paso)

Opciones de linea de comandos:
    --sin-color       sin colores
    --pantalla-fija   arranca en modo pantalla fija
    --exportar        guarda TXT y HTML automaticamente al terminar

La simulacion se detiene cada vez que llega o termina un proceso (y ante
apropiaciones, admisiones o CPU ociosa). Cada paso muestra:
  - los eventos del paso con una etiqueta de color y su motivo;
  - [SRTF]: los procesos candidatos ordenados por tiempo restante y cual
    usa la CPU (y si hubo empate);
  - el mapa de memoria: una barra proporcional con el SO, cada particion
    y los huecos libres (marca la fragmentacion externa);
  - la tabla de procesos (con barra de progreso y una marca en los que
    cambiaron de estado) y la tabla de particiones;
  - las tablas de CPU, cola LISTO y cola LISTO_SUSPENDIDO;
  - el uso de la CPU desde t = 0 (Gantt compacto).
Al finalizar muestra el informe estadistico, un grafico de barras de
retorno y espera por proceso y el diagrama de Gantt completo.


5. FORMATO DEL ARCHIVO CSV
--------------------------

Una linea por proceso, SIN encabezado, en este orden:

    id,tamanio,tiempo_arribo,tiempo_irrupcion

    id                 nombre unico del proceso (ej.: P1)
    tamanio            memoria que necesita, en KB (1 a 450)
    tiempo_arribo      instante de llegada (entero, desde 0)
    tiempo_irrupcion   tiempo de CPU que necesita (entero, mayor que 0)

Ejemplo:
    P1,120,0,8
    P2,150,1,4
    P3,100,2,9

Limites: entre 1 y 10 procesos. Si el archivo tiene errores (mas de 10
procesos, letras en un numero, ID repetido, columnas de mas o de menos,
proceso mayor a 450K) el programa informa la linea y el motivo y no inicia.


6. LOTES DE PRUEBA INCLUIDOS (carpeta data/)
--------------------------------------------

    procesos_demo.csv                    caso general: apropiacion SRTF,
                                         suspension por memoria y
                                         fragmentacion externa
    lote_1_best_fit.csv                  Best-Fit elige el hueco mas chico
                                         aunque haya otro mas grande antes
    lote_2_cupo_10_procesos.csv          10 procesos: cupo de
                                         multiprogramacion lleno (NUEVO),
                                         memoria llena (LISTO_SUSPENDIDO)
    lote_3_cpu_ociosa_memoria_exacta.csv CPU ociosa entre arribos y un
                                         proceso que ocupa los 450K exactos
    lote_4_empate_srtf.csv               empate de tiempo restante: el
                                         proceso en CPU la conserva


7. REGLAS DEL SIMULADOR
-----------------------

  - Memoria total 550K: 100K para el SO y 450K para procesos de usuario.
  - Particiones variables (MVT) con Best-Fit: cada proceso recibe una
    particion de su tamanio exacto en el hueco libre mas chico donde entra.
    Por eso la fragmentacion interna es siempre 0K. Al liberar, los huecos
    contiguos se unen.
  - Grado maximo de multiprogramacion 5: EJECUCION + LISTO +
    LISTO_SUSPENDIDO nunca supera 5. Sin cupo, el proceso queda en NUEVO.
    Con cupo pero sin hueco de memoria, pasa a LISTO_SUSPENDIDO.
  - Al terminar un proceso se libera su memoria y se reintenta admitir:
    primero los suspendidos (en orden de llegada), luego los NUEVO.
  - SRTF apropiativo: usa la CPU el proceso LISTO con menor tiempo
    restante. Ante empate, el que ya esta en CPU la conserva; si la CPU
    esta libre, gana el de menor arribo y luego el de menor ID.
  - Los arribos simultaneos se atienden en el orden del CSV.


8. INFORME ESTADISTICO
----------------------

  T. Retorno   = T. Finalizacion - T. Arribo
  T. Espera    = T. Retorno - T. Irrupcion
                 (incluye el tiempo en NUEVO, LISTO_SUSPENDIDO y LISTO)
  T. Respuesta = primer instante en CPU - T. Arribo
  Rendimiento  = procesos terminados / tiempo total de la simulacion


9. GENERAR EL EJECUTABLE (solo para desarrolladores)
----------------------------------------------------

    python3 -m pip install pyinstaller
    python3 empaquetar.py

Corre las pruebas, genera el ejecutable y deja el paquete en
entrega/KernelFlow-<sistema>.zip. El ejecutable de Linux se genera en
Linux y el de Windows en Windows.
