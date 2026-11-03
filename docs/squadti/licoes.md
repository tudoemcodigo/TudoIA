---
titulo: Livro de Lições da SquadTI
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../README.md) › [📚 Documentação](../README.md) › 📖 Livro de Lições da SquadTI

# 📖 Livro de Lições da SquadTI

> Para quem mantém a SquadTI e para quem decide o que vira regra. Responde: como um achado de agente (hacker, macaco, revisor, Sênior Master, QA) vira prevenção no lugar certo, quais são os guardrails, o formato do livro e o que **ainda não está ligado** ao fluxo.
> Implementação: [`runtime/squadti/orquestrador/licoes.py`](../../runtime/squadti/orquestrador/licoes.py) (API pura: sem rede, sem modelo). Testes: `orquestrador/tests/test_licoes.py`.

## 📑 Sumário

- [🎯 Visão geral](#-visão-geral)
- [🚀 Uso](#-uso)
- [🌳 Árvore de decisão (`triar`)](#-árvore-de-decisão-triar)
- [🛡️ Segurança (guardrails)](#️-segurança-guardrails)
- [📒 O livro (arquivo)](#-o-livro-arquivo)
- [❌ Erros / diagnóstico](#-erros--diagnóstico)
- [🚧 O que ainda não está ligado](#-o-que-ainda-não-está-ligado)
- [❓ Perguntas frequentes](#-perguntas-frequentes)

## 🎯 Visão geral

O Livro de Lições transforma achados dos agentes em **prevenção no lugar certo** (prompt do papel, verificação determinística, esclarecimento ou regra nova da Doutrina, ajuste de configuração), para o mesmo erro não se repetir.

> [!IMPORTANT]
> **Estado em 2026-11-03:** `licoes.py` é uma **biblioteca isolada**. Nenhum nó, a API da Squad, o painel nem os evals a chamam hoje (conferido por busca em `runtime/squadti/orquestrador/`, `painel/` e `runtime/squadti/evals/`): o estado da tarefa já acumula os achados estruturados em `achados_agentes` (hacker, macaco e Sênior Master), mas ninguém os grava no livro, e não há tela para aprovar lições. O ciclo abaixo é o **contrato** da biblioteca e o que falta ligar está em [O que ainda não está ligado](#-o-que-ainda-não-está-ligado).

```text
achados_agentes ──registrar──▶ livro (JSONL) ──triar──▶ destino
                                   │                        │
                       lição PENDENTE (dedup por tarefa)    ▼
                                   │                 humano aprova/rejeita
                                   ▼                        │
                      (painel lista e decide: a ligar) ◀────┘
                                   │
              aprovada ──▶ licoes_para_prompt (prompt do papel)
                       ──▶ caso_de_regressao (evals)
                       ──▶ proposta_doutrina / exportar_propostas (se candidata)
                                   │
                       humano abre o PR na Doutrina ──▶ promover (estado promovida)
```

1. `registrar(livro, tarefa, stack, achados)` recebe os achados já estruturados (o formato de `achados_agentes`: `agente`, `id`, `severidade`, `categoria`, `endpoint`, `metodo`).
2. A lição nasce `pendente` e **não influencia nada** até um humano aprovar.
3. `triar(licao)` diz para onde vai a prevenção; `aprovar`, `rejeitar`, `desativar` e `promover` registram quem e quando.
4. Aprovada, a lição entra no prompt do papel responsável (`licoes_para_prompt`), vira caso de regressão (`caso_de_regressao`) e, se candidata, vira proposta de Doutrina em arquivo.

## 🚀 Uso

Chamadas da biblioteca (Python, a partir de `runtime/squadti/orquestrador`; `livro=None` usa o arquivo padrão):

| Função | O que faz |
|---|---|
| `registrar(livro, tarefa, stack, achados)` | Acrescenta as ocorrências. Devolve `{registradas, ignoradas, avisos}`. Ignora `BAIXO`, severidade inválida e achado malformado |
| `listar(estado=None, livro=None)` · `obter(licao_id, livro=None)` | Lições (com `contagem`, `severidade_max`, `tarefas`, `evidencia_hash`, `historico`) |
| `aprovar` · `rejeitar` · `desativar` · `promover` `(licao_id, quem, livro=None)` | Transições de estado; `quem` é obrigatório. `promover` exige `candidata_doutrina` (senão `NaoCandidata`) |
| `triar(licao, ids_doutrina=None)` | `{destino, motivo, papel_alvo, candidata_doutrina}` |
| `texto_da_licao(licao)` | O texto exato que iria ao prompt (para o humano ver antes de aprovar) |
| `licoes_para_prompt(livro, agente, stack, limite_tokens=600)` | Bloco para o prompt de um papel |
| `caso_de_regressao(licao)` | Dict JSON de um caso de regressão |
| `proposta_doutrina(licao, ids_doutrina=None)` · `exportar_propostas(livro, pasta, ids_doutrina=None)` | Rascunho Markdown de regra/ADR para a Doutrina |

Exemplo mínimo:

```python
import licoes
licoes.registrar(None, "TASK-001", "python", state["achados_agentes"])
for l in licoes.listar("pendente"):
    print(l["id"], licoes.triar(l)["destino"], licoes.texto_da_licao(l))
licoes.aprovar("L-<id>", "<usuario-autenticado>")
bloco = licoes.licoes_para_prompt(None, "backend", "python")
```

Variável: `SQUADTI_LICOES_ARQUIVO` (padrão `licoes.jsonl`, relativo à pasta de trabalho; na imagem, `/dados`).

## 🌳 Árvore de decisão (`triar`)

Avaliada nesta ordem; a primeira que casar vale. Resultado: `{destino, motivo, papel_alvo, candidata_doutrina}`.

| # | Condição | Destino |
|---|---|---|
| 1 | categoria `componente` (defeito de `TEC.*`) | `componente` (pedido formal ao repositório do componente, ECO-MAP-02) |
| 2 | categoria `projeto` ou `regra-de-negocio` | `projeto` (spec/ADR do projeto gerado; nunca generaliza) |
| 3 | categoria `comportamento`, `formato` ou `comando` | `squad_config` |
| 4 | ID do kit de ataque (`AUTH`, `INJ`, `ERR`, `CORS`, `MASS`, `LIM`, `HDR`, `MET`, `RATE`, `IDOR`), ID `QC-*` ou categoria detectável por código (`segredos`, `dockerfile`, `complexidade`, `duplicacao`) | `squad_verificacao` (verificação determinística nova mais regressão) |
| 5 | ID no formato da Doutrina (`FAM-AREA-NN`, família conhecida) que **existe** na Doutrina: 1 tarefa | `squad_prompt` |
| 5b | idem, em **2 ou mais tarefas** (reincidência com regra citada) | `doutrina_esclarecimento` |
| 6 | sem regra existente (ID de família conhecida que a Doutrina não tem, ou ID fora do padrão) e com família sugerida (pela categoria ou pelo ID) | `doutrina_regra_nova` |
| 7 | resto | `squad_prompt` |

"Existe na Doutrina" vem de `triar(licao, ids_doutrina)` (passe `doutrina_tec.ids_existentes(state)`); sem esse conjunto vale a marca `na_doutrina` que o achado trouxe; sem nenhuma das duas presume-se que existe.

**Papel alvo** (lista): kit de ataque -> `backend`; `MAC-*` e `UI-*` -> `frontend`; `QC-*` -> `backend` e `frontend`; ID da Doutrina -> papéis da família (SEC -> backend/frontend, DAD -> dba, FRT -> frontend, DOC -> documentacao, REQ -> analista, ARQ/CMP/IA -> backend, ECO -> arquiteto); senão pela família da categoria; senão `backend`.

**`candidata_doutrina`**: o destino é `doutrina_esclarecimento` ou `doutrina_regra_nova` **e** há reincidência: `>= 2` tarefas distintas, ou 1 achado CRITICO de segurança. Verificação de código e prompt nunca são candidatos à Doutrina.

## 🛡️ Segurança (guardrails)

1. **Texto nunca vem de prosa de modelo.** O livro só aceita campos estruturados validados: `agente` (vocabulário fechado: `hacker`, `macaco`, `revisor`, `senior`, `qa`, `qualidade`, `appsec`, `devops`, `chefe`, `analista`, `arquiteto`, `dba`, `backend`, `frontend`, `documentacao`) e `categoria` de vocabulário fechado (categoria fora da lista vira `outra`), `id` em formato fixo (`^[A-Z]{2,5}(-[A-Z]{2,5})?-\d{2,3}$`), severidade, `stack` e `tarefa` em formato restrito. Tudo passa por `entrada.sanitizar`. `endpoint` e `metodo` viram um hash de 16 hex; o texto deles não é gravado. O texto da lição sai de modelos fixos de frase (tabela por ID, depois por prefixo, depois por família/categoria, depois genérico), interpolando só contagem e ID validado, com no máximo 300 caracteres. A leitura do disco **revalida** cada linha (inclusive a impressão digital): livro adulterado à mão não injeta texto.
2. **Aprovação humana explícita.** Estados: `pendente`, `aprovada`, `rejeitada`, `desativada`, `promovida`. Transições permitidas: `pendente -> aprovada|rejeitada`, `aprovada -> desativada|promovida`, `desativada -> aprovada`. `rejeitada` e `promovida` são finais (reincidência não reabre decisão humana). `quem` é obrigatório, sanitizado e limitado a 80 caracteres. O histórico guarda de, para, quem, quando e o hash das evidências vistas na decisão.
3. **Origem rastreável sem conteúdo sensível.** Cada lição guarda tarefas, contagem, primeira e última ocorrência e `evidencia_hash` (hash do conjunto tarefa, evidência, severidade). Nunca prompt, resposta, endpoint nem segredo.
4. **Doutrina só por proposta.** `proposta_doutrina` recusa (`NaoCandidata`) lição sem reincidência; `exportar_propostas` grava `proposta-<id>.md` só para candidatas aprovadas/promovidas e **não sobrescreve** arquivo existente (pode ter edição humana). Nada aqui escreve na Doutrina. O ID da regra é placeholder `<FAMILIA>-<AREA>-<NN>`; o humano escolhe o definitivo.
5. **Dedup por impressão digital** (`agente + id + categoria + stack`). A contagem é de **tarefas distintas**: o mesmo achado repetido na mesma tarefa conta 1 (a maior severidade prevalece) e nem cresce o arquivo. BAIXO, severidade inválida e achado malformado são ignorados.
6. **O prompt trata a lição como dado.** `licoes_para_prompt` devolve só lições `aprovada`, do papel e da stack, com destino `squad_prompt`, `squad_verificacao`, `doutrina_esclarecimento` ou `doutrina_regra_nova` (enquanto a verificação ou a regra não existem, a lição cobre o vão). `projeto`, `componente`, `squad_config` e `promovida` ficam fora. Ordem: severidade, depois recorrência. Limite em caracteres/4; a primeira linha é um cabeçalho dizendo que é dado de apoio, não instrução, e que a Doutrina TEC vence. Sem lição elegível devolve `""` (sem cabeçalho).

## 📒 O livro (arquivo)

- JSONL append-only; caminho: argumento `livro` > `SQUADTI_LICOES_ARQUIVO` > `licoes.jsonl`. Duas linhas: `o` (ocorrência por lição e tarefa) e `x` (transição de estado). O estado é sempre recalculado relendo o arquivo.
- Escrita: um único `write` em `O_APPEND` com `fsync`, sob trava de processo. Se o arquivo terminou sem quebra de linha (queda no meio da escrita), a próxima escrita começa por uma, sem colar na linha quebrada.
- Linha quebrada, maior que 2 KiB ou inválida: **ignorada com aviso** (logger `squadti.licoes`); as demais continuam valendo.
- **Limites e poda**: 2.000 lições, 25 tarefas por lição, 8 MiB. Acima disso o livro é compactado (forma canônica; a cópia anterior fica em `<arquivo>.1`) e, se preciso, as lições **pendentes** menos graves, menos recorrentes e mais antigas são podadas. Lição decidida (aprovada, rejeitada, desativada, promovida) nunca é podada; com o livro cheio delas, a ocorrência nova é ignorada com aviso. Com 25 tarefas guardadas a contagem para de crescer (reincidência só precisa de 2).
- Suposição: **um processo escritor** por livro (o orquestrador); threads são serializadas. Dois processos escrevendo ao mesmo tempo continuam sem perder linha (append), mas a compactação não é coordenada entre processos.

## ❌ Erros / diagnóstico

| Sintoma | Causa | Ação |
|---|---|---|
| `TransicaoInvalida` | Transição fora da tabela (por exemplo aprovar uma `rejeitada`) ou `quem` vazio | Confira o estado atual com `obter`; decisão final não se desfaz |
| `LicaoInexistente` | ID fora do formato `L-<16 hex>` ou ausente do livro | Pegue o ID de `listar` |
| `NaoCandidata` (em `promover`/`proposta_doutrina`) | Destino não é a Doutrina ou sem reincidência (2 tarefas, ou 1 CRITICO de segurança) | Deixe a lição no prompt; espere reincidência |
| `registrar` devolve `registradas: 0` com aviso | Tarefa ou stack em formato inválido, ou `achados` que não é lista | Veja `avisos` |
| Aviso "linha ignorada" no log `squadti.licoes` | Linha quebrada, maior que 2 KiB ou adulterada | Inspecione o arquivo; as demais lições seguem valendo |
| Ocorrência nova ignorada com o livro cheio | 2.000 lições decididas, nada a podar | Desative ou arquive lições antigas (a compactação não remove decididas) |

## 🚧 O que ainda não está ligado

- **Orquestrador** (`nodes.py`/`graph.py`): ao concluir a tarefa, chamar `registrar(None, state["task_id"], stack_id, state["achados_agentes"])`; ao montar o prompt de cada papel, acrescentar `licoes_para_prompt(None, papel, stack_id)` depois da Doutrina. No nó do revisor, preencher `na_doutrina=False` nos achados que foram para `nao_verificados`.
- **Descasamento a corrigir ao ligar:** `validacao.py` grava os achados do macaco com `agente: "qa_macaco"` (`_estruturar("qa_macaco", ...)`), mas o vocabulário fechado do livro tem `macaco`; hoje `registrar` ignoraria todos eles ("agente desconhecido"). Várias categorias dos kits também não estão no vocabulário do livro e viram `outra` (por exemplo `robustez`, `interface`, `disponibilidade`, `validação`, `vazamento de informação`, `cabeçalhos`, `atribuição em massa`, `controle de acesso`, `limite de taxa`); isso não muda a triagem dos IDs do kit (decidem pelo prefixo), mas muda a impressão digital e o papel alvo quando o ID não é de kit.
- **API/painel** (`api.py` e painel do TudoIA): listar `listar("pendente")`, botões Aprovar/Rejeitar/Desativar que chamam `aprovar`/`rejeitar`/`desativar` com o usuário autenticado em `quem` (nunca um valor vindo do corpo da requisição); `promover` depois do PR na Doutrina; mostrar `triar` e `texto_da_licao` na tela para o humano ver exatamente o que entraria no prompt.
- **Evals**: `caso_de_regressao(licao)` gera um dict com `versao`, `id` (`reg-L-...`), `stack`, `origem`, `papel_alvo`, `briefing` mínimo e `verificador`. Esse formato **não é** o de `evals/casos/*.json` (que exige `respostas_da_entrevista`, `limites` e o resto, ver [Evals](evals.md)): falta um adaptador antes de o driver rodar um caso de regressão.
- **Doutrina**: `exportar_propostas(None, pasta)` gera os rascunhos; o humano abre o PR no repositório da Doutrina (ECO-MAP-01: regra de engenharia pertence à Doutrina) e roda `validar`, `gerar` e os testes de lá.

## ❓ Perguntas frequentes

**Os IDs dos kits têm frase própria?** Os IDs `INJ-01..05`, `MAC-01..05`, `UI-01..06`, `HDR-*` e `QC-GAM-*` usam frase por prefixo, não por ID, porque o texto exato de cada um vive nos kits e não neste módulo. Se um kit precisar de frase específica, é uma linha em `_FRASE_POR_ID`.

**A triagem lê o conteúdo do achado?** Não: decide pelo ID, pela categoria e pela contagem.

**Uma lição aprovada muda o comportamento da Squad hoje?** Não: sem a ligação acima, nada chama `licoes_para_prompt`.

---

[🏠 README](../../README.md) · ⬅️ [Evals](evals.md)
