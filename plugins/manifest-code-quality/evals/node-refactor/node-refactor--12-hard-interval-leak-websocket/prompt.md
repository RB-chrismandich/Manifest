---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Our WS presence service works fine in staging, but memory climbs slowly in prod under high connection churn (lots of clients connecting and disconnecting). Here's the relevant file -- what's going on?

```typescript
// src/ws/presence.ts
import { WebSocket, WebSocketServer } from "ws";

export function attachPresence(wss: WebSocketServer) {
  wss.on("connection", (socket: WebSocket) => {
    const heartbeat = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ping", ts: Date.now() }));
      }
    }, 15000);

    socket.on("message", (data) => {
      handleMessage(socket, data);
    });
  });
}

function handleMessage(socket: WebSocket, data: unknown) {
  // business logic omitted
}
```
