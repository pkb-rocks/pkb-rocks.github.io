#!/usr/bin/env python3
"""Collect public statistics on Fedora and publish YubiKey-signed bot commits to stats."""

import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile

from piv_bot import bot_agent
from stats_schedule import timestamp, iso, next_daily, plan, merge_pending, publication_reasons
from importlib.util import module_from_spec, spec_from_file_location

spec = spec_from_file_location("release_collector", Path(__file__).with_name("collect-release-stats.py"))
release_collector = module_from_spec(spec)
spec.loader.exec_module(release_collector)

MESSAGE = ('chore(stats): refresh download counts and star history\n\n'
           'Automated statistics update by the PKB.rocks Bot.\n'
           'Cryptographic verification records origin and integrity; '
           'no individual approval is expressed.')
PUBLIC_REPO = 'https://github.com/pkb-rocks/pkb-rocks.github.io.git'

FILES = ('release-stats.json', 'nightly-downloads.svg', 'stable-downloads.svg',
         'star-history.json', 'star-history.svg', 'star-history-dark.svg')


def run(*args, cwd=None, capture=False, env=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None, env=env).stdout


def git(repo, *args, capture=False, env=None):
    return run('git', '-C', str(repo), *args, capture=capture, env=env)


def due(marker, now):
    if not marker.exists():
        return True
    data = json.loads(marker.read_text())
    return now >= datetime.fromisoformat(data['next_collection_at'].replace('Z', '+00:00'))


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def publish(tree, stage, config, env):
    # A temporary index keeps both source and stats worktrees unchanged on failure.
    env = dict(env, GIT_INDEX_FILE=str(stage / 'index'))
    git(tree, 'read-tree', 'HEAD', env=env)
    git(tree, f'--work-tree={stage}', 'add', '--', *FILES, env=env)
    new_tree = git(tree, 'write-tree', capture=True, env=env).strip()
    if new_tree == git(tree, 'rev-parse', 'HEAD^{tree}', capture=True).strip():
        return
    options = ('-c', 'gpg.format=ssh', '-c', 'gpg.ssh.program=ssh-keygen',
               '-c', f'user.signingkey={config["public_key"]}',
               '-c', f'gpg.ssh.allowedSignersFile={config["allowed_signers"]}')
    commit = git(tree, *options, 'commit-tree', '-S', new_tree, '-p', 'HEAD',
                 '-m', MESSAGE, capture=True, env=env).strip()
    git(tree, *options, 'verify-commit', commit, env=env)
    # A competing update rejects this push. No force and no reuse of stale snapshots.
    git(tree, 'push', 'origin', f'{commit}:refs/heads/stats', env=env)
    print(f'Published YubiKey-signed bot statistics: {commit}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--state-dir', type=Path,
                        default=Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'plektra-stats')
    parser.add_argument('--bot-config', type=Path,
                        default=Path.home() / '.config/plektra-stats/bot.json')
    parser.add_argument('--force', action='store_true', help='Collect even before the next planned run')
    parser.add_argument('--no-push', action='store_true', help='Collect into preview/ without committing or pushing')
    args = parser.parse_args()
    repo, state = args.repo.resolve(), args.state_dir.expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / 'collector.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another collection is running.')
            return
        marker = state / 'next-run.json'
        if not args.force and not args.no_push and not due(marker, datetime.now(timezone.utc)):
            return
        try:
            execute(args, repo, state, marker)
        except Exception:
            if not args.no_push:
                retry = read_json(marker, {})
                retry['next_collection_at'] = iso(datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=5))
                save_json(marker, retry)
            raise


def execute(args, repo, state, marker):
    # Release polling is public/read-only and does not start an agent or GitHub CI.
    git(repo, 'fetch', PUBLIC_REPO, 'refs/heads/stats:refs/remotes/origin/stats')
    tree = state / 'stats'
    if not tree.exists():
        git(repo, 'worktree', 'add', '--detach', str(tree), 'refs/remotes/origin/stats')
    if git(tree, 'status', '--porcelain', capture=True).strip():
        raise RuntimeError('Statistics worktree contains uncommitted changes; leaving it untouched.')
    git(tree, 'merge', '--ff-only', 'refs/remotes/origin/stats')
    published = read_json(tree / 'release-stats.json')
    if published is None:
        raise RuntimeError('The stats branch has no release-stats.json.')
    pending_path = state / 'pending-release-stats.json'
    seed = merge_pending(published, read_json(pending_path))
    collected = release_collector.collect(published['repository'], seed)
    # Persist measurements before chart rendering, star API calls, signing or pushing.
    if not args.no_push:
        save_json(pending_path, collected)
    now = timestamp(collected['last_checked_at'])
    previous_schedule = read_json(marker, {})
    daily_due = not previous_schedule.get('next_daily_at') or now >= timestamp(previous_schedule['next_daily_at'])
    daily_at = next_daily(now) if daily_due else timestamp(previous_schedule['next_daily_at'])
    retry_value = previous_schedule.get('next_star_retry_at')
    star_retry = timestamp(retry_value) if retry_value else None
    stars_due = daily_due or (star_retry is not None and now >= star_retry)
    stars_before = read_json(tree / 'star-history.json', {})
    with tempfile.TemporaryDirectory(prefix='collect-', dir=state) as temporary:
        stage = Path(temporary)
        for name in FILES:
            if (tree / name).exists():
                shutil.copyfile(tree / name, stage / name)
        for channel in ('nightly', 'stable'):
            (stage / f'{channel}-downloads.svg').write_text(release_collector.chart(collected, channel))
        if stars_due or not all((stage / name).exists() for name in FILES[3:]):
            with tempfile.TemporaryDirectory(prefix='stars-', dir=state) as star_temporary:
                star_stage = Path(star_temporary)
                for name in FILES[3:]:
                    if (stage / name).exists():
                        shutil.copyfile(stage / name, star_stage / name)
                try:
                    run('python3', str(repo / 'scripts/collect-star-history.py'), '--output-dir', str(star_stage))
                except subprocess.CalledProcessError:
                    if not all((stage / name).exists() for name in FILES[3:]):
                        raise
                    print('Star collection failed; retaining previous data and retrying in five minutes.', file=sys.stderr)
                    star_retry = now.replace(second=0, microsecond=0) + timedelta(minutes=5)
                else:
                    star_retry = None
                    for name in FILES[3:]:
                        shutil.copyfile(star_stage / name, stage / name)
        schedule = plan(collected, now, daily_at, star_retry)
        collected['next_collection_at'] = schedule['next_collection_at']
        measurement = collected.get('next_measurement_at')
        collected['next_publication_at'] = iso(min([daily_at] + ([timestamp(measurement)] if measurement else []) + ([star_retry] if star_retry else [])))
        save_json(stage / 'release-stats.json', collected)
        stars_after = read_json(stage / 'star-history.json', {})
        reasons = publication_reasons(published, collected, daily_due, stars_before, stars_after, stars_due)
        if args.no_push:
            preview = state / 'preview'
            preview.mkdir(exist_ok=True)
            for name in FILES:
                shutil.copyfile(stage / name, preview / name)
            print(f'Preview saved to {preview}; publication reasons: {reasons or "none"}; no commit or push.')
            return
        if reasons:
            print('Publishing: ' + ', '.join(reasons))
            with bot_agent(args.bot_config.expanduser().resolve(), state) as (config, env):
                publish(tree, stage, config, env)
        else:
            print('No publication: no new release or measurement; daily values unchanged or not due.')
    # Successful runs advance their deadlines; failures retain unfinished daily work.
    save_json(marker, schedule)


if __name__ == '__main__':
    main()
