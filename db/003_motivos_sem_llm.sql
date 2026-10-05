-- Motivos são para a atendente: explicam regras de negócio, não a tecnologia.
-- Remove o "LLM: <nível>" (o nível do modelo já fica em urgencia_llm),
-- reescreve os textos antigos que citavam o LLM e acentua síndico/subsíndico.
-- Mantém a ordem dos motivos; pode ser reaplicada sem efeito colateral.

UPDATE triagens
SET motivos = ARRAY(
    SELECT CASE
        WHEN m = 'LLM não devolveu classificação válida' THEN 'Classificação automática falhou: conferir no Gmail'
        WHEN m = 'LLM em dúvida entre dois níveis' THEN 'Classificação em dúvida entre dois níveis'
        WHEN m LIKE 'Dúvida do LLM: %' THEN replace(m, 'Dúvida do LLM', 'Classificação em dúvida')
        WHEN m = 'Corpo vazio com anexo: conteúdo não lido na v1' THEN 'Conteúdo só no anexo: abrir no Gmail'
        WHEN m LIKE 'Remetente é sindico %' THEN replace(m, 'é sindico', 'é síndico')
        WHEN m LIKE 'Remetente é subsindico %' THEN replace(m, 'é subsindico', 'é subsíndico')
        ELSE m
    END
    FROM unnest(motivos) WITH ORDINALITY AS u(m, ordem)
    WHERE m NOT LIKE 'LLM:%'
    ORDER BY ordem
);
