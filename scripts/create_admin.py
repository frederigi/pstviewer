#!/usr/bin/env python3
"""
Script seguro para criação ou atualização do primeiro administrador do PST Viewer.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from sqlalchemy import select

from app.auth.security import create_user, hash_password
from app.database.models import SystemSetting, User
from app.database.session import SessionLocal


def _set_must_change_flag(db, must_change: bool) -> None:
    val = "1" if must_change else "0"
    row = db.get(SystemSetting, "admin_must_change_password")
    if row:
        row.setting_value = val
    else:
        db.add(
            SystemSetting(
                setting_key="admin_must_change_password",
                setting_value=val,
                description="Exige troca de senha no primeiro login do admin (1=Sim, 0=Não)",
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="PST Viewer - Cadastro de Administrador")
    parser.add_argument("--username", default="admin", help="Nome de usuário (padrão: admin)")
    parser.add_argument("--full-name", default="Administrador do Sistema", help="Nome completo")
    parser.add_argument("--password", default=None, help="Senha (se omitida, gera senha forte aleatória)")
    parser.add_argument(
        "--if-not-exists",
        action="store_true",
        help="Não altera a senha caso o usuário administrador já exista.",
    )
    parser.add_argument(
        "--must-change-password",
        action="store_true",
        help="Solicita ao administrador a definição de uma senha pessoal no primeiro acesso web.",
    )
    args = parser.parse_args()

    auto_generated = args.password is None
    must_change = args.must_change_password or auto_generated

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == args.username.strip().lower()))
        if existing:
            if args.if_not_exists:
                print(f"[OK] Administrador '{existing.username}' já está cadastrado (senha preservada).")
                return 0
            pw = args.password or secrets.token_urlsafe(10)
            existing.password_hash = hash_password(pw)
            existing.is_admin = True
            existing.is_active = True
            existing.failed_login_attempts = 0
            existing.locked_until = None
            _set_must_change_flag(db, must_change)
            db.commit()
            print(f"[OK] Senha do administrador '{existing.username}' redefinida: {pw}")
            return 0

        pw = args.password or secrets.token_urlsafe(10)
        user = create_user(
            db,
            username=args.username,
            plain_password=pw,
            full_name=args.full_name,
            is_admin=True,
        )
        _set_must_change_flag(db, must_change)
        db.commit()
        print("==================================================================")
        print(" CREDENCIAIS DO PRIMEIRO ADMINISTRADOR CRIADAS COM SUCESSO:")
        print(f"   Usuário: {user.username}")
        print(f"   Senha:   {pw}")
        print("==================================================================")
        return 0


if __name__ == "__main__":
    sys.exit(main())
