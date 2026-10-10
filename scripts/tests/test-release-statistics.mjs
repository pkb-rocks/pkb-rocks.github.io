import assert from 'node:assert/strict';
import { measurement } from '../../release-statistics.mjs';

assert.equal(measurement(null).label, 'Pending');
for (const status of ['late', 'invalid']) {
  assert.equal(measurement({ status, assets: [{ download_count: 999 }] }).label,
    status === 'late' ? 'Late' : 'Invalid');
}
assert.equal(measurement({ status: 'captured', assets: [{ download_count: 100 }, { download_count: 12 }] }).label, '112');
assert.equal(measurement({ status: 'captured', assets: [{ download_count: 0 }] }).label, '0');
console.log('Website snapshot states: OK');
