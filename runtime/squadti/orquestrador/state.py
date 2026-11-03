"""
Esquema de Estado da Squad de TI para LangGraph com Fonte da Verdade Corporativa.
"""
from typing import Annotated, TypedDict, List, Dict, Optional, Any


def unir_listas(atual: Optional[List[str]], novo: Optional[List[str]]) -> List[str]:
    """Reducer: backend e frontend rodam em paralelo e gravam `arquivos_gerados` no mesmo passo; une sem duplicar."""
    return list(dict.fromkeys([*(atual or []), *(novo or [])]))


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
