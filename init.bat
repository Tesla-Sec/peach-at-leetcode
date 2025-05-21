@echo off
:: ================================
:: run_main.bat — executa main.py como administrador
:: ================================

:: 1) Verifica se já está em modo admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Solicitando privilégios de administrador...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb runAs"
    exit /b
)

:: 2) Vai para a pasta onde o .bat está localizado
cd /d "%~dp0"

:: 3) Executa o main.py
python main.py

:: (Opcional) Segura a janela para você ver a saída
pause
