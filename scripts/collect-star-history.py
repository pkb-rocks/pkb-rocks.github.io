#!/usr/bin/env python3
"""Render public GitHub star history for the website."""

import argparse
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen

from importlib.util import module_from_spec, spec_from_file_location

spec = spec_from_file_location('release_stats', Path(__file__).with_name('collect-release-stats.py'))
release_stats = module_from_spec(spec)
spec.loader.exec_module(release_stats)
REPOSITORY = 'pkb-rocks/plektra'


def request(path):
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10',
               'User-Agent': 'plektra-star-history'}
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    with urlopen(Request(f'https://api.github.com/repos/{REPOSITORY}/{path}', headers=headers), timeout=30) as response:
        return json.load(response)


def points(weeks):
    """Use GitHub's supplied week boundaries, without inferring the API's timezone."""
    result = []
    cumulative = 0
    for week in sorted(weeks, key=lambda item: item['week']):
        if not isinstance(week['week'], int) or len(week['days']) != 7:
            raise ValueError('Invalid star history week')
        if any(not isinstance(day, int) or day < 0 for day in week['days']):
            raise ValueError('Invalid daily star count')
        if sum(week['days']) != week['total']:
            raise ValueError('Star history totals do not match daily counts')
        for index, count in enumerate(week['days']):
            stamp = week['week'] + index * 86400
            if stamp > datetime.now(timezone.utc).timestamp():
                break
            cumulative += count
            result.append((stamp, cumulative))
    return result


def chart(data, dark=False):
    background, foreground, muted, grid, accent = (
        ('#101820', '#edf2f7', '#b9c6d3', '#334250', '#2f80ed') if dark else
        ('#f4f1e9', '#242729', '#535960', '#d3cec3', '#fc7a0f'))
    values = points(data['weeks'])
    left, right, top, bottom = 58, 696, 85, 318
    first = values[0][0] if values else 0
    last = values[-1][0] if values else 1
    maximum = max([count for _, count in values] + [1])
    maximum = max(5, ((maximum + 4) // 5) * 5)
    def x(stamp):
        return left + (stamp - first) / max(last - first, 1) * (right - left)
    def y(count):
        return bottom - count / maximum * (bottom - top)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="720" height="400" viewBox="0 0 720 400" role="img" aria-labelledby="title desc">',
             '<title id="title">Plektra GitHub star history</title>',
             '<desc id="desc">Cumulative stars from GitHub’s daily star history. The current repository star count is shown separately.</desc>',
             f'<rect width="720" height="400" fill="{background}"/>',
             f'<g font-family="system-ui,sans-serif" fill="{foreground}">',
             f'<text x="696" y="33" text-anchor="end" font-size="18">{data["count"]} stars</text>']
    for index in range(5):
        value = maximum * index / 4
        parts.extend([f'<path d="M{left} {y(value):.1f}H{right}" stroke="{grid}"/>',
                      f'<text x="{left-10}" y="{y(value)+4:.1f}" text-anchor="end" font-size="12">{value:g}</text>'])
    if values:
        path = ' '.join(f'{"M" if index == 0 else "L"}{x(stamp):.1f} {y(count):.1f}' for index, (stamp, count) in enumerate(values))
        parts.append(f'<path d="{path}" fill="none" stroke="{accent}" stroke-width="3"/>')
        for index in range(4):
            stamp = first + (last - first) * index / 3
            date = datetime.fromtimestamp(stamp, timezone.utc).strftime('%d %b %Y')
            anchor = 'start' if index == 0 else 'end' if index == 3 else 'middle'
            parts.append(f'<text x="{x(stamp):.1f}" y="345" text-anchor="{anchor}" font-size="12">{date}</text>')
    else:
        parts.append('<text x="377" y="205" text-anchor="middle">No star history available yet</text>')
    date = escape(data['updated_at'][:10])
    parts.extend([f'<text x="24" y="382" font-size="12" fill="{muted}">pkb-rocks/plektra · Updated {date} · Source: GitHub</text>', '</g></svg>'])
    return '\n'.join(parts) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    weeks = []
    for page in range(1, 101):
        batch = request(f'stargazers/history?per_page=100&page={page}')
        if not isinstance(batch, list):
            raise ValueError('Expected a list of star history weeks')
        weeks.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise ValueError('Star history pagination exceeded the API limit')
    count = request('stargazers/count')['count']
    if not isinstance(count, int) or count < 0:
        raise ValueError('Invalid current star count')
    data = {'schema_version': 1, 'repository': REPOSITORY, 'count': count,
            'weeks': sorted(weeks, key=lambda item: item['week']),
            'updated_at': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')}
    path = args.output_dir / 'star-history.json'
    if path.exists():
        previous = json.loads(path.read_text())
        if all(previous.get(key) == data[key] for key in ('schema_version', 'repository', 'count', 'weeks')):
            data['updated_at'] = previous['updated_at']
    # Validate and render before replacing any output.
    light, dark = chart(data), chart(data, dark=True)
    release_stats.write_changed(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    release_stats.write_changed(args.output_dir / 'star-history.svg', light)
    release_stats.write_changed(args.output_dir / 'star-history-dark.svg', dark)
    print(f'{count} stars; {len(weeks)} weeks of public history')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Star history failed: {error}', file=sys.stderr)
        sys.exit(1)
