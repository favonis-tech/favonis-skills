# Framing, encodings and writing

Bytes arrive in chunks whose boundaries mean nothing. Every receive path is: chunk → framer → complete line or frame → decode → parse. The example's `LineFramer` (`src/serial/framing.ts`) does this for text lines.

## Text lines

- `LineFramer` splits on `\n` and drops a trailing `\r`, so `\n` and `\r\n` both work, including a `\r\n` split across two chunks.
- A device that ends lines with `\r` only (some modems and instruments) needs the delimiter changed to `\r`. Do not split on both: `\r\n` would then produce empty lines.
- Bytes without a newline for `maxLineBytes` are passed on as one line. A wrong baud rate shows up as such garbage in the log, which is the quickest diagnosis there is.
- Parse values by name, not by column position, so firmware can add or reorder fields. A line that does not parse (boot banner, debug print, error message) belongs in the log, not the chart.
- Lines with a fixed prefix are a cheap way to multiplex message types: `D temp=21.5` data, `A led on` acknowledgements, `E overheat` errors.

## Binary frames

Use them only when text does not fit the bandwidth budget (firmware.md). A frame that can resynchronize after noise needs a header, a length and a checksum:

```
0xAA 0x55 | length (payload bytes) | payload | checksum = low 8 bits of (length + payload bytes)
```

```ts
export class BinaryFramer {
  private pending = new Uint8Array(0);

  push(chunk: Uint8Array): Uint8Array[] {
    const bytes = new Uint8Array(this.pending.length + chunk.length);
    bytes.set(this.pending);
    bytes.set(chunk, this.pending.length);
    const frames: Uint8Array[] = [];
    let i = 0;
    while (i + 4 <= bytes.length) {
      if (bytes[i] !== 0xaa || bytes[i + 1] !== 0x55) {
        i++;
        continue;
      }
      const length = bytes[i + 2];
      const end = i + 4 + length;
      if (end > bytes.length) break; // The rest of the frame has not arrived yet.
      let sum = length;
      for (let k = i + 3; k < end - 1; k++) sum += bytes[k];
      if ((sum & 0xff) === bytes[end - 1]) {
        frames.push(bytes.slice(i + 3, end - 1));
        i = end;
      } else {
        i++; // A false header or a corrupted frame: search again one byte later.
      }
    }
    this.pending = bytes.slice(i);
    return frames;
  }
}
```

- Read payloads with a `DataView` and say the byte order explicitly: `new DataView(p.buffer, p.byteOffset, p.byteLength).getInt16(0, true) / 100`. Little-endian is what Arduino, ESP32 and STM32 produce when they copy a struct.
- Fixed-point integers (`int16` hundredths) are smaller and steadier than floats.
- A sequence byte in the payload makes lost frames visible: count the gaps.
- CRC-16/MODBUS instead of the 8-bit sum when the link is noisy (long cables, motors, radio modules).
- Keep framers and payload parsers pure (`Uint8Array` in, values out) and test them with frames split one byte at a time and with garbage in front.

## Encodings and hex

- UTF-8 is the default. `TextDecoder` also decodes legacy encodings: `new TextDecoder("gbk")`, `"gb18030"`, `"big5"`, `"shift_jis"`. `TextEncoder` only produces UTF-8, so keep commands ASCII when the device expects GBK, or encode them by hand.
- The labels `"ascii"` and `"latin1"` both decode as windows-1252, which turns bytes 0x80–0x9F into characters such as `€`. Show raw bytes as hex instead of relying on them.
- Hex view: `[...bytes].map((b) => b.toString(16).padStart(2, "0")).join(" ")`. Hex input: strip spaces, reject an odd number of digits or non-hex characters, then `Uint8Array.from(pairs, (p) => parseInt(p, 16))`.
- A text/hex toggle that applies to data already received needs the raw chunks kept, not just decoded lines.

## Read errors

- `BreakError`, `FramingError`, `ParityError` and `BufferOverrunError` leave the port open: `port.readable` is replaced and the read loop continues (the example's loop does this). Bytes around the error are lost, so reset or resynchronize the framer if a frame was cut.
- `NetworkError` means the device is gone: `port.readable` becomes null, the loop ends and the port must be closed and chosen again or reopened after it reappears. `navigator.serial` fires `connect` and `disconnect` events only for ports this site was granted.
- Parity, stop bits and flow control must match the device. A mismatch usually shows up as garbage or silence rather than as an error.

## Writing

- Keep one writer for the connection. `write()` calls queue inside the stream; calling `port.writable.getWriter()` per message throws when an earlier write still holds the lock.
- Text commands: append the line ending the firmware expects, once. Offer LF, CRLF and none when the user types raw commands.
- Binary commands: `writer.write(Uint8Array.of(0xaa, 0x55, 1, 0x10, 0x11))`.
- Timers that send periodically (polling, heartbeats) start on open and stop on close; a timer that outlives the port throws on every tick.
- Request/response: send, then wait for the matching line with a timeout instead of sleeping a fixed time.

```ts
// Inside the component or store that receives frames.
const waiters = new Set<(text: string) => boolean>();
function onFrame(text: string) {
  for (const waiter of waiters) if (waiter(text)) waiters.delete(waiter);
}

function request(connection: SerialConnection, command: string, match: (line: string) => boolean, ms = 1000) {
  return new Promise<string>((resolve, reject) => {
    const timer = setTimeout(() => {
      waiters.delete(waiter);
      reject(new Error(`No answer to ${command}`));
    }, ms);
    const waiter = (line: string) => {
      if (!match(line)) return false;
      clearTimeout(timer);
      resolve(line);
      return true;
    };
    waiters.add(waiter);
    connection.send(`${command}\n`).catch(reject);
  });
}
```
