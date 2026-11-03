"""
Adaptadores de stack (Stack Adapters): o que muda de uma tecnologia para outra, num lugar só.

O grafo, os portões (QA, revisão, AppSec, DevOps, release) e as regras de segurança são os mesmos para toda stack. O adaptador
diz só: como detectar que o projeto existe, que comandos rodam (build, testes, auditoria de dependências), onde cada papel pode
escrever, o que o modelo precisa saber da tecnologia e quais famílias da Doutrina não se aplicam (a família de arquitetura e a de
componentes são específicas de .NET/TEC.*).

Comandos vêm da configuração da stack (`stack_config.json`) quando declarados; o adaptador só dá o padrão. O modelo nunca escolhe
comando (IA-ORQ-07): quem escolhe é o adaptador ou o dono, e o executável precisa estar na lista de `execucao.py`.
"""
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from execucao import tem_projeto_dotnet

STACK_PADRAO = "dotnet"

_DEVOPS_EXIGE = (
    "Entregue também a higiene de entrega que o DevOps confere: `.gitignore` na raiz (cobrindo segredos, ambientes virtuais, caches e "
    "saídas de build), Dockerfile com imagem-base de tag FIXA (nunca `latest`, nunca sem tag), workflow em `.github/workflows/` com "
    "actions fixadas por SHA de commit, e nenhum `.env` com conteúdo (só `.env.example` com nomes de variável).")


def _python_projeto(raiz: Path) -> bool:
    return (raiz / "pyproject.toml").is_file()


STACKS: Dict[str, dict] = {
    "dotnet": {
        "nome": ".NET 10 (Clean Architecture, CQRS, EF Core, template TEC)",
        "detecta": tem_projeto_dotnet,
        "scaffold_command": "dotnet new tec-project -n {nome}",
        "build_command": "dotnet build --configuration Release",
        "test_command": "dotnet test --no-build --coverage --coverage-output-format cobertura",
        "audit_command": "dotnet list package --vulnerable --include-transitive",
        "audit_falha_se_texto": "has the following vulnerable packages",  # o comando sai 0 mesmo com vulnerabilidade
        "areas_backend": ("src/", "tests/"),
        "areas_dba": ("src/", "docs/dados/"),
        "log_tipo": "dotnet",
        "excluir_familias": (),
        "receita": ("Stack .NET: todo serviço nasce do template TEC (`dotnet new tec-project`), em Clean Architecture com CQRS. "
                    "Persistência por EF Core: uma IEntityTypeConfiguration por entidade, índices únicos filtrados e RowVersion; "
                    "a migration é gerada pela ferramenta (`dotnet ef migrations add`), nunca escrita à mão."),
    },
    "python": {
        "nome": "Python 3.12 (FastAPI, SQLAlchemy 2, Alembic, pytest, uv)",
        "detecta": _python_projeto,
        "scaffold_command": None,  # não há template: o desenvolvedor escreve o projeto
        "build_command": "uv sync",
        "test_command": "uv run pytest --cov=app --cov-branch --cov-report=xml",
        "audit_command": "uv run --with pip-audit pip-audit",
        "audit_falha_se_texto": None,  # pip-audit sai com código diferente de 0 quando acha vulnerabilidade
        "areas_backend": ("app/", "tests/", "migrations/", "pyproject.toml", "uv.lock", "alembic.ini", "Dockerfile", ".dockerignore",
                          ".gitignore", ".env.example", ".github/workflows/"),
        "areas_dba": ("app/", "migrations/", "docs/dados/"),
        "log_tipo": "python",
        "excluir_familias": ("arquitetura", "componentes"),  # específicas de .NET/TEC.*
        "receita": ("Stack Python: projeto em `pyproject.toml` (gerenciado por uv, Python 3.12, dependências com versão mínima), pacote "
                    "`app/` em camadas (api → application → domain; infrastructure implementa as portas do domain; domain não importa "
                    "framework), FastAPI com Pydantic v2 nas bordas, SQLAlchemy 2 (async) e Alembic para migrations, erros de negócio "
                    "como tipos nomeados mapeados num envelope de erro único, logs estruturados, timeouts explícitos em toda chamada "
                    "externa. Testes em `tests/` com pytest (unidade, integração da API com TestClient e casos adversariais: entrada "
                    "inválida, limites, autorização). Cobertura Cobertura XML (`pytest --cov=app --cov-branch --cov-report=xml`). "
                    + _DEVOPS_EXIGE),
    },
}

# O que `target_stack` pode declarar para escolher a tecnologia do backend; o CHEFE também grava `stack_id` no estado.
APELIDOS = {"csharp": "dotnet", "c#": "dotnet", "dotnet": "dotnet", ".net": "dotnet", "python": "python", "fastapi": "python"}


class StackDesconhecida(RuntimeError):
    pass


def resolver(state: Optional[dict]) -> str:
    """Id da stack do backend: `stack_id` do estado (decisão do CHEFE) > linguagem do `target_stack.backend` > .NET."""
    estado = state or {}
    bruto = estado.get("stack_id")
    if not bruto:
        bruto = ((estado.get("target_stack") or {}).get("backend") or {}).get("language") or STACK_PADRAO
    nome = APELIDOS.get(str(bruto).strip().lower())
    if nome is None:
        raise StackDesconhecida(f"stack '{bruto}' não suportada; use uma de {sorted(STACKS)}")
    return nome


def adaptador(state: Optional[dict]) -> dict:
    return STACKS[resolver(state)]


def comando(state: Optional[dict], chave: str) -> Optional[str]:
    """Comando da stack: o declarado em `target_stack.backend` vence; senão o padrão do adaptador."""
    declarado = ((state or {}).get("target_stack") or {}).get("backend", {}).get(chave)
    return declarado if declarado else adaptador(state).get(chave)


def projeto_gerado(state: Optional[dict], raiz: Path) -> bool:
    detecta: Callable[[Path], bool] = adaptador(state)["detecta"]
    return bool(detecta(raiz))


def areas(state: Optional[dict], papel: str) -> Tuple[str, ...]:
    return tuple(adaptador(state)["areas_" + papel])


def familias_excluidas(state: Optional[dict]) -> Tuple[str, ...]:
    return tuple(adaptador(state)["excluir_familias"])
