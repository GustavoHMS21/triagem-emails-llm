"""Listas de palavras-chave e a busca por elas.

Duas listas, com custos de erro diferentes:

- REDE DE SEGURANÇA (PALAVRAS_CRITICAS): usada depois do LLM, pelas regras de
  negócio. Sobe o nível e pede revisão humana. Um falso positivo vira alarme na
  fila da atendente, então esta lista é estreita.
- FILA (PALAVRAS_CRITICAS + PALAVRAS_SO_FILA): usada antes do LLM, só para
  decidir a ordem de classificação. Um falso positivo apenas adianta um e-mail
  comum, então esta lista é larga e inclui automaticamente a da rede.
"""

import re

from triagem.modelos import Nivel

# --- Rede de segurança -------------------------------------------------------
# Não substitui o LLM: só pega o caso em que ele subestimou algo grave. O nível
# indicado é o piso; quem confirma é a atendente na revisão.
#
# padrão -> (nível, rótulo). O motivo gravado usa o rótulo, nunca o trecho
# encontrado: padrões como "elevador.{0,60}dentro" capturam texto livre do
# e-mail, que pode ter nome de pessoa.
PALAVRAS_CRITICAS: dict[str, tuple[Nivel, str]] = {
    r"cheiro de g[aá]s|vazamento de g[aá]s": (Nivel.URGENTE, "cheiro de gás"),
    r"pres[oa]s? no elevador|gente presa|pessoa presa": (Nivel.URGENTE, "pessoa presa no elevador"),
    r"elevador.{0,60}dentro|dentro do elevador": (Nivel.URGENTE, "pessoa presa no elevador"),  # E039
    r"inc[eê]ndio|fuma[cç]a|fa[ií]sca|curto[- ]circuito": (Nivel.URGENTE, "fogo ou faísca"),
    r"cheiro de queimado": (Nivel.URGENTE, "cheiro de queimado"),  # E132
    r"fio desencapado": (Nivel.URGENTE, "fio desencapado"),
    r"cano estourad|estourou o cano|alagad|alagamento": (Nivel.URGENTE, "cano estourado ou alagamento"),
    r"vazamento|vazando|vasament|infiltra": (Nivel.IMPORTANTE, "vazamento ou infiltração"),  # "vasamento" (E064)
    r"sem [aá]gua|falta de [aá]gua": (Nivel.IMPORTANTE, "falta de água"),
    r"sem luz|falta de luz|apag[aã]o": (Nivel.IMPORTANTE, "falta de luz"),
    r"port[aã]o.{0,30}(n[aã]o fecha|aberto|quebrad)": (Nivel.URGENTE, "portão que não fecha"),
}

# --- Só para a ordem da fila ---------------------------------------------------
PALAVRAS_SO_FILA: dict[str, Nivel] = {
    # Água em movimento: "ta descendo agua", "a agua da escada entrou" (E019, E020)
    (
        r"[aá]gua.{0,30}(descend|cain|sain|entr|escorr)"
        r"|(descend|cain|sain|entr|escorr)\w*\s+[aá]gua|molhando|molhou"
    ): Nivel.URGENTE,
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

_REDE = [(re.compile(p, re.IGNORECASE), n, rotulo) for p, (n, rotulo) in PALAVRAS_CRITICAS.items()]
_FILA = [
    (re.compile(p, re.IGNORECASE), n)
    for p, n in {**{p: n for p, (n, _) in PALAVRAS_CRITICAS.items()}, **PALAVRAS_SO_FILA}.items()
]


def nivel_por_palavra_chave(texto: str) -> tuple[Nivel, str] | None:
    """Rede de segurança: maior nível acionado e o rótulo do padrão, ou None."""
    achados = [(n, rotulo) for p, n, rotulo in _REDE if p.search(texto)]
    return max(achados, key=lambda a: a[0]) if achados else None


def nivel_da_fila(texto: str) -> int:
    """Fila: maior nível acionado (0 se nenhuma palavra), para ordenar a classificação."""
    return max((n for p, n in _FILA if p.search(texto)), default=0)
