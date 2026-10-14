import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const body = readFileSync(new URL('../../plektra/assets/download.js', import.meta.url), 'utf8').replace(/^import .*;$/m, '');
const run = new (Object.getPrototypeOf(async function(){}).constructor)('document', 'location', 'URLSearchParams', 'CHANNELS', 'findAsset', 'findChecksums', 'latestRelease', body);
async function resolve(query, release, fail=false) {
  const elements = Object.fromEntries(['status','fallback','notes'].map(key=>[key,{hidden:true}]));
  const document = {documentElement:{dataset:{channel:'nightly'}}, querySelector:selector=>elements[selector.match(/data-(\w+)/)[1]]};
  const location = {search:query, replace(url){this.target=url;}};
  await run(document,location,URLSearchParams,{nightly:{name:'Nightly',fallbackUrl:'https://github.com/example/releases'}},r=>r.apk,r=>r.checksums,async()=>{if(fail)throw Error('API error');return release;});
  return {elements,location};
}
const release={html_url:'https://github.com/example/releases/tag/nightly',apk:{name:'Plektra-full.apk',browser_download_url:'https://github.com/example/download/Plektra-full.apk'}};
let result=await resolve('',release);
assert.equal(result.location.target,release.apk.browser_download_url);
assert.equal(result.elements.fallback.textContent,'Download Plektra-full.apk');
assert.match(result.elements.status.textContent,/Download starting/);
assert.equal(result.elements.notes.href,release.html_url);
result=await resolve('?to=notes',release);assert.equal(result.location.target,release.html_url);
result=await resolve('',null);assert.equal(result.elements.fallback.href,'/#download');assert.equal(result.location.target,undefined);
result=await resolve('',null,true);assert.match(result.elements.fallback.textContent,/releases/);
console.log('Download destinations and visible labels: OK');
