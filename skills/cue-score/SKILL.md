---
name: cue-score
display-name: Cue-synced Score
description: >-
  Synthesize an instrumental score with sound effects from a timeline JSON so that every hit, cut
  and effect lands on its exact second: chords and energy per section, impacts, risers, whooshes,
  heartbeats and chimes, mixed and normalized to streaming loudness. Use for music that must follow
  a known edit: promo films from the promo-film skill, Manim animations, slide or screen-recording
  videos with known shot times, or a cue list the user describes. Not for songs, lyrics, a named
  genre or realistic instruments without exact sync; use the audio skill's music generation for those.
localizations:
  zh-CN:
    display-name: 卡点配乐
    description: 按时间线合成配乐与音效，重拍、转场和音效精确落在指定秒数，适合给宣传片、动画和剪好的视频配乐。
    keywords: [配乐, 卡点, 音效, 背景音乐, 预告片音乐, bgm]
  zh-TW:
    display-name: 卡點配樂
    description: 依時間軸合成配樂與音效，重拍、轉場和音效精準落在指定秒數，適合為宣傳片、動畫和剪好的影片配樂。
    keywords: [配樂, 卡點, 音效, 背景音樂, 預告片音樂, bgm]
  zh-HK:
    display-name: 卡點配樂
    description: 按時間線合成配樂與音效，重拍、轉場和音效準確落在指定秒數，適合為宣傳片、動畫和剪輯好的影片配樂。
    keywords: [配樂, 卡點, 音效, 背景音樂, 預告片音樂, bgm]
  en-US:
    display-name: Cue-synced Score
    description: Synthesize music and sound effects from a timeline so hits, cuts and effects land on exact seconds, for promo films, animations and edited videos.
    keywords: [score, music, sound effects, cue, sync, bgm]
---

# Cue-synced score

Write or export a timeline, synthesize it with the bundled script, and deliver the audio or mux it into the video. The result is deterministic: the same timeline and seed always give the same file.

## Environment

- The package directory is the `sandbox_path` returned by `skill_read` (normally `/skills/cue-score`) and is read-only. The command below is all you need from the script.
- Use the `shell` tool in `/project`: `python /skills/cue-score/scripts/score.py TIMELINE.json --out audio/score.mp3`. It needs only NumPy, SciPy and FFmpeg, which the sandbox includes. Output is `.mp3`, `.m4a` or `.wav` at 48 kHz, normalized to −14 LUFS.

## Timeline

```json
{
  "duration": 32.0,
  "bpm": 90,
  "style": "cinematic",
  "sections": [
    { "name": "intro", "start": 0, "end": 10.667, "chords": ["Dm", "Bb", "F", "C"], "energy": 1 },
    { "name": "reveal", "start": 10.667, "end": 29.333, "chords": ["Dm", "Bb", "C", "A"], "energy": 3 }
  ],
  "hits": [{ "t": 10.667, "k": 1 }],
  "cues": [
    { "t": 0.5, "name": "heart" },
    { "t": 10.667, "name": "riser", "dur": 2 },
    { "t": 16.0, "name": "whoosh", "dur": 0.8, "pan": -0.5 }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `duration` | Length of the output in seconds. Time after the last section is the ring-out; the end fades. |
| `bpm` | Tempo, 40–220. One bar is `240 / bpm` seconds; harmony and rhythm follow a bar grid that starts at each section's `start`. |
| `style` | `cinematic` (strings, felt piano, celesta, choir, taiko, braams) or `electronic` (supersaw pads, plucks, four-on-the-floor, claps). |
| `sections` | In time order, without overlaps. `chords` has one chord per bar, cycled; `"-"` is a bar without harmony. `energy` 0–4: 0 silence (effects only), 1 pads, 2 adds arpeggios, 3 adds drums and a bass or string ostinato, 4 is the full arrangement (cinematic adds choir, snare and a braam at the section start). A section two or more energy steps above the previous one gets an automatic riser. |
| `hits` | Impacts with strength `k` (0–1.5): sub drop, rumble, taiko and, above 0.6, a crash; the pads duck under them. |
| `cues` | Sound effects with optional `gain` (default 1), `pan` (−1 to 1), `dur` and `note`. Most start at `t`; the lead-ins `riser`, `reverse` and `swell` build up for `dur` seconds and land on `t`, so give them the time of the moment they lead into. |

Chords: roots `A`–`G` with `#` or `b`, qualities `m`, `5`, `sus2`, `sus4`, `dim`, `aug`, `6`, `m6`, `7`, `maj7`, `m7`, `m7b5`, `dim7`, `7sus4`, `add9`, `madd9`, `9`, `m9`, `maj9`, and an optional slash bass (`F/A`).

| Cue | Sound | `dur` |
| --- | --- | --- |
| `hit` | Short punch for a flash cut | — |
| `boom` | Full impact, like a hit at `k` 1 | — |
| `riser` | Noise and tone rising, lands on `t` | 2 |
| `reverse` | Reversed cymbal, lands on `t` | 1 |
| `swell` | Orchestral crescendo on the current chord, lands on `t` | 2 |
| `whoosh` | Air passing left to right | 0.8 |
| `sparkle` | Scattered celesta notes from the current chord | 2 |
| `chime` | Bell; `note` such as `"D6"`, default from the chord | — |
| `heart` | Heartbeat (two thumps) | — |
| `tick` | Small click, for counters and typing | — |
| `glitch` | Digital stutter | 0.4 |
| `drop` | Falling sub tone | 1.2 |

## Writing a timeline by hand

For a video that already exists (a Manim render, a screen recording, an edited clip), take the shot boundaries and important moments from its source or from `ffprobe` and scene timings, then:

- Choose a tempo whose bars fit the shots; 90 BPM gives 2.667-second bars, 120 BPM 2-second bars. Section boundaries need not fall on bars, but music sounds tighter when they do.
- Shape energy over the piece: start at 1, build to 3–4 at the main reveal, dip before the last section. Use 0 for silence before a big hit.
- Keep the piece in one key and vary the loop between sections. Loops that work: minor epic `Dm Bb F C` or `Am F C G`; tension `Dm Bb Gm A`; bright `C G Am F` or `F C G Am`; tech `Fm Db Ab Eb` with `electronic`. The report warns when neighbouring sections share no key.
- Put `hits` on reveals and hard cuts and land `riser`, `reverse` or `swell` on them (same `t`); never add a `boom` or `hit` cue on a hit, which already sounds. Use `whoosh` on fast camera moves, `tick` on counters, `chime` or `sparkle` on small reveals. Do not stack more than two effects on the same moment.

From the promo-film skill, export the timeline with `promo.py timeline` instead of writing it.

## Workflow

1. Write or export the timeline, for example `promo/light/timeline.json`.
2. Run the script:

   ```bash
   python /skills/cue-score/scripts/score.py promo/light/timeline.json --out promo/light/score.mp3
   ```

   On `"ok": false`, `error` lists every invalid field with its section or cue index; fix them and run it again. `warnings` point out key changes between sections; change the chords unless the user asked for a modulation. For a different arrangement of the same timeline, pass another `--seed`.
3. Use the audio: pass it to promo-film's `build` or `render` with `--audio`, or mux it into another video:

   ```bash
   ffmpeg -i outputs/scene.mp4 -i audio/score.mp3 -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest outputs/scene-with-music.mp4
   ```

4. When the score is the deliverable, call `present_files` with the audio file only; the timeline stays in the project. When it goes into a video, deliver the video instead. You cannot hear the result: say so, and offer concrete variations (style, energy curve, chords, seed) rather than claiming how it sounds.
