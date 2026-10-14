"""Collection deadlines, immutable pending snapshots and publication decisions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def minute(value):
    tick = value.replace(second=0, microsecond=0)
    return tick + timedelta(minutes=1) if tick < value else tick


def next_daily(now):
    target = now.astimezone(UTC).replace(hour=3, minute=17, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def plan(data, now, daily_at, star_retry=None):
    candidates = [now.replace(second=0, microsecond=0) + timedelta(minutes=5), daily_at]
    if star_retry:
        candidates.append(star_retry)
    measurement = data.get('next_measurement_at')
    if measurement:
        candidates.append(timestamp(measurement))
    return {'next_collection_at': iso(minute(min(candidates))),
            'next_daily_at': iso(daily_at),
            'next_star_retry_at': iso(star_retry) if star_retry else None}


def merge_pending(published, pending):
    """Published measurements win; unpublished local measurements survive retries."""
    if pending is None:
        return deepcopy(published)
    if any(published.get(key) != pending.get(key) for key in ('schema_version', 'repository')):
        raise ValueError('Pending statistics schema or repository does not match')
    result = deepcopy(published)
    records = {r['release_id']: r for r in result['releases']}
    for local in pending['releases']:
        remote = records.get(local['release_id'])
        if remote is None:
            records[local['release_id']] = deepcopy(local)
            continue
        if any(remote[key] != local[key] for key in ('published_at', 'initial_asset_ids')):
            raise ValueError(f'Pending release identity changed: {local["release_id"]}')
        for window in ('24h', '72h'):
            if remote['snapshots'][window] is None and local['snapshots'][window] is not None:
                remote['snapshots'][window] = deepcopy(local['snapshots'][window])
        remote['asset_changes_detected'] |= local['asset_changes_detected']
        if local.get('current', {}).get('captured_at', '') > remote.get('current', {}).get('captured_at', ''):
            remote['current'] = deepcopy(local['current'])
    result['releases'] = sorted(records.values(), key=lambda r: (r['published_at'], r['release_id']))
    return result


def download_values(data):
    records = deepcopy(data['releases'])
    for record in records:
        record.pop('first_seen_at', None)
        if record.get('current'):
            record['current'].pop('captured_at', None)
    return records


def star_values(data):
    return {key: data.get(key) for key in ('count', 'weeks')}


def publication_reasons(published, collected, daily_due, stars_before, stars_after, stars_due=False):
    old = {r['release_id']: r for r in published['releases']}
    reasons = []
    if 'next_publication_at' not in published:
        reasons.append('publisher setup')
    if any(r['release_id'] not in old for r in collected['releases']):
        reasons.append('new release')
    if any(snapshot is not None and (r['release_id'] not in old or
               old[r['release_id']]['snapshots'][window] is None)
           for r in collected['releases'] for window, snapshot in r['snapshots'].items()):
        reasons.append('24/72h measurement')
    if daily_due and (download_values(published) != download_values(collected)
                      or star_values(stars_before) != star_values(stars_after)):
        reasons.append('daily totals and stars')
    elif stars_due and star_values(stars_before) != star_values(stars_after):
        reasons.append('star history retry')
    return reasons
