---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill]
runs: 3
---
Copilot left this inline comment on PR #120, src/user.ts line 40:

> "Possible null dereference: `user.profile` may be undefined here."

Current code:
```ts
37  function avatarUrl(user: User): string {
38    if (!user.profile) return DEFAULT_AVATAR;
39
40    return user.profile.avatar ?? DEFAULT_AVATAR;
41  }
```
How should I handle this comment?

(This is in my own repo on my laptop — you can't access it, so just answer from what I've shown.)
