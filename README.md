<div align="center">

<!-- BARRA INTERATIVA DE SELEÇÃO DE IDIOMA (PT-BR / EN-US) -->
<p align="center">
  <a href="README.md">
    <img src="https://img.shields.io/badge/🇧🇷_Idioma-Português_(Ativo)-0f6cbd?style=for-the-badge" alt="Português Ativo" />
  </a>
  &nbsp;&nbsp;
  <a href="README.en.md">
    <img src="https://img.shields.io/badge/🇺🇸_Language-Read_in_English_(EN--US)-107c10?style=for-the-badge" alt="Read in English" />
  </a>
</p>

# 📧 PST Viewer
### Plataforma Corporativa de Inspeção, Leitura e Pesquisa Temporária de Arquivos Microsoft Outlook (`.pst`)

[![Python](https://img.shields.io/badge/Python-3.10%2B-0f6cbd?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![MariaDB / MySQL](https://img.shields.io/badge/MariaDB_%2F_MySQL-InnoDB_UTF8MB4-003545?style=for-the-badge&logo=mariadb&logoColor=white)](https://mariadb.org/)
[![Engine MAPI](https://img.shields.io/badge/Engine-libpff_%2F_pypff-0a2e5c?style=for-the-badge&logo=microsoftoutlook&logoColor=white)](#arquitetura-e-fluxo-de-dados)
[![Docker Ready](https://img.shields.io/badge/Docker-Compose_Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](#op%C3%A7%C3%A3o-2-docker--docker-compose-windows-macos-linux-ou-cloud)
[![Privacidade](https://img.shields.io/badge/Pol%C3%ADtica-Reten%C3%A7%C3%A3o_Zero_(LGPD)-107c10?style=for-the-badge&logo=shield&logoColor=white)](#seguran%C3%A7a-isolamento-e-descarte-autom%C3%A1tico)

<p align="center">
  <strong>Leitor web estilo Outlook 365 • Pesquisa profunda em e-mails e anexos (PDF/Office) • Bilíngue Interativo (PT / EN)</strong>
</p>

[Visão Geral](#-visão-geral) •
[Interface do Leitor Outlook](#-interface-do-leitor-estilo-microsoft-outlook) •
[Instalação Rápida](#-instalação-execute-e-saia-usando) •
[Arquitetura](#-arquitetura-e-fluxo-de-dados) •
[Comandos Úteis](#-comandos-de-gerenciamento-e-administração) •
[🇺🇸 Full English Docs (`README.en.md`)](README.en.md)

</div>

<details>
<summary><strong>🌐 🇺🇸 English Speaker? Click here for the Interactive Quick Start (or open <a href="README.en.md">README.en.md</a> for full English docs)</strong></summary>

<br>

**PST Viewer** is a turnkey enterprise web application for opening, searching, printing, and exporting Microsoft Outlook (`.pst`) archives directly in your browser with **Zero Data Retention** (your original `.pst` file is never modified and temporary reading data is purged automatically on close/logout).

* **Interactive Language Switcher (`🇧🇷 PT` | `🇺🇸 EN`):** Switch languages with 1 click on the login screen, inside the app top bar, or during CLI installation (`--lang en`).
* **Linux / Cloud 1-Command Install (in English):**
  ```bash
  git clone https://github.com/frederigi/pstviewer.git && cd pstviewer
  chmod +x install.sh && sudo ./install.sh --lang en
  ```
* **Windows + XAMPP 1-Click Install (in English):**
  ```powershell
  git clone https://github.com/frederigi/pstviewer.git
  cd pstviewer
  .\install_windows_xampp.bat --lang en
  ```
* 👉 **[Click here to read the complete documentation in English (`README.en.md`)](README.en.md)**

</details>

---

## 🎯 Visão Geral

O **PST Viewer** é uma aplicação web corporativa desenvolvida para **abrir, pesquisar, imprimir e exportar pontualmente mensagens e anexos de arquivos `.pst` do Microsoft Outlook** diretamente pelo navegador — sem necessidade de instalar o Microsoft Outlook na máquina do usuário e **sem reter dados permanentemente no servidor**.

> [!IMPORTANT]
> **Filosofia de Retenção Zero (Consulta Efêmera):**
> O sistema **não é um cofre permanente** de e-mails. O arquivo `.pst` original do usuário jamais é modificado (`0400 read-only`), a sessão roda em diretório isolado (`0700`) e, assim que o usuário clica em **"Fechar Consulta"**, faz **Logout** ou atinge o tempo limite de inatividade, **100% das mensagens, anexos e arquivos temporários são fisicamente expurgados do disco e do banco MySQL**.

---

## 🖥️ Interface do Leitor (Estilo Microsoft Outlook)

### ✨ Destaques da Experiência de Uso

| Recurso | Descrição Técnica |
| :--- | :--- |
| 🌍 **Bilíngue Interativo (`🇧🇷 PT` / `🇺🇸 EN`)** | Seletor interativo de idiomas em 1 clique no topo da tela (e também nos instaladores CLI via `--lang pt` ou `--lang en`), permitindo instalar, configurar e usar o sistema em **Português** ou **Inglês**. |
| 📂 **Árvore Limpa (Foco no Backup Real)** | Oculta automaticamente pastas técnicas ocultas do MAPI (`SPAM Search Folder`, `Pesquisar Raiz`), pastas vazias (`Itens Excluídos` sem itens) e cascas vazias (`Início do arquivo de dados do Outlook`), exibindo direto a pasta real do seu backup. |
| ⚡ **Abertura Progressiva (`READY_PARTIAL`)** | Não é preciso esperar um PST de vários Gigabytes terminar para começar a ler: assim que a 1ª pasta é mapeada, o leitor já é liberado enquanto o worker indexa o restante em background. |
| 🔍 **Pesquisa Global + Conteúdo de Anexos** | Busca `FULLTEXT` combinada com filtros por pasta, remetente, destinatário (`Para`/`CC`/`CCO`), período de datas e textos extraídos de dentro de arquivos **PDF, DOCX, XLSX, PPTX, RTF, DOC, TXT, CSV, HTML e ZIP**. |
| 🛡️ **Leitura Sanitizada em Sandbox** | Renderização de e-mails HTML higienizada via `nh3` dentro de `iframe sandbox`, bloqueando execução de scripts (`XSS`), formulários maliciosos e rastreadores. |
| 🖨️ **Exportação `.EML`, `.TXT` e Impressão A4** | Download individual de e-mails no padrão **RFC 5322 (`.eml`)** ou texto puro (`.txt`), além de folha de impressão limpa pronta para PDF/papel. |
| 🔑 **Escolha de Senha e Troca Fácil** | Permite escolher a própria senha do `admin` já na instalação, solicita troca automática no 1º acesso caso tenha usado senha gerada e oferece botão **Alterar Senha** direto no topo da tela. |
| 🚀 **Inicialização Automática no Boot** | Sobe sozinho junto com o sistema operacional no **Linux** (`systemd`), no **Windows + XAMPP** (iniciando inclusive o MySQL do XAMPP em segundo plano) e no **Docker** (`restart: unless-stopped`). |
| ⚙️ **Painel Administrativo Integrado** | Gestão completa de usuários, bloqueio/desbloqueio de contas, redefinição de senhas, monitoramento de sessões ativas, uso de disco e trilha de auditoria. |

---

## 🚀 Instalação "Execute e Saia Usando"

O **PST Viewer** conta com instaladores inteligentes que **verificam os requisitos da máquina**, **avisam o usuário sobre o que falta instalar**, **configuram o banco e os serviços sozinhos** e **exibem o usuário `admin` e a senha gerada no final**.

<div align="center">
  <img src="docs/assets/pstviewer-cli-installer.svg" alt="Instalador Automático do PST Viewer" width="92%" />
</div>

---

### 🐧 Opção 1: Servidor Linux ou Nuvem (Debian / Ubuntu / DietPi / VPS) — *Recomendado*

Ideal para servidores dedicados, máquinas virtuais ou instâncias em nuvem (AWS, Oracle Cloud, DigitalOcean, Hetzner, Proxmox, DietPi).

```bash
# 1. Clone o repositório oficial
git clone https://github.com/frederigi/pstviewer.git
cd pstviewer

# 2. Dê permissão de execução e inicie o instalador automático
chmod +x install.sh
sudo ./install.sh
```

> [!TIP]
> **Modo 100% Autônomo (Sem confirmação manual):**
> Se quiser rodar em scripts de provisionamento sem perguntas na tela, adicione a flag `--yes`:
> ```bash
> sudo ./install.sh --yes
> ```
> Para **escolher ou redefinir a senha do admin e desbloquear a conta** a qualquer momento:
> ```bash
> chmod +x reset_password.sh
> sudo ./reset_password.sh
> ```
> Para **atualizar um servidor Linux/Cloud já instalado via SSH** (mantendo seu banco de dados, usuários e configurações intactos):
> ```bash
> chmod +x update.sh
> sudo ./update.sh
> ```
> *(Se o repositório GitHub for privado, o script faz fallback automático para o Gitea interno `http://10.14.127.225:3000/anderson/pstviewer.git` ou você pode passar a URL como argumento!)*

**O que o `install.sh` faz por você:**
1. Analisa CPU, memória RAM, espaço livre em disco e verifica todos os pacotes APT (`python3-pypff`, `mariadb-server`, `poppler-utils`, `antiword`, `catdoc`, `tesseract-ocr`).
2. Avisa na tela quais pacotes já estão presentes (`[INSTALADO]`) e quais serão baixados (`[PENDENTE]`).
3. Cria o usuário de sistema sem privilégios (`pstviewer`) e diretórios confinados (`/srv/pstviewer/sessions`).
4. Configura o banco **MariaDB/MySQL (`InnoDB utf8mb4`)** e aplica todas as migrações automaticamente.
5. Pergunta qual senha você deseja para o usuário **`admin`** (ou gera uma senha forte caso pressione `ENTER`).
6. Registra e inicia os 3 serviços `systemd` com **inicialização automática no boot**: `pstviewer-web.service`, `pstviewer-worker.service` e `pstviewer-cleaner.timer`.
7. Exibe o quadro verde com a **URL de acesso**, **Usuário (`admin`)** e **Senha configurada**.

---

### 🐳 Opção 2: Docker & Docker Compose (Windows, macOS, Linux ou Cloud)

A maneira mais rápida de rodar em **qualquer sistema operacional** com **100% das dependências C (`libpff`, `poppler`, `antiword`, `tesseract`) e banco MariaDB 11 já embutidos**:

```bash
# 1. Clone o repositório
git clone https://github.com/frederigi/pstviewer.git
cd pstviewer

# 2. Suba toda a infraestrutura (Banco MariaDB + Web + Worker PST + Cleaner)
docker compose up -d --build
```

```bash
# 3. Exiba ou gere a credencial do usuário Administrador (admin)
docker exec -it pstviewer-web /opt/pstviewer/venv/bin/python /opt/pstviewer/scripts/create_admin.py
```

* 🌐 **Endereço de Acesso:** `http://localhost:8085`

---

### 💻 Opção 3: Instalação do Zero no Windows com XAMPP (ou MySQL Local)

Ideal para quem deseja rodar o sistema localmente no Windows aproveitando o banco **MySQL/MariaDB do XAMPP** (sem precisar configurar banco de dados manualmente nem criar tabelas no phpMyAdmin).

> [!NOTE]
> **Como o PST Viewer usa o XAMPP?**
> O PST Viewer é uma aplicação **Python (FastAPI)** com servidor web próprio (`Uvicorn`). Ele **não usa o Apache/PHP** (`htdocs`), mas **usa automaticamente o banco de dados MySQL/MariaDB do XAMPP** na porta `3306` (usuário padrão `root` sem senha).

#### Passo 1: Instalar os 2 requisitos base no Windows (caso ainda não tenha)

Se a máquina estiver totalmente do zero, instale via terminal (**PowerShell**) com um único comando via `winget` (ou baixe pelos instaladores oficiais):

```powershell
# Instala o XAMPP, o Python 3.12 e o Git automaticamente no Windows:
winget install -e --id ApacheFriends.Xampp.8.2
winget install -e --id Python.Python.3.12
winget install -e --id Git.Git
```

#### Passo 2: Baixar o Projeto e Iniciar o MySQL do XAMPP

1. Abra o **XAMPP Control Panel** e clique em **Start** apenas na linha **MySQL** (até ficar verde na porta `3306`).
   *(Se o XAMPP estiver em `C:\xampp`, o próprio instalador do Passo 3 consegue iniciar o MySQL sozinho caso você esqueça!)*
2. No **PowerShell** ou **Prompt de Comando (CMD)**, baixe o projeto na pasta de sua preferência:

```powershell
git clone https://github.com/frederigi/pstviewer.git
cd pstviewer
```

#### Passo 3: Executar o Instalador Automático (`install_windows_xampp.bat`)

Você pode dar **duplo clique** no arquivo `install_windows_xampp.bat` na pasta do projeto ou executá-lo pelo terminal:

```powershell
.\install_windows_xampp.bat
```

> [!TIP]
> **Preferindo rodar direto via Python (Windows, Linux ou macOS com MySQL local):**
> ```powershell
> # Cria o ambiente virtual, instala as dependências e executa o assistente:
> python -m venv venv
> .\venv\Scripts\activate
> pip install -r requirements.txt
> python setup_and_run.py
> ```

**O que o `install_windows_xampp.bat` + `setup_and_run.py` fazem sozinhos do zero:**
1. **Verificam a máquina:** Checam a versão do Python (oferecendo instalar via `winget` se ausente), o espaço livre em disco e instalam as bibliotecas pré-compiladas (`--only-binary=:all:`) sem exigir compilador C++ ou Rust.
2. **Iniciam e conectam no MySQL do XAMPP (`127.0.0.1:3306`):** Se o MySQL do `C:\xampp` estiver parado, o script o inicia automaticamente em segundo plano; em seguida, conecta com o usuário `root` e cria o banco `pstviewer` (`utf8mb4_unicode_ci`) sem que você precise abrir o phpMyAdmin.
3. **Criam o ambiente isolado (`venv`) e o arquivo `config/pstviewer.env`:** Configuram automaticamente as pastas temporárias locais (`./storage/sessions`, `./storage/quarantine`, `./storage/logs`).
4. **Executam as migrações:** Criam todas as tabelas InnoDB e índices `FULLTEXT` automaticamente.
5. **Configuram o usuário Administrador:** Perguntam qual senha você deseja para o **`admin`** (ou geram uma senha forte caso você pressione `ENTER`).
6. **Iniciam os 3 Serviços em Segundo Plano e Registram no Boot do Windows:** Sobem o Servidor Web (`http://127.0.0.1:8085`), o Worker de Extração PST e o Guardião de Limpeza de forma **100% desacoplada do terminal** (`pythonw.exe` + inicialização automática ao ligar o Windows, subindo inclusive o MySQL do XAMPP sozinho). **Você pode fechar o PowerShell/CMD tranquilamente e o sistema continuará funcionando!**

**Atalhos de 1 clique e comandos úteis no Windows:**

* 🔑 **`reset_admin_password.bat`** *(duplo clique)*: Escolhe ou gera uma nova senha para o usuário `admin` e garante que o servidor esteja rodando.
* 🛑 **`stop_windows.bat`** *(duplo clique)*: Encerra imediatamente todos os processos em segundo plano do PST Viewer.

```powershell
# Ver se os serviços estão rodando em segundo plano e quais os PIDs:
.\venv\Scripts\python.exe setup_and_run.py --status

# Parar todos os serviços em segundo plano:
.\venv\Scripts\python.exe setup_and_run.py --stop

# Escolher ou gerar uma nova senha para o usuário 'admin':
.\venv\Scripts\python.exe setup_and_run.py --reset-admin
```

---

## 🏗️ Arquitetura e Fluxo de Dados

```mermaid
flowchart LR
    subgraph Cliente["🌐 Navegador do Usuário"]
        UI["Interface Web Outlook\n(SPA Vanilla JS + CSP)"]
    end

    subgraph Servidor["⚙️ PST Viewer Server (FastAPI + Daemons)"]
        API["FastAPI Web Server\n(Uvicorn :8085)"]
        WRK["PST Worker Daemon\n(Extração pypff + Anexos)"]
        CLN["Cleaner Daemon\n(Expurgo a cada 60s)"]
    end

    subgraph Storage["🔒 Armazenamento Temporário Isolado"]
        FS[("/srv/pstviewer/sessions/<uuid>\nPermissão 0700 | PST 0400")]
        DB[("MariaDB / MySQL InnoDB\nUTF8MB4 + Índices FULLTEXT")]
    end

    UI -- "1. Upload Streaming (1 MiB)\nValidação !BDN + SHA-256" --> API
    API -- "2. Grava PST e enfileira Job" --> FS
    API -- "3. Consulta Pastas, E-mails e Busca" --> DB
    WRK -- "4. Lê árvore MAPI (libpff)\ne extrai texto PDF/Office" --> FS
    WRK -- "5. Salva lotes (READY_PARTIAL)" --> DB
    CLN -- "6. Expurga Disco + MySQL\nno Logout ou Inatividade" --> FS
    CLN -- "7. Remove registros expirados" --> DB
```

---

## 🔒 Segurança, Isolamento e Descarte Automático

> [!WARNING]
> **Regra de Arquitetura — Proibição Estrita de SQLite:**
> Por exigência de concorrência, integridade transacional (`SAVEPOINT` por mensagem/anexo) e índices `FULLTEXT`, o sistema opera **exclusivamente com MySQL / MariaDB (`InnoDB`)**. Qualquer tentativa de configurar SQLite é bloqueada imediatamente na inicialização.

* **Validação Binária Real (`!BDN`):** Arquivos enviados com extensão `.pst` falsa são rejeitados nos primeiros `564 bytes` durante o streaming na quarentena antes mesmo de ocupar disco.
* **Proteção contra *Zip Bomb* e Anexos Criptografados:** Pacotes Office (`.docx`, `.xlsx`, `.pptx`) e arquivos `.zip` têm taxa de compressão e quantidade de entradas inspecionadas antes da extração textual.
* **Senhas com Hash `Argon2id`:** Autenticação com bloqueio temporário automático após tentativas inválidas (`login_lockout_minutes`), cookies `HttpOnly` + `SameSite=Lax` e validação de token `X-CSRF-Token`.
* **Auditoria Sanitizada:** A tabela `audit_logs` e o arquivo `/var/log/pstviewer/audit/audit.log` registram eventos operacionais (`LOGIN_SUCCESS`, `UPLOAD_DONE`, `EXTRACT_DONE`, `SESSION_PURGED`, `AUTHZ_DENIED`), filtrando qualquer senha, token ou corpo de mensagem.

---

## 🛠️ Comandos de Gerenciamento e Administração

### Atualizar Servidor Linux / Nuvem via SSH (`update.sh`)

```bash
# 1. Conceda permissão de execução (se necessário)
chmod +x update.sh

# 2. Atualize a partir do GitHub oficial:
sudo ./update.sh

# OU atualize a partir do seu Gitea interno (ideal enquanto o GitHub estiver privado):
sudo ./update.sh http://10.14.127.225:3000/anderson/pstviewer.git
```

> [!NOTE]
> **Repositório Privado vs. Público no GitHub:**
> O GitHub não aceita mais senhas de conta via terminal (`Password authentication is not supported`). Se o seu repositório no GitHub for privado, torne-o público em **Settings -> Change visibility -> Make public**, ou use o seu **Gitea** na rede interna (`http://10.14.127.225:3000/anderson/pstviewer.git`), ou informe um Personal Access Token (PAT).

### Gerenciar Serviços no Linux (`systemd`)

```bash
# Verificar o status em tempo real dos 3 serviços
sudo systemctl status pstviewer-web.service pstviewer-worker.service pstviewer-cleaner.timer

# Acompanhar os logs do extrator PST em tempo real
sudo journalctl -u pstviewer-worker.service -f

# Reiniciar a aplicação web e o worker de processamento
sudo systemctl restart pstviewer-web.service pstviewer-worker.service
```

### Gerenciar Usuários Administradores via CLI

```bash
# Criar novo administrador ou redefinir a senha do usuário 'admin'
sudo PYTHONPATH=/opt/pstviewer PSTVIEWER_ENV_FILE=/opt/pstviewer/config/pstviewer.env \
  /opt/pstviewer/venv/bin/python /opt/pstviewer/scripts/create_admin.py --username admin

# Definir uma senha específica manualmente
sudo PYTHONPATH=/opt/pstviewer PSTVIEWER_ENV_FILE=/opt/pstviewer/config/pstviewer.env \
  /opt/pstviewer/venv/bin/python /opt/pstviewer/scripts/create_admin.py --username admin --password "SuaSenhaForteAqui!"
```

### Executar o Expurgo Manual de Sessões Expiradas

```bash
sudo PYTHONPATH=/opt/pstviewer PSTVIEWER_ENV_FILE=/opt/pstviewer/config/pstviewer.env \
  /opt/pstviewer/venv/bin/python -m app.workers.cleaner_daemon --once
```

---

## 📂 Estrutura de Diretórios do Repositório

```ini
pstviewer/
├── app/
│   ├── api/                  # Endpoints REST (Auth, Sessões, Leitor, Busca Global, Exportação, Admin)
│   ├── auth/                 # Segurança Argon2id, sessões, CSRF e controle de acesso por usuário
│   ├── core/                 # Carregamento de ambiente (.env) e motor de auditoria LGPD
│   ├── database/             # Modelos SQLAlchemy 2.0, conexão PyMySQL e migrações automáticas
│   ├── services/             # Extrator MAPI (pypff), extrator de anexos, sanitizador HTML e limpeza
│   ├── static/               # Folha de estilo Fluent UI (outlook.css) e lógica SPA (app.js)
│   ├── templates/            # Interface web responsiva (index.html)
│   ├── workers/              # Daemons de processamento (pst_worker.py) e limpeza (cleaner_daemon.py)
│   └── main.py               # Inicialização FastAPI e políticas Content-Security-Policy (CSP)
├── config/
│   └── pstviewer.env.example # Modelo documentado de variáveis de ambiente
├── database/
│   └── schema_v1.sql         # DDL completo MySQL/MariaDB InnoDB UTF8MB4
├── docs/assets/              # Ilustrações vetoriais da interface e do instalador para documentação
├── scripts/                  # Utilitários CLI (create_admin.py) e suítes de testes automatizados
├── Dockerfile                # Imagem Debian Bookworm com libpff, poppler, antiword e tesseract
├── docker-compose.yml        # Orquestração completa pronta para uso
├── install.sh                    # Instalador automático bilíngue (PT/EN) para Linux / Cloud VPS
├── update.sh                     # Atualizador rápido via SSH para servidores Linux / Cloud
├── reset_password.sh             # Script rápido Linux para redefinir senha do admin e desbloquear conta
├── install_windows_xampp.bat     # Instalador e inicializador automático (1 clique) para Windows + XAMPP
├── reset_admin_password.bat      # Atalho de 1 clique no Windows para escolher/redefinir a senha do admin
├── stop_windows.bat              # Atalho de 1 clique no Windows para encerrar os serviços em background
├── setup_and_run.py              # Assistente bilíngue (PT/EN) para execução com MySQL local / XAMPP
├── README.md                     # Documentação completa em Português (com barra interativa de idioma)
├── README.en.md                  # Full documentation in English (with interactive language bar)
└── requirements.txt              # Dependências Python com suporte a pacotes binários pré-compilados
```

---

<div align="center">
  <sub>Desenvolvido por <strong>Anderson Gonçalez</strong> — Tecnologia da Informação (B.T.I.)</sub>
</div>
