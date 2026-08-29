@echo off
setlocal
title Build Chimera Map Downloader EXE
cd /d "%~dp0"

echo ============================================================
echo  Chimera Hybrid Map Downloader v3.5 - Windows EXE Builder
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python 3 was not found.
    pause
    exit /b 1
)

echo [1/3] Installing/updating PyInstaller...
py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo ERROR: PyInstaller installation failed.
    pause
    exit /b 2
)

echo.
echo [2/3] Building one-file, no-console EXE...

set ICON_ARG=
if exist "%CD%\haloce.ico" (
    echo Halo CE icon found: haloce.ico
    set ICON_ARG=--icon="%CD%\haloce.ico"
) else (
    echo No haloce.ico found - using default EXE icon.
)

py -3 -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --noupx ^
    --name ChimeraMapDownloader ^
    %ICON_ARG% ^
    --hidden-import tkinter ^
    --hidden-import tkinter.ttk ^
    --hidden-import tkinter.filedialog ^
    --hidden-import tkinter.messagebox ^
    ChimeraMapDownloader.pyw

if errorlevel 1 (
    echo ERROR: EXE build failed.
    pause
    exit /b 3
)

echo.
echo [3/3] Creating RELEASE folder...
if not exist "RELEASE" mkdir "RELEASE"
copy /y "dist\ChimeraMapDownloader.exe" "RELEASE\ChimeraMapDownloader.exe" >nul
copy /y "PUBLIC_README.txt" "RELEASE\README.txt" >nul

echo.
echo ============================================================
echo BUILD COMPLETE
echo ============================================================
echo.
echo Public EXE:
echo     RELEASE\ChimeraMapDownloader.exe
echo.
pause
