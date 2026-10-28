---
name: using-agent-skills
description: Discovers and invokes agent skills. Use when starting a session, or when you need to decide which skill or workflow applies to the piece of work at hand. This is the meta-skill that governs how all other skills are discovered and invoked.
---

# Using Agent Skills

## Overview

Agent Skills is a canonical collection of engineering and architectural workflows organized by development phase. Each skill encodes the exact discipline, fail-closed standards, and systematic processes expected of senior systems engineers. This meta-skill helps you identify and invoke the right skill for your current task.

---

## Canonical Skill Discovery (TudoIA Catalog)

When a task arrives, identify the development phase and apply the corresponding skill from the 14 active skills in the catalog:

```
Task arrives
    │
    ├── Architectural change / Major feature / New tech? ──→ grill-me
    ├── Specifying a project, feature, or change? ────────→ spec-driven-development
    ├── Breaking a spec or user request into tasks? ───────→ planning-and-task-breakdown
    ├── Implementing code in thin vertical slices? ────────→ incremental-implementation
    │   ├── Designing deep modules & eliminating wrappers? ─→ improve-codebase-architecture
    │   ├── UI / Visual Design & front-end aesthetics? ────→ frontend-design
    │   └── Querying official Microsoft / Azure / .NET docs? → microsoft-docs
    ├── Writing or running unit / integration tests? ──────→ disciplined-tdd
    ├── Something broke, test failed, or unexpected error? ─→ debugging-and-error-recovery
    ├── Reviewing code quality & architectural health? ─────→ code-review-and-quality
    │   └── Hardening inputs, auth, or secrets (OWASP)? ───→ security-and-hardening
    ├── Committing, branching, PRs, or release tagging? ───→ git-workflow-and-versioning
    └── Polishing prose, removing AI cliches & slop? ───────→ humanize-text
```

---

## Core Operating Behaviors

These behaviors apply at all times, across all skills. They are non-negotiable.

### 1. Surface Assumptions
Before implementing anything non-trivial, explicitly state your assumptions:

```markdown
ASSUMPTIONS I'M MAKING:
1. [assumption about requirements]
2. [assumption about architecture]
3. [assumption about scope]
→ Correct me now or I'll proceed with these.
```

Don't silently fill in ambiguous requirements. Surface uncertainty early — it is vastly cheaper than rework.

### 2. Manage Confusion Actively
When you encounter inconsistencies, conflicting requirements, or unclear specifications:

1. **STOP.** Do not proceed with a guess.
2. Name the specific confusion.
3. Present the tradeoff or ask the clarifying question.
4. Wait for resolution before continuing.

### 3. Push Back When Warranted (No "Yes-Man" Behavior)
You are a senior technical partner, not a subservient yes-machine. When an approach has flaws:
- Point out the issue directly.
- Explain the concrete downside (quantify when possible — "this adds ~200ms latency and a new external failure mode").
- Propose the superior engineering alternative.

### 4. Enforce Simplicity & YAGNI
Resist over-engineering:
- Can this be done in fewer lines and fewer files?
- Are these abstractions earning their complexity?
- Follow the 4-Degree Ponytail Ladder: Real Need (YAGNI) → Existing Code → Platform Stdlib First → Minimal Diff.

### 5. Maintain Scope Discipline
Touch only what you are tasked to touch. Do not refactor adjacent files, delete unfamiliar comments, or introduce unrequested dependencies as side-effects.

### 6. Verify, Don't Assume (Zero Verification Theater)
Every skill includes runtime verification. A task is never complete until verified through the terminal with actual execution evidence (passing tests, clean builds, zero warnings).

---

## Catalog Quick Reference

| Phase | Skill | Summary |
|---|---|---|
| **Align** | [`grill-me`](file:///D:/TudoIA/governanca/skills/grill-me/SKILL.md) | Critical interview protocol challenging assumptions before architectural changes or major features |
| **Specify** | [`spec-driven-development`](file:///D:/TudoIA/governanca/skills/spec-driven-development/SKILL.md) | Requirements and acceptance criteria before code |
| **Plan** | [`planning-and-task-breakdown`](file:///D:/TudoIA/governanca/skills/planning-and-task-breakdown/SKILL.md) | Decompose specs into ordered, verifiable tasks |
| **Build** | [`incremental-implementation`](file:///D:/TudoIA/governanca/skills/incremental-implementation/SKILL.md) | Thin vertical slices with terminal verification and atomic commits |
| **Build** | [`improve-codebase-architecture`](file:///D:/TudoIA/governanca/skills/improve-codebase-architecture/SKILL.md) | Deep module design (Ousterhout standard) and elimination of shallow wrappers |
| **Build** | [`frontend-design`](file:///D:/TudoIA/governanca/skills/frontend-design/SKILL.md) | Distinctive, intentional UI aesthetics avoiding AI design templates |
| **Build** | [`microsoft-docs`](file:///D:/TudoIA/governanca/skills/microsoft-docs/SKILL.md) | Live Microsoft Learn MCP documentation and code samples for Azure, .NET, and Windows |
| **Verify** | [`disciplined-tdd`](file:///D:/TudoIA/governanca/skills/disciplined-tdd/SKILL.md) | Public seam agreement, Red-Green-Refactor loop, zero tautological mocks, adversarial tests |
| **Verify** | [`debugging-and-error-recovery`](file:///D:/TudoIA/governanca/skills/debugging-and-error-recovery/SKILL.md) | Systematic root-cause debugging: Reproduce → Localize → Fix → Guard |
| **Review** | [`code-review-and-quality`](file:///D:/TudoIA/governanca/skills/code-review-and-quality/SKILL.md) | Five-axis code review with strict quality gates |
| **Review** | [`security-and-hardening`](file:///D:/TudoIA/governanca/skills/security-and-hardening/SKILL.md) | OWASP defense, input validation, secret leakage protection, fail-closed boundaries |
| **Ship** | [`git-workflow-and-versioning`](file:///D:/TudoIA/governanca/skills/git-workflow-and-versioning/SKILL.md) | Atomic commits, short-lived branches, and clean git history |
| **Refine** | [`humanize-text`](file:///D:/TudoIA/governanca/skills/humanize-text/SKILL.md) | Eradicates synthetic AI slop, clichés, and cadence in both English and Portuguese prose |
| **Orchestrate** | [`using-agent-skills`](file:///D:/TudoIA/governanca/skills/using-agent-skills/SKILL.md) | Meta-skill for discovering and applying the appropriate skill |
