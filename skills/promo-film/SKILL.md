---
name: promo-film
display-name: Animated Short
description: >-
  Make narrated animated shorts drawn frame by frame in code: a small story with a character, a world
  that turns the subject into a picture, typed dialogue, diagrams and knowledge cards, subtitles, and
  synthesized voices, sound effects and music on every event. Suits explainers ("why X happens", "how X
  works"), product and brand stories, promos and openers on any subject. Delivers a self-contained HTML
  player and, on request, an MP4. Not for live-action footage, AI-generated video, slide decks, or
  step-by-step math derivations (use Manim for those).
localizations:
  zh-CN:
    display-name: 动画短片
    description: 用代码逐帧画出有故事的动画短片：角色、把主题变成画面的场景、打字对白、图解卡片和字幕，配上跟着画面走的合成配音与音效，导出可直接播放的网页或 MP4。
    keywords: [动画, 短片, 科普视频, 讲解视频, 宣传片, 片头, 视频]
  zh-TW:
    display-name: 動畫短片
    description: 用程式碼逐格畫出有故事的動畫短片：角色、把主題變成畫面的場景、打字對白、圖解卡片和字幕，配上跟著畫面走的合成配音與音效，匯出可直接播放的網頁或 MP4。
    keywords: [動畫, 短片, 科普影片, 講解影片, 宣傳片, 片頭, 影片]
  zh-HK:
    display-name: 動畫短片
    description: 用程式碼逐格畫出有故事的動畫短片：角色、把主題變成畫面的場景、打字對白、圖解卡片和字幕，配上跟着畫面走的合成配音與音效，匯出可直接播放的網頁或 MP4。
    keywords: [動畫, 短片, 科普影片, 講解影片, 宣傳片, 片頭, 影片]
  en-US:
    display-name: Animated Short
    description: Draw narrated animated shorts in code, with a character, a world that pictures the subject, typed dialogue, knowledge cards, subtitles and synthesized voices and sound, delivered as a playable web page or MP4.
    keywords: [animation, explainer, short film, promo, opener, video]
---

# Animated short

Design the film in a production bible, implement it as one JavaScript file for the bundled engine, check and review it in the sandbox, then deliver a self-contained HTML player. The engine synthesizes the soundtrack from the film itself: voices as lines type, effects on events, a soft music bed.

## Environment

- The package directory is the `sandbox_path` returned by `skill_read` (normally `/skills/promo-film`) and is read-only. Before writing the first film in a conversation, read [references/craft.md](references/craft.md), [references/api.md](references/api.md), [references/example-bible.md](references/example-bible.md) and [references/example.js](references/example.js); the commands below are all you need from the script.
- Use the `shell` tool in `/project` and run the script with an explicit interpreter: `python /skills/promo-film/scripts/promo.py`. Paths passed to the script and to `present_files` are project-relative; caches stay under `/tmp/promo-film`.
- The sandbox renders with headless Chromium; nothing has to be installed. If the script reports that Chromium, Playwright or fontTools is missing, the sandbox was created from an older image: tell the user and stop.

## Workflow

1. **Brief.** Start working without asking questions. Defaults: 16:9; an explainer or story runs 1.5–3 minutes, a promo or opener 30–60 seconds; on-screen text, dialogue and subtitles in the user's language; synthesized sound; delivered as the HTML player. Ask only when the subject itself is unclear.
2. **Bible.** Before any code, write `promo/<slug>/bible.md` with every section listed in craft.md: logline, story, accuracy, world and characters, look with a layout map in coordinates, character sheets, sound, and a timeline per scene with every word that appears or is heard and the second it happens. This is where the film is designed; [example-bible.md](references/example-bible.md) shows the level of detail. The story, the world, the look and every word come from the user's subject, never from the example.
3. **Write** `promo/<slug>/film.js` implementing the bible exactly: one `scene()` per timeline section, subtitles, dialogue and sounds copied from it, positions from the layout map. When the code needs a different plan, change the bible first, then the code.
4. **Check** and review a contact sheet:

   ```bash
   python /skills/promo-film/scripts/promo.py check promo/queue/film.js --sheet review/queue.png
   ```

   On `"ok": false`, fix the error it names (scene, time and `film.js` line) and run it again. Resolve every entry in `issues`. Open every page listed in `sheets` with `project_read` and work through the review list in craft.md. `--at 3.5,12.2` picks other moments; a single moment comes out full size. Delete the `review` folder with `project_delete` before delivering. If you cannot view images, say that the visual check was not performed.
5. **Build** the player and deliver it. Build only after the last edit to `film.js` has passed `check` and you have looked at the frames of the scenes it changed. Do not edit the film after building; if a change is still needed, check and review it, then rebuild before delivering.

   ```bash
   python /skills/promo-film/scripts/promo.py build promo/queue/film.js --out outputs/旁边那队.html
   ```

   The HTML embeds the engine, the film and font subsets and synthesizes the sound when it opens, so it plays offline and in the project preview. Call `present_files` with the HTML only; the bible and `film.js` stay in the project for later edits but are not deliverables. Close with one or two sentences: the title, its length, what it covers and any check you could not perform. You cannot hear the result: do not describe how it sounds.

## Sound

The film's sound comes from `film.js`: the `voices` and `music` of `film()`, each scene's `say`, `sfx` and `music`, and `sound()` for events kept in film-time tables. There is no separate audio step. When the user provides a track, pass it with `--audio` to `build` and `render`; it plays under the film's own sound, so set `music: false` in `film()` to keep the two from clashing. Music from the platform's audio tool is not synchronized with the picture.

## Revision

Change the bible, then `film.js`, run `check` again, and rebuild to the same output path; the project keeps earlier versions in its history. Change only the scenes the user commented on, and keep the copy and layout of the others. Deliver the rebuilt HTML.

## Video files

Only when the user asks for a video file, render an MP4 from the same film; the synthesized sound is mixed in, together with the `--audio` track if there is one:

```bash
python /skills/promo-film/scripts/promo.py render promo/queue/film.js --out outputs/旁边那队.mp4
```

Pass `timeout_ms: 1800000` to the shell. Rendering is CPU-bound: plan on a few minutes per minute of 1080p film and rely on the `eta_seconds` the first call reports. Each call stops before its `--budget` (default 1500 seconds) and reports `"complete": false` with `done_frames`, `total_frames` and `eta_seconds`; tell the user the estimate, then run the same command again until `"complete": true`. Finished chunks are reused only while the film is unchanged. `--quality draft` (960×540) suits previews; `720p` sits in between. Deliver the MP4 with `present_files` and state its length and resolution.
