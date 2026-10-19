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
| `/plektra/download/stable/` | newest normal release, recommended APK without the Clicks accessibility service |
| `/plektra/download/nightly/` | newest `nightly/` pre-release, full APK |
| `?variant=full` | full APK with Clicks launcher-button remapping |
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

Fedora publishes YubiKey-signed bot updates with download snapshots, current APK download counts and star
history on the `stats` branch. The website reads those files directly; data
updates do not require rebuilding Pages. GitHub Actions tests the collector
scripts and no longer writes statistics. See [the data contract](docs/release-statistics.md)
and [Fedora operation](ops/fedora/README.md).

The product page uses its mobile contents strip and desktop side navigation.
Open Collective is linked prominently in the header. Screenshot versions in
`index.html` refresh when assets are rebuilt, so browsers request the updated
images. The Plektra README uses visual-only exports with its own headings.
