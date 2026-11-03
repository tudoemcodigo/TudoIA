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

// Ícones de linha Lucide (ISC, v1.64.0, ver docs/terceiros.md), no mesmo traço dos SVG do index.html.
// Cada ícone é uma lista de desenhos: texto = <path d>, [tag, atributos] = outro elemento. Montado pelo DOM.
const ICONES = {
  olho: ["M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0",
         "M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0"],
  olhoFechado: ["M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49",
                "M14.084 14.158a3 3 0 0 1-4.242-4.242",
                "M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143",
                "m2 2 20 20"],
  "activity": ["M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"],
  "arrowDown": ["M12 5v14","m19 12-7 7-7-7"],
  "arrowRight": ["M5 12h14","m12 5 7 7-7 7"],
  "arrowUp": ["m5 12 7-7 7 7","M12 19V5"],
  "bot": ["M12 8V4H8",["rect",{"width":"16","height":"12","x":"4","y":"8","rx":"2"}],"M2 14h2","M20 14h2","M15 13v2","M9 13v2"],
  "brain": ["M12 18V5","M15 13a4.17 4.17 0 01-3-4 4.17 4.17 0 01-3 4","M17.707 6.294A3 3 0 1012 5a3 3 0 10-5.707 1.294","M17.996 5.125a4 4 0 012.526 5.77","M18 18a4 4 0 002-7.465","M19.967 17.482a4 4 0 11-7.967.517 4 4 0 11-7.967-.517","M6 18a4 4 0 01-2-7.465","M6.004 5.125a4 4 0 00-2.526 5.77"],
  "chartColumn": ["M3 3v16a2 2 0 0 0 2 2h16","M18 17V9","M13 17V5","M8 17v-3"],
  "check": ["M20 6 9 17l-5-5"],
  "chevronDown": ["m6 9 6 6 6-6"],
  "chevronRight": ["m9 18 6-6-6-6"],
  "chevronUp": ["m18 15-6-6-6 6"],
  "circleAlert": [["circle",{"cx":"12","cy":"12","r":"10"}],["line",{"x1":"12","x2":"12","y1":"8","y2":"12"}],["line",{"x1":"12","x2":"12.01","y1":"16","y2":"16"}]],
  "circleCheck": [["circle",{"cx":"12","cy":"12","r":"10"}],"m16 9-5.5 5.5L8 12"],
  "circleDot": [["circle",{"cx":"12","cy":"12","r":"1"}],["circle",{"cx":"12","cy":"12","r":"10"}]],
  "circleX": [["circle",{"cx":"12","cy":"12","r":"10"}],"m15 9-6 6","m9 9 6 6"],
  "clock": [["circle",{"cx":"12","cy":"12","r":"10"}],"M12 6v6l4 2"],
  "cloud": ["M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"],
  "coins": ["M13.744 17.736a6 6 0 1 1-7.48-7.48","M15 6h1v4","m6.134 14.768.866-.5 2 3.464",["circle",{"cx":"16","cy":"8","r":"6"}]],
  "copy": [["rect",{"width":"14","height":"14","x":"8","y":"8","rx":"2","ry":"2"}],"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"],
  "cpu": ["M12 20v2","M12 2v2","M17 20v2","M17 2v2","M2 12h2","M2 17h2","M2 7h2","M20 12h2","M20 17h2","M20 7h2","M7 20v2","M7 2v2",["rect",{"x":"4","y":"4","width":"16","height":"16","rx":"2"}],["rect",{"x":"8","y":"8","width":"8","height":"8","rx":"1"}]],
  "database": [["ellipse",{"cx":"12","cy":"5","rx":"9","ry":"3"}],"M3 5V19A9 3 0 0 0 21 19V5","M3 12A9 3 0 0 0 21 12"],
  "download": ["M12 15V3","M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4","m7 10 5 5 5-5"],
  "ellipsis": [["circle",{"cx":"12","cy":"12","r":"1"}],["circle",{"cx":"19","cy":"12","r":"1"}],["circle",{"cx":"5","cy":"12","r":"1"}]],
  "externalLink": ["M15 3h6v6","M10 14 21 3","M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"],
  "fileText": ["M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z","M14 2v5a1 1 0 0 0 1 1h5","M10 9H8","M16 13H8","M16 17H8"],
  "folder": ["M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"],
  "gauge": ["m12 14 4-4","M3.34 19a10 10 0 1 1 17.32 0"],
  "globe": [["circle",{"cx":"12","cy":"12","r":"10"}],"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20","M2 12h20"],
  "hardDrive": ["M10 16h.01","M2.212 11.577a2 2 0 0 0-.212.896V18a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5.527a2 2 0 0 0-.212-.896L18.55 5.11A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z","M21.946 12.013H2.054","M6 16h.01"],
  "house": ["M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8","M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  "image": [["rect",{"width":"18","height":"18","x":"3","y":"3","rx":"2","ry":"2"}],["circle",{"cx":"9","cy":"9","r":"2"}],"m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"],
  "info": [["circle",{"cx":"12","cy":"12","r":"10"}],"M12 16v-4","M12 8h.01"],
  "keyRound": ["M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z",["circle",{"cx":"16.5","cy":"7.5","r":".5","fill":"currentColor"}]],
  "layers": ["M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z","M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12","M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17"],
  "layoutDashboard": [["rect",{"width":"7","height":"9","x":"3","y":"3","rx":"1"}],["rect",{"width":"7","height":"5","x":"14","y":"3","rx":"1"}],["rect",{"width":"7","height":"9","x":"14","y":"12","rx":"1"}],["rect",{"width":"7","height":"5","x":"3","y":"16","rx":"1"}]],
  "link": ["M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71","M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"],
  "list": ["M3 5h.01","M3 12h.01","M3 19h.01","M8 5h13","M8 12h13","M8 19h13"],
  "lock": [["rect",{"width":"18","height":"11","x":"3","y":"11","rx":"2","ry":"2"}],"M7 11V7a5 5 0 0 1 10 0v4"],
  "messageSquare": ["M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z"],
  "monitor": [["rect",{"width":"20","height":"14","x":"2","y":"3","rx":"2"}],["line",{"x1":"8","x2":"16","y1":"21","y2":"21"}],["line",{"x1":"12","x2":"12","y1":"17","y2":"21"}]],
  "music": ["M21 16V3a1 1 0 0 0-1.28-.96l-10 2.917a1 1 0 0 0-.72.96V19",["circle",{"cx":"18","cy":"16","r":"3"}],["circle",{"cx":"6","cy":"19","r":"3"}]],
  "pause": [["rect",{"x":"14","y":"3","width":"5","height":"18","rx":"1"}],["rect",{"x":"5","y":"3","width":"5","height":"18","rx":"1"}]],
  "pencil": ["M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z","m15 5 4 4"],
  "play": ["M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"],
  "plug": ["M12 22v-5","M15 8V2","M17 8a1 1 0 0 1 1 1v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1z","M9 8V2"],
  "plus": ["M5 12h14","M12 5v14"],
  "power": ["M12 2v10","M18.4 6.6a9 9 0 1 1-12.77.04"],
  "refreshCw": ["M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8","M21 3v5h-5","M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16","M8 16H3v5"],
  "rocket": ["M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5","M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09","M9 12a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.4 22.4 0 0 1-4 2z","M9 12H4s.55-3.03 2-4c1.62-1.08 5 .05 5 .05"],
  "rotateCcw": ["M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8","M3 3v5h5"],
  "search": ["m21 21-4.34-4.34",["circle",{"cx":"11","cy":"11","r":"8"}]],
  "server": [["rect",{"width":"20","height":"8","x":"2","y":"2","rx":"2","ry":"2"}],["rect",{"width":"20","height":"8","x":"2","y":"14","rx":"2","ry":"2"}],["line",{"x1":"6","x2":"6.01","y1":"6","y2":"6"}],["line",{"x1":"6","x2":"6.01","y1":"18","y2":"18"}]],
  "settings": ["M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915",["circle",{"cx":"12","cy":"12","r":"3"}]],
  "shield": ["M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"],
  "sparkles": ["M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z","M20 2v4","M22 4h-4",["circle",{"cx":"4","cy":"20","r":"2"}]],
  "square": [["rect",{"width":"18","height":"18","x":"3","y":"3","rx":"2"}]],
  "star": ["M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"],
  "terminal": ["M12 19h8","m4 17 6-6-6-6"],
  "trash2": ["M10 11v6","M14 11v6","M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6","M3 6h18","M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"],
  "triangleAlert": ["m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3","M12 9v4","M12 17h.01"],
  "upload": ["M12 3v12","m17 8-5-5-5 5","M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"],
  "video": ["m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5",["rect",{"x":"2","y":"6","width":"14","height":"12","rx":"2"}]],
  "wandSparkles": ["m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72","m14 7 3 3","M5 6v4","M19 14v4","M10 2v2","M7 8H3","M21 16h-4","M11 3H9"],
  "x": ["M18 6 6 18","m6 6 12 12"],
  "zap": ["M15.914 4a1.5 1.5 0 00-2.474-1.561l-9 9A1.5 1.5 0 005.5 14h4.002a.5.5 0 01.471.666L8.086 20a1.5 1.5 0 002.475 1.56l9-9A1.5 1.5 0 0018.5 10h-3.997a.5.5 0 01-.472-.667z"],
};
function icone(nome, tamanho = 14) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({ width: tamanho, height: tamanho, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" })) {
    svg.setAttribute(k, v);
  }
  svg.classList.add("icone");
  for (const desenho of ICONES[nome] || []) {
    const [tag, attrs] = typeof desenho === "string" ? ["path", { d: desenho }] : desenho;
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    svg.appendChild(e);
  }
  return svg;
}

// Botão só com ícone: o texto vai para aria-label e title (leitor de tela e dica ao passar o mouse).
function botaoIcone(nome, rotulo, onclick, classe = "btn btn-outline btn-sm btn-icone") {
  return el("button", { className: classe, type: "button", "aria-label": rotulo, title: rotulo, onclick }, [icone(nome)]);
}

// <i data-icone="nome"> no HTML estático vira o SVG do mapa acima, herdando as classes.
function hidratarIcones(raiz = document) {
  raiz.querySelectorAll("i[data-icone]").forEach((marcador) => {
    const svg = icone(marcador.dataset.icone, Number(marcador.dataset.tamanho) || 14);
    marcador.classList.forEach((c) => svg.classList.add(c));
    marcador.replaceWith(svg);
  });
}
hidratarIcones();

// Ícone + texto num mesmo nó (botões, links e etiquetas).
function comIcone(nome, texto, tamanho = 14) {
  const frag = document.createDocumentFragment();
  frag.appendChild(icone(nome, tamanho));
  frag.appendChild(el("span", { textContent: texto }));
  return frag;
}

function toast(mensagem, tipo = "info") {
  const container = $("toast-container");
  const nomeIcone = { success: "circleCheck", error: "circleX", warning: "triangleAlert" }[tipo] || "info";
  const t = el("div", { className: `toast toast-${tipo}`, role: tipo === "error" ? "alert" : "status" }, [icone(nomeIcone, 16), el("span", { textContent: mensagem })]);
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
  else if (viewId === "inicio") carregarInicio();
  else if (viewId === "provedores") carregarProvedores();
  else if (viewId === "squadti" && typeof carregarSquadti === "function") carregarSquadti();  // squadti.js carrega depois: no 1º acesso por #squadti ele mesmo chama
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
  segredoEmEdicao = chave;
  filtroSegredoAtual = "todos";
  buscaSegredo = "";
  $$("[data-filter-segredo]").forEach(b => b.classList.toggle("active", b.dataset.filterSegredo === "todos"));
  if ($("busca-segredos")) $("busca-segredos").value = "";
  if (abaAtivaAtual === "segredos") {
    renderizarSegredos();
  } else {
    ativarAba("segredos");
  }
}
function destacarSegredoNaTela() {
  if (!chaveParaDestacar) return;
  const alvo = $(`card-segredo-${chaveParaDestacar}`);
  if (!alvo) return;
  chaveParaDestacar = null;
  alvo.scrollIntoView({ behavior: "smooth", block: "center" });
  alvo.classList.add("destaque");
  setTimeout(() => alvo.classList.remove("destaque"), 2500);
}

// Rótulo de tier para exibição (a lógica continua comparando os valores originais)
function rotuloTier(tier) {
  return ({ LOCAL: "Local", NUVEM: "Nuvem", FREE: "Gratuito", PAID: "Pago", OUTROS: "Outros" })[tier] ?? tier ?? "Nuvem";
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
      }, [comIcone("externalLink", "Abrir", 12)]) : null;
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
        className: "btn btn-sm btn-outline btn-parar",
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
  // Os provedores agora são grupos na própria lista; a barra antiga fica sempre oculta.
  $("subfiltro-provedores").style.display = "none";
  filtroProvedorModelo = null;
}

let buscaModelosTermo = "";

function casouBuscaModelos(textoCompleto) {
  if (!buscaModelosTermo) return true;
  const termos = buscaModelosTermo.split(/\s+/).filter(Boolean);
  const alvo = (textoCompleto || "").toLowerCase();
  return termos.every(t => alvo.includes(t));
}

// Modelos agrupados por origem e tipo: Ollama (texto, embeddings), ComfyUI (um grupo por tipo de arquivo) e nuvem
// (um grupo por provedor). Cadastro e edição dos modelos de nuvem ficam na tela Provedores.
const gruposModelosFechados = new Set();

function grupoModelos(id, titulo, nomeIcone, resumo, linhas, colunas, extra = null) {
  const fechado = gruposModelosFechados.has(id) && !buscaModelosTermo;
  const corpoId = `grupo-modelos-${id}`;
  const alternar = el("button", { type: "button", className: "provedor-alternar", "aria-expanded": String(!fechado), "aria-controls": corpoId,
    onclick: () => { gruposModelosFechados.has(id) ? gruposModelosFechados.delete(id) : gruposModelosFechados.add(id); renderizarModelos(); } },
    [icone("chevronRight"), icone(nomeIcone), el("strong", { textContent: titulo })]);
  const tabela = el("table", { className: "tabela", id: corpoId }, [
    el("colgroup", {}, colunas.map((c) => el("col", { className: c.opcional ? "col-opcional" : "", style: `width:${c.largura}` }))),
    el("thead", {}, [el("tr", {}, colunas.map((c) => el("th", { className: [c.opcional ? "col-opcional" : "", c.classe || ""].join(" ").trim(), textContent: c.titulo })))]),
    el("tbody", {}, linhas),
  ]);
  tabela.hidden = fechado;
  return el("section", { className: "grupo provedor", "aria-label": titulo }, [
    el("div", { className: "grupo-cabecalho" }, [alternar, el("div", { className: "provedor-meta" }, [el("span", { className: "grupo-resumo", textContent: resumo }), extra])]),
    tabela,
  ]);
}

function celulaNomeModelo(nome, sub) {
  return el("td", {}, [
    el("span", { className: "celula-nome" }, [el("strong", { textContent: nome, title: nome })]),
    sub ? el("span", { className: "celula-sub mono", textContent: sub, title: sub }) : null,
  ]);
}

async function acaoModelo(fn, msgOk) {
  try {
    await fn();
    if (msgOk) toast(msgOk, "success");
    cacheModelos = null;
    await carregarModelos();
  } catch (err) { toast(err.message, "error"); }
}

function renderizarModelos() {
  const grid = $("grid-modelos");
  if (!cacheModelos) return;
  renderizarSubfiltroProvedores();
  const blocos = [];
  let total = 0;
  let exibidos = 0;
  const filtro = filtroModeloAtual;

  // 1. Ollama: texto e embeddings
  if (filtro === "todos" || filtro === "local") {
    for (const [cat, titulo, nomeIcone] of [["LLM", "Ollama · texto", "messageSquare"], ["Embedding", "Ollama · embeddings (busca)", "search"]]) {
      const todos = (cacheModelos.locais || []).filter((m) => (m.categoria || "LLM") === cat);
      total += todos.length;
      const visiveis = todos.filter((m) => casouBuscaModelos(`${m.nome} ${m.formato} ${m.quantizacao} ${m.familia || ""} ${m.categoria || ""} local ollama`));
      exibidos += visiveis.length;
      if (!visiveis.length) continue;
      const linhas = visiveis.map((m) => {
        const statusBar = criarBarraStatusTeste(historicoTestesModelos[m.nome]);
        const btnTestar = botaoIcone("zap", `Testar ${m.nome}`, () => testarUmModelo(m.nome, "ollama", statusBar, btnTestar), "btn btn-outline btn-sm btn-icone btn-testar-modelo");
        const celNome = celulaNomeModelo(m.nome, [m.familia, m.quantizacao].filter(Boolean).join(" · "));
        celNome.appendChild(statusBar);
        const ativo = m.ativo !== false;
        return el("tr", { className: ativo ? "" : "inativo" }, [
          celNome,
          el("td", { className: "num", textContent: m.tamanho_gb ? `${numeroBR.format(m.tamanho_gb)} GB` : "—" }),
          el("td", { className: "col-opcional" }, [m.em_vram ? el("span", { className: "badge badge-ok", textContent: `Na VRAM · ${numeroBR.format(m.vram_gb)} GB` }) : el("span", { className: "celula-sub", textContent: "No disco" })]),
          el("td", {}, [el("span", { className: `badge ${ativo ? "badge-ok" : "badge-neutro"}`, textContent: ativo ? "Ligado" : "Desligado" })]),
          el("td", { className: "acoes" }, [el("span", { className: "grupo-acoes" }, [
            ativo ? btnTestar : null,
            menuMais(`Mais ações para ${m.nome}`, [
              itemMenu(ativo ? "power" : "play", ativo ? "Desligar no roteador" : "Ligar no roteador", () => acaoModelo(
                () => api("POST", `/api/modelos/local/${encodeURIComponent(m.nome)}/toggle-ativo`, {}), `${m.nome} ${ativo ? "desligado" : "ligado"}.`)),
              m.em_vram ? itemMenu("cpu", "Tirar da memória de vídeo", () => acaoModelo(
                () => api("POST", `/api/modelos/local/${encodeURIComponent(m.nome)}/descarregar`, {}), `${m.nome} saiu da VRAM.`)) : null,
              el("hr"),
              itemMenu("trash2", "Apagar do disco", () => {
                if (!confirm(`Apagar ${m.nome} do disco? Libera ${m.tamanho_gb} GB.`)) return;
                acaoModelo(() => api("DELETE", `/api/modelos/local/${encodeURIComponent(m.nome)}`), `${m.nome} apagado.`);
              }, true),
            ]),
          ])]),
        ]);
      });
      blocos.push(grupoModelos(`ollama-${cat}`, titulo, nomeIcone, `${visiveis.length} modelo(s)`, linhas, [
        { titulo: "Modelo", largura: "44%" }, { titulo: "Tamanho", largura: "12%", classe: "num" },
        { titulo: "Memória", largura: "18%", opcional: true }, { titulo: "Estado", largura: "12%" }, { titulo: "", largura: "14%", classe: "acoes" }]));
    }
  }

  // 2. ComfyUI: um grupo por tipo de arquivo (checkpoint, difusão de vídeo, VAE, codificador de texto…)
  if (filtro === "todos" || filtro === "midia") {
    const porTipo = new Map();
    for (const m of cacheModelos.midia?.modelos || []) {
      total++;
      if (!casouBuscaModelos(`${m.nome || ""} ${m.arquivo} ${m.motor} ${m.tipo || ""} ${m.categoria || ""} comfyui`)) continue;
      exibidos++;
      const tipo = m.categoria || "Outros";
      if (!porTipo.has(tipo)) porTipo.set(tipo, []);
      porTipo.get(tipo).push(m);
    }
    for (const [tipo, lista] of [...porTipo.entries()].sort((a, b) => a[0].localeCompare(b[0], "pt-BR"))) {
      const linhas = lista.map((m) => {
        const statusBar = criarBarraStatusTeste(historicoTestesModelos[m.id]);
        const btnVerificar = botaoIcone("circleCheck", `Verificar o arquivo ${m.arquivo}`, () => testarUmModelo(m.id, "midia", statusBar, btnVerificar), "btn btn-outline btn-sm btn-icone btn-testar-modelo");
        const celNome = celulaNomeModelo(m.arquivo, m.nome !== m.arquivo ? m.nome : null);
        celNome.appendChild(statusBar);
        const ativo = m.ativo !== false;
        return el("tr", { className: ativo ? "" : "inativo" }, [
          celNome,
          el("td", { className: "num", textContent: `${numeroBR.format(m.tamanho_gb)} GB` }),
          el("td", { className: "col-opcional" }, [el("span", { className: "chip", textContent: (m.formato || "").toLowerCase() })]),
          el("td", {}, [el("span", { className: `badge ${ativo ? "badge-ok" : "badge-neutro"}`, textContent: ativo ? "Ligado" : "Desligado" })]),
          el("td", { className: "acoes" }, [el("span", { className: "grupo-acoes" }, [
            btnVerificar,
            menuMais(`Mais ações para ${m.arquivo}`, [
              itemMenu(ativo ? "power" : "play", ativo ? "Desligar no Estúdio" : "Ligar no Estúdio", () => acaoModelo(
                () => api("POST", `/api/modelos/local/${encodeURIComponent(m.id)}/toggle-ativo`, {}), `${m.arquivo} ${ativo ? "desligado" : "ligado"}.`)),
              el("hr"),
              itemMenu("trash2", "Apagar do disco", () => {
                if (!confirm(`Apagar ${m.arquivo} do disco? Libera ${m.tamanho_gb} GB.`)) return;
                acaoModelo(() => api("DELETE", `/api/modelos/midia/${encodeURIComponent(m.id)}`), `${m.arquivo} apagado.`);
              }, true),
            ]),
          ])]),
        ]);
      });
      const gb = lista.reduce((s, m) => s + (Number(m.tamanho_gb) || 0), 0);
      blocos.push(grupoModelos(`comfy-${tipo}`, `ComfyUI · ${tipo}`, "image", `${lista.length} arquivo(s) · ${numeroBR.format(Math.round(gb * 10) / 10)} GB`, linhas, [
        { titulo: "Arquivo", largura: "44%" }, { titulo: "Tamanho", largura: "12%", classe: "num" },
        { titulo: "Formato", largura: "18%", opcional: true }, { titulo: "Estado", largura: "12%" }, { titulo: "", largura: "14%", classe: "acoes" }]));
    }
  }

  // 3. Nuvem: um grupo por provedor (só consulta e teste; manutenção em Provedores)
  if (filtro === "todos" || filtro === "nuvem") {
    const semModelos = [];
    for (const prov of cacheModelos.provedores || []) {
      const modelos = prov.modelos || [];
      total += modelos.length;
      if (!modelos.length) { semModelos.push(prov.nome); continue; }
      const visiveis = modelos.filter((m) => casouBuscaModelos(`${m.nome} ${m.id} ${prov.nome} ${prov.chave_id} ${(m.papeis || []).join(" ")} nuvem`));
      exibidos += visiveis.length;
      if (!visiveis.length) continue;
      const linhas = visiveis.map((m) => {
        const statusBar = criarBarraStatusTeste(historicoTestesModelos[m.nome] || (m.id && historicoTestesModelos[m.id]));
        const pode = prov.tem_chave && m.ativo !== false;
        const btnTestar = pode ? botaoIcone("zap", `Testar ${m.nome}`, () => testarUmModelo(m.nome, "litellm", statusBar, btnTestar), "btn btn-outline btn-sm btn-icone btn-testar-modelo") : null;
        const celNome = celulaNomeModelo(m.nome, m.id);
        celNome.appendChild(statusBar);
        return el("tr", { className: m.ativo === false ? "inativo" : "" }, [
          celNome,
          el("td", { className: "num", textContent: m.contexto ? `${numeroBR.format(Math.round(m.contexto / 1000))} mil` : "—" }),
          el("td", { className: "col-opcional" }, [el("span", { className: "chips" }, (m.papeis || []).map((x) => el("span", { className: "chip", textContent: x })))]),
          el("td", {}, [el("span", { className: `badge ${m.ativo !== false ? "badge-ok" : "badge-neutro"}`, textContent: m.ativo !== false ? "Ligado" : "Desligado" })]),
          el("td", { className: "acoes" }, [el("span", { className: "grupo-acoes" }, [btnTestar])]),
        ]);
      });
      const gerenciar = el("a", { className: "link-externo", href: "#provedores", textContent: "Gerenciar",
        onclick: (ev) => { ev.preventDefault(); provedoresAbertos.add(prov.chave_id); ativarAba("provedores"); } });
      const chave = prov.tem_chave ? null : el("span", { className: "provedor-chave" }, [el("span", { className: "status-ponto aviso" }), "Sem chave"]);
      blocos.push(grupoModelos(`nuvem-${prov.chave_id}`, `${prov.nome}`, "cloud",
        `${modelos.filter((m) => m.ativo !== false).length} de ${modelos.length} ligados · ${prov.tier === "FREE" ? "gratuito" : "pago"}`, linhas, [
          { titulo: "Modelo", largura: "44%" }, { titulo: "Contexto", largura: "12%", classe: "num" },
          { titulo: "Papéis", largura: "22%", opcional: true }, { titulo: "Estado", largura: "12%" }, { titulo: "", largura: "10%", classe: "acoes" }],
        el("span", { className: "grupo-acoes" }, [chave, gerenciar])));
    }
    if (semModelos.length && !buscaModelosTermo) {
      blocos.push(el("div", { className: "grupo" }, [el("div", { className: "vazio" }, [
        el("strong", { textContent: `${semModelos.length} provedor(es) de nuvem ainda sem modelos no catálogo.` }),
        `${semModelos.join(", ")}. `,
        el("a", { className: "link-externo", href: "#provedores", textContent: "Procurar modelos em Provedores" }),
      ])]));
    }
  }

  $("contagem-busca-modelos").textContent = buscaModelosTermo ? `${exibidos} de ${total} modelo(s)` : `${total} modelo(s)`;
  $("btn-limpar-busca-modelos").style.display = buscaModelosTermo ? "inline-flex" : "none";

  if (!exibidos && !blocos.length) {
    blocos.push(el("div", { className: "grupo" }, [el("div", { className: "vazio" }, [
      el("strong", { textContent: buscaModelosTermo ? `Nada encontrado para "${buscaModelosTermo}".` : "Nenhum modelo nesta categoria." }),
      buscaModelosTermo ? el("button", { className: "btn btn-outline btn-sm", textContent: "Limpar busca", onclick: () => {
        buscaModelosTermo = "";
        $("input-busca-modelos-catalogo").value = "";
        renderizarModelos();
      } }) : null,
    ])]));
  }
  grid.replaceChildren(...blocos);
}

async function testarUmModelo(modeloId, tipo, elStatus, elBtn) {
  if (elBtn) elBtn.disabled = true;
  if (elStatus) {
    elStatus.style.display = "flex";
    elStatus.className = "card-status-bar carregando";
    elStatus.textContent = "Testando latência...";
  }
  try {
    const res = await api("POST", "/api/modelos/testar", { modelo: modeloId, tipo });
    if (res.ok) {
      const respTxt = (res.resposta || '').replace(/\n/g, ' ').trim();
      const preview = respTxt.length > 22 ? respTxt.slice(0, 20) + "..." : respTxt;
      const texto = `${res.latencia_ms}ms · "${preview}"`;
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
      const texto = `${res.latencia_ms || 0}ms · ${previewErr}`;
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
    const texto = `Erro: ${e.message.slice(0, 24)}`;
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

  const fila = [...$$("#grid-modelos .btn-testar-modelo")].filter((b) => !b.disabled);

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

  progresso.textContent = `${fila.length} testados`;
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
      btnSalvar.replaceChildren(comIcone("check", "Salvar e aplicar *"));
    } else {
      btnSalvar.classList.remove("btn-salvar-pendente");
      btnSalvar.replaceChildren(comIcone("check", "Salvar e aplicar"));
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
    el("div", { className: "parametros-roteador" }, [
      el("span", {}, ["Limiar para ir à nuvem ", el("strong", { textContent: rot.limiar })]),
      el("span", {}, ["Máximo de turnos ", el("strong", { textContent: rot.limites_texto.turnos || 8 })]),
      el("span", {}, ["Estratégia ", el("strong", { className: "mono", textContent: "latency-based-routing" })]),
      el("span", { className: "celula-sub", textContent: "Modelo com erro 429 ou tempo esgotado fica 60 s em quarentena" }),
    ])
  ]);
  container.appendChild(info);

  const listaGrupos = rot.grupos || [];
  if (listaGrupos.length === 0) {
    const cardVazio = el("div", {
      style: "text-align:center; padding:36px 16px; background:var(--bg-surface); border:1px dashed var(--border-color); border-radius:var(--radius-md); color:var(--text-muted); font-size:13px;"
    }, [
      el("div", { style: "display:flex; justify-content:center; margin-bottom:8px; color:var(--text-dim);" }, [icone("layers", 26)]),
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
    if (g.papeis_esperados && g.papeis_esperados.length) {
      g.papeis_esperados.forEach(p => {
        badgesHeader.push(el("span", { className: "chip", textContent: p }));
      });
    }
    if (!isAtivo) {
      badgesHeader.push(el("span", { className: "badge badge-desativado", textContent: "Desativado" }));
    }

    const btnEditarGrupo = botaoIcone("pencil", `Editar o grupo ${g.id}`, () => abrirModalEditarGrupo(g));
    const btnExcluirGrupo = (g.pode_excluir !== false) ? itemMenu("trash2", "Excluir grupo", async () => {
      if (!confirm(`Excluir o grupo ${g.id} (${g.titulo})? Os modelos continuam no catálogo.`)) return;
      try {
        await api("DELETE", `/api/roteador/grupos/${encodeURIComponent(g.id)}`);
        toast(`Grupo ${g.id} excluído.`, "success");
        await carregarRoteador();
      } catch (err) {
        toast(`Não foi possível excluir o grupo: ${err.message}`, "error");
      }
    }, true) : null;
    const grupoAcoes = el("div", { className: "grupo-acoes" }, [
      el("span", { className: "grupo-resumo", textContent: `${membrosNomes.length} modelo(s)` }),
      btnEditarGrupo,
      btnExcluirGrupo ? menuMais(`Mais ações para ${g.id}`, [btnExcluirGrupo]) : null,
    ]);
    const header = el("div", { className: "grupo-roteador-header" }, [
      el("div", { className: "grupo-roteador-titulo" }, [
        el("div", { className: "grupo-roteador-linha" }, [
          el("h4", { className: "mono", textContent: g.id, title: g.id }),
          ...badgesHeader
        ]),
        el("div", { className: "grupo-roteador-nome", textContent: g.titulo }),
        g.descricao ? el("div", { className: "celula-sub", textContent: g.descricao }) : null
      ]),
      grupoAcoes
    ]);

    // Lista de membros ativos
    const listaMembros = el("div", { className: "grupo-membros-lista" });
    const membrosMap = new Map((g.membros || []).map(m => [m.nome, m]));

    if (membrosNomes.length === 0) {
      listaMembros.appendChild(el("div", {
        style: "font-size:12px; color:var(--warning); font-style:italic; padding:10px 12px; background:rgba(234, 179, 8, 0.08); border-radius:var(--radius-sm); border:1px dashed rgba(234, 179, 8, 0.3);",
        textContent: "Nenhum modelo configurado neste grupo (o LiteLLM acionará o fallback padrão do sistema)."
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
          textContent: isLocal ? "Local" : `${provNome} (${tierNome})`
        });

        const infoMembro = el("div", { style: "display:flex; align-items:center; gap:8px; flex-wrap:wrap;" }, [
          badgePrioridade,
          badgeOrigem,
          el("strong", { style: "color:var(--text-primary); font-size:12px;", textContent: nomeModelo }),
          ...(papeisTxt || ctxTxt ? [
            el("span", { style: "font-size:11px; color:var(--text-dim); font-family:var(--font-sans);", textContent: `· [${papeisTxt}] ${ctxTxt}` })
          ] : [])
        ]);

        const btnsAcao = el("div", { className: "acoes-ordem", style: "display:flex; gap:4px; align-items:center;" }, [
          el("button", {
            className: "btn-ordem",
            "aria-label": "Subir prioridade",
            title: "Subir prioridade deste modelo no fallback",
            disabled: idx === 0,
            onclick: () => moverMembroGrupo(g.id, idx, -1)
          }, [icone("chevronUp", 12)]),
          el("button", {
            className: "btn-ordem",
            "aria-label": "Descer prioridade",
            title: "Descer prioridade deste modelo no fallback",
            disabled: idx === membrosNomes.length - 1,
            onclick: () => moverMembroGrupo(g.id, idx, 1)
          }, [icone("chevronDown", 12)]),
          el("button", {
            className: "btn-ordem",
            style: "color:var(--danger); border-color:rgba(239,68,68,0.3); margin-left:6px; font-weight:700;",
            "aria-label": "Remover modelo deste grupo",
            title: "Remover modelo deste grupo",
            onclick: () => removerMembroGrupo(g.id, idx)
          }, [icone("x", 12)])
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
        optgroupRec.label = `Recomendados para este Grupo (${recomendados.length})`;
        recomendados.forEach(m => {
          const opt = document.createElement("option");
          opt.value = m.nome;
          const papeisTxt = (m.papeis || []).join(", ");
          const origemTxt = m.origem === "local" ? "Ollama Local" : (m.provedor_nome || "Nuvem");
          opt.textContent = `${m.nome}  ·  [${papeisTxt}] (${origemTxt})`;
          optgroupRec.appendChild(opt);
        });
        selectModelos.appendChild(optgroupRec);
      }

      // 2. Modelos Locais Ollama (não recomendados diretamente, mas disponíveis)
      const locaisDisponiveis = elegiveis.filter(m => !m.recomendado && (m.origem === "local" || m.nome.startsWith("local/")));
      if (locaisDisponiveis.length > 0) {
        const optgroupLoc = document.createElement("optgroup");
        optgroupLoc.label = `Locais (Ollama) (${locaisDisponiveis.length})`;
        locaisDisponiveis.forEach(m => {
          const opt = document.createElement("option");
          opt.value = m.nome;
          const papeisTxt = (m.papeis || []).join(", ");
          opt.textContent = `${m.nome}  ·  [${papeisTxt}] (Ollama Local)`;
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
        grupoOpt.label = `${provNome} (${tier})`;
        listaMods.forEach(m => {
          const opt = document.createElement("option");
          opt.value = m.nome;
          const papeisTxt = (m.papeis || []).join(", ");
          opt.textContent = `${m.nome}  ·  [${papeisTxt}]`;
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
        textContent: "Todos os modelos disponíveis no ecossistema já estão vinculados a este grupo."
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
    toast("Composição dos grupos salva e aplicada no LiteLLM com sucesso!", "success");
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
    toast(`Auto-vinculação concluída! ${r.modelos_vinculados} modelo(s) organizados nos grupos.`, "success");
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
      <span class="girando" aria-hidden="true"></span>
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
              <span class="badge badge-ok">HTTP 200</span>
              <span style="font-family:var(--font-mono); font-size:11px; color:var(--brand-primary); font-weight:600;">${esc(res.modelo_usado)}</span>
</div>
            <span class="badge" style="background:rgba(99,102,241,0.15); color:var(--brand-primary); font-family:var(--font-mono); font-size:11px;"> ${esc(res.latencia_ms)}ms</span>
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
            <span class="badge badge-falha">Erro HTTP ${esc(res.status_http || "")}</span>
            <span class="badge" style="background:rgba(239,68,68,0.15); color:var(--danger); font-family:var(--font-mono); font-size:11px;"> ${esc(res.latencia_ms || 0)}ms</span>
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
          <span class="badge badge-falha">Falha de conexão</span>
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
      badgeDrift.textContent = `${totalAlertasMcp} MCP com chave pendente`;
    } else if (g.drift && g.drift.length > 0) {
      badgeDrift.className = "badge badge-paid";
      badgeDrift.textContent = `${g.drift.length} arquivo(s) fora de sincronia`;
    } else {
      badgeDrift.className = "badge badge-free";
      badgeDrift.textContent = "Tudo sincronizado";
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
          className: "interruptor",
          title: ativo ? "Ligado: vai para os clientes no próximo sincronizar" : "Desligado",
        }, [
          switchInput,
          el("span")
        ]);
        switchInput.setAttribute("aria-label", `${ativo ? "Desligar" : "Ligar"} ${nomeItem}`);

        const statusTeste = el("div", {
          className: "gov-status-row",
          style: "display: none;"
        });

        const btnTestar = sec.id === "mcp" ? el("button", {
          className: "btn btn-outline btn-sm btn-testar-mcp",
          textContent: "Testar",
          title: `Testar a conexão do MCP ${nomeItem}`,
          onclick: () => testarUmMcp(nomeItem, statusTeste, btnTestar)
        }) : null;

        const btnVerCodigo = botaoIcone("fileText", `Ver e editar ${nomeItem}`, () => abrirModalVerCodigo(sec.id, nomeItem, sec.titulo));

        const btnExcluir = menuMais(`Mais ações para ${nomeItem}`, [
          itemMenu("trash2", "Excluir", async () => {
            if (!confirm(`Excluir ${nomeItem} de ${sec.titulo}? O arquivo é apagado.`)) return;
            try {
              await api("DELETE", `/api/governanca/${sec.id}/${nomeItem}`);
              toast(`${nomeItem} excluído.`, "success");
              carregarGovernanca();
            } catch (e) {
              toast(e.message, "error");
            }
          }, true)
        ]);

        const avisosInfo = [];
        if (!ativo) {
          avisosInfo.push(el("span", {
            className: "badge",
            style: "font-size: 11px; padding: 1px 6px; background: rgba(255,255,255,0.06); color: var(--text-dim);",
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
            title: `Chave(s) obrigatória(s) não configurada(s) no .env: ${chavesPendentes.join(", ")}. Clique para ir ao Chaves e segredos.`,
            onclick: (ev) => {
              ev.stopPropagation();
              navegarParaSegredo(chavesPendentes[0]);
            }
          }, [
            el("span", { textContent: "" }, [icone("triangleAlert", 12)]),
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
            el("span", { textContent: `Variável obrigatória '${chavesPendentes.join(", ")}' não configurada no .env` }),
            el("a", {
              href: "#segredos",
              style: "color: var(--accent); text-decoration: underline; font-weight: 500; font-size: 11px; cursor: pointer;",
              textContent: "Configurar a chave",
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
          switchLabel,
          btnVerCodigo,
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
$("btn-sync-global")?.addEventListener("click", sincronizarClientesGlobal);

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
    case "claude": return icone("bot");
    case "antigravity": return icone("rocket");
    case "cursor": return icone("terminal");
    case "codex": return icone("fileText");
    default: return icone("folder");
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

  switchInput.setAttribute("aria-label", `${inst.ativo ? "Desligar" : "Ligar"} a sincronização de ${inst.nome || inst.id}`);
  const switchLabel = el("label", {
    className: "interruptor",
    title: inst.ativo ? "Recebe a sincronização" : "Fica fora da sincronização"
  }, [
    switchInput,
    el("span")
  ]);

  const badgeDisco = el("span", {
    className: `badge ${inst.existe_disco ? "badge-ok" : "badge-aviso"}`,
    textContent: inst.existe_disco ? "Pasta encontrada" : "Pasta não existe"
  });

  const btnEditar = botaoIcone("pencil", `Editar ${inst.nome || inst.id}`, () => abrirModalEditarInstancia(inst));

  const btnExcluir = menuMais(`Mais ações para ${inst.nome || inst.id}`, [
    itemMenu("trash2", "Tirar da sincronização", async () => {
      if (!confirm(`Tirar ${inst.nome || inst.id} da sincronização? Os arquivos dessa pasta não são apagados.`)) return;
      try {
        await api("DELETE", `/api/governanca/instancias/${inst.id}`);
        toast(`${inst.nome || inst.id} saiu da sincronização.`, "success");
        carregarInstanciasGovernanca();
      } catch (e) {
        toast(e.message, "error");
      }
    }, true),
  ]);

  return el("div", { className: "card", style: "display: flex; flex-direction: column; justify-content: space-between; gap: 12px;" }, [
    el("div", {}, [
      el("div", { style: "display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;" }, [
        el("div", {}, [
          el("div", { style: "font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 6px;" }, [
            el("span", {}, [obterIconeCliente(inst.cliente)]),
            el("span", {}, [inst.nome || inst.id])
          ]),
          el("div", { style: "font-size: 12px; color: var(--text-dim); margin-top: 2px;" }, [
            el("span", { style: "font-size: 11px; font-weight: 600; background: rgba(255,255,255,0.06); padding: 1px 6px; border-radius: 4px; margin-right: 6px;" }, [inst.cliente]),
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
          el("span", { style: "color: var(--text-dim);" }, ["Pasta: "]),
          el("code", { style: "font-size: 11px;" }, [inst.caminho])
        ]),
        inst.config_json ? el("div", {}, [
          el("span", { style: "color: var(--text-dim);" }, ["Configuração: "]),
          el("code", { style: "font-size: 11px;" }, [inst.config_json])
        ]) : el("div", { style: "color: var(--text-dim); font-size: 12px;" }, ["Configuração: padrão do cliente"])
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
            el("span", { className: "badge badge-free", style: "font-size: 11px;" }, ["No Disco"])
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
    elBtn.textContent = "Testando…";
  }
  if (elStatus) {
    elStatus.style.display = "block";
    elStatus.className = "gov-status-row gov-status-loading";
    elStatus.textContent = `Conectando e executando handshake JSON-RPC em '${mcpId}'...`;
  }
  try {
    const res = await api("POST", `/api/governanca/mcp/${mcpId}/testar`);
    if (res.ok) {
      if (elStatus) {
        elStatus.style.display = "block";
        elStatus.className = "gov-status-row gov-status-success";
        elStatus.textContent = `${res.mensagem} • Latência: ${res.latencia_ms}ms • Tipo: ${res.tipo}`;
      }
      return { ok: true, latencia_ms: res.latencia_ms };
    } else {
      if (elStatus) {
        elStatus.style.display = "block";
        elStatus.className = "gov-status-row gov-status-error";
        elStatus.textContent = `${res.mensagem} ${res.latencia_ms ? `(${res.latencia_ms}ms)` : ""}`;
      }
      return { ok: false, erro: res.mensagem };
    }
  } catch (e) {
    if (elStatus) {
      elStatus.style.display = "block";
      elStatus.className = "gov-status-row gov-status-error";
      elStatus.textContent = `Falha de conexão: ${e.message}`;
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

  progresso.textContent = `Concluído: ${botoes.length} MCPs testados!`;
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
    $("modal-ver-codigo-msg").textContent = "Salvo e sincronizado!";
    $("modal-ver-codigo-msg").style.color = "var(--success)";
    setTimeout(() => { $("modal-ver-codigo-msg").textContent = ""; }, 3500);
    carregarGovernanca();
  } catch (e) {
    toast(`Falha ao salvar: ${e.message}`, "error");
    $("modal-ver-codigo-msg").textContent = `Erro: ${e.message}`;
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
    $("modal-ver-codigo-msg").textContent = "Código copiado para a área de transferência!";
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
    btn.textContent = "Clonando repositório e importando skill...";

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
    hint.textContent = "O token será salvo no arquivo .env e protegido no Chaves e segredos.";
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

// ------------------------------------------------ 5. CHAVES E SEGREDOS (tabela agrupada)
let cacheSegredos = [];
let filtroSegredoAtual = "todos";
let buscaSegredo = "";
let segredoEmEdicao = null;   // chave com a linha de edição aberta

const GRUPOS_SEGREDO = [
  { id: "pagos", titulo: "Provedores pagos", icone: "coins" },
  { id: "gratuitos", titulo: "Provedores gratuitos", icone: "cloud" },
  { id: "mcp", titulo: "MCP e agentes", icone: "plug" },
  { id: "servicos", titulo: "Serviços internos", icone: "server" },
  { id: "acesso", titulo: "Login e acesso", icone: "lock" },
  { id: "configuracao", titulo: "Configuração", icone: "settings" },
];

async function carregarSegredos() {
  const grid = $("grid-segredos");
  if (!cacheSegredos.length) grid.replaceChildren(el("div", { className: "vazio", textContent: "Carregando chaves…" }));
  try {
    cacheSegredos = await api("GET", "/api/segredos");
    renderizarSegredos();
  } catch (e) {
    grid.replaceChildren(el("div", { className: "vazio" }, [el("strong", { textContent: "Não foi possível ler as chaves." }), e.message]));
  }
}

// Painel antigo (sem o campo grupo) ainda agrupa pela categoria.
function grupoDoSegredo(s) {
  return s.grupo || { FREE: "gratuitos", PAID: "pagos", GOVERNANCA: "mcp" }[s.categoria] || "servicos";
}

function segredoVisivel(s) {
  if (filtroSegredoAtual === "faltando" && s.definido) return false;
  if (!buscaSegredo) return true;
  return `${s.nome_provedor} ${s.chave}`.toLowerCase().includes(buscaSegredo);
}

function linkPortal(s) {
  if (!s.link) return null;
  const rotulo = s.grupo === "pagos" || s.grupo === "gratuitos" ? "Obter chave" : "Abrir";
  return el("a", { className: "link-externo", href: s.link, target: "_blank", rel: "noopener noreferrer",
    title: `${rotulo} em ${s.link}` }, [rotulo, icone("externalLink", 12)]);
}

async function testarSegredo(s, saida) {
  saida.className = "resultado-teste";
  saida.textContent = "Testando…";
  try {
    const res = await api("POST", `/api/segredos/${s.chave}/testar`);
    saida.className = `resultado-teste ${res.valido ? "ok" : "falha"}`;
    saida.textContent = `${res.valido ? "Funcionou" : "Falhou"}: ${res.mensagem} (${res.latencia_ms} ms)`;
  } catch (e) {
    saida.className = "resultado-teste falha";
    saida.textContent = `Falhou: ${e.message}`;
  }
}

function linhaSegredo(s) {
  const celulaValor = el("td", { className: "mono" });
  const mostrarMascarado = () => celulaValor.replaceChildren(
    s.definido ? s.mascarado : el("span", { className: "celula-sub", textContent: "Não configurada" }));
  mostrarMascarado();

  let revelado = false;
  const btnVer = s.definido ? botaoIcone("olho", "Revelar valor", async () => {
    if (revelado) {
      mostrarMascarado();
      btnVer.replaceChildren(icone("olho"));
      btnVer.setAttribute("aria-label", "Revelar valor");
      btnVer.title = "Revelar valor";
      revelado = false;
      return;
    }
    try {
      const res = await api("POST", `/api/segredos/${s.chave}/revelar`);
      celulaValor.replaceChildren(el("span", { textContent: res.valor }));
      btnVer.replaceChildren(icone("olhoFechado"));
      btnVer.setAttribute("aria-label", "Ocultar valor");
      btnVer.title = "Ocultar valor";
      revelado = true;
    } catch (e) { toast(`Não foi possível revelar: ${e.message}`, "error"); }
  }) : null;

  const resultado = el("span", { className: "resultado-teste" });
  const btnTestar = s.testavel && s.definido ? botaoIcone("zap", "Testar a chave no provedor", () => testarSegredo(s, resultado)) : null;
  const btnEditar = botaoIcone("pencil", s.definido ? "Trocar valor" : "Configurar", () => {
    segredoEmEdicao = segredoEmEdicao === s.chave ? null : s.chave;
    renderizarSegredos();
  });

  const status = s.definido
    ? el("span", { className: "celula-nome" }, [el("span", { className: "status-ponto ok" }), "Configurada"])
    : el("span", { className: "celula-nome" }, [el("span", { className: "status-ponto" }), "Faltando"]);

  const linha = el("tr", { id: `card-segredo-${s.chave}` }, [
    el("td", {}, [
      el("span", { className: "celula-nome" }, [el("strong", { textContent: s.nome_provedor || s.chave, title: s.nome_provedor || s.chave })]),
      el("span", { className: "celula-sub mono", textContent: s.chave, title: s.chave }),
    ]),
    celulaValor,
    el("td", { className: "col-opcional" }, [status, resultado]),
    el("td", { className: "col-opcional col-link" }, [linkPortal(s)]),
    el("td", { className: "acoes" }, [el("span", { className: "grupo-acoes" }, [btnVer, btnTestar, btnEditar])]),
  ]);
  return segredoEmEdicao === s.chave ? [linha, linhaEdicaoSegredo(s)] : [linha];
}

function linhaEdicaoSegredo(s) {
  const entrada = el("input", { type: s.secreto ? "password" : "text", autocomplete: "off", spellcheck: "false",
    placeholder: s.definido ? "Novo valor (substitui o atual)" : "Cole o valor aqui", "aria-label": `Novo valor para ${s.chave}` });
  const btnSalvar = el("button", { className: "btn btn-primary btn-sm", textContent: "Salvar", disabled: true });
  entrada.addEventListener("input", () => { btnSalvar.disabled = !entrada.value.trim(); });
  const salvar = async () => {
    if (!entrada.value.trim()) return;
    try {
      await api("PUT", `/api/segredos/${s.chave}`, { valor: entrada.value });
      toast(`${s.nome_provedor || s.chave}: valor salvo. Cópia anterior do .env guardada.`, "success");
      segredoEmEdicao = null;
      await carregarSegredos();
    } catch (e) { toast(e.message, "error"); }
  };
  btnSalvar.addEventListener("click", salvar);
  entrada.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") salvar();
    if (ev.key === "Escape") { segredoEmEdicao = null; renderizarSegredos(); }
  });
  const alternar = s.secreto ? botaoIcone("olho", "Mostrar o que estou digitando", () => {
    entrada.type = entrada.type === "password" ? "text" : "password";
  }) : null;
  const cancelar = el("button", { className: "btn btn-outline btn-sm", textContent: "Cancelar",
    onclick: () => { segredoEmEdicao = null; renderizarSegredos(); } });
  setTimeout(() => entrada.focus(), 0);
  return el("tr", { className: "linha-edicao" }, [
    el("td", { colspan: "5" }, [
      el("div", { className: "form-linha" }, [entrada, alternar, btnSalvar, cancelar,
        el("span", { className: "dica", textContent: "Enter salva, Esc cancela. Serviços que usam esta chave podem precisar ser reiniciados." })]),
    ]),
  ]);
}

function renderizarSegredos() {
  const grid = $("grid-segredos");
  const faltando = cacheSegredos.filter((s) => !s.definido).length;
  $("cont-seg-todos").textContent = cacheSegredos.length;
  $("cont-seg-faltando").textContent = faltando;

  const blocos = [];
  for (const g of GRUPOS_SEGREDO) {
    const doGrupo = cacheSegredos.filter((s) => grupoDoSegredo(s) === g.id)
      .sort((a, b) => (a.nome_provedor || a.chave).localeCompare(b.nome_provedor || b.chave, "pt-BR"));
    const visiveis = doGrupo.filter(segredoVisivel);
    if (!visiveis.length) continue;
    const configuradas = doGrupo.filter((s) => s.definido).length;
    const corpo = el("tbody", {}, visiveis.flatMap(linhaSegredo));
    blocos.push(el("section", { className: "grupo", "aria-label": g.titulo }, [
      el("div", { className: "grupo-cabecalho" }, [
        el("span", { className: "grupo-titulo" }, [icone(g.icone), g.titulo]),
        el("span", { className: "grupo-resumo", textContent: `${configuradas} de ${doGrupo.length} configuradas` }),
      ]),
      el("table", { className: "tabela" }, [
        el("colgroup", {}, [el("col", { style: "width:30%" }), el("col", { style: "width:24%" }), el("col", { className: "col-opcional", style: "width:15%" }),
          el("col", { className: "col-opcional", style: "width:15%" }), el("col", { style: "width:16%" })]),
        el("thead", {}, [el("tr", {}, [el("th", { textContent: "Nome" }), el("th", { textContent: "Valor" }),
          el("th", { className: "col-opcional", textContent: "Status" }), el("th", { className: "col-opcional", textContent: "Portal" }),
          el("th", { className: "acoes", textContent: "Ações" })])]),
        corpo,
      ]),
    ]));
  }
  if (!blocos.length) {
    blocos.push(el("div", { className: "vazio" }, [el("strong", { textContent: "Nenhuma chave encontrada." }),
      filtroSegredoAtual === "faltando" ? "Todas as chaves estão configuradas." : "Tente outro termo de busca."]));
  }
  grid.replaceChildren(...blocos);
  destacarSegredoNaTela();
}

// Nova chave: nome + valor livres (mesma regra de nome do servidor: letra maiúscula, depois A-Z, 0-9 e _).
const NOME_VARIAVEL = /^[A-Z][A-Z0-9_]{0,63}$/;
const formNovaChave = $("form-nova-chave");
function fecharNovaChave() {
  formNovaChave.hidden = true;
  formNovaChave.reset();
  $("nova-chave-valor").type = "password";
  $("nova-chave-salvar").disabled = true;
}
function validarNovaChave() {
  $("nova-chave-salvar").disabled = !(NOME_VARIAVEL.test($("nova-chave-nome").value) && $("nova-chave-valor").value.trim());
}
$("btn-nova-chave").addEventListener("click", () => {
  formNovaChave.hidden = !formNovaChave.hidden;
  if (!formNovaChave.hidden) $("nova-chave-nome").focus();
});
$("nova-chave-nome").addEventListener("input", (ev) => {
  ev.target.value = ev.target.value.toUpperCase().replace(/[\s-]+/g, "_");
  validarNovaChave();
});
$("nova-chave-valor").addEventListener("input", validarNovaChave);
$("nova-chave-ver").addEventListener("click", () => {
  const campo = $("nova-chave-valor");
  campo.type = campo.type === "password" ? "text" : "password";
});
$("nova-chave-cancelar").addEventListener("click", fecharNovaChave);
formNovaChave.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fecharNovaChave(); });
formNovaChave.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const nome = $("nova-chave-nome").value;
  const valor = $("nova-chave-valor").value;
  if (!NOME_VARIAVEL.test(nome) || !valor.trim()) return;
  const jaExiste = cacheSegredos.find((s) => s.chave === nome);
  if (jaExiste?.definido && !confirm(`${nome} já tem valor. Substituir? (o painel guarda cópia do .env)`)) return;
  try {
    await api("PUT", `/api/segredos/${nome}`, { valor });
    toast(`${nome}: valor salvo. Cópia anterior do .env guardada.`, "success");
    fecharNovaChave();
    await carregarSegredos();
    buscaSegredo = nome.toLowerCase();
    $("busca-segredos").value = nome;
    document.querySelector('[data-filter-segredo="todos"]').click();   // mostra todas e redesenha
  } catch (e) { toast(e.message, "error"); }
});

$$("[data-filter-segredo]").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$("[data-filter-segredo]").forEach((b) => b.classList.toggle("active", b === btn));
    filtroSegredoAtual = btn.dataset.filterSegredo;
    renderizarSegredos();
  });
});
$("busca-segredos").addEventListener("input", (ev) => {
  buscaSegredo = ev.target.value.trim().toLowerCase();
  renderizarSegredos();
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
        const statusClass = item.status === "failure" ? "badge badge-falha" : "badge badge-ok";
        const statusText = item.status === "failure" ? "Falhou" : "Ok";

        const latClass = item.latencia_ms < 1000 ? "latency-pill latency-fast"
                       : item.latencia_ms < 4000 ? "latency-pill latency-medium"
                       : "latency-pill latency-slow";

        const tr = el("tr", {}, [
          el("td", { style: "font-family:var(--font-mono); font-size:12px; color:var(--text-dim);", textContent: hora }),
          el("td", { className: "mono", title: item.modelo || "tudoia-auto", textContent: item.modelo || "tudoia-auto" }),
          el("td", {}, [el("span", { className: "badge badge-role", textContent: item.grupo })]),
          el("td", { className: "num", title: `Entrada ${item.prompt_tokens} · saída ${item.completion_tokens}`, textContent: numeroBR.format(item.total_tokens) }),
          el("td", { className: "num" }, [el("span", { className: latClass, textContent: `${numeroBR.format(item.latencia_ms)} ms` })]),
          el("td", {}, [el("span", { className: statusClass, textContent: statusText })]),
          el("td", { className: "col-opcional", title: item.cliente, textContent: item.cliente })
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
        const statusClass = isOk ? "badge badge-ok" : "badge badge-falha";
        const statusText = isOk ? "Ok" : "Falhou";
        const tipoBadge = item.tipo === "inpaint" ? "Edição" : item.tipo === "video" ? "Vídeo" : item.tipo === "svg" ? "SVG" : "Imagem";

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
  $("btn-toggle-stream-telemetria").replaceChildren(comIcone(telemetriaPausada ? "play" : "pause", telemetriaPausada ? "Retomar" : "Pausar"));
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
  $("btn-toggle-stream-hardware").replaceChildren(comIcone(hardwarePausado ? "play" : "pause", hardwarePausado ? "Retomar" : "Pausar"));
  toast(hardwarePausado ? "Monitoramento de hardware pausado" : "Monitoramento de hardware ativo (2s)", "info");
});

$("btn-recarregar-hardware").addEventListener("click", () => {
  carregarHardware();
  toast("Hardware atualizado", "info");
});

$("btn-limpar-vram").addEventListener("click", async () => {
  const btn = $("btn-limpar-vram");
  btn.disabled = true;
  try {
    toast("Descarregando modelos do Ollama para liberar VRAM...", "info");
    const res = await api("POST", "/api/hardware/limpar-vram");
    toast(`${res.mensagem}`, "success");
    carregarHardware();
  } catch (e) {
    toast(`Erro ao limpar VRAM: ${e.message}`, "error");
  } finally {
    btn.disabled = false;
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
  spanAlertas.className = `stat-detalhe ${resumo.alertas_criticos > 0 ? "resultado-teste falha" : ""}`;
  spanAlertas.textContent = resumo.alertas_criticos > 0
    ? `${resumo.alertas_criticos} provedor(es) perto ou acima da cota`
    : "Nenhuma cota estourada";

  // 2. Rótulo de período
  const periodoLabelMap = { "24h": "Últimas 24 horas", "7d": "Últimos 7 dias", "total": "Todo o histórico" };
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
      textContent: "Nenhum token registrado no período"
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
      el("td", { colspan: "7", className: "vazio", textContent: "Nenhum modelo foi usado neste período." })
    ]));
  } else {
    ranking_modelos.forEach(m => {
      const custo = m.tier === "PAID"
        ? el("span", { textContent: formatarMoedaUSD(m.custo_usd) })
        : el("span", { className: "resultado-teste ok", title: "Economia estimada", textContent: formatarMoedaUSD(m.economia_usd) });
      const tr = el("tr", {}, [
        el("td", {}, [el("strong", { className: "mono", textContent: m.modelo, title: m.modelo }),
          el("span", { className: "celula-sub", textContent: `${m.pct_do_total}% do total` })]),
        el("td", { className: "col-opcional", title: m.provedor_nome, textContent: m.provedor_nome }),
        el("td", { className: "num", textContent: m.requisicoes.toLocaleString("pt-BR") }),
        el("td", { className: "num col-opcional", textContent: formatarTokens(m.tokens_entrada) }),
        el("td", { className: "num col-opcional", textContent: formatarTokens(m.tokens_saida) }),
        el("td", { className: "num", textContent: formatarTokens(m.tokens_total) }),
        el("td", { className: "num" }, [custo])
      ]);
      tbodyModelos.appendChild(tr);
    });
  }
}

function textoCota(p) {
  const l = p.limites || {};
  const c = p.consumo;
  if (p.tier === "LOCAL") return el("span", { className: "celula-sub", textContent: "Sem limite de rede" });
  if (l.rpd) {
    const pct = Math.min(c.pct_rpd || 0, 100);
    const estado = pct >= 90 ? "falha" : pct >= 70 ? "aviso" : "ok";
    return el("span", { className: "cota" }, [
      el("span", { className: "cota-texto", textContent: `${numeroBR.format(c.requisicoes)} de ${numeroBR.format(l.rpd)} por dia` }),
      el("span", { className: "cota-barra", role: "img", "aria-label": `${pct}% da cota diária` }, [el("span", { className: estado, style: `width:${pct}%` })]),
    ]);
  }
  const partes = Object.entries(l).filter(([k, v]) => ROTULO_LIMITE[k] && k !== "reset" && v).map(([k, v]) => ROTULO_LIMITE[k](v));
  return el("span", { className: "celula-sub", textContent: partes.join(" · ") || "Sem limite cadastrado" });
}

function renderizarCardsProvedores(provedores) {
  const alvo = $("grid-limites-provedores");
  const mostrarSemUso = $("limites-mostrar-sem-uso").checked;
  const filtrados = provedores.filter((p) => filtroTierLimiteAtual === "todos" || p.tier === filtroTierLimiteAtual);
  const comUso = filtrados.filter((p) => mostrarSemUso || p.consumo.requisicoes > 0 || p.consumo.status_alerta !== "normal");
  const ocultos = filtrados.length - comUso.length;

  if (!comUso.length) {
    alvo.replaceChildren(el("div", { className: "grupo" }, [el("div", { className: "vazio" }, [
      el("strong", { textContent: "Nenhum uso no período." }),
      ocultos ? `${ocultos} provedor(es) sem uso estão ocultos. Marque "Mostrar provedores sem uso" para ver.` : "",
    ])]));
    return;
  }

  const linhas = comUso.map((p) => {
    const c = p.consumo;
    const alerta = c.status_alerta !== "normal";
    const critico = c.status_alerta === "critico" || c.status_alerta === "rate_limited";
    const sub = !p.chave_configurada && p.chave
      ? el("a", { className: "celula-sub", href: "#segredos", textContent: `Falta a chave ${p.chave}`, onclick: (ev) => { ev.preventDefault(); navegarParaSegredo(p.chave); } })
      : alerta ? el("span", { className: `celula-sub resultado-teste ${critico ? "falha" : ""}`, textContent: c.motivo_alerta })
      : el("span", { className: "celula-sub", textContent: `${(p.modelos || []).length} modelo(s) usados`, title: (p.modelos || []).map((m) => m.modelo).join("\n") });
    const valor = p.tier === "PAID"
      ? el("span", { textContent: formatarMoedaUSD(c.custo_usd) })
      : el("span", { className: "resultado-teste ok", textContent: `economia ${formatarMoedaUSD(c.economia_usd)}` });
    return el("tr", {}, [
      el("td", {}, [
        el("span", { className: "celula-nome" }, [
          el("span", { className: `status-ponto ${critico ? "falha" : alerta || (!p.chave_configurada && p.chave) ? "aviso" : "ok"}` }),
          el("strong", { textContent: p.nome, title: p.nome }),
        ]),
        sub,
      ]),
      el("td", {}, [el("span", { className: `badge ${p.tier === "FREE" ? "badge-free" : p.tier === "PAID" ? "badge-paid" : "badge-neutro"}`, textContent: rotuloTier(p.tier) })]),
      el("td", { className: "num", textContent: numeroBR.format(c.requisicoes) }),
      el("td", { className: "num", title: `Entrada ${formatarTokens(c.tokens_entrada)} · saída ${formatarTokens(c.tokens_saida)}`, textContent: formatarTokens(c.tokens_total) }),
      el("td", { className: "col-opcional" }, [textoCota(p)]),
      el("td", { className: "num" }, [valor]),
      el("td", { className: "acoes col-opcional" }, [p.site_limites
        ? el("a", { className: "link-externo", href: p.site_limites, target: "_blank", rel: "noopener noreferrer", title: p.fonte_limites || p.site_limites }, ["Limites", icone("externalLink", 12)])
        : el("span", { className: "celula-sub", title: p.fonte_limites || "", textContent: p.fonte_limites ? "Ver fonte" : "" })]),
    ]);
  });

  const rodape = ocultos ? el("div", { className: "grupo-rodape", textContent: `${ocultos} provedor(es) sem uso no período estão ocultos.` }) : null;
  alvo.replaceChildren(el("div", { className: "grupo" }, [
    el("table", { className: "tabela" }, [
      el("colgroup", {}, [el("col", { style: "width:28%" }), el("col", { style: "width:10%" }), el("col", { style: "width:10%" }),
        el("col", { style: "width:11%" }), el("col", { className: "col-opcional", style: "width:19%" }), el("col", { style: "width:13%" }), el("col", { className: "col-opcional", style: "width:9%" })]),
      el("thead", {}, [el("tr", {}, [
        el("th", { textContent: "Provedor" }), el("th", { textContent: "Plano" }), el("th", { className: "num", textContent: "Pedidos" }),
        el("th", { className: "num", textContent: "Tokens" }), el("th", { className: "col-opcional", textContent: "Cota" }),
        el("th", { className: "num", textContent: "Custo" }), el("th", { className: "acoes col-opcional", textContent: "Fonte" })])]),
      el("tbody", {}, linhas),
    ]),
    rodape,
  ]));
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

$("limites-mostrar-sem-uso").addEventListener("change", () => {
  if (dadosLimitesCache) renderizarCardsProvedores(dadosLimitesCache.provedores);
});

$("btn-recarregar-limites").addEventListener("click", () => {
  carregarLimites();
  toast("Métricas de limites e tokens atualizadas", "info");
});

// ------------------------------------------------ PROVEDORES EXTERNOS (manutenção completa)
let cacheProvedores = [];
let filtroProvedor = "todos";
let buscaProvedor = "";
const provedoresAbertos = new Set();
let provedorEmEdicao = null;   // id do provedor aberto no modal em modo edição; null = cadastro

const ROTULO_LIMITE = {
  rpm: (v) => `${numeroBR.format(v)} pedidos/min`,
  rpd: (v) => `${numeroBR.format(v)} pedidos/dia`,
  tpm: (v) => `${numeroBR.format(v)} tokens/min`,
  tpd: (v) => `${numeroBR.format(v)} tokens/dia`,
  usd_dia: (v) => `US$ ${numeroBR.format(v)}/dia`,
  neurons_dia: (v) => `${numeroBR.format(v)} neurons/dia`,
  reset: (v) => `renova ${String(v).toUpperCase() === "UTC" ? "à meia-noite UTC" : v}`,
};

// Toda mudança no catálogo invalida as telas que o leem.
function aposMudarCatalogo() {
  cacheModelos = null;
  if (abaAtivaAtual === "provedores") carregarProvedores();
  if (abaAtivaAtual === "modelos") carregarModelos();
  if (abaAtivaAtual === "limites") carregarLimites();
}

async function carregarProvedores() {
  const lista = $("lista-provedores");
  if (!cacheProvedores.length) lista.replaceChildren(el("div", { className: "vazio", textContent: "Carregando provedores…" }));
  try {
    cacheProvedores = await api("GET", "/api/provedores");
    renderizarProvedores();
  } catch (e) {
    lista.replaceChildren(el("div", { className: "vazio" }, [el("strong", { textContent: "Não foi possível ler os provedores." }), e.message]));
  }
}

function provedorVisivel(p) {
  if (filtroProvedor === "FREE" || filtroProvedor === "PAID") { if (p.tier !== filtroProvedor) return false; }
  if (filtroProvedor === "sem-chave" && p.tem_chave) return false;
  if (!buscaProvedor) return true;
  const texto = `${p.nome} ${p.id} ${(p.modelos || []).map((m) => `${m.nome} ${m.id}`).join(" ")}`.toLowerCase();
  return texto.includes(buscaProvedor);
}

function menuMais(rotulo, itens) {
  const lista = el("div", { className: "menu-mais-lista", role: "menu" }, itens.filter(Boolean));
  const menu = el("details", { className: "menu-mais" }, [
    el("summary", { className: "btn btn-outline btn-sm btn-icone", "aria-label": rotulo, title: rotulo }, [icone("ellipsis")]),
    lista,
  ]);
  lista.addEventListener("click", () => menu.removeAttribute("open"));
  return menu;
}
// Um menu aberto fecha ao clicar fora dele.
document.addEventListener("click", (ev) => {
  $$("details.menu-mais[open]").forEach((d) => { if (!d.contains(ev.target)) d.removeAttribute("open"); });
});

function itemMenu(nomeIcone, texto, onclick, perigo = false) {
  return el("button", { type: "button", role: "menuitem", className: perigo ? "perigo" : "", onclick }, [icone(nomeIcone), texto]);
}

async function alternarModelo(p, m, ligado, interruptor) {
  try {
    await api("PATCH", `/api/provedores/${encodeURIComponent(p.id)}/modelos/${encodeURIComponent(m.nome)}`, { ativo: ligado });
    m.ativo = ligado;
    p.modelos_ativos += ligado ? 1 : -1;
    toast(`${m.nome} ${ligado ? "ligado" : "desligado"}. O LiteLLM foi atualizado.`, "success");
    renderizarProvedores();
  } catch (e) {
    interruptor.checked = !ligado;
    toast(e.message, "error");
  }
}

async function removerModelo(p, m) {
  if (!confirm(`Remover ${m.nome} do catálogo de ${p.nome}?`)) return;
  try {
    await api("DELETE", `/api/provedores/${encodeURIComponent(p.id)}/modelos/${encodeURIComponent(m.nome)}`);
    toast(`${m.nome} removido.`, "success");
    aposMudarCatalogo();
  } catch (e) {
    const refs = (e.extras?.referencias || []).map((r) => `${r.modelo} (${(r.grupos || []).join(", ")})`).join("; ");
    toast(refs ? `${e.message} Em uso: ${refs}. Tire do grupo no Roteador antes.` : e.message, "error");
  }
}

async function excluirProvedor(p) {
  if (!confirm(`Excluir o provedor ${p.nome} e os ${p.total_modelos} modelo(s) dele do catálogo?\nA chave ${p.chave} continua no .env.`)) return;
  try {
    await api("DELETE", `/api/provedores/${encodeURIComponent(p.id)}`);
    toast(`${p.nome} excluído. A chave continua em Chaves e segredos.`, "success");
    provedoresAbertos.delete(p.id);
    aposMudarCatalogo();
  } catch (e) {
    const refs = (e.extras?.referencias || []).map((r) => `${r.modelo} (${(r.grupos || []).join(", ")})`).join("; ");
    toast(refs ? `${e.message} Em uso: ${refs}.` : e.message, "error");
  }
}

async function testarModeloProvedor(m, saida) {
  saida.className = "resultado-teste";
  saida.textContent = "Testando…";
  try {
    const res = await api("POST", "/api/modelos/testar", { modelo: m.nome, tipo: "litellm" });
    saida.className = `resultado-teste ${res.ok ? "ok" : "falha"}`;
    saida.textContent = res.ok ? `Respondeu em ${res.latencia_ms} ms` : `Falhou: ${(res.erro || "sem detalhe").slice(0, 80)}`;
    saida.title = res.ok ? res.resposta || "" : res.erro || "";
    if (res.desativado_automaticamente) {
      toast(`${m.nome}: o provedor diz que o modelo não existe mais. Foi desligado e tirado do roteamento.`, "error");
      aposMudarCatalogo();
    }
  } catch (e) {
    saida.className = "resultado-teste falha";
    saida.textContent = `Falhou: ${e.message}`;
  }
}

function tabelaModelos(p) {
  if (!p.modelos.length) {
    return el("div", { className: "vazio" }, [el("strong", { textContent: "Nenhum modelo cadastrado." }),
      p.url_modelos ? "Use Procurar na API para listar o que o provedor oferece." : "Cadastre a lista de modelos do provedor para procurar na API."]);
  }
  const linhas = p.modelos.map((m) => {
    const interruptor = el("input", { type: "checkbox", checked: m.ativo, "aria-label": `${m.ativo ? "Desligar" : "Ligar"} ${m.nome}` });
    interruptor.addEventListener("change", () => alternarModelo(p, m, interruptor.checked, interruptor));
    const saida = el("span", { className: "resultado-teste" });
    const podeTestar = p.tem_chave && m.ativo;
    return el("tr", {}, [
      el("td", {}, [
        el("span", { className: "celula-nome" }, [el("strong", { textContent: m.nome, title: m.nome })]),
        el("span", { className: "celula-sub mono", textContent: m.id, title: m.id }),
        saida,
      ]),
      el("td", { className: "col-opcional" }, [el("span", { className: "chips" }, (m.papeis || []).map((x) => el("span", { className: "chip", textContent: x })))]),
      el("td", { className: "num col-opcional", textContent: m.contexto ? `${numeroBR.format(Math.round(m.contexto / 1000))} mil` : "—" }),
      el("td", {}, [m.em_uso ? el("span", { className: "badge badge-ok", textContent: "Em uso", title: "Está em algum grupo do Roteador" })
        : el("span", { className: "celula-sub", textContent: "Fora dos grupos" })]),
      el("td", {}, [el("label", { className: "interruptor", title: m.ativo ? "Ligado no LiteLLM" : "Desligado" }, [interruptor, el("span")])]),
      el("td", { className: "acoes" }, [el("span", { className: "grupo-acoes" }, [
        podeTestar ? botaoIcone("zap", `Testar ${m.nome}`, () => testarModeloProvedor(m, saida)) : null,
        menuMais(`Mais ações para ${m.nome}`, [itemMenu("trash2", "Remover do catálogo", () => removerModelo(p, m), true)]),
      ])]),
    ]);
  });
  return el("table", { className: "tabela" }, [
    el("colgroup", {}, [el("col", { style: "width:38%" }), el("col", { className: "col-opcional", style: "width:22%" }),
      el("col", { className: "col-opcional", style: "width:10%" }), el("col", { style: "width:14%" }), el("col", { style: "width:7%" }), el("col", { style: "width:9%" })]),
    el("thead", {}, [el("tr", {}, ["Modelo", "Papéis", "Contexto", "Roteador", "Ligado", ""].map((t, i) =>
      el("th", { className: [i === 1 || i === 2 ? "col-opcional" : "", i === 2 ? "num" : "", i === 5 ? "acoes" : ""].join(" ").trim(), textContent: t })))]),
    el("tbody", {}, linhas),
  ]);
}

function blocoProvedor(p) {
  const aberto = provedoresAbertos.has(p.id) || Boolean(buscaProvedor);
  const corpoId = `prov-corpo-${p.id}`;
  const alternar = el("button", { type: "button", className: "provedor-alternar", "aria-expanded": String(aberto), "aria-controls": corpoId,
    onclick: () => { provedoresAbertos.has(p.id) ? provedoresAbertos.delete(p.id) : provedoresAbertos.add(p.id); renderizarProvedores(); } }, [
    icone("chevronRight"),
    el("strong", { textContent: p.nome }),
    el("span", { className: `badge ${p.tier === "FREE" ? "badge-free" : "badge-paid"}`, textContent: p.tier === "FREE" ? "Gratuito" : "Pago" }),
  ]);

  const chave = p.tem_chave
    ? el("span", { className: "provedor-chave" }, [el("span", { className: "status-ponto ok" }), "Chave configurada"])
    : el("span", { className: "provedor-chave" }, [el("span", { className: "status-ponto aviso" }),
        el("a", { href: "#segredos", textContent: `Falta ${(p.chaves_faltando || [p.chave]).join(", ")}`,
          onclick: (ev) => { ev.preventDefault(); navegarParaSegredo((p.chaves_faltando || [p.chave])[0]); } })]);

  const links = [
    p.site_chave ? el("a", { className: "link-externo", href: p.site_chave, target: "_blank", rel: "noopener noreferrer", title: p.site_chave }, ["Obter chave", icone("externalLink", 12)]) : null,
    p.site_limites ? el("a", { className: "link-externo", href: p.site_limites, target: "_blank", rel: "noopener noreferrer", title: p.site_limites }, ["Limites e preços", icone("externalLink", 12)]) : null,
  ];

  const cabecalho = el("div", { className: "grupo-cabecalho" }, [
    alternar,
    el("div", { className: "provedor-meta" }, [
      chave,
      el("span", { className: "grupo-resumo aviso", id: `prov-progresso-${p.id}`, "aria-live": "polite" }),
      el("span", { className: "grupo-resumo", textContent: `${p.modelos_ativos} de ${p.total_modelos} modelos ligados` }),
      ...links,
      el("span", { className: "grupo-acoes" }, [
        p.url_modelos ? botaoIcone("search", "Procurar modelos na API do provedor", () => abrirModalDescobrirModelos(p.id, p.nome, p.tier)) : null,
        botaoIcone("pencil", `Editar ${p.nome}`, () => abrirModalProvedor(p)),
        menuMais(`Mais ações para ${p.nome}`, [
          p.url_modelos && p.tem_chave ? itemMenu("zap", "Preencher com os que funcionam", () => preencherProvedor(p)) : null,
          p.url_modelos ? itemMenu("sparkles", "Escolher modelos novos", () => abrirEscolherNovos(p.id)) : null,
          itemMenu("keyRound", "Ir para a chave", () => navegarParaSegredo(p.chave)),
          el("hr"),
          itemMenu("trash2", "Excluir provedor", () => excluirProvedor(p), true),
        ]),
      ]),
    ]),
  ]);

  const limites = Object.entries(p.limites || {}).filter(([k, v]) => ROTULO_LIMITE[k] && v !== null && v !== "")
    .map(([k, v]) => el("span", { className: "chip", textContent: ROTULO_LIMITE[k](v) }));
  const corpo = el("div", { className: "provedor-corpo", id: corpoId }, [
    el("div", { className: "provedor-info" }, [
      limites.length ? el("span", { className: "chips" }, limites) : el("span", { textContent: "Sem limites cadastrados." }),
      p.fonte_limites ? el("span", { textContent: `Fonte: ${p.fonte_limites}` }) : null,
    ]),
    tabelaModelos(p),
  ]);
  corpo.hidden = !aberto;
  return el("section", { className: "grupo provedor", "aria-label": p.nome }, [cabecalho, corpo]);
}

function renderizarProvedores() {
  const cont = { todos: cacheProvedores.length, FREE: 0, PAID: 0, "sem-chave": 0 };
  for (const p of cacheProvedores) { cont[p.tier]++; if (!p.tem_chave) cont["sem-chave"]++; }
  for (const [k, v] of Object.entries(cont)) $(`cont-prov-${k}`).textContent = v;

  const visiveis = cacheProvedores.filter(provedorVisivel);
  const lista = $("lista-provedores");
  if (!visiveis.length) {
    lista.replaceChildren(el("div", { className: "vazio" }, [el("strong", { textContent: "Nenhum provedor aqui." }),
      cacheProvedores.length ? "Troque o filtro ou a busca." : "Cadastre o primeiro em Novo provedor."]));
    return;
  }
  lista.replaceChildren(...visiveis.map(blocoProvedor));
}

$$("[data-filtro-provedor]").forEach((btn) => btn.addEventListener("click", () => {
  $$("[data-filtro-provedor]").forEach((b) => b.classList.toggle("active", b === btn));
  filtroProvedor = btn.dataset.filtroProvedor;
  renderizarProvedores();
}));
$("busca-provedores").addEventListener("input", (ev) => {
  buscaProvedor = ev.target.value.trim().toLowerCase();
  renderizarProvedores();
});

// Modal único para cadastrar (POST) e editar (PATCH). Na edição, id e variável da chave não mudam.
function abrirModalProvedor(p = null) {
  provedorEmEdicao = p ? p.id : null;
  const lim = p?.limites || {};
  const valores = {
    "prov-id": p?.id || "", "prov-nome": p?.nome || "", "prov-tier": p?.tier || "PAID", "prov-chave": p?.chave || "",
    "prov-valor-chave": "", "prov-api-base": p?.api_base || "", "prov-url-modelos": p?.url_modelos || "",
    "prov-site-chave": p?.site_chave || "", "prov-site-limites": p?.site_limites || "",
    "prov-rpm": lim.rpm ?? "", "prov-rpd": lim.rpd ?? "", "prov-tpd": lim.tpd ?? "", "prov-usd-dia": lim.usd_dia ?? "",
    "prov-fonte-limites": p?.fonte_limites || "",
  };
  for (const [id, v] of Object.entries(valores)) $(id).value = v;
  $("prov-id").readOnly = Boolean(p);
  $("prov-chave").readOnly = Boolean(p);
  $("grupo-prov-valor-chave").hidden = Boolean(p);
  $("modal-provedor-titulo").textContent = p ? `Editar ${p.nome}` : "Novo provedor";
  $("modal-provedor-sub").textContent = p
    ? "A chave em si é trocada em Chaves e segredos."
    : "Qualquer serviço compatível com a API da OpenAI ou suportado pelo LiteLLM.";
  $("btn-salvar-provedor").textContent = p ? "Salvar alterações" : "Cadastrar provedor";
  $("modal-provedor").classList.add("open");
  setTimeout(() => $(p ? "prov-nome" : "prov-id").focus(), 0);
}

function limitesDoFormulario() {
  const limites = {};
  const reset = provedorEmEdicao ? cacheProvedores.find((x) => x.id === provedorEmEdicao)?.limites?.reset : null;
  for (const [campo, chave] of [["prov-rpm", "rpm"], ["prov-rpd", "rpd"], ["prov-tpd", "tpd"], ["prov-usd-dia", "usd_dia"]]) {
    const v = $(campo).value.trim();
    if (v !== "") limites[chave] = Number(v);
  }
  // Campos que o formulário não mostra (neurons_dia, tpm, reset) são preservados na edição.
  const atual = provedorEmEdicao ? cacheProvedores.find((x) => x.id === provedorEmEdicao)?.limites || {} : {};
  for (const k of ["neurons_dia", "tpm"]) if (atual[k] !== undefined && atual[k] !== null) limites[k] = atual[k];
  if (reset) limites.reset = reset;
  return limites;
}

$("btn-salvar-provedor").addEventListener("click", async () => {
  const comum = {
    nome: $("prov-nome").value.trim(),
    tier: $("prov-tier").value,
    api_base: $("prov-api-base").value.trim(),
    url_modelos: $("prov-url-modelos").value.trim(),
    site_chave: $("prov-site-chave").value.trim(),
    site_limites: $("prov-site-limites").value.trim(),
    fonte_limites: $("prov-fonte-limites").value.trim(),
    limites: limitesDoFormulario(),
  };
  try {
    if (provedorEmEdicao) {
      await api("PATCH", `/api/provedores/${encodeURIComponent(provedorEmEdicao)}`, comum);
      toast(`${comum.nome} atualizado.`, "success");
    } else {
      const id = $("prov-id").value.trim().toLowerCase();
      const chave = $("prov-chave").value.trim().toUpperCase();
      if (!id || !comum.nome || !chave) {
        toast("Preencha identificador, nome e variável da chave.", "error");
        return;
      }
      const corpo = { id, chave, ...comum };
      for (const k of ["api_base", "url_modelos", "site_chave", "site_limites", "fonte_limites"]) if (!corpo[k]) delete corpo[k];
      const valor = $("prov-valor-chave").value.trim();
      if (valor) corpo.valor_chave = valor;
      const res = await api("POST", "/api/provedores", corpo);
      toast(`${res.nome} cadastrado. Agora procure os modelos dele na API.`, "success");
      provedoresAbertos.add(res.id);
    }
    fecharModais();
    aposMudarCatalogo();
  } catch (e) {
    toast(e.message, "error");
  }
});

$("btn-provedores-novo").addEventListener("click", () => abrirModalProvedor());
$("btn-provedores-escolher-novos").addEventListener("click", () => abrirEscolherNovos());
$("btn-provedores-sincronizar").addEventListener("click", () => sincronizarNovosModelos());

// Selo do ComfyUI nas telas do Estúdio: mesma consulta, mesmo texto e mesma cor nas três.
async function atualizarSeloComfy(badge) {
  if (!badge) return null;
  let online = null;
  try {
    online = Boolean((await api("GET", "/api/estudio/status-motores")).comfyui);
  } catch (e) { online = null; }
  badge.className = `badge ${online ? "badge-ok" : online === false ? "badge-aviso" : "badge-neutro"} selo-comfy`;
  badge.replaceChildren(el("span", { className: `status-ponto ${online ? "ok" : online === false ? "aviso" : ""}` }),
    online ? "ComfyUI no ar" : online === false ? "ComfyUI desligado" : "ComfyUI sem resposta");
  badge.title = online ? "Abrir o ComfyUI em outra aba" : "Ligue o ComfyUI em Serviços";
  return online;
}

// ------------------------------------------------ TESTAR ANTES DE INCLUIR
// Um modelo só entra no catálogo depois de responder a uma chamada real na API do próprio provedor
// (POST /api/provedores/{id}/testar-modelos). O servidor espaça as chamadas pelo limite por minuto do provedor.
const TAMANHO_LOTE_TESTE = 10;   // lotes pequenos: o progresso aparece e um pedido HTTP não dura minutos

async function testarCandidatos(provedorId, ids, aoProgresso) {
  const resultados = new Map();
  for (let i = 0; i < ids.length; i += TAMANHO_LOTE_TESTE) {
    const lote = ids.slice(i, i + TAMANHO_LOTE_TESTE);
    try {
      const res = await api("POST", `/api/provedores/${encodeURIComponent(provedorId)}/testar-modelos`, { ids: lote });
      for (const r of res.resultados || []) resultados.set(r.id, r);
    } catch (e) {
      // Falha do lote inteiro (rede, permissão): conta como reprovado, nada é incluído sem teste.
      for (const id of lote) resultados.set(id, { id, ok: false, erro: e.message });
    }
    if (aoProgresso) aoProgresso(Math.min(i + TAMANHO_LOTE_TESTE, ids.length), ids.length);
  }
  return resultados;
}

// Testa os itens ({provedor, nome, id, papeis, contexto}) e inclui só os aprovados. Devolve o resumo.
async function testarEIncluir(itens, aoProgresso) {
  const porProvedor = new Map();
  for (const item of itens) {
    if (!porProvedor.has(item.provedor)) porProvedor.set(item.provedor, []);
    porProvedor.get(item.provedor).push(item);
  }
  let feitos = 0;
  const aprovados = [];
  const reprovados = [];
  for (const [provedor, lista] of porProvedor) {
    const resultados = await testarCandidatos(provedor, lista.map((n) => n.id), (n) => aoProgresso?.(feitos + n, itens.length));
    feitos += lista.length;
    for (const item of lista) {
      const r = resultados.get(item.id) || { ok: false, erro: "sem resposta do teste" };
      item.teste = r;
      (r.ok ? aprovados : reprovados).push(item);
    }
  }
  let incluidos = [];
  let recusados = [];
  // Já no catálogo (desligado): só liga. Novo: entra pelo lote.
  const aLigar = aprovados.filter((i) => i.jaNoCatalogo);
  const aAdicionar = aprovados.filter((i) => !i.jaNoCatalogo);
  if (aAdicionar.length) {
    const res = await api("POST", "/api/provedores/modelos-lote", {
      itens: aAdicionar.map(({ provedor, nome, id, papeis, contexto }) => ({ provedor, nome, id, papeis, contexto: contexto || null })),
    });
    incluidos = res.adicionados || [];
    recusados = res.recusados || [];
  }
  for (const item of aLigar) {
    try {
      await api("PATCH", `/api/provedores/${encodeURIComponent(item.provedor)}/modelos/${encodeURIComponent(item.nome)}`, { ativo: true });
      incluidos.push(item.nome);
    } catch (e) {
      recusados.push({ id: item.id, motivo: e.message });   // um que não liga não impede os demais
    }
  }
  return { aprovados, reprovados, incluidos, recusados };
}

function textoResumoTeste(r) {
  const partes = [`${r.incluidos.length} ligado(s) depois de passar no teste`];
  if (r.reprovados.length) partes.push(`${r.reprovados.length} reprovado(s), sem ligar`);
  if (r.recusados.length) partes.push(`${r.recusados.length} recusado(s) pelo catálogo`);
  return partes.join(" · ");
}

// Provedores: procura os modelos novos de um provedor, testa todos e inclui só os que responderam.
async function preencherProvedor(p) {
  let dados;
  try {
    dados = await api("GET", `/api/provedores/novos?provedor=${encodeURIComponent(p.id)}`);
  } catch (e) {
    toast(`Não foi possível listar os modelos de ${p.nome}: ${e.message}`, "error");
    return;
  }
  const erro = (dados.erros || {})[p.id];
  if (erro) { toast(`${p.nome}: ${erro}`, "error"); return; }
  const novos = dados.novos || [];
  // Modelos já no catálogo e desligados (ex.: vindos de "Sincronizar catálogo") também entram no teste.
  // Acima do limite diário do provedor ficam de fora: testar tudo gastaria a cota inteira (OpenRouter free: 50/dia).
  const porDia = Number(p.limites?.rpd) || 0;
  const desligados = (p.modelos || []).filter((m) => m.ativo === false)
    .map((m) => ({ provedor: p.id, nome: m.nome, id: m.id, papeis: m.papeis, contexto: m.contexto, jaNoCatalogo: true }));
  const ignorados = porDia && desligados.length > porDia ? desligados.length : 0;
  const candidatos = [...novos, ...(ignorados ? [] : desligados)];
  const avisoCota = ignorados
    ? `\n${ignorados} modelo(s) desligado(s) ficam de fora: passam do limite de ${porDia} pedidos por dia. Ligue-os pelo interruptor ou use "Escolher modelos novos".`
    : "";
  if (!candidatos.length) {
    toast(`${p.nome}: nenhum modelo novo ou desligado para testar.${avisoCota}`, ignorados ? "warning" : "info");
    return;
  }
  const porMinuto = Number(p.limites?.rpm) || 0;
  const minutos = porMinuto ? Math.ceil(candidatos.length / porMinuto) : null;
  const aviso = (minutos ? `\nCom o limite de ${porMinuto} pedidos por minuto, leva cerca de ${minutos} min.` : "") + avisoCota;
  if (!confirm(`${p.nome}: ${novos.length} modelo(s) novo(s) na API e ${ignorados ? 0 : desligados.length} já cadastrado(s) e desligado(s).\nCada um recebe uma mensagem curta de teste ("Responda apenas: ok") e só os que responderem ficam ligados.${aviso}\n\nContinuar?`)) return;

  const marca = $(`prov-progresso-${p.id}`);
  try {
    const r = await testarEIncluir(candidatos, (feito, total) => { if (marca) marca.textContent = `Testando ${feito} de ${total}…`; });
    toast(`${p.nome}: ${textoResumoTeste(r)}.`, r.incluidos.length ? "success" : "warning");
    if (r.reprovados.length) {
      console.info(`Reprovados em ${p.nome}:`, r.reprovados.map((n) => `${n.id}: ${n.teste?.erro || n.teste?.status_http}`));
    }
    provedoresAbertos.add(p.id);
  } catch (e) {
    toast(`${p.nome}: ${e.message}`, "error");
  } finally {
    if (marca) marca.textContent = "";
    aposMudarCatalogo();
  }
}

// ------------------------------------------------ CADASTRO DE PROVEDORES & DESCOBERTA DINÂMICA
let scanResultadoAtual = null;
let scanFiltroFreeOnly = false;
let provedorSincronizandoId = null;

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
      ? el("span", { className: "badge badge-success", textContent: "Ativo na API" })
      : el("span", { className: "badge badge-warning", textContent: "Ausente na API" });

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
    toast(`Modelo ${res.modelo.nome} adicionado (desligado). Ligue-o em Provedores.`, "success");
    abrirModalDescobrirModelos(provId, provId, "API");
    aposMudarCatalogo();
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
  const btn = $("btn-provedores-sincronizar");
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
    toast(final.texto, "success");
    aposMudarCatalogo();
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
      el("td", {}, [n.teste
        ? el("span", { className: `badge ${n.teste.ok ? "badge-ok" : "badge-falha"}`, title: n.teste.erro || "", textContent: n.teste.ok ? "Passou" : "Reprovado" })
        : el("span", { className: "celula-sub", textContent: n.tier || "—" })])
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
  const itens = escolhaNovosItens.filter(n => n.marcado);
  if (itens.length === 0) return;
  const contagem = $("escolher-novos-contagem");
  try {
    const r = await testarEIncluir(itens, (feito, total) => { contagem.textContent = `Testando ${feito} de ${total}…`; });
    toast(textoResumoTeste(r), r.incluidos.length ? "success" : "warning");
    // Fica no modal mostrando quem reprovou; os aprovados saem da lista.
    escolhaNovosItens = escolhaNovosItens.filter(n => !(n.teste && n.teste.ok));
    for (const n of escolhaNovosItens) if (n.teste && !n.teste.ok) n.marcado = false;
    renderizarEscolhaNovos();
    aposMudarCatalogo();
  } catch (e) {
    toast(`Erro ao incluir modelos: ${e.message}`, "error");
  }
}

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
      toast(`Modelo '${nome}' baixado e instalado com sucesso!`, "success");
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
    const tierSel = $("select-novo-grupo-tier");
    if (tierSel) tierSel.value = "FREE";
    document.querySelectorAll(".chk-papel-novo").forEach(chk => {
      chk.checked = ["chat", "codigo"].includes(chk.value);
    });
    $("modal-novo-grupo").classList.add("open");
  });
}

const btnSalvarNovoGrupo = $("btn-salvar-novo-grupo");
if (btnSalvarNovoGrupo) {
  btnSalvarNovoGrupo.addEventListener("click", async () => {
    const id = $("input-novo-grupo-id").value.trim().toLowerCase();
    const titulo = $("input-novo-grupo-titulo").value.trim();
    const descricao = $("input-novo-grupo-desc").value.trim();
    const tierSel = $("select-novo-grupo-tier");
    const tier = tierSel ? tierSel.value : "FREE";
    const papeis = Array.from(document.querySelectorAll(".chk-papel-novo:checked")).map(c => c.value);

    if (!id || !titulo) {
      toast("Informe o identificador (ID) e o título do grupo.", "error");
      return;
    }
    btnSalvarNovoGrupo.disabled = true;
    try {
      await api("POST", "/api/roteador/grupos/novo", { id, titulo, descricao, tier, papeis, modelos: [] });
      toast(`Grupo '${id}' criado com sucesso!`, "success");
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
  const tierSel = $("select-editar-grupo-tier");
  if (tierSel) tierSel.value = g.tier || "FREE";
  const papeisEsperados = new Set(g.papeis_esperados || ["chat", "codigo"]);
  document.querySelectorAll(".chk-papel-editar").forEach(chk => {
    chk.checked = papeisEsperados.has(chk.value);
  });
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
    const tierSel = $("select-editar-grupo-tier");
    const tier = tierSel ? tierSel.value : undefined;
    const papeis = Array.from(document.querySelectorAll(".chk-papel-editar:checked")).map(c => c.value);
    const ativo = $("check-editar-grupo-ativo").checked;

    btnConfirmarEdicaoGrupo.disabled = true;
    try {
      await api("PATCH", `/api/roteador/grupos/${encodeURIComponent(id)}`, {
        titulo: titulo || null,
        descricao: descricao,
        tier: tier,
        papeis: papeis,
        ativo
      });
      toast(`Grupo '${id}' atualizado com sucesso!`, "success");
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
  await atualizarSeloComfy($("badge-status-comfyui"));

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
  if (fase) fase.textContent = sucesso ? "Concluído com Sucesso!" : "Finalizado com ressalvas";
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
    toast("Prompt traduzido e enriquecido! Veja o resultado no card abaixo.", "success");
  } else {
    tit.textContent = "Prompt em Inglês Mantido";
    txt.textContent = `"${res.prompt || res.prompt_original}"`;
    aviso.style.display = "block";
    toast("Prompt mantido (já detalhado em inglês).", "info");
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
    btnOtimizarManual.textContent = "Otimizando...";
    try {
      const res = await api("POST", "/api/estudio/otimizar-prompt", { prompt: val });
      if (res.ok && res.prompt) {
        exibirAvisoPromptOtimizado(res);
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
    btnModo.textContent = "Sair da edição";
  }
  if (btnGerar) {
    btnGerar.classList.add("btn-inpaint-active");
    btnGerar.innerHTML = `<span>Refazer a área marcada</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 14 4-4-4-4"/><path d="m2 10h20"/></svg>`;
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
    btnModo.textContent = "Editar área";
  }
  if (btnGerar) {
    btnGerar.classList.remove("btn-inpaint-active");
    btnGerar.innerHTML = `<span>Gerar imagem</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/><circle cx="9" cy="9" r="2"/></svg>`;
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
      btnGerarImagem.innerHTML = `<span>Refazendo a área…</span><span class="girando" aria-hidden="true"></span>`;

      try {
        const denoise = parseFloat($("inpaint-slider-denoise").value) || 0.75;
        const res = await api("POST", "/api/estudio/inpaint", {
          imagem_base: ultimaImagemGeradaUrl,
          mascara_base64: maskB64,
          prompt,
          prompt_negativo: promptNegativo,
          denoise,
          steps,
          seed,
          otimizar_prompt: Boolean($("img-otimizar-auto")?.checked)
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
          btnGerarImagem.innerHTML = `<span>Refazer a área marcada</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m18 14 4-4-4-4"/><path d="m2 10h20"/></svg>`;
        } else {
          btnGerarImagem.innerHTML = `<span>Gerar imagem</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/><circle cx="9" cy="9" r="2"/></svg>`;
        }
      }
      return;
    }

    iniciarProgressoGeracao("Gerando Imagem com IA...", "Otimizando prompt e conectando ao motor de inferência...");
    btnGerarImagem.innerHTML = `<span>Gerando imagem…</span><span class="girando" aria-hidden="true"></span>`;

    try {
      const res = await api("POST", "/api/estudio/gerar-imagem", {
        prompt,
        prompt_negativo: promptNegativo,
        motor,
        modelo,
        aspect_ratio: aspectRatioSelecionado,
        steps,
        seed,
        otimizar_prompt: Boolean($("img-otimizar-auto")?.checked)
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
            el("div", { style: "color:var(--warning); font-size:15px; font-weight:600; margin-bottom:6px;" }, ["ComfyUI está Offline (:8188)"]),
            el("div", { style: "color:var(--text-secondary); font-size:12px; margin-bottom:14px; max-width:380px; text-align:center;" }, ["O motor ComfyUI portátil na GPU não está em execução no host."]),
            el("div", { style: "display:flex; gap:8px;" }, [
              el("button", {
                className: "btn btn-primary btn-sm",
                textContent: "Ligar o ComfyUI",
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
      btnGerarImagem.innerHTML = `<span>Gerar imagem</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/><circle cx="9" cy="9" r="2"/></svg>`;
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
      title: `${item.prompt} (clique para abrir)`,
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
      }, [icone("x", 12)])
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
  await atualizarSeloComfy($("badge-status-comfy-video"));
  await carregarCatalogoModelos();
  carregarTrilhasVideo();
  agendarPlanoVideo();
  retomarAcompanhamentoVideoLongo();

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
        el("span", { style: "font-size:11px; font-weight:600; color:var(--brand-primary); display:flex; align-items:center; gap:3px;" }, [
          "",
          el("span", { style: "font-size:11px; color:var(--text-muted);" }, [item.tamanho || "MP4"])
        ]),
        el("button", {
          className: "galeria-thumb-del",
          title: "Excluir clipe",
          style: "position:static; width:16px; height:16px; font-size:11px;",
          onclick: (e) => {
            e.stopPropagation();
            excluirVideoPorUrl(item.url);
          }
        }, [icone("x", 12)])
      ]),
      el("div", { style: "text-align:center; padding:4px 0;" }, [
        el("div", { style: "width:22px; height:22px; margin:0 auto; border-radius:50%; background:rgba(99,102,241,0.15); display:flex; align-items:center; justify-content:center; color:var(--brand-primary);" }, [icone("play", 11)])
      ]),
      el("div", {
        style: "font-family:var(--font-mono); font-size:11px; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:center;"
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
      badgeModo.textContent = "Usa o 1º quadro do vídeo";
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
  if (statusPrev) statusPrev.textContent = "Mídia pronta para renderização";

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
        toast(`Upload de ${file.name} concluído com sucesso!`, "success");
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
          toast("Prompt enriquecido cinematograficamente!", "success");
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
    btnGerar.innerHTML = `<span>Gerando vídeo…</span><span class="girando" aria-hidden="true"></span>`;
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
  if (faseTxt) faseTxt.textContent = msg || (sucesso ? "Vídeo cinematográfico renderizado com sucesso!" : "Inferência interrompida.");

  setTimeout(() => {
    if (container) container.style.display = "none";
    if (barra) barra.style.width = "0%";
  }, 1200);

  if (btnGerar) {
    btnGerar.disabled = false;
    btnGerar.innerHTML = `<span>Gerar vídeo</span><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
  }
}

let jobVideoAtual = null;   // prompt_id em andamento: o cancelar mira só ele
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
  jobVideoAtual = jobId;
  let desconhecidoSeguidos = 0;

  monitoramentoJobVideoInterval = setInterval(async () => {
    try {
      const statusRes = await api("GET", `/api/estudio/status-video/${jobId}`);
      if (!statusRes) return;

      if (statusRes.ok && statusRes.status === "concluido") {
        pararProgressoVideo(true, "Renderização concluída! Carregando player...");
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
          if ($("vid-meta-job")) $("vid-meta-job").textContent = nomeArq;
          if ($("vid-meta-status")) $("vid-meta-status").textContent = "Pronto (ComfyUI)";
          if ($("vid-meta-latencia")) $("vid-meta-latencia").textContent = ` ${statusRes.latencia_ms || 0}ms`;
        }

        toast("Vídeo pronto no player.", "success");
      } else if (statusRes.status === "erro") {
        pararProgressoVideo(false, `Falha: ${statusRes.erro || "Erro no ComfyUI"}`);
        toast(`Erro na renderização: ${statusRes.erro || "Falha desconhecida"}`, "error");
      } else if (statusRes.status === "executando" && statusRes.fase) {
        desconhecidoSeguidos = 0;
        const faseTxt = $("vid-progresso-fase-txt");
        if (faseTxt) faseTxt.textContent = statusRes.fase;
      } else if (statusRes.status === "desconhecido" && ++desconhecidoSeguidos >= 5) {
        // O ComfyUI reiniciou ou o job sumiu do histórico: para de perguntar em vez de repetir para sempre.
        pararProgressoVideo(false, "O ComfyUI não conhece mais este trabalho (reiniciou?).");
        toast("O vídeo em andamento se perdeu: o ComfyUI não tem mais registro dele.", "warning");
      }
    } catch (err) {
      console.warn("Polling de status do vídeo:", err);
    }
  }, 1800);
}

// ------------------------------------------------ Vídeo longo (clipes emendados, local ou nuvem)
// Entra quando a duração passa do maior clipe do modelo ou quando o modelo é de nuvem. O servidor planeja os clipes
// e estima o custo; na nuvem nada sai da máquina sem a caixa de confirmação marcada.
const CHAVE_VIDEO_LONGO = "tudoia_video_longo_ativo";
let videoLongoAtual = null;   // id do trabalho acompanhado agora
let temporizadorPlanoVideo = null;

function infoModeloVideoAtual() {
  const id = $("vid-select-modelo") ? $("vid-select-modelo").value : "";
  return { id, ...(mapaModelosVideo[id] || {}) };
}

function maxSegmentoVideoAtual() {
  const info = infoModeloVideoAtual();
  const res = $("vid-select-resolucao") ? $("vid-select-resolucao").value : "720p";
  return (info.max_segmento_s && info.max_segmento_s[res]) || 5;
}

function ehVideoLongoAtual() {
  const info = infoModeloVideoAtual();
  const duracao = parseInt($("vid-select-duracao").value, 10) || 5;
  return info.tipo === "nuvem" || duracao > maxSegmentoVideoAtual();
}

function cenasDoRoteiro() {
  const texto = $("vid-cenas") ? $("vid-cenas").value : "";
  return texto.split("\n").map(l => l.trim()).filter(Boolean).slice(0, 12);
}

function corpoVideoLongo(prompt) {
  const info = infoModeloVideoAtual();
  const modo = $("vid-select-modo-longo").value;
  const cenas = modo === "cenas" ? cenasDoRoteiro() : [];
  const inputCaminhoVal = $("vid-input-caminho") ? $("vid-input-caminho").value.trim() : "";
  const arquivoRef = (midiaReferenciaCarregada && (midiaReferenciaCarregada.caminho || midiaReferenciaCarregada.url)) || inputCaminhoVal || null;
  return {
    prompt,
    motor: info.tipo === "nuvem" ? "nuvem" : "comfyui",
    modelo: info.id,
    duracao_segundos: parseInt($("vid-select-duracao").value, 10) || 5,
    resolucao: $("vid-select-resolucao").value,
    modo,
    cenas: cenas.length ? cenas : null,
    arquivo_referencia: modoVideoAtual === "t2v" ? null : arquivoRef,
    trilha: $("vid-select-trilha").value || null,
    otimizar_prompt: Boolean($("vid-otimizar-auto")?.checked),
    confirmar_nuvem: Boolean($("vid-confirmar-nuvem")?.checked),
  };
}

const dinheiroUSD = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" });

async function atualizarPlanoVideo() {
  const bloco = $("vid-bloco-longo");
  if (!bloco) return;
  const info = infoModeloVideoAtual();
  const longo = ehVideoLongoAtual();
  bloco.hidden = !longo;
  $("vid-nuvem-box").hidden = info.tipo !== "nuvem";
  $("vid-grupo-cenas").hidden = $("vid-select-modo-longo").value !== "cenas";
  const specs = $("vid-badge-specs");
  if (specs) specs.textContent = info.tipo === "nuvem" ? "nuvem · com áudio" : (/minimax|ltx/i.test(info.id || "") ? "24 fps · com áudio" : "sem áudio");
  if (!longo || !info.id) return;
  const prompt = ($("vid-prompt").value || "").trim() || "plano";
  try {
    const est = await api("POST", "/api/estudio/video-longo/estimar", { ...corpoVideoLongo(prompt), cenas: null, confirmar_nuvem: false });
    const partes = est.segmentos.join(" s + ") + " s";
    const onde = est.nuvem ? "na nuvem" : "no ComfyUI local";
    $("vid-plano-info").textContent = `${est.clipes} clipe(s) ${onde}: ${partes}.` +
      (est.continuidade_por_quadro ? "" : " Este modelo não recebe quadro inicial: a continuidade vem só do texto.");
    if (est.nuvem) {
      const teto = est.teto_usd != null ? ` · teto ${dinheiroUSD.format(est.teto_usd)}` : "";
      $("vid-nuvem-custo").textContent = est.chave_presente
        ? `Custo estimado: ${dinheiroUSD.format(est.custo_estimado_usd)} (${est.segundos_gerados} s × ${dinheiroUSD.format(est.preco_usd_s)}/s)${teto}`
        : `Configure ${est.chave} em Chaves e segredos para usar este modelo.`;
    }
  } catch (e) {
    $("vid-plano-info").textContent = `Não foi possível planejar: ${e.message}`;
  }
}

function agendarPlanoVideo() {
  clearTimeout(temporizadorPlanoVideo);
  temporizadorPlanoVideo = setTimeout(atualizarPlanoVideo, 250);
}

["vid-select-modelo", "vid-select-duracao", "vid-select-resolucao", "vid-select-modo-longo"].forEach(id => {
  const elemento = $(id);
  if (elemento) elemento.addEventListener("change", agendarPlanoVideo);
});

async function carregarTrilhasVideo() {
  const sel = $("vid-select-trilha");
  if (!sel) return;
  try {
    const r = await api("GET", "/api/estudio/musicas");
    const atual = sel.value;
    sel.replaceChildren(el("option", { value: "", textContent: "Som dos próprios clipes (quando todos têm)" }));
    (r.musicas || []).forEach(m => sel.appendChild(el("option", { value: m.nome, textContent: `Trilha: ${m.nome}` })));
    sel.value = atual;
  } catch (e) {
    console.warn("Trilhas do Estúdio de música indisponíveis:", e);
  }
}

function mostrarRetomarVideo(trabalho) {
  const box = $("vid-retomar-box");
  if (!box) return;
  const podeRetomar = trabalho && ["erro", "interrompido", "cancelado"].includes(trabalho.estado);
  box.hidden = !podeRetomar;
  if (podeRetomar) {
    $("vid-retomar-texto").textContent = `Vídeo longo parado em ${trabalho.clipes_prontos}/${trabalho.clipes_total} clipes` +
      (trabalho.erro ? `: ${trabalho.erro}` : ".");
    $("vid-progresso-container").style.display = "flex";
  }
}

function concluirVideoLongo(t) {
  localStorage.removeItem(CHAVE_VIDEO_LONGO);
  pararProgressoVideo(true, "Vídeo longo pronto! Carregando player...");
  selecionarVideoPlayer(t.video_url, t.nome_arquivo);
  galeriaVideosSessao = galeriaVideosSessao.filter(v => v.nome !== t.nome_arquivo);
  galeriaVideosSessao.unshift({ url: t.video_url, nome: t.nome_arquivo, tamanho: `${t.pedido.duracao_total_s}s` });
  renderizarGaleriaVideos();
  toast("Vídeo longo pronto no player.", "success");
}

function monitorarVideoLongo(trabalho) {
  videoLongoAtual = trabalho.id;
  localStorage.setItem(CHAVE_VIDEO_LONGO, trabalho.id);
  $("vid-retomar-box").hidden = true;
  iniciarProgressoVideo(trabalho.pedido.duracao_total_s, trabalho.pedido.modelo);
  // o progresso aqui é real (clipes prontos), não a curva estimada do clipe único
  clearInterval(timerProgressoVideoInterval);
  timerProgressoVideoInterval = setInterval(() => {
    const t = $("vid-progresso-timer");
    if (t) t.textContent = `${((Date.now() - tempoInicioVideo) / 1000).toFixed(0)}s`;
  }, 1000);
  const atualizar = t => {
    const fase = $("vid-progresso-fase-txt");
    if (fase) fase.textContent = `${t.fase} · ${t.clipes_prontos}/${t.clipes_total} clipes`;
    const barra = $("vid-progresso-barra");
    if (barra) barra.style.width = `${Math.max(4, Math.round(t.clipes_prontos / Math.max(1, t.clipes_total) * 92))}%`;
    const detalhe = $("vid-progresso-detalhe");
    if (detalhe) detalhe.textContent = t.pedido.motor === "nuvem"
      ? `Nuvem (${t.pedido.modelo}) · estimativa ${dinheiroUSD.format(t.custo_estimado_usd || 0)}`
      : `ComfyUI local (${t.pedido.modelo}) · ${t.pedido.modo === "cenas" ? "cenas com cortes" : "plano contínuo"}`;
  };
  atualizar(trabalho);
  clearInterval(monitoramentoJobVideoInterval);
  monitoramentoJobVideoInterval = setInterval(async () => {
    try {
      const r = await api("GET", `/api/estudio/video-longo/${trabalho.id}`);
      const t = r.trabalho;
      atualizar(t);
      if (t.estado === "concluido") {
        videoLongoAtual = null;
        concluirVideoLongo(t);
      } else if (["erro", "interrompido", "cancelado"].includes(t.estado)) {
        pararProgressoVideo(false, t.estado === "cancelado" ? "Vídeo longo cancelado." : `Falha: ${t.erro || t.fase}`);
        setTimeout(() => mostrarRetomarVideo(t), 1300);
      }
    } catch (e) {
      if (e.status === 404) {
        localStorage.removeItem(CHAVE_VIDEO_LONGO);
        videoLongoAtual = null;
        pararProgressoVideo(false, "O trabalho de vídeo longo não existe mais.");
      } else {
        console.warn("Polling do vídeo longo:", e);
      }
    }
  }, 3000);
}

async function gerarVideoLongo(prompt) {
  const corpo = corpoVideoLongo(prompt);
  if (corpo.motor === "nuvem" && !corpo.confirmar_nuvem) {
    toast("Marque a autorização de envio e cobrança para gerar na nuvem.", "warning");
    $("vid-confirmar-nuvem").focus();
    return;
  }
  try {
    const r = await api("POST", "/api/estudio/video-longo", corpo);
    toast(`Vídeo longo iniciado: ${r.trabalho.clipes_total} clipe(s).`, "info");
    monitorarVideoLongo(r.trabalho);
  } catch (e) {
    toast(`Não foi possível iniciar o vídeo longo: ${e.message}`, "error");
  }
}

const btnRetomarVideo = $("btn-retomar-video");
if (btnRetomarVideo) {
  btnRetomarVideo.addEventListener("click", async () => {
    const id = videoLongoAtual || localStorage.getItem(CHAVE_VIDEO_LONGO);
    if (!id) return;
    try {
      const r = await api("POST", `/api/estudio/video-longo/${id}/retomar`, { confirmar_nuvem: Boolean($("vid-confirmar-nuvem")?.checked) });
      monitorarVideoLongo(r.trabalho);
    } catch (e) {
      toast(e.codigo === "confirmacao_necessaria" ? "Marque a autorização de envio e cobrança para retomar na nuvem." : `Falha ao retomar: ${e.message}`, "warning");
    }
  });
}

async function retomarAcompanhamentoVideoLongo() {
  const id = localStorage.getItem(CHAVE_VIDEO_LONGO);
  if (!id) return;
  try {
    const r = await api("GET", `/api/estudio/video-longo/${id}`);
    const t = r.trabalho;
    if (t.estado === "concluido") {
      localStorage.removeItem(CHAVE_VIDEO_LONGO);
    } else if (["na_fila", "executando"].includes(t.estado)) {
      monitorarVideoLongo(t);
    } else {
      videoLongoAtual = t.id;
      mostrarRetomarVideo(t);
    }
  } catch {
    localStorage.removeItem(CHAVE_VIDEO_LONGO);
  }
}

// Botão Cancelar Geração de Vídeo
const btnCancelarVideo = $("btn-cancelar-video");
if (btnCancelarVideo) {
  btnCancelarVideo.addEventListener("click", async () => {
    try {
      btnCancelarVideo.disabled = true;
      if (videoLongoAtual) {
        toast("Cancelando o vídeo longo (clipe já enviado à nuvem continua cobrado)...", "warning");
        await api("POST", `/api/estudio/video-longo/${videoLongoAtual}/cancelar`, {});
        return;   // o polling mostra o estado "cancelado" e o botão Retomar
      }
      toast("Solicitando cancelamento imediato ao ComfyUI...", "warning");
      const res = await api("POST", "/api/estudio/cancelar", jobVideoAtual ? { prompt_id: jobVideoAtual } : {});
      if (res.ok) {
        toast("Inferência interrompida no ComfyUI!", "info");
      }
    } catch (e) {
      toast(`Falha ao cancelar: ${e.message}`, "error");
    } finally {
      btnCancelarVideo.disabled = false;
      if (!videoLongoAtual) pararProgressoVideo(false, "Inferência cancelada pelo usuário.");
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

    if (ehVideoLongoAtual()) {
      await gerarVideoLongo(prompt);
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
        modo_execucao: "async",
        otimizar_prompt: Boolean($("vid-otimizar-auto")?.checked)
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

        toast("Renderização iniciada na GPU.", "info");
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
            el("div", { style: "color:var(--warning); font-size:15px; font-weight:600; margin-bottom:6px;" }, ["ComfyUI está Offline"]),
            el("div", { style: "color:var(--text-secondary); font-size:12px; margin-bottom:14px; max-width:400px; text-align:center;" }, [e.message]),
            el("div", { style: "display:flex; gap:8px;" }, [
              el("button", {
                className: "btn btn-primary btn-sm",
                textContent: "Ligar o ComfyUI",
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
// ------------------------------------------------ 0. INÍCIO (visão geral e pendências)
// Monta a tela a partir das APIs que já existem. Cada fonte é independente: se uma falhar, as outras aparecem e
// a falha vira uma pendência, em vez de deixar a tela vazia.
const numeroBR = new Intl.NumberFormat("pt-BR");
const dolarBR = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 4 });

function cardNumero({ rotulo, icone: nomeIcone, valor, unidade, detalhe, estado, href }) {
  const filhos = [
    el("span", { className: "stat-rotulo" }, [icone(nomeIcone), rotulo]),
    el("span", { className: "stat-valor" }, [valor, unidade ? el("small", { textContent: unidade }) : null]),
    detalhe ? el("span", { className: "stat-detalhe", textContent: detalhe }) : null,
  ];
  const attrs = { className: `stat${estado ? " " + estado : ""}` };
  if (href) attrs.href = href;
  return el(href ? "a" : "div", attrs, filhos);
}

function itemPendencia(estado, texto, href, rotuloLink) {
  const nomeIcone = estado === "ok" ? "circleCheck" : estado === "falha" ? "circleX" : "triangleAlert";
  return el("li", { className: estado }, [
    icone(nomeIcone, 16),
    el("span", { textContent: texto }),
    href ? el("a", { href, textContent: rotuloLink }) : null,
  ]);
}

async function carregarInicio() {
  const stats = $("inicio-stats");
  const lista = $("inicio-pendencias");
  const [servicos, hardware, telemetria, governanca, provedores] = await Promise.allSettled([
    api("GET", "/api/servicos"),
    api("GET", "/api/hardware"),
    api("GET", "/api/telemetria"),
    api("GET", "/api/governanca"),
    api("GET", "/api/provedores"),
  ]);
  const cards = [];
  const pendencias = [];

  if (servicos.status === "fulfilled") {
    const lista = servicos.value || [];
    const parados = lista.filter((s) => !s.ativo);
    cards.push(cardNumero({
      rotulo: "Serviços no ar", icone: "server", href: "#servicos",
      valor: `${lista.length - parados.length}`, unidade: `de ${lista.length}`,
      estado: parados.length ? "aviso" : "ok",
      detalhe: parados.length ? `Parados: ${parados.map((s) => s.titulo).join(", ")}` : "Todos funcionando",
    }));
    for (const s of parados) pendencias.push(itemPendencia("aviso", `${s.titulo} está parado.`, "#servicos", "Ver serviços"));
  } else {
    pendencias.push(itemPendencia("falha", `Não foi possível ler os serviços: ${servicos.reason.message}`));
  }

  if (hardware.status === "fulfilled" && hardware.value.gpu) {
    const g = hardware.value.gpu;
    cards.push(cardNumero({
      rotulo: "Memória de vídeo", icone: "cpu", href: "#hardware",
      valor: numeroBR.format(g.vram_usada_gb ?? 0), unidade: `de ${numeroBR.format(g.vram_total_gb ?? 0)} GB`,
      estado: (g.vram_pct ?? 0) >= 90 ? "aviso" : null,
      detalhe: g.nome || "GPU",
    }));
  }

  if (telemetria.status === "fulfilled") {
    const t = telemetria.value;
    const falhas = (t.feed || []).filter((f) => String(f.status).toLowerCase() === "failure").length;
    cards.push(cardNumero({
      rotulo: "Requisições em 24 h", icone: "activity", href: "#telemetria",
      valor: numeroBR.format(t.total_requisicoes || 0),
      detalhe: `${numeroBR.format(t.total_tokens || 0)} tokens · ${t.taxa_sucesso ?? 100}% com sucesso`,
      estado: falhas ? "aviso" : null,
    }));
    cards.push(cardNumero({
      rotulo: "Custo em 24 h", icone: "coins", href: "#limites",
      valor: dolarBR.format(t.custo_total_usd || 0), detalhe: "Provedores pagos",
    }));
    if (falhas) {
      pendencias.push(itemPendencia("aviso", `${falhas} das últimas ${(t.feed || []).length} requisições falharam.`, "#telemetria", "Ver atividade"));
    }
  }

  if (governanca.status === "fulfilled") {
    const g = governanca.value;
    if (g.drift && g.drift.length) {
      pendencias.push(itemPendencia("aviso", `${g.drift.length} arquivo(s) de agentes fora de sincronia.`, "#governanca", "Sincronizar"));
    }
    for (const [mcp, chaves] of Object.entries(g.alertas_mcp || {})) {
      pendencias.push(itemPendencia("aviso", `O MCP ${mcp} precisa da chave ${chaves.join(", ")}.`, "#segredos", "Configurar chave"));
    }
  }

  if (provedores.status === "fulfilled") {
    for (const p of provedores.value || []) {
      if (!p.tem_chave && p.modelos_ativos > 0) {
        pendencias.push(itemPendencia("aviso", `${p.nome} tem ${p.modelos_ativos} modelo(s) ativo(s) mas está sem chave.`, "#provedores", "Ver provedor"));
      }
    }
  }

  stats.replaceChildren(...cards);
  if (!pendencias.length) pendencias.push(itemPendencia("ok", "Nada pendente. Serviços, chaves e agentes estão em ordem."));
  lista.replaceChildren(...pendencias);
}

$("btn-atualizar-inicio").addEventListener("click", carregarInicio);

const hashInicial = window.location.hash.replace("#", "");
ativarAba(hashInicial && $(`view-${hashInicial}`) ? hashInicial : "inicio");
// Estado do topo (online/parcial) é atualizado já na abertura, mesmo que a aba inicial não seja a de serviços.
carregarServicos();


// =====================================================================
// ESTÚDIO DE MÚSICA & TRILHAS SONORAS (YuE 2 · ComfyUI)
// =====================================================================
let galeriaMusicasSessao = [];
let ultimaMusicaGeradaUrl = null;

async function carregarMusicas() {
  await atualizarSeloComfy($("badge-status-comfy-musica"));

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
        el("span", { style: "font-size:11px; font-weight:600; color:#10b981; display:flex; align-items:center; gap:3px;" }, [
          "",
          el("span", { style: "font-size:11px; color:var(--text-muted);" }, [item.tamanho || "FLAC"])
        ]),
        el("button", {
          className: "galeria-thumb-del",
          title: "Excluir faixa",
          style: "position:static; width:16px; height:16px; font-size:11px;",
          onclick: (e) => {
            e.stopPropagation();
            excluirMusicaPorUrl(item.url);
          }
        }, [icone("x", 12)])
      ]),
      el("div", { style: "text-align:center; padding:4px 0;" }, [
        el("div", { style: "width:22px; height:22px; margin:0 auto; border-radius:50%; background:rgba(16,185,129,0.15); display:flex; align-items:center; justify-content:center; color:#10b981;" }, [icone("play", 11)])
      ]),
      el("div", {
        style: "font-family:var(--font-mono); font-size:11px; color:var(--text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; text-align:center;"
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
          toast("Estilo musical enriquecido para o YuE 2!", "success");
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
  if (faseTxt && sucesso) faseTxt.textContent = "Música sintetizada com sucesso!";

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
        btnGerar.innerHTML = `<span>Gerar música</span><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
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
    btnGerarMusica.innerHTML = `<span>Compondo Música (${duracao}s)...</span><span class="girando" aria-hidden="true"></span>`;

    iniciarProgressoMusica(duracao > 30 ? 60 : 35);

    try {
      const res = await api("POST", "/api/estudio/gerar-musica", {
        style,
        lyrics: lyrics || "[instrumental]",
        duracao_segundos: duracao,
        modo,
        modelo,
        otimizar_prompt: Boolean($("mus-otimizar-auto")?.checked)
      });

      if (res.ok && res.audio_url) {
        pararProgressoMusica(true);
        toast(`Música sintetizada com sucesso em ${(res.latencia_ms / 1000).toFixed(1)}s!`, "success");

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
      btnGerarMusica.innerHTML = `<span>Gerar música</span><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
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
