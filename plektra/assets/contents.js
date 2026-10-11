const nav = document.querySelector('.toc');
const list = nav.querySelector('ol');
const links = [...nav.querySelectorAll('a')];
const items = links.map(link => {
  const number = link.querySelector('span');
  if (number) number.classList.add('contents-number');
  const label = link.textContent.replace(/^\d+/, '').trim();
  const text = document.createElement('span');
  text.className = 'contents-label';
  for (const char of label.toUpperCase()) {
    const letter = document.createElement('span');
    letter.className = 'contents-letter';
    letter.textContent = char;
    text.append(letter);
  }
  link.setAttribute('aria-label', label);
  link.replaceChildren(...(number ? [number] : []), text);
  return {link, node: link.parentElement, target: document.querySelector(link.hash), letters: [...text.children]};
});
const desktop = matchMedia('(min-width: 1280px) and (hover: hover) and (pointer: fine)');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const ruler = document.createElement('div');
ruler.className = 'contents-ruler';
ruler.setAttribute('role', 'scrollbar');
ruler.setAttribute('aria-label', 'Page position');
ruler.setAttribute('aria-controls', 'page-content');
ruler.setAttribute('aria-valuemin', '0');
ruler.setAttribute('aria-valuemax', '100');
ruler.setAttribute('tabindex', '0');
document.querySelector('main').id = 'page-content';
const ticks = [];
for (let percent = 0; percent <= 100; percent += 1) {
  const tick = document.createElement('span');
  tick.className = `tick${percent % 5 === 0 ? ' major' : ''}`;
  tick.setAttribute('aria-hidden', 'true');
  if (percent % 5 === 0) tick.innerHTML = `<span class="tick-label">${percent}</span>`;
  ruler.append(tick);
  ticks.push({tick, percent});
}
const needle = document.createElement('span');
needle.className = 'needle';
const readout = document.createElement('output');
needle.append(readout);
ruler.append(needle);
document.body.append(ruler);
let overview = false;
let dragging = false;
let queued = false;
let activeIndex = -1;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const ease = t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3)/2;
const canvas = document.createElement('canvas').getContext('2d');
function metrics(item) {
  const font = getComputedStyle(item.link);
  canvas.font = `650 27px ${font.fontFamily}`;
  let total = 0;
  const glyphs = item.letters.map(letter => {const width = canvas.measureText(letter.textContent).width; const center = total + width/2; total += width; return {center, width};});
  return {glyphs, total};
}
function update() {
  queued = false;
  const wide = desktop.matches;
  const height = innerHeight;
  const max = Math.max(0, document.documentElement.scrollHeight - height);
  const progress = max ? scrollY / max : 0;
  const line = wide ? 115 : height * .35;
  let current = -1;
  items.forEach((item, index) => {
    if (item.target && item.target.getBoundingClientRect().top <= line) current = index;
  });
  const states = items.map((item, index) => {
    const measure = metrics(item);
    const y = (item.target?.getBoundingClientRect().top ?? 84) + 12;
    const queueY = height - 30 - (items.length - index) * 22;
    const rideScale = 14 / 27;
    const flip = clamp((height * .38 - y) / 90, 0, 1);
    const detach = clamp((queueY + 80 - y - measure.total * rideScale) / 80, 0, 1);
    return {measure, y, queueY, rideScale, flip, detach};
  });
  if (wide) current = states.findLastIndex(state => state.flip >= .5);
  items.forEach((item, index) => {
    const active = current === index;
    if (active) item.link.setAttribute('aria-current', 'true');
    else item.link.removeAttribute('aria-current');
    item.node.hidden = false;
    if (!wide || reduced.matches) {
      item.link.style.cssText = '';
      item.letters.forEach(letter => letter.style.cssText = '');
      if (!wide) {item.node.style.transform = ''; return;}
      const y = index <= current ? 84 + index*22 : height - 28 - (items.length-index)*22;
      item.node.style.transform = `translateY(${y}px)`;
      return;
    }
    item.node.style.transform = '';
    const {measure, y, queueY, rideScale, flip, detach} = states[index];
    const queueScale = 13 / 27;
    const followingFlip = states[index + 1]?.flip ?? 0;
    const dockY = 96 + index * 22 + 30 * (1 - followingFlip);
    const dockScale = 1 - (1 - queueScale) * followingFlip;
    const horizontal = (glyph, baseline, scale) => ({x: innerWidth - 60 - (measure.total - glyph.center) * scale, y: baseline, angle: 0, scale});
    const vertical = (glyph, baseline) => ({x: innerWidth - 24, y: baseline + (measure.total - glyph.center)*rideScale, angle: -90, scale: rideScale});
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    item.letters.forEach((letter, letterIndex) => {
      const glyph = measure.glyphs[letterIndex];
      let from, to, phase;
      if (flip > 0) {
        from = vertical(glyph, Math.max(y, dockY));
        to = horizontal(glyph, dockY, dockScale);
        phase = flip;
      } else {
        from = horizontal(glyph, queueY, queueScale);
        to = vertical(glyph, y);
        phase = detach;
      }
      const stagger = .045;
      const order = item.letters.length - 1 - letterIndex;
      const t = ease(clamp(phase*(1 + (item.letters.length-1)*stagger) - order*stagger, 0, 1));
      const bend = flip > 0 ? 0 : -60 * Math.sin(Math.PI*t);
      const x = from.x + (to.x-from.x)*t + bend;
      const letterY = from.y + (to.y-from.y)*t;
      const angle = from.angle + (to.angle-from.angle)*t;
      const scale = from.scale + (to.scale-from.scale)*t;
      letter.style.cssText = `position:fixed;left:0;top:0;font-size:27px;line-height:1;pointer-events:none;transform:translate3d(${x}px,${letterY}px,0) translate(-50%,-50%) rotate(${angle}deg) scale(${scale});color:${active ? 'var(--text)' : 'var(--muted)'};`;
      const radians = angle*Math.PI/180;
      const halfX = (Math.abs(Math.cos(radians))*glyph.width + Math.abs(Math.sin(radians))*27)*scale/2;
      const halfY = (Math.abs(Math.sin(radians))*glyph.width + Math.abs(Math.cos(radians))*27)*scale/2;
      minX = Math.min(minX, x-halfX); maxX = Math.max(maxX, x+halfX);
      minY = Math.min(minY, letterY-halfY); maxY = Math.max(maxY, letterY+halfY);
    });
    item.link.style.cssText = `position:fixed;left:${minX-4}px;top:${minY-4}px;width:${maxX-minX+8}px;height:${maxY-minY+8}px;padding:0;`;
  });
  if (!wide && current >= 0 && current !== activeIndex) {
    const link = items[current].link;
    // Only scroll the contents strip, without moving the page.
    const strip = list.getBoundingClientRect();
    const rect = link.getBoundingClientRect();
    list.scrollLeft += rect.left < strip.left ? rect.left - strip.left : rect.right > strip.right ? rect.right - strip.right : 0;
  }
  activeIndex = current;
  nav.querySelector('[data-toc-progress]').style.setProperty('--progress', progress.toFixed(4));
  ruler.setAttribute('aria-valuenow', Math.floor(progress * 100));
  ruler.hidden = !wide;
  ruler.tabIndex = wide ? 0 : -1;
  const usable = ruler.clientHeight - 36;
  ticks.forEach(({tick, percent}) => {
    const y = overview ? 18 + percent / 100 * usable : percent / 100 * document.documentElement.scrollHeight - scrollY + 18 + progress * usable;
    tick.style.transform = `translateY(${Math.round(y)}px)`;
  });
  needle.style.transform = `translateY(${Math.round(18 + progress * usable)}px)`;
  readout.textContent = `${Math.floor(progress * 100).toString()}%`;
}
function schedule() {
  if (!queued) { queued = true; requestAnimationFrame(update); }
}
function seek(y) {
  const rect = ruler.getBoundingClientRect();
  const fraction = clamp((y - rect.top - 18) / (rect.height - 36), 0, 1);
  window.scrollTo({top: fraction * (document.documentElement.scrollHeight - innerHeight), behavior: dragging || reduced.matches ? 'instant' : 'smooth'});
}
ruler.addEventListener('pointerenter', () => {overview = true; schedule();});
ruler.addEventListener('pointerleave', () => {if (!dragging) {overview = false; schedule();}});
ruler.addEventListener('pointerdown', event => {dragging = true; overview = true; ruler.setPointerCapture(event.pointerId); seek(event.clientY);});
ruler.addEventListener('pointermove', event => {if (dragging) seek(event.clientY);});
ruler.addEventListener('pointerup', event => {dragging = false; ruler.releasePointerCapture(event.pointerId); overview = ruler.matches(':hover'); schedule();});
ruler.addEventListener('pointercancel', () => {dragging = false; overview = false; schedule();});
ruler.addEventListener('keydown', event => {
  const actions = {ArrowDown: scrollY + innerHeight * .15, ArrowUp: scrollY - innerHeight * .15, PageDown: scrollY + innerHeight, PageUp: scrollY - innerHeight, Home: 0, End: document.documentElement.scrollHeight};
  if (!(event.key in actions)) return;
  event.preventDefault();
  window.scrollTo({top: actions[event.key], behavior: reduced.matches ? 'instant' : 'smooth'});
});
addEventListener('scroll', schedule, {passive: true});
addEventListener('resize', schedule);
desktop.addEventListener('change', schedule);
reduced.addEventListener('change', schedule);
new ResizeObserver(schedule).observe(document.body);
document.fonts.ready.then(schedule);
update();
