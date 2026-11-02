---
name: microsoft-docs
description: Understand Microsoft technologies by querying official documentation. Use whenever the user asks how something works, wants tutorials, needs configuration options, limits, quotas, or best practices for any Microsoft technology (Azure, .NET, M365, Windows, Power Platform, etc.)—even if they don't mention "docs." If the question is about understanding a concept rather than writing code, this is the right skill.
context: fork
compatibility: Primarily uses the Microsoft Learn MCP Server (https://learn.microsoft.com/api/mcp); if that is unavailable, report it (the mslearn CLI is used only on explicit user request, see CLI Alternative).
---

> **Precedence in TEC:** In TEC services and components, the TEC Doctrine (skill `doutrina-tec`) prevails over this skill (ECO-PRE-07): run only the compatible part and report the conflict with the rule ID and the passage of this skill.

# Microsoft Docs

## Tools

The `microsoft-learn` MCP server provides real-time access to official Microsoft Learn documentation and verified code samples:

| Tool | Use For |
|------|---------|
| `microsoft_docs_search` | Find documentation—concepts, guides, tutorials, configuration |
| `microsoft_docs_fetch` | Get full page content in markdown (when search excerpts aren't enough) |
| `microsoft_code_sample_search` | Search verified official code samples from Microsoft Learn |

## When to Use

- **Understanding concepts** — "How does Cosmos DB partitioning work?"
- **Learning a service** — "Azure Functions overview", "Container Apps architecture"
- **Finding tutorials** — "quickstart", "getting started", "step-by-step"
- **Configuration options** — "App Service configuration settings"
- **Limits & quotas** — "Azure OpenAI rate limits", "Service Bus quotas"
- **Best practices** — "Azure security best practices"

## Query Effectiveness

Good queries are specific:

```
# ❌ Too broad
"Azure Functions"

# ✅ Specific
"Azure Functions Python v2 programming model"
"Cosmos DB partition key design best practices"
"Container Apps scaling rules KEDA"
```

Include context:
- **Version** when relevant (`.NET 8`, `EF Core 8`)
- **Task intent** (`quickstart`, `tutorial`, `overview`, `limits`)
- **Platform** for multi-platform docs (`Linux`, `Windows`)

## When to Fetch Full Page

Fetch after search when:
- **Tutorials** — need complete step-by-step instructions
- **Configuration guides** — need all options listed
- **Deep dives** — user wants comprehensive coverage
- **Search excerpt is cut off** — full context needed

## Why Use This

- **Accuracy** — live docs, not training data that may be outdated
- **Completeness** — tutorials have all steps, not fragments
- **Authority** — official Microsoft documentation

## CLI Alternative

If the Learn MCP server is not reachable, say so. Do not download or run the `mslearn` CLI on your own (IA-FER-02, IA-OPS-01): use it only if the user asks, with a pinned version whose package was read first (`@microsoft/learn-cli@<version>`):

```sh
# Only on explicit user request, pinned version
npx @microsoft/learn-cli@<version> search "azure functions timeout"

# Or install globally (also only on request), then run
npm install -g @microsoft/learn-cli@<version>
mslearn search "azure functions timeout"
```

| MCP Tool | CLI Command |
|----------|-------------|
| `microsoft_docs_search(query: "...")` | `mslearn search "..."` |
| `microsoft_docs_fetch(url: "...")` | `mslearn fetch "..."` |
| `microsoft_code_sample_search(query: "...")` | `mslearn code-search "..."` |

The `fetch` command also supports `--section <heading>` to extract a single section and `--max-chars <number>` to truncate output.
