"""Etapa 2: classificação com o LLM.

Monta o prompt, chama o modelo e valida a saída com Pydantic. Se a resposta
vier inválida, tenta de novo; se continuar falhando, devolve None e as regras
de negócio mandam o e-mail para revisão humana. O pipeline nunca para por causa do LLM.
"""

import logging
from pathlib import Path

import httpx
from pydantic import ValidationError

from triagem.llm import ClienteLLM
from triagem.modelos import Classificacao, EmailLimpo

log = logging.getLogger(__name__)

PROMPT_VERSAO = "classificacao_v1"
_PROMPT_SISTEMA = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSAO}.md").read_text(
    encoding="utf-8"
)
_SCHEMA = Classificacao.model_json_schema()


def montar_mensagem(email: EmailLimpo) -> str:
    anexos = ", ".join(a.nome for a in email.original.anexos) or "nenhum"
    return (
        f"Assunto: {email.assunto or '(sem assunto)'}\n"
        f"Anexos: {anexos}\n"
        f"<email>\n{email.corpo or '(corpo vazio)'}\n</email>"
    )


class Classificador:
    def __init__(self, llm: ClienteLLM, tentativas: int = 2):
        self.llm = llm
        self.tentativas = tentativas

    def classificar(self, email: EmailLimpo) -> Classificacao | None:
        mensagem = montar_mensagem(email)
        for tentativa in range(1, self.tentativas + 1):
            try:
                bruto = self.llm.gerar_json(_PROMPT_SISTEMA, mensagem, _SCHEMA)
                return Classificacao.model_validate_json(bruto)
            except (ValidationError, httpx.HTTPError) as erro:
                log.warning(
                    "Falha ao classificar %s (tentativa %d/%d): %s",
                    email.original.id, tentativa, self.tentativas, erro,
                )
        return None
