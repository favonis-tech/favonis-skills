'use strict';
// 宣传片引擎：场景时间线、Canvas 2D 图层、WebGL 背景与胶片后期、字幕与章节卡、播放器、逐帧导出接口。
// film.js 在本文件之后执行，只调用这里的全局函数。画面只由时间决定，所以导出与实时播放逐帧一致。

const PI = Math.PI, TAU = Math.PI * 2;
let W = 1920, H = 1080, BPM = 90, BEAT = 60 / 90, BAR = 4 * 60 / 90;
let ctx = null;

const FILM = {
  title: '', tagline: '', size: [1920, 1080], bpm: 90, grade: 'neutral',
  bloom: null, grain: null, vignette: null, tail: 2, poster: null, music: { style: 'cinematic' },
};
const SCENES = [];
const GRADES = {
  neutral: { lift: [0, 0, 0], gain: [1, 1, 1], sat: 1, contrast: 1.04, bloom: .55, grain: .3, vignette: .45 },
  gold: { lift: [.012, .006, 0], gain: [1.05, .99, .86], sat: 1.04, contrast: 1.08, bloom: .85, grain: .35, vignette: .6 },
  teal: { lift: [0, .016, .022], gain: [1.05, 1, .93], sat: 1.06, contrast: 1.07, bloom: .7, grain: .3, vignette: .5 },
  cool: { lift: [0, .006, .02], gain: [.94, 1, 1.07], sat: .96, contrast: 1.05, bloom: .7, grain: .28, vignette: .5 },
  noir: { lift: [0, 0, 0], gain: [1, 1, 1], sat: .12, contrast: 1.18, bloom: .5, grain: .5, vignette: .7 },
};
const BACKDROPS = { nebula: 1, aurora: 2, grid: 3, silk: 4 };
const FONT = {
  serif: '"Noto Serif CJK SC", "Noto Serif SC", "Songti SC", "SimSun", serif',
  sans: '"Noto Sans CJK SC", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  display: '"Cinzel", "Noto Serif CJK SC", serif',
  italic: '"Cormorant Garamond", "Noto Serif CJK SC", serif',
  math: '"STIX Two Text", "Noto Serif CJK SC", serif',
  mono: '"Noto Sans Mono", "Noto Sans CJK SC", "Menlo", "Consolas", monospace',
};
const PARAMS = new URLSearchParams(location.search);
const EXPORT = PARAMS.has('export');
let DURATION = 0;

function film(o) {
  if (SCENES.length) throw new Error('call film() before the first scene()');
  Object.assign(FILM, o);
  [W, H] = FILM.size;
  BPM = FILM.bpm; BEAT = 60 / BPM; BAR = 4 * BEAT;
  if (!GRADES[FILM.grade]) throw new Error(`unknown grade "${FILM.grade}"; use ${Object.keys(GRADES).join(', ')}`);
}
function scene(o) {
  const name = o.name || `scene ${SCENES.length + 1}`;
  if (!(o.bars > 0) || Math.abs(o.bars * 4 - Math.round(o.bars * 4)) > 1e-6) throw new Error(`${name}: bars must be a positive multiple of 0.25 (one beat)`);
  if (typeof o.draw !== 'function') throw new Error(`${name}: draw(t, d) is missing`);
  SCENES.push({ ...o, name });
  return o;
}

// ------------------------------------------------------------------ 数学与缓动
const clamp = (x, a = 0, b = 1) => x < a ? a : x > b ? b : x;
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const fade = (t, a, b, fi = .4, fo = .4) => smooth(a, a + fi, t) * (1 - smooth(b - fo, b, t));
const progress = (t, start, dur) => clamp((t - start) / dur);
const ease = {
  in: t => t * t * t,
  out: t => 1 - (1 - t) ** 3,
  inOut: t => t < .5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2,
  expo: t => t >= 1 ? 1 : 1 - 2 ** (-10 * t),
  back: t => 1 + 2.7 * (t - 1) ** 3 + 1.7 * (t - 1) ** 2,
  sine: t => .5 - .5 * Math.cos(PI * t),
};
function rng(seed = 1) {
  let a = seed | 0;
  return () => { a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
const hash = n => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
function noise(x) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(hash(i), hash(i + 1), u) * 2 - 1; }
function rgba(hex, a = 1) {
  const n = parseInt(hex.slice(1), 16);
  return hex.length === 4
    ? `rgba(${(n >> 8 & 15) * 17},${(n >> 4 & 15) * 17},${(n & 15) * 17},${a})`
    : `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`;
}
const hexRGB = hex => { const n = parseInt(hex.slice(1), 16); return hex.length === 4 ? [(n >> 8 & 15) / 15, (n >> 4 & 15) / 15, (n & 15) / 15] : [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; };

// ------------------------------------------------------------------ 文字
const PIXEL = { scale: 1 };
let track = null;                                                // check 模式下记录每段文字的包围盒

function fontOf(o) { return `${o.style || ''} ${o.weight || 400} ${o.size || 40}px ${o.font || FONT.serif}`; }
function record(str, x0, y0, x1, y1, alpha) {
  if (!track || alpha < .05 || !String(str).trim()) return;
  const m = ctx.getTransform(), s = PIXEL.scale;
  const xs = [], ys = [];
  for (const [x, y] of [[x0, y0], [x1, y0], [x0, y1], [x1, y1]]) { xs.push((m.a * x + m.c * y + m.e) / s); ys.push((m.b * x + m.d * y + m.f) / s); }
  track.push({ text: String(str).slice(0, 40), x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) });
}
function spacing(ls = 0) {
  if ('letterSpacing' in ctx) { ctx.letterSpacing = ls + 'px'; return 0; }
  return ls;                                                     // 不支持 letterSpacing 的浏览器逐字排
}
function measure(str, o = {}) {
  ctx.save(); ctx.font = fontOf(o);
  const manual = spacing(o.ls), w = ctx.measureText(str).width + manual * [...str].length;
  ctx.restore();
  return w;
}
function text(str, x, y, o = {}) {
  str = String(str);
  ctx.save();
  ctx.font = fontOf(o);
  ctx.textAlign = 'left'; ctx.textBaseline = o.base || 'middle';
  const manual = spacing(o.ls), chars = [...str];
  const width = ctx.measureText(str).width + manual * chars.length - (o.ls || 0);
  const align = o.align || 'center';
  const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
  const alpha = o.alpha ?? 1;
  ctx.globalAlpha *= alpha;
  if (o.glow) { ctx.shadowColor = o.glow; ctx.shadowBlur = o.blur ?? 24; }
  ctx.fillStyle = o.color || '#fff';
  if (o.stroke) { ctx.strokeStyle = o.stroke; ctx.lineWidth = o.lineWidth || 2; }
  const put = (s, px) => { if (o.stroke) ctx.strokeText(s, px, y); if (o.fill !== false) ctx.fillText(s, px, y); };
  if (manual) { let px = left; for (const c of chars) { put(c, px); px += ctx.measureText(c).width + manual; } }
  else put(str, left);
  const size = o.size || 40, top = (o.base || 'middle') === 'middle' ? y - size * .6 : (o.base === 'top' ? y : y - size);
  record(str, left, top, left + width, top + size * 1.2, ctx.globalAlpha);
  ctx.restore();
  return width;
}
function lines(str, maxWidth, o = {}) {
  ctx.save(); ctx.font = fontOf(o); spacing(o.ls);
  const out = [];
  for (const para of String(str).split('\n')) {
    // 中日韩按字断行，拉丁文按词断行
    const tokens = para.match(/[⺀-鿿豈-﫿＀-￯][，。、；：！？）」』》]?|[^\s⺀-鿿]+\s*|\s+/g) || [''];
    let line = '';
    for (const tk of tokens) {
      if (line && ctx.measureText(line + tk).width > maxWidth) { out.push(line.trimEnd()); line = tk.trimStart(); }
      else line += tk;
    }
    out.push(line.trimEnd());
  }
  ctx.restore();
  return out;
}
function textBlock(str, x, y, o = {}) {
  const ls = lines(str, o.width || W * .7, o), lh = (o.size || 40) * (o.lineHeight || 1.5);
  const top = y - (ls.length - 1) * lh / 2;
  ls.forEach((l, i) => text(l, x, top + i * lh, o));
  return ls.length * lh;
}
const typed = (str, k) => { const c = [...String(str)]; return c.slice(0, Math.round(clamp(k) * c.length)).join(''); };
function count(value, k, o = {}) {
  const v = value * clamp(k), d = o.decimals || 0;
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: o.group !== false });
}

const METALS = {
  gold: ['#6e4b1b', '#d9b25c', '#fff6dc', '#c99a45', '#7a5520'],
  silver: ['#5d6470', '#c9d0da', '#ffffff', '#aab3c0', '#5d6470'],
  rose: ['#6b2f2a', '#e3a08f', '#fff0ea', '#cf8573', '#6b2f2a'],
};
// 逐字浮现的金属质感标题：t 是从开始浮现起的秒数，sweep 是高光扫过的位置（0–1，默认随时间扫过一次）。
function title(str, x, y, o = {}) {
  const size = o.size || 160, ls = o.ls ?? size * .12, t = o.t ?? 99;
  const font = o.font || FONT.serif, weight = o.weight || 900;
  const chars = [...String(str)], stagger = o.stagger ?? .09, dur = o.dur ?? .9;
  ctx.save();
  ctx.font = `${weight} ${size}px ${font}`; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
  if ('letterSpacing' in ctx) ctx.letterSpacing = '0px';
  const widths = chars.map(c => ctx.measureText(c).width), total = widths.reduce((a, b) => a + b, 0) + ls * (chars.length - 1);
  const left = x - total / 2, metal = METALS[o.metal || 'gold'];
  const sweep = o.sweep ?? clamp((t - chars.length * stagger - .2) / 1.6) * 1.3 - .15;
  let fill = o.color;
  if (!fill) {
    fill = ctx.createLinearGradient(left, y - size / 2, left + total, y + size / 2);
    fill.addColorStop(0, metal[0]); fill.addColorStop(.3, metal[1]);
    if (sweep > .06 && sweep < .94) { fill.addColorStop(sweep - .06, metal[1]); fill.addColorStop(sweep, metal[2]); fill.addColorStop(sweep + .06, metal[3]); }
    fill.addColorStop(.72, metal[3]); fill.addColorStop(1, metal[4]);
  }
  const base = ctx.globalAlpha * (o.alpha ?? 1);
  let px = left;
  chars.forEach((c, i) => {
    const k = ease.out(progress(t, i * stagger, dur));
    if (k > 0) {
      ctx.save();
      ctx.globalAlpha = base * k;
      ctx.translate(px + widths[i] / 2, y + (1 - k) * size * .22);
      const g = 1 + (1 - k) * .12; ctx.scale(g, g);
      if (o.glow !== false) { ctx.shadowColor = o.glow || rgba(metal[2], .45); ctx.shadowBlur = size * .18; }
      ctx.fillStyle = fill; ctx.translate(-(px + widths[i] / 2), -y);
      ctx.fillText(c, px, y);
      ctx.restore();
    }
    px += widths[i] + ls;
  });
  record(str, left, y - size * .6, left + total, y + size * .6, base);
  ctx.restore();
  return total;
}
// RGB 分离加横向错切的故障字，常用于快切镜头
function glitch(str, x, y, o = {}) {
  const size = o.size || 120, seed = (o.seed || 0) + Math.floor((o.t || 0) * 24);
  const base = { ...o, size, glow: null };
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  [['#ff2a4a', -1], ['#22e4ff', 1]].forEach(([c, s], i) => text(str, x + s * size * .03 * hash(seed + i), y, { ...base, color: c, alpha: (o.alpha ?? 1) * .7 }));
  ctx.restore();
  for (let i = 0; i < 4; i++) {
    const h = size * (.12 + .2 * hash(seed * 3 + i)), yy = y - size * .6 + hash(seed * 7 + i) * size * 1.1;
    ctx.save(); ctx.beginPath(); ctx.rect(x - W, yy, 2 * W, h); ctx.clip();
    ctx.translate((hash(seed * 11 + i) - .5) * size * .35, 0);
    text(str, x, y, { ...base, color: o.color || '#fff' });
    ctx.restore();
  }
  text(str, x, y, { ...base, color: o.color || '#fff', alpha: (o.alpha ?? 1) * .85 });
}

// ------------------------------------------------------------------ 光效、粒子与 3D
function glow(x, y, r, color = '#fff', a = 1) {
  if (r <= 0 || a <= 0) return;
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, rgba('#ffffff', a)); g.addColorStop(.15, rgba(color, a * .85)); g.addColorStop(.45, rgba(color, a * .22)); g.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = g; ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
  ctx.restore();
}
function flare(x, y, a = 1, o = {}) {
  if (a <= 0) return;
  const len = o.len || W * .45, color = o.color || '#9fc8ff';
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  const g = ctx.createLinearGradient(x - len, 0, x + len, 0);
  g.addColorStop(0, rgba(color, 0)); g.addColorStop(.5, rgba(color, .55 * a)); g.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = g; ctx.fillRect(x - len, y - 2.5, 2 * len, 5);
  ctx.restore();
  glow(x, y, (o.r || 90), color, a * .8);
}
function rays(x, y, t, o = {}) {
  const n = o.count || 24, a = o.alpha ?? .5, len = o.len || Math.hypot(W, H), color = o.color || '#ffd9a0';
  if (a <= 0) return;
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.translate(x, y); ctx.rotate(t * (o.speed ?? .05));
  const g = ctx.createRadialGradient(0, 0, 0, 0, 0, len);
  g.addColorStop(0, rgba(color, a)); g.addColorStop(.15, rgba(color, a * .4)); g.addColorStop(.5, rgba(color, a * .06)); g.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = g;
  for (let i = 0; i < n; i++) {
    const th = i / n * TAU, w = (o.width || .022) * (.5 + hash(i + 7));
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, len, th - w, th + w); ctx.closePath(); ctx.fill();
  }
  ctx.restore();
}
function stars(t, o = {}) {
  const n = o.count || 260, r = rng(o.seed || 7), speed = o.speed ?? 6, a = o.alpha ?? 1;
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.fillStyle = o.color || '#dfe9ff';
  for (let i = 0; i < n; i++) {
    const depth = .3 + .7 * r(), x = ((r() * W + t * speed * depth) % W + W) % W, y = r() * H;
    const tw = .55 + .45 * Math.sin(t * (1 + 2 * r()) + i), s = (o.size || 2.2) * depth;
    ctx.globalAlpha = a * depth * tw; ctx.fillRect(x, y, s, s);
  }
  ctx.restore();
}
const pointCache = new Map();
// 把文字栅格化后采样成点阵，坐标以文字中心为原点（设计单位）
function textPoints(str, o = {}) {
  const size = o.size || 200, step = o.step || Math.max(3, size / 45), key = `${str}|${size}|${step}|${o.font}|${o.weight}`;
  if (pointCache.has(key)) return pointCache.get(key);
  const c = document.createElement('canvas'), g = c.getContext('2d', { willReadFrequently: true });
  g.font = `${o.weight || 900} ${size}px ${o.font || FONT.serif}`;
  const w = Math.ceil(g.measureText(str).width + size * .4), h = Math.ceil(size * 1.6);
  c.width = w; c.height = h;
  g.font = `${o.weight || 900} ${size}px ${o.font || FONT.serif}`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillStyle = '#fff';
  g.fillText(str, w / 2, h / 2);
  const data = g.getImageData(0, 0, w, h).data, pts = [], r = rng(size + str.length);
  for (let y = 0; y < h; y += step) for (let x = 0; x < w; x += step) {
    const jx = x + (r() - .5) * step * .6, jy = y + (r() - .5) * step * .6;
    if (data[(Math.floor(clamp(jy, 0, h - 1)) * w + Math.floor(clamp(jx, 0, w - 1))) * 4 + 3] > 128) pts.push({ x: jx - w / 2, y: jy - h / 2 });
  }
  pointCache.set(key, pts);
  return pts;
}
function shapePoints(kind, n = 600, o = {}) {
  const r = rng(o.seed || 3), R = o.r || 300, pts = [];
  for (let i = 0; i < n; i++) {
    const u = i / n;
    if (kind === 'ring') { const a = u * TAU; pts.push({ x: Math.cos(a) * R, y: Math.sin(a) * R }); }
    else if (kind === 'spiral') { const a = u * TAU * 6, rr = R * Math.sqrt(u); pts.push({ x: Math.cos(a) * rr, y: Math.sin(a) * rr }); }
    else if (kind === 'disc') { const a = r() * TAU, rr = R * Math.sqrt(r()); pts.push({ x: Math.cos(a) * rr, y: Math.sin(a) * rr }); }
    else throw new Error(`unknown shape "${kind}"; use ring, spiral or disc`);
  }
  return pts;
}
// 粒子从散开处飞入目标点阵；t 为开始后的秒数，reverse 为炸散
function assemble(points, t, o = {}) {
  if (t < 0) return;
  const x0 = o.x ?? W / 2, y0 = o.y ?? H / 2, dur = o.dur ?? 1.6, stagger = o.stagger ?? .8, spread = o.spread ?? W * .7;
  const size = o.size ?? 2.4, r = rng(o.seed || 11), color = o.color || '#ffffff';
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.fillStyle = color;
  for (const p of points) {
    // 每个粒子的随机量一次取完，跳过不可见粒子时后面粒子的随机序列才不会错位
    const delay = r() * stagger, a = r() * TAU, d = spread * (.35 + .65 * r()), w = r() - .5, sx = Math.cos(a) * d, sy = Math.sin(a) * d;
    let k = ease.inOut(progress(t, delay, dur));
    if (o.reverse) k = 1 - k;
    if (k <= 0) continue;
    const wob = Math.sin(k * PI) * 40 * w;
    const px = lerp(sx, p.x, k) + wob, py = lerp(sy, p.y, k) - wob, s = size * (1.8 - .8 * k);
    ctx.globalAlpha = (o.alpha ?? 1) * clamp(k * 3) * (.45 + .55 * k);
    ctx.fillRect(x0 + px - s / 2, y0 + py - s / 2, s, s);
  }
  ctx.restore();
}
function rot3(p, yaw = 0, pitch = 0, roll = 0) {
  let [x, y, z] = p;
  let c = Math.cos(yaw), s = Math.sin(yaw); [x, z] = [c * x + s * z, -s * x + c * z];
  c = Math.cos(pitch); s = Math.sin(pitch); [y, z] = [c * y - s * z, s * y + c * z];
  c = Math.cos(roll); s = Math.sin(roll); [x, y] = [c * x - s * y, s * x + c * y];
  return [x, y, z];
}
// 透视投影：世界单位 → 屏幕设计单位；k 是透视缩放，用于点大小与景深透明度
function project(p, cam = {}) {
  const [x, y, z] = rot3(p, cam.yaw, cam.pitch, cam.roll), dist = cam.dist ?? 6, f = cam.f ?? Math.min(W, H) * .9;
  const k = f / (dist + z);
  return { x: (cam.x ?? W / 2) + x * k, y: (cam.y ?? H / 2) - y * k, k, z };
}
const POLY = (() => {
  const g = (1 + Math.sqrt(5)) / 2, edges = (v, len) => {
    const e = []; for (let i = 0; i < v.length; i++) for (let j = i + 1; j < v.length; j++) if (Math.abs(Math.hypot(...v[i].map((c, k) => c - v[j][k])) - len) < 1e-3) e.push([i, j]); return e;
  };
  const make = (v, len) => { const s = 1 / Math.max(...v.map(p => Math.hypot(...p))); const vs = v.map(p => p.map(c => c * s)); return { vertices: vs, edges: edges(v, len) }; };
  const ico = []; for (const a of [-1, 1]) for (const b of [-g, g]) ico.push([0, a, b], [a, b, 0], [b, 0, a]);
  const cube = []; for (const a of [-1, 1]) for (const b of [-1, 1]) for (const c of [-1, 1]) cube.push([a, b, c]);
  return {
    tetra: make([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], Math.sqrt(8)),
    cube: make(cube, 2),
    octa: make([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], Math.SQRT2),
    icosa: make(ico, 2),
  };
})();
// 线框多面体：近处的棱更亮更粗，顶点带光点
function wire(shape, cam = {}, o = {}) {
  const sc = o.scale ?? 1, pts = shape.vertices.map(v => project(v.map(c => c * sc), cam)), a = o.alpha ?? 1, color = o.color || '#bfe3ff';
  const near = p => clamp(.5 - p.z / (2 * sc)), k0 = (cam.f ?? Math.min(W, H) * .9) / (cam.dist ?? 6);
  ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.strokeStyle = color; ctx.lineCap = 'round';
  for (const [i, j] of shape.edges) {
    const depth = .3 + .7 * (near(pts[i]) + near(pts[j])) / 2;
    ctx.globalAlpha = a * depth; ctx.lineWidth = (o.width || 2.2) * (.6 + .6 * depth);
    ctx.beginPath(); ctx.moveTo(pts[i].x, pts[i].y); ctx.lineTo(pts[j].x, pts[j].y); ctx.stroke();
  }
  ctx.restore();
  if (o.nodes !== false) for (const p of pts) glow(p.x, p.y, (o.nodeSize || 26) * p.k / k0, color, a * (.4 + .6 * near(p)));
  return pts;
}

// ------------------------------------------------------------------ WebGL：背景与后期
const gl = (() => {
  const c = document.createElement('canvas');
  const g = c.getContext('webgl2', { preserveDrawingBuffer: true, antialias: false, alpha: false, premultipliedAlpha: false });
  if (!g) return null;
  g.halfFloat = !!g.getExtension('EXT_color_buffer_float') || !!g.getExtension('EXT_color_buffer_half_float');
  return g;
})();
const VS = `#version 300 es
in vec2 p; out vec2 uv; void main(){ uv = p * .5 + .5; gl_Position = vec4(p, 0., 1.); }`;
const HEAD = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
// 整数哈希：浮点 fract 哈希在大坐标下精度不足，颗粒会排成竖条
float hash(vec2 p){ uvec2 q = uvec2(ivec2(floor(p)) + 32768) * uvec2(1597334673u, 3812015801u);
  uint n = (q.x ^ q.y) * 1597334673u; n ^= n >> 16; n *= 2246822519u; n ^= n >> 13; return float(n) * (1. / 4294967295.); }
float noise(vec2 p){ vec2 i = floor(p), f = fract(p); f = f * f * (3. - 2. * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y); }
float fbm(vec2 p){ float s = 0., a = .5; for (int i = 0; i < 5; i++){ s += a * noise(p); p = p * 2.03 + vec2(3.1, 1.7); a *= .5; } return s; }
`;
const FS_BACKDROP = HEAD + `
uniform int kind; uniform float time, amount, speed, aspect; uniform vec3 tint, tint2;
vec3 nebula(vec2 p){
  float t = time * .03 * speed;
  vec2 q = vec2(fbm(p * 1.2 + t), fbm(p * 1.2 + vec2(5.2, 1.3) - t));
  float n = fbm(p * 1.2 + 2.2 * q + vec2(t * 1.5, 0.));
  vec3 c = vec3(.006, .008, .02);
  c += tint * smoothstep(.38, 1.02, n) * 1.5;
  c += tint2 * .55 * pow(clamp(q.y - .22, 0., 1.), 2.4);
  float h = hash(floor(gl_FragCoord.xy));
  c += vec3(.85, .9, 1.) * step(.9975, h) * (.5 + .5 * sin(time * 2. + h * 400.));
  return c;
}
vec3 aurora(vec2 p){
  vec3 c = vec3(.004, .008, .018) + tint2 * .06 * (1. - uv.y);
  for (int i = 0; i < 3; i++){
    float fi = float(i), x = p.x * 1.1 + fi * 1.9;
    float w = sin(x * 1.4 + time * .22 * speed + fi * 2.) * .16 + (fbm(vec2(x * .7, time * .04 * speed + fi)) - .5) * .5;
    float d = p.y - .12 - w + fi * .1;
    float band = exp(-d * d * 22.) * (d > 0. ? 1. : exp(d * 6.));
    float streak = .45 + .55 * fbm(vec2(x * 9., time * .15 * speed + fi));
    c += mix(tint, tint2, fi * .5) * band * streak * .6;
  }
  float h = hash(floor(gl_FragCoord.xy));
  c += vec3(.8, .9, 1.) * step(.998, h) * smoothstep(-.1, .4, p.y) * .7;
  return c;
}
vec3 grid(vec2 p){
  float hz = -.06;
  vec3 c = vec3(.008, .006, .018) + tint2 * .3 * exp(-abs(p.y - hz) * 7.) + tint2 * .05 * smoothstep(hz, .5, p.y);
  if (p.y < hz){
    float z = .3 / (hz - p.y), x = p.x * z, zz = z + time * speed * .5;
    vec2 g = vec2(x, zz), f = abs(fract(g) - .5), w = fwidth(g) * 1.2;
    float line = max(1. - smoothstep(0., w.x, .5 - f.x), 1. - smoothstep(0., w.y, .5 - f.y));
    c += tint * line * exp(-z * .12) * 1.2;
  } else {
    float h = hash(floor(gl_FragCoord.xy));
    c += vec3(.8, .85, 1.) * step(.9982, h) * .8;
  }
  return c;
}
vec3 silk(vec2 p){
  float t = time * .05 * speed;
  float n = fbm(p * .9 + vec2(t, -t * .7));
  float w = sin((p.x * 1.1 + p.y * 1.9 + n * 3.2 + t * 2.) * 2.1);
  vec3 c = mix(tint2 * .12, tint * .85, pow(w * .5 + .5, 3.));
  c += tint * .3 * pow(1. - abs(w), 10.);
  return c * (.55 + .45 * smoothstep(1.2, 0., length(p)));
}
void main(){
  vec2 p = (uv - .5) * vec2(aspect, 1.);
  vec3 c = kind == 1 ? nebula(p) : kind == 2 ? aurora(p) : kind == 3 ? grid(p) : silk(p);
  o = vec4(c * amount, 1.);
}`;
const FS_ACCUM = HEAD + `uniform sampler2D src; uniform float weight; void main(){ o = vec4(texture(src, uv).rgb * weight, 1.); }`;
const FS_BRIGHT = HEAD + `uniform sampler2D src; uniform vec2 texel; uniform float threshold;
void main(){
  vec3 c = .25 * (texture(src, uv + texel * vec2(-1, -1)).rgb + texture(src, uv + texel * vec2(1, -1)).rgb + texture(src, uv + texel * vec2(-1, 1)).rgb + texture(src, uv + texel).rgb);
  float l = max(c.r, max(c.g, c.b));
  o = vec4(c * smoothstep(threshold, threshold + .35, l), 1.);
}`;
const FS_DOWN = HEAD + `uniform sampler2D src; uniform vec2 texel;
void main(){
  vec3 s = texture(src, uv).rgb * 4.;
  s += texture(src, uv - texel).rgb + texture(src, uv + texel).rgb + texture(src, uv + vec2(texel.x, -texel.y)).rgb + texture(src, uv - vec2(texel.x, -texel.y)).rgb;
  o = vec4(s / 8., 1.);
}`;
const FS_UP = HEAD + `uniform sampler2D src; uniform vec2 texel;
void main(){
  vec3 s = texture(src, uv + vec2(-texel.x * 2., 0.)).rgb + texture(src, uv + vec2(texel.x * 2., 0.)).rgb
    + texture(src, uv + vec2(0., -texel.y * 2.)).rgb + texture(src, uv + vec2(0., texel.y * 2.)).rgb;
  s += (texture(src, uv + texel).rgb + texture(src, uv - texel).rgb + texture(src, uv + vec2(texel.x, -texel.y)).rgb + texture(src, uv - vec2(texel.x, -texel.y)).rgb) * 2.;
  o = vec4(s / 12., 1.);
}`;
const FS_COMPOSE = HEAD + `uniform sampler2D src, bloomTex; uniform float bloom, grain, vignette, sat, contrast, exposure, frame, aspect, aberration;
uniform vec3 lift, gain;
void main(){
  vec2 d = uv - .5;
  float ab = aberration * dot(d, d);
  vec3 c = vec3(texture(src, uv - d * ab).r, texture(src, uv).g, texture(src, uv + d * ab).b);
  c += texture(bloomTex, uv).rgb * bloom;
  c = mix(c, .8 + .2 * (1. - exp(-(c - .8) / .2)), step(.8, c));        // 高光柔和压缩，避免泛光叠加后硬截断
  c = gain * (c + lift * (1. - c));
  float l = dot(c, vec3(.2126, .7152, .0722));
  c = mix(vec3(l), c, sat);
  c = mix(c, c * c * (3. - 2. * c), contrast - 1.);
  float r = length(d * vec2(aspect, 1.)) / length(vec2(aspect, 1.) * .5);
  c *= 1. - vignette * .55 * pow(r, 2.4);
  c *= exposure;
  c += (hash(gl_FragCoord.xy + frame * vec2(17.3, 41.9)) - .5) * grain * .09 * (1. - l * .6);
  o = vec4(clamp(c, 0., 1.), 1.);
}`;

const GL = {};
function glInit() {
  if (!gl) return false;
  const compile = (type, src) => {
    const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error('shader: ' + gl.getShaderInfoLog(s));
    return s;
  };
  const vs = compile(gl.VERTEX_SHADER, VS);
  const program = fs => {
    const p = gl.createProgram(); gl.attachShader(p, vs); gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs));
    gl.bindAttribLocation(p, 0, 'p'); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error('program: ' + gl.getProgramInfoLog(p));
    const u = {}, n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) { const name = gl.getActiveUniform(p, i).name; u[name] = gl.getUniformLocation(p, name); }
    return { p, u };
  };
  GL.backdrop = program(FS_BACKDROP); GL.accum = program(FS_ACCUM); GL.bright = program(FS_BRIGHT);
  GL.down = program(FS_DOWN); GL.up = program(FS_UP); GL.compose = program(FS_COMPOSE);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
  GL.layerTex = texture(1, 1, false);
  return true;
}
function texture(w, h, float) {
  const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
  const hf = float && gl.halfFloat;
  gl.texImage2D(gl.TEXTURE_2D, 0, hf ? gl.RGBA16F : gl.RGBA8, w, h, 0, gl.RGBA, hf ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE, null);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  return t;
}
function target(w, h) {
  const tex = texture(w, h, true), fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo); gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  return { tex, fbo, w, h };
}
function glResize(w, h) {
  gl.canvas.width = w; gl.canvas.height = h;
  for (const k of ['acc', ...[0, 1, 2, 3, 4].map(i => 'b' + i)]) if (GL[k]) { gl.deleteTexture(GL[k].tex); gl.deleteFramebuffer(GL[k].fbo); }
  GL.acc = target(w, h);
  for (let i = 0, d = 2; i < 5; i++, d *= 2) GL['b' + i] = target(Math.max(1, Math.round(w / d)), Math.max(1, Math.round(h / d)));
}
function pass(prog, dst, uniforms, w, h) {
  gl.useProgram(prog.p);
  gl.bindFramebuffer(gl.FRAMEBUFFER, dst ? dst.fbo : null);
  gl.viewport(0, 0, w ?? dst.w, h ?? dst.h);
  let unit = 0;
  for (const [k, v] of Object.entries(uniforms)) {
    const loc = prog.u[k]; if (loc == null) continue;
    if (v instanceof WebGLTexture) { gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, v); gl.uniform1i(loc, unit++); }
    else if (k === 'kind') gl.uniform1i(loc, v);
    else if (Array.isArray(v)) gl[`uniform${v.length}fv`](loc, v);
    else gl.uniform1f(loc, v);
  }
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}

// ------------------------------------------------------------------ 画面管线
const view = document.createElement('canvas');
const sctx = view.getContext('2d');
const layer = document.createElement('canvas');
const lctx = layer.getContext('2d');
const bg = document.createElement('canvas');
const bgctx = bg.getContext('2d');
let hasGL = false;

function setScale(s) {
  PIXEL.scale = s;
  const w = Math.round(W * s), h = Math.round(H * s);
  if (view.width === w && view.height === h) return;
  view.width = layer.width = w; view.height = layer.height = h;
  bg.width = Math.max(1, Math.round(w / 2)); bg.height = Math.max(1, Math.round(h / 2));
  if (hasGL) glResize(w, h);
}
function layout() {
  if (!SCENES.length) throw new Error('the film has no scenes');
  let t = 0;
  for (const s of SCENES) {
    s.t0 = t; s.d = s.bars * BAR; t += s.d;
    s.hitList = (s.hits || []).map(([at, k = 1]) => [s.t0 + at, k]);
  }
  DURATION = t + (FILM.tail ?? 2);
}
const sceneAt = T => { let sc = SCENES[0]; for (const s of SCENES) if (T >= s.t0) sc = s; return sc; };
const resolve = (v, t, d) => typeof v === 'function' ? v(t, d) : v;

function camera(sc, t) {
  const d = sc.d, c = sc.camera ?? 'push', p = clamp(t / d);
  if (typeof c === 'function') return { x: 0, y: 0, z: 1, r: 0, ...c(t, d) };
  if (c === 'still') return { x: 0, y: 0, z: 1, r: 0 };
  const drift = { x: 10 * Math.sin(t * .21), y: 6 * Math.sin(t * .17 + 1), r: 0 };
  if (c === 'push') return { ...drift, z: 1 + .045 * p };
  if (c === 'pull') return { ...drift, z: 1.05 - .045 * p };
  if (c === 'arc') return { ...drift, z: 1 + .04 * Math.sin(PI * p) };
  if (c === 'drift') return { ...drift, z: 1.02 };
  throw new Error(`${sc.name}: unknown camera "${c}"`);
}
function shakeAt(T) {
  let s = 0;
  for (const sc of SCENES) for (const [th, k] of sc.hitList) if (T >= th && T < th + 1.5) s += 16 * k * Math.exp(-(T - th) * 6);
  return s;
}
function flashAt(T) {
  let f = 0;
  for (const sc of SCENES) for (const [th, k] of sc.hitList) if (T >= th && T < th + 1.5) f += .75 * k * Math.exp(-(T - th) * 5);
  return Math.min(.9, f);
}
function sceneFade(sc, lt) {
  const [fi, fo] = sc.fade ?? [.35, .35];
  return (fi > 0 ? smooth(0, fi, lt) : 1) * (fo > 0 ? 1 - smooth(sc.d - fo, sc.d, lt) : 1);
}

// 背景每帧只算一次（运动模糊的子帧共用），在半分辨率下渲染后放大
function renderBackdrop(sc, lt) {
  const spec = resolve(sc.backdrop, lt, sc.d);
  if (!spec) return false;
  const o = typeof spec === 'string' ? { kind: spec } : spec;
  if (!BACKDROPS[o.kind]) throw new Error(`${sc.name}: unknown backdrop "${o.kind}"; use ${Object.keys(BACKDROPS).join(', ')}`);
  const defaults = { nebula: ['#2a4bd7', '#b0408f'], aurora: ['#2be0a8', '#5a4bff'], grid: ['#ff3fb4', '#6a3cff'], silk: ['#4f7cff', '#0b1230'] }[o.kind];
  if (!hasGL) { bgctx.fillStyle = rgba(o.tint2 || defaults[1], .25); bgctx.fillRect(0, 0, bg.width, bg.height); return true; }
  pass(GL.backdrop, null, {
    kind: BACKDROPS[o.kind], time: (o.time ?? lt) + (o.seed || 0) * 37, amount: o.amount ?? 1, speed: o.speed ?? 1, aspect: W / H,
    tint: hexRGB(o.tint || defaults[0]), tint2: hexRGB(o.tint2 || defaults[1]),
  }, bg.width, bg.height);
  bgctx.drawImage(gl.canvas, 0, gl.canvas.height - bg.height, bg.width, bg.height, 0, 0, bg.width, bg.height);
  return true;
}
function drawLayer(sc, T, withBackdrop, jitter = [0, 0]) {
  const lt = T - sc.t0, s = PIXEL.scale;
  ctx = lctx;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none'; ctx.shadowBlur = 0;
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, layer.width, layer.height);
  if (withBackdrop) ctx.drawImage(bg, 0, 0, layer.width, layer.height);
  const cam = camera(sc, lt), sh = shakeAt(T);
  ctx.setTransform(s, 0, 0, s, 0, 0);
  ctx.translate(W / 2 + jitter[0] + cam.x + (sh > .3 ? Math.sin(T * 91) * sh : 0), H / 2 + jitter[1] + cam.y + (sh > .3 ? Math.cos(T * 73) * sh : 0));
  ctx.rotate(cam.r || 0); ctx.scale(cam.z, cam.z); ctx.translate(-W / 2, -H / 2);
  ctx.save();
  try { sc.draw(lt, sc.d, T); }
  catch (e) { e.message = `${sc.name} at ${lt.toFixed(2)}s (film ${T.toFixed(2)}s): ${e.message}`; throw e; }
  finally { ctx.restore(); }
}
const JITTER = [[0, 0], [.25, -.25], [-.25, .25], [.375, .125], [-.125, -.375], [.125, .375], [-.375, -.125], [0, .5]];
let frameNo = 0;
function renderFrame(T, samples = 1, fps = 30) {
  T = clamp(T, 0, DURATION - 1e-4);
  const sc = sceneAt(T), lt = T - sc.t0, K = Math.max(1, Math.min(8, samples > 1 ? (sc.blur ?? samples) : 1));
  const withBackdrop = renderBackdrop(sc, lt);
  const grade = { ...GRADES[FILM.grade] };
  for (const k of ['bloom', 'grain', 'vignette']) if (FILM[k] != null) grade[k] = FILM[k];
  if (sc.grade) Object.assign(grade, sc.grade);
  const exposure = sceneFade(sc, lt);
  if (hasGL) {
    gl.disable(gl.BLEND);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    for (let k = 0; k < K; k++) {
      let tk = K > 1 ? T + ((k + .5) / K - .5) * .5 / fps : T;
      if (sceneAt(tk) !== sc || tk < 0) tk = T;
      drawLayer(sc, tk, withBackdrop, K > 1 ? JITTER[k] : [0, 0]);
      gl.bindTexture(gl.TEXTURE_2D, GL.layerTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, layer);
      if (k === 1) { gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE); }
      pass(GL.accum, GL.acc, { src: GL.layerTex, weight: 1 / K });
    }
    gl.disable(gl.BLEND);
    const b = [0, 1, 2, 3, 4].map(i => GL['b' + i]);
    pass(GL.bright, b[0], { src: GL.acc.tex, texel: [1 / GL.acc.w, 1 / GL.acc.h], threshold: grade.threshold ?? .62 });
    for (let i = 1; i < 5; i++) pass(GL.down, b[i], { src: b[i - 1].tex, texel: [1 / b[i - 1].w, 1 / b[i - 1].h] });
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE);
    for (let i = 3; i >= 0; i--) pass(GL.up, b[i], { src: b[i + 1].tex, texel: [.5 / b[i + 1].w, .5 / b[i + 1].h] });
    gl.disable(gl.BLEND);
    pass(GL.compose, null, {
      src: GL.acc.tex, bloomTex: b[0].tex, bloom: grade.bloom, grain: grade.grain, vignette: grade.vignette, sat: grade.sat, contrast: grade.contrast,
      exposure, frame: frameNo++ % 997, aspect: W / H, aberration: grade.aberration ?? .012, lift: grade.lift, gain: grade.gain,
    }, view.width, view.height);
    sctx.setTransform(1, 0, 0, 1, 0, 0); sctx.globalAlpha = 1; sctx.globalCompositeOperation = 'copy';
    sctx.drawImage(gl.canvas, 0, 0); sctx.globalCompositeOperation = 'source-over';
  } else {
    drawLayer(sc, T, withBackdrop);
    sctx.setTransform(1, 0, 0, 1, 0, 0); sctx.globalCompositeOperation = 'copy'; sctx.drawImage(layer, 0, 0);
    sctx.globalCompositeOperation = 'source-over';
    if (exposure < 1) { sctx.fillStyle = `rgba(0,0,0,${1 - exposure})`; sctx.fillRect(0, 0, view.width, view.height); }
  }
  overlays(T, sc);
}

// ------------------------------------------------------------------ 叠加层：遮幅、章节卡、字幕、闪白
let SUBS = [];
function letterboxAt(T, sc) {
  const i = SCENES.indexOf(sc), cur = sc.letterbox ? 1 : 0, prev = i > 0 && SCENES[i - 1].letterbox ? 1 : cur;
  return lerp(prev, cur, ease.inOut(progress(T - sc.t0, 0, .9)));
}
function overlays(T, sc) {
  ctx = sctx;
  const s = PIXEL.scale;
  sctx.setTransform(s, 0, 0, s, 0, 0);
  const lb = letterboxAt(T, sc) * (H - W / 2.39) / 2;
  if (lb > .5) { sctx.fillStyle = '#000'; sctx.fillRect(0, 0, W, lb); sctx.fillRect(0, H - lb, W, lb); }
  chapter(sc, T - sc.t0);
  subtitles(T);
  const f = flashAt(T);
  if (f > .01) { sctx.fillStyle = `rgba(255,248,235,${f})`; sctx.fillRect(0, 0, W, H); }
}
function chapter(sc, lt) {
  if (!sc.chapter) return;
  const a = fade(lt, .5, Math.min(sc.d - .2, 5), .6, .8); if (a <= 0) return;
  const [n, main, sub] = sc.chapter, u = Math.min(W, H) / 1080, x = W * .047, y = Math.min(W, H) * .085;
  const slide = (1 - ease.out(progress(lt, .5, .8))) * -30 * u;
  const nw = text(n, x + slide, y, { font: FONT.display, weight: 700, size: 46 * u, color: '#e2bd6b', alpha: a, align: 'left' });
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = '#e2bd6b'; ctx.fillRect(x + nw + 20 * u + slide, y - 26 * u, 2 * u, 52 * u); ctx.restore();
  text(main, x + nw + 42 * u + slide, y - (sub ? 8 : 0) * u, { size: 36 * u, weight: 700, color: '#fff', alpha: a, align: 'left' });
  if (sub) text(sub, x + nw + 44 * u + slide, y + 30 * u, { font: FONT.display, size: 16 * u, ls: 5 * u, color: '#cdb88e', alpha: a, align: 'left' });
}
function subtitles(T) {
  const u = Math.min(W, H) / 1080;
  for (const sb of SUBS) {
    if (T < sb.start - .3 || T > sb.end + .3) continue;
    const a = fade(T, sb.start, sb.end, .25, .3); if (a <= 0) continue;
    const g = ctx.createLinearGradient(0, H - 200 * u, 0, H);
    g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, `rgba(0,0,0,${.55 * a})`);
    ctx.fillStyle = g; ctx.fillRect(0, H - 200 * u, W, 200 * u);
    const main = { size: 42 * u, weight: 700, color: '#fff', alpha: a, glow: 'rgba(0,0,0,.9)', blur: 12 * u, ls: 2 * u, width: W * .86 };
    const second = { font: FONT.italic, style: 'italic', weight: 500, size: 30 * u, color: '#ddd5c4', alpha: a * .9, glow: 'rgba(0,0,0,.9)', blur: 8 * u, width: W * .86 };
    const mainLines = lines(sb.text, main.width, main), secondLines = sb.second ? lines(sb.second, second.width, second) : [];
    let y = H - 48 * u - secondLines.length * 40 * u - (mainLines.length - 1) * 54 * u - 30 * u;
    for (const l of mainLines) { text(l, W / 2, y, main); y += 54 * u; }
    y += 2 * u;
    for (const l of secondLines) { text(l, W / 2, y, second); y += 40 * u; }
  }
}

// ------------------------------------------------------------------ 字体、检查与导出接口
let fontsReady = false, started = false;
function cues() {
  const out = [];
  for (const sc of SCENES) {
    for (const [t, name, opts] of sc.sfx || []) out.push({ t: +(sc.t0 + t).toFixed(4), name, ...(opts || {}), scene: sc.name });
  }
  return out.sort((a, b) => a.t - b.t);
}
function info() {
  return {
    title: FILM.title, tagline: FILM.tagline, size: [W, H], bpm: BPM, duration: DURATION, tail: FILM.tail ?? 2, music: FILM.music, grade: FILM.grade,
    poster: posterTime(), webgl: hasGL,
    scenes: SCENES.map(s => ({
      name: s.name, start: s.t0, end: s.t0 + s.d, bars: s.bars, music: s.music ?? null,
      hits: (s.hits || []).map(([t, k = 1]) => [s.t0 + t, k]),
    })),
    subs: SUBS.map(({ start, end, text, second, scene }) => ({ start, end, text, second, scene })),
    cues: cues(),
  };
}
// check 用：在给定时刻只画图层（不含背景、后期和叠加层），记录越界或压住字幕的文字，
// 并给出与上一个采样相比变化了的像素比例，用来找长时间不动的画面。
const SIG = document.createElement('canvas');
SIG.width = 96; SIG.height = 54;
const sigctx = SIG.getContext('2d', { willReadFrequently: true });
const scanSeen = new Set();
let lastSig = null, lastScene = null;
function signature() {
  sigctx.drawImage(layer, 0, 0, SIG.width, SIG.height);
  const d = sigctx.getImageData(0, 0, SIG.width, SIG.height).data, out = new Uint8Array(SIG.width * SIG.height);
  for (let i = 0; i < out.length; i++) out[i] = (d[i * 4] * 54 + d[i * 4 + 1] * 183 + d[i * 4 + 2] * 19) >> 8;
  return out;
}
function scan(times) {
  const issues = [], motion = [], u = Math.min(W, H) / 1080;
  for (const T of times) {
    const sc = sceneAt(T);
    track = [];
    drawLayer(sc, T, false);
    const sig = signature();
    let changed = null;
    if (lastSig && lastScene === sc) { changed = 0; for (let i = 0; i < sig.length; i++) if (Math.abs(sig[i] - lastSig[i]) > 6) changed++; changed /= sig.length; }
    motion.push(changed);
    lastSig = sig; lastScene = sc;
    const subOn = SUBS.some(sb => T >= sb.start && T <= sb.end), band = H - (SUBS.length ? 150 * u : 0);
    for (const b of track) {
      const key = `${sc.name}|${b.text}`;
      if (scanSeen.has(key)) continue;
      const out = b.x0 < -2 || b.x1 > W + 2 || b.y0 < -2 || b.y1 > H + 2;
      const edge = b.x0 < W * .03 || b.x1 > W * .97 || b.y0 < H * .03 || b.y1 > H * .97;
      if (out || edge) { scanSeen.add(key); issues.push({ kind: out ? 'clipped' : 'edge', scene: sc.name, at: +T.toFixed(2), text: b.text, box: [b.x0, b.y0, b.x1, b.y1].map(Math.round) }); }
      else if (subOn && b.y1 > band) { scanSeen.add(key); issues.push({ kind: 'under-subtitle', scene: sc.name, at: +T.toFixed(2), text: b.text, box: [b.x0, b.y0, b.x1, b.y1].map(Math.round) }); }
    }
    track = null;
  }
  return { issues, motion };
}
const posterTime = () => clamp(FILM.poster ?? (SCENES[1] ? SCENES[1].t0 + SCENES[1].d * .6 : DURATION * .3), 0, DURATION - .01);

window.PROMO = {
  ready: () => started && fontsReady,
  info,
  scan,
  frame(t, o = {}) {
    if (o.scale && o.scale !== PIXEL.scale) setScale(o.scale);
    renderFrame(t, o.samples || 1, o.fps || 30);
    return view.toDataURL('image/jpeg', o.quality ?? .92);
  },
};

function start() {
  layout();
  SUBS = SCENES.flatMap(s => (s.subs || []).map(sub => {
    const [a, b, t1, t2] = sub;
    if (!(b > a) || typeof t1 !== 'string') throw new Error(`${s.name}: each subtitle is [start, end, text, secondLine?] with end > start`);
    return { start: s.t0 + a, end: s.t0 + b, text: t1, second: t2, scene: s.name };
  }));
  if (EXPORT) document.body.classList.add('export');
  hasGL = glInit();
  setScale(+(PARAMS.get('scale') || 1));
  document.title = FILM.title || 'Promo';
  started = true;
  Promise.all([...document.fonts].map(f => f.load().catch(() => {}))).then(() => document.fonts.ready).then(() => {
    fontsReady = true;
    if (!EXPORT) player();
  });
}

// ------------------------------------------------------------------ 播放器
function player() {
  const $ = id => document.getElementById(id);
  const stage = $('stage'), audio = $('audio'), cover = $('cover'), controls = $('controls'), toggle = $('toggle'), bar = $('bar'), fill = $('fill');
  stage.appendChild(view);
  $('cover-title').textContent = FILM.title; $('cover-tagline').textContent = FILM.tagline || '';
  const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  $('duration').textContent = fmt(DURATION);
  if (window.PROMO_AUDIO) audio.src = window.PROMO_AUDIO;
  const fs = $('fullscreen');
  if (!document.fullscreenEnabled) fs.remove();
  else fs.onclick = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {});

  // 渲染分辨率跟随显示尺寸，避免小窗口里白算 1080p
  const fit = () => {
    const r = stage.getBoundingClientRect(), s = clamp(r.width * devicePixelRatio / W, .35, 1);
    if (Math.abs(s - PIXEL.scale) / PIXEL.scale > .1) { setScale(s); draw(); }
  };
  let playing = false, clock0 = 0, offset = 0, useAudio = !!window.PROMO_AUDIO, hideTimer = 0, now = 0, failed = false;
  const time = () => playing ? (useAudio ? audio.currentTime : offset + (performance.now() - clock0) / 1000) : offset;
  function draw() {
    // 开播前画面停在海报帧，进度仍从 0 开始
    try { renderFrame(document.body.classList.contains('started') ? now : posterTime()); }
    catch (e) { if (!failed) console.error(e); failed = true; }
    fill.style.width = `${now / DURATION * 100}%`; $('time').textContent = fmt(now);
  }
  function loop() {
    if (!playing) return;
    now = time();
    if (now >= DURATION - .02) { now = DURATION - .02; pause(); draw(); controls.classList.add('show'); return; }
    draw();
    requestAnimationFrame(loop);
  }
  function play() {
    if (offset >= DURATION - .1) offset = 0;
    playing = true; document.body.classList.add('playing');
    if (useAudio) { audio.currentTime = offset; audio.play().catch(() => { useAudio = false; clock0 = performance.now(); }); }
    clock0 = performance.now();
    requestAnimationFrame(loop);
  }
  function pause() { offset = time(); playing = false; document.body.classList.remove('playing'); if (useAudio) audio.pause(); }
  function seek(t) {
    offset = now = clamp(t, 0, DURATION - .02);
    if (useAudio) audio.currentTime = offset;
    clock0 = performance.now();
    if (!playing) draw();
  }
  function poke() { controls.classList.add('show'); clearTimeout(hideTimer); hideTimer = setTimeout(() => playing && controls.classList.remove('show'), 2200); }
  cover.onclick = () => { cover.remove(); document.body.classList.add('started'); play(); poke(); };
  toggle.onclick = () => playing ? pause() : play();
  let dragging = false;
  const scrub = e => { const r = bar.getBoundingClientRect(); seek(clamp((e.clientX - r.left) / r.width) * DURATION); };
  bar.addEventListener('pointerdown', e => { dragging = true; bar.setPointerCapture(e.pointerId); scrub(e); });
  bar.addEventListener('pointermove', e => dragging && scrub(e));
  bar.addEventListener('pointerup', () => { dragging = false; });
  addEventListener('pointermove', poke);
  addEventListener('keydown', e => {
    if (document.getElementById('cover')) { if (e.code === 'Space' || e.code === 'Enter') { e.preventDefault(); cover.click(); } return; }
    if (e.code === 'Space') { e.preventDefault(); playing ? pause() : play(); }
    else if (e.code === 'ArrowRight' || e.code === 'ArrowLeft') seek(time() + (e.code === 'ArrowRight' ? 5 : -5));
    else if (e.code === 'KeyF' && document.getElementById('fullscreen')) document.getElementById('fullscreen').click();
    poke();
  });
  new ResizeObserver(fit).observe(stage);
  fit();
  draw();
}
