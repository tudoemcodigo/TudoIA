# Automação com n8n

O n8n roda como container no stack Docker (serviço `n8n` em `runtime/docker-compose.yml`). Os quatro workflows versionados ficam em `automacao/n8n/`. Eles resumem documentos, pesquisam na web, montam um digest de notícias e ingerem um documento enviado por formulário.

## Onde roda e o que ele enxerga

- Interface e formulários em `http://localhost:5678`, publicada só em `127.0.0.1` (`127.0.0.1:5678:5678`).
- Volume `dados/documentos` do host montado em `/data/docs` dentro do container. É a mesma pasta que o Cérebro lê (em `/docs`, somente leitura).
- `N8N_RESTRICT_FILE_ACCESS_TO=/data/docs`: os nós de leitura e escrita de arquivo só alcançam essa pasta. Qualquer caminho fora dela é recusado pelo n8n.
- Fuso: `GENERIC_TIMEZONE` e `TZ` vêm de `TZ` do `.env`. Os horários dos gatilhos de agenda seguem esse fuso.
- Alcança os outros serviços pelo nome do container na rede do compose: `http://cerebro:8765` e, pelas credenciais, o LiteLLM e o SearXNG. O Keycloak é alcançado por `http://host.docker.internal:8180`.
- `N8N_ENCRYPTION_KEY` vem do `.env` e cifra as credenciais salvas. Restaurar o volume `n8n` exige a mesma chave (ver `scripts/backup/restaurar.md`).
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`: nenhum nó Code ou expressão (`$env`) lê as variáveis do container. Nenhum fluxo versionado usa `$env`. Os segredos ficam no cofre de credenciais do n8n.
- Healthcheck: `GET /healthz` a cada 30 s.
- Versão: a imagem é `n8n:latest` fixada por digest no compose. O container em execução respondeu `n8n --version` = 2.44.6. O número da versão não está escrito em nenhum arquivo do repositório.

Estrutura de pastas usada pelos workflows:

```
dados/documentos/
  entrada/   documentos de origem (lidos e gravados pelos workflows)
  resumos/   resumos em Markdown (gravados pelos workflows)
```

## Importar os workflows

1. Suba o stack (`scripts\tudoia.ps1 up`) e abra `http://localhost:5678`. Na primeira execução, o n8n pede para criar o usuário dono da instância.
2. Grave a credencial do Cérebro (passo único, com o container `n8n` no ar e o Keycloak já provisionado):

   ```powershell
   .\scripts\tudoia.ps1 n8n-credencial
   ```

   O comando (`scripts/n8n/credencial_cerebro.py`) lê `TUDOIA_MCP_CLIENT_ID` e `TUDOIA_MCP_CLIENT_SECRET` do `.env` e grava no n8n a credencial OAuth2 `TudoIA Cérebro (client_credentials)`, id `tudoiaCerebroOAuth`, com o token URL `http://host.docker.internal:8180/realms/<realm>/protocol/openid-connect/token`. O segredo passa pelo stdin do `docker exec`, nunca por argumento. O arquivo temporário dentro do container é criado com `umask 077` e apagado em seguida. Rodar de novo sobrescreve a mesma credencial. Saída: `0` ok, `1` segredo ausente no `.env` (rode o provisionamento do Keycloak), `2` falha no Docker ou no n8n.
3. Crie as outras duas credenciais com os nomes exatos abaixo. Os workflows referenciam as credenciais pelo nome.

   | Nome da credencial | Tipo no n8n | Usado por | Observação |
   |---|---|---|---|
   | `TudoIA LiteLLM` | OpenAI API | os quatro workflows (modelo de chat) | aponta para o LiteLLM na rede do compose (endereço e chave ficam na credencial; a confirmar qual chave do LiteLLM ela usa). Não cole o valor da chave em arquivos do repositório. |
   | `SearXNG local` | SearXNG API | `02-agente-pesquisador` | aponta para o SearXNG (`http://searxng:8080` na rede do compose). A URL fica na credencial, não no JSON. |

   O JSON não traz segredos. Os workflows trazem apenas o nome e, em dois casos, o ID interno da credencial (`ingerir-documento.json`: `TudoIA LiteLLM` e `tudoiaCerebroOAuth`), que não é segredo.

4. Importe cada arquivo: menu **Workflows**, **Import from file** (ou colar o conteúdo do JSON). São quatro arquivos:
   - `automacao/n8n/01-resumir-documentos.json`
   - `automacao/n8n/02-agente-pesquisador.json`
   - `automacao/n8n/03-digest-noticias.json`
   - `automacao/n8n/ingerir-documento.json`
5. Os JSON não têm o campo `active`. Os workflows entram **desativados**. Ative os de agenda (01 e 03) e o de formulário (ingerir) quando quiser que eles respondam aos gatilhos. O de chat (02) fica disponível na URL do próprio gatilho de chat.

Quem já tinha importado o `ingerir-documento.json` antigo (com o nó que lia `$env` para pedir o token) precisa rodar o `n8n-credencial` e reimportar o fluxo. Com `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`, o fluxo antigo não consegue mais ler o segredo.

A compatibilidade dos workflows com a versão do n8n não foi testada nesta documentação: a importação foi conferida só pela leitura do JSON. `tests/n8n/test_fluxos_n8n.py` confere que nenhum fluxo lê `$env` e que o formulário de ingestão exige login. Confirme na primeira importação.

## Workflows

### 1. TudoIA - Resumir documentos (`01-resumir-documentos.json`)

- **Gatilhos:** manual ("Executar agora") e agenda diária às 7h.
- **Entrada:** `/data/docs/entrada/*.{txt,md}`. Lê cada arquivo e extrai o texto.
- **Processo:** agente com o modelo `tudoia-auto` (via LiteLLM). Pede resumo de até 8 tópicos em português e uma linha final "Ações:" com tarefas, se houver.
- **Saída:** `/data/docs/resumos/<nome original>.resumo.md`.
- **Chamadas externas:** nenhuma direta. Tudo passa pelo LiteLLM.
- **Credenciais:** `TudoIA LiteLLM`.
- **Observação:** o texto do arquivo entra inteiro no prompt, sem limite de tamanho (ao contrário do ingerir, que corta em 30 000 caracteres). Um arquivo grande pode estourar o contexto do modelo.

### 2. TudoIA - Agente pesquisador (`02-agente-pesquisador.json`)

- **Gatilho:** Chat (gatilho de chat do n8n). A conversa é aberta pela URL do próprio gatilho.
- **Processo:** agente com o modelo `tudoia-auto`, instruído a pesquisar fatos recentes, citar as fontes e usar a calculadora para contas. Responde em português.
- **Ferramentas:** busca no SearXNG (5 resultados, idioma `pt-BR`) e calculadora.
- **Chamadas internas:** LiteLLM e SearXNG.
- **Credenciais:** `TudoIA LiteLLM` e `SearXNG local`.
- **Observação:** o gatilho de chat não tem autenticação no JSON. Como a porta só escuta em `127.0.0.1`, quem alcança a conversa é quem tem acesso à máquina. Se o n8n for exposto a outra rede, proteja esse gatilho antes.

### 3. TudoIA - Digest de notícias (`03-digest-noticias.json`)

- **Gatilhos:** manual e agenda diária às 8h.
- **Fonte externa:** feed RSS `https://g1.globo.com/rss/g1/tecnologia/`. Pega os 10 primeiros itens e junta títulos e links.
- **Processo:** agente com o modelo `tudoia-auto` escreve um digest curto em português, agrupado por assunto, com o link de cada notícia.
- **Saída:** `/data/docs/resumos/digest-AAAA-MM-DD.md`.
- **Credenciais:** `TudoIA LiteLLM`.
- **Observação:** a URL do feed está escrita no nó. Trocar de fonte é editar esse nó.

### 4. TudoIA - Ingerir documento (`ingerir-documento.json`)

É o fluxo que liga o n8n ao Cérebro.

- **Gatilho:** formulário do n8n (`formTrigger` versão 2.6), caminho `tudoia-ingerir-documento`, com autenticação "n8n User Auth" (`authentication: n8nUserAuth`): só quem está logado no n8n abre o formulário. Aceita um arquivo `.txt`, `.md` ou `.pdf`. O endereço segue o padrão do n8n: `http://localhost:5678/form/tudoia-ingerir-documento` (confirme na instância). O formulário devolve uma mensagem ao final.
- **Passos:**
  1. "Preparar arquivo": limpa o nome (remove caminho e caracteres estranhos) e valida a extensão no servidor. O atributo `accept` do formulário só ajuda o navegador.
  2. Se a extensão não é válida: mensagem de formato e fim.
  3. Se já existe `entrada/<nome>` ou `resumos/<base>.md`: acrescenta `-AAAAMMDD-HHMMSS` ao nome. O workflow nunca sobrescreve.
  4. Grava o original em `/data/docs/entrada`.
  5. PDF: extrai o texto do PDF. Demais: lê como texto.
  6. Sem texto (PDF escaneado, vazio ou corrompido): grava o original, avisa e não gera resumo.
  7. Resume com o modelo `tudoia-auto`, em até 15 tópicos, com um título na primeira linha. O texto é limitado a 30 000 caracteres.
  8. Se o modelo falhar: avisa, mas o original fica salvo.
  9. Grava o resumo em `/data/docs/resumos/<base>.md`.
  10. `POST http://cerebro:8765/indexar` com timeout de 120 s, autenticado pela credencial OAuth2 `TudoIA Cérebro (client_credentials)` (o n8n pede o token ao Keycloak com o cliente `tudoia-mcp`). Resposta 200: indexação concluída. Resposta 409: já há indexação em andamento, e o arquivo entra na próxima rodada. Outra resposta: a mensagem final informa a falha e o resumo fica salvo. Se o Cérebro estiver fora do ar, o nó de erro leva ao aviso "Msg cérebro off", que promete indexação em até 10 minutos (o Cérebro reindexa a cada 600 s, em segundo plano). Não verifiquei na instância qual texto chega ao usuário nesse caso (a confirmar).
- **Chamadas internas:** LiteLLM (resumo), Keycloak (token) e `http://cerebro:8765/indexar` (indexação).
- **Credenciais:** `TudoIA LiteLLM` e `TudoIA Cérebro (client_credentials)`.

## Riscos a conhecer

- **Formulário com login do n8n** (antes: sem autenticação; corrigido). Só um usuário logado no n8n envia arquivos para `entrada/`. Quem tem conta no n8n continua podendo enviar documentos que o Cérebro indexa.
- **Entrada controla o prompt.** O conteúdo dos documentos vai para o modelo. Um documento pode conter instruções que o modelo siga. O agente de resumo não tem ferramentas, então o dano fica no texto do resumo, mas o resumo é gravado e indexado. Trate o resumo como dado não confiável.
- **Indexação autenticada** (antes: sem token; corrigido). O `POST /indexar` exige token com papel de operador ou admin.
- **Credencial do Cérebro no volume `n8n`.** O segredo do cliente `tudoia-mcp` fica cifrado no volume com a `N8N_ENCRYPTION_KEY`. Quem tem a chave e o volume (por exemplo, um backup `n8n.tar.gz` mais o `.env`) obtém o segredo.
- **Arquivo de entrada grande.** O workflow 01 não limita o tamanho do texto. O workflow de ingestão limita a 30 000 caracteres.
- **Pastas de trabalho.** Crie `dados\documentos\entrada` e `dados\documentos\resumos` antes da primeira execução. Não verifiquei se o n8n cria essas pastas sozinho nem se os nós de leitura falham quando a pasta está vazia (a confirmar na instância).

## Veja também

- [servicos-docker.md](servicos-docker.md): o serviço `n8n` e os demais containers.
- [cerebro.md](cerebro.md): o endpoint `/indexar`, a autenticação e a indexação em segundo plano.
- [keycloak.md](keycloak.md): o cliente `tudoia-mcp`.
- [../configuracao.md](../configuracao.md): variáveis do `.env`.
