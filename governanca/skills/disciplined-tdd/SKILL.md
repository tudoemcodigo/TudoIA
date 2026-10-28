---
name: disciplined-tdd
description: Enforces disciplined Test-Driven Development (Red-Green-Refactor) with public seam agreement, zero tautological mocks, zero verification theater, and mandatory adversarial path coverage. Use when implementing any logic, bug fix, behavior change, or refactoring.
---

# Disciplined Test-Driven Development (Canonical TudoHaS TDD Standard)

## Overview

Disciplined TDD is not an administrative checkbox or a cosmetic code-generation exercise. It is a rigorous engineering protocol designed to prove correctness, prevent regression, guard public seams, and ensure fail-closed resilience under real-world runtime stress.

---

## When to Use

- Implementing any new business logic, algorithm, or domain rule.
- Fixing a bug (first reproduce the bug with a failing test, then fix).
- Refactoring internal implementation details while preserving external contracts.
- Adding resilience, retries, concurrency limits, or caching layers.
- Whenever writing code where correctness, performance, or security matters.

---

## The 3 Inflexible Pillars

### 1. The Public Seam Agreement (Contract First)
- **Define the Observable Boundary Before Testing:** Before writing test or production code, define the exact public interface (`Seam`) to be exercised.
- **Prohibition of Testing Private/Internal Methods:** Tests must only interact with externally observable contracts, return values, and visible state changes. Testing private methods couples the test suite to internal plumbing, causing brittle tests that shatter during harmless refactorings.
- **Strict Prohibition of Tautological Mocks:** 
  - A test that mocks every collaborator and merely asserts `mock.Verify(x => x.DoSomething(), Times.Once())` verifies nothing about system correctness. It only repeats the implementation code in test form.
  - Test real behavior, output payloads, and observable side-effects. Use real in-memory implementations, lightweight fakes, or ephemeral local instances over brittle mock trees.

### 2. The Strict Red-Green-Refactor Loop

Every feature or bug fix must advance through three strictly verified stages:

```
┌──────────────┐     Terminal Check: Must fail for the expected reason
│   1. RED     │ ──> (Missing feature, not syntax error or bad imports)
└──────────────┘
       │
       ▼
┌──────────────┐     Write minimum sufficient production code.
│   2. GREEN   │ ──> Run tests via terminal. Must pass cleanly (0 errors).
└──────────────┘
       │
       ▼
┌──────────────┐     Consolidate modules, eliminate duplication, improve depth.
│ 3. REFACTOR  │ ──> Re-run test suite. Must remain 100% green.
└──────────────┘
```

1. **RED Phase (Proven Real Failure):**
   - Write a targeted test exercising the agreed public seam.
   - Execute the test in the real terminal (`pytest`, `dotnet test`, `npm test`).
   - Verify that it fails **for the expected functional reason** (e.g. `AssertionError: expected 42 but got None`), NOT due to compilation errors, import typos, or missing test fixture files.
2. **GREEN Phase (Minimal Sufficient Code):**
   - Write only the exact code required to turn the failing test green.
   - Resist the urge to add speculative abstractions, unrequested config knobs, or premature generalizations.
3. **REFACTOR Phase (Clean Separation & Deep Modules):**
   - Clean up code structure, enhance readability, remove duplication, and ensure deep module encapsulation.
   - Re-run the entire test suite to guarantee zero regression.

### 3. Adversarial Path Coverage (Beyond the Happy Path)

A feature is never "done" if it only verifies the happy path. The test suite must actively attack the implementation across real-world adversarial vectors:

- **Timeouts & Upstream Failures:** How does the code behave when a downstream dependency times out, drops the socket, or returns HTTP 500 / 429? Does it fail-closed?
- **Malformed & Boundary Payloads:** Null values, empty collections, oversized strings, negative numbers, boundary indices, and unexpected encodings.
- **Concurrency & Race Conditions:** Do simultaneous concurrent requests cause state corruption, memory leaks, or deadlocks? Is idempotency preserved?

---

## Tool Execution Standard: Zero Verification Theater

You are strictly prohibited from claiming code works or tests pass based on visual inspection alone.

1. **Mandatory Runtime Execution:** Always invoke the native test runner via `desktop-commander` or the terminal after writing or modifying tests.
2. **Self-Healing Loop:** If a test breaks or a build produces warnings:
   - Read the actual terminal stack trace.
   - Identify the root cause.
   - Fix the defect.
   - Re-run until achieving 100% pass with 0 errors and 0 warnings.
3. **Delivery Evidence:** Conclude every coding slice by reporting the exact command executed and the empirical output received.

---

## Concrete Anti-Patterns

| Anti-Pattern | Why It Fails | What to Do Instead |
|---|---|---|
| **The Mock Cloud** | Mocking 8 dependencies to test a 5-line method. The test passes even when production crashes. | Use real components, test against the public seam, or use in-memory state. |
| **Skipping the Red Phase** | Writing tests after the production code is already finished. You cannot prove the test can actually catch bugs. | Always run the test before writing code to observe it fail. |
| **Testing Private Fields** | Using reflection or friend assemblies to inspect private state. | Verify observable outputs, exceptions thrown, or return values. |
| **Happy-Path Only** | Testing only valid input scenarios. Code crashes on the first unexpected production payload. | Write adversarial tests for timeouts, nulls, empty arrays, and concurrency. |
