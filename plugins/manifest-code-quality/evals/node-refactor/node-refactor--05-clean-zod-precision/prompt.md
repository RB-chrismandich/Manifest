---
max_turns: 15
timeout_seconds: 480
allowed_tools: [Skill, Read, Grep, Glob]
runs: 3
model: sonnet
---
Here's the new input schema for our create-user endpoint. Anything to flag before I open the PR?

```ts
// src/schemas/user.ts
import { z } from "zod";

const CreateUserSchema = z.object({
  email: z.string().email(),
  age: z.number().int().min(0).max(150),
});

export type CreateUserInput = z.infer<typeof CreateUserSchema>;

export function parseCreateUser(input: unknown): CreateUserInput {
  return CreateUserSchema.parse(input);
}
```
