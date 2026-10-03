"""Filtro antes do LLM: decide o que nem precisa passar pelo modelo
e em que ordem o resto vai ser classificado.
"""

import re
import unicodedata

from triagem.modelos import EmailLimpo

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


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def motivo_propaganda(email: EmailLimpo) -> str | None:
    """Devolve o motivo se o e-mail é propaganda, ou None se não é."""
    tem_descadastro = any(nome.lower() == "list-unsubscribe" for nome in email.original.cabecalhos)
    if not tem_descadastro:
        return None

    texto = _sem_acento(f"{email.assunto}\n{email.corpo}")
    marca = _MARCAS.search(texto)
    if not marca:
        return None

    return f'Propaganda: tem List-Unsubscribe e a expressão "{marca.group(0)}"'
