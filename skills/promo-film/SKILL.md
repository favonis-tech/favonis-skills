---
name: promo-film
display-name: Promo Film
description: >-
  Make cinematic promo films, trailers, title sequences and openers drawn frame by frame in code
  (Canvas 2D and WebGL): particle titles, light effects, chapter cards, bilingual subtitles,
  film grading and hits on the beat. Delivers a self-contained HTML player that plays in the
  browser and, on request, an MP4. Use when the user asks for a promo film, trailer, teaser,
  opener, brand or launch video, or an animated title sequence. Not for live-action footage,
  AI-generated video, slide decks, or step-by-step math explanations (use Manim for those).
localizations:
  zh-CN:
    display-name: 电影感宣传片
    description: 用代码逐帧绘制电影感宣传片和片头：粒子标题、光效、章节卡、双语字幕和踩点闪切，导出可直接播放的网页或 MP4。
    keywords: [宣传片, 预告片, 片头, 开场动画, 发布会视频, 视频]
  zh-TW:
    display-name: 電影感宣傳片
    description: 用程式碼逐格繪製電影感宣傳片和片頭：粒子標題、光效、章節卡、雙語字幕和踩點閃切，匯出可直接播放的網頁或 MP4。
    keywords: [宣傳片, 預告片, 片頭, 開場動畫, 發表會影片, 影片]
  zh-HK:
    display-name: 電影感宣傳片
    description: 用程式碼逐格繪製電影感宣傳片和片頭：粒子標題、光效、章節卡、雙語字幕和踩點閃切，匯出可直接播放的網頁或 MP4。
    keywords: [宣傳片, 預告片, 片頭, 開場動畫, 發佈會影片, 影片]
  en-US:
    display-name: Promo Film
    description: Draw cinematic promo films and title sequences in code, with particle titles, light effects, chapter cards, bilingual subtitles and cuts on the beat, delivered as a playable web page or MP4.
    keywords: [promo, trailer, teaser, opener, title sequence, video]
---

# Promo film

Write the film as one JavaScript file for the bundled engine, check it in the sandbox, add a score, then deliver a self-contained HTML player and, when asked, an MP4.

## Environment

- The package directory is the `sandbox_path` returned by `skill_read` (normally `/skills/promo-film`) and is read-only. Before writing the first film in a conversation, read [references/authoring.md](references/authoring.md) and [references/example.js](references/example.js). Read [scripts/promo.py](scripts/promo.py) once before running it.
- Use the `shell` tool in `/project` and run the script with an explicit interpreter: `python /skills/promo-film/scripts/promo.py`. Paths passed to the script and to `present_files` are project-relative; caches stay under `/tmp/promo-film`.
- The sandbox renders with Chromium's software WebGL; no GPU or display is needed and nothing has to be installed. If the script reports that Chromium, Playwright or fontTools is missing, the sandbox was created from an older image: tell the user and stop.

## Workflow

1. **Brief.** Settle the subject, audience, length, aspect ratio, on-screen language and the sound. Defaults: 16:9, 45–75 seconds, Chinese on screen with English secondary subtitle lines for a cinematic feel (or the user's language only), a synthesized score. Ask only when a missing decision changes the film.
2. **Storyboard.** Write a short table of scenes: name, bars, what appears and moves, the subtitle, the sound. Pick the tempo first; a bar lasts `240 / bpm` seconds. Follow the structure and pacing in authoring.md.
3. **Write** `promo/<slug>/film.js`, one `scene()` per row of the storyboard.
4. **Check** and review a contact sheet:

   ```bash
   python /skills/promo-film/scripts/promo.py check promo/light/film.js --sheet /tmp/promo-review/light.png
   ```

   On `"ok": false`, fix the error it names (scene, time and `film.js` line) and run it again. Resolve every entry in `issues`. The sheet shows one frame per scene by default; `--frames 12` spaces frames evenly and `--at 3.5,12.2` picks moments, for example the middle of an animation. To see the sheet, copy it into a temporary project review folder, open it with `project_read`, then delete that copy. Look for overlapping or crowded elements, unreadable text, empty frames and leftovers from earlier beats. If you cannot view images, say that the visual check was not performed.
5. **Sound.** Choose one:
   - A synthesized, cue-synced score when the `cue-score` skill is available: export the timeline, then read that skill and follow it to write `promo/<slug>/score.mp3`.

     ```bash
     python /skills/promo-film/scripts/promo.py timeline promo/light/film.js --out promo/light/timeline.json
     ```

   - A track the user provides, or music from the platform's audio tool. Generated music is not synchronized with the cuts: ask for the film's tempo in the prompt and keep hits on bar boundaries.
   - No sound: skip `--audio` below.
6. **Build** the player and deliver it:

   ```bash
   python /skills/promo-film/scripts/promo.py build promo/light/film.js --audio promo/light/score.mp3 --out outputs/光.html
   ```

   The HTML embeds the engine, the film, font subsets and the audio, so it plays offline and in the project preview. Call `present_files` with the HTML and `film.js`. Mention any `warnings`, such as an audio track that is shorter or longer than the film.
7. **Render an MP4** only when the user wants a video file (to upload, share or edit):

   ```bash
   python /skills/promo-film/scripts/promo.py render promo/light/film.js --audio promo/light/score.mp3 --out outputs/光.mp4
   ```

   Pass `timeout_ms: 1800000` to the shell. Rendering is CPU-bound and slow: in the sandbox plan on roughly 20–45 minutes per minute of 1080p film, and rely on the `eta_seconds` the first call reports. Each call stops before its `--budget` (default 1500 seconds) and reports `"complete": false` with `done_frames`, `total_frames` and `eta_seconds`; tell the user the estimate, then run the same command again until `"complete": true`. Finished chunks are reused only while the film is unchanged. `--quality draft` (960×540, no motion blur) needs about a fifth of the work and suits previews; `720p` sits in between. Deliver the MP4 with `present_files` and state its length and resolution.

## Revision

Edit `film.js`, run `check` again, and rebuild to the same output path; the project keeps earlier versions in its history. Change only the scenes the user commented on. When scene lengths, `music`, `hits` or `sfx` change, export the timeline and regenerate the score before building. Re-render the MP4 only if the user still wants one. Keep `film.js`, `timeline.json` and the score in the project so the film can be edited later.
