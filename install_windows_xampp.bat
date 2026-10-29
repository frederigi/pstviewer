@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "IS_EN=0"
for %%A in (%*) do (
    if /i "%%A"=="en" set "IS_EN=1"
    if /i "%%A"=="--lang=en" set "IS_EN=1"
)

if "!IS_EN!"=="1" (
    title PST Viewer - Smart Installer (Windows / XAMPP / MySQL)
    echo ============================================================================
    echo    PST VIEWER - SMART INSTALLATION ASSISTANT (WINDOWS / XAMPP)
    echo ============================================================================
) else (
    title PST Viewer - Instalador Inteligente (Windows / XAMPP / MySQL)
    echo ============================================================================
    echo    PST VIEWER - ASSISTENTE INTELIGENTE DE INSTALACAO (WINDOWS / XAMPP)
    echo ============================================================================
)
echo.

:: 1. Detecta a melhor versao do Python disponivel na maquina (3.10 a 3.14+)
if "!IS_EN!"=="1" (
    echo [1/3] Detecting installed Python versions on Windows...
) else (
    echo [1/3] Analisando versoes do Python instaladas na maquina...
)
set "PY_CMD="

where py >nul 2>&1
if %errorlevel% equ 0 (
    for %%V in (3.12 3.13 3.11 3.14 3.10) do (
        if "!PY_CMD!"=="" (
            py -%%V --version >nul 2>&1
            if !errorlevel! equ 0 (
                set "PY_CMD=py -%%V"
            )
        )
    )
)

if "!PY_CMD!"=="" (
    python --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=python"
    )
)

if "!PY_CMD!"=="" (
    echo.
    if "!IS_EN!"=="1" (
        echo [NOTICE] Python 3.10+ was not found on your Windows system!
        echo Would you like the installer to download and install Python 3.12 LTS automatically?
        set /p INSTALL_PY="Type Y to install or N to exit [Y/n]: "
        if /i "!INSTALL_PY!"=="N" (
            echo Please install Python from https://www.python.org/downloads/ checking "Add Python to PATH".
            pause
            exit /b 1
        )
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        echo.
        echo [OK] Python 3.12 installed successfully! Run this .bat file again to continue.
        pause
        exit /b 0
    ) else (
        echo [AVISO] Nenhuma versao do Python 3.10+ foi encontrada no seu Windows!
        echo Deseja que o instalador baixe e instale o Python 3.12 LTS automaticamente?
        set /p INSTALL_PY="Digite S para instalar ou N para sair [S/n]: "
        if /i "!INSTALL_PY!"=="N" (
            echo Instale o Python em https://www.python.org/downloads/ marcando "Add Python to PATH".
            pause
            exit /b 1
        )
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        echo.
        echo [OK] Python 3.12 instalado com sucesso! Abra novamente este arquivo .bat para continuar.
        pause
        exit /b 0
    )
)

for /f "tokens=*" %%i in ('!PY_CMD! --version 2^>^&1') do set PY_VER=%%i
if "!IS_EN!"=="1" (
    echo   - Automatically selected: !PY_VER! ^(!PY_CMD!^) [OK]
) else (
    echo   - Selecionado automaticamente: !PY_VER! ^(!PY_CMD!^) [OK]
)

:: 2. Verifica se o MySQL/MariaDB (porta 3306, 3307 ou 3308) esta rodando
echo.
if "!IS_EN!"=="1" (
    echo [2/3] Checking MySQL / MariaDB database service (XAMPP)...
) else (
    echo [2/3] Verificando servico de Banco de Dados MySQL / MariaDB (XAMPP)...
)
netstat -an | findstr /R ":3306 :3307 :3308 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    if exist "C:\xampp\mysql_start.bat" (
        if "!IS_EN!"=="1" (
            echo   - XAMPP MySQL was stopped. Starting C:\xampp\mysql_start.bat automatically...
        ) else (
            echo   - MySQL do XAMPP estava parado. Iniciando C:\xampp\mysql_start.bat automaticamente...
        )
        start "" /min "C:\xampp\mysql_start.bat"
        timeout /t 4 /nobreak >nul
    ) else (
        echo.
        if "!IS_EN!"=="1" (
            echo   [NOTICE] No active MySQL/MariaDB detected on ports 3306/3307/3308.
            echo   If using XAMPP, open XAMPP Control Panel and click "Start" on MySQL.
            echo   ^(The setup wizard will ask for connection credentials if on another port/host^).
        ) else (
            echo   [AVISO] Nenhum MySQL/MariaDB detectado ativo nas portas 3306/3307/3308.
            echo   Se voce usa o XAMPP, abra o XAMPP Control Panel e clique em "Start" no MySQL.
            echo   ^(O assistente pedira os dados de conexao caso esteja em outra porta/servidor^).
        )
    )
) else (
    if "!IS_EN!"=="1" (
        echo   - MySQL / MariaDB database service detected running [OK]
    ) else (
        echo   - Servico MySQL / MariaDB detectado em execucao [OK]
    )
)

:: 3. Prepara o ambiente virtual (venv) e delega o diagnostico/instalacao de pacotes ao setup_and_run.py
echo.
if "!IS_EN!"=="1" (
    echo [3/3] Preparing isolated virtual environment (venv) and launching setup...
) else (
    echo [3/3] Preparando ambiente virtual isolado (venv) e iniciando assistente...
)
if not exist "venv\Scripts\python.exe" (
    if "!IS_EN!"=="1" (
        echo   - Creating virtual environment venv with !PY_VER!...
    ) else (
        echo   - Criando ambiente virtual venv com !PY_VER!...
    )
    !PY_CMD! -m venv venv
)

call venv\Scripts\python.exe setup_and_run.py %*

pause
