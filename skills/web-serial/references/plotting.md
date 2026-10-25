# Charts, recording and export

Draw on `<canvas>`, not SVG or DOM elements per point. Keep samples in ring buffers (`Series` in `src/chart.ts`), draw at most once per animation frame, and size canvases by `devicePixelRatio`. Received data only fills buffers; the render loop decides what is on screen.

## Rolling time chart

The example's `drawRolling` is the model for any time plot:

- The time axis is the window `[now - windowMs, now]` and `now` advances every frame, so the trace scrolls like an oscilloscope even when nothing arrives. Never fit the time axis to the data (the trace stops scrolling and gets squeezed) and never use the sample index (gaps and stalls shift the trace).
- Each pixel column draws the minimum and maximum of its samples. Short spikes stay visible at any zoom; taking every n-th sample would hide them.
- The value axis fits the visible data with 10% padding. When the range is known (a percentage, a 12-bit ADC, ±1 g), fix it instead so the trace does not jump.
- Pause by freezing `now`; resume from the current time.
- Zoom changes `windowMs`. Ring capacity must hold the longest window at the highest rate: 60 s at 500 Hz is 30,000 samples per channel.
- Timestamps: arrival time from `performance.now()` is enough for trends. For exact intervals have the device send its own time (`t=` in milliseconds) and plot against that.

Measured with `drawRolling` in desktop Chrome on a 900×256 canvas at device pixel ratio 2: one channel with 50,000 visible samples takes about 2 ms per frame, 200,000 about 3 ms, well inside a 16 ms frame. Raise ring capacities before reaching for workers or WebGL; several charts with many channels each are where the budget runs out.

## Several charts and channels

- One canvas per chart. Assign channels to charts by name, and keep the assignment and colors in `localStorage` so a reload keeps the layout.
- Show the latest value of each channel next to the chart with its unit; update the numbers once per frame, not per line.
- Gauges and big numbers suit slow values (temperature, battery); a chart suits anything that moves faster than once a second.

## XY trajectory

For position data (`x=`, `y=` from a robot or plotter):

- Keep the last N points in a ring, draw them as a polyline and mark the newest one; draw the heading as an arrow when the device sends it, or from `atan2(dy, dx)` of the last two points.
- Use fixed field coordinates when the arena is known, otherwise the bounding box of the visible points plus 10%, with equal scale on both axes so circles stay round.
- Thin very long tracks by distance (keep a point only when it moved more than a pixel), not by count.

## Spectrum

An FFT needs evenly spaced samples: use the device's sample rate, not arrival times. Take the latest 2^n samples, apply a Hann window and plot magnitudes up to half the sample rate.

```ts
// In-place radix-2 FFT; re and im have the same power-of-two length.
function fft(re: Float64Array, im: Float64Array) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let size = 2; size <= n; size <<= 1) {
    const angle = (-2 * Math.PI) / size;
    for (let start = 0; start < n; start += size) {
      for (let k = 0; k < size / 2; k++) {
        const wr = Math.cos(angle * k);
        const wi = Math.sin(angle * k);
        const a = start + k;
        const b = a + size / 2;
        const tr = re[b] * wr - im[b] * wi;
        const ti = re[b] * wi + im[b] * wr;
        re[b] = re[a] - tr;
        im[b] = im[a] - ti;
        re[a] += tr;
        im[a] += ti;
      }
    }
  }
}

// Hann window before the transform: re[i] = sample[i] * (0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1)))
// Bin k is k * sampleRate / n Hz; its magnitude is Math.hypot(re[k], im[k]) * 2 / n.
```

## Recording, replay and export

- Record raw chunks with their arrival time, not decoded lines. A recording can then be decoded again with another baud-rate guess, encoding or parser, and replay goes through the same framer and parser as live data.
- Replay feeds the recorded chunks into `framer.push(chunk, time)` at their recorded offsets (or as fast as possible for analysis), so live and replayed data cannot behave differently.
- Store the settings that shaped the data (baud rate, protocol version, channel layout) with the recording.
- CSV for Excel: start with a byte order mark and name the encoding, or Chinese headers turn into garbage on Windows: `new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })`, downloaded through an `<a download>` link.
- Long recordings: stream to disk with `showSaveFilePicker()` and a writable file stream instead of growing an array; Web Serial already requires a Chromium browser, which has this API.
- Raw exports as hex with a time column survive any encoding mistake.
