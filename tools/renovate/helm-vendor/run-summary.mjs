import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const skipped = (reason) => ({ status: "Skipped", reason });
const failed = (reason) => ({ status: "Failed", reason });

export function chartResult(log, profile, mode, expectedVersion) {
  const records = log
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  const lookup = records.findLast(
    ({ msg }) => msg === "packageFiles with updates",
  );
  const chart = lookup?.config?.["helm-vendor"]
    ?.flatMap(({ deps }) => deps)
    .find(({ depName }) => depName === profile);
  const finish = records.findLast(({ msg }) => msg === "Repository finished");
  if (
    !finish ||
    records.some(({ level }) => level >= 50) ||
    (finish.result && finish.result !== "done")
  ) {
    return failed("Renovate reported an error or did not finish");
  }
  if (
    !chart ||
    !Array.isArray(chart.updates) ||
    chart.skipReason ||
    chart.warnings?.length
  ) {
    return failed("Chart lookup did not return a usable result");
  }

  const { currentValue, updates } = chart;
  if (updates.length === 0) {
    if (expectedVersion && expectedVersion.replace(/^v/, "") !== currentValue) {
      return skipped(
        `No eligible update to ${expectedVersion} (current ${currentValue})`,
      );
    }
    return skipped(`Already up to date at ${currentValue}`);
  }

  const update = updates[0];
  const version = `${currentValue} → ${update.newVersion}`;
  const branch = records
    .findLast(({ msg }) => msg === "branches info extended")
    ?.branchesInformation?.find(
      ({ branchName }) => branchName === update.branchName,
    );
  if (branch?.result === "already-existed") {
    return {
      ...skipped(`Previously closed PR for ${update.newVersion}`),
      pr: branch.prNo,
    };
  }
  if (branch?.result === "error" || branch?.artifactErrors?.length) {
    return failed(`Could not prepare ${version}`);
  }
  if (mode !== "off") {
    return { status: "Dry run", reason: `${version} (${mode})` };
  }

  const change = records.findLast(
    ({ msg, branch: name, commitSha }) =>
      name === update.branchName &&
      commitSha &&
      ["Branch created", "Branch updated"].includes(msg),
  );
  if ((branch?.result === "pr-created" && branch.prNo) || change) {
    return {
      status: "Updated",
      reason: version,
      branch: update.branchName,
      commit: change?.commitSha,
      pr: branch?.prNo,
    };
  }
  if (branch?.result === "done" && branch.prNo) {
    return {
      ...skipped(`Existing PR already covers ${update.newVersion}`),
      pr: branch.prNo,
    };
  }
  if (branch?.result === "no-work") {
    return skipped(`No branch changes needed for ${update.newVersion}`);
  }
  if (
    branch?.result &&
    branch.result !== "done" &&
    branch.result !== "pr-created"
  ) {
    return { status: "Deferred", reason: `${version} (${branch.result})` };
  }
  return failed("Renovate did not report what happened to the candidate");
}

function readResult(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    return failed("No result recorded. See the matrix job.");
  }
}

export function summaryTable(include, reports, repository) {
  const rows = include
    .filter(({ profile }) => profile)
    .map(({ selector, key }) => {
      const result = readResult(
        join(reports, `renovate-log-${key}`, "result.json"),
      );
      const pr = result.pr
        ? `[#${result.pr}](${repository}/pull/${result.pr})`
        : " ";
      return `| \`${selector}\` | ${result.status} | ${result.reason} | ${pr} |`;
    });
  return [
    "## Helm vendoring results",
    "",
    "| Chart | Result | Reason | PR |",
    "| --- | --- | --- | --- |",
    ...rows,
    "",
  ].join("\n");
}

function main(command, path) {
  const env = process.env;
  if (command === "summary") {
    const { include } = JSON.parse(env.RENOVATE_MATRIX);
    appendFileSync(
      env.GITHUB_STEP_SUMMARY,
      summaryTable(
        include,
        path,
        `${env.GITHUB_SERVER_URL}/${env.GITHUB_REPOSITORY}`,
      ),
    );
    return;
  }

  const report = join(path, "result.json");
  if (command === "verification-failed") {
    const result = readResult(report);
    writeFileSync(
      report,
      JSON.stringify({
        ...result,
        ...failed("Published branch or PR verification failed"),
      }),
    );
    return;
  }

  let result;
  if (env.RENOVATE_OUTCOME === "success") {
    try {
      result = chartResult(
        readFileSync(join(path, "renovate-log.jsonl"), "utf8"),
        env.HELM_VENDOR_PROFILE,
        env.RENOVATE_MODE,
        env.EXPECTED_VERSION,
      );
    } catch {
      result = failed("Renovate did not produce a readable log");
    }
  } else {
    result = failed("The Renovate step did not complete successfully");
  }

  writeFileSync(report, JSON.stringify(result));
  console.log(`${result.status}: ${result.reason}`);
  if (result.status === "Failed") process.exitCode = 1;
  if (result.status === "Updated") {
    const outputs = {
      branch: result.branch,
      commit: result.commit ?? "",
      pr: result.pr ?? "",
    };
    appendFileSync(
      env.GITHUB_OUTPUT,
      Object.entries(outputs)
        .map(([key, value]) => `${key}=${value}\n`)
        .join(""),
    );
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main(...process.argv.slice(2));
}
