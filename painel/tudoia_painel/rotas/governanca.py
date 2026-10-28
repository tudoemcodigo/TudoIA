"""Governança: regras, skills e MCP distribuídos para os clientes de IA."""
import json
import logging
import re
import shutil
from pathlib import Path

from fastapi import APIRouter

import governanca

from ..envfile import ler_env
from ..erros import ErroApi
from .. import mcp_teste
from ..ambiente import Contexto
from ..skills_servico import ID
from .. import skills_servico
from ..schemas import Ativo, EditarConteudoGovernanca, EditarInstanciaGovernanca, ImportarSkill, NovaInstanciaGovernanca, NovaRegra, NovaSkill, NovoMcp


TIPOS = ("mcp", "skills", "regras")


log = logging.getLogger(__name__)


def criar_router(ctx: Contexto) -> APIRouter:
    router = APIRouter()
    raiz = ctx.raiz
    home = ctx.home
    trava = ctx.trava

    def cfg_path() -> Path:
        return raiz / "governanca" / "governanca.json"

    def gravar_cfg(cfg: dict) -> None:
        # Atômico: queda no meio da gravação não deixa o governanca.json truncado (o sync recusaria tudo).
        tmp = cfg_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        tmp.replace(cfg_path())

    def _backups_governanca() -> Path:
        # Na home e fora de todo workspace: as cópias do ~/.claude.json têm tokens em claro, e D:/ é workspace.
        return home / ".tudoia" / "backups"

    def _aplicar_mcp(remover: tuple[str, ...] = ()) -> str | None:
        """Aplica MCP (Claude, OpenCode, Antigravity) e sync numa só validação. Devolve o motivo se não der (nada é gravado)."""
        try:
            governanca.aplicar_tudo(raiz, home, _backups_governanca(), remover)
            return None
        except governanca.ErroGovernanca as e:
            return str(e)

    def catalogo_governanca() -> dict[str, list[str]]:
        g = raiz / "governanca"
        arq_mcp = g / "mcp.json"
        mcp = json.loads(arq_mcp.read_text(encoding="utf-8")).get("mcpServers", {}) if arq_mcp.is_file() else {}
        return {
            "mcp": sorted(mcp),
            "skills": sorted(p.parent.name for p in (g / "skills").glob("*/SKILL.md")),
            "regras": sorted(p.stem for p in (g / "regras").glob("*.md"))
        }

    # ------------------------------------------------ governança
    @router.get("/api/governanca")
    def estado_governanca():
        cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
        drift = []
        alertas_mcp: dict[str, list[str]] = {}
        dados_mcp: dict = {}  # sem mcp.json a tela mostra "nenhum MCP" (antes: NameError e 500)

        # Mapeia variáveis de ambiente obrigatórias ausentes para os MCPs
        mcp_path = raiz / "governanca" / "mcp.json"
        if mcp_path.is_file():
            env_local = ler_env(raiz / ".env")
            dados_mcp = json.loads(mcp_path.read_text(encoding="utf-8")).get("mcpServers", {})
            for mid, mcp_cfg in dados_mcp.items():
                if mcp_cfg.get("auth") == "oauth":
                    continue
                ausentes = []
                for _k, v in mcp_cfg.get("env", {}).items():
                    m = re.match(r"^\$\{([A-Z0-9_]+)(?::-.*)?\}$", str(v))
                    if m and ":-" not in str(v):
                        var_nome = m.group(1)
                        if not env_local.get(var_nome, "").strip():
                            ausentes.append(var_nome)
                for arg in mcp_cfg.get("args", []):
                    for m in re.finditer(r"\$\{([A-Z0-9_]+)(?::-.*)?\}", str(arg)):
                        if ":-" not in m.group(0):
                            var_nome = m.group(1)
                            if not env_local.get(var_nome, "").strip():
                                ausentes.append(var_nome)
                if mcp_cfg.get("url"):
                    for m in re.finditer(r"\$\{([A-Z0-9_]+)(?::-.*)?\}", str(mcp_cfg["url"])):
                        if ":-" not in m.group(0):
                            var_nome = m.group(1)
                            if not env_local.get(var_nome, "").strip():
                                ausentes.append(var_nome)
                if ausentes:
                    alertas_mcp[mid] = sorted(list(set(ausentes)))

        try:
            drift = governanca.verificar(raiz, home)
        except governanca.ErroGovernanca as e:
            drift = [str(e)]
        except (OSError, ValueError) as e:
            raise ErroApi(422, "validacao", str(e)) from e

        catalogo = catalogo_governanca()
        return {
            "drift": drift,
            "alertas_mcp": alertas_mcp,
            "mcp_configs": dados_mcp,
            "instancias": cfg.get("instancias", []),
            **{t: {i: i in cfg.get(t, []) for i in catalogo[t]} for t in TIPOS}
        }

    @router.post("/api/governanca/sincronizar")
    def sincronizar():
        with trava:
            try:
                # Tudo validado antes de gravar qualquer arquivo (antes: Claude gravava e o OpenCode falhava depois)
                return governanca.aplicar_tudo(raiz, home, _backups_governanca())
            except governanca.ErroGovernanca as e:
                raise ErroApi(422, "validacao", str(e)) from e

    # ------------------------------------------------ instâncias de governança
    @router.get("/api/governanca/instancias")
    def listar_instancias_governanca():
        cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
        instancias = [dict(i) for i in cfg.get("instancias", [])]
        for inst in instancias:
            caminho_res = governanca._resolver_caminho(inst.get("caminho", ""), home)
            inst["existe_disco"] = caminho_res.exists()
            if inst.get("config_json"):
                cfg_res = governanca._resolver_caminho(inst["config_json"], home)
                inst["config_json_existe"] = cfg_res.exists()
            else:
                inst["config_json_existe"] = None

        detectadas = governanca.detectar_instancias(home, cfg.get("workspaces", []))
        configuradas_ids = {i.get("id") for i in instancias}
        for d in detectadas:
            d["ja_configurado"] = d["id"] in configuradas_ids

        return {
            "instancias": instancias,
            "detectadas": detectadas
        }

    @router.post("/api/governanca/instancias")
    def adicionar_instancia_governanca(corpo: NovaInstanciaGovernanca):
        if not ID.match(corpo.id):
            raise ErroApi(422, "validacao", f"ID de instância inválido: '{corpo.id}'", campo="id")
        if corpo.cliente not in governanca._CLIENTES:
            raise ErroApi(422, "validacao", f"Cliente desconhecido: '{corpo.cliente}'", campo="cliente")
        with trava:
            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            instancias = cfg.setdefault("instancias", [])
            if any(i.get("id") == corpo.id for i in instancias):
                raise ErroApi(409, "duplicado", f"Instância '{corpo.id}' já existe")
            nova = {
                "id": corpo.id,
                "cliente": corpo.cliente,
                "nome": corpo.nome.strip() or corpo.id,
                "caminho": corpo.caminho.strip(),
                "config_json": corpo.config_json.strip() if corpo.config_json else None,
                "ativo": corpo.ativo
            }
            instancias.append(nova)
            gravar_cfg(cfg)
            return {"ok": True, "instancia": nova}

    @router.put("/api/governanca/instancias/{id}")
    def atualizar_instancia_governanca(id: str, corpo: EditarInstanciaGovernanca):
        with trava:
            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            instancias = cfg.get("instancias", [])
            alvo = next((i for i in instancias if i.get("id") == id), None)
            if not alvo:
                raise ErroApi(404, "nao_encontrado", f"Instância '{id}' não encontrada")
            if corpo.nome is not None:
                alvo["nome"] = corpo.nome.strip()
            if corpo.caminho is not None:
                alvo["caminho"] = corpo.caminho.strip()
            if corpo.config_json is not None:
                alvo["config_json"] = corpo.config_json.strip() if corpo.config_json else None
            if corpo.ativo is not None:
                alvo["ativo"] = bool(corpo.ativo)
            gravar_cfg(cfg)
            return {"ok": True, "instancia": alvo}

    @router.delete("/api/governanca/instancias/{id}")
    def remover_instancia_governanca(id: str):
        with trava:
            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            instancias = cfg.get("instancias", [])
            idx = next((i for i, inst in enumerate(instancias) if inst.get("id") == id), None)
            if idx is None:
                raise ErroApi(404, "nao_encontrado", f"Instância '{id}' não encontrada")
            removida = instancias.pop(idx)
            gravar_cfg(cfg)
            return {"ok": True, "removida": removida}

    @router.post("/api/governanca/instancias/detectar")
    def detectar_instancias_api():
        cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
        instancias = cfg.get("instancias", [])
        detectadas = governanca.detectar_instancias(home, cfg.get("workspaces", []))
        configuradas_ids = {i.get("id") for i in instancias}
        for d in detectadas:
            d["ja_configurado"] = d["id"] in configuradas_ids
        return {"detectadas": detectadas}

    @router.get("/api/governanca/{tipo}/{item}")
    def obter_item_governanca(tipo: str, item: str):
        if tipo not in TIPOS or not ID.match(item) or item not in catalogo_governanca()[tipo]:
            raise ErroApi(404, "nao_encontrado", "item de governança desconhecido")
        
        conteudo = ""
        caminho_rel = ""
        if tipo == "regras":
            alvo = raiz / "governanca" / "regras" / f"{item}.md"
            if not alvo.is_file():
                raise ErroApi(404, "nao_encontrado", "arquivo de regra não encontrado")
            conteudo = alvo.read_text(encoding="utf-8")
            caminho_rel = f"governanca/regras/{item}.md"
        elif tipo == "skills":
            alvo = raiz / "governanca" / "skills" / item / "SKILL.md"
            if not alvo.is_file():
                raise ErroApi(404, "nao_encontrado", "SKILL.md não encontrado")
            conteudo = alvo.read_text(encoding="utf-8")
            caminho_rel = f"governanca/skills/{item}/SKILL.md"
        elif tipo == "mcp":
            mcp_path = raiz / "governanca" / "mcp.json"
            if not mcp_path.is_file():
                raise ErroApi(404, "nao_encontrado", "mcp.json não encontrado")
            dados = json.loads(mcp_path.read_text(encoding="utf-8")).get("mcpServers", {})
            if item not in dados:
                raise ErroApi(404, "nao_encontrado", f"servidor MCP {item} não encontrado")
            conteudo = json.dumps(dados[item], indent=2, ensure_ascii=False)
            caminho_rel = "governanca/mcp.json"

        return {
            "id": item,
            "tipo": tipo,
            "caminho": caminho_rel,
            "conteudo": conteudo
        }

    @router.put("/api/governanca/{tipo}/{item}/conteudo")
    def editar_conteudo_governanca(tipo: str, item: str, corpo: EditarConteudoGovernanca):
        if tipo not in TIPOS or not ID.match(item) or item not in catalogo_governanca()[tipo]:
            raise ErroApi(404, "nao_encontrado", "item de governança desconhecido")

        conteudo_normalizado = corpo.conteudo.rstrip() + "\n"
        caminho_rel = ""

        with trava:
            if tipo == "regras":
                alvo = raiz / "governanca" / "regras" / f"{item}.md"
                if not alvo.is_file():
                    raise ErroApi(404, "nao_encontrado", "arquivo de regra não encontrado")
                alvo.write_text(conteudo_normalizado, encoding="utf-8", newline="\n")
                caminho_rel = f"governanca/regras/{item}.md"
            elif tipo == "skills":
                pasta = raiz / "governanca" / "skills" / item
                alvo = pasta / "SKILL.md"
                if not alvo.is_file():
                    raise ErroApi(404, "nao_encontrado", "SKILL.md não encontrado")
                alvo.write_text(conteudo_normalizado, encoding="utf-8", newline="\n")
                caminho_rel = f"governanca/skills/{item}/SKILL.md"
            elif tipo == "mcp":
                try:
                    cfg_mcp = json.loads(corpo.conteudo)
                    if not isinstance(cfg_mcp, dict):
                        raise ValueError("Configuração MCP deve ser um objeto JSON (dict)")
                except Exception as e:
                    raise ErroApi(422, "validacao", f"JSON inválido para servidor MCP: {e}") from e

                mcp_path = raiz / "governanca" / "mcp.json"
                if not mcp_path.is_file():
                    raise ErroApi(404, "nao_encontrado", "mcp.json não encontrado")
                dados_mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
                dados_mcp.setdefault("mcpServers", {})[item] = cfg_mcp
                mcp_path.write_text(json.dumps(dados_mcp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
                caminho_rel = "governanca/mcp.json"
                if pendencia := _aplicar_mcp():
                    raise ErroApi(422, "validacao", f"Falha ao atualizar ~/.claude.json após salvar: {pendencia}")

            try:
                governanca.sincronizar(raiz, home)
            except governanca.ErroGovernanca as e:
                raise ErroApi(422, "validacao", f"Falha na sincronização após salvar: {e}") from e

        return {
            "ok": True,
            "id": item,
            "tipo": tipo,
            "caminho": caminho_rel,
            "conteudo": conteudo_normalizado
        }

    @router.put("/api/governanca/{tipo}/{item}")
    def alternar(tipo: str, item: str, corpo: Ativo):
        if tipo not in TIPOS or not ID.match(item) or item not in catalogo_governanca()[tipo]:
            raise ErroApi(404, "nao_encontrado", "item de governança desconhecido")
        with trava:
            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            atuais = [i for i in cfg.get(tipo, []) if i != item]
            cfg[tipo] = atuais + [item] if corpo.ativo else atuais
            tmp = cfg_path().with_suffix(".tmp")
            tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
            tmp.replace(cfg_path())
            pendencia = _aplicar_mcp() if tipo == "mcp" else None
        return {"ok": True, "pendencia": pendencia}

    @router.delete("/api/governanca/{tipo}/{item}")
    def excluir_item_governanca(tipo: str, item: str):
        if tipo not in TIPOS or not ID.match(item) or item not in catalogo_governanca()[tipo]:
            raise ErroApi(404, "nao_encontrado", "item de governança desconhecido")
        with trava:
            if tipo == "regras":
                alvo = raiz / "governanca" / "regras" / f"{item}.md"
                if alvo.is_file():
                    alvo.unlink()
            elif tipo == "skills":
                pasta = raiz / "governanca" / "skills" / item
                if pasta.is_dir():
                    shutil.rmtree(pasta)
            elif tipo == "mcp":
                mcp_path = raiz / "governanca" / "mcp.json"
                if mcp_path.is_file():
                    dados_mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
                    if "mcpServers" in dados_mcp and item in dados_mcp["mcpServers"]:
                        del dados_mcp["mcpServers"][item]
                        mcp_path.write_text(json.dumps(dados_mcp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            if item in cfg.get(tipo, []):
                cfg[tipo] = [i for i in cfg[tipo] if i != item]
                tmp = cfg_path().with_suffix(".tmp")
                tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
                tmp.replace(cfg_path())
            pendencia = _aplicar_mcp(remover=(item,)) if tipo == "mcp" else None
        return {"ok": True, "removido": item, "pendencia": pendencia}

    @router.post("/api/governanca/regras")
    def incluir_regra(corpo: NovaRegra):
        if not ID.match(corpo.id):
            raise ErroApi(422, "validacao", "ID de regra inválido (use letras, números e hífens)", campo="id")
        alvo = raiz / "governanca" / "regras" / f"{corpo.id}.md"
        with trava:
            alvo.write_text(corpo.conteudo.strip() + "\n", encoding="utf-8", newline="\n")
            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            if corpo.ativo and corpo.id not in cfg.get("regras", []):
                cfg.setdefault("regras", []).append(corpo.id)
                gravar_cfg(cfg)
        return {"ok": True, "id": corpo.id}

    @router.post("/api/governanca/skills")
    def incluir_skill(corpo: NovaSkill):
        if not ID.match(corpo.id):
            raise ErroApi(422, "validacao", "ID de skill inválido", campo="id")
        pasta = raiz / "governanca" / "skills" / corpo.id
        pasta.mkdir(parents=True, exist_ok=True)
        alvo = pasta / "SKILL.md"
        with trava:
            alvo.write_text(corpo.conteudo.strip() + "\n", encoding="utf-8", newline="\n")
            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            if corpo.ativo and corpo.id not in cfg.get("skills", []):
                cfg.setdefault("skills", []).append(corpo.id)
                gravar_cfg(cfg)
        return {"ok": True, "id": corpo.id}

    @router.post("/api/governanca/skills/importar")
    def importar_skill(corpo: ImportarSkill):
        repo_url, skill_nome = skills_servico.interpretar_pedido(corpo.comando, corpo.repo_url, corpo.skill_nome)
        destino = skills_servico.importar(raiz, trava, repo_url, skill_nome)
        with trava:
            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            if corpo.ativo and skill_nome not in cfg.get("skills", []):
                cfg.setdefault("skills", []).append(skill_nome)
                gravar_cfg(cfg)
            try:
                governanca.sincronizar(raiz, home)
            except Exception as e:   # a skill já está importada; o sync pode ser refeito pelo botão Sincronizar
                log.warning("skill %s importada, mas o sync falhou (%s)", skill_nome, type(e).__name__)
        return {"ok": True, "id": skill_nome, "arquivos": [p.name for p in destino.glob("**/*") if p.is_file()]}

    @router.post("/api/governanca/mcp")
    def incluir_mcp(corpo: NovoMcp):
        if not ID.match(corpo.id):
            raise ErroApi(422, "validacao", "ID de servidor MCP inválido", campo="id")
        mcp_path = raiz / "governanca" / "mcp.json"
        with trava:
            dados_mcp = json.loads(mcp_path.read_text(encoding="utf-8"))
            dados_mcp.setdefault("mcpServers", {})[corpo.id] = corpo.config
            mcp_path.write_text(json.dumps(dados_mcp, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

            cfg = json.loads(cfg_path().read_text(encoding="utf-8"))
            if corpo.ativo and corpo.id not in cfg.get("mcp", []):
                cfg.setdefault("mcp", []).append(corpo.id)
                gravar_cfg(cfg)
            pendencia = _aplicar_mcp()
        return {"ok": True, "id": corpo.id, "pendencia": pendencia}

    @router.post("/api/governanca/mcp/{id}/testar")
    def testar_mcp(id: str):
        if not ID.match(id):
            raise ErroApi(422, "validacao", "ID de servidor MCP inválido", campo="id")
        mcp_path = raiz / "governanca" / "mcp.json"
        if not mcp_path.is_file():
            raise ErroApi(404, "nao_encontrado", "mcp.json não encontrado")
        dados = json.loads(mcp_path.read_text(encoding="utf-8"))
        servidores = dados.get("mcpServers", {})
        if id not in servidores:
            raise ErroApi(404, "nao_encontrado", f"Servidor MCP '{id}' não encontrado")

        return mcp_teste.testar(id, servidores[id], ler_env(raiz / ".env"))

    return router
