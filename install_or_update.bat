@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv 2>nul || py -3.11 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 goto :error
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error
python app.py
exit /b 0

:error
echo.
echo No fue posible instalar CivilLab Suite. Verifica Python y la conexion a Internet.
pause
exit /b 1
