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
PULL_SUCCESS=0

if git fetch origin main 2>/dev/null; then
    PULL_SUCCESS=1
else
    # Se falhou e houver Gitea acessível, tenta fallback automático para o Gitea interno
    GITEA_FALLBACK="http://10.14.127.225:3000/anderson/pstviewer.git"
    echo "  [AVISO] Falha ao baixar de 'origin'. Tentando fallback automático via Gitea local..."
    if git fetch "${GITEA_FALLBACK}" main 2>/dev/null; then
        echo "  [OK] Baixado com sucesso a partir do Gitea (${GITEA_FALLBACK})!"
        git remote set-url origin "${GITEA_FALLBACK}"
        PULL_SUCCESS=1
    fi
fi

if [ "${PULL_SUCCESS}" -ne 1 ]; then
    echo "------------------------------------------------------------------"
    echo " [AVISO] Falha ao baixar atualizações do repositório remoto."
    echo " Possíveis causas e como resolver:"
    echo " 1. Se o repositório GitHub for privado, mude para Público em:"
    echo "    GitHub -> Settings -> Danger Zone -> Change visibility -> Make public"
    echo " 2. Ou atualize diretamente do seu Gitea interno (sem exigir senha):"
    echo "    ./update.sh http://10.14.127.225:3000/anderson/pstviewer.git"
    echo " 3. Ou configure um Token de Acesso Pessoal (PAT) do GitHub:"
    echo "    git remote set-url origin https://<SEU_TOKEN>@github.com/frederigi/pstviewer.git"
    echo "------------------------------------------------------------------"
    exit 1
fi
git reset --hard FETCH_HEAD

if [ -d "${APP_ROOT}" ] && [ "${CURRENT_DIR}" != "${APP_ROOT}" ]; then
    echo "[2/3] Sincronizando arquivos atualizados para ${APP_ROOT}..."
    cp -r "${CURRENT_DIR}/app/"* "${APP_ROOT}/app/"
    cp -r "${CURRENT_DIR}/database/"* "${APP_ROOT}/database/"
    cp -r "${CURRENT_DIR}/scripts/"* "${APP_ROOT}/scripts/"
    cp "${CURRENT_DIR}/requirements.txt" "${APP_ROOT}/requirements.txt"
    cp "${CURRENT_DIR}/update.sh" "${APP_ROOT}/update.sh" 2>/dev/null || true
    cp "${CURRENT_DIR}/reset_password.sh" "${APP_ROOT}/reset_password.sh" 2>/dev/null || true
    chown -R root:"${APP_USER}" "${APP_ROOT}/app" "${APP_ROOT}/database" "${APP_ROOT}/scripts" "${APP_ROOT}/requirements.txt" "${APP_ROOT}/reset_password.sh" 2>/dev/null || true
fi

chmod +x "${CURRENT_DIR}/update.sh" "${CURRENT_DIR}/install.sh" "${CURRENT_DIR}/reset_password.sh" "${APP_ROOT}/reset_password.sh" 2>/dev/null || true

echo "[3/3] Reiniciando serviços pstviewer-web e pstviewer-worker..."
systemctl restart pstviewer-web.service pstviewer-worker.service

echo "=================================================================="
echo " [OK] ATUALIZAÇÃO CONCLUÍDA COM SUCESSO!"
echo "  • pstviewer-web.service    : $(systemctl is-active pstviewer-web.service)"
echo "  • pstviewer-worker.service : $(systemctl is-active pstviewer-worker.service)"
echo "=================================================================="
