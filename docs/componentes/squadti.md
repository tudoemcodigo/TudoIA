# SquadTI no painel

O menu **SquadTI** (grupo Agentes) conduz o orquestrador [SquadTI](https://github.com/tudoemcodigo/SquadTI) pelo painel: inicia tarefas,
responde à entrevista do analista, aprova a especificação e o release e lê os arquivos gerados. O painel não executa a Squad: ele repassa
pedidos validados à **API local** do orquestrador (`orquestrador/api.py`, só loopback, sempre com token).

```
navegador ──► painel (/api/squadti/*, papéis, auditoria) ──► API da Squad (127.0.0.1:8790, Bearer) ──► LangGraph ──► LiteLLM
```

## Configuração (`.env`)

| Variável | Para que serve |
|---|---|
| `TUDOIA_SQUADTI_DIR` | Pasta do repositório SquadTI. O painel usa `orquestrador/api.py` e `.venv\Scripts\python.exe` dela (ou `TUDOIA_SQUADTI_PYTHON`) |
| `TUDOIA_SQUADTI_TOKEN` | Token da API da Squad (32+ caracteres). O painel e a API leem o mesmo valor; sem ele nada sobe nem é chamado |
| `SQUADTI_API_KEY` | Chave virtual do LiteLLM **só da Squad** (alias e tag `squadti`): lista os perfis locais e a nuvem gratuita, nunca `tudoia-max` |
| `DOUTRINA_TEC` | Pasta da Doutrina TEC que os agentes consomem |
| `TUDOIA_SQUADTI_URL` | Opcional. Padrão `http://127.0.0.1:8790`; só `http://127.0.0.1` ou `http://localhost` |
| `TUDOIA_SQUADTI_CONFIG`, `TUDOIA_SQUADTI_GATEWAY`, `TUDOIA_SQUADTI_PYTHON` | Opcionais: configuração de stack, URL do gateway e Python do ambiente |

Ligar e desligar: Sistema → Serviços → **SquadTI**. O processo roda em `dados\squadti` (workspace e checkpoint ficam ali, fora dos repositórios), com
log em `dados\logs\squadti.log`. O "todos" do painel não liga nem desliga a Squad.

## Papéis e privacidade

- **Leitor** vê tarefas e arquivos. **Operador** inicia, responde e aprova (inclusive o release, que só gera notas: nada é commitado, tagueado nem publicado).
- O perfil padrão é `local-estrito` (nunca sai da máquina). `local`, `hibrido` e `nuvem` exigem marcar o consentimento na criação da tarefa, e ele fica gravado
  no estado dela. `tudoia-max` (pago) não é oferecido.
- Arquivos lidos pelo painel omitem linhas com padrão de segredo.
- Uma execução por vez: a API responde 409 se houver outra. Reiniciar o serviço interrompe a execução em curso; o checkpoint permite retomar.

## Custo e telemetria

A chave `SQUADTI_API_KEY` leva a tag `squadti` no LiteLLM, então Atividade e Custos distinguem o gasto da Squad. Para gerar a chave, use `POST /key/generate`
do LiteLLM com `models` (os perfis acima), `key_alias: "squadti"` e `metadata: {"tags": ["squadti"]}`; guarde o valor só no `.env`.

## Scripts do Windows

| Script | O que faz |
|---|---|
| `scripts\iniciar.ps1 [-ComSquadti]` | Liga Docker, Ollama, ComfyUI, serviços e painel; com `-ComSquadti`, também a API da Squad |
| `scripts\parar.ps1` | Desliga painel, API da Squad, serviços, Ollama e ComfyUI (os dois últimos só se o `.env` os configurou) |
| `scriptseiniciar.ps1 [-ComSquadti] [-Tudo]` | Padrão: reinicia **só** o painel (e a Squad, se ligada), sem derrubar Ollama, ComfyUI nem Docker. `-Tudo` = parar + iniciar. Use depois de atualizar o código do painel |
| `scripts\painel.ps1` | Abre o painel; sobe-o se não estiver no ar (não reinicia um painel já ligado com código antigo) |

Os scripts compartilham `scripts\_comum.ps1`. A porta é testada por conexão TCP real: `Get-NetTCPConnection -State Listen` deixa entradas fantasma (PID 0) de processos
mortos, e o launcher chegou a achar que um painel parado estava no ar. Cada parada confere a linha de comando do processo antes de encerrá-lo.
