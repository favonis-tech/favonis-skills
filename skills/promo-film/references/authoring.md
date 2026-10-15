# Writing a promo film

A film is one JavaScript file, normally `promo/<slug>/film.js`. It calls `film()` once, then `scene()` once per shot, in order. The engine plays the scenes back to back on a bar grid, draws each frame with the scene's `draw(t, d)`, adds the backdrop, camera, film grade, letterbox, chapter card, subtitles and hit flashes, and exports the timing for the score. [example.js](example.js) is a complete 70-second film; read it before writing the first film of a conversation.

## Rules that keep frames correct

- **A frame depends only on time.** `draw(t, d)` must give the same picture for the same `t`, whether frames are played live, rendered out of order or rendered twice for motion blur. Derive every position from `t`. Use `rng(seed)` or `hash(n)` for randomness, never `Math.random()`, `Date` or `performance.now()`, and never keep state between calls.
- **Design units.** The frame is `W × H` (1920 × 1080 by default, origin top left). The engine scales to the output size; never read the canvas size.
- **`ctx` is the 2D context** of the current frame, already transformed by the camera and wrapped in `save()`/`restore()`. Draw with the helpers below or with plain Canvas 2D calls.
- **Call `film()` before the first `scene()`**; `BEAT` and `BAR` are valid after it. The file runs in strict mode inside a block, so its top-level names never clash with the engine's.
- **Precompute outside `draw`.** Point sets, paths, gradients that do not change and other expensive work belong at the top level or in a cache; `textPoints()` caches by itself. Keep particle counts in the low thousands and `shadowBlur` on a few elements: the sandbox renders on the CPU.

## film(options)

| Option | Default | Meaning |
| --- | --- | --- |
| `title`, `tagline` | `''` | Shown on the player's cover and as the page title. |
| `size` | `[1920, 1080]` | Design size. `[1080, 1920]` for vertical video. |
| `bpm` | `90` | Tempo of the bar grid. 80–100 for epic or documentary, 110–128 for tech and product films. |
| `grade` | `'neutral'` | Colour grade: `neutral`, `gold`, `teal`, `cool`, `noir`. |
| `bloom`, `grain`, `vignette` | from the grade | Override the grade's glow (0–1.5), film grain (0–1) and vignette (0–1). |
| `tail` | `2` | Seconds after the last scene for the music to ring out. |
| `poster` | middle of scene 2 | Film time shown on the player cover. |
| `music` | `{ style: 'cinematic' }` | Score style for the timeline export: `cinematic` or `electronic`; `false` for a film without a synthesized score. |

## scene(options)

| Option | Meaning |
| --- | --- |
| `name` | Shown in reports and errors. Use short slugs such as `cold-open`. |
| `bars` | Length in bars, a multiple of 0.25 (one beat). Scene length is `bars * BAR` seconds. |
| `draw(t, d, T)` | Draws the frame: `t` seconds into the scene, `d` its duration, `T` film time. |
| `backdrop` | WebGL background behind `draw`: `'nebula'`, `'aurora'`, `'grid'`, `'silk'`, an object `{ kind, tint, tint2, amount, speed, seed }`, or a function `(t, d) => object` to animate it. Omit for black. |
| `camera` | `'push'` (default, slow push-in with drift), `'pull'`, `'arc'`, `'drift'`, `'still'`, or `(t, d) => ({ x, y, z, r })`. |
| `fade` | `[in, out]` seconds to and from black, default `[.35, .35]`. `[0, 0]` for hard cuts. |
| `hits` | `[[t, strength], ...]`: a white flash, a camera shake and, in the score, an impact. Strength 0.3–1. |
| `letterbox` | `true` for 2.39:1 cinema bars; they slide between scenes. Good for the cold open and the finale. |
| `chapter` | `['I', '对称', 'SYMMETRY']`: numeral, title and optional small caps line, shown top left for the first 5 s. |
| `subs` | `[[start, end, text, secondLine], ...]` in scene seconds. The second line is optional, usually the translation. |
| `sfx` | `[[t, name, { dur, gain, pan, note }], ...]` sound effects for the score; names are listed below. |
| `music` | `{ chords: ['Dm', 'Bb', 'F', 'C'], energy: 0–4 }`, one chord per bar, cycled. A scene without `music` continues the previous one. |
| `blur` | Motion-blur samples in renders (default 2; `1` turns it off for flash cuts, counters and dense text, where blending two frames shows double digits or letters). |
| `grade` | Per-scene overrides: `bloom`, `grain`, `vignette`, `sat`, `contrast`, `threshold`, `aberration`, `lift`, `gain`. |

Sound effect names: `heart`, `hit`, `boom`, `riser`, `reverse`, `swell`, `whoosh`, `sparkle`, `chime`, `tick`, `glitch`, `drop`. `riser`, `reverse` and `swell` end at `t + dur`, so start them `dur` seconds before the moment they lead into. Hits already sound; do not add a `boom` on the same moment.

## Helpers

Time and maths:

| Helper | Use |
| --- | --- |
| `fade(t, a, b, fi = .4, fo = .4)` | 0→1 from `a` over `fi` seconds, 1→0 ending at `b`. The usual alpha for anything on screen. |
| `progress(t, start, dur)` | 0–1 progress of an animation, clamped. Pass it through `ease.out`, `ease.inOut`, `ease.expo`, `ease.back`, `ease.in` or `ease.sine`. |
| `smooth(a, b, x)`, `clamp`, `lerp` | Smoothstep, clamp to 0–1 by default, linear interpolation. |
| `rng(seed)`, `hash(n)`, `noise(x)` | Seeded generator returning 0–1; hash of a number to 0–1; smooth 1D noise in −1…1. |
| `rgba('#e2bd6b', a)` | Hex colour with alpha. |

Text (sizes in design pixels; returns the drawn width):

| Helper | Use |
| --- | --- |
| `text(str, x, y, o)` | `o`: `size`, `font`, `weight`, `style` (`'italic'`), `color`, `alpha`, `align` (`center`/`left`/`right`), `base`, `ls` (letter spacing), `glow` + `blur`, `stroke` + `lineWidth`. |
| `title(str, x, y, o)` | Metal title, characters rising in one by one with a highlight sweep. `o`: `size`, `t` (seconds since the reveal starts), `stagger`, `dur`, `metal` (`gold`, `silver`, `rose`) or flat `color`, `ls`, `font`, `weight`. |
| `glitch(str, x, y, o)` | RGB-split glitch word for flash cuts; `o.t` animates it, `o.seed` varies it. |
| `textBlock(str, x, y, o)`, `lines(str, width, o)` | Wrapped paragraph centred on `y` (`o.width`, `o.lineHeight`); line breaking alone. CJK breaks per character, Latin per word. |
| `typed(str, k)`, `count(value, k, { decimals })` | Typewriter prefix at progress `k`; number counting up to `value`, with thousands separators. |
| `measure(str, o)` | Width without drawing. |

Fonts in `FONT`: `serif` (Noto Serif CJK SC, the default; titles and Chinese copy), `sans` (Noto Sans CJK SC; product and tech films), `display` (Cinzel, Roman capitals for English titles and chapter lines), `italic` (Cormorant Garamond; pass `style: 'italic'` for English secondary lines), `math` (STIX Two Text; numbers, formulas, units), `mono` (Noto Sans Mono). The build embeds only the characters the film file contains, so text assembled at runtime from characters that appear nowhere in the file falls back to a system font.

Light and particles:

| Helper | Use |
| --- | --- |
| `glow(x, y, r, color, a)` | Soft additive light. |
| `flare(x, y, a, { len, color })` | Anamorphic lens streak with a glow. |
| `rays(x, y, t, { count, alpha, color, speed })` | Rotating sunburst, for finales. |
| `stars(t, { count, speed, seed, alpha })` | Drifting, twinkling starfield. |
| `textPoints(str, { size, step, font, weight })` | Points sampled from text, centred on the origin. |
| `shapePoints('ring' / 'spiral' / 'disc', n, { r })` | Points on simple shapes. |
| `assemble(points, t, { x, y, dur, stagger, spread, size, color, reverse })` | Particles flying in from a scatter to the points; `reverse: true` scatters them. |

3D: `project([x, y, z], { yaw, pitch, roll, dist, f, x, y })` returns `{ x, y, k, z }` (`k` scales sizes with depth); `rot3(p, yaw, pitch, roll)`; `wire(POLY.icosa, cam, { scale, color, alpha })` draws a glowing wireframe of `POLY.tetra`, `cube`, `octa` or `icosa` and returns the projected vertices.

## Craft

- **Structure.** A cold open that poses a question or flashes through the film in 2–4 bars; the title in 2–3 bars; three to five chapters of 3–4 bars, each with one idea and one image; a finale that returns to the title and lands the last line. 45–75 seconds is the sweet spot; split anything over two minutes into several films.
- **Rhythm.** Cut and reveal on bar or beat boundaries (`BAR`, `BEAT`, `BEAT / 2`). Put hits on scene starts that reveal something. Raise `energy` across the film (1 intro, 2 build, 3 drive, 4 climax), drop it for a breath before the finale, and keep the finale at 4 or let it resolve at 2–3.
- **Screen text.** One line of large text per moment. At 1080p: titles 120–420, headlines 54–88, body 36–48, small caps 16–34 with generous `ls`; nothing under 24. Keep text inside the middle 94 % of the frame and above the subtitle band (the bottom 150 px) while subtitles show; `check` reports violations.
- **Subtitles** carry the narration. Up to about 18 Chinese characters or 9 English words per subtitle, on screen at least 1.5 s, no more than 7 characters or 3 words per second. Do not repeat on-screen text in the subtitles.
- **Look.** One backdrop and one accent colour per scene; pick the grade to suit the subject (`gold` for history and science, `teal` or `cool` for tech, `noir` for drama). Additive light (`glow`, `'lighter'` composite) on black reads as cinematic; large flat bright areas do not.
- **Vertical video** (`size: [1080, 1920]`): stack elements vertically, keep titles under about 8 Chinese characters per line, and leave the top and bottom 200 px clear for platform UI.

## check issues

| Kind | Meaning and fix |
| --- | --- |
| `clipped` | Text extends outside the frame. Reduce the size, wrap it with `textBlock`, or move it. |
| `edge` | Text sits within 3 % of the frame edge. Move it inward unless the edge position is deliberate. |
| `under-subtitle` | Text is in the subtitle band while a subtitle is showing. Move it up or time it apart. |
| `subtitle-too-fast` | Reading speed too high. Lengthen the subtitle or shorten the line. |
| `subtitle-past-scene` | A subtitle ends after its scene. Move it into the next scene's `subs`. |
| `subtitle-overlap` | Two subtitles show at once. |

A JavaScript error stops the check and reports the scene, its local time and the `film.js` line. A syntax error reports the line from Node's parser.
