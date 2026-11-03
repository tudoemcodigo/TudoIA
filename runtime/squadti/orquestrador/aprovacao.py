"""
Aprovação humana amarrada ao CONTEÚDO aprovado.

Um `sim` vale para aquele texto, não para o nome do arquivo: se o arquivo mudar depois da aprovação (uma nova tentativa, uma
reescrita), a aprovação deixa de valer e o nó seguinte recusa. Vale para a especificação (antes da arquitetura) e para o pacote
de verificações do release (relatórios, revisão e documentação que o humano viu).
"""
import hashlib
from pathlib import Path
from typing import List, Optional

from execucao import caminho_seguro


class AprovacaoInvalida(RuntimeError):
    """A aprovação não existe, não tem hash ou o conteúdo mudou depois dela."""


def hash_bytes(dados: bytes) -> str:
    # fim de linha normalizado: o mesmo texto no Windows e no Linux dá o mesmo hash
    return hashlib.sha256(dados.replace(b"\r\n", b"\n")).hexdigest()


def hash_arquivo(raiz: Path, relativo: str) -> str:
    destino = caminho_seguro(raiz, relativo)
    try:
        return hash_bytes(destino.read_bytes())
    except OSError as e:
        raise AprovacaoInvalida(f"não consegui ler {relativo} para conferir a aprovação: {e}") from e


def arquivos_do_pacote(state: dict) -> List[str]:
    """Arquivos que o humano revisa antes de aprovar o release, na ordem fixa."""
    chaves = ("business_spec_file", "technical_prd_file", "openapi_file", "qa_report_file", "review_file",
              "security_report_file", "devops_report_file", "docs_file")
    return [state[c] for c in chaves if state.get(c)]


def hash_do_pacote(raiz: Path, state: dict) -> str:
    """Hash dos hashes (caminho + hash de cada arquivo do pacote). Arquivo ausente entra como 'ausente': muda o hash do mesmo jeito."""
    partes = []
    for rel in arquivos_do_pacote(state):
        try:
            h = hash_arquivo(raiz, rel)
        except AprovacaoInvalida:
            h = "ausente"
        partes.append(f"{rel}:{h}")
    return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()


def conferir(atual: Optional[str], aprovado: Optional[str], rotulo: str) -> None:
    if not aprovado:
        raise AprovacaoInvalida(f"{rotulo}: a aprovação não registrou o hash do conteúdo aprovado")
    if atual != aprovado:
        raise AprovacaoInvalida(f"{rotulo}: o conteúdo mudou depois da aprovação (hash diferente); aprove de novo o texto atual")
