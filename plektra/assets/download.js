// Permanent download links: /plektra/download/<channel>/ redirects to the newest release.
//   ?variant=no-accessibility  APK without the Clicks accessibility service
//   ?to=notes                  release page with notes
//   ?to=checksums              SHA256SUMS
import { CHANNELS, findAsset, findChecksums, latestRelease } from "./releases.js";

const channel = document.documentElement.dataset.channel;
const params = new URLSearchParams(location.search);
const target = params.get("to") ?? "apk";
const variant = params.get("variant") ?? "full";
const status = document.querySelector("[data-status]");
const fallback = document.querySelector("[data-fallback]");

function go(url) {
  fallback.href = url;
  location.replace(url);
}

try {
  const release = await latestRelease(channel);
  if (!release) {
    status.textContent = `No ${CHANNELS[channel].name} release is published yet.`;
    fallback.textContent = "Back to the Plektra downloads";
    fallback.href = "/plektra/#download";
  } else if (target === "notes") {
    go(release.html_url);
  } else if (target === "checksums") {
    go(findChecksums(release)?.browser_download_url ?? release.html_url);
  } else {
    go(findAsset(release, variant)?.browser_download_url ?? release.html_url);
  }
} catch {
  go(CHANNELS[channel].fallbackUrl);
}
