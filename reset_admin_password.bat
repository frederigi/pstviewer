@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title PST Viewer - Redefinir Senha do Administrador (admin)

echo ============================================================================
echo    PST VIEWER - REDEFINICAO DE SENHA DO ADMINISTRADOR (admin)
echo ============================================================================
echo.

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\python.exe setup_and_run.py --setup-only --reset-admin
) else (
    python setup_and_run.py --setup-only --reset-admin
)
echo.
pause
