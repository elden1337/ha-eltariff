#!/usr/bin/env python3
"""Compare the latest RI-SE release with a reviewed specification fingerprint."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

UPSTREAM = "RI-SE/Eltariff-API"
BASELINE = Path(__file__).resolve().parents[1] / ".github/upstream-eltariff-baseline.json"
MARKER = "<!-- ha-eltariff-upstream-specification -->"
MAX_DEFINITION_SIZE = 5 * 1024 * 1024


def gh(*args: str) -> bytes:
    return subprocess.run(["gh", "api", *args], check=True, stdout=subprocess.PIPE).stdout


def fingerprint_archive(archive: bytes) -> dict[str, str]:
    """Hash canonical JSON from all files under specification, without extracting the archive."""
    files: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
        for member in source:
            parts = PurePosixPath(member.name).parts
            if len(parts) < 3 or parts[1] != "specification" or not member.isfile():
                continue
            name = "/".join(parts[2:])
            if not name.endswith(".json"):
                continue
            if ".." in parts or name in files or member.size > MAX_DEFINITION_SIZE:
                raise ValueError(f"Invalid specification archive member: {member.name}")
            content = source.extractfile(member)
            if content is None:
                raise ValueError(f"Cannot read specification: {member.name}")
            data = json.load(content)
            canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            files[name] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if not files:
        raise ValueError("Upstream release contains no specification JSON files")
    return dict(sorted(files.items()))


def latest_release() -> tuple[dict, dict[str, str]]:
    release = json.loads(gh(f"repos/{UPSTREAM}/releases/latest"))
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not tag:
        raise ValueError("Latest upstream release has no tag")
    archive = gh(f"repos/{UPSTREAM}/tarball/{quote(tag, safe='')}")
    return release, fingerprint_archive(archive)


def changes(baseline: dict[str, str], upstream: dict[str, str]) -> list[tuple[str, str]]:
    result = []
    for name in sorted(baseline.keys() | upstream.keys()):
        if name not in baseline:
            result.append(("Added", name))
        elif name not in upstream:
            result.append(("Removed", name))
        elif baseline[name] != upstream[name]:
            result.append(("Changed", name))
    return result


def issue_body(baseline: dict, release: dict, differences: list[tuple[str, str]]) -> str:
    old_tag = quote(baseline["release"], safe="")
    new_tag = quote(release["tag_name"], safe="")
    lines = [
        "## Upstream Eltariff API changes",
        "",
        f"Reviewed baseline: `{baseline['release']}`",
        f"Latest release: [{release['tag_name']}]({release['html_url']})",
        f"Published: `{release['published_at']}`",
        f"[Compare releases](https://github.com/{UPSTREAM}/compare/{old_tag}...{new_tag})",
        "",
        "JSON definitions with different canonical fingerprints:",
        "",
    ]
    lines.extend(f"- **{kind}:** `{name}`" for kind, name in differences)
    lines.extend(
        [
            "",
            "Review the upstream changelog and changes, update the integration and tests as",
            "needed, then refresh `.github/upstream-eltariff-baseline.json` using",
            "`python scripts/check_upstream_eltariff.py --write-baseline`.",
            "The baseline records a reviewed release; it does not assert full API compliance.",
            "Close this issue after the updates and baseline are merged.",
            "",
            MARKER,
        ]
    )
    return "\n".join(lines)


def report_issue(repo: str, release: dict, body: str) -> str:
    pages = json.loads(gh(f"repos/{repo}/issues?state=open&per_page=100", "--paginate", "--slurp"))
    matching = [
        issue
        for page in pages
        for issue in page
        if "pull_request" not in issue and MARKER in (issue.get("body") or "")
    ]
    if len(matching) > 1:
        raise ValueError("More than one open upstream synchronization issue has the marker")
    title = f"Investigate Eltariff API {release['tag_name']} changes"
    if matching:
        response = gh(
            f"repos/{repo}/issues/{matching[0]['number']}",
            "--method", "PATCH", "-f", f"title={title}", "-f", f"body={body}",
        )
    else:
        response = gh(
            f"repos/{repo}/issues",
            "--method", "POST", "-f", f"title={title}", "-f", f"body={body}",
        )
    return json.loads(response)["html_url"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the latest release after manually reviewing its changes",
    )
    args = parser.parse_args()
    release, files = latest_release()
    if args.write_baseline:
        BASELINE.write_text(
            json.dumps({"release": release["tag_name"], "files": files}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Recorded {release['tag_name']} in {BASELINE}")
        return
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    if not baseline.get("release") or not isinstance(baseline.get("files"), dict):
        raise ValueError("Invalid upstream baseline")
    differences = changes(baseline["files"], files)
    if not differences:
        print(f"Specification matches the reviewed baseline ({baseline['release']}).")
        return
    repo = os.environ["GITHUB_REPOSITORY"]
    url = report_issue(repo, release, issue_body(baseline, release, differences))
    print(f"Upstream specification changed; issue: {url}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(f"Upstream check failed: {exc}", file=sys.stderr)
        sys.exit(1)
