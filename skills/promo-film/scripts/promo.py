"""Check, export, build and render a promo film written for the bundled engine; every command prints a JSON report.

    python promo.py check FILM.js [--sheet PNG] [--frames N | --at T,T,...]
    python promo.py timeline FILM.js --out TIMELINE.json
    python promo.py build FILM.js --out outputs/NAME.html [--audio AUDIO]
    python promo.py render FILM.js --out outputs/NAME.mp4 [--audio AUDIO] [--quality draft|720p|1080p] [--budget SECONDS]
"""

import argparse
import base64
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ASSETS = SKILL / "assets"
WORK = Path(tempfile.gettempdir()) / "promo-film"
QUALITY = {  # 渲染比例、运动模糊子帧数、x264 CRF、码率上限（胶片颗粒很费码率，不封顶时 1080p 会到 20 Mbps 以上）
    "draft": (0.5, 1, 23, "3M"),
    "720p": (2 / 3, 2, 21, "6M"),
    "1080p": (1.0, 2, 20, "12M"),
}
BUNDLED_FONTS = [
    ("Cinzel", "Cinzel.ttf", "400 900", "normal"),
    ("Cormorant Garamond", "CormorantGaramond.ttf", "300 700", "normal"),
    ("Cormorant Garamond", "CormorantGaramond-Italic.ttf", "300 700", "italic"),
    ("STIX Two Text", "STIXTwoText.ttf", "400 700", "normal"),
    ("STIX Two Text", "STIXTwoText-Italic.ttf", "400 700", "italic"),
]
SYSTEM_FONTS = [
    ("Noto Serif CJK SC", [("regular", 400), ("bold", 700), ("black", 900)]),
    ("Noto Sans CJK SC", [("regular", 400), ("bold", 700), ("black", 900)]),
    ("Noto Sans Mono", [("regular", 400), ("bold", 700)]),
]
EXTRA_CHARS = "–—‘’“”…·•°×÷±→←↑↓∞√∑∏∫≈≠≤≥①②③④⑤"
BROWSER_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                "--ignore-gpu-blocklist", "--mute-audio", "--allow-file-access-from-files", "--hide-scrollbars"]
AUDIO_MIME = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".opus": "audio/ogg"}


class Failure(Exception):
    """A problem the author has to fix; reported as {"ok": false, "error": ...} with exit code 1."""


def emit(report, code=0):
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(code)


def digest(*parts):
    h = hashlib.sha256()
    for part in parts:
        h.update(part if isinstance(part, bytes) else str(part).encode())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ 字体：按片中实际出现的字符做子集并内嵌
def fc_match(family, weight):
    """用 fontconfig 找系统字体文件；匹配到的家族名不对（回退到别的字体）时返回 None。"""
    if not shutil.which("fc-match"):
        return None
    out = subprocess.run(["fc-match", "-f", "%{file}\t%{index}\t%{family}", f"{family}:weight={weight}"],
                         capture_output=True, text=True).stdout
    path, _, rest = out.partition("\t")
    index, _, families = rest.partition("\t")
    if not path or family not in [f.strip() for f in families.split(",")]:
        return None
    return path, int(index or 0)


def subset(path, index, chars):
    """返回 WOFF 子集字节；结果按文件与字符集缓存，同一部片反复构建不再重算。"""
    from fontTools import subset as ft_subset
    from fontTools.ttLib import TTFont

    stat = os.stat(path)
    key = digest(path, index, stat.st_size, stat.st_mtime_ns, "".join(sorted(chars)))
    cached = WORK / "fonts" / f"{key}.woff"
    if cached.exists():
        return cached.read_bytes() or None
    font = TTFont(path, fontNumber=index, recalcTimestamp=False)
    cmap = font.getBestCmap()
    codepoints = sorted(ord(c) for c in chars if ord(c) in cmap)
    data = b""
    if codepoints:
        options = ft_subset.Options()
        options.flavor = "woff"
        options.layout_features = ["*"]
        options.hinting = False
        options.notdef_outline = True
        sub = ft_subset.Subsetter(options)
        sub.populate(unicodes=codepoints)
        sub.subset(font)
        buffer = io.BytesIO()
        font.flavor = "woff"
        font.save(buffer)
        data = buffer.getvalue()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data or None


def font_css(chars):
    faces, embedded, missing = [], [], []

    def face(family, data, weight, style):
        src = base64.b64encode(data).decode()
        faces.append(f'@font-face {{ font-family: "{family}"; font-weight: {weight}; font-style: {style}; font-display: block; '
                     f'src: url(data:font/woff;base64,{src}) format("woff"); }}')
        embedded.append(f"{family} {weight} {style}")

    for family, file, weights, style in BUNDLED_FONTS:
        data = subset(str(ASSETS / "fonts" / file), 0, chars)
        if data:
            face(family, data, weights, style)
    for family, wanted in SYSTEM_FONTS:
        found = {}
        for name, css_weight in wanted:
            match = fc_match(family, name)
            if match is None:
                missing.append(f"{family} {css_weight}")
            else:
                found.setdefault(match, []).append(css_weight)
        for (path, index), weights in found.items():
            data = subset(path, index, chars)
            if data:
                # 同一个文件对应多个字重时它是可变字体，或者系统只有一种字重
                face(family, data, f"{min(weights)} {max(weights)}" if len(weights) > 1 else weights[0], "normal")
    return "\n".join(faces), embedded, missing


# ------------------------------------------------------------------ 构建单文件 HTML
def audio_uri(audio):
    path = Path(audio)
    if not path.is_file():
        raise Failure(f"audio file not found: {audio}")
    mime = AUDIO_MIME.get(path.suffix.lower())
    if mime is None:
        # WAV 等无损格式先转成 MP3，避免内嵌后 HTML 过大
        stat = path.stat()
        converted = WORK / "audio" / f"{digest(path.resolve(), stat.st_size, stat.st_mtime_ns)}.mp3"
        if not converted.exists():
            converted.parent.mkdir(parents=True, exist_ok=True)
            run = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-c:a", "libmp3lame", "-b:a", "192k", str(converted)],
                                 capture_output=True, text=True)
            if run.returncode:
                raise Failure(f"could not convert {audio} to MP3: {run.stderr.strip()[-800:]}")
        path, mime = converted, "audio/mpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def build_html(film, audio=None):
    source = Path(film).read_text(encoding="utf-8")
    chars = set(source) | {chr(c) for c in range(0x20, 0x7F)} | set(EXTRA_CHARS)
    css, embedded, missing = font_css(chars)
    # 包进块作用域：片里的顶层常量不会和引擎的全局名冲突；sourceURL 让报错指向 film.js 的行号
    film_js = "'use strict';{" + source.replace("</script", "<\\/script") + "\n}\n//# sourceURL=film.js"
    engine = (ASSETS / "engine.js").read_text(encoding="utf-8").replace("</script", "<\\/script") + "\n//# sourceURL=engine.js"
    html = (ASSETS / "player.html").read_text(encoding="utf-8")
    for marker, value in [("/*@FONTS*/", css), ("/*@ENGINE*/", engine), ("/*@FILM*/", film_js),
                          ("/*@AUDIO*/null", json.dumps(audio_uri(audio)) if audio else "null")]:
        html = html.replace(marker, value, 1)
    return html, {"embedded": embedded, "missing": missing}


def syntax_check(film):
    """浏览器的 SyntaxError 不带行号，先用 Node 解析一遍拿到准确位置。"""
    if not shutil.which("node"):
        return
    copy = WORK / "syntax" / "film.cjs"
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(film, copy)
    run = subprocess.run(["node", "--check", str(copy)], capture_output=True, text=True)
    if run.returncode:
        raise Failure(run.stderr.replace(str(copy), str(film)).strip()[-3000:])


# ------------------------------------------------------------------ 无头浏览器
class Page:
    """Headless Chromium with software WebGL; the page runs in export mode and is driven through window.PROMO."""

    def __init__(self, html, scale):
        from playwright.sync_api import sync_playwright

        self.errors = []
        self.path = WORK / "pages" / f"{digest(html)}.html"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(html, encoding="utf-8")
        self._pw = sync_playwright().start()
        executable = os.environ.get("PROMO_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")
        self.browser = self._pw.chromium.launch(executable_path=executable, args=BROWSER_ARGS)
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 720})
        self.page.on("pageerror", lambda e: self.errors.append(page_error(e.stack or e.message)))
        self.page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        self.page.goto(self.path.as_uri() + f"?export=1&scale={scale}")
        # 片子出错时页面永远不会就绪，一有报错就停止等待
        deadline = time.time() + 120
        while not self.errors and not self.page.evaluate("!!(window.PROMO && PROMO.ready())"):
            if time.time() > deadline:
                self.errors.append("the page did not become ready within 120 s")
            self.page.wait_for_timeout(100)
        if self.errors:
            self.close()
            raise Failure("\n".join(self.errors))
        self.info = self.page.evaluate("PROMO.info()")

    def call(self, expression, arg=None):
        try:
            return self.page.evaluate(expression, arg)
        except Exception as e:
            raise Failure(page_error(getattr(e, "message", str(e)))) from None

    def frame(self, t, scale, samples=1, fps=30):
        url = self.call("([t, o]) => PROMO.frame(t, o)", [t, {"scale": scale, "samples": samples, "fps": fps}])
        return base64.b64decode(url.split(",", 1)[1])

    def close(self):
        try:
            self.browser.close()
        finally:
            self._pw.stop()


def page_error(text):
    """保留 JS 异常的消息和指向 film.js 的栈帧；片子没出现在栈里时才给引擎的栈帧。"""
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    head = [line.replace("Page.evaluate: ", "") for line in lines if not line.startswith("at ")][:3]
    frames = [line for line in lines if line.startswith("at ") and "film.js" in line][:3] \
        or [line for line in lines if line.startswith("at ") and "engine.js" in line][:2]
    return "\n".join(head + frames)


# ------------------------------------------------------------------ check
def subtitle_issues(info):
    issues, scenes = [], {s["name"]: s for s in info["scenes"]}
    subs = sorted(info["subs"], key=lambda s: s["start"])
    for i, sub in enumerate(subs):
        dur = sub["end"] - sub["start"]
        cjk = sum(1 for c in sub["text"] if "⺀" <= c <= "鿿")
        words = len(sub["text"].split()) if not cjk else 0
        where = {"scene": sub["scene"], "at": round(sub["start"], 2), "text": sub["text"][:40]}
        if cjk and cjk / dur > 7 or words and words / dur > 3.2:
            issues.append({"kind": "subtitle-too-fast", **where, "seconds": round(dur, 2)})
        if sub["end"] > scenes[sub["scene"]]["end"] + 0.01:
            issues.append({"kind": "subtitle-past-scene", **where})
        if i + 1 < len(subs) and subs[i + 1]["start"] < sub["end"] - 0.01:
            issues.append({"kind": "subtitle-overlap", **where})
    return issues


def sheet_times(info, frames, at):
    if at:
        return [min(max(0.0, float(t)), info["duration"] - 0.01) for t in at.split(",")]
    if frames:
        n = max(1, frames)
        return [round(info["duration"] * (k + 0.5) / n, 2) for k in range(n)]
    scenes = info["scenes"]
    if len(scenes) > 16:
        scenes = [scenes[round(k * (len(scenes) - 1) / 15)] for k in range(16)]
    return [round(s["start"] + (s["end"] - s["start"]) * 0.6, 2) for s in scenes]


def contact_sheet(images, times, info, path):
    """横排 4 列拼图，每格下方标注时间与场景序号，供逐格检查。"""
    from PIL import Image, ImageDraw

    tiles = [Image.open(io.BytesIO(data)).convert("RGB") for data in images]
    width = 480 if len(tiles) > 1 else tiles[0].width
    tiles = [t.resize((width, round(t.height * width / t.width))) for t in tiles]
    columns = min(4, len(tiles))
    rows = math.ceil(len(tiles) / columns)
    th, label, pad = tiles[0].height, 22, 8
    sheet = Image.new("RGB", (columns * (width + pad) + pad, rows * (th + label + pad) + pad), "white")
    draw = ImageDraw.Draw(sheet)
    names = [s["name"] for s in info["scenes"]]
    for i, (tile, t) in enumerate(zip(tiles, times)):
        x, y = pad + (i % columns) * (width + pad), pad + (i // columns) * (th + label + pad)
        sheet.paste(tile, (x, y))
        scene = max((k for k, s in enumerate(info["scenes"]) if s["start"] <= t), default=0)
        draw.text((x + 2, y + th + 5), f"{t:.2f}s  scene {scene + 1}/{len(names)}", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def command_check(args):
    syntax_check(args.film)
    html, fonts = build_html(args.film)
    page = Page(html, 0.5)
    try:
        info = page.info
        issues = subtitle_issues(info)
        times = [round(k * 0.5, 2) for k in range(int(info["duration"] / 0.5) + 1) if k * 0.5 < info["duration"]]
        for i in range(0, len(times), 40):
            issues += page.call("times => PROMO.scan(times)", times[i:i + 40])
        report = {
            "ok": True, "duration": round(info["duration"], 2), "size": info["size"], "bpm": info["bpm"], "webgl": info["webgl"],
            "scenes": [{"name": s["name"], "start": round(s["start"], 2), "end": round(s["end"], 2)} for s in info["scenes"]],
            "subtitles": len(info["subs"]), "issues": issues, "fonts": fonts,
        }
        if args.sheet:
            times = sheet_times(info, args.frames, args.at)
            images = [page.frame(t, 0.5) for t in times]
            contact_sheet(images, times, info, Path(args.sheet))
            report.update(sheet=str(args.sheet), sheet_times=times)
        if page.errors:
            raise Failure("\n".join(page.errors))
    finally:
        page.close()
    if not info["webgl"]:
        report["warnings"] = ["WebGL is unavailable in this browser: backdrops and the film grade are skipped"]
    return report


# ------------------------------------------------------------------ timeline：交给 cue-score 的时间线
def timeline_of(info):
    music = info["music"]
    style = music.get("style", "cinematic") if isinstance(music, dict) else None
    sections, current = [], {"chords": [], "energy": 0}
    for s in info["scenes"]:
        if s["music"] is not None:
            current = {"chords": list(s["music"].get("chords", [])), "energy": s["music"].get("energy", 0)}
        sections.append({"name": s["name"], "start": round(s["start"], 4), "end": round(s["end"], 4),
                         **(current if style else {"chords": [], "energy": 0})})
    cues = [{k: v for k, v in c.items() if k != "scene"} for c in info["cues"]]
    hits = [{"t": round(t, 4), "k": k} for s in info["scenes"] for t, k in s["hits"]]
    return {"duration": round(info["duration"], 4), "bpm": info["bpm"], "style": style or "cinematic",
            "sections": sections, "hits": hits, "cues": cues}


def command_timeline(args):
    html, _ = build_html(args.film)
    page = Page(html, 0.25)
    try:
        timeline = timeline_of(page.info)
    finally:
        page.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ok": True, "output": str(out), "duration": timeline["duration"], "bpm": timeline["bpm"],
            "sections": len(timeline["sections"]), "hits": len(timeline["hits"]), "cues": len(timeline["cues"])}


# ------------------------------------------------------------------ build
def probe_duration(path):
    run = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    try:
        return round(float(run.stdout.strip()), 3)
    except ValueError:
        return None


def audio_warnings(audio, duration):
    if not audio:
        return []
    length = probe_duration(audio)
    if length is not None and abs(length - duration) > 1:
        return [f"the audio lasts {length:.1f} s but the film lasts {duration:.1f} s"]
    return []


def command_build(args):
    if Path(args.out).suffix.lower() != ".html":
        raise Failure("--out must end with .html")
    html, fonts = build_html(args.film, args.audio)
    # 用不含音频的同一份页面验证能加载并画出封面帧，避免交付打不开的文件
    page = Page(build_html(args.film)[0], 0.25)
    try:
        info = page.info
        page.frame(info["poster"], 0.25)
    finally:
        page.close()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    report = {"ok": True, "output": str(out), "bytes": out.stat().st_size, "duration": round(info["duration"], 2),
              "audio": bool(args.audio), "fonts": fonts}
    warnings = audio_warnings(args.audio, info["duration"])
    if warnings:
        report["warnings"] = warnings
    return report


# ------------------------------------------------------------------ render：分段渲染，超时后再次运行从断点继续
def encode_chunk(page, path, frames, fps, scale, samples, crf, maxrate):
    part = path.with_suffix(".part.mp4")
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-maxrate", maxrate, "-bufsize", f"{2 * int(maxrate[:-1])}M",
         "-pix_fmt", "yuv420p", "-r", str(fps), str(part)],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for n in frames:
            ffmpeg.stdin.write(page.frame(n / fps, scale, samples, fps))
        ffmpeg.stdin.close()
    except BaseException:
        ffmpeg.kill()
        raise
    if ffmpeg.wait():
        raise Failure("ffmpeg failed: " + ffmpeg.stderr.read().decode(errors="replace")[-800:])
    part.replace(path)


def command_render(args):
    out = Path(args.out)
    if out.suffix.lower() != ".mp4":
        raise Failure("--out must end with .mp4")
    if args.audio and not Path(args.audio).is_file():
        raise Failure(f"audio file not found: {args.audio}")
    scale, samples, crf, maxrate = QUALITY[args.quality]
    started = time.time()
    html, _ = build_html(args.film)
    work = WORK / "render" / digest(html, QUALITY[args.quality], args.fps)
    work.mkdir(parents=True, exist_ok=True)
    page = Page(html, scale)
    try:
        info = page.info
        total = round(info["duration"] * args.fps)
        per_chunk = args.fps * 8
        chunks = [work / f"chunk-{i:04d}.mp4" for i in range(math.ceil(total / per_chunk))]
        spent = []
        for i, chunk in enumerate(chunks):
            if chunk.exists():
                continue
            estimate = (sum(spent) / len(spent)) if spent else 0
            if time.time() - started + estimate * 1.15 > args.budget:
                break
            t0 = time.time()
            encode_chunk(page, chunk, range(i * per_chunk, min(total, (i + 1) * per_chunk)), args.fps, scale, samples, crf, maxrate)
            spent.append(time.time() - t0)
            print(f"chunk {i + 1}/{len(chunks)} in {spent[-1]:.0f} s", file=sys.stderr, flush=True)
    finally:
        page.close()
    done = [c for c in chunks if c.exists()]
    if len(done) < len(chunks):
        per_frame = sum(spent) / max(1, len(spent) * per_chunk) if spent else None
        remaining = total - len(done) * per_chunk
        return {"ok": True, "complete": False, "done_frames": min(total, len(done) * per_chunk), "total_frames": total,
                "eta_seconds": round(remaining * per_frame) if per_frame else None,
                "next": "Run the same command again; finished chunks are kept and rendering resumes where it stopped."}
    listing = work / "chunks.txt"
    listing.write_text("".join(f"file '{c}'\n" for c in chunks))
    command = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
    if args.audio:
        command += ["-i", args.audio, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "192k"]
    command += ["-c:v", "copy", "-t", f"{info['duration']:.3f}", "-movflags", "+faststart", str(work / "film.mp4")]
    run = subprocess.run(command, capture_output=True, text=True)
    if run.returncode:
        raise Failure("ffmpeg failed: " + run.stderr.strip()[-800:])
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(work / "film.mp4", out)
    width, height = round(info["size"][0] * scale / 2) * 2, round(info["size"][1] * scale / 2) * 2
    report = {"ok": True, "complete": True, "output": str(out), "width": width, "height": height, "fps": args.fps,
              "duration": probe_duration(out), "audio": bool(args.audio), "render_seconds": round(time.time() - started)}
    warnings = audio_warnings(args.audio, info["duration"])
    if warnings:
        report["warnings"] = warnings
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Load the film, report errors and layout issues, optionally write a contact sheet")
    check.add_argument("film")
    check.add_argument("--sheet", type=Path, help="Contact sheet PNG; default one frame per scene")
    check.add_argument("--frames", type=int, help="Evenly spaced frames instead of one per scene")
    check.add_argument("--at", help="Comma-separated film times in seconds")
    timeline = sub.add_parser("timeline", help="Export the music timeline JSON for the cue-score skill")
    timeline.add_argument("film")
    timeline.add_argument("--out", required=True)
    build = sub.add_parser("build", help="Write the self-contained HTML player")
    build.add_argument("film")
    build.add_argument("--out", required=True)
    build.add_argument("--audio", help="Soundtrack to embed (MP3 recommended; other formats are converted)")
    render = sub.add_parser("render", help="Render an MP4 in resumable chunks")
    render.add_argument("film")
    render.add_argument("--out", required=True)
    render.add_argument("--audio", help="Soundtrack to mux")
    render.add_argument("--quality", choices=QUALITY, default="1080p")
    render.add_argument("--fps", type=int, default=30)
    render.add_argument("--budget", type=float, default=1500, help="Stop starting new chunks after this many seconds (default 1500)")
    args = parser.parse_args()
    if not Path(args.film).is_file():
        parser.error(f"film file not found: {args.film}")
    if args.command == "check" and args.frames and args.at:
        parser.error("use either --frames or --at")
    try:
        report = {"check": command_check, "timeline": command_timeline, "build": command_build, "render": command_render}[args.command](args)
    except Failure as e:
        emit({"ok": False, "error": str(e)}, 1)
    emit(report)


if __name__ == "__main__":
    main()
