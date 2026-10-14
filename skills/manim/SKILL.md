---
name: manim
display-name: Manim Animation
description: >-
  Create precise, code-driven animations with Manim Community and render them to MP4, GIF or PNG in the
  project sandbox: math (equations, derivations, geometry, function graphs, calculus, linear algebra),
  algorithms and data structures, physics and engineering diagrams, animated charts and
  3Blue1Brown-style explainer videos. Use when the user asks for Manim, a math, science or algorithm
  animation, or an animated explanation built from shapes, formulas and graphs. Not for live-action
  footage, AI-generated video, photo slideshows or slide decks.
localizations:
  zh-CN:
    display-name: Manim 数学动画
    description: 用代码生成精确的数学、算法和科学动画，导出 MP4、GIF 或 PNG，适合公式推导、函数图像和 3Blue1Brown 风格的讲解视频。
    keywords: [动画, 数学视频, 公式, 算法动画, 3b1b, manim]
  zh-TW:
    display-name: Manim 數學動畫
    description: 用程式碼產生精確的數學、演算法和科學動畫，匯出 MP4、GIF 或 PNG，適合公式推導、函數圖形和 3Blue1Brown 風格的講解影片。
    keywords: [動畫, 數學影片, 公式, 演算法動畫, 3b1b, manim]
  zh-HK:
    display-name: Manim 數學動畫
    description: 用程式碼生成精確的數學、算法和科學動畫，匯出 MP4、GIF 或 PNG，適合公式推導、函數圖像和 3Blue1Brown 風格的講解影片。
    keywords: [動畫, 數學影片, 公式, 算法動畫, 3b1b, manim]
  en-US:
    display-name: Manim Animation
    description: Create precise math, algorithm and science animations in code and export them as MP4, GIF or PNG, for derivations, function graphs and 3Blue1Brown-style explainers.
    keywords: [animation, math video, formula, algorithm, 3b1b, manim]
---

# Manim animation

Write a Manim Community scene as a project source file, render it in the sandbox with the bundled script, check sampled frames, then deliver the video together with its source.

## Environment

- The Favonis sandbox image includes Manim Community 0.22 with the Cairo renderer, FFmpeg, TeX Live (LaTeX, XeLaTeX, ctex, dvisvgm) and Noto CJK fonts. Run `python -m manim --version` once. If Manim is missing, the sandbox was created from an older image: tell the user and stop. Do not install it with pip; its Cairo and Pango builds need system packages that cannot be added in the sandbox.
- The package directory is the `sandbox_path` returned by `skill_read` (normally `/skills/manim`) and is read-only. Read [references/authoring.md](references/authoring.md) before writing the first scene in a conversation, and read [scripts/render.py](scripts/render.py) once before running it. Run the script with an explicit interpreter: `python /skills/manim/scripts/render.py`.
- Use the `shell` tool in `/project`. Paths passed to the script and to `present_files` are project-relative. Manim's cache and intermediate files stay in `/tmp/manim`.
- Manim Community is not 3Blue1Brown's `manimgl`/`manimlib`; never import those. Never pass `-p`/`--preview` or `--renderer opengl`: the sandbox has no display or GPU.

## Workflow

1. **Brief.** Settle the idea, audience, language, approximate length, aspect ratio and output format. Defaults: 16:9 MP4, 30–90 seconds, dark background, on-screen text in the user's language. Use GIF only for short loops (under about 10 seconds), PNG for a single still, and 9:16 (`--resolution 1080,1920`) for phone-first short video. Ask only when a missing decision changes the result.
2. **Storyboard.** List the beats: what appears, what moves, what the viewer should notice, and roughly how many seconds each takes. One idea per beat. Keep about 6–8 elements on screen at most and clear the stage between topics. Split anything longer than about two minutes into several Scene classes.
3. **Write the source** in the project, for example `animations/pythagoras.py`, with one `Scene` subclass per segment. Follow references/authoring.md for layout, text, formulas and CJK.
4. **Draft render** at low quality with a contact sheet:

   ```bash
   python /skills/manim/scripts/render.py animations/pythagoras.py Pythagoras --sheet /tmp/manim-review/pythagoras.png
   ```

   On `"ok": false`, read `error`: its last lines name the failing source line or the LaTeX error. Fix the source and render again. Also resolve `warnings`, such as a missing font.
5. **Check frames.** The sheet tiles evenly spaced frames, first and last included, in reading order; `sheet_times` gives their timestamps. To see it, copy it into a temporary project review folder, open it with `project_read`, then delete that review copy. Look for overlapping or clipped elements, text that is too small, wrongly rendered formulas, empty frames and leftovers from earlier beats. Fix and re-render until the draft is clean. Use `--sheet-frames 12` to `16` for longer scenes. If you cannot view images, say that the visual check was not performed.
6. **Final render** at the delivery quality into the project:

   ```bash
   python /skills/manim/scripts/render.py animations/pythagoras.py Pythagoras --quality h --output outputs/勾股定理.mp4
   ```

   `h` (1080p60) is the default for delivery; use `m` for quick shares and `k` only on request. High quality takes several times longer than the draft, so pass a larger shell `timeout_ms` (up to 30 minutes) for long scenes. Check `duration`, `width` and `height` in the report, the shell `exit_code` and the project saving result.
7. **Deliver** with `present_files`, passing the video and its source file. Briefly state the length, resolution and what the animation shows, plus any check you did not perform. Never return `/tmp` paths or sandbox URLs.

For several scenes, render each one without `--output`, then join the `rendered` files with FFmpeg's concat demuxer into one project file. Keep resolution and frame rate identical across the scenes.

## Render script

| Option | Meaning |
| --- | --- |
| `FILE SCENE` | Source file and one Scene class name. |
| `--quality l\|m\|h\|p\|k` | 480p15 (default, for drafts), 720p30, 1080p60, 1440p60, 2160p60. |
| `--resolution W,H` | Custom pixel size, for example `1080,1920`. The frame height stays 8 units, so a vertical frame is only 4.5 units wide. |
| `--fps N` | Override the preset frame rate. |
| `--format mp4\|gif\|webm\|mov` | Video container, default `mp4`. |
| `--still` | Save only the last frame as PNG. |
| `--transparent` | Alpha channel; combine with `--format mov` or `--still`. |
| `--output PATH` | Copy the result there; the extension must match the format. |
| `--sheet PATH`, `--sheet-frames N` | Contact sheet PNG of N frames (default 8). |

The script prints JSON. On success it reports `rendered` (the cached file), `output`, `width`, `height`, `duration`, `fps`, `sheet`, `sheet_times` and any `warnings`, and exits with 0. On failure it reports `"ok": false`, `exit_code` and `error`, and exits with 1. A wrong scene name fails at once, and the error lists the scenes in the file.

## Narration and sound

Manim renders silent video. For a voiceover, write the narration per beat first, then generate it with the platform's audio tool if one is available. Measure each clip with `ffprobe` and set `run_time` and `self.wait()` from the real durations, not from an estimated reading speed. Attach clips with `self.add_sound("audio/beat-1.wav")` at the start of their beat (paths resolve from `/project`), or mux one finished track afterwards with FFmpeg. Do not promise narration when no audio could be generated.

## Revision

Edit the scene source and render again to the same `--output` path; the project keeps the previous version in its history. Change only the beats the user commented on. Keep the source in the project so the user can edit or re-render it. Do not publish the animation unless the user asks.
