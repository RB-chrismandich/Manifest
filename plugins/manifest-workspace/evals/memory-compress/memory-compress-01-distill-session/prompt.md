---
max_turns: 6
timeout_seconds: 150
allowed_tools: [Skill, Read, Glob, Grep]
runs: 3
---
Distill this session into one entry for my memory log. Use this header exactly: `## 14:32 | feat/auth-refresh`. Output just the entry.

Session transcript:
> user: the refresh token isn't rotating, users get logged out after 15 min
> assistant: Found it — `rotate_refresh()` in `auth/refresh_token.py` compared expiry with `<` instead of `<=`, so tokens expiring exactly at the boundary were rejected. Fixed the comparison and added a boundary test.
> user: run the tests
> assistant: `pytest tests/auth` — 41 passed (was 38; 3 new boundary tests).
> user: great, open a PR
> assistant: Opened PR #412 "fix(auth): rotate refresh token at expiry boundary", commit a1b2c3d. Also bumped `AUTH_SCHEMA_VERSION` 14→15 because the token table got a new `rotated_at` column.
> user: thanks, that's it for today
