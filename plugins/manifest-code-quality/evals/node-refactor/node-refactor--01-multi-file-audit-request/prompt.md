---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
We're onboarding a bigger customer onto this service soon. Can you do a full refactor audit of these files and give me a prioritized roadmap?

```ts
// src/db.ts
import { Pool } from "pg";
const pool = new Pool();

export async function findUserByEmail(email: string) {
  const result = await pool.query(`SELECT * FROM users WHERE email = '${email}'`);
  return result.rows[0];
}
```

```ts
// src/config.ts
export const config = {
  jwtSecret: "super-secret-dev-key-2024",
  stripeKey: "sk_live_51ABCDEXAMPLE", // gitleaks:allow
};
```

```ts
// src/handlers/upload.ts
import { exec } from "child_process";

export function convertFile(filename: string, cb: (err: Error | null) => void) {
  exec(`convert ${filename} output.png`, cb);
}
```
