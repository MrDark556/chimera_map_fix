**English** | [Español](README.es.md) | [Português (Brasil)](README.pt-BR.md)

# Chimera Hybrid Map Downloader

A lightweight map downloader and launcher for **Halo Custom Edition + Chimera**.

This tool is mainly meant for players who have trouble with Chimera's normal HaloNet map downloader, although anyone can use it.

When Chimera requests a custom map you don't have, the downloader automatically tries several Halo CE map sources until it finds a working copy.

## Installation

### 1. Download the launcher


You can place the EXE file wherever is convenient for you.

### 2. Edit `chimera.ini`

Open your Chimera configuration file:

```text
chimera.ini
```

Find the section:

```ini
[memory]
```

Add or enable this line:

```ini
download_template=http://127.0.0.1:8765/{map}
```

If you already have another `download_template` line active, comment it out by putting a semicolon (`;`) at the beginning.

For example:

```ini
[memory]

;download_template=http://maps.halonet.net/halonet/locator.php?format=inv&map={map}&type={game}
download_template=http://127.0.0.1:8765/{map}
```

> **Important:** Only one `download_template` line should be active.

---

## Download sources

The downloader tries sources in this order:

1. **Normal HaloNet locator**
2. **HaloNet static ZIP archive**
3. **CE3**
4. **HaloMaps.org**

If the normal HaloNet downloader works for you, Chimera will keep using its normal download behavior and progress.

If HaloNet fails and the program needs to use one of the alternate sources, a small progress window will appear showing information such as:

- Map name
- Current download source
- Percentage downloaded
- MB downloaded
- Download speed
- Estimated time remaining
- Search / extraction status

---

## Starting Halo

After configuring Chimera, start Halo Custom Edition using:

```text
ChimeraMapDownloader.exe
```

If you want the downloader to start automatically, **do not open `haloce.exe` directly**.

The launcher will do the following:

1. Silently start the map downloader in the background.
2. Start Halo Custom Edition.
3. Keep the downloader running while Halo is open.
4. Automatically close the downloader when Halo closes.

No Command Prompt or BAT window is shown.

---

## First launch

The launcher will try to find `haloce.exe` automatically.

If Halo Custom Edition is installed in a non-standard location, you'll be asked to select:

```text
haloce.exe
```

once.

The location will be saved for future launches.

---

## How each source works

### HaloNet — Normal locator

This is Chimera/HaloNet's normal map download method.

If it works for you, the custom alternate progress window will **not** appear, since Chimera handles the download normally.

### HaloNet — Alternate static ZIP

If the normal HaloNet locator fails, the downloader will try to fetch the map directly from HaloNet's static ZIP archive.

The file is downloaded, the `.map` is extracted and validated, and then handed off to Chimera.

### CE3

The downloader searches the CE3 Halo Custom Edition archive.

CE3 entries display the map's internal name, so the downloader verifies the requested `.map` filename before accepting a result.

### HaloMaps.org

HaloMaps.org is used as an additional fallback source if the previous sources can't provide the requested map.

The downloader searches the archive, resolves the matching entry, downloads the file, extracts the map, validates it, and hands it off to Chimera.

---

## Download progress

When the normal HaloNet locator works, Chimera uses its normal progress indicator.

The custom progress window is only used for alternate downloads, where Halo would otherwise be stuck showing:

```text
Connecting to map server...
```

The alternate window may show:

```text
Map: example_map
Source: CE3
Downloading...

102.4 MB / 150.6 MB
7.3 MB/s
~7s remaining
```

During non-download stages it may show, for example:

```text
Searching CE3...
Extracting map...
Validating map...
```

The window closes automatically once the map is ready.

---

## Stall protection

To prevent Halo from staying indefinitely on **Connecting to map server...**:

| Limit | Time |
|---|---:|
| Max time without network activity | 15 seconds |
| Max time per map/file transfer | 5 minutes |
| Absolute limit per request | 6 minutes |

Large maps may take a bit to download and extract before Halo starts loading them.

---

## Logs and troubleshooting

Runtime files are saved at:

```text
%LOCALAPPDATA%\ChimeraHybridMapDownloader
```

Useful log files include:

```text
chimera_downloader.log
launcher.log
```

If a map fails to download, include the following when reporting the issue:

- Map name
- Which server/source was being attempted
- `chimera_downloader.log`
- `launcher.log` if the issue was with the launcher

---

## Requirements

- Windows
- Halo Custom Edition
- Chimera

The public release of `ChimeraMapDownloader.exe` does **not** require Python to be installed.

---

## Windows SmartScreen

The executable may show an **Unknown Publisher** warning or Windows SmartScreen prompt because it isn't digitally signed.

This is normal for unsigned community executables.

---

## Quick setup

1. [Download `ChimeraMapDownloader.exe`](https://github.com/MrDark57/chimera-custom-map-downloader/releases/latest/download/ChimeraMapDownloader.exe)
2. Open `chimera.ini`.
3. Under `[memory]`, set:

```ini
download_template=http://127.0.0.1:8765/{map}
```

4. Comment out any other active `download_template` line.
5. Start Halo using:

```text
ChimeraMapDownloader.exe
```

6. Join servers normally.

---

## Current source priority

```text
Normal HaloNet locator
        ↓
HaloNet static ZIP
        ↓
CE3
        ↓
HaloMaps.org
```

---

Enjoy Halo Custom Edition!
