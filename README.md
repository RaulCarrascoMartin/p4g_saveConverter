# p4g_saveConverter

Convierte saves de **Persona 4 Golden de PC (Steam)** al formato de **PS Vita**, para continuar en la consola una partida empezada en PC.

Es un único script en Python 3 sin dependencias (`p4g_pc2vita.py`).

## Qué hace

Los saves de PC y de Vita son casi iguales, pero no se pueden copiar tal cual. El script:

| Entrada (PC) | Salida (Vita) | Qué cambia |
|---|---|---|
| `data00XX.bin` | `data00XX.bin` | Reescribe el segmento de *rescue requests* (en PC es más grande), rellena el archivo hasta `0x38000` bytes y recalcula el checksum de `0x3165C`. Desactiva el flag de dificultad personalizada (ver más abajo). |
| `system.bin` | `system.bin` | Se copia igual. |
| `data00XX.binslot` + `system.binslot` | `sce_sys/sdslot.dat` | PC guarda los metadatos de cada slot en un `.binslot`. La Vita los junta todos en un solo `sdslot.dat` (17 slots de `0x400` bytes). El texto de cada slot se reescribe con el formato en inglés. |

Los slots se conservan: `data0001.bin` de PC pasa a ser el slot 1 de la Vita, y así con los demás.

## Requisitos

- Python 3.9 o superior.
- Los archivos del save de PC, en la carpeta `remote` de Steam. En Windows suele ser `C:\Program Files (x86)\Steam\userdata\<tu_id>\1113000\remote\`. Necesitas, por cada slot, el `data00XX.bin` **y** su `data00XX.binslot`, además de `system.bin` y `system.binslot`. Un `.bin` sin su `.binslot` se omite.
- Una Vita con CFW (HENkaku/Enso) y **VitaShell**. Funciona con el juego en versión USA (`PCSE00120`) o EUR (`PCSB00245`).

## Uso

```bash
python3 p4g_pc2vita.py <carpeta_con_los_saves_de_pc> [opciones]
```

Ejemplo, conservando los otros slots que ya tengas en la Vita:

```bash
python3 p4g_pc2vita.py P4GoldenPC --base-sdslot ruta/a/tu/sdslot.dat
```

Crea `<carpeta>_conv/` con los `.bin`, `system.bin` y `sce_sys/sdslot.dat`.

| Opción | Descripción |
|---|---|
| `--base-sdslot RUTA` | `sdslot.dat` actual de tu Vita. Los slots que no conviertas se conservan. Sin esta opción se genera uno nuevo con solo los slots convertidos. |
| `--custom-diff {disable,enable,keep}` | Flag del menú de dificultad personalizada (`disable` por defecto, ver más abajo). |
| `-o, --output RUTA` | Carpeta de salida (por defecto `<carpeta>_conv`). |

### Copiar los saves a la Vita

> **Haz una copia de seguridad antes.** Los slots que conviertas sobrescriben los que ya tengas con el mismo número.

1. Pasa la carpeta de salida a la Vita (por FTP o USB) a una carpeta temporal, por ejemplo `ux0:/data/p4g_import/`.
2. En **VitaShell** entra en esa carpeta: `△` → **Mark all** → `△` → **Copy**.
3. Ve a `ux0:/user/00/savedata/`, deja el cursor sobre `PCSE00120` (USA) o `PCSB00245` (EUR) y pulsa `△` → **Open decrypted**. Si la carpeta no existe, abre el juego y guarda una vez.
4. Dentro, `△` → **Paste** y acepta reemplazar.
5. Abre el juego → **Load game**.

**No copies por FTP directamente a `savedata/<ID>`, ni restaures con Save Manager.** Esa carpeta está cifrada (PFS) y, copiando así, el juego muestra *No data* en todos los slots. Hay que usar "Open decrypted".

## Diferencias con el conversor de zarroboogs

Está basado en el formato documentado en [zarroboogs/p4g-saveconv](https://github.com/zarroboogs/p4g-saveconv) (`convert_pc2vita.py`). Es una reimplementación propia, no una copia, con estos cambios:

### 1. Saves de PC en otros idiomas: el juego ya no se congela (el problema principal)

El conversor original, al pasar los metadatos de cada slot, solo elimina la línea `LANG1` (inglés). Con un save de PC en **español** (`LANG8`), el texto del slot llega a la Vita con etiquetas en español (`Fecha:`, `Nombre:`, `Ubicación:`, `Tiempo de juego:`…). Resultado con una Vita EUR: **el juego se congela al entrar en Load game**.

Esto se acotó probando variantes de `sdslot.dat` sobre saves nativos de Vita que cargaban bien:

| Variante de `sdslot.dat` | Resultado |
|---|---|
| Solo marcas de tiempo convertidas | Carga bien |
| Texto del slot convertido (español) | Se congela |
| Texto en inglés, formato nativo de la Vita | Carga bien |
| Etiquetas en español sin tildes | Se congela |

Este conversor elimina **cualquier** línea `LANGn` y reescribe el texto del slot con las etiquetas en inglés (`Date`, `Name`, `Difficulty`, `Location`, `Play Time`, `Times Cleared`), cambiando `Nv.` por `Lv`, traduciendo algunos nombres frecuentes y quitando las tildes del resto. Es solo la vista previa del slot: la partida no cambia y el juego reescribe ese texto al volver a guardar.

Sin determinar: no se aisló si el congelamiento lo causan las etiquetas en español, los valores o la longitud del texto (los textos en español medían unos 175-180 bytes y los que cargaban, 166 como máximo). Por eso se reescribe todo el bloque.

### 2. Conserva los otros slots de tu Vita

`--base-sdslot` parte del `sdslot.dat` que ya tienes y solo reemplaza los slots convertidos. El original genera un `sdslot.dat` nuevo desde cero, así que cualquier otro slot que no vengas de convertir deja de aparecer.

### 3. Dificultad personalizada desactivada por defecto

El menú de dificultad personalizada solo existe en PC. El original deja el flag (bits 0-1 de `0x1304`) como viene salvo que pases `--custom-diff`. Aquí el valor por defecto es `disable`, que coincide con lo que tenían los saves de la Vita que cargaban. Con `keep` se deja como en el save de PC. **No se probó si dejarlo activado causa problemas** por sí solo.

### 4. Otros cambios

- Trabaja en memoria y comprueba tamaños antes de convertir, con un error claro si el save es demasiado pequeño.
- Se niega a ejecutarse sobre una carpeta que ya contenga saves de Vita.
- Funciona con el Python que trae macOS (3.9).

## Estado de las pruebas

Probado con una Vita **EUR (`PCSB00245`)** y saves de PC en **español**: la pantalla de Load game ya no se congela y las partidas cargan y se pueden jugar. No se probó con la versión USA ni con saves de PC en otros idiomas, aunque el formato es el mismo.

Comprobado además con saves reales: los `.bin` convertidos coinciden byte a byte con los de otra conversión anterior, salvo el checksum y el flag de dificultad.

## Créditos

El formato de los saves y los offsets (`0x15120`, `0x190CC`, el checksum de `0x3165C`, el contenido de `sdslot.dat`) vienen de [zarroboogs/p4g-saveconv](https://github.com/zarroboogs/p4g-saveconv). Ese repositorio no declara licencia.
