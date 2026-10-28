"""Importação de skill de um repositório do GitHub para a governança (executa `npx skills add`, só para admin)."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .erros import ErroApi

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
REPO_GITHUB = re.compile(r"https://github\.com/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/?")
# Pacote npm que baixa a skill: versão fixa, para uma publicação nova não rodar com o painel de admin sem revisão.
VERSAO_SKILLS_CLI = "1.7.4"
PRAZO_S = 90


def interpretar_pedido(comando: str | None, repo_url: str | None, skill_nome: str | None) -> tuple[str, str]:
    """(url do repositório, nome da skill) validados. Aceita o comando `npx skills add ...` colado pelo usuário."""
    repo_url = (repo_url or "").strip()
    skill_nome = (skill_nome or "").strip()
    if comando:
        cmd = comando.strip()
        m_skill = re.search(r"--skill\s+([a-zA-Z0-9_-]+)", cmd)
        if m_skill and not skill_nome:
            skill_nome = m_skill.group(1)
        m_url = re.search(r"(?:https?://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+|[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)", cmd)
        if m_url and not repo_url:
            repo_url = m_url.group(0)

    if not repo_url:
        raise ErroApi(422, "validacao", "URL do repositório ou comando não identificada", campo="repo_url")
    if not skill_nome or not ID.match(skill_nome):
        raise ErroApi(422, "validacao", "Nome da skill não identificado ou inválido (use letras, números e hífens)",
                      campo="skill_nome")
    if not repo_url.startswith(("http://", "https://")):
        repo_url = f"https://github.com/{repo_url}"
    # Só repositório do GitHub, sem nenhum caractere que o cmd.exe interprete: no Windows o npx é um .cmd, e o
    # Python não escapa argumento de .cmd para o cmd.exe (& | ^ % " viravam comando).
    if not REPO_GITHUB.fullmatch(repo_url):
        raise ErroApi(422, "validacao", "Use um repositório do GitHub: dono/repo ou https://github.com/dono/repo",
                      campo="repo_url")
    return repo_url, skill_nome


def comando_npx(repo_url: str, skill_nome: str) -> list[str]:
    npx_bin = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    return [npx_bin, "--yes", f"skills@{VERSAO_SKILLS_CLI}", "add", repo_url, "--skill", skill_nome, "-y"]


def _pasta_da_skill(base: Path, skill_nome: str) -> Path:
    candidatos = list(base.rglob("SKILL.md"))
    if not candidatos:
        raise ErroApi(422, "skill_invalida",
                      f"O repositório foi clonado, mas nenhum SKILL.md foi encontrado para '{skill_nome}'.")
    pasta = next((c.parent for c in candidatos if c.parent.name == skill_nome), candidatos[0].parent)
    # copytree segue link: uma skill com link para ~/.ssh traria as chaves para a governança e o sync as
    # espalharia para todos os clientes. Skill é Markdown e arquivos comuns; link é recusado.
    if any(p.is_symlink() for p in [pasta, *pasta.rglob("*")]):
        raise ErroApi(422, "skill_invalida", "A skill contém link simbólico; importação recusada.")
    return pasta


def importar(raiz: Path, trava, repo_url: str, skill_nome: str) -> Path:
    """Baixa a skill num diretório temporário e a instala em governanca/skills/<nome>. Devolve a pasta final.

    A cópia entra ao lado e troca a antiga no fim: falha no meio da cópia não apaga a skill que já existia."""
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            proc = subprocess.run(comando_npx(repo_url, skill_nome), cwd=temp_dir, capture_output=True, text=True,
                                  timeout=PRAZO_S)
        except subprocess.TimeoutExpired as e:
            raise ErroApi(408, "timeout", "Tempo limite excedido ao clonar repositório e importar skill") from e
        except Exception as e:
            raise ErroApi(500, "erro_execucao", f"Falha ao executar o comando de importação: {type(e).__name__}") from e
        if proc.returncode != 0:
            msg_erro = (proc.stderr or proc.stdout or "Código de retorno diferente de zero").strip()
            raise ErroApi(422, "falha_importacao", f"Erro no comando skills: {msg_erro[:500]}")

        origem = _pasta_da_skill(Path(temp_dir), skill_nome)
        destino = raiz / "governanca" / "skills" / skill_nome
        novo = raiz / "governanca" / f".skill-novo-{skill_nome}"   # fora de skills/: o catálogo não a enxerga
        with trava:
            shutil.rmtree(novo, ignore_errors=True)
            shutil.copytree(origem, novo)
            if destino.exists():
                shutil.rmtree(destino)
            novo.replace(destino)
    return destino
