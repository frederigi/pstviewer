#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Instalador Unificado Automático (Linux Debian / Ubuntu / DietPi)
# Verifica requisitos da máquina, avisa o usuário, instala dependências,
# configura MariaDB, migrações, serviços systemd e exibe login/senha do Admin.
# ==============================================================================
set -euo pipefail

AUTO_YES=false
BIND_PORT=8085
RESET_ADMIN_PW=false

for arg in "$@"; do
    case "$arg" in
        -y|--yes) AUTO_YES=true ;;
        --reset-admin) RESET_ADMIN_PW=true ;;
        --port=*) BIND_PORT="${arg#*=}" ;;
    esac
done

BOLD="\033[1m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
CYAN="\033[1;36m"
RESET="\033[0m"

echo -e "${CYAN}========================================================================${RESET}"
echo -e "${BOLD}   PST VIEWER — INSTALADOR AUTOMÁTICO DE SERVIDOR (LINUX / CLOUD)${RESET}"
echo -e "${CYAN}========================================================================${RESET}"

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}[ERRO] Este instalador precisa ser executado como root (use: sudo ./install.sh).${RESET}" >&2
    exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# ------------------------------------------------------------------------------
# ETAPA 1: VERIFICAÇÃO DE REQUISITOS DE HARDWARE E PACOTES DO SISTEMA
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[1/7] Analisando requisitos da máquina e pacotes necessários...${RESET}"

OS_NAME="Linux"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME="${PRETTY_NAME:-Linux}"
fi
CPU_CORES=$(nproc 2>/dev/null || echo 1)
RAM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}' || echo 0)
FREE_DISK_MB=$(df -Pm / 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)

echo -e "  • Sistema Operacional : ${BOLD}${OS_NAME}${RESET}"
echo -e "  • Processador (vCPUs) : ${BOLD}${CPU_CORES} núcleo(s)${RESET}"
echo -e "  • Memória RAM Total   : ${BOLD}${RAM_MB} MB${RESET}"
echo -e "  • Espaço Livre Disco  : ${BOLD}${FREE_DISK_MB} MB${RESET}"

if [ "${RAM_MB}" -lt 1024 ]; then
    echo -e "  ${YELLOW}[AVISO] A máquina possui menos de 1 GB de RAM (${RAM_MB} MB). Recomendado >= 2 GB para PSTs grandes.${RESET}"
fi
if [ "${FREE_DISK_MB}" -lt 5120 ]; then
    echo -e "  ${YELLOW}[AVISO] Espaço livre em disco inferior a 5 GB (${FREE_DISK_MB} MB). Recomendado >= 20 GB para sessões temporárias.${RESET}"
fi

REQUIRED_PKGS=(
    "python3"
    "python3-venv"
    "python3-pip"
    "python3-pypff"
    "libpff1"
    "pff-tools"
    "mariadb-server"
    "poppler-utils"
    "antiword"
    "catdoc"
    "tesseract-ocr"
    "tesseract-ocr-por"
    "curl"
)

MISSING_PKGS=()
echo -e "\n${BOLD}Status das dependências de sistema (APT):${RESET}"
for pkg in "${REQUIRED_PKGS[@]}"; do
    if dpkg -s "$pkg" >/dev/null 2>&1; then
        echo -e "  ${GREEN}[INSTALADO]${RESET} $pkg"
    else
        echo -e "  ${YELLOW}[PENDENTE]${RESET}  $pkg  -> será instalado automaticamente"
        MISSING_PKGS+=("$pkg")
    fi
done

if [ "${#MISSING_PKGS[@]}" -gt 0 ]; then
    echo -e "\n${YELLOW}Atenção:${RESET} ${#MISSING_PKGS[@]} pacote(s) serão instalados via APT: ${BOLD}${MISSING_PKGS[*]}${RESET}"
else
    echo -e "\n${GREEN}Todos os pacotes de sistema necessários já estão instalados!${RESET}"
fi

if [ "${AUTO_YES}" = false ] && [ -t 0 ]; then
    echo ""
    read -r -p "Deseja iniciar a instalação e configuração completa agora? [S/n]: " RESP
    RESP="${RESP:-S}"
    if [[ ! "${RESP}" =~ ^[SsYy]$ ]]; then
        echo "Instalação cancelada pelo usuário."
        exit 0
    fi
fi

# ------------------------------------------------------------------------------
# ETAPA 2: INSTALAÇÃO DE DEPENDÊNCIAS AUSENTES
# ------------------------------------------------------------------------------
if [ "${#MISSING_PKGS[@]}" -gt 0 ]; then
    echo -e "\n${BOLD}[2/7] Instalando pacotes ausentes via APT...${RESET}"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y "${MISSING_PKGS[@]}"
else
    echo -e "\n${BOLD}[2/7] Nenhuma dependência APT pendente. Pulando download de pacotes...${RESET}"
fi

# ------------------------------------------------------------------------------
# ETAPA 3: USUÁRIO DE SISTEMA E DIRETÓRIOS ISOLADOS
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[3/7] Configurando usuário dedicado (${APP_USER}) e diretórios seguros...${RESET}"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir "${APP_ROOT}" --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_ROOT}/app/templates" "${APP_ROOT}/app/static/css" "${APP_ROOT}/app/static/js"
mkdir -p "${CONF_DIR}" "${APP_ROOT}/database" "${APP_ROOT}/scripts"
mkdir -p "${SESSIONS_DIR}" "${QUARANTINE_DIR}" "${JOBS_DIR}"
mkdir -p "${LOG_DIR}/application" "${LOG_DIR}/audit"

if [ "${SRC_DIR}" != "${APP_ROOT}" ]; then
    cp -r "${SRC_DIR}/app/"* "${APP_ROOT}/app/"
    cp -r "${SRC_DIR}/database/"* "${APP_ROOT}/database/"
    cp -r "${SRC_DIR}/scripts/"* "${APP_ROOT}/scripts/"
    cp "${SRC_DIR}/requirements.txt" "${APP_ROOT}/requirements.txt"
fi

chown -R root:"${APP_USER}" "${APP_ROOT}"
chmod 0750 "${APP_ROOT}" "${CONF_DIR}"
chown -R "${APP_USER}:${APP_USER}" "/srv/pstviewer" "${JOBS_DIR}" "${LOG_DIR}"
chmod 0700 "/srv/pstviewer" "${SESSIONS_DIR}" "${QUARANTINE_DIR}" "${JOBS_DIR}"
chmod 0750 "${LOG_DIR}" "${LOG_DIR}/application" "${LOG_DIR}/audit"

# ------------------------------------------------------------------------------
# ETAPA 4: BANCO DE DADOS MARIADB / MYSQL E ARQUIVO .ENV
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[4/7] Configurando MariaDB/MySQL (InnoDB UTF8MB4) e variáveis de ambiente...${RESET}"
systemctl enable --now mariadb >/dev/null 2>&1 || systemctl enable --now mysql >/dev/null 2>&1 || true

if [ -f "${ENV_FILE}" ]; then
    DB_PASS=$(awk -F= '/^PSTVIEWER_DB_PASSWORD=/{print $2}' "${ENV_FILE}" | tr -d '"' | tr -d "'")
    sed -i "s/^PSTVIEWER_BIND_HOST=.*/PSTVIEWER_BIND_HOST=0.0.0.0/" "${ENV_FILE}"
    sed -i "s/^PSTVIEWER_BIND_PORT=.*/PSTVIEWER_BIND_PORT=${BIND_PORT}/" "${ENV_FILE}"
else
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat <<EOF > "${ENV_FILE}"
PSTVIEWER_ENV=production
PSTVIEWER_APP_NAME="PST Viewer"
PSTVIEWER_BIND_HOST=0.0.0.0
PSTVIEWER_BIND_PORT=${BIND_PORT}
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

# ------------------------------------------------------------------------------
# ETAPA 5: AMBIENTE VIRTUAL PYTHON E MIGRAÇÕES DO BANCO
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[5/7] Instalando bibliotecas Python no virtualenv e aplicando migrações...${RESET}"
if [ ! -d "${APP_ROOT}/venv" ]; then
    python3 -m venv --system-site-packages "${APP_ROOT}/venv"
fi
"${APP_ROOT}/venv/bin/pip" install --upgrade pip >/dev/null
"${APP_ROOT}/venv/bin/pip" install -r "${APP_ROOT}/requirements.txt" >/dev/null

PYTHONPATH="${APP_ROOT}" PSTVIEWER_ENV_FILE="${ENV_FILE}" \
    "${APP_ROOT}/venv/bin/python" -m app.database.migrations

# ------------------------------------------------------------------------------
# ETAPA 6: SERVIÇOS SYSTEMD (WEB, WORKER E GUARDIÃO DE LIMPEZA)
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[6/7] Configurando e iniciando serviços systemd...${RESET}"

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

cat <<EOF > /etc/systemd/system/pstviewer-worker.service
[Unit]
Description=PST Viewer - Worker de Extracao PST e Indexacao de Anexos
After=network.target mariadb.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_ROOT}
Environment="PYTHONPATH=${APP_ROOT}"
Environment="PSTVIEWER_ENV_FILE=${ENV_FILE}"
ExecStart=${APP_ROOT}/venv/bin/python -m app.workers.pst_worker --poll-interval 2.0
Restart=on-failure
RestartSec=5s
Nice=10
CPUQuota=80%
MemoryMax=2560M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/srv/pstviewer /var/lib/pstviewer /var/log/pstviewer

[Install]
WantedBy=multi-user.target
EOF

cat <<EOF > /etc/systemd/system/pstviewer-web.service
[Unit]
Description=PST Viewer - Aplicacao Web FastAPI (Leitor Temporario de PST)
After=network.target mariadb.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_ROOT}
Environment="PYTHONPATH=${APP_ROOT}"
Environment="PSTVIEWER_ENV_FILE=${ENV_FILE}"
Environment="TMPDIR=/srv/pstviewer/quarantine"
ExecStart=${APP_ROOT}/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${BIND_PORT} --workers 2 --timeout-keep-alive 120 --no-access-log
Restart=on-failure
RestartSec=3s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/srv/pstviewer /var/lib/pstviewer /var/log/pstviewer

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now pstviewer-cleaner.timer
systemctl enable --now pstviewer-worker.service
systemctl enable --now pstviewer-web.service
systemctl restart pstviewer-worker.service pstviewer-web.service

# ------------------------------------------------------------------------------
# ETAPA 7: CRIAÇÃO DO ADMINISTRADOR E RESUMO DE ACESSO
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}[7/7] Configurando credenciais do usuário Administrador...${RESET}"

CHOSEN_PW=""
if [ "${AUTO_YES}" = false ] && [ -t 0 ]; then
    echo -e "\n${CYAN}Definição de senha para o usuário 'admin':${RESET}"
    read -r -p "Digite a senha que deseja para o 'admin' (mín. 8 caracteres) [Enter = gerar automática]: " CHOSEN_PW
fi

if [ -n "${CHOSEN_PW}" ]; then
    ADMIN_PW="${CHOSEN_PW}"
    MUST_CHANGE_FLAG=""
else
    ADMIN_PW=$(python3 -c "import secrets; print(secrets.token_urlsafe(10))")
    MUST_CHANGE_FLAG="--must-change-password"
fi

if [ "${RESET_ADMIN_PW}" = true ] || [ -n "${CHOSEN_PW}" ]; then
    ADMIN_OUT=$(PYTHONPATH="${APP_ROOT}" PSTVIEWER_ENV_FILE="${ENV_FILE}" \
        "${APP_ROOT}/venv/bin/python" "${APP_ROOT}/scripts/create_admin.py" --username admin --password "${ADMIN_PW}" ${MUST_CHANGE_FLAG})
else
    ADMIN_OUT=$(PYTHONPATH="${APP_ROOT}" PSTVIEWER_ENV_FILE="${ENV_FILE}" \
        "${APP_ROOT}/venv/bin/python" "${APP_ROOT}/scripts/create_admin.py" --username admin --password "${ADMIN_PW}" --if-not-exists ${MUST_CHANGE_FLAG})
fi

INTERNAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
INTERNAL_IP="${INTERNAL_IP:-127.0.0.1}"

echo -e "\n${GREEN}========================================================================${RESET}"
echo -e "${GREEN}   INSTALAÇÃO DO PST VIEWER CONCLUÍDA COM SUCESSO!${RESET}"
echo -e "${GREEN}========================================================================${RESET}"
echo -e "  • Status Web App  : $(systemctl is-active pstviewer-web.service)"
echo -e "  • Status Worker   : $(systemctl is-active pstviewer-worker.service)"
echo -e "  • Status Cleaner  : $(systemctl is-active pstviewer-cleaner.timer)"
echo -e "------------------------------------------------------------------------"
echo -e "  ${BOLD}URL de Acesso     :${RESET} http://${INTERNAL_IP}:${BIND_PORT}"
echo -e "  ${BOLD}Usuário Admin     :${RESET} admin"
if echo "${ADMIN_OUT}" | grep -q "já está cadastrado"; then
    echo -e "  ${BOLD}Senha Admin       :${RESET} (Preservada da instalação anterior)"
    echo -e "  ${YELLOW}Dica: Para gerar nova senha do admin, rode: sudo ./install.sh --reset-admin${RESET}"
else
    echo -e "  ${BOLD}Senha Admin       :${RESET} ${YELLOW}${ADMIN_PW}${RESET}"
fi
echo -e "${GREEN}========================================================================${RESET}"

