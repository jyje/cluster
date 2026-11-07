import { execFile } from "node:child_process";
import {
  lstat,
  mkdir,
  mkdtemp,
  readdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
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
          valuesObject: z.record(z.string(), z.unknown()).optional(),
        })
        .optional(),
    }),
  }),
});
const metadataSchema = z.object({ name: z.string(), version: z.string() });
type Chart = { group: string; chart: string; applications: string[] };
type Source = { type: "http" | "oci"; url: string };

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

async function patchResources(
  directory: string,
  files: string[],
): Promise<void> {
  await mkdir(join(directory, "templates"), { recursive: true });
  await writeFile(
    join(directory, "templates", "extra-resources.yaml"),
    extraResources,
  );
  const valuesPath = join(directory, "values.yaml");
  const values = parseDocument(await readFile(valuesPath, "utf8"));
  if (values.errors.length) {
    throw new Error("Invalid chart values.yaml");
  }
  if (!values.has("extraResources")) {
    values.set("extraResources", []);
    await writeFile(valuesPath, values.toString());
  }
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

function validateIdentities(rendered: string): void {
  const seen = new Set<string>();
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
  }
}

async function verifyApplication(
  stage: string,
  directory: string,
  chart: Chart,
  path: string,
): Promise<void> {
  const content = await readLocalFile(path, "utf8");
  if (!content) {
    throw new Error("Missing Application for Helm rendering");
  }
  const app = parseYaml(content, { customSchema: applicationSchema })[0];
  if (
    !app.spec.source.path.startsWith(
      "helm/" + chart.group + "/" + chart.chart + "-",
    )
  ) {
    throw new Error("Application does not point at this vendored chart");
  }
  const config = app.spec.source.helm;
  const values = config?.valuesObject ?? {};
  const valuesPath = join(stage, "application-values.json");
  const namespace = app.spec.destination.namespace;
  const args = [
    "template",
    config?.releaseName ?? app.metadata.name,
    directory,
    "--namespace",
    namespace,
    "--include-crds",
    "-f",
    valuesPath,
  ];
  await writeFile(valuesPath, JSON.stringify(values), { mode: 0o600 });
  validateIdentities(await helm(stage, ...args));

  await writeFile(
    valuesPath,
    JSON.stringify({
      ...values,
      extraResources: [
        {
          apiVersion: "v1",
          kind: "ConfigMap",
          metadata: { name: "helm-vendor-object-probe" },
        },
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: helm-vendor-string-probe-{{ .Release.Namespace }}\n",
      ],
    }),
  );
  const probes = await helm(stage, ...args);
  validateIdentities(probes);
  if (
    !probes.includes("name: helm-vendor-object-probe") ||
    !probes.includes("name: helm-vendor-string-probe-" + namespace)
  ) {
    throw new Error("Canonical resource injection probes did not render");
  }
}

export async function materialize(
  chart: Chart,
  source: Source,
  version: string,
): Promise<UpdateArtifactsResult[]> {
  const target = "helm/" + chart.group + "/" + chart.chart + "-" + version;
  try {
    await lstat(join(GlobalConfig.get("localDir"), target));
    throw new Error("Target chart directory already exists");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw error;
    }
  }
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
    const metadata = parseYaml(
      await readFile(join(directory, "Chart.yaml"), "utf8"),
      { customSchema: metadataSchema },
    )[0];
    if (metadata.name !== chart.chart || metadata.version !== version) {
      throw new Error(
        "Fetched chart metadata does not match the selected release",
      );
    }

    await patchResources(directory, files);
    await helm(stage, "lint", directory);
    for (const application of chart.applications) {
      await verifyApplication(stage, directory, chart, application);
    }
    const additions: UpdateArtifactsResult[] = [];
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
