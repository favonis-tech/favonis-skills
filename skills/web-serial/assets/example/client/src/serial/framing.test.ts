import { describe, expect, it } from "vitest";

import { LineFramer, parseValues } from "./framing";

const bytes = (text: string) => new TextEncoder().encode(text);

function feed(framer: LineFramer, chunks: Uint8Array[]) {
  return chunks.flatMap((chunk) => framer.push(chunk, 0)).map((frame) => frame.text);
}

describe("LineFramer", () => {
  it("gives the same lines however the bytes are split", () => {
    const data = bytes("温度=21.5\r\nhum=40\r\nok\n");
    const whole = feed(new LineFramer(), [data]);
    const oneByOne = feed(
      new LineFramer(),
      [...data].map((byte) => Uint8Array.of(byte)),
    );

    expect(whole).toEqual(["温度=21.5", "hum=40", "ok"]);
    expect(oneByOne).toEqual(whole);
  });

  it("keeps an unfinished line until its newline arrives", () => {
    const framer = new LineFramer();

    expect(feed(framer, [bytes("a=1\r")])).toEqual([]);
    expect(feed(framer, [bytes("\nb=")])).toEqual(["a=1"]);
    expect(feed(framer, [bytes("2\n")])).toEqual(["b=2"]);
  });

  it("passes on data without newlines once it reaches the line limit", () => {
    const framer = new LineFramer(8);

    expect(feed(framer, [bytes("abcdefghij")])).toEqual(["abcdefgh"]);
    expect(feed(framer, [bytes("\n")])).toEqual(["ij"]);
  });
});

describe("parseValues", () => {
  it("reads named values", () => {
    expect(parseValues("temp=21.5 hum: 40")).toEqual({ temp: 21.5, hum: 40 });
    expect(parseValues("sine:-0.5,cos:1e-3")).toEqual({ sine: -0.5, cos: 0.001 });
    expect(parseValues("温度=21.5")).toEqual({ 温度: 21.5 });
  });

  it("numbers bare columns", () => {
    expect(parseValues("1.5, -2  3")).toEqual({ ch1: 1.5, ch2: -2, ch3: 3 });
  });

  it("ignores lines without values", () => {
    expect(parseValues("Simulated device ready")).toEqual({});
    expect(parseValues("")).toEqual({});
    expect(parseValues("12 apples")).toEqual({});
  });
});
