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
        record["current"] = {"captured_at": iso(observed_at), "assets": deepcopy(assets)}
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
    active = {r["id"] for r in releases if not r["draft"] and r["published_at"]}
    due = [timestamp(r["published_at"]) + timedelta(hours=h)
           for r in state["releases"] if r["release_id"] in active
           for h in WINDOWS if r["snapshots"][f"{h}h"] is None]
    state["last_checked_at"] = iso(observed_at)
    state["next_measurement_at"] = iso(min(due)) if due else None
    planned = min(due + [observed_at.replace(second=0, microsecond=0) + timedelta(minutes=5)])
    tick = planned.replace(second=0, microsecond=0)
    if tick < planned:
        tick += timedelta(minutes=1)
    state["next_collection_at"] = iso(tick)
    return state


def collect(repository, state):
    releases = pages(f"/repos/{repository}/releases")
    for release in releases:
        if release["draft"] or not release["published_at"]:
            continue
        # The release response includes its assets; use the paginated endpoint
        # for large collections to keep unattended public API usage small.
        if len(release["assets"]) >= 30:
            release["assets"] = pages(f"/repos/{repository}/releases/{release['id']}/assets")
    return update(state, releases, datetime.now(UTC))


def total(snapshot):
    if snapshot is None or snapshot["status"] != "captured":
        return None
    return sum(a["download_count"] for a in snapshot["assets"])


def chart(state, channel):
    records = [r for r in state["releases"] if r["channel"] == channel][-12:][::-1]
    width, height = 720, max(180, 100 + len(records) * 114)
    valid = [snap for record in records for snap in record["snapshots"].values()
             if snap and snap["status"] in ("captured", "late") and not snap.get("issues")]
    maximum = max([sum(a["download_count"] for a in snap["assets"]) for snap in valid] + [1])
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             f'<title id="title">Plektra {channel.title()} APK downloads per release</title>',
             '<desc id="desc">Independent 24 and 72 hour measurements. Striped bars are late observations, labelled with their actual measurement time. Missing and invalid measurements have no bar.</desc>',
             '<defs><pattern id="late" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path d="M0 0V8" stroke="#f4f1e9" stroke-width="2"/></pattern></defs>',
             f'<rect width="720" height="{height}" fill="#f4f1e9"/>',
             '<g font-family="system-ui,sans-serif" fill="#1f1d19">',
             '<text x="24" y="30" font-size="17">APK downloads per measurement</text>']
    for index, record in enumerate(records):
        y = 64 + index * 114
        label = escape(record["tag"].removeprefix("nightly/").removeprefix("v"))
        parts.append(f'<text x="24" y="{y}" font-size="13">{label}</text>')
        for row, key in enumerate(("24h", "72h")):
            yy = y + 25 + row * 29
            snap = record["snapshots"][key]
            parts.append(f'<text x="24" y="{yy+4}" font-size="12" fill="#5d5a52">{key[:-1]} h</text>')
            parts.append(f'<path d="M76 {yy}H476" stroke="#d8d0bf" stroke-width="10"/>')
            if not snap or snap["status"] == "invalid" or snap.get("issues"):
                label = 'Invalid' if snap else 'Pending'
            else:
                count = sum(a["download_count"] for a in snap["assets"])
                age = (timestamp(snap["captured_at"]) - timestamp(record["published_at"])).total_seconds() / 3600
                bar_width = 400 * count / maximum
                color = '#2f80ed' if row == 0 else '#5d5a52'
                parts.append(f'<rect data-measurement="{key}" x="76" y="{yy-5}" width="{bar_width:.2f}" height="10" fill="{color}"/>')
                late = snap["status"] == "late"
                if late:
                    parts.append(f'<rect x="76" y="{yy-5}" width="{bar_width:.2f}" height="10" fill="url(#late)"/>')
                label = f'{count} · at {age:.1f} h' + (' · late' if late else '')
            parts.append(f'<text x="492" y="{yy+4}" font-size="12">{label}</text>')
    if not records:
        parts.append('<text x="24" y="92" font-size="14">Awaiting measurements</text>')
    parts.extend([f'<text x="24" y="{height-18}" font-size="12" fill="#5d5a52">Striped: collected late. Each bar shows the total at its actual measurement time.</text>', '</g></svg>'])
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
