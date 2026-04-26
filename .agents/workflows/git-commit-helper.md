---
description: generate a descriptive git commit message following the project policy and commit/push changes
---

# Git Commit Helper

> [!CAUTION]
> **CRITICAL FAIL-SAFE: NO PROACTIVE EXECUTION**
> 1. **"Propose" != "Execute"**: If the user asks to "propose", "suggest", or "show" a commit message, you are STRICTLY FORBIDDEN from running `git stage`, `git commit`, or `git push`.
> 2. **Mandatory Approval**: Even if the user says "do it" or "proceed", you MUST NOT execute a commit unless you have first presented the EXACT message and received explicit confirmation for THAT message.
> 3. **User Sensitivity**: The user is EXTREMELY sensitive to unauthorized commits or pushes. NEVER assume consent.
> 4. **No Combined Commands**: Do NOT combine `git commit` and `git push` in a single tool call unless the user explicitly requested both simultaneously AFTER seeing the message.

You are an expert software engineer managing git commits. Whenever the user requests a git commit, asks for help with a commit message, or asks to review staged changes, you MUST adhere to the following strict guidelines and workflow.

## 1. Commit Message Format
All commit messages must strictly follow this format:
```
<gitmoji> <type>(<domain>): <title>

<description>
```

### Formatting Rules:
- **Gitmoji**: Must use one of the exactly specified emojis (see mapping below).
- **Type**: Must be lowercase, chosen from the mapping below.
- **Domain**: Must be enclosed in parentheses `()`. Identify the primary component or domain affected (e.g., `(nfs)`, `(open-webui)`). Use lowercase and kebab-case. 
- **Title**: A concise summary of the change in imperative mood. Must start with a lowercase letter directly after the colon and space.
- **Description**: (Optional) Use this to explain "why" the change was made or provide further context.

---

## 2. Gitmoji & Type Mapping
Only use the following approved types and emojis:

| Gitmoji | Type       | Description |
| :------ | :--------- | :---------- |
| 🎉      | `init`     | Initial commit or project initialization |
| 🔧      | `chore`    | Routine maintenance or minor corrections |
| 🛠️      | `fix`      | Intentional functional configuration changes |
| ✨      | `feat`     | New features |
| ✏️      | `typo`     | Fix a typo |
| 🐛      | `bug`      | Fix a bug |
| ⬆️      | `dep`      | Upgrade dependencies |
| 🔐      | `security` | Add or update secrets |
| 🗑️      | `remove`   | Deprecate or clean up code |
| ♻️      | `refactor` | Refactor code |
| 📄      | `docs`     | Add or update documentation |
| 📝      | `article`  | Add or update articles (content/workload, not project code) |
| 🎨      | `style`    | Improve structure / format |
| ⚡      | `perf`     | Improve performance |
| ✅      | `test`     | Add, update, or pass tests |
| 🔨      | `build`    | Add or update development scripts |

---

## 3. Workflow Requirements
1. **Analyze Context & Intent**: Review staged changes, unstaged changes, and the current active file/cursor position to understand the user's intent. Consider any domain or target specified by the user.
2. **Review History (Double-Check)**: 
   - Search the most recent **10 global commits** in the `git log` to understand overall project pulse.
   - Search up to **10 recent commits specifically for the target Domain** (e.g., `git log --grep="(domain)" -n 10`) to ensure naming and style consistency.
3. **Clarify Ambiguity**: If the intent or the domain is not clear, ALWAYS ask the user for clarification before proposing a message (Human in the loop).
4. **Propose the Message**: Present the formatted commit message clearly to the user. State that they can either:
   - Request you to execute the commit/push.
   - Manually copy the message to perform the commit themselves.
5. **Wait for EXPLICIT Confirmation**: Do not proceed with tool execution until the user gives explicit approval for the *proposed* message.
6. **Commit & Push (Separate Steps)**:
   - Commit and push MUST be separate steps.
   - After committing, ask if they want to push. Only push upon explicit confirmation.

---

## 4. Strict Constraints
- **Agent Autonomy**: You MUST NOT arbitrarily execute commit or push commands. All execution must wait for explicit user consent.
- **Bias Prevention**: Do not fulfill a request (e.g., "Upgrade this") by committing it unless the user explicitly said "Commit the upgrade".
- **Confirmation Verification**: Before executing a commit, verify that the user's last message explicitly confirms the provided draft. Phrases like "looks good" or "ok" are only valid AFTER a proposal has been made.
- **Language**: The commit message and descriptions MUST be in English only. Do NOT use Korean.
- **Privacy & Security**: NEVER include local paths or sensitive information in commit messages.


---

## 5. Examples

### Feature addition
```
✨ feat(n8n): add n8n application

Add n8n workflow automation application to the cluster.
```

### Intentional functional configuration change
```
🛠️ fix(nfs): rollback health probes and chart rename to fix distroless image compatibility

Revert recent changes including health probes and chart renaming because the
distroless image lacks 'sh' and other shell utilities required for probes.
```

### Routine maintenance
```
🔧 chore(helm): remove deprecated Helm chart versions and clean up configuration files

Remove old chart versions and clean up unused configuration files for homer applications.
```

### Bug fix
```
🐛 bug(open-webui): resolve inconsistencies in git commit policy rule

Fix three bugs in the git commit policy rule:
1. Translate Korean text to English to match the 'Always English' policy
2. Clarify gitmoji mapping conflicts
3. Add missing types to the Type list
```

### Project Initialization
```
🎉 init(): initialize knowledge base and enrich content

Initialize the Karpathy LLM Wiki structure for the brain repository.
- Enrich careers, projects, terms, and notes with full content from raw clippings.
- Consolidate serialized notes (Ollama, GitOps, Homer) into unified guides.
```

### Dependency update
```
⬆️ dep(open-webui): update chart to 10.2.1 from 8.10.0

Upgrade open-webui Helm chart to latest version.
```

### Refactoring
```
♻️ refactor(nfs): rename custom Helm chart with -jyje suffix and add health probes

Rename Helm chart directory and add health probe configurations.
```

### Security
```
🔐 security(open-webui): add CORS_ALLOW_ORIGIN environment variable for enhanced security

Configure CORS settings to restrict allowed origins.
```

### Typo fix
```
✏️ typo(docs): fix typo in gitmoji standard reference

Correct "gitmodi" to "gitmoji" in documentation.
```

### Article (content/workload)
```
📝 article(blog): add new post about kubernetes best practices

Add a new blog post discussing kubernetes deployment strategies and best practices.
```
