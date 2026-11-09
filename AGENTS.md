# Repository instructions

## Helm chart updates

Track each chart update in an issue from vendoring through verified deployment.

1. **Vendor the chart.** Open or identify the tracking issue first. Keep the vendoring PR limited to the new chart version and reference the issue as `Tracking issue: #<number>`. Merging this PR does not update the Argo CD Application or complete the issue.
2. **Review and deploy separately.** Compare the old and new chart with the current Application values. After approval, update the Argo CD Application in a separate PR that references the same issue. Record any intentional image pin or values override.
3. **Verify the live rollout.** Confirm Argo CD synced the intended revision, the Application is Healthy, and the updated workloads are Ready. Run a service-specific smoke test when applicable. If verification is blocked, incomplete, or rolled back, record the outcome and keep the issue open.
4. **Record the result and close the issue.** Before closing, record the vendoring and deployment PRs, chart and image versions, rollout result, and verification evidence in the tracking issue. Do not use `Closes #<number>` in either PR as a substitute for this check. Close the issue only after the live deployment is verified and the record is complete.

Renovate's auto-closed dashboard is not evidence of deployment. If a dashboard can close before live verification, use a linked rollout tracking issue that stays open until the steps above are complete. Do not include credentials or private infrastructure details in public issues or PRs.
