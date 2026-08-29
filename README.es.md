[English](README.md) | **Español** | [Português (Brasil)](README.pt-BR.md)

# Chimera Hybrid Map Downloader

Un descargador y lanzador ligero de mapas para **Halo Custom Edition + Chimera**.

Este proyecto fue coautoría de Mark and Dark

Esta herramienta está pensada principalmente para jugadores que tienen problemas con el descargador normal de mapas de HaloNet en Chimera, aunque cualquiera puede usarla.

Cuando Chimera solicita un mapa personalizado que no tienes, el descargador intenta automáticamente varias fuentes de mapas de Halo CE hasta encontrar una copia funcional.

## Instalación

### 1. Descarga el lanzador

Para la versión en español, usa **`haloce_chimera_mpdlr_es.exe`**.

Coloca `haloce_chimera_mpdlr_es.exe` en la **misma carpeta que el `haloce.exe` original que usas con Chimera**. Este es el método recomendado, especialmente para instalaciones portátiles de Halo CE.

Si es necesario, también puedes editar manualmente la ubicación guardada de Halo en:

```text
%LOCALAPPDATA%\ChimeraHybridMapDownloader\launcher_config.ini
```

Normalmente, basta con colocar el archivo junto al `haloce.exe` correcto y ejecutarlo.

### 2. Edita `chimera.ini`

Abre tu archivo de configuración de Chimera:

```text
chimera.ini
```

Busca la sección:

```ini
[memory]
```

Agrega o habilita esta línea:

```ini
download_template=http://127.0.0.1:8765/{map}
```

Si ya tienes otra línea `download_template` activa, coméntala colocando un punto y coma (`;`) al principio.

Por ejemplo:

```ini
[memory]

;download_template=http://maps.halonet.net/halonet/locator.php?format=inv&map={map}&type={game}
download_template=http://127.0.0.1:8765/{map}
```

> **Importante:** Solo debe haber una línea `download_template` activa.

---

## Fuentes de descarga

El descargador prueba las fuentes en este orden:

1. **Localizador normal de HaloNet**
2. **Archivo ZIP estático de HaloNet**
3. **CE3**
4. **HaloMaps.org**

Si el descargador normal de HaloNet funciona para ti, Chimera seguirá usando su comportamiento y progreso de descarga normal.

Si HaloNet falla y el programa necesita usar una de las fuentes alternativas, aparecerá una pequeña ventana de progreso mostrando información como:

- Nombre del mapa
- Fuente de descarga actual
- Porcentaje descargado
- MB descargados
- Velocidad de descarga
- Tiempo restante estimado
- Estado de búsqueda / extracción

---

## Iniciar Halo

Después de configurar Chimera, inicia Halo Custom Edition usando la versión en español:

```text
haloce_chimera_mpdlr_es.exe
```

Si quieres que el descargador se inicie automáticamente, **no abras `haloce.exe` directamente**.

El lanzador hará lo siguiente:

1. Inicia silenciosamente el descargador de mapas en segundo plano.
2. Inicia Halo Custom Edition.
3. Mantiene el descargador activo mientras Halo esté abierto.
4. Cierra automáticamente el descargador cuando Halo se cierre.

No se muestra ninguna ventana de Símbolo del sistema ni de BAT.

---

## Primer inicio

El lanzador primero busca `haloce.exe` en la **misma carpeta que el descargador**. Si lo encuentra, usará automáticamente esa instalación.

De lo contrario, puede usar una ubicación guardada previamente o buscar en las ubicaciones comunes de Halo CE. Si encuentra una instalación estándar, te preguntará si esa es la correcta. Si no lo es, podrás seleccionar manualmente tu `haloce.exe`.

La ubicación confirmada se guarda para futuros inicios en:

```text
%LOCALAPPDATA%\ChimeraHybridMapDownloader\launcher_config.ini
```

---

## Cómo funciona cada fuente

### HaloNet — Localizador normal

Este es el método normal de descarga de mapas de Chimera/HaloNet.

Si funciona para ti, la ventana personalizada de progreso alternativo **no** aparecerá, ya que Chimera maneja la descarga normalmente.

### HaloNet — ZIP estático alternativo

Si el localizador normal de HaloNet falla, el descargador intentará obtener el mapa directamente desde el archivo ZIP estático de HaloNet.

El archivo se descarga, el `.map` se extrae y valida, y luego se entrega a Chimera.

### CE3

El descargador busca en el archivo de Halo Custom Edition de CE3.

Las entradas de CE3 muestran el nombre interno del mapa, por lo que el descargador verifica el nombre solicitado del archivo `.map` antes de aceptar un resultado.

### HaloMaps.org

HaloMaps.org se utiliza como una fuente alternativa adicional si las fuentes anteriores no pueden proporcionar el mapa solicitado.

El descargador busca en el archivo, resuelve la entrada correspondiente, descarga el archivo, extrae el mapa, lo valida y lo entrega a Chimera.

---

## Progreso de descarga

Cuando el localizador normal de HaloNet funciona, Chimera usa su indicador normal de progreso.

La ventana de progreso personalizada solo se usa para descargas alternativas, donde Halo de otro modo podría quedarse mostrando:

```text
Connecting to map server...
```

La ventana alternativa puede mostrar:

```text
Map: example_map
Source: CE3
Downloading...

102.4 MB / 150.6 MB
7.3 MB/s
~7s remaining
```

Durante etapas que no son de descarga puede mostrar, por ejemplo:

```text
Searching CE3...
Extracting map...
Validating map...
```

La ventana se cierra automáticamente cuando el mapa está listo.

---

## Protección contra bloqueos

Para evitar que Halo permanezca indefinidamente en **Connecting to map server...**:

| Límite | Tiempo |
|---|---:|
| Tiempo máximo sin actividad de red | 15 segundos |
| Tiempo máximo por transferencia de mapa/archivo | 5 minutos |
| Límite absoluto por solicitud | 6 minutos |

Los mapas grandes pueden tardar un poco en descargarse y extraerse antes de que Halo empiece a cargarlos.

---

## Registros y solución de problemas

Los archivos de ejecución se guardan en:

```text
%LOCALAPPDATA%\ChimeraHybridMapDownloader
```

Los archivos de registro útiles incluyen:

```text
chimera_downloader.log
launcher.log
```

Si un mapa no se descarga, incluye lo siguiente al reportar el problema:

- Nombre del mapa
- Qué servidor/fuente se estaba intentando usar
- `chimera_downloader.log`
- `launcher.log` si el problema fue con el lanzador

---

## Requisitos

- Windows
- Halo Custom Edition
- Chimera

La versión pública en español, `haloce_chimera_mpdlr_es.exe`, **no** requiere que Python esté instalado.

---

## Windows SmartScreen / Antivirus

**No es necesario desactivar el antivirus** para usar el descargador de mapas.

Como el EXE es un programa comunitario sin firma digital y está compilado con PyInstaller, Windows SmartScreen o algunos antivirus pueden mostrar una advertencia de **Editor desconocido** o un falso positivo. Si ocurre, verifica que el archivo provenga de la fuente oficial y permite/restaura **solo este EXE** si confías en él.

No desactives completamente tu antivirus.

---

## Configuración rápida

1. Obtén **`haloce_chimera_mpdlr_es.exe`** (la versión en español; también puede distribuirse directamente por Discord) y colócala junto al `haloce.exe` que usas con Chimera.
2. Abre `chimera.ini`.
3. En `[memory]`, configura:

```ini
download_template=http://127.0.0.1:8765/{map}
```

4. Comenta cualquier otra línea `download_template` activa.
5. Inicia Halo usando:

```text
haloce_chimera_mpdlr_es.exe
```

6. Únete a los servidores normalmente.

---

## Prioridad actual de fuentes

```text
Localizador normal de HaloNet
        ↓
ZIP estático de HaloNet
        ↓
CE3
        ↓
HaloMaps.org
```

---

¡Disfruta Halo Custom Edition!
