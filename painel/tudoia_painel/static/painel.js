"use strict";

const $ = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelectorAll(sel);

function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "className") e.className = v;
    else if (k === "textContent") e.textContent = v;
    else if (k === "checked") e.checked = Boolean(v);
    else if (k === "disabled") e.disabled = Boolean(v);
    else if (k === "value") e.value = v;
    else if (k === "dataset") Object.assign(e.dataset, v);
    else if (k.startsWith("on")) e.addEventListener(k.substring(2).toLowerCase(), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (typeof c === "string") e.appendChild(document.createTextNode(c));
    else if (c) e.appendChild(c);
  }
  return e;
}

// Escapa texto vindo de fora (resposta de modelo, erro de provedor) antes de um template com innerHTML.
// A CSP já barra script, mas não barra marcação nem CSS injetados.
function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Ícone de linha no mesmo traço dos SVG do index.html (stroke currentColor, 24x24), montado pelo DOM.
const ICONES = {
  olho: ["M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0",
         "M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0"],
  olhoFechado: ["M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49",
                "M14.084 14.158a3 3 0 0 1-4.242-4.242",
                "M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143",
                "m2 2 20 20"],
};
function icone(nome, tamanho = 14) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({ width: tamanho, height: tamanho, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) {
    svg.setAttribute(k, v);
  }
  for (const d of ICONES[nome]) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    svg.appendChild(p);
  }
  return svg;
}

function toast(mensagem, tipo = "info") {
  const container = $("toast-container");
  const t = el("div", { className: `toast toast-${tipo}`, textContent: mensagem });
  container.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transform = "translateX(100%)";
    t.style.transition = "all 0.3s ease";
    setTimeout(() => t.remove(), 300);
  }, 4000);
}

// ------------------------------------------------ FEEDBACK DE CARREGAMENTO (geral)
// Toda ação que fala com o servidor passa por api(). Enquanto ela roda, aparece a barra no topo e o botão que
// originou o clique mostra um indicador e fica desabilitado. Assim nenhum clique parece "não fazer nada".
let botaoDoClique = null;
let limpezaBotaoDoClique = null;
let chamadasEmCurso = 0;

document.addEventListener("click", (evento) => {
  const botao = evento.target.closest?.("button, .btn");
  botaoDoClique = botao && !botao.disabled ? botao : null;
  clearTimeout(limpezaBotaoDoClique);
  // O clique só vale para a próxima chamada que ele disparar; depois disso não pode marcar outro botão.
  limpezaBotaoDoClique = setTimeout(() => { botaoDoClique = null; }, 1500);
}, true);

function barraDeCarregamento() {
  let barra = $("barra-carregando");
  if (!barra) {
    barra = document.createElement("div");
    barra.id = "barra-carregando";
    barra.setAttribute("aria-hidden", "true");
    document.body.appendChild(barra);
  }
  return barra;
}

function iniciarCarregamento() {
  chamadasEmCurso++;
  barraDeCarregamento().classList.add("ativa");
  const botao = botaoDoClique;
  botaoDoClique = null;
  if (!botao) return null;
  const estado = { botao, desabilitadoAntes: botao.disabled };
  botao.classList.add("is-loading");
  botao.setAttribute("aria-busy", "true");
  botao.disabled = true;
  return estado;
}

function terminarCarregamento(estado) {
  chamadasEmCurso = Math.max(0, chamadasEmCurso - 1);
  if (chamadasEmCurso === 0) barraDeCarregamento().classList.remove("ativa");
  if (estado) {
    estado.botao.classList.remove("is-loading");
    estado.botao.removeAttribute("aria-busy");
    estado.botao.disabled = estado.desabilitadoAntes;
  }
}

let redirecionandoLogin = false;
function redirecionarLogin() {
  if (redirecionandoLogin) return;
  redirecionandoLogin = true;
  const hash = window.location.hash || "";
  const retorno = encodeURIComponent(location.pathname + location.search + hash);
  window.location.assign(`/auth/login?retorno=${retorno}`);
}

async function api(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: { "content-type": "application/json" } };
  if (metodo !== "GET") opcoes.body = JSON.stringify(corpo ?? {});
  const estado = iniciarCarregamento();
  try {
    const r = await fetch(caminho, opcoes);
    if (r.status === 401) {
      // Sessão ausente ou expirada: volta ao login e retorna para a tela atual depois.
      redirecionarLogin();
      throw new Error("sessão expirada: faça login novamente");
    }
    const dados = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = dados.erro ? dados.erro.mensagem : `Erro ${r.status}`;
      const erro = new Error(msg);
      erro.status = r.status;
      erro.codigo = dados.erro ? dados.erro.codigo : null;
      erro.extras = (dados.erro && dados.erro.extras) || {};
      throw erro;
    }
    return dados;
  } finally {
    terminarCarregamento(estado);
  }
}

// ------------------------------------------------ NAVEGAÇÃO & ABAS
let abaAtivaAtual = null;

function ativarAba(viewId) {
  if (!viewId || !$(`view-${viewId}`)) return;
  if (abaAtivaAtual === viewId) return;
  abaAtivaAtual = viewId;
  $$(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === viewId);
  });
  $$(".page-view").forEach((view) => {
    view.classList.toggle("active", view.id === `view-${viewId}`);
  });
  if (window.location.hash.replace("#", "") !== viewId) {
    window.location.hash = viewId;
  }
  carregarAba(viewId);
}

function carregarAba(viewId) {
  if (viewId === "chat") carregarChat();
  else if (viewId === "imagens") carregarImagens();
  else if (viewId === "videos") carregarVideos();
  else if (viewId === "musicas") carregarMusicas();
  else if (viewId === "servicos") carregarServicos();
  else if (viewId === "hardware") carregarHardware();
  else if (viewId === "modelos") carregarModelos();
  else if (viewId === "roteador") carregarRoteador();
  else if (viewId === "governanca") carregarGovernanca();
  else if (viewId === "segredos") carregarSegredos();
  else if (viewId === "limites") carregarLimites();
  else if (viewId === "telemetria") carregarTelemetria();
}

$$(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => ativarAba(btn.dataset.view));
});

window.addEventListener("hashchange", () => {
  const hash = window.location.hash.replace("#", "");
  if (hash && $(`view-${hash}`) && hash !== abaAtivaAtual) {
    ativarAba(hash);
  }
});

let chaveParaDestacar = null;

function navegarParaSegredo(chave) {
  chaveParaDestacar = chave;
  if (filtroSegredoAtual !== "todos") {
    filtroSegredoAtual = "todos";
    $$("[data-filter-segredo]").forEach(b => b.classList.toggle("active", b.dataset.filterSegredo === "todos"));
  }
  if (abaAtivaAtual === "segredos") {
    destacarSegredoNaTela();
  } else {
    ativarAba("segredos");
  }
}

function destacarSegredoNaTela() {
  if (!chaveParaDestacar) return;
  const chave = chaveParaDestacar;
  const alvo = $(`card-segredo-${chave}`);
  if (alvo) {
    setTimeout(() => {
      alvo.scrollIntoView({ behavior: "smooth", block: "center" });
      alvo.style.outline = "2px solid var(--accent)";
      alvo.style.boxShadow = "0 0 16px rgba(99, 102, 241, 0.45)";
      const inp = alvo.querySelector("input");
      if (inp) {
        inp.focus();
        inp.select();
      }
      setTimeout(() => {
        alvo.style.outline = "";
        alvo.style.boxShadow = "";
      }, 3500);
    }, 150);
    chaveParaDestacar = null;
  }
}

// Rótulo de tier para exibição (a lógica continua comparando os valores originais)
function rotuloTier(tier) {
  return ({ LOCAL: "Local", NUVEM: "Nuvem", FREE: "Grátis", PAID: "Pago" })[tier] ?? tier ?? "Nuvem";
}

// ------------------------------------------------ 1. SERVIÇOS
async function carregarServicos() {
  const grid = $("grid-servicos");
  grid.className = "servicos-tabela";
  grid.replaceChildren(el("div", { className: "suave", textContent: "Carregando serviços…" }));
  try {
    const lista = await api("GET", "/api/servicos");
    grid.replaceChildren(el("div", { className: "servico-linha servico-cabecalho" }, [
      el("span", { textContent: "Serviço" }),
      el("span", { textContent: "Tipo" }),
      el("span", { textContent: "Porta" }),
      el("span", { textContent: "Estado" }),
      el("span", { textContent: "Ações", className: "servico-acoes-cabecalho" }),
    ]));
    let todosOnline = true;
    for (const s of lista) {
      if (!s.ativo) todosOnline = false;
      const tituloEl = s.url
        ? el("a", {
            className: "servico-titulo servico-titulo-link",
            href: s.url,
            target: "_blank",
            rel: "noopener noreferrer",
            title: `Abrir ${s.titulo || s.nome} em nova aba (${s.url})`,
            textContent: s.titulo || s.nome,
          })
        : el("div", { className: "servico-titulo", textContent: s.titulo || s.nome });

      const nome = el("div", { className: "servico-nome" }, [
        el("span", { className: `status-dot ${s.ativo ? "online" : ""}` }),
        el("div", {}, [
          tituloEl,
          el("div", { className: "servico-desc", textContent: s.descricao || `Serviço ${s.nome}` }),
        ]),
      ]);
      const tipo = el("span", { className: "servico-tipo", textContent: s.tipo });
      const porta = !s.porta
        ? el("span", { className: "servico-porta inativa", textContent: "—" })
        : s.url
          ? el("a", { className: `servico-porta ${s.ativo ? "" : "inativa"}`, href: s.url, target: "_blank", rel: "noopener noreferrer", title: `Abrir ${s.url} em nova aba`, textContent: `:${s.porta}` })
          : el("span", { className: "servico-porta inativa", textContent: `:${s.porta}` });
      const estado = el("span", { className: `servico-estado ${s.ativo ? "on" : "off"}`, textContent: s.ativo ? "Online" : "Parado" });

      const linkApp = s.url ? el("a", {
        href: s.url,
        target: "_blank",
        rel: "noopener noreferrer",
        className: s.ativo ? "btn btn-open-ui btn-sm" : "btn btn-outline btn-sm",
        style: s.ativo ? "" : "opacity:0.55;",
        title: s.ativo ? `Abrir ${s.titulo || s.nome} em nova aba (${s.url})` : `Serviço parado (${s.url}) — clique para abrir se já estiver em execução`,
        textContent: "Abrir ↗"
      }) : null;
      const btnStart = el("button", {
        className: "btn btn-sm btn-outline",
        textContent: s.ativo ? "Reiniciar" : "Iniciar",
        onclick: async () => {
          try {
            await api("POST", `/api/servicos/${s.nome}/${s.ativo ? "restart" : "start"}`);
            toast(`${s.titulo || s.nome} ${s.ativo ? "reiniciado" : "iniciado"}`, "success");
            carregarServicos();
          } catch (e) { toast(e.message, "error"); }
        }
      });
      const btnStop = s.ativo ? el("button", {
        className: "btn btn-sm btn-danger",
        textContent: "Parar",
        onclick: async () => {
          try {
            await api("POST", `/api/servicos/${s.nome}/stop`);
            toast(`${s.titulo || s.nome} parado`, "info");
            carregarServicos();
          } catch (e) { toast(e.message, "error"); }
        }
      }) : null;
      const acoes = el("div", { className: "servico-acoes" }, [linkApp, btnStart, btnStop]);

      grid.appendChild(el("div", { className: "servico-linha" }, [nome, tipo, porta, estado, acoes]));
    }
    $("global-indicator").className = `status-dot ${todosOnline ? "online" : ""}`;
    $("global-status").textContent = todosOnline ? "Todos os serviços online" : "Serviços parciais";
  } catch (e) {
    grid.replaceChildren(el("div", { className: "toast toast-error", textContent: e.message }));
  }
}

$("btn-iniciar-tudo").addEventListener("click", async () => {
  try {
    toast("Iniciando ecossistema completo (Docker, Ollama, ComfyUI)...", "info");
    await api("POST", "/api/servicos/todos/start");
    toast("Todos os serviços e infraestrutura iniciados com sucesso!", "success");
    carregarServicos();
  } catch (e) { toast(e.message, "error"); }
});

$("btn-desligar-tudo").addEventListener("click", async () => {
  try {
    toast("Desligando todos os serviços e processos (Docker, Ollama, ComfyUI)...", "info");
    await api("POST", "/api/servicos/todos/stop");
    toast("Todos os serviços e processos foram encerrados com sucesso!", "info");
    carregarServicos();
  } catch (e) { toast(e.message, "error"); }
});

$("btn-recarregar-servicos").addEventListener("click", carregarServicos);

$("btn-reiniciar-todos-servicos")?.addEventListener("click", async () => {
  if (!confirm("Deseja realmente reiniciar todos os serviços e processos do ecossistema TudoIA?")) return;
  try {
    toast("Reiniciando todos os serviços (Docker, Ollama, ComfyUI)...", "info");
    await api("POST", "/api/servicos/todos/restart");
    toast("Todos os serviços foram reiniciados com sucesso!", "success");
    carregarServicos();
  } catch (e) {
    toast(e.message, "error");
  }
});

// ------------------------------------------------ 2. MODELOS
let cacheModelos = null;
let filtroModeloAtual = "todos";

let historicoTestesModelos = {};
try {
  const salvo = localStorage.getItem("tudoia_testes_modelos");
  if (salvo) historicoTestesModelos = JSON.parse(salvo);
} catch (e) { historicoTestesModelos = {}; }

function salvarResultadoTesteModelo(modeloId, resultado) {
  historicoTestesModelos[modeloId] = resultado;
  try {
    localStorage.setItem("tudoia_testes_modelos", JSON.stringify(historicoTestesModelos));
  } catch (e) {}
}

function criarBarraStatusTeste(salvo) {
  if (!salvo || !salvo.texto) {
    return el("div", { className: "card-status-bar vazio" });
  }
  const isOk = Boolean(salvo.ok);
  return el("div", {
    className: `card-status-bar ${isOk ? 'sucesso' : 'falha'}`,
    title: salvo.detalhe || salvo.texto || "",
    textContent: salvo.texto
  });
}

async function carregarModelos() {
  const grid = $("grid-modelos");
  grid.replaceChildren(el("div", { className: "suave", textContent: "Carregando catálogo de modelos..." }));
  try {
    if (!cacheModelos) {
      cacheModelos = await api("GET", "/api/modelos");
    }
    renderizarModelos();
  } catch (e) {
    grid.replaceChildren(el("div", { className: "toast toast-error", textContent: e.message }));
  }
}

let filtroProvedorModelo = null;  // chave_id do provedor escolhido no subfiltro; null = todos

// Subfiltro de provedores, visível em Todos / Nuvem Free / Nuvem Pagos
function provedoresDoFiltroAtual() {
  return (cacheModelos?.provedores || []).filter(p => {
    if (filtroModeloAtual === "free") return p.tier === "FREE";
    if (filtroModeloAtual === "paid") return p.tier !== "FREE";
    return true;
  });
}

function renderizarSubfiltroProvedores() {
  const barra = $("subfiltro-provedores");
  barra.replaceChildren();
  const visivel = ["todos", "free", "paid"].includes(filtroModeloAtual) && Boolean(cacheModelos);
  barra.style.display = visivel ? "flex" : "none";
  if (!visivel) {
    filtroProvedorModelo = null;  // sem barra visível não há como desfazer a escolha
    return;
  }

  const provedores = provedoresDoFiltroAtual();
  if (filtroProvedorModelo && !provedores.some(p => p.chave_id === filtroProvedorModelo)) {
    filtroProvedorModelo = null;  // provedor saiu do grupo (ex.: trocou de Free para Pagos)
  }

  const botao = (rotulo, valor) => el("button", {
    className: `subtab-btn${filtroProvedorModelo === valor ? " active" : ""}`,
    textContent: rotulo,
    onclick: () => { filtroProvedorModelo = valor; renderizarModelos(); }
  });
  barra.appendChild(botao("Todos os provedores", null));
  for (const p of provedores) {
    barra.appendChild(botao(`${p.nome} (${(p.modelos || []).length})`, p.chave_id));
  }
}

let buscaModelosTermo = "";

function casouBuscaModelos(textoCompleto) {
  if (!buscaModelosTermo) return true;
  const termos = buscaModelosTermo.split(/\s+/).filter(Boolean);
  const alvo = (textoCompleto || "").toLowerCase();
  return termos.every(t => alvo.includes(t));
}

function renderizarModelos() {
  const grid = $("grid-modelos");
  grid.replaceChildren();
  if (!cacheModelos) return;
  renderizarSubfiltroProvedores();

  let cardsExibidos = 0;
  let totalCardsDisponiveis = 0;

  // 1. Locais (Ollama)
  // Com um provedor escolhido no subfiltro, só aparecem os modelos dele (nuvem)
  if ((filtroModeloAtual === "todos" || filtroModeloAtual === "local") && !filtroProvedorModelo) {
    for (const m of cacheModelos.locais || []) {
      totalCardsDisponiveis++;
      const textoBuscaLocal = `${m.nome} ${m.formato} ${m.quantizacao} ${m.familia || ''} ${m.categoria || ''} local ollama gpu`;
      if (!casouBuscaModelos(textoBuscaLocal)) continue;
      cardsExibidos++;
      const badgesTopo = [];
      if (m.em_vram) {
        badgesTopo.push(el("span", { className: "badge badge-vram", textContent: `VRAM ${m.vram_gb} GB` }));
      }
      if (m.ativo === false) {
        badgesTopo.push(el("span", { className: "badge badge-desativado", textContent: "Desativado" }));
      } else {
        badgesTopo.push(el("span", { className: "badge badge-free", textContent: "LOCAL (Ollama)" }));
      }
      if (m.categoria === "Embedding") {
        badgesTopo.push(el("span", { className: "badge badge-role", textContent: "Embedding" }));
      }

      const header = el("div", { className: "card-header" }, [
        el("div", { className: "card-title-group" }, [
          el("span", { className: "card-title", textContent: m.nome }),
          ...badgesTopo
        ]),
        el("span", { style: "font-family:var(--font-mono); font-size:12px; color:var(--text-dim);" }, [`${m.tamanho_gb} GB`])
      ]);
      const desc = el("div", { className: "card-desc", textContent: `Formato: ${m.formato} · Quantização: ${m.quantizacao} · Família: ${m.familia || 'LLM'}` });

      const salvo = historicoTestesModelos[m.nome];
      const statusBar = criarBarraStatusTeste(salvo);

      const btnTestar = el("button", {
        className: "btn btn-outline btn-sm btn-testar-modelo",
        textContent: "Testar",
        title: `Testar inferência rápida no modelo ${m.nome}`,
        onclick: () => testarUmModelo(m.nome, "ollama", statusBar, btnTestar)
      });

      // Botão Liberar VRAM (se estiver carregado)
      const btnLiberarVram = m.em_vram ? el("button", {
        className: "btn btn-outline btn-sm",
        style: "color:var(--warning); border-color:rgba(234, 179, 8, 0.4);",
        textContent: "Ejetar VRAM",
        title: `Descarregar ${m.nome} da memória da GPU`,
        onclick: async () => {
          try {
            btnLiberarVram.disabled = true;
            btnLiberarVram.textContent = "⏳...";
            await api("POST", `/api/modelos/local/${encodeURIComponent(m.nome)}/descarregar`, {});
            toast(`Modelo ${m.nome} descarregado da VRAM!`, "success");
            cacheModelos = null;
            await carregarModelos();
          } catch (err) {
            toast(`Falha ao descarregar VRAM: ${err.message}`, "error");
            btnLiberarVram.disabled = false;
            btnLiberarVram.textContent = "Ejetar VRAM";
          }
        }
      }) : null;

      // Botão Desativar / Ativar
      const isAtivo = m.ativo !== false;
      const btnToggleAtivo = el("button", {
        className: "btn btn-outline btn-sm",
        textContent: isAtivo ? "Desativar" : "Ativar",
        title: isAtivo ? `Desativar ${m.nome} das rotas do LiteLLM` : `Ativar ${m.nome} no LiteLLM`,
        onclick: async () => {
          try {
            btnToggleAtivo.disabled = true;
            await api("POST", `/api/modelos/local/${encodeURIComponent(m.nome)}/toggle-ativo`, {});
            toast(`Modelo ${m.nome} ${isAtivo ? 'desativado' : 'ativado'} com sucesso!`, "info");
            cacheModelos = null;
            await carregarModelos();
          } catch (err) {
            toast(`Falha ao alternar estado: ${err.message}`, "error");
            btnToggleAtivo.disabled = false;
          }
        }
      });

      // Botão Excluir do Disco
      const btnExcluir = el("button", {
        className: "btn btn-outline btn-sm",
        style: "color:var(--danger); border-color:rgba(239, 68, 68, 0.4);",
        textContent: "Excluir",
        title: `Excluir ${m.nome} permanentemente do disco`,
        onclick: async () => {
          if (!confirm(`Atenção: Deseja realmente excluir o modelo '${m.nome}' do disco?\nIsso liberará ${m.tamanho_gb} GB de armazenamento.`)) {
            return;
          }
          try {
            btnExcluir.disabled = true;
            btnExcluir.textContent = "⏳...";
            await api("DELETE", `/api/modelos/local/${encodeURIComponent(m.nome)}`);
            toast(`Modelo ${m.nome} excluído do disco!`, "success");
            cacheModelos = null;
            await carregarModelos();
          } catch (err) {
            toast(`Falha ao excluir modelo: ${err.message}`, "error");
            btnExcluir.disabled = false;
            btnExcluir.textContent = "Excluir";
          }
        }
      });

      const actions = el("div", { className: "card-actions" }, [
        btnTestar,
        ...(btnLiberarVram ? [btnLiberarVram] : []),
        btnToggleAtivo,
        btnExcluir
      ]);
      const footer = el("div", { className: "card-meta" }, [
        actions,
        el("span", { className: "badge badge-role", textContent: "GPU Local" })
      ]);
      const cardClasses = ["card"];
      if (!isAtivo) cardClasses.push("desativado");
      grid.appendChild(el("div", { className: cardClasses.join(" ") }, [header, desc, statusBar, footer]));
    }
  }

  // 2. Nuvem Provedores (OpenRouter, NVIDIA NIM, Groq, Gemini, etc.)
  for (const prov of cacheModelos.provedores || []) {
    const isFree = prov.tier === "FREE";
    if (filtroModeloAtual === "free" && !isFree) continue;
    if (filtroModeloAtual === "paid" && isFree) continue;
    if (filtroModeloAtual === "local") continue;
    if (filtroModeloAtual === "midia") continue;
    if (filtroProvedorModelo && prov.chave_id !== filtroProvedorModelo) continue;

    for (const m of prov.modelos || []) {
      totalCardsDisponiveis++;
      const textoBuscaNuvem = `${m.nome} ${m.id} ${prov.nome} ${prov.chave_id} ${(m.papeis || []).join(' ')} ${prov.tier} nuvem`;
      if (!casouBuscaModelos(textoBuscaNuvem)) continue;
      cardsExibidos++;
      const badgeTier = isFree ? el("span", { className: "badge badge-free", textContent: "FREE" })
                               : el("span", { className: "badge badge-paid", textContent: "PAID" });
      const header = el("div", { className: "card-header" }, [
        el("div", { className: "card-title-group" }, [
          el("span", { className: "card-title", textContent: m.nome }),
          badgeTier
        ]),
        el("span", { style: "font-size:11px; color:var(--text-dim);" }, [prov.nome])
      ]);
      const papeis = (m.papeis || []).map(p => el("span", { className: "badge badge-role", textContent: p }));
      const desc = el("div", { className: "card-desc" }, [
        el("div", { style: "font-size:11px; color:var(--text-dim); margin-bottom:6px;", textContent: `ID: ${m.id}` }),
        el("div", { style: "display:flex; flex-wrap:wrap; gap:4px;" }, papeis)
      ]);

      const salvo = historicoTestesModelos[m.nome] || (m.id && historicoTestesModelos[m.id]);
      const statusBar = criarBarraStatusTeste(salvo);

      // Inativo não está no LiteLLM, então o teste sempre falharia: só testa modelo ativo
      const btnTestar = prov.tem_chave && m.ativo !== false ? el("button", {
        className: "btn btn-outline btn-sm btn-testar-modelo",
        textContent: "Testar",
        title: `Testar completions no gateway LiteLLM para ${m.nome}`,
        onclick: () => testarUmModelo(m.nome, "litellm", statusBar, btnTestar)
      }) : null;

      const actions = el("div", { className: "card-actions" }, btnTestar ? [btnTestar] : []);
      const footer = el("div", { className: "card-meta" }, [
        actions,
        el("span", {
          className: "badge " + (prov.tem_chave ? "badge-free" : "badge-desativado"),
          textContent: prov.tem_chave ? "✓ Chave ativa" : "⚠ Sem chave"
        })
      ]);
      grid.appendChild(el("div", { className: "card" }, [header, desc, statusBar, footer]));
    }
  }

  // Mídia (ComfyUI: Modelos .safetensors/.gguf)
  if ((filtroModeloAtual === "todos" || filtroModeloAtual === "midia") && !filtroProvedorModelo) {
    const modelosMidia = cacheModelos.midia?.modelos || [];

    // Modelos de Vídeo & Imagem instalados no disco (.safetensors / .gguf)
    for (const m of modelosMidia) {
      totalCardsDisponiveis++;
      const textoBuscaMidia = `${m.nome || ''} ${m.arquivo} ${m.motor} ${m.tipo || ''} midia video imagem`;
      if (!casouBuscaModelos(textoBuscaMidia)) continue;
      cardsExibidos++;
      const isAtivo = m.ativo !== false;
      const badgeMotor = isAtivo
        ? el("span", { className: "badge badge-free", textContent: `${m.motor.toUpperCase()}` })
        : el("span", { className: "badge badge-desativado", textContent: "Desativado" });

      const header = el("div", { className: "card-header" }, [
        el("div", { className: "card-title-group" }, [
          el("span", { className: "card-title", title: m.nome, textContent: m.arquivo.length > 32 ? m.arquivo.slice(0, 29) + "..." : m.arquivo }),
          badgeMotor
        ]),
        el("span", { style: "font-family:var(--font-mono); font-size:12px; color:var(--text-dim);", textContent: `${m.tamanho_gb} GB` })
      ]);

      const desc = el("div", { className: "card-desc" }, [
        el("div", { style: "font-size:11px; color:var(--text-dim); margin-bottom:4px; word-break:break-all;", textContent: `Arquivo: ${m.nome}` }),
        el("div", { style: "display:flex; gap:6px; flex-wrap:wrap;" }, [
          el("span", { className: "badge badge-role", textContent: m.categoria }),
          el("span", { className: "badge badge-role", textContent: m.formato.toUpperCase() })
        ])
      ]);

      const salvo = historicoTestesModelos[m.id];
      const statusBar = criarBarraStatusTeste(salvo);
      const btnTestar = el("button", {
        className: "btn btn-outline btn-sm btn-testar-modelo",
        textContent: "Verificar",
        title: `Verificar integridade binária do arquivo ${m.arquivo} no disco`,
        onclick: () => testarUmModelo(m.id, "midia", statusBar, btnTestar)
      });

      const btnToggle = el("button", {
        className: "btn btn-outline btn-sm",
        textContent: isAtivo ? "Desativar" : "Ativar",
        title: isAtivo ? `Desativar modelo ${m.arquivo}` : `Ativar modelo ${m.arquivo}`,
        onclick: async () => {
          try {
            btnToggle.disabled = true;
            await api("POST", `/api/modelos/local/${encodeURIComponent(m.id)}/toggle-ativo`, {});
            toast(`Modelo ${m.arquivo} ${isAtivo ? 'desativado' : 'ativado'}!`, "info");
            cacheModelos = null;
            await carregarModelos();
          } catch (err) {
            toast(`Erro: ${err.message}`, "error");
            btnToggle.disabled = false;
          }
        }
      });

      const btnExcluir = el("button", {
        className: "btn btn-outline btn-sm",
        style: "color:var(--danger); border-color:rgba(239,68,68,0.4);",
        textContent: "Excluir",
        title: `Excluir ${m.arquivo} permanentemente do disco (${m.tamanho_gb} GB)`,
        onclick: async () => {
          if (!confirm(`Atenção: Deseja excluir permanentemente o modelo '${m.arquivo}' do disco?\nIsso liberará ${m.tamanho_gb} GB de espaço.`)) return;
          try {
            btnExcluir.disabled = true;
            await api("DELETE", `/api/modelos/midia/${encodeURIComponent(m.id)}`);
            toast(`Modelo ${m.arquivo} excluído (${m.tamanho_gb} GB liberados)!`, "success");
            cacheModelos = null;
            await carregarModelos();
          } catch (err) {
            toast(`Falha ao excluir modelo: ${err.message}`, "error");
            btnExcluir.disabled = false;
          }
        }
      });

      const actions = el("div", { className: "card-actions" }, [btnTestar, btnToggle, btnExcluir]);
      const footer = el("div", { className: "card-meta" }, [
        actions,
        el("span", { className: "badge badge-role", textContent: m.motor })
      ]);
      const cardClasses = ["card"];
      if (!isAtivo) cardClasses.push("desativado");
      grid.appendChild(el("div", { className: cardClasses.join(" ") }, [header, desc, statusBar, footer]));
    }
  }

  const elContagem = $("contagem-busca-modelos");
  if (elContagem) {
    elContagem.textContent = buscaModelosTermo ? `${cardsExibidos} de ${totalCardsDisponiveis} modelo(s)` : `${totalCardsDisponiveis} modelo(s)`;
  }
  const btnLimpar = $("btn-limpar-busca-modelos");
  if (btnLimpar) {
    btnLimpar.style.display = buscaModelosTermo ? "block" : "none";
  }

  if (cardsExibidos === 0) {
    grid.appendChild(el("div", {
      className: "card",
      style: "grid-column: 1 / -1; text-align: center; padding: 40px 20px; color: var(--text-dim);"
    }, [
      el("p", { style: "font-size: 14px; margin-bottom: 8px;", textContent: buscaModelosTermo ? `Nenhum modelo encontrado para "${buscaModelosTermo}".` : "Nenhum modelo cadastrado nesta categoria." }),
      buscaModelosTermo ? el("button", {
        className: "btn btn-outline btn-sm",
        textContent: "Limpar pesquisa",
        onclick: () => {
          buscaModelosTermo = "";
          const inp = $("input-busca-modelos-catalogo");
          if (inp) inp.value = "";
          renderizarModelos();
        }
      }) : null
    ].filter(Boolean)));
  }
}

async function testarUmModelo(modeloId, tipo, elStatus, elBtn) {
  if (elBtn) elBtn.disabled = true;
  if (elStatus) {
    elStatus.style.display = "flex";
    elStatus.className = "card-status-bar carregando";
    elStatus.textContent = "⏳ Testando latência...";
  }
  try {
    const res = await api("POST", "/api/modelos/testar", { modelo: modeloId, tipo });
    if (res.ok) {
      const respTxt = (res.resposta || '').replace(/\n/g, ' ').trim();
      const preview = respTxt.length > 22 ? respTxt.slice(0, 20) + "..." : respTxt;
      const texto = `✓ ${res.latencia_ms}ms · "${preview}"`;
      salvarResultadoTesteModelo(modeloId, { ok: true, texto, detalhe: res.resposta });
      if (elStatus) {
        elStatus.style.display = "flex";
        elStatus.className = "card-status-bar sucesso";
        elStatus.textContent = texto;
        elStatus.title = `Latência: ${res.latencia_ms}ms | Resposta: ${res.resposta}`;
      }
      return { ok: true, latencia_ms: res.latencia_ms };
    } else {
      let errTxt = (res.erro || 'Falha no teste').replace(/\n/g, ' ').trim();
      const previewErr = errTxt.length > 26 ? errTxt.slice(0, 24) + "..." : errTxt;
      const texto = `✕ ${res.latencia_ms || 0}ms · ${previewErr}`;
      salvarResultadoTesteModelo(modeloId, { ok: false, texto, detalhe: res.erro });
      if (elStatus) {
        elStatus.style.display = "flex";
        elStatus.className = "card-status-bar falha";
        elStatus.textContent = texto;
        elStatus.title = `Erro HTTP ${res.status_http || 0}: ${res.erro}`;
      }
      if (res.desativado_automaticamente) {
        // Sem re-renderizar aqui: o "Testar Todos" ainda tem botões desta tela na fila
        toast(`${modeloId}: o provedor diz que o modelo não existe mais. Inativado e removido do roteamento`, "error");
        cacheModelos = null;
      } else if (res.dica && Date.now() - ultimaDicaTeste > 30000) {
        // Uma vez a cada 30 s: no "Testar Todos" a mesma dica viria de cada modelo
        ultimaDicaTeste = Date.now();
        toast(res.dica, "warning");
      }
      return { ok: false, erro: res.erro };
    }
  } catch (e) {
    const texto = `✕ Erro: ${e.message.slice(0, 24)}`;
    salvarResultadoTesteModelo(modeloId, { ok: false, texto, detalhe: e.message });
    if (elStatus) {
      elStatus.style.display = "flex";
      elStatus.className = "card-status-bar falha";
      elStatus.textContent = texto;
      elStatus.title = e.message;
    }
    return { ok: false, erro: e.message };
  } finally {
    if (elBtn) elBtn.disabled = false;
  }
}

let testandoTodos = false;
let ultimaDicaTeste = 0;
async function testarTodosModelos() {
  if (testandoTodos) return;
  testandoTodos = true;
  const progresso = $("progresso-teste-modelos");
  const btn = $("btn-testar-todos-modelos");
  btn.disabled = true;

  const cards = $$("#grid-modelos .card");
  const fila = [];
  cards.forEach(c => {
    const btnT = c.querySelector(".btn-testar-modelo");
    if (btnT && !btnT.disabled) {
      fila.push(btnT);
    }
  });

  if (fila.length === 0) {
    toast("Nenhum modelo disponível para teste nesta visão.", "info");
    btn.disabled = false;
    testandoTodos = false;
    return;
  }

  let concluidos = 0;
  progresso.textContent = `0 / ${fila.length} testando...`;
  progresso.style.color = "var(--text-muted)";

  for (const btnItem of fila) {
    progresso.textContent = `${concluidos + 1} / ${fila.length} testando...`;
    btnItem.click();
    await new Promise(r => setTimeout(r, 650));
    concluidos++;
  }

  progresso.textContent = `✓ Concluído: ${fila.length} modelos testados!`;
  progresso.style.color = "var(--success)";
  btn.disabled = false;
  testandoTodos = false;
  toast(`Bateria de testes em ${fila.length} modelos concluída!`, "success");
}

$("btn-testar-todos-modelos").addEventListener("click", testarTodosModelos);

$("btn-limpar-historico-testes").addEventListener("click", () => {
  historicoTestesModelos = {};
  try { localStorage.removeItem("tudoia_testes_modelos"); } catch (e) {}
  renderizarModelos();
  toast("Histórico de testes de modelos limpo.", "info");
});

$$("[data-filter-modelo]").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("[data-filter-modelo]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    filtroModeloAtual = btn.dataset.filterModelo;
    renderizarModelos();
  });
});

const inpBuscaCatalogo = $("input-busca-modelos-catalogo");
if (inpBuscaCatalogo) {
  inpBuscaCatalogo.addEventListener("input", (e) => {
    buscaModelosTermo = e.target.value.trim().toLowerCase();
    renderizarModelos();
  });
}
const btnLimparBuscaCatalogo = $("btn-limpar-busca-modelos");
if (btnLimparBuscaCatalogo) {
  btnLimparBuscaCatalogo.addEventListener("click", () => {
    buscaModelosTermo = "";
    if (inpBuscaCatalogo) inpBuscaCatalogo.value = "";
    renderizarModelos();
  });
}

// ------------------------------------------------ 3. ROTEADOR
let dadosRoteadorCache = null;
let ordemGruposEdicao = {};
let alteracoesPendentesRoteador = false;

function atualizarEstadoPendenciasRoteador(pendente) {
  alteracoesPendentesRoteador = Boolean(pendente);
  const badge = $("badge-roteador-pendente");
  const banner = $("aviso-banner-roteador-pendente");
  const btnSalvar = $("btn-salvar-ordem-roteador");

  if (badge) badge.style.display = alteracoesPendentesRoteador ? "inline-flex" : "none";
  if (banner) banner.style.display = alteracoesPendentesRoteador ? "block" : "none";
  if (btnSalvar) {
    if (alteracoesPendentesRoteador) {
      btnSalvar.classList.add("btn-salvar-pendente");
      btnSalvar.textContent = "Salvar Grupos *";
    } else {
      btnSalvar.classList.remove("btn-salvar-pendente");
      btnSalvar.textContent = "Salvar Grupos";
    }
  }
}

async function carregarRoteador() {
  const container = $("container-roteador-grupos");
  container.replaceChildren(el("div", { className: "suave", textContent: "Carregando regras de roteamento..." }));
  try {
    const rot = await api("GET", "/api/roteador/detalhes");
    dadosRoteadorCache = rot;

    // Inicializa estado de edição local
    ordemGruposEdicao = {};
    for (const g of rot.grupos || []) {
      ordemGruposEdicao[g.id] = (g.membros || []).map(m => m.nome);
    }

    atualizarEstadoPendenciasRoteador(false);
    renderizarGruposRoteador();
    atualizarSelectGruposTesteRoteador(rot.grupos);
  } catch (e) {
    container.replaceChildren(el("div", { className: "toast toast-error", textContent: e.message }));
  }
}

function atualizarSelectGruposTesteRoteador(grupos) {
  const select = $("select-teste-roteador-grupo");
  const btn = $("btn-executar-teste-roteador");
  if (!select) return;
  const valorAtual = select.value;
  select.innerHTML = "";

  const listaGrupos = grupos || [];
  if (listaGrupos.length === 0) {
    const optVazio = document.createElement("option");
    optVazio.value = "";
    optVazio.textContent = "Nenhum grupo de roteamento cadastrado";
    optVazio.disabled = true;
    optVazio.selected = true;
    select.appendChild(optVazio);
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Nenhum grupo para enviar (:4000)";
    }
    return;
  }

  if (btn) {
    btn.disabled = false;
  }

  // 1. Orquestração Inteligente (só se houver grupos cadastrados para os quais rotear)
  const gAuto = document.createElement("optgroup");
  gAuto.label = "Orquestração Inteligente (tudoia-auto)";
  const optAuto = document.createElement("option");
  optAuto.value = "tudoia-auto";
  optAuto.textContent = "tudoia-auto  ·  Decisão Automática (kNN semântico + regras)";
  gAuto.appendChild(optAuto);
  select.appendChild(gAuto);

  // 2. Grupos de Roteamento Efetivamente Cadastrados
  const gCadastrados = document.createElement("optgroup");
  gCadastrados.label = `Grupos Cadastrados (${listaGrupos.length})`;

  listaGrupos.forEach(g => {
    const isAtivo = g.ativo !== false;
    const opt = document.createElement("option");
    opt.value = g.id;
    const qtdMembros = (ordemGruposEdicao[g.id] || g.membros || []).length;
    const statusTxt = isAtivo ? "" : " [DESATIVADO]";
    opt.textContent = `${g.id}  ·  ${g.titulo || g.id} (${qtdMembros} modelo${qtdMembros === 1 ? '' : 's'})${statusTxt}`;
    gCadastrados.appendChild(opt);
  });
  select.appendChild(gCadastrados);

  // Restaura valor selecionado se existir
  const existe = Array.from(select.options).some(o => o.value === valorAtual && !o.disabled);
  select.value = existe ? valorAtual : "tudoia-auto";
  atualizarBotaoTesteRoteador();
}

function atualizarBotaoTesteRoteador() {
  const select = $("select-teste-roteador-grupo");
  const btn = $("btn-executar-teste-roteador");
  if (!select || !btn) return;
  const val = select.value;
  if (!val) {
    btn.disabled = true;
    btn.textContent = "Nenhum grupo para enviar (:4000)";
    return;
  }
  btn.disabled = false;
  btn.textContent = `Enviar para ${val} (:4000)`;
}

function renderizarGruposRoteador() {
  const container = $("container-roteador-grupos");
  container.replaceChildren();

  const rot = dadosRoteadorCache;
  if (!rot) return;

  const info = el("div", { style: "display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; font-size:12px; color:var(--text-muted); background:var(--bg-subtle); padding:10px 14px; border-radius:var(--radius-sm); border:1px solid var(--border-color);" }, [
    el("div", { style: "display:flex; gap:16px;" }, [
      el("span", {}, ["Limiar de Roteamento Nuvem: ", el("strong", { style:"color:var(--text-primary);", textContent: rot.limiar })]),
      el("span", {}, ["Teto de Turnos: ", el("strong", { style:"color:var(--text-primary);", textContent: rot.limites_texto.turnos || 8 })]),
      el("span", {}, ["Estratégia de Gateway: ", el("strong", { style:"color:var(--brand-primary);", textContent: "latency-based-routing" })])
    ]),
    el("span", { style: "font-size:11px; color:var(--text-dim);", textContent: "Quarentena automática de 60s em caso de 429/timeout" })
  ]);
  container.appendChild(info);

  const listaGrupos = rot.grupos || [];
  if (listaGrupos.length === 0) {
    const cardVazio = el("div", {
      style: "text-align:center; padding:36px 16px; background:var(--bg-surface); border:1px dashed var(--border-color); border-radius:var(--radius-md); color:var(--text-muted); font-size:13px;"
    }, [
      el("div", { style: "font-size:26px; margin-bottom:8px;", textContent: "📭" }),
      el("div", { style: "font-weight:600; color:var(--text-primary); margin-bottom:4px; font-size:14px;", textContent: "Nenhum grupo de roteamento cadastrado" }),
      el("div", { style: "font-size:12px; color:var(--text-dim); margin-bottom:16px; max-width:400px; margin-left:auto; margin-right:auto;", textContent: "Crie grupos de fallback ou utilize a auto-vinculação para definir rotas do LiteLLM Gateway." }),
      el("button", {
        className: "btn btn-primary btn-sm",
        textContent: "+ Criar Primeiro Grupo",
        onclick: () => {
          const btnNovo = $("btn-modal-novo-grupo");
          if (btnNovo) btnNovo.click();
        }
      })
    ]);
    container.appendChild(cardVazio);
    return;
  }

  for (const g of listaGrupos) {
    const membrosNomes = ordemGruposEdicao[g.id] || [];
    const isAtivo = g.ativo !== false;

    // Header do grupo
    const badgeTier = el("span", { className: `badge badge-${g.tier.toLowerCase()}`, textContent: g.tier });
    const badgesHeader = [badgeTier];
    if (!isAtivo) {
      badgesHeader.push(el("span", { className: "badge badge-desativado", textContent: "Desativado" }));
    }

    const btnEditarGrupo = el("button", {
      className: "btn btn-outline btn-sm",
      style: "padding:2px 8px; font-size:11px;",
      textContent: "Editar",
      title: "Editar título, descrição ou ativar/desativar este grupo",
      onclick: () => abrirModalEditarGrupo(g)
    });

    const btnExcluirGrupo = (g.pode_excluir !== false) ? el("button", {
      className: "btn btn-outline btn-sm",
      style: "padding:2px 8px; font-size:11px; color:var(--danger); border-color:rgba(239,68,68,0.3);",
      textContent: "Excluir",
      title: "Excluir este grupo de roteamento",
      onclick: async () => {
        if (!confirm(`Tem certeza que deseja excluir o grupo '${g.id}' (${g.titulo})?`)) {
          return;
        }
        try {
          btnExcluirGrupo.disabled = true;
          await api("DELETE", `/api/roteador/grupos/${encodeURIComponent(g.id)}`);
          toast(`Grupo '${g.id}' excluído com sucesso!`, "success");
          await carregarRoteador();
        } catch (err) {
          toast(`Falha ao excluir grupo: ${err.message}`, "error");
          btnExcluirGrupo.disabled = false;
        }
      }
    }) : null;

    const grupoAcoes = el("div", { style: "display:flex; align-items:center; gap:6px;" }, [
      el("span", { className: "badge", style: "background:rgba(255,255,255,0.05); font-family:var(--font-mono); font-size:11px;", textContent: `${membrosNomes.length} modelo(s)` }),
      btnEditarGrupo,
      ...(btnExcluirGrupo ? [btnExcluirGrupo] : [])
    ]);

    const header = el("div", { className: "grupo-roteador-header" }, [
      el("div", {}, [
        el("div", { style: "display:flex; align-items:center; gap:8px;" }, [
          el("h4", { style: "margin:0; font-size:14px; color:var(--brand-primary); font-family:var(--font-mono);", textContent: g.id }),
          ...badgesHeader
        ]),
        el("div", { style: "font-size:12px; font-weight:600; color:var(--text-primary); margin-top:3px;", textContent: g.titulo }),
        el("div", { style: "font-size:11px; color:var(--text-muted); margin-top:2px;", textContent: g.descricao })
      ]),
      grupoAcoes
    ]);

    // Lista de membros ativos
    const listaMembros = el("div", { className: "grupo-membros-lista" });
    const membrosMap = new Map((g.membros || []).map(m => [m.nome, m]));

    if (membrosNomes.length === 0) {
      listaMembros.appendChild(el("div", {
        style: "font-size:12px; color:var(--warning); font-style:italic; padding:10px 12px; background:rgba(234, 179, 8, 0.08); border-radius:var(--radius-sm); border:1px dashed rgba(234, 179, 8, 0.3);",
        textContent: "⚠ Nenhum modelo configurado neste grupo (o LiteLLM acionará o fallback padrão do sistema)."
      }));
    } else {
      membrosNomes.forEach((nomeModelo, idx) => {
        const itemMembro = el("div", { className: `grupo-membro-item${idx === 0 ? " principal" : ""}` });
        const mMeta = membrosMap.get(nomeModelo) || {};
        const isLocal = mMeta.origem === "local" || mMeta.provedor_id === "local" || nomeModelo.startsWith("local/");
        const provNome = isLocal ? "Ollama Local" : (mMeta.provedor_nome || "Nuvem");
        const tierNome = isLocal ? "LOCAL" : (mMeta.tier || "FREE");
        const papeisTxt = (mMeta.papeis && mMeta.papeis.length) ? mMeta.papeis.join(", ") : "";
        const ctxTxt = mMeta.contexto ? `${Math.round(mMeta.contexto / 1000)}k ctx` : "";

        const badgePrioridade = el("span", {
          className: idx === 0 ? "badge-prioridade-principal" : "badge-prioridade-fallback",
          textContent: idx === 0 ? "#1 Principal" : `#${idx + 1} Fallback ${idx}`
        });

        const badgeOrigem = el("span", {
          className: isLocal ? "badge-origem-local" : "badge-origem-nuvem",
          textContent: isLocal ? "🏠 Local" : `🌐 ${provNome} (${tierNome})`
        });

        const infoMembro = el("div", { style: "display:flex; align-items:center; gap:8px; flex-wrap:wrap;" }, [
          badgePrioridade,
          badgeOrigem,
          el("strong", { style: "color:var(--text-primary); font-size:12px;", textContent: nomeModelo }),
          ...(papeisTxt || ctxTxt ? [
            el("span", { style: "font-size:11px; color:var(--text-dim); font-family:var(--font-sans);", textContent: `· [${papeisTxt}] ${ctxTxt}` })
          ] : [])
        ]);

        const btnsAcao = el("div", { style: "display:flex; gap:4px; align-items:center;" }, [
          el("button", {
            className: "btn-ordem",
            textContent: "▲",
            title: "Subir prioridade deste modelo no fallback",
            disabled: idx === 0,
            onclick: () => moverMembroGrupo(g.id, idx, -1)
          }),
          el("button", {
            className: "btn-ordem",
            textContent: "▼",
            title: "Descer prioridade deste modelo no fallback",
            disabled: idx === membrosNomes.length - 1,
            onclick: () => moverMembroGrupo(g.id, idx, 1)
          }),
          el("button", {
            className: "btn-ordem",
            style: "color:var(--danger); border-color:rgba(239,68,68,0.3); margin-left:6px; font-weight:700;",
            textContent: "✕",
            title: "Remover modelo deste grupo",
            onclick: () => removerMembroGrupo(g.id, idx)
          })
        ]);

        itemMembro.appendChild(infoMembro);
        itemMembro.appendChild(btnsAcao);
        listaMembros.appendChild(itemMembro);
      });
    }

    // Área para vincular novos modelos ao grupo manualmente
    const membrosSet = new Set(membrosNomes);
    const elegiveis = (g.modelos_elegiveis || []).filter(m => !membrosSet.has(m.nome));

    const formAdicionar = el("div", { style: "display:flex; gap:10px; align-items:center; margin-top:14px; padding-top:12px; border-top:1px dashed var(--border-color); flex-wrap:wrap;" });

    if (elegiveis.length > 0) {
      const selectModelos = el("select", {
        className: "select-adicionar-membro",
        style: "flex:1; min-width:280px; padding:7px 10px; font-size:12px; font-family:var(--font-mono); border:1px solid var(--border-color); border-radius:var(--radius-sm); background:var(--bg-surface); color:var(--text-primary);"
      });

      // 1. Modelos Recomendados (casam papel e tier)
      const recomendados = elegiveis.filter(m => m.recomendado);
      if (recomendados.length > 0) {
        const optgroupRec = document.createElement("optgroup");
        optgroupRec.label = `⭐ Recomendados para este Grupo (${recomendados.length})`;
        recomendados.forEach(m => {
          const opt = document.createElement("option");
          opt.value = m.nome;
          const papeisTxt = (m.papeis || []).join(", ");
          const origemTxt = m.origem === "local" ? "Ollama Local" : (m.provedor_nome || "Nuvem");
          opt.textContent = `⭐ ${m.nome}  ·  [${papeisTxt}] (${origemTxt})`;
          optgroupRec.appendChild(opt);
        });
        selectModelos.appendChild(optgroupRec);
      }

      // 2. Modelos Locais Ollama (não recomendados diretamente, mas disponíveis)
      const locaisDisponiveis = elegiveis.filter(m => !m.recomendado && (m.origem === "local" || m.nome.startsWith("local/")));
      if (locaisDisponiveis.length > 0) {
        const optgroupLoc = document.createElement("optgroup");
        optgroupLoc.label = `🏠 Modelos Locais Ollama (${locaisDisponiveis.length})`;
        locaisDisponiveis.forEach(m => {
          const opt = document.createElement("option");
          opt.value = m.nome;
          const papeisTxt = (m.papeis || []).join(", ");
          opt.textContent = `🏠 ${m.nome}  ·  [${papeisTxt}] (Ollama Local)`;
          optgroupLoc.appendChild(opt);
        });
        selectModelos.appendChild(optgroupLoc);
      }

      // 3. Outros Modelos de Nuvem (agrupados por provedor)
      const outrosNuvem = elegiveis.filter(m => !m.recomendado && m.origem !== "local" && !m.nome.startsWith("local/"));
      const porProvedor = {};
      outrosNuvem.forEach(m => {
        const provNome = m.provedor_nome || "Nuvem";
        if (!porProvedor[provNome]) porProvedor[provNome] = [];
        porProvedor[provNome].push(m);
      });

      Object.entries(porProvedor).forEach(([provNome, listaMods]) => {
        const grupoOpt = document.createElement("optgroup");
        const tier = listaMods[0]?.tier || "FREE";
        grupoOpt.label = `🌐 Provedor: ${provNome} (${tier})`;
        listaMods.forEach(m => {
          const opt = document.createElement("option");
          opt.value = m.nome;
          const papeisTxt = (m.papeis || []).join(", ");
          opt.textContent = `🌐 ${m.nome}  ·  [${papeisTxt}]`;
          grupoOpt.appendChild(opt);
        });
        selectModelos.appendChild(grupoOpt);
      });

      const btnAdd = el("button", {
        className: "btn btn-primary btn-sm",
        style: "padding:8px 14px; font-size:12px; white-space:nowrap; display:flex; align-items:center; gap:6px;",
        textContent: "+ Vincular ao Grupo",
        onclick: () => {
          adicionarMembroGrupo(g.id, selectModelos.value);
        }
      });

      formAdicionar.appendChild(selectModelos);
      formAdicionar.appendChild(btnAdd);
    } else {
      formAdicionar.appendChild(el("span", {
        style: "font-size:12px; color:var(--text-dim); display:flex; align-items:center; gap:6px;",
        textContent: "✓ Todos os modelos disponíveis no ecossistema já estão vinculados a este grupo."
      }));
    }

    const classesCard = ["grupo-roteador-card"];
    if (!isAtivo) classesCard.push("desativado");
    const cardGrupo = el("div", { className: classesCard.join(" ") }, [header, listaMembros, formAdicionar]);
    container.appendChild(cardGrupo);
  }
}

function moverMembroGrupo(grupoId, indice, direcao) {
  const lista = ordemGruposEdicao[grupoId];
  if (!lista) return;
  const novoIndice = indice + direcao;
  if (novoIndice < 0 || novoIndice >= lista.length) return;
  const temp = lista[indice];
  lista[indice] = lista[novoIndice];
  lista[novoIndice] = temp;
  atualizarEstadoPendenciasRoteador(true);
  renderizarGruposRoteador();
}

function removerMembroGrupo(grupoId, indice) {
  const lista = ordemGruposEdicao[grupoId];
  if (!lista) return;
  lista.splice(indice, 1);
  atualizarEstadoPendenciasRoteador(true);
  renderizarGruposRoteador();
}

function adicionarMembroGrupo(grupoId, nomeModelo) {
  if (!nomeModelo) return;
  const lista = ordemGruposEdicao[grupoId] || [];
  if (!lista.includes(nomeModelo)) {
    lista.push(nomeModelo);
    ordemGruposEdicao[grupoId] = lista;
    atualizarEstadoPendenciasRoteador(true);
    renderizarGruposRoteador();
  }
}

$("btn-salvar-ordem-roteador").addEventListener("click", async () => {
  try {
    toast("Salvando nova composição de grupos do roteador...", "info");
    await api("PUT", "/api/roteador/grupos", { ordem: ordemGruposEdicao });
    toast("✓ Composição dos grupos salva e aplicada no LiteLLM com sucesso!", "success");
    atualizarEstadoPendenciasRoteador(false);
    await carregarRoteador();
  } catch (e) {
    toast(`Erro ao salvar grupos: ${e.message}`, "error");
  }
});

$("btn-auto-bind-roteador").addEventListener("click", async () => {
  try {
    toast("Executando auto-vinculação de modelos aos grupos por papéis...", "info");
    const r = await api("POST", "/api/roteador/auto-bind");
    toast(`✓ Auto-vinculação concluída! ${r.modelos_vinculados} modelo(s) organizados nos grupos.`, "success");
    atualizarEstadoPendenciasRoteador(false);
    await carregarRoteador();
  } catch (e) {
    toast(`Erro na auto-vinculação: ${e.message}`, "error");
  }
});

$("btn-gerar-roteador").addEventListener("click", async () => {
  try {
    toast("Gerando config.yaml do LiteLLM a partir do catálogo...", "info");
    const r = await api("POST", "/api/roteador/gerar");
    toast(`Config gerado com sucesso! ${r.modelos} modelos mapeados. Reinicie o LiteLLM para aplicar.`, "success");
  } catch (e) { toast(e.message, "error"); }
});

const selectGrupoTeste = $("select-teste-roteador-grupo");
if (selectGrupoTeste) {
  selectGrupoTeste.addEventListener("change", atualizarBotaoTesteRoteador);
}

$("btn-executar-teste-roteador").addEventListener("click", async () => {
  const input = $("input-teste-roteador");
  const select = $("select-teste-roteador-grupo");
  const saida = $("resultado-teste-roteador");
  const msg = input.value.trim();
  const grupoAlvo = select ? (select.value || "tudoia-auto") : "tudoia-auto";
  if (!msg) { toast("Digite uma mensagem para testar", "warning"); return; }

  const btn = $("btn-executar-teste-roteador");
  btn.disabled = true;
  saida.innerHTML = `
    <div class="resultado-teste-box" style="align-items:center; justify-content:center; padding:20px;">
      <span style="font-size:20px; animation:spin 1s linear infinite;">⏳</span>
      <span style="font-size:12px; color:var(--text-muted); margin-top:8px;">Consultando gateway LiteLLM em :4000 (${esc(grupoAlvo)})...</span>
</div>
  `;

  try {
    const res = await api("POST", "/api/roteador/testar", { mensagem: msg, modelo: grupoAlvo });
    if (res.ok) {
      saida.innerHTML = `
        <div class="resultado-teste-box">
          <div class="resultado-teste-meta">
            <div style="display:flex; align-items:center; gap:6px;">
              <span class="badge badge-success" style="font-size:10px;">✓ HTTP 200</span>
              <span style="font-family:var(--font-mono); font-size:11px; color:var(--brand-primary); font-weight:600;">${esc(res.modelo_usado)}</span>
</div>
            <span class="badge" style="background:rgba(99,102,241,0.15); color:var(--brand-primary); font-family:var(--font-mono); font-size:10px;"> ${esc(res.latencia_ms)}ms</span>
</div>
          <div style="font-size:11px; color:var(--text-dim); display:flex; gap:12px;">
            <span>Rota solicitada: <strong style="color:var(--text-muted);">${esc(res.modelo_solicitado || grupoAlvo)}</strong></span>
</div>
          <div class="resultado-teste-corpo">${esc(res.resposta || "(Resposta vazia)")}</div>
</div>
      `;
    } else {
      saida.innerHTML = `
        <div class="resultado-teste-box" style="border-color:rgba(239,68,68,0.4);">
          <div class="resultado-teste-meta">
            <span class="badge badge-danger" style="font-size:10px;">✕ Erro HTTP ${esc(res.status_http || "")}</span>
            <span class="badge" style="background:rgba(239,68,68,0.15); color:var(--danger); font-family:var(--font-mono); font-size:10px;"> ${esc(res.latencia_ms || 0)}ms</span>
</div>
          <div style="font-size:11px; color:var(--text-dim);">Rota: <strong style="color:var(--text-muted);">${esc(res.modelo_solicitado || grupoAlvo)}</strong></div>
          <div class="resultado-teste-corpo" style="color:var(--danger);">${esc(res.erro || "Falha desconhecida")}</div>
</div>
      `;
    }
  } catch (e) {
    saida.innerHTML = `
      <div class="resultado-teste-box" style="border-color:rgba(239,68,68,0.4);">
        <div class="resultado-teste-meta">
          <span class="badge badge-danger" style="font-size:10px;">✕ Falha de Conexão</span>
</div>
        <div class="resultado-teste-corpo" style="color:var(--danger);">${esc(e.message)}</div>
</div>
    `;
  } finally {
    btn.disabled = false;
  }
});

// ------------------------------------------------ 4. GOVERNANÇA
async function carregarGovernanca() {
  const grid = $("grid-governanca");
  grid.replaceChildren(el("div", { className: "suave", textContent: "Carregando governança..." }));
  try {
    const g = await api("GET", "/api/governanca");
    const badgeDrift = $("badge-drift");
    const totalAlertasMcp = g.alertas_mcp ? Object.keys(g.alertas_mcp).length : 0;
    if (totalAlertasMcp > 0) {
      badgeDrift.className = "badge badge-paid";
      badgeDrift.textContent = `⚠ ${totalAlertasMcp} MCP com chave pendente`;
    } else if (g.drift && g.drift.length > 0) {
      badgeDrift.className = "badge badge-paid";
      badgeDrift.textContent = `${g.drift.length} arquivo(s) fora de sincronia`;
    } else {
      badgeDrift.className = "badge badge-free";
      badgeDrift.textContent = "✓ Sincronizado (Zero Drift)";
    }

    grid.replaceChildren();

    const secoes = [
      { id: "regras", titulo: "Regras Canônicas de Engenharia", desc: "Diretrizes System-First, Ponytail e padrões aplicados no início de cada sessão." },
      { id: "skills", titulo: "Skills Procedurais Modulares", desc: "Procedimentos executáveis de TDD disciplinado, módulos profundos, revisão e hardening." },
      { id: "mcp", titulo: "Servidores Model Context Protocol (MCP)", desc: "Ferramentas conectadas aos agentes para arquivos, banco, documentação viva e browser." }
    ];

    for (const sec of secoes) {
      const itens = g[sec.id] || {};
      const entries = Object.entries(itens);
      const totalAtivos = entries.filter(([_, ativo]) => ativo).length;

      const listaCards = entries.map(([nomeItem, ativo]) => {
        const switchInput = el("input", {
          type: "checkbox",
          checked: Boolean(ativo),
          onchange: async () => {
            const novoEstado = switchInput.checked;
            try {
              switchInput.disabled = true;
              await api("PUT", `/api/governanca/${sec.id}/${nomeItem}`, { ativo: novoEstado });
              toast(`${nomeItem} ${novoEstado ? "ativado" : "desativado"}`, "success");
              carregarGovernanca();
            } catch (e) {
              switchInput.checked = !novoEstado;
              switchInput.disabled = false;
              toast(e.message, "error");
            }
          }
        });

        const switchLabel = el("label", {
          className: "switch",
          title: ativo ? "Clique para desativar" : "Clique para ativar",
          style: "margin: 0 4px;"
        }, [
          switchInput,
          el("span", { className: "slider" })
        ]);

        const statusTeste = el("div", {
          className: "gov-status-row",
          style: "display: none;"
        });

        const btnTestar = sec.id === "mcp" ? el("button", {
          className: "btn btn-outline btn-sm btn-testar-mcp",
          style: "padding: 3px 10px; font-size: 11px; border-radius: 6px; font-weight: 500;",
          textContent: "Testar",
          title: `Testar conexão do servidor MCP ${nomeItem}`,
          onclick: () => testarUmMcp(nomeItem, statusTeste, btnTestar)
        }) : null;

        const btnVerCodigo = el("button", {
          className: "btn btn-outline btn-sm",
          style: "padding: 3px 10px; font-size: 11px; border-radius: 6px; color: var(--text-main); font-weight: 500;",
          textContent: " Código",
          title: `Visualizar código fonte de ${nomeItem}`,
          onclick: () => abrirModalVerCodigo(sec.id, nomeItem, sec.titulo)
        });

        const btnExcluir = el("button", {
          className: "btn btn-outline btn-sm",
          style: "padding: 3px 10px; font-size: 11px; border-radius: 6px; color: var(--danger); border-color: rgba(239, 68, 68, 0.35); background: rgba(239, 68, 68, 0.05); font-weight: 500;",
          textContent: "Excluir",
          title: `Excluir permanentemente ${nomeItem}`,
          onclick: async () => {
            if (!confirm(`Deseja realmente excluir permanentemente '${nomeItem}' de ${sec.titulo}?`)) return;
            try {
              btnExcluir.disabled = true;
              btnExcluir.textContent = "...";
              await api("DELETE", `/api/governanca/${sec.id}/${nomeItem}`);
              toast(`'${nomeItem}' foi excluído com sucesso!`, "success");
              carregarGovernanca();
            } catch (e) {
              toast(e.message, "error");
              btnExcluir.disabled = false;
              btnExcluir.textContent = "Excluir";
            }
          }
        });

        const avisosInfo = [];
        if (!ativo) {
          avisosInfo.push(el("span", {
            className: "badge",
            style: "font-size: 10px; padding: 1px 6px; background: rgba(255,255,255,0.06); color: var(--text-dim);",
            textContent: "Inativo"
          }));
        }

        const mcpCfg = (sec.id === "mcp" && g.mcp_configs) ? g.mcp_configs[nomeItem] : null;
        if (mcpCfg && mcpCfg.auth === "oauth") {
          avisosInfo.push(el("span", {
            className: "badge",
            style: "font-size: 11px; padding: 2px 8px; background: rgba(59, 130, 246, 0.15); color: var(--accent); border: 1px solid rgba(59, 130, 246, 0.35); font-weight: 600; display: inline-flex; align-items: center; gap: 4px;",
            title: "Servidor configurado para autenticação dinâmica via OAuth 2.0 pelo cliente de IA"
          }, [
            el("span", { textContent: "" }),
            el("span", { textContent: "OAuth 2.0" })
          ]));
        } else if (sec.id === "mcp" && g.alertas_mcp && g.alertas_mcp[nomeItem]) {
          const chavesPendentes = g.alertas_mcp[nomeItem];
          avisosInfo.push(el("span", {
            className: "badge",
            style: "font-size: 11px; padding: 2px 8px; background: rgba(245, 158, 11, 0.15); color: var(--warning); border: 1px solid rgba(245, 158, 11, 0.35); font-weight: 600; display: inline-flex; align-items: center; gap: 4px; cursor: pointer;",
            title: `Chave(s) obrigatória(s) não configurada(s) no .env: ${chavesPendentes.join(", ")}. Clique para ir ao Cofre de Segredos.`,
            onclick: (ev) => {
              ev.stopPropagation();
              navegarParaSegredo(chavesPendentes[0]);
            }
          }, [
            el("span", { textContent: "⚠" }),
            el("span", { textContent: `Chave pendente: ${chavesPendentes.join(", ")}` })
          ]));

          statusTeste.className = "gov-status-row gov-status-error";
          statusTeste.style.display = "flex";
          statusTeste.style.justifyContent = "space-between";
          statusTeste.style.alignItems = "center";
          statusTeste.style.borderColor = "rgba(245, 158, 11, 0.35)";
          statusTeste.style.background = "rgba(245, 158, 11, 0.08)";
          statusTeste.style.color = "var(--warning)";
          statusTeste.replaceChildren(
            el("span", { textContent: `⚠ Variável obrigatória '${chavesPendentes.join(", ")}' não configurada no .env` }),
            el("a", {
              href: "#segredos",
              style: "color: var(--accent); text-decoration: underline; font-weight: 500; font-size: 11px; cursor: pointer;",
              textContent: "Configurar Chave no Cofre de Segredos →",
              onclick: (ev) => {
                ev.preventDefault();
                navegarParaSegredo(chavesPendentes[0]);
              }
            })
          );
        }

        const ladoEsquerdo = el("div", { className: "gov-item-info" }, [
          el("span", { className: "gov-item-name", textContent: nomeItem }),
          ...avisosInfo
        ]);

        const acoesDireita = el("div", { className: "gov-item-actions" }, [
          btnTestar,
          btnVerCodigo,
          switchLabel,
          btnExcluir
        ]);

        const headerLinha = el("div", { className: "gov-item-header" }, [
          ladoEsquerdo,
          acoesDireita
        ]);

        return el("div", {
          className: "gov-item",
          style: `opacity: ${ativo ? "1" : "0.6"};`
        }, [
          headerLinha,
          statusTeste
        ]);
      });

      const card = el("div", {
        className: `card ${sec.id === "mcp" ? "card-gov-mcp" : ""}`
      }, [
        el("div", { className: "card-header" }, [
          el("div", { style: "display: flex; align-items: center; gap: 10px;" }, [
            el("span", { className: "card-title", textContent: sec.titulo }),
            el("span", {
              className: "badge badge-free",
              style: "font-size: 11px; font-weight: 600;",
              textContent: `${totalAtivos}/${entries.length} ativos`
            })
          ])
        ]),
        el("div", { className: "card-desc", style: "color: var(--text-dim); font-size: 12px;", textContent: sec.desc }),
        el("div", { style: "margin-top: 12px;" }, listaCards)
      ]);
      grid.appendChild(card);
    }
  } catch (e) {
    grid.replaceChildren(el("div", { className: "toast toast-error", textContent: e.message }));
  }
}

async function sincronizarClientesGlobal() {
  try {
    toast("Sincronizando regras, skills e MCPs para todas as instâncias de clientes ativas...", "info");
    const r = await api("POST", "/api/governanca/sincronizar");
    toast("Clientes multi-agente sincronizados com sucesso!", "success");
    if (subabaGovernancaAtual === "instancias") {
      carregarInstanciasGovernanca();
    } else {
      carregarGovernanca();
    }
  } catch (e) { toast(e.message, "error"); }
}

$("btn-sync-governanca").addEventListener("click", sincronizarClientesGlobal);
$("btn-sync-global").addEventListener("click", sincronizarClientesGlobal);

// Sub-abas de Governança
let subabaGovernancaAtual = "componentes";

$$("#subtabs-governanca .subtab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    $$("#subtabs-governanca .subtab-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    subabaGovernancaAtual = btn.dataset.subtabGov;
    const viewComp = $("gov-subview-componentes");
    const viewInst = $("gov-subview-instancias");
    if (subabaGovernancaAtual === "componentes") {
      viewComp.style.display = "block";
      viewInst.style.display = "none";
      carregarGovernanca();
    } else {
      viewComp.style.display = "none";
      viewInst.style.display = "block";
      carregarInstanciasGovernanca();
    }
  });
});

function obterIconeCliente(cliente) {
  switch (cliente) {
    case "claude": return "🟣";
    case "antigravity": return "🔵";
    case "cursor": return "🔷";
    case "codex": return "📜";
    default: return "📁";
  }
}

function criarCardInstancia(inst) {
  const switchInput = el("input", {
    type: "checkbox",
    checked: Boolean(inst.ativo),
    onchange: async () => {
      const novoEstado = switchInput.checked;
      try {
        switchInput.disabled = true;
        await api("PUT", `/api/governanca/instancias/${inst.id}`, { ativo: novoEstado });
        toast(`Instância '${inst.nome}' ${novoEstado ? "ativada" : "desativada"} para sincronização`, "success");
        carregarInstanciasGovernanca();
      } catch (e) {
        switchInput.checked = !novoEstado;
        switchInput.disabled = false;
        toast(e.message, "error");
      }
    }
  });

  const switchLabel = el("label", {
    className: "switch",
    title: inst.ativo ? "Instância ativa (recebe sincronização)" : "Instância inativa (ignorada na sincronização)"
  }, [
    switchInput,
    el("span", { className: "slider" })
  ]);

  const badgeDisco = el("span", {
    className: `badge ${inst.existe_disco ? "badge-free" : "badge-paid"}`,
    style: "font-size: 11px;",
    textContent: inst.existe_disco ? "✓ Disco OK" : "⚠ Caminho Ausente"
  });

  const btnEditar = el("button", {
    className: "btn btn-outline btn-sm",
    style: "padding: 3px 10px; font-size: 11px;",
    textContent: "Editar",
    onclick: () => abrirModalEditarInstancia(inst)
  });

  const btnExcluir = el("button", {
    className: "btn btn-outline btn-sm",
    style: "padding: 3px 10px; font-size: 11px; color: var(--danger); border-color: rgba(239, 68, 68, 0.35);",
    textContent: "Remover",
    onclick: async () => {
      if (!confirm(`Deseja remover a instância '${inst.nome}' (${inst.id}) da governança canônica?`)) return;
      try {
        btnExcluir.disabled = true;
        await api("DELETE", `/api/governanca/instancias/${inst.id}`);
        toast(`Instância '${inst.nome}' removida!`, "success");
        carregarInstanciasGovernanca();
      } catch (e) {
        btnExcluir.disabled = false;
        toast(e.message, "error");
      }
    }
  });

  return el("div", { className: "card", style: "display: flex; flex-direction: column; justify-content: space-between; gap: 12px;" }, [
    el("div", {}, [
      el("div", { style: "display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;" }, [
        el("div", {}, [
          el("div", { style: "font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 6px;" }, [
            el("span", {}, [obterIconeCliente(inst.cliente)]),
            el("span", {}, [inst.nome || inst.id])
          ]),
          el("div", { style: "font-size: 12px; color: var(--text-dim); margin-top: 2px;" }, [
            el("span", { style: "text-transform: uppercase; font-size: 10px; font-weight: 600; background: rgba(255,255,255,0.06); padding: 1px 6px; border-radius: 4px; margin-right: 6px;" }, [inst.cliente]),
            el("span", { style: "font-family: var(--font-mono); font-size: 11px;" }, [inst.id])
          ])
        ]),
        el("div", { style: "display: flex; align-items: center; gap: 6px;" }, [
          badgeDisco,
          switchLabel
        ])
      ]),
      el("div", { style: "font-size: 12px; margin-top: 10px; display: flex; flex-direction: column; gap: 4px;" }, [
        el("div", {}, [
          el("span", { style: "color: var(--text-dim);" }, ["Diretório: "]),
          el("code", { style: "font-size: 11px;" }, [inst.caminho])
        ]),
        inst.config_json ? el("div", {}, [
          el("span", { style: "color: var(--text-dim);" }, ["Config JSON: "]),
          el("code", { style: "font-size: 11px;" }, [inst.config_json])
        ]) : el("div", { style: "color: var(--text-dim); font-size: 11px;" }, ["Config JSON: Automático / Padrão"])
      ])
    ]),
    el("div", { style: "display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--border-subtle); padding-top: 10px;" }, [
      btnEditar,
      btnExcluir
    ])
  ]);
}

async function carregarInstanciasGovernanca() {
  const gridInst = $("grid-gov-instancias");
  gridInst.replaceChildren(el("div", { className: "suave", textContent: "Carregando instâncias de clientes..." }));

  try {
    const dados = await api("GET", "/api/governanca/instancias");
    const instancias = dados.instancias || [];
    const detectadas = dados.detectadas || [];

    gridInst.replaceChildren();

    if (instancias.length === 0) {
      gridInst.replaceChildren(el("div", {
        className: "info-callout",
        style: "grid-column: 1 / -1;",
        innerHTML: "<p class='info-callout-text'>Nenhuma instância configurada manualmente ainda. Clique em <strong> Detectar na Máquina</strong> ou <strong>+ Adicionar Instância</strong> acima.</p>"
      }));
    } else {
      instancias.forEach(inst => {
        gridInst.appendChild(criarCardInstancia(inst));
      });
    }

    const naoConfiguradas = detectadas.filter(d => !d.ja_configurado);
    const containerDet = $("container-gov-detectadas");
    const gridDet = $("grid-gov-detectadas");
    const badgeDet = $("badge-total-detectadas");

    if (naoConfiguradas.length > 0) {
      containerDet.style.display = "block";
      badgeDet.textContent = `${naoConfiguradas.length} encontrada(s)`;
      badgeDet.className = "badge badge-paid";
      gridDet.replaceChildren();

      naoConfiguradas.forEach(det => {
        const card = el("div", { className: "card", style: "border: 1px dashed var(--border-color); padding: 14px;" }, [
          el("div", { style: "display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;" }, [
            el("div", {}, [
              el("div", { style: "font-weight: 600; font-size: 14px;" }, [
                obterIconeCliente(det.cliente),
                document.createTextNode(" " + det.nome)
              ]),
              el("div", { style: "font-size: 12px; color: var(--text-dim); margin-top: 2px;" }, [
                el("code", { style: "font-size: 11px;" }, [det.caminho])
              ])
            ]),
            el("span", { className: "badge badge-free", style: "font-size: 10px;" }, ["No Disco"])
          ]),
          el("p", { style: "font-size: 12px; color: var(--text-muted); margin-bottom: 12px;" }, [det.descricao || "Instância encontrada automaticamente nesta máquina."]),
          el("button", {
            className: "btn btn-primary-outline btn-sm",
            style: "width: 100%;",
            textContent: "+ Adicionar à Governança",
            onclick: async () => {
              try {
                await api("POST", "/api/governanca/instancias", {
                  id: det.id,
                  cliente: det.cliente,
                  nome: det.nome,
                  caminho: det.caminho,
                  config_json: det.config_json || null,
                  ativo: true
                });
                toast(`Instância '${det.nome}' adicionada com sucesso!`, "success");
                carregarInstanciasGovernanca();
              } catch (e) {
                toast(e.message, "error");
              }
            }
          })
        ]);
        gridDet.appendChild(card);
      });
    } else {
      containerDet.style.display = "none";
    }
  } catch (e) {
    gridInst.replaceChildren(el("div", { className: "badge badge-paid", textContent: `Erro ao carregar instâncias: ${e.message}` }));
  }
}

function abrirModalNovaInstancia() {
  $("modal-instancia-titulo").textContent = "Adicionar Instância de Cliente";
  $("instancia-modo").value = "novo";
  $("instancia-id").value = "";
  $("instancia-id").disabled = false;
  $("instancia-cliente").value = "claude";
  $("instancia-nome").value = "";
  $("instancia-caminho").value = "";
  $("instancia-config-json").value = "";
  $("instancia-ativo").checked = true;
  abrirModal("modal-instancia");
}

function abrirModalEditarInstancia(inst) {
  $("modal-instancia-titulo").textContent = `Editar Instância: ${inst.nome || inst.id}`;
  $("instancia-modo").value = "editar";
  $("instancia-id").value = inst.id;
  $("instancia-id").disabled = true;
  $("instancia-cliente").value = inst.cliente || "claude";
  $("instancia-nome").value = inst.nome || "";
  $("instancia-caminho").value = inst.caminho || "";
  $("instancia-config-json").value = inst.config_json || "";
  $("instancia-ativo").checked = Boolean(inst.ativo);
  abrirModal("modal-instancia");
}

$("btn-modal-nova-instancia").addEventListener("click", abrirModalNovaInstancia);

$("instancia-cliente").addEventListener("change", (e) => {
  const cli = e.target.value;
  const grpJson = $("grupo-instancia-config-json");
  if (cli === "claude" || cli === "antigravity") {
    grpJson.style.display = "block";
  } else {
    grpJson.style.display = "none";
  }
});

$("btn-detectar-instancias").addEventListener("click", async () => {
  try {
    toast("Varrendo perfis de clientes de IA no disco...", "info");
    const res = await api("POST", "/api/governanca/instancias/detectar", {});
    toast(`Detecção concluída: ${res.detectadas?.length || 0} cliente(s) mapeados`, "success");
    carregarInstanciasGovernanca();
  } catch (e) {
    toast(e.message, "error");
  }
});

$("btn-salvar-instancia").addEventListener("click", async () => {
  const modo = $("instancia-modo").value;
  const id = $("instancia-id").value.trim();
  const cliente = $("instancia-cliente").value;
  const nome = $("instancia-nome").value.trim();
  const caminho = $("instancia-caminho").value.trim();
  const config_json = $("instancia-config-json").value.trim() || null;
  const ativo = $("instancia-ativo").checked;

  if (!id || !caminho) {
    toast("Preencha ao menos o ID e o Caminho do perfil", "warning");
    return;
  }

  try {
    if (modo === "novo") {
      await api("POST", "/api/governanca/instancias", { id, cliente, nome: nome || id, caminho, config_json, ativo });
      toast(`Instância '${id}' adicionada com sucesso!`, "success");
    } else {
      await api("PUT", `/api/governanca/instancias/${id}`, { nome: nome || id, caminho, config_json, ativo });
      toast(`Instância '${id}' atualizada com sucesso!`, "success");
    }
    fecharModais();
    carregarInstanciasGovernanca();
  } catch (e) {
    toast(e.message, "error");
  }
});

async function testarUmMcp(mcpId, elStatus, elBtn) {
  if (elBtn) {
    elBtn.disabled = true;
    elBtn.textContent = "⏳...";
  }
  if (elStatus) {
    elStatus.style.display = "block";
    elStatus.className = "gov-status-row gov-status-loading";
    elStatus.textContent = `⏳ Conectando e executando handshake JSON-RPC em '${mcpId}'...`;
  }
  try {
    const res = await api("POST", `/api/governanca/mcp/${mcpId}/testar`);
    if (res.ok) {
      if (elStatus) {
        elStatus.style.display = "block";
        elStatus.className = "gov-status-row gov-status-success";
        elStatus.textContent = `✓ ${res.mensagem} • Latência: ${res.latencia_ms}ms • Tipo: ${res.tipo}`;
      }
      return { ok: true, latencia_ms: res.latencia_ms };
    } else {
      if (elStatus) {
        elStatus.style.display = "block";
        elStatus.className = "gov-status-row gov-status-error";
        elStatus.textContent = `✕ ${res.mensagem} ${res.latencia_ms ? `(${res.latencia_ms}ms)` : ""}`;
      }
      return { ok: false, erro: res.mensagem };
    }
  } catch (e) {
    if (elStatus) {
      elStatus.style.display = "block";
      elStatus.className = "gov-status-row gov-status-error";
      elStatus.textContent = `✕ Falha de conexão: ${e.message}`;
    }
    return { ok: false, erro: e.message };
  } finally {
    if (elBtn) {
      elBtn.disabled = false;
      elBtn.textContent = "Testar";
    }
  }
}

let testandoTodosMcp = false;
async function testarTodosMcp() {
  if (testandoTodosMcp) return;
  testandoTodosMcp = true;
  const progresso = $("progresso-teste-mcp");
  const btn = $("btn-testar-todos-mcp");
  btn.disabled = true;

  const botoes = $$(".btn-testar-mcp");
  if (botoes.length === 0) {
    toast("Nenhum servidor MCP cadastrado para teste.", "info");
    btn.disabled = false;
    testandoTodosMcp = false;
    return;
  }

  let concluidos = 0;
  progresso.textContent = `0 / ${botoes.length} testando...`;
  progresso.style.color = "var(--text-muted)";

  for (const b of botoes) {
    progresso.textContent = `${concluidos + 1} / ${botoes.length} testando...`;
    b.click();
    await new Promise(r => setTimeout(r, 650));
    concluidos++;
  }

  progresso.textContent = `✓ Concluído: ${botoes.length} MCPs testados!`;
  progresso.style.color = "var(--success)";
  btn.disabled = false;
  testandoTodosMcp = false;
  toast(`Bateria de testes em ${botoes.length} servidores MCP finalizada!`, "success");
}

$("btn-testar-todos-mcp").addEventListener("click", testarTodosMcp);

// Modais Governança
function abrirModal(id) { $(id).classList.add("open"); }
function fecharModais() { $$(".modal-backdrop").forEach(m => m.classList.remove("open")); }

$$("[data-close-modal]").forEach(b => b.addEventListener("click", fecharModais));

let itemCodigoAtual = null;

function alternarModoVisualizacaoCodigo(modoEdicao) {
  const pre = $("modal-ver-codigo-pre");
  const editor = $("modal-ver-codigo-editor");
  const badge = $("modal-ver-codigo-badge");
  const btnEditar = $("btn-editar-codigo");
  const btnCancelar = $("btn-cancelar-edicao");
  const btnSalvar = $("btn-salvar-edicao");
  const msg = $("modal-ver-codigo-msg");

  if (modoEdicao) {
    pre.style.display = "none";
    editor.style.display = "block";
    editor.value = itemCodigoAtual?.conteudo || $("modal-ver-codigo-conteudo").textContent;
    badge.textContent = "Modo Edição";
    badge.style.background = "rgba(245, 158, 11, 0.15)";
    badge.style.color = "var(--warning)";
    badge.style.borderColor = "rgba(245, 158, 11, 0.3)";
    btnEditar.style.display = "none";
    btnCancelar.style.display = "inline-flex";
    btnSalvar.style.display = "inline-flex";
    msg.textContent = "";
    editor.focus();
  } else {
    pre.style.display = "block";
    editor.style.display = "none";
    badge.textContent = "Visualização";
    badge.style.background = "rgba(59, 130, 246, 0.15)";
    badge.style.color = "var(--accent)";
    badge.style.borderColor = "rgba(59, 130, 246, 0.3)";
    btnEditar.style.display = "inline-flex";
    btnCancelar.style.display = "none";
    btnSalvar.style.display = "none";
    msg.textContent = "";
  }
}

async function abrirModalVerCodigo(tipo, item, tituloSecao) {
  itemCodigoAtual = { tipo, item, tituloSecao, conteudo: "" };
  $("modal-ver-codigo-titulo").textContent = `${item} (${tipo})`;
  $("modal-ver-codigo-sub").textContent = "Carregando código...";
  $("modal-ver-codigo-conteudo").textContent = "Carregando...";
  $("modal-ver-codigo-msg").textContent = "";
  alternarModoVisualizacaoCodigo(false);
  abrirModal("modal-ver-codigo");

  try {
    const dados = await api("GET", `/api/governanca/${tipo}/${item}`);
    itemCodigoAtual.conteudo = dados.conteudo;
    $("modal-ver-codigo-titulo").textContent = `${item} (${tipo})`;
    $("modal-ver-codigo-sub").textContent = `Arquivo: ${dados.caminho}`;
    $("modal-ver-codigo-conteudo").textContent = dados.conteudo;
    $("modal-ver-codigo-editor").value = dados.conteudo;
    $("btn-editar-codigo").style.display = "inline-flex";
  } catch (e) {
    $("modal-ver-codigo-sub").textContent = "Falha ao carregar código";
    $("modal-ver-codigo-conteudo").textContent = `Erro: ${e.message}`;
    $("btn-editar-codigo").style.display = "none";
  }
}

$("btn-editar-codigo").addEventListener("click", () => {
  alternarModoVisualizacaoCodigo(true);
});

$("btn-cancelar-edicao").addEventListener("click", () => {
  if ($("modal-ver-codigo-editor").value !== (itemCodigoAtual?.conteudo || "")) {
    if (!confirm("Descartar alterações não salvas?")) return;
  }
  alternarModoVisualizacaoCodigo(false);
});

$("btn-salvar-edicao").addEventListener("click", async () => {
  if (!itemCodigoAtual) return;
  const novoConteudo = $("modal-ver-codigo-editor").value;
  if (!novoConteudo.trim()) {
    toast("O conteúdo não pode estar vazio.", "error");
    return;
  }

  if (itemCodigoAtual.tipo === "mcp") {
    try {
      JSON.parse(novoConteudo);
    } catch (e) {
      toast("JSON inválido: " + e.message, "error");
      return;
    }
  }

  const btnSalvar = $("btn-salvar-edicao");
  btnSalvar.disabled = true;
  btnSalvar.textContent = "Salvando...";

  try {
    const res = await api("PUT", `/api/governanca/${itemCodigoAtual.tipo}/${itemCodigoAtual.item}/conteudo`, {
      conteudo: novoConteudo
    });
    itemCodigoAtual.conteudo = res.conteudo || novoConteudo;
    $("modal-ver-codigo-conteudo").textContent = itemCodigoAtual.conteudo;
    alternarModoVisualizacaoCodigo(false);
    toast(`'${itemCodigoAtual.item}' atualizado e sincronizado com sucesso!`, "success");
    $("modal-ver-codigo-msg").textContent = "✓ Salvo e sincronizado!";
    $("modal-ver-codigo-msg").style.color = "var(--success)";
    setTimeout(() => { $("modal-ver-codigo-msg").textContent = ""; }, 3500);
    carregarGovernanca();
  } catch (e) {
    toast(`Falha ao salvar: ${e.message}`, "error");
    $("modal-ver-codigo-msg").textContent = `✕ Erro: ${e.message}`;
    $("modal-ver-codigo-msg").style.color = "var(--danger)";
  } finally {
    btnSalvar.disabled = false;
    btnSalvar.textContent = " Salvar Alterações";
  }
});

$("btn-copiar-codigo").addEventListener("click", () => {
  const isEditing = $("modal-ver-codigo-editor").style.display !== "none";
  const code = isEditing ? $("modal-ver-codigo-editor").value : $("modal-ver-codigo-conteudo").textContent;
  if (!code) return;
  navigator.clipboard.writeText(code).then(() => {
    $("modal-ver-codigo-msg").textContent = "✓ Código copiado para a área de transferência!";
    $("modal-ver-codigo-msg").style.color = "var(--success)";
    setTimeout(() => { $("modal-ver-codigo-msg").textContent = ""; }, 3000);
  }).catch(() => {
    toast("Falha ao copiar para a área de transferência", "warning");
  });
});

$("btn-modal-nova-regra").addEventListener("click", () => abrirModal("modal-regra"));
$("btn-modal-nova-skill").addEventListener("click", () => abrirModal("modal-skill"));
$("btn-modal-novo-mcp").addEventListener("click", () => abrirModal("modal-mcp"));

let modoSkill = "script";

$("tab-skill-script").addEventListener("click", () => {
  modoSkill = "script";
  $("tab-skill-script").classList.add("active");
  $("tab-skill-manual").classList.remove("active");
  $("secao-skill-script").style.display = "block";
  $("secao-skill-manual").style.display = "none";
  $("btn-salvar-skill").textContent = "Executar e Importar Skill";
});

$("tab-skill-manual").addEventListener("click", () => {
  modoSkill = "manual";
  $("tab-skill-manual").classList.add("active");
  $("tab-skill-script").classList.remove("active");
  $("secao-skill-script").style.display = "none";
  $("secao-skill-manual").style.display = "block";
  $("btn-salvar-skill").textContent = "Criar e Ativar Skill";
});

$("skill-comando").addEventListener("input", (e) => {
  const val = e.target.value.trim();
  const mSkill = val.match(/--skill\s+([a-zA-Z0-9_-]+)/);
  if (mSkill) $("skill-nome-script").value = mSkill[1];

  const mUrl = val.match(/(https?:\/\/github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+|[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+)/);
  if (mUrl) $("skill-repo-url").value = mUrl[0];
});

$("mcp-tipo").addEventListener("change", (e) => {
  const isHttp = e.target.value === "http";
  $("grupo-mcp-cmd").style.display = isHttp ? "none" : "block";
  $("grupo-mcp-url").style.display = isHttp ? "block" : "none";
});

$("btn-salvar-regra").addEventListener("click", async () => {
  const id = $("regra-id").value.trim();
  const conteudo = $("regra-conteudo").value.trim();
  if (!id || !conteudo) { toast("Preencha ID e Conteúdo da Regra", "warning"); return; }
  try {
    await api("POST", "/api/governanca/regras", { id, conteudo, ativo: true });
    toast(`Regra '${id}' criada e ativada!`, "success");
    fecharModais();
    $("regra-id").value = ""; $("regra-conteudo").value = "";
    carregarGovernanca();
  } catch (e) { toast(e.message, "error"); }
});

$("btn-salvar-skill").addEventListener("click", async () => {
  if (modoSkill === "script") {
    const comando = $("skill-comando").value.trim();
    const repo_url = $("skill-repo-url").value.trim();
    const skill_nome = $("skill-nome-script").value.trim();

    if (!comando && (!repo_url || !skill_nome)) {
      toast("Informe o comando completo ou a URL do repositório e o nome da skill", "warning");
      return;
    }

    const btn = $("btn-salvar-skill");
    btn.disabled = true;
    const txtAntigo = btn.textContent;
    btn.textContent = "⏳ Clonando repositório e importando skill...";

    try {
      const res = await api("POST", "/api/governanca/skills/importar", {
        comando: comando || null,
        repo_url: repo_url || null,
        skill_nome: skill_nome || null,
        ativo: true
      });
      toast(`Skill '${res.id}' importada com sucesso (${res.arquivos.length} arquivos)!`, "success");
      fecharModais();
      $("skill-comando").value = "";
      $("skill-repo-url").value = "";
      $("skill-nome-script").value = "";
      carregarGovernanca();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = txtAntigo;
    }
  } else {
    const id = $("skill-id").value.trim();
    const conteudo = $("skill-conteudo").value.trim();
    if (!id || !conteudo) { toast("Preencha ID e Instruções da Skill", "warning"); return; }
    try {
      await api("POST", "/api/governanca/skills", { id, conteudo, ativo: true });
      toast(`Skill '${id}' criada e ativada!`, "success");
      fecharModais();
      $("skill-id").value = ""; $("skill-conteudo").value = "";
      carregarGovernanca();
    } catch (e) { toast(e.message, "error"); }
  }
});

$("mcp-tipo").addEventListener("change", () => {
  const isHttp = $("mcp-tipo").value === "http";
  $("grupo-mcp-cmd").style.display = isHttp ? "none" : "block";
  $("grupo-mcp-url").style.display = isHttp ? "block" : "none";
});

$("mcp-auth-tipo").addEventListener("change", () => {
  const auth = $("mcp-auth-tipo").value;
  const grupoEnv = $("grupo-mcp-env");
  const hint = $("hint-mcp-auth");
  if (auth === "chave") {
    grupoEnv.style.display = "block";
    hint.textContent = "O token será salvo no arquivo .env e protegido no Cofre de Segredos.";
  } else if (auth === "oauth") {
    grupoEnv.style.display = "none";
    hint.textContent = "Autenticação delegada ao cliente (Claude Code, Cursor, OpenCode). O navegador abrirá automaticamente para login quando a IA invocar o servidor.";
  } else {
    grupoEnv.style.display = "none";
    hint.textContent = "Servidor acessível publicamente ou em rede local sem necessidade de credenciais.";
  }
});

$("btn-salvar-mcp").addEventListener("click", async () => {
  const id = $("mcp-id").value.trim();
  const tipo = $("mcp-tipo").value;
  const authTipo = $("mcp-auth-tipo").value;
  const desc = $("mcp-desc").value.trim();
  if (!id) { toast("Informe o ID do servidor MCP", "warning"); return; }
  let config = { description: desc };
  if (tipo === "http") {
    const url = $("mcp-url").value.trim();
    if (!url) { toast("Informe a URL do servidor HTTP", "warning"); return; }
    config.type = "http";
    config.url = url;
  } else {
    const cmdStr = $("mcp-cmd").value.trim();
    if (!cmdStr) { toast("Informe o comando de execução", "warning"); return; }
    const partes = cmdStr.split(/\s+/);
    config.command = partes[0];
    config.args = partes.slice(1);
  }

  if (authTipo === "oauth") {
    config.auth = "oauth";
  } else if (authTipo === "chave") {
    // Processa múltiplas variáveis de ambiente (separadas por vírgula, espaço ou ponto e vírgula)
    const rawEnv = $("mcp-env-key").value.trim();
    if (rawEnv) {
      config.env = config.env || {};
      const tokens = rawEnv.split(/[,;\n\r\s]+/).map(t => t.trim()).filter(Boolean);
      for (const t of tokens) {
        let varName = t;
        let varVal = null;
        if (t.includes("=")) {
          const idx = t.indexOf("=");
          varName = t.substring(0, idx).trim();
          varVal = t.substring(idx + 1).trim();
        }
        varName = varName.replace(/[^A-Za-z0-9_]/g, "");
        if (varName) {
          config.env[varName] = varVal || `\${${varName}}`;
        }
      }
    }
  }

  // Extrai flags -e NOME_VAR caso tenham sido coladas no comando
  if (config.args && Array.isArray(config.args)) {
    for (let i = 0; i < config.args.length; i++) {
      if (config.args[i] === "-e" && config.args[i + 1]) {
        const flagVal = config.args[i + 1];
        const [vName, ...vRest] = flagVal.split("=");
        const cleanName = vName.replace(/[^A-Za-z0-9_]/g, "");
        if (cleanName) {
          config.env = config.env || {};
          config.env[cleanName] = vRest.length > 0 ? vRest.join("=") : `\${${cleanName}}`;
        }
      }
    }
  }

  try {
    await api("POST", "/api/governanca/mcp", { id, config, ativo: true });
    toast(`Servidor MCP '${id}' cadastrado com sucesso!`, "success");
    fecharModais();
    $("mcp-id").value = ""; $("mcp-cmd").value = ""; $("mcp-url").value = ""; $("mcp-desc").value = ""; $("mcp-env-key").value = "";
    carregarGovernanca();
  } catch (e) { toast(e.message, "error"); }
});

// ------------------------------------------------ 5. SEGREDOS & TESTES
let cacheSegredos = [];
let filtroSegredoAtual = "todos";

async function carregarSegredos() {
  const grid = $("grid-segredos");
  grid.replaceChildren(el("div", { className: "suave", textContent: "Carregando segredos..." }));
  try {
    cacheSegredos = await api("GET", "/api/segredos");
    renderizarSegredos();
  } catch (e) {
    grid.replaceChildren(el("div", { className: "toast toast-error", textContent: e.message }));
  }
}

function renderizarSegredos() {
  const grid = $("grid-segredos");
  grid.replaceChildren();

  const filtrados = cacheSegredos.filter(s => {
    if (filtroSegredoAtual === "todos") return true;
    return s.categoria === filtroSegredoAtual;
  });

  for (const s of filtrados) {
    const badgeTier = s.categoria === "FREE" ? el("span", { className: "badge badge-free", textContent: "FREE" })
                    : s.categoria === "PAID" ? el("span", { className: "badge badge-paid", textContent: "PAID" })
                    : el("span", { className: "badge badge-role", textContent: s.categoria });

    const header = el("div", { className: "card-header" }, [
      el("div", { className: "card-title-group" }, [
        el("span", { className: "card-title", textContent: s.nome_provedor || s.chave }),
        badgeTier
      ]),
      el("span", { style: "font-family:var(--font-mono); font-size:11px; color:var(--text-dim);" }, [s.chave])
    ]);

    let revelado = false;
    const inputVal = el("input", {
      type: "password",
      placeholder: s.definido ? s.mascarado : "Não configurado",
      autocomplete: "off"
    });

    const btnVer = el("button", {
      className: "btn btn-outline btn-sm",
      title: "Revelar / Ocultar valor do segredo",
      "aria-label": "Revelar valor do segredo",
      onclick: async () => {
        if (revelado) {
          inputVal.type = "password";
          mostrarIconeVer(false);
          revelado = false;
        } else {
          if (inputVal.value) {
            inputVal.type = "text";
            mostrarIconeVer(true);
            revelado = true;
          } else if (s.definido) {
            btnVer.replaceChildren("⏳");
            try {
              const res = await api("POST", `/api/segredos/${s.chave}/revelar`);
              inputVal.value = res.valor;
              inputVal.type = "text";
              mostrarIconeVer(true);
              revelado = true;
              toast(`Segredo ${s.chave} revelado na tela`, "info");
            } catch (e) {
              mostrarIconeVer(false);
              toast(`Erro ao revelar: ${e.message}`, "error");
            }
          }
        }
      }
    });
    // Olho = revelar; olho riscado = ocultar (o valor está visível).
    function mostrarIconeVer(visivel) {
      btnVer.replaceChildren(icone(visivel ? "olhoFechado" : "olho"));
      btnVer.setAttribute("aria-label", visivel ? "Ocultar valor do segredo" : "Revelar valor do segredo");
    }
    mostrarIconeVer(false);

    const btnSalvar = el("button", {
      className: "btn btn-primary btn-sm",
      textContent: "Salvar",
      onclick: async () => {
        if (!inputVal.value) return;
        try {
          await api("PUT", `/api/segredos/${s.chave}`, { valor: inputVal.value });
          toast(`Chave ${s.chave} atualizada com backup no cofre!`, "success");
          carregarSegredos();
        } catch (e) { toast(e.message, "error"); }
      }
    });

    const statusTeste = el("span", { style: "font-size:12px; margin-top:4px;" });

    const btnTestar = s.testavel && s.definido ? el("button", {
      className: "btn btn-outline btn-sm",
      textContent: "Testar Conexão",
      onclick: async () => {
        statusTeste.textContent = "Testando conexão com a API oficial...";
        statusTeste.style.color = "var(--text-muted)";
        try {
          const res = await api("POST", `/api/segredos/${s.chave}/testar`);
          if (res.valido) {
            statusTeste.textContent = `✓ ${res.mensagem} (${res.latencia_ms}ms)`;
            statusTeste.style.color = "var(--success)";
          } else {
            statusTeste.textContent = `✕ ${res.mensagem} (${res.latencia_ms}ms)`;
            statusTeste.style.color = "var(--danger)";
          }
        } catch (e) {
          statusTeste.textContent = `✕ Erro: ${e.message}`;
          statusTeste.style.color = "var(--danger)";
        }
      }
    }) : null;

    const rowInput = el("div", { style: "display:flex; gap:8px;" }, [inputVal, btnVer, btnSalvar]);
    const actionsRow = el("div", { style: "display:flex; justify-content:space-between; align-items:center; margin-top:6px;" }, [
      statusTeste,
      btnTestar
    ]);

    grid.appendChild(el("div", { className: "card", id: `card-segredo-${s.chave}` }, [header, rowInput, actionsRow]));
  }
  destacarSegredoNaTela();
}

$$("[data-filter-segredo]").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("[data-filter-segredo]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    filtroSegredoAtual = btn.dataset.filterSegredo;
    renderizarSegredos();
  });
});

// ------------------------------------------------ 6. TELEMETRIA
let timerTelemetria = null;
let telemetriaPausada = false;

async function carregarTelemetria() {
  try {
    const dados = await api("GET", "/api/telemetria");
    renderizarTelemetria(dados);
  } catch (e) {
    const tbody = $("tbody-telemetria-feed");
    if (tbody) {
      tbody.replaceChildren(
        el("tr", {}, [
          el("td", { colSpan: "7", style: "text-align:center; color:var(--danger); padding:20px;", textContent: `Erro ao carregar telemetria: ${e.message}` })
        ])
      );
    }
  }
}

function renderizarTelemetria(dados) {
  if ($("stat-total-req")) $("stat-total-req").textContent = dados.total_requisicoes.toLocaleString();
  if ($("stat-total-tokens")) $("stat-total-tokens").textContent = dados.total_tokens.toLocaleString();
  if ($("stat-media-latencia")) $("stat-media-latencia").textContent = `${dados.latencia_media_ms} ms`;
  if ($("stat-custo-total")) $("stat-custo-total").textContent = `$ ${dados.custo_total_usd.toFixed(4)}`;

  // VRAM Models (Ollama)
  const gridVram = $("grid-telemetria-vram");
  if (gridVram) {
    gridVram.replaceChildren();
    if (!dados.vram_modelos || dados.vram_modelos.length === 0) {
      gridVram.appendChild(el("div", { className: "card suave", style: "grid-column:1/-1; padding:16px; text-align:center; color:var(--text-muted);", textContent: "Nenhum modelo carregado na VRAM no momento (os modelos sobem automaticamente sob demanda)." }));
    } else {
      for (const vm of dados.vram_modelos) {
        const header = el("div", { className: "card-header" }, [
          el("div", { className: "card-title-group" }, [
            el("span", { className: "status-dot online" }),
            el("span", { className: "card-title", textContent: vm.nome })
          ]),
          el("span", { className: "badge badge-free", textContent: "Na VRAM" })
        ]);
        const desc = el("div", { className: "card-desc", textContent: `Tamanho: ${vm.tamanho_mb} MB · VRAM Alocada: ${vm.tamanho_vram_mb} MB · Janela de Contexto: ${vm.contexto || 8192} tok` });
        const horaExp = vm.expira_em ? vm.expira_em.split("T")[1]?.slice(0,8) : 'automático';
        const footer = el("div", { className: "card-meta" }, [
          el("span", { textContent: `Expira em memória: ${horaExp}` }),
          el("span", { className: "badge badge-role", textContent: "GPU" })
        ]);
        gridVram.appendChild(el("div", { className: "card" }, [header, desc, footer]));
      }
    }
  }

  // Feed de Requisições (LiteLLM)
  const tbody = $("tbody-telemetria-feed");
  if (tbody) {
    tbody.replaceChildren();
    if (!dados.feed || dados.feed.length === 0) {
      tbody.appendChild(el("tr", {}, [
        el("td", { colSpan: "7", style: "text-align:center; padding:20px; color:var(--text-dim);", textContent: "Nenhuma requisição registrada no gateway ainda." })
      ]));
    } else {
      for (const item of dados.feed) {
        const hora = item.inicio ? item.inicio.split("T")[1]?.slice(0, 8) : "-";
        const statusClass = item.status === "failure" ? "badge badge-paid" : "badge badge-free";
        const statusText = item.status === "failure" ? "FALHA" : "OK 200";

        const latClass = item.latencia_ms < 1000 ? "latency-pill latency-fast"
                       : item.latencia_ms < 4000 ? "latency-pill latency-medium"
                       : "latency-pill latency-slow";

        const tr = el("tr", {}, [
          el("td", { style: "font-family:var(--font-mono); font-size:12px; color:var(--text-dim);", textContent: hora }),
          el("td", { style: "font-family:var(--font-mono); font-weight:600;", textContent: item.modelo || "tudoia-auto" }),
          el("td", {}, [el("span", { className: "badge badge-role", textContent: item.grupo })]),
          el("td", { style: "font-family:var(--font-mono); font-size:12px;", textContent: `${item.total_tokens} (${item.prompt_tokens}↑ / ${item.completion_tokens}↓)` }),
          el("td", {}, [el("span", { className: latClass, textContent: `${item.latencia_ms}ms` })]),
          el("td", {}, [el("span", { className: statusClass, textContent: statusText })]),
          el("td", { style: "font-size:12px; color:var(--text-muted); max-width:180px; overflow:hidden; text-overflow:ellipsis;", textContent: item.cliente })
        ]);
        tbody.appendChild(tr);
      }
    }
  }

  // ---------------- Renderização da Aba Visual & ComfyUI / GPU
  const c = dados.comfyui || {};
  const feedVis = dados.feed_visual || [];

  if ($("stat-visual-vram-usada")) {
    $("stat-visual-vram-usada").textContent = c.vram_usada_mb ? `${c.vram_usada_mb} MB` : "0 MB";
  }
  if ($("stat-visual-vram-sub")) {
    $("stat-visual-vram-sub").textContent = c.vram_pct_usada ? `${c.vram_pct_usada}% da GPU` : "Hardware Local CUDA";
  }
  if ($("badge-vram-pct")) {
    $("badge-vram-pct").textContent = `${c.vram_pct_usada || 0}% VRAM`;
  }
  if ($("bar-vram-ocupada")) {
    $("bar-vram-ocupada").style.width = `${Math.min(100, c.vram_pct_usada || 0)}%`;
  }
  if ($("label-vram-detalhe")) {
    $("label-vram-detalhe").textContent = `Alocada: ${c.vram_usada_mb || 0} MB / ${c.vram_total_mb || 8192} MB (Livre: ${c.vram_livre_mb || 0} MB)`;
  }
  if ($("label-ram-detalhe")) {
    $("label-ram-detalhe").textContent = `RAM Host: ${c.ram_livre_gb || 0} GB Livre / ${c.ram_total_gb || 0} GB Total`;
  }
  if ($("telemetria-gpu-nome") && c.gpu_nome) {
    $("telemetria-gpu-nome").textContent = c.gpu_nome;
  }

  if ($("stat-visual-comfy-status")) {
    $("stat-visual-comfy-status").textContent = c.ativo ? "ONLINE" : "OFFLINE";
    $("stat-visual-comfy-status").style.color = c.ativo ? "var(--success, #10b981)" : "var(--text-muted)";
  }
  if ($("stat-visual-comfy-sub")) {
    $("stat-visual-comfy-sub").textContent = c.ativo ? `Fila: ${c.fila_executando || 0} ativa / ${c.fila_pendente || 0} pendente` : "Porta :8188";
  }

  if ($("stat-visual-motor-status")) {
    $("stat-visual-motor-status").textContent = c.ativo ? "ONLINE (GPU)" : "OFFLINE";
    $("stat-visual-motor-status").style.color = c.ativo ? "var(--success, #10b981)" : "var(--text-muted)";
  }

  if ($("stat-visual-total-geracoes")) {
    $("stat-visual-total-geracoes").textContent = feedVis.length.toString();
  }
  if ($("stat-visual-latencia-media")) {
    const duracoes = feedVis.map(f => f.duracao_s).filter(d => d > 0);
    const media = duracoes.length ? (duracoes.reduce((a, b) => a + b, 0) / duracoes.length).toFixed(1) : "-";
    $("stat-visual-latencia-media").textContent = `Média: ${media}s`;
  }

  // Tabela Feed Visual
  const tbodyVis = $("tbody-telemetria-visual-feed");
  if (tbodyVis) {
    tbodyVis.replaceChildren();
    if (feedVis.length === 0) {
      tbodyVis.appendChild(
        el("tr", {}, [
          el("td", { colSpan: "7", style: "text-align:center; padding:20px; color:var(--text-dim);", textContent: "Nenhuma geração visual registrada na sessão ainda." })
        ])
      );
    } else {
      for (const item of feedVis) {
        const isOk = item.status === "sucesso";
        const statusClass = isOk ? "badge badge-free" : "badge badge-paid";
        const statusText = isOk ? "SUCESSO" : "FALHA";
        const tipoBadge = item.tipo === "inpaint" ? " Inpaint" : item.tipo === "video" ? " Vídeo" : item.tipo === "svg" ? " SVG" : " Txt2Img";

        const tr = el("tr", {}, [
          el("td", { style: "font-family:var(--font-mono); font-size:12px; color:var(--text-dim);", textContent: item.horario || "-" }),
          el("td", {}, [el("span", { className: "badge badge-role", textContent: tipoBadge })]),
          el("td", { style: "font-family:var(--font-mono); font-weight:600; font-size:12px;", textContent: `${item.motor} · ${item.modelo || 'auto'}` }),
          el("td", { style: "font-family:var(--font-mono); font-size:12px;", textContent: item.dimensoes || "-" }),
          el("td", { style: "font-family:var(--font-mono); font-size:12px; font-weight:600;", textContent: `${item.duracao_s}s` }),
          el("td", {}, [el("span", { className: statusClass, textContent: statusText })]),
          el("td", { style: "font-size:12px; color:var(--text-muted); max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;", textContent: item.prompt || "-" })
        ]);
        tbodyVis.appendChild(tr);
      }
    }
  }
}

function iniciarStreamTelemetria() {
  if (timerTelemetria) clearInterval(timerTelemetria);
  timerTelemetria = setInterval(() => {
    if (!telemetriaPausada) {
      const viewTel = $("view-telemetria");
      if (viewTel && viewTel.classList.contains("active")) {
        carregarTelemetria();
      }
    }
  }, 3000);
}

$("btn-toggle-stream-telemetria").addEventListener("click", () => {
  telemetriaPausada = !telemetriaPausada;
  $("btn-toggle-stream-telemetria").textContent = telemetriaPausada ? "▶ Retomar Stream" : "⏸ Pausar Stream (3s)";
  toast(telemetriaPausada ? "Stream de telemetria pausado" : "Stream de telemetria ativo (3s)", "info");
});

$("btn-recarregar-telemetria").addEventListener("click", () => {
  carregarTelemetria();
  toast("Telemetria atualizada", "info");
});

// Subtabs da Telemetria (Texto & Agentes vs Estúdio Visual)
const tabTelTexto = $("tab-telemetria-texto");
const tabTelVisual = $("tab-telemetria-visual");
const conteudoTelTexto = $("conteudo-telemetria-texto");
const conteudoTelVisual = $("conteudo-telemetria-visual");

if (tabTelTexto && tabTelVisual) {
  tabTelTexto.addEventListener("click", () => {
    tabTelTexto.classList.add("active");
    tabTelVisual.classList.remove("active");
    if (conteudoTelTexto) conteudoTelTexto.style.display = "block";
    if (conteudoTelVisual) conteudoTelVisual.style.display = "none";
  });
  tabTelVisual.addEventListener("click", () => {
    tabTelVisual.classList.add("active");
    tabTelTexto.classList.remove("active");
    if (conteudoTelTexto) conteudoTelTexto.style.display = "none";
    if (conteudoTelVisual) conteudoTelVisual.style.display = "block";
    carregarTelemetria(); // Atualiza na hora ao alternar para a aba visual
  });
}

// Botão Cancelar Inferência Visual no Studio
const btnCancelarGeracao = $("btn-cancelar-geracao");
if (btnCancelarGeracao) {
  btnCancelarGeracao.addEventListener("click", async () => {
    try {
      btnCancelarGeracao.disabled = true;
      btnCancelarGeracao.textContent = "Cancelando...";
      const res = await api("POST", "/api/estudio/cancelar");
      if (res && res.ok) {
        toast("Inferência interrompida no ComfyUI!", "info");
      } else {
        toast("Sinal de interrupção enviado.", "info");
      }
    } catch (e) {
      toast(`Erro ao cancelar: ${e.message}`, "danger");
    } finally {
      finalizarProgressoGeracao(false);
      btnCancelarGeracao.disabled = false;
      btnCancelarGeracao.textContent = " Cancelar";
    }
  });
}

iniciarStreamTelemetria();

// ------------------------------------------------ 7. SERVIDOR & HARDWARE
let timerHardware = null;
let hardwarePausado = false;

async function carregarHardware() {
  try {
    const d = await api("GET", "/api/hardware");
    renderizarHardware(d);
  } catch (e) {
    console.error("Erro hardware:", e);
  }
}

function renderizarHardware(d) {
  // CPU
  if ($("hw-cpu-cores")) $("hw-cpu-cores").textContent = `${d.cpu.cores_fisicos} cores / ${d.cpu.cores_logicos} threads`;
  if ($("hw-cpu-val")) $("hw-cpu-val").textContent = `${d.cpu.pct.toFixed(1)} %`;
  if ($("hw-cpu-pct-txt")) $("hw-cpu-pct-txt").textContent = `${d.cpu.pct.toFixed(1)}%`;
  if ($("hw-cpu-bar")) {
    $("hw-cpu-bar").style.width = `${Math.min(d.cpu.pct, 100)}%`;
    $("hw-cpu-bar").className = `progress-bar-fill ${d.cpu.pct > 80 ? 'fill-high' : d.cpu.pct > 50 ? 'fill-medium' : 'fill-low'}`;
  }
  if ($("hw-cpu-freq")) $("hw-cpu-freq").textContent = `Frequência: ${d.cpu.freq_mhz} MHz`;

  // RAM
  if ($("hw-ram-total")) $("hw-ram-total").textContent = `${d.ram.total_gb} GB Total`;
  if ($("hw-ram-val")) $("hw-ram-val").textContent = `${d.ram.usada_gb} GB`;
  if ($("hw-ram-sub")) $("hw-ram-sub").textContent = `Usada: ${d.ram.usada_gb} GB / Livre: ${d.ram.livre_gb} GB`;
  if ($("hw-ram-pct-txt")) $("hw-ram-pct-txt").textContent = `${d.ram.pct.toFixed(1)}%`;
  if ($("hw-ram-bar")) {
    $("hw-ram-bar").style.width = `${Math.min(d.ram.pct, 100)}%`;
    $("hw-ram-bar").className = `progress-bar-fill ${d.ram.pct > 85 ? 'fill-high' : d.ram.pct > 70 ? 'fill-medium' : 'fill-low'}`;
  }

  // GPU
  if ($("hw-gpu-temp")) $("hw-gpu-temp").textContent = `${d.gpu.temp_c} °C`;
  if ($("hw-gpu-val")) $("hw-gpu-val").textContent = `${d.gpu.utilizacao_pct.toFixed(1)} %`;
  if ($("hw-gpu-pct-txt")) $("hw-gpu-pct-txt").textContent = `${d.gpu.utilizacao_pct.toFixed(1)}%`;
  if ($("hw-gpu-bar")) {
    $("hw-gpu-bar").style.width = `${Math.min(d.gpu.utilizacao_pct, 100)}%`;
    $("hw-gpu-bar").className = `progress-bar-fill ${d.gpu.utilizacao_pct > 80 ? 'fill-high' : d.gpu.utilizacao_pct > 50 ? 'fill-medium' : 'fill-low'}`;
  }
  if ($("hw-gpu-nome")) $("hw-gpu-nome").textContent = d.gpu.nome;

  // VRAM
  if ($("hw-vram-total")) $("hw-vram-total").textContent = `${d.gpu.vram_total_gb} GB`;
  if ($("hw-vram-val")) $("hw-vram-val").textContent = `${d.gpu.vram_usada_gb} GB`;
  if ($("hw-vram-sub")) $("hw-vram-sub").textContent = `Alocada: ${d.gpu.vram_usada_gb} GB / Livre: ${d.gpu.vram_livre_gb} GB`;
  if ($("hw-vram-pct-txt")) $("hw-vram-pct-txt").textContent = `${d.gpu.vram_pct.toFixed(1)}%`;
  if ($("hw-vram-bar")) {
    $("hw-vram-bar").style.width = `${Math.min(d.gpu.vram_pct, 100)}%`;
    $("hw-vram-bar").className = `progress-bar-fill ${d.gpu.vram_pct > 85 ? 'fill-high' : d.gpu.vram_pct > 60 ? 'fill-medium' : 'fill-low'}`;
  }

  // Discos
  const gridDiscos = $("grid-hardware-discos");
  if (gridDiscos) {
    gridDiscos.replaceChildren();
    for (const disco of d.discos || []) {
      const header = el("div", { className: "hardware-card-header" }, [
        el("span", { className: "hardware-card-title" }, [` Unidade ${disco.drive}`]),
        el("span", { className: "badge badge-role", textContent: `${disco.total_gb} GB` })
      ]);
      const val = el("div", { className: "telemetria-stat-value", textContent: `${disco.usado_gb} GB` });
      const barFill = el("div", {
        className: `progress-bar-fill ${disco.pct > 90 ? 'fill-high' : disco.pct > 75 ? 'fill-medium' : 'fill-low'}`,
        style: `width: ${Math.min(disco.pct, 100)}%;`
      });
      const barBg = el("div", { className: "progress-bar-bg" }, [barFill]);
      const prog = el("div", { className: "progress-container" }, [
        el("div", { className: "progress-header" }, [
          el("span", { textContent: `Livre: ${disco.livre_gb} GB` }),
          el("span", { textContent: `${disco.pct.toFixed(1)}%` })
        ]),
        barBg
      ]);
      gridDiscos.appendChild(el("div", { className: "hardware-card" }, [header, val, prog]));
    }
  }
}

function iniciarStreamHardware() {
  if (timerHardware) clearInterval(timerHardware);
  timerHardware = setInterval(() => {
    if (!hardwarePausado) {
      const viewHw = $("view-hardware");
      if (viewHw && viewHw.classList.contains("active")) {
        carregarHardware();
      }
    }
  }, 2000);
}

$("btn-toggle-stream-hardware").addEventListener("click", () => {
  hardwarePausado = !hardwarePausado;
  $("btn-toggle-stream-hardware").textContent = hardwarePausado ? "▶ Retomar Monitor" : "⏸ Pausar Monitor (2s)";
  toast(hardwarePausado ? "Monitoramento de hardware pausado" : "Monitoramento de hardware ativo (2s)", "info");
});

$("btn-recarregar-hardware").addEventListener("click", () => {
  carregarHardware();
  toast("Hardware atualizado", "info");
});

$("btn-limpar-vram").addEventListener("click", async () => {
  const btn = $("btn-limpar-vram");
  btn.disabled = true;
  btn.textContent = "⏳ Limpando...";
  try {
    toast("Descarregando modelos do Ollama para liberar VRAM...", "info");
    const res = await api("POST", "/api/hardware/limpar-vram");
    toast(`✓ ${res.mensagem}`, "success");
    carregarHardware();
  } catch (e) {
    toast(`Erro ao limpar VRAM: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = " Limpar VRAM";
  }
});

// ------------------------------------------------ LIMITES & TOKENS POR PROVEDOR
let periodoLimitesAtual = "24h";
let filtroTierLimiteAtual = "todos";
let dadosLimitesCache = null;

function formatarTokens(qtd) {
  if (qtd == null || isNaN(qtd)) return "0";
  if (qtd >= 1000000) return (qtd / 1000000).toFixed(2) + " M";
  if (qtd >= 1000) return (qtd / 1000).toFixed(1) + " K";
  return Number(qtd).toLocaleString("pt-BR");
}

function formatarMoedaUSD(valor) {
  const v = Number(valor || 0);
  if (v === 0) return "$0.00";
  if (v < 0.01) return "$" + v.toFixed(4);
  return "$" + v.toFixed(2);
}

// Só a resposta do pedido mais recente é renderizada: uma resposta de período antigo que chega depois não pode
// sobrescrever a tela (antes, o rótulo mostrava o período atual com os números do anterior).
let requisicaoLimitesAtual = 0;

async function carregarLimites() {
  const requisicao = ++requisicaoLimitesAtual;
  try {
    const dados = await api("GET", `/api/limites-tokens?periodo=${periodoLimitesAtual}`);
    if (requisicao !== requisicaoLimitesAtual) return;
    dadosLimitesCache = dados;
    renderizarLimites(dados);
  } catch (e) {
    if (requisicao === requisicaoLimitesAtual) toast(`Erro ao carregar limites e tokens: ${e.message}`, "error");
  }
}

function renderizarLimites(dados) {
  if (!dados) return;
  const { resumo, distribuicao, provedores, ranking_modelos } = dados;

  // 1. KPIs
  $("stat-limites-tokens-total").textContent = formatarTokens(resumo.total_tokens);
  $("stat-limites-tokens-split").textContent = `Prompt: ${formatarTokens(resumo.total_entrada)} | Completion: ${formatarTokens(resumo.total_saida)}`;
  $("stat-limites-economia").textContent = formatarMoedaUSD(resumo.economia_estimada_usd);
  $("stat-limites-custo-pago").textContent = formatarMoedaUSD(resumo.custo_total_usd);
  $("stat-limites-prov-ativos").textContent = `${resumo.provedores_com_trafego} de ${resumo.total_provedores}`;

  const spanAlertas = $("stat-limites-alertas");
  if (resumo.alertas_criticos > 0) {
    spanAlertas.textContent = `⚠ ${resumo.alertas_criticos} alerta(s) de quota/limite`;
    spanAlertas.style.color = "var(--danger)";
    spanAlertas.style.fontWeight = "bold";
  } else {
    spanAlertas.textContent = `✓ Zero quotas bloqueadas`;
    spanAlertas.style.color = "var(--success)";
  }

  // 2. Rótulo de período
  const periodoLabelMap = { "24h": "Últimas 24 Horas", "7d": "Últimos 7 Dias", "total": "Histórico Acumulado" };
  const lblPeriodo = $("label-distribuicao-periodo");
  if (lblPeriodo) lblPeriodo.textContent = periodoLabelMap[periodoLimitesAtual] || periodoLimitesAtual;

  // 3. Barra de Distribuição de Tokens
  const barraDist = $("barra-distribuicao-tokens");
  const legDist = $("legenda-distribuicao-tokens");
  barraDist.innerHTML = "";
  legDist.innerHTML = "";

  if (!distribuicao || distribuicao.length === 0) {
    barraDist.appendChild(el("div", {
      className: "distribuicao-bar-segment",
      style: "width:100%; background:var(--bg-subtle); display:flex; align-items:center; justify-content:center; color:var(--text-dim); font-size:11px;",
      textContent: "Nenhum consumo de tokens registrado no período selecionado"
    }));
  } else {
    distribuicao.forEach(d => {
      const seg = el("div", {
        className: "distribuicao-bar-segment",
        style: `width:${Math.max(d.pct, 1.5)}%; background:${d.cor};`,
        title: `${d.nome} (${d.tier}): ${d.pct}% (${formatarTokens(d.tokens)} tokens)`
      });
      barraDist.appendChild(seg);

      const itemLeg = el("div", { className: "distribuicao-legend-item" }, [
        el("span", { className: "distribuicao-legend-dot", style: `background:${d.cor};` }),
        el("strong", { textContent: d.nome }),
        el("span", { style: "color:var(--text-muted);", textContent: `${d.pct}% (${formatarTokens(d.tokens)})` })
      ]);
      legDist.appendChild(itemLeg);
    });
  }

  // 4. Grid de Provedores com Filtro
  renderizarCardsProvedores(provedores);

  // 5. Ranking de Modelos
  const tbodyModelos = $("tbody-limites-ranking-modelos");
  tbodyModelos.innerHTML = "";
  if (!ranking_modelos || ranking_modelos.length === 0) {
    tbodyModelos.appendChild(el("tr", {}, [
      el("td", { colSpan: "9", style: "text-align:center; color:var(--text-dim); padding:20px;", textContent: "Nenhum modelo foi executado neste período." })
    ]));
  } else {
    ranking_modelos.forEach(m => {
      const tierBadge = el("span", {
        className: `badge badge-${m.tier ? m.tier.toLowerCase() : "gray"}`,
        textContent: rotuloTier(m.tier)
      });
      const econOuCusto = m.tier === "PAID"
        ? el("span", { style: "color:var(--text-primary); font-family:var(--font-mono);", textContent: formatarMoedaUSD(m.custo_usd) })
        : el("span", { style: "color:var(--success); font-family:var(--font-mono);", textContent: `+ ${formatarMoedaUSD(m.economia_usd)} (econ)` });

      const tr = el("tr", {}, [
        el("td", {}, [el("strong", { textContent: m.modelo })]),
        el("td", { textContent: m.provedor_nome }),
        el("td", {}, [tierBadge]),
        el("td", { style: "font-family:var(--font-mono);", textContent: m.requisicoes.toLocaleString("pt-BR") }),
        el("td", { style: "font-family:var(--font-mono); color:var(--text-muted);", textContent: formatarTokens(m.tokens_entrada) }),
        el("td", { style: "font-family:var(--font-mono); color:var(--text-muted);", textContent: formatarTokens(m.tokens_saida) }),
        el("td", { style: "font-family:var(--font-mono); font-weight:600;", textContent: formatarTokens(m.tokens_total) }),
        el("td", { style: "font-family:var(--font-mono);", textContent: `${m.pct_do_total}%` }),
        el("td", {}, [econOuCusto])
      ]);
      tbodyModelos.appendChild(tr);
    });
  }
}

function renderizarCardsProvedores(provedores) {
  const grid = $("grid-limites-provedores");
  grid.innerHTML = "";

  const filtrados = provedores.filter(p => {
    if (filtroTierLimiteAtual === "todos") return true;
    return p.tier === filtroTierLimiteAtual;
  });

  if (filtrados.length === 0) {
    grid.appendChild(el("div", {
      className: "card",
      style: "grid-column: 1 / -1; text-align:center; padding:30px; color:var(--text-muted);",
      textContent: "Nenhum provedor encontrado com o filtro selecionado."
    }));
    return;
  }

  filtrados.forEach(p => {
    const c = p.consumo;
    const l = p.limites || {};

    // Header do card
    const badgeTier = el("span", {
      className: `badge badge-${p.tier.toLowerCase()}`,
      textContent: p.tier
    });

    const badgesContainer = el("div", { style: "display:flex; gap:6px; align-items:center;" }, [badgeTier]);

    if (!p.chave_configurada && p.chave) {
      badgesContainer.appendChild(el("a", {
        href: `#segredos`,
        className: "badge badge-warning",
        style: "cursor:pointer; text-decoration:none;",
        textContent: "⚠ Chave pendente",
        onclick: (e) => {
          e.preventDefault();
          navegarParaSegredo(p.chave);
        }
      }));
    } else if (p.tier === "LOCAL") {
      badgesContainer.appendChild(el("span", { className: "badge badge-success", textContent: " GPU" }));
    } else if (p.ativo) {
      badgesContainer.appendChild(el("span", { className: "badge badge-success", textContent: "✓ Conectado" }));
    }

    if (p.tier !== "LOCAL") {
      badgesContainer.appendChild(el("button", {
        className: "btn btn-outline btn-sm",
        style: "padding: 2px 8px; font-size: 11px; margin-left: 4px;",
        textContent: "Modelos Novos",
        title: "Listar modelos novos deste provedor e escolher quais incluir",
        onclick: () => abrirEscolherNovos(p.id)
      }));
    }

    const cardHeader = el("div", { className: "card-header", style: "display:flex; justify-content:space-between; align-items:center;" }, [
      el("div", { style: "display:flex; align-items:center; gap:8px;" }, [
        el("h3", { className: "card-title", style: "margin:0;", textContent: p.nome }),
      ]),
      badgesContainer
    ]);

    // Grid de métricas numéricas
    const gridMetricas = el("div", { className: "limite-metricas-grid" }, [
      el("div", { className: "limite-metrica-item" }, [
        el("span", { className: "valor", textContent: formatarTokens(c.tokens_total) }),
        el("span", { className: "label", textContent: "Tokens Totais" })
      ]),
      el("div", { className: "limite-metrica-item" }, [
        el("span", { className: "valor", textContent: formatarTokens(c.tokens_entrada) }),
        el("span", { className: "label", textContent: "Prompt" })
      ]),
      el("div", { className: "limite-metrica-item" }, [
        el("span", { className: "valor", textContent: formatarTokens(c.tokens_saida) }),
        el("span", { className: "label", textContent: "Completion" })
      ])
    ]);

    // Seção de Quotas e Limites Operacionais
    const quotaSection = el("div", { style: "margin-top:10px; display:flex; flex-direction:column; gap:8px;" });

    // Barra de RPD se houver
    if (l.rpd) {
      const pct = c.pct_rpd || 0;
      const statusClass = pct >= 90 ? "critico" : (pct >= 70 ? "atencao" : "normal");
      quotaSection.appendChild(el("div", { className: "quota-bar-wrapper" }, [
        el("div", { className: "quota-bar-label" }, [
          el("span", { textContent: `Cota Diária (RPD): ${c.requisicoes} / ${l.rpd} reqs` }),
          el("strong", { textContent: `${pct}%` })
        ]),
        el("div", { className: "quota-bar-bg" }, [
          el("div", { className: `quota-bar-fill ${statusClass}`, style: `width: ${Math.min(pct, 100)}%;` })
        ])
      ]));
    }

    // Indicadores de RPM, Reset e Quota USD
    const indicatorsList = [];
    if (l.rpm) {
      indicatorsList.push(`Limite: ${l.rpm} RPM (Pico recente: ${c.rpm_atual} req/min)`);
    }
    if (l.usd_dia) {
      indicatorsList.push(`Cota Diária USD: $${l.usd_dia}/dia`);
    }
    if (l.reset) {
      indicatorsList.push(`Reset: ${l.reset.toUpperCase()}`);
    }
    if (p.tier === "LOCAL") {
      indicatorsList.push("Zero limites de rede (Acelerado em VRAM local)");
    }

    if (indicatorsList.length > 0) {
      quotaSection.appendChild(el("div", {
        style: "font-size:11px; color:var(--text-muted); display:flex; flex-wrap:wrap; gap:12px; background:rgba(255,255,255,0.02); padding:6px 8px; border-radius:4px;"
      }, indicatorsList.map(txt => el("span", { textContent: `• ${txt}` }))));
    }

    // Status de alerta se houver
    if (c.status_alerta !== "normal") {
      const isCrit = c.status_alerta === "critico" || c.status_alerta === "rate_limited";
      quotaSection.appendChild(el("div", {
        style: `font-size:11px; padding:6px 8px; border-radius:4px; font-weight:500; ${isCrit ? "background:rgba(239,68,68,0.1); color:#f87171; border:1px solid rgba(239,68,68,0.3);" : "background:rgba(245,158,11,0.1); color:#fbbf24; border:1px solid rgba(245,158,11,0.3);"}`
      }, [
        el("span", { textContent: isCrit ? "⚠ " : "ℹ " }),
        el("span", { textContent: c.motivo_alerta })
      ]));
    }

    // Economia / Custo
    const econOuCustoText = p.tier === "PAID"
      ? el("div", { style: "display:flex; justify-content:space-between; font-size:12px; margin-top:6px;" }, [
          el("span", { style: "color:var(--text-muted);", textContent: "Gasto acumulado:" }),
          el("strong", { style: "font-family:var(--font-mono);", textContent: formatarMoedaUSD(c.custo_usd) })
        ])
      : el("div", { style: "display:flex; justify-content:space-between; font-size:12px; margin-top:6px;" }, [
          el("span", { style: "color:var(--text-muted);", textContent: "Economia gerada:" }),
          el("strong", { style: "color:var(--success); font-family:var(--font-mono);", textContent: `+ ${formatarMoedaUSD(c.economia_usd)}` })
        ]);

    // Modelos utilizados neste provedor
    const containerModelos = el("div", { style: "margin-top:10px; border-top:1px solid var(--border-color); padding-top:8px;" });
    const modHeader = el("div", { style: "font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom:4px;", textContent: "Modelos Utilizados:" });
    containerModelos.appendChild(modHeader);

    if (p.modelos && p.modelos.length > 0) {
      const modUl = el("div", { style: "display:flex; flex-direction:column; gap:3px; max-height:120px; overflow-y:auto;" });
      p.modelos.forEach(m => {
        modUl.appendChild(el("div", {
          style: "display:flex; justify-content:space-between; font-size:11px; font-family:var(--font-mono); color:var(--text-secondary); padding:2px 0;"
        }, [
          el("span", { style: "white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:65%;", textContent: m.modelo }),
          el("span", { style: "color:var(--text-primary); font-weight:500;", textContent: `${formatarTokens(m.tokens_total)} (${m.requisicoes} reqs)` })
        ]));
      });
      containerModelos.appendChild(modUl);
    } else {
      containerModelos.appendChild(el("div", {
        style: "font-size:11px; color:var(--text-dim); font-style:italic;",
        textContent: "Nenhuma requisição realizada no período."
      }));
    }

    // Fonte de limites
    let fonteEl = null;
    if (p.fonte_limites) {
      fonteEl = el("div", {
        style: "font-size:10px; color:var(--text-dim); margin-top:8px; line-height:1.3; border-top:1px dashed var(--border-color); padding-top:6px;",
        textContent: `Fonte: ${p.fonte_limites}`
      });
    }

    // Montagem final do card
    const card = el("div", { className: "card card-limite" }, [
      el("div", {}, [cardHeader, gridMetricas, quotaSection, econOuCustoText, containerModelos]),
      fonteEl
    ]);

    grid.appendChild(card);
  });
}

// Event Listeners de Limites
$$(".btn-periodo").forEach(btn => {
  btn.addEventListener("click", () => {
    $$(".btn-periodo").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    periodoLimitesAtual = btn.dataset.periodo;
    carregarLimites();
  });
});

$$("[data-filter-limite-tier]").forEach(btn => {
  btn.addEventListener("click", () => {
    $$("[data-filter-limite-tier]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    filtroTierLimiteAtual = btn.dataset.filterLimiteTier;
    if (dadosLimitesCache) {
      renderizarCardsProvedores(dadosLimitesCache.provedores);
    }
  });
});

$("btn-recarregar-limites").addEventListener("click", () => {
  carregarLimites();
  toast("Métricas de limites e tokens atualizadas", "info");
});

// ------------------------------------------------ CADASTRO DE PROVEDORES & DESCOBERTA DINÂMICA
let scanResultadoAtual = null;
let scanFiltroFreeOnly = false;
let provedorSincronizandoId = null;

function abrirModalNovoProvedor() {
  $("prov-id").value = "";
  $("prov-nome").value = "";
  $("prov-tier").value = "PAID";
  $("prov-chave").value = "";
  $("prov-valor-chave").value = "";
  $("prov-api-base").value = "";
  $("prov-url-modelos").value = "";
  $("prov-site-chave").value = "";
  $("prov-rpm").value = "";
  $("prov-rpd").value = "";
  $("prov-fonte-limites").value = "";
  $("modal-provedor").classList.add("open");
}

const btnNovoProvModelos = $("btn-modal-novo-provedor");
if (btnNovoProvModelos) btnNovoProvModelos.addEventListener("click", abrirModalNovoProvedor);

const btnNovoProvLimites = $("btn-modal-novo-provedor-limites");
if (btnNovoProvLimites) btnNovoProvLimites.addEventListener("click", abrirModalNovoProvedor);

$("btn-salvar-provedor").addEventListener("click", async () => {
  const id = $("prov-id").value.trim().toLowerCase();
  const nome = $("prov-nome").value.trim();
  const tier = $("prov-tier").value;
  const chave = $("prov-chave").value.trim().toUpperCase();
  const valor_chave = $("prov-valor-chave").value.trim();
  const api_base = $("prov-api-base").value.trim();
  const url_modelos = $("prov-url-modelos").value.trim();
  const site_chave = $("prov-site-chave").value.trim();
  const rpm = $("prov-rpm").value.trim();
  const rpd = $("prov-rpd").value.trim();
  const fonte_limites = $("prov-fonte-limites").value.trim();

  if (!id || !nome || !chave) {
    toast("Preencha os campos obrigatórios: ID, Nome e Nome da Chave.", "error");
    return;
  }

  const limites = {};
  if (rpm) limites.rpm = parseInt(rpm, 10);
  if (rpd) limites.rpd = parseInt(rpd, 10);

  const payload = { id, nome, tier, chave, limites };
  if (valor_chave) payload.valor_chave = valor_chave;
  if (api_base) payload.api_base = api_base;
  if (url_modelos) payload.url_modelos = url_modelos;
  if (site_chave) payload.site_chave = site_chave;
  if (fonte_limites) payload.fonte_limites = fonte_limites;

  try {
    toast(`Cadastrando provedor ${nome}...`, "info");
    const res = await api("POST", "/api/provedores", payload);
    toast(`✓ Provedor ${res.nome} cadastrado com sucesso!`, "success");
    $("modal-provedor").classList.remove("open");
    cacheModelos = null;
    if (abaAtivaAtual === "modelos") carregarModelos();
    if (abaAtivaAtual === "limites") carregarLimites();
  } catch (e) {
    toast(`Erro ao cadastrar provedor: ${e.message}`, "error");
  }
});

// Modal de Descoberta Dinâmica de Modelos
async function abrirModalDescobrirModelos(provedorId, nome, tier) {
  provedorSincronizandoId = provedorId;
  $("modal-descobrir-titulo").textContent = `Modelos na API de ${nome}`;
  const badgeTier = $("modal-descobrir-badge-tier");
  badgeTier.className = `badge badge-${tier.toLowerCase()}`;
  badgeTier.textContent = tier;

  $("modal-descobrir-erro").style.display = "none";
  $("modal-descobrir-loading").style.display = "block";
  $("modal-descobrir-conteudo").style.display = "none";
  $("input-filtro-scan-modelos").value = "";
  scanFiltroFreeOnly = false;
  $("btn-filtro-scan-free-only").classList.remove("active");

  $("modal-descobrir-modelos").classList.add("open");

  try {
    const dados = await api("GET", `/api/provedores/${provedorId}/descobrir-modelos`);
    $("modal-descobrir-loading").style.display = "none";
    $("modal-descobrir-conteudo").style.display = "block";

    if (!dados.ok && dados.erro) {
      $("modal-descobrir-erro").style.display = "block";
      $("modal-descobrir-erro-msg").textContent = dados.erro;
    }

    scanResultadoAtual = dados;
    renderizarScanModelos();
  } catch (e) {
    $("modal-descobrir-loading").style.display = "none";
    $("modal-descobrir-erro").style.display = "block";
    $("modal-descobrir-erro-msg").textContent = e.message;
  }
}

function renderizarScanModelos() {
  if (!scanResultadoAtual) return;
  const { total_na_api, cadastrados, novos_disponiveis } = scanResultadoAtual;

  $("stat-scan-total").textContent = (total_na_api || 0).toLocaleString("pt-BR");
  $("stat-scan-cadastrados").textContent = (cadastrados || []).length.toLocaleString("pt-BR");
  $("stat-scan-novos").textContent = (novos_disponiveis || []).length.toLocaleString("pt-BR");

  // Renderizar Cadastrados
  const tbodyCadastrados = $("tbody-scan-cadastrados");
  tbodyCadastrados.innerHTML = "";
  (cadastrados || []).forEach(m => {
    const isAtivoApi = m.status_api === "ativo_na_api";
    const statusBadge = isAtivoApi
      ? el("span", { className: "badge badge-success", textContent: "✓ Ativo na API" })
      : el("span", { className: "badge badge-warning", textContent: "⚠ Ausente na API" });

    tbodyCadastrados.appendChild(el("tr", {}, [
      el("td", {}, [el("strong", { textContent: m.nome })]),
      el("td", { style: "font-family:var(--font-mono); font-size:11px; color:var(--text-muted);", textContent: m.id }),
      el("td", { textContent: (m.papeis || []).join(", ") }),
      el("td", {}, [statusBadge])
    ]));
  });

  // Renderizar Novos com Filtros
  const termo = $("input-filtro-scan-modelos").value.trim().toLowerCase();
  const tbodyNovos = $("tbody-scan-novos");
  tbodyNovos.innerHTML = "";

  const filtrados = (novos_disponiveis || []).filter(m => {
    if (scanFiltroFreeOnly && !m.free) return false;
    if (termo && !m.id.toLowerCase().includes(termo) && !m.nome.toLowerCase().includes(termo)) return false;
    return true;
  });

  if (filtrados.length === 0) {
    tbodyNovos.appendChild(el("tr", {}, [
      el("td", { colSpan: "4", style: "text-align:center; padding:20px; color:var(--text-dim);", textContent: "Nenhum modelo novo encontrado com os filtros atuais." })
    ]));
    return;
  }

  filtrados.forEach(m => {
    const badgeTipo = m.free
      ? el("span", { className: "badge badge-free", textContent: "FREE :free" })
      : el("span", { className: "badge badge-paid", textContent: "Nuvem" });

    const btnAdicionar = el("button", {
      className: "btn btn-primary btn-sm",
      style: "font-size:11px; padding:3px 8px;",
      textContent: "+ Adicionar ao Catálogo",
      onclick: () => abrirFormularioAdicionarModelo(m)
    });

    tbodyNovos.appendChild(el("tr", {}, [
      el("td", {}, [
        el("strong", { style: "font-family:var(--font-mono); font-size:12px;", textContent: m.id }),
        m.descricao ? el("div", { style: "font-size:11px; color:var(--text-muted); margin-top:2px;", textContent: m.descricao.slice(0, 90) }) : null
      ]),
      el("td", {}, [badgeTipo]),
      el("td", { style: "font-family:var(--font-mono); font-size:11px; color:var(--text-muted);", textContent: m.contexto ? `${(m.contexto / 1000).toFixed(0)}k` : "-" }),
      el("td", { style: "text-align:right;" }, [btnAdicionar])
    ]));
  });
}

function abrirFormularioAdicionarModelo(modeloApi) {
  const provId = provedorSincronizandoId;
  const idCompleto = modeloApi.id.includes("/") ? modeloApi.id : `${provId}/${modeloApi.id}`;
  const apelidoSugerido = `${provId}/${modeloApi.id.split("/").pop().replace(":free", "")}`;

  const nome = prompt(`Confirme o apelido interno do modelo para o LiteLLM:`, apelidoSugerido);
  if (!nome) return;

  const papeisStr = prompt(`Informe os papéis do modelo separados por vírgula (chat, codigo, agente, visao, raciocinio). Vazio = inferir pelo ID:`, "");
  if (papeisStr === null) return;
  const papeis = papeisStr.split(",").map(p => p.trim()).filter(Boolean);

  salvarNovoModeloProvedor(provId, {
    nome,
    id: idCompleto,
    papeis,
    contexto: modeloApi.contexto || null,
    ativo: false
  });
}

async function salvarNovoModeloProvedor(provId, payload) {
  try {
    toast(`Adicionando modelo ${payload.nome} ao provedor ${provId}...`, "info");
    const res = await api("POST", `/api/provedores/${provId}/modelos`, payload);
    toast(`✓ Modelo ${res.modelo.nome} adicionado com sucesso!`, "success");
    cacheModelos = null;
    abrirModalDescobrirModelos(provId, provId, "API");
    if (abaAtivaAtual === "modelos") carregarModelos();
    if (abaAtivaAtual === "limites") carregarLimites();
  } catch (e) {
    toast(`Erro ao adicionar modelo: ${e.message}`, "error");
  }
}

// Sincronização de modelos de todos os provedores com url_modelos (OpenRouter muda o catálogo com frequência)
function resumirSincronizacao(provedores) {
  let adicionados = 0, inativados = 0, protegidos = 0;
  const falhas = [];
  for (const [pid, r] of Object.entries(provedores)) {
    if (!r.ok) { falhas.push(`${pid}: ${r.erro}`); continue; }
    adicionados += r.adicionados.length;
    inativados += r.inativados.length;
    protegidos += r.protegidos_pelo_roteamento.length;
  }
  const partes = [`+${adicionados} novos (inativos)`, `${inativados} descontinuados inativados`];
  if (protegidos) partes.push(`${protegidos} mantidos por estarem no roteamento`);
  if (falhas.length) partes.push(`Falhas, sem alteração: ${falhas.join(" | ")}`);
  return { mudancas: adicionados + inativados, texto: partes.join(" · ") };
}

async function sincronizarNovosModelos() {
  const btn = $("btn-sincronizar-novos");
  btn.disabled = true;
  try {
    toast("Consultando as APIs dos provedores...", "info");
    const previa = await api("POST", "/api/provedores/sincronizar", { aplicar: false });
    const resumo = resumirSincronizacao(previa.provedores);
    if (resumo.mudancas === 0) {
      toast(`Catálogo em dia. ${resumo.texto}`, "success");
      return;
    }
    if (!confirm(`Prévia da sincronização:\n${resumo.texto}\n\nAplicar?`)) return;
    const res = await api("POST", "/api/provedores/sincronizar", { aplicar: true });
    const final = resumirSincronizacao(res.provedores);
    toast(`✓ ${final.texto}`, "success");
    cacheModelos = null;
    if (abaAtivaAtual === "modelos") carregarModelos();
  } catch (e) {
    toast(`Erro ao sincronizar: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
  }
}

let escolhaNovosItens = [];
let escolhaSoFree = true;
let escolhaNovosProvedor = null;  // null: todos os provedores; senão, só o escolhido no card

function filtrarEscolhaNovos() {
  const termoRaw = ($("input-filtro-escolher-novos").value || "").trim().toLowerCase();
  const termos = termoRaw ? termoRaw.split(/\s+/).filter(Boolean) : [];
  // Dentro do card de um provedor, o filtro FREE não se aplica: o usuário escolheu esse provedor
  const tierOk = (n) => escolhaNovosProvedor !== null || !escolhaSoFree || n.tier === "FREE";
  return escolhaNovosItens.filter(n => {
    if (!tierOk(n)) return false;
    if (termos.length === 0) return true;
    const textoCompleto = `${n.provedor} ${n.id} ${n.nome} ${(n.papeis || []).join(" ")} ${n.tier}`.toLowerCase();
    return termos.every(t => textoCompleto.includes(t));
  });
}

function atualizarContagemEscolha() {
  const marcados = escolhaNovosItens.filter(n => n.marcado).length;
  const visiveis = filtrarEscolhaNovos().length;
  const total = escolhaNovosItens.length;
  const termo = ($("input-filtro-escolher-novos").value || "").trim();

  const btnLimpar = $("btn-limpar-filtro-escolha");
  if (btnLimpar) {
    btnLimpar.style.display = termo ? "block" : "none";
  }

  const infoExibicao = (termo || escolhaSoFree) ? `${visiveis} de ${total} modelos exibidos` : `${total} modelos`;
  const infoMarcados = marcados ? ` · ${marcados} selecionado(s)` : "";
  $("escolher-novos-contagem").textContent = `${infoExibicao}${infoMarcados}`;
  $("btn-confirmar-escolha-novos").disabled = marcados === 0;
}

function renderizarEscolhaNovos() {
  const tbody = $("tbody-escolher-novos");
  tbody.innerHTML = "";
  const visiveis = filtrarEscolhaNovos();
  if (visiveis.length === 0) {
    tbody.appendChild(el("tr", {}, [
      el("td", { colSpan: "5", style: "text-align:center; padding:20px; color:var(--text-dim);", textContent: "Nenhum modelo novo com esse filtro." })
    ]));
  }
  visiveis.forEach(n => {
    tbody.appendChild(el("tr", {}, [
      el("td", {}, [el("input", { type: "checkbox", checked: n.marcado, onchange: (e) => { n.marcado = e.target.checked; atualizarContagemEscolha(); } })]),
      el("td", { textContent: n.provedor }),
      el("td", {}, [el("strong", { style: "font-family:var(--font-mono); font-size:12px;", textContent: n.id })]),
      el("td", { textContent: (n.papeis || []).join(", ") }),
      el("td", { textContent: n.tier || "-" })
    ]));
  });
  atualizarContagemEscolha();
}

async function abrirEscolherNovos(provedorId = null) {
  escolhaNovosItens = [];
  escolhaNovosProvedor = provedorId;
  $("escolher-novos-titulo").textContent = provedorId ? `Modelos novos: ${provedorId}` : "Escolher Modelos Novos";
  $("btn-escolher-novos-so-free").style.display = provedorId ? "none" : "";
  $("escolher-novos-loading").style.display = "block";
  $("escolher-novos-conteudo").style.display = "none";
  $("escolher-novos-erros").style.display = "none";
  $("input-filtro-escolher-novos").value = "";
  $("modal-escolher-novos").classList.add("open");
  try {
    const caminho = provedorId ? `/api/provedores/novos?provedor=${encodeURIComponent(provedorId)}` : "/api/provedores/novos";
    const dados = await api("GET", caminho);
    escolhaNovosItens = dados.novos.map(n => ({ ...n, marcado: false }));
    const erros = Object.entries(dados.erros || {});
    if (erros.length) {
      $("escolher-novos-erros").style.display = "block";
      $("escolher-novos-erros-msg").textContent = erros.map(([pid, msg]) => `${pid}: ${msg}`).join("\n");
    }
    $("escolher-novos-loading").style.display = "none";
    $("escolher-novos-conteudo").style.display = "block";
    renderizarEscolhaNovos();
  } catch (e) {
    $("escolher-novos-loading").style.display = "none";
    toast(`Erro ao listar modelos: ${e.message}`, "error");
    fecharModais();
  }
}

async function confirmarEscolhaNovos() {
  const itens = escolhaNovosItens
    .filter(n => n.marcado)
    .map(({ provedor, nome, id, papeis, contexto }) => ({ provedor, nome, id, papeis, contexto: contexto || null }));
  if (itens.length === 0) return;
  try {
    const res = await api("POST", "/api/provedores/modelos-lote", { itens });
    const recusados = res.recusados.length ? ` · ${res.recusados.length} recusado(s)` : "";
    toast(`✓ ${res.adicionados.length} modelo(s) adicionado(s)${recusados}`, "success");
    fecharModais();
    cacheModelos = null;
    if (abaAtivaAtual === "modelos") carregarModelos();
  } catch (e) {
    toast(`Erro ao adicionar modelos: ${e.message}`, "error");
  }
}

$("btn-sincronizar-novos").addEventListener("click", sincronizarNovosModelos);
$("btn-escolher-novos").addEventListener("click", () => abrirEscolherNovos());
$("input-filtro-escolher-novos").addEventListener("input", renderizarEscolhaNovos);
const btnLimparFiltroEscolha = $("btn-limpar-filtro-escolha");
if (btnLimparFiltroEscolha) {
  btnLimparFiltroEscolha.addEventListener("click", () => {
    $("input-filtro-escolher-novos").value = "";
    renderizarEscolhaNovos();
  });
}
$("btn-escolher-novos-so-free").addEventListener("click", () => {
  escolhaSoFree = !escolhaSoFree;
  $("btn-escolher-novos-so-free").classList.toggle("active", escolhaSoFree);
  renderizarEscolhaNovos();
});
$("btn-escolher-novos-marcar-visiveis").addEventListener("click", () => {
  filtrarEscolhaNovos().forEach(n => { n.marcado = true; });
  renderizarEscolhaNovos();
});
$("btn-confirmar-escolha-novos").addEventListener("click", confirmarEscolhaNovos);

// Filtros do modal de scan
$("input-filtro-scan-modelos").addEventListener("input", renderizarScanModelos);
$("btn-filtro-scan-free-only").addEventListener("click", () => {
  scanFiltroFreeOnly = !scanFiltroFreeOnly;
  $("btn-filtro-scan-free-only").classList.toggle("active", scanFiltroFreeOnly);
  renderizarScanModelos();
});

// ------------------------------------------------ MODAIS DE MODELOS LOCAIS (OLLAMA) E GRUPOS DO ROTEADOR
const btnModalBaixarLocal = $("btn-modal-baixar-modelo-local");
if (btnModalBaixarLocal) {
  btnModalBaixarLocal.addEventListener("click", () => {
    $("input-nome-modelo-local").value = "";
    $("status-download-modelo").style.display = "none";
    $("btn-confirmar-baixar-modelo").disabled = false;
    $("modal-baixar-modelo-local").classList.add("open");
  });
}

$$(".btn-tag-sugestao").forEach(btn => {
  btn.addEventListener("click", () => {
    $("input-nome-modelo-local").value = btn.dataset.tag || "";
  });
});

const btnConfirmarBaixarModelo = $("btn-confirmar-baixar-modelo");
if (btnConfirmarBaixarModelo) {
  btnConfirmarBaixarModelo.addEventListener("click", async () => {
    const nome = $("input-nome-modelo-local").value.trim();
    if (!nome) {
      toast("Informe o nome do modelo Ollama (ex: qwen2.5-coder:7b)", "error");
      return;
    }
    const statusBox = $("status-download-modelo");
    const txtStatus = $("txt-status-download");
    statusBox.style.display = "block";
    txtStatus.textContent = `Baixando '${nome}' do registro Ollama...`;
    btnConfirmarBaixarModelo.disabled = true;

    try {
      await api("POST", "/api/modelos/local/baixar", { nome });
      toast(`✓ Modelo '${nome}' baixado e instalado com sucesso!`, "success");
      $("modal-baixar-modelo-local").classList.remove("open");
      cacheModelos = null;
      await carregarModelos();
    } catch (e) {
      toast(`Falha ao baixar '${nome}': ${e.message}`, "error");
    } finally {
      statusBox.style.display = "none";
      btnConfirmarBaixarModelo.disabled = false;
    }
  });
}

// Modal Novo Grupo do Roteador
const btnModalNovoGrupo = $("btn-modal-novo-grupo");
if (btnModalNovoGrupo) {
  btnModalNovoGrupo.addEventListener("click", () => {
    $("input-novo-grupo-id").value = "tudoia-";
    $("input-novo-grupo-titulo").value = "";
    $("input-novo-grupo-desc").value = "";
    $("modal-novo-grupo").classList.add("open");
  });
}

const btnSalvarNovoGrupo = $("btn-salvar-novo-grupo");
if (btnSalvarNovoGrupo) {
  btnSalvarNovoGrupo.addEventListener("click", async () => {
    const id = $("input-novo-grupo-id").value.trim().toLowerCase();
    const titulo = $("input-novo-grupo-titulo").value.trim();
    const descricao = $("input-novo-grupo-desc").value.trim();
    if (!id || !titulo) {
      toast("Informe o identificador (ID) e o título do grupo.", "error");
      return;
    }
    btnSalvarNovoGrupo.disabled = true;
    try {
      await api("POST", "/api/roteador/grupos/novo", { id, titulo, descricao, modelos: [] });
      toast(`✓ Grupo '${id}' criado com sucesso!`, "success");
      $("modal-novo-grupo").classList.remove("open");
      await carregarRoteador();
    } catch (e) {
      toast(`Erro ao criar grupo: ${e.message}`, "error");
    } finally {
      btnSalvarNovoGrupo.disabled = false;
    }
  });
}

// Modal Editar Grupo do Roteador
const checkEditarGrupoAtivo = $("check-editar-grupo-ativo");
if (checkEditarGrupoAtivo) {
  checkEditarGrupoAtivo.addEventListener("change", () => {
    const lbl = $("txt-editar-grupo-ativo");
    if (checkEditarGrupoAtivo.checked) {
      lbl.textContent = "Ativo";
      lbl.style.color = "var(--success)";
    } else {
      lbl.textContent = "Desativado";
      lbl.style.color = "var(--text-muted)";
    }
  });
}

function abrirModalEditarGrupo(g) {
  $("input-editar-grupo-id").value = g.id;
  $("modal-editar-grupo-titulo-topo").textContent = `Editar Grupo: ${g.id}`;
  $("input-editar-grupo-titulo").value = g.titulo || "";
  $("input-editar-grupo-desc").value = g.descricao || "";
  const isAtivo = g.ativo !== false;
  $("check-editar-grupo-ativo").checked = isAtivo;
  const lbl = $("txt-editar-grupo-ativo");
  lbl.textContent = isAtivo ? "Ativo" : "Desativado";
  lbl.style.color = isAtivo ? "var(--success)" : "var(--text-muted)";
  $("modal-editar-grupo").classList.add("open");
}

const btnConfirmarEdicaoGrupo = $("btn-confirmar-edicao-grupo");
if (btnConfirmarEdicaoGrupo) {
  btnConfirmarEdicaoGrupo.addEventListener("click", async () => {
    const id = $("input-editar-grupo-id").value;
    const titulo = $("input-editar-grupo-titulo").value.trim();
    const descricao = $("input-editar-grupo-desc").value.trim();
    const ativo = $("check-editar-grupo-ativo").checked;

    btnConfirmarEdicaoGrupo.disabled = true;
    try {
      await api("PATCH", `/api/roteador/grupos/${encodeURIComponent(id)}`, {
        titulo: titulo || null,
        descricao: descricao,
        ativo
      });
      toast(`✓ Grupo '${id}' atualizado com sucesso!`, "success");
      $("modal-editar-grupo").classList.remove("open");
      await carregarRoteador();
    } catch (e) {
      toast(`Erro ao atualizar grupo: ${e.message}`, "error");
    } finally {
      btnConfirmarEdicaoGrupo.disabled = false;
    }
  });
}

// ==========================================================================
// ESTÚDIO TUDOIA: CHAT, IMAGENS, VÍDEOS
// ==========================================================================

// 1. CHAT PLAYGROUND
let historicoChat = [];
let enviandoChat = false;

function carregarChat() {
  const select = $("chat-select-modelo");
  if (!select) return;
  if (dadosRoteadorCache && dadosRoteadorCache.grupos) {
    const valorAtual = select.value || "tudoia-auto";
    const opcoes = ["tudoia-auto", ...dadosRoteadorCache.grupos.map(g => g.id)];
    const optionsHtml = opcoes.map(id => `<option value="${esc(id)}">${esc(id)}</option>`).join("");
    if (select.innerHTML !== optionsHtml) {
      select.innerHTML = optionsHtml;
      select.value = opcoes.includes(valorAtual) ? valorAtual : "tudoia-auto";
    }
  }
}

async function enviarMensagemChat(textoCustomizado = null) {
  if (enviandoChat) return;
  const input = $("chat-input-texto");
  const texto = (textoCustomizado !== null ? textoCustomizado : input.value).trim();
  if (!texto) return;

  const modelo = $("chat-select-modelo").value || "tudoia-auto";
  const temp = parseFloat($("chat-range-temp").value) || 0.7;
  const container = $("chat-mensagens-box");
  const emptyState = $("chat-empty-state");
  if (emptyState) emptyState.style.display = "none";

  // 1. Mensagem do Usuário
  historicoChat.push({ role: "user", content: texto });
  if (textoCustomizado === null) input.value = "";

  const divUser = el("div", { className: "chat-message chat-message-user" }, [
    el("div", { className: "chat-msg-avatar", textContent: "VC" }),
    el("div", { className: "chat-msg-bubble", textContent: texto })
  ]);
  container.appendChild(divUser);

  // 2. Placeholder do Assistente
  const metaInfo = $("chat-meta-info");
  metaInfo.textContent = `Consultando ${modelo}...`;
  metaInfo.style.color = "var(--brand-primary)";

  const bubbleAssistente = el("div", { className: "chat-msg-bubble", style: "color:var(--text-muted); font-style:italic;", textContent: "Pensando..." });
  const footerAssistente = el("div", { className: "chat-msg-footer" });
  const divAssistente = el("div", { className: "chat-message chat-message-assistant" }, [
    el("div", { className: "chat-msg-avatar", textContent: "IA" }),
    el("div", {}, [bubbleAssistente, footerAssistente])
  ]);
  container.appendChild(divAssistente);
  container.scrollTop = container.scrollHeight;

  enviandoChat = true;
  const btnEnviar = $("btn-enviar-chat");
  btnEnviar.disabled = true;

  try {
    const res = await api("POST", "/api/chat/completions", {
      model: modelo,
      messages: historicoChat,
      temperature: temp,
      max_tokens: 2048
    });

    if (res.ok && res.message) {
      bubbleAssistente.textContent = res.message.content;
      bubbleAssistente.style.color = "var(--text-primary)";
      bubbleAssistente.style.fontStyle = "normal";

      historicoChat.push({ role: "assistant", content: res.message.content });

      footerAssistente.replaceChildren(
        el("span", { style: "color:var(--brand-primary);", textContent: res.model || modelo }),
        el("span", { textContent: `· ${res.latencia_ms}ms` }),
        el("span", { textContent: `· ${res.usage?.total_tokens || 0} tokens` }),
        el("span", { textContent: `· motor: ${res.motor}` })
      );
      metaInfo.textContent = `Resposta concluída em ${res.latencia_ms}ms (${res.model})`;
      metaInfo.style.color = "var(--success)";
    } else {
      bubbleAssistente.textContent = `Erro: ${res.erro || "Falha na resposta do modelo"}`;
      bubbleAssistente.style.color = "var(--danger)";
      metaInfo.textContent = "Erro na geração";
      metaInfo.style.color = "var(--danger)";
    }
  } catch (err) {
    bubbleAssistente.textContent = `Erro: ${err.message}`;
    bubbleAssistente.style.color = "var(--danger)";
    metaInfo.textContent = "Erro de conexão";
    metaInfo.style.color = "var(--danger)";
  } finally {
    enviandoChat = false;
    btnEnviar.disabled = false;
    container.scrollTop = container.scrollHeight;
  }
}

// Eventos de Chat
const btnEnviarChat = $("btn-enviar-chat");
if (btnEnviarChat) {
  btnEnviarChat.addEventListener("click", () => enviarMensagemChat());
}

const inputChatTexto = $("chat-input-texto");
if (inputChatTexto) {
  inputChatTexto.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviarMensagemChat();
    }
  });
}

const rangeTemp = $("chat-range-temp");
if (rangeTemp) {
  rangeTemp.addEventListener("input", () => {
    $("chat-temp-val").textContent = rangeTemp.value;
  });
}

const btnLimparChat = $("btn-limpar-chat");
if (btnLimparChat) {
  btnLimparChat.addEventListener("click", () => {
    historicoChat = [];
    const container = $("chat-mensagens-box");
    container.replaceChildren();
    const empty = $("chat-empty-state");
    if (empty) {
      empty.style.display = "flex";
      container.appendChild(empty);
    }
    $("chat-meta-info").textContent = "Conversa limpa";
    toast("Histórico do chat limpo.", "info");
  });
}

document.addEventListener("click", (e) => {
  const btnSug = e.target.closest(".btn-sugestao-prompt");
  if (btnSug && btnSug.dataset.prompt) {
    enviarMensagemChat(btnSug.dataset.prompt);
  }
});


// 2. GERADOR DE IMAGENS
let aspectRatioSelecionado = "1:1";
let ultimaImagemGeradaUrl = null;
let galeriaImagensSessao = [];

async function carregarImagens() {
  if (!inpaintingInicializado) {
    inicializarInpainting();
    inpaintingInicializado = true;
  }
  const badge = $("badge-status-comfyui");
  try {
    const st = await api("GET", "/api/estudio/status-motores");
    if (st.comfyui) {
      badge.textContent = "ComfyUI :8188 online (GPU)";
      badge.className = "badge badge-free";
    } else {
      badge.textContent = "ComfyUI :8188 OFFLINE (Nuvem Ativa)";
      badge.className = "badge badge-role";
    }
  } catch (e) {
    badge.textContent = "ComfyUI :8188 INDISPONÍVEL";
    badge.className = "badge badge-role";
  }

  // Carrega catálogo dinâmico de modelos de imagem e vídeo
  await carregarCatalogoModelos();

  // Carrega histórico de imagens existentes em disco
  try {
    const resImgs = await api("GET", "/api/estudio/imagens");
    if (resImgs.ok && Array.isArray(resImgs.imagens)) {
      galeriaImagensSessao = resImgs.imagens.map(img => ({
        url: img.url,
        prompt: img.nome,
        res: img.tamanho ? `${Math.round(img.tamanho / 1024)} KB` : ""
      }));
      renderizarGaleriaImagens();

      // Se há imagem salva e nenhuma exibida ainda, exibe a mais recente no canvas
      if (!ultimaImagemGeradaUrl && galeriaImagensSessao.length > 0) {
        selecionarImagemCanvas(galeriaImagensSessao[0].url, galeriaImagensSessao[0].prompt);
      }
    }
  } catch (e) {
    console.warn("Falha ao carregar galeria de imagens:", e);
  }
}

let catalogoModelosCarregado = false;
async function carregarCatalogoModelos() {
  if (catalogoModelosCarregado) return;
  try {
    const cat = await api("GET", "/api/estudio/catalogo-modelos");
    if (!cat.ok) return;

    // Popula modelos de imagem
    const selectImg = $("img-select-modelo");
    if (selectImg && cat.imagem) {
      selectImg.replaceChildren();

      // Grupo Nuvem (se houver)
      if ((cat.imagem.nuvem || []).length > 0) {
        const grpNuvem = el("optgroup", { label: "Modelos em Nuvem (Prontos)" });
        (cat.imagem.nuvem || []).forEach(m => {
          grpNuvem.appendChild(el("option", { value: m.id, textContent: m.rotulo || m.nome }));
        });
        selectImg.appendChild(grpNuvem);
      }

      // Grupo Local ComfyUI (Checkpoints)
      const checkpointsLocais = (cat.imagem.locais || []).filter(m => m.tipo === "local");
      if (checkpointsLocais.length > 0) {
        const grpLocal = el("optgroup", { label: "Modelos Locais Checkpoints (GPU · Sem Watermark)" });
        checkpointsLocais.forEach(m => {
          grpLocal.appendChild(el("option", { value: m.id, textContent: m.rotulo || m.nome }));
        });
        selectImg.appendChild(grpLocal);
      }
    }

    // Popula modelos de vídeo
    const selectVid = $("vid-select-modelo");
    if (selectVid && cat.video) {
      selectVid.replaceChildren();

      // Checkpoints brutos
      const checkpointsVid = (cat.video.locais || []).filter(m => m.tipo === "local");
      if (checkpointsVid.length > 0) {
        const grpLocal = el("optgroup", { label: "Modelos Locais Brutos (*.safetensors)" });
        checkpointsVid.forEach(m => {
          grpLocal.appendChild(el("option", { value: m.id, textContent: m.rotulo || m.nome }));
        });
        selectVid.appendChild(grpLocal);
      }

      if ((cat.video.nuvem || []).length > 0) {
        const grpNuvem = el("optgroup", { label: "Modelos em Nuvem" });
        (cat.video.nuvem || []).forEach(m => {
          grpNuvem.appendChild(el("option", { value: m.id, textContent: m.rotulo || m.nome }));
        });
        selectVid.appendChild(grpNuvem);
      }

      mapaModelosVideo = {};
      (cat.video.locais || []).forEach(m => { mapaModelosVideo[m.id] = m; });
      (cat.video.nuvem || []).forEach(m => { mapaModelosVideo[m.id] = m; });
            const optMinimax = Array.from(selectVid.options).find(o => o.value.toLowerCase().includes("minimax"));
      if (optMinimax) {
        selectVid.value = optMinimax.value;
      }
      atualizarModoVideoPorModelo();
    }

    catalogoModelosCarregado = true;
  } catch (e) {
    console.warn("Falha ao carregar catálogo de modelos:", e);
  }
}

let mapaModelosVideo = {};

// Sincronização inteligente entre seletores de modelo e motor
const selectModeloImg = $("img-select-modelo");
if (selectModeloImg) {
  selectModeloImg.addEventListener("change", () => {
    const val = selectModeloImg.value;
    const selectMotor = $("img-select-motor");
    if (!selectMotor) return;
    if (val.startsWith("local:")) {
      selectMotor.value = "comfyui";
      toast("Modelo local selecionado: requer ComfyUI ativo na GPU.", "info");
    } else {
      selectMotor.value = "nuvem";
    }
  });
}

const selectModeloVid = $("vid-select-modelo");
if (selectModeloVid) {
  selectModeloVid.addEventListener("change", () => {
    const val = selectModeloVid.value;
    const selectMotor = $("vid-select-motor");
    if (!selectMotor) return;
    if (val.startsWith("local:")) {
      selectMotor.value = "comfyui";
    }
  });
}

function selecionarImagemCanvas(url, prompt = "") {
  ultimaImagemGeradaUrl = url;
  const wrapper = $("img-wrapper-inpaint");
  const preview = $("img-canvas-preview");
  const placeholder = $("img-canvas-placeholder");
  const metaStrip = $("img-meta-strip");
  const btnInpaint = $("btn-modo-inpaint");

  if (wrapper) wrapper.style.display = "inline-block";
  preview.src = url;
  preview.style.display = "block";
  placeholder.style.display = "none";

  $("btn-baixar-imagem").disabled = false;
  $("btn-copiar-link-imagem").disabled = false;
  const btnExcluir = $("btn-excluir-imagem");
  if (btnExcluir) btnExcluir.disabled = false;
  if (btnInpaint) btnInpaint.disabled = false;

  metaStrip.style.display = "flex";
  $("img-meta-dim").textContent = url.split("/").pop();
  $("img-meta-latencia").textContent = "Disco local";
  $("img-meta-motor").textContent = "Salva";

  if (modoInpaintAtivo) {
    sincronizarDimensoesCanvasInpaint();
  }

  renderizarGaleriaImagens();
}

function limparCanvasImagem() {
  ultimaImagemGeradaUrl = null;
  const wrapper = $("img-wrapper-inpaint");
  const preview = $("img-canvas-preview");
  const placeholder = $("img-canvas-placeholder");
  const metaStrip = $("img-meta-strip");
  const btnInpaint = $("btn-modo-inpaint");

  if (wrapper) wrapper.style.display = "none";
  preview.src = "";
  preview.style.display = "none";
  placeholder.style.display = "flex";
  metaStrip.style.display = "none";

  $("btn-baixar-imagem").disabled = true;
  $("btn-copiar-link-imagem").disabled = true;
  const btnExcluir = $("btn-excluir-imagem");
  if (btnExcluir) btnExcluir.disabled = true;
  if (btnInpaint) btnInpaint.disabled = true;

  if (modoInpaintAtivo) {
    desativarModoInpaint();
  }
}

async function excluirImagemPorUrl(url) {
  if (!url) return;
  const nomeArquivo = url.split("/").pop();
  if (!confirm(`Deseja excluir permanentemente a imagem "${nomeArquivo}" do disco?`)) return;

  try {
    const res = await api("DELETE", `/api/estudio/imagens/${encodeURIComponent(nomeArquivo)}`);
    if (res.ok) {
      toast(`Imagem "${nomeArquivo}" excluída do disco.`, "success");
      galeriaImagensSessao = galeriaImagensSessao.filter(item => item.url !== url);

      if (ultimaImagemGeradaUrl === url) {
        if (galeriaImagensSessao.length > 0) {
          selecionarImagemCanvas(galeriaImagensSessao[0].url, galeriaImagensSessao[0].prompt);
        } else {
          limparCanvasImagem();
        }
      }
      renderizarGaleriaImagens();
    } else {
      toast(`Falha ao excluir imagem: ${res.erro || "Erro no servidor"}`, "error");
    }
  } catch (e) {
    toast(`Erro ao excluir imagem: ${e.message}`, "error");
  }
}

$$("#img-aspect-selector .btn-aspect").forEach(btn => {
  btn.addEventListener("click", () => {
    $$("#img-aspect-selector .btn-aspect").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    aspectRatioSelecionado = btn.dataset.ratio;
  });
});

const rangeSteps = $("img-steps");
if (rangeSteps) {
  rangeSteps.addEventListener("input", () => {
    $("img-steps-val").textContent = rangeSteps.value;
  });
}


// ------------------------------------------------ CONTROLE DE PROGRESSO & MODELOS INPAINT
let timerProgressoImg = null;
let inicioProgressoImg = 0;

function iniciarProgressoGeracao(faseTexto, detalheTexto) {
  const container = $("img-progresso-container");
  const barra = $("img-progresso-barra");
  const fase = $("img-progresso-fase-txt");
  const detalhe = $("img-progresso-detalhe");
  const timer = $("img-progresso-timer");

  if (container) container.style.display = "block";
  if (barra) barra.style.width = "12%";
  if (fase) fase.textContent = faseTexto || "Iniciando geração com IA...";
  if (detalhe) detalhe.textContent = detalheTexto || "Conectando ao motor de difusão...";
  if (timer) timer.textContent = "0.0s";

  $("btn-gerar-imagem").disabled = true;
  $("img-prompt").disabled = true;
  const pNeg = $("img-prompt-negativo");
  if (pNeg) pNeg.disabled = true;

  inicioProgressoImg = Date.now();
  if (timerProgressoImg) clearInterval(timerProgressoImg);

  timerProgressoImg = setInterval(() => {
    const decorrido = (Date.now() - inicioProgressoImg) / 1000;
    if (timer) timer.textContent = `${decorrido.toFixed(1)}s`;

    if (barra) {
      if (decorrido < 2.0) {
        barra.style.width = `${Math.min(30, 12 + decorrido * 9)}%`;
        if (fase) fase.textContent = "Traduzindo e enriquecendo prompt visual com IA...";
        if (detalhe) detalhe.textContent = "Otimizando descritores arquitetônicos e iluminação para SDXL/FLUX...";
      } else if (decorrido < 12.0) {
        barra.style.width = `${Math.min(88, 30 + (decorrido - 2) * 5.8)}%`;
        if (fase) fase.textContent = "Executando KSampler de Difusão na GPU...";
        if (detalhe) detalhe.textContent = "Calculando tensores latentes e refinando ruído visual...";
      } else {
        barra.style.width = `${Math.min(96, 88 + (decorrido - 12) * 0.8)}%`;
        if (fase) fase.textContent = "Decodificando VAE e finalizando imagem...";
        if (detalhe) detalhe.textContent = "Convertendo espaço latente para pixels em alta resolução...";
      }
    }
  }, 200);
}

function finalizarProgressoGeracao(sucesso = true) {
  if (timerProgressoImg) {
    clearInterval(timerProgressoImg);
    timerProgressoImg = null;
  }
  const container = $("img-progresso-container");
  const barra = $("img-progresso-barra");
  const fase = $("img-progresso-fase-txt");
  const detalhe = $("img-progresso-detalhe");

  if (barra) barra.style.width = "100%";
  if (fase) fase.textContent = sucesso ? "✓ Concluído com Sucesso!" : "⚠ Finalizado com ressalvas";
  if (detalhe) detalhe.textContent = sucesso ? "Imagem renderizada e carregada no Canvas." : "Verifique os detalhes na tela.";

  $("btn-gerar-imagem").disabled = false;
  $("img-prompt").disabled = false;
  const pNeg = $("img-prompt-negativo");
  if (pNeg) pNeg.disabled = false;

  setTimeout(() => {
    if (container) container.style.display = "none";
  }, 800);
}

function atualizarDisponibilidadeModelosInpaint(emModoInpaint) {
  const selectModelo = $("img-select-modelo");
  const selectMotor = $("img-select-motor");
  if (!selectModelo) return;

  let inpaintOpt = null;
  for (const opt of selectModelo.options) {
    if (opt.value.includes("inpaint")) {
      inpaintOpt = opt;
      opt.disabled = !emModoInpaint;
      if (!emModoInpaint) {
        if (!opt.textContent.includes("(Apenas no Inpainting)")) {
          opt.textContent = `${opt.textContent} (Apenas no Inpainting)`;
        }
      } else {
        opt.textContent = opt.textContent.replace(" (Apenas no Inpainting)", "");
      }
    }
  }

  // Se a opção de inpainting ainda não estiver no select, insere dinamicamente
  if (!inpaintOpt) {
    inpaintOpt = el("option", {
      value: "inpaint-tudoia",
      textContent: " Inpaint Tudoia (ComfyUI)"
    });
    selectModelo.appendChild(inpaintOpt);
  }

  if (emModoInpaint) {
    inpaintOpt.disabled = false;
    selectModelo.value = inpaintOpt.value;
    selectModelo.disabled = true;
    selectModelo.title = "Modelo travado para Inpainting: Inpaint Tudoia (GPU)";
    selectModelo.style.opacity = "1";
    selectModelo.style.color = "var(--brand-primary)";
    selectModelo.style.fontWeight = "600";
    selectModelo.style.backgroundColor = "rgba(99,102,241,0.08)";
    selectModelo.style.borderColor = "var(--brand-primary)";
    selectModelo.style.cursor = "not-allowed";

    if (selectMotor) {
      selectMotor.value = "comfyui";
      selectMotor.disabled = true;
      selectMotor.style.opacity = "1";
    }
  } else {
    selectModelo.disabled = false;
    selectModelo.title = "";
    selectModelo.style.opacity = "";
    selectModelo.style.color = "";
    selectModelo.style.fontWeight = "";
    selectModelo.style.backgroundColor = "";
    selectModelo.style.borderColor = "";
    selectModelo.style.cursor = "";

    if (selectModelo.value.includes("inpaint") || !selectModelo.value) {
      const primeiraOpcaoNormal = Array.from(selectModelo.options).find(o => !o.value.includes("inpaint"));
      if (primeiraOpcaoNormal) {
        selectModelo.value = primeiraOpcaoNormal.value;
      }
    }
    if (selectMotor) {
      selectMotor.disabled = false;
      selectMotor.style.opacity = "";
    }
  }
}

function exibirAvisoPromptOtimizado(res) {
  const aviso = $("img-prompt-aviso-traducao");
  const tit = $("img-prompt-aviso-titulo");
  const txt = $("img-prompt-aviso-texto");
  if (!aviso || !tit || !txt) return;

  if (res.prompt_otimizado && res.prompt) {
    tit.textContent = res.prompt_msg || "Traduzido e Enriquecido com IA:";
    txt.textContent = `"${res.prompt}"`;
    aviso.style.display = "block";
    toast(" Prompt em português traduzido e enriquecido para o SDXL/FLUX!", "info");
  } else {
    aviso.style.display = "none";
  }
}

// Detecção dinâmica de português enquanto o usuário digita no prompt
const campoImgPrompt = $("img-prompt");
if (campoImgPrompt) {
  campoImgPrompt.addEventListener("input", () => {
    const val = campoImgPrompt.value;
    const dicaPt = $("img-prompt-dica-pt");
    if (!dicaPt) return;
    const temAcentos = /[áéíóúãõâêîôûàèìòùçÁÉÍÓÚÃÕÂÊÎÔÛÀÈÌÒÙÇ]/i.test(val);
    const temTermosPt = /\b(de|do|da|dos|das|um|uma|com|em|no|na|para|por|incluir|colocar|criar|imagem|foto|prédio|museu|são|paulo|cidade|rua|masp)\b/i.test(val);
    if ((temAcentos || temTermosPt) && val.trim().length > 3) {
      dicaPt.style.display = "block";
    } else {
      dicaPt.style.display = "none";
    }
  });
}

// Botão 'Melhorar com IA' para otimização sob demanda antes de gerar
const btnOtimizarManual = $("btn-otimizar-prompt-manual");
if (btnOtimizarManual) {
  btnOtimizarManual.addEventListener("click", async () => {
    const val = $("img-prompt").value.trim();
    if (!val) {
      toast("Digite uma ideia ou prompt antes de otimizar.", "warning");
      $("img-prompt").focus();
      return;
    }
    btnOtimizarManual.disabled = true;
    btnOtimizarManual.textContent = "⏳ Otimizando...";
    try {
      const res = await api("POST", "/api/estudio/otimizar-prompt", { prompt: val });
      if (res.ok && res.prompt) {
        exibirAvisoPromptOtimizado(res);
        toast("Prompt traduzido e enriquecido! Veja o resultado no card abaixo.", "success");
      } else {
        toast("Não foi possível otimizar o prompt no momento.", "warning");
      }
    } catch (e) {
      toast(`Erro ao otimizar: ${e.message}`, "error");
    } finally {
      btnOtimizarManual.disabled = false;
      btnOtimizarManual.textContent = " Melhorar com IA";
    }
  });
}

// Botão para aplicar o prompt traduzido no campo
const btnAplicarTraduzido = $("btn-aplicar-prompt-traduzido");
if (btnAplicarTraduzido) {
  btnAplicarTraduzido.addEventListener("click", () => {
    const txt = $("img-prompt-aviso-texto");
    if (txt && txt.textContent) {
      const limpo = txt.textContent.replace(/^"|"$/g, "").trim();
      $("img-prompt").value = limpo;
      $("img-prompt-dica-pt").style.display = "none";
      toast("Prompt aplicado no campo!", "success");
    }
  });
}

// Botão para copiar o prompt traduzido
const btnCopiarTraduzido = $("btn-copiar-prompt-traduzido");
if (btnCopiarTraduzido) {
  btnCopiarTraduzido.addEventListener("click", () => {
    const txt = $("img-prompt-aviso-texto");
    if (txt && txt.textContent) {
      const limpo = txt.textContent.replace(/^"|"$/g, "").trim();
      navigator.clipboard.writeText(limpo);
      toast("Prompt copiado para a área de transferência!", "info");
    }
  });
}

// ------------------------------------------------ INPAINTING INTERATIVO
let modoInpaintAtivo = false;
let ferramentaInpaintAtual = "pincel"; // "pincel" ou "borracha"
let tamanhoPincel = 35;
let desenhandoNoCanvas = false;
let mascaraPossuiTinta = false;
let maskCanvasCtx = null;
let inpaintingInicializado = false;
let historicoPinturaInpaint = [];
let imagemBaseAntesInpaint = null;

function inicializarInpainting() {
  const btnFecharAviso = $("btn-fechar-aviso-traducao");
  if (btnFecharAviso) {
    btnFecharAviso.addEventListener("click", () => {
      const aviso = $("img-prompt-aviso-traducao");
      if (aviso) aviso.style.display = "none";
    });
  }

  atualizarDisponibilidadeModelosInpaint(false);
  const maskCanvas = $("inpaint-mask-canvas");
  if (!maskCanvas) return;
  maskCanvasCtx = maskCanvas.getContext("2d");

  function iniciarDesenho(e) {
    if (!modoInpaintAtivo || !maskCanvasCtx) return;
    // Salva estado para Desfazer (Ctrl+Z)
    if (historicoPinturaInpaint.length >= 12) historicoPinturaInpaint.shift();
    historicoPinturaInpaint.push(maskCanvasCtx.getImageData(0, 0, maskCanvas.width, maskCanvas.height));
    desenhandoNoCanvas = true;
    desenharPonto(e);
  }

  function atualizarCursorPincel(e) {
    const cursor = $("inpaint-cursor-brush");
    if (!cursor || !modoInpaintAtivo) return;
    const rect = maskCanvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    const scaleVisual = rect.width / (maskCanvas.width || 1);
    const diametro = Math.max(10, (tamanhoPincel * (maskCanvas.width / (rect.width || 1))) * scaleVisual);

    cursor.style.display = "block";
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
    cursor.style.width = `${diametro}px`;
    cursor.style.height = `${diametro}px`;
    if (ferramentaInpaintAtual === "borracha") {
      cursor.style.borderColor = "rgba(56, 189, 248, 0.9)";
      cursor.style.background = "rgba(56, 189, 248, 0.1)";
    } else {
      cursor.style.borderColor = "rgba(239, 68, 68, 0.9)";
      cursor.style.background = "rgba(239, 68, 68, 0.15)";
    }
  }

  function desenhar(e) {
    if (modoInpaintAtivo) atualizarCursorPincel(e);
    if (!desenhandoNoCanvas || !modoInpaintAtivo) return;
    e.preventDefault();
    desenharPonto(e);
  }

  function finalizarDesenho() {
    if (!desenhandoNoCanvas) return;
    desenhandoNoCanvas = false;
    if (maskCanvasCtx) maskCanvasCtx.beginPath();
  }

  function desenharPonto(e) {
    if (!maskCanvasCtx) return;
    const rect = maskCanvas.getBoundingClientRect();
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const scaleX = maskCanvas.width / (rect.width || 1);
    const scaleY = maskCanvas.height / (rect.height || 1);
    const x = (clientX - rect.left) * scaleX;
    const y = (clientY - rect.top) * scaleY;
    const raio = (tamanhoPincel / 2) * scaleX;

    maskCanvasCtx.save();
    if (ferramentaInpaintAtual === "borracha") {
      maskCanvasCtx.globalCompositeOperation = "destination-out";
      maskCanvasCtx.beginPath();
      maskCanvasCtx.arc(x, y, raio, 0, Math.PI * 2);
      maskCanvasCtx.fill();
    } else {
      maskCanvasCtx.globalCompositeOperation = "source-over";
      maskCanvasCtx.fillStyle = "rgba(239, 68, 68, 0.55)";
      maskCanvasCtx.beginPath();
      maskCanvasCtx.arc(x, y, raio, 0, Math.PI * 2);
      maskCanvasCtx.fill();
      mascaraPossuiTinta = true;
    }
    maskCanvasCtx.restore();
  }

  maskCanvas.addEventListener("mousedown", iniciarDesenho);
  maskCanvas.addEventListener("mousemove", desenhar);
  maskCanvas.addEventListener("mouseenter", (e) => { if (modoInpaintAtivo) atualizarCursorPincel(e); });
  maskCanvas.addEventListener("mouseleave", () => {
    const cursor = $("inpaint-cursor-brush");
    if (cursor) cursor.style.display = "none";
  });
  window.addEventListener("mouseup", finalizarDesenho);

  maskCanvas.addEventListener("touchstart", iniciarDesenho, { passive: false });
  maskCanvas.addEventListener("touchmove", desenhar, { passive: false });
  window.addEventListener("touchend", finalizarDesenho);

  const btnPincel = $("btn-ferramenta-pincel");
  const btnBorracha = $("btn-ferramenta-borracha");
  if (btnPincel && btnBorracha) {
    btnPincel.addEventListener("click", () => {
      ferramentaInpaintAtual = "pincel";
      btnPincel.className = "btn btn-sm btn-primary";
      btnBorracha.className = "btn btn-sm btn-outline";
    });
    btnBorracha.addEventListener("click", () => {
      ferramentaInpaintAtual = "borracha";
      btnBorracha.className = "btn btn-sm btn-primary";
      btnPincel.className = "btn btn-sm btn-outline";
    });
  }

  const sliderTamanho = $("inpaint-tamanho-pincel");
  if (sliderTamanho) {
    sliderTamanho.addEventListener("input", () => {
      tamanhoPincel = parseInt(sliderTamanho.value, 10) || 35;
      const lbl = $("inpaint-tamanho-pincel-val");
      if (lbl) lbl.textContent = `${tamanhoPincel}px`;
    });
  }

  const btnDesfazer = $("btn-desfazer-mascara");
  if (btnDesfazer) {
    btnDesfazer.addEventListener("click", desfazerUltimoTracoInpaint);
  }

  const btnLimpar = $("btn-limpar-mascara");
  if (btnLimpar) {
    btnLimpar.addEventListener("click", () => {
      limparMascaraInpaint();
      toast("Pintura da máscara limpa.", "info");
    });
  }

  const btnFechar = $("btn-cancelar-inpaint");
  if (btnFechar) {
    btnFechar.addEventListener("click", desativarModoInpaint);
  }

  const btnModo = $("btn-modo-inpaint");
  if (btnModo) {
    btnModo.addEventListener("click", () => {
      if (modoInpaintAtivo) {
        desativarModoInpaint();
      } else {
        ativarModoInpaint();
      }
    });
  }

  const sliderDenoise = $("inpaint-slider-denoise");
  if (sliderDenoise) {
    sliderDenoise.addEventListener("input", () => {
      const lbl = $("inpaint-denoise-val");
      if (lbl) lbl.textContent = sliderDenoise.value;
    });
  }
}


function desfazerUltimoTracoInpaint() {
  const maskCanvas = $("inpaint-mask-canvas");
  if (!maskCanvas || !maskCanvasCtx || historicoPinturaInpaint.length === 0) {
    toast("Nenhum traço anterior para desfazer.", "info");
    return;
  }
  const estadoAnterior = historicoPinturaInpaint.pop();
  maskCanvasCtx.putImageData(estadoAnterior, 0, 0);
  mascaraPossuiTinta = historicoPinturaInpaint.length > 0;
  toast("Último traço desfeito (Ctrl+Z).", "info");
}

// Atalho de teclado global Ctrl+Z para inpainting
window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && modoInpaintAtivo) {
    e.preventDefault();
    desfazerUltimoTracoInpaint();
  }
});

// Presets rápidos de estilo adicionam termos ao prompt positivo
$$(".btn-preset-estilo").forEach(btn => {
  btn.addEventListener("click", () => {
    const estilo = btn.dataset.estilo;
    if (!estilo) return;
    const campo = $("img-prompt");
    if (!campo) return;
    const atual = campo.value.trim();
    if (!atual) {
      campo.value = estilo;
    } else if (!atual.toLowerCase().includes(estilo.toLowerCase().slice(0, 15))) {
      campo.value = `${atual}, ${estilo}`;
    }
    campo.focus();
    toast(`Estilo "${btn.textContent.trim()}" adicionado ao prompt!`, "success");
  });
});

// Comparador Antes/Depois (segurar para ver a original antes do inpainting)
const btnComparar = $("btn-comparar-original");
if (btnComparar) {
  function verOriginal(e) {
    if (!imagemBaseAntesInpaint) return;
    e.preventDefault();
    const preview = $("img-canvas-preview");
    if (preview) preview.src = imagemBaseAntesInpaint;
    $("img-meta-motor").textContent = "ORIGINAL (ANTES)";
  }

  function verInpaint(e) {
    if (!ultimaImagemGeradaUrl) return;
    e.preventDefault();
    const preview = $("img-canvas-preview");
    if (preview) preview.src = ultimaImagemGeradaUrl;
    $("img-meta-motor").textContent = "COMFYUI · INPAINT";
  }

  btnComparar.addEventListener("mousedown", verOriginal);
  btnComparar.addEventListener("mouseup", verInpaint);
  btnComparar.addEventListener("mouseleave", verInpaint);
  btnComparar.addEventListener("touchstart", verOriginal, { passive: false });
  btnComparar.addEventListener("touchend", verInpaint);
}

function sincronizarDimensoesCanvasInpaint() {
  const maskCanvas = $("inpaint-mask-canvas");
  const preview = $("img-canvas-preview");
  if (!maskCanvas || !preview) return;

  const w = preview.naturalWidth || preview.clientWidth || 1024;
  const h = preview.naturalHeight || preview.clientHeight || 1024;

  if (maskCanvas.width !== w || maskCanvas.height !== h) {
    maskCanvas.width = w;
    maskCanvas.height = h;
    limparMascaraInpaint();
  }
}

function limparMascaraInpaint() {
  const maskCanvas = $("inpaint-mask-canvas");
  if (!maskCanvas || !maskCanvasCtx) return;
  maskCanvasCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
  mascaraPossuiTinta = false;
}

function ativarModoInpaint() {
  if (!ultimaImagemGeradaUrl) {
    toast("Gere ou selecione uma imagem antes de ativar o Inpainting.", "warning");
    return;
  }
  modoInpaintAtivo = true;
  sincronizarDimensoesCanvasInpaint();

  const toolbar = $("inpaint-toolbar");
  const maskCanvas = $("inpaint-mask-canvas");
  const painel = $("inpaint-painel-controles");
  const btnModo = $("btn-modo-inpaint");
  const btnGerar = $("btn-gerar-imagem");

  if (toolbar) toolbar.style.display = "flex";
  if (maskCanvas) maskCanvas.style.display = "block";
  if (painel) painel.style.display = "block";
  if (btnModo) {
    btnModo.className = "btn btn-primary btn-sm";
    btnModo.textContent = "✕ Sair do Inpaint";
  }
  if (btnGerar) {
    btnGerar.classList.add("btn-inpaint-active");
    btnGerar.innerHTML = `<span> Regenerar Região (Inpaint)</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 14 4-4-4-4"/><path d="m2 10h20"/></svg>`;
  }
  atualizarDisponibilidadeModelosInpaint(true);
  toast("Modo Inpainting ativado! Pinte sobre a área que deseja regenerar e ajuste o prompt.", "info");
}

function desativarModoInpaint() {
  modoInpaintAtivo = false;
  const toolbar = $("inpaint-toolbar");
  const maskCanvas = $("inpaint-mask-canvas");
  const painel = $("inpaint-painel-controles");
  const btnModo = $("btn-modo-inpaint");
  const btnGerar = $("btn-gerar-imagem");

  if (toolbar) toolbar.style.display = "none";
  if (maskCanvas) maskCanvas.style.display = "none";
  if (painel) painel.style.display = "none";
  if (btnModo) {
    btnModo.className = "btn btn-outline btn-sm";
    btnModo.style.borderColor = "var(--brand-primary)";
    btnModo.style.color = "var(--brand-primary)";
    btnModo.textContent = " Inpainting";
  }
  if (btnGerar) {
    btnGerar.classList.remove("btn-inpaint-active");
    btnGerar.innerHTML = `<span>Gerar Imagem</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/><circle cx="9" cy="9" r="2"/></svg>`;
  }
  atualizarDisponibilidadeModelosInpaint(false);
}

function exportarMascaraPretoEBranco() {
  const maskCanvas = $("inpaint-mask-canvas");
  if (!maskCanvas || !maskCanvasCtx) return null;

  const off = document.createElement("canvas");
  off.width = maskCanvas.width;
  off.height = maskCanvas.height;
  const offCtx = off.getContext("2d");

  // Fundo preto puro (0,0,0) = preservar área original
  offCtx.fillStyle = "#000000";
  offCtx.fillRect(0, 0, off.width, off.height);

  const srcData = maskCanvasCtx.getImageData(0, 0, maskCanvas.width, maskCanvas.height);
  const src = srcData.data;
  const outData = offCtx.createImageData(off.width, off.height);
  const out = outData.data;

  let temPixelsPintados = false;
  for (let i = 0; i < src.length; i += 4) {
    if (src[i + 3] > 10) {
      out[i] = 255;     // R
      out[i + 1] = 255; // G
      out[i + 2] = 255; // B
      out[i + 3] = 255; // A
      temPixelsPintados = true;
    } else {
      out[i] = 0;
      out[i + 1] = 0;
      out[i + 2] = 0;
      out[i + 3] = 255;
    }
  }

  if (!temPixelsPintados) return null;
  offCtx.putImageData(outData, 0, 0);
  return off.toDataURL("image/png");
}

const btnGerarImagem = $("btn-gerar-imagem");
if (btnGerarImagem) {
  btnGerarImagem.addEventListener("click", async () => {
    const prompt = $("img-prompt").value.trim();
    if (!prompt) {
      toast("Informe um prompt para gerar a imagem.", "warning");
      $("img-prompt").focus();
      return;
    }

    const promptNegativo = $("img-prompt-negativo").value.trim();
    const motor = $("img-select-motor").value;
    const modelo = $("img-select-modelo") ? $("img-select-modelo").value : "flux";
    const steps = parseInt($("img-steps").value, 10) || 25;
    const seedStr = $("img-seed").value.trim();
    const seed = seedStr ? parseInt(seedStr, 10) : null;
    const placeholder = $("img-canvas-placeholder");
    const preview = $("img-canvas-preview");
    const metaStrip = $("img-meta-strip");

    // Fluxo especial de Inpainting quando ativado
    if (modoInpaintAtivo) {
      const maskB64 = exportarMascaraPretoEBranco();
      if (!maskB64) {
        toast("Pinte com o pincel a área da imagem que deseja regenerar!", "warning");
        return;
      }

      iniciarProgressoGeracao("Regenerando Região (Inpaint)...", "Preparando máscara e traduzindo prompt para o SDXL...");
      btnGerarImagem.innerHTML = `<span>Regenerando Região (Inpaint)...</span><span style="animation:spin 1s linear infinite;">⏳</span>`;

      try {
        const denoise = parseFloat($("inpaint-slider-denoise").value) || 0.75;
        const res = await api("POST", "/api/estudio/inpaint", {
          imagem_base: ultimaImagemGeradaUrl,
          mascara_base64: maskB64,
          prompt,
          prompt_negativo: promptNegativo,
          denoise,
          steps,
          seed
        });

        if (res.ok && res.imagem_url) {
          imagemBaseAntesInpaint = ultimaImagemGeradaUrl;
          const btnComp = $("btn-comparar-original");
          if (btnComp) btnComp.style.display = "inline-block";
          ultimaImagemGeradaUrl = res.imagem_url;
          preview.src = res.imagem_url;
          metaStrip.style.display = "flex";
          $("img-meta-dim").textContent = `${res.largura}x${res.altura} (Inpaint)`;
          $("img-meta-latencia").textContent = ` ${res.latencia_ms}ms`;
          $("img-meta-motor").textContent = "COMFYUI · INPAINT";

          galeriaImagensSessao.unshift({ url: res.imagem_url, prompt: `[Inpaint] ${prompt}`, res: `${res.largura}x${res.altura}` });
          renderizarGaleriaImagens();
          limparMascaraInpaint();
          desativarModoInpaint();
          exibirAvisoPromptOtimizado(res);
          finalizarProgressoGeracao(true);
          toast("Região regenerada com sucesso com Inpainting!", "success");
        }
      } catch (e) {
        if (e.extras && e.extras.servico_offline === "comfyui") {
          toast("ComfyUI está offline (:8188). Inicie o ComfyUI para usar Inpainting.", "warning");
        } else {
          toast(`Falha no Inpainting: ${e.message}`, "error");
        }
      } finally {
        finalizarProgressoGeracao(true);
        if (modoInpaintAtivo) {
          btnGerarImagem.innerHTML = `<span> Regenerar Região (Inpaint)</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 14 4-4-4-4"/><path d="m2 10h20"/></svg>`;
        } else {
          btnGerarImagem.innerHTML = `<span>Gerar Imagem</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/><circle cx="9" cy="9" r="2"/></svg>`;
        }
      }
      return;
    }

    iniciarProgressoGeracao("Gerando Imagem com IA...", "Otimizando prompt e conectando ao motor de inferência...");
    btnGerarImagem.innerHTML = `<span>Gerando Imagem...</span><span style="animation:spin 1s linear infinite;">⏳</span>`;

    try {
      const res = await api("POST", "/api/estudio/gerar-imagem", {
        prompt,
        prompt_negativo: promptNegativo,
        motor,
        modelo,
        aspect_ratio: aspectRatioSelecionado,
        steps,
        seed
      });

      if (res.ok && res.imagem_url) {
        ultimaImagemGeradaUrl = res.imagem_url;
        preview.src = res.imagem_url;
        preview.style.display = "block";
        placeholder.style.display = "none";

        metaStrip.style.display = "flex";
        $("img-meta-dim").textContent = `${res.largura}x${res.altura} (${aspectRatioSelecionado})`;
        $("img-meta-latencia").textContent = ` ${res.latencia_ms}ms`;
        $("img-meta-motor").textContent = `${res.motor.toUpperCase()} · ${(res.modelo || modelo).toUpperCase()}`;

        $("btn-baixar-imagem").disabled = false;
        $("btn-copiar-link-imagem").disabled = false;
        const btnExcluir = $("btn-excluir-imagem");
        if (btnExcluir) btnExcluir.disabled = false;

        galeriaImagensSessao.unshift({ url: res.imagem_url, prompt, res: `${res.largura}x${res.altura}` });
        renderizarGaleriaImagens();
        exibirAvisoPromptOtimizado(res);
        finalizarProgressoGeracao(true);

        if (res.aviso) toast(res.aviso, "warning");
        else toast(`Imagem gerada com sucesso (${res.modelo || res.motor})!`, "success");
      }
    } catch (e) {
      if (e.extras && e.extras.servico_offline === "comfyui") {
          placeholder.style.display = "flex";
          preview.style.display = "none";
          placeholder.replaceChildren(
            el("div", { style: "color:var(--warning); font-size:15px; font-weight:600; margin-bottom:6px;" }, ["⚠ ComfyUI está Offline (:8188)"]),
            el("div", { style: "color:var(--text-secondary); font-size:12px; margin-bottom:14px; max-width:380px; text-align:center;" }, ["O motor ComfyUI portátil na GPU não está em execução no host."]),
            el("div", { style: "display:flex; gap:8px;" }, [
              el("button", {
                className: "btn btn-primary btn-sm",
                textContent: "▶ Iniciar ComfyUI Agora",
                onclick: async () => {
                  try {
                    toast("Iniciando ComfyUI portátil...", "info");
                    await api("POST", "/api/servicos/comfyui/start", {});
                    toast("ComfyUI subindo! Aguarde alguns segundos para carregar na GPU.", "success");
                    await carregarImagens();
                  } catch (e) {
                    toast(`Falha ao iniciar: ${e.message}`, "error");
                  }
                }
              }),
              el("button", {
                className: "btn btn-outline btn-sm",
                textContent: "Usar Modo Nuvem",
                onclick: () => {
                  $("img-select-motor").value = "nuvem";
                  btnGerarImagem.click();
                }
              })
            ])
          );
          toast("ComfyUI está offline. Inicie o serviço ou use Modo Nuvem.", "warning");
      } else {
        toast(`Falha ao gerar imagem: ${e.message}`, "error");
      }
    } finally {
      finalizarProgressoGeracao(true);
      btnGerarImagem.innerHTML = `<span>Gerar Imagem</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/><circle cx="9" cy="9" r="2"/></svg>`;
    }
  });
}

function renderizarGaleriaImagens() {
  const container = $("img-galeria-thumbs");
  if (!container) return;
  container.replaceChildren();

  if (galeriaImagensSessao.length === 0) {
    container.appendChild(el("span", {
      style: "font-size:11px; color:var(--text-dim); font-style:italic;"
    }, ["Nenhuma imagem salva no disco."]));
    return;
  }

  galeriaImagensSessao.slice(0, 16).forEach(item => {
    const isAtiva = ultimaImagemGeradaUrl === item.url;
    const thumb = el("div", {
      className: `galeria-thumb-item${isAtiva ? " active" : ""}`,
      title: `${item.prompt} (Clique para ver / ✕ para excluir)`,
      onclick: () => {
        selecionarImagemCanvas(item.url, item.prompt);
      }
    }, [
      el("img", { src: item.url, alt: item.prompt }),
      el("button", {
        className: "galeria-thumb-del",
        title: "Excluir imagem do disco",
        onclick: (e) => {
          e.stopPropagation();
          excluirImagemPorUrl(item.url);
        }
      }, ["✕"])
    ]);
    container.appendChild(thumb);
  });
}

const btnBaixarImagem = $("btn-baixar-imagem");
if (btnBaixarImagem) {
  btnBaixarImagem.addEventListener("click", () => {
    if (!ultimaImagemGeradaUrl) return;
    const a = document.createElement("a");
    a.href = ultimaImagemGeradaUrl;
    a.download = `tudoia-imagem-${Date.now()}.jpg`;
    a.target = "_blank";
    a.click();
    toast("Download iniciado!", "info");
  });
}

const btnCopiarLinkImagem = $("btn-copiar-link-imagem");
if (btnCopiarLinkImagem) {
  btnCopiarLinkImagem.addEventListener("click", () => {
    if (!ultimaImagemGeradaUrl) return;
    const urlAbsoluta = new URL(ultimaImagemGeradaUrl, window.location.origin).href;
    navigator.clipboard.writeText(urlAbsoluta).then(() => {
      toast("Link completo copiado para a área de transferência!", "success");
    }).catch(() => {
      // Fallback se permissão do clipboard falhar
      prompt("Copie o link abaixo:", urlAbsoluta);
    });
  });
}

const btnExcluirImagem = $("btn-excluir-imagem");
if (btnExcluirImagem) {
  btnExcluirImagem.addEventListener("click", () => {
    if (!ultimaImagemGeradaUrl) return;
    excluirImagemPorUrl(ultimaImagemGeradaUrl);
  });
}


// 3. GERADOR DE VÍDEOS
let galeriaVideosSessao = [];
let ultimoVideoGeradoUrl = null;

async function carregarVideos() {
  const badge = $("badge-status-comfy-video");
  try {
    const st = await api("GET", "/api/estudio/status-motores");
    if (st.comfyui) {
      if (badge) {
        badge.textContent = "ComfyUI :8188 online (GPU)";
        badge.className = "badge badge-free";
      }
    } else {
      if (badge) {
        badge.textContent = "ComfyUI :8188 OFFLINE";
        badge.className = "badge badge-role";
      }
    }
  } catch (e) {
    if (badge) {
      badge.textContent = "ComfyUI :8188 INDISPONÍVEL";
      badge.className = "badge badge-role";
    }
  }
  await carregarCatalogoModelos();

  // Carrega vídeos salvos do disco
  try {
    const resVids = await api("GET", "/api/estudio/videos");
    if (resVids.ok && Array.isArray(resVids.videos)) {
      galeriaVideosSessao = resVids.videos.map(v => ({
        url: v.url,
        nome: v.nome,
        tamanho: v.tamanho ? `${Math.round(v.tamanho / (1024 * 1024))} MB` : ""
      }));
      renderizarGaleriaVideos();

      // Recupera job de renderização de vídeo ativo se houver
      try {
        const rawJob = localStorage.getItem("tudoia_active_video_job");
        if (rawJob) {
          const savedJob = JSON.parse(rawJob);
          if (savedJob && savedJob.jobId) {
            toast("Retomando monitoramento de renderização ativa no ComfyUI...", "info");
            iniciarMonitoramentoJobVideo(savedJob.jobId, savedJob);
          }
        }
      } catch (e) {}

      if (!ultimoVideoGeradoUrl && galeriaVideosSessao.length > 0) {
        selecionarVideoPlayer(galeriaVideosSessao[0].url, galeriaVideosSessao[0].nome);
      }
    }
  } catch (e) {
    console.warn("Falha ao carregar vídeos do disco:", e);
  }
}

function selecionarVideoPlayer(url, titulo = "") {
  ultimoVideoGeradoUrl = url;
  const player = $("vid-player-preview");
  const placeholder = $("vid-canvas-placeholder");
  const metaStrip = $("vid-meta-strip");

  player.src = url;
  player.style.display = "block";
  placeholder.style.display = "none";
  player.play().catch(() => {});

  $("btn-baixar-video").disabled = false;
  const btnCopiar = $("btn-copiar-link-video");
  if (btnCopiar) btnCopiar.disabled = false;
  const btnExcluir = $("btn-excluir-video");
  if (btnExcluir) btnExcluir.disabled = false;

  metaStrip.style.display = "flex";
  $("vid-meta-job").textContent = `CLIPE: ${url.split("/").pop()}`;
  $("vid-meta-status").textContent = "Disco local";
  $("vid-meta-latencia").textContent = "Pronto";

  renderizarGaleriaVideos();
}

function limparPlayerVideo() {
  ultimoVideoGeradoUrl = null;
  const player = $("vid-player-preview");
  const placeholder = $("vid-canvas-placeholder");
  const metaStrip = $("vid-meta-strip");

  player.pause();
  player.src = "";
  player.style.display = "none";
  placeholder.style.display = "flex";
  metaStrip.style.display = "none";

  $("btn-baixar-video").disabled = true;
  const btnCopiar = $("btn-copiar-link-video");
  if (btnCopiar) btnCopiar.disabled = true;
  const btnExcluir = $("btn-excluir-video");
  if (btnExcluir) btnExcluir.disabled = true;
}

async function excluirVideoPorUrl(url) {
  if (!url) return;
  const nomeArquivo = url.split("/").pop();
  if (!confirm(`Deseja excluir permanentemente o vídeo "${nomeArquivo}" do disco?`)) return;

  try {
    const res = await api("DELETE", `/api/estudio/videos/${encodeURIComponent(nomeArquivo)}`);
    if (res.ok) {
      toast(`Vídeo "${nomeArquivo}" excluído do disco.`, "success");
      galeriaVideosSessao = galeriaVideosSessao.filter(item => item.url !== url);

      if (ultimoVideoGeradoUrl === url) {
        if (galeriaVideosSessao.length > 0) {
          selecionarVideoPlayer(galeriaVideosSessao[0].url, galeriaVideosSessao[0].nome);
        } else {
          limparPlayerVideo();
        }
      }
      renderizarGaleriaVideos();
    } else {
      toast(`Falha ao excluir vídeo: ${res.erro || "Erro no servidor"}`, "error");
    }
  } catch (e) {
    toast(`Erro ao excluir vídeo: ${e.message}`, "error");
  }
}

function renderizarGaleriaVideos() {
  const container = $("vid-galeria-thumbs");
  if (!container) return;
  container.replaceChildren();

  if (galeriaVideosSessao.length === 0) {
    container.appendChild(el("span", {
      style: "font-size:11px; color:var(--text-dim); font-style:italic; padding:6px 0;"
    }, ["Nenhum clipe renderizado nesta sessão."]));
    return;
  }

  galeriaVideosSessao.slice(0, 12).forEach(item => {
    const isAtivo = ultimoVideoGeradoUrl === item.url;
    const thumb = el("div", {
      className: `vid-reel-card${isAtivo ? " active" : ""}`,
      title: `${item.nome} (Clique para assistir no cinema player)`,
      onclick: () => {
        selecionarVideoPlayer(item.url, item.nome);
      }
    }, [
      el("div", { style: "display:flex; justify-content:space-between; align-items:center; width:100%;" }, [
        el("span", { style: "font-size:10px; font-weight:600; color:var(--brand-primary); display:flex; align-items:center; gap:3px;" }, [
          "",
          el("span", { style: "font-size:9px; color:var(--text-muted);" }, [item.tamanho || "MP4"])
        ]),
        el("button", {
          className: "galeria-thumb-del",
          title: "Excluir clipe",
          style: "position:static; width:16px; height:16px; font-size:9px;",
          onclick: (e) => {
            e.stopPropagation();
            excluirVideoPorUrl(item.url);
          }
        }, ["✕"])
      ]),
      el("div", { style: "text-align:center; padding:4px 0;" }, [
        el("div", { style: "width:22px; height:22px; margin:0 auto; border-radius:50%; background:rgba(99,102,241,0.15); display:flex; align-items:center; justify-content:center; color:var(--brand-primary); font-size:10px;" }, ["▶"])
      ]),
      el("div", {
        style: "font-family:var(--font-mono); font-size:9px; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:center;"
      }, [item.nome.replace("vid_", "").replace(".mp4", "")])
    ]);
    container.appendChild(thumb);
  });
}

const btnBaixarVideo = $("btn-baixar-video");
if (btnBaixarVideo) {
  btnBaixarVideo.addEventListener("click", () => {
    if (!ultimoVideoGeradoUrl) return;
    const a = document.createElement("a");
    a.href = ultimoVideoGeradoUrl;
    a.download = `tudoia-video-${Date.now()}.mp4`;
    a.target = "_blank";
    a.click();
    toast("Download do vídeo iniciado!", "info");
  });
}

const btnCopiarLinkVideo = $("btn-copiar-link-video");
if (btnCopiarLinkVideo) {
  btnCopiarLinkVideo.addEventListener("click", () => {
    if (!ultimoVideoGeradoUrl) return;
    const urlAbsoluta = new URL(ultimoVideoGeradoUrl, window.location.origin).href;
    navigator.clipboard.writeText(urlAbsoluta).then(() => {
      toast("Link completo do vídeo copiado!", "success");
    }).catch(() => {
      prompt("Copie o link abaixo:", urlAbsoluta);
    });
  });
}

const btnExcluirVideo = $("btn-excluir-video");
if (btnExcluirVideo) {
  btnExcluirVideo.addEventListener("click", () => {
    if (!ultimoVideoGeradoUrl) return;
    excluirVideoPorUrl(ultimoVideoGeradoUrl);
  });
}

// ------------------------------------------------ CONTROLES DE MÍDIA DE ENTRADA (I2V / V2V)
let modoVideoAtual = "t2v";
let midiaReferenciaCarregada = null; // { url, caminho, nome, tipo }

function setModoVideo(modo) {
  modoVideoAtual = modo;
  const botoes = document.querySelectorAll(".vid-modo-btn");
  botoes.forEach(b => {
    b.classList.toggle("active", b.getAttribute("data-modo") === modo);
  });

  const painelArquivo = $("vid-painel-arquivo");
  const badgeModo = $("vid-badge-modo");
  if (modo === "t2v") {
    if (painelArquivo) painelArquivo.style.display = "none";
    if (badgeModo) {
      badgeModo.textContent = "T2V · Texto Puro";
      badgeModo.style.color = "var(--brand-primary)";
    }
  } else if (modo === "i2v") {
    if (painelArquivo) painelArquivo.style.display = "block";
    if (badgeModo) {
      badgeModo.textContent = "I2V · Imagem para Vídeo";
      badgeModo.style.color = "var(--warning)";
    }
  } else if (modo === "v2v") {
    if (painelArquivo) painelArquivo.style.display = "block";
    if (badgeModo) {
      badgeModo.textContent = "V2V · Vídeo para Vídeo";
      badgeModo.style.color = "var(--success)";
    }
  }
}

function atualizarModoVideoPorModelo() {
  const selectVid = $("vid-select-modelo");
  if (!selectVid) return;
  const modId = selectVid.value;
  const info = mapaModelosVideo[modId] || {};
  const idLower = (modId || "").toLowerCase();
  if (info.modo_entrada === "i2v" || idLower.includes("i2v") || idLower.includes("image_to_video") || idLower.includes("image-to-video")) {
    setModoVideo("i2v");
  } else if (info.modo_entrada === "v2v" || idLower.includes("v2v") || idLower.includes("video_to_video") || idLower.includes("video-to-video")) {
    setModoVideo("v2v");
  } else if (info.modo_entrada === "ti2v" || idLower.includes("ti2v")) {
    if (midiaReferenciaCarregada) {
      setModoVideo(midiaReferenciaCarregada.tipo === "video" ? "v2v" : "i2v");
    }
  } else {
    if (!midiaReferenciaCarregada) {
      setModoVideo("t2v");
    }
  }
}

function exibirPreviewMidia(urlOuCaminho, nome, tipo) {
  const box = $("vid-midia-preview-box");
  const imgPrev = $("vid-preview-img");
  const vidPrev = $("vid-preview-vid");
  const nomePrev = $("vid-preview-nome");
  const statusPrev = $("vid-preview-status");

  if (!box) return;
  box.style.display = "flex";
  if (nomePrev) nomePrev.textContent = nome || urlOuCaminho.split(/[\\/]/).pop();
  if (statusPrev) statusPrev.textContent = "✓ Mídia pronta para renderização";

  if (tipo === "video") {
    if (imgPrev) imgPrev.style.display = "none";
    if (vidPrev) {
      vidPrev.style.display = "block";
      if (urlOuCaminho && (urlOuCaminho.startsWith("http") || urlOuCaminho.startsWith("/api/"))) {
        vidPrev.src = urlOuCaminho;
      }
    }
  } else {
    if (vidPrev) vidPrev.style.display = "none";
    if (imgPrev) {
      imgPrev.style.display = "block";
      if (urlOuCaminho && (urlOuCaminho.startsWith("http") || urlOuCaminho.startsWith("/api/") || urlOuCaminho.startsWith("data:"))) {
        imgPrev.src = urlOuCaminho;
      }
    }
  }
}

function limparMidiaReferencia() {
  midiaReferenciaCarregada = null;
  const inputCaminho = $("vid-input-caminho");
  const fileInput = $("vid-file-input");
  const box = $("vid-midia-preview-box");
  const imgPrev = $("vid-preview-img");
  const vidPrev = $("vid-preview-vid");

  if (inputCaminho) inputCaminho.value = "";
  if (fileInput) fileInput.value = "";
  if (box) box.style.display = "none";
  if (imgPrev) { imgPrev.src = ""; imgPrev.style.display = "none"; }
  if (vidPrev) { vidPrev.src = ""; vidPrev.style.display = "none"; }
}

async function uploadArquivoMidia(file) {
  if (!file) return;
  const isVideo = file.type.startsWith("video/") || /\.(mp4|webm|mov|avi|mkv)$/i.test(file.name);
  const tipo = isVideo ? "video" : "imagem";

  toast(`Enviando ${file.name}...`, "info");
  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const res = await api("POST", "/api/estudio/upload", {
        nome_arquivo: file.name,
        conteudo_base64: e.target.result,
        tipo
      });
      if (res.ok) {
        midiaReferenciaCarregada = {
          url: res.url,
          caminho: res.caminho_local,
          nome: res.nome_arquivo,
          tipo: res.tipo
        };
        const inputCaminho = $("vid-input-caminho");
        if (inputCaminho) inputCaminho.value = res.caminho_local;
        exibirPreviewMidia(res.url, res.nome_arquivo, res.tipo);
        toast(`✓ Upload de ${file.name} concluído com sucesso!`, "success");
      }
    } catch (err) {
      toast(`Falha no upload: ${err.message}`, "error");
    }
  };
  reader.readAsDataURL(file);
}

function inicializarControlesMidiaVideo() {
  const tabs = document.querySelectorAll(".vid-modo-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      const modo = btn.getAttribute("data-modo");
      setModoVideo(modo);
    });
  });

  const dropzone = $("vid-dropzone");
  const fileInput = $("vid-file-input");
  if (dropzone && fileInput) {
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.style.borderColor = "var(--brand-primary)";
      dropzone.style.background = "rgba(99,102,241,0.05)";
    });
    dropzone.addEventListener("dragleave", () => {
      dropzone.style.borderColor = "var(--border-focus)";
      dropzone.style.background = "rgba(255,255,255,0.01)";
    });
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.style.borderColor = "var(--border-focus)";
      dropzone.style.background = "rgba(255,255,255,0.01)";
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        uploadArquivoMidia(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener("change", () => {
      if (fileInput.files && fileInput.files.length > 0) {
        uploadArquivoMidia(fileInput.files[0]);
      }
    });
  }

  const inputCaminho = $("vid-input-caminho");
  if (inputCaminho) {
    inputCaminho.addEventListener("input", () => {
      const val = inputCaminho.value.trim();
      if (val) {
        const isVid = /\.(mp4|webm|mov|avi|mkv)$/i.test(val);
        const tipo = isVid ? "video" : "imagem";
        midiaReferenciaCarregada = {
          url: (val.startsWith("http") || val.startsWith("/api/")) ? val : "",
          caminho: val,
          nome: val.split(/[\\/]/).pop(),
          tipo
        };
        exibirPreviewMidia(val, val.split(/[\\/]/).pop(), tipo);
      } else {
        limparMidiaReferencia();
      }
    });
  }

  const btnRemoverMidia = $("btn-remover-midia-vid");
  if (btnRemoverMidia) {
    btnRemoverMidia.addEventListener("click", () => {
      limparMidiaReferencia();
      toast("Mídia de referência removida.", "info");
    });
  }

  const selectVid = $("vid-select-modelo");
  if (selectVid) {
    selectVid.addEventListener("change", () => {
      atualizarModoVideoPorModelo();
    });
  }
}

inicializarControlesMidiaVideo();

// Controles de Prompt e Tradução Inteligente de Vídeo
function inicializarControlesPromptVideo() {
  const vidPrompt = $("vid-prompt");
  const dicaPt = $("vid-prompt-dica-pt");
  const cardTraducao = $("vid-prompt-aviso-traducao");
  const textoTraducao = $("vid-prompt-aviso-texto");
  const tituloTraducao = $("vid-prompt-aviso-titulo");
  const btnOtimizar = $("btn-otimizar-prompt-video-manual");

  if (vidPrompt && dicaPt) {
    vidPrompt.addEventListener("input", () => {
      const val = vidPrompt.value.trim();
      dicaPt.style.display = (val && detectarTextoPortugues(val)) ? "block" : "none";
    });
  }

  if (btnOtimizar && vidPrompt) {
    btnOtimizar.addEventListener("click", async () => {
      const val = vidPrompt.value.trim();
      if (!val) {
        toast("Digite uma cena ou movimento antes de enriquecer com IA.", "warning");
        vidPrompt.focus();
        return;
      }
      btnOtimizar.disabled = true;
      btnOtimizar.textContent = " Enriquecendo...";
      try {
        const res = await api("POST", "/api/estudio/otimizar-prompt-video", { prompt: val });
        if (res.ok && res.prompt) {
          if (textoTraducao) textoTraducao.textContent = `"${res.prompt}"`;
          if (tituloTraducao) tituloTraducao.textContent = res.prompt_otimizado ? "Direção Cinematográfica Enriquecida com IA" : "Prompt em Inglês Mantido";
          if (cardTraducao) cardTraducao.style.display = "block";
          toast("✓ Prompt enriquecido cinematograficamente!", "success");
        }
      } catch (e) {
        toast(`Erro ao melhorar prompt: ${e.message}`, "error");
      } finally {
        btnOtimizar.disabled = false;
        btnOtimizar.textContent = " Melhorar com IA";
      }
    });
  }

  const btnFecharAviso = $("btn-fechar-aviso-traducao-video");
  if (btnFecharAviso && cardTraducao) {
    btnFecharAviso.addEventListener("click", () => {
      cardTraducao.style.display = "none";
    });
  }

  const btnAplicar = $("btn-aplicar-prompt-traduzido-video");
  if (btnAplicar && vidPrompt && textoTraducao) {
    btnAplicar.addEventListener("click", () => {
      let t = textoTraducao.textContent.trim();
      if (t.startsWith('"') && t.endsWith('"')) t = t.slice(1, -1);
      vidPrompt.value = t;
      if (cardTraducao) cardTraducao.style.display = "none";
      if (dicaPt) dicaPt.style.display = "none";
      toast("Prompt cinematográfico aplicado ao campo de texto!", "info");
      vidPrompt.focus();
    });
  }

  const btnCopiar = $("btn-copiar-prompt-traduzido-video");
  if (btnCopiar && textoTraducao) {
    btnCopiar.addEventListener("click", () => {
      let t = textoTraducao.textContent.trim();
      if (t.startsWith('"') && t.endsWith('"')) t = t.slice(1, -1);
      navigator.clipboard.writeText(t).then(() => toast("Copiado para a área de transferência!", "success"));
    });
  }

  // Presets Rápidos de Câmera
  document.querySelectorAll(".btn-preset-vid").forEach(btn => {
    btn.addEventListener("click", () => {
      const estilo = btn.getAttribute("data-estilo");
      if (!vidPrompt || !estilo) return;
      const atual = vidPrompt.value.trim();
      vidPrompt.value = atual ? `${atual}, ${estilo}` : estilo;
      toast(`Adicionado: ${btn.textContent}`, "info");
      vidPrompt.focus();
    });
  });
}

inicializarControlesPromptVideo();

// Gerenciador Assíncrono da Barra de Progresso Real de Vídeo (ComfyUI)
let timerProgressoVideoInterval = null;
let monitoramentoJobVideoInterval = null;
let tempoInicioVideo = 0;

function iniciarProgressoVideo(duracaoEstimada = 25, modelo = "") {
  const container = $("vid-progresso-container");
  const barra = $("vid-progresso-barra");
  const timerTxt = $("vid-progresso-timer");
  const faseTxt = $("vid-progresso-fase-txt");
  const detalheTxt = $("vid-progresso-detalhe");
  const btnGerar = $("btn-gerar-video");

  if (!container || !barra) return;

  container.style.display = "flex";
  barra.style.width = "4%";
  tempoInicioVideo = Date.now();

  const ehMinimax = (modelo || "").toLowerCase().includes("minimax");
  if (faseTxt) {
    faseTxt.textContent = ehMinimax
      ? "Sintetizando Vídeo Cinemático & Áudio Estéreo (MiniMax H3 Turbo)..."
      : "Renderizando Vídeo na GPU...";
  }
  if (detalheTxt) {
    detalheTxt.textContent = ehMinimax
      ? "Amostragem KSampler 8-step + Decodificação Neural Dupla (Vídeo VAE + Áudio 32-bit VAE)"
      : "Arbitrando recursos da GPU para difusão acelerada";
  }

  if (btnGerar) {
    btnGerar.disabled = true;
    btnGerar.innerHTML = `<span>Renderizando na GPU...</span><span style="animation:spin 1s linear infinite;">⏳</span>`;
  }

  if (timerProgressoVideoInterval) clearInterval(timerProgressoVideoInterval);

  timerProgressoVideoInterval = setInterval(() => {
    const elapsedSeg = (Date.now() - tempoInicioVideo) / 1000;
    if (timerTxt) timerTxt.textContent = `${elapsedSeg.toFixed(1)}s`;

    // Progresso assintótico suave que nunca some enquanto estiver gerando
    const pct = Math.min(94, 5 + Math.atan(elapsedSeg / 35) * (89 / (Math.PI / 2)));
    barra.style.width = `${pct.toFixed(0)}%`;
  }, 300);
}

function pararProgressoVideo(sucesso = true, msg = "") {
  if (timerProgressoVideoInterval) {
    clearInterval(timerProgressoVideoInterval);
    timerProgressoVideoInterval = null;
  }
  if (monitoramentoJobVideoInterval) {
    clearInterval(monitoramentoJobVideoInterval);
    monitoramentoJobVideoInterval = null;
  }
  localStorage.removeItem("tudoia_active_video_job");

  const barra = $("vid-progresso-barra");
  const container = $("vid-progresso-container");
  const faseTxt = $("vid-progresso-fase-txt");
  const btnGerar = $("btn-gerar-video");

  if (barra) barra.style.width = sucesso ? "100%" : "0%";
  if (faseTxt) faseTxt.textContent = msg || (sucesso ? "✓ Vídeo cinematográfico renderizado com sucesso!" : "Inferência interrompida.");

  setTimeout(() => {
    if (container) container.style.display = "none";
    if (barra) barra.style.width = "0%";
  }, 1200);

  if (btnGerar) {
    btnGerar.disabled = false;
    btnGerar.innerHTML = `<span>Renderizar Vídeo Cinematográfico</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
  }
}

function iniciarMonitoramentoJobVideo(jobId, meta = {}) {
  if (!jobId) return;

  localStorage.setItem("tudoia_active_video_job", JSON.stringify({
    jobId,
    modelo: meta.modelo || "video-minimax-h3",
    duracao: meta.duracao || 5,
    resolucao: meta.resolucao || "720p",
    inicio: meta.inicio || Date.now()
  }));

  tempoInicioVideo = meta.inicio || Date.now();
  iniciarProgressoVideo(meta.duracao || 5, meta.modelo || "");

  if (monitoramentoJobVideoInterval) clearInterval(monitoramentoJobVideoInterval);

  monitoramentoJobVideoInterval = setInterval(async () => {
    try {
      const statusRes = await api("GET", `/api/estudio/status-video/${jobId}`);
      if (!statusRes) return;

      if (statusRes.ok && statusRes.status === "concluido") {
        pararProgressoVideo(true, "✓ Renderização concluída! Carregando player...");
        const videoUrl = statusRes.video_url;
        const nomeArq = statusRes.nome_arquivo || videoUrl.split("/").pop();

        selecionarVideoPlayer(videoUrl, nomeArq);
        galeriaVideosSessao = galeriaVideosSessao.filter(v => v.nome !== nomeArq);
        galeriaVideosSessao.unshift({
          url: videoUrl,
          nome: nomeArq,
          tamanho: `${statusRes.latencia_ms ? Math.round(statusRes.latencia_ms / 1000) + 's' : 'MP4'}`
        });
        renderizarGaleriaVideos();

        const metaStrip = $("vid-meta-strip");
        if (metaStrip) {
          metaStrip.style.display = "flex";
          if ($("vid-meta-job")) $("vid-meta-job").textContent = `CLIPE: ${nomeArq} (Áudio & Vídeo Nativo)`;
          if ($("vid-meta-status")) $("vid-meta-status").textContent = "Pronto (ComfyUI)";
          if ($("vid-meta-latencia")) $("vid-meta-latencia").textContent = ` ${statusRes.latencia_ms || 0}ms`;
        }

        toast("✓ Vídeo cinematográfico com áudio renderizado e pronto no player!", "success");
      } else if (statusRes.status === "erro") {
        pararProgressoVideo(false, `Falha: ${statusRes.erro || "Erro no ComfyUI"}`);
        toast(`Erro na renderização: ${statusRes.erro || "Falha desconhecida"}`, "error");
      } else if (statusRes.status === "executando" && statusRes.fase) {
        const faseTxt = $("vid-progresso-fase-txt");
        if (faseTxt) faseTxt.textContent = statusRes.fase;
      }
    } catch (err) {
      console.warn("Polling de status do vídeo:", err);
    }
  }, 1800);
}

// Botão Cancelar Geração de Vídeo
const btnCancelarVideo = $("btn-cancelar-video");
if (btnCancelarVideo) {
  btnCancelarVideo.addEventListener("click", async () => {
    try {
      toast("Solicitando cancelamento imediato ao ComfyUI...", "warning");
      btnCancelarVideo.disabled = true;
      const res = await api("POST", "/api/estudio/cancelar", {});
      if (res.ok) {
        toast("Inferência interrompida no ComfyUI!", "info");
      }
    } catch (e) {
      toast(`Falha ao cancelar: ${e.message}`, "error");
    } finally {
      btnCancelarVideo.disabled = false;
      pararProgressoVideo(false, "Inferência cancelada pelo usuário.");
    }
  });
}

const btnGerarVideo = $("btn-gerar-video");
if (btnGerarVideo) {
  btnGerarVideo.addEventListener("click", async () => {
    const prompt = $("vid-prompt").value.trim();
    if (!prompt) {
      toast("Informe um prompt para renderizar o vídeo.", "warning");
      $("vid-prompt").focus();
      return;
    }

    const modo = modoVideoAtual;
    const inputCaminhoVal = $("vid-input-caminho") ? $("vid-input-caminho").value.trim() : "";
    const arquivoRef = (midiaReferenciaCarregada && (midiaReferenciaCarregada.caminho || midiaReferenciaCarregada.url)) || inputCaminhoVal || null;

    if ((modo === "i2v" || modo === "v2v") && !arquivoRef) {
      toast(`O fluxo ${modo.toUpperCase()} requer uma ${modo === "i2v" ? "imagem" : "vídeo"} de referência. Faça upload ou informe o caminho.`, "warning");
      const painelArq = $("vid-painel-arquivo");
      if (painelArq) painelArq.style.display = "block";
      const inputCam = $("vid-input-caminho");
      if (inputCam) inputCam.focus();
      return;
    }

    const motor = $("vid-select-motor") ? $("vid-select-motor").value : "comfyui";
    const modelo = $("vid-select-modelo") ? $("vid-select-modelo").value : "video-minimax-h3";
    const duracao = parseInt($("vid-select-duracao").value, 10) || 5;
    const resolucao = $("vid-select-resolucao").value;
    const fps = parseInt($("vid-select-fps").value, 10) || 24;

    iniciarProgressoVideo(duracao, modelo);

    try {
      const res = await api("POST", "/api/estudio/gerar-video", {
        prompt,
        motor,
        modelo,
        duracao_segundos: duracao,
        resolucao,
        fps,
        modo_origem: modo,
        arquivo_referencia: arquivoRef,
        modo_execucao: "async"
      });


      if (res.ok && res.job_id) {
        // Exibe o card de aviso de tradução e enriquecimento se o prompt foi otimizado
        if (res.foi_otimizado && res.prompt_otimizado) {
          const cardTrad = $("vid-prompt-aviso-traducao");
          const txtTrad = $("vid-prompt-aviso-texto");
          const titTrad = $("vid-prompt-aviso-titulo");
          if (cardTrad && txtTrad) {
            txtTrad.textContent = `"${res.prompt_otimizado}"`;
            if (titTrad) titTrad.textContent = res.msg_otimizacao || " Traduzido e Enriquecido com IA (ComfyUI)";
            cardTrad.style.display = "block";
          }
        }

        toast("▶ Renderização iniciada na GPU!", "info");
        iniciarMonitoramentoJobVideo(res.job_id, {
          modelo,
          duracao,
          resolucao,
          inicio: Date.now()
        });
      }
    } catch (e) {
      if (e.extras && e.extras.servico_offline === "comfyui") {
        pararProgressoVideo(false, "ComfyUI está offline.");
        const placeholder = $("vid-canvas-placeholder");
        const player = $("vid-player-preview");
        if (placeholder && player) {
          placeholder.style.display = "flex";
          player.style.display = "none";
          placeholder.replaceChildren(
            el("div", { style: "color:var(--warning); font-size:15px; font-weight:600; margin-bottom:6px;" }, ["⚠ ComfyUI está Offline"]),
            el("div", { style: "color:var(--text-secondary); font-size:12px; margin-bottom:14px; max-width:400px; text-align:center;" }, [e.message]),
            el("div", { style: "display:flex; gap:8px;" }, [
              el("button", {
                className: "btn btn-primary btn-sm",
                textContent: "▶ Iniciar ComfyUI na GPU",
                onclick: async () => {
                  try {
                    toast("Iniciando ComfyUI...", "info");
                    await api("POST", "/api/servicos/comfyui/start", {});
                    toast("Serviço subindo! Aguarde carregar na VRAM da GPU.", "success");
                    await carregarVideos();
                  } catch (e) {
                    toast(`Falha ao iniciar: ${e.message}`, "error");
                  }
                }
              })
            ])
          );
        }
        toast("ComfyUI está offline. Inicie o serviço para renderizar na GPU.", "warning");
        return;
      }
      pararProgressoVideo(false, "Falha na renderização.");
      toast(`Erro na renderização: ${e.message}`, "error");
    }
  });
}

iniciarStreamHardware();

// Inicialização com rota hash e listener de mudança de hash
function sincronizarRotaHash() {
  const hash = window.location.hash.replace("#", "");
  if (hash && $(`view-${hash}`) && abaAtivaAtual !== hash) {
    ativarAba(hash);
  }
}
window.addEventListener("hashchange", sincronizarRotaHash);
const hashInicial = window.location.hash.replace("#", "");
ativarAba(hashInicial && $(`view-${hashInicial}`) ? hashInicial : "servicos");
// Estado do topo (online/parcial) é atualizado já na abertura, mesmo que a aba inicial não seja a de serviços.
carregarServicos();


// =====================================================================
// ESTÚDIO DE MÚSICA & TRILHAS SONORAS (YuE 2 · ComfyUI)
// =====================================================================
let galeriaMusicasSessao = [];
let ultimaMusicaGeradaUrl = null;

async function carregarMusicas() {
  const badge = $("badge-status-comfy-musica");
  try {
    const resMotores = await api("GET", "/api/estudio/status-motores");
    if (resMotores.ok && resMotores.comfyui) {
      if (badge) {
        badge.textContent = "ComfyUI :8188 online (YuE 2)";
        badge.className = "badge badge-paid";
      }
    } else {
      if (badge) {
        badge.textContent = "ComfyUI :8188 OFFLINE";
        badge.className = "badge badge-role";
      }
    }
  } catch (e) {
    if (badge) {
      badge.textContent = "ComfyUI :8188 INDISPONÍVEL";
      badge.className = "badge badge-role";
    }
  }

  // Carrega músicas salvas do disco
  try {
    const resMus = await api("GET", "/api/estudio/musicas");
    if (resMus.ok && Array.isArray(resMus.musicas)) {
      galeriaMusicasSessao = resMus.musicas.map(m => ({
        url: m.url,
        nome: m.nome,
        tamanho: m.tamanho ? `${Math.round(m.tamanho / 1024)} KB` : ""
      }));
      renderizarGaleriaMusicas();

      if (!ultimaMusicaGeradaUrl && galeriaMusicasSessao.length > 0) {
        selecionarMusicaPlayer(galeriaMusicasSessao[0].url, galeriaMusicasSessao[0].nome);
      }
    }
  } catch (e) {
    console.warn("Falha ao carregar músicas do disco:", e);
  }
}

function selecionarMusicaPlayer(url, titulo = "") {
  ultimaMusicaGeradaUrl = url;
  const player = $("mus-player-preview");
  const stage = $("mus-audio-stage");
  const placeholder = $("mus-canvas-placeholder");
  const metaStrip = $("mus-meta-strip");
  const tituloTxt = $("mus-player-titulo");

  if (player && stage && placeholder) {
    player.src = url;
    stage.style.display = "flex";
    placeholder.style.display = "none";
    if (tituloTxt) tituloTxt.textContent = `FAIXA: ${url.split("/").pop()}`;
    player.play().catch(() => {});
  }

  const btnBaixar = $("btn-baixar-musica");
  if (btnBaixar) btnBaixar.disabled = false;
  const btnCopiar = $("btn-copiar-link-musica");
  if (btnCopiar) btnCopiar.disabled = false;
  const btnExcluir = $("btn-excluir-musica");
  if (btnExcluir) btnExcluir.disabled = false;

  if (metaStrip) {
    metaStrip.style.display = "flex";
    $("mus-meta-job").textContent = `FAIXA: ${url.split("/").pop()}`;
    $("mus-meta-status").textContent = "FLAC estéreo";
    $("mus-meta-latencia").textContent = "Pronto";
  }

  renderizarGaleriaMusicas();
}

function limparPlayerMusica() {
  ultimaMusicaGeradaUrl = null;
  const player = $("mus-player-preview");
  const stage = $("mus-audio-stage");
  const placeholder = $("mus-canvas-placeholder");
  const metaStrip = $("mus-meta-strip");

  if (player) {
    player.pause();
    player.src = "";
  }
  if (stage) stage.style.display = "none";
  if (placeholder) placeholder.style.display = "flex";
  if (metaStrip) metaStrip.style.display = "none";

  const btnBaixar = $("btn-baixar-musica");
  if (btnBaixar) btnBaixar.disabled = true;
  const btnCopiar = $("btn-copiar-link-musica");
  if (btnCopiar) btnCopiar.disabled = true;
  const btnExcluir = $("btn-excluir-musica");
  if (btnExcluir) btnExcluir.disabled = true;
}

async function excluirMusicaPorUrl(url) {
  if (!url) return;
  const nomeArquivo = url.split("/").pop();
  if (!confirm(`Deseja excluir permanentemente a faixa musical "${nomeArquivo}" do disco?`)) return;

  try {
    const res = await api("DELETE", `/api/estudio/musicas/${encodeURIComponent(nomeArquivo)}`);
    if (res.ok) {
      toast(`Música "${nomeArquivo}" excluída do disco.`, "success");
      galeriaMusicasSessao = galeriaMusicasSessao.filter(item => item.url !== url);

      if (ultimaMusicaGeradaUrl === url) {
        if (galeriaMusicasSessao.length > 0) {
          selecionarMusicaPlayer(galeriaMusicasSessao[0].url, galeriaMusicasSessao[0].nome);
        } else {
          limparPlayerMusica();
        }
      }
      renderizarGaleriaMusicas();
    } else {
      toast(`Falha ao excluir música: ${res.erro || "Erro no servidor"}`, "error");
    }
  } catch (e) {
    toast(`Erro ao excluir música: ${e.message}`, "error");
  }
}

function renderizarGaleriaMusicas() {
  const container = $("mus-galeria-thumbs");
  if (!container) return;
  container.replaceChildren();

  if (galeriaMusicasSessao.length === 0) {
    container.appendChild(el("span", {
      style: "font-size:11px; color:var(--text-dim); font-style:italic; padding:6px 0;"
    }, ["Nenhuma faixa musical gerada nesta sessão ainda."]));
    return;
  }

  galeriaMusicasSessao.slice(0, 12).forEach(item => {
    const isAtivo = ultimaMusicaGeradaUrl === item.url;
    const thumb = el("div", {
      className: `vid-reel-card${isAtivo ? " active" : ""}`,
      title: `${item.nome} (Clique para reproduzir)`,
      onclick: () => {
        selecionarMusicaPlayer(item.url, item.nome);
      }
    }, [
      el("div", { style: "display:flex; justify-content:space-between; align-items:center; width:100%;" }, [
        el("span", { style: "font-size:10px; font-weight:600; color:#10b981; display:flex; align-items:center; gap:3px;" }, [
          "",
          el("span", { style: "font-size:9px; color:var(--text-muted);" }, [item.tamanho || "FLAC"])
        ]),
        el("button", {
          className: "galeria-thumb-del",
          title: "Excluir faixa",
          style: "position:static; width:16px; height:16px; font-size:9px;",
          onclick: (e) => {
            e.stopPropagation();
            excluirMusicaPorUrl(item.url);
          }
        }, ["✕"])
      ]),
      el("div", { style: "text-align:center; padding:4px 0;" }, [
        el("div", { style: "width:22px; height:22px; margin:0 auto; border-radius:50%; background:rgba(16,185,129,0.15); display:flex; align-items:center; justify-content:center; color:#10b981; font-size:10px;" }, ["▶"])
      ]),
      el("div", {
        style: "font-family:var(--font-mono); font-size:9px; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:center;"
      }, [item.nome.replace("comfy_audio_", "").replace(".flac", "")])
    ]);
    container.appendChild(thumb);
  });
}

// Botões da Barra de Ações de Áudio
const btnBaixarMusica = $("btn-baixar-musica");
if (btnBaixarMusica) {
  btnBaixarMusica.addEventListener("click", () => {
    if (!ultimaMusicaGeradaUrl) return;
    const a = document.createElement("a");
    a.href = ultimaMusicaGeradaUrl;
    a.download = `tudoia-musica-${Date.now()}.flac`;
    a.target = "_blank";
    a.click();
    toast("Download da faixa musical iniciado!", "info");
  });
}

const btnCopiarLinkMusica = $("btn-copiar-link-musica");
if (btnCopiarLinkMusica) {
  btnCopiarLinkMusica.addEventListener("click", () => {
    if (!ultimaMusicaGeradaUrl) return;
    const urlAbsoluta = new URL(ultimaMusicaGeradaUrl, window.location.origin).href;
    navigator.clipboard.writeText(urlAbsoluta).then(() => {
      toast("Link completo da música copiado!", "success");
    }).catch(() => {
      prompt("Copie o link abaixo:", urlAbsoluta);
    });
  });
}

const btnExcluirMusica = $("btn-excluir-musica");
if (btnExcluirMusica) {
  btnExcluirMusica.addEventListener("click", () => {
    if (!ultimaMusicaGeradaUrl) return;
    excluirMusicaPorUrl(ultimaMusicaGeradaUrl);
  });
}

// Controles de Prompt Musical e Tradução Inteligente
function inicializarControlesMusica() {
  const musStyle = $("mus-style");
  const dicaPt = $("mus-style-dica-pt");
  const cardTraducao = $("mus-style-aviso-traducao");
  const textoTraducao = $("mus-style-aviso-texto");
  const tituloTraducao = $("mus-style-aviso-titulo");
  const btnOtimizar = $("btn-otimizar-style-musica-manual");

  if (musStyle && dicaPt) {
    musStyle.addEventListener("input", () => {
      const val = musStyle.value.trim();
      dicaPt.style.display = (val && detectarTextoPortugues(val)) ? "block" : "none";
    });
  }

  if (btnOtimizar && musStyle) {
    btnOtimizar.addEventListener("click", async () => {
      const val = musStyle.value.trim();
      if (!val) {
        toast("Digite um estilo ou gênero musical antes de enriquecer com IA.", "warning");
        musStyle.focus();
        return;
      }
      btnOtimizar.disabled = true;
      btnOtimizar.textContent = " Enriquecendo...";
      try {
        const res = await api("POST", "/api/estudio/otimizar-prompt-musica", { prompt: val });
        if (res.ok && res.prompt) {
          if (textoTraducao) textoTraducao.textContent = `"${res.prompt}"`;
          if (tituloTraducao) tituloTraducao.textContent = res.prompt_otimizado ? "Estilo Musical Enriquecido com IA" : "Estilo em Inglês Mantido";
          if (cardTraducao) cardTraducao.style.display = "block";
          toast("✓ Estilo musical enriquecido para o YuE 2!", "success");
        }
      } catch (e) {
        toast(`Erro ao enriquecer estilo: ${e.message}`, "error");
      } finally {
        btnOtimizar.disabled = false;
        btnOtimizar.textContent = " Melhorar Estilo com IA";
      }
    });
  }

  const btnFecharAviso = $("btn-fechar-aviso-traducao-musica");
  if (btnFecharAviso && cardTraducao) {
    btnFecharAviso.addEventListener("click", () => {
      cardTraducao.style.display = "none";
    });
  }

  const btnAplicar = $("btn-aplicar-style-traduzido-musica");
  if (btnAplicar && musStyle && textoTraducao) {
    btnAplicar.addEventListener("click", () => {
      let t = textoTraducao.textContent.trim();
      if (t.startsWith('"') && t.endsWith('"')) t = t.slice(1, -1);
      musStyle.value = t;
      if (cardTraducao) cardTraducao.style.display = "none";
      if (dicaPt) dicaPt.style.display = "none";
      toast("Estilo musical aplicado ao campo!", "info");
      musStyle.focus();
    });
  }

  const btnCopiar = $("btn-copiar-style-traduzido-musica");
  if (btnCopiar && textoTraducao) {
    btnCopiar.addEventListener("click", () => {
      let t = textoTraducao.textContent.trim();
      if (t.startsWith('"') && t.endsWith('"')) t = t.slice(1, -1);
      navigator.clipboard.writeText(t).then(() => toast("Copiado para a área de transferência!", "success"));
    });
  }

  // Chips Rápidos de Estilos Musicais
  document.querySelectorAll(".btn-preset-mus").forEach(btn => {
    btn.addEventListener("click", () => {
      const estilo = btn.getAttribute("data-estilo");
      if (!musStyle || !estilo) return;
      const atual = musStyle.value.trim();
      musStyle.value = atual ? `${atual}, ${estilo}` : estilo;
      toast(`Adicionado: ${btn.textContent}`, "info");
      musStyle.focus();
    });
  });

  // Preset Instrumental
  const btnInst = $("btn-preset-instrumental");
  if (btnInst) {
    btnInst.addEventListener("click", () => {
      const musLyrics = $("mus-lyrics");
      if (musLyrics) {
        musLyrics.value = "[instrumental]";
        toast("Definido para [instrumental] sem vocais.", "info");
      }
    });
  }
}

inicializarControlesMusica();

// Gerenciador de Progresso Musical (YuE 2)
let timerProgressoMusicaInterval = null;
let tempoInicioMusica = 0;

function iniciarProgressoMusica(duracaoEstimada = 40) {
  const container = $("mus-progresso-container");
  const barra = $("mus-progresso-barra");
  const timerTxt = $("mus-progresso-timer");
  const faseTxt = $("mus-progresso-fase-txt");
  const detalheTxt = $("mus-progresso-detalhe");

  if (!container || !barra) return;

  container.style.display = "flex";
  barra.style.width = "4%";
  tempoInicioMusica = Date.now();

  const fases = [
    { seg: 0, pct: 10, fase: "Carregando YuE 2 3B e VAE de Áudio na GPU...", detalhe: "Arbitrando VRAM e preparando tokens harmônicos" },
    { seg: 3, pct: 30, fase: "Planejando Partitura ABC (Notação Musical)...", detalhe: "Estruturando melodia, progressão de acordes e compassos" },
    { seg: 10, pct: 60, fase: "Amostragem KSampler de Difusão de Áudio...", detalhe: "Sintetizando formas de onda e timbres dos instrumentos" },
    { seg: 25, pct: 85, fase: "Decodificação Neural VAE (Áudio Estéreo 44.1kHz)...", detalhe: "Reconstruindo áudio espacial em alta definição" },
    { seg: 35, pct: 95, fase: "Masterização e Empacotamento FLAC...", detalhe: "Finalizando exportação sem perdas" }
  ];

  if (timerProgressoMusicaInterval) clearInterval(timerProgressoMusicaInterval);

  timerProgressoMusicaInterval = setInterval(() => {
    const elapsedSeg = (Date.now() - tempoInicioMusica) / 1000;
    if (timerTxt) timerTxt.textContent = `${elapsedSeg.toFixed(1)}s`;

    let faseAtual = fases[0];
    for (let i = fases.length - 1; i >= 0; i--) {
      if (elapsedSeg >= fases[i].seg) {
        faseAtual = fases[i];
        break;
      }
    }

    if (faseTxt) faseTxt.textContent = faseAtual.fase;
    if (detalheTxt) detalheTxt.textContent = faseAtual.detalhe;

    const progressoSimulado = Math.min(95, faseAtual.pct + ((elapsedSeg - faseAtual.seg) / (duracaoEstimada || 40)) * 12);
    barra.style.width = `${progressoSimulado}%`;
  }, 300);
}

function pararProgressoMusica(sucesso = true) {
  if (timerProgressoMusicaInterval) {
    clearInterval(timerProgressoMusicaInterval);
    timerProgressoMusicaInterval = null;
  }
  const barra = $("mus-progresso-barra");
  const container = $("mus-progresso-container");
  const faseTxt = $("mus-progresso-fase-txt");

  if (barra) barra.style.width = sucesso ? "100%" : "0%";
  if (faseTxt && sucesso) faseTxt.textContent = "✓ Música sintetizada com sucesso!";

  setTimeout(() => {
    if (container) container.style.display = "none";
    if (barra) barra.style.width = "0%";
  }, 1200);
}

// Botão Cancelar Geração de Música
const btnCancelarMusica = $("btn-cancelar-musica");
if (btnCancelarMusica) {
  btnCancelarMusica.addEventListener("click", async () => {
    try {
      toast("Solicitando cancelamento imediato ao ComfyUI...", "warning");
      btnCancelarMusica.disabled = true;
      const res = await api("POST", "/api/estudio/cancelar", {});
      if (res.ok) {
        toast("Composição interrompida no ComfyUI!", "info");
      }
    } catch (e) {
      toast(`Falha ao cancelar: ${e.message}`, "error");
    } finally {
      btnCancelarMusica.disabled = false;
      pararProgressoMusica(false);
      const btnGerar = $("btn-gerar-musica");
      if (btnGerar) {
        btnGerar.disabled = false;
        btnGerar.innerHTML = `<span>Compor & Sintetizar Música</span><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
      }
    }
  });
}

// Botão Disparar Geração de Música
const btnGerarMusica = $("btn-gerar-musica");
if (btnGerarMusica) {
  btnGerarMusica.addEventListener("click", async () => {
    const style = $("mus-style") ? $("mus-style").value.trim() : "";
    if (!style) {
      toast("Informe um estilo ou gênero musical para compor a faixa.", "warning");
      $("mus-style").focus();
      return;
    }

    const lyrics = $("mus-lyrics") ? $("mus-lyrics").value.trim() : "[instrumental]";
    const duracao = parseFloat($("mus-select-duracao").value) || 30.0;
    const modo = $("mus-select-modo") ? $("mus-select-modo").value : "full";
    const modelo = $("mus-select-modelo") ? $("mus-select-modelo").value : "musica-yue2";

    btnGerarMusica.disabled = true;
    btnGerarMusica.innerHTML = `<span>Compondo Música (${duracao}s)...</span><span style="animation:spin 1s linear infinite;">⏳</span>`;

    iniciarProgressoMusica(duracao > 30 ? 60 : 35);

    try {
      const res = await api("POST", "/api/estudio/gerar-musica", {
        style,
        lyrics: lyrics || "[instrumental]",
        duracao_segundos: duracao,
        modo,
        modelo
      });

      if (res.ok && res.audio_url) {
        pararProgressoMusica(true);
        toast(`✓ Música sintetizada com sucesso em ${(res.latencia_ms / 1000).toFixed(1)}s!`, "success");

        selecionarMusicaPlayer(res.audio_url, res.job_id);

        galeriaMusicasSessao.unshift({
          url: res.audio_url,
          nome: res.audio_url.split("/").pop(),
          tamanho: "FLAC"
        });
        renderizarGaleriaMusicas();
      }
    } catch (e) {
      pararProgressoMusica(false);
      toast(`Erro na composição: ${e.message}`, "error");
    } finally {
      btnGerarMusica.disabled = false;
      btnGerarMusica.innerHTML = `<span>Compor & Sintetizar Música</span><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
    }
  });
}

// ------------------------------------------------ MINHA CONTA (sessão e login obrigatório)
const PAPEIS_TEXTO = {
  "tudoia-admin": "Administrador",
  "tudoia-operador": "Operador",
  "tudoia-leitor": "Leitor",
};
const PERMISSOES_TEXTO = {
  "tudoia-admin": "Tudo: alterar serviços, modelos, governança e roteador, além de segredos, provedores e importação de skills.",
  "tudoia-operador": "Alterar serviços, modelos e roteador. Vê a governança, mas não a altera nem sincroniza. Não acessa segredos nem provedores.",
  "tudoia-leitor": "Somente leitura: vê o painel, não altera nada.",
};

function formatarInstante(segundos) {
  if (!segundos) return "—";
  return new Date(segundos * 1000).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" });
}

function iniciaisDe(nome) {
  const partes = String(nome || "?").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  return (partes[0][0] + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}

let sessaoAtual = null;

function preencherMinhaConta(sessao) {
  sessaoAtual = sessao;
  const u = sessao.usuario || {};
  const nome = u.nome || u.login || u.email || "usuário";
  $("nav-usuario-iniciais").textContent = iniciaisDe(nome);
  $("nav-usuario-nome").textContent = nome;
  $("nav-usuario").style.display = "";

  $("usu-iniciais").textContent = iniciaisDe(nome);
  $("usu-nome").textContent = nome;
  $("usu-login").textContent = u.login ? `@${u.login}` : "";
  $("usu-email").textContent = u.email || "—";
  $("usu-login-2").textContent = u.login || "—";
  $("usu-sub").textContent = u.sub || "—";
  $("usu-conta-link").href = sessao.conta_url || "#";

  const papeis = $("usu-papeis");
  papeis.replaceChildren(...sessao.papeis.map((p) => {
    const badge = document.createElement("span");
    badge.className = "usuario-badge";
    badge.textContent = PAPEIS_TEXTO[p] || p;
    badge.title = p;
    return badge;
  }));
  const maior = sessao.papeis.includes("tudoia-admin") ? "tudoia-admin"
    : sessao.papeis.includes("tudoia-operador") ? "tudoia-operador" : "tudoia-leitor";
  $("usu-permissoes").textContent = PERMISSOES_TEXTO[maior];

  $("usu-entrou").textContent = formatarInstante(sessao.entrou_em);
  $("usu-expira").textContent = formatarInstante(sessao.expira_em);
  atualizarVerificacao();
}

function atualizarVerificacao() {
  if (!sessaoAtual?.verificado_em) return;
  const segundos = Math.max(0, Math.round(Date.now() / 1000 - sessaoAtual.verificado_em));
  $("usu-verificado").textContent = segundos < 60 ? `há ${segundos} s` : `há ${Math.round(segundos / 60)} min`;
}
setInterval(atualizarVerificacao, 5000);

async function encerrarSessao() {
  const saida = await api("POST", "/auth/logout", {});
  window.location.assign(saida.url);
}

(async function iniciarSessao() {
  if (!$("view-usuario")) return;
  const sessao = await api("GET", "/api/sessao");
  if (!sessao.configurado) {
    $("nav-usuario-nome").textContent = "login não configurado";
    $("nav-usuario").style.display = "";
    return;
  }
  if (!sessao.autenticado) {
    redirecionarLogin();
    return;
  }
  preencherMinhaConta(sessao);
  $("btn-sair-usuario").addEventListener("click", encerrarSessao);
})().catch(() => { /* falha de rede: a próxima chamada à API decide o que fazer */ });
