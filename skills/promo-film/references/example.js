// Example film: a 70-second science teaser, "光 / The Story of Light".
// Seven scenes on a 90 BPM grid: cold open with flash cuts, particle title, four chapters, finale.

film({
  title: '光',
  tagline: 'THE STORY OF LIGHT',
  bpm: 90,
  grade: 'gold',
  tail: 3,
  music: { style: 'cinematic' },
});

const INK = '#f3ead8', GOLD = '#e2bd6b', SOFT = '#cfc6b4';
const EIGHTH = BEAT / 2;

// ---------------------------------------------------------------- 1. cold open: heartbeat, flash cuts, the question
const FLASH = [['299,792,458', FONT.math], ['λ', FONT.math], ['1905', FONT.display], ['E = hν', FONT.math],
  ['700 nm', FONT.math], ['c', FONT.math], ['FIAT LUX', FONT.display], ['∞', FONT.math]];
scene({
  name: 'cold-open', bars: 4, letterbox: true, camera: 'still', fade: [0, .5],
  music: { chords: ['Dm', 'Bb', 'F', 'C'], energy: 1 },
  sfx: [[0, 'heart'], [BEAT, 'heart'], ...FLASH.map((_, i) => [2 * BEAT + i * EIGHTH, 'hit', { gain: .45 + i * .06 }]),
    [6 * BEAT, 'reverse', { dur: .45 }], [8 * BEAT, 'swell', { dur: 1.6 }]],
  draw(t, d) {
    if (t < 2 * BEAT) {
      const p = Math.exp(-(t % BEAT) * 5);
      glow(W / 2, H / 2, 50 + 90 * p, '#9fc8ff', .15 + .85 * p);
      return;
    }
    if (t < 6 * BEAT) {
      const i = Math.floor((t - 2 * BEAT) / EIGHTH), f = t - 2 * BEAT - i * EIGHTH, [word, font] = FLASH[i];
      glitch(word, W / 2, H / 2, { size: clamp(1300 / Math.max(2.4, word.length * .62), 90, 260), font, t: f, seed: i * 13, alpha: clamp(f / .04) });
      ctx.fillStyle = `rgba(255,255,255,${.5 * Math.exp(-f * 18)})`; ctx.fillRect(0, 0, W, H);
      return;
    }
    const a = fade(t, 6 * BEAT + .2, d, .5, .6), b = fade(t, 8 * BEAT, d, .5, .6);
    stars(t, { count: 160, speed: 5, alpha: .7 * a });
    text('它照亮一切，却从不被看见——', W / 2, H / 2 - 70, { size: 54, weight: 700, ls: 6, color: INK, alpha: a });
    text('It lights up everything, yet is never seen—', W / 2, H / 2 - 8, { font: FONT.italic, style: 'italic', weight: 500, size: 30, color: SOFT, alpha: a });
    text('什么是光？', W / 2, H / 2 + 100, { size: 88, weight: 900, ls: 12, alpha: b, glow: rgba('#ffd28c', .5), blur: 30 });
    text('What is light?', W / 2, H / 2 + 175, { font: FONT.italic, style: 'italic', weight: 500, size: 32, color: '#e2cf9f', alpha: b });
  },
});

// ---------------------------------------------------------------- 2. title: particles gather into 光, then the gold title takes over
scene({
  name: 'title', bars: 3, hits: [[0, 1]],
  backdrop: t => ({ kind: 'nebula', tint: '#b8742a', tint2: '#3a2a8f', amount: .9 * smooth(0, 2, t) }),
  music: { chords: ['Dm', 'Bb', 'F', 'C'], energy: 2 },
  sfx: [[0, 'riser', { dur: 2 }], [.2, 'sparkle', { dur: 2.2 }], [2.3, 'chime', { note: 'D6' }]],
  draw(t, d) {
    const y = H / 2 - 40, pts = textPoints('光', { size: 420 });
    assemble(pts, t, { y, dur: 1.8, stagger: .6, color: '#ffe7b0', alpha: 1 - smooth(2.4, 3.2, t) });
    if (t > 2.2) title('光', W / 2, y, { size: 420, t: t - 2.2, stagger: 0, dur: .8 });
    flare(W / 2, y, fade(t, 2.3, 4.2, .2, 1.2), { color: '#ffd9a0', len: 800 });
    text('THE STORY OF LIGHT', W / 2, y + 270, { font: FONT.display, size: 34, ls: 18, color: '#cdb88e', alpha: fade(t, 3, d, .8, .5) });
  },
});

// ---------------------------------------------------------------- 3. wave: two sources, interfering rings
scene({
  name: 'wave', bars: 4, chapter: ['I', '波', 'WAVE'],
  backdrop: { kind: 'aurora', tint: '#2be0a8', tint2: '#3b4bd8', amount: .45 },
  music: { chords: ['Gm', 'Dm', 'Bb', 'A'], energy: 2 },
  subs: [[1, 5, '光是一种波。', 'Light is a wave.'], [5.4, 10.2, '两束光相遇，彼此加强，也彼此抵消。', 'Where two beams meet, they reinforce—and cancel.']],
  sfx: [[0, 'whoosh', { dur: 1 }], [5.4, 'chime', { note: 'A5' }]],
  draw(t, d) {
    const sources = [[W / 2 - 230, H / 2 - 30], [W / 2 + 230, H / 2 - 30]], grow = smooth(.3, 1.5, t);
    ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineWidth = 2.2;
    for (const [sx, sy] of sources) for (let k = 0; k < 14; k++) {
      const r = (t * 70 + k * 64) % 900;
      ctx.strokeStyle = rgba('#8fe8ff', .5 * grow * (1 - r / 900));
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, TAU); ctx.stroke();
    }
    ctx.restore();
    for (const [sx, sy] of sources) glow(sx, sy, 70, '#8fe8ff', grow);
    text('λ', W / 2 + 230 + 64 * 2.5, H / 2 - 120, { font: FONT.math, style: 'italic', size: 64, color: INK, alpha: fade(t, 2, d, .6, .5) });
  },
});

// ---------------------------------------------------------------- 4. particle: photons strike a plate, E = hν
scene({
  name: 'particle', bars: 3, chapter: ['II', '粒子', 'PARTICLE'], hits: [[0, .5]],
  backdrop: { kind: 'grid', tint: '#ff9a3c', tint2: '#5a2bd8', amount: .7, speed: .6 },
  music: { chords: ['Dm', 'F', 'C'], energy: 3 },
  subs: [[.8, 4, '它也是粒子：一份一份，不可再分。', 'It is also a particle: indivisible packets of energy.'], [4.3, 7.6, '爱因斯坦，1905 年。', 'Einstein, 1905.']],
  sfx: [[4.3, 'tick'], [4.6, 'tick'], [4.9, 'tick']],
  draw(t, d) {
    const plate = W * .64, r = rng(5);
    ctx.fillStyle = rgba('#e8eef8', .85); ctx.fillRect(plate, H * .28, 10, H * .42);
    for (let i = 0; i < 26; i++) {
      const y = H * .3 + r() * H * .38, x = W * .22 + ((t * 520 + r() * 900) % (plate - W * .22));
      glow(x, y, 16, '#ffcf6b', .9);
      const hit = ((t * 520 + 900) % (plate - W * .22)) / (plate - W * .22);
      if (hit > .97) glow(plate + 40, y, 22, '#9fd3ff', .8);
    }
    text('E = hν', W * .33, H * .2, { font: FONT.math, style: 'italic', size: 96, color: INK, alpha: fade(t, .6, d, .6, .4) });
    text(`h = ${count(6.62607015, ease.out(progress(t, 1.2, 2)), { decimals: 8 })} × 10⁻³⁴ J·s`, W * .33, H * .2 + 90,
      { font: FONT.math, size: 34, color: GOLD, alpha: fade(t, 1.2, d, .4, .4) });
  },
});

// ---------------------------------------------------------------- 5. colour: a prism splits white light into a spectrum
const SPECTRUM = ['#ff3b3b', '#ff8a2a', '#ffd43a', '#4be36a', '#36b7ff', '#4a5bff', '#9a4bff'];
scene({
  name: 'colour', bars: 4, chapter: ['III', '色', 'COLOUR'],
  backdrop: { kind: 'silk', tint: '#3a3f7a', tint2: '#0b1230', amount: .45 },
  music: { chords: ['Bb', 'F', 'C', 'Dm'], energy: 3 },
  subs: [[1, 5, '一束白光，藏着整道彩虹。', 'A single white beam hides a whole rainbow.'], [5.4, 10.2, '牛顿用一块棱镜，把它拆开。', 'Newton took it apart with a prism.']],
  sfx: [[1.6, 'sparkle', { dur: 2.5 }]],
  draw(t, d) {
    const cx = W / 2, cy = H / 2 - 20, s = 230;
    const A = [cx, cy - s], B = [cx - s * .87, cy + s * .5], C = [cx + s * .87, cy + s * .5];
    const entry = [lerp(A[0], B[0], .5), lerp(A[1], B[1], .5)], exit = [lerp(A[0], C[0], .55), lerp(A[1], C[1], .55)];
    ctx.save(); ctx.strokeStyle = rgba('#dfe9ff', .9); ctx.lineWidth = 3; ctx.shadowColor = '#bcd4ff'; ctx.shadowBlur = 18;
    ctx.beginPath(); ctx.moveTo(...A); ctx.lineTo(...B); ctx.lineTo(...C); ctx.closePath(); ctx.stroke(); ctx.restore();
    const beam = ease.out(progress(t, .5, 1.1)), start = [0, entry[1] + 140];
    ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineCap = 'round';
    ctx.strokeStyle = rgba('#ffffff', .95); ctx.lineWidth = 6;
    ctx.beginPath(); ctx.moveTo(...start); ctx.lineTo(lerp(start[0], entry[0], beam), lerp(start[1], entry[1], beam)); ctx.stroke();
    const fan = ease.out(progress(t, 1.6, 1.6));
    if (fan > 0) {
      ctx.lineWidth = 7; ctx.strokeStyle = rgba('#ffffff', .7); ctx.beginPath(); ctx.moveTo(...entry); ctx.lineTo(...exit); ctx.stroke();
      SPECTRUM.forEach((c, i) => {
        const angle = -.05 + i * .055, len = 900 * fan;
        ctx.strokeStyle = rgba(c, .85); ctx.lineWidth = 9;
        ctx.beginPath(); ctx.moveTo(...exit); ctx.lineTo(exit[0] + Math.cos(angle) * len, exit[1] + Math.sin(angle) * len); ctx.stroke();
      });
    }
    ctx.restore();
  },
});

// ---------------------------------------------------------------- 6. cosmos: starlight that left 13.8 billion years ago
scene({
  name: 'cosmos', bars: 4, chapter: ['IV', '宇宙', 'COSMOS'], hits: [[0, .7]], blur: 1,
  backdrop: { kind: 'nebula', tint: '#2a4bd7', tint2: '#b0408f' },
  music: { chords: ['Dm', 'Bb', 'C', 'A'], energy: 4 },
  subs: [[1, 5.2, '我们今夜看见的星光，', 'The starlight we see tonight'], [5.4, 10.2, '有的已经走了一百三十八亿年。', 'has been travelling for 13.8 billion years.']],
  draw(t, d) {
    stars(t, { count: 320, speed: 14 });
    const k = ease.out(progress(t, .8, 3.2));
    text(count(13800000000, k), W / 2, H / 2 - 40, { font: FONT.math, size: 150, color: '#fff2d6', glow: rgba(GOLD, .6), blur: 36, alpha: fade(t, .6, d, .4, .5) });
    text('年', W / 2, H / 2 + 90, { size: 48, weight: 700, ls: 20, color: GOLD, alpha: fade(t, 3.4, d, .6, .5) });
  },
});

// ---------------------------------------------------------------- 7. finale: rays, the title again, the last line
scene({
  name: 'finale', bars: 3, letterbox: true, hits: [[0, 1]], fade: [.35, 1.5],
  backdrop: { kind: 'nebula', tint: '#b8742a', tint2: '#5a2a1a', amount: .7 },
  music: { chords: ['Dm', 'Bb', 'A'], energy: 4 },
  sfx: [[2.6, 'chime', { note: 'D6' }]],
  draw(t, d) {
    const y = H / 2 - 60;
    rays(W / 2, y, t, { count: 28, alpha: .35 * fade(t, 0, d, 1, 1.5) });
    title('光', W / 2, y, { size: 300, t, stagger: 0, dur: 1 });
    text('FIAT LUX', W / 2, y + 205, { font: FONT.display, size: 30, ls: 22, color: '#cdb88e', alpha: fade(t, 1.2, d, .8, 1.4) });
    text('看见一切的，从来不被看见。', W / 2, y + 290, { size: 40, weight: 700, ls: 6, color: INK, alpha: fade(t, 2.6, d, .8, 1.4) });
  },
});
