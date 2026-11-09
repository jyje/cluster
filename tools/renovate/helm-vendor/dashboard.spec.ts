import { logger, partial, platform } from "~test/util.ts";
import { GlobalConfig } from "../../../config/global.ts";
import type { RenovateConfig } from "../../../config/types.ts";
import {
  ensureDependencyDashboard,
  readDashboardBody,
} from "../../../workers/repository/dependency-dashboard.ts";
import { getPrNotes } from "../../../workers/repository/update/pr/body/notes.ts";
import type { BranchConfig, BranchUpgradeConfig } from "../../../workers/types.ts";
import { helmDashboardPresentation, prepareHelmDashboard } from "./dashboard.ts";

const legacyTitle = "Dependency Dashboard (Helm vendor/demo)";
const title = "Helm: demo 2.1.0";

function candidate(): BranchConfig {
  return partial<BranchConfig>({
    branchName: "renovate/helm-vendor-demo-2.x",
    upgrades: [
      partial<BranchUpgradeConfig>({
        manager: "helm-vendor",
        depName: "demo",
        newVersion: "2.1.0",
        prBodyNotes: ["Keep this note."],
      }),
    ],
  });
}

describe("Helm dashboard issues", () => {
  let config: RenovateConfig;

  beforeEach(() => {
    vi.stubEnv("HELM_VENDOR_PROFILE", "demo");
    GlobalConfig.set({});
    config = {
      dependencyDashboard: true,
      dependencyDashboardAutoclose: true,
      dependencyDashboardTitle: legacyTitle,
    };
    platform.getIssueList.mockResolvedValue([]);
    logger.getProblems.mockReturnValue([]);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    GlobalConfig.reset();
  });

  it("creates an issue before supplying its number to the PR body", async () => {
    const branch = candidate();
    platform.ensureIssue.mockResolvedValueOnce("created");
    platform.findIssue.mockResolvedValueOnce({ title, number: 42 });

    await prepareHelmDashboard(config, [branch]);

    expect(platform.ensureIssue).toHaveBeenCalledWith(
      expect.objectContaining({ title, reuseTitle: legacyTitle }),
    );
    expect(platform.ensureIssue).toHaveBeenCalledBefore(platform.findIssue);
    expect(platform.findIssue).toHaveBeenCalledWith(title);
    expect(getPrNotes(branch)).toBe("Keep this note.\n\nTracking issue: #42\n\n");
  });

  it("preserves approvals when the issue was already renamed", async () => {
    const branch = candidate();
    const issue = {
      title: "Helm: demo 2.0.0",
      state: "open",
      number: 42,
      body: " - [x] <!-- approve-branch=renovate/helm-vendor-demo-2.x -->",
    };
    platform.getIssueList.mockResolvedValue([
      issue,
      { title: "Helm: demo-controller 2.1.0", state: "open", number: 99 },
    ]);
    platform.findIssue.mockResolvedValueOnce(issue);

    await readDashboardBody(config);
    await prepareHelmDashboard(config, [branch]);
    await prepareHelmDashboard(config, [branch]);

    expect(config.dependencyDashboardIssue).toBe(42);
    expect(config.dependencyDashboardChecks).toHaveProperty([branch.branchName]);
    expect(platform.ensureIssue).not.toHaveBeenCalled();
    expect(await helmDashboardPresentation(config, [branch])).toEqual({
      title,
      reuseTitle: issue.title,
    });
    expect(getPrNotes(branch)).toBe("Keep this note.\n\nTracking issue: #42\n\n");
  });

  it("renames a legacy issue in place, even when only its title changes", async () => {
    const branch = candidate();
    const issue = { title: legacyTitle, number: 42, state: "open" };
    platform.getIssueList.mockResolvedValue([issue]);
    platform.findIssue.mockResolvedValueOnce(issue);
    platform.maxBodyLength.mockReturnValue(60_000);
    platform.massageMarkdown.mockImplementation((body) => body);
    await readDashboardBody(config);
    await ensureDependencyDashboard(config, [branch], {}, { result: "no-migration" });
    const body = platform.ensureIssue.mock.lastCall?.[0].body;
    platform.ensureIssue.mockClear();
    platform.getIssue.mockResolvedValue({ ...issue, body });

    await ensureDependencyDashboard(config, [branch], {}, { result: "no-migration" });

    expect(platform.ensureIssue).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ title, reuseTitle: legacyTitle, body }),
    );
  });

  it("closes the renamed issue when the chart is up to date", async () => {
    platform.getIssueList.mockResolvedValue([{ title, number: 42, state: "open" }]);

    await ensureDependencyDashboard(config, [], {}, { result: "no-migration" });

    expect(platform.ensureIssueClosing).toHaveBeenCalledWith(title);
    expect(platform.ensureIssue).not.toHaveBeenCalled();
  });

  it("reuses a closed chart issue for its next version", async () => {
    const previous = "Helm: demo 2.0.0";
    platform.getIssueList.mockResolvedValue([
      { title: previous, number: 42, state: "closed" },
    ]);
    platform.findIssue.mockResolvedValueOnce({ title, number: 42 });

    await prepareHelmDashboard(config, [candidate()]);

    expect(platform.ensureIssue).toHaveBeenCalledWith(
      expect.objectContaining({ title, reuseTitle: previous }),
    );
    expect(config.dependencyDashboardIssue).toBe(42);
  });

  it("does not create issues for a dry run, an unrelated job, or no candidate", async () => {
    GlobalConfig.set({ dryRun: "full" });
    await prepareHelmDashboard(config, [candidate()]);
    GlobalConfig.reset();
    await prepareHelmDashboard(config, []);
    await prepareHelmDashboard({ dependencyDashboardTitle: "Dependency Dashboard" }, [candidate()]);

    expect(platform.getIssueList).not.toHaveBeenCalled();
    expect(platform.ensureIssue).not.toHaveBeenCalled();
  });

  it("does not proceed to publication if the tracking issue could not be found", async () => {
    platform.findIssue.mockResolvedValueOnce(null);
    await expect(prepareHelmDashboard(config, [candidate()])).rejects.toThrow(
      "Could not prepare the Helm tracking issue before publishing",
    );
  });
});
