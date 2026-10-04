import re

import pytest

from triagem.formatacao import escapar_markdown, link_gmail

# Sintaxes que, sem escape, o markdown transformaria em imagem, link ou fórmula
ATAQUES = {
    "imagem rastreadora": "boleto ![](http://atacante.com/pixel.png?chamado=123)",
    "link de phishing": "[Confirme seus dados](http://site-falso.com)",
    "link automático": "acesse http://site-falso.com/login",
    "link automático www": "acesse www.site-falso.com",
    "fórmula": "valor $x^2$",
    "html": "<img src=x>",
}


@pytest.mark.parametrize("texto", ATAQUES.values(), ids=ATAQUES.keys())
def test_sintaxe_perigosa_fica_escapada(texto):
    escapado = escapar_markdown(texto)
    # nenhum caractere especial sobra sem a barra na frente
    assert not re.search(r"(?<!\\)[!\[\]()<>:$]", escapado)


def test_imagem_vira_texto_literal():
    assert escapar_markdown("![](http://a.com/p.png)") == r"\!\[\]\(http\://a\.com/p\.png\)"


def test_texto_comum_continua_legivel():
    texto = "Vazamento no apto 42, bloco B"
    assert escapar_markdown(texto).replace("\\", "") == texto


def test_aceita_valor_que_nao_e_texto():
    assert escapar_markdown(42) == "42"


def test_link_gmail_busca_pelo_message_id():
    assert link_gmail("<abc123@mail.gmail.com>") == (
        "https://mail.google.com/mail/u/0/#search/rfc822msgid%3A%3Cabc123%40mail.gmail.com%3E"
    )


def test_link_gmail_codifica_id_malicioso():
    # caracteres que poderiam mudar a URL (outro parâmetro, outro caminho) ficam codificados
    url = link_gmail("x&y=1#/../evil")
    assert url.endswith("x%26y%3D1%23%2F..%2Fevil")
