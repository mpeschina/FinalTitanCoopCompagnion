/* Blocking cinematics (§3.2). Each one is skippable by click or space; the board below already shows the final state. */

function summaryHtml(p) {
  const rows = [
    ['Fights', p.fights], ['K.O.s', p.kos !== undefined ? p.kos + ' / ' + p.total : undefined], ['Ultimates', p.ultimates],
    ['Damage dealt', p.damage], ['Your Titans left', p.titans_left !== undefined ? p.titans_left + ' / ' + p.titans_total : undefined],
  ];
  return rows.filter(([, v]) => v !== undefined).map(([k, v]) => '<span>' + esc(k) + '</span><b>' + esc(v) + '</b>').join('');
}

function bigWord(text, x, y, size, burst, color) {
  const t = div('ft-fx-word' + (burst ? ' burst' : ''), esc(text), { left: x + 'px', top: y + 'px', fontSize: size, zIndex: 12, color: color || '' });
  if (burst) t.style.setProperty('--burst', burst);
  return t;
}

HANDLERS.title = async (c) => {
  if (!cineOn(c)) return;
  const diff = c.params.difficulty ? '<div class="stamp">' + esc(String(c.params.difficulty).toUpperCase()) + '</div>' : '';
  const cn = cine('', '<div class="lines"></div><div class="stack"><div class="title">FINAL TITAN</div><div class="sub">&mdash; CO-OP &mdash;</div>' + diff + '</div>');
  sfx('fight');
  slam(cn.querySelector('.title'));
  slam(cn.querySelector('.sub'), 250);
  const stamp = cn.querySelector('.stamp');
  if (stamp) {
    anim(stamp, [{ transform: 'rotate(-8deg) scale(4)', opacity: 0 }, { transform: 'rotate(-8deg) scale(1)', opacity: 1 }],
      { duration: 240, delay: 750 * C.k, fill: 'both', easing: 'cubic-bezier(.2,.9,.3,1.3)' }).then(() => { shake(1); sfx('bam'); });
  }
  await wait(c.duration_ms - 300);
  await closeCine(cn);
};

HANDLERS.reveal_arena = async (c) => {
  const p = c.params;
  sfx('whoosh');
  await move(c.target, p.from, p.flip, 'titan', { dur: 800, land: 2, lift: -120 });
  const r = imgRect(byId(c.target));
  if (!r || !cineOn(c)) return;
  const m = center(r);
  const cn = cine('', '<div class="spot"></div>');
  cn.style.background = 'transparent';
  cn.querySelector('.spot').style.background =
    `radial-gradient(ellipse ${Math.round(r.w * 0.8)}px ${Math.round(r.h * 0.7)}px at ${m.x}px ${m.y}px, transparent 0 55%, rgba(0,0,0,.9) 100%)`;
  const head = p.role === 'champion' ? 'THE CHAMPION AWAITS!' : 'A NEW CHALLENGER!';
  const h = bigWord(head, m.x, Math.max(70, r.y + 40), 'clamp(2rem, 4vw, 3.4rem)', null, '#fff');
  const t = bigWord(p.name, m.x, r.y + r.h * 0.8, 'clamp(2.6rem, 5vw, 4.6rem)', '#E63946', '#FFD400');
  sfx('bam');
  shake(1);
  slam(h, 0, 'translate(-50%,-50%)');
  slam(t, 280, 'translate(-50%,-50%)');
  await wait(c.duration_ms - 900);
  h.remove();
  t.remove();
  await closeCine(cn);
};

HANDLERS.vs = async (c) => {
  const p = c.params;
  const el = byId(p.card);
  const img = el && el.querySelector('img');
  if (!cineOn(c)) {
    const r = imgRect(el);
    if (r) await word(p.word, r.x + r.w / 2, r.y + r.h * 0.4, { burst: '#E63946', color: '#FFD400', size: 5 });
    return;
  }
  const players = p.role === 'champion' ? 'YOUR CHALLENGER' : 'YOUR CHAMPION';
  const pic = img ? '<img src="' + esc(img.currentSrc || img.src) + '" alt="">' : '';
  const cn = cine('', '<div class="vs"><div class="left"><div class="sil"></div><div class="sub">' + players + '</div></div>'
    + '<div class="right">' + pic + '<div class="sub">' + esc(p.name) + '</div></div></div><div class="vs-word">VS</div>');
  const vw = cn.querySelector('.vs-word');
  vw.style.opacity = 0;
  anim(cn.querySelector('.left'), [{ transform: 'translateX(-100%)' }, { transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.2,.9,.3,1.2)' });
  await anim(cn.querySelector('.right'), [{ transform: 'translateX(100%)' }, { transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.2,.9,.3,1.2)' });
  sfx('bam');
  vw.style.opacity = '';
  slam(vw, 0, 'translate(-50%,-50%)');
  shake(1);
  bubble(p.taunt, rectOf(cn.querySelector('.right img')));
  await wait(1100);
  vw.textContent = p.word || 'FIGHT!';
  sfx('fight');
  slam(vw, 0, 'translate(-50%,-50%)');
  shake(2);
  await wait(750);
  await closeCine(cn);
};

HANDLERS.ultimate = async (c) => {
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  const img = el.querySelector('img');
  if (!cineOn(c) || !img) {
    shake(2);
    await word(c.params.word, r.x + r.w / 2, r.y + r.h * 0.3, { burst: '#E63946', color: '#FFD400', size: 4.5 });
    return;
  }
  sfx('zap');
  screenFlash('#E63946', 0.6, 280);
  const cn = cine('', '<div class="lines" style="--lines: rgba(230,57,70,.4)"></div>');
  const s = sprite(img.currentSrc || img.src, r);
  s.style.zIndex = 11;
  el.style.visibility = 'hidden';
  const vw = W.innerWidth, vh = W.innerHeight;
  const dx = vw / 2 - (r.x + r.w / 2), dy = vh / 2 - (r.y + r.h / 2), sc = Math.min(1.6, (vh * 0.8) / r.h);
  await anim(s, [{ transform: 'none' }, { transform: `translate(${dx}px,${dy}px) scale(${sc})` }], { duration: 450, easing: 'cubic-bezier(.2,.9,.3,1.2)', fill: 'forwards' });
  shake(3);
  const t = bigWord(c.params.word, vw / 2, vh * 0.8, 'clamp(4rem, 11vw, 10rem)', null, '#FFD400');
  anim(t, [{ transform: 'translate(-50%,40%) scale(.6)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1.1)', opacity: 1, offset: 0.6 },
    { transform: 'translate(-50%,-50%) scale(1)', opacity: 1 }], { duration: 500, easing: 'ease-out', fill: 'forwards' });
  for (let i = 0; i < 4; i++) {
    setTimeout(() => emit(vw / 2, vh / 2, 40, { color: ['#E63946', '#FFD400', '#fff', '#9D4EDD'], min: 6, max: 16, g: 0, drag: 0.94, life: 40 }), i * 150 * C.k);
  }
  bubble(c.params.taunt, { x: vw / 2 + r.w * sc * 0.35, y: vh / 2 - (r.h * sc) / 2 + 20, w: 0, h: 0 });
  await wait(1300);
  t.remove();
  await anim(s, [{ transform: `translate(${dx}px,${dy}px) scale(${sc})` }, { transform: 'none' }], { duration: 380, easing: 'cubic-bezier(.6,0,.9,.4)' });
  s.remove();
  el.style.visibility = '';
  land(r, 2);
  await closeCine(cn);
};

HANDLERS.ko = async (c) => {
  const p = c.params;
  const el = cardEl(c.target);
  const r = imgRect(el);
  if (!r) return;
  const img = el.querySelector('img');
  const src = img && (img.currentSrc || img.src);
  let cn = null;
  sfx('ko');
  if (cineOn(c)) {
    cn = cine('gray', '');
    cn.style.background = 'rgba(0,0,0,.35)';
    const t = bigWord(p.word, r.x + r.w / 2, r.y + r.h * 0.35, 'clamp(5rem, 9vw, 9rem)', '#E63946', '#FFD400');
    await slam(t, 0, 'translate(-50%,-50%)');
    shake(2);
    await wait(450);
    anim(t, [{ opacity: 1 }, { opacity: 0 }], { duration: 250 }).then(() => t.remove());
  }
  el.style.visibility = 'hidden';
  await destroyCard(src, r, p, p.slowmo ? 2 : 1);
  const pile = zoneRect('graveyard');
  if (pile && src && !C.reduced) {
    const g = sprite(src, r);
    g.style.filter = 'grayscale(1) brightness(.5)';
    const dx = pile.x + pile.w / 2 - (r.x + r.w / 2), dy = pile.y + pile.h / 2 - (r.y + r.h / 2);
    await anim(g, [{ transform: 'scale(.15)', opacity: 0 }, { transform: 'scale(.3)', opacity: 1, offset: 0.25 },
      { transform: `translate(${dx}px,${dy}px) scale(${pile.w / r.w})`, opacity: 1 }], { duration: 600, easing: 'ease-in' });
    g.remove();
    spark(pile);
  }
  const pips = byId('defeated');
  const lit = pips ? pips.querySelectorAll('.pip.on') : [];
  const pip = lit[lit.length - 1];
  if (pip) {
    const pr = rectOf(pip);
    anim(pip, [{ transform: 'scale(2.4)' }, { transform: 'scale(1)' }], { duration: 420, easing: 'cubic-bezier(.34,1.8,.64,1)' });
    if (pr) emit(pr.x + pr.w / 2, pr.y + pr.h / 2, 20, { color: ['#E63946', '#FFD400'], min: 2, max: 6, life: 20 });
  }
  if (cn) await closeCine(cn);
};

HANDLERS.player_lost = async (c) => {
  const p = c.params;
  let cn = null;
  if (cineOn(c)) {
    cn = cine('gray', '<div class="stack"><div class="sub">One of your Titans has fallen&hellip;</div></div>');
    cn.style.background = 'rgba(0,0,0,.45)';
  }
  sfx('sad');
  const arena = q('.ft-card.arena');
  if (arena) {
    anim(arena, [{ transform: 'none', filter: 'none' }, { transform: 'translateY(-18px) scale(1.04)', filter: 'drop-shadow(0 0 30px #E63946)', offset: 0.4 },
      { transform: 'none', filter: 'none' }], { duration: 1200 });
    bubble(p.taunt, imgRect(arena));
  }
  const pips = byId('titans-left');
  const pip = pips && pips.querySelector('.pip:not(.on)');
  if (pip) {
    const pr = rectOf(pip);
    anim(pip, [{ transform: 'scale(1.8)' }, { transform: 'scale(1.8) rotate(-15deg)', offset: 0.2 }, { transform: 'scale(1.8) rotate(12deg)', offset: 0.4 }, { transform: 'scale(1)' }], { duration: 750 });
    if (pr) emit(pr.x + pr.w / 2, pr.y + pr.h / 2, 16, { shape: 'debris', color: ['#00B4D8', '#08404d', '#000'], min: 1, max: 4, g: 0.3, life: 40, size: 3 });
  }
  await wait(c.duration_ms - 300);
  if (cn) await closeCine(cn);
};

HANDLERS.final_fight = async (c) => {
  if (!cineOn(c)) return;
  const cn = cine('alert', '');
  const b = div('ft-fx-banner final', 'FINAL FIGHT');
  b.style.zIndex = 11;
  sfx('bam');
  shake(2);
  await anim(b, [{ transform: 'skewY(-6deg) scaleX(0)' }, { transform: 'skewY(-6deg) scaleX(1.05)', offset: 0.3 }, { transform: 'skewY(-6deg) scaleX(1)' }], { duration: 450, easing: 'ease-out' });
  await wait(1100);
  b.remove();
  await closeCine(cn);
};

HANDLERS.victory = async (c) => {
  if (!cineOn(c)) return;
  const cn = cine('', '<div class="lines"></div><div class="stack"><div class="title">VICTORY!</div><div class="panel">' + summaryHtml(c.params) + '</div></div>');
  sfx('win');
  slam(cn.querySelector('.title'));
  const vw = W.innerWidth;
  for (let i = 0; i < 10; i++) {
    setTimeout(() => emit(rnd(0, vw), -10, 30, { shape: 'confetti', color: ['#FFD400', '#E63946', '#00B4D8', '#2DC653', '#9D4EDD'], angle: Math.PI / 2, spread: 0.7, min: 2, max: 6, g: 0.06, drag: 0.99, life: 160, size: 5 }), i * 300 * C.k);
  }
  await wait(c.duration_ms + 2000);
  await closeCine(cn);
};

HANDLERS.defeat = async (c) => {
  if (!cineOn(c)) return;
  const cn = cine('ink', '<div class="stack"><div class="title" style="color:#E63946;--shadow:#000">GAME OVER</div><div class="panel">' + summaryHtml(c.params)
    + '</div><div class="sub">Try again? &mdash; New game in the command pad.</div></div>');
  sfx('sad');
  anim(cn, [{ clipPath: 'circle(0% at 50% 45%)' }, { clipPath: 'circle(150% at 50% 45%)' }], { duration: 1200, easing: 'ease-in' });
  anim(cn.querySelector('.title'), [{ transform: 'translateY(-40px)', opacity: 0 }, { transform: 'translateY(0) scaleY(1.08)', opacity: 1, offset: 0.7 }, { transform: 'none', opacity: 1 }],
    { duration: 900, delay: 500 * C.k, fill: 'both' });
  await wait(c.duration_ms + 2000);
  await closeCine(cn);
};
