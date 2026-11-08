import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { chartResult, summaryTable } from "./run-summary.mjs";

const branchName = "renovate/helm-vendor-test-2.x";
const update = { newVersion: "2.1.0", branchName };

function chartLog({ updates = [], branch, change, chart = {} } = {}) {
  const records = [
    {
      msg: "packageFiles with updates",
      config: {
        "helm-vendor": [
          {
            deps: [
              { depName: "test", currentValue: "2.0.0", updates, ...chart },
            ],
          },
        ],
      },
    },
    change && {
      msg: "Branch created",
      branch: branchName,
      commitSha: "123456",
    },
    branch && {
      msg: "branches info extended",
      branchesInformation: [{ branchName, ...branch }],
    },
    { msg: "Repository finished", result: "done" },
  ];
  return records
    .filter(Boolean)
    .map((record) => JSON.stringify(record))
    .join("\n");
}

test("skips an up-to-date chart and distinguishes a filtered version", () => {
  assert.deepEqual(chartResult(chartLog(), "test", "off"), {
    status: "Skipped",
    reason: "Already up to date at 2.0.0",
  });
  assert.equal(
    chartResult(chartLog(), "test", "off", "2.1.0").reason,
    "No eligible update to 2.1.0 (current 2.0.0)",
  );
});

test("skips a closed PR and retains the PR number", () => {
  const log = chartLog({
    updates: [update],
    branch: { result: "already-existed", prNo: 216 },
  });
  assert.deepEqual(chartResult(log, "test", "off"), {
    status: "Skipped",
    reason: "Previously closed PR for 2.1.0",
    pr: 216,
  });
});

test("verifies a published or explicitly retried update and skips an unchanged existing PR", () => {
  const log = chartLog({
    updates: [update],
    branch: { result: "pr-created", prNo: 219 },
    change: true,
  });
  assert.deepEqual(chartResult(log, "test", "off"), {
    status: "Updated",
    reason: "2.0.0 → 2.1.0",
    branch: branchName,
    commit: "123456",
    pr: 219,
  });
  const unchanged = chartLog({
    updates: [update],
    branch: { result: "done", prNo: 219 },
  });
  assert.equal(chartResult(unchanged, "test", "off").status, "Skipped");
});

test("distinguishes lookup, a missing or failed lookup, and a deferred update", () => {
  assert.equal(
    chartResult(chartLog({ updates: [update] }), "test", "lookup").status,
    "Dry run",
  );
  assert.equal(chartResult(chartLog(), "unknown", "off").status, "Failed");
  assert.equal(
    chartResult(
      chartLog({ chart: { warnings: [{ message: "Failed to look up" }] } }),
      "test",
      "off",
    ).status,
    "Failed",
  );
  const pending = chartLog({
    updates: [update],
    branch: { result: "needs-approval" },
  });
  assert.equal(chartResult(pending, "test", "off").status, "Deferred");
});

test("writes a row for each chart, including missing results", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "helm-summary-test-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const artifact = join(directory, "renovate-log-helm-test");
  mkdirSync(artifact);
  writeFileSync(
    join(artifact, "result.json"),
    JSON.stringify({
      status: "Skipped",
      reason: "Previously closed PR for 2.1.0",
      pr: 216,
    }),
  );
  const include = [
    { profile: "", selector: "dependencies", key: "dependencies" },
    { profile: "test", selector: "vendor/test", key: "helm-test" },
    { profile: "other", selector: "vendor/other", key: "helm-other" },
  ];
  const table = summaryTable(
    include,
    directory,
    "https://github.com/owner/repo",
  );
  assert.match(table, /vendor\/test.*Skipped.*closed PR.*\/pull\/216/);
  assert.match(table, /vendor\/other.*Failed.*No result recorded/);
  assert.doesNotMatch(table, /dependencies/);
});
