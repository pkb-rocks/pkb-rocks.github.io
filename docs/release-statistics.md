# Release download statistics

Fedora collects public Plektra release data and publishes verified bot updates to this
repository's `stats` branch. GitHub Actions tests the scripts; it does not publish
statistics. The website reads the branch directly, so statistics updates need no
Pages deployment.

## Measurements

Each published release has immutable `24h` and `72h` snapshots relative to its
GitHub `published_at` time. APK variants remain separate in the data and are
summed for the displayed download count. Checksums, SBOMs and source archives are
excluded. Downloads do not identify unique users or installations.

A snapshot contains `due_at`, `captured_at`, `status`, `issues` and `assets`.
`captured` means the observation was within two hours of its target and had no
asset continuity problems. `late` keeps the actual observed counter and time;
`invalid` identifies changed assets, decreased counters or other continuity
problems. Existing snapshots are never overwritten or backfilled with invented
historical counts. Removed releases retain their existing records.

Each release also has `current`, with an observed APK asset list and
`captured_at`. Current counts refresh on collection even after both fixed
snapshots are complete. `last_checked_at` records the observation used by the
published data. `next_collection_at` and `next_measurement_at` describe collection;
`next_publication_at` identifies the next planned daily or fixed-measurement update. The website displays
current totals, fixed snapshots and explicitly labelled late values. Orange
circles in the chart identify late observations; the table gives their elapsed
hours and its cell tooltip gives the exact timestamp.

## Fedora collector

See [installation and operation](../ops/fedora/README.md).

A user systemd timer checks local deadlines each minute. It queries releases every
five minutes and at the first timer tick after a pending 24h/72h deadline. A new
release triggers publication immediately after detection and adds deadlines
relative to GitHub's actual publication time. A newly captured 24h/72h measurement
also triggers immediate publication. Otherwise, changed totals and star history
are published together daily at **03:17 UTC**. Changes only to checking timestamps
do not create commits. Star API failures retain the previous star files and
retry after five minutes without blocking release or measurement publications. A powered-off or disconnected machine
cannot capture historical counters; the next successful collection records any
missed observation as late. Scheduled timestamps describe plans, not guarantees.

The collection API calls use public data. Publication uses the dedicated PIV
key on YK2 (serial 38906327, slot 9a), registered on `pkb-rocks-bot` for both SSH
authentication and commit signing. Bot commits use `bot@pkb.rocks` and this format:

```text
chore(stats): refresh download counts and star history

Automated statistics update by the PKB.rocks Bot.
Cryptographic verification records origin and integrity; no individual approval is expressed.
```

The key is generated on the YubiKey and configured without PIN or touch for
unattended operation. The separate APK signing slots retain their original
policies. A short-lived agent exposes only the bot key and checks its hardware
identity before every signature. Bot updates are separate from personal GitHub
contributions. The bot email must be verified on GitHub.

A process lock prevents overlapping local runs. Measurements are atomically saved to Fedora's `pending-release-stats.json` before
rendering, star collection or publication. On the next run, published measurements
remain authoritative and unpublished local measurements are preserved. This
prevents a failed push or restart from replacing an already observed counter with
a later counter. `next-run.json` records collection, daily and separate star-retry deadlines.
A star retry does not repeat an already completed daily totals update. Other
failures retry after five minutes while retaining any unfinished daily work.
Rendering completes in a temporary directory. A temporary index creates one signed commit for all six
files. Local SSH verification must pass before the non-force push. A concurrent
branch update rejects publication instead of overwriting another writer's
observations. Hardware, signing and push failures are recorded in the journal.

## Public files

The schema remains version 1; the current-count and schedule fields are additive.

```text
https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/release-stats.json
https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/nightly-downloads.svg
https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/stable-downloads.svg
https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/star-history.json
https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/star-history.svg
https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/star-history-dark.svg
```

The star chart uses GitHub's daily history and displays the current repository
star count separately. Chart headings are provided by the website instead of
being repeated visibly inside the SVG. All SVGs retain accessible titles.

## Checks

```sh
python3 -m unittest discover -s scripts/tests -p 'test_*.py'
node scripts/tests/test-release-statistics.mjs
node scripts/tests/test-download.mjs
python3 scripts/run-release-stats.py --no-push
```
