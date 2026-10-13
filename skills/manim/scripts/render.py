"""Render one Manim scene, copy the result into the project and print a JSON report."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VIDEO_FORMATS = ("mp4", "gif", "webm", "mov")


def probe(path):
    """读取渲染结果的尺寸、时长和帧率；GIF 与 PNG 也走 ffprobe。"""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    info = {"width": stream["width"], "height": stream["height"]}
    duration = data.get("format", {}).get("duration")
    if duration not in (None, "N/A"):
        numerator, _, denominator = stream["r_frame_rate"].partition("/")
        info["duration"] = round(float(duration), 3)
        info["fps"] = round(float(numerator) / float(denominator or 1), 3)
    return info


def find_output(media_dir, scene, suffix, started):
    """Manim 的输出目录随质量变化，GIF/PNG 还会在文件名后加版本号，所以按场景名和后缀找本次写出的文件。"""
    candidates = [
        path for path in media_dir.rglob(f"{scene}*{suffix}")
        if "partial_movie_files" not in path.parts and path.stat().st_mtime >= started
        and path.stem.split("_ManimCE_")[0] == scene
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def contact_sheet(video, sheet, info, frames):
    """把均匀分布、包含首尾帧的若干帧拼成一张图，供逐帧检查布局。"""
    total = max(1, round(info["duration"] * info["fps"]))
    frames = max(1, min(frames, total))
    indices = sorted({round(k * (total - 1) / max(1, frames - 1)) for k in range(frames)})
    columns = min(4, len(indices))
    rows = -(-len(indices) // columns)
    select = "+".join(f"eq(n\\,{index})" for index in indices)
    sheet.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video),
         "-vf", f"select='{select}',scale=480:-2,tile={columns}x{rows}:padding=8:color=white",
         "-fps_mode", "vfr", "-frames:v", "1", str(sheet)],
        capture_output=True, text=True, check=True,
    )
    return [round(index / info["fps"], 2) for index in indices]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Scene source file, e.g. animations/pythagoras.py")
    parser.add_argument("scene", help="Scene class name")
    parser.add_argument("--quality", choices="lmhpk", default="l",
                        help="l=480p15 draft (default), m=720p30, h=1080p60, p=1440p60, k=2160p60")
    parser.add_argument("--resolution", help="W,H, e.g. 1080,1920 for vertical video; frame height stays 8 units")
    parser.add_argument("--fps", type=float, help="Override the quality preset frame rate")
    parser.add_argument("--format", choices=VIDEO_FORMATS, default="mp4")
    parser.add_argument("--still", action="store_true", help="Save only the last frame as PNG")
    parser.add_argument("--transparent", action="store_true", help="Alpha channel; use with --format mov or --still")
    parser.add_argument("--output", type=Path, help="Copy the result to this path, normally under the project")
    parser.add_argument("--sheet", type=Path, help="Write a contact sheet PNG of evenly spaced frames here")
    parser.add_argument("--sheet-frames", type=int, default=8, help="Frames in the contact sheet (default 8)")
    args = parser.parse_args()

    source = args.file.resolve()
    if not source.is_file():
        parser.error(f"scene file not found: {args.file}")
    suffix = ".png" if args.still else "." + args.format
    if args.output and args.output.suffix.lower() != suffix:
        parser.error(f"--output must end with {suffix}")
    if args.sheet and args.still:
        parser.error("--sheet needs a video, not --still")

    # 媒体缓存放在临时目录，按源文件名复用，避免把 Manim 的中间文件写进项目。
    media_dir = Path(tempfile.gettempdir()) / "manim" / source.stem
    command = [sys.executable, "-m", "manim", "render", "-q", args.quality,
               "--media_dir", str(media_dir), "--progress_bar", "none", "-v", "WARNING"]
    if args.resolution:
        command += ["-r", args.resolution]
    if args.fps:
        command += ["--fps", str(args.fps)]
    command += ["-s"] if args.still else ["--format", args.format]
    if args.transparent:
        command.append("-t")
    command += [str(source), args.scene]

    started = time.time() - 1
    # 场景名不存在时 Manim 会在 stdin 上等用户选场景，必须断开；加宽 Rich 输出让每条日志保持一行。
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            env={**os.environ, "COLUMNS": "400"})
    log = (result.stdout + result.stderr).splitlines()
    rendered = find_output(media_dir, args.scene, suffix, started) if result.returncode == 0 else None
    if rendered is None:
        lines = [re.sub(r" {3,}", "  ", line.strip("│╭╮╰╯─ ")) for line in log]
        error = "\n".join(line for line in lines if line).strip()
        print(json.dumps({"ok": False, "exit_code": result.returncode,
                          "error": error[-6000:] or "Manim wrote no output file"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    report = {"ok": True, "scene": args.scene, "rendered": str(rendered), **probe(rendered)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(rendered, args.output)
        report["output"] = str(args.output)
    if args.sheet:
        report["sheet"] = str(args.sheet)
        report["sheet_times"] = contact_sheet(rendered, args.sheet, report, args.sheet_frames)
    warnings = [re.sub(r" {3,}", "  ", line.split("WARNING", 1)[1].strip())[:300] for line in log if "WARNING" in line]
    if warnings:
        report["warnings"] = warnings[-20:]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
