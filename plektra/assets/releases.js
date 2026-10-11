// Release lookup for the Plektra pages.
// Stable: newest normal GitHub release. Nightly: newest pre-release on the nightly/ tag line.
// Release assets are named Plektra-VERSION-full.apk and Plektra-VERSION-no-accessibility.apk.

export const REPO = "pkb-rocks/plektra";
export const RELEASES_URL = `https://github.com/${REPO}/releases`;

export const CHANNELS = {
  stable: {
    name: "Plektra",
    fallbackUrl: `${RELEASES_URL}/latest`,
    matches: (release) => !release.prerelease,
  },
  nightly: {
    name: "Plektra Nightly",
    fallbackUrl: RELEASES_URL,
    matches: (release) => release.prerelease && release.tag_name.startsWith("nightly/"),
  },
};

export const VARIANTS = {
  full: "-full.apk",
  "no-accessibility": "-no-accessibility.apk",
};

let cached;

export function fetchReleases() {
  cached ??= fetch(`https://api.github.com/repos/${REPO}/releases?per_page=50`, {
    headers: { Accept: "application/vnd.github+json" },
  }).then((response) => {
    if (!response.ok) throw new Error(`GitHub API returned ${response.status}`);
    return response.json();
  });
  return cached;
}

export async function latestRelease(channel) {
  const releases = await fetchReleases();
  return releases.find((release) => !release.draft && CHANNELS[channel].matches(release)) ?? null;
}

export function findAsset(release, variant = "full") {
  const suffix = VARIANTS[variant] ?? VARIANTS.full;
  return release.assets.find((asset) => asset.name.endsWith(suffix)) ?? null;
}

export function findChecksums(release) {
  return release.assets.find((asset) => asset.name === "SHA256SUMS") ?? null;
}

export function versionOf(release) {
  return release.tag_name.replace(/^nightly\//, "").replace(/^v/, "");
}

export function formatDate(iso) {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}
