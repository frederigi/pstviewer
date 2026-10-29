@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title PST Viewer - Instalador e Inicializador Automatico (Windows / XAMPP)

echo ==========================================================================
echo    PST VIEWER - INSTALADOR AUTOMATICO PARA WINDOWS (COM MYSQL / XAMPP)
echo ==========================================================================
echo.

:: 1. Verifica se o Python esta instalado
echo [1/4] Verificando instalacao do Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [AVISO] Python 3.10+ nao foi encontrado no seu Windows!
    echo Deseja instalar o Python 3.12 automaticamente via Winget agora?
    set /p INSTALL_PY="Digite S para instalar ou N para sair [S/n]: "
    if /i "!INSTALL_PY!"=="N" (
        echo Instale o Python em https://www.python.org/downloads/ marcando "Add Python to PATH".
        pause
        exit /b 1
    )
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo [OK] Python instalado! Feche e abra novamente este arquivo .bat para atualizar o PATH.
    pause
    exit /b 0
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
echo   - Encontrado: !PY_VER! [OK]

:: 2. Verifica se a porta 3306 (MySQL do XAMPP ou MySQL Server) esta ativa
echo.
echo [2/4] Verificando servico MySQL / MariaDB na porta 3306 (XAMPP)...
netstat -an | findstr ":3306 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    if exist "C:\xampp\mysql_start.bat" (
        echo   - MySQL do XAMPP parado. Iniciando automaticamente C:\xampp\mysql_start.bat...
        start "" /min "C:\xampp\mysql_start.bat"
        timeout /t 4 /nobreak >nul
    ) else (
        echo.
        echo   [ATENCAO] Nenhum banco MySQL/MariaDB detectado rodando na porta 3306!
        echo   Por favor, abra o XAMPP Control Panel e clique em "Start" ao lado de "MySQL"
        echo   ^(ou inicie seu servico MySQL Server^) antes de prosseguir.
        echo.
        pause
    )
) else (
    echo   - Banco MySQL/MariaDB ativo na porta 3306 [OK]
)

:: 3. Cria ambiente virtual Python isolado (venv) se nao existir
echo.
echo [3/4] Preparando ambiente virtual Python (venv) e dependencias...
if not exist "venv\Scripts\python.exe" (
    echo   - Criando pasta venv...
    python -m venv venv
)
call venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1
call venv\Scripts\python.exe -m pip install -r requirements.txt

:: 4. Executa o assistente que cria o banco no XAMPP, gera o admin e inicia os servicos
echo.
echo [4/4] Configurando banco de dados, usuario Admin e iniciando o PST Viewer...
call venv\Scripts\python.exe setup_and_run.py %*

pause
