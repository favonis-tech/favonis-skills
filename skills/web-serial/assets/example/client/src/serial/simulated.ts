import type { SerialLike, SerialOptions, SerialPortInfo, SerialPortLike } from "./types";

export interface SimulatedDeviceOptions {
  // Milliseconds between generated lines.
  intervalMs?: number;
  random?: () => number;
}

// A stand-in for navigator.serial with one device behind it. The app uses it for its
// "Simulated device" mode and the tests use it in place of hardware. Like a real port it
// delivers lines in arbitrary chunks, answers writes, and can be unplugged.
export class SimulatedSerial extends EventTarget implements SerialLike {
  readonly port: SimulatedPort;
  private granted = false;

  constructor(options: SimulatedDeviceOptions = {}) {
    super();
    this.port = new SimulatedPort(options);
  }

  async requestPort() {
    this.granted = true;
    return this.port;
  }

  async getPorts() {
    return this.granted ? [this.port] : [];
  }
}

export class SimulatedPort extends EventTarget implements SerialPortLike {
  private opened = false;
  private lost = false;
  private input: ReadableStream<Uint8Array> | null = null;
  private controller: ReadableStreamDefaultController<Uint8Array> | null = null;
  private output: WritableStream<Uint8Array> | null = null;
  private timer: ReturnType<typeof setInterval> | undefined;
  private noise = 0;
  private readonly encoder = new TextEncoder();
  private readonly decoder = new TextDecoder();
  private readonly intervalMs: number;
  private readonly random: () => number;

  constructor({ intervalMs = 20, random = Math.random }: SimulatedDeviceOptions) {
    super();
    this.intervalMs = intervalMs;
    this.random = random;
  }

  // As in Web Serial, a cancelled stream is replaced on the next access while the port is open.
  get readable() {
    return this.opened && !this.lost ? this.inputStream() : null;
  }

  get writable() {
    if (!this.opened || this.lost) return null;
    this.output ??= new WritableStream<Uint8Array>({
      write: (chunk) => this.answer(this.decoder.decode(chunk)),
    });
    return this.output;
  }

  getInfo(): SerialPortInfo {
    return {};
  }

  async open(_options: SerialOptions) {
    if (this.lost) throw new DOMException("The device has been lost.", "NetworkError");
    if (this.opened) throw new DOMException("The port is already open.", "InvalidStateError");
    this.opened = true;
    this.inputStream();
    this.emit("Simulated device ready\n");
    this.timer = setInterval(() => this.sample(), this.intervalMs);
  }

  async close() {
    if (!this.opened) throw new DOMException("The port is already closed.", "InvalidStateError");
    if (this.input?.locked || this.output?.locked) {
      throw new TypeError("Cannot close a port while its streams are locked.");
    }
    clearInterval(this.timer);
    await this.input?.cancel();
    this.input = this.controller = this.output = null;
    this.opened = false;
  }

  // Simulates pulling the cable: pending reads fail and the port cannot be used again.
  unplug() {
    clearInterval(this.timer);
    this.lost = true;
    this.controller?.error(new DOMException("The device has been lost.", "NetworkError"));
    this.input = this.controller = this.output = null;
    this.dispatchEvent(new Event("disconnect"));
  }

  private inputStream() {
    this.input ??= new ReadableStream<Uint8Array>({
      start: (controller) => {
        this.controller = controller;
      },
      cancel: () => {
        this.input = null;
        this.controller = null;
      },
    });
    return this.input;
  }

  private sample() {
    const seconds = performance.now() / 1000;
    this.noise = this.noise * 0.9 + (this.random() - 0.5) * 0.2;
    const sine = Math.sin(2 * Math.PI * 0.5 * seconds);
    this.emit(`sine=${sine.toFixed(3)} noise=${this.noise.toFixed(3)}\n`);
  }

  private answer(text: string) {
    const command = text.replace(/[\r\n]+$/, "");
    if (command) this.emit(`ack ${command}\n`);
  }

  // Splits each line into random chunks, the way bytes arrive from a real USB serial adapter.
  private emit(text: string) {
    const bytes = this.encoder.encode(text);
    for (let start = 0; start < bytes.length; ) {
      const end = Math.min(bytes.length, start + 1 + Math.floor(this.random() * 12));
      this.controller?.enqueue(bytes.slice(start, end));
      start = end;
    }
  }
}
