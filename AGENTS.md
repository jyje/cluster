# Repository instructions

## Language: English only for public text

**Write everything that lands in this public repository in English. No Korean (Hangul), with no exceptions.**

This covers:

- Pull request titles and descriptions
- Issue titles, descriptions and comments, including tracking-issue evidence and edits to existing comments
- PR review comments and replies
- Commit messages
- Code comments, YAML comments and `PATCH.md` files

Rules:

- Write the English text first. Do not draft in Korean and translate afterwards.
- Chat replies to the user may follow the user's language. Anything published to GitHub or committed to the repository may not.
- Documentation follows the existing rule: English is the default, and a Korean twin is allowed only as a separate `*-ko.md` file next to it.
- If Korean text was already published by mistake, rewrite it in English right away (edit the comment or PR body in place).

## Helm chart updates

Track each chart update in an issue from vendoring through verified deployment.

1. **Vendor the chart.** Open or identify the tracking issue first. Keep the vendoring PR limited to the new chart version and reference the issue as `Tracking issue: #<number>`. Merging this PR does not update the Argo CD Application or complete the issue.
2. **Review and deploy separately.** Compare the old and new chart with the current Application values. After approval, update the Argo CD Application in a separate PR that references the same issue. Record any intentional image pin or values override.
3. **Verify the live rollout.** Confirm Argo CD synced the intended revision, the Application is Healthy, and the updated workloads are Ready. Run a service-specific smoke test when applicable. If verification is blocked, incomplete, or rolled back, record the outcome and keep the issue open.
4. **Record the result and close the issue.** Before closing, record the vendoring and deployment PRs, chart and image versions, rollout result, and verification evidence in the tracking issue. Do not use `Closes #<number>` in either PR as a substitute for this check. Close the issue only after the live deployment is verified and the record is complete.

Renovate's auto-closed dashboard is not evidence of deployment. If a dashboard can close before live verification, use a linked rollout tracking issue that stays open until the steps above are complete. Do not include credentials or private infrastructure details in public issues or PRs.

## Manifest layout

Keep each workload in its own manifest file. Do not mix resources that serve different workloads, applications or namespaces in one YAML file, even when they share a directory or an Argo CD Application. For example, the UDP game Gateway and the Henry web Gateway live in separate files.

When splitting an existing file, keep it in the same directory and Application so resource identity does not change, and verify that the new files concatenate to the original content.

## Temporary worktrees

Do not create git worktrees next to the regular project checkouts (for example under `~/repo/jyje/`). Create them outside that tree, such as `~/.claude/worktrees/jyje-cluster/<name>`.

Remove the worktree, the local branch and the remote branch as soon as the PR is merged. Before deleting one, check that it is clean and that the PR is merged with the same head commit as the local branch. A squash merge needs `git branch -D` after that check.
