import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/promo-film/scripts/promo.py"
spec = importlib.util.spec_from_file_location("promo_film", SCRIPT)
promo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promo)

CHROMIUM = os.environ.get("PROMO_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")
HAS_BROWSER = bool(CHROMIUM and shutil.which("ffmpeg") and all(importlib.util.find_spec(m) for m in ("playwright", "fontTools", "PIL")))

FILM = """film({ title: 'Test', tail: 1, voices: { 甲: { tone: 'square', cps: 10 } } });
scene({
  name: 'one', dur: 2,
  subs: [[0.2, 1.8, '第一句字幕']],
  draw(t, d) {
    text('出界的标题', W - 40, H / 2, { size: 120 });
    text('压住字幕', W / 2, H - 60, { size: 40 });
    text('上层文字', W / 2, H * .3, { size: 60 });
    text('下层文字', W / 2 + 30, H * .3 + 20, { size: 60 });
  },
});
scene({
  name: 'two', dur: 2,
  say: [[0.2, '甲', '你好']],
  sfx: [[1, 'chime']],
  draw(t, d, T) {
    glow(W / 2, H / 2, 200, '#ffd28c', fade(t, 0, d));
    for (const l of dialogue(T)) bubble(l.full, W / 2, H * .4, { upto: l.shown });
  },
});
"""


CHECKS_FILM = """film({ title: 'Checks', tail: 1 });
scene({
  name: 'hold', dur: 4,
  draw(t, d) { text('不动的标题', W / 2, H / 2, { size: 80, alpha: fade(t, 0, 99, .3, .1) }); },
});
scene({
  name: 'moving', dur: 4,
  draw(t, d) { glow(W * (.2 + .15 * t), H / 2, 120, '#88ccff', 1); },
});
"""


def run_script(cwd, *args, timeout=300):
    # 缓存（字体子集、渲染分段）放进用例自己的临时目录，避免用例之间互相复用
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "TMPDIR": str(cwd)})


def max_volume(path):
    run = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True)
    return float(re.search(r"max_volume: (-?[\d.]+|-inf) dB", run.stderr).group(1).replace("-inf", "-999"))


class ReportTests(unittest.TestCase):
    def test_default_frames_follow_the_subtitles(self):
        info = {"duration": 9.0, "subs": [{"start": 1, "end": 3, "scene": "a"}, {"start": 3.5, "end": 4.5, "scene": "a"}],
                "scenes": [{"name": "a", "start": 0, "end": 5}, {"name": "b", "start": 5, "end": 8}]}
        self.assertEqual(promo.sheet_times(info, None, None), [2.0, 4.0, 6.8])

    def test_subtitle_timing_issues(self):
        info = {"scenes": [{"name": "a", "start": 0, "end": 5}], "subs": [
            {"start": 0, "end": 1, "text": "这一句字幕实在太长了根本读不完", "scene": "a"},
            {"start": 0.5, "end": 5.5, "text": "Fine pace here", "scene": "a"},
        ]}
        kinds = {i["kind"] for i in promo.subtitle_issues(info)}
        self.assertEqual(kinds, {"subtitle-too-fast", "subtitle-overlap", "subtitle-past-scene"})

    def test_rejects_wrong_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "film.js").write_text(FILM)
            for command, out, message in [("build", "x.mp4", "must end with .html"), ("render", "x.html", "must end with .mp4")]:
                result = run_script(directory, command, "film.js", "--out", out)
                self.assertEqual(result.returncode, 1)
                self.assertIn(message, json.loads(result.stdout)["error"])
            result = run_script(directory, "check", "missing.js")
            self.assertEqual(result.returncode, 2)
            self.assertIn("film file not found", result.stderr)


@unittest.skipUnless(HAS_BROWSER, "needs Chromium (PROMO_CHROMIUM or chromium on PATH), Playwright, fontTools, Pillow and FFmpeg")
class BrowserTests(unittest.TestCase):
    def test_check_reports_layout_and_writes_sheet(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "film.js").write_text(FILM)
            result = run_script(directory, "check", "film.js", "--sheet", "review/sheet.png", "--at", "0.5,2.5")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual([s["name"] for s in report["scenes"]], ["one", "two"])
            self.assertAlmostEqual(report["duration"], 5.0, places=2)
            self.assertEqual((report["lines"], report["sounds"], report["music"]), (1, 1, False))
            issues = {(i["kind"], i["text"]) for i in report["issues"]}
            self.assertIn(("clipped", "出界的标题"), issues)
            self.assertIn(("under-subtitle", "压住字幕"), issues)
            self.assertIn(("text-overlap", "上层文字 / 下层文字"), issues)
            self.assertEqual(report["sheet_times"], [0.5, 2.5])
            self.assertEqual(report["sheets"], ["review/sheet.png"])
            self.assertTrue(Path(directory, "review/sheet.png").stat().st_size)
            # 超过一页的帧分页写出
            report = json.loads(run_script(directory, "check", "film.js", "--sheet", "review/many.png", "--frames", "9").stdout)
            self.assertEqual(report["sheets"], ["review/many-1.png", "review/many-2.png"])
            self.assertTrue(all(Path(directory, p).stat().st_size for p in report["sheets"]))

    def test_check_reports_static_pictures(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "film.js").write_text(CHECKS_FILM)
            report = json.loads(run_script(directory, "check", "film.js").stdout)
            self.assertEqual({(i["kind"], i["scene"]) for i in report["issues"]}, {("static", "hold")})
            self.assertGreaterEqual(report["issues"][0]["seconds"], 3)

    def test_errors_point_at_the_film(self):
        with tempfile.TemporaryDirectory() as directory:
            broken = FILM.replace("glow(W / 2", "glowing(W / 2")
            Path(directory, "film.js").write_text(broken)
            line = broken.splitlines().index(next(l for l in broken.splitlines() if "glowing" in l)) + 1
            result = run_script(directory, "check", "film.js")
            self.assertEqual(result.returncode, 1)
            error = json.loads(result.stdout)["error"]
            self.assertIn("two at", error)
            self.assertIn("glowing is not defined", error)
            self.assertIn(f"film.js:{line}:", error)
            # 没声明声音的说话人在加载时就报错
            Path(directory, "film.js").write_text(FILM.replace("'甲', '你好'", "'乙', '你好'"))
            error = json.loads(run_script(directory, "check", "film.js").stdout)["error"]
            self.assertIn('"乙" has no voice', error)
            if shutil.which("node"):
                Path(directory, "film.js").write_text(FILM.replace("dur: 2,", "dur: 2,,", 1))
                error = json.loads(run_script(directory, "check", "film.js").stdout)["error"]
                self.assertIn("film.js:3", error)
                self.assertIn("SyntaxError", error)

    def test_build_and_resumable_render_carry_the_film_sound(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "film.js").write_text(FILM)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "5",
                            "-c:a", "libmp3lame", str(Path(directory, "track.mp3"))], check=True)
            report = json.loads(run_script(directory, "build", "film.js", "--out", "outputs/test.html").stdout)
            self.assertTrue(report["ok"], report)
            self.assertFalse(report["audio"])
            html = Path(directory, "outputs/test.html").read_text()
            self.assertIn('font-family: "STIX Two Text"', html)
            self.assertNotIn("data:audio/", html)
            report = json.loads(run_script(directory, "build", "film.js", "--audio", "track.mp3", "--out", "outputs/track.html").stdout)
            self.assertIn("data:audio/mpeg;base64,", Path(directory, "outputs/track.html").read_text())

            args = ["render", "film.js", "--audio", "track.mp3", "--out", "outputs/test.mp4", "--quality", "draft"]
            first = json.loads(run_script(directory, *args, "--budget", "0").stdout)
            self.assertEqual((first["complete"], first["done_frames"], first["total_frames"]), (False, 0, 150))
            result = run_script(directory, *args, timeout=900)
            done = json.loads(result.stdout)
            self.assertTrue(done["complete"], result.stdout + result.stderr)
            self.assertEqual((done["width"], done["height"], done["fps"]), (960, 540, 30))
            self.assertAlmostEqual(done["duration"], 5.0, delta=0.1)
            # 另给的音轨是静音，成片里听得见的只能是片子自己合成的说话声和音效
            self.assertGreater(max_volume(Path(directory, "outputs/test.mp4")), -20)


if __name__ == "__main__":
    unittest.main()
