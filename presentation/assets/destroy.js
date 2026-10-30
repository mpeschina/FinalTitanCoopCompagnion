/* K.O. destroy animations on the overlay canvas: SLASH, DISSOLVE, SHATTER (§3.5). */

function loadImg(src) {
  return new Promise((res) => {
    const i = new Image();
    i.onload = () => res(i);
    i.onerror = () => res(null);
    i.src = src;
  });
}

function fadeOut(src, r) {
  const s = sprite(src, r);
  return anim(s, [{ filter: 'none', opacity: 1 }, { filter: 'grayscale(1)', opacity: 0 }], { duration: 400 }).then(() => s.remove());
}

async function destroyCard(src, r, p, slow) {
  if (!src) return;
  if (C.reduced) return fadeOut(src, r);
  const img = await loadImg(src);
  if (!img) return fadeOut(src, r);
  const sp = 1 / (slow || 1);
  if (p.style === 'slash') return slash(img, r, p.cuts || 1, sp);
  if (p.style === 'dissolve') return dissolve(img, r, p.color, sp, src);
  return shatter(img, r, sp);
}

function centroid(poly) {
  const c = poly.reduce((a, q2) => ({ x: a.x + q2.x, y: a.y + q2.y }), { x: 0, y: 0 });
  return { x: c.x / poly.length, y: c.y / poly.length };
}

// Splits a convex polygon by the infinite line through a and b.
function splitPoly(poly, a, b) {
  const L = [], R = [];
  const side = (pt) => (b.x - a.x) * (pt.y - a.y) - (b.y - a.y) * (pt.x - a.x);
  for (let i = 0; i < poly.length; i++) {
    const p1 = poly[i], p2 = poly[(i + 1) % poly.length];
    const s1 = side(p1), s2 = side(p2);
    if (s1 >= 0) L.push(p1);
    if (s1 <= 0) R.push(p1);
    if ((s1 > 0 && s2 < 0) || (s1 < 0 && s2 > 0)) {
      const t = s1 / (s1 - s2);
      const ip = { x: p1.x + (p2.x - p1.x) * t, y: p1.y + (p2.y - p1.y) * t };
      L.push(ip); R.push(ip);
    }
  }
  return [L, R].filter((x) => x.length >= 3);
}

function drawPiece(g, img, r, poly, c, x, y, rot, sx, alpha) {
  g.save();
  g.globalAlpha = Math.max(0, alpha);
  g.translate(r.x + c.x + x, r.y + c.y + y);
  g.rotate(rot);
  g.scale(sx, 1);
  g.translate(-c.x, -c.y);
  g.beginPath();
  poly.forEach((pt, i) => (i ? g.lineTo(pt.x, pt.y) : g.moveTo(pt.x, pt.y)));
  g.closePath();
  g.clip();
  g.drawImage(img, 0, 0, r.w, r.h);
  g.restore();
}

function slash(img, r, cuts, sp) {
  let pieces = [[{ x: 0, y: 0 }, { x: r.w, y: 0 }, { x: r.w, y: r.h }, { x: 0, y: r.h }]];
  const lines = [];
  for (let i = 0; i < cuts; i++) {
    const cx = r.w * rnd(0.3, 0.7), cy = r.h * rnd(0.25, 0.75);
    const ang = rnd(-0.95, -0.45) + (i % 2 ? Math.PI / 2.2 : 0);
    const dx = Math.cos(ang) * r.h * 2, dy = Math.sin(ang) * r.h * 2;
    const a = { x: cx - dx, y: cy - dy }, b = { x: cx + dx, y: cy + dy };
    lines.push([a, b, ang]);
    pieces = pieces.flatMap((pc) => splitPoly(pc, a, b));
  }
  const mid = { x: r.w / 2, y: r.h / 2 };
  const st = pieces.map((pc) => {
    const c = centroid(pc);
    const vx = c.x - mid.x, vy = c.y - mid.y, len = Math.hypot(vx, vy) || 1;
    return { pc, c, vx: (vx / len) * rnd(1.5, 3), vy: (vy / len) * rnd(1, 2), x: 0, y: 0, rot: 0, vr: rnd(-0.04, 0.04) };
  });
  sfx('pow');
  word('SHING!', r.x + r.w / 2, r.y + r.h * 0.2, { color: '#e0f7ff', burst: '#00B4D8', size: 3.4, dur: 700 });
  let t = 0, sparked = false;
  return actor((dt, g) => {
    t += dt * sp;
    if (t < 9) {
      g.drawImage(img, r.x, r.y, r.w, r.h);
      g.save();
      g.beginPath(); g.rect(r.x, r.y, r.w, r.h); g.clip();
      g.strokeStyle = '#fff'; g.shadowColor = '#9be7ff'; g.shadowBlur = 18; g.lineWidth = 6 * (1 - t / 9) + 1;
      lines.forEach(([a, b]) => { g.beginPath(); g.moveTo(r.x + a.x, r.y + a.y); g.lineTo(r.x + b.x, r.y + b.y); g.stroke(); });
      g.restore();
      return true;
    }
    if (!sparked) {
      sparked = true;
      lines.forEach(([, , ang]) => {
        for (let k = 0; k < 6; k++) {
          const d = rnd(-0.5, 0.5) * r.h;
          emit(r.x + r.w / 2 + Math.cos(ang) * d, r.y + r.h / 2 + Math.sin(ang) * d, 4, { color: ['#fff', '#9be7ff', '#FFD400'], min: 2, max: 7, g: 0.2, life: 22 });
        }
      });
    }
    const k = t - 9;
    let alive = false;
    st.forEach((s) => {
      s.x += s.vx * dt * sp; s.y += s.vy * dt * sp;
      if (k > 12) { s.vy += 0.35 * dt * sp; s.rot += s.vr * dt * sp * 3; }
      const alpha = 1 - k / 70;
      if (alpha > 0) alive = true;
      drawPiece(g, img, r, s.pc, s.c, s.x, s.y, s.rot, 1, alpha);
    });
    return alive;
  });
}

function valueNoise(w, h, cell) {
  const gw = Math.ceil(w / cell) + 2, gh = Math.ceil(h / cell) + 2;
  const grid = new Float32Array(gw * gh).map(() => Math.random());
  const out = new Float32Array(w * h);
  for (let y = 0; y < h; y++) {
    const gy = y / cell, y0 = Math.floor(gy), fy = gy - y0, sy = fy * fy * (3 - 2 * fy);
    for (let x = 0; x < w; x++) {
      const gx = x / cell, x0 = Math.floor(gx), fx = gx - x0, sx = fx * fx * (3 - 2 * fx);
      const a = grid[y0 * gw + x0], b = grid[y0 * gw + x0 + 1], c = grid[(y0 + 1) * gw + x0], d = grid[(y0 + 1) * gw + x0 + 1];
      out[y * w + x] = a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
    }
  }
  return out;
}

function dissolve(img, r, color, sp, src) {
  const w = Math.max(1, Math.round(r.w / 2)), h = Math.max(1, Math.round(r.h / 2));
  const off = D.createElement('canvas');
  off.width = w; off.height = h;
  const o = off.getContext('2d');
  o.drawImage(img, 0, 0, w, h);
  let base;
  try { base = o.getImageData(0, 0, w, h); } catch (e) { return fadeOut(src, r); }
  const frame = o.createImageData(w, h);
  const n1 = valueNoise(w, h, 14), n2 = valueNoise(w, h, 5);
  const corner = pick([[0, 0], [w, 0], [0, h], [w, h]]);
  const maxd = Math.hypot(w, h);
  const nz = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x;
    nz[i] = 0.4 * n1[i] + 0.15 * n2[i] + 0.45 * (Math.hypot(x - corner[0], y - corner[1]) / maxd);
  }
  const glow = color === 'fire' ? [255, 123, 0] : color === 'poison' ? [138, 201, 38] : [157, 78, 221];
  const ember = color === 'fire' ? ['#FF7B00', '#FFD400', '#E63946'] : color === 'poison' ? ['#8AC926', '#c5f277'] : ['#9D4EDD', '#5a5a66', '#c8b6ff'];
  if (color === 'fire') sfx('whoosh'); else sfx('whiff');
  const total = 90;
  let t = 0;
  return actor((dt, g) => {
    t += dt * sp;
    const th = (t / total) * 1.15 - 0.05, band = 0.045;
    const s = base.data, d = frame.data;
    const edges = [];
    for (let i = 0, p = 0; i < nz.length; i++, p += 4) {
      const v = nz[i];
      if (v < th) { d[p + 3] = 0; } else if (v < th + band) {
        d[p] = glow[0]; d[p + 1] = glow[1]; d[p + 2] = glow[2]; d[p + 3] = 255;
        if (edges.length < 40 && Math.random() < 0.01) edges.push(i);
      } else { d[p] = s[p]; d[p + 1] = s[p + 1]; d[p + 2] = s[p + 2]; d[p + 3] = s[p + 3]; }
    }
    o.putImageData(frame, 0, 0);
    g.save(); g.shadowColor = `rgb(${glow.join(',')})`; g.shadowBlur = 16;
    g.drawImage(off, r.x, r.y, r.w, r.h);
    g.restore();
    for (let k = 0; k < Math.min(6, edges.length); k++) {
      const i = edges[k];
      emit(r.x + (i % w) * 2, r.y + Math.floor(i / w) * 2, 1, { angle: -Math.PI / 2, spread: 0.6, min: 0.5, max: 2.5, g: -0.04, color: ember, shape: color === 'poison' ? 'bubble' : 'dot', size: 2.5, life: 45 });
    }
    return th < 1.05;
  });
}

function shatter(img, r, sp) {
  const ip = { x: r.w * rnd(0.35, 0.65), y: r.h * rnd(0.3, 0.6) };
  const rays = Array.from({ length: 9 }, (_, i) => {
    const a = (i / 9) * Math.PI * 2 + rnd(-0.2, 0.2);
    const pts = [{ x: ip.x, y: ip.y }];
    let len = 0;
    while (len < Math.max(r.w, r.h)) {
      len += rnd(20, 45);
      const aa = a + rnd(-0.25, 0.25);
      pts.push({ x: ip.x + Math.cos(aa) * len, y: ip.y + Math.sin(aa) * len });
    }
    return pts;
  });
  const cols = 4, rows = 5, cw = r.w / cols, ch = r.h / rows;
  const P = [];
  for (let j = 0; j <= rows; j++) for (let i = 0; i <= cols; i++) {
    const inner = i > 0 && i < cols && j > 0 && j < rows;
    P.push({ x: i * cw + (inner ? rnd(-0.35, 0.35) * cw : 0), y: j * ch + (inner ? rnd(-0.35, 0.35) * ch : 0) });
  }
  const at = (i, j) => P[j * (cols + 1) + i];
  const tris = [];
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
    const a = at(i, j), b = at(i + 1, j), c = at(i + 1, j + 1), d = at(i, j + 1);
    if ((i + j) % 2) tris.push([a, b, c], [a, c, d]); else tris.push([a, b, d], [b, c, d]);
  }
  const maxd = Math.hypot(r.w, r.h);
  const st = tris.map((tri) => {
    const c = centroid(tri);
    const vx = c.x - ip.x, vy = c.y - ip.y, dist = Math.hypot(vx, vy) || 1;
    const speed = rnd(4, 10) * (1 - (dist / maxd) * 0.5);
    return { tri, c, vx: (vx / dist) * speed, vy: (vy / dist) * speed - 3, x: 0, y: 0, rot: 0, vr: rnd(-0.15, 0.15), ph: rnd(0, 6) };
  });
  let t = 0, boomed = false;
  return actor((dt, g) => {
    t += dt * sp;
    if (t < 12) {
      g.drawImage(img, r.x, r.y, r.w, r.h);
      const f = t / 12;
      g.save(); g.lineJoin = 'round';
      rays.forEach((pts) => {
        const n = Math.max(2, Math.ceil(pts.length * f));
        g.beginPath();
        pts.slice(0, n).forEach((pt, i) => (i ? g.lineTo(r.x + pt.x, r.y + pt.y) : g.moveTo(r.x + pt.x, r.y + pt.y)));
        g.strokeStyle = '#000'; g.lineWidth = 4; g.stroke();
        g.strokeStyle = '#fff'; g.lineWidth = 1.5; g.stroke();
      });
      g.restore();
      return true;
    }
    if (!boomed) {
      boomed = true;
      screenFlash('#fff', 0.7, 220);
      shake(3);
      sfx('boom');
      emit(r.x + ip.x, r.y + ip.y, 50, { shape: 'debris', color: ['#E63946', '#9A96A0', '#FFD400', '#fff'], min: 4, max: 14, g: 0.35, life: 55, size: 4 });
    }
    const k = t - 12;
    st.forEach((s) => {
      s.vy += 0.45 * dt * sp;
      s.x += s.vx * dt * sp; s.y += s.vy * dt * sp; s.rot += s.vr * dt * sp;
      drawPiece(g, img, r, s.tri, s.c, s.x, s.y, s.rot, Math.cos(k * 0.15 + s.ph), 1 - k / 60);
    });
    return k < 60;
  });
}
