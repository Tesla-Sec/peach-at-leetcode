@echo off
:: ====================================
:: run_main.bat — executa main.py 100% oculto como admin
:: ====================================

:: 1) Se não for admin, relança este .bat como administrador (janela oculta)
net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -WindowStyle Hidden ^
      -Command "Start-Process -FilePath '%~f0' -Verb runAs"
    exit /b
)

:: 2) Vai para a pasta onde o .bat está
cd /d "%~dp0"

:: 3) Executa o main.py com pythonw (sem console) em janela oculta
powershell -NoProfile -WindowStyle Hidden ^
  -Command "Start-Process -FilePath 'pythonw' -ArgumentList 'main.py' -WorkingDirectory '%cd%'"

:: 4) Fecha imediatamente
exit
