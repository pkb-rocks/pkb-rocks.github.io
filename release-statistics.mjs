const base = 'https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/';

export function measurement(snapshot) {
  if (!snapshot) return { label: 'Pending', detail: 'This snapshot has not been collected yet.' };
  const detail = `Target: ${snapshot.due_at}; captured: ${snapshot.captured_at}`;
  if (snapshot.status !== 'captured') {
    return { label: snapshot.status === 'late' ? 'Late' : 'Invalid', detail };
  }
  return { label: String(snapshot.assets.reduce((sum, asset) => sum + asset.download_count, 0)), detail };
}

export function renderStatistics(data, container) {
  container.replaceChildren();
  for (const channel of ['nightly', 'stable']) {
    const releases = data.releases.filter(release => release.channel === channel).slice(-12);
    if (!releases.length) continue;
    const heading = document.createElement('h3');
    heading.textContent = channel === 'nightly' ? 'Nightly' : 'Stable';
    const image = document.createElement('img');
    const latest = releases.flatMap(release => Object.values(release.snapshots))
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
    for (const label of ['Release', 'After 24 h', 'After 72 h']) {
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
      for (const key of ['24h', '72h']) {
        const cell = document.createElement('td');
        const value = measurement(release.snapshots[key]);
        cell.textContent = value.label;
        cell.title = value.detail;
        row.append(cell);
      }
      body.append(row);
    }
    table.append(body);
    wrapper.append(table);
    container.append(heading, image, wrapper);
  }
  container.hidden = false;
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
      const snapshots = data.releases.flatMap(release => Object.values(release.snapshots)).filter(Boolean);
      const latest = snapshots.map(snapshot => snapshot.captured_at).sort().at(-1);
      status.textContent = latest ? `Latest snapshot: ${new Date(latest).toLocaleString()}` : 'Waiting for the first snapshot.';
    })
    .catch(error => {
      status.textContent = 'Release statistics are currently unavailable. Please try again later.';
      console.error(error);
    });
}
