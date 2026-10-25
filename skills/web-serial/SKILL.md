---
name: web-serial
display-name: Serial Port Apps
description: >-
  Build web apps that talk to serial devices through the browser's Web Serial API: serial monitors,
  live plots and oscilloscope-style charts, command consoles, dashboards and data loggers (上位机) for
  Arduino, ESP32, STM32, Raspberry Pi Pico, sensors, robots and other USB-serial or Bluetooth-serial
  hardware. Use it with the app skill whenever a page must read from or write to a serial port, and
  when a line protocol or matching firmware has to be designed for such a page. Not for native desktop
  programs, WebUSB, WebHID or Bluetooth GATT devices.
localizations:
  zh-CN:
    display-name: 串口上位机
    description: 做能直接连接串口设备的网页：串口监视、实时波形、指令收发和数据记录，适合 Arduino、ESP32、STM32、传感器和小车，在电脑上的 Chrome 或 Edge 里打开就能用，不用安装软件。
    keywords: [串口, 上位机, 串口助手, 串口调试, 示波器, 波形, 单片机, Arduino, ESP32, Web Serial]
  zh-TW:
    display-name: 序列埠監控
    description: 製作能直接連接序列埠裝置的網頁：序列埠監看、即時波形、指令收發與資料記錄，適用 Arduino、ESP32、STM32、感測器和自走車，在電腦上的 Chrome 或 Edge 開啟即可使用，不必安裝軟體。
    keywords: [序列埠, 串列埠, 上位機, 示波器, 波形, 微控制器, Arduino, ESP32, Web Serial]
  zh-HK:
    display-name: 序列埠監控
    description: 製作可以直接連接序列埠裝置的網頁：序列埠監察、即時波形、指令收發和數據記錄，適合 Arduino、ESP32、STM32、感應器和小車，在電腦上用 Chrome 或 Edge 打開就能用，不用安裝軟件。
    keywords: [序列埠, 串口, 上位機, 示波器, 波形, 單片機, Arduino, ESP32, Web Serial]
  en-US:
    display-name: Serial Port Apps
    description: Build web pages that connect straight to serial devices to monitor them, plot live data, send commands and log readings from Arduino, ESP32, STM32, sensors and robots. They run in Chrome or Edge on a computer with nothing to install.
    keywords: [serial port, serial monitor, serial plotter, oscilloscope, microcontroller, Arduino, ESP32, Web Serial]
---

# Serial port apps

Build the page as an Application with the `app` skill and follow its workflow. This skill adds what a serial page needs on top of it: a protocol fixed before the interface, a simulated device that stands in for the hardware, and the rules of Web Serial.

## Environment

- The package directory is the `sandbox_path` returned by `skill_read` (normally `/skills/web-serial`) and is read-only. `assets/example/client` is a minimal serial monitor laid over the `web-static` scaffold: device chooser, baud rate, connect and disconnect, a received/sent log, one line of text to send, a rolling chart of every value it finds, and a simulated device. Read its `src/serial/` modules and `src/chart.ts` before writing serial code.
- Read the references when the task touches them: [references/framing.md](references/framing.md) for line and binary framing, encodings, hex, read errors and request/response; [references/plotting.md](references/plotting.md) for charts, trajectories, spectra, recording and export; [references/firmware.md](references/firmware.md) for protocol design, bandwidth and the code on the device.
- Only the user's browser can reach their serial ports. The sandbox, its headless browser and the platform cannot, so every check you run uses the simulated device, and the user connects the real hardware.

## Where the page works

- Chromium-based desktop browsers: Chrome, Edge and Opera. Recent Chrome on Android reaches Bluetooth serial devices; do not promise USB serial on phones. Firefox, Safari and the Favonis mobile app have no Web Serial.
- A secure context: HTTPS or `localhost`. Preview and published Applications are HTTPS. An iframe from another origin needs `allow="serial"`; the Favonis Preview pane grants it, other sites that embed the page must too.
- One program owns a port at a time. The Arduino IDE serial monitor, another tab or another tool holding the port makes `open()` fail.
- USB-serial chips such as CH340 and CP2102 may need the vendor driver on Windows and macOS before any browser sees the port.

## Workflow

1. **Fix the protocol first.** Settle the baud rate, line ending, line format, value names, units, sample rate and commands before building the interface. Default to text lines of named values, `temp=21.5 hum=40\n`, which the example parses and the Arduino Serial Plotter also reads. Use binary frames only when the bandwidth budget in firmware.md requires them. When the user has firmware or sample output, take the format from its print statements or the sample; ask only when neither exists and the format changes the product. Record the protocol in `/DESIGN.md`.
2. **Start from the example.** Scaffold `web-static` through the `app` skill, then lay the example over it and drop the scaffold's starter copy:

   ```bash
   cp -R --no-preserve=mode /skills/web-serial/assets/example/client/. client/
   rm client/src/content.json
   ```

   For an existing project, copy `src/serial/` and `src/chart.ts` into its source instead and adapt the imports. Then shape it to the task: `parseValues` for the protocol, the controls the device needs (command buttons, set-points, gauges, tables), and the interface text in the user's language. Keep connection, framing and the simulated device as separate modules.
3. **Make the simulated device tell the truth.** Change `sample()` and `answer()` in `simulated.ts` so it prints the same lines at the same rate, and answers commands the way the real device does, boot text included. Keep the "Simulated device" switch and `?sim=1` in the product: it is how you check the page and how the user tries it without hardware.
4. **Check.** Add tests for the real protocol: feed sample lines whole and split one byte at a time and expect the same values. Run the component's tests and build. In Preview, open the page with `?sim=1` and use the browser skill to confirm data flows, the chart moves, values are labelled, and commands get their answers.
5. **Hand off.** Say how to connect: on a computer, open Favonis in Chrome or Edge and use the Preview pane, or open the published address; plug in the device, press Connect, pick the port and use the baud rate from the protocol. Deliver firmware written for the page with the same settings, and say that you tested against the simulated device only.

## Rules the code must keep

- Call `requestPort()` directly in the click handler, before any other `await`: the chooser needs the user's gesture. Ports chosen before come back from `getPorts()` without a chooser, which is how to offer "reconnect".
- Never decode a chunk on its own. A `read()` ends anywhere, inside a line, between `\r` and `\n` or inside a multi-byte character; collect bytes into complete lines or frames, then decode.
- Hold one reader loop and one writer per connection. Shut down in order: cancel the reader, release it, release the writer, close the port. A port closed with a locked stream stays busy until the page reloads.
- Port settings are fixed while it is open. Changing the baud rate means closing and opening again; disable the settings while connected, as the example does.
- Opening the port usually resets Arduino Uno, Nano and ESP32 boards through DTR: expect boot text before data, leave lines that do not parse in the log, and wait for the device's ready line before sending commands. Boards that stay silent after opening (RP2040, Leonardo and other native-USB boards waiting in `while (!Serial)`) need `port.setSignals({ dataTerminalReady: true })` after `open()`.
- Time comes from arrival time or the device's timestamps, never from the sample count. The chart's time axis ends at the current time and moves even when no data arrives.
- Bound memory and work: ring buffers for samples, a capped log, at most one render per animation frame. Never set React state or redraw a canvas once per received line.
- Raise `bufferSize` in `open()` (the example uses 64 KiB); the default 255 bytes overflows at high baud rates as soon as the page is busy.
