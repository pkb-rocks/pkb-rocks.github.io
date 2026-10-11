# PKB.rocks Pages

Organization site and Android App Links association for Plektra and Pastiera.

`/.well-known/assetlinks.json` contains the Stable and Nightly package IDs with
the certificate fingerprints from the 2026-09-05 signing ceremony. Pastiera
also retains its legacy certificate for update continuity.

## Plektra product page

`/` is the Plektra product page. Its Stable/Nightly switch changes the page
theme: Stable is light with the orange mark, Nightly is dark with the blue mark.

Permanent download links resolve the newest release through the GitHub API, so
new releases need no change here:

| Link | Target |
| --- | --- |
| `/plektra/download/stable/` | newest normal release, full APK |
| `/plektra/download/nightly/` | newest `nightly/` pre-release, full APK |
| `?variant=no-accessibility` | APK without the Clicks accessibility service |
| `?to=notes` | release page |
| `?to=checksums` | `SHA256SUMS` |

The screenshots under `plektra/assets/shots/` are generated from the Plektra
showcase slides. Render the showcase in the Plektra repository first, then run:

```sh
node tools/build-plektra-assets.mjs ../plektra
```

The custom domain is `pkb.rocks`. Its apex DNS records must point to GitHub
Pages before HTTPS and Android App Links verification can succeed.

## Release statistics

The hourly `Release download statistics` workflow reads public Plektra releases
and saves immutable 24h/72h APK download snapshots on this repository's `stats`
branch. The home page reads that JSON and its SVG charts directly; statistics
updates do not require a Pages rebuild. See [the data contract](docs/release-statistics.md).

The Plektra product page at `/` combines the device showcase, feature
chapters, Stable and Nightly download links, release download statistics, and a
separate GitHub star history. Its right-hand desktop contents navigation follows
the reading position; smaller screens use the horizontal contents strip.
Showcase assets are rebuilt with `node tools/build-plektra-assets.mjs ../plektra`.
The hourly statistics workflow updates the public `stats` branch independently
of website builds; the Plektra repository README embeds its star charts directly.

The asset builder also refreshes screenshot content versions in `index.html`, so browser previews request new images after a rebuild.

Keyboard-bar images use native transparent Debug exports when available. This retains both LED rails and their spacing without screenshot background subtraction. Bar comparison images share a light backing in the Nightly page theme so inactive LEDs remain visible. Software keyboard themes are shown vertically; slide text wraps within its own column.
