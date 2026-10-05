"""Fixtures de integração com um PostgreSQL de verdade.

Cada teste recebe um banco novo e vazio, criado com nome aleatório no servidor
de TESTE_DATABASE_URL (padrão: o Postgres do docker-compose) e apagado no fim.
O banco da aplicação nunca é tocado.

Sem servidor disponível, os testes de integração são pulados; com
EXIGIR_BANCO=1 (no CI), falham: um CI sem banco não pode ficar verde.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from triagem.migrar import listar, migrar

SERVIDOR = os.environ.get("TESTE_DATABASE_URL", "postgresql://triagem:triagem@127.0.0.1:5433/postgres")


@pytest.fixture
def banco_vazio() -> Iterator[str]:
    """URL de um banco novo e vazio, apagado ao fim do teste."""
    try:
        admin = psycopg.connect(SERVIDOR, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as erro:
        if os.environ.get("EXIGIR_BANCO") == "1":
            raise
        pytest.skip(f"Postgres indisponível para testes de integração: {erro}")

    nome = f"teste_{uuid.uuid4().hex[:12]}"
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    try:
        yield make_conninfo(SERVIDOR, dbname=nome)
    finally:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nome)))
        admin.close()


@pytest.fixture
def banco_migrado(banco_vazio: str) -> str:
    """Banco descartável com o schema real, criado pelas migrações de db/ (como em produção)."""
    with psycopg.connect(banco_vazio, autocommit=True) as conn:
        migrar(conn, listar(Path("db")))
    return banco_vazio
