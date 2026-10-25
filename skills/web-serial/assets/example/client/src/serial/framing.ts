export interface Frame {
  text: string;
  // Arrival time of the chunk that completed the line, from performance.now().
  time: number;
}

const NEWLINE = 0x0a;
const CARRIAGE_RETURN = 0x0d;

// Collects bytes until a newline and decodes only complete lines. A read() can end anywhere:
// halfway through a line, between \r and \n, or inside a multi-byte character, so chunks are
// never decoded on their own.
export class LineFramer {
  private pending = new Uint8Array(0);
  private readonly decoder: TextDecoder;

  constructor(
    // Without a newline for this many bytes the data is not text lines (often a wrong baud
    // rate); the bytes are passed on as one frame so the garbage stays visible.
    private readonly maxLineBytes = 4096,
    encoding = "utf-8",
  ) {
    this.decoder = new TextDecoder(encoding);
  }

  push(chunk: Uint8Array, time: number): Frame[] {
    const bytes = new Uint8Array(this.pending.length + chunk.length);
    bytes.set(this.pending);
    bytes.set(chunk, this.pending.length);

    const frames: Frame[] = [];
    let start = 0;
    for (let i = 0; i < bytes.length; i++) {
      if (bytes[i] === NEWLINE) {
        frames.push({ text: this.decode(bytes.subarray(start, i)), time });
        start = i + 1;
      } else if (i + 1 - start >= this.maxLineBytes) {
        frames.push({ text: this.decode(bytes.subarray(start, i + 1)), time });
        start = i + 1;
      }
    }
    this.pending = bytes.slice(start);
    return frames;
  }

  reset() {
    this.pending = new Uint8Array(0);
  }

  private decode(line: Uint8Array) {
    const end =
      line.length > 0 && line[line.length - 1] === CARRIAGE_RETURN ? line.length - 1 : line.length;
    return this.decoder.decode(line.subarray(0, end));
  }
}

const NAMED_VALUE =
  /([\p{L}_][\p{L}\p{N}_.]*)\s*[:=]\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)/gu;
const NUMBER = /^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$/;

// Reads one line of the formats firmware usually prints, the same ones the Arduino Serial
// Plotter accepts: "temp=21.5 hum=40", "temp:21.5,hum:40", or bare numbers "21.5,40" / "21.5 40"
// (named ch1, ch2, ...). Anything else, such as a boot banner, yields no values.
export function parseValues(text: string): Record<string, number> {
  const values: Record<string, number> = {};
  for (const match of text.matchAll(NAMED_VALUE)) {
    values[match[1]] = Number(match[2]);
  }
  if (Object.keys(values).length > 0) return values;

  const parts = text.trim().split(/[\s,;]+/);
  if (parts[0] === "" || !parts.every((part) => NUMBER.test(part))) return values;
  parts.forEach((part, index) => {
    values[`ch${index + 1}`] = Number(part);
  });
  return values;
}
