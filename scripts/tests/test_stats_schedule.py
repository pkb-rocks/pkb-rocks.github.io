"""Publication cadence and durable measurements across collection retries."""
from copy import deepcopy
from datetime import timedelta
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parents[1]))
from stats_schedule import merge_pending, publication_reasons, next_daily, plan, timestamp
from test_release_stats import stats, START, empty, release


class ScheduleTests(unittest.TestCase):
    def published(self, age=20):
        data=stats.update(empty(),[release(10)],START+timedelta(hours=age))
        data['next_publication_at']='2026-10-03T03:17:00Z'
        return data

    def test_new_release_publishes_before_daily_deadline(self):
        old=self.published()
        new=release(0);new['id']=2;new['tag_name']='nightly/new'
        new['published_at']=stats.iso(START+timedelta(hours=20))
        collected=stats.update(old,[release(20),new],START+timedelta(hours=20,minutes=5))
        self.assertEqual(['new release'],publication_reasons(old,collected,False,{},{}))

    def test_download_totals_wait_for_daily_run_and_timestamps_do_not_publish(self):
        old=self.published()
        changed=stats.update(old,[release(20)],START+timedelta(hours=20,minutes=5))
        self.assertEqual([],publication_reasons(old,changed,False,{},{}))
        self.assertEqual(['daily totals and stars'],publication_reasons(old,changed,True,{},{}))
        unchanged=stats.update(old,[release(10)],START+timedelta(hours=20,minutes=5))
        self.assertEqual([],publication_reasons(old,unchanged,True,{'count':19,'updated_at':'old'},{'count':19,'updated_at':'new'}))
        self.assertEqual(['daily totals and stars'],publication_reasons(old,unchanged,True,{'count':19},{'count':20}))

    def test_measurement_publishes_immediately_and_survives_failed_push(self):
        published=self.published()
        measured=stats.update(published,[release(100)],START+timedelta(hours=24))
        snapshot=deepcopy(measured['releases'][0]['snapshots']['24h'])
        # A failed push leaves this measurement local; remote remains unchanged.
        seed=merge_pending(published,measured)
        retry=stats.update(seed,[release(150)],START+timedelta(hours=24,minutes=5))
        self.assertEqual(snapshot,retry['releases'][0]['snapshots']['24h'])
        self.assertEqual(['24/72h measurement'],publication_reasons(published,retry,False,{},{}))
        remote=deepcopy(retry)
        self.assertEqual([],publication_reasons(remote,retry,False,{},{}))

    def test_published_measurements_are_authoritative_over_stale_pending_data(self):
        remote=stats.update(self.published(),[release(100)],START+timedelta(hours=24))
        pending=deepcopy(remote)
        pending['releases'][0]['snapshots']['24h']['assets'][0]['download_count']=999
        self.assertEqual(remote['releases'][0]['snapshots'],merge_pending(remote,pending)['releases'][0]['snapshots'])
        self.assertEqual(pending['releases'][0]['snapshots']['24h']['assets'][0]['download_count'],999)

    def test_release_anchor_conflict_cannot_merge_unrelated_measurements(self):
        remote=self.published();pending=deepcopy(remote)
        pending['releases'][0]['initial_asset_ids']=[123]
        with self.assertRaisesRegex(ValueError,'identity changed'):
            merge_pending(remote,pending)

    def test_pending_new_release_is_not_lost_before_publication(self):
        remote=empty();pending=self.published()
        merged=merge_pending(remote,pending)
        self.assertEqual(pending['releases'],merged['releases'])
        self.assertEqual([],remote['releases'])

    def test_polling_never_delays_a_known_measurement(self):
        now=timestamp('2026-10-15T02:58:23Z')
        measurement='2026-10-15T03:01:05Z'
        result=plan({'next_measurement_at':measurement},now,next_daily(now))
        self.assertEqual('2026-10-15T03:02:00Z',result['next_collection_at'])
        self.assertEqual('2026-10-15T03:17:00Z',result['next_daily_at'])
        result=plan({},now,next_daily(now))
        self.assertEqual('2026-10-15T03:03:00Z',result['next_collection_at'])
        self.assertEqual('2026-10-16T03:17:00Z',stats.iso(next_daily(timestamp('2026-10-15T03:17:00Z'))))
