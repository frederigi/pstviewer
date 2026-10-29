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
from app.database.models import User
from app.database.session import SessionLocal


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
    args = parser.parse_args()

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == args.username.strip().lower()))
        if existing:
            if args.if_not_exists:
                print(f"[OK] Administrador '{existing.username}' já está cadastrado (senha preservada).")
                return 0
            pw = args.password or secrets.token_urlsafe(12)
            existing.password_hash = hash_password(pw)
            existing.is_admin = True
            existing.is_active = True
            existing.failed_login_attempts = 0
            existing.locked_until = None
            db.commit()
            print(f"[OK] Senha do administrador '{existing.username}' redefinida: {pw}")
            return 0

        pw = args.password or secrets.token_urlsafe(12)
        user = create_user(
            db,
            username=args.username,
            plain_password=pw,
            full_name=args.full_name,
            is_admin=True,
        )
        print("==================================================================")
        print(" CREDENCIAIS DO PRIMEIRO ADMINISTRADOR CRIADAS COM SUCESSO:")
        print(f"   Usuário: {user.username}")
        print(f"   Senha:   {pw}")
        print("==================================================================")
        return 0


if __name__ == "__main__":
    sys.exit(main())

