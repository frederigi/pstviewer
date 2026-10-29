# PST Viewer — Leitor Web Temporário de Arquivos Microsoft Outlook (.PST)

O **PST Viewer** é uma aplicação web corporativa para **abertura, leitura, pesquisa avançada, impressão e exportação pontual de arquivos Microsoft Outlook PST**, com interface inspirada no Microsoft Outlook e arquitetura de **retenção zero (armazenamento estritamente temporário)**.

Diferente de soluções de arquivamento permanente, o PST Viewer foi projetado para que o usuário envie seu arquivo `.pst`, consulte pastas, e-mails e anexos diretamente no navegador e, ao encerrar a consulta (ou por expiração automática de inatividade), **todos os dados extraídos no banco e arquivos em disco sejam fisicamente eliminados**.

---

## Principais Funcionalidades

- **Interface Estilo Microsoft Outlook (3 Painéis):**
  - Árvore hierárquica de pastas com classificação inteligente (*Caixa de Entrada*, *Itens Enviados*, *Rascunhos*, *Arquivo*, *Lixo Eletrônico*, *Itens Excluídos*) e contadores.
  - Lista paginada de mensagens com ordenação por data, remetente, assunto ou tamanho.
  - Painel de leitura seguro em `iframe` isolado (`sandbox`), com bloqueio de scripts e proteção contra XSS (`nh3`).
- **Abertura Progressiva (`READY_PARTIAL`):**
  - O usuário não precisa aguardar o fim da extração de PSTs grandes: assim que a primeira pasta é processada, a leitura e a navegação já são liberadas em tempo real enquanto o worker conclui o restante em segundo plano.
- **Pesquisa Global e Indexação de Conteúdo de Anexos:**
  - Busca textual (`FULLTEXT` + filtros combinados por pasta, remetente, destinatário, período e presença de anexo).
  - Extração e indexação automática do texto interno de anexos **PDF, DOCX, XLSX, PPTX, TXT, CSV, HTML, RTF, DOC e ZIP**, com proteção contra *Zip Bombs* e detecção de arquivos protegidos por senha.
- **Visualização, Exportação e Impressão:**
  - Pré-visualização integrada de anexos (PDF, imagens e textos) e download individual sob demanda.
  - Exportação fiel de mensagens individuais em formato **`.eml` (RFC 5322)** ou **`.txt`**.
  - Modo de impressão limpa formatado para PDF/impressora.
- **Expurgo Automático e Segurança por Design:**
  - Validação binária da assinatura mágica `!BDN` (ANSI 32-bit e Unicode 64-bit) em streaming de 1 MiB antes de aceitar o upload.
  - Isolamento estrito por usuário e por sessão (`UUID v4`), impedindo acesso cruzado (`AUTHZ_DENIED` auditado).
  - Guardião independente de limpeza (`cleaner_daemon`) que elimina do disco e do MySQL sessões encerradas, expiradas por inatividade ou órfãs.
- **Painel Administrativo e Auditoria:**
  - Gestão de usuários, bloqueio/desbloqueio de contas, redefinição de senhas, monitoramento de sessões ativas, métricas de disco e trilha de auditoria sem exposição de conteúdo privado.

---

## Arquitetura Técnica

| Camada | Tecnologia |
| :--- | :--- |
| **Backend & API** | Python 3.10+ / FastAPI / Uvicorn |
| **Banco de Dados** | MySQL 8.0+ ou MariaDB 10.6+ (`InnoDB`, `utf8mb4`, `FULLTEXT`) — *SQLite é bloqueado por arquitetura* |
| **Motor de Leitura PST** | `libpff` / `pypff` nativo + parser MAPI e RFC 5322 (`transport_headers`) |
| **Extratores de Anexos** | `poppler-utils` (`pdftotext`/`pdfinfo`), `python-docx`, `openpyxl`, `python-pptx`, `striprtf`, `antiword`/`catdoc`, `tesseract-ocr` (opcional) |
| **Frontend** | SPA Vanilla JS + CSS corporativo inspirado no Outlook (sem dependência de CDNs externos) |

---

## Instalação Rápida ("Execute e Saia Usando")

O projeto conta com **3 formas de instalação automatizada**, dependendo do seu ambiente:

### Opção 1: Servidor Linux ou Nuvem (Debian / Ubuntu / DietPi / VPS) — Recomendado

O script unificado `install.sh` verifica os requisitos de hardware e pacotes da máquina, avisa o que precisa ser instalado, configura o MariaDB, cria o ambiente virtual Python, executa as migrações, registra os 3 serviços `systemd` (`pstviewer-web`, `pstviewer-worker` e `pstviewer-cleaner.timer`) e **exibe na tela o usuário `admin` e a senha gerada**.

```bash
git clone https://github.com/frederigi/pstviewer.git
cd pstviewer
chmod +x install.sh
sudo ./install.sh
```

Para instalação 100% autônoma (sem perguntas de confirmação) ou para redefinir a senha do `admin`:

```bash
sudo ./install.sh --yes
sudo ./install.sh --reset-admin
```

---

### Opção 2: Docker & Docker Compose (Windows, macOS, Linux ou Nuvem)

Ideal para rodar em **qualquer sistema operacional** sem precisar instalar bibliotecas C (`libpff`, `poppler`, `antiword`) ou banco de dados manualmente na máquina hospedeira:

```bash
git clone https://github.com/frederigi/pstviewer.git
cd pstviewer
docker compose up -d --build
```

Para ver ou gerar uma nova senha para o administrador no container:

```bash
docker exec -it pstviewer-web /opt/pstviewer/venv/bin/python /opt/pstviewer/scripts/create_admin.py
```

Acesse em: **`http://localhost:8085`**

---

### Opção 3: Assistente Python Local (Usando MySQL do XAMPP, MariaDB ou MySQL Server)

> **Nota sobre XAMPP:** O PST Viewer é escrito em **Python (FastAPI)**, portanto não utiliza o Apache/PHP do XAMPP, mas **funciona perfeitamente utilizando o banco de dados MySQL/MariaDB do XAMPP** (porta `3306`, usuário `root`).

Basta iniciar o módulo **MySQL** no painel do XAMPP (ou ter qualquer MySQL/MariaDB ativo) e executar o assistente interativo:

```bash
python setup_and_run.py
```

O `setup_and_run.py` fará automaticamente:
1. O diagnóstico de requisitos da máquina (Python, espaço em disco, bibliotecas e `pypff`).
2. O aviso ao usuário e instalação automática dos pacotes do `requirements.txt`.
3. A conexão ao MySQL (detecta `127.0.0.1:3306` padrão XAMPP ou pergunta usuário/senha) e criação do banco `pstviewer`.
4. A criação de todas as tabelas e índices via migração automática.
5. A criação do usuário **`admin`**, exibindo a **senha gerada** no terminal.
6. A inicialização conjunta do Servidor Web (`http://127.0.0.1:8085`), do Worker de Extração PST e do Guardião de Limpeza.

---

## Estrutura do Projeto

```text
├── app/
│   ├── api/                  # Rotas FastAPI (Autenticação, Sessões, Leitor, Busca, Exportação, Admin)
│   ├── auth/                 # Hash Argon2id, sessões de autenticação, CSRF e controle de acesso
│   ├── core/                 # Configurações (.env) e trilha de auditoria sanitizada
│   ├── database/             # Modelos SQLAlchemy, engine MySQL InnoDB e migrações automáticas
│   ├── services/             # Motor de extração PST (pypff), sanitizador HTML, anexos e expurgo
│   ├── static/               # Estilos CSS e aplicação SPA JavaScript
│   ├── templates/            # Template principal da interface estilo Outlook
│   ├── workers/              # Daemons de extração em background (pst_worker) e limpeza (cleaner_daemon)
│   └── main.py               # Entrada principal FastAPI e cabeçalhos de segurança (CSP)
├── config/
│   └── pstviewer.env.example # Exemplo de variáveis de ambiente
├── database/
│   └── schema_v1.sql         # Esquema relacional MySQL/MariaDB InnoDB UTF8MB4
├── scripts/                  # Scripts utilitários, criação de admin e bateria de testes integrados
├── Dockerfile                # Imagem containerizada com libpff, poppler e extratores nativos
├── docker-compose.yml        # Orquestração completa (MariaDB + Web + Worker + Cleaner)
├── install.sh                # Instalador automático unificado para servidores Linux/Cloud
├── setup_and_run.py          # Instalador e inicializador assistido multiplataforma (MySQL local/XAMPP)
└── requirements.txt          # Dependências Python
```

---

## Gerenciamento de Serviços (Linux systemd)

Quando instalado via `install.sh` em servidor Linux:

```bash
# Verificar status dos serviços
sudo systemctl status pstviewer-web pstviewer-worker pstviewer-cleaner.timer

# Reiniciar serviços
sudo systemctl restart pstviewer-web pstviewer-worker

# Gerar nova senha para o usuário admin
sudo PYTHONPATH=/opt/pstviewer PSTVIEWER_ENV_FILE=/opt/pstviewer/config/pstviewer.env \
  /opt/pstviewer/venv/bin/python /opt/pstviewer/scripts/create_admin.py --username admin
```

