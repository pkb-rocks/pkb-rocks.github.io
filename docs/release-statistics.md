# Release download statistics

The `Release download statistics` workflow collects two APK download snapshots per
published release: 24 and 72 hours after `published_at`. It runs hourly at minute
17 and can also be started manually. It does not build Android packages.

The collector uses Python 3's standard library and GitHub's REST API. The workflow
uses a standard Ubuntu runner and the repository's `GITHUB_TOKEN` with
`contents: write`. It writes `release-stats.json`, `nightly-downloads.svg`, and
`stable-downloads.svg` on this Pages repository's `stats` branch,
creating an orphan branch on the first successful run. It commits only changed
data and pushes without force. Concurrent collector runs are serialized.
Branch rules must permit the Actions token to update `stats`.

## Data contract

The JSON document has `schema_version: 1`, `repository`,
`capture_tolerance_seconds: 7200`, and a chronological `releases` array.
Each release includes its ID, tag, publication time, channel, prerelease flag,
first observation, initially observed APK asset IDs, an asset-change flag,
and `snapshots` with `24h` and `72h` entries.

Nightly tags (`nightly/` or `-nightly.`) determine the Nightly channel. Other tags
are Stable; `prerelease` remains a separate field so other preview releases can
be filtered explicitly.

A snapshot is `null` until due. Once recorded it is immutable and contains:

- `due_at`: the target time relative to publication.
- `captured_at`: the actual collection time, after the API requests complete.
- `status`: `captured`, `late`, or `invalid`.
- `issues`: observed changes to publication time, APK asset IDs, decreased
  counters, or missing APKs.
- `assets`: uploaded `.apk` assets, each with ID, name, creation time, and
  cumulative `download_count`. Checksums, source archives, and SBOMs are excluded.

`captured` means the observation was within two hours of its target without
detected continuity problems. `late` retains the actual observed counters but
must not be presented as a regular 24h/72h measurement. `invalid` means the
observation was timely but has a continuity problem. Late observations can
also have `issues`.

GitHub Actions schedules can be delayed or disabled after repository inactivity.
The collector records missed deadlines as `late`; historical counters cannot be
reconstructed. Initial activation will therefore mark already overdue releases
as late. Completed records remain available even if a release is later removed.
API failures leave the existing JSON unchanged and fail the workflow.

Asset-ID changes observed before the second snapshot invalidate subsequent
timely observations. Replacements before the collector's first observation
cannot always be detected; asset creation after a measurement's deadline is
flagged. Do not edit assets during a measurement window if comparability is
required. Changes after both snapshots are complete do not alter those records.

## Presentation handoff

The current home page displays a minimal chart and table. The SVG charts are
regenerated only when their content changes. A future design can use the same
data contract. Public consumers can read:

```text
https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/release-stats.json
```

For stacked bars, use the 24h count as the lower segment and `72h - 24h` as the
upper segment. The top is the 72h count. Use only `captured` measurements and
match assets by ID before calculating differences. A release with only a valid
24h snapshot has no upper segment yet. Missing, late, or invalid values are gaps,
not zero downloads. A valid 72h value without a valid 24h value can be shown as
a standalone total, but cannot be split into these segments.

Keep Stable and Nightly separate. Preserve APK variants in the data; summing
them measures downloads across variants. Downloads do not identify unique users
or installations, and intervening releases can affect a release's reach.

## Local checks

```sh
python3 -m unittest discover -s scripts/tests -p 'test_release_stats.py'
python3 scripts/collect-release-stats.py --output /tmp/plektra-release-stats.json --charts-dir /tmp/plektra-release-charts
```

The second command reads the public API and writes only the specified local
file. Set `GH_TOKEN` for authenticated API limits. Reusing that file preserves
completed snapshots. Normal runs do not update the file when nothing changes.

The production source repository is always `pkb-rocks/plektra`; the workflow
token writes only this Pages repository. The public source API requires no
additional cross-repository credentials. The existing branch-based Pages
deployment remains in place. Only publication of website code rebuilds Pages;
statistic updates are read from the public `stats` branch at page load.
