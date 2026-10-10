#!/usr/bin/env python3
"""Collect immutable 24h/72h APK download snapshots using the GitHub REST API."""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from html import escape
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

UTC = timezone.utc
WINDOWS = (24, 72)
TOLERANCE = timedelta(hours=2)


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def pages(path):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "plektra-release-stats"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    result = []
    page = 1
    while True:
        request = Request(f"https://api.github.com{path}?per_page=100&page={page}", headers=headers)
        with urlopen(request, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("Expected a paginated GitHub API list")
        result.extend(batch)
        if len(batch) < 100:
            return result
        page += 1


def apk_assets(assets):
    return sorted([
        {"asset_id": a["id"], "name": a["name"], "created_at": a["created_at"],
         "download_count": a["download_count"]}
        for a in assets if a["name"].lower().endswith(".apk") and a["state"] == "uploaded"
    ], key=lambda a: a["asset_id"])


def update(state, releases, observed_at):
    """Pure transformation; completed measurements and removed releases are retained."""
    state = deepcopy(state)
    records = {r["release_id"]: r for r in state["releases"]}
    for release in releases:
        if release["draft"] or not release["published_at"]:
            continue
        published = timestamp(release["published_at"])
        assets = apk_assets(release["assets"])
        record = records.get(release["id"])
        if record is None:
            record = {
                "release_id": release["id"], "tag": release["tag_name"],
                "published_at": release["published_at"],
                "channel": "nightly" if release["tag_name"].startswith("nightly/") or
                    "-nightly." in release["tag_name"] else "stable",
                "prerelease": release["prerelease"], "first_seen_at": iso(observed_at),
                "initial_asset_ids": [a["asset_id"] for a in assets],
                "asset_changes_detected": False,
                "snapshots": {"24h": None, "72h": None},
            }
            records[release["id"]] = record
        if all(record["snapshots"].values()):
            continue
        if [a["asset_id"] for a in assets] != record["initial_asset_ids"]:
            record["asset_changes_detected"] = True
        for hours in WINDOWS:
            key = f"{hours}h"
            due = timestamp(record["published_at"]) + timedelta(hours=hours)
            if record["snapshots"][key] is not None or observed_at < due:
                continue
            reasons = []
            if record["published_at"] != release["published_at"]:
                reasons.append("publication_time_changed")
            if record["asset_changes_detected"] or any(timestamp(a["created_at"]) > due for a in assets):
                reasons.append("apk_assets_changed")
            if not assets:
                reasons.append("no_apk_assets")
            if hours == 72:
                first = record["snapshots"]["24h"]
                if first:
                    counts = {a["asset_id"]: a["download_count"] for a in first["assets"]}
                    if any(a["download_count"] < counts.get(a["asset_id"], 0) for a in assets):
                        reasons.append("download_count_decreased")
            status = "late" if observed_at > due + TOLERANCE else "invalid" if reasons else "captured"
            record["snapshots"][key] = {
                "due_at": iso(due), "captured_at": iso(observed_at), "status": status,
                "issues": reasons, "assets": deepcopy(assets),
            }
    state["releases"] = sorted(records.values(), key=lambda r: (r["published_at"], r["release_id"]))
    return state


def collect(repository, state):
    releases = pages(f"/repos/{repository}/releases")
    known = {r["release_id"]: r for r in state["releases"]}
    for release in releases:
        if release["draft"] or not release["published_at"]:
            continue
        record = known.get(release["id"])
        if record and all(record["snapshots"].values()):
            continue
        release["assets"] = pages(f"/repos/{repository}/releases/{release['id']}/assets")
    return update(state, releases, datetime.now(UTC))


def total(snapshot):
    if snapshot is None or snapshot["status"] != "captured":
        return None
    return sum(a["download_count"] for a in snapshot["assets"])


def chart(state, channel):
    records = [r for r in state["releases"] if r["channel"] == channel][-12:]
    width, height = 720, 400
    left, right, top, bottom = 54, 700, 88, 292
    values = [(total(r["snapshots"]["24h"]), total(r["snapshots"]["72h"])) for r in records]
    maximum = max([v for pair in values for v in pair if v is not None] + [1])
    maximum = max(50, ((maximum + 49) // 50) * 50)
    def y(value):
        return bottom - value / maximum * (bottom - top)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             f'<title id="title">Plektra {channel.title()} APK downloads per release</title>',
             '<desc id="desc">Snapshots after 24 and 72 hours. The upper segment contains additional downloads between those times. Missing measurements are not zero.</desc>',
             '<rect width="720" height="400" fill="#0a0f14"/>',
             '<g font-family="system-ui,sans-serif" fill="#edf8fa">',
             f'<text x="18" y="29" font-size="20">{channel.title()} APK downloads</text>',
             '<rect x="18" y="46" width="13" height="13" fill="#72e6ec"/><text x="39" y="58" font-size="13">Up to 24 h</text>',
             '<rect x="180" y="46" width="13" height="13" fill="#3c7b77"/><text x="201" y="58" font-size="13">Additional downloads up to 72 h</text>']
    for i in range(5):
        value = maximum * i / 4
        parts.append(f'<path d="M{left} {y(value):.1f}H{right}" stroke="#2b3a41"/>')
        parts.append(f'<text x="{left-8}" y="{y(value)+4:.1f}" text-anchor="end" font-size="12">{value:g}</text>')
    slot = (right - left) / max(len(records), 1)
    bar = min(42, slot * .65)
    for index, (record, (first, second)) in enumerate(zip(records, values)):
        x = left + slot * (index + .5)
        label = record["published_at"][:10]
        parts.append(f'<text x="{x:.1f}" y="314" transform="rotate(35 {x:.1f} 314)" font-size="11">{label}</text>')
        parts.append(f'<g><title>{escape(record["tag"])}</title>')
        if first is not None:
            parts.append(f'<rect x="{x-bar/2:.1f}" y="{y(first):.1f}" width="{bar:.1f}" height="{bottom-y(first):.1f}" fill="#72e6ec"/>')
        if second is not None:
            base = first if first is not None else 0
            fill = '#3c7b77' if first is not None else 'none'
            parts.append(f'<rect x="{x-bar/2:.1f}" y="{y(second):.1f}" width="{bar:.1f}" height="{y(base)-y(second):.1f}" fill="{fill}" stroke="#3c7b77"/>')
        value = second if second is not None else first
        if value is not None:
            parts.append(f'<text x="{x:.1f}" y="{y(value)-8:.1f}" text-anchor="middle" font-size="13">{value}</text>')
        else:
            parts.append(f'<text x="{x:.1f}" y="{bottom-9}" text-anchor="middle" font-size="16">—</text>')
        parts.append('</g>')
    if not any(v is not None for pair in values for v in pair):
        parts.append('<text x="377" y="178" text-anchor="middle" font-size="16">Awaiting valid snapshots</text>')
    parts.extend(['<text x="18" y="383" font-size="12" fill="#a9bbc0">APKs combined · Outlined bars: 72 h total without a valid 24 h snapshot</text>', '</g></svg>'])
    return '\n'.join(parts) + '\n'


def write_changed(path, content):
    if not path.exists() or path.read_text() != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(content)
        temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="pkb-rocks/plektra")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--charts-dir", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Expected owner/repository")
    state = {"schema_version": 1, "repository": args.repository,
             "capture_tolerance_seconds": int(TOLERANCE.total_seconds()), "releases": []}
    if args.output.exists():
        state = json.loads(args.output.read_text())
        if state["schema_version"] != 1 or state["repository"] != args.repository:
            raise ValueError("Statistics schema or repository does not match")
    result = collect(args.repository, state)
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    write_changed(args.output, content)
    if args.charts_dir:
        for channel in ("nightly", "stable"):
            write_changed(args.charts_dir / f"{channel}-downloads.svg", chart(result, channel))
    for r in result["releases"]:
        print(r["tag"], {k: v["status"] if v else "pending" for k, v in r["snapshots"].items()})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Release statistics failed: {error}", file=sys.stderr)
        sys.exit(1)
