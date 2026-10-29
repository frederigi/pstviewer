#!/usr/bin/env python3
"""
PST Viewer — Assistente de Instalação e Inicialização Multiplataforma (Windows / Linux / Cloud).
Suporta MySQL/MariaDB local (incluindo banco MySQL do XAMPP, MariaDB Server ou MySQL em nuvem).

Fluxo automático:
  1. Verifica requisitos da máquina (Python, espaço em disco, pacotes Python, motor pypff e banco MySQL).
  2. Exibe diagnóstico claro ao usuário informando o que está pronto e o que falta instalar.
  3. Instala automaticamente pacotes Python ausentes (requirements.txt) se autorizado.
  4. Conecta ao MySQL/MariaDB (detecta automaticamente MySQL padrão na porta 3306 ou solicita credenciais),
     cria o banco `pstviewer` (UTF8MB4 InnoDB) e gera `config/pstviewer.env`.
  5. Executa as migrações versionadas (`app.database.migrations`).
  6. Cria o usuário `admin` e apresenta na tela o login, senha e URL de acesso.
  7. Inicia os 3 processos integrados (Servidor Web FastAPI + Worker PST + Guardião de Limpeza).
"""

from __future__ import annotations

import argparse
import os
import platform
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
ENV_FILE = CONFIG_DIR / "pstviewer.env"
STORAGE_ROOT = PROJECT_ROOT / "storage"


def _banner(title: str) -> None:
    print("\n" + "=" * 74)
    print(f"  {title}")
    print("=" * 74)


def check_system_requirements() -> dict:
    """Inspeciona Python, espaço livre, pacotes do requirements.txt e módulo pypff."""
    _banner("1. VERIFICAÇÃO DE REQUISITOS DA MÁQUINA")

    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    os_desc = f"{platform.system()} {platform.release()} ({platform.machine()})"
    disk = shutil.disk_usage(PROJECT_ROOT)
    free_gb = round(disk.free / (1024 ** 3), 2)

    print(f"  • Sistema Operacional : {os_desc}")
    print(f"  • Versão do Python    : {py_ver} {'[OK]' if py_ok else '[REQUER >= 3.10]'}")
    print(f"  • Espaço Livre Disco  : {free_gb} GB")

    req_file = PROJECT_ROOT / "requirements.txt"
    missing_pip = []
    module_map = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "sqlalchemy": "sqlalchemy",
        "pymysql": "pymysql",
        "cryptography": "cryptography",
        "argon2-cffi": "argon2",
        "python-multipart": "multipart",
        "jinja2": "jinja2",
        "nh3": "nh3",
        "charset-normalizer": "charset_normalizer",
        "striprtf": "striprtf",
        "python-docx": "docx",
        "openpyxl": "openpyxl",
        "python-pptx": "pptx",
        "pydantic": "pydantic",
        "pydantic-settings": "pydantic_settings",
    }

    print("\n  Status das bibliotecas Python:")
    for pkg_name, import_name in module_map.items():
        try:
            __import__(import_name)
            print(f"    [OK]       {pkg_name}")
        except ImportError:
            print(f"    [PENDENTE] {pkg_name}")
            missing_pip.append(pkg_name)

    has_pypff = False
    try:
        import pypff  # type: ignore
        has_pypff = True
        print(f"    [OK]       pypff (libpff nativo v{pypff.get_version()})")
    except ImportError:
        print("    [AVISO]    pypff (libpff-python) não detectado no ambiente atual.")

    return {
        "py_ok": py_ok,
        "free_gb": free_gb,
        "missing_pip": missing_pip,
        "has_pypff": has_pypff,
        "req_file": req_file,
    }


def install_missing_python_deps(req_file: Path, has_pypff: bool) -> None:
    _banner("2. INSTALANDO DEPENDÊNCIAS PYTHON")
    print("  -> Instalando pacotes de requirements.txt via pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
    if not has_pypff:
        print("  -> Tentando instalar libpff-python (pypff) via pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "libpff-python"])
        except Exception:
            print(
                "\n  [NOTA IMPORTANTE SOBRE PYPFF NO WINDOWS]:"
                "\n  O pacote C 'libpff-python' requer compilador C++ no Windows ou execução via Docker/Linux."
                "\n  Se preferir rodar no Windows sem compilar C++, utilize: docker compose up -d --build"
            )


def configure_database_and_env(
    db_host: str,
    db_port: int,
    db_user: str,
    db_password: str,
    db_name: str,
    bind_port: int,
    interactive: bool,
) -> Path:
    _banner("3. CONFIGURAÇÃO DO BANCO MYSQL / MARIADB (LOCAL / XAMPP / NUVEM)")
    import pymysql

    if ENV_FILE.is_file():
        print(f"  [OK] Arquivo de configuração existente encontrado em: {ENV_FILE}")
        return ENV_FILE

    # Tenta conectar automaticamente com os parâmetros informados (padrão root sem senha = XAMPP/local)
    connected = False
    while not connected:
        try:
            conn = pymysql.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                charset="utf8mb4",
                connect_timeout=5,
            )
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                )
            conn.commit()
            conn.close()
            connected = True
            print(f"  [OK] Conectado ao MySQL/MariaDB em {db_host}:{db_port} e banco '{db_name}' pronto!")
        except Exception as exc:
            print(f"\n  [AVISO] Não foi possível conectar ao MySQL em {db_host}:{db_port} com usuário '{db_user}': {exc}")
            if not interactive:
                raise RuntimeError(
                    "Falha na conexão com o MySQL/MariaDB. Certifique-se de que o MySQL (XAMPP ou servidor) está rodando."
                ) from exc
            print("  Informe os dados do seu servidor MySQL/MariaDB (ou inicie o MySQL no painel do XAMPP):")
            db_host = input(f"    Host do MySQL [{db_host}]: ").strip() or db_host
            port_str = input(f"    Porta do MySQL [{db_port}]: ").strip()
            if port_str.isdigit():
                db_port = int(port_str)
            db_user = input(f"    Usuário do MySQL [{db_user}]: ").strip() or db_user
            db_password = input("    Senha do MySQL (Enter se vazia no XAMPP): ").strip()
            db_name = input(f"    Nome do Banco [{db_name}]: ").strip() or db_name

    sessions_dir = (STORAGE_ROOT / "sessions").resolve()
    quarantine_dir = (STORAGE_ROOT / "quarantine").resolve()
    jobs_dir = (STORAGE_ROOT / "jobs").resolve()
    log_dir = (STORAGE_ROOT / "logs").resolve()

    for d in (CONFIG_DIR, sessions_dir, quarantine_dir, jobs_dir, log_dir / "application", log_dir / "audit"):
        d.mkdir(parents=True, exist_ok=True)

    secret_key = secrets.token_hex(32)
    env_content = "\n".join(
        [
            "PSTVIEWER_ENV=production",
            'PSTVIEWER_APP_NAME="PST Viewer"',
            "PSTVIEWER_BIND_HOST=0.0.0.0",
            f"PSTVIEWER_BIND_PORT={bind_port}",
            f"PSTVIEWER_DB_HOST={db_host}",
            f"PSTVIEWER_DB_PORT={db_port}",
            f"PSTVIEWER_DB_NAME={db_name}",
            f"PSTVIEWER_DB_USER={db_user}",
            f"PSTVIEWER_DB_PASSWORD={db_password}",
            f"PSTVIEWER_SESSIONS_DIR={sessions_dir.as_posix()}",
            f"PSTVIEWER_QUARANTINE_DIR={quarantine_dir.as_posix()}",
            f"PSTVIEWER_JOBS_DIR={jobs_dir.as_posix()}",
            f"PSTVIEWER_LOG_DIR={log_dir.as_posix()}",
            f"PSTVIEWER_SECRET_KEY={secret_key}",
            "PSTVIEWER_COOKIE_SECURE=false",
            "PSTVIEWER_AUTH_SESSION_HOURS=8",
            "PSTVIEWER_MAX_LOGIN_ATTEMPTS=5",
            "PSTVIEWER_LOGIN_LOCKOUT_MINUTES=15",
            "",
        ]
    )
    ENV_FILE.write_text(env_content, encoding="utf-8")
    print(f"  [OK] Arquivo {ENV_FILE} gerado com sucesso.")
    return ENV_FILE


def run_migrations_and_create_admin(env_path: Path, reset_admin: bool = False) -> Tuple[str, str]:
    _banner("4. MIGRAÇÕES DO BANCO E CRIAÇÃO DO ADMINISTRADOR")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PSTVIEWER_ENV_FILE"] = str(env_path)

    subprocess.check_call([sys.executable, "-m", "app.database.migrations"], env=env)

    # Ajusta espaço livre mínimo para ambientes locais de teste se necessário
    admin_pw = secrets.token_urlsafe(10)
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "create_admin.py"),
        "--username",
        "admin",
        "--password",
        admin_pw,
    ]
    if not reset_admin:
        cmd.append("--if-not-exists")

    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    out = proc.stdout or ""
    if "já está cadastrado" in out and not reset_admin:
        return "admin", "(Senha preservada — use --reset-admin para gerar nova senha)"
    return "admin", admin_pw


def main() -> int:
    parser = argparse.ArgumentParser(description="PST Viewer - Setup & Run Assistido")
    parser.add_argument("--yes", "-y", action="store_true", help="Não pede confirmação interativa")
    parser.add_argument("--setup-only", action="store_true", help="Apenas instala e configura sem iniciar o servidor")
    parser.add_argument("--reset-admin", action="store_true", help="Gera uma nova senha para o usuário admin")
    parser.add_argument("--port", type=int, default=8085, help="Porta HTTP da aplicação (padrão: 8085)")
    parser.add_argument("--db-host", default="127.0.0.1", help="Host do MySQL/MariaDB (padrão: 127.0.0.1)")
    parser.add_argument("--db-port", type=int, default=3306, help="Porta do MySQL/MariaDB (padrão: 3306)")
    parser.add_argument("--db-user", default="root", help="Usuário do MySQL/MariaDB (padrão: root)")
    parser.add_argument("--db-password", default="", help="Senha do MySQL/MariaDB (padrão: vazio para XAMPP)")
    parser.add_argument("--db-name", default="pstviewer", help="Nome do banco (padrão: pstviewer)")
    args = parser.parse_args()

    interactive = (not args.yes) and sys.stdin.isatty()

    status = check_system_requirements()
    if not status["py_ok"]:
        print("\n[ERRO] O PST Viewer requer Python 3.10 ou superior.")
        return 1

    if status["missing_pip"]:
        print(f"\n[AVISO] Faltam {len(status['missing_pip'])} bibliotecas Python: {', '.join(status['missing_pip'])}")
        if interactive:
            ans = input("Deseja instalar automaticamente as dependências Python agora? [S/n]: ").strip() or "S"
            if ans.lower() not in ("s", "sim", "y", "yes"):
                print("Operação cancelada pelo usuário.")
                return 0
        install_missing_python_deps(status["req_file"], status["has_pypff"])

    env_path = configure_database_and_env(
        db_host=args.db_host,
        db_port=args.db_port,
        db_user=args.db_user,
        db_password=args.db_password,
        db_name=args.db_name,
        bind_port=args.port,
        interactive=interactive,
    )

    admin_user, admin_pw = run_migrations_and_create_admin(env_path, reset_admin=args.reset_admin)

    _banner("PRONTO PARA USO — CREDENCIAIS DE ACESSO")
    print(f"  • URL Local         : http://127.0.0.1:{args.port}")
    print(f"  • Usuário Admin     : {admin_user}")
    print(f"  • Senha Admin       : {admin_pw}")
    print("=" * 74)

    if args.setup_only:
        return 0

    print("\nIniciando serviços do PST Viewer (Web + Worker PST + Guardião de Limpeza)...")
    print("Pressione Ctrl+C para encerrar todos os serviços.\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PSTVIEWER_ENV_FILE"] = str(env_path)

    procs = []
    try:
        worker_proc = subprocess.Popen(
            [sys.executable, "-m", "app.workers.pst_worker", "--poll-interval", "2.0"],
            env=env,
        )
        procs.append(worker_proc)

        cleaner_proc = subprocess.Popen(
            [sys.executable, "-m", "app.workers.cleaner_daemon", "--interval", "60"],
            env=env,
        )
        procs.append(cleaner_proc)

        web_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(args.port),
            ],
            env=env,
        )
        procs.append(web_proc)

        while True:
            time.sleep(1)
            if web_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        print("\nEncerrando serviços do PST Viewer...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())

