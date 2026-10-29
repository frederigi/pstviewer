#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Atualizador Rápido via SSH (Preserva Banco, Senhas e .env)
# Funciona automaticamente tanto para quem clonou do GitHub quanto do Gitea!
# ==============================================================================
set -euo pipefail

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="/opt/pstviewer"
APP_USER="pstviewer"
DEFAULT_GITHUB_URL="https://github.com/frederigi/pstviewer.git"

cd "${CURRENT_DIR}"

if [ ! -d "${CURRENT_DIR}/.git" ]; then
    git init
    git branch -M main
fi

# Se o usuário passou uma URL por parâmetro, usa ela;
# caso contrário, preserva o remote 'origin' original de onde foi clonado (GitHub ou Gitea)
if [ -n "${1:-}" ]; then
    REPO_URL="$1"
    git remote remove origin 2>/dev/null || true
    git remote add origin "${REPO_URL}"
elif git remote get-url origin >/dev/null 2>&1; then
    REPO_URL="$(git remote get-url origin)"
else
    REPO_URL="${DEFAULT_GITHUB_URL}"
    git remote add origin "${REPO_URL}"
fi

echo "=================================================================="
echo " PST VIEWER - ATUALIZANDO CÓDIGO A PARTIR DE:"
echo " ${REPO_URL}"
echo "=================================================================="

echo "[1/3] Baixando última versão do repositório em ${CURRENT_DIR}..."
git fetch origin main
git reset --hard origin/main

if [ -d "${APP_ROOT}" ] && [ "${CURRENT_DIR}" != "${APP_ROOT}" ]; then
    echo "[2/3] Sincronizando arquivos atualizados para ${APP_ROOT}..."
    cp -r "${CURRENT_DIR}/app/"* "${APP_ROOT}/app/"
    cp -r "${CURRENT_DIR}/database/"* "${APP_ROOT}/database/"
    cp -r "${CURRENT_DIR}/scripts/"* "${APP_ROOT}/scripts/"
    cp "${CURRENT_DIR}/requirements.txt" "${APP_ROOT}/requirements.txt"
    cp "${CURRENT_DIR}/update.sh" "${APP_ROOT}/update.sh" 2>/dev/null || true
    chown -R root:"${APP_USER}" "${APP_ROOT}/app" "${APP_ROOT}/database" "${APP_ROOT}/scripts" "${APP_ROOT}/requirements.txt"
fi

chmod +x "${CURRENT_DIR}/update.sh" "${CURRENT_DIR}/install.sh" 2>/dev/null || true

echo "[3/3] Reiniciando serviços pstviewer-web e pstviewer-worker..."
systemctl restart pstviewer-web.service pstviewer-worker.service

echo "=================================================================="
echo " [OK] ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!"
echo "  • pstviewer-web.service    : $(systemctl is-active pstviewer-web.service)"
echo "  • pstviewer-worker.service : $(systemctl is-active pstviewer-worker.service)"
echo "=================================================================="
