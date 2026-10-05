import json

from triagem.avaliacao import calcular_metricas, rodar
from triagem.classificador import Classificador


def resultado(id, nivel_final, urgencia_llm, categoria="manutencao", revisao=False):
    return {
        "id": id,
        "nivel_final": nivel_final,
        "urgencia_llm": urgencia_llm,
        "categoria": categoria,
        "requer_revisao": revisao,
        "llm_falhou": False,
        "filtrado_como_propaganda": False,
        "motivos": [],
    }


def gabarito(**niveis):
    return {i: {"nivel_esperado": n, "categorias_aceitas": "manutencao|outros"} for i, n in niveis.items()}


def test_recall_compara_sistema_e_llm_sozinho():
    # 2 urgentes esperados: o LLM pegou 1; as regras recuperaram o outro
    resultados = [
        resultado("A", "urgente", "urgente"),
        resultado("B", "urgente", "importante"),  # ex.: síndico ou elevador subiu
        resultado("C", "normal", "normal"),
    ]
    m = calcular_metricas(resultados, gabarito(A="urgente", B="urgente", C="normal"))
    assert m.recall_urgente_llm == 0.5
    assert m.recall_urgente_sistema == 1.0
    assert m.urgentes_perdidos == []


def test_alarme_falso_e_urgente_perdido_sao_listados():
    resultados = [
        resultado("A", "importante", "importante"),  # urgente perdido
        resultado("B", "urgente", "normal"),  # alarme falso do sistema
    ]
    m = calcular_metricas(resultados, gabarito(A="urgente", B="normal"))
    assert m.urgentes_perdidos == ["A"]
    assert m.alarmes_falsos == ["B"]
    assert m.alarmes_falsos_llm == 0
    assert m.confusao[("urgente", "importante")] == 1


def test_categoria_aceita_qualquer_uma_das_listadas():
    resultados = [
        resultado("A", "normal", "normal", categoria="outros"),
        resultado("B", "normal", "normal", categoria="lixo"),
    ]
    m = calcular_metricas(resultados, gabarito(A="normal", B="normal"))
    assert m.acerto_categoria == 0.5


def test_ignora_emails_ainda_nao_avaliados():
    m = calcular_metricas([resultado("A", "urgente", "urgente")], gabarito(A="urgente", B="urgente"))
    assert m.total == 1
    assert m.recall_urgente_sistema == 1.0


# --- rodar(): a avaliação passa pelo pipeline de produção ---------------------

RESPOSTA = (
    '{"categoria": "manutencao", "urgencia": "urgente", "em_duvida": false,'
    ' "elevador_parado": false, "resumo": "r", "motivo": "m"}'
)


class LLMQueAnota:
    nome_modelo = "falso"

    def __init__(self):
        self.recebidos: list[str] = []

    def gerar_json(self, sistema, usuario, schema):
        self.recebidos.append(usuario)
        return RESPOSTA


def _amostra(pasta):
    emails = [
        {
            "id": "boleto",
            "remetente": "a@b.com",
            "assunto": "boleto",
            "corpo": "segunda via do boleto",
            "recebido_em": "2026-10-01T08:00:00-03:00",
        },
        {
            "id": "loja",
            "remetente": "loja@x.com",
            "assunto": "Aproveite a promoção",
            "corpo": "Para não receber mais nossos e-mails, clique aqui.",
            "recebido_em": "2026-10-01T09:00:00-03:00",
        },
        {
            "id": "gas",
            "remetente": "c@d.com",
            "assunto": "cheiro estranho",
            "corpo": "cheiro de gás no hall",
            "recebido_em": "2026-10-01T11:00:00-03:00",
        },
    ]
    caminho = pasta / "amostra.json"
    caminho.write_text(json.dumps(emails), encoding="utf-8")
    return caminho


def test_rodar_usa_filtro_e_ordem_do_pipeline(tmp_path):
    llm = LLMQueAnota()
    saida = tmp_path / "resultados.jsonl"
    rodar(_amostra(tmp_path), saida, Classificador(llm, 1))

    registros = {r["id"]: r for r in map(json.loads, saida.read_text(encoding="utf-8").splitlines())}
    assert set(registros) == {"boleto", "loja", "gas"}
    assert registros["loja"]["filtrado_como_propaganda"]
    assert len(llm.recebidos) == 2  # propaganda não chegou ao LLM
    assert "cheiro de gás" in llm.recebidos[0]  # urgente primeiro, como na produção


def test_rodar_retoma_sem_chamar_o_llm_de_novo(tmp_path):
    amostra, saida = _amostra(tmp_path), tmp_path / "resultados.jsonl"
    rodar(amostra, saida, Classificador(LLMQueAnota(), 1))

    segunda = LLMQueAnota()
    rodar(amostra, saida, Classificador(segunda, 1))
    assert segunda.recebidos == []
    assert len(saida.read_text(encoding="utf-8").splitlines()) == 3
