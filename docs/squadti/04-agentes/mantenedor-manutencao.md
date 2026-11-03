---
titulo: Perfil de agente da SquadTI - Mantenedor (eu daqui a 1 ano)
tipo: referencia
dono: TudoIA (mantenedor do repositório)
status: vigente
classificacao: publico
verificado-em: 2026-11-03
---

[🏠 TudoIA](../../../README.md) › [📚 Documentação](../../README.md) › [🧩 SquadTI (design)](../00-visao-geral-e-arquitetura.md) › 🤖 Mantenedor

# 🤖 Mantenedor (eu daqui a 1 ano)

> Público-alvo: quem mantém ou estende a SquadTI. Responde: como a Squad testa se um desenvolvedor novo se orienta no sistema gerado só com a documentação, e o que isso reprova. Nó `mantenedor` (usa modelo, nota por conferência em código), depois da documentação. Contexto em [catálogo de agentes](../01-catalogo-de-agentes.md); componente em execução: [squadti.md](../../componentes/squadti.md).

## 1. Identidade e Perfil
- **Nome:** Mantenedor
- **Papel:** leitor "a frio": abriu o repositório numa segunda-feira e só tem o `README.md`, a documentação e a lista de arquivos.
- **Postura:** a nota **não é a opinião do modelo**. Ele aponta onde mexeria; o código confere se os arquivos existem e se são os certos.

---

## 2. Contrato do Nó (`orquestrador/qualidade.py`)
- **Posição no grafo:** depois de `documentacao`. Agente configurável: `mantenedor`. Chamada sem núcleo nem regras da Doutrina.
- **Itens de documentação** (existência por busca de texto em `README.md` e `docs/`, sem os relatórios da própria Squad): como rodar, como testar, configuração, arquitetura, decisões, e a existência de `.env.example`. Precisa de pelo menos 80% (`MINIMO_DOCS`).
- **Três mudanças típicas**, com a resposta certa calculada por busca no código: adicionar um campo opcional à primeira entidade do contrato (`campo`), mudar a regra que produz o primeiro erro de negócio nomeado da especificação (`regra`) e descobrir onde a autenticação/autorização é aplicada (`autorizacao`). Mudança sem resposta calculável é descartada.
- **O modelo** recebe a árvore de arquivos (até 300 entradas), a documentação (até 8.000 caracteres por arquivo e 30.000 no total, sem linhas com padrão de segredo) e os pedidos, e responde com um JSON (`entendimento`, `confusoes`, `respostas` por pedido) que o nó lê da resposta (o arquivo `docs/manutencao/RESPOSTAS.json` do prompt não é gravado). Resposta inutilizável conta como mudança não localizada.
- **Acerto de uma mudança:** o modelo citou pelo menos um arquivo da resposta certa e a maioria dos arquivos citados existe (nada inventado).
- **Aprovação:** documentação ≥ 80% **e** pelo menos 2 acertos (`MINIMO_DRILLS`; menos se houver menos de 2 mudanças calculáveis).
- **Saída:** `docs/manutencao/AVALIACAO_MANUTENIBILIDADE.json`.
- **Estado:** `manutencao_passed`, `manutencao_report_file`, `rodadas_manutencao`, `feedback_manutencao`.
- **Rota:** reprovado volta à `documentacao` com a lista de lacunas (itens ausentes, mudanças não localizadas, até 3 confusões relatadas); na 2ª reprovação escala. Aprovado segue à pausa do release.

## 3. Limites
- Mede orientação pela documentação, não a qualidade da explicação nem a correção do texto.
- A busca de itens de documentação é por palavra-chave: texto que cita o assunto sem explicá-lo passa.
- Depende de contrato OpenAPI e de especificação com erro nomeado para montar as duas primeiras mudanças.

---

[🏠 README](../../../README.md) · ⬅️ [Carga (DevOps/SRE)](carga-sre.md) · [Visão geral](../00-visao-geral-e-arquitetura.md) ➡️
