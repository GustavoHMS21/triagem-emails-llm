from datetime import datetime

import httpx
import pytest

from triagem import classificador as modulo
from triagem.classificador import Classificador
from triagem.limpeza import limpar
from triagem.llm import ClienteOllama, ErroLLM
from triagem.modelos import Email

VALIDO = (
    '{"categoria": "manutencao", "urgencia": "urgente", "em_duvida": false,'
    ' "elevador_parado": false, "resumo": "r", "motivo": "m"}'
)
INVALIDO = VALIDO.replace('"urgente"', '"MUITO ALTA"')

EMAIL = limpar(Email(id="e1", remetente="a@b.com", corpo="cheiro de gás no hall", recebido_em=datetime(2026, 10, 1)))


class LLMRoteiro:
    """Devolve as respostas do roteiro em ordem; ErroLLM no roteiro é levantado."""

    nome_modelo = "roteiro"

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.mensagens: list[str] = []

    def gerar_json(self, sistema, usuario, schema):
        self.mensagens.append(usuario)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


@pytest.fixture
def esperas(monkeypatch):
    """Registra os time.sleep em vez de esperar de verdade."""
    registro = []
    monkeypatch.setattr(modulo.time, "sleep", registro.append)
    return registro


# --- Retry por formato inválido ---------------------------------------------


def test_formato_invalido_reenvia_dizendo_o_que_corrigir(esperas):
    llm = LLMRoteiro(INVALIDO, VALIDO)
    resultado = Classificador(llm, tentativas=2).classificar(EMAIL)

    assert resultado.urgencia == "urgente"
    assert "rejeitada pela validação" in llm.mensagens[1]
    assert "urgencia" in llm.mensagens[1]
    assert esperas == []  # erro de formato não espera


def test_correcao_nao_ecoa_o_valor_gerado_pelo_modelo(esperas):
    llm = LLMRoteiro(INVALIDO, VALIDO)
    Classificador(llm, tentativas=2).classificar(EMAIL)
    assert "MUITO ALTA" not in llm.mensagens[1]


# --- Retry por falha transitória --------------------------------------------


def test_falha_transitoria_espera_com_backoff_exponencial(esperas):
    llm = LLMRoteiro(ErroLLM("timeout"), ErroLLM("timeout"), VALIDO)
    resultado = Classificador(llm, tentativas=3, espera_s=2).classificar(EMAIL)

    assert resultado is not None
    assert esperas == [2, 4]
    assert llm.mensagens[0] == llm.mensagens[2]  # falha transitória não muda o prompt


def test_esgotadas_as_tentativas_devolve_none_sem_esperar_no_fim(esperas):
    llm = LLMRoteiro(ErroLLM("fora do ar"), ErroLLM("fora do ar"))
    assert Classificador(llm, tentativas=2, espera_s=1).classificar(EMAIL) is None
    assert esperas == [1]


# --- Adaptador do Ollama traduz falhas para ErroLLM -------------------------


@pytest.mark.parametrize(
    "resposta",
    [
        httpx.Response(200, json={"done": True}),  # JSON sem message
        httpx.Response(200, text="<html>Bad Gateway</html>"),  # proxy no meio
        httpx.Response(500, json={"error": "model crashed"}),
    ],
    ids=["sem-message", "html", "erro-500"],
)
def test_ollama_traduz_resposta_inesperada_para_erro_llm(resposta):
    http = httpx.Client(transport=httpx.MockTransport(lambda req: resposta))
    llm = ClienteOllama("http://ollama", "qwen3:8b", http=http)
    with pytest.raises(ErroLLM):
        llm.gerar_json("sistema", "usuario", {})


def test_ollama_fora_do_ar_vira_erro_llm():
    def recusa(req):
        raise httpx.ConnectError("conexão recusada")

    llm = ClienteOllama("http://ollama", "qwen3:8b", http=httpx.Client(transport=httpx.MockTransport(recusa)))
    with pytest.raises(ErroLLM):
        llm.gerar_json("sistema", "usuario", {})
