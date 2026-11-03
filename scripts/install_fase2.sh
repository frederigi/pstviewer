#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Fase 2: Instalação Idempotente de Banco (MariaDB/MySQL),
# Diretórios Protegidos, Ambiente Virtual Python e Guardião de Limpeza.
# Compatível com execução direta como root no Debian 12 (sem depender de sudo).
# ==============================================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "[ERRO] Execute este script como root." >&2
    exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ROOT="/opt/pstviewer"
CONF_DIR="${APP_ROOT}/config"
ENV_FILE="${CONF_DIR}/pstviewer.env"
SESSIONS_DIR="/srv/pstviewer/sessions"
QUARANTINE_DIR="/srv/pstviewer/quarantine"
JOBS_DIR="/var/lib/pstviewer/jobs"
LOG_DIR="/var/log/pstviewer"
APP_USER="pstviewer"
DB_NAME="pstviewer"
DB_USER="pstviewer_app"

echo "=================================================================="
echo " PST VIEWER - INSTALAÇÃO FASE 2 (BANCO, SESSÕES E LIMPEZA)"
echo " Origem: ${SRC_DIR}"
echo "=================================================================="

echo "[1/8] Verificando pacotes de sistema necessários (python3-venv)..."
if ! dpkg -s python3-venv >/dev/null 2>&1; then
    apt-get update && apt-get install -y python3-venv
fi

echo "[2/8] Criando usuário dedicado sem privilégios (${APP_USER})..."
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir "${APP_ROOT}" --shell /usr/sbin/nologin "${APP_USER}"
    echo "  -> Usuário ${APP_USER} criado."
else
    echo "  -> Usuário ${APP_USER} já existe."
fi

echo "[3/8] Criando estrutura de diretórios isolados e permissões..."
mkdir -p "${APP_ROOT}/app" "${CONF_DIR}" "${APP_ROOT}/database" "${APP_ROOT}/scripts"
mkdir -p "${SESSIONS_DIR}" "${QUARANTINE_DIR}"
mkdir -p "${JOBS_DIR}"
mkdir -p "${LOG_DIR}/application" "${LOG_DIR}/audit"

chown -R root:"${APP_USER}" "${APP_ROOT}"
chmod 0750 "${APP_ROOT}" "${CONF_DIR}"

chown -R "${APP_USER}:${APP_USER}" "/srv/pstviewer" "${JOBS_DIR}" "${LOG_DIR}"
chmod 0700 "/srv/pstviewer" "${SESSIONS_DIR}" "${QUARANTINE_DIR}" "${JOBS_DIR}"
chmod 0750 "${LOG_DIR}" "${LOG_DIR}/application" "${LOG_DIR}/audit"

echo "[4/8] Configurando banco de dados MariaDB/MySQL (${DB_NAME}) e credenciais..."
systemctl start mariadb || systemctl start mysql || true

if [ -f "${ENV_FILE}" ]; then
    echo "  -> Arquivo ${ENV_FILE} já existe; preservando credenciais atuais."
    DB_PASS=$(awk -F= '/^PSTVIEWER_DB_PASSWORD=/{print $2}' "${ENV_FILE}" | tr -d '"' | tr -d "'")
else
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat <<EOF > "${ENV_FILE}"
PSTVIEWER_ENV=production
PSTVIEWER_APP_NAME="PST Viewer"
PSTVIEWER_BIND_HOST=127.0.0.1
PSTVIEWER_BIND_PORT=8000
PSTVIEWER_DB_HOST=127.0.0.1
PSTVIEWER_DB_PORT=3306
PSTVIEWER_DB_NAME=${DB_NAME}
PSTVIEWER_DB_USER=${DB_USER}
PSTVIEWER_DB_PASSWORD=${DB_PASS}
PSTVIEWER_SESSIONS_DIR=${SESSIONS_DIR}
PSTVIEWER_QUARANTINE_DIR=${QUARANTINE_DIR}
PSTVIEWER_JOBS_DIR=${JOBS_DIR}
PSTVIEWER_LOG_DIR=${LOG_DIR}
PSTVIEWER_SECRET_KEY=${SECRET_KEY}
PSTVIEWER_COOKIE_SECURE=false
PSTVIEWER_AUTH_SESSION_HOURS=8
PSTVIEWER_MAX_LOGIN_ATTEMPTS=5
PSTVIEWER_LOGIN_LOCKOUT_MINUTES=15
EOF
    chown root:"${APP_USER}" "${ENV_FILE}"
    chmod 0640 "${ENV_FILE}"
    echo "  -> Arquivo ${ENV_FILE} gerado com permissões 0640."
fi

mariadb -u root <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
ALTER USER '${DB_USER}'@'127.0.0.1' IDENTIFIED BY '${DB_PASS}';
ALTER USER '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP ON \`${DB_NAME}\`.* TO '${DB_USER}'@'127.0.0.1';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES, DROP ON \`${DB_NAME}\`.* TO '${DB_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "  -> Banco '${DB_NAME}' e usuário '${DB_USER}' configurados no MariaDB."

echo "[5/8] Sincronizando arquivos da aplicação para ${APP_ROOT}..."
if [ "${SRC_DIR}" != "${APP_ROOT}" ]; then
    cp -r "${SRC_DIR}/app/"* "${APP_ROOT}/app/"
    cp -r "${SRC_DIR}/database/"* "${APP_ROOT}/database/"
    cp -r "${SRC_DIR}/scripts/"* "${APP_ROOT}/scripts/"
    cp "${SRC_DIR}/requirements.txt" "${APP_ROOT}/requirements.txt"
    chown -R root:"${APP_USER}" "${APP_ROOT}/app" "${APP_ROOT}/database" "${APP_ROOT}/scripts" "${APP_ROOT}/requirements.txt"
fi

echo "[6/8] Criando virtualenv Python (com acesso ao python3-pypff do sistema)..."
if [ ! -d "${APP_ROOT}/venv" ]; then
    python3 -m venv --system-site-packages "${APP_ROOT}/venv"
fi
"${APP_ROOT}/venv/bin/pip" install --upgrade pip >/dev/null
"${APP_ROOT}/venv/bin/pip" install -r "${APP_ROOT}/requirements.txt"

echo "[7/8] Executando migrações versionadas no MySQL/MariaDB..."
PYTHONPATH="${APP_ROOT}" PSTVIEWER_ENV_FILE="${ENV_FILE}" \
    "${APP_ROOT}/venv/bin/python" -m app.database.migrations

echo "[8/8] Configurando serviço systemd do Guardião de Limpeza (pstviewer-cleaner)..."
cat <<EOF > /etc/systemd/system/pstviewer-cleaner.service
[Unit]
Description=PST Viewer - Guardiao de Limpeza de Sessoes Temporarias
After=network.target mariadb.service

[Service]
Type=oneshot
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_ROOT}
Environment="PYTHONPATH=${APP_ROOT}"
Environment="PSTVIEWER_ENV_FILE=${ENV_FILE}"
ExecStart=${APP_ROOT}/venv/bin/python -m app.workers.cleaner_daemon --once
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/srv/pstviewer /var/lib/pstviewer /var/log/pstviewer
EOF

cat <<EOF > /etc/systemd/system/pstviewer-cleaner.timer
[Unit]
Description=PST Viewer - Execucao periodica do Guardiao de Limpeza (a cada 60s)

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
AccuracySec=5s
Unit=pstviewer-cleaner.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now pstviewer-cleaner.timer

echo "=================================================================="
echo " [OK] FASE 2 INSTALADA COM SUCESSO!"
echo " Para rodar a bateria de testes da Fase 2:"
echo "   PYTHONPATH=${APP_ROOT} ${APP_ROOT}/venv/bin/python ${APP_ROOT}/scripts/test_fase2_db_sessions.py"
echo "=================================================================="

