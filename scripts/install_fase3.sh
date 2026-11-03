#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Fase 3: Atualização dos Serviços de Upload, Extração PST,
# Extratores de Anexos e Serviço systemd do Worker (pstviewer-worker.service).
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
APP_USER="pstviewer"

echo "=================================================================="
echo " PST VIEWER - INSTALAÇÃO FASE 3 (UPLOAD E WORKER DE EXTRAÇÃO PST)"
echo "=================================================================="

echo "[1/5] Verificando extratores opcionais de documentos (antiword, catdoc)..."
apt-get install -y antiword catdoc curl >/dev/null 2>&1 || true

echo "[2/5] Sincronizando código da Fase 3 para ${APP_ROOT}..."
if [ "${SRC_DIR}" != "${APP_ROOT}" ]; then
    cp -r "${SRC_DIR}/app/"* "${APP_ROOT}/app/"
    cp -r "${SRC_DIR}/database/"* "${APP_ROOT}/database/"
    cp -r "${SRC_DIR}/scripts/"* "${APP_ROOT}/scripts/"
    cp "${SRC_DIR}/requirements.txt" "${APP_ROOT}/requirements.txt"
    chown -R root:"${APP_USER}" "${APP_ROOT}/app" "${APP_ROOT}/database" "${APP_ROOT}/scripts" "${APP_ROOT}/requirements.txt"
fi

echo "[3/5] Configurando serviço systemd do Worker PST (pstviewer-worker.service)..."
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
MemoryMax=1024M
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/srv/pstviewer /var/lib/pstviewer /var/log/pstviewer

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now pstviewer-worker.service

echo "[4/5] Obtendo amostra PST pública legal (Apache Tika testPST.pst - Apache License 2.0) para o teste automatizado..."
SAMPLE_PST="/tmp/sample_apache_tika.pst"
if [ ! -s "${SAMPLE_PST}" ]; then
    curl -fsSL "https://raw.githubusercontent.com/apache/tika/main/tika-parsers/tika-parsers-standard/tika-parsers-standard-modules/tika-parser-microsoft-module/src/test/resources/test-documents/testPST.pst" \
        -o "${SAMPLE_PST}" || true
fi
if [ -s "${SAMPLE_PST}" ]; then
    chmod 0644 "${SAMPLE_PST}"
    echo "  -> Amostra legal salva em ${SAMPLE_PST} ($(stat -c%s "${SAMPLE_PST}") bytes)."
else
    echo "  -> [AVISO] Não foi possível baixar amostra externa; você pode informar qualquer .pst local."
fi

echo "[5/5] Verificando status dos serviços systemd..."
systemctl is-active pstviewer-worker.service
systemctl is-active pstviewer-cleaner.timer

echo "=================================================================="
echo " [OK] FASE 3 INSTALADA COM SUCESSO!"
echo " Para executar a bateria de testes reais da Fase 3:"
echo "   PYTHONPATH=${APP_ROOT} ${APP_ROOT}/venv/bin/python ${APP_ROOT}/scripts/test_fase3_upload_processing.py"
echo "=================================================================="

