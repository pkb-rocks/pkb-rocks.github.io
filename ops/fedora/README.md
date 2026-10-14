# Fedora statistics collector

Canonical checkout: `/home/user/gits/GitHub/pkb-rocks.github.io`.
Runtime data: `/home/user/.local/state/plektra-stats/`.
User units: `/home/user/.config/systemd/user/plektra-stats.{service,timer}`.
Bot configuration: `/home/user/.config/plektra-stats/`.

Fedora schedules collection and publishes all six files together on `stats`.
Commits use `PKB.rocks Bot <bot@pkb.rocks>` and the `pkb-rocks-bot` account.
A dedicated P-256 key was generated on **YK2, serial 38906327, PIV slot 9a**.
Its PIN and touch policies are **Never** for unattended operation. Existing
APK keys in slots **9c and 82** retain their original policies.

## Identity and key registration

The public key is registered on `pkb-rocks-bot` twice: as Authentication Key and
Signing Key. GitHub supports using the same key for both purposes. The email
`bot@pkb.rocks` must be verified on that account for commit attribution and
verification. Repository permissions belong to the bot account; its currently
assigned all-repository Write role applies beyond this checkout.

The private key remains on the YubiKey. Public files under
`~/.config/plektra-stats/yubikey/` include `bot.pub`, its certificate and hardware
attestations. SSH fingerprint:

```text
SHA256:mMHrtblGMZ57srwLF8BlFRu89bCBAJOWNY2qOobUss8
```

`enroll-bot-key.py` is a one-time setup tool. It requires an interactive PIN entry
to unlock the device's protected management key. It refuses an occupied slot,
checks the existing APK slot metadata and tests the new key in a fresh session.
Do not rerun enrollment to repair a runtime issue. Never reset PIV to repair this
collector: the existing APK keys must be preserved.

## Runtime

Git, Python 3 and the YubiKey Manager Python libraries are required. On Fedora,
`yubikey-manager`, `python3-yubikey-manager`, `python3-pyscard`, `python3-fido2`
and `yubico-piv-tool` were downloaded from the Fedora repositories and extracted
without root under `~/.local/share/agent-tools/yubico-piv-tool/root/`. Scripts add
that runtime's Python package directories to their import path. System packages
for Python cryptography, Click, PyUSB and PC/SC are also used.

`piv_bot.py` provides a short-lived SSH agent that exposes only this bot key.
Standard PKCS#11 providers advertise token-wide PIN login requirements even when
a particular slot has PIN policy Never; this adapter uses the YubiKey Manager
PIV API directly. It performs no PIN or management-key operations. Before every
signature it checks serial number, slot, public key, on-device generation and
PIN/touch policies. Missing hardware or a mismatch stops the operation.

The repository-local Git configuration uses SSH signing and the public key above.
`~/.config/plektra-stats/ssh_config` selects only that identity. The publisher
starts its own agent and overrides inherited SSH agent/command settings. Personal
keys are never used as a fallback.

Configuration files:

- `bot.json`: copy `bot.example.json`; fields identify the account, email, serial,
  slot and public-key path.
- `allowed-signers`: `bot@pkb.rocks` followed by the SSH public key, used for local
  signature verification.
- `ssh_config`: host `github.com`, user `git`, `IdentityFile` pointing to
  `yubikey/bot.pub`, `IdentitiesOnly yes`, `IdentityAgent SSH_AUTH_SOCK`,
  `BatchMode yes`, password and keyboard-interactive authentication disabled.

The configuration directory has mode `0700`; configuration files have mode
`0600`. No private key file or PIN is needed for normal operation.

## Schedule

The timer wakes each minute and the runner skips work before its stored deadline.
Releases are checked every five minutes. Newly detected releases and newly
captured 24h/72h measurements publish immediately. Download totals and star history
are otherwise published once daily at **03:17 UTC**, only when values changed.
Timestamp-only updates never produce commits. Star collection failures reuse the
last complete star files and retry after five minutes; release and measurement
updates continue independently.

`~/.local/state/plektra-stats/pending-release-stats.json` preserves measurements
before any rendering or publication can fail. `next-run.json` tracks collection
daily deadlines and separate star-retry deadlines. A failed star request does
not mark daily totals as unfinished again. Other failures back off for five
minutes. Keep these files across service restarts. Published snapshots
win when reconciling with the public branch. The bot changes only `stats`; it
never edits README files or `main`. Statistics pushes do not match the collector
checks workflow's `main` branch filter, and the site reads the data without a
Pages rebuild.

## Checks and activation

```sh
cd ~/gits/GitHub/pkb-rocks.github.io
python3 scripts/piv_bot.py -- ssh -F ~/.config/plektra-stats/ssh_config -T git@github.com
python3 scripts/run-release-stats.py --no-push
systemd-analyze --user verify ~/.config/systemd/user/plektra-stats.service ~/.config/systemd/user/plektra-stats.timer
```

GitHub's successful `ssh -T` greeting exits with status 1 because it provides no
shell. It must name `pkb-rocks-bot`. Preview fetches the public branch via HTTPS,
writes `~/.local/state/plektra-stats/preview/`, and neither signs nor pushes.

Keep the timer disabled until publication is authorized and the workflow change
removing the old publisher is live. This avoids simultaneous writers.

```sh
systemctl --user enable --now plektra-stats.timer
systemctl --user list-timers plektra-stats.timer
journalctl --user -u plektra-stats.service -n 50
```

For an explicitly authorized manual publication:

```sh
python3 scripts/run-release-stats.py --force
```

Pause with `systemctl --user disable --now plektra-stats.timer`. User lingering is
already enabled for `user` on Fedora. Source updates are explicit Git pulls;
the collector fetches `stats` but never updates its own executable source.

Measurements are saved locally before rendering in a temporary directory. A temporary Git index creates the
signed commit without modifying the statistics worktree. The signature is checked
before pushing. Failures leave the published branch unchanged and the worktree
clean. A competing writer rejects the non-force push; the next run collects from
the new branch state. There is no force-push, destructive reset or fallback
identity. A failed push can leave a local unreferenced commit.
