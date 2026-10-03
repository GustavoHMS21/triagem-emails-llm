"""Etapa 1: limpeza do texto antes de ir para o LLM.

Tira o que não é conteúdo novo: histórico de resposta, rodapé de celular e
assinatura. Também tira "URGENTE" do assunto, porque pela regra do cliente
ele não conta; assim o modelo nem chega a ver.
"""

import re

from triagem.modelos import Email, EmailLimpo

# Linha que marca o início do histórico citado; tudo dali para baixo sai
_INICIO_HISTORICO = [
    re.compile(r"^\s*Em .{5,120} escreveu:\s*$", re.IGNORECASE),
    re.compile(r"^\s*On .{5,120} wrote:\s*$", re.IGNORECASE),
    re.compile(r"^\s*-{2,}\s*Mensagem (original|encaminhada)\s*-{2,}", re.IGNORECASE),
    re.compile(r"^\s*-{2,}\s*(Original|Forwarded) message\s*-{2,}", re.IGNORECASE),
    re.compile(r"^\s*De:\s.+", re.IGNORECASE),  # cabeçalho do Outlook ao responder
    re.compile(r"^\s*From:\s.+", re.IGNORECASE),
    re.compile(r"^\s*_{10,}\s*$"),  # linha de sublinhados do Outlook
]

_RODAPE_CELULAR = re.compile(
    r"^\s*(Enviado do meu \w+.*|Enviado de meu \w+.*|Sent from my \w+.*|"
    r"Obter o Outlook para \w+.*|Get Outlook for \w+.*|Enviado via .+)\s*$",
    re.IGNORECASE,
)

# Despedidas que costumam abrir a assinatura
_DESPEDIDA = re.compile(
    r"^\s*(att\.?|atte\.?|atenciosamente|abs\.?|abraços?|grat[oa]|"
    r"obrigad[oa]s?|cordialmente|saudações)[\s,.!]*$",
    re.IGNORECASE,
)
_LINHAS_FINAIS_ASSINATURA = 8  # só procura despedida perto do fim

_LIXO_ASSUNTO = re.compile(
    r"\b(urgente|urgentíssimo|urgencia|urgência)\b|^\s*((re|res|enc|fw|fwd|tr)\s*:\s*)+|!{2,}",
    re.IGNORECASE,
)


def limpar_corpo(corpo: str) -> str:
    linhas = corpo.replace("\r\n", "\n").split("\n")

    # 1. corta no início do histórico citado
    for i, linha in enumerate(linhas):
        if any(p.match(linha) for p in _INICIO_HISTORICO):
            linhas = linhas[:i]
            break

    # 2. remove linhas citadas (">") e rodapé de celular
    linhas = [l for l in linhas if not l.lstrip().startswith(">") and not _RODAPE_CELULAR.match(l)]

    # 3. corta no separador padrão de assinatura "-- "
    for i, linha in enumerate(linhas):
        if linha.rstrip() == "--":
            linhas = linhas[:i]
            break

    # 4. corta na despedida, se estiver perto do fim
    inicio_busca = max(0, len(linhas) - _LINHAS_FINAIS_ASSINATURA)
    for i in range(inicio_busca, len(linhas)):
        if _DESPEDIDA.match(linhas[i]):
            linhas = linhas[:i]
            break

    texto = "\n".join(l.rstrip() for l in linhas)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def limpar_assunto(assunto: str) -> str:
    sem_lixo = _LIXO_ASSUNTO.sub(" ", assunto)
    return re.sub(r"\s+", " ", sem_lixo).strip(" -:")


def limpar(email: Email) -> EmailLimpo:
    return EmailLimpo(
        original=email,
        assunto=limpar_assunto(email.assunto),
        corpo=limpar_corpo(email.corpo),
    )
