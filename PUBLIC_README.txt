CHIMERA HYBRID MAP DOWNLOADER v3.5
==================================

NEW IN v3.5: FALLBACK DOWNLOAD WINDOW
-------------------------------------
If normal HaloNet works, nothing changes:
- Chimera/Halo displays its normal map download progress.
- The custom progress popup does NOT appear.

If normal HaloNet fails and the downloader has to use a fallback:
- HaloNet static ZIP
- CE3
- HaloMaps.org

a small progress window appears automatically.

It shows:
- Requested map
- Current fallback source
- Searching / Downloading / Extracting stage
- Percentage when Content-Length is available
- Downloaded MB / total MB
- Download speed
- Estimated time remaining

The popup disappears automatically when the map is ready.

This is specifically intended for users whose normal HaloNet locator is
broken/region-affected, because Halo otherwise remains at "Connecting to map
server..." while the fallback archive is downloaded and extracted.

CHIMERA SETTING
---------------
Under [memory]:

download_template=http://127.0.0.1:8765/{map}

SOURCE ORDER
------------
1. HaloNet normal locator (native Halo progress, no custom popup)
2. HaloNet static ZIP        (custom fallback popup)
3. CE3                       (custom fallback popup)
4. HaloMaps.org              (custom fallback popup)

ANTI-HANG LIMITS
----------------
Network stall: 15 seconds
Individual map/archive transfer: 5 minutes
Absolute request watchdog: 6 minutes

BUILD ICON
----------
If a file named:

    haloce.ico

is beside Build Windows EXE.bat, the build script automatically uses it as
the ChimeraMapDownloader.exe icon.

RUNTIME DATA
------------
%LOCALAPPDATA%\ChimeraHybridMapDownloader
