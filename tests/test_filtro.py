from datetime import datetime

from triagem.classificador import Classificador
from triagem.filtro import chave_da_fila, motivo_propaganda
from triagem.limpeza import limpar
from triagem.modelos import Email, Nivel
from triagem.pipeline import processar
from triagem.regras import CadastroCondominios

DESCADASTRO = {"List-Unsubscribe": "<mailto:sair@loja.com>"}


def email(id="e1", assunto="assunto", corpo="texto do morador", hora=9, cabecalhos=None):
    return Email(
        id=id, remetente="morador@gmail.com", assunto=assunto, corpo=corpo,
        recebido_em=datetime(2026, 10, 1, hora, 0), cabecalhos=cabecalhos or {},
    )


# --- Propaganda --------------------------------------------------------------


def test_propaganda_precisa_de_descadastro_e_expressao():
    assert motivo_propaganda(limpar(email(assunto="PROMOÇÃO", cabecalhos=DESCADASTRO)))


def test_descadastro_escrito_no_corpo_vale_como_cabecalho():
    # E009: sem cabeçalho, mas com o aviso de descadastro no texto
    e = email(assunto="Últimas vagas: curso", corpo="Clique aqui.\nPara não receber mais nossos e-mails, clique aqui.")
    assert "descadastro no texto" in motivo_propaganda(limpar(e))


def test_expressao_sem_descadastro_nao_e_propaganda():
    assert motivo_propaganda(limpar(email(assunto="PROMOÇÃO"))) is None


def test_descadastro_sem_expressao_nao_e_propaganda():
    # ex.: boletim do sistema com link de descadastro, mas sem cara de marketing
    assert motivo_propaganda(limpar(email(assunto="Boletim mensal", cabecalhos=DESCADASTRO))) is None


def test_fornecedor_citando_desconto_nao_e_propaganda():
    e = email(assunto="Orçamento portão", corpo="Segue orçamento com desconto de 5% à vista.")
    assert motivo_propaganda(limpar(e)) is None


# --- Ordem da fila -----------------------------------------------------------


def test_urgente_passa_na_frente_mesmo_chegando_depois():
    boleto = limpar(email(id="boleto", corpo="segunda via do boleto", hora=8))
    gas = limpar(email(id="gas", corpo="cheiro de gás no hall", hora=11))
    assert [e.original.id for e in sorted([boleto, gas], key=chave_da_fila)] == ["gas", "boleto"]


def test_mesmo_grupo_segue_ordem_de_chegada():
    cedo = limpar(email(id="cedo", corpo="segunda via", hora=8))
    tarde = limpar(email(id="tarde", corpo="reserva do salão", hora=10))
    assert [e.original.id for e in sorted([tarde, cedo], key=chave_da_fila)] == ["cedo", "tarde"]


def test_agua_em_movimento_entra_na_fila_como_urgente():
    e = limpar(email(corpo="ta descendo agua pela parede da escada"))
    assert chave_da_fila(e)[0] == -Nivel.URGENTE


# --- Pipeline com LLM falso --------------------------------------------------


class LLMFalso:
    """Responde na hora e anota o que recebeu, para checar ordem e quem passou."""

    nome_modelo = "falso"

    def __init__(self):
        self.recebidos: list[str] = []

    def gerar_json(self, sistema: str, usuario: str, schema: dict) -> str:
        self.recebidos.append(usuario)
        return (
            '{"categoria": "manutencao", "urgencia": "normal", "em_duvida": false,'
            ' "elevador_parado": false, "resumo": "r", "motivo": "m"}'
        )


class FonteLista:
    def __init__(self, emails):
        self.emails = emails

    def ler(self):
        yield from self.emails


def test_pipeline_pula_propaganda_e_classifica_urgente_primeiro():
    llm = LLMFalso()
    fonte = FonteLista([
        email(id="boleto", assunto="boleto", corpo="segunda via do boleto", hora=8),
        email(id="loja", assunto="Aproveite a promoção", cabecalhos=DESCADASTRO, hora=9),
        email(id="gas", assunto="cheiro estranho", corpo="cheiro de gás no hall", hora=11),
    ])

    resultados = processar(fonte, Classificador(llm, 1), CadastroCondominios([]), repositorio=None)

    # propaganda não chegou ao LLM: só 2 chamadas, e a primeira foi a do gás
    assert len(llm.recebidos) == 2
    assert "cheiro de gás" in llm.recebidos[0]
    propaganda = next(t for t in resultados if t.email.original.id == "loja")
    assert propaganda.categoria == "lixo"
    assert propaganda.modelo == "nenhum (filtro)"
