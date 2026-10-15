"""Synthesize a cue-synced score from a timeline JSON and print a JSON report.

    python score.py TIMELINE.json --out audio/score.mp3 [--seed N]

The timeline gives the tempo, sections with chords and energy, hits and sound-effect cues in seconds.
Every hit and cue lands on its exact time; harmony and rhythm follow each section's bar grid.
"""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
STYLES = ("cinematic", "electronic")
OUTPUT = {".mp3": ["-c:a", "libmp3lame", "-b:a", "192k"], ".m4a": ["-c:a", "aac", "-b:a", "192k"], ".wav": ["-c:a", "pcm_s16le"]}
SFX_DEFAULT_DUR = {"riser": 2.0, "reverse": 1.0, "swell": 2.0, "whoosh": 0.8, "sparkle": 2.0, "glitch": 0.4, "drop": 1.2}
QUALITIES = {
    "": (0, 4, 7), "maj": (0, 4, 7), "m": (0, 3, 7), "min": (0, 3, 7), "5": (0, 7), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
    "sus": (0, 5, 7), "dim": (0, 3, 6), "aug": (0, 4, 8), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9), "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10), "m7b5": (0, 3, 6, 10), "dim7": (0, 3, 6, 9), "7sus4": (0, 5, 7, 10),
    "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14), "9": (0, 4, 7, 10, 14), "m9": (0, 3, 7, 10, 14), "maj9": (0, 4, 7, 11, 14),
}
PITCH = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class Invalid(Exception):
    """The timeline breaks the format; the message lists every problem found."""


# ------------------------------------------------------------------ 乐理
def pitch_class(name):
    return (PITCH[name[0]] + {"#": 1, "b": -1}.get(name[1:2], 0)) % 12


def parse_chord(name):
    """'Dm7', 'Bb', 'F/A', 'Asus4' → (root pitch class, intervals, bass pitch class); '-' is a bar without harmony."""
    if name == "-":
        return None
    m = re.fullmatch(r"([A-G][#b]?)([^/]*)(?:/([A-G][#b]?))?", name)
    if not m or m.group(2) not in QUALITIES:
        raise ValueError(f"unknown chord {name!r}")
    root = pitch_class(m.group(1))
    return root, QUALITIES[m.group(2)], pitch_class(m.group(3)) if m.group(3) else root


def note_midi(name):
    m = re.fullmatch(r"([A-G][#b]?)(-?\d)", name)
    if not m:
        raise ValueError(f"unknown note {name!r}; use names like A5 or C#4")
    return 12 * (int(m.group(2)) + 1) + PITCH[m.group(1)[0]] + {"#": 1, "b": -1}.get(m.group(1)[1:], 0)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def voicing(chord, previous):
    """在 E3–C5 附近排出与上一个和弦平均音高最接近的密集排列，保证声部进行平滑。"""
    root, intervals, _ = chord
    pcs = list(dict.fromkeys((root + i) % 12 for i in intervals))
    target = sum(previous) / len(previous) if previous else 62
    best = None
    for rotate in range(len(pcs)):
        order = pcs[rotate:] + pcs[:rotate]
        for low in range(48, 64):
            if low % 12 != order[0]:
                continue
            notes = [low]
            for pc in order[1:]:
                n = notes[-1] + 1
                while n % 12 != pc:
                    n += 1
                notes.append(n)
            if len(notes) < 4:
                notes.append(notes[0] + 12)
            cost = abs(sum(notes) / len(notes) - target) + 0.2 * (notes[-1] - notes[0])
            if best is None or cost < best[0]:
                best = (cost, notes)
    return best[1]


# ------------------------------------------------------------------ 信号基础
def tvec(dur):
    return np.arange(max(1, int(dur * SR))) / SR


def lowpass(x, f, order=2):
    return sosfilt(butter(order, min(f, SR * 0.45), "low", fs=SR, output="sos"), x)


def highpass(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bandpass(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, min(hi, SR * 0.45)], "band", fs=SR, output="sos"), x)


def envelope(n, attack, release, hold=None):
    """线性起音、保持、指数释放；hold 为 None 时释放从起音结束开始。"""
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    start = attack if hold is None else hold
    r = np.where(t > start, np.exp(-(t - start) / max(release / 4.6, 1e-4)), 1.0)
    return a * r


def saw(freq, n, phase=0.0):
    """PolyBLEP 锯齿波，freq 可以是逐样本数组（滑音）。"""
    dt = np.broadcast_to(np.asarray(freq, dtype=np.float64) / SR, (n,))
    ph = (phase + np.cumsum(dt)) % 1.0
    out = 2 * ph - 1
    lo = ph < dt
    x = ph[lo] / dt[lo]
    out[lo] -= 2 * x - x * x - 1
    hi = ph > 1 - dt
    x = (ph[hi] - 1) / dt[hi]
    out[hi] -= x * x + 2 * x + 1
    return out


def sine(freq, n, phase=0.0):
    dt = np.broadcast_to(np.asarray(freq, dtype=np.float64) / SR, (n,))
    return np.sin(2 * np.pi * (phase + np.cumsum(dt)))


class Mix:
    """各声部按总线累加；hall/room 是混响发送，sidechain 记录需要让位的重音。"""

    def __init__(self, seconds, rng):
        self.n = int(seconds * SR) + SR
        self.rng = rng
        self.bus = {k: np.zeros((2, self.n)) for k in ("music", "pad", "drums", "sfx", "hall", "room")}
        self.ducks = []

    def noise(self, n):
        return self.rng.standard_normal(n)

    def put(self, sig, t, bus="music", gain=1.0, pan=0.0, hall=0.0, room=0.0):
        sig = np.asarray(sig)
        if sig.ndim == 1:
            angle = (np.clip(pan, -1, 1) + 1) * np.pi / 4
            sig = np.vstack([sig * np.cos(angle), sig * np.sin(angle)]) * math.sqrt(2)
        i = int(round(t * SR))
        if i >= self.n or i + sig.shape[1] <= 0:
            return
        if i < 0:
            sig, i = sig[:, -i:], 0
        sig = sig[:, : self.n - i] * gain
        self.bus[bus][:, i:i + sig.shape[1]] += sig
        if hall:
            self.bus["hall"][:, i:i + sig.shape[1]] += sig * hall
        if room:
            self.bus["room"][:, i:i + sig.shape[1]] += sig * room


# ------------------------------------------------------------------ 乐器
def pad(mix, notes, t0, dur, gain, bright=2200, voices=3, spread=0.09, bus="pad", hall=0.6, attack=0.7):
    n = int((dur + 1.6) * SR)
    left, right = np.zeros(n), np.zeros(n)
    for m in notes:
        for v in range(voices):
            detune = (v - (voices - 1) / 2) * spread / max(1, voices - 1) * 2
            wave_ = saw(hz(m + detune), n, mix.rng.random())
            (left if v % 2 == 0 else right)[:] += wave_
            if voices == 1:
                right += wave_
    env = envelope(n, attack, 1.5, hold=dur)
    # 高通让出低频给贝斯和底鼓，铺底只负责中频的和声
    sig = np.vstack([highpass(lowpass(c, bright), 140) for c in (left, right)]) * env / (len(notes) * voices) * 2
    mix.put(sig, t0, bus, gain, hall=hall)


def choir(mix, notes, t0, dur, gain):
    n = int((dur + 2) * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for k, m in enumerate(notes):
        f = hz(m) * (1 + 0.003 * np.sin(2 * np.pi * (5 + 0.3 * k) * t + k))
        src = saw(f, n, mix.rng.random())
        out += bandpass(src, 650, 950) + 0.5 * bandpass(src, 1000, 1300) + 0.2 * bandpass(src, 2600, 3200)
    sig = out * envelope(n, 1.2, 2.0, hold=dur) / len(notes)
    mix.put(sig, t0, "pad", gain, pan=0.0, hall=1.0)


def celesta(mix, m, t0, gain, pan=0.0, decay=0.9, bus="music", hall=0.5):
    t = tvec(decay * 3.5)
    f = hz(m)
    sig = (np.sin(2 * np.pi * f * t) * np.exp(-t / decay) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t / (decay * .5))
           + 0.15 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / (decay * .25))) * np.clip(t / 0.002, 0, 1)
    mix.put(sig, t0, bus, gain, pan, hall=hall)


def bell(mix, m, t0, gain, pan=0.0):
    t = tvec(4.0)
    f = hz(m)
    sig = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t / d) for r, a, d in [(1, 1, 2.6), (2.76, .5, 1.4), (5.4, .25, .8), (8.93, .12, .4)])
    mix.put(sig * np.clip(t / 0.003, 0, 1), t0, "music", gain, pan, hall=0.9)


def piano(mix, m, t0, gain, pan=0.0):
    t = tvec(3.5)
    f = hz(m)
    sig = np.zeros_like(t)
    for k in range(1, 9):
        fk = k * f * math.sqrt(1 + 0.0004 * k * k)
        if fk > SR * 0.45:
            break
        tau = 2.4 / (1 + 0.35 * k)
        sig += (np.sin(2 * np.pi * fk * t) + np.sin(2 * np.pi * (fk + 0.25) * t)) * 0.5 / k ** 1.15 * np.exp(-t / tau)
    hammer = lowpass(mix.noise(len(t)), 1800) * np.exp(-t * 90) * 0.15
    mix.put(lowpass(sig + hammer, 3500) * np.clip(t / 0.003, 0, 1), t0, "music", gain, pan, hall=0.5)


def pluck(mix, m, t0, gain, pan=0.0):
    t = tvec(0.6)
    src = saw(hz(m), len(t), mix.rng.random())
    k = np.exp(-t * 14)
    sig = (lowpass(src, 4000) * k + lowpass(src, 500) * (1 - k)) * np.exp(-t * 6) * np.clip(t / 0.002, 0, 1)
    mix.put(sig, t0, "music", gain, pan, hall=0.25, room=0.2)


def spiccato(mix, m, t0, gain, pan=0.0):
    t = tvec(0.35)
    src = saw(hz(m), len(t), mix.rng.random()) + saw(hz(m + 0.08), len(t), mix.rng.random())
    sig = lowpass(src, 4200) * np.clip(t / 0.006, 0, 1) * np.exp(-t * 11)
    mix.put(sig, t0, "music", gain, pan, hall=0.25, room=0.3)


def sub(mix, m, t0, dur, gain):
    n = int((dur + 0.5) * SR)
    sig = sine(hz(m), n) * envelope(n, 0.08, 0.4, hold=dur)
    mix.put(sig, t0, "pad", gain)


def bass(mix, m, t0, dur, gain, cutoff=700):
    n = int((dur + 0.1) * SR)
    sig = lowpass(saw(hz(m), n, mix.rng.random()) + 0.6 * sine(hz(m), n), cutoff) * envelope(n, 0.004, 0.08, hold=dur * 0.8)
    mix.put(sig, t0, "music", gain, room=0.1)


def braam(mix, root, t0, dur, gain):
    n = int((dur + 1.2) * SR)
    src = sum(saw(hz(m + d), n, mix.rng.random()) for m in (root, root + 7, root + 12) for d in (-0.07, 0.07))
    k = np.clip(np.arange(n) / SR / max(dur, 0.1), 0, 1)
    sig = np.tanh(1.8 * (lowpass(src, 300) * (1 - k) + lowpass(src, 1400) * k) / 6) * envelope(n, 0.25, 1.0, hold=dur)
    mix.put(sig, t0, "pad", gain, hall=0.5)


def kick(mix, t0, gain, duck=0.55):
    t = tvec(0.6)
    sig = sine(48 + 110 * np.exp(-t * 28), len(t)) * np.exp(-t * 8.5) + highpass(mix.noise(len(t)), 2000) * np.exp(-t * 300) * 0.35
    mix.put(np.tanh(1.5 * sig), t0, "drums", gain)
    mix.ducks.append((t0, duck))


def taiko(mix, t0, gain, pitch=1.0, pan=0.0):
    t = tvec(1.4)
    sig = sine((60 + 70 * np.exp(-t * 15)) * pitch, len(t)) * np.exp(-t * 4.5) + lowpass(mix.noise(len(t)), 500) * np.exp(-t * 25) * 0.5
    mix.put(sig, t0, "drums", gain, pan, hall=0.3, room=0.5)


def snare(mix, t0, gain, big=False):
    t = tvec(0.9 if big else 0.4)
    sig = sine(185, len(t)) * np.exp(-t * 18) * 0.5 + bandpass(mix.noise(len(t)), 1500, 8000) * np.exp(-t * (8 if big else 16))
    mix.put(sig, t0, "drums", gain, hall=0.35 if big else 0.1, room=0.3)


def clap(mix, t0, gain):
    t = tvec(0.5)
    burst = sum(np.where((t >= d) & (t < d + 0.008), 1.0, 0.0) for d in (0, 0.011, 0.023))
    sig = bandpass(mix.noise(len(t)), 900, 3200) * (burst + np.exp(-np.maximum(t - 0.023, 0) * 18) * (t >= 0.023) * 0.8)
    mix.put(sig, t0, "drums", gain, hall=0.2, room=0.3)


def hat(mix, t0, gain, open_=False, pan=0.25):
    t = tvec(0.5 if open_ else 0.12)
    mix.put(highpass(mix.noise(len(t)), 6500) * np.exp(-t * (9 if open_ else 38)), t0, "drums", gain, pan)


def crash(mix, t0, gain, dur=3.0, reverse=False):
    t = tvec(dur)
    metal = sum(np.sign(np.sin(2 * np.pi * f * t)) for f in (3150, 4290, 5530, 6870)) * 0.08
    sig = (highpass(mix.noise(len(t)), 3500) + bandpass(metal, 4000, 11000)) * np.exp(-t * 3.2 / dur)
    if reverse:
        sig = sig[::-1] * np.clip(t[::-1] / 0.02, 0, 1)[::-1]
    mix.put(sig, t0, "drums", gain, hall=0.4)


# ------------------------------------------------------------------ 音效
def sfx_heart(mix, t, o, chord):
    tt = tvec(0.6)
    thump = lowpass(sine(52, len(tt)) * np.exp(-tt * 12) + sine(38, len(tt)) * np.exp(-tt * 9) * .6, 160)
    mix.put(thump, t, "sfx", 0.9 * o["gain"])
    mix.put(thump * 0.65, t + 0.2, "sfx", 0.9 * o["gain"])


def sfx_hit(mix, t, o, chord):
    kick(mix, t, 0.5 * o["gain"], duck=0.3 * o["gain"])
    snare(mix, t, 0.2 * o["gain"])
    crash(mix, t, 0.05 * o["gain"], 1.0)


def sfx_boom(mix, t, o, chord, k=1.0):
    tt = tvec(3.0)
    body = np.tanh(2 * sine(30 + 28 * np.exp(-tt * 1.2), len(tt))) * np.exp(-tt * 1.3)
    rumble = lowpass(mix.noise(len(tt)), 180) * np.exp(-tt * 2.5) * 1.5
    mix.put((body + rumble) * k, t, "sfx", 0.4 * o["gain"], hall=0.6)
    taiko(mix, t, 0.35 * k * o["gain"], 0.8)
    if k > 0.6:
        crash(mix, t, 0.08 * k * o["gain"], 3.5)
    mix.ducks.append((t, 0.75 * min(1, k)))


def sfx_riser(mix, t, o, chord):
    dur = o["dur"]
    tt = tvec(dur)
    x = tt / dur
    noise = mix.noise(len(tt))
    bands = [400, 800, 1600, 3200, 6400, 10000]
    sweep = sum(bandpass(noise, f * .7, f * 1.4) * np.exp(-((x * (len(bands) - 1) - i) ** 2) / 0.8) for i, f in enumerate(bands))
    root = 48 + (chord[0] if chord else 2)
    tone = lowpass(saw(hz(root) * 2 ** (x * 2), len(tt)), 3000) * 0.25
    sig = (sweep + tone) * x ** 2 * np.clip((dur - tt) / 0.03, 0, 1)
    mix.put(sig, t, "sfx", 0.5 * o["gain"], o["pan"], hall=0.4)


def sfx_reverse(mix, t, o, chord):
    crash(mix, t, 0.16 * o["gain"], o["dur"], reverse=True)


def sfx_swell(mix, t, o, chord):
    root = 48 + (chord[0] if chord else 2)
    dur = o["dur"]
    n = int((dur + 0.6) * SR)
    x = np.clip(np.arange(n) / SR / dur, 0, 1)
    sig = lowpass(sum(saw(hz(m), n, mix.rng.random()) for m in (root, root + 7, root + 12, root + 19)), 1600) * x ** 2.2
    sig *= np.where(np.arange(n) / SR > dur, np.exp(-(np.arange(n) / SR - dur) * 8), 1)
    mix.put(sig / 4, t, "sfx", 0.35 * o["gain"], o["pan"], hall=0.8)


def sfx_whoosh(mix, t, o, chord):
    dur = o["dur"]
    tt = tvec(dur)
    x = tt / dur
    noise = mix.noise(len(tt))
    pos = np.sin(np.pi * x) * 4
    sig = sum(bandpass(noise, f * .7, f * 1.4) * np.exp(-((pos - i) ** 2) / 0.7) for i, f in enumerate([300, 600, 1200, 2400, 4800]))
    sig *= np.sin(np.pi * x) ** 1.5
    pan = np.linspace(-0.8, 0.8, len(tt)) + o["pan"]
    angle = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    mix.put(np.vstack([sig * np.cos(angle), sig * np.sin(angle)]) * math.sqrt(2), t, "sfx", 0.45 * o["gain"], hall=0.3)


def sfx_sparkle(mix, t, o, chord):
    tones = [(chord[0] + i) % 12 for i in chord[1]] if chord else [2, 5, 9]
    count = max(3, int(o["dur"] * 7))
    for _ in range(count):
        m = 84 + tones[int(mix.rng.integers(len(tones)))] + 12 * int(mix.rng.integers(2))
        celesta(mix, m, t + mix.rng.random() * o["dur"], 0.03 * o["gain"], pan=mix.rng.uniform(-0.8, 0.8), decay=0.6, bus="sfx", hall=0.9)


def sfx_chime(mix, t, o, chord):
    m = note_midi(o["note"]) if o.get("note") else 84 + (chord[0] if chord else 2)
    bell(mix, m, t, 0.12 * o["gain"], o["pan"])


def sfx_tick(mix, t, o, chord):
    tt = tvec(0.03)
    sig = highpass(mix.noise(len(tt)), 3000) * np.exp(-tt * 800) + 0.4 * np.sin(2 * np.pi * 3200 * tt) * np.exp(-tt * 400)
    mix.put(sig, t, "sfx", 0.25 * o["gain"], o["pan"])


def sfx_glitch(mix, t, o, chord):
    for k in range(6):
        start = t + mix.rng.random() * o["dur"]
        tt = tvec(0.02 + 0.05 * mix.rng.random())
        src = np.round(mix.noise(len(tt)) * 2) / 2 + np.sign(np.sin(2 * np.pi * mix.rng.uniform(200, 2000) * tt))
        mix.put(src * 0.3, start, "sfx", 0.3 * o["gain"], mix.rng.uniform(-0.6, 0.6))


def sfx_drop(mix, t, o, chord):
    tt = tvec(o["dur"])
    sig = np.tanh(1.5 * sine(90 * (30 / 90) ** (tt / o["dur"]), len(tt))) * np.exp(-tt * 1.5 / o["dur"])
    mix.put(sig, t, "sfx", 0.5 * o["gain"], hall=0.3)


SFX = {"heart": sfx_heart, "hit": sfx_hit, "boom": sfx_boom, "riser": sfx_riser, "reverse": sfx_reverse, "swell": sfx_swell,
       "whoosh": sfx_whoosh, "sparkle": sfx_sparkle, "chime": sfx_chime, "tick": sfx_tick, "glitch": sfx_glitch, "drop": sfx_drop}


# ------------------------------------------------------------------ 编配
class Song:
    def __init__(self, timeline):
        self.bpm = timeline["bpm"]
        self.beat = 60 / self.bpm
        self.bar = 4 * self.beat
        self.style = timeline.get("style", "cinematic")
        self.duration = timeline["duration"]
        self.sections = timeline["sections"]
        for s in self.sections:
            s["parsed"] = [parse_chord(c) for c in s.get("chords", [])]

    def bars(self, section):
        """段落里每个小节的 (起点, 长度, 和弦)；最后一个小节可能不满。"""
        out, t, k = [], section["start"], 0
        while t < section["end"] - 1e-6:
            length = min(self.bar, section["end"] - t)
            chord = section["parsed"][k % len(section["parsed"])] if section["parsed"] else None
            out.append((t, length, chord))
            t += self.bar
            k += 1
        return out

    def chord_at(self, t):
        for s in self.sections:
            if s["start"] <= t < s["end"]:
                for start, length, chord in self.bars(s):
                    if start <= t < start + length:
                        return chord
        return None


ARP = (0, 2, 1, 3, 2, 4, 3, 5)


def arrange(song, mix):
    voices = None
    last = len(song.sections) - 1
    for idx, section in enumerate(song.sections):
        energy = section.get("energy", 0)
        bars = song.bars(section)
        nxt = song.sections[idx + 1] if idx < last else None
        for b, (t0, length, chord) in enumerate(bars):
            final = idx == last and b == len(bars) - 1
            hold = song.duration - t0 if final else length
            if chord is None or energy == 0:
                continue
            voices = voicing(chord, voices)
            root = 36 + chord[2] if chord[2] >= 4 else 48 + chord[2] - 12
            pool = voices + [n + 12 for n in voices[:3]]
            if song.style == "cinematic":
                cinematic_bar(song, mix, energy, t0, length, hold, voices, root, pool, b, len(bars), final)
            else:
                electronic_bar(song, mix, energy, t0, length, hold, voices, root, pool, b, final)
        # 下一段能量明显抬升时，用一个小节的上升音效把听众推过去
        if nxt and nxt.get("energy", 0) >= energy + 2 and abs(nxt["start"] - section["end"]) < 0.01:
            dur = min(song.bar, section["end"] - section["start"])
            sfx_riser(mix, section["end"] - dur, {"gain": 0.8, "pan": 0.0, "dur": dur}, bars[-1][2] if bars else None)


def cinematic_bar(song, mix, e, t0, length, hold, voices, root, pool, b, nbars, final):
    beat, eighth = song.beat, song.beat / 2
    pad(mix, voices, t0, hold, 0.05 + 0.01 * e, bright=1800 + 500 * e)
    sub(mix, root, t0, hold, 0.035 if e < 3 else 0.05)
    if e == 1 and b % 2 == 0:
        for k, m in enumerate((voices[0], voices[-1] + 12)):
            piano(mix, m, t0 + k * 0.03, 0.08, pan=-0.2 + 0.4 * k)
    steps = int(round(length / eighth))
    if e >= 2 and not final:
        for i in range(steps):
            celesta(mix, pool[ARP[i % 8] % len(pool)] + 12, t0 + i * eighth, 0.04, pan=0.35 * math.sin(i))
    if e >= 3 and not final:
        for i in range(int(round(length / beat))):
            if i % 2 == 0:
                kick(mix, t0 + i * beat, 0.26 if e == 3 else 0.3)
        if b % 2 == 0:
            taiko(mix, t0, 0.2, pan=-0.2)
        for i in range(steps):
            hat(mix, t0 + i * eighth, 0.06 if i % 2 else 0.085)
            spiccato(mix, root + 24 + (7 if i % 4 == 2 else 0), t0 + i * eighth, 0.08, pan=0.3)
    if e >= 4:
        choir(mix, voices[1:] + [voices[0] + 12], t0, hold, 0.07)
        if not final:
            for i in range(int(round(length / beat))):
                if i % 2 == 1:
                    snare(mix, t0 + i * beat, 0.13, big=True)
            for i in range(steps):
                bass(mix, root, t0 + i * eighth, eighth * 0.85, 0.05)
            if b == nbars - 1:
                for i in range(steps):
                    taiko(mix, t0 + i * eighth, 0.1 + 0.02 * i, pitch=1.3, pan=0.3 * (-1) ** i)
        if b == 0:
            braam(mix, root - 12 if root >= 36 else root, t0, min(hold, song.bar), 0.12)
            crash(mix, t0, 0.07)


def electronic_bar(song, mix, e, t0, length, hold, voices, root, pool, b, final):
    beat, eighth, sixteenth = song.beat, song.beat / 2, song.beat / 4
    pad(mix, voices, t0, hold, 0.045 + 0.008 * e, bright=1500 + 600 * e, voices=5, spread=0.14, attack=0.3)
    sub(mix, root, t0, hold, 0.045)
    if final:
        return
    if e >= 2:
        for i in range(int(round(length / sixteenth))):
            if i % 3 != 2:
                pluck(mix, pool[ARP[i % 8] % len(pool)] + 12, t0 + i * sixteenth, 0.05, pan=0.4 * math.sin(i * 1.3))
    if e >= 3:
        for i in range(int(round(length / beat))):
            kick(mix, t0 + i * beat, 0.45, duck=0.7)
            hat(mix, t0 + i * beat + eighth, 0.03, open_=True, pan=0.15)
            if i % 2 == 1:
                clap(mix, t0 + i * beat, 0.16)
            bass(mix, root, t0 + i * beat + eighth, eighth * 0.8, 0.09, cutoff=900)
    if e >= 4:
        for i in range(int(round(length / sixteenth))):
            hat(mix, t0 + i * sixteenth, 0.012, pan=-0.3)
        for i in range(int(round(length / beat))):
            pad(mix, [n + 12 for n in voices], t0 + i * beat + eighth, eighth * 0.6, 0.03, bright=5000, voices=5, spread=0.2, attack=0.005, hall=0.3, bus="music")
        if b == 0:
            crash(mix, t0, 0.06)


# ------------------------------------------------------------------ 混音与母带
def reverb_ir(seconds, rng, damp):
    t = tvec(seconds)
    decay = np.exp(-t * 6.9 / seconds)
    ir = np.vstack([lowpass(rng.standard_normal(len(t)), damp) for _ in range(2)]) * decay
    ir[:, : int(0.012 * SR)] = 0
    return ir / np.sqrt(np.sum(ir ** 2, axis=1, keepdims=True))


def master(mix, song, rng):
    out = mix.bus["music"] + mix.bus["drums"] + mix.bus["sfx"]
    t = np.arange(mix.n) / SR
    duck = np.ones(mix.n)
    for t0, depth in mix.ducks:
        i = int(t0 * SR)
        j = min(mix.n, i + int(0.6 * SR))
        if 0 <= i < mix.n:
            duck[i:j] = np.minimum(duck[i:j], 1 - depth * np.exp(-(t[i:j] - t0) / 0.16))
    out += mix.bus["pad"] * duck
    for name, seconds, damp, level in (("hall", 3.2, 5000, 0.45), ("room", 0.8, 7000, 0.35)):
        ir = reverb_ir(seconds, rng, damp)
        wet = np.vstack([fftconvolve(mix.bus[name][c], ir[c])[: mix.n] for c in range(2)])
        out += wet * level
    out = highpass(out, 25)
    # 平缓压缩把各层粘在一起，再软限幅留出峰值余量
    level = np.sqrt(np.maximum(lowpass(np.mean(out ** 2, axis=0), 8), 0) + 1e-9)   # 低通会下冲出负值
    gain = np.minimum(1.0, (0.25 / level) ** 0.35)
    out *= gain
    out /= max(1e-6, np.max(np.abs(out))) * 1.05
    out = np.tanh(out * 1.3) / np.tanh(1.3)
    n = int(song.duration * SR)
    out = out[:, :n]
    last_end = max((s["end"] for s in song.sections), default=0)
    fade = min(2.5, max(0.3, song.duration - last_end))
    out[:, -int(fade * SR):] *= np.linspace(1, 0, int(fade * SR)) ** 1.5
    return out


def write_wav(path, audio):
    pcm = (np.clip(audio.T, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def loudnorm(source, out):
    """两遍 loudnorm：先测量，再按测量值线性归一到 -14 LUFS、真峰值 -1.5 dB。"""
    target = "I=-14:TP=-2:LRA=11"
    run = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(source), "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                         capture_output=True, text=True)
    measured = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", run.stderr).group(0))
    flt = (f"loudnorm={target}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
           f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true")
    run = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-af", flt, "-ar", str(SR), *OUTPUT[out.suffix.lower()], str(out)],
                         capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr.strip()[-800:])
    return round(float(measured["input_i"]), 1)


# ------------------------------------------------------------------ 校验与入口
def validate(timeline):
    errors = []
    if not isinstance(timeline.get("duration"), (int, float)) or timeline["duration"] <= 0:
        errors.append("duration must be a positive number of seconds")
    if not isinstance(timeline.get("bpm"), (int, float)) or not 40 <= timeline["bpm"] <= 220:
        errors.append("bpm must be between 40 and 220")
    if timeline.get("style", "cinematic") not in STYLES:
        errors.append(f"style must be one of {', '.join(STYLES)}")
    duration = timeline.get("duration") or 0
    previous_end = 0.0
    for i, s in enumerate(timeline.get("sections", [])):
        where = f"sections[{i}] ({s.get('name', 'unnamed')})"
        if not (isinstance(s.get("start"), (int, float)) and isinstance(s.get("end"), (int, float)) and s["start"] < s["end"]):
            errors.append(f"{where}: start and end must be numbers with start < end")
            continue
        if s["start"] < previous_end - 1e-3:
            errors.append(f"{where}: overlaps the previous section; sections must be in time order")
        if s["end"] > duration + 1e-3:
            errors.append(f"{where}: ends after the duration")
        previous_end = s["end"]
        if s.get("energy", 0) not in (0, 1, 2, 3, 4):
            errors.append(f"{where}: energy must be an integer from 0 to 4")
        for c in s.get("chords", []):
            try:
                parse_chord(c)
            except ValueError as e:
                errors.append(f"{where}: {e}")
        if s.get("energy", 0) > 0 and not s.get("chords"):
            errors.append(f"{where}: energy above 0 needs chords")
    for i, h in enumerate(timeline.get("hits", [])):
        if not 0 <= h.get("t", -1) <= duration or not 0 < h.get("k", 1) <= 1.5:
            errors.append(f"hits[{i}]: t must lie within the duration and k in (0, 1.5]")
    for i, c in enumerate(timeline.get("cues", [])):
        if c.get("name") not in SFX:
            errors.append(f"cues[{i}]: unknown sound {c.get('name')!r}; use {', '.join(SFX)}")
        if not isinstance(c.get("t"), (int, float)) or not 0 <= c["t"] <= duration:
            errors.append(f"cues[{i}]: t must lie within the duration")
        if c.get("note"):
            try:
                note_midi(c["note"])
            except ValueError as e:
                errors.append(f"cues[{i}]: {e}")
    if errors:
        raise Invalid("\n".join(errors))


def render(timeline, seed):
    validate(timeline)
    rng = np.random.default_rng(seed)
    song = Song(timeline)
    mix = Mix(song.duration + 4, rng)
    arrange(song, mix)
    for h in timeline.get("hits", []):
        sfx_boom(mix, h["t"], {"gain": 1.0, "pan": 0.0}, song.chord_at(h["t"]), k=h.get("k", 1))
    for c in timeline.get("cues", []):
        o = {"gain": c.get("gain", 1.0), "pan": c.get("pan", 0.0), "dur": c.get("dur", SFX_DEFAULT_DUR.get(c["name"], 0.5)), "note": c.get("note")}
        SFX[c["name"]](mix, c["t"], o, song.chord_at(c["t"]))
    return master(mix, song, rng)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("timeline", type=Path, help="Timeline JSON")
    parser.add_argument("--out", type=Path, required=True, help="Output audio: .mp3, .m4a or .wav")
    parser.add_argument("--seed", type=int, default=1, help="Variation seed; the same seed reproduces the same mix")
    args = parser.parse_args()
    if args.out.suffix.lower() not in OUTPUT:
        parser.error("--out must end with .mp3, .m4a or .wav")
    if not args.timeline.is_file():
        parser.error(f"timeline not found: {args.timeline}")
    if not shutil.which("ffmpeg"):
        parser.error("ffmpeg is not on PATH")
    try:
        timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
        audio = render(timeline, args.seed)
    except (Invalid, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        sys.exit(1)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "mix.wav"
        write_wav(raw, audio)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        measured = loudnorm(raw, args.out)
    print(json.dumps({"ok": True, "output": str(args.out), "duration": round(timeline["duration"], 3), "style": timeline.get("style", "cinematic"),
                      "sections": len(timeline.get("sections", [])), "hits": len(timeline.get("hits", [])), "cues": len(timeline.get("cues", [])),
                      "loudness_before_normalization": measured, "loudness": -14}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
