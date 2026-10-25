import { type Frame, LineFramer } from "./framing";
import type { SerialOptions, SerialPortLike } from "./types";

export type ConnectionState = "closed" | "opening" | "open" | "closing";

export interface ConnectionEvents {
  onFrame(frame: Frame): void;
  onState(state: ConnectionState): void;
  // Garbled data while the port stays open, or the device going away.
  onError(error: unknown): void;
}

// Owns one open port: the read loop, the single writer and the shutdown order.
export class SerialConnection {
  private port: SerialPortLike | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private writer: WritableStreamDefaultWriter<Uint8Array> | null = null;
  private reading: Promise<void> = Promise.resolve();
  // Bumped by every open and close, so a read loop or an open that finishes late knows it is stale.
  private epoch = 0;
  private readonly framer = new LineFramer();
  private readonly encoder = new TextEncoder();

  constructor(private readonly events: ConnectionEvents) {}

  get connected() {
    return this.writer !== null;
  }

  async open(port: SerialPortLike, options: SerialOptions) {
    await this.close();
    const epoch = ++this.epoch;
    this.events.onState("opening");
    try {
      // Parameters are fixed once the port is open; changing the baud rate means close and open.
      await port.open(options);
    } catch (error) {
      if (epoch === this.epoch) this.events.onState("closed");
      throw error;
    }
    if (epoch !== this.epoch || !port.writable) {
      await port.close().catch(() => {});
      return;
    }
    this.port = port;
    this.framer.reset();
    // One writer for the whole connection: write() calls queue inside the stream, while a
    // getWriter() per message throws as soon as an earlier write still holds the lock.
    this.writer = port.writable.getWriter();
    this.events.onState("open");
    this.reading = this.readLoop(port, epoch);
  }

  async send(text: string) {
    if (!this.writer) throw new Error("The port is not open.");
    await this.writer.write(this.encoder.encode(text));
  }

  async close() {
    const port = this.port;
    if (!port) return;
    this.epoch++;
    this.events.onState("closing");
    await this.reader?.cancel().catch(() => {});
    await this.reading;
    await this.release(port);
    this.events.onState("closed");
  }

  private async readLoop(port: SerialPortLike, epoch: number) {
    // port.readable is replaced after a recoverable error (framing, parity, break, buffer overrun)
    // and becomes null when the device is lost.
    while (epoch === this.epoch && port.readable) {
      const reader = port.readable.getReader();
      this.reader = reader;
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          for (const frame of this.framer.push(value, performance.now()))
            this.events.onFrame(frame);
        }
      } catch (error) {
        this.events.onError(error);
      } finally {
        reader.releaseLock();
        this.reader = null;
      }
    }
    if (epoch === this.epoch) {
      // The device went away (unplugged, reset into a bootloader) rather than being closed here.
      this.epoch++;
      await this.release(port);
      this.events.onState("closed");
    }
  }

  // Runs after the read loop has released its reader. Order matters: a port whose streams are
  // still locked refuses to close and stays busy until the page is reloaded.
  private async release(port: SerialPortLike) {
    this.writer?.releaseLock();
    this.writer = null;
    this.port = null;
    await port.close().catch(() => {});
  }
}

// Turns Web Serial failures into a sentence for the interface; null when there is nothing to say.
export function describeSerialError(error: unknown): string | null {
  const name = error instanceof DOMException || error instanceof Error ? error.name : "";
  switch (name) {
    case "NotFoundError":
      return null; // The user closed the device chooser without picking a port.
    case "SecurityError":
      return "This page is not allowed to use serial ports. Open it in its own browser tab.";
    case "InvalidStateError":
      return "This port is already open in this page.";
    case "NetworkError":
      return "The port could not be opened or the device was disconnected. Close other programs using it (Arduino IDE, another tab) and reconnect.";
    case "BreakError":
    case "FramingError":
    case "ParityError":
      return "Received garbled data. Check that the baud rate matches the device.";
    case "BufferOverrunError":
      return "The device sent data faster than the page read it; some bytes were lost.";
    default:
      return error instanceof Error ? error.message : String(error);
  }
}
