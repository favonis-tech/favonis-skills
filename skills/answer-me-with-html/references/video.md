# Explainer videos (am video, 3Blue1Brown style)

Read this when SKILL.md section 7 sends you here. Use the full sandbox command from SKILL.md section 2 for every `am` command, with `AM_HOME=/tmp/answer-me-with-html`, `AM_NO_OPEN=1` and `AM_NO_UPDATE_CHECK=1`. Replace the example's `/skills/answer-me-with-html` prefix with the returned `sandbox_path` if it differs. Run in `/project` and explicitly set the output under `outputs/`.

A video draft has the same format as a page draft, with one extra rule: lines starting with `>` are narration, one beat per line.

````bash
mkdir -p outputs
AM_HOME=/tmp/answer-me-with-html AM_NO_OPEN=1 AM_NO_UPDATE_CHECK=1 node /skills/answer-me-with-html/scripts/am.mjs video - --no-open -o outputs/explainer.html <<'AM_EOF'
---
title: The TCP three-way handshake
subtitle: Why three
---
> Opening narration (optional).

## Both ends are waiting
```sequence
Client -> Server: SYN
Server -> Client: SYN-ACK
Client -> Server: ACK
```
> First the client sends SYN to ask for a connection.
> [Server] answers with SYN-ACK.
> The client replies with ACK, and the connection is open.
AM_EOF
````

- One `## ` is one scene. Put one component (or one table, one list) in a scene as the picture, and write 2–5 narration lines below it.
- When the Nth narration line plays, the picture shows step N. In flow / sequence / tree every source line is one step; timeline, limits, table rows and list items step by entry. So the line order of the component is the order of the explanation. When there are more narration lines than steps, the extra first lines serve as an opening and show nothing new.
- Write `[name]` in narration: the camera zooms in on the node or actor with that name and highlights it. The name must match how it is written in the component.
- Nodes with the same name in adjacent scenes move smoothly to their new position. To keep the viewer following one object, reuse the same name in the next scene.
- 3–6 scenes per video, one or two sentences per narration line.
- Narration is read aloud, so write it as speech, as if explaining to someone face to face: transitions like `你看`, `那问题来了`, `我们换个角度看` are fine, and characters' "lines" go in quotes. Do not write it like a manual (`客户端发送 SYN 报文以请求建立连接`). Sentence length is still subject to the STE check.
- The look follows the theme in the settings by default (usually the blueprint drawing style). When the user wants "that dark 3b1b style", write `theme: 3b1b` in the frontmatter.
- Narration voice: Favonis runs this CLI in a Linux sandbox. The default `--voice auto` uses ElevenLabs when `ELEVENLABS_API_KEY` is set, otherwise `espeak-ng` if installed, otherwise subtitles only. Do not assume macOS `say` or a configured speech provider. When the user says "no sound", add `--voice off`. For a configured OpenAI-compatible speech service, use `--voice local` with `AM_TTS_URL`; the address must be reachable from the sandbox (`localhost` means the sandbox, not the user's computer). Do not print credentials when checking configuration.
- The output is a single-file player page (audio embedded when available). Always set `-o outputs/<name>.html`. When the user requests a video file, add `--mp4`; it needs Chrome/Chromium, ffmpeg and Node.js 22+. The current Favonis E2B image includes these tools, but existing sandboxes may differ: check `node --version` and `command -v chromium chromium-browser ffmpeg` before export. If export fails, inspect the CLI error and installed tools before attempting dependency installation. A speech provider is required for narration; do not promise narration when only subtitles are available.
- Full syntax: `am help video`. Confirm the shell saved the output files, then call `present_files` with their project-relative paths as described in SKILL.md. Return a short conclusion; sandbox-local URLs cannot deliver files to the user.
