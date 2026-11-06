# KernelFlow

Simulador de procesos y memoria por consola para Linux, desarrollado en Python 3.
Carga hasta 10 procesos desde un CSV, asigna 450K de memoria de usuario con
MVT y Best-Fit, y planifica la CPU con SRTF apropiativo. Los primeros 100K
quedan reservados para el sistema operativo.

## Ejecucion

Desde la raiz del proyecto:

```bash
python3 main.py
```

Para usar otro archivo:

```bash
python3 main.py ruta/al/archivo.csv
```

No se requieren paquetes externos de Python. El archivo predeterminado es
`data/procesos_demo.csv`.

El menu muestra el logo de la UTN y una breve descripcion debajo de cada
opcion. Al elegir una opcion se limpia la pantalla:

- `[1]` simula el CSV de prueba `data/procesos_demo.csv`.
- `[2]` lista los CSV de `data/` para elegir uno por numero; con `R` se
  escribe la ruta de otro archivo y con `E` se abre el explorador de archivos
  (este ultimo requiere `tkinter` y entorno grafico).
- `[3]` muestra la guia rapida: formato del CSV, reglas, estados, columnas,
  informe final y controles.
- `[0]` sale del simulador.

Antes de empezar se muestra la tabla de procesos cargados. Durante la
simulacion: Espacio/Enter avanza al siguiente cambio, `B` vuelve al paso
anterior para revisarlo, `F` alterna entre historial y pantalla fija, y `q`
vuelve al menu. Al terminar, `G` guarda la simulacion en `resultados/` como
TXT y HTML con colores (o automaticamente con `--exportar`). La opcion 4 del
menu (o `--pantalla-fija`) elige el modo de pantalla. Funciona en Linux y
tambien en Windows (`py main.py`).

## Colores, tablas y graficos

Cada paso muestra, ademas de los eventos y las tablas:

- `[SRTF]`: los candidatos ordenados por tiempo restante y el elegido,
  aclarando cuando hay empate;
- un **mapa de memoria** proporcional (SO, particiones con un color por
  proceso y huecos libres), que marca la fragmentacion externa;
- una **barra de progreso** por proceso y una marca `►` en los que cambiaron
  de estado en ese paso;
- el **uso de la CPU** desde `t = 0`.

El informe final suma un grafico de barras de retorno y espera y el
**diagrama de Gantt** completo.

En una terminal, cada paso muestra los eventos con una etiqueta de color
(LLEGADA, SUSPENSION, APROPIACION, FIN, etc.) y tablas con bordes para los
procesos, la memoria principal, la CPU y las dos colas. Los estados tienen un
color propio (NUEVO gris, LISTO cian, LISTO/SUSP. amarillo, EJECUCION verde y
TERMINADO azul). Si la terminal no muestra bien los colores:

```bash
python3 main.py --sin-color
```

Tambien se respeta la variable de entorno `NO_COLOR`. Si la terminal no
soporta los caracteres de borde, las tablas se dibujan con `+`, `-` y `|`.

## Formato del CSV

Cada linea contiene `id,tamanio,tiempo_arribo,tiempo_irrupcion`, sin encabezado.
El tamanio se expresa en KB y los tiempos en unidades discretas.

```csv
P1,120,0,8
P2,150,1,4
P3,100,2,9
```

El simulador admite entre 1 y 10 procesos. Un proceso que requiere mas de
450K se rechaza antes de iniciar, porque nunca podria alojarse en memoria.

## Comportamiento

Los estados son `NUEVO`, `LISTO`, `LISTO_SUSPENDIDO`, `EJECUCION` y
`TERMINADO`. Como maximo cinco procesos pueden estar simultaneamente en
`LISTO`, `LISTO_SUSPENDIDO` o `EJECUCION`. Un proceso sin cupo permanece en
`NUEVO`; uno con cupo pero sin hueco de memoria pasa a `LISTO_SUSPENDIDO`.

Los arribos simultaneos se atienden segun el orden del CSV. Al liberar memoria,
se reintentan primero los suspendidos en orden de llegada y luego los nuevos
que esperan cupo. La simulacion avanza sin pedir una tecla por unidad y se
detiene en cada instante con cambios relevantes (llegadas, finalizaciones,
admisiones, apropiaciones o CPU ociosa).

Cada paso empieza con "COMIENZO DEL PASO" y termina con "FIN DEL PASO", y
muestra el estado del sistema en el instante del evento (`t`). Dentro del paso
se informan todas las transiciones con su origen, destino y motivo, por
ejemplo:

- `P5 llega y pasa a LISTO_SUSPENDIDO (requiere 200K y solo hay 0K libres).`
- `P5 permanece en LISTO_SUSPENDIDO (... el mayor hueco contiguo es de 150K (fragmentacion externa)).`
- `P2 apropia la CPU a P1 ... P2 pasa de LISTO a EJECUCION y P1 pasa de EJECUCION a LISTO.`

Las colas muestran el tiempo restante de cada proceso entre parentesis. En la
tabla de procesos, `T. Irrupcion` es el tiempo de irrupcion original,
`T. Ejecutado` el tiempo de CPU ya consumido y `T. Restante` el que falta para
terminar. La tabla de particiones muestra el ID de particion (0 es el SO; cada
particion recibe un numero al crearse y lo conserva hasta liberarse; los huecos
libres se muestran con `-`), direccion de comienzo, tamanio, proceso asignado y fragmentacion interna, que
en MVT es siempre 0K porque cada particion se crea del tamanio exacto del
proceso.

Al terminar, se presenta el informe estadistico:

- tiempo de retorno = finalizacion - arribo;
- tiempo de espera = retorno - irrupcion (incluye el tiempo en `NUEVO`,
  `LISTO_SUSPENDIDO` y `LISTO`);
- promedios de retorno y espera;
- tiempo de respuesta = primer instante en CPU - arribo;
- rendimiento = trabajos terminados / tiempo total de la simulacion.

## Caso de demostracion

`python3 main.py` ejecuta los seis procesos de `data/procesos_demo.csv`. Durante
el recorrido, P2 apropia la CPU en `t = 1`, P5 espera en
`LISTO_SUSPENDIDO` desde `t = 4` (en `t = 13` hay 230K libres pero
fragmentados), P6 apropia la CPU en `t = 6` y P5 ingresa a memoria en
`t = 20`. La ejecucion termina en `t = 31` con los 450K de usuario libres,
retorno promedio de 14.00 ut, espera promedio de 8.83 ut y rendimiento de
0.1935 trabajos por unidad de tiempo.

## Lotes de prueba

| Archivo | Que muestra |
|---|---|
| `procesos_demo.csv` | Apropiacion SRTF, suspension por memoria y fragmentacion externa |
| `lote_1_best_fit.csv` | Best-Fit elige el hueco mas chico aunque haya uno mas grande antes |
| `lote_2_cupo_10_procesos.csv` | 10 procesos: cupo de multiprogramacion y memoria llenos |
| `lote_3_cpu_ociosa_memoria_exacta.csv` | CPU ociosa entre arribos y un proceso de 450K exactos |
| `lote_4_empate_srtf.csv` | Empate de tiempo restante: el proceso en CPU la conserva |

## Entrega y ejecutable

`HOWTO.md` es la guia de ejecucion que va en el paquete. Para generar el
ejecutable y el ZIP de entrega:

```bash
python3 -m pip install pyinstaller
python3 empaquetar.py
```

El script corre las pruebas, genera el ejecutable con PyInstaller
(`kernelflow.spec`) y deja `entrega/KernelFlow-<sistema>.zip` con el
ejecutable, la carpeta `data/`, el codigo fuente y el HOWTO. PyInstaller no
genera ejecutables para otro sistema: el de Linux se arma en Linux.
`docs/GUIA_INFORME.md` indica que capturar para el informe.

## Estructura

- `carga.py` y `proceso.py`: lectura y modelo de procesos.
- `memoria.py`: MVT y Best-Fit.
- `estados.py` y `admision.py`: transiciones, cupo y colas.
- `planificador.py`: reloj y SRTF apropiativo.
- `estadisticas.py`: retorno, espera, respuesta, promedios y rendimiento.
- `presentacion.py`: salida de texto simple (sin terminal) e informe final.
- `panel.py`: panel de la terminal con tablas de procesos, particiones, CPU,
  cola LISTO y cola LISTO_SUSPENDIDO.
- `estilo.py`: colores ANSI y tablas con bordes, sin librerias externas.
- `exportar.py`: guarda la simulacion en TXT y HTML con colores.
- `main.py`: menu, entrada e integracion de los modulos.
- `empaquetar.py` y `kernelflow.spec`: ejecutable y paquete de entrega.

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```
