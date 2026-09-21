"""Copia os dados locais para um PostgreSQL novo, sem apagar o destino.

Uso (PowerShell):
  $env:DATABASE_URL='postgresql://...'
  python migrate_sqlite_to_postgres.py
"""
import os
import sys

from sqlalchemy import create_engine, func, select

from models_v4 import Base


SOURCE_URL = os.getenv("SOURCE_SQLITE_URL", "sqlite:///./motor_tributario_v4.db")
TARGET_URL = os.getenv("DATABASE_URL", "")


def main() -> None:
    if not TARGET_URL:
        raise SystemExit("Defina DATABASE_URL com a conexão PostgreSQL de destino.")
    if TARGET_URL.startswith("sqlite"):
        raise SystemExit("DATABASE_URL deve apontar para PostgreSQL, não SQLite.")
    target_url = (
        "postgresql://" + TARGET_URL[len("postgres://"):]
        if TARGET_URL.startswith("postgres://") else TARGET_URL
    )
    source = create_engine(SOURCE_URL)
    target = create_engine(target_url)
    Base.metadata.create_all(target)

    with source.connect() as source_connection, target.begin() as target_connection:
        for table in Base.metadata.sorted_tables:
            existing = target_connection.scalar(select(func.count()).select_from(table))
            if existing:
                raise SystemExit(
                    f"Destino não está vazio: tabela '{table.name}' tem {existing} registro(s). "
                    "A migração foi interrompida sem alterar dados."
                )
        for table in Base.metadata.sorted_tables:
            rows = list(source_connection.execute(select(table)).mappings())
            if rows:
                target_connection.execute(table.insert(), rows)
            print(f"{table.name}: {len(rows)} registro(s) copiado(s)")
    print("Migração concluída com sucesso.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Erro na migração: {error}", file=sys.stderr)
        raise
