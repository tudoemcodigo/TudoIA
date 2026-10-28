# AI Data Privacy

Rules for what may be sent to language models and other AI services. Prompts, files, and embeddings sent to a provider leave the machine.

- **Know where the request goes.** Local models (Ollama, local ComfyUI) keep data on the machine. Cloud providers receive the full prompt; free tiers often retain it and may train on it. A router or gateway (such as LiteLLM `tudoia-auto`) may send a request to the cloud unless the request is explicitly pinned to a local model.
- **Personal and confidential data stays local by default.** Personal data (any information about an identifiable person), client or employer confidential code and documents, credentials, and internal infrastructure details go only to local models, or to a paid provider under a contract that forbids training on inputs, and only when the task needs them.
- **Minimize before sending.** Strip or mask identifiers, secrets, and irrelevant personal fields from prompts, test data, evaluation sets, and logs that feed a model. Use synthetic data for examples and tests.
- **Never place secrets or tokens in a prompt**, a system prompt, a tool description, or a vector store.
- **Record new flows.** A feature that sends user content to an AI provider is a data-sharing activity (and usually an international transfer): document it where the project keeps its data map. For LGPD obligations, use the `lgpd-compliance` skill.
- **Model output is untrusted input.** Validate it before it reaches a query, a shell, the DOM, a file path, or another tool.
