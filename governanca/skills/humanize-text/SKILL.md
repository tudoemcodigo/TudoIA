---
name: humanize-text
description: Crafts, reviews, and refines written content to sound natural, authentic, and genuinely human-authored, eliminating artificial intelligence tells and robotic slop. Use whenever drafting or polishing articles, documentation, essays, emails, announcements, PR descriptions, or when asked to "humanize", "remove AI slop", or "make it sound like a real person". Based on real-world editorial standards, Wikipedia's "Signs of AI-generated text", and bilingual (EN/PT) slop eradication principles.
---

# Humanize Text (Anti-AI Slop & Authentic Voice Standard)

## Overview

Large Language Models (LLMs) suffer from predictable statistical convergence: repetitive cadence, hyperbolic praise, artificial structural symmetries, and formulaic transition phrases. This skill systematically eliminates those synthetic artifacts, transforming robotic prose into direct, authentic, rhythmic, and engaging human communication.

---

## When to Use

- Writing or reviewing blog posts, essays, public documentation, tutorials, or guides.
- Polishing release notes, PR summaries, and architectural design records (ADRs).
- Crafting announcements, technical communications, and stakeholder emails.
- When explicitly prompted to "humanize", "make it sound human", "tirar cara de IA", or "revisar texto com voz autêntica".

---

## Core Philosophy

1. **Information Over Packaging:** Humans communicate because they have something concrete to say. AI generates packaging first, then pads it with abstract claims. Cut the wrapping; start with the signal.
2. **Dynamic Rhythm & Metric Variety:** AI prose clusters around identical sentence lengths (18–25 words). Real human writing alternates between punchy statements and descriptive clauses.
3. **Restraint and Emotional Grounding:** Resist breathless cheerleading. If something is effective, demonstrate it through facts, measurable numbers, and code examples — never through empty superlatives.
4. **Preserve Exact Technical Precision:** Never modify code blocks, variable names, URLs, commit hashes, formulas, architectural boundaries, or cited benchmark numbers.

---

## The 16 AI Slop Patterns (Bilingual Detection & Remediation)

Every agent must be vigilant against these 16 statistical markers in both English and Portuguese:

### 1. The "Not Just X, But Y" Antithesis / A Embalagem "Não é apenas X, mas sim Y"
- **The Problem:** The most notorious LLM rhetorical formula. Falsely elevates trivial features by juxtaposing them against a diminished strawman.
- **EN Tell:** *"It's not just a caching layer; it's a paradigm shift in distributed resilience."*
- **PT Tell:** *"Não é apenas uma camada de cache; é uma verdadeira revolução na resiliência distribuída."*
- **Remediation:** State what the thing is plainly: *"The caching layer reduces p99 database query latency to under 5ms."*

### 2. Triads & The Compulsive Rule of Three / Tríades Forçadas
- **The Problem:** Grouping adjectives, nouns, or clauses in rigid threes in almost every paragraph.
- **EN Tell:** *"Fast, reliable, and scalable...", "designed to inspire, empower, and transform."*
- **PT Tell:** *"Rápido, seguro e escalável...", "criado para capacitar, transformar e revolucionar."*
- **Remediation:** Break the predictable cadence. Use one precise adjective, two distinct points, or a concrete list of four when necessary.

### 3. Solemn Buzzwords & AI "Power Words" / Palavras Solenes de Preenchimento
- **The Problem:** Words that appear with unnaturally high frequency in LLM training data.
- **EN Slop Words:** *delve, tapestry, beacon, testament, pivotal, crucial, journey, realm, landscape, foster, harness, vibrant, intricate, seamless, game-changer, unlock, elevate, cornerstone*.
- **PT Slop Words:** *adentrar, mergulhar, tapeçaria, farol, testemunho, crucial, jornada, ecossistema vibrante, impulsionar, orquestrar, desvendar, divisor de águas, potencializar, pedra angular*.
- **Remediation:** Replace with everyday Anglo-Saxon / plain Romance verbs: use *examine* or *look into* instead of *delve*; use *important* instead of *pivotal*; use *help* instead of *foster*.

### 4. Formulaic "Title : Subtitle" & "Beyond X" Headers / Títulos Clichês
- **The Problem:** Generic dramatic titles that feel like student essays or promotional blog spam.
- **EN Tell:** *"Beyond Code: The Dance Between Architecture and Agility", "Navigating the Changing Landscape of Microservices".*
- **PT Tell:** *"Além do Código: A Dança entre Arquitetura e Agilidade", "Navegando pelo Futuro dos Microsserviços".*
- **Remediation:** Use clear, descriptive, functional titles: *"Benchmarking Cache Eviction Policies in High-Throughput Services"*.

### 5. Inflated Metaphors / Metáforas Teatrais Infladas
- **The Problem:** Describing mundane technical software as grand cosmic or biological phenomena.
- **EN Tell:** *"A rich symphony of microservices working in perfect harmony across the cloud tapestry."*
- **PT Tell:** *"Uma verdadeira sinfonia de microsserviços atuando em harmonia no tecido conectivo da nuvem."*
- **Remediation:** Speak literally: *"The microservices communicate asynchronously via Kafka topics."*

### 6. Colon Overuse / Dois-Pontos Explicativos em Toda Sentença
- **The Problem:** Using colons to announce explanations dramatically in every other line.
- **EN Tell:** *"The result: unmatched speed. The reason: a zero-allocation parser."*
- **PT Tell:** *"O resultado: velocidade incomparável. A razão: um parser com zero alocações."*
- **Remediation:** Write complete, connected declarative sentences without treating every sentence like a keynote slide.

### 7. Em-Dash Addiction (—) / Vício em Travessão Duplo
- **The Problem:** Compulsively breaking sentence flow with em-dashes for manufactured suspense.
- **EN/PT Tell:** *"This approach — which took months of intense research — completely reshaped our pipeline — and our bottom line."*
- **Remediation:** Limit em-dashes to instances where an abrupt break or aside is genuinely warranted. Use commas, parentheses, or separate sentences.

### 8. Decorative Emojis on Every Bullet Point / Emojis Decorativos Compulsivos
- **The Problem:** Decorating technical lists with uniform thematic emojis (🚀, 💡, 🔍, 🛡️, 📈, ⚡).
- **Remediation:** In technical documentation, code reviews, and serious engineering posts, use clean Markdown bullet points (`-`). Reserve emojis only for explicit product UI badges or playful informal context when requested.

### 9. Passive Voice & Excessive Impersonality / Voz Passiva Burocrática
- **The Problem:** Evading ownership and clarity by writing in detached bureaucratic passive voice.
- **EN Tell:** *"It should be noted that optimizations were carried out by the team..."*
- **PT Tell:** *"Pode-se observar que otimizações foram implementadas pela equipe..."*
- **Remediation:** Use active, direct voice: *"We profiled the queries and removed two table scans."*

### 10. Rhetorical Opening Questions / Perguntas Retóricas de Abertura
- **The Problem:** Opening an article or section with a condescending question to hook the reader.
- **EN Tell:** *"Have you ever wondered how high-scale distributed caches survive catastrophic power loss?"*
- **PT Tell:** *"Você já se perguntou como caches distribuídos de alta escala sobrevivem a quedas de energia?"*
- **Remediation:** Jump straight into the thesis or fact: *"Distributed caches survive power loss by flushing write-ahead logs to NVMe drives before acknowledging commits."*

### 11. Formulaic Transitional Signposts / Marcadores de Transição de Redação
- **The Problem:** Stiff connective tissue that adds zero information.
- **EN Tell:** *Furthermore, Notably, It is worth noting, It goes without saying, In today's fast-paced world, To begin with*.
- **PT Tell:** *Vale ressaltar, É importante lembrar, Cabe destacar, No mundo dinâmico de hoje, Primeiramente*.
- **Remediation:** Delete the transition entirely. If two sentences are conceptually coherent, they flow naturally without verbal glue.

### 12. School-Essay Conclusions ("In Summary" & "Looking Ahead") / Conclusões Clichês
- **The Problem:** Wrapping up with a boilerplate paragraph summarizing what was just read or predicting an optimistic future.
- **EN Tell:** *"In conclusion, while hurdles remain, the future of distributed systems is brighter than ever as we forge ahead."*
- **PT Tell:** *"Em suma, apesar dos desafios existentes, o futuro dos sistemas distribuídos é promissor se houver equilíbrio."*
- **Remediation:** Stop writing as soon as the final substantive point is made. Strong human writing concludes on the last concrete insight.

### 13. Breathless Press-Release Enthusiasm / Tom de Assessoria de Imprensa
- **The Problem:** Treating standard software functionality as a groundbreaking spectacle.
- **EN Tell:** *"This feature plays a vital and game-changing role in delivering an unforgettable developer experience."*
- **PT Tell:** *"Essa funcionalidade desempenha um papel vital e encantador, proporcionando uma experiência sem precedentes."*
- **Remediation:** Maintain professional sobriety. Let the utility speak through the code and data.

### 14. Forced Elegant Variation / Medo de Repetir o Substantivo Técnico
- **The Problem:** Cycling through contrived synonyms in a single paragraph to avoid repeating an exact noun.
- **EN/PT Tell:** Calling PostgreSQL "the relational engine", then "the data vault", then "the persistent storage backbone" within 3 sentences.
- **Remediation:** Repeat the precise technical term (*PostgreSQL* or *the database*). In technical engineering, consistency beats thesaurus acrobatics.

### 15. Chatbot Politeness & Delivery Leftovers / Resíduos de Chatbot
- **The Problem:** Leaving conversational wrapper greetings and sign-offs in the final deliverable.
- **EN/PT Tell:** *"Sure! Here is the revised text:", "I hope this helps!", "Let me know if you need further tweaks!"*
- **Remediation:** Deliver the clean text directly without conversational baggage.

### 16. False Broad Ranges / Amplitude Falsa de Escopo
- **The Problem:** Claiming universal applicability with dramatic polar opposites.
- **EN Tell:** *"From nimble garage startups to Fortune 500 corporate giants..."*
- **PT Tell:** *"Desde pequenas startups de garagem até gigantes multinacionais da Fortune 500..."*
- **Remediation:** Specify the actual intended audience or scope: *"Built for teams managing clusters between 50 and 500 nodes."*

---

## The Humanization Checklist

Before considering any text finalized, run this quick editorial audit:

- [ ] **First sentence test:** Does it open with concrete substance, or a rhetorical question / throat-clearing fluff?
- [ ] **Adjective purge:** Did you strip out *tapestry / tapeçaria*, *delve / adentrar*, *pivotal / crucial*, *vibrant / vibrante*?
- [ ] **Rhythm check:** Are sentence lengths varied? Read a paragraph aloud; does it sound like a human talking or a synthesized speech engine?
- [ ] **Conclusion check:** Did you delete the "In conclusion / Em suma" paragraph and end on the last actionable takeaway?
- [ ] **Code & Data preservation:** Are code snippets, parameters, metrics, and references 100% untouched?
