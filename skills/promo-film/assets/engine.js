'use strict';
// 动画短片引擎：场景时间线、Canvas 2D 绘制、像素角色、界面零件、对白与字幕、合成音轨、播放器和逐帧导出接口。
// film.js 在本文件之后执行，只调用这里的全局函数。画面和声音都只由时间决定，所以导出与实时播放逐帧一致。

const PI = Math.PI, TAU = Math.PI * 2;
let W = 1920, H = 1080;

const FILM = {
  title: '', tagline: '', size: [1920, 1080], bg: '#16120f', tail: 1.5, poster: null,
  subtitle: {}, voices: {}, music: false,
};
const SCENES = [], SUBS = [], LINES = [], CUES = [];
const FONT = {
  serif: '"Noto Serif CJK SC", "Noto Serif SC", "Songti SC", "SimSun", serif',
  sans: '"Noto Sans CJK SC", "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
  mono: '"Noto Sans Mono", "SF Mono", "Menlo", "Consolas", "Noto Sans CJK SC", monospace',
  math: '"STIX Two Text", "Noto Serif CJK SC", serif',
};
const PARAMS = new URLSearchParams(location.search);
const EXPORT = PARAMS.has('export');
let DURATION = 0, filmed = false;

function film(o) {
  if (SCENES.length) throw new Error('call film() before the first scene()');
  Object.assign(FILM, o);
  [W, H] = FILM.size;
  for (const [who, v] of Object.entries(FILM.voices || {})) {
    if (v.tone && !VOICE_TONES[v.tone]) throw new Error(`voice "${who}": unknown tone "${v.tone}"; use ${Object.keys(VOICE_TONES).join(', ')}`);
    (v.notes || []).forEach(noteHz);
  }
  if (FILM.music) (FILM.music.chords || []).forEach(chordNotes);
  filmed = true;
}
function scene(o) {
  if (!filmed) throw new Error('call film() before the first scene()');
  const name = o.name || `scene ${SCENES.length + 1}`;
  if (!(o.dur > 0)) throw new Error(`${name}: dur must be a positive number of seconds`);
  if (typeof o.draw !== 'function') throw new Error(`${name}: draw(t, d) is missing`);
  const start = SCENES.length ? SCENES[SCENES.length - 1].end : 0;
  const sc = { ...o, name, start, end: start + o.dur, d: o.dur };
  SCENES.push(sc);
  for (const sub of o.subs || []) {
    const [a, b, t1, t2] = sub;
    if (!(b > a) || typeof t1 !== 'string') throw new Error(`${name}: each subtitle is [start, end, text, secondLine?] with end > start`);
    SUBS.push({ start: start + a, end: start + b, text: t1, second: t2, scene: name });
  }
  for (const line of o.say || []) {
    const [t, who, str, opt = {}] = line, v = (FILM.voices || {})[who];
    if (!(t >= 0) || typeof str !== 'string') throw new Error(`${name}: each line is [t, who, text, { cps, silent, tag }?]`);
    if (!v) throw new Error(`${name}: "${who}" has no voice; declare it in film({ voices })`);
    const chars = [...str], cps = opt.cps ?? v.cps ?? 12;
    LINES.push({ who, text: str, chars, cps, start: start + t, end: start + t + chars.length / cps, scene: name, silent: !!opt.silent, tag: opt.tag });
  }
  for (const [t, kind, opt] of o.sfx || []) addSound(start + t, kind, opt, name);
  if (o.music) (o.music.chords || []).forEach(chordNotes);
  for (const list of [SUBS, LINES]) list.sort((a, b) => a.start - b.start);
  return { name, start, end: sc.end };
}
// 在全片时间上加音效：跨场景的状态表（比如一串离队时刻）可以直接配声
function sound(T, kind, opt) { addSound(T, kind, opt, 'sound()'); }
function addSound(T, kind, opt = {}, where) {
  if (!SOUNDS[kind]) throw new Error(`${where}: unknown sound "${kind}"; use ${Object.keys(SOUNDS).join(', ')}`);
  if (!(T >= 0)) throw new Error(`${where}: sound "${kind}" needs a time of 0 s or later`);
  CUES.push({ ...opt, t: T, name: kind });
  CUES.sort((a, b) => a.t - b.t);
}

// ------------------------------------------------------------------ 数学、缓动与阶梯运动
const clamp = (x, a = 0, b = 1) => x < a ? a : x > b ? b : x;
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const fade = (t, a, b, fi = .4, fo = .4) => smooth(a, a + fi, t) * (1 - smooth(b - fo, b, t));
const progress = (t, start, dur) => clamp((t - start) / dur);
const ease = {
  in: t => t * t * t,
  out: t => 1 - (1 - t) ** 3,
  inOut: t => t < .5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2,
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
// 像素物体按帧率取整时间，动作一格一格地走，不和界面的平滑缓动混在一起
const stepped = (x, fps = 12) => Math.floor(x * fps + 1e-6) / fps;
function hop(t, at, o = {}) {
  const dur = o.dur ?? .35, height = o.height ?? 2;
  let up = 0;
  for (const a of [].concat(at)) {
    const k = stepped(t - a) / dur;
    if (k >= 0 && k < 1) up = Math.max(up, Math.round(height * Math.sin(PI * k)));
  }
  return up;
}
const blinkCache = new Map();
function blinking(T, o = {}) {
  const seed = o.seed ?? 1, [lo, hi] = o.every ?? [2.5, 4.5], dur = o.dur ?? .12, key = `${seed}|${lo}|${hi}`;
  let list = blinkCache.get(key);
  if (!list) {
    const r = rng(seed); list = [];
    for (let x = .8 + r() * lo; x < 3600; x += lo + r() * (hi - lo)) list.push(x);
    blinkCache.set(key, list);
  }
  for (const b of list) { if (b > T) break; if (T < b + dur) return true; }
  return false;
}
const breathe = (t, o = {}) => { const p = o.period ?? 1.6, h = o.hold ?? .4; return ((t % p) + p) % p >= p - h ? 1 : 0; };

// ------------------------------------------------------------------ 文字
const PIXEL = { scale: 1 };
let track = null;                                                // check 模式下记录每段文字的包围盒

function fontOf(o) { return `${o.style || ''} ${o.weight || 400} ${o.size || 40}px ${o.font || FONT.sans}`; }
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
const plain = str => Array.isArray(str) ? str.map(p => Array.isArray(p) ? p[0] : p).join('') : String(str);
function measure(str, o = {}) {
  str = plain(str);
  ctx.save(); ctx.font = fontOf(o);
  const manual = spacing(o.ls), w = ctx.measureText(str).width + manual * [...str].length - (o.ls || 0);
  ctx.restore();
  return w;
}
// str 可以是 [[文字, 颜色], ...] 分段着色；upto 只画前 n 个字，但按整句排版，打字时位置不跳
function text(str, x, y, o = {}) {
  const parts = Array.isArray(str) ? str.map(p => Array.isArray(p) ? [String(p[0]), p[1]] : [String(p), null]) : [[String(str), null]];
  ctx.save();
  ctx.font = fontOf(o);
  ctx.textAlign = 'left'; ctx.textBaseline = o.base || 'middle';
  const manual = spacing(o.ls);
  const widthOf = s => ctx.measureText(s).width + manual * [...s].length;
  const widths = parts.map(([s]) => widthOf(s));
  const width = widths.reduce((a, b) => a + b, 0) - (o.ls || 0);
  const align = o.align || 'center';
  const left = align === 'center' ? x - width / 2 : align === 'right' ? x - width : x;
  ctx.globalAlpha *= o.alpha ?? 1;
  if (o.glow) { ctx.shadowColor = o.glow; ctx.shadowBlur = o.blur ?? 24; }
  if (o.stroke) { ctx.strokeStyle = o.stroke; ctx.lineWidth = o.lineWidth || 2; ctx.lineJoin = 'round'; }
  const put = (s, px) => {
    const one = c => { if (o.stroke) ctx.strokeText(c, px, y); if (o.fill !== false) ctx.fillText(c, px, y); };
    if (!manual) return one(s);
    for (const c of s) { one(c); px += ctx.measureText(c).width + manual; }
  };
  let budget = o.upto == null ? Infinity : Math.max(0, Math.floor(o.upto)), px = left, drawn = '';
  for (let i = 0; i < parts.length && budget > 0; i++) {
    let [s, color] = parts[i];
    const chars = [...s];
    if (chars.length > budget) s = chars.slice(0, budget).join('');
    budget -= Math.min(budget, chars.length);
    ctx.fillStyle = color || o.color || '#fff';
    put(s, px);
    drawn += s; px += widths[i];
  }
  if (drawn) {
    // 按实际字形边界记录，留白不算，检查重叠和越界时才不会误报
    const ink = ctx.measureText(drawn);
    record(drawn, left - ink.actualBoundingBoxLeft, y - ink.actualBoundingBoxAscent, manual ? left + widthOf(drawn) : left + ink.actualBoundingBoxRight,
      y + ink.actualBoundingBoxDescent, ctx.globalAlpha);
  }
  ctx.restore();
  return width;
}
function lines(str, maxWidth, o = {}) {
  ctx.save(); ctx.font = fontOf(o); spacing(o.ls);
  const out = [];
  for (const para of String(str).split('\n')) {
    // 中日韩按字断行，拉丁文按词断行
    const tokens = para.match(/[⺀-鿿豈-﫿＀-￯][，。、；：！？）」』》]?|[^\s⺀-鿿]+\s*|\s+/g) || [''];
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

// ------------------------------------------------------------------ 对白：说话的人、打字进度、说话声
function dialogue(T, o = {}) {
  const who = o.who == null ? null : [].concat(o.who), out = [];
  for (const l of LINES) {
    if (l.start > T) break;
    if (who && !who.includes(l.who)) continue;
    if (o.since != null && l.start < o.since) continue;
    if (o.until != null && l.start >= o.until) continue;
    const n = Math.min(l.chars.length, Math.floor((T - l.start) * l.cps + 1e-6));
    out.push({ who: l.who, text: l.chars.slice(0, n).join(''), full: l.text, shown: n, start: l.start, end: l.end, typing: T < l.end, tag: l.tag });
  }
  return o.last ? out.slice(-o.last) : out;
}
const speaking = (T, who) => LINES.some(l => l.who === who && T >= l.start && T < l.end);

// ------------------------------------------------------------------ 界面零件与图解
function roundRect(x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h / 2));
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
// 面板或窗口：返回内容区（有标题栏时不含标题栏）
function panel(x, y, w, h, o = {}) {
  const r = o.radius ?? 18, bar = o.title != null ? o.bar ?? 52 : 0;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  if (o.shadow) { ctx.shadowColor = o.shadow === true ? 'rgba(0,0,0,.35)' : o.shadow; ctx.shadowBlur = 40; ctx.shadowOffsetY = 12; }
  roundRect(x, y, w, h, r); ctx.fillStyle = o.fill ?? '#201a16'; ctx.fill();
  ctx.shadowColor = 'transparent';
  if (o.stroke !== false) { ctx.lineWidth = o.lineWidth ?? 2; ctx.strokeStyle = o.stroke ?? '#3a3029'; ctx.stroke(); }
  if (bar) {
    ctx.fillStyle = o.stroke || '#3a3029'; ctx.fillRect(x, y + bar, w, o.lineWidth ?? 2);
    if (o.dots) for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(x + 28 + i * 22, y + bar / 2, 6, 0, TAU); ctx.fillStyle = o.dots === true ? '#4a3f37' : o.dots; ctx.fill(); }
  }
  ctx.restore();
  if (bar && o.title) text(o.title, x + w / 2, y + bar / 2, { font: o.font ?? FONT.sans, size: o.titleSize ?? 24, color: o.titleColor ?? '#8a7f74', alpha: o.alpha ?? 1 });
  return { x, y: y + bar, w, h: h - bar };
}
// 带底色的标签：章节标签、token 方块、价签。返回外框
function chip(str, x, y, o = {}) {
  const size = o.size ?? 28, font = o.font ?? FONT.sans, weight = o.weight ?? 600, [px, py] = o.pad ?? [size * .5, size * .28];
  const w = measure(str, { size, font, weight, ls: o.ls }) + px * 2, h = size * 1.15 + py * 2;
  const left = o.align === 'left' ? x : o.align === 'right' ? x - w : x - w / 2;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  roundRect(left, y - h / 2, w, h, o.radius ?? 8);
  if (o.fill !== false) { ctx.fillStyle = o.fill ?? '#D97757'; ctx.fill(); }
  if (o.outline) { ctx.lineWidth = o.lineWidth ?? 3; ctx.strokeStyle = o.outline; ctx.stroke(); }
  ctx.restore();
  text(str, left + w / 2, y, { size, font, weight, ls: o.ls, color: o.color ?? '#1b1410', alpha: o.alpha ?? 1, upto: o.upto });
  return { x: left, y: y - h / 2, w, h };
}
// 对话气泡：(x, y) 是尾巴尖，气泡默认在上方；按整句定宽，打字时不变形
function bubble(str, x, y, o = {}) {
  const size = o.size ?? 30, font = o.font ?? FONT.sans, [px, py] = o.pad ?? [size * .7, size * .45];
  const w = Math.max(measure(str, { size, font, weight: o.weight }) + px * 2, size * 2.4), h = size * 1.25 + py * 2;
  const tail = o.tail ?? 16, below = o.side === 'below', r = o.radius ?? Math.min(18, h / 2);
  const bx = x - w / 2 + (o.shift ?? 0), by = below ? y + tail : y - tail - h, edge = below ? by : by + h;
  const tx = clamp(x, bx + r + tail, bx + w - r - tail);
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  ctx.beginPath();
  ctx.moveTo(bx + r, by);
  if (below) { ctx.lineTo(tx - tail * .7, edge); ctx.lineTo(x, y); ctx.lineTo(tx + tail * .7, edge); }
  ctx.arcTo(bx + w, by, bx + w, by + h, r); ctx.arcTo(bx + w, by + h, bx, by + h, r);
  if (!below) { ctx.lineTo(tx + tail * .7, edge); ctx.lineTo(x, y); ctx.lineTo(tx - tail * .7, edge); }
  ctx.arcTo(bx, by + h, bx, by, r); ctx.arcTo(bx, by, bx + w, by, r); ctx.closePath();
  ctx.fillStyle = o.fill ?? '#fffaf2'; ctx.fill();
  if (o.stroke !== false) { ctx.lineWidth = o.lineWidth ?? 2; ctx.strokeStyle = o.stroke ?? '#d9cfbf'; ctx.lineJoin = 'round'; ctx.stroke(); }
  ctx.restore();
  text(str, bx + w / 2, by + h / 2, { size, font, weight: o.weight, color: o.color ?? '#2b2622', alpha: o.alpha ?? 1, upto: o.upto });
  return { x: bx, y: by, w, h };
}
// 方格阵列：上下文窗口、参数、计数墙、条形图。color(i, col, row) 返回颜色，返回 null 不画
function cells(x, y, cols, rows, o = {}) {
  const size = o.size ?? 22, pitch = size + (o.gap ?? 4);
  const at = i => ({ x: x + (i % cols) * pitch, y: y + Math.floor(i / cols) * pitch });
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  for (let i = 0; i < cols * rows; i++) {
    const c = typeof o.color === 'function' ? o.color(i, i % cols, Math.floor(i / cols)) : o.color ?? '#2a221d';
    if (!c) continue;
    const p = at(i);
    ctx.fillStyle = c;
    if (o.radius) { roundRect(p.x, p.y, size, size, o.radius); ctx.fill(); } else ctx.fillRect(p.x, p.y, size, size);
  }
  ctx.restore();
  return { x, y, w: cols * pitch - (o.gap ?? 4), h: rows * pitch - (o.gap ?? 4), at };
}
// 箭头：k 是画出的比例（0–1），dash 为虚线段长
function arrow(x0, y0, x1, y1, o = {}) {
  const k = o.k ?? 1; if (k <= 0) return;
  const x = lerp(x0, x1, k), y = lerp(y0, y1, k), a = Math.atan2(y1 - y0, x1 - x0), head = o.head ?? 16;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1;
  ctx.strokeStyle = ctx.fillStyle = o.color ?? '#f3ece4'; ctx.lineWidth = o.width ?? 4; ctx.lineCap = 'round';
  if (o.dash) ctx.setLineDash([o.dash, o.dash * .8]);
  ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x - Math.cos(a) * head * .6, y - Math.sin(a) * head * .6); ctx.stroke();
  ctx.setLineDash([]);
  ctx.beginPath(); ctx.moveTo(x, y);
  ctx.lineTo(x - Math.cos(a - .45) * head, y - Math.sin(a - .45) * head); ctx.lineTo(x - Math.cos(a + .45) * head, y - Math.sin(a + .45) * head);
  ctx.closePath(); ctx.fill();
  ctx.restore();
}
function caret(x, y, h, T, o = {}) {
  if ((T % 1 + 1) % 1 >= .5) return;
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1; ctx.fillStyle = o.color ?? '#f3ece4'; ctx.fillRect(x, y - h / 2, h * .5, h); ctx.restore();
}
function dotgrid(o = {}) {
  const gap = o.gap ?? 32, r = o.size ?? 2;
  ctx.save(); ctx.fillStyle = o.color ?? '#ffffff'; ctx.globalAlpha *= o.alpha ?? .04;
  for (let y = gap / 2; y < H; y += gap) for (let x = gap / 2; x < W; x += gap) ctx.fillRect(x - r / 2, y - r / 2, r, r);
  ctx.restore();
}
function vignette(a = .5, color = '#000000') {
  const g = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * .35, W / 2, H / 2, Math.hypot(W, H) * .6);
  g.addColorStop(0, rgba(color, 0)); g.addColorStop(1, rgba(color, a));
  ctx.save(); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H); ctx.restore();
}
function glow(x, y, r, color = '#ffffff', a = 1) {
  if (r <= 0 || a <= 0) return;
  ctx.save(); ctx.globalCompositeOperation = 'lighter';
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, rgba(color, a * .8)); g.addColorStop(.4, rgba(color, a * .25)); g.addColorStop(1, rgba(color, 0));
  ctx.fillStyle = g; ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
  ctx.restore();
}

// ------------------------------------------------------------------ 像素角色与物件
function sprite(rows, palette = {}) {
  const grid = rows.map(r => [...r]);
  for (const ch of new Set(grid.flat())) if (ch !== '.' && ch !== ' ' && !(ch in palette)) throw new Error(`sprite: no colour for "${ch}"`);
  return { rows: grid, w: Math.max(...grid.map(r => r.length)), h: grid.length, palette };
}
const revealCache = new WeakMap();
function revealRank(sp, seed) {
  let bySeed = revealCache.get(sp);
  if (!bySeed) revealCache.set(sp, bySeed = new Map());
  if (!bySeed.has(seed)) {
    const filled = [];
    sp.rows.forEach((row, r) => row.forEach((ch, c) => { if (ch !== '.' && ch !== ' ') filled.push(r * sp.w + c); }));
    const rand = rng(seed);
    for (let i = filled.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [filled[i], filled[j]] = [filled[j], filled[i]]; }
    const rank = new Float32Array(sp.w * sp.h);
    filled.forEach((idx, i) => { rank[idx] = (i + 1) / filled.length; });
    bySeed.set(seed, rank);
  }
  return bySeed.get(seed);
}
// 按格画像素图。每格的边缘对齐到设备像素，任何缩放下都不糊、不留缝。
// edits: [[行, 列, 字符], ...] 临时改格子（眨眼、表情、抬手）；offset(行, 列) → [dx, dy] 按格挪动部分身体（呼吸）
function pixels(sp, x, y, o = {}) {
  const c = o.cell ?? 10, pal = o.palette ? { ...sp.palette, ...o.palette } : sp.palette;
  let grid = sp.rows;
  if (o.edits && o.edits.length) {
    grid = sp.rows.map(r => r.slice());
    for (const [r, col, ch] of o.edits) if (r >= 0 && col >= 0) (grid[r] || (grid[r] = []))[col] = ch;
  }
  const w = sp.w * c, h = sp.h * c, anchor = o.anchor || 'bottom';
  const left = anchor === 'top-left' ? x : x - w / 2, top = anchor === 'bottom' ? y - h : anchor === 'center' ? y - h / 2 : y;
  const rank = o.reveal != null && o.reveal < 1 ? revealRank(sp, o.seed ?? 1) : null;
  const m = ctx.getTransform(), X = v => Math.round(m.a * v + m.e), Y = v => Math.round(m.d * v + m.f);
  ctx.save(); ctx.globalAlpha *= o.alpha ?? 1; ctx.setTransform(1, 0, 0, 1, 0, 0);
  for (let r = 0; r < grid.length; r++) for (let col = 0; col < grid[r].length; col++) {
    const ch = grid[r][col];
    if (!ch || ch === '.' || ch === ' ' || !pal[ch]) continue;
    if (rank && (rank[r * sp.w + col] || 0) > o.reveal) continue;
    const [dx, dy] = (o.offset && o.offset(r, col)) || [0, 0];
    const x0 = left + ((o.flip ? sp.w - 1 - col : col) + dx) * c, y0 = top + (r + dy) * c, px = X(x0), py = Y(y0);
    ctx.fillStyle = pal[ch]; ctx.fillRect(px, py, X(x0 + c) - px, Y(y0 + c) - py);
  }
  ctx.restore();
  return { x: left, y: top, w, h };
}

// ------------------------------------------------------------------ 声音：按事件逐样本合成单声道音轨
const RATE = 44100;
const SEMI = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const accidental = s => s === '#' ? 1 : s === 'b' ? -1 : 0;
function noteHz(name) {
  if (typeof name === 'number') return name;
  const m = /^([A-G])([#b]?)(-?\d)$/.exec(String(name));
  if (!m) throw new Error(`unknown note "${name}"; write it like "E5" or "F#4"`);
  return 440 * 2 ** ((SEMI[m[1]] + accidental(m[2]) - 9) / 12 + (+m[3] - 4));
}
const midiHz = n => 440 * 2 ** ((n - 69) / 12);
const QUALITIES = {
  '': [0, 4, 7], m: [0, 3, 7], 5: [0, 7], sus2: [0, 2, 7], sus4: [0, 5, 7], dim: [0, 3, 6], aug: [0, 4, 8],
  6: [0, 4, 7, 9], m6: [0, 3, 7, 9], 7: [0, 4, 7, 10], maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10],
  add9: [0, 4, 7, 14], madd9: [0, 3, 7, 14], 9: [0, 4, 7, 10, 14], maj9: [0, 4, 7, 11, 14], m9: [0, 3, 7, 10, 14],
};
function chordNotes(name) {
  const m = /^([A-G])([#b]?)(.*)$/.exec(String(name)), q = m && QUALITIES[m[3]];
  if (!q) throw new Error(`unknown chord "${name}"; use a root A–G, optional # or b, and one of: major (no suffix), ${Object.keys(QUALITIES).filter(Boolean).join(', ')}`);
  return q.map(i => SEMI[m[1]] + accidental(m[2]) + i);
}
const WAVES = {
  sine: p => Math.sin(p),
  triangle: p => 2 / PI * Math.asin(Math.sin(p)),
  square: p => Math.tanh(3 * Math.sin(p)),                       // 圆一点的方波，短音不刺耳
};
function tone(buf, t, dur, f0, o = {}) {
  const wave = WAVES[o.wave || 'sine'], gain = o.gain ?? .2, f1 = o.to ?? f0, attack = o.attack ?? .004, shape = o.decay ?? 'exp';
  const i0 = Math.max(0, Math.round(t * RATE)), i1 = Math.min(buf.length, Math.round((t + dur) * RATE));
  let phase = 0;
  for (let i = i0; i < i1; i++) {
    const x = i / RATE - t, k = x / dur, f = f1 === f0 ? f0 : f0 * (f1 / f0) ** k;
    phase += TAU * f / RATE;
    const env = Math.min(1, x / attack) * (shape === 'exp' ? Math.exp(-5 * k) : shape === 'pad' ? Math.min(1, (dur - x) / .5) : Math.min(1, (1 - k) * 8));
    buf[i] += gain * env * wave(phase);
  }
}
function hiss(buf, t, dur, o = {}) {
  const gain = o.gain ?? .2, rand = rng(o.seed ?? Math.round(t * 997) + 1), bright = o.bright ?? .5;
  const i0 = Math.max(0, Math.round(t * RATE)), i1 = Math.min(buf.length, Math.round((t + dur) * RATE));
  let low = 0;
  for (let i = i0; i < i1; i++) {
    const k = (i / RATE - t) / dur, cut = typeof o.cutoff === 'function' ? o.cutoff(k) : o.cutoff ?? .25;
    const white = rand() * 2 - 1; low += (white - low) * cut;
    const env = Math.min(1, (i / RATE - t) / .002) * (o.decay === 'hold' ? Math.min(1, (1 - k) * 6) : o.decay === 'swell' ? Math.sin(PI * k) : Math.exp(-6 * k));
    buf[i] += gain * env * (white * bright + low * (1 - bright));
  }
}
const SOUNDS = {
  tick: (b, t, o) => hiss(b, t, o.dur ?? .015, { gain: .5 * (o.gain ?? 1), bright: .9 }),
  key: (b, t, o) => hiss(b, t, .03, { gain: .3 * (o.gain ?? 1), bright: .4, cutoff: .5 }),
  click: (b, t, o) => { hiss(b, t, .012, { gain: .4 * (o.gain ?? 1), bright: .9 }); tone(b, t, .03, 1800, { gain: .1 * (o.gain ?? 1) }); },
  pop: (b, t, o) => tone(b, t, o.dur ?? .08, 640, { to: 280, gain: .35 * (o.gain ?? 1) }),
  blip: (b, t, o) => tone(b, t, o.dur ?? .06, noteHz(o.note ?? 'E5'), { wave: 'square', gain: .14 * (o.gain ?? 1) }),
  chime: (b, t, o) => { const f = noteHz(o.note ?? 'G5'), d = o.dur ?? 1.4; tone(b, t, d, f, { gain: .2 * (o.gain ?? 1) }); tone(b, t, d * .5, f * 2.76, { gain: .05 * (o.gain ?? 1) }); },
  ding: (b, t, o) => { tone(b, t, .14, noteHz('E6'), { wave: 'triangle', gain: .18 * (o.gain ?? 1) }); tone(b, t + .09, .3, noteHz('G6'), { wave: 'triangle', gain: .18 * (o.gain ?? 1) }); },
  success: (b, t, o) => ['C5', 'E5', 'G5', 'C6'].forEach((n, i) => tone(b, t + i * .08, .24, noteHz(n), { wave: 'triangle', gain: .16 * (o.gain ?? 1) })),
  sad: (b, t, o) => { tone(b, t, .2, noteHz('E4'), { wave: 'square', gain: .1 * (o.gain ?? 1), decay: 'hold' }); tone(b, t + .22, .34, noteHz('C4'), { wave: 'square', gain: .1 * (o.gain ?? 1) }); },
  drop: (b, t, o) => tone(b, t, o.dur ?? .14, noteHz(o.note ?? 'G4'), { to: noteHz(o.to ?? 'C4'), wave: 'triangle', gain: .2 * (o.gain ?? 1), decay: 'hold' }),
  rise: (b, t, o) => tone(b, t, o.dur ?? .1, noteHz(o.note ?? 'C5'), { to: noteHz(o.to ?? 'C6'), wave: 'triangle', gain: .2 * (o.gain ?? 1), decay: 'hold' }),
  thump: (b, t, o) => tone(b, t, o.dur ?? .3, 64, { to: 46, gain: .6 * (o.gain ?? 1) }),
  whoosh: (b, t, o) => hiss(b, t, o.dur ?? .45, { gain: .25 * (o.gain ?? 1), bright: 0, cutoff: k => .03 + .25 * Math.sin(PI * k), decay: 'swell' }),
  scratch: (b, t, o) => hiss(b, t, o.dur ?? .09, { gain: .2 * (o.gain ?? 1), bright: .2, cutoff: .35, decay: 'hold' }),
  tone: (b, t, o) => tone(b, t, o.dur ?? .3, noteHz(o.note ?? 'A4'), { wave: o.wave ?? 'sine', to: o.to == null ? undefined : noteHz(o.to), gain: .2 * (o.gain ?? 1) }),
};
const VOICE_TONES = {
  square: (b, t, f, g) => tone(b, t, .045, f, { wave: 'square', gain: .09 * g }),
  triangle: (b, t, f, g) => tone(b, t, .05, f, { wave: 'triangle', gain: .15 * g }),
  sine: (b, t, f, g) => tone(b, t, .06, f, { gain: .17 * g }),
  key: (b, t, f, g) => hiss(b, t, .022, { gain: .2 * g, bright: .6 }),
  none: () => {},
};
const PAUSE = /[\s\p{P}\p{S}]/u;
function speech(buf) {
  for (const l of LINES) {
    if (l.silent) continue;
    const v = FILM.voices[l.who], play = VOICE_TONES[v.tone || 'square'], g = v.gain ?? 1;
    const notes = (v.notes || ['C5', 'D5', 'E5', 'G5', 'A5']).map(noteHz);
    l.chars.forEach((ch, i) => { if (!PAUSE.test(ch)) play(buf, l.start + i / l.cps, notes[ch.codePointAt(0) % notes.length], g); });
  }
}
// 背景音乐：小节网格从 0 开始；每小节由它开头所在的、写了 music 的最近场景决定和弦与能量
function music(buf) {
  const m = FILM.music;
  if (!m) return;
  const bar = 240 / (m.bpm ?? 90), g = m.gain ?? 1;
  for (let k = 0; k * bar < DURATION - .1; k++) {
    const t0 = k * bar;
    let owner = null;
    for (const sc of SCENES) if (sc.music !== undefined && sc.start <= t0 + .05) owner = sc;
    const set = { chords: m.chords || ['C'], energy: m.energy ?? 1, ...(owner && owner.music ? owner.music : {}) };
    if (owner && owner.music === false) set.energy = 0;
    if (!(set.energy > 0)) continue;
    const first = owner ? Math.ceil((owner.start - .05) / bar) : 0;
    const notes = chordNotes(set.chords[(k - first) % set.chords.length]);
    // 根音放在 C3 附近，其余音往上排，高过 G4 的降一个八度
    const midi = notes.map((s, j) => { let n = 48 + s; if (j && n > 67) n -= 12; return n; });
    for (const n of midi) {
      tone(buf, t0, bar + .5, midiHz(n), { gain: .02 * g, attack: .45, decay: 'pad' });
      tone(buf, t0, bar + .5, midiHz(n) * 1.004, { wave: 'triangle', gain: .012 * g, attack: .45, decay: 'pad' });
    }
    tone(buf, t0, 1.6, midiHz(midi[0] + 24), { gain: .045 * g });
    if (set.energy >= 2) for (let e = 0; e < 8; e++) tone(buf, t0 + e * bar / 8, .28, midiHz(midi[e % midi.length] + 24), { wave: 'triangle', gain: .026 * g });
  }
}
function soundtrack() {
  const buf = new Float32Array(Math.ceil(DURATION * RATE));
  music(buf); speech(buf);
  for (const c of CUES) SOUNDS[c.name](buf, c.t, c);
  // 按有声部分的均方根把响度拉到约 −18 dBFS，再软限幅：叠在一起时圆滑压住，不会削波；结尾淡出
  let sum = 0, n = 0;
  for (const x of buf) if (Math.abs(x) > 1e-3) { sum += x * x; n++; }
  const gain = n ? clamp(.12 / Math.sqrt(sum / n), .5, 6) : 1, tail = Math.min(buf.length, Math.round(.8 * RATE));
  for (let i = 0; i < buf.length; i++) buf[i] = Math.tanh(buf[i] * gain) * .95 * Math.min(1, (buf.length - i) / tail);
  return buf;
}
function wav(samples) {
  const n = samples.length, bytes = new Uint8Array(44 + n * 2), v = new DataView(bytes.buffer);
  const tag = (at, s) => [...s].forEach((ch, i) => v.setUint8(at + i, ch.charCodeAt(0)));
  tag(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); tag(8, 'WAVE'); tag(12, 'fmt '); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, RATE, true); v.setUint32(28, RATE * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); tag(36, 'data'); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, clamp(samples[i], -1, 1) * 32767, true);
  let s = '';
  for (let i = 0; i < bytes.length; i += 32768) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
  return btoa(s);
}

// ------------------------------------------------------------------ 画面管线
const view = document.createElement('canvas');
const vctx = view.getContext('2d');
let ctx = vctx;

function setScale(s) {
  PIXEL.scale = s;
  const w = Math.round(W * s), h = Math.round(H * s);
  if (view.width !== w || view.height !== h) { view.width = w; view.height = h; }
}
const sceneAt = T => { let sc = SCENES[0]; for (const s of SCENES) if (T >= s.start) sc = s; return sc; };
function sceneFade(sc, lt) {
  const [fi, fo] = sc.fade ?? [0, 0];
  return (fi > 0 ? smooth(0, fi, lt) : 1) * (fo > 0 ? 1 - smooth(sc.d - fo, sc.d, lt) : 1);
}
function drawScene(sc, T) {
  const lt = T - sc.start, s = PIXEL.scale;
  ctx = vctx;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over'; ctx.filter = 'none';
  ctx.shadowBlur = 0; ctx.shadowColor = 'transparent'; ctx.setLineDash([]);
  ctx.fillStyle = sc.bg || FILM.bg; ctx.fillRect(0, 0, view.width, view.height);
  ctx.setTransform(s, 0, 0, s, 0, 0);
  if (sc.camera) {
    const cam = { x: 0, y: 0, z: 1, ...sc.camera(lt, sc.d) };
    ctx.translate(W / 2 + cam.x, H / 2 + cam.y); ctx.scale(cam.z, cam.z); ctx.translate(-W / 2, -H / 2);
  }
  ctx.save();
  try { sc.draw(lt, sc.d, T); }
  catch (e) {
    // DOMException 的 message 只读，所以新建一个错误，并带上原来指向 film.js 的栈帧
    const err = new Error(`${sc.name} at ${lt.toFixed(2)}s (film ${T.toFixed(2)}s): ${e && e.name !== 'Error' ? e.name + ': ' : ''}${e && e.message || e}`);
    err.stack = err.message + '\n' + String(e && e.stack || '').split('\n').filter(l => /^\s*at /.test(l)).join('\n');
    throw err;
  }
  finally { ctx.restore(); }
}
function renderFrame(T) {
  T = clamp(T, 0, DURATION - 1e-4);
  const sc = sceneAt(T);
  drawScene(sc, T);
  overlays(T, sc);
}

// ------------------------------------------------------------------ 叠加层：转场与字幕
const subtitleStyle = () => ({ font: FONT.serif, size: 44, weight: 500, color: '#f3ece4', shadow: 'rgba(0,0,0,.85)', y: H - 80, ...FILM.subtitle });
function overlays(T, sc) {
  ctx = vctx;
  ctx.setTransform(PIXEL.scale, 0, 0, PIXEL.scale, 0, 0); ctx.globalAlpha = 1;
  const exposure = sceneFade(sc, T - sc.start);
  if (exposure < 1) { ctx.fillStyle = sc.fadeTo || FILM.bg; ctx.globalAlpha = 1 - exposure; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
  subtitles(T);
}
function subtitles(T) {
  const st = subtitleStyle();
  for (const sb of SUBS) {
    if (T < sb.start - .2 || T > sb.end + .2) continue;
    const a = fade(T, sb.start, sb.end, .15, .15); if (a <= 0) continue;
    const main = { font: st.font, size: st.size, weight: st.weight, color: st.color, alpha: a, glow: st.shadow, blur: st.size * .3 };
    const second = { ...main, size: st.size * .68, color: st.second || st.color, alpha: a * .85 };
    const l1 = lines(sb.text, W * .86, main), l2 = sb.second ? lines(sb.second, W * .86, second) : [];
    let y = st.y - (l1.length - 1) * st.size * 1.3 - l2.length * st.size;
    for (const l of l1) { text(l, W / 2, y, main); y += st.size * 1.3; }
    y -= st.size * .3;
    for (const l of l2) { text(l, W / 2, y, second); y += st.size; }
  }
}

// ------------------------------------------------------------------ 字体、检查与导出接口
let fontsReady = false, started = false;
function info() {
  return {
    title: FILM.title, tagline: FILM.tagline, size: [W, H], duration: DURATION, tail: FILM.tail ?? 1.5, poster: posterTime(),
    scenes: SCENES.map(s => ({ name: s.name, start: s.start, end: s.end })),
    subs: SUBS.map(({ start, end, text, second, scene }) => ({ start, end, text, second, scene })),
    lines: LINES.length, cues: CUES.length, music: !!FILM.music,
  };
}
// check 用：在给定时刻只画场景（不含转场和字幕），记录越界或压住字幕的文字，
// 并给出与上一个采样相比变化了的像素比例，用来找长时间不动的画面。
const SIG = document.createElement('canvas');
SIG.width = 96; SIG.height = 54;
const sigctx = SIG.getContext('2d', { willReadFrequently: true });
const scanSeen = new Set();
const OVERLAP_SHARE = .1;   // 重叠面积占较小文字字形框的比例
let lastSig = null, lastScene = null;
function signature() {
  sigctx.drawImage(view, 0, 0, SIG.width, SIG.height);
  const d = sigctx.getImageData(0, 0, SIG.width, SIG.height).data, out = new Uint8Array(SIG.width * SIG.height);
  for (let i = 0; i < out.length; i++) out[i] = (d[i * 4] * 54 + d[i * 4 + 1] * 183 + d[i * 4 + 2] * 19) >> 8;
  return out;
}
function scan(times) {
  const issues = [], motion = [], st = subtitleStyle(), band = st.y - st.size * 2.2;
  for (const T of times) {
    const sc = sceneAt(T);
    track = [];
    drawScene(sc, T);
    const sig = signature();
    let changed = null;
    if (lastSig && lastScene === sc) { changed = 0; for (let i = 0; i < sig.length; i++) if (Math.abs(sig[i] - lastSig[i]) > 6) changed++; changed /= sig.length; }
    motion.push(changed);
    lastSig = sig; lastScene = sc;
    const subOn = SUBS.some(sb => T >= sb.start && T <= sb.end);
    for (const b of track) {
      const key = `${sc.name}|${b.text}`;
      if (scanSeen.has(key)) continue;
      const out = b.x0 < -2 || b.x1 > W + 2 || b.y0 < -2 || b.y1 > H + 2;
      const edge = b.x0 < W * .03 || b.x1 > W * .97 || b.y0 < H * .03 || b.y1 > H * .97;
      if (out || edge) { scanSeen.add(key); issues.push({ kind: out ? 'clipped' : 'edge', scene: sc.name, at: +T.toFixed(2), text: b.text, box: [b.x0, b.y0, b.x1, b.y1].map(Math.round) }); }
      else if (subOn && b.y1 > band) { scanSeen.add(key); issues.push({ kind: 'under-subtitle', scene: sc.name, at: +T.toFixed(2), text: b.text, box: [b.x0, b.y0, b.x1, b.y1].map(Math.round) }); }
    }
    // 两段不同的文字明显重叠；同一段文字叠画（描边加填充）不算
    for (let i = 0; i < track.length; i++) for (let j = i + 1; j < track.length; j++) {
      const p = track[i], q = track[j];
      if (p.text === q.text) continue;
      const w = Math.min(p.x1, q.x1) - Math.max(p.x0, q.x0), h = Math.min(p.y1, q.y1) - Math.max(p.y0, q.y0);
      if (w <= 0 || h <= 0) continue;
      const share = w * h / Math.min((p.x1 - p.x0) * (p.y1 - p.y0), (q.x1 - q.x0) * (q.y1 - q.y0));
      // 按两框的位置去重：打字和计数每帧文字都不同，但碰撞的是同一处
      const at = r => `${Math.round((r.x0 + r.x1) / 80)},${Math.round((r.y0 + r.y1) / 80)}`, key = `${sc.name}|${at(p)}|${at(q)}`;
      if (share < OVERLAP_SHARE || scanSeen.has(key)) continue;
      scanSeen.add(key);
      issues.push({ kind: 'text-overlap', scene: sc.name, at: +T.toFixed(2), text: `${p.text} / ${q.text}`, share: +share.toFixed(2) });
    }
    track = null;
  }
  return { issues, motion };
}
const posterTime = () => clamp(FILM.poster ?? (SCENES[1] ? SCENES[1].start + SCENES[1].d * .6 : DURATION * .3), 0, DURATION - .01);

window.PROMO = {
  ready: () => started && fontsReady,
  info,
  scan,
  frame(t, o = {}) {
    if (o.scale && o.scale !== PIXEL.scale) setScale(o.scale);
    renderFrame(t);
    return view.toDataURL('image/jpeg', o.quality ?? .92);
  },
  audio: () => wav(soundtrack()),
};

function start() {
  if (!SCENES.length) throw new Error('the film has no scenes');
  DURATION = SCENES[SCENES.length - 1].end + (FILM.tail ?? 1.5);
  if (EXPORT) document.body.classList.add('export');
  setScale(+(PARAMS.get('scale') || 1));
  document.title = FILM.title || 'Film';
  started = true;
  Promise.all([...document.fonts].map(f => f.load().catch(() => {}))).then(() => document.fonts.ready).then(() => {
    fontsReady = true;
    if (!EXPORT) player();
  });
}

// ------------------------------------------------------------------ 播放器
function player() {
  const $ = id => document.getElementById(id);
  const stage = $('stage'), cover = $('cover'), controls = $('controls'), toggle = $('toggle'), bar = $('bar'), fill = $('fill');
  stage.appendChild(view);
  $('cover-title').textContent = FILM.title; $('cover-tagline').textContent = FILM.tagline || '';
  const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  $('duration').textContent = fmt(DURATION);
  const fs = $('fullscreen');
  if (!document.fullscreenEnabled) fs.remove();
  else fs.onclick = () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen().catch(() => {});

  // 渲染分辨率跟随显示尺寸，避免小窗口里白算 1080p
  const fit = () => {
    const r = stage.getBoundingClientRect(), s = clamp(r.width * devicePixelRatio / W, .35, 1);
    if (Math.abs(s - PIXEL.scale) / PIXEL.scale > .1) { setScale(s); draw(); }
  };
  // 音轨在封面停留时合成；声音是时钟，没有声音（浏览器不支持或出错）时退回系统时钟
  let samples = null, ac = null, synth = null, extra = null, sources = [];
  setTimeout(() => { try { samples = soundtrack(); } catch (e) { console.error(e); } }, 30);
  async function prepareAudio() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    ac = new AC();
    samples = samples || soundtrack();
    synth = ac.createBuffer(1, samples.length, RATE); synth.copyToChannel(samples, 0);
    if (window.PROMO_AUDIO) extra = await ac.decodeAudioData(await (await fetch(window.PROMO_AUDIO)).arrayBuffer());
    if (ac.state === 'suspended') await ac.resume();
  }
  let playing = false, offset = 0, clock0 = 0, acStart = 0, hideTimer = 0, now = 0, failed = false;
  const time = () => playing ? offset + (ac ? ac.currentTime - acStart : (performance.now() - clock0) / 1000) : offset;
  function stopSources() { for (const s of sources) { try { s.stop(); } catch (e) { /* 已经停了 */ } } sources = []; }
  function startSources() {
    stopSources();
    clock0 = performance.now();
    if (!ac) return;
    acStart = ac.currentTime;
    for (const b of [synth, extra]) {
      if (!b || offset >= b.duration) continue;
      const s = ac.createBufferSource(); s.buffer = b; s.connect(ac.destination); s.start(0, offset); sources.push(s);
    }
  }
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
    startSources();
    requestAnimationFrame(loop);
  }
  function pause() { offset = time(); playing = false; stopSources(); document.body.classList.remove('playing'); }
  function seek(t) {
    offset = now = clamp(t, 0, DURATION - .02);
    if (playing) startSources(); else draw();
  }
  function poke() { controls.classList.add('show'); clearTimeout(hideTimer); hideTimer = setTimeout(() => playing && controls.classList.remove('show'), 2200); }
  cover.onclick = async () => {
    cover.remove(); document.body.classList.add('started');
    try { await prepareAudio(); } catch (e) { console.error(e); stopSources(); ac = null; }
    play(); poke();
  };
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
