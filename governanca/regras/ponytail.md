# Ponytail Guidelines (Pragmatic Minimalism & YAGNI)

## 🧘‍♂️ The "Pragmatic Senior" Stance

When designing or coding any solution, climb the **4-Rung Decision Ladder**:

1. **Rung 1 - Real Need (YAGNI):**
   Is this feature, abstraction, or layer strictly necessary for the current goal? If it is speculative ("we might need it later"), **don't build it**.

2. **Rung 2 - Reuse Existing Code:**
   Before creating a new helper, base class, or utility service, check thoroughly whether the codebase already has a function, type, or extension that solves the problem.

3. **Rung 3 - Platform Standard Library (Stdlib First):**
   Strongly prefer the native .NET / C# / Python APIs over pulling new third-party packages (NuGet / npm / PyPI) for trivial tasks. Every external dependency is an attack vector, a breakage risk, and technical debt.

4. **Rung 4 - Least Possible Complexity (Clean Diff):**
   Don't rewrite whole files to change a few lines. Keep diffs surgical, predictable, and easy to review in Pull Requests.

YAGNI cuts speculative features, never safety: correctness, security, and the failure handling the change needs are part of "strictly necessary" (see System-First).
