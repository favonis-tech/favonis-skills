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

Write the film as one JavaScript file for the bundled engine, check and review it in the sandbox, add a score, then deliver a self-contained HTML player with the music embedded.

## Environment

- The package directory is the `sandbox_path` returned by `skill_read` (normally `/skills/promo-film`) and is read-only. Before writing the first film in a conversation, read [references/api.md](references/api.md), [references/craft.md](references/craft.md) and [references/example.js](references/example.js); the commands below are all you need from the script.
- Use the `shell` tool in `/project` and run the script with an explicit interpreter: `python /skills/promo-film/scripts/promo.py`. Paths passed to the script and to `present_files` are project-relative; caches stay under `/tmp/promo-film`.
- The sandbox renders with Chromium's software WebGL; no GPU or display is needed and nothing has to be installed. If the script reports that Chromium, Playwright or fontTools is missing, the sandbox was created from an older image: tell the user and stop.

## Workflow

1. **Brief.** Start working without asking questions. Defaults: 16:9, 45–75 seconds, on-screen text and subtitles in the user's language with English secondary lines for a cinematic feel, a synthesized score, delivered as the HTML player. Ask only when the subject itself is unclear.
2. **Storyboard.** Write a short table of scenes: name, bars, what appears and moves, the subtitle, the sound. Pick the tempo first; a bar lasts `240 / bpm` seconds. Follow craft.md: every scene shows what its subtitles say and keeps moving.
3. **Write** `promo/<slug>/film.js`, one `scene()` per row of the storyboard. example.js shows technique; the storyboard and every word come from the user's subject.
4. **Check** and review a contact sheet:

   ```bash
   python /skills/promo-film/scripts/promo.py check promo/abyss/film.js --sheet review/abyss.png
   ```

   On `"ok": false`, fix the error it names (scene, time and `film.js` line) and run it again. Resolve every entry in `issues`. Open every page listed in `sheets` with `project_read` and work through the review list in craft.md. `--at 3.5,12.2` picks other moments; a single moment comes out full size. Delete the `review` folder with `project_delete` before delivering. If you cannot view images, say that the visual check was not performed.
5. **Sound.** Choose one:
   - A synthesized, cue-synced score when the `cue-score` skill is available: export the timeline, then read that skill and follow it to write `promo/<slug>/score.mp3`. If its report has `warnings`, such as a key change, fix the chords in `film.js` and regenerate.

     ```bash
     python /skills/promo-film/scripts/promo.py timeline promo/abyss/film.js --out promo/abyss/timeline.json
     ```

   - A track the user provides, or music from the platform's audio tool. Generated music is not synchronized with the cuts: ask for the film's tempo in the prompt and keep hits on bar boundaries.
   - No sound, only when the user asks for it: skip `--audio` below.
6. **Build** the player and deliver it. Build only after the last edit to `film.js` has passed `check` and you have looked at the frames of the scenes it changed. Do not edit the film after building; if a change is still needed, check and review it, then rebuild before delivering.

   ```bash
   python /skills/promo-film/scripts/promo.py build promo/abyss/film.js --audio promo/abyss/score.mp3 --out outputs/海渊七号.html
   ```

   The HTML embeds the engine, the film, font subsets and the audio, so it plays offline and in the project preview. Call `present_files` with the HTML only; `film.js`, the timeline and the score stay in the project for later edits but are not deliverables. Close with one or two sentences: the title, its length, what it covers, any `warnings` (such as an audio track shorter or longer than the film) and any check you could not perform.

## Revision

Edit `film.js`, run `check` again, and rebuild to the same output path; the project keeps earlier versions in its history. Change only the scenes the user commented on. When scene lengths, `music`, `hits` or `sfx` change, export the timeline and regenerate the score before building. Deliver the rebuilt HTML.

## Video files

Only when the user asks for a video file, render an MP4 from the same film:

```bash
python /skills/promo-film/scripts/promo.py render promo/abyss/film.js --audio promo/abyss/score.mp3 --out outputs/海渊七号.mp4
```

Pass `timeout_ms: 1800000` to the shell. Rendering is CPU-bound and slow: in the sandbox plan on roughly 20–45 minutes per minute of 1080p film, and rely on the `eta_seconds` the first call reports. Each call stops before its `--budget` (default 1500 seconds) and reports `"complete": false` with `done_frames`, `total_frames` and `eta_seconds`; tell the user the estimate, then run the same command again until `"complete": true`. Finished chunks are reused only while the film is unchanged. `--quality draft` (960×540, no motion blur) needs about a fifth of the work and suits previews; `720p` sits in between. Deliver the MP4 with `present_files` and state its length and resolution.
