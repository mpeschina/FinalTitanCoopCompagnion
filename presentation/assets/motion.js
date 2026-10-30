/* Card motion: FLIP travel between zones, swap, anticipation on click, idle tilt, tap-to-zoom lightbox. */

function backSrc(kind) { return kind === 'upgrade' ? FX.assets.upgrade_back : FX.assets.titan_back; }

function sprite(src, r, back) {
  return div('ft-fx-sprite',
    '<img class="front" src="' + esc(src) + '">' + (back ? '<img class="back" src="' + esc(back) + '">' : ''),
    { left: r.x + 'px', top: r.y + 'px', width: r.w + 'px', height: r.h + 'px' });
}

function land(r, level) {
  emit(r.x + r.w / 2, r.y + r.h, 14 * level, { jx: r.w / 2, angle: -Math.PI / 2, spread: 1.3, min: 1, max: 4, g: 0.12,
    color: ['#9A96A0', '#3A3A46', '#F2EBDD'], shape: 'dot', size: 4, life: 30 });
  if (level > 1) shake(1);
}
function spark(r) {
  const m = center(r);
  emit(m.x, m.y, 22, { color: ['#fff', '#FFD400'], min: 3, max: 8, g: 0.1, life: 20 });
}

// Moves the card with this target from its old box (or a zone) to its new box in the DOM.
async function move(target, fromZone, flip, backKind, opts) {
  opts = opts || {};
  const el = byId(target);
  const to = imgRect(el);
  if (!el || !to) return;
  el.classList.remove('ft-arriving');
  const snap = FX.rects[target];
  const zone = el.closest('[data-fx-zone]');
  let from = snap && snap.zone !== (zone ? zone.dataset.fxZone : null) ? snap.rect : null;
  if (!from && fromZone) from = zoneRect(fromZone);
  if (!from) return;
  if (C.reduced) { await anim(el, [{ opacity: 0 }, { opacity: 1 }], { duration: 300 }); return; }
  const img = el.querySelector('img');
  const s = sprite(img.currentSrc || img.src, to, flip ? backSrc(backKind) : null);
  if (opts.z) s.style.zIndex = opts.z;
  el.style.visibility = 'hidden';
  const dx = from.x + from.w / 2 - (to.x + to.w / 2), dy = from.y + from.h / 2 - (to.y + to.h / 2);
  const sc = from.w / to.w, lift = opts.lift !== undefined ? opts.lift : -80, ry = flip ? 180 : 0;
  await anim(s, [
    { transform: `perspective(1200px) translate(${dx}px,${dy}px) scale(${sc}) rotateY(${ry}deg)` },
    { transform: `perspective(1200px) translate(${dx * 0.45}px,${dy * 0.45 + lift}px) scale(${((sc + 1) / 2) * 1.12}) rotateY(${ry / 2}deg) rotate(${rnd(-6, 6)}deg)`, offset: 0.55 },
    { transform: 'perspective(1200px) translate(0,0) scale(1) rotateY(0deg)' },
  ], { duration: opts.dur || 750, easing: 'cubic-bezier(.45,0,.25,1)' });
  el.style.visibility = '';
  s.remove();
  if (opts.land) land(to, opts.land);
}

HANDLERS.move = (c) => move(c.target, c.params.from, c.params.flip, 'titan');

HANDLERS.reveal_upgrade = async (c) => {
  sfx('whoosh');
  await move(c.target, 'hand', true, 'upgrade', { dur: 800, lift: -60 });
  const el = byId(c.target);
  const r = imgRect(el);
  if (r) spark(r);
  const sticker = el && el.querySelector('.ft-new');
  if (sticker) anim(sticker, [{ transform: 'rotate(8deg) scale(3)', opacity: 0 }, { transform: 'rotate(8deg) scale(1)', opacity: 1 }], { duration: 260, easing: 'cubic-bezier(.2,.9,.3,1.3)' });
};

HANDLERS.reveal_bench = async (c) => {
  await move(c.target, 'deck', true, 'titan', { dur: 700, lift: -50 });
  const r = imgRect(byId(c.target));
  if (r) spark(r);
};

HANDLERS.swap = async (c) => {
  sfx('whoosh');
  await Promise.all([
    move(c.params.out, null, false, 'titan', { lift: 70 }),
    move(c.target, null, false, 'titan', { z: 3, lift: -110, land: 1 }),
  ]);
};

HANDLERS.retreat = async (c) => {
  await move(c.target, null, false, 'titan', { lift: -40, dur: 650 });
  const r = imgRect(byId(c.target));
  if (r) await word(c.params.word, r.x + r.w / 2, r.y + r.h * 0.3, { burst: '#00B4D8', color: '#fff', size: 3.4 });
};

// ------------------------------------------------- anticipation (< 100 ms)
function anticipate(btn) {
  const card = q('.ft-card.arena');
  const r = imgRect(card), b = rectOf(btn);
  if (!r || !b) return;
  relax();
  FX.anticipated = performance.now();
  streak(center(b), { x: r.x + r.w * 0.5, y: r.y + r.h * 0.4 });
  FX.tense = card.animate([{ transform: 'none' }, { transform: 'translateX(8px) scale(.97) rotate(1.5deg)' }], { duration: 120, fill: 'forwards', easing: 'ease-out' });
  FX.tenseTimer = setTimeout(() => {
    const t = FX.tense;
    FX.tense = null;
    if (t) { t.reverse(); t.finished.then(() => t.cancel()).catch(() => {}); }
  }, 800);
}

on(D, 'pointerdown', (e) => {
  snapshot();
  const a = FX.settings.sound ? ac() : null;
  if (a && a.state === 'suspended') a.resume();
  const btn = e.target.closest && e.target.closest('[class*="st-key-dmg_q"] button, .st-key-dmg_go button');
  if (btn && !C.off && !C.reduced) {
    btn.classList.add('ft-pressed');
    setTimeout(() => btn.classList.remove('ft-pressed'), 160);
    anticipate(btn);
  }
}, true);
on(D, 'keydown', () => snapshot(), true);

// ------------------------------------------------- idle tilt toward the mouse
let tiltFrame = 0;
on(D, 'mousemove', (e) => {
  if (tiltFrame || FX.settings.idle === false || C.reduced || C.off) return;
  tiltFrame = W.requestAnimationFrame(() => {
    tiltFrame = 0;
    const card = q('.ft-card.arena');
    const img = card && card.querySelector('.ft-img');
    const r = rectOf(img);
    if (!r) return;
    const px = (e.clientX - r.x) / r.w, py = (e.clientY - r.y) / r.h;
    const inside = px >= 0 && px <= 1 && py >= 0 && py <= 1;
    img.style.setProperty('--ry', inside ? ((px - 0.5) * 12).toFixed(2) + 'deg' : '0deg');
    img.style.setProperty('--rx', inside ? ((0.5 - py) * 12).toFixed(2) + 'deg' : '0deg');
    const fl = card.querySelector('.ft-float');
    if (fl && inside) { fl.style.setProperty('--mx', (px * 100).toFixed(1) + '%'); fl.style.setProperty('--my', (py * 100).toFixed(1) + '%'); }
  });
}, { passive: true });

// ------------------------------------------------- tap / click to zoom
on(D, 'click', (e) => {
  const img = e.target.closest && e.target.closest('.ft-zoomable .ft-img');
  if (!img) return;
  const lb = div('ft-fx-lightbox', '<img src="' + esc(img.dataset.zoom || img.src) + '" alt="">');
  anim(lb, [{ opacity: 0 }, { opacity: 1 }], { duration: 150 });
  lb.addEventListener('click', () => lb.remove());
});
