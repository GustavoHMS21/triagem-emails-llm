-- Tabela única da v1: um registro por e-mail triado.
-- Roda sozinho na primeira subida do docker-compose (pasta montada em docker-entrypoint-initdb.d).

CREATE TABLE IF NOT EXISTS triagens (
    id                BIGSERIAL PRIMARY KEY,
    email_id          TEXT        NOT NULL UNIQUE,  -- Message-ID: reprocessar não duplica
    remetente         TEXT        NOT NULL,
    assunto_original  TEXT        NOT NULL,
    assunto           TEXT        NOT NULL,
    corpo             TEXT        NOT NULL,
    anexos            JSONB       NOT NULL DEFAULT '[]',
    recebido_em       TIMESTAMPTZ NOT NULL,

    -- saída do LLM (NULL quando ele falhou)
    categoria         TEXT,
    outras_categorias TEXT[]      NOT NULL DEFAULT '{}',
    urgencia_llm      TEXT,
    resumo            TEXT,
    classificacao     JSONB,                         -- saída completa, para auditoria e evals

    -- resultado das regras de negócio
    condominio_id     TEXT,
    remetente_sindico BOOLEAN     NOT NULL,
    nivel_final       SMALLINT    NOT NULL CHECK (nivel_final BETWEEN 1 AND 3),  -- 3 = urgente
    requer_revisao    BOOLEAN     NOT NULL,
    motivos           TEXT[]      NOT NULL,

    -- rastreabilidade
    modelo            TEXT        NOT NULL,
    prompt_versao     TEXT        NOT NULL,

    -- atendimento
    status            TEXT        NOT NULL DEFAULT 'pendente'
                      CHECK (status IN ('pendente', 'em_atendimento', 'concluido')),
    triado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A fila do painel: pendentes, mais urgente primeiro, depois revisão, depois o mais antigo
CREATE INDEX IF NOT EXISTS idx_triagens_fila
    ON triagens (status, nivel_final DESC, requer_revisao DESC, recebido_em ASC);
