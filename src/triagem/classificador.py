"""Etapa 2: classificação com o LLM.

Monta o prompt, chama o modelo e valida a saída com Pydantic. Se a resposta
vier inválida, tenta de novo; se continuar falhando, devolve None e as regras
de negócio mandam o e-mail para revisão humana. O pipeline nunca para por causa do LLM.
"""

import logging
import time
from functools import cache
from pathlib import Path

from pydantic import ValidationError

from triagem.llm import ClienteLLM, ErroLLM
from triagem.modelos import Classificacao, EmailLimpo

log = logging.getLogger(__name__)

PROMPT_VERSAO = "classificacao_v1"
_SCHEMA = Classificacao.model_json_schema()  # cálculo puro, sem I/O: pode ficar no import


@cache
def carregar_prompt(versao: str = PROMPT_VERSAO) -> str:
    """Lê o prompt versionado na primeira chamada (e não no import do módulo)."""
    return (Path(__file__).parent / "prompts" / f"{versao}.md").read_text(encoding="utf-8")


def montar_mensagem(email: EmailLimpo) -> str:
    anexos = ", ".join(a.nome for a in email.original.anexos) or "nenhum"
    return (
        f"Assunto: {email.assunto or '(sem assunto)'}\n"
        f"Anexos: {anexos}\n"
        f"<email>\n{email.corpo or '(corpo vazio)'}\n</email>"
    )


def _resumir_erros(erro: ValidationError) -> str:
    # Só campo e tipo do erro: nunca ecoa de volta o valor que o modelo gerou
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'json'}: {e['msg']}" for e in erro.errors()[:5])


class Classificador:
    def __init__(self, llm: ClienteLLM, tentativas: int = 2, espera_s: float = 2.0, prompt: str | None = None):
        self.llm = llm
        self.tentativas = tentativas
        self.espera_s = espera_s
        self.prompt = prompt if prompt is not None else carregar_prompt()

    def classificar(self, email: EmailLimpo) -> Classificacao | None:
        mensagem = montar_mensagem(email)
        for tentativa in range(1, self.tentativas + 1):
            try:
                bruto = self.llm.gerar_json(self.prompt, mensagem, _SCHEMA)
                return Classificacao.model_validate_json(bruto)

            except ValidationError as erro:
                # O modelo respondeu fora do formato. Com temperature=0, repetir o
                # mesmo prompt repete o erro: a próxima tentativa diz o que corrigir.
                resumo = _resumir_erros(erro)
                log.warning(
                    "Resposta inválida para %s (tentativa %d/%d): %s",
                    email.original.id,
                    tentativa,
                    self.tentativas,
                    resumo,
                )
                mensagem = (
                    f"{montar_mensagem(email)}\n\n"
                    f"Sua resposta anterior foi rejeitada pela validação ({resumo}). "
                    "Responda de novo seguindo exatamente o schema."
                )

            except ErroLLM as erro:
                # Falha transitória (rede, timeout, serviço reiniciando): esperar ajuda,
                # mudar o prompt não. Espera dobra a cada tentativa (backoff exponencial).
                log.warning(
                    "LLM indisponível para %s (tentativa %d/%d): %s",
                    email.original.id,
                    tentativa,
                    self.tentativas,
                    erro,
                )
                if tentativa < self.tentativas:
                    time.sleep(self.espera_s * 2 ** (tentativa - 1))
        return None
