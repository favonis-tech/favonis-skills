import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "skills/cue-score/scripts/score.py"
spec = importlib.util.spec_from_file_location("cue_score", SCRIPT)
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

HAS_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


def timeline(**overrides):
    base = {"duration": 6.0, "bpm": 120, "style": "cinematic",
            "sections": [{"name": "quiet", "start": 0, "end": 4, "chords": [], "energy": 0}],
            "hits": [{"t": 3.0, "k": 1}], "cues": []}
    return {**base, **overrides}


def rms(audio, t0, t1):
    seg = audio[:, int(t0 * score.SR):int(t1 * score.SR)]
    return float(np.sqrt(np.mean(seg ** 2)))


class TheoryTests(unittest.TestCase):
    def test_chords_and_notes(self):
        self.assertEqual(score.parse_chord("F/A"), (5, (0, 4, 7), 9))
        self.assertEqual(score.parse_chord("Bbm7")[:2], (10, (0, 3, 7, 10)))
        self.assertIsNone(score.parse_chord("-"))
        for bad in ("Hm", "Cmaj13", "D/X"):
            with self.assertRaises(ValueError):
                score.parse_chord(bad)
        self.assertEqual([score.note_midi(n) for n in ("A4", "C#4", "Bb3")], [69, 61, 58])

    def test_voicing_moves_smoothly(self):
        previous = None
        for name in ["Dm", "Bb", "F", "C", "Gm", "A7"]:
            notes = score.voicing(score.parse_chord(name), previous)
            self.assertTrue(all(48 <= n <= 80 for n in notes), notes)
            if previous:
                self.assertLess(abs(sum(notes) / len(notes) - sum(previous) / len(previous)), 6)
            previous = notes


class RenderTests(unittest.TestCase):
    def test_validation_reports_every_problem(self):
        bad = timeline(bpm=300, sections=[{"name": "a", "start": 0, "end": 4, "chords": ["Hm"], "energy": 5},
                                          {"name": "b", "start": 3, "end": 9, "energy": 2}],
                       cues=[{"t": 1, "name": "laser"}])
        with self.assertRaises(score.Invalid) as caught:
            score.render(bad, 1)
        message = str(caught.exception)
        for part in ["bpm", "unknown chord 'Hm'", "energy must be", "overlaps", "ends after", "needs chords", "unknown sound 'laser'"]:
            self.assertIn(part, message)

    def test_hits_and_cues_land_on_time(self):
        audio = score.render(timeline(cues=[{"t": 1.0, "name": "tick"}]), 1)
        self.assertEqual(audio.shape, (2, int(6.0 * score.SR)))
        self.assertLess(rms(audio, 0.5, 0.99), 1e-4)
        self.assertGreater(rms(audio, 1.0, 1.03), 1e-3)
        self.assertLess(rms(audio, 2.5, 2.99), rms(audio, 3.0, 3.3) / 20)

    def test_lead_ins_land_on_their_time(self):
        audio = score.render(timeline(hits=[], cues=[{"t": 3.0, "name": "riser", "dur": 2}]), 1)
        self.assertLess(rms(audio, 0.2, 0.95), 1e-4)
        before = rms(audio, 2.4, 2.95)
        self.assertGreater(before, rms(audio, 1.05, 1.6) * 10)
        self.assertLess(rms(audio, 3.05, 3.3), before / 5)

    def test_key_change_warnings(self):
        def loops(*chords):
            return {"sections": [{"name": f"s{i}", "chords": c} for i, c in enumerate(chords)]}

        self.assertEqual(score.key_warnings(loops(["Dm", "Bb", "F", "C"], ["Gm", "Dm", "Bb", "A"], ["C", "G", "Am", "F"])), [])
        warnings = score.key_warnings(loops(["Am", "F", "C", "Em"], ["Fm", "Db", "Ab", "Eb"]))
        self.assertEqual(len(warnings), 1)
        self.assertIn("s0 → s1", warnings[0])

    def test_sections_play_and_seed_is_reproducible(self):
        song = timeline(sections=[{"name": "a", "start": 0, "end": 4, "chords": ["Dm", "Bb"], "energy": 3}], hits=[])
        for style in score.STYLES:
            first = score.render({**song, "style": style}, 1)
            self.assertGreater(rms(first, 0.5, 3.5), 0.05)
            np.testing.assert_array_equal(first, score.render({**song, "style": style}, 1))
            self.assertFalse(np.array_equal(first, score.render({**song, "style": style}, 2)))


@unittest.skipUnless(HAS_FFMPEG, "needs FFmpeg")
class CommandTests(unittest.TestCase):
    def run_script(self, directory, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=directory, capture_output=True, text=True, timeout=180)

    def test_writes_normalized_audio_and_reports_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "t.json").write_text(json.dumps(timeline(sections=[
                {"name": "a", "start": 0, "end": 4, "chords": ["Am", "F"], "energy": 2}])))
            result = self.run_script(directory, "t.json", "--out", "audio/score.mp3")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)["ok"])
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(Path(directory, "audio/score.mp3"))], capture_output=True, text=True)
            self.assertAlmostEqual(float(probe.stdout), 6.0, delta=0.1)

            Path(directory, "bad.json").write_text(json.dumps(timeline(style="jazz")))
            result = self.run_script(directory, "bad.json", "--out", "x.mp3")
            self.assertEqual(result.returncode, 1)
            self.assertIn("style must be one of", json.loads(result.stdout)["error"])
            result = self.run_script(directory, "t.json", "--out", "x.ogg")
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
