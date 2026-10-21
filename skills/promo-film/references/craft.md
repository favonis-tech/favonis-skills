# Craft and review

[api.md](api.md) lists what the engine offers; this file covers how to design a film that is worth watching, how to write its bible, and how to review it before delivery. [example-bible.md](example-bible.md) and [example.js](example.js) show one film carried through all of it.

## The bible

Write `promo/<slug>/bible.md` before any code, in the language of the film. It has these sections, each concrete enough that someone else could build the film from it without asking anything:

1. **Logline.** One or two sentences: who, what happens, what the viewer learns.
2. **Story.** A table of beats: hook, setup, escalation, turn, payoff, closing line; one row each, saying what happens on screen.
3. **Accuracy.** The facts the film claims and the simplifications it makes. Anything simplified on screen carries a small "示意" or "illustrative" note.
4. **World and characters.** The visual metaphor and who lives in it.
5. **Look.** Palette as hex values with their roles; fonts by role; a layout map with the coordinates of every recurring element (panels, the world, where characters stand, labels, counters, the knowledge card, the subtitle band).
6. **Characters.** The pixel grid of every sprite, and each pose as the cells it changes.
7. **Sound.** Each speaker's voice (tone, notes, speed), the effect for each kind of event, the music (tempo, chords, energy per scene).
8. **Timeline.** One section per scene with its film span and length. Inside, in scene seconds: every action, every line of dialogue, every subtitle and every sound, with the exact words.

## Story

- **Find the story before the facts.** A protagonist the viewer can root for (a character, an object, or "you"), something it wants, obstacles that get worse, and the explanation arriving at the moment the story needs it. A list of facts with pictures is a slideshow, not a film.
- **Hook in the first five to eight seconds:** a question, the surprising end state shown first, or a familiar annoyance. The title can be the hook; a title card that only names the topic is not.
- **Turn the subject into a world** the viewer already knows, where each concept becomes something that moves: a room that fills up with blocks for a context window, checkout lanes for probability, a kitchen line for a pipeline, a post office for a network. The world is also the diagram, so the explanation happens inside the story.
- **One concept per beat**; three to five concepts in a two-to-three-minute film. Introduce each where the story trips over it, either in the world or on a knowledge card.
- **A running gag that escalates**: a counter that keeps going up, a line that keeps coming back, the same mistake in a new place. Pay it off at the end.
- **Close with a callback** that answers the hook, on a quiet sentence card without subtitles. A film that teaches several things may end on a card that lists them and credits the cast.
- **Never let the metaphor claim something false.** If the drama needs an exaggeration, keep it visibly playful and keep the narration accurate.

## Copy

- **Subtitles carry the narration** as short spoken sentences: up to about 18 Chinese characters or 9 English words, one line, on screen at least 1.5 s, at most 5 characters or 3 words per second. No second-language line unless the user asks for one.
- **Concrete and specific**: numbers, days, names, the subject's own words ("第八天", "212 次", "价签扫不出来"). Humour comes from situations, not from jokes in the narration. Avoid stock phrases ("让我们一起", "在这个……的时代", "揭开……的神秘面纱", "你知道吗"), chains of rhetorical questions, and summary sentences that repeat what the picture just showed.
- **Dialogue is what characters say on screen**, typed into bubbles, chat windows or terminals: short and in character. Narration stays in the subtitles; the two never repeat each other.
- **While subtitles run, on-screen text is a label, a name, a number or dialogue**, never a sentence that competes with the subtitle. Sentence cards belong to scenes without subtitles.

## Look

- **Take the art direction from the subject's own visual world**: its interface, tools, materials and places. Pick one style and keep it for the whole film: pixel art, flat interface panels, paper cut-outs, blueprint lines, chalk on a board. Light or dark as the subject suggests.
- **A small palette with fixed roles**: background, surface, line, ink, secondary ink, one accent, one highlight, one warning. Every scene uses the same roles.
- **Not "cinematic" by default.** Gradient or metallic text, glows on black, lens flares, starfields and particle titles make every film look the same; use light effects only when the subject is light, space or fire.
- **Fonts by role**: serif for subtitles, titles and sentence cards; sans for interface, labels and dialogue; mono for clocks, counters and file names; math for numbers and formulas.

## Layout

- The frame is 1920 × 1080 design units. Keep 96 px side margins; the band below y = 900 belongs to the subtitles whenever they show.
- **The layout map is fixed**: the main panel, the world, where characters stand, the counter and the cards stay in the same place from scene to scene, so the viewer always knows where to look.
- **Sizes at 1080p**: sentence cards 56–72, titles 80–110, headings 40–48, interface text and dialogue 26–34, labels 22–28; nothing under 22.
- **Knowledge cards**: a centred panel of about 1280 × 580, a tag chip and a heading at the top left, the diagram in the middle, an "illustrative" note at the bottom; dim the world behind it to 25–35 % and bring it back afterwards.
- **Persistent labels give a sense of progress**: a day or time at the top left, a running counter at the top right.
- **Vertical video** (`size: [1080, 1920]`): stack the world and the panels vertically, keep the top and bottom 200 px clear for platform UI, and keep sentence cards under about 8 Chinese characters per line.

## Characters

- **A protagonist with a face.** A pixel sprite of about 12–20 by 8–12 cells drawn at 10–14 px per cell, or a few simple shapes. The eyes do most of the acting.
- **Poses are edits of the grid**, chosen by time: blink, look left, right, up or down, surprise (taller eyes and a "!"), sad or asleep (flat eyes, body one cell lower), talk (bob while its line types), hop, walk (alternate feet, move in whole cells), wave, think (dots above the head).
- **Never frozen**: idle characters breathe and blink on a seed. Extras breathe out of phase with each other.

## Motion

- **The picture shows what the subtitle says, while it says it.** If a line says the room is full, the room fills during that line.
- **Two kinds of motion, never mixed on one object**: pixel things (characters, cells, sprites) move in whole cells on a stepped clock (`stepped`, `hop`); interface things (panels, cards, scrolling messages) ease smoothly over 250–450 ms.
- **Spread the action over the scene.** Each subtitle gets its own beat; between beats something keeps changing: a line typing, a counter counting, a bar filling, characters breathing. `check` reports `static` stretches of 3 seconds or more; subtitles do not count as movement.
- **Persistent state is replayed, not accumulated**: a queue, a log or a grid's contents is a table of events in film seconds and a function that computes the state at `T`.
- No camera shake, white flashes or zoom pulses. A slow camera push onto one element is fine.

## Sound

- **Every visible event makes a sound**: typing, a block landing, someone leaving, a counter going up, a mistake, a success, writing, a reveal. The sound table in api.md suggests one for each.
- **Every speaker has a voice**, distinct in tone and pitch range; the engine blips once per character as a line types, so dialogue is heard without recorded speech. Use `key` for typing that nobody speaks, such as a sentence card or a search box.
- **Music is a soft bed**: one four-chord loop in one key, energy 1 for most scenes, 2 when the story speeds up, `false` or 0 for the hook and for a breath before the payoff. Silence before a reveal makes it land.
- At most two effects at the same moment.

## Review

Run `check` with a contact sheet and go through this list before building:

1. The sheet has a frame in the middle of every subtitle, with that subtitle on screen, and one frame for each scene without subtitles; past eight frames it comes in pages, listed in `sheets`. Open every page. For each frame, write down what is on screen and compare it with the bible's timeline at that second: the picture shows what its subtitle says, the layout matches the map, and nothing is clipped, covered or hard to read.
2. For a subtitle that describes a change, also open the moment it starts with `--at` (a single frame comes out full size): the change has to happen while the subtitle is on screen, and nothing may contradict the subtitle before it does.
3. Check the running state at a few moments: counters, queues and logs show the numbers the story says they show.
4. Fix what you found and every `issues` entry. After the last edit, run `check` again and look at the frames of every scene you changed; build only when that pass is clean.

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
| `text-overlap` | Two texts overlap at `at`. Move or shrink one, or show them at different times. |

A JavaScript error stops the check and reports the scene, its local time and the `film.js` line. A syntax error reports the line from Node's parser.
