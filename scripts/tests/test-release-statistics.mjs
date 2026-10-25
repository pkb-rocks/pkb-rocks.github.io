import assert from 'node:assert/strict';
import { measurement, statisticsStatus, chartMeasurement } from '../../release-statistics.mjs';

assert.equal(measurement(null).label, 'Pending');
for (const status of ['late', 'invalid']) {
  assert.equal(measurement({ status, assets: [{ download_count: 999 }] }).label,
    status === 'late' ? '999 (late)' : 'Invalid');
}
assert.equal(measurement({ status: 'captured', assets: [{ download_count: 100 }, { download_count: 12 }] }).label, '112');
assert.equal(measurement({ status: 'captured', assets: [{ download_count: 0 }] }).label, '0');
console.log('Website snapshot states: OK');

const schedule = {releases: [], last_checked_at: '2026-10-14T12:00:00Z', next_publication_at: '2026-10-15T03:17:00Z'};
assert.match(statisticsStatus(schedule,new Date('2026-10-14T20:00:00Z')), /Next update planned:/);
assert.match(statisticsStatus(schedule,new Date('2026-10-16T20:00:00Z')), /daily at 03:17 UTC/);
assert.doesNotMatch(statisticsStatus(schedule,new Date('2026-10-16T20:00:00Z')), /Next update planned:/);

const release = {published_at: '2026-10-01T00:00:00Z', snapshots: {}};
assert.deepEqual(chartMeasurement(release, '24h'), {state: 'pending', count: null, detail: 'Pending'});
release.snapshots['24h'] = {status: 'late', captured_at: '2026-10-02T06:00:00Z', assets: [{download_count: 25}]};
assert.deepEqual(chartMeasurement(release, '24h'), {state: 'late', count: 25, detail: 'Measured at 30.0 h · late'});
release.snapshots['24h'].issues = ['asset_changed'];
assert.equal(chartMeasurement(release, '24h').count, null);
release.snapshots['24h'] = {status: 'captured', captured_at: '2026-10-02T00:00:00Z', assets: [{download_count: 0}]};
assert.equal(chartMeasurement(release, '24h').count, 0);
