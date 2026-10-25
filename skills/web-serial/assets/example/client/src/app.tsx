import { Eraser, Plug, Send, Unplug } from "lucide-react";
import { type FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import { CHANNEL_COLORS, type Channel, drawRolling, Series } from "@/chart";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type ConnectionState, describeSerialError, SerialConnection } from "@/serial/connection";
import { parseValues } from "@/serial/framing";
import { SimulatedSerial } from "@/serial/simulated";
import { browserSerial, type SerialPortInfo } from "@/serial/types";

const BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600];
const LINE_ENDINGS = [
  { label: "LF", value: "\n" },
  { label: "CRLF", value: "\r\n" },
  { label: "None", value: "" },
];
const WINDOW_MS = 10_000;
const LOG_LIMIT = 500;

interface LogEntry {
  id: number;
  direction: "rx" | "tx";
  text: string;
}

export function App() {
  const [simulate, setSimulate] = useState(
    () => new URLSearchParams(window.location.search).get("sim") === "1",
  );
  const [baudRate, setBaudRate] = useState(115200);
  const [lineEnding, setLineEnding] = useState("\n");
  const [state, setState] = useState<ConnectionState>("closed");
  const [portLabel, setPortLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [channelNames, setChannelNames] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [, setLogVersion] = useState(0);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const followLog = useRef(true);
  const log = useRef<LogEntry[]>([]);
  const logId = useRef(0);
  const logFlushPending = useRef(false);
  const channels = useRef(new Map<string, Channel>());

  // Data can arrive hundreds of lines a second: entries collect in a ref and React renders the
  // log at most once per animation frame.
  const appendLog = (direction: LogEntry["direction"], text: string) => {
    log.current.push({ id: logId.current++, direction, text });
    if (log.current.length > LOG_LIMIT) log.current.splice(0, log.current.length - LOG_LIMIT);
    if (logFlushPending.current) return;
    logFlushPending.current = true;
    requestAnimationFrame(() => {
      logFlushPending.current = false;
      setLogVersion((version) => version + 1);
    });
  };

  const [simulatedSerial] = useState(() => new SimulatedSerial());
  const [connection] = useState(
    () =>
      new SerialConnection({
        onFrame(frame) {
          appendLog("rx", frame.text);
          for (const [name, value] of Object.entries(parseValues(frame.text))) {
            let channel = channels.current.get(name);
            if (!channel) {
              const color = CHANNEL_COLORS[channels.current.size % CHANNEL_COLORS.length];
              channel = { name, color, series: new Series() };
              channels.current.set(name, channel);
              setChannelNames([...channels.current.keys()]);
            }
            channel.series.push(frame.time, value);
          }
        },
        onState: setState,
        onError(cause) {
          setError(describeSerialError(cause));
        },
      }),
  );

  useEffect(() => () => void connection.close(), [connection]);

  useEffect(() => {
    let frame = 0;
    const render = () => {
      if (canvasRef.current) {
        drawRolling(
          canvasRef.current,
          [...channels.current.values()],
          performance.now(),
          WINDOW_MS,
        );
      }
      frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frame);
  }, []);

  useLayoutEffect(() => {
    const element = logRef.current;
    if (element && followLog.current) element.scrollTop = element.scrollHeight;
  });

  const supported = simulate || browserSerial() !== undefined;
  const busy = state === "opening" || state === "closing";

  async function connect() {
    setError(null);
    const serial = simulate ? simulatedSerial : browserSerial();
    if (!serial) {
      setError(
        window.isSecureContext
          ? "This browser cannot use serial ports. Open the page in desktop Chrome or Edge."
          : "Serial ports only work on HTTPS pages.",
      );
      return;
    }
    try {
      // The device chooser only opens from a click, so nothing slow may run before this call.
      const port = await serial.requestPort();
      // The default 255-byte receive buffer overflows at high baud rates as soon as the page
      // stalls for a moment.
      await connection.open(port, { baudRate, bufferSize: 65_536 });
      setPortLabel(simulate ? "Simulated device" : describePort(port.getInfo()));
    } catch (cause) {
      setError(describeSerialError(cause));
    }
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    try {
      await connection.send(draft + lineEnding);
      appendLog("tx", draft);
      setDraft("");
    } catch (cause) {
      setError(describeSerialError(cause));
    }
  }

  function clear() {
    log.current = [];
    for (const channel of channels.current.values()) channel.series.clear();
    setLogVersion((version) => version + 1);
  }

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-5xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Serial monitor</h1>
        <Badge variant={state === "open" ? "default" : "outline"} data-testid="connection-state">
          {state === "open" ? `Connected · ${portLabel} · ${baudRate} baud` : STATE_LABELS[state]}
        </Badge>
      </header>

      <section className="flex flex-wrap items-end gap-3" aria-label="Connection">
        <label className="grid gap-1 text-sm">
          <span className="text-muted-foreground">Baud rate</span>
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50"
            value={baudRate}
            disabled={state !== "closed"}
            onChange={(event) => setBaudRate(Number(event.target.value))}
          >
            {BAUD_RATES.map((rate) => (
              <option key={rate} value={rate}>
                {rate}
              </option>
            ))}
          </select>
        </label>
        <label className="flex h-10 items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4"
            checked={simulate}
            disabled={state !== "closed"}
            onChange={(event) => setSimulate(event.target.checked)}
          />
          Simulated device
        </label>
        {state === "open" ? (
          <Button variant="outline" onClick={() => void connection.close()}>
            <Unplug size={16} /> Disconnect
          </Button>
        ) : (
          <Button disabled={busy || !supported} onClick={() => void connect()}>
            <Plug size={16} /> Connect
          </Button>
        )}
        {!supported && (
          <p className="basis-full text-sm text-muted-foreground">
            This browser has no serial support. Open the page in desktop Chrome or Edge, or try the
            simulated device.
          </p>
        )}
      </section>

      {error && <Alert variant="destructive">{error}</Alert>}

      <section className="grid gap-2" aria-label="Chart">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span>Last {WINDOW_MS / 1000} s</span>
          {channelNames.map((name) => (
            <span key={name} className="inline-flex items-center gap-1.5">
              <span
                className="size-2.5 rounded-full"
                style={{ background: channels.current.get(name)?.color }}
              />
              {name}
            </span>
          ))}
        </div>
        <canvas
          ref={canvasRef}
          role="img"
          aria-label="Live chart of received values"
          className="h-64 w-full rounded-lg border border-border text-muted-foreground"
        />
      </section>

      <section className="grid min-h-0 flex-1 gap-2" aria-label="Log">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">Log</h2>
          <Button variant="ghost" size="sm" onClick={clear}>
            <Eraser size={14} /> Clear
          </Button>
        </div>
        <div
          ref={logRef}
          role="log"
          aria-live="off"
          className="h-64 overflow-y-auto rounded-lg border border-border bg-card p-3 font-mono text-xs leading-5"
          onScroll={(event) => {
            const element = event.currentTarget;
            followLog.current =
              element.scrollHeight - element.scrollTop - element.clientHeight < 24;
          }}
        >
          {log.current.map((entry) => (
            <div key={entry.id} className="whitespace-pre-wrap break-all">
              <span
                className={entry.direction === "tx" ? "text-blue-600" : "text-muted-foreground"}
              >
                {entry.direction === "tx" ? "TX " : "RX "}
              </span>
              {entry.text}
            </div>
          ))}
        </div>
        <form className="flex gap-2" onSubmit={(event) => void send(event)}>
          <Input
            aria-label="Message"
            placeholder="Text to send"
            value={draft}
            disabled={state !== "open"}
            onChange={(event) => setDraft(event.target.value)}
          />
          <select
            aria-label="Line ending"
            className="h-10 rounded-md border border-input bg-background px-2 text-sm disabled:opacity-50"
            value={lineEnding}
            disabled={state !== "open"}
            onChange={(event) => setLineEnding(event.target.value)}
          >
            {LINE_ENDINGS.map((ending) => (
              <option key={ending.label} value={ending.value}>
                {ending.label}
              </option>
            ))}
          </select>
          <Button type="submit" disabled={state !== "open"}>
            <Send size={16} /> Send
          </Button>
        </form>
      </section>
    </main>
  );
}

const STATE_LABELS: Record<ConnectionState, string> = {
  closed: "Not connected",
  opening: "Connecting…",
  open: "Connected",
  closing: "Disconnecting…",
};

function describePort({ usbVendorId, usbProductId }: SerialPortInfo) {
  if (usbVendorId === undefined) return "Serial port";
  const hex = (id = 0) => id.toString(16).padStart(4, "0");
  return `USB ${hex(usbVendorId)}:${hex(usbProductId)}`;
}
