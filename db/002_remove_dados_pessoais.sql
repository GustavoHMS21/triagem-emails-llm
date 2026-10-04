-- Minimização (LGPD, art. 6º, III): o conteúdo dos e-mails fica só no Gmail.
-- O banco guarda apenas o necessário para ordenar a fila; email_id é a
-- referência para abrir a mensagem no Gmail.

-- Registros antigos têm texto do e-mail nos motivos (motivo do LLM, trecho da palavra-chave)
DELETE FROM triagens;

ALTER TABLE triagens
    DROP COLUMN IF EXISTS remetente,
    DROP COLUMN IF EXISTS assunto_original,
    DROP COLUMN IF EXISTS assunto,
    DROP COLUMN IF EXISTS corpo,
    DROP COLUMN IF EXISTS anexos,
    DROP COLUMN IF EXISTS resumo,
    DROP COLUMN IF EXISTS classificacao,
    ADD COLUMN IF NOT EXISTS tem_anexo BOOLEAN NOT NULL DEFAULT false;
