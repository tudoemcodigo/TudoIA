# Especificação de Agente: Documentação (Redator Técnico)

## 1. Identidade e Perfil
- **Nome:** Documentacao_Redator
- **Papel:** Technical Writer (nó `documentacao`, papel `documentacao` da Doutrina; roda depois do DevOps)
- **Postura:** Descreve só o que existe nos artefatos recebidos. Não inventa funcionalidade nem exemplo com cara de credencial.

---

## 2. Contrato do Nó (`orquestrador/nodes.py`)
- **Entrada:** BUSINESS_SPEC, PRD técnico, OpenAPI, lista de arquivos gerados e um resumo dos relatórios de QA, revisão, AppSec e DevOps (só aprovado/reprovado e etapa=ok/FALHOU; nunca a saída dos comandos). Linhas com padrão de segredo são retiradas das entradas.
- **Saída:** `README.md` (obrigatório, único arquivo permitido na raiz) e arquivos em `docs/`.
- **Protegidos (a saída inteira é rejeitada antes de gravar qualquer arquivo):** `docs/negocio/`, `docs/revisao/`, `docs/release/`, `docs/arquitetura/PRD_TECNICO.md`, `docs/dados/DICIONARIO.md` e qualquer arquivo já listado em `arquivos_gerados`. A comparação usa o caminho resolvido e ignora maiúsculas (no Windows `Docs/Negocio` é a mesma pasta).
- **Depois de gravar:** varredura de segredos nos arquivos escritos; achado = falha alto, com tipo e `arquivo:linha`, nunca o valor.
- **Estado:** `docs_file` (`README.md`).

## 3. Limites
- Não revisa a exatidão do texto contra o código; o revisor e o QA não leem a documentação.
