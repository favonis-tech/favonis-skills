# Protocol design and firmware

The page and the firmware share one contract. Write it down in `/DESIGN.md` and as a comment at the top of the firmware, and change both together.

## The contract

- Port settings: baud rate, data bits, parity, stop bits (8N1 unless the device says otherwise), flow control.
- Line ending (`\n` recommended) or the binary frame layout with byte order and checksum.
- Every value: name, unit, scale (`temp` in °C; `angle` in degrees, not radians) and the rate it is sent at.
- Every command: its text, its arguments and its answer, including the error answer.
- A ready line after boot (`ready fw=1.2`), so the page knows the device has started and which protocol version it speaks.

## Bandwidth budget

With 8N1 framing each byte costs 10 bits on the wire: bytes per second ≈ baud rate / 10.

| Baud rate | Bytes per second | 30-byte lines per second |
| --------- | ---------------- | ------------------------ |
| 9,600     | 960              | 32                       |
| 115,200   | 11,520           | 384                      |
| 460,800   | 46,080           | 1,536                    |
| 921,600   | 92,160           | 3,072                    |

Stay below about 70% of the budget so bursts and command answers still fit. When text does not fit, lower the rate, average on the device, raise the baud rate if the USB-serial chip supports it, or switch to binary frames (framing.md). Boards with native USB serial (ESP32-S2/S3/C3 USB port, RP2040, STM32 USB CDC, Arduino Leonardo and Micro) ignore the baud rate and run at USB speed, with one exception: opening them at 1200 baud makes many of them (Leonardo, Micro, SAMD and RP2040 Arduino cores) reboot into the bootloader, so never offer 1200 for them.

## Example sketch matching the page

This Arduino sketch speaks the example page's protocol: named values every 20 ms, a ready line and acknowledged commands.

```cpp
// Protocol: 115200 8N1, lines end with \n.
// Device → page: "ready", then "sine=<-1..1> light=<0..1023>" every 20 ms; "ack <command>" or "error <command>".
// Page → device: "led on", "led off".
const unsigned long PERIOD_MS = 20;
unsigned long lastSample = 0;
String command;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(115200);
  Serial.println("ready");
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample >= PERIOD_MS) {  // Subtraction stays correct when millis() wraps around.
    lastSample = now;
    Serial.print("sine=");
    Serial.print(sin(now / 1000.0 * PI), 3);
    Serial.print(" light=");
    Serial.println(analogRead(A0));
  }
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c != '\n') {
      if (command.length() < 64) command += c;
      continue;
    }
    bool known = command == "led on" || command == "led off";
    if (known) digitalWrite(LED_BUILTIN, command == "led on" ? HIGH : LOW);
    Serial.print(known ? "ack " : "error ");
    Serial.println(command);
    command = "";
  }
}
```

`Serial.println` ends lines with `\r\n`, which the example framer accepts.

## Firmware pitfalls

- Opening the port toggles DTR, and boards with a USB-serial chip (Uno, Nano, most ESP32 DevKits) reset. The first second after connecting is bootloader output; print the ready line from `setup()` and let the page wait for it before sending commands.
- Boards with native USB may wait for the host in `while (!Serial)` and send nothing until DTR is set. The page then calls `port.setSignals({ dataTerminalReady: true })` after `open()`; or drop the wait from the firmware.
- Printing blocks when the transmit buffer is full, which stretches the sampling loop. Sample on a timer, print from the main loop, check `Serial.availableForWrite()` before long prints, and never print inside an interrupt.
- Floats print slowly on small AVR boards; send scaled integers (`temp=2153` for 21.53 °C) when the rate is high.
- With hardware flow control both sides must implement RTS/CTS; a page that expects it from a device that does not will stall.
- Logic levels: a 3.3 V board's TX/RX connects straight to a 3.3 V USB-serial adapter (CH340, CP2102, FT232); 5 V devices need level shifting.

## Checklist before handing over firmware

- Baud rate, line ending, value names, units and command texts match the page and the simulated device exactly.
- The device prints a ready line after boot.
- The data rate fits the bandwidth budget with margin.
- Sampling is not slowed by printing.
- The protocol is written at the top of the sketch.
