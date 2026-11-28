#!/usr/bin/env python3
"""Apply the vendored chart retention rule to helm/<group>/<chart>-<version>/.

A chart is identified by its group directory and the name in Chart.yaml. For each
chart, keep:

1. the 3 versions most recently deployed, according to the history of
   `path: helm/...` lines in clusters/ on the checked-out branch,
2. every directory an Argo CD Application references now, and
3. every version newer than the newest referenced one (waiting for deployment).

A chart listed in helm-sources/catalog.yaml with no deployment yet keeps its
newest version. Everything else is removed. Charts written in this repository are
not vendored and are never touched.

Run from a full clone of an up-to-date main:

    python3 scripts/prune_vendored_charts.py          # list what would be removed
    python3 scripts/prune_vendored_charts.py --apply  # git rm those directories
"""

import argparse
import collections
import pathlib
import re
import subprocess
import sys

KEEP_DEPLOYED = 3
LOCAL_CHARTS = ("helm/jyje/", "helm/homer-legacy-jyje")

PATH_LINE = re.compile(r"""^\s*(?:-\s*)?path:\s*["']?(?:\./)?(helm/[^\s"'#]+)""")


def version_key(version):
    """Sort key for chart versions. A prerelease sorts before its release."""
    core, _, pre = version.lstrip("v").partition("+")[0].partition("-")
    numbers = tuple(int(n) for n in re.findall(r"\d+", core))
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.-]", pre) if p)
    return numbers, 0 if pre else 1, parts


def referenced_directory(line):
    match = PATH_LINE.match(line)
    return match.group(1).rstrip("/") if match else None


def deployment_order(log_lines):
    """Map a chart directory name to the position of its latest deployment.

    The input is `git log --reverse -p` output, so a higher number is newer. The
    directory name is the key because older commits used helm/<chart>-<version>
    without a group directory.
    """
    order = {}
    for position, line in enumerate(log_lines):
        if line.startswith("+") and not line.startswith("+++"):
            directory = referenced_directory(line[1:])
            if directory:
                order[directory.rsplit("/", 1)[-1]] = position
    return order


def select_removals(charts, deployed, referenced, cataloged):
    """Return the chart directories to remove.

    charts: {(group, name): {directory: version}}
    deployed: {directory name: deployment position}
    referenced: set of directories used by Applications now
    cataloged: set of (group, chart name) opted in to automatic vendoring
    """
    removals = []
    for family, versions in charts.items():
        history = sorted(
            (d for d in versions if d.rsplit("/", 1)[-1] in deployed),
            key=lambda d: deployed[d.rsplit("/", 1)[-1]],
            reverse=True,
        )
        keep = set(history[:KEEP_DEPLOYED])
        current = [d for d in versions if d in referenced]
        keep.update(current)
        if current:
            newest = max(version_key(versions[d]) for d in current)
            keep.update(d for d, v in versions.items() if version_key(v) > newest)
        if not keep and family in cataloged:
            keep.add(max(versions, key=lambda d: version_key(versions[d])))
        removals.extend(d for d in versions if d not in keep)
    return sorted(removals)


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, errors="replace"
    ).stdout


def chart_field(text, field):
    match = re.search(rf"""^{field}:\s*["']?([^\s"'#]+)""", text, re.MULTILINE)
    if not match:
        raise SystemExit(f"Chart.yaml has no {field}")
    return match.group(1)


def load_charts(root):
    charts = collections.defaultdict(dict)
    for manifest in sorted((root / "helm").glob("*/*/Chart.yaml")):
        directory = manifest.parent.relative_to(root).as_posix()
        if directory.startswith(LOCAL_CHARTS):
            continue
        text = manifest.read_text()
        family = (directory.split("/")[1], chart_field(text, "name"))
        charts[family][directory] = chart_field(text, "version")
    return charts


def load_cataloged(root):
    """Read (group, chart) pairs from the charts section of the catalog."""
    pairs, group, in_charts = set(), None, False
    for line in (root / "helm-sources" / "catalog.yaml").read_text().splitlines():
        if re.match(r"^\S", line):
            in_charts = line.startswith("charts:")
        elif in_charts:
            if match := re.match(r"^    group:\s*(\S+)", line):
                group = match.group(1)
            elif match := re.match(r"^    chart:\s*(\S+)", line):
                pairs.add((group, match.group(1)))
    return pairs


def load_referenced(root):
    referenced = set()
    for manifest in (root / "clusters").rglob("*.y*ml"):
        for line in manifest.read_text().splitlines():
            if directory := referenced_directory(line):
                referenced.add(directory)
    return referenced


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="git rm the directories")
    args = parser.parse_args()

    root = pathlib.Path(git(".", "rev-parse", "--show-toplevel").strip())
    if git(root, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise SystemExit("A shallow clone has no complete deployment history")

    log = git(root, "log", "--first-parent", "-m", "--reverse", "--no-renames", "--unified=0",
              "--format=", "-p", "HEAD", "--", "clusters")
    referenced = load_referenced(root)
    missing = sorted(d for d in referenced if not (root / d / "Chart.yaml").is_file())
    if missing:
        raise SystemExit("Applications reference missing charts: " + ", ".join(missing))

    removals = select_removals(
        load_charts(root), deployment_order(log.splitlines()), referenced, load_cataloged(root)
    )
    for directory in removals:
        print(directory)
    print(f"{len(removals)} chart directories to remove", file=sys.stderr)
    if args.apply and removals:
        git(root, "rm", "-r", "-q", "--", *removals)


if __name__ == "__main__":
    main()
