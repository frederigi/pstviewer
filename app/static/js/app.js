/**
 * PST Viewer - Aplicação Frontend Estilo Microsoft Outlook
 * 100% em Português Brasileiro, com proteção CSRF, paginação sob demanda e iframe sandbox.
 */

(function () {
    "use strict";

    const state = {
        user: null,
        csrfToken: null,
        currentSessionUuid: null,
        currentSessionData: null,
        foldersFlat: [],
        foldersTree: [],
        expandedFolderIds: new Set(),
        selectedFolderId: null,
        isSearchMode: false,
        currentPage: 1,
        pageSize: 150,
        totalPages: 1,
        sortBy: "date_desc",
        selectedMessageId: null,
        selectedMessageDetail: null,
        bodyViewMode: "html", // "html" | "plain" | "raw"
        pollTimer: null,
    };

    const $ = (id) => document.getElementById(id);

    function escapeHtml(val) {
        if (val === null || val === undefined) return "";
        return String(val)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    /* ======================================================================
     * SISTEMA DE DIÁLOGOS E NOTIFICAÇÕES ELEGANTES (SUBSTITUI ALERT/CONFIRM)
     * ====================================================================== */
    function getToastContainer() {
        let c = document.getElementById("ui-toast-container");
        if (!c) {
            c = document.createElement("div");
            c.id = "ui-toast-container";
            c.className = "ui-toast-container";
            document.body.appendChild(c);
        }
        return c;
    }

    const SVG_ICONS = {
        check: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polyline points="20 6 9 17 4 12"/></svg>`,
        alert: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
        info: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
        shield: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
        key: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>`,
        trash: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,
        logout: `<svg class="svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`,
        paperclip: `<svg class="svg-icon svg-icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>`,
        folder: `<svg class="svg-icon svg-icon-sm" style="color:#005a9e;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
        inbox: `<svg class="svg-icon svg-icon-sm" style="color:#005a9e;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>`,
        sent: `<svg class="svg-icon svg-icon-sm" style="color:#005a9e;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
        drafts: `<svg class="svg-icon svg-icon-sm" style="color:#605e5c;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>`,
    };

    function uiToast(message, variant = "info", title = "") {
        const container = getToastContainer();
        const icons = {
            success: SVG_ICONS.check,
            danger: SVG_ICONS.alert,
            warning: SVG_ICONS.alert,
            info: SVG_ICONS.info,
        };
        const defaultTitles = {
            success: "Operação concluída",
            danger: "Atenção / Erro",
            warning: "Aviso do Sistema",
            info: "Informação",
        };
        const toast = document.createElement("div");
        toast.className = `ui-toast toast-${variant}`;
        toast.innerHTML = `
            <div class="ui-toast-icon">${icons[variant] || SVG_ICONS.info}</div>
            <div class="ui-toast-body">
                <div class="ui-toast-title">${escapeHtml(title || defaultTitles[variant] || "Sistema")}</div>
                <div class="ui-toast-msg">${escapeHtml(message)}</div>
            </div>
        `;
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.transition = "opacity 0.25s ease, transform 0.25s ease";
            toast.style.opacity = "0";
            toast.style.transform = "translateX(20px)";
            setTimeout(() => toast.remove(), 260);
        }, 4500);
    }

    function uiConfirm({
        title = "Confirmação do Sistema",
        message = "",
        confirmText = "Confirmar",
        cancelText = "Cancelar",
        variant = "primary", // "primary" | "danger" | "warning"
        icon = SVG_ICONS.shield,
    } = {}) {
        return new Promise((resolve) => {
            const backdrop = document.createElement("div");
            backdrop.className = "ui-dialog-backdrop";
            const btnClass = variant === "danger" ? "btn-danger" : "btn-primary";
            const iconVariant = variant === "danger" ? "icon-danger" : (variant === "warning" ? "icon-warning" : "icon-primary");

            backdrop.innerHTML = `
                <div class="ui-dialog-box" role="dialog" aria-modal="true">
                    <div class="ui-dialog-body">
                        <div class="ui-dialog-icon ${iconVariant}">${icon}</div>
                        <div class="ui-dialog-content">
                            <h3 class="ui-dialog-title">${escapeHtml(title)}</h3>
                            <p class="ui-dialog-message">${escapeHtml(message)}</p>
                        </div>
                    </div>
                    <div class="ui-dialog-footer">
                        <button type="button" class="btn btn-outline" data-dialog-cancel>${escapeHtml(cancelText)}</button>
                        <button type="button" class="btn ${btnClass}" data-dialog-confirm>${escapeHtml(confirmText)}</button>
                    </div>
                </div>
            `;

            const close = (result) => {
                document.removeEventListener("keydown", onKey);
                backdrop.remove();
                resolve(result);
            };
            const onKey = (ev) => {
                if (ev.key === "Escape") close(false);
                if (ev.key === "Enter") close(true);
            };
            document.addEventListener("keydown", onKey);

            backdrop.querySelector("[data-dialog-cancel]").addEventListener("click", () => close(false));
            backdrop.querySelector("[data-dialog-confirm]").addEventListener("click", () => close(true));
            backdrop.addEventListener("click", (ev) => {
                if (ev.target === backdrop) close(false);
            });

            document.body.appendChild(backdrop);
            backdrop.querySelector("[data-dialog-confirm]").focus();
        });
    }

    function uiAlert({
        title = "Aviso do Sistema",
        message = "",
        buttonText = "Entendi",
        variant = "primary",
        icon = SVG_ICONS.info,
    } = {}) {
        return new Promise((resolve) => {
            const backdrop = document.createElement("div");
            backdrop.className = "ui-dialog-backdrop";
            const iconVariant = variant === "danger" ? "icon-danger" : (variant === "success" ? "icon-success" : "icon-primary");

            backdrop.innerHTML = `
                <div class="ui-dialog-box" role="alertdialog" aria-modal="true">
                    <div class="ui-dialog-body">
                        <div class="ui-dialog-icon ${iconVariant}">${icon}</div>
                        <div class="ui-dialog-content">
                            <h3 class="ui-dialog-title">${escapeHtml(title)}</h3>
                            <p class="ui-dialog-message">${escapeHtml(message)}</p>
                        </div>
                    </div>
                    <div class="ui-dialog-footer">
                        <button type="button" class="btn btn-primary" data-dialog-ok>${escapeHtml(buttonText)}</button>
                    </div>
                </div>
            `;

            const close = () => {
                document.removeEventListener("keydown", onKey);
                backdrop.remove();
                resolve(true);
            };
            const onKey = (ev) => {
                if (ev.key === "Escape" || ev.key === "Enter") close();
            };
            document.addEventListener("keydown", onKey);
            backdrop.querySelector("[data-dialog-ok]").addEventListener("click", close);
            backdrop.addEventListener("click", (ev) => {
                if (ev.target === backdrop) close();
            });

            document.body.appendChild(backdrop);
            backdrop.querySelector("[data-dialog-ok]").focus();
        });
    }

    function uiPrompt({
        title = "Informar Valor",
        message = "",
        placeholder = "",
        inputType = "password",
        minLength = 1,
        confirmText = "Salvar",
        cancelText = "Cancelar",
    } = {}) {
        return new Promise((resolve) => {
            const backdrop = document.createElement("div");
            backdrop.className = "ui-dialog-backdrop";

            backdrop.innerHTML = `
                <div class="ui-dialog-box" role="dialog" aria-modal="true">
                    <div class="ui-dialog-body">
                        <div class="ui-dialog-icon icon-primary">${SVG_ICONS.key}</div>
                        <div class="ui-dialog-content">
                            <h3 class="ui-dialog-title">${escapeHtml(title)}</h3>
                            <p class="ui-dialog-message">${escapeHtml(message)}</p>
                            <input type="${escapeHtml(inputType)}" class="form-control ui-dialog-input" placeholder="${escapeHtml(placeholder)}" minlength="${minLength}">
                            <div class="ui-dialog-err hidden" style="color:var(--danger);font-size:12px;margin-top:6px;"></div>
                        </div>
                    </div>
                    <div class="ui-dialog-footer">
                        <button type="button" class="btn btn-outline" data-dialog-cancel>${escapeHtml(cancelText)}</button>
                        <button type="button" class="btn btn-primary" data-dialog-confirm>${escapeHtml(confirmText)}</button>
                    </div>
                </div>
            `;

            const inp = backdrop.querySelector(".ui-dialog-input");
            const errBox = backdrop.querySelector(".ui-dialog-err");

            const close = (val) => {
                document.removeEventListener("keydown", onKey);
                backdrop.remove();
                resolve(val);
            };
            const submit = () => {
                const val = inp.value || "";
                if (val.length < minLength) {
                    errBox.textContent = `O campo deve ter pelo menos ${minLength} caracteres.`;
                    errBox.classList.remove("hidden");
                    inp.focus();
                    return;
                }
                close(val);
            };
            const onKey = (ev) => {
                if (ev.key === "Escape") close(null);
                if (ev.key === "Enter") submit();
            };
            document.addEventListener("keydown", onKey);

            backdrop.querySelector("[data-dialog-cancel]").addEventListener("click", () => close(null));
            backdrop.querySelector("[data-dialog-confirm]").addEventListener("click", submit);

            document.body.appendChild(backdrop);
            inp.focus();
        });
    }

    function formatBytes(bytes) {
        const n = Number(bytes || 0);
        if (n < 1024) return n + " B";
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
        return (n / (1024 * 1024)).toFixed(2) + " MB";
    }

    function formatDateTime(isoStr) {
        if (!isoStr) return "—";
        try {
            const d = new Date(isoStr.endsWith("Z") ? isoStr : isoStr + "Z");
            if (isNaN(d.getTime())) return isoStr;
            return d.toLocaleString("pt-BR", {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch (_e) {
            return isoStr;
        }
    }

    function getFolderRoleIcon(role) {
        switch (role) {
            case "INBOX": return SVG_ICONS.inbox;
            case "SENT": return SVG_ICONS.sent;
            case "DRAFTS": return SVG_ICONS.drafts;
            case "TRASH": return SVG_ICONS.trash;
            default: return SVG_ICONS.folder;
        }
    }

    function getSenderInitials(name, email) {
        const src = (name || email || "?").trim();
        const parts = src.replace(/[^a-zA-Z0-9À-ÿ\s]/g, "").trim().split(/\s+/);
        if (parts.length >= 2) {
            return (parts[0][0] + parts[1][0]).toUpperCase();
        }
        return src.substring(0, 2).toUpperCase() || "✉";
    }

    async function apiFetch(url, options = {}) {
        const opts = Object.assign({ credentials: "same-origin" }, options);
        opts.headers = Object.assign({}, options.headers || {});
        if (state.csrfToken && ["POST", "PUT", "DELETE", "PATCH"].includes((opts.method || "GET").toUpperCase())) {
            opts.headers["X-CSRF-Token"] = state.csrfToken;
        }
        if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
            opts.headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(opts.body);
        }

        const resp = await fetch(url, opts);
        if (resp.status === 401 && !url.endsWith("/api/auth/login") && !url.endsWith("/api/auth/me")) {
            showLoginView("Sua sessão de autenticação expirou. Faça login novamente.");
            throw new Error("Não autenticado");
        }
        let data = null;
        const ctype = resp.headers.get("content-type") || "";
        if (ctype.includes("application/json")) {
            data = await resp.json();
        } else {
            data = await resp.text();
        }
        if (!resp.ok) {
            const msg = (data && data.detail) ? data.detail : `Erro HTTP ${resp.status}`;
            throw new Error(msg);
        }
        return data;
    }

    function stopPolling() {
        if (state.pollTimer) {
            clearInterval(state.pollTimer);
            state.pollTimer = null;
        }
    }

    /* ======================================================================
     * NAVEGAÇÃO ENTRE TELAS
     * ====================================================================== */
    function showLoginView(alertMsg = "") {
        stopPolling();
        state.user = null;
        state.csrfToken = null;
        state.currentSessionUuid = null;
        $("app-shell").classList.add("hidden");
        $("view-login").classList.remove("hidden");
        const alertEl = $("login-alert");
        if (alertMsg) {
            alertEl.textContent = alertMsg;
            alertEl.classList.remove("hidden");
        } else {
            alertEl.classList.add("hidden");
        }
    }

    function showHomeView() {
        stopPolling();
        state.currentSessionUuid = null;
        state.currentSessionData = null;
        $("view-login").classList.add("hidden");
        $("app-shell").classList.remove("hidden");
        $("view-home").classList.remove("hidden");
        $("view-processing").classList.add("hidden");
        $("view-reader").classList.add("hidden");

        $("topbar-session-label").classList.add("hidden");
        $("topbar-indexing-badge").classList.add("hidden");
        $("topbar-search-area").classList.add("hidden");
        $("btn-close-session").classList.add("hidden");

        loadMyActiveSessions();
    }

    function showProcessingView(sessionUuid) {
        stopPolling();
        state.currentSessionUuid = sessionUuid;
        $("view-home").classList.add("hidden");
        $("view-reader").classList.add("hidden");
        $("view-processing").classList.remove("hidden");
        $("btn-close-session").classList.remove("hidden");
        $("topbar-search-area").classList.add("hidden");

        pollProcessingStatus();
        state.pollTimer = setInterval(pollProcessingStatus, 1800);
    }

    async function openReaderView(sessionUuid) {
        stopPolling();
        state.currentSessionUuid = sessionUuid;
        state.selectedFolderId = null;
        state.selectedMessageId = null;
        state.isSearchMode = false;

        $("view-home").classList.add("hidden");
        $("view-processing").classList.add("hidden");
        $("view-reader").classList.remove("hidden");
        $("topbar-search-area").classList.remove("hidden");
        $("btn-close-session").classList.remove("hidden");

        resetReadingPane();
        await loadFoldersTree(true);

        // Se ainda estiver indexando em segundo plano (READY_PARTIAL), atualiza a cada 4s
        state.pollTimer = setInterval(async () => {
            if (!state.currentSessionUuid) return;
            try {
                const s = await apiFetch(`/api/sessions/${state.currentSessionUuid}`);
                state.currentSessionData = s;
                updateTopbarSessionBadges(s);
                if (s.is_indexing_in_background) {
                    await loadFoldersTree(false);
                } else {
                    stopPolling();
                }
            } catch (_e) {
                stopPolling();
            }
        }, 4000);
    }

    function updateTopbarSessionBadges(sess) {
        if (!sess) return;
        const lbl = $("topbar-session-label");
        lbl.textContent = `${sess.display_label} (${formatBytes(sess.file_size_bytes)})`;
        lbl.classList.remove("hidden");

        const idxBadge = $("topbar-indexing-badge");
        const partialNotice = $("reader-partial-notice");
        if (sess.is_indexing_in_background) {
            idxBadge.textContent = `Indexando ${sess.progress_percent}%`;
            idxBadge.classList.remove("hidden");
            partialNotice.classList.remove("hidden");
        } else {
            idxBadge.classList.add("hidden");
            partialNotice.classList.add("hidden");
        }
    }

    /* ======================================================================
     * AUTENTICAÇÃO E SESSÕES NA TELA INICIAL
     * ====================================================================== */
    async function checkCurrentSession() {
        try {
            const data = await apiFetch("/api/auth/me");
            onAuthenticated(data.user, data.csrf_token);
        } catch (_e) {
            showLoginView();
        }
    }

    async function promptChangeOwnPassword(isFirstAccess = false) {
        const newPw = await uiPrompt({
            title: isFirstAccess
                ? "Primeiro Acesso — Defina sua Senha Pessoal"
                : "Alterar Minha Senha de Acesso",
            message: isFirstAccess
                ? "Você acessou com uma senha temporária gerada pelo instalador. Escolha abaixo uma senha pessoal fácil de lembrar (mínimo 8 caracteres):"
                : "Digite sua nova senha de acesso (mínimo de 8 caracteres):",
            placeholder: "Digite a nova senha (mín. 8 caracteres)",
            inputType: "password",
            confirmText: "Salvar Nova Senha",
            cancelText: isFirstAccess ? "Manter a Atual" : "Cancelar",
            minLength: 8,
        });
        if (!newPw) return;
        try {
            await apiFetch("/api/auth/change-password", {
                method: "POST",
                body: { new_password: newPw },
            });
            if (state.user) {
                state.user.must_change_password = false;
            }
            uiToast("Sua senha pessoal foi salva com sucesso!", "success", "Senha Atualizada");
        } catch (err) {
            uiToast(err.message, "danger", "Erro ao alterar senha");
        }
    }

    function onAuthenticated(user, csrfToken) {
        state.user = user;
        state.csrfToken = csrfToken;
        $("topbar-user-info").textContent = `${user.full_name} (${user.username})`;
        if (user.is_admin) {
            $("btn-open-admin").classList.remove("hidden");
        } else {
            $("btn-open-admin").classList.add("hidden");
        }
        showHomeView();
        if (user.must_change_password) {
            setTimeout(() => promptChangeOwnPassword(true), 350);
        }
    }

    async function loadMyActiveSessions() {
        const container = $("home-sessions-list");
        container.innerHTML = `<div style="color:var(--text-secondary);">Carregando sessões...</div>`;
        try {
            const data = await apiFetch("/api/sessions");
            const list = data.sessions || [];
            if (list.length === 0) {
                container.innerHTML = `
                    <div style="padding:14px;background:var(--bg-subtle);border-radius:6px;color:var(--text-secondary);">
                        Nenhuma consulta PST ativa no momento. Envie um arquivo PST acima para iniciar.
                    </div>`;
                return;
            }
            let html = `<table class="table-clean">
                <thead>
                    <tr>
                        <th>Arquivo</th>
                        <th>Formato</th>
                        <th>Estado</th>
                        <th>Pastas / E-mails</th>
                        <th>Expira por inatividade</th>
                        <th style="text-align:right;">Ações</th>
                    </tr>
                </thead>
                <tbody>`;
            for (const s of list) {
                const canOpen = s.can_open_reader;
                html += `
                    <tr>
                        <td><strong>${escapeHtml(s.display_label)}</strong><br><small style="color:var(--text-secondary);">${formatBytes(s.file_size_bytes)}</small></td>
                        <td>${escapeHtml(s.pst_format || "—")}</td>
                        <td><span class="badge ${canOpen ? "badge-success" : "badge-info"}">${escapeHtml(s.status)} (${s.progress_percent}%)</span></td>
                        <td>${s.processed_folders} pastas / ${s.processed_messages} msgs</td>
                        <td>${formatDateTime(s.idle_expires_at)}</td>
                        <td style="text-align:right;">
                            ${canOpen
                                ? `<button class="btn btn-primary btn-sm" data-open-sess="${escapeHtml(s.session_uuid)}">Abrir Leitor</button>`
                                : `<button class="btn btn-outline btn-sm" data-watch-sess="${escapeHtml(s.session_uuid)}">Ver Progresso</button>`
                            }
                            <button class="btn btn-danger btn-sm" data-close-sess="${escapeHtml(s.session_uuid)}">Encerrar e Limpar</button>
                        </td>
                    </tr>`;
            }
            html += `</tbody></table>`;
            container.innerHTML = html;

            container.querySelectorAll("[data-open-sess]").forEach((btn) => {
                btn.addEventListener("click", () => openReaderView(btn.getAttribute("data-open-sess")));
            });
            container.querySelectorAll("[data-watch-sess]").forEach((btn) => {
                btn.addEventListener("click", () => showProcessingView(btn.getAttribute("data-watch-sess")));
            });
            container.querySelectorAll("[data-close-sess]").forEach((btn) => {
                btn.addEventListener("click", () => closeSpecificSession(btn.getAttribute("data-close-sess")));
            });
        } catch (err) {
            container.innerHTML = `<div class="reading-warning-banner">${escapeHtml(err.message)}</div>`;
        }
    }

    /* ======================================================================
     * UPLOAD DE ARQUIVO PST E PROGRESSO DO PROCESSAMENTO
     * ====================================================================== */
    function uploadPstFile(file) {
        if (!file) return;
        const errBox = $("upload-error-box");
        errBox.classList.add("hidden");

        const progBox = $("upload-progress-box");
        const progBar = $("upload-progress-bar");
        const pctTxt = $("upload-percent-text");
        const stTxt = $("upload-status-text");

        progBox.classList.remove("hidden");
        progBar.style.width = "0%";
        pctTxt.textContent = "0%";
        stTxt.textContent = `Enviando "${file.name}" (${formatBytes(file.size)})...`;
        $("btn-choose-pst").disabled = true;

        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/sessions/upload-stream", true);
        xhr.withCredentials = true;
        xhr.setRequestHeader("Content-Type", "application/octet-stream");
        xhr.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
        if (state.csrfToken) {
            xhr.setRequestHeader("X-CSRF-Token", state.csrfToken);
        }

        xhr.upload.onprogress = function (evt) {
            if (evt.lengthComputable) {
                const pct = Math.round((evt.loaded / evt.total) * 100);
                progBar.style.width = pct + "%";
                pctTxt.textContent = pct + "%";
                if (pct >= 100) {
                    stTxt.textContent = "Validando assinatura binária (!BDN) e calculando SHA-256 no servidor...";
                }
            }
        };

        xhr.onload = function () {
            $("btn-choose-pst").disabled = false;
            progBox.classList.add("hidden");
            let resp = null;
            try {
                resp = JSON.parse(xhr.responseText);
            } catch (_e) {
                resp = { detail: xhr.responseText };
            }

            if (xhr.status >= 200 && xhr.status < 300 && resp.session) {
                state.currentSessionData = resp.session;
                updateTopbarSessionBadges(resp.session);
                showProcessingView(resp.session.session_uuid);
            } else {
                errBox.textContent = (resp && resp.detail) ? resp.detail : `Falha no envio (HTTP ${xhr.status}).`;
                errBox.classList.remove("hidden");
            }
        };

        xhr.onerror = function () {
            $("btn-choose-pst").disabled = false;
            progBox.classList.add("hidden");
            errBox.textContent = "Erro de rede durante o envio do arquivo PST. Os dados parciais foram descartados.";
            errBox.classList.remove("hidden");
        };

        xhr.send(file);
    }

    async function pollProcessingStatus() {
        if (!state.currentSessionUuid) return;
        try {
            const s = await apiFetch(`/api/sessions/${state.currentSessionUuid}`);
            state.currentSessionData = s;
            updateTopbarSessionBadges(s);

            $("proc-title").textContent = `Processando: ${s.display_label}`;
            $("proc-stage").textContent = s.current_stage || s.status;
            $("proc-status-badge").textContent = s.status;
            $("proc-progress-bar").style.width = `${s.progress_percent}%`;
            $("proc-percent-label").textContent = `${s.progress_percent}%`;
            $("proc-format-hash").textContent = `Formato: ${s.pst_format || "—"} | SHA-256: ${(s.file_sha256 || "").substring(0, 24)}...`;

            $("proc-stat-folders").textContent = `${s.processed_folders} / ${s.total_folders}`;
            $("proc-stat-messages").textContent = `${s.processed_messages} / ${s.total_messages}`;
            $("proc-stat-attachments").textContent = `${s.processed_attachments}`;
            $("proc-stat-corrupted").textContent = `${s.corrupted_items}`;

            const btnOpen = $("btn-proc-open-reader");
            const hint = $("proc-progressive-hint");

            if (s.status === "READY") {
                stopPolling();
                openReaderView(s.session_uuid);
                return;
            }

            if (s.can_open_reader) {
                btnOpen.classList.remove("hidden");
                hint.textContent = "As primeiras pastas já estão prontas! Você pode abrir o leitor agora enquanto a indexação continua em 2º plano.";
            } else if (s.status === "FAILED") {
                stopPolling();
                hint.textContent = "Ocorreu uma falha ao processar este arquivo PST. Consulte o Diagnóstico.";
            }
        } catch (err) {
            stopPolling();
            showHomeView();
        }
    }

    /* ======================================================================
     * ÁRVORE DE PASTAS (PAINEL ESQUERDO)
     * ====================================================================== */
    async function loadFoldersTree(autoSelectFirst = false) {
        if (!state.currentSessionUuid) return;
        const data = await apiFetch(`/api/sessions/${state.currentSessionUuid}/folders`);
        state.foldersFlat = data.folders || [];
        state.foldersTree = data.tree || [];

        // Expande automaticamente pastas container e primeiros níveis para exibir direto as pastas com e-mails
        if (state.expandedFolderIds.size === 0) {
            for (const f of state.foldersFlat) {
                if (f.depth <= 2 || f.message_count === 0) {
                    state.expandedFolderIds.add(f.id);
                }
            }
        }

        // Popula select de filtro de pastas da pesquisa
        const selFolder = $("filter-folder");
        const prevVal = selFolder.value;
        selFolder.innerHTML = `<option value="">Todas as pastas do PST</option>`;
        for (const f of state.foldersFlat) {
            const opt = document.createElement("option");
            opt.value = String(f.id);
            opt.textContent = `${f.full_path} (${f.message_count})`;
            selFolder.appendChild(opt);
        }
        selFolder.value = prevVal;

        renderFolderTreeDom();

        if (autoSelectFirst && !state.selectedFolderId && state.foldersFlat.length > 0) {
            // Prioriza Caixa de Entrada ou primeira pasta com mensagens
            const inbox = state.foldersFlat.find((f) => f.folder_role === "INBOX" && f.message_count > 0);
            const withMsgs = state.foldersFlat.find((f) => f.message_count > 0);
            const chosen = inbox || withMsgs || state.foldersFlat[0];
            selectFolder(chosen.id);
        }
    }

    function renderFolderTreeDom() {
        const container = $("folder-tree-container");
        if (!state.foldersTree.length) {
            container.innerHTML = `<div style="padding:14px;color:var(--text-secondary);">Nenhuma pasta encontrada.</div>`;
            return;
        }

        function buildList(nodes, level) {
            let html = `<ul class="folder-tree-list">`;
            for (const node of nodes) {
                const hasChildren = node.children && node.children.length > 0;
                const isExpanded = state.expandedFolderIds.has(node.id);
                const isActive = !state.isSearchMode && state.selectedFolderId === node.id;
                const padLeft = 10 + level * 14;
                const icon = getFolderRoleIcon(node.folder_role);

                html += `<li>
                    <div class="folder-node-row ${isActive ? "active" : ""}" style="padding-left:${padLeft}px;" data-folder-id="${node.id}" title="${escapeHtml(node.full_path)}">
                        <span class="folder-toggle-btn" data-toggle-folder="${hasChildren ? node.id : ""}">
                            ${hasChildren ? (isExpanded ? "▾" : "▸") : ""}
                        </span>
                        <span>${icon}</span>
                        <span class="folder-name-label">${escapeHtml(node.name)}</span>
                        ${node.message_count > 0 ? `<span class="folder-count-badge">${node.message_count}</span>` : ""}
                    </div>
                    ${hasChildren && isExpanded ? buildList(node.children, level + 1) : ""}
                </li>`;
            }
            html += `</ul>`;
            return html;
        }

        container.innerHTML = buildList(state.foldersTree, 0);

        container.querySelectorAll("[data-toggle-folder]").forEach((el) => {
            const fid = Number(el.getAttribute("data-toggle-folder"));
            if (!fid) return;
            el.addEventListener("click", (ev) => {
                ev.stopPropagation();
                if (state.expandedFolderIds.has(fid)) {
                    state.expandedFolderIds.delete(fid);
                } else {
                    state.expandedFolderIds.add(fid);
                }
                renderFolderTreeDom();
            });
        });

        container.querySelectorAll("[data-folder-id]").forEach((row) => {
            row.addEventListener("click", () => {
                const fid = Number(row.getAttribute("data-folder-id"));
                selectFolder(fid);
            });
        });
    }

    async function selectFolder(folderId, page = 1) {
        state.isSearchMode = false;
        state.selectedFolderId = folderId;
        state.currentPage = page;
        $("btn-search-clear").classList.add("hidden");
        renderFolderTreeDom();
        await loadFolderMessagesPage();
    }

    /* ======================================================================
     * LISTA PAGINADA DE MENSAGENS E RESULTADOS DE PESQUISA (PAINEL CENTRAL)
     * ====================================================================== */
    async function loadFolderMessagesPage() {
        if (!state.currentSessionUuid || !state.selectedFolderId) return;
        const listEl = $("message-list-scroll");
        listEl.innerHTML = `<div style="padding:18px;color:var(--text-secondary);">Carregando mensagens...</div>`;

        try {
            const url = `/api/sessions/${state.currentSessionUuid}/folders/${state.selectedFolderId}/messages?page=${state.currentPage}&page_size=${state.pageSize}&sort_by=${encodeURIComponent(state.sortBy)}`;
            const data = await apiFetch(url);

            $("msg-list-title").textContent = data.folder ? data.folder.name : "Mensagens";
            state.totalPages = data.total_pages || 1;
            renderMessagesListDom(data.items || [], data.total || 0);
        } catch (err) {
            listEl.innerHTML = `<div class="reading-warning-banner" style="margin:12px;">${escapeHtml(err.message)}</div>`;
        }
    }

    async function executeGlobalSearch(page = 1) {
        if (!state.currentSessionUuid) return;
        state.isSearchMode = true;
        state.currentPage = page;
        renderFolderTreeDom();

        const q = $("global-search-input").value.trim();
        const sender = $("filter-sender").value.trim();
        const recipient = $("filter-recipient").value.trim();
        const folderId = $("filter-folder").value;
        const dateFrom = $("filter-date-from").value;
        const dateTo = $("filter-date-to").value;
        const hasAtt = $("filter-has-attachments").value;

        const params = new URLSearchParams();
        params.set("page", String(state.currentPage));
        params.set("page_size", String(state.pageSize));
        if (q) params.set("q", q);
        if (sender) params.set("sender", sender);
        if (recipient) params.set("recipient", recipient);
        if (folderId) params.set("folder_id", folderId);
        if (dateFrom) params.set("date_from", dateFrom);
        if (dateTo) params.set("date_to", dateTo);
        if (hasAtt !== "") params.set("has_attachments", hasAtt);

        $("btn-search-clear").classList.remove("hidden");
        const listEl = $("message-list-scroll");
        listEl.innerHTML = `<div style="padding:18px;color:var(--text-secondary);">Pesquisando em todo o PST...</div>`;

        try {
            const data = await apiFetch(`/api/sessions/${state.currentSessionUuid}/search?${params.toString()}`);
            $("msg-list-title").textContent = q ? `Pesquisa: "${q}"` : "Resultados Filtrados";
            state.totalPages = data.total_pages || 1;
            renderMessagesListDom(data.items || [], data.total || 0);
        } catch (err) {
            listEl.innerHTML = `<div class="reading-warning-banner" style="margin:12px;">Erro ao pesquisar: ${escapeHtml(err.message)}</div>`;
        }
    }

    function renderMessagesListDom(items, totalCount) {
        const listEl = $("message-list-scroll");
        $("msg-page-info").textContent = `Página ${state.currentPage} de ${state.totalPages} (${totalCount} itens)`;
        $("btn-page-prev").disabled = state.currentPage <= 1;
        $("btn-page-next").disabled = state.currentPage >= state.totalPages;

        if (!items.length) {
            listEl.innerHTML = `
                <div style="padding:32px 18px;text-align:center;color:var(--text-muted);">
                    Nenhuma mensagem encontrada para os critérios selecionados.
                </div>`;
            return;
        }

        let html = "";
        for (const m of items) {
            const isSelected = state.selectedMessageId === m.id;
            const senderDisplay = m.sender_name || m.sender_email || "Remetente desconhecido";
            const initials = getSenderInitials(m.sender_name, m.sender_email);
            const dateStr = formatDateTime(m.received_at || m.sent_at);

            let badgesHtml = "";
            if (m.importance === 2) {
                badgesHtml += `<span class="badge badge-danger" title="Alta importância">!</span>`;
            } else if (m.importance === 0) {
                badgesHtml += `<span class="badge badge-info" title="Baixa importância">↓</span>`;
            }
            if (m.has_attachments) {
                badgesHtml += `<span title="${m.attachment_count} anexo(s)" style="display:inline-flex;align-items:center;gap:2px;color:var(--text-secondary);">${SVG_ICONS.paperclip}${m.attachment_count > 1 ? `<small>${m.attachment_count}</small>` : ""}</span>`;
            }

            const folderPill = state.isSearchMode && m.folder_name
                ? `<span class="badge badge-info" style="font-size:10.5px;margin-right:4px;">${escapeHtml(m.folder_name)}</span>`
                : "";

            html += `
                <div class="message-item ${isSelected ? "active" : ""}" data-msg-id="${m.id}">
                    <div class="msg-avatar">${escapeHtml(initials)}</div>
                    <div class="msg-item-body">
                        <div class="msg-row-top">
                            <span class="msg-sender">${escapeHtml(senderDisplay)}</span>
                            <span class="msg-date">${escapeHtml(dateStr)}</span>
                        </div>
                        <div class="msg-subject-row">
                            ${badgesHtml}
                            <span class="msg-subject">${escapeHtml(m.subject)}</span>
                        </div>
                        <div class="msg-snippet">
                            ${folderPill}${escapeHtml(m.snippet || "")}
                        </div>
                    </div>
                </div>`;
        }
        listEl.innerHTML = html;

        listEl.querySelectorAll("[data-msg-id]").forEach((itemEl) => {
            itemEl.addEventListener("click", () => {
                const mid = Number(itemEl.getAttribute("data-msg-id"));
                openMessageDetail(mid);
            });
        });
    }

    /* ======================================================================
     * PAINEL DE LEITURA DA MENSAGEM (PAINEL DIREITO)
     * ====================================================================== */
    function resetReadingPane() {
        state.selectedMessageId = null;
        state.selectedMessageDetail = null;
        $("reading-empty-state").classList.remove("hidden");
        $("reading-content-wrap").classList.add("hidden");
        $("btn-msg-print").disabled = true;
        $("btn-msg-export-eml").disabled = true;
        $("btn-msg-export-txt").disabled = true;
    }

    async function openMessageDetail(messageId) {
        if (!state.currentSessionUuid) return;
        state.selectedMessageId = messageId;

        document.querySelectorAll(".message-item").forEach((el) => {
            el.classList.toggle("active", Number(el.getAttribute("data-msg-id")) === messageId);
        });

        const msg = await apiFetch(`/api/sessions/${state.currentSessionUuid}/messages/${messageId}`);
        state.selectedMessageDetail = msg;

        $("reading-empty-state").classList.add("hidden");
        $("reading-content-wrap").classList.remove("hidden");
        $("btn-msg-print").disabled = false;
        $("btn-msg-export-eml").disabled = false;
        $("btn-msg-export-txt").disabled = false;

        $("read-subject").textContent = msg.subject || "(Sem assunto)";

        const fromParts = [];
        if (msg.sender_name) fromParts.push(msg.sender_name);
        if (msg.sender_email) fromParts.push(`<${msg.sender_email}>`);
        $("read-from").textContent = fromParts.join(" ") || "Não informado";

        $("read-to").textContent = msg.recipients_to || "—";

        if (msg.recipients_cc) {
            $("read-cc-label").classList.remove("hidden");
            $("read-cc").classList.remove("hidden");
            $("read-cc").textContent = msg.recipients_cc;
        } else {
            $("read-cc-label").classList.add("hidden");
            $("read-cc").classList.add("hidden");
        }

        if (msg.recipients_bcc) {
            $("read-bcc-label").classList.remove("hidden");
            $("read-bcc").classList.remove("hidden");
            $("read-bcc").textContent = msg.recipients_bcc;
        } else {
            $("read-bcc-label").classList.add("hidden");
            $("read-bcc").classList.add("hidden");
        }

        $("read-date").textContent = `${formatDateTime(msg.received_at || msg.sent_at)} (${formatBytes(msg.size_bytes)})`;
        $("read-folder").textContent = msg.folder ? msg.folder.full_path : "—";

        const warnEl = $("read-warnings-banner");
        warnEl.classList.add("hidden");

        // Anexos
        const attBar = $("read-attachments-bar");
        const atts = msg.attachments || [];
        if (atts.length > 0) {
            attBar.classList.remove("hidden");
            attBar.innerHTML = atts.map((a) => `
                <div class="attachment-chip">
                    <span style="color:var(--primary);display:inline-flex;">${SVG_ICONS.paperclip}</span>
                    <div>
                        <div class="attachment-chip-name" title="${escapeHtml(a.original_filename)}">${escapeHtml(a.original_filename)}</div>
                        <div class="attachment-chip-size">${formatBytes(a.size_bytes)} • ${escapeHtml(a.extraction_status)}</div>
                    </div>
                    <button type="button" class="btn btn-outline btn-sm" data-preview-att="${a.id}">Abrir / Ler</button>
                    <a class="btn btn-primary btn-sm" href="/api/sessions/${encodeURIComponent(state.currentSessionUuid)}/attachments/${a.id}/download" download>Baixar</a>
                </div>
            `).join("");

            attBar.querySelectorAll("[data-preview-att]").forEach((btn) => {
                btn.addEventListener("click", () => {
                    openAttachmentModal(Number(btn.getAttribute("data-preview-att")));
                });
            });
        } else {
            attBar.classList.add("hidden");
            attBar.innerHTML = "";
        }

        // Seleciona automaticamente o melhor modo de exibição (HTML Sanitizado quando disponível)
        state.bodyViewMode = msg.body_html_sanitized ? "html" : "plain";
        renderMessageBodyMode();
    }

    function renderMessageBodyMode() {
        const msg = state.selectedMessageDetail;
        if (!msg) return;

        const iframeEl = $("read-body-iframe");
        const preEl = $("read-body-plain");

        $("btn-view-mode-html").classList.toggle("btn-primary", state.bodyViewMode === "html");
        $("btn-view-mode-plain").classList.toggle("btn-primary", state.bodyViewMode === "plain");
        $("btn-view-mode-raw").classList.toggle("btn-primary", state.bodyViewMode === "raw");

        if (state.bodyViewMode === "html" && msg.body_html_sanitized) {
            preEl.classList.add("hidden");
            iframeEl.classList.remove("hidden");
            const safeDoc = `<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
                body { font-family: "Segoe UI", Arial, sans-serif; font-size: 14px; color: #242424; margin: 16px 20px; line-height: 1.5; word-wrap: break-word; }
                img { max-width: 100%; height: auto; }
                a { color: #0f6cbd; }
                blockquote { border-left: 3px solid #c8c6c4; margin-left: 0; padding-left: 12px; color: #616161; }
            </style></head><body>${msg.body_html_sanitized}</body></html>`;
            iframeEl.srcdoc = safeDoc;
        } else if (state.bodyViewMode === "raw") {
            iframeEl.classList.add("hidden");
            preEl.classList.remove("hidden");
            const hdrs = msg.transport_headers || "(Mensagem MAPI interna sem cabeçalhos SMTP de transporte)";
            preEl.textContent = `=== CABEÇALHOS DE TRANSPORTE ORIGINAIS ===\n${hdrs}\n\n=== TEXTO ORIGINAL EXTRAÍDO ===\n${msg.body_plain || "(Vazio)"}`;
        } else {
            iframeEl.classList.add("hidden");
            preEl.classList.remove("hidden");
            preEl.textContent = msg.body_plain || "(Mensagem sem corpo textual)";
        }
    }

    /* ======================================================================
     * VISUALIZAÇÃO DE ANEXOS, DIAGNÓSTICO E ADMINISTRAÇÃO
     * ====================================================================== */
    async function openAttachmentModal(attachmentId) {
        if (!state.currentSessionUuid) return;
        const modal = $("modal-attachment");
        const body = $("att-modal-body");
        modal.classList.remove("hidden");
        body.innerHTML = `<p>Carregando metadados e conteúdo do anexo...</p>`;

        try {
            const meta = await apiFetch(`/api/sessions/${state.currentSessionUuid}/attachments/${attachmentId}/metadata`);
            $("att-modal-title").textContent = `Anexo: ${meta.original_filename}`;
            const dlUrl = `/api/sessions/${encodeURIComponent(state.currentSessionUuid)}/attachments/${attachmentId}/download`;
            const viewUrl = `/api/sessions/${encodeURIComponent(state.currentSessionUuid)}/attachments/${attachmentId}/view`;
            const printUrl = `/api/sessions/${encodeURIComponent(state.currentSessionUuid)}/attachments/${attachmentId}/print`;

            $("btn-att-modal-download").href = dlUrl;
            $("btn-att-modal-print").onclick = () => window.open(printUrl, "_blank", "noopener");

            let previewHtml = "";
            if (meta.extraction_status === "ENCRYPTED_OR_PASSWORD") {
                previewHtml = `<div class="reading-warning-banner"><strong>Arquivo protegido por senha ou criptografado:</strong> Não é possível extrair o conteúdo interno automaticamente. Você pode baixar o arquivo original caso possua a senha.</div>`;
            } else if (meta.can_view_native_inline && meta.mime_type === "application/pdf") {
                previewHtml = `<iframe src="${viewUrl}" style="width:100%;height:420px;border:1px solid var(--border-color);border-radius:4px;"></iframe>`;
            } else if (meta.can_view_native_inline && meta.mime_type.startsWith("image/")) {
                previewHtml = `<div style="text-align:center;padding:12px;"><img src="${viewUrl}" style="max-width:100%;max-height:420px;border:1px solid var(--border-color);"></div>`;
            }

            if (meta.has_extracted_text) {
                previewHtml += `
                    <h4 style="margin:14px 0 6px 0;">Conteúdo Textual Extraído (Pesquisável):</h4>
                    <pre style="background:var(--bg-subtle);border:1px solid var(--border-color);padding:12px;border-radius:4px;max-height:340px;overflow-y:auto;white-space:pre-wrap;font-size:12.5px;">${escapeHtml(meta.extracted_text)}</pre>`;
            } else if (!previewHtml) {
                previewHtml = `<div style="padding:16px;background:var(--bg-subtle);border-radius:6px;">${escapeHtml(meta.extraction_status_description)}</div>`;
            }

            body.innerHTML = `
                <table class="table-clean" style="margin-bottom:14px;">
                    <tr><th>Nome Original:</th><td>${escapeHtml(meta.original_filename)}</td><th>Tamanho:</th><td>${formatBytes(meta.size_bytes)}</td></tr>
                    <tr><th>Tipo MIME:</th><td>${escapeHtml(meta.mime_type)}</td><th>Status:</th><td><span class="badge badge-info">${escapeHtml(meta.extraction_status)}</span></td></tr>
                    <tr><th>Hash SHA-256:</th><td colspan="3" style="font-family:monospace;font-size:12px;">${escapeHtml(meta.sha256 || "—")}</td></tr>
                </table>
                ${previewHtml}`;
        } catch (err) {
            body.innerHTML = `<div class="reading-warning-banner">${escapeHtml(err.message)}</div>`;
        }
    }

    async function openDiagnosticsModal() {
        if (!state.currentSessionUuid) return;
        const modal = $("modal-diagnostics");
        const body = $("modal-diagnostics-body");
        modal.classList.remove("hidden");
        body.innerHTML = `<p>Carregando diagnóstico da sessão...</p>`;

        try {
            const s = await apiFetch(`/api/sessions/${state.currentSessionUuid}/diagnostics`);
            const d = s.diagnostics || {};
            const warnings = d.warnings || [];
            body.innerHTML = `
                <table class="table-clean" style="margin-bottom:16px;">
                    <tr><th>Arquivo em Consulta:</th><td>${escapeHtml(s.display_label)}</td><th>Estado:</th><td><span class="badge badge-info">${escapeHtml(s.status)}</span></td></tr>
                    <tr><th>Formato Binário PST:</th><td>${escapeHtml(s.pst_format || "—")}</td><th>Motor de Leitura:</th><td>${escapeHtml(d.engine || "pypff")}</td></tr>
                    <tr><th>Tamanho Original:</th><td>${formatBytes(s.file_size_bytes)}</td><th>Uso Total Temporário:</th><td>${formatBytes(s.disk_usage_bytes)}</td></tr>
                    <tr><th>Hash SHA-256:</th><td colspan="3" style="font-family:monospace;font-size:12px;">${escapeHtml(s.file_sha256 || "—")}</td></tr>
                    <tr><th>Pastas Extraídas:</th><td>${s.processed_folders} / ${s.total_folders}</td><th>Mensagens Extraídas:</th><td>${s.processed_messages} / ${s.total_messages}</td></tr>
                    <tr><th>Anexos Extraídos:</th><td>${s.processed_attachments}</td><th>Itens Corrompidos:</th><td>${s.corrupted_items}</td></tr>
                    <tr><th>Anexos Protegidos por Senha:</th><td>${d.encrypted_attachments || 0}</td><th>Recursos Externos Bloqueados:</th><td>${d.external_resources_blocked || 0}</td></tr>
                </table>
                <h4 style="margin:12px 0 6px 0;">Avisos Técnicos de Extração:</h4>
                ${warnings.length
                    ? `<ul style="font-size:12.5px;padding-left:18px;">${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>`
                    : `<div style="color:var(--success);font-size:13px;">✓ Nenhum erro estrutural ou corrupção detectada nas páginas B-Tree do PST.</div>`
                }`;
        } catch (err) {
            body.innerHTML = `<div class="reading-warning-banner">${escapeHtml(err.message)}</div>`;
        }
    }

    async function closeSpecificSession(sessionUuid) {
        if (!sessionUuid) return;
        const ok = await uiConfirm({
            title: "Fechar Visualização Temporária",
            message: "Deseja encerrar a visualização deste PST aqui no leitor web? A leitura temporária do servidor será limpa (o arquivo .pst original no seu computador/rede continua 100% salvo e intacto).",
            confirmText: "Sim, Fechar Consulta",
            cancelText: "Continuar Lendo",
            variant: "danger",
            icon: SVG_ICONS.trash,
        });
        if (!ok) return;
        try {
            await apiFetch(`/api/sessions/${sessionUuid}/close`, { method: "POST" });
            uiToast("Visualização encerrada no servidor (seu arquivo .pst original permanece intacto no seu PC).", "success", "Consulta Encerrada");
            if (state.currentSessionUuid === sessionUuid) {
                showHomeView();
            } else {
                loadMyActiveSessions();
            }
        } catch (err) {
            await uiAlert({
                title: "Erro ao Encerrar Sessão",
                message: err.message,
                variant: "danger",
                icon: SVG_ICONS.alert,
            });
        }
    }

    /* ======================================================================
     * PAINEL ADMINISTRATIVO (TELAS 12, 13, 14 E 15)
     * ====================================================================== */
    async function openAdminModal(tab = "sessions") {
        $("modal-admin").classList.remove("hidden");
        await renderAdminTab(tab);
    }

    async function renderAdminTab(tab) {
        const body = $("admin-modal-body");
        document.querySelectorAll(".admin-tab-btn").forEach((b) => {
            b.classList.toggle("btn-primary", b.getAttribute("data-tab") === tab);
        });
        body.innerHTML = `<p>Carregando dados administrativos...</p>`;

        try {
            if (tab === "sessions") {
                const data = await apiFetch("/api/admin/sessions");
                const m = data.host_metrics || {};
                let html = `
                    <div class="stats-grid" style="margin-top:0;margin-bottom:16px;">
                        <div class="stat-card"><div class="stat-label">CPU (${m.cpu_count} vCPUs)</div><div class="stat-value">Load: ${m.load_avg_1m}</div></div>
                        <div class="stat-card"><div class="stat-label">RAM Disponível</div><div class="stat-value">${m.mem_available_mb} / ${m.mem_total_mb} MB</div></div>
                        <div class="stat-card"><div class="stat-label">Disco Livre (/srv)</div><div class="stat-value">${m.disk_free_mb} MB</div></div>
                        <div class="stat-card" style="display:flex;align-items:center;justify-content:center;">
                            <button type="button" id="btn-admin-run-cleanup" class="btn btn-danger">${SVG_ICONS.trash} Executar Limpeza Agora</button>
                        </div>
                    </div>
                    <h4 style="margin:10px 0 8px 0;">Estado das Sessões Temporárias</h4>
                    <table class="table-clean" style="margin-bottom:18px;">
                        <thead><tr><th>UUID</th><th>Usuário</th><th>Status</th><th>Uso Disco</th><th>Expira Inatividade</th><th>Expurgado em</th><th>Ação</th></tr></thead>
                        <tbody>
                            ${(data.sessions || []).map((s) => `
                                <tr>
                                    <td style="font-family:monospace;font-size:11.5px;">${escapeHtml(s.session_uuid.substring(0, 12))}...</td>
                                    <td>${escapeHtml(s.owner_username)}</td>
                                    <td><span class="badge ${s.status === "PURGED" ? "badge-info" : "badge-success"}">${escapeHtml(s.status)}</span></td>
                                    <td>${formatBytes(s.disk_usage_bytes)}</td>
                                    <td>${formatDateTime(s.idle_expires_at)}</td>
                                    <td>${formatDateTime(s.purged_at)}</td>
                                    <td>${s.status !== "PURGED" ? `<button class="btn btn-danger btn-sm" data-force-purge="${escapeHtml(s.session_uuid)}">Expurgar</button>` : "—"}</td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                    <h4 style="margin:14px 0 8px 0;">Últimos Eventos de Auditoria (Sem conteúdo sensível)</h4>
                    <table class="table-clean">
                        <thead><tr><th>Data/Hora</th><th>Evento</th><th>Resultado</th><th>Usuário</th><th>IP</th><th>Detalhes</th></tr></thead>
                        <tbody>
                            ${(data.audit_logs || []).slice(0, 25).map((a) => `
                                <tr>
                                    <td>${formatDateTime(a.event_time)}</td>
                                    <td><strong>${escapeHtml(a.event_type)}</strong></td>
                                    <td>${escapeHtml(a.event_result)}</td>
                                    <td>${escapeHtml(a.username || "—")}</td>
                                    <td>${escapeHtml(a.ip_address || "—")}</td>
                                    <td style="font-family:monospace;font-size:11px;">${escapeHtml(JSON.stringify(a.details || {}))}</td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>`;
                body.innerHTML = html;

                $("btn-admin-run-cleanup").addEventListener("click", async () => {
                    const res = await apiFetch("/api/admin/cleanup/run", { method: "POST" });
                    uiToast(
                        `Sessões expurgadas: ${res.purged_sessions.length} • Diretórios órfãos removidos: ${res.orphan_dirs_removed.length}`,
                        "success",
                        "Varredura de Limpeza Concluída"
                    );
                    renderAdminTab("sessions");
                });
                body.querySelectorAll("[data-force-purge]").forEach((btn) => {
                    btn.addEventListener("click", async () => {
                        const uuid = btn.getAttribute("data-force-purge");
                        const ok = await uiConfirm({
                            title: "Forçar Expurgo de Sessão",
                            message: `Deseja expurgar imediatamente a sessão temporária ${uuid.substring(0, 12)}... e remover todos os arquivos de disco?`,
                            confirmText: "Expurgar Agora",
                            cancelText: "Cancelar",
                            variant: "danger",
                            icon: SVG_ICONS.trash,
                        });
                        if (!ok) return;
                        await apiFetch(`/api/admin/sessions/${uuid}/force-purge`, { method: "POST" });
                        uiToast("Sessão expurgada com sucesso.", "success", "Expurgo Administrativo");
                        renderAdminTab("sessions");
                    });
                });

            } else if (tab === "users") {
                const data = await apiFetch("/api/admin/users");
                const currentUserId = state.user ? state.user.id : null;
                body.innerHTML = `
                    <form id="form-admin-new-user" style="background:var(--bg-subtle);padding:14px;border-radius:6px;margin-bottom:16px;display:grid;grid-template-columns:1fr 1fr 1fr auto auto;gap:8px;align-items:end;">
                        <div><label class="form-label">Usuário</label><input type="text" id="new-u-name" class="form-control" required minlength="3"></div>
                        <div><label class="form-label">Nome Completo</label><input type="text" id="new-u-full" class="form-control" required></div>
                        <div><label class="form-label">Senha (mín. 8)</label><input type="password" id="new-u-pass" class="form-control" required minlength="8"></div>
                        <div style="padding-bottom:8px;"><label><input type="checkbox" id="new-u-admin"> Admin</label></div>
                        <button type="submit" class="btn btn-primary">Criar Usuário</button>
                    </form>
                    <table class="table-clean">
                        <thead><tr><th>Usuário</th><th>Nome</th><th>Perfil</th><th>Ativo</th><th>Último Login</th><th style="text-align:right;">Ações</th></tr></thead>
                        <tbody>
                            ${(data.users || []).map((u) => {
                                const isSelf = u.id === currentUserId;
                                return `
                                <tr>
                                    <td><strong>${escapeHtml(u.username)}</strong>${isSelf ? ` <span class="badge badge-info" style="margin-left:4px;">Você</span>` : ""}</td>
                                    <td>${escapeHtml(u.full_name)}</td>
                                    <td>${u.is_admin ? "Administrador" : "Padrão"}</td>
                                    <td>${u.is_active ? "Sim" : "Bloqueado/Inativo"}</td>
                                    <td>${formatDateTime(u.last_login_at)}</td>
                                    <td style="text-align:right;white-space:nowrap;">
                                        ${!isSelf ? `<button class="btn btn-outline btn-sm" data-toggle-u="${u.id}">${u.is_active ? "Desativar" : "Ativar"}</button>` : ""}
                                        <button class="btn btn-outline btn-sm" data-reset-pw="${u.id}">Nova Senha</button>
                                        ${!isSelf ? `<button class="btn btn-danger btn-sm" data-delete-u="${u.id}" data-delete-uname="${escapeHtml(u.username)}">Excluir</button>` : ""}
                                    </td>
                                </tr>`;
                            }).join("")}
                        </tbody>
                    </table>`;

                $("form-admin-new-user").addEventListener("submit", async (ev) => {
                    ev.preventDefault();
                    try {
                        await apiFetch("/api/admin/users", {
                            method: "POST",
                            body: {
                                username: $("new-u-name").value,
                                full_name: $("new-u-full").value,
                                password: $("new-u-pass").value,
                                is_admin: $("new-u-admin").checked,
                            },
                        });
                        uiToast("Novo usuário cadastrado com sucesso.", "success", "Gestão de Usuários");
                        renderAdminTab("users");
                    } catch (err) {
                        uiToast(err.message, "danger", "Erro ao Criar Usuário");
                    }
                });
                body.querySelectorAll("[data-toggle-u]").forEach((btn) => {
                    btn.addEventListener("click", async () => {
                        try {
                            await apiFetch(`/api/admin/users/${btn.getAttribute("data-toggle-u")}/toggle-active`, { method: "POST" });
                            uiToast("Status do usuário atualizado.", "info", "Gestão de Usuários");
                            renderAdminTab("users");
                        } catch (err) {
                            uiToast(err.message, "danger", "Erro na Operação");
                        }
                    });
                });
                body.querySelectorAll("[data-reset-pw]").forEach((btn) => {
                    btn.addEventListener("click", async () => {
                        const pw = await uiPrompt({
                            title: "Redefinir Senha do Usuário",
                            message: "Informe a nova senha para este usuário (mínimo de 8 caracteres):",
                            placeholder: "Digite a nova senha...",
                            inputType: "password",
                            minLength: 8,
                            confirmText: "Atualizar Senha",
                        });
                        if (!pw || pw.length < 8) return;
                        try {
                            await apiFetch(`/api/admin/users/${btn.getAttribute("data-reset-pw")}/reset-password`, {
                                method: "POST",
                                body: { new_password: pw },
                            });
                            uiToast("Senha atualizada e criptografada com Argon2id!", "success", "Segurança");
                        } catch (err) {
                            uiToast(err.message, "danger", "Erro ao Redefinir Senha");
                        }
                    });
                });
                body.querySelectorAll("[data-delete-u]").forEach((btn) => {
                    btn.addEventListener("click", async () => {
                        const uid = btn.getAttribute("data-delete-u");
                        const uname = btn.getAttribute("data-delete-uname") || "";
                        const ok = await uiConfirm({
                            title: "Excluir Conta de Usuário",
                            message: `Deseja excluir permanentemente o usuário "${uname}"? Eventuais sessões PST temporárias abertas por ele serão encerradas e limpas do servidor.`,
                            confirmText: "Sim, Excluir Usuário",
                            cancelText: "Cancelar",
                            variant: "danger",
                            icon: SVG_ICONS.trash,
                        });
                        if (!ok) return;
                        try {
                            await apiFetch(`/api/admin/users/${uid}`, { method: "DELETE" });
                            uiToast(`Usuário "${uname}" excluído com sucesso.`, "success", "Gestão de Usuários");
                            renderAdminTab("users");
                        } catch (err) {
                            await uiAlert({
                                title: "Erro ao Excluir Usuário",
                                message: err.message,
                                variant: "danger",
                                icon: SVG_ICONS.alert,
                            });
                        }
                    });
                });

            } else if (tab === "settings") {
                const data = await apiFetch("/api/admin/settings");
                body.innerHTML = `
                    <form id="form-admin-settings">
                        <table class="table-clean" style="margin-bottom:14px;">
                            <thead><tr><th>Parâmetro</th><th>Valor</th><th>Descrição</th></tr></thead>
                            <tbody>
                                ${(data.settings || []).map((s) => `
                                    <tr>
                                        <td><code>${escapeHtml(s.key)}</code></td>
                                        <td><input type="number" class="form-control setting-input" data-skey="${escapeHtml(s.key)}" value="${escapeHtml(s.value)}" style="width:130px;"></td>
                                        <td>${escapeHtml(s.description)}</td>
                                    </tr>
                                `).join("")}
                            </tbody>
                        </table>
                        <div style="text-align:right;">
                            <button type="submit" class="btn btn-primary">Salvar Configurações</button>
                        </div>
                    </form>`;

                $("form-admin-settings").addEventListener("submit", async (ev) => {
                    ev.preventDefault();
                    const payload = {};
                    body.querySelectorAll(".setting-input").forEach((inp) => {
                        payload[inp.getAttribute("data-skey")] = inp.value;
                    });
                    await apiFetch("/api/admin/settings", { method: "PUT", body: { settings: payload } });
                    uiToast("Configurações administrativas salvas com sucesso!", "success", "Configurações");
                });
            }
        } catch (err) {
            body.innerHTML = `<div class="reading-warning-banner">${escapeHtml(err.message)}</div>`;
        }
    }

    /* ======================================================================
     * EVENT LISTENERS GLOBAIS
     * ====================================================================== */
    document.addEventListener("DOMContentLoaded", () => {
        $("form-login").addEventListener("submit", async (ev) => {
            ev.preventDefault();
            const btn = $("btn-login-submit");
            btn.disabled = true;
            try {
                const data = await apiFetch("/api/auth/login", {
                    method: "POST",
                    body: {
                        username: $("login-username").value,
                        password: $("login-password").value,
                    },
                });
                $("login-password").value = "";
                onAuthenticated(data.user, data.csrf_token);
            } catch (err) {
                showLoginView(err.message);
            } finally {
                btn.disabled = false;
            }
        });

        $("btn-logout").addEventListener("click", async () => {
            const ok = await uiConfirm({
                title: "Sair do PST Viewer",
                message: "Deseja sair do sistema? A visualização temporária aberta no leitor web será fechada (o seu arquivo .pst original no computador ou na rede permanece 100% intacto).",
                confirmText: "Sair do Sistema",
                cancelText: "Continuar Conectado",
                variant: "primary",
                icon: SVG_ICONS.logout,
            });
            if (!ok) return;
            try {
                await apiFetch("/api/auth/logout", { method: "POST" });
            } catch (_e) {}
            showLoginView("Você saiu do sistema e os dados temporários foram eliminados.");
        });

        $("btn-go-home").addEventListener("click", () => {
            if (state.user) showHomeView();
        });

        $("btn-close-session").addEventListener("click", () => {
            if (state.currentSessionUuid) {
                closeSpecificSession(state.currentSessionUuid);
            }
        });

        $("btn-choose-pst").addEventListener("click", () => $("input-pst-file").click());
        $("input-pst-file").addEventListener("change", (ev) => {
            if (ev.target.files && ev.target.files[0]) {
                uploadPstFile(ev.target.files[0]);
                ev.target.value = "";
            }
        });

        $("btn-refresh-sessions").addEventListener("click", loadMyActiveSessions);

        $("btn-proc-open-reader").addEventListener("click", () => {
            if (state.currentSessionUuid) openReaderView(state.currentSessionUuid);
        });
        $("btn-proc-diagnostics").addEventListener("click", openDiagnosticsModal);
        $("btn-reader-diagnostics").addEventListener("click", openDiagnosticsModal);
        $("btn-proc-cancel").addEventListener("click", async () => {
            if (!state.currentSessionUuid) return;
            const ok = await uiConfirm({
                title: "Cancelar Processamento PST",
                message: "Deseja interromper a extração em andamento e eliminar imediatamente todos os arquivos parciais?",
                confirmText: "Sim, Cancelar e Limpar",
                cancelText: "Continuar Processando",
                variant: "danger",
                icon: SVG_ICONS.alert,
            });
            if (!ok) return;
            await apiFetch(`/api/sessions/${state.currentSessionUuid}/cancel`, { method: "POST" });
            uiToast("Processamento cancelado e dados parciais removidos.", "info", "Cancelado");
            showHomeView();
        });

        $("btn-toggle-folders-pane").addEventListener("click", () => {
            $("pane-folders").classList.toggle("hidden");
        });
        $("btn-reload-folders").addEventListener("click", () => loadFoldersTree(false));

        $("msg-sort-select").addEventListener("change", (ev) => {
            state.sortBy = ev.target.value;
            state.currentPage = 1;
            if (!state.isSearchMode) loadFolderMessagesPage();
        });

        $("btn-page-prev").addEventListener("click", () => {
            if (state.currentPage > 1) {
                state.currentPage--;
                state.isSearchMode ? executeGlobalSearch(state.currentPage) : loadFolderMessagesPage();
            }
        });
        $("btn-page-next").addEventListener("click", () => {
            if (state.currentPage < state.totalPages) {
                state.currentPage++;
                state.isSearchMode ? executeGlobalSearch(state.currentPage) : loadFolderMessagesPage();
            }
        });

        // Pesquisa Global e Filtros
        $("btn-search-run").addEventListener("click", () => executeGlobalSearch(1));
        $("global-search-input").addEventListener("keydown", (ev) => {
            if (ev.key === "Enter") executeGlobalSearch(1);
        });
        $("btn-search-filters-toggle").addEventListener("click", () => {
            $("search-filters-drawer").classList.toggle("hidden");
        });
        $("btn-apply-filters").addEventListener("click", () => executeGlobalSearch(1));
        $("btn-reset-filters").addEventListener("click", () => {
            $("filter-sender").value = "";
            $("filter-recipient").value = "";
            $("filter-folder").value = "";
            $("filter-date-from").value = "";
            $("filter-date-to").value = "";
            $("filter-has-attachments").value = "";
        });
        $("btn-search-clear").addEventListener("click", () => {
            $("global-search-input").value = "";
            $("btn-reset-filters").click();
            $("search-filters-drawer").classList.add("hidden");
            if (state.selectedFolderId) {
                selectFolder(state.selectedFolderId, 1);
            }
        });

        // Modos de visualização do corpo da mensagem
        $("btn-view-mode-html").addEventListener("click", () => {
            state.bodyViewMode = "html";
            renderMessageBodyMode();
        });
        $("btn-view-mode-plain").addEventListener("click", () => {
            state.bodyViewMode = "plain";
            renderMessageBodyMode();
        });
        $("btn-view-mode-raw").addEventListener("click", () => {
            state.bodyViewMode = "raw";
            renderMessageBodyMode();
        });

        // Impressão e Exportação EML / TXT
        $("btn-msg-print").addEventListener("click", () => {
            if (!state.currentSessionUuid || !state.selectedMessageId) return;
            window.open(`/api/sessions/${state.currentSessionUuid}/messages/${state.selectedMessageId}/print`, "_blank", "noopener");
        });
        $("btn-msg-export-eml").addEventListener("click", () => {
            if (!state.currentSessionUuid || !state.selectedMessageId) return;
            window.location.href = `/api/sessions/${state.currentSessionUuid}/messages/${state.selectedMessageId}/export.eml`;
        });
        $("btn-msg-export-txt").addEventListener("click", () => {
            if (!state.currentSessionUuid || !state.selectedMessageId) return;
            window.location.href = `/api/sessions/${state.currentSessionUuid}/messages/${state.selectedMessageId}/export.txt`;
        });

        // Sobre / Como Funciona / Créditos
        ["btn-login-about", "btn-open-about", "btn-home-about"].forEach((id) => {
            const el = $(id);
            if (el) {
                el.addEventListener("click", () => {
                    $("modal-about").classList.remove("hidden");
                });
            }
        });

        // Administração
        $("btn-open-admin").addEventListener("click", () => openAdminModal("sessions"));
        if ($("btn-change-password")) {
            $("btn-change-password").addEventListener("click", () => promptChangeOwnPassword(false));
        }
        document.querySelectorAll(".admin-tab-btn").forEach((btn) => {
            btn.addEventListener("click", () => renderAdminTab(btn.getAttribute("data-tab")));
        });

        // Fechamento de modais
        document.querySelectorAll("[data-close-modal]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const target = btn.getAttribute("data-close-modal");
                $(target).classList.add("hidden");
            });
        });

        checkCurrentSession();
    });
})();

