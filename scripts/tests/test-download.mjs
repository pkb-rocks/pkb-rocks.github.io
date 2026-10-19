import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const body = readFileSync(new URL('../../plektra/assets/download.js', import.meta.url), 'utf8').replace(/^import .*;$/m, '');
const run = new (Object.getPrototypeOf(async function(){}).constructor)('document', 'location', 'URLSearchParams', 'CHANNELS', 'findAsset', 'findChecksums', 'latestRelease', body);
async function resolve(query, release, {channel='nightly', fail=false}={}) {
  const elements = Object.fromEntries(['status','fallback','notes'].map(key=>[key,{hidden:true}]));
  const document = {documentElement:{dataset:{channel}}, querySelector:selector=>elements[selector.match(/data-(\w+)/)[1]]};
  const location = {search:query, replace(url){this.target=url;}};
  const channels = {stable:{name:'Plektra',fallbackUrl:'https://github.com/example/releases/latest'},nightly:{name:'Nightly',fallbackUrl:'https://github.com/example/releases'}};
  await run(document,location,URLSearchParams,channels,(r,variant)=>r.apks[variant],r=>r.checksums,async()=>{if(fail)throw Error('API error');return release;});
  return {elements,location};
}
const release={html_url:'https://github.com/example/releases/tag/v26.10',apks:{
  full:{name:'Plektra-26.10-full.apk',browser_download_url:'https://github.com/example/download/Plektra-26.10-full.apk'},
  'no-accessibility':{name:'Plektra-26.10-no-accessibility.apk',browser_download_url:'https://github.com/example/download/Plektra-26.10-no-accessibility.apk'}
},checksums:{browser_download_url:'https://github.com/example/download/SHA256SUMS'}};
let result=await resolve('',release);
assert.equal(result.location.target,release.apks.full.browser_download_url);
assert.equal(result.elements.fallback.textContent,'Download Plektra-26.10-full.apk');
assert.match(result.elements.status.textContent,/Download starting/);
assert.equal(result.elements.notes.href,release.html_url);
result=await resolve('',release,{channel:'stable'});
assert.equal(result.location.target,release.apks['no-accessibility'].browser_download_url);
assert.equal(result.elements.fallback.textContent,'Download Plektra-26.10-no-accessibility.apk');
result=await resolve('?variant=full',release,{channel:'stable'});
assert.equal(result.location.target,release.apks.full.browser_download_url);
result=await resolve('?variant=no-accessibility',release);
assert.equal(result.location.target,release.apks['no-accessibility'].browser_download_url);
result=await resolve('?to=notes',release);assert.equal(result.location.target,release.html_url);
result=await resolve('?to=checksums',release,{channel:'stable'});assert.equal(result.location.target,release.checksums.browser_download_url);
const fullOnly={...release,apks:{full:release.apks.full}};
result=await resolve('',fullOnly,{channel:'stable'});assert.equal(result.location.target,release.html_url);
result=await resolve('',null);assert.equal(result.elements.fallback.href,'/#download');assert.equal(result.location.target,undefined);
result=await resolve('',null,{fail:true});assert.match(result.elements.fallback.textContent,/releases/);
console.log('Stable reduced default, explicit Full, Nightly compatibility and fallbacks: OK');
