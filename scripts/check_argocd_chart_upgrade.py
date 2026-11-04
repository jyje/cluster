#!/usr/bin/env python3
"""Offline compatibility guard for the Argo CD 3.5 to 3.6 chart upgrade.

Requires helm and mikefarah/yq. It renders using the Application values in
memory and reports schema paths only, never rendered manifests or values.
This is not an API-server, admission, CEL, or rollout test.
"""

import collections
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "clusters/r4spi/apps/argocd.yaml"
OLD = ROOT / "helm/argo/argo-cd-10.4.2"
NEW = ROOT / "helm/argo/argo-cd-10.12.0"
IGNORED = {"description", "title", "example", "examples", "externalDocs"}


def command(args, data=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed with exit code {result.returncode}")
    return result.stdout


def render(chart, values):
    manifest = command(["helm", "template", "argocd", str(chart), "-n", "argocd",
                        "--include-crds", "-f", "-"], values)
    documents = command(["yq", "-o=json", "-I=0", 'select(.kind != null)'], manifest)
    return [json.loads(line) for line in documents.splitlines() if line.strip()]


def without_docs(value):
    if isinstance(value, dict):
        return {k: without_docs(v) for k, v in value.items() if k not in IGNORED}
    if isinstance(value, list):
        return [without_docs(v) for v in value]
    return value


def schema_nodes(schema, path="", result=None):
    if result is None:
        result = {}
    if not isinstance(schema, dict):
        return result
    children = {"properties", "items", "additionalProperties"}
    here = {k: without_docs(v) for k, v in schema.items()
            if k not in IGNORED and k not in children}
    if "additionalProperties" in schema and not isinstance(schema["additionalProperties"], dict):
        here["additionalProperties"] = schema["additionalProperties"]
    result[path or "/"] = here
    for name, child in schema.get("properties", {}).items():
        schema_nodes(child, f"{path}/{name}", result)
    if isinstance(schema.get("items"), dict):
        schema_nodes(schema["items"], f"{path}/*", result)
    if isinstance(schema.get("additionalProperties"), dict):
        schema_nodes(schema["additionalProperties"], f"{path}/{{key}}", result)
    return result


def compare_schemas(old, new):
    before, after = schema_nodes(old), schema_nodes(new)
    removed = sorted(before.keys() - after.keys())
    changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    return removed, changed


def crds(documents):
    return {doc["metadata"]["name"]: doc for doc in documents
            if doc.get("kind") == "CustomResourceDefinition"}


def identities(documents):
    return collections.Counter((d.get("apiVersion"), d.get("kind"),
                                d.get("metadata", {}).get("namespace", ""),
                                d.get("metadata", {}).get("name", ""))
                               for d in documents)


def main():
    values = command(["yq", "-o=json", ".spec.source.helm.valuesObject // {}", str(APP)])
    before, after = render(OLD, values), render(NEW, values)
    if identities(before) != identities(after):
        raise ValueError("Rendered resource identities changed; review the resource diff")
    old_crds, new_crds = crds(before), crds(after)
    if old_crds.keys() != new_crds.keys() or len(old_crds) != 3:
        raise ValueError("Unexpected CRD set; review the resource diff")
    for name, old in sorted(old_crds.items()):
        new = new_crds[name]
        a, b = old["spec"], new["spec"]
        a_spec = without_docs({k: v for k, v in a.items() if k != "versions"})
        b_spec = without_docs({k: v for k, v in b.items() if k != "versions"})
        if a_spec != b_spec:
            raise ValueError(f"{name}: CRD non-version specification changed")
        av = {v["name"]: v for v in a["versions"]}
        bv = {v["name"]: v for v in b["versions"]}
        if av.keys() != bv.keys():
            raise ValueError(f"{name}: CRD version set changed")
        for version in av:
            x, y = av[version], bv[version]
            if any(x.get(k) != y.get(k) for k in ("served", "storage")):
                raise ValueError(f"{name}: served/storage settings changed")
            x_version = without_docs({k: v for k, v in x.items() if k != "schema"})
            y_version = without_docs({k: v for k, v in y.items() if k != "schema"})
            if x_version != y_version:
                raise ValueError(f"{name}: version settings changed")
            removed, changed = compare_schemas(x["schema"]["openAPIV3Schema"],
                                               y["schema"]["openAPIV3Schema"])
            if removed or changed:
                raise ValueError(f"{name}: existing schema fields or constraints changed")
        print(f"PASS {name}: existing schema constraints and versions preserved")
    print("PASS rendered resource identities unchanged")
    print("NOTE: Kubernetes admission, CEL, pruning, SSO and rollout were not tested")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
