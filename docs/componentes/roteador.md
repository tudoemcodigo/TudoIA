# Roteador (LiteLLM)

O roteador é o gateway do TudoIA. Todos os clientes falam com um único endereço, `http://127.0.0.1:4000`, usando a API
OpenAI (`/v1/chat/completions`) ou a API Anthropic (`/v1/messages`, usada pelo Claude Code). O gateway é o LiteLLM,
rodando em container. Por cima dele, um hook em Python escolhe, para cada pedido, o grupo de modelos que vai atendê-lo.

Este documento cobre os perfis de destino (`tudoia-local-estrito`, `tudoia-hibrido`), o modelo `tudoia-auto`, os grupos, o algoritmo de decisão, a resiliência (cooldown, quarentena,
novas tentativas), os logs e a configuração.

## Arquivos

| Arquivo | Papel |
|---|---|
| `runtime/litellm/roteador.py` | Hook do LiteLLM (`Roteador`, herdado de `CustomLogger`). Ponto de entrada: `proxy_handler_instance`. Trata pré-chamada, escolha de membro, streaming, sucesso, erro e logs. |
| `runtime/litellm/roteador_regras.py` | Funções puras: marcadores, pontuação, kNN, decisão, limites e quarentena lidos de arquivo, validação de `roteamento.yaml`. |
| `runtime/litellm/roteador_resiliente.py` | Para `/v1/messages`: segura o stream até estar completo, detecta laço e corte por `max_tokens`, refaz em outro membro. |
| `runtime/litellm/roteador_eventos.py` | Eventos da aba "Ao vivo" (lista branca de campos, com `perfil`, `categoria` e `destino`), gravador em thread separada, corte por idade e tamanho. |
| `config/roteamento.yaml` | Pesos, limiar, palavras, ordem dos membros por grupo. Relido quando muda. |
| `config/catalogo-modelos.yaml` | Provedores, modelos, tier (FREE ou PAID), papéis, limites. Fonte do `config.yaml` gerado. |
| `config/exemplos-roteamento.yaml` | Exemplos rotulados `local` e `nuvem` para o classificador semântico. |
| `config/precos-referencia.yaml` | Preços de referência para a estimativa de economia do painel. Não é cobrança. |
| `runtime/litellm/config.yaml` | Gerado pelo painel (`POST /api/roteador/gerar`). Não editar à mão. Ignorado pelo git. |
| `painel/tudoia_painel/gerador.py` | Monta o `config.yaml` a partir do catálogo, do `.env` e de `roteamento.yaml`. |
| `runtime/docker-compose.yml`, serviço `litellm` | Imagem, portas, volumes e variáveis do gateway. |

O serviço `litellm` do compose publica `127.0.0.1:4000:4000`, usa o Postgres `litellm-db` (`DATABASE_URL`) e monta
`config/` como somente leitura. Ele não lê o `.env` inteiro: recebe só `LITELLM_MASTER_KEY`, `DATABASE_URL`,
`OLLAMA_URL`, `TZ` e as chaves de provedor listadas em `environment`. Provedor novo no catálogo (`chave:` em
`config/catalogo-modelos.yaml`) precisa entrar nessa lista também; `tests/runtime/test_compose.py` falha se faltar.
Os quatro arquivos Python do hook são montados em `/app`. Os logs vão para `dados\logs` (montado em `/app/logs`).
Healthcheck: `GET /health/liveliness` a cada 30 s.

## Grupos e aliases

O cliente escolhe um nome de modelo. Esse nome é um grupo do LiteLLM. Os grupos fixos, do `painel/tudoia_painel/gerador.py`:

| Grupo | Membros | Uso |
|---|---|---|
| `tudoia-auto` | Virtual. O hook troca o nome pelo grupo escolhido em cada pedido. Se o hook não rodar, cai no modelo local `tudoia-chat`. | Padrão para clientes que querem roteamento automático |
| `tudoia-nuvem` | Membros FREE na ordem de `roteamento.yaml`. Sem membros: `tudoia-chat` local. | Pedidos leves ou de texto |
| `tudoia-codigo` | Membros FREE. Sem membros: `tudoia-agente` local. | Pedidos com ferramentas (`tools`) ou com marcador de código |
| `tudoia-codigo-reserva` | Membros FREE de reserva para `tudoia-codigo`. | Quando o grupo principal falha |
| `tudoia-visao` | Membros FREE com visão. Sem membros, o grupo não existe e o hook ignora a imagem. | Pedidos com imagem |
| `tudoia-max` | Membros PAID. Só entra por marcador `#max` ou pelo nome. Nunca é escolhido sozinho. | Pedidos caros e importantes |
| `tudoia-local` | `ollama_chat/tudoia-chat` (Ollama local) | Fallback local e pedidos com `#local` |
| `tudoia-local-estrito`, `tudoia-local-estrito-agente` | Só membros locais, sem nenhum fallback | Destinos do perfil `local-estrito` (ver [Perfis de destino](#perfis-de-destino)) |
| `tudoia-local-agente` | `ollama_chat/tudoia-agente` (Ollama local) | Fallback local para ferramentas |

Grupos extras podem ser criados pelo painel (aba Roteador). Eles entram no `ordem` de `roteamento.yaml` e viram grupos do LiteLLM.

Nota sobre o nome `tudoia-chat`: é o nome de um **modelo do Ollama** (criado a partir de `runtime/ollama/modelfiles/`),
não um grupo do LiteLLM. Os grupos são os da tabela. Um cliente que pede `tudoia-chat` ao gateway não recebe o roteamento
automático, porque esse nome não é um grupo.

Cada membro tem um nome do catálogo (ex.: `nim/glm-5.3`, `groq/gpt-oss-120b`, `or/free`). O nome aparece na
`ordem` de `roteamento.yaml`. Um membro só entra no `config.yaml` se o provedor estiver com todas as chaves preenchidas
e o modelo estiver `ativo` no catálogo.

## Perfis de destino

O cliente escolhe **onde** o pedido pode ir pelo nome do modelo (clientes como o Claude Code só escolhem o modelo) e,
se quiser, **que tipo de tarefa** é, por um marcador. Os perfis são configuração (`perfis` em `config/roteamento.yaml`),
não código: o hook (`roteador.py`, `_rotear_perfil`) e as funções puras (`roteador_regras.py`, `decidir_perfil`) só
leem o que está lá. O gerador (`painel/tudoia_painel/gerador.py`, `grupos_dos_perfis`) cria no `config.yaml` os grupos
que os perfis pedem.

### Nomes, por perfil

| Nome do modelo | Perfil | Para onde vai | Pago? |
|---|---|---|---|
| `tudoia-local-estrito` | `local-estrito` | Só Ollama local. Nunca a nuvem, nem por estouro de contexto, nem com o Ollama fora (falha com erro). | Nunca |
| `tudoia-hibrido` | `hibrido` | Local primeiro. Nuvem **gratuita** como apoio (ver abaixo). | Nunca |
| `tudoia-nuvem`, `tudoia-codigo`, `tudoia-visao` | nuvem | Grupos gratuitos de sempre, escolhidos pelo nome. Não passam pelos perfis. | Nunca |
| `tudoia-max` | max | Pago. Só pelo nome ou por `#max` em `tudoia-auto`. | Sim, por escolha explícita |
| `tudoia-auto` | (automático) | Decide por pontuação, como sempre. Marcadores `#local`, `#nuvem`, `#max` inalterados. | Só com `#max` |

Os perfis `nuvem` e `max` já existiam como grupos e continuam assim: o nome do grupo é o perfil. Os dois perfis novos
são modelos virtuais que o hook resolve para um grupo.

### Categorias

A categoria diz que tipo de tarefa é. Os nomes são os papéis do catálogo: `chat`, `codigo`, `agente`, `raciocinio`,
`rapido`, `visao`. Para cada perfil, `categorias` (e `nuvem_categorias`, no híbrido) mapeia categoria para grupo. Sem
marcador, o hook infere nesta ordem: `tools` no pedido = `agente`; imagem na última mensagem = `visao`; bloco de código,
stack trace ou diff = `codigo`; o resto = `chat`.

Marcador de categoria: `#chat`, `#codigo`, `#agente`, `#raciocinio`, `#rapido`, `#visao`, na última mensagem do usuário, com
espaço ou início antes do `#`, sem diferenciar maiúsculas. Vale só nos perfis novos (em `tudoia-auto` o `#codigo` é texto
comum). Todos os marcadores de categoria saem do texto enviado ao modelo. Com marcadores diferentes no mesmo pedido vale o
primeiro, e o motivo `categorias em conflito` aparece no registro.

Padrão atual de `config/roteamento.yaml`:

| Categoria | `local-estrito` | `hibrido`, local | `hibrido`, apoio da nuvem |
|---|---|---|---|
| `chat`, `rapido`, `raciocinio` | `tudoia-local-estrito` | `tudoia-local` | `tudoia-nuvem` |
| `codigo`, `agente` | `tudoia-local-estrito-agente` | `tudoia-local-agente` | `tudoia-codigo` |
| `visao` | sem destino: erro 400 | `tudoia-visao` (nuvem gratuita, não há visão local) | `tudoia-visao` |

`raciocinio` e `rapido` hoje caem no mesmo grupo de `chat`: o catálogo tem esses papéis nos modelos, mas ainda não há
grupo próprio. Para separar, crie o grupo no painel e aponte a categoria para ele no YAML.

### Como escolher no cliente

- **Claude Code / Open WebUI / n8n**: escolha o modelo `tudoia-local-estrito` ou `tudoia-hibrido`.
- **Marcador na mensagem** (qualquer cliente): `#local` ou `#nuvem` (conforme o perfil aceita) e/ou uma categoria, por
  exemplo `#local #codigo refatore isto`.
- Quando o dado não pode sair da máquina, **o nome do modelo é a garantia**; o marcador é conveniência.

### `local-estrito`: o que garante

1. Os grupos `tudoia-local-estrito` e `tudoia-local-estrito-agente` só têm membros locais (o gerador descarta membro de
   nuvem posto na `ordem` desses grupos) e **não aparecem** em `fallbacks`, `context_window_fallbacks` nem
   `content_policy_fallbacks`. Teste: `tests/runtime/test_perfis.py::test_gerador_cria_grupos_locais_sem_saida`.
2. O hook marca o pedido com `disable_fallbacks: true`, que desliga todo fallback do router para aquele pedido
   ([doc do LiteLLM](https://docs.litellm.ai/docs/proxy/reliability)).
3. O contexto local é limitado a 30000 tokens (`max_input_tokens` + `enable_pre_call_checks`). Um pedido maior não
   encontra membro e falha, em vez de ir à nuvem.
4. A cada pedido o hook confere no `config.yaml` gerado que o grupo é só local, sem pago e sem fallback (`info_grupos`).
   Se algo contradisser isso, responde erro 500 e não roteia.
5. Ollama fora (`GET /api/version`, resultado de 10 s): erro 503 com a mensagem "Nada foi enviado". GPU ocupada não desvia.
6. `#nuvem` e `#max` **não têm efeito** e ficam no texto (o perfil só aceita `#local`). Sem destino para a categoria
   (por exemplo `visao`): erro 400.
7. `config.yaml` ilegível ou grupo ausente: erro 503.

Se o `roteamento.yaml` estiver inválido quando o hook sobe, o hook não conhece os perfis e não altera o pedido. Mesmo assim
o pedido a `tudoia-local-estrito` cai em um grupo local sem fallback: a segurança não depende do hook ter lido o YAML
(`test_hook_roteamento_invalido_no_inicio_nao_abre_caminho_para_nuvem`).

### `hibrido`: o que faz

Começa pelo grupo local da categoria. Troca para o grupo gratuito de `nuvem_categorias` quando, nesta ordem: o Ollama está
fora (`ollama fora`); há job de vídeo na GPU (`gpu ocupada`); o pedido estimado (4 caracteres por token, mais as
definições de `tools`) passa do `max_input_tokens` do grupo local (`excede contexto local`). `#nuvem` vai direto à nuvem.
`#local` fica no grupo local, **sem** desvio do hook e com `disable_fallbacks`: nem o estouro de contexto leva `#local`
à nuvem (diferente de `tudoia-auto`, onde o fallback do router ainda vale). Com `#local` e `#nuvem` no mesmo pedido, vale
`#local`. `#max` não é aceito: pago só pelo nome `tudoia-max`.

Sem provedor de nuvem ativo: `#nuvem` e o desvio por Ollama fora ou contexto grande dão erro 503. GPU ocupada segue no local.
Categoria `visao` sem o grupo `tudoia-visao` degrada para `chat`, com o motivo no registro. O tipo do destino
(`local`, `nuvem`, `pago`) vem do `model_info.plano` dos membros no `config.yaml`, não do nome: `tudoia-nuvem` sem
provedor ativo é, no gerador, um grupo local, e o perfil o trata como local.

### Onde ver o destino real

- **Aba "Ao vivo" e `dados\logs\eventos.jsonl`**: o evento `inicio` traz `perfil`, `categoria`, `destino`, `grupo` e `motivos`;
  o evento `modelo` (um por tentativa) traz `provedor` e `membro` do modelo que atendeu de fato (`local` = Ollama).
  Recusas viram evento `erro` com a mensagem do perfil. `roteador.jsonl` tem os mesmos campos, uma linha por pedido.
- **Cabeçalhos de resposta** `x-tudoia-perfil`, `x-tudoia-categoria`, `x-tudoia-destino`, `x-tudoia-grupo`: o destino
  *decidido*. O LiteLLM também manda `x-litellm-model-group`. O cabeçalho usa o gancho
  `async_post_call_response_headers_hook` da documentação do LiteLLM; **não foi exercitado numa instância real** (só nos
  testes, com um LiteLLM de mentira). Se a versão em uso não chamar o gancho, o log continua valendo.

### Limites e o que NÃO é fronteira de segurança

- **Não é controle de acesso.** O perfil é escolhido pelo próprio cliente. Qualquer cliente com a chave do gateway pode
  pedir `tudoia-nuvem`, `tudoia-max` ou `tudoia-auto`. O perfil `local-estrito` impede o *roteador* de enviar à nuvem
  quem o pediu; não impede um cliente de pedir outro modelo. Para restringir um cliente, veja "Chaves virtuais" abaixo.
- Os marcadores vêm do texto do usuário. Texto colado que contenha `#nuvem` não muda o destino no `local-estrito` (ele
  ignora), mas muda no `hibrido` e no `tudoia-auto`. Use `local-estrito` quando o conteúdo é de terceiros.
- A estimativa de tokens do híbrido é grosseira. Se subestimar, o pedido vai ao grupo local e o router o recusa pelo contexto
  (erro, não vazamento; no `hibrido` sem `#local` o fallback do router ainda pode levá-lo à nuvem para `tudoia-local`).
- `disable_fallbacks`, as saídas de contexto e a recusa por `max_input_tokens` seguem a documentação do LiteLLM, mas **não
  foram exercitados contra um LiteLLM em execução** nesta entrega (regra do projeto: não reiniciar o gateway). Os testes
  cobrem o `config.yaml` gerado, as decisões e o hook com LiteLLM simulado.
- O Ollama é consultado por `GET /api/version`. Um Ollama que responde mas não tem o modelo carregado ou instalado falha
  na chamada (erro do Ollama), sem ir à nuvem no `local-estrito`.
- Dado de **GPU** e de limites (`gpu.json`, `limites.json`) segue sem escritor no repositório (ver [Quarentena](#quarentena-e-falhas)).
- Vale para o painel: a aba Roteador ainda não edita `perfis`; mexa no YAML. Uma edição do painel em outras chaves preserva
  o bloco `perfis` (lê e regrava o arquivo inteiro), mas perde os comentários.

### Chaves virtuais do LiteLLM: restringir grupos por cliente

Confirmado na documentação do LiteLLM ([model_access](https://docs.litellm.ai/docs/proxy/model_access)): ao gerar uma chave
com `POST /key/generate` e `"models": ["tudoia-local-estrito", "tudoia-local-estrito-agente"]`, a chave só enxerga e só
chama esses modelos; os demais são bloqueados. Isso seria o controle de acesso que falta, por cliente (por exemplo, uma
chave só local para o Claude Code de um projeto confidencial).

**Verificado em instância real (2026-11-01)**: uma chave gerada com `models: ["tudoia-local-estrito",
"tudoia-local-estrito-agente"]` e `duration: "90d"` (alias `squadti-local-estrito`) lista só esses dois em `/v1/models`, e
um pedido a outro modelo (`tudoia-local-agente`) volta `403 key_model_access_denied` antes de qualquer roteamento. Com a
chave nova, o hook respondeu 503 "grupo(s) não existem no config.yaml gerado" enquanto os perfis não estavam ativos: a
chave passa a autenticação e o hook falha fechado.

**Ainda não verificado**: o pedido completo depois de gerar o `config.yaml` e reiniciar o LiteLLM, ou seja, que a
checagem de acesso olha o nome pedido (`tudoia-local-estrito`) e aceita o grupo para onde o hook o reescreve
(`tudoia-local-estrito-agente`, por isso está na lista). A chave fica na variável de ambiente `TUDOIA_API_KEY` do
usuário (a criação não está no painel nem num script do repositório). A chave mestra continua sendo irrestrita; a
chave vence em 2027-01-31 e deve ser regerada antes.

### Roteamento por tags do LiteLLM

Não usado. O [tag routing](https://docs.litellm.ai/docs/proxy/tag_routing) escolhe deployment por `tags` enviadas pelo
cliente no corpo ou em cabeçalho; o Claude Code não manda tags. O nome do modelo cobre o mesmo caso sem depender do cliente.

## Como o `tudoia-auto` decide

O hook (`roteador_regras.decidir`) roda antes de cada chamada a `tudoia-auto`. A ordem é esta:

1. **Marcador explícito** na última mensagem do usuário: `#local`, `#nuvem` ou `#max` (sem diferenciar maiúsculas,
   e só com espaço ou início antes do `#`). O marcador é removido do texto antes do envio. `#local` vai direto para
   `tudoia-local` e nunca é desviado pelo hook (nem por GPU ocupada, nem por Ollama fora). `#nuvem` vai para
   `tudoia-nuvem`. `#max` vai para `tudoia-max`, se o grupo existir; senão, a decisão segue as regras normais.
2. **Ferramentas** (`tools`): vai para `tudoia-codigo`, mesmo com imagem no pedido. Nesse caso não há pontuação. O
   motivo `imagem com ferramentas` aparece no registro. Os membros de visão podem não aceitar ferramentas; para ver
   a imagem numa sessão com ferramentas, use `#max`.
3. **Imagem** no pedido, sem ferramentas: vai para `tudoia-visao`, se o grupo existir.
4. **Pontuação** (demais casos). Pesos de `config/roteamento.yaml`:

   | Critério | Peso | Condição |
   |---|---|---|
   | `longo` | +3 | Última mensagem com mais de 2000 caracteres, ou pedido com mais de 12000 tokens estimados |
   | `codigo` | +2 | Bloco de código detectado na última mensagem |
   | `palavras_dificeis` | +2 por palavra, até 2 | Termos da lista `palavras_dificeis` (ex.: "arquitetura", "depure", "compare") |
   | `muitos_turnos` | +1 | Mais de 8 mensagens do usuário na conversa |
   | `trivial` | −3 | Só se não houver palavra difícil nem código, e um termo de `palavras_triviais` aparecer como palavra inteira |
   | `semantico_nuvem` | +3 | kNN: o rótulo mais votado entre os 7 vizinhos é `nuvem` com margem de pelo menos 2 |
   | `semantico_local` | −2 | Idem, com rótulo `local` |

   O kNN só entra se o embedding da última mensagem estiver pronto a tempo (ver abaixo). Sem ele, a decisão usa só os
   critérios da heurística, e o motivo `semantico_indisponivel` aparece no registro.

   Pontuação `>= limiar` (3 em `roteamento.yaml`) vai para `tudoia-nuvem`. Abaixo disso, vai para `tudoia-local`.

5. **GPU ocupada**: se `logs\gpu.json` indicar um job de vídeo com lock ativo, `tudoia-local` vira `tudoia-nuvem`
   (salvo `#local`). Veja o aviso sobre esse arquivo em [Quarentena](#quarentena-e-falhas).
6. **Provedores esgotados**: se todos os membros de `tudoia-nuvem` estão esgotados, o pedido vai para `tudoia-local`.
   O mesmo vale para `tudoia-codigo` e `tudoia-local-agente`.
7. **Ollama fora** (`roteador.py`, `_ollama_no_ar`): se a decisão deu `tudoia-local` ou `tudoia-local-agente` sem
   `#local`, o hook confere
   `GET /api/version` no Ollama. Fora do ar, `tudoia-local` vira `tudoia-nuvem` e `tudoia-local-agente` vira
   `tudoia-codigo`, com o motivo `ollama fora`. `#local` explícito nunca é desviado. O resultado da checagem vale 10 s,
   com timeout de 0,3 s. Erro que não diz nada sobre o Ollama mantém o destino local.

Embedding do kNN: o hook chama o Ollama (`/api/embed`) com o modelo `bge-m3`, em CPU (`num_gpu: 0`). O tempo máximo de
espera é de 1,5 s (`LIMITE_EMBED_S`). Se passar disso, o pedido segue sem o semântico. Os vetores dos exemplos ficam em
cache, em `dados\logs\exemplos-vetores.json`, indexados por SHA-1 do texto. Quando um pedido chega sem o aquecimento
feito, o hook dispara um aquecimento do `bge-m3` em segundo plano.

Exemplos de decisão (a partir do código e de `roteamento.yaml`):

| Pedido | Resultado |
|---|---|
| `oi, tudo bem?` | Trivial (−3) e sem palavra difícil. Tende a ir para `tudoia-local`, salvo se o kNN somar `semantico_nuvem`. |
| `Compare duas arquiteturas de fila e explique o trade-off` | `palavras_dificeis` (+4, duas palavras) e possivelmente `longo` e `semantico_nuvem`. Vai para `tudoia-nuvem`. |
| `#nuvem oi` | Marcador. Vai para `tudoia-nuvem`, e o texto enviado é `oi`. |
| Pedido com `tools` | `tudoia-codigo`, mesmo com imagem. |
| `previsão do tempo` | `revis` não casa: as palavras difíceis casam só no início de palavra. |

## Quarentena e falhas

"Quarentena" tem três mecanismos (1 a 3). Só o primeiro está completo no repositório. O item 4 é o fallback por
contexto, que também troca o destino de um pedido.

### 1. Cooldown do próprio LiteLLM (completo)

Configurado pelo gerador em `router_settings` (`painel/tudoia_painel/gerador.py`):

| Parâmetro | Valor | Efeito |
|---|---|---|
| `routing_strategy` | `latency-based-routing` | Escolhe o membro mais rápido. Membro sem histórico conta como latência zero, então todos são testados. |
| `allowed_fails` | 1 | Falhas por minuto antes de esfriar o membro |
| `allowed_fails_policy` | Timeout 3, RateLimit 1, InternalServerError 2, BadRequest 5, Authentication 0 | Limite por tipo de erro. Autenticação esfria na primeira falha. |
| `cooldown_time` | 60 s | Quanto tempo o membro fica fora depois de esfriar |
| `num_retries` | 1 | Novas tentativas no próprio router |
| `enable_pre_call_checks` | `true` | Pula membro cujo `max_input_tokens` não cabe no pedido |

Os valores são comentados no próprio `gerador.py` com a medição que motivou cada um.

### 2. Limites e membros lidos de arquivo (leitura completa, escrita não encontrada)

O hook lê dois arquivos em `dados\logs\`:

- `limites.json`: lista `esgotados` (nomes de membros) e `membros` por grupo. Válido por 120 s depois da última
  atualização (`limites_validos`).
- `quarentena.json`: cada entrada de `esgotados` tem sua própria validade (`ate`). `membros` vale por 3600 s
  (`quarentena_valida`, `quarentena_membros`).

Esses membros são descartados da escolha do grupo e do fallback. Os nomes `esgotados` e `membros` aparecem na
decisão.

**Não encontrei nenhum código que grave esses dois arquivos neste repositório.** O painel calcula o consumo, mas não
escreve `limites.json`. O próprio comentário de `roteador_regras.py` diz que "o painel grava em logs/limites.json". Esse
trecho não se confirma no código versionado. Se algum processo externo grava esses arquivos, não está neste repositório.
A confirmar.

O mesmo vale para `logs\gpu.json`, lido pelo hook para detectar job de vídeo, sem escritor no repositório.

### 3. Refazer um pedido quando o stream falha (`/v1/messages`)

Esse é o caminho que trata erros no meio da resposta. Ele é implementado em `roteador_resiliente.py`:

- O hook segura todos os bytes da resposta até chegar `message_stop`. Se o stream terminar sem isso, com `event: error`,
  ou cortado por `max_tokens` sem ter sido o cliente que pediu pouco, a tentativa é descartada e o pedido é refeito.
  Os eventos são lidos só das linhas `event:` do SSE (`_eventos`). O texto do modelo vai escapado dentro de
  `data: {...}`, então uma resposta que fala de "código de servidor SSE" não parece mais erro.
- A nova tentativa vai ao próximo membro do grupo (`plano`), até `MAX_TENTATIVAS = 3`, depois aos fallbacks do grupo.
  Os campos do pedido são copiados de uma lista de permitidos (`CAMPOS_DO_CLIENTE`). Objetos internos do LiteLLM não
  são reenviados.
- Enquanto segura a resposta, o hook manda `event: ping` a cada 10 s, para a conexão não parecer ociosa.
- Se todas as tentativas falharem, o cliente recebe `event: error` com a mensagem `TudoIA: todos os modelos falharam nesta
  resposta`.
- Laço: `DetectorDeLaco` procura repetição exata de um trecho gerado (texto, pensamento ou JSON de ferramenta), com
  período de até 750 caracteres e pelo menos 4 cópias seguidas, nos últimos 3000 caracteres. Quando detecta, corta o
  stream e refaz.
- Limite de saída: `stop_reason: max_tokens` só é tratado como falha quando o orçamento do pedido é grande (8192 ou
  mais) ou quando a saída ficou abaixo de 90% do pedido.

Para pedidos sem streaming (`/v1/chat/completions` sem `stream`), a nova tentativa segue o `router_settings` acima.

### 4. Fallback por contexto (`context_window_fallbacks`)

O gerador grava `context_window_fallbacks: [{"tudoia-local": ["tudoia-nuvem"]}]` em `router_settings`
(`painel/tudoia_painel/gerador.py`). Um pedido que não cabe no contexto do modelo local vai para `tudoia-nuvem`, inclusive
um pedido com `#local` em `tudoia-auto` ou direto em `tudoia-local`. O hook não roda nessa troca. É um risco de
privacidade em aberto: ver o risco 16 em [seguranca.md](../seguranca.md#riscos-residuais). **Quem não pode correr esse
risco usa `tudoia-local-estrito`**, que não tem essa saída (ver [Perfis de destino](#perfis-de-destino)).

## Imagens e `cache_control` no pedido

Depois da decisão, o hook ajusta o corpo para o destino (`roteador.py`, perto de `GRUPOS_COM_VISAO`):

- Destino com visão (`tudoia-visao`, `tudoia-max`): as imagens seguem como vieram.
- Destino sem visão e pedido com `tools`: todas as imagens viram texto (`[Imagem anterior no histórico omitida]`),
  inclusive as da última mensagem e as de `tool_result`.
- Destino sem visão e sem `tools`: se a última mensagem do usuário não tem imagem, as imagens do histórico viram texto.
  Se tem, o pedido segue como veio.
- `cache_control` só fica para deployments pagos pedidos pelo nome e sem fallback (`destinos_com_cache`). Nos outros, é
  removido do `system`, das mensagens e das ferramentas (o Gemini grátis responde 429 com cache).

## Logs e eventos

Tudo fica em `dados\logs\` (montado em `/app/logs`):

| Arquivo | Conteúdo | Quem grava | Retenção |
|---|---|---|---|
| `eventos.jsonl` | Eventos da aba "Ao vivo": `inicio`, `modelo` (cada tentativa), `progresso`, `fim`, `erro`, `vazia`, `cancelado` | Hook, por thread separada | 24 h e 20 MB (`Gravador`, `cortar_arquivo`) |
| `roteador.jsonl` | Uma linha por decisão de `tudoia-auto`: grupo, pontos, motivos, marcador, modelo, provedor, membro, tempo, sucesso e erro | Hook, pela thread do `Gravador` | Vira `roteador.jsonl.1` ao passar de 5 MB (`girar_se_grande`; sobrescreve o `.1` anterior) |
| `correcoes.jsonl` | Rótulo (`local` ou `nuvem`), SHA-1 e tamanho do pedido quando o usuário usa `#local` ou `#nuvem`. O texto não é gravado | Hook, pela thread do `Gravador` | Vira `correcoes.jsonl.1` ao passar de 5 MB |
| `ratelimit.json` | Últimos cabeçalhos `x-ratelimit-*` de cada provedor | Hook | Atualizado por provedor |
| `exemplos-vetores.json` | Cache SHA-1 do texto → vetor (bge-m3) | Hook | Sem corte |

Metadados, não texto: `eventos.jsonl` só guarda os campos da lista branca `CAMPOS` (`roteador_eventos.py`). Nenhum deles
é texto de pedido ou de resposta. O erro é registrado como classe da exceção e código HTTP (`resumir_erro`), sem a
mensagem, porque o provedor às vezes repete trechos do pedido.

`auditoria.jsonl`, na mesma pasta, é do painel (ver [seguranca.md](../seguranca.md#auditoria)).

`correcoes.jsonl` guarda só rótulo, SHA-1 e tamanho do pedido (não o texto). Nenhum código deste repositório lê esse arquivo,
e não há código que gere `config/exemplos-aprendidos.yaml`, que `carregar_exemplos` aceita: o aprendizado a partir de
correções ainda não existe. Se for construído, precisa de decisão sobre guardar texto (risco 12 em
[seguranca.md](../seguranca.md#riscos-residuais)).

A aba "Ao vivo" e a telemetria do painel leem `eventos.jsonl` e `/spend/logs` do LiteLLM
(`painel/tudoia_painel/rotas/telemetria.py`, rota `/api/telemetria`). A telemetria pede ao LiteLLM só as últimas 24 h.

## Configuração

### `config/roteamento.yaml`

- `limiar` (3): pontuação mínima para `tudoia-nuvem`.
- `pesos`: os pesos da tabela de decisão.
- `limites_texto`: `caracteres` (2000), `tokens_total` (12000), `turnos` (8).
- `palavras_dificeis` e `palavras_triviais`: listas em minúsculas, comparadas sem acento. As difíceis casam no início de
  palavra (`(?<!\w)`): o termo funciona como prefixo (`revis` casa "revisão"), mas não no meio de palavra ("previsão"
  não casa). As triviais casam só como palavra inteira. Na lista atual, o antigo `prove` deu lugar a `provar` e `prove que`.
- `ordem`: por grupo, a lista de membros (nome do catálogo), na ordem de tentativa.
- `perfis`: perfis de destino (ver [Perfis de destino](#perfis-de-destino)). Campo opcional; sem ele nada muda.

O hook relê o arquivo quando o `mtime` muda. Se o novo arquivo for inválido (`validar_regras`), o hook mantém a última
versão válida e registra no log. Pesos e palavras entram sem reiniciar. A `ordem` dos membros só vale depois de regerar
o `config.yaml` (`POST /api/roteador/gerar`) e reiniciar o LiteLLM, porque o `model_list` é lido na inicialização.

### `config/catalogo-modelos.yaml`

Por provedor: `nome`, `tier` (`FREE` ou `PAID`), `chave` e `chaves_extras`, `api_base`, `url_modelos`, `limites`
(`rpm`, `rpd`, `tpm`, `tpd`, `usd_dia`, `reset`), `fonte_limites`, `modelos`. Por modelo: `nome` (o nome do membro),
`id` (identificador no LiteLLM, ex.: `groq/...`), `papeis` (chat, codigo, agente, rapido, visao, raciocinio), `contexto`
e `ativo` (padrão `true`). Um modelo com `ativo: false` fica no catálogo e não entra no `config.yaml`.

### `config/exemplos-roteamento.yaml`

Listas `local` e `nuvem` com frases de exemplo. O classificador compara a mensagem com esses exemplos (kNN, `k = 7`).
Não repita ali as palavras de `palavras_dificeis`, porque o semântico existe para o que a lista não pega.

### `config/precos-referencia.yaml`

Preços de referência, em dólares por milhão de tokens, usados só para a "economia estimada" da análise do painel. O
arquivo declara a própria data de origem. Confira antes de usar.

### Editar grupos pelo painel

A aba **Roteador** do painel altera `roteamento.yaml` (membros de cada grupo, criação e exclusão de grupo, auto-vínculo
por papéis). Depois, gere o `config.yaml` (botão ou `POST /api/roteador/gerar`) e reinicie o LiteLLM. O endpoint de
geração só grava o arquivo e não reinicia nada.

### Trocar um provedor

1. Preencha a chave em `.env` (ou na aba Segredos).
2. Confira que o modelo está em `catalogo-modelos.yaml` com `ativo: true`.
3. Coloque o membro na `ordem` do grupo em `roteamento.yaml`.
4. Gere o `config.yaml` e reinicie o `litellm`.

Um provedor sem todas as chaves preenchidas fica fora do `config.yaml`, sem erro.

## Operação

- Subir ou reiniciar o gateway: `docker compose -p tudoia -f runtime\docker-compose.yml --env-file .env restart litellm`,
  ou o `.\scripts\tudoia.ps1 up`, ou a aba Serviços do painel.
- Checar o gateway: `curl.exe -s http://127.0.0.1:4000/v1/models -H "Authorization: Bearer <LITELLM_MASTER_KEY>"`. Use a
  chave mestra do `.env`, sem colá-la em lugar nenhum.
- Ver as decisões: `dados\logs\roteador.jsonl`, uma linha por pedido.
- Se o hook não carregar, o log do container mostra `[roteador] não li ...` e `#max`, visão e nova tentativa ficam
  desligados (`_ler_config`).
