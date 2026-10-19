// Permanent channel links resolve to GitHub APKs, release notes or checksums.
import { CHANNELS, findAsset, findChecksums, latestRelease } from "./releases.js";

const channel = document.documentElement.dataset.channel;
const params = new URLSearchParams(location.search);
const target = params.get("to") ?? "apk";
const variant = params.get("variant") ?? (channel === "stable" ? "no-accessibility" : "full");
const status = document.querySelector("[data-status]");
const fallback = document.querySelector("[data-fallback]");
const notes = document.querySelector("[data-notes]");

function go(url, label, message) {
  fallback.href = url;
  fallback.textContent = label;
  status.textContent = message;
  location.replace(url);
}

try {
  const release = await latestRelease(channel);
  if (!release) {
    status.textContent = `No ${CHANNELS[channel].name} release is published yet.`;
    fallback.textContent = "Back to the Plektra downloads";
    fallback.href = "/#download";
  } else {
    notes.href = release.html_url;
    notes.hidden = false;
    if (target === "notes") {
      go(release.html_url, "Open release notes on GitHub", "Opening the release notes…");
    } else if (target === "checksums") {
      const checksums = findChecksums(release);
      go(checksums?.browser_download_url ?? release.html_url,
        checksums ? "Download SHA256SUMS" : "Open the release on GitHub",
        checksums ? "Checksum download starting…" : "Opening the release on GitHub…");
    } else {
      const apk = findAsset(release, variant);
      go(apk?.browser_download_url ?? release.html_url,
        apk ? `Download ${apk.name}` : "Open the release on GitHub",
        apk ? "Download starting… If it does not start, use the APK link below." : "Opening the release on GitHub…");
    }
  }
} catch {
  go(CHANNELS[channel].fallbackUrl, "Open releases on GitHub", "The latest build could not be resolved. Opening GitHub releases…");
}
