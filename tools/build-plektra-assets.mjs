#!/usr/bin/env node
// Builds the web assets for the Plektra home page from the Plektra showcase.
//
// Source: the rendered slide SVGs in the Plektra repository
// (docs/showcase/exports/stable/landscape/*.svg, created by `npm run render`).
// Each slide is reduced to its visual area: headline, body copy, brand row and
// footer are removed, the background becomes transparent, and the remaining
// labels are recoloured per page theme. The page sets its own text in HTML.
//
// Usage: node tools/build-plektra-assets.mjs [path-to-plektra-repo]
// Requires rsvg-convert (librsvg) and cwebp.

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const plektraRepo = resolve(process.argv[2] ?? new URL("../../plektra", import.meta.url).pathname);
const pagesRoot = resolve(new URL("..", import.meta.url).pathname);
const slidesDir = join(plektraRepo, "docs/showcase/exports/stable/landscape");
const brandingDir = join(plektraRepo, "docs/branding");
const outDir = join(pagesRoot, "plektra/assets");

// Shared crop for every slide visual. It covers the union of all visual areas
// (x 794..1842, y 148..938) with a small margin, so every image has one ratio.
const VIEW = { x: 770, y: 130, width: 1100, height: 830 };
const RENDER_WIDTH = 1320;
const WEBP_QUALITY = "82";

const LABEL_COLOURS = ["#555A60", "#565B60"];
const THEMES = {
  stable: { label: "#4E535A" },
  nightly: { label: "#B9C6D3" },
};

function attrs(source) {
  return Object.fromEntries([...source.matchAll(/([\w:-]+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
}

function isVisual(tag, a) {
  if (tag === "rect") return false; // page background and accent rule
  return Number(a.x) >= 700 && Number(a.y) <= 980;
}

function visualSvg(svg, theme) {
  let body = svg
    .replace(/^<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "")
    .replace(/<(rect|image)\b([^>]*)\/>/g, (whole, tag, a) => (isVisual(tag, attrs(a)) ? whole : ""))
    .replace(/<text\b([^>]*)>[^<]*<\/text>/g, (whole, a) => (isVisual("text", attrs(a)) ? whole : ""));
  for (const colour of LABEL_COLOURS) body = body.replaceAll(`fill="${colour}"`, `fill="${THEMES[theme].label}"`);
  // Native dark LED strokes need a light surface after their capture background is removed.
  if (theme === "nightly") {
    body = body.replace(/(<text\b[^>]*>LED strip<\/text>)(<image\b([^>]*)\/>)/, (_, label, image, source) => {
      const a = attrs(source);
      return `${label}<rect x="${a.x}" y="${a.y}" width="${a.width}" height="${a.height}" fill="#CFDDE7"/>${image}`;
    });
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${VIEW.width}" height="${VIEW.height}" viewBox="${VIEW.x} ${VIEW.y} ${VIEW.width} ${VIEW.height}">${body}</svg>`;
}

const work = join(tmpdir(), `plektra-web-assets-${process.pid}`);
mkdirSync(work, { recursive: true });

const slides = readdirSync(slidesDir).filter((f) => f.endsWith(".svg")).sort();
if (slides.length === 0) throw new Error(`No slide SVGs in ${slidesDir}. Run the showcase render first.`);

for (const theme of Object.keys(THEMES)) {
  const target = join(outDir, "shots", theme);
  rmSync(target, { recursive: true, force: true });
  mkdirSync(target, { recursive: true });
  for (const file of slides) {
    const id = file.replace(/\.svg$/, "");
    const svgPath = join(work, `${theme}-${id}.svg`);
    const pngPath = join(work, `${theme}-${id}.png`);
    writeFileSync(svgPath, visualSvg(readFileSync(join(slidesDir, file), "utf8"), theme));
    execFileSync("rsvg-convert", ["-w", String(RENDER_WIDTH), "-o", pngPath, svgPath]);
    execFileSync("cwebp", ["-quiet", "-q", WEBP_QUALITY, "-alpha_q", "90", pngPath, "-o", join(target, `${id}.webp`)]);
  }
  console.log(`${theme}: ${slides.length} images`);
}

// Use image content versions so previews request regenerated screenshots.
const pagePath = join(pagesRoot, "index.html");
const page = readFileSync(pagePath, "utf8").replace(/<img\b[^>]*data-shot="([^"]+)"[^>]*>/g, (tag, id) => {
  const hash = createHash("sha256");
  for (const theme of Object.keys(THEMES)) hash.update(readFileSync(join(outDir, "shots", theme, `${id}.webp`)));
  const version = hash.digest("hex").slice(0, 12);
  return tag.replace(/ src="([^"]+)"/, (_, source) => ` src="${source.split("?")[0]}?v=${version}"`)
    .replace(/ data-shot-version="[^"]*"/g, "")
    .replace(/>$/, ` data-shot-version="${version}">`);
});
writeFileSync(pagePath, page);

// Logos: the open mark. The Nightly page is dark, so its key tiles use a light
// tone instead of the dark brown; the geometry stays identical to the source.
writeFileSync(join(outDir, "logo-stable.svg"), readFileSync(join(brandingDir, "plektra-open-color.svg")));
writeFileSync(
  join(outDir, "logo-nightly.svg"),
  readFileSync(join(brandingDir, "plektra-nightly-open-color.svg"), "utf8").replaceAll("#332515", "#D5E0EB"),
);

rmSync(work, { recursive: true, force: true });
console.log(`Wrote assets to ${outDir}`);
