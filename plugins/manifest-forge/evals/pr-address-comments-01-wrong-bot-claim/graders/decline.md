---
type: llm
focus: last_message
weight: 1
---
Pass if the answer concludes the claim is wrong (line 38 already guards `user.profile`) and recommends declining it with that evidence — NOT adding a redundant null check just to satisfy the bot.
