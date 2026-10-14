"""Regression checks for timing, asset continuity and API persistence."""

from copy import deepcopy
from datetime import timedelta
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("release_stats", Path(__file__).parents[1] / "collect-release-stats.py")
stats = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stats)
START = stats.timestamp("2026-10-01T12:00:00Z")


def release(count=100, asset_id=10):
    return {"id": 1, "tag_name": "nightly/v26.10-nightly.01.120000Z",
            "published_at": stats.iso(START), "draft": False, "prerelease": True,
            "assets": [{"id": asset_id, "name": "Plektra-full.apk", "state": "uploaded",
                        "created_at": stats.iso(START), "download_count": count},
                       {"id": 99, "name": "Plektra-full.apk.sha256", "state": "uploaded",
                        "created_at": stats.iso(START), "download_count": 500}]}


def empty():
    return {"schema_version": 1, "repository": "pkb-rocks/plektra",
            "capture_tolerance_seconds": 7200, "releases": []}


class SnapshotTests(unittest.TestCase):
    def capture(self, state, hours, data=None):
        return stats.update(state, [data or release()], START + timedelta(hours=hours))

    def test_two_snapshots_exclude_checksums_and_never_overwrite(self):
        state = self.capture(empty(), 23)
        self.assertIsNone(state["releases"][0]["snapshots"]["24h"])
        state = self.capture(state, 24, release(100))
        first = deepcopy(state["releases"][0]["snapshots"]["24h"])
        state = self.capture(state, 72, release(150))
        snapshots = state["releases"][0]["snapshots"]
        self.assertEqual(first, snapshots["24h"])
        self.assertEqual([100, 150], [snapshots[k]["assets"][0]["download_count"] for k in ("24h", "72h")])
        self.assertEqual(1, len(snapshots["24h"]["assets"]))
        updated = self.capture(state, 100, release(900))
        self.assertEqual(state["releases"][0]["snapshots"], updated["releases"][0]["snapshots"])
        self.assertEqual(900, updated["releases"][0]["current"]["assets"][0]["download_count"])
        self.assertIsNone(updated["next_measurement_at"])

    def test_next_deadline_and_current_counts_are_independent_of_fixed_snapshots(self):
        state = self.capture(empty(), 23.9)
        self.assertEqual(stats.iso(START + timedelta(hours=23, minutes=59)), state["next_collection_at"])
        state = self.capture(state, 24, release(100))
        self.assertEqual(stats.iso(START + timedelta(hours=72)), state["next_measurement_at"])
        state = self.capture(state, 30, release(140))
        self.assertEqual(100, state["releases"][0]["snapshots"]["24h"]["assets"][0]["download_count"])
        self.assertEqual(140, state["releases"][0]["current"]["assets"][0]["download_count"])
        self.assertEqual(stats.iso(START + timedelta(hours=30, minutes=5)), state["next_collection_at"])

    def test_collector_reuses_embedded_assets_for_public_api_budget(self):
        with patch.object(stats, "pages", return_value=[release(123)]) as api:
            state = stats.collect("pkb-rocks/plektra", empty())
        self.assertEqual(1, api.call_count)
        self.assertEqual(123, state["releases"][0]["current"]["assets"][0]["download_count"])

    def test_tolerance_boundary_and_missed_history(self):
        self.assertEqual("captured", self.capture(empty(), 26)["releases"][0]["snapshots"]["24h"]["status"])
        state = self.capture(empty(), 26 + 1 / 3600)
        self.assertEqual("late", state["releases"][0]["snapshots"]["24h"]["status"])
        state = self.capture(empty(), 100)
        self.assertEqual(["late", "late"], [v["status"] for v in state["releases"][0]["snapshots"].values()])

    def test_asset_replacement_invalidates_later_snapshot(self):
        state = self.capture(empty(), 24)
        state = self.capture(state, 72, release(30, asset_id=11))
        snapshot = state["releases"][0]["snapshots"]["72h"]
        self.assertEqual("invalid", snapshot["status"])
        self.assertIn("apk_assets_changed", snapshot["issues"])

    def test_asset_replaced_before_first_snapshot(self):
        state = self.capture(empty(), 2)
        state = self.capture(state, 24, release(asset_id=11))
        self.assertEqual("invalid", state["releases"][0]["snapshots"]["24h"]["status"])

    def test_counter_reset(self):
        state = self.capture(empty(), 24, release(100))
        state = self.capture(state, 72, release(20))
        self.assertIn("download_count_decreased", state["releases"][0]["snapshots"]["72h"]["issues"])

    def test_no_apk_is_invalid_not_zero_downloads(self):
        data = release()
        data["assets"] = data["assets"][1:]
        state = self.capture(empty(), 24, data)
        snapshot = state["releases"][0]["snapshots"]["24h"]
        self.assertEqual("invalid", snapshot["status"])
        self.assertEqual([], snapshot["assets"])

    def test_drafts_excluded_and_removed_releases_retained(self):
        data = release()
        data["draft"] = True
        self.assertEqual([], self.capture(empty(), 24, data)["releases"])
        state = self.capture(empty(), 24)
        removed = stats.update(state, [], START + timedelta(hours=72))
        self.assertEqual(state["releases"], removed["releases"])
        self.assertIsNone(removed["next_measurement_at"])

    def test_changed_publication_time_is_invalid(self):
        state = self.capture(empty(), 2)
        data = release()
        data["published_at"] = stats.iso(START + timedelta(hours=1))
        state = self.capture(state, 24, data)
        self.assertIn("publication_time_changed", state["releases"][0]["snapshots"]["24h"]["issues"])


class PersistenceTests(unittest.TestCase):
    def test_chart_stacks_increment_and_omits_late_counts(self):
        state = stats.update(empty(), [release(100)], START + timedelta(hours=24))
        state = stats.update(state, [release(150)], START + timedelta(hours=72))
        svg = ET.fromstring(stats.chart(state, "nightly"))
        rectangles = svg.findall('.//{http://www.w3.org/2000/svg}rect')
        segments = [r for r in rectangles if float(r.attrib.get('width', 0)) == 42]
        self.assertEqual(2, len(segments))
        self.assertEqual(2, float(segments[0].attrib['height']) / float(segments[1].attrib['height']))
        state['releases'][0]['snapshots']['24h']['status'] = 'late'
        svg = ET.fromstring(stats.chart(state, 'nightly'))
        segments = [r for r in svg.findall('.//{http://www.w3.org/2000/svg}rect') if float(r.attrib.get('width', 0)) == 42]
        self.assertEqual(1, len(segments))
        self.assertEqual('none', segments[0].attrib['fill'])

    def test_api_pagination_and_token_header(self):
        responses = [io.BytesIO(json.dumps([release()] * 100).encode()), io.BytesIO(b"[]")]
        with patch.object(stats, "urlopen", side_effect=responses) as api, patch.dict(stats.os.environ, {"GH_TOKEN": "test-token"}):
            self.assertEqual(100, len(stats.pages("/repos/pkb-rocks/plektra/releases")))
        self.assertIn("page=2", api.call_args_list[1].args[0].full_url)
        self.assertEqual("Bearer test-token", api.call_args_list[0].args[0].get_header("Authorization"))

    def test_cli_records_empty_check_and_api_failure_preserves_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release-stats.json"
            output.write_text(json.dumps(empty(), ensure_ascii=False, indent=2) + "\n")
            with patch.object(stats.sys, "argv", ["collector", "--output", str(output)]), patch.object(stats, "pages", return_value=[]):
                stats.main()
            self.assertIn("last_checked_at", json.loads(output.read_text()))
            original = output.read_bytes()
            with patch.object(stats.sys, "argv", ["collector", "--output", str(output)]), patch.object(stats, "pages", side_effect=OSError("API unavailable")):
                with self.assertRaises(OSError):
                    stats.main()
            self.assertEqual(original, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
