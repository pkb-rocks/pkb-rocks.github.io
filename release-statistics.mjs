const base = 'https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/';

export function measurement(snapshot) {
  if (!snapshot) return { label: 'Pending', detail: 'This snapshot has not been collected yet.' };
  const detail = `Target: ${snapshot.due_at}; captured: ${snapshot.captured_at}`;
  const count = snapshot.assets.reduce((sum, asset) => sum + asset.download_count, 0);
  if (snapshot.status === 'invalid' || snapshot.issues?.length) return {label: 'Invalid', detail};
  if (snapshot.status === 'late') return {label: `${count} (late)`, detail};
  return { label: String(count), detail };
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
    const image = document.createElement('img');
    const latest = data.last_checked_at || releases.flatMap(release => Object.values(release.snapshots))
      .filter(Boolean).map(snapshot => snapshot.captured_at).sort().at(-1) || releases.at(-1).first_seen_at;
    image.src = `${base}${channel}-downloads.svg?v=${encodeURIComponent(latest)}`;
    image.alt = `${heading.textContent} APK downloads per release after 24 and 72 hours`;
    image.width = 720;
    image.height = 400;
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
      group.append(heading, current, image, wrapper);
    } else group.append(heading, image, wrapper);
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
