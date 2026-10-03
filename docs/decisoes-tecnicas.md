# Decisões técnicas: triagem de e-mails da Alvorada

Como o sistema funciona por dentro, por que foi feito assim e como explicar cada decisão numa entrevista técnica. Segurança tem documento próprio: [seguranca.md](seguranca.md).

## Visão geral

Workflow fixo em Python: o código decide o caminho, o LLM executa só o passo de linguagem.

```
FonteJson → limpeza → filtro (propaganda / ordem) → Classificador ──HTTP──▶ Ollama (Qwen3 8B)
                                                         │
                                                  regras de negócio ◀── condominios.csv
                                                         │
                                                  Repositorio ──psycopg──▶ PostgreSQL ◀── painel Streamlit
```

Princípio que guia tudo: **o LLM não é dono de nenhuma regra determinística.** Ele julga o que depende de linguagem (categoria, urgência do conteúdo); regra exata (síndico, número de elevadores, palavra crítica) fica em código testável.

---

## 1. Integrações (APIs)

### 1.1 Ollama: API REST do LLM

| | |
|---|---|
| O que é | Servidor local que roda o modelo Qwen3 8B e expõe uma API HTTP |
| Endpoint | `POST http://localhost:11434/api/chat` |
| Cliente | `httpx` (cliente HTTP síncrono, com timeout configurável) |
| Código | [src/triagem/llm.py](../src/triagem/llm.py) |

**O que vai na requisição e por quê:**

| Campo | Valor | Motivo |
|---|---|---|
| `messages` | `system` (prompt com regras) + `user` (e-mail) | Separa instrução de dado |
| `format` | JSON Schema gerado do Pydantic | **Saída estruturada**: o Ollama restringe a geração token a token para só produzir JSON que siga o schema (*constrained decoding*) |
| `options.temperature` | `0` | Classificação precisa ser reprodutível: mesmo e-mail, mesma resposta |
| `think` | `false` | O Qwen3 tem modo de raciocínio longo; aqui só gastaria tempo |
| `stream` | `false` | Precisamos do JSON inteiro para validar; streaming não ajuda |

**Como a integração fica isolada:** o classificador não conhece o Ollama. Ele depende de uma **interface** (`ClienteLLM`, um `typing.Protocol`) com um método só, `gerar_json(sistema, usuario, schema) -> str`. O `ClienteOllama` implementa essa interface. Trocar para outro provedor (OpenAI, Anthropic, Azure) é escrever outra classe com o mesmo método, sem tocar no resto. É o padrão **Ports and Adapters** (ou inversão de dependência). O mesmo mecanismo permite usar um LLM falso nos testes.

### 1.2 PostgreSQL: banco de dados

| | |
|---|---|
| Driver | `psycopg` 3 (protocolo nativo do Postgres, não é REST) |
| Infra | Container Docker `postgres:17`, porta 5433 |
| Código | [src/triagem/repositorio.py](../src/triagem/repositorio.py), [db/001_init.sql](../db/001_init.sql) |

- **Padrão Repository:** todo SQL fica numa classe só (`Repositorio`); o resto do código chama `salvar()`, `fila()`, `ja_triado()`.
- **Uma conexão por rodada** (`with Repositorio(url) as repo:`), com `autocommit`: cada e-mail salvo é gravado na hora; se o processo cair, nada do que já foi triado se perde.
- **Idempotência:** `email_id` é `UNIQUE` e o insert usa `ON CONFLICT DO NOTHING`. Reprocessar o mesmo lote não duplica nada, então rodar de novo depois de uma falha é seguro.
- **JSONB** guarda a resposta completa do LLM, para auditoria e evals.
- **Incidente resolvido:** cada conexão via `localhost` levava ~130 s, porque no Windows `localhost` tenta IPv6 (`::1`) primeiro e o Docker não respondia por ali. Diagnosticado cronometrando cada peça isoladamente; resolvido com `127.0.0.1`.

### 1.3 Streamlit: painel

Não é uma API: é o framework da interface. O painel lê a tabela `triagens` via `Repositorio` e permite mudar o status do chamado. **Limitação conhecida:** o painel fala direto com o banco. Em produção, com mais de um cliente (painel, app, integração), o certo é uma API própria no meio (ex.: FastAPI) com autenticação e autorização centralizadas.

### 1.4 Gmail API: planejada, fora da v1

A entrada depende do protocolo `FonteEmails` (método `ler()`). Hoje a implementação é `FonteJson`. A `FonteGmail` futura usaria:
- **OAuth 2.0** com escopo mínimo (`gmail.readonly`);
- `users.messages.list` + `users.messages.get` para ler as mensagens, com os **cabeçalhos** (de onde vem o `List-Unsubscribe` do filtro de propaganda);
- `users.watch` + Google Pub/Sub para ser avisado de e-mail novo, em vez de consultar a caixa a cada X minutos.

Nada do pipeline muda: só a fonte.

---

## 2. Validação de dados (três camadas)

| Camada | Onde | Ferramenta | O que garante |
|---|---|---|---|
| Entrada | `entrada.py` → `Email` | Pydantic | Todo e-mail tem id, remetente e data válida; formatos diferentes são traduzidos num lugar só (`_normalizar`) |
| Saída do LLM | `classificador.py` → `Classificacao` | JSON Schema + Pydantic | Categoria e urgência só podem ser valores da lista (`Literal`) |
| Banco | `001_init.sql` | `CHECK`, `NOT NULL`, `UNIQUE` | Mesmo com bug no Python, o banco recusa `nivel_final = 7` ou status inventado |

**Por que validar a saída do LLM duas vezes** (schema no Ollama e Pydantic na volta)? O schema no Ollama faz o modelo *tentar* acertar o formato; o Pydantic *garante*. Se um dia o provedor mudar, ou o modelo for trocado por um que não suporta saída estruturada, a validação continua de pé. **Nunca se confia em texto de LLM para acionar código sem validar.**

---

## 3. Retry e tratamento de falhas

**Como funciona hoje** ([classificador.py](../src/triagem/classificador.py)):
1. Chama o LLM e valida a resposta com `Classificacao.model_validate_json`.
2. Se der `ValidationError` (JSON fora do formato) ou `httpx.HTTPError` (timeout, conexão recusada, erro 5xx), registra no log e tenta de novo, até `LLM_TENTATIVAS` vezes (padrão 2).
3. Se todas falharem, devolve `None`. As regras de negócio tratam isso: o e-mail vai para a fila com **revisão humana** e o motivo "LLM não devolveu classificação válida". A rede de palavras-chave roda mesmo assim, então um "cheiro de gás" ainda sobe para urgente.

**Princípio:** o pipeline **nunca para e nunca perde e-mail** por causa do LLM. Falha vira revisão humana, não buraco na fila.

**Limitações que já identifiquei (e como melhoraria):**

| Limitação | Por que importa | Melhoria |
|---|---|---|
| Com `temperature=0`, repetir o mesmo prompt tende a gerar a mesma resposta inválida | O retry só ajuda de verdade em falha **transitória** (timeout, rede) | Para `ValidationError`, reenviar incluindo o erro ("o campo X veio inválido, corrija"), ou não repetir |
| Não há espera entre tentativas (*backoff*) | Se o Ollama estiver sobrecarregado, a segunda tentativa chega na hora errada | *Backoff* exponencial com *jitter* (ex.: 2 s, 4 s, 8 s + aleatório), via `tenacity` |
| Resposta HTTP sem a chave `message`, ou corpo que não é JSON, gera `KeyError`/`ValueError`, que **não** são capturados | Derruba o pipeline em vez de mandar para revisão | Capturar esses erros também, ou validar a resposta do Ollama com um modelo Pydantic |

---

## 4. Testes

- **Unitários** (`pytest`, 34 testes): limpeza, regras de negócio, filtro.
- **LLM falso:** como o classificador depende da interface `ClienteLLM`, os testes usam uma classe que responde na hora e **anota o que recebeu**. Isso prova, sem rodar o modelo (26 s por e-mail), que a propaganda nunca chega ao LLM e que o urgente é classificado primeiro.
- **Regressão:** cada bug corrigido ganha um teste (ex.: e-mail encaminhado com corpo vazio, E048), e um teste garante que a correção não quebrou o comportamento antigo (resposta continua cortando o histórico).
- **Medição em dados reais:** as listas de palavras-chave foram ajustadas medindo cobertura numa amostra de 149 e-mails rotulados (urgentes cobertos pela fila: 16/27 → 27/27), contando também os falsos positivos.

---

## 5. Rastreabilidade

- Prompt em arquivo versionado ([prompts/classificacao_v1.md](../src/triagem/prompts/classificacao_v1.md)); cada triagem grava `modelo` e `prompt_versao`.
- Cada triagem grava `motivos`: a trilha de por que o nível final é aquele ("LLM: importante", "Elevador parado e o prédio tem um só elevador: subiu para urgente").
- Propaganda filtrada grava `modelo = "nenhum (filtro)"`: dá para saber se uma decisão veio do LLM ou do código.

---

## Perguntas prováveis numa entrevista técnica

**"Como você garante que o LLM devolve um JSON válido?"**
> "Em duas camadas. Gero um JSON Schema a partir do modelo Pydantic e passo no campo `format` da API do Ollama, que restringe a geração do modelo a esse schema. Na volta, valido de novo com Pydantic, porque não confio em saída de LLM para acionar código. Se a validação falhar, tento de novo; se continuar falhando, o e-mail vai para revisão humana em vez de travar o pipeline."

**"Como funciona o retry?"**
> "O classificador tenta até N vezes, configurável, capturando erro de validação e erro HTTP. Esgotadas as tentativas, devolve nulo, e a regra de negócio manda para revisão humana, ainda passando pela rede de segurança de palavras-chave. Uma limitação que identifiquei: com temperatura zero, repetir o mesmo prompt tende a repetir o mesmo erro, então o retry só ajuda de verdade em falha transitória. A melhoria seria backoff exponencial para erro de rede e, para erro de validação, reenviar o prompt incluindo o erro."

**"Como você integrou o LLM? E se precisar trocar de provedor?"**
> "Via API REST do Ollama, com httpx. Mas o resto do sistema não conhece o Ollama: depende de uma interface com um único método, `gerar_json`. Trocar de provedor é escrever outro adaptador com esse método. Essa mesma interface me permitiu testar o pipeline com um LLM falso, sem esperar o modelo."

**"O que acontece se o processo cair no meio de um lote?"**
> "Nada se perde. Cada e-mail é gravado na hora (autocommit) e o `email_id` é único no banco, com `ON CONFLICT DO NOTHING`. Rodo de novo e o pipeline pula o que já foi triado."

**"Por que não usar só palavras-chave, que é mais barato?"**
> "Medi isso numa amostra de 149 e-mails. Palavra-chave não entende paráfrase ('o elevador parou' não tem palavra de urgência), negação ('não tem cheiro de gás' disparava urgente) nem tempo verbal ('quando fiquei presa no elevador', num e-mail de agradecimento). Por isso o LLM classifica, e a palavra-chave tem dois papéis onde erra barato: ordenar a fila e servir de rede de segurança, só subindo nível e sempre pedindo revisão humana."

**"Teve algum problema de performance?"**
> "O pipeline levava até 9 minutos por e-mail. Em vez de culpar o modelo, cronometrei cada peça separadamente: o modelo levava 26 segundos, e cada conexão com o Postgres, 130. Era o `localhost` tentando IPv6 primeiro no Windows. Troquei para `127.0.0.1` e passei a reutilizar uma conexão por rodada."
