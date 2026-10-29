#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Atualizador Rápido via SSH (Preserva Banco, Senhas e .env)
# Atualiza tanto a pasta atual (ex: /var/www/mail) quanto /opt/pstviewer.
# ==============================================================================
set -euo pipefail

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="/opt/pstviewer"
APP_USER="pstviewer"
REPO_URL="${1:-http://10.14.127.225:3000/anderson/pstviewer.git}"

echo "=================================================================="
echo " PST VIEWER - ATUALIZANDO CÓDIGO A PARTIR DE ${REPO_URL}"
echo "=================================================================="

cd "${CURRENT_DIR}"

if [ ! -d "${CURRENT_DIR}/.git" ]; then
    git init
    git branch -M main
fi

git remote remove origin 2>/dev/null || true
git remote add origin "${REPO_URL}"

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
