import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/app";

describe("Serial monitor", () => {
  it("connects to the simulated device, shows its data and sends a line", async () => {
    // jsdom has no canvas; the chart skips drawing without a context.
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    window.history.replaceState(null, "", "/?sim=1");
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    const log = screen.getByRole("log");
    await waitFor(() => expect(within(log).getAllByText(/^sine=/).length).toBeGreaterThan(0));
    expect(screen.getByTestId("connection-state")).toHaveTextContent("Connected");
    expect(screen.getByText("noise")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
      target: { value: "led on" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(within(log).getByText("ack led on")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await waitFor(() =>
      expect(screen.getByTestId("connection-state")).toHaveTextContent("Not connected"),
    );
  });
});
