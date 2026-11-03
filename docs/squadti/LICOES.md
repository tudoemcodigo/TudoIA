# Livro de Lições da SquadTI

O Livro de Lições transforma achados dos agentes (hacker, macaco, revisor, sênior, QA...) em **prevenção no lugar certo**, para o mesmo erro não se repetir. Implementação: `runtime/squadti/orquestrador/licoes.py` (API pura: sem rede, sem modelo). Testes: `orquestrador/tests/test_licoes.py`.

## Ciclo

```
achados_agentes ──registrar──▶ livro (JSONL) ──triar──▶ destino
                                   │                        │
                       lição PENDENTE (dedup por tarefa)    ▼
                                   │                 humano aprova/rejeita
                                   ▼                        │
                      painel lista e decide  ◀──────────────┘
                                   │
              aprovada ──▶ licoes_para_prompt (prompt do papel)
                       ──▶ caso_de_regressao (evals)
                       ──▶ proposta_doutrina / exportar_propostas (se candidata)
                                   │
                       humano abre o PR na Doutrina ──▶ promover (estado promovida)
```

1. Ao fim da tarefa o orquestrador chama `registrar(livro, tarefa, stack, achados)` com os achados já estruturados.
2. A lição nasce `pendente` e **não influencia nada** até um humano aprovar.
3. `triar(licao)` diz para onde vai a prevenção; `aprovar`, `rejeitar`, `desativar` e `promover` registram quem e quando.
4. Aprovada, a lição entra no prompt do papel responsável (`licoes_para_prompt`), vira caso de regressão (`caso_de_regressao`) e, se candidata, vira proposta de Doutrina em arquivo.

## Árvore de decisão (`triar`)

Avaliada nesta ordem; a primeira que casar vale. Resultado: `{destino, motivo, papel_alvo, candidata_doutrina}`.

| # | Condição | Destino |
|---|---|---|
| 1 | categoria `componente` (defeito de `TEC.*`) | `componente` (pedido formal ao repositório do componente, ECO-MAP-02) |
| 2 | categoria `projeto` ou `regra-de-negocio` | `projeto` (spec/ADR do projeto gerado; nunca generaliza) |
| 3 | categoria `comportamento`, `formato` ou `comando` | `squad_config` |
| 4 | ID do kit de ataque (`AUTH`, `INJ`, `ERR`, `CORS`, `MASS`, `LIM`, `HDR`, `MET`, `RATE`, `IDOR`), ID `QC-*` ou categoria detectável por código (`segredos`, `dockerfile`, `complexidade`, `duplicacao`) | `squad_verificacao` (verificação determinística nova mais regressão) |
| 5 | ID no formato da Doutrina (`FAM-AREA-NN`, família conhecida) que **existe** na Doutrina: 1 tarefa | `squad_prompt` |
| 5b | idem, em **2 ou mais tarefas** (reincidência com regra citada) | `doutrina_esclarecimento` |
| 6 | sem regra (ID de revisor que a Doutrina não tem, ou achado de macaco) e categoria generalizável | `doutrina_regra_nova` |
| 7 | resto | `squad_prompt` |

"Existe na Doutrina" vem de `triar(licao, ids_doutrina)` (passe `doutrina_tec.ids_existentes(state)`); sem esse conjunto vale a marca `na_doutrina` que o achado trouxe (o nó do revisor sabe quais IDs foram para `nao_verificados`, e deve preencher `na_doutrina=False` neles); sem nenhuma das duas presume-se que existe.

**Papel alvo** (lista): kit de ataque e `ERR`/`AUTH` -> `backend`; `MAC-*` e `UI-*` -> `frontend`; `QC-*` -> `backend` e `frontend`; ID da Doutrina -> papéis da família (SEC -> backend/frontend, DAD -> dba, FRT -> frontend, DOC -> documentacao, REQ -> analista, ARQ/CMP/IA -> backend, ECO -> arquiteto); senão pela categoria; senão `backend`.

**`candidata_doutrina`**: o destino é `doutrina_esclarecimento` ou `doutrina_regra_nova` **e** há reincidência: `>= 2` tarefas distintas, ou 1 achado CRITICO de segurança. Verificação de código e prompt nunca são candidatos à Doutrina.

## Guardrails

1. **Texto nunca vem de prosa de modelo.** O livro só aceita campos estruturados validados: `agente` e `categoria` de vocabulário fechado (categoria fora da lista vira `outra`), `id` em formato fixo (`^[A-Z]{2,5}(-[A-Z]{2,5})?-\d{2,3}$`), severidade, `stack` e `tarefa` em formato restrito. Tudo passa por `entrada.sanitizar`. `endpoint` e `metodo` viram um hash de 16 hex; o texto deles não é gravado. O texto da lição sai de modelos fixos de frase (tabela por ID, depois por prefixo, depois por família/categoria, depois genérico), interpolando só contagem e ID validado, com no máximo 300 caracteres. A leitura do disco **revalida** cada linha (inclusive a impressão digital): livro adulterado à mão não injeta texto.
2. **Aprovação humana explícita.** Estados: `pendente`, `aprovada`, `rejeitada`, `desativada`, `promovida`. Transições permitidas: `pendente -> aprovada|rejeitada`, `aprovada -> desativada|promovida`, `desativada -> aprovada`. `rejeitada` e `promovida` são finais (reincidência não reabre decisão humana). `quem` é obrigatório, sanitizado e limitado a 80 caracteres. O histórico guarda de, para, quem, quando e o hash das evidências vistas na decisão.
3. **Origem rastreável sem conteúdo sensível.** Cada lição guarda tarefas, contagem, primeira e última ocorrência e `evidencia_hash` (hash do conjunto tarefa, evidência, severidade). Nunca prompt, resposta, endpoint nem segredo.
4. **Doutrina só por proposta.** `proposta_doutrina` recusa (`NaoCandidata`) lição sem reincidência; `exportar_propostas` grava `proposta-<id>.md` só para candidatas aprovadas/promovidas e **não sobrescreve** arquivo existente (pode ter edição humana). Nada aqui escreve na Doutrina. O ID da regra é placeholder `<FAMILIA>-<AREA>-<NN>`; o humano escolhe o definitivo.
5. **Dedup por impressão digital** (`agente + id + categoria + stack`). A contagem é de **tarefas distintas**: o mesmo achado repetido na mesma tarefa conta 1 (a maior severidade prevalece) e nem cresce o arquivo. BAIXO, severidade inválida e achado malformado são ignorados.

## O livro (arquivo)

- JSONL append-only; caminho: argumento `livro` > `SQUADTI_LICOES_ARQUIVO` > `licoes.jsonl`. Duas linhas: `o` (ocorrência por lição e tarefa) e `x` (transição de estado). O estado é sempre recalculado relendo o arquivo.
- Escrita: um único `write` em `O_APPEND` com `fsync`, sob trava de processo. Se o arquivo terminou sem quebra de linha (queda no meio da escrita), a próxima escrita começa por uma, sem colar na linha quebrada.
- Linha quebrada, maior que 2 KiB ou inválida: **ignorada com aviso** (logger `squadti.licoes`); as demais continuam valendo.
- **Limites e poda**: 2.000 lições, 25 tarefas por lição, 8 MiB. Acima disso o livro é compactado (forma canônica; a cópia anterior fica em `<arquivo>.1`) e, se preciso, as lições **pendentes** menos graves, menos recorrentes e mais antigas são podadas. Lição decidida (aprovada, rejeitada, desativada, promovida) nunca é podada; com o livro cheio delas, a ocorrência nova é ignorada com aviso. Com 25 tarefas guardadas a contagem para de crescer (reincidência só precisa de 2).
- Suposição: **um processo escritor** por livro (o orquestrador); threads são serializadas. Dois processos escrevendo ao mesmo tempo continuam sem perder linha (append), mas a compactação não é coordenada entre processos.

## Uso no prompt

`licoes_para_prompt(livro, agente, stack, limite_tokens=600)` devolve só lições `aprovada`, do papel e da stack, com destino `squad_prompt`, `squad_verificacao`, `doutrina_esclarecimento` ou `doutrina_regra_nova` (enquanto a verificação ou a regra não existem, a lição cobre o vão). `projeto`, `componente`, `squad_config` e `promovida` ficam fora. Ordem: severidade, depois recorrência. Limite em caracteres/4; a primeira linha é um cabeçalho dizendo que é dado de apoio, não instrução, e que a Doutrina TEC vence. Sem lição elegível devolve `""` (sem cabeçalho).

## Onde ligar (fora deste PR)

- **Orquestrador** (`nodes.py`/`graph.py`): ao concluir a tarefa, chamar `registrar(None, state["task_id"], stack_id, state["achados_agentes"])`; ao montar o prompt de cada papel, acrescentar `licoes_para_prompt(None, papel, stack_id)` depois da Doutrina. No nó do revisor, preencher `na_doutrina=False` nos achados que foram para `nao_verificados`.
- **API/painel** (`api.py` e painel do TudoIA): listar `listar("pendente")`, botões Aprovar/Rejeitar/Desativar que chamam `aprovar`/`rejeitar`/`desativar` com o usuário autenticado em `quem` (nunca um valor vindo do corpo da requisição); `promover` depois do PR na Doutrina; mostrar `triar` e `texto_da_licao` na tela para o humano ver exatamente o que entraria no prompt.
- **Evals**: `caso_de_regressao(licao)` gera o dict JSON do caso; a Squad grava os casos das lições aprovadas na pasta de evals.
- **Doutrina**: `exportar_propostas(None, pasta)` gera os rascunhos; o humano abre o PR no repositório da Doutrina (ECO-MAP-01: regra de engenharia pertence à Doutrina) e roda `validar`, `gerar` e os testes de lá.

## Limites conhecidos

- Os IDs `INJ-01..05`, `MAC-01..05`, `UI-01..06`, `HDR-*` e `QC-GAM-*` usam frase por prefixo, não por ID, porque o texto exato de cada um vive nos kits e não neste módulo. Se um kit precisar de frase específica, é uma linha em `_FRASE_POR_ID`.
- A triagem decide pelo ID, pela categoria e pela contagem; não lê o conteúdo do achado.
