"""
Esquema de Estado da Squad de TI para LangGraph com Fonte da Verdade Corporativa.
"""
from typing import Annotated, TypedDict, List, Dict, Optional, Any


def unir_listas(atual: Optional[List[str]], novo: Optional[List[str]]) -> List[str]:
    """Reducer: backend e frontend rodam em paralelo e gravam `arquivos_gerados` no mesmo passo; une sem duplicar."""
    return list(dict.fromkeys([*(atual or []), *(novo or [])]))


RESET = "__reset__"  # primeiro item de uma atualização: zera a lista (só `continuar` usa, para limpar a trilha de estagnação)


def somar_listas(atual: Optional[List[Any]], novo: Optional[List[Any]]) -> List[Any]:
    """Reducer de trilha (auditoria, mensagens, assinaturas): só acrescenta, nunca reescreve o que já foi registrado."""
    if novo and novo[0] == RESET:
        return list(novo[1:])
    return [*(atual or []), *(novo or [])]


def ultimo_valor(atual: Any, novo: Any) -> Any:
    """Reducer: quando dois nós paralelos gravam o mesmo campo escalar, vale o último; o campo é só informativo."""
    return novo


class SquadState(TypedDict):
    # Identificação do Projeto e Configuração da Fonte da Verdade
    task_id: str
    project_name: str
    target_stack: Dict[str, Any]
    architecture_source_path: str  # pasta da Doutrina TEC; a variável DOUTRINA_TEC tem precedência
    workspace_dir: str             # tudo que a tarefa gera fica aqui (workspace/<task_id>)

    # Modelo desta tarefa (perfil do gateway) e consentimento explícito para modelo que pode sair da máquina
    modelo: Optional[str]
    consentimento_nuvem: Optional[bool]

    # CHEFE (canal único do usuário), plano e stack decididos por ele
    plano: Optional[Dict[str, Any]]        # tamanho, stack, precisa_banco, precisa_frontend, riscos (docs/chefe/PLANO.json)
    stack_id: Optional[str]                # 'dotnet' | 'python' (adaptador de stack)
    doutrina_excluir: Optional[List[str]]  # famílias da Doutrina que a stack escolhida não usa
    mensagens: Annotated[List[Dict[str, Any]], somar_listas]   # conversa usuário <-> CHEFE (de, para, texto, em)
    observacoes_usuario: Annotated[List[str], somar_listas]    # instruções livres do usuário (DADO para os agentes, já sanitizadas)

    # Configuração e controle da execução
    agentes_cfg: Optional[Dict[str, Any]]  # modelo/temperatura por agente, modo de revisão e orçamento (cópia da config ao iniciar)
    orcamento: Optional[Dict[str, Any]]    # tetos da tarefa: tokens, tempo_s, chamadas
    auditoria: Annotated[List[Dict[str, Any]], somar_listas]   # um registro por nó: duração, chamadas, tokens, modelo, hash de prompt
    assinaturas_erro: Annotated[List[str], somar_listas]       # assinatura das falhas seguidas (detecção de estagnação)
    achados_agentes: Annotated[List[Dict[str, Any]], somar_listas]  # achados estruturados dos agentes (alimentam o livro de lições)
    rodadas_runtime: Optional[int]         # voltas da validação em execução (macaco, hacker, carga) com o desenvolvimento
    rodadas_senior: Optional[int]          # voltas da revisão sênior com o desenvolvimento
    rodadas_manutencao: Optional[int]      # voltas do teste de manutenibilidade com a documentação
    validacao_executada: Optional[bool]    # False = o sistema NÃO foi validado em execução (Docker ausente ou desligado)
    validacao_motivo: Optional[str]
    hacker_passed: Optional[bool]
    macaco_passed: Optional[bool]
    carga_passed: Optional[bool]
    senior_passed: Optional[bool]
    manutencao_passed: Optional[bool]
    hacker_report_file: Optional[str]
    macaco_report_file: Optional[str]
    carga_report_file: Optional[str]
    senior_report_file: Optional[str]
    manutencao_report_file: Optional[str]
    docs_proprios: Annotated[List[str], unir_listas]       # arquivos que a documentação escreveu (ela pode reescrevê-los)
    feedback_manutencao: Optional[str]     # lacunas que o teste de manutenibilidade devolveu à documentação
    escalada: Optional[str]                # motivo de uma parada que exige humano (estagnação, orçamento, saída inválida)
    stack_fixa: Optional[bool]             # True = o usuário escolheu a stack; o CHEFE não troca
    feedback_chefe: Optional[str]          # pendências que o CHEFE devolveu ao analista (critério de pronto)
    rodadas_gate: Optional[int]            # quantas vezes o CHEFE devolveu a especificação

    # Aprovações amarradas ao conteúdo
    business_spec_hash: Optional[str]
    release_gate_hash: Optional[str]

    # Rastreabilidade: versão da Doutrina usada. Mudou no meio da tarefa = a tarefa aborta.
    doutrina_versao: Optional[str]
    doutrina_hash: Optional[str]
    doutrina_familias: Optional[List[str]]  # força as mesmas famílias em todos os papéis; omitido = perfil de cada papel (DOUTRINA_FAMILIAS tem precedência)

    # Interação com o Usuário e Elicitação
    user_initial_briefing: str
    interview_questions: List[str]
    interview_answers: List[str]
    business_spec_approved: bool

    # Artefatos em Disco (caminhos relativos ao workspace)
    business_spec_file: Optional[str]
    technical_prd_file: Optional[str]
    openapi_file: Optional[str]
    backend_dir: Optional[str]
    frontend_dir: Optional[str]
    qa_report_file: Optional[str]
    security_report_file: Optional[str]
    devops_report_file: Optional[str]
    review_file: Optional[str]
    docs_file: Optional[str]
    release_notes_file: Optional[str]
    ultima_versao: Optional[str]  # última versão SemVer já publicada, se conhecida; o release nunca inventa tag
    arquivos_gerados: Annotated[List[str], unir_listas]

    # Execução e Auto-Cura
    current_phase: Annotated[str, ultimo_valor]
    iteration_count: int
    last_error_log: Optional[str]
    falha_origem: Optional[str]  # 'backend' | 'frontend' | None: quem o QA responsabiliza pela falha (define a rota de correção)
    tests_passed: bool
    review_passed: bool
    security_passed: bool
    devops_passed: bool
    release_approved: bool  # aprovação humana explícita; o nó release recusa rodar sem ela (o interrupt não basta)
