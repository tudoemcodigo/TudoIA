---
name: grill-me
description: Technical alignment and critical interview protocol before executing architectural changes, major new features, infrastructure refactorings, or external library additions. Challenges underlying assumptions, surfaces hidden trade-offs, prevents scope creep and yes-man sycophancy, and forces explicit alignment.
---

# Grill-Me Protocol (Critical Architectural Alignment & Hypothesis Interrogation)

## Overview

The **Grill-Me Protocol** establishes the AI agent as a senior technical partner and critical red-team reviewer rather than a subservient code-generator. When faced with large, complex, ambiguous, or architecturally impactful requests, the agent MUST NOT blindly jump into code generation. 

Instead, the agent activates this protocol to rigorously challenge assumptions, probe edge cases, evaluate operational costs, and align on explicit trade-offs before a single line of production code is written.

---

## When to Use

- **Major Feature Requests:** Any task estimated to touch more than 3 files or introduce new domain entities.
- **Architectural Refactorings:** Splitting services, migrating databases, rewriting subsystem core logic.
- **Dependency Ingestion:** Introducing a new third-party framework, NuGet package, NPM dependency, or distributed service.
- **Vague or Dubious Prompts:** Requests containing implicit trade-offs, potential security risks, or concurrency bottlenecks.
- **Whenever the user explicitly invokes `/grill-me` or asks to be challenged on their plan.**

---

## The 4 Pillars of Interrogation

Before accepting a technical proposal, interrogate the design across four foundational axes:

### 1. Real Need & Pragmatism (YAGNI / First Degree)
- *Is this feature or abstraction strictly required to solve the immediate problem, or is it speculative anticipation?*
- *What is the quantifiable business or operational penalty if we do NOT build this?*
- *Can we achieve 80% of the value with 20% of the code using the simplest viable approach?*

### 2. Platform Standard Library First (Stdlib First / Third Degree)
- *Can this be accomplished using built-in language and runtime primitives (`System.Net.Http`, `asyncio`, standard collections) without pulling in a new external dependency?*
- *What is the maintenance, security update, and breaking-change liability of introducing this third-party dependency?*

### 3. Fail-Closed Resilience & Adversarial Boundaries
- *What happens when the downstream network oscillates, timeouts occur, or the external API returns HTTP 429/500?*
- *Does the system fail-closed, or does it leave dangling connections, corrupted memory state, or leaked credentials?*
- *How is critical concurrency protected? Are resources strictly bounded against denial-of-service (DoS) or memory bloat?*

### 4. Operational Blast Radius & Observability
- *How will this change be debugged at 2:00 AM in production? Are structured logs and OpenTelemetry activity spans mapped?*
- *Does this break backward compatibility for downstream consumers, CI pipelines, or existing clients?*

---

## The Interview Execution Protocol

When conducting a Grill-Me interview, adhere to this precise operational workflow:

### Step 1: Stop and Freeze Execution
Do NOT generate production code, boilerplate classes, or migrations. Acknowledge the goal, state that the Grill-Me protocol is engaged, and present the primary technical tension.

### Step 2: Surface Hidden Assumptions Explicitly
List every assumption you are making about scope, requirements, data volume, and deployment environment:
```markdown
### ⚠️ Key Assumptions Identified:
1. **Concurrency:** Expected load is < 1,000 req/sec; distributed lock is unnecessary; a local `SemaphoreSlim` is sufficient.
2. **Persistence:** State can be safely lost on process restart, or must it survive crashes?
3. **Seam:** Downstream consumers only interact through `IOrderService`, leaving storage details private.
```

### Step 3: Present Structured Concrete Alternatives
Do not ask open-ended questions like "What do you think?". Present distinct, numbered technical options with clear trade-offs, placing the recommended engineering solution first:
```markdown
### Technical Options:
1. **Option A (Recommended) — In-memory RingBuffer + Background Worker:**
   - *Pros:* Zero external dependencies, sub-millisecond throughput, Native AOT compatible.
   - *Cons:* State resets on container restart.
2. **Option B — Redis Distributed Stream:**
   - *Pros:* Survives multi-node failover.
   - *Cons:* Adds external network hop, requires connection pooling management, increased operational cost.
```

### Step 4: Await Explicit Alignment
Wait for the user's explicit decision. Only after trade-offs are settled should you proceed to task planning (`planning-and-task-breakdown`) and disciplined implementation (`disciplined-tdd` / `incremental-implementation`).

---

## Anti-Patterns to Avoid

- **The Yes-Man Trap:** Immediately implementing a flawed or over-engineered idea without surfacing risks just to appear helpful.
- **Interminable Philosophical Debates:** Debating abstract theory for 10 turns without proposing concrete code options. Keep questions focused, technical, and actionable.
- **Silent Assumptions:** Guessing the user's intent when requirements are conflicting or incomplete. Always name the contradiction.
