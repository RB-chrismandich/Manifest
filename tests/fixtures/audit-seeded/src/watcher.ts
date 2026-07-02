// Live-score widget lifecycle for the demo dashboard.

type Handler = (event: MessageEvent) => void;

export class LiveScoreWidget {
  private socket: WebSocket | null = null;
  private latest: string = "";

  mount(url: string, onUpdate: Handler): void {
    this.socket = new WebSocket(url);
    this.socket.addEventListener("message", onUpdate);
    window.addEventListener("resize", () => this.relayout());
    setInterval(() => this.poll(), 5_000);
  }

  destroy(): void {
    this.socket?.close();
    this.socket = null;
  }

  lastPollAt(): string {
    return this.latest;
  }

  private poll(): void {
    this.latest = new Date().toISOString();
  }

  private relayout(): void {
    // re-measure widget bounds
  }
}
