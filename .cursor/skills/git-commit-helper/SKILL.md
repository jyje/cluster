---
name: git-commit-helper
description: Generate descriptive commit messages by analyzing git diffs following the project's specific policy. Use when the user asks for help writing commit messages or reviewing staged changes.
---

# Git Commit Helper

## Instructions

When the user requests a git commit or help with a commit message, follow these steps:

1. **Analyze changes**: Review staged and unstaged changes to understand the scope and purpose of the work.
2. **Determine Domain**: Identify the primary component or domain affected (e.g., `(nfs)`, `(open-webui)`). Use lowercase and kebab-case.
3. **Select Type & Gitmoji**: Choose the appropriate type and its corresponding gitmoji from the table below.
4. **Search git log**: Once the type is chosen, search git log for (1) the last 10 commits and (2) the last 10 commits of that same type (e.g. `feat`, `fix`). Use the results to keep wording and style consistent with recent history.
5. **Draft Message**: Create the message in English using the required format.

### Format

```
<gitmoji> <type>(<domain>): <title>

<description>
```

- **Title**: Concise, imperative mood, lowercase after the type.
- **Description**: Optional, explain "why" or provide context.
- **Co-Authored-By**: Do **not** add a co-author line in the message. Cursor adds `Co-authored-by: Cursor <cursoragent@cursor.com>` automatically when the agent runs `git commit`; adding one in the message causes a duplicate.

### Gitmoji & Type Mapping

| Gitmoji | Type | Description |
| :--- | :--- | :--- |
| 🔧 | `chore` | Routine maintenance or minor corrections |
| 🛠️ | `fix` | Intentional functional configuration changes |
| ✨ | `feat` | New features |
| ✏️ | `typo` | Fix a typo |
| 🐛 | `bug` | Fix a bug |
| ⬆️ | `dep` | Upgrade dependencies |
| 🔐 | `security` | Add or update secrets |
| 🗑️ | `remove` | Deprecate or clean up code |
| ♻️ | `refactor` | Refactor code |
| 📝 | `docs` | Add or update documentation |
| 🎨 | `style` | Improve structure / format |
| ⚡ | `perf` | Improve performance |
| ✅ | `test` | Add, update, or pass tests |
| 🔨 | `build` | Add or update development scripts |

- **Skill updates**: When committing changes to this skill (e.g. under `.cursor/skills/git-commit-helper/`), do **not** use `docs`. Use `chore` for routine updates or `fix` for behavior/instruction corrections.

## Workflow

1. **Propose message**: Present the drafted message in a markdown code block.
2. **Request confirmation**: Ask the user if they want to proceed with the commit.
3. **Commit & Push**:
   - Only execute `git commit` after explicit user approval.
   - After committing, ask if they want to push to the remote.
   - Only execute `git push` after receiving explicit user approval.

## Additional Resources

- For concrete usage examples, see [examples.md](examples.md)
