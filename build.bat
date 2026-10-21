@echo off
REM Genera el ejecutable portable dist\Hasher Informes.exe
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
)
.venv\Scripts\python scripts\build.py %*
echo.
echo Ejecutable generado en: %~dp0dist\Hasher Informes.exe
