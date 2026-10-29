#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Atualizador Rápido via SSH (Preserva Banco, Senhas e .env)
# ==============================================================================
set -euo pipefail

APP_ROOT="/opt/pstviewer"
APP_USER="pstviewer"
REPO_URL="${1:-https://github.com/frederigi/pstviewer.git}"

echo "=================================================================="
echo " PST VIEWER - ATUALIZANDO CÓDIGO EM ${APP_ROOT}"
echo "=================================================================="

if [ ! -d "${APP_ROOT}" ]; then
    echo "[ERRO] Diretório ${APP_ROOT} não encontrado. Use ./install.sh para instalar do zero."
    exit 1
fi

cd "${APP_ROOT}"

if [ ! -d "${APP_ROOT}/.git" ]; then
    echo "[1/3] Vinculando instalação existente ao repositório Git (${REPO_URL})..."
    git init
    git branch -M main
    git remote add origin "${REPO_URL}"
fi

echo "[2/3] Baixando última versão do código (preservando config/pstviewer.env e venv)..."
git fetch origin main
git reset --hard origin/main

chown -R root:"${APP_USER}" "${APP_ROOT}/app" "${APP_ROOT}/database" "${APP_ROOT}/scripts" "${APP_ROOT}/requirements.txt"
chmod +x "${APP_ROOT}/install.sh" "${APP_ROOT}/update.sh" 2>/dev/null || true

echo "[3/3] Reiniciando serviços pstviewer-web e pstviewer-worker..."
systemctl restart pstviewer-web.service pstviewer-worker.service

echo "=================================================================="
echo " [OK] ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!"
echo "  • pstviewer-web.service    : $(systemctl is-active pstviewer-web.service)"
echo "  • pstviewer-worker.service : $(systemctl is-active pstviewer-worker.service)"
echo "=================================================================="
