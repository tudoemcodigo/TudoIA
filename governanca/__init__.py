"""Governança única de regras, skills e MCP para os clientes de IA.

Interface: sincronizar(), verificar(), aplicar_mcp_claude(), aplicar_mcp_opencode(), aplicar_tudo(),
ErroGovernanca, detectar_instancias().
Spec: SPEC.md na raiz do repositório.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

__all__ = ["ErroGovernanca", "sincronizar", "verificar", "aplicar_mcp_claude", "aplicar_mcp_opencode",
           "aplicar_tudo", "detectar_instancias"]

_INI = "<!-- tudoia:inicio (gerado por governanca; edite governanca/regras/) -->"
_FIM = "<!-- tudoia:fim -->"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_CLIENTES = {"antigravity", "claude", "cursor", "codex", "opencode", "workspace"}
_MANTER_BACKUPS = 10
# Base dos backups (relativa à home). Os JSON de MCP têm tokens em claro: o backup fica na home e fora de todo
# workspace, senão um editor que indexa o workspace (D:/ está na lista) leria os tokens das cópias.
_BACKUPS = Path(".tudoia") / "backups"
_MARCA_SKILL = ".tudoia"                       # dentro da pasta de skill copiada: prova que a pasta é nossa
_TEXTO_MARCA = "gerado por governanca (TudoIA): esta pasta some quando a skill sai de governanca.json\n"
_TENTATIVAS_CORRIDA = 3   # releituras quando outro processo (ex.: Claude Code) grava entre a leitura e a troca
_TENTATIVAS_TROCA = 5     # os.replace com PermissionError (Windows: arquivo aberto sem FILE_SHARE_DELETE)
# Variável do .env tratada como segredo pelo nome (PAT só como parte inteira: PATH não é segredo).
_NOME_SEGREDO = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|SENHA|SEGREDO|(?:^|_)PAT(?:_|$)", re.IGNORECASE)
# Valores mais curtos não são procurados no catálogo: casariam por acaso com trechos comuns
# ("true", "8080", "npx") e recusariam configurações legítimas (falso positivo).
_MIN_SEGREDO = 8
_WINDOWS = os.name == "nt"
# Atalhos do Node no Windows são .cmd: o Codex inicia o processo direto, sem shell, então vão por `cmd /c`.
_SHIMS_NODE = {"npx", "npm", "pnpm", "yarn"}


class ErroGovernanca(Exception):
    """Configuração inválida ou insegura; nada foi escrito."""


def sincronizar(raiz: Path, home: Path | None = None) -> dict[str, str]:
    """Escreve os arquivos gerados. Valida tudo antes de gravar (fail-closed).

    Devolve {alvo: "atualizado" | "igual" | "removido"} ("removido" = skill gerenciada órfã apagada).
    Não toca `mcpServers` de ~/.claude.json: essa seção é gerida só pelo painel (aplicar_mcp_claude).
    """
    raiz = Path(raiz)
    plano, _, orfas = _planejar(raiz, _home(home), _home(home) / _BACKUPS)
    return _executar(plano, orfas)


def verificar(raiz: Path, home: Path | None = None) -> list[str]:
    """Lista divergências entre o esperado e o disco. Nunca escreve."""
    plano, mcp, orfas = _planejar(Path(raiz), _home(home))
    # Só as entradas de MCP que o painel gerencia (catálogo governanca/mcp.json)
    escritas = [*plano.items(),
                *(("claude:mcp", e) for e in _escritas_claude(mcp, mcp.catalogo, None)),
                *(("opencode:mcp", e) for e in _escritas_opencode(mcp, mcp.catalogo, None))]
    problemas = []
    for alvo, e in escritas:
        _preparar(e)
        if e.texto != e.atual:
            problemas.append(f"{alvo}: {'ausente' if e.atual is None else 'divergente'} ({e.caminho})")
    problemas += [f"{alvo}: skill gerenciada órfã, fora de governanca.json ({pasta})" for alvo, pasta in orfas]
    return problemas


def aplicar_mcp_claude(raiz: Path, home: Path | None, dir_backup: Path,
                       remover: tuple[str, ...] | list[str] = ()) -> dict[str, str]:
    """Grava no ~/.claude.json só as entradas de MCP geridas pelo painel.

    Dono = ids do catálogo `governanca/mcp.json` (+ `remover`). Ativos são escritos com segredos
    substituídos (destino em home) ou com `${VAR}` literal (destino em workspace). Entradas escritas à mão
    são preservadas. Valida tudo antes de gravar; grava atômico e guarda backup em `dir_backup`.
    """
    _, mcp, _ = _planejar(Path(raiz), _home(home))
    escritas = _escritas_claude(mcp, mcp.catalogo | set(remover), Path(dir_backup))
    return _executar({str(e.caminho): e for e in escritas})


def aplicar_mcp_opencode(raiz: Path, home: Path | None, dir_backup: Path,
                         remover: tuple[str, ...] | list[str] = ()) -> dict[str, str]:
    """Grava no opencode.json só a seção `mcp` das entradas geridas pelo painel.

    Mesmo contrato de aplicar_mcp_claude: dono = ids do catálogo (+ `remover`); entradas escritas à mão
    (ex.: agent-browser) e chaves de provider, modelo e permissão são preservadas. Segredos substituídos
    (destino em home). Valida tudo antes de gravar; backup em `dir_backup`.
    """
    _, mcp, _ = _planejar(Path(raiz), _home(home))
    escritas = _escritas_opencode(mcp, mcp.catalogo | set(remover), Path(dir_backup))
    return _executar({str(e.caminho): e for e in escritas})


def aplicar_tudo(raiz: Path, home: Path | None, dir_backup: Path,
                 remover: tuple[str, ...] | list[str] = ()) -> dict[str, str]:
    """aplicar_mcp_claude + aplicar_mcp_opencode + sincronizar com UMA fase de validação.

    Planeja e valida os três (JSON malformado, marcas, segredos, destinos) antes de gravar qualquer
    arquivo. `dir_backup` é a base: backups em `<dir_backup>/claude-json`, `opencode-json` e
    `antigravity-json`. `remover` vale para os três JSON de MCP. Chaves do resultado: alvos de
    sincronizar + `claude:mcp:<caminho>` e `opencode:mcp:<caminho>`.
    """
    base = Path(dir_backup)
    plano, mcp, orfas = _planejar(Path(raiz), _home(home), base, remover)
    dono = mcp.catalogo | set(remover)
    escritas = {f"claude:mcp:{e.caminho}": e for e in _escritas_claude(mcp, dono, base / "claude-json")}
    escritas.update({f"opencode:mcp:{e.caminho}": e for e in _escritas_opencode(mcp, dono, base / "opencode-json")})
    escritas.update(plano)
    return _executar(escritas, orfas)


# ---------------------------------------------------------------- interno

@dataclass
class _McpClaude:
    caminhos: list[Path]          # arquivos ~/.claude.json (ou config_json) de instâncias Claude ativas
    ativos: dict[str, dict]       # servidores ativos, config crua (com ${VAR})
    catalogo: set[str]            # ids do catálogo: o conjunto que o painel possui
    env: dict[str, str]
    home: Path
    raizes: list[Path]            # raízes de workspace (workspaces + caminhos de instâncias cursor/workspace)
    opencode: list[Path] = field(default_factory=list)   # opencode.json de instâncias OpenCode ativas
    segredos: dict[str, str] = field(default_factory=dict)   # variáveis do .env tratadas como segredo


@dataclass
class _Escrita:
    """Um arquivo a gravar. `gerar(texto_atual)` devolve o texto desejado (valida; pode levantar)."""
    caminho: Path                                  # já resolvido e aprovado por _destino
    gerar: Callable[[str | None], str | None]
    dir_backup: Path | None = None                 # só os JSON de MCP têm backup
    segredo: bool = False                          # arquivo novo nasce 0600 (pode conter segredo)
    assinatura: str | None = None                  # sha256 do conteúdo lido (None = não existia)
    atual: str | None = None
    texto: str | None = None


def _home(home: Path | None) -> Path:
    return Path(home) if home else Path.home()


def _ler_bytes(caminho: Path) -> bytes | None:
    try:
        return caminho.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ErroGovernanca(f"{caminho}: ilegível ({e.strerror or e}); nada foi gravado") from e


def _decodificar(caminho: Path, dados: bytes | None) -> str | None:
    if dados is None:
        return None
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ErroGovernanca(f"{caminho}: não está em UTF-8 ({e.reason}); nada foi gravado") from e
    return texto.replace("\r\n", "\n").replace("\r", "\n")   # mesmas quebras que read_text()


def _ler(caminho: Path) -> str | None:
    return _decodificar(caminho, _ler_bytes(caminho))


def _assinatura(dados: bytes | None) -> str | None:
    return None if dados is None else hashlib.sha256(dados).hexdigest()


def _preparar(e: _Escrita) -> None:
    """Lê o arquivo atual e calcula o desejado. Não escreve."""
    dados = _ler_bytes(e.caminho)
    e.assinatura, e.atual = _assinatura(dados), _decodificar(e.caminho, dados)
    e.texto = e.gerar(e.atual)


def _executar(escritas: dict[str, _Escrita], orfas: list[tuple[str, Path]] = ()) -> dict[str, str]:
    for e in escritas.values():          # fase 1: valida tudo (fail-closed); nada foi gravado ainda
        _preparar(e)
    resultado = {alvo: _efetivar(e) for alvo, e in escritas.items()}
    for alvo, pasta in orfas:
        try:
            shutil.rmtree(pasta)
        except OSError as ex:
            raise ErroGovernanca(f"{pasta}: falha ao remover skill órfã ({ex.strerror or ex})") from ex
        resultado[alvo] = "removido"
    return resultado


def _efetivar(e: _Escrita) -> str:
    try:
        for _ in range(_TENTATIVAS_CORRIDA):
            if e.texto == e.atual:
                return "igual"
            if _gravar(e):
                return "atualizado"
            _preparar(e)   # outro processo gravou depois da leitura: relê e reaplica só o que é nosso
    except OSError as ex:
        raise ErroGovernanca(f"{e.caminho}: falha ao gravar ({ex.strerror or ex})") from ex
    raise ErroGovernanca(f"{e.caminho}: alterado por outro processo durante a gravação "
                         f"({_TENTATIVAS_CORRIDA} tentativas); nada foi gravado nele, tente de novo")


def _gravar(e: _Escrita) -> bool:
    """Grava atômico: temporário único no mesmo diretório, modo do original, fsync, os.replace.

    False se o arquivo mudou desde a leitura (nada é trocado). O temporário nunca fica para trás.
    """
    e.caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(dir=e.caminho.parent, prefix=f".{e.caminho.name}.", suffix=".tmp")
    tmp = Path(nome)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(e.texto.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        try:
            modo = stat.S_IMODE(e.caminho.stat().st_mode)
        except FileNotFoundError:
            modo = 0o600 if e.segredo else 0o644
        os.chmod(tmp, modo)
        if _assinatura(_ler_bytes(e.caminho)) != e.assinatura:
            return False
        if e.dir_backup is not None and e.assinatura is not None:
            _backup(e.caminho, e.dir_backup)
        _trocar(tmp, e.caminho)
        return True
    finally:
        _apagar(tmp)


def _trocar(tmp: Path, caminho: Path) -> None:
    for i in range(_TENTATIVAS_TROCA):
        try:
            os.replace(tmp, caminho)
            return
        except PermissionError as ex:   # Windows: violação de compartilhamento enquanto o cliente grava
            erro = ex
            if i < _TENTATIVAS_TROCA - 1:
                time.sleep(0.05 * (i + 1))
    raise ErroGovernanca(f"{caminho}: em uso por outro processo ou somente leitura; troca recusada após "
                         f"{_TENTATIVAS_TROCA} tentativas. Nada foi alterado nele; feche o cliente e tente de novo.") \
        from erro


def _apagar(tmp: Path) -> None:
    try:
        if tmp.exists():
            os.chmod(tmp, stat.S_IREAD | stat.S_IWRITE)   # Windows não apaga arquivo somente leitura
            tmp.unlink()
    except OSError:
        pass


def _backup(caminho: Path, dir_backup: Path) -> None:
    dir_backup.mkdir(parents=True, exist_ok=True)
    prefixo = f"{caminho.parent.name}__{caminho.name}"
    base = f"{prefixo}.{datetime.now():%Y%m%d-%H%M%S-%f}"
    destino, n = dir_backup / base, 1
    while destino.exists():
        destino, n = dir_backup / f"{base}-{n:02d}", n + 1
    fd = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)  # pode ter segredo
    with os.fdopen(fd, "wb") as f:
        f.write(caminho.read_bytes())
    for velho in sorted(dir_backup.glob(f"{prefixo}.*"))[:-_MANTER_BACKUPS]:
        velho.unlink()


def _bloco(existente: str | None, regras: str, caminho: Path) -> str:
    novo = f"{_INI}\n{regras.strip()}\n{_FIM}"
    base = existente or ""
    marcas = re.findall(re.escape(_INI) + "|" + re.escape(_FIM), base)
    if marcas != [_INI, _FIM] * (len(marcas) // 2):
        # Sem isto, uma marca de fim apagada faz o padrão casar até o fim de outro bloco e apagar o meio
        raise ErroGovernanca(f"{caminho}: marcas do bloco gerenciado desbalanceadas ou fora de ordem "
                             f"({marcas.count(_INI)} de início, {marcas.count(_FIM)} de fim); "
                             "corrija o arquivo à mão; nada foi gravado")
    padrao = re.compile(re.escape(_INI) + r".*?" + re.escape(_FIM), re.DOTALL)
    if padrao.search(base):
        return padrao.sub(lambda _: novo, base)
    return f"{base.rstrip()}\n\n{novo}\n" if base.strip() else f"{novo}\n"


def _id_seguro(valor: object, tipo: str) -> str:
    if not isinstance(valor, str) or not _ID.match(valor):
        raise ErroGovernanca(f"{tipo} com id inválido: {valor!r}")
    return valor


def _carregar_env(arquivo: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    texto = _ler(arquivo) or ""
    for linha in texto.splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env


def _interpolar(obj, env: dict[str, str], servidor: str):
    if isinstance(obj, dict):
        return {k: _interpolar(v, env, servidor) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolar(v, env, servidor) for v in obj]
    if isinstance(obj, str):
        def sub(m: re.Match) -> str:
            valor = env.get(m.group(1))
            if not valor and m.group(2) is not None:   # ${VAR:-padrão}: opcional
                return m.group(2)
            if not valor:
                raise ErroGovernanca(f"MCP '{servidor}': variável {m.group(1)} ausente no .env")
            return valor
        return _VAR.sub(sub, obj)
    return obj


def _json(caminho: Path) -> dict:
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ErroGovernanca(f"{caminho}: ilegível ou JSON inválido ({e})") from e
    if not isinstance(dados, dict):
        raise ErroGovernanca(f"{caminho}: esperado objeto JSON")
    return dados


def _cfg_json(caminho: Path, texto: str | None, chave: str) -> dict | None:
    """None se o arquivo não existe. Malformado -> erro (nunca é substituído por {})."""
    if texto is None:
        return None
    try:
        dados = json.loads(texto.lstrip("﻿"))
    except ValueError as e:
        raise ErroGovernanca(f"{caminho}: JSON inválido ({e}); nada foi gravado") from e
    if not isinstance(dados, dict) or not isinstance(dados.get(chave, {}), dict):
        raise ErroGovernanca(f"{caminho}: esperado objeto JSON com '{chave}' em objeto; nada foi gravado")
    return dados


def _escrita_json(caminho: Path, chave: str, desejado: dict, dono: set[str],
                  dir_backup: Path | None, mcp: _McpClaude) -> _Escrita:
    """Só as entradas de `chave` cujos ids estão em `dono` são gravadas/removidas; o resto é preservado."""
    def gerar(atual: str | None) -> str | None:
        dados = _cfg_json(caminho, atual, chave)
        servidores = (dados or {}).get(chave, {})
        if {k: v for k, v in servidores.items() if k in dono} == desejado:
            return atual   # nada a fazer: não cria nem reformata o arquivo
        novos = {k: v for k, v in servidores.items() if k not in dono}
        novos.update(desejado)
        return json.dumps({**(dados or {}), chave: novos}, indent=2, ensure_ascii=False) + "\n"
    return _Escrita(caminho, gerar, dir_backup, _destino(caminho, mcp.home, mcp.raizes) == "home")


def _escritas_claude(mcp: _McpClaude, dono: set[str], dir_backup: Path | None) -> list[_Escrita]:
    return [_escrita_json(c, "mcpServers", _servidores_para(c, mcp), dono, dir_backup, mcp) for c in mcp.caminhos]


def _escritas_opencode(mcp: _McpClaude, dono: set[str], dir_backup: Path | None) -> list[_Escrita]:
    return [_escrita_json(c, "mcp", _servidores_opencode(c, mcp), dono, dir_backup, mcp) for c in mcp.opencode]


def _para_opencode(mid: str, cfg: dict) -> dict:
    """Formato do catálogo (estilo Claude) -> formato do OpenCode (`mcp.<id>`)."""
    tipo = cfg.get("type")
    if tipo in ("http", "sse"):
        if not isinstance(cfg.get("url"), str) or not cfg["url"]:
            raise ErroGovernanca(f"MCP '{mid}': tipo {tipo} sem 'url'")
        out: dict = {"type": "remote", "url": cfg["url"]}   # auth 'oauth' fica a cargo do OpenCode
        if cfg.get("headers"):
            out["headers"] = cfg["headers"]
    elif tipo in (None, "stdio"):
        args = cfg.get("args", [])
        if not isinstance(cfg.get("command"), str) or not cfg["command"] or not isinstance(args, list):
            raise ErroGovernanca(f"MCP '{mid}': 'command' (texto) e 'args' (lista) são obrigatórios")
        out = {"type": "local", "command": [cfg["command"], *args]}
        if cfg.get("env"):
            out["environment"] = cfg["env"]
    else:
        raise ErroGovernanca(f"MCP '{mid}': tipo {tipo!r} sem tradução para o OpenCode")
    out["enabled"] = True
    return out


def _servidores_opencode(destino: Path, mcp: _McpClaude) -> dict[str, dict]:
    return {mid: _para_opencode(mid, cfg) for mid, cfg in _servidores_para(destino, mcp).items()}


def _transporte(mid: str, cfg: dict, cliente: str) -> tuple[str, dict]:
    """('http', cfg) ou ('stdio', cfg) já validado. Campos fora do protocolo (description, auth) não vão adiante."""
    tipo = cfg.get("type")
    if tipo in ("http", "sse"):
        if not isinstance(cfg.get("url"), str) or not cfg["url"]:
            raise ErroGovernanca(f"MCP '{mid}': tipo {tipo} sem 'url'")
        if tipo == "sse" and cliente == "Codex":
            raise ErroGovernanca(f"MCP '{mid}': o Codex só aceita streamable HTTP, não SSE")
        return "http", cfg
    if tipo in (None, "stdio"):
        if not isinstance(cfg.get("command"), str) or not cfg["command"] \
                or not isinstance(cfg.get("args", []), list):
            raise ErroGovernanca(f"MCP '{mid}': 'command' (texto) e 'args' (lista) são obrigatórios")
        return "stdio", cfg
    raise ErroGovernanca(f"MCP '{mid}': tipo {tipo!r} sem tradução para o {cliente}")


def _para_cursor(mid: str, cfg: dict) -> dict:
    """Catálogo (estilo Claude) -> ~/.cursor/mcp.json: remoto só com url/headers; o OAuth fica com o Cursor."""
    tipo, cfg = _transporte(mid, cfg, "Cursor")
    if tipo == "http":
        out = {"url": cfg["url"]}
        if cfg.get("headers"):
            out["headers"] = cfg["headers"]
        return out
    out = {"command": cfg["command"], "args": list(cfg.get("args", []))}
    if cfg.get("env"):
        out["env"] = cfg["env"]
    return out


def _para_codex(mid: str, cfg: dict) -> dict:
    """Catálogo -> [mcp_servers.<id>] do Codex. Cabeçalho vai em http_headers (o Codex recusa bearer_token literal);
    login OAuth é do próprio Codex (`codex mcp login`)."""
    tipo, cfg = _transporte(mid, cfg, "Codex")
    if tipo == "http":
        out = {"url": cfg["url"]}
        if cfg.get("headers"):
            out["http_headers"] = cfg["headers"]
        return out
    comando, args = cfg["command"], list(cfg.get("args", []))
    if _WINDOWS and comando.lower() in _SHIMS_NODE:
        comando, args = "cmd", ["/c", comando, *args]
    out = {"command": comando, "args": args}
    if cfg.get("env"):
        out["env"] = cfg["env"]
    return out


def _escrita_mcp_json(caminho: Path, para: Callable[[str, dict], dict], dono: set[str],
                      dir_backup: Path | None, mcp: _McpClaude) -> _Escrita:
    desejado = {mid: para(mid, cfg) for mid, cfg in _servidores_para(caminho, mcp).items()}
    return _escrita_json(caminho, "mcpServers", desejado, dono, dir_backup, mcp)


# ---------------------------------------------------------------- TOML do Codex (só stdlib: tomllib lê, nós escrevemos)

_TOML_PARTE = re.compile(r"""\s*(?:([A-Za-z0-9_-]+)|"((?:[^"\\]|\\.)*)"|'([^']*)')\s*""")
_TOML_CABECALHO = re.compile(r"^\s*\[\[?(.+?)\]\]?\s*(?:#.*)?$")


def _chaves_toml(texto: str) -> list[str] | None:
    """Chave pontuada de um cabeçalho TOML (`mcp_servers."a.b".env`) -> ['mcp_servers', 'a.b', 'env']."""
    partes, pos = [], 0
    while True:
        m = _TOML_PARTE.match(texto, pos)
        if not m:
            return None
        if m.group(1) is not None:
            partes.append(m.group(1))
        elif m.group(2) is not None:
            try:
                partes.append(json.loads(f'"{m.group(2)}"'))
            except ValueError:
                return None
        else:
            partes.append(m.group(3))
        pos = m.end()
        if pos == len(texto):
            return partes
        if texto[pos] != ".":
            return None
        pos += 1


def _toml_texto(valor: str) -> str:
    saida = []
    for c in valor:
        if c in '"\\':
            saida.append("\\" + c)
        elif c in "\b\t\n\f\r":
            saida.append({"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}[c])
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            saida.append(f"\\u{ord(c):04x}")
        else:
            saida.append(c)
    return '"' + "".join(saida) + '"'


def _toml_chave(chave: str) -> str:
    return chave if re.fullmatch(r"[A-Za-z0-9_-]+", chave) else _toml_texto(chave)


def _toml_valor(valor) -> str:
    if isinstance(valor, str):
        return _toml_texto(valor)
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, list):
        return "[" + ", ".join(_toml_valor(v) for v in valor) + "]"
    if isinstance(valor, dict):
        return "{ " + ", ".join(f"{_toml_chave(str(k))} = {_toml_valor(v)}" for k, v in valor.items()) + " }"
    raise ErroGovernanca(f"valor sem representação TOML: {type(valor).__name__}")


def _toml_servidor(mid: str, cfg: dict) -> str:
    linhas = [f"[mcp_servers.{_toml_chave(mid)}]"] + [f"{_toml_chave(k)} = {_toml_valor(v)}" for k, v in cfg.items()]
    return "\n".join(linhas) + "\n"


def _sem_tabelas_nossas(texto: str, dono: set[str]) -> str:
    """Tira as tabelas [mcp_servers.<id>] e [mcp_servers.<id>.*] dos ids em `dono`; o resto fica byte a byte."""
    saida, pulando = [], False
    for linha in texto.splitlines(keepends=True):
        m = _TOML_CABECALHO.match(linha)
        if m:
            chaves = _chaves_toml(m.group(1))
            pulando = bool(chaves and len(chaves) >= 2 and chaves[0] == "mcp_servers" and chaves[1] in dono)
        if not pulando:
            saida.append(linha)
    return "".join(saida)


def _escrita_toml_codex(caminho: Path, dono: set[str], dir_backup: Path | None, mcp: _McpClaude) -> _Escrita:
    """config.toml do Codex: o app reescreve plugins, projetos e o próprio MCP; só [mcp_servers.<id do catálogo>] é
    nosso. Depois de editar, relê com tomllib e exige que todo o resto seja semanticamente igual (senão recusa)."""
    desejado = {mid: _para_codex(mid, cfg) for mid, cfg in _servidores_para(caminho, mcp).items()}

    def gerar(atual: str | None) -> str | None:
        base = (atual or "").lstrip("﻿")
        try:
            dados = tomllib.loads(base)
        except tomllib.TOMLDecodeError as e:
            raise ErroGovernanca(f"{caminho}: TOML inválido ({e}); nada foi gravado") from e
        servidores = dados.get("mcp_servers", {})
        if not isinstance(servidores, dict):
            raise ErroGovernanca(f"{caminho}: 'mcp_servers' deve ser tabela; nada foi gravado")
        if {k: v for k, v in servidores.items() if k in dono} == desejado:
            return atual   # nada a fazer: não cria nem reformata o arquivo
        texto = _sem_tabelas_nossas(base, dono)
        if desejado:
            separador = "" if not texto.strip() else ("\n" if texto.endswith("\n") else "\n\n")
            texto += separador + "\n".join(_toml_servidor(m, d) for m, d in desejado.items())
        esperado = dict(dados)
        todos = {**{k: v for k, v in servidores.items() if k not in dono}, **desejado}
        if todos:
            esperado["mcp_servers"] = todos
        else:
            esperado.pop("mcp_servers", None)
        try:
            obtido = tomllib.loads(texto)
        except tomllib.TOMLDecodeError as e:
            raise ErroGovernanca(f"{caminho}: a edição geraria TOML inválido ({e}); edite à mão; nada foi gravado") from e
        if obtido != esperado:
            raise ErroGovernanca(f"{caminho}: os MCP do catálogo não estão em tabelas [mcp_servers.<id>] (ex.: tabela "
                                 "inline); edite à mão para esse formato; nada foi gravado")
        return texto
    return _Escrita(caminho, gerar, dir_backup, _destino(caminho, mcp.home, mcp.raizes) == "home")


def _caminho_opencode_json(inst: dict, home: Path) -> Path:
    cfg_json_raw = inst.get("config_json")
    if cfg_json_raw:
        return _resolver_caminho(cfg_json_raw, home)
    return _resolver_caminho(inst.get("caminho", ""), home) / "opencode.json"


def _destino(caminho: Path, home: Path, raizes: list[Path]) -> str:
    """'workspace' se dentro de uma raiz de workspace; 'home' se dentro de home; senão recusa.

    Decide sobre o caminho resolvido: junction/symlink no meio do caminho não desvia a escrita.
    """
    caminho = Path(caminho).resolve()
    if any(caminho.is_relative_to(r) for r in raizes):
        return "workspace"
    if caminho.is_relative_to(home):
        return "home"
    raise ErroGovernanca(f"destino fora de home e de workspace (recusado): {caminho}")


def _servidores_para(destino: Path, mcp: _McpClaude) -> dict[str, dict]:
    """Segredos só em destino sob home. Em workspace: placeholders ${VAR} literais."""
    if _destino(destino, mcp.home, mcp.raizes) == "home":
        return {mid: _interpolar(cfg, mcp.env, mid) for mid, cfg in mcp.ativos.items()}
    texto = json.dumps(mcp.ativos, ensure_ascii=False)
    for nome, valor in mcp.segredos.items():
        # Compara cru e na forma escapada em JSON (valor com " ou \ aparece escapado no texto)
        if valor in texto or json.dumps(valor, ensure_ascii=False)[1:-1] in texto:
            raise ErroGovernanca(f"governanca/mcp.json contém valor literal de segredo ({nome}); "
                                 f"recusado para {destino}")
    return mcp.ativos


def _resolver_caminho(caminho_str: str, home: Path | None = None) -> Path:
    home = Path(home) if home else Path.home()
    caminho_str = str(caminho_str).strip()
    if caminho_str.startswith("~"):
        rel = caminho_str[1:].lstrip("/\\")
        return (home / rel).resolve() if rel else home.resolve()
    return Path(caminho_str).resolve()


def _caminho_claude_json(inst: dict, home: Path) -> Path:
    cfg_json_raw = inst.get("config_json")
    if cfg_json_raw:
        return _resolver_caminho(cfg_json_raw, home)
    caminho = _resolver_caminho(inst.get("caminho", ""), home)
    if caminho.name == ".claude":
        return home / ".claude.json"
    return caminho / ".claude.json"


def detectar_instancias(home: Path | None = None, workspaces: list[str] | None = None) -> list[dict]:
    """Detecta clientes e diretórios de perfil presentes nesta máquina."""
    home = Path(home) if home else Path.home()
    detectadas: list[dict] = []

    # 1. Claude Code - Instância Padrão
    padrao_claude = home / ".claude"
    if padrao_claude.is_dir():
        detectadas.append({
            "id": "claude-padrao",
            "cliente": "claude",
            "nome": "Claude Code (Padrão)",
            "caminho": "~/.claude",
            "config_json": "~/.claude.json",
            "existe_disco": True,
            "descricao": "Instância principal do Claude Code no diretório de usuário"
        })

    # Perfis adicionais do Claude (ex: .claude-trabalho, .claude-server-commander)
    for p in sorted(home.glob(".claude-*")):
        if p.is_dir():
            sufixo = p.name.replace(".claude-", "").upper()
            cid = f"claude-{p.name.replace('.claude-', '')}"
            caminho_rel = f"~/{p.name}"
            config_json = f"{caminho_rel}/.claude.json" if (p / ".claude.json").is_file() else None
            detectadas.append({
                "id": cid,
                "cliente": "claude",
                "nome": f"Claude Code ({sufixo})",
                "caminho": caminho_rel,
                "config_json": config_json,
                "existe_disco": True,
                "descricao": f"Perfil personalizado do Claude Code ({p.name})"
            })

    # 2. Google Antigravity CLI
    gemini_dir = home / ".gemini"
    if gemini_dir.is_dir():
        detectadas.append({
            "id": "antigravity",
            "cliente": "antigravity",
            "nome": "Google Antigravity CLI",
            "caminho": "~/.gemini",
            "config_json": "~/.gemini/config/mcp_config.json",
            "existe_disco": True,
            "descricao": "Ambiente de governança do Google Antigravity CLI"
        })

    # 3. Codex CLI
    codex_dir = home / ".codex"
    if codex_dir.is_dir():
        detectadas.append({
            "id": "codex",
            "cliente": "codex",
            "nome": "Codex CLI",
            "caminho": "~/.codex",
            "config_json": None,
            "existe_disco": True,
            "descricao": "Ambiente de execução de regras para Codex CLI"
        })

    # 4. Workspaces & Cursor
    if workspaces:
        for ws in workspaces:
            pws = Path(ws)
            if pws.is_dir():
                nome_ws = pws.name or str(pws).replace(":", "").replace("\\", "").replace("/", "")
                detectadas.append({
                    "id": f"cursor-{nome_ws.lower()}",
                    "cliente": "cursor",
                    "nome": f"Cursor IDE ({ws})",
                    "caminho": ws,
                    "config_json": None,
                    "existe_disco": True,
                    "descricao": f"Regras de engenharia TudoIA para workspace Cursor ({ws})"
                })

    return detectadas


def _planejar(raiz: Path, home: Path, dir_backup: Path | None = None,
              remover: tuple[str, ...] | list[str] = ()
              ) -> tuple[dict[str, _Escrita], _McpClaude, list[tuple[str, Path]]]:
    """Monta o plano sem escrever. `dir_backup` = base dos backups do JSON de MCP do Antigravity."""
    home = home.resolve()
    g = raiz / "governanca"
    cfg = _json(g / "governanca.json")

    clientes = set(cfg.get("clientes", []))
    if not clientes <= _CLIENTES:
        raise ErroGovernanca(f"clientes desconhecidos: {sorted(clientes - _CLIENTES)}")

    partes = []
    for rid in cfg.get("regras", []):
        arq = g / "regras" / f"{_id_seguro(rid, 'regra')}.md"
        texto = _ler(arq)
        if texto is None:
            raise ErroGovernanca(f"regra inexistente: {rid}")
        partes.append(texto.strip())
    regras = "\n\n---\n\n".join(partes)

    skills: dict[str, Path] = {}
    for sid in cfg.get("skills", []):
        pasta = g / "skills" / _id_seguro(sid, "skill")
        if not (pasta / "SKILL.md").is_file():
            raise ErroGovernanca(f"skill inexistente: {sid}")
        skills[sid] = pasta

    workspaces = []
    for ws in cfg.get("workspaces", []):
        p = Path(ws)
        if not p.is_dir():
            raise ErroGovernanca(f"workspace inexistente: {ws}")
        workspaces.append(p.resolve())

    catalogo = _json(g / "mcp.json").get("mcpServers", {})
    if not isinstance(catalogo, dict):
        raise ErroGovernanca("governanca/mcp.json: 'mcpServers' deve ser objeto")
    env = _carregar_env(raiz / ".env")
    ativos: dict[str, dict] = {}
    for mid in cfg.get("mcp", []):
        if mid not in catalogo:
            raise ErroGovernanca(f"MCP inexistente no catálogo: {mid}")
        if not isinstance(catalogo[mid], dict):
            raise ErroGovernanca(f"MCP '{mid}': entrada do catálogo deve ser objeto")
        _interpolar(catalogo[mid], env, mid)   # valida variáveis obrigatórias (fail-closed)
        ativos[mid] = catalogo[mid]
    # Segredo = nome com cara de segredo ou variável referenciada por ${VAR} em algum MCP do catálogo
    referenciadas = {m.group(1) for m in _VAR.finditer(json.dumps(catalogo))}
    segredos = {k: v for k, v in env.items()
                if len(v) >= _MIN_SEGREDO and (k in referenciadas or _NOME_SEGREDO.search(k))}

    instancias = cfg.get("instancias")
    if not (instancias and isinstance(instancias, list)):
        instancias = None

    # Raízes de workspace: os workspaces declarados + pastas de instâncias cursor/workspace ativas
    raizes = list(workspaces)
    for inst in instancias or []:
        if isinstance(inst, dict) and inst.get("ativo", True) and inst.get("cliente") in ("cursor", "workspace") \
                and inst.get("caminho"):
            raizes.append(_resolver_caminho(inst["caminho"], home))

    mcp = _McpClaude(caminhos=[], ativos=ativos, catalogo=set(catalogo), env=env, home=home, raizes=raizes,
                     segredos=segredos)
    dono = mcp.catalogo | set(remover)
    backup = dir_backup / "antigravity-json" if dir_backup is not None else None
    plano: dict[str, _Escrita] = {}
    orfas: list[tuple[str, Path]] = []
    claude_caminhos: dict[Path, None] = {}
    opencode_caminhos: dict[Path, None] = {}

    def resolvido(caminho: Path) -> Path:
        # Fail-closed: nenhum arquivo gerado fora de home e de workspace, checado no caminho resolvido
        c = caminho.resolve()
        _destino(c, home, raizes)
        return c

    def bloco(alvo: str, caminho: Path) -> None:
        c = resolvido(caminho)
        plano[alvo] = _Escrita(c, lambda atual: _bloco(atual, regras, c))

    def fixo(alvo: str, caminho: Path, texto: str) -> None:
        plano[alvo] = _Escrita(resolvido(caminho), lambda _atual: texto)

    def copiar_skills(alvo: str, destino: Path) -> None:
        for sid, pasta in skills.items():
            for f in sorted(pasta.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(pasta).as_posix()
                    fixo(f"{alvo}:skill:{sid}/{rel}", destino / sid / rel, _ler(f))
            fixo(f"{alvo}:skill:{sid}/{_MARCA_SKILL}", destino / sid / _MARCA_SKILL, _TEXTO_MARCA)
        # Órfã = pasta com a nossa marca cuja skill saiu de governanca.json. Pasta sem marca é do usuário.
        d = resolvido(destino)
        for p in sorted(d.iterdir()) if d.is_dir() else ():
            if p.name not in skills and p.is_dir() and not p.is_symlink() and not p.is_junction() \
                    and (p / _MARCA_SKILL).is_file() and not (p / _MARCA_SKILL).is_symlink():
                orfas.append((f"{alvo}:skill:{p.name}", p))

    def mcp_antigravity(alvo: str, caminho: Path) -> None:
        c = resolvido(caminho)
        plano[alvo] = _escrita_json(c, "mcpServers", _servidores_para(c, mcp), dono, backup, mcp)

    def mcp_cursor(alvo: str, caminho: Path) -> None:
        c = resolvido(caminho)
        plano[alvo] = _escrita_mcp_json(c, _para_cursor, dono, base_backup("cursor-json"), mcp)

    def mcp_codex(alvo: str, caminho: Path) -> None:
        c = resolvido(caminho)
        plano[alvo] = _escrita_toml_codex(c, dono, base_backup("codex-toml"), mcp)

    def base_backup(nome: str) -> Path | None:
        return dir_backup / nome if dir_backup is not None else None

    def caminho_cursor_mcp(inst: dict) -> Path:
        # Sempre o global da home: a pasta da instância do Cursor é workspace, onde segredo não entra
        return _resolver_caminho(inst["config_json"], home) if inst.get("config_json") else home / ".cursor" / "mcp.json"

    if instancias:
        # 1. Workspaces sempre recebem AGENTS.md
        for ws in workspaces:
            bloco(f"agents:{ws}", ws / "AGENTS.md")

        # 2. Sincroniza cada instância explícita ativa
        for inst in instancias:
            if not isinstance(inst, dict):
                continue
            if not inst.get("ativo", True):
                continue
            cid = _id_seguro(inst.get("id", ""), "instancia")
            tipo_cli = inst.get("cliente")
            if tipo_cli not in _CLIENTES:
                raise ErroGovernanca(f"Instância '{cid}' com cliente desconhecido: {tipo_cli!r}")

            caminho_raw = inst.get("caminho", "")
            if not caminho_raw:
                raise ErroGovernanca(f"Instância '{cid}' sem caminho definido")
            caminho = _resolver_caminho(caminho_raw, home)

            if tipo_cli == "claude":
                bloco(f"claude:{cid}", caminho / "CLAUDE.md")
                copiar_skills(f"claude:{cid}", caminho / "skills")
                # ~/.claude.json: mcpServers é gerido pelo painel (aplicar_mcp_claude), não pelo sync
                claude_caminhos[resolvido(_caminho_claude_json(inst, home))] = None

            elif tipo_cli == "antigravity":
                bloco(f"antigravity:{cid}", caminho / "GEMINI.md")
                cfg_json_raw = inst.get("config_json")
                mcp_path = _resolver_caminho(cfg_json_raw, home) if cfg_json_raw else caminho / "config" / "mcp_config.json"
                mcp_antigravity(f"antigravity:{cid}:mcp", mcp_path)
                copiar_skills(f"antigravity:{cid}", caminho / "antigravity-cli" / "skills")

            elif tipo_cli == "cursor":
                mdc = "---\ndescription: Regras de engenharia TudoIA\nalwaysApply: true\n---\n\n" + regras + "\n"
                fixo(f"cursor:{cid}", caminho / ".cursor" / "rules" / "tudoia.mdc", mdc)
                mcp_cursor(f"cursor:mcp:{caminho_cursor_mcp(inst)}", caminho_cursor_mcp(inst))

            elif tipo_cli == "codex":
                bloco(f"codex:{cid}", caminho / "AGENTS.md")
                cfg_json_raw = inst.get("config_json")
                mcp_codex(f"codex:{cid}:mcp", _resolver_caminho(cfg_json_raw, home) if cfg_json_raw
                          else caminho / "config.toml")

            elif tipo_cli == "opencode":
                bloco(f"opencode:{cid}", caminho / "AGENTS.md")
                # opencode.json é do painel na seção `mcp` (aplicar_mcp_opencode); o resto do arquivo é do usuário
                opencode_caminhos[resolvido(_caminho_opencode_json(inst, home))] = None

            elif tipo_cli == "workspace":
                bloco(f"agents:{cid}", caminho / "AGENTS.md")

    else:
        # Modo legado (clientes e workspaces)
        for ws in workspaces:
            bloco(f"agents:{ws}", ws / "AGENTS.md")
            if "cursor" in clientes:
                mdc = "---\ndescription: Regras de engenharia TudoIA\nalwaysApply: true\n---\n\n" + regras + "\n"
                fixo(f"cursor:{ws}", ws / ".cursor" / "rules" / "tudoia.mdc", mdc)
        if "claude" in clientes:
            bloco("claude", home / ".claude" / "CLAUDE.md")
            copiar_skills("claude", home / ".claude" / "skills")
            claude_caminhos[resolvido(home / ".claude.json")] = None
        if "antigravity" in clientes:
            bloco("antigravity", home / ".gemini" / "GEMINI.md")
            mcp_antigravity("antigravity:mcp", home / ".gemini" / "config" / "mcp_config.json")
            copiar_skills("antigravity", home / ".gemini" / "antigravity-cli" / "skills")
        if "cursor" in clientes:
            mcp_cursor("cursor:mcp", home / ".cursor" / "mcp.json")
        if "codex" in clientes:
            bloco("codex", home / ".codex" / "AGENTS.md")
            mcp_codex("codex:mcp", home / ".codex" / "config.toml")

    mcp.caminhos, mcp.opencode = list(claude_caminhos), list(opencode_caminhos)
    return plano, mcp, orfas
