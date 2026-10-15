// Example film: a 70-second promo for 海渊七号 / ABYSS-7, a deep-sea station that does not exist.
// Seven scenes on a 90 BPM grid: cold open with flash cuts, particle title, four chapters, finale.

film({
  title: '海渊七号',
  tagline: 'ABYSS-7 · DEEP STATION',
  bpm: 90,
  grade: 'teal',
  tail: 3,
  music: { style: 'cinematic' },
});

const INK = '#e9fbf7', SOFT = '#a9d6cf', SEA = '#7ff0e0', PALE = '#bff7ee';
const EIGHTH = BEAT / 2;

// ---------------------------------------------------------------- 1. cold open: sonar pings, flash cuts, two sentence cards
const FLASH = [['7,000 m', FONT.math], ['700 atm', FONT.math], ['2 °C', FONT.math], ['0 lux', FONT.math],
  ['SONAR', FONT.display], ['20', FONT.math], ['ABYSS-7', FONT.display], ['∞', FONT.math]];
scene({
  name: 'cold-open', bars: 4, letterbox: true, camera: 'still', fade: [0, .5],
  music: { chords: ['Am', 'F', 'C', 'G'], energy: 1 },
  sfx: [[0, 'heart'], [BEAT, 'heart'], ...FLASH.map((_, i) => [2 * BEAT + i * EIGHTH, 'hit', { gain: .45 + i * .06 }]),
    [6 * BEAT, 'reverse', { dur: .45 }], [8 * BEAT, 'swell', { dur: 1.6 }]],
  draw(t, d) {
    if (t < 2 * BEAT) {
      const p = Math.exp(-(t % BEAT) * 5);
      glow(W / 2, H / 2, 50 + 90 * p, SEA, .15 + .85 * p);
      return;
    }
    if (t < 6 * BEAT) {
      const i = Math.floor((t - 2 * BEAT) / EIGHTH), f = t - 2 * BEAT - i * EIGHTH, [word, font] = FLASH[i];
      glitch(word, W / 2, H / 2, { size: clamp(1300 / Math.max(2.4, word.length * .62), 90, 260), font, t: f, seed: i * 13, alpha: clamp(f / .04) });
      ctx.fillStyle = `rgba(255,255,255,${.5 * Math.exp(-f * 18)})`; ctx.fillRect(0, 0, W, H);
      return;
    }
    // no subtitles in this scene, so sentence cards are allowed
    const a = fade(t, 6 * BEAT + .2, d, .5, .6), b = fade(t, 8 * BEAT, d, .5, .6);
    stars(t, { count: 160, speed: 5, alpha: .7 * a, color: PALE });
    text('海面之下七千米，有人在值夜班。', W / 2, H / 2 - 70, { size: 54, weight: 700, ls: 6, color: INK, alpha: a });
    text('Seven thousand metres down, someone is on the night shift.', W / 2, H / 2 - 8, { font: FONT.italic, style: 'italic', weight: 500, size: 30, color: SOFT, alpha: a });
    text('那里是什么样子？', W / 2, H / 2 + 100, { size: 84, weight: 900, ls: 12, alpha: b, glow: rgba(SEA, .5), blur: 30 });
    text('What is it like down there?', W / 2, H / 2 + 172, { font: FONT.italic, style: 'italic', weight: 500, size: 32, color: SOFT, alpha: b });
  },
});

// ---------------------------------------------------------------- 2. title: particles gather into the name, a silver title takes over
scene({
  name: 'title', bars: 3, hits: [[0, 1]],
  backdrop: t => ({ kind: 'nebula', tint: '#1f8a8a', tint2: '#1a2a6f', amount: .9 * smooth(0, 2, t) }),
  music: { chords: ['Am', 'F', 'C', 'G'], energy: 2 },
  sfx: [[0, 'riser', { dur: 2 }], [.2, 'sparkle', { dur: 2.2 }], [2.3, 'chime', { note: 'E6' }]],
  draw(t, d) {
    const y = H / 2 - 40;
    assemble(textPoints('海渊', { size: 360 }), t, { y, dur: 1.8, stagger: .6, color: '#c8fff4', alpha: 1 - smooth(2.4, 3.2, t) });
    if (t > 2.2) title('海渊', W / 2, y, { size: 360, t: t - 2.2, stagger: .12, dur: .8, metal: 'silver' });
    flare(W / 2, y, fade(t, 2.3, 4.2, .2, 1.2), { color: '#9ff3e8', len: 820 });
    text('ABYSS-7 · DEEP STATION', W / 2, y + 250, { font: FONT.display, size: 32, ls: 16, color: SOFT, alpha: fade(t, 3, d, .8, .5) });
  },
});

// ---------------------------------------------------------------- 3. descent: the probe sinks, depth and then pressure count up
scene({
  name: 'descent', bars: 4, chapter: ['I', '下潜', 'DESCENT'], blur: 1,
  backdrop: { kind: 'grid', tint: '#2fd3c0', tint2: '#0b2a4a', amount: .45, speed: .4 },
  music: { chords: ['Am', 'Dm', 'F', 'E'], energy: 2 },
  subs: [[.8, 5, '从海面出发，它要下潜整整三个小时。', 'From the surface, it sinks for three full hours.'],
    [5.4, 10.2, '每下沉十米，就多压上一个大气压。', 'Every ten metres adds another atmosphere.']],
  sfx: [[0, 'whoosh', { dur: 1 }], [1, 'tick'], [1.3, 'tick'], [1.6, 'tick'], [5.4, 'drop', { dur: 1.2 }]],
  draw(t, d) {
    const depth = ease.inOut(progress(t, .8, 8.6)) * 7000;
    for (let i = 0; i < 40; i++) {                    // particles rise past the sinking probe
      const y = ((hash(i) * H - t * 120 * (.5 + hash(i + 9))) % H + H) % H;
      glow(W * (.06 + .5 * hash(i + 50)), y, 6, SEA, .35);
    }
    glow(W * .3, lerp(H * .2, H * .62, depth / 7000), 60, PALE, .9);
    text(typed('PROBE // DEPTH LOG', progress(t, 1, .8)), W * .64, H * .27, { font: FONT.mono, size: 26, ls: 4, color: SEA, alpha: .8 });
    text(`${count(depth, 1)} m`, W * .64, H * .4, { font: FONT.math, size: 120, color: INK, glow: rgba('#2fd3c0', .5), blur: 30 });
    text(`${count(1 + depth / 10, 1)} atm`, W * .64, H * .4 + 110, { font: FONT.math, size: 54, color: SEA, alpha: fade(t, 5.4, d, .5, .5) });
  },
});

// ---------------------------------------------------------------- 4. sonar: a ping every bar, the echoes draw a ridge
scene({
  name: 'sonar', bars: 4, chapter: ['II', '声呐', 'SONAR'],
  backdrop: { kind: 'aurora', tint: '#2be0c8', tint2: '#1b3a8f', amount: .35 },
  music: { chords: ['F', 'C', 'G', 'Am'], energy: 3 },
  subs: [[.8, 5, '在没有光的地方，它用声音看世界。', 'Where there is no light, it sees with sound.'],
    [5.4, 10.2, '回声一点点勾出海底山脊的轮廓。', 'The echoes slowly trace an undersea ridge.']],
  sfx: [0, 1, 2, 3].map(k => [.8 + k * BAR, 'chime', { note: 'A5', gain: .6 }]),
  draw(t, d) {
    const sx = W / 2, sy = H * .3;
    ctx.save(); ctx.globalCompositeOperation = 'lighter'; ctx.lineWidth = 4;
    for (let k = 0; k < 4; k++) for (let j = 0; j < 3; j++) {   // each ping is a pulse of three rings
      const r = (t - .8 - k * BAR) * 420 - j * 26;
      if (r <= 0) continue;
      ctx.strokeStyle = rgba(SEA, (.9 - j * .25) * Math.max(0, 1 - r / 1400));
      ctx.beginPath(); ctx.arc(sx, sy, r, 0, TAU); ctx.stroke();
    }
    ctx.restore();
    glow(sx, sy, 40, PALE, 1);
    const ridge = progress(t, 5.4, 4.4);
    if (ridge <= 0) return;
    ctx.save(); ctx.strokeStyle = rgba('#2fd3c0', .9); ctx.lineWidth = 3; ctx.shadowColor = '#2fd3c0'; ctx.shadowBlur = 14;
    ctx.beginPath();
    for (let x = W * .08; x <= W * (.08 + .84 * ridge); x += 12) {
      const y = H * .76 - 160 * Math.exp(-(((x - W * .55) / 260) ** 2)) - 40 * noise(x / 140);
      x === W * .08 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }
    ctx.stroke(); ctx.restore();
  },
});

// ---------------------------------------------------------------- 5. hull: a rotating 3D shell; a mid-scene hit when the load lands
scene({
  name: 'hull', bars: 3, chapter: ['III', '结构', 'HULL'], hits: [[4.2, .5]],
  backdrop: { kind: 'silk', tint: '#2a6f7a', tint2: '#06121c', amount: .45 },
  music: { chords: ['Dm', 'Am', 'E', 'Am'], energy: 3 },
  subs: [[.6, 3.8, '二十个三角面，一起扛住七百个大气压。', 'Twenty triangles share seven hundred atmospheres.'],
    [4.2, 7.6, '压力落下时，每一条棱同时受力。', 'When the pressure lands, every edge takes it at once.']],
  sfx: [[4.2, 'swell', { dur: 1.5 }]],
  draw(t, d) {
    const cam = { yaw: t * .5, pitch: .35 + .1 * Math.sin(t * .7), dist: 5, y: H * .44 };
    const grow = smooth(.2, 1.4, t), load = fade(t, 4.2, d, .3, .6);
    wire(POLY.icosa, cam, { scale: 1.6 * grow, color: SEA, alpha: .9 });
    if (load > 0) wire(POLY.icosa, cam, { scale: 1.6 * grow, color: '#ffd28c', alpha: load * (.6 + .4 * Math.sin(t * 12)), width: 3.5, nodes: false });
  },
});

// ---------------------------------------------------------------- 6. life: glowing creatures appear, then gather around the station
scene({
  name: 'life', bars: 4, chapter: ['IV', '生命', 'LIFE'], hits: [[0, .7]],
  backdrop: { kind: 'nebula', tint: '#1f8a8a', tint2: '#3b1f7a', amount: .6 },
  music: { chords: ['Am', 'F', 'C', 'G'], energy: 4 },
  subs: [[.8, 5, '可在这片黑暗里，发光的不只是它。', 'Yet in this dark, it is not the only thing that glows.'],
    [5.4, 10.2, '一群发光的生物，正慢慢围拢过来。', 'A swarm of glowing creatures gathers around it.']],
  sfx: [[0, 'riser', { dur: 2 }], [.8, 'sparkle', { dur: 3 }], [5.4, 'swell', { dur: 2 }]],
  draw(t, d) {
    const cx = W / 2, cy = H * .42, r = rng(9), gather = ease.inOut(progress(t, 5.4, 3.5));
    glow(cx, cy, 70, PALE, 1);
    for (let i = 0; i < 90; i++) {
      const a0 = r() * TAU, d0 = 300 + r() * 600, show = fade(t, .8 + r() * 3, 99, .8, .1), ph = r() * TAU, ring = TAU * i / 90 + t * .2;
      const x = lerp(cx + Math.cos(a0 + t * .05) * d0, cx + Math.cos(ring) * 230, gather);
      const y = lerp(cy + Math.sin(a0 + t * .05) * d0 * .55, cy + Math.sin(ring) * 130, gather);
      glow(x, y, 22, i % 3 ? SEA : '#c79bff', show * (.5 + .5 * Math.sin(t * 3 + ph)));
    }
  },
});

// ---------------------------------------------------------------- 7. finale: rays, the name again, the last line (no subtitles, so a sentence card)
scene({
  name: 'finale', bars: 3, letterbox: true, hits: [[0, 1]], fade: [.35, 1.5],
  backdrop: { kind: 'nebula', tint: '#1f8a8a', tint2: '#0b2a4a', amount: .6 },
  music: { chords: ['F', 'G', 'Am'], energy: 4 },
  sfx: [[2.6, 'chime', { note: 'A5' }]],
  draw(t, d) {
    const y = H / 2 - 60;
    rays(W / 2, y, t, { count: 28, alpha: .35 * fade(t, 0, d, 1, 1.5), color: '#9ff3e8' });
    title('海渊', W / 2, y, { size: 260, t, stagger: .12, dur: 1, metal: 'silver' });
    text('ABYSS-7', W / 2, y + 190, { font: FONT.display, size: 30, ls: 22, color: SOFT, alpha: fade(t, 1.2, d, .8, 1.4) });
    text('在最深的黑暗里，我们点亮一盏灯。', W / 2, y + 275, { size: 40, weight: 700, ls: 6, color: INK, alpha: fade(t, 2.6, d, .8, 1.4) });
    text('In the deepest dark, we light one lamp.', W / 2, y + 335, { font: FONT.italic, style: 'italic', weight: 500, size: 28, color: SOFT, alpha: fade(t, 3, d, .8, 1.4) });
  },
});
