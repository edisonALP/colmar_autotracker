@echo off
chcp 65001 >nul
setlocal

set "GUI_DIR=%~dp0"
set "DIST=%GUI_DIR%dist\AutoTracker"

echo [1/3] PyInstaller bauen...
cd /d "%GUI_DIR%"
pip install -r requirements.txt --quiet
pyinstaller autotracker.spec --clean --noconfirm
if errorlevel 1 ( echo [FEHLER] PyInstaller fehlgeschlagen & pause & exit /b 1 )

echo [2/3] Videos-Ordner anlegen...
mkdir "%DIST%\videos" >nul 2>&1

echo [3/3] ZIP erstellen...
powershell -Command "Compress-Archive -Path '%DIST%' -DestinationPath '%GUI_DIR%dist\AutoTracker.zip' -Force"
if errorlevel 1 ( echo [FEHLER] ZIP fehlgeschlagen & pause & exit /b 1 )

echo.
echo ============================================================
echo  Build fertig!
echo  Schick dem Kollegen: dist\AutoTracker.zip
echo  Inhalt entpacken, AutoTracker.exe starten.
echo ============================================================
pause
