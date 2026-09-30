---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Reviewing this PR for our webhook receiver before I approve it -- thoughts?

```ts
// src/webhooks/verify.ts
import crypto from "crypto";

export function verifySignature(payload: string, signature: string, secret: string): boolean {
  const expected = crypto.createHmac("sha256", secret).update(payload).digest("hex");
  return expected === signature;
}
```

```ts
// src/webhooks/config.ts
import fs from "fs/promises";

export async function loadWebhookConfig(path: string) {
  try {
    return JSON.parse(await fs.readFile(path, "utf8"));
  } catch {}
  return {};
}
```
