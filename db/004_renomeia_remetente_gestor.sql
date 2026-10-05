-- Desde que o subsíndico passou a subir a prioridade, a coluna significa
-- "remetente é síndico OU subsíndico". O nome passa a dizer isso.
--
-- Renomear quebra o código que ainda usa o nome antigo: aqui (um processo só)
-- a migração e o código novo sobem juntos. Com várias instâncias no ar, o
-- caminho seria expand/contract: criar a coluna nova, gravar nas duas, migrar
-- o código e só então remover a antiga.

ALTER TABLE triagens RENAME COLUMN remetente_sindico TO remetente_gestor;
