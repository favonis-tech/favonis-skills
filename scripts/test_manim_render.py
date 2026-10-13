import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills/manim/scripts/render.py"
spec = importlib.util.spec_from_file_location("manim_render", SCRIPT)
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

HAS_MANIM = importlib.util.find_spec("manim") is not None and shutil.which("ffmpeg") and shutil.which("ffprobe")


def run_script(cwd, *args):
    # 场景名错误时 Manim 会等待交互输入；超时即视为脚本没有断开 stdin。
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, timeout=180)


class FindOutputTests(unittest.TestCase):
    def test_picks_this_render_of_the_named_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory)
            videos = media / "videos/demo/480p15"
            (videos / "partial_movie_files/Demo").mkdir(parents=True)
            started = time.time()
            for name in ["Demo.mp4", "DemoTwo.mp4", "partial_movie_files/Demo/Demo.mp4"]:
                (videos / name).write_bytes(b"x")
            stale = media / "videos/demo/1080p60/Demo.mp4"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"x")
            os.utime(stale, (started - 60, started - 60))
            self.assertEqual(render.find_output(media, "Demo", ".mp4", started), videos / "Demo.mp4")
            self.assertIsNone(render.find_output(media, "Demo", ".gif", started))
            # GIF 与静帧的文件名带 Manim 版本号。
            (videos / "Demo_ManimCE_v0.22.0.gif").write_bytes(b"x")
            self.assertEqual(render.find_output(media, "Demo", ".gif", started), videos / "Demo_ManimCE_v0.22.0.gif")


class ArgumentTests(unittest.TestCase):
    def test_rejects_inconsistent_outputs_before_rendering(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "scene.py").write_text("")
            for args, message in [
                (["--output", "out.gif"], "--output must end with .mp4"),
                (["--still", "--output", "out.mp4"], "--output must end with .png"),
                (["--still", "--sheet", "sheet.png"], "--sheet needs a video"),
            ]:
                result = run_script(directory, "scene.py", "Demo", *args)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)
            result = run_script(directory, "missing.py", "Demo")
            self.assertEqual(result.returncode, 2)
            self.assertIn("scene file not found", result.stderr)


@unittest.skipUnless(HAS_MANIM, "needs Manim and FFmpeg")
class RenderTests(unittest.TestCase):
    def test_render_copy_contact_sheet_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "clip.py").write_text(
                "from manim import *\n\n"
                "class Clip(Scene):\n"
                "    def construct(self):\n"
                "        self.play(Create(Square()), run_time=1)\n"
                "        self.wait(1)\n\n"
                "class Broken(Scene):\n"
                "    def construct(self):\n"
                "        self.play(ShowCreation(Square()))\n"
            )
            result = run_script(directory, "clip.py", "Clip", "--output", "outputs/clip.mp4", "--sheet", "review/clip.png")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual((report["width"], report["height"], report["fps"]), (854, 480, 15.0))
            self.assertAlmostEqual(report["duration"], 2, delta=0.2)
            self.assertEqual(Path(directory, "outputs/clip.mp4").read_bytes(), Path(report["rendered"]).read_bytes())
            self.assertTrue(Path(directory, "review/clip.png").stat().st_size)
            times = report["sheet_times"]
            self.assertEqual((len(times), times[0]), (8, 0))
            self.assertAlmostEqual(times[-1], report["duration"], delta=0.1)

            still = json.loads(run_script(directory, "clip.py", "Clip", "--still", "--output", "still.png").stdout)
            self.assertNotIn("duration", still)
            self.assertTrue(Path(directory, "still.png").stat().st_size)

            broken = run_script(directory, "clip.py", "Broken")
            self.assertEqual(broken.returncode, 1)
            self.assertIn("NameError: name 'ShowCreation' is not defined", json.loads(broken.stdout)["error"])
            missing = run_script(directory, "clip.py", "Nope")
            self.assertEqual(missing.returncode, 1)
            error = json.loads(missing.stdout)["error"]
            self.assertIn("Nope is not in the script", error)
            self.assertIn("Clip", error)


if __name__ == "__main__":
    unittest.main()
