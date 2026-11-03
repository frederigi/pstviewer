-- ============================================================================
-- PST Viewer - Schema MySQL 8.0+ / MariaDB 10.11+ (Debian/DietPi)
-- Engine: InnoDB | Charset: utf8mb4 | Collation: utf8mb4_unicode_ci
-- ============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 1. Usuários do sistema
CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL COMMENT 'Argon2id hash',
    is_admin TINYINT(1) NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    failed_login_attempts INT UNSIGNED NOT NULL DEFAULT 0,
    locked_until DATETIME NULL,
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Sessões de Autenticação Web
CREATE TABLE IF NOT EXISTS auth_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    session_token_hash CHAR(64) NOT NULL COMMENT 'SHA-256 do token de cookie HttpOnly',
    csrf_token CHAR(64) NOT NULL,
    user_id BIGINT UNSIGNED NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    user_agent VARCHAR(255) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    UNIQUE KEY uq_auth_sessions_token (session_token_hash),
    KEY idx_auth_sessions_user_active (user_id, revoked_at, expires_at),
    CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Sessões Temporárias de Consulta PST (Isolamento Estrito por Usuário)
CREATE TABLE IF NOT EXISTS pst_sessions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    session_uuid CHAR(36) NOT NULL COMMENT 'UUID v4 criptograficamente aleatório',
    user_id BIGINT UNSIGNED NOT NULL,
    auth_session_id BIGINT UNSIGNED NULL,
    status ENUM(
        'UPLOADING',
        'VALIDATING',
        'QUEUED',
        'PROCESSING',
        'READY_PARTIAL',
        'READY',
        'CANCELLED',
        'CLOSING',
        'CLEANING',
        'PURGED',
        'FAILED',
        'CLEANUP_ERROR'
    ) NOT NULL DEFAULT 'UPLOADING',
    pst_format VARCHAR(48) NULL COMMENT 'ANSI ou Unicode',
    file_sha256 CHAR(64) NULL,
    file_size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
    disk_usage_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
    storage_rel_path VARCHAR(128) NOT NULL COMMENT 'Subdiretório relativo em /srv/pstviewer/sessions/',
    display_label VARCHAR(120) NOT NULL COMMENT 'Rótulo sanitizado em uso apenas enquanto a sessão estiver ativa',
    total_folders INT UNSIGNED NOT NULL DEFAULT 0,
    processed_folders INT UNSIGNED NOT NULL DEFAULT 0,
    total_messages INT UNSIGNED NOT NULL DEFAULT 0,
    processed_messages INT UNSIGNED NOT NULL DEFAULT 0,
    total_attachments INT UNSIGNED NOT NULL DEFAULT 0,
    processed_attachments INT UNSIGNED NOT NULL DEFAULT 0,
    corrupted_items INT UNSIGNED NOT NULL DEFAULT 0,
    progress_percent DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    current_stage VARCHAR(120) NULL,
    diagnostic_summary TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    idle_expires_at DATETIME NOT NULL,
    hard_expires_at DATETIME NOT NULL,
    closed_at DATETIME NULL,
    purged_at DATETIME NULL,
    UNIQUE KEY uq_pst_sessions_uuid (session_uuid),
    KEY idx_pst_sessions_user_status (user_id, status),
    KEY idx_pst_sessions_expiration (status, idle_expires_at, hard_expires_at),
    CONSTRAINT fk_pst_sessions_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_pst_sessions_auth FOREIGN KEY (auth_session_id)
        REFERENCES auth_sessions (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Árvore de Pastas Temporárias Extraídas
CREATE TABLE IF NOT EXISTS pst_folders (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pst_session_id BIGINT UNSIGNED NOT NULL,
    parent_folder_id BIGINT UNSIGNED NULL,
    pff_identifier VARCHAR(64) NULL,
    name VARCHAR(255) NOT NULL,
    full_path VARCHAR(1024) NOT NULL,
    folder_role ENUM(
        'INBOX',
        'SENT',
        'DRAFTS',
        'TRASH',
        'ARCHIVE',
        'JUNK',
        'CUSTOM'
    ) NOT NULL DEFAULT 'CUSTOM',
    depth SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    message_count INT UNSIGNED NOT NULL DEFAULT 0,
    unread_count INT UNSIGNED NOT NULL DEFAULT 0,
    sort_order INT UNSIGNED NOT NULL DEFAULT 0,
    KEY idx_pst_folders_session_parent (pst_session_id, parent_folder_id, sort_order),
    CONSTRAINT fk_pst_folders_session FOREIGN KEY (pst_session_id)
        REFERENCES pst_sessions (id) ON DELETE CASCADE,
    CONSTRAINT fk_pst_folders_parent FOREIGN KEY (parent_folder_id)
        REFERENCES pst_folders (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Mensagens Extraídas (Metadados e Corpos Sanitizados)
CREATE TABLE IF NOT EXISTS pst_messages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pst_session_id BIGINT UNSIGNED NOT NULL,
    folder_id BIGINT UNSIGNED NOT NULL,
    pff_message_id VARCHAR(64) NULL,
    internet_message_id VARCHAR(255) NULL,
    subject VARCHAR(998) NULL,
    sender_name VARCHAR(255) NULL,
    sender_email VARCHAR(320) NULL,
    recipients_to TEXT NULL,
    recipients_cc TEXT NULL,
    recipients_bcc TEXT NULL,
    sent_at DATETIME NULL,
    received_at DATETIME NULL,
    importance TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '0=Baixa, 1=Normal, 2=Alta',
    has_attachments TINYINT(1) NOT NULL DEFAULT 0,
    attachment_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    size_bytes INT UNSIGNED NOT NULL DEFAULT 0,
    snippet VARCHAR(300) NULL,
    body_plain MEDIUMTEXT NULL,
    body_html_sanitized MEDIUMTEXT NULL,
    transport_headers TEXT NULL,
    raw_eml_rel_path VARCHAR(255) NULL COMMENT 'Caminho relativo se .eml bruto foi salvo em disco',
    extraction_warnings VARCHAR(500) NULL,
    KEY idx_pst_messages_session_folder_date (pst_session_id, folder_id, received_at DESC, id DESC),
    KEY idx_pst_messages_session_sender (pst_session_id, sender_email(120)),
    KEY idx_pst_messages_session_date (pst_session_id, received_at DESC),
    FULLTEXT KEY ft_pst_messages_search (subject, sender_name, sender_email, recipients_to, recipients_cc, body_plain),
    CONSTRAINT fk_pst_messages_session FOREIGN KEY (pst_session_id)
        REFERENCES pst_sessions (id) ON DELETE CASCADE,
    CONSTRAINT fk_pst_messages_folder FOREIGN KEY (folder_id)
        REFERENCES pst_folders (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Anexos Extraídos e Conteúdo Textual Indexável
CREATE TABLE IF NOT EXISTS pst_attachments (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pst_session_id BIGINT UNSIGNED NOT NULL,
    message_id BIGINT UNSIGNED NOT NULL,
    attachment_index SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    original_filename VARCHAR(255) NOT NULL,
    safe_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL DEFAULT 'application/octet-stream',
    size_bytes BIGINT UNSIGNED NOT NULL DEFAULT 0,
    sha256 CHAR(64) NULL,
    storage_rel_path VARCHAR(255) NOT NULL COMMENT 'Caminho relativo dentro do diretório da sessão',
    extraction_status ENUM(
        'EXTRACTED',
        'TEXT_INDEXED',
        'ENCRYPTED_OR_PASSWORD',
        'CORRUPTED',
        'UNSUPPORTED_FORMAT',
        'SIZE_LIMIT_EXCEEDED'
    ) NOT NULL DEFAULT 'EXTRACTED',
    is_inline TINYINT(1) NOT NULL DEFAULT 0,
    content_id VARCHAR(255) NULL,
    extracted_text MEDIUMTEXT NULL,
    metadata_json JSON NULL,
    KEY idx_pst_attachments_session_msg (pst_session_id, message_id),
    FULLTEXT KEY ft_pst_attachments_search (original_filename, extracted_text),
    CONSTRAINT fk_pst_attachments_session FOREIGN KEY (pst_session_id)
        REFERENCES pst_sessions (id) ON DELETE CASCADE,
    CONSTRAINT fk_pst_attachments_message FOREIGN KEY (message_id)
        REFERENCES pst_messages (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Fila Persistente de Tarefas (Processamento PST e Limpeza Segura)
CREATE TABLE IF NOT EXISTS background_jobs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    pst_session_id BIGINT UNSIGNED NOT NULL,
    job_type ENUM('EXTRACT_PST', 'INDEX_ATTACHMENTS', 'CLEANUP_SESSION') NOT NULL,
    status ENUM('PENDING', 'RUNNING', 'COMPLETED', 'CANCELLED', 'FAILED') NOT NULL DEFAULT 'PENDING',
    priority TINYINT UNSIGNED NOT NULL DEFAULT 5,
    attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts TINYINT UNSIGNED NOT NULL DEFAULT 3,
    worker_pid INT UNSIGNED NULL,
    cancel_requested TINYINT(1) NOT NULL DEFAULT 0,
    next_retry_at DATETIME NULL,
    last_error TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    KEY idx_jobs_status_priority (status, priority, next_retry_at, created_at),
    KEY idx_jobs_session (pst_session_id, job_type),
    CONSTRAINT fk_jobs_session FOREIGN KEY (pst_session_id)
        REFERENCES pst_sessions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. Configurações Administrativas Dinâmicas
CREATE TABLE IF NOT EXISTS system_settings (
    setting_key VARCHAR(64) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL,
    description VARCHAR(255) NOT NULL,
    updated_by BIGINT UNSIGNED NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. Logs de Auditoria (Sem dados pessoais de mensagens ou corpos de e-mail)
CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    event_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id BIGINT UNSIGNED NULL,
    username_snapshot VARCHAR(64) NULL,
    session_uuid CHAR(36) NULL,
    event_type VARCHAR(64) NOT NULL COMMENT 'LOGIN, LOGOUT, LOGIN_FAIL, UPLOAD_START, UPLOAD_DONE, EXTRACT_DONE, EXPORT_EML, DOWNLOAD_ATTACHMENT, SESSION_PURGED, AUTHZ_DENIED, CLEANUP_ERROR',
    event_result ENUM('SUCCESS', 'FAILURE', 'WARNING') NOT NULL,
    ip_address VARCHAR(45) NULL,
    details_json JSON NULL COMMENT 'Metadados técnicos sanitizados (ex.: sha256, bytes, código de erro), nunca corpos ou nomes sensíveis permanentes',
    KEY idx_audit_event_time (event_time),
    KEY idx_audit_user (user_id, event_time),
    KEY idx_audit_session (session_uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Valores iniciais calibrados para a VM Debian 12 (4 vCPUs x86_64, 4 GiB RAM, 111 GiB livres em NVMe)
INSERT IGNORE INTO system_settings (setting_key, setting_value, description) VALUES
('max_upload_size_mb', '5120', 'Tamanho máximo permitido por arquivo PST enviado (MB) - 5 GB'),
('max_session_disk_mb', '12288', 'Espaço máximo total em disco por sessão PST incluindo extraídos (MB) - 12 GB'),
('min_free_disk_mb', '15360', 'Espaço livre mínimo exigido no volume para aceitar novos uploads (MB) - 15 GB'),
('session_idle_timeout_min', '30', 'Tempo máximo de inatividade da sessão antes do expurgo automático (minutos)'),
('session_hard_timeout_min', '240', 'Duração máxima absoluta de uma consulta PST (minutos)'),
('max_concurrent_extractions', '1', 'Quantidade máxima de extrações PST pesadas simultâneas no worker (ajustável até 2 em 4 vCPUs)'),
('batch_commit_size', '100', 'Quantidade de mensagens gravadas por transação curta no banco durante extração'),
('max_attachment_extract_mb', '50', 'Tamanho máximo de anexo individual para extração de texto (MB)'),
('enable_ocr_tesseract', '0', 'Habilitar OCR opcional com Tesseract em imagens/PDFs digitalizados (0=Não, 1=Sim)'),
('audit_retention_days', '90', 'Dias de retenção dos logs de auditoria');

SET FOREIGN_KEY_CHECKS = 1;

