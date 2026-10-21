# Engine API

A film is one JavaScript file, normally `promo/<slug>/film.js`. It calls `film()` once, then `scene()` once per section of the bible's timeline, in order. The engine plays the scenes back to back, draws each frame with the scene's `draw(t, d, T)`, adds scene fades and subtitles, and synthesizes the soundtrack from the voices, dialogue, effects and music the file declares. [example.js](example.js) is a complete 74-second film built from [example-bible.md](example-bible.md); [craft.md](craft.md) covers story, copy, look, motion, sound and review.

## Rules that keep frames correct

- **A frame depends only on time.** `draw(t, d, T)` must give the same picture for the same time, whether frames are played live, rendered out of order or rendered twice. Derive every position from time. Use `rng(seed)` or `hash(n)` for randomness, never `Math.random()`, `Date` or `performance.now()`, and never keep state between calls.
- **State that lasts across scenes is a table of events in film seconds** (who left a queue when, which message arrived when), replayed by a function of `T`. `scene()` returns `{ start, end }`, so tables can be written as `queue.start + 4.2` after the scenes are declared; `draw` runs only after the whole file has executed.
- **Design units.** The frame is `W × H` (1920 × 1080 by default, origin top left). The engine scales to the output size; never read the canvas size.
- **`ctx` is the 2D context** of the current frame, wrapped in `save()`/`restore()` and transformed by the scene's camera. Draw with the helpers below or with plain Canvas 2D calls.
- **Call `film()` before the first `scene()`.** The file runs in strict mode inside a block, so its top-level names never clash with the engine's.
- **Precompute outside `draw`.** Sprites, shuffled orders and event tables belong at the top level.

## film(options)

| Option | Default | Meaning |
| --- | --- | --- |
| `title`, `tagline` | `''` | Shown on the player's cover and as the page title. |
| `size` | `[1920, 1080]` | Design size. `[1080, 1920]` for vertical video. |
| `bg` | `'#16120f'` | Background of every frame and the colour scenes fade to. |
| `tail` | `1.5` | Seconds after the last scene; the sound fades out over the end. |
| `poster` | 60 % into scene 2 | Film time shown on the player cover. Pick a frame that tells the story. |
| `subtitle` | serif 44px `#f3ece4`, dark halo, baseline `H − 80` | `{ font, size, weight, color, shadow, y, second }`; on a light background use a dark `color` and a light `shadow`. |
| `voices` | `{}` | `{ name: { tone, notes, cps, gain } }` for everyone who speaks: `tone` is `square`, `triangle`, `sine`, `key` (a keyboard click) or `none`; `notes` the pitches a line's characters cycle through (default `C5 D5 E5 G5 A5`); `cps` characters per second (default 12). |
| `music` | `false` | `{ bpm, chords, energy, gain }`: a soft pad on a bar grid, one chord per bar, cycled. `energy` 0 silence, 1 pad and a pluck on each chord, 2 adds an arpeggio. |

## scene(options)

| Option | Meaning |
| --- | --- |
| `name` | Shown in reports and errors. Short slugs such as `hook`. |
| `dur` | Length in seconds. |
| `draw(t, d, T)` | Draws the frame: `t` seconds into the scene, `d` its length, `T` film time. |
| `subs` | `[[start, end, text, secondLine?], ...]` in scene seconds. |
| `say` | `[[t, who, text, { cps, silent, tag }?], ...]`: a line of dialogue starting at scene second `t`. Its characters appear at the voice's `cps` and each one plays the speaker's voice; `silent` mutes it; `tag` travels with the line so `draw` knows where to put its bubble. |
| `sfx` | `[[t, name, { gain, note, to, dur }?], ...]` sound effects in scene seconds; names below. |
| `music` | Overrides `film().music` from the first bar that starts in this scene: `{ chords, energy }`, or `false` for silence. Later scenes without `music` continue it. |
| `fade` | `[in, out]` seconds from and to the background colour, default `[0, 0]`. |
| `camera` | `(t, d) => ({ x, y, z })`: offset and zoom around the frame centre, for a slow push onto one element. |
| `bg` | Background colour for this scene only. |

`sound(T, name, options)` adds an effect at film time `T`, for events kept in film-time tables.

## Time and motion

| Helper | Use |
| --- | --- |
| `fade(t, a, b, fi = .4, fo = .4)` | 0→1 from `a` over `fi` seconds, 1→0 ending at `b`. The usual alpha. |
| `progress(t, start, dur)` | 0–1 progress, clamped; pass it through `ease.out`, `ease.inOut`, `ease.in`, `ease.back` or `ease.sine` for interface motion. |
| `stepped(x, fps = 12)` | Time rounded down to a 12 fps clock: pixel motion moves in visible steps. |
| `hop(t, at, { height, dur })` | Cells to lift a character for a stepped jump starting at `at` (a time or a list of times); default 2 cells over 0.35 s. |
| `blinking(T, { seed, every, dur })` | True while a seeded blink is on (every 2.5–4.5 s, 0.12 s long). |
| `breathe(t, { period, hold })` | 1 during the last `hold` seconds of each `period` (default 0.4 of 1.6 s), else 0. |
| `smooth`, `clamp`, `lerp`, `rng(seed)`, `hash(n)`, `noise(x)`, `rgba('#hex', a)` | Maths, seeded randomness, colour with alpha. |

## Text

Sizes are design pixels; text is vertically centred on `y` unless `base` says otherwise.

| Helper | Use |
| --- | --- |
| `text(str, x, y, o)` | `str` is a string or coloured parts `[['只是旁边，有', ink], ['两队', red]]`. `o`: `size`, `font`, `weight`, `color`, `alpha`, `align` (`center`/`left`/`right`), `base`, `ls` (letter spacing), `glow` + `blur` (a halo), `stroke` + `lineWidth`, `upto` (draw only the first n characters, laid out as the whole line so typing never shifts it). Returns the width. |
| `textBlock(str, x, y, o)`, `lines(str, width, o)` | Wrapped paragraph centred on `y` (`o.width`, `o.lineHeight`); line breaking alone. |
| `typed(str, k)`, `count(value, k, { decimals })`, `measure(str, o)` | Prefix at progress `k`; a number counting up; width without drawing. |

Fonts in `FONT`: `serif` (Noto Serif CJK SC: subtitles, titles, sentence cards), `sans` (Noto Sans CJK SC, the default: interface, labels, dialogue), `mono` (Noto Sans Mono: clocks, counters, file names), `math` (STIX Two Text: numbers and formulas). The build embeds only the characters that appear in the film file, so text assembled at runtime from characters that appear nowhere in the file falls back to a system font.

## Dialogue

| Helper | Use |
| --- | --- |
| `dialogue(T, { who, since, until, last })` | Lines started by `T`, oldest first: `{ who, text, full, shown, start, end, typing, tag }`, where `text` is what has typed so far and `shown` its length. Filter by speaker (a name or a list), by start time in film seconds, or keep the `last` n. Draw `full` with `upto: shown` so the line keeps its place while it types. |
| `speaking(T, who)` | True while one of `who`'s lines is typing: drive the talking pose with it. |

## Interface and diagrams

| Helper | Use |
| --- | --- |
| `panel(x, y, w, h, o)` | A window or card: `fill`, `stroke` (`false` for none), `lineWidth`, `radius` (18), `shadow` (`true` or a colour), `alpha`, `title` with `bar` height, `titleSize`, `titleColor`, `dots` (three window dots). Returns the content rect below the title bar. |
| `chip(str, x, y, o)` | A label with a filled background: tags, token blocks, price tags. `size`, `font`, `weight`, `fill` (`false` for none), `outline`, `color`, `radius` (8), `pad`, `align`, `alpha`, `upto`. Returns its rect. |
| `bubble(str, x, y, o)` | A speech bubble whose tail tip is at `(x, y)`, above it unless `side: 'below'`; sized to the whole line, so pass `upto: line.shown` while it types. `size`, `fill`, `stroke`, `color`, `shift` (move the body sideways), `alpha`. Returns its rect. |
| `cells(x, y, cols, rows, o)` | A grid of squares: a context window, a tally, a bar chart. `size` (22), `gap` (4), `radius`, `alpha`, `color` (a colour or `(i, col, row) => colour or null`). Returns `{ w, h, at(i) }`. |
| `arrow(x0, y0, x1, y1, o)` | `k` (0–1 drawn), `dash`, `width`, `head`, `color`, `alpha`. |
| `caret(x, y, h, T, o)` | A blinking block cursor. |
| `dotgrid(o)`, `vignette(a, color)`, `glow(x, y, r, color, a)` | A dot-grid backdrop (`gap`, `size`, `color`, `alpha`), darkened corners, a soft light. |
| `roundRect(x, y, w, h, r)` | Rounded-rectangle path for your own fills and strokes. |

## Pixel sprites

`sprite(rows, palette)` turns a list of strings into a sprite: each character is a cell, `.` or a space is empty, every other character needs a colour in `palette`.

`pixels(sp, x, y, o)` draws it with each cell snapped to device pixels, crisp at any size. `x, y` is the bottom centre by default (`anchor: 'bottom'`; also `'center'` and `'top-left'`).

| Option | Meaning |
| --- | --- |
| `cell` | Pixels per cell (10). |
| `edits` | `[[row, col, char], ...]` changes for this frame: closed eyes, eyes that look aside, a raised arm, a lifted foot. `'.'` clears a cell. |
| `offset(row, col)` | `[dx, dy]` in cells, to move part of the body, for example the torso down one cell when breathing. |
| `palette` | Colour overrides: one sprite, many clothes. |
| `reveal`, `seed` | 0–1: cells appear in a seeded random order. |
| `flip`, `alpha` | Mirror horizontally; opacity. |

It returns the drawn rect. Keep a character's poses as functions of time that return `edits`, as `drawBean` does in the example.

## Sounds

| Name | Sound | Options |
| --- | --- | --- |
| `key` | Keyboard click; typing on sentence cards, blocks landing | `gain` |
| `tick` | Short dry tick; counting, clocks | `gain`, `dur` |
| `click` | Switch or lock click | `gain` |
| `pop` | Something appears | `gain`, `dur` |
| `blip` | Short square note; scanner beeps, UI | `note` (`E5`), `gain`, `dur` |
| `chime` | Bell; a reveal or a sentence card | `note` (`G5`), `gain`, `dur` |
| `ding` | Two rising notes; a counter goes up | `gain` |
| `success` | Four rising notes | `gain` |
| `sad` | Two falling notes; a mistake | `gain` |
| `drop` / `rise` | Sliding note down / up; something falls out, something springs up | `note`, `to`, `dur`, `gain` |
| `thump` | Low thud; something is full or heavy | `gain`, `dur` |
| `whoosh` | Air; fast moves and switches | `gain`, `dur` |
| `scratch` | Pen or paper rustle | `gain`, `dur` |
| `tone` | Any note | `note`, `to`, `wave` (`sine`, `triangle`, `square`), `dur`, `gain` |

Notes are written like `E5` or `F#4`; chords as a root `A`–`G` with optional `#` or `b` and one of: major (no suffix), `m`, `5`, `sus2`, `sus4`, `dim`, `aug`, `6`, `m6`, `7`, `maj7`, `m7`, `add9`, `madd9`, `9`, `maj9`, `m9`. The mix is normalized and softly limited, so effects can overlap without clipping.
