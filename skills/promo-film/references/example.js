// Example film: 旁边那队, 74 seconds in six scenes. Its bible is example-bible.md; this file only implements it.
// Techniques: a pixel protagonist with poses, a world that is the diagram (three checkout lanes), typed dialogue in
// speech bubbles with a voice per speaker, a running counter, a knowledge card, sentence cards and a sound on every event.

film({
  title: '旁边那队', tagline: '为什么旁边那队总是更快', bg: '#f3ede3', tail: 1.5, poster: 31.6,
  subtitle: { color: '#2b2622', shadow: 'rgba(255,250,242,.95)' },
  voices: {
    豆豆: { tone: 'square', notes: ['E5', 'G5', 'A5', 'C6', 'D6'], cps: 10 },
    顾客: { tone: 'triangle', notes: ['C4', 'D4', 'E4', 'G4'], cps: 7 },
    收银员: { tone: 'sine', notes: ['G4', 'A4', 'C5', 'D5'], cps: 9 },
  },
  music: { bpm: 104, chords: ['C', 'Am', 'F', 'G'] },
});

const C = {
  ink: '#2b2622', soft: '#8c8378', floor: '#e7decd', desk: '#fffaf2', line: '#d6cab7',
  bean: '#5fae7b', eye: '#1f2a22', yellow: '#f2b33d', red: '#d9534a', behind: '#cfc4b2', empty: '#ece4d6',
};

// ---------------------------------------------------------------- characters
const BEAN = sprite([
  '....ggggg....',
  '..ggggggggg..',
  '.ggggggggggg.',
  '.ggEgggggEgg.',
  '.ggEgggggEgg.',
  '.ggggggggggg.',
  '..ggggggggg..',
  '...g.....g...',
  '..gg.....gg..',
], { g: C.bean, E: C.eye });
const PERSON = sprite(['.hhh.', '.hhh.', '..h..', 'bbbbb', '.bbb.', '.bbb.', '.l.l.', '.l.l.'], { h: '#e2b48f', b: '#6f8fb3', l: '#4a4038' });
const EYES = [[3, 3], [4, 3], [3, 9], [4, 9]];

// 豆豆的表情只由时间决定：看、眨眼、沮丧、走路都是对网格的临时修改
function drawBean(T, x, y, o = {}) {
  const edits = [], cell = o.cell ?? 10;
  if (o.sad) { for (const [r, c] of EYES) edits.push([r, c, 'g']); for (const c of [2, 3, 9, 10]) edits.push([4, c, 'E']); }
  else if (o.look) { for (const [r, c] of EYES) edits.push([r, c, 'g']); for (const [r, c] of EYES) edits.push([r + o.look, c, 'E']); }
  else if (blinking(T, { seed: 7 })) edits.push([3, 3, 'g'], [3, 9, 'g']);
  if (o.walking && Math.floor(T / .15) % 2) edits.push([8, 2, '.'], [8, 10, '.']);
  const sink = o.sad || (!o.walking && breathe(T));
  return pixels(BEAN, x, y - hop(T, o.hops || []) * cell, { cell, edits, reveal: o.reveal, seed: 3, offset: r => sink && r <= 6 ? [0, 1] : [0, 0] });
}

// ---------------------------------------------------------------- 1. hook: the question as a sentence card
const ASK = '为什么旁边那队，', ASK2 = [['总是', C.ink], ['更快', C.red], ['？', C.ink]];
const typing = (t, from, cps) => t < from ? 0 : (t - from) * cps + 1;
scene({
  name: 'hook', dur: 7, fade: [0, .6], music: false,
  sfx: [...[...ASK].map((_, i) => [.6 + i * .2, 'key']), ...[0, 1, 2, 3, 4].map(i => [2.8 + i * .2, 'key']),
    [4.2, 'pop'], [4.8, 'pop', { gain: .6 }], [5.8, 'blip', { note: 'C6' }]],
  draw(t, d, T) {
    text(ASK, W / 2, 430, { font: FONT.serif, size: 64, weight: 600, color: C.ink, upto: typing(t, .6, 5) });
    text(ASK2, W / 2, 520, { font: FONT.serif, size: 64, weight: 600, upto: typing(t, 2.8, 5) });
    drawBean(T, W / 2, 800, { cell: 12, reveal: progress(t, 4.2, 1.2), hops: [T - t + 5.8] });
  },
});

// ---------------------------------------------------------------- 2–5. the store
const queue = scene({
  name: 'queue', dur: 16, music: { energy: 1 },
  subs: [[.6, 3.4, '豆豆排进了中间那一队。'], [3.8, 7, '上面走了一个，下面也走了一个。'], [7.4, 10.4, '它这一队，一动不动。'],
    [10.8, 14.4, '前面那位，在一枚一枚地数硬币。']],
  say: [[10.8, '顾客', '一毛、两毛、三毛……', { tag: 1 }]],
  sfx: [[0, 'pop', { gain: .5 }], [.15, 'pop', { gain: .5 }], [.3, 'pop', { gain: .5 }]],
  draw(t, d, T) { store(T, t); },
});
const swap = scene({
  name: 'switch', dur: 14, music: { energy: 2 },
  subs: [[.4, 3.4, '于是，豆豆换到了下面。'], [3.8, 6.6, '下面立刻卡住了。'], [7, 10.2, '再换。还是卡住。'], [10.6, 13.6, '好像排哪队，哪队就最慢。']],
  say: [[2, '收银员', '这个价签扫不出来……', { tag: 2 }], [8.2, '顾客', '能给个袋子吗？', { tag: 0 }], [11.4, '豆豆', '唉。']],
  sfx: [[.4, 'whoosh'], [.4, 'ding'], [2, 'blip', { note: 'C4' }], [2.25, 'blip', { note: 'C4' }], [6.8, 'whoosh'], [6.8, 'ding'],
    [9.6, 'scratch'], [9.9, 'scratch'], [10.3, 'scratch'], [11, 'sad']],
  draw(t, d, T) { store(T); },
});

// 30 次排队里，你这队最快的 10 次落在哪几格（打乱后固定）
const TRIALS = (() => {
  const r = rng(12), order = [...Array(30).keys()];
  for (let i = 29; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
  const win = new Set(order.slice(0, 10));
  return order.map((_, i) => win.has(i));
})();
const LOSSES = TRIALS.map((w, i) => w ? -1 : i).filter(i => i >= 0);
scene({
  name: 'card', dur: 18, music: { chords: ['F', 'G', 'Em', 'Am'] },
  subs: [[.6, 3.6, '每一队什么时候卡住，全凭运气。'], [4, 7.6, '三队里，你这队最快的机会只有三分之一。'],
    [8, 11.6, '剩下三分之二，总有一队比你快。'], [12, 15.6, '被超过的那几次，又特别好记。']],
  sfx: [...TRIALS.map((_, i) => [3 + i * .2, 'key', { gain: .7 }]), [7, 'chime', { note: 'C6', gain: .6 }], [8.4, 'chime', { note: 'G5', gain: .6 }]],
  draw(t, d, T) {
    store(T);
    ctx.save(); ctx.globalAlpha = .75 * fade(t, 0, d, .5, .8); ctx.fillStyle = '#f3ede3'; ctx.fillRect(0, 0, W, H); ctx.restore();
    const a = fade(t, 0, d - .8, .6, .8);
    ctx.save(); ctx.translate(0, (1 - ease.out(progress(t, 0, .6))) * 30);
    panel(320, 150, 1280, 600, { fill: C.desk, stroke: C.line, radius: 20, shadow: 'rgba(60,45,30,.18)', alpha: a });
    const tag = chip('原理', 380, 214, { align: 'left', fill: C.yellow, color: C.ink, size: 26, alpha: a });
    text('三队里挑一队', tag.x + tag.w + 20, 214, { align: 'left', size: 44, weight: 700, color: C.ink, alpha: a });
    const shown = t < 3 ? 0 : Math.min(30, Math.floor((t - 3) / .2 + 1e-6) + 1), wins = TRIALS.slice(0, shown).filter(Boolean).length;
    const pulse = t >= 8 && t < 11.6 ? .6 + .4 * Math.cos((t - 8) * 6) : 1, memory = stepped(progress(t, 12, 3));
    const grid = cells(400, 330, 10, 3, {
      size: 48, gap: 12, radius: 6, alpha: a,
      color: i => i >= shown ? C.empty : TRIALS[i] ? rgba(C.bean, 1 - .6 * memory) : rgba(C.behind, pulse),
    });
    ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = C.red; ctx.lineWidth = 4;
    LOSSES.forEach((i, n) => { if (n < memory * LOSSES.length) { const p = grid.at(i); ctx.strokeRect(p.x + 2, p.y + 2, 44, 44); } });
    ctx.restore();
    text('你这队最快', 1300, 340, { size: 30, color: C.soft, alpha: a });
    text([[String(wins), C.bean], [' / 30', C.soft]], 1300, 430, { font: FONT.math, size: 88, alpha: a });
    chip('1/3  你这队最快', 1300, 545, { fill: C.bean, color: '#ffffff', size: 28, alpha: a * fade(t, 7, 99, .3, .1) });
    chip('2/3  别的队更快', 1300, 615, { fill: C.behind, color: C.ink, size: 28, alpha: a * fade(t, 8.4, 99, .3, .1) });
    text('示意：每队快慢各自随机', W / 2, 705, { size: 24, color: C.soft, alpha: a });
    ctx.restore();
  },
});
const stay = scene({
  name: 'stay', dur: 11, fade: [0, .6], music: { energy: 1 },
  subs: [[.4, 3, '这一次，豆豆没有再换。'], [3.4, 6.8, '它这一队，也照常往前走了。']],
  say: [[5.6, '收银员', '下一位！', { tag: 0 }]],
  sfx: [...[0, 1, 2, 3, 4].map(k => [6.6 + k * .6, 'blip', { note: 'A5' }]), [9.8, 'success']],
  draw(t, d, T) { store(T); },
});

// ---------------------------------------------------------------- 6. end: the answer as sentence cards
scene({
  name: 'end', dur: 8, fade: [0, .8],
  sfx: [[.6, 'chime', { note: 'E5', gain: .5 }], [2.8, 'chime', { note: 'C6', gain: .5 }], [5, 'blip', { note: 'C6' }]],
  draw(t, d, T) {
    text('旁边那队并不更快。', W / 2, 430, { font: FONT.serif, size: 60, weight: 600, color: C.ink, alpha: fade(t, .6, 99, .6, .1) });
    text([['只是旁边，有', C.ink], ['两队', C.red], ['。', C.ink]], W / 2, 520, { font: FONT.serif, size: 60, weight: 600, alpha: fade(t, 2.8, 99, .6, .1) });
    drawBean(T, W / 2, 800, { cell: 10, hops: [T - t + 5] });
  },
});

// ---------------------------------------------------------------- the store's state, in film seconds
const LANE_Y = [290, 500, 710], FRONT = 1400, GAP = 150, FEET = 48, STEP = .4;
const slotX = k => FRONT - k * GAP;
const LANES = [
  { clothes: ['#6f8fb3', '#c98a6b', '#9a7fb0', '#7a9e8e', '#c4a05a'],
    leave: [queue.start + 4.2, queue.start + 8, queue.start + 11.6, stay.start + 3.4, stay.start + 5],
    stuck: [[swap.start + 8.2, stay.start + 3.4, '找袋子中…']] },
  { clothes: ['#b07a8f', '#6f9fb3', '#a8a05a'],
    leave: [swap.start + 1.8, swap.start + 3.6, swap.start + 5.4],
    stuck: [[queue.start + 7.4, swap.start + 1.8, '数硬币中…']] },
  { clothes: ['#8f8fb8', '#c98a6b', '#6fa38a', '#b38f6f', '#7f9fc4'],
    leave: [queue.start + 5.2, queue.start + 9, queue.start + 12.6, swap.start + 9, swap.start + 10.4],
    stuck: [[swap.start + 2, swap.start + 9, '重新扫码中…']] },
];
// 豆豆的行程：几时出发、去哪一队、走多久；到了排在当时队里还剩的人后面
const TRIPS = [{ at: queue.start + .4, lane: 1, walk: 2.2 }, { at: swap.start + .4, lane: 2, walk: 1.2 }, { at: swap.start + 6.8, lane: 0, walk: 1.2 }];
const LOOKS = [[queue.start + 4, queue.start + 5, -1], [queue.start + 5, queue.start + 6, 1], [stay.start + .6, stay.start + 1.4, -1], [stay.start + 1.4, stay.start + 2.2, 1]];
const SAD = [swap.start + 11, swap.end], CHECKOUT = [stay.start + 6.6, stay.start + 9.6];
const HOPS = [stay.start + 6.4, stay.start + 9.8, stay.start + 10.2];

for (const L of LANES) {
  for (const d of L.leave) sound(d, 'blip', { note: 'A5', gain: .8 });
  for (const [a, b, label] of L.stuck) if (label === '数硬币中…') for (let x = a; x < b; x += .4) sound(x, 'tick', { gain: .6 });
}

// 前面每走一个人，后面的人用 STEP 秒一格一格挪上去
const moved = (T, times) => times.reduce((k, d) => k + clamp(stepped(T - d) / STEP), 0);
function beanSpot(T) {
  let i = -1;
  TRIPS.forEach((tr, j) => { if (T >= tr.at) i = j; });
  if (i < 0) return null;
  const place = (j, at) => {
    const tr = TRIPS[j], ahead = LANES[tr.lane].leave.filter(d => d > tr.at);
    return { x: slotX(ahead.length - moved(at, ahead)), y: LANE_Y[tr.lane] + FEET };
  };
  const tr = TRIPS[i], to = place(i, T), k = stepped(T - tr.at) / tr.walk;
  if (k >= 1) return { ...to, walking: false };
  // 先竖着走到目标通道，再横着走进队尾；坐标按 10px 一格取整
  const from = i ? place(i - 1, tr.at) : { x: -130, y: to.y };
  const v = Math.abs(to.y - from.y), h = Math.abs(to.x - from.x), split = v / (v + h);
  const x = k < split ? from.x : lerp(from.x, to.x, (k - split) / (1 - split)), y = k < split ? lerp(from.y, to.y, k / split) : to.y;
  return { x: Math.round(x / 10) * 10, y: Math.round(y / 10) * 10, walking: true };
}
function serving(i, T) {
  if (i === 0 && T >= CHECKOUT[0]) return CHECKOUT;
  const L = LANES[i], next = L.leave.find(d => d > T);
  return next == null ? null : [Math.max(queue.start, ...L.leave.filter(d => d <= T)), next];
}

function store(T, enter = 99) {
  text('18:30 · 超市', 96, 100, { align: 'left', font: FONT.mono, size: 28, color: C.soft, alpha: smooth(0, .6, enter) });
  const swaps = TRIPS.filter(tr => T >= tr.at).length - 1;
  if (swaps > 0) text([['换队 ×', C.ink], [String(swaps), C.red]], 1824, 100, { align: 'right', size: 30, weight: 600 });
  const bean = beanSpot(T), talk = new Map();
  for (const l of dialogue(T)) if (T < l.end + 1.2) talk.set(l.tag ?? 'bean', l);
  LANE_Y.forEach((y, i) => {
    const k = ease.out(progress(enter, i * .15, .45));
    ctx.save(); ctx.globalAlpha = k; ctx.translate(0, (1 - k) * 24);
    ctx.fillStyle = C.floor; roundRect(150, y - 60, 1350, 120, 14); ctx.fill();
    chip(`${i + 1}号`, 176, y, { align: 'left', fill: C.line, color: C.ink, size: 22 });
    panel(1530, y - 60, 240, 120, { fill: C.desk, stroke: C.line, radius: 16 });
    text(`收银 ${i + 1}`, 1650, y - 24, { size: 26, weight: 600, color: C.ink });
    const span = serving(i, T), stuck = LANES[i].stuck.find(([a, b]) => T >= a && T < b);
    ctx.fillStyle = C.empty; roundRect(1560, y + 18, 180, 12, 6); ctx.fill();
    if (span) { ctx.fillStyle = stuck ? C.red : C.bean; roundRect(1560, y + 18, 180 * clamp((T - span[0]) / (span[1] - span[0])), 12, 6); ctx.fill(); }
    // 顾客：离队的人往收银台走出去并淡出，其余人按离队次数往前挪
    LANES[i].clothes.forEach((cloth, j) => {
      const gone = T - LANES[i].leave[j];
      if (gone >= .6) return;
      const x = gone >= 0 ? slotX(0) + Math.round(stepped(gone) * 300 / 10) * 10 : slotX(j - moved(T, LANES[i].leave.slice(0, j)));
      pixels(PERSON, x, y + FEET, { cell: 10, palette: { b: cloth }, alpha: gone >= 0 ? 1 - gone / .6 : 1, offset: r => r <= 5 && breathe(T + j * .37) ? [0, 1] : [0, 0] });
    });
    if (stuck && !talk.has(i)) chip(stuck[2], 1650, y - 92, { fill: C.yellow, color: C.ink, size: 24 });
    ctx.restore();
  });
  if (bean) {
    const look = LOOKS.find(([a, b]) => T >= a && T < b);
    drawBean(T, bean.x, bean.y, { walking: bean.walking, look: look && look[2], sad: T >= SAD[0] && T < SAD[1], hops: HOPS });
  }
  // 气泡：顾客从队首头顶说，收银员从收银台说，豆豆从自己头顶说
  for (const [tag, l] of talk) {
    const o = { upto: l.shown, size: 28, fill: C.desk, stroke: C.line, color: C.ink };
    if (tag === 'bean') { if (bean) bubble(l.full, bean.x, bean.y - 102, o); }
    else if (l.who === '收银员') bubble(l.full, 1600, LANE_Y[tag] - 64, { ...o, shift: -40 });
    else bubble(l.full, slotX(0), LANE_Y[tag] - 44, o);
  }
}
