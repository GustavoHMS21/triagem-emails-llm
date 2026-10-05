"""Formatação para o painel: texto seguro, rótulos legíveis e tempo de espera.

No Streamlit, st.markdown, st.caption e títulos de componentes interpretam
markdown: um texto com ![](http://atacante/pixel.png) vira uma imagem que o
navegador da atendente busca sozinho (rastreamento), e [texto](http://...)
vira link de phishing. Todo texto dinâmico passa por escapar_markdown.
"""

import re
from datetime import datetime
from urllib.parse import quote

ROTULOS_CATEGORIA = {
    "financeiro": "Financeiro",
    "manutencao": "Manutenção",
    "cobranca": "Cobrança",
    "assembleia_reserva": "Assembleia e reserva",
    "cadastro": "Cadastro",
    "fornecedor": "Fornecedor",
    "lixo": "Propaganda",
    "outros": "Outros",
}
ROTULOS_STATUS = {"pendente": "Pendente", "em_atendimento": "Em atendimento", "concluido": "Concluído"}

# Tudo que o markdown do Streamlit interpreta, incluindo ":" e "." (links
# automáticos de http://... e www....) e "$" (fórmulas LaTeX)
_ESPECIAIS = re.compile(r"([\\`*_{}\[\]()<>#+\-.!|~:$])")


def escapar_markdown(texto: object) -> str:
    """Devolve o texto para ser exibido literalmente, sem virar link, imagem ou formatação."""
    return _ESPECIAIS.sub(r"\\\1", str(texto))


def rotulo_categoria(categoria: str | None) -> str:
    return ROTULOS_CATEGORIA.get(categoria, "Sem categoria") if categoria else "Sem categoria"


def tempo_de_espera(desde: datetime, agora: datetime) -> str:
    """Quanto tempo o chamado está esperando, ex.: "há 4h 12min".

    `agora` vem de fora (e não de datetime.now()) para a função ser testável.
    """
    minutos = max(0, int((agora - desde).total_seconds() // 60))
    if minutos < 1:
        return "agora"
    if minutos < 60:
        return f"há {minutos} min"
    horas, resto = divmod(minutos, 60)
    if horas < 24:
        return f"há {horas}h {resto:02d}min"
    dias = horas // 24
    return f"há {dias} dia{'s' if dias > 1 else ''}"


def link_gmail(message_id: str) -> str:
    """Busca a mensagem original no Gmail pelo Message-ID.

    O conteúdo do e-mail não é guardado no banco (minimização): a atendente lê
    no Gmail. O id vem de fora e é codificado para não alterar a URL.
    """
    return f"https://mail.google.com/mail/u/0/#search/rfc822msgid%3A{quote(message_id, safe='')}"
