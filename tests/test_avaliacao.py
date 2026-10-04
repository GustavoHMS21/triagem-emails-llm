from triagem.avaliacao import calcular_metricas


def resultado(id, nivel_final, urgencia_llm, categoria="manutencao", revisao=False):
    return {
        "id": id, "nivel_final": nivel_final, "urgencia_llm": urgencia_llm, "categoria": categoria,
        "requer_revisao": revisao, "llm_falhou": False, "filtrado_como_propaganda": False, "motivos": [],
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
    resultados = [resultado("A", "normal", "normal", categoria="outros"), resultado("B", "normal", "normal", categoria="lixo")]
    m = calcular_metricas(resultados, gabarito(A="normal", B="normal"))
    assert m.acerto_categoria == 0.5


def test_ignora_emails_ainda_nao_avaliados():
    m = calcular_metricas([resultado("A", "urgente", "urgente")], gabarito(A="urgente", B="urgente"))
    assert m.total == 1
    assert m.recall_urgente_sistema == 1.0
