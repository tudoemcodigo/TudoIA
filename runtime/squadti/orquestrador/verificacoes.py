"""
Verificações estáticas e determinísticas do workspace para o nó `devops`: sem modelo, sem rede, sem executar nada.

Cada verificação devolve uma etapa no mesmo formato do relatório de segurança
(`etapa`, `comando`, `codigo`, `saida_final`, `achados`). Os achados trazem arquivo:linha e o motivo; nunca o conteúdo
do arquivo (um `.env` é reportado só pelo nome). É um filtro de higiene, não substitui linter de pipeline nem scanner de imagem.
"""
import fnmatch
import os
import re
from pathlib import Path
from typing import Iterator, List

from segredos import IGNORAR_DIRS

MAX_ARQUIVOS = 20_000
MAX_BYTES = 1_000_000
GITIGNORE_OBRIGATORIO = ("bin", "obj", "node_modules", ".env")
CI_GITHUB = {"github", "github-actions", "github_actions", "githubactions"}

_RE_SHA1 = re.compile(r"^[0-9a-fA-F]{40}$")
_RE_DIGEST = re.compile(r"@sha256:[0-9a-fA-F]{64}$")
_RE_USES = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(?P<v>.+?)\s*$")
_RE_FROM = re.compile(r"^\s*FROM\s+(?P<resto>.+)$", re.IGNORECASE)
_RE_ARG = re.compile(r"^\s*ARG\s+(?P<nome>[A-Za-z_][A-Za-z0-9_]*)(?:=(?P<valor>.*))?\s*$", re.IGNORECASE)
_RE_VAR = re.compile(r"\$\{(?P<a>[A-Za-z_][A-Za-z0-9_]*)(?::?-(?P<d>[^}]*))?\}|\$(?P<b>[A-Za-z_][A-Za-z0-9_]*)")


def _etapa(nome: str, problemas: List[dict], ok_msg: str) -> dict:
    msg = "; ".join(f"{p['arquivo']}:{p['linha']} {p['motivo']}" if p.get("linha") else f"{p['arquivo']} {p['motivo']}"
                    for p in problemas[:20])
    return {"etapa": nome, "comando": "", "codigo": 1 if problemas else 0, "achados": problemas[:50],
            "saida_final": msg if problemas else ok_msg}


def percorrer(raiz: Path) -> Iterator[Path]:
    """Arquivos do workspace sem seguir links e sem entrar em pastas de dependência/saída. Levanta OverflowError se passar
    do limite (falha fechado: varredura incompleta não aprova)."""
    raiz = raiz.resolve()
    n = 0
    for dirpath, dirnames, nomes in os.walk(raiz, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORAR_DIRS and not Path(dirpath, d).is_symlink())
        for nome in sorted(nomes):
            p = Path(dirpath, nome)
            if p.is_symlink():
                continue
            n += 1
            if n > MAX_ARQUIVOS:
                raise OverflowError(f"mais de {MAX_ARQUIVOS} arquivos: varredura incompleta")
            yield p


def _rel(raiz: Path, p: Path) -> str:
    return p.relative_to(raiz.resolve()).as_posix()


def _linhas(p: Path) -> List[str]:
    if p.stat().st_size > MAX_BYTES:
        raise OSError("arquivo grande demais para verificar")
    return p.read_text(encoding="utf-8", errors="replace").splitlines()


def _workflows(raiz: Path) -> List[Path]:
    base = raiz.resolve() / ".github"
    if not base.is_dir() or base.is_symlink():
        return []
    achados = []
    for sub in ("workflows", "actions"):
        pasta = base / sub
        if pasta.is_dir() and not pasta.is_symlink():
            achados += [p for p in percorrer(pasta) if p.suffix.lower() in (".yml", ".yaml")]
    return achados


def verificar_ci(raiz: Path, stack: dict) -> dict:
    ci = str(((stack or {}).get("infra") or {}).get("ci") or "").strip().lower()
    if not ci:
        return {"etapa": "ci-workflow", "comando": "", "codigo": 0,
                "saida_final": "não configurado (stack.infra.ci ausente): nada verificado"}
    if ci not in CI_GITHUB:
        return {"etapa": "ci-workflow", "comando": "", "codigo": 0,
                "saida_final": f"CI '{ci}' declarado, mas este nó só verifica GitHub Actions: nada verificado"}
    base = raiz.resolve() / ".github" / "workflows"
    existentes = [p for p in (percorrer(base) if base.is_dir() and not base.is_symlink() else [])
                  if p.suffix.lower() in (".yml", ".yaml") and p.stat().st_size > 0]
    if not existentes:
        return _etapa("ci-workflow", [{"arquivo": ".github/workflows/", "linha": 0,
                                       "motivo": "CI GitHub declarado e nenhum workflow (.yml/.yaml) encontrado"}], "")
    return {"etapa": "ci-workflow", "comando": "", "codigo": 0,
            "saida_final": f"{len(existentes)} workflow(s) em .github/workflows/ (conteúdo e sintaxe não validados)"}


def _resolver_vars(texto: str, args: dict) -> str:
    def troca(m):
        nome = m.group("a") or m.group("b")
        if nome in args and args[nome] is not None:
            return args[nome]
        return m.group("d") if m.group("d") is not None else m.group(0)
    return _RE_VAR.sub(troca, texto)


def _problema_da_imagem(imagem: str):
    """None se a imagem tem digest ou tag explícita diferente de 'latest'; senão o motivo."""
    if "$" in imagem:
        return f"imagem '{imagem}' parametrizada por variável sem valor padrão: tag não verificável"
    if _RE_DIGEST.search(imagem):
        return None
    ultimo = imagem.rsplit("/", 1)[-1]
    if ":" not in ultimo:
        return f"imagem '{imagem}' sem tag nem digest (equivale a latest)"
    tag = ultimo.rsplit(":", 1)[1]
    if not tag or tag.lower() == "latest":
        return f"imagem '{imagem}' usa a tag latest"
    return None


def _dockerfiles(raiz: Path) -> List[Path]:
    return [p for p in percorrer(raiz)
            if p.name.lower() == "dockerfile" or p.name.lower().startswith("dockerfile.") or p.name.lower().endswith(".dockerfile")]


def verificar_dockerfiles(raiz: Path) -> dict:
    problemas, vistos = [], 0
    for p in _dockerfiles(raiz):
        vistos += 1
        rel = _rel(raiz, p)
        try:
            linhas = _linhas(p)
        except OSError as e:
            problemas.append({"arquivo": rel, "linha": 0, "motivo": f"ilegível: {e}"})
            continue
        # junta continuações com '\' guardando a linha inicial
        logicas, atual, inicio = [], "", 0
        for n, bruta in enumerate(linhas, 1):
            if not atual:
                inicio = n
            corpo = bruta.rstrip()
            if corpo.lstrip().startswith("#") and not atual:
                continue
            if corpo.endswith("\\"):
                atual += corpo[:-1] + " "
                continue
            logicas.append((inicio, atual + corpo))
            atual = ""
        if atual:
            logicas.append((inicio, atual))
        args, estagios = {}, set()
        viu_from = False
        for n, texto in logicas:
            m_arg = _RE_ARG.match(texto)
            if m_arg and not viu_from:  # ARG antes do primeiro FROM vale para os FROM
                valor = m_arg.group("valor")
                args[m_arg.group("nome")] = valor.strip().strip("\"'") if valor is not None else None
                continue
            m = _RE_FROM.match(texto)
            if not m:
                continue
            viu_from = True
            partes = [t for t in m.group("resto").split() if not t.startswith("--")]
            if not partes:
                problemas.append({"arquivo": rel, "linha": n, "motivo": "FROM sem imagem"})
                continue
            imagem = _resolver_vars(partes[0], args)
            alias = partes[2].lower() if len(partes) >= 3 and partes[1].upper() == "AS" else None
            if imagem.lower() != "scratch" and imagem.lower() not in estagios:  # scratch e estágio anterior não têm tag
                motivo = _problema_da_imagem(imagem)
                if motivo:
                    problemas.append({"arquivo": rel, "linha": n, "motivo": motivo})
            if alias:
                estagios.add(alias)
    return _etapa("dockerfile", problemas, f"{vistos} Dockerfile(s) sem tag latest nem FROM sem tag" if vistos else
                  "nenhum Dockerfile no workspace: nada verificado")


def _uses_aceito(valor: str):
    """None se a referência está pinada; senão o motivo."""
    v = valor.strip().strip("\"'")
    if v.startswith("./") or v == ".":
        return None  # ação local do próprio repositório
    if v.startswith("docker://"):
        return None if _RE_DIGEST.search(v) else "imagem docker:// sem digest sha256"
    if "@" not in v:
        return f"'{v}' sem referência fixa (@SHA)"
    ref = v.rsplit("@", 1)[1]
    if not _RE_SHA1.match(ref):
        return f"'{v}' não está fixada por SHA de 40 hex"
    return None


def verificar_actions(raiz: Path) -> dict:
    problemas, usos, arquivos = [], 0, _workflows(raiz)
    for p in arquivos:
        rel = _rel(raiz, p)
        try:
            linhas = _linhas(p)
        except OSError as e:
            problemas.append({"arquivo": rel, "linha": 0, "motivo": f"ilegível: {e}"})
            continue
        for n, linha in enumerate(linhas, 1):
            m = _RE_USES.match(linha)
            if not m:
                continue
            valor = re.sub(r"\s+#.*$", "", m.group("v"))
            usos += 1
            motivo = _uses_aceito(valor)
            if motivo:
                problemas.append({"arquivo": rel, "linha": n, "motivo": motivo})
    return _etapa("actions-pinadas", problemas,
                  f"{usos} uso(s) de 'uses:' em {len(arquivos)} arquivo(s), todos locais ou fixados por SHA/digest")


def _cobre(padroes: List[str], nome: str) -> bool:
    """Último padrão que casa vence (como o git); '!' reabre. Só o .gitignore da raiz."""
    coberto = False
    for bruto in padroes:
        linha = bruto.strip()
        if not linha or linha.startswith("#"):
            continue
        negado = linha.startswith("!")
        pad = linha[1:] if negado else linha
        pad = pad.lstrip("/")
        while pad.startswith("**/"):
            pad = pad[3:]
        pad = pad.rstrip("/")
        if pad and fnmatch.fnmatchcase(nome, pad):
            coberto = not negado
    return coberto


def verificar_gitignore(raiz: Path) -> dict:
    alvo = raiz.resolve() / ".gitignore"
    if not alvo.is_file() or alvo.is_symlink():
        return _etapa("gitignore", [{"arquivo": ".gitignore", "linha": 0, "motivo": "ausente na raiz do workspace"}], "")
    try:
        linhas = _linhas(alvo)
    except OSError as e:
        return _etapa("gitignore", [{"arquivo": ".gitignore", "linha": 0, "motivo": f"ilegível: {e}"}], "")
    faltando = [n for n in GITIGNORE_OBRIGATORIO if not _cobre(linhas, n)]
    return _etapa("gitignore", [{"arquivo": ".gitignore", "linha": 0, "motivo": f"não cobre {n}"} for n in faltando],
                  "cobre bin/, obj/, node_modules/ e .env (só o .gitignore da raiz foi lido)")


def _eh_env(nome: str) -> bool:
    n = nome.lower()
    return (n == ".env" or n.startswith(".env.")) and not n.endswith((".example", ".sample", ".template"))


def verificar_env(raiz: Path) -> dict:
    problemas = []
    for p in percorrer(raiz):
        if not _eh_env(p.name):
            continue
        try:
            util = any(l.strip() and not l.lstrip().startswith("#") for l in _linhas(p))
        except OSError:
            util = True  # não deu para ler: não presume vazio
        if util:
            problemas.append({"arquivo": _rel(raiz, p), "linha": 0, "motivo": "arquivo de ambiente com conteúdo (valores não exibidos)"})
    return _etapa("env-com-conteudo", problemas, "nenhum .env com conteúdo (modelos .example/.sample/.template são ignorados)")


def executar_todas(raiz: Path, stack: dict) -> List[dict]:
    """Todas as etapas do nó devops. Varredura que estoura o limite vira etapa reprovada, nunca aprovação."""
    etapas = []
    for nome, fn in (("ci-workflow", lambda: verificar_ci(raiz, stack)), ("dockerfile", lambda: verificar_dockerfiles(raiz)),
                     ("actions-pinadas", lambda: verificar_actions(raiz)), ("gitignore", lambda: verificar_gitignore(raiz)),
                     ("env-com-conteudo", lambda: verificar_env(raiz))):
        try:
            etapas.append(fn())
        except OverflowError as e:
            etapas.append({"etapa": nome, "comando": "", "codigo": 1, "saida_final": str(e)})
    return etapas
