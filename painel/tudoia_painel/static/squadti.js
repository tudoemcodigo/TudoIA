"use strict";
// Menu SquadTI: abas Tarefas | Agentes. Tarefas = lista + cockpit (trilha, orçamento, log ao vivo, auditoria, conversa com o CHEFE);
// Agentes = configuração de modelo, revisão, validação em execução e orçamento (só o admin salva).
// Carregado depois do painel.js (usa $, el, api, toast, abaAtivaAtual).
// Todo texto que vem da API entra por textContent: briefing, mensagens, log e arquivos são conteúdo de modelo/usuário, nunca marcação.

const SQUADTI_ROTULOS = {
  aguardando_respostas: ["Aguardando suas respostas", "aviso"],
  aguardando_aprovacao_spec: ["Aprovar especificação", "aviso"],
  aguardando_aprovacao_release: ["Aprovar release", "aviso"],
  em_fase: ["Em andamento", "info"],
  concluida: ["Concluída", "ok"],
  bloqueada: ["Bloqueada", "erro"],
  escalada: ["Escalada: precisa de você", "erro"],
  escalada_qa: ["Escalada: QA reprovou", "erro"],
  escalada_revisao: ["Escalada: revisão reprovou", "erro"],
  inexistente: ["Inexistente", "info"],
};
const SQUADTI_NOS = ["analista_requisitos", "arquiteto", "dba", "dev_backend", "dev_frontend", "qa_testes", "revisor", "appsec", "devops", "documentacao", "release"];
const SQUADTI_PERFIS = [
  ["local-estrito", "Local estrito (nunca sai da máquina)", false],
  ["local", "Local (o gateway pode reenviar à nuvem)", true],
  ["hibrido", "Híbrido (local primeiro, nuvem gratuita de apoio)", true],
  ["nuvem", "Nuvem gratuita", true],
  ["auto", "Automático (tudoia-auto: o roteador decide por pedido entre local e nuvem)", true],
];
const SQUADTI_AGENTES = ["chefe", "analista", "arquiteto", "dba", "backend", "frontend", "revisor", "senior", "hacker", "mantenedor", "documentacao"];
const SQUADTI_EIXOS = [["tokens", "Tokens", 1000, 50000000], ["tempo_s", "Tempo (s)", 60, 86400], ["chamadas", "Chamadas ao modelo", 1, 10000]];
const SQUADTI_MAX_LOG = 500;
const SQUADTI_MAX_MENSAGEM = 4000;
const SQUADTI_PRONTO_PARA_ENTREVISTA = "aguardando_respostas";

let squadtiTimer = null;
let squadtiLogTimer = null;
let squadtiAberta = null;
let squadtiAba = "tarefas";
let squadtiSessaoPromessa = null;
// Estado do log ao vivo da tarefa aberta: o cursor devolvido pela API e as linhas já mostradas (no máximo SQUADTI_MAX_LOG).
const squadtiLog = { tarefa: null, cursor: 0, linhas: [], rodando: false, finalPendente: false, ocupado: false };

function squadtiRotulo(estado) {
  return SQUADTI_ROTULOS[estado] || [estado, "info"];
}

function squadtiBadge(estado, rodando) {
  const [texto, tom] = rodando ? ["Executando…", "info"] : squadtiRotulo(estado);
  return el("span", { className: `squadti-badge squadti-${tom}`, textContent: texto });
}

function squadtiHora(t) {
  return t ? new Date(t * 1000).toLocaleTimeString("pt-BR") : "";
}

function squadtiNum(n) {
  n = Number(n) || 0;
  return n >= 1000000 ? `${(n / 1000000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function squadtiSeg(s) {
  s = Number(s) || 0;
  return s >= 60 ? `${Math.floor(s / 60)}min ${Math.round(s % 60)}s` : `${s.toFixed(1)}s`;
}

// Papel do usuário (cache): leitor só vê; operador também age; admin também salva a configuração dos agentes.
function squadtiSessao() {
  if (!squadtiSessaoPromessa) {
    squadtiSessaoPromessa = api("GET", "/api/sessao")
      .then((s) => ({ admin: s.admin === true, escrita: s.admin === true || (s.papeis || []).includes("tudoia-operador") }))
      .catch(() => ({ admin: false, escrita: false }));
  }
  return squadtiSessaoPromessa;
}

// Atualiza uma região só quando a assinatura muda, para não apagar o que o usuário está digitando nem o arquivo aberto.
function squadtiRegiao(id, assinatura, construir) {
  const alvo = $(id);
  if (!alvo || alvo.dataset.assinatura === assinatura) return;
  alvo.dataset.assinatura = assinatura;
  alvo.replaceChildren(...construir());
}

// ---------------------------------------------------------------- casca: abas
async function carregarSquadti() {
  const raiz = $("squadti-conteudo");
  let estado;
  try {
    estado = await api("GET", "/api/squadti/estado");
  } catch (e) {
    raiz.replaceChildren(el("div", { className: "squadti-faixa squadti-erro", textContent: `Não consegui consultar a SquadTI: ${e.message}` }));
    return;
  }
  if (!estado.configurado) {
    raiz.replaceChildren(el("div", { className: "squadti-faixa squadti-aviso" }, [
      el("strong", { textContent: "SquadTI não configurada. " }),
      "Marque squadti em COMPOSE_PROFILES, gere o TUDOIA_SQUADTI_TOKEN (tudoia segredos) e a chave (tudoia squadti-chave) e ligue o serviço SquadTI em Sistema → Serviços.",
    ]));
    return;
  }
  if (!estado.no_ar) {
    raiz.replaceChildren(el("div", { className: "squadti-faixa squadti-aviso" }, [
      el("strong", { textContent: "A API da Squad está parada. " }),
      "Ligue o serviço SquadTI em Sistema → Serviços (container squadti).",
    ]));
    return;
  }
  const abas = el("div", { className: "squadti-abas", role: "tablist" }, [
    ["tarefas", "Tarefas"], ["agentes", "Agentes"],
  ].map(([id, rotulo]) => el("button", {
    className: `subtab-btn ${squadtiAba === id ? "active" : ""}`, id: `squadti-aba-${id}`, role: "tab", textContent: rotulo,
    onclick: () => trocarAbaSquadti(id),
  })));
  raiz.replaceChildren(abas, el("div", { id: "squadti-painel-tarefas" }), el("div", { id: "squadti-painel-agentes" }));
  aplicarAbaSquadti();
  clearInterval(squadtiTimer);
  squadtiTimer = setInterval(() => {
    if (abaAtivaAtual !== "squadti") { pararSquadti(); return; }
    if (squadtiAba === "tarefas") atualizarSquadti(true);
  }, 5000);
}

function pararSquadti() {
  clearInterval(squadtiTimer);
  clearInterval(squadtiLogTimer);
  squadtiLogTimer = null;
}

function trocarAbaSquadti(aba) {
  squadtiAba = aba;
  aplicarAbaSquadti();
}

function aplicarAbaSquadti() {
  for (const id of ["tarefas", "agentes"]) {
    $(`squadti-aba-${id}`).classList.toggle("active", id === squadtiAba);
    $(`squadti-painel-${id}`).style.display = id === squadtiAba ? "" : "none";
  }
  if (squadtiAba === "tarefas") atualizarSquadti();
  else carregarAgentesSquadti();
}

// ---------------------------------------------------------------- aba Tarefas
async function atualizarSquadti(silencioso = false) {
  const raiz = $("squadti-painel-tarefas");
  if (!raiz) return;
  let lista;
  try {
    lista = (await api("GET", "/api/squadti/tarefas")).tarefas;
  } catch (e) {
    if (!silencioso) toast(`SquadTI: ${e.message}`, "error");
    return;
  }
  const rodando = (t) => t.execucao && t.execucao.estado === "rodando";
  const precisaDeVoce = ["aguardando_respostas", "aguardando_aprovacao_spec", "aguardando_aprovacao_release", "escalada"];
  const pendentes = lista.filter((t) => !rodando(t) && precisaDeVoce.includes(t.situacao.estado));

  const caixa = el("section", { className: "squadti-bloco" }, [
    el("h3", { textContent: `Precisa de você (${pendentes.length})` }),
    pendentes.length ? el("div", { className: "squadti-cartoes" }, pendentes.map(squadtiCartao))
      : el("p", { className: "suave", textContent: "Nenhuma tarefa esperando resposta, aprovação ou decisão sobre uma escalada." }),
  ]);

  const linhas = lista.map((t) => el("tr", { className: "squadti-linha", onclick: () => abrirTarefaSquadti(t.tarefa) }, [
    el("td", {}, [el("strong", { textContent: t.tarefa })]),
    el("td", { textContent: t.projeto || "" }),
    el("td", { textContent: t.modelo || "" }),
    el("td", {}, [squadtiBadge(t.situacao.estado, rodando(t))]),
    el("td", { textContent: t.situacao.fase || "" }),
  ]));
  const tabela = el("section", { className: "squadti-bloco" }, [
    el("h3", { textContent: `Tarefas (${lista.length})` }),
    lista.length ? el("table", { className: "squadti-tabela" }, [
      el("thead", {}, [el("tr", {}, ["Tarefa", "Projeto", "Modelo", "Situação", "Fase"].map((h) => el("th", { textContent: h })))]),
      el("tbody", {}, linhas),
    ]) : el("p", { className: "suave", textContent: "Nenhuma tarefa ainda. Use “Nova tarefa”." }),
  ]);

  // a seção do detalhe é criada uma vez e atualizada por regiões: o campo do chat e o log não podem ser recriados a cada ciclo
  let detalhe = $("squadti-detalhe");
  if (!detalhe) detalhe = el("section", { className: "squadti-bloco", id: "squadti-detalhe" });
  let lst = $("squadti-lista");
  if (!lst) {
    lst = el("div", { id: "squadti-lista" });
    raiz.replaceChildren(lst, detalhe);
  }
  lst.replaceChildren(caixa, tabela);
  if (squadtiAberta && lista.some((t) => t.tarefa === squadtiAberta)) await abrirTarefaSquadti(squadtiAberta, true);
  else if (squadtiAberta) fecharDetalheSquadti();
}

function fecharDetalheSquadti() {
  squadtiAberta = null;
  squadtiLog.tarefa = null;
  clearInterval(squadtiLogTimer);
  squadtiLogTimer = null;
  const d = $("squadti-detalhe");
  if (d) { d.replaceChildren(); delete d.dataset.tarefa; }
}

function squadtiCartao(t) {
  const est = t.situacao.estado;
  const acoes = [el("button", { className: "btn btn-outline btn-sm", textContent: "Abrir", onclick: () => abrirTarefaSquadti(t.tarefa) })];
  if (est === "aguardando_aprovacao_spec") {
    acoes.push(el("button", { className: "btn btn-primary btn-sm", textContent: "Aprovar especificação", onclick: () => aprovarSquadti(t.tarefa, "aprovar") }));
  } else if (est === "aguardando_aprovacao_release") {
    acoes.push(el("button", { className: "btn btn-primary btn-sm", textContent: "Aprovar release", onclick: () => aprovarSquadti(t.tarefa, "aprovar-release") }));
  }
  return el("div", { className: "squadti-cartao" }, [
    el("div", {}, [el("strong", { textContent: t.tarefa }), " ", squadtiBadge(est, false)]),
    el("p", { className: "suave", textContent: t.situacao.mensagem }),
    el("div", { className: "squadti-acoes" }, acoes),
  ]);
}

async function aprovarSquadti(tarefa, acao) {
  const aviso = acao === "aprovar-release"
    ? `Aprovar o release de “${tarefa}”? Isso só gera as notas de release: nada é commitado, tagueado nem publicado.`
    : `Aprovar a especificação de “${tarefa}”? A Squad começa a arquitetura e o código.`;
  if (!window.confirm(aviso)) return;
  try {
    await api("POST", `/api/squadti/tarefas/${encodeURIComponent(tarefa)}/${acao}`, {});
    toast("Aprovado. A Squad segue em segundo plano.", "success");
    squadtiAberta = tarefa;
    await atualizarSquadti(true);
  } catch (e) {
    toast(`Não aprovou: ${e.message}`, "error");
  }
}

// ---------------------------------------------------------------- cockpit
function squadtiBarra(rotulo, uso, limite, formatar) {
  const sem = !limite;
  const pct = sem ? 0 : Math.min(100, Math.round((uso / limite) * 100));
  const tom = pct >= 90 ? "erro" : pct >= 70 ? "aviso" : "ok";
  return el("div", { className: "squadti-barra" }, [
    el("div", { className: "squadti-barra-rotulo" }, [
      el("span", { textContent: rotulo }),
      el("span", { className: "suave", textContent: sem ? `${formatar(uso)} (sem limite)` : `${formatar(uso)} de ${formatar(limite)} (${pct}%)` }),
    ]),
    el("div", { className: "squadti-barra-trilho", role: "progressbar", "aria-label": rotulo, "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) }, [
      el("div", { className: `squadti-barra-enche squadti-${sem ? "info" : tom}`, style: `width:${sem ? 0 : pct}%` }),
    ]),
  ]);
}

function squadtiStatusNos(d, aud) {
  const feitos = new Map((aud.nos || []).map((n) => [n.no, n]));
  const ex = d.execucao;
  const rodando = Boolean(ex && ex.estado === "rodando");
  const ordem = [...SQUADTI_NOS, ...[...feitos.keys()].filter((n) => !SQUADTI_NOS.includes(n))];
  let proximoMarcado = false;
  return ordem.map((no) => {
    const reg = feitos.get(no);
    let status = "pendente";
    if (reg) status = reg.erro || reg.status === "falhou" ? "falhou" : "ok";
    else if (d.falha_origem === no) status = "falhou";
    else if (rodando && !proximoMarcado) { status = "rodando"; proximoMarcado = true; }
    return { no, status, reg };
  });
}

function squadtiTrilha(d, aud) {
  const rotulos = { pendente: "pendente", rodando: "rodando", ok: "ok", falhou: "falhou" };
  return el("div", { className: "squadti-trilha" }, squadtiStatusNos(d, aud).map(({ no, status, reg }) => {
    const filhos = [el("span", { className: "squadti-no-nome", textContent: no.replace(/_/g, " ") }),
      el("span", { className: `squadti-no-status squadti-no-${status}`, textContent: rotulos[status] })];
    if (reg) {
      const tokens = (Number(reg.tokens_entrada) || 0) + (Number(reg.tokens_saida) || 0);
      filhos.push(el("span", { className: "squadti-no-detalhe suave", textContent: `${squadtiSeg(reg.duracao_s)} · ${reg.chamadas || 0} chamada(s) · ${squadtiNum(tokens)} tok` }));
    }
    return el("div", { className: `squadti-no squadti-no-caixa-${status}` }, filhos);
  }));
}

function squadtiOrcamento(aud) {
  const t = aud.totais || {};
  const o = aud.orcamento || {};
  return el("div", { className: "squadti-orcamento" }, [
    squadtiBarra("Tokens", t.tokens || 0, o.tokens, squadtiNum),
    squadtiBarra("Tempo", t.tempo_s || 0, o.tempo_s, squadtiSeg),
    squadtiBarra("Chamadas", t.chamadas || 0, o.chamadas, (n) => String(n)),
  ]);
}

function squadtiBannerEscalada(d, aud, podeEscrever) {
  const o = aud.orcamento || {};
  const campos = {};
  const linha = SQUADTI_EIXOS.map(([chave, rotulo, lo, hi]) => {
    const campo = el("input", { className: "squadti-campo squadti-campo-num", type: "number", min: String(lo), max: String(hi), step: "1",
      placeholder: "sem limite", "aria-label": `Novo teto de ${rotulo}` });
    if (o[chave]) campo.value = String(o[chave]);
    campos[chave] = campo;
    return el("label", { className: "squadti-mini" }, [`${rotulo}: `, campo]);
  });
  const botao = el("button", { className: "btn btn-primary btn-sm", textContent: "Continuar", disabled: !podeEscrever, onclick: async () => {
    const orcamento = {};
    for (const [chave, , lo, hi] of SQUADTI_EIXOS) {
      const bruto = campos[chave].value.trim();
      if (!bruto) { orcamento[chave] = null; continue; }
      const n = Number(bruto);
      if (!Number.isInteger(n) || n < lo || n > hi) { toast(`${chave}: use um inteiro entre ${lo} e ${hi}, ou deixe vazio para sem limite.`, "warning"); return; }
      orcamento[chave] = n;
    }
    botao.disabled = true;
    try {
      await api("POST", `/api/squadti/tarefas/${encodeURIComponent(d.tarefa)}/continuar`, { orcamento });
      toast("Retomada. A Squad segue de onde parou.", "success");
      await atualizarSquadti(true);
    } catch (e) { toast(`Não continuou: ${e.message}`, "error"); botao.disabled = !podeEscrever; }
  } });
  return el("div", { className: "squadti-faixa squadti-erro squadti-escalada", role: "alert" }, [
    el("strong", { textContent: "Escalada: a Squad parou e espera você. " }),
    el("p", { textContent: d.situacao.mensagem || (d.execucao && d.execucao.erro) || "" }),
    el("p", { className: "suave", textContent: "Se o motivo foi o orçamento, ajuste os tetos abaixo (cada campo vazio vira “sem limite”). Continuar não pula aprovações nem portões." }),
    el("div", { className: "squadti-linha-campos" }, linha),
    el("div", { className: "squadti-acoes" }, [botao]),
  ]);
}

function squadtiTabelaAuditoria(aud) {
  const cham = aud.chamadas || [];
  if (!cham.length) return [el("p", { className: "suave", textContent: "Nenhuma chamada ao modelo registrada ainda." })];
  return [el("div", { className: "squadti-rolagem" }, [el("table", { className: "squadti-tabela squadti-compacta" }, [
    el("thead", {}, [el("tr", {}, ["Nó", "Agente", "Modelo", "Tent.", "Tokens (ent/saída)", "Tempo", "prompt_sha"].map((h) => el("th", { textContent: h })))]),
    el("tbody", {}, cham.map((c) => el("tr", {}, [
      el("td", { textContent: c.no || "" }), el("td", { textContent: c.agente || "" }), el("td", { textContent: c.modelo || "" }),
      el("td", { textContent: String(c.tentativa ?? "") }),
      el("td", { textContent: `${c.tokens_entrada ?? 0} / ${c.tokens_saida ?? 0}` }),
      el("td", { textContent: c.duracao_s == null ? "" : squadtiSeg(c.duracao_s) }),
      el("td", { className: "squadti-mono", textContent: String(c.prompt_sha || "").slice(0, 16), title: String(c.prompt_sha || "") }),
    ]))),
  ])])];
}

async function baixarProvenienciaSquadti(tarefa) {
  try {
    const dados = await api("GET", `/api/squadti/tarefas/${encodeURIComponent(tarefa)}/proveniencia`);
    const url = URL.createObjectURL(new Blob([JSON.stringify(dados, null, 2)], { type: "application/json" }));
    const a = el("a", { href: url, download: `proveniencia-${tarefa}.json` });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  } catch (e) { toast(`Proveniência: ${e.message}`, "error"); }
}

async function abrirTarefaSquadti(tarefa, silencioso = false) {
  const base = `/api/squadti/tarefas/${encodeURIComponent(tarefa)}`;
  let d;
  let aud = { totais: {}, orcamento: {}, nos: [], chamadas: [] };
  let msgs = { mensagens: [], observacoes: [] };
  try {
    d = await api("GET", base);
  } catch (e) {
    if (!silencioso) toast(`Detalhe: ${e.message}`, "error");
    return;
  }
  // auditoria e conversa são acessórios: se falharem, o resto do detalhe continua útil
  const [a, m, sessao] = await Promise.all([
    api("GET", `${base}/auditoria`).catch(() => null),
    api("GET", `${base}/mensagens`).catch(() => null),
    squadtiSessao(),
  ]);
  if (a) aud = a;
  if (m) msgs = m;
  const alvo = $("squadti-detalhe");
  if (!alvo) return;
  const trocou = alvo.dataset.tarefa !== tarefa;
  squadtiAberta = tarefa;
  if (trocou) montarEsqueletoSquadti(alvo, tarefa);

  const ex = d.execucao;
  const rodando = Boolean(ex && ex.estado === "rodando");
  const est = d.situacao.estado;
  const escalada = est === "escalada";

  squadtiRegiao("sq-resumo", JSON.stringify([d.tarefa, est, rodando, d.situacao.mensagem, d.modelo, d.briefing, d.verificacoes, ex && ex.erro, ex && ex.fim]), () => {
    const v = d.verificacoes || {};
    const filhos = [
      el("h3", {}, [`Tarefa ${d.tarefa} `, squadtiBadge(est, rodando)]),
      el("p", { className: "suave", textContent: d.situacao.mensagem }),
      el("p", {}, [el("strong", { textContent: "Modelo: " }), d.modelo || "padrão do serviço", d.consentimento_nuvem ? "  (com consentimento de nuvem)" : ""]),
      el("p", {}, [el("strong", { textContent: "Doutrina: " }), `${d.doutrina.versao || "?"} · ${(d.doutrina.hash || "").slice(0, 12)}`]),
      el("p", {}, [el("strong", { textContent: "Briefing: " }), d.briefing || ""]),
    ];
    if (ex && ex.erro && ex.estado !== "escalada") filhos.push(el("div", { className: "squadti-faixa squadti-erro", textContent: `Última execução falhou: ${ex.erro}` }));
    filhos.push(el("div", { className: "squadti-verif" }, [["tests_passed", "Testes"], ["review_passed", "Revisão"], ["security_passed", "AppSec"], ["devops_passed", "DevOps"]].map(([k, r]) =>
      el("span", { className: `squadti-badge squadti-${v[k] ? "ok" : "info"}`, textContent: `${r}: ${v[k] ? "aprovado" : "pendente"}` }))));
    return filhos;
  });

  squadtiRegiao("sq-escalada", JSON.stringify([escalada, d.situacao.mensagem, aud.orcamento, sessao.escrita]), () =>
    escalada ? [squadtiBannerEscalada(d, aud, sessao.escrita)] : []);

  squadtiRegiao("sq-cockpit", JSON.stringify([aud, ex && ex.nos, rodando, d.falha_origem]), () => [
    el("h4", { textContent: "Trilha dos nós" }), squadtiTrilha(d, aud),
    ex && ex.nos && ex.nos.length ? el("p", { className: "suave", textContent: `Última execução (${ex.acao}) iniciada às ${squadtiHora(ex.inicio)}${ex.fim ? `, fim às ${squadtiHora(ex.fim)}` : ""}.` }) : null,
    el("h4", { textContent: "Consumo do orçamento" }), squadtiOrcamento(aud),
  ]);

  squadtiRegiao("sq-acoes", JSON.stringify([est, rodando, d.perguntas.length, sessao.escrita]), () => {
    const filhos = [];
    if (d.perguntas.length) {
      filhos.push(el("h4", { textContent: "Perguntas do analista" }));
      filhos.push(el("pre", { className: "squadti-pre", textContent: d.perguntas[d.perguntas.length - 1] }));
    }
    if (est === "aguardando_respostas" && !rodando) {
      filhos.push(el("p", { className: "suave", textContent: "Responda aqui ou na conversa com o CHEFE abaixo: as duas vias valem como resposta à entrevista." }));
      const caixa = el("textarea", { className: "squadti-texto", rows: "4", maxlength: "20000", placeholder: "Responda às perguntas acima", disabled: !sessao.escrita });
      filhos.push(caixa, el("button", { className: "btn btn-primary btn-sm", textContent: "Enviar respostas", disabled: !sessao.escrita, onclick: async () => {
        if (!caixa.value.trim()) { toast("Escreva a resposta.", "warning"); return; }
        try {
          await api("POST", `${base}/responder`, { resposta: caixa.value });
          toast("Resposta enviada.", "success");
          await atualizarSquadti(true);
        } catch (e) { toast(`Não enviou: ${e.message}`, "error"); }
      } }));
    }
    if (est === "aguardando_aprovacao_spec" && !rodando) {
      filhos.push(el("p", { className: "suave", textContent: "Leia a especificação nos arquivos abaixo antes de aprovar." }));
      filhos.push(el("button", { className: "btn btn-primary btn-sm", textContent: "Aprovar especificação", onclick: () => aprovarSquadti(tarefa, "aprovar") }));
    }
    if (est === "aguardando_aprovacao_release" && !rodando) {
      filhos.push(el("button", { className: "btn btn-primary btn-sm", textContent: "Aprovar release", onclick: () => aprovarSquadti(tarefa, "aprovar-release") }));
    }
    return filhos;
  });

  squadtiRegiao("sq-chat-historico", JSON.stringify([msgs.mensagens, msgs.observacoes]), () => {
    const bolhas = (msgs.mensagens || []).map((x) => el("div", { className: `squadti-bolha squadti-bolha-${x.de === "usuario" ? "usuario" : "chefe"}` }, [
      el("div", { className: "squadti-bolha-autor suave", textContent: `${x.de === "usuario" ? "Você" : "CHEFE"} · ${squadtiHora(x.em)}` }),
      el("div", { className: "squadti-bolha-texto", textContent: x.texto || "" }),
    ]));
    if (!bolhas.length) return [el("p", { className: "suave", textContent: "Nenhuma mensagem ainda." })];
    const obs = (msgs.observacoes || []).length ? [el("p", { className: "suave", textContent: `${msgs.observacoes.length} instrução(ões) /ajuste registrada(s) para as próximas fases.` })] : [];
    return [...bolhas, ...obs];
  });
  const hist = $("sq-chat-historico");
  if (hist && trocou) hist.scrollTop = hist.scrollHeight;
  atualizarChatSquadti(est === SQUADTI_PRONTO_PARA_ENTREVISTA, sessao.escrita);

  squadtiRegiao("sq-auditoria", JSON.stringify(aud.chamadas), () => [
    el("h4", { textContent: `Auditoria das chamadas (${(aud.chamadas || []).length})` }),
    ...squadtiTabelaAuditoria(aud),
  ]);

  squadtiRegiao("sq-arquivos", JSON.stringify(d.arquivos), () => {
    const visor = el("pre", { className: "squadti-pre", textContent: "Clique num arquivo para ler." });
    return [
      el("h4", { textContent: `Arquivos gerados (${d.arquivos.length})` }),
      el("div", { className: "squadti-arquivos" }, d.arquivos.map((arq) =>
        el("button", { className: "btn btn-outline btn-sm", textContent: arq, onclick: async () => {
          try {
            const r = await api("GET", `${base}/arquivo?caminho=${encodeURIComponent(arq)}`);
            visor.textContent = r.conteudo + (r.truncado ? "\n\n[arquivo truncado]" : "") + (r.linhas_omitidas ? `\n\n[${r.linhas_omitidas} linha(s) com possível segredo omitida(s)]` : "");
          } catch (e) { visor.textContent = `Não consegui ler: ${e.message}`; }
        } }))),
      visor,
    ];
  });

  // log ao vivo: o cursor vale por tarefa; ao terminar a execução faz-se uma última leitura
  if (squadtiLog.rodando && !rodando) squadtiLog.finalPendente = true;
  squadtiLog.rodando = rodando;
  iniciarLogSquadti(tarefa, trocou);
}

// Estrutura fixa do detalhe: o que o usuário digita (chat) e o log não são recriados a cada atualização.
function montarEsqueletoSquadti(alvo, tarefa) {
  alvo.dataset.tarefa = tarefa;
  const texto = el("textarea", { className: "squadti-texto", id: "sq-chat-texto", rows: "2", maxlength: String(SQUADTI_MAX_MENSAGEM),
    placeholder: "Fale com o CHEFE (Enter envia, Shift+Enter quebra a linha)", "aria-label": "Mensagem ao CHEFE" });
  const enviar = el("button", { className: "btn btn-primary btn-sm", id: "sq-chat-enviar", textContent: "Enviar" });
  const mandar = async () => {
    const t = texto.value.trim();
    if (!t || enviar.disabled) return;
    texto.disabled = true;
    enviar.disabled = true;
    $("sq-chat-estado").textContent = "O CHEFE está respondendo… (pode levar até 2 minutos)";
    try {
      await api("POST", `/api/squadti/tarefas/${encodeURIComponent(tarefa)}/mensagem`, { texto: t });
      texto.value = "";
      toast("Mensagem enviada ao CHEFE.", "success");
    } catch (e) { toast(`CHEFE: ${e.message}`, "error"); }
    texto.disabled = false;
    enviar.disabled = false;
    $("sq-chat-estado").textContent = "";
    texto.focus();
    if (squadtiAberta === tarefa) await abrirTarefaSquadti(tarefa, true);
    const hist = $("sq-chat-historico");
    if (hist) hist.scrollTop = hist.scrollHeight;
  };
  enviar.addEventListener("click", mandar);
  texto.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); mandar(); } });

  const log = el("pre", { className: "squadti-pre squadti-log", id: "sq-log", "aria-live": "off", textContent: "Sem eventos desta execução." });
  alvo.replaceChildren(
    el("div", { id: "sq-resumo" }), el("div", { id: "sq-escalada" }),
    el("div", { className: "squadti-acoes" }, [
      el("button", { className: "btn btn-outline btn-sm", textContent: "Baixar proveniência (JSON)", onclick: () => baixarProvenienciaSquadti(tarefa) }),
      el("button", { className: "btn btn-outline btn-sm", textContent: "Fechar", onclick: fecharDetalheSquadti }),
    ]),
    el("div", { id: "sq-cockpit" }),
    el("h4", { textContent: "Log ao vivo" }), log,
    el("h4", { textContent: "Conversa com o CHEFE" }),
    el("p", { className: "suave", id: "sq-chat-dica", textContent: "O CHEFE é o seu canal único com a Squad. Escreva “status” para um resumo, ou “/ajuste <texto>” para registrar uma instrução para as próximas fases (ela não altera aprovações, portões nem configuração)." }),
    el("div", { className: "squadti-chat", id: "sq-chat-historico" }),
    el("div", { className: "squadti-faixa squadti-aviso", id: "sq-chat-entrevista", style: "display:none", textContent: "Esta tarefa aguarda as respostas da entrevista: a mensagem que você enviar aqui vale como resposta ao analista e retoma a execução." }),
    texto, el("div", { className: "squadti-acoes" }, [enviar, el("span", { className: "suave", id: "sq-chat-estado", "aria-live": "polite" })]),
    el("div", { id: "sq-acoes" }), el("div", { id: "sq-auditoria" }), el("div", { id: "sq-arquivos" }),
  );
  Object.assign(squadtiLog, { tarefa: null, cursor: 0, linhas: [], rodando: false, finalPendente: false });
}

function atualizarChatSquadti(entrevista, podeEscrever) {
  const aviso = $("sq-chat-entrevista");
  if (aviso) aviso.style.display = entrevista ? "" : "none";
  const texto = $("sq-chat-texto");
  if (!texto) return;
  const ocupado = $("sq-chat-estado") && $("sq-chat-estado").textContent !== "";
  if (!ocupado) {
    texto.disabled = !podeEscrever;
    $("sq-chat-enviar").disabled = !podeEscrever;
  }
  texto.placeholder = !podeEscrever ? "Seu papel só permite ler a conversa"
    : entrevista ? "Responda às perguntas do analista (vale como resposta). Enter envia" : "Fale com o CHEFE (Enter envia, Shift+Enter quebra a linha)";
}

// ---------------------------------------------------------------- log ao vivo (polling de 2 s enquanto há execução)
function iniciarLogSquadti(tarefa, trocou) {
  if (trocou || squadtiLog.tarefa !== tarefa) {
    Object.assign(squadtiLog, { tarefa, cursor: 0, linhas: [], finalPendente: false });
    lerLogSquadti();  // histórico em memória da API, mesmo sem execução em curso
  }
  if (!squadtiLogTimer) {
    squadtiLogTimer = setInterval(() => {
      if (abaAtivaAtual !== "squadti" || squadtiAba !== "tarefas" || !squadtiAberta) return;
      if (squadtiLog.rodando || squadtiLog.finalPendente) lerLogSquadti();
    }, 2000);
  }
}

async function lerLogSquadti() {
  const tarefa = squadtiLog.tarefa;
  if (!tarefa || squadtiLog.ocupado) return;
  squadtiLog.ocupado = true;
  try {
    const r = await api("GET", `/api/squadti/tarefas/${encodeURIComponent(tarefa)}/log?desde=${squadtiLog.cursor}`);
    if (squadtiLog.tarefa !== tarefa) return;  // o usuário trocou de tarefa no meio do pedido
    if (!squadtiLog.rodando) squadtiLog.finalPendente = false;
    squadtiLog.cursor = Number.isInteger(r.proximo) ? r.proximo : squadtiLog.cursor;
    if ((r.eventos || []).length) {
      for (const e of r.eventos) squadtiLog.linhas.push(`[${squadtiHora(e.em)}] ${e.texto}`);
      if (squadtiLog.linhas.length > SQUADTI_MAX_LOG) squadtiLog.linhas.splice(0, squadtiLog.linhas.length - SQUADTI_MAX_LOG);
      const pre = $("sq-log");
      if (pre) {
        pre.textContent = squadtiLog.linhas.join("\n");
        pre.scrollTop = pre.scrollHeight;
      }
    }
  } catch (e) { /* o próximo ciclo tenta de novo; falha de log não derruba o cockpit */ }
  finally { squadtiLog.ocupado = false; }
}

// ---------------------------------------------------------------- aba Agentes
async function carregarAgentesSquadti() {
  const raiz = $("squadti-painel-agentes");
  const [sessao] = await Promise.all([squadtiSessao()]);
  let cfg;
  try {
    cfg = await api("GET", "/api/squadti/agentes");
  } catch (e) {
    raiz.replaceChildren(el("div", { className: "squadti-faixa squadti-erro", textContent: `Não consegui ler a configuração dos agentes: ${e.message}` }));
    return;
  }
  const admin = sessao.admin;
  const tocados = new Set();
  const marcar = (chave) => () => { tocados.add(chave); };
  const num = (valor, attrs) => el("input", { className: "squadti-campo squadti-campo-num", type: "number", disabled: !admin, value: valor == null ? "" : String(valor), ...attrs });
  const val = cfg.validacao || {};
  const slo = val.slo || {};

  // tabela por agente
  const linhas = SQUADTI_AGENTES.map((nome) => {
    const atual = (cfg.agentes || {})[nome] || {};
    const sel = el("select", { className: "squadti-campo", disabled: !admin, "aria-label": `Perfil de ${nome}` }, [
      el("option", { value: "", textContent: "(o da tarefa)" }),
      ...SQUADTI_PERFIS.map(([v, r]) => el("option", { value: v, textContent: r })),
    ]);
    if (atual.perfil && !SQUADTI_PERFIS.some((p) => p[0] === atual.perfil)) sel.append(el("option", { value: atual.perfil, textContent: `${atual.perfil} (fora do painel)`, disabled: true }));
    sel.value = atual.perfil || "";
    const temp = num(atual.temperatura ?? 0.1, { min: "0", max: "1.5", step: "0.05", "aria-label": `Temperatura de ${nome}` });
    const maxTok = num(atual.max_tokens, { min: "256", max: "32000", step: "1", placeholder: "padrão", "aria-label": `Máximo de tokens de ${nome}` });
    const sai = el("span", { className: "squadti-badge squadti-aviso", textContent: "pode sair da máquina", style: "display:none" });
    const mostra = () => { const p = SQUADTI_PERFIS.find((x) => x[0] === sel.value); sai.style.display = p && p[2] ? "" : "none"; };
    sel.addEventListener("change", () => { mostra(); tocados.add(nome); });
    temp.addEventListener("input", () => tocados.add(nome));
    maxTok.addEventListener("input", () => tocados.add(nome));
    mostra();
    return { nome, sel, temp, maxTok, linha: el("tr", {}, [
      el("td", {}, [el("strong", { textContent: nome })]), el("td", {}, [sel, sai]), el("td", {}, [temp]), el("td", {}, [maxTok]),
    ]) };
  });

  const revisao = el("select", { className: "squadti-campo", disabled: !admin, "aria-label": "Modo de revisão" }, [
    el("option", { value: "simples", textContent: "Simples (um revisor)" }), el("option", { value: "dupla", textContent: "Dupla (dois revisores independentes)" }),
  ]);
  revisao.value = (cfg.revisao || {}).modo || "simples";

  const opcoes = (valores, rotulos) => valores.map((v, i) => el("option", { value: v, textContent: rotulos[i] }));
  const vModo = el("select", { className: "squadti-campo", disabled: !admin, "aria-label": "Modo da validação em execução" }, opcoes(["auto", "sempre", "nunca"], ["Automático (quando o projeto sobe)", "Sempre", "Nunca"]));
  const vCarga = el("select", { className: "squadti-campo", disabled: !admin, "aria-label": "Carga da validação" }, opcoes(["escalado", "completo", "nunca"], ["Escalada (leve, cresce se preciso)", "Completa", "Nunca"]));
  vModo.value = val.modo || "auto";
  vCarga.value = val.carga || "escalado";
  const vP95 = num(slo.p95_ms, { min: "1", step: "1", placeholder: "p95 (ms)", "aria-label": "SLO p95 em ms" });
  const vP99 = num(slo.p99_ms, { min: "1", step: "1", placeholder: "p99 (ms)", "aria-label": "SLO p99 em ms" });
  const vErro = num(slo.erro_max === undefined ? undefined : slo.erro_max * 100, { min: "0", max: "100", step: "0.1", placeholder: "erro (%)", "aria-label": "SLO de taxa de erro em %" });
  const vMacaco = num(val.ui_segundos, { min: "10", max: "600", step: "1", placeholder: "segundos (10 a 600)", "aria-label": "Segundos do macaco de UI" });
  for (const campo of [vModo, vCarga, vP95, vP99, vErro, vMacaco]) { campo.addEventListener("input", marcar("validacao")); campo.addEventListener("change", marcar("validacao")); }

  const orc = cfg.orcamento || {};
  const campoOrc = {};
  const linhaOrc = SQUADTI_EIXOS.map(([chave, rotulo, lo, hi]) => {
    campoOrc[chave] = num(orc[chave], { min: String(lo), max: String(hi), step: "1", placeholder: "sem limite", "aria-label": `Orçamento de ${rotulo}` });
    return el("label", { className: "squadti-mini" }, [`${rotulo}: `, campoOrc[chave]]);
  });

  const salvar = el("button", { className: "btn btn-primary btn-sm", textContent: "Salvar", disabled: !admin,
    title: admin ? "" : "Só o administrador salva a configuração dos agentes", onclick: async () => {
      const inteiro = (campo, rotulo, lo, hi) => {
        const bruto = campo.value.trim();
        if (!bruto) return null;
        const n = Number(bruto);
        if (!Number.isInteger(n) || n < lo || n > hi) throw new Error(`${rotulo}: use um inteiro entre ${lo} e ${hi}`);
        return n;
      };
      let corpo;
      try {
        const agentes = {};
        for (const { nome, sel, temp, maxTok } of linhas) {
          if (!(nome in (cfg.agentes || {})) && !tocados.has(nome)) continue;  // agente que esta versão da Squad não conhece só vai se você o alterou
          const t = Number(temp.value);
          if (temp.value.trim() === "" || !(t >= 0 && t <= 1.5)) throw new Error(`${nome}: temperatura entre 0 e 1,5`);
          agentes[nome] = { perfil: sel.value || null, temperatura: t, max_tokens: inteiro(maxTok, `${nome}: max tokens`, 256, 32000) };
        }
        const orcamento = {};
        for (const [chave, rotulo, lo, hi] of SQUADTI_EIXOS) orcamento[chave] = inteiro(campoOrc[chave], rotulo, lo, hi);
        corpo = { agentes, revisao: { modo: revisao.value }, orcamento };
        if (cfg.validacao !== undefined || tocados.has("validacao")) {
          const dec = (campo, rotulo) => { const b = campo.value.trim(); if (!b) return null; const n = Number(b); if (!(n >= 0)) throw new Error(`${rotulo}: número positivo`); return n; };
          const slo = {};  // campo vazio = não enviar (a Squad usa o padrão); null seria recusado
          for (const [chave, campo, rotulo, f] of [["p95_ms", vP95, "p95", 1], ["p99_ms", vP99, "p99", 1], ["erro_max", vErro, "erro %", 0.01]]) { const n = dec(campo, rotulo); if (n !== null) slo[chave] = n * f; }
          corpo.validacao = { modo: vModo.value, carga: vCarga.value, slo };
          const ui = dec(vMacaco, "macaco de UI"); if (ui !== null) corpo.validacao.ui_segundos = Math.round(ui);
        }
      } catch (e) { toast(e.message, "warning"); return; }
      salvar.disabled = true;
      try {
        await api("POST", "/api/squadti/agentes", corpo);
        toast("Configuração dos agentes salva. Vale para as próximas tarefas.", "success");
        await carregarAgentesSquadti();
      } catch (e) { toast(`Não salvou: ${e.message}`, "error"); salvar.disabled = !admin; }
    } });

  raiz.replaceChildren(
    el("div", { className: "squadti-faixa squadti-aviso" }, [
      el("strong", { textContent: "Privacidade: " }),
      "um perfil que pode sair da máquina (tudo menos “Local estrito”) só vale em tarefa iniciada com consentimento de nuvem explícito. A configuração é copiada para a tarefa ao iniciar: editar aqui não muda tarefas em andamento.",
    ]),
    !admin ? el("p", { className: "suave", textContent: "Você pode ver a configuração, mas só o administrador a altera." }) : null,
    el("section", { className: "squadti-bloco" }, [
      el("h3", { textContent: "Modelo por agente" }),
      el("div", { className: "squadti-rolagem" }, [el("table", { className: "squadti-tabela" }, [
        el("thead", {}, [el("tr", {}, ["Agente", "Perfil de modelo", "Temperatura", "Máx. tokens"].map((h) => el("th", { textContent: h })))]),
        el("tbody", {}, linhas.map((l) => l.linha)),
      ])]),
    ]),
    el("section", { className: "squadti-bloco" }, [
      el("h3", { textContent: "Revisão" }), el("label", { className: "squadti-mini" }, ["Modo: ", revisao]),
    ]),
    el("section", { className: "squadti-bloco" }, [
      el("h3", { textContent: "Validação em execução" }),
      el("div", { className: "squadti-linha-campos" }, [
        el("label", { className: "squadti-mini" }, ["Modo: ", vModo]), el("label", { className: "squadti-mini" }, ["Carga: ", vCarga]),
      ]),
      el("p", { className: "suave", textContent: "SLO a respeitar na carga (vazio = sem meta) e duração do macaco de UI:" }),
      el("div", { className: "squadti-linha-campos" }, [
        el("label", { className: "squadti-mini" }, ["p95 (ms): ", vP95]), el("label", { className: "squadti-mini" }, ["p99 (ms): ", vP99]),
        el("label", { className: "squadti-mini" }, ["Erro (%): ", vErro]), el("label", { className: "squadti-mini" }, ["Macaco de UI (s): ", vMacaco]),
      ]),
    ]),
    el("section", { className: "squadti-bloco" }, [
      el("h3", { textContent: "Orçamento por tarefa" }),
      el("p", { className: "suave", textContent: "Ao atingir qualquer teto a Squad escala para você. Campo vazio = sem limite." }),
      el("div", { className: "squadti-linha-campos" }, linhaOrc),
    ]),
    el("div", { className: "squadti-acoes" }, [salvar]),
  );
}

// ---------------------------------------------------------------- nova tarefa
function abrirNovaTarefaSquadti() {
  const id = el("input", { className: "squadti-campo", maxlength: "64", placeholder: "TASK-001", autocomplete: "off" });
  const brief = el("textarea", { className: "squadti-texto", rows: "6", maxlength: "20000", placeholder: "Descreva o que a Squad deve construir (projeto novo)" });
  const stack = el("select", { className: "squadti-campo", "aria-label": "Stack" }, [
    el("option", { value: "", textContent: "Automático (o CHEFE decide pelo briefing)" }),
    el("option", { value: "dotnet", textContent: ".NET" }), el("option", { value: "python", textContent: "Python" }),
  ]);
  const perfil = el("select", { className: "squadti-campo" }, SQUADTI_PERFIS.map(([v, r]) => el("option", { value: v, textContent: r })));
  const consent = el("input", { type: "checkbox" });
  const aviso = el("label", { className: "squadti-consent", style: "display:none" }, [consent,
    " Entendo que o código, o esquema e o briefing deste projeto podem ser enviados a provedores de nuvem."]);
  perfil.addEventListener("change", () => { aviso.style.display = SQUADTI_PERFIS.find((p) => p[0] === perfil.value)[2] ? "" : "none"; if (aviso.style.display === "none") consent.checked = false; });
  const campos = {};
  const orc = el("details", { className: "squadti-detalhes" }, [
    el("summary", { textContent: "Orçamento desta tarefa (opcional)" }),
    el("p", { className: "suave", textContent: "Campo vazio = o padrão da aba Agentes." }),
    ...SQUADTI_EIXOS.map(([chave, rotulo, lo, hi]) => {
      campos[chave] = el("input", { className: "squadti-campo", type: "number", min: String(lo), max: String(hi), step: "1", placeholder: "padrão" });
      return el("label", { className: "squadti-mini" }, [`${rotulo}: `, campos[chave]]);
    }),
  ]);
  const fundo = el("div", { className: "squadti-fundo" });
  const fechar = () => fundo.remove();
  const enviar = el("button", { className: "btn btn-primary btn-sm", textContent: "Iniciar", onclick: async () => {
    const corpo = { tarefa: id.value.trim(), briefing: brief.value, perfil: perfil.value, consentimento_nuvem: consent.checked };
    if (stack.value) corpo.stack = stack.value;
    const orcamento = {};
    for (const [chave, rotulo, lo, hi] of SQUADTI_EIXOS) {
      const bruto = campos[chave].value.trim();
      if (!bruto) continue;
      const n = Number(bruto);
      if (!Number.isInteger(n) || n < lo || n > hi) { toast(`${rotulo}: use um inteiro entre ${lo} e ${hi}.`, "warning"); return; }
      orcamento[chave] = n;
    }
    if (Object.keys(orcamento).length) corpo.orcamento = orcamento;
    try {
      await api("POST", "/api/squadti/tarefas", corpo);
      toast("Tarefa iniciada.", "success");
      squadtiAberta = corpo.tarefa;
      fechar();
      squadtiAba = "tarefas";
      if ($("squadti-aba-tarefas")) aplicarAbaSquadti();
    } catch (e) { toast(`Não iniciou: ${e.message}`, "error"); }
  } });
  fundo.append(el("div", { className: "squadti-modal", role: "dialog", "aria-modal": "true", "aria-label": "Nova tarefa" }, [
    el("h3", { textContent: "Nova tarefa da Squad" }),
    el("label", { textContent: "Identificador (letras, números, . _ -)" }), id,
    el("label", { textContent: "Briefing" }), brief,
    el("label", { textContent: "Stack" }), stack,
    el("label", { textContent: "Onde o modelo roda" }), perfil, aviso,
    orc,
    el("div", { className: "squadti-acoes" }, [el("button", { className: "btn btn-outline btn-sm", textContent: "Cancelar", onclick: fechar }), enviar]),
  ]));
  document.body.appendChild(fundo);
  id.focus();
}

$("btn-squadti-nova").addEventListener("click", abrirNovaTarefaSquadti);
$("btn-squadti-atualizar").addEventListener("click", () => carregarSquadti());

// Acesso direto por #squadti: o painel.js já ativou a aba antes deste arquivo existir.
if (abaAtivaAtual === "squadti") carregarSquadti();
