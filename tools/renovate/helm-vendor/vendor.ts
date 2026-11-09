import { execFile } from "node:child_process";
import {
  lstat,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  realpath,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join, relative, sep } from "node:path";
import { isDeepStrictEqual, promisify } from "node:util";
import { valid } from "semver";
import { parseDocument } from "yaml";
import { z } from "zod/v4";
import { GlobalConfig } from "../../../config/global.ts";
import { readLocalFile } from "../../../util/fs/index.ts";
import { parseYaml } from "../../../util/yaml.ts";
import type { UpdateArtifactsResult } from "../types.ts";

const run = promisify(execFile);
const extraResources = [
  "{{- range .Values.extraResources }}",
  "---",
  '{{- if typeIs "string" . }}',
  "  {{- tpl . $ }}",
  "{{- else }}",
  "  {{- tpl (toYaml .) $ }}",
  "{{- end }}",
  "{{- end }}",
  "",
].join("\n");

const applicationSchema = z.object({
  metadata: z.object({ name: z.string() }),
  spec: z.object({
    destination: z.object({ namespace: z.string() }),
    source: z.object({
      path: z.string(),
      helm: z
        .strictObject({
          releaseName: z.string().optional(),
          valueFiles: z.array(z.string()).optional(),
          valuesObject: z.record(z.string(), z.unknown()).optional(),
        })
        .optional(),
    }),
  }),
});
const metadataSchema = z.object({
  name: z.string(),
  version: z.string(),
  dependencies: z.array(z.unknown()).optional(),
});
type Chart = {
  group: string;
  chart: string;
  directoryName?: string;
  applications: string[];
};
type Source = { type: "http" | "oci"; url: string };
const extraResourcesPolicySchema = z.strictObject({
  objectOnly: z.array(
    z.string().regex(/^helm\/[a-z0-9][a-z0-9.-]*\/[a-z0-9][a-z0-9.-]*$/),
  ),
});

export async function usesObjectOnlyResources(
  chartPrefix: string,
): Promise<boolean> {
  const content = await readLocalFile(
    "helm-sources/extra-resources-policy.json",
    "utf8",
  );
  if (!content) {
    throw new Error("Missing Helm extraResources verification policy");
  }
  const policy = extraResourcesPolicySchema.parse(JSON.parse(content));
  return policy.objectOnly.includes(chartPrefix);
}

const literalManifest = z.object({
  apiVersion: z.string().min(1),
  kind: z.string().min(1),
});

export function assertObjectOnlyResources(resources: unknown): void {
  if (resources === undefined || resources === null) {
    return;
  }
  if (
    !Array.isArray(resources) ||
    resources.some(
      (resource) =>
        !literalManifest.safeParse(resource).success ||
        JSON.stringify(resource).includes("{{"),
    )
  ) {
    throw new Error(
      "Object-only extraResources requires Kubernetes objects without Helm expressions",
    );
  }
}

export function extraResourceProbes(objectOnly: boolean) {
  const object = {
    apiVersion: "v1",
    kind: "ConfigMap",
    metadata: { name: "helm-vendor-object-probe" },
  };
  return objectOnly
    ? [object]
    : [
        object,
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: helm-vendor-string-probe-{{ .Release.Namespace }}\n",
      ];
}

async function helm(cwd: string, ...args: string[]): Promise<string> {
  try {
    const { stdout } = await run("helm", args, {
      cwd,
      timeout: 120_000,
      maxBuffer: 16 * 1024 * 1024,
    });
    return stdout;
  } catch {
    throw new Error("Helm " + args[0] + " failed");
  }
}

async function chartFiles(directory: string, relative = ""): Promise<string[]> {
  const files: string[] = [];
  for (const entry of await readdir(join(directory, relative), {
    withFileTypes: true,
  })) {
    const path = relative ? relative + "/" + entry.name : entry.name;
    if (entry.isDirectory()) {
      files.push(...(await chartFiles(directory, path)));
    } else if (entry.isFile() && !/[\u0000-\u001f\u007f\\]/.test(path)) {
      files.push(path);
    } else {
      throw new Error("Chart archive contains an unsupported file");
    }
  }
  return files.sort();
}

export async function patchResources(
  directory: string,
  files: string[],
): Promise<void> {
  const valuesPath = join(directory, "values.yaml");
  const values = parseDocument(await readFile(valuesPath, "utf8"));
  if (values.errors.length) {
    throw new Error("Invalid chart values.yaml");
  }
  // Preserve the exact upstream contract. Rendering probes below validate it
  // without installing a competing renderer or replacing the upstream schema.
  if (values.has("extraResources")) {
    return;
  }
  await mkdir(join(directory, "templates"), { recursive: true });
  await writeFile(
    join(directory, "templates", "extra-resources.yaml"),
    extraResources,
    { flag: "wx" },
  );
  values.set("extraResources", []);
  await writeFile(valuesPath, values.toString());
  if (files.includes("values.schema.json")) {
    const path = join(directory, "values.schema.json");
    const schema = JSON.parse(await readFile(path, "utf8"));
    schema.properties ??= {};
    schema.properties.extraResources = {
      type: "array",
      items: { type: ["object", "string"] },
    };
    await writeFile(path, JSON.stringify(schema, null, 2) + "\n");
  }
}

function renderSummary(rendered: string): {
  identities: string[];
  crds: unknown[];
} {
  const seen = new Set<string>();
  const crds: unknown[] = [];
  for (const doc of parseYaml<Record<string, unknown> | null>(rendered)) {
    if (!doc) {
      continue;
    }
    const metadata = doc.metadata as Record<string, unknown> | undefined;
    if (!metadata?.name) {
      continue;
    }
    const id = JSON.stringify([
      doc.apiVersion,
      doc.kind,
      metadata.namespace ?? "",
      metadata.name,
    ]);
    if (seen.has(id)) {
      throw new Error("Helm rendered duplicate resource identities");
    }
    seen.add(id);
    if (doc.kind === "CustomResourceDefinition") {
      crds.push(doc);
    }
  }
  return { identities: Array.from(seen).sort(), crds };
}

export async function chartValueFileArgs(
  directory: string,
  valueFiles: string[] = [],
): Promise<string[]> {
  if (!valueFiles.length) {
    return [];
  }
  const chartRoot = await realpath(directory);
  const args: string[] = [];
  for (const file of valueFiles) {
    if (!/^(?:[\w-][\w.-]*\/)*[\w-][\w.-]*\.ya?ml$/.test(file)) {
      throw new Error("Only chart-local YAML valueFiles are supported");
    }
    const candidate = join(chartRoot, file);
    const resolved = await realpath(candidate);
    const within = relative(chartRoot, resolved);
    if (
      !within ||
      within === ".." ||
      within.startsWith(".." + sep) ||
      isAbsolute(within) ||
      !(await lstat(candidate)).isFile()
    ) {
      throw new Error("Helm valueFiles must be regular files inside the chart");
    }
    args.push("-f", candidate);
  }
  return args;
}

async function verifyApplication(
  stage: string,
  directory: string,
  chart: Chart,
  path: string,
  objectOnly: boolean,
): Promise<string> {
  const content = await readLocalFile(path, "utf8");
  if (!content) {
    throw new Error("Missing Application for Helm rendering");
  }
  const app = parseYaml(content, { customSchema: applicationSchema })[0];
  const prefix =
    "helm/" + chart.group + "/" + (chart.directoryName ?? chart.chart) + "-";
  const deployed = app.spec.source.path;
  if (!deployed.startsWith(prefix) || !valid(deployed.slice(prefix.length))) {
    throw new Error("Application does not point at this vendored chart");
  }
  const previous = join(GlobalConfig.get("localDir"), deployed);
  const config = app.spec.source.helm;
  const values = config?.valuesObject ?? {};
  const valuesPath = join(stage, "application-values.json");
  const namespace = app.spec.destination.namespace;
  const oldValues = await chartValues(previous);
  const newValues = await chartValues(directory);
  const oldFiles = await chartValueFileArgs(previous, config?.valueFiles);
  const newFiles = await chartValueFileArgs(directory, config?.valueFiles);
  if (objectOnly) {
    for (const source of [values, oldValues, newValues]) {
      assertObjectOnlyResources(source.extraResources);
    }
    const uniqueFiles = new Set(
      [...oldFiles, ...newFiles].filter((file) => file !== "-f"),
    );
    for (const file of uniqueFiles) {
      const documents = parseYaml<Record<string, unknown> | null>(
        await readFile(file, "utf8"),
      );
      for (const document of documents) {
        assertObjectOnlyResources(document?.extraResources);
      }
    }
  }
  const render = (chartPath: string, files: string[]): Promise<string> =>
    helm(
      stage,
      "template",
      config?.releaseName ?? app.metadata.name,
      chartPath,
      "--namespace",
      namespace,
      "--include-crds",
      ...files,
      "-f",
      valuesPath,
    );
  await writeFile(valuesPath, JSON.stringify(values), { mode: 0o600 });
  const before = renderSummary(await render(previous, oldFiles));
  const after = renderSummary(await render(directory, newFiles));

  await writeFile(
    valuesPath,
    JSON.stringify({
      ...values,
      extraResources: extraResourceProbes(objectOnly),
    }),
  );
  const probes = await render(directory, newFiles);
  renderSummary(probes);
  if (
    !probes.includes("name: helm-vendor-object-probe") ||
    (!objectOnly &&
      !probes.includes("name: helm-vendor-string-probe-" + namespace))
  ) {
    throw new Error("Canonical resource injection probes did not render");
  }

  const removed = Object.keys(oldValues).filter(
    (key) => !Object.hasOwn(newValues, key),
  );
  const added = Object.keys(newValues).filter(
    (key) => !Object.hasOwn(oldValues, key),
  );
  const changed = Object.keys(oldValues).filter(
    (key) =>
      Object.hasOwn(newValues, key) &&
      !isDeepStrictEqual(oldValues[key], newValues[key]),
  );
  const affected = [...removed, ...changed].filter((key) =>
    Object.hasOwn(values, key),
  );
  const oldMetadata = await chartMetadata(previous);
  const newMetadata = await chartMetadata(directory);
  const list = (keys: string[]): string =>
    keys.length
      ? keys
          .sort()
          .slice(0, 20)
          .map((key) => JSON.stringify(key))
          .join(", ")
      : "none";
  return [
    "Helm lint and rendering passed with the Application values.",
    objectOnly
      ? "The object injection probe passed (object-only policy)."
      : "The object and string injection probes also passed.",
    "- Added default keys - " + list(added),
    "- Removed default keys - " + list(removed),
    "- Changed default keys - " + list(changed),
    "- Changed or removed keys overridden by the Application - " +
      list(affected),
    "- Chart dependencies - " +
      (isDeepStrictEqual(oldMetadata.dependencies, newMetadata.dependencies)
        ? "unchanged"
        : "changed"),
    "- Rendered resource identities - " +
      (isDeepStrictEqual(before.identities, after.identities)
        ? "unchanged"
        : "changed"),
    "- Rendered CRDs - " +
      (isDeepStrictEqual(before.crds, after.crds) ? "unchanged" : "changed"),
  ].join("\n");
}

async function chartMetadata(directory: string) {
  return parseYaml(await readFile(join(directory, "Chart.yaml"), "utf8"), {
    customSchema: metadataSchema,
  })[0];
}

async function chartValues(
  directory: string,
): Promise<Record<string, unknown>> {
  return parseYaml(await readFile(join(directory, "values.yaml"), "utf8"), {
    customSchema: z.record(z.string(), z.unknown()),
  })[0];
}

export async function materialize(
  chart: Chart,
  source: Source,
  version: string,
): Promise<UpdateArtifactsResult[]> {
  const chartPrefix =
    "helm/" + chart.group + "/" + (chart.directoryName ?? chart.chart);
  const target = chartPrefix + "-" + version;
  try {
    await lstat(join(GlobalConfig.get("localDir"), target));
    throw new Error("Target chart directory already exists");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw error;
    }
  }
  const objectOnly = await usesObjectOnlyResources(chartPrefix);
  const stage = await mkdtemp(join(tmpdir(), "renovate-helm-vendor-"));
  try {
    const sourceArgs =
      source.type === "oci"
        ? [source.url + "/" + chart.chart]
        : [chart.chart, "--repo", source.url];
    await helm(
      stage,
      "pull",
      ...sourceArgs,
      "--version",
      version,
      "--untar",
      "--untardir",
      stage,
    );
    const directory = join(stage, chart.chart);
    const files = await chartFiles(directory);
    const metadata = await chartMetadata(directory);
    if (metadata.name !== chart.chart || metadata.version !== version) {
      throw new Error(
        "Fetched chart metadata does not match the selected release",
      );
    }

    await patchResources(directory, files);
    await helm(stage, "lint", directory);
    const additions: UpdateArtifactsResult[] = [];
    for (const application of chart.applications) {
      const message = await verifyApplication(
        stage,
        directory,
        chart,
        application,
        objectOnly,
      );
      additions.push({ notice: { file: application, message } });
    }
    for (const path of await chartFiles(directory)) {
      additions.push({
        file: {
          type: "addition",
          path: target + "/" + path,
          contents: await readFile(join(directory, path)),
        },
      });
    }
    return additions;
  } finally {
    await rm(stage, { recursive: true, force: true });
  }
}
