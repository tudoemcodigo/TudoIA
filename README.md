<div align="center">

<img src="https://www.tudoemcodigo.com/marca/PNG/tudoemcodigo-icone-512.png" alt="TudoIA" width="120" />

# 🧠 TudoIA

**Uma stack local de IA para uma máquina com GPU: painel de controle, gateway com roteador entre modelos gratuitos, locais e pagos, memória e busca por MCP e uma única fonte de regras, skills e servidores MCP para todos os seus clientes de IA.**

LiteLLM · Ollama · ComfyUI · Cérebro (MCP) · Keycloak · Open WebUI · n8n · SquadTI · Python 3.12 · Windows

[![CI](https://github.com/tudoemcodigo/TudoIA/actions/workflows/ci.yml/badge.svg)](https://github.com/tudoemcodigo/TudoIA/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](.python-version)
[![Versão](https://img.shields.io/badge/vers%C3%A3o-2.0.6-blue)](pyproject.toml)
[![Licença: Apache 2.0](https://img.shields.io/badge/licen%C3%A7a-Apache%202.0-blue)](LICENSE)

[📥 Instalação](#-instalação-e-início-rápido) · [🧩 Componentes](#-componentes) · [📚 Documentação](docs/README.md) · [🛡️ Segurança](docs/seguranca.md) · [📖 Glossário](docs/glossario.md)

</div>

---

> [!WARNING]
> O TudoIA é de uso pessoal e está em evolução. A instalação está automatizada e **testada só no Windows**. No Linux há o `scripts/tudoia.sh`, com quase os mesmos comandos e sem teste; no macOS nada é automatizado. Ver [instalação manual](docs/instalacao.md).

## 📑 Sumário

- [✨ O que é](#-o-que-é)
- [🧩 Componentes](#-componentes)
- [📥 Instalação e início rápido](#-instalação-e-início-rápido)
- [📚 Documentação](#-documentação)
- [🛡️ Segurança](#️-segurança)
- [🧪 Testes](#-testes)
- [🤝 Contribuição](#-contribuição)
- [🏷️ Versionamento](#️-versionamento)
- [📄 Licença](#-licença)

---

## ✨ O que é

| Sem o TudoIA | Com o TudoIA |
|---|---|
| Cada cliente de IA (Claude Code, Cursor, Codex...) com suas próprias regras, skills e MCP, copiados à mão | Uma pasta (`governanca/`) distribui regras, skills e MCP para todos, sem sobrescrever o que é seu e sem gravar segredo em workspace |
| Um provedor ou modelo por vez, escolhido na unha | Um gateway (LiteLLM, porta 4000) e o `tudoia-auto`, que escolhe o grupo de modelos por regras e similaridade semântica |
| Dado sensível indo para a nuvem sem querer | Perfis como `tudoia-local-estrito` (nunca sai da máquina) e marcadores `#local`, `#nuvem` e `#max` |
| Memória e busca espalhadas | O Cérebro, um servidor MCP local com busca na web, leitura de páginas, busca nos seus documentos e memória de fatos |
| Ligar e desligar tudo em vários terminais | Um painel com login (OIDC) para serviços, modelos, roteador, segredos, governança e Estúdio |

- ✅ **Local por padrão:** todas as portas ficam em `127.0.0.1`; nenhum container recebe o `.env` inteiro.
- ✅ **Falha fechada:** sem login configurado o painel responde 503; a governança valida tudo antes de escrever.
- ✅ **Reproduzível:** imagens de terceiros fixadas por digest, `uv.lock` por projeto e instalador gerado no CI.

## 🧩 Componentes

| Componente | O que faz | Código | Guia |
|---|---|---|---|
| Painel | Interface e API de controle (FastAPI e SPA): login OIDC, serviços, modelos, roteador, governança, segredos, Estúdio | `painel/` | [painel](docs/componentes/painel.md) |
| Gateway e roteador | LiteLLM na porta 4000; o hook `tudoia-auto` escolhe o grupo de modelos | `runtime/litellm/`, `config/` | [roteador](docs/componentes/roteador.md) |
| Cérebro | Servidor MCP local: busca na web, leitura de páginas, busca nos documentos e memória de fatos | `runtime/cerebro/` | [cérebro](docs/componentes/cerebro.md) |
| Governança | Fonte única de regras, skills e MCP para Claude Code, Cursor, Antigravity, Codex, OpenCode e Aider | `governanca/` | [governança](docs/componentes/governanca.md) |
| Doutrina TEC | Regras de engenharia consumidas pela skill `doutrina-tec`, pelo MCP `doutrina-tec` e pela SquadTI; commit fixado | `governanca/doutrina.json` | [doutrina](docs/componentes/doutrina.md) |
| Login (Keycloak) | Realm `tudoia` com os papéis admin, operador e leitor | `scripts/keycloak/`, `infra/keycloak/` | [keycloak](docs/componentes/keycloak.md) |
| Modelos | Manifesto e baixador dos pesos de IA (fora do repositório) | `config/modelos.yaml`, `scripts/modelos/` | [modelos](docs/componentes/modelos.md) |
| Serviços Docker e do host | Postgres, LiteLLM, Open WebUI, SearXNG, Kokoro, n8n e Keycloak no Docker; Ollama e ComfyUI no host | `runtime/docker-compose.yml`, `painel/tudoia_painel/servicos.py` | [serviços Docker](docs/componentes/servicos-docker.md) |
| Estúdio | Chat, imagens, vídeos e músicas pelo ComfyUI ou por provedores de nuvem | `painel/tudoia_painel/rotas/estudio_*.py` | [estúdio](docs/componentes/estudio.md) |
| Automação | Quatro fluxos do n8n (resumo de documentos, pesquisa, digest de notícias, ingestão no Cérebro) | `automacao/n8n/` | [automação n8n](docs/componentes/automacao-n8n.md) |
| SquadTI | Equipe de agentes (LangGraph) que gera projetos novos, em container isolado | `runtime/squadti/` | [squadti](docs/componentes/squadti.md) |
| Instalador | `TudoIA-Setup.exe`: instala tudo no Windows, com os componentes à sua escolha | `instalador/`, `scripts/empacotar/` | [instalador](docs/instalador.md) |
| Backup | Postgres, `cerebro.db` e volumes do n8n e do Open WebUI, com manifesto sha256 (sem o `.env`) | `scripts/backup/` | [instalação](docs/instalacao.md) |

Como as peças se ligam, as portas e onde ficam os dados: [arquitetura](docs/arquitetura.md).

## 📥 Instalação e início rápido

**Windows, um clique.** Baixe o [`TudoIA-Setup.exe`](https://github.com/tudoemcodigo/TudoIA/releases/latest/download/TudoIA-Setup.exe) e o [`.sha256`](https://github.com/tudoemcodigo/TudoIA/releases/latest/download/TudoIA-Setup.exe.sha256) da última release, confira o download e execute:

```powershell
(Get-FileHash .\TudoIA-Setup.exe -Algorithm SHA256).Hash.ToLower()   # compare com o conteúdo do .sha256
```

O assistente instala Docker Desktop, Ollama, os serviços, o login e os atalhos, com as pastas e os componentes à sua escolha. O `.exe` **não é assinado digitalmente** (o SmartScreen avisa na primeira execução). Detalhes: [instalador](docs/instalador.md). Para gerar o `.exe` você mesmo: `.\scripts\tudoia.ps1 empacotar`.

**Windows, manual.** Pré-requisitos: [uv](https://docs.astral.sh/uv/), Docker Desktop com `docker compose`, Ollama e Git. Na raiz do repositório:

```powershell
git clone https://github.com/tudoemcodigo/TudoIA.git
cd TudoIA
uv sync
Copy-Item .env.example .env
.\scripts\tudoia.ps1 segredos                       # gera só os segredos internos vazios
$env:PYTHONPATH = "$PWD;$PWD\painel"
uv run python -m tudoia_painel gerar-config         # cria runtime\litellm\config.yaml (não é versionado)
.\scripts\tudoia.ps1 up                             # Ollama, sync da governança, serviços Docker e painel
.\scripts\tudoia.ps1 status                         # espere o keycloak ficar "healthy"
.\scripts\tudoia.ps1 keycloak --admin-inicial admin@example.com
.\scripts\reiniciar.ps1                             # o painel só lê o .env ao iniciar
.\scripts\tudoia.ps1 n8n-credencial                 # credencial do Cérebro no n8n
.\scripts\tudoia.ps1 modelos --obrigatorios         # pesos de IA (fora do repositório)
```

O painel fica em `http://127.0.0.1:3100/app/`. Entre com a conta criada por `--admin-inicial`; a senha temporária aparece uma única vez. Troque `admin@example.com` pelo seu e-mail. Guarde uma cópia do `.env` fora da máquina: o backup do TudoIA não o inclui. Pré-requisitos, verificação, backup e atualização: [instalação manual](docs/instalacao.md). Variáveis do `.env`: [configuração](docs/configuracao.md).

Dia a dia: `.\scripts\iniciar.ps1` liga tudo, `.\scripts\parar.ps1` desliga tudo (dados e volumes ficam), `.\scripts\reiniciar.ps1` reinicia só o painel, `.\scripts\tudoia.ps1 backup` faz o backup. Quando algo não funcionar, [operação](docs/operacao.md).

## 📚 Documentação

Índice completo, com tipo e propósito de cada documento: [docs/README.md](docs/README.md).

| Documento | O que responde |
|---|---|
| [Glossário](docs/glossario.md) | O termo canônico de cada conceito do projeto |
| [Arquitetura](docs/arquitetura.md) | Componentes, portas, fluxos e onde ficam os dados |
| [Configuração](docs/configuracao.md) | Toda variável do `.env`: padrão, efeito e onde é lida |
| [Instalação manual](docs/instalacao.md) | Pré-requisitos, passo a passo, verificação, backup e desinstalação |
| [Instalador](docs/instalador.md) | Instalar com o `TudoIA-Setup.exe`; empacotar e publicar o executável |
| [Operação](docs/operacao.md) | Runbooks: sintoma, diagnóstico, mitigação, reversão |
| [Segurança](docs/seguranca.md) | Modelo de ameaças, controles, riscos residuais e como reportar |
| [Desenvolvimento](docs/desenvolvimento.md) | Ambiente, lint, testes, convenções e como adicionar um componente |
| [Terceiros](docs/terceiros.md) | Licenças, versões e serviços externos |
| [Painel](docs/componentes/painel.md) | Rotas, papéis e operação do painel |
| [Estúdio](docs/componentes/estudio.md) | Imagem, vídeo e música: motores, limites e custos |
| [Roteador](docs/componentes/roteador.md) | Grupos, perfis, `tudoia-auto` e quarentena |
| [Cérebro](docs/componentes/cerebro.md) | Ferramentas MCP, autenticação e limites |
| [Governança](docs/componentes/governanca.md) | O que é escrito em cada cliente de IA e onde |
| [Doutrina](docs/componentes/doutrina.md) | Integração com a Doutrina TEC e o commit fixado |
| [Keycloak](docs/componentes/keycloak.md) | Realm, provisionamento e login do painel |
| [Modelos](docs/componentes/modelos.md) | Manifesto, catálogo, download e verificação dos pesos |
| [Serviços Docker](docs/componentes/servicos-docker.md) | Containers, portas, volumes e processos do host |
| [Automação n8n](docs/componentes/automacao-n8n.md) | Importar e usar os fluxos do n8n |
| [SquadTI (componente)](docs/componentes/squadti.md) | O que a Squad faz, isolamento e configuração |
| [SquadTI 00 Visão geral](docs/squadti/00-visao-geral-e-arquitetura.md) | Por que a squad é um grafo de artefatos |
| [SquadTI 01 Catálogo de agentes](docs/squadti/01-catalogo-de-agentes.md) | Papéis, entradas, saídas e regras |
| [SquadTI 02 Protocolo e estado](docs/squadti/02-protocolo-de-comunicacao-e-estado.md) | Ciclo da tarefa e `SquadState` |
| [SquadTI 03 Guia de implementação](docs/squadti/03-guia-de-implementacao.md) | Conexão com o gateway e o grafo real |
| [SquadTI 04 Agentes](docs/squadti/04-agentes/chefe-orquestrador.md) | Um perfil por papel, a partir do CHEFE (pasta `docs/squadti/04-agentes/`) |
| [SquadTI 05 Doutrina](docs/squadti/05-fonte-da-verdade-arquitetura.md) | Como as regras chegam aos agentes |
| [SquadTI 06 Sistema web](docs/squadti/06-sistema-web-squadti.md) | Proposta de portal (não implementada) |
| [SquadTI 07 Análise crítica](docs/squadti/07-analise-critica-e-benchmarks.md) | Registro histórico de benchmarks |
| [SPEC.md](SPEC.md) | Interface pública do módulo `governanca` |

## 🛡️ Segurança

Resumo: tudo escuta só em loopback, o painel exige login OIDC com papéis, os segredos vivem só no `.env` (ignorado pelo git) e a governança nunca grava segredo em workspace. A SquadTI monta o `docker.sock` do host para os testes de integração, o que a isola menos do host do que o resto da stack; leia o aviso no guia.

**Como reportar uma vulnerabilidade:** não abra issue pública com detalhes de exploração. Use o security advisory privado do repositório e siga o passo a passo em [docs/seguranca.md](docs/seguranca.md#como-reportar-uma-vulnerabilidade). Nunca cole o valor de um segredo em um relato.

## 🧪 Testes

O CI (`.github/workflows/ci.yml`) roda em todo push e pull request. Os mesmos comandos, na raiz:

```powershell
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen pytest -q
cd runtime\cerebro; uv sync --frozen; uv run --frozen pytest -q; cd ..\..
cd runtime\squadti; uv sync --frozen; uv run --frozen python -W error -m pytest -q; cd ..\..
```

Os testes não usam rede, Docker, GPU nem Keycloak. Resultado de 2026-11-03 neste repositório: lint sem erros; raiz com 1360 testes passando, 1 ignorado e 2 falhas (uma intermitente sob carga, outra que depende de um trecho do guia da SquadTI, ver [desenvolvimento](docs/desenvolvimento.md#testes)); Cérebro com 149 passando; SquadTI com 190 passando.

## 🤝 Contribuição

Mudanças entram por pull request. Antes de abrir um, rode o lint e as três suítes acima, acrescente testes que cubram o caminho feliz e as falhas, e atualize o guia do componente que você tocou (a documentação segue [docs/README.md](docs/README.md#-convenções-desta-documentação)). Nunca inclua segredo, dado pessoal ou caminho real da sua máquina em código, teste ou documento. Convenções, layout do repositório e o passo a passo para adicionar um componente: [desenvolvimento](docs/desenvolvimento.md). As regras e skills dos agentes de IA são geradas: edite `governanca/regras/` e `governanca/skills/`, não o `AGENTS.md`.

## 🏷️ Versionamento

[SemVer](https://semver.org/lang/pt-BR/). A versão do produto é a do `pyproject.toml` (2.0.6) e precisa ser igual à do instalador (`instalador/tudoia_instalador/__init__.py`) e à tag `vX.Y.Z` da release; o teste `tests/instalacao/test_versao.py` e o workflow `release.yml` conferem. Empurrar a tag constrói o `TudoIA-Setup.exe` no CI e publica a release com notas geradas automaticamente; não há `CHANGELOG.md`. Cada projeto Python (Cérebro, SquadTI) tem a própria versão interna, sem tag.

## 📄 Licença

Apache-2.0 (ver [LICENSE](LICENSE) e [NOTICE](NOTICE)). Skills, servidores MCP, imagens e pesos de terceiros mantêm a licença de origem: [docs/terceiros.md](docs/terceiros.md) e [governanca/ORIGEM.md](governanca/ORIGEM.md).
