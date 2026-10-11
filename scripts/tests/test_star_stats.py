import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('star_stats', Path(__file__).parents[1] / 'collect-star-history.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StarHistoryTests(unittest.TestCase):
    def test_unsorted_weeks_produce_chronological_cumulative_counts(self):
        weeks = [
            {'week': 604800, 'days': [2, 0, 0, 0, 0, 0, 0], 'total': 2},
            {'week': 0, 'days': [1, 0, 1, 0, 0, 0, 0], 'total': 2},
        ]
        values = module.points(weeks)
        self.assertEqual(values[0], (0, 1))
        self.assertEqual(values[6], (518400, 2))
        self.assertEqual(values[7], (604800, 4))
        self.assertEqual(values[-1][1], 4)

    def test_inconsistent_totals_are_rejected(self):
        with self.assertRaises(ValueError):
            module.points([{'week': 0, 'days': [0] * 7, 'total': 1}])

    def test_future_days_are_not_shown_as_observations(self):
        self.assertEqual(module.points([{'week': 9999999999, 'days': [0] * 7, 'total': 0}]), [])

    def test_chart_distinguishes_history_from_current_count(self):
        svg = module.chart({'weeks': [{'week': 0, 'days': [1, 0, 0, 0, 0, 0, 0], 'total': 1}],
                            'count': 2, 'updated_at': '2026-10-11T00:00:00Z'})
        self.assertIn('2 stars', svg)
        self.assertIn('current repository star count is shown separately', svg)
        self.assertIn('Source: GitHub', svg)
