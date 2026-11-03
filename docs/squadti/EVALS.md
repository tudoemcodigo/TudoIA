# Evals da SquadTI (qualidade real de ponta a ponta)

Os testes unitários provam que o orquestrador funciona com modelos falsos. Os evals respondem à outra pergunta: **com modelo real, a Squad entrega código bom?**
Eles rodam briefings sintéticos pela API HTTP, deixam a Squad trabalhar de verdade e conferem o resultado com verificadores em código. Código em
[`runtime/squadti/evals/`](../../runtime/squadti/evals/).

> [!WARNING]
> **MODO EVAL**: o driver aprova sozinho a especificação e o release. É uma aprovação automática de TESTE, registrada em cada resultado
> (`modo_eval`, `aprovacoes_automaticas`) e no topo do relatório. Nada é commitado nem publicado, mas ninguém revisou a entrega. Cada execução consome tokens
> do perfil `auto` (pode usar nuvem; o driver envia `consentimento_nuvem: true`). Os briefings são sintéticos: sem dado real.

## Como rodar (dentro do container)

A imagem copia `orquestrador/` e `evals/` para `/app`. O token já está no ambiente do container (`TUDOIA_SQUADTI_TOKEN`); o driver o lê de lá e nunca por argumento.

```powershell
# todos os casos, uma vez
docker exec -e PYTHONPATH=/app squadti python -m evals.run --saida /dados/evals/resultados

# um caso, três vezes (pass@3 e pass^3)
docker exec -e PYTHONPATH=/app squadti python -m evals.run --caso d-pedidos --k 3 --saida /dados/evals/resultados
```

Opções: `--caso ID` (repetível), `--k N` (1 a 20), `--saida PASTA`, `--url` (só loopback; padrão `http://127.0.0.1:8790`), `--timeout-s` (prazo global por execução; padrão o `timeout_s` do caso),
`--intervalo-s` (polling). Código de saída: 0 tudo passou, 1 algum caso falhou, 2 uso inválido. A Squad executa uma tarefa por vez, então as execuções são em série: um caso leva de dezenas de minutos a ~2 h.

Para ler os resultados no host: `docker cp squadti:/dados/evals/resultados ./resultados`. Fora do container (API publicada em `127.0.0.1:8790`):
`cd runtime/squadti; $env:TUDOIA_SQUADTI_TOKEN=...; uv run python -m evals.run`.

## Os casos dourados (`evals/casos/*.json`)

| Caso | Complexidade | O que exercita |
|---|---|---|
| `a-crud-tarefas` | 1 | CRUD, validação (título obrigatório) |
| `b-catalogo` | 2 | regra de preço (Decimal), paginação, SKU único |
| `c-autenticada` | 3 | token Bearer, papéis admin/usuário, escopo por dono (IDOR: B acessa nota de A deve dar 404), limite de login |
| `d-pedidos` | 4 | idempotência por `Idempotency-Key`, máquina de estados (409), concorrência |

Todos usam a stack fixa `python`. Cada JSON traz `briefing`, `respostas_da_entrevista`, `limites` (`tokens`, `tempo_s`: o que os verificadores conferem), `orcamento` (o teto que a Squad
recebe, maior que o limite para o verificador, e não a parada da Squad, acusar o estouro), `timeout_s` e `verificadores_extra`. O driver envia **todas** as respostas fixas numa única
mensagem quando a tarefa pausa em `aguardando_respostas`; se o analista perguntar de novo, responde "adote o padrão da Doutrina" e, após 3 rodadas, encerra o caso (`entrevista_nao_convergiu`).

## Verificadores (`evals/verificadores.py`)

Funções puras `(workspace, api, caso) -> {nome, passou, detalhe}`. Falham fechado: relatório ausente, corrompido, grande demais ou fora do workspace reprova.

| Verificador | Passa quando |
|---|---|
| `desfecho_concluida` | `situacao.estado == "concluida"` |
| `build_e_testes` | `qa_report.json` tem `backend-build` e `backend-testes` com código 0 |
| `cobertura` | linha e ramo >= `cobertura_minima` do caso (90) e o gate não foi desligado |
| `sem_achados_graves` | `hacker_report.json` e `macaco_report.json` existem e não têm achado CRITICO/ALTO |
| `portoes_verdes` | `tests/review/security/devops_passed` no estado; `aprovado: true` em QA/AppSec/DevOps; hacker/macaco/carga existem e não declaram `aprovado: false` |
| `arquivos_obrigatorios` | README, PRD técnico, OpenAPI, Dockerfile, `.gitignore`, `docs/proveniencia.json` presentes e não vazios |
| `sem_segredos` | nenhum padrão de segredo no workspace (só tipo e `arquivo:linha` no resultado, nunca o valor) |
| `proveniencia_doutrina` | versão e hash da Doutrina em `docs/proveniencia.json` = os que a tarefa usou |
| `limites_tokens_tempo` | `totais.tokens` (auditoria) e a duração medida pelo driver <= `limites` do caso |
| `conversa_com_chefe` | há mensagem do usuário e do CHEFE em `/mensagens` |

Verificadores por caso: `verificadores_extra` com `tipo: "conteudo_contem"` (`glob`, `termos_todos`, `termos_qualquer`), p.ex. o OpenAPI do caso `d` precisa conter `Idempotency-Key`.
Eles conferem presença de elementos, não correção do comportamento: uma suíte que *cita* 404 não prova que o IDOR está fechado (isso é papel dos relatórios hacker/macaco e de revisão humana).

## Como ler o resultado

`<saida>/<rodada>/` (rodada = `AAAA-MM-DD_HHMMSS`):

- `RELATORIO.md`: tabela por caso (passou, pass@k, pass^k, verificadores que falharam, tokens médios, duração média, nós mais lentos), motivos de parada, detalhe das falhas e a **comparação com a rodada anterior**.
- `<caso>-<n>.json`: resultado de uma execução (desfecho, motivo, verificadores, tokens, duração, aprovações automáticas).
- `<caso>-<n>/workspace/`: cópia dos arquivos coletados por `/arquivo` (a API já omite linhas com padrão de segredo).
- `resumo.json`: usado para comparar com a próxima rodada.

**pass@k** = alguma das k execuções passou (capacidade). **pass^k** = todas passaram (confiabilidade; é o número que importa para confiar na Squad sem supervisão).
Regressão = caso que passava em todas as execuções e agora falha, ou tokens/duração médios +30% sobre a rodada anterior. Desfechos de parada:
`escalada` (orçamento, estagnação, QA/AppSec/DevOps bloqueando), `erro_de_execucao`, `erro_de_api`, `timeout`, `entrevista_nao_convergiu`, `aprovacao_em_loop`, `estado_inesperado`.

## Limites conhecidos

- Os relatórios `hacker/macaco/carga_report.json` ainda não têm formato fixado: o leitor aceita `severidade`/`severity` em qualquer nível e resumos `{"ALTO": n}`; ajuste `_graves` quando o formato fechar.
- Se a execução falhar antes do primeiro checkpoint (p.ex. modelo recusado), a API responde 404 para a tarefa e o motivo não é visível pela API: o driver espera até 10 min e reprova com `erro_de_api`; o motivo está no log do container.
- Não substitui revisão humana nem testa o comportamento do código gerado além do que a própria Squad executa.
