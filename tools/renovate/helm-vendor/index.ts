import { readdir } from "node:fs/promises";
import { join } from "node:path";
import { compare, valid } from "semver";
import { z } from "zod/v4";
import { GlobalConfig } from "../../../config/global.ts";
import type { Category } from "../../../constants/index.ts";
import { readLocalFile } from "../../../util/fs/index.ts";
import { parseYaml } from "../../../util/yaml.ts";
import type {
  PackageDependency,
  PackageFileContent,
  UpdateArtifact,
  UpdateArtifactsResult,
} from "../types.ts";
import { materialize } from "./vendor.ts";

export const displayName = "Vendored Helm charts";
export const url = "https://helm.sh/docs/topics/registries/";
export const categories: Category[] = ["helm", "kubernetes"];
export const supportedDatasources = ["docker", "helm"];
export const supportsArtifactOnlyUpdates = true;
export const defaultConfig = {
  managerFilePatterns: ["helm-sources/catalog.yaml"],
  commitMessageTopic: "vendored Helm chart {{depName}}",
  additionalBranchPrefix: "helm-vendor-",
  pinDigests: false,
};

const identifier = z.string().regex(/^[a-z0-9][a-z0-9.-]*$/);
const chartVersion = z.string().refine((version) => valid(version) !== null);
const catalogSchema = z.strictObject({
  repositories: z.record(
    identifier,
    z.strictObject({ type: z.enum(["http", "oci"]), url: z.string() }),
  ),
  charts: z.record(
    identifier,
    z.strictObject({
      repository: identifier,
      group: identifier,
      chart: identifier,
      applications: z
        .array(
          z.string().regex(/^clusters\/[a-z0-9-]+\/apps\/[a-z0-9-]+\.yaml$/),
        )
        .min(1),
    }),
  ),
});
const chartSchema = z.object({ name: identifier, version: chartVersion });
type Catalog = z.infer<typeof catalogSchema>;

function parseCatalog(content: string): Catalog {
  const documents = parseYaml(content, { customSchema: catalogSchema });
  if (documents.length !== 1) {
    throw new Error("Expected one Helm vendor catalog document");
  }
  return documents[0];
}

function sourceFor(
  catalog: Catalog,
  name: string,
): z.infer<typeof catalogSchema>["repositories"][string] {
  const entry = catalog.repositories[name];
  if (!entry) {
    throw new Error("Helm chart references an unknown repository");
  }
  const url = new URL(entry.url);
  const protocol = entry.type === "oci" ? "oci:" : "https:";
  if (
    url.protocol !== protocol ||
    !url.host ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      "Helm source must be an OCI or HTTPS registry URL without credentials",
    );
  }
  return { ...entry, url: url.href.replace(/\/+$/, "") };
}

async function latestVendored(
  group: string,
  chart: string,
): Promise<string | undefined> {
  const directory = join("helm", group);
  const paths = await readdir(join(GlobalConfig.get("localDir"), directory), {
    withFileTypes: true,
  });
  const versions: string[] = [];
  for (const path of paths) {
    if (!path.isDirectory() || !path.name.startsWith(chart + "-")) {
      continue;
    }
    const version = path.name.slice(chart.length + 1);
    if (!valid(version)) {
      continue;
    }
    const content = await readLocalFile(
      join(directory, path.name, "Chart.yaml"),
      "utf8",
    );
    if (!content) {
      throw new Error("Missing Chart.yaml in a versioned chart directory");
    }
    const metadata = parseYaml(content, { customSchema: chartSchema })[0];
    if (metadata.name !== chart || metadata.version !== version) {
      throw new Error("Vendored Chart.yaml does not match its directory");
    }
    versions.push(version);
  }
  return versions.sort(compare).at(-1);
}

export async function extractPackageFile(
  content: string,
): Promise<PackageFileContent> {
  const catalog = parseCatalog(content);
  const deps: PackageDependency[] = [];
  for (const [id, chart] of Object.entries(catalog.charts)) {
    const source = sourceFor(catalog, chart.repository);
    const currentValue = await latestVendored(chart.group, chart.chart);
    if (!currentValue) {
      throw new Error(
        "Each Helm vendor catalog entry needs a vendored baseline",
      );
    }
    deps.push({
      depName: id,
      packageName:
        source.type === "oci"
          ? source.url.slice("oci://".length) + "/" + chart.chart
          : chart.chart,
      datasource: source.type === "oci" ? "docker" : "helm",
      registryUrls: source.type === "http" ? [source.url] : undefined,
      currentValue,
      versioning: "semver",
    });
  }
  return { deps };
}

export async function updateArtifacts(
  input: UpdateArtifact,
): Promise<UpdateArtifactsResult[]> {
  const catalog = parseCatalog(input.newPackageFileContent);
  const [upgrade] = input.updatedDeps;
  if (
    input.updatedDeps.length !== 1 ||
    !upgrade?.depName ||
    !upgrade.newValue ||
    !valid(upgrade.newValue)
  ) {
    throw new Error("Expected one versioned Helm chart per branch");
  }
  const chart = catalog.charts[upgrade.depName];
  if (!chart) {
    throw new Error("Chart disappeared from the Helm vendor catalog");
  }
  const source = sourceFor(catalog, chart.repository);
  return materialize(chart, source, upgrade.newValue);
}
