---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Some users are reporting the login form just spins for a long time after they type certain email addresses -- no crash, no error, just hangs. Can you look through the auth code broadly, not just for that one thing?

```ts
// src/auth/validate.ts
export function isValidEmailFormat(email: string): boolean {
  const re = /^([a-zA-Z0-9_.+-]+)+@([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$/;
  return re.test(email);
}
```

```ts
// src/auth/login.ts
import { Router } from "express";
import { findUserByEmail } from "../db";
import { isValidEmailFormat } from "./validate";

const router = Router();

router.post("/login", async (req, res) => {
  const email = req.body.email;
  if (!isValidEmailFormat(email)) {
    return res.status(400).json({ error: "invalid email" });
  }
  const user = await findUserByEmail(email);
  res.json(user);
});

export default router;
```
