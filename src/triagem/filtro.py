"""Filtro antes do LLM: decide o que nem precisa passar pelo modelo
e em que ordem o resto vai ser classificado.
"""

import re
import unicodedata
from datetime import datetime

from triagem.modelos import EmailLimpo, Nivel, Triagem
from triagem.regras import PALAVRAS_CRITICAS

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
# A fila usa TODAS as palavras críticas da rede de segurança (regras.py) e mais
# algumas extras. Aqui errar é barato: no pior caso um e-mail comum é
# classificado mais cedo. Por isso esta lista pode ser mais larga.

PALAVRAS_SO_FILA: dict[str, Nivel] = {
    # Água em movimento: "ta descendo agua", "a agua da escada entrou" (E019, E020)
    r"[aá]gua.{0,30}(descend|cain|sain|entr|escorr)|(descend|cain|sain|entr|escorr)\w*\s+[aá]gua|molhando|molhou": Nivel.URGENTE,
    # Risco elétrico: "fio solto... pode dar choque?" (E073)
    r"fio solto|choque": Nivel.URGENTE,
    r"elevador": Nivel.IMPORTANTE,
    r"goteira|pingando|pingo": Nivel.IMPORTANTE,
    r"port[aã]o": Nivel.IMPORTANTE,
    r"interfone": Nivel.IMPORTANTE,
    r"mofo|umidade|mancha": Nivel.IMPORTANTE,
    # Luz: "ta um breu", "muito escuro", "lampada da escada queimou" (E052, E063, E144)
    r"apagad|breu|escuro|l[aâ]mpada": Nivel.IMPORTANTE,
    # Falta de água chegando: "a bomba parou... acaba a agua" (E077)
    r"bomba|acab\w* a [aá]gua": Nivel.IMPORTANTE,
    # Risco físico: "buraco aberto... alguém pode cair", "se alguém se machucar" (E048, E081)
    r"buraco|\bcair\b|machuc": Nivel.IMPORTANTE,
}
_PALAVRAS_FILA = [
    (re.compile(padrao, re.IGNORECASE), nivel)
    for padrao, nivel in {**{p: n for p, (n, _) in PALAVRAS_CRITICAS.items()}, **PALAVRAS_SO_FILA}.items()
]


def chave_da_fila(email: EmailLimpo) -> tuple[int, datetime]:
    """Ordem de classificação: menor chave passa antes pelo LLM.

    1º quem tem palavra de nível urgente, 2º importante, 3º o resto;
    dentro de cada grupo, o mais antigo primeiro.
    """
    texto = f"{email.assunto}\n{email.corpo}"
    nivel = max((nivel for padrao, nivel in _PALAVRAS_FILA if padrao.search(texto)), default=0)
    return (-nivel, email.original.recebido_em)
