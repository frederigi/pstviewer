#!/usr/bin/env bash
# ==============================================================================
# PST Viewer - Instalação Completa das Fases 4, 5, 6 e 7:
#   - Leitor Web Estilo Outlook, Pesquisa Global, Anexos, Exportação EML/TXT e Impressão
#   - Serviço systemd da Aplicação Web (pstviewer-web.service)
#   - Criação segura do primeiro Administrador
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
echo " PST VIEWER - INSTALAÇÃO FASES 4 A 7 (LEITOR WEB E SERVIÇOS)"
echo "=================================================================="

echo "[1/6] Sincronizando código-fonte, templates e arquivos estáticos para ${APP_ROOT}..."
mkdir -p "${APP_ROOT}/app/templates" "${APP_ROOT}/app/static/css" "${APP_ROOT}/app/static/js"
if [ "${SRC_DIR}" != "${APP_ROOT}" ]; then
    cp -r "${SRC_DIR}/app/"* "${APP_ROOT}/app/"
    cp -r "${SRC_DIR}/database/"* "${APP_ROOT}/database/"
    cp -r "${SRC_DIR}/scripts/"* "${APP_ROOT}/scripts/"
    cp "${SRC_DIR}/requirements.txt" "${APP_ROOT}/requirements.txt"
    chown -R root:"${APP_USER}" "${APP_ROOT}/app" "${APP_ROOT}/database" "${APP_ROOT}/scripts" "${APP_ROOT}/requirements.txt"
fi
chown -R "${APP_USER}:${APP_USER}" /srv/pstviewer /var/lib/pstviewer /var/log/pstviewer

echo "[2/6] Verificando pacote httpx no virtualenv para testes integrados..."
"${APP_ROOT}/venv/bin/pip" install httpx==0.28.1 >/dev/null

echo "[3/6] Fixando porta interna 8085 para o PST Viewer..."
BIND_PORT=8085

sed -i "s/^PSTVIEWER_BIND_HOST=.*/PSTVIEWER_BIND_HOST=0.0.0.0/" "${ENV_FILE}"
sed -i "s/^PSTVIEWER_BIND_PORT=.*/PSTVIEWER_BIND_PORT=${BIND_PORT}/" "${ENV_FILE}"

echo "[4/6] Configurando serviço systemd da Aplicação Web (pstviewer-web.service)..."
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

if [ -f /etc/systemd/system/pstviewer-worker.service ]; then
    sed -i "s/^MemoryMax=.*/MemoryMax=2560M/" /etc/systemd/system/pstviewer-worker.service
fi

systemctl daemon-reload

echo "[4.2/6] Verificando se há sessões PST com status FAILED para recuperar..."
NEEDS_WORKER_RESTART=$(PYTHONPATH="${APP_ROOT}" PSTVIEWER_ENV_FILE="${ENV_FILE}" \
    "${APP_ROOT}/venv/bin/python" - <<'PY' || echo "0"
from datetime import timedelta
import shutil
from sqlalchemy import delete, select
from app.database.session import SessionLocal
from app.database.models import BackgroundJob, PstAttachment, PstFolder, PstMessage, PstSession
from app.services.session_manager import resolve_session_dir, utc_now

now = utc_now()
recovered = 0
with SessionLocal() as db:
    sessions = list(
        db.scalars(
            select(PstSession).where(PstSession.status == "FAILED")
        ).all()
    )
    for s in sessions:
        sdir = resolve_session_dir(s.session_uuid)
        pst_file = sdir / "original.pst"
        if not pst_file.is_file():
            continue
        job = db.scalar(
            select(BackgroundJob).where(
                BackgroundJob.pst_session_id == s.id,
                BackgroundJob.job_type == "EXTRACT_PST",
            )
        )
        if not job or job.status == "COMPLETED":
            continue
        db.execute(delete(PstAttachment).where(PstAttachment.pst_session_id == s.id))
        db.execute(delete(PstMessage).where(PstMessage.pst_session_id == s.id))
        db.execute(delete(PstFolder).where(PstFolder.pst_session_id == s.id))
        att_dir = sdir / "attachments"
        if att_dir.exists():
            shutil.rmtree(att_dir, ignore_errors=True)
        att_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        s.processed_folders = 0
        s.processed_messages = 0
        s.processed_attachments = 0
        s.total_attachments = 0
        s.corrupted_items = 0
        s.disk_usage_bytes = s.file_size_bytes
        s.progress_percent = 0
        s.status = "QUEUED"
        s.current_stage = "Reprocessando arquivo PST com extração otimizada"
        s.last_heartbeat_at = now
        s.idle_expires_at = now + timedelta(minutes=60)
        job.status = "PENDING"
        job.attempts = 0
        job.cancel_requested = False
        job.worker_pid = None
        job.last_error = None
        recovered += 1
    db.commit()
print(recovered)
PY
)

chown -R "${APP_USER}:${APP_USER}" /srv/pstviewer /var/lib/pstviewer /var/log/pstviewer
if ! systemctl is-active --quiet pstviewer-worker.service || [ "${NEEDS_WORKER_RESTART}" != "0" ]; then
    systemctl restart pstviewer-worker.service
fi
systemctl enable --now pstviewer-web.service
systemctl restart pstviewer-web.service

echo "[4.5/6] Atualizando mensagens já extraídas no banco para liberar todas as imagens externas..."
mariadb -u root "${DB_NAME:-pstviewer}" <<'SQL' || true
UPDATE pst_messages
SET extraction_warnings = NULL,
    body_html_sanitized = REPLACE(
        REPLACE(body_html_sanitized, 'data-blocked-src="', 'src="'),
        'alt="[Imagem externa bloqueada por segurança]"',
        ''
    )
WHERE extraction_warnings IS NOT NULL
   OR body_html_sanitized LIKE '%data-blocked-src%';
SQL

echo "[5/6] Cadastrando primeiro administrador (se ainda não existir)..."
PYTHONPATH="${APP_ROOT}" PSTVIEWER_ENV_FILE="${ENV_FILE}" \
    "${APP_ROOT}/venv/bin/python" "${APP_ROOT}/scripts/create_admin.py" --if-not-exists

echo "[6/6] Verificando status de todos os serviços do PST Viewer..."
echo "  - pstviewer-web.service:     $(systemctl is-active pstviewer-web.service)"
echo "  - pstviewer-worker.service:  $(systemctl is-active pstviewer-worker.service)"
echo "  - pstviewer-cleaner.timer:   $(systemctl is-active pstviewer-cleaner.timer)"

INTERNAL_IP=$(hostname -I | awk '{print $1}')
echo "=================================================================="
echo " [OK] PST VIEWER ATIVO NA REDE INTERNA!"
echo " Endereço de acesso interno: http://${INTERNAL_IP}:${BIND_PORT}"
echo " Para redefinir ou ver uma nova senha do usuário 'admin':"
echo "   PYTHONPATH=${APP_ROOT} ${APP_ROOT}/venv/bin/python ${APP_ROOT}/scripts/create_admin.py"
echo "=================================================================="

