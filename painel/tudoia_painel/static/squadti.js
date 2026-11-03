"use strict";
// Menu SquadTI: inicia, acompanha e aprova as tarefas da Squad. Carregado depois do painel.js (usa $, el, api, toast, icone).
// Todo texto que vem da API entra por textContent: briefing, perguntas e arquivos são conteúdo de modelo, nunca marcação.

const SQUADTI_ROTULOS = {
  aguardando_respostas: ["Aguardando suas respostas", "aviso"],
  aguardando_aprovacao_spec: ["Aprovar especificação", "aviso"],
  aguardando_aprovacao_release: ["Aprovar release", "aviso"],
  em_fase: ["Em andamento", "info"],
  concluida: ["Concluída", "ok"],
  bloqueada: ["Bloqueada", "erro"],
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
];
let squadtiTimer = null;
let squadtiAberta = null;

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
  await atualizarSquadti();
  clearInterval(squadtiTimer);
  squadtiTimer = setInterval(() => {
    if (abaAtivaAtual !== "squadti") { clearInterval(squadtiTimer); return; }
    atualizarSquadti(true);
  }, 5000);
}

async function atualizarSquadti(silencioso = false) {
  const raiz = $("squadti-conteudo");
  let lista;
  try {
    lista = (await api("GET", "/api/squadti/tarefas")).tarefas;
  } catch (e) {
    if (!silencioso) toast(`SquadTI: ${e.message}`, "error");
    return;
  }
  const rodando = (t) => t.execucao && t.execucao.estado === "rodando";
  const pendentes = lista.filter((t) => !rodando(t) && ["aguardando_respostas", "aguardando_aprovacao_spec", "aguardando_aprovacao_release"].includes(t.situacao.estado));

  const caixa = el("section", { className: "squadti-bloco" }, [
    el("h3", { textContent: `Precisa de você (${pendentes.length})` }),
    pendentes.length ? el("div", { className: "squadti-cartoes" }, pendentes.map(squadtiCartao))
      : el("p", { className: "suave", textContent: "Nenhuma tarefa esperando resposta ou aprovação." }),
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

  const detalhe = el("section", { className: "squadti-bloco", id: "squadti-detalhe" });
  raiz.replaceChildren(caixa, tabela, detalhe);
  if (squadtiAberta && lista.some((t) => t.tarefa === squadtiAberta)) await abrirTarefaSquadti(squadtiAberta, true);
  else squadtiAberta = null;
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

async function abrirTarefaSquadti(tarefa, silencioso = false) {
  let d;
  try {
    d = await api("GET", `/api/squadti/tarefas/${encodeURIComponent(tarefa)}`);
  } catch (e) {
    if (!silencioso) toast(`Detalhe: ${e.message}`, "error");
    return;
  }
  squadtiAberta = tarefa;
  const alvo = $("squadti-detalhe");
  if (!alvo) return;
  const ex = d.execucao;
  const rodando = ex && ex.estado === "rodando";
  const filhos = [
    el("h3", {}, [`Tarefa ${d.tarefa} `, squadtiBadge(d.situacao.estado, rodando)]),
    el("p", { className: "suave", textContent: d.situacao.mensagem }),
    el("p", {}, [el("strong", { textContent: "Modelo: " }), d.modelo || "padrão do serviço", d.consentimento_nuvem ? "  (com consentimento de nuvem)" : ""]),
    el("p", {}, [el("strong", { textContent: "Doutrina: " }), `${d.doutrina.versao || "?"} · ${(d.doutrina.hash || "").slice(0, 12)}`]),
    el("p", {}, [el("strong", { textContent: "Briefing: " }), d.briefing || ""]),
  ];

  if (ex && ex.erro) filhos.push(el("div", { className: "squadti-faixa squadti-erro", textContent: `Última execução falhou: ${ex.erro}` }));

  // linha do tempo dos nós
  const feitos = new Set((ex ? ex.nos : []).map((n) => n.no));
  filhos.push(el("div", { className: "squadti-trilha" }, SQUADTI_NOS.map((n) =>
    el("span", { className: `squadti-no ${feitos.has(n) ? "feito" : ""}`, textContent: n.replace("_", " ") }))));
  if (ex && ex.nos.length) filhos.push(el("p", { className: "suave", textContent: `Última execução (${ex.acao}) iniciada às ${squadtiHora(ex.inicio)}${ex.fim ? `, fim às ${squadtiHora(ex.fim)}` : ""}.` }));

  // verificações
  const v = d.verificacoes || {};
  filhos.push(el("div", { className: "squadti-verif" }, [["tests_passed", "Testes"], ["review_passed", "Revisão"], ["security_passed", "AppSec"], ["devops_passed", "DevOps"]].map(([k, r]) =>
    el("span", { className: `squadti-badge squadti-${v[k] ? "ok" : "info"}`, textContent: `${r}: ${v[k] ? "aprovado" : "pendente"}` }))));

  // perguntas e resposta
  const est = d.situacao.estado;
  if (d.perguntas.length) {
    filhos.push(el("h4", { textContent: "Perguntas do analista" }));
    filhos.push(el("pre", { className: "squadti-pre", textContent: d.perguntas[d.perguntas.length - 1] }));
  }
  if (est === "aguardando_respostas" && !rodando) {
    const caixa = el("textarea", { className: "squadti-texto", rows: "4", maxlength: "20000", placeholder: "Responda às perguntas acima" });
    filhos.push(caixa, el("button", { className: "btn btn-primary btn-sm", textContent: "Enviar respostas", onclick: async () => {
      if (!caixa.value.trim()) { toast("Escreva a resposta.", "warning"); return; }
      try {
        await api("POST", `/api/squadti/tarefas/${encodeURIComponent(tarefa)}/responder`, { resposta: caixa.value });
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

  // arquivos
  filhos.push(el("h4", { textContent: `Arquivos gerados (${d.arquivos.length})` }));
  const visor = el("pre", { className: "squadti-pre", id: "squadti-visor", textContent: "Clique num arquivo para ler." });
  filhos.push(el("div", { className: "squadti-arquivos" }, d.arquivos.map((a) =>
    el("button", { className: "btn btn-outline btn-sm", textContent: a, onclick: async () => {
      try {
        const r = await api("GET", `/api/squadti/tarefas/${encodeURIComponent(tarefa)}/arquivo?caminho=${encodeURIComponent(a)}`);
        visor.textContent = r.conteudo + (r.truncado ? "\n\n[arquivo truncado]" : "") + (r.linhas_omitidas ? `\n\n[${r.linhas_omitidas} linha(s) com possível segredo omitida(s)]` : "");
      } catch (e) { visor.textContent = `Não consegui ler: ${e.message}`; }
    } }))), visor);

  alvo.replaceChildren(...filhos);
}

function abrirNovaTarefaSquadti() {
  const id = el("input", { className: "squadti-campo", maxlength: "64", placeholder: "TASK-001", autocomplete: "off" });
  const brief = el("textarea", { className: "squadti-texto", rows: "6", maxlength: "20000", placeholder: "Descreva o que a Squad deve construir (projeto novo)" });
  const perfil = el("select", { className: "squadti-campo" }, SQUADTI_PERFIS.map(([v, r]) => el("option", { value: v, textContent: r })));
  const consent = el("input", { type: "checkbox" });
  const aviso = el("label", { className: "squadti-consent", style: "display:none" }, [consent,
    " Entendo que o código, o esquema e o briefing deste projeto podem ser enviados a provedores de nuvem."]);
  perfil.addEventListener("change", () => { aviso.style.display = SQUADTI_PERFIS.find((p) => p[0] === perfil.value)[2] ? "" : "none"; if (aviso.style.display === "none") consent.checked = false; });
  const fundo = el("div", { className: "squadti-fundo" });
  const fechar = () => fundo.remove();
  const enviar = el("button", { className: "btn btn-primary btn-sm", textContent: "Iniciar", onclick: async () => {
    try {
      await api("POST", "/api/squadti/tarefas", { tarefa: id.value.trim(), briefing: brief.value, perfil: perfil.value, consentimento_nuvem: consent.checked });
      toast("Tarefa iniciada.", "success");
      squadtiAberta = id.value.trim();
      fechar();
      await atualizarSquadti(true);
    } catch (e) { toast(`Não iniciou: ${e.message}`, "error"); }
  } });
  fundo.append(el("div", { className: "squadti-modal", role: "dialog", "aria-modal": "true", "aria-label": "Nova tarefa" }, [
    el("h3", { textContent: "Nova tarefa da Squad" }),
    el("label", { textContent: "Identificador (letras, números, . _ -)" }), id,
    el("label", { textContent: "Briefing" }), brief,
    el("label", { textContent: "Onde o modelo roda" }), perfil, aviso,
    el("div", { className: "squadti-acoes" }, [el("button", { className: "btn btn-outline btn-sm", textContent: "Cancelar", onclick: fechar }), enviar]),
  ]));
  document.body.appendChild(fundo);
  id.focus();
}

$("btn-squadti-nova").addEventListener("click", abrirNovaTarefaSquadti);
$("btn-squadti-atualizar").addEventListener("click", () => carregarSquadti());

// Acesso direto por #squadti: o painel.js já ativou a aba antes deste arquivo existir.
if (abaAtivaAtual === "squadti") carregarSquadti();
