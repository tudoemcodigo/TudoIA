# TudoIA

Stack local de IA para uma máquina com GPU: um painel de controle, um gateway (LiteLLM) com roteador entre modelos
gratuitos, locais e pagos, um servidor de memória e busca (Cérebro), a governança que distribui regras, skills e
servidores MCP para os clientes de IA, e os serviços que sobem por Docker ou direto no host (Ollama, ComfyUI).

O projeto é de uso pessoal e está em evolução. A instalação está automatizada e testada só no Windows. No Linux há o
`scripts/tudoia.sh`, com os mesmos comandos, sem teste. macOS não é automatizado (ver [instalação](docs/instalacao.md)).

Licença: Apache-2.0 (ver [LICENSE](LICENSE)). Skills de terceiros mantêm a licença de origem, listada em
[governanca/ORIGEM.md](governanca/ORIGEM.md).

## Componentes

| Componente | O que faz | Código | Documentação |
|---|---|---|---|
| Painel | Interface e API de controle (FastAPI + SPA). Login OIDC, serviços, modelos, roteador, governança, segredos, Estúdio | `painel/` | [painel](docs/componentes/painel.md) |
| Gateway e roteador | LiteLLM na porta 4000. Hook `tudoia-auto` escolhe o grupo de modelos por regras e similaridade semântica | `runtime/litellm/`, `config/` | [roteador](docs/componentes/roteador.md) |
| Cérebro | Servidor MCP local: busca na web, leitura de páginas, busca nos seus documentos e memória de fatos | `runtime/cerebro/` | [cérebro](docs/componentes/cerebro.md) |
| Governança | Uma fonte de regras, skills e MCP, distribuída para Claude Code, Cursor, Antigravity, Codex e OpenCode | `governanca/` | [governança](docs/componentes/governanca.md) |
| Login (Keycloak) | Realm `tudoia` com papéis de admin, operador e leitor | `scripts/keycloak/`, `infra/keycloak/` | [keycloak](docs/componentes/keycloak.md) |
| Modelos | Manifesto e baixador dos pesos de IA (fora do repositório) | `config/modelos.yaml`, `scripts/modelos/` | [modelos](docs/componentes/modelos.md) |
| Serviços Docker | Open WebUI, SearXNG, Kokoro (voz), n8n e o Postgres do LiteLLM | `runtime/docker-compose.yml` | [serviços Docker](docs/componentes/servicos-docker.md) |
| Serviços do host | Ollama (LLMs locais) e ComfyUI (imagens e vídeo, usado pelo Estúdio) | `painel/tudoia_painel/servicos.py` | [arquitetura](docs/arquitetura.md) |
| Estúdio | Chat, imagens, vídeos e músicas pelo ComfyUI ou por provedores de nuvem | `painel/tudoia_painel/rotas/estudio_*.py` | [estúdio](docs/componentes/estudio.md) |
| Automação | Fluxos do n8n (resumo de documentos, pesquisa, digest de notícias, ingestão no Cérebro) | `automacao/n8n/` | [automação n8n](docs/componentes/automacao-n8n.md) |
| Backup | Postgres do LiteLLM, `cerebro.db` e volumes do n8n e do Open WebUI, com manifesto sha256 (sem o `.env`) | `scripts/backup/` | [instalação](docs/instalacao.md#11-backup) |

## Início rápido

**Windows, um clique:** `TudoIA-Setup.exe` abre um assistente que instala tudo (Docker Desktop, Ollama, serviços, login e atalhos), com as pastas e os componentes à sua escolha. Veja [docs/instalador.md](docs/instalador.md). Para gerar o `.exe`: `.\scripts\tudoia.ps1 empacotar`.

Manual, no Windows:

Pré-requisitos, passo a passo e verificação estão em [docs/instalacao.md](docs/instalacao.md). Em resumo, no Windows:

```powershell
uv sync
Copy-Item .env.example .env
.\scripts\tudoia.ps1 segredos
.\scripts\tudoia.ps1 keycloak         # Keycloak no ar em localhost:8180
.\scripts\tudoia.ps1 up
.\scripts\tudoia.ps1 n8n-credencial   # credencial do Cérebro no n8n
.\scripts\tudoia.ps1 painel           # http://127.0.0.1:3100/app/
```

Os modelos de IA são baixados à parte (`tudoia.ps1 modelos`). Backup: `tudoia.ps1 backup`. A ordem completa está na
instalação.

## Documentação

- [Instalação](docs/instalacao.md): pré-requisitos por máquina, passo a passo e verificação.
- [Configuração](docs/configuracao.md): todas as variáveis do `.env`, agrupadas.
- [Arquitetura](docs/arquitetura.md): componentes, portas, fluxos de requisição e onde ficam os dados.
- [Segurança](docs/seguranca.md): modelo de ameaças, controles implementados e riscos residuais. Inclui como
  reportar uma vulnerabilidade.
- Componentes:
  - [Painel](docs/componentes/painel.md)
  - [Estúdio](docs/componentes/estudio.md)
  - [Serviços Docker](docs/componentes/servicos-docker.md)
  - [Automação n8n](docs/componentes/automacao-n8n.md)
  - [Roteador (LiteLLM)](docs/componentes/roteador.md)
  - [Cérebro (MCP)](docs/componentes/cerebro.md)
  - [Governança](docs/componentes/governanca.md)
  - [Keycloak](docs/componentes/keycloak.md)
  - [Modelos de IA](docs/componentes/modelos.md)
- Desenvolvimento e licenças de terceiros:
  - [Desenvolvimento](docs/desenvolvimento.md)
  - [Terceiros](docs/terceiros.md)

## Estado do projeto

- Versão do pacote Python: 2.0.0 (`pyproject.toml`).
- Python 3.12 (`.python-version`).
- Os modelos, os pesos e os dados de execução não fazem parte do repositório (`modelos/` e `dados/` são ignorados).
