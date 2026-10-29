#!/usr/bin/env python3
"""
PST Viewer — Assistente Inteligente de Diagnóstico, Instalação e Inicialização.
Compatível com Windows (XAMPP / MySQL Server / MariaDB), Linux e Nuvem.

Inteligência de Adaptação a Diferentes Versões:
  1. Detecta a versão exata do Python (3.10 a 3.14+) e busca sempre pacotes binários
     pré-compilados (.whl) compatíveis com a versão do usuário, sem exigir compilador C++/Rust.
  2. Inspeciona as versões já instaladas de cada biblioteca e informa o que está [OK],
     o que será [ATUALIZADO] e o que será [INSTALADO].
  3. Detecta automaticamente o MySQL/MariaDB (inclusive portas 3306, 3307, 3308 e diferentes
     versões do XAMPP como MariaDB 10.4+, 10.6+, 11.x ou MySQL 5.7/8.0/8.4).
  4. Adapta automaticamente o limite mínimo de espaço em disco conforme a máquina do usuário.
  5. Cria o usuário `admin`, exibe login e senha em destaque e inicia os 3 serviços.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version as pkg_version
import os
import platform
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
ENV_FILE = CONFIG_DIR / "pstviewer.env"
STORAGE_ROOT = PROJECT_ROOT / "storage"

REQUIRED_LIBRARIES: List[Tuple[str, str, str]] = [
    ("fastapi", "fastapi", "0.115.0"),
    ("uvicorn[standard]", "uvicorn", "0.30.0"),
    ("sqlalchemy", "sqlalchemy", "2.0.0"),
    ("pymysql", "pymysql", "1.1.0"),
    ("cryptography", "cryptography", "41.0.0"),
    ("argon2-cffi", "argon2-cffi", "23.1.0"),
    ("python-multipart", "python-multipart", "0.0.9"),
    ("jinja2", "jinja2", "3.1.0"),
    ("nh3", "nh3", "0.2.14"),
    ("charset-normalizer", "charset-normalizer", "3.2.0"),
    ("striprtf", "striprtf", "0.0.26"),
    ("python-docx", "python-docx", "1.1.0"),
    ("openpyxl", "openpyxl", "3.1.0"),
    ("python-pptx", "python-pptx", "1.0.0"),
    ("pydantic", "pydantic", "2.7.0"),
    ("pydantic-settings", "pydantic-settings", "2.2.0"),
]


def _banner(title: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {title}")
    print("=" * 76)


def _parse_ver(v_str: str) -> Tuple[int, ...]:
    parts = []
    for item in v_str.split("."):
        num = "".join(ch for ch in item if ch.isdigit())
        if num:
            parts.append(int(num))
    return tuple(parts) or (0,)


def _get_installed_version(dist_name: str) -> Optional[str]:
    try:
        return pkg_version(dist_name)
    except PackageNotFoundError:
        return None


def check_system_requirements() -> Dict[str, object]:
    """Faz diagnóstico completo de versão do Python, disco, bibliotecas e ferramentas."""
    _banner("1. DIAGNÓSTICO INTELIGENTE DE REQUISITOS E VERSÕES DA MÁQUINA")

    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    os_desc = f"{platform.system()} {platform.release()} ({platform.machine()})"
    disk = shutil.disk_usage(PROJECT_ROOT)
    free_gb = round(disk.free / (1024 ** 3), 2)

    print(f"  • Sistema Operacional : {os_desc}")
    print(f"  • Interpretador Python: v{py_ver} ({sys.executable})")
    if not py_ok:
        print("    [ERRO] Versão muito antiga! O sistema requer Python 3.10 ou superior.")
    elif sys.version_info >= (3, 14):
        print("    [INFO] Python 3.14+ detectado -> Modo de pacotes binários pré-compilados ativado.")
    else:
        print("    [OK]   Versão do Python totalmente compatível.")

    print(f"  • Espaço Livre Disco  : {free_gb} GB", end="")
    if free_gb < 2.0:
        print(" [AVISO: Pouco espaço livre! Recomendado >= 5 GB]")
    elif free_gb < 15.0:
        print(" [OK - Cota mínima será ajustada automaticamente para seu disco]")
    else:
        print(" [OK]")

    to_install: List[str] = []
    print("\n  Status das bibliotecas Python necessárias:")
    for pip_spec, dist_name, min_ver in REQUIRED_LIBRARIES:
        inst_v = _get_installed_version(dist_name)
        if inst_v is None:
            print(f"    [AUSENTE]    {dist_name:<22} (requer >= {min_ver}) -> será instalado")
            to_install.append(f"{pip_spec}>={min_ver}")
        elif _parse_ver(inst_v) < _parse_ver(min_ver):
            print(f"    [ATUALIZAR]  {dist_name:<22} (atual: v{inst_v} | requer >= {min_ver})")
            to_install.append(f"{pip_spec}>={min_ver}")
        else:
            print(f"    [OK]         {dist_name:<22} (v{inst_v} instalada)")

    has_pypff = False
    try:
        import pypff  # type: ignore
        has_pypff = True
        print(f"    [OK]         {'libpff-python (pypff)':<22} (v{pypff.get_version()} nativa ativa)")
    except ImportError:
        print(f"    [AUSENTE]    {'libpff-python (pypff)':<22} (motor nativo PST -> será instalado)")
        to_install.append("libpff-python")

    print("\n  Utilitários externos opcionais (indexação extra de PDF / OCR / DOC legado):")
    for bin_name, desc in (
        ("pdftotext", "Extração de texto de PDFs (Poppler)"),
        ("tesseract", "OCR de imagens e PDFs escaneados"),
        ("antiword", "Leitura de arquivos .DOC do Word 97-2003"),
    ):
        found = shutil.which(bin_name)
        if found:
            print(f"    [DETECTADO]  {bin_name:<12} -> {desc}")
        else:
            print(f"    [OPCIONAL]   {bin_name:<12} -> Não instalado (o sistema funcionará normalmente sem ele)")

    return {
        "py_ok": py_ok,
        "free_gb": free_gb,
        "to_install": to_install,
        "has_pypff": has_pypff,
    }


def install_missing_python_deps(to_install: List[str]) -> bool:
    """
    Instala pacotes ausentes priorizando wheels binários pré-compilados (--only-binary=:all:),
    evitando falhas por falta de compilador C++/Rust na máquina do usuário.
    """
    _banner("2. INSTALAÇÃO INTELIGENTE DE DEPENDÊNCIAS PYTHON")

    print("  -> Atualizando gerenciador pip...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Tentativa 1: Rápida em lote forçando apenas binários pré-compilados (.whl)
    print("  -> Baixando pacotes binários pré-compilados compatíveis com seu Python...")
    cmd_binary = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--only-binary=:all:",
        "--prefer-binary",
        *to_install,
    ]
    res = subprocess.run(cmd_binary)
    if res.returncode == 0:
        print("  [OK] Todas as dependências foram instaladas com sucesso via pacotes pré-compilados!")
        return True

    # Tentativa 2: Pacote por pacote com fallback inteligente caso algum pacote seja pure-python sem wheel
    print("\n  [INFO] Ajustando instalação individual para compatibilidade de versão...")
    failed_pkgs: List[str] = []
    for spec in to_install:
        pkg_base = spec.split(">=")[0].split("==")[0]
        print(f"    • Instalando {pkg_base}...", end=" ", flush=True)
        r1 = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--only-binary=:all:", "--prefer-binary", spec],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if r1.returncode == 0:
            print("[OK - Binário]")
            continue

        r2 = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--prefer-binary", spec],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if r2.returncode == 0:
            print("[OK]")
            continue

        # Último fallback sem trava de versão mínima
        r3 = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--prefer-binary", pkg_base],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if r3.returncode == 0:
            print("[OK - Versão Adaptada]")
        else:
            print("[FALHOU]")
            failed_pkgs.append(pkg_base)

    if failed_pkgs:
        print(
            f"\n  [ERRO] Não foi possível instalar: {', '.join(failed_pkgs)}"
            f"\n  Motivo provável: Sua versão do Python ({sys.version.split()[0]}) ainda não possui"
            "\n  pacote pré-compilado para essa biblioteca e sua máquina não tem Visual C++ Build Tools."
            "\n  Solução recomendada: Instale o Python 3.12 LTS (winget install Python.Python.3.12)"
            "\n  ou execute via Docker (docker compose up -d --build)."
        )
        return False

    return True


def _detect_open_mysql_port(host: str, preferred_port: int) -> int:
    """Verifica a porta preferida e, se fechada, escaneia portas alternativas comuns (3306, 3307, 3308)."""
    candidates = [preferred_port] + [p for p in (3306, 3307, 3308) if p != preferred_port]
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return port
    return preferred_port


def configure_database_and_env(
    db_host: str,
    db_port: int,
    db_user: str,
    db_password: str,
    db_name: str,
    bind_port: int,
    interactive: bool,
) -> Path:
    _banner("3. DETECÇÃO E CONFIGURAÇÃO DO MYSQL / MARIADB (XAMPP / LOCAL / NUVEM)")
    import pymysql

    if ENV_FILE.is_file():
        print(f"  [OK] Configuração existente carregada de: {ENV_FILE}")
        return ENV_FILE

    detected_port = _detect_open_mysql_port(db_host, db_port)
    if detected_port != db_port:
        print(
            f"  [AUTO-DETECÇÃO] Porta {db_port} fechada, mas banco detectado ativo na porta {detected_port}!"
        )
        db_port = detected_port

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
                cur.execute("SELECT VERSION();")
                ver_row = cur.fetchone()
                db_ver = ver_row[0] if ver_row else "Desconhecida"
                engine_type = "MariaDB" if "mariadb" in db_ver.lower() else "MySQL"
                print(f"  [OK] Conectado com sucesso ao {engine_type} (versão: {db_ver}) em {db_host}:{db_port}")

                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
                )
            conn.commit()
            conn.close()
            connected = True
            print(f"  [OK] Banco de dados '{db_name}' (UTF8MB4 InnoDB) verificado e pronto!")
        except Exception as exc:
            print(f"\n  [AVISO] Não foi possível conectar ao MySQL em {db_host}:{db_port} com usuário '{db_user}':")
            print(f"          Detalhe: {exc}")
            if not interactive:
                raise RuntimeError(
                    "Falha na conexão com o MySQL/MariaDB. Verifique se o MySQL (XAMPP) está iniciado."
                ) from exc
            print("\n  Por favor, confira se o MySQL está iniciado no painel do XAMPP ou informe as credenciais:")
            db_host = input(f"    Host do MySQL [{db_host}]: ").strip() or db_host
            port_str = input(f"    Porta do MySQL [{db_port}]: ").strip()
            if port_str.isdigit():
                db_port = int(port_str)
            db_user = input(f"    Usuário do MySQL [{db_user}]: ").strip() or db_user
            db_password = input("    Senha do MySQL (pressione Enter se for vazia no XAMPP): ").strip()
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
    print(f"  [OK] Arquivo de ambiente gerado em: {ENV_FILE}")
    return ENV_FILE


def run_migrations_and_adapt_settings(
    env_path: Path, free_gb: float, reset_admin: bool = False
) -> Tuple[str, str]:
    _banner("4. MIGRAÇÕES DO BANCO, AJUSTE DE DISCO E CRIAÇÃO DO ADMIN")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PSTVIEWER_ENV_FILE"] = str(env_path)

    subprocess.check_call([sys.executable, "-m", "app.database.migrations"], env=env)

    # Se o disco local tiver menos de 20 GB livres, adapta min_free_disk_mb automaticamente
    if free_gb < 20.0:
        safe_min_mb = max(512, min(2048, int((free_gb * 1024) * 0.2)))
        adapt_code = (
            "from app.database.session import SessionLocal; "
            "from app.database.models import SystemSetting; "
            "db = SessionLocal(); "
            "row = db.get(SystemSetting, 'min_free_disk_mb'); "
            f"row.setting_value = '{safe_min_mb}' if row else None; "
            "db.commit(); db.close()"
        )
        subprocess.run([sys.executable, "-c", adapt_code], env=env, check=False)
        print(f"  [AUTO-AJUSTE] Cota mínima de espaço livre adaptada para {safe_min_mb} MB conforme seu disco.")

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
        return "admin", "(Senha atual preservada — use --reset-admin se quiser gerar outra)"
    return "admin", admin_pw


def _find_available_http_port(preferred_port: int) -> int:
    """Verifica se a porta HTTP está livre; se estiver ocupada por outro programa, escolhe a próxima."""
    for port in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred_port


def main() -> int:
    parser = argparse.ArgumentParser(description="PST Viewer - Assistente Inteligente Setup & Run")
    parser.add_argument("--yes", "-y", action="store_true", help="Instala tudo sem confirmação interativa")
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
        print("\n[ERRO] Atualize seu Python para 3.10+ antes de continuar.")
        return 1

    to_install: List[str] = status["to_install"]  # type: ignore
    if to_install:
        print(f"\n  [AÇÃO NECESSÁRIA] {len(to_install)} pacote(s) precisam ser instalados ou atualizados.")
        if interactive:
            ans = input("  Deseja que o assistente instale/atualize automaticamente agora? [S/n]: ").strip() or "S"
            if ans.lower() not in ("s", "sim", "y", "yes"):
                print("  Instalação cancelada pelo usuário.")
                return 0
        if not install_missing_python_deps(to_install):
            return 1

    http_port = _find_available_http_port(args.port)
    if http_port != args.port:
        print(f"\n  [AUTO-AJUSTE] A porta {args.port} já estava em uso; utilizando porta livre {http_port}!")

    env_path = configure_database_and_env(
        db_host=args.db_host,
        db_port=args.db_port,
        db_user=args.db_user,
        db_password=args.db_password,
        db_name=args.db_name,
        bind_port=http_port,
        interactive=interactive,
    )

    admin_user, admin_pw = run_migrations_and_adapt_settings(
        env_path,
        free_gb=float(status["free_gb"]),  # type: ignore
        reset_admin=args.reset_admin,
    )

    _banner("SISTEMA PRONTO — CREDENCIAIS DO ADMINISTRADOR")
    print(f"  • Endereço de Acesso : http://127.0.0.1:{http_port}")
    print(f"  • Usuário Admin      : {admin_user}")
    print(f"  • Senha Admin        : {admin_pw}")
    print("=" * 76)

    if args.setup_only:
        return 0

    print("\nIniciando serviços integrados (Servidor Web + Worker PST + Guardião de Limpeza)...")
    print(f"Abra seu navegador em: http://127.0.0.1:{http_port}")
    print("Pressione Ctrl+C a qualquer momento para encerrar os serviços.\n")

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
                str(http_port),
            ],
            env=env,
        )
        procs.append(web_proc)

        while True:
            time.sleep(1)
            if web_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        print("\nEncerrando todos os serviços do PST Viewer com segurança...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
