import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { GlobalConfig } from "../../../config/global.ts";
import {
  extractPackageFile,
  selectProfiles,
  updateArtifacts,
} from "./index.ts";
import { patchResources } from "./vendor.ts";

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

const catalogWithTwoProfiles = [
  catalog,
  "  second:",
  "    repository: vendor",
  "    group: group",
  "    chart: other",
  "    applications: [clusters/site/apps/demo.yaml]",
].join("\n");

describe("Helm vendor manager", () => {
  let directory: string;

  beforeEach(async () => {
    vi.stubEnv("HELM_VENDOR_PROFILE", "");
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
    vi.unstubAllEnvs();
    GlobalConfig.reset();
    await rm(directory, { recursive: true, force: true });
  });

  it("adds extraResources without changing a differently named upstream hook", async () => {
    const chart = join(directory, "helm", "group", "demo-1.10.0");
    const templates = join(chart, "templates");
    const upstream = join(templates, "extra-objects.yaml");
    const upstreamTemplate = "{{ toYaml .Values.extraObjects }}\n";
    await mkdir(templates);
    await writeFile(upstream, upstreamTemplate);
    await writeFile(join(chart, "values.yaml"), "extraObjects: []\n");

    await patchResources(chart, ["templates/extra-objects.yaml"]);

    await expect(readFile(upstream, "utf8")).resolves.toBe(upstreamTemplate);
    await expect(readFile(join(chart, "values.yaml"), "utf8")).resolves.toBe(
      "extraObjects: []\nextraResources: []\n",
    );
    await expect(
      readFile(join(templates, "extra-resources.yaml"), "utf8"),
    ).resolves.toContain(".Values.extraResources");
  });

  it("preserves native extraResources values, template and schema unchanged", async () => {
    const chart = join(directory, "helm", "group", "demo-1.10.0");
    const templates = join(chart, "templates");
    await mkdir(templates);
    const files = {
      "values.yaml": "# Keep this comment\nextraResources: []\n",
      "values.schema.json":
        '{"properties":{"extraResources":{"type":"array","description":"Native"}}}\n',
      "templates/native.yaml": "{{ toYaml .Values.extraResources }}\n",
    };
    for (const [path, content] of Object.entries(files)) {
      await writeFile(join(chart, path), content);
    }

    await patchResources(chart, Object.keys(files));

    for (const [path, content] of Object.entries(files)) {
      await expect(readFile(join(chart, path), "utf8")).resolves.toBe(content);
    }
    await expect(
      readFile(join(templates, "extra-resources.yaml"), "utf8"),
    ).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("does not overwrite a template at the standard patch path", async () => {
    const chart = join(directory, "helm", "group", "demo-1.10.0");
    const templates = join(chart, "templates");
    const template = join(templates, "extra-resources.yaml");
    await mkdir(templates);
    await writeFile(template, "# Upstream template\n");
    await writeFile(join(chart, "values.yaml"), "extraObjects: []\n");

    await expect(
      patchResources(chart, ["templates/extra-resources.yaml"]),
    ).rejects.toMatchObject({ code: "EEXIST" });
    await expect(readFile(template, "utf8")).resolves.toBe("# Upstream template\n");
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

  it("plans one job per provider and chart for all", () => {
    expect(selectProfiles(catalogWithTwoProfiles, "all")).toEqual([
      { profile: "demo", selector: "vendor/demo", key: "helm-demo" },
      { profile: "second", selector: "vendor/other", key: "helm-second" },
    ]);
  });

  it("selects one chart by provider and chart name", () => {
    expect(selectProfiles(catalogWithTwoProfiles, "vendor/other")).toEqual([
      { profile: "second", selector: "vendor/other", key: "helm-second" },
    ]);
  });

  it("rejects an unregistered provider and chart name", () => {
    expect(() => selectProfiles(catalogWithTwoProfiles, "other")).toThrow(
      "No Helm profiles matched",
    );
  });

  it("rejects duplicate provider and chart names", () => {
    const duplicate = catalogWithTwoProfiles.replace(
      "chart: other",
      "chart: demo",
    );
    expect(() => selectProfiles(duplicate, "all")).toThrow(
      "Duplicate Helm chart selector vendor/demo",
    );
  });

  it("rejects two sources writing to the same chart directory", () => {
    const duplicate = catalogWithTwoProfiles
      .replace(
        "charts:",
        "  another:\n    type: oci\n    url: oci://ghcr.io/another/charts\ncharts:",
      )
      .replace(
        "repository: vendor\n    group: group\n    chart: other",
        "repository: another\n    group: group\n    chart: demo",
      );
    expect(() => selectProfiles(duplicate, "all")).toThrow(
      "Duplicate Helm chart destination group/demo",
    );
  });

  it("extracts only the selected profile for a manual run", async () => {
    const chart = join(directory, "helm", "group", "other-1.9.0");
    await mkdir(chart, { recursive: true });
    await writeFile(join(chart, "Chart.yaml"), "name: other\nversion: 1.9.0\n");
    vi.stubEnv("HELM_VENDOR_PROFILE", "second");
    const { deps } = await extractPackageFile(catalogWithTwoProfiles);
    expect(deps.map(({ depName }) => depName)).toEqual(["second"]);
  });

  it("rejects an unknown profile", async () => {
    vi.stubEnv("HELM_VENDOR_PROFILE", "typo");
    await expect(extractPackageFile(catalog)).rejects.toThrow(
      "Unknown Helm vendor profile",
    );
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
