import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { GlobalConfig } from "../../../config/global.ts";
import { extractPackageFile, updateArtifacts } from "./index.ts";

const catalog = [
  "repositories:",
  "  vendor:",
  "    type: oci",
  "    url: oci://ghcr.io/vendor/charts",
  "charts:",
  "  demo:",
  "    repository: vendor",
  "    group: group",
  "    chart: demo",
  "    applications: [clusters/site/apps/demo.yaml]",
].join("\n");

describe("Helm vendor manager", () => {
  let directory: string;

  beforeEach(async () => {
    directory = await mkdtemp(join(tmpdir(), "helm-vendor-test-"));
    GlobalConfig.set({ localDir: directory });
    for (const version of ["1.9.0", "1.10.0"]) {
      const chart = join(directory, "helm", "group", "demo-" + version);
      await mkdir(chart, { recursive: true });
      await writeFile(
        join(chart, "Chart.yaml"),
        "name: demo\nversion: " + version + "\n",
      );
    }
  });

  afterEach(async () => {
    GlobalConfig.reset();
    await rm(directory, { recursive: true, force: true });
  });

  it("discovers the newest vendored version and the OCI package name", async () => {
    await expect(extractPackageFile(catalog)).resolves.toEqual({
      deps: [
        {
          depName: "demo",
          currentValue: "1.10.0",
          datasource: "docker",
          packageName: "ghcr.io/vendor/charts/demo",
          registryUrls: undefined,
          versioning: "semver",
        },
      ],
    });
  });

  it("uses the Helm datasource for a traditional repository", async () => {
    const http = catalog
      .replace("type: oci", "type: http")
      .replace("oci://ghcr.io/vendor/charts", "https://vendor.example/charts");
    await expect(extractPackageFile(http)).resolves.toMatchObject({
      deps: [
        {
          datasource: "helm",
          packageName: "demo",
          registryUrls: ["https://vendor.example/charts"],
        },
      ],
    });
  });

  it("rejects an existing release before running Helm", async () => {
    await expect(
      updateArtifacts({
        packageFileName: "helm-sources/catalog.yaml",
        newPackageFileContent: catalog,
        config: {},
        updatedDeps: [{ depName: "demo", newValue: "1.10.0" }],
      }),
    ).rejects.toThrow("Target chart directory already exists");
  });
});
