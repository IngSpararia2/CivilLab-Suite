@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Primero ejecuta run_windows.bat para crear el entorno.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if not exist "deployment" mkdir "deployment"
copy /y "tools\pysidedeploy.spec.template" "deployment\pysidedeploy.spec" >nul
pyside6-deploy -c "deployment\pysidedeploy.spec" --name "CivilLab Suite" app.py
if errorlevel 1 (
    echo.
    echo No fue posible compilar CivilLab Suite.
    pause
    exit /b 1
)

echo.
echo Compilacion finalizada. Revisa el ejecutable en dist.
pause
