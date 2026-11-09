import { rcompare, valid } from "semver";
import { GlobalConfig } from "../../../config/global.ts";
import type { RenovateConfig } from "../../../config/types.ts";
import type { BranchConfig } from "../../../workers/types.ts";
import { platform } from "../../platform/index.ts";

function identity(config: RenovateConfig) {
  const profile = process.env.HELM_VENDOR_PROFILE;
  const legacy = config.dependencyDashboardTitle;
  if (
    !profile ||
    !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(profile) ||
    !legacy?.startsWith("Dependency Dashboard (Helm ")
  ) {
    return undefined;
  }
  return { profile, legacy, prefix: "Helm: " + profile + " " };
}

type DashboardIdentity = NonNullable<ReturnType<typeof identity>>;

async function findDashboard(dashboard: DashboardIdentity, openOnly: boolean) {
  const issues = (await platform.getIssueList()).filter(
    ({ title, state }) =>
      (!openOnly || state === "open") &&
      (title === dashboard.legacy ||
        (title?.startsWith(dashboard.prefix) &&
          valid(title.slice(dashboard.prefix.length)) !== null)),
  );
  return issues.sort(
    (a, b) =>
      Number(b.state === "open") - Number(a.state === "open") ||
      (b.number ?? 0) - (a.number ?? 0),
  )[0];
}

function chartUpgrades(dashboard: DashboardIdentity, branches: BranchConfig[]) {
  return branches.flatMap(({ upgrades }) =>
    (upgrades ?? []).filter(
      ({ manager, depName }) =>
        manager === "helm-vendor" && depName === dashboard.profile,
    ),
  );
}

function nextTitle(dashboard: DashboardIdentity, branches: BranchConfig[]) {
  const version = chartUpgrades(dashboard, branches)
    .map(({ newVersion, newValue }) => newVersion ?? newValue ?? "")
    .filter((candidate) => valid(candidate) !== null)
    .sort(rcompare)[0];
  return version ? dashboard.prefix + version : undefined;
}

export async function openHelmDashboardTitle(config: RenovateConfig) {
  const dashboard = identity(config);
  return dashboard ? (await findDashboard(dashboard, true))?.title : undefined;
}

export async function helmDashboardPresentation(
  config: RenovateConfig,
  branches: BranchConfig[],
) {
  const dashboard = identity(config);
  if (!dashboard) {
    return undefined;
  }
  const existing = await findDashboard(dashboard, false);
  const title =
    nextTitle(dashboard, branches) ?? existing?.title ?? dashboard.legacy;
  return { title, reuseTitle: existing?.title ?? dashboard.legacy };
}

export async function prepareHelmDashboard(
  config: RenovateConfig,
  branches: BranchConfig[],
) {
  const dashboard = identity(config);
  if (!dashboard || GlobalConfig.get("dryRun") || config.mode === "silent") {
    return;
  }
  const title = nextTitle(dashboard, branches);
  if (!title) {
    return;
  }
  if (!config.dependencyDashboardIssue) {
    const existing = await findDashboard(dashboard, false);
    if (existing?.state === "open" && existing.number) {
      config.dependencyDashboardIssue = existing.number;
    } else {
      await platform.ensureIssue({
        title,
        reuseTitle: existing?.title ?? dashboard.legacy,
        body: "Renovate is preparing this chart update.",
        labels: config.dependencyDashboardLabels,
        confidential: config.confidential,
      });
      config.dependencyDashboardIssue = (await platform.findIssue(title))?.number;
    }
  }
  const number = config.dependencyDashboardIssue;
  if (!number || number < 1) {
    throw new Error("Could not prepare the Helm tracking issue before publishing");
  }
  const note = "Tracking issue: #" + number;
  for (const upgrade of chartUpgrades(dashboard, branches)) {
    upgrade.prBodyNotes = [...new Set([...(upgrade.prBodyNotes ?? []), note])];
  }
}
