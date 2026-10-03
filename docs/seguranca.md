# Segurança: triagem de e-mails da Alvorada

Registro técnico de cada risco encontrado, como foi tratado e como verificar.
Os itens seguem a ordem de prioridade: o que expõe mais dado com menos esforço do atacante vem primeiro.

| # | Item | Status |
|---|---|---|
| 1 | Painel exposto na rede | Camada de rede resolvida; login pendente |
| 2 | E-mails maliciosos (golpe, manipulação do LLM) | Pendente |
| 3 | LGPD (dados pessoais, retenção, acesso) | Pendente |
| 4 | Segredos e configuração | Pendente |

---

## 1. Painel exposto na rede

### Problema
O Streamlit, por padrão, escuta em `0.0.0.0` (todas as interfaces de rede, IPv4 e IPv6) e não tem autenticação. O painel mostra o conteúdo dos e-mails dos moradores (nome, apartamento, condomínio, reclamação) e tem botões que mudam o status dos chamados.

### Risco
- **Confidencialidade:** qualquer pessoa na mesma rede (Wi-Fi do escritório, de casa, de um café) acessa `http://<ip-da-máquina>:8501` e lê dados pessoais de moradores. Não exige senha nem conhecimento técnico.
- **Integridade:** a mesma pessoa pode clicar em "Concluir" e tirar um chamado urgente da fila.
- **LGPD:** acesso não autorizado a dados pessoais é incidente de segurança (art. 46 e 48).

Severidade: **alta** (dado pessoal + esforço zero do atacante).

### Evidência
```
netstat -ano | grep :8501
TCP    0.0.0.0:8501    LISTENING
TCP    [::]:8501       LISTENING
```
O log do Streamlit listava também "Network URL" (IP da rede local) e "External URL" (IP público).

### Solução: defesa em camadas
Uma única barreira não basta; cada camada cobre a falha da outra.

| Camada | Controle | Status |
|---|---|---|
| A. Rede | Painel escuta só em `127.0.0.1` (`.streamlit/config.toml`, `server.address`) | ✅ Feito |
| B. Identidade | Login: só usuários autorizados acessam | Pendente |
| C. Transporte | HTTPS via proxy reverso no deploy | Bloco de deploy |

**Camada A**, em `.streamlit/config.toml`:
- `server.address = "127.0.0.1"`: o sistema operacional recusa qualquer conexão que não venha da própria máquina, antes mesmo de chegar ao Streamlit
- `enableXsrfProtection` e `enableCORS` explícitos como `true`: já são padrão, mas ficam documentados para ninguém desligar sem perceber
- `gatherUsageStats = false`: o painel não envia telemetria de uso para terceiros

### Verificação
```
netstat -ano | grep :8501                          -> só 127.0.0.1:8501
curl http://127.0.0.1:8501/_stcore/health          -> ok
curl http://192.168.15.8:8501/_stcore/health       -> conexão recusada
```

### Limitações
- `127.0.0.1` resolve o ambiente local, mas as três atendentes precisam acessar de outros computadores. Em produção, o painel continua em `127.0.0.1` (ou numa rede privada do servidor) e o acesso externo passa por um **proxy reverso** (ex.: Caddy, Nginx, Cloudflare Access) que faz HTTPS e autenticação. O Streamlit nunca fica exposto diretamente.
- Sem a camada B, quem tiver acesso à máquina acessa o painel.

### Como explicar numa entrevista
> "O painel de triagem, que mostra dados pessoais de moradores, vinha com o padrão do Streamlit: escutando em todas as interfaces e sem autenticação. Primeiro confirmei a exposição com `netstat` e testando o acesso pelo IP da rede. Tratei em camadas: na rede, restringi o bind para `127.0.0.1`, e o sistema operacional passou a recusar conexões externas, o que verifiquei com o mesmo teste. Na identidade, adicionei login [ver camada B]. Para produção, o desenho é o painel nunca exposto diretamente: o acesso passa por um proxy reverso com HTTPS e autenticação. É defesa em profundidade: se uma camada falhar, a outra ainda protege."

**Perguntas que podem vir em seguida:**
- *Por que não só colocar uma senha?* Senha protege a identidade, mas o serviço continuaria exposto: qualquer falha no Streamlit ou senha fraca vira acesso direto. Restringir a rede reduz a superfície de ataque antes da autenticação.
- *Como você sabe que funcionou?* Testei o mesmo acesso antes e depois: pelo IP da rede, passou de aberto para recusado.
