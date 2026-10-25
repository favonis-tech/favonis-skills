// Samples of one channel in a fixed-size ring: memory stays flat however long the page runs.
export class Series {
  private readonly times: Float64Array;
  private readonly values: Float32Array;
  private head = 0;
  private count = 0;

  constructor(private readonly capacity = 20_000) {
    this.times = new Float64Array(capacity);
    this.values = new Float32Array(capacity);
  }

  push(time: number, value: number) {
    this.times[this.head] = time;
    this.values[this.head] = value;
    this.head = (this.head + 1) % this.capacity;
    this.count = Math.min(this.count + 1, this.capacity);
  }

  clear() {
    this.head = 0;
    this.count = 0;
  }

  // Oldest first.
  forEach(visit: (time: number, value: number) => void) {
    for (let n = 0; n < this.count; n++) {
      const i = (this.head - this.count + n + this.capacity) % this.capacity;
      visit(this.times[i], this.values[i]);
    }
  }
}

export interface Channel {
  name: string;
  color: string;
  series: Series;
}

export const CHANNEL_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"];

// Draws the last windowMs of every channel like an oscilloscope: the time axis always ends at
// `now`, so the trace keeps moving even when no data arrives. Only the value axis follows the
// data. Each pixel column keeps its minimum and maximum, so short spikes survive any zoom.
export function drawRolling(
  canvas: HTMLCanvasElement,
  channels: Channel[],
  now: number,
  windowMs: number,
) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const start = now - windowMs;
  let low = Number.POSITIVE_INFINITY;
  let high = Number.NEGATIVE_INFINITY;
  for (const channel of channels) {
    channel.series.forEach((time, value) => {
      if (time < start) return;
      low = Math.min(low, value);
      high = Math.max(high, value);
    });
  }
  if (!Number.isFinite(low)) {
    low = -1;
    high = 1;
  } else if (low === high) {
    low -= 1;
    high += 1;
  }
  const padding = (high - low) * 0.1;
  low -= padding;
  high += padding;

  const left = 48;
  const plotWidth = Math.max(1, width - left);
  const x = (time: number) => left + ((time - start) / windowMs) * plotWidth;
  const y = (value: number) => height - ((value - low) / (high - low)) * height;

  const text = getComputedStyle(canvas).color;
  ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
  ctx.textBaseline = "middle";
  ctx.lineWidth = 1;
  for (let step = 0; step <= 4; step++) {
    const value = low + ((high - low) * step) / 4;
    const row = Math.round(y(value)) + 0.5;
    ctx.strokeStyle = "rgba(127, 127, 127, 0.18)";
    ctx.beginPath();
    ctx.moveTo(left, row);
    ctx.lineTo(width, row);
    ctx.stroke();
    ctx.fillStyle = text;
    ctx.fillText(formatTick(value, high - low), 4, Math.min(height - 6, Math.max(6, row)));
  }

  ctx.lineWidth = 1.5;
  ctx.lineJoin = "round";
  for (const channel of channels) {
    ctx.strokeStyle = channel.color;
    ctx.beginPath();
    let column = Number.NaN;
    let min = 0;
    let max = 0;
    let started = false;
    const flush = () => {
      if (Number.isNaN(column)) return;
      if (started) ctx.lineTo(column, y(max));
      else ctx.moveTo(column, y(max));
      ctx.lineTo(column, y(min));
      started = true;
    };
    channel.series.forEach((time, value) => {
      if (time < start) return;
      const next = Math.floor(x(time));
      if (next !== column) {
        flush();
        column = next;
        min = max = value;
      } else {
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    });
    flush();
    ctx.stroke();
  }
}

function formatTick(value: number, span: number) {
  const digits = span >= 100 ? 0 : span >= 1 ? 2 : 4;
  return value.toFixed(digits);
}
