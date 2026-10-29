#!/usr/bin/env python3
"""
PST Viewer — Assistente Inteligente de Diagnóstico, Instalação e Execução em Segundo Plano.
Compatível com Windows (XAMPP / MySQL Server / MariaDB), Linux e Nuvem.

Destaques:
  1. Verifica versões de Python, espaço em disco, pacotes e banco MySQL/MariaDB.
  2. Instala dependências usando pacotes binários pré-compilados (.whl).
  3. Configura o banco `pstviewer` no MySQL/XAMPP, roda as migrações e cria o usuário `admin`.
  4. Inicia os 3 serviços (Web Server, Worker PST e Cleaner) EM SEGUNDO PLANO (Background Daemon),
     totalmente desacoplados do terminal — o usuário pode fechar o PowerShell/CMD à vontade!
  5. Registra inicialização automática no logon do Windows para continuar ativo após reiniciar.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version as pkg_version
import json
import os
import platform
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from typing import Dict, List, Optional, Tuple
import webbrowser

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
ENV_FILE = CONFIG_DIR / "pstviewer.env"
STORAGE_ROOT = PROJECT_ROOT / "storage"
PID_FILE = STORAGE_ROOT / "logs" / "pstviewer_pids.json"

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


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in (proc.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def stop_background_services(silent: bool = False) -> int:
    """Encerra os processos em segundo plano registrados no arquivo de PID."""
    stopped = 0
    if PID_FILE.is_file():
        try:
            data = json.loads(PID_FILE.read_text(encoding="utf-8"))
            for key in ("web_pid", "worker_pid", "cleaner_pid"):
                pid = int(data.get(key, 0) or 0)
                if _is_pid_running(pid):
                    _kill_pid(pid)
                    stopped += 1
        except Exception:
            pass
        PID_FILE.unlink(missing_ok=True)
    if not silent:
        print(f"  [OK] {stopped} serviço(s) em segundo plano do PST Viewer foram encerrados.")
    return stopped


def get_background_status() -> Dict[str, object]:
    """Retorna se os serviços estão ativos em segundo plano e seus PIDs."""
    if not PID_FILE.is_file():
        return {"running": False}
    try:
        data = json.loads(PID_FILE.read_text(encoding="utf-8"))
        web_pid = int(data.get("web_pid", 0) or 0)
        worker_pid = int(data.get("worker_pid", 0) or 0)
        cleaner_pid = int(data.get("cleaner_pid", 0) or 0)
        port = int(data.get("port", 8085) or 8085)
        web_ok = _is_pid_running(web_pid)
        worker_ok = _is_pid_running(worker_pid)
        cleaner_ok = _is_pid_running(cleaner_pid)
        return {
            "running": (web_ok and worker_ok),
            "web_pid": web_pid if web_ok else None,
            "worker_pid": worker_pid if worker_ok else None,
            "cleaner_pid": cleaner_pid if cleaner_ok else None,
            "port": port,
        }
    except Exception:
        return {"running": False}


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

    return {
        "py_ok": py_ok,
        "free_gb": free_gb,
        "to_install": to_install,
        "has_pypff": has_pypff,
    }


def install_missing_python_deps(to_install: List[str]) -> bool:
    """Instala pacotes ausentes priorizando wheels binários pré-compilados (--only-binary=:all:)."""
    _banner("2. INSTALAÇÃO INTELIGENTE DE DEPENDÊNCIAS PYTHON")

    print("  -> Atualizando gerenciador pip...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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
            f"\n  Solução recomendada: Instale o Python 3.12 LTS (winget install Python.Python.3.12)"
            "\n  ou execute via Docker (docker compose up -d --build)."
        )
        return False

    return True


def _detect_open_mysql_port(host: str, preferred_port: int) -> int:
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
) -> Tuple[Path, int]:
    _banner("3. DETECÇÃO E CONFIGURAÇÃO DO MYSQL / MARIADB (XAMPP / LOCAL / NUVEM)")
    import pymysql

    if ENV_FILE.is_file():
        print(f"  [OK] Configuração existente carregada de: {ENV_FILE}")
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("PSTVIEWER_BIND_PORT="):
                try:
                    bind_port = int(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
        return ENV_FILE, bind_port

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
    return ENV_FILE, bind_port


def run_migrations_and_adapt_settings(
    env_path: Path, free_gb: float, reset_admin: bool = False, interactive: bool = True
) -> Tuple[str, str]:
    _banner("4. MIGRAÇÕES DO BANCO, AJUSTE DE DISCO E CREDENCIAIS DO ADMIN")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PSTVIEWER_ENV_FILE"] = str(env_path)

    subprocess.check_call([sys.executable, "-m", "app.database.migrations"], env=env)

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

    # Verifica se o admin já existe no banco
    check_code = (
        "from sqlalchemy import select; "
        "from app.database.session import SessionLocal; "
        "from app.database.models import User; "
        "db = SessionLocal(); "
        "u = db.scalar(select(User).where(User.username == 'admin')); "
        "print('EXISTS' if u else 'NEW'); "
        "db.close()"
    )
    chk = subprocess.run([sys.executable, "-c", check_code], env=env, capture_output=True, text=True)
    admin_exists = "EXISTS" in (chk.stdout or "")

    if admin_exists and not reset_admin and interactive:
        ans = input("\n  O usuário 'admin' já existe. Deseja redefinir a senha do 'admin' agora? [s/N]: ").strip()
        if ans.lower() in ("s", "sim", "y", "yes"):
            reset_admin = True

    if admin_exists and not reset_admin:
        return "admin", "(Senha atual preservada — rode reset_admin_password.bat se esquecer)"

    chosen_pw = ""
    if interactive:
        print("\n  [DEFINIÇÃO DE SENHA DO ADMINISTRADOR]")
        while True:
            chosen_pw = input(
                "  Digite a senha que deseja para o usuário 'admin' (mín. 8 caracteres)\n"
                "  [ou pressione Enter para gerar uma senha temporária]: "
            ).strip()
            if not chosen_pw or len(chosen_pw) >= 8:
                break
            print("  [AVISO] A senha deve ter pelo menos 8 caracteres. Tente novamente.")

    auto_generated = not bool(chosen_pw)
    final_pw = chosen_pw or secrets.token_urlsafe(10)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "create_admin.py"),
        "--username",
        "admin",
        "--password",
        final_pw,
    ]
    if auto_generated:
        cmd.append("--must-change-password")

    subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    if auto_generated:
        return "admin", f"{final_pw}  (Temporária -> o navegador pedirá para você criar a sua no 1º login!)"
    return "admin", final_pw


def _find_available_http_port(preferred_port: int) -> int:
    for port in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred_port


def _spawn_detached_process(args_list: List[str], env: Dict[str, str], log_file: Path) -> int:
    """
    Inicia um processo 100% desacoplado do terminal/PowerShell atual.
    No Windows, usa `pythonw.exe` (subsistema GUI sem janela de console) + flags de desacoplamento,
    garantindo que fechar o PowerShell ou CMD JAMAIS encerre o serviço!
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    out_handle = open(log_file, "a", encoding="utf-8")

    exe = sys.executable
    if os.name == "nt":
        pyw = Path(sys.executable).with_name("pythonw.exe")
        if pyw.is_file():
            exe = str(pyw)
        base_flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
        breakaway_flag = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
        try:
            proc = subprocess.Popen(
                [exe, *args_list],
                env=env,
                cwd=str(PROJECT_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=out_handle,
                stderr=subprocess.STDOUT,
                creationflags=base_flags | breakaway_flag,
                close_fds=True,
            )
            return proc.pid
        except OSError:
            proc = subprocess.Popen(
                [exe, *args_list],
                env=env,
                cwd=str(PROJECT_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=out_handle,
                stderr=subprocess.STDOUT,
                creationflags=base_flags,
                close_fds=True,
            )
            return proc.pid
    else:
        proc = subprocess.Popen(
            [exe, *args_list],
            env=env,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=out_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        return proc.pid


def start_services_in_background(env_path: Path, http_port: int) -> Dict[str, int]:
    """Inicia Web Server, Worker PST e Cleaner em segundo plano e aguarda o Health Check responder."""
    stop_background_services(silent=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PSTVIEWER_ENV_FILE"] = str(env_path)

    app_log_dir = STORAGE_ROOT / "logs" / "application"
    app_log_dir.mkdir(parents=True, exist_ok=True)

    worker_pid = _spawn_detached_process(
        ["-m", "app.workers.pst_worker", "--poll-interval", "2.0"],
        env=env,
        log_file=app_log_dir / "worker.log",
    )
    cleaner_pid = _spawn_detached_process(
        ["-m", "app.workers.cleaner_daemon", "--interval", "60"],
        env=env,
        log_file=app_log_dir / "cleaner.log",
    )
    web_pid = _spawn_detached_process(
        [
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(http_port),
            "--no-access-log",
        ],
        env=env,
        log_file=app_log_dir / "web.log",
    )

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(
        json.dumps(
            {
                "web_pid": web_pid,
                "worker_pid": worker_pid,
                "cleaner_pid": cleaner_pid,
                "port": http_port,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Aguarda até 10 segundos para confirmar que o servidor HTTP já está respondendo
    health_url = f"http://127.0.0.1:{http_port}/api/health"
    for _ in range(20):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(health_url, timeout=1.5) as resp:
                if resp.status == 200:
                    break
        except Exception:
            continue

    # Registra tarefa automática no logon do Windows (sem exigir privilégio de Admin)
    if os.name == "nt":
        pyw = Path(sys.executable).with_name("pythonw.exe")
        runner_exe = str(pyw if pyw.is_file() else Path(sys.executable))
        task_cmd = f'"{runner_exe}" "{PROJECT_ROOT / "setup_and_run.py"}" --yes --no-browser'
        subprocess.run(
            [
                "schtasks",
                "/Create",
                "/TN",
                "PSTViewer_Background_Service",
                "/TR",
                task_cmd,
                "/SC",
                "ONLOGON",
                "/F",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    return {"web_pid": web_pid, "worker_pid": worker_pid, "cleaner_pid": cleaner_pid}


def main() -> int:
    parser = argparse.ArgumentParser(description="PST Viewer - Assistente Inteligente Setup & Run")
    parser.add_argument("--yes", "-y", action="store_true", help="Instala tudo sem confirmação interativa")
    parser.add_argument("--setup-only", action="store_true", help="Apenas instala e configura sem iniciar o servidor")
    parser.add_argument("--stop", action="store_true", help="Encerra os serviços em segundo plano do PST Viewer")
    parser.add_argument("--status", action="store_true", help="Exibe o status dos serviços em segundo plano")
    parser.add_argument("--no-browser", action="store_true", help="Não abre o navegador automaticamente no final")
    parser.add_argument("--reset-admin", action="store_true", help="Gera uma nova senha para o usuário admin")
    parser.add_argument("--port", type=int, default=8085, help="Porta HTTP da aplicação (padrão: 8085)")
    parser.add_argument("--db-host", default="127.0.0.1", help="Host do MySQL/MariaDB (padrão: 127.0.0.1)")
    parser.add_argument("--db-port", type=int, default=3306, help="Porta do MySQL/MariaDB (padrão: 3306)")
    parser.add_argument("--db-user", default="root", help="Usuário do MySQL/MariaDB (padrão: root)")
    parser.add_argument("--db-password", default="", help="Senha do MySQL/MariaDB (padrão: vazio para XAMPP)")
    parser.add_argument("--db-name", default="pstviewer", help="Nome do banco (padrão: pstviewer)")
    args = parser.parse_args()

    if args.stop:
        stop_background_services(silent=False)
        return 0

    if args.status:
        st = get_background_status()
        if st.get("running"):
            print(
                f"  [ATIVO EM SEGUNDO PLANO] URL: http://127.0.0.1:{st['port']} | "
                f"PIDs -> Web: {st['web_pid']}, Worker: {st['worker_pid']}, Cleaner: {st['cleaner_pid']}"
            )
        else:
            print("  [PARADO] Os serviços em segundo plano do PST Viewer não estão em execução.")
        return 0

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

    # Se não for apenas setup, reinicia os serviços em segundo plano mantendo a porta 8085
    if not args.setup_only:
        stop_background_services(silent=True)

    http_port = _find_available_http_port(args.port)
    env_path, http_port = configure_database_and_env(
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
        interactive=interactive,
    )

    if args.setup_only:
        return 0

    pids = start_services_in_background(env_path, http_port)
    url = f"http://127.0.0.1:{http_port}"

    _banner("✔ PST VIEWER ATIVO EM SEGUNDO PLANO (PODE FECHAR O TERMINAL!)")
    print("  Os serviços foram iniciados de forma independente em segundo plano:")
    print(f"  • Servidor Web FastAPI : ATIVO (PID {pids['web_pid']})")
    print(f"  • Worker Extrator PST  : ATIVO (PID {pids['worker_pid']})")
    print(f"  • Guardião de Limpeza  : ATIVO (PID {pids['cleaner_pid']})")
    print("-" * 76)
    print(f"  • Endereço de Acesso   : {url}")
    print(f"  • Usuário Admin        : {admin_user}")
    print(f"  • Senha Admin          : {admin_pw}")
    print("-" * 76)
    print("  💡 Você já pode FECHAR esta janela do PowerShell/CMD tranquilamente!")
    print("     O sistema continuará rodando em segundo plano.")
    print("=" * 76)

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
