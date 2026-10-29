"use strict";
// Assistente do TudoIA Setup. Todo texto vindo de fora entra por textContent (nunca innerHTML).
const TOKEN = new URLSearchParams(location.search).get("t") || "";
const PASSOS = ["Sistema", "O que instalar", "Onde instalar", "Conta e chaves", "Revisar", "Instalar"];
const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, "");
    else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const f of filhos.flat()) if (f != null && f !== false) e.append(f.nodeType ? f : document.createTextNode(String(f)));
  return e;
}

async function api(metodo, caminho, corpo) {
  const r = await fetch(caminho, {
    method: metodo,
    headers: { "X-Token": TOKEN, ...(metodo === "POST" ? { "Content-Type": "application/json" } : {}) },
    body: metodo === "POST" ? JSON.stringify(corpo || {}) : undefined,
  });
  const dados = await r.json().catch(() => ({}));
  if (!r.ok && !dados.erros) throw new Error(dados.erro || `Erro ${r.status}`);
  return dados;
}

let diag = null;
let passo = 0;
let opcoes = null;
let errosCampo = {};
let instalando = false;

function mostrarCarregando(mensagem = "Aguarde um momento…", detalhe = "Conferindo configurações e sistema") {
  esconderCarregando();
  $("avancar").disabled = true;
  $("voltar").disabled = true;
  const overlay = h("div", { id: "carregando", class: "carregando-overlay", role: "status", "aria-live": "assertive" },
    h("div", { class: "spinner", "aria-hidden": "true" }),
    h("div", { class: "carregando-texto" }, mensagem),
    detalhe && h("div", { class: "carregando-sub" }, detalhe)
  );
  $("tela").append(overlay);
}

function esconderCarregando() {
  const el = $("carregando");
  if (el) el.remove();
  if (passo < 5) $("avancar").disabled = false;
  $("voltar").disabled = false;
}

function padroes() {
  const p = structuredClone(diag.padroes);
  p.componentes = diag.componentes.filter((c) => c.padrao).map((c) => c.id);
  p.fonte_codigo = diag.embutido ? "embutido" : "github";
  p.keycloak_existente_senha = "";
  p.chaves_provedores = {};
  return p;
}

// ───────── campos reutilizáveis
function campoTexto(rotulo, chave, { tipo = "text", dica = "", placeholder = "" } = {}) {
  const entrada = h("input", { type: tipo, value: opcoes[chave] ?? "", placeholder, autocomplete: "off", spellcheck: "false" });
  entrada.addEventListener("input", () => { opcoes[chave] = entrada.value; });
  return h("label", { class: "campo" }, rotulo, entrada, dica && h("small", {}, dica),
    errosCampo[chave] && h("div", { class: "erro-campo" }, errosCampo[chave]));
}

function campoPasta(rotulo, chave, dica, padraoTexto) {
  const entrada = h("input", { type: "text", value: opcoes[chave] ?? "", placeholder: padraoTexto || "", autocomplete: "off", spellcheck: "false" });
  entrada.addEventListener("input", () => { opcoes[chave] = entrada.value; });
  const botao = h("button", { class: "btn btn-sec", type: "button", onclick: () => escolherPasta(entrada, chave) }, "Escolher…");
  return h("div", {}, h("div", { class: "linha" }, h("label", { class: "campo" }, rotulo, entrada), botao),
    dica && h("small", { class: "campo" }, dica), errosCampo[chave] && h("div", { class: "erro-campo" }, errosCampo[chave]));
}

// ───────── seletor de pastas (o navegador não enxerga o disco; quem lista é o instalador, só nomes de pasta)
async function escolherPasta(entrada, chave) {
  const dlg = $("seletor");
  let atual = (opcoes[chave] || "").trim();
  const desenhar = async (caminho) => {
    const r = await api("GET", "/api/pastas?caminho=" + encodeURIComponent(caminho));
    if (r.erro) { $("seletor-atual").textContent = r.erro; return; }
    atual = r.atual;
    $("seletor-atual").textContent = r.atual || "Unidades do computador";
    const lista = $("seletor-lista");
    lista.replaceChildren();
    if (r.atual) lista.append(h("li", { onclick: () => desenhar(r.pai) }, "⬑ Subir um nível"));
    for (const i of r.itens) lista.append(h("li", { onclick: () => desenhar(i.caminho) }, i.nome));
  };
  await desenhar(atual && !atual.includes("..") ? atual.replace(/[\\/][^\\/]*$/, "") || "" : "");
  $("seletor-nova").value = "";
  $("seletor-ok").onclick = () => {
    const nova = $("seletor-nova").value.trim();
    const base = atual.replace(/\\$/, "");
    const final = nova ? `${base}\\${nova}` : atual;
    if (final) { opcoes[chave] = final; entrada.value = final; }
    dlg.close();
  };
  $("seletor-cancelar").onclick = () => dlg.close();
  dlg.showModal();
}

// ───────── telas
function telaSistema() {
  const s = diag.sistema;
  const cartao = (titulo, ok, texto, aviso) => h("div", { class: "cartao" }, h("b", {}, titulo),
    h("span", { class: ok ? "estado-ok" : aviso ? "estado-aviso" : "estado-erro" }, (ok ? "✓ " : aviso ? "! " : "✗ ") + texto));
  const ocupadas = Object.entries(s.portas_ocupadas).map(([n, p]) => `${n} (${p})`);
  const blocos = [
    h("h2", {}, "Vamos conferir esta máquina"),
    h("p", {}, "O instalador baixa o que faltar (Python, Docker Desktop, Ollama, dependências e imagens). Nada é enviado para fora."),
    h("div", { class: "grade" },
      cartao("Windows", s.windows_ok, s.windows_ok ? `build ${s.windows_build}` : `build ${s.windows_build}: precisa do Windows 10 2004 ou mais novo`),
      cartao("Internet", s.internet, s.internet ? "acesso ao GitHub" : "sem acesso ao github.com"),
      cartao("Python", s.python_instalado, s.python_instalado ? `instalado (${s.python_versao})` : "não encontrado: será instalado automaticamente", !s.python_instalado),
      cartao("Docker Desktop", s.docker_pronto, s.docker_pronto ? "pronto" : s.docker_instalado ? "instalado, será iniciado" : "será instalado (pede permissão de administrador)", !s.docker_pronto),
      cartao("Ollama", s.ollama_instalado, s.ollama_instalado ? "instalado" : "será instalado se você marcar", !s.ollama_instalado),
      cartao("GPU NVIDIA", !!s.gpu_nome, s.gpu_nome ? `${s.gpu_nome} (${Math.round(s.gpu_vram_mb / 1024)} GB)` : "não encontrada: sem ComfyUI; só nuvem e CPU", !s.gpu_nome),
      cartao("Portas", ocupadas.length === 0, ocupadas.length ? `em uso: ${ocupadas.join(", ")}` : "todas livres", ocupadas.length > 0)),
  ];
  if (diag.anterior) {
    blocos.push(h("div", { class: "cartao", style: "margin-top:14px" }, h("b", {}, diag.reinicio ? "Instalação interrompida por reinício" : "Há uma instalação anterior neste PC"),
      h("p", {}, "Posso carregar as opções dela (sem senhas nem chaves) para você continuar ou reinstalar por cima. Dados e .env são preservados."),
      h("button", { class: "btn btn-sec btn-peq", type: "button", onclick: () => { opcoes = { ...padroes(), ...diag.anterior, chaves_provedores: {}, keycloak_existente_senha: "" }; passo = 1; desenhar(); } }, "Carregar opções anteriores")));
  }
  return blocos;
}

function telaOnde() {
  const usa = (c) => opcoes.componentes.includes(c);
  return [
    h("h2", {}, "Onde instalar"),
    h("p", {}, "Escolha as pastas. Deixe em branco o que quiser no padrão (dentro da pasta de instalação)."),
    campoPasta("Pasta de instalação", "pasta_instalacao", "Programa, ambiente Python e configuração (.env). Evite caminhos longos.", "C:\\TudoIA"),
    campoPasta("Pasta de dados", "pasta_dados", "Bancos, memória do Cérebro, documentos, logs e saídas do Estúdio.", "<instalação>\\dados"),
    usa("ollama") && campoPasta("Pasta dos modelos do Ollama", "pasta_pesos_ollama", "Os pesos são grandes (dezenas de GB). Escolha um disco com espaço.", "<instalação>\\modelos\\ollama\\models"),
    usa("comfyui") && campoPasta("Pasta do ComfyUI portable", "pasta_comfyui", "Cerca de 2 GB mais os modelos de imagem e vídeo.", "<instalação>\\modelos\\comfyui\\ComfyUI_windows_portable"),
    h("details", {}, h("summary", {}, "Avançado"),
      campoTexto("Nome do projeto Docker", "projeto_compose", { dica: "Prefixo dos volumes. Use outro nome para conviver com uma instalação que já exista." })),
  ];
}

function telaComponentes() {
  const caixa = (c) => {
    const marcada = opcoes.componentes.includes(c.id);
    const gpuAusente = c.id === "comfyui" && !diag.sistema.gpu_nome;
    const entrada = h("input", { type: "checkbox", checked: marcada, disabled: gpuAusente });
    entrada.addEventListener("change", () => {
      opcoes.componentes = entrada.checked ? [...opcoes.componentes, c.id] : opcoes.componentes.filter((x) => x !== c.id);
      if (c.id === "keycloak" && entrada.checked) opcoes.keycloak_existente = false;
      desenhar();
    });
    const descr = {
      cerebro: "Servidor MCP local: busca na web, leitura de páginas, seus documentos e memória de fatos.",
      webui: "Chat com interface própria e voz (Kokoro) sobre os seus modelos.",
      n8n: "Automação visual: resumos, digest de notícias e ingestão de documentos no Cérebro.",
      keycloak: "Login do painel (OIDC) já configurado, com um administrador seu. Recomendado.",
      ollama: "LLMs locais e embeddings (o Cérebro e o roteador usam o bge-m3). Os modelos NÃO são baixados agora.",
      comfyui: gpuAusente ? "Indisponível: precisa de GPU NVIDIA." : "Geração de imagem e vídeo no Estúdio (versão NVIDIA).",
    }[c.id];
    return h("label", { class: "opcao" }, entrada, h("div", {}, h("b", {}, c.nome), h("p", {}, descr)), h("span", { class: "gb" }, `~${c.gb} GB`));
  };
  const login = opcoes.keycloak_existente
    ? [h("label", { class: "campo" }, "Usuário admin do Keycloak existente", (() => { const i = h("input", { type: "text", value: opcoes.keycloak_existente_admin }); i.addEventListener("input", () => { opcoes.keycloak_existente_admin = i.value; }); return i; })()),
       campoTexto("Senha do admin", "keycloak_existente_senha", { tipo: "password", dica: "Usada só para criar o realm tudoia; fica no .env, protegido pela pasta." })]
    : [];
  return [
    h("h2", {}, "O que instalar"),
    h("p", {}, "O núcleo (painel, gateway LiteLLM e o banco dele) sempre é instalado. O resto você escolhe."),
    h("label", { class: "opcao travada" }, h("input", { type: "checkbox", checked: true, disabled: true }),
      h("div", {}, h("b", {}, "Núcleo: painel + LiteLLM/roteador + Postgres"), h("p", {}, "Obrigatório.")), h("span", { class: "gb" }, "~4 GB")),
    diag.componentes.map(caixa),
    !opcoes.componentes.includes("keycloak") && h("div", { class: "cartao" },
      h("b", {}, "Sem Keycloak embutido"),
      h("p", {}, "O painel exige login. Marque o embutido acima ou use um Keycloak que já roda em localhost:8180."),
      h("label", { class: "opcao", style: "margin-top:8px" }, (() => { const i = h("input", { type: "checkbox", checked: opcoes.keycloak_existente }); i.addEventListener("change", () => { opcoes.keycloak_existente = i.checked; desenhar(); }); return i; })(),
        h("div", {}, h("b", {}, "Usar o Keycloak que já existe em localhost:8180"))), login),
    errosCampo.componentes && h("div", { class: "erro-campo" }, errosCampo.componentes),
  ];
}

function telaConta() {
  const chaves = diag.chaves_provedores.map((nome) => {
    const i = h("input", { type: "password", value: opcoes.chaves_provedores[nome] || "", autocomplete: "off", spellcheck: "false", placeholder: "(opcional)" });
    i.addEventListener("input", () => { if (i.value) opcoes.chaves_provedores[nome] = i.value; else delete opcoes.chaves_provedores[nome]; });
    return h("label", { class: "campo" }, nome, i);
  });
  const radio = (valor, texto) => {
    const i = h("input", { type: "radio", name: "fonte", checked: opcoes.fonte_codigo === valor, disabled: valor === "embutido" && !diag.embutido });
    i.addEventListener("change", () => { opcoes.fonte_codigo = valor; desenhar(); });
    return h("label", { class: "opcao" }, i, h("div", {}, texto));
  };
  const caixa = (chave, texto) => {
    const i = h("input", { type: "checkbox", checked: opcoes[chave] });
    i.addEventListener("change", () => { opcoes[chave] = i.checked; });
    return h("label", { class: "opcao" }, i, h("div", {}, texto));
  };
  return [
    h("h2", {}, "Conta e chaves"),
    campoTexto("E-mail do administrador", "admin_email", { tipo: "email", dica: "Vira o primeiro administrador do painel. Uma senha temporária aparece no fim da instalação." }),
    campoTexto("Fuso horário", "fuso", { dica: "Ex.: America/Sao_Paulo" }),
    h("details", {}, h("summary", {}, "Chaves de provedores de IA (opcional — pode preencher depois no painel)"),
      h("p", {}, "Ficam só no .env desta instalação. Gratuito não é privado: o texto sai da sua máquina para o provedor."), chaves),
    h("h3", {}, "Opções"),
    caixa("criar_atalhos", "Criar atalhos na área de trabalho e no menu Iniciar"),
    caixa("iniciar_ao_final", "Iniciar o painel ao terminar"),
    caixa("configurar_clientes_ia", "Configurar Claude Code, Cursor, Codex… (grava regras e servidores MCP nesses programas)"),
    h("details", {}, h("summary", {}, "Origem do código do TudoIA"),
      radio("embutido", diag.embutido ? "Embutido neste instalador (versão fixa)" : "Embutido (indisponível neste instalador)"),
      radio("github", "Baixar do GitHub"),
      opcoes.fonte_codigo === "github" && [campoTexto("Repositório", "github_repo"), campoTexto("Branch ou tag", "github_ref")]),
  ];
}

let resumoValidado = null;
function telaRevisar() {
  const r = resumoValidado;
  if (!r) return [h("p", {}, "Conferindo…")];
  const nomes = Object.fromEntries(diag.componentes.map((c) => [c.id, c.nome]));
  const item = (t, v) => [h("dt", {}, t), h("dd", { class: "mono" }, v || "—")];
  return [
    h("h2", {}, "Revisar"),
    r.erros.length ? h("div", { class: "cartao" }, h("b", { class: "estado-erro" }, "Corrija antes de instalar:"), r.erros.map((e) => h("div", { class: "erro-campo" }, `${e.campo ? e.campo + ": " : ""}${e.mensagem}`))) : h("p", { class: "estado-ok" }, "✓ Tudo certo para instalar."),
    h("dl", { class: "resumo" },
      item("Pasta de instalação", opcoes.pasta_instalacao), item("Pasta de dados", r.resumo.pasta_dados),
      r.resumo.pasta_pesos && item("Modelos do Ollama", r.resumo.pasta_pesos), r.resumo.pasta_comfyui && item("ComfyUI", r.resumo.pasta_comfyui),
      item("Componentes", ["Núcleo", ...opcoes.componentes.map((c) => nomes[c])].join(" · ") + (opcoes.keycloak_existente ? " · Keycloak existente" : "")),
      item("Perfis Docker", r.resumo.perfis.join(", ")),
      item("Administrador", opcoes.admin_email), item("Espaço", `~${r.resumo.espaco_gb} GB necessários, ${r.resumo.livre_gb} GB livres (sem os modelos)`),
      item("Portas", Object.entries(r.resumo.portas).map(([n, p]) => `${n}:${p}`).join("  ")),
      item("Origem do código", opcoes.fonte_codigo === "github" ? `GitHub ${opcoes.github_repo}@${opcoes.github_ref}` : "embutido")),
    Object.keys(r.resumo.portas_ocupadas).length ? h("p", { class: "estado-aviso" }, "Portas em uso agora: " + Object.keys(r.resumo.portas_ocupadas).join(", ") + ". Só é problema se não for uma instalação anterior do TudoIA.") : null,
    h("p", {}, "Os modelos de IA não são baixados agora (são dezenas de GB). Depois da instalação use o painel ou o comando de modelos."),
  ];
}

// ───────── instalação
let proximo = 0;
function telaInstalar() {
  return [h("h2", {}, "Instalando"), h("ul", { id: "lista-etapas", class: "etapas" }), h("div", { id: "log", class: "log", "aria-label": "Registro" }), h("div", { id: "fim" })];
}

const MARCAS = { pendente: "·", executando: "…", ok: "✓", falhou: "✗", pulada: "–" };
async function acompanhar() {
  for (;;) {
    let p;
    try { p = await api("GET", "/api/progresso?desde=" + proximo); } catch (e) { $("aviso").textContent = "Perdi a conexão com o instalador: " + e.message; return; }
    if (!p.ativo) return;
    const lista = $("lista-etapas");
    if (lista) lista.replaceChildren(...p.etapas.map((e) => h("li", { class: e.estado === "falhou" ? "estado-erro" : e.estado === "ok" ? "estado-ok" : "" },
      h("span", { class: "marca" }, MARCAS[e.estado] || "?"), h("span", {}, e.titulo), e.mensagem && e.estado === "falhou" ? h("small", {}, " — " + e.mensagem) : null)));
    const log = $("log");
    if (log && p.linhas.length) { log.append(document.createTextNode(p.linhas.join("\n") + "\n")); log.scrollTop = log.scrollHeight; }
    proximo = p.proximo;
    if (p.terminou) { instalando = false; return fim(p); }
    await new Promise((r) => setTimeout(r, 1200));
  }
}

function fim(p) {
  const alvo = $("fim");
  if (!alvo) return;
  $("avancar").disabled = true;
  if (p.resultado) {
    const r = p.resultado;
    alvo.replaceChildren(h("div", { class: "destaque" }, h("b", {}, "TudoIA instalado."),
      h("p", {}, "Painel: ", h("span", { class: "mono" }, r.painel), " — entre com ", h("b", {}, r.admin_email), "."),
      r.admin_senha_temporaria && h("p", {}, "Senha temporária (aparece só agora; a troca é obrigatória no primeiro login): ", h("span", { class: "senha" }, r.admin_senha_temporaria)),
      h("p", {}, "Próximo passo: baixar os modelos de IA (painel → Modelos). Os atalhos TudoIA - Painel, Iniciar e Parar já estão na área de trabalho e no menu Iniciar.")),
      h("button", { class: "btn btn-pri", type: "button", onclick: () => api("POST", "/api/abrir-painel") }, "Abrir o painel"), " ",
      h("button", { class: "btn btn-sec", type: "button", onclick: async () => { await api("POST", "/api/encerrar"); document.body.replaceChildren(h("p", {}, "Instalador encerrado. Pode fechar esta aba.")); } }, "Fechar o instalador"));
  } else if (p.reinicio) {
    alvo.replaceChildren(h("div", { class: "cartao" }, h("b", { class: "estado-aviso" }, "Reinicie o Windows para continuar"),
      h("p", {}, p.erro), h("p", {}, "Depois do reinício abra o TudoIA Setup de novo: ele retoma de onde parou."),
      h("button", { class: "btn btn-sec", type: "button", onclick: retomar }, "Já reiniciei / tentar de novo")));
  } else {
    alvo.replaceChildren(h("div", { class: "cartao" }, h("b", { class: "estado-erro" }, "A instalação parou"), h("p", {}, p.erro),
      h("p", {}, "Corrija o problema e tente de novo: o instalador pula o que já foi concluído."),
      h("button", { class: "btn btn-pri", type: "button", onclick: retomar }, "Tentar de novo")));
  }
}

async function retomar() {
  mostrarCarregando("Retomando a instalação…", "Aguarde enquanto o processo é reiniciado");
  const r = await api("POST", "/api/retomar").catch((e) => ({ erro: e.message }));
  esconderCarregando();
  if (r.erro) { $("aviso").textContent = r.erro; return; }
  instalando = true;
  $("fim").replaceChildren();
  acompanhar();
}

// ───────── navegação
async function validar() {
  resumoValidado = await api("POST", "/api/validar", opcoes);
  errosCampo = {};
  for (const e of resumoValidado.erros) if (e.campo) errosCampo[e.campo] = e.mensagem;
  return resumoValidado.erros;
}

const CAMPOS_POR_PASSO = { 1: ["componentes", "keycloak_existente", "keycloak_existente_admin", "keycloak_existente_senha"],
  2: ["pasta_instalacao", "pasta_dados", "pasta_pesos_ollama", "pasta_comfyui", "projeto_compose"],
  3: ["admin_email", "fuso", "github_repo", "github_ref", "chaves_provedores", "fonte_codigo"] };

function desenhar() {
  document.title = `TudoIA Setup · ${PASSOS[passo]}`;
  $("passos").replaceChildren(...PASSOS.map((n, i) => h("span", { class: "passo" + (i === passo ? " atual" : i < passo ? " feito" : "") }, `${i + 1}. ${n}`)));
  const telas = [telaSistema, telaComponentes, telaOnde, telaConta, telaRevisar, telaInstalar];
  $("tela").replaceChildren(...[telas[passo]()].flat(3).filter(Boolean));
  $("voltar").style.visibility = passo === 0 || passo === 5 ? "hidden" : "visible";
  $("avancar").textContent = passo === 4 ? "Instalar" : "Continuar";
  $("avancar").style.display = passo === 5 ? (instalando ? "none" : "inline-block") : "inline-block";
  $("avancar").disabled = passo === 0 && !(diag.sistema.windows_ok && diag.sistema.internet);
  $("aviso").textContent = "";
}

$("voltar").addEventListener("click", () => { if (passo > 0) { passo -= 1; desenhar(); } });
$("avancar").addEventListener("click", async () => {
  $("aviso").textContent = "";
  try {
    if (passo >= 1 && passo <= 3) {
      mostrarCarregando("Validando opções…", "Conferindo portas, pastas e compatibilidade");
      const erros = await validar();
      const meus = erros.filter((e) => (CAMPOS_POR_PASSO[passo] || []).includes(e.campo));
      if (meus.length) {
        esconderCarregando();
        $("aviso").textContent = meus[0].mensagem;
        desenhar();
        $("aviso").textContent = meus[0].mensagem;
        return;
      }
    }
    if (passo === 3) {
      mostrarCarregando("Preparando revisão…", "Validando todas as configurações");
      await validar();
    }
    if (passo === 4) {
      mostrarCarregando("Validando tudo antes de instalar…", "Verificando se o sistema está pronto");
      const erros = await validar();
      if (erros.length) {
        esconderCarregando();
        $("aviso").textContent = "Há campos para corrigir.";
        desenhar();
        return;
      }
      mostrarCarregando("Iniciando a instalação…", "Disparando o processo de configuração do TudoIA");
      const r = await api("POST", "/api/instalar", opcoes).catch((e) => ({ erro: e.message }));
      if (r.erro) {
        esconderCarregando();
        $("aviso").textContent = r.erro;
        return;
      }
      esconderCarregando();
      passo = 5;
      instalando = true;
      proximo = 0;
      desenhar();
      acompanhar();
      return;
    }
    esconderCarregando();
    passo += 1;
    desenhar();
  } catch (e) {
    esconderCarregando();
    $("aviso").textContent = e.message;
  }
});

(async function iniciar() {
  try {
    $("tela").replaceChildren(
      h("div", { class: "carregando-tela" },
        h("div", { class: "spinner", "aria-hidden": "true" }),
        h("div", { class: "carregando-texto" }, "Iniciando o TudoIA Setup…"),
        h("div", { class: "carregando-sub" }, "Examinando sistema, portas e componentes")
      )
    );
    diag = await api("GET", "/api/diagnostico");
  } catch (e) {
    $("tela").replaceChildren(h("p", { class: "estado-erro" }, "Não consegui falar com o instalador: " + e.message + ". Abra o endereço completo que ele mostrou."));
    $("avancar").disabled = true;
    return;
  }
  $("versao").textContent = "v" + diag.versao;
  opcoes = padroes();
  desenhar();
})();
