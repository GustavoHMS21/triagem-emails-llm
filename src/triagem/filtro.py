"""Filtro antes do LLM: decide o que nem precisa passar pelo modelo
e em que ordem o resto vai ser classificado.
"""

import re
import unicodedata
from datetime import datetime

from triagem.modelos import EmailLimpo, Nivel, Triagem
from triagem.palavras_chave import nivel_da_fila

FILTRO_VERSAO = "filtro_v1"

# Expressões típicas de marketing. Sozinhas não bastam: o e-mail também
# precisa ter o cabeçalho List-Unsubscribe para ser tratado como propaganda.
MARCAS_PROPAGANDA = [
    r"aproveite",
    r"desconto",
    r"promocao",
    r"oferta",
    r"ligue ja",
    r"clique aqui",
    r"nao perca",
    r"ultimas vagas",
    r"frete gratis",
    r"cupom",
]
_MARCAS = re.compile("|".join(MARCAS_PROPAGANDA), re.IGNORECASE)

# Descadastro escrito no corpo vale como o cabeçalho List-Unsubscribe:
# "Para não receber mais nossos e-mails, clique aqui" (E009)
_DESCADASTRO_NO_TEXTO = re.compile(
    r"nao receber mais|descadastr|cancelar (a |sua )?inscricao|unsubscribe|sair da lista", re.IGNORECASE
)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def motivo_propaganda(email: EmailLimpo) -> str | None:
    """Devolve o motivo se o e-mail é propaganda, ou None se não é."""
    texto = _sem_acento(f"{email.assunto}\n{email.corpo}")

    if any(nome.lower() == "list-unsubscribe" for nome in email.original.cabecalhos):
        descadastro = "List-Unsubscribe"
    elif _DESCADASTRO_NO_TEXTO.search(texto):
        descadastro = "descadastro no texto"
    else:
        return None

    marca = _MARCAS.search(texto)
    if not marca:
        return None

    return f'Propaganda: tem {descadastro} e a expressão "{marca.group(0)}"'


def triagem_de_propaganda(email: EmailLimpo, motivo: str) -> Triagem:
    """Resultado para propaganda: vai para o banco como lixo, sem passar pelo LLM.
    Não é apagada: aparece no painel ao desmarcar "Esconder propaganda"."""
    return Triagem(
        email=email,
        classificacao=None,
        categoria="lixo",
        condominio_id=None,
        remetente_sindico=False,
        nivel_final=Nivel.NORMAL,
        requer_revisao=False,
        motivos=[motivo],
        modelo="nenhum (filtro)",
        prompt_versao=FILTRO_VERSAO,
    )


# --- Ordem da fila -----------------------------------------------------------


def chave_da_fila(email: EmailLimpo) -> tuple[int, datetime]:
    """Ordem de classificação: menor chave passa antes pelo LLM.

    1º quem tem palavra de nível urgente, 2º importante, 3º o resto;
    dentro de cada grupo, o mais antigo primeiro. As palavras estão em palavras_chave.py.
    """
    return (-nivel_da_fila(f"{email.assunto}\n{email.corpo}"), email.original.recebido_em)
