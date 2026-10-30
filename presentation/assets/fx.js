/* FX engine core: overlay root, timeline, particles, sound, inline effects, cinematics.
   Injected once into the Streamlit page by fx_layer (as a <script>), so it survives reruns.
   motion.js and destroy.js are concatenated after this file into the same scope. */
const W = window, D = document;
if (W.__ftFx && W.__ftFx.destroy) { try { W.__ftFx.destroy(); } catch (e) { /* old engine already gone */ } }
const FX = W.__ftFx = {
  version: '__VERSION__', seen: (W.__ftFx && W.__ftFx.seen) || new Set(), rects: {}, queue: [], playing: false,
  settings: {}, assets: {}, skipping: false, ghosts: {}, anims: new Set(), listeners: [],
};
const pending = new Set();
let C = { off: false, low: false, reduced: false, k: 1, cine: 'Key moments only' };

// ------------------------------------------------------------------ setup
const root = D.createElement('div');
root.id = 'ft-fx-root';
const canvas = D.createElement('canvas');
root.appendChild(canvas);
D.body.appendChild(root);
const ctx = canvas.getContext('2d');
function resize() { canvas.width = W.innerWidth; canvas.height = W.innerHeight; }
resize();
function on(target, type, fn, opts) { target.addEventListener(type, fn, opts); FX.listeners.push([target, type, fn, opts]); }
on(W, 'resize', () => { resize(); snapshot(); });
FX.destroy = () => {
  FX.dead = true;
  FX.listeners.forEach(([t, ty, fn, o]) => t.removeEventListener(ty, fn, o));
  root.remove();
};

function settings(s) {
  FX.settings = s || {};
  const rm = FX.settings.reduced_motion || 'System';
  const reduced = rm === 'On' || (rm === 'System' && W.matchMedia('(prefers-reduced-motion: reduce)').matches);
  C = {
    off: FX.settings.intensity === 'Off', low: FX.settings.intensity === 'Low', reduced,
    k: 1 / (FX.settings.speed || 1), cine: FX.settings.cinematics || 'Key moments only',
  };
  const b = D.body.classList;
  b.toggle('ft-fx-on', !C.off);
  b.toggle('ft-fx-off', C.off);
  b.toggle('ft-reduced', reduced);
  b.toggle('ft-noidle', FX.settings.idle === false);
}

// ---------------------------------------------------------------- helpers
function wait(ms) {
  if (FX.skipping || ms <= 0) return Promise.resolve();
  return new Promise((res) => {
    const done = () => { clearTimeout(t); pending.delete(done); res(); };
    const t = setTimeout(done, ms * C.k);
    pending.add(done);
  });
}
function anim(el, frames, opts) {
  if (!el || !el.animate) return Promise.resolve();
  const a = el.animate(frames, Object.assign({}, opts, { duration: (opts.duration || 300) * C.k }));
  FX.anims.add(a);
  if (FX.skipping) a.finish();
  return a.finished.catch(() => {}).then(() => FX.anims.delete(a));
}
function rnd(a, b) { return a + Math.random() * (b - a); }
function pick(list) { return list[Math.floor(Math.random() * list.length)]; }
function esc(s) { const d = D.createElement('div'); d.textContent = String(s == null ? '' : s); return d.innerHTML; }
function q(sel) { return D.querySelector(sel); }
function byId(id) { return id ? q('[data-fx-id="' + CSS.escape(id) + '"]') || q('[data-fx-target="' + CSS.escape(id) + '"]') : null; }
function toRect(r) { return r && { x: r.left !== undefined ? r.left : r.x, y: r.top !== undefined ? r.top : r.y, w: r.width !== undefined ? r.width : r.w, h: r.height !== undefined ? r.height : r.h }; }
function rectOf(el) { const r = el && el.getBoundingClientRect(); return r && r.width ? toRect(r) : null; }
function imgRect(el) { const img = el && el.querySelector('img'); return rectOf(img) || rectOf(el); }
function center(r) { return { x: r.x + r.w / 2, y: r.y + r.h / 2 }; }
function zoneRect(zone) {
  const z = q('[data-fx-zone="' + zone + '"]');
  if (!z) return null;
  return rectOf(z.querySelector('.ft-stack-cards')) || rectOf(z.querySelector('.ft-img')) || rectOf(z);
}
function app() { return q('.stApp') || D.body; }
function div(cls, html, style) {
  const d = D.createElement('div');
  d.className = cls;
  if (html) d.innerHTML = html;
  if (style) Object.assign(d.style, style);
  root.appendChild(d);
  return d;
}
function cineOn(c) { return !C.reduced && (C.cine === 'Always' || (C.cine === 'Key moments only' && c.params.key)); }

// Card element of a target, or a ghost sprite at its last known box (the card left the DOM, e.g. on K.O.).
function cardEl(target) {
  const el = byId(target);
  if (el && rectOf(el)) return el;
  if (FX.ghosts[target]) return FX.ghosts[target];
  const snap = FX.rects[target];
  if (!snap || !snap.src) return null;
  const g = div('ft-fx-sprite ft-ghost', '<img src="' + esc(snap.src) + '">', {
    left: snap.rect.x + 'px', top: snap.rect.y + 'px', width: snap.rect.w + 'px', height: snap.rect.h + 'px',
  });
  FX.ghosts[target] = g;
  return g;
}

// --------------------------------------------------------------- snapshot
function snapshot() {
  const r = {};
  D.querySelectorAll('[data-fx-id]').forEach((e) => {
    const box = imgRect(e);
    if (!box) return;
    const img = e.querySelector('img');
    const zone = e.closest('[data-fx-zone]');
    r[e.dataset.fxId] = { rect: box, src: img ? img.currentSrc || img.src : null, zone: zone ? zone.dataset.fxZone : null };
  });
  FX.rects = r;
}

// -------------------------------------------------------------- particles
const parts = [];
const actors = [];
const MAX_PARTS = 300;
// A canvas animation step: fn(dt, ctx) returns false when done. Resolves when done or skipped.
function actor(fn) {
  return new Promise((res) => {
    actors.push((dt, g) => {
      if (FX.skipping) { res(); return false; }
      const go = fn(dt, g);
      if (go === false) res();
      return go;
    });
  });
}
function emit(x, y, n, o) {
  if (C.off || C.low || C.reduced) return;
  o = o || {};
  for (let i = 0; i < n && parts.length < MAX_PARTS; i++) {
    const a = o.angle !== undefined ? o.angle + rnd(-(o.spread || Math.PI), o.spread || Math.PI) : rnd(0, Math.PI * 2);
    const sp = rnd(o.min || 2, o.max || 8);
    parts.push({
      x: x + rnd(-(o.jx || 0), o.jx || 0), y: y + rnd(-(o.jy || 0), o.jy || 0), vx: Math.cos(a) * sp, vy: Math.sin(a) * sp,
      g: o.g !== undefined ? o.g : 0.25, life: 0, max: rnd(o.life || 40, (o.life || 40) * 1.6), size: rnd(o.size || 3, (o.size || 3) * 2),
      color: Array.isArray(o.color) ? pick(o.color) : o.color || '#FFD400', shape: o.shape || 'spark', drag: o.drag || 0.98,
      rot: rnd(0, 6.3), vr: rnd(-0.3, 0.3),
    });
  }
}
let last = performance.now();
function loop(now) {
  if (FX.dead) return;
  const dt = Math.min(3, (now - last) / 16.67) / C.k;
  last = now;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (let i = actors.length - 1; i >= 0; i--) {
    if (actors[i](dt, ctx) === false) actors.splice(i, 1);
  }
  for (let i = parts.length - 1; i >= 0; i--) {
    const p = parts[i];
    p.life += dt;
    if (p.life > p.max) { parts.splice(i, 1); continue; }
    p.vx *= Math.pow(p.drag, dt); p.vy = p.vy * Math.pow(p.drag, dt) + p.g * dt;
    p.x += p.vx * dt; p.y += p.vy * dt; p.rot += p.vr * dt;
    const a = 1 - p.life / p.max;
    ctx.globalAlpha = Math.max(0, a);
    ctx.fillStyle = p.color;
    if (p.shape === 'spark') {
      ctx.strokeStyle = p.color; ctx.lineWidth = p.size * 0.6;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(p.x - p.vx * 2, p.y - p.vy * 2); ctx.stroke();
    } else if (p.shape === 'bubble') {
      ctx.strokeStyle = p.color; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(p.x, p.y, p.size * (1.2 - a * 0.4), 0, 6.3); ctx.stroke();
    } else if (p.shape === 'confetti' || p.shape === 'debris') {
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.scale(Math.cos(p.rot * 2), 1);
      ctx.fillRect(-p.size, -p.size / 2, p.size * 2, p.size); ctx.restore();
    } else {
      ctx.beginPath(); ctx.arc(p.x, p.y, p.size * a, 0, 6.3); ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
  W.requestAnimationFrame(loop);
}
W.requestAnimationFrame(loop);

// ------------------------------------------------------------------- sound
let AC = null;
function ac() {
  if (!AC) { const A = W.AudioContext || W.webkitAudioContext; AC = A ? new A() : null; }
  return AC;
}
function noise(a, dur, freq, type, vol, t0) {
  const len = Math.floor(a.sampleRate * dur);
  const buf = a.createBuffer(1, len, a.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2);
  const src = a.createBufferSource(); src.buffer = buf;
  const f = a.createBiquadFilter(); f.type = type || 'lowpass'; f.frequency.value = freq;
  const g = a.createGain(); g.gain.value = vol;
  src.connect(f).connect(g).connect(a.destination);
  src.start(t0);
}
function tone(a, type, f0, f1, dur, vol, t0) {
  const o = a.createOscillator(); o.type = type;
  o.frequency.setValueAtTime(f0, t0); o.frequency.exponentialRampToValueAtTime(Math.max(f1, 1), t0 + dur);
  const g = a.createGain(); g.gain.setValueAtTime(vol, t0); g.gain.exponentialRampToValueAtTime(0.001, t0 + dur);
  o.connect(g).connect(a.destination); o.start(t0); o.stop(t0 + dur + 0.02);
}
function sfx(name) {
  if (!FX.settings.sound || C.off || FX.skipping) return;
  const a = ac();
  if (!a || a.state !== 'running') return;
  const v = Math.max(0, Math.min(1, FX.settings.volume == null ? 0.6 : FX.settings.volume));
  const t = a.currentTime;
  switch (name) {
    case 'pow': noise(a, 0.12, 1400, 'lowpass', v, t); tone(a, 'sine', 220, 60, 0.15, v * 0.8, t); break;
    case 'bam': noise(a, 0.22, 900, 'lowpass', v, t); tone(a, 'sine', 140, 40, 0.25, v, t); break;
    case 'boom': noise(a, 0.6, 500, 'lowpass', v, t); tone(a, 'sine', 90, 25, 0.6, v, t); break;
    case 'whiff': noise(a, 0.25, 1800, 'bandpass', v * 0.5, t); break;
    case 'clang': tone(a, 'triangle', 1250, 1100, 0.35, v * 0.4, t); tone(a, 'triangle', 1870, 1700, 0.3, v * 0.25, t); break;
    case 'zap': tone(a, 'square', 900, 180, 0.3, v * 0.25, t); noise(a, 0.2, 4000, 'highpass', v * 0.3, t); break;
    case 'heal': [523, 659, 784].forEach((f, i) => tone(a, 'sine', f, f, 0.25, v * 0.35, t + i * 0.08)); break;
    case 'ko': tone(a, 'sawtooth', 320, 40, 0.9, v * 0.35, t); noise(a, 0.7, 700, 'lowpass', v, t + 0.05); break;
    case 'whoosh': noise(a, 0.35, 900, 'bandpass', v * 0.6, t); break;
    case 'fight': [392, 494, 587].forEach((f) => tone(a, 'sawtooth', f, f * 1.01, 0.5, v * 0.15, t)); break;
    case 'sad': [392, 370, 349].forEach((f, i) => tone(a, 'triangle', f, f, 0.35, v * 0.3, t + i * 0.3)); break;
    case 'win': [523, 659, 784, 1047].forEach((f, i) => tone(a, 'square', f, f, 0.22, v * 0.15, t + i * 0.12)); break;
    default: break;
  }
}

// ---------------------------------------------------------- overlay pieces
function word(text, x, y, o) {
  if (!text) return Promise.resolve();
  o = o || {};
  const w = div('ft-fx-word' + (o.burst ? ' burst' : '') + (o.puff ? ' puff' : ''), esc(text), {
    left: x + 'px', top: y + 'px', fontSize: (o.size || 4) + 'rem', color: o.color || '', zIndex: o.z || '',
  });
  if (o.burst) w.style.setProperty('--burst', o.burst);
  const rot = o.rot !== undefined ? o.rot : rnd(-12, 12);
  if (C.reduced) return anim(w, [{ opacity: 0 }, { opacity: 1, offset: 0.2 }, { opacity: 0 }], { duration: o.dur || 800 }).then(() => w.remove());
  return anim(w, [
    { transform: `translate(-50%,-50%) scale(0) rotate(${rot}deg)`, opacity: 1 },
    { transform: `translate(-50%,-50%) scale(1.25) rotate(${rot}deg)`, offset: 0.15 },
    { transform: `translate(-50%,-50%) scale(1) rotate(${rot}deg)`, offset: 0.3 },
    { transform: `translate(-50%,-60%) scale(1.05) rotate(${rot}deg)`, opacity: 1, offset: 0.8 },
    { transform: `translate(-50%,-70%) scale(1.1) rotate(${rot}deg)`, opacity: 0 },
  ], { duration: o.dur || 900, easing: 'ease-out' }).then(() => w.remove());
}
function floatNum(text, x, y, cls) {
  const n = div('ft-fx-num ' + (cls || ''), esc(text), { left: x + 'px', top: y + 'px' });
  return anim(n, [
    { transform: 'translate(-50%,-50%) scale(.4)', opacity: 0 },
    { transform: 'translate(-50%,-90%) scale(1.2)', opacity: 1, offset: 0.2 },
    { transform: 'translate(-50%,-200%) scale(1)', opacity: 0 },
  ], { duration: 1000, easing: 'ease-out' }).then(() => n.remove());
}
function bubble(text, r) {
  if (!text || FX.settings.taunts === false || !r) return;
  const b = div('ft-fx-bubble', esc(text), { left: Math.max(8, r.x - 150) + 'px', top: Math.max(8, r.y - 40) + 'px' });
  anim(b, [{ transform: 'scale(0)', opacity: 0 }, { transform: 'scale(1.1)', opacity: 1, offset: 0.12 },
    { transform: 'scale(1)', opacity: 1, offset: 0.2 }, { opacity: 1, offset: 0.85 }, { opacity: 0 }],
  { duration: 1800, easing: 'ease-out' }).then(() => b.remove());
}
function flashRect(r, color, dur, opacity) {
  if (!r || C.reduced) return Promise.resolve();
  const f = div('ft-fx-flash', '', { inset: 'auto', left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px', background: color, borderRadius: '10px' });
  return anim(f, [{ opacity: opacity || 0.9 }, { opacity: 0 }], { duration: dur || 180 }).then(() => f.remove());
}
function screenFlash(color, peak, dur) {
  if (C.reduced) return Promise.resolve();
  const f = div('ft-fx-flash', '', { background: color });
  return anim(f, [{ opacity: 0 }, { opacity: peak, offset: 0.15 }, { opacity: 0 }], { duration: dur || 300 }).then(() => f.remove());
}
function shake(level) {
  if (C.off || C.low || C.reduced || !level) return;
  const a = app();
  a.classList.remove('ft-shake-1', 'ft-shake-2', 'ft-shake-3');
  void a.offsetWidth;
  a.classList.add('ft-shake-' + level);
  setTimeout(() => a.classList.remove('ft-shake-' + level), 700 * C.k);
}
function punch(amount) {
  if (C.off || C.low || C.reduced) return;
  anim(app(), [{ transform: 'scale(1)' }, { transform: `scale(${1 + amount})`, offset: 0.3 }, { transform: 'scale(1)' }], { duration: 260, easing: 'ease-out' });
}
function streak(from, to, miss) {
  if (C.reduced || !from || !to) return Promise.resolve();
  const end = miss ? { x: to.x + 200, y: to.y - 120 } : to;
  const dx = end.x - from.x, dy = end.y - from.y;
  const len = Math.hypot(dx, dy);
  const s = div('ft-fx-streak', '', { left: from.x + 'px', top: from.y + 'px', width: len + 'px', transform: `rotate(${Math.atan2(dy, dx)}rad) scaleX(0)` });
  const rot = `rotate(${Math.atan2(dy, dx)}rad)`;
  return anim(s, [{ transform: rot + ' scaleX(0)', opacity: 1 }, { transform: rot + ' scaleX(1)', opacity: 1, offset: 0.6 }, { transform: rot + ' scaleX(1)', opacity: 0 }],
    { duration: 220, easing: 'ease-in' }).then(() => s.remove());
}
function padPoint() {
  const pad = q('.st-key-ft_dmg_row') || q('.st-key-ft_pad');
  const r = rectOf(pad);
  return r ? { x: r.x + r.w * 0.6, y: r.y + r.h * 0.4 } : { x: 0, y: W.innerHeight * 0.7 };
}
function cine(cls, html) {
  const c = div('ft-fx-cine ' + (cls || ''), html + '<div class="skip">CLICK TO SKIP</div>');
  root.classList.add('blocking');
  return c;
}
function closeCine(c, dur) {
  return anim(c, [{ opacity: 1 }, { opacity: 0 }], { duration: dur || 250 }).then(() => {
    c.remove();
    if (!root.querySelector('.ft-fx-cine')) root.classList.remove('blocking');
  });
}
function slam(el, delay, base) {
  base = base || '';
  return anim(el, [{ transform: base + ' scale(3)', opacity: 0 }, { transform: base + ' scale(.9)', opacity: 1, offset: 0.6 }, { transform: base + ' scale(1)', opacity: 1 }],
    { duration: 380, delay: (delay || 0) * C.k, easing: 'cubic-bezier(.2,.9,.3,1.3)', fill: 'both' });
}

// ------------------------------------------------------------- the timeline
FX.receive = function (payload) {
  settings(payload.settings);
  FX.assets = payload.assets || {};
  const fresh = (payload.cues || []).filter((c) => !FX.seen.has(c.id));
  fresh.forEach((c) => FX.seen.add(c.id));
  const targets = new Set();
  if (!C.off) fresh.forEach((c) => { targets.add(c.target); if (c.params && c.params.out) targets.add(c.params.out); });
  D.querySelectorAll('.ft-arriving').forEach((el) => { if (!targets.has(el.dataset.fxId)) el.classList.remove('ft-arriving'); });
  if (!fresh.length || C.off) {
    if (!FX.playing) setTimeout(snapshot, 50);
    return;
  }
  FX.queue.push(...fresh);
  if (!FX.playing) run();
};

function settle() {
  return new Promise((res) => {
    let t = null;
    const fin = () => { mo.disconnect(); clearTimeout(t); clearTimeout(cap); res(); };
    const mo = new MutationObserver(() => { clearTimeout(t); t = setTimeout(fin, 60); });
    mo.observe(D.body, { childList: true, subtree: true });
    t = setTimeout(fin, 80);
    const cap = setTimeout(fin, 500);
  });
}

async function run() {
  FX.playing = true;
  try {
    await settle();
    while (FX.queue.length) {
      const batch = FX.queue.splice(0, FX.queue.length);
      let running = [];
      for (const c of batch) {
        const fn = HANDLERS[c.kind];
        if (!fn) continue;
        if (c.blocking) {
          await Promise.all(running);
          running = [];
          await fn(c).catch((e) => console.warn('ft fx', c.kind, e));
        } else {
          const p = fn(c).catch((e) => console.warn('ft fx', c.kind, e));
          running.push(p);
          await Promise.race([p, wait(Math.max(0, (c.duration_ms || 600) - 150))]);
        }
      }
      await Promise.all(running);
    }
  } finally {
    Object.values(FX.ghosts).forEach((g) => g.remove());
    FX.ghosts = {};
    D.querySelectorAll('.ft-arriving').forEach((el) => el.classList.remove('ft-arriving'));
    D.querySelectorAll('[data-fx-id]').forEach((el) => { if (el.style.visibility === 'hidden') el.style.visibility = ''; });
    root.querySelectorAll('.ft-fx-cine').forEach((c) => c.remove());
    root.classList.remove('blocking');
    FX.playing = false;
    FX.skipping = false;
    snapshot();
  }
}

function skip() {
  if (!FX.playing) return;
  FX.skipping = true;
  [...pending].forEach((f) => f());
  FX.anims.forEach((a) => { try { a.finish(); } catch (e) { a.cancel(); } });
  parts.length = 0;
}
on(root, 'click', () => { if (root.classList.contains('blocking')) skip(); });
on(D, 'keydown', (e) => { if (e.code === 'Space' && FX.playing && root.classList.contains('blocking')) { e.preventDefault(); skip(); } });

// ---------------------------------------------------------- inline effects
const HANDLERS = {};
const BURSTS = { 1: ['#FFD400', '#E63946'], 2: ['#FF7B00', '#FFD400'], 3: ['#E63946', '#FFD400'] };

HANDLERS.hit = async (c) => {
  relax();
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  const p = c.params, tier = Math.max(1, Math.min(3, p.tier || 1));
  const hp = { x: r.x + r.w * rnd(0.3, 0.7), y: r.y + r.h * rnd(0.25, 0.6) };
  if (p.word && performance.now() - (FX.anticipated || 0) > 1500) await streak(padPoint(), hp);
  if (C.reduced) {
    floatNum('-' + p.amount, hp.x, r.y + r.h * 0.2);
    return wait(500);
  }
  flashRect(r, '#fff', 90, 0.85);
  flashRect(r, '#E63946', 420, 0.45);
  const stop = [60, 90, 140][tier - 1];
  await wait(stop);
  const kx = [12, 24, 40][tier - 1], rot = [2, 4, 6][tier - 1];
  anim(el, [{ transform: 'none' }, { transform: `translate(${kx}px,-4px) rotate(${rot}deg)`, offset: 0.2 },
    { transform: `translate(${-kx * 0.25}px,0) rotate(${-rot * 0.3}deg)`, offset: 0.6 }, { transform: 'none' }],
  { duration: 420 + tier * 80, easing: 'cubic-bezier(.3,1.5,.5,1)' });
  emit(hp.x, hp.y, 8 + tier * 10, { color: ['#fff', '#FFD400', '#FF7B00'], min: 3, max: 9 + tier * 2, g: 0.15, life: 22 });
  if (tier === 3) {
    emit(hp.x, hp.y, 25, { shape: 'debris', color: ['#3A3A46', '#9A96A0', '#E63946'], min: 2, max: 10, g: 0.4, life: 50, size: 4 });
    const crack = div('ft-fx-crack', '', { position: 'fixed', inset: 'auto', left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' });
    anim(crack, [{ opacity: 1 }, { opacity: 1, offset: 0.7 }, { opacity: 0 }], { duration: 900 }).then(() => crack.remove());
  }
  shake(tier === 3 ? 3 : tier === 2 ? 1 : 0);
  punch([0.02, 0.03, 0.05][tier - 1]);
  sfx(['pow', 'bam', 'boom'][tier - 1]);
  floatNum('-' + p.amount, hp.x + rnd(-20, 20), r.y + r.h * 0.18);
  if (p.word) {
    const colors = BURSTS[tier];
    await word(p.word, r.x + r.w * rnd(0.35, 0.65), r.y + r.h * rnd(0.15, 0.35), { burst: colors[0], color: colors[1], size: 3 + tier * 1.2 });
  } else {
    await wait(600);
  }
};

HANDLERS.whiff = async (c) => {
  relax();
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  const m = center(r);
  streak(padPoint(), m, true);
  sfx('whiff');
  anim(el, [{ transform: 'none' }, { transform: 'translate(-10px,0) rotate(-4deg)', offset: 0.35 }, { transform: 'none' }], { duration: 500, easing: 'ease-out' });
  bubble(c.params.taunt, r);
  await word(c.params.word, m.x - r.w * 0.2, r.y + r.h * 0.3, { puff: true, color: '#d6d6dc', size: 3 });
};

HANDLERS.armor = async (c) => {
  const r = imgRect(cardEl(c.target));
  if (!r) return;
  sfx('clang');
  const x = r.x + r.w * 0.15, y = r.y + r.h * 0.45;
  emit(x, y, 12, { color: ['#fff', '#adb5bd'], min: 3, max: 7, g: 0.2, life: 18 });
  const t = div('ft-fx-num ft-fx-small', '&#128737; ' + esc(c.params.from) + ' &rarr; ' + esc(c.params.to), { left: x + 'px', top: y + 'px' });
  anim(t, [{ transform: 'translate(-50%,-50%) scale(.5)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1.2)', opacity: 1, offset: 0.2 },
    { transform: 'translate(-50%,-80%) scale(1)', opacity: 1, offset: 0.8 }, { opacity: 0 }], { duration: 1100 }).then(() => t.remove());
  await word(c.params.word, x, y - 50, { color: '#e9ecef', size: 2.4, burst: '#3A3A46', dur: 700 });
};

HANDLERS.dodge = async (c) => {
  relax();
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  sfx('whoosh');
  streak(padPoint(), center(r), true);
  if (!C.reduced) {
    const img = el.querySelector('img');
    for (let i = 1; i <= 3 && img; i++) {
      const g = div('ft-fx-sprite', '<img src="' + esc(img.currentSrc || img.src) + '">', { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px', opacity: 0.35 / i });
      anim(g, [{ transform: 'none' }, { transform: `translate(${20 * i}px,${-14 * i}px)`, opacity: 0 }], { duration: 400 + i * 60 }).then(() => g.remove());
    }
    anim(el, [{ transform: 'none' }, { transform: 'translate(46px,-24px) skewX(-8deg)', offset: 0.3 }, { transform: 'translate(46px,-24px)', offset: 0.6 }, { transform: 'none' }],
      { duration: 650, easing: 'cubic-bezier(.3,1.3,.5,1)' });
  }
  bubble(c.params.taunt, r);
  await word(c.params.word, r.x + r.w * 0.5, r.y + r.h * 0.3, { color: '#9be7ff', size: 3.2 });
};

HANDLERS.minion = async (c) => {
  relax();
  const r = imgRect(cardEl(c.target));
  if (!r) return;
  const m = div('ft-fx-word', '&#129485;', { left: r.x + r.w * 0.15 + 'px', top: r.y + r.h * 0.6 + 'px', fontSize: '3.6rem' });
  await anim(m, [{ transform: 'translate(-50%,40%) scale(.3)', opacity: 0 }, { transform: 'translate(-50%,-80%) scale(1.2)', opacity: 1, offset: 0.4 },
    { transform: 'translate(-50%,-50%) scale(1)', opacity: 1 }], { duration: 380, easing: 'ease-out' });
  streak(padPoint(), { x: r.x + r.w * 0.15, y: r.y + r.h * 0.6 });
  await wait(200);
  sfx('pow');
  emit(r.x + r.w * 0.15, r.y + r.h * 0.6, 26, { color: ['#c0a080', '#fff', '#FFD400'], min: 3, max: 9, life: 26 });
  m.remove();
  bubble(c.params.taunt, r);
  await word(c.params.word, r.x + r.w * 0.5, r.y + r.h * 0.35, { burst: '#c0a080', color: '#fff', size: 2.8 });
};

HANDLERS.heal = async (c) => {
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  sfx('heal');
  anim(el, [{ transform: 'none', filter: 'none' }, { transform: 'translateY(-8px)', filter: 'drop-shadow(0 0 22px #2DC653)', offset: 0.4 }, { transform: 'none', filter: 'none' }],
    { duration: 800, easing: 'ease-out' });
  for (let i = 0; i < 4; i++) setTimeout(() => emit(r.x + r.w / 2, r.y + r.h * 0.9, 8, { jx: r.w / 2, angle: -Math.PI / 2, spread: 0.4, min: 1, max: 3, g: -0.02, color: ['#2DC653', '#b9fbc0', '#fff'], shape: 'dot', size: 3, life: 60 }), i * 120 * C.k);
  await floatNum('+' + c.params.amount, r.x + r.w / 2, r.y + r.h * 0.25, 'heal');
};

HANDLERS.tick = async (c) => {
  const r = imgRect(cardEl(c.target));
  if (!r) return;
  const p = c.params;
  for (let i = 0; i < 5; i++) {
    setTimeout(() => {
      if (p.poison) emit(r.x + r.w / 2, r.y + r.h, 6, { jx: r.w / 2, angle: -Math.PI / 2, spread: 0.3, min: 1, max: 3, g: -0.03, color: ['#8AC926', '#c5f277'], shape: 'bubble', size: 4, life: 60 });
      if (p.fire) emit(r.x + r.w / 2, r.y + r.h, 8, { jx: r.w / 2, angle: -Math.PI / 2, spread: 0.5, min: 2, max: 5, g: -0.05, color: ['#FF7B00', '#FFD400', '#E63946'], shape: 'dot', size: 3, life: 45 });
    }, i * 90 * C.k);
  }
  sfx(p.fire ? 'whoosh' : 'whiff');
  await word(p.word, r.x + r.w * 0.5, r.y + r.h * 0.75, { color: p.fire ? '#FF7B00' : '#8AC926', size: 3, rot: -6 });
};

HANDLERS.lunge = async (c) => {
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  sfx('whoosh');
  bubble(c.params.taunt, r);
  await anim(el, [{ transform: 'none', filter: 'none' }, { transform: 'translateX(-30px) scale(1.05)', filter: 'drop-shadow(0 0 26px #E63946)', offset: 0.35 },
    { transform: 'none', filter: 'none' }], { duration: 560, easing: 'cubic-bezier(.3,1.3,.5,1)' });
};

HANDLERS.combo = async (c) => {
  const r = imgRect(cardEl(c.target));
  if (!r) return;
  await word(c.params.actions + ' ACTIONS!', r.x + r.w * 0.5, r.y + r.h * 0.12, { burst: '#E63946', color: '#FFD400', size: 3.2, rot: -4, dur: 1000 });
};

HANDLERS.token = async (c) => {
  const p = c.params;
  const b = byId('badge-' + c.target.slice(5) + '-' + p.token);
  if (b && p.value > 0) {
    await anim(b, [{ transform: 'scale(.2)' }, { transform: 'scale(1.35)', offset: 0.6 }, { transform: 'scale(1)' }], { duration: 420, easing: 'cubic-bezier(.34,1.8,.64,1)' });
    return;
  }
  const r = imgRect(cardEl(c.target));
  if (!r) return;
  const sign = p.delta > 0 ? '+' : '';
  const t = div('ft-fx-num ft-fx-small', esc(sign + p.delta + ' ' + String(p.token).toUpperCase()), { left: r.x + 20 + 'px', top: r.y + r.h * 0.3 + 'px' });
  await anim(t, [{ opacity: 0, transform: 'translate(-50%,-50%) scale(.6)' }, { opacity: 1, transform: 'translate(-50%,-80%) scale(1)', offset: 0.3 },
    { opacity: 0, transform: 'translate(-50%,-160%)' }], { duration: 900 }).then(() => t.remove());
};

HANDLERS.poof = async (c) => {
  const r = imgRect(cardEl(c.target));
  if (!r) return;
  const x = r.x + 10, y = r.y + r.h * 0.35;
  emit(x, y, 20, { color: ['#d6d6dc', '#9A96A0', c.params.token === 'blessed' ? '#FFC300' : '#9D4EDD'], min: 2, max: 6, g: 0.05, life: 30, shape: 'dot', size: 4 });
  await word(c.params.word, x + 40, y, { puff: true, color: '#fff', size: 2.6 });
};

HANDLERS.charge_on = async (c) => {
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  sfx('zap');
  anim(el, [{ transform: 'none' }, { transform: 'scaleY(.96) translateY(6px)', offset: 0.3 }, { transform: 'scaleY(1.02)', filter: 'drop-shadow(0 0 18px #FFD400)', offset: 0.6 }, { transform: 'none' }],
    { duration: 650, easing: 'ease-out' });
  bolt(r.x + r.w * rnd(0.3, 0.7), r.y - 40, r.y + r.h * 0.7);
  const ind = byId('charge-' + c.target.slice(5));
  if (ind) anim(ind, [{ transform: 'rotateY(0)' }, { transform: 'rotateY(180deg) scale(1.4)', offset: 0.5 }, { transform: 'rotateY(360deg)' }], { duration: 600 });
  await word(c.params.word, r.x + r.w * 0.5, r.y + r.h * 0.25, { color: '#FFD400', burst: '#9D4EDD', size: 3.6 });
};

HANDLERS.charge_off = async (c) => {
  const ind = byId('charge-' + c.target.slice(5));
  if (ind) await anim(ind, [{ transform: 'rotateY(360deg)' }, { transform: 'rotateY(0)' }], { duration: 450 });
};

HANDLERS.ultimate_form = async (c) => {
  const r = imgRect(cardEl(c.target));
  if (!r) return;
  const m = center(r);
  sfx('heal');
  for (let i = 0; i < 3; i++) setTimeout(() => emit(m.x, m.y, 30, { jx: r.w / 2, jy: r.h / 2, color: ['#FFC300', '#fff3b0'], shape: 'dot', min: 0.5, max: 2, g: -0.03, size: 3, life: 50 }), i * 150 * C.k);
  await word('\u2605', r.x + 24, r.y + 24, { color: '#FFC300', size: 4.5, rot: 0 });
};

HANDLERS.taunt = async (c) => { bubble(c.params.text, imgRect(cardEl(c.target))); };

HANDLERS.turn_banner = async (c) => {
  if (C.reduced) return;
  const side = c.params.side === 'enemy' ? 'enemy' : 'players';
  const b = div('ft-fx-banner ' + side, side === 'enemy' ? 'ENEMY TURN' : 'YOUR TURN');
  sfx('whoosh');
  await anim(b, [{ transform: 'skewY(-6deg) translateX(-110%)' }, { transform: 'skewY(-6deg) translateX(0)', offset: 0.25 },
    { transform: 'skewY(-6deg) translateX(0)', offset: 0.75 }, { transform: 'skewY(-6deg) translateX(110%)' }],
  { duration: 1100, easing: 'cubic-bezier(.6,0,.4,1)' });
  b.remove();
};

function bolt(x, y0, y1) {
  if (C.reduced || C.low) return;
  const pts = [];
  for (let y = y0; y < y1; y += rnd(18, 36)) pts.push([x + rnd(-22, 22), y]);
  let t = 0;
  actor((dt, g) => {
    t += dt;
    g.save(); g.strokeStyle = '#fff59a'; g.shadowColor = '#FFD400'; g.shadowBlur = 20; g.lineWidth = 5 * (1 - t / 18);
    g.beginPath(); pts.forEach(([px, py], i) => (i ? g.lineTo(px, py) : g.moveTo(px, py))); g.stroke(); g.restore();
    return t < 18;
  });
}

function relax() {
  if (FX.tense) { try { FX.tense.cancel(); } catch (e) { /* element gone */ } FX.tense = null; }
  clearTimeout(FX.tenseTimer);
}
