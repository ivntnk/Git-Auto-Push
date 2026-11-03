@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist logs mkdir logs

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set LOG=%~dp0logs\build_%TS%.log

echo Compilation en cours, patiente...
call :main > "%LOG%" 2>&1
set RC=%errorlevel%

type "%LOG%"
echo.
echo ==========================================
echo   Log enregistre dans : %LOG%
echo ==========================================
pause
exit /b %RC%

:main
echo ===== GIT AUTOPUSH - LOG DE COMPILATION =====
echo Date : %date% %time%
echo Dossier : %~dp0
echo.
echo ----- SYSTEME -----
ver
echo PROCESSOR_ARCHITECTURE = %PROCESSOR_ARCHITECTURE%
echo PROCESSOR_ARCHITEW6432 = %PROCESSOR_ARCHITEW6432%
powershell -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture | Format-List | Out-String)"
echo.

echo ----- PYTHON DISPONIBLES -----
where python
py -0p
echo.

set PY=
py -3.12 --version >nul 2>nul && set PY=py -3.12
if "%PY%"=="" py -3.13 --version >nul 2>nul && set PY=py -3.13
if "%PY%"=="" set PY=python

echo ----- PYTHON UTILISE : %PY% -----
%PY% --version
%PY% -c "import platform,struct,sys;print('Machine:',platform.machine(),'|',struct.calcsize('P')*8,'bits');print('Executable:',sys.executable)"
%PY% -c "import tkinter;print('tkinter OK, version',tkinter.TkVersion)"
echo.

echo ----- GIT -----
git --version
echo.

echo ----- INSTALLATION PYINSTALLER -----
%PY% -m pip install --upgrade pyinstaller
echo Code retour pip : %errorlevel%
%PY% -m PyInstaller --version
echo.

echo ----- COMPILATION -----
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
%PY% -m PyInstaller --onefile --noconsole --clean --log-level INFO --name GitAutoPush "%~dp0git_autopush_gui.py"
echo Code retour PyInstaller : %errorlevel%
echo.

echo ----- VERIFICATION DU .EXE -----
if not exist dist\GitAutoPush.exe (
    echo [ERREUR] dist\GitAutoPush.exe n'existe pas : la compilation a echoue.
    goto :warnings
)
%PY% -c "import struct,os;p=r'dist\GitAutoPush.exe';f=open(p,'rb');d=f.read(4096);print('Taille (octets):',os.path.getsize(p));print('En-tete MZ (vrai exe Windows):',d[:2]==b'MZ');o=struct.unpack('<I',d[0x3c:0x40])[0];m=struct.unpack('<H',d[o+4:o+6])[0];print('Architecture du exe:',hex(m),{0x14c:'x86 (32 bits)',0x8664:'x64 (64 bits)',0xaa64:'ARM64'}.get(m,'inconnue'))"
echo.

:warnings
echo ----- AVERTISSEMENTS PYINSTALLER -----
if exist build\GitAutoPush\warn-GitAutoPush.txt (
    type build\GitAutoPush\warn-GitAutoPush.txt
) else (
    echo (aucun fichier d'avertissements)
)
echo.
echo ===== FIN DU LOG =====
exit /b 0
