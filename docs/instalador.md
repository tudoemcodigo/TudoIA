# Instalador (TudoIA Setup)

`TudoIA-Setup.exe` instala o ecossistema numa máquina Windows limpa: assistente no navegador, pré-requisitos (Docker
Desktop, Ollama, uv), serviços Docker, login (Keycloak) e atalhos. Não leva nada da máquina onde foi gerado.

## Para quem instala

1. Copie `TudoIA-Setup.exe` (e confira o SHA-256 em `TudoIA-Setup.exe.sha256`) e dê duplo clique. O Windows
   SmartScreen avisa porque o executável **não é assinado**: *Mais informações > Executar assim mesmo*.
2. O instalador abre uma tela em `http://127.0.0.1:<porta>/` (só neste PC, protegida por token) com seis passos:
   **Sistema**, **Onde instalar**, **O que instalar**, **Conta e chaves**, **Revisar**, **Instalar**.
3. No fim aparece o endereço do painel, o e-mail do administrador e uma **senha temporária, mostrada uma única vez**
   (a troca é obrigatória no primeiro login; a política do realm exige 12 caracteres).

### O que a tela parametriza

| Passo | Opções |
|---|---|
| Onde instalar | Pasta de instalação (padrão `C:\TudoIA`), pasta de **dados** (vira junção em `<instalação>\dados`), pasta dos modelos do Ollama, pasta do ComfyUI portable, nome do projeto Docker |
| O que instalar | Núcleo (sempre: painel, LiteLLM, Postgres) e, à escolha: Cérebro + SearXNG, Open WebUI + Kokoro, n8n, Keycloak embutido (ou usar um existente em `localhost:8180`), Ollama, ComfyUI portable (só com GPU NVIDIA) |
| Conta e chaves | E-mail do primeiro administrador, fuso horário, chaves de provedores (opcionais), atalhos, iniciar ao final, configurar Claude Code/Cursor/Codex (`sync`, desligado por padrão), origem do código (embutido ou GitHub) |

**Modelos de IA não são baixados na instalação** (dezenas de GB). Depois, use o painel ou `tudoia modelos`.

### O que ele faz, em ordem

verificar o sistema → instalar os arquivos → pastas e junção de dados → `.env` (chaves só nele; acesso restrito ao seu
usuário) → `uv` → dependências Python (`uv sync --frozen`) → segredos internos → Docker Desktop (winget, com a janela
de permissão do Windows; se precisar reiniciar, abra o TudoIA Setup de novo depois do reinício, carregue as opções anteriores e ele continua de onde parou) → Ollama → configuração do LiteLLM → `docker compose
pull` e `up --wait` → Keycloak (realm, clientes e administrador) → credencial do n8n → ComfyUI → atalhos → painel.

Cada etapa é idempotente. Se uma falha, corrija e clique em **Tentar de novo**: o que já terminou é pulado. O estado
fica em `%LOCALAPPDATA%\TudoIA-Setup\estado.json` (sem segredos) e o registro em `instalador.log` (com segredos
mascarados).

### Depois de instalado

Atalhos **TudoIA - Iniciar**, **TudoIA - Parar** e **TudoIA - Desinstalar** na área de trabalho e no menu Iniciar
(`scripts\iniciar.ps1`, `parar.ps1`, `desinstalar.ps1`). A desinstalação mantém `dados` e `modelos` a menos que você
digite `APAGAR`; só apaga pastas que tenham a marca `.tudoia-instalacao.json`.

### Sem tela (automação)

```powershell
TudoIA-Setup.exe --config opcoes.json      # mesmos nomes de campo da tela; o JSON pode ter segredos: apague-o depois
TudoIA-Setup.exe --desinstalar C:\TudoIA [--remover-dados]
TudoIA-Setup.exe --versao
```

Códigos de saída da instalação: 0 ok, 1 falhou, 2 opções inválidas, 3 precisa reiniciar o Windows.

## Limites conhecidos

- Só Windows 10 2004+ / 11. Linux e macOS não têm instalador.
- Portas fixas (3100, 4000, 8765, 3000, 8080, 8880, 5678, 5433, 8180, 11434, 8188): o instalador confere se estão livres e
  recusa instalar por cima de outro programa. Uma instalação por máquina (os containers têm nome fixo).
- Docker Desktop, Ollama e ComfyUI são baixados da internet. O caminho do Docker Desktop (winget elevado, WSL2,
  reinício) foi escrito conforme a documentação e coberto por testes com duplos, **mas não foi executado numa máquina
  sem Docker**.
- O Keycloak embutido roda em modo `start` com HTTP, só em `127.0.0.1`. É para uso local.
- O `.exe` não é assinado. Antivírus podem reclamar de executáveis PyInstaller; confira o SHA-256.

## Para quem empacota

```powershell
.\scripts\tudoia.ps1 empacotar        # = python -m scripts.empacotar.construir
```

1. `scripts/empacotar/payload.py` monta `instalador/dados/payload.zip` por **lista de permissão** (`INCLUIR`): nunca
   entram `.env`, `dados`, `modelos`, `.venv`, bancos, caches, memórias de agentes nem o `config.yaml` do LiteLLM. O zip
   é reprodutível (mesmo código, mesmo SHA-256).
2. O mesmo script **varre o pacote** atrás de chaves de API, tokens, chaves privadas, JWT, senha em URL, e-mails
   pessoais, a pasta de usuário do Windows e o nome de usuário e do computador de quem empacota. Qualquer achado
   reprova a construção. Para termos extras: `PESSOAIS_EXTRA=nome1,nome2`.
3. PyInstaller (`--onefile`) gera `dist/TudoIA-Setup.exe` (~9 MB) e o `.sha256`.

Para mudar o que entra no pacote, edite `INCLUIR`/`EXCLUIR` em `payload.py`. O teste
`tests/instalacao/test_payload.py::test_o_repositorio_real_gera_um_pacote_limpo` reprova se alguém commitar um segredo.

## Segurança do assistente

Ele executa comandos e grava arquivos, então a tela local é fechada: escuta só em `127.0.0.1`; token aleatório por
execução (cabeçalho `X-Token`, comparação em tempo constante); `Host` exato; `Origin` local; corpo JSON de até 256 KB;
CSP restritiva; nada de CORS. Toda opção é validada antes de virar caminho, comando ou linha de `.env` (caminhos sem
`% $ \` ' ; & ^ ! " < > | ? *`, nome de projeto, e-mail, repositório, chaves de provedor só as conhecidas). Comandos
rodam sem shell, com tempo limite e com os segredos mascarados no log. A extração do pacote barra `..`, caminho
absoluto, link simbólico e zip bomb. Downloads só por https nos hosts esperados.
