const base = 'https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/';

export function measurement(snapshot) {
  if (!snapshot) return { label: 'Pending', detail: 'This snapshot has not been collected yet.' };
  const detail = `Target: ${snapshot.due_at}; captured: ${snapshot.captured_at}`;
  const count = snapshot.assets.reduce((sum, asset) => sum + asset.download_count, 0);
  if (snapshot.status === 'invalid' || snapshot.issues?.length) return {label: 'Invalid', detail};
  if (snapshot.status === 'late') return {label: `${count} (late)`, detail};
  return { label: String(count), detail };
}

export function chartMeasurement(release, key) {
  const snapshot = release.snapshots[key];
  const value = measurement(snapshot);
  if (!snapshot || snapshot.status === 'invalid' || snapshot.issues?.length) {
    return { state: snapshot ? 'invalid' : 'pending', count: null, detail: value.label };
  }
  const hours = (new Date(snapshot.captured_at) - new Date(release.published_at)) / 3600000;
  return {
    state: snapshot.status,
    count: snapshot.assets.reduce((sum, asset) => sum + asset.download_count, 0),
    detail: snapshot.status === 'late' ? `Measured at ${hours.toFixed(1)} h · late` : `Measured at ${hours.toFixed(1)} h`,
  };
}

function downloadChart(releases) {
  const chart = document.createElement('div');
  chart.className = 'download-chart';
  const maximum = Math.max(1, ...releases.flatMap(release => ['24h', '72h'].map(key => chartMeasurement(release, key).count ?? 0)));
  for (const release of [...releases].reverse()) {
    const entry = document.createElement('div');
    entry.className = 'download-release';
    const link = document.createElement('a');
    link.href = `https://github.com/pkb-rocks/plektra/releases/tag/${encodeURIComponent(release.tag)}`;
    link.textContent = release.tag.replace(/^nightly\//, '').replace(/^v/, '');
    entry.append(link);
    for (const key of ['24h', '72h']) {
      const value = chartMeasurement(release, key);
      const row = document.createElement('div');
      row.className = 'download-measurement';
      row.dataset.target = key;
      row.dataset.state = value.state;
      const label = document.createElement('span');
      label.className = 'download-target';
      label.textContent = key.replace('h', ' h');
      const track = document.createElement('span');
      track.className = 'download-track';
      track.setAttribute('aria-hidden', 'true');
      if (value.count !== null) {
        const bar = document.createElement('span');
        bar.className = 'download-bar';
        bar.style.width = `${value.count / maximum * 100}%`;
        track.append(bar);
      }
      const count = document.createElement('span');
      count.className = 'download-value';
      count.textContent = value.count === null ? '—' : value.count.toLocaleString();
      const detail = document.createElement('small');
      detail.textContent = value.detail;
      count.append(detail);
      row.append(label, track, count);
      entry.append(row);
    }
    chart.append(entry);
  }
  return chart;
}

export function renderStatistics(data, container) {
  container.replaceChildren();
  for (const channel of ['nightly', 'stable']) {
    const releases = data.releases.filter(release => release.channel === channel).slice(-12);
    if (!releases.length) continue;
    const group = document.createElement('div');
    group.className = 'statistics-channel';
    const heading = document.createElement('h3');
    heading.textContent = channel === 'nightly' ? 'Nightly' : 'Stable';
    const chart = downloadChart(releases);
    const note = document.createElement('p');
    note.className = 'chart-note';
    note.textContent = 'APK downloads at each measurement. Striped bars were collected late; the actual time is shown beside each value. Missing or invalid measurements have no bar.';
    const wrapper = document.createElement('div');
    wrapper.className = 'table-scroll';
    const table = document.createElement('table');
    const caption = document.createElement('caption');
    caption.textContent = `${heading.textContent}: latest ${releases.length} releases`;
    table.append(caption);
    const head = document.createElement('thead');
    const header = document.createElement('tr');
    for (const label of ['Release', 'Current downloads', 'After 24 h', 'After 72 h']) {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.textContent = label;
      header.append(cell);
    }
    head.append(header);
    table.append(head);
    const body = document.createElement('tbody');
    for (const release of [...releases].reverse()) {
      const row = document.createElement('tr');
      const name = document.createElement('td');
      const link = document.createElement('a');
      link.href = `https://github.com/pkb-rocks/plektra/releases/tag/${encodeURIComponent(release.tag)}`;
      link.textContent = release.tag;
      name.append(link);
      row.append(name);
      const current = document.createElement('td');
      current.textContent = release.current ? String(release.current.assets.reduce((sum, asset) => sum + asset.download_count, 0)) : 'Pending';
      current.title = release.current ? `Checked: ${release.current.captured_at}` : 'Awaiting the next collection.';
      row.append(current);
      for (const key of ['24h', '72h']) {
        const cell = document.createElement('td');
        const value = measurement(release.snapshots[key]);
        if (release.snapshots[key]?.status === 'late' && !release.snapshots[key].issues?.length) {
          const hours = (new Date(release.snapshots[key].captured_at) - new Date(release.published_at)) / 3600000;
          cell.textContent = `${value.label} · after ${hours.toFixed(1)} h`;
        } else cell.textContent = value.label;
        cell.title = value.detail;
        row.append(cell);
      }
      body.append(row);
    }
    table.append(body);
    wrapper.append(table);
    const latestRelease = releases.at(-1);
    if (latestRelease.current) {
      const total = latestRelease.current.assets.reduce((sum, asset) => sum + asset.download_count, 0);
      const current = document.createElement('p');
      current.textContent = `Latest release: ${total} APK downloads.`;
      group.append(heading, current, chart, note, wrapper);
    } else group.append(heading, chart, note, wrapper);
    container.append(group);
  }
  container.hidden = false;
}

export function statisticsStatus(data, now = new Date()) {
  const snapshots = data.releases.flatMap(release => Object.values(release.snapshots)).filter(Boolean);
  const latest = snapshots.map(snapshot => snapshot.captured_at).sort().at(-1);
  const checked = data.last_checked_at || latest;
  let text = checked ? `Last checked: ${new Date(checked).toLocaleString()}.` : 'Waiting for the first collection.';
  const next = data.next_publication_at;
  if (next && new Date(next) > now) text += ` Next update planned: ${new Date(next).toLocaleString()}.`;
  else text += ' Routine updates are planned daily at 03:17 UTC.';
  if (data.next_measurement_at) text += ` Next 24/72 h measurement: ${new Date(data.next_measurement_at).toLocaleString()}.`;
  text += ' New releases are checked every five minutes.';
  return text;
}

if (typeof document !== 'undefined' && document.querySelector('#statistics-results')) {
  const status = document.querySelector('#statistics-status');
  fetch(`${base}release-stats.json`, { cache: 'no-store' })
    .then(response => {
      if (!response.ok) throw new Error(`Statistics request failed: ${response.status}`);
      return response.json();
    })
    .then(data => {
      if (data.schema_version !== 1 || data.repository !== 'pkb-rocks/plektra') {
        throw new Error('Unexpected statistics data');
      }
      renderStatistics(data, document.querySelector('#statistics-results'));
      status.textContent = statisticsStatus(data);
    })
    .catch(error => {
      status.textContent = 'Release statistics are currently unavailable. Please try again later.';
      console.error(error);
    });
}
