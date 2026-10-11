const base = 'https://raw.githubusercontent.com/pkb-rocks/pkb-rocks.github.io/refs/heads/stats/';
const image = document.querySelector('[data-star-history]');
const status = document.querySelector('[data-star-status]');
let source = '/plektra/assets/';
let updatedAt;

function renderTheme() {
  const dark = document.documentElement.dataset.channel === 'nightly';
  image.src = `${source}star-history${dark ? '-dark' : ''}.svg${updatedAt ? `?v=${encodeURIComponent(updatedAt)}` : ''}`;
}

function renderStatus(data, fallback = false) {
  updatedAt = data.updated_at;
  status.textContent = `${data.count} stars · Updated ${new Date(data.updated_at).toLocaleDateString('en-GB')}${fallback ? ' · Latest update unavailable' : ''}`;
  renderTheme();
}

new MutationObserver(renderTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-channel'] });
renderTheme();
image.addEventListener('error', () => {
  if (source === '/plektra/assets/') return;
  source = '/plektra/assets/';
  loadFallback();
});

async function loadFallback() {
  try {
    const response = await fetch('/plektra/assets/star-history.json');
    if (!response.ok) throw new Error('No saved star history');
    renderStatus(await response.json(), true);
  } catch {
    status.textContent = 'Star history is currently unavailable.';
    renderTheme();
  }
}

try {
  const response = await fetch(`${base}star-history.json`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Star history request failed: ${response.status}`);
  const data = await response.json();
  if (data.schema_version !== 1 || data.repository !== 'pkb-rocks/plektra') throw new Error('Unexpected star history data');
  source = base;
  renderStatus(data);
} catch {
  await loadFallback();
}
