# Cliente 02: Alvorada Gestão Condominial (triagem e classificação de e-mails)

Empresa fictícia. Caso simulado para portfólio.
Playbook de referência: https://claude.ai/code/artifact/0e27935f-96ef-4b07-a98d-30a3f305f6b9

## A empresa
- Alvorada Gestão Condominial, administradora de condomínios em Santo André (SP)
- Cuida da parte financeira, manutenção, cobrança, assembleias e reservas dos condomínios
- Sistema de gestão: CondoGestor, na nuvem, pago por mensalidade (cadastro, boletos, chamados). Não se sabe se tem integração com outros sistemas
- E-mail: Google Workspace (Gmail pago com domínio próprio), caixa única atendimento@ divulgada no site, nos boletos e nas circulares
- Também atende por WhatsApp, fora do foco deste projeto

## O problema, em números
- Cerca de 2.400 e-mails por mês (2.380 em setembro); segunda-feira recebe quase o dobro de um dia normal
- Três atendentes (Juliana, Priscila e Tânia) leem por ordem de chegada e encaminham ao setor, repassando o e-mail ou abrindo chamado no CondoGestor com copiar e colar
- Urgência que chega depois de dezenas de e-mails simples fica esperando na fila
- Estimativa do Sérgio: 2 a 3 urgências reais por semana (ninguém registra)
- Caso recente: vazamento ficou quase dois dias sem ser visto e o síndico reclamou direto com o Sérgio
- O campo "tipo" do chamado no CondoGestor não bate com as categorias internas; as atendentes marcam "Outros" em cerca de metade dos casos

## Quem é o Sérgio Tavares
- Sócio da Alvorada, sem conhecimento técnico
- Maior preocupação: urgência perdida e síndico insatisfeito, porque síndico insatisfeito é contrato perdido
- Prazo: funcionando até meados de novembro, antes das chuvas de dezembro e janeiro, quando mais acontecem vazamentos e infiltrações

## Restrição do portfólio
- Projeto de até 1 semana: MVP funcionando, com arquitetura que não impeça escalar depois
- Descoberta simplificada e custo fora da conversa por decisão do Gutto: foco na prática de construção
- Projeto enxuto; aprofundamento de chunking fica como experimento de melhoria no projeto 1
- O que ficar de fora da v1 entra como roadmap no README

## O que a descoberta revelou
- Categorias usadas de cabeça pelas atendentes, por setor:
  - Financeiro: segunda via de boleto, dúvida de valor, comprovante de pagamento
  - Manutenção: consertos e problemas no prédio
  - Cobrança: inadimplência, acordo, carta de advogado
  - Assembleia e reserva: salão de festa, churrasqueira, convocação, ata
  - Cadastro: morador novo, mudança, troca de proprietário
  - Fornecedor: orçamento, nota fiscal, cobrança de prestador
  - Lixo: propaganda e similares
- Anexos frequentes: fotos (vazamento, rachadura, carro na vaga), comprovantes em PDF ou print, orçamentos em PDF; planilhas são raras
- Há e-mails só com "segue anexo" e o conteúdo inteiro no arquivo
- Moradores escrevem "URGENTE" no assunto de quase tudo; as atendentes já ignoram
- E-mail de síndico sempre recebe mais atenção, mesmo com assunto simples
- Não existia regra escrita de urgência e as atendentes divergiam (ex.: infiltração). A regra abaixo foi definida pelo Sérgio com as três

## Regra de urgência (definida pelo cliente)
**Urgente (mesmo dia, em poucas horas)**
- Vazamento ativo, cano estourado, água descendo
- Falta de água no prédio ou em vários apartamentos
- Cheiro de gás
- Elevador parado com gente dentro
- Elevador parado em prédio com um único elevador
- Portão da garagem ou da entrada que não fecha
- Falta de luz nas áreas comuns (escada, garagem, hall)
- Infiltração pingando ou perto de fiação

**Importante (até 2 dias úteis)**
- Infiltração sem pingar, mancha, mofo
- Um elevador parado com outro funcionando
- Interfone quebrado
- Lâmpada queimada fora da escada e da garagem
- Carta de advogado ou notificação da prefeitura (têm prazo)

**Normal (fila comum)**
- Boleto, dúvida de valor, comprovante
- Reserva de área comum
- Cadastro e mudança
- Orçamento e nota de fornecedor
- Barulho de vizinho: não é responsabilidade da administradora; atendente orienta procurar síndico ou portaria

**Combinados**
- "URGENTE" no assunto não conta; vale o conteúdo do texto
- E-mail de síndico sobe um nível
- Na dúvida entre dois níveis, fica no mais alto

## Pontos de atenção levantados na revisão
- A regra do síndico mistura urgência do problema com prioridade do negócio. Direção: o LLM classifica a urgência do conteúdo; o código confere o remetente numa lista de e-mails de síndicos e calcula a prioridade final. Assinatura no texto não serve como prova de que é síndico
- A regra da dúvida pode inflar as urgências e recriar o problema do "URGENTE" no assunto. Direção: a dúvida vira campo explícito na saída do modelo e o código decide (subir o nível ou mandar para revisão humana)
- Erros têm custos diferentes: perder uma urgência é muito pior que um alarme falso

## Direções para a v1 (a validar no bloco 2)
- Entrada: e-mails fictícios em arquivos (JSON ou .eml), lidos por uma função de entrada que depois pode ser trocada por leitura do Gmail
- Dados: 150 a 200 e-mails fictícios rotulados à mão (categoria, urgência, campos), incluindo casos difíceis: corpo vazio com anexo, propaganda, e-mail com dois assuntos, escrita informal, "URGENTE" falso, e-mail de síndico
- Saída: tabela no PostgreSQL e painel simples com a fila ordenada por prioridade
- Métrica principal: recall da classe urgente, com limite de alarmes falsos

## Arquitetura da v1 (pipeline)
Workflow fixo: o código decide o caminho; o LLM só executa o passo de linguagem (classificar).

```
e-mails (JSON hoje, Gmail amanhã)          entrada.py      FonteEmails (protocolo) / FonteJson
   ↓
1. Leitura e limpeza (código)              limpeza.py      tira histórico, "Enviado do meu iPhone", assinatura, "URGENTE" do assunto
   ↓
2. Classificação (Qwen via Ollama)         classificador.py + llm.py + prompts/classificacao_v1.md
   devolve JSON, validado com Pydantic     modelos.py      Classificacao (schema enviado ao Ollama)
   ↓
3. Regras de negócio (código + CSV)        regras.py       + data/condominios.csv
   ↓
4. PostgreSQL                              repositorio.py  + db/001_init.sql (tabela triagens)
   ↓
5. Painel de fila por prioridade           painel.py       Streamlit
```

Orquestração em `pipeline.py`. Stack: Python 3.12+, uv, Pydantic, httpx, psycopg 3, Streamlit, Postgres 17 no Docker.

### Decisões tomadas na estruturação
- **LLM atrás de interface** (`ClienteLLM`): trocar Qwen local por outro modelo é uma classe nova, sem mexer no pipeline. Modelo padrão `qwen3:8b`, `temperature=0`, saída restrita ao JSON Schema do Pydantic
- **LLM classifica só a urgência do conteúdo**; síndico, elevador e dúvida são decididos no código
- **Dúvida**: o modelo marca `em_duvida` + `urgencia_alternativa`; o código fica no nível mais alto (regra do cliente) e marca para revisão humana. Isso respeita o combinado e mantém visível quanto a dúvida está inflando a fila (medir nos evals)
- **Elevador**: o modelo só diz `elevador_parado`; o código cruza com `qtd_elevadores` do condomínio. Condomínio não identificado → urgente + revisão (perder urgência custa mais que alarme falso)
- **Síndico**: só pelo e-mail do remetente cadastrado no CSV; assinatura no texto não conta. Sobe um nível, aplicado por último
- **Palavras-chave críticas**: rede de segurança, não classificador. Só sobem nível (nunca rebaixam o LLM) e sempre mandam para revisão. Gás, pessoa presa, fogo e cano estourado → urgente; vazamento, falta de água ou luz e portão → importante. Rodam mesmo se o LLM falhar
- **Falha do LLM** (JSON inválido após 2 tentativas ou Ollama fora): o e-mail não se perde, vai para a fila com revisão humana
- **Corpo vazio com anexo** → revisão (anexo não é lido na v1)
- **Idempotência**: `email_id` único no banco; reprocessar não duplica
- **Auditoria**: cada triagem grava `motivos` (por que está nesse nível), a saída completa do LLM, o modelo e a versão do prompt
- **Prompt injection indireta**: o prompt trata o e-mail como dado e o corpo vai delimitado por `<email>`; regras críticas não dependem do prompt

### Primeira execução real (02 e 03/10/2026)
- 8 e-mails de exemplo classificados, todos no nível esperado. Regra do elevador (ex-004) e do síndico (ex-003) corrigiram o LLM como previsto
- Lentidão inicial (até ~9 min por e-mail) era a conexão com o Postgres, não o modelo: no Windows, `localhost` tenta IPv6 primeiro e ficava ~130 s pendurado, 2 conexões por e-mail. Corrigido com `127.0.0.1` e uma conexão por rodada (`with Repositorio(...)`)
- Medido com o modelo carregado, na tomada: ~26 s por e-mail no `qwen3:8b` em CPU (i7-1255U, sem GPU); 5 s lendo o prompt (~720 tokens) e 22 s gerando (~100 tokens, 4 tok/s). Na bateria e com memória cheia, piora bastante
- LLM não extraiu "Jardim das Acácias" no ex-001 (`condominio_mencionado: null`): caso para o dataset de evals

### Análise da amostra de setembro (03/10/2026)
149 e-mails em `data/amostras/emails_setembro.json`, rotulados manualmente (provisório, a validar): 27 urgentes, 21 importantes, 101 normais.
- Filtro antes do LLM: propaganda não passa pelo LLM (parece propaganda E tem descadastro, no cabeçalho `List-Unsubscribe` ou escrito no corpo); vai para o banco como `lixo`, sem ser apagada. O resto é ordenado por palavra-chave (urgente → importante → resto, e por chegada dentro de cada grupo)
- Duas listas de palavras, por custo de erro diferente: a da **fila** é larga (falso positivo só adianta a classificação) e inclui automaticamente a da **rede de segurança**, que é estreita (falso positivo vira alarme na fila da atendente)
- Depois de ajustar as listas com a amostra e corrigir a limpeza: a fila pega 27/27 urgentes (antes 16/27); as 4 expressões novas da rede não geraram nenhum falso positivo
- Teste com o Qwen real (4 e-mails): propaganda filtrada sem LLM; urgentes classificados antes do boleto que chegou primeiro
- Limite da palavra-chave, com prova (resposta ao mentor): E032 "**não** tem cheiro de gás" e E113 "quero agradecer... quando **fiquei presa** no elevador" acionam a rede como urgente; palavra-chave não entende negação nem tempo verbal

**Corrigido:**
- Bug na limpeza: e-mail encaminhado (E048, "buraco aberto, alguém pode cair") ficava com corpo vazio. Agora o encaminhamento perde só a marca e o cabeçalho; resposta continua cortando o histórico
- Formato da amostra (`data`, `remetente_email`, anexos como texto) traduzido na entrada (`entrada.py`); o resto do pipeline só conhece o `Email`

**Limitações conhecidas:**
- Filtro de propaganda pega 1/10 na amostra (E009), com zero falso positivo. A amostra não tem cabeçalhos; no Gmail real o `List-Unsubscribe` deve elevar isso. Prospecção de fornecedor sem descadastro (E053, E093, E115, E145) vai para o LLM, que a classifica como lixo
- Golpes (E021 "conta será bloqueada", E037 "envie seu CPF") não são propaganda: tratar no bloco de segurança

**Perguntas para o Sérgio (rótulos em dúvida):**
- Falta de água em **um só** apartamento (E070): a regra fala em "prédio ou vários apartamentos". Fica importante?
- Lâmpada queimada no **hall** (E094): o hall está em "falta de luz nas áreas comuns" (urgente), mas lâmpada queimada está em importante. Qual vale?
- Vazamento "pequeno", pingando devagar (E117): vazamento ativo é urgente. Vale também para os pequenos?
- Portão travado **fechado**, ninguém sai pela rua (E128): a regra fala só em portão que não fecha
- Riscos fora da regra: buraco aberto no estacionamento (E048/E081) e fio solto no playground (E073). Que nível?

### Pontos em aberto
- Fila de classificação: mesmo a ~26 s por e-mail, uma urgência espera os e-mails à frente dela serem classificados (segunda-feira com 200 e-mails ≈ 1h30). Em discussão: modelo menor, GPU/API, ordem de processamento, filtro antes do LLM
- Lixo com palavra-chave (ex.: propaganda de "conserto de vazamento") vai subir para importante + revisão. Aceito por ora; medir nos evals
- Identificação do condomínio de morador depende do nome citado no texto (busca simples por nome). Avaliar se vale pedir ao cliente uma lista de e-mails de moradores
- Modelo Qwen exato (tamanho) decidido nos evals do bloco 9

## Candidatos a ficar fora da v1
- WhatsApp
- Leitura do conteúdo dos anexos
- Integração com o CondoGestor (pendente: perguntar ao suporte se existe API)
- Leitura direta da caixa real do Gmail

## Blocos do projeto
1. Descoberta com o cliente (concluído, simplificado)
2. Precisa de IA? Qual tipo?
3. Dataset e rotulagem
4. Schema e prompt de classificação
5. Saída estruturada e validação
6. Regras de negócio (síndico, dúvida, revisão humana)
7. Armazenamento e painel
8. Segurança e LGPD
9. Avaliação (evals)
10. Deploy
11. Case de portfólio

## Status
- Bloco atual: 2 (precisa de IA? qual tipo?)
- Esqueleto do código montado (02/10/2026): pipeline ponta a ponta, regras de negócio com 22 testes passando; prompt v1 é rascunho para o bloco 4
- Pergunta aberta do mentor: por que não resolver com palavras-chave, tipo "vazamento" vira urgente?
