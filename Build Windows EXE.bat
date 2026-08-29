@echo off
setlocal
title Build Chimera Map Downloader EXE
cd /d "%~dp0"

echo ============================================================
echo  Chimera Hybrid Map Downloader v3.6 - Windows EXE Builder
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3 was not found.
    pause
    exit /b 1
)

if not exist "ChimeraMapDownloader.pyw" (
    echo ERROR: ChimeraMapDownloader.pyw was not found.
    pause
    exit /b 2
)

if not exist "chimera_hybrid_downloader.py" (
    echo ERROR: chimera_hybrid_downloader.py was not found.
    pause
    exit /b 2
)

if not exist "halonet_map_index.json" (
    echo ERROR: halonet_map_index.json was not found.
    echo.
    echo Run:
    echo     py -3 "Update HaloNet Cache.py"
    echo.
    echo If HaloNet is blocked in your region, run the
    echo "Update HaloNet map index" GitHub Action instead.
    pause
    exit /b 2
)

REM Refuse to make a public build with only the tiny seed cache.
py -3 -c "import json,sys; d=json.load(open('halonet_map_index.json',encoding='utf-8')); sys.exit(0 if d.get('complete') and int(d.get('map_count',0)) >= 5000 else 1)"
if errorlevel 1 (
    echo ERROR: HaloNet map index is incomplete.
    echo.
    echo The included seed cache is only for development/testing.
    echo Generate the full cache first:
    echo.
    echo   Option A - unblocked PC:
    echo     py -3 "Update HaloNet Cache.py"
    echo.
    echo   Option B - region blocked:
    echo     GitHub ^> Actions ^> Update HaloNet map index ^> Run workflow
    echo.
    echo Then pull the committed halonet_map_index.json and build again.
    pause
    exit /b 2
)

echo [1/3] Installing/updating PyInstaller...
py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: PyInstaller installation failed.
    pause
    exit /b 3
)

echo.
echo [2/3] Building one-file, no-console EXE...

set "ICON_ARG="
if exist "%CD%\haloce.ico" (
    echo Halo CE icon found: haloce.ico
    set "ICON_ARG=--icon=%CD%\haloce.ico"
) else (
    echo No haloce.ico found - using default EXE icon.
)

if exist ".pyinstaller" rmdir /s /q ".pyinstaller"

py -3 -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --noupx ^
    --name haloce_chimera_mpdlr ^
    --workpath "%CD%\.pyinstaller\work" ^
    --distpath "%CD%\.pyinstaller\dist" ^
    --specpath "%CD%\.pyinstaller" ^
    --add-data "%CD%\halonet_map_index.json;." ^
    %ICON_ARG% ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.filedialog ^
    --hidden-import tkinter.messagebox ^
    ChimeraMapDownloader.pyw

if errorlevel 1 (
    echo ERROR: EXE build failed.
    pause
    exit /b 4
)

echo.
echo [3/3] Creating RELEASE folder...
if not exist "RELEASE" mkdir "RELEASE"

copy /y ^
    ".pyinstaller\dist\haloce_chimera_mpdlr.exe" ^
    "RELEASE\haloce_chimera_mpdlr.exe" >nul

echo.
echo ============================================================
echo BUILD COMPLETE
echo ============================================================
echo.
echo Public EXE:
echo     RELEASE\haloce_chimera_mpdlr.exe
echo.
echo The HaloNet filename index is embedded inside the EXE.
echo End users do NOT need halonet_map_index.json separately.
echo.
pause
