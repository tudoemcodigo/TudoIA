# SquadTI

Squad de agentes (LangGraph) que leva uma demanda do briefing à entrega, seguindo a [Doutrina TEC](https://github.com/tudoemcodigo/Doutrina). O código vive em
[`runtime/squadti/`](../../runtime/squadti/) (README com o fluxo, os agentes e os limites) e a documentação de projeto em [`docs/squadti/`](../squadti/).
Este documento cobre como ela se encaixa no TudoIA: container, painel, chave, privacidade e scripts.

```
navegador ──► painel (/api/squadti/*, papéis, auditoria) ──► container squadti (127.0.0.1:8790, Bearer) ──► LiteLLM (rede do compose)
                                                                   │
                                                                   └─ volume squadti-dados: checkpoint, workspace/<tarefa>, caches NuGet e npm
```

## Por que um container isolado

A Squad compila e testa o código que o modelo escreveu: o MSBuild e o npm executam código dele. No host isso rodaria com o seu usuário. No container (perfil
`squadti` do compose) o raio de dano é pequeno: usuário sem root (uid 10001), sistema de arquivos somente leitura, `cap_drop: ALL`, `no-new-privileges`,
teto de CPU, memória e processos. A única escrita no disco da Squad é o volume `squadti-dados`.

> [!WARNING]
> **O `docker.sock` do host está montado** (decisão do dono, 2026-11-03) para os testes de integração (Testcontainers). Quem controla o socket controla o
> Docker do host: o código que o modelo gera e a Squad executa pode criar containers privilegiados, ler volumes de outros serviços (banco do LiteLLM, Keycloak)
> e virar root no host. O endurecimento acima não cobre esse caminho. Para voltar ao isolamento, remova do serviço `squadti` do compose a linha do `docker.sock`,
> o `group_add` e o `TESTCONTAINERS_HOST_OVERRIDE`. Uma alternativa mais segura (não implementada): um Docker próprio em container (`docker:dind`), que isola os
> containers de teste dos do TudoIA.

Os testes de integração (Testcontainers) rodam na Squad: os containers de teste sobem no Docker do host, como irmãos do container da Squad, e ela os alcança por
`host.docker.internal` (`TESTCONTAINERS_HOST_OVERRIDE`). A imagem é grande (~2 GB: .NET SDK 10 + Node 24 + Python 3.12).
Por isso o componente é **opcional** no instalador (desmarcado por padrão).

## Instalação e configuração

- **Instalador:** marque *SquadTI*. Ele coloca `squadti` em `COMPOSE_PROFILES`, gera `TUDOIA_SQUADTI_TOKEN` (`tudoia segredos`), constrói a imagem e cria a chave
  virtual do LiteLLM (`scripts/squadti/chave.py`), recriando o container para ele ler a chave.
- **Instalação existente:** inclua `squadti` em `COMPOSE_PROFILES`, rode `scripts\tudoia.ps1 segredos`, `scripts\tudoia.ps1 squadti-chave` e `scripts\iniciar.ps1 -ComSquadti`.

| Variável (`.env`) | Para que serve |
|---|---|
| `TUDOIA_SQUADTI_TOKEN` | Token da API (32+ caracteres). O painel e o container leem o mesmo valor; sem ele a API não sobe |
| `SQUADTI_API_KEY` | Chave virtual do LiteLLM **só da Squad** (alias e tag `squadti`, 90 dias): lista os perfis locais e a nuvem gratuita, nunca `tudoia-max` |
| `TUDOIA_NUGET_FEED_URL` | Feed NuGet **público** (`https://...`, sem credencial) das bibliotecas TEC.*; entra como fonte `tec-publico` |
| `TUDOIA_NUGET_USER`, `TUDOIA_NUGET_PAT` | Opcional: feed privado `tec-interno` (GitHub Packages exige PAT `read:packages`). Só por ambiente; o arquivo do NuGet guarda a referência, não o segredo |
| `SQUADTI_TEMPLATE_DIR` | Opcional: pasta do TemplateTEC (padrão `dados\squadti-template`), montada só leitura em `/template` para o `dotnet new tec-project` |
| `SQUADTI_DOUTRINA_SHA` | Opcional: versão da Doutrina embutida na imagem (padrão fixado no `Dockerfile`); trocar exige reconstruir |
| `SQUADTI_MEMORIA`, `SQUADTI_CPUS`, `SQUADTI_TIMEOUT_S`, `SQUADTI_CONTEXTO_TOKENS` | Opcionais: tetos do container, prazo por chamada ao modelo e janela de contexto |
| `TUDOIA_SQUADTI_URL` | Opcional: só `http://127.0.0.1` ou `http://localhost` (padrão `:8790`) |

Ligar e desligar: Sistema → Serviços → **SquadTI** (serviço Docker comum do painel) ou os scripts abaixo.

## Papéis e privacidade

- **Leitor** vê tarefas e arquivos. **Operador** inicia, responde e aprova (inclusive o release, que só gera notas: nada é commitado, tagueado nem publicado).
- O perfil padrão é `local-estrito` (nunca sai da máquina). `local`, `hibrido` e `nuvem` exigem o consentimento marcado na criação da tarefa, gravado no estado dela.
  `tudoia-max` (pago) não é oferecido, e a chave da Squad nem o lista.
- Arquivos lidos pelo painel omitem linhas com padrão de segredo. Uma execução por vez (a API responde 409 se houver outra).
- A API só escuta em `0.0.0.0` **dentro** do container; no host a porta é publicada só em `127.0.0.1`. O `Host` da requisição precisa ser `127.0.0.1:8790` ou `localhost:8790`.

## Custo e telemetria

A chave leva a tag `squadti` no LiteLLM, então Atividade e Custos distinguem o gasto da Squad. Para rotacionar: `scripts\tudoia.ps1 squadti-chave --rotacionar`.

## Scripts do Windows

| Script | O que faz |
|---|---|
| `scripts\iniciar.ps1 [-ComSquadti]` | Liga Docker, Ollama, ComfyUI, serviços e painel; com `-ComSquadti`, também (re)constrói e sobe a Squad |
| `scripts\parar.ps1` | Desliga painel, Squad, serviços, Ollama e ComfyUI (os dois últimos só se o `.env` os configurou) |
| `scripts\reiniciar.ps1 [-ComSquadti] [-Tudo]` | Padrão: reinicia **só** o painel (e a Squad, se ligada), sem derrubar Ollama, ComfyUI nem Docker. `-Tudo` = parar + iniciar |
| `scripts\painel.ps1` | Abre o painel; sobe-o se não estiver no ar |

Os scripts compartilham `scripts\_comum.ps1`. A porta é testada por conexão TCP real: `Get-NetTCPConnection -State Listen` deixa entradas fantasma (PID 0) de processos
mortos, e o launcher chegou a achar que um painel parado estava no ar.
