@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title PST Viewer - Parar Servicos em Segundo Plano

if exist "venv\Scripts\python.exe" (
    call venv\Scripts\python.exe setup_and_run.py --stop
) else (
    python setup_and_run.py --stop
)
pause

