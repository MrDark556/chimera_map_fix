# HaloNet Filename Cache

`halonet_map_index.json` maps Halo/Chimera's case-insensitive map request to
the exact capitalization used by HaloNet's case-sensitive static ZIP path.

Example:

```text
Chimera requests: new_mombasa_race
Index resolves:   New_Mombasa_Race
Static URL:       https://maps.halonet.net/maps/New_Mombasa_Race.zip
```

## Why it exists

The normal HaloNet locator is case-insensitive, but users whose locator route
fails may need the downloader's direct static ZIP fallback. That static path
is case-sensitive.

Guessing capitalization is unreliable for names such as:

```text
New_Mombasa_Race
BMT_New_Mombasa
Blood_Glade
```

The index records HaloNet's exact filename instead.

## Updating locally

On a connection that can access HaloNet:

```powershell
py -3 "Update HaloNet Cache.py"
```

The updater uses only the Python standard library.

## Updating when HaloNet is region-blocked

Use the included GitHub Action:

1. Push `.github/workflows/update-halonet-cache.yml`.
2. Open the repository on GitHub.
3. Go to **Actions**.
4. Select **Update HaloNet map index**.
5. Choose **Run workflow**.

GitHub's runner fetches the map listing and commits the resulting
`halonet_map_index.json` back to the repository.

The action also runs weekly and only creates a commit if the list changes.

## Public EXE

The build script embeds the full JSON index into:

```text
haloce_chimera_mpdlr.exe
```

End users do not need the JSON file separately.

A newer JSON can also be placed at:

```text
%LOCALAPPDATA%\ChimeraHybridMapDownloader\halonet_map_index.json
```

and it will override the bundled copy without requiring a rebuild.
