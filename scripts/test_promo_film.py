import importlib.util
import json
import os
from pathlib import Path
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

FILM = """film({ title: 'Test', bpm: 120, tail: 1 });
scene({
  name: 'one', bars: 1, camera: 'still',
  subs: [[0.2, 1.8, '第一句字幕']],
  draw(t, d) {
    text('出界的标题', W - 40, H / 2, { size: 120 });
    text('压住字幕', W / 2, H - 60, { size: 40 });
  },
});
scene({
  name: 'two', bars: 1, hits: [[0, 0.5]],
  sfx: [[1, 'chime']],
  draw(t, d) { glow(W / 2, H / 2, 200, '#ffd28c', fade(t, 0, d)); },
});
"""


CHECKS_FILM = """film({ title: 'Checks', bpm: 120, tail: 1 });
scene({
  name: 'hold', bars: 2, camera: 'still',
  sfx: [[1.3, 'riser', { dur: 1 }]],
  draw(t, d) { text('不动的标题', W / 2, H / 2, { size: 80, alpha: fade(t, 0, 99, .3, .1) }); },
});
scene({
  name: 'moving', bars: 2, camera: 'still', hits: [[0, 1]],
  sfx: [[0, 'boom'], [0, 'swell', { dur: 2 }]],
  draw(t, d) { glow(W * (.2 + .15 * t), H / 2, 120, '#88ccff', 1); },
});
"""


def run_script(cwd, *args, timeout=300):
    # 缓存（字体子集、渲染分段）放进用例自己的临时目录，避免用例之间互相复用
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "TMPDIR": str(cwd)})


class TimelineTests(unittest.TestCase):
    def info(self, music):
        return {
            "duration": 9.0, "bpm": 90, "music": music,
            "scenes": [
                {"name": "a", "start": 0, "end": 4, "music": {"chords": ["Dm"], "energy": 1}, "hits": []},
                {"name": "b", "start": 4, "end": 8, "music": None, "hits": [[4, 0.8]]},
            ],
            "cues": [{"t": 1.0, "name": "tick", "scene": "a"}],
        }

    def test_scenes_without_music_continue_the_previous_one(self):
        timeline = promo.timeline_of(self.info({"style": "electronic"}))
        self.assertEqual(timeline["style"], "electronic")
        self.assertEqual([s["energy"] for s in timeline["sections"]], [1, 1])
        self.assertEqual(timeline["sections"][1]["chords"], ["Dm"])
        self.assertEqual(timeline["hits"], [{"t": 4, "k": 0.8}])
        self.assertEqual(timeline["cues"], [{"t": 1.0, "name": "tick"}])

    def test_disabled_music_keeps_only_effects(self):
        timeline = promo.timeline_of(self.info(False))
        self.assertEqual({(s["energy"], tuple(s["chords"])) for s in timeline["sections"]}, {(0, ())})
        self.assertEqual(len(timeline["cues"]), 1)

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
            issues = {(i["kind"], i["text"]) for i in report["issues"]}
            self.assertIn(("clipped", "出界的标题"), issues)
            self.assertIn(("under-subtitle", "压住字幕"), issues)
            self.assertEqual(report["sheet_times"], [0.5, 2.5])
            self.assertTrue(Path(directory, "review/sheet.png").stat().st_size)

    def test_check_reports_static_pictures_and_misplaced_sounds(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "film.js").write_text(CHECKS_FILM)
            report = json.loads(run_script(directory, "check", "film.js").stdout)
            found = {(i["kind"], i["scene"]) for i in report["issues"]}
            self.assertEqual(found, {("static", "hold"), ("lead-in-off-beat", "hold"), ("double-impact", "moving")})
            static = next(i for i in report["issues"] if i["kind"] == "static")
            self.assertGreaterEqual(static["seconds"], 3)

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
            if shutil.which("node"):
                Path(directory, "film.js").write_text(FILM.replace("bars: 1,", "bars: 1,,", 1))
                error = json.loads(run_script(directory, "check", "film.js").stdout)["error"]
                self.assertIn("film.js:3", error)
                self.assertIn("SyntaxError", error)

    def test_timeline_build_and_resumable_render(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "film.js").write_text(FILM)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "5",
                            "-c:a", "libmp3lame", str(Path(directory, "score.mp3"))], check=True)
            report = json.loads(run_script(directory, "timeline", "film.js", "--out", "timeline.json").stdout)
            self.assertTrue(report["ok"])
            timeline = json.loads(Path(directory, "timeline.json").read_text())
            self.assertEqual([s["start"] for s in timeline["sections"]], [0, 2])
            self.assertEqual(timeline["hits"], [{"t": 2, "k": 0.5}])
            self.assertEqual(timeline["cues"], [{"t": 3, "name": "chime"}])

            report = json.loads(run_script(directory, "build", "film.js", "--audio", "score.mp3", "--out", "outputs/test.html").stdout)
            self.assertTrue(report["ok"], report)
            html = Path(directory, "outputs/test.html").read_text()
            self.assertIn("data:audio/mpeg;base64,", html)
            self.assertIn('font-family: "Cinzel"', html)

            args = ["render", "film.js", "--audio", "score.mp3", "--out", "outputs/test.mp4", "--quality", "draft"]
            first = json.loads(run_script(directory, *args, "--budget", "0").stdout)
            self.assertEqual((first["complete"], first["done_frames"], first["total_frames"]), (False, 0, 150))
            result = run_script(directory, *args, timeout=900)
            done = json.loads(result.stdout)
            self.assertTrue(done["complete"], result.stdout + result.stderr)
            self.assertEqual((done["width"], done["height"], done["fps"]), (960, 540, 30))
            self.assertAlmostEqual(done["duration"], 5.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
