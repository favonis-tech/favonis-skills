import { describe, expect, it, vi } from "vitest";

import { type ConnectionState, SerialConnection } from "./connection";
import type { Frame } from "./framing";
import { SimulatedSerial } from "./simulated";

function setup() {
  const serial = new SimulatedSerial({ intervalMs: 5 });
  const frames: string[] = [];
  const states: ConnectionState[] = [];
  const errors: unknown[] = [];
  const connection = new SerialConnection({
    onFrame: (frame: Frame) => frames.push(frame.text),
    onState: (state) => states.push(state),
    onError: (error) => errors.push(error),
  });
  return { serial, connection, frames, states, errors };
}

describe("SerialConnection", () => {
  it("receives whole lines and sends text", async () => {
    const { serial, connection, frames } = setup();
    await connection.open(await serial.requestPort(), { baudRate: 115200 });

    await vi.waitFor(() =>
      expect(frames.filter((f) => f.startsWith("sine=")).length).toBeGreaterThanOrEqual(3),
    );
    expect(frames[0]).toBe("Simulated device ready");
    expect(frames.find((f) => f.startsWith("sine="))).toMatch(
      /^sine=-?\d\.\d{3} noise=-?\d\.\d{3}$/,
    );

    await connection.send("led on\n");
    await vi.waitFor(() => expect(frames).toContain("ack led on"));
    await connection.close();
  });

  it("closes so that the port can be opened again", async () => {
    const { serial, connection, frames, states } = setup();
    const port = await serial.requestPort();

    await connection.open(port, { baudRate: 9600 });
    await connection.close();
    expect(states).toEqual(["opening", "open", "closing", "closed"]);
    expect(port.readable).toBeNull();

    frames.length = 0;
    await connection.open(port, { baudRate: 115200 });
    await vi.waitFor(() => expect(frames).toContain("Simulated device ready"));
    await connection.close();
  });

  it("reports an unplugged device and ends closed", async () => {
    const { serial, connection, states, errors } = setup();
    await connection.open(await serial.requestPort(), { baudRate: 115200 });

    serial.port.unplug();

    await vi.waitFor(() => expect(states.at(-1)).toBe("closed"));
    expect(errors).toHaveLength(1);
    expect((errors[0] as DOMException).name).toBe("NetworkError");
    expect(connection.connected).toBe(false);
    await expect(connection.send("x")).rejects.toThrow();
  });
});
