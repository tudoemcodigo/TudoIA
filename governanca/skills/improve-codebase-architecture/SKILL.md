---
name: improve-codebase-architecture
description: Applies deep module design principles (Ousterhout standard), eliminating shallow wrappers, pass-through classes, and fragmented logic. Use when reviewing code structure, designing new services, refactoring sprawling codebases, or consolidating scattered domain rules into cohesive, deep modules.
---

# Codebase Architecture Guidelines (Deep Modules & Ousterhout Standard)

## Overview

Software complexity is accumulated incrementally through cognitive friction, fragmented information, and shallow abstractions. Following the foundational principles of *A Philosophy of Software Design* (John Ousterhout) and high-rigor systems engineering, this skill directs agents to eliminate accidental complexity by designing **deep modules**, maximizing **information locality**, and ruthlessly pruning **shallow pass-through layers**.

---

## When to Use

- Designing the architecture of a new service, package, or subsystem.
- Reviewing pull requests with excessive new files or layers.
- Refactoring sprawling codebases where a single business change requires editing multiple disconnected files.
- Consolidating anemic boilerplate (e.g., repository layers that merely forward calls to an ORM).
- Simplifying over-engineered abstraction hierarchies.

---

## Core Architectural Principles

### 1. The Deep Module Rule
- **The best module is one that provides powerful, complex internal functionality behind a small, simple public interface.**
- **Interface Minimization:** Expose as few public methods and parameters as possible. Use clean, strongly typed inputs and fail-closed defaults.
- **Hidden Complexity:** Concurrency management, thread synchronization, retries, caching, protocol parsing, and validation must remain encapsulated within the module boundary, completely invisible to the caller.

```
┌───────────────────────────────────────────────┐
│              Deep Module                      │
│   Public Seam:  Execute(request) -> result    │
├───────────────────────────────────────────────┤
│  [Hidden Internal Machinery]                  │
│  - Exponential backoff & jitter               │
│  - Connection pooling & circuit breaker       │
│  - In-memory eviction cache                   │
│  - Payload encryption & serialization         │
└───────────────────────────────────────────────┘
```

### 2. Prohibition of Shallow Modules (Micro-Wrappers)
- A **shallow module** is an abstraction whose interface is relatively complex compared to the functionality it implements.
- **Pass-through Classes:** Creating an interface, service, mapper, and repository just to forward a call to a database without domain logic creates cognitive overhead with zero architectural benefit:
  ```csharp
  // ❌ Shallow pass-through: Adds cognitive friction, no real abstraction
  public class UserRepository : IUserRepository {
      public Task<User> GetById(int id) => _context.Users.FindAsync(id);
  }
  ```
- If a layer does not enforce domain invariants, transform semantics, or isolate an unstable external boundary, **eliminate it** and let the consumer call the underlying component directly.

### 3. Information Locality vs. Logic Fragmentation
- **Keep related knowledge together:** All code affected by a specific design decision should reside within a single cohesive module.
- **The 5-File Smell:** If adding or modifying a single business capability requires changing 5 distinct files across 5 directories (DTO -> Interface -> Controller -> Service -> Repository), the system suffers from **information leakage and fragmentation**.
- Consolidate fragmented layers into deep, vertical slices.

### 4. Rigorous Engineering Vocabulary

When discussing and naming architectural components, employ terms with exact technical precision:

- **Module:** A self-contained unit of code that hides complex implementation details behind a stable, cohesive interface.
- **Interface:** The minimal public surface through which clients interact with a module.
- **Seam:** The boundary where two modules connect, and where behavioral tests are coupled.
- **Depth:** The ratio of internal capability delivered to the surface complexity of its interface.
- **Locality:** The co-location of logically interdependent rules and state within the same boundary.
- **Adapter:** An explicit translator reconciling two incompatible external interfaces or protocol boundaries.

---

## Refactoring Heuristic: Consolidate Before Extracting

Before extracting a new class, file, or helper, ask:

1. *Does this extraction make the overall system simpler to understand, or does it scatter one coherent thought across multiple files?*
2. *Is this interface designed for multiple real implementations, or is it a 1:1 mirror interface created solely for mocking?*
3. *If this module is deleted tomorrow, does the system lose a capability or just an unnecessary intermediary?*

### Concrete Before & After

#### ❌ Shallow & Fragmented (Anti-Pattern):
```
src/
  Controllers/OrderController.cs      (Calls OrderService)
  Services/OrderService.cs            (Calls OrderRepository, OrderValidator, OrderMapper)
  Validators/OrderValidator.cs        (Checks order.Total > 0)
  Mappers/OrderMapper.cs              (Copies 4 fields between OrderDto and OrderEntity)
  Repositories/OrderRepository.cs     (Calls dbContext.Orders.Add)
```
*Result: 5 files, 4 interfaces, hundreds of lines of glue code, zero encapsulation.*

#### ✅ Deep Module (Canonical Standard):
```
src/
  Ordering/
    OrderProcessor.cs  (Exposes ProcessOrder(request); encapsulates validation, persistence, and event dispatch)
    Order.cs           (Domain entity guarding invariants)
```
*Result: Clear public seam, encapsulated logic, high information locality, zero pass-through indirection.*
