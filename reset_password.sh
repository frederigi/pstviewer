#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Redefinição Rápida de Senha do Administrador (admin)
# Desbloqueia a conta e define uma nova senha imediatamente no MySQL/MariaDB.
# ==============================================================================
set -euo pipefail

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="/opt/pstviewer"

# Detecta o Python do ambiente virtual
if [ -f "${APP_ROOT}/venv/bin/python" ]; then
    PY_BIN="${APP_ROOT}/venv/bin/python"
elif [ -f "${CURRENT_DIR}/venv/bin/python" ]; then
    PY_BIN="${CURRENT_DIR}/venv/bin/python"
else
    PY_BIN="python3"
fi

# Detecta o script create_admin.py
SCRIPT_PATH="${APP_ROOT}/scripts/create_admin.py"
if [ ! -f "${SCRIPT_PATH}" ]; then
    SCRIPT_PATH="${CURRENT_DIR}/scripts/create_admin.py"
fi

echo "=================================================================="
echo " PST VIEWER - REDEFINIÇÃO DE SENHA DO ADMINISTRADOR (admin)"
echo "=================================================================="

NEW_PW="${1:-}"

if [ -z "${NEW_PW}" ]; then
    echo -n "Digite a nova senha para o usuário 'admin' (mínimo 8 caracteres): "
    read -r NEW_PW
fi

if [ -z "${NEW_PW}" ]; then
    echo "[ERRO] A senha não pode ser vazia."
    exit 1
fi

if [ ${#NEW_PW} -lt 8 ]; then
    echo "[AVISO] Senha possui menos de 8 caracteres. Recomendado pelo menos 8."
fi

echo "Atualizando credenciais no banco de dados..."
"${PY_BIN}" "${SCRIPT_PATH}" --username admin --password "${NEW_PW}"

echo "=================================================================="
echo " [OK] SUCESSO!"
echo " A senha do usuário 'admin' foi redefinida para: ${NEW_PW}"
echo " Tentativas de bloqueio foram zeradas. Você já pode fazer login."
echo "=================================================================="
