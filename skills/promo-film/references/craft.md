# Promo film craft and review

[api.md](api.md) lists what the engine offers; this file covers how to use it well and how to review a film before delivery.

## Structure and rhythm

- **Structure.** A cold open that poses a question or flashes through the film in 2–4 bars; the title in 2–3 bars; three to five chapters of 3–4 bars, each with one idea and one image; a finale that returns to the title and lands the last line. 45–75 seconds is the sweet spot; split anything over two minutes into several films.
- **Rhythm.** Cut and reveal on bar or beat boundaries (`BAR`, `BEAT`, `BEAT / 2`). Put hits on scene starts that reveal something. Raise `energy` across the film (1 intro, 2 build, 3 drive, 4 climax), drop it for a breath before the finale, and keep the finale at 4 or let it resolve at 2–3.

## Motion

- **The picture shows what the subtitle says, while it says it.** Whatever a line of narration describes happens on screen during that line.
- **Spread the action over the whole scene.** Do not reveal everything in the first second and hold. Give each subtitle its own beat of action, and between reveals keep something changing: a highlight walking through the items, a slow build-up, particles drifting, a value counting. `check` reports `static` stretches of 3 seconds or more; camera drift counts as movement, subtitles do not.
- A deliberate hold, such as the final title, still breathes: rays turning, a glow pulsing, stars drifting.

## Layout

- **Screen text.** One line of large text per moment. At 1080p: titles 120–420, headlines 54–88, body 36–48, small caps 16–34 with generous `ls`; nothing under 24. Keep text inside the middle 94 % of the frame and above the subtitle band (the bottom 150 px) while subtitles show; `check` reports violations.
- **Narration lives in the subtitles.** While subtitles run, on-screen text is a title, a label, a number or a formula, not a sentence: a sentence competes with them, and placed just above them it reads as part of them. A sentence card, such as the opening question or the last line, belongs in a scene without subtitles.
- **Subtitles** carry the narration. Up to about 18 Chinese characters or 9 English words per subtitle, on screen at least 1.5 s, no more than 7 characters or 3 words per second. Do not repeat on-screen text in the subtitles.
- **Look.** One backdrop and one accent colour per scene; pick the grade to suit the subject (`gold` for history and science, `teal` or `cool` for tech, `noir` for drama). Additive light (`glow`, `'lighter'` composite) on black reads as cinematic; large flat bright areas do not.
- **Vertical video** (`size: [1080, 1920]`): stack elements vertically, keep titles under about 8 Chinese characters per line, and leave the top and bottom 200 px clear for platform UI.

## Sound

- **One key for the whole film.** Take every scene's chord loop from the same key: D minor `Dm Bb F C`, `Gm Dm Bb A`, `Bb F C Dm`; A minor `Am F C G`, `Dm Am E Am`; C major `C G Am F`, `F C G Am`. The score report warns when neighbouring scenes change key.
- **Effects mark events on screen.** Hits on reveals; lead-ins (`riser`, `reverse`, `swell`) landing on scene starts or hits; `whoosh` on fast moves; `tick` on typing and counters; `chime` or `sparkle` on small reveals. At most two effects at the same moment. `check` reports `double-impact` and `lead-in-off-beat`.

## Review

Run `check` with a contact sheet and go through this list before building:

1. The sheet has a frame in the middle of every subtitle, with that subtitle on screen, and one frame for each scene without subtitles; past eight frames it comes in pages, listed in `sheets`. Open every page. For each frame, write down what is on screen, check that the picture shows what its subtitle says at that moment, and look for anything clipped, covered or hard to read.
2. For a subtitle that describes a change, also open the moment it starts with `--at` (a single frame comes out full size): the change has to happen while the subtitle is on screen, and nothing may contradict the subtitle before it does.
3. Fix what you found and every `issues` entry. After the last edit, run `check` again and look at the frames of every scene you changed; build only when that pass is clean.

## check issues

| Kind | Meaning and fix |
| --- | --- |
| `clipped` | Text extends outside the frame. Reduce the size, wrap it with `textBlock`, or move it. |
| `edge` | Text sits within 3 % of the frame edge. Move it inward unless the edge position is deliberate. |
| `under-subtitle` | Text is in the subtitle band while a subtitle is showing. Move it up or time it apart. |
| `subtitle-too-fast` | Reading speed too high. Lengthen the subtitle or shorten the line. |
| `subtitle-past-scene` | A subtitle ends after its scene. Move it into the next scene's `subs`. |
| `subtitle-overlap` | Two subtitles show at once. |
| `static` | Nothing changes for `seconds` from `at`. Add the motion the narration describes, spread the reveals, or shorten the scene. |
| `double-impact` | A `boom` or `hit` sits on a hit, which already sounds. Remove the effect. |
| `lead-in-off-beat` | A lead-in lands on nothing. Move its `t` to a scene start (`t: 0`), a hit, a subtitle start or a beat. |
| `text-overlap` | Two texts overlap at `at`. Move or shrink one, or show them at different times. |

A JavaScript error stops the check and reports the scene, its local time and the `film.js` line. A syntax error reports the line from Node's parser.
