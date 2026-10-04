"""Exibição segura de texto não confiável no painel.

Assunto, remetente e nome de anexo vêm de quem enviou o e-mail; resumo e
motivos vêm do LLM, que leu esse e-mail. No Streamlit, st.markdown, st.caption
e o título do st.expander interpretam markdown: um assunto com
![](http://atacante/pixel.png) vira uma imagem que o navegador da atendente
busca sozinho (rastreamento), e [texto](http://...) vira link de phishing.
"""

import re
from urllib.parse import quote

# Tudo que o markdown do Streamlit interpreta, incluindo ":" e "." (links
# automáticos de http://... e www....) e "$" (fórmulas LaTeX)
_ESPECIAIS = re.compile(r"([\\`*_{}\[\]()<>#+\-.!|~:$])")


def escapar_markdown(texto: object) -> str:
    """Devolve o texto para ser exibido literalmente, sem virar link, imagem ou formatação."""
    return _ESPECIAIS.sub(r"\\\1", str(texto))


def link_gmail(message_id: str) -> str:
    """Busca a mensagem original no Gmail pelo Message-ID.

    O conteúdo do e-mail não é guardado no banco (minimização): a atendente lê
    no Gmail. O id vem de fora e é codificado para não alterar a URL.
    """
    return f"https://mail.google.com/mail/u/0/#search/rfc822msgid%3A{quote(message_id, safe='')}"
