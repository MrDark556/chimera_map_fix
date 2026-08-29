DEVELOPER BUILD PACKAGE - v3.5
================================

Build on Windows:
    Build Windows EXE.bat

Output:
    RELEASE\ChimeraMapDownloader.exe

NEW:
The launcher now has a small fallback-only progress window.

The proxy emits UI events only AFTER the normal HaloNet locator fails.
Therefore users whose normal Chimera/Halo map downloading works continue to
use Halo's native progress display without seeing a redundant popup.

Optional:
Place haloce.ico beside the build BAT before compiling to embed the Halo CE
icon automatically.
