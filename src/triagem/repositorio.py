"""Etapa 4: persistência no PostgreSQL."""

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from triagem.modelos import Triagem

_INSERIR = """
INSERT INTO triagens (
    email_id, remetente, assunto_original, assunto, corpo, anexos, recebido_em,
    categoria, outras_categorias, urgencia_llm, resumo, classificacao,
    condominio_id, remetente_sindico, nivel_final, requer_revisao, motivos,
    modelo, prompt_versao
) VALUES (
    %(email_id)s, %(remetente)s, %(assunto_original)s, %(assunto)s, %(corpo)s, %(anexos)s, %(recebido_em)s,
    %(categoria)s, %(outras_categorias)s, %(urgencia_llm)s, %(resumo)s, %(classificacao)s,
    %(condominio_id)s, %(remetente_sindico)s, %(nivel_final)s, %(requer_revisao)s, %(motivos)s,
    %(modelo)s, %(prompt_versao)s
)
ON CONFLICT (email_id) DO NOTHING
"""

_FILA = """
SELECT * FROM triagens
WHERE status = ANY(%(status)s)
ORDER BY nivel_final DESC, requer_revisao DESC, recebido_em ASC
"""


class Repositorio:
    """Uma conexão por uso, reaproveitada em todas as operações:

        with Repositorio(url) as repo:
            repo.salvar(...)

    autocommit: cada e-mail salvo fica gravado na hora. Se o pipeline cair no
    meio, o que já foi triado não se perde e a próxima rodada continua dali.

    Para um processo que roda dias (leitura contínua do Gmail), trocar por um
    pool de conexões (psycopg_pool), que recria conexões que caíram.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._conn: psycopg.Connection | None = None

    def __enter__(self) -> "Repositorio":
        self._conn = psycopg.connect(self.database_url, row_factory=dict_row, autocommit=True)
        return self

    def __exit__(self, *_) -> None:
        self._conn.close()

    @property
    def conn(self) -> psycopg.Connection:
        if self._conn is None:
            raise RuntimeError("Use o Repositorio dentro de um bloco `with`")
        return self._conn

    def ja_triado(self, email_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM triagens WHERE email_id = %s", (email_id,)).fetchone() is not None

    def salvar(self, t: Triagem) -> bool:
        """Devolve False se o e-mail já estava no banco."""
        email, c = t.email.original, t.classificacao
        params = {
            "email_id": email.id,
            "remetente": email.remetente,
            "assunto_original": email.assunto,
            "assunto": t.email.assunto,
            "corpo": t.email.corpo,
            "anexos": Jsonb([a.model_dump() for a in email.anexos]),
            "recebido_em": email.recebido_em,
            "categoria": t.categoria,
            "outras_categorias": c.outras_categorias if c else [],
            "urgencia_llm": c.urgencia if c else None,
            "resumo": c.resumo if c else None,
            "classificacao": Jsonb(c.model_dump()) if c else None,
            "condominio_id": t.condominio_id,
            "remetente_sindico": t.remetente_sindico,
            "nivel_final": int(t.nivel_final),
            "requer_revisao": t.requer_revisao,
            "motivos": t.motivos,
            "modelo": t.modelo,
            "prompt_versao": t.prompt_versao,
        }
        return self.conn.execute(_INSERIR, params).rowcount == 1

    def fila(self, status: list[str] | None = None) -> list[dict]:
        return self.conn.execute(_FILA, {"status": status or ["pendente", "em_atendimento"]}).fetchall()

    def atualizar_status(self, triagem_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE triagens SET status = %s, atualizado_em = now() WHERE id = %s",
            (status, triagem_id),
        )
