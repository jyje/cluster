# Git Commit Helper Examples

Below are examples of commit messages following the project policy.

## Feature addition
```
✨ feat(n8n): add n8n application

Add n8n workflow automation application to the cluster.

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```

## Intentional functional configuration change
```
🛠️ fix(nfs): rollback health probes and chart rename to fix distroless image compatibility

Revert recent changes including health probes and chart renaming because the
distroless image lacks 'sh' and other shell utilities required for probes.

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```

## Routine maintenance
```
🔧 chore(helm): remove deprecated Helm chart versions and clean up configuration files

Remove old chart versions and clean up unused configuration files for homer applications.

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```

## Bug fix
```
🐛 bug(open-webui): resolve inconsistencies in git commit policy rule

Fix three bugs in the git commit policy rule:
1. Translate Korean text to English to match the 'Always English' policy
2. Clarify gitmoji mapping conflicts
3. Add missing types to the Type list

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```

## Dependency update
```
⬆️ dep(open-webui): update chart to 10.2.1 from 8.10.0

Upgrade open-webui Helm chart to latest version.

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```

## Refactoring
```
♻️ refactor(nfs): rename custom Helm chart with -jyje suffix and add health probes

Rename Helm chart directory and add health probe configurations.

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```

## Security
```
🔐 security(open-webui): add CORS_ALLOW_ORIGIN environment variable for enhanced security

Configure CORS settings to restrict allowed origins.

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```

## Typo fix
```
✏️ typo(docs): fix typo in gitmoji standard reference

Correct "gitmodi" to "gitmoji" in documentation.

Co-Authored-By: Cursor Agent <cursoragent@cursor.com>
```
