"""Executor de migrações: aplica os .sql de db/ que ainda não rodaram neste banco.

Uso:
    uv run python -m triagem.migrar              # aplica as que faltam
    uv run python -m triagem.migrar --baseline   # só registra as existentes (banco anterior ao executor)

Cada migração roda numa transação e é registrada em schema_migrations com o
checksum do arquivo. Regras:
  - ordem pelo nome do arquivo (001_, 002_, ...);
  - migração já aplicada que foi editada depois é recusada: crie uma nova;
  - uma trava no banco impede dois executores ao mesmo tempo.
"""

import argparse
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg

from triagem.config import carregar_config

log = logging.getLogger("triagem.migrar")

_TRAVA = 7_465_311  # id arbitrário e fixo para pg_advisory_lock

_CRIAR_REGISTRO = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    versao      TEXT        PRIMARY KEY,
    checksum    TEXT        NOT NULL,
    aplicada_em TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class MigracaoAlterada(Exception):
    """Uma migração já aplicada foi editada depois: o banco não corresponde mais ao arquivo."""


@dataclass(frozen=True)
class Migracao:
    versao: str  # nome do arquivo, ex.: 002_remove_dados_pessoais.sql
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def listar(pasta: Path) -> list[Migracao]:
    return [Migracao(arquivo.name, arquivo.read_text(encoding="utf-8")) for arquivo in sorted(pasta.glob("*.sql"))]


def _aplicadas(conn: psycopg.Connection) -> dict[str, str]:
    return dict(conn.execute("SELECT versao, checksum FROM schema_migrations").fetchall())


def migrar(conn: psycopg.Connection, migracoes: list[Migracao], baseline: bool = False) -> list[str]:
    """Aplica (ou, com baseline, só registra) as migrações pendentes. Devolve as versões processadas."""
    conn.execute("SELECT pg_advisory_lock(%s)", (_TRAVA,))
    try:
        conn.execute(_CRIAR_REGISTRO)
        aplicadas = _aplicadas(conn)

        for m in migracoes:
            if m.versao in aplicadas and aplicadas[m.versao] != m.checksum:
                raise MigracaoAlterada(f"{m.versao} já foi aplicada e o arquivo mudou depois; crie uma migração nova")

        processadas = []
        for m in migracoes:
            if m.versao in aplicadas:
                continue
            with conn.transaction():  # falhou no meio: desfaz a migração inteira e não registra
                if not baseline:
                    # SQL lido de arquivo vai como bytes: o psycopg só aceita texto literal do código
                    # ou bytes (proteção contra injection). Sem parâmetros, aceita vários comandos.
                    conn.execute(m.sql.encode("utf-8"))
                conn.execute("INSERT INTO schema_migrations (versao, checksum) VALUES (%s, %s)", (m.versao, m.checksum))
            processadas.append(m.versao)
        return processadas
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (_TRAVA,))


def main() -> None:
    parser = argparse.ArgumentParser(description="Aplica as migrações pendentes de db/")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Registra as migrações como aplicadas SEM executá-las (uma vez, em banco anterior ao executor)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config = carregar_config()

    with psycopg.connect(config.database_url, autocommit=True) as conn:
        processadas = migrar(conn, listar(config.migracoes_dir), baseline=args.baseline)

    acao = "registradas sem executar (baseline)" if args.baseline else "aplicadas"
    if processadas:
        log.info("%d migração(ões) %s: %s", len(processadas), acao, ", ".join(processadas))
    else:
        log.info("Banco em dia: nenhuma migração pendente")


if __name__ == "__main__":
    main()
