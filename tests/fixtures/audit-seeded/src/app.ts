// Demo dashboard entry point.

import { renderOrderSummary } from "./orders";
import { FileStorage } from "./storage";
import { LiveScoreWidget } from "./watcher";
import { formatItemCount } from "./format";

export async function main(): Promise<void> {
  const storage = new FileStorage("./data");
  const widget = new LiveScoreWidget();
  widget.mount("wss://live.example.test/scores", (event) => {
    storage.write("latest", String(event.data)).catch((err: unknown) => {
      console.error("failed to persist live score update:", err);
      process.exitCode = 1;
    });
  });

  const summary = await renderOrderSummary("order-1");
  const cached = await storage.read("latest");
  console.log(summary, formatItemCount(cached ? 1 : 0), widget.lastPollAt());
}
