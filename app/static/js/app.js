/**
 * PST Viewer - Aplicação Frontend Estilo Microsoft Outlook
 * 100% em Português Brasileiro, com proteção CSRF, paginação sob demanda e iframe sandbox.
 */

(function () {
    "use strict";

    const state = {
        lang: localStorage.getItem("pstviewer_lang") || ((navigator.language || "").toLowerCase().startsWith("en") ? "en" : "pt"),
        user: null,
        csrfToken: null,
        sessionToken: localStorage.getItem("pstviewer_token") || null,
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
        simFolder: "inbox",
        simSelectedId: 1,
        simQuery: "",
    };

    const I18N = {
        pt: {
            "nav.about_system": "Sobre o sistema",
            "nav.about": "Sobre",
            "nav.back_home": "Voltar à Central de Consultas",
            "nav.indexing": "Indexando...",
            "nav.change_pw": "Alterar Senha",
            "nav.change_pw_title": "Alterar sua senha de acesso",
            "nav.admin": "Administração",
            "nav.close_session": "Fechar Consulta",
            "nav.close_session_title": "Fechar a visualização atual no leitor web (seu arquivo .pst original permanece intacto no seu PC)",
            "nav.logout": "Sair",
            "nav.logout_title": "Sair do sistema",
            "login.tagline": "Abra, pesquise e leia seus arquivos de e-mail do Outlook com facilidade.",
            "login.username_label": "Usuário",
            "login.username_placeholder": "Digite seu usuário",
            "login.password_label": "Senha",
            "login.password_placeholder": "Digite sua senha",
            "login.submit_btn": "Entrar",
            "login.by": "Por",
            "sim.badge": "SIMULADOR INTERATIVO • OUTLOOK 365 WEB",
            "sim.heading": "Veja como é simples consultar seus backups de e-mail no navegador",
            "sim.subtitle": "Clique nas pastas ou nas mensagens fictícias abaixo para testar o leitor antes mesmo de entrar.",
            "sim.search_placeholder": "Experimente pesquisar no simulador (ex: orçamento, contrato, nuvem)...",
            "sim.demo_mode": "Modo Demonstração",
            "sim.ribbon_read": "Leitura Instantânea",
            "sim.safe_pill": "✔ Arquivo original preservado",
            "search.placeholder": "Pesquisar em todo o PST (assunto, corpo, remetente, destinatários e anexos)...",
            "search.btn": "Pesquisar",
            "search.filters": "Filtros",
            "search.filters_title": "Filtros avançados de pesquisa",
            "search.clear": "Limpar",
            "home.open_title": "Abrir Arquivo de E-mails (.PST)",
            "home.drop_heading": "Escolha um arquivo do Outlook (.pst) no seu computador",
            "home.drop_sub": "Visualize suas pastas, leia suas mensagens, pesquise por palavras e abra seus anexos diretamente no navegador.",
            "home.choose_btn": "Escolher Arquivo .PST",
            "home.assurance": "<strong>Fique tranquilo:</strong> O arquivo original salvo no seu computador ou na rede <strong>não sofre nenhuma alteração</strong>.",
            "home.active_files": "Arquivos Abertos",
            "home.refresh": "Atualizar",
            "home.no_sessions": "Nenhuma consulta PST ativa no momento. Escolha um arquivo .PST acima para iniciar.",
            "proc.title": "Processando arquivo PST...",
            "proc.stage": "Iniciando validação...",
            "proc.folders": "Pastas Mapeadas",
            "proc.messages": "Mensagens Extraídas",
            "proc.attachments": "Anexos Processados",
            "proc.corrupted": "Itens Corrompidos / Avisos",
            "proc.hint": "Aguardando indexação inicial das pastas para liberar o leitor...",
            "proc.diagnostics": "Ver Diagnóstico",
            "proc.cancel": "Cancelar Leitura",
            "proc.open_reader": "Abrir Leitor de E-mails",
            "filter.sender": "Remetente",
            "filter.recipient": "Destinatário (Para/CC/CCO)",
            "filter.name_email": "Nome ou e-mail",
            "filter.folder": "Pasta",
            "filter.all_folders": "Todas as pastas do PST",
            "filter.date_from": "Período (De)",
            "filter.date_to": "Período (Até)",
            "filter.attachments": "Presença de Anexos",
            "filter.all_msgs": "Todas as mensagens",
            "filter.with_att": "Somente com anexos",
            "filter.without_att": "Sem anexos",
            "filter.apply": "Aplicar",
            "reader.folders": "Pastas",
            "reader.diagnostics": "Diagnóstico do PST",
            "reader.partial_notice": "Indexação em andamento: novas mensagens podem surgir",
            "reader.print": "Imprimir E-mail",
            "reader.save_eml": "Salvar EML",
            "reader.export_txt": "Exportar TXT",
            "reader.folders_pane_title": "Pastas do Arquivo PST",
            "reader.messages": "Mensagens",
            "reader.prev_page": "◀ Anterior",
            "reader.next_page": "Próxima ▶",
            "reader.empty_title": "Selecione uma mensagem na lista para ler seu conteúdo",
            "reader.empty_sub": "Os anexos, cabeçalhos e opções de impressão aparecerão neste painel.",
            "reader.mode_html": "Formatado",
            "reader.mode_plain": "Texto",
            "reader.mode_headers": "Cabeçalhos",
            "reader.from": "De:",
            "reader.to": "Para:",
            "reader.date": "Data/Hora:",
            "reader.folder": "Pasta PST:",
            "sort.newest": "Mais recentes",
            "sort.oldest": "Mais antigas",
            "sort.sender": "Remetente (A-Z)",
            "sort.subject": "Assunto (A-Z)",
            "sort.size": "Maior tamanho",
            "diag.title": "Diagnóstico Técnico do Arquivo PST",
            "att.title": "Visualizar Anexo",
            "att.print": "Imprimir Anexo",
            "att.download": "Baixar Anexo",
            "admin.title": "Administração do PST Viewer",
            "admin.tab_sessions": "Sessões & Limpeza",
            "admin.tab_users": "Usuários",
            "admin.tab_settings": "Configurações & Limites",
            "common.close_x": "Fechar ✕",
            "common.close": "Fechar",
            "common.got_it": "Entendi",
            "about.badge_safe": "100% Seguro & Web",
            "about.hero_sub": "Plataforma moderna para abertura, pesquisa rápida e leitura de arquivos de e-mail do Microsoft Outlook (.pst)",
            "about.tab_story": "Propósito & Como Funciona",
            "about.tab_privacy": "Preservação dos Seus Arquivos",
            "about.tab_author": "Autoria & Recursos",
            "about.story_title": "Por que o PST Viewer foi criado?",
            "about.story_p1": "O <strong>PST Viewer</strong> nasceu da necessidade prática de consultar arquivos de backup do Microsoft Outlook (<code>.pst</code>) dos departamentos de forma rápida e sem complicação.",
            "about.story_p2": "Após os backups periódicos de e-mail para liberar espaço nos servidores principais, localizar uma mensagem ou contrato antigo dentro de arquivos <code>.pst</code> exigia configurações pesadas no computador ou licenças caras de softwares pagos. Com esta plataforma, basta abrir o navegador para ler, pesquisar e imprimir qualquer e-mail em segundos.",
            "about.steps_heading": "Como usar em 3 passos simples",
            "about.step1_title": "Escolha seu arquivo .PST",
            "about.step1_desc": "Selecione o arquivo no seu computador ou na pasta da rede. Apenas as pastas reais do seu backup são exibidas, sem pastas vazias desnecessárias.",
            "about.step2_title": "Pesquise e Leia no Navegador",
            "about.step2_desc": "Navegue no visual do Outlook 365, pesquise por palavras (inclusive dentro de anexos PDF, Word e Excel) e imprima ou salve o que precisar.",
            "about.step3_title": "Feche com Tranquilidade",
            "about.step3_desc": "Ao encerrar a consulta, a leitura temporária na web é limpa automaticamente e seu arquivo original permanece 100% intacto onde sempre esteve.",
            "about.pc_title": "No seu Computador ou Pasta da Rede",
            "about.pc_1": "<strong>Seu arquivo .pst original NUNCA é alterado:</strong> O arquivo que você escolheu continua 100% salvo e intacto no seu computador ou servidor de arquivos.",
            "about.pc_2": "<strong>Zero instalação no cliente:</strong> Não precisa ter o Microsoft Outlook instalado para abrir seus backups.",
            "about.pc_3": "<strong>Sem arquivos espalhados:</strong> Nada fica salvo na máquina, a menos que você clique em <em>Baixar</em>.",
            "about.srv_title": "Na Sala de Leitura Temporária",
            "about.srv_1": "<strong>Ambiente exclusivo por usuário:</strong> Cada sessão é isolada para que apenas você veja o arquivo que abriu.",
            "about.srv_2": "<strong>Limpeza imediata ao fechar:</strong> Ao clicar em <em>Fechar Consulta</em> ou <em>Sair</em>, a visualização temporária aberta no servidor é descartada na hora.",
            "about.srv_3": "<strong>Descarte por inatividade:</strong> Se você esquecer a aba aberta, o sistema limpa a visualização temporária sozinho.",
            "about.created_by": "Idealizado e Desenvolvido por",
            "about.author_dept": "Tecnologia da Informação • Soluções Corporativas",
            "about.features_heading": "Diferenciais da Plataforma",
            "about.feat1_t": "Árvore Limpa e Inteligente",
            "about.feat1_d": "Filtra pastas vazias do sistema e foca exatamente nas pastas do seu backup.",
            "about.feat2_t": "Busca dentro de Anexos",
            "about.feat2_d": "Encontra termos tanto no corpo do e-mail quanto dentro de PDFs, Word e Excel.",
            "about.feat3_t": "Bilíngue Interativo (PT / EN)",
            "about.feat3_d": "Interface e instaladores prontos para uso em Português e Inglês com 1 clique.",
            "about.feat4_t": "Impressão A4 e Exportação EML",
            "about.feat4_d": "Gera folha de impressão limpa ou exporta mensagens individuais no padrão universal."
        },
        en: {
            "nav.about_system": "About the system",
            "nav.about": "About",
            "nav.back_home": "Back to Home Dashboard",
            "nav.indexing": "Indexing...",
            "nav.change_pw": "Change Password",
            "nav.change_pw_title": "Change your account password",
            "nav.admin": "Administration",
            "nav.close_session": "Close Session",
            "nav.close_session_title": "Close current web view (your original .pst file remains 100% untouched on your PC)",
            "nav.logout": "Sign Out",
            "nav.logout_title": "Sign out of the system",
            "login.tagline": "Open, search, and read your Microsoft Outlook email archives with ease.",
            "login.username_label": "Username",
            "login.username_placeholder": "Enter your username",
            "login.password_label": "Password",
            "login.password_placeholder": "Enter your password",
            "login.submit_btn": "Sign In",
            "login.by": "By",
            "sim.badge": "INTERACTIVE SIMULATOR • OUTLOOK 365 WEB",
            "sim.heading": "See how easy it is to browse your email backups right in your browser",
            "sim.subtitle": "Click the folders or fictitious sample emails below to test the reader before signing in.",
            "sim.search_placeholder": "Try searching the simulator (e.g., budget, contract, cloud)...",
            "sim.demo_mode": "Live Demo Mode",
            "sim.ribbon_read": "Instant Reader",
            "sim.safe_pill": "✔ Original file preserved",
            "search.placeholder": "Search entire PST (subject, body, sender, recipients & attachments)...",
            "search.btn": "Search",
            "search.filters": "Filters",
            "search.filters_title": "Advanced search filters",
            "search.clear": "Clear",
            "home.open_title": "Open Email Archive (.PST)",
            "home.drop_heading": "Choose an Outlook (.pst) file from your computer",
            "home.drop_sub": "Browse your folders, read messages, search keywords, and open attachments directly in your browser.",
            "home.choose_btn": "Choose .PST File",
            "home.assurance": "<strong>Peace of mind:</strong> The original file saved on your computer or network drive is <strong>never modified</strong>.",
            "home.active_files": "Open Archives",
            "home.refresh": "Refresh",
            "home.no_sessions": "No active PST sessions right now. Choose a .PST file above to begin.",
            "proc.title": "Processing PST archive...",
            "proc.stage": "Starting validation...",
            "proc.folders": "Mapped Folders",
            "proc.messages": "Extracted Messages",
            "proc.attachments": "Processed Attachments",
            "proc.corrupted": "Corrupted Items / Warnings",
            "proc.hint": "Waiting for initial folder indexing to unlock the reader...",
            "proc.diagnostics": "View Diagnostics",
            "proc.cancel": "Cancel Reading",
            "proc.open_reader": "Open Email Reader",
            "filter.sender": "Sender",
            "filter.recipient": "Recipient (To/CC/BCC)",
            "filter.name_email": "Name or email",
            "filter.folder": "Folder",
            "filter.all_folders": "All PST folders",
            "filter.date_from": "Date (From)",
            "filter.date_to": "Date (To)",
            "filter.attachments": "Attachments",
            "filter.all_msgs": "All messages",
            "filter.with_att": "With attachments only",
            "filter.without_att": "Without attachments",
            "filter.apply": "Apply",
            "reader.folders": "Folders",
            "reader.diagnostics": "PST Diagnostics",
            "reader.partial_notice": "Background indexing active: new messages may appear",
            "reader.print": "Print Email",
            "reader.save_eml": "Save EML",
            "reader.export_txt": "Export TXT",
            "reader.folders_pane_title": "PST Archive Folders",
            "reader.messages": "Messages",
            "reader.prev_page": "◀ Prev",
            "reader.next_page": "Next ▶",
            "reader.empty_title": "Select a message from the list to read its content",
            "reader.empty_sub": "Attachments, headers, and print options will appear in this pane.",
            "reader.mode_html": "Formatted",
            "reader.mode_plain": "Plain Text",
            "reader.mode_headers": "Headers",
            "reader.from": "From:",
            "reader.to": "To:",
            "reader.date": "Date/Time:",
            "reader.folder": "PST Folder:",
            "sort.newest": "Newest first",
            "sort.oldest": "Oldest first",
            "sort.sender": "Sender (A-Z)",
            "sort.subject": "Subject (A-Z)",
            "sort.size": "Largest size",
            "diag.title": "PST Technical Diagnostics",
            "att.title": "View Attachment",
            "att.print": "Print Attachment",
            "att.download": "Download Attachment",
            "admin.title": "PST Viewer Administration",
            "admin.tab_sessions": "Sessions & Cleanup",
            "admin.tab_users": "Users",
            "admin.tab_settings": "Settings & Limits",
            "common.close_x": "Close ✕",
            "common.close": "Close",
            "common.got_it": "Got it",
            "about.badge_safe": "100% Safe & Web-Based",
            "about.hero_sub": "Modern platform for opening, fast searching, and reading Microsoft Outlook (.pst) email archives",
            "about.tab_story": "Purpose & How It Works",
            "about.tab_privacy": "Your Files Are Preserved",
            "about.tab_author": "Author & Capabilities",
            "about.story_title": "Why was PST Viewer created?",
            "about.story_p1": "<strong>PST Viewer</strong> was created from the practical need to inspect departmental Microsoft Outlook backup archives (<code>.pst</code>) quickly and effortlessly.",
            "about.story_p2": "After periodic email backups are moved off the primary mail server to free up storage, finding an old message or contract inside <code>.pst</code> files used to require complex desktop setups or expensive commercial licenses. With this web platform, you simply open your browser to read, search, and print any email in seconds.",
            "about.steps_heading": "How it works in 3 simple steps",
            "about.step1_title": "Choose your .PST file",
            "about.step1_desc": "Select the file from your computer or network share. Only your actual backed-up folders are shown—no cluttered empty system folders.",
            "about.step2_title": "Search & Read in Browser",
            "about.step2_desc": "Browse in an Outlook 365 interface, search keywords (including inside PDF, Word, and Excel attachments), and print or save what you need.",
            "about.step3_title": "Close with Peace of Mind",
            "about.step3_desc": "When you finish, the temporary web reading session is automatically cleaned up while your original file stays 100% untouched where it has always been.",
            "about.pc_title": "On Your Computer or Network Share",
            "about.pc_1": "<strong>Your original .pst file is NEVER modified:</strong> The file you selected stays 100% saved and intact on your computer or file server.",
            "about.pc_2": "<strong>Zero client installation:</strong> No need to have Microsoft Outlook installed to inspect your backups.",
            "about.pc_3": "<strong>No leftover local files:</strong> Nothing is written to your machine unless you click <em>Download</em>.",
            "about.srv_title": "Inside the Ephemeral Reading Room",
            "about.srv_1": "<strong>Isolated per user:</strong> Each reading session is private so only you can view the archive you opened.",
            "about.srv_2": "<strong>Instant cleanup on close:</strong> Clicking <em>Close Session</em> or <em>Sign Out</em> immediately purges the temporary web copy.",
            "about.srv_3": "<strong>Automatic idle expiration:</strong> If you leave the tab open, the background cleaner removes the temporary view automatically.",
            "about.created_by": "Designed & Developed by",
            "about.author_dept": "Information Technology • Enterprise Solutions",
            "about.features_heading": "Platform Highlights",
            "about.feat1_t": "Smart Clean Folder Tree",
            "about.feat1_d": "Automatically hides empty MAPI system folders and focuses directly on your backed-up folders.",
            "about.feat2_t": "Deep Attachment Search",
            "about.feat2_d": "Finds keywords inside both email bodies and attached PDF, Word, and Excel documents.",
            "about.feat3_t": "Interactive Bilingual (PT / EN)",
            "about.feat3_d": "Web interface and automated installers ready for Portuguese and English with 1 click.",
            "about.feat4_t": "A4 Print & Universal EML Export",
            "about.feat4_d": "Generates clean printouts or exports individual emails in standard RFC 5322 (.eml) format."
        }
    };

    function isEn() {
        return state.lang === "en";
    }

    function t(key) {
        const dict = I18N[state.lang] || I18N.pt;
        return dict[key] !== undefined ? dict[key] : (I18N.pt[key] || key);
    }

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
        const defaultTitles = isEn() ? {
            success: "Operation Completed",
            danger: "Attention / Error",
            warning: "System Notice",
            info: "Information",
        } : {
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
                <div class="ui-toast-title">${escapeHtml(title || defaultTitles[variant] || (isEn() ? "System" : "Sistema"))}</div>
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
        title = "",
        message = "",
        confirmText = "",
        cancelText = "",
        variant = "primary", // "primary" | "danger" | "warning"
        icon = SVG_ICONS.shield,
    } = {}) {
        const en = isEn();
        const finalTitle = title || (en ? "System Confirmation" : "Confirmação do Sistema");
        const finalConfirm = confirmText || (en ? "Confirm" : "Confirmar");
        const finalCancel = cancelText || (en ? "Cancel" : "Cancelar");

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
                            <h3 class="ui-dialog-title">${escapeHtml(finalTitle)}</h3>
                            <p class="ui-dialog-message">${escapeHtml(message)}</p>
                        </div>
                    </div>
                    <div class="ui-dialog-footer">
                        <button type="button" class="btn btn-outline" data-dialog-cancel>${escapeHtml(finalCancel)}</button>
                        <button type="button" class="btn ${btnClass}" data-dialog-confirm>${escapeHtml(finalConfirm)}</button>
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
        title = "",
        message = "",
        buttonText = "",
        variant = "primary",
        icon = SVG_ICONS.info,
    } = {}) {
        const en = isEn();
        const finalTitle = title || (en ? "System Notice" : "Aviso do Sistema");
        const finalButton = buttonText || (en ? "Got it" : "Entendi");

        return new Promise((resolve) => {
            const backdrop = document.createElement("div");
            backdrop.className = "ui-dialog-backdrop";
            const iconVariant = variant === "danger" ? "icon-danger" : (variant === "success" ? "icon-success" : "icon-primary");

            backdrop.innerHTML = `
                <div class="ui-dialog-box" role="alertdialog" aria-modal="true">
                    <div class="ui-dialog-body">
                        <div class="ui-dialog-icon ${iconVariant}">${icon}</div>
                        <div class="ui-dialog-content">
                            <h3 class="ui-dialog-title">${escapeHtml(finalTitle)}</h3>
                            <p class="ui-dialog-message">${escapeHtml(message)}</p>
                        </div>
                    </div>
                    <div class="ui-dialog-footer">
                        <button type="button" class="btn btn-primary" data-dialog-ok>${escapeHtml(finalButton)}</button>
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
        title = "",
        message = "",
        placeholder = "",
        inputType = "password",
        minLength = 1,
        confirmText = "",
        cancelText = "",
    } = {}) {
        const en = isEn();
        const finalTitle = title || (en ? "Enter Value" : "Informar Valor");
        const finalConfirm = confirmText || (en ? "Save" : "Salvar");
        const finalCancel = cancelText || (en ? "Cancel" : "Cancelar");

        return new Promise((resolve) => {
            const backdrop = document.createElement("div");
            backdrop.className = "ui-dialog-backdrop";

            backdrop.innerHTML = `
                <div class="ui-dialog-box" role="dialog" aria-modal="true">
                    <div class="ui-dialog-body">
                        <div class="ui-dialog-icon icon-primary">${SVG_ICONS.key}</div>
                        <div class="ui-dialog-content">
                            <h3 class="ui-dialog-title">${escapeHtml(finalTitle)}</h3>
                            <p class="ui-dialog-message">${escapeHtml(message)}</p>
                            <input type="${escapeHtml(inputType)}" class="form-control ui-dialog-input" placeholder="${escapeHtml(placeholder)}" minlength="${minLength}">
                            <div class="ui-dialog-err hidden" style="color:var(--danger);font-size:12px;margin-top:6px;"></div>
                        </div>
                    </div>
                    <div class="ui-dialog-footer">
                        <button type="button" class="btn btn-outline" data-dialog-cancel>${escapeHtml(finalCancel)}</button>
                        <button type="button" class="btn btn-primary" data-dialog-confirm>${escapeHtml(finalConfirm)}</button>
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
                    errBox.textContent = en
                        ? `This field must have at least ${minLength} characters.`
                        : `O campo deve ter pelo menos ${minLength} caracteres.`;
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
            backdrop.addEventListener("click", (ev) => {
                if (ev.target === backdrop) close(null);
            });

            document.body.appendChild(backdrop);
            inp.focus();
        });
    }
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
        if (state.sessionToken) {
            opts.headers["X-Session-Token"] = state.sessionToken;
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
     * SIMULADOR INTERATIVO OUTLOOK 365 WEB (PESSOAS FICTÍCIAS + BILÍNGUE)
     * ====================================================================== */
    const SIM_DATA = {
        pt: {
            fileBadge: "📁 backup_departamentos_2026.pst",
            folders: [
                { id: "inbox", name: "📥 Caixa de Entrada", count: 4 },
                { id: "sent", name: "📤 Itens Enviados", count: 2 },
                { id: "contracts", name: "📂 Contratos & Finanças", count: 2 },
            ],
            messages: [
                {
                    id: 1,
                    folder: "inbox",
                    sender: "Helena Martins",
                    email: "helena.martins@auroracorp.com",
                    to: "Mariana Costa <mariana.costa@auroracorp.com>; Equipe Financeira",
                    initials: "HM",
                    color: "#0f6cbd",
                    date: "29/10/2026 09:14",
                    subject: "Relatório Consolidado Q4 e Planejamento 2027",
                    snippet: "Segue em anexo o fechamento trimestral revisado e a planilha de metas...",
                    attachments: [
                        { name: "Fechamento_Trimestral_Q4.pdf", size: "1,4 MB" },
                        { name: "Metas_Orcamento_2027.xlsx", size: "620 KB" },
                    ],
                    body: `<p>Olá pessoal,</p><p>Encaminho em anexo o <strong>Relatório Consolidado do 4º Trimestre</strong> e a planilha atualizada com as projeções dos departamentos para 2027.</p><p>Todos os documentos já foram conferidos pela equipe de controladoria e estão prontos para consulta.</p><p>Atenciosamente,<br><strong>Helena Martins</strong><br>Diretoria Financeira • Aurora Corp</p>`,
                },
                {
                    id: 2,
                    folder: "inbox",
                    sender: "Lucas Vance",
                    email: "lucas.vance@auroracorp.com",
                    to: "Coordenação de Operações <operacoes@auroracorp.com>",
                    initials: "LV",
                    color: "#0284c7",
                    date: "28/10/2026 17:42",
                    subject: "Cronograma de Migração de Servidores Nuvem",
                    snippet: "A janela de manutenção programada para o próximo sábado foi aprovada...",
                    attachments: [
                        { name: "Plano_Migracao_Cloud.docx", size: "410 KB" },
                    ],
                    body: `<p>Boa tarde equipe,</p><p>Confirmamos que a atualização dos servidores em nuvem ocorrerá neste sábado às 08h00, sem impacto para os usuários finais.</p><p>O roteiro completo está no documento Word em anexo.</p><p>Abraços,<br><strong>Lucas Vance</strong><br>Arquitetura Cloud</p>`,
                },
                {
                    id: 3,
                    folder: "inbox",
                    sender: "Sofia Alencar",
                    email: "sofia.alencar@auroracorp.com",
                    to: "Compras & Suprimentos <compras@auroracorp.com>",
                    initials: "SA",
                    color: "#7c3aed",
                    date: "27/10/2026 14:15",
                    subject: "Minuta Aprovada — Renovação de Fornecedores",
                    snippet: "Enviamos a versão final revisada pelo jurídico para assinatura digital...",
                    attachments: [
                        { name: "Minuta_Fornecedores_2027.pdf", size: "980 KB" },
                    ],
                    body: `<p>Prezados,</p><p>A revisão jurídica do contrato anual de fornecedores foi concluída. O arquivo PDF em anexo já contempla todas as cláusulas atualizadas.</p><p>Cordialmente,<br><strong>Sofia Alencar</strong><br>Consultoria Jurídica</p>`,
                },
                {
                    id: 4,
                    folder: "inbox",
                    sender: "Marcos Oliveira",
                    email: "marcos.oliveira@auroracorp.com",
                    to: "Recursos Humanos <rh@auroracorp.com>",
                    initials: "MO",
                    color: "#059669",
                    date: "25/10/2026 11:05",
                    subject: "Calendário de Integração de Novos Colaboradores",
                    snippet: "Lista das turmas confirmadas para a primeira semana de novembro...",
                    attachments: [],
                    body: `<p>Bom dia,</p><p>As salas de treinamento para a integração de novembro já estão reservadas. Teremos 18 novos integrantes distribuídos em duas turmas.</p><p>Atenciosamente,<br><strong>Marcos Oliveira</strong><br>Desenvolvimento Humano</p>`,
                },
                {
                    id: 5,
                    folder: "sent",
                    sender: "Clara Novak",
                    email: "clara.novak@auroracorp.com",
                    to: "Helena Martins <helena.martins@auroracorp.com>",
                    initials: "CN",
                    color: "#d97706",
                    date: "29/10/2026 10:02",
                    subject: "RE: Relatório Consolidado Q4 e Planejamento 2027",
                    snippet: "Obrigada pelo envio, Helena! Já validamos os números do nosso setor...",
                    attachments: [],
                    body: `<p>Olá Helena,</p><p>Muito obrigada pelo envio! Já revisamos as abas da planilha e os valores do nosso departamento estão 100% corretos.</p><p>Um abraço,<br><strong>Clara Novak</strong></p>`,
                },
                {
                    id: 6,
                    folder: "sent",
                    sender: "Daniel Costa",
                    email: "daniel.costa@auroracorp.com",
                    to: "Sofia Alencar <sofia.alencar@auroracorp.com>",
                    initials: "DC",
                    color: "#dc2626",
                    date: "27/10/2026 16:30",
                    subject: "ENC: Comprovante de Assinatura de Contrato",
                    snippet: "Segue o protocolo de assinatura eletrônica concluído hoje à tarde...",
                    attachments: [
                        { name: "Protocolo_Assinatura.pdf", size: "315 KB" },
                    ],
                    body: `<p>Olá Sofia,</p><p>Segue em anexo o comprovante de assinatura digital referente ao contrato de serviços logísticos.</p><p>Atenciosamente,<br><strong>Daniel Costa</strong></p>`,
                },
            ],
        },
        en: {
            fileBadge: "📁 corporate_departments_2026.pst",
            folders: [
                { id: "inbox", name: "📥 Inbox", count: 4 },
                { id: "sent", name: "📤 Sent Items", count: 2 },
                { id: "contracts", name: "📂 Contracts & Finance", count: 2 },
            ],
            messages: [
                {
                    id: 1,
                    folder: "inbox",
                    sender: "Helena Martins",
                    email: "helena.martins@auroracorp.com",
                    to: "Mariana Costa <mariana.costa@auroracorp.com>; Finance Team",
                    initials: "HM",
                    color: "#0f6cbd",
                    date: "10/29/2026 09:14 AM",
                    subject: "Q4 Consolidated Report & 2027 Budget Planning",
                    snippet: "Please find attached the revised quarterly closing and target sheet...",
                    attachments: [
                        { name: "Q4_Quarterly_Closing.pdf", size: "1.4 MB" },
                        { name: "Budget_Targets_2027.xlsx", size: "620 KB" },
                    ],
                    body: `<p>Hello everyone,</p><p>Please find attached the <strong>Q4 Consolidated Financial Report</strong> along with the updated departmental budget projections for 2027.</p><p>All figures have been verified by the controlling team and are ready for review.</p><p>Best regards,<br><strong>Helena Martins</strong><br>Finance Director • Aurora Corp</p>`,
                },
                {
                    id: 2,
                    folder: "inbox",
                    sender: "Lucas Vance",
                    email: "lucas.vance@auroracorp.com",
                    to: "Operations Team <operations@auroracorp.com>",
                    initials: "LV",
                    color: "#0284c7",
                    date: "10/28/2026 05:42 PM",
                    subject: "Cloud Server Upgrade Schedule",
                    snippet: "The maintenance window scheduled for next Saturday has been approved...",
                    attachments: [
                        { name: "Cloud_Migration_Plan.docx", size: "410 KB" },
                    ],
                    body: `<p>Good afternoon team,</p><p>We confirm that the cloud server upgrade will take place this Saturday at 8:00 AM with zero downtime for end users.</p><p>The complete checklist is available in the attached Word document.</p><p>Best,<br><strong>Lucas Vance</strong><br>Cloud Architecture</p>`,
                },
                {
                    id: 3,
                    folder: "inbox",
                    sender: "Sofia Alencar",
                    email: "sofia.alencar@auroracorp.com",
                    to: "Procurement & Supply <procurement@auroracorp.com>",
                    initials: "SA",
                    color: "#7c3aed",
                    date: "10/27/2026 02:15 PM",
                    subject: "Approved Draft — Vendor Master Renewal",
                    snippet: "Sending the final version reviewed by Legal for digital signature...",
                    attachments: [
                        { name: "Vendor_Agreement_2027.pdf", size: "980 KB" },
                    ],
                    body: `<p>Dear team,</p><p>The legal review for the annual vendor agreement is now complete. The attached PDF includes all updated compliance clauses.</p><p>Kind regards,<br><strong>Sofia Alencar</strong><br>Corporate Legal</p>`,
                },
                {
                    id: 4,
                    folder: "inbox",
                    sender: "Marcos Oliveira",
                    email: "marcos.oliveira@auroracorp.com",
                    to: "Human Resources <hr@auroracorp.com>",
                    initials: "MO",
                    color: "#059669",
                    date: "10/25/2026 11:05 AM",
                    subject: "New Hire Onboarding Schedule — November",
                    snippet: "Confirmed training groups for the first week of November...",
                    attachments: [],
                    body: `<p>Good morning,</p><p>The training rooms for the November onboarding sessions are booked. We will welcome 18 new team members across two groups.</p><p>Sincerely,<br><strong>Marcos Oliveira</strong><br>People & Culture</p>`,
                },
                {
                    id: 5,
                    folder: "sent",
                    sender: "Clara Novak",
                    email: "clara.novak@auroracorp.com",
                    to: "Helena Martins <helena.martins@auroracorp.com>",
                    initials: "CN",
                    color: "#d97706",
                    date: "10/29/2026 10:02 AM",
                    subject: "RE: Q4 Consolidated Report & 2027 Budget Planning",
                    snippet: "Thanks for sending this over, Helena! We validated our department numbers...",
                    attachments: [],
                    body: `<p>Hi Helena,</p><p>Thank you for sending this over! We reviewed the spreadsheet tabs and our department's figures are 100% accurate.</p><p>Warm regards,<br><strong>Clara Novak</strong></p>`,
                },
                {
                    id: 6,
                    folder: "sent",
                    sender: "Daniel Costa",
                    email: "daniel.costa@auroracorp.com",
                    to: "Sofia Alencar <sofia.alencar@auroracorp.com>",
                    initials: "DC",
                    color: "#dc2626",
                    date: "10/27/2026 04:30 PM",
                    subject: "FW: Digital Contract Signature Receipt",
                    snippet: "Attached is the electronic signature certificate completed this afternoon...",
                    attachments: [
                        { name: "Signature_Certificate.pdf", size: "315 KB" },
                    ],
                    body: `<p>Hi Sofia,</p><p>Please find attached the digital signature receipt for the logistics services agreement.</p><p>Best regards,<br><strong>Daniel Costa</strong></p>`,
                },
            ],
        },
    };

    function renderOutlook365Simulator() {
        const foldersEl = $("sim-folders-list");
        const msgsEl = $("sim-messages-container");
        const readEl = $("sim-reading-pane");
        if (!foldersEl || !msgsEl || !readEl) return;

        const en = isEn();
        const data = SIM_DATA[state.lang] || SIM_DATA.pt;
        if ($("sim-file-badge")) {
            $("sim-file-badge").textContent = data.fileBadge;
        }

        // Render pastas
        foldersEl.innerHTML = data.folders.map((f) => `
            <div class="o365-folder-item ${state.simFolder === f.id ? "active" : ""}" data-sim-folder="${f.id}">
                <span>${escapeHtml(f.name)}</span>
                <span class="o365-folder-badge">${f.count}</span>
            </div>
        `).join("");

        foldersEl.querySelectorAll("[data-sim-folder]").forEach((el) => {
            el.addEventListener("click", () => {
                state.simFolder = el.getAttribute("data-sim-folder");
                state.simQuery = "";
                if ($("sim-search-input")) $("sim-search-input").value = "";
                renderOutlook365Simulator();
            });
        });

        // Filtrar mensagens
        const q = (state.simQuery || "").toLowerCase().trim();
        let filtered = data.messages.filter((m) => {
            if (q) {
                return (
                    m.subject.toLowerCase().includes(q) ||
                    m.sender.toLowerCase().includes(q) ||
                    m.snippet.toLowerCase().includes(q) ||
                    m.body.toLowerCase().includes(q)
                );
            }
            if (state.simFolder === "contracts") {
                return m.id === 1 || m.id === 3;
            }
            return m.folder === state.simFolder;
        });

        if (!filtered.some((m) => m.id === state.simSelectedId) && filtered.length > 0) {
            state.simSelectedId = filtered[0].id;
        }

        const activeFolderObj = data.folders.find((f) => f.id === state.simFolder) || data.folders[0];
        if ($("sim-folder-title")) {
            $("sim-folder-title").textContent = q
                ? (en ? `Search: "${state.simQuery}"` : `Busca: "${state.simQuery}"`)
                : activeFolderObj.name.replace(/^[^\s]+\s/, "");
        }
        if ($("sim-folder-count")) {
            $("sim-folder-count").textContent = `${filtered.length} ${en ? "items" : "itens"}`;
        }

        if (filtered.length === 0) {
            msgsEl.innerHTML = `<div style="padding:24px 14px;text-align:center;color:#64748b;font-size:12.5px;">${en ? "No sample messages matched your search." : "Nenhuma mensagem de exemplo encontrada."}</div>`;
            readEl.innerHTML = "";
            return;
        }

        msgsEl.innerHTML = filtered.map((m) => `
            <div class="o365-msg-card ${m.id === state.simSelectedId ? "active" : ""}" data-sim-msg="${m.id}">
                <div class="o365-avatar" style="background:${m.color};">${escapeHtml(m.initials)}</div>
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:6px;">
                        <strong style="font-size:12.5px;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(m.sender)}</strong>
                        <span style="font-size:10.5px;color:#64748b;flex-shrink:0;">${escapeHtml(m.date.split(" ")[0])}</span>
                    </div>
                    <div style="font-size:12px;font-weight:700;color:#0f6cbd;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:2px 0;">
                        ${m.attachments.length ? "📎 " : ""}${escapeHtml(m.subject)}
                    </div>
                    <div style="font-size:11.5px;color:#64748b;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                        ${escapeHtml(m.snippet)}
                    </div>
                </div>
            </div>
        `).join("");

        msgsEl.querySelectorAll("[data-sim-msg]").forEach((el) => {
            el.addEventListener("click", () => {
                state.simSelectedId = Number(el.getAttribute("data-sim-msg"));
                renderOutlook365Simulator();
            });
        });

        const sel = filtered.find((m) => m.id === state.simSelectedId) || filtered[0];
        readEl.innerHTML = `
            <h4 class="o365-read-subj">${escapeHtml(sel.subject)}</h4>
            <div class="o365-read-sender-row">
                <div class="o365-avatar" style="background:${sel.color};">${escapeHtml(sel.initials)}</div>
                <div style="flex:1;min-width:0;">
                    <div style="font-size:13px;font-weight:700;color:#0f172a;">
                        ${escapeHtml(sel.sender)} <span style="font-weight:400;color:#64748b;font-size:12px;">&lt;${escapeHtml(sel.email)}&gt;</span>
                    </div>
                    <div style="font-size:11.5px;color:#64748b;">
                        <strong>${en ? "To:" : "Para:"}</strong> ${escapeHtml(sel.to)} • ${escapeHtml(sel.date)}
                    </div>
                </div>
            </div>
            ${sel.attachments.length ? `
                <div class="o365-att-bar">
                    ${sel.attachments.map((a) => `
                        <span class="o365-att-pill" data-sim-att="${escapeHtml(a.name)}">
                            📎 ${escapeHtml(a.name)} <small style="color:#64748b;">(${escapeHtml(a.size)})</small>
                        </span>
                    `).join("")}
                </div>
            ` : ""}
            <div class="o365-read-body">${sel.body}</div>
        `;

        readEl.querySelectorAll("[data-sim-att]").forEach((pill) => {
            pill.addEventListener("click", () => {
                const name = pill.getAttribute("data-sim-att");
                uiToast(
                    en
                        ? `In the full reader, clicking "${name}" opens its content or downloads the original file.`
                        : `No leitor completo, clicar em "${name}" abre a leitura do anexo na tela ou baixa o arquivo original.`,
                    "info",
                    en ? "Attachment Preview (Simulator)" : "Visualização de Anexo (Simulador)"
                );
            });
        });
    }

    function applyLanguage(lang) {
        state.lang = lang === "en" ? "en" : "pt";
        try {
            localStorage.setItem("pstviewer_lang", state.lang);
        } catch (_e) {}
        document.documentElement.lang = state.lang === "en" ? "en" : "pt-BR";

        document.querySelectorAll("[data-set-lang]").forEach((btn) => {
            btn.classList.toggle("active", btn.getAttribute("data-set-lang") === state.lang);
        });

        document.querySelectorAll("[data-i18n]").forEach((el) => {
            const key = el.getAttribute("data-i18n");
            const val = t(key);
            if (val !== undefined && val !== null) {
                if (val.includes("<")) {
                    el.innerHTML = val;
                } else {
                    el.textContent = val;
                }
            }
        });

        document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
            const key = el.getAttribute("data-i18n-placeholder");
            const val = t(key);
            if (val) el.setAttribute("placeholder", val);
        });

        document.querySelectorAll("[data-i18n-title]").forEach((el) => {
            const key = el.getAttribute("data-i18n-title");
            const val = t(key);
            if (val) el.setAttribute("title", val);
        });

        renderOutlook365Simulator();
        if (state.user && $("view-home") && !$("view-home").classList.contains("hidden")) {
            loadMyActiveSessions();
        }
    }

    // Delegação global de clique para garantir que a troca de idioma NUNCA falhe
    document.addEventListener("click", (ev) => {
        const btn = ev.target.closest ? ev.target.closest("[data-set-lang]") : null;
        if (btn) {
            ev.preventDefault();
            const lang = btn.getAttribute("data-set-lang");
            if (lang) {
                applyLanguage(lang);
            }
        }
    });

    /* ======================================================================
     * NAVEGAÇÃO ENTRE TELAS
     * ====================================================================== */
    function showLoginView(alertMsg = "") {
        stopPolling();
        state.user = null;
        state.csrfToken = null;
        state.sessionToken = null;
        localStorage.removeItem("pstviewer_token");
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
        const en = isEn();
        const newPw = await uiPrompt({
            title: isFirstAccess
                ? (en ? "First Sign-In — Set Your Personal Password" : "Primeiro Acesso — Defina sua Senha Pessoal")
                : (en ? "Change My Account Password" : "Alterar Minha Senha de Acesso"),
            message: isFirstAccess
                ? (en
                    ? "You signed in with a temporary password generated by the installer. Choose an easy-to-remember personal password below (min. 8 characters):"
                    : "Você acessou com uma senha temporária gerada pelo instalador. Escolha abaixo uma senha pessoal fácil de lembrar (mínimo 8 caracteres):")
                : (en
                    ? "Enter your new account password (minimum 8 characters):"
                    : "Digite sua nova senha de acesso (mínimo de 8 caracteres):"),
            placeholder: en ? "Enter new password (min. 8 chars)" : "Digite a nova senha (mín. 8 caracteres)",
            inputType: "password",
            confirmText: en ? "Save New Password" : "Salvar Nova Senha",
            cancelText: isFirstAccess ? (en ? "Keep Current" : "Manter a Atual") : (en ? "Cancel" : "Cancelar"),
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
            uiToast(
                en ? "Your personal password has been saved!" : "Sua senha pessoal foi salva com sucesso!",
                "success",
                en ? "Password Updated" : "Senha Atualizada"
            );
        } catch (err) {
            uiToast(err.message, "danger", en ? "Password Error" : "Erro ao alterar senha");
        }
    }

    function onAuthenticated(user, csrfToken, sessionToken = null) {
        state.user = user;
        state.csrfToken = csrfToken;
        if (sessionToken) {
            state.sessionToken = sessionToken;
            localStorage.setItem("pstviewer_token", sessionToken);
        }
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
        const en = isEn();
        container.innerHTML = `<div style="color:var(--text-secondary);">${en ? "Loading active sessions..." : "Carregando sessões..."}</div>`;
        try {
            const data = await apiFetch("/api/sessions");
            const list = data.sessions || [];
            if (list.length === 0) {
                container.innerHTML = `
                    <div style="padding:14px;background:var(--bg-subtle);border-radius:6px;color:var(--text-secondary);">
                        ${t("home.no_sessions")}
                    </div>`;
                return;
            }
            let html = `<table class="table-clean">
                <thead>
                    <tr>
                        <th>${en ? "File" : "Arquivo"}</th>
                        <th>${en ? "Format" : "Formato"}</th>
                        <th>${en ? "Status" : "Estado"}</th>
                        <th>${en ? "Folders / Emails" : "Pastas / E-mails"}</th>
                        <th>${en ? "Idle Expiration" : "Expira por inatividade"}</th>
                        <th style="text-align:right;">${en ? "Actions" : "Ações"}</th>
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
                        <td>${s.processed_folders} ${en ? "folders" : "pastas"} / ${s.processed_messages} msgs</td>
                        <td>${formatDateTime(s.idle_expires_at)}</td>
                        <td style="text-align:right;">
                            ${canOpen
                                ? `<button class="btn btn-primary btn-sm" data-open-sess="${escapeHtml(s.session_uuid)}">${en ? "Open Reader" : "Abrir Leitor"}</button>`
                                : `<button class="btn btn-outline btn-sm" data-watch-sess="${escapeHtml(s.session_uuid)}">${en ? "View Progress" : "Ver Progresso"}</button>`
                            }
                            <button class="btn btn-danger btn-sm" data-close-sess="${escapeHtml(s.session_uuid)}">${en ? "Close & Clean" : "Encerrar e Limpar"}</button>
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
        if (state.sessionToken) {
            xhr.setRequestHeader("X-Session-Token", state.sessionToken);
        }

        xhr.upload.onprogress = function (evt) {
            if (evt.lengthComputable) {
                const pct = Math.round((evt.loaded / evt.total) * 100);
                progBar.style.width = pct + "%";
                pctTxt.textContent = pct + "%";
                if (pct >= 100) {
                    stTxt.textContent = "Preparando suas pastas e e-mails para leitura...";
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
        const en = isEn();
        const ok = await uiConfirm({
            title: en ? "Close Temporary Viewing" : "Fechar Visualização Temporária",
            message: en
                ? "Do you want to close this PST viewing session? The server's temporary reading cache will be purged (the original .pst file on your computer or network remains 100% safe and intact)."
                : "Deseja encerrar a visualização deste PST aqui no leitor web? A leitura temporária do servidor será limpa (o arquivo .pst original no seu computador/rede continua 100% salvo e intacto).",
            confirmText: en ? "Yes, Close Session" : "Sim, Fechar Consulta",
            cancelText: en ? "Continue Reading" : "Continuar Lendo",
            variant: "danger",
            icon: SVG_ICONS.trash,
        });
        if (!ok) return;
        try {
            await apiFetch(`/api/sessions/${sessionUuid}/close`, { method: "POST" });
            uiToast(
                en ? "Session closed on server (original .pst file remains intact on your PC)." : "Visualização encerrada no servidor (seu arquivo .pst original permanece intacto no seu PC).",
                "success",
                en ? "Session Closed" : "Consulta Encerrada"
            );
            if (state.currentSessionUuid === sessionUuid) {
                showHomeView();
            } else {
                loadMyActiveSessions();
            }
        } catch (err) {
            await uiAlert({
                title: en ? "Error Closing Session" : "Erro ao Encerrar Sessão",
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
                        const en = isEn();
                        const uuid = btn.getAttribute("data-force-purge");
                        const ok = await uiConfirm({
                            title: en ? "Force Session Purge" : "Forçar Expurgo de Sessão",
                            message: en
                                ? `Do you want to immediately purge temporary session ${uuid.substring(0, 12)}... and remove all files from disk?`
                                : `Deseja expurgar imediatamente a sessão temporária ${uuid.substring(0, 12)}... e remover todos os arquivos de disco?`,
                            confirmText: en ? "Purge Now" : "Expurgar Agora",
                            cancelText: en ? "Cancel" : "Cancelar",
                            variant: "danger",
                            icon: SVG_ICONS.trash,
                        });
                        if (!ok) return;
                        await apiFetch(`/api/admin/sessions/${uuid}/force-purge`, { method: "POST" });
                        uiToast(
                            en ? "Session purged successfully." : "Sessão expurgada com sucesso.",
                            "success",
                            en ? "Administrative Purge" : "Expurgo Administrativo"
                        );
                        renderAdminTab("sessions");
                    });
                });
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
                        const en = isEn();
                        const uid = btn.getAttribute("data-delete-u");
                        const uname = btn.getAttribute("data-delete-uname") || "";
                        const ok = await uiConfirm({
                            title: en ? "Delete User Account" : "Excluir Conta de Usuário",
                            message: en
                                ? `Do you want to permanently delete user "${uname}"? Any temporary PST sessions opened by this user will be terminated and purged from the server.`
                                : `Deseja excluir permanentemente o usuário "${uname}"? Eventuais sessões PST temporárias abertas por ele serão encerradas e limpas do servidor.`,
                            confirmText: en ? "Yes, Delete User" : "Sim, Excluir Usuário",
                            cancelText: en ? "Cancel" : "Cancelar",
                            variant: "danger",
                            icon: SVG_ICONS.trash,
                        });
                        if (!ok) return;
                        try {
                            await apiFetch(`/api/admin/users/${uid}`, { method: "DELETE" });
                            uiToast(
                                en ? `User "${uname}" deleted successfully.` : `Usuário "${uname}" excluído com sucesso.`,
                                "success",
                                en ? "User Management" : "Gestão de Usuários"
                            );
                            renderAdminTab("users");
                        } catch (err) {
                            await uiAlert({
                                title: en ? "Error Deleting User" : "Erro ao Excluir Usuário",
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
        applyLanguage(state.lang);

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
                onAuthenticated(data.user, data.csrf_token, data.session_token);
            } catch (err) {
                const en = isEn();
                let msg = err.message || "";
                if (en && msg.includes("Credenciais inválidas")) {
                    msg = "Invalid username or password.";
                } else if (en && msg.includes("bloqueada")) {
                    msg = "Account is temporarily locked due to failed attempts.";
                }
                showLoginView(msg);
            } finally {
                btn.disabled = false;
            }
        });

        $("btn-logout").addEventListener("click", async () => {
            const en = isEn();
            const ok = await uiConfirm({
                title: en ? "Sign Out of PST Viewer" : "Sair do PST Viewer",
                message: en
                    ? "Do you want to sign out? The temporary web viewing session will be closed (your original .pst file on your computer or network remains 100% untouched)."
                    : "Deseja sair do sistema? A visualização temporária aberta no leitor web será fechada (o seu arquivo .pst original no computador ou na rede permanece 100% intacto).",
                confirmText: en ? "Sign Out" : "Sair do Sistema",
                cancelText: en ? "Stay Connected" : "Continuar Conectado",
                variant: "primary",
                icon: SVG_ICONS.logout,
            });
            if (!ok) return;
            try {
                await apiFetch("/api/auth/logout", { method: "POST" });
            } catch (_e) {}
            showLoginView(en ? "You have signed out and temporary viewing data has been purged." : "Você saiu do sistema e os dados temporários foram eliminados.");
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
            const en = isEn();
            const ok = await uiConfirm({
                title: en ? "Cancel PST Processing" : "Cancelar Processamento PST",
                message: en
                    ? "Do you want to stop the ongoing extraction and immediately purge all partial files?"
                    : "Deseja interromper a extração em andamento e eliminar imediatamente todos os arquivos parciais?",
                confirmText: en ? "Yes, Cancel and Purge" : "Sim, Cancelar e Limpar",
                cancelText: en ? "Continue Processing" : "Continuar Processando",
                variant: "danger",
                icon: SVG_ICONS.alert,
            });
            if (!ok) return;
            await apiFetch(`/api/sessions/${state.currentSessionUuid}/cancel`, { method: "POST" });
            uiToast(
                en ? "Processing canceled and partial data removed." : "Processamento cancelado e dados parciais removidos.",
                "info",
                en ? "Canceled" : "Cancelado"
            );
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

        if ($("sim-search-input")) {
            $("sim-search-input").addEventListener("input", (ev) => {
                state.simQuery = ev.target.value;
                renderOutlook365Simulator();
            });
        }

        if ($("sim-btn-print")) {
            $("sim-btn-print").addEventListener("click", () => {
                uiToast(
                    isEn()
                        ? "In the live reader, this button opens a clean A4 print sheet ready for paper or PDF."
                        : "No leitor real, este botão gera uma folha A4 limpa pronta para impressora ou salvar em PDF.",
                    "info",
                    isEn() ? "Print Email (Simulator)" : "Imprimir E-mail (Simulador)"
                );
            });
        }

        if ($("sim-btn-eml")) {
            $("sim-btn-eml").addEventListener("click", () => {
                uiToast(
                    isEn()
                        ? "In the live reader, this downloads the selected email in universal .EML format."
                        : "No leitor real, este botão baixa o e-mail selecionado no formato universal .EML.",
                    "info",
                    isEn() ? "Export EML (Simulator)" : "Salvar EML (Simulador)"
                );
            });
        }

        // Sobre / Como Funciona / Créditos e Abas Interativas
        ["btn-login-about", "btn-login-about-top", "btn-open-about", "btn-home-about"].forEach((id) => {
            const el = $(id);
            if (el) {
                el.addEventListener("click", () => {
                    $("modal-about").classList.remove("hidden");
                });
            }
        });

        document.querySelectorAll("[data-about-tab]").forEach((tabBtn) => {
            tabBtn.addEventListener("click", () => {
                const targetTab = tabBtn.getAttribute("data-about-tab");
                document.querySelectorAll("[data-about-tab]").forEach((b) => {
                    b.classList.toggle("active", b === tabBtn);
                });
                ["story", "privacy", "author"].forEach((paneKey) => {
                    const pane = $(`about-pane-${paneKey}`);
                    if (pane) {
                        pane.classList.toggle("hidden", paneKey !== targetTab);
                    }
                });
            });
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

        applyLanguage(state.lang);
        checkCurrentSession();
    });
})();

